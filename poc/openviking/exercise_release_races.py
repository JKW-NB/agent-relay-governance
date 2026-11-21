"""Windows-only POC for serialized, compare-and-swap index publication."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError

from exercise_index_release import verify_manifest
from index_reader_lock import current_scope, publication_lock
from query_approval import ACTIVE, RUNTIME, load_context, query, switch_index
from evaluate_natural_approvals import CASES


def publish(active, expected, expected_revision, candidate, context, interrupt=False):
    headers, records, directory = context
    with publication_lock(active):
        pointer = json.loads(active.read_text(encoding="utf-8"))
        if (pointer["scope"], pointer.get("revision", 0)) != (expected, expected_revision):
            return "stale_pointer"
        verify_manifest(candidate, records, headers)
        if interrupt:
            os._exit(77)
        if candidate == expected:
            return "already_active"
        switch_index(
            active, candidate, headers, records, directory,
            revision=expected_revision + 1, rollback_scope=expected,
        )
    return "published"


def exercise(candidate, context):
    headers, records, directory = context
    old = current_scope(ACTIVE)
    assert old != candidate
    results = {}
    with tempfile.TemporaryDirectory(dir=RUNTIME, prefix="release-race-") as tmp:
        active = Path(tmp) / ACTIVE.name
        switch_index(active, old, headers, records, directory, revision=0)
        baseline = active.read_bytes()
        try:
            publish(active, old, 0, candidate + "-missing", context)
        except HTTPError as error:
            assert error.code == 404 and active.read_bytes() == baseline
            results["invalid_candidate"] = {"http_status": error.code, "scope": old}
        else:
            raise AssertionError("Missing scope was accepted")
        worker = [sys.executable, "-B", __file__, candidate, "--worker", str(active), old, "0"]
        interrupted = subprocess.run(worker + ["--interrupt"], timeout=45)
        assert interrupted.returncode == 77 and active.read_bytes() == baseline
        results["interrupted_before_commit"] = {"exit_code": interrupted.returncode, "scope": old}

        processes = [
            subprocess.Popen(worker, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            for _ in range(2)
        ]
        outcomes = []
        try:
            for process in processes:
                output, error = process.communicate(timeout=45)
                assert process.returncode == 0, error
                outcomes.append(output.strip())
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.wait()
        assert sorted(outcomes) == ["published", "stale_pointer"], outcomes
        assert json.loads(active.read_text(encoding="utf-8")) == {"scope": candidate, "revision": 1, "rollback_scope": old}
        result = query(CASES[1][1], current_scope(active), headers, records, directory)
        assert result["result"] == ("revoked", None, "APPROVAL-028")
        assert result["hit_source_uri"].startswith(candidate + "/")
        results["competing_publishers"] = {"outcomes": outcomes, "query": result}

        assert publish(active, candidate, 1, old, context) == "published"
        assert json.loads(active.read_text(encoding="utf-8")) == {"scope": old, "revision": 2, "rollback_scope": candidate}
        results["rollback"] = {"scope": old, "revision": 2, "rollback_scope": candidate}
        late = subprocess.run(worker, capture_output=True, text=True, timeout=45, check=True)
        assert late.stdout.strip() == "stale_pointer"
        assert json.loads(active.read_text(encoding="utf-8")) == {"scope": old, "revision": 2, "rollback_scope": candidate}
        results["stale_after_return_to_same_scope"] = {
            "outcome": late.stdout.strip(), "expected_revision": 0, "current_revision": 2,
        }
        assert publish(active, old, 2, candidate, context) == "published"
        assert json.loads(active.read_text(encoding="utf-8")) == {"scope": candidate, "revision": 3, "rollback_scope": old}
        results["fresh_publish_after_rollback"] = {"scope": candidate, "revision": 3, "rollback_scope": old}
    assert current_scope(ACTIVE) == old
    output = RUNTIME / f"approval-release-races-{time.strftime('%Y%m%d-%H%M%S')}.json"
    with output.open("x", encoding="utf-8") as stream:
        json.dump(results, stream, indent=2)
    print(output)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate")
    parser.add_argument("--worker", nargs=3, metavar=("POINTER", "EXPECTED", "REVISION"))
    parser.add_argument("--interrupt", action="store_true")
    args = parser.parse_args()
    context = load_context()
    if args.worker:
        pointer, expected, revision = args.worker
        path = Path(pointer).resolve()
        if path.parent.parent != RUNTIME.resolve() or not path.parent.name.startswith("release-race-"):
            parser.error("worker pointer must be inside an isolated release-race directory")
        print(publish(path, expected, int(revision), args.candidate, context, args.interrupt))
    else:
        exercise(args.candidate, context)


if __name__ == "__main__":
    main()
