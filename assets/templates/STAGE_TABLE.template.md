# 项目阶段状态总表（derived view）

> **Derived view**：本表内容派生自 `CURRENT_STATE.yaml`（derived_from: CURRENT_STATE.yaml @ YYYY-MM-DD）。
> 允许滞后；**冲突时以 CURRENT_STATE.yaml 为准**。本表不承担权威状态，仅供人快速浏览。

| 工作流 | 状态 | 启动条件 | 完成标志 | 管辖 |
|---|---|---|---|---|
| G0 项目治理与交接层 | PASS | 根 AGENTS.md 生效 | validator 通过 | 根目录协议 |
| G3 子项目 | IN_PROGRESS | 启动条件 | 完成标志 | 嵌套协议 |

## 当前指针

```text
（从 CURRENT_STATE.yaml 摘录，非权威）
CURRENT_WORKSTREAM = ...
CURRENT_TASK       = ...
```

## 维护规则

- 状态变化后可以滞后更新本表（给人看），但 CURRENT_STATE.yaml 与 PROJECT_LOG 必须即时更新。
- 若本表与 CURRENT_STATE 不一致且造成困惑：删掉本表对应行或标注"以 CURRENT_STATE 为准"，而不是修改 CURRENT_STATE 来迁就本表。
