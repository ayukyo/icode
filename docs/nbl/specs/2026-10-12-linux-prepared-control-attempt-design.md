# Linux S2b1：原始控制面 attempt 与新鲜绑定观察

状态：有限 CP 适配已实施，通过正式新测试、限定回归、独立源码双审、本片唯一原完整预检与最终文档门；精确index及发布待完成。runner/自动模式仍未接线，不表示 S2 或 R2/R3 完成。
母合同：[单步准备与消费](./2026-10-12-linux-prepared-step-scope-design.md)、[S2a上下文适配](./2026-10-12-linux-prepared-tool-context-design.md)。

## 1. 真实缺口、复用与方案

三问已确认：ControlPlane.step_start 对任意truthy attempt调用str，会丢失原值类型；现有attachment绑定和每次borrow已经能调用宿主observer；需要原始回执和真实fresh CP观察，而非新增控制面协议。原 ControlResult.ok 缺省/真假语义也不能用于严格准备链。

源码观察基线main01e22a4：control.py摘要acda84bf6bdec0488199c7c4620e9037203e37968e89d8c2b6a6aa80b765279e，linux_prepared_step.py摘要f165ba45cb07152079c0bb4a3ea1bb3059b7af28a23732cd5b70f74155547075。后者只读。实际实施前重新核当时main，不猜当前deadline发布SHA。

| 选择 | 收益与成本 | 取舍 |
| --- | --- | --- |
| 私有raw start + 有限fresh CP observer | 保留旧接口；准备链能核未经转换的值和当前open_steps | 推荐 |
| 全局收紧ControlResult.ok/step_start | 少一个私有入口，但改变全部旧控制面调用/测试合同 | 不适配本片 |
| 修改ICODE-SKILL接口或本机直接读写metadata/event | 重复已有trace；绕过唯一控制面入口或扩子仓库合同 | 不适配 |

本片只闭合CP适配，尚未把runner或自动模式接上。S2b2继续负责首次模型前prepare、真实调用attach、普通/补救/工程/Reviewer/legacy入口及finally；S2c/安装矩阵继续独立。不把一个validator当作执行授权或完成S2。

## 2. 职责、接口与调用链

```mermaid
flowchart LR
    CP[真实ControlPlane原CLI] --> RAW[私有raw start回执]
    RAW --> B[有限类型与坐标校验]
    B --> V[捕获cp与工单坐标的observer]
    V --> T[每次fresh trace核当前open_steps]
    T --> A[既有attachment bind与borrow]
    A --> H[既有session policy held helper核验]
```

拟给ControlPlane增加私有 `_step_start_result(out_dir, step, *, ticket_id, request=None) -> ControlResult`：复用现有完全相同的step/start argv与确定性request，不先取attempt或str转换。原public `step_start(...) -> str`调用这一入口后，继续原truthy检查、原异常文字和str返回，不全局收紧旧行为；其默认调用次数、run/check参数形状不变。不更改ControlResult.ok、step_check/finish/trace或vendor。

拟新增内部模块 `src/icode/linux_prepared_control.py`，私有函数 `_prepared_control_attempt_binding(control, *, out_dir, ticket_id, step, start_result)` 返回 `(attempt, observer)`。这只是可信宿主runner接线的适配资产，不进工具registry/模型schema/持久化/公开包接口。本片不修改runner调用点；后续runner必须自己直接取得raw start，不从调用方模型字符串或checkpoint还原许可。

函数验证原始ControlResult及data容器、精确int returncode==0、data.ok is True；step为精确str且等于可信输入，attempt为精确str、非空白、无ASCII控制字符。拒绝bool/int/list/dict/object等attempt，不str补救，不使用宽松result.ok。可信ticket/step也须合法非空字符串；out_dir来自已建立的宿主工单目录，捕获固定Path值与实际ControlPlane引用，不接受dict或任意callback冒充控制面。class/字符串通过本身不认证执行权。

原start没有ticket_id；不能要求不存在的字段或假造run_id/session。幂等回放已有ok/step/attempt/event_id/input_digest，但没有phase；不能强制phase=start而拒绝合法回放。event_id/input_digest不是本片授权依据，不新造schema或猜格式。

observer捕获上述真实control/out_dir/ticket/step和已校验的attempt，不从后来调用实参反取预期身份。首次供现有 `_bind_attempt`调用、随后每次borrow再调用：实际query `control.trace(out_dir, limit=1)`，精确校验原ControlResult、int returncode0、data.ok is True；data.ticket_id须精确str且匹配捕获ticket，data.open_steps须精确dict，对应捕获attempt条目须精确dict，其中step须精确str且匹配捕获step。不要求trace顶层step，真实接口没有此字段；实参attempt必须精确等于捕获值。全部成立返回None，否则固定输入无关ControlError。不能缓存PASS或在trace失败时回退到start/磁盘事件/旧receipt。

limit=1只限制显示events；固定vendor21566a5的execution_trace先归约全部验证事件的open_steps再截取records。即使显示窗口没有目标start，真实未结束attempt仍可在open_steps；真实已finish则应拒绝。新鲜观察不是跨系统事务/锁：不承诺CP查询之后绝无外部变更；现有可信宿主禁止并发修改合同与每次实际borrow重核保持。

适配资产不拥有helper/session/lease/FD，不attach/finish/close或产生第二step start。runner后续在自己的栈中将返回attempt和observer交既有attachment；既有真实session/policy/hash/FD/消费状态核验不能被CP成功替代。原linux_prepared_step.py的状态机和callback返回None合同不改。

## 3. 错误与兼容边界

普通CP异常、坏回执/缺字段/错工单/闭合或错step均固定拒绝，异常正文/路径/原data不出固定错误。KeyboardInterrupt/SystemExit保留原对象传播，不用普通错误包装中断。CP子进程和既有存储由原ControlPlane拥有；本适配没有额外OS资源，不以观察成功授任何清理信用。

全旧接口/旧调用者保持原行为，新的严格分支只能由后续准备链显式使用。不新增kwargs到custom step_runner、普通None路径或模型。模块顶层不得因Linux-only依赖导致Windows/macOS import失败；有限CP适配可便携测试，真实Linuxattachment部分条件收集，不以skip授能力。

## 4. 验收与精确范围

六发布路径：control.py、新linux_prepared_control.py、新tests/test_linux_prepared_control_attempt.py、本DESIGN、对应PLAN、docs/agent-landscape-live.md。runner/tools/chain/attachment/core/native/vendor/CI及当前deadline六路径只读；不同片不混提交。main-only，TEST与不同SOURCE依序、独立双审和root唯一完整预检；原完整门启动后当前冻结源码不动。

至少验证：

- raw入口一次原run/完全相同argv与request，返回原ControlResult引用，无类型转换；旧step_start真假检查/str返回及错误文本保持。
- 严格start类型/字段/returncode/ok/step矩阵；缺接口时使用signature-aware/guarded真实目标断言，不能把缺模块/TypeError当RED。
- 实际固定子仓库CP创建临时工单、原start、同request幂等回放（无phase）、真实trace limit1；不得mock trace正例代替事件链。
- 当前open attempt在显示窗口外仍合法；CP真实finish blocked后旧observer拒绝，随后以不同request真实新start产生不同attempt，不接受旧binding/错ticket/错step；不能用同request幂等回放冒称新attempt。
- 绑定及每次真实attachment borrow均重新query；绑定后CP闭合/事件链破坏不得触及wrapper/payload，scope仍由原外部创建者结束/关闭。错误或信号不提前授bound，不自建替代owner。
- raw坏值和trace异常的有限负控可注入结果选择seam，但须区分它们和真实CP/attachment正例；回归control/runner/retry/budget与prepared模块，非Linux正常collection。

temp fixture只允许新建隔离目录内CP工单与必要git init/add/commit，不改本仓/vendor或用户工程。模型double不供应真实模型、六步或90%一致性信用；本片不执行KEY调用、不翻ready。DESIGN双审→完整PLAN双审→正式作者/root有效RED→不同源码作者/rootGREEN与回归→fresh源码双审→原完整门→最终文档/精确index→root一次main发布。当前deadline发布前只准备本文与研究，不开本片TEST/SOURCE。

## 5. 研究与设计自检

独立只读研究2026-10-12实际GET固定OpenHands SDK3934349da2db0433238621542173a00a8af7439c（MIT）：08:18:42及08:19:05 UTC核[state.py恢复身份与重建事件视图](https://github.com/OpenHands/software-agent-sdk/blob/3934349da2db0433238621542173a00a8af7439c/openhands-sdk/openhands/sdk/conversation/state.py#L526-L561)，08:19:07核[workspace结果分账](https://github.com/OpenHands/software-agent-sdk/blob/3934349da2db0433238621542173a00a8af7439c/openhands-sdk/openhands/sdk/workspace/models.py#L20-L42)，08:18:44核LICENSE。08:19:05 UTC另核Codex27065a91ccbf5ba8532844be3777fcf83b77820d（Apache-2.0）的[真实thread.started身份与turn结果](https://github.com/openai/codex/blob/27065a91ccbf5ba8532844be3777fcf83b77820d/sdk/typescript/src/thread.ts#L77-L141)及LICENSE。有效文件均HTTP200；tree API403、猜测路径404未作为证据，未刷新HEAD/二十名单。

**采纳（设计输入）**原始字段保留、明确身份配对、消费时重新观察、结果与生命周期分账；ICODE已有CLI/attachment observer，收益是避免类型洗白与旧PASS缓存，成本为有限适配及真实CP负控，无新增依赖/权限。显示窗口与authority分离的直接证据来自本地固定vendor，不能归功于上游。**暂缓**跨step缓存、全事件重放、全局结果schema、旧ok/step_start收紧及runner/原生合流。**不适配**上游Pydantic对象、workspace赋值或TypeScript强制转换当runtime认证/执行授权；字符串身份、typed result不能证明ICODE的lease/helper/隔离。仅借机制、不复制源码或修改子仓库。

技术设计技能用于职责/接口/流程与验收；Java/Spring/HTTP/MQ/SQL模板不适配，不引入框架。用户已委托常规推荐方案自主推进，故不为有限既定合同重复询问；新扩权或验收改变仍须必要确认。本文先独立审查，没有实施放行。

【架构级自检报告】（设计范围）

- 语法/编译：真实符号/CP字段已核，新源码未实施。
- 依赖/调用链：复用原CLI、full-chain trace与attachment observer，不另造授权通道。
- 逻辑/边界：类型/回放/显示窗口/闭合/每次新鲜观察明确。
- 异常处理：固定普通拒绝、首信号原对象传播；无新资源。
- 关联模块：六路径；当前冻结片及runner/attachment/vendor只读。
- 兼容安全：旧公开语义不收紧，无权限/依赖/schema新增。
- 可运行性：仅设计，不授正式TDD、原生或S2/R2/R3完成。

## 6. 正式实施记录（2026-10-12）

批准DESIGN35fa3722与PLAN855091d7分别经独立SPEC→不同QUALITY零遗留后，正式不同TEST作者/root在原control基线取得16/15有效callable assertion失败/0error/skip（均0.003s、exit1），旧公开compat通过。这些guard失败不授其后矩阵已执行。
不同SOURCE作者/root随后新16实际GREEN（5.620s/5.190s，0F/E/skip）及限定八模块196 GREEN（41.456s/39.682s，各5旧平台skip）；compileall-j1/diff通过。actualcontrol ffdaec53c10a23deed7b4383415fe48e1b54af706bee908a4f80fdece127c5ff、新module875635c99689a7e95c6c5d48670727f1453ef3fa05fa6ebf714440747d3596a0、TEST20868a62bff6138ce3f1ff8d25faf25ed14b57a69fb6f92c22503d5606d22f80；旧attachment/vendor未变。
fresh实际SOURCE SPEC及不同QUALITY均C0/I0/M0，各独立新16 GREEN（5.136s/5.270s）；root唯一原fullguard session74867于09:10:18 UTC开始，日志 `/tmp/icode-cp-prepared-preflight.dOMmDP/typescript`，当前仅secrets/submodule确认PASS，全量结果待原footer，不借旧片完整门。资产提取诊断失败和正式证据在PLAN保留，不伪装产品失败或有效RED。
同一原guard最终09:20:00 UTC日志footer `COMMAND_EXIT_CODE="0"`，root09:20:20 UTC取得三门全部PASS及session exit0；三freeze不变。原守护成功时不输出全量数量，因此不猜测试数量/skip。只授本片原软件完整门，最终文档/精确index/实际发布与新CI仍分账。
阶段末研究仍沿第5节实际GET固定提交/许可证及原观察时点，无新的HEAD或二十名单刷新、源码复制、依赖权限变更。仅授本片有限CP/实际attachment软件验证；不授runner/原生installed/自动ready/模型六步/90%或整体信用。
三DOCS原scanner两轮各raw0/exit0、fresh secrets/submodule及diff均通过；最终状态记录更新后仍重复两轮原scanner/单门校验，再执行精确六index。批准设计/计划与后续追加实际文件摘要分账，不将未来S2b2 DESIGN/PLAN混本片发布。
