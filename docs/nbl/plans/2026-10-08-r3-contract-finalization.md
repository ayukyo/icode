# R3 契约收尾与检查点确认

> 本片先于宿主工程VerificationPlan接线，修已复现的收尾顺序，不代表工程测试/Reviewer或R2/R3整体完成。REQUIRED SUB-SKILL: nbl.test-driven-development、nbl.subagent-driven-development。

## 三问、来源和实际缺口

真实问题：独立只读研究实际运行现有runner/固定169 CP，在临时工作区用FakeBackend/NoIsolation执行，不读KEY。真实plan产物和必需checks齐备但推演空响应时，报告失败，CP却已经记录success且checkpoint已删；状态前移由thinking_gate拦住，未观察错误completed。另一真实resume缺before_transition时，CP拒success、openstep/checkpoint保持，但_finalize仍调用transition并被CP拦住。

已有实现：ReasoningGate.build_row/append_trace、StepReport检查点、CP step_finish、预算失败收尾的独立trace、原Recoverer及chain停步。复用已有判据和控制面，不新造状态机或复制推演。调用链：CLI step/recover/chain→run/resume_contract_step→_finish_step/_finalize→chain→NativeChainExecutor。主阶段基线root `fd68b1f77d9050776e3e2fd263d19b4931affa66` / vendor `1693651c1bd7daad3272eb054f0f81d6f254d08d`；研究复现时旧主分支的runner/chain字节与该基线相同，不把本机NoIsolation称正式隔离。

## 实施边界

1. 先执行一次原共享预算推演；hard-budget路径保持原直接失败且不写thinking trace。其后将原_finalize中的build_row/append/检查点块移到私有_record_deliberation，在finish之前消费，失败落真实degraded行；无trace步骤不加失败或伪造行。原等级/下限/解析和能力判据不改，不重复模型、计费或append。
2. missing、已知false检查或report.error决定failure，不能只看文件存在。初始report.ok=False不是已知失败，不能因此拒所有正常任务；max-turn/backend循环软提示继续按原warning合同，不替代真实推理门。
3. 仅rc0、ok is True、outcome等于请求值且step/attempt精确一致才确认finish；未确认先清空本地finish_outcome，保留checkpoint。真实CP幂等成功没有phase字段，不能加错误的phase必需条件。非0+JSON成功/异身份是消费端transport负控，不宣称默认CP已有该错返。
4. 仅确认success且当前检查通过可尝试metadata/transition；metadata新增false后再次拒前移。failure/拒绝只做trace观察；trace未确认不声称无未闭合动作，report.ok要求确认success。保留原链路对状态门拒绝的单独解释，不扩成新状态机。
5. 普通finish调用异常不覆盖原失败，也不阻止后续trace；同一KeyboardInterrupt/SystemExit对象透传。检查点的后续处理仍由Recoverer读真实CP决定，本片只保证失败收尾当下不删；不承诺关闭failure后再次resume盲目重放模型。

## TDD与关联验收

新六方法修正夹具out_dir缺项后，实际10个FAIL、0ERROR，包含四真实CP顺序窗口与transport/已有false检查；新增身份四FAIL、metadata拒绝一FAIL、DEFAULT接线一FAIL皆单独复现0ERROR。早期缺out_dir、metadata Mock不可迭代、chain缺requirement等fixture ERROR均修正，不计作产品RED或通过。

新15方法包括七真实CP场景：run/resume空推演、真实缺检查拒绝、成功trace先于finish且单行、幂等finish、max-turn空推演、真实chain不启动review；其余覆盖transport身份/状态、已有hard false/error、metadata失败、finish异常/中断、无trace步骤和未知trace。新模块在DEFAULT只接一次，CROSS50/权限不变。最终关联与20轮/独立SPEC→不同QUALITY/完整preflight/compileall≤j6及main发布另记。

旧max_turns正控只给一次write tool-call，FakeBackend重复空content造成真实reasoning degraded；旧success恰是本片漏洞，不应为保持夹具错误放过该失败。补三次有效JSON且零费用的真实推演响应，原max_turns/loop.ok False、产物/post计数与checkpoint消失断言不变，另加四调用/成功推演断言。已有正常backend软提示、预算300/301、修复/reset与恢复合同仍关联测试，不放宽门禁。

## 持续研究取舍（2026-10-08）

独立只读复核[Aider固定5dc9490](https://github.com/Aider-AI/aider/tree/5dc9490bb35f9729ef2c95d00a19ccd30c26339c)，原[Apache2 LICENSE.txt](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/LICENSE.txt)。采纳真实检查结果决定后续动作；不适配[base](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/coders/base_coder.py)与[commands](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/commands.py)空test None按无错误成功的静态口径。源码推断不是上游动态复现，未复制源码/增加依赖。ICODE自身问题由真实CP回执证明，不用竞品设计替代测试。收益是成功事件/恢复上下文与已知检查一致，成本为收尾顺序及消费者回归；许可证/运行依赖/系统权限不变。

## 未覆盖

尚未接宿主工程验证计划、非Python适配器、合同独立Reviewer、真实模型1→6或90%能力矩阵。Windows正式启动及macOS单任务quota仍独立未通过。KEY未读取/上传，不更改自动模式或readiness。

**Execution Mode:** serial implementation, independent read-only research/reviews

## 本机冻结结果（2026-10-08）

五文件SHA256：runner `08820bae2d3cd2993e232c1d42d25a93dd4bf42e3eea2ec7143f5b648f1290ae`，新测试 `931484d6cf892362077a76f15a2f3ec920612bf091011665dca5512c55734199`，旧budget fixture `852b966b2fbccd52112ede21192d1621dfa718caa31104954e9450a0d3df6fae`，DEFAULT script `1e8235d5db9bd777f35b6db208aa0abb47d9617104f32339b156d67f34d28d09`，CI接线测试 `0e7efd9675f461bba420632be6010f80166431a76289689df276d4f7b4e79f63`，完整门禁前后保持一致。

最终新15+CI9实际24 PASS、0SKIP、5.927秒；新15方法20轮300 PASS、0SKIP、112.507秒。最终十消费者244项OK、5既有skip（239实际PASS）、111.645秒；DEFAULT253 PASS、0SKIP、107.584秒。早载入缺requirement夹具的244项错误运行不计通过；误拼不存在reasoning_gate模块的一次158项ERROR也不计通过，没有以这些错误报告产品根因。

独立SPEC：24 PASS、0SKIP、6.085秒；八旧消费者186项OK/5既有skip（181实际PASS）/82.047秒；RAM仅旧HEAD复得四真实CP顺序场景4FAIL、0ERROR、0SKIP、4.166秒。五SHA/AST5/diff保持，未写源码。macOS/Windows及未启用policy Reviewer的五skip不计该平台验收。

最终全仓preflight于2026-10-08 10:14 UTC三道全部PASS，发现2083项；守护成功不打印全部skip明细，不称2083全部零skip。compileall-j6/governance/site/严格竞品/diff通过；不同作者QUALITY与主分支提交/原生新SHA结果另记，当前未将部分结果说成R2/R3完成。

不同作者QUALITY：新24 PASS、0SKIP、5.790秒；正确八消费者177项OK/5既有skip（172实际PASS）/77.595秒，合201发现/196实际PASS/5SKIP。最初误选不存在test_reasoning的import ERROR不计通过，已更正并重跑。另三个真实CP追加写入OSError/KI/SystemExit边界通过：无finish/transition，checkpoint/openstep保留，中断同对象；RAM旧HEAD四真实CP负控4FAIL、0ERROR、0SKIP。前后五SHA/AST5/diff一致，无阻断。不同作者关联模块组合不同于SPEC，不强凑相同数量。

【架构级自检报告】

- ✅ 语法/编译：AST5、compileall-j6、JSON/文档及diff通过。
- ✅ 依赖/调用链：run/resume→record→finish→finalize→chain/CLI完整，控制面唯一写入口保持。
- ✅ 逻辑/边界：实际空推演/缺检查/幂等成功/chain停步及transport负控通过。
- ✅ 异常处理：finish普通异常保留原因，trace失败关闭，追加写入/中断实际负控通过。
- ✅ 关联模块：本机244项无失败/5既有skip，独立SPEC及不同QUALITY无回归。
- ✅ 兼容安全：max-turn软提示、300/301共享预算、无trace步骤、幂等phase可选与Recoverer保持。
- ✅ 可运行性：本片Ubuntu离线真实CP及DEFAULT253/全仓3守护通过；新SHA异平台/模型/总门另验，不宣称100%整体验收。

## 精确提交的远端终态

实际提交推送main `71a3d2c726903fb701d10bb8380952c7bc741fd0`，远端ls-remote及GitHub分支API核对一致。独立只读观察已结束：相同SHA [主CI37763592180](https://github.com/ayukyo/icode/actions/runs/37763592180)44 jobs、39成功/2旧Windows Reviewer失败/3skip；Python3.11与3.12各2083项、71skip、324.346/528.923秒。DEFAULT Linux253/0skip/101.059秒，macOS253/0skip/215.107秒，Windows x64与ARM64各252/9skip/154.074与260.098秒。新15方法由DEFAULT和全量发现链纳入，但聚合日志不是逐方法日志，亦未单独运行本机24项命令，不倒填。

两个旧Reviewer job为113265696118/113265696228，step7仍78!=0；Job已执行且cleanup_ok=true，固定诊断connect=10035/wait=timeout/fd=false/enum_not_attempted，不能称根因修复或生产Windows可用。相同SHA [provenance37763592173](https://github.com/ayukyo/icode/actions/runs/37763592173)validate加四原生矩阵5/5成功，四组license各9项零skip，实际attestation/gh oracle/安装后offline API/六类严格串行密码学负控/setup拒绝/wheel上传通过；聚合负控日志不说成六条独立日志，launch仍false。[Pages37763592207](https://github.com/ayukyo/icode/actions/runs/37763592207)validate/deploy成功。三轮均已终态STOP，不rerun或反复查询，不以39/5/2个子门替代R2/R3总体完成。
