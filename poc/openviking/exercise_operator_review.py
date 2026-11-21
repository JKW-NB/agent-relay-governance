"""Exercise the operator CLI with untrusted proposal files."""
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from query_approval import HERE, RUNTIME

REVIEW = HERE.parents[1] / "integrations/openviking/review_handoff.py"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    fixture = RUNTIME / "handoff-recovery-e2575b25643e/ov_available"
    rows = []
    with tempfile.TemporaryDirectory(dir=RUNTIME, prefix="operator-review-") as staging:
        root = Path(staging).resolve()
        core = {name: (fixture / name).read_bytes()
                for name in ("AGENTS.md", "CURRENT_STATE.yaml", "CHECKPOINT.md", "PROJECT_LOG.md")}
        for name, data in core.items():
            (root / name).write_bytes(data)
        report = root / "rollback.json"
        original = (RUNTIME / "rollback-protection-20261108-102939.json").read_bytes()
        report.write_bytes(original)
        policy = root / "policy.json"
        proposal = root / "proposal.json"
        policy.write_text(json.dumps({"project_root": root.as_posix(), "tasks": {
            "T-01-01": {"path": report.name, "sha256": digest(original),
                        "field": ["restored", "revision"], "expected": 4},
        }}), encoding="utf-8")
        pin = digest(policy.read_bytes())
        command = [sys.executable, "-B", str(REVIEW), "--project-root", str(root),
                   "--policy", str(policy), "--policy-sha256", pin, "--proposal", str(proposal)]
        valid = {"task_id": "T-01-01", "task_status": "PAUSED", "proposed_action": "VERIFY_COMPLETE"}

        def run(case, content, status, reason=None):
            proposal.write_text(json.dumps(content), encoding="utf-8")
            completed = subprocess.run(command, encoding="utf-8", capture_output=True, timeout=15)
            result = json.loads(completed.stdout)
            assert result["status"] == status and result.get("reason") == reason, (case, result)
            expected_code = {"accepted_verification_proposal": 0, "accepted_hold_proposal": 3, "rejected": 1}[status]
            assert completed.returncode == expected_code, (case, completed.returncode)
            # A host action can only run on code 0. Use a harmless marker in this rehearsal.
            marker = root / "host-advanced"
            if completed.returncode == 0:
                marker.write_text(case, encoding="utf-8")
            host_advanced = marker.is_file()
            assert host_advanced == (status == "accepted_verification_proposal")
            if host_advanced:
                marker.unlink()
            rows.append({"case": case, "result": result,
                         "exit_code": completed.returncode, "host_advanced": host_advanced})

        run("valid", valid, "accepted_verification_proposal")
        run("override pin", {**valid, "policy_sha256": "0" * 64}, "rejected", "unexpected_proposal_fields")
        run("override path", {**valid, "policy": "other.json"}, "rejected", "unexpected_proposal_fields")
        run("status override", {**valid, "task_status": "PASS"}, "rejected", "proposal_differs")
        run("propose PASS", {**valid, "proposed_action": "PASS"}, "rejected", "proposal_differs")
        run("wrong task", {**valid, "task_id": "T-01-02"}, "rejected", "proposal_differs")
        report.write_bytes(b'{"restored":{"revision":99}}')
        run("tampered report", valid, "rejected", "proposal_differs")
        run("hold on tampering", {**valid, "proposed_action": "HOLD"}, "accepted_hold_proposal")
        guided = json.loads((fixture.parent / "guided-agent-20261110-153647.json").read_text(encoding="utf-8"))
        for row in guided["rows"]:
            mode = row["mode"]
            has_evidence = mode != "ov_unreachable_local_missing"
            if has_evidence:
                report.write_bytes(original)
            else:
                report.unlink(missing_ok=True)
            model = row["proposal"]
            model_input = {
                "task_id": model.get("task_id"),
                "task_status": model.get("status"),
                "proposed_action": model.get("action", model.get("status")),
            }
            run(f"{mode}: model proposal", model_input, "rejected", "proposal_differs")
            verified = row["guarded"]["decision"]
            checked = {"task_id": verified["task_id"], "task_status": verified["status"],
                       "proposed_action": verified["action"]}
            run(f"{mode}: guarded proposal", checked,
                "accepted_verification_proposal" if has_evidence else "accepted_hold_proposal")
        proposal.write_text("{invalid", encoding="utf-8")
        malformed = subprocess.run(command, encoding="utf-8", capture_output=True, timeout=15)
        assert malformed.returncode == 1 and json.loads(malformed.stdout)["reason"] == "invalid_input"
        rows.append({"case": "malformed proposal", "exit_code": malformed.returncode, "host_advanced": False})
        assert core == {name: (root / name).read_bytes() for name in core}
        assert pin == digest(policy.read_bytes())
    output = RUNTIME / f"operator-handoff-review-{time.strftime('%Y%m%d-%H%M%S')}.json"
    with output.open("x", encoding="utf-8") as stream:
        json.dump({"rows": rows, "governance_unchanged": True}, stream, indent=2)
    print(f"{len(rows)} operator review checks passed")
    print(output)


if __name__ == "__main__":
    main()
