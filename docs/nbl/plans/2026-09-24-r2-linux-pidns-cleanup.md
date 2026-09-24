# R2.2 Linux 异常退出后代清理：验证计划

- 日期：2026-09-24
- 状态：生产助手与本机 wheel 实测通过；GitHub 24.04 Linux x64/ARM64 因 `uid_map` 权限阻断，R2.2 尚未验收
- 依据：[R2 正式设计](../specs/2026-09-23-r2-cross-platform-isolation-design.md) §6.1、§14

## 三问与调用链

1. 真实问题：当前 broker 只在自身存活时执行 `killpg`；宿主被 `SIGKILL` 时，助手的 `PDEATHSIG` 不会随 `fork` 传给后代，后代可能残留。
2. 已有实现：复用随 wheel 分发的 `icode_landlock`、策略包装、现有 broker 与 Landlock/seccomp；不引入用户另装的 `unshare` 命令或特权守护服务。
3. 影响链：`SandboxPolicy` → `LandlockSandbox.wrap_policy` → `execute_policy_command` → 随包助手 → 受限进程树。新机制失败时返回稳定启动失败，绝不能回退裸执行；`policy_contract_ready` 继续为 false。

## 实现边界

1. 原生助手在可信阶段创建 user + PID namespace，并保持一条受宿主死亡约束的监督链。受限命令由 namespace 内的可信 PID 1 派生，命令本身不能成为 PID 1。
2. 可信 PID 1 在命令正常退出、超时或宿主异常死亡时退出；内核随之清理 namespace 中所有后代，包括主动 `setsid` 的进程。创建 namespace、UID/GID 映射、安装父死信号及控制管道的顺序必须处理父进程死亡竞态。
3. PID 1 与命令之间须隔离信号、ptrace、`process_vm_*` 和可改变监督者行为的句柄；不能仅凭简单 `setsid` 测试宣称恶意代码清理成立。任何凭据变化后重新核对 `PDEATHSIG`，避免该设置被内核清除。
4. 文件/网络边界仍由 Landlock/seccomp 执行。用户 namespace 不得让命令获得祖先 namespace 权限；不把当前用户主目录或宿主原仓映射为可写。
5. 本阶段只解决 Linux 异常退出后代清理；`process_limit`、Git/网络代理与十项完整回执另行验收。若发行环境禁用 userns/PID namespace，清楚报不可用并阻断自动模式。

## 先红后绿与验收

- 原先失败的真实负例：宿主 `SIGKILL` 后，主动脱组孙进程延迟写入；新实现必须使该标记不出现，并确认宿主 PID 消失。
- 正常退出、超时、输出超限与启动失败都不留后代；负例覆盖 `setsid`、多层 fork、受限后代尝试干扰 PID 1。
- `ubuntu-latest` x64 和 `ubuntu-24.04-arm` 均编译 `-Wall -Wextra -Werror`，运行源树测试和独立 wheel 安装测试；若任一 runner 不支持命名空间，CI 给出确定失败回执，保持门禁关闭，再研究不依赖系统包/特权的替代方案。
- 任何实现都需检查中断、管道 EOF、等待与资源回收，且不得因单项清理实验通过把 Linux R2 完整合同标为 ready。

## 已有证据与尚未证明

[第三轮线上 CI](https://github.com/ayukyo/icode/actions/runs/35999349870) 的 Ubuntu 22.04 x64/ARM64 原生探测均通过，24.04 x64/ARM64 仍卡在 `uid_map`；这把差异收窄到宿主配置/发行环境，但尚未证明具体机制。[Ubuntu 24.04 官方发行说明](https://documentation.ubuntu.com/release-notes/24.04/)描述了“可创建 user namespace，但内部 capability 受 AppArmor 限制”的默认行为；[user namespace](https://man7.org/linux/man-pages/man7/user_namespaces.7.html)与[PID namespace](https://man7.org/linux/man-pages/man7/pid_namespaces.7.html)手册未要求先写 UID/GID map 才能 fork/exec 或让 PID 1 清理后代。本机无映射 `unshare --user --pid --fork` 可启动，进程视角 uid/gid 为 65534，但本机 AppArmor 限制关闭，**不得外推至 CI**。下一轮仅诊断 GitHub 24.04 能否无映射创建 PID namespace，不修改生产助手的 fail-closed 行为；即使能启动，仍须验证 capability 清除、Landlock/seccomp、工作区正反向文件/网络边界及异常退出后代清理。

[第二轮线上 CI](https://github.com/ayukyo/icode/actions/runs/35997854549) 已运行：Linux x64/ARM64 原生负例均在 `/proc/self/uid_map: Operation not permitted` 失败，Python 3.11/3.12 全套测试也未通过。当前只能确认 GitHub 24.04 宿主拒绝此映射，不能仅凭 `EPERM` 断言具体是 AppArmor、capability 还是 namespace 叠加限制。[Linux user namespace 手册](https://man7.org/linux/man-pages/man7/user_namespaces.7.html)列出映射的能力/身份约束。下一轮 CI 增加 22.04 x64/ARM64 对照与只读宿主策略诊断，保留 24.04 原样失败门禁；22.04 通过也不能把 24.04 或完整 R2 标记为通过。

本机 Ubuntu x64 的独立临时目录实验：`unshare --user --map-root-user --pid --fork --mount-proc` 可用，namespace PID 1 的 `getppid()` 为 0；可信 PID 1 绑定父死信号后，宿主杀死外层进程，已 `setsid` 的后代在 1.9 秒后没有写出延迟标记，宿主视角 PID 已消失。Linux 的 `PDEATHSIG` 在 fork 及凭据变化时有清除条件；生产助手在凭据变化后重新设置，并用控制管道处理父死亡竞态。[内核接口说明](https://man7.org/linux/man-pages/man2/PR_SET_PDEATHSIG.2const.html)与[PID namespace 文档](https://man7.org/linux/man-pages/man7/pid_namespaces.7.html)提供机制依据。

生产助手本机先红后绿已覆盖：宿主 `SIGKILL` 后已脱组孙进程的 `pidfd` 退出与无延迟写；正常退出、超时、输出超限；`unshare` 被 seccomp 拒绝时不执行负载；负载尝试 ptrace、`process_vm_readv`/`writev` 与对 PID 1 发送 `SIGKILL`。独立代码审查另发现并复现两项继承状态缺口：`SIGCHLD=SIG_IGN` 使可信 `waitpid` 失败，预开工作区外文件描述符可绕过 Landlock；分别通过恢复默认 `SIGCHLD` 与入口 `close_range` 修复，失败时均 fail-closed。新增测试共 9 项，本机实际 wheel 构建、隔离 venv 安装及后代清理探测通过；完整 `preflight.py` 三道门禁通过。**这些本机证据不等于 GitHub x64/ARM64 通过，也不证明进程数上限或完整 R2 合同；`policy_contract_ready` 继续为 false。**

[首轮线上 CI](https://github.com/ayukyo/icode/actions/runs/35995535030) 在 Linux x64/ARM64 同时因 `/proc/self/setgroups: Permission denied` 阻断，macOS 双架构与 Windows Job 双架构作业通过。根据 [Linux user namespace 接口](https://man7.org/linux/man-pages/man7/user_namespaces.7.html)，新增两条受核验的映射路径：已是 `deny` 时不重复写；`allow` 状态写 `deny` 仅在 `EACCES/EPERM` 时尝试 UID-only 映射，要求真实 `gid_map` 为空且 `setgroups(0,NULL)` 返回 `EPERM`，其余情况失败关闭。本机以测试专用驱动复现权限拒绝，重跑文件/网络/已脱组后代负例、干净 wheel 与前置门禁通过；生产入口固定读取真实 proc 文件，测试路径不进入 wheel。**本机通过不等于线上修复成功；第二轮 CI 结果见本节开头。**
