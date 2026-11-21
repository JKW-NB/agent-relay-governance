"""Operator entry point for a reviewed, read-only ARG handoff validation."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from review_handoff import EXIT_CODES, review

VALIDATOR = Path(__file__).resolve().parents[2] / "scripts/validate_governance.py"


def state_digest(root):
    path = (root / "CURRENT_STATE.yaml").resolve()
    if not path.is_relative_to(root):
        raise ValueError("State is outside the project")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dispatch(root, policy, pin, proposal):
    before = state_digest(root)
    checked = review(root, policy, pin, proposal)
    if checked["status"] != "accepted_verification_proposal":
        return {**checked, "validator_ran": False}
    if state_digest(root) != before or review(root, policy, pin, proposal) != checked:
        return {"status": "rejected", "reason": "inputs_changed_before_validation", "validator_ran": False}
    completed = subprocess.run(
        [sys.executable, "-B", str(VALIDATOR), "-p", str(root)],
        capture_output=True, encoding="utf-8", timeout=30,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    if completed.returncode:
        return {"status": "rejected", "reason": "native_validator_failed", "validator_ran": True,
                "validator_exit_code": completed.returncode, "validator_output": completed.stdout}
    if state_digest(root) != before or review(root, policy, pin, proposal) != checked:
        return {"status": "rejected", "reason": "inputs_changed_during_validation", "validator_ran": True}
    return {**checked, "validator_ran": True, "validator_exit_code": 0,
            "state_sha256": before, "validator_output": completed.stdout}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--policy-sha256", required=True)
    parser.add_argument("--proposal", required=True, type=Path)
    args = parser.parse_args()
    try:
        with args.proposal.open("rb") as stream:
            data = stream.read(4097)
        if len(data) > 4096:
            raise ValueError("Proposal exceeds the accepted size")
        result = dispatch(args.project_root.resolve(), args.policy, args.policy_sha256,
                          json.loads(data.decode("utf-8-sig")))
    except (OSError, ValueError, TypeError, KeyError, AttributeError, subprocess.TimeoutExpired):
        result = {"status": "rejected", "reason": "invalid_or_unavailable_input"}
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return EXIT_CODES[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
