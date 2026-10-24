# 整体架构重构分析（2026-10-24）

**状态**：分析稿（未实施）。基线：`f584c47`（2026-10-20）。度量方法：AST 导入图 + 模块清单 + 测试映射，全部数据可复算（脚本见文末）。用户判断"整体架构还是得重构下"——本分析的结论是：**架构意图总体成立，失真的是代码组织与文档映射；推荐"分层巩固"而非重写**。依据如下。

## 1. 结论摘要

- 104 个模块、48.5K 行（42.6K 代码行）、194 个测试文件、3945 个测试函数；**导入图零循环依赖**；枢纽结构清晰（`sandbox_policy` 扇入 19、`control` 10、`config` 9）。
- §4 架构图的**分层意图没有被破坏**：控制面边界完好（无人绕过 `control` 写状态）、UI→编排→隔离的依赖方向单向、hub 集中在策略/契约/配置这类"稳定基座"上。
- 真正的问题是两个"上帝模块"和一张**过时的架构图**：`runner.py` 4495 行吸收了平台执行细节；`pack_verify.py` 3214 行把纯算法与验证策略耦合；架构图缺 `execution_broker`（1117 行）等已存在的盒子，14 个模块"未归类"。
- 推荐路径：**O1 分层巩固**（4 个可独立提交的小收敛，每个带测试与 CI），之后评估 O2 子包重组；**不推荐**大爆炸重写——它会把 3737 项测试 + 三 CI run + provenance 的验收面置于零收益风险中。

## 2. 现状度量（2026-10-24，`f584c47`）

| 维度 | 数据 |
|---|---|
| 规模 | src/icode 104 模块 / 48,516 行（42,605 代码行） |
| 测试 | tests 194 文件 / 3,945 测试函数；本地全量 3,737 通过（205 跳过，9 项环境性失败/错误） |
| 依赖健康 | 模块级导入图**零循环**；扇入 hub：sandbox_policy 19、control 10、config 9、contracts 8 |
| 跨盒子依赖 | 方向单向为主：UI→GUARD/控制面/ORCH；ORCH→SANDBOX/EVIDENCE/控制面；无反向穿透 |

按 §4/§5 盒子的代码分布：

| 盒子 | 代码行 / 模块数 | 最大模块 |
|---|---:|---|
| SANDBOX 隔离执行 | 9,583 / 20 | isolation 2444、windows_appcontainer 1810、windows_job 1338 |
| ORCH 任务编排 | 7,121 / 7 | **runner 4495**、windows_runner_pipe 956 |
| EVIDENCE 证据包 | 6,685 / 8 | **pack_verify 3214**、evidence 1465 |
| 扩展生态 | 4,669 / 11 | network_proxy_server 1204、network_lease 1136 |
| WORKTREE 工作区 | 4,147 / 4 | workspace 2243、workspace_snapshot 1176 |
| UI 前端 | 3,702 / 6 | autonomy 1031、cli 875、tickets 561 |
| **未归类** | **3,591 / 14** | **execution_broker 1117**、reviewer 334、handshake 328 |
| LOOP Tool Loop | 3,353 / 7 | tools.builtin 1235、loop 931 |
| MODELS 模型后端 | 1,255 / 9 | openai_compatible 399 |
| GUARD 审批 | 1,164 / 4 | sandbox_policy 568、guard 270 |
| 多 Agent | 1,038 / 5 | multi_agent 329、write_lease 267 |
| 控制面适配 | 847 / 5 | control 407、contracts 249 |
| 评测 | 671 / 2 | benchmark 410、conformance 261 |
| RECOVERY | 437 / 2 | recovery 297、checkpoint 140 |
| CTX 上下文与预算 | **253 / 2** | context_index 187、budget 66 |

## 3. 架构图与代码的漂移（结构债务，按证据排序）

### D1（高）runner.py 4495 行：编排器吸收平台执行细节

`runner` 占 ORCH 盒子 63% 代码，fan-out 33（全仓第一）。其内部约 40% 是**平台进程机制**：`_run_posix_bounded_output`、`_cancel_windows_pipe_readers`、`_run_threaded_bounded_output*`、`_PosixVerificationExitMonitor`、`windows_runner_pipe`（956 行）——即"验证执行"横跨 ORCH 与 SANDBOX 两个盒子。后果：

- 改验证行为必须动编排器；编排器无法在无平台环境（纯单测）中完整测试；
- 与 `isolation` 盒子（9583 行，本应拥有平台执行）职责重叠，两边都可能改同一行为。

### D2（高）架构图缺盒子，14 个模块无分层归属

`execution_broker`（1117 行）是 ORCH 与 SANDBOX 之间真实的执行中介（fan-out 10，连接 isolation/linux_*/network_proxy_scope），但 §4 图里没有这个盒子；`reviewer`、`handshake`、`windows_worktree`、`windows_startup_*` 等同样未归类。§12 P2"文档漂移"刚按验收记录修复，但"架构盒子→模块"映射表仍不存在——图是真源、模块是影子，影子没有登记处。

### D3（中高）pack_verify.py 3214 行：算法与验证策略耦合

内嵌 Ed25519（约 700 行纯算法，RFC 8032 向量）与包验证/签名策略/锚定校验同文件。零依赖纪律**要求**自实现算法（这点不动），但算法应独立成 `icode.crypto.ed25519`：边界干净、可单独向量测试、pack_verify 只留策略。

### D4（中）CTX 盒子名不副实

架构图的"上下文与预算"盒子实际只有 253 行；真正的上下文压缩（compaction）在 `loop.py` 内，`context_index`（R4 门禁驱动上下文）与盒子语义也不完全对应。盒子概念需要重定义或重命名。

### D5（中）CLI 是第二编排路径

`cli.py` 875 行、21 依赖、13 个 `cmd_*` inline；`cmd_task` 自行组装 `_build_runner + LoopConfig + Budget + run_task`——与 `runner.run_task` 重复编排知识。入口层应只做参数解析与调用。

### D6（中低）workbench.py 服务器/服务/资产同文件

448 行内混合 HTTP 安全、资产服务、`WorkbenchServer` 组装（依赖 autonomy/tickets/control/workspace）。服务组装逻辑在 HTTP 层，独立测试需要起服务器。

### D7（低）测试盲区 4 模块约 690 行无直接契约测试

`windows_positive_loopback_policy`（332）、`windows_startup_source`（176）、`windows_provenance`（107）、`leased_connect`（75）无任何测试文件直接导入（仅有脚本/CI 间接覆盖）。

### D8（低）scripts/ 43 文件扩张

CI/probe 工具与产品代码分离是好的；但 `windows_positive_loopback_admin*` 5 文件族说明 probe 工具自身在按平台细节膨胀，可设边界。

## 4. 重构选项与取舍

### O1 分层巩固（推荐先行）

不动模块位置，四个可独立提交的收敛，每步独立 CI：

| 步 | 内容 | 预期收益 | 风险 |
|---|---|---|---|
| R1a | runner 的验证进程管理（约 1500 行）下沉新模块 `icode.verification_process`，runner 只留策略调用与结果解释 | runner 降约 35%；验证行为改动不再触碰编排器 | 中：`test_runner` 92 项是回归面 |
| R1b | Ed25519 提取为 `icode.crypto.ed25519`，pack_verify 只 import | pack_verify 降约 25%；算法可独立向量测试 | 低：R7 签名/验签/整合测试全绿即验收 |
| R1c | 建立"架构盒子→模块"登记表 + `test_architecture_boundaries.py`：编排层禁 import 平台模块清单、hub 不得被反向依赖 | 漂移可检测（新增模块必须归类） | 低 |
| R1d | CLI 收敛为参数解析层，编排知识回到 runner/autonomy/workbench 公开入口 | cli fan-out 下降；单一编排路径 | 低-中：`test_cli` 回归 |

### O2 子包重组（O1 后评估）

104 个扁平模块 → 约 10 个子包（execution/isolation/evidence/models/ui/control/benchmark/...），`__init__` 重导出保持公开 API。收益：分层显式化；成本：194 个测试文件的 import 更新 + 至少一轮完整 CI。机械化但 diff 巨大，建议作为独立阶段并配 SPEC。

### O3 runner 协作者化（暂缓）

`TaskRunner` / `VerificationSupervisor` / `RepairCoordinator` + 依赖注入。收益最大（可测试性）但触碰 CI 全绿面，按仓库纪律需独立 SPEC + 独立评审；仅当 O1/O2 后仍有痛点时启动。

**不推荐大爆炸重写**：导入图零循环、hub 健康、控制面边界完好、3737 测试 + 三 CI run 的验收面是多年阶段成果；重写不增加任何用户可见能力，只把验收面置于风险中。

## 5. 推荐路径与验收

1. R1b（最低风险，先建立"提取模块"的操作先例）→ R1a（最大收益）→ R1c（防再漂移）→ R1d（入口收敛）。
2. 每步：独立提交、相关测试文件全绿 + 全量套件零新增失败 + CI 三 run success 后进入下一步；任一步失败按 git revert 回退该步。
3. O2 在 R1a-R1d 完成后以独立 SPEC 评估（本分析不预先拍板）。
4. 验收度量：runner ≤ 3000 行、pack_verify ≤ 2500 行、`test_architecture_boundaries.py` 存在且 104 模块全部归类、全量 3737+ 零新增失败。

## 6. 明确不动（重构边界）

- 控制面子仓边界与 `icode_control.py` JSON 契约（§4 不变量 1/3/5）；
- evidence pack 的 schema 与**签名消息格式**（外部可验证性，R7 已锚定公开仓库）；
- core 零第三方依赖（pyproject dependencies=[]）；
- Guard/Sandbox 的 fail-closed 语义与 conformance 契约；
- CI 三 run 与 provenance 验收面（重构不得以"测试适配"为名削弱断言——只允许因公开 API 重导出做的 import 更新）。

## 7. 风险与回滚

- 最大风险是 R1a：验证进程管理横跨平台（posix 组/Windows 管道/线程读取），下沉时行为差异可能只在 CI 的 Windows/macOS 腿暴露。缓解：先补平台差异的固化测试（当前 4 个盲区模块之一正是 `windows_positive_loopback_policy`），再搬迁。
- 每步独立提交保证回滚粒度；全量套件 + CI 是唯一验收依据，"跳过≠通过"。

## 8. 待补充输入

- 主流 Agent 项目分层实践对照（并行调研中，到达后补入"外部参照"一节：采纳/暂缓/不适配判定）。

## 附：度量复算

- 模块清单/LOC：`ast` 遍历 `src/icode/**/*.py`；
- 导入图：`ast.Import/ImportFrom`（含相对导入包解析）归一化到模块名；
- 测试映射：测试文件对 src 模块的直接 import；
- 数据落盘：`/home/orbbec/icode_arch_metrics.json`（基线 `f584c47`）。
