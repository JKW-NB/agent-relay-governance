"""Check that the native ARG validator stays independent of the OV sidecar."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from evaluate_natural_approvals import CASES
from query_approval import ACTIVE, HERE, RUNTIME, lease, load_context, query_with_service_status

STATE = """schema_version: 2
project: "Synthetic approval pilot"
last_updated: "{today}"
current:
  workstream: "G1"
  stage: "01"
  task:
    id: "T-01-01"
    goal: "Verify archive approval evidence"
    role: "AUDITOR"
    status: "READY"
    depends_on: []
    inputs: ["PROJECT_LOG.md"]
    outputs: []
context:
  required: ["PROJECT_LOG.md"]
  conditional: []
  do_not_preload: []
"""


def digest(root):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir() if p.is_file()}


def main():
    question = CASES[1][1]
    context = load_context()
    checks = []
    with tempfile.TemporaryDirectory(dir=RUNTIME, prefix="pilot-") as folder:
        root = Path(folder)
        (root / "CURRENT_STATE.yaml").write_text(
            STATE.format(today=time.strftime("%Y-%m-%d %H:%M")), encoding="utf-8",
        )
        (root / "PROJECT_LOG.md").write_text("# Synthetic pilot event history\n", encoding="utf-8")
        before = digest(root)
        validator = HERE.parents[1] / "scripts" / "validate_governance.py"
        with lease(ACTIVE) as scope:
            healthy = query_with_service_status(question, scope, *context)
            assert healthy["status"] == "revoked", healthy
            checks.append({"case": "live OV query", "status": healthy["status"]})
            faults = (
                (URLError("simulated connection refused"), "index_unavailable"),
                (TimeoutError("simulated timeout"), "index_unavailable"),
                (HTTPError("", 403, "", None, None), "index_access_denied"),
                (HTTPError("", 404, "", None, None), "index_resource_missing"),
                (HTTPError("", 503, "", None, None), "index_unavailable"),
            )
            for fault, expected in faults:
                with patch("query_approval.request", side_effect=fault):
                    result = query_with_service_status(question, scope, *context)
                assert result["status"] == expected and "result" not in result, result
                checks.append({"case": type(fault).__name__, "status": expected,
                               "http_status": getattr(fault, "code", None)})
            with patch("query_approval.request", return_value={"resources": [{
                "uri": f"{scope}/APPROVAL-027/APPROVAL-027.md",
            }]}) as retrieval, patch("query_approval.directed", return_value={
                "status": "source_mismatch",
            }):
                retrieval.side_effect = [retrieval.return_value, "stale indexed content"]
                result = query_with_service_status(question, scope, *context)
            assert result["status"] == "source_mismatch" and "result" not in result, result
            checks.append({"case": "simulated stale index content", "status": result["status"]})
        result = subprocess.run(
            [sys.executable, "-B", str(validator), "-p", str(root)],
            encoding="utf-8", errors="replace", capture_output=True, timeout=30,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        assert result.returncode == 0, (result.stdout, result.stderr)
        assert digest(root) == before
        checks.append({"case": "native ARG validator and read-only sample", "status": "passed",
                       "stdout": result.stdout.replace(str(root), "<synthetic project>")})
    output = RUNTIME / f"pilot-readiness-{time.strftime('%Y%m%d-%H%M%S')}.json"
    with output.open("x", encoding="utf-8") as stream:
        json.dump(checks, stream, ensure_ascii=False, indent=2)
    print(f"{len(checks)} checks passed")
    print(output)


if __name__ == "__main__":
    main()
