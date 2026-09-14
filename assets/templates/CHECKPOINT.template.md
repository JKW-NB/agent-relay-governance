# CHECKPOINT.md — Resume Package（恢复现场用）

> 本文件是 **resume memory**：只在 PAUSED / HOLD / agent handoff / session handoff / 中断 时生成或更新。
> 普通状态变化**不需要**同步本文件（那是 V1 的负担）。恢复时以本文件为准恢复现场，
> 若与 CURRENT_STATE.yaml 冲突，以 CURRENT_STATE 为准并记入 PROJECT_LOG。

```text
状态               : PAUSED / HOLD
执行者             : <role + any model>
更新时间           : YYYY-MM-DD HH:MM
任务               : T-05-01 <一句话>
暂停原因           : <具体原因 / blocker>

现场快照           :
  - 关键变量/数据状态（版本、路径、哈希如有）
  - 内存中的临时结论（防止丢失）

已完成步骤         :
  - <可核验步骤>

未完成步骤         :
  - <剩余步骤>

下一步准确操作     : <具体到文件/命令，接手者照做即可>

恢复后必读         :
  - <接手者除了 AGENTS.md + CURRENT_STATE.yaml 还要读什么>

阻塞项             : <无 / 具体阻塞与解除条件>
```

恢复流程：读本文件 → 对照 CURRENT_STATE.yaml（不一致以 CURRENT_STATE 为准，记 PROJECT_LOG）→ 按"下一步准确操作"继续。
