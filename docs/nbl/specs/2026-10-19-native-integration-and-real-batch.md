# R7 后收束工作包规格：原生创新整合验证 + 真实评测跑批（2026-10-19）

**状态**：v1.2（二次评审 MAJOR×3/MINOR×6 处置完毕）。继承主序 §13.12（五项原生创新体系）与 R7 规格的 benchmark 口径。前置：R0–R7 全部验收通过（R7 见 `2026-10-19-r7-trusted-delivery-public-evaluation.md`，HEAD `ac277ff`）。

## 1. 目标与边界

用户指示"都做"，本工作包收束两件事：

- **A（§13.12 整合收束）**：五项原生创新（Contract-driven Agent / Gate-driven Context / Evidence-carrying Action / Least-capability Execution / Auditable Multi-Agent）目前各自有验收，但缺少"**同一个不可绕过控制平面**"的端到端证明。本工作包交付一个真实控制面（icode-skill）上的端到端整合测试，五项机制在同一条工单生命周期内逐环咬合，并以 R7 签名证据包收尾。
- **C（真实评测跑批）**：用户已授权模型预算（models.json 的 MiniMax-M3）。按 R7 W4 口径执行**第一包**真实跑批：pycalc 靶场任务 ×5 次，产出 RunLedger、四率报告与失败样本，全部如实入库。**范围诚实声明：这是单靶场任务的统计口径端到端，不是 §13.11 的多仓库公开评测**（后者仍列暂缓）。

不适配：不新增第二状态机、不放宽任何门禁、不引入第三方依赖；UI 设计包（B）另立文档（`2026-10-19-ui-workbench-design-package.md`），不进本规格。

## 2. A：整合验证（W1）

落地物 `tests/test_native_integration.py`（unittest，真实 skill 控制面，缺失时按既有纪律跳过）。单场景逐环断言：

| 环 | 机制 | 断言要点 |
|---|---|---|
| 1 | Contract-driven | `ControlPlane.create` 建单；gates.json 状态机驱动当前步骤；事件链记录 ticket_created |
| 2 | Gate-driven Context | 以**当前未满足门禁**的词项驱动 `build_index`/`select_context`，断言选中的上下文指向门禁相关文件而非全仓大纲 |
| 3 | Least-capability Execution | executor 经 `AgentTeam.spawn/run` 在申报区域内写产物（区域收敛策略）；reviewer 派生只读策略（`write_roots=()`）；越区写被拒（稳定码） |
| 4 | Evidence-carrying Action | 产物摘要经 `attach_evidence` 绑定进入控制面记录；事件链可核 |
| 5 | Auditable Multi-Agent | executor/reviewer 各自产生带 `context_digest` 的结论；`step_gate` 要求两角色 completed 才放行；单缺任一结论门禁 blocked |
| 6 | R7 收尾 | `build_evidence_pack` 出包 → `verify_pack` 通过 → `pack_signing.sign_pack` 签名 → 提供公钥验签通过、篡改即拒 → 预声明 git-tag 锚定记录校验通过 |

验收判据（G-A1）：全部六环在**同一工单**上顺序通过；任意一环的破坏（如删结论、篡改产物）导致其后环节可观察失败（门禁 blocked / 验签失败）。测试文件内对五项机制的源码锚点（模块/函数名）逐项注释，形成"声明 → 证据"链接表。

## 3. C：真实跑批协议（W2）

落地物 `scripts/run_real_benchmark_batch.py` + 运行产物。

- **驱动**：直接调用 `runner.run_task`（与 `icode task` 同路径）：fixture `pycalc`、DEFAULT_TASK、`DenyAllApprover`（批处理无交互；审批需求记 refused）、`LoopConfig` 默认、`Budget(expected_tokens=每 run 上限)`、每 run 全新隔离工作区与全新 backend 实例（usage 独立）。
- **后端**：openai-compatible，`--model/--base-url/--key-file` 由调用方提供（models.json 的 MiniMax-M3；key 不入任何提交物）。
- **样本量**：默认 5 次（--runs 可调）；统计口径 = R7 benchmark 模块，无筛选参数。
- **记录映射**：`result`：ok→success、验证/循环失败→failed、审批拒绝→refused；`first_pass` = ok 且 `repair_attempts` 为空；`recovered` = 曾失败（有 repair/重试）最终 ok；tokens/latency 取 `backend.usage`；cost 未知如实 null（MiniMax 不在 pricing 表则不冒充）。
- **产物**：`docs/nbl/benchmarks/2026-10-19-minimax-m3-pycalc-batch/`（ledger.json、report.md、runs/raw-<i>.json 有界摘要；均 `git add -f`）。报告开头显式声明样本范围（单靶场任务、单一模型、非公开评测）；run 数不足或全失败时按"无统计结论"纪律输出。
- **预算与安全（回应 B1）**：`Budget(expected_tokens=N, hard_ratio=1.0)` 使硬停点**恰好等于** `--budget-tokens`（默认 120,000）——默认 hard_ratio=3.0 的语义是"超预期 3 倍才必须回退"，直接传 expected 会让真实硬停点膨胀 3 倍；RunRecord.budget.max_tokens 记录的就是该实际硬停值。每 run 另设 `LoopConfig(max_output_tokens=8192)`（回应 M4）并写入报告。批处理脚本禁写工作区外路径；密钥只经仓外授权文件（models.json，`C:\Users\orbbec\.workbuddy\models.json`，回应 m1）转存临时 key 文件传入，绝不入库；跑批失败不重试掩盖（如实记 failed）。
- **成本口径（回应 M1）**：MiniMax 已在 pricing 表（minimax 前缀），cost_usd 为**静态估算价而非账单**——报告与 scope note 明确标注。
- **结果态映射（回应 M2/M3）**：v1 驱动只产出 success/failed 两态；refused/human_intervention 为保留态（驱动不启用判定规则，报告注明）。budget 三键填充规则：max_tokens=硬停值、max_cost_usd=None（未设成本闸门）、max_minutes=None（未设墙钟上限，最坏串行耗时为已知限制，如实记录）。
- **样本量与泛化边界（回应评审）**：n=5 的样本量不足以支撑任何泛化结论，报告开头固定声明「统计口径端到端、不构成对任务域的泛化结论」；查询词项与 fixture 路径对齐（calc.py 缺口驱动上下文，回应 m3）。

验收判据（G-C1）：脚本可重复执行（同参数产生结构一致的 ledger）；ledger/report 通过 benchmark 模块校验；报告含全部 run 与失败样本；密钥哨兵扫描干净；样本量、成本口径、范围限制在报告中逐项可见。

**显式暂缓（保持 R7 §5 口径）**：多仓库真实任务集、主流 Agent 对比、Rekor/RFC 3161 真实接入。

## 4. 风险与控制

- A 的端到端场景依赖 skill 控制面测试基建（`require_skill`），缺失环境自动跳过，不冒充通过。
- C 的真实调用可能因网络/限流失败：失败 run **如实入账**（failed + 错误码），不重试美化；连续失败时报告仍成立（0 成功也是统计事实）。
- 真实成本失控防线：Budget 每 run fail-closed；脚本累计打印已耗 token； runs 默认 5。
- 不动 vendor/icode-skill；A 的场景构造复用既有测试模式（ControlPlane + 注入工厂），不新建基建。

## 5. 验收计划汇总

| 门 | 判据 | 证据 |
|---|---|---|
| G-A1 | 六环同一工单顺序咬合，破坏任一环其后可观察失败 | `tests/test_native_integration.py` |
| G-C1 | 跑批脚本可重复、ledger/report 合规、失败样本如实、密钥零泄漏 | `scripts/run_real_benchmark_batch.py` + `docs/nbl/benchmarks/` |
| 阶段判据 | 新增测试全绿 + 全量零新增失败 + CI 三 run success | CI 记录回填 |

## 6. 评审回应（v1 → v1.1）

独立评审（QUALITY 代理，2026-10-19）：BLOCKER×1、MAJOR×4、MINOR×5。处置：B1（Budget 默认 hard_ratio=3.0 使硬停点=3×expected）→ 采纳，`hard_ratio=1.0` 且 max_tokens 记实际硬停值；M1（MiniMax 在 pricing 表，cost 是估算）→ 采纳，报告标注"静态估算价、非账单"；M2（refused 判定规则）→ 采纳，v1 驱动只产出 success/failed，refused/human_intervention 保留并注明；M3（budget 三键填充规则）→ 采纳，max_minutes=None 为如实声明；M4（max_output_tokens）→ 采纳，8192 并入报告；m1-m5（models.json 措辞、墙钟上限、查询词项、manifest 构造模式、破坏性注入由分步门禁承担）→ 采纳或已在实现中覆盖。

## 7. 实施记录

- **W1 整合测试**：`tests/test_native_integration.py`（1 项，六环同一工单咬合，全绿）。环 2 断言修正为排序语义（预算充足时全选是正常行为，缺口词项决定排序）；executor 结论的 context_digest = 收敛后区域策略指纹（`converge_policy_to_region(...).policy_hash`），与 spawn 时全域摘要不同——这正是最小权限的可观察边界；门禁为分步核对（code 步 executor / review 步 reviewer / verify 步 verifier 缺失即 blocked），executor 的 code 步结论不能顶替 review 步的 reviewer 结论。证据通道：`attach_evidence`（R5 词表）+ `collect_verifications` 经 `build_evidence_pack(verifications=...)` 入包（R3）。
- **W2 跑批**：`scripts/run_real_benchmark_batch.py`（可重复驱动）。执行了两批真实跑批（模型 MiniMax-M3，来自仓外授权 models.json）：
  - 第一批（端点配置错误 404，5 failed × 0 tokens，作废）；
  - 第二批（端点修正，3 success / 2 failed，410,530 tokens）——发现 cost 全为 null 的聚合器缺陷后作废；
  - **最终批（提交入库）**：1 success / 4 failed，544,889 tokens（prompt 513,375 / completion 31,514），耗时 417,557 ms，成功率 0.20、恢复率 0.75、首次门禁通过率 0.00（每 run 均有修复循环），其中 3 个失败 run 越过 120K token 硬停，run 01 在预算内失败（exit_code=0、无错误文本，形态指向 Reviewer/交付门拒绝）。两批合计 4/10 成功——样本量不支持任何泛化结论，如实入库。
- **附带缺陷修复（跑批发现）**：四个真实后端（openai-compatible/anthropic/gemini/ollama）的 usage 聚合器以 `Usage(calls=0)`（cost=None）起步，`Usage.merge` 的"任一未知即未知"语义把估算费用永久污染为 None。修复：聚合器初始 `cost_usd=0.0`（费用求和的单位元；零观测=零成本，真实观测的未知仍正确传播为未知）。回归测试 `tests/test_usage_cost_aggregation.py` 3 项；契约套件 4 后端全过。第一版修复（首观测替换聚合器）曾在重试场景丢失累计重试计数，被契约套件当场捕获后改为单位元方案。
- **pricing 表数据问题（如实披露）**：minimax 条目（0.30/1.20 per 1K tokens）与 MiniMax M3 公开标价（约 0.30/1M 输入）量级不符，本批 cost 字段高估约两个数量级（$191 vs 实际约 $2）。报告已标注失真；pricing 表数据修正列为后续项（属 R4 数据维护，不在本工作包擅改）。
- **B 前置交付**：UI 设计包另立文档（`2026-10-19-ui-workbench-design-package.md` + `docs/ui/workbench-prototype.html`），不属本规格验收范围。

**二次评审处置（v1.1 → v1.2，MAJOR×3/MINOR×6）**：M-A（run 01 并非硬停失败，措辞失实）→ 采纳，§7 措辞已改；M-B（recovered 三处口径不一致）→ 采纳，统一为"曾经历失败且最终 success"，`benchmark.aggregate` 恢复率分母改为"经历失败的 run（非 first_pass）"，账本按统一语义从 raw 重建（免重跑模型），测试样本同步更新；M-C（gemini 测试空转）→ 采纳，重写为四后端真实双调用费用聚合回归（`tests/test_usage_cost_aggregation.py` 5 项，ollama 本地计价为 0 的断言同时覆盖）；m1（per-run 增量落盘）→ 采纳，驱动每 run 后即写 ledger；m2（运行树披露）→ 采纳，scope note 注明；m3（包级篡改断言）→ 采纳，整合测试补 manifest 尾字节篡改 → 验签失败；m4（提交完整性）→ 采纳，交付物 `git add -f`；m5（循环参数披露）→ 采纳，scope note 注明 max_turns/max_output_tokens/max_repairs/硬停；m6（Usage 聚合约定与 en-US 视图）→ 采纳，Usage 文档补单位元约定，原型 en-US 视图补完成页/IC-139/R7 三行。

**测试台账**：新增 4 项（native_integration 1 + usage_cost_aggregation 3，其中 usage_cost_aggregation 重写后为 5 项）全绿；契约套件全过；全量套件结果见 CI 验收记录。
