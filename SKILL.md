---
name: agent-relay-governance
description: Lightweight file-driven model-agnostic governance protocol for long-horizon multi-agent projects. Use when: (1) multiple AI agents work sequentially on one project and need reliable cross-session handoff, (2) setting up project governance files (CURRENT_STATE.yaml, CHECKPOINT, PROJECT_LOG, DECISIONS, LESSONS, progress board, AGENTS.md), (3) designing task contracts with acceptance criteria for agent handoff, (4) resolving state conflicts between agents or files, (5) running human-review gate-close workflows for machine-encoded data, (6) validating governance state integrity with scripts/validate_governance.py, (7) organizing project files into human-facing vs machine-facing folders with SHA256 archiving. Triggers: 多agent串行接力, 跨会话交接, 项目治理, agent handoff, serial handoff, governance protocol, task contract, decision memory, checkpoint resume, state validation.
---

# Agent Relay Governance (V2)

A **file-driven, model-agnostic, Git-friendly** governance protocol for long-horizon multi-agent projects. It is a protocol, **not an agent runtime**: no orchestrator service, no framework dependency, no default parallel execution. Any model (Claude, Codex, opencode, GPT) can pick up the baton from any other, guided only by files.

## Invariants

```text
SERIAL HANDOFF        — one executor at a time
MODEL AGNOSTIC        — roles, not models
FILE DRIVEN           — files are the only state
NO AGENT FRAMEWORK    — works with any agent tool
AUDITABLE             — append-only log + hashes
RESUMABLE             — checkpoint = resume package
VERIFIABLE            — validate_governance.py + verify-before-PASS
HUMAN CAN OVERRIDE    — conflict arbitration ends at a human
```

## Memory model (who owns what)

Five files, five distinct jobs. **Each fact has exactly one authoritative owner** — never copy the same fact into two files.

| File | Role | Authoritative for |
|---|---|---|
| `CURRENT_STATE.yaml` | **Working state** | where we are now: workstream, stage, task contract, blockers, next action, context to load |
| `CHECKPOINT.md` | **Resume memory** | how to restore the scene; written only on PAUSED / HOLD / handoff / interruption |
| `PROJECT_LOG.md` | **Episodic history** | what happened (append-only; corrections via `CORRECTION` entries, never edits) |
| `DECISIONS.md` | **Decision memory** | why decisions were made (ACTIVE / FROZEN / SUPERSEDED) |
| `LESSONS.md` | **Procedural memory** | how to do it better next time (project-level failure patterns) |

Derived human-facing views (`PROGRESS_BOARD`, `STAGE_TABLE`) carry a `derived_from: CURRENT_STATE.yaml @ <timestamp>` header. They may lag; on conflict, **CURRENT_STATE wins**.

## Conflict precedence (when files disagree)

```text
1. Executable / file / data evidence wins
2. ACTIVE or FROZEN decision in DECISIONS.md wins
3. Otherwise → HOLD with blocker {type: STATE_CONFLICT | DECISION_CONFLICT | EVIDENCE_CONFLICT}
   → human arbitration
```

Never resolve fact conflicts by majority vote, "looks more reasonable", or silent overwrite.

## State vocabulary

```text
NOT_STARTED / READY / IN_PROGRESS / PAUSED / PASS / HOLD / LOCKED
```

Conflicts are NOT new states — they are expressed as a blocker with a conflict type. Keep the state machine small.

## Context loading protocol

Every agent starts by reading exactly two files:

1. `AGENTS.md`
2. `CURRENT_STATE.yaml`

Then loads more **only as the state directs** — via `context.required` and `context.conditional` in CURRENT_STATE:

```yaml
context:
  required: ["path/to/stage_spec.md"]        # always load these next
  conditional:
    - when: "status in [PAUSED, HOLD]"
      load: ["CHECKPOINT.md"]                 # resume memory
    - when: "task involves frozen design"
      load: ["DECISIONS.md"]                  # decision memory
    - when: "new agent, first contact"
      load: ["PROJECT_LOG.md"]                # last N events for background
  do_not_preload: ["PROGRESS_BOARD.md"]       # human views: load only if asked
```

Never dump the whole log/board/history into context by default.

## Task contract (inside CURRENT_STATE.yaml)

The handoff unit is a **task contract**, not a free-text note. Next agent must know goal, inputs, outputs, dependencies, and done-criteria:

```yaml
current:
  workstream: "G3"
  stage: "05"
  task:
    id: "T-05-01"
    goal: "..."
    role: "EXECUTOR"          # PLANNER | EXECUTOR | REVIEWER | AUDITOR
    status: "IN_PROGRESS"
    depends_on: ["T-04-01"]
    inputs: ["data/input.dta"]
    outputs: ["out/result.csv"]
    acceptance_criteria: ["N==108", "wild p < 0.05"]
    attempt: 1
    max_attempts: 3
    blocker: null             # or {type, detail}
    last_failure: null
    recovery_action: null
    escalation: "HOLD if attempt > max_attempts"
    exact_next_action: "write Shapley do-file per stage spec"
```

**Roles are logical, not models.** PLANNER / EXECUTOR / REVIEWER / AUDITOR can each be any agent.

## Retry / recovery rules

- `attempt` increments on each failed run; log each failure with evidence.
- Never repeat the identical failing action more than `max_attempts` times.
- On exceeding: stop, set `status: HOLD`, write CHECKPOINT, log escalation.
- `recovery_action` must state what to do differently next time.

## Serial handoff protocol

- **One executor at a time.** A new executor must find `status ∈ {PAUSED, HOLD}` plus a CHECKPOINT, or an explicit handoff entry in PROJECT_LOG; otherwise it must not take over silently.
- Never re-litigate FROZEN decisions; read DECISIONS.md first.
- Pause = write CHECKPOINT (resume package) + set PAUSED + log.
- Complete = run verification, then write PASS + log with evidence. **Verify before PASS, never after.**
- Verify governance integrity before and after significant work:
  ```bash
  python scripts/validate_governance.py
  ```

## Human review / gate-close (machine-encoded data)

Machine-encoded data (LLM scoring, coding, classification) passes a gate before entering analysis. Full workflow: [references/human-review-workflow.md](references/human-review-workflow.md). Essentials: delivery-state JSON with `blocking_reasons`; P1 items get individual notes; missing evidence → no inference; write-back to originals by ID; re-aggregate; flip gate only when blockers are empty.

## Data archiving

Copy never move; SHA256 manifest; UTF-8 with BOM for CSVs. Details: [references/data-archiving.md](references/data-archiving.md).

## Skill-level vs project-level lessons

- `references/pitfalls.md` = **skill-level** lessons (applies to every project: PowerShell `-f` trap, panel-lag leakage, BOM, hash drift).
- `LESSONS.md` = **project-level** lessons (specific to one project's domain or data).

## Migration from V1

Existing V1 projects keep working; V1's five-place sync maps onto V2's memory model. See [references/migration-v1-to-v2.md](references/migration-v1-to-v2.md). Progressive compatibility, no forced rebuild.

## Templates & validator

- Governance file templates: [assets/templates/](assets/templates/) — AGENTS, CURRENT_STATE (schema v2), CHECKPOINT, PROJECT_LOG, STAGE_TABLE, PROGRESS_BOARD, DECISIONS, LESSONS, DELIVERY_STATE.
- Machine validator: `scripts/validate_governance.py` (pure stdlib, no pip install). Run it; fix what it reports; never let it auto-repair state silently.
