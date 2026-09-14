# Migration: V1 → V2

## Table of contents
1. Do I have to migrate?
2. What changed
3. File mapping
4. Field changes
5. Minimal migration steps
6. Running V1 and V2 side by side

## 1. Do I have to migrate?

**No.** V1 projects keep working. V2 is progressive:

- V2 keeps the same file names and locations (except new DECISIONS.md / LESSONS.md / scripts/).
- V2 only *changes responsibilities*, not existence. An old project is valid-but-lagging until you choose to migrate.
- The validator accepts V1-shaped files (missing V2 fields produce warnings, not failures) — see §6.

## 2. What changed

| Concern | V1 | V2 |
|---|---|---|
| Current state | scattered across 5 files | `CURRENT_STATE.yaml` is the single canonical "now" |
| Five-place sync | every state change must touch 5 files | write CURRENT_STATE + PROJECT_LOG always; CHECKPOINT only on pause/hold/handoff; boards are derived views |
| Task description | `exact_next_action` free text | structured `current.task` contract: goal, role, inputs, outputs, acceptance_criteria, depends_on, attempt/max_attempts, blocker, escalation |
| Decisions | embedded in log/notes | `DECISIONS.md` with ACTIVE/FROZEN/SUPERSEDED |
| Project lessons | mixed into log | `LESSONS.md` (skill-level stays in references/pitfalls.md) |
| Conflict resolution | implicit | explicit precedence: evidence > frozen decision > HOLD + human |
| Roles | implied per-model | logical roles PLANNER/EXECUTOR/REVIEWER/AUDITOR, model-agnostic |
| Retry | ad-hoc | attempt/max_attempts/escalation in task contract |
| Validation | manual | `scripts/validate_governance.py` |
| Context loading | "read everything in order" | AGENTS.md + CURRENT_STATE.yaml, then context-directed loading |

## 3. File mapping

| V1 file | V2 role | Kept? |
|---|---|---|
| `AGENTS.md` | protocol entry | kept, updated |
| `CURRENT_STATE.yaml` | **canonical working state** | kept, schema v2 |
| `CHECKPOINT_项目断点.md` | **resume package** (pause/hold/handoff only) | kept, slimmer |
| `PROJECT_LOG_工作日志.md` | **episodic history** (append-only) | kept |
| `项目阶段状态总表.md` | derived view | kept, marked derived |
| `进度看板.md` | derived view (human) | kept, marked derived |
| — | `DECISIONS.md` | **new** |
| — | `LESSONS.md` | **new** |
| — | `scripts/validate_governance.py` | **new** |

## 4. Field changes

`CURRENT_STATE.yaml`:
- added: `current.task` contract block (id/goal/role/status/depends_on/inputs/outputs/acceptance_criteria/attempt/max_attempts/blocker/last_failure/recovery_action/escalation/exact_next_action)
- added: `context` block (required/conditional/do_not_preload)
- kept: `current.workstream`, `current.stage`, `blockers`

`CHECKPOINT`:
- unchanged content shape, but now written **only** for PAUSED/HOLD/handoff — ordinary progress no longer requires editing it.

## 5. Minimal migration steps

1. Add `DECISIONS.md` (empty template) and `LESSONS.md` (empty template).
2. Copy `scripts/validate_governance.py` from this repo.
3. In `CURRENT_STATE.yaml`: bump `schema_version: 2`, add a `current.task` block for the active task, add a `context` block.
4. Add `derived_from: CURRENT_STATE.yaml @ <date>` headers to boards/stage tables.
5. Stop editing CHECKPOINT on every state change; write it only on pause/hold/handoff.
6. Run `python scripts/validate_governance.py` and fix what it reports.

## 6. Running V1 and V2 side by side

The validator distinguishes:
- **errors**: both V1 and V2 violations (illegal status, PASS without evidence, blocker+PASS conflict).
- **warnings**: missing V2-only structures (no task contract, no context block, no DECISIONS.md) — old V1 projects get warnings, not failures, until migrated.

GOVERNANCE_VALIDATION = PASS requires no errors; warnings are reported and count as "PASS with warnings".
