# 开源 AI Agent 持续对照与借鉴记录

- 最近观察：2026-09-24；下次全量复核：不晚于 2026-10-24
- 注：观察日期统一按 UTC 记录；本轮为 2026-09-24 UTC（上海时间 2026-09-25）补充 R2.3 Windows 启动差分、R2.4 Git porcelain v2 解析器边界、临时网络代理架构研究与 NetworkLease 审批/HMAC authority；20 项观察名单最近全量复核为 2026-09-24。
- 用途：每项开发并行研究 1–3 个相关项目，按需吸收机制；不是一次性市场排名，也不是 ICODE 功能完成清单。
- 历史研究：[2026-09-23 快照](./agent-landscape.md)。热度、活跃度、许可证、实现状态会变化，旧结论须重新核对。

## 如何持续执行

每个开发任务由实现线和只读研究线同时开始。研究线先回答：真实问题是什么、ICODE/ICODE-SKILL 是否已有实现、借鉴会影响哪些调用链；然后从下表选最相关的 1–3 项，检查上游**实际源码或官方文档**。工具支持时交给独立子代理；不支持时在实现工作的独立时间片完成。调研不替代实现和测试，也不因 GitHub 限流阻塞安全工作；受限时标记“待复核”。

主阶段开始和结束时更新本页的“观察日期 / 上游提交或发布版本 / 证据 / 采纳决定 / ICODE 验收”，至少每 30 天复核观察名单。上游归档、许可证变化、安全问题、关键架构变化立即复核。只有实质代码或文档变动才触发设计重评；`pushed_at` 变化本身不是行为变化证据。变更历史由 Git 保留。

每周[只读到期检查](../.github/workflows/research-refresh.yml)根据本页日期和 20 项名单提醒复核；过期时定时任务失败，普通开发 CI 仅提示而不阻断紧急修复。此检查**不访问上游、也不证明人工已读源码**；完成复核后须由研究线更新来源版本、证据与采纳结论，再更新复核日期。

记录格式：`任务/阶段 | 上游项目与 commit/tag | 源码或官方文档链接 | 上游已实现/仅设计 | ICODE 现状 | 采纳/暂缓/不适配 + 原因 | 验收测试 | 观察日期`。不能把星数、博客转述、源码注释或设计草案当作已验证能力；不能因为相似而复制许可不明的代码。

## 20 个观察对象

这是按 ICODE 相关性选取的**观察样本**，并非经过统一口径排序的“热度前 20”。“深读”表示本次检查了指定官方资料并记录上游提交；“观察”只列候选，机制判断仍需开发任务中核对。

| 分组 | 项目 | 本次关注点 | 证据深度 |
|---|---|---|---|
| 编码 Agent | [Codex](https://github.com/openai/codex) | OS 沙箱与批准分离、跨平台边界 | 深读 |
| 编码 Agent | [Gemini CLI](https://github.com/google-gemini/gemini-cli) | 工具沙箱、按需授权 | 深读 |
| 编码 Agent | [Qwen Code](https://github.com/QwenLM/qwen-code) | 沙箱中未适配扩展的拒绝策略 | 深读 |
| 编码 Agent | [OpenCode](https://github.com/anomalyco/opencode) | 会话持久化与恢复 | 深读；V2 规范仅作设计材料 |
| 编码 Agent | [Aider](https://github.com/Aider-AI/aider) | 仓库映射与上下文选择 | 深读；活跃度待复核 |
| 编码 Agent | [Cline](https://github.com/cline/cline) | Plan/Act、可见审批、检查点 | 深读 |
| 编码 Agent | [Kilo Code](https://github.com/Kilo-Org/kilocode) | 工单/多工作区管理 | 观察 |
| 编码 Agent | [Continue](https://github.com/continuedev/continue) | IDE/CLI 入口、规则 | 观察 |
| 编码 Agent | [Goose](https://github.com/aaif-goose/goose) | 扩展与任务执行 | 观察 |
| 编码 Agent | [OpenHands](https://github.com/OpenHands/OpenHands) | UI 与 Agent 服务边界 | 深读 |
| 编码 Agent | [SWE-agent](https://github.com/SWE-agent/SWE-agent) | 工具接口与基准验证 | 观察 |
| 编码 Agent | [Pi](https://github.com/earendil-works/pi) | 精简执行内核 | 观察；沙箱不能默认假设 |
| 编码 Agent | [Open Interpreter](https://github.com/openinterpreter/openinterpreter) | 本地工具调用与用户确认 | 观察 |
| 编排/运行时 | [LangGraph](https://github.com/langchain-ai/langgraph) | 检查点、恢复、幂等副作用 | 深读 |
| 编排/运行时 | [CrewAI](https://github.com/crewAIInc/crewAI) | 多 Agent 流程 | 观察 |
| 编排/运行时 | [Microsoft Agent Framework](https://github.com/microsoft/agent-framework) | 状态与多 Agent 组合 | 观察 |
| 编排/运行时 | [smolagents](https://github.com/huggingface/smolagents) | 轻量工具循环 | 观察 |
| 编排/运行时 | [Pydantic AI](https://github.com/pydantic/pydantic-ai) | 类型化工具集合 | 观察 |
| 编排/运行时 | [Langflow](https://github.com/langflow-ai/langflow) | 可视化编排（只做反例/局部参考） | 观察 |
| 编排/运行时 | [Agno](https://github.com/agno-agi/agno) | 会话存储与运行时 | 观察 |

归档/许可观察池（不混入 20 项）：[Roo Code](https://github.com/RooCodeInc/Roo-Code)、[Flowise](https://github.com/FlowiseAI/Flowise)、[AutoGen](https://github.com/microsoft/autogen)、[AutoGPT](https://github.com/Significant-Gravitas/AutoGPT)。本次研究提示其维护或许可边界可能变化；需要用当时的仓库状态和具体子目录许可证重新确认，不能仅凭旧快照下结论。

## 本次深读的版本锚点

以下是 2026-09-24 调研时观察到的默认分支短提交号；不是长期锁定依赖。链接指向上游仓库或官方资料，下一轮必须重新核对提交、文档和实际代码是否一致。

| 项目 | 本次上游提交 | 核对入口 | 目前可借鉴的边界 |
|---|---|---|---|
| Codex | `3e27195`（2026-09-25 R2 网络复核） | [Linux 沙箱源码说明](https://github.com/openai/codex/blob/3e27195f2de00dc975b1db03440ade31b889d9b7/codex-rs/linux-sandbox/README.md) · [网络代理](https://github.com/openai/codex/blob/3e27195f2de00dc975b1db03440ade31b889d9b7/codex-rs/network-proxy/README.md) · [应用网络策略](https://github.com/openai/codex/blob/3e27195f2de00dc975b1db03440ade31b889d9b7/codex-rs/app-server/README.md#application-network-policy) | `.git`/解析后 gitdir 只读；代理模式以 netns/桥接与 seccomp 组合；应用与沙箱命令的网络边界不同。Git 查询细节仍引用下方已观察的 `61e23bc` 锚点 |
| Codex Git safeguards | `e4b6861` | [fsmonitor 防仓库配置选择任意 helper](https://github.com/openai/codex/blob/e4b68615f06621c43b365d66823ed01b8f8e8416/codex-rs/git-utils/src/fsmonitor.rs) · [core 平台元数据只读边界](https://github.com/openai/codex/blob/e4b68615f06621c43b365d66823ed01b8f8e8416/codex-rs/core/README.md) · [Git Doctor 文件系统诊断](https://github.com/openai/codex/blob/e4b68615f06621c43b365d66823ed01b8f8e8416/codex-rs/cli/src/doctor/git.rs) | 有 Git helper 抑制、元数据只读及不启动 Git 的诊断实现；未发现独立只读 Git 状态 broker，不能将这些局部实现等同完整 broker |
| Windows sandbox | Codex `3e9d1d2`；Qwen `330b928`；Gemini CLI `87de0b6` | [Microsoft AppContainer 启动](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer) · [隔离模型](https://learn.microsoft.com/en-us/windows/win32/secauthz/appcontainer-isolation) · [Codex restricted token](https://github.com/openai/codex/blob/3e9d1d29370ee7239585b9d1d576bea8263768ec/codex-rs/windows-sandbox-rs/src/token.rs) · [Qwen 沙箱文档](https://github.com/QwenLM/qwen-code/blob/330b92811c07483e30704190c7e135161120481b/docs/users/features/sandbox.md) · [Gemini Windows 沙箱](https://github.com/google-gemini/gemini-cli/blob/87de0b6369f0466da37d9b3c0c9b77374bb59992/docs/cli/sandbox.md) | Windows 机制深读；ICODE CI #91–#102 的 x64/ARM64 AppContainer 原生测试均失败；#92–#102 的 AppContainer `CreateProcessW` 返回 203。CI #96–#102 普通 Job 正向对照通过。#102 profile 创建、属性初始化与安全属性更新均成功；大小查询的 122/48 字节是 Win32 预期探测回执，不是根因。runner 根因未证实。 |
| Windows Python/AppContainer 运维风险 | Microsoft MXC `021b9b5`；Codex issue `#45871`（2026-09-16 用户报告，仍 open） | [MXC issue #572](https://github.com/microsoft/mxc/issues/572) · [MXC 当前 DACL 实现](https://github.com/microsoft/mxc/blob/021b9b58561cac98a3b34f10dbdf11b5393e776e/src/core/wxc_common/src/filesystem_dacl.rs) · [Codex issue #45871](https://github.com/openai/codex/issues/45871) | MXC issue 报告：低层 AppContainer+DACL 路径对 Python 安装树逐次递归加/撤 ACE 可达约 35 秒；Codex 用户报告 `canonicalize` 的 DOS 盘符解析在 AppContainer 中可能因 `\GLOBAL??` 拒绝。MXC 源码另含“修改前持久化恢复状态、按路径互斥、启动时回收死进程状态”的设计，可作为 ICODE 崩溃恢复候选借鉴。上述是风险线索，不能视为 ICODE 实测 |
| Gemini CLI | `87de0b6` | [沙箱文档](https://github.com/google-gemini/gemini-cli/blob/87de0b6369f0466da37d9b3c0c9b77374bb59992/docs/cli/sandbox.md) | 工具级隔离与单次扩权批准分开，自动模式不隐式批准 |
| Qwen Code | `11c87ee` | [沙箱文档](https://github.com/QwenLM/qwen-code/blob/11c87ee7c27dbc98efd0f67bb82f19b027f3e610/docs/users/features/sandbox.md) | 未适配的 MCP/扩展/宿主 Git 预览不静默放行；新 Linux 工具级模式尚不支持 `proxied` |
| OpenCode | `0f54984`（`dev`） | [V2 会话设计](https://github.com/anomalyco/opencode/blob/dev/specs/v2/session.md) | 仅参考持久化设计，采纳前检查落地代码 |
| Aider | `5dc9490` | [Repo Map 文档](https://github.com/Aider-AI/aider/blob/main/aider/website/docs/repomap.md) | 相关上下文裁剪可借鉴，不照搬索引实现 |
| Cline | `b51c27b` | [仓库 README](https://github.com/cline/cline/blob/main/README.md) | 人能理解的计划/执行和审批呈现 |
| OpenHands | `e069808` | [仓库 README](https://github.com/OpenHands/OpenHands/blob/main/README.md) | UI/运行服务分离可借鉴；容器依赖不符合 pip-only 目标 |
| LangGraph | `7daa3ab` | [持久执行文档](https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/durable-execution.mdx) | 恢复须处理副作用幂等；文档仓库另行核对 |

## 当前开发决策

| 阶段/需求 | 上游启发与证据 | ICODE 取舍 | 验收边界 |
|---|---|---|---|
| R2 跨平台隔离 | [Codex 授权/安全](https://learn.chatgpt.com/docs/agent-approvals-security)、[Gemini 沙箱](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/sandbox.md) | **采纳机制**：审批、OS 强制隔离、进程清理分开报告；不把应用层限制叫安全沙箱。macOS 按已确认的 Codex 式边界：文件/网络强制继承，同组清理，主动脱组后代不承诺零残留。 | Linux/macOS/Windows 各自的真实宿主测试和 policy critical 项；当前 R2 **未完成**，自动模式不得因此放行。 |
| R2 Windows 默认断网 | [Microsoft AppContainer](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer)、[Codex restricted token](https://github.com/openai/codex/blob/3e9d1d29370ee7239585b9d1d576bea8263768ec/codex-rs/windows-sandbox-rs/src/token.rs)、[Qwen Windows 前置](https://github.com/QwenLM/qwen-code/blob/330b92811c07483e30704190c7e135161120481b/docs/users/features/sandbox.md)、[Gemini Windows ACL](https://github.com/google-gemini/gemini-cli/blob/87de0b6369f0466da37d9b3c0c9b77374bb59992/docs/cli/sandbox.md)、[MXC DACL 性能报告](https://github.com/microsoft/mxc/issues/572)、[Codex AppContainer 路径报告](https://github.com/openai/codex/issues/45871) | **AppContainer 保持候选，不予接入**：当前实验按每次命令扫描并递归加/撤工作区 ACL，尚未证明大仓性能，也未证明 pip 安装的 Python 运行时/ICODE 本身能在容器内启动；MXC issue #572 报告相似路径的全树 ACE 传播可很慢。Codex issue #45871 是单一用户报告，提示 `Path.resolve` 类路径规范化风险；ICODE 源码多处实际使用 `Path.resolve`，必须用原生测试验证。 | CI #91–#102 的 Windows x64、ARM64 AppContainer 原生测试均失败；#92–#102 可见 `CreateProcessW` 错误码 203，#96–#102 普通 Job 对照双架构通过。#101 同一最小环境块正向对照仍失败于 AppContainer；runner 根因未证实，因此没有 Windows 文件/网络隔离验收结论。CI #102 的 `CreateAppContainerProfile`、属性列表初始化和 `UpdateProcThreadAttribute` 均成功，属性大小查询 122/48 字节符合 API 预期；其后仍需大目录基准、IPv4/IPv6/UDP/DNS 外联负例、Git/凭据边界、profile/ACL 多轮清理。WFP/代理继续独立门禁。 |
| R2 Linux 24.04 userns 兼容 | [Ubuntu 24.04 发行说明](https://documentation.ubuntu.com/release-notes/24.04/)、[Linux user namespace 手册](https://man7.org/linux/man-pages/man7/user_namespaces.7.html)、[PID namespace 手册](https://man7.org/linux/man-pages/man7/pid_namespaces.7.html) | **选择性采纳、Linux 清理子项已跨 runner 验证**：仅在 UID 映射权限拒绝且真实映射均空时保留无映射 PID namespace；活动能力归零、`no_new_privs`、Landlock/seccomp 必须全通过，不退回裸执行。 | [CI #85](https://github.com/ayukyo/icode/actions/runs/36001610973) 的 Ubuntu 22.04/24.04 x64/ARM64 原生与 wheel 作业全部通过；仍不证明进程数、Git/网络代理和完整 R2 合同。 |
| R2 macOS 单工单进程数 | [Apple `RLIMIT_NPROC`](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/setrlimit.2.html)、[launchd `NumberOfProcesses`](https://github.com/apple-oss-distributions/launchd/blob/main/man/launchd.plist.5)、[Codex Seatbelt 策略](https://github.com/openai/codex/blob/4083a68f88375bb0bc90a41b8c454d9e2d7c5281/codex-rs/sandboxing/src/seatbelt_base_policy.sbpl) | **暂缓、未找到等价机制**：前两者限制同 UID 总进程数，不能直接作为单工单配额；当前公开 Seatbelt 规则允许或拒绝派生，未证明数值上限。不能因主流 Agent 使用 Seatbelt 就推断其已满足 ICODE 的 `process_limit`。 | 用户批准的 macOS 例外仅限整树清理；若资源限制也失败则最多 8/10，自动模式仍阻断。需双架构负例证明真实单工单硬上限，或另行取得用户对合同变更的明确决定。 |
| R2 临时网络授权 | [Codex Linux 沙箱与桥接](https://github.com/openai/codex/blob/3e27195f2de00dc975b1db03440ade31b889d9b7/codex-rs/linux-sandbox/README.md) · [Codex 网络代理](https://github.com/openai/codex/blob/3e27195f2de00dc975b1db03440ade31b889d9b7/codex-rs/network-proxy/README.md) · [Gemini 严格代理 profile](https://github.com/google-gemini/gemini-cli/blob/87de0b6369f0466da37d9b3c0c9b77374bb59992/packages/cli/src/utils/sandbox-macos-strict-proxied.sb) · [Windows WFP ALE](https://learn.microsoft.com/en-us/windows/win32/fwp/application-layer-enforcement--ale-) | **选择性采纳，执行能力尚未实现**：`NetworkLeaseAuthority` 现要求通用 `Approver` 明示同意，用进程内随机 HMAC key 签发有时限租约并维护撤销代次；它不创建 socket、不控制 OS 路由，也没有接入命令执行。Linux 建议先做 netns + 可信桥接 HTTP(S) 最小切片；macOS 只许连接可信代理端口，Windows 需 AppContainer 通过后再评估 WFP；未完成 OS 级负例的平台继续 DENY。点时验签还不能解决连接建立与撤销的竞态。详见[网络门禁](./nbl/plans/2026-09-24-r2-network-proxy-gate.md)。 | raw IP/私网/DNS 重绑定/重定向/直连/UDP/UDS、代理失效与到期旧连接、会话串权、凭据隔离，以及三平台干净 wheel 负例未通过前保持 fail-closed。 |
| 后续会话恢复 | [LangGraph 持久执行](https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/durable-execution.mdx)、[OpenCode V2 设计](https://github.com/anomalyco/opencode/blob/dev/specs/v2/session.md) | **暂缓到恢复阶段**：先定义写前意图、幂等键和不确定副作用的人工确认，不承诺任意副作用自动重放。 | 断电/崩溃恢复与重复写副作用的故障注入测试。 |
| 后续上下文选择 | [Aider Repo Map](https://github.com/Aider-AI/aider/blob/main/aider/website/docs/repomap.md) | **采纳方向**：按任务检索相关结构，保留 ICODE-SKILL 必须输入与证据门禁；不复制其代码。 | 大仓库命中率、token 成本、必需上下文不遗漏。 |
| 后续办公工单 UI | [Cline](https://github.com/cline/cline/blob/main/README.md)、[OpenHands](https://github.com/OpenHands/OpenHands/blob/main/README.md) | **选择性采纳**：计划/执行切换、可读审批、工单状态与执行服务分层；不把 Langflow 式节点画布作为小白首页。 | 中英双语、普通白领可新建/查找工单并理解状态；会话/自动模式清晰标识安全边界。 |

### 2026-09-24 UTC R2.4 Git 状态代理复核

- Codex commit `e4b68615f06621c43b365d66823ed01b8f8e8416` 的 `fsmonitor.rs` 检查仓库 `core.fsmonitor` 配置并覆盖可能指定外部 helper 的值；core README 记录 macOS `.git`、解析后的 worktree `gitdir` 与 `.codex` 在 workspace-write 策略中保持只读。Git Doctor 另有从文件系统读取元数据、不启动 Git 的诊断实现。未找到 Codex 专门的只读 Git 状态 broker；这些都是可借鉴组件而不是端到端能力。
- Qwen Code v0.24.4 的 Linux 工具执行沙箱由系统/用户设置控制，项目设置不能降低策略，配置错误不回退宿主执行；它明确说明 `network: closed` 仍不隐藏宿主文件，也不隔离全部本机服务。官方文档禁用宿主 Git 预览等未移植工具；未发现独立 Git 状态 broker。
- ICODE 取舍：采纳可信会话绑定、操作系统级只读 Git 元数据/禁网、禁用外部 helper 与失败关闭；暂不开放模型命令入口。先做固定可执行文件与参数、NUL 结构化输出和恶意仓库负例，执行隔离必须可证明且覆盖链接 worktree 的 gitdir/common-dir；不能仅用 `GIT_OPTIONAL_LOCKS=0`、环境清理或正则参数过滤宣称安全。

### 2026-09-24 Windows AppContainer 追查补充

- ICODE CI #92 与 #93 在 Windows x64、ARM64 均于 CreateProcessW 返回错误码 203 后失败；#93 采用盘符环境项和 Windows `PATH` 修正仍未改变结果。CI #94 的两个 Windows 架构再以空自定义环境块启动 System32 `whoami.exe`，仍返回 203。[Convira issue #1](https://github.com/Convira/convira-sandbox/issues/1) 报告同一 GitHub hosted runner 现象，但作者没有确认根因，不能据此断言 runner 是原因。
- Microsoft 的 CreateProcessW 文档说明：调用方传入自定义环境块时，系统不会自动转交系统驱动器的当前目录信息；需显式带上例如 `=C:` 的特殊环境条目并按名称排序。ICODE 已按此修正，但双架构空环境块试验表明，当前错误不依赖环境块内具体变量。下一轮同时在普通 Job 中启动同一系统程序，确认空环境块本身有效，再判断失败是否 AppContainer/runner 特有。
- CI #95 的 x64 与 ARM64 AppContainer 探针仍在 `CreateProcessW` 返回 203。CI [#96](https://github.com/ayukyo/icode/actions/runs/36035908657) 普通 Job 空环境对照双架构成功，相同系统程序在 AppContainer 仍返回 203，故已排除“空环境普通 CreateProcess 本身不能启动”这一解释；仍不能判定 hosted runner 限制。[Microsoft AppContainer 启动文档](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer)要求通过 `STARTUPINFOEX.lpAttributeList` 携带安全能力以创建容器环境。下一步逐项隔离 AppContainer 创建参数，并修正无子进程时误报 `cleanup_failed` 的结果分类。

### 2026-09-25 Windows AppContainer 追查补充

- CI [#97](https://github.com/ayukyo/icode/actions/runs/36037204891) 双架构通知确认 AppContainer `CreateProcessW` 仍返回 203，现分类为 `native_api_failed, cleanup=True`；普通 Job 空环境 `whoami.exe` 对照保持成功。修复分类只能让失败事实准确，不改变隔离能力。
- 独立核对 io-harness 0.86.0 的 [AppContainer 环境块源码](https://docs.rs/io-harness/0.86.0/src/io_harness/sandbox/appcontainer.rs.html)：其实现跳过名称以 `=` 开头的 shell 盘符项，并说明其子解析器会把这类项当作块结束。**取舍：暂缓把它当修复**，只作为单变量差分诊断；ICODE #94 的空环境 AppContainer（无 `=X:` 项）也失败，因此它不能单独解释现有 203。原生差分仍待 CI #98 验证。

- CI [#98](https://github.com/ayukyo/icode/actions/runs/36038951938) 在 Windows x64 与 ARM64 继续返回 203，普通 Job 空环境对照通过。结论：省略 `=X:` 差异**不适配为修复**，ICODE 已恢复保留盘符伪变量。独立核对 `io-harness` 0.86.0 固定提交 `8c03ca273246937975bf63da8413c927ba264916` 的[属性列表分配源码](https://docs.rs/io-harness/0.86.0/src/io_harness/sandbox/appcontainer.rs.html#L1240-L1277)：上游用 `Vec<usize>` 保证指针对齐；Microsoft [InitializeProcThreadAttributeList 文档](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-initializeprocthreadattributelist)只要求分配足够空间、未明文规定对齐。因此当前把显式对齐作为低风险 A/B，不认为现有地址已被证明未对齐或是 203 根因。#98 的 macOS Intel `setsid` 负例测试未能在 1.5 秒内完成，而 ARM 通过；测试现在要求 broker 返回后释放脱组孙进程，再验证其存活 marker，待双架构重验。

### 2026-09-25 R2.4 Git porcelain v2 解析器研究

- 复核 Git 官方 [status/porcelain v2 文档](https://git-scm.com/docs/git-status)（页面标注最新手册 Git 2.55.0；2.54 至 2.55 无格式变更）：机器输出使用 NUL 分隔；路径按原始字节传输；重命名记录将新路径和旧路径分成相邻的两个 NUL 终止字段；`#` 扩展头允许未来扩展。基于这些约定新增严格字节解析器，未知扩展头忽略，未知/截断记录整体拒绝。
- 解析器用真实本机 `git status --porcelain=v2 -z` 输出和合成边界样例验证，包括空格/换行/非 UTF-8 路径、重命名旧路径、未合并、错误字段和流截断；实现本身不运行 Git，也不接触工作树或 `.git`。
- 独立审查发现并补齐合法 `.A`（intent-to-add）状态；模式字段收紧为 `000000`、`040000`、`100644`、`100755`、`120000`、`160000`，保留删除与 sparse-index 目录模式并拒绝其他八进制伪值；畸形 `#` 头 fail-closed。验证包含 Git 上游 [intent-to-add 回归](https://github.com/git/git/blob/master/t/t7064-wtstatus-pv2.sh#L1934-L1953)和有效模式/错误头测试。
- **取舍：仅采纳格式解析，不宣称 broker 或安全边界已完成。** 解析器不是权限控制；继续保留 `git_broker_unavailable`。可信会话绑定、helper 禁用、元数据只读、无网络、原仓零写与跨平台恶意仓库负例仍是接线前置门槛，详见[R2.4 Git 状态代理门禁](./nbl/plans/2026-09-24-r2-git-broker-gate.md)。

### 2026-09-25 R2.4 网络代理复核

- 对照 ICODE `f6d95ea`、Codex `3e27195f2de00dc975b1db03440ade31b889d9b7` 与 Gemini CLI `87de0b6369f0466da37d9b3c0c9b77374bb59992` 的源码/官方文档。Codex Linux 方案组合 netns、TCP/UDS/TCP 桥和 seccomp；Gemini macOS strict-proxied profile 只开放本地代理端口。两者是架构证据，不是 ICODE 已有能力。
- ICODE 的 `NetworkLeaseAuthority` 已有通用审批、当前进程随机 HMAC 签名与内存撤销代次，但仍没有代理进程、执行接线或 OS 路由；Linux seccomp 禁止新 socket，macOS 试验模式只接 DENY、旧 `network=True` 过宽，Windows Job 不限制网络且 AppContainer 尚未通过启动门槛。`HTTP_PROXY` 只影响合作式客户端。
- **取舍：**采纳“OS 强制工具只能连接可信代理 + 代理逐请求核对域名/期限”的分层边界；建议 Linux 先做精确域名 HTTP(S) 最小切片，其他平台保持 DENY 直到各自 OS 负例通过。DNS 最终解析 IP 必须由代理校验；DNS 重绑定、现存隧道到期/撤销、raw IP/UDP/loopback/私网与代理掉线均需负例。Git HTTPS 域名许可不等于只读 fetch，未解决凭据与协议授权前拒绝 push。点时签名验证与建连的 TOCTOU 也必须由代理方案解决。详见[网络代理门禁](./nbl/plans/2026-09-24-r2-network-proxy-gate.md)。
- 新增 authority 仍是本机授权合同，不开放联网、不保护同进程隔离，也不能作为代理连接许可；OS 路由/连接关闭/真实负例未完成前，执行路径必须保持 DENY。

### 2026-09-24 UTC Windows AppContainer CI #102

- [CI #102](https://github.com/ayukyo/icode/actions/runs/36051234628) 的普通 Job 同环境块正向对照成功；Windows x64/ARM64 AppContainer 仍于 `CreateProcessW` 返回 203。profile 创建 HRESULT 为 0，安全属性更新成功，flags 为 `0x00080404`；无子进程的失败仍准确报告 `cleanup=True`。
- 属性列表大小查询回执 `error=122, bytes=48` 符合 Microsoft 文档规定的首次空指针查询行为；初始化和安全属性更新随后成功，故不把此现象当作根因。来源：[Microsoft InitializeProcThreadAttributeList](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-initializeprocthreadattributelist)、[Microsoft AppContainer 启动示例](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer)。
- **下一项只读研究采纳为候选差分、尚未测试：**Microsoft AppContainer 样例和固定版本 io-harness 0.86.0 的 `CreateProcessW` 都将 `lpApplicationName` 设为 `NULL`，由可写命令行提供模块路径；ICODE 当前显式传绝对 `argv[0]`。计划只针对 `System32\\whoami.exe` A/B，保留环境、AppContainer、挂起创建与 Job 顺序，绝不对任意用户命令启用此变体。[io-harness 固定版本源码](https://docs.rs/io-harness/0.86.0/src/io_harness/sandbox/appcontainer.rs.html#L1439-L1458)。这只是代码差异，不是根因判断。

本页记录的是设计依据和阶段候选，不等于交付证明；交付状态以[路线图](./roadmap.md)、测试和线上 CI 为准。
