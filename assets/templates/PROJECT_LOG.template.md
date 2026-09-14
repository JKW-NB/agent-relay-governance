# PROJECT_LOG.md — Episodic History（发生过什么）

> 本文件是 **canonical event history**：append-only，记录已发生的事件。
> 不承担"当前状态"（那是 CURRENT_STATE.yaml 的职责）。纠错用 `CORRECTION` 追加，不删改历史。

---

## 日志条目格式

```text
## YYYY-MM-DD HH:MM | ROLE | TASK_ID | START / RESUME / END / CHECKPOINT / CORRECTION

**事件：**
- 可核验的操作与证据（文件、哈希、数字、验证结果）。

**状态：**
\`\`\`text
<简短状态指针：本事件后 CURRENT_STATE 变成了什么>
\`\`\`
```

## 规则

1. 每个任务：START 开始、END 结束；END 必须含验证证据（跑了什么、结果如何）。
2. PAUSED/HOLD 写 CHECKPOINT 条目并指向 CHECKPOINT.md。
3. 形成决策 → 记事件 + 写 DECISIONS.md；踩坑 → 记事件 + 写 LESSONS.md。
4. 状态变化 → 记事件 + 更新 CURRENT_STATE.yaml（本日志不替代 CURRENT_STATE）。
5. 纠错：追加 `CORRECTION` 条目说明原记录何处有误，不改原文。

*日志尾部即最新记录。*
