"""Compare G1 answers with and without direct governance evidence."""
import argparse
import json
import re
import time
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

from evaluate import HERE, MODEL, RUNTIME, generate, request

QUESTIONS = {
    "ASSIGN-013": "Who was assigned to implement SHA-256 archive verification?",
    "APPROVAL-027": "Who approved the SHA-256 archive verification change?",
    "DEPLOY-041": "On what date was SHA-256 archive verification deployed to production?",
}


NAME = r"[A-Z][a-z]+(?: [A-Z][a-z]+)+"
FACT_PATTERNS = {
    "ASSIGN": re.compile(
        rf"The relay team assigned (?P<value>{NAME}) to implement SHA-256 archive verification\."
    ),
    "APPROVAL": re.compile(
        rf"(?P<value>{NAME}) approved the SHA-256 archive verification change on \d{{4}}-\d{{2}}-\d{{2}}\."
    ),
    "DEPLOY": re.compile(
        r"The SHA-256 archive verification change was deployed to production on "
        r"(?P<value>\d{4}-\d{2}-\d{2})\."
    ),
}


def extract_fact(expected_id, evidence):
    """Extract a single fact from the synthetic record formats in this POC."""
    record_type = expected_id.split("-", 1)[0]
    pattern = FACT_PATTERNS[record_type]
    candidates = {}
    for evidence_id, content, *_ in evidence:
        if evidence_id.split("-", 1)[0] != record_type:
            continue
        for line in content.splitlines():
            match = pattern.fullmatch(line.strip())
            if not match:
                continue
            value = match["value"]
            if record_type == "DEPLOY":
                try:
                    date.fromisoformat(value)
                except ValueError:
                    continue
            candidates.setdefault(value, []).append({"id": evidence_id, "quote": match[0]})

    if len(candidates) != 1:
        reason = "conflicting_records" if candidates else "no_matching_fact"
        return {"answer": "Insufficient evidence", "citations": []}, reason
    value, citations = next(iter(candidates.items()))
    return {"answer": value, "citations": citations}, "extracted"

def verify_answer(row):
    """Gate short factual answers against an in-scope record of the required type."""
    record_type = row["expected_source"].split("-", 1)[0]
    sources = {item[0]: item[1] for item in row["evidence"]}
    response = row["answer"]
    answer = response["answer"].strip()
    refusal = {"answer": "Insufficient evidence", "citations": []}
    if answer == refusal["answer"]:
        return {"status": "refused", "reason": "model_refused", **refusal}
    typed_sources = {
        key: value for key, value in sources.items()
        if key.split("-", 1)[0] == record_type
    }
    if not typed_sources:
        return {"status": "blocked", "reason": "required_record_type_missing", **refusal}
    verified = []
    for citation in response["citations"]:
        source = typed_sources.get(citation["id"])
        quote = citation["quote"].strip()
        if source and quote and answer and quote in source and answer in quote:
            verified.append(citation)
    if not verified:
        return {"status": "blocked", "reason": "answer_not_grounded_in_required_record", **refusal}
    return {"status": "accepted", "answer": answer, "citations": verified}


def replay(path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    for row in payload["runs"]:
        row["verified_answer"] = verify_answer(row)
        print(row["condition"], row["expected_source"], row["verified_answer"])
    output = path.with_name(path.stem + "-gated.json")
    with output.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2)
    print(output)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--replay', type=Path)
    parser.add_argument('--filter-record-type', action='store_true')
    parser.add_argument('--extract-fact', action='store_true')
    args = parser.parse_args()
    if args.extract_fact and args.replay:
        parser.error('--extract-fact requires a live run')
    if args.replay:
        replay(args.replay)
        return
    config = json.loads((RUNTIME / "ov.conf").read_text(encoding="utf-8"))
    headers = {
        "X-API-Key": config["server"]["root_api_key"],
        "X-OpenViking-Account": "arg-poc",
        "X-OpenViking-User": "evaluator",
        "Content-Type": "application/json",
    }
    fixtures = {
        path.stem: path.read_text(encoding="utf-8").strip()
        for path in (HERE / "governance-pairs").glob("*.md")
    }
    scopes = json.loads((RUNTIME / "governance-pair-scopes.json").read_text(encoding="utf-8"))
    rows = []
    for expected_id, question in QUESTIONS.items():
        for condition, scope in scopes.items():
            started = time.perf_counter()
            result = request(
                "/search/find", headers,
                {"query": question, "target_uri": scope, "limit": 5},
            )
            evidence = []
            for hit in result["resources"]:
                uri = hit["uri"]
                evidence_id = Path(uri).stem
                if evidence_id not in fixtures:
                    continue
                if not uri.startswith(scope + "/"):
                    raise ValueError(f"Out-of-scope hit: {uri}")
                if not uri.endswith(".md"):
                    uri += f"/{evidence_id}.md"
                source = request("/content/read?" + urlencode({"uri": uri}), headers).strip()
                if source != fixtures[evidence_id]:
                    raise ValueError(f"Source mismatch: {uri}")
                evidence.append((evidence_id, source, hit["score"], uri))
            model_evidence = evidence
            if args.filter_record_type or args.extract_fact:
                record_type = expected_id.split("-", 1)[0]
                model_evidence = [
                    item for item in evidence if item[0].split("-", 1)[0] == record_type
                ]
            if args.extract_fact:
                answer, reason = extract_fact(expected_id, model_evidence)
                raw = {'done_reason': reason}
            elif model_evidence:
                raw = generate(question, model_evidence, 60 - (time.perf_counter() - started), True)
                answer = json.loads(raw["response"])
            else:
                raw = {"done_reason": "required_record_type_missing"}
                answer = {"answer": "Insufficient evidence", "citations": []}
            sources = {item[0]: item[1] for item in model_evidence}
            audits = [
                {"id": c["id"], "verbatim": bool(c["quote"]) and c["quote"] in sources.get(c["id"], ""),
                 "expected_source": c["id"] == expected_id}
                for c in answer["citations"]
            ]
            row = {
                "condition": condition, "question": question, "expected_source": expected_id,
                "evidence": evidence, "model_evidence_ids": [item[0] for item in model_evidence],
                "answer": answer, "citation_audit": audits,
                "done_reason": raw.get("done_reason"),
            }
            row['verified_answer'] = verify_answer(row)
            rows.append(row)
            print(condition, expected_id, answer, flush=True)
    label = 'typed' if args.filter_record_type else 'unfiltered'
    if args.extract_fact:
        label = 'extracted'
    output = RUNTIME / f"governance-pairs-{label}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    with output.open("x", encoding="utf-8") as stream:
        json.dump({"model": None if args.extract_fact else MODEL, "mode": label, "runs": rows}, stream, indent=2)
    print(output)


if __name__ == "__main__":
    main()
