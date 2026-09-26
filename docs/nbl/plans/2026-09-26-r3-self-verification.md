# R3 自验证与有界修复

- 日期：2026-09-27
- 状态：R3 自验证/有界修复核心和独立只读 Reviewer 已有离线实现。MiniMax-M3 TDD 靶场完成真实失败 → `allow` → 修复 → 独立测试 → Reviewer 合法提交（25 次调用 / 109,087 tokens）；Reviewer 短上下文终结器仍缺真模型路径证据。本轮新增只读原始 Git tree 投影 OID及可选结果 commit tree 比对，并将绑定结果写入验证指纹/回执；`icode task --result-commit` 可显式启用。提交比对只证明 Git tree 内容相等，不认证来源或安全性，且时间字段只报告测试前后 HEAD 的观测关系，不按 author/committer date 推断。受测 tree 投影仅支持 POSIX 仓库根，最多 250,000 项、128 层和 256 MiB 文件字节，Python SHA-1 OID 不构成签名或抗碰撞安全证明；commit 对象读取上限 1 MiB；子模块/嵌套 `.git`、Windows、attributes clean 转换、ACL/xattr、宿主环境与执行轨迹均不在该证明范围。13 项定向回归通过；全仓 preflight 三道守护通过，unittest 883 项通过、23 项跳过。常规 [CI #214](https://github.com/ayukyo/icode/actions/runs/36254293856) 是此前提交的结果，成功但 Linux 与 macOS 原生隔离均为 `5/10`、`critical_passed=false`、`ready=false`，Windows 标准用户 pipe 探针被跳过；前次手动 [CI #213](https://github.com/ayukyo/icode/actions/runs/36252440492) x64/ARM64 管道均在 `CreateFileW` 以 `winerror=5` 失败。此代码切片 push 后的 CI 尚未出结果；跨平台只读边界未闭合，工作流 Reviewer 的 `run_command` 继续 fail-closed 禁用。
- 依据：[产品总架构](../../icode-agent-product-architecture.md) §13.7；[R2 跨平台隔离设计](../specs/2026-09-23-r2-cross-platform-isolation-design.md) §12.2

## 2026-09-26 UTC 当前联动状态

- **测试计数补记：**首轮聚焦批次为 126 项；随后纳入离线链路快照基准断言并加严回归，最新聚焦批次为 133 项通过；全量 preflight 为 861 项通过、23 项平台跳过。路线图与持续对照已按最新计数刷新。

- R3 真模型修复闭环已在受控 MiniMax-M3 靶场完成；本地 `run_task` 将真实 Git 基线 SHA 与初始/受测工作区指纹纳入回执，快照进一步区分文件类型与 POSIX 可执行位。133 项聚焦测试和全量 preflight（861 项测试、23 skipped）通过。Reviewer 跨平台只读命令边界、终结器真模型路径及结果 commit/tree 匹配仍未验收。
- R2 常规 [CI #212](https://github.com/ayukyo/icode/actions/runs/36252023822) 成功，但 Windows 标准用户探针在 push 运行中跳过；Linux/macOS conformance 仍 `5/10`、`critical_passed=false`、`ready=false`。手动 [CI #213](https://github.com/ayukyo/icode/actions/runs/36252440492) 同 SHA x64/ARM64 标准用户管道均在子进程 `CreateFileW` 返回 `access_denied`，自动模式保持关闭。
- R2.4 Linux x86_64 Git broker 有精确 helper 白名单和污染环境的已安装 wheel 负例；不是跨平台 broker，尚未接入模型工具入口。#212 常规 CI 通过不验证手动 Windows pipe、R2 全部 10 项隔离门或 R3 Reviewer OS 边界。

## 2026-09-27 UTC：稳定受测 Git tree 投影 OID

- **实现边界：**`run_task` 在每轮测试前后只读计算 POSIX 仓库根的 Git 原始文件树投影，并在前后 tree OID 与完整工作区指纹一致时，才把 `tested_git_tree_oid` / `tested_git_tree_status=stable` 写入验证证据、指纹、回执和 Reviewer 输入；测试修改工作区或 Reviewer 后发生漂移都会撤销/否决证据。非 Git 靶场继续留空；没有调用 Git、`git add`、用户 index、attributes、filter 或仓库 helper。
- **算法与限制：**以 Git 对象序列化规则计算 SHA-1/SHA-256 tree，路径排序、常规文件模式、符号链接目标及目录均有 Git CLI 交叉向量；不跟随链接。扫描上限为 250,000 项、128 层、256 MiB 普通文件内容。未知特殊文件、嵌套 `.git`/子模块、竞态、超限、非 POSIX 或非仓库根均不给 OID。所有 ignored/未跟踪文件纳入原始投影，不应用 clean filter；因而这不是等价于 Git index/tree 的“已提交内容”证明，投影不匹配时 fail-closed。
- **密码学边界：**Python 标准库 SHA-1 OID 与 Git 对象 ID 兼容，但没有复用 Git 的碰撞检测 SHA-1，因此 OID 不用作签名或抗碰撞安全根。Git 正在迁移/加固 SHA-1 的官方说明见 [hash-function transition](https://git-scm.com/docs/hash-function-transition/2.48.0) 与 [Git 2.48 highlights](https://github.blog/open-source/git/highlights-from-git-2-48/)；此处仅将 OID 用作本地相等性筛查，后续结果 commit 验证需保持这一风险边界，并结合已绑定证据，不得升级为安全认证声明。
- **验证：**R3 聚焦回归 43 项通过；全量 `scripts/preflight.py` 三项保护门通过，独立全量 unittest 为 871 项通过、23 项平台跳过。专用临时 Git 仓库覆盖 SHA-1/SHA-256、staged/unstaged、untracked/ignored、模式、类型、链接、特殊文件与属性 helper 不执行；还核验用户 index 字节及时间戳未改变、测试期间变化撤销 OID。
- **线上隔离状态：**push CI [#214](https://github.com/ayukyo/icode/actions/runs/36254293856) 总体成功；其中 Linux/macOS 原生隔离均 `5/10`、`critical_passed=false`、`ready=false`，Windows 标准用户管道 job 跳过。不得把常规 CI 成功写成 R2 通过；自动模式仍关闭。
- **结果 commit tree 比对（2026-09-27）：**新增只读 Git 对象读取：只接收完整 storage-format commit OID，禁用 replace refs 和 partial-clone lazy fetch，校验对象类型/大小/tree header 与 tree 对象，不读写用户 index；明确不接受 SHA-256 仓库的兼容格式 OID。`run_task(..., result_commit_sha=...)` 与 `icode task --result-commit <完整 SHA>` 可显式绑定；tree 不匹配或结果对象不可用时 `TaskReport.ok` 失败关闭，匹配结果进入 receipt/fingerprint。测试前后 HEAD SHA 分别记录；相同 tree 的非边界 HEAD commit 只标注“tree matched / not observed as HEAD”，不得声称 commit 当时存在。Git author/committer dates 不用于时序判断。
- **后续验收：**对 partial clone 缺失对象的无网络读取、对象损坏、SHA-256 storage/compat OID 边界、CLI/receipt 的实际调用方闭环继续补足；当前 CLI 仅在标准输出显示比对结论，尚无 `task` 命令的持久化 receipt 导出。还需继续解决 R2 原生隔离红门、跨平台只读 Reviewer 命令边界和 Reviewer 短上下文终结器真模型路径证据；所有未验收项保持 fail-closed，不输出“R2/R3 已完成”。

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

## 2026-09-26 UTC：CI #206 DACL 放行但管道连接仍拒绝

- **独立原生证据：**手动 [CI #206](https://github.com/ayukyo/icode/actions/runs/36243032179) 的 Windows x64 与 ARM64 都报告 `dacl_present+ace_match+token_child_process+logon_enabled+restricted_no+access_allow`；同一目标子进程的真实 `CreateFileW` 仍 `access_denied`。Linux/macOS 原生 conformance 仍为 `passed=5/10`、`critical_passed=false`、`ready=false`。因此只确认 DACL `AccessCheck` 不是充分解释，不能将失败归咎于完整性控制。
- **只读诊断补充：**根据并行微软 API 核对，将下一轮诊断收窄到实际 pipe 对象的 `LABEL_SECURITY_INFORMATION` 中 `SYSTEM_MANDATORY_LABEL_ACE`/`NO_WRITE_UP` bit，以及真实目标 child token 的 `TokenIntegrityLevel` 和 `TokenMandatoryPolicy`；只输出固定标签，不输出 SID/RID，不回退到父 token。Label-only 查询不读取审计 SACL；token 查询只需 `TOKEN_QUERY`。没有权限变更、重试 open 或改变探针判定。
- **微软 API 依据与推断边界：**[`GetSecurityInfo`](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-getsecurityinfo) 对管道 handle 可按 [`SECURITY_INFORMATION`](https://learn.microsoft.com/en-us/windows/win32/secauthz/security-information) 请求 `LABEL_SECURITY_INFORMATION`；微软分别说明完整 SACL 查询与 label-only 查询的权限边界。`GetTokenInformation` 的 [`TokenIntegrityLevel`](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-token_mandatory_label) 与 [`TokenMandatoryPolicy`](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-token_mandatory_policy) 均通过 `TOKEN_QUERY` 读取；[Mandatory Integrity Control](https://learn.microsoft.com/en-us/windows/win32/secauthz/mandatory-integrity-control) 在 DACL 之外检查对象标签与 mandatory policy，[SYSTEM_MANDATORY_LABEL_ACE](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-system_mandatory_label_ace) 定义 `NO_WRITE_UP`。对象 label + 有效 client token + 读写请求三者匹配才能形成强 MIC 候选，仍不能宣称唯一根因。
- **本机验证：**新增固定 RID/authority 分类、mandatory-label ACE 结构、缺失 label 与查询失败区分、token policy bit、白名单及较长但有界回执测试；Windows 探针单测 37 项通过。该环境不能原生执行 Windows API；需在后续 x64/ARM64 CI 确认新标签，且结果仍不能替代真实 `CreateFileW` 结论。
- **未关闭边界：**`CreateFileW` 拒绝、Windows 文件/网络隔离、runner 自动模式、Linux/macOS 5/10 门槛以及 R3 SHA 锚定和跨平台 workflow Reviewer 均未关闭。

## 2026-09-26 UTC：CI #208 完整性诊断未支持 MIC 假设

- **双架构原生证据：**手动 [CI #208](https://github.com/ayukyo/icode/actions/runs/36244885627) 的 Windows x64 与 ARM64 均报告 `dacl_present+ace_match+token_child_process+logon_enabled+restricted_no+access_allow+client_il_medium+pipe_il_absent+pipe_nwu_unavailable+token_nwu_yes`；两架构真实 `CreateFileW` 都仍 `access_denied`。Linux/macOS 原生 conformance 继续 `passed=5/10`、`critical_passed=false`、`ready=false`。
- **有限推断：**本探针测量的是失败目标进程的 primary token（`token_child_process`），其 IL 为 medium，`NO_WRITE_UP` 策略启用；实际 pipe 上未发现显式 mandatory-label ACE。微软 [MIC 文档](https://learn.microsoft.com/en-us/windows/win32/secauthz/mandatory-integrity-control)规定无标签对象按 medium 处理，因此当前记录不符合“低 IL 客户端写高 IL 对象”的典型 MIC 解释。它不能排除线程 impersonation、对象/令牌快照差异或其他内核路径条件，也不能单凭回执确定根因。
- **下一只读观察：**在调用 `CreateFileW` 的同一 runner 线程记录 [`OpenThreadToken`](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-openthreadtoken) 有无 token；如存在，仅以该 token 记录固定类别 IL、mandatory policy 和相同 DACL `AccessCheck` 结果。Microsoft 说明通常用请求线程的 primary token，但 impersonation 时改用线程 token（[How AccessCheck Works](https://learn.microsoft.com/en-us/windows/win32/secauthz/how-dacls-control-access-to-an-object)）；目标进程退出后的父进程快照不能代替这一调用点观察。保留真实 `CreateFileW` 结果及错误阶段；不扩大 desired access、不更改 DACL/SACL、不重试 production open。named-pipe 文档把 `FILE_CREATE_PIPE_INSTANCE` 的额外检查限定在 server-side `CreateNamedPipe` 打开现有实例；客户端 `CreateFile` 有自己的访问检查（[Named Pipe Security and Access Rights](https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights)），不能误把该服务器端条件套到客户端。
- **本地诊断切片（待原生 CI）：**已在等待实例后、实际 `CreateFileW` 前通过私有 CI 观察入口采样当前线程；公开 pipe-open API 没有接收任意回调，内部实现仅在标准用户探针使用，具体观察闭包只查询、不调用任何 token mutation API。`OpenThreadToken(TOKEN_QUERY, OpenAsSelf=TRUE)` 仅在 `ERROR_NO_TOKEN` 时读取进程 primary token，否则标记 unavailable，不把查询失败伪装成 primary token。固定回执包括 token 来源、归一化 IL、受限状态、logon SID 启用状态，以及 `TOKEN_MANDATORY_POLICY_NO_WRITE_UP`/`NEW_PROCESS_MIN` 两位；pipe open 失败时追加该调用的 Win32 错误码。观察失败不会改变原 open，客户端 desired access、share、creation disposition、flags 和 ACL/SACL 保持原值。依据微软的 [OpenThreadToken](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-openthreadtoken) 与 [`TOKEN_MANDATORY_POLICY`](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-token_mandatory_policy) 文档；不复制上游实现或代码。诊断 API 会拉长 `WaitNamedPipeW` 成功到 `CreateFileW` 之间的时间窗；微软也说明等待后实例状态仍可能变化，所以原生复验需确认失败仍可复现，不能将单次标签当作拒绝根因。Linux 上两份定向单测共 55 项通过，但不等于 Windows API 实测；提交后须用 x64/ARM64 workflow_dispatch 验证标签长度、双架构回执及实际失败阶段。
- **研究取舍：采纳该观测机制，暂缓任何权限/ACL 调整。**现有 token/DACL 解析器可复用，收益是把实际线程 token 与退出后的 primary-token 快照分开；代价是多次 `TOKEN_QUERY` 调用会增加 open 窗口延迟，且 `ERROR_NO_TOKEN` 回退语义仍待目标 Windows 原生确认。微软列出的 `OpenThreadToken` 最低客户端版本为 Windows XP；使用标准系统 API，不引入依赖或复制上游代码，因此无第三方许可负担。验收条件为 x64/ARM64 报告均有合法固定标签/错误码、原 `CreateFileW` 请求参数不变、失败阶段仍可复现；诊断本身不作为根因或 R2 readiness 证据。
- **边界：**x64/ARM64 均重现拒绝，Windows 自动模式保持关闭；Linux/macOS 仍 5/10；R2 Git broker 接入与 R3 Git SHA 锚定、workflow Reviewer 跨平台只读边界仍待验收。

## 2026-09-26 UTC：CI #210 同线程令牌复验

- **双架构原生结果：**手动 [CI #210 x64](https://github.com/ayukyo/icode/actions/runs/36247565458/job/108419708823) 与 [ARM64](https://github.com/ayukyo/icode/actions/runs/36247565458/job/108419708651) 都在标准用户 restricted-token probe 失败；固定回执包含 `client_open_access_denied+token_process+il_medium+restricted_no+logon_enabled+nwu_yes+npm_yes+dacl_present+ace_match+token_child_process+logon_enabled+restricted_no+access_allow+client_il_medium+pipe_il_absent+pipe_nwu_unavailable+token_nwu_yes:winerror=5`。其他 Python、workspace、Linux/macOS native、Windows Job/wheel 与 presentation 作业按其自身结果通过；不能替代失败的 Windows pipe gate。Linux/macOS native score 仍 `5/10`、`critical_passed=false`、`ready=false`。
- **结论边界：**`token_process` 表明该次同线程采样按严格无 impersonation-token 分支使用目标子进程的 primary token；这降低了“线程模拟令牌不同”的解释可能，但不会把用户态 `AccessCheck=allow` 变成内核 `CreateFileW` 的通过，也不能排除观察窗口/pipe 实例竞争或其他访问检查差异。实际错误为 Win32 5。没有改 DACL/SACL、token、desired access 或 CreateFile flags；Windows 自动模式仍关闭。
- **研究取舍：**并行只读核对 Codex runner 的命名管道 DACL/PID 验证与 Microsoft `CreateFileW`/`WaitNamedPipeW` 文档，采纳“必须检查客户端真实请求权限、创建端 DACL 与 client handle 打开结果分别验证”的方法；将等待成功与打开之间的实例变化保留为待实验风险，不据此归因。暂缓任何 ACL 放宽、提权或安全描述符改动；下一片继续只读/可控的时序与调用参数证据采集。

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

1. **已实现的基础锚点：**`base_commit_sha` 只表示任务开始时的提交；`initial_worktree_fingerprint` 与 `tested_worktree_fingerprint` 覆盖包括预存脏改动在内的快照，`diff_fingerprint` 保留本轮改动语义。回执与 Reviewer 终态校验均覆盖这些字段；快照摘要现包含文件类型、符号链接目标及 POSIX Git 可执行位，相关行为先 RED 后 GREEN。该快照仍不等于 Git tree。
2. **受测 tree 方案已收窄：**从 POSIX 仓库根以 no-follow 文件描述符只读扫描当前 Git 文件投影，用 Python 标准库按 Git object serialization 计算 tree OID；包含 staged/unstaged 当前工作树状态、未跟踪及 ignored 项，不触碰用户 index、不调用 `git add`/filters。以测试前后工作树 fingerprint 与 tree OID 一致作为可记录条件。结果 commit 需在后续切片与此 OID 精确比较；本切片不单独宣布 commit 已验证。Windows、子目录工作区、嵌套 `.git`/gitlink、特殊文件、路径竞态或不可读项一律不提供 OID。Attributes 不被读取或执行：其转换最多造成安全的不匹配，不能把 raw-worktree 哈希解释为 Git clean-filter 结果；commit tree 的相等只证明 tree 层路径/字节/模式一致，不含 ACL、xattr 或执行环境。
3. 对工作流 review 步骤只读命令边界完成跨平台原生验收；策略化 Reviewer 的只读文件权限与拒读子路径仍需证明能由同一 OS profile 强制组合；
4. 补足 Reviewer 短上下文终结器的真模型路径证据。Windows/其他平台门未过前继续 fail-closed，不能用本机 R3 回执锚定代替 R2 OS 沙箱验收。

## 2026-09-27 UTC：受测 tree 证据方案复核

- **竞品研究：**OpenCode `a42f393c850bec0c0f395fb91bf19b1ee8b31666` 用独立 Git 目录/index/对象库构造可撤销会话快照，但会按 ignore 筛选且不代表测试认证；Codex `b334d5b3f2d9441b95286a8c2af8c2152737d977` 提供 HEAD→worktree diff/未跟踪清单，本次未见测试结果 tree 绑定。详细源码链接、采纳/暂缓判断见[持续竞品对照](../../agent-landscape-live.md)。
- **方案判断：**Git 官方对象是由类型、长度与正文寻址，Git tree 由路径、模式与子对象 ID 构成；`write-tree` 仅写 index。为避免临时索引过程继承配置并执行 clean/process filter，本实现不调用 Git 来生成投影，而在 Python 中只算规范 OID、不写对象。官方 `gitattributes` 可改写 check-in 字节，故只将 OID 等值解释成最终 Git tree 字节相同；不匹配不推断测试失败，未知条目则不给 OID。
- **验收切片：**先覆盖 canonical object hash 与 Git CLI tree 的交叉测试、类型/模式/符号链接/字节路径排序、untracked+ignored 输入、SHA-1/SHA-256，以及测试前后净漂移与用户 index 未变化。真实 `result_commit_sha`/`^{tree}` 比对、receipt/reviewer 后验绑定和 Windows no-follow 实现仍是后续门槛。研究日期：2026-09-27 UTC。

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
