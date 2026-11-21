"""Inventory isolated release scopes without mutating OpenViking."""
import json
import time

from evaluate import request
from index_reader_lock import retention
from query_approval import ACTIVE, RUNTIME, load_context


def main():
    headers, _, _ = load_context()
    pointer = json.loads(ACTIVE.read_text(encoding='utf-8'))
    active = pointer['scope']
    reports = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(RUNTIME.glob("approval-release-*.json"))
        if not path.name.startswith("approval-release-races-")
    ]
    candidates = {report["candidate"] for report in reports}
    candidates.update(
        json.loads(path.read_text(encoding="utf-8"))["scope"]
        for path in RUNTIME.glob("approval-bootstrap-*.json")
    )
    rollback = {report['old'] for report in reports} - {active}
    if pointer.get('rollback_scope'):
        rollback.add(pointer['rollback_scope'])
    rows = []
    for scope in sorted({active} | rollback | candidates):
        state = "active" if scope == active else "rollback_reference" if scope in rollback else "retained_candidate"
        rows.append({"scope": scope, "classification": state,
                     "delete_allowed": False, "reader_tracking": "unavailable"})
    listing = request("/fs/ls?uri=viking%3A%2F%2Fresources", headers)
    known = {row["scope"] for row in rows}
    for entry in listing:
        uri = entry.get("uri", "").rstrip("/")
        if uri.startswith("viking://resources/") and uri not in known:
            rows.append({"scope": uri, "classification": "unclassified",
                         "delete_allowed": False, "reader_tracking": "unavailable"})
    managed = {active} | rollback | candidates
    for row in rows:
        observed = retention(ACTIVE, row["scope"], rollback, managed, expected_revision=pointer.get("revision", 0))
        row.update({
            "reader_tracking": "cooperating_local_queries",
            "retention_reasons": observed["reasons"],
            "active_reader_count": observed["active_readers"].count(row["scope"]),
            "abandoned_registrations": len(observed["abandoned"]),
            "eligible_in_local_snapshot": observed["eligible"],
        })
    assert sum(row["classification"] == "active" for row in rows) == 1
    output = RUNTIME / f"index-retention-preflight-{time.strftime('%Y%m%d-%H%M%S')}.json"
    with output.open("x", encoding="utf-8") as stream:
        json.dump({"active": active, "rows": rows, "unmodified": True}, stream, indent=2)
    print(f"Inventory: {len(rows)} scopes")
    print(output)


if __name__ == "__main__":
    main()
