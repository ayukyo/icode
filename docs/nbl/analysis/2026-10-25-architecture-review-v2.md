# 架构复核与优化空间评估（2026-10-25）

**基线**：`105fc274`（远端 main，2026-10-25 12:xx 拉取；WSL 权威工作区 `/home/orbbec/projects/icode`）
**方法**：AST 导入图 + 符号级跨模块引用统计 + 实测行数核算，全部数据可复算（脚本见文末）。
**前置**：本稿是对 `docs/nbl/analysis/2026-10-24-architecture-refactor-analysis.md`（基线 `f584c47`）的**独立复核**，不是重复它。结论有 4 处与前稿冲突，已逐条给出实证。

---

## 1. 结论摘要

**架构意图成立，代码组织需要收敛——但前稿的两条核心量化依据是错的，导致其推荐路径的收益被高估。**

| 判断 | 结论 |
|---|---|
| 分层意图是否被破坏？ | **未破坏**。硬循环依赖 = 0，控制面边界完好，前稿此结论成立 |
| 是否需要大重构？ | **不需要重写**。但前稿的 R1a/R1b 两步都建立在错误数字上，实际收益远低于预期 |
| 前稿结论可执行性 | **R1b（Ed25519 提取）不可行**——与「证据包自带独立校验器」架构契约直接冲突 |
| 真正的优化空间在哪？ | 不是「拆大文件」，而是 **① 参数爆炸的编排函数 ② 文档-代码漂移 ③ 缺架构边界回归防线 ④ CLI/自治双编排路径** |

**优先级重排（与前稿不同）**：

| 序 | 动作 | 前稿对应 | 理由 |
|---|---|---|---|
| **P0** | 编排函数参数收敛（`_run_agent` 24 参 → 上下文对象） | 前稿未提 | 这是真正阻碍测试与演进的瓶颈，收益高于拆文件 |
| **P1** | 架构盒子→模块登记表 + 边界回归测试 | R1c | 前稿已提，**但必须先做**，否则每次拆分都在放大漂移 |
| **P2** | `runner` 平台执行簇下沉（约 797 行，零私有耦合） | R1a（估 1500 行） | 方向对，**但收益是 797 行不是 1500 行**，达不到前稿「≤3000 行」目标 |
| **P3** | CLI / 自治编排路径收敛 | R1d | 前稿已提，方向正确 |
| **—** | ~~Ed25519 提取为 `icode.crypto.ed25519`~~ | R1b | **建议撤销**，见 §3.2 |

---

## 2. 现状度量（`105fc274`，独立复算）

| 维度 | 数据 |
|---|---|
| 规模 | `src/icode` **104 模块 / 48,516 行**（42,605 代码行）—— 与前稿一致 |
| 测试 | tests **194 文件 / 3,937 测试函数**（前稿称 3,945，差 8，为统计口径差异） |
| 函数总数 | **1,653** |
| 硬循环依赖 | **0**（模块级双向 import 为零；见 §2.1） |
| 软循环（延迟导入） | 14 组，**177 处函数内延迟导入**，分布在 28 个模块 |
| 扇入 hub | sandbox_policy 21、config 10、control 10、isolation 10、contracts/workspace/tools.base/native_helper 各 8 |
| 扇出 hub | **runner 36**、cli 22、autonomy 14、chain 12、execution_broker 10 |

### 2.1 「零循环依赖」需要加限定词

前稿称「模块级导入图零循环依赖」。这个说法**在硬依赖上成立，但掩盖了真实耦合**：

- **硬循环 = 0**：所有双向 import 关系都有一侧是函数内延迟导入。`chain.py:30` 顶层 `from .runner import ...`，而 `runner.py:1332` 用 `from .chain import assemble_review_manifest`（函数内）——靠延迟导入打破。
- **软循环 = 14 组**：`runner↔chain`、`runner↔reviewer`、`runner↔evidence↔self_verify↔engineering_evidence`、`execution_broker↔isolation`、`workspace_snapshot↔windows_worktree`、`backends` 家族 5 个模块互环等。

**判定**：不是「没有循环」，而是「用 177 处延迟导入把循环压在了运行时」。这本身是一种**成熟的解耦手段**（且 patch 机制依赖它，见 §4.2），但它意味着**模块边界没有被强制约束**——今天靠自觉，明天靠 review。

### 2.2 真实瓶颈：编排函数的参数爆炸

前稿全部精力放在「文件太大」，但实测显示**参数数量**才是演进瓶颈：

| 函数 | 参数数 | 位置 |
|---|---:|---|
| `_run_agent()` | **24** | `runner.py:2609` |
| `run_contract_step()` | **22** | `runner.py:1237` |
| `run_chain()` | 20 | `chain.py:288` |
| `_contract_engineering_gate()` | 20 | `runner.py:1906` |
| `resume_contract_step()` | 16 | `runner.py:3010` |
| `_bind_task_evidence()` | 14 | `runner.py:4361` |

**全仓 1,653 个函数中，51 个（3.1%）参数 ≥8，13 个 ≥12，5 个 ≥16，4 个 ≥20。**

为什么这比「大文件」更关键：`runner.py` 的 4495 行里，真正难测的是**编排函数必须同时拿到 20+ 个协作者**——这意味着无法在无平台环境下构造它，单元测试只能整块 mock。**参数收敛（引入 `RunContext` 之类的上下文对象）能同时降低耦合度与测试成本，而拆文件只降低行数。**

---

## 3. 与前稿的四处冲突（逐条实证）

### 3.1 R1a「约 1500 行验证进程管理」**高估 2.07 倍** → 实测 723 行

前稿 D1 段落点名 5 个 runner 内符号：`_run_posix_bounded_output`(167) + `_cancel_windows_pipe_readers`(45) + `_run_threaded_bounded_output`(18) + `_run_threaded_bounded_output_impl`(182) + `_PosixVerificationExitMonitor`(82) = **494**，再加上**外部模块 `windows_runner_pipe.py`(956 行)** = 1450 ≈ 1500。

**实测**：

```
grep -n "windows_runner_pipe" src/icode/runner.py  →  0 命中
```

`windows_runner_pipe.py` **是独立模块，runner.py 从未引用它**（仅 `tests/test_windows_runner_pipe.py` 引用）。把它算进「runner 的验证进程管理」是**跨模块重复计数**。

补上 D1 漏掉的 4 个函数（`_darwin_process_group_has_live_members` 103、`_terminate_posix_verification_group` 32、`_reap_posix_verification_process` 22、`_join_or_cancel_threaded_readers` 9 = 166），runner 内真实总量：

| 口径 | 行数 |
|---|---:|
| 严格进程管理（12 个平台函数） | **723** |
| + `run_unittest`(48) + wrapper(25) | 796 |
| 平台簇连续区间 387–1183 | **797** |

**连带影响**：前稿称「runner 降约 35%」。按 797 行算实际降幅 **17.7%**（4495 → ~3700），**达不到前稿自设的「runner ≤ 3000 行」验收目标**（§5 第 4 条）。要达标需再抽 A簇(520)/R簇(617)/G簇(364) 中至少一个。

### 3.2 R1b「Ed25519 约 700 行」**高估 5.1 倍** → 实测 183 行（141 代码行）

实测 `pack_verify.py:1915-2097` 区间：183 行，其中代码行 141 行。逐函数求和：

| 函数组 | 行号 | 行数 |
|---|---|---:|
| 曲线常量 `_ED_P`…`_ED_IDENTITY` + `_DOM4_PREFIX` | 1920-1928 | 9 |
| `_ed_inv` / `_ed_point_add` / `_ed_point_mul` | 1938-1962 | 21 |
| `_ed_compress` / `_ed_recover_x` / `_ed_decompress` | 1965-1998 | 30 |
| `_ed_secret_expand` / `_ed_dom4` | 2001-2013 | 11 |
| `ed25519_public_key` / `ed25519_sign` / `_ed_verify_core` / `ed25519_verify` | 2016-2057 | 36 |
| ctx/ph 变体 + `_ed_ctx_sign` | 2060-2097 | 41 |
| **纯算法合计** | | **137**（含注释空行 183） |

即使把签名区(98 行)与锚定区(79 行)全算进来也只有 360 行，**不足前稿 700 的一半**。

### 3.3 ⚠️ 更严重：R1b 与架构契约**直接冲突**，不可实施

这是本次复核最重要的产出。前稿建议「Ed25519 提取为 `icode.crypto.ed25519`，pack_verify 只 import」——但这会破坏三条既有不变量：

| # | 不变量 | 证据 | 破坏方式 |
|---|---|---|---|
| ① | `tools/verify_evidence_pack.py` 与 `src/icode/pack_verify.py` **字节完全相同** | 实测 sha256 均为 `823a5959…c56e`；`tests/test_pack_verify_extensions.py:32-35` 断言相等 | pack_verify 一旦 `from .crypto.ed25519 import ...`，两文件不再同步 → **断言失败** |
| ② | tools 副本**只能用标准库**，不得含 `icode` import | `tests/test_pack_verify_extensions.py:37-44` 断言 `assertNotIn("icode.", ...)` | `from .crypto.ed25519` **直接命中该断言** |
| ③ | 每个证据包内含**可独立运行的 `verify.py`** | `evidence.py:1281-1283`：`Path(pack_verify.__file__).read_bytes()` 原样写入包内 `verify.py` | 包内副本必须自带 Ed25519 实现；`import icode.crypto` 在第三方机器上失败 |

且 `pack_verify.py` docstring 第 2 行明写「**零依赖，不 import 本仓任何代码**」。

**结论：撤销 R1b。** 137 行的收益无法补偿破坏「零依赖单文件 + 字节同源 + 包内独立副本」三条架构契约的代价。

**若仍要降低 pack_verify 的认知负荷**，唯一合规路径是**「共享源 + 生成」模式**：把 3214 行拆成 `pack_verify_parts/*.py` 分片源，由脚本拼装生成 `src/icode/pack_verify.py` 与 `tools/verify_evidence_pack.py`。三条不变量全部保持 ✓，但引入构建步骤。**建议推迟**——pack_verify 的 3214 行中约 1151 行是打包/规范化、1334 行是验证策略，真实可移动部分有限，优先级低于 runner。

### 3.4 架构文档漂移**比前稿描述的更严重**

前稿 D2 称「架构图缺 `execution_broker`（1117 行）等已存在的盒子，14 个模块未归类」。实测 `docs/icode-agent-product-architecture.md`（1309 行）：

| 模块 | 文档提及次数 |
|---|---:|
| `execution_broker` | **0** |
| `reviewer` | **0** |
| `handshake` | **0** |
| `pack_verify` | **0** |
| `runner` | **0** |
| `isolation` | 1 |

**最核心的 5 个模块（合计约 12,700 行，占代码 26%）在架构文档中一次都没出现。** 文档描述的是「盒子」这一抽象层，而代码是 104 个扁平模块——两者之间**没有映射表**，所以既谈不上「缺盒子」，也谈不上「已对齐」，而是**根本对不上**。

---

## 4. 既有分析成立且值得保留的部分

### 4.1 「不推荐大爆炸重写」——完全正确

导入图零硬循环、hub 结构健康、控制面边界完好、3,937 测试 + 三 CI run 的验收面是多年阶段成果。**重写不增加任何用户可见能力，只把验收面置于风险中。** 本稿同意。

### 4.2 延迟导入是**刻意设计**，不是技术债

`engineering_verification.py:478-529` 用 `from . import runner` + `runner._run_unittest_with_bounded_output` + `runner.VerificationOutputError` 的**模块属性访问**模式，而非直接 import——这是为了让 `patch("icode.runner.X")` 生效。全仓 **18 处** patch 目标为 `_run_unittest_with_bounded_output`，**11 处**为 `_run_task_reviewer`。

**拆分时必须保持 `runner.X` 属性访问路径**，否则这些 patch 静默失效（不会报错，只会失去隔离效果）——这是最容易踩的坑。

### 4.3 runner 内部职责簇已做实测清点

| 簇 | 行号区间 | 行数 | 拆分难度 |
|---|---|---:|---|
| **P 平台进程执行/输出捕获** | 387–1183 | **797** | ★ 零外部私有耦合、零循环风险——**首选** |
| R 审查（Reviewer） | 3461–4083 | 617 | 需 `_make_ctx` 注入 |
| O 编排主流程 | 1207–1639 等 | 680 | 核心，暂不动 |
| A Agent 循环桥接 | 2444–2966 | 520 | ⚠ `runner↔chain` 双向依赖高风险 |
| E 工程门禁 | 1642–2127 | 505 | 扇出 12，跨 4 簇，须最后做 |
| G Git 会话与结果绑定 | 4086–4465 | 364 | 零循环风险 |
| F 证据写入 | 2203–2288 等 | 118 | 低 |

**P 簇的独特优势**：12 个平台函数**零外部私有耦合**，只依赖 stdlib + `windows_process_tree`（单向），其中 POSIX 侧用 `selectors`/`os.waitid`/`killpg`，Windows 侧用 `ctypes.WinDLL("kernel32")`/`CREATE_SUSPENDED`。抽走后 runner 不再需要理解平台进程语义。

### 4.4 CLI 是第二编排路径——确认

`cli.py` 875 行、13 个 `cmd_*`、`_build_runner`(:406) 被 `cmd_step_run`(:478)、`cmd_task`(:495)、`cmd_recover`(:668)、`cmd_workbench`(:722)、`cmd_chain`(:800) **5 处重复组装** backend/approver/budget/sandbox/LoopConfig。`cmd_task` 自行拼装 `run_task` + `LoopConfig` + `Budget`，与 `runner.run_task` 重复编排知识。**入口层应只做参数解析与调用。**

### 4.5 未归类的 14 个模块与测试盲区

实测无直接测试 import 的模块：**6 个 / 926 行**（`extensions.mcp_client` 419、`windows_startup_source` 207、`windows_provenance` 125、`leased_connect` 88、`backends.fake` 73、`__init__` 14）。

前稿点名 4 个中的 3 个属实；前稿未提 **`extensions.mcp_client`（419 行，扩展生态入口）**——这是比前稿所列更值得补测试的一处。

---

## 5. 优化方案（按证据重排）

### P0：编排函数参数收敛 —— **前稿遗漏的最大机会**

**问题**：`_run_agent()` 24 参、`run_contract_step()` 22 参、`run_chain()` 20 参、`_contract_engineering_gate()` 20 参。

**做法**：引入不可变上下文对象（如 `RunContext` / `StepContext`），把「环境类」参数（settings/backend/approver/budget/sandbox/policy/session/on_event/loop_config…）打包，保留「本次调用差异类」参数（step/attempt/workspace 等）为显式入参。

**收益**：
- 消除 3.1% 高参函数的尾部风险（新增参数要改所有调用点）；
- 让编排函数**可在无平台环境构造** → 单测成本骤降；
- 与 P2 的文件拆分互补：拆文件解决行数，参数收敛解决可测性。

**风险**：中。`run_contract_step` 被 **13 个文件**引用、`StepReport` 被 10 个、`resume_contract_step` 9 个、`run_task` 8 个——**必须保留现有签名作为兼容外观**，内部转调新上下文版本。

**验收**：全量测试零新增失败 + 参数数 ≤8 的编排函数清单落地。

### P1：架构盒子→模块登记表 + 边界回归测试 —— **必须先于任何拆分**

**问题**：架构文档对 5 个核心模块提及为 0；104 个模块无归类登记处；`tests/` 下**不存在**任何架构边界测试（`test_architecture_boundaries.py` 不存在）。

**做法**：
1. 建立 `docs/architecture/modules.yaml`（或等价表）：每个模块 → 盒子、层级、允许依赖的层；
2. 新增 `tests/test_architecture_boundaries.py`：断言（a）编排层不得 import 平台模块白名单；（b）hub 模块不得被反向依赖；（c）**新增模块必须归类**（未登记即失败）；
3. 架构文档按登记表回填，不再手写抽象图。

**收益**：这是**唯一能让前稿 R1a/R1c/R1d 不再漂移的机制**。没有它，每次拆分都在赌下一次 review 会注意到。

**风险**：低。纯新增，不改行为。

### P2：runner 平台执行簇下沉（约 797 行，**不是 1500 行**）

**做法**：新建 `src/icode/verification_process.py`，迁入 P 簇 12 个平台函数 + `run_unittest` + 3 个错误类 + 相关常量。

**关键约束**：
- runner 侧**保留 `from .verification_process import ...` 重导出**，且 `engineering_verification.py` 必须继续走 `runner._run_unittest_with_bounded_output` 属性访问路径（保住 18 处 patch）；
- `_snapshot`（是 `workspace_snapshot.snapshot_workspace` 的别名，非 runner 私有函数）与 `_runtime_budget` 被 `chain.py:30` 引用，**不能搬走**。

**收益**：runner 4495 → ~3700（-17.7%）。**注意：单做此步达不到「≤3000 行」**。若该目标仍要保留，需再抽 R 簇(617) 或 G 簇(364)。

**风险**：中。`tests/test_runner.py` + 4 个 Windows probe 脚本 + 3 个 Windows 测试文件。

### P3：CLI 与自治编排路径收敛

**做法**：`cli.py` 只留参数解析；`_build_runner` 的组装下沉到 `runner` 或新的 `icode.bootstrap`；`cmd_task`/`cmd_step_run` 改为调用单一入口。`autonomy.NativeChainExecutor` 已通过 `step_runner` 注入做了正确的依赖倒置——**CLI 应对齐这个已有模式**，而不是自造一套。

**收益**：cli fan-out 36 → 显著下降；消除「同一编排逻辑两处维护」。

**风险**：低-中。`test_cli` 回归。

### 明确不做（本稿新增）

- **不做 Ed25519 提取**（§3.3）——与架构契约冲突；
- **不做大爆炸重写**（§4.1）；
- **不做 O2 子包重组**（104 → 10 子包）——194 个测试文件的 import 更新 + 巨大 diff，收益是「分层显式化」，而 P1 的登记表已能低成本达成同样的可见性；
- **不把 `pack_verify` 拆分排进近期计划**——真实可移动部分有限，且触及 R7 已锚定公开仓库的签名契约。

---

## 6. 与前稿的净差异

| 项 | 前稿（2026-10-24） | 本稿（2026-10-25） | 差异性质 |
|---|---|---|---|
| 硬循环依赖 | 「零循环」 | **零硬循环 + 14 组软循环 + 177 处延迟导入** | 补充限定，结论不变 |
| R1a 验证进程行数 | ~1500 | **723（严格）/ 797（含 wrapper）** | **纠正，高估 2.07×** |
| R1a 降幅 | ~35% | **17.7%** | **纠正** |
| R1a 后能否达 ≤3000 行 | 能 | **不能，需再抽 1 簇** | **纠正** |
| R1b Ed25519 行数 | ~700 | **183（141 代码行）** | **纠正，高估 5.1×** |
| R1b 方案可行性 | 推荐实施 | **不可行，建议撤销** | **推翻** |
| 首要优化目标 | 拆大文件 | **编排函数参数收敛（24 参）** | **重排** |
| 架构文档漂移 | 缺 execution_broker 等盒子 | **5 个核心模块提及为 0，无法映射** | **升级严重性** |
| 边界测试 | R1c 中提 | **前置为 P1** | **重排** |
| 拆分优先级 | R1b → R1a → R1c → R1d | **P0 参数 → P1 边界 → P2 平台簇 → P3 入口** | **重排** |

---

## 7. 建议的落地纪律

沿用仓库既有纪律（SPEC → 独立评审 → 逐条处置 → 实施 → 全绿 CI → 验收记录）：

1. 本稿**未实施任何改动**，仅分析。落地前需先转成独立 SPEC（当前 `docs/nbl/specs/` 下**无重构 SPEC**——前稿的分析从未转为可执行规格）。
2. P1（登记表 + 边界测试）**必须先落地**，为后续每次拆分提供回归防线。
3. P2 的验收要写明「runner ≤ 3700」而非前稿的「≤3000」；若坚持 3000，需在 SPEC 里显式纳入 R 簇或 G 簇。
4. P0 属接口形状变更，触碰 `run_contract_step`（13 文件）等公开入口，**按仓库纪律应走独立 SPEC + 评审**。
5. 每步独立提交、绑定实际候选 SHA 与三 CI run；「跳过≠通过」。

---

## 附：度量复算

脚本（本稿随附于临时工作区，可迁入 `scripts/` 归档）：

- `metrics.py` — 模块清单 / LOC / 扇入扇出 / 测试映射；
- `cycles.py` — SCC 循环检测（含行号与 import 形态）；
- `cycles_classified.py` — 硬循环 vs 延迟导入循环分类；
- `coupling.py` — 平台混用 / 重复函数 / 参数分布 / 全局状态。

数据来源：`src/icode/**/*.py` AST 遍历 + `tests/` 直接 import 映射；基线 `105fc274`。
