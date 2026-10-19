# R7 后收束工作包规格：原生创新整合验证 + 真实评测跑批（2026-10-19）

**状态**：v1（待独立评审）。继承主序 §13.12（五项原生创新体系）与 R7 规格的 benchmark 口径。前置：R0–R7 全部验收通过（R7 见 `2026-10-19-r7-trusted-delivery-public-evaluation.md`，HEAD `ac277ff`）。

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
- **预算与安全**：每 run token 上限默认 120,000（fail-closed）；批处理脚本禁写工作区外路径；密钥只经环境/文件传入，绝不入库；跑批失败不重试掩盖（如实记 failed）。

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

## 6. 实施记录

（实施后回填）
