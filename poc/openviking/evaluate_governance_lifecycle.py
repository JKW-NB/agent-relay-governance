"""Resolve one synthetic fact stream per record type at an explicit date."""
import json
import os
import time
from collections import Counter
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNTIME = Path(os.environ.get("ARG_POC_RUNTIME", HERE.parents[2] / "openviking-runtime"))


def resolve(records, record_type, as_of):
    cutoff = date.fromisoformat(as_of)
    eligible = [
        record for record in records
        if record["type"] == record_type and date.fromisoformat(record["effective_on"]) <= cutoff
    ]
    if not eligible:
        return ("no_effective_record", None, None)

    by_id = {record["id"]: record for record in eligible}
    if len(by_id) != len(eligible):
        return ("conflict", None, None)
    predecessors = Counter()
    for record in eligible:
        previous_id = record["supersedes"]
        if previous_id is None:
            continue
        previous = by_id.get(previous_id)
        if previous is None:
            return ("incomplete_chain", None, None)
        if date.fromisoformat(previous["effective_on"]) >= date.fromisoformat(record["effective_on"]):
            return ("conflict", None, None)
        predecessors[previous_id] += 1
    heads = [record for record in eligible if record["id"] not in predecessors]
    if len(heads) != 1 or any(count > 1 for count in predecessors.values()):
        return ("conflict", None, None)
    head = heads[0]
    if head["value"] is None:
        return ("revoked", None, head["id"])
    return ("active", head["value"], head["id"])


def main():
    fixture = json.loads((HERE / "governance-lifecycle.json").read_text(encoding="utf-8"))
    records = {record["id"]: record for record in fixture["records"]}
    results = []
    for case in fixture["cases"]:
        supplied = [records[key] for key in case["ids"]]
        result = resolve(supplied, case["type"], case["as_of"])
        assert list(result) == case["expected"], (case["name"], result)
        results.append({"case": case, "result": result, "source": records.get(result[2])})

    competing = {**records["ASSIGN-014"], "id": "ASSIGN-015", "value": "Dana Park"}
    supplied = [records["ASSIGN-013"], records["ASSIGN-014"], competing]
    result = resolve(supplied, "assignment", "2026-10-10")
    assert result == ("conflict", None, None), result
    results.append({"case": {"name": "competing replacements", "records": supplied}, "result": result})

    output = RUNTIME / f"governance-lifecycle-{time.strftime('%Y%m%d-%H%M%S')}.json"
    with output.open("x", encoding="utf-8") as stream:
        json.dump(results, stream, indent=2)
    print(f"{len(results)} lifecycle cases passed")
    print(output)


if __name__ == "__main__":
    main()
