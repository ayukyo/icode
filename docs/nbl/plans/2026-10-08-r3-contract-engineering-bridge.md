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

### 编码回归片之后的接口冻结（设计，未实现）

工程证据依赖已推送b508；该SHA新Windows离仓回归优先修复，再串行实施本片。第一合同片只修改autonomy/chain/runner/reviewer及其定点测试与CI选择，不同时改旧task默认验收、自动项目脚本发现或原生资源后端。

- NativeChainExecutor新增宿主可选`verification_plan_provider: Callable[[ExecutionContext, SandboxPolicy], VerificationPlan] | None`。仅原生`run_chain`适配器的code/deepcheck在session policy准备成功后调用一次；provider缺失/异常/返回非精确计划类型均阻断本步模型调用。provider以policy.run_id和step冻结身份，不能用ExecutionContext中不存在的run_id。旧可信自定义step_runner保持原kwargs签名，不探测/重试；它不是本片原生工程验收通道，不能外推R3信用。
- run_chain/run_contract_step显式`verification_plan=None`；策略化code/deepcheck缺plan、plan/policy/工作区/环境/工具/适用步或平台不匹配、resource dispatch不可用，在CP写和模型调用前拒绝。旧无policy直接调用仅保留开发诊断兼容，不得到Native正式工程信用；非代码步骤不执行计划。policy准入不代替实际资源运行回执。
- 真CP step_start attempt贯穿检查、工程事实和记录，不用repair_round冒充。全部模型写入/产物补救/宿主装配后，复用新鲜Git/tree窗口实际执行计划一次。宿主检查可能有副作用：用现OperationRecorder的managed_write完整计划动作，在执行前start，已知完成后finish；unknown/清理未确认/异常不得伪造payload_not_started或关闭歧义动作，保留checkpoint供人工核对。
- 复用build_engineering_evidence和save_verification_receipt；仅新增工程分支严确认CP record_verification，不改旧缺件warning辅助函数。首次回包核对rc0/okTrue、合法event_id/run_id及run中kind/device_test、layer/unit、scenario、outcome、完整audit evidence与baseline。幂等回包没有run，须核对already_applied/确定性request_id/run_id/event_id；上游对完整输入幂等冲突硬拒。trace不包含verification_recorded，不能拿trace缺行或猜测字段作确认。保存失败、记录失败或绑定不符均阻断。
- _run_task_reviewer新增可选policy/workspace_session，两个ctx均转交。策略化合同使用tighten_policy对同一run/ticket/step身份收窄write_roots为空、网络DENY、排除工单目录；不修改现derive_read_only_reviewer_policy的review专用合同。精确read_file/submit_review及Guard仍复用；只读工具/静态policy不冒充另一套OS Reviewer隔离实测。IndependentReviewer新工程分支消费evidence.passed/unknown，而旧None保持原退出码分支。
- 测试合格后才运行独立代码Reviewer；Reviewer后重核源/tree/计划身份。工程检查/质量审查/记录/终结均合格才成功；原_finish_step精确身份确认与_finalize保守verification_pending保留。新工程回执以宿主冻结audit摘要命名保存在工单控制区，StepReport只公开回执路径与门结果，不公开argv/env；实际导出验收显式消费保存回执，不宣称CLI自动发现尚未实现的接口。
- resume_contract_step新工程分支显式接收可信plan/policy/session及工作区，先重核Recoverer的真实attempt和副作用状态，再复用同一工程终结门。不能从metadata/checkpoint恢复权限或默认推导Native workspace。缺可信身份拒绝新工程自动重放；旧非工程诊断恢复保持。run_task可选工程计划为随后独立片，本片不改默认None行为。

方案的兼容边界是旧诊断接口与宿主TCB适配器保留、正式隔离合同增加实际工程门；不把缺省provider阻断误写为工作台已可自动完成。CLI/工作台安全宿主计划配置与真实模型矩阵仍是后续总门。

同日宿主配置专项只读核对：现Settings和cmd_workbench均无provider来源，仓内TOML静默加载不可直接升为执行授权。独立研究与根代理均实际证明工程unittest.py可遮蔽-B -m unittest；根代理正式Python3.11.15/实际broker环境RAM为rc1/partially initialized module，隔离-I前缀加discover实际1测试rc0，但当前VerificationCheck明确拒绝-I。随后独立片应先stdlib可信启动与shadow负控，再干净pip的CLI配置→工作台→provider往返；高级宿主模板只从明确仓外配置冻结checks，身份由session派生，坏配置不fallback、不自动安装工具或依赖。当前执行器只观察可执行对象与框架输出，未认证整套stdlib/依赖；本片不重写适配器，也不能称默认工作台已自动可用。

身份补充：policy/plan.run_id为宿主session身份，EngineeringVerificationRun.attempt为CP step_start真实值，operation attempt为CP动作身份，record_verification返回run.run_id为控制面新生成UUID；不能把后者与宿主run_id做相等判断。首次核对回包UUID/at和期望payload，replay核对其既有run/event身份与确定性request。保存路径必须同时区分实际step attempt和完整audit（用有界安全摘要，不把argv/env或不可信路径拼入），保留已有原执行标签；同audit的不同attempt不能互相覆盖，冲突或不可确认既存回执要阻断，不另造静默覆盖恢复规则。

### 合同、链路与生命周期审计范围

`scope/boundary`：b508软件基线（编码修复后新SHA实施），Native单次可信policy code/deepcheck→CP接受工程及质量终结；没有物理硬件操作。真实入口已明确，entry-detection不适用；跨层主路由为端到端与状态重放，不套用嵌入式协议/枚举/Broker专有技能。

| Dimension | Producer contract | Consumer contract | Current gap / evidence | Match status |
|---|---|---|---|---|
| 身份 | policy run/ticket/step/root，CP真实attempt | plan/check/Reviewer/终结同一执行 | b508尚无合同plan转交 | unresolved |
| 结果 | 全部check有序结果，unknown单列 | 整体evidence.passed与审查结果 | 旧合同只检查产物 | unresolved |
| 持久确认 | 首次run对象或幂等ID回包 | rc/身份/完整audit必须确认 | 旧helper只看ok | unresolved |
| 兼容 | None旧格式/非代码/诊断/可信adapter | 不擅自扩大参数或执行授权 | 显式kwargs、无TypeError重试 | design |

5个编排模块（autonomy/chain/runner/reviewer/control）、5个明确入口；本片限定链路清单至少15条（模块×3启发下限），不是全仓init链路或90%覆盖证明。逐条的nodes/edges正负证据须在实现验收表补齐：N1 provider缺失，N2 provider异常/一次调用，N3 session策略准入，C1 plan身份，C2 step/platform/env，C3资源拒裸退，R1全部写后执行，R2真实attempt与新窗口，R3未知动作恢复，R4保存/记录，R5审查前后源漂移，V1整体unknown，V2两个只读ctx和共享预算，P1首次/replay确认，P2精确finish/checkpoint/advance。当前只有静态缺口证据，这15条动态状态均unknown；不得仅按列表数量标proven。

| Gate/state | Owner | Read by | Written by | Cleared/restored by | Observed decision |
|---|---|---|---|---|---|
| frozen plan / policy | 可信宿主单次调用 | 工程executor/Reviewer | provider/session | 每次重建，不从JSON恢复授权 | 待实施 |
| step attempt / checkpoint | CP/Checkpointer | 新检查/Recoverer | step_start/save | 仅精确success清除，未知保留 | 复用既有，不推定新门通过 |
| host command operation | CP/OperationRecorder | Recoverer/finish | 执行前start/已知后finish | 未收束不重放、不由下一请求清除 | 待接线 |
| engineering audit / receipt | 宿主与CP事件 | Reviewer/export/verifier | measure/save/record | 不覆盖原执行标签，重放核对ID | 证据片本机通过，合同消费缺失 |
| shared budget | Native调用本地owner | 全部step/Reviewer | 真实模型用量 | 下一调用新建，单次修复不重置 | 既有owner复用，新增消费待验 |

| Dimension | Initial state | Stimulus | Expected state/effect | Observed / cleanup | Status |
|---|---|---|---|---|---|
| immediate | step与动作已start | 实际测试失败/unknown | 无成功/前移；未知动作和checkpoint保留 | 新合同门未接线 | unobserved |
| converged | 失败收尾在途 | 无新业务请求观察CP | 已知failure确认或明确未决，不靠下一请求清理 | 待真实fixture | unobserved |
| restart | 持久checkpoint/事件存在 | 新进程恢复 | 不从可写JSON授plan/policy，不重放歧义动作 | 待重启夹具 | unobserved |
| replay | 记录已存在 | 同request与迟到/重复结果 | 完整身份幂等；不同窗口不能替代前败 | 待首写/replay实际回包 | unobserved |
| rollback | 保存/记录/finish边界 | 取消或局部失败 | 不删除已写事实，不假清checkpoint/动作 | 待故障注入 | unobserved |
| failure | 各门正控 | 源漂移/预算/记录/终结故障 | 拒绝成功、完整可恢复状态 | 待负控 | unobserved |

`breakpoints/support_ceiling/verdict`：最后已观测为b508证据保存/离仓本机链；首次缺边是Native宿主计划及合同结果消费。合格策略、声明或CP finish都不能越过未知边。当前本片`unobserved`，无动态产品或user_visible/physical信用；硬件故障矩阵not_applicable。独立研究可改善设计，不能填充上述动态证据。

| Node | Role | Input | Output/state | Observation | Status |
|---|---|---|---|---|---|
| Native/chain | 可信入口与编排 | host context/session/plan | 单步policy与预算 | 基线已有session，无plan | unknown |
| contract runner/executor | 产物后工程验收 | CP attempt与冻结检查 | 完整工程run/receipt | 执行器与证据已有，合同消费缺失 | unknown |
| code Reviewer | 独立质量消费 | 精确文件与整体evidence | 结构化发现与源复核 | task已有，合同与双ctx policy缺失 | unknown |
| CP/导出/verifier | 持久与独立消费 | 完整audit与回执 | 记录、终结、可验包 | 首写/replay结构已静态读取，新合同未实际走通 | unknown |

| Source | Target | Transport/mapping | Precondition | Positive evidence | Negative evidence | Status |
|---|---|---|---|---|---|---|
| Native | chain/runner | 显式verification_plan kwarg | 同一步policy/session | b508静态接口缺失 | 缺plan预期拒绝尚待RED | unknown |
| runner | executor→Reviewer | 真attempt/新鲜Git窗口→整体evidence | 全部写入已结束/实际通道 | 独立执行器已有源重核 | 合同产物不能替代实际测试 | unknown |
| runner | CP→export | 保存回执/严格record/finish | audit与首次或replay身份对齐 | vendor精确回包已读取 | trace没有verification_recorded | unknown |

| State/artifact | Lifetime | Owner | Written by | Read by | Cleared by | Restored from | Invariant |
|---|---|---|---|---|---|---|---|
| plan/policy/budget | 单次可信调用 | host/session | provider/session/usage | executor/Reviewer | 调用结束 | host新建，禁止JSON权限恢复 | 不跨ticket共享 |
| step/op attempt | 单个CP事务 | CP | start | runner/Recoverer | 已确认finish | 真实持久事件 | 未闭合副作用不盲重放 |
| checkpoint/receipt | 持久窗口 | host/CP | save/measure | Recoverer/export | 仅成功清checkpoint，事实不删 | 文件与事件比对 | 原execution attempt不可改成repair标签 |

| From | Event/guard | Round check | Side effect | Compensation | To | Evidence | Status |
|---|---|---|---|---|---|---|---|
| 未启动 | 身份/资源准入失败 | policy与plan完全核对 | 不CP写、不模型调用 | 无副作用可补偿 | blocked | 新负控待实施 | unobserved |
| step/op运行 | unknown或记录失败 | CP真实attempt | 工程命令可能已执行 | 保留事实/未决动作/checkpoint | human或未确认failure | 未决不可假清 | unobserved |
| 工程已知完成 | 检查/Reviewer/记录全过 | 同源窗口/共享预算 | CP精确finish/transition | 拒绝则保留checkpoint | success仅确认后 | 正负控待实施 | unobserved |

`classification/skill_routes`：合同结果未消费为端到端缺边（primary end-to-end-functional-chain-audit）；真实attempt/副作用恢复为生命周期（primary state-lifecycle-replay-audit）；输出编码漏洞是另一个最小CLI边界，不并入合同万能修复。当前两合同问题均unresolved、severity重要，已有符号/固定vendor/动态负控为输入，期望各15链路表及六维重放证据；无缺失技能fallback。`gaps/leaks_and_conflicts`：新合同实际结果、首次/replay确认、恢复和故障收敛均未观测，修复owner为下一片串行实现者/root验收，不能用下一轮成功抹掉前轮未决状态。

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
