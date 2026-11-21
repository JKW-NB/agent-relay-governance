"""Benchmark candidate depth in an isolated, synthetic shared OV scope."""
import argparse
import json
import statistics
import time
from pathlib import Path

from evaluate import request
from evaluate_natural_approvals import CASES, identify_matter
from evaluate_parallel_approvals import HERE, RUNTIME, resolve_matter

EXPECTED = {
    "ARCHIVE-VERIFY": ("revoked", None, "APPROVAL-028"),
    "BACKUP-VERIFY": ("active", "Dana Park", "APPROVAL-031"),
}


def measure(scope, headers, records):
    rows = []
    for repetition in range(3):
        depths = (3, 10) if repetition % 2 == 0 else (10, 3)
        for name, query, expected_matter in CASES:
            matter = identify_matter(query)
            for depth in depths:
                started = time.perf_counter()
                hits = request("/search/find", headers, {
                    "query": query, "target_uri": scope, "limit": depth,
                })["resources"]
                assert all(hit["uri"].startswith(scope + "/") for hit in hits)
                ids = [Path(hit["uri"]).stem for hit in hits]
                rank = next(
                    (index for index, key in enumerate(ids, 1)
                     if matter and records.get(key, {}).get("matter_id") == matter), None,
                )
                if matter is None:
                    outcome = ("matter_required", None, None)
                elif rank is None:
                    outcome = ("target_missing", None, None)
                else:
                    outcome, _ = resolve_matter(records, ids[rank - 1], matter, "2026-10-12")
                rows.append({
                    "case": name, "query": query, "repetition": repetition + 1, "depth": depth,
                    "expected_matter": expected_matter, "identified_matter": matter,
                    "hits": hits, "target_rank": rank, "outcome": outcome,
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                })
    return rows


def main(scope):
    config = json.loads((RUNTIME / "ov.conf").read_text(encoding="utf-8"))
    headers = {
        "X-API-Key": config["server"]["root_api_key"],
        "X-OpenViking-Account": "arg-poc", "X-OpenViking-User": "evaluator",
        "Content-Type": "application/json",
    }
    fixture = json.loads((HERE / "parallel-approvals.json").read_text(encoding="utf-8"))
    records = {row["id"]: row for row in fixture}
    # The decoys are valid records from different matters, not unknown documents.
    records.update({
        f"APPROVAL-{index}": {"matter_id": f"DECOY-{index}", "type": "approval"}
        for index in range(101, 109)
    })
    rows = measure(scope, headers, records)
    summary = {}
    for depth in (3, 10):
        group = [row for row in rows if row["depth"] == depth]
        summary[depth] = {
            "runs": len(group),
            "correct_state": sum(tuple(row["outcome"]) == EXPECTED.get(row["expected_matter"]) for row in group),
            "target_missing": sum(row["outcome"][0] == "target_missing" for row in group),
            "matter_required": sum(row["outcome"][0] == "matter_required" for row in group),
            "wrong_release": sum(
                row["outcome"][0] in ("active", "revoked")
                and tuple(row["outcome"]) != EXPECTED.get(row["expected_matter"])
                for row in group
            ),
            "median_ms": statistics.median(row["elapsed_ms"] for row in group),
        }
    assert len(rows) == 36
    output = RUNTIME / f"candidate-depth-{time.strftime('%Y%m%d-%H%M%S')}.json"
    with output.open("x", encoding="utf-8") as stream:
        json.dump({"scope": scope, "summary": summary, "rows": rows}, stream, indent=2)
    print(json.dumps(summary))
    print(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("scope")
    main(parser.parse_args().scope)
