# R2 资源限制与统一违规回执实施门

- 日期：2026-09-29 Asia/Shanghai
- **CI #425 最新门结果（2026-10-01 Asia/Shanghai，commit `2e63d504adebf1c8adff3cee87b75e79084b9aee`）：**四个 Linux R2.2 原生 job（Ubuntu 22.04 x64/ARM64、Ubuntu latest x64、Ubuntu 24.04 ARM64）及 macOS Intel/Apple Silicon 原生 jobs 完成；Linux 上策略化 Reviewer 交集和真实 runner 链步骤均成功。Windows authenticated runner-pipe x64 [job](https://github.com/ayukyo/icode/actions/runs/36766864593/job/110063106459) 与 ARM64 [job](https://github.com/ayukyo/icode/actions/runs/36766864593/job/110063106527) 仍在 `CreateFileW` access denied；全轮 [CI #425](https://github.com/ayukyo/icode/actions/runs/36766864593) 仅这两个 job failure，官网 [#303](https://github.com/ayukyo/icode/actions/runs/36766864492) success。该 job 结果不关闭 `resource_limits`、`uniform_violation`、策略 readiness 或自动模式；本条不推导未取出的平台评分。`process_limit` 的 RL-0 计数口径仍待确认。
- **CI #422 R2 平台门复核（2026-10-01 Asia/Shanghai，commit `8231663de94ffa2a09e85d0d489db3ca75904fba`）：**Ubuntu 22.04 x64/ARM64 均 `8/10 critical_passed=true ready=false`；ubuntu-latest x64 与 Ubuntu 24.04 ARM 均 `7/10 critical_passed=false ready=false`（网络租约过期 probe skipped）；macOS Intel/Apple Silicon 均 `6/10 critical_passed=false ready=false`，数字 IPv4 Seatbelt rule unsupported、违规日志不计 conformance credit。Windows authenticated pipe x64/ARM64 仍在真实 `CreateFileW` 得到 WinError 5；本轮只是把已有 bounded target-access receipt 显示到公开 annotation，没有变更拒绝行为。Windows R3 directory/tree OID、workspace、Job cleanup、wheel、Python 3.11/3.12 子门通过；标准用户/AppContainer 可选诊断 skipped。详见 [CI #422](https://github.com/ayukyo/icode/actions/runs/36754441132) 与官网部署 [#300](https://github.com/ayukyo/icode/actions/runs/36754441011)。`process_limit` 的 RL-0 语义仍待用户决定；`resource_limits=false`、`uniform_violation=false`、policy readiness 与自动模式门槛不变，R2/R3 均未完成。
- **CI #417 R2 native 分数刷新（2026-10-01 Asia/Shanghai，commit `4e326b3ebfb03a1540692b89cc1ae1383317eeb0`）：**Ubuntu 22.04 x64/ARM64 均 `8/10 critical_passed=true ready=false`；ubuntu-latest x64 和 Ubuntu 24.04 ARM `7/10 critical_passed=false ready=false`（网络租约过期 probe skipped）；macOS Intel 与 Apple Silicon `6/10 critical_passed=false ready=false`，`process_group_cleanup=true` 但数字 IPv4 rule 仍 unsupported。Linux observed-command-bounds、seccomp receipt、22.04 network lease expiry 与 process cleanup 子探针 success，不填 `process_limit` 或 `uniform_violation` 的空证据；macOS Seatbelt violation log 为 observed，但 conformance credit none。Windows authenticated pipe 失败，其他 workspace/Job/wheel/R3 子门 success；可选 Windows 标准用户/AppContainer skipped。详见 [CI #417](https://github.com/ayukyo/icode/actions/runs/36740862698)；R2 不就绪、自动模式关闭。
- **CI #414 当前平台证据（2026-09-30 UTC，commit `abbffcc80140f99bf5eb5c712a6ae8e7d44a3a09`）：**Ubuntu 22.04 x64/ARM64 仍为 `8/10` 且 `ready=false`；其余 Ubuntu x64/ARM64 为 `7/10` 且 `ready=false`，网络租约 probe 为 skipped；macOS Intel/Apple Silicon 为 `6/10` 且 `ready=false`，数字 IPv4 Seatbelt 谓词仍 unsupported。Linux seccomp receipt probe 虽通过，仍不传入 `uniform_violation` 评分；Windows authenticated runner pipe x64/ARM64 两个 job 失败，其它 Windows R2.1 workspace、R2.3 Job cleanup/wheel 子门通过。完整作业结果见 [CI #414](https://github.com/ayukyo/icode/actions/runs/36731656189)。这些子门不能相互替代，R2/自动模式继续关闭。
- 状态：R2 资源限制和跨平台统一违规回执验收未完成；Linux deny-only `run_command` 已接入 USER_NOTIF 原生回执，CLI 对单类别和多类别回执均可展示；非 POSIX 不支持路径新增固定 CLI 提示和明确的未启动字段，但 MCP adapter、macOS/Windows 来源 parity、文件拒绝覆盖、`process_limit` 语义和平台门槛仍未闭合，能力评分不变
- 目标：把十项合同中的 `resource_limits`、`uniform_violation` 接入真实隔离命令路径，并提供跨平台可核验回执。
- 依据：[R2 跨平台隔离设计 §12.2、§13、§14](../specs/2026-09-23-r2-cross-platform-isolation-design.md)

## 已确认的边界

`resource_limits` 同时包括进程数、墙钟时间和输出量。`execution_broker` 已按策略实施墙钟 deadline、输出字节上限和进程组清理，但 `process_limit` 尚未传入 Linux/macOS 通用命令执行链。Windows Job Object 诊断代码设置过 `ActiveProcessLimit`，但目前没有接到 workbench 的真实 `run_command` 启动协议。因此策略字段、组件测试或当前的 8/10 Linux 分数都不能替代独立资源限制证据。

`uniform_violation` 要求真实操作系统沙箱的 DENY 经执行链成为稳定机器回执；仅有 `ToolRegistry` 应用层 `read_denied`/`write_denied` 的 `policy_denied` 回执不够。普通非零退出码、stderr 文本或错误号也不能单独推断是沙箱违规。满足合同至少要让同一真实负例通过 CLI/MCP 返回稳定错误码、脱敏用户提示及隔离违规摘要，并用允许路径正对照和普通程序失败反对照防止误分类。

## Linux 候选机制与本机实验

本机 user systemd 可创建 transient scope；只读检查显示当前用户 manager 可达，但其 cgroup `Delegate=no`，工程进程不能直接管理 cgroup 子树。临时执行 `systemd-run --user --scope --property=TasksMax=1` 时，scope 内 Python 子进程创建被 `EAGAIN` 拒绝；相同载荷使用 `TasksMax=2` 时子进程退出 0。另一个实验令 scope 内根进程启动 `setsid` 后代并退出：`systemd-run` 客户端返回后 unit 仍 active，显式 `systemctl --user stop <unit>` 后 unit 才变为 inactive。

这证明当前机器上 systemd transient scope 的任务限额与 unit 清理原语可运行，不证明 ICODE 已接线，也不证明所有 Linux 主机有 user manager、能设 `TasksMax` 或具有相同生命周期语义。实验使用宿主 `/usr/bin/python3`，并未修改 ICODE 源码。systemd [`TasksMax=`](https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html#TasksMax=) 使用任务配额；Linux 官方 [cgroup v2 PID controller 文档](https://docs.kernel.org/admin-guide/cgroup-v2.html#pid)说明限额按内核 task/TID 计数，超过 `pids.max` 的 `fork()`/`clone()` 会收到 `EAGAIN`。因此它也限制线程创建，和 Windows Job 的活动进程口径不完全相同。

若选择该路线，必须在每个命令启动前确认限制已由可信 systemd manager 应用；缺 manager、scope 创建失败、属性无效或 unit 身份无法确认时，payload 不得启动。执行返回、超时、输出超限、取消及异常路径都须显式停止该唯一 scope，并验证 unit 已 inactive 且其后代无残留。不得以宿主全局 `RLIMIT_NPROC` 代替单工单限制；不得把仅同进程组回收记成 cgroup 清理。

## 分阶段退出门

| 子阶段 | 实施范围 | 必须通过的退出条件 | 不通过时 |
|---|---|---|---|
| RL-0 | 固定 `process_limit` 的计数口径：是否包含根命令、helper、线程及其他并发进程 | Linux、Windows、macOS 的语义和可接受差异得到明确记录；用户尚未确认时不改字段含义 | 保持 `resource_limits=false`，不开始影响命令行为的集成 |
| RL-1 | Linux 原生执行链接入 per-task 限额候选 | 同一 payload cap 内成功、超限拒绝；deadline/output cap 真正通过 Agent 命令入口；scope 创建失败前无 payload marker；正常/超时/脱组后代清理与无残留均有正反对照 | capability 不加分，R2 Linux 自动模式保持关闭 |
| RL-2 | Windows spawn 协议传递上限并由真实 Job 生效 | `process_limit` 从 policy 经 runner IPC 到 Job Object；同载荷阈值正反对照；超时及异常后确认整 Job 回收 | 仅保留组件诊断，不开放 Windows 自动模式 |
| RL-3 | macOS 任务级进程限制可行性与真实探针 | 不用 per-user 全局限额冒充 per-task 限制；有真实 Seatbelt/受支持 OS mechanism 才计分 | 无合格机制时保持未验证，不能用进程组清理补分 |
| VR-1 | 原生 DENY 到统一回执 | 三平台真实后端/执行 broker 负例 + 允许路径正例 + 普通 exit 13 反例；CLI/MCP 稳定 code、同义提示、脱敏违规摘要一致 | 不计 `uniform_violation`；禁止按 stderr 文本或通用非零码猜测 |
| RL/VR final | 汇总各平台直接证据 | 证据来自真实 Agent/workbench 执行链，环境 skip 不加分；每个平台满足 §14 的 90% 与关键项门槛 | 保持 `policy_contract_ready=false` 和自动执行关闭 |

## 并行上游对照与取舍

Codex 固定快照 [`21eb35513df478a2a090bfc2c0293caaf435b36d`](https://github.com/openai/codex/commit/21eb35513df478a2a090bfc2c0293caaf435b36d) 中的 deadline、输出缓冲、进程组清理可作为宿主监督结构参考；Unified Exec 的 tracked-session 数不能作为任务进程上限。Codex 的内部 OS violation 分类可作为脱敏分类测试参考，但未发现其公开工具回执有统一机器错误码。相关源码事实和采纳决策记录在[持续竞品对照](../../agent-landscape-live.md)。本计划不复制代码、不增加运行时依赖，也不据上游行为推断 ICODE 能力。

本计划不改变 worker 网络默认 `DENY`、macOS 地址范围门槛、`policy_contract_ready`、workbench 自动模式或现有 capability 评分。macOS 的 `localhost` 同端口规则和 `process_limit` 是否把线程计入两项用户决定仍待答复；为获取直接内核行为证据，允许新增不接入产品的原生 test-only 诊断，但答复前不放宽策略或评分。

## 2026-09-28：应用策略层统一拒绝回执（已落地，非 OS 验收）

- `ToolRegistry` 文件读取/写入拒绝与 `AgentLoop` Guard 拒绝现在都返回稳定 `error_code=policy_denied` 和 `violation_receipt`；CLI 对两类路径都显示同一普通语言提示。拒绝结果事件不转发动态判定原因，`LoopResult.render()` 也不再回显 Guard 拒绝细节。
- 回执固定标记 `enforcement_layer=application_policy` 与 `os_enforced=false`，只记录受限工具名和静态类别；非标准工具名收敛为 `other`，避免把原始标签写入回执。既有细分 `meta.error` 保留，兼容原调用方。
- RED 新用例先观察到缺字段、拒绝提示未到达 CLI、报告回显动态参数及成功结果机器码碰撞，再实现；5 项聚焦回归通过；全仓 `python -m unittest` 为 1,094 项通过、25 项条件跳过。
- **不改变 `uniform_violation` 评分：**上述结果是调用进入 OS 后端前的应用策略拒绝，明确不证明原生 DENY；真实 OS 负例、允许路径正例、普通 `exit 13` 反例及 CLI/MCP 原生回执 parity 仍是 VR-1 门槛。

## 2026-09-28 Asia/Shanghai：Codex / OpenHands 原生拒绝回执复核

- **Codex 固定版本：**`rust-v0.157.1`，SHA `36650394c5b38c2990ccf2a3457165ca3e9d9726`，Apache-2.0；只代表此发布快照。Linux seccomp 确实可对匹配 syscall 返回 `EPERM`，但源码里的 `is_likely_sandbox_denied` 结合非零退出与输出文本推断“可能的沙箱拒绝”；`SandboxViolationEvent` 注释同样说明来自进程结果推断。公开工具路径没有把每次内核拒绝稳定返回为带 syscall 身份的工具回执；所查分类测试使用合成输出/退出码，非真实 syscall 端到端测试。`--log-denials` 的固定实现仅支持 macOS，Linux 分支不提供该日志能力。注意同名 `landlock.rs` 里另有未用于默认 bubblewrap 文件系统沙箱的 Landlock 路径，不应混淆两者。
- **OpenHands 固定版本：**SDK SHA `d77ada7a030b3acaa82593d402632680361dfe42`，MIT；`LocalWorkspace`/`TerminalObservation` 使用通用命令结果，hook 的 `UserRejectObservation` 是应用层拒绝。未发现通用 OS-deny 机器码或真实 syscall deny 到工具回执的 SDK 路径。
- **系统审计候选：**Linux Landlock audit/trace events 可记录内核拒绝，但官方文档描述其为系统级流并要求审计/BPF 权限，明确不是为无特权的逐沙箱监控设计；不符合默认仅 Python 包安装、无需特权服务的产品约束。参考 [Landlock system-wide management](https://docs.kernel.org/admin-guide/LSM/landlock.html)、[userspace API](https://docs.kernel.org/userspace-api/landlock.html) 与 [trace events](https://docs.kernel.org/next/trace/events-landlock.html)。
- **ICODE 取舍：**采纳把 `os_enforcer`、`tool_output_inference`、`application_policy` 分层且显式报告来源；暂缓将 Codex 文本/退出码启发式作为可信 `uniform_violation`，不加入提权 audit/BPF 守护进程。现有 `application_policy` 回执仍明确 `os_enforced=false`；只有真实后端拒绝到 broker 的可验证链路、允许路径对照、普通失败反例及 CLI/MCP 一致性全部通过才计分。Linux `8/10` 不变，R2 自动模式关闭。
- **源码链接：**[Codex denial classification](https://github.com/openai/codex/blob/36650394c5b38c2990ccf2a3457165ca3e9d9726/codex-rs/sandboxing/src/denial.rs)、[violation classification](https://github.com/openai/codex/blob/36650394c5b38c2990ccf2a3457165ca3e9d9726/codex-rs/sandboxing/src/violation.rs)、[tool events](https://github.com/openai/codex/blob/36650394c5b38c2990ccf2a3457165ca3e9d9726/codex-rs/core/src/tools/events.rs)、[OpenHands command result](https://github.com/OpenHands/software-agent-sdk/blob/d77ada7a030b3acaa82593d402632680361dfe42/openhands-sdk/openhands/sdk/workspace/models.py)。

## 2026-09-30 Asia/Shanghai：Codex / Gemini OS 拒绝回执复核

- **固定来源与许可：**Codex 主线观察快照 [`67727e7`](https://github.com/openai/codex/commit/67727e7cf114cf3e1b71db368d74b24e32f6cb12)，Cargo workspace 版本 `0.0.0`、Apache-2.0；Gemini CLI [`38700b4`](https://github.com/google-gemini/gemini-cli/commit/38700b4b38bf387dafded6c97c3f190d084b49e9)，`0.64.0-nightly.20260929.gd75234cae`、Apache-2.0。均为该日源码观察，不代表后续主线。
- **核对事实与采纳判断：**所查 Codex 文件拒绝路径将输出/退出状态分类为 sandbox violation 并记录 tracing warning；统一执行工具仍返回原始输出和退出码，未发现稳定 OS-deny tool receipt。Gemini 有 bwrap/Seatbelt/Windows OS enforcement，但拒绝 parser 从命令输出/错误文本匹配 `permission denied`、`EPERM`、网络错误等，再发出扩权提示；parser 结果没有 enforcement provenance。真实集成负例证明受限命令失败，不证明结构化 OS 事件回执；分类单测使用合成文本。故**采纳** enforcement provenance 与用户文案、机器码分层；**不采纳**文本/退出码启发式作为 OS 回执或能力证据；无源码复制、无运行依赖和许可证义务增加。
- **ICODE 现状与下一步：**Linux `LandlockSandbox + seccomp USER_NOTIF` 的真实 AF_INET DENY 已贯穿 broker→ToolResult→AgentLoop→CLI，并以普通 exit 13、伪造 `Permission denied` 输出和 Landlock 文件拒绝为反例；但目前只覆盖 seccomp socket 类来源，MCP runtime adapter、macOS/Windows来源 parity 和 OS 文件拒绝仍缺。CI #414 Linux receipt diagnostic 通过，但不计 `uniform_violation`；故继续保留 fail-closed。更完整的固定源码位置与逐项取舍见下列上游链接；本次观察日为 2026-09-30。
- **源码锚点：**[Codex 分类与 warning](https://github.com/openai/codex/blob/67727e7cf114cf3e1b71db368d74b24e32f6cb12/codex-rs/sandboxing/src/violation.rs#L135-L233)、[Codex 工具结果](https://github.com/openai/codex/blob/67727e7cf114cf3e1b71db368d74b24e32f6cb12/codex-rs/core/src/tools/handlers/unified_exec/exec_command.rs#L445-L470)、[Gemini 文本启发式](https://github.com/google-gemini/gemini-cli/blob/38700b4b38bf387dafded6c97c3f190d084b49e9/packages/core/src/sandbox/utils/sandboxDenialUtils.ts#L60-L169)、[Gemini 扩权提示路径](https://github.com/google-gemini/gemini-cli/blob/38700b4b38bf387dafded6c97c3f190d084b49e9/packages/core/src/tools/shell.ts#L964-L1108)、[Gemini integration test](https://github.com/google-gemini/gemini-cli/blob/38700b4b38bf387dafded6c97c3f190d084b49e9/packages/core/src/services/sandboxManager.integration.test.ts#L442-L562)。

## 2026-09-28 Asia/Shanghai：macOS Seatbelt 代理端口边界复核

- Codex 固定源码 `openai/codex@21eb35513df478a2a090bfc2c0293caaf435b36d` 先绑定随机 `127.0.0.1` listener，再以 `localhost:<port>` 生成 Seatbelt 出站规则。该机制按端口授权，不绑定代理进程身份，也不能单独证明地址仅为 `127.0.0.1`。
- Microsoft MXC 的固定版本说明称 `localhost` 规则可能匹配宿主所有本地地址（包括 LAN IP）上的同端口服务；Apple 官方材料未明确给出这一 SBPL 规则的精确匹配语义。因此该范围须在 Intel/Apple Silicon 原生 profile 中以 LAN-bound same-port decoy 等负例实测，且不能把上游描述当作 Apple 保证。
- **当前决策：等待用户确认是否接受“宿主本地任意地址上的唯一 task-scoped 随机代理端口”边界。**确认前保持 macOS 网络 DENY，不连接 CONNECT candidate，不计 `network_temporary_allowlist`。若要求严格 loopback 地址/代理进程身份绑定，Seatbelt 端口规则不足，需评估 AF_UNIX path-scoped 通道或另有授权的系统机制。来源、验收向量与采纳/暂缓记录见[持续竞品对照](../../agent-landscape-live.md)。

## 2026-09-28 Asia/Shanghai：任务级 process_limit 平台语义复核

- **真实接线现状：**`SandboxPolicy.process_limit` 已有 schema/正整数校验，但通用 `execution_broker.execute_policy_command()` 未传给 enforcer，Windows `windows_runner_protocol` spawn 请求也不含此字段。`run_windows_job()` 设置 `ActiveProcessLimit` 且有组件级 cap=1/2 正反回归，尚不证明真实 Workbench 命令路径。
- **平台语义：**Linux cgroup v2 `pids.max` 是子树硬限额、超限 fork/clone 失败，但 PID controller 按 TID/task 统计，线程也计入；需 systemd manager/cgroup delegation 能力探测，缺失时 payload 不启动。Windows [Job `ActiveProcessLimit`](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_limit_information#members)按 Job 中活跃进程计数。macOS [RLIMIT_NPROC](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/setrlimit.2.html)和 launchd [`NumberOfProcesses`](https://github.com/apple-oss-distributions/launchd/blob/main/man/launchd.plist.5#L1807-L1818)按 UID，无法表达 per-ticket cap；当前 Seatbelt 无等价计数原语。
- **Codex 对照：**固定 SHA `21eb35513df478a2a090bfc2c0293caaf435b36d` 的 `MAX_UNIFIED_EXEC_PROCESSES=64` 是 tracked session LRU soft cap（[常量](https://github.com/openai/codex/blob/21eb35513df478a2a090bfc2c0293caaf435b36d/codex-rs/core/src/unified_exec/mod.rs#L832) · [清理逻辑](https://github.com/openai/codex/blob/21eb35513df478a2a090bfc2c0293caaf435b36d/codex-rs/core/src/unified_exec/process_manager.rs#L1650-L1688)），不是 OS 级子进程限制；所查 Windows Job helper 也未设置 `ACTIVE_PROCESS`。[license](https://github.com/openai/codex/blob/21eb35513df478a2a090bfc2c0293caaf435b36d/LICENSE#L588-L590) 为 Apache-2.0。
- **取舍与验收：**保留 RL-0，不改变 `process_limit` 计数合同，等待确认是否包含命令根/helper、以及是否接受 Linux 将线程计入。下一实现必须贯通 policy→Workbench `run_command`→broker→原生 enforcer；Linux cap=2 根+子进程正例、cap=1 超限无 marker、真实 cgroup membership/`pids.events`、缺 manager/delegation 时无 payload；Windows policy/IPC→Job 正反例与 Job assignment 失败无 marker；macOS 无机制时返回 `unsupported` 且不计分，禁止用 per-user `RLIMIT_NPROC` 假装单任务上限。所有平台另需宽限正对照及普通 exit 13 不误报。macOS 若 `process_limit` 与 `uniform_violation` 都未通过，按 9/10 合同无法就绪。Codex/Linux/Windows/Apple 一手来源和观察日期见[持续竞品对照](../../agent-landscape-live.md)。

## 2026-09-28 Asia/Shanghai：Seatbelt localhost 端口范围 test-only 诊断

- 在 `tests/test_isolation.py` 增加原生 macOS 专项用例，并挂入现有 macOS native-probe CI 矩阵；它仅对该测试子进程使用 Codex 式 `localhost:<random_port>` 规则，不修改生产 profile、网络默认 DENY、能力评分或自动模式。
- 用 loopback listener 验证该端口正例、另一 loopback 端口拒绝；再对宿主已分配的非 loopback 地址同端口发起不发送数据的连接，不建立 LAN listener。按 `EPERM`/`EACCES`、`ECONNREFUSED` 分类；不可分类时跳过并明确提示。无公网目标。
- 此无监听探针低于 LAN-bound same-port decoy 的证据强度，不能证明与活跃本机服务的完整交互语义；实际 macOS runner 结果待 CI。用户对产品边界的决定仍待答复，生产授权继续 DENY。

## 2026-09-28 Asia/Shanghai：macOS localhost 诊断 CI 失败的安全化观测

- **远端状态：**commit `4e98e76f59aea218020f65a7c27b0c37ae5b6edf` 的 [CI #271](https://github.com/ayukyo/icode/actions/runs/36370796374) 中 Linux/Windows、Python 3.11/3.12 以及官网部署均成功；macOS ARM64 与 Intel 两个 native job 都在 `Diagnose Seatbelt localhost random-port address scope` 失败。可匿名读取的 GitHub job/check 注解只给出步骤非零退出码和既有 `6/10, critical_passed=false, ready=false` 汇总，未暴露 unittest 断言/阶段输出；因此当前不推断失败阶段或 Seatbelt 行为。
- **本地边界：**诊断用例在 Linux 按设计跳过，不能作为 macOS 通过证据。该步骤此前只有最终汇总 notice，loopback 正例/异端口拒绝任一步失败时均缺少可公开机器分类。
- **本次处理：**在每个本机 socket probe 完成后写出不含地址、端口、路径的固定阶段与结果 notice；子进程退出异常、缺失结果标记或正/负对照分类不符时写出脱敏 error annotation。仅增强观测，不改变 Seatbelt profile、产品 network DENY、评分或自动模式。提交后须重新收集双架构原生结果，才能决定后续实现。

## 2026-09-28 Asia/Shanghai：macOS probe 将 socket 创建纳入拒绝分类

- **复跑证据：**commit `fbf2960b379b` 的 CI [run 36372163484](https://github.com/ayukyo/icode/actions/runs/36372163484) 中 Intel 与 Apple Silicon 两个 macOS job 均输出安全注解 `stage=loopback-allowed subprocess_exit=1 marker_count=0`，说明失败发生在正例探针产生结果标记之前。此次信息仍不足以证明 Seatbelt 规则行为。
- **测试缺陷与修正：**子进程探针把 `socket.socket()` 和 `settimeout()` 放在 `try/except OSError` 外；若其中任一受策略影响，子进程会退出而不是返回 errno。现将创建/设置超时也纳入同一受控分类，并仅在对象已创建时关闭；这样拒绝会成为带数字 errno 的受限标记，再由父测试按预期分类。Linux 无法运行 Seatbelt 原生分支；修改后的 macOS 双架构 CI 尚待结果。
- **边界：**这是测试观测正确性修复，不放宽 profile、不将策略拒绝当成成功、不改生产网络 DENY、macOS 地址范围决策、评分或自动模式。若 loopback 正例报告拒绝，仍需另行处理机制边界。

## 2026-09-28 Asia/Shanghai：profile 启动与 socket probe 分层对照

- **复跑结果：**commit `38c241a26099` 的 CI [run 36372816346](https://github.com/ayukyo/icode/actions/runs/36372816346) 在两个 macOS 架构仍于 `loopback-allowed` 返回 `subprocess_exit=1, marker_count=0`；将 socket 构造和 timeout 设置移入 `try/except OSError` 后结果未变，因此不能把此前的异常归因为 socket syscall 被策略拒绝。
- **下一步诊断：**新增同一 Seatbelt profile 下只启动 Python 并打印固定标记的前置对照，先判断 profile/解释器是否可启动，再运行 loopback socket probe。回执仅包含阶段、退出码、固定标记数和 stderr 是否非空；不会回显 stderr、路径、地址或端口。
- **门槛：**本机 Linux 的相关测试只能按平台跳过；下一次 Intel/Apple Silicon 原生结果是确认失败在启动层还是 socket 层的必要证据。生产网络授权与评分不变。

## 2026-09-28 Asia/Shanghai：profile startup 失败的 stderr 词类回执

- **复跑证据：**commit `abe6ef55ee9a` 的 [CI run 36373392322](https://github.com/ayukyo/icode/actions/runs/36373392322) 在 Intel 与 Apple Silicon 上都于 `profile-startup` 失败：进程退出 1、固定标记数 0、stderr 非空。该结果说明 Python 在该 profile 下未成功启动，但尚不能区分 SBPL 解析、执行器启动或 runner 约束。
- **观测修改：**下一回执仅由固定词类形成 `sandbox_exec` / `profile` / `syntax_or_invalid` / `permission` / `loader` / `launch` 标签；绝不输出 stderr 原文、用户目录、地址或端口。相同 profile 的启动 A/B 和后续 loopback 探针仍分别运行。
- **边界：**目前不能将该现象归因于产品 Seatbelt 网络边界或修改生产策略；需等待新一轮双架构原生 CI 的安全类别结果。

## 2026-09-28 Asia/Shanghai：host proxy 授权前关闭回执竞态

- `serve_once()` 在不完整 CONNECT 请求头期间遇到 `server.close()`，曾在 socket/lease 错误分支未观察 `_closed` 时偶发返回 `True`，与其“关闭/停机返回 `False`”文档契约不一致。
- 更新路径：无已授权 tunnel 时，在错误处理后用既有锁观察 `_closed`；若 shutdown 已线性化则返回 `False`。已授权 tunnel 在 relay I/O 错误时仍视为本次请求已处理，保持原有 `True` 语义。
- TDD 证据：旧实现对 shutdown 断言 20 轮中 16 次失败；修复后 20/20 通过。proxy server 套件 28 项通过，提交前 `preflight --only tests` 通过。此修复不改变 lease 授权、网络 DENY、策略评分或自动模式。

## 2026-09-28 Asia/Shanghai：Seatbelt startup 失败边界与固定上游对照

- **复跑证据：**commit `c3a67a1` 的 CI [run 36374038529](https://github.com/ayukyo/icode/actions/runs/36374038529) 中 Apple Silicon 与 Intel 原生 job 都报告 `stage=profile-startup subprocess_exit=1 marker_count=0 stderr_tags=other`；因此目前只确认失败早于 socket，不确认是动态 `localhost:<port>` 规则、Python 启动、profile 解析或平台限制。
- **固定上游核对：**Codex `openai/codex@21eb35513df478a2a090bfc2c0293caaf435b36d` 的逐端口 SBPL 规则与 ICODE 测试追加的字面相同，但 Codex profile 还组合 base、文件、动态网络与网络策略等规则；其公开测试核验生成的 profile 文本，没有证据证明该固定测试在原生 Seatbelt 下实际 connect。Apple 公开 entitlement 文档也未规定该 raw SBPL 谓词的精确语法/匹配范围。故不复制 Codex 的额外授权策略，不把代码文本相同当作运行行为相同。
- **下一组可证伪对照：**仅在测试子进程依次运行 ICODE 基础 profile + `/usr/bin/true`、Python `-S`、普通 Python，再追加随机端口规则重复普通 Python；为每个阶段输出固定 stage/退出码/标记数/白名单 stderr 类别，固定工作目录，不输出原始 stderr、路径、地址或端口。若基础 profile 的 true 失败，调查执行器/profile；若 true 成功而 `-S` 失败，调查解释器/运行库访问；若 `-S` 成功而普通 Python 失败，调查 site 初始化路径；若只有追加规则失败，才将调查转向该 SBPL 规则。此诊断不发送网络数据，不改生产 profile、network DENY、能力分数或自动模式。
- **本机验证边界：**stderr 分类回归与语法检查可在 Linux 执行；Seatbelt 原生诊断按平台跳过，不计 macOS 证据。修改后必须回收 Intel 和 Apple Silicon 原生 runner 输出，才能继续判断根因。当前 macOS 仍为 `6/10, critical_passed=false, ready=false`。

## 2026-09-28 Asia/Shanghai：macOS profile startup 已通过、socket 子进程仍异常

- **远端分层结果：**commit `a57a93e` 的 CI [run 36375272942](https://github.com/ayukyo/icode/actions/runs/36375272942) 双架构都通过 `base-executable`、`base-python-no-site`、`base-python-site` 和 `port-rule-python-site`，随后在 `loopback-allowed` 探针退出 1、没有结果标记，stderr 仅命中固定 `python_runtime` 类别。基础 profile、普通 Python 初始化和追加端口规则后的解释器启动因此已有正向证据；网络 connect/send 是否执行成功仍无证据。
- **可排除范围：**本次不再把失败描述为 profile startup 失败；前述 Python venv/site 启动路径假设在这些启动控制中未复现。尚未区分 socket 模块导入、socket 创建/timeout、connect、send 或探针内部未捕获异常，不推断为 Seatbelt 拒绝或授权。
- **本次处理：**子进程现输出固定阶段 `socket-imported`/`socket-created`/`timeout-set`/`connect`/`send`；OSError 回执附数字 errno 与失败阶段，annotation 只包含有序固定阶段标签和白名单 Python 异常类别，不打印异常正文。保留连接正反对照，不把不可分类结果降为 skip。Linux 本机分类/语法/全量测试守护通过；Seatbelt 原生用例按平台跳过，下一 commit 的 Intel 与 Apple Silicon CI 才能验证这些阶段标签。产品网络 DENY、评分、自动模式不变。

## 2026-09-28 Asia/Shanghai：macOS 探针 socket import 前失败的上下文一致化

- **远端证据：**commit `4359b64` 的 CI [run 36376053831](https://github.com/ayukyo/icode/actions/runs/36376053831) 两架构的四个启动对照均通过；socket 探针失败时 `child_stages=none` 且 stderr 分类为 `python_runtime+python_os_error`。因为第一个阶段标记原先位于 `import socket` 之后，这说明异常发生在该标记之前或导入过程中，不能归因于 connect/send。
- **代码差异与推断：**启动控制显式使用临时 workspace 作为 `cwd`，而原 socket 子进程继承 CI checkout cwd；该 cwd 不在 test-only profile 的 workspace 读授权内。此上下文差异可由源码直接确认；它是否就是 Python socket 导入期间权限异常的根因，仍待新原生 runner 验证。
- **本次处理：**socket 子进程与启动控制统一 `cwd=workspace`，并将 `import socket` 放入阶段化 OSError 捕获区。若导入返回权限 errno，会标记 `socket-import`；若仍为非 OSError Python 异常，则只输出固定异常类别和已到达阶段，不泄漏原文。只改诊断测试，不改产品 profile/网络 DENY/评分/自动模式。Linux 全量测试通过；Seatbelt 原生效果待下一 CI。

## 2026-09-28 Asia/Shanghai：Linux seccomp USER_NOTIF 原生回执试验原型

- **上游研究：**Linux 内核 [`seccomp filter` 官方文档](https://docs.kernel.org/userspace-api/seccomp_filter.html)定义了 `SECCOMP_RET_USER_NOTIF`、`NEW_LISTENER`、listener 传递与 broker `NOTIF_SEND` 响应；无特权进程先设置 `no_new_privs` 后可建立过滤器。该机制的系统调用结果由接收通知的 broker 决定，所以回执必须如实写成“内核通知到达 + ICODE broker 回答 EPERM”，不是独立于 broker 的内核审计结论。Codex 固定版本 `36650394c5b38c2990ccf2a3457165ca3e9d9726` 的 [`denial.rs`](https://github.com/openai/codex/blob/36650394c5b38c2990ccf2a3457165ca3e9d9726/codex-rs/sandboxing/src/denial.rs) 仍结合退出与输出推测 likely denial；OpenHands 固定版本 `d77ada7a030b3acaa82593d402632680361dfe42` 的 [`CommandResult`](https://github.com/OpenHands/software-agent-sdk/blob/d77ada7a030b3acaa82593d402632680361dfe42/openhands-sdk/openhands/sdk/workspace/models.py) 仍是通用命令结果字段。只借鉴内核监督原语及显式结果分层，没有复制代码；Codex 为 Apache-2.0、OpenHands 为 MIT，本原型无第三方代码/运行依赖。
- **当前实现与窄切片：**产品 Linux helper 的默认网络过滤仍直接返回 `SECCOMP_RET_ERRNO|EPERM`，没有通知通道。新增的 C probe 只在 `tests/fixtures/native/`，通过 `SCM_RIGHTS` 将 USER_NOTIF listener 交给测试父进程，父端确认仅为 `socket(AF_INET, ...)` 后明确回复 `-EPERM`；`AF_UNIX socketpair()` 是允许正例。拒绝握手时载荷不启动；普通 exit 13 单独验证不产生通知标记。CI 输出显式 `conformance_credit=none`，不接入 `ExecutionResult`、CLI/MCP、产品策略或评分。
- **取舍：**采纳 USER_NOTIF 作为 Linux 私有机制原型，暂缓产品接线；其生产化还需将 listener 从当前 PID namespace 安全交给 broker、启动前建立观察与失败关闭，并定义通知器退出/覆盖不完整语义。macOS `log stream` 仅是待原生验证的系统日志观察候选，空流不得解释为无拒绝；Windows Job Object 不提供通用文件/网络违规事件，三平台 `uniform_violation` 仍不计分。Landlock 普通文件拒绝亦没有本原型可用的通用逐操作通知。
- **验收结果：**本机三项 Linux 用例、20 轮重复、全量 unittest 均通过。推送提交 `48c465f` 的 [CI #285](https://github.com/ayukyo/icode/actions/runs/36392124437) 成功，四个 Ubuntu native job（x86_64/ARM64，22.04 与当前 runner）均包含并通过该 test-only probe；Apple Silicon 与 Intel macOS job 也在同一 run 通过其既有诊断。Linux 评分仍随 runner 不同（最新 runner/24.04 ARM 为 7/10、critical 未通过；22.04 两架构为 8/10、critical 通过），所有平台 `ready=false`。这只验证 Linux syscall 机制，不代表 workbench/broker 产品路径闭环；完成真实 broker/CLI/MCP 正反例和跨平台来源 parity 前，`uniform_violation` 仍不计分。本阶段不改变 `resource_limits=false`、`uniform_violation=false`、自动模式或能力评分。

## 2026-09-28 Asia/Shanghai：macOS Seatbelt 原生拒绝日志 test-only 探针

- **上游证据：**Apple 的[沙箱违规诊断文档](https://developer.apple.com/documentation/security/discovering-and-diagnosing-app-sandbox-violations)建议在 Console 中按 `com.apple.sandbox.reporting` / `violation` 检索，并说明部分系统库拒绝可能出现在 app stderr；macOS [`log(1)`](https://man.freebsd.org/cgi/man.cgi?apropos=0&manpath=macOS+13.6.5&query=log&sektion=1)文档定义 `ndjson`、`--level debug` 和 predicate 查询接口，但没有承诺每个 deny 都会被 CLI 实时输出或给出稳定字段合同。固定 Codex SHA [`1cc7e2361237ce7244430ee1d581c77f95c57ac8`](https://github.com/openai/codex/commit/1cc7e2361237ce7244430ee1d581c77f95c57ac8) 的 [Seatbelt logger](https://github.com/openai/codex/blob/1cc7e2361237ce7244430ee1d581c77f95c57ac8/codex-rs/cli/src/debug_sandbox/seatbelt.rs#L52-L114) 同时筛选 Sandbox kernel sender 与 reporting subsystem，并解析 `eventMessage` 中的进程 PID/能力；这是实现参考，不保证其他系统版本/runner 上的日志可见性。
- **ICODE 本机改动：**仅扩展 `tests/macos_violation_log_probe.py` 的原生诊断：请求 debug NDJSON，同时读取 stdout/stderr，以 kernel sender、Apple reporting subsystem 和 Sandbox 消息作为候选筛选；对日志总量/行数设限，诊断只输出固定类别与计数，不保留或打印原始日志正文、路径或 PID。日志格式错误、观察器失败或超时均保持 inconclusive；只有解析到目标进程 PID 与目标 capability 的精确事件才报告 observed。未接入产品执行器、ExecutionResult、CLI/MCP 或能力计分。
- **原生结果：**提交 [`a2b54ee`](https://github.com/ayukyo/icode/commit/a2b54ee8c8ac51d9bfc3cfbbd32dd348b4533074) 的 [CI #289 Intel job](https://github.com/ayukyo/icode/actions/runs/36402344430/job/108862919786) 与 [Apple Silicon job](https://github.com/ayukyo/icode/actions/runs/36402344430/job/108862919787) 均输出 `macos-sandbox-violation-probe status=observed capability=file-read-data conformance_credit=none`；受控子进程 stderr 的拒绝与 PID/capability 精确日志事件在两个 runner 上均有观测。全量 workflow 最终 success；此 test-only 结果仍不给能力分。
- **采纳 / 暂缓：**采纳 bounded、脱敏、精确 PID/capability 的原生正例作为后续 observer 研究基础；暂缓将统一日志用作产品级可信回执。该通道可能缺记录或延迟，空日志不证明无拒绝；还需 observer 启动前屏障、错误/丢失的不完整状态、允许路径对照、普通 exit 13 反例及真实 broker→CLI/MCP parity。`uniform_violation=false`、macOS `6/10`、自动模式关闭不变；不复制 Codex 代码、不增加依赖或许可证义务。
- **并行网络边界结果：**同一 CI #289 的 Intel 与 Apple Silicon job 均验证 `localhost:<port>` 可连接宿主非 loopback 活跃同端口 listener 并发送 canary；获准 loopback 正例成功、其它 loopback 端口拒绝。该行为不能满足严格 loopback 地址边界，产品 worker 网络继续 DENY，不计 `network_temporary_allowlist`。

## 2026-09-28 Asia/Shanghai：macOS AF_UNIX 代理通道候选（原语通过、产品接入暂缓）

- **上游对照与采纳边界：**Anthropic `sandbox-runtime` 固定提交 `ddbeb74711c4097014ef3056791efa83f553116c`（Apache-2.0）把 `system-socket(AF_UNIX)`、`network-bind` 与按目录 `network-outbound (remote unix-socket (subpath ...))` 分开；其真实 macOS 测试通过的是沙箱内部 bind/connect，不是“宿主预监听 + 沙箱仅 connect”的代理闭环。Codex 固定提交 `44fe510ce3ee61c8ef623adcbf89b901c73ddd61`（Apache-2.0）也生成路径限定 UDS 规则，但所查原生 TCP 与 daemon deny 测试都不足以证明受限 profile 的 allowlisted UDS 正连。Apple DTS 明确 raw SBPL 面向第三方未文档化/支持且 `sandbox-exec` 已弃用；上游 CI 不能升格为 Apple 平台合同。详见[持续竞品对照](../../agent-landscape-live.md)。
- **ICODE test-only 探针：**新增 `tests/macos_unix_socket_probe.py` 和 `tests/test_macos_unix_socket_probe.py`，只在现有 macOS Intel/Apple Silicon native job 执行。基础策略仍 deny-default；测试候选只追加 `AF_UNIX` 与专用私有目录的 outbound subpath，以及连接所需的只读 metadata/existence，不给 `network-bind`、TCP/IP 或 wildcard 网络权限。宿主预先监听该目录内 socket；子进程须收发固定 canary、不能 unlink 宿主 socket，且活跃 sibling UDS、loopback TCP 都须被拒。输出仅固定结果类别，不含路径或数据。独立目录必须在工作区可写根之外，因为 subpath 是目录级授权，不是 socket identity。
- **双架构原生结果（CI #294）：**[macOS Intel job](https://github.com/ayukyo/icode/actions/runs/36414729151/job/108903016393) 与 [Apple Silicon job](https://github.com/ayukyo/icode/actions/runs/36414729151/job/108903016255) 均记录 `approved_unix=connected_payload_verified=yes other_unix=denied tcp_loopback=denied conformance_credit=none`。故 test-only profile 证明了本轮 runner 上宿主预监听 UDS canary 正例、工作区 sibling UDS 与 loopback TCP 负例；仍不是 Apple 兼容承诺、生产执行链或网络 capability 证据。相同 job 记录 macOS `6/10`、`critical_passed=false`、`ready=false`，数值 IPv4 Seatbelt host 谓词仍 unsupported；`localhost:<port>` 同端口外部 listener 可达问题也仍存在。
- **curl SOCKS5-over-UDS 客户端复核（commit `a69dc50`，CI #296）：**[macOS Apple Silicon](https://github.com/ayukyo/icode/actions/runs/36419842949/job/108919642278) 与 [Intel](https://github.com/ayukyo/icode/actions/runs/36419842949/job/108919642426) 原生任务均确认 runner curl 版本 `>=7.84.0` 且包含 `UnixSockets` feature；真实 sandboxed curl 通过 `ALL_PROXY=socks5h://localhost/<absolute-UDS-path>` 发起请求，测试 SOCKS5 服务观察到完整 `approved.example` 域名并回送固定 canary，另一个 `blocked.example` 得到 SOCKS 拒绝。服务端从不创建 TCP socket，不访问远端网络；所以只验证 UDS SOCKS 客户端兼容性与域名转交，不是产品代理闭环，notice 仍为 `conformance_credit=none`。全矩阵成功，但各平台原生 conformance 数值/`ready=false` 均不变。
- **代理客户端兼容研究（官方文档/固定版本，只读核查，2026-09-28）：**Python [`urllib.request`](https://docs.python.org/3.13/library/urllib.request.html) 与 HTTPX 0.28.1 的 proxy env 都是 proxy URL；HTTPX `uds=` 是目标服务 transport，不是 UDS proxy。Node v26.10 内置 proxy env 接受 HTTP(S)_PROXY/NO_PROXY，没有 UDS proxy 表达。curl/libcurl [`--proxy`](https://curl.se/docs/manpage.html#-x) 支持 SOCKS proxy over UDS，不是当前 ICODE HTTP CONNECT listener 的兼容协议。源码/文档研究没有在 macOS 运行时测试；ICODE 模型 backend 在宿主侧走 urllib，不经过 Seatbelt 子进程网络策略。
- **取舍：**采纳分离 socket-domain 与路径 outbound 规则仅作为 test-only 原语；**暂缓**生产接入、网络评分和自动模式。当前 `HostConnectProxyServer` 为 loopback TCP + HTTP CONNECT，不能因此候选而向常见客户端只注入 `HTTP_PROXY` 并期待 AF_UNIX。若继续此路线，须评估受同一 lease/policy 限制的 SOCKS5-over-UDS 或逐客户端 adapter，再实测真实代理协议、严格直连负例、DNS/IP 约束、连接到期/撤销和 listener 清理。还须覆盖 socket path alias/symlink、短路径长度、目录权限/替换竞态。当前 `MacSeatbeltSandbox` 不放开网络，macOS `6/10`、`policy_contract_ready=false` 与自动模式关闭均不变；无上游代码复制或新运行依赖。

## 2026-09-28 Asia/Shanghai：Linux USER_NOTIF 接入真实 run_command（本机切片）

### AgentLoop 与 CLI 安全投影 follow-up（2026-09-28）

- **范围：**AgentLoop 真实命令拒绝事件测试核实 `ToolResult.meta` 中的稳定 `policy_denied`、原生回执和统一用户提示能到达 CLI 事件边界。CLI 仅在 schema 版本、强制层、来源、类别和有界计数全部匹配时显示固定 `network_socket × count` 摘要；其余拒绝仍用通用安全提示，不显示 argv、路径、输出或额外回执字段。
- **回归：**Linux 原生回执集成 10 项连续 20 轮共 200/200；CLI、AgentLoop、Linux receipt 定向套件 40 项通过。覆盖真实 AF_INET DENY 事件、允许 `AF_UNIX socketpair()`、普通 exit 13 不误报，以及 CLI 摘要与参数脱敏。
- **最终门禁：**完整 `scripts/preflight.py` 的 secrets、submodule、全量 unittest 三门通过（1,156 项，30 项 skip）；针对复审反馈加强线程关闭交错测试后，该用例连续 100/100 通过，最终 `scripts/preflight.py --only tests` 也通过。Python compileall、`git diff --check`、竞品/治理/官网检查通过，三文档一致性审计连续两次均为 0 项；独立复审最终 APPROVE，无 Critical/Important/Minor。提交 [`99a4849`](https://github.com/ayukyo/icode/commit/99a4849fbb16ce4b9e47c67a7fc4870b84868b79) 的 [CI #299](https://github.com/ayukyo/icode/actions/runs/36443592405) 和官网 [#203](https://github.com/ayukyo/icode/actions/runs/36443592413) 均 success。
- **上游取舍：**Codex `openai/codex@36650394c5b38c2990ccf2a3457165ca3e9d9726`（Apache-2.0）保留 MCP `structuredContent`、`isError`、`_meta` 等结果面；OpenHands `software-agent-sdk@d77ada7a030b3acaa82593d402632680361dfe42`（MIT）的所查转换路径把内容与错误布尔值转成 observation；MCP `2026-07-28` 规范允许由工具定义 schema 的 `structuredContent`，没有通用业务 `error_code`。采纳机器码、脱敏回执、用户文案分层；不复制代码、不新增依赖。固定来源见[持续竞品对照](../../agent-landscape-live.md)。
- **MCP 边界：**`src/icode` 当前没有对外 MCP server/result adapter；`vendor/icode-skill` 提供的 MCP 服务是工作流工具，不是 AgentLoop `ToolResult` 的传输层。因此本阶段只验证 CLI，不声称 CLI/MCP parity。若未来增加 runtime MCP adapter，应将相同 `error_code` 与受限回执放入 `structuredContent`、安全提示放入 `content`，并测试同一拒绝来源的等价性。
- **观察不完整的失败提示（2026-09-28 follow-up）：**底层失败事件若明确标为 `violation_observer_status=incomplete`，CLI 现在显示固定“隔离结果未确认”提示，不回显动态 user message、argv 或异常正文；它不把 timeout 或不完整观察描述成 OS 拒绝，也不声称 payload 一定未启动。回归先在旧输出上失败，修正后 CLI + Linux receipt 14 项通过，新提示用例连续 100/100 通过；全量 `preflight.py --only tests`、Python compileall 与 diff check 通过，独立复审 APPROVE（无 Critical/Important/Minor）。本阶段已跑测试、编译和差异检查；跨平台 CI 待推送核验。
- **门禁状态：**Linux→AgentLoop→CLI 本机链路通过，但 macOS/Windows 来源 parity、MCP adapter、文件拒绝覆盖及 `process_limit` 语义仍未闭合；`uniform_violation=false`、`resource_limits=false`、平台评分、网络 DENY、`policy_contract_ready=false` 与自动模式不变，R2/R3 不宣告完成。

- **阶段范围：**在真实 Linux `LandlockSandbox` + deny-only policy 的 `run_command` 分支引入 `SECCOMP_RET_USER_NOTIF` listener；C helper 通过 SCM_RIGHTS 将 listener 交给已就绪的 Python broker，并在收到正确 ACK 前不启动 payload。broker 明确对当前受控 socket DENY 回复 `EPERM`，原生来源与观察器状态沿 `ExecutionResult` 传至工具回执。其它 sandbox、平台、allow policy 和既有执行路径保持不变。
- **TDD 与验收：**新增回归先因缺少原生回执失败；独立审查后又补入策略根错配、只读上下文、observer deadline 到期、poller 初始化异常及 `Thread.start()` 失败清理的先红后绿用例。覆盖真实 AF_INET socket DENY、AF_UNIX `socketpair()` 允许正例、普通 exit 13 不误报、错误 ACK、策略绑定失败及观察器失败关闭。新模块 9 项连续 20 轮共 180/180；broker/tools/CLI/loop 定向 73 项、isolation 74 项通过；C helper 以 `-std=c11 -O2 -Wall -Wextra -Werror` 编译，Python 源码/测试编译检查通过。全仓 preflight 首轮因核心离线模块引入 `socket` 导入失败，已修正并定向复测通过；最终三道门待重跑。
- **风险控制与限制：**回执只包含固定错误文案、有限类别/计数及 `seccomp_user_notif` 来源，不回显 argv、路径或原始输出；handoff/observer 初始化失败时 helper 不得执行 payload，运行期观察失败采取终止并标为 incomplete。观察线程的就绪/ACK 采用显式 event barrier；ACK 前确认 observer 未失败且仍存活，close 会唤醒等待中的线程；线程创建失败路径不会对未启动线程调用 join，仍会关闭 listener FD。该 observer 只覆盖 helper 当前经 USER_NOTIF 处理的 socket 类系统调用，不能记录 Landlock 文件访问拒绝；不宣称覆盖全部 syscall、完整 CLI/MCP parity 或跨平台一致性。
- **门禁状态：**这是本机 Linux 产品路径的增量证据；CI native-probe 已显式加入此集成测试，提交后仍须确认 x86_64/ARM64 与发行版 jobs 实际结果；macOS/Windows 原生来源 parity 仍未闭合。不得据此关闭 VR-1 或增加 `uniform_violation` 分数；不改变 `resource_limits=false`、`policy_contract_ready=false`、R2/R3 完成状态、网络 DENY 或自动模式。`process_limit` 计数口径仍待用户确认，代码未调整其语义。

## 2026-09-29 Asia/Shanghai：不支持平台的命令启动状态提示

- **问题与安全边界：**`execution_broker._execute_policy_command()` 在非 POSIX 平台于 `subprocess.Popen()` 前返回 `unsupported_platform`，但 `ToolResult` 原先继续拼接 `exit=None / <无输出>`，CLI 事件只显示“失败”。这既不够清楚，也没有可让 UI 稳定识别“命令尚未启动”的字段。
- **修改：**该唯一早退路径新增 `error_code=unsupported_platform`、`payload_started=false`；保留既有 `error`、`exit_code=None` 与 `cleanup_scope=not_started`。工具内容和 CLI 均使用固定提示；CLI 只有在两个新增字段精确匹配时才称“命令未启动”。观察器 `incomplete` 分支优先，不被覆盖成确定未启动；argv、路径和异常文本不进入提示。
- **TDD 与验证：**原工具输出用例先因 `exit=None` 与预期不符失败；补充机器字段/CLI 脱敏回归后，旧行为分别以字段缺失和泛化“失败”复现。修正后执行 broker/工具/CLI 定向 51 项通过，新路径重复 20/20；`preflight.py --only tests`、compileall、diff check 与治理/官网/竞品检查通过，独立只读复审 APPROVE（无 Critical/Important/Minor）。
- **推送后复验：**commit [`1f43463`](https://github.com/ayukyo/icode/commit/1f43463149e87fa24b64863f6e81f1b7df6477cb) 的 GitHub [CI #302](https://github.com/ayukyo/icode/actions/runs/36452558796) 总体 success，Windows x64/ARM64 wheel 与 Job cleanup、R3 Windows 目录句柄探针、macOS Intel/Apple Silicon workspace、Linux x64/ARM64 native probe、Python 3.11/3.12 及 presentation jobs 均完成；Retired AppContainer diagnostics 和 Standard-user restricted-token probe 为 skipped，不计作验证。官网部署 [#206](https://github.com/ayukyo/icode/actions/runs/36452558685) success。此 CI 仅验证提交所含回归和所列矩阵，不代表 `process_limit` 已接入真实 Workbench 链路，不补齐 macOS/Windows 原生违规来源 parity，也不关闭 R2/R3 门槛。
- **上游取舍：**Codex Action 固定快照在不满足 Windows 安全策略时于安装/启动前固定失败，但只有 stderr/退出码，没有结构化 `payload_started`；Codex 核心文档说明 WSL1 缺 bwrap 时调用前拒绝；OpenHands SDK 所查通用会话错误路径无对应“后端不支持且 payload 未启动”回执。采纳“拒绝要在启动前发生并给固定说明”，不复制代码，也不采用 Codex Action 的 `unsafe` 降级；ICODE 自有机器状态更明确。版本、许可证与源链接见[持续竞品对照](../../agent-landscape-live.md)。
- **边界：**这只是 unsupported-platform 情况的状态表达，不新增 Windows/macOS 执行后端，不代表用户可在这些平台运行受控命令，也不补充 `uniform_violation`/`resource_limits` 证据；R2/R3、自动模式、策略评分和网络 DENY 均不变。无运行依赖。

## 2026-09-29 Asia/Shanghai：`process_limit` 的 per-command 边界复核

- **真实调用链：**在代码锚点 [`1f43463`](https://github.com/ayukyo/icode/commit/1f43463149e87fa24b64863f6e81f1b7df6477cb) 只读检查，`SandboxPolicy.process_limit` 只有正整数校验/策略合并，未传入 Workbench `run_command → execution_broker`；Windows spawn IPC 也不传该值，`windows_job.py` 只提供未接入的组件。当前字段和旧组件测试都不能证明真实命令受限。
- **平台单位证据：**Linux cgroup v2 [`pids.max`](https://docs.kernel.org/admin-guide/cgroup-v2.html#pid) 是 task 硬限额，PID controller 按 TID 计，线程计数；`pids.current` 与 `pids.events:max` 可作为核验。Windows Job [`ActiveProcessLimit`](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_limit_information#members)按 Job 的活动进程数限制，不计线程。Apple [`RLIMIT_NPROC`](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/setrlimit.2.html) 与 launchd [`NumberOfProcesses`](https://github.com/apple-oss-distributions/launchd/blob/main/man/launchd.plist.5#L1807-L1818)按 UID，当前不构成单命令硬限额。机制、固定上游版本和许可证取舍见[持续竞品对照](../../agent-landscape-live.md)。
- **推荐合同（待确认）：**每个 `run_command` 自成 OS 配额边界；payload 根进程计 1，所有子孙进程计入；ICODE broker/launcher/observer 不计入且必须位于边界外，不能通过事后扣减 helper 数来掩盖语义。Linux TID 与 Windows active-process 的平台差异在策略回执/能力说明中明示。macOS 没有 task-scoped 硬限额时启动前返回 `unsupported`，附 `payload_started=false`，不改用 per-user 限额或进程组清理代替。
- **待用户确认：**是否接受 Linux 把线程计入而 Windows 不计线程；payload 根进程/子孙计数且基础设施 helper 排除在配额边界外。答复前不改 `process_limit` 的语义或资源限制评分。
- **下一实现验收：**同一 cap 从 policy 经 AgentLoop、Workbench 和 broker 到 OS enforcer；cap=2 根+一个子进程成功、cap=1 仅根可运行且子进程在 marker 前被拒绝；按选定口径验证线程；真实 cgroup membership/`pids.current`/`pids.events` 与 Job active-process 证据；cgroup manager/delegation、Job 创建/配置/assignment 失败时无 payload marker；正常、超时、取消、异常及脱组后代路径均确认整 scope/Job 清理。macOS native job 应确认 unsupported + 未启动，而不是跳过后计分。所有正例均需同载荷对照；未完成前 `resource_limits=false`、平台能力评分和自动模式保持不变。

## 2026-09-29 Asia/Shanghai：macOS 同组清理回执字段复验

- **改动：**原生评分 notice 现在并列输出严格 `critical_passed`、平台语义 `platform_critical_passed` 与 `process_group_cleanup`。当平台不适用同组例外时输出 `not_applicable`。只复用现有 scorer 数据，不改变十项证据、9/10 最低项数、critical 集或 `ready` 公式。
- **测试与远端验证：**TDD 回归先观测缺失的平台字段，再验证 macOS 严格树仍 `UNVERIFIED`、平台同组证据可见且 `ready` 不被抬高；非 macOS 对照确认 `not_applicable`。Python 3.11 原生探针模块 11 项通过，全量 preflight 三门通过。提交 [`00440f2`](https://github.com/ayukyo/icode/commit/00440f2) 的 CI [#315](https://github.com/ayukyo/icode/actions/runs/36486236204) 18 个必需 job success，两个可选 Windows 安全诊断跳过；官网 [#219](https://github.com/ayukyo/icode/actions/runs/36486236336) success。
- **门槛边界：**此前 CI #313 macOS Intel 与 Apple Silicon 同组 normal-exit/timeout 测试通过，但评分为 `6/10`、`ready=false`。Codex 对照只支持“同 PGID”局部清理口径，不能推导脱组后代清理；`process_tree_cleanup` 严格项仍保留为未验证。此次 CI 不增加能力分数，`resource_limits=false`、`uniform_violation=false`、`process_limit` 语义待确认、R2/R3 与自动模式状态不变。上游机制和取舍记录在[持续竞品对照](../../agent-landscape-live.md)。

## 2026-09-29 Asia/Shanghai：Linux 多类别 seccomp 回执诊断接入原生 runner

- **TDD 与实现：**先新增 runner 回归，复现 `_run_unittest_probe()` 直接调用 `TestCase.run()`、未执行 `setUpClass/tearDownClass`，以及 `_check()` 未运行原生多类别回执探针的问题。修复后 runner 通过 `TestSuite` 管理测试类资源；Linux native check 执行真实的 seccomp receipt 集成用例，三态为 PASS/SKIP/FAIL，FAIL 令 native job 非零退出，SKIP 不计能力分数。
- **直接证据：**新真实命令分别触发 `socket(AF_INET, ...)` 与 `socketpair(AF_INET, ...)`，可信 USER_NOTIF broker 对两类都明确回复 `EPERM`；Agent `ToolResult` 只给固定 schema、`category=multiple`、`count=2`。真实负例确认应用自行打印 `Permission denied` 并退出 13 不生成 OS 回执；Landlock 拒绝工作区外文件写入也不伪装成 seccomp 回执。28 项 runner/receipt 聚焦测试通过；完整 Linux native probe 实跑状态为 `linux-seccomp-receipt-probe=passed`，总体评分仍 `8/10, critical_passed=true, ready=false`，两个未验证项仍是 `resource_limits` 与 `uniform_violation`。
- **上游取舍：**固定 Codex `3a16c0b7076944bd7c850950464aa38f5620407c` / `9f06cf1a0907f650887ca26af5cee13b4f9a13ea` 使用退出码/输出关键字做不确定的 likely-denial 判断，不采纳为 OS 证据；Anthropic `sandbox-runtime@3ed97390547bdd3d5cec5097d123f3a5fb741c6b` 记录写尝试并由 broker `CONTINUE`，只适合作诊断遥测，不代表内核拒绝；Gemini `fe6350238c1862dade66a9dea9080c6508475bec` 扩权交互不提供此次所需的 syscall 来源证明。均为 Apache-2.0，只借机制，无源码复制或依赖增加。链接与更详细取舍见[持续竞品对照](../../agent-landscape-live.md)。
- **不计分边界：**此探针只证明被该 seccomp filter 覆盖的类别，Landlock 文件拒绝仍无原生回执；不覆盖 macOS/Windows，也不证明全部 syscall/CLI/MCP parity。因此它只在 Linux native job 检查诊断实现，不传入 `score_probe_evidence(uniform_violation=...)`，保留 `uniform_violation=false`、`resource_limits=false`、自动模式关闭及 R2/R3 未完成状态。推送 commit [`d721d83`](https://github.com/ayukyo/icode/commit/d721d83) 的 CI [#333 Ubuntu 22.04 x64](https://github.com/ayukyo/icode/actions/runs/36520245581/job/109251298461)、[Ubuntu 22.04 ARM64](https://github.com/ayukyo/icode/actions/runs/36520245581/job/109251298470)、[Ubuntu 24.04 x64](https://github.com/ayukyo/icode/actions/runs/36520245581/job/109251298205) 与 [Ubuntu 24.04 ARM64](https://github.com/ayukyo/icode/actions/runs/36520245581/job/109251298327) 的 R2.2 native jobs success，覆盖本项 receipt probe；同轮 macOS native jobs success。整条 CI #333 仍因 Windows AppContainer read-handle x64/ARM64 jobs 失败，独立结果见[Windows 计划](./2026-09-25-r2-windows-appcontainer.md)。官网 [#229](https://github.com/ayukyo/icode/actions/runs/36520245588) success。

## 2026-09-29 Asia/Shanghai：deny-only Linux `run_command` deadline 与输出预算直连验收

- **上游取舍：**Codex 固定 `0d7b8117d3cc6d9ffe21d22375d70307133e9f16` 以执行 timeout 清理进程组、另设 I/O drain 窗口；输出保留 cap 后 drain 到 EOF 而非终止命令。Anthropic `sandbox-runtime@3ed97390547bdd3d5cec5097d123f3a5fb741c6b` 的所查 CLI 不设通用 deadline/output cap，signal forwarding 面向直接子进程。均为 Apache-2.0。ICODE 采纳期限/保留量/清理期限应分开验收以及 timeout 后代 marker 测试；保留超输出即停止的本项目既有合同，不把上游“截断后继续”当强制资源限制。固定源码链接和观察结论见[持续竞品对照](../../agent-landscape-live.md)。
- **TDD 与直接证据：**新增原生 runner 合同测试先因 `_check()` 未调用 deny-only 资源界限探针而失败，再接入 Linux 专项探针。真实 `ToolContext → run_command → execute_linux_violation_observed_command → execution_broker` 调用中，将 policy 输出 cap 设为 128 bytes，持续输出命令以 `error=output_limit` 终止，`output_bytes=128`、`output_truncated=true`；另将 policy `wall_timeout_seconds=2`、工具请求 timeout 设为 8 秒，命令启动同组子进程后挂起，2 秒期限返回 `timeout`，broker cleanup 成功且延后 marker 不出现。两条均不产生 `violation_receipt`。聚焦 runner/receipt 32 项通过；完整本机 Linux native probe 中 `linux-observed-command-bounds status=passed`。
- **评分与失败边界：**这个子探针只确认 deny-only Linux 执行链上的墙钟超时、输出字节预算和同组清理；它不验证 per-task `process_limit` 或所有平台的资源上限，因此不向 `resource_limits` 传证据、不改变 `8/10`、`ready=false`、`process_limit` 待确认、`uniform_violation=false`、自动模式关闭或 R2/R3 未完成状态。probe 故障让 Linux native job 失败，环境显式 skip 不加分；CI x64/ARM64 结果随下一次本切片 push 后复验。

## 2026-09-30 Asia/Shanghai：CLI 多类别原生回执摘要对齐

- **问题与 RED：**Linux USER_NOTIF broker 可在同一命令中记录两个受限 socket syscall，并生成固定 `category=multiple`、`count>=2` 的 OS-enforced 回执；CLI 显示白名单此前只接受 `network_socket`，因此这类真实 OS 回执被降级成普通 `[拒绝]`。合成 CLI event formatter 回归在旧逻辑上失败；随后新增一条真实多类别命令贯穿 `run_command → ToolResult → AgentLoop → CLI event callback` 的原生集成回归。
- **最小修正：**CLI 现在仅接受既有固定来源/schema/enforcement 字段完整匹配的 `network_socket` 或 `multiple`，并要求 `multiple` 至少计数 2；摘要仍由固定 allowlist 字段构成，不输出命令参数或任意回执附加字段。应用层回执、未知来源/类别和异常计数继续显示通用安全提示。
- **验收与边界：**CLI 8 项与 Linux USER_NOTIF receipt 15 项定向测试通过；真实多类别 `run_command → ToolResult → AgentLoop → CLI event callback` 同条路径产生固定摘要，另覆盖 `multiple/count=1` 与 list/dict 类别畸形值失败关闭及脱敏。MCP adapter/parity 仍未覆盖。此改动只修复 CLI 安全投影的一致性，不增加新 OS 证据、不改变 `uniform_violation`/`resource_limits` 评分。上游仍引用本计划已固定的 Codex denial 与 OpenHands 通用结果快照；本次未复制代码、未增加依赖。R2/R3 readiness、网络 DENY 与自动模式不变。

## 2026-10-01 Asia/Shanghai：macOS TCP host predicate 不适配与 UDS lease 后续候选

- **上游/原生证据：**CI 双架构 macOS runner 均拒绝数字 `remote ip "127.0.0.1:<port>"` profile；`localhost:<port>` 则连到宿主非 loopback 同端口 listener，不能用于严格 loopback 地址授权。Apple DTS 说明自定义 SBPL 未对第三方文档化/支持、`sandbox-exec` deprecated；Apple `network.client` entitlement 只表达可否连接，不提供按目的地址或租约授权。因而不适配 `localhost`、数字 IP 猜测或 `(allow network*)` 作为受支持的强 TCP 边界。[Apple DTS](https://developer.apple.com/forums/thread/661939) · [network.client entitlement](https://developer.apple.com/documentation/BundleResources/Entitlements/com.apple.security.network.client)
- **候选与现状：**Codex 固定 Apache-2.0 源码 [`44fe510`](https://github.com/openai/codex/blob/44fe510ce3ee61c8ef623adcbf89b901c73ddd61/codex-rs/sandboxing/src/seatbelt.rs#L2648-L2716) 和 Anthropic Sandbox Runtime `0.0.77` Apache-2.0 [`3ed9739`](https://raw.githubusercontent.com/anthropics/sandbox-runtime/3ed97390547bdd3d5cec5097d123f3a5fb741c6b/src/sandbox/macos-sandbox-utils.ts#L1116-L1144) 提供 AF_UNIX 路径授权机制参照。ICODE 已有 host-only SOCKS5-over-UDS proxy 与 lease API、macOS curl 真实正反例；但仅 test profile 按私有目录 `subpath` 放行，未精确限制 socket path，未接 production profile、executor、approval chain，也未证明 curl 以外的常见命令兼容。上游规则包含 `network-bind` 的机制不直接复制；ICODE 只考虑更窄的 outbound 能力，不增加依赖。
- **采纳 / 暂缓与验收：**采纳 AF_UNIX outbound path-scoped route 为生产候选；暂缓接线和任何评分，直到工单私有 0700 目录、0600 socket、不可由 worker 替换、Seatbelt outbound-only grant、批准域名/拒绝域名/直连 IPv4+IPv6、其它 UDS/路径替换/子进程负例、TTL/revoke/正常与异常退出清理、Mac Intel/Apple Silicon 与支持 OS 版本的原生验收完成。非 UDS-aware 客户端必须有 fail-closed adapter 或明确不可联网；curl canary 不代表普通 CLI 兼容。此研究不改变 macOS `6/10`、`ready=false`、`network_temporary_allowlist` 或自动模式状态。
