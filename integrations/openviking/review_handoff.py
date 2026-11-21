"""Review an untrusted agent proposal against operator-supplied inputs."""
import argparse
import json
from pathlib import Path

from verify_handoff import verify_policy

FIELDS = {"task_id", "task_status", "proposed_action"}
EXIT_CODES = {"accepted_verification_proposal": 0, "accepted_hold_proposal": 3, "rejected": 1}


def review(root, policy_path, pin, proposal):
    verified = verify_policy(root, policy_path, pin)
    if not isinstance(proposal, dict) or set(proposal) != FIELDS:
        return {"status": "rejected", "reason": "unexpected_proposal_fields", "verified": verified}
    if not FIELDS <= verified.keys():
        return {"status": "rejected", "reason": "canonical_context_unverified", "verified": verified}
    expected = {key: verified[key] for key in FIELDS}
    if proposal != expected:
        return {"status": "rejected", "reason": "proposal_differs", "verified": verified}
    status = "accepted_verification_proposal" if expected["proposed_action"] == "VERIFY_COMPLETE" else "accepted_hold_proposal"
    return {"status": status, "verified": verified}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--policy-sha256", required=True)
    parser.add_argument("--proposal", type=Path, required=True)
    args = parser.parse_args()
    try:
        data = args.proposal.read_bytes()
        if len(data) > 4096:
            raise ValueError("Proposal exceeds the accepted size")
        proposal = json.loads(data.decode("utf-8-sig"))
        result = review(args.project_root.resolve(), args.policy, args.policy_sha256, proposal)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        result = {"status": "rejected", "reason": "invalid_input"}
    print(json.dumps(result, indent=2))
    return EXIT_CODES[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
