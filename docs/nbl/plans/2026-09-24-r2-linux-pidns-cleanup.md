# R2.2 Linux 异常退出后代清理：验证计划

- 日期：2026-09-24
- 状态：生产助手与本机 wheel 实测通过；GitHub Linux x64/ARM64 CI 尚待验证
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

本机 Ubuntu x64 的独立临时目录实验：`unshare --user --map-root-user --pid --fork --mount-proc` 可用，namespace PID 1 的 `getppid()` 为 0；可信 PID 1 绑定父死信号后，宿主杀死外层进程，已 `setsid` 的后代在 1.9 秒后没有写出延迟标记，宿主视角 PID 已消失。Linux 的 `PDEATHSIG` 在 fork 及凭据变化时有清除条件；生产助手在凭据变化后重新设置，并用控制管道处理父死亡竞态。[内核接口说明](https://man7.org/linux/man-pages/man2/PR_SET_PDEATHSIG.2const.html)与[PID namespace 文档](https://man7.org/linux/man-pages/man7/pid_namespaces.7.html)提供机制依据。

生产助手本机先红后绿已覆盖：宿主 `SIGKILL` 后已脱组孙进程的 `pidfd` 退出与无延迟写；正常退出、超时、输出超限；`unshare` 被 seccomp 拒绝时不执行负载；负载尝试 ptrace、`process_vm_readv`/`writev` 与对 PID 1 发送 `SIGKILL`。独立代码审查另发现并复现两项继承状态缺口：`SIGCHLD=SIG_IGN` 使可信 `waitpid` 失败，预开工作区外文件描述符可绕过 Landlock；分别通过恢复默认 `SIGCHLD` 与入口 `close_range` 修复，失败时均 fail-closed。新增测试共 9 项，本机实际 wheel 构建、隔离 venv 安装及后代清理探测通过；完整 `preflight.py` 三道门禁通过。**这些本机证据不等于 GitHub x64/ARM64 通过，也不证明进程数上限或完整 R2 合同；`policy_contract_ready` 继续为 false。**
