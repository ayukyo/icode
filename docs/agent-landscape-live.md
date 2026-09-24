# 开源 AI Agent 持续对照与借鉴记录

- 最近观察：2026-09-24；下次全量复核：不晚于 2026-10-24
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
| Codex | `61e23bc`（R2 Git/网络复核） | [Linux 沙箱源码说明](https://github.com/openai/codex/blob/61e23bc6a1e9e5fc8ed6aefb3575c9d1fd077c22/codex-rs/linux-sandbox/README.md) · [内部 Git 查询](https://github.com/openai/codex/blob/61e23bc6a1e9e5fc8ed6aefb3575c9d1fd077c22/codex-rs/git-utils/src/info.rs) · [应用网络策略](https://github.com/openai/codex/blob/61e23bc6a1e9e5fc8ed6aefb3575c9d1fd077c22/codex-rs/app-server/README.md#application-network-policy) | `.git`/解析后 gitdir 只读；内部 Git 禁可选锁/hook 并限制 fsmonitor；应用、沙箱命令、Git/SSH 子进程的网络边界不同 |
| Gemini CLI | `87de0b6` | [沙箱文档](https://github.com/google-gemini/gemini-cli/blob/87de0b6369f0466da37d9b3c0c9b77374bb59992/docs/cli/sandbox.md) | 工具级隔离与单次扩权批准分开，自动模式不隐式批准 |
| Qwen Code | `d33cd4d` | [沙箱文档](https://github.com/QwenLM/qwen-code/blob/d33cd4ddcb5ce4c8f98df42210ca967707b3b9cd/docs/users/features/sandbox.md) | 未适配的 MCP/扩展/宿主 Git 预览不静默放行；启动失败不退回宿主执行 |
| OpenCode | `0f54984`（`dev`） | [V2 会话设计](https://github.com/anomalyco/opencode/blob/dev/specs/v2/session.md) | 仅参考持久化设计，采纳前检查落地代码 |
| Aider | `5dc9490` | [Repo Map 文档](https://github.com/Aider-AI/aider/blob/main/aider/website/docs/repomap.md) | 相关上下文裁剪可借鉴，不照搬索引实现 |
| Cline | `b51c27b` | [仓库 README](https://github.com/cline/cline/blob/main/README.md) | 人能理解的计划/执行和审批呈现 |
| OpenHands | `e069808` | [仓库 README](https://github.com/OpenHands/OpenHands/blob/main/README.md) | UI/运行服务分离可借鉴；容器依赖不符合 pip-only 目标 |
| LangGraph | `7daa3ab` | [持久执行文档](https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/durable-execution.mdx) | 恢复须处理副作用幂等；文档仓库另行核对 |

## 当前开发决策

| 阶段/需求 | 上游启发与证据 | ICODE 取舍 | 验收边界 |
|---|---|---|---|
| R2 跨平台隔离 | [Codex 授权/安全](https://learn.chatgpt.com/docs/agent-approvals-security)、[Gemini 沙箱](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/sandbox.md) | **采纳机制**：审批、OS 强制隔离、进程清理分开报告；不把应用层限制叫安全沙箱。macOS 按已确认的 Codex 式边界：文件/网络强制继承，同组清理，主动脱组后代不承诺零残留。 | Linux/macOS/Windows 各自的真实宿主测试和 policy critical 项；当前 R2 **未完成**，自动模式不得因此放行。 |
| R2 Linux 24.04 userns 兼容 | [Ubuntu 24.04 发行说明](https://documentation.ubuntu.com/release-notes/24.04/)、[Linux user namespace 手册](https://man7.org/linux/man-pages/man7/user_namespaces.7.html)、[PID namespace 手册](https://man7.org/linux/man-pages/man7/pid_namespaces.7.html) | **选择性采纳、Linux 清理子项已跨 runner 验证**：仅在 UID 映射权限拒绝且真实映射均空时保留无映射 PID namespace；活动能力归零、`no_new_privs`、Landlock/seccomp 必须全通过，不退回裸执行。 | [CI #85](https://github.com/ayukyo/icode/actions/runs/36001610973) 的 Ubuntu 22.04/24.04 x64/ARM64 原生与 wheel 作业全部通过；仍不证明进程数、Git/网络代理和完整 R2 合同。 |
| R2 macOS 单工单进程数 | [Apple `RLIMIT_NPROC`](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/setrlimit.2.html)、[launchd `NumberOfProcesses`](https://github.com/apple-oss-distributions/launchd/blob/main/man/launchd.plist.5)、[Codex Seatbelt 策略](https://github.com/openai/codex/blob/4083a68f88375bb0bc90a41b8c454d9e2d7c5281/codex-rs/sandboxing/src/seatbelt_base_policy.sbpl) | **暂缓、未找到等价机制**：前两者限制同 UID 总进程数，不能直接作为单工单配额；当前公开 Seatbelt 规则允许或拒绝派生，未证明数值上限。不能因主流 Agent 使用 Seatbelt 就推断其已满足 ICODE 的 `process_limit`。 | 用户批准的 macOS 例外仅限整树清理；若资源限制也失败则最多 8/10，自动模式仍阻断。需双架构负例证明真实单工单硬上限，或另行取得用户对合同变更的明确决定。 |
| R2 Git/网络 broker | [Codex Linux 沙箱](https://github.com/openai/codex/blob/61e23bc6a1e9e5fc8ed6aefb3575c9d1fd077c22/codex-rs/linux-sandbox/README.md)、[内部 Git 查询](https://github.com/openai/codex/blob/61e23bc6a1e9e5fc8ed6aefb3575c9d1fd077c22/codex-rs/git-utils/src/info.rs)、[应用网络策略](https://github.com/openai/codex/blob/61e23bc6a1e9e5fc8ed6aefb3575c9d1fd077c22/codex-rs/app-server/README.md#application-network-policy)、[Qwen 沙箱](https://github.com/QwenLM/qwen-code/blob/d33cd4ddcb5ce4c8f98df42210ca967707b3b9cd/docs/users/features/sandbox.md) | **采纳原则，实施待验收**：先做绑定可信会话的只读 Git 状态端口，元数据只读、固定参数、禁可选锁/hook/fsmonitor、无网络；宿主 Git/SSH 与模型 API 出网分离，未移植路径 fail-closed。参见[R2.4 门禁](./nbl/plans/2026-09-24-r2-git-broker-gate.md)。 | `git_broker_unavailable` 保留至恶意仓库扩展、原仓无写、路径注入等负例通过；raw IP/重定向/UDS/代理失效及凭据隔离属网络代理独立验收；三平台 wheel 实测前不升级能力。 |
| 后续会话恢复 | [LangGraph 持久执行](https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/durable-execution.mdx)、[OpenCode V2 设计](https://github.com/anomalyco/opencode/blob/dev/specs/v2/session.md) | **暂缓到恢复阶段**：先定义写前意图、幂等键和不确定副作用的人工确认，不承诺任意副作用自动重放。 | 断电/崩溃恢复与重复写副作用的故障注入测试。 |
| 后续上下文选择 | [Aider Repo Map](https://github.com/Aider-AI/aider/blob/main/aider/website/docs/repomap.md) | **采纳方向**：按任务检索相关结构，保留 ICODE-SKILL 必须输入与证据门禁；不复制其代码。 | 大仓库命中率、token 成本、必需上下文不遗漏。 |
| 后续办公工单 UI | [Cline](https://github.com/cline/cline/blob/main/README.md)、[OpenHands](https://github.com/OpenHands/OpenHands/blob/main/README.md) | **选择性采纳**：计划/执行切换、可读审批、工单状态与执行服务分层；不把 Langflow 式节点画布作为小白首页。 | 中英双语、普通白领可新建/查找工单并理解状态；会话/自动模式清晰标识安全边界。 |

本页记录的是设计依据和阶段候选，不等于交付证明；交付状态以[路线图](./roadmap.md)、测试和线上 CI 为准。
