"""Validate declared handoff evidence against an operator-pinned policy."""
import argparse
import hashlib
import hmac
import json
import re
from pathlib import Path

from handoff import preflight



def digest(data):
    return hashlib.sha256(data).hexdigest()


def check(root, contract):
    local = preflight(root)
    result = {key: local.get(key) for key in ("task_id", "task_status")}
    result["proposed_action"] = "HOLD"
    if local["status"] != "local_context_ready":
        return {**result, "reason": "required_context_missing", "missing": local["missing"]}
    if local["task_id"] != contract["task_id"] or local["task_status"] not in {"READY", "PAUSED"}:
        return {**result, "reason": "contract_does_not_apply"}
    source = (root / contract["path"]).resolve()
    if not source.is_relative_to(root) or not source.is_file():
        return {**result, "reason": "approved_report_missing"}
    data = source.read_bytes()
    if digest(data) != contract["sha256"]:
        return {**result, "reason": "report_hash_mismatch"}
    try:
        actual = json.loads(data.decode("utf-8-sig"))
        for segment in contract["field"]:
            if not isinstance(actual, dict):
                raise TypeError("Expected a JSON object")
            actual = actual[segment]
    except (ValueError, TypeError, KeyError):
        return {**result, "reason": "report_field_unavailable"}
    expected = contract["expected"]
    if type(actual) is not type(expected) or actual != expected:
        return {**result, "reason": "criterion_not_met"}
    return {**result, "proposed_action": "VERIFY_COMPLETE", "reason": "criterion_verified",
            "evidence": {"path": source.relative_to(root).as_posix(),
                         "sha256": contract["sha256"], "field": contract["field"], "value": actual}}


def verify_policy(root, policy_path, policy_sha256):
    if not re.fullmatch(r"[a-fA-F0-9]{64}", policy_sha256):
        return {"proposed_action": "HOLD", "reason": "invalid_policy_pin"}
    try:
        raw = policy_path.read_bytes()
    except OSError:
        return {"proposed_action": "HOLD", "reason": "policy_unavailable"}
    if not hmac.compare_digest(digest(raw), policy_sha256.lower()):
        return {"proposed_action": "HOLD", "reason": "policy_hash_mismatch"}
    policy = json.loads(raw.decode("utf-8-sig"))
    if policy["project_root"] != root.as_posix():
        return {"proposed_action": "HOLD", "reason": "policy_project_mismatch"}
    local = preflight(root)
    if local["status"] != "local_context_ready":
        return {"proposed_action": "HOLD", "reason": "required_context_missing",
                "missing": local["missing"]}
    task_id = local["task_id"]
    contract = policy["tasks"].get(task_id)
    if contract is None:
        return {"proposed_action": "HOLD", "reason": "no_approved_task_contract",
                "task_id": task_id, "task_status": local["task_status"]}
    return {**check(root, {**contract, "task_id": task_id}), "policy_sha256": digest(raw)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--policy-sha256", required=True)
    args = parser.parse_args()
    try:
        result = verify_policy(args.project_root.resolve(), args.policy, args.policy_sha256)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        result = {"proposed_action": "HOLD", "reason": "invalid_policy_or_local_state"}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
