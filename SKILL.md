---
name: multi-agent-serial-handoff
description: Multi-agent serial handoff governance for research/documentation projects. Use when: (1) setting up cross-session/cross-agent project state tracking so any AI agent can resume work without re-asking the human, (2) multiple AI agents (Claude/Codex/opencode/GPT etc.) work sequentially on one project and need checkpoint/log/board/YAML state sync, (3) creating governance files like CURRENT_STATE.yaml, CHECKPOINT files, PROJECT_LOG, stage tables, progress boards, AGENTS.md, (4) running human-review workflows for machine-encoded data (LLM scoring/coding) with gate-close aggregation, (5) organizing project files into human-facing vs AI-facing folders with SHA256 archiving. Triggers: 多agent串行接力, 跨会话交接, 项目治理, 状态同步, 断点续接, 人工复核关闸, agent handoff protocol, project governance, checkpoint resume, serial handoff.
---

# Multi-Agent Serial Handoff Governance

Establish and run a governance layer that lets multiple AI agents work **sequentially** on one project without losing state. Proven in a real master's-thesis research project (Stata/data/paper workstreams with Claude, Codex, opencode taking turns).

## When this workflow applies

- A project (thesis, research repo, long documentation task) is worked on by more than one AI agent or session, one at a time.
- You need "any agent can pick up where the last one stopped" without re-asking the human.
- Machine-encoded data (LLM scoring, coding, classification) must pass a human-review gate before being used in analysis.

## Core architecture: two-tier governance

```text
Root level (workstreams G0-G6)          Nested level (stages 00-09, per sub-project)
├─ AGENTS.md  (protocol, stays at root)   ├─ AGENTS.md (nested protocol)
├─ _AI交接文件/ (machine state folder)     ├─ CURRENT_STATE.yaml
│   ├─ CURRENT_STATE.yaml                  ├─ JKai_项目进度看板.md
│   ├─ 项目阶段状态总表.md                   ├─ PROJECT_LOG_工作日志.md
│   ├─ CHECKPOINT_项目断点.md               └─ per-stage CHECKPOINT + README
│   └─ PROJECT_LOG_工作日志.md
├─ JKai_论文总进度看板.md (human board)
└─ README_文件导航.md (file navigation)
```

**Tier split rule**: root files record workstream-granularity pointers only; nested files record stage-granularity detail. The two tiers never duplicate content. Root log gets one summary line when a stage starts/completes/blocks; nested log gets full audit detail.

**Non-negotiable**: `AGENTS.md` must stay at project root (tool auto-discovery finds it there). Machine state files go in `_AI交接文件/` (or similar), human-facing files stay visible. Old drafts go to `_历史稿归档/` with `[!WARNING]` markers.

## State machine

Allowed status values (single vocabulary everywhere):

```text
NOT_STARTED / READY / IN_PROGRESS / PAUSED / PASS / HOLD / LOCKED
```

## Serial handoff protocol (mandatory reading order)

1. Every agent, before ANY task, reads in order: `AGENTS.md` → `CURRENT_STATE.yaml` → progress board → project log (tail) → CHECKPOINT → stage table. If the task falls in a nested directory, continue with the nested protocol's reading order.
2. **One executor at a time.** Resume from checkpoint; never create duplicate code or re-choose models already frozen.
3. Never infer progress from chat context alone.
4. Pausing requires writing a CHECKPOINT (with exact next action: file/section/command) and setting status `PAUSED`.
5. Completion requires verifying first, then writing `PASS` — never print PASS early.

## The 5-place sync rule (non-negotiable)

Every state change updates ALL five:

```text
1. CURRENT_STATE.yaml        (machine-readable current pointer only)
2. CHECKPOINT_项目断点.md      (active checkpoint)
3. 阶段状态总表.md             (stage table)
4. PROJECT_LOG_工作日志.md     (append-only; corrections via CORRECTION entry)
5. Progress board (human)     (plain language, no command dumps)
```

**Missing even one = incomplete work.** This is the #1 failure mode; verify all 5 before declaring anything done. See [references/pitfalls.md](references/pitfalls.md).

## Project bootstrap (G0)

When setting up governance for a new project:

1. Create root `AGENTS.md` with: reading order, state vocabulary, sync rule, freeze rules, concept red lines, data rules.
2. Create `_AI交接文件/` with the 4 machine files from [assets/templates/](assets/templates/).
3. Create human board + file navigation README (which file is for whom: human vs AI).
4. Define workstreams (G0-G6 style) and nested sub-project protocol if needed.
5. Log the bootstrap in the project log.

## Task execution loop

```text
READ (5 files) → verify checkpoint matches disk → append START to log
→ do work (write to the correct stage directory, never the frozen source)
→ verify (run validation, check N/keys/hashes)
→ append END + update all 5 places → report only with evidence
```

## Human review + gate-close workflow (for machine-encoded data)

When LLM/machine produces scored or coded data that enters analysis:

1. Machine output ships as `PENDING` with a **delivery state JSON** listing `blocking_reasons`.
2. Human reviews flagged items first (priority P1 = evidence/document problems; P2 = full-score audit); each item gets an individual note, never a template sentence for risk items.
3. Missing evidence → conservative coding ("no evidence, no inference"), never guess.
4. Reviewer marks: `ACCEPT_AS_CODED` / `REVISED_AND_ACCEPTED` / `EXCLUDE`.
5. **Write-back**: review results are merged into the ORIGINAL files by ID; derived work files stay separate.
6. Re-aggregate the final dataset with the corrected values; spot-check against hand calculation.
7. Close the gate: flip `formal_ready: true`, empty `blocking_reasons`, log + board + hash updates.

Full workflow: [references/human-review-workflow.md](references/human-review-workflow.md)

## Data archiving rules

- Copy, never move original sources; new versions get date/version suffix (never overwrite by filename alone).
- Every archived file gets a row in a SHA256 manifest (`文件清单_SHA256.csv`): relative_path, source_path, bytes, modified_time, sha256, source_check.
- After ANY batch of file work, audit: re-hash changed files, add missing rows, verify manifest vs disk 100%.
- CSV for Excel compatibility: UTF-8 **with BOM**.

Details + manifest template: [references/data-archiving.md](references/data-archiving.md)

## Practical pitfalls (hard-won lessons)

PowerShell `-f` string formatting can throw "Index out of range" on seemingly valid 8-arg calls (use string concatenation instead); province-level lags must be within-group (`by province: gen l1 = x[_n-1]`), never whole-table shift; check BOM on generated CSVs; re-hash files after content edits. Full list: [references/pitfalls.md](references/pitfalls.md)

## Templates

All 6 governance files as fill-in templates: [assets/templates/](assets/templates/) — `CURRENT_STATE.template.yaml`, `CHECKPOINT.template.md`, `STAGE_TABLE.template.md`, `PROJECT_LOG.template.md`, `PROGRESS_BOARD.template.md`, `AGENTS.template.md`, `DELIVERY_STATE.template.json`.
