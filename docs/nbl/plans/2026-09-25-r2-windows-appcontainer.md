# R2.3 Windows AppContainer 与 Job Object 实验计划

- 日期：2026-09-25
- 状态：原生实验入口仍未通过验收；CI #91/#92 的 Windows x64 与 ARM64 均失败，#92 返回 CreateProcessW 错误码 203；不接生产自动工单
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
- CI [#92](https://github.com/ayukyo/icode/actions/runs/36030432822) 的 Windows x64 与 ARM64 分类 notice 均显示 CreateProcessW 错误码 203（ERROR_ENVVAR_NOT_FOUND）。[Convira issue #1](https://github.com/Convira/convira-sandbox/issues/1) 报告相同 GitHub hosted runner 现象，但作者未确诊并在该项目跳过原生集成测试；因此这只能说明故障可能受 CI 环境影响，不能证明 ICODE 在普通 Windows 上可用。[Microsoft CreateProcessW 文档](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw)说明自定义环境块不会自动带入系统驱动器当前目录，调用方必须显式传入类似 =C: 的特殊项。本次工作补了这些盘符项并加跨平台结构测试；需等待 CI #93 双架构实测才知道是否修复本故障。

竞品取舍：Codex `3e9d1d29370ee7239585b9d1d576bea8263768ec` 的 Windows 后端采用 restricted token，借鉴“降低令牌权限”，但不能据此等同凭据读取隔离；Qwen `330b92811c07483e30704190c7e135161120481b` 的 Windows 方案需 Docker/Podman，不符合 pip-only；Gemini `87de0b6369f0466da37d9b3c0c9b77374bb59992` 文档提到低完整性 ACL 处理，但不把 ACL 残留风险带入本方案。仅借鉴机制，不复制其实现。

## 当前实现与验收

Windows 实验用例覆盖目标：在 AppContainer 中启动 Python 并 resolve 工作路径；工作区已有嵌套文件可读、工作区可写、相邻目录 canary 不可读写、宿主 loopback 正向对照成立而 AppContainer 连接被拒、主进程正常退出与超时后的子进程回收、`process_limit=1` 阻止再启动子进程；ACL 恢复后，同一 Package SID 不能再写工作区。另有跨平台环境块测试验证盘符伪变量存在、排序和宿主变量不继承。现有 `WindowsJob` 原生测试另测正常退出、超时和宿主异常退出回收。CI #91/#92 的原生集成都失败，故这些只能称测试覆盖意图，不能称通过。

必须在 GitHub Actions 的 Windows x64 与 ARM64 runner 同时通过，并保持纯 wheel / Python 3.11 路径。当前 Linux 本机仅验证了非 Windows 拒绝分支、链接/硬链接防护、环境块结构、语法和既有非 Windows 回归；它**没有**执行任何 Win32 API。CI #91/#92 双架构均失败，AppContainer 不可用；#92 的分类 notice 已暴露 CreateProcessW 错误码 203，原始步骤日志仍需仓库权限。不能在确认 Python 运行时启动和路径规范化后接自动模式。

目前仍缺少真实 Windows 的 IPv4/IPv6、UDP、DNS、外网直连拒绝、受保护 Git 元数据与凭据 canary、主动脱离/显式换身份尝试、profile/ACL 多轮泄漏以及更完整的失败恢复测试。即便本轮 CI 通过，也只说明这个原生实验子项通过，Windows R2.3、R2.2 和完整 R2 均仍未验收；`policy_contract_ready` 必须继续为 false。

## 风险与成本

- ACL 变更需要完整扫描工作区，体积很大时耗时可能明显；MXC issue #572 报告兼容路径的全树 ACE 传播在 Python 安装目录上约需 35 秒/命令。ICODE 尚无大目录实测；扫描失败、任何 ACE 清理失败或 profile 删除失败都必须留下失败结果。当前实验只支持本地目录，不接受 UNC。
- 单次 Python 解释器/模块依赖可能位于工作区之外；不准因此放开整个用户目录或系统盘。必须证明最小运行时只读授权和 `Path.resolve()` 在 AppContainer 中可用，且衡量引入 ACL 的体积与启动耗时。
- 仅给目录 SID 授权并不能替代工作区构造合同：生产接入前要确认执行根不包含 `.git` 指针/元数据，并继续证明项目链接和重解析点无法访问外部路径。
- 企业策略可拒绝创建 AppContainer profile，API 失败必须阻止命令执行，不可退回普通 Job。
- 默认断网可不要求管理员；Windows 临时代理路径仍需管理员可管理的网络策略或等价可信服务，拒绝授权时保持断网。
