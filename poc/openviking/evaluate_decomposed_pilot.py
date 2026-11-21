"""Evaluate narrow facts on the same passages used for the broad questions."""
import argparse
import hashlib
import json
import time
from pathlib import Path

from evaluate import generate

TASKS = (
    (4, "Which two new Markdown files must be added during migration?", ("DECISIONS.md", "LESSONS.md")),
    (4, "What schema version, task block, and context block should CURRENT_STATE.yaml contain?", ("2", "current.task", "context")),
    (4, "Which Python command validates governance after migration?", ("python scripts/validate_governance.py",)),
    (5, "What values must formal_ready and blocking_reasons have at gate close?", ("formal_ready", "true", "blocking_reasons", "[]")),
    (5, "What count of revised-score mismatches is required before gate close?", ("0",)),
    (5, "Which two governance files are refreshed before declaring the gate closed?", ("CURRENT_STATE", "PROJECT_LOG")),
    (6, "How is the manifest row updated when a tracked file changes?", ("re-hash", "update", "REHASHED_AFTER_REVIEW")),
    (6, "What should be done when a manifest row refers to a missing file?", ("flag", "log")),
    (6, "What three categories must the final archive verification report?", ("ok", "mismatch", "missing")),
)


SOURCE_LINES = (
    ("MIGRATION", 60, 60), ("MIGRATION", 62, 62), ("MIGRATION", 65, 65),
    ("REVIEW", 83, 84), ("REVIEW", 92, 92), ("REVIEW", 96, 96),
    ("ARCHIVING", 38, 38), ("ARCHIVING", 40, 40), ("ARCHIVING", 41, 41),
)


def main(previous_path, line_only):
    previous = json.loads(previous_path.read_text(encoding="utf-8"))
    passages = {row["case"]: row["curated_evidence"] for row in previous["results"]}
    rows = []
    manifest = json.loads(previous_path.with_name("report.json").read_text(encoding="utf-8"))["manifest"]
    for (parent, question, expected), (key, first, last) in zip(TASKS, SOURCE_LINES, strict=True):
        source = previous_path.with_name(key + ".md").read_bytes()
        if hashlib.sha256(source).hexdigest() != manifest[key]["sha256"]:
            raise ValueError(f"Snapshot changed: {key}")
        reference_quote = "\n".join(source.decode("utf-8").splitlines()[first - 1:last])
        evidence = [(key, reference_quote)] if line_only else passages[parent]
        started = time.perf_counter()
        raw = generate(question, evidence, 60, True, model=previous["model"])
        try:
            answer = json.loads(raw["response"])
        except json.JSONDecodeError:
            answer = None
        response = (answer or {}).get("answer", "")
        audits = []
        for item in (answer or {}).get("citations", []):
            quote = item["quote"].strip()
            audits.append({**item, "exact": bool(quote) and any(
                key == item["id"] and quote in text for key, text in evidence
            )})
        matched = [term for term in expected if term.casefold() in response.casefold()]
        row = {"parent": parent, "question": question, "expected_terms": expected,
               "matched_terms": matched, "answer": answer, "raw": raw["response"],
               "reference": {"id": key, "lines": [first, last], "quote": reference_quote},
               "citations": audits, "done_reason": raw.get("done_reason"),
               "elapsed_ms": round((time.perf_counter() - started) * 1000, 2)}
        rows.append(row)
        print(parent, question, ascii(response), [(item["id"], item["exact"]) for item in audits], flush=True)
    mode = 'lines' if line_only else 'sections'
    output = previous_path.with_name(f"public-decomposed-{mode}-{time.strftime('%Y%m%d-%H%M%S')}.json")
    with output.open("x", encoding="utf-8") as stream:
        json.dump({"baseline": str(previous_path), "model": previous["model"], "rows": rows}, stream, indent=2)
    print(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("previous", type=Path)
    parser.add_argument('--line-only', action='store_true')
    args = parser.parse_args()
    main(args.previous, args.line_only)
