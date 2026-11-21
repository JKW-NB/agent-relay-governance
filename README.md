# Agent Relay Governance (ARG V2)

用于长周期项目的文件化交接协议与 Agent Skill。多个 Agent 可以按顺序接手同一项目，通过 Git 和普通文件恢复进度、检查验收依据，并追溯关键决策。

ARG 的基本流程只依赖本地治理文件。需要查找分散的历史证据时，项目可以额外启用 OpenViking。

[快速开始](#快速开始) · [治理文件](#治理文件) · [OpenViking 接入](#可选接入-openviking) · [English overview](#english-overview)

## 快速开始

1. 克隆仓库。将其放到你的 Agent 支持的 Skill 目录，或在项目说明中明确让接手者读取本仓库的 [SKILL.md](SKILL.md)。
2. 从 [模板目录](assets/templates/) 复制 `AGENTS.template.md` 和 `CURRENT_STATE.template.yaml` 到项目根目录，分别命名为 `AGENTS.md` 和 `CURRENT_STATE.yaml`。填写当前任务、输入、输出、验收条件和下一步。按项目需要初始化日志、断点和决策文件。
3. 每次接手先读 `AGENTS.md` 和 `CURRENT_STATE.yaml`，再根据 `context.required` 和 `context.conditional` 加载所需材料。暂停、阻塞或移交时，用 `CHECKPOINT.md` 保存恢复现场。
4. 用仓库里的原生验证器检查项目。将示例中的两个路径换成实际位置。

```bash
git clone https://github.com/JKW-NB/agent-relay-governance.git
python path/to/agent-relay-governance/scripts/validate_governance.py --project-root path/to/your-project --check-hashes
```

验证器使用 Python 标准库，覆盖状态、依赖、验收记录和 SHA-256 清单等一致性检查。以命令输出的 `GOVERNANCE_VALIDATION = PASS` 或 `FAIL` 判断结果。规则细节见 [SKILL.md](SKILL.md)，旧项目升级步骤见 [V1 到 V2 迁移指南](references/migration-v1-to-v2.md)。

## 治理文件

| 文件 | 职责 |
|---|---|
| `AGENTS.md` | 项目规则、角色和交接要求 |
| `CURRENT_STATE.yaml` | 当前任务、状态、阻塞和下一步的权威记录 |
| `CHECKPOINT.md` | 暂停或交接时的恢复现场 |
| `PROJECT_LOG.md` | 追加式事件历史与验收证据 |
| `DECISIONS.md` | 决策、理由和冻结状态 |
| `LESSONS.md` | 可复用的项目经验和操作规则 |
| `PROGRESS_BOARD.md`、`STAGE_TABLE.md` | 供人查看的派生视图 |
| `DELIVERY_STATE.json` | 机器编码数据的人工复核与关闸状态 |

角色分为规划、执行、复核和审计，可以由不同模型承担。任务推进依据结构化验收条件，冻结决策的变更需要人工批准并留痕。数据交付细节见 [人工复核流程](references/human-review-workflow.md) 和 [归档规则](references/data-archiving.md)。

## 可选接入 OpenViking

OpenViking 是面向 AI Agent 的开源上下文数据库。它用类似文件系统的目录组织文档、记忆和技能，并支持在指定目录内按语义检索。了解项目和安装方式可访问 [OpenViking 官方 GitHub 仓库](https://github.com/volcengine/OpenViking)。

OpenViking 适用于接手时追查旧决策、复核依据或变更记录。启用后，Agent 先完成 ARG 要求的本地上下文读取，再按需检索历史证据。适配器会核对已登记的本地文件及其 SHA-256，并返回可以在原文定位的摘录、文件路径和行号。当前任务状态、冻结决策和验收仍由各自的 ARG 治理文件及流程决定。

1. 启动本机 OpenViking，将允许检索的历史资料副本导入项目专用范围。
2. 以 [配置样例](integrations/openviking/config.example.json) 为起点，填写本机地址、检索范围、来源路径和哈希。样例默认关闭，配置完成后由项目显式启用。
3. 在项目说明中记录配置位置。从仓库根目录运行下面的命令，按需替换路径和问题。

```bash
python integrations/openviking/retrieve.py --project-root path/to/your-project --config path/to/openviking.json "What evidence supported the previous decision?"
```

服务不可达或缺少可核验证据时，按 ARG 的本地流程处理。有必要证据才能推进的任务应记录阻塞。交接预检、操作者审阅和原生验证器的调用方式见 [集成说明](integrations/openviking/README.md)。

### 验证状态

本机已验证来源核验、服务不可达时的本地降级，以及操作者审阅后调用 ARG 原生验证器。以本仓库自身的真实工程记录做的一项交接试点中，纯本地与 OpenViking 路径均找到了目标证据，模型在两种路径上都未正确提出下一步。操作者随后核验原始报告并通过后续回归。现有结果支持把 OpenViking 用作可选的历史证据检索，真实长周期项目中的效率收益仍待验证。

## English overview

Agent Relay Governance (ARG) is a file-based protocol and Agent Skill for sequential handoffs. Start with [SKILL.md](SKILL.md) and the [project templates](assets/templates/). Read the project’s instructions and canonical state first, then load the evidence required by the active task. Use the native validator to check consistency before advancing the project.

[OpenViking integration](integrations/openviking/README.md) is opt-in. It retrieves historical excerpts and verifies them against registered local sources. ARG governance files retain authority over task state and decisions. The local workflow remains available when the service is unavailable.

## License

MIT
