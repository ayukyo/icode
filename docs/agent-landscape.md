# AI Agent 主流格局调研与我们的定位

> 历史快照（2026-09-23），不代表当前排名、源码状态或已验证的 ICODE 能力。持续维护的观察名单、上游版本和采纳记录请看[持续竞品对照](./agent-landscape-live.md)。本页中的热度数字、唯一性判断及未附一手来源的机制描述不得直接作为新设计依据。

- 日期：2026-09-23
- 调研方式：四路并行联网检索（终端/CLI 类、国产厂商类、开源框架类、热度榜单类）
- 关联：[方案与决策记录](./design-decisions.md) · [预研报告](./preresearch-2026-09-22.md)
- 数据说明：**所有 star 数来自第三方 tracker 的不同日期快照，口径不一致，只能看趋势，不能横向精确比较**；部分结论来自二手博客，已在 §9 标注可信度

---

## 0. 结论摘要

1. **通用 Agent 的四个坑（CLI 编码 Agent / IDE 内 Agent / 云自主 Agent / 通用 Agent 框架）已被填死**，不要重复造。
2. **与我们最相似的是一类新兴的「治理 sidecar」**：Conduct AI、MakerChecker、aegis、sofagent、Proving、FailproofAI、microsoft/agent-governance-toolkit —— 它们全都做 fail-closed 策略、哈希链审计、人工审批门，**但都是"套在不可审计的 Agent 外面的一道门"**（包住 Claude Code / Cursor / Codex）。
3. **我们的差异化因此非常清晰：治理是内核，不是外挂。** 证据在每一步执行中原生产出，fail-closed 是默认行为而非可关的开关，工单制把"为什么改"固化成可验证契约。**这个位置目前没有被占满。**
4. **最值得借鉴的 6 个机制**：OS 级强制沙箱、planner/executor 分流、检查点 + 时间旅行、幂等键 / 写前意图、HITL 硬门禁、渐进式上下文披露。
5. **我们真正独有的 4 项能力**（见 §6）：Reactive 边界复检、副作用感知重试、verdict-based 反误导注入、分步可切模型 + 哈希链账本。

---

## 1. 热度榜单（前 20，趋势参考）

| # | 产品 | 形态 | 热度依据（口径各异） |
|---|---|---|---|
| 1 | Claude Code / Anthropic | 闭源 CLI | ~142k★；份额估算居首；$20–200/月 |
| 2 | OpenCode | 开源 CLI/TUI | ~200k★，OSS 增速最快 |
| 3 | DeepSeek Harness (dsh) | 开源 CLI | ~203–211k★，2026-08 才发布 |
| 4 | OpenAI Codex CLI | 开源 CLI | ~112–119k★，Apache-2.0 |
| 5 | Gemini CLI / Google | 开源 CLI | ~107k★ |
| 6 | Pi / earendil-works | 开源 CLI | ~95–102k★，近 3 月 +40.8% |
| 7 | OpenHands / All Hands | 开源云/桌面 Agent | ~85k★，$18.8M A 轮 |
| 8 | Cursor / Anysphere | 闭源 AI IDE | 份额估算 15–26% |
| 9 | Warp | 闭源 Agent 终端 | ~64k★ |
| 10 | Cline | 开源 VS Code/SDK | ~67k★，4M+ 开发者 |
| 11 | Goose / Linux 基金会 | 开源 MCP Agent | ~53k★ |
| 12 | Zed | 开源 AI 编辑器 | ~79k★ |
| 13 | Aider | 开源终端 Git | ~48k★，4.1M 安装，**自 5/22 停更** |
| 14 | Continue | 开源 IDE 插件 | ~36k★ |
| 15 | GitHub Copilot / 微软 | 闭源多形态 | 份额估算 22–24% |
| 16 | Qwen Code / 阿里 | 开源 CLI | ~27k★ |
| 17 | Kilo Code | 开源 VS Code | ~27k★，$8M 种子轮 |
| 18 | Devin / Cognition | 闭源云 Agent | PR 合并率 ~67%，$20–500/月 |
| 19 | SWE-agent / 普林斯顿 | 开源研究 CLI | ~20k★，SWE-bench 强 |
| 20 | Roo Code | 开源 VS Code | ~24k★，**已停更**，由 Kilo 继承 |

国产侧补位（未进前 20 但机制值得看）：腾讯 **CodeBuddy**（插件+IDE+CLI 三形态）、阿里 **Qoder / 通义灵码**、百度 **文心快码 Comate**（SPEC 白盒化）、字节 **Trae**、智谱 **CodeGeeX / ZCode**、月之暗面 **Kimi Code**（`/swarm` 最多 300 并行子代理）、小米 **MiMo Code**、开源 **OpenSquilla**。

---

## 2. 格局判断

- **头部收敛、长尾发散**：闭源付费侧高度集中（Claude Code + Copilot + Cursor + Windsurf，CR4 估算 90%+，第三方聚合口径可靠性中低）；**开源侧反而在混战**——OpenCode / Codex CLI / Gemini CLI / DeepSeek Harness 四强并行，无单一赢家。
- **开源 vs 闭源的分野**：闭源 = 产品化 + 订阅 + 锁模型；开源 = BYOK / 本地模型 + 可审计 + 自托管。**合规与隐私诉求越强，越偏开源**——这正是我们的机会窗口。
- **新范式三条线**：① 长时自主云沙箱（Devin / OpenHands / Jules，issue→PR）；② 多代理编排（子代理、swarm）；③ **治理层从"事后观测"转向"执行前拦截"**——这是 2026 年最新、也是与我们最相关的一条。

---

## 3. 机制横向对比

### 3.1 终端 / CLI 类

| 产品 | 执行模型 | 审批 / 沙箱 | 状态恢复 | 验证机制 |
|---|---|---|---|---|
| Claude Code | 单主代理 + 子代理（隔离 worktree） | 5 种 permissionMode；**无 OS 沙箱** | 会话 JSONL + 压缩 | Verification 子代理跑测试/lint |
| Codex CLI | 单代理 loop | **内核级沙箱**（Seatbelt / bwrap+seccomp），审批与沙箱是两个独立旋钮 | 依赖沙箱+审批 | `auto_review` 子代理预审危险动作 |
| Gemini CLI | 单代理 | trust 设置 + 工具确认 | 未找到可靠来源 | 无内建验证循环 |
| Aider | 单代理 + architect 双模型 | 无沙箱；`/add` 显式授权 | **git 即状态**，每步自动 commit，可 `/undo` | 每次编辑后自动 lint+test 自愈 |
| Cline | Plan / Act 两阶段 | **每动作批准** | **影子 git 仓库** checkpoint 回滚 | 编辑后 lint 感知修复 |
| OpenCode | Build(全)/Plan(只读) + 多子代理 | 服务器控制权限 | **SQLite 持久化**，断线可恢复 | LSP 诊断回灌模型 |
| Charm Crush | 单代理 + Coordinator | permission + PreToolUse hooks | SQLite 持久化 | hooks 阻断危险命令 + LSP |
| Kilo Code | 模式 + **扁平子代理（不能嵌套）** | `kilo.jsonc` 按工具/通配授权 | CLI/IDE 共享会话 | 无内建验证 |

### 3.2 开源框架 / 自主 Agent

| 框架 | 编排 | 状态持久化 | 重试/幂等 | 验证 | 沙箱 |
|---|---|---|---|---|---|
| **OpenHands** | Action-Observation 循环 + **EventStream（append-only）** | 事件流落盘，可重放 | StuckDetector 卡死检测 | 跑项目自带测试 | Docker |
| **SWE-agent** | ReAct + **ACI（Agent-Computer Interface）** | 容器内 FS + 转录 | 步数预算；lint 失败即回退 | **跑 pytest + git diff** | 每任务独立 Docker |
| **LangGraph** | **显式状态机**（StateGraph） | Checkpointer，**支持时间旅行** | 需自实现幂等 | **interrupt / Command 人在环** | 依赖外部 |
| OpenAI Agents SDK | Runner 循环 + handoff | SQLiteSession | max_turns | guardrails + tracing | 无 |
| CrewAI | Crews + Flows | Flow 状态/缓存 | 超时、重试、回滚 | schema 校验 + 审批点 | 无 |
| Devin | 分层任务图 | 持久状态 + 代码库索引 | 测试失败→定位→修→重跑 | **两个不可配置 checkpoint** + Confidence 评分 | 隔离云沙箱 |
| Goose | 核心循环 + Recipe(YAML) | 每会话 JSON 导出 | subagent 并行 | Container Use（git 分支隔离容器） | 本地 Rust |

### 3.3 国产厂商

| 产品 | 形态 | 验证机制 | 差异化定位 |
|---|---|---|---|
| 腾讯 CodeBuddy | 插件 + IDE + **CLI** 三形态 | Plan 模式、隔离沙箱、**NPC 按 CI 结果迭代** | 企业研效 / 安全审计 |
| 阿里 Qoder | IDE + CLI | Quest「集成结果验证」 | Spec 驱动 + Repo Wiki 知识图谱 |
| 百度 文心快码 Comate | 客户端 + 插件 + CLI | **SPEC 白盒化**（Doc→Tasks→Changes→Summary） | 规范驱动 + 私有化 |
| 月之暗面 Kimi Code | CLI + VS Code | hooks（16 生命周期事件）门控 | **兼容 Claude Code 生态**，`/swarm` 并行 |
| 小米 MiMo Code | CLI（基于 OpenCode） | **Goal 完成度验证** | 持久记忆 + 无限上下文 |
| 智谱 ZCode | 多智能体 + 手机远程 | 未找到内置测试验证 | 完全开源可本地部署 |
| **OpenSquilla**（开源） | 框架 / 桌面 | **红-绿-回归证据链 + 隔离施工 + 自动修复闭环** | 自我验证 + TDD 内化 |

**国产共性打法**：Spec/白盒化先行压制幻觉；三形态全覆盖抢入口；**普遍兼容 Claude Code 生态**（Skills / Hooks / `.mcp.json`）降低迁移成本；自研模型 + 第三方模型分流。少数（OpenSquilla、CodeBuddy NPC、MiMo Goal）已开始从"生成即完成"转向"自证正确"。

---

## 4. 最值得借鉴的 6 个机制

### 4.1 OS 级强制沙箱（Codex CLI）★ 优先级最高

- **怎么做**：写策略在**内核层**拒绝 syscall（macOS Seatbelt / Linux bwrap+seccomp）；`.git`、`.agents`、`.codex` 受保护，防 `.git/hooks` 提权；沙箱与审批是两个独立旋钮。
- **对我们的价值**：我们的门禁目前是**应用层**的。应用层白名单挡不住模型主动绕过——**只要 Agent 能执行任意 shell，fail-closed 就只是约定而非机制**。
- **风险 / 成本**：三平台实现差异大（Windows 需另找方案，如 Job Object / AppContainer 或干脆用容器）。建议**分阶段**：一期先把 bash 工具限制在工作区内 + 危险命令拦截，二期再做真正的隔离。

### 4.2 planner / executor 分工（Aider architect、OpenCode Plan、Claude plan mode）★

- **怎么做**：只读规划代理产出方案，全权限代理执行；Aider 用强模型规划 + 廉价模型编辑，**成本降 60–70%**。
- **对我们的价值**：我们的工单制天然就是 Plan→Review→Merge→Code 的分段，**契合度最高**。而且我们"每步可单独调用、可换模型"的设计，正好落在"分步切换模型"这个行业前沿上。
- **风险**：规划阶段若无外部约束会产出"看起来合理但不可验证"的计划——我们的 `gates.json` 步骤契约正好补这一刀。

### 4.3 检查点 + 时间旅行恢复（LangGraph、Temporal）★

- **怎么做**：每超步落盘状态，崩溃后同 `thread_id` 续跑，可回溯任意历史态。
- **对我们的价值**：我们的哈希事件链管"**发生了什么**"（审计），检查点管"**如何恢复**"（韧性）——**两者互补而非重复**。目前事件链是唯一账本，恢复靠 `open_steps / open_operations / open_agents` 投影推导，够用但不够直接。
- **风险**：历史无界增长需摘要裁剪；重启即丢的内存 checkpointer 不可用于生产。

### 4.4 幂等键 + 写前意图（Write-Ahead Intent）★

- **怎么做**：副作用前由运行时生成**确定性**幂等键（如 `hash(会话ID, 动作类型, 序列号)`），服务端按 key 去重；配合意图哈希防篡改重放。
- **对我们的价值**：这正是我们 `ambiguous_side_effect`（同名副作用只有 start 没有 finish → 拒绝重放）的**同构解法**，但我们要的是"人工核对后继续"，而工业界做法是"幂等键让重试天然安全"。**两者可以叠加**：能幂等的动作自动放行，不能幂等的仍交人工。
- **风险**：键必须由稳定逻辑上下文派生，若用随机 UUID 则去重失效。

### 4.5 HITL 硬门禁（Devin 双 checkpoint、LangGraph interrupt_before）★

- **怎么做**：Devin 有两个**不可配置**的人为检查点（Plan Checkpoint、PR Checkpoint）；LangGraph 用 `interrupt_before` 挂在不可逆节点。
- **对我们的价值**：**直接对标**我们的 fail-closed 门禁。Devin 用"不可配置"强制门禁的思路值得我们学——**门禁必须不可绕过，否则等于没有**。
- **风险**：官方明确警告 —— interrupt 前置于副作用会导致**重复执行**，必须让副作用幂等或用状态标志。我们已有的 `before_side_effect` 边界复检正好是这一层的防线。

### 4.6 渐进式上下文披露（Gemini Skills、MCP 资源按需）★

- **怎么做**：能力默认不可见，匹配时才加载指令 / 读取资源，避免全量工具 schema 占满上下文。
- **对我们的价值**：**这是我们的一个明显短板**。`steps/01_plan.md` 67KB、`log.md` 146KB，若全量注入单步成本会失控。上游 SKILL.md 其实已经声明了"懒加载"原则，我们实现时要真正贯彻：**默认收起、按需挂载、工具结果在入链前先裁剪**。
- **风险**：按需加载会引入"该读的没读"这类遗漏——需要门禁侧强制校验必需输入，恰好我们 `gates.json` 的 `inputs[].required` 就是干这个的。

---

## 5. 我们的差异化定位

### 5.1 关键区分：原生可审计 vs 治理 sidecar

调研中最重要的发现是——**"fail-closed + 哈希链审计 + 人工审批门"不是蓝海，已有一个密集的子类**：

| 项目 | 许可证 | 做法 | 与我们相同的部分 |
|---|---|---|---|
| Conduct AI（Guard/Router） | Apache-2.0 | fail-closed 策略引擎、SHA-256 哈希链审计 | 策略 + 哈希链 |
| **MakerChecker** | AGPL-3.0 | 角色执行 + 人工审批门 + **Ed25519 签名哈希链日志** | 几乎完全同构 |
| aegis | MIT | 运行时策略 + 加密审计 + kill switch | 策略 + 审计 |
| **sofagent** | MIT | 专为编码 Agent 的**提交期审计**，git diff × 24 条规则 + HMAC 哈希链 | 编码场景证据 |
| microsoft/agent-governance-toolkit | MIT | **Merkle 链审计** + 沙箱 + 映射 OWASP Agentic Top10 / NIST / SOC2 / EU AI Act | 合规映射 |
| Proofline | MIT | 任务契约 → SHA-256 证明包，缺证据即拒 | 缺证据即拒 |
| FailproofAI | MIT + Commons Clause | 拦截危险工具调用，兼容 12 个 harness | 危险拦截 |

**但它们无一例外都是「在不可审计的 Agent 外面加一道可审计的门」。**

### 5.2 我们的位置

> **不是"给 Agent 装一道审计门"，而是"Agent 本身不可撒谎"。**

- 证据链在**每一步执行中原生产出**（`step start → check → artifact → finish` + 哈希事件链），而不是事后从 transcript 里抽
- fail-closed 是**默认行为**，不是可关的开关或可选 sidecar
- 工单制把"**为什么改**"固化为可验证契约（requirement → plan → review → code → evidence），而不是只审 diff

**一句话**：现有治理项目审的是"**产物**"，我们审的是"**过程**"。

### 5.3 潜在用户与竞品

| 维度 | 内容 |
|---|---|
| **用户** | 受监管行业（金融 / 医疗 / 政企）需要 AI 生成代码的可审计留痕；开源维护者（Agent 刷 PR 后"PR 成了证据问题"）；EU AI Act / SOC2 / PCI 范围内的团队 |
| **直接竞品** | Aider（git 提交即审计）、Cline（逐步审批 + 合规） |
| **治理侧竞品** | Conduct AI、MakerChecker、sofagent、aegis、microsoft/agent-governance-toolkit |
| **工单自主竞品** | Devin、OpenHands、SWE-agent |
| **差异化风险** | 必须明确与"治理 sidecar"阵营切割，否则会被误读为"又一个 Conduct AI" |

---

## 6. 我们独有的能力（需重点保护与宣传）

这些来自 `icode-skill` 的既有设计，在调研中没有发现等同物：

| # | 能力 | 说明 | 为什么难被复制 |
|---|---|---|---|
| 1 | **Reactive 边界复检** | 步骤开始时冻结受保护输入摘要；在写入 / 等待 / 副作用 / 状态转换**之前**重新计算，漂移即 fail-closed 回流，**禁止同一 attempt 静默刷新基线** | 业界普遍只做"开始校验"，**没有做"执行中持续校验基线漂移"**——这防的是"边做边被改"的经典事故 |
| 2 | **副作用感知 Retry/Fallback** | 4 类 operation_class × 6 类失败分类 → 决定 `retry / fallback / repair_then_retry / verify_receipt / block / human_decision`；**只有只读瞬时失败可自动重试** | 多数 Agent 重试策略不看"动作类别"，会把写操作重放，造成重复副作用 |
| 3 | **verdict-based 反误导注入** | 历史检索时，被**证伪 / 已废弃**的工单注入的是"陷阱"而不是"结论" | 常规 RAG 式记忆检索会平等注入历史决策，**反而把过去的错误结论当经验复用**——这是记忆系统的隐性毒化 |
| 4 | **分步可切模型 + 哈希链账本** | 每步独立命令，可在步骤之间自行换模型；所有 step/gate/artifact/operation 共用一条哈希事件链，`trace` 从同一来源生成时间线 | 业界多为"会话级"模型绑定；且审计信息常是旁路日志，**账本与执行同源**的很少 |

**加分项**：39 条反懒惰规则 + 强制 Read 留痕 + `file:line` 证据要求；独立质疑者对抗（**明确禁止自我委派**）；跨项目历史检索 + 决策锚点传递（`.decision_anchors.json`）；`init/log/plan` 多入口 + `--worktree` 隔离。

---

## 7. 需要规避的坑

| 坑 | 现象 | 我们的对策 |
|---|---|---|
| **指标误用** | 国产多家以"采纳率 / 补全率"标榜（44%、68–82% 等），是营销口径而非可靠性证据 | 我们只用**门禁通过率 / 回归是否通过 / 证据完整度**作为指标 |
| **纯生成无验证** | Trae、CodeGeeX、多数国产插件仍"改完即交、人逐行复核" | 门禁必须兜底，验证证据来自**外部工具退出码**而非模型自述 |
| **假沙箱** | 只做工具白名单 / hooks 拦截，模型仍可绕过 | 分阶段：先工作区限制 + 危险拦截，后做内核级隔离；**不要宣称"安全沙箱"** |
| **上下文膨胀** | 我们的步骤文档 67KB–146KB，比谁都大 | 强制渐进披露 + 工具结果入链前裁剪 |
| **对抗验证可被共谋攻破** | arXiv 2512.03097 证明：无防护下对抗 Agent 共谋可把有害建议成功率推到 100% | 验证者必须是**规则绑定的独立裁决**，而非"另一个 LLM 投票"；上游"禁止自我委派"的设计正好对 |
| **门禁过严致停滞** | fail-closed 在高不确定任务上会让 Agent 寸步难行 | 参考快手 L1→L2→L3 成熟度分级：先在非关键工单灰度，关键路径才上硬门禁 |
| **与 sidecar 阵营混淆** | 被误读为"又一个治理网关" | 宣传口径聚焦"**过程**审计 vs **产物**审计" |

---

## 8. 对我们的直接动作建议

按优先级：

1. **保持并强化内核级门禁** —— 这是我们的护城河，绝不能让 Model 有任何绕过路径（尤其 `bash` 工具）
2. **实现真正的渐进式上下文加载** —— 这是当前最薄弱的环节，也直接决定成本能否可控
3. **补齐 checkpointer** —— 让"事件链（审计）+ 检查点（恢复）"双轨并行
4. **引入确定性幂等键** —— 让能幂等的副作用自动重试，把人工介入留给真正不可逆的动作
5. **在定位与文档上明确切割 sidecar 阵营** —— 主打"过程可审计"
6. **E2E 指标就用退出码** —— `pycalc` 的 `python -m unittest` 退出码作为验收信号，不引入任何主观指标

---

## 9. 数据可信度说明

- **较可靠（一手）**：各产品官方文档（Anthropic / OpenAI / Google / 项目 GitHub / 各厂商官网）、学术论文（SWE-agent NeurIPS 2024、SagaLLM VLDB 2025、arXiv 2512.03097）。
- **需二次确认（二手博客 / 第三方 tracker）**：所有 star 数与增速（irrlicht、pinggy、benchgecko 等，日期集中在 2026-08）、份额估算（CR4 90%+ 等）、部分产品机制描述。
- **已剔除**：明确存在事实错误的二手文章（如把 CodeBuddy 误归百度、Qoder 误归腾讯）。
- **未获一手确认、暂不纳入决策**：GLM-5.3 细节；"开源侧 CR4"类聚合口径。
- **停更 / 变动风险**：Aider 自 2026-05-22 停更；Roo Code 已停更由 Kilo 继承；Charm Crush 许可证为 FSL-1.1-MIT（**非 OSI 开源**，两年后转 MIT）——这三项在选型对标时需注意。
