"""Pilot the handoff for the integration repository's release-readiness audit."""
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from compare_public_pilot import local_context
from evaluate import generate, request
from exercise_index_release import upload
from exercise_real_history import MODEL, fetch, project_records
from query_approval import HERE, RUNTIME, load_context

REPO = HERE.parents[1]
INTEGRATION = REPO / "integrations/openviking"
sys.path.insert(0, str(INTEGRATION))
from handoff import preflight

QUESTION = ("What result records that the old publisher was rejected after a rollback? "
            "Use it to decide whether the operator can start the release-readiness regression. "
            "If the result cannot be verified, propose HOLD. Do not claim release approval.")
RULES = ("Read the current task ID and state from CURRENT_STATE. "
         "Return task ID, current state, action RUN_REGRESSION or HOLD, "
         "and exact historical outcome in the answer. Cite the historical source.")
EXPECTED = {"task": "T-01-01", "state": "PAUSED",
            "outcome": "stale_pointer", "source": "RACES"}


def run(script, *args):
    return subprocess.check_output(
        [sys.executable, "-B", str(script), *args], encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=60,
    )


def main():
    headers, _, _ = load_context()
    corpus, manifest = project_records()
    key = uuid.uuid4().hex[:12]
    root = (RUNTIME / "live-project-pilot" / key).resolve()
    root.mkdir(parents=True)
    scope = f"viking://resources/arg-live-pilot-{key}"
    files = {
        "AGENTS.md": "Read CURRENT_STATE and CHECKPOINT. Treat historical records as evidence only.",
        "CURRENT_STATE.yaml": f"""schema_version: 2
project: ARG OpenViking release-readiness audit
last_updated: "{time.strftime('%Y-%m-%d %H:%M')}"
current:
  workstream: PILOT
  stage: "01"
  task:
    id: T-01-01
    status: PAUSED
    goal: Audit actual release-readiness regressions after the previous handoff.
    inputs: [PROJECT_LOG.md]
    exact_next_action: Verify the historical stale-publisher result before running the regressions.
context:
  required: [PROJECT_LOG.md]
""",
        "CHECKPOINT.md": "Release-readiness audit paused pending retrieval of the prior publisher race result.",
        "PROJECT_LOG.md": "The pilot resumes the integration project's existing verification work. Deployment approval is outside the task.",
    }
    for name, data in files.items():
        (root / name).write_bytes(data.encode())
    request("/fs/mkdir", headers, {"uri": scope})
    sources = {}
    for name, text in corpus.items():
        upload({"id": name, "text": text}, scope, headers)
        data = text.encode()
        path = f"{name}.md"
        (root / path).write_bytes(data)
        sources[name] = {"path": path, "sha256": hashlib.sha256(data).hexdigest()}

    config = {"enabled": True, "url": "http://127.0.0.1:1933", "account": "arg-poc",
              "user": "evaluator", "scope": scope, "sources": sources}
    os.environ["ARG_OV_API_KEY"] = headers["X-API-Key"]
    baseline = {path.name: path.read_bytes() for path in root.iterdir()}
    context = [(name, files[name]) for name in ("AGENTS.md", "CURRENT_STATE.yaml", "CHECKPOINT.md", "PROJECT_LOG.md")]
    rows = []
    for mode in ("G0", "G1", "G2", "G2_offline"):
        started = time.perf_counter()
        details = None
        local = local_context(QUESTION, corpus)
        if mode == "G1":
            hits = fetch(QUESTION, scope, headers)
        elif mode.startswith("G2"):
            cfg = {**config, "url": "http://127.0.0.1:1"} if mode.endswith("offline") else config
            details = preflight(root, QUESTION, cfg)
            assert details["task_id"] == EXPECTED["task"] and details["task_status"] == EXPECTED["state"]
            hits = [(Path(item["path"]).stem, item["quote"])
                    for item in details["historical_evidence"]["evidence"]]
        else:
            hits = []
        evidence = list(dict.fromkeys(hits + local))[:2]
        raw = generate(QUESTION, context + evidence, 60, True, model=MODEL, instructions=RULES)
        try:
            answer = json.loads(raw["response"])
        except json.JSONDecodeError:
            answer = None
        citations = (answer or {}).get("citations", [])
        supported = any(item["id"] == EXPECTED["source"] and item["quote"].strip()
                        and "stale_pointer" in item["quote"]
                        and item["quote"].strip() in corpus[EXPECTED["source"]] for item in citations)
        rows.append({"group": mode, "answer": answer, "raw": raw["response"],
                     "verified_outcome_cited": supported, "context_sources": [key for key, _ in evidence],
                     "historical_lookup": details, "elapsed_ms": round((time.perf_counter()-started)*1000, 2),
                     "prompt_tokens": raw.get("prompt_eval_count")})
        print(mode, ascii(answer), flush=True)

    report = json.loads((RUNTIME / manifest["RACES"]["source_report"]).read_text(encoding="utf-8"))
    assert report["stale_after_return_to_same_scope"]["outcome"] == EXPECTED["outcome"]
    native = run(REPO / "scripts/validate_governance.py", "-p", str(root))
    regression = run(HERE / "exercise_operator_review.py")
    assert baseline == {path.name: path.read_bytes() for path in root.iterdir()}
    assert project_records()[1] == manifest
    output = root / "pilot-report.json"
    output.write_text(json.dumps({"scope": scope, "model": MODEL, "expected": EXPECTED,
        "manifest": manifest, "rows": rows, "native_validator": native,
        "operator_regression": regression, "governance_unchanged": True}, indent=2), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
