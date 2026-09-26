# R3 自验证与有界修复

- 日期：2026-09-26
- 状态：R3 自验证/有界修复核心和独立只读 Reviewer 已有离线实现。`run_task` Reviewer 精确读取改动文件，并通过只读上下文的 `submit_review` JSON Schema 工具提交；长上下文在完整读取后仍漏提交时，新增受限短上下文终结器作为一次有界兼容路径，只接收完整读回的源码（合计最多 64 KiB）且只开放具名提交工具。宿主继续校验 findings、证据指纹和 diff；权限越界、未完整读取、合同错误、预算/回合耗尽都 fail-closed。MiniMax-M3 TDD 靶场现已真实触发 `repair_decisions=["allow"]`，修复回合改动 `calc.py`/`test_calc.py`，独立 20 项测试通过，Reviewer 完整读取并结构化提交，最终 `TaskReport.ok=True`（25 次调用 / 109,087 tokens；预算预期 180,000）。另一真模型单次任务通过 17 项测试 / 14 次调用 / 64,427 tokens，但未触发短上下文终结器；兜底仍由离线回归验证。上一轮全量测试 830 项通过（23 skipped），`scripts/preflight.py` 三道门通过；本轮异常分类修正后门禁待重跑。R2 Windows runner-pipe 最新原生 [CI #198](https://github.com/ayukyo/icode/actions/runs/36239940582) x64/ARM64 都报告 `unclassified`，本地已修正异常类名分类、待下一次双架构复验；R3 工作流 Reviewer 跨平台只读边界和真实 Git SHA 锚定仍未闭合。OS wrappers 仍不能证明 Reviewer 命令不可见排除树，因此工作流 Reviewer 的 `run_command` 继续 fail-closed 禁用。
- 依据：[产品总架构](../../icode-agent-product-architecture.md) §13.7；[R2 跨平台隔离设计](../specs/2026-09-23-r2-cross-platform-isolation-design.md) §12.2

## 2026-09-26 UTC 当前联动状态

- R3 真模型修复闭环已在受控 MiniMax-M3 靶场完成，但这只证明该靶场链路；真实 Git SHA 锚点和 workflow Reviewer 跨平台只读边界仍未验收。工作流 Reviewer 的 `run_command` 保持 fail-closed。
- R2 手动 [CI #200](https://github.com/ayukyo/icode/actions/runs/36240714328) 中 Windows x64/ARM64 标准用户探针都在子进程 `CreateFileW` 返回 `access_denied`；Linux/macOS conformance `passed=5/10`、`critical_passed=false`、`ready=false`。本地正在加入只读 DACL/实际客户端 primary token 诊断，尚无新 Windows 原生运行结果。
- 本地回归新增验证必须选择被诊断的子进程 token，且无法打开时不能回退到父线程/进程 token；`test_windows_standard_user_token_probe` 29 项通过。该测试不调用 Windows API，不能替代 x64/ARM64 原生 CI。R2 自动模式与 Windows runner pipe 仍关闭。

## 2026-09-26 UTC：CI #202 回执过滤根因与修正

- **原生复验：**手动 [CI #202](https://github.com/ayukyo/icode/actions/runs/36242053362) 的 Windows x64/ARM64 标准用户步骤都仍输出通用 `RuntimeError`；此前的新增 DACL/token 诊断标签没有泄漏，但也被外层错误过滤器隐藏。此次运行其他已完成的 Windows Job、wheel、workspace 和 native-probe 作业保持其各自结果；它们不把 R2 变为通过。
- **根因：**子进程报告 parser 返回由 `+` 连接的固定安全标签，父端再包成 `standard_user_restricted_child_failed:<detail>`；最外层只接受 `[a-z_]+` 阶段名，因此将合法标签折叠成异常类型。并且旧的 `"winerror=" in safe` 快速通道不够严格，可能放行未按格式校验的异常正文。
- **修正与回归：**提取纯函数 `_safe_standard_user_probe_error()`，只允许精确的已知状态、完整小写 `stage:winerror=N`、或总长不超 200 字符且满足固定语法的受限子进程标签。增加正例验证 child-token/DACL 标签完整保留，负例验证 Windows 路径与秘密文本仍折叠为 `RuntimeError`。新测试先 RED，修正后 `test_windows_standard_user_token_probe` 31 项通过；`compileall`、`git diff --check` 与全量 `scripts/preflight.py` 通过。
- **边界：**这修正回执可见性并收紧错误输出，不改变权限、不宣称 `AccessCheck` 等同 `CreateFileW`，也不代表管道连接成功。需以新提交重新跑双架构 `workflow_dispatch`，读取 DACL、ACE、child primary-token、logon SID 与 AccessCheck 标签；R2 Windows 自动模式继续关闭，R3 Git SHA 与 workflow Reviewer OS 边界仍待验收。

## 2026-09-26 UTC：CI #204 AccessCheck 状态与安全描述符修正

- **原生证据：**手动 [CI #204](https://github.com/ayukyo/icode/actions/runs/36242591553) 的 Windows x64/ARM64 都报告相同标签：`client_open_access_denied+dacl_present+ace_match+token_child_process+logon_enabled+restricted_no+access_unavailable`。因此已看到真实 DACL 有预期 ACE，child primary token 的 logon SID enabled 且 token 非 restricted；真实 `CreateFileW` 仍拒绝。Linux/macOS `5/10`、`critical_passed=false`、`ready=false`，不能据此通过 R2。
- **API 合同与推断：**Microsoft [`AccessCheck`](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-accesscheck) 说明其输入需为有效安全描述符，缺少 owner/group SID 时会以 `ERROR_INVALID_SECURITY_DESCR` 失败；[`GetSecurityInfo`](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-getsecurityinfo) 仅返回被 `SecurityInfo` flags 请求的组件。本地原代码只请求 `DACL_SECURITY_INFORMATION`，与 `access_unavailable` 一致；但 CI 没保留 API 错误码，所以这仍是待验证根因，不是已确认结论。
- **TDD 修正：**先增加安全信息 mask RED 测试，再令 `GetSecurityInfo` 同时请求 `OWNER_SECURITY_INFORMATION | GROUP_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION`；DACL 读取/ACE 匹配逻辑、访问掩码及 ACL 均不改变。`test_windows_standard_user_token_probe` 32 项通过；下一次双架构原生 probe 必须验证 `access_allow` 或 `access_deny`，且不把 AccessCheck 单独当作 CreateFile 实际结果。
- **未关闭边界：**管道 `CreateFileW` access denied、标准用户 runner probe、Windows 文件/网络隔离与自动模式仍未通过/开放。即便 AccessCheck 返回 allow，也要继续分析 AccessCheck 与内核 CreateFile 结果差异，不能扩大权限试探。

## 目标与范围

从「能修改」升级到「能根据真实失败证据验证和修复」：

```text
修改 → 静态诊断 → 编译 → 单元测试 → 失败分类 → 有界修复 → 回归 → 独立 Reviewer
```

R3 核心能力（本切片）：

1. **失败分类**（`src/icode/self_verify.py::classify_failure`）
   把命令 / 测试 / 契约回执的失败分成六类：
   `environment` / `code` / `test` / `contract` / `model_capability` / `side_effect_unknown`。
   分类依据是可见证据（退出码、输出模式、错误类型、是否产物缺失）；
   无法归类时如实归入 `side_effect_unknown`（fail-safe）。

2. **证据绑定**（`VerificationEvidence` / `evidence_fingerprint`）
   每次验证绑定到 step、attempt、命令摘要、退出码、环境指纹、产物哈希、
   输出摘要与捕获时间。没有绑定的结果不能被当成「新证据」，
   也就不能支撑一次新的修复；指纹不包含输出正文或敏感参数。

3. **有界修复决策**（`VerificationLedger::decide_repair`）
   只有出现**新的失败证据**才允许重试 / 修复；相同指纹的重复失败在
   有界次数内被终止，避免「没有新证据就反复碰运气」；
   副作用状态不明一律按 fail-safe 拒绝自动重试（`human`）。

4. **runner 补救回合证据门**（`src/icode/runner.py::run_contract_step`）
   进入补救回合前先给「产物缺失」分类并绑定证据，`decide_repair` 返回非
   `allow` 时跳过并如实警告，不再无条件重试。

5. **任务级验证证据绑定**（`src/icode/runner.py::run_task`）
   独立跑 `python -m unittest` 后把退出码、输出摘要、环境指纹、改动文件哈希
   与失败分类绑定成一条 `VerificationEvidence` 挂到 `TaskReport.verification`；
   模型自述不算证据。

6. **证据回执序列化**（`VerificationEvidence.to_receipt`）
   可把一条验证证据序列化成 `verifications.json` 回执（含指纹、环境指纹、
   产物哈希与失败分类，不含输出正文/敏感参数）；`build_evidence_pack` 直接
   接受 `VerificationEvidence` 并序列化进证据包。

7. **独立 Reviewer 只读上下文**（`src/icode/reviewer.py`）
   `reviewer_guard` 构造无任何写授权的审查上下文，`verify_read_only` 用真实
   Guard 判定锁死；`IndependentReviewer.review` 针对改动文件与验证证据产出
   带严重级别、类别、文件/行号与证据指纹引用的结构化发现，且不能修改被审对象
   （符号链接被审对象直接拒绝）。`run_task` 使用独立模型对话执行语义审查，工具
   运行时通过 `Guard.allowed_read_files` 精确限制为本次改动文件，仅开放 `read_file`
   与只读上下文专用 `submit_review`；后者以 JSON Schema 承载结构化结果，局部校验
   失败最多反馈纠正一次；未经结构化工具提交或超过回合/纠正上限均失败关闭。需完整读取所有改动文件，finding 绑定验证证据，审查结束重核
   diff 指纹。任何越权、无效响应、文件快照漂移或 Reviewer 错误均失败关闭。

8. **回归证据绑定到具体 diff**（`workspace_snapshot.diff_fingerprint`）
   把一次改动（相对基线）绑定成确定性指纹：只依赖改动前后每条路径的 sha256，
   增删改状态区分、同结果不同基线指纹不同。`run_task` 的独立测试回执把
   `diff_fingerprint` 一并绑定进 `VerificationEvidence`（进指纹与回执），
   证据锚定到「具体这一份 diff」而非仅结果内容。

9. **修复证据写入事件链并随证据包取证**（`control.record_verification`）
   控制面 `record-verification` 是唯一允许写 `verification_runs` 的入口；
   `runner` 在补救回合（产物缺失）进入时把该条修复证据（指纹 + 缺失摘要 +
   分类）写入事件链（`verification_recorded` 事件，幂等）。`build_evidence_pack`
   自动把 `metadata.verification_runs` 一并纳入 `verifications.json`，回归证据
   随包可取证。控制面验证域只有 build/deploy/listen/device_test 四类，R3 验证
   按 `device_test + layer=unit` 如实记录，`evidence` 字段放指纹、`note` 注明
   实际类别，不冒充设备实测。

## 六类失败定义

| 类别 | 含义 | 证据信号（示例） |
|---|---|---|
| `environment` | 环境/系统问题，与代码改动无关 | 退出码 126/127、`command not found`、`ModuleNotFoundError`、`Permission denied`、OOM |
| `code` | 代码改动引入的回归 | 测试断言失败、非零退出且无环境/契约信号 |
| `test` | 测试架子本身的问题 | `failed to collect`、`no tests ran`、fixture 错误 |
| `contract` | 控制面/门禁未满足 | 产物缺失、边界复检失败、副作用回执失败 |
| `model_capability` | 模型没有按契约产出或产出不可解析 | JSON 提取失败、未知工具、未审批、max_turns |
| `side_effect_unknown` | 无法判断类别/副作用不明 | `ambiguous_side_effect`、未闭合 operation |

## 验收（离线，已通过）

- `classify_failure` 对六类代表性样本分类正确；无法归类按 fail-safe；
- `evidence_fingerprint` 对同一事实稳定、对输出/退出码/产物哈希变化敏感，
  且不泄露输出正文或敏感参数；
- `VerificationLedger`：首次新证据允许、同指纹拒绝、输出变化允许、
  超界停止、副作用不明转人工、attempt 递增；
- runner 补救回合在首次失败时仍会进入（兼容既有离线链），无新证据时跳过；
- `run_task` 把独立测试退出码/输出摘要/环境指纹/改动哈希绑进 `TaskReport.verification`；
- `to_receipt` 与 `build_evidence_pack` 把验证证据序列化进证据包且不含正文。

## 边界（不冒充）

- 本切片**不是**完整 R3：真实模型有界修复循环尚在验收，证据尚未绑定真实 commit SHA；
  工作流 `step=review` 的原生跨平台命令边界仍 fail-closed；
- 分类函数只消费已提供证据，不做无依据推断，也不代替控制面门禁；
- 有界修复仍受既有预算、回合数、审批与副作用回执约束。

## 并行开源研究取舍

- **采纳机制：** Aider 的 edit→lint/test 验证闭环、SWE-agent 的
  observation-feedback、OpenHands 的 stuck detection、Cline 的 checkpoint
  共同点都是「没有新证据就不允许继续碰运气」；本切片用证据指纹 + 有界
  次数实现同一目标，不复制任何第三方实现。
- **不直接采纳：** 多 LLM 投票式对抗验证（arXiv 2512.03097 已证明共谋可破）；
  保持规则绑定 + 禁止自我委派。
- 以上为机制层面结论，不代表已集成任何上游运行时依赖。

## 已完成（回归切片，2026-09-26）

1. `workspace_changes` / 测试回执绑定到具体 commit/diff 与 artifact hash：
   `diff_fingerprint` 进 `VerificationEvidence`（指纹 + 回执）；
   工作区快照排除 `__pycache__` 编译产物（不是模型改动，不进 diff 证据）；
2. 独立 Reviewer 接线：`run_task` 用只读上下文复核改动与证据，不能修改被审对象；
3. 修复证据写入事件链与证据包：`record-verification` 记录 `verification_recorded`
   + `verification_runs`，`build_evidence_pack` 自动纳入 `verifications.json`；
4. **`run_task` 有界修复循环**：独立测试失败后，若类别可自动修复，在
   `max_repairs` 有界次数内重新让模型改动并复测；每次必须有**新的失败证据**
   （diff 或退出码/类别变化），同 diff 无新证据即停止，不碰运气；
   `TaskReport.repair_attempts` / `repair_decisions` 记录全部尝试与决策。
   指纹语义修正：`attempt` 是账本标签不进指纹（同一失败再次观测=无新证据），
   `record` 保留 `diff_fingerprint`；离线用 FakeBackend 覆盖修复成功、
   无新证据停止、次数有界三种路径。
5. **验证器继承执行隔离**：`run_task` 的独立 unittest 验证使用与 Executor 相同的
   sandbox，避免工作区测试代码经后置验证进程越过文件/网络边界。新增 Linux bwrap
   负例：测试代码尝试打开工作区外临时文件时被拒绝；密钥路径只验证 `open` 被拒，
   不读取内容。该修正已本地回归，跨平台 CI 与真模型调用待验证。
6. **独立模型 Reviewer 的精确读权限**：Reviewer 使用新对话、仅 `read_file` 工具与
   `allowed_read_files` 精确路径集，不获得 `glob`/`grep`/`workspace_changes`、写入或
   命令执行能力；必须读全本次变更、合法 findings 仅能指向改动文件，finding 保存行号
   并绑定 `evidence_fingerprint`。审查前后快照一致且任务确有改动才可能通过。
   Guard、工具越权、账本保密、无改动任务、非法响应及阻断 finding 的回归均先 RED 后 GREEN；
   本轮 57 项 Reviewer/Guard/runner 定向测试通过；真实模型单次执行 + 测试 + Reviewer 已通过，
   但 `max_repairs=0` 且没有出现失败，未覆盖真实模型修复重试；全量预检与跨平台 CI 待完成。

## 下一片（尚未闭合）

1. 端到端真模型修复循环：通过受控、可复现的失败初态，验证真实失败分类 → 有界修复
   → 回归 → 独立 Reviewer；当前真模型单次成功路径已验收，但未触发修复分支；
2. 对本轮新接入的 review 步骤只读执行边界完成跨平台原生验收，并评估策略化
   Reviewer 的只读文件与拒读子路径能否由同一 OS profile 可证明地组合；
3. 证据指纹锚定到真实 commit（Git SHA）而非仅工作区 diff 快照（R2.4 Git broker
   接通后可做）。

## 2026-09-26 UTC：CI #188 跨平台证据接线回归

- [CI #188](https://github.com/ayukyo/icode/actions/runs/36222709957) 的 Python 3.11/3.12、Windows x64/ARM64 wheel、Linux 原生探针通过；Windows 两架构的 `test_局部自检不冒充完整沙箱` 失败，macOS Intel/ARM 因评分调用没有提供 `process_group_cleanup` 布尔证据而异常退出。
- **根因区分：**Windows `capability_report()` 把 Job 的正常退出/超时回收局部探针作为 `doctor_self_test`，并把 Windows Job 清理错传成 macOS 专用 `process_group_cleanup`；评分因此回退到空证据。macOS 原生 CI 的 `scripts/run_native_probe_ci.py` 评分前只运行六项文件/网络探针，没有运行真实同组清理探针，而 evaluator 按设计拒绝缺失证据。
- **修正与本地回归：**先新增跨平台 capability-report 与 macOS 原生 CI 编排测试并观测 RED，再修为：仅 Linux 已完成的内核沙箱最小探针可点亮 doctor `doctor_self_test`；Windows Job/macOS 同组清理只保留其局部证据；macOS 原生 CI 评分前运行真实组清理，把通过或失败的布尔值写入评分，失败仍令作业非零。额外发现 CI evidence 的来源字段可能是字符串或数组；补上输出格式回归，避免把字符串逐字符 join。当前 focused tests 与 Linux 原生探针通过；Windows、Intel macOS、Apple Silicon 的真实 runner 复验尚待后续 workflow。
- **状态边界：**CI #188 原始失败保留为历史证据。上述本地修正不等同原生复验，不关闭 R2；R3 的真模型端到端有界修复与 review 步骤接线仍是独立未闭门项。

## 2026-09-26 UTC：真实模型修复分支首次端到端试跑

- **靶场与实际分支：**使用一次性隔离 Python 计算器靶场，预置确定性除零缺陷。真实模型触发独立测试失败，分类结果进入可修复分支，`repair_decisions=["allow"]`；模型修改了计算逻辑及相关测试，第二次 unittest 从失败转为通过。此次证明有界修复分支确实执行，不是此前“只跑一次且没有触发修复”的成功用例。
- **最终任务结果：**首轮 Executor 与 repair Executor 都在 `max_turns=8` 到顶；Reviewer 虽读取本次改动文件，但返回值不符合严格 JSON findings schema。`TaskReport` 因回合耗尽和 Reviewer 合同错误正确 fail-closed，没有报告任务成功。整次调用为 18 次模型调用 / 68,929 tokens；因此这不是 R3 端到端验收通过，也不覆盖成功 Reviewer 后的最终闭环。
- **修正方向：**下一步先分析每一轮工具调用消耗与提示响应大小，确定合理且仍有限的 Executor / Reviewer 回合上限；压缩 Reviewer 输出合同、对格式错误保留失败证据并禁止修复器接管 Reviewer；以相同靶场再次验证“初始测试失败 → `allow` → 修复后测试通过 → Reviewer 合法 JSON → TaskReport 成功”。预算与最大回合仍为硬上限，不通过时保持失败关闭。
- **清理与边界：**临时缺陷靶场已移除；模型密钥只经既有本机配置读取，不写入仓库、命令记录或输出。该试跑不证明任意仓库的修复率、成本或生产环境成功率。

## 2026-09-26 UTC：Reviewer 短上下文终结回退

- **现象与改动：**MiniMax-M3 长 Reviewer 会话曾在完整读取改动后仍连续未调用被强制的 `submit_review`。新增只在 `required_tool_not_called`、所有改动文件已完整无截断读取、无此前无效提交且无权限拒绝时启用的全新终结上下文；最终上下文只暴露 `submit_review`，源码从已验证的 `read_file` 输出重建并受 64 KiB 上限约束，仍共用原 `BudgetTracker`。
- **回归与边界：**FakeBackend 正例验证读取阶段自由文本失败后短上下文提交可通过；负例验证终结器请求 `read_file` 会被拒绝。结构化结果仍走原本地合同校验，随后核验工作区快照与 diff fingerprint；fallback 本身不能形成成功，只有本地验证通过的工具提交可形成审查报告。
- **真模型复验：**MiniMax-M3 在 bubblewrap 临时靶场添加 `calc_clamp` 与测试，改动 `calc.py`、`test_calc.py`；独立 unittest 17 项通过，Reviewer 读取两个改动文件并提交有效 schema，TaskReport 通过（14 次调用 / 64,427 tokens）。本次没有进入 fallback 或 repair，因此只作为常规真模型链路证据；fallback 当前由离线回归验证。
- **验证状态：**Reviewer/loop/runner/Windows token probe 聚焦测试 104 项通过；`./.venv/bin/python -m unittest`：830 项通过、23 项跳过；`scripts/preflight.py` 密钥扫描、子模块完整性、全量测试门均通过。真实修复 TaskReport 成功、R2 Windows 双架构 probe 和 Git SHA 锚点仍待完成。
- **Windows 诊断边界：**父子握手都可能在 15 秒附近超时；父端失败后增加最多 2 秒退出宽限，再读取最多 512 字节的安全白名单报告。该改动只改善失败归因，不能让管道握手变成通过；当前 CI #196 使用旧 SHA，必须重跑双架构手动 probe。
- **CI #198 结果与异常映射修正：**使用 `8dd40eb` 的 x64/ARM64 标准用户探针均完成但返回 `unclassified`；普通测试、workspace、Linux/macOS 原生探针、Windows Job 与 wheel 作业完成。`_run_child_mode` 曾把 `TimeoutError` 等类名直接写入回执，违反仅小写标签的 parser 契约。新增固定小写 label 映射、对既有异常类标签的有限兼容，并只在报告路径经固定 TEMP/文件名合同校验后回写；聚焦测试通过，双架构原生复验仍未完成，Windows pipe 不视为已验收。
