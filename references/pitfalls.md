# Pitfalls (hard-won lessons from real multi-agent projects)

## Table of contents
1. State sync omissions
2. PowerShell formatting traps
3. Panel lag errors
4. Encoding traps
5. Hash drift after edits
6. Merge/write-back ID losses
7. Gate-close theater
8. Review theater

## 1. State sync omissions (most common failure)

Symptom: work is done and logged, but other state files still say the old thing (e.g., "pending human review" after the review closed).

- The 5-place sync is the completion standard, not a nice-to-have. After finishing, grep all 5 files for stale phrases (task name, "pending", "待复核") and update every hit.
- A human asking "is everything updated?" usually means one of the 5 places was missed. Verify with grep, not memory.

## 2. PowerShell `-f` formatting trap

```powershell
# Sometimes throws "Index (zero based) must be greater than or equal to zero..."
$lines.Add('"{0}",{1},{2},{3},{4},{5},{6},{7}' -f $a, $b, $c, $d, $e, $f, $g, $h)
```

Even with 8 placeholders and 8 args, PS 5.1 intermittently throws. AND the exception can silently drop the line being written (file ends up missing a row you thought you wrote).

- **Rule: use string concatenation for CSV/JSON building in PowerShell 5.1**, never `-f` with many args.
- After writing any generated file, verify row count (expected = N + 1 header).

## 3. Panel lag errors (cross-unit leakage)

Symptom: lagged variables look fine in aggregate but are wrong per unit.

- Lag must be within-group: `by unit: gen l1 = x[_n-1]` or group-by-then-sort-then-lag.
- Whole-table shift (`gen l1 = x[_n-1]` on sorted multi-unit panel) leaks the previous unit's value into each unit's first year.
- Detection: check `lag(unit_i, year_t) == value(unit_i, year_t-1)` for all rows; report matches/total (e.g., "155/155 ok"). Also test the wrong pattern (`lag == previous row's value`) to confirm the bug when matches are ~100%.
- Cross-unit leakage was the actual root cause of a "153/155 mismatch" audit finding — the numbers in the audit report exactly matched the within-group check failure count.

## 4. Encoding traps

- BOM-less UTF-8 CSV opened in Excel (Chinese locale) → mojibake. Always UTF-8 with BOM for deliverables.
- Terminal display mojibake ≠ file corruption: verify file bytes, not console output. Read the first bytes / use a proper reader before "fixing" a file that is actually fine.
- Windows path transport to shells can corrupt Chinese characters intermittently; if a path suddenly fails, re-test with a shorter command or copy the file to an ASCII temp path first.

## 5. Hash drift after edits

Symptom: manifest says hash X, disk file is hash Y.

- Any edit to an archived file (write-back, encoding fix, BOM add) invalidates its manifest row. Re-hash immediately.
- The final audit compares manifest vs disk for every row — a "1 mismatch" report usually means an encoding fix you forgot to re-hash.

## 6. Merge/write-back ID losses

Symptom: after merging review results into originals, some rows vanish.

- Merge by stable ID; verify counts before/after (original N == written-back N, 0 missing, 0 extra).
- A formatting exception mid-write can drop exactly the row being written — always verify final row counts.

## 7. Gate-close theater

Symptom: `formal_ready: true` but blockers not actually cleared (or vice versa).

- The gate JSON is the single source of truth for "can this data enter regression". Flipping it without verifying each blocker is theater.
- Gate-close checklist lives in human-review-workflow.md §9 — run it.

## 8. Review theater

Symptom: 100% of flagged items marked ACCEPT_AS_CODED with identical template notes.

- If the machine flagged items for missing attachments, a uniform "all 17 codes verified against original text" note is contradictory — the attachment was missing.
- P1 items (missing evidence, low confidence) require individual notes; template notes are only acceptable for low-risk P2 full-score confirmations.
- Two-pass review (junior agent proposes, human disposes) with explicit "待终审" marking prevents rubber-stamping.
