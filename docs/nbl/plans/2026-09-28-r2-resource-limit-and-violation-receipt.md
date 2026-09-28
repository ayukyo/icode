# R2 资源限制与统一违规回执实施门

- 日期：2026-09-28 Asia/Shanghai
- 状态：R2 资源限制及原生回执的产品接线仍未开始；只读审计、本机机制实验、应用层拒绝回执基础切片、Linux test-only USER_NOTIF 原型，以及 macOS 双架构 test-only 精确拒绝事件观测已有证据，能力评分不变
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
