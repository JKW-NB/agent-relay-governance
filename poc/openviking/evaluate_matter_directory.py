"""Probe directed fallback using a project-local synthetic matter directory."""
import argparse
import json
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode

from evaluate import request
from evaluate_natural_approvals import CASES, identify_matter
from evaluate_parallel_approvals import HERE, RUNTIME, resolve_matter

QUERY = next(query for name, query, _ in CASES if name == "near match")
AS_OF = "2026-10-12"


def directed(query, directory, records, scope, headers, as_of=AS_OF):
    matter = identify_matter(query)
    if matter is None:
        return {"status": "matter_required"}
    mapped_id = directory.get(matter)
    if mapped_id is None:
        return {"status": "mapping_missing"}
    entry = records.get(mapped_id)
    if entry is None or entry["matter_id"] != matter:
        return {"status": "mapping_mismatch", "mapped_id": mapped_id}

    target = f"{scope}/{mapped_id}"
    try:
        hits = request("/search/find", headers, {
            "query": query, "target_uri": target, "limit": 3,
        })["resources"]
    except HTTPError as error:
        if error.code == 404:
            return {"status": "scope_missing", "target": target}
        raise
    expected_uri = f"{target}/{mapped_id}.md"
    if not any(hit["uri"] == expected_uri for hit in hits):
        return {"status": "target_missing", "target": target, "hits": hits}
    try:
        source = request("/content/read?" + urlencode({"uri": expected_uri}), headers)
    except HTTPError as error:
        if error.code == 404:
            return {"status": "source_missing", "source_uri": expected_uri, "hits": hits}
        raise
    if source.strip() != entry["text"]:
        return {"status": "source_mismatch", "source_uri": expected_uri, "hits": hits}

    result, chain = resolve_matter(records, mapped_id, matter, as_of)
    return {
        "status": result[0], "result": result, "matter_id": matter,
        "hit_source_uri": expected_uri, "hits": hits, "local_chain": chain,
        "state_source": records.get(result[2]),
    }


def main(scope):
    cfg = json.loads((RUNTIME / "ov.conf").read_text(encoding="utf-8"))
    headers = {
        "X-API-Key": cfg["server"]["root_api_key"],
        "X-OpenViking-Account": "arg-poc", "X-OpenViking-User": "evaluator",
        "Content-Type": "application/json",
    }
    fixture = json.loads((HERE / "parallel-approvals.json").read_text(encoding="utf-8"))
    records = {row["id"]: row for row in fixture}
    directory = json.loads((HERE / "matter-directory.json").read_text(encoding="utf-8"))
    cases = (
        ("valid mapping", QUERY, directory, records, scope, ("active",)),
        ("old hit resolves to revocation", CASES[0][1], directory, records, scope, ("revoked",)),
        ("stale mapping points to another matter", QUERY,
         {**directory, "BACKUP-VERIFY": "APPROVAL-027"}, records, scope, ("mapping_mismatch",)),
        ("mapped record absent locally", QUERY,
         {**directory, "BACKUP-VERIFY": "APPROVAL-999"}, records, scope, ("mapping_mismatch",)),
        ("missing mapping", QUERY, {}, records, scope, ("mapping_missing",)),
        ("stale remote scope", QUERY, directory, records,
         scope + "-missing", ("scope_missing", "target_missing")),
        ("stale indexed source", QUERY, directory,
         {**records, "APPROVAL-031": {**records["APPROVAL-031"], "text": "Changed local source."}},
         scope, ("source_mismatch",)),
        ("ambiguous matter", "Is the SHA-256 verification approval still valid?",
         directory, records, scope, ("matter_required",)),
    )
    results = []
    for name, query, mapping, local, target, allowed in cases:
        started = time.perf_counter()
        result = directed(query, mapping, local, target, headers)
        assert result["status"] in allowed, (name, result)
        if name == "valid mapping":
            assert result["result"] == ("active", "Dana Park", "APPROVAL-031"), result
        elif name == "old hit resolves to revocation":
            assert result["result"] == ("revoked", None, "APPROVAL-028"), result
            assert result["hit_source_uri"].endswith("/APPROVAL-027.md"), result
        else:
            assert "result" not in result, (name, result)
        results.append({"case": name, "query": query, **result,
                        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2)})
        print(name, result["status"], flush=True)
    output = RUNTIME / f"matter-directory-{time.strftime('%Y%m%d-%H%M%S')}.json"
    with output.open("x", encoding="utf-8") as stream:
        json.dump({"scope": scope, "as_of": AS_OF, "results": results}, stream, indent=2)
    print(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("scope")
    main(parser.parse_args().scope)
