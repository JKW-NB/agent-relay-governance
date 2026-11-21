"""Compare line-level search with and without verified OV context."""
import argparse
import hashlib
import json
import math
import re
import time
from collections import Counter
from pathlib import Path

from compare_public_pilot import audit_hits, words
from evaluate import request
from evaluate_decomposed_pilot import SOURCE_LINES, TASKS
from query_approval import load_context


HOLDOUT = (
    ("Which encoding should generated CSV files use for Excel compatibility?", ("ARCHIVING", 47, 47)),
    ("Can agents settle a factual conflict by majority vote or silent overwrite?", ("SKILL", 46, 46)),
    ("How many times may an agent repeat the identical failing action?", ("SKILL", 111, 111)),
    ("What metadata is recorded for each review row during two-pass review?", ("REVIEW", 55, 55)),
    ("How are review results merged back into the original registry files?", ("REVIEW", 64, 64)),
)


def normalize(text):
    return " ".join(text.split())


def windows(sources):
    for key, text in sources.items():
        lines = text.splitlines()
        heading = ""
        for index, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("#"):
                heading = stripped
                continue
            if not stripped or stripped.startswith("```"):
                continue
            yield key, index + 1, line, words(line), words(heading)


def rank(question, candidates, ov_lines):
    terms = words(question)
    counts = Counter(term for _, _, _, tokens, _ in candidates for term in tokens)
    weight = {term: math.log(1 + len(candidates) / (1 + counts[term])) for term in terms}
    scored = []
    for key, number, line, tokens, heading in candidates:
        direct = sum(weight[term] for term in terms & tokens)
        contextual = sum(weight[term] for term in terms & heading)
        if not direct and not contextual:
            continue
        if normalize(line) in ov_lines.get(key, set()):
            direct *= 1.35
        scored.append((direct + 0.25 * contextual, key, number, line))
    return sorted(scored, key=lambda row: (-row[0], row[1], row[2]))[:3]


def expand_key_values(question, sources, picked):
    """Keep adjacent named key/value facts together when both keys are requested."""
    key_pattern = re.compile(r"^\s*([a-z][a-z0-9_]*):\s+\S", re.IGNORECASE)
    query_keys = set(re.findall(r"[a-z][a-z0-9_]*", question.casefold()))
    selected = {(row["source"], row["line"]) for row in picked}
    added = []
    for row in picked:
        match = key_pattern.match(row["quote"])
        if not match or match[1].casefold() not in query_keys:
            continue
        lines = sources[row["source"]].splitlines()
        for neighbor in (row["line"] - 1, row["line"] + 1):
            key = (row["source"], neighbor)
            if not 1 <= neighbor <= len(lines) or key in selected:
                continue
            quote = lines[neighbor - 1]
            other = key_pattern.match(quote)
            if other and other[1].casefold() in query_keys:
                added.append({**row, "line": neighbor, "quote": quote, "selection": "adjacent_requested_key"})
                selected.add(key)
    return added

def main(report_path, structured_blocks, holdout):
    report = json.loads(report_path.read_text(encoding="utf-8"))
    sources = {}
    for key, entry in report["manifest"].items():
        data = report_path.with_name(key + ".md").read_bytes()
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise ValueError(f"Snapshot changed: {key}")
        sources[key] = data.decode("utf-8")
    candidates = list(windows(sources))
    headers, _, _ = load_context()
    rows = []
    cases = HOLDOUT if holdout else tuple(
        (task[1], source) for task, source in zip(TASKS, SOURCE_LINES, strict=True)
    )
    for question, (key, first, last) in cases:
        expected = {(key, line) for line in range(first, last + 1)}
        for mode in ("local", "ov"):
            started = time.perf_counter()
            ov_lines = {}
            if mode == "ov":
                hits = request("/search/find", headers, {
                    "query": question, "target_uri": report["scope"], "limit": 5,
                })["resources"]
                for audit in audit_hits(report["scope"], hits, sources, headers):
                    if audit["normalized"]:
                        ov_lines.setdefault(audit["id"], set()).update(
                            normalize(line) for line in audit["text"].splitlines() if line.strip()
                        )
            picked = []
            for score, source, number, line in rank(question, candidates, ov_lines):
                assert sources[source].splitlines()[number - 1] == line
                picked.append({"path": report["manifest"][source]["path"], "source": source,
                               "line": number, "quote": line, "score": round(score, 4)})
            adjacent = expand_key_values(question, sources, picked) if structured_blocks else []
            actual = {(row["source"], row["line"]) for row in picked}
            augmented = actual | {(row["source"], row["line"]) for row in adjacent}
            row = {
                "mode": mode, "question": question, "expected": sorted(expected),
                "top1_complete": bool(picked) and expected <= {(picked[0]["source"], picked[0]["line"])},
                "top3_complete": expected <= actual, "with_adjacent_complete": expected <= augmented,
                "picked": picked, "adjacent": adjacent,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            }
            rows.append(row)
            print(mode, question, row["with_adjacent_complete"], sorted(augmented), flush=True)
    mode = 'holdout' if holdout else 'original'
    output = report_path.with_name(f"line-retrieval-{mode}-{time.strftime('%Y%m%d-%H%M%S')}.json")
    with output.open("x", encoding="utf-8") as stream:
        json.dump({"commit": report["commit"], "rows": rows}, stream, indent=2)
    print(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument('--structured-blocks', action='store_true')
    parser.add_argument('--holdout', action='store_true')
    args = parser.parse_args()
    main(args.report, args.structured_blocks, args.holdout)
