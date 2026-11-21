"""Run a fixed model on automatically selected, source-bound evidence."""
import argparse
import json
import time
from pathlib import Path

from evaluate import generate


def main(path):
    baseline = json.loads(path.read_text(encoding="utf-8"))
    results = []
    for row in baseline["rows"]:
        if row["mode"] != "ov":
            continue
        selected = row["picked"] + row["adjacent"]
        evidence = [(item["source"], item["quote"]) for item in selected]
        started = time.perf_counter()
        raw = generate(row["question"], evidence, 60, True, model="qwen2.5:1.5b")
        try:
            answer = json.loads(raw["response"])
        except json.JSONDecodeError:
            answer = None
        audits = []
        for citation in (answer or {}).get("citations", []):
            quote = citation["quote"].strip()
            audits.append({**citation, "exact": bool(quote) and any(
                key == citation["id"] and quote in text for key, text in evidence
            )})
        results.append({"question": row["question"], "evidence_complete": row["with_adjacent_complete"],
                        "candidates": selected, "answer": answer, "raw": raw["response"],
                        "citation_audit": audits, "elapsed_ms": round((time.perf_counter()-started)*1000, 2)})
        print(row["with_adjacent_complete"], ascii((answer or {}).get("answer", raw["response"])), flush=True)
    output = path.with_name(f"automatic-line-answers-{time.strftime('%Y%m%d-%H%M%S')}.json")
    with output.open("x", encoding="utf-8") as stream:
        json.dump({"retrieval_report": str(path), "model": "qwen2.5:1.5b", "results": results}, stream, indent=2)
    print(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    main(parser.parse_args().report)
