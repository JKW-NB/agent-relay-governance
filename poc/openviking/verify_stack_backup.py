"""Check a stack snapshot against the file digests recorded at backup time."""
import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

ITEMS = ("ov/ov.conf", "ov/data", "ov/approval-active-index.json")


def verify(root, files):
    expected = {Path(row["path"]).as_posix(): row["sha256"].lower() for row in files}
    actual = {}
    for item in ITEMS:
        path = root / item
        for file in ([path] if path.is_file() else path.rglob("*")):
            if file.is_file():
                with file.open("rb") as stream:
                    digest = hashlib.file_digest(stream, "sha256").hexdigest()
                actual[file.relative_to(root).as_posix()] = digest
    return {
        "missing": sorted(expected.keys() - actual.keys()),
        "unexpected": sorted(actual.keys() - expected.keys()),
        "modified": sorted(key for key in expected.keys() & actual.keys() if expected[key] != actual[key]),
    }


def main(report_path, exercise):
    report = json.loads(report_path.read_text(encoding="utf-8"))
    snapshot = Path(report["snapshot"])
    result = verify(snapshot, report["files"])
    if any(result.values()):
        print(json.dumps(result))
        return 1
    if exercise:
        with tempfile.TemporaryDirectory(dir=report_path.parent, prefix="backup-integrity-") as folder:
            root = Path(folder) / "copy"
            shutil.copytree(snapshot, root)
            pointer = root / "ov/approval-active-index.json"
            pointer.write_bytes(pointer.read_bytes() + b" ")
            assert verify(root, report["files"])["modified"] == ["ov/approval-active-index.json"]
            pointer.unlink()
            assert verify(root, report["files"])["missing"] == ["ov/approval-active-index.json"]
            (root / "ov/data/unexpected-probe.txt").write_text("probe", encoding="utf-8")
            assert verify(root, report["files"])["unexpected"] == ["ov/data/unexpected-probe.txt"]
        result["faults_detected"] = ["modified", "missing", "unexpected"]
    print(json.dumps({"snapshot": str(snapshot), "files": len(report["files"]), **result}))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--exercise", action="store_true")
    args = parser.parse_args()
    raise SystemExit(main(args.report, args.exercise))
