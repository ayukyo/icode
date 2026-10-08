# R3 宿主工程验证计划与契约独立验收

> REQUIRED SUB-SKILL: nbl.test-driven-development、nbl.subagent-driven-development。先完成共享预算片的冻结、独立审查及交付，随后实施本片；不并发修改runner。当前是设计，不是已具备能力或验收证据。

## 真实缺口、复用与调用链

2026-10-08主代理核对当前主分支：run_unittest固定当前Python的参数数组 `-B -m unittest`，_measure_task_verification只执行该命令。run_task已有宿主测试窗口、受测tree、修复账本及全新模型Reviewer，可复用；run_contract_step→chain→NativeChainExecutor的code/deepcheck仍主要根据必需产物和CP门禁终结，没有接同等级宿主工程测试/独立语义审查。不能把单独靶场成功、模型生成测试说明或inspection清单等同真实研发工单已验证。

本片解决非Python工程验证及真实合同链缺口，保护已有unittest与task receipt消费者；复用有界输出/清理、VerificationEvidence、VerificationLedger、_measure_task_verification的Git/tree窗口、现有结构化Reviewer及控制面原生验证记录，不另造事件状态机或以更多抽取代替产品链。

## 1. 可信验证计划

- 宿主在Executor首调用前冻结VerificationPlan：平台适用范围、步骤/任务身份、命令id、kind（build/lint/test）、argv数组、工作区内cwd、有限timeout/output、测试结果适配器以及确定性摘要。命令不从模型回复或执行中可写文件自动采用；工单内副本仅作展示，不能成为宿主下一轮真源。
- 保持现run_unittest的旧API、默认命令、零测试拒绝、输出预算与中断合同。新计划入口为可选显式参数；省略时仍是原Python测试，不在此处默认执行未知项目脚本。
- 新工程验收计划不能为空，至少一个required test和合格结果适配器；显式区分not_run/missing_command/unknown_adapter/failed/passed。build-only或非required test不能关闭测试门，旧API兼容不能成为code/deepcheck未运行工程检查仍success的fallback。
- 工作台可展示易懂的“准备检查/正在验证/检查未通过”，预先识别技术栈只生成建议。已批准的自动任务可消费宿主冻结配置；会话模式可先确认推荐检查，不要求普通用户记CLI术语。未经授权的安装、外部上传、网络扩大或新系统工具不能由“自动发现”默许。
- 限制命令数量/参数长度及总输出；不拼shell字符串、&&或临时script，不接受工作区外cwd/路径逃逸。构建并发不超过6，拒绝不受控的-j/已知高并发配置，不能仅提示模型遵守。
- 模型开始后更换计划必须停止当前验收，显式建立新计划/测试窗口，不重用旧fingerprint；计划摘要、命令身份与平台结果须进入回执。

## 2. 实际运行及证据

- 每条命令使用当前任务同一隔离边界。策略化合同必须走既有可信执行broker及单命令RL-0，不用宿主普通subprocess绕开policy；验证进程自身是该命令payload，真正宿主监督程序仍不计入额度。
- policy执行复用真实resource及USER_NOTIF broker的可信argv/环境/结果合同，而不只是sandbox.wrap。runtime/adapter缺失明确拒绝；payload_started=false只能源于确认未spawn/可信阶段事实，其它未知保持unknown，不推断“没有执行”。
- 复用测试前后Git/完整工作树窗口，计划前后身份一致。执行逐条有界，失败、超时、启动/I/O错误、输出不完整、漂移或资源channel未确认即失败关闭；不继续下一命令或模型修复/Reviewer直至有完整新证据和既有有界修复许可。
- 多命令分别保存真实退出码、输出摘要、环境、plan digest、step/attempt与受测tree；不能只取最后一条退出0覆盖前面的失败。聚合结论必须由每个必需检查决定，旧单命令回执继续兼容且不伪装为新版多检查结果。
- 零测试不能通过。unittest保留真实summary门；其它框架须有明确实际结果适配和正/负控。未知命令exit0只证明该命令成功，不证明存在测试/覆盖充分，不能拿build-only关闭工程测试门。测试进程输出仍受项目代码影响，证据证明已执行的观察事实，不是独立质量认证或不可伪造测试计数。
- 不自动安装或升级项目依赖来把环境故障变绿。缺工具/缺依赖单独归类，与代码缺陷、合同缺件、模型能力和未知副作用区分。

## 3. 合同接线与独立Reviewer

- code/deepcheck在success finish、checkpoint清除和状态前移前消费宿主工程结果；失败则真实failure终结或保持CP未决，不制造成功事件。plan/review/merge等非代码步骤继续原合同，不硬塞unittest。
- 测试成功后，到Reviewer与CP成功终结之前再次核对宿主计划、受测tree和全部必需结果；若failure终结回执被拒绝，保留checkpoint/openstep，不伪造已关闭或清checkpoint。
- Reviewer与Executor隔离上下文，复用只读精确文件与submit_review合同；输入由宿主选出的变更和验证证据构造，不能只审模型总结。缺报告/非法JSON/证据引用失配/未读完整对象/申请写或越权工具均失败关闭。
- Reviewer计入本次共享预算；其越限不能被真实测试exit0软化。只有artifact齐备、必需测试及Reviewer通过、CP终结被确认，才能推进软件研发步骤。
- 原靶场run_task继续兼容。新合同能力必须测试真实chain和原生executor，不仅单独API；Windows/WSL或其它Reviewer边界不合格时保持该路径不可用，不用NoIsolation正控外推正式隔离。

## 4. TDD与整体验收门

- RED：真实非Python检查命令无法由现接口表达；两个命令前失败后成功仍拒绝；运行中计划替换/受测tree漂移拒绝；合同产物齐但测试失败不得success/清checkpoint/transition；真实测试通过但独立Reviewerblocking不得推进。
- RED还包括空计划、仅build、非required test、缺runtime/adapter、exit0但无实际测试，以及原默认合同未执行检查不得fallback成功。
- GREEN：至少Python默认兼容、显式多命令及一个非Python实际build/test fixture，缺工具与零测试负控；执行上限、stdin/EOF、超时、清理、异常/中断、plan identity、回执导出→独立验证器往返完整。模拟分支或shell打印测试数不算目标技术栈真实测试。
- 最终矩阵20轮、关联runner/chain/autonomy/reviewer/receipt/evidence、独立SPEC→不同QUALITY、7维自检、完整preflight及compileall≤j6、治理/官网/竞品/diff，干净pip安装运行，再main提交推送/核对远端及精确SHA原生矩阵。
- 真实模型1→6另有隔离靶场与明确费用/KEY边界，必须在工程验证/平台前提具备后实际运行。离线FakeBackend和本片接口不替代90%SKILL能力一致性、真实模型质量或R2/R3最终退出条件。

## 调研取舍（独立固定源码复核，2026-10-08）

独立只读研究固定Aider `5dc9490bb35f9729ef2c95d00a19ccd30c26339c`，取得完整args/main/base_coder/commands/run_cmd原字节与[Apache-2.0 LICENSE.txt](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/LICENSE.txt)，无本地缓存/摘要，不声称缓存证据。官方[lint/test文档](https://aider.chat/docs/usage/lint-test.html)说明可配置test-cmd/auto-test及编译检查；实际[base调用](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/coders/base_coder.py#L1585)在edited且auto_test时调用[cmd_test/cmd_run](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/commands.py#L993)，底层[run_cmd_subprocess](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/run_cmd.py#L62)确有shell=True、实际read/wait/exitcode。主代理独立raw回读base和run_cmd关键段及LICENSE头；commands的本机raw读取TLS EOF，未将该次错误当读取成功，commands链以独立研究的完整读取为依据。

采纳“项目配置的编译/测试及真实错误反馈”机制，成本为显式宿主计划/多检查证据/合同接线；不复制源码、不加Aider依赖或许可义务。不适配shell串联、无限输出、格式化二次成功口径或模型临时选择验收命令。独立静态审查发现空test_cmd时cmd_test返回None，而base用not test_errors设置test_outcome；这是源码推断，不声称上游动态复现。ICODE必须区分not_run、failed、passed，空计划/无测试不能默认成功；该研究不替代产品动态验收或R2/R3门。

**Execution Mode:** serial implementation, independent read-only research/reviews
