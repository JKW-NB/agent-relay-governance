# Agent Relay Governance (V2)

> 轻量、文件驱动、模型无关、Git 友好的 Long-horizon Agent Governance Protocol。
> A file-driven, model-agnostic governance protocol for long-horizon multi-agent projects — a protocol, **not** an agent runtime.

[English](#what-it-is) | [中文](#它是什么)

## What it is

When multiple AI agents work **sequentially** on one project, four things go wrong: state loss between handoffs, drift (each agent re-does prior work), unverifiable machine-encoded data entering analysis, and untraceable files. This repository encodes a battle-tested protocol that prevents all four — extracted from a real master's-thesis project where three agent platforms took turns for months without losing continuity.

**It is not AutoGen / CrewAI / LangGraph.** No orchestrator service, no framework dependency, no default parallelism. Serial handoff only. Any agent tool (Claude Code, Codex, opencode, GPT) can use it, because all state lives in plain files.

## 它是什么

多个 AI Agent 顺序协同一个项目时，四大风险：交接丢状态、各干各的、机器编码数据未经人工复核进分析、文件无可追溯。本仓库是一套实战验证过的治理协议，解决全部四个问题。它不是多 Agent 编排框架，不依赖任何外部框架，所有状态都在普通文件里，任何 agent 工具都能用。

## Core design (V2)

| 设计 | 内容 |
|---|---|
| **Memory model** | `CURRENT_STATE`=现在在哪；`CHECKPOINT`=怎么恢复；`PROJECT_LOG`=发生过什么；`DECISIONS`=为什么；`LESSONS`=怎么做。每种事实只有一个权威 owner。 |
| **Single source of truth** | 状态只写在 CURRENT_STATE.yaml；日志 append-only；看板/状态总表是 derived views（可滞后，冲突时以 CURRENT_STATE 为准）。 |
| **Task contract** | 交接单元是结构化任务契约：goal / role / inputs / outputs / acceptance_criteria / depends_on / attempt / max_attempts / blocker / next_action。 |
| **Selective context loading** | Agent 只先读 AGENTS.md + CURRENT_STATE.yaml，然后按 context.required/conditional 按需加载，不预载全部历史。 |
| **Conflict resolution** | 证据 > FROZEN 决策 > HOLD 人工仲裁。禁止投票、禁止静默覆盖。 |
| **Roles, not models** | PLANNER / EXECUTOR / REVIEWER / AUDITOR 是逻辑角色，任何模型都能承担。 |
| **Verifiable** | `python scripts/validate_governance.py` 检查状态机、任务契约、依赖、验证证据、冻结决策、SHA256 等 12 类一致性。 |

## Install

```bash
git clone https://github.com/JKW-NB/agent-relay-governance.git \
  ~/.config/opencode/skills/agent-relay-governance
# or ~/.claude/skills/agent-relay-governance
```

## Structure

```
├── SKILL.md                      # Core protocol (triggers: 多agent串行接力 / agent handoff / governance ...)
├── scripts/
│   └── validate_governance.py    # Machine validator (pure stdlib, no pip)
├── references/
│   ├── human-review-workflow.md  # Machine-encoded data → human review → gate close
│   ├── data-archiving.md         # SHA256 manifest maintenance
│   ├── pitfalls.md               # Skill-level lessons (8 failure modes)
│   └── migration-v1-to-v2.md     # V1 → V2 compatibility guide
└── assets/templates/             # 9 fill-in governance file templates
    ├── AGENTS.template.md
    ├── CURRENT_STATE.template.yaml   (schema v2: task contract + context loading)
    ├── CHECKPOINT.template.md        (resume package)
    ├── PROJECT_LOG.template.md       (append-only event history)
    ├── DECISIONS.template.md         (decision memory)
    ├── LESSONS.template.md           (procedural memory)
    ├── STAGE_TABLE.template.md       (derived view)
    ├── PROGRESS_BOARD.template.md    (derived view, human-facing)
    └── DELIVERY_STATE.template.json  (gate-close status)
```

## Quick validation

```bash
cd your-project
python path/to/scripts/validate_governance.py --check-hashes
```

Expect `GOVERNANCE_VALIDATION = PASS` (warnings allowed, errors fail).

## Invariants

```text
SERIAL HANDOFF · MODEL AGNOSTIC · FILE DRIVEN · NO AGENT FRAMEWORK
AUDITABLE · RESUMABLE · VERIFIABLE · HUMAN CAN OVERRIDE
```

## License

MIT
