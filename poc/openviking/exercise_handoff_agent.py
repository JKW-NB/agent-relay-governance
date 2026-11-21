"""Let a local model choose read-only tools during an isolated ARG handoff."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from evaluate import DOCKER
from guard_handoff_recovery import guard
from query_approval import HERE, RUNTIME, load_context

REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "integrations/openviking"))
from handoff import preflight
from retrieve import verify

MODEL = "qwen2.5:1.5b"
QUERY = "What revision was recorded after the active index rollback?"
CORE = {"AGENTS.md", "CURRENT_STATE.yaml", "CHECKPOINT.md", "PROJECT_LOG.md"}
ACTIONS = {
    "preflight": "Read canonical current task and report optional verified history lookup.",
    "read": "Read one approved project file by exact name.",
    "finish": "Submit task_id, status, action (VERIFY_COMPLETE or HOLD) and revision (integer or null).",
}
ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "tool": {"type": "string", "enum": list(ACTIONS)},
        "file": {"type": "string"},
        "task_id": {"type": "string"}, "status": {"type": "string"},
        "action": {"type": "string", "enum": ["VERIFY_COMPLETE", "HOLD"]},
        "revision": {"type": ["integer", "null"]},
    },
    "required": ["tool"],
}


def next_action(messages):
    body = {"model": MODEL, "messages": messages, "format": ACTION_SCHEMA,
            "stream": False, "options": {"temperature": 0, "seed": 42, "num_predict": 160}}
    bridge = (
        "import sys,urllib.request; "
        "r=urllib.request.Request('http://arg-ollama:11434/api/chat', "
        "data=sys.stdin.buffer.read(), headers={'Content-Type':'application/json'}); "
        "sys.stdout.buffer.write(urllib.request.urlopen(r,timeout=50).read())"
    )
    result = subprocess.run(
        [str(DOCKER), "exec", "-i", "arg-openviking", "python", "-c", bridge],
        input=json.dumps(body), encoding="utf-8", capture_output=True, check=True, timeout=55,
    )
    return json.loads(result.stdout)["message"]["content"]


def run_agent(root, cfg):
    messages = [
        {"role": "system", "content": (
            "You are a new ARG handoff agent. Choose one tool per turn as JSON. Tools: "
            + json.dumps(ACTIONS)
            + " Read AGENTS.md and CURRENT_STATE.yaml first, then required context. "
              "Use preflight for historical lookup; if unavailable, try reading rollback.md. "
              "Keep the exact current status and only propose the next action. "
              "Propose HOLD with null revision if evidence is missing. "
              "When done submit finish with task_id, status, action and revision."
        )},
        {"role": "user", "content": "Resume the paused verification task."},
    ]
    trace = []
    verified = []
    proposal = None
    seen_files = set()
    for _ in range(8):
        raw = next_action(messages)
        try:
            action = json.loads(raw)
        except json.JSONDecodeError:
            trace.append({"raw": raw, "error": "invalid_json"})
            break
        tool = action.get("tool")
        if tool == "finish":
            proposal = {key: value for key, value in action.items() if key != "tool"}
            trace.append({"request": action})
            break
        if tool == "preflight" and {"AGENTS.md", "CURRENT_STATE.yaml"} <= seen_files:
            result = preflight(root, QUERY, cfg)
            verified.extend(result.get("historical_evidence", {}).get("evidence", []))
        elif tool == "read" and action.get("file") in CORE | {"rollback.md"}:
            name = action["file"]
            if name not in {"AGENTS.md", "CURRENT_STATE.yaml"} and not {"AGENTS.md", "CURRENT_STATE.yaml"} <= seen_files:
                result = {"error": "read AGENTS.md and CURRENT_STATE.yaml first"}
            elif not (root / name).is_file():
                result = {"error": "file_missing", "file": name}
            else:
                text = (root / name).read_text(encoding="utf-8")
                if name == "rollback.md":
                    evidence = verify(root, cfg["sources"]["ROLLBACK"], text)
                    if evidence:
                        verified.append(evidence)
                seen_files.add(name)
                result = {"file": name, "text": text}
        else:
            result = {"error": "tool or file unavailable at this step"}
        trace.append({"request": action, "result": result})
        messages.extend([{"role": "assistant", "content": raw},
                         {"role": "user", "content": "Tool result: " + json.dumps(result)}])
    validated = guard(root, verified, proposal)
    required_read = CORE <= seen_files
    return {"trace": trace, "proposal": proposal, "all_core_files_read": required_read,
            "proposal_accepted": required_read and validated["model_proposal_accepted"],
            "guarded": validated}


def main():
    headers, _, _ = load_context()
    os.environ["ARG_OV_API_KEY"] = headers["X-API-Key"]
    workspace = RUNTIME / "handoff-recovery-e2575b25643e"
    rows = []
    for mode in ("ov_available", "ov_unreachable_local_present", "ov_unreachable_local_missing"):
        root = (workspace / mode).resolve()
        before = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
        cfg = json.loads((root / "ov-lookup.json").read_text(encoding="utf-8"))
        result = run_agent(root, cfg)
        assert before == {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
        rows.append({"mode": mode, **result, "files_unchanged": True})
        print(mode, len(result["trace"]), result["proposal_accepted"],
              result["guarded"]["reason"], flush=True)
    output = workspace / f"tool-agent-{time.strftime('%Y%m%d-%H%M%S')}.json"
    with output.open("x", encoding="utf-8") as stream:
        json.dump({"model": MODEL, "rows": rows}, stream, indent=2)
    print(output)


if __name__ == "__main__":
    main()
