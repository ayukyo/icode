# 开发路线图与取舍原则

- 日期：2026-09-25
- 状态：**R2.1 工作区边界已验收；R2.2/R2.3 仍在 main 实施中，尚未通过阶段退出条件**
- 依据：[持续竞品对照](./agent-landscape-live.md) · [方案与决策记录](./design-decisions.md)

---

## 0. 一句话策略

调研结论收敛成两条：

1. **不做什么** —— 结合持续竞品对照，定期复核不学清单，避免把旧热度结论当成当前事实
2. **先做什么** —— 把「**过程可审计**」做成内核，而不是把功能做多

**战略主线**：功能广度上我们注定打不过 OpenCode / Codex / Claude Code，
唯一的赢面是**在"证据与门禁的严格性"这一个维度上做到无人能及**。

---

## 1. 三条原则（用于裁决所有后续争议）

| # | 原则 | 含义 | 冲突时的取舍 |
|---|---|---|---|
| P1 | **门禁不可绕过 > 功能多** | 只要 Agent 能绕开门禁，"可审计"就是谎言 | 为了保住不可绕过，宁可少做工具、降低自动化程度 |
| P2 | **过程可审计 > 产物可审计** | 这是与治理 sidecar 阵营的唯一切割点 | 不为兼容其他宿主而让证据链降级为旁路日志 |
| P3 | **成本可控 > 单次吞吐** | 我们的步骤文档 67–146KB，是全行业最大的 | 宁可慢、宁可多次交互，也不能全量注入 prompt |

---

## 2. 能力边界：对齐什么、不做不学什么

**重要澄清**：本路线图强调"别做广度"，指的是**不争形态渠道、不追功能数量**，
**不是**"功能少"。主流 Agent 的底层能力我们**基本都要对齐**——因为缺了它们，
"过程可审计"根本无从谈起（没有 Tool Loop 就没有过程，没有 MCP 就没有生态）。

### 2.1 主流能力对照（对齐清单）

| # | 能力 | 主流代表 | 我们的计划 | 阶段 |
|---|---|---|---|---|
| 1 | **Tool Loop**（读/写/改/检索/执行） | 全部 | ✅ 最小集 `read/grep/glob/write/edit`；`bash` P2 仅白名单命令，P5 随沙箱全开 | P2 起 |
| 2 | **多模型 backend** | Aider(100+)、OpenCode(75+) | ✅ backend 抽象 + MiniMax-M3 / OpenAI 兼容 / Anthropic / 本地 | P2 起 |
| 3 | **MCP 扩展** | 几乎全部 | ✅ 复用上游生态（`icode-skill` 已带 17 个 MCP 定义） | P2+ |
| 4 | **上下文管理** | Claude Code 压缩、Aider Repo Map | ✅ **渐进披露**（比"事后压缩"更前置） | P1 |
| 5 | **计划/执行分离** | Aider architect、OpenCode Plan | ✅ 工单制天然分段（Plan→Review→Merge→Code） | 已有 |
| 6 | **项目规则 / 红线** | `AGENTS.md`、`.clinerules` | ✅ `limit`（项目约束红线）+ `steps/` + `references/` | 已有 |
| 7 | **Skills 体系** | Claude Code、Gemini CLI | ✅ 复用 `icode-skill` 的共享技能包 | 已有 |
| 8 | **子代理 / 独立审查** | Claude Code、Kimi（300 并行） | ✅ **但用途不同**：只做**独立质疑者**，不追数量（见 2.3） | P3+ |
| 9 | **审批 / 权限** | Cline 每动作批准、Codex 沙箱+审批 | ✅ 应用层限制 + 审批门禁；**内核沙箱后置** | P1/P2 |
| 10 | **会话恢复 / 检查点** | LangGraph、Cline、OpenCode | ✅ checkpointer 与事件链**双轨** | P4 |
| 11 | **审计 / 证据留痕** | Cline、sofagent | ✅ **这是我们最强项**，且要导出为可独立校验的证据包 | 已有 + P3 |
| 12 | **本地 WebUI** | 上游已有、OpenCode | ✅ 二期（loopback + SSE） | P5 |
| 13 | **便利分发** | 各家安装方式 | ✅ Python 包（`pipx` / `uv tool install`） | P5 |

**结论**：以上 13 项，**没有一项是我们"不支持"的**。差别只在**顺序**和**实现方式**。

> ⚠️ **期待管理**：P1 结束时的 `icode` 是一个**几乎没有功能的契约测试壳**。
> 要等到 **P2 才是"能用的 Agent"**，P3 才有产品形态。不要指望一期就有完整体验。

### 2.2 四个已被填满的坑（形态渠道，不做）

| 不做什么 | 谁在做 | 为什么不做 |
|---|---|---|
| 通用 CLI 编码 Agent | OpenCode(~200k★)、Codex CLI、Gemini CLI、dsh(~203k★) | 四强混战，无差异化空间 |
| IDE 内 Agent / 插件 | Cursor、Cline、Continue、Kilo | 我们的卖点是可审计，不是编辑器体验 |
| 云自主 Agent（issue→PR） | Devin、OpenHands、Jules | 需要云基础设施与沙箱，重资产 |
| 通用 Agent 框架 | LangGraph、CrewAI、AutoGen、OpenAI SDK | 我们是应用，不是框架 |

### 2.3 七项"明确不学"（有意识地放弃）

| 不学 | 出处 | 为什么不学 |
|---|---|---|
| 数百并行子代理 | Kimi Code `/swarm`（最多 300） | 与 P1 冲突：并发放大门禁与审计难度，先要可控 |
| "采纳率 / 补全率"类指标 | 国产厂商常见口径（44%、68–82%） | 是营销指标不是可靠性证据，会诱导我们做假优化 |
| 工具白名单冒充"沙箱" | 多数产品的实际做法 | 会给我们虚假的安全感，必须诚实标注能力边界 |
| 多 LLM 投票式对抗验证 | 部分多代理框架 | arXiv 2512.03097 已证明共谋可攻破；坚持规则绑定 + 禁止自我委派 |
| 一次性实现内核级沙箱 | Codex（Seatbelt / bwrap+seccomp） | 三平台成本极高，且会拖死进度；改为分阶段 |
| 多形态入口同时铺开 | 腾讯 CodeBuddy 三形态 | 三形态是渠道打法，我们是单点深度打法 |
| 全量上下文注入 | 我们当前的默认做法 | 是成本生死线，必须改成渐进披露 |

---

## 3. 分阶段路线图

> **排序已按确认结论调整**：原计划的"证据包导出"从最后一期**提前到 Phase 3**。
> 理由见 §4 —— 它不是锦上添花，而是我们的**产品形态**。

### Phase 0 —— 预研与准备（**已完成**）

| 项 | 状态 |
|---|---|
| 预研报告 | ✅ `docs/preresearch-2026-09-22.md` |
| 方案与决策记录 D1–D10 | ✅ `docs/design-decisions.md` |
| 格局调研 | ✅ 历史快照 `docs/agent-landscape.md`；持续对照 `docs/agent-landscape-live.md` |
| 子模块（ssh + main + 浅克隆） | ✅ `vendor/icode-skill` @ `a4ddbce` |
| E2E 靶场 | ✅ `tests/fixtures/pycalc`（主）+ `tests/fixtures/demo`（附加） |
| 跨平台换行治理 | ✅ `.gitattributes` + 4 个 C 文件规范化回 LF |

---

### Phase 1 —— 契约内核（离线，零成本）

**目标**：证明我们与控制面完全对齐，全程不调真模型、不花钱、可进 CI。

| 项 | 内容 |
|---|---|
| 交付 | `pyproject.toml` + `src/icode/{config, control, backends, cli}` |
| backend | 只接 `fake`（离线回放） |
| 关键链路 | `step start → check(before_write) → artifact → check(before_transition) → finish` 全通，并用 `icode_control.py trace` 校验事件链 |
| **渐进披露（硬要求，分两层）** | **门禁规则每步强制注入（不可懒加载）**；背景知识才允许按需加载——先只读 frontmatter + 章节索引，按步骤再取正文。**禁止一次性注入整份文档** |
| 契约来源 | 从 `gates.json` 的 `step_contracts` 动态读取必需输入/输出/复检点，**不写死步骤表** |
| **上游契约防御** | 文档化依赖的控制面子命令与输出字段清单；**每次子模块 bump 必须重跑契约握手冒烟测试**。注：gitlink 记录的就是具体 commit，"跟随 main"实为**手动 bump**，不会自动漂移 |
| 权限模型（应用层） | 只读自动放行；工作区内写按策略判定；工作区外与危险命令**默认拒绝**。**措辞上不得宣称"沙箱"**，只称"应用层限制" |
| 验收 | ① `python -m unittest` 全绿 ② `trace` 显示事件链完整且 `open_steps` 为空 ③ 全流程无网络访问 ④ **子模块完整性：`vendor/icode-skill` 无任何本地修改**（`git -C vendor/icode-skill status --porcelain` 输出为空） |
| 成本 | 0 元 |
| 风险闸门 | 若发现控制面必须人工交互才能推进，立即停下来重新评估自动化边界 |

---

### Phase 2 —— 真模型 + Tool Loop（**已完成**，2026-09-23）

**目标**：在 `pycalc` 上真正跑完一条端到端流程，用退出码验收。

| 项 | 内容 |
|---|---|
| backend | MiniMax-M3（OpenAI 兼容，**标准库实现，零依赖**）；保留 anthropic / 本地扩展位 |
| 工具集 | `read / grep / glob / write / edit`（最小集）；**`bash` 默认禁用，仅开放白名单命令**（如 `python -m unittest`）——沙箱在 P5，执行类工具的开放程度必须与阶段绑定 |
| 副作用处理 | 所有写与执行动作包 `operation` 回执（start/finish），支持 `ambiguous_side_effect` 拒绝重放 |
| **人机交互协议** | CLI 形态：门禁要求人工决定时（destructive / `ambiguous_side_effect` / 工作区外写）**暂停并显式提示，用户确认后才继续**；非交互环境**一律拒绝** |
| **E2E 隔离** | 运行前**把靶场复制到临时工作区**再操作，跑完丢弃——避免污染 `tests/fixtures/` 基线 |
| **幂等键** | **确定性**幂等键（由稳定逻辑坐标派生，**不用随机 UUID**）；只读动作的传输类失败可自动重试 |
| **实测验收** | ① `icode task`：隔离靶场改 `calc.py`/`test_calc.py`，**独立跑 unittest 退出码 0**（11 回合 / 41,343 tokens）<br>② `icode step-run --step plan`：产物 `01_plan.md` 登记成功、`finish success`、事件链 24 条无未闭合 |
| 成本 | 实测 41K tokens / 任务（cached 33.9K）；预算闸门就绪 |
| 遗留 | 状态前移仍被 `thinking_gate` 拦下（未接 sequential-thinking，如实 degraded 不冒充）；完整 1→6 链路待后续 |

**Phase 2 实测中修掉的真问题**（都是真实运行才暴露的）：

| # | 问题 | 修法 |
|---|---|---|
| 1 | 模型习惯传 `"ls && -la"` 这类 shell 串，被当作"未知命令等审批"，提示词对模型毫无指导 | guard 增加**形态校验**：单参数含 shell 元字符 → DENY + 可纠正提示 |
| 2 | 简报里的上游相对链接 `../references/x.md` 诱导模型读工作区外文件，白烧整轮 | 简报**降级相对链接为纯文本** + 声明上游路径不可读 |
| 3 | 简报只列输入文件名不报存在性，模型满目录找 `00_init.md`，12 回合全耗尽在侦察 | 简报**逐项标注输入实际存在性** + 提示词禁止无目的侦察 |
| 4 | `ProxyHandler({})` 不注册为 handler，直连逻辑形同虚设；托管环境隧道代理 502 | 改为 `_proxy_mapping()` 显式契约；新增 `--no-proxy` / `ICODE_LLM_NO_PROXY` |
| 5 | 模型调用无重试，网络抖动即中断整步 | 只读动作的**传输类失败自动重试**（4xx 不重试），`Usage.retries` 可观测 |
| 6 | 触到 `max_turns` 时即使产物齐备也判失败 | **由证据判定成败**，不由循环停止原因判定；非自然结束降级为提示 |

---

### Phase 3 —— 证据包导出（**已完成**，2026-09-23）

**为什么提前**：这是唯一把 P2（过程可审计）变成**可交付物**的一步。
外部审计方消费的不是我们的日志，而是证据包——**它才是产品**。

| 项 | 内容 |
|---|---|
| **最小版证据包** | `manifest.json`（清单 + `pack_digest`）+ `ticket/events.jsonl`（账本原样）+ **`ticket/bodies/` 正文快照** + `artifacts.json`（正文↔链上 sha256 对应表）+ `contracts.json`（契约快照）+ `verifications.json`（含命令退出码）+ `verify.py` |
| **独立校验器** | `verify.py` **零依赖、不 import 本仓任何代码**（有静态测试断言），审计方只需 Python 标准库 |
| 校验覆盖 | ① 清单完整性 ② 事件链哈希链（复算 `canonical_event_hash` + `previous_event_hash` 链接 + event_id 唯一 + 首事件类型）③ 正文与链上哈希对应 ④ 包摘要 ⑤ **未登记额外文件** |
| **对外定位口径** | 明确切割治理 sidecar 阵营，主打"**审过程而非审产物**"；四条诚实边界写进包内 README |
| 验收 | 对一条真实工单导出包：**审计方在包外、无 PYTHONPATH 下独立校验通过（exit 0）**；篡改正文一处即被检出 4 处问题（exit 1） |

**实测结果**（用真模型产出的工单，24 条事件 / 1 个产物）：

```text
审计方独立校验（cwd=/，无 PYTHONPATH）→ 退出码 0
篡改正文后 → 检出 4 处：清单不符 / 大小不符 / 与链上哈希不符 / 链上产物缺正文快照 → 退出码 1
```

**四条诚实边界**（写在包内 README，不可省略）：
1. 证明「过程记录自洽且未被篡改」，**不是**「代码绝对正确」
2. `pack_digest` 需**外部锚定**才具抗抵赖力，否则可被整体重签
3. 权限模型是**应用层限制，非内核级沙箱**
4. 未接入 `sequential-thinking`，推理 trace 如实标 `degraded`

**Phase 3 顺带修掉的一个跨平台坑**：把 Git Bash 的 `/c/xxx` 路径传给 Windows Python
会抛 `NotADirectoryError` 堆栈；CLI 现在给出可操作的提示（"请用 `C:/...` 形式"）。

---

### Phase 4 —— 韧性与恢复（**已完成**，2026-09-23）

**双轨分工**：事件链管"发生了什么"（审计），检查点管"走到哪了"（恢复）。

| 项 | 内容 |
|---|---|
| **检查点** | `.agent_checkpoint.json`，**原子写**（临时文件 + `os.replace`）；只存回合数 / 工具调用数 / 历史摘要 / 未决审批计数 |
| **不保存模型正文** | 安全底线：模型对话内容绝不落盘；恢复时**从事件链重新水合上下文**，不回放聊天记录 |
| **真源优先级** | 检查点与事件链冲突时**事件链优先**，检查点被丢弃并告警 |
| **恢复决策** | `start_fresh` / `resume` / `verify_side_effect_first` / `blocked`；由 `trace` 的 `open_steps`·`open_operations`·`open_agents` 投影判定 |
| **副作用 fail-closed** | 有未终结副作用时**拒绝自动恢复**，要求先核对真实状态，再用 `resolve_open_operation()` 补 finish（上游规定的正确收尾） |
| **未决审批** | `pending_approvals > 0` 时明确提示"不会自动放行"，必须重新人工确认 |
| 类别未知时 | **按副作用处理**（fail-safe）——误判为只读会导致重放副作用 |
| 验收 | 两类崩溃演练均通过（见下） |

**崩溃演练实测**：

```text
① 写到一半中断
   第一回合写产物 → 第二回合后端崩溃 → 检查点留下进度
   工单侧：step_finished=0 / artifact_written=0（未误报完成）
   恢复分析 → resume → 续跑 → 登记产物 → 复检 → finish success
   不变量：artifact_written=1、step_finished=1（不重复登记）

② 副作用已发出但回执未知
   开一个 external_side_effect 动作 → 进程死亡（无 finish）
   恢复分析 → verify_side_effect_first（needs_human=True，拒绝自动继续）
   人工核对 → resolve_open_operation() 补 finish → 再分析不再阻断
```

---

### Phase 5 —— 隔离升级 · WebUI · 分发（**已完成**，2026-09-23）

| 项 | 内容 |
|---|---|
| **隔离能力层** | `isolation.py`：`probe_capabilities()` **实测**本机后端（bwrap / sandbox-exec / docker / podman），`select_sandbox()` 按结果选择 |
| 平台落地 | Linux → `bwrap`（文件系统 + 默认断网 + PID/IPC/UTS）；macOS → `sandbox-exec` Seatbelt profile；容器 → `docker`/`podman`（仅挂工作区 + `--network none`） |
| **Windows** | **未实现内核级隔离**（Job Object 只限资源不限文件/网络；AppContainer 需 Win32 组包）→ **如实报告「应用层限制，非内核级沙箱」** |
| 三条铁律 | ①能力靠探测不靠假设 ②没落地不许宣称沙箱 ③**隔离包装失败时拒绝执行，不降级执行** |
| 接入方式 | `--isolation auto|none|bwrap|docker|podman`；`doctor` 打印能力与诚实标注；执行结果 meta 带 `isolation` / `real_isolation` |
| **WebUI** | `webui.py` + `web_assets/`：唯一监听 `127.0.0.1`（无 `--host`）；`WebApprover` 是审批协议的第 4 个实现，core 不改 |
| **三条硬边界** | ①不做状态第二写入者（静态断言不 import 控制面）②不收路径/命令/shell（未知字段 400）③重启后不自动放行（挂起项只在内存） |
| **命名划线** | 上游 `/icode ui` 是宿主的工单浏览器；本仓叫 **`webui`** 而非 `ui`，避免混淆 |
| 安全细节 | 同源 Cookie（`SameSite=Strict`）、拒绝跨源 Origin、严格 JSON + 64KiB、无 CDN、无内联脚本、不用 `innerHTML` |
| 分发 | `console_scripts` 入口 `icode`；`package-data` 含 `web_assets/*`；`pipx` / `uv tool install` |

**实测**：

```text
隔离（本机 Windows）：[WARN] 应用层限制，非内核级沙箱 / 后端=none / 无可探测后端
WebUI 边界（真实 HTTP）：GET / →200（下发 Cookie）；无 Cookie 读 →403；带 argv 字段 →400；
                        跨源 Origin →403；未知 approval_id →409；错误 Content-Type →400
WebUI 闭环：网页放行 → 200，approver 返回 True
重启后挂起项：[]（不会自动放行）
分发：pip install --target → 包发现正常、web_assets 随包分发、bin/icode.exe 生成、
      从仓库外可执行、11 个子命令齐全
```

**顺带修**：`--skill-root` 原本只能写在子命令**之前**；现在通过 `parents` 让它在前后都能用
（用户和我自己都自然地写到了后面）。

**未验证项（如实记录）**：本沙箱禁止创建新 venv（`python -m venv` 返回 0 但目录不落盘），
因此 `pipx install` 的端到端未能在本环境验证；已用 `pip install --target` 覆盖到包发现、
资源分发与控制台脚本层面。

### Phase 6 —— 缺口收口（2026-09-23）

四个遗留缺口的处理结果：

| 缺口 | 状态 | 关键证据 |
|---|---|---|
| ① 推理门禁未满足 | ✅ **闭环** | L2 由本仓自实现的 `sequential` 承担；trace `result=success attempted=True 推演=5步`；**`plan` 步骤首次推进到 `plan_done`** |
| ② 完整 1→6 链路 | ⚠️ **部分**：编排器已建，`plan` 走通，`review` 阻塞 | 链路顺序由状态机派生；两个阻塞点已精确复现并定位（见下） |
| ③ Windows 内核级隔离 | ✅ **落地并诚实标注** | 新增 `WslSandbox`（真隔离，需显式指定）+ `WindowsJobLimits`（**部分强制：仅资源**，明说不是沙箱） |
| ④ pipx 端到端未验证 | ✅ **用 wheel 验证** | 构建 → 核验 entry_points/资源/RECORD → 安装 → 仓库外执行 → **12 子命令齐全** |

**诚实说明（缺口②）**：本轮**没有**让 1→6 全链路跑完。已经做到的是：
编排器可用、链路顺序不写死、`plan` 全绿并推进状态；`review` 及之后仍未通过。
阻塞点两条，均可复现：

1. **模型不落盘**：`review` 里模型倾向在文本里回答，不调用 `write_file` 写 `02_review.md`
   与 `review_round_1.json`。已加**有界补救回合**（列出缺失产物的绝对路径并要求立即写），
   本轮仍未救回，需要继续调优提示或改成"文本产出 → 本仓落盘"的显式通道。
2. **`operation_finish` 失败留下未闭合动作**：导致同名副作用再次 start 被判
   `ambiguous_side_effect`，运行时如实拒绝执行。已改为**显式暴露**（`inv.note` /
   `tool_result.meta.operation_finish_failed` / `operation_finish_failed` 事件），
   不再静默；但"为什么 finish 会失败"仍需下一轮定位。

**Phase 6 实测中修掉的真 bug**：

| # | 问题 | 修法 |
|---|---|---|
| 1 | **tool_call 与 tool 消息不配对**：单回合超上限时直接丢弃多余调用，assistant 仍列着它们 → OpenAI 兼容端点 **HTTP 400 invalid params**（整条链路曾因此走不动） | 未执行的调用也回一条**"未执行"**配对结果；单回合上限 4→8。加回归测试锁死一一对应 |
| 2 | 推演 `max_tokens=300` 对推理模型太小：思考吃满 token，剥离 `<think>` 后正文为空，5 步里 4 步空转 | 提到 1200；空响应立即停止并如实记录（不烧完额度） |
| 3 | `extra_instructions` 里写裸文件名（`01_plan.md`）与"必须写绝对路径"冲突，模型把产物写到工作区根目录 | 步骤说明**只描述内容、不写裸文件名**；提示词末尾再次钉住绝对路径并禁止写到工作区根目录 |
| 4 | 补救回合新建 `OperationRecorder` 导致 occurrence 计数重启、request 键重复 → 副作用歧义 | 回执器改为**整步共用** |
| 5 | WSL 只因 `wsl.exe` 存在就被自动选中（本机被安全策略拦截，命令全失败） | **存在 ≠ 可用**：WSL 不进自动选择列表，仅显式指定才用；`doctor` 区分"有可执行文件"与"可用" |
| 6 | `_ensure_gate_metadata` 用了 `json` 但 runner 未 import → `NameError` 中断整条链路 | 补 `import json` |

> 教训：本轮有**两次**用 `str.replace` 打补丁**静默未生效**（`run_contract_step` 的签名与 `sandbox` 参数），
> 之后改成"改完立刻 grep 核对"，才没有继续带着错往下跑。

### R2 —— 跨平台隔离策略（实施中）

R2.0 已发布版本化 policy schema、冲突规则与 contract vectors/score。
R2.1 已实现每工单 Git worktree 或非 Git 清单快照、跨进程租约、受保护路径策略，并接入自主运行生命周期。
Linux 本地回归验证了同工单两进程互斥、worker 退出后释放租约、原始 Git 工作树内容与状态不变、非 Git 快照清单和受保护路径合同。[三平台 CI 验收](https://github.com/ayukyo/icode/actions/runs/35880420396) 的 Linux、macOS、Windows 工作区专项、Python 3.11/3.12 全量测试与仓库展示检查均通过。
这些工作区边界和策略合同**不等于操作系统强制隔离**：模型执行尚未被原生内核机制限制。
R2.2 已合入 main 持续验证 Linux/macOS 原生后端。[CI #85](https://github.com/ayukyo/icode/actions/runs/36001610973) 的 Ubuntu 22.04/24.04 x64/ARM64 原生与 wheel 测试全部通过，只验收 Linux PID 清理子项；两平台完整退出条件尚未通过，自动模式仍阻断。R2.3 当前开发 Windows AppContainer + Job Object 的原生实验；CI #91–#105 的 Windows AppContainer 原生启动探针多轮返回 `CreateProcessW` 错误 203，#105 固定 whoami 对照发现需设置 profile `LOCALAPPDATA`。常规路径接入后，CI #106–#111 的 Python 仍退出 `0xC0000135`；#110 的工作区/网络和后代清理组件 notice 通过，但 profile marker 两架构均未写入，进程数正反对照不确定。#111 发现测试诊断时序和 CMD 状态行编码有误，未运行 `process_limit=1` 负例；这些属于 harness 问题，不产生新的隔离结论。CI #96–#102 普通 Job 对照双架构通过，#104 windows-latest 普通 Job 正向对照也成功；#102 属性大小查询 122/48 字节符合 Win32 预期。不得据子项通过认定 Windows 隔离完成，自动模式继续关闭。macOS Intel/ARM64 的脱组后代握手负例在 #101 通过，按已批准的 Codex 式边界验收。默认无网络能力的 AppContainer 是候选实现，域名代理仍需独立网络强制机制。R2.4 Git 仅完成不执行 Git 的 porcelain v2 字节解析器前置模块；`git_broker_unavailable` 不变，可信会话绑定、元数据只读、helper 禁止、无网络、原仓不变及跨平台恶意仓库负例尚待实现/验收。R2.4 网络代理已新增 `NetworkLease` 范围校验和本机审批/HMAC/内存撤销 authority；最长租期 15 分钟，绑定策略摘要与工单步骤。但它未创建代理、未接入执行器，也未设置 OS 强制路由，联网保持关闭；点时验证与未来连接建立间还存在撤销竞态，代理须解决原子连接登记和到期/撤销关闭。已研究建议 Linux 先做 netns + 可信桥接 HTTP(S) 切片，macOS/Windows 在各自 OS 级门禁通过前保持 DENY。R2.5 负责安装引导和发布矩阵。开发期线上只保留 main，不以合入主线代替阶段验收。
完整 R2 的验收门槛仍是 Linux、macOS、Windows 每个平台均达到 ≥9/10，且 8 项 critical 全部通过。

### 2026-09-25 UTC：CI #120 交叉平台回执

CI [#120](https://github.com/ayukyo/icode/actions/runs/36081977910) 中 R2.1 工作区三平台、Python 3.11/3.12 与 R2.2 Linux/macOS 原生探针矩阵均通过，官网工作流 [#55](https://github.com/ayukyo/icode/actions/runs/36081977987) 通过。Windows x64 与 ARM64 AppContainer 作业仍失败：两架构均见 Python `0xC0000135`；actual `LOCALAPPDATA` 键唯一，CMD 对显式注入的 API 路径 alias 比较为不相等，宿主 `stat=not_found`，路径位于 API profile 下方但不是 API `Temp`，profile marker 缺失。具体子目录尚未分类，不能推断与 Python 加载失败有因果关系。工作区、网络和 Job 子项的通过 notice 仍只是组件证据。故 R2.2 的当前原生探针矩阵通过但完整阶段门槛未闭合；R2.3、R2 全阶段与 `policy_contract_ready` 均未通过，自动模式继续关闭。

### 2026-09-25 UTC：CI #121 子目录分类回执

CI [#121](https://github.com/ayukyo/icode/actions/runs/36083440360) 的 Windows x64 与 ARM64 AppContainer 探针均失败；新增脱敏关系分类显示 actual `LOCALAPPDATA` 属于 API profile 下的多层子路径（`api_child_nested`），两架构 Python 仍以 `0xC0000135` 退出，profile marker 缺失。工作区/网络负例、Job 进程限制对照和后代清理的组件 notice 通过，不构成完整 Windows 隔离验收。下一轮只再识别首层是否为 `Temp`、`Local`、`LocalState` 或其他类别，不输出路径、不改 ACL；R2.3、完整 R2 和自动模式仍未通过。

### 2026-09-25 UTC：CI #122 Windows profile 路径复核

CI [#122](https://github.com/ayukyo/icode/actions/runs/36083962877) 的 Windows x64 与 ARM64 均将 actual `LOCALAPPDATA` 归为 `api_child_other_nested`；宿主 `stat=not_found`、profile marker 缺失、Python 仍退出 `0xC0000135`。其它平台矩阵通过。profile 子目录进一步猜测的收益有限，下一轮改为每个 Python 运行时文件直读探针完成时立即输出脱敏 notice，避免末尾断言失败掩盖逐项证据；仍不放宽 ACL 或输出路径。Windows R2.3、完整 R2 与自动模式继续关闭。

设计与实施依据：[R2 跨平台隔离设计](./nbl/specs/2026-09-23-r2-cross-platform-isolation-design.md) ·
[R2.0 policy contract 实施计划](./nbl/plans/2026-09-23-r2-policy-contract.md) ·
[R2.1 工作区与租约实施计划](./nbl/plans/2026-09-23-r2-workspace-lease.md) ·
[R2.2 Linux/macOS 原生隔离实施计划](./nbl/plans/2026-09-23-r2-native-isolation.md) ·
[R2.3 Windows AppContainer 实验计划](./nbl/plans/2026-09-25-r2-windows-appcontainer.md) ·
[R2.4 Git 状态代理门禁](./nbl/plans/2026-09-24-r2-git-broker-gate.md) ·
[R2.4 临时网络授权门禁](./nbl/plans/2026-09-24-r2-network-proxy-gate.md)

R2.3 Windows AppContainer 原生探针现已有 CI #91–#112 结果；Windows x64 与 ARM64 的 #91–#105 原生启动探针多轮返回 `CreateProcessW` 错误码 203，#105 固定 whoami A/B 发现设置 profile `LOCALAPPDATA` 后启动成功。常规路径接入后，#106–#112 的 Python 均退出 `0xC0000135`。#112 的同载荷 `process_limit=2` 正对照与 `process_limit=1` 负对照在双架构均通过组件断言（负例无子 marker、启动状态 1816）；profile 路径仍在 AppContainer 内不可见、marker 两架构均缺失。工作区/网络与后代清理 notice 只是子项证据。微软启动指南称 profile 是 AppContainer 可创建/读写的数据位置，但路径查询本身不创建目录或改 ACL；当前先核对容器实际 SID、环境路径与逐段访问回执，不扩大 ACL。自动模式继续关闭。普通 Job 对照双架构通过；属性查询 122/48 为预期，runner 根因未证实。macOS Intel/ARM64 的脱组后代握手负例在 #101 通过，按已批准的 Codex 式边界验收。Windows AppContainer 仍为实验态，不接自动工单。

CI [#105 x64](https://github.com/ayukyo/icode/actions/runs/36059960206/job/107836254760) 与 [#105 ARM64](https://github.com/ayukyo/icode/actions/runs/36059960206/job/107836255639) 的固定 whoami 同-profile A/B 均显示：省略容器 `LOCALAPPDATA` 时 `CreateProcessW` 返回 203，加入系统 API 返回的 profile 路径后成功且清理通过；但当时完整 AppContainer 流程的常规命令尚未带该变量，整组作业仍失败。当前代码已将容器专属路径接入常规 AppContainer 命令及撤权探针，并新增路径查询失败不启动、准确报告清理状态、临时 profile 数据目录删除/残留核验的测试；这条常规路径尚待新的 Windows x64/ARM64 CI。Windows AppContainer 与完整 R2 仍未验收，自动模式保持关闭。

CI [#106 x64](https://github.com/ayukyo/icode/actions/runs/36063691161/job/107848355215) 与 [#106 ARM64](https://github.com/ayukyo/icode/actions/runs/36063691161/job/107848355043) 已证明固定 whoami 的同-profile `LOCALAPPDATA` A/B 两边均可成功；但两项环境块断言拦截的是追加变量前的基础块，属于探针捕获层错误，现改为核对最终传给 `CreateProcessW` 的块。原生 Python 子进程退出码 `0xC0000135`（`STATUS_DLL_NOT_FOUND`），只能确认当前宿主 Python 运行时还不能在此 AppContainer 路径运行，具体依赖/访问原因尚未定位；工作区/网络组合探针仍返回 1，待补齐逐阶段成功标记后复验。上述结果没有证明 Windows 文件/网络门禁通过，R2.3、完整 R2 与自动模式仍未验收。

### 2026-09-24 UTC CI #112：进程上限组件通过，profile 与 Python 仍失败

CI [#112](https://github.com/ayukyo/icode/actions/runs/36074365589) 的 x64 与 ARM64 同载荷进程上限正反对照通过组件断言；cap=1 时没有子 marker、启动状态为 1816。两架构 `LOCALAPPDATA` 均已定义、API 路径宿主侧预先存在，但容器目录检查为假、写入类别 `path_not_found`、删除前 marker 缺失；Python 仍退出 `0xC0000135`。最新测试增加了只显示路径相等布尔值的对照，不输出路径；在 token SID、实际环境值与逐段访问问题查清前，不做目录创建或 ACL 放宽。R2.3/完整 R2 未通过，`policy_contract_ready=false`。

---

### 2026-09-25 UTC CI #113：profile 环境路径比较需原生复验

CI [#113](https://github.com/ayukyo/icode/actions/runs/36075689060) 的 x64 与 ARM64 普通检查及 `process_limit=2/1` 正反对照通过组件断言；两架构 AppContainer 集成仍失败，Python 继续退出 `0xC0000135`。profile notice 均显示 `LOCALAPPDATA` 已定义、API 路径宿主侧存在、容器内目录不可见、写入错误 `path_not_found`、删除前 marker 缺失。`cmd.exe set LOCALAPPDATA` 重定向文本比较为 false，但输出编码未固定，不能据此断言传入环境值不同。当前测试仅在环境块加入同值临时 alias，由受限进程内 CMD 比较并只发布 match/mismatch，不改生产环境或 ACL；Windows 自动模式和完整 R2 继续关闭。

### 2026-09-25 UTC CI #114：同块 alias 比较仍为 false

CI [#114](https://github.com/ayukyo/icode/actions/runs/36077520320) x64/ARM64 的 AppContainer 集成均失败；Job `process_limit=2/1` 对照仍通过组件断言，Python 仍退出 `0xC0000135`。容器内 `LOCALAPPDATA` 与 API 路径 alias 的 CMD 比较在两架构均为 false，但 alias 是否到达 CMD 尚未单独测量。新一轮只增加 alias-defined 状态和 Unicode `cmd /u` 输出，在宿主内比较实际值与 API 路径、notice 只报布尔值；不输出路径、不改变 ACL。R2.3、完整 R2 与 Windows 自动模式仍未验收。

### 2026-09-25 UTC CI #115：alias 存在但 profile 值不匹配

CI [#115](https://github.com/ayukyo/icode/actions/runs/36078212333) x64/ARM64 的 AppContainer 集成仍失败；`expected_localappdata_defined=true`，profile 路径不可见、marker 缺失，Python 退出 `0xC0000135`。Unicode `set` 输出的解析比较为 false，但当轮未记录子命令退出码或输出是否存在，不能据此判断值不匹配。CI [#116](https://github.com/ayukyo/icode/actions/runs/36078821652) x64 的 API/宿主路径比较也均为 false，但沿用相同的未验证采集文件，仍不能判断实际值。下一版记录 Unicode 子命令退出码和输出非空状态，仅对有效采集做内存布尔比较；不传入宿主路径、不授权访问。R2.3 和自动模式继续关闭。

### 2026-09-25 UTC CI #116：Unicode 采集有效性尚未核验

CI [#116](https://github.com/ayukyo/icode/actions/runs/36078821652) x64 的 profile 路径比较（API 值和宿主值）都报告 false，但 Unicode `set` 子命令的退出码、输出文件是否非空尚未单独采集，因此这两个结果不足以认定路径与两者都不同。下一版仅补这两个采集状态，并在有效时保留 API/宿主两个内存比较；不记录路径、不将宿主 profile 用于容器。Windows 自动模式与 R2.3 继续关闭。

### 2026-09-25 UTC CI #117：有效 Unicode 输出与 API/宿主值均不匹配

CI [#117](https://github.com/ayukyo/icode/actions/runs/36079222456) x64/ARM64 的 `cmd /u` 子命令均退出 0、输出文件非空，expected alias 已定义；当前解析出的 `LOCALAPPDATA` 不等于 API profile 路径，也不等于宿主变量。该结果将问题进一步收窄到受限子进程观察到的值/解析项，但仍未证明实际字符串含义（下一步核实 exact 键唯一性、actual/API 父子同级关系与文件系统对象身份）。profile 不可写、Python `0xC0000135`，Windows 自动模式与 R2.3 继续关闭；不扩大 ACL。

### 2026-09-25 UTC CI #118：删除前 actual path 仍不等于 API 对象

CI [#118](https://github.com/ayukyo/icode/actions/runs/36079893851) x64/ARM64 在 profile 删除前都确认 Unicode 输出有效、actual `LOCALAPPDATA` 键唯一，但宿主 `Path.is_dir` 与 `samefile(API profile path)` 均为 false；此采样尚未记录 `stat` 错误码，不能区分路径不存在与 host-side access-denied。下一版记录只读 `stat` 分类及 actual/API 的父子同级关系；不输出路径、不改变权限。Windows 自动模式与 R2.3 继续关闭。

### 2026-09-24 UTC CI #107：Windows cwd-relative 探针

CI [#107 x64](https://github.com/ayukyo/icode/actions/runs/36066941127) 的最终环境块与 profile `LOCALAPPDATA` A/B 检查通过；Python 仍退出 `0xC0000135`。CMD 批处理脚本未落下任何工作区标记，运行时文件诊断也未复制文件，故不能推断源文件 ACL。当前探针改用任务工作目录相对路径并增加 inline 写入对照；x64 不通过，ARM64 当时仍运行。R2.3 与自动模式继续关闭。

### 2026-09-24 UTC CI #108：工作区访问与子进程验收仍未闭环

CI [#108 x64](https://github.com/ayukyo/icode/actions/runs/36067827628/job/107861602120) 与 [#108 ARM64](https://github.com/ayukyo/icode/actions/runs/36067827628/job/107861602149) 的公开 notice 支持 profile 环境、cwd-relative workspace 及 loopback 子项通过，Python 两架构仍退出 `0xC0000135`。独立只读复核发现公开 Actions 注释不足以恢复精确失败断言：x64 没有 timeout notice，ARM64 只报告清理状态，日志 API 无法读取，因此不再把旧 notice 解读为具体失败根因。该提交 `eabc4df` 的源测试对 3 秒子进程仅留 3.2 秒观察窗，且没有同一 payload 的无 Job 正向对照；故 #108 不作为可靠的进程清理通过证据。#109 加入 release handshake 并有两架构子项通过 notice，但仍缺同 payload 正向对照和充分观察窗。#110 增加了 host 同载荷后代正对照及五秒清理观察窗，双架构组件 notice 通过；但 profile 写入与进程上限控制仍未验证，Python runtime 仍退出 `0xC0000135`。Windows R2.3 与自动模式继续关闭。

### 2026-09-24 UTC CI #109–#111：Windows 子项与真实失败分开记录

CI [#109 x64](https://github.com/ayukyo/icode/actions/runs/36069030309/job/107865391485) 与 [#109 ARM64](https://github.com/ayukyo/icode/actions/runs/36069030309/job/107865391466) 的 Windows 测试均有 cwd 工作区、loopback 拒绝、后代回收与 timeout 回收通过 notice，但研究复核指出进程探针只有 0.2 秒宽限。CI [#110](https://github.com/ayukyo/icode/actions/runs/36071476528) 以同 payload host 正对照和五秒后代观察窗重验后，双架构正常/timeout 后代清理 notice 通过；x64/ARM64 profile marker 均未写入，进程数对照尚不可靠。CI [#111](https://github.com/ayukyo/icode/actions/runs/36073278352) 的同步进程正对照父/子 marker 均出现，但临时目录诊断读取太晚、CMD 裸数字状态行未写出，导致两架构都在 `process_limit=1` 负例前失败。Python 仍退出 `0xC0000135`，AppContainer 和自动模式继续关闭；下一轮修正探针本身并重跑原生对照。

## 4. 为什么是这个顺序

| 顺序 | 依据 |
|---|---|
| Phase 1 先离线 | 控制面门禁极严（fail-closed），**不确定"我们的 Agent 能否满足契约"之前，接真模型就是烧钱** |
| 渐进披露必须在 Phase 1 | 步骤文档 67–146KB，是全行业最大；这是**成本生死线**，晚做等于先烧光预算 |
| **证据包提前到 Phase 3** | 它是**产品形态**而非收尾工作。越早做出可交付的证据包，越早能验证"过程可审计"这个定位是否真的成立；若等到最后才发现定位不成立，前面的投入全部报废 |
| 幂等键在 Phase 2 | 工业界已有成熟做法（确定性幂等键 + 写前意图），直接对齐，不必自研 |
| 内核沙箱放在 Phase 5 | 它是唯一能真正保证 P1 的手段，但三平台成本最高 → **先想清楚、分阶段落，但绝不能假装已经具备** |
| 韧性在证据包之后 | 证据包定义"什么算完成"，恢复机制定义"没完成怎么办"——**先定义完成，再定义恢复** |

---

## 5. 度量体系（质量指标与运营指标分开）

### 5.1 质量指标（只认三个，用于验收）

| 指标 | 定义 | 为什么 |
|---|---|---|
| **门禁通过率** | 首个 attempt 即 `finish success` 的步骤占比 | 反映 Agent 是否真在收集证据，而非反复碰运气 |
| **回归退出码** | E2E 靶场 `python -m unittest` 的退出码 | 客观、不可伪造、跨平台一致 |
| **证据完整度** | 每个产物是否都有 `artifact` 登记 + 短证据引用 | 这是我们与 sidecar 阵营的差异点，必须可度量 |

**防博弈**：门禁通过率**不可单独使用**——Agent 若知道指标，可能靠降低标准（如隐瞒漂移）刷分；必须与任务难度、证据完整度**配对观察**。

### 5.2 运营指标（只管预算，不进验收）

| 指标 | 用途 |
|---|---|
| 单工单 token / 费用 | P2 预算闸门（"超预算 3 倍即回退"）的**数据来源** |
| 任务耗时 / 尝试次数 | 观测回归，不用于横向比较 |

**区分逻辑**：token 与耗时会随任务规模、模型波动剧烈变化，**当质量指标会被优化成偷工减料或刷分**；但当运营指标是预算闸门的必需输入——**两者混用就是自相矛盾**。

---

## 6. 已确认的取舍（2026-09-23）

| # | 决策点 | 结论 |
|---|---|---|
| 1 | Phase 1 范围 | **只做离线契约内核，不接真模型** —— 最低成本的风险探针 |
| 2 | 渐进披露 | **提为 Phase 1 硬要求** |
| 3 | 沙箱措辞边界 | Phase 1–2 只做**应用层限制**，对外**绝不宣称"安全沙箱"** |
| 4 | 确定性幂等键 | **引入**，对齐工业界成熟做法 |
| 5 | 证据包导出 | **从最后一期提前到 Phase 3**，视为产品形态 |
| 6 | 交付节奏 | **逐 Phase 验收**，每阶段留明确验收点 |

---

### 6.1 自检修正（2026-09-23 第二轮，换模型交叉审查）

| # | 发现 | 修正 |
|---|---|---|
| A1 | "零第三方依赖"与 Tool Loop / SSE / token 计数 / MCP 客户端冲突 | 改为 **core 零依赖 + 可选 extras**（`icode-agent[llm]` / `[web]`） |
| A2 | 成本被排除出度量，但 P2 预算闸门需要它 | 成本 = **运营指标**（管预算），不进质量验收（见 §5.2） |
| A3 | 依赖上游 main，但上游无契约稳定性承诺 | P1 验收加**上游 bump 冒烟测试**；依赖面文档化；澄清 gitlink 即 pin |
| B1 | 事件链不存正文 vs 审计需正文的张力 | 证据包 = **正文快照 + hash 对应表**，校验器验 hash 匹配 |
| B2 | 渐进披露可能漏读门禁规则 | 分两层：**门禁规则强制注入**，背景知识才懒加载 |
| B3 | E2E 会污染靶场基线 | 运行前复制到临时工作区，跑完丢弃 |
| B4 | CLI 人在环交互未定义 | P2 初定义**暂停/确认协议**并文档化 |
| C1 | 文档 5 份、代码 0 行，规划过剩 | **立即启动 Phase 1**，停止继续膨胀文档 |
| C2 | P2 首次让真模型跑 bash，而沙箱在 P5 | **P2 的 bash 默认禁用，仅白名单命令** |

---

## 7. 阶段交付工作流（每阶段一次 commit + push）

**约定**：每开发完一个阶段（Phase 验收全部通过），**立即自动 commit 并 push 一次**，不攒批。

### 7.1 提交前守护（三条全过才允许 commit / push）

| # | 守护 | 命令 / 规则 | 不过怎么办 |
|---|---|---|---|
| ① | **密钥扫描** | 全仓扫描 `sk-`、`Bearer `、`apiKey` 等形态与密钥文件名；命中即中止 | 排查来源，删除或移出仓外 |
| ② | **子模块完整性** | `git -C vendor/icode-skill status --porcelain` 必须为空，且 HEAD == 记录的 gitlink | 本仓**永不修改** `vendor/icode-skill/**`；修复一律在上游仓库独立进行 |
| ③ | **测试全绿** | `python -m unittest` 退出码 0 | 修完再交付 |

### 7.2 提交规范

- commit message：`phase<N>: <一句话成果>`（如 `phase1: offline contract handshake green`）
- push 目标：`origin main`
- 一阶段一提交，**禁止把多个 Phase 混在一个 commit 里**

### 7.3 `.gitignore` 责任边界

自动提交意味着**没有人工把关的机会**，所以 `.gitignore` 必须先行兜底，已覆盖：

| 类别 | 模式 |
|---|---|
| 密钥与本地配置 | `.env`、`*.key`、`*KEY*.txt`、`*密钥*.txt`、`icode.local.toml` 等 |
| Agent 运行产物 | `.icode_output/`、`.ico_*/`、`.icontrol.lock` |
| 工作数据 | `.workbuddy/*`（**保留** `.workbuddy/skills/` 供项目技能共享） |
| Python 构建与缓存 | `__pycache__`、`*.egg-info`、`.venv`、`.pytest_cache`、`.coverage`、`htmlcov` |
| IDE / OS | `.idea`、`.vscode`、`.DS_Store`、`Thumbs.db` |
| 临时产物 | `*.tmp`、`.tmp/`、`*.log` |

---

## 8. 一句话总结

> 调研告诉我们**别做广度**。我们的开发决策只有一条主线：
> **把"证据与门禁"这一个维度做到无人能及，其余一切都可以晚做、少做、甚至不做。**
