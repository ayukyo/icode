# R2.2 Linux/macOS 原生隔离实施计划

- 日期：2026-09-23
- 状态：实施中；尚未达到 R2.2 退出条件
- 依据：[R2 正式设计](../specs/2026-09-23-r2-cross-platform-isolation-design.md) §6、§14、§16

## 三问与边界

1. 真实问题：现有 `probe_capabilities()` 只看可执行文件是否存在，`select_sandbox()` 因此可能宣称未验证的隔离能力；自主执行链也未消费 R2.1 的 `SandboxPolicy`。
2. 已有实现：保留 `WorkspaceSession.policy()`、现有 `Sandbox`/`ToolContext` 与 R2.0 的 10 项合同；先修复探测，再建立统一执行入口，不再平行维护第二套策略。
3. 调用链：工作台启动 → `AutonomyManager` → `NativeChainExecutor` → `run_chain` → `run_contract_step` → `ToolContext` → `run_command`。运行时自己的测试命令也必须经同一执行入口，否则会绕过边界。会话模式保持兼容；自动模式无可用且已实测的后端时禁止外部命令。

## 实施任务

### 1. 真实能力探测与回执

- 为 Linux/macOS 后端添加短时、独立临时目录中的启动和负向探测：工作区外写入、受保护目录读取、默认网络、子进程继承；返回逐项证据，不把可执行文件存在当成 `ready`。
- `icode doctor` 区分“找到候选工具”和“实际验证通过”；探测超时或异常按不可用处理，不裸执行。测试用失败注入覆盖候选存在但启动失败的情况。
- macOS profile 的路径转义和系统读取白名单由测试锁定；每个 CI macOS 版本真实运行负向用例。

### 2. Linux 随包助手与策略映射

- 以包内助手为首选，不依赖用户 PATH 中的 `bwrap`；x86_64/arm64 wheel 包含对应构建产物、哈希与来源记录。辅助工具缺失或哈希不符时 fail-closed。
- 按 `SandboxPolicy` 生成挂载/权限边界，工作区可写，原仓、gitdir、Skill、账本与证据不可写，敏感目录不可读，默认断网；验证 `..`、符号链接与子进程负例。
- 若采用 Landlock，必须检查实际 ABI 与构建配置；Linux 5.13 仅保证初版文件系统接口，网络限制仍需另一原语，不能把 kernel 版本等同于完整能力。

### 3. macOS Seatbelt 后端

- 使用系统 `/usr/bin/sandbox-exec` 与由可信策略编译的 profile；工作区允许、受保护路径优先拒绝、默认拒绝网络。`sandbox-exec` 虽仍被主流 Agent 使用，但 Apple 将其标为 deprecated，故只以受测系统版本的真实负向结果作为能力声明。
- CI 在 macOS runner 测试真实写外、敏感读取、网络、子进程与清理；失败时保持自动模式阻断。

### 4. 唯一执行入口与阶段验收

- `run_command`、运行时测试命令及自动链路统一走带策略的执行 broker，命令无 shell、环境显式、cwd 限于工作区；超时回收进程树，输出有界并留脱敏回执。
- 旧会话模式及可注入测试 executor 保持兼容；自动模式未完成探测不能退回 `NoIsolation` 裸执行。
- Linux/macOS 在 R2.2 范围内的关键负向测试（文件读写、默认断网、子进程继承、清理、启动失败阻断）全部通过；代理临时授权属于 R2.4，不把它提前计为通过。完整 8 项 critical 与 ≥9/10 一致性是 R2 最终发布门槛。独立安装 wheel 验证，无 Docker/WSL/Node/系统包前置；本阶段任一退出项未达到时只推送开发分支，不把 R2.2 标为完成或合入主线。

## 验证与风险

- [开发分支首次三平台 CI](https://github.com/ayukyo/icode/actions/runs/35882823179) 暴露两项真实环境差异：Ubuntu runner 上 `bwrap` 的 loopback 设置被权限策略拒绝，macOS 初版探测脚本误用了 Linux 的 `cat` 路径。前者转向 Landlock/seccomp 路径，后者已修正并通过后续复测。
- [四架构 CI](https://github.com/ayukyo/icode/actions/runs/35888941694) 已通过 Linux x86_64/ARM64、macOS Apple Silicon/Intel 的真实负向探测；Linux 两架构也通过 wheel 构建、独立安装和安装后探测。开发期 Landlock/seccomp 助手已随对应 Linux wheel 发布并做哈希校验，**但未接入自动执行，也未覆盖受保护路径、完整策略和进程树清理**。
- 执行链检查发现 `run_contract_step` 接收 `sandbox` 后没有传给模型主回合与补救回合；已以先红后绿的离线测试修复。`run_command` 原先允许 `cwd` 逃出工作区（包含 `..`/符号链接），现由工具本身再次解析并拒绝，避免只依赖上层 guard。两项修正不代表 `SandboxPolicy` 已完整执行。
- `WorkspaceSession.policy(step)` 现逐步传至 `NativeChainExecutor` → `run_chain` → `run_contract_step` → `Guard`/`ToolContext`；应用层读写按允许根和拒绝根裁决。当前任何原生后端都尚无完整的 `wrap_policy`，因此真实工作台自动模式在模型调用前返回稳定的 `isolation_unavailable` 阻断，UI 中英双语显示“策略级隔离尚未就绪”。这避免把 6 项最小负向探测误当成完整工单策略；下一项工作是绑定受保护路径和进程/输出限额后恢复可运行自动模式。
- 调用链复查又确认一个必须成对解决的接口：自动会话的工单 `out_dir` 留在宿主原工程，策略只给独立工作区读写权；旧模型提示却要求直接对 `out_dir` 调用 `write_file`。即使策略级后端就绪，这仍会被正确拒绝。按正式设计 §7.3，需要受控的精确产物 API：仅允许当前步骤合同声明的产物由宿主代写、校验并登记；旧步骤输入也只能通过受控只读路径提供，不能开放整个账本或把账本映射进模型命令沙箱。
- 已增量实现 `submit_artifact` / `read_artifact`：仅策略会话注册，按当前步骤 `ticket_file` / 单层 `ticket_glob` 端口校验，禁止隐藏/越界/机器装配产物、符号链接、超限和非法 JSON；宿主原子代写，现有控制面仍负责最终登记。模型主回合与补救提示改用产物名，文本补落盘也复用端口；操作回执与公开工具启动事件只记录参数摘要。离线链路证明直接伪写账本被拒而合法计划产物可以提交。**尚未做真实模型 E2E，且原生策略后端仍未就绪；不能把该接口单测等同于 R2.2 完成。**
- 策略会话的 `run_command` 现经独立 POSIX 执行 broker：显式环境只带必要的 PATH/HOME/TMPDIR 等变量，不继承模型密钥；无 shell，用户超时受策略上限约束，合并输出在策略字节限额处终止，正常退出和超时均回收同一进程组；回执保留策略/参数哈希、退出码、输出截断及清理状态，不回显原始参数。先红后绿测试覆盖环境泄漏、输出超限和子进程超时清理；非策略会话保持原执行路径。进程组不能约束主动 `setsid` 脱离的后代，`process_limit` 尚未由原生助手落实；本项只是宿主执行边界，不是 R2.2 的完整进程树保证。
- broker 的四架构首轮 CI 在 macOS 双架构发现：主进程输出/退出码正常，若在其退出后先向僵尸进程组发 `SIGKILL`，macOS 返回 `EPERM`；补充错误码回执后改为先 `poll()` 回收已退出主进程，再清理仍存在的同组子进程。后续 [四架构 CI](https://github.com/ayukyo/icode/actions/runs/35947638254) 中 Linux x64/ARM64 和 macOS Intel/Apple Silicon 的 broker 项均通过，且失败时仍保留 `cleanup_failed` 而不吞掉真正的清理错误。
- macOS 增加从 `SandboxPolicy` 生成的实验性 Seatbelt profile：可写根的 `allow` 条件排除精确受保护路径及其子树，限制可移动的受保护祖先，读取根同理排除拒读路径，默认断网。[双架构真实 CI](https://github.com/ayukyo/icode/actions/runs/35948062141) 已通过受保护 `.git` 文件、工作区外写入、拒读文件及当前 Python 启动负例。该 profile **尚未提供 `wrap_policy`、尚未接通自动模式**，进程数限制与完整合同仍待落实。Linux 的 Landlock 不能在授权整个可写父目录后撤销 `.git` 子路径权限，需另行完成可用的子路径隔离方案，不能直接复用当前最小助手声明完成。
- Linux worktree 增加**未启用的实验性** `isolate_git_metadata` 选项：把 `.git` 指针内容移至受保护的 runtime 目录，checkout 内保留指向它的符号链接；复用时核验目标、内容摘要和 Git 身份，要求隔离的会话不能静默复用旧格式。此举只防止在 Landlock 可写 checkout 中直接改写原指针**内容**；checkout 内的符号链接本身仍可能被删除或替换，Git 命令在当前最小 Landlock 读白名单下也无法读取外部指针。因此它不是完整的受保护子路径方案，不能启用自动模式。Linux 助手同时拒绝沙箱内 `setsid`/`setpgid` 脱离 broker 进程组，并拒绝 x86_64 上的 x32 syscall 编号；进程树与策略级负向验证仍待完成。
- 每个任务先补失败测试再实现；逐项运行单测、`compileall`、`preflight.py`、三平台 CI 和干净 wheel 安装。编译并发不超过 `-j6`。
- Linux CI 的 user namespace/AppArmor 组合可能禁止 Bubblewrap；需报告环境不支持并保持拒绝执行，而不是在测试中跳过关键项。
- macOS 的 Seatbelt profile 行为及系统服务授权可能随版本变化；限制是系统级目标，不能用应用层路径判断代替负向测试。

参考：[Linux Landlock 官方文档](https://docs.kernel.org/userspace-api/landlock.html) · [Bubblewrap 手册](https://manpages.debian.org/bookworm/bubblewrap/bwrap.1.en.html) · [Apple 开发者论坛关于 sandbox-exec 支持状态](https://developer.apple.com/forums/thread/661939) · [Codex 当前 Seatbelt 实现](https://github.com/openai/codex/blob/main/codex-rs/sandboxing/src/seatbelt.rs)
