"""Verify that an OV semantic hit locates only its own approval stream."""
import json
import sys
import time
from pathlib import Path

from evaluate import request
from evaluate_governance_lifecycle import HERE, RUNTIME, resolve


def resolve_matter(records, seed_id, expected_matter, as_of):
    seed = records.get(seed_id)
    if seed is None or seed["matter_id"] != expected_matter:
        return ("unverified_matter", None, None), []
    chain = [
        record for record in records.values()
        if (record["matter_id"], record["type"]) == (seed["matter_id"], seed["type"])
    ]
    return resolve(chain, seed["type"], as_of), [record["id"] for record in chain]


def main(scope):
    cfg = json.loads((RUNTIME / "ov.conf").read_text(encoding="utf-8"))
    headers = {
        "X-API-Key": cfg["server"]["root_api_key"],
        "X-OpenViking-Account": "arg-poc",
        "X-OpenViking-User": "evaluator",
        "Content-Type": "application/json",
    }
    fixtures = json.loads((HERE / "parallel-approvals.json").read_text(encoding="utf-8"))
    records = {record["id"]: record for record in fixtures}
    results = []
    for matter, question, expected_seed, expected, expected_chain in (
        ("ARCHIVE-VERIFY", "APPROVAL-027 ARCHIVE-VERIFY Riley Chen approved SHA-256 relay archive verification.",
         "APPROVAL-027", ("revoked", None, "APPROVAL-028"), ["APPROVAL-027", "APPROVAL-028"]),
        ("BACKUP-VERIFY", "APPROVAL-031 BACKUP-VERIFY Dana Park approved SHA-256 relay backup verification.",
         "APPROVAL-031", ("active", "Dana Park", "APPROVAL-031"), ["APPROVAL-031"]),
    ):
        hits = request("/search/find", headers, {"query": question, "target_uri": scope, "limit": 1})["resources"]
        assert len(hits) == 1 and hits[0]["uri"].startswith(scope + "/"), hits
        seed_id = Path(hits[0]["uri"]).stem
        assert seed_id == expected_seed, hits
        result, chain = resolve_matter(records, seed_id, matter, "2026-10-12")
        assert (result, chain) == (expected, expected_chain), (result, chain)
        results.append({"query": question, "matter_id": matter, "hit": hits[0],
                        "local_chain": chain, "result": result})
        print(matter, seed_id, chain, result)

    for seed, matter in (("APPROVAL-027", "BACKUP-VERIFY"), ("APPROVAL-999", "ARCHIVE-VERIFY")):
        result, chain = resolve_matter(records, seed, matter, "2026-10-12")
        assert result == ("unverified_matter", None, None) and not chain
        results.append({"seed_id": seed, "matter_id": matter, "result": result, "local_chain": chain})
        print("rejected", seed, matter)

    output = RUNTIME / f"parallel-approvals-{time.strftime('%Y%m%d-%H%M%S')}.json"
    with output.open("x", encoding="utf-8") as stream:
        json.dump({"scope": scope, "as_of": "2026-10-12", "results": results}, stream, indent=2)
    print(output)


if __name__ == "__main__":
    main(sys.argv[1])
