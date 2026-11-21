"""Windows POC for retaining indexes while cooperating queries use them."""
import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from evaluate_natural_approvals import CASES
from exercise_release_races import publish
from index_reader_lock import current_scope, lease, retention
from query_approval import ACTIVE, RUNTIME, load_context, query, switch_index


def reader(active, gate, output):
    headers, records, directory = load_context()
    with lease(active) as scope:
        gate.with_suffix(".ready").touch()
        deadline = time.monotonic() + 35
        while not gate.exists():
            if time.monotonic() >= deadline:
                raise TimeoutError("Reader gate did not open")
            time.sleep(0.05)
        result = query(CASES[1][1], scope, headers, records, directory)
        output.write_text(json.dumps(result), encoding="utf-8")


def start_reader(active, gate, output):
    process = subprocess.Popen([sys.executable, "-B", __file__, "--reader",
                                str(active), str(gate), str(output)])
    deadline = time.monotonic() + 20
    while not gate.with_suffix(".ready").exists():
        if process.poll() is not None:
            raise RuntimeError(f"Reader failed: {process.returncode}")
        if time.monotonic() >= deadline:
            process.kill()
            process.wait()
            raise TimeoutError("Reader failed to acquire lease")
        time.sleep(0.05)
    return process


def exercise(candidate):
    context = load_context()
    old = current_scope(ACTIVE)
    assert candidate != old
    result = {}
    managed = {old, candidate}
    with tempfile.TemporaryDirectory(dir=RUNTIME, prefix="lease-") as folder:
        root = Path(folder)
        active, gate, answer = root / ACTIVE.name, root / "finish", root / "answer.json"
        switch_index(active, old, *context, revision=0)
        initial_candidate = retention(active, candidate, set(), managed)
        assert initial_candidate["eligible"] and initial_candidate["revision"] == 0
        process = start_reader(active, gate, answer)
        try:
            assert publish(active, old, 0, candidate, context) == "published"
            recheck = retention(active, candidate, set(), managed,
                                expected_revision=initial_candidate["revision"])
            assert recheck["reasons"] == ["stale_snapshot", "active"] and not recheck["eligible"]
            result["stale_cleanup_snapshot"] = {"before": initial_candidate, "recheck": recheck}
            protected = retention(active, old, {old}, managed)
            assert protected["reasons"] == ["rollback", "in_use"], protected
            result["during_switch"] = protected
            gate.touch()
            assert process.wait(timeout=30) == 0
            state = json.loads(answer.read_text(encoding="utf-8"))
            assert state["result"] == ["revoked", None, "APPROVAL-028"]
            assert state["hit_source_uri"].startswith(old + "/")
            result["completed_on_old_scope"] = state
            result["rollback_protected"] = retention(active, old, {old}, managed)
            assert result["rollback_protected"]["reasons"] == ["rollback"]
            result["active_protected"] = retention(active, candidate, set(), managed)
            assert result["active_protected"]["reasons"] == ["active"]
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()

        gate = root / "crash"
        process = start_reader(active, gate, answer)
        process.kill()
        process.wait(timeout=20)
        result["after_crash"] = retention(active, candidate, set(), managed)
        assert result["after_crash"]["reasons"] == ["active"]
        assert len(result["after_crash"]["abandoned"]) == 1
        result["no_reader_no_rollback"] = retention(active, old, set(), managed)
        assert result["no_reader_no_rollback"]["eligible"]
        result["unregistered"] = retention(active, candidate + "-unknown", set(), managed)
        assert result["unregistered"]["reasons"] == ["unregistered"]
        assert not result["unregistered"]["eligible"]
    assert current_scope(ACTIVE) == old
    output = RUNTIME / f"index-leases-{time.strftime('%Y%m%d-%H%M%S')}.json"
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
    print(f"{len(result)} retention checks passed")
    print(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", nargs="?")
    parser.add_argument("--reader", nargs=3, type=Path)
    args = parser.parse_args()
    if args.reader:
        active, gate, output = args.reader
        if active.resolve().parent.parent != RUNTIME.resolve() or not active.parent.name.startswith("lease-"):
            parser.error("reader requires an isolated lease pointer")
        reader(active, gate, output)
    elif args.candidate:
        exercise(args.candidate)
    else:
        parser.error("provide a candidate")
