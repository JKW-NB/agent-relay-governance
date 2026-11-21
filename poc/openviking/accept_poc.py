"""Run the POC acceptance checks against the four local demo instances."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

from evaluate_natural_approvals import CASES
from query_approval import HERE, RUNTIME

CASES_TO_RUN = (
    (CASES[0][1], "2026-10-10", "active", "APPROVAL-027"),
    (CASES[1][1], "2026-10-12", "revoked", "APPROVAL-028"),
    (CASES[2][1], "2026-10-12", "active", "APPROVAL-031"),
    (CASES[-1][1], "2026-10-12", "matter_required", None),
)


def run(script, *args, env=None):
    completed = subprocess.run(
        [sys.executable, "-B", str(HERE / script), *args], env=env,
        encoding="utf-8", capture_output=True, timeout=90,
    )
    if completed.returncode:
        raise RuntimeError(f"{script} failed: {completed.stderr}")
    return completed.stdout.strip()


def main():
    rows = []
    for port in range(1933, 1937):
        url = f"http://127.0.0.1:{port}"
        root = RUNTIME if port == 1933 else RUNTIME / f"compose-{port}/ov"
        pointer_file = root / "approval-active-index.json"
        before = pointer_file.read_bytes()
        pointer = json.loads(before)
        with urlopen(url + "/health", timeout=10) as response:
            health = json.load(response)
        assert health["healthy"], (port, health)
        env = {**os.environ, "ARG_POC_RUNTIME": str(root), "ARG_POC_OV_URL": url,
               "PYTHONIOENCODING": "utf-8"}
        queries = []
        for question, as_of, status, source_id in CASES_TO_RUN:
            result = json.loads(run("query_approval.py", question, "--as-of", as_of, env=env))
            assert result["status"] == status, (port, result)
            if source_id:
                assert result["state_source"]["id"] == source_id, result
                assert result["hit_source_uri"].startswith(pointer["scope"] + "/"), result
            queries.append({"as_of": as_of, "question": question, "status": status, "state_source": source_id})
        assert pointer_file.read_bytes() == before
        rows.append({"port": port, "version": health["version"], "scope": pointer["scope"], "queries": queries})

    snapshot_report = RUNTIME / "backup-restore-20261110-101047.json"
    snapshot = json.loads(run("verify_stack_backup.py", str(snapshot_report), "--exercise"))
    assert snapshot["files"] == 86
    assert set(snapshot["faults_detected"]) == {"modified", "missing", "unexpected"}
    native = run("exercise_pilot_readiness.py")
    native_report = Path(native.splitlines()[-1])
    assert len(json.loads(native_report.read_text(encoding="utf-8"))) == 8
    pointer = json.loads((RUNTIME / "approval-active-index.json").read_text(encoding="utf-8"))
    candidate = pointer["rollback_scope"]
    races = run("exercise_release_races.py", candidate)
    leases = run("exercise_index_leases.py", candidate)
    release = Path(races.splitlines()[-1])
    occupancy = Path(leases.splitlines()[-1])
    assert len(json.loads(release.read_text(encoding="utf-8"))) == 6
    assert len(json.loads(occupancy.read_text(encoding="utf-8"))) == 8
    output = RUNTIME / f"poc-acceptance-{time.strftime('%Y%m%d-%H%M%S')}.json"
    with output.open("x", encoding="utf-8") as stream:
        json.dump({"instances": rows, "snapshot": snapshot, "native_report": str(native_report),
                   "release_report": str(release), "reader_report": str(occupancy)}, stream, indent=2)
    print("16 live queries, snapshot verification, native ARG and release regression passed")
    print(output)


if __name__ == "__main__":
    main()
