# R2.3 Windows AppContainer 与 Job Object 实验计划

- 日期：2026-09-25 UTC
- 状态：**未通过验收，Windows 自动模式不开放。** CI #133–#136 的 disposable staging Python 3.11.9 宿主正向控制成功，但 AppContainer 候选退出 1。#136 x64/ARM64 均确认：staging ACL 的 DACL bytes 已恢复、身份未变、无 Package SID 残留、staging 最终删除；唯一报告差异是根对象 security descriptor `control` 字段。下轮只增加脱敏 control-bit 差分，以确认具体变化；尚未证明能按原状态恢复。工作区/network/child 组合结果仍无效；不接入生产、不扩大权限。
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

### 2026-09-24 UTC 差分诊断更新

- CI [#97](https://github.com/ayukyo/icode/actions/runs/36037204891) 的 x64、ARM64 通知确认：AppContainer 的 `CreateProcessW` 仍返回 203，但现在正确报告 `native_api_failed, cleanup=True`；普通 Job 空环境 `whoami.exe` 对照仍为 `executed=True, exit=0, cleanup=True`。#97 因 AppContainer 实验本身失败而未通过，不能把结果分类修复当作隔离验收。
- 只读核对 `io-harness` 0.86.0 的 [AppContainer 环境块实现](https://docs.rs/io-harness/0.86.0/src/io_harness/sandbox/appcontainer.rs.html)：其构造器明确跳过 `=X:` 盘符伪变量，源码注释称子进程解析器会把这类项误当环境块结束。这是另一实现里的防御性处理，不证明它就是 ICODE 的 203 根因；微软文档说明启动时会基于属性列表创建容器环境，但没有说明 `=X:` 是本故障原因。
- 据此形成一个窄差分实验：仅在创建 AppContainer 进程时省略 `=X:` 项，普通 Job 环境块保持兼容，显式绝对 `cwd` 不变。Linux 本地模拟测试只证明参数分支和回执逻辑，未调用 Win32。候选待 CI #98 在 x64、ARM64 原生验证；无论结果如何，Windows 自动工单继续关闭。

- CI [#98](https://github.com/ayukyo/icode/actions/runs/36038951938) 在 x64 与 ARM64 仍以 `CreateProcessW` 错误码 203 失败；同轮普通 Job 空环境对照双架构通过。因此，省略 `=X:` 没有改变失败，撤销该差分并恢复 AppContainer 环境块原有盘符当前目录项；这条候选判为**不采纳**，不是根因修复。#98 的 macOS Intel `setsid` 后代负例测试也未能在 1.5 秒固定等待内观察到 marker，而 macOS ARM 同项通过；等待边界改为最多 8 秒轮询 marker，并保留必须观察到脱组后代真实存活的断言。该测试修订待下一轮 macOS 双架构 CI 验证。
- 只读核对 `io-harness` 0.86.0 的固定提交 `8c03ca273246937975bf63da8413c927ba264916`：[属性列表源码](https://docs.rs/io-harness/0.86.0/src/io_harness/sandbox/appcontainer.rs.html#L1240-L1277) 用 `Vec<usize>` 对齐分配，注释说明其目的为指针对齐；[Microsoft API 文档](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-initializeprocthreadattributelist)只明确要求有足够分配空间，未写明对齐要求。故“上游显式保证、ICODE 未显式保证”是已证实差异，“ICODE 实际地址未对齐并造成 203”不是已证实根因。当前以 `c_size_t` 数组向上取整分配，作为单变量、低风险 A/B；Linux 单测验证容量与对齐契约，Windows x64/ARM64 CI 仍须验证是否改变 203，若未改变则继续差分诊断。
- macOS 后代负例改为握手：脱组孙进程在 `setsid()` 后记录 PID/session/process-group 并等待 release；仅在 broker 调用返回后测试才发 release，随后要求存活 marker 出现。等待和孙进程自退均有界，因此测试证明的是清理返回后的真实存活，不再依赖固定睡眠长度；CI #99 的 macOS Intel 与 ARM64 均通过该负例。

## 2026-09-24 UTC CI #99 结果

- CI [#99](https://github.com/ayukyo/icode/actions/runs/36043391647) 的 Windows x64 与 ARM64 普通 Job 空环境 `whoami.exe` 对照均 `executed=True, exit=0, cleanup=True`；AppContainer 空环境诊断、工作区测试和 Python 启动仍均在 `CreateProcessW` 返回 203。显式对齐属性列表缓冲区 A/B 未解决问题。保留指针对齐作为稳健的内存分配方式，但判定它**不适配为当前 203 的修复**；runner 根因仍未证实，Windows 自动模式保持关闭。
- 同轮 macOS Intel 与 ARM64 `setsid` 脱组后代握手负例通过：测试在 broker 返回、原进程组清理已结束后才释放脱组后代，并验证其存活 marker。它验证用户已批准的 Codex 式边界，不承诺回收主动脱组后代。

## 2026-09-24 UTC CI #100 结果与下一差分

- CI [#100](https://github.com/ayukyo/icode/actions/runs/36045885881) 的 Windows x64 与 ARM64 AppContainer 空环境探针、Python 启动及工作区测试均在 `CreateProcessW` 返回 203；同两架构普通 Job 空环境 `whoami.exe` 正向对照成功。macOS、Linux、Python 3.11/3.12 与工作区平台作业通过。该结果仍不能证明 hosted runner 是根因。
- 先前 `test_诊断空环境块下的系统程序启动` 使用 `side_effect=(空环境块, 安全环境块)`；安全块仅供主进程成功后执行 ACL 撤权子调用，当前主进程启动失败时并未尝试以安全块启动 AppContainer。此前普通 Job 对照也只覆盖空块，没有与 AppContainer 使用同一最小环境块的正对照。
- **下一差分已加入待验测试：**同一临时工作区、绝对 `whoami.exe`、同一 cwd 和由 ICODE 构造的显式最小 Unicode 环境块，依次运行普通 Job 与 AppContainer；日志仅记录环境条目名、字符/UTF-16 字节数、NUL 数和摘要，不输出变量值。CI 复验前不对结果作推断；若普通 Job 成功而 AppContainer 仍报 203，环境内容本身不是充分解释，应继续记录 SID/属性载荷 API 回执，而不改放宽权限。

## 2026-09-24 UTC CI #101 结果与属性诊断

- CI [#101](https://github.com/ayukyo/icode/actions/runs/36048561915) 的全部非 Windows 作业通过；Windows x64 与 ARM64 原生 AppContainer 作业仍失败。两架构的新增 notice 都显示普通 Job `whoami.exe` 成功、AppContainer `CreateProcessW` 错误 203、主进程未创建且清理状态准确；捕获到两条最小环境块，结构元数据均为 483 字符、966 UTF-16 字节、9 个变量项/10 个 NUL 字符。notice 不含环境变量值；该实验没有改变权限或放入宿主密钥。
- 新增测试在本机代码中比较两条启动路径生成的完整环境块，并断言一致；但 Linux 本机不能执行 Win32 API。CI step 仍失败，因为 AppContainer 子进程未能启动，因此它不是 R2.3 通过证据，也不证明 GitHub runner 是根因。普通 Job 正向对照继续通过，错误仍定位在 AppContainer CreateProcess 路径。
- 为下一轮记录调用前提而新增纯诊断：`CreateAppContainerProfile` HRESULT、SID 存在/`IsValidSid`/长度；属性列表 size query/init、`UpdateProcThreadAttribute` 的结果和立即错误码、能力结构字节数/空 capability 计数及创建 flags。诊断不输出 SID、环境值或指针地址，不改能力集合/权限/启动 flags；非法 SID 会 fail-closed。CI #102 验证这些字段与原生回归。

## 2026-09-24 UTC CI #102（上海时间 2026-09-25）

- [CI #102](https://github.com/ayukyo/icode/actions/runs/36051234628) 的非 Windows 检查均通过；Windows x64 与 ARM64 AppContainer 仍在启动探针失败。普通 Job 的同一最小 Unicode 环境块 `whoami.exe` 正向对照成功，AppContainer 的 `CreateProcessW` 仍返回 203，清理回执为真。
- 两架构 notice 均显示 `CreateAppContainerProfile` 成功，`UpdateProcThreadAttribute` 成功，创建 flags 为 `0x00080404`；大小查询探针返回 `ERROR_INSUFFICIENT_BUFFER` (122) 与 48 字节。Microsoft 文档明确说明该 API 首次以空指针查询大小时会按设计失败，因此 122/48 是预期回执，不是原因；ICODE 代码也要求该错误码和非零大小才继续初始化。参考：[InitializeProcThreadAttributeList 官方说明](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-initializeprocthreadattributelist)、[AppContainer 启动样例](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer)。
- 现有可见信息进一步排除了 profile 创建、属性列表初始化/更新及最小环境块作为充分解释，但不能定位 `CreateProcessW` 203 的根因，也不能归因 hosted runner。当前诊断 notice 有长度上限；SID 校验成功由失败前控制流保证，但不把它当作 CI 独立日志字段。
- **下一单变量差分：**只针对系统自带的绝对路径 `System32\whoami.exe`，比较 `CreateProcessW.lpApplicationName` 传绝对路径与传 `NULL`（完整绝对路径仍在可写命令行中）；环境块、cwd、SID、属性列表、`CREATE_SUSPENDED`、Job 处理全部不变。Microsoft AppContainer 官方样例和独立 io-harness 0.86.0 源码都用 `NULL` application name；这是候选差异，不是已知修复。只允许该固定无副作用程序走此诊断，不能用于用户命令。
- 不尝试移除 `CREATE_SUSPENDED`：AppContainer 仍须先加入 Job 才能执行，不能为诊断让用户代码在 Job 外运行。Windows 自动模式继续关闭。

## 2026-09-24 UTC CI #104 app-name A/B 结果

- CI [#104](https://github.com/ayukyo/icode/actions/runs/36056228159) 对同一临时工作区、固定无参数 `SystemRoot\\System32\\whoami.exe` 依次测试显式 `lpApplicationName` 和 `NULL`。两次都在 `CreateProcessW` 返回错误 203，且 `cleanup=True`；诊断捕获两份实际环境块并确认完全相等，创建 flags 保持 `0x00080404`。结果：[CI 注释](https://github.com/ayukyo/icode/actions/runs/36056228159)。
- 结论：`lpApplicationName=NULL` 不是这次启动失败的充分解释或修复；也不据此断定是 hosted runner 原因。该开关仅保留在私有、固定 whoami 诊断路由，普通 AppContainer 与用户命令仍显式传绝对应用路径。下一项差分等独立研究确定，自动模式继续关闭。
- 本地 Python 3.11/3.12 守护、模拟 Win32 参数与保护边界用例通过；Linux 未执行 Win32。CI 原生 Windows 作业仍整体失败，不作为 R2.3 通过证据。

## 2026-09-24 UTC LOCALAPPDATA 单变量 A/B 结果与常规路径接入

- 微软《[Launch an AppContainer](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer)》说明容器 profile 可通过 `LOCALAPPDATA` 或 `GetAppContainerFolderPath` 访问，并给出 profile 专属目录示例；[API 参考](https://learn.microsoft.com/en-us/windows/win32/api/userenv/nf-userenv-getappcontainerfolderpath)规定输入为 SID 字符串、输出由调用方使用 `CoTaskMemFree` 释放。ICODE 从刚创建的二进制 SID 调用 `ConvertSidToStringSidW` 得规范 SID 字符串，再查询路径；失败时不猜路径、不使用宿主 `LOCALAPPDATA`。微软还说明 profile 是 per-user/per-app 的文件及注册表存储，并要求调用 `DeleteAppContainerProfile` 前关闭相关句柄；失败时应重试且状态未定，因此本实现有界重试并验证已知的 `LOCALAPPDATA` 路径消失：[CreateAppContainerProfile](https://learn.microsoft.com/en-us/windows/win32/api/userenv/nf-userenv-createappcontainerprofile)、[DeleteAppContainerProfile](https://learn.microsoft.com/en-us/windows/win32/api/userenv/nf-userenv-deleteappcontainerprofile)。容器环境契约为工单工作区 + 当前 profile 的私有临时数据区；`TEMP/TMP` 仍指向工单工作区，而不沿用文档示例的 profile 子目录。
- 只读核对 Chromium 固定提交 [`19e92f6`](https://chromium.googlesource.com/chromium/src/%2B/19e92f6a6088ac35a31d74cbf4d64b32ef54957c/sandbox/win/src/app_container_profile_base.cc#178)：调用 `GetAppContainerFolderPath` 前将 SID 转为 SDDL 字符串。取舍是借鉴官方 API 的输入/内存所有权处理，不复制其实现，也不认为这证明缺少 `LOCALAPPDATA` 是 203 根因。
- 受限原生 A/B 固定同一临时 profile/SID、工作区、无参数 `System32\\whoami.exe`、cwd、能力、flags 与 Job 生命周期，环境块仅差 profile `LOCALAPPDATA`。CI [#105 x64](https://github.com/ayukyo/icode/actions/runs/36059960206/job/107836254760) 与 [#105 ARM64](https://github.com/ayukyo/icode/actions/runs/36059960206/job/107836255639) 均观测到 baseline 返回 `CreateProcessW` 203、candidate 成功退出 0 且 Job 清理通过。此受控结果说明该差异改变了固定探针的启动结果，但不是完整隔离通过证据。
- CI #105 的完整 AppContainer 用例仍失败，因为当时只有诊断 candidate 添加该变量，正常 AppContainer 启动路径未添加它。当前实现已在创建 profile 后通过官方 API 得到专属路径，并给正常执行、app-name A/B 和 ACL 撤权探针使用；路径查询失败会在命令启动前 fail-closed，且测试确认 profile/ACL/SID 资源清理成功时保留准确错误分类。新的 Windows 原生 CI 尚待验证这项常规路径接入。
- Linux 本地测试只验证 Win32 参数构造、SID/API 内存所有权模拟、fail-closed 和清理结果，不执行任何 Win32 API。A/B 路径不输出 profile 路径或宿主变量值；即便固定探针继续成功，也不代表 Python、工作区读写、网络拒绝、ACL 撤权和完整 R2 验收通过。

## 2026-09-24 UTC CI #106：profile 环境接入后的首轮回归

- CI [#106 x64](https://github.com/ayukyo/icode/actions/runs/36063691161/job/107848355215) 与 [#106 ARM64](https://github.com/ayukyo/icode/actions/runs/36063691161/job/107848355043) 的固定 whoami `LOCALAPPDATA` A/B 均通过：baseline 仍是错误 203，追加当前 profile API 返回路径后成功退出 0，Job 清理通过。普通 Job、R2.1 workspace、Linux/macOS 原生检查及 Python 3.11/3.12 单测也通过。
- 两项“最终 AppContainer 环境块含 `LOCALAPPDATA`”断言曾只捕获 `_build_windows_environment_block` 的返回值，而 `run_windows_job` 在该函数返回后才追加 profile 路径；这是测试探针层错误，不是容器未传变量的证据。现在测试同时捕获追加函数返回的最终环境块，并断言普通 Job 与容器基础环境一致、只有容器最终块增加该单项。
- Python 原生探针确实创建了进程，但退出码为 `0xC0000135`（Windows `STATUS_DLL_NOT_FOUND`），因此没有生成工作区标记。它说明当前宿主解释器/依赖尚不能在该 AppContainer 环境运行；尚未证明具体哪个 DLL 缺失，也未证明是 ACL 拒绝。不得通过授权整个用户目录或系统盘绕过。接下来须原生诊断最小运行时依赖、`Path.resolve()` 与 ACL 耗时后，才能决定是否值得保留该路线。
- 工作区/网络组合探针执行并正常清理，但退出码为 1；首轮日志只显示外部访问负例的控制台错误，无法确认脚本到达末尾及全部检查点。已加入 completion sentinel 与安全布尔状态 notice，下一轮据此判断问题是预期的拒绝码还是未走完探针。故 CI #106 **不是** R2.3 通过证据，自动模式继续关闭。

## 2026-09-24 UTC CI #107 x64：任务脚本路径探针未执行

- CI [#107 x64](https://github.com/ayukyo/icode/actions/runs/36066941127) 中，修正后的最终环境块回归及固定程序/profile `LOCALAPPDATA` 差分测试通过；Python 主进程仍退出 `0xC0000135`，具体加载依赖尚未定位。
- 工作区/网络组合探针显示 CMD 创建成功但退出 1，`script_complete=false`、工作区写入和嵌套复制标记均缺失。运行时文件直读诊断同样没有复制出文件；它使用同种绝对批处理入口，所以不能把 `source_read_match=false` 当成 AppContainer 源文件拒绝的证据。
- **待验证的路径上下文假设：**容器仅获任务目录 ACE，CMD 通过绝对临时目录路径定位批处理文件可能触发入口访问差异。现将批处理入口和任务内读写改用 `cwd` 相对路径，并先加 CMD inline 相对写入正对照；不授予父目录访问。只有对照与 completion marker 均通过，才继续解读运行时源文件读取结果。ARM64 #107 当时尚未完成。
- 因此 CI #107 x64 **不是** Windows 文件/网络/进程门禁通过证据，R2.3、完整 R2 和自动模式仍未验收。

## 2026-09-24 UTC CI #108：工作区边界通过一部分，进程与 Python 未通过

- CI [#108 x64](https://github.com/ayukyo/icode/actions/runs/36067827628/job/107861602120) 与 [#108 ARM64](https://github.com/ayukyo/icode/actions/runs/36067827628/job/107861602149) 中，环境块最终回归及 profile `LOCALAPPDATA` 单变量 A/B 均通过；Python 仍退出 `0xC0000135`，尚未由 Agent 完成实际任务。
- 两架构均报告 inline cwd 写入、相对批处理入口、工作区写入与嵌套读取成功；相邻目录写入未发生，宿主 loopback 正对照可达而 AppContainer 未触达。此结果只覆盖当前 loopback/文件 canary，不等于 IPv4/IPv6、UDP、DNS、外网和 Git 凭据门禁通过。
- 对 #108 的历史解释收窄：公开 Actions 注释无法还原精确失败断言（x64 无 timeout notice；ARM64 notice 只有 cleanup 状态，公开日志 API 返回 403），所以不从日志推断具体根因。只读检查 `eabc4df` 源码确认旧子进程测试让后代等待 3 秒、runner 返回后仅观察 3.2 秒，且没有同载荷无 Job 正向对照；该测试设计存在约 0.2 秒裕量，不能作为稳健的清理验收。旧用例依赖 `timeout.exe`，后续改成 release-handshake 与 runner timeout；本地不能验证 Win32。
- ARM64 运行时文件 notice 显示同一路径副本中 System32 `whoami.exe` 可读，而 Python executable、共享 DLL、`pathlib.py` 和 `encodings` 样本没有复制结果；当前还未记录每个 copy 脚本是否启动，故此差异仍需下轮启动标记确认。没有证据支持递归放宽 ACL。
- 因此 CI #108 **不是** R2.3 Windows 通过证据，自动模式继续关闭。

## 2026-09-24 UTC CI #109：Windows 子项有通过 notice，Python runtime 仍失败

- CI [#109 x64](https://github.com/ayukyo/icode/actions/runs/36069030309/job/107865391485) 与 [#109 ARM64](https://github.com/ayukyo/icode/actions/runs/36069030309/job/107865391466) notice 报告 workspace 读写/外部写拒绝/loopback 拒绝、正常后代回收、runner timeout 后代回收、`process_limit=1`、环境块及 profile A/B 子项通过。研究复核发现进程探针在 release handshake 后仍只观察 0.2 秒，没有相同 payload 正向对照；这比 #108 清晰，但不足以排除调度延迟造成的假阴性。R2.3 仍不能验收，因为 Windows Agent 尚不能启动 Python 执行器。
- 新增 copy script 自身的启动标记，两架构均确认它已启动；Python executable、共享 DLL、`pathlib.py`、`encodings` 样本均无副本。ARM64 的 System32 `whoami.exe` 对照可复制；x64 的相同 System32 对照也未复制。CMD 原始 copy 错误文本没有保存，不能把退出码 1 直接定性为 `ACCESS_DENIED`；下轮只记录错误类别（不暴露路径），区分访问控制与路径错误。
- 为避免 Python loader 失败遮住 profile 存储本身的状态，下轮另用受限 CMD 写入 profile 专属 marker，并在删除 profile 前观测 marker、删除后确认路径消失；同时保留原始 copy 文本于任务工作区，仅将安全错误类别写入 Actions notice。
- 不放宽到整用户目录、整 Python 安装、`site-packages` 或系统盘。只在错误分类确认必要范围后，设计可审计的最小只读运行时访问或暂存；并单独验收 ACL 恢复、Profile 清理、性能和工作区 venv 兼容。
- 故 #109 的工作区/断网与进程相关 notice 仅作原始观察；其短等待窗不足以单独验收清理。#110 已用同 payload 正向对照与五秒后代观察窗补强清理子项，但 profile 写入、进程数限制和 Python 运行时仍阻断 Windows R2.3 / 完整 R2 / 自动模式。

### 2026-09-24 UTC 上游 Windows Job 测试设计复核

- 独立只读核对 `io-harness` v0.86.0、commit `8c03ca273246937975bf63da8413c927ba264916`（Apache-2.0）：其 Job 清理测试用相同三代后代载荷，先验证 Job 模式等待后无 sentinel，再以无 Job 模式等待相同时间并要求 sentinel 出现；进程数测试也对同一脚本对比上限开启/关闭。参考[树清理与正对照](https://github.com/initorigin/io-harness/blob/8c03ca273246937975bf63da8413c927ba264916/tests/sandbox_job_object.rs)及[许可证](https://github.com/initorigin/io-harness/blob/8c03ca273246937975bf63da8413c927ba264916/LICENSE)。ICODE 只采纳测试结构，不复制实现或引入依赖。
- OpenAI 官方 Windows 沙箱工程文章（2026-05-13）记录 AppContainer 对开放式 shell/Python/Git/build 工具链的适配限制；Codex 后续改为需安装的受限用户/Token 与防火墙组合。[官方说明](https://openai.com/index/building-codex-windows-sandbox/)。这强化 ICODE 需验证实际 Python/toolchain，而不能据系统 `cmd.exe` 子项通过就判断可产品化；Codex 的提权安装架构不符合当前 pip-only 普通用户边界，暂不照搬。
- ICODE 取舍：采纳“负例 + 同负载正对照 + 足够观察窗”的验证方法；暂缓授予 Python 安装树 ACL。#110 已确认 profile marker 未写入、Python 仍不能运行；本轮将先分类 profile 专属目录写入失败，再决定最小运行时 staging 或淘汰 AppContainer。测试 harness 的进程限制对照也将改为确定等待同一子脚本及记录创建状态。

## 2026-09-24 UTC CI #110：Windows 探针证据收窄，仍未验收

- [CI #110 x64](https://github.com/ayukyo/icode/actions/runs/36071476528/job/107873192081) 与 [ARM64](https://github.com/ayukyo/icode/actions/runs/36071476528/job/107873192101) 的 AppContainer Python 均以 `0xC0000135` 退出；这只能证明当前宿主解释器未能在容器中启动，不能定位 DLL、路径或 ACL 根因。系统 CMD 的相对工作目录写入、工作区嵌套读取/写入、外部写入拒绝、loopback 拒绝、正常退出后代清理和 timeout 后代清理均有通过 notice；它们是子项证据，不构成 Python 或整体边界验收。
- 两架构的 profile marker 探针均执行且退出 1，删除前 marker 均不存在，profile 清理 notice 为真。原探针未分别记录 `LOCALAPPDATA` 是否到达 CMD、profile 目录是否预先存在、写入 stderr 类别；故尚不能区分路径不存在与访问拒绝，也不据此改目录 ACL。
- [Microsoft `GetAppContainerFolderPath`](https://learn.microsoft.com/en-us/windows/win32/api/userenv/nf-userenv-getappcontainerfolderpath) 规定该 API 返回指定 SID 的 LocalAppData 路径，但没有在此 API 说明中保证目录已物化；本轮因此只记录路径在启动前的存在性，不假定缺目录或缺 ACL。失败分类确认前不创建、放宽或改写 profile 目录。
- 进程上限测试的旧载荷通过 `start` 异步启动后等待一秒。x64 的 `process_limit=8` 正对照未产生子标记；ARM64 虽产生标记但父命令退出 1。ARM64 `process_limit=1` 调用也执行并清理，但公开 notice 未带负例标记；原始 Actions 日志无法匿名读取，无法恢复精确失败断言。退出码 1 本身不足以区分子进程是否成功启动。
- 依据 [Microsoft Job Objects 文档](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)，`CreateProcess` 后代默认加入同一 Job；[活动进程限制](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_limit_information)说明超限进程关联会失败。当前改为父脚本直接同步调用同一个 `cmd.exe` 子脚本，并记录父尝试标记、子 marker 与子进程状态：正对照 `process_limit=2` 必须全部成功；负对照 `process_limit=1` 必须有父尝试、子状态非零且无子 marker。profile 用例只向 Actions notice 暴露布尔状态、整数状态码及白名单错误类别，不输出绝对路径或原始错误文本。此轮改动仍须 Windows x64/ARM64 CI 验证；AppContainer、R2.3 与自动模式继续 fail-closed。

## 2026-09-24 UTC CI #111：诊断本身无效，尚未进入进程上限负例

- CI [#111 x64](https://github.com/ayukyo/icode/actions/runs/36073278352/job/107878821096) 与 [ARM64](https://github.com/ayukyo/icode/actions/runs/36073278352/job/107878821121) 都在 Windows AppContainer 集成步骤失败。两架构 profile 生命周期 notice 为 `executed=True, exit=0, cleanup=True`、profile 路径在启动前存在、删除前 marker 不存在；但 `LOCALAPPDATA`/目录状态、写状态和错误类别的读取发生在 `TemporaryDirectory` 退出之后，显示的 `False/None/no_stderr` 全部是探针时序错误，不能据此推断容器环境或目录 ACL。
- 两架构 `process_limit=2` 的同步正对照中，父尝试 marker 与子 marker 均存在、命令 `exit=0`；状态文件为空。CMD 将 `echo %errorlevel%> file` 展开成以数字紧邻重定向符的语法，数字会被当作文件描述符而不是文本，因此测试在检查正对照状态后失败，没有执行 `process_limit=1` 负例。该轮不构成 process limit 结论。
- 本轮把 profile 分类读取移到临时目录清理之前，并将退出状态编码为 `exit_code=<整数>` 后解析；新增纯解析器回归测试。现有 Python `0xC0000135` 和其他子项状态不变。CI #111 不作为 Windows 自动模式/R2.3 通过证据；修正后需重新跑双架构原生测试。

## 2026-09-24 UTC CI #112：进程上限组件通过，profile 与 Python 仍阻断

- CI [#112](https://github.com/ayukyo/icode/actions/runs/36074365589) 的 x64/ARM64 `process_limit=2` 同载荷正对照均记录父、子 marker 且状态为 0；`process_limit=1` 均记录父启动尝试、没有子 marker，子进程启动状态为 1816，清理通过。该结果支持 Job 活动进程上限在此测试边界生效，不代表完整 AppContainer 验收。
- 两架构 Python 仍以 `0xC0000135` 退出。profile 探针报告 `LOCALAPPDATA` 已定义、API 返回的目录在宿主启动前存在，但容器内目录检查为假、写入分类为 `path_not_found`、删除前 marker 不存在；profile 最终清理通过。当前证据不能区分容器拿到的字符串与 API 返回值不一致、路径语义或实际目录访问问题。
- 工作区读写/外部写拒绝、loopback 拒绝、正常退出与 timeout 后代回收有组件级通过 notice；它们不替代 Python 执行、profile 存储或完整文件/网络门禁。
- 微软[启动指南](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer)说明 profile 为 AppContainer 提供可创建、读取和写入文件的位置，并可经 `LOCALAPPDATA` 或 `GetAppContainerFolderPath` 访问；[创建 profile API](https://learn.microsoft.com/en-us/windows/win32/api/userenv/nf-userenv-createappcontainerprofile)说明每用户/每应用文件夹和注册表数据存储随 profile 建立。[路径查询 API](https://learn.microsoft.com/en-us/windows/win32/api/userenv/nf-userenv-getappcontainerfolderpath)只返回 Local AppData 路径，不保证其创建目录或修订 ACL。官方文档没有给出精确 ACL mask，因此不能据文档推断 CI runner 上实际 token 一定可达。
- CI #113 的旧 `set LOCALAPPDATA` 输出比较与 #114 的同块 alias 比较在双架构均为 false。CI #115/#116 未核验 Unicode 输出文件有效性，故比较结果不作结论。CI #117 已确认 alias 存在、`cmd /u` exit 0 且输出非空，解析比较仍不等于 API/宿主路径。CI #118 在 profile 删除前确认 actual `LOCALAPPDATA` 唯一，但 `Path.is_dir`/`samefile` 均为 false；当时未区分 not-found 与 access-denied。当前增加宿主只读 `stat` 错误类别及 actual/API 父子同级关系，防止把解析缺项或路径别名误当环境改写。Microsoft [`cmd /u`](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/cmd) 说明该选项输出 Unicode。Actions 不记录路径，亦不调整 ACL。
- CI [#119](https://github.com/ayukyo/icode/actions/runs/36080610266) 的 Windows x64 job [107901499390](https://github.com/ayukyo/icode/actions/runs/36080610266/job/107901499390) 与 ARM64 job [107901499384](https://github.com/ayukyo/icode/actions/runs/36080610266/job/107901499384) 均失败。profile notice 显示 Unicode `LOCALAPPDATA` 唯一、宿主 `stat=not_found`、相对 API 路径类别为 `api_child`、`samefile` 为 false；Python 仍退出 `0xC0000135`。这表明 actual 路径字符串位于 API 返回目录内，但尚未证明具体子目录名称或为何不可见/不可写。
- Microsoft [AppContainer 启动指南](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer)示例把 `LOCALAPPDATA` 指向 profile 的 `AC`，并把 `TEMP/TMP` 指向 `AC\\Temp`；[CreateProcessW 环境块说明](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw)规定调用者可为新进程提供环境块，但没有说明 AppContainer 对自定义 `LOCALAPPDATA` 值的改写行为。该指南的示例使用默认环境块，不足以裁定 ICODE 的显式环境块。当前 Windows 探针仅比较 actual 是否等于 API `Temp` 子目录，并缩短 notice 避免 GitHub 注释截断；不创建目录、不调整 ACL、不输出路径。若该比较为 true，仍须先查清 `not_found` 与 profile 写入失败，不能直接把 profile 子目录变更为产品契约。
- Windows R2.3、完整 R2 及自动模式仍未验收，`policy_contract_ready` 必须保持 `false`。

## 当前实现与验收

CI [#95](https://github.com/ayukyo/icode/actions/runs/36034747937) 的 x64 与 ARM64 再次在 AppContainer `CreateProcessW` 返回 203；Python 启动及空环境诊断表现一致。CI [#96](https://github.com/ayukyo/icode/actions/runs/36035908657)、#99、#100、[#101](https://github.com/ayukyo/icode/actions/runs/36048561915)、[#102](https://github.com/ayukyo/icode/actions/runs/36051234628) 与 [#104](https://github.com/ayukyo/icode/actions/runs/36056228159) 的普通 Job 对照在 x64 与 ARM64 均成功，而 AppContainer 中仍返回 203。这把问题收窄到 AppContainer 启动路径，但不能据此断言是 GitHub runner 限制。#96 注释还暴露回执缺陷：AppContainer 没有创建进程却标记 `cleanup_failed`；#97 修复后保留 `native_api_failed` 且 `cleanup_ok=True`，但原生启动仍失败。#98 进一步确认省略 `=X:` 当前目录伪变量无效；#99 进一步确认显式对齐属性列表缓冲区仍未改变失败。#101/#102 加入相同最小 Unicode 环境块对照；#102 已排除 attribute-size 查询、profile 创建和 attribute 更新为充分解释。#104 的固定 whoami app-name A/B 两边仍为 203、环境块相等；该差异不构成修复。#105 发现同 profile `LOCALAPPDATA` 单变量 A/B 在两架构中改变了固定探针的启动结果；常规路径接入后，#106–#112 的 Python 仍以 `0xC0000135` 退出。#110 的 profile marker 未写入且进程数探针不确定；#112 的同载荷进程数正反对照通过，但 profile 路径在 AppContainer 内仍不可见、marker 缺失。工作区/网络和后代清理仍只是组件级证据，不代表完整验收。Windows x64/ARM64 原生复验未通过前不开放自动模式。

Windows 实验用例覆盖目标：在 AppContainer 中启动 Python 并 resolve 工作路径；工作区已有嵌套文件可读、工作区可写、相邻目录 canary 不可读写、容器专属 profile `LOCALAPPDATA` 可写且退出后删除；宿主 loopback 正向对照成立而 AppContainer 连接被拒、主进程正常退出与超时后的子进程回收、`process_limit=1` 阻止再启动子进程；ACL 恢复后，同一 Package SID 不能再写工作区。边界实际是“任务工作区 + 当前容器的私有临时 profile 数据区”，TEMP/TMP 仍固定到任务工作区；profile 不复用、不允许落到宿主 profile，API 删除失败或目录残留均使清理失败。另有跨平台环境块测试验证普通 Job 与 AppContainer 路径均保留盘符伪变量、排序和宿主变量不继承。CI #105 固定 whoami `LOCALAPPDATA` 单变量 A/B 在两架构成功，但正常路径接入后 #106–#112 的 Python 仍无法启动；#112 profile marker 两架构均缺失，进程上限同载荷正反对照通过组件断言。工作区/网络及后代清理 notice 是局部通过，不代表 AppContainer/R2.3 已验收。

必须在 GitHub Actions 的 Windows x64 与 ARM64 runner 同时通过，并保持纯 wheel / Python 3.11 路径。当前 Linux 本机仅验证了非 Windows 拒绝分支、链接/硬链接防护、环境块结构、显式属性指针对齐分配、SID/API 内存所有权模拟、固定命令白名单和环境变量差分；它**没有**执行任何 Win32 API。CI #91–#105 双架构的 AppContainer 启动探针失败，#92–#105 可见 notice 包含错误码 203；#106–#112 的 profile 主路径可启动系统 CMD，但 Python 均退出 `0xC0000135`。CI #102 已确认 profile 创建及 attribute 初始化/更新成功；size-query 122/48 符合 Microsoft 预期。#112 两架构均未写 profile marker；同载荷 process-limit 正反对照通过组件断言。工作区、loopback 和后代清理的组件 notice 不替代实际 Python 启动、profile 写入/删除、全套文件/网络隔离契约；Windows 自动模式继续关闭。

目前仍缺少真实 Windows 的 IPv4/IPv6、UDP、DNS、外网直连拒绝、受保护 Git 元数据与凭据 canary、主动脱离/显式换身份尝试、profile/ACL 多轮泄漏以及更完整的失败恢复测试。CI #112 的进程上限正反对照通过组件断言，但 profile 专属目录写入仍失败、路径身份待复核，Python 主执行器也无法启动。Windows R2.3、R2.2 和完整 R2 均未验收；`policy_contract_ready` 必须继续为 false。

## 风险与成本

- ACL 变更需要完整扫描工作区，体积很大时耗时可能明显；MXC issue #572 报告兼容路径的全树 ACE 传播在 Python 安装目录上约需 35 秒/命令。ICODE 尚无大目录实测；扫描失败、任何 ACE 清理失败或 profile 删除失败都必须留下失败结果。当前实验只支持本地目录，不接受 UNC。
- 单次 Python 解释器/模块依赖可能位于工作区之外；不准因此放开整个用户目录或系统盘。必须证明最小运行时只读授权和 `Path.resolve()` 在 AppContainer 中可用，且衡量引入 ACL 的体积与启动耗时。
- 仅给目录 SID 授权并不能替代工作区构造合同：生产接入前要确认执行根不包含 `.git` 指针/元数据，并继续证明项目链接和重解析点无法访问外部路径。
- 企业策略可拒绝创建 AppContainer profile，API 失败必须阻止命令执行，不可退回普通 Job。
- 默认断网可不要求管理员；Windows 临时代理路径仍需管理员可管理的网络策略或等价可信服务，拒绝授权时保持断网。

### 2026-09-25 UTC 追加：默认临时路径与自定义环境块

- Microsoft [GetTempPath2W](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-gettemppath2w) 对非 SYSTEM 进程按 `TMP`、`TEMP`、`USERPROFILE`、Windows 目录顺序选路径，且不检查目录是否存在或当前进程是否有权限。ICODE 显式把前三项指向工单工作区，所以 `LOCALAPPDATA` 位于 profile 子目录并不能解释 TEMP 路由或 Python 加载失败；CI #120 的 `api_temp=false` 只排除与 API `Temp` 完全相同。
- [CreateAppContainerProfile](https://learn.microsoft.com/en-us/windows/win32/api/userenv/nf-userenv-createappcontainerprofile) 说明 profile 文件夹受 ACL 保护，但没有保证 `Temp`、`Local` 或 `LocalState` 子目录预创建。[io-harness 0.86.0 固定源码](https://docs.rs/io-harness/0.86.0/src/io_harness/sandbox/appcontainer.rs.html#1045-1114)也构造显式环境块并将临时目录放进其授权工作区。取舍：**采纳**由可信调用方显式构造环境块、明确设置 TMP/TEMP 的机制（ICODE 已实现）；**暂缓**复制 Rust 实现及扩大运行时 ACL。FastRender 固定提交 `19bf1036105d4eeb8bf3330678b7cb11c1490bdc` 同样只显式重设 `TEMP/TMP`，未提供 `LOCALAPPDATA` 重写证据，故不据此推断 Windows 机制。下一步先用不输出路径的白名单分类探针区分 `Temp`、`Local`、`LocalState`、其他单层/多层子路径；沿用同 SID/Job，不改 ACL，不新增编译。

### 2026-09-25 UTC CI #120 回执与 #121 探针

- [CI #120 x64](https://github.com/ayukyo/icode/actions/runs/36081977910/job/107905707747) 与 [ARM64](https://github.com/ayukyo/icode/actions/runs/36081977910/job/107905707999) 的脱敏 notice 均为 `alias_match=false`、`equals_api=false`、`relation=api_child`、`api_temp=false`、`stat=not_found`、profile marker 缺失，Python 仍退出 `0xC0000135`。这证明当前子进程观察到的值不同于环境块中传入的 API 路径，但具体后缀未知，且不能推断路径差异导致 Python 加载失败。
- 微软 [AppContainer 启动指南](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer)只示例 `LOCALAPPDATA=...\\AC`、`TEMP/TMP=...\\AC\\Temp`；[GetAppContainerFolderPath](https://learn.microsoft.com/en-us/windows/win32/api/userenv/nf-userenv-getappcontainerfolderpath) 定义 LocalAppData 返回值，[CreateAppContainerProfile](https://learn.microsoft.com/en-us/windows/win32/api/userenv/nf-userenv-createappcontainerprofile) 未保证特定子目录。没有官方依据把 MSIX `LocalState` 推定为桌面 AppContainer profile 的子目录。

### 2026-09-25 UTC CI #121 子目录分类回执

- [CI #121 x64](https://github.com/ayukyo/icode/actions/runs/36083440360/job/107910090970) 与 [ARM64](https://github.com/ayukyo/icode/actions/runs/36083440360/job/107910091117) 均将 actual `LOCALAPPDATA` 分类为 API profile 下的多层子路径（`api_child_nested`）；`alias_match=false`、宿主 `stat=not_found`、profile marker 缺失、Python 退出 `0xC0000135`。不能从共同出现推断该路径分类是 Python 失败原因。
- 工作区写入/嵌套读取、相邻目录拒绝、loopback 拒绝、Job 进程上限正反对照和后代清理 notice 均通过其各自组件断言；本轮完整 AppContainer 作业仍失败，故不能把它们合并成 Windows 沙箱通过。
- 首轮分类只区分了多层/单层，信息仍不足。本地测试已转为在多层场景只保留白名单首层类别（`Temp`、`Local`、`LocalState`、其他），继续隐藏任意子路径；等 CI #122 核实双架构结果。无论首层为何，暂不创建目录或更改 ACL。

### 2026-09-25 UTC CI #122 与相邻上游源码复核

- CI [#122 x64](https://github.com/ayukyo/icode/actions/runs/36083962877/job/107911650724) 与 [ARM64](https://github.com/ayukyo/icode/actions/runs/36083962877/job/107911650705) 均返回 `relation=api_child_other_nested`、`alias_match=false`、`stat=not_found`、marker 缺失、Python `0xC0000135`。工作区/网络/Job/进程清理 notice 为各自组件证据；不能从路径和 Python 失败共现推断因果。
- 补充观察（不加入固定 20 项热门名单）：Harn v0.10.142，固定源码提交 [`8f9587982efa0d515230ee04ae4559fc60f1f394`](https://github.com/burin-labs/harn/blob/8f9587982efa0d515230ee04ae4559fc60f1f394/crates/harn-vm/src/stdlib/sandbox/windows.rs)，采用每进程 AppContainer + Job，调用 `GetAppContainerFolderPath`，创建 `<profile>\\Temp`，并构造 `LOCALAPPDATA`/`TEMP`/`TMP` 覆盖；其进程沙箱还可按 preset/root 对只读工具链目录运行 `icacls` 授权。该提交自报 pre-1.0；本次核对到的环境测试验证的是环境块序列化，并非 Windows 原生 AppContainer 内启动 Python 的实测，因此不据此判定 Harn 已解决 ICODE 的环境观察。
- 取舍：**采纳方向而不照抄实现**——将 child-process 运行时只读依赖与 Agent 自身文件工具可读范围分开审查；ICODE 当前仅 Linux Landlock helper 有独立 Python runtime roots，Windows AppContainer runner 尚未接入此类授权。**暂缓**默认递归开放完整 Python/toolchain/user roots：递归 ACL 有耗时与撤权风险，Harn 的 package-manager preset 文档还涵盖 `.netrc`/`.pypirc` 等凭据配置，不能隐式扩权。不得复制 Rust 代码或仅凭静态 env 测试宣称跨平台可用。
- 另发现运行时文件直读探针把 notice 放在全部候选文件循环结束之后，任何早期断言都会丢掉该组逐文件观测。下一轮把无路径 notice 移到每个文件回执之后、断言之前；按单文件区分 `read_ok`、访问拒绝、路径/文件缺失等类别，随后再判断最小只读运行时授权实验。

### 2026-09-25 UTC CI #123 直读探针复核

- [CI #123 x64](https://github.com/ayukyo/icode/actions/runs/36085435118/job/107916150553) 与 [ARM64](https://github.com/ayukyo/icode/actions/runs/36085435118/job/107916150560) 均在 AppContainer 综合测试步骤失败；脱敏 annotations 仍显示 Python `0xC0000135` 与 profile marker 缺失，未出现 runtime direct-read 单文件结果。其它平台阶段矩阵通过不改变 Windows 验收状态。
- 复核发现 `len(runtime_files) >= 4` 的样本门槛在 notice 之前执行，因此 #123 未给出候选清单证据。增加候选/可用样本数及固定标签 notice，保留原四样本门槛；仍不输出路径，不把 DLL 状态码解释为具体依赖或 ACL 失败。
- Windows SDK `ntstatus.h` 固定版本定义 `0xC0000135` 为 `STATUS_DLL_NOT_FOUND`（[SDK 源码](https://github.com/microsoft/win32metadata/blob/1bfb76db1c360653bdcb56512af0fdf987aceab8/generation/WinSDK/RecompiledIdlHeaders/shared/ntstatus.h#L4921-L4927)）；微软[DLL 搜索顺序](https://learn.microsoft.com/en-us/windows/win32/dlls/dynamic-link-library-search-order)显示直接或传递依赖搜索不等同于顶层 EXE 可执行路径。ICODE 最小环境 `PATH` 仅含 EXE 父目录和 System32，尚未验证完整 DLL 依赖闭包。CPython `._pth`/`PYTHONHOME`/`pyvenv.cfg` 影响解释器模块搜索（[3.11 文档](https://docs.python.org/3.11/using/windows.html#finding-modules)），但目前无进程已进入 Python 的证据，故暂缓改动这些设置。
- Harn v0.10.142 固定源码在 profile 下创建 `Temp` 目录（[行 395–420](https://github.com/burin-labs/harn/blob/8f9587982efa0d515230ee04ae4559fc60f1f394/crates/harn-vm/src/stdlib/sandbox/windows.rs#L395-L420)），可作单变量目录准备 A/B，但这并不解释 DLL 状态码；先完成 inventory/direct-read 与依赖闭包证据，再考虑低风险可撤销实验，不继承完整宿主 `PATH` 或递归授权 runner/home。

### 2026-09-25 UTC CI #124 与独立直读步骤

- [CI #124 x64](https://github.com/ayukyo/icode/actions/runs/36086599173/job/107919764633) 与 [ARM64](https://github.com/ayukyo/icode/actions/runs/36086599173/job/107919764585) 均在综合 AppContainer 测试失败，Python `0xC0000135`、profile marker 缺失；R2.1、通用 Python 3.11/3.12 和 R2.2 非 Windows 子项通过。
- #124 未显示 #123 代码调整后新增的 inventory notice。公开 annotations 只给 workflow command 失败，不足以判断单测未执行、候选构造异常或平台 notice 收集限制。新增单独执行该单测的 Windows CI 步骤，并将该诊断步骤设为可继续；完整单测仍保留原正式门禁并再次运行该用例。
- 不新增权限或解释器环境变更。下一轮依据独立步骤的可用标签数及每文件 `copy_error_class`、启动状态、清理状态决定是否扩充运行时依赖样本；读取成功只证明文件内容可读/复制，不单独证明 DLL 可映射执行。

### 2026-09-25 UTC CI #125：双架构运行时文件访问回执

- [CI #125 x64](https://github.com/ayukyo/icode/actions/runs/36087232240/job/107921726078) 与 [ARM64](https://github.com/ayukyo/icode/actions/runs/36087232240/job/107921726100) 的隔离直读步骤都执行完成。两架构候选清单均为 6 项、其中 5 项可用：`system32_control`、`python_executable`、`python_shared_library`、`stdlib_pathlib`、`stdlib_encodings`；`stdlib_archive` 未提供。
- 两架构均观察到 `system32_control=read_ok`；Python EXE、共享库、`pathlib.py`、`encodings/__init__.py` 均 `copy_error_class=access_denied`、探针退出 1、`cleanup_ok=true`。x64 样本大小依次为 103192、5800216、49972、6058 bytes；ARM64 为 102680、6076184、49972、6058 bytes。原始路径未进入 notice。
- 完整 AppContainer Python 两架构仍退出十进制 `3221225781`（`0xC0000135`，`STATUS_DLL_NOT_FOUND`），marker 缺失。和逐文件访问拒绝同时出现，使“AppContainer SID 无法读取 Python 安装树”成为优先验证假设；但直接读探针不是 loader 依赖映射测试，不能证明哪一个 DLL 缺失，也不能仅凭共现认定 ACL 就是唯一根因。
- **下一实验（代码已实现，待 CI）：**仅允许 GitHub Windows runner 的当前解释器，以 `sys.prefix` / `sys.base_prefix` 为候选根；在任何写 ACL 前拒绝 UNC/卷根/系统目录/包含 home 的路径/工作区重叠/reparse point/hardlink/null 或 protected/defaulted DACL，并把扫描限制为 100,000 个对象、30 秒。完整记录每个对象的 DACL bytes、control/revision、present/defaulted 状态与文件身份；只给本次随机 Package SID 添加只读/执行继承 ACE，注入运行时写入拒绝检查。恢复根 DACL 后必须等待并逐对象精确比对全树、确认 SID 无残留；失败则 `cleanup_failed` 且阻止命令继续。该差分有独立 Actions 步骤（诊断失败允许继续以便保留回执），之后完整 AppContainer 测试再次运行并仍是正式门槛。实验仅在临时托管 runner 上运行，生产执行器完全未接入；如果双架构任一端不能精确恢复，就停止 ACL 路线，不以宽松回退补救。读访问成功仍须同时满足 Python 启动、marker、工作区/网络门禁和 ACL 恢复。

Microsoft 文档明确了 inheritable ACE 的传播与控制标志行为，但 `SetNamedSecurityInfoW` 不是针对并发写者的原子事务；因此全树前后精确核对是实验硬门槛，并不等价于与并发安装/更新隔离：[ACE inheritance](https://learn.microsoft.com/en-us/windows/win32/secauthz/ace-inheritance-rules)、[automatic propagation](https://learn.microsoft.com/en-us/windows/win32/secauthz/automatic-propagation-of-inheritable-aces)、[`SetNamedSecurityInfoW` remarks](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-setnamedsecurityinfow#remarks)。

### 2026-09-25 UTC CI #127：差分预检暂未到达 ACL 写入

- [x64](https://github.com/ayukyo/icode/actions/runs/36090932965/job/107933023862) 和 [ARM64](https://github.com/ayukyo/icode/actions/runs/36090932965/job/107933023845) 的新独立诊断都报告 `runtime tree contains unsafe filesystem entries`，候选解释器未启动，`candidate_cleanup=true`；实现是在 runtime snapshot 阶段失败，尚未新增任何 runtime ACL。综合 Python 仍为 `0xC0000135`，其余 Windows 组件 notice 不构成完整通过。
- #127 的回执没有给出具体拒绝种类，因此不能推断 Python 安装树包含哪类对象。下一版只透出由预检器产生的固定拒绝类别/说明，不记录路径；不跳过项、不放宽 root 校验。若 CI 显示确有 reparse/hardlink/special file，保留拒绝并判断该树不适配；若是可修正的枚举失败，再单独评估可恢复的窄方案。

### 2026-09-25 UTC CI #128：runtime tree 含 reparse point

- [Windows x64](https://github.com/ayukyo/icode/actions/runs/36091394407/job/107934399982) 与 [ARM64](https://github.com/ayukyo/icode/actions/runs/36091394407/job/107934399966) 的诊断现已将拒绝原因收窄为 reparse point；尚未区分 symbolic link、junction/mount point 或其它 tag。候选未启动、未改任何 Python runtime DACL；两架构原始 AppContainer Python 仍是 `0xC0000135`。
- **不直接允许该项：**Windows/Python 提供 `st_reparse_tag` 可用于脱敏类型识别，但 Microsoft 文档没有定义 `GetNamedSecurityInfoW` / `SetNamedSecurityInfoW` 面对链接时操作本体还是目标，也未说明继承 ACE 是否穿过 junction。当前实现回执只允许固定类别 `symbolic_link` / `mount_point` / `other_reparse`，不记录路径、目标或原始 tag 值；#128 本身尚未包含此类别结果。保持 fail-closed。任何后续放行评估必须先对一次性临时目录用 handle-based API 比较链接、目标及后代 DACL，再验证逐对象精确恢复；不能触碰 runner Python/toolcache。 [Python `os.lstat` / `st_reparse_tag`](https://docs.python.org/3.11/library/os.html#os.stat_result)、[Microsoft reparse point operations](https://learn.microsoft.com/en-us/windows/win32/fileio/reparse-points-and-file-operations)、[symbolic-link API effects](https://learn.microsoft.com/en-us/windows/win32/fileio/symbolic-link-effects-on-file-systems-functions)、[`GetNamedSecurityInfoW`](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-getnamedsecurityinfow)、[`SetNamedSecurityInfoW`](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-setnamedsecurityinfow)、[ACE automatic propagation](https://learn.microsoft.com/en-us/windows/win32/secauthz/automatic-propagation-of-inheritable-aces)。

### 2026-09-25 UTC CI #129：两架构具体类别为 symbolic_link

- [Windows x64](https://github.com/ayukyo/icode/actions/runs/36092603966/job/107937999811) 与 [ARM64](https://github.com/ayukyo/icode/actions/runs/36092603966/job/107937999747) 都在 ACL 预检阶段报告 `symbolic_link`，候选未启动，清理为真且无 runtime DACL 变更；完整 AppContainer Python 仍退出 `0xC0000135`，已抽样的 runtime 文件仍不能从容器读取。
- #129 没有泄露 offending path 或 target，因此不能称它为 `python.exe` 链接，也不能判断 target 是否在 runtime 根内。暂不放行；下一 CI 仅用 `readlink` 文本做词法目标关系计数（根内/根外/未知），不跟随链接、不泄露名称/路径、不改 ACL。仅当出现根内链接时，才考虑进一步用一次性临时树实测 link/target/后代安全描述符传播和恢复；实验通过也不自动改变 hosted runtime 预检策略。

### 2026-09-25 UTC CI #131 与 runtime staging 路线

- CI [#131 x64](https://github.com/ayukyo/icode/actions/runs/36093962446/job/107942126150) 与 [ARM64](https://github.com/ayukyo/icode/actions/runs/36093962446/job/107942126118) 清点到 6,721 项、1 个 symbolic link，`readlink` 词法关系为 `inside_root`。这不证明真实解析对象身份，也不构成放行 ACL 的依据。现有 ACL 差分仍因 `unsupported_workspace_entry` 在授权前拒绝，未修改 runner runtime DACL；原 Python 仍以 `0xC0000135` 退出，runtime 抽样直读仍为 `access_denied`。
- 官方 CPython Windows embeddable ZIP 可供应用随包携带，但它是“应用嵌入运行时”而非通用用户 Python：不含 pip、Tcl/Tk 和文档；3.11.16、3.12.14 已是仅源码安全更新，3.11/3.12 的最后 Windows binary installer 分别为 3.11.9/3.12.10。[3.11.16](https://www.python.org/downloads/release/python-31116/) · [3.12.14](https://www.python.org/downloads/release/python-31214/) · [3.12 Windows embeddable 文档](https://docs.python.org/3.12/using/windows.html#the-embeddable-package)。3.13.15 官方 x64/ARM64 embeddable ZIP 分别为 11,010,501 / 10,403,665 bytes，合计约 20.4 MiB；ICODE 元数据 `requires-python >=3.11` 且无核心依赖，不能由此推断用户项目兼容 3.13。[官方文件清单](https://www.python.org/ftp/python/3.13.15/)。因此先不把旧版本 embed ZIP 固定进 wheel，也不以新 minor 替换用户选定的解释器。
- **本提交新增、待 CI 验证的诊断切片：**在独立 Windows Actions 步骤将当前 runner Python 前缀复制到唯一 temp 子目录；目标名及父路径均受限，复制前逐个检查 symbolic link 的真实解析目标必须仍在源根内且为普通文件（目录链接、链接循环、断链及越界目标一律拒绝），复制后要求 staging 无任何 reparse point。ACL 候选只作用于该 disposable staging 根，原 host runtime/toolcache 不在授权集合；使用现有 Package SID read/execute ACE 与逐对象精确 DACL 回滚门。验证模块/DLL 导入、`sys.prefix`、子进程、workspace 写、stage 写拒绝、原 runtime 直读拒绝、loopback 拒绝和 staging/profile/ACL 清理。该试验用于判断“同版本 host runtime 复制 staging”是否可行；**不是**生产路径，不承诺对并发源 runtime 变更安全，也不解决分发与项目 venv 兼容性。Windows R2.3、自动模式和完整 R2 继续关闭。
- **默认 CI 安全边界：**移除对原 host runtime 直接改 DACL 的 A/B 步骤；此前探针虽因 reparse 预检而未授权，但完整测试套件也会自动触发该候选。该测试现要求显式 `ICODE_DIAGNOSTIC_RUNTIME_ACL=true`，仅保留给隔离、可丢弃的人工诊断环境；常规双架构 CI 只在临时 staging 副本上测试 ACL。

### 2026-09-25 UTC CI #133/#134：staging 正向对照通过，ACL 精确恢复失败

- CI [#133](https://github.com/ayukyo/icode/actions/runs/36100147033) 和 [#134](https://github.com/ayukyo/icode/actions/runs/36100928044) 的 x64/ARM64 runtime 树均为 6,721 项、1 个根内词法 symbolic link；复制逻辑将该链接物化为普通文件，staging 无 reparse point。临时副本在宿主可加载 `_ctypes/_sqlite3/_ssl`、标准库与 Python 3.11.9。
- AppContainer 无 runtime ACL 的基线仍退出 `0xC0000135`；候选进程启动后退出 1。#134 的固定类别回执为 `runtime_acl_snapshot`、`runtime_acl_access_granted`、`runtime_acl_restore_failed`，ACL 根确认仅为 staging，源树 DACL 未修改；candidate `cleanup_failed`，不能把未生成的 Python/workspace/network/child markers解释成某个具体边界失败。
- **恢复规则不变：**不能仅凭 staging 可删除而把失败改报成功；先诊断全树首次 mismatch 属于 path-set、root/descendant DACL、descriptor metadata、SID residual 或 inspection error。无论分类为何，只有精确恢复验证和完整 AppContainer 组合验收都通过才考虑继续；若持续无法恢复即停止继承 ACL 路线并评估替代，不作宽松回退。

### 2026-09-25 UTC CI #135/#136：恢复差异定位到根对象 control 元数据

- CI [#135](https://github.com/ayukyo/icode/actions/runs/36102565397) 已确认两个架构的 staging 在检测后被删除，但当时分类只报告 `metadata_changed=true`。CI [#136](https://github.com/ayukyo/icode/actions/runs/36103288445) 将元数据拆分后，x64 与 ARM64 均报告 `object=root`、`dacl_changed=false`、`control_changed=true`，而 revision/present/defaulted/file identity 均未变化、`sid_residual=false`；授权 root 是 disposable staging，源 Python runtime 未改。
- 两架构的 Python staging 宿主正向控制通过；AppContainer candidate 仍退出 1、`cleanup_failed`，并且 ACL 恢复失败导致候选 runtime/workspace/network/child assertions 均无效。不得把控制字段差异解释为无害或把 staging 删除替代 ACL 恢复。
- Microsoft 文档指出 `SetNamedSecurityInfo` 设置 DACL 时会传播可继承 ACE，且自动继承控制位可能被设置；这是待核对的解释，不是本轮对具体位的实测。下一轮诊断仅增加 `control_delta` 掩码，输出不含路径/ACL/SID；只有位值明确后再评估能否在 staging snapshot 前安全规范化并恢复，或停止继承 ACL 路线。此前硬门槛不变。
