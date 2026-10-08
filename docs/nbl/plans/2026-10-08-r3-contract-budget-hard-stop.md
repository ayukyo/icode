# R3 契约预算硬停止 Implementation Plan

> REQUIRED SUB-SKILL: nbl.test-driven-development、nbl.subagent-driven-development。必须等独立验证测量片冻结、门禁及提交后才修改runner，避免交叉污染。

**Goal:** 已观测 budget_exceeded 不得因已有产物或恢复路径而变成契约成功，不再触发装配、补救、推演或状态前移。

**Architecture:** 复用 LoopResult.stop_reason 和现有控制面 failure finish；仅初次/repair/resume三个消费点及共用私有硬停止收尾。正常回合上限仍保留既有产物驱动软处理，不扩大其它stop语义。

## 实际基线（三问）

2026-10-08主代理实际临时工作区、真实ControlPlane及AgentLoop复现：expected_tokens=100，第一次100tokens真实工具写01_plan.md，第二次201tokens纯文本使loop ok=false/budget_exceeded/301tokens；run_contract_step仍post_write一次、finish=success、backend总5次（含之后3次推演）、状态已前移、error为空。该离线夹具证明运行时路径，不代表真实模型能力或生产工程验收。

这是预算硬失败被统一软化的真实问题。已有loop charge后硬门和CP failure终结机制应复用，不造新预算阈值。调用链为run_contract_step初次、产物repair、resume_contract_step，chain消费StepReport并停步；预算全链所有权和推演计费仍是下一片，不能据本片虚称闭合。

## Task 1: 拒绝成功与后续工作

- [ ] 完成

编辑限定 src/icode/runner.py 与新 tests/test_contract_budget_stop.py，必要关联测试补兼容断言。不改平台、vendor、CI权限、预算阈值或模型KEY。

- [ ] Step 1: RED

真实CP+明确last_usage的离线backend，已有真实产物301超限仍success的原行为作为RED；另覆盖缺件超限不得repair/autopersist，repair首回复超限不得后装配，resume超限不得清检查点或前移。后续模型调用计数、post_write、artifact登记和实际CP事件必须核对，不只断言report.ok（其可能已被其它门禁阻断）。

- [ ] Step 2: 最小硬停止

每个模型loop返回后立即识别精确budget_exceeded，report.loop保留真实结果及已计费用量；固定错误说明预算硬停止。只尝试当前attempt的failure finish，失败不伪造成功、不改旧产物/操作回执、不清checkpoint。收尾只读cp.trace、如实检查开放步骤/操作，不能调用会推演或transition的_finalize。

初次不调用post_write/登记/repair/autopersist；repair之前已发生的登记保留，但超限之后不能再调用这些动作；resume同样硬停止。共享最小私有函数不得把普通失败或max_turns一律改为硬拒绝。失败回执被拒绝或cp.trace异常仍report.ok=false，当次保留checkpoint，不吞KeyboardInterrupt/SystemExit。固定预算提示不能被普通收尾异常覆盖；只有CP明确ok=true且outcome=failure才记已确认失败终结，trace闭合不等于步骤通过。

独立计划审查的真实CP实证：failure finish接受后attempt已终结，检查点只在本次保留；以后显式resume按现有Recoverer删除失效检查点、无openattempt而拒绝，0模型，不自动新建attempt或重放。finish拒绝时旧attempt仍开放，显式恢复可能创建新tracker；本片不保证跨进程旧预算拒绝持续。追加上述两条回归，不改Recoverer或把检查点存在当可继续成功证据。

- [ ] Step 3: 兼容与冻结

expected=0观察、严格300允许/301拒绝、max_turns产物齐备的旧软行为、普通非预算stop及已有产物真实性测试保持。原failure finish拒绝/异常、真实chain停止不启动下一步骤。新矩阵冻结20轮；关联loop、reasoning_budget、runner、recovery、chain、evidence；独立SPEC→QUALITY及7维自检。

- [ ] Step 4: 交付后自动继续

完整preflight三门、compileall≤j6及治理/官网/竞品/diff后提交推送main，核对远端并独立观察新CI。下一片给初次/repair/final推演同一个BudgetTracker，推演计费检查在成功finish之前，chain多步骤同一owner；不能把同一Budget配置当共享账本。跨进程恢复尚无累计usage持久化，要单独定边界，不在本片虚称恢复预算连续。

## 研究与不适配

复用2026-10-08持续对照的PydanticAI固定`f55bb8a6fd6cdb34405e5f523d67cf8f366df4aa` MIT：usage入账后、工具与结果终态之前检查；ICODE本片把该硬门传播到实际契约消费点。OpenHands SDK固定`69e26889401fe69157fff536e6a69049e6644cb3` MIT：多LLM用量聚合暂缓至共享预算片；FINISHED预算豁免和>=阈值不适配ICODE。无源码复制、SDK或新增许可依赖，实际控制面负控是验收依据而非上游文档。

**Execution Mode:** serial implementation, independent research/reviews
