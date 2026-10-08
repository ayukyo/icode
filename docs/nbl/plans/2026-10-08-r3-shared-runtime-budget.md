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

## 2026-10-08 实施与独立验收记录

本片以 `edc91cb3301936a1d1501437391f3d878576964b` 为基线；以下是实测记录，不代表 R2/R3 整体验收、内核隔离或真实模型能力通过。

Task 1、Task 2 已实现：五模块显式转交同次 owner，NativeChainExecutor 仅在本次 execute 内持有，不给自定义旧签名盲传新参数或重试副作用。成功推演在控制面 finish/清 checkpoint 前执行；预算失败走原硬停止。原 LoopResult usage 保留当时快照。没有增加持久账本或跨重启预算承诺。

有效初始行为 RED 为六个真实控制面方法；另外五个方法为新参数结构性 RED。完整旧源码 RAM 对照中，19 方法有 17 方法包含失败、25 个 failure entries、0 ERROR/SKIP，不能称 19 个全部功能 RED。最终新矩阵 19×20=380 PASS、0 SKIP，282.989 秒。

第一次关联 352 项出现三个旧 fixture 失败，不能计为通过：repair 应累计 302，review 应累计 402；原精确 300 的正控重复回放 done 响应作为未计费推演。主代理仅调整旧测试期望和三个零增量合法推演响应，保留产物、拒绝、checkpoint 和控制面断言。旧 17 项通过；最终关联重跑 352 项，346 PASS、6 个既有平台 SKIP，124.985 秒。

独立 SPEC 实际重跑：新 19/19；关联 174/174；runner/R3 159 项、153 PASS、6 个既有平台 SKIP。额外真实控制证明全部推演发生在 finish/清 checkpoint 前、只写一次 trace/finish、第四步累计 301 阻断、KeyboardInterrupt/SystemExit 原对象透传且不完成控制面。不同代理 QUALITY 独立实跑新19+旧17共36/36、29.323秒，九模块关联316项、310 PASS/6既有SKIP、94.184秒，以及CI覆盖7/7、0.058秒；无阻断，九文件AST/diff及冻结摘要一致。跳过为四Windows、一macOS、一未启用bwrap Reviewer原生链，均不计通过。

主代理离线构建 wheel，在 `/tmp/icode-shared-budget-acceptance-t99umC0g/venv` 干净安装，用 `-I`、仓库外工作目录、移除 ICODE_SKILL_ROOT/PYTHONPATH 实跑六项：repair 301、reasoning 301、精确 300、首调用前超限、真实 chain 累计 301、reasoning_tokens 不重复计费，全部 PASS。五模块安装后摘要与冻结源一致。此处显式使用外部固定 SKILL，只证明安装后 Agent 代码；不冒充免配置纯 pip 安装或内核沙箱。

全仓 preflight 在 CI 补充前 3/3 PASS（实际加载 2029 项）。主代理随后补充跨平台选择合同：新增覆盖方法先真实 RED，再在现有 DEFAULT_MODULES 加入 `tests.test_shared_runtime_budget`，覆盖合同 7/7 PASS；无 workflow 权限变化。独立SPEC补充7/7、0.049秒，确认四workspace平台采用同一默认清单、新19项无平台skip分支、原CROSS50项不变。主代理实际DEFAULT 227项全通过、96.749秒；这是本机而非四远端平台的结果。补充后最终全仓守护于08:34 UTC实际3/3 PASS，发现2030项，不沿用前一次门禁。compileall-j6、治理、官网、竞品排期、diff与子模块无改动检查均通过。

【架构级自检报告】

- ✅ 语法/编译：九文件AST、compileall-j6及diff通过。
- ✅ 依赖/调用链：契约两入口、repair、推演、chain、NativeExecutor及CI注册成对。
- ✅ 逻辑/边界：300/301、调用前超限、预算冲突、快照、两工单隔离通过。
- ✅ 异常处理：普通失败、中断原对象、custom runner不重跑及checkpoint保留通过。
- ✅ 关联模块：上述352项、独立359项和227项实际回归，既有skip不计通过。
- ✅ 兼容安全：observe_only/缺usage/旧可选API保持，无KEY或权限扩张。
- ✅ 可运行性：本机源码、干净安装六项、全仓守护通过；远端平台及整体验收仍独立核验。

冻结 SHA256：

| 文件 | SHA256 |
| --- | --- |
| runner.py | `28897b310b8bb924a07eb59efccd8c66150add2c748e0dfe57c9ad3373b42966` |
| chain.py | `4df82f6172e483dfe4c9ba3ad637eb42a45d64846e4483050f76a4018cd6cada` |
| autonomy.py | `009d96e5c72b1a6da639dc2bf58cb7b5b22a93c125b1380fcfba4758c3857c69` |
| reasoning.py | `322fd1f3842b9ec13891d07893239259b64c0e72d3a54dca41eff37e483756cc` |
| sequential.py | `a7dcba85f1bc917e32aee384e3031c95282478bf966cc7958941decd2e1761d4` |
| test_shared_runtime_budget.py | `4d862a5e23303db3642441f13e45c2344be4352a5b48c8907db374a2d70dcd43` |
| test_contract_budget_stop.py | `51b9d0a6fe00c48ad27e4ec56ff54f35762b74398210edf0c2dcda301b6e21fd` |

**Execution Mode:** serial implementation, independent read-only research/reviews

本片已提交并推送main `edbfbe83a97e1fc2a72beb6b024aa57632696708`，fresh普通ls-remote一致；前两次SSH22/443关闭未计成功，第三次普通push成功。Pages run `37750929989`已成功，deploy `113223719122`实际绑定该SHA、artifact `11538306194`；新SHA主CI及provenance仍独立观察。后续SKILL升级只在本片提交后单独验收，不回写本片20轮的控制面版本归属。
