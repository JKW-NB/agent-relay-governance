"""Rehearse a paused ARG handoff with real project evidence in fresh model calls."""
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from evaluate import generate, request
from guard_handoff_recovery import guard
from exercise_index_release import upload
from query_approval import HERE, RUNTIME, load_context

REPO = HERE.parents[1]
MODEL = "qwen2.5:1.5b"
SOURCE = "rollback-protection-20261108-102939.json"
QUERY = "What revision was recorded after the active index rollback?"
TASK = "T-01-01"
FILES = {
    "AGENTS.md": "# Pilot instructions\nRead CURRENT_STATE first, then CHECKPOINT and PROJECT_LOG. Read verified history if needed. Keep all governance files read-only.\n",
    "CHECKPOINT.md": "# Resume package\n状态: PAUSED\nResume task T-01-01. Confirm the recorded rollback revision before starting release review.\n",
    "PROJECT_LOG.md": "# Event history\nThe release review was paused pending verification of the historical rollback revision. No release approval is recorded.\n",
}
STATE = """schema_version: 2
project: "ARG OpenViking handoff rehearsal"
last_updated: "{today}"
current:
  workstream: "POC"
  stage: "01"
  task:
    id: "T-01-01"
    goal: "Verify prior rollback revision before starting release review"
    role: "AUDITOR"
    status: "PAUSED"
    depends_on: []
    inputs: ["PROJECT_LOG.md"]
    outputs: []
    exact_next_action: "Find the recorded rollback revision. If there is no verified source, report HOLD and request evidence."
context:
  required: ["PROJECT_LOG.md"]
  conditional:
    - when: "status in [PAUSED, HOLD]"
      load: ["CHECKPOINT.md"]
  do_not_preload: []
"""
QUESTION = "What is the task, its current status, the proposed next action, and the verified rollback revision?"
RULES = (
    "Read CURRENT_STATE for task and status. Use rollback.md for the revision if provided. "
    "If it is present, propose VERIFY_COMPLETE; otherwise propose HOLD and set revision to null. "
    "Do not change the current status or claim release approval."
)
SCHEMA = {
    "type": "object",
    "properties": {
        "task_id": {"type": "string"}, "status": {"type": "string"},
        "action": {"type": "string", "enum": ["VERIFY_COMPLETE", "HOLD"]},
        "revision": {"type": ["integer", "null"]},
    },
    "required": ["task_id", "status", "action", "revision"],
}

def execute(script, *args, env=None):
    output = subprocess.run(
        [sys.executable, "-B", str(script), *args], env=env, capture_output=True,
        encoding="utf-8", timeout=45,
    )
    if output.returncode:
        raise RuntimeError(output.stdout + output.stderr)
    return output.stdout


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    headers, _, _ = load_context()
    actual = RUNTIME / SOURCE
    source_hash = sha(actual)
    revision = json.loads(actual.read_text(encoding="utf-8-sig"))["restored"]["revision"]
    evidence_text = f"The historical rollback verification finished at pointer revision {revision}."
    tag = uuid.uuid4().hex[:12]
    scope = f"viking://resources/arg-handoff-{tag}"
    request("/fs/mkdir", headers, {"uri": scope})
    upload({"id": "ROLLBACK", "text": evidence_text}, scope, headers)
    workspace = RUNTIME / f"handoff-recovery-{tag}"
    workspace.mkdir()
    rows = []
    for mode, url, include_local in (
        ("ov_available", "http://127.0.0.1:1933", True),
        ("ov_unreachable_local_present", "http://127.0.0.1:1", True),
        ("ov_unreachable_local_missing", "http://127.0.0.1:1", False),
    ):
        root = workspace / mode
        root.mkdir()
        files = {**FILES, "CURRENT_STATE.yaml": STATE.format(today=time.strftime("%Y-%m-%d %H:%M"))}
        for name, text in files.items():
            (root / name).write_text(text, encoding="utf-8")
        if include_local:
            (root / "rollback.md").write_bytes((evidence_text + "\n").encode("utf-8"))
        entry = {"path": "rollback.md", "sha256": hashlib.sha256((evidence_text + "\n").encode()).hexdigest()}
        cfg = {"enabled": True, "url": url, "scope": scope, "account": "arg-poc", "user": "evaluator",
               "sources": {"ROLLBACK": entry}}
        (root / "ov-lookup.json").write_text(json.dumps(cfg), encoding="utf-8")
        before = {name: sha(root / name) for name in files}
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "ARG_OV_API_KEY": headers["X-API-Key"]}
        validator = execute(REPO / "scripts/validate_governance.py", "-p", str(root), env=env)
        result = json.loads(execute(
            REPO / "integrations/openviking/retrieve.py", "--project-root", str(root),
            "--config", str(root / "ov-lookup.json"), QUERY, env=env,
        ))
        wanted = "verified_evidence" if mode == "ov_available" else "unavailable_use_local"
        assert result["status"] == wanted, result
        context = [(name, (root / name).read_text(encoding="utf-8")) for name in
                   ("AGENTS.md", "CURRENT_STATE.yaml", "CHECKPOINT.md", "PROJECT_LOG.md")]
        verified = result["evidence"]
        if not verified and include_local:
            local_file = root / entry["path"]
            if sha(local_file) == entry["sha256"]:
                verified = [{"path": entry["path"], "sha256": entry["sha256"], "line": 1,
                             "quote": local_file.read_text(encoding="utf-8").strip()}]
        if result["evidence"]:
            context.extend((item["path"], item["quote"]) for item in result["evidence"])
        elif include_local:
            context.append(("rollback.md", (root / "rollback.md").read_text(encoding="utf-8")))
        start = time.perf_counter()
        raw = generate(QUESTION, context, 60, True, model=MODEL, schema=SCHEMA, instructions=RULES)
        try:
            answer = json.loads(raw["response"])
        except json.JSONDecodeError:
            answer = None
        assert before == {name: sha(root / name) for name in files}
        expected = {"task_id": TASK, "status": "PAUSED",
                    "action": "VERIFY_COMPLETE" if include_local else "HOLD",
                    "revision": revision if include_local else None}
        guarded = guard(root, verified, answer)
        assert guarded["decision"] == expected, (mode, guarded)
        assert before == {name: sha(root / name) for name in files}
        rows.append({"mode": mode, "adapter_status": result["status"], "validator": validator,
                     "guarded": guarded,
                     "expected_answer": expected, "answer": answer, "raw": raw["response"],
                     "evidence_files": [name for name, _ in context], "governance_unchanged": True,
                     "elapsed_ms": round((time.perf_counter() - start) * 1000, 2)})
        print(mode, result["status"], ascii(answer if answer is not None else raw["response"]), flush=True)
    guarded_cases = []
    root = workspace / "ov_available"
    bad = {"path": "rollback.md", "quote": "Unverified claim: revision 99."}
    assert guard(root, [bad], None)["reason"] == "missing_verified_revision"
    guarded_cases.append("unexpected evidence format")
    competing = [
        {"path": "rollback.md", "quote": evidence_text},
        {"path": "different.md", "quote": f"The historical rollback verification finished at pointer revision {revision + 1}."},
    ]
    assert guard(root, competing, None)["reason"] == "conflicting_revisions"
    guarded_cases.append("competing verified revisions")
    assert sha(actual) == source_hash
    output = workspace / "report.json"
    with output.open("x", encoding="utf-8") as stream:
        json.dump({"scope": scope, "model": MODEL, "source_report": SOURCE, "source_sha256": source_hash,
                   "rows": rows, "guard_negative_checks": guarded_cases}, stream, indent=2)
    print(output)


if __name__ == "__main__":
    main()
