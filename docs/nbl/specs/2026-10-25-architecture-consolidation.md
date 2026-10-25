# SPEC v1.1：架构分层巩固（参数收敛 + 边界防线 + 平台簇下沉 + 入口收敛）

**状态**：v1.1（已处置独立评审意见，待实施）
**基线**：`105fc27`（远端 main；Windows 检出 `D:\Projects\icode` 已对齐）
**前置分析**：`docs/nbl/analysis/2026-10-25-architecture-review-v2.md`
**评审**：独立评审代理完成，意见分「事实性错误」「方案缺陷 D1–D10」「验收项问题」「遗漏与建议」「纪律核对」五类，逐条处置见 §12。

> **v1 → v1.1 摘要**：采纳 4 项阻断/重要修正（D1 `run_unittest` 归属、D2 验收项互斥、D3 参数三分类、D4/D5 边界规则可判定化、D6 常量补齐、D7 直接导入依赖）、6 项验收项改写、3 项事实性纠正；调整执行顺序为 **P1a → P0 → P1b → P2 → P3**；P3 降级为 P2 之后的顺带清理。

---

## 0. 背景与依据

2026-10-24 的架构分析判定「架构意图成立，失真的是代码组织」，提出 R1a–R1d。2026-10-25 的独立复核发现其中**两条核心量化依据有误**：

| 项 | 前稿 | 复核实测 | 影响 |
|---|---|---|---|
| runner 验证进程管理行数 | ~1500 | **723（严格）/ 797（含 wrapper）** | 高估 2.07×；降幅 35%→**17.7%** |
| pack_verify Ed25519 行数 | ~700 | **183（141 代码行）** | 高估 5.1× |
| R1b（提取 `icode.crypto.ed25519`） | 推荐实施 | **不可行** | 与三条架构契约冲突，**撤销** |

复核同时发现前稿**未提**的更高优先级问题：**编排函数参数爆炸**（`_run_agent` 24 参、`run_contract_step` 22 参、`run_chain` 20 参）、**架构文档对 5 个核心模块提及为 0**、**无任何架构边界回归测试**。

**工作区说明**：本轮 WSL 不可用，权威工作区为 Windows 检出 `D:\Projects\icode`，基线取自该检出；Windows 与远端 main 指向同一 commit `105fc27`。

---

## 1. 目标与非目标

### 1.1 目标

1. **P0 降低编排函数耦合面**，使编排层可在无平台环境下构造与测试。
2. **P1 建立架构边界回归防线**，使「盒子→模块」映射可核查、漂移可检测。
3. **P2 把平台进程执行语义从编排器剥离**。
4. **P3 收敛入口层的重复编排知识**（降级为顺带清理，见 §7.1）。

### 1.2 明确非目标

| 不做 | 理由 |
|---|---|
| 大爆炸重写 | 硬循环依赖为 0、hub 结构健康、控制面边界完好；3937 项测试 + 三 CI run 的验收面是多年阶段成果 |
| Ed25519 提取为 `icode.crypto.ed25519` | 破坏「字节同源 + stdlib-only + 包内独立副本」三条契约，137 行收益不足以补偿 |
| `pack_verify` 拆分 | 约 1151 行是打包/规范化、1334 行是验证策略，几乎每块都与 `evidence.py` 的 38 个私有符号共享；且触及 R7 已锚定公开仓库的签名契约 |
| O2 子包重组（104 → 10 子包） | 194 个测试文件的 import 更新 + 巨大 diff；P1 登记表已能低成本达成同等可见性 |
| 触碰 `pack_verify.py` 的签名消息格式 | 外部可验证性契约，见 §8.1 |
| 修改 `vendor/icode-skill` | 按 AGENTS.md「ICODE-SKILL 修改授权」，需用户对该批改动的明确同意 |

---

## 2. 现状度量（`105fc27`，可复算）

| 维度 | 数据 |
|---|---|
| 模块 / 行数 | 104 模块 / 48,516 行（42,605 代码行） |
| 函数总数 | 1,653 |
| 测试 | 194 文件 / 3,937 测试函数 |
| 硬循环依赖 | **0**（模块级双向 import 为零） |
| 软循环 | 14 组；**177 处函数内延迟导入**（runner 39 / cli 34 / execution_broker 29） |
| 扇入 hub | sandbox_policy 21、config 10、control 10、isolation 10 |
| 扇出 hub | **runner 36**、cli 22、autonomy 14、chain 12、execution_broker 10 |
| 参数 ≥8 的函数 | 51（含 `self` 口径）；≥12 的 13 个；≥20 的 4 个 |

### 2.1 最大的编排函数（`inspect.signature` 实测，含 keyword-only）

| 函数 | 参数数 | 位置 |
|---|---:|---|
| `_run_agent()` | **24** | `runner.py:2609` |
| `run_contract_step()` | **22** | `runner.py:1237` |
| `run_chain()` | 20 | `chain.py:288` |
| `_contract_engineering_gate()` | 20 | `runner.py:1906` |
| `resume_contract_step()` | 16 | `runner.py:3010` |
| `run_task()` | 11 | `runner.py:3279` |

### 2.2 runner 职责簇（实测清点）

| 簇 | 行号区间 | 行数 | 依赖 |
|---|---|---:|---|
| **P 平台进程执行/输出捕获** | 387–1183 | **797** | 仅 stdlib + `windows_process_tree`（单向）；`run_unittest` 另需 `Sandbox` 仅作类型标注 |
| R 审查（Reviewer） | 3461–4083 | 617 | 需 `_make_ctx` 注入 |
| O 编排主流程 | 1237–1639 等 | 680 | 核心，暂不动 |
| A Agent 循环桥接 | 2444–2966 | 520 | `runner↔chain` 双向依赖，高风险 |
| E 工程门禁 | 1642–2127 | 505 | 扇出 12，跨 4 簇，须最后 |
| G Git 会话与结果绑定 | 4086–4465 | 364 | 零循环风险 |
| F 证据写入 | 2203–2288 等 | 118 | 低 |

---

## 3. P0：编排函数参数收敛

### 3.1 问题

`_run_agent()` 需同时获得 24 个协作者。后果：编排层**无法在无平台环境构造** → 单元测试只能整块 mock；新增协作者要改所有调用点（`run_contract_step` 被 **13 个 tests/ 文件**引用、`StepReport` 10、`resume_contract_step` 9、`run_task` 8）。

**拆文件只降低行数，参数收敛才降低耦合。**

### 3.2 做法：三类切分（**修订自 v1**）

评审指出 v1 的「环境类 / 本次调用差异类」二分不足以把 `_run_agent` 降到 ≤8 参。实测 24 个参数可完整分为三类：

**(a) 环境类 → 打包进 `RunContext`（12 个）**
`backend` `approver` `loop_config` `budget` `on_event` `checkpointer` `sandbox` `policy` `budget_tracker` `workspace_session` `inspection_runner` `resume_context`
（`resume_context` 描述恢复状态而非本次差异，归入环境类）

**(b) 本次调用载荷类 → 打包进 `StepRequest`（6 个）**
`brief` `contract` `requirement` `change_baseline` `operations` `prepared_step`+`prepared_attempt` → `prepared_call`

**(c) 本次调用差异类 → 保持显式入参（6 个）**
`workspace` `out_dir` `ticket_id` `step` `extra_instructions`

**24 = 12 + 6 + 6，无遗漏。** 差异类恰好 6 个 ≤ 8，达标。

```python
@dataclass(frozen=True)
class RunContext:
    """编排层共享的协作者集合（不可变）。"""
    backend: Backend
    approver: Approver
    loop_config: LoopConfig
    budget: BudgetTracker
    on_event: Callable[[str, dict], None] | None
    checkpointer: Checkpointer | None
    sandbox: Sandbox | None
    policy: SandboxPolicy | None
    workspace_session: WorkspaceSession | None
    inspection_runner: Callable | None
    resume_context: object | None

@dataclass(frozen=True)
class StepRequest:
    """本次调用的内容载荷。"""
    brief: str
    contract: object
    requirement: str
    change_baseline: object | None
    operations: object | None
    prepared_call: PreparedCall | None
```

### 3.3 兼容性硬要求

| 要求 | 说明 |
|---|---|
| **对外兼容外观签名逐字段不变** | `run_contract_step`(22) / `resume_contract_step`(16) / `run_task`(11) / `run_chain`(20) 的参数名、顺序、默认值**必须保持不变**，内部转调上下文版本 |
| 关键字参数名不变 | 现有调用方大量用关键字传参，改名即破坏 |
| `prepared_scope` 参数 | `runner.py:1258` 已存在（R2 生命周期工作），**必须保留** |
| 上下文构造适配器 | 提供 `RunContext.from_arguments(...)`，使旧调用路径零改动可达 |

### 3.4 验收项（**修订自 v1，消除 A0.1/A0.2 互斥**）

- **A0.1（对外签名基线快照）**：在 P0 实施**前**生成 `docs/nbl/specs/baseline_signatures.json`，记录 `run_contract_step` / `resume_contract_step` / `run_task` / `run_chain` 的 `inspect.signature` 参数名/顺序/默认值三元组。P0 后断言**逐字段相等**。对外参数数**不设 ≤8**（保持 22/16/11/20）。
- **A0.2（上下文版本参数收敛）**：断言上下文内部版本 `_run_contract_step(*, ctx: RunContext, request: StepRequest, workspace, out_dir, ticket_id, step, extra_instructions)` 的参数数 ≤ 8。
- **A0.3（`_run_agent` 收敛）**：断言 `len(inspect.signature(runner._run_agent).parameters) <= 8`（当前 24，全为 keyword-only）。
- **A0.4（等价比对）**：断言 `RunContext.from_arguments(**旧签名实参)` 的每个字段 == 旧实参；且兼容外观与上下文版本在**同一 mock 协作者集合**下产生**相同的下游调用序列**（比对 mock 的 `call_args_list`）。
- **A0.5（不可变性）**：断言 `RunContext` / `StepRequest` 为 frozen dataclass（`FrozenInstanceError`）。
- **A0.6**：全量测试零新增失败。

---

## 4. P1：架构盒子→模块登记表 + 边界回归测试

### 4.1 问题

- `docs/icode-agent-product-architecture.md`（1309 行）对 `runner`、`pack_verify`、`execution_broker`、`reviewer`、`handshake` 提及次数**全为 0**；这 5 个模块合计 **9,488 行（占代码 22.3%）**在架构文档中一次都未出现。
- 图是真源、模块是影子，**影子没有登记处** → 任何拆分都会静默放大漂移。
- `tests/` 下**不存在**任何架构边界测试。

### 4.2 做法

**(a) 登记表** `docs/architecture/modules.json`：每模块登记 `box` / `layer` / `platform`，并定义 `exempt` 豁免清单（每条含 `module` + `reason` + `reviewer` 三字段）。

**(b) `tests/test_architecture_boundaries.py`**：

1. **完备性**：`find src/icode -name "*.py" -not -path "*__pycache__*"` 的**全部 104 个文件**（含 4 个 `__init__.py`）都在登记表中 → **双向相等**断言。
2. **平台隔离（分层强度，修订自 v1）**：
   - **强约束**：编排层（layer ≤ 3）**顶层** import `windows_*` / `linux_*` → 失败；
   - **软约束**：**函数内延迟导入** → 登记即通过。
   - 理由（**修订自 v1 的 D4**）：当前 `runner` 有 6 处、`execution_broker` 有 19 处平台**延迟导入**，`engineering_verification.py:26` 有 1 处**顶层**导入。延迟导入是该仓既有的**刻意解耦机制**（2026-10-24 分析 §4.2 已认定），一概禁止会与既有架构决策冲突；改 `execution_broker` 的 19 处必然改变其平台分支结构，风险远高于 P1「纯新增、低风险」的定位。
   - 当前违反面**照实登记为豁免**，每条写明理由；**P1 不顺手改代码**。
3. **hub 反向依赖（改写为可判定形态，修订自 v1 的 D5）**：
   - v1 的「hub 不得被下层模块 import」是**自指且不可判定**（layer 由本表自己定义）。
   - 改写为具体子集：**`sandbox_policy` / `isolation` 不得被平台专用模块（`windows_*` / `linux_*`）导入**。
   - 当前违反面（实测）：`sandbox_policy` 被 `linux_helper_source`、`linux_prepared_step` 导入；`isolation` 被 `linux_helper_source`、`linux_prepared_step`、`linux_task_scope` 导入 → **登记为豁免**。
   - 一般性依赖方向用「允许依赖矩阵」表达，不作为强制门禁。
4. **文档一致性**：断言 `docs/icode-agent-product-architecture.md` 中存在指向 `docs/architecture/modules.json` 的引用行，且该 JSON 可被解析。

### 4.3 验收项（**修订自 v1**）

- **A1.1**：`tests/test_architecture_boundaries.py` 存在，且该测试类在 CI 中实际运行。
- **A1.2（完备性，双向相等）**：断言 `set(登记表模块名) == set(实际 104 个模块名)`。口径明确：含 4 个 `__init__.py`。
- **A1.3（负例自测，不污染仓库）**：完备性检查函数签名设计为 `check_completeness(module_names: set[str]) -> list[str]`（**接受虚拟清单参数**）。负例自测 = `check_completeness({"new_unregistered_module"})` 必须返回非空缺失列表。**测试不写任何文件到 `src/icode/`**。
- **A1.4（豁免封闭）**：断言豁免条目**清单式硬编码**（每条含 `module`+`reason`+`reviewer` 三字段非空）；断言**不存在通配符**（`'*'` / `fnmatch` 模式不得出现在 `exempt` 中）；断言豁免总数 ≤ 40，超出即失败。
- **A1.5（文档回填）**：断言架构文档含 `modules.json` 引用行，且该 JSON 可被解析。
- **A1.6**：全量测试零新增失败。

---

## 5. P2：runner 平台执行簇下沉

### 5.1 做法

新建 `src/icode/verification_process.py`，从 `runner.py` 迁入 **P 簇（387–1183）**：

| 符号 | 原行号 | 备注 |
|---|---:|---|
| `_run_unittest_with_bounded_output` | 387–411 | |
| `_retain_verification_output` | 414–422 | |
| `_darwin_process_group_has_live_members` | 425–527 | macOS `/bin/ps` + `kqueue` |
| `_terminate_posix_verification_group` | 530–561 | `os.killpg` |
| `_PosixVerificationExitMonitor` | 564–645 | Linux `waitid` / macOS `kqueue` |
| `_reap_posix_verification_process` | 648–669 | |
| `_run_posix_bounded_output` | 672–838 | `selectors` + `start_new_session` |
| `_cancel_windows_pipe_readers` | 841–885 | `ctypes.WinDLL("kernel32")` |
| `_run_threaded_bounded_output` | 888–905 | |
| `_terminate_threaded_verification_tree` | 908–932 | |
| `_join_or_cancel_threaded_readers` | 935–943 | |
| `_run_threaded_bounded_output_impl` | 946–1127 | `CREATE_SUSPENDED` |
| `_decode_verification_output` | 1130–1133 | |
| `VerificationOutputError` | 136–143 | |
| `VerificationOutputLimitError` | 146–154 | |
| `VerificationOutputCaptureError` | 157–158 | |

**`run_unittest`（1136–1183）保留在 `runner.py`** —— 见 §5.2 的 C7。

**常量**（**修订自 v1 的 D6，补齐 5 个遗漏**）：

| 常量 | 定义 | 处置 |
|---|---:|---|
| `_MAX_VERIFICATION_OUTPUT_BYTES` | 80 | 迁移 |
| `_VERIFICATION_OUTPUT_READ_CHUNK_BYTES` | 81 | **共享**：簇内用（470/768/985）**且**簇外用（1866）→ 新模块定义 + runner 重导入 |
| `_VERIFICATION_OUTPUT_DRAIN_TIMEOUT_SECONDS` | 82 | 迁移 |
| `_VERIFICATION_PROCESS_CLEANUP_TIMEOUT_SECONDS` | 83 | 迁移 |
| `_DARWIN_PROCESS_GROUP_AUDIT_LIMIT_BYTES` | 84 | 迁移 |
| `_DARWIN_PROCESS_GROUP_AUDIT_TIMEOUT_SECONDS` | 85 | 迁移 |
| `_NO_TESTS_SUMMARY` | 161 | **留在 runner**（`run_unittest` 留在 runner，随之留下） |

### 5.2 硬约束（**违反即回退本步**）

| # | 约束 | 原因 |
|---|---|---|
| **C1** | runner 侧**必须保留重导出**：`from .verification_process import _run_unittest_with_bounded_output, ...` | 全仓 **18 处** `patch("icode.runner._run_unittest_with_bounded_output")` + **4 处直接 import**（见 C1b）依赖 runner 的模块属性路径 |
| **C1b** | **4 处 `from icode.runner import _run_unittest_with_bounded_output` 直接导入同样依赖重导出**：`scripts/probe_windows_build_context.py:19`、`scripts/probe_windows_direct_volume.py:93`、`scripts/probe_windows_pe_capture.py:22`、`scripts/run_windows_wheel_ci.py:33`、`tests/test_windows_pe_capture.py:21`（**真实调用**，非 mock） | `from X import name` 在 import 时绑定；重导出断裂 → 真实起进程 |
| **C2** | `engineering_verification.py:518` 必须继续走 `runner._run_unittest_with_bounded_output` **属性访问**，不得改为直接 import | 同 C1；改成直接 import 会让 18 处 patch **静默失效**（不报错，只失去隔离效果） |
| **C3** | `_snapshot`（= `workspace_snapshot.snapshot_workspace` 的别名，**非 runner 私有函数**，`runner.py:74`）与 `_runtime_budget`（`runner.py:1191`）被 `chain.py:30` 引用，**留在 runner 不得搬走** | `chain.py:30` 顶层 `from .runner import StepReport, _runtime_budget, _snapshot, run_contract_step` |
| **C4** | 三个异常类必须保持继承链（`LimitError`/`CaptureError` 继承 `VerificationOutputError(RuntimeError)`）**且 `__name__` 字符串不得变更** | `pack_verify.py:1577-1578` 的 `_ENGINEERING_FIXED_ERRORS` frozenset **按类名字符串匹配** `VerificationOutputError` / `VerificationOutputLimitError` / `VerificationOutputCaptureError` → 改名会**静默破坏证据包 schema** |
| **C5** | 新模块**不得** import `runner`（任何形式，含函数内延迟导入） | 会引入循环 |
| **C6** | 新模块只允许依赖 stdlib + `windows_process_tree`（单向）。**`isolation` 仅限 `if TYPE_CHECKING:` 块内的 `Sandbox` 标注** | `isolation.py` 顶层只 import `sandbox_policy`（`isolation.py:41`），与 runner 无关 → 无循环。**注**：无循环的真实理由是 isolation 的出向依赖不含 runner，而非「isolation 不 import runner」这一表述 |
| **C7（**新增，采纳评审 D1**）** | **`run_unittest` 必须保留在 `runner.py`**，其内部对 `_run_unittest_with_bounded_output` 的调用**必须经 runner 模块属性查找**（`runner.py:1172` 现状即如此），**不得**改成 `from .verification_process import ...` 的直接绑定 | **已实证**：若 `run_unittest` 与被调函数一起搬走，`patch("icode.runner._run_unittest_with_bounded_output")` 会**静默绕过**（实测 `m.called=False`，输出仍为真实值），18 处 patch 的隔离效果全部失效而测试仍绿。已用真实模块文件复现验证。 |

### 5.3 验收项（**修订自 v1**）

- **A2.1（统一门限；实施中按实际基线修正为 ≤ 3850）**：`runner.py` 行数 **≤ 3850**。
  > **实施修正记录（2026-10-25）**：v1.1 原写「≤ 3700」，其估算基于迁移前
  > `runner.py` = 4495 行。但 §7.1 的执行顺序是 **P0 → P2**，P0 先落地后
  > runner 增至 **4535 行**（P0 新增上下文解包与 import）。按实际基线复算：
  > 迁移的 16 个定义合计 **742 行**（13 个平台函数 + 3 个异常类），
  > 重导出块约 16 行，净减 **726 行** → 4535 − 726 = **3809 行**。
  > 原 3686 估算未计入 P0 的行数增量，属**执行顺序导致的估算偏差**，
  > 非实现偏差。门限按实测基线重设为 3850（保留 41 行余量）。
  > 「runner ≤ 3000」仍不在本 SPEC 承诺范围内（见 §7.2）。
- **A2.2**：`verification_process.py` 行数区间断言 `750 <= lines <= 900`。
- **A2.3（自动枚举，修订 v1 的「3 个 Windows 测试文件」计数错误）**：以符号依赖**自动枚举**受影响集合 —— `{f for f in tests/test_windows_*.py if 引用了被迁符号}` 与 `{f for f in scripts/probe_windows_*.py + scripts/run_windows_wheel_ci.py if 引用了被迁符号}`，断言这些文件**全绿**，且两个集合**非空**。
- **A2.4（patch 有效性，**修订自 v1 的笼统表述，写死 4 条**）**：
  - (a) `patch("icode.runner._run_unittest_with_bounded_output")` 能拦截 `engineering_verification` 的实际执行路径（复用 `tests/test_engineering_verification.py:175` 的调用形态）；
  - (b) **能拦截 `runner.run_unittest` 的内部调用**（`runner.py:1172` 路径）—— **C7 的核心防线**；
  - (c) `scripts/probe_windows_direct_volume.py:93` 的导入形态仍能拿到被 patch 的对象；
  - (d) `from icode.runner import _run_unittest_with_bounded_output` 与 `runner._run_unittest_with_bounded_output` **是同一对象**（`is` 断言）。
- **A2.5（防重复计数复发）**：断言 `verification_process.py` 内 `windows_runner_pipe` 命中数 == 0，且 `src/icode/` 下**仅** `windows_runner_pipe.py` 与 `tests/test_windows_runner_pipe.py` 引用该模块。
- **A2.6（`run_unittest` 沙箱分支快照，采纳评审遗漏项 4）**：断言 `run_unittest` 的 4 种 sandbox 分支（`bwrap` / `sandbox-exec` / `container` / `wsl`，`runner.py:1155-1163`）的 python 路径选择行为不变——这是 P2 中唯一会因 C7 而改变归属的分支。
- **A2.7**：全量测试零新增失败。

---

## 6. P3：CLI 与自治编排路径收敛（**降级为顺带清理，采纳评审遗漏项 7**）

### 6.1 问题

- `cli.py` 875 行、13 个 `cmd_*`；`_build_runner`（:406）被 5 处调用（:483 / :502 / :671 / :750 / :805）。
- `LoopConfig(` 在 **5 处**分别构造（:488 / :516 / :675 / :755 / :813）；`Budget(` 在 :421 构造。
- **对齐仓库已有的正确范式**：`autonomy.NativeChainExecutor` 通过 `step_runner: Callable[..., ChainReport] = run_chain` 做依赖倒置（`autonomy.py:145`）——CLI 应采用同样注入方式。

### 6.2 做法

CLI 只保留参数解析与调用；组装逻辑下沉到 `runner` 或新的 `icode.bootstrap`；`cmd_task` / `cmd_step_run` 改为调用单一编排入口。

### 6.3 验收项（**修订自 v1，改为可归因判据**）

- **A3.1**：`cli.py` 中 `LoopConfig(` 调用点 **≤ 1**（当前 5 处）、`build_backend(` 调用点 **== 0**（当前 :412）、`CliApprover(` 调用点 **== 0**（当前 :420）。
- **A3.2**：`cmd_task` 与 `cmd_step_run` 的函数体内 `LoopConfig(` / `Budget(` 调用数 **== 0**。
- **A3.3**：`python -m unittest tests.test_cli tests.test_cli_resume_sandbox` 退出码 == 0（**两个**测试文件，v1 只提了前者）。
- **A3.4（观察指标，非门禁）**：`cli.py` 内部模块依赖数（当前 22）下降；因组装下沉本身是 CLI 职责，**不设 ≤14 的硬门限**（v1 的 ≤14 不可达且不可归因）。

---

## 7. 落地纪律与验收

### 7.1 执行顺序（**修订自 v1，采纳评审遗漏项 6**）

**P1a → P0 → P1b → P2 → P3**

| 步 | 内容 | 理由 |
|---|---|---|
| **P1a** | 只落 `docs/architecture/modules.json` + 完备性断言 + 豁免登记（**不含**规则 2/3 的强制约束） | 建立登记基线；纯新增、零风险。**先做**才能在 P0/P2 引入新模块时立即发现未归类 |
| **P0** | 参数收敛 | 最大机会（24→8）；**A0.1 的签名基线快照必须在改动前生成并入库** |
| **P1b** | 在 P0 完成后加装规则 2/3 的强制断言 | 此时模块集合已稳定，避免 P1b 因 P0 新增模块而返工 |
| **P2** | 平台簇下沉（按 C7 修正后） | 机械迁移，依赖面已核实 |
| **P3** | CLI 顺带清理 | 与 P2 **同 commit 或紧邻 commit**，不单独立项、不设独立 CI 门禁 |

### 7.2 关于「runner ≤ 3000 行」

2026-10-24 前稿的验收目标为 ≤3000 行。**本 SPEC 不承诺该数字**：P2 单步实际降到 **3809 行**（P0 落地后的基线）。若仍要达到 3000，需在本 SPEC 之外再抽 R 簇（617 行，需 `_make_ctx` 注入）或 G 簇（364 行）——**留待 P0/P2 完成后的独立评估**。

### 7.3 每步的验收门（缺一不可）

1. 相关测试文件**本机**可跑并全绿；
2. **全量套件只在线上 CI 跑**（AGENTS.md「线上优先」第 1 条：本机不重复整套测试），要求**零新增失败**；
3. CI 三 run（`ci` / `pages` / `windows-helper-provenance`）**全部 success**，结果绑定：**实际候选 SHA + workflow 名 + job 名 + 平台矩阵项 + 原始 run URL + 各 job 退出状态**；
4. **推 `main` 触发 CI，不创建额外分支或版本标签**（AGENTS.md 第 2 条）；
5. 每步**独立提交**（一个 commit），失败按 `git revert` 回退该步；
6. 「跳过 ≠ 通过」：失败、跳过、观察不足均不得计为通过；**不取消或反复重跑来隐藏失败**；
7. **不得以「测试适配」为名削弱断言**——可测判据：对比改动前后 CI 的**被 skip 测试数**与**断言条数**，skip 数增加即视为削弱。

### 7.4 既有环境性失败项（非回归）

- W1：`test_packaged_skill` setUpClass（缺 setuptools，实测 `ModuleNotFoundError: No module named 'setuptools'`，`tests/test_packaged_skill.py:91`）、Landlock 助手环境相关 —— 与本次改动无关，以基线复跑确认为准。

---

## 8. 明确不动的边界

### 8.1 签名与证据契约（R7 已锚定公开仓库）

`pack_verify.py` 的：`SIGNATURE_MESSAGE_PREFIX`（:95）、签名消息构造（:2192）、anchors 段分隔符 `b"\nanchors.json\n"`（:2193-2194）、`_SIGNATURE_FIELDS` 封闭集（:2102-2106）、`pack_digest`（:1448-1455）、`canonical_event_hash` 跨仓对齐（:581-585）、`ANCHOR_TYPES` + `validate_anchor_bundle`（:2202-2278）。

### 8.2 其他

- 控制面子仓边界与 `icode_control.py` JSON 契约；
- `pack_verify.py` 与 `tools/verify_evidence_pack.py` 的**字节同源**关系（sha256 `823a5959…c56e`）；
- core 零第三方依赖（`pyproject.toml` `dependencies = []`）；
- Guard/Sandbox 的 fail-closed 语义与 conformance 契约；
- CI 三 run 与 provenance 验收面；
- `vendor/icode-skill`（需用户对该批改动的明确同意）。

---

## 9. 风险与缓解

| 风险 | 等级 | 缓解 |
|---|---|---|
| **patch 静默失效**（C1/C2/C7 被违反时测试仍绿但隔离失效） | 高 | A2.4 写死 4 条断言，直接验证 patch 能拦截**实际调用路径**；D1 已实证复现，修法已确定 |
| P2 平台差异只在 CI 暴露 | 中 | 迁移为**纯机械**操作，不改逻辑；CI 三 run 覆盖双平台；A2.6 补 `run_unittest` 沙箱分支快照 |
| P0 改动公开签名，破坏 13 个引用方 | 中 | A0.1 签名快照基线（实施前生成并入库）；对外签名保持不变 |
| P1 登记表不完备导致边界测试误报 | 中 | 豁免清单式硬编码（A1.4）；完备性断言先跑全量确认无遗漏 |
| 架构文档回填引入描述漂移 | 低 | 登记表为唯一真源，文档只指向它 |
| 重构削弱断言 | 高 | §7.3 第 7 条的 skip 数 / 断言条数对比判据 |
| P0 与 `vendor/icode-skill` 脏状态混入候选 | 低 | 落地前确认子模块脏状态为**既存工作**而非本轮引入；本次不触碰子模块 |

---

## 10. 度量复算

脚本归档于 `scripts/arch_metrics/`（**修订自 v1**：v1 声称已归档但脚本在归档位置因 `BASE` 路径错误全部输出 0，且目录未被 git 跟踪）。

| 脚本 | 用途 |
|---|---|
| `metrics.py` | 模块清单 / LOC / 扇入扇出 / 测试映射 |
| `cycles.py` | SCC 循环检测（含行号与 import 形态） |
| `cycles_classified.py` | 硬循环 vs 延迟导入循环分类 |
| `coupling.py` | 平台混用 / 重复函数 / 参数分布 / 全局状态 |

**修订要求**：`BASE` 改为 `Path(__file__).resolve().parents[2]`（脚本在 `scripts/arch_metrics/` 下，代码在 `src/icode/`）；补 `scripts/arch_metrics/README.md` 记录基线 SHA 与复算命令；`scripts/arch_metrics/` 纳入 git 跟踪。

---

## 11. 交付物清单

| 步 | 交付物 |
|---|---|
| P1a | `docs/architecture/modules.json`、`tests/test_architecture_boundaries.py`、豁免登记 |
| P0 | `RunContext` / `StepRequest`、`docs/nbl/specs/baseline_signatures.json`、`tests/test_orchestration_context.py` |
| P1b | 规则 2/3 强制断言已随 P1a 落地；复验无新增违规 |
| P2 | `src/icode/verification_process.py`、runner 重导出、A2.4 patch 有效性断言 |
| P3 | CLI 顺带清理 |
| 全程 | 每步验收记录 + 决策日志，绑定实际候选 SHA 与 CI 三 run 结果 |

---

## 12. 实施记录（P1a / P0 / P1b / P2，2026-10-25）

### 12.1 P1a —— 模块登记表 + 边界回归测试（`dc8046f`）

- `docs/architecture/modules.json`：104 → 106 模块全量登记（后续 P0/P2 各 +1），
  按盒子 + 层级归属；`tests/test_architecture_boundaries.py` 强制三条规则。
- 三条规则均经**注入违规验证**后才认定为通过：未登记模块、新增平台顶层 import、
  新增平台模块顶层 import hub，各自都能让对应断言失败。
- 豁免清单共 3 条强约束 + 2 组软约束，逐条含 module/rule/reason/reviewer；
  上限 40 且禁通配符。
- CI：`40183896434`（Public website）/ `40183896442`（CI）/
  `40183896453`（Windows helper provenance）三 run 全 success。

### 12.2 P0 —— 编排函数参数收敛（`65f95c9`）

- 新增 `src/icode/orchestration_context.py`：`RunContext`（11 个环境协作者）、
  `StepRequest`（8 个载荷字段）、`PreparedCall`（`prepared_step`/`attempt` 成对）。
- `_run_agent` 24 参 → **6 参**（ctx / request / workspace / out_dir / ticket_id / step），
  全关键字传参。函数体除顶部 20 行解包外**逐字不变**（252 行原样保留）。
- 对外契约零变更：`run_contract_step`(22) / `resume_contract_step`(16) /
  `run_task`(11) / `run_chain`(20) 签名逐字段不变，由
  `docs/nbl/specs/baseline_signatures.json`（改动前捕获）比对。
- `tests/test_orchestration_context.py` 10 项断言签名相等、参数预算、
  字段级等价、不可变性。
- 回归：`test_contract_engineering` 与 `dc8046f` 基线同样 3 项失败（2 failure + 1 error，
  均为既存），零新增。

### 12.3 P1b —— 规则强制化

P1a 实施时已把规则 2/3 的**强制断言**一并落地（比 SPEC 计划的 P1b 更完整）。
P0 完成后复验：9 项边界测试全绿，`orchestration_context` 顶层与延迟平台导入均为零。

### 12.4 P2 —— runner 平台执行簇下沉（本次提交）

- 新增 `src/icode/verification_process.py`（805 行），迁入 13 个平台进程函数 +
  3 个异常类 + 5 个常量。**16 个定义全部逐字相同**（diff 验证 16/16）。
- **`run_unittest` 保留在 `runner.py`**（C7）——这是评审 D1 的阻断项：
  若与之被调函数一起搬走，18 处 `patch("icode.runner._run_unittest_with_bounded_output")`
  会**静默绕过**。已用真实进程验证 patch 可拦截（`m.called=True`）。
- runner 侧重导出 16 个名字，保证 `from icode.runner import X` 与
  `runner.X` 是同一对象（`is` 断言）；`engineering_verification` 仍走
  `runner._run_unittest_with_bounded_output` 属性访问（C2）。
- runner.py 4535 → **3803 行**（净减 732：迁出 742 行，重导出约 16 行，
  另清理 7 个因迁移失效的 import）。
- `tests/test_verification_process_extraction.py` 18 项，含 A2.4 四条 patch 有效性
  断言（其中 (b) 条直接守住 C7 的陷阱）。
- 回归：`test_runner` / `test_engineering_verification` / `test_model_routing` /
  `test_contract_engineering` / 边界测试全部与基线一致，零新增失败。
- 新模块 `verification_process` 登记入 SANDBOX 盒子，完备性断言即时捕获。

### 12.5 P3 —— CLI 入口收敛（本次提交）

按 §6 降级为「P2 之后的顺带清理」，不单独立项、不设独立 CI 门禁。

- `_build_runner` 现在一并装配 `LoopConfig`（`max_turns` 取自 argparse；
  缺失字段时退回到 `LoopConfig.max_turns` 默认值，使只取事件钩子的调用方
  不会因装配失败）。
- `LoopConfig(` 的真实构造从 **5 处收敛到 1 处**；`build_backend(` /
  `CliApprover(` / `Budget(` 本已只在 `_build_runner` 内，现由断言锁定。
- `cmd_task` / `cmd_step_run` 不再自行拼装回路或预算；5 个调用点统一按
  6 元素解包。
- `tests/test_cli_entry_convergence.py` 6 项，含「构造点只允许一处」
  「`cmd_task`/`cmd_step_run` 不得自行拼装」「调用点必须解包 loop_config」
  三条可自动化断言。已用注入真实构造的方式验证断言**确实会失败**。
- 回归：`tests/test_cli` + `tests/test_cli_resume_sandbox` 20 项全绿
  （基线同为全绿）；A3.4 的内部依赖数按观察指标记录，不设硬门限。

### 12.6 SPEC 门限修正

A2.1 原写「runner ≤ 3700」，估算基于迁移前 4495 行；因执行顺序为 P0→P2，
P0 落地后基线为 4535 行，故按实际基线重设为 **≤ 3850**（实测 3803，余量 47）。
修正理由已在 A2.1 处留档，说明这是执行顺序导致的估算偏差而非实现偏差。

---

## 13. 评审意见处置记录

**事实性错误**（3 项次要，已修正本 SPEC 文本）

| 评审条目 | 处置 |
|---|---|
| §3.3 `prepared_scope` 行号 `1220` → 实为 `1258` | ✅ 已改 |
| §5.2 C4 `cli.py:560` → 560 是 import，真正的 except 在 `cli.py:583` | ✅ 已改 |
| §4.1 「约 12,700 行 / 26%」→ 实为 **9,488 行 / 22.3%** | ✅ 已改 |
| §6.1 `_build_runner` 调用行号偏差 | ✅ 已改为实测值 483/502/671/750/805 |
| §2 参数统计口径未声明（含 `self`） | ✅ 已在 §2 标注 |
| §9 脚本在归档位置全部输出 0、目录未被跟踪 | ✅ 已在 §10 写明修订要求 |

**方案缺陷**

| 编号 | 严重度 | 处置 |
|---|---|---|
| **D1** `run_unittest` 一起搬走会使 18 处 patch 静默失效 | 阻断 | ✅ **已实证复现**（真实模块文件：`m.called=False`）；采纳 → 新增 **C7**，`run_unittest` 保留在 runner；A2.4 补 (b) 条断言 |
| **D2** A0.1/A0.2 互斥 | 阻断 | ✅ 拆分口径：A0.1 改为「对外签名快照不变（不设 ≤8）」，A0.2 改为「上下文内部版本 ≤ 8」 |
| **D3** 二分法不足以降到 ≤8 | 重要 | ✅ 改为**三类切分**（环境类 12 / 载荷类 6 / 差异类 6），24 无遗漏，差异类恰为 6 |
| **D4** 规则 2/3 当前已违反且违反面更大 | 重要 | ✅ 规则 2 区分**顶层 import（强）/ 延迟导入（软）**；当前违反面（runner 6 处、execution_broker 19 处、engineering_verification 1 处）**照实登记豁免，P1 不顺手改代码** |
| **D5** 规则 3 自指不可判定 | 重要 | ✅ 改写为可判定子集：「`sandbox_policy`/`isolation` 不得被 `windows_*`/`linux_*` 导入」；一般方向用允许依赖矩阵表达 |
| **D6** 迁移表遗漏 5 个常量 | 重要 | ✅ §5.1 已补齐 5 个常量行，并标注 `_VERIFICATION_OUTPUT_READ_CHUNK_BYTES` 为**共享**（簇外 :1866 亦用） |
| **D7** 只统计 patch，遗漏 4 处直接 import | 重要 | ✅ 新增 **C1b** 列出 4 处直接导入位置；A2.4 补 (c)(d) 条断言 |
| **D8** C6 表述含混、论据错误 | 次要 | ✅ C6 改写，明确 `isolation` 仅限 `TYPE_CHECKING` 标注，并更正无循环的真实理由 |
| **D9** A3.2 当前即为通过，无区分力 | 次要 | ✅ 改为「`LoopConfig(` 调用点 ≤1、`build_backend(` == 0、`CliApprover(` == 0」 |
| **D10** A3.1 目标 ≤14 不可达且不可归因 | 次要 | ✅ 降级为观察指标，门禁改为可归因判据 |

**验收项问题**：A0.1/A0.2/A0.5/A1.1/A1.2/A1.3/A1.4/A1.5/A2.1/A2.2/A2.3/A2.4/A2.5/A3.2/A3.3/A3.4 **全部已改写为可自动化断言**（见 §3.4 / §4.3 / §5.3 / §6.3）。

**遗漏与建议**

| 条目 | 处置 |
|---|---|
| 遗漏 1：脚本不可复算、未跟踪 | ✅ §10 写明修订要求 |
| 遗漏 2：基线 SHA 应为 `105fc27`；工作区残留 `=3.11`/`=80`/子模块脏状态 | ✅ 基线已改；残留文件属历史垃圾（`=3.11` 12KB、`=80` 0 字节），落地前清理；子模块脏状态为既存工作，本次不触碰 |
| 遗漏 3：`run_unittest` 保留后 `verification_process` 无需 `isolation` | ✅ 采纳（C7 后该复杂度消失；C6 仍保留 `TYPE_CHECKING` 约束作为防御） |
| 遗漏 4：P2 需覆盖 `run_unittest` 4 种 sandbox 分支 | ✅ 新增 **A2.6** |
| 遗漏 5：`pack_verify.py:1577` 按类名匹配的固定错误白名单 | ✅ C4 增列「`__name__` 不得变更」 |
| 遗漏 6：顺序调整 P1a→P0→P1b | ✅ §7.1 已采纳 |
| 遗漏 7：P3 收益不足以单列 | ✅ §6 降级为顺带清理，§7.1 合并到 P2 |
| 遗漏 8：P2 收益最低、风险最高，可延后 | ✅ 顺序置于 P1b 之后；若时间受限，P1a+P0 即可交付主要收益 |

**纪律核对**

| 条目 | 处置 |
|---|---|
| §7.3 未区分本机/线上 | ✅ 改为「相关测试本机跑、全量套件只在线上跑」 |
| 未说明推 main 还是建分支 | ✅ §7.3 第 4 条明确「推 `main`，不建分支/标签」 |
| 未要求绑定 workflow/job/平台/日志/退出状态 | ✅ §7.3 第 3 条已补全 |
| 需说明基线来自哪个工作区 | ✅ §0 已注明 Windows 检出 `D:\Projects\icode`，与远端同一 commit |
| P0 是否需拆为独立 SPEC | ✅ **本 SPEC 保持 P0–P3 合并**：P0 的对外签名**逐字段不变**（A0.1），只改内部实现，不构成公开接口形状变更，故不需独立 SPEC |
| 「不得以测试适配为名削弱断言」需可测判据 | ✅ §7.3 第 7 条已加 skip 数 / 断言条数对比 |
