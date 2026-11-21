"""Index an explicit allowlist of committed ARG project documentation."""
import hashlib
import json
import subprocess
import uuid
from urllib.parse import urlencode

from evaluate import request
from exercise_index_release import upload
from query_approval import HERE, RUNTIME, load_context

SOURCES = {
    "README": "README.md",
    "SKILL": "SKILL.md",
    "MIGRATION": "references/migration-v1-to-v2.md",
    "REVIEW": "references/human-review-workflow.md",
    "ARCHIVING": "references/data-archiving.md",
    "PITFALLS": "references/pitfalls.md",
    "CHECKPOINT": "assets/templates/CHECKPOINT.template.md",
    "DECISIONS": "assets/templates/DECISIONS.template.md",
}
CASES = (
    ("What file owns the current working state when derived views disagree?", {"SKILL", "README"}),
    ("When should a checkpoint be written and when may it be skipped?", {"CHECKPOINT", "SKILL"}),
    ("How should a frozen decision be overturned?", {"DECISIONS", "SKILL"}),
    ("How do I migrate existing V1 governance files to V2?", {"MIGRATION"}),
    ("What evidence is needed before closing the human review gate?", {"REVIEW"}),
    ("How do I maintain the SHA-256 archive manifest?", {"ARCHIVING"}),
    ("What recurring failure modes should a handoff avoid?", {"PITFALLS"}),
    ("Who approved production deployment of the OpenViking integration?", set()),
)


def git(*args):
    return subprocess.check_output(["git", "-C", str(HERE.parents[1]), *args])


def main():
    headers, _, _ = load_context()
    head = git("rev-parse", "HEAD").decode().strip()
    before = git("status", "--porcelain")
    key = uuid.uuid4().hex[:12]
    scope = f"viking://resources/arg-public-pilot-{key}"
    pilot = RUNTIME / "public-pilot" / key
    pilot.mkdir(parents=True)
    request("/fs/mkdir", headers, {"uri": scope})
    sources = {}
    for source_id, path in SOURCES.items():
        data = git("show", f"{head}:{path}")
        text = data.decode("utf-8").strip()
        (pilot / f"{source_id}.md").write_bytes(data)
        upload({"id": source_id, "text": text}, scope, headers)
        sources[source_id] = {"path": path, "sha256": hashlib.sha256(data).hexdigest(), "text": text}
    rows = []
    for question, expected in CASES:
        hits = request("/search/find", headers, {
            "query": question, "target_uri": scope, "limit": 5,
        })["resources"]
        audits = []
        for hit in hits:
            uri = hit["uri"]
            assert uri.startswith(scope + "/"), uri
            source_id = uri.removeprefix(scope + "/").split("/", 1)[0]
            if source_id not in sources:
                continue
            if not uri.endswith(".md"):
                uri += f"/{source_id}.md"
            observed = request("/content/read?" + urlencode({"uri": uri}), headers)
            fragment = observed.strip()
            audits.append({"id": source_id, "uri": uri, "score": hit["score"],
                           "matches": bool(fragment) and fragment in sources[source_id]["text"]})
        relevant = [row["id"] for row in audits if row["id"] in expected and row["matches"]]
        rows.append({"query": question, "expected": sorted(expected), "hits": hits,
                     "source_audit": audits, "matching_sources": relevant})
        print(question, relevant, flush=True)
    assert git("rev-parse", "HEAD").decode().strip() == head
    assert git("status", "--porcelain") == before
    output = pilot / "report.json"
    manifest = {key: {k: v for k, v in value.items() if k != "text"} for key, value in sources.items()}
    with output.open("x", encoding="utf-8") as stream:
        json.dump({"commit": head, "scope": scope, "manifest": manifest, "queries": rows}, stream, indent=2)
    print(output)


if __name__ == "__main__":
    main()
