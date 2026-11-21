"""Run an ARG handoff with deterministic prerequisites and a model proposal."""
import json
import os
import time

from exercise_handoff_agent import QUERY, RUNTIME, guard, load_context, next_action, preflight, verify

WORKSPACE = RUNTIME / "handoff-recovery-e2575b25643e"
MODES = ("ov_available", "ov_unreachable_local_present", "ov_unreachable_local_missing")


def guided(root, config):
    trace = []
    # Mandatory ARG order is executed by the harness, not selected by the model.
    local = preflight(root)
    if local["status"] != "local_context_ready":
        return {"status": local["status"], "missing": local["missing"]}
    for name in local["local_required"]:
        (root / name).read_text(encoding="utf-8-sig")
        trace.append({"tool": "read", "file": name})
    historical = preflight(root, QUERY, config)["historical_evidence"]
    trace.append({"tool": "preflight", "status": historical["status"]})
    evidence = historical["evidence"]
    if not evidence:
        entry = config["sources"]["ROLLBACK"]
        path = (root / entry["path"]).resolve()
        if path.is_relative_to(root) and path.is_file():
            match = verify(root, entry, path.read_text(encoding="utf-8-sig"))
            if match:
                evidence = [match]
        trace.append({"tool": "read_registered_local_evidence", "found": bool(evidence)})

    raw = next_action([
        {"role": "system", "content": (
            "Submit the finish tool. Copy task_id and status exactly from canonical_task. "
            "If verified evidence gives a revision, use VERIFY_COMPLETE and that integer. "
            "If verified_evidence is empty, use HOLD and revision null. Do not change the status."
        )},
        {"role": "user", "content": json.dumps({
            "canonical_task": {"task_id": local["task_id"], "status": local["task_status"]},
            "verified_evidence": evidence,
        })},
    ])
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {}
    proposal = {key: value for key, value in parsed.items() if key != "tool"} if parsed.get("tool") == "finish" else None
    checked = guard(root, evidence, proposal)
    return {"trace": trace, "proposal": proposal, "raw": raw, "guarded": checked}


def main():
    headers, _, _ = load_context()
    os.environ["ARG_OV_API_KEY"] = headers["X-API-Key"]
    expected = json.loads((WORKSPACE / "report.json").read_text(encoding="utf-8"))
    expected_by_mode = {row["mode"]: row["expected_answer"] for row in expected["rows"]}
    rows = []
    for mode in MODES:
        root = (WORKSPACE / mode).resolve()
        before = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
        result = guided(root, json.loads((root / "ov-lookup.json").read_text(encoding="utf-8")))
        assert result["guarded"]["decision"] == expected_by_mode[mode], result
        assert before == {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
        rows.append({"mode": mode, **result, "files_unchanged": True})
        print(mode, result["guarded"]["model_proposal_accepted"], result["guarded"]["decision"], flush=True)
    output = WORKSPACE / f"guided-agent-{time.strftime('%Y%m%d-%H%M%S')}.json"
    with output.open("x", encoding="utf-8") as stream:
        json.dump({"rows": rows}, stream, indent=2)
    print(output)


if __name__ == "__main__":
    main()
