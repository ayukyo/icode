# R2.3 Windows AppContainer 与 Job Object 实验计划

- 日期：2026-09-25
- 状态：原生实验入口仍未通过验收；CI #91–#98 的 Windows x64 与 ARM64 AppContainer 均失败，#92–#98 的启动返回 CreateProcessW 错误码 203；普通 Job 空环境对照在 #96–#98 双架构通过；#97 已修正失败分类，#98 排除了 `=X:` 环境项差异；属性列表缓冲区显式对齐及 macOS 脱组后代握手测试待 CI 复验；不接生产自动工单
- 依据：[R2 正式设计](../specs/2026-09-23-r2-cross-platform-isolation-design.md) §6.3、§14；[持续竞品对照](../../agent-landscape-live.md)

## 三问与边界

1. **真实问题：**Windows Job Object 已提供工单级活动进程限制和退出回收，但不能限制文件或网络；R2.3 仍缺 OS 强制的工作区边界。
2. **已有实现：**`src/icode/windows_job.py` 负责挂起创建、加入 `KILL_ON_JOB_CLOSE | ACTIVE_PROCESS` Job、再恢复进程；`SandboxPolicy` 已表达读写根和默认断网。当前 `run_windows_job` 是开发探针，不接自主执行。
3. **调用链影响：**本实验仅新增 `run_windows_appcontainer`，沿用现有 Job runner，并以 AppContainer Package SID 为进程安全能力。生产 `NativeChainExecutor`、`policy_contract_ready`、`icode doctor` 和自动模式均未开放。

## 研究结论与选择

- **选择性采纳 AppContainer 机制：**Microsoft 官方文档说明，AppContainer 可用 `CreateAppContainerProfile` 建立当前用户 profile，再通过 `STARTUPINFOEX` 的 `PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES` 创建进程；不授网络 capability 时没有网络能力。ICODE 使用 Python 标准库 `ctypes` 调 Win32 API，不增加安装依赖。参考：[AppContainer 启动](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer)、[隔离模型](https://learn.microsoft.com/en-us/windows/win32/secauthz/appcontainer-isolation)、[创建 profile API](https://learn.microsoft.com/en-us/windows/win32/api/userenv/nf-userenv-createappcontainerprofile)。
- **权限与文件策略：**每次运行随机 profile / Package SID；只给传入的独立工单目录添加临时可继承 ACL，原仓、`.git`、common gitdir、用户目录和凭据路径不加该 SID。执行完恢复原始根 ACL，并遍历校验 Package SID ACE 已从当前子树消失；另外以相同 SID 做工作区写入拒绝后测，再删除 profile。工作区含重解析点、硬链接、受保护 ACL、null DACL 或网络共享时拒绝启动。Windows 自动 ACL 传播规则见[官方说明](https://learn.microsoft.com/en-us/windows/win32/secauthz/automatic-propagation-of-inheritable-aces)。
- **Job 组合：**`CREATE_SUSPENDED` 与 `EXTENDED_STARTUPINFO_PRESENT` 组合；AppContainer 创建后先加入独立 Job，再恢复主线程。进程创建、属性设置、Job 归属任一失败时均不运行普通宿主命令。
- **不开临时网络：**AppContainer 不授 `internetClient` / `privateNetworkClientServer`，当前仅探测本机 loopback 拒绝。需要按域名临时联网时须另行实现可验证的 WFP/防火墙身份规则与受控代理；环境变量和 AppContainer internet capability 不足以表达域名 allowlist。

### 新增研究结论（2026-09-24 UTC）

- Microsoft `mxc` 主分支观察锚点 `021b9b58561cac98a3b34f10dbdf11b5393e776e` 的 [issue #572](https://github.com/microsoft/mxc/issues/572) 报告：兼容层对大 Python 安装目录逐条命令递归增加、撤销 AppContainer ACE，约 35 秒/次；这是 issue 报告而非本机复测。ICODE 当前同样每次命令扫描和递归写工作区 ACL，因此不能只凭小型 CI 工单认定性能可用。候选改进方向是单工单工作区会话复用 SID，并尽可能在文件生成前建立根继承 ACL；还需测大目录建树、撤权和中断恢复后才能采纳。
- [Codex issue #45871](https://github.com/openai/codex/issues/45871)（2026-09-16 开放中的用户报告）描述 AppContainer 可能拒绝经 `\\GLOBAL??\\C:` 的 DOS 盘符解析，即使实际目录 ACL 已放行。ICODE 大量使用 `Path.resolve()`，故增加 Windows 原生 Python 运行探针：容器内启动本机 Python、分别 resolve `cwd` 与解释器路径，并将结果作为 Actions notice；此测试尚未通过。
- CI [#91](https://github.com/ayukyo/icode/actions/runs/36028273699) 中 Windows x64 与 ARM64 的 AppContainer 测试均失败。匿名 REST 只能读到步骤退出码，日志接口要求仓库管理员权限；因此失败点尚未确认，不把任何候选机制写成验证通过。Python 与完整工作区探针已加上分类 notice，以便下轮按平台读取失败阶段。
- CI [#92](https://github.com/ayukyo/icode/actions/runs/36030432822) 的 Windows x64 与 ARM64 分类 notice 均显示 CreateProcessW 错误码 203（ERROR_ENVVAR_NOT_FOUND）。[Microsoft CreateProcessW 文档](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw)说明自定义环境块不会自动带入系统驱动器当前目录，调用方必须显式传入类似 `=C:` 的特殊项；当前环境块已按文档修正，但 CI [#93](https://github.com/ayukyo/icode/actions/runs/36032231436) 在 x64 与 ARM64 仍返回同样的 203，因此原先候选原因未获验证。[Convira issue #1](https://github.com/Convira/convira-sandbox/issues/1) 报告相同 GitHub hosted runner 现象，但作者未确诊并在该项目跳过原生集成测试；不能据此断言是 runner 限制。下一步用空自定义环境块启动 System32 `whoami.exe`，且不继承任何宿主变量，以分离环境块与 AppContainer 进程启动因素。
- CI [#94](https://github.com/ayukyo/icode/actions/runs/36033714035) 的 x64 与 ARM64 空环境块诊断仍以 CreateProcessW 203 失败：在 AppContainer 下，当前失败不依赖具体环境变量或盘符项。此前 Convira issue 也以 GitHub hosted runner 为复现范围，但未确定根因，故仍不能判定 runner 限制。下一轮在非 AppContainer Job 中用相同空环境块和 System32 `whoami.exe` 做正向对照，随后再选探测方向。

竞品取舍：Codex `3e9d1d29370ee7239585b9d1d576bea8263768ec` 的 Windows 后端采用 restricted token，借鉴“降低令牌权限”，但不能据此等同凭据读取隔离；Qwen `330b92811c07483e30704190c7e135161120481b` 的 Windows 方案需 Docker/Podman，不符合 pip-only；Gemini `87de0b6369f0466da37d9b3c0c9b77374bb59992` 文档提到低完整性 ACL 处理，但不把 ACL 残留风险带入本方案。仅借鉴机制，不复制其实现。

### 2026-09-25 差分诊断更新

- CI [#97](https://github.com/ayukyo/icode/actions/runs/36037204891) 的 x64、ARM64 通知确认：AppContainer 的 `CreateProcessW` 仍返回 203，但现在正确报告 `native_api_failed, cleanup=True`；普通 Job 空环境 `whoami.exe` 对照仍为 `executed=True, exit=0, cleanup=True`。#97 因 AppContainer 实验本身失败而未通过，不能把结果分类修复当作隔离验收。
- 只读核对 `io-harness` 0.86.0 的 [AppContainer 环境块实现](https://docs.rs/io-harness/0.86.0/src/io_harness/sandbox/appcontainer.rs.html)：其构造器明确跳过 `=X:` 盘符伪变量，源码注释称子进程解析器会把这类项误当环境块结束。这是另一实现里的防御性处理，不证明它就是 ICODE 的 203 根因；微软文档说明启动时会基于属性列表创建容器环境，但没有说明 `=X:` 是本故障原因。
- 据此形成一个窄差分实验：仅在创建 AppContainer 进程时省略 `=X:` 项，普通 Job 环境块保持兼容，显式绝对 `cwd` 不变。Linux 本地模拟测试只证明参数分支和回执逻辑，未调用 Win32。候选待 CI #98 在 x64、ARM64 原生验证；无论结果如何，Windows 自动工单继续关闭。

- CI [#98](https://github.com/ayukyo/icode/actions/runs/36038951938) 在 x64 与 ARM64 仍以 `CreateProcessW` 错误码 203 失败；同轮普通 Job 空环境对照双架构通过。因此，省略 `=X:` 没有改变失败，撤销该差分并恢复 AppContainer 环境块原有盘符当前目录项；这条候选判为**不采纳**，不是根因修复。#98 的 macOS Intel `setsid` 后代负例测试也未能在 1.5 秒固定等待内观察到 marker，而 macOS ARM 同项通过；等待边界改为最多 8 秒轮询 marker，并保留必须观察到脱组后代真实存活的断言。该测试修订待下一轮 macOS 双架构 CI 验证。
- 只读核对 `io-harness` 0.86.0 的固定提交 `8c03ca273246937975bf63da8413c927ba264916`：[属性列表源码](https://docs.rs/io-harness/0.86.0/src/io_harness/sandbox/appcontainer.rs.html#L1240-L1277) 用 `Vec<usize>` 对齐分配，注释说明其目的为指针对齐；[Microsoft API 文档](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-initializeprocthreadattributelist)只明确要求有足够分配空间，未写明对齐要求。故“上游显式保证、ICODE 未显式保证”是已证实差异，“ICODE 实际地址未对齐并造成 203”不是已证实根因。当前以 `c_size_t` 数组向上取整分配，作为单变量、低风险 A/B；Linux 单测验证容量与对齐契约，Windows x64/ARM64 CI 仍须验证是否改变 203，若未改变则继续差分诊断。
- macOS 后代负例改为握手：脱组孙进程在 `setsid()` 后记录 PID/session/process-group 并等待 release；仅在 broker 调用返回后测试才发 release，随后要求存活 marker 出现。等待和孙进程自退均有界，因此测试证明的是清理返回后的真实存活，不再依赖固定睡眠长度；CI #99 的 macOS Intel 与 ARM64 均通过该负例。

## 2026-09-25 CI #99 结果

- CI [#99](https://github.com/ayukyo/icode/actions/runs/36043391647) 的 Windows x64 与 ARM64 普通 Job 空环境 `whoami.exe` 对照均 `executed=True, exit=0, cleanup=True`；AppContainer 空环境诊断、工作区测试和 Python 启动仍均在 `CreateProcessW` 返回 203。显式对齐属性列表缓冲区 A/B 未解决问题。保留指针对齐作为稳健的内存分配方式，但判定它**不适配为当前 203 的修复**；runner 根因仍未证实，Windows 自动模式保持关闭。
- 同轮 macOS Intel 与 ARM64 `setsid` 脱组后代握手负例通过：测试在 broker 返回、原进程组清理已结束后才释放脱组后代，并验证其存活 marker。它验证用户已批准的 Codex 式边界，不承诺回收主动脱组后代。

## 当前实现与验收

CI [#95](https://github.com/ayukyo/icode/actions/runs/36034747937) 的 x64 与 ARM64 再次在 AppContainer `CreateProcessW` 返回 203；Python 启动及空环境诊断表现一致。CI [#96](https://github.com/ayukyo/icode/actions/runs/36035908657) 与 #99 的普通 Job 空环境对照在 x64 与 ARM64 均 `executed=True, exit=0, cleanup=True`，而 AppContainer 中仍返回 203。这把问题收窄到 AppContainer 启动路径，但不能据此断言是 GitHub runner 限制。#96 注释还暴露回执缺陷：AppContainer 没有创建进程却标记 `cleanup_failed`；#97 修复后保留 `native_api_failed` 且 `cleanup_ok=True`，但原生启动仍失败。#98 进一步确认省略 `=X:` 当前目录伪变量无效；#99 进一步确认显式对齐属性列表缓冲区仍未改变失败，问题根因仍未确诊。

Windows 实验用例覆盖目标：在 AppContainer 中启动 Python 并 resolve 工作路径；工作区已有嵌套文件可读、工作区可写、相邻目录 canary 不可读写、宿主 loopback 正向对照成立而 AppContainer 连接被拒、主进程正常退出与超时后的子进程回收、`process_limit=1` 阻止再启动子进程；ACL 恢复后，同一 Package SID 不能再写工作区。另有跨平台环境块测试验证普通 Job 与 AppContainer 路径均保留盘符伪变量、排序和宿主变量不继承；空环境 AppContainer 探针不传递宿主环境，普通 Job 对照验证相同空环境块和系统程序可以正常启动。现有 `WindowsJob` 原生测试另测正常退出、超时和宿主异常退出回收。CI #91–#99 的 AppContainer 原生集成都失败，故这些只能称测试覆盖意图，不能称通过；普通 Job 空环境对照已在双架构实测通过。

必须在 GitHub Actions 的 Windows x64 与 ARM64 runner 同时通过，并保持纯 wheel / Python 3.11 路径。当前 Linux 本机仅验证了非 Windows 拒绝分支、链接/硬链接防护、环境块结构、显式属性指针对齐分配和模拟原生失败路径的回归；它**没有**执行任何 Win32 API。CI #91–#99 双架构的 AppContainer 原生探针均失败，普通 Job 空环境对照双架构通过；#92–#99 的可见分类 notice 显示 AppContainer `CreateProcessW` 错误码 203。不能在确认 Python 运行时启动和路径规范化后接自动模式。

目前仍缺少真实 Windows 的 IPv4/IPv6、UDP、DNS、外网直连拒绝、受保护 Git 元数据与凭据 canary、主动脱离/显式换身份尝试、profile/ACL 多轮泄漏以及更完整的失败恢复测试。即便本轮 CI 通过，也只说明这个原生实验子项通过，Windows R2.3、R2.2 和完整 R2 均仍未验收；`policy_contract_ready` 必须继续为 false。

## 风险与成本

- ACL 变更需要完整扫描工作区，体积很大时耗时可能明显；MXC issue #572 报告兼容路径的全树 ACE 传播在 Python 安装目录上约需 35 秒/命令。ICODE 尚无大目录实测；扫描失败、任何 ACE 清理失败或 profile 删除失败都必须留下失败结果。当前实验只支持本地目录，不接受 UNC。
- 单次 Python 解释器/模块依赖可能位于工作区之外；不准因此放开整个用户目录或系统盘。必须证明最小运行时只读授权和 `Path.resolve()` 在 AppContainer 中可用，且衡量引入 ACL 的体积与启动耗时。
- 仅给目录 SID 授权并不能替代工作区构造合同：生产接入前要确认执行根不包含 `.git` 指针/元数据，并继续证明项目链接和重解析点无法访问外部路径。
- 企业策略可拒绝创建 AppContainer profile，API 失败必须阻止命令执行，不可退回普通 Job。
- 默认断网可不要求管理员；Windows 临时代理路径仍需管理员可管理的网络策略或等价可信服务，拒绝授权时保持断网。
