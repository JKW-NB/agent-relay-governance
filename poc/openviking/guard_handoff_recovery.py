"""Read-only guard for the rollback-verification handoff rehearsal."""
import importlib.util
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("arg_validator", REPO / "scripts/validate_governance.py")
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)
REVISION = re.compile(r"The historical rollback verification finished at pointer revision (\d+)\.")


def guard(root, verified, model_proposal):
    state = VALIDATOR.parse_yaml_subset((root / "CURRENT_STATE.yaml").read_text(encoding="utf-8-sig"))
    task = state["current"]["task"]
    if task["id"] != "T-01-01" or task["status"] != "PAUSED":
        return {"status": "unsupported_handoff", "task_id": task["id"], "current_status": task["status"]}
    matches = {}
    for item in verified:
        match = REVISION.fullmatch(item["quote"].strip())
        if match:
            matches.setdefault(int(match[1]), []).append(item)
    if len(matches) == 1:
        revision, sources = next(iter(matches.items()))
        decision = {"task_id": task["id"], "status": task["status"], "action": "VERIFY_COMPLETE",
                    "revision": revision}
        reason = "verified_revision"
    else:
        decision = {"task_id": task["id"], "status": task["status"], "action": "HOLD", "revision": None}
        sources = []
        reason = "conflicting_revisions" if matches else "missing_verified_revision"
    return {"decision": decision, "reason": reason, "sources": sources,
            "model_proposal_accepted": model_proposal == decision}
