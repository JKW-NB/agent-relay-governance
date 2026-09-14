# Human Review + Gate-Close Workflow (machine-encoded data)

For data produced by machine/LLM coding that must be human-verified before entering analysis (e.g., policy text PMC scoring, document classification, transcript coding). Validated end-to-end on a 276-document policy scoring pipeline with two blocking gates.

## Table of contents
1. Delivery state JSON
2. Review list preparation
3. Priority tiers (P1/P2)
4. Review rules per item
5. Evidence paths
6. Write-back to original files
7. Final aggregation
8. Gate close
9. Verification checklist

## 1. Delivery state JSON

Ship machine output with a machine-readable status file:

```json
{
  "formal_main_target": 276,
  "auto_passed": 93,
  "pending_human_review": 183,
  "scoring_failed": 0,
  "formal_stock_ready": false,
  "blocking_reasons": ["183_SCORING_REVIEWS_PENDING", "276_VALIDITY_PERIODS_PENDING"]
}
```

`blocking_reasons` is the gate: any non-empty list means "do not use this data in regression". The aggregation program refuses (`FORMAL_GATE_BLOCKED`) while blockers exist.

## 2. Review list preparation

- Split machine output into: auto-passed (machine-confident) vs review queue.
- Sort review queue by risk priority. Each row carries `review_reasons` and `low_confidence_codes` so the reviewer knows WHY it was flagged.
- Attach `source_path` to every review row (join by ID from the master registry if missing — reviewers cannot work without the original text).

## 3. Priority tiers

| Tier | Meaning | Review depth |
|---|---|---|
| P1_EVIDENCE_OR_DOCUMENT | Missing attachment, truncated text, low-confidence codes | Read original carefully; individual note required |
| P2_FULL_SCORE_AUDIT | A module scored 100% | Verify the full-score module against the text only |

One full-score policy outweighs five 20-point policies in aggregation — full scores must be human-confirmed.

## 4. Review rules per item

- Status vocabulary: `ACCEPT_AS_CODED` / `REVISED_AND_ACCEPTED` / `EXCLUDE` (plus `AUTO_ACCEPTED` for machine-passed items, never hand-written).
- Every P1 item gets an **individual** note stating which code changed and the text evidence. A uniform template sentence for P1 items is a red flag (contradicts "missing attachment verified").
- Missing/truncated evidence → conservative: keep only what the visible text confirms, drop what it cannot, never infer from titles alone. ("no evidence, no inference")
- If text contains the topic but machine missed it → do not EXCLUDE; revise codes upward.
- EXCLUDE only when the document genuinely lacks the subject matter (e.g., pure forwarding notice, unrelated section).
- Two-pass review: junior agent (Codex-style) does initial per-item review marking "初审，待终审"; human does final sign-off. Every review row records reviewer + date + note.

## 5. Evidence paths

Every reviewed item should be able to answer "where exactly in the source does this come from". Store per-item evidence files (scoring JSON with quote + offset) next to the pipeline outputs; reviewers check evidence file first, full text second.

## 6. Write-back to original files

After human sign-off:
- Merge review results back into the ORIGINAL registry files by ID (status, revised scores, reviewer, date, note).
- Derived review files (review results, P1 comparison tables) stay as separate dated artifacts — they are work files, not the canonical source.
- Re-hash changed originals in the SHA256 manifest (content changed → old hash invalid).

## 7. Final aggregation

Aggregate the canonical dataset from the corrected values:
- Rule must be stated in the delivery README (e.g., "module score ÷ 100, summed over policies valid in that province-year").
- Validity periods: start year = effective year (publication year unless text says otherwise); end year by type:
  - explicit term in title/body → term end year
  - annual task documents (work plans, notices) without end date → same year only (they are replaced next year)
  - institutional documents (regulations, plans, opinions) without end date → observation-period end, with evidence note
  - superseded documents → end = superseding document year (define the convention ONCE and apply uniformly — mixed conventions across rows are a classic error)
- Spot-check aggregation: hand-calculate 2-3 province-years and compare.
- Panel lags (if regression uses lagged stock): within-group lag only, see pitfalls.

## 8. Gate close

```text
formal_ready: true
blocking_reasons: []
```
plus: log entry, board update, SHA256 manifest rows for the aggregated table (source_check = FORMAL_AGGREGATED_GATE_OPEN).

## 9. Verification checklist (before declaring closed)

- [ ] All review rows have legal status values, reviewer, date
- [ ] P1 items all have individual notes
- [ ] Revised scores match between comparison table and written-back file (machine-check: 0 mismatches)
- [ ] No ID lost in merge (original count == written-back count)
- [ ] Validity: no missing start/end, no start > end, no title-term contradictions
- [ ] Aggregation spot-check passed
- [ ] Gate JSON flipped, manifest updated, CURRENT_STATE + PROJECT_LOG refreshed (derived views may follow later)
