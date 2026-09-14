# DECISIONS.md — Decision Memory（为什么这么决定）

> 记录已形成的设计/方法决策。Agent 不得重新讨论 FROZEN 决策；要推翻须走人工流程并在 PROJECT_LOG 留痕。
> 状态：ACTIVE（现行有效）/ FROZEN（冻结，改动需人工批准）/ SUPERSEDED（被新决策取代，保留可追溯）。

---

## D-001

```text
scope               : <决策覆盖范围：工作流/阶段/变量/方法>
decision            : <决定内容>
alternatives        : <被否决的方案及原因>
reason              : <采用理由>
evidence            : <支撑证据：数据/文献/验证结果>
status              : FROZEN
supersedes          : <无 / D-000>
date                : YYYY-MM-DD
```

## D-002

```text
scope               : <…>
decision            : <…>
alternatives        : <…>
reason              : <…>
evidence            : <…>
status              : ACTIVE
supersedes          : <无>
date                : YYYY-MM-DD
```

---

## 使用规则

1. 每个决策独立编号 D-NNN，按序递增。
2. FROZEN 决策被推翻时：旧条目 status 改 SUPERSEDED（不删除），新增条目 supersedes 指向它；同时在 PROJECT_LOG 记录推翻原因与人工批准人。
3. 冲突裁决优先级：证据 > FROZEN/ACTIVE 决策 > 人工仲裁（见 SKILL.md Conflict precedence）。
4. Agent 每次涉及某决策范围的工作前，先查本文件是否存在相关 ACTIVE/FROZEN 条目。
