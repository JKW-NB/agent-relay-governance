# Agent Relay Governance

> 多 Agent 串行接力治理协议 —— 让多个 AI Agent 在同一个项目上"接力跑"，不丢状态、可审计、可交接。
> A serial-handoff governance protocol for multi-agent collaboration: any agent can pick up where the last one stopped — with full auditability.

[English](#what-it-solves) | [中文](#它解决什么)

## What it solves

When multiple AI agents (Claude Code, Codex, opencode, etc.) work **sequentially** on one project, the biggest risks are:

1. **State loss** — the next agent doesn't know what the previous one did
2. **Drift** — each agent re-does or contradicts prior work
3. **Unverifiable data** — machine-encoded data enters analysis without human review
4. **Untraceable files** — nobody knows which file is canonical

This repository is a **Claude Code / opencode skill** that encodes a battle-tested governance protocol: two-tier state management, a 5-place sync rule, serial handoff discipline, human-review gate-close workflow, and SHA256 archiving. It was extracted from a real master's thesis research project where three different agent platforms took turns over months without losing continuity.

## 它解决什么

多个 AI Agent 顺序协同一个项目时，最大的风险是：状态丢失、各干各的、机器编码的数据未经人工复核就进分析、文件无可追溯。本仓库是一套经过实战验证的治理协议 skill——双层状态管理、5 处同步、串行接力纪律、人工复核关闸流程、SHA256 归档。

## Install

```bash
# clone into your skills directory
git clone https://github.com/<your-account>/agent-relay-governance.git \
  ~/.config/opencode/skills/agent-relay-governance
# or for Claude Code
git clone https://github.com/<your-account>/agent-relay-governance.git \
  ~/.claude/skills/agent-relay-governance
```

## Structure

```
├── SKILL.md                      # Core protocol (triggers on "多agent串行接力" / "agent handoff" / ...)
├── references/
│   ├── human-review-workflow.md  # Machine-encoded data → human review → gate close
│   ├── data-archiving.md         # SHA256 manifest maintenance
│   └── pitfalls.md               # 8 failure modes learned the hard way
└── assets/templates/             # 7 fill-in governance file templates
    ├── AGENTS.template.md
    ├── CURRENT_STATE.template.yaml
    ├── CHECKPOINT.template.md
    ├── PROJECT_LOG.template.md
    ├── STAGE_TABLE.template.md
    ├── PROGRESS_BOARD.template.md
    └── DELIVERY_STATE.template.json
```

## Core rules at a glance

| Rule | Content |
|---|---|
| 串行接力 | One executor at a time; resume from checkpoint; never re-decide frozen designs |
| 5-place sync | Every state change updates: YAML state + checkpoint + stage table + log + human board. Missing one = incomplete. |
| 状态机 | `NOT_STARTED / READY / IN_PROGRESS / PAUSED / PASS / HOLD / LOCKED` |
| 人工复核 | P1 items get individual notes; missing evidence → no inference; gate JSON blocks regression until blockers are empty |
| 数据归档 | Copy never move; SHA256 manifest; verify manifest vs disk 100% after every batch |

## License

MIT
