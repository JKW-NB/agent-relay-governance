"""Regression for source-bound short answers, without a generation model."""
import argparse
import json
import time
from pathlib import Path

from evaluate_decomposed_pilot import SOURCE_LINES, TASKS
from query_public_evidence import answer_with_fallback, evidence_for, load_snapshot, short_answer

EXPECTED = (
    "Add `DECISIONS.md` (empty template) and `LESSONS.md` (empty template).",
    "In `CURRENT_STATE.yaml`: bump `schema_version: 2`, add a `current.task` block for the active task, add a `context` block.",
    "python scripts/validate_governance.py",
    {"formal_ready": True, "blocking_reasons": []},
    0,
    "CURRENT_STATE + PROJECT_LOG",
    "re-hash, update row, mark `REHASHED_AFTER_REVIEW`",
    "flag (do not silently delete the row; log it).",
    "ok / mismatch / missing",
)
PARAPHRASES = (
    (0, "What two Markdown files should I add for V2 migration?"),
    (2, "What validation command should I run after V2 migration?"),
    (4, "How many score mismatches are allowed before closing the gate?"),
    (8, "What three outcomes does the final manifest verification report?"),
)


def main(path):
    report, sources = load_snapshot(path)
    rows = []
    cases = [(index, task[1]) for index, task in enumerate(TASKS)] + list(PARAPHRASES)
    for use_ov in (True, False):
        for index, question in cases:
            result = answer_with_fallback(
                question, evidence_for(report, sources, question, use_ov)["evidence"], report, sources,
            )
            assert result.get("answer") == EXPECTED[index], (question, result)
            source, first, last = SOURCE_LINES[index]
            assert {(c["source"], c["line"]) for c in result["citations"]} == {
                (source, number) for number in range(first, last + 1)
            }, result
            for citation in result["citations"]:
                assert citation["quote"] == sources[source].splitlines()[citation["line"] - 1]
            rows.append({"question": question, "mode": "ov" if use_ov else "local", "result": result})
    rejects = (
        "Who approved OpenViking production deployment?",
        "What is the migration validation command and who approved it?",
        "What is the migration validation command and the gate score mismatch count?",
    )
    for question in rejects:
        assert answer_with_fallback(question, [], report, sources)["status"] == "unsupported_question"
    assert answer_with_fallback(TASKS[6][1], [], report, {**sources, "ARCHIVING": ""})["status"] == "insufficient_evidence"
    conflicting = [{"source": "REVIEW", "quote": f"Revised scores match (machine-check: {n} mismatches)"} for n in (0, 1)]
    assert short_answer(TASKS[4][1], conflicting)["status"] == "conflicting_evidence"
    output = path.with_name(f"public-short-regression-{time.strftime('%Y%m%d-%H%M%S')}.json")
    with output.open("x", encoding="utf-8") as stream:
        json.dump({"rows": rows, "unsupported": rejects, "checks": ["missing_source", "conflicting_evidence"]}, stream, indent=2)
    print(f"{len(rows)} correct answers with exact citations; {len(rejects) + 2} refusal checks passed")
    print(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    main(parser.parse_args().report)
