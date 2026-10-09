# Linux 实际工程验收与控制面证据连接设计

日期：2026-10-09。基线 main `8d53670192e3e2cbfebaa0300d697fb3036308be`，vendor `1693651c1bd7daad3272eb054f0f81d6f254d08d`。本文是独立静态设计，未实现、未执行生产模块、测试、helper、编译、安装或模型 HTTP。当前作者仅新建本文及配套研究文档；没有提交、推送、修改生产准入或访问私有 KEY。

用户既有连续推进、自主决定阶段、main-only 授权覆盖脑暴技能的例行问答等待、分支/worktree和逐任务提交惯例。方案 A 是 root 依据该授权作出的阶段选择（sequential-thinking 142–144），不是用户新增回答。作者另完成需求→复用方案→风险三步结构化检查。后续计划、实现、测试、提交与线上观察由 root 接续；本作者到文档交付即 STOP。

## 问题与现有实现

真实缺口是实际 Linux 命令证据尚未接入完整工程验收往返的正控。`tests/test_contract_engineering.py` 已覆盖真实 CP、工程 gate、Reviewer/tree、receipt/pack，但 `gate_fixture` 替换 `_uses_resource_dispatch`/`_controlled_dispatch`，末尾完整往返还使用 `TransportSandbox.policy_contract_ready=True`。它证明编排合同，不能证明真实 Linux dispatch、资源管理或 Native 准入。

现有实际组件可以复用：registry `run_command` → `_controlled_dispatch` → `execute_linux_resource_observed_command` → `LinuxTaskScope`/资源通道与 USER_NOTIF → 原 helper。`TestLinuxProductTaskQuota` 正控使用真实 manager/helper，`capture_scopes` 只包装原 `configured` 作观察；故障注入负控必须独立标为 injected_fault。已安装 wheel 的 `probe_installed_linux_violation_receipt.py` 同时核 AF_INET 拒绝、AF_UNIX 正控、cap=1 fork 配额、普通 exit13 与收束。

已有正式工程入口为 `run_contract_step(...verification_plan=..., workspace_session=...)`；内部 `_contract_engineering_gate` 使用同一个 CP step attempt，创建另一个 `managed_write` operation attempt，执行 frozen plan、构建 tree 绑定证据、确认 operation finish、保存 receipt、`record-verification`、运行 fresh Reviewer，再核 plan/tree。`_finish_step`、普通 required_checks、产物、推演、MCP、transition/advance 是后续独立门；工程 gate 或 Reviewer 通过不等于 step_finish success，更不等于六步完成。

四个不能隐去的边界：

1. `LandlockSandbox.policy_contract_ready` 固定 False；`NativeChainExecutor.execute` 在 session 策略检查处拒绝它，先于 provider/step runner/模型。本片不改这一事实，不使用子类、monkeypatch 或假 `ready=True` 正控。
2. Landlock 单一代码读写根不能表达根内 deny carve-out。Workbench POSIX 已使用 `WorkspaceManager(...isolate_git_metadata=True)`；真实 Git session 把代码放 `checkout/code`，Git 元数据、runtime、receipts、原 source 等留在外部并加入保护。必须复用它，不能删保护、把 `.git` 移回可写根，或用无 session 临时目录冒充真实 session。
3. 直接 runner 的 `_contract_plan_error` 检查资源 dispatch 与 wrapper 存在，不调用 `prepare_policy`；实际包装时才核完整当前可表达子集。因此原入口不能泛称任何包装失败都在 CP 前零写。本验收驱动须先对实际 `session.policy(step)` 调 `sandbox.prepare_policy(policy)`，拒绝不兼容拓扑后才开本次 CP 工程窗口；这只是验收驱动检查，不修改生产入口时序。
4. 分离布局当前存在确定的生产接线阻塞：`checkout/code`没有`workspace/.git`，`runner._capture_task_git_tree_oid`（3647–3651）返回`workspace_not_repository_root`，但`_read_task_git_state`（3841起）会沿父层获取非空Git身份。`_contract_engineering_gate`的`source_stable`（1802–1805）在有Git身份时要求`tree_status == stable`且`before_status == captured`，因此该布局必然被工程门拒绝。仅新增验收测试不能使L2a/L2b/ENG-06正控通过；须先由root另立并独立审查session-aware Git tree投影生产修复设计。本作者不设计或实施该生产修复。严禁移动`.git`、清空Git身份、替换tree捕获、降低断言或把Native设为ready来绕过。

## 方案取舍

| 方案 | 决定 | 收益与成本 | 验收/兼容边界 |
|---|---|---|---|
| A：连接现有真实组件与 CP/evidence | 采纳，Git投影修复是前置依赖 | 验收补齐；需要实际宿主、same-run身份、失败/清理矩阵 | 本文仅设计验收；root另立session-aware Git投影生产修复设计并验收后才能进入L2正控，不改Native flag |
| B：使自动模式 ready | 暂缓 | 可进入 Native，但必须满足完整政策和全部平台条件 | 当前 false 不被本片测试数量、资源子门或新签名抵消 |
| C：迁移 bubblewrap | 暂缓 | 可能支持 nested deny，代价为新执行/打包/许可/跨平台合同 | 先复用已有分离元数据布局；不复制上游 bundled bwrap |

相关上游的采纳/暂缓/不适配、固定提交、许可与读取范围见[独立研究记录](2026-10-09-linux-engineering-bridge-upstream-research.md)。不增加任意语言/命令、依赖安装、提权、manager服务配置、普通 subprocess fallback 或自动重试。

## acceptance_contract

| Expected behavior | Required layers | Consumers | Scenarios | Environment/device | Baseline | Pass criteria |
|---|---|---|---|---|---|---|
| 真实 Linux 资源/拒绝回执被工程控制面消费 | static、host command、host CP/evidence、model_double | helper、broker、plan、CP、Reviewer、pack verifier | 正控/确定失败/不完整/漂移/并发/拒绝 | 非 root Linux、实际 kernel/systemd/cgroupv2、当前解释器 | 上述 main/vendor，source helper与binary/manifest绑定 | 每个具名必需门实际通过、无 dispatch/receipt 替身；缺行或 skip 不授信用 |
| 普通 code/deepcheck 合同仍约束推进 | host CP/evidence、model_double | run_contract_step、required_checks、MCP、finish/advance | code 与 deepcheck分别、负控保留原拒绝 | 同 session/ticket/tree | 同 frozen plan/attempt | 普通门按原合同实际响应；仅当实际 success 才报该层成功 |
| Native 当前仍拒绝实验后端 | static、host rejection | NativeChainExecutor | 真实 session、真实 Landlock | 相同基线 | policy_contract_ready=False | isolation_unavailable且未调 provider/step runner/模型；此前trace/safe_point/intent写入如实记录 |

## 最小分层与实际接口

### L1：复用现有实际命令验收

实施前先按已有接口运行 `python -m unittest tests.test_linux_product_task_quota.TestLinuxProductTaskQuota tests.test_linux_violation_receipt.TestLinuxViolationReceipt`；解释器取项目当前实际 Python，保持其 lexical venv 路径，不解析成另一个 Python。模块/class是真实存在的；本设计没有执行这些命令。完整方法逐项记录 pass/fail/skip，不把 fault injection 或测试内 mock 的负控写成纯原生正控。已安装层继续使用现有 `scripts/run_native_wheel_ci.py` 所建干净环境和 `scripts/probe_installed_linux_violation_receipt.py`，不在用户环境安装，也不下载 artifact 替代本地来源核对。

### L2a：Git投影前置修复后的工程 gate 与实际 CP/evidence 连接

基线8d的真实分离Git session不能通过该工程门，这是已知阻塞，尚非可仅用新增测试完成的连接层。下述正控接口是前置session-aware Git tree投影生产修复独立设计、实施、验收通过后的验收目标；修复前最多独立完成L1与实际plan命令层观察，或记录原门的确定拒绝，不能宣称L2a完整成功。

新增验收测试文件 `tests/test_linux_contract_engineering.py`，仅复用生产接口，不改生产文件。fixture 的 source/data/control/pack 是四个相互不重叠、明确归属的临时根；临时 source 是专用 Git fixture，不操作仓库 main 的 checkout。建立可运行的一个 unittest与一个被修改源码，在变更前真实 Git commit（仅 fixture）并核返回码。使用 `WorkspaceManager(source_root, data_root, project_id, extra_protected_paths=(settings.skill_root,), isolate_git_metadata=True).open(ticket_id, run_id)` 取得真实 session；git metadata与源码控制根位置由 manager 决定，不手工拼假的 `WorkspaceSession`。

用真实 `LandlockSandbox(helper=..., manifest=...)`（源码编译层）或 `LandlockSandbox.from_bundle()`（installed层）并核非空。从 `session.policy("code", process_limit=8, wall_timeout_seconds=30, output_limit_bytes=65536)` 或 `session.policy("deepcheck", ...)` 取得 policy，先真实 `prepare_policy`。code与deepcheck的初始baseline/源码固定时点分别按下面两条时间线，不能共用“step_start之后改源码”的fixture流程。

Plan 使用现有构造签名：`VerificationCheck("python-unittest", "test", (str(executable), "-I", "-B", "-X", "utf8", "-m", "unittest", "discover", "-s", str(root), "-t", str(root)), "unittest_summary_v1", timeout_seconds=5, output_limit_bytes=65536)`，`VerificationPlan(root, policy.run_id, ticket_id, (check,), steps=(step,), platforms=("Linux",))`。root精确取`session.workspace_root`，不由模型/项目配置提供。该 grammar、Plan身份和冻结环境已存在，不另造 adapter。

CP 使用真实 `ControlPlane(settings)`；在代码树外创建受控 fixture 工单，`create(...metadata_json=json.dumps({"project_path": str(root)}))` 绑定工程对象，`action-policy`必须返回相同 ticket/`execution_root`。不将任意 `active_checkout` 当可信：现有vendor会额外核Git拓扑/状态。按对应时间线调用真实 `step_start`取得CP attempt，完成该步真实 required_checks与必要固定输入。若CP拒绝步骤/输入，L2a为blocked，不能绕过或覆写事件/元数据取绿。

| 步骤 | 必须保持的时间线 |
|---|---|
| code | 真实session与计划输入就绪→在源码变更前采集baseline→真实step_start→在本次attempt内按已定计划改源码→固定最终源码→真实工程测试/Reviewer/tree重核。工程测试窗口内及之后不得再次写源码 |
| deepcheck | 真实session内最终源码就绪→通过真实metadata入口固定code_files及审查范围→采集该最终源码baseline→真实step_start捕获源码与范围→只读审查/真实工程测试/Reviewer/tree重核。step_start后不得改源码、改范围或重新捕获输入；任何此类变化仅作拒绝负例 |

deepcheck正控不为制造非空diff而在开始后改源码；它由CP保护的固定范围驱动Reviewer。保留`deepcheck_source_mutated_after_step_start`和`deepcheck_scope_mutated_after_step_start`负例，确认原门拒绝且不重捕获/不重授权。

在Git投影前置修复通过后，code按本次attempt的计划变更、deepcheck按开始前固定的最终源码，复用实际 `_contract_engineering_gate`，参数按其当前签名传 `cp/out_dir/ticket_id/step/attempt/report/plan/policy/sandbox/workspace_session/workspace/baseline/git_baseline/operations/backend/requirement/loop_config/budget_tracker`；`OperationRecorder(...scope=step)`、`StepReport`与BudgetTracker保持原逻辑。这是内部工程窗口验收，不注册新模型工具、不用Native伪准入。成功时须观测实际一次计划运行、operation start/finish、资源/违规通道、tree前后与Reviewer后重核、唯一工程receipt和真实verification_recorded。此层不调用step_finish强行关闭，也不把仍open的step说成功。基线8d如形成operation/receipt/CP记录仍须保留其实际结果，不能因这些局部观察消除tree投影门的拒绝。

`load_verification_receipts([actual_receipt_path])`严格载入；`build_evidence_pack(out_dir, dest=fresh_pack, gates_json=settings.gates_json, verifications=[row], clean=False)`导出部分工单，返回 `.ok`与 `verify_pack(pack)==[]`各独立断言。独立验证器在另一个cwd/新进程调用当前解释器 `-I -B <pack>/verify.py <pack>`，限时15秒；实际exit0才授独立结构验包信用，不把它叫来源认证或工程质量认证。partial pack如因真实open步骤合同被拒绝，记录具体拒绝并停止该层；不修改verifier放行。

### L2b：直接 runner 的完整当前步骤连接

L2b与L2a同样被基线8d的分离Git tree投影阻断，必须先通过独立生产修复门；不能用直接runner或legacy fixture消除该阻塞。code和deepcheck沿上述两条时间线，deepcheck在runner内部step_start捕获前已经固定最终源码和审查范围；其模型工具/host post_write不能在开始后改源码或重新捕获输入。

复用同一个真实session/policy/Plan及外部control根，使用现有 `run_contract_step(settings, backend=..., workspace=root, step=step, ticket_id=ticket_id, sandbox=sandbox, policy=policy, verification_plan=plan, workspace_session=session, out_dir=out_dir, post_write=...)`。先取得合法CP步骤入口；可复用现有测试的明确legacy fixture与真实migration，但必须标`fixture_seed`，不得称已执行前三个模型步骤。不能通过修改生产step_runner、替换 `_finish_step`、`_contract_engineering_gate`、`_uses_resource_dispatch`、`_controlled_dispatch`、CP响应或receipt来满足正控。

确定性backend仅驱动真实工具调用/合法submit_artifact、完整Reviewer read_file/submit_review与既有推演输出；标签固定`model_double`。`post_write`复用chain既有机器装配方式和vendor inspection接口，实际读取指定源码、计算读阶段hash并由原worklist validator验证，不能填虚假reads/覆盖coverage。普通合同、inspection/worklist、deepcheck fixed review_scope、artifact登记、required_checks、thinking/MCP、final binding、step_finish与finalize/advance全部走原路径。前置修复后，若合法装配仍不能满足普通门，保存原拒绝；只交付实际已过的层，L2b明确blocked，不预设L2a成功。不得补造缺失成功事件。code/deepcheck分别跑，不能从一个步骤外推另一个。

### L3：Native负控及真实模型未授信用

使用真实 session 的Native入口观测 `isolation_unavailable`；实际调用AutonomyManager/RunControl现有入口可产生trace/safe_point/intent等控制写入，应将模型/provider/step_runner“未调用”与整个run“零写入”分开。不改`chain_steps`让Native绕门，不覆写policy ready。真实模型账户/full endpoint尚待确认，本设计不猜、不读KEY、不发模型HTTP；model_double不授语义审查质量、真实1→6、自然成功率≥90%或R2/R3整体信用。

## 身份与可观测证据

新验收驱动的本地run清单绑定：repository main/vendor、被读生产文件SHA256、native源SHA256、实际helper二进制/manifest摘要、实际解释器lexical/resolved身份与版本、UID、kernel/arch、systemd版本、cgroupv2及实际同UIDbus/peer检查、本次session/run/ticket/root inode、Plan digest/environment/executable_identity、CP step attempt、operation name/attempt、base/head/object_format、tested tree/worktree fingerprint、resource receipt摘要、工程receipt fingerprint、pack摘要。只保存必要公开版本/摘要与闭结果，不输出私有路径、argv/env/模型正文或完整manager stderr。

这些关系分开核：`public_plan.run_id == session.run_id == policy.run_id`；`row.binding.attempt == row.run.attempt == actual CP step attempt`；operation名称由`engineering- + sha256(step + "|" + attempt)`派生，operation attempt另外从真实CP取得；`record-verification`返回的UUID是CP验证记录run_id，不等于host `policy.run_id`。通过已保存fingerprint与真实verification_recorded的evidence/baseline连接CP记录，不强制UUID等同host run。资源回执本身没有run/attempt/unit公开字段；只能由可信宿主同一次调用的实际scope/私有通道/返回对象绑定并记入本地清单，不在生产schema虚增认证字段。

读取日志、stdout/stderr和unittest summary只证明观察到报告；项目代码能伪造框架输出。独立pack验证的是内容/合同一致性，摘要不是签名认证。Reviewer为独立模型上下文、只读工具/Guard与snapshot核对；`read_only_verified`不是独立OS进程沙箱证明。

## 具名正负验收矩阵

全部是后续验收要求，当前结果均`blocked: not_executed_by_design_author`。每方法保存实际层、入口、环境、observed、结果，子向量不虚增方法数。

| ID/具名场景 | 正控或负控及实际观察 | 允许结论 |
|---|---|---|
| CMD-01 `registry_quota_and_thread` | 原cap1 fork/pthread EAGAIN，payload计数1，supervisor在外；cap2 setsid不能第三task | 单命令真实task quota；不授全run预算 |
| CMD-02 `deny_and_unix_positive` | AF_INET真实USER_NOTIF闭回执；AF_UNIX socketpair实际成功无违规 | 已覆盖seccomp类别；Landlock文件拒绝不误记该类别 |
| CMD-03 `ordinary_exit_and_forged_stdout` | exit13无OS拒绝；伪ICQR1/JSON不能改实际host resource | 普通失败/通道来源区分；不是stdout防伪认证 |
| CMD-04 `bounded_command_cleanup` | 正常/timeout/outputlimit各实际scope收束，unit not-found、ControlGroup空、pinned路径消失、launcher回收 | 只属本次owned scope；unknown不得写true |
| CMD-05 `setup_and_ack_failure` | 缺bus/root/mismatch/tool/cap、observer/receiver/ack失败；marker不出现。注入故障单列 | 失败关闭及异常路径；只在确证preexec时payload_started=False |
| CMD-06 `concurrent_and_host_death` | 原双scope cap1/2独立；原host SIGKILL及late marker观察 | 并发/宿主故障子门，不扩展到他人unit |
| ENG-01 `real_session_prepare` | 真实Git分离session与原保护可prepare；deny根交叠真实拒绝、不删除保护 | 可表达子集/拒绝边界；不授ready |
| ENG-02 `actual_plan_pass` | 真正隔离unittest≥1、complete streams/resource/observer、scope清理、source前后相等 | 实际命令→plan；不认零测试/全skip/假summary为质量 |
| ENG-03 `actual_plan_deterministic_fail` | 真正断言失败/缺依赖；通过collection/完整清理才可闭operation failure；后续check not_run | 确定失败停止；不调用Reviewer或advance |
| ENG-04 `actual_plan_incomplete` | timeout/output截断/observer或resource不完整/cleanup未知，原证据output_incomplete | 未决operation保留，拒绝自动重放/成功 |
| ENG-05 `plan_tool_environment_root_drift` | 原解释器/Plan/环境/root身份漂移，各真实入口拒绝；非Linux无fallback | 不重新采集漂移为授权；模拟平台只属unit |
| ENG-06 `tree_source_and_review_drift` | 前置独立session-aware Git投影生产修复通过后，分离session才能取得真实captured/stable正控；测试写源码/改HEAD与Reviewer后变更仍拒绝；deepcheck开始后源码/范围变更单列拒绝负例 | 基线8d已知blocked，不能仅增测试达到；投影稳定不等结果commit已匹配 |
| CP-01 `actual_operation_receipt_record` | 同step attempt另operation，finish回读已闭；唯一receipt/真实first/replay验证记录 | managed action已闭、CP已消费；非step成功 |
| CP-02 `unconfirmed_control_and_replay` | 实际mismatched执行根/attempt/open action/重复未决拒绝；传输fault单列 | 未确认不报已记录，不重执行未决payload |
| REV-01 `fresh_context_read_submit` | 原fresh上下文完整读范围后submit，空/非法/越权/blocking/漏读拒绝 | model_double协议及应用只读；非语义/OS隔离 |
| PACK-01 `actual_partial_export_and_external_verify` | 唯一实际receipt导出、原verify_pack与独立verify.py；坏binding/摘要/重复/缺项原样拒绝 | 部分证据结构链；不授认证或六步成功 |
| STEP-01 `code_and_deepcheck_full_contract` | 前置Git投影修复通过后，两步分别按各自固定时间线走原required_checks/inspection/MCP/final_binding/finish/advance；deepcheck开始后变化拒绝且不重捕获 | 基线8d已知blocked；只授实际通过门，不以工程正控代替 |
| NATIVE-01 `ready_false_stays_blocked` | 真实Landlock/session Native阻断，provider/step/model未调 | 当前准入继续fail-closed |

## 清理、失败与 skip

正控不替换dispatch/helper/manager query/回执/CP，允许只观察式包装原函数，原调用次数/结果/异常不变；观察故障不得改变生产判定。fault injection与model_double在清单中显式标记。通过集合必须含实际正控，不能全由注入模拟组成。

继续使用原broker的deadline/output最小值、manager独立stderr预算、私有FD通道、owned scope/InvocationID与inode保护。`payload_started=None`是正常finished回执的未知exec状态，不能改true。resource terminal/通道/observer/cleanup缺失即失败/不完整。中断沿原BaseException语义传播，保留未决CP动作；不为取绿补finish或清除未决。

只有确定缺平台、compiler、非root同UIDbus等原必需环境时允许`skip; conformance_credit=none`；实际manager无响应、委托配置失败、quota无效、通道/清理失败是fail/blocked，不能降为skip。root已只读观察UID1000/Linux6.8.0-138-generic/x64/systemd249/cgroupv2、runtime0700同UID与bus同UID socket(mode666)，未调用manager或验证实际Delegate/pids配置，绝不预授resource PASS。

临时fixture在明确owned路径内回收；session.close释放lease不是删除完整worktree，工作区归属/清理沿现有manager合同。scope正常收束依原systemd --collect，不枚举/停止他人unit，不改user manager服务/权限。清理未确认时保留相应产物并报告，不能做广域删除。installed层复用CI临时环境生命周期；本轮不运行它。

## 后续文件范围和验收门

本验收片的最小文件范围是新增 `tests/test_linux_contract_engineering.py`，但仅此新增不能关闭L2a/L2b/ENG-06；前置session-aware Git tree投影生产修复已是确定依赖，由root另立设计、独立审查与实现，不在本文验收驱动中暗改。installed扩展才新增 `scripts/probe_installed_linux_contract_engineering.py`，由已有`run_native_wheel_ci.py`在相同已安装环境追加一次调用。其选择守卫应同步`tests/test_run_native_probe_ci.py`或相应wheel调度测试（先核实际现有选择位置，禁止猜不存在模块）。源码probe如选择新class则仅改已有`run_native_probe_ci.py`和对应选择测试。本作者本轮仍仅改两份文档，禁止修改生产/测试/计划/landscape。

软件门仍是fresh独立SPEC→不同QUALITY→单writer TDD→root关联/20轮/DEFAULT/原完整preflight/compile-j1/七维自检/文档复核→root按已授权main提交推送→同SHA线上观察。source与installed/helper身份各独立；主CI/签名绿色不能替Linux实际工程、Windows原生、macquota或真实模型门。既有8d完整2439total/2380P/59skip/0F/E与三guard属于root此前软件窗口，本作者无运行、不复用为本片PASS。

Windows Git10093/10038只允许已授三UTF8/current-interpreter validator修复，不自动扩大到SKILL Git pipe；Reviewer10035/tokenNone、PEcapture三false/完整解析/pre-main/UAC、macquota、Linux完整readiness及真实model endpoint/1→6/≥90%全部仍未通过。

## verification_matrix、negative_evidence、gaps、verdict

| Layer | Required | Consumer/scenario | Baseline/artifact | Action/evidence | Result |
|---|---|---|---|---|---|
| static | 是 | 准入与连接接口 | 8d/vendor1693及下表SHA | 本作者实际定点读源码/技能/研究 | pass（仅静态可审查设计） |
| host command | 是 | CMD-01..06/ENG-02..06 | 未生成本片helper/run | 后续现有实际组件矩阵 | blocked（未运行） |
| host CP/evidence | 是 | L2a/L2b/CP/PACK/STEP | 8d分离session Git投影不兼容；未生成本片CP attempt/pack | 先独立session-aware Git投影生产修复，再真实session/CP验收 | blocked（已知接线阻塞，未运行） |
| model_double | 是 | Reviewer/编排 | 未执行确定性backend | 后续显式double，无模型信用 | blocked（未运行） |
| deploy/install | installed切片必需 | 干净wheel/helper | 未构建/安装 | 现有wheel CI同环境追加 | blocked（未运行） |
| real model/Native overall | 本片不关闭 | 六步/≥90%/整体资源政策 | 原门保留 | endpoint未确认；readyFalse | blocked |

negative_evidence：当前完整合同正控替换dispatch/资源回执（证据`test_contract_engineering.py:35–90,884–1044`）反驳“已有真实Native工程往返”；readyFalse（`isolation.py:925–928`）反驳“Native可自动进入”；分离布局缺`workspace/.git`导致`workspace_not_repository_root`，与父层非空Git身份共同使gate1802–1805拒绝（`runner.py:3640–3674,3841起`），反驳“仅新增验收测试能通过L2a/L2b”。已有bus仅是前置存在观察，对manager实际委托/配额属inconclusive。安全下一步分别为L1实测、root独立Git投影生产修复设计与验收、保留NATIVE-01负控；deepcheck开始后源码/范围变更继续作为原门拒绝负例，不能重捕获取绿。

gaps：session-aware Git tree投影生产修复是已知前置依赖，由root另立设计并负责独立审查/验收，未过前阻断L2a/L2b/ENG-06 verified；实际host/installed矩阵、same-run CP与pack往返、完整code/deepcheck普通门由后续writer/root负责。deepcheck正控必须先固定最终源码/范围再step_start，开始后变更仅属拒绝负例。Native完整准入和真实模型由独立后续阶段负责，本文不新增授权或变合同。交付仅含实际已过层与原拒绝码，不声称修复/整体完成。

verdict：`blocked`（已知分离Git投影接线阻塞且实际验收未执行）；已交付范围为带明确前置依赖的静态设计，允许说“验收连接方案及前置阻塞已记录”。禁止说“仅补验收即可完整通过”“Linux工程验收已通过”“已认证工程质量”“自动ready”“R2/R3完成”。无工单状态回写。

## 作者实际读取与身份

以下为实际读取范围，未列全文的文件不声称全文件审查；SHA为完整文件内容身份。AGENTS全文、两个技能全文、landscape 475–550与当前头部及既有Python-preset设计全文已读。历史memory只用R2/R3证据分层提醒，所有决定性当前源码另核。`native/linux/icode_landlock.c`本作者仅核完整文件摘要`0700aa0a9fb8f18d60d1fe2f8320d8a1a03d4c0be9e189d10922fc2ada0a1ea3`，没有读native全文/运行，不能授native实现审计信用。

| 文件 | 实际阅读范围 | SHA256 |
|---|---|---|
| isolation.py | 860–1025、1135–1320 | `3ee49c12efce8002a32e5b86fd8acc1edf221042df8d7177fff18e9fcec0816d` |
| autonomy.py | 123–338、396–440 | `0b2613691e178a6452f3dc3c66481d9d104553d15922b3f069fd00d95fe8dbf8` |
| workspace.py | 418–494、1609–1700、2080–2150 | `4fe2dd726ef75f53175bd8e69408855174f5b84ce5fcebf76c7ed98bdf1c7753` |
| workbench.py | 350–385 | `690ba045dd30b4c06bbf619ecb29386c6c5e0edfaf45f345d7a3664e47ca9848` |
| runner.py | 1153–1449、1449–1615、1713–1960、3017–3270、3280–3345；本次补读1788–1810、3558–3598、3620–3675、3838–3857 | `2b145db41b3ebbd0f90f3e9d8b19e73b9ca6a08c97e1ba5fbe59d6d777ea671b` |
| tools/base.py | 255–305 | `b4f4c6269fe280417e817dfe366e933016bf7db24508e5003e52b2492e9a8764` |
| tools/builtin.py | 619–676 | `170d209b69e67dde05be320f83dadd4d326bb81e2a843a9f0c931a53eca00482` |
| execution_broker.py | 160–300 | `ee1b60b5c922a72de23234069d83e603287b66f3f6bed70323944d1663aab6f3` |
| linux_task_scope.py | 110–190、208–310 | `6ce8cc433395a2110ba636d7b6eae0af2a6614bcea62b23687e577432493f6f9` |
| engineering_verification.py | 1–42、59–78、100–275、340–555、672–840 | `0d98080f9ad5aec567b23073048eca8bd584924f26ee927f17a49e582c901027` |
| engineering_evidence.py | 1–95、73–103、148–220 | `0e568d46d8f2b026cf9ea18e8d02a8c909f099d4e9f28574fbc8a4b4ed28b95e` |
| control.py | 107–129、174–227、313–376 | `bab7da59d06d52c3fa5383c1676baa15b3c0ec109c92ba4a9812ebd7dffe8781` |
| evidence.py | 296–328、1006–1038、1374–1405 | `d50a01eb0016e8fd50e12a6fa59c5d4184d1bd5dabe35a6f81036b0023feffe4` |
| test_contract_engineering.py | 1–170、884–1044；符号定位其余gate/pack | `f4845043d0ad2d4b5f39c54cf3143b8c09479f31f49c06114c589e8efa2bb6a9` |
| test_linux_product_task_quota.py | 1–65、400–760、869–895、989–1028；其余方法名定位 | `b04d5996799c66bcc86709cc1e201fc0718d214a1af01ce34d758e70b1db9418` |
| test_linux_violation_receipt.py | 1–185；其余方法名定位 | `02821aa85001dba014d7966114173b405c9bf5b187e0632e665f020b2ae5bda3` |
| probe_installed_linux_violation_receipt.py | 全部1–164 | `9c3406f9a4dc67789c6f7248db240007279d41f5ea1236a73b7cf4437edbca2c` |
| run_native_probe_ci.py | 41–135、173–210 | `2bd6c3ab81738d803944d66988172bd2758428ecf33bf416f8648b56db4baa76` |
| run_native_wheel_ci.py | 1–140、129–175（重叠） | `51607146937657740e898171e9b361f8b4239d066cb372fdf11c30f8ba256e37` |
| vendor/tools/icode_control.py | 1150–1265、5100–5175 | `0b7e2577844f135269bdcc78bee195ad974a350f20792af7de46b2bdae76564c` |

`pack_verify.py`/linux_task_resource.py/linux_seccomp_notify.py/reviewer.py仅符号定位及零散reviewer273–307，本作者未完整审查；完整身份分别为`30dcdc6dcaf1fc49f0b8081997b1424c2d060c1f76b378357035446bc956fde3`、`2c7158a6b3d5ef67d42578ebe675a12aeb97a1896e3790c9bbdca22d42cf6217`、`740eaca978f67946a2cd6e7fa05e78b6694e06bf425fa8340919022132ade8dd`、`5066760c6dec8ef9f63c805329b990febfd675778e6c8d3bdb9d25498b49942b`。独立上游研究与作者补核范围另列，不替root阅读信用。

## 静态自审与七维报告

修订历史：原作者自审C0/I0/M0未发现下述问题，fresh独立SPEC给出C0/I2/M0，不能把原自审当独立通过。原设计SHA`b135799f6ec0ebfdff9c78cda9fb0ef9b96f347a96bc5bcf689e07860bf95147`、研究SHA`6c9c74c90e8c19fe4ad291a077abb448c45e214060825768c845cc85245110c1`保留历史。I1是分离Git布局的tree投影生产阻塞；I2是原稿对code/deepcheck共用“step_start后改源码”导致deepcheck保护输入必漂移。本次只修文档：新增确定前置修复依赖、收紧所有L2/ENG-06成功表述；拆开两条时间线，保留开始后mutation拒绝负例与禁止重捕获。未运行复现或实施生产修复。

修订后作者先selfSPEC：无占位，I1/I2关联段与研究同步，L2需前置独立生产门；再selfQUALITY：Git身份/投影门、deepcheck冻结时点、CP UUID/资源通道、异常/清理/skip与许可/平台合同复核。修订后自审C0/I0/M0；该结果不是重新独立SPEC结论，下一门为fresh独立SPEC。本作者STOP等待该审查，不编写计划/实现。实际运行数0、测试数0、编译/安装数0。

【架构级自检报告】

- ✅ 语法/编译：Markdown静态检查通过；生产编译未运行，本文无代码实现。
- ✅ 依赖/调用链：现有入口、session、plan、CP/operation/receipt/pack接口已定点核对。
- ✅ 逻辑/边界：已知Git投影阻塞、code/deepcheck不同冻结时点、三层信用、Native拒绝与普通门分别记录。
- ✅ 异常处理：失败/不完整/中断/skip要求具名；没有授未知清理或重放成功。
- ✅ 关联模块：本次只修两份文档；前置Git投影生产修复由root另立设计/验收，源码、vendor和平台准入未修改。
- ✅ 兼容安全：无新依赖、权限、fallback、KEY/模型HTTP、服务变更。
- ✅ 可运行性：当前API与既有命令接口静态可定位；实际工程/完整步骤尚未运行，不能宣称100%运行验收。
