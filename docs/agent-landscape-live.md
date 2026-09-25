# 开源 AI Agent 持续对照与借鉴记录

- 最近观察：2026-09-24；下次全量复核：不晚于 2026-10-24
- 注：观察日期统一按 UTC 记录；本轮定向复核 R2.3 Windows AppContainer 与 Job 清理验收；20 项观察名单最近全量复核为 2026-09-24。
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
| Codex | `3e27195`（2026-09-24 UTC R2 网络复核） | [Linux 沙箱源码说明](https://github.com/openai/codex/blob/3e27195f2de00dc975b1db03440ade31b889d9b7/codex-rs/linux-sandbox/README.md) · [网络代理](https://github.com/openai/codex/blob/3e27195f2de00dc975b1db03440ade31b889d9b7/codex-rs/network-proxy/README.md) · [应用网络策略](https://github.com/openai/codex/blob/3e27195f2de00dc975b1db03440ade31b889d9b7/codex-rs/app-server/README.md#application-network-policy) | `.git`/解析后 gitdir 只读；代理模式以 netns/桥接与 seccomp 组合；应用与沙箱命令的网络边界不同。Git 查询细节仍引用下方已观察的 `61e23bc` 锚点 |
| Codex Git safeguards | `e4b6861` | [fsmonitor 防仓库配置选择任意 helper](https://github.com/openai/codex/blob/e4b68615f06621c43b365d66823ed01b8f8e8416/codex-rs/git-utils/src/fsmonitor.rs) · [core 平台元数据只读边界](https://github.com/openai/codex/blob/e4b68615f06621c43b365d66823ed01b8f8e8416/codex-rs/core/README.md) · [Git Doctor 文件系统诊断](https://github.com/openai/codex/blob/e4b68615f06621c43b365d66823ed01b8f8e8416/codex-rs/cli/src/doctor/git.rs) | 有 Git helper 抑制、元数据只读及不启动 Git 的诊断实现；未发现独立只读 Git 状态 broker，不能将这些局部实现等同完整 broker |
| Windows sandbox | Codex `3e9d1d2`；Qwen `330b928`；Gemini CLI `87de0b6` | [Microsoft AppContainer 启动](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer) · [隔离模型](https://learn.microsoft.com/en-us/windows/win32/secauthz/appcontainer-isolation) · [Codex restricted token](https://github.com/openai/codex/blob/3e9d1d29370ee7239585b9d1d576bea8263768ec/codex-rs/windows-sandbox-rs/src/token.rs) · [Qwen 沙箱文档](https://github.com/QwenLM/qwen-code/blob/330b92811c07483e30704190c7e135161120481b/docs/users/features/sandbox.md) · [Gemini Windows 沙箱](https://github.com/google-gemini/gemini-cli/blob/87de0b6369f0466da37d9b3c0c9b77374bb59992/docs/cli/sandbox.md) | Windows 机制深读；CI #91–#105 的 Windows AppContainer 启动探针多轮 x64/ARM64 返回 `CreateProcessW` 203；#105 固定 whoami A/B 显示需注入 profile `LOCALAPPDATA` 才能启动。常规路径接入后，#106–#111 的 Python 仍退出 `0xC0000135`；#110 profile marker 两架构均未写入。#111 确认诊断读取时序及 CMD 状态行编码有误；同步进程正对照成功，但因状态文件缺失未运行 `process_limit=1` 负例。普通 Job 双架构通过；#102 profile 创建、属性初始化与安全属性更新成功，大小查询 122/48 字节符合 Win32 预期。runner 根因未证实，组件级通过不代表 Windows R2.3 完成。 |
| Windows Python/AppContainer 运维风险 | Microsoft MXC `021b9b5`；Codex issue `#45871`（2026-09-16 用户报告，仍 open） | [MXC issue #572](https://github.com/microsoft/mxc/issues/572) · [MXC 当前 DACL 实现](https://github.com/microsoft/mxc/blob/021b9b58561cac98a3b34f10dbdf11b5393e776e/src/core/wxc_common/src/filesystem_dacl.rs) · [Codex issue #45871](https://github.com/openai/codex/issues/45871) | MXC issue 报告：低层 AppContainer+DACL 路径对 Python 安装树逐次递归加/撤 ACE 可达约 35 秒；Codex 用户报告 `canonicalize` 的 DOS 盘符解析在 AppContainer 中可能因 `\GLOBAL??` 拒绝。MXC 源码另含“修改前持久化恢复状态、按路径互斥、启动时回收死进程状态”的设计，可作为 ICODE 崩溃恢复候选借鉴。上述是风险线索，不能视为 ICODE 实测 |
| Gemini CLI | `87de0b6` | [沙箱文档](https://github.com/google-gemini/gemini-cli/blob/87de0b6369f0466da37d9b3c0c9b77374bb59992/docs/cli/sandbox.md) | 工具级隔离与单次扩权批准分开，自动模式不隐式批准 |
| Qwen Code | `11c87ee` | [沙箱文档](https://github.com/QwenLM/qwen-code/blob/11c87ee7c27dbc98efd0f67bb82f19b027f3e610/docs/users/features/sandbox.md) | 未适配的 MCP/扩展/宿主 Git 预览不静默放行；新 Linux 工具级模式尚不支持 `proxied` |
| OpenCode | `0f54984`（`dev`） | [V2 会话设计](https://github.com/anomalyco/opencode/blob/dev/specs/v2/session.md) | 仅参考持久化设计，采纳前检查落地代码 |
| Aider | `5dc9490` | [Repo Map 文档](https://github.com/Aider-AI/aider/blob/main/aider/website/docs/repomap.md) | 相关上下文裁剪可借鉴，不照搬索引实现 |
| Cline | `b51c27b` | [仓库 README](https://github.com/cline/cline/blob/main/README.md) | 人能理解的计划/执行和审批呈现 |
| OpenHands | `e069808` | [仓库 README](https://github.com/OpenHands/OpenHands/blob/main/README.md) | UI/运行服务分离可借鉴；容器依赖不符合 pip-only 目标 |
| LangGraph | `7daa3ab` | [持久执行文档](https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/durable-execution.mdx) | 恢复须处理副作用幂等；文档仓库另行核对 |

### 2026-09-24 UTC R2.3 Windows Job 与运行时复核

- **证据修正（ICODE #108）**：只读检查基线 `eabc4df` 的 `tests/test_windows_appcontainer.py`，后代延迟约 3 秒、清理后只等待 3.2 秒，无同 payload 无 Job 正向对照；公开 CI 注释只显示部分阶段，x64 没有 timeout notice，ARM64 notice 没有 timeout 状态/迟到哨兵断言，日志 API 返回 403。因此不再从 #108 公共日志推断具体失败断言或根因。
- **深读补充：**`io-harness` v0.86.0，commit `8c03ca273246937975bf63da8413c927ba264916`，许可证 Apache-2.0。[Job Object 测试](https://github.com/initorigin/io-harness/blob/8c03ca273246937975bf63da8413c927ba264916/tests/sandbox_job_object.rs)用三代进程、较长等待及同 payload 的无 Job 正向控制；进程上限测试也对比同脚本有/无上限。[AppContainer 实现](https://github.com/initorigin/io-harness/blob/8c03ca273246937975bf63da8413c927ba264916/src/sandbox/appcontainer.rs)将访问授权区分为目录遍历、只读执行和工作区完全访问。ICODE 只选择采纳验证结构与权限分级概念；不复制代码、不增加 Rust 依赖，运行时目录授权仍要另行审计。
- **兼容性边界：**OpenAI 官方 Windows 沙箱说明（2026-05-13）指出 AppContainer 适合预先知道访问集的窄应用，对开放式 shell/Python/Git/构建链路形状不合；其最终方案需要额外安装/管理员初始化、专用受限用户及防火墙。[官方设计](https://openai.com/index/building-codex-windows-sandbox/)。ICODE 当前要求 pip-only 和普通用户易用，因此不照搬提权部署；把实际 Python/toolchain 能运行作为 Windows R2.3 硬门禁。
- **ICODE 取舍：采纳**：正反向同载荷对照和充分的迟到哨兵观察窗；**暂缓**给宿主 Python 安装树扩展 ACL；逐文件读取仅记录错误类别。CI #110 的 workspace/network 和后代回收子项有通过 notice，但 Python 仍退出 `0xC0000135`；profile 写入与进程上限探针也未形成有效正反对照，须修正后再做双架构原生复验。
- **CI #110 校正：**[x64](https://github.com/ayukyo/icode/actions/runs/36071476528/job/107873192081) 与 [ARM64](https://github.com/ayukyo/icode/actions/runs/36071476528/job/107873192101) 均报告 profile 专属目录写入退出 1、marker 缺失；进程上限正对照 x64 未写 marker，ARM64 写出 marker 但父命令退出 1，旧异步启动/`timeout` 载荷不够确定。相同两架构的工作区写入、相邻目录写拒绝、loopback 拒绝和正常/超时后的代际清理有通过 notice。新一轮将记录 profile 目录是否预先存在、LOCALAPPDATA 是否进入 CMD 环境和脱敏错误类别；进程上限正负对照改为等待同一子脚本完成，并分别断言 marker 与启动状态。未经 Windows x64/ARM64 全部关键项通过，不开放自动模式。
- **CI #111 诊断校正：**[x64](https://github.com/ayukyo/icode/actions/runs/36073278352/job/107878821096) 与 [ARM64](https://github.com/ayukyo/icode/actions/runs/36073278352/job/107878821121) 同样失败。profile 诊断将状态文件留在临时目录中，却在该目录已删除后读取；环境和错误类别 notice 因此无效。进程正对照的父/子 marker 已出现，但裸 `echo %errorlevel%> file` 没有生成状态文件，测试在 cap=1 负例之前终止。本轮修正了读取生命周期与 `exit_code=` 状态编码；这些是测试 harness 缺陷，不是 Windows 沙箱通过/失败的新根因，修正仍需 x64/ARM64 CI 验证。

## 当前开发决策

| 阶段/需求 | 上游启发与证据 | ICODE 取舍 | 验收边界 |
|---|---|---|---|
| R2 跨平台隔离 | [Codex 授权/安全](https://learn.chatgpt.com/docs/agent-approvals-security)、[Gemini 沙箱](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/sandbox.md) | **采纳机制**：审批、OS 强制隔离、进程清理分开报告；不把应用层限制叫安全沙箱。macOS 按已确认的 Codex 式边界：文件/网络强制继承，同组清理，主动脱组后代不承诺零残留。 | Linux/macOS/Windows 各自的真实宿主测试和 policy critical 项；当前 R2 **未完成**，自动模式不得因此放行。 |
| R2 Windows 默认断网 | [Microsoft AppContainer](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer)、[Codex restricted token](https://github.com/openai/codex/blob/3e9d1d29370ee7239585b9d1d576bea8263768ec/codex-rs/windows-sandbox-rs/src/token.rs)、[Qwen Windows 前置](https://github.com/QwenLM/qwen-code/blob/330b92811c07483e30704190c7e135161120481b/docs/users/features/sandbox.md)、[Gemini Windows ACL](https://github.com/google-gemini/gemini-cli/blob/87de0b6369f0466da37d9b3c0c9b77374bb59992/docs/cli/sandbox.md)、[MXC DACL 性能报告](https://github.com/microsoft/mxc/issues/572)、[Codex AppContainer 路径报告](https://github.com/openai/codex/issues/45871) | **AppContainer 保持候选，不予接入**：当前实验按每次命令扫描并递归加/撤工作区 ACL，尚未证明大仓性能，也未证明 pip 安装的 Python 运行时/ICODE 本身能在容器内启动；MXC issue #572 报告相似路径的全树 ACE 传播可很慢。Codex issue #45871 是单一用户报告，提示 `Path.resolve` 类路径规范化风险；ICODE 源码多处实际使用 `Path.resolve`，必须用原生测试验证。 | CI #91–#105 的 Windows AppContainer 启动探针多轮返回 `CreateProcessW` 错误 203；#105 固定 whoami A/B 显示注入 profile `LOCALAPPDATA` 后可启动。常规路径接入后，#106–#111 的 Python 仍退出 `0xC0000135`。#110 两架构 profile marker 均未写入，进程上限正反对照不确定；#111 发现 profile 状态读取在临时目录删除后、退出码裸数字行被 CMD 当作重定向，相关字段无效；进程正对照已写 marker、负对照尚未执行。工作区/网络及后代清理子项有通过 notice，但不是 Windows 文件/网络隔离验收结论，也不能归因 runner。#102 的 `CreateAppContainerProfile`、属性列表初始化和 `UpdateProcThreadAttribute` 均成功，大小查询 122/48 字节符合 Win32 预期；仍需 Python 启动、大目录基准、IPv4/IPv6/UDP/DNS 外联负例、Git/凭据边界、profile/ACL 多轮清理。WFP/代理继续独立门禁。 |
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

### 2026-09-24 UTC Windows AppContainer 追查补充

- CI [#97](https://github.com/ayukyo/icode/actions/runs/36037204891) 双架构通知确认 AppContainer `CreateProcessW` 仍返回 203，现分类为 `native_api_failed, cleanup=True`；普通 Job 空环境 `whoami.exe` 对照保持成功。修复分类只能让失败事实准确，不改变隔离能力。
- 独立核对 io-harness 0.86.0 的 [AppContainer 环境块源码](https://docs.rs/io-harness/0.86.0/src/io_harness/sandbox/appcontainer.rs.html)：其实现跳过名称以 `=` 开头的 shell 盘符项，并说明其子解析器会把这类项当作块结束。**取舍：暂缓把它当修复**，只作为单变量差分诊断；ICODE #94 的空环境 AppContainer（无 `=X:` 项）也失败，因此它不能单独解释现有 203。原生差分仍待 CI #98 验证。

- CI [#98](https://github.com/ayukyo/icode/actions/runs/36038951938) 在 Windows x64 与 ARM64 继续返回 203，普通 Job 空环境对照通过。结论：省略 `=X:` 差异**不适配为修复**，ICODE 已恢复保留盘符伪变量。独立核对 `io-harness` 0.86.0 固定提交 `8c03ca273246937975bf63da8413c927ba264916` 的[属性列表分配源码](https://docs.rs/io-harness/0.86.0/src/io_harness/sandbox/appcontainer.rs.html#L1240-L1277)：上游用 `Vec<usize>` 保证指针对齐；Microsoft [InitializeProcThreadAttributeList 文档](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-initializeprocthreadattributelist)只要求分配足够空间、未明文规定对齐。因此当前把显式对齐作为低风险 A/B，不认为现有地址已被证明未对齐或是 203 根因。#98 的 macOS Intel `setsid` 负例测试未能在 1.5 秒内完成，而 ARM 通过；测试现在要求 broker 返回后释放脱组孙进程，再验证其存活 marker，待双架构重验。

### 2026-09-24 UTC R2.4 Git porcelain v2 解析器研究

- 复核 Git 官方 [status/porcelain v2 文档](https://git-scm.com/docs/git-status)（页面标注最新手册 Git 2.55.0；2.54 至 2.55 无格式变更）：机器输出使用 NUL 分隔；路径按原始字节传输；重命名记录将新路径和旧路径分成相邻的两个 NUL 终止字段；`#` 扩展头允许未来扩展。基于这些约定新增严格字节解析器，未知扩展头忽略，未知/截断记录整体拒绝。
- 解析器用真实本机 `git status --porcelain=v2 -z` 输出和合成边界样例验证，包括空格/换行/非 UTF-8 路径、重命名旧路径、未合并、错误字段和流截断；实现本身不运行 Git，也不接触工作树或 `.git`。
- 独立审查发现并补齐合法 `.A`（intent-to-add）状态；模式字段收紧为 `000000`、`040000`、`100644`、`100755`、`120000`、`160000`，保留删除与 sparse-index 目录模式并拒绝其他八进制伪值；畸形 `#` 头 fail-closed。验证包含 Git 上游 [intent-to-add 回归](https://github.com/git/git/blob/master/t/t7064-wtstatus-pv2.sh#L1934-L1953)和有效模式/错误头测试。
- **取舍：仅采纳格式解析，不宣称 broker 或安全边界已完成。** 解析器不是权限控制；继续保留 `git_broker_unavailable`。可信会话绑定、helper 禁用、元数据只读、无网络、原仓零写与跨平台恶意仓库负例仍是接线前置门槛，详见[R2.4 Git 状态代理门禁](./nbl/plans/2026-09-24-r2-git-broker-gate.md)。

### 2026-09-24 UTC R2.4 网络代理复核

- 对照 ICODE `f6d95ea`、Codex `3e27195f2de00dc975b1db03440ade31b889d9b7` 与 Gemini CLI `87de0b6369f0466da37d9b3c0c9b77374bb59992` 的源码/官方文档。Codex Linux 方案组合 netns、TCP/UDS/TCP 桥和 seccomp；Gemini macOS strict-proxied profile 只开放本地代理端口。两者是架构证据，不是 ICODE 已有能力。
- ICODE 的 `NetworkLeaseAuthority` 已有通用审批、当前进程随机 HMAC 签名与内存撤销代次，但仍没有代理进程、执行接线或 OS 路由；Linux seccomp 禁止新 socket，macOS 试验模式只接 DENY、旧 `network=True` 过宽，Windows Job 不限制网络且 AppContainer 尚未通过启动门槛。`HTTP_PROXY` 只影响合作式客户端。
- **取舍：**采纳“OS 强制工具只能连接可信代理 + 代理逐请求核对域名/期限”的分层边界；建议 Linux 先做精确域名 HTTP(S) 最小切片，其他平台保持 DENY 直到各自 OS 负例通过。DNS 最终解析 IP 必须由代理校验；DNS 重绑定、现存隧道到期/撤销、raw IP/UDP/loopback/私网与代理掉线均需负例。Git HTTPS 域名许可不等于只读 fetch，未解决凭据与协议授权前拒绝 push。点时签名验证与建连的 TOCTOU 也必须由代理方案解决。详见[网络代理门禁](./nbl/plans/2026-09-24-r2-network-proxy-gate.md)。
- 新增 authority 仍是本机授权合同，不开放联网、不保护同进程隔离，也不能作为代理连接许可；OS 路由/连接关闭/真实负例未完成前，执行路径必须保持 DENY。

### 2026-09-24 UTC Windows AppContainer CI #102

- [CI #102](https://github.com/ayukyo/icode/actions/runs/36051234628) 的普通 Job 同环境块正向对照成功；Windows x64/ARM64 AppContainer 仍于 `CreateProcessW` 返回 203。profile 创建 HRESULT 为 0，安全属性更新成功，flags 为 `0x00080404`；无子进程的失败仍准确报告 `cleanup=True`。
- 属性列表大小查询回执 `error=122, bytes=48` 符合 Microsoft 文档规定的首次空指针查询行为；初始化和安全属性更新随后成功，故不把此现象当作根因。来源：[Microsoft InitializeProcThreadAttributeList](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-initializeprocthreadattributelist)、[Microsoft AppContainer 启动示例](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer)。
- **受限 A/B 已完成，未改变结果：**CI [#104](https://github.com/ayukyo/icode/actions/runs/36056228159) 对固定、无参数 `SystemRoot\\System32\\whoami.exe` 分别显式传路径和传 `NULL`；两边均为 `CreateProcessW` 错误 203，清理状态为 true。原生测试观测到两次实际环境块相等，flags 仍为 `0x00080404`。因此此单一差异不能解释/修复当前失败；它也不足以判定 hosted runner 是根因。AppContainer 启动门槛仍未通过，自动模式继续关闭；下一项差分等待独立研究筛选后实施。[Microsoft CreateProcessW 参数说明](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw)。

### 2026-09-24 UTC Windows AppContainer profile 路径与清理边界

- 微软[启动指南](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer)为 profile 给出 `LOCALAPPDATA` 目录示例，并指向 `GetAppContainerFolderPath`；其[API 页面](https://learn.microsoft.com/en-us/windows/win32/api/userenv/nf-userenv-getappcontainerfolderpath)定义输出内存必须使用 `CoTaskMemFree`。这是核验某个显式环境变量是否影响 `CreateProcessW 203` 的依据，不代表 API 可以修复该错误。
- Chromium 固定观察点 [`19e92f6`](https://chromium.googlesource.com/chromium/src/%2B/19e92f6a6088ac35a31d74cbf4d64b32ef54957c/sandbox/win/src/app_container_profile_base.cc#178) 先把 SID 转为字符串再调用该 API。ICODE 采纳 API 所需的 SID 表示与内存所有权处理，不复制 Chromium 代码、不传宿主环境值。
- 同一个临时 SID 下执行 baseline 与 candidate，candidate 仅增加该 profile 的 `LOCALAPPDATA`；测试对比完整环境块除该键以外相等。CI [#105 x64](https://github.com/ayukyo/icode/actions/runs/36059960206/job/107836254760) 与 [#105 ARM64](https://github.com/ayukyo/icode/actions/runs/36059960206/job/107836255639) 两边均观测到 baseline 启动失败 203、candidate 成功且清理通过。该固定探针结果验证了受控变量差异，但不构成完整沙箱通过；同一轮完整容器用例仍失败，因为正常启动路径尚未附加变量。当前改动已将 API 返回的 profile 路径附加到所有常规 AppContainer 命令，并在路径查询失败时保持 fail-closed 与准确清理状态；新代码的 Windows x64/ARM64 原生复验待 CI。
- profile 目录是本次容器的独立临时数据区，不等同于仅工单目录可写。微软说明 profile 属于 per-user/per-app 存储，并警告句柄未关闭时删除可能不完整；ICODE 现按 API 约定重试删除并要求已知的 `LOCALAPPDATA` 目录消失，否则将清理标记失败。[CreateAppContainerProfile](https://learn.microsoft.com/en-us/windows/win32/api/userenv/nf-userenv-createappcontainerprofile) · [DeleteAppContainerProfile](https://learn.microsoft.com/en-us/windows/win32/api/userenv/nf-userenv-deleteappcontainerprofile)。CI 将另验证 Python 在 profile 中创建临时标记、容器退出后目录确实删除。
- **状态：常规路径及 profile 数据清理门禁已实现，等待 Windows x64/ARM64 CI；**不连接自动工单，安全沙箱与 R2 仍未验收。

### 2026-09-24 UTC AppContainer Python 运行时兼容性

- ICODE CI [#106 x64](https://github.com/ayukyo/icode/actions/runs/36063691161/job/107848355215) 与 [#106 ARM64](https://github.com/ayukyo/icode/actions/runs/36063691161/job/107848355043) 中，固定 whoami 的 profile `LOCALAPPDATA` A/B 成功；完整 Python 探针退出 `0xC0000135`，工作区/网络组合探针仍未达验收。环境变量回归断言捕获层错误已修正，待下一轮双架构复验。
- [Microsoft AppContainer 启动说明](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer)指出资源需由 Package/Capability SID 的 DACL 明确授权；权限仍与宿主用户权限取交集。因此，“宿主 Python 可读”不等于容器 SID 可读。Windows CI 当前只证明宿主解释器启动失败，不能推断具体 DLL、ACL 或搜索路径原因。
- 上游风险复核：[MXC issue #572](https://github.com/microsoft/mxc/issues/572) 的提交者报告，对含数万文件的 Python `Lib\site-packages` 做每次命令的整树继承 ACE 加/撤，在其环境约 35 秒；这是单个 issue 的测量，不是 ICODE 基准。[Codex issue #45871](https://github.com/openai/codex/issues/45871) 是仍 open 的单一 Windows 用户报告，称 AppContainer 中 `canonicalize()` 的 DOS 路径解析因 `\\GLOBAL??` 访问被拒，而普通文件读写仍成功。二者都是需本机复现实验的风险线索，不是已确认的普遍 Windows 行为。
- ICODE 取舍：**暂缓**递归授权完整 Python 安装树或放开用户目录/系统盘；先在双架构验证精准运行时依赖、`Path.resolve()`、只读 ACL 撤权/恢复与增量耗时。若无法同时满足最小权限、可靠清理和可接受启动开销，则 AppContainer 不进入 Windows 自动模式，继续比较隔离方案。
- ICODE CI [#107 x64](https://github.com/ayukyo/icode/actions/runs/36066941127) 的 profile A/B 通过，但任务内 CMD 批处理脚本没有到达任何 workspace marker；运行时拷贝探针依赖同一绝对脚本入口，故本轮不能判断其源文件 DACL。为继续区分路径解析与 AppContainer 文件 ACL，下一轮只将任务内部入口切换到 cwd-relative 路径并加入 inline write positive control；该结论仍是待验证，不是 Codex issue #45871 路径问题已复现。
- CI [#108](https://github.com/ayukyo/icode/actions/runs/36067827628) 在两架构验证 cwd-relative workspace 写/读及 loopback 拒绝，但子进程/超时仍有 x64/ARM64 差异。ARM64 的同一复制 harness 可读 System32 样本而未复制 Python 运行时样本；因尚缺每轮脚本启动哨兵，暂记为线索，不扩展 ACL。ICODE 仍采用 AppContainer 最小权限路线作候选，Codex 路径解析 issue 仍未在 ICODE 中复现。
- CI [#110](https://github.com/ayukyo/icode/actions/runs/36071476528) 的 x64/ARM64 工作区写入、相邻目录写拒绝、loopback 拒绝及正常/超时后代回收 notice 通过；Python 仍退出 `0xC0000135`。两边 profile marker 均未写入；上轮进程上限控制的 x64 正对照未写标记，ARM64 的正向 marker 与父进程退出码相矛盾，故均不记为进程上限通过。暂缓授权 Python 整树；先查明 profile 写入失败类别，并以同步等待同载荷正反控制重测进程限制。AppContainer 路线未完成，不把组件级通过写成 R2.3 通过。
- 下一轮在不依赖 Python 的 CMD 容器中单独验 profile marker 写入/删除，并将外部运行时复制失败压缩为错误类别；研究/实现都不建议用扩大用户目录 ACL 换启动成功。

### 2026-09-24 UTC Windows AppContainer CI #112

- CI [#112](https://github.com/ayukyo/icode/actions/runs/36074365589) 的 x64/ARM64 同载荷 `process_limit=2` 正对照均观察到子进程 marker 与状态 0；上限 1 的负对照均有父尝试、无子 marker，子进程启动状态为 1816，清理通过。将 Job 活动进程上限记为该边界下的组件通过，不外推为 AppContainer/R2.3 通过。
- 两架构 profile 探针均观察到 API 路径在宿主启动前存在、`LOCALAPPDATA` 已定义，但 AppContainer 内目录检查为假，写入错误类别为 `path_not_found`，删除前 marker 不存在。Python 仍退出 `0xC0000135`。尚不能区分环境值不匹配、路径语义或 token/访问边界问题。
- 微软[启动指南](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer)将 profile 定义为 AppContainer 可创建、读取和写入文件的位置，并说明可通过 `LOCALAPPDATA` 或 `GetAppContainerFolderPath` 访问；[CreateAppContainerProfile](https://learn.microsoft.com/en-us/windows/win32/api/userenv/nf-userenv-createappcontainerprofile)说明 profile 含每用户/每应用文件夹及注册表存储。[GetAppContainerFolderPath](https://learn.microsoft.com/en-us/windows/win32/api/userenv/nf-userenv-getappcontainerfolderpath)是路径查询接口，不承诺创建目录或改 ACL；官方文档也未列出具体 ACL mask。因此先核对容器实际 token SID、精确 `LOCALAPPDATA` 值及逐路径访问错误，暂缓手动 mkdir 或扩大 ACL。
- 当时增加的路径对照只向 Actions notice 发布 `profile_path_matches_api` 布尔值，不发布实际路径。**取舍：**保留 AppContainer 为候选后端，Windows 自动模式关闭；只有 Python、profile 私有写入/退出清理及跨架构全门禁通过后，才讨论接入执行器。

### 2026-09-25 UTC Windows AppContainer CI #113

- CI [#113](https://github.com/ayukyo/icode/actions/runs/36075689060) 的 x64 与 ARM64 `process_limit=2/1` 同载荷正反对照均通过组件断言；负例父进程尝试启动子进程、没有子进程 marker、启动状态为 1816，Job 清理成功。该结果只验收 Job 活动进程限制子项。
- 两架构 AppContainer 集成均失败：Python 退出 `0xC0000135`；profile notice 显示 `LOCALAPPDATA` 已定义、profile 路径在启动前存在、容器内目录不可见、写入错误 `path_not_found`、删除前 marker 缺失。CMD `set LOCALAPPDATA` 重定向文本与 API 路径比较为 false，但输出编码不固定，故这条解析结果暂不作路径不一致结论。
- 新诊断只在 Windows 测试中把 API 路径以临时 alias 同值注入环境块，由容器内 CMD 比较实际 `LOCALAPPDATA` 与 alias；Actions 只显示相等布尔值，不记录路径，也不改变正式产品环境或 ACL。等待 x64/ARM64 原生 CI 结果后再决定下一项最小修复。Windows 自动模式和 R2.3 仍未验收。

### 2026-09-25 UTC Windows AppContainer CI #114

- CI [#114](https://github.com/ayukyo/icode/actions/runs/36077520320) 的 x64 job [107891968933](https://github.com/ayukyo/icode/actions/runs/36077520320/job/107891968933) 与 ARM64 job [107891968868](https://github.com/ayukyo/icode/actions/runs/36077520320/job/107891968868) 均在 AppContainer 集成失败；`process_limit=2/1` 对照继续通过组件断言，Python 仍为 `0xC0000135`，profile 路径不可见、marker 缺失。
- 同块注入的 `ICODE_EXPECTED_LOCALAPPDATA` 与子进程 `LOCALAPPDATA` 的 CMD 比较两架构均为 false；这排除了单纯的控制台输出编码解释，但还未证明 alias 存在于 CMD 环境或路径值如何变化。不能由此确定是 environment block 未传递、AppContainer 对变量的处理还是 CMD 比较/解析行为。
- 下一轮增加 expected alias 的独立 `defined` 状态，并按 Microsoft [`cmd /u`](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/cmd) 选项将 `set LOCALAPPDATA` 重定向为 Unicode，再由宿主在内存中比较、只记录布尔值。普通产品环境和 ACL 不变；结果出来前不调整目录权限、不开放 Windows 自动模式。

### 2026-09-25 UTC Windows AppContainer CI #115

- CI [#115](https://github.com/ayukyo/icode/actions/runs/36078212333) 的 x64 job [107894086441](https://github.com/ayukyo/icode/actions/runs/36078212333/job/107894086441) 与 ARM64 job [107894086354](https://github.com/ayukyo/icode/actions/runs/36078212333/job/107894086354) 确认 expected alias 已定义、profile 不可见、marker 未写入，Python 仍退出 `0xC0000135`。采集到的 Unicode `set` 内容比较为 false，但当轮没有记录子命令退出码/输出是否非空，故尚不能把它当作实际路径不匹配。
- CI [#116](https://github.com/ayukyo/icode/actions/runs/36078821652) x64 notice 中 API 路径比较和宿主路径比较均为 false，宿主变量已定义；同样因 Unicode 子命令是否成功及输出文件是否非空未被单独报告，两个 false 仍可能是采集失败。下一轮补上退出码和非空状态，只有 `set` 成功且输出存在时才计算路径相等布尔值；不传入宿主路径、不输出任何路径。
- CI [#117](https://github.com/ayukyo/icode/actions/runs/36079222456) x64 job [107897174176](https://github.com/ayukyo/icode/actions/runs/36079222456/job/107897174176) 与 ARM64 job [107897174312](https://github.com/ayukyo/icode/actions/runs/36079222456/job/107897174312) 确认 Unicode `set` 子命令 exit 0、输出文件非空；expected alias 已定义，但解析值既不等于 API profile 路径也不等于宿主 `LOCALAPPDATA`。profile 目录仍不可见、marker 缺失、Python `0xC0000135`。新一轮在 profile 删除前分类宿主 `stat` 错误及 actual/API 的父子同级关系，并核对 exact 键唯一性和 samefile；Actions 只记类别，不记路径内容。
- CI [#118](https://github.com/ayukyo/icode/actions/runs/36079893851) 的 x64 job [107899342238](https://github.com/ayukyo/icode/actions/runs/36079893851/job/107899342238) 与 ARM64 job [107899342205](https://github.com/ayukyo/icode/actions/runs/36079893851/job/107899342205) 删除前采样一致：Unicode 输出有效、actual `LOCALAPPDATA` 键唯一，但 `Path.is_dir` 与 `samefile(API path)` 均为 false；旧取样没有区分 not-found 与 access-denied。profile/ Python 门槛仍失败。下一轮在删除前只记录宿主 `stat` 类别与 actual/API 父子同级关系，以区分目录缺失、访问拒绝及路径重定位，不披露原始路径。
- CI [#119](https://github.com/ayukyo/icode/actions/runs/36080610266) 的 Windows x64/ARM64 均失败：actual `LOCALAPPDATA` 在 API profile 路径之下、宿主 `stat=not_found`、与 API 目录不是同一对象，Python 仍退出 `0xC0000135`。微软启动指南的默认环境示例把 `TEMP/TMP` 放在 `AC\\Temp`，但没有界定自定义环境块下 `LOCALAPPDATA` 是否会被重写。下一轮只比较脱敏布尔值“actual 等于 API `Temp` 子目录”，并压短 Actions notice 以保留字段；不改 ACL 或记录路径。

### 2026-09-25 UTC R2.3 `LOCALAPPDATA` 子目录分类复核

- CI [#120 x64](https://github.com/ayukyo/icode/actions/runs/36081977910/job/107905707747) 与 [ARM64](https://github.com/ayukyo/icode/actions/runs/36081977910/job/107905707999) 的实际环境值均不等于显式传入的 API 路径 alias，位于 API profile 路径下方但不是 `Temp`，宿主 `stat=not_found`；Python 均以 `0xC0000135` 退出。CI 只证明观测差异，不证明它与 Python 加载失败有因果关系。
- 微软 [AppContainer 启动指南](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer)展示默认环境 `LOCALAPPDATA=...\\AC` 与 `TEMP/TMP=...\\AC\\Temp`，没有说明自定义环境块里 `LOCALAPPDATA` 是否被系统重写；[GetAppContainerFolderPath](https://learn.microsoft.com/en-us/windows/win32/api/userenv/nf-userenv-getappcontainerfolderpath)及[CreateAppContainerProfile](https://learn.microsoft.com/en-us/windows/win32/api/userenv/nf-userenv-createappcontainerprofile)也没有规定 `AC\\Local` / `AC\\LocalState` 等具体子目录。不得套用 MSIX 包应用目录约定或自行创建目录。
- FastRender 固定观察提交 [`19bf1036105d4eeb8bf3330678b7cb11c1490bdc`](https://github.com/wilsonzlin/fastrender/blob/19bf1036105d4eeb8bf3330678b7cb11c1490bdc/src/sandbox/windows.rs)显式构造环境块并设置 `TEMP/TMP`，没有 `LOCALAPPDATA` 重写实现或原生实测。ICODE **采纳**显式、最小环境块及任务临时目录路由（现有实现）；**暂缓**照搬其 Rust 代码或推断其能解释当前差异。
- ICODE CI [#121 x64](https://github.com/ayukyo/icode/actions/runs/36083440360/job/107910090970) 与 [ARM64](https://github.com/ayukyo/icode/actions/runs/36083440360/job/107910091117) 将路径分类为 API profile 下的多层子路径，Python 仍退出 `0xC0000135`、profile marker 缺失。工作区、网络拒绝、Job 进程数和后代清理只有组件级通过，不等于完整 Windows 验收。
- 首轮 `api_child_nested` 仍隐藏了首层类别。下一探针仅细分到白名单首层（`Temp`、`Local`、`LocalState`、其他），保留 alias 布尔对照，不输出路径。已本地 RED/GREEN 验证，等待 CI #122 双架构回执；在查明前不创建目录、不改 ACL、不开放自动模式。

### 2026-09-25 UTC R2.3 CI #122 与 Harn Windows 沙箱源码

- CI [#122 x64](https://github.com/ayukyo/icode/actions/runs/36083962877/job/107911650724) 与 [ARM64](https://github.com/ayukyo/icode/actions/runs/36083962877/job/107911650705) 均将 actual `LOCALAPPDATA` 归为 `api_child_other_nested`；Python `0xC0000135`、profile marker 缺失。路径值与 Python 加载失败之间仍无因果证明；下一轮先让运行时直接读取探针逐项返回脱敏结果，不继续盲猜路径段。
- 补充技术参照而非固定 20 项热门观察名单：Harn v0.10.142 固定提交 [`8f9587982efa0d515230ee04ae4559fc60f1f394`](https://github.com/burin-labs/harn/blob/8f9587982efa0d515230ee04ae4559fc60f1f394/crates/harn-vm/src/stdlib/sandbox/windows.rs)的 Windows 实现创建 profile `Temp` 并设置 `LOCALAPPDATA`/`TEMP`/`TMP`；还用进程沙箱 roots/presets 为部分工具链目录做只读 ACL。我们检查到的 env-block 单测只校验序列化，不是 Windows 原生 AppContainer 运行 Python 的证据；项目自述 pre-1.0，故不把文档方案视作已验证解法。
- **采纳方向：**进程所需只读 runtime roots 与 Agent 文件工具的授权范围分离；ICODE 当前只有 Linux Landlock helper 有独立 Python runtime roots，Windows AppContainer runner 尚未接入，需在确认依赖边界后设计。**暂缓：**默认递归授权整套 home/toolchain/package-manager 配置：会扩大读取面，并可能暴露 `.netrc`、`.pypirc` 凭据；递归 ACL 的耗时与回滚也需单独验收。不复制 Rust 代码。
- 现有直读探针把所有 Actions notice 延迟到候选文件循环结束，早期断言会丢失已观测的首项结果。已改为每项完成后先发送固定字段 notice（标签、尺寸、结果类别、状态），再断言；不含实际路径、原始错误文本或文件内容，等待 CI #123 双架构验证。

### 2026-09-25 UTC R2.3 CI #123：直读候选清单观测缺口

- CI [#123 x64](https://github.com/ayukyo/icode/actions/runs/36085435118/job/107916150553) 与 [ARM64](https://github.com/ayukyo/icode/actions/runs/36085435118/job/107916150560) 仍在 Python AppContainer 探针失败（`0xC0000135`）；对应组件 notice 仍显示 profile marker 缺失。R2.1 三平台、Python 3.11/3.12 和 R2.2 Linux/macOS 原生矩阵通过，但整轮 CI 失败。
- #123 没有产生 Python runtime direct-read 的逐文件 notice。代码复核发现样本数量断言 `len(runtime_files) >= 4` 位于全部 notice 之前，因此不能判断是候选文件不足、运行时异常还是其它原因。下一轮会先只输出固定候选标签与可用数量，再保留原四样本门槛并发出逐文件脱敏回执；不降低验收要求、不输出源路径。
- Windows SDK `ntstatus.h` 将 `0xC0000135` 定义为 `STATUS_DLL_NOT_FOUND`，这是 loader 依赖缺失的直接线索，但不定位具体 DLL 或 ACL 根因；微软[动态链接库搜索顺序](https://learn.microsoft.com/en-us/windows/win32/dlls/dynamic-link-library-search-order)说明 unpackaged 应用搜索多个目录，`PATH` 位于搜索序列末尾。ICODE 当前最小环境块的 `PATH` 只有解释器父目录和 System32，Python 可执行文件/动态库所在安装树尚未得到独立访问验证。
- CPython [3.11 Windows 模块查找文档](https://docs.python.org/3.11/using/windows.html#finding-modules)及[3.12 对应文档](https://docs.python.org/3.12/using/windows.html#finding-modules)说明 `._pth`、`PYTHONHOME`、`pyvenv.cfg`、`Lib\\os.py`/`pythonXY.zip` 等影响模块搜索；这属于解释器进入后的模块/stdlib 路径，不能直接解释 Windows loader 的 `STATUS_DLL_NOT_FOUND`。Windows AppContainer [隔离文档](https://learn.microsoft.com/en-us/windows/win32/secauthz/appcontainer-isolation)说明文件能力依 ACL 授予，不能为排查而扩大成用户目录访问。
- Harn v0.10.142 固定提交还会创建 profile `Temp` 目录（[源码行 395–420](https://github.com/burin-labs/harn/blob/8f9587982efa0d515230ee04ae4559fc60f1f394/crates/harn-vm/src/stdlib/sandbox/windows.rs#L395-L420)）；这只能作为隔离的目录准备 A/B 候选，不解释 `0xC0000135`，其环境块单测也不是原生 Python/AppContainer 验收。当前**优先**拿到直读 inventory 和具体 loader 依赖证据；**暂缓**`._pth`/`PYTHONHOME` 修改与 profile ACL 扩权，避免把模块搜索、临时目录和 DLL loader 混为同一根因。

### 2026-09-25 UTC R2.3 CI #124：隔离直读步骤

- CI [#124 x64](https://github.com/ayukyo/icode/actions/runs/36086599173/job/107919764633) 与 [ARM64](https://github.com/ayukyo/icode/actions/runs/36086599173/job/107919764585) 仍因 AppContainer Python `0xC0000135` 失败，profile marker 缺失；R2.1 三平台、Python 3.11/3.12 通用任务和 R2.2 Linux/macOS 原生子项通过。
- 将 inventory notice 移到四样本断言之前后，#124 的综合作业 annotations 仍未出现 inventory 或逐文件 notice；该公开摘要不能证明测试未运行，也不能说明异常位置。下一轮在完整 Windows 验收步骤之前单独运行直读单测（其失败 `continue-on-error`，完整套件仍会重复并保留正式门禁），以便独立取得 traceback 和路径脱敏回执。
- 对照 CI #124 的公开结果仍未证明 profile 子目录、DLL 搜索路径或 ACL 中哪一项导致退出；继续按固定标签输出，保持不继承宿主完整 `PATH`、不扩大 ACL、不开放自动模式。

### 2026-09-25 UTC R2.3 CI #125：Python runtime 最小只读授权候选

- [CI #125 x64](https://github.com/ayukyo/icode/actions/runs/36087232240/job/107921726078) 与 [ARM64](https://github.com/ayukyo/icode/actions/runs/36087232240/job/107921726100) 的独立 AppContainer 直读探针都执行完成。inventory 为 6 个候选、5 个可用；两架构的 System32 控制可读，Python EXE、Python 共享库、`pathlib.py` 和 `encodings/__init__.py` 均报告 `access_denied`。完整 Python 仍以 `0xC0000135` 退出。逐项通知不含源路径，并显示清理成功。
- **采纳进入下一步验证：**把子进程 Python runtime 的只读执行依赖，与 Agent 文件工具可读范围分开设计；先只在临时 GitHub Windows runner 上验证经过边界校验的 runtime roots，不接入生产执行器。
- **暂缓：**直接授权整个 home、PATH 中所有目录或完整工具链 preset。CI 直读拒绝是文件读取证据，不是 DLL loader 完整依赖因果证明；尚无 DACL A/B 结果。Harn v0.10.142 的 roots/preset ACL 仍仅作架构参考，其测试没有提供该 Windows 原生 Python/AppContainer 证据。
- 验收前置：拒绝 UNC、卷根、用户凭据目录、与写入工作区重叠、reparse point/hardlink 或 DACL 无法精确快照的根；任何授权/恢复失败均中止命令并保留 fail-closed。即使逐文件读取转为成功，也不能单独宣称 `0xC0000135` 已修复或 Windows R2.3 已通过。

### 2026-09-25 UTC R2.3 CI-only runtime ACL 差分实现

- 诊断开关仅接受 GitHub-hosted Windows runner 上的当前 `sys.executable`，作用范围为 `sys.prefix` / `sys.base_prefix`，拒绝 UNC、卷根、系统目录、用户目录覆盖、工作区重叠、重解析点、硬链接、null/protected/defaulted DACL；扫描最多 100,000 个对象且不超过 30 秒。生产 runner、自动模式和 `policy_contract_ready` 均未接入。
- 变更前逐对象保存 DACL bytes、descriptor control/revision、DACL present/defaulted 状态和文件身份；仅给当次随机 Package SID 增加可继承 read/execute ACE，不授写。恢复后复扫整树，逐对象精确比较并检查 SID 残留；不能恢复/验证即 `cleanup_failed`。这仍是临时 CI 实验，不承诺与并发安装器事务隔离。
- 微软说明可继承 ACE 会传播到子对象，且安全描述符更新存在自动传播规则（[ACE inheritance](https://learn.microsoft.com/en-us/windows/win32/secauthz/ace-inheritance-rules)、[automatic propagation](https://learn.microsoft.com/en-us/windows/win32/secauthz/automatic-propagation-of-inheritable-aces)、[`SetNamedSecurityInfoW` remarks](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-setnamedsecurityinfow#remarks)）。所以恢复根 DACL 后仍必须验证每个已有对象的原始状态；SID 消失不等于已精确恢复。下一步由双架构 CI 决定这条方案能否继续，任何一架构失败或精确恢复不通过即停止 ACL 路线，不开放 Windows 自动模式。

### 2026-09-25 UTC R2.3 CI #127：runtime ACL 差分被安全预检挡住

- [windows-latest](https://github.com/ayukyo/icode/actions/runs/36090932965/job/107933023862) 与 [windows-11-arm](https://github.com/ayukyo/icode/actions/runs/36090932965/job/107933023845) 的独立差分步骤都在授权前返回 `runtime tree contains unsafe filesystem entries`，候选未启动、清理回执为真；因此没有对 runner Python 安装树进行 ACL 修改。完整 AppContainer Python 仍为 `0xC0000135`。
- 该回执无法区分运行时树中是重解析点、硬链接、特殊文件还是枚举错误。**暂缓**任何扩大扫描范围或跳过不安全项；只增加固定、脱敏的预检拒绝类别回执，再由 CI 确定准确类别。若无法在保持拒绝边界的前提下完成快照，本 ACL 方案不适配，不授权。

### 2026-09-25 UTC R2.3 CI #128：预检确认是 reparse point

- [x64](https://github.com/ayukyo/icode/actions/runs/36091394407/job/107934399982) 与 [ARM64](https://github.com/ayukyo/icode/actions/runs/36091394407/job/107934399966) 的差分都在快照阶段因 `FILE_ATTRIBUTE_REPARSE_POINT` 拒绝；候选未运行、runtime ACL 未改。当前回执仍不区分 symbolic link、junction/mount point 或其它 reparse tag。
- Microsoft 文档列出多种 reparse tag，且路径操作对 symbolic link 的行为会随 API/`FILE_FLAG_OPEN_REPARSE_POINT` 不同；`SetNamedSecurityInfoW` 会传播 ACE 到现存子对象，但没有定义 junction 边界；`GetNamedSecurityInfoW` 文档也未承诺 name-based API 对链接本体/目标的选择语义。故**暂缓**跟随或跳过 reparse point。实现仅将 `st_reparse_tag` 映射为 `symbolic_link` / `mount_point` / `other_reparse` 等固定类别，路径、目标与原始 tag 值均不进入回执；#128 尚未得到新分类 CI 结果，授权边界不变。未来若评估放行，先在一次性临时树用 handle-based API 分别验证链接本体、目标、后代 DACL 与精确恢复；未知 tag、跨卷/外部目标及并发可替换对象继续拒绝。[Python `os.lstat` / `st_reparse_tag`](https://docs.python.org/3.11/library/os.html#os.stat_result)、[Microsoft reparse tag 说明](https://learn.microsoft.com/en-us/windows/win32/fileio/reparse-point-tags)、[reparse point operations](https://learn.microsoft.com/en-us/windows/win32/fileio/reparse-points-and-file-operations)、[symbolic-link API effects](https://learn.microsoft.com/en-us/windows/win32/fileio/symbolic-link-effects-on-file-systems-functions)、[`GetNamedSecurityInfoW`](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-getnamedsecurityinfow)、[`SetNamedSecurityInfoW`](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-setnamedsecurityinfow)、[ACE 自动传播](https://learn.microsoft.com/en-us/windows/win32/secauthz/automatic-propagation-of-inheritable-aces)

### 2026-09-25 UTC R2.3 CI #129：两架构均识别为 symbolic link

- [windows-latest x64](https://github.com/ayukyo/icode/actions/runs/36092603966/job/107937999811) 与 [windows-11-arm](https://github.com/ayukyo/icode/actions/runs/36092603966/job/107937999747) 的 runtime ACL 差分均在任何授权前以 `symbolic_link` 拒绝；候选未启动、清理为真、未改变 Python runtime DACL。原始 AppContainer Python 仍 `0xC0000135`，Python EXE、共享库与标准库文件的直接读取探针仍为 `access_denied`。此结论不识别具体链接名称、目标是否位于 runtime 根内，也不证明 ACL 是 `0xC0000135` 的唯一原因。
- **暂缓**通用 symbolic-link 放行。下一轮先由 CI 清点链接数量，并仅用 `readlink` 文本做不跟随的词法关系分类（根内/根外/未知），绝不回执链接名、原始 target 或路径；根外与未知均保留拒绝，根内也只够决定是否开展下一项隔离实验。只有继续推进时，才在 CI 自建临时树观察实际安全 API 的 link/target/后代差异并验证状态恢复；不得触碰 hosted Python/toolcache。即便临时实验通过，也需另行证明 runner 上实际 runtime link 的目标身份并复验完整 Python 启动、只读、工作区、断网和恢复门禁。

本页记录的是设计依据和阶段候选，不等于交付证明；交付状态以[路线图](./roadmap.md)、测试和线上 CI 为准。

### 2026-09-25 UTC R2.3 临时路径与环境块复核

微软 [GetTempPath2W](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-gettemppath2w) 按 `TMP`→`TEMP`→`USERPROFILE`→Windows 目录选临时路径且不验证目录存在/可达；ICODE 已将前三项绑定工单工作区。`io-harness 0.86.0` [固定源码](https://docs.rs/io-harness/0.86.0/src/io_harness/sandbox/appcontainer.rs.html#1045-1114)显式构建环境块并将临时目录指向授权的 task temp。**采纳**显式、最小化环境块的调用方机制（ICODE 已有），**暂缓**其 Rust 实现；此观察不构成 `LOCALAPPDATA` 子目录或 Python 加载失败的根因证据。

### 2026-09-25 UTC R2.3 staging 与 R2.4 Git 状态 broker 刷新

- [CI #131 x64](https://github.com/ayukyo/icode/actions/runs/36093962446/job/107942126150) / [ARM64](https://github.com/ayukyo/icode/actions/runs/36093962446/job/107942126118)：Python runtime 6,721 项中有 1 个 symbolic link，目标文本词法归为根内；runtime ACL 仍在预检阶段 fail-closed，未更改源 DACL，Python `0xC0000135` 未解。下一项是 disposable staging 原生探针，不放行真实 toolcache link。
- 默认 Windows CI 已停止运行“直接对 host runtime 改 DACL”的旧 A/B（#131 两架构均在授权前 fail-closed）；测试现在需显式 `ICODE_DIAGNOSTIC_RUNTIME_ACL=true`。持续 CI 的 ACL 实验只作用于 disposable temp staging 副本。
- Python 官方资料复核：3.13.15 为当前发布线的 Windows embeddable ZIP 提供 x64 11,010,501 B、ARM64 10,403,665 B；embeddable 包面向嵌入应用，不含 pip/Tk/文档。3.11.16、3.12.14 属仅源码安全更新，embed 旧二进制会冻结安全补丁；改用 3.13 需项目兼容性验证。**暂缓**把二进制 runtime 固定进 ICODE wheel；先证明现有 host runtime 在临时只读 staging 中可完整启动。[3.13.15 官方目录](https://www.python.org/ftp/python/3.13.15/) · [embeddable 文档](https://docs.python.org/3.12/using/windows.html#the-embeddable-package) · [3.11.16](https://www.python.org/downloads/release/python-31116/) · [3.12.14](https://www.python.org/downloads/release/python-31214/)。
- Git broker 当前无可调用实现；本机只存在 porcelain v2 parser，direct Git 对分层工单仍 fail-closed。固定上游源码复核：Codex `aa380897f67b91e1a47d530d7286d497b6726d3f` 使用 OS 只读保护 `.git`/gitdir 并约束内部 status 参数；Qwen Code `2686cad25fe8ffc24f582d8cb50f49743a884e3b` 明确不在 sandbox 启动失败时退回 host；Gemini CLI `bedef96ef42905bd84a86dbec021c706168e7e2f` 解析 worktree/common gitdir，但不照搬按项目权限扩写 Git 管理目录。**采纳**边界组合与 fail-closed，Linux status 是可独立实施的下一子切片，尚未开放工具入口；详情见 [Git broker 门禁](./nbl/plans/2026-09-24-r2-git-broker-gate.md)。
