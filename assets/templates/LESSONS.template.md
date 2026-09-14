# LESSONS.md — Procedural Memory（下次怎么做）

> 项目运行中踩过的坑，形成可复用规则。与 PROJECT_LOG（发生过什么）、DECISIONS（为什么决定）、CURRENT_STATE（现在在哪）、CHECKPOINT（怎么恢复）严格分工。
> Skill 级通用坑在 `references/pitfalls.md`；本文件只记**本项目特有**的坑。

---

## L-001

```text
failure_pattern     : <什么情况下会踩>
root_cause          : <根本原因>
prevention_rule     : <下次如何避免>
detection_method    : <如何第一时间发现>
recovery_procedure  : <踩了怎么恢复>
date                : YYYY-MM-DD
```

## L-002

```text
failure_pattern     : <…>
root_cause          : <…>
prevention_rule     : <…>
detection_method    : <…>
recovery_procedure  : <…>
date                : YYYY-MM-DD
```

---

## 使用规则

1. 编号 L-NNN 递增；只追加不修改历史条目。
2. 同一坑重复踩时：更新对应条目的 prevention_rule 并注明"重复发生 N 次"，而不是新建条目。
3. 新 Agent 接手时，按 CURRENT_STATE 的 context.conditional 决定是否读本文件（涉及踩坑领域时读）。
