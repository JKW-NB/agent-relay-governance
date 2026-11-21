"""Build a fresh synthetic approval index and verify it before optional activation."""
import argparse
import json
import uuid

from evaluate import request
from evaluate_natural_approvals import CASES
from exercise_index_release import upload, verify_manifest
from exercise_release_races import publication_lock
from query_approval import ACTIVE, RUNTIME, load_context, query, switch_index


def activate(pointer, scope, headers, records, directory):
    with publication_lock(pointer):
        if pointer.exists():
            return "existing_pointer_preserved"
        switch_index(pointer, scope, headers, records, directory, revision=0)
    return "activated"


def bootstrap(activate_if_empty=False):
    headers, records, directory = load_context()
    key = uuid.uuid4().hex[:12]
    scope = f"viking://resources/approval-bootstrap-{key}"
    request("/fs/mkdir", headers, {"uri": scope})
    for record in records.values():
        upload(record, scope, headers)
    manifest = verify_manifest(scope, records, headers)
    cases = (
        (CASES[0][1], "2026-10-10", ("active", "Riley Chen", "APPROVAL-027")),
        (CASES[0][1], "2026-10-12", ("revoked", None, "APPROVAL-028")),
        (CASES[2][1], "2026-10-12", ("active", "Dana Park", "APPROVAL-031")),
        (CASES[-1][1], "2026-10-12", None),
    )
    checks = []
    for question, as_of, expected in cases:
        result = query(question, scope, headers, records, directory, as_of)
        if expected is None:
            assert result["status"] == "matter_required", result
        else:
            assert result["result"] == expected, result
            assert result["hit_source_uri"].startswith(scope + "/"), result
        checks.append({"question": question, "as_of": as_of, "result": result})
    report = RUNTIME / f"approval-bootstrap-{key}.json"
    with report.open("x", encoding="utf-8") as stream:
        json.dump({"scope": scope, "manifest": manifest, "checks": checks}, stream, indent=2)
    activation = activate(ACTIVE, scope, headers, records, directory) if activate_if_empty else "not_requested"
    return {"scope": scope, "report": str(report), "activation": activation,
            "records": len(manifest), "checks": len(checks)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--activate-if-empty", action="store_true")
    args = parser.parse_args()
    print(json.dumps(bootstrap(args.activate_if_empty), indent=2))
