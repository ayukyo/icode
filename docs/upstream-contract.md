# 上游契约依赖面（icode-skill）

- 首次探测：2026-09-23；当前接入与安装边界复核：2026-10-08
- 对应决策：**A3** —— 上游无契约稳定性承诺，因此依赖面必须文档化 + bump 时冒烟测试
- 当前 pin：`vendor/icode-skill` @ `1693651c1bd7daad3272eb054f0f81d6f254d08d`；固定 gitlink，升级需独立验收，不在用户运行时拉取main。

下文Phase1/2探测保留历史语境，不表示当前R2/R3只剩推理门禁；最新进度见[路线图](./roadmap.md)。

---

## 1. 我们只读消费的上游面

| 类别 | 路径 | 用途 |
|---|---|---|
| 契约真源 | `mcp/workflow-gate/gates.json` | 步骤契约 / 边界 / 操作类别 / 失败分类 / 状态机 / 门禁策略 |
| 流程文档 | `steps/*.md`（当前27个） | 步骤流程合同；**渐进披露**的懒加载对象 |
| 控制面 | `tools/icode_control.py` | 唯一写入口，以子进程 CLI 方式调用 |
| 推理门禁真源 | `mcp/reasoning-gate/gates.json` | 各步骤默认思考等级与是否 `requires_trace` |
| 参考文档 | `references/*.md` | 按需查阅（不由本仓自动加载） |
| 控制面依赖 | `tools/inspection_worklist.py`、三个 `tools/lint_*.py` | 动态检查清单与三个固定Python门禁；当前解释器/UTF8执行 |

**本仓永不修改以上任何文件**（D3：两仓完全独立）。

### 安装后的运行资源

开发从固定子模块读取；wheel与sdist携带72个原字节机器运行成员，清单见[固定资源manifest](../src/icode/skill_runtime_manifest.json)。安装后默认发现包内资源，显式参数/env/local高级来源保留。默认入口解析时先校验全部成员；缺失或损坏不偷偷回退HOME。随后调用沿用可信Settings与CP，不声称每次调用原子认证或OS只读。

资源只读消费，工单和事件仍只写任务目录；CP使用当前Python的 `-B -X utf8`，三固定校验器在上游使用同一解释器。真正动态inspection/三gate及工作台通过离仓直接wheel和sdist重建安装验证；安装不运行上游install/MCP同步器，也不将指南中的43个候选外引用等同已支持完整SKILL。受限PPT模板和预览未分发，72成员不是90%能力分母。

### 1.1 明确**不消费**的上游面（D13）

| 不消费 | 原因 |
|---|---|
| `/icode <step>` slash 命令（`integrations/codebuddy/commands/icode.md`） | 那是**给宿主 LLM 的入口**（宿主理解后自己执行步骤）。本仓自带 Tool Loop，本身就是执行者，再引入一层"请别人执行"会产生两个写者 |
| `install.sh` | 它把 skill 与 MCP 装进宿主机；本仓只读消费固定子模块/包内资源，不执行该安装器 |
| `agent_runtime/`（ICODE Manager UI 与 host_runner） | 它是"通过宿主 CLI 执行受控步骤"的管理入口；我们的 UI 要展示 Tool Loop 实时过程，不走它 |

**保留消费的**：流程语义（`steps/*.md`）、门禁真源（两个 `gates.json`）、控制面 CLI。
即：**用它的"法规"，不用它的"命令桥"。**

---

## 2. 调用的子命令与读取字段

### 2.1 子命令（Phase 1 实际使用）

| 子命令 | 用途 | 是否必需 |
|---|---|---|
| `create` | 原子创建 vNext 工单 + 出生事件 | ✅ |
| `step --phase start/check/finish` | 步骤端口、边界复检、终结回执 | ✅ |
| `artifact` | 登记产物路径与 hash | ✅ |
| `transition` | 状态流转（门禁在此触发） | ✅ |
| `trace` | 只读事件链与未闭合投影 | ✅ |
| `validate` | 工单整体校验（降级使用） | 可选 |
| `check-outputs` | 步骤产物合同检查 | 可选 |
| `resolve-ticket` | 工单身份解析 | 可选 |
| `policy` | 副作用感知 Retry/Fallback 决策 | P2 起 |

### 2.2 我们依赖的输出字段（**上游若改名即破坏兼容**）

| 字段 | 出现位置 | 我们如何使用 |
|---|---|---|
| `ok` | 所有命令 | 成功判定 |
| `ticket_id` / `status` / `out_dir` | `create` | 建单结果与身份 |
| `attempt` | `step --phase start` | 后续所有调用的关联键 |
| `result` | `step --phase check` | `pass` / `blocked` 判定与回流 |
| `event_id` | 写入类命令 | 事件确认 |
| `event_count` / `events` | `trace` | 事件链验收 |
| `open_steps` / `open_operations` / `open_agents` | `trace` | **未闭合项必须为空**（Phase 1 验收项） |
| `fail_closed` / `failed_gates[]` / `error` | `transition` 失败响应 | 门禁拦截的如实上报 |

### 2.3 事件类型（我们断言存在的）

`ticket_created`、`step_started`、`gate_checked`、`artifact_written`、`step_finished`

> 注意：事件名与字段名都是**上游内部约定**，没有 semver 保证。
> 因此每次 bump 子模块必须重跑 `python -m unittest`，其中 `tests/test_handshake.py`
> 就是那道**冒烟测试**。

---

## 3. 门禁深度探测结果（Phase 1 的重要发现）

`transition --to plan_done` 是 **gated target**：要依次通过三个 strict linter
（`gate_policy.gated_targets` 定义），任一失败即 fail-closed。

对一个**只有产物、没有真实推理证据**的探测件，实测被两个门禁拦下：

| 门禁 | 拦截原因 | 上游要求的证据 |
|---|---|---|
| `thinking_gate` | `plan` 的 `requires_trace=true`，而缺 `.thinking_gate_trace.jsonl` 最终行 | 每 step 一行 trace，schema 见 `references/thinking_detail.md`「thinking gate trace」段；`tier` 必须 ≥ `default_tier`（plan 默认 **L2**），`mechanism` 词表受限 |
| `workflow_contract` | strict 模式要求 `metadata.semantic_decisions` 与 `metadata.requirement_deltas` | 两个 metadata 数组；`semantic_decisions[].status` 有词表约束，`resolved` 必须带 `selected` |

`mcp_coverage` 在本次探测中通过。

### 这条发现的意义

**门禁在正确工作**：它拒绝了一个"流程走完但没真思考"的工单前移。
这正是本项目「过程可审计」的核心价值 —— 所以 Phase 1 **不伪造 trace 去凑前移**，
而是把缺口如实记录（见 `icode handshake` 的「状态前移」段）。

### 2026-09-23 复测（Phase 2 真模型）

接入真模型后再测：**步骤契约本身已完全走通**（`step start → check → artifact → check → finish success`，
事件链 24 条无未闭合），但 `transition --to plan_done` 仍被同样两个门禁拦下。
即：**当前瓶颈只剩推理门禁这一项**，契约与状态机部分已对齐。

---

## 4. Phase 2 待补清单（由上述探测得出）

| # | 项 | 说明 |
|---|---|---|
| 1 | 写 `.thinking_gate_trace.jsonl` | 每步一行，需真实判定 tier 与触发原因；**不得伪造**——没做 L2 就如实标 `degraded` 并给 `degraded_reason` |
| 2 | `metadata.semantic_decisions` | 本步待裁决语义决策；无则显式写空数组（"本步无待裁决决策"是合法声明） |
| 3 | `metadata.requirement_deltas` | 需求偏移记录 |
| 4 | 推理门禁真源读取 | 从 `mcp/reasoning-gate/gates.json` 取 `default_tier` / `requires_trace` / 升级触发器，**不写死等级** |
| 5 | 过渡到 `in_progress` 态不需要 linter | 可先验证状态机合法性路径，再逐步补齐门禁 |

---

## 5. bump 子模块的标准动作

```bash
# 1) 更新引用（浅克隆，耗时约数分钟）
git submodule update --remote --depth 1 vendor/icode-skill

# 2) 冒烟：契约握手 + 全量测试（离线，零成本）
python -m unittest
PYTHONPATH=src python -m icode.cli doctor

# 3) 关注点：doctor 的「契约与 steps/ 不一致」与「控制面可执行」两项
#    以及 tests/test_handshake.py 的门禁拦截断言

# 4) 全部通过后提交新的 gitlink
git add vendor/icode-skill && git commit -m "chore: bump icode-skill to <sha>"
```

**若冒烟失败**：不要在本仓打补丁（D3）。改为在上游仓库独立修复，或暂时回退到上一个可用 gitlink。

增加随包资源后，bump还须审许可及成员边界、更新全部原字节hash/固定manifest身份，再运行正式setuptools>=80的包安装测试、sdist离仓重建和完整preflight。Windows检出固定资源必须保留Git原字节；CI只在checkout步骤使用command-scope core.autocrlf=false，不修改用户全局配置或打包时归一化。异平台安装与完整隔离验收仍单列，不用本机安装通过关闭R2/R3。
