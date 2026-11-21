"""Use a semantic hit to locate the local synthetic approval history."""
import json
import sys
import time
from pathlib import Path

from evaluate import request
from evaluate_governance_lifecycle import HERE, RUNTIME, resolve


def main(scope):
    config = json.loads((RUNTIME / "ov.conf").read_text(encoding="utf-8"))
    headers = {
        "X-API-Key": config["server"]["root_api_key"],
        "X-OpenViking-Account": "arg-poc",
        "X-OpenViking-User": "evaluator",
        "Content-Type": "application/json",
    }
    query = "APPROVAL-027 Riley Chen approved the SHA-256 archive verification change on October 8."
    result = request("/search/find", headers, {"query": query, "target_uri": scope, "limit": 1})
    hits = result["resources"]
    if len(hits) != 1 or not hits[0]["uri"].startswith(scope + "/"):
        raise AssertionError(f"Expected one in-scope semantic hit: {hits}")
    seed_id = Path(hits[0]["uri"]).stem
    assert seed_id == "APPROVAL-027", hits
    fixture = json.loads((HERE / "governance-lifecycle.json").read_text(encoding="utf-8"))
    by_id = {record["id"]: record for record in fixture["records"]}
    seed = by_id[seed_id]
    # The synthetic fixture contains only one governance stream per record type.
    chain = [record for record in by_id.values() if record["type"] == seed["type"]]
    checks = []
    for as_of, expected in (
        ("2026-10-10", ("active", "Riley Chen", "APPROVAL-027")),
        ("2026-10-11", ("revoked", None, "APPROVAL-028")),
    ):
        hit_only = resolve([seed], seed["type"], as_of)
        resolved = resolve(chain, seed["type"], as_of)
        assert hit_only == ("active", "Riley Chen", "APPROVAL-027")
        assert resolved == expected, (as_of, resolved)
        checks.append({"as_of": as_of, "hit_only": hit_only, "resolved": resolved})
        print(as_of, "hit only:", hit_only, "local history:", resolved)
    output = RUNTIME / f"lifecycle-retrieval-{time.strftime('%Y%m%d-%H%M%S')}.json"
    with output.open("x", encoding="utf-8") as stream:
        json.dump({"query": query, "scope": scope, "hits": hits, "chain": chain, "checks": checks}, stream, indent=2)
    print(output)


if __name__ == "__main__":
    main(sys.argv[1])
