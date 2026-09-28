# R2 资源限制与统一违规回执实施门

- 日期：2026-09-28 Asia/Shanghai
- 状态：R2 资源限制与原生违规回执实现未开始；只读审计、本机机制实验和应用层拒绝回执基础切片已完成，能力评分不变
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

本计划不改变 worker 网络默认 `DENY`、macOS 地址范围门槛、`policy_contract_ready`、workbench 自动模式或现有 capability 评分。macOS 的 `localhost` 同端口规则和 `process_limit` 是否把线程计入两项用户决定仍待答复；答复前仅进行只读核查，不放宽策略。

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
