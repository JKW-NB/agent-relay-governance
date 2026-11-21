"""Run the same question in isolated G0 and G1 model calls."""
import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
RUNTIME = HERE.parents[2] / "openviking-runtime"
DOCKER = Path(r"D:\DevTools\Docker\Desktop\resources\bin\docker.exe")
MODEL = "qwen2.5:0.5b"
OV = os.environ.get("ARG_POC_OV_URL", "http://127.0.0.1:1933").rstrip("/") + "/api/v1"
QUESTIONS = (
    json.loads((HERE / "config.json").read_text(encoding="utf-8"))["query"],
    "What method did the team settle on to detect tampering in the handoff package, and what incident prompted the switch?",
    "Who approved the change to the relay archive verification method?",
)
EXPANDED_QUESTIONS = (
    "Who was assigned to implement SHA-256 for relay archive verification?",
    "Was SHA-256 deployed to production, and on what date?",
    "How many seconds did the smaller screenshots save per upload?",
    "What did the demo team change to speed up uploads, and what did it measure?",
    "What check passed despite the content being edited, and why could the edit evade that check?",
    "Which rehearsal event does the SHA-256 decision cite as evidence?",
)
INSTRUCTIONS = (
    "Answer the question using only the supplied evidence. "
    "Return JSON with an answer string and a citations array of evidence IDs. "
    "If the evidence does not answer the question, answer 'Insufficient evidence' "
    "and use an empty citations array."
)


STRICT_INSTRUCTIONS = (
    "Use only the supplied evidence. For each claim, copy a verbatim quote "
    "that directly proves it and give the evidence ID. "
    "Answer every part of the question. Choosing a method does not prove who approved it. "
    "If any requested fact lacks a direct quote, answer 'Insufficient evidence' "
    "with an empty citations array."
)
STRICT_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "quote": {"type": "string"}},
                "required": ["id", "quote"],
            },
        },
    },
    "required": ["answer", "citations"],
}

def request(path, headers, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = Request(OV + path, data=data, headers=headers)
    with urlopen(req, timeout=20) as response:
        payload = json.load(response)
    if payload["status"] != "ok":
        raise RuntimeError(payload.get("error"))
    return payload["result"]


def retrieve(question, headers, fixtures):
    result = request(
        "/search/find", headers,
        {"query": question, "target_uri": "viking://resources/arg-poc", "limit": 5},
    )
    evidence = []
    for hit in result["resources"]:
        uri = hit["uri"]
        evidence_id = Path(uri).stem
        if evidence_id not in fixtures:
            continue
        if not uri.endswith(".md"):
            uri += f"/{evidence_id}.md"
        content = request("/content/read?" + urlencode({"uri": uri}), headers)
        if content.strip() != fixtures[evidence_id]:
            raise ValueError(f"Source mismatch: {uri}")
        evidence.append((evidence_id, content.strip(), hit["score"], uri))
    return evidence


def generate(question, evidence, timeout, strict, *, model=MODEL, schema=None, instructions=None):
    context = "\n\n".join(
        f"[{item[0]}]" + (f" retrieval_score={item[2]:.3f}" if len(item) > 2 else "")
        + "\n" + item[1] for item in evidence
    )
    instructions = instructions or (STRICT_INSTRUCTIONS if strict else INSTRUCTIONS)
    payload = {
        "model": model,
        "prompt": f"{instructions}\n\nQuestion: {question}\n\nEvidence:\n{context}",
        "format": schema or (STRICT_SCHEMA if strict else "json"),
        "stream": False,
        "options": {"temperature": 0, "seed": 42, "num_predict": 384 if strict else 160},
    }
    bridge = (
        "import sys, urllib.request; "
        "r=urllib.request.Request('http://arg-ollama:11434/api/generate', "
        "data=sys.stdin.buffer.read(), headers={'Content-Type':'application/json'}); "
        "sys.stdout.buffer.write(urllib.request.urlopen(r, timeout=60).read())"
    )
    result = subprocess.run(
        [str(DOCKER), "exec", "-i", "arg-openviking", "python", "-c", bridge],
        input=json.dumps(payload), encoding="utf-8", capture_output=True,
        check=True, timeout=timeout,
    )
    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--strict-evidence', action='store_true')
    parser.add_argument('--expanded', action='store_true')
    args = parser.parse_args()
    strict = args.strict_evidence
    questions = QUESTIONS + EXPANDED_QUESTIONS if args.expanded else QUESTIONS
    config = json.loads((RUNTIME / "ov.conf").read_text(encoding="utf-8"))
    headers = {
        "X-API-Key": config["server"]["root_api_key"],
        "X-OpenViking-Account": "arg-poc",
        "X-OpenViking-User": "evaluator",
        "Content-Type": "application/json",
    }
    fixtures = {
        path.stem: path.read_text(encoding="utf-8").strip()
        for path in sorted((HERE / "fixtures").glob("*.md"))
    }
    rows = []
    for index, question in enumerate(questions):
        for group in (("G0", "G1") if index % 2 == 0 else ("G1", "G0")):
            started = time.perf_counter()
            evidence = list(fixtures.items()) if group == "G0" else retrieve(question, headers, fixtures)
            prep = time.perf_counter() - started
            raw = generate(question, evidence, 60 - prep, strict)
            row = {
                "question": question, "group": group, "evidence": evidence,
                "prep_seconds": round(prep, 3),
                "total_seconds": round(time.perf_counter() - started, 3),
                "prompt_tokens": raw.get("prompt_eval_count"),
                "response": raw["response"], "done_reason": raw.get("done_reason"),
            }
            rows.append(row)
            print(group, index + 1, row["total_seconds"], row["response"], flush=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    mode = 'strict' if strict else 'baseline'
    if args.expanded:
        mode += '-expanded'
    output = RUNTIME / f'paired-evaluation-{mode}-{stamp}.json'
    with output.open("x", encoding="utf-8") as stream:
        json.dump({"model": MODEL, "mode": mode, "runs": rows}, stream, ensure_ascii=False, indent=2)
    print(output)


if __name__ == "__main__":
    main()
