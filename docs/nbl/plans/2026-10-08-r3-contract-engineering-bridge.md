# R3 真实合同工程验证接线（依赖证据片）

## 2026-10-08 实施冻结窗口（本机阶段门通过，提交推送中）

实现者已停止源码写入，提交前production HEAD 为 `aaaa448c3cfd7d859e894e87c627be156c77a65d`。冻结候选的定点矩阵为37个合同方法（32可移植、5 POSIX）及12个CI选择方法，共49 PASS/0skip；最后关联窗口119 total/118 PASS/1既有opt-in skip/0FAIL，76.446秒。跳过项为 `test_bwrap策略化reviewer由runner派生策略并隐藏宿主账本`，不是新增合同正控。随后独立SPEC49/37.762秒与不同QUALITY49/37.796秒均0FAIL/0ERROR/0skip并批准；根代理同49项20轮980PASS/0skip/747.797秒，七源码摘要及CRLF夹具摘要未变。根代理扩大关联330 total/325PASS/5既有skip/0FAIL（162.396秒）、DEFAULT367PASS/0skip（159.765秒）、干净安装20外层PASS/0skip（52.240秒，含安装版37新合同子测0skip）通过；最终完整守护见下文，新SHA线上原生结果另验，不允许仅据部分单门提交。

扩大关联的5个跳过明确为macOS zombie/ps、Windows Job分配及两同步pipe取消原生语义、Linux策略Reviewer opt-in；不计通过。干净安装子进程先导入安装版四生产模块并核SHA、随后仅载入源测试夹具，37方法后再次核生产模块路径/SHA及包内SKILL来源，避免helpers加入src后误测checkout。工程证据/pack生产摘要保持原样；旧安装回归及三编码0/1/2控制也保留。它验证安装输运，不验证Windows/macOS原生通道。

最终完整preflight实际3/3通过：2201 total＝2142PASS/59skip，466.044秒，0FAIL/0ERROR；仅透明打印原unittest返回的末尾统计，不改守护行为。Go1.27.1仅本次进程PATH、GOMAXPROCS=1、GOFLAGS=-p=1、CMake并发1；未读KEY。compileall-j1、治理、双语官网、竞品排期、密钥、子模块及diff分别通过；结果文档补录后再核非测试守护与全部冻结摘要，源码无变化。59skip不计原生通过，也不消除默认历史正文债务。阶段按授权main提交推送，线上只观察精确新SHA；此处没有宣称R2/R3总门通过。

| Frozen file | SHA-256 |
|---|---|
| autonomy.py | `0d47c0541c22482f6baaddda76785e15fb24a6dcb68c1bc3aea2be8a89b475b3` |
| chain.py | `ba914983114dbd2cbed11d730e6d3cb6a0bd8564bf8e1c6737ce8303a9619125` |
| runner.py | `2b145db41b3ebbd0f90f3e9d8b19e73b9ca6a08c97e1ba5fbe59d6d777ea671b` |
| reviewer.py | `5066760c6dec8ef9f63c805329b990febfd675778e6c8d3bdb9d25498b49942b` |
| run_workspace_ci.py | `e159867925ef5c1b8234aef8b307356c3d8b06cb067e978114e708402c82c8b0` |
| test_contract_engineering.py | `1ebc2287d5209a3858f9fa6f0f7b25bdd0ac22e25357b52657939ab490e48eba` |
| test_run_workspace_ci.py | `83cf05a70098e7ed3431f7365e0e4bd966abdb961d64e5c7a5b986908ce7e32e` |

本候选已覆盖缺计划/身份与资源拒绝、全部写入后的检查、真实attempt/动作、严格首次及replay确认、双Reviewer只读上下文/共享预算、源码与CP保护重核、checkpoint失败保留及原始baseline恢复。A+B恢复夹具实际经过Reviewer读两文件与CP工程记录，但普通合同产物故意缺失，checkpoint仍保留，不是完整恢复success。原baseline复用现snapshot的250000项/128深度/256MiB预算，缩放边界夹具没有进行巨量分配；冻结副本防调用者后续修改，不证明宿主原始采集时刻或自动持久化。

Native code/deepcheck软件正控实际经过真实CP→保存/导出→内置/离仓验包，但其命令输运与模型是测试适配，不授原生隔离/模型质量信用；清单由宿主真实读后一次登记最终正文。默认增量inspection旧正文缺失的独立负控仍失败关闭，历史正文债务没有消除。初始设计与unknown表保留其原观察窗口，下面新增SPEC的15链路/6生命周期表只记录明确软件观察，不能将静态表或方法数量当90%总覆盖。

### 独立SPEC的实际软件连接表

不同审查者已完整核对本片需求、diff及执行/Reviewer/恢复/finish上下文，实际49定点37.762秒，0FAIL/0ERROR/0skip；7 SHA测试前后相同，SPEC APPROVED、Critical/Important/Minor均0。以下仅固定候选的软件连接观察；不同QUALITY、根代理重测与平台门另验。测试方法均位于 `tests/test_contract_engineering.py`，不是仅凭静态声明标proven。

| 链路 | 实际正负观察 | 判定上限 |
|---|---|---|
| N1 provider缺失 | `test_policy_code_missing_plan_refuses_before_control_write_and_model` | CP/模型前阻断 |
| N2 provider异常/一次 | `test_native_provider_required_and_exception_are_stable_before_adapter`、两个Native验包正控 | 宿主单次调用/稳定失败，不是自动配置 |
| N3 session策略 | `test_session_identity_mismatch_refuses_before_cp`、Native正控 | policy准备与session核对；transport不授原生信用 |
| C1 plan/root身份 | `test_wrong_plan_binding_and_unavailable_resource_refuse_before_cp`、同bytes不同CP根负控 | 实际root/devino/CP绑定 |
| C2 step/platform/env/tools | `test_plan_environment_platform_directory_and_tool_drift_refuse_before_cp` | 写入前拒绝错身份/漂移 |
| C3资源拒裸退 | 缺通道负控与 `test_build_only_and_required_not_run_plan_never_gain_quality_credit` | 无合格通道不成功 |
| R1全部写后执行 | `test_contract_consumes_gate_after_last_artifact_registration` | 一次宿主验收位于末次登记后 |
| R2 attempt/窗口 | `test_host_gate_failure_saves_full_actual_attempt_and_records_failed_cp_run`、工作区控制区漂移负控 | 真实CP attempt及检查窗口，不忽略账本变化 |
| R3未知/重复动作 | `test_exception_after_confirmed_start_retains_unknown_action`、两个action replay负控 | 已完成不重复；未知不假闭合 |
| R4保存/记录 | `test_save_record_and_operation_ack_failures_retain_checkpoint_without_quality`、Native验包正控 | 完整audit保存与确认，失败不授质量信用 |
| R5审查后漂移 | `test_saved_complete_binding_is_rechecked_before_final_step_finish`、真实protected输入终态重核 | 源/Git/plan/tool/CP新鲜窗口 |
| V1整体结果 | zero/skipped/nonzero/unknown与build-only/not_run负控 | 不能按最后exit0成功 |
| V2双ctx/预算 | `test_finalizer_context_keeps_policy_session_and_same_shared_budget`、Reviewer各失败负控 | 精确只读与共享预算；非OS Reviewer实测 |
| P1首写/replay | strict record两个方法实际首写/replay及畸形回包负控 | canonical UUID/完整payload/确定request |
| P2 finish/checkpoint | 两个Native精确finish正控、save/record/ack失败保留 | 成功确认后才清；后续MCP/transition仍独立 |

| 生命周期维度 | 实际观察 | 仍未观测/不外推 |
|---|---|---|
| immediate | 准入/同bytes不同CP根在模型与CP写前拒绝 | 不代表所有平台准入 |
| converged | legacy code/deepcheck→精确CP success→软件验包 | 默认增量历史正文仍失败，新birth 1→6未跑 |
| restart | checkpoint新进程/逐turn marker；显式原baseline的A+B Reviewer与CP记录 | 无自动持久原baseline；A+B普通产物缺，非resume success |
| replay | 同request工程动作及完成动作恢复拒绝再次执行；strict记录幂等确认 | 没有自动复用已完成工程结果 |
| rollback | 实现者既有5项cancel/stale/late回归通过 | 新工程完整rollback仍unobserved，不填已通过 |
| failure | 结果/预算/源/保存/记录/动作/finish各负控阻断并保留事实 | 非穷尽故障认证 |

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

深化研究已记为下一[Python隔离模板独立设计](./2026-10-08-r3-python-isolated-template.md)：精确-I discover形式及root绑定先TDD，-I非-S与可伪造框架摘要的上限明确保留；旧分支和本片合同WIP不因只读研究给信用。非Git合同沿既有空Git字段语义，采用实际source snapshot稳定窗口；Git可用时继续核对真实HEAD/tree。不得新增强制Git要求或把空Git当稳定证据。

身份补充：policy/plan.run_id为宿主session身份，EngineeringVerificationRun.attempt为CP step_start真实值，operation attempt为CP动作身份，record_verification返回run.run_id为控制面新生成UUID；不能把后者与宿主run_id做相等判断。首次核对回包UUID/at和期望payload，replay核对其既有run/event身份与确定性request。保存路径必须同时区分实际step attempt和完整audit（用有界安全摘要，不把argv/env或不可信路径拼入），保留已有原执行标签；同audit的不同attempt不能互相覆盖，冲突或不可确认既存回执要阻断，不另造静默覆盖恢复规则。

### 实施中发现的两个边界（设计补充，尚未冻结验收）

- 工程checkpoint新进程resume若没有plan/policy/session，不能转入旧裸模型诊断分支。仅复用既有stop_reason保存负向常量`engineering_verification_pending`，初始及每turn保留；它只要求显式可信输入，不保存或恢复argv/env/权限。实际事件/未决动作与真实attempt仍由Recoverer核对，marker不授权；旧非工程恢复语义不变。此方案的新进程/迟到结果/标记与错误收尾仍须动态验证。
- deepcheck的已登记code_files是固定vendor保护的metadata_files输入（含真实文件hash），无改动深检合法且必须审查现有实现；旧task Reviewer把审查范围等同本轮非空diff。不能以dummy源码改动、假baseline或覆盖code_files绕漂移门。推荐内部显式scope：仅策略化合同deepcheck消费CP本轮已捕获且检查通过的protected code_files实际file facts；本轮changed_files和baseline仍为真实diff（可空）。两Reviewer上下文按精确固定范围完整read/submit、只读/路径/链接/控制区/64文件上限不变，终态仍重核本轮diff/snapshot/Git/plan/tool。旧task/code保持非空diff默认；提示区分现有源码审查与本轮新增，不虚称新引入。范围/内容漂移、缺/空/额外范围或保护门拒绝均阻断，metadata任意list不是权限。该行为已发用户可选确认，未收到回答，不称已确认；在已授权合同范围按可逆推荐TDD继续，独立SPEC/QUALITY及完整门另验。

定点复核补充：新record工程确认须核对固定CP真实canonical UUID event_id及run_id，而不是任意安全字符串；旧warning helper不变。固定源码事实读取在打开正文前复用宿主2MiB单项及累计预算，事件链继续既有1MiB行/64MiB总量/100000事件流式预算，不以声明size授权无限读。当前helper是POSIX no-follow/dir_fd实现，CI明确分开可移植编排和POSIX捕获/深检方法；Windows不选这些POSIX正控，不能用skip、模拟FD或软件输运补原生信用。新SHA各平台实际执行结果另验。

恢复原始差异补充（实施中）：Checkpointer v1没有原source baseline，CP start仅保护HEAD及合同输入；恢复时新采样会漏掉同attempt中断前的A改动。新工程resume沿已有名称显式要求可信宿主`change_baseline`原始快照映射，验证格式/限额后复制冻结；缺/坏快照在模型/CP写前拒绝，不能从可写JSON、聊天摘要或恢复时新snapshot补造。Reviewer仍消费原baseline→当前的完整A+B差异；原CP root/HEAD/attempt及未决动作仍独立核验。合法最初空工程可用空映射，旧非工程诊断兼容不变。该宿主TCB输入不证明自动持久化或独立认证原始采集时刻，默认工作台缺原baseline仍须阻断；已发用户可选确认，未收到回答，不称已确认。真实A+B覆盖/缺坏快照负控及冻结复核另验。

这不是放宽深检源码保护或新增工程自动修复：如确实修复导致保护输入漂移，沿既有route失败/新轮语义处理。真实CP还要求inspection_worklist、逐阶段实际Read、coverage及源码artifact；测试须满足它们，不造MCP trace。nonGit自查可能保留真实“无受影响Git仓库/差异覆盖不可用”债务，正控用实际临时Git库并如实界定；生产nonGit窗口语义不变，不因夹具新增强制Git要求。

### 真实导出链暴露的历史正文缺口（实施中，未关闭）

同日真实code正控在仓外宿主控制区已走到工程检查、独立Reviewer及精确CP success；尚不能据此宣称完整导出链通过。固定vendor的`inspection prepare/read`每次覆盖同一路径并登记各版本sha；现`evidence._snapshot_artifacts`对每条历史事件只复制当前路径正文，`ArtifactBroker.submit`也仅原子替换而不留历史。旧版本正文因此缺失，实际pack自验拒绝。这是默认增量生产链的兼容缺口，不只是断言或夹具问题；不得忽略历史sha、删除旧事件或降低验证门。

本片可另设有明确上限的软件正控：宿主用既有`inspection_worklist.build_worklist`派生真实范围，逐required phase实际读取每个文件并核对sha，一次提交完整最终清单，再让真实CP `prepare(resumed)`及check验证身份/范围/来源并登记正文。这是既有支持的最终正文生产路径，不能冒充默认逐次CP read、模型语义审查或历史版本归档已修复。保留原增量路径失败回归及未关闭债务；后续独立历史正文片须完成增量producer→保存→export→内置/离仓verify真实往返后，才关闭该缺边。本片不修改evidence、pack verifier或vendor。

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
