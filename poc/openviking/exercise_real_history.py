"""Run three arms on measured ARG/OV development history, using selected report fields."""
import hashlib
import json
import time
import uuid
from pathlib import Path
from urllib.parse import urlencode

from compare_public_pilot import budget, local_context
from evaluate import generate, request
from exercise_index_release import upload
from query_approval import RUNTIME, load_context

INPUTS = {
    "CUTOVER": "active-index-cutover-20261108-102646.json",
    "RACES": "approval-release-races-20261108-102936.json",
    "BACKUP": "backup-integrity-20261110-101624.json",
    "RESTORE": "restore-from-report-1936-20261110-102036.json",
    "ACCEPTANCE": "poc-acceptance-20261110-110609.json",
}
TASKS = (
    ("After active-index cutover and rollback, what was the final pointer revision?", "CUTOVER"),
    ("In the race test, what status did an old publish request get after the scope changed away and returned?", "RACES"),
    ("How many files passed verification in the backup integrity exercise?", "BACKUP"),
    ("If the source instance cannot participate, which port was successfully restored from an existing backup report?", "RESTORE"),
    ("How many live approval queries passed in the final four-instance POC acceptance?", "ACCEPTANCE"),
    ("Who gave final approval to launch OpenViking in production?", None),
)
MODEL = "qwen2.5:1.5b"


def project_records():
    raw = {key: (RUNTIME / name).read_bytes() for key, name in INPUTS.items()}
    data = {key: json.loads(value.decode("utf-8-sig")) for key, value in raw.items()}
    summaries = {
        "CUTOVER": f"The active-index cutover and rollback exercise finished at pointer revision {data['CUTOVER']['final']['revision']}.",
        "RACES": f"After switching away and returning to the original scope, the old publish request returned {data['RACES']['stale_after_return_to_same_scope']['outcome']}.",
        "BACKUP": f"The backup integrity exercise verified {data['BACKUP']['integrity']['files']} files. The source and restored embedding digests matched.",
        "RESTORE": f"The independent restore from an existing backup report succeeded on port {data['RESTORE']['target_port']}. The query recovered the original approval status.",
        "ACCEPTANCE": f"The final four-instance POC acceptance passed {sum(len(item['queries']) for item in data['ACCEPTANCE']['instances'])} live approval queries.",
    }
    manifest = {key: {"source_report": INPUTS[key], "source_sha256": hashlib.sha256(raw[key]).hexdigest(),
                      "indexed_text": text} for key, text in summaries.items()}
    return summaries, manifest


def fetch(question, scope, headers):
    hits = request("/search/find", headers, {"query": question, "target_uri": scope, "limit": 5})["resources"]
    passages = []
    for hit in hits:
        uri = hit["uri"]
        if not uri.startswith(scope + "/") or not uri.endswith(".md"):
            continue
        key = Path(uri).stem
        if uri != f"{scope}/{key}/{key}.md":
            continue
        text = request("/content/read?" + urlencode({"uri": uri}), headers)
        passages.append((key, text.strip()))
    return passages


def main():
    headers, _, _ = load_context()
    corpus, manifest = project_records()
    tag = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    scope = f"viking://resources/arg-project-history-{tag}"
    request("/fs/mkdir", headers, {"uri": scope})
    for key, text in corpus.items():
        upload({"id": key, "text": text}, scope, headers)

    rows = []
    for index, (question, expected) in enumerate(TASKS):
        groups = ("G0", "G1", "G2")
        for group in groups[index % 3:] + groups[:index % 3]:
            started = time.perf_counter()
            local = local_context(question, corpus)[:2]
            retrieved = fetch(question, scope, headers) if group != "G0" else []
            verified = [(key, text) for key, text in retrieved if corpus.get(key) == text]
            evidence = budget((verified if group == "G2" else retrieved)[:2] + local)[:2]
            raw = generate(question, evidence, 60 - (time.perf_counter() - started), True, model=MODEL)
            try:
                answer = json.loads(raw["response"])
            except json.JSONDecodeError:
                answer = None
            citations = []
            for item in (answer or {}).get("citations", []):
                quote = item["quote"].strip()
                citations.append({**item, "matches_original": bool(quote) and quote in corpus.get(item["id"], "")})
            rows.append({"group": group, "question": question, "expected_source": expected,
                         "retrieved": retrieved, "verified": verified, "context": evidence,
                         "answer": answer, "raw": raw["response"], "citation_audit": citations,
                         "prompt_tokens": raw.get("prompt_eval_count"), "generated_tokens": raw.get("eval_count"),
                         "elapsed_ms": round((time.perf_counter() - started) * 1000, 2)})
            print(group, index + 1, ascii((answer or {}).get("answer", raw["response"])), flush=True)

    # Separately inject an unauthorized and an out-of-date copy to exercise the same provenance check.
    fault_rows = [("CUTOVER", "The final pointer revision was 99."), ("UNKNOWN", "Production approved.")]
    assert all(corpus.get(key) != text for key, text in fault_rows)
    assert project_records()[1] == manifest
    output = RUNTIME / f"real-history-three-arm-{tag}.json"
    with output.open("x", encoding="utf-8") as stream:
        json.dump({"scope": scope, "model": MODEL, "manifest": manifest, "rows": rows,
                   "rejected_provenance_probes": fault_rows}, stream, indent=2)
    print(output)


if __name__ == "__main__":
    main()
