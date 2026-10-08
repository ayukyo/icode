# R3 契约预算硬停止 Implementation Plan

> REQUIRED SUB-SKILL: nbl.test-driven-development、nbl.subagent-driven-development。必须等独立验证测量片冻结、门禁及提交后才修改runner，避免交叉污染。

**Goal:** 已观测 budget_exceeded 不得因已有产物或恢复路径而变成契约成功，不再触发装配、补救、推演或状态前移。

**Architecture:** 复用 LoopResult.stop_reason 和现有控制面 failure finish；仅初次/repair/resume三个消费点及共用私有硬停止收尾。正常回合上限仍保留既有产物驱动软处理，不扩大其它stop语义。

## 实际基线（三问）

2026-10-08主代理实际临时工作区、真实ControlPlane及AgentLoop复现：expected_tokens=100，第一次100tokens真实工具写01_plan.md，第二次201tokens纯文本使loop ok=false/budget_exceeded/301tokens；run_contract_step仍post_write一次、finish=success、backend总5次（含之后3次推演）、状态已前移、error为空。该离线夹具证明运行时路径，不代表真实模型能力或生产工程验收。

这是预算硬失败被统一软化的真实问题。已有loop charge后硬门和CP failure终结机制应复用，不造新预算阈值。调用链为run_contract_step初次、产物repair、resume_contract_step，chain消费StepReport并停步；预算全链所有权和推演计费仍是下一片，不能据本片虚称闭合。

## Task 1: 拒绝成功与后续工作

- [x] 完成（源码及本机分片验收；精确交付另记录）

编辑限定 src/icode/runner.py 与新 tests/test_contract_budget_stop.py，必要关联测试补兼容断言。不改平台、vendor、CI权限、预算阈值或模型KEY。

- [x] Step 1: RED

真实CP+明确last_usage的离线backend，已有真实产物301超限仍success的原行为作为RED；另覆盖缺件超限不得repair/autopersist，repair首回复超限不得后装配，resume超限不得清检查点或前移。后续模型调用计数、post_write、artifact登记和实际CP事件必须核对，不只断言report.ok（其可能已被其它门禁阻断）。

- [x] Step 2: 最小硬停止

每个模型loop返回后立即识别精确budget_exceeded，report.loop保留真实结果及已计费用量；固定错误说明预算硬停止。只尝试当前attempt的failure finish，失败不伪造成功、不改旧产物/操作回执、不清checkpoint。收尾只读cp.trace、如实检查开放步骤/操作，不能调用会推演或transition的_finalize。

初次不调用post_write/登记/repair/autopersist；repair之前已发生的登记保留，但超限之后不能再调用这些动作；resume同样硬停止。共享最小私有函数不得把普通失败或max_turns一律改为硬拒绝。失败回执被拒绝或cp.trace异常仍report.ok=false，当次保留checkpoint，不吞KeyboardInterrupt/SystemExit。固定预算提示不能被普通收尾异常覆盖；只有CP明确ok=true且outcome=failure才记已确认失败终结，trace闭合不等于步骤通过。

独立计划审查的真实CP实证：failure finish接受后attempt已终结，检查点只在本次保留；以后显式resume按现有Recoverer删除失效检查点、无openattempt而拒绝，0模型，不自动新建attempt或重放。finish拒绝时旧attempt仍开放，显式恢复可能创建新tracker；本片不保证跨进程旧预算拒绝持续。追加上述两条回归，不改Recoverer或把检查点存在当可继续成功证据。

- [x] Step 3: 兼容与冻结

expected=0观察、严格300允许/301拒绝、max_turns产物齐备的旧软行为、普通非预算stop及已有产物真实性测试保持。原failure finish拒绝/异常、真实chain停止不启动下一步骤。新矩阵冻结20轮；关联loop、reasoning_budget、runner、recovery、chain、evidence；独立SPEC→QUALITY及7维自检。

- [x] Step 4: 交付后自动继续

完整preflight三门、compileall≤j6及治理/官网/竞品/diff后提交推送main，核对远端并独立观察新CI。独立审查另确认真实CLI恢复传sandbox但resume不收的TypeError，先按[窄修复计划](./2026-10-08-r3-cli-resume-sandbox.md)修通既有入口；随后按[共享预算计划](./2026-10-08-r3-shared-runtime-budget.md)给初次/repair/final推演同一个BudgetTracker，推演计费检查在成功finish之前，chain及原生自主execute多步骤同一owner；不能把同一Budget配置当共享账本。跨进程恢复尚无累计usage持久化，要单独定边界，不在本片虚称恢复预算连续。

## 研究与不适配

复用2026-10-08持续对照的PydanticAI固定`f55bb8a6fd6cdb34405e5f523d67cf8f366df4aa` MIT：usage入账后、工具与结果终态之前检查；ICODE本片把该硬门传播到实际契约消费点。OpenHands SDK固定`69e26889401fe69157fff536e6a69049e6644cb3` MIT：多LLM用量聚合暂缓至共享预算片；FINISHED预算豁免和>=阈值不适配ICODE。无源码复制、SDK或新增许可依赖，实际控制面负控是验收依据而非上游文档。

**Execution Mode:** serial implementation, independent research/reviews

## 冻结证据（2026-10-08；待完整守护及精确提交）

生产仅48新增行：三个消费点精确停止与共享failure/只读观察收尾；runner SHA256 `5f479762c94505a9d152e245931610bfab63d31b42a14982e78e7b826178d381`，新测试 `053ef328ecbac8165c9dcb0e6898721afd1bac8991ef8ddf22fe3c923bcf4dd7`。最终真实旧RAM对照17方法，3兼容正控GREEN、14预算负控方法RED（含trace中断两个subtest的15失败条目）、0ERROR/0SKIP；初始夹具目录错位的轮次无效，不计RED。真实review补救负控旧版会完成成功并补落MD，新版保留先前manifest/round原字节及2产物回执，不再补落。

最终17方法连续20轮=340/340、0SKIP、309.163秒，轮前后两个摘要均一致。实施关联九模块391方法、386通过/5既有平台SKIP、194.617秒，0失败/错误；不把平台SKIP当跨平台能力通过。

独立SPEC17/17、15.671秒、0SKIP；其关联选择197方法（含新17）、192通过/5既有SKIP、61.460秒；另6组failure确认真值负控通过，只有returncode0/ok is True/outcome failure才确认，closed trace不能使report.ok成功。三个消费点、原事实保留、后续Recoverer边界、固定提示与原中断身份均核对，无遗留P2。独立QUALITY及全preflight仍在执行，不能提前写通过。

独立QUALITY随后通过：新增17/17、15.848秒、0SKIP；其六模块281/281、169.850秒及runner/测量93方法88通过/5既有SKIP、8.312秒，关联合374方法369通过/5SKIP（不与SPEC/实施者选择混合）。额外真实CP当次事实保留、持久failure状态独立进程重读、same-request幂等终结、8项finish/trace异常含KI/SystemExit原对象透传及3项闭合trace不冒成功负控均通过，无Critical/Important/Minor finding。原failure被拒绝后未来显式恢复新tracker边界仍保留。全preflight尚待实际结束。

主代理隔离构建、native wheel检查、干净pip --no-deps安装通过；临时cwd/-I/no checkout import下已安装runner摘要精确一致，真实CP四控制全部通过：已有产物301拒绝保旧写回执、缺产物301不repair/autopersist、300旧成功、observe_only旧成功。显式只读消费仓内SKILL真源，不声称已经证明无SKILL来源的新机安装体验；此离线矩阵不验证真实模型质量或R2/R3整体。

主代理完整preflight于2026-10-08 07:28:40 UTC退出0，密钥/子模块/全测试三门通过；完整load为2000方法，preflight不打印通过SKIP数，不编造零SKIP或全部原生执行。compileall -j6、治理/官网/竞品/diff通过，冻结两摘要不变，最终文档后重新执行只读守护。已具备本机分片交付条件，精确main提交推送与新SHA线上终态待实际记录。

### 精确提交及下一片

已提交推送main `bd49060b8c79cfe9911bf5a6643f368981cd4398`，主代理git push成功并新鲜ls-remote一致；8文件受测树同时含下一CLI修复与共享预算设计、上一SHA线上证据收口。新SHA线上仍待终态，不冒称整体绿。CLI恢复sandbox窄修复已按授权自动开工，不需新用户命令；预算共享及真实工程验证随后继续。没有跨进程账本或真实模型质量的新通过证据。

独立新SHA观察全部终态：主[37743783091](https://github.com/ayukyo/icode/actions/runs/37743783091)完整37为32success/2既有Windowscandidatefailure/3skip，Python3.11 `113200376135`实际2000方法/459.628秒、3.12 `113200376110`实际2000/458.875秒，均OK/71既有平台SKIP；quiet日志不逐名列新17方法，不伪称每个新case有独立线上日志。四Linux安装、七输出生命周期、四workspace各子门通过，24.04lease仍SKIP。provenance[37743783014](https://github.com/ayukyo/icode/actions/runs/37743783014)于07:45:04 UTC success，validate及四真实验签/安装/密码学负控通过，但bootstrap仍拒绝setup/commands。官网[37743783016](https://github.com/ayukyo/icode/actions/runs/37743783016)success，artifact `11534324470`精确该SHA部署。三run均停止重复查询；不称Windows正式执行或R2/R3整体通过。
