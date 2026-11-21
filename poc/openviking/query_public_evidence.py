"""Return source-bound excerpts from the public ARG pilot snapshot."""
import argparse
import hashlib
import json
import re
import time
from pathlib import Path
from urllib.error import HTTPError, URLError

from compare_public_pilot import audit_hits
from evaluate import request
from evaluate_line_retrieval import expand_key_values, normalize, rank, windows
from query_approval import load_context


def load_snapshot(report_path):
    report = json.loads(report_path.read_text(encoding="utf-8"))
    sources = {}
    for key, entry in report["manifest"].items():
        data = report_path.with_name(key + ".md").read_bytes()
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise ValueError(f"Snapshot changed: {key}")
        sources[key] = data.decode("utf-8")
    return report, sources


def evidence_for(report, sources, question, use_ov=True):
    verified = {}
    mode = "local"
    if use_ov:
        headers, _, _ = load_context()
        try:
            hits = request("/search/find", headers, {
                "query": question, "target_uri": report["scope"], "limit": 5,
            })["resources"]
            for audit in audit_hits(report["scope"], hits, sources, headers):
                if audit["normalized"]:
                    verified.setdefault(audit["id"], set()).update(
                        normalize(line) for line in audit["text"].splitlines() if line.strip()
                    )
            mode = "ov_augmented" if verified else "local_no_verified_ov_hits"
        except (HTTPError, URLError, TimeoutError):
            mode = "local_ov_unavailable"
    selected = [
        {"source": key, "path": report["manifest"][key]["path"], "line": number,
         "quote": line, "score": round(score, 4),
         "seen_in_verified_ov_hit": normalize(line) in verified.get(key, set())}
        for score, key, number, line in rank(question, list(windows(sources)), verified)
    ]
    for extra in expand_key_values(question, sources, selected):
        extra["seen_in_verified_ov_hit"] = normalize(extra["quote"]) in verified.get(extra["source"], set())
        selected.append(extra)
    return {"commit": report["commit"], "mode": mode, "status": "candidate_evidence" if selected else "no_candidates",
            "evidence": selected}


EXTRA_SHORT_ANSWERS = {
    "migration_new_files": (
        r"\b(?:which|what) two (?:new )?markdown files\b.*\bmigration\b",
        "MIGRATION", r"^1\. (Add `DECISIONS\.md`.*`LESSONS\.md`.*)$",
    ),
    "migration_state_fields": (
        r"\b(?:schema version|schema_version)\b.*\btask block\b.*\bcontext block\b",
        "MIGRATION", r"^3\. (In `CURRENT_STATE\.yaml`:.*`schema_version: 2`.*`current\.task`.*`context`.*)$",
    ),
    "gate_refreshed_files": (
        r"\b(?:which|what) two (?:governance )?files\b.*\brefresh(?:ed)?\b.*\bgate\b",
        "REVIEW", r"^- \[ \] Gate JSON flipped, manifest updated, (CURRENT_STATE \+ PROJECT_LOG) refreshed\b",
    ),
    "manifest_changed_file": (
        r"\bmanifest row\b.*\bupdated\b.*\b(?:tracked|registered) file changes\b",
        "ARCHIVING", r"^\s*- in manifest AND content changed → (re-hash, update row, mark `REHASHED_AFTER_REVIEW`)$",
    ),
    "manifest_missing_file": (
        r"\bmanifest row\b.*\b(?:missing file|missing disk file)\b",
        "ARCHIVING", r"^4\. For each manifest row with missing disk file → (flag \(do not silently delete the row; log it\)\.)$",
    ),
    "manifest_verification_categories": (
        r"\b(?:three categories|three outcomes)\b.*\b(?:archive|manifest) verification\b",
        "ARCHIVING", r"^5\. Final verification: .* report `(ok / mismatch / missing)`\.",
    ),
}

def short_answer(question, candidates):
    """Extract only explicit fact types exercised in the public pilot."""
    text = question.casefold()
    intents = [
        intent for intent, (question_pattern, _, _) in EXTRA_SHORT_ANSWERS.items()
        if re.search(question_pattern, text)
    ]
    if "migration" in text and any(word in text for word in ("validate", "validator", "validation")) and "command" in text:
        intents.append("migration_validation_command")
    if {"formal_ready", "blocking_reasons"} <= set(re.findall(r"[a-z_]+", text)) and "gate" in text:
        intents.append("gate_close_values")
    if "mismatch" in text and "score" in text and "gate" in text and any(
        word in text for word in ("count", "how many", "number")
    ):
        intents.append("revised_score_mismatch_count")
    qualifier_text = re.sub(r"\bwhen a (?:(?:tracked|registered) file changes|manifest row refers to a missing file)\b", "", text)
    if len(intents) != 1 or re.search(r"\b(?:who|when|why)\b", qualifier_text):
        return {"status": "unsupported_question"}
    intent = intents[0]
    patterns = {
        "migration_validation_command": (
            ("MIGRATION", r"\bRun `(python scripts/validate_governance\.py)`"),),
        "gate_close_values": (
            ("REVIEW", r"^\s*formal_ready:\s*(true|false)\s*$"),
            ("REVIEW", r"^\s*blocking_reasons:\s*(\[\])\s*$"),
        ),
        "revised_score_mismatch_count": (
            ("REVIEW", r"Revised scores match.*machine-check:\s*(\d+)\s+mismatches"),),
    }
    patterns.update({intent: ((source, pattern),)
                     for intent, (_, source, pattern) in EXTRA_SHORT_ANSWERS.items()})
    values, citations = [], []
    for source, pattern in patterns[intent]:
        matches = {}
        for item in candidates:
            if item["source"] != source:
                continue
            match = re.search(pattern, item["quote"])
            if match:
                matches.setdefault(match[1], item)
        if len(matches) != 1:
            return {"status": "conflicting_evidence" if matches else "insufficient_evidence", "type": intent}
        value, citation = next(iter(matches.items()))
        values.append(value)
        citations.append(citation)
    answer = values[0]
    if intent == "gate_close_values":
        answer = {"formal_ready": values[0] == "true", "blocking_reasons": []}
    elif intent == "revised_score_mismatch_count":
        answer = int(values[0])
    return {"status": "answered", "type": intent, "answer": answer, "citations": citations}

def answer_with_fallback(question, candidates, report, sources):
    result = short_answer(question, candidates)
    if result["status"] != "insufficient_evidence":
        return {**result, "path": "ranked_candidates"}
    source = {
        "migration_validation_command": "MIGRATION",
        "gate_close_values": "REVIEW",
        "revised_score_mismatch_count": "REVIEW",
        **{intent: source for intent, (_, source, _) in EXTRA_SHORT_ANSWERS.items()},
    }[result["type"]]
    rows = [
        {"source": source, "path": report["manifest"][source]["path"], "line": number,
         "quote": line, "selection": "directed_snapshot"}
        for number, line in enumerate(sources[source].splitlines(), 1)
    ]
    return {**short_answer(question, rows), "path": "directed_snapshot"}

def verbatim_anchor(answer, candidates):
    """An exact excerpt can be anchored, without asserting that it answers the question."""
    text = (answer or {}).get("answer", "").strip()
    if not text or text == "Insufficient evidence":
        return []
    return [item for item in candidates if text in item["quote"]]


def exercise(report_path, answer_path):
    report, sources = load_snapshot(report_path)
    model = json.loads(answer_path.read_text(encoding="utf-8"))
    rows = []
    for row in model["results"]:
        for item in row["candidates"]:
            assert sources[item["source"]].splitlines()[item["line"] - 1] == item["quote"], item
        anchors = verbatim_anchor(row["answer"], row["candidates"])
        rows.append({"question": row["question"], "answer": row["answer"],
                     "verbatim_anchors": anchors, "evidence_complete": row["evidence_complete"]})
    queries = []
    for question in (
        "Which Python command validates governance after migration?",
        "What values must formal_ready and blocking_reasons have at gate close?",
        "Who approved the production deployment of the OpenViking integration?",
    ):
        result = evidence_for(report, sources, question)
        assert "answer" not in result and result["commit"] == report["commit"]
        assert all(sources[item["source"]].splitlines()[item["line"] - 1] == item["quote"]
                   for item in result["evidence"])
        queries.append({"question": question, **result})
    output = report_path.with_name(f"public-evidence-cli-{time.strftime('%Y%m%d-%H%M%S')}.json")
    with output.open("x", encoding="utf-8") as stream:
        json.dump({"replayed_answers": rows, "live_queries": queries}, stream, indent=2)
    print(f"{sum(bool(row['verbatim_anchors']) for row in rows)}/{len(rows)} answers have verbatim anchors")
    print(output)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("question", nargs="?")
    parser.add_argument("--local-only", action="store_true")
    parser.add_argument("--exercise", type=Path)
    parser.add_argument('--short-answer', action='store_true')
    args = parser.parse_args()
    if bool(args.question) == bool(args.exercise):
        parser.error("provide a question or --exercise with an answer report")
    if args.exercise:
        exercise(args.report, args.exercise)
    else:
        report, sources = load_snapshot(args.report)
        result = evidence_for(report, sources, args.question, not args.local_only)
        if args.short_answer:
            result["short_answer"] = answer_with_fallback(args.question, result["evidence"], report, sources)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
