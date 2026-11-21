"""Inspect canonical ARG context and gather optional historical evidence."""
import argparse
import importlib.util
import json
from pathlib import Path

from retrieve import lookup

spec = importlib.util.spec_from_file_location(
    "arg_validator", Path(__file__).resolve().parents[2] / "scripts/validate_governance.py",
)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


def local_file(root, relative):
    path = (root / relative).resolve()
    return path.is_relative_to(root) and path.is_file()


def preflight(root, question=None, config=None):
    state_file = "CURRENT_STATE.yaml"
    required = ["AGENTS.md", state_file]
    missing = [path for path in required if not local_file(root, path)]
    if missing:
        return {"status": "required_context_missing", "missing": missing}
    state = validator.parse_yaml_subset((root / state_file).read_text(encoding="utf-8-sig"))
    task = state["current"]["task"]
    status = task["status"]
    if status not in validator.STATUS_VOCAB:
        raise ValueError("Unknown task status")
    context = state.get("context", {})
    required += list(context.get("required") or [])
    if status in {"PAUSED", "HOLD"}:
        checkpoint = validator._find(root, ["CHECKPOINT_项目断点.md", "CHECKPOINT.md"])
        required.append(Path(checkpoint).relative_to(root).as_posix() if checkpoint else "CHECKPOINT.md")
    required = list(dict.fromkeys(required))
    missing = [path for path in required if not local_file(root, path)]
    result = {
        "status": "required_context_missing" if missing else "local_context_ready",
        "state_source": state_file,
        "task_id": task["id"],
        "task_status": status,
        "exact_next_action": task.get("exact_next_action"),
        "local_required": required,
        "missing": missing,
        "conditional_context": context.get("conditional") or [],
    }
    if question and not missing:
        try:
            result["historical_evidence"] = lookup(root, config or {}, question)
        except (OSError, ValueError, TypeError, AttributeError, KeyError):
            result["historical_evidence"] = {"status": "invalid_config_use_local", "evidence": []}
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--question")
    args = parser.parse_args()
    config = None
    invalid_config = False
    if args.config and args.question:
        try:
            config = json.loads(args.config.read_text(encoding="utf-8-sig"))
            invalid_config = not isinstance(config, dict)
        except (OSError, ValueError):
            invalid_config = True
    try:
        result = preflight(args.project_root.resolve(), args.question, None if invalid_config else config)
        if invalid_config and "historical_evidence" in result:
            result["historical_evidence"]["status"] = "invalid_config_use_local"
    except (OSError, ValueError, TypeError, AttributeError, KeyError) as error:
        result = {"status": "invalid_local_state", "error": type(error).__name__}
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
