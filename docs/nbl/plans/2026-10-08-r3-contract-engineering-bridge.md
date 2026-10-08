# R3 真实合同工程验证接线（依赖证据片）

> REQUIRED SUB-SKILL: nbl.test-driven-development、nbl.subagent-driven-development。本文件是下一片设计，不是实现或验收；先完成工程证据片的冻结、独立SPEC→不同QUALITY、完整守护及main提交推送，再串行修改runner/chain/autonomy/reviewer。用户已授权自动继续，主分支开发，不另建分支。

## 真实问题与复用

2026-10-08主代理及独立只读研究按production基线eead3ad核对：run_task有实际unittest/Git/tree/独立Reviewer，但ctx没有policy；run_contract_step→run_chain→NativeChainExecutor的code/deepcheck尚未消费同等级宿主工程验证。合同产物齐备与CP接受finish不能替代实际测试。工程执行器和证据片是依赖，不由接口存在推定本片已闭合。

复用现有session逐step policy、共享预算、可信broker、EngineeringVerificationRun、新版VerificationEvidence、原Git/tree采样、精确只读Reviewer、CP record_verification及finish/trace/checkpoint；不新造状态机，不让模型或工单JSON成为命令真源。三问已确认：真实缺口、已有复用实现和完整调用链均有定点源码依据。

## 实施顺序与边界

1. **优先接真实合同路径。**NativeChainExecutor在session.policy(step)身份核验及prepare_policy成功后、调用run_chain之前取得宿主冻结计划。计划来自可信服务端配置/宿主提供者，不从模型输出、metadata或工作区临时配置自动采用。无可信计划不能给code/deepcheck成功信用；非代码步骤不硬塞unittest。
2. run_chain转交计划并核对run/ticket/workspace/session/step；run_contract_step在CP或模型写入前预检这些身份、平台及实际可用执行通道。policy存在不等于RL0：已有资源dispatch还要求合格Linux/Landlock/DENY通道；不满足不得退裸subprocess。
3. 从CP step_start取得真实attempt后，所有模型写入、产物补救及宿主装配结束，才执行冻结工程计划。复用Git状态/tree前后窗口；源变化、未知输出/清理、通道失败不签合格结论。不能把旧unittest窗口锚点搬到新检查。
4. 新证据完整audit指纹用于事件记录，稳定repair键仅用于去重。保存回执与事件引用必须对应；记录失败成为阻断checkpoint，不沿用旧缺件补救的warning后继续成功策略。不能旁路CP直接写metadata。
5. 实际测试通过后进行独立代码质量Reviewer；合同原review步骤是计划审查，不冒充此Reviewer。复用精确文件read_file/submit_review/共享预算及审查后tree重核。新工程分支不能仅按exit0称通过，要消费整体evidence.passed及unknown；旧None分支保持原语义。
6. 只有产物、工程检查、Reviewer及CP精确终结全部合格，才clear checkpoint和推进状态。failure终结未确认则保留未决事实；不让scope不明、模型成功文案或末条命令exit0覆盖前败。

宿主计划提供者的具体参数/存储接口须在证据schema验收后冻结，沿用显式kwargs；旧自定义executor不得通过TypeError后重试副作用调用“兼容”。本设计不暗示已有未实现API。

## 旧API、task与恢复保护

- run_task可选计划的默认None继续原Python验证/回执/Git/修复/Reviewer路径。非None普通组只据实提供宿主观察，未知副作用仍human、不能给TaskReport成功或正式隔离信用；单独task接线不是合同或R3闭合。
- 旧None receipt/fingerprint/预算和所有非代码合同能力保持；code/deepcheck无实际工程验收不得由旧成功路径兜底。具体默认推荐必须由宿主明确配置，不能自动安装依赖或执行未经批准项目脚本。
- resume_contract_step目前没有policy/session/plan参数，不能默认继承Native权限。新工程恢复必须经Recoverer重新取得可信会话及冻结计划；缺失时拒绝自动重放，不从相邻JSON补造隐藏argv/env或清理事实。
- 本片不开放Windows自动模式，不豁免macOS单任务额度，不把组级清理变为整树清理；pip-only资源和签名成功不替代平台门。

## TDD与阶段验收

先真实RED，再最小实现，不以loader ImportError或模拟原生成功计产品通过。至少覆盖：

- 错run/ticket/step/workspace、缺plan、policy有但资源dispatch不可用，在CP写与模型调用前拒绝。
- 产物齐备但实际测试失败/零测试/仅build，不能finish success、clear checkpoint或transition。
- 全部测试通过但独立Reviewer blocking、共享预算超限或审查期间源码变化，不能推进。
- 完整检查后计划/工具/源窗口漂移、证据记录失败、失败finish被拒，保留真实未决checkpoint。
- 默认True重复repair不能绕稳定键，原attempt标签与CP执行身份保全；不完整输出/清理不重放。
- resume缺宿主会话/计划不启动；旧None task、非代码chain及既有自定义executor兼容。
- 真实code/deepcheck→chain→NativeChainExecutor→CP事件/回执导出→内置及离仓verify完整往返；离线FakeBackend只证明编排，不证明模型质量或原生隔离。

冻结后新矩阵20轮、runner/chain/autonomy/reviewer/receipt/evidence关联、独立SPEC→不同QUALITY、七维自检、完整preflight、compileall-j1、治理/官网/竞品/diff、干净pip运行。按授权main提交推送并只观察精确新SHA；真实模型1→6及90%平台合同另验，不把本片接口或单平台fixture计整体完成。

## 研究依据与取舍

定点源码：runner.py run_contract_step、_measure_task_verification、_run_task_reviewer、_record_verification_evidence、_finish_step、_finalize、resume_contract_step；chain.py run_chain；autonomy.py NativeChainExecutor；reviewer.py IndependentReviewer。主代理实际回读上述调用点，研究者独立核对相同固定production，不以正在实施的证据WIP推定完成。

沿用持续对照中固定Aider5dc9490与PydanticAIf55bb8a的真实检查反馈、完整结果集合和有界重试机制；**采纳**宿主结果先于成功终结、全部必需检查消费及显式恢复身份；**暂缓**自动技术栈执行推荐与新框架适配；**不适配**shell串联、无测试当成功、调用方布尔值授权重复修复。成本为少量显式参数传递、共享验收窗口与拒绝路径测试；不复制上游源码、不增加运行依赖/权限，许可与固定链接沿用持续对照。收益与验收均以上述动态负控为准。

**Execution Mode:** serial implementation, independent read-only research/reviews
