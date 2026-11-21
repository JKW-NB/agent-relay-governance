"""Separate context selection from generation using fixed expert-chosen passages."""
import argparse
import hashlib
import json
import time
from pathlib import Path

from evaluate import MODEL, generate

# One-based, inclusive ranges in the frozen source snapshot.
PASSAGES = {
    1: (("README", 21, 24),),
    2: (("CHECKPOINT", 3, 6),),
    3: (("DECISIONS", 3, 4), ("DECISIONS", 39, 39)),
    4: (("MIGRATION", 58, 65),),
    5: (("REVIEW", 80, 96),),
    6: (("ARCHIVING", 30, 43),),
    7: (("PITFALLS", 13, 19), ("PITFALLS", 49, 61), ("PITFALLS", 63, 76)),
    8: (("REVIEW", 80, 87),),
}


def normalized(text):
    return " ".join(text.split())


def main(previous_path, model):
    report_path = previous_path.with_name("report.json")
    manifest = json.loads(report_path.read_text(encoding="utf-8"))["manifest"]
    previous = json.loads(previous_path.read_text(encoding="utf-8"))
    lines = {}
    for key, entry in manifest.items():
        data = report_path.with_name(key + ".md").read_bytes()
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise ValueError(f"Snapshot changed: {key}")
        lines[key] = data.decode("utf-8").splitlines()
    results = []
    for case, ranges in PASSAGES.items():
        g1 = next(row for row in previous["rows"] if row["case"] == case and row["group"] == "G1")
        evidence = [(key, "\n".join(lines[key][start - 1:end])) for key, start, end in ranges]
        assert sum(len(text) for _, text in evidence) <= previous["max_context_chars"]
        coverage = []
        for (key, start, end), (_, text) in zip(ranges, evidence):
            source_lines = [normalized(line) for line in text.splitlines() if line.strip()]
            candidates = [normalized(chunk) for source, chunk in g1["evidence"] if source == key]
            retrieved = [normalized(hit["text"]) for hit in g1["ov_audit"]
                         if hit["id"] == key and hit["normalized"]]
            coverage.append({
                "source": key, "range": [start, end], "lines": len(source_lines),
                "found_in_context": sum(any(line in chunk for chunk in candidates) for line in source_lines),
                "found_in_verified_ov_hits": sum(any(line in chunk for chunk in retrieved) for line in source_lines),
            })
        started = time.perf_counter()
        raw = generate(g1["question"], evidence, 60, True, model=model)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        try:
            answer = json.loads(raw["response"])
        except json.JSONDecodeError:
            answer = None
        citations = [
            {"id": item["id"], "exact": bool(item["quote"].strip()) and any(
                key == item["id"] and item["quote"].strip() in text for key, text in evidence
            )}
            for item in (answer or {}).get("citations", [])
        ]
        results.append({"case": case, "question": g1["question"], "coverage": coverage,
                        "previous_answer": g1["answer"], "curated_evidence": evidence,
                        "answer": answer, "raw": raw["response"], "citations": citations,
                        "elapsed_ms": elapsed_ms, "done_reason": raw.get("done_reason")})
        print(case, [(x["found_in_verified_ov_hits"], x["found_in_context"], x["lines"])
                     for x in coverage], ascii((answer or {}).get("answer", raw["response"]))[:520], flush=True)
    output = previous_path.with_name(f"public-evidence-diagnosis-{time.strftime('%Y%m%d-%H%M%S')}.json")
    with output.open("x", encoding="utf-8") as stream:
        json.dump({"previous_run": str(previous_path), "model": model, "results": results}, stream, indent=2)
    print(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("previous", type=Path)
    parser.add_argument('--model', default=MODEL)
    args = parser.parse_args()
    main(args.previous, args.model)
