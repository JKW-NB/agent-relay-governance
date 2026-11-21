"""Measure natural-language retrieval separately from scoped state resolution."""
import argparse
import json
import re
import time
from pathlib import Path

from evaluate import request
from evaluate_parallel_approvals import HERE, RUNTIME, resolve_matter

CASES = (
    ("archive", "Is the approval to verify the relay archive with SHA-256 still valid?", "ARCHIVE-VERIFY"),
    ("archive paraphrase", "Did authorization for checking the archived handoff package get withdrawn?", "ARCHIVE-VERIFY"),
    ("backup", "Does approval for SHA-256 verification of the relay backup still stand?", "BACKUP-VERIFY"),
    ("backup paraphrase", "Who cleared the integrity check for backup copies of the handoff?", "BACKUP-VERIFY"),
    ("near match", "For the backup copy, did the SHA-256 authorization get withdrawn like the archive approval?", "BACKUP-VERIFY"),
    ("ambiguous", "Is the SHA-256 verification approval still valid?", None),
)


STRESS_CASES = (
    ("comparison first", "Unlike the archive approval, is the relay backup approval still valid?", "BACKUP-VERIFY", 3),
    ("reverse target", "Is the relay archive approval still valid like the relay backup approval?", "ARCHIVE-VERIFY", 3),
    ("unknown alias", "Is approval for checking the cold-storage duplicate still valid?", "BACKUP-VERIFY", 3),
    ("mixed unresolved", "Which is still approved, the relay archive or the relay backup?", None, 3),
    ("comparison without main subject", "Unlike the archive approval, is it still valid?", None, 3),
    ("candidate cutoff", "For the backup copy, did the SHA-256 authorization get withdrawn like the archive approval?", "BACKUP-VERIFY", 1),
)

MATTER_ALIASES = {
    "ARCHIVE-VERIFY": ("relay archive", "archived handoff package", "archive approval"),
    "BACKUP-VERIFY": ("relay backup", "backup copies", "backup copy"),
}


def identify_matter(question):
    """Identify a unique matter in the main clause of the synthetic queries."""
    normalized = question.casefold().strip()
    if normalized.startswith(("unlike ", "like ")):
        _, separator, normalized = normalized.partition(",")
        if not separator:
            return None
    focus, *_ = re.split(r"\blike\b", normalized, maxsplit=1)
    candidates = [
        matter for matter, aliases in MATTER_ALIASES.items()
        if any(re.search(rf"\b{re.escape(alias)}\b", focus) for alias in aliases)
    ]
    return candidates[0] if len(candidates) == 1 else None

def main(scope, use_aliases=False, stress=False, retry_top3=False):
    config = json.loads((RUNTIME / "ov.conf").read_text(encoding="utf-8"))
    headers = {
        "X-API-Key": config["server"]["root_api_key"],
        "X-OpenViking-Account": "arg-poc",
        "X-OpenViking-User": "evaluator",
        "Content-Type": "application/json",
    }
    fixtures = json.loads((HERE / "parallel-approvals.json").read_text(encoding="utf-8"))
    records = {record["id"]: record for record in fixtures}
    expected_states = {
        "ARCHIVE-VERIFY": ("revoked", None, "APPROVAL-028"),
        "BACKUP-VERIFY": ("active", "Dana Park", "APPROVAL-031"),
    }
    rows = []
    cases = tuple((*case, 3) for case in CASES)
    if use_aliases:
        cases += (("two matters", "Are the relay archive and relay backup approvals both valid?", None, 3),)
    if stress:
        cases += STRESS_CASES
    for name, query, expected_matter, limit in cases:
        identified = identify_matter(query) if use_aliases else expected_matter
        attempts = []
        limits = (limit, 3) if retry_top3 and identified and limit < 3 else (limit,)
        for candidate_limit in limits:
            hits = request(
                "/search/find", headers,
                {"query": query, "target_uri": scope, "limit": candidate_limit},
            )["resources"]
            assert all(hit["uri"].startswith(scope + "/") for hit in hits), hits
            ids = [Path(hit["uri"]).stem for hit in hits]
            matters = [records.get(record_id, {}).get("matter_id") for record_id in ids]
            attempts.append({"limit": candidate_limit, "ids": ids, "matters": matters})
            if identified in matters:
                break
        rank = next((i for i, matter in enumerate(matters, 1) if matter == expected_matter), None) if expected_matter else None
        selected = next((key for key, matter in zip(ids, matters) if matter == identified), None) if identified else None
        if not use_aliases and rank != 1:
            selected = None
        if identified is None:
            result = ("matter_required", None, None)
            stage = "matter_not_specified"
        elif selected is None:
            result = ("unverified_matter", None, None)
            stage = "retrieval_mismatch"
        else:
            result, _ = resolve_matter(records, selected, identified, "2026-10-12")
            stage = "resolved" if result == expected_states.get(expected_matter) else "resolution_failure"
        rows.append({
            "case": name, "query": query, "expected_matter": expected_matter, "limit": limit,
            "hits": hits, "hit_ids": ids, "hit_matters": matters,
            "first_matching_rank": rank, "identified_matter": identified, "selected_id": selected,
            "stage": stage, "result": result, "attempts": attempts,
        })
        print(name, ids, rank, stage, result, flush=True)
    mode = 'aliases' if use_aliases else 'top1'
    if stress:
        mode += '-stress'
    if retry_top3:
        mode += '-retry'
    output = RUNTIME / f"natural-approvals-{mode}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    with output.open("x", encoding="utf-8") as stream:
        json.dump({"scope": scope, "as_of": "2026-10-12", "rows": rows}, stream, indent=2)
    print(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("scope")
    parser.add_argument("--use-aliases", action="store_true")
    parser.add_argument('--stress', action='store_true')
    parser.add_argument('--retry-top3', action='store_true')
    args = parser.parse_args()
    main(args.scope, args.use_aliases or args.stress, args.stress, args.retry_top3)
