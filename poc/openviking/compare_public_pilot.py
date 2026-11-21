"""Compare local keyword context with OV-augmented context on one committed snapshot."""
import argparse
import hashlib
import json
import re
import time
from pathlib import Path
from urllib.parse import urlencode

from evaluate import MODEL, generate, request
from query_approval import load_context

STOP_WORDS = set("a an and are before can do does for how i in is it may of on or should the to was what when who with".split())
MAX_CONTEXT = 3600


def words(text):
    return set(re.findall(r"[a-z0-9]+", text.casefold())) - STOP_WORDS


def local_context(question, sources):
    terms = words(question)
    ranked = []
    for key, document in sources.items():
        for section in re.split(r"(?m)(?=^#{1,6} )", document):
            section = section.strip()
            if section:
                ranked.append((len(terms & words(section)), key, section))
    return [(key, section) for _, key, section in sorted(ranked, reverse=True)]


def budget(candidates):
    evidence = []
    remaining = MAX_CONTEXT
    for source_id, text in candidates:
        snippet = text[:min(1200, remaining)]
        if any(key == source_id and snippet == prior for key, prior in evidence):
            continue
        evidence.append((source_id, snippet))
        remaining -= len(snippet)
        if remaining <= 0:
            break
    return evidence


def audit_hits(scope, hits, sources, headers):
    audits = []
    for hit in hits:
        uri = hit["uri"]
        if not uri.startswith(scope + "/"):
            raise ValueError(f"Out-of-scope hit: {uri}")
        key = uri.removeprefix(scope + "/").split("/", 1)[0]
        if key not in sources or not uri.endswith(".md"):
            continue
        text = request("/content/read?" + urlencode({"uri": uri}), headers).strip()
        exact = bool(text) and text in sources[key]
        canonical = " ".join(text.split())
        whitespace = bool(canonical) and canonical in " ".join(sources[key].split())
        audits.append({"id": key, "uri": uri, "exact": exact, "normalized": whitespace, "text": text})
    return audits


def main(report_path):
    report = json.loads(report_path.read_text(encoding="utf-8"))
    sources = {}
    for key, record in report["manifest"].items():
        data = report_path.with_name(key + ".md").read_bytes()
        if hashlib.sha256(data).hexdigest() != record["sha256"]:
            raise ValueError(f"Snapshot changed: {key}")
        sources[key] = data.decode("utf-8").strip()
    headers, _, _ = load_context()
    rows = []
    for index, case in enumerate(report["queries"], 1):
        question = case["query"]
        for group in (("G0", "G1") if index % 2 else ("G1", "G0")):
            started = time.perf_counter()
            local = local_context(question, sources)
            audits = []
            if group == "G1":
                hits = request("/search/find", headers, {
                    "query": question, "target_uri": report["scope"], "limit": 5,
                })["resources"]
                audits = audit_hits(report["scope"], hits, sources, headers)
            ov = [(hit["id"], hit["text"]) for hit in audits if hit["normalized"]]
            evidence = budget(ov + local)
            prep = time.perf_counter() - started
            raw = generate(question, evidence, 60 - prep, True)
            try:
                response = json.loads(raw["response"])
            except json.JSONDecodeError:
                response = None
            citations = []
            for item in (response or {}).get("citations", []):
                phrase = item["quote"].strip()
                citations.append({
                    **item, "exact_in_context": bool(phrase) and any(
                        key == item["id"] and phrase in text for key, text in evidence
                    ),
                })
            row = {"case": index, "group": group, "question": question,
                   "expected_sources": case["expected"], "evidence": evidence,
                   "ov_audit": audits, "prep_ms": round(prep * 1000, 2),
                   "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                   "answer": response, "raw": raw["response"], "citations": citations}
            rows.append(row)
            print(index, group, ascii((response or {}).get("answer", raw["response"]))[:500], flush=True)
    output = report_path.with_name(f"paired-public-pilot-{time.strftime('%Y%m%d-%H%M%S')}.json")
    with output.open("x", encoding="utf-8") as stream:
        json.dump({"model": MODEL, "max_context_chars": MAX_CONTEXT, "rows": rows}, stream, indent=2)
    print(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    main(parser.parse_args().report)
