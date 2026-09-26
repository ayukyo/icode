# R3 自验证与有界修复

- 日期：2026-09-26
- 状态：核心切片已实现并离线验收：失败分类、证据绑定、有界修复决策、runner 补救回合证据门、独立 Reviewer（只读上下文 + 证据引用）、回归证据绑定到具体 diff（`diff_fingerprint`）、修复证据写入事件链（`verification_recorded`）并随证据包取证；`run_task` 已具备有界修复循环（失败 → 分类 → 有界修复 → 回归 → 独立 Reviewer）的机制并以 FakeBackend 离线验收；R3 完整退出门槛（真模型端到端跑通）尚未闭合
- 依据：[产品总架构](../../icode-agent-product-architecture.md) §13.7；[R2 跨平台隔离设计](../specs/2026-09-23-r2-cross-platform-isolation-design.md) §12.2

## 目标与范围

从「能修改」升级到「能根据真实失败证据验证和修复」：

```text
修改 → 静态诊断 → 编译 → 单元测试 → 失败分类 → 有界修复 → 回归 → 独立 Reviewer
```

R3 核心能力（本切片）：

1. **失败分类**（`src/icode/self_verify.py::classify_failure`）
   把命令 / 测试 / 契约回执的失败分成六类：
   `environment` / `code` / `test` / `contract` / `model_capability` / `side_effect_unknown`。
   分类依据是可见证据（退出码、输出模式、错误类型、是否产物缺失）；
   无法归类时如实归入 `side_effect_unknown`（fail-safe）。

2. **证据绑定**（`VerificationEvidence` / `evidence_fingerprint`）
   每次验证绑定到 step、attempt、命令摘要、退出码、环境指纹、产物哈希、
   输出摘要与捕获时间。没有绑定的结果不能被当成「新证据」，
   也就不能支撑一次新的修复；指纹不包含输出正文或敏感参数。

3. **有界修复决策**（`VerificationLedger::decide_repair`）
   只有出现**新的失败证据**才允许重试 / 修复；相同指纹的重复失败在
   有界次数内被终止，避免「没有新证据就反复碰运气」；
   副作用状态不明一律按 fail-safe 拒绝自动重试（`human`）。

4. **runner 补救回合证据门**（`src/icode/runner.py::run_contract_step`）
   进入补救回合前先给「产物缺失」分类并绑定证据，`decide_repair` 返回非
   `allow` 时跳过并如实警告，不再无条件重试。

5. **任务级验证证据绑定**（`src/icode/runner.py::run_task`）
   独立跑 `python -m unittest` 后把退出码、输出摘要、环境指纹、改动文件哈希
   与失败分类绑定成一条 `VerificationEvidence` 挂到 `TaskReport.verification`；
   模型自述不算证据。

6. **证据回执序列化**（`VerificationEvidence.to_receipt`）
   可把一条验证证据序列化成 `verifications.json` 回执（含指纹、环境指纹、
   产物哈希与失败分类，不含输出正文/敏感参数）；`build_evidence_pack` 直接
   接受 `VerificationEvidence` 并序列化进证据包。

7. **独立 Reviewer 只读上下文**（`src/icode/reviewer.py`）
   `reviewer_guard` 构造无任何写授权的审查上下文，`verify_read_only` 用真实
   Guard 判定锁死；`IndependentReviewer.review` 针对改动文件与验证证据产出
   带严重级别、失败分类、文件与证据指纹引用的结构化发现，且不能修改被审对象
   （符号链接被审对象直接拒绝）。`run_task` 已接线：任务验证完成后用只读
   上下文复核改动与证据，`TaskReport.review` 携带审查报告。

8. **回归证据绑定到具体 diff**（`workspace_snapshot.diff_fingerprint`）
   把一次改动（相对基线）绑定成确定性指纹：只依赖改动前后每条路径的 sha256，
   增删改状态区分、同结果不同基线指纹不同。`run_task` 的独立测试回执把
   `diff_fingerprint` 一并绑定进 `VerificationEvidence`（进指纹与回执），
   证据锚定到「具体这一份 diff」而非仅结果内容。

9. **修复证据写入事件链并随证据包取证**（`control.record_verification`）
   控制面 `record-verification` 是唯一允许写 `verification_runs` 的入口；
   `runner` 在补救回合（产物缺失）进入时把该条修复证据（指纹 + 缺失摘要 +
   分类）写入事件链（`verification_recorded` 事件，幂等）。`build_evidence_pack`
   自动把 `metadata.verification_runs` 一并纳入 `verifications.json`，回归证据
   随包可取证。控制面验证域只有 build/deploy/listen/device_test 四类，R3 验证
   按 `device_test + layer=unit` 如实记录，`evidence` 字段放指纹、`note` 注明
   实际类别，不冒充设备实测。

## 六类失败定义

| 类别 | 含义 | 证据信号（示例） |
|---|---|---|
| `environment` | 环境/系统问题，与代码改动无关 | 退出码 126/127、`command not found`、`ModuleNotFoundError`、`Permission denied`、OOM |
| `code` | 代码改动引入的回归 | 测试断言失败、非零退出且无环境/契约信号 |
| `test` | 测试架子本身的问题 | `failed to collect`、`no tests ran`、fixture 错误 |
| `contract` | 控制面/门禁未满足 | 产物缺失、边界复检失败、副作用回执失败 |
| `model_capability` | 模型没有按契约产出或产出不可解析 | JSON 提取失败、未知工具、未审批、max_turns |
| `side_effect_unknown` | 无法判断类别/副作用不明 | `ambiguous_side_effect`、未闭合 operation |

## 验收（离线，已通过）

- `classify_failure` 对六类代表性样本分类正确；无法归类按 fail-safe；
- `evidence_fingerprint` 对同一事实稳定、对输出/退出码/产物哈希变化敏感，
  且不泄露输出正文或敏感参数；
- `VerificationLedger`：首次新证据允许、同指纹拒绝、输出变化允许、
  超界停止、副作用不明转人工、attempt 递增；
- runner 补救回合在首次失败时仍会进入（兼容既有离线链），无新证据时跳过；
- `run_task` 把独立测试退出码/输出摘要/环境指纹/改动哈希绑进 `TaskReport.verification`；
- `to_receipt` 与 `build_evidence_pack` 把验证证据序列化进证据包且不含正文。

## 边界（不冒充）

- 本切片**不是**完整 R3：独立 Reviewer 的隔离上下文、代码变更后验证证据
  绑定到具体 commit/diff、回归证据打包仍未接线；
- 分类函数只消费已提供证据，不做无依据推断，也不代替控制面门禁；
- 有界修复仍受既有预算、回合数、审批与副作用回执约束。

## 并行开源研究取舍

- **采纳机制：** Aider 的 edit→lint/test 验证闭环、SWE-agent 的
  observation-feedback、OpenHands 的 stuck detection、Cline 的 checkpoint
  共同点都是「没有新证据就不允许继续碰运气」；本切片用证据指纹 + 有界
  次数实现同一目标，不复制任何第三方实现。
- **不直接采纳：** 多 LLM 投票式对抗验证（arXiv 2512.03097 已证明共谋可破）；
  保持规则绑定 + 禁止自我委派。
- 以上为机制层面结论，不代表已集成任何上游运行时依赖。

## 已完成（回归切片，2026-09-26）

1. `workspace_changes` / 测试回执绑定到具体 commit/diff 与 artifact hash：
   `diff_fingerprint` 进 `VerificationEvidence`（指纹 + 回执）；
   工作区快照排除 `__pycache__` 编译产物（不是模型改动，不进 diff 证据）；
2. 独立 Reviewer 接线：`run_task` 用只读上下文复核改动与证据，不能修改被审对象；
3. 修复证据写入事件链与证据包：`record-verification` 记录 `verification_recorded`
   + `verification_runs`，`build_evidence_pack` 自动纳入 `verifications.json`；
4. **`run_task` 有界修复循环**：独立测试失败后，若类别可自动修复，在
   `max_repairs` 有界次数内重新让模型改动并复测；每次必须有**新的失败证据**
   （diff 或退出码/类别变化），同 diff 无新证据即停止，不碰运气；
   `TaskReport.repair_attempts` / `repair_decisions` 记录全部尝试与决策。
   指纹语义修正：`attempt` 是账本标签不进指纹（同一失败再次观测=无新证据），
   `record` 保留 `diff_fingerprint`；离线用 FakeBackend 覆盖修复成功、
   无新证据停止、次数有界三种路径。

## 下一片（尚未闭合）

1. 端到端真模型修复循环：失败 → 分类 → 有界修复 → 回归 → 独立 Reviewer 全链路
   在**真模型**下跑通并验收（机制已就绪，缺真模型验收）；
2. 把独立 Reviewer 完整接入 review 步骤 / Reviewer 上下文（当前接线在 `run_task`
   能力验证路径，review 步骤的对抗审查上下文仍需接入）；
3. 证据指纹锚定到真实 commit（Git SHA）而非仅工作区 diff 快照（R2.4 Git broker
   接通后可做）。
