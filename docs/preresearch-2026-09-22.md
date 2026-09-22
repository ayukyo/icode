# ICODE Agent 工具 · 预研报告

- 日期：2026-09-22
- 目标仓：`icode`（git@github.com:ayukyo/icode.git，本地 `D:\AI_CODING\icode`）
- 依赖仓：`icode-skill`（git@github.com:ayukyo/icode-skill.git，本地 `D:\AI_CODING\icode-skill`）
- 结论用途：确定 `icode` 仓的定位、边界与技术选型，先看清楚再动手

---

## 0. 一句话结论

`icode-skill` 是**"提示词工作流 + 机器控制面"**，它自己**不会思考也不会动手**——思考和动手由宿主（Claude Code / Codex / CodeBuddy）承担。它唯一的自研执行层 `agent_runtime` 目前只有"有界单回合 + 本地 UI"，并且**在 README 里明确写明：工具循环尚未启用，将来必须经过 Tool Gateway**。

所以 `icode` 仓最有价值的定位是：**补上这块缺口——一个自带 Tool Loop、能脱离宿主独立跑完 ICODE 全流程的 Agent 运行时**，把 `icode-skill` 的 `steps/*.md`（流程）、`gates.json`（门禁）、`icode_control.py`（状态）当作**真源**来消费，而不是重写一遍。

`demo/`（C 计算器）是现成的、确定性的 E2E 靶场。

---

## 1. 现状盘点

| 项 | `icode`（目标仓） | `icode-skill`（依赖仓） |
|---|---|---|
| 本地路径 | `D:\AI_CODING\icode` | `D:\AI_CODING\icode-skill` |
| Git 状态 | `main` 分支，**0 commit**，工作区全空 | 有完整历史，最新 `0e91836 feat(seo)` |
| 远端可达性 | 本机**无法解析 github.com**（DNS 失败），`git ls-remote` 不可用于验证 | 同左（本地副本完整，可离线研究） |
| 体量 | 空 | SKILL.md 46KB、README 38KB×2、`steps/` 29 个文件、`references/` 26 个、`tools/` 40+ 脚本 |
| 版本 | — | **ICODE v2.32.0** |
| 本机安装 | — | 已安装于 `~/.claude/skills/icode`；`~/.claude/icode_data/` 已有 index.json / project_docs / mcp_entries |

`demo/` 目录的实际内容（不是空壳）：

```text
demo/
├── calc.h   (5.4KB)  错误码 + calc_basic/calc_power/calc_sqrt/calc_isqrt/calc_eval 声明
├── calc.c   (18KB)   实现，含 calc_isqrt → 转发 calc_sqrt 的兼容别名
├── main.c   (15KB)   大量 printf 自测用例
├── Makefile          gcc -Wall -Wextra -std=c99 -O2，`make test` 6 条 grep 断言
├── .all_tests_final/         ← 已入库的测试夹具快照（286 个文件，含 .icode_output 样本）
└── .ui_runtime_sim-final/    ← UI 运行时仿真产物
```

---

## 2. `icode-skill` 架构解剖（五层）

```
L0 发现层   SKILL.md frontmatter (name/description) —— 宿主凭此决定是否加载
L1 路由层   SKILL.md 命令表 → steps/*.md（29 个）；主流程 00_init→01_plan→02_review
            →03_merge→04_code→05_deepcheck→06_audit→07_readme→08_patch
L2 知识层   references/*.md（26 个，懒加载）—— anti_laziness / thinking_core /
            inspection_worklist / worktree_isolation / host_adapters ...
L3 机器层   tools/icode_control.py（293KB，27+ 子命令）+ mcp/workflow-gate/gates.json
            （33KB，门禁真源）+ schemas/（7 个 JSON Schema）
L4 执行层   agent_runtime/ —— backends(fake / openai-responses)、ui_server.py、
            host_runner.py、ticket_catalog.py
L5 宿主层   integrations/codebuddy（命令桥）+ mcp/*（17 个 MCP server）
```

**最关键的认知**：`steps/*.md` 是**给宿主 LLM 看的 prompt 合同**，不是可执行代码。
`SKILL.md` 里那句"步骤编号/产物文件名一律以 `steps/*.md` 实时清单为准"意味着：
流程定义是**数据**，执行者是**别人**。

### 控制面（L3）才是真正的"机器真源"

`tools/icode_control.py` 是**唯一写入口**（禁止绕过直写 metadata）：

```text
resolve-ticket / create / create-next / check-outputs / validate / event
step        ← 步骤端口 start / check / finish（回执制）
artifact    ← 落盘产物登记（hash）
inspection  ← 原生自查清单（不调模型）
operation   ← 长动作 start/finish 回执（禁止盲重放副作用）
policy      ← 副作用感知 Retry/Fallback 决策
trace / action-policy / transition / metadata-update
index-write / index-update / migration
record-verification / record-claim / record-skill-run
record-agent-spawn / record-agent-result     ← 外部 Agent 的登记口
archive-manifest / close-phase / reopen / snapshot
```

`gates.json` 的 `execution_model` 摘要（自动导出，可直接作为我们 Agent 的编排依据）：

- **12 个已登记步骤**：`init / log / plan / review / merge / code / deepcheck / audit / patch / verify / readme / worktree`
- **4 类 boundary 复检点**：`before_write` / `after_wait` / `before_side_effect` / `before_transition`
  - `plan/code/merge/patch/readme/init`：before_write（+ before_transition）
  - `review/deepcheck/audit`：多一个 `after_wait`（因为有子代理等待）
  - `verify/worktree`：只有 `before_side_effect` + `after_wait`
- **4 类 operation_class**：`read_only` / `managed_write` / `external_side_effect` / `destructive_hardware`
- **6 类失败分类**：`retryable_transport` / `capability_unavailable` / `deterministic_failure` / `policy_schema_security` / `ambiguous_side_effect` / `destructive_risk`
- **唯一执行账本**：`.ico_events.jsonl`（哈希链）；`snapshot` 只是可重建视图

固定执行顺序（每个步骤都必须走完，缺一即 fail-closed 拒绝伪成功）：

```bash
step --phase start            → 取回 attempt
step --phase check --boundary <...> --attempt <a>   （写/等/副作用/转换前复检）
artifact --step <s> --attempt <a> --path <p>        （每个落盘产物）
step --phase finish --outcome <success|failure|degraded|blocked|skipped>
```

---

## 3. 缺口分析：为什么还需要 `icode` 仓

| 能力 | `icode-skill` 现状 | 缺口 |
|---|---|---|
| 流程定义 | ✅ `steps/*.md` 29 个，成熟 | 无 |
| 状态/门禁 | ✅ `icode_control.py` + `gates.json`，极严 | 无 |
| 模型调用 | ⚠️ 仅 `openai-responses` 一个真 backend（+ `fake`） | 缺 Anthropic / 本地 / 兼容层 |
| **工具循环（Tool Loop）** | ❌ **0 实现** | **这是核心缺口** |
| **Tool Gateway** | ❌ 全仓仅 `agent_runtime/README.md:110` 一句承诺 | 未落地 |
| 自主推进工单 | ❌ 明确"不自动推进 status"、"不替代宿主主会话" | 未开放 |
| 独立跑完 1→6 | ❌ 必须宿主 LLM 在场 | 需要 Agent 运行时 |
| 本地 UI | ✅ `ui_server.py`（127.0.0.1，安全边界写得很扎实） | 可复用/对接 |

`agent_runtime/README.md` 的两句原文是本次预研最重要的证据：

> "UI 本身不解释模型 tool call；真实 ICODE 工具使用由 Codex/Claude Code 及既有步骤规则约束。"
> "后续工具循环必须经过 Tool Gateway、`operation` 回执和副作用审批后再启用。"

**设计者自己留了口子，而 `icode` 仓正好可以填它**——这也解释了为什么会有两个仓库而不是一个。

---

## 4. 三个候选定位（含取舍）

### 方案 A：自主 Agent 运行时（Standalone CLI）⭐ 推荐

`icode` = 一个可独立运行的 CLI：`icode run "给 calc 加 xxx" --project ../icode-skill/demo`

- 自带 LLM backend 抽象 + **Tool Loop**（read / write / edit / grep / glob / bash）
- 流程真源读 `icode-skill/steps/*.md`，门禁全走 `icode_control.py`
- 复用 `record-agent-spawn / record-agent-result` 向控制面报到（**这条通道已经存在**）
- 优点：真正补齐缺口；能脱离宿主；demo 可自动化验收；与 icode-skill 单向依赖、不侵入
- 代价：工作量最大；要自己实现工具沙箱、token/成本控制、人在环降级

### 方案 B：宿主编排器（Orchestrator）

`icode` 只做调度器：解析意图 → 决定下一步 → 通过 `host_runner` 调 Claude/Codex CLI 执行。
- 优点：工作量小，天然复用宿主能力，风险低
- 缺点：**没有自主性**，本质仍是 `agent_runtime` 的加强版，agent_runtime README 已经把这条路定为"不替代宿主主会话"；产品壁垒弱

### 方案 C：把 Tool Gateway 直接补进 `icode-skill`
- 优点：架构最正统（就是它自己声明的下一步）
- 缺点：**与"在 icode 仓开发"的诉求冲突**；会把已经很庞大的 icode-skill 继续撑大（SKILL.md 已 46KB）

**推荐 A**，并把 A 中的 Tool Gateway 设计成未来可回填 C 的形态（接口对齐 `operation` 回执 + 副作用审批）。

---

## 5. 技术选型建议

| 维度 | 建议 | 理由 |
|---|---|---|
| 语言 | **Python 3.11+** | 与 `icode-skill` 同栈；可直接 import/子进程复用 `icode_control.py`、`gates.json`；`agent_runtime` 已是 Python；本机已有 3.13.12（managed） |
| LLM 接入 | 复用 `agent_runtime/icode_agent/backends/` 抽象（`base.py` 仅 ~900B），新增 anthropic / openai-compatible / 本地 | 不重写；`fake` backend 让离线 E2E 成为可能 |
| 工具集 | 最小集：`read / grep / glob / write / edit / bash` | 对齐 `references/host_adapters.md` 的"抽象操作"表，宿主无关 |
| 状态 | **一律不新造**，全走 `icode_control.py` | 控制面是唯一真源，绕过即破坏 fail-closed |
| 前端 | 一期不做；二期复用/对接 `ui_server.py` | UI 已有 38KB 实现且安全边界严密，不要重复造 |
| 依赖策略 | 从 `icode-skill` **只读引用**（路径配置/submodule），不拷贝 | 避免流程真源分叉 |

---

## 6. `demo/` 作为验收靶场：可行，但有三个坑

**可行的部分**
- 纯 C、无外部依赖，`make test` 有 6 条确定性 grep 断言 → 天然的"改了有没有坏"判定信号
- README 官方示例就是 `/icode fast "Add isqrt function to calc.c"` → 场景与作者意图完全对齐
- `.gitignore` 已排除 `/demo/.icode_output/`，跑脏了不会污染仓库

**必须先处理的三个坑**

1. **demo 已经被跑过一轮，官方示例需求已实现。**
   `calc.c` 里 `calc_sqrt` 与 `calc_isqrt` 都已存在（`calc_isqrt` 是转发 `calc_sqrt` 的兼容别名），`main.c` 也有对应用例。
   → E2E 必须换一个新需求，否则 Agent 会"发现已存在"直接收尾，验收不到真实编码路径。
   建议换成**未被实现**且**可断言**的需求，例如：`calc_fact` 系列已有、`calc_power` 已有 → 可考虑 `calc_gcd` / `calc_lcm` / 表达式 `calc_eval` 增强。

2. **本机没有 gcc / make。**
   `which gcc` 失败 → `make test` 当前跑不起来。
   → 需要 MSYS2 / MinGW / TDM-GCC，或改用 Windows 上可用的编译链；否则 E2E 只能验证到"产出代码"为止，验证（verify）阶段必须降级声明。

3. **Makefile 依赖 `rm` / `grep` 等 Unix 工具**（Git Bash 可满足，但 PATH 需要显式配置）。
   本机 Bash 环境当前 PATH 不完整（`ls`/`head` 都找不到），需先修复或统一走 PowerShell。

---

## 7. 风险与硬约束

| 风险 | 说明 | 建议 |
|---|---|---|
| **网络不可达** | 本机 DNS 无法解析 github.com，`git push` / `ls-remote` 均不可用 | 先本地开发；需要推送时请确认网络/代理 |
| **门禁极严** | fail-closed：缺 required_outputs / 缺 Read / 源码漂移一律拒绝 success，只能 degraded 或 blocked | Agent 必须实现"证据收集"而非"生成文本"；先做 `fake` backend 的契约测试 |
| **步骤 prompt 极重** | `01_plan.md` 67KB、`log.md` 146KB、`08_patch.md` 70KB | 必须有懒加载/裁剪策略，否则单步成本失控 |
| **副作用不可盲重放** | 同名副作用动作只有 start 无 finish → 再 start 返回 `ambiguous_side_effect` | Tool Loop 的每个写操作必须包 `operation` 回执 |
| **身份/版本漂移** | Reactive 边界复检会在写前重新算摘要，漂移即 blocked | Agent 修改代码后必须终结旧 attempt 并 restart，不能"强制接受" |
| **定位歧义** | "icode 主打使用 icode-skill，即 demo" 有至少两种读法 | 见下方待确认项 |

---

## 8. 待你确认的三件事

1. **定位**：方案 A（自主 Agent 运行时）/ B（宿主编排器）/ C（回填 icode-skill）？
2. **与 icode-skill 的耦合方式**：运行时按路径只读引用 / git submodule / vendored 拷贝快照？
3. **demo 的角色**：只当验收靶场（保留在 icode-skill 里）/ 复制一份到 icode 仓自带 / 换一个非 C 的靶场（规避 gcc 缺失）？

---

## 9. 建议的第一步（确认定位后即可执行）

```text
Step 1  立骨架：Python 包 + CLI 入口 + icode-skill 路径解析 + backend 抽象（先只接 fake）
Step 2  契约握手（不调真模型）：用 fake backend 跑通 plan 步骤的
        step start → check(before_write) → artifact → finish 全链路，
        并用 icode_control.py trace 验证事件链正确
Step 3  真模型 + Tool Loop 最小集（read/grep/edit/bash），在 demo 上跑一条
        "新增 calc_gcd" 的 fast 流程，用 make test 扩展断言验收
```

第 2 步是关键里程碑：**它能在完全不花钱、不联网的情况下证明"我们的 Agent 与控制面对齐"**。
