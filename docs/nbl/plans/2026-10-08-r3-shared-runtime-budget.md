# R3 同次工单共享预算与推演前置 Implementation Plan

> REQUIRED SUB-SKILL: nbl.test-driven-development、nbl.subagent-driven-development。先完成契约硬停止片及已确认的CLI恢复sandbox断链窄修复，各自冻结、独立审查、完整门禁及 main 提交；不要并发修改 runner。

**Goal:** 单次进程内工单执行的初次、补救、推演及链路步骤使用同一预算所有者；已观测超限不能通过新 tracker 或成功 finish 后推演绕过。

**Architecture:** 复用 BudgetTracker、AgentLoop 的 charge 后门和契约 failure 硬停止。NativeChainExecutor 每次 execute 创建一次 owner，贯穿它分次调用的单步 run_chain；CLI 单次 run_chain 自建一次并传到步骤。独立 run_contract_step/resume_contract_step 每次调用创建一次。推演在成功 finish 前计费，_finalize 只消费已经完成的推演结果，不重复请求。

## 三问与实际调用链

2026-10-08主代理实际核对 runner、chain、reasoning、sequential、budget、loop 与相关测试：_run_agent 每次构造新 BudgetTracker，contract repair 因而重置；run_chain 只传相同 Budget 配置，不共享累计量。_finalize 在 _finish_step 和清 checkpoint 后运行 run_deliberation，SequentialThinking 直接 complete，不记 usage。run_task 的 repair 与 Reviewer 已共享 tracker，不属于本片重置缺陷，不再做无关改动。

问题真实、已有累计器可复用。影响链为 CLI/NativeChainExecutor → run_chain → run_contract_step → _run_agent，以及 resume_contract_step、run_deliberation → SequentialThinking、ReasoningGate.build_row。独立审查发现 autonomy.execute 将 pending 拆成多次 steps=(step,) 的 run_chain，不能仅改chain而漏真实自主入口；主代理已完整回读该入口。新增参数应为可选关键字，默认调用保持兼容；参数身份冲突必须在模型及控制面写入之前拒绝，不静默采用另一配置。

## Task 1: 单次 owner

- [ ] 完成
- [ ] RED：真实 CP/明确 last_usage 证明初次100+补救201在旧 tracker 分离时继续执行；真实可推进步骤链的累计超限不能仅靠 mock StepReport 成功。
- [ ] 实施：每次独立契约调用创建一次 tracker，初次/补救复用；chain创建或接收一次owner，跨所有本次步骤传递。NativeChainExecutor owner只属于本次execute，不能存实例字段使不同工单串账；现有注入step_runner签名保持兼容，仅明确支持共享owner的原生入口传新参数，不以捕获TypeError重跑副作用，任意自定义runner不计原生预算覆盖。已超限 owner 不启动新的模型或补救；不合并 backend 累计 usage。已有 StepReport.loop 保存它发生时真实累计值，后续推演不得反向改写该回执快照。
- [ ] 兼容：expected=0、300允许/301拒绝、缺失 last_usage 不凭空估算、相同配置与既有调用方不破坏；不同工单/独立调用不得意外串账。公共 CLI 不增加必填项。

## Task 2: 推演计费与成功终结顺序

- [ ] RED：真实产物齐备时推演响应把累计量推到301，旧版仍 success finish/清 checkpoint/transition；前三步已足够而第四步超限也不得写成功推理 trace。
- [ ] 实施：run_deliberation 与 SequentialThinking 接可选同一 tracker。调用前检查；成功响应后按单次 last_usage 记录一次，再检查，之后才解析正文或请求下一步。不把已包含的 reasoning_tokens 重复叠加 total_tokens；不估算失败请求费用或把 backend usage 再加一遍。
- [ ] 推演结果携带明确预算硬停止事实，不能落入普通模型异常降级，也不能被 build_row 的步数>=3判为成功。已有普通异常降级、KeyboardInterrupt/SystemExit透传、L0/L1/不要求trace/L3未实现行为保持。
- [ ] 调整顺序：成功 finish 之前生成并记录本次推理结果，超限走既有 failure 硬停止并保留当次 checkpoint；正常情况下 finish、清 checkpoint、transition/只读 trace仍遵从既有 CP 门。_finalize 不重跑模型、不重复写推理行。预算拒绝不增加后装配、登记、修复或自动落盘动作。

## Task 3: 验收与交付

- [ ] 新矩阵连续20轮，冻结源码/测试 SHA256，记录方法数和SKIP。覆盖 response单次计费、初次+repair、跨步、推演前三步后超限、首调用前已有超限、真实事件链没有early success及checkpoint保留；chain超限后不启动下一步。
- [ ] 关联 autonomy、loop、contract硬停止、reasoning_budget、sequential、runner、recovery、chain、R3回归，保留原正常产物及非预算max_turns行为；必须实际测试原生executor分次chain沿用owner，以及两次execute不串账。独立SPEC→QUALITY，7维自检。
- [ ] 全preflight三门、compileall≤j6、治理/官网/竞品/diff，干净pip安装实际运行路径；完成后main提交推送核对远端、只观察新SHA CI。下一片接可信工程验证计划及契约独立验收，不用更多抽取代替实际产品链。

## 明确不覆盖

这是单次进程内 owner，不是持久工单账本：当前 checkpoint 没有累计 usage；显式重新 resume/重新 chain 调用不能称预算跨重启连续。后续持久账本需要宿主控制身份、调用序号/nonce、usage delta/硬停止事实与幂等恢复，单独设计验收。本片不引入系统服务、提权、Windows晋升实现或模型KEY，不放宽R2/R3评分、平台ready和自动模式。

缺失 usage 仅代表无数据，不证明零费用；已花费模型调用无法追回。预算是运营指标，不是工程质量或90%能力一致性的证明。

## 独立研究取舍（2026-10-08）

PydanticAI固定`f55bb8a6fd6cdb34405e5f523d67cf8f366df4aa`、MIT：[实际agent graph](https://github.com/pydantic/pydantic-ai/blob/f55bb8a6fd6cdb34405e5f523d67cf8f366df4aa/pydantic_ai_slim/pydantic_ai/_agent_graph.py)的 `_record_response_usage`/`_enforce_usage_limits` 与共享state.usage提供同一owner、包装链外硬失败机制参考。采纳响应边界仅计一次和结果处理前拒绝；不适配schema retry重置工程额度。网页核对符号，不声称原字节摘要或网页编号等于原始行号。

Codex固定`1fbe15c962cc3d8eabec36d67987c83cfc4eeec9`、Apache-2.0：[任务取消入口](https://github.com/openai/codex/blob/1fbe15c962cc3d8eabec36d67987c83cfc4eeec9/codex-rs/core/src/tasks/mod.rs)区分BudgetLimited与Interrupted，后者的pending-work续跑不移植到预算硬停止。采纳硬终态与普通中断分离；暂缓持久owner及跨进程自动恢复。成本为少量显式参数和真实控制面负控，无源码复制、SDK或新许可依赖，研究不能替代ICODE动态验收。

**Execution Mode:** serial implementation, independent read-only research/reviews
