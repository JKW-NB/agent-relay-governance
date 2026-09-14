# AGENTS.md：项目名（模板 V2）

本目录是[项目性质一句话]。所有 LLM/Agent/自动化执行者必须遵守本文件。

## 0. 治理协议（全库生效）

任何 Agent 开始任务前：

1. 必读两个文件：本 `AGENTS.md` → `_AI交接文件/CURRENT_STATE.yaml`。
2. 然后按 CURRENT_STATE 的 `context.required` / `context.conditional` 决定继续读什么（CHECKPOINT / DECISIONS / PROJECT_LOG / 阶段说明）。
3. 不得仅凭聊天上下文推断进度；一次一个执行者；从 CURRENT_STATE 与 CHECKPOINT 续接，不另建重复文件。

> `AGENTS.md` 必须留在根目录（工具自动发现机制）。机器交接文件在 `_AI交接文件/`。

- **记忆模型**：CURRENT_STATE=现在在哪；CHECKPOINT=怎么恢复；PROJECT_LOG=发生过什么；DECISIONS=为什么；LESSONS=怎么做。同一事实只有一个 authoritative owner。
- **冲突裁决**：证据 > DECISIONS 中 ACTIVE/FROZEN 决策 > HOLD 人工仲裁。禁止投票/静默覆盖。
- **状态值**：`NOT_STARTED / READY / IN_PROGRESS / PAUSED / PASS / HOLD / LOCKED`。
- **暂停**：写 CHECKPOINT + CURRENT_STATE 置 PAUSED + PROJECT_LOG 追加。
- **完成**：先验证（含 `python scripts/validate_governance.py`）再写 PASS + 带证据的 END 日志。

## 1. 文档权威层级

- 历史稿（`_历史稿归档/`）禁止作为当前口径。
- 当前核心文件：[列出]。

## 2. 冻结决策

见 `DECISIONS.md` 中 status=FROZEN 的条目，不得擅自更改；推翻需人工批准。

## 3. 文件写入边界

- 代码/日志/结果写入对应阶段目录；权威输入 READ_ONLY_SOURCE。
- 数据归档：复制不移动、SHA256 清单、CSV 用 UTF-8 BOM。

## 4. 子项目治理（若有嵌套）

- 子项目目录有嵌套 AGENTS.md；进入该目录按嵌套协议 + 其 CURRENT_STATE 续接。
