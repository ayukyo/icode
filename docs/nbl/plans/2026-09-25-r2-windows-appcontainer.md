# R2.3 Windows AppContainer 与 Job Object 实验计划

- 日期：2026-09-25 UTC
- 状态：**未通过验收，Windows 自动模式不开放。** CI #154 双架构已消除全部 8.3 短名/长路径断言失败；完整 Windows 测试仍有 2 项失败：profile 写入 marker 缺失、宿主 Python 退出 `0xC0000135`。当前主线新增容器内只读 profile API/token/原始环境块观测，纯单测与脚本语法通过，待 CI #155；不扩大 ACL，也不把 staged tempfile 子项通过外推为 R2.3。
- 依据：[R2 正式设计](../specs/2026-09-23-r2-cross-platform-isolation-design.md) §6.3、§14；[持续竞品对照](../../agent-landscape-live.md)

> 注：下方按时间追加验证记录。阶段状态以最新 CI 和本机回归为准，历史记录不代表当前 Windows 后端已通过。

## 三问与边界

1. **真实问题：**Windows Job Object 已提供工单级活动进程限制和退出回收，但不能限制文件或网络；R2.3 仍缺 OS 强制的工作区边界。
2. **已有实现：**`src/icode/windows_job.py` 负责挂起创建、加入 `KILL_ON_JOB_CLOSE | ACTIVE_PROCESS` Job、再恢复进程；`SandboxPolicy` 已表达读写根和默认断网。当前 `run_windows_job` 是开发探针，不接自主执行。
3. **调用链影响：**本实验仅新增 `run_windows_appcontainer`，沿用现有 Job runner，并以 AppContainer Package SID 为进程安全能力。生产 `NativeChainExecutor`、`policy_contract_ready`、`icode doctor` 和自动模式均未开放。

## 研究结论与选择

- **选择性采纳 AppContainer 机制：**Microsoft 官方文档说明，AppContainer 可用 `CreateAppContainerProfile` 建立当前用户 profile，再通过 `STARTUPINFOEX` 的 `PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES` 创建进程；不授网络 capability 时没有网络能力。ICODE 使用 Python 标准库 `ctypes` 调 Win32 API，不增加安装依赖。参考：[AppContainer 启动](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer)、[隔离模型](https://learn.microsoft.com/en-us/windows/win32/secauthz/appcontainer-isolation)、[创建 profile API](https://learn.microsoft.com/en-us/windows/win32/api/userenv/nf-userenv-createappcontainerprofile)。
- **权限与文件策略：**每次运行随机 profile / Package SID；只给传入的独立工单目录添加临时可继承 ACL，原仓、`.git`、common gitdir、用户目录和凭据路径不加该 SID。执行完恢复原始根 ACL，并遍历校验 Package SID ACE 已从当前子树消失；另外以相同 SID 做工作区写入拒绝后测，再删除 profile。工作区含重解析点、硬链接、受保护 ACL、null DACL 或网络共享时拒绝启动。Windows 自动 ACL 传播规则见[官方说明](https://learn.microsoft.com/en-us/windows/win32/secauthz/automatic-propagation-of-inheritable-aces)。
- **Job 组合：**`CREATE_SUSPENDED` 与 `EXTENDED_STARTUPINFO_PRESENT` 组合；AppContainer 创建后先加入独立 Job，再恢复主线程。进程创建、属性设置、Job 归属任一失败时均不运行普通宿主命令。
- **不开临时网络：**AppContainer 不授 `internetClient` / `privateNetworkClientServer`，当前仅探测本机 loopback 连接是否建立；连接失败本身不证明具体 WFP/策略原因。需要按域名临时联网时须另行实现可验证的 WFP/防火墙身份规则与受控代理；环境变量和 AppContainer internet capability 不足以表达域名 allowlist。

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

- CI [#109 x64](https://github.com/ayukyo/icode/actions/runs/36069030309/job/107865391485) 与 [#109 ARM64](https://github.com/ayukyo/icode/actions/runs/36069030309/job/107865391466) notice 报告 workspace 读写/外部写拒绝/loopback 连接失败、正常后代回收、runner timeout 后代回收、`process_limit=1`、环境块及 profile A/B 子项通过。研究复核发现进程探针在 release handshake 后仍只观察 0.2 秒，没有相同 payload 正向对照；这比 #108 清晰，但不足以排除调度延迟造成的假阴性。R2.3 仍不能验收，因为 Windows Agent 尚不能启动 Python 执行器。
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

### 2026-09-25 UTC CI #137：根对象变化确认为 `SE_DACL_AUTO_INHERITED`

- CI [#137](https://github.com/ayukyo/icode/actions/runs/36104010820) 的 Windows x64 与 ARM64 均回报十进制 `control_delta=1024`（`0x0400`），其余 #136 类别保持不变：DACL bytes/身份无变化、无 SID 残留，staging 删除成功；candidate 仍 `cleanup_failed`，workspace/network/child 断言无效。
- Microsoft 将 `0x0400` 定义为 `SE_DACL_AUTO_INHERITED`；其自动传播说明指出，对对象设置 DACL 时系统会应用当前继承模型并可能设置此位。与本轮实测结合，可解释为何恢复相同 DACL 后 control 仍有系统规范化差异；该位仍不是可忽略理由。[control flags](https://learn.microsoft.com/en-us/windows/win32/secauthz/security-descriptor-control) · [automatic propagation](https://learn.microsoft.com/en-us/windows/win32/secauthz/automatic-propagation-of-inheritable-aces)
- **下一项仅限 disposable staging 的实验：**在添加 Package SID 前重设 staging 根的同一 DACL；要求 root 的 DACL bytes、identity、revision/present/defaulted 不变，control 唯一变化为 `0x0400`；随后以该系统规范化状态为 snapshot baseline，并照旧要求临时授权后全树逐对象精确恢复。任何其它差异都停止 candidate。不得修改原 runtime，也不得把 staging 删除作为 ACL restore 证据。此实验即使通过也只验证 disposable-runtime 路线，不直接开放生产 Windows 自动模式。

### 2026-09-25 UTC CI #138：staging ACL 精确恢复通过，Python 组合探针仍未闭环

- CI [#138](https://github.com/ayukyo/icode/actions/runs/36105290309) x64/ARM64 均报告 `acl_baseline_normalization_delta=1024`、`acl_restore_verified=true`、restore classifier `state=restored`、`candidate_cleanup=true`、`staging_removed=true`，且 `source_acl_untouched=true`。因此这轮证明了“staging 先规范化，再对规范化快照精确恢复”的 ACL 子项；不把它外推为宿主 runtime 或生产 Windows 通过。
- 两架构候选进程 `executed=true` 但退出码 1，结果 JSON、runtime/workspace/network/child marker 均未生成；普通无 ACL baseline 仍为 `0xC0000135`。因此不能判断候选是否进入脚本，也不能声称工作区或网络测试失败/通过。其它 CI 矩阵通过。
- 下一轮只增加 staging 脚本的固定阶段 marker：命令脚本启动、标准库导入、运行时路径检查、写拒绝、源 runtime 拒绝、loopback 拒绝、workspace 和 child；异常只记录白名单阶段/异常类，不记录路径或错误正文。ACL 初始化与回滚门继续保持，production runner 未接入。

### 2026-09-25 UTC CI #141：strict `Path.resolve()` 权限失败，根因仍待 API 分解

- CI [#141](https://github.com/ayukyo/icode/actions/runs/36110318680) 的 Windows x64 与 ARM64 staged Python 均已启动脚本并完成标准库导入，但在 `Path(sys.executable).resolve(strict=True)` 得到 `PermissionError`，随后退出 1。该回执将此前“Python 启动后退出 1”缩小到路径规范化调用；此时 runtime 写拒绝、原 runtime 读取拒绝、loopback、workspace 与子进程均尚未执行，不能把它们解释为通过或失败。ACL 恢复精确验证、源 runtime ACL 未修改和 staging 删除仍单独通过。
- CPython Windows 源码显示 `Path.resolve(strict=True)` 经 `ntpath.realpath` 调用 `_getfinalpathname`，底层使用 `CreateFileW` 和 `GetFinalPathNameByHandleW(..., VOLUME_NAME_DOS)`；Microsoft 文档将 `VOLUME_NAME_DOS` 定义为返回盘符路径。[CPython 3.11 `posixmodule.c`](https://github.com/python/cpython/blob/3.11/Modules/posixmodule.c) · [CPython `ntpath.py`](https://github.com/python/cpython/blob/main/Lib/ntpath.py) · [Microsoft API](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfinalpathnamebyhandlew)。Codex issue [#45871](https://github.com/openai/codex/issues/45871) 的提交者在 AppContainer 中报告同一 DOS 最终路径查询遭拒、NT 路径查询成功；这是已打开的用户报告而非 Codex 维护者确认。它与 ICODE 的异常机制吻合，但 ICODE 尚未记录到底层 API，故根因标为**高相关假设，未证实**。
- **本轮诊断切片（待双架构 CI）：**在同一可信 disposable staging 路径分别记录词法 `absolute`、`stat`、字节读取、strict/non-strict `resolve`、`nt._getfinalpathname`，并直接比较 Win32 `CreateFileW(access=0)` 及同一文件的 `GetFinalPathNameByHandleW(VOLUME_NAME_NT/DOS)`。回执仅留成功状态、异常类及 WinError 数字，不包含路径、SID、ACL 或错误正文；strict resolve 单项失败后仍使用 `absolute()` 继续执行其余沙箱边界探针。`absolute()` 不解析重解析点，不能当作物理路径 containment 证明；它只用于此处已复制并检查过的无 reparse staging 样本路径比较。生产 runner 和 `policy_contract_ready` 不变，Windows 自动模式仍关闭。

### 2026-09-25 UTC CI #147：探针回执语义与跨架构门禁修正

- [CI #147](https://github.com/ayukyo/icode/actions/runs/36122289071) 的 Windows x64/ARM64 作业都未通过。两架构公开 notice 显示 staging ACL 已精确恢复、清理通过、宿主 staging Python 3.11.9 正向控制成功；候选完成脚本启动、导入、路径、runtime 写拒绝与 source-read 检查，但 `network_check_completed=false` 且 `python_failure=invalid_marker`。网络调用附近是尚未定位的失败边界，不能据此认定 loopback 被策略拒绝，也不能把随后工作区/子进程标记缺失解释为它们的结果。
- 同一轮 Ubuntu 22.04/24.04 ARM64 wheel probe 都因可选系统路径 `/lib64` 不存在，在 `_validate_non_executable_workspace()` 的 `resolve(strict=True)` 处失败。修正只将固定可选系统可执行根改为非严格解析；工作区本身仍严格解析。原生 helper 对这些系统根使用 `required=0`，遇到 `ENOENT` 即按可选项跳过；新回归模拟 `/lib64` 缺失并继续验证只读工作区与可执行白名单不能重叠。
- **网络结论修正：**Microsoft Winsock 文档给出连接/系统状态的错误码语义，但单个错误码不标识 WFP 或策略是拒绝原因；Microsoft 的 loopback 默认阻断说明针对 packaged applications，不能直接外推到 ICODE 通过 `CreateAppContainerProfile` 创建的 CI 进程。[Winsock errors](https://learn.microsoft.com/en-us/windows/win32/winsock/windows-sockets-error-codes-2) · [Microsoft loopback IPC](https://learn.microsoft.com/en-us/windows/apps/develop/communication/interprocess-communication#loopback)。Project Zero 2021 在其测试环境观察到 AppContainer loopback 由 WFP receive/accept 层丢弃并表现为 timeout；这是特定环境的实验记录，不是稳定 API 保证。[Project Zero analysis](https://projectzero.google/2021/08/understanding-network-access-windows-app.html#localhost-access)
- **采纳/暂缓：**采纳安全的阶段/异常类型 marker 与“宿主同一活跃 listener 正向连接成功、容器连接未建立”的诊断设计；结果字段为 `network_connect_failed`。不把 `10013/10060/10061` 等错误直接称为 policy/WFP denial。若以后需要归因，必须收集匹配 AppContainer 身份、目标和 layer 的 WFP classify-drop 证据，或执行隔离环境中的受控 A/B；当前不添加 loopback exemption、不修改宿主网络策略。修正仍待新 CI 双架构验证，不替代 Windows 网络隔离验收；Windows 自动模式继续关闭。

### 2026-09-25 UTC CI #148：双架构 loopback 超时分类与 macOS job 异常

- [CI #148 Windows x64](https://github.com/ayukyo/icode/actions/runs/36125785293/job/108041458358) 与 [Windows ARM64](https://github.com/ayukyo/icode/actions/runs/36125785293/job/108041458385) notice 一致：staging ACL 精确恢复、清理、宿主 Python 3.11.9 positive control 成功；脚本启动、导入、路径、runtime 写拒绝和 source-read 逐项通过，随后在 `network:TimeoutError` 退出。原探针把未附带 WSA code 的 Python `TimeoutError` 误当作未知错误，未写 network-completed marker。新代码单独接纳 `TimeoutError` 为“连接尝试超时”，并只输出 `network_connect_failed=true` 与安全异常类；不声称 WFP/策略拦截，后续 workspace/child 仍需双架构 CI 验证。
- 同轮 Ubuntu 22.04/24.04 ARM64 wheel jobs 已通过，确认缺失可选 `/lib64` 的本机与安装式验证修正有效。macOS Intel 原生 job 通过，`macos-latest` 的 `Verify policy command broker` 步骤失败；公开 annotation 只有退出码，没有失败断言，Actions 日志接口返回 403，因此原因未定位。本轮没有修改 broker 实现；下一轮继续观察该步骤，若复现再按证据诊断。

### 2026-09-25 UTC CI #149：连接超时已分类，路径诊断回执超长

- [CI #149 Windows x64](https://github.com/ayukyo/icode/actions/runs/36126829375/job/108044773273) 与 [Windows ARM64](https://github.com/ayukyo/icode/actions/runs/36126829375/job/108044773248) 都已将之前的 `TimeoutError` 作为连接超时完成处理；候选 Python 退出 0、cleanup 成功，所有脚本 checkpoint（含 network-completed）出现。独立 workflow 步骤仍失败，且后续 `Python disposable staging path-resolution probes` 与 boundary notice 未生成。
- 只读核对输出次序与 `_workflow_json_notice()` 的硬性 500 字符限制后，定位到路径诊断 notice 构造体过长；9 项完整嵌套结构在代表性错误样本下为 671 字符。这是诊断回执门禁失败，不是 candidate 隔离测试的反例或通过证据。新代码保留完整内部操作结果，仅将公开 notice 的操作名固定缩写、字段改为 `[ok,error_class,winerror]`，并以最长白名单异常类测试长度上限。
- CI #149 的 Ubuntu 22.04/24.04 ARM64 wheel、macOS Intel/`macos-latest` 原生探针、macOS `Verify policy command broker` 均通过；因此 #148 的 macOS-latest 失败未复现。Windows 完整外层路径/ACL/workspace/child 断言尚未全部输出验证，自动模式与 R2.3 仍关闭。

### 2026-09-25 UTC CI #150：staging Python 通过，组合门槛暴露路径别名与两项真实失败

- [Windows x64](https://github.com/ayukyo/icode/actions/runs/36128698379/job/108050697474) 和 [Windows ARM64](https://github.com/ayukyo/icode/actions/runs/36128698379/job/108050697703) 的独立 disposable-staging Python 步骤均退出 0；报告脚本启动、导入、路径操作、运行时写拒绝、源 runtime 读取拒绝、网络探针及 staging ACL 恢复。原宿主解释器正向启动对照仍为 `0xC0000135`，这属于测试/候选运行时启动问题，不是隔离成功的证据。
- 综合 59 项 Windows 测试两架构都报告 5 failures、4 errors。8 项的具体断言与 `C:\Users\RUNNER~1`/`C:\Users\runneradmin` 8.3 短长路径不一致有关；当前主工作树已在检查 reparse ancestry 后将真实路径 canonicalize，并将测试期望按同一 canonical root 比较。待 CI #151 验证，不先宣称修复完成。
- 仍有两个真实未通过项：profile 生命周期探针中子进程观察到的 `LOCALAPPDATA` 与 `GetAppContainerFolderPath` 不等，relation 为 API profile 下的多层未知子目录、宿主 `stat=not_found`，目录不可见且 marker 写入类别为 `path_not_found`；普通宿主 Python 在容器内退出 `0xC0000135`，虽然相同副本 staged candidate 成功。两项不能相互归因，且不因 staging candidate 成功而解除生产门槛。
- **上游采纳/暂缓：**Codex `86be5320b068ef67b56348b02aa8c33706955da6` 的真实 Windows smoke-test 与 Python 允许/拒绝配对控制值得采纳；Qwen Code `ab61e04161a30bf825fefede85bcc09ebef7a673` backend admission 失败不回退宿主值得采纳；Gemini CLI `bedef96ef42905bd84a86dbec021c706168e7e2f` 的真实命令集成测试值得参考，但其 ACL/Job warning-and-continue 不适合作为 ICODE 安全验收。暂缓将 staged runtime 方案接生产执行器，直到性能、重复调用复用、安全生命周期和双架构全边界通过均有可验证答案。

### 2026-09-25 UTC 下一诊断片：staged Python 进程环境双 API 观测

- **假设边界：**此前 profile probe 的子进程 `LOCALAPPDATA` 与 `GetAppContainerFolderPath` 不匹配，但没有直接比较 Python `os.environ` 与 Win32 `GetEnvironmentVariableW`。这项观测可以定位“环境块/进程 API/Python 快照”是否分歧；无论是否一致，都不能单独解释 `0xC0000135`，也不能证明访问权限或 DLL loader 根因。
- **实现范围：**只在 disposable staged Python candidate 中观察 `LOCALAPPDATA`、`TEMP`、`TMP` 的 Python 值、Win32 值和 `stat` 分类；原始值仅留在 runner 的临时 workspace marker，主进程在删除该目录前将其转为固定字段：是否定义、Python/Win32 是否相等、`LOCALAPPDATA` 是否等于 API profile，以及路径存在性类别。Actions notice 不发布原值、用户目录或 workspace 路径，编码长度受 500 字符约束。探针不创建/删除 profile 子目录、不修改 ACL、不改变环境块、不接生产执行器。
- **本机验收：**纯 Python 测试覆盖正常摘要、API profile 不匹配、路径脱敏、notice 长度与生成探针语法；需要 Windows x64 和 ARM64 独立 Actions job 才能验证实际 Win32 API。未获得双架构 CI 回执前，结果为“诊断待验证”，不可宣称此诊断完成或 R2.3 通过。
- **竞品研究取舍：**Microsoft [AppContainer 启动指南](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer)仅示例显式 `LOCALAPPDATA`/`TEMP`/`TMP` 配置；[CreateProcessW](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw) 文档没有给出本场景下显式 Unicode 环境块被改写的证据。新鲜对照见[持续竞品对照](../../agent-landscape-live.md)：采纳进程内双 API 观测和环境失败不回宿主；暂缓猜测 profile 子目录、目录创建、ACL 扩张或 staged runtime 生产化。无代码复制与新依赖；安全增量仅为受控诊断数据，验收重点是双架构通过、notice 脱敏/限长及原 ACL 恢复门不变。

### 2026-09-25 UTC CI #151：环境 API 一致，但临时路径仍不可见

- [CI #151](https://github.com/ayukyo/icode/actions/runs/36135745573) 中 staged Python 在 Windows x64/ARM64 均报告 `LOCALAPPDATA`、`TEMP`、`TMP` 的 `os.environ` 与 `GetEnvironmentVariableW` 定义状态/值匹配；但三项 `stat` 分类均为 `not_found`，`LOCALAPPDATA` 也不等于 API profile 路径。notice 不含原始路径。该结果排除了“Python 快照与 Win32 环境 API 看见不同值”这一差异假设，但不能说明目录为什么不可见、是否可被 `tempfile` 使用，亦不能解释 `0xC0000135`。
- 双架构 staged candidate 退出 0、ACL 精确恢复/清理成功；相对 cwd 的 workspace 读写、外部 canary 拒绝、子进程与 Job 进程数正负对照有组件通过 notice。loopback 尝试仍是 `TimeoutError`/连接未建立，不单独证明网络策略拒绝。完整 `Verify AppContainer workspace, network denial, ACL revocation, and Job composition` 步骤两架构仍失败；直接宿主 Python 继续退出 `0xC0000135`，profile 写标记仍为 `path_not_found`。
- **下一小步只测试真实消费者：**在 disposable staging 的 Python 进程内调用标准库 `tempfile.gettempdir()` 并以脱敏结果检查该目录的可用性/创建临时文件；不回显任何路径、不改环境变量、不创建 profile 子目录、不扩大 ACL。继续保留宿主 Python 启动差异作为独立失败门槛。此诊断通过也不等于完整 AppContainer 组合门禁通过，R2.3/Windows 自动模式仍关闭。

### 2026-09-25 UTC CI #152：双 API 仍一致，真实 tempfile 消费者尚未测量

- [CI #152](https://github.com/ayukyo/icode/actions/runs/36139938565) 的 staged Python x64/ARM64 仍观察到 `LOCALAPPDATA`、`TEMP`、`TMP` 的 Python 与 Win32 值匹配，但路径分类为 `not_found`，`LOCALAPPDATA` 与 API profile 不匹配。staged candidate 正常运行；完整 AppContainer 组合步骤仍失败，直接宿主 Python 仍为 `0xC0000135`，loopback 仍只观测到连接超时。该轮未调用 `tempfile`，所以不能据此判断标准临时目录候选或实际文件创建能力。
- CPython 3.11.16 固定源码显示 tempfile 候选优先为 `TMPDIR`、`TEMP`、`TMP`；Windows 后续尝试用户 Temp、系统 Temp 与当前目录，不把 `LOCALAPPDATA` 本身直接作为候选。候选可用性通过真实创建、写入和删除探测，全部失败才抛 `FileNotFoundError`；`gettempdir()` 结果还会在进程内缓存。[固定源码](https://github.com/python/cpython/blob/41388c9cb160d0886d5ca00d2e6c8782608a4549/Lib/tempfile.py) · [3.11 tempfile 文档](https://docs.python.org/3.11/library/tempfile.html)。因此 `stat=not_found` 不能替代真实消费者测试，也不单独构成根因。
- **本次待双架构验证的诊断实现：**staged candidate 现在调用 `tempfile.gettempdir()`，再执行一次 `NamedTemporaryFile` 写入/关闭/自动删除；runner 只保留 TEMP/TMP 精确匹配、workspace、other/unavailable 等固定类别、是否位于 workspace、创建/删除布尔值和白名单异常类。完整原始路径只经过临时 workspace marker，读取摘要后随 staging workspace 一起清理。纯单测覆盖路径脱敏、目录分类、成功/失败结果与 notice <=500 字符。探针不改环境块、不创建 profile 目录、不扩大 ACL，也不接生产执行器；仍保留宿主 Python 启动差异为独立失败门槛。只有 Windows x64/ARM64 notice 与完整步骤回执齐备，才能判断该小诊断是否完成；这不等于 R2.3 或 R2 完成。

### 2026-09-25 UTC CI #153：tempfile 子项通过，组合门禁仍失败

- [CI #153](https://github.com/ayukyo/icode/actions/runs/36143290017) 的 Windows x64 与 ARM64 staged candidate 都完成 `tempfile.gettempdir()` 与 `NamedTemporaryFile` 创建/删除：结果为 `source=workspace`、`within_workspace=true`、`created=true`、`deleted=true`。这说明该候选 Python 可回退到工单工作目录使用临时文件，不说明 profile 私有目录可写，也不解释另一宿主 Python 的加载失败。
- 两架构完整测试仍各有 5 failures、1 error。当前归纳为：路径短名/长名规范化预期有四项失败；profile marker 未出现（子进程退出码 0 但 marker 缺失，写入类别 `path_not_found`）；宿主 Python 以 `0xC0000135`（十进制 3221225781）退出。失败项不能互相归因；尤其不能把 staged candidate 成功解释为原安装树或 profile 写入通过。
- **只读上游复核：**Microsoft `CreateProcessW` 文档说明调用返回时子进程可能尚未初始化完成，必需 DLL 缺失/初始化失败会终止子进程；Windows 错误表将 `0xC0000135` 定义为 `STATUS_DLL_NOT_FOUND`，但不指定缺失模块或根因。[CreateProcessW](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw) · [MS-ERREF](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-erref/596a1078-e883-4972-9bbc-49e60bebca55)。CPython 3.11.9 的 `python.exe` 入口调用 `Py_Main`，而 Python core 是 `python311.dll` 动态库；因此优先检查 Windows image-loader/native DLL 依赖，而不是先改 `PYTHONHOME` 或 `._pth`。[入口](https://raw.githubusercontent.com/python/cpython/v3.11.9/Programs/python.c) · [项目链接](https://github.com/python/cpython/blob/v3.11.9/PCbuild/pythoncore.vcxproj) · [命名配置](https://github.com/python/cpython/blob/v3.11.9/PCbuild/python.props)。原 runtime 文件读取拒绝（CI #125）是优先调查线索，不等同 DLL 映射诊断。
- **本地路径规范化修复（待完整回归与 CI #154）：**`_runtime_reparse_inventory` 仅保留经 `normpath` 归一的词法 root 拼写，避免 Windows `Path.resolve()` 将短路径变成长路径、而 `os.readlink()` 保留短路径时误判链接关系；该清点仍拒绝 root ancestry reparse。实际 staging 复制另行 `resolve(strict=True)` 每个链接目标，并要求最终目标是源 root 内的 regular file，因此安全 containment 仍由真实目标解析路径负责。测试相应区分 lexical inventory 与 canonical Win32 ACL 路径；当前 `tests.test_windows_appcontainer` 局部通过（63 tests，11 skipped），完整套件/守护及双架构 CI 尚待执行。
- **下一步：**先跑完整本地回归并让 #154 验证路径修复；之后单独追踪 profile marker 的真实写入目标和原 runtime 的 native loader 依赖，不扩大 ACL、不回退宿主、不直接把 staged runtime 接入生产执行器。R2.3、R2 与 Windows 自动模式继续关闭。

### 2026-09-25 UTC CI #154：路径别名断言修复，两个 Windows 门槛独立保留

- [CI #154 x64](https://github.com/ayukyo/icode/actions/runs/36146195771/job/108107865622) 与 [ARM64](https://github.com/ayukyo/icode/actions/runs/36146195771/job/108107865591) 的完整 Windows 测试从 5 failures/1 error 降为 2 failures；此前短名/长名造成的重解析分类与 DACL 测试预期均通过。staged Python tempfile 创建/写入/删除、staging ACL 精确恢复、工作区/运行时/网络/子进程边界子项均通过回执。Windows R2.3 整体仍未通过。
- 两项保留失败分别是 profile `LOCALAPPDATA` marker `path_not_found` 与原宿主 Python 3.11.9 子进程退出 `0xC0000135`。CI #154 日志的原 runtime `copy /b` 对照中，System32 `whoami.exe` 可读，但 `python.exe`、`python311.dll`、`pathlib.py`、`encodings` 样本均为 `access_denied`；这只证明文件数据读取被拒，不等同 `SEC_IMAGE`/DLL loader 诊断。`0xC0000135` 是子进程退出状态（非 `CreateProcessW` 返回错误）；两条证据都提高了 runtime 可达性这一候选的优先级，但不证明唯一根因。
- **下一只读诊断（本提交待 #155 双架构验证）：**在能够运行的 disposable staged Python 子进程中查询 `TokenIsAppContainer`、`TokenAppContainerSid`、该 SID 的 `GetAppContainerFolderPath`，并读取 `GetEnvironmentStringsW` 中 `LOCALAPPDATA` 项数/值，再与同进程 `GetEnvironmentVariableW`、Python `os.environ` 及宿主 API 路径作比较。原始路径/SID 只保留在短寿命 staging 结果文件中，Actions notice 仅报告布尔值、固定路径关系类别和白名单错误/错误码。此探针不写 profile、不改环境、不扩展权限，不证明 profile marker 已修复；如果数据确认容器 API 与宿主一致但环境指向不存在的子路径，才另行设计最小因果 A/B。
- **竞品取舍：**FastRender 固定提交 `19bf1036105d4eeb8bf3330678b7cb11c1490bdc` 的 Windows sandbox 设计/实现从 AppContainer API 路径建立目录，并将 `TEMP/TMP` 收敛至该 profile 的 `Temp`；它没有实测解释本项目进程环境与 API 路径差异，且其许可证本次未审。采纳“按可信 API 路径建立临时目录、临时变量显式白名单”作为待评估思路；暂缓建目录、改 `TEMP/TMP` 或授权访问，先取回 #155 只读观测。[设计](https://github.com/wilsonzlin/fastrender/blob/19bf1036105d4eeb8bf3330678b7cb11c1490bdc/docs/windows_sandbox.md#L526-L540) · [固定源码](https://github.com/wilsonzlin/fastrender/blob/19bf1036105d4eeb8bf3330678b7cb11c1490bdc/src/sandbox/windows.rs)。没有复制代码或引入依赖。
- **下一 runtime loader 阶段仍未实施：**只读调研建议先记录实际 Windows runner 的 Python 版本/架构与 `python.exe`、`python311.dll` 哈希，再解析实际 PE 普通/延迟 imports；后续若仍需因果确认，使用独立原生 helper 在同一 AppContainer/Job 对原文件区分 `FILE_READ_DATA`、`SEC_IMAGE`、`LoadLibraryExW`，同调用宿主正向对照。不在已加载 staged Python 中再次 `LoadLibrary` 原树同名 DLL，以免命中已加载模块。当前未解析 PE imports、未验证 loader API、未触碰原 runtime ACL；这些都不能写成根因结论。
