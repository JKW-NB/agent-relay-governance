"""Query the isolated approval POC and exercise index cutover."""
import argparse
import json
import os
import tempfile
import time
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

from evaluate import request
from index_reader_lock import lease
from evaluate_matter_directory import directed, QUERY
from evaluate_natural_approvals import CASES, identify_matter
from evaluate_parallel_approvals import HERE, RUNTIME, resolve_matter

ACTIVE = RUNTIME / "approval-active-index.json"
OLD_SCOPE = "viking://resources/parallel-approvals-20261107-223813"
NEW_SCOPE = "viking://resources/candidate-depth-20261107-225734"
AS_OF = "2026-10-12"


def load_context():
    config = json.loads((RUNTIME / "ov.conf").read_text(encoding="utf-8"))
    headers = {
        "X-API-Key": config["server"]["root_api_key"],
        "X-OpenViking-Account": "arg-poc",
        "X-OpenViking-User": "evaluator",
        "Content-Type": "application/json",
    }
    fixture = json.loads((HERE / "parallel-approvals.json").read_text(encoding="utf-8"))
    records = {row["id"]: row for row in fixture}
    directory = json.loads((HERE / "matter-directory.json").read_text(encoding="utf-8"))
    return headers, records, directory


def query(question, scope, headers, records, directory, as_of=AS_OF):
    matter = identify_matter(question)
    if matter is None:
        return {"status": "matter_required"}
    hits = request("/search/find", headers, {
        "query": question, "target_uri": scope, "limit": 3,
    })["resources"]
    for hit in hits:
        uri = hit["uri"]
        if not uri.startswith(scope + "/") or not uri.endswith(".md"):
            continue
        record_id = Path(uri).stem
        entry = records.get(record_id)
        if entry is None or entry["matter_id"] != matter:
            continue
        if uri != f"{scope}/{record_id}/{record_id}.md":
            continue
        source = request("/content/read?" + urlencode({"uri": uri}), headers)
        if source.strip() != entry["text"]:
            continue
        result, chain = resolve_matter(records, record_id, matter, as_of)
        return {
            "path": "shared_search", "status": result[0], "result": result,
            "hit_source_uri": uri, "local_chain": chain, "state_source": records.get(result[2]),
        }
    return {"path": "directed_fallback", **directed(question, directory, records, scope, headers, as_of)}


def switch_index(active, candidate, headers, records, directory, *, revision=None, rollback_scope=None):
    """Check every directory entry before atomically replacing the active pointer."""
    for matter, record_id in directory.items():
        entry = records[record_id]
        if entry["matter_id"] != matter:
            raise ValueError(f"Invalid local mapping for {matter}")
        uri = f"{candidate}/{record_id}/{record_id}.md"
        body = request("/content/read?" + urlencode({"uri": uri}), headers)
        if body.strip() != entry["text"]:
            raise ValueError(f"Candidate source differs for {matter}")
        hits = request("/search/find", headers, {
            "query": entry["text"], "target_uri": f"{candidate}/{record_id}", "limit": 3,
        })["resources"]
        if not any(hit["uri"] == uri for hit in hits):
            raise ValueError(f"Candidate record is not searchable for {matter}")
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=active.parent, prefix=active.name + ".",
        suffix=".tmp", delete=False,
    ) as stream:
        staged = Path(stream.name)
        try:
            pointer = {"scope": candidate}
            if revision is not None:
                pointer["revision"] = revision
            if rollback_scope is not None:
                pointer['rollback_scope'] = rollback_scope
            json.dump(pointer, stream)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            stream.close()
            staged.unlink(missing_ok=True)
            raise
    try:
        staged.replace(active)
    finally:
        staged.unlink(missing_ok=True)


def exercise(active, headers, records, directory):
    if active.exists():
        raise FileExistsError(f"Exercise requires an unused pointer: {active}")
    switch_index(active, OLD_SCOPE, headers, records, directory)
    initial = active.read_bytes()
    results = []
    for invalid in (NEW_SCOPE + "-missing", NEW_SCOPE + "/APPROVAL-031"):
        try:
            switch_index(active, invalid, headers, records, directory)
        except (OSError, ValueError, RuntimeError) as error:
            assert active.read_bytes() == initial
            backup = query(CASES[2][1], OLD_SCOPE, headers, records, directory)
            assert backup["status"] == "active", backup
            results.append({"case": "failed cutover", "candidate": invalid,
                            "error_type": type(error).__name__, "retained_query": backup})
        else:
            raise AssertionError("Unusable scope was accepted")

    switch_index(active, NEW_SCOPE, headers, records, directory)
    assert json.loads(active.read_text(encoding="utf-8"))["scope"] == NEW_SCOPE
    for name, question, path, status in (
        ("shared archive search", CASES[1][1], "shared_search", "revoked"),
        ("backup fallback", QUERY, "directed_fallback", "active"),
        ("ambiguous", CASES[-1][1], None, "matter_required"),
    ):
        result = query(question, NEW_SCOPE, headers, records, directory)
        assert (result.get("path"), result["status"]) == (path, status), (name, result)
        results.append({"case": name, **result})
    switch_index(active, OLD_SCOPE, headers, records, directory)
    assert active.read_bytes() == initial
    results.append({"case": "rollback", "scope": OLD_SCOPE})
    switch_index(active, NEW_SCOPE, headers, records, directory)
    output = RUNTIME / f"approval-cutover-{time.strftime('%Y%m%d-%H%M%S')}.json"
    with output.open("x", encoding="utf-8") as stream:
        json.dump(results, stream, indent=2)
    print(f"{len(results)} cutover and query checks passed")
    print(output)


def query_with_service_status(question, scope, headers, records, directory, as_of=AS_OF):
    try:
        return query(question, scope, headers, records, directory, as_of)
    except HTTPError as error:
        if error.code in (401, 403):
            return {"status": "index_access_denied", "http_status": error.code}
        if error.code == 404:
            return {"status": "index_resource_missing", "http_status": error.code}
        if error.code >= 500:
            return {"status": "index_unavailable", "http_status": error.code}
        raise
    except (URLError, TimeoutError):
        return {"status": "index_unavailable"}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("question", nargs="?")
    parser.add_argument("--exercise", action="store_true")
    parser.add_argument('--as-of', default=AS_OF, type=date.fromisoformat)
    args = parser.parse_args()
    if args.exercise == bool(args.question):
        parser.error("provide a question or --exercise")
    headers, records, directory = load_context()
    if args.exercise:
        with tempfile.TemporaryDirectory(dir=RUNTIME, prefix='cutover-') as directory_path:
            exercise(Path(directory_path) / ACTIVE.name, headers, records, directory)
        return
    with lease(ACTIVE) as scope:
        result = query_with_service_status(args.question, scope, headers, records, directory, str(args.as_of))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
