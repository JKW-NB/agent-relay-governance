# ARG × OpenViking POC 阶段记录

## 已验证的路径

1. 本地事项别名确定查询指向。当前样例支持单事项查询。
2. OpenViking 在隔离范围内召回证据。事项明确且首条候选不匹配时，可将上限从 1 扩至 3，最多重试一次。
3. 用本地事项 ID 校验候选归属，再读取该事项及记录类型的结构化历史。
4. 按查询时点和显式替代关系判定有效、撤销、缺少证据或冲突。保留实际记录 ID 作为来源。

## 实测

- 初始检索的两道正例均召回两份预期证据，来源正文与本地样例相符。
- 扩展生成评测中 G0 与 G1 均完整答对 4/9。逐字引文核验无法单独排除角色混淆和无依据结论。
- 三类固定格式记录经程序提取后，有直接证据 3/3 正确放行，无直接证据 3/3 拒答。
- 生命周期解析 9/9 通过，覆盖改派、撤销、更正、缺失前序与分叉。
- 自然语言压力测试共 13 条。启用有界重试后，8 条返回正确状态，5 条要求明确事项。备份记录在第一轮候选中缺失，扩到前三条后排第三并被选中。

## 本机复跑

Docker Desktop、arg-openviking 和 arg-ollama 就绪后，在仓库根目录运行下面的命令。范围 URI 对应本次已导入的合成样例。

    & 'D:\DevTools\PythonEnvs\main\python.exe' -B poc/openviking/evaluate_natural_approvals.py viking://resources/parallel-approvals-20261107-223813 --stress --retry-top3

运行配置、索引、模型缓存和原始结果位于 D:\Projects\AgentRelayGovernance\openviking-runtime。运行配置含本机服务凭据，保存在仓库外。

## 适用边界

样例使用三个文档、两个事项、预设英文别名和有限比较句式。压力测试验证的是已构造的候选排序与回退行为。实际项目需要可信事项标识、完整的本地历史、记录来源核验和跨项目隔离。ARG 核心协议和治理文件仍由原流程管理。

## 候选深度与事项定向

- 11 份文档的压力语料中，目标明确的查询使用前三条候选正确判定 3/15，使用前十条正确判定 12/15。两组均无错误放行。
- 定向回退由本地事项目录提供资源路径。先核对资源归属，再读取索引正文，与本地样例逐字核对。最终状态仍按本地历史判定，分别记录命中来源和状态来源。
- 定向验证入口为 evaluate_matter_directory.py，传入已索引范围 viking://resources/candidate-depth-20261107-225734。当前目录为人工配置的合成映射。真实项目仍需验证映射更新、完整历史和隔离边界。

## 统一查询与索引切换

query_approval.py 先从本地别名识别事项，然后在当前范围取前三条候选。未找到可核对的同事项正文时，使用事项目录定向回退。状态由本地结构化历史按查询时点决定。

在仓库根目录查询示例：

    & 'D:\DevTools\PythonEnvs\main\python.exe' -B poc/openviking/query_approval.py 'Is the approval to verify the relay archive with SHA-256 still valid?' --as-of 2026-10-10

切换演练可用同一脚本的 --exercise 参数复跑。演练使用独立临时指针，验证候选范围中每个登记条目的正文与可检索性后再原子切换。失败保留旧指针，可重新验证并切回旧范围。演练复用两套已索引的合成范围，未覆盖真实索引发布流程或并发切换。

## 从本地记录构建候选索引

在仓库根目录执行：

    & 'D:\DevTools\PythonEnvs\main\python.exe' -B poc/openviking/exercise_index_release.py

每次生成独立的候选范围。先导入目录登记的审批，故意保留一条撤销记录未导入，验证清单核验能阻止发布。补齐后逐份读回正文、核对定向检索和记录 SHA-256，再替换演练用的临时指针。四个查询线程跨越构建、发布和回切，逐次验证状态和来源归属。结果写入 openviking-runtime，普通查询的活动指针保持原值。候选范围保留供审计。本演练覆盖单发布者，不覆盖多发布者、进程崩溃恢复或候选索引清理。

## 多发布者竞争与提交前中断

    & 'D:\DevTools\PythonEnvs\main\python.exe' -B poc/openviking/exercise_release_races.py viking://resources/approval-release-7af64fdd7cf2

本机 Windows 进程共享独立演练锁。获取锁后先比较预期活动范围，再核验候选清单和切换指针。两个进程使用同一旧范围提交时，只有一个提交成功。演练还覆盖候选缺失、清单核验后提交前退出、退出后重新发布，以及回切。普通查询的活动指针保持原值。比较条件是范围 URI，本轮不覆盖活动指针切走又切回同一 URI 后的过期写入，也不覆盖系统断电恢复或候选清理。

### 发布版本与索引清理预检

竞争演练现在同时比较范围 URI 与版本号。回切也递增版本，因此 A → B → A 后基于第一次 A 的发布会被拒绝。此前的无版本普通查询指针仍可读取，版本化切换只在演练指针上运行。

    & 'D:\DevTools\PythonEnvs\main\python.exe' -B poc/openviking/plan_index_retention.py

预检只读合成索引目录，将当前范围、已知发布候选及其他范围分组。没有读取者生命周期登记时，全部保留。预检不会执行远端删除。

### 查询占用与保留演练

    & 'D:\DevTools\PythonEnvs\main\python.exe' -B poc/openviking/exercise_index_leases.py viking://resources/approval-release-7af64fdd7cf2

隔离查询进程先在发布锁内读取范围并登记占用，再持有 Windows 文件锁直到查询结束。预检区分活动、可回切、读取中和未登记范围。终止进程后，Windows 释放锁，预检把其残留登记识别为失效。已登记的非活动范围仅在没有回切保护和读取者时列为清理候选。本演练没有远端删除，也未接入普通查询入口或其他机器上的读者。

普通 query_approval.py 查询现已使用同一套 Windows 发布锁和查询占用。plan_index_retention.py 读取本机参与登记的查询占用，每个范围单独采样，报告中的局部候选资格仅用于预检，所有范围仍禁止删除。发布与竞争演练继续使用独立临时指针。绕过入口的查询、其他机器的读者和实际远端清理仍需单独验证。

### 普通 POC 活动配置的发布和回切

publish_approval_index.py 接收候选范围、--expect-scope 和 --expect-revision。运行前应读取 openviking-runtime 中的 approval-active-index.json。完整清单核验通过后才在共享锁内切换。回切使用同一入口，将旧范围作为候选，并传入当前范围和版本号。

清理演练在共享锁内比较预检版本与当前版本。原本符合局部候选条件的索引一旦发布，旧预检会同时因版本过期和索引已活动而失效。该核验只用于演练和预检，远端删除未接入。

发布指针原子记录当前范围、版本和上一份已验证范围。回切后，被切出的范围成为新的回切保留项。预检读取该字段，并在每次采样时检查指针版本。同范围重复发布返回 already_active，保留原有回切关系。清理依旧只读，未设自动删除策略。

复跑命令已迁至当前回切保护范围。旧候选范围保留供历史报告追溯，预检仅反映参与登记的本机查询状态。

### 试点验收

    & 'D:\DevTools\PythonEnvs\main\python.exe' -B poc/openviking/exercise_pilot_readiness.py

验收包含本机实时查询、模拟连接与 HTTP 错误、索引正文过期、原生 ARG 验证器与样例文件哈希。普通查询在无法访问索引或索引证据缺失时返回明确状态。试点仍使用合成资料，运行结果保存在 openviking-runtime。

### 从现有服务重建 POC 索引

    & 'D:\DevTools\PythonEnvs\main\python.exe' -B poc/openviking/bootstrap_approval_index.py --activate-if-empty

从仓库内的合成记录创建新范围、逐份核验并运行四项查询。空配置可以首次激活，已有活动指针会被保留。省略参数只构建候选。报告提供新范围和可核验记录清单，预检会识别该候选。此入口需要项目专用 OpenViking 和 Ollama 已运行。

### 独立 Compose 部署

在仓库根目录运行 PowerShell 7：

    & ./poc/openviking/start_clean_stack.ps1 -Port 1934

需要已运行的 Docker Desktop、Compose 和 Python。可用 -Docker、-Python 指定本机路径。Compose 固定了已验证的镜像摘要，首次启动需要下载镜像和嵌入模型。运行目录为 openviking-runtime/compose-1934，包含独立的凭据、模型和索引。OpenViking 只映射到 127.0.0.1，Ollama 只在 Compose 网络内提供服务。

脚本先等模型和服务就绪，再建立合成索引并验收。重复运行复用模型和活动索引，并执行审批查询。已在本机独立的 1934 端口验证首次构建、重启持久化和重复运行，原 1933 服务同时保持可用。Docker Desktop 安装和另一台机器的兼容性仍需分别核验。

### 实际停服与容器重建验收

独立 1934 容器停止时，普通查询返回 index_unavailable，退出后无残留查询登记，1933 主实例健康。使用 Compose 强制重建 1934 的 OpenViking 容器后，原活动指针与命中来源一致，恢复正常查询。未携带凭据的检索请求被拒绝。恢复依赖项目 D 盘运行目录，未演练该目录丢失后的备份恢复。

### 从备份恢复到空运行目录

    & ./poc/openviking/exercise_stack_backup.ps1 -SourcePort 1934 -RestorePort 1935

恢复端口和目录必须未使用。演练短暂停止源 OpenViking，快照包含服务配置、索引数据及活动指针。逐文件核验源、备份、恢复目录的路径和 SHA-256，随后在新实例下载嵌入模型并复查同一审批问题。快照含本机服务凭据，保存在仓库外。快照与原实例位于同一物理盘上的情况下，仍需独立介质才能覆盖整盘故障。

### 备份完整性与模型摘要

    & 'D:\DevTools\PythonEnvs\main\python.exe' -B poc/openviking/verify_stack_backup.py 'D:\Projects\AgentRelayGovernance\openviking-runtime\backup-restore-20261110-101047.json' --exercise

省略 --exercise 可只读校验快照。演练在临时副本模拟文件修改、缺失和意外新增，三种情况均应被检出。恢复验收要求源与恢复实例的嵌入模型完整摘要一致，已对 1934 与 1935 实例实测。模型检查已纳入后续恢复演练脚本。

### 独立恢复已有快照

    & ./poc/openviking/restore_stack_backup.ps1 -Report 'D:\Projects\AgentRelayGovernance\openviking-runtime\backup-restore-20261110-101047.json' -IntegrityReport 'D:\Projects\AgentRelayGovernance\openviking-runtime\backup-integrity-20261110-101624.json' -Port 1936

使用尚未占用的端口和目录。源实例无需参与。新格式的备份报告含模型摘要时，可以省略 -IntegrityReport。恢复前校验快照，复制后再次校验，再启动服务并比较模型摘要、查询状态和来源。已有 1936 运行目录时，复跑须选其他空闲端口。测试报告中的错误哈希在创建恢复目录前已被拒绝。

### 总体验收

    & 'D:\DevTools\PythonEnvs\main\python.exe' -B poc/openviking/accept_poc.py

需要四套本地验收实例和已生成的 86 文件快照清单。入口执行 16 次实时查询、快照与三类损坏检测、ARG 原生验证、发布竞争和索引占用回归。2026-11-10 的验收通过。真实试点的范围和验收口径见 PILOT-PLAN.md。

### 第一批公开资料只读试点

    & 'D:\DevTools\PythonEnvs\main\python.exe' -B poc/openviking/exercise_public_pilot.py

在独立范围索引当前 Git 提交中的八份公开文档。每次生成单独的 public-pilot 子目录，保存快照、Git 提交、文件 SHA-256、检索响应和原文核验。长文档会被 OpenViking 分段，按资源目录追溯原文件，片段必须可逐字在提交快照中定位。此次仅衡量预期来源是否进入前五条且核验通过，未运行答题或 G0/G1 对照。

### 公开文档的配对作答

compare_public_pilot.py 接收一次公开文档试点的 report.json。先重新核对快照 SHA-256，再从同一快照生成两组上下文。G0 使用本地关键词段落排序，G1 优先放入已核对的 OpenViking 片段，再用相同的本地候选补齐。两组使用同一模型和 3600 字符上限。

2026-11-10 的 16 次配对作答中，39 次 OpenViking 片段命中有 29 次逐字匹配，39 次在仅归一化空白后匹配。G0 与 G1 分别有 6/7、7/7 正例把预期来源放进模型上下文。两组均只完整通过无答案题，提交的引文均未通过按来源 ID 的逐字核验。本轮不能据此估计人工或更强模型的答题收益。

### 多步骤题拆分

evaluate_decomposed_pilot.py 接收固定证据诊断报告，运行九道迁移、关闸和归档子问。默认使用原段落，--line-only 使用人工标注的原文行并校验快照哈希。两组使用同一模型和提示。完整性和引文支持程度需人工判读，脚本的关键词匹配只用于排查。2026-11-10 的段落条件答对 6/9，原文行条件严格答对 8/9。后一条件仍有一条回答把归档标记解释成已获批准，超出原文。

### 直接查询公开原文证据

    & 'D:\DevTools\PythonEnvs\main\python.exe' -B poc/openviking/query_public_evidence.py 'D:\Projects\AgentRelayGovernance\openviking-runtime\public-pilot\04cff22bfd9f\report.json' 'Which Python command validates governance after migration?'

输出提交号、原文件、行号和候选原文。--local-only 跳过 OpenViking。服务不可达时回退本地排序并标注状态。候选原文可能与问题相关但不足以回答问题。入口不生成答案。--exercise 可以用旧作答报告核验是否存在逐字定位，定位成功也不代表答对。

### 可选的规则化简答

query_public_evidence.py 默认只返回候选原文。显式使用 --short-answer 时，可提取三类已定义事实：V2 迁移验证命令、关闸的 formal_ready 与 blocking_reasons、分数差异数。程序只从相应来源和固定句式提取，并附原文行。未支持的问题、缺失或冲突证据分别返回状态。六条受支持查询中五条答对，一条迁移改写未召回所需原文而拒答。

简答候选缺少所需原文时，仅扫描该问题类型对应的已核验 Git 快照文件一次，标记 directed_snapshot。已在实时查询中验证三条迁移改写均从迁移指南第 65 行恢复。未知问题、同时触发多类的问句以及额外要求谁、何时或为何的问句返回不支持。候选冲突不触发补查。

简答模式现覆盖九类预定义事实，包含迁移、关闸与归档。使用 exercise_public_short_answers.py 加公开试点 report.json 可复跑九条原题和四条改写，每题分别测试 OpenViking 增强和纯本地路径。检查期望值、引文行号及原文，同时覆盖不支持、缺证据和冲突。2026-11-10 实测 26 条回答、5 条拒答均通过。

### 中断交接演练

exercise_handoff_recovery.py 基于本项目实际回切报告生成隔离的暂停交接，运行 ARG 原生验证器及可选适配器。三次独立的 Ollama 模型调用分别测试服务可用、不可达但有本地证据、不可达且缺证据。权威文件哈希保持不变。结构化输出的三个会话都恢复了任务 ID，但都将 PAUSED 错报为 HOLD；缺证据时还建议完成验证。自动验收不应放行这些建议。本次使用受控文件上下文的本地模型会话，未运行具备自主工具调用的第二个 Agent。

中断演练现使用原生 YAML 解析器读取暂停任务 ID 和状态，并对核验过的回切版本进行程序判断。三场景最终门控结果与预期一致，模型三条原始建议均未通过。固定句式、缺失证据、不同版本冲突、篡改哈希和任务 ID 错配另有验证。门控仅适用于这次回切验证任务，未接入通用 ARG 流程。
