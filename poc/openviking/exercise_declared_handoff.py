"""Exercise read-only handoff checks against declared JSON report fields."""
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

from query_approval import HERE, RUNTIME

REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "integrations/openviking"))
from verify_handoff import check, digest

CASES = (
    ("T-01-01", "rollback-protection-20261108-102939.json", ["restored", "revision"], 4),
    ("T-01-02", "backup-integrity-20261110-101624.json", ["integrity", "files"], 86),
    ("T-01-03", "restore-from-report-1936-20261110-102036.json", ["target_port"], 1936),
)


def main():
    fixture = RUNTIME / "handoff-recovery-e2575b25643e/ov_available"
    rows = []
    with tempfile.TemporaryDirectory(dir=RUNTIME, prefix="declared-handoff-") as folder:
        for index, (task, filename, field, expected) in enumerate(CASES):
            root = Path(folder, task).resolve()
            root.mkdir()
            for name in ("AGENTS.md", "CHECKPOINT.md", "PROJECT_LOG.md"):
                shutil.copyfile(fixture / name, root / name)
            status = "READY" if index == 1 else "PAUSED"
            state = (fixture / "CURRENT_STATE.yaml").read_text(encoding="utf-8").replace(
                "T-01-01", task
            ).replace('status: "PAUSED"', f'status: "{status}"').replace(
                "Verify prior rollback revision before starting release review", "Verify the declared report field"
            ).replace(
                "Find the recorded rollback revision. If there is no verified source, report HOLD and request evidence.",
                "Check the declared report field against the acceptance criterion."
            )
            (root / "CURRENT_STATE.yaml").write_text(state, encoding="utf-8")
            evidence = root / filename
            data = (RUNTIME / filename).read_bytes()
            evidence.write_bytes(data)
            contract = {"task_id": task, "path": filename, "sha256": digest(data),
                        "field": field, "expected": expected}
            before = {p.name: digest(p.read_bytes()) for p in root.iterdir() if p.is_file()}
            for name, params, want in (
                ("positive", contract, "criterion_verified"),
                ("wrong task", {**contract, "task_id": "T-01-99"}, "contract_does_not_apply"),
                ("missing file", {**contract, "path": "not-present.json"}, "approved_report_missing"),
                ("wrong hash", {**contract, "sha256": "0" * 64}, "report_hash_mismatch"),
                ("wrong field", {**contract, "field": ["no_such_field"]}, "report_field_unavailable"),
                ("different criterion", {**contract, "expected": expected + 1}, "criterion_not_met"),
            ):
                actual = check(root, params)
                assert actual["reason"] == want and actual["task_status"] == status, actual
                assert actual["proposed_action"] == ("VERIFY_COMPLETE" if name == "positive" else "HOLD")
                rows.append({"task": task, "case": name, "result": actual})
            assert before == {p.name: digest(p.read_bytes()) for p in root.iterdir() if p.is_file()}
    output = RUNTIME / f"declared-handoff-{time.strftime('%Y%m%d-%H%M%S')}.json"
    with output.open("x", encoding="utf-8") as stream:
        json.dump({"rows": rows, "files_unchanged": True}, stream, indent=2)
    print(f"{len(rows)} checks passed")
    print(output)


if __name__ == "__main__":
    main()
