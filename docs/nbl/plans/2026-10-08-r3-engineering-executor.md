# R3 宿主工程检查执行器第一片

> REQUIRED SUB-SKILL: nbl.test-driven-development、nbl.subagent-driven-development。主分支基线71a3d2c；按已授权main推进，实施串行，调研/SPEC/不同QUALITY独立只读。本片是[工程验证总设计](2026-10-08-r3-engineering-verification-plan.md)的实际执行入口，不把接口或诊断运行当成合同接线完成。

## 三问与现有链

真实问题是宿主只能固定运行Python unittest，不能表达已批准的多项工程检查或可靠区分非Python命令成功与真实非零测试。已有ExecutionResult/raw_output、ToolContext绑定、resource/USER_NOTIF broker、有界POSIX/Windows输出执行器及完整工作树快照，均优先复用。调用链为宿主冻结计划→逐项实际检查→完整结果/源窗口→后续runner/证据/合同消费；旧run_unittest及默认task、旧receipt保持原样，不造第二套状态机或模型工具。

## 本片边界与步骤

1. 宿主预先构造深不可变VerificationCheck/VerificationPlan，固定工作区/运行/工单/适用step/platform、argv/cwd/adapter及有限逐项/总输出和时限。只接受严格类型、唯一有界id、至少一个required test、闭合adapter及现有绝对执行工具。确定性摘要不从模型回复或可写工单副本重载。冻结工具字节身份供执行前后核对，不称整套工具链认证。
2. execute_verification_plan是宿主入口，不注册到模型工具。逐项实际运行，先失败即后项not_run，每个required test须真实非零成功；build/lint exit0只证明该命令成功。readonly Reviewer上下文不得经可写路径运行检查。缺工具/adapter/权限、输出截断/未知清理/未确认resource通道、源窗口或计划身份漂移失败关闭。KI/SystemExit原对象透传。
3. 策略任务要求实际RL-0及违规观察链，复用当前Linux Landlock DENY/resource dispatch，不能用run_unittest(sandbox.wrap)/普通subprocess代替。当前不合格Windows/macOS路径启动前拒绝，readiness不变；非policy入口仅用于已显式选择的旧边界/诊断，结果如实标明，不计正式策略验收。
4. 先接unittest_summary_v1：完整UTF-8输出、实际正计数summary和终态OK、扣除skip后非零；空/全跳过/失败不能passed。接go_test_json_v1：实际Test run→pass、所有已开始测试闭合及所属包成功；强制-count=1/-p1/-parallel1/-mod=readonly，GOTOOLCHAIN=local，不下载依赖/工具链。Go1.27 build和新动作按固定源码复核，未知或不完整协议拒绝。不把项目stdout当独立质量认证。
5. Go缓存/临时输出仅用宿主新建的工作区内精确私有目录；未批准运行时不扩大白名单。目录身份确认且命令收束确认后仅清理由宿主创建的对象；替换/清理不确定保留并拒绝，既有用户输出不删除。不按gitignore或笼统build排除源文件。实际检查前后完整源快照必须相等，后续Git/tree及受测产物窗口消费另接线。

## TDD与阶段门

新增真实Python正/零/全skip/失败fixture，多检查前失败后成功不执行后项、源变化/工具变化、完整输出/超量/超时/清理、坏计划和只读上下文拒绝；Go用已核验开发临时工具链实际std-library fixture，缺Go跳过单列，不能凭打印结果当Go实际测试。策略调用选择与完整resource回执采用明确transport负控，原生资源链需独立实际运行，模拟不计OS通过。

20轮关键矩阵、旧runner/输出生命周期/broker/tools/快照关联、独立SPEC→不同QUALITY、完整preflight/compileall≤j6/治理/官网/竞品/diff后main提交推送。随后下一片同步VerificationEvidence/fingerprint/ledger/导入/独立verifier和run_task可选宿主计划，再接真实code/deepcheck/chain与独立Reviewer。旧回执不增加可选字段；本片尚不产新版verifications.json，不能宣称往返已实现。

## 持续研究（2026-10-08）

采纳Aider固定5dc9490的配置检查与实际错误反馈，拒其shell/无检查None→成功/无输出预算。实际raw行号为[base1616](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/coders/base_coder.py#L1616)、[cmd_test993](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/commands.py#L993)、[Popen62](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/run_cmd.py#L62)；网页提取省掉空行后的行号不是源码锚点。采纳Codex固定1fbe15c的退出/超时/输出分层，不能由其终态证明非零测试或受测tree。两者Apache-2.0，仅机制参考，无代码复制/新依赖。

Go官方[test2json](https://pkg.go.dev/cmd/test2json)/[go命令](https://pkg.go.dev/cmd/go)/[工具链选择](https://go.dev/doc/toolchain)用于adapter合同；研究观察Go1.27.1另有build-output/build-fail及attr/artifacts，须固定源码与真实fixture核对，不盲用仅文档动作集。CTest3.22的JUnit/--no-tests=error暂缓下一片，不能把show-only计实际测试。Go/CMake为BSD-3-Clause，仅调用现有工具，不随包分发。

**Execution Mode:** serial implementation, independent read-only research/reviews

## 实际边界修正与阶段记录

2026-10-08独立早期审查的五项实际负控均纳入回归：venv词法启动路径不能被resolve替换；真实postspawn marker后的程序异常不投影payload_started=false；闭合stdio的有限setsid后代仍存活时，普通process_group不授权缓存owner清理；Ninja默认并发及Make长/组合jobs和CMake后端覆盖拒绝；原缓存保持FD，真实删除重建不能通过可复用inode冒充宿主对象。选择已知前端参数界限，不声称可控制任意script内部线程或递归构建树。

首次正式SPEC在722499/test39dc冻结上43项（42PASS/1Go skip）和六关联157项（152PASS/5旧平台skip）后拒绝交付，实际指出两Important：rmtree(name,parent_fd)没有消费原cache FD，删除入口替换时删了foreign.txt；Go build+Python required test以cache=None执行。根代理补两方法，旧版2FAIL/0ERROR，修正递归遍历消费原FD与所有词法go命令触发owned/offlinecache。末尾空目录unlink以payload写入者全部收束/其余宿主可信为前提，不声称抵御同UID恶意宿主。重复Go pass来自固定官方framebig，幂等不补信用，只有第二次run才补报告次数。

POSIX无policy只确认同进程组，任何owned-cache写入者未知即停止后项并保留；实际Go三个std-library模式成功/零/编译失败只验证框架观察，aggregate均cache_cleanup_unconfirmed，不计OS或正式工程通过。Go1.27.1临时开发工具链未安装到PATH/系统、未随包分发、未扩大native读根，编译-p1/-parallel1/GOMAX1；离线且私有telemetry配置，不更改用户配置。Windows held-cache HANDLE生命周期未实现，Go build/test等均拒启；SystemRoot/WINDIR仅静态合同和显式env配对，原生另验。Python诊断真实nonzero计数可以通过，但os_enforced=false，不转成正式隔离。

新增源快照不可用在before/after失败关闭，无未知after指纹；策略预检不可用不退普通subprocess；资源回执闭合七字段严格验证后才摘要，不序列化任意未知对象/字段。缓存关闭尝试全部持有FD后报告首异常，原KI/SystemExit对象透传，异常时不猜清理成功。新增宿主入口不注册模型工具，旧单命令/receipt默认完全保留；新版多检查证据、ledger与合同/Reviewer接线仍下一片，不能宣称已往返或R3闭合。

最终本机三类34+CI10实际44PASS/0skip/5.636秒，真实Go一方法覆盖三模式PASS/0skip/16.489秒（上述诊断边界）；十关联256项OK/5旧skip（251实际PASS）/23.919秒，DEFAULT287PASS/0skip/108.200秒。最初误选不存在test_task_io的221项ImportError、未设src导入路径的workspace91项8ImportError及task IO32项ImportError均不计产品RED/通过，正确PYTHONPATH与实际模块名后重跑。最终20轮、SPEC复审→不同QUALITY及提交前新完整preflight进行中；源码变更重叠的旧preflight3/3仅历史成功，不计最终冻结守护。

### 后续冻结复验（2026-10-08）

上述44/287是历史迭代计数。后续独立审查又复现真实局部FD注册/关闭和异常优先级缺陷：构造路径的read中断被finally close普通故障覆盖，终结路径的remove中断被随后同优先close中断覆盖。两个公共入口方法、12子场景在旧版得到6FAIL/0ERROR；复用既有`_select_cleanup_error`与通用`_local_descriptor`后通过。同优先保留先发生异常的原对象，KI/SystemExit优先于普通故障，尝试关闭全部自有FD；不吞异常或猜测清理成功。GNU Make4.4.1的-L组合flag补入已知参数扫描；本机4.3不支持-L，仅静态固定源码及构造负控，不称本机4.4.1动态验收。

当前冻结engineering SHA256为`5d3bf82b97ec31802ed9a7249a9f22e754022b9182bd4b91ad055ef119a83412`，tests为`3027fe84d864b5138dc6dac391a7badcc5a065e5f893f8f25216e32672813b00`；broker/runner/builtin/CI选择五文件同步冻结。独立SPEC批准限定第一片，48PASS/0skip/6.346秒，另RAM十负控拒绝/三正控通过。根代理冻结后20轮×48=960PASS/0skip/125.311秒；十关联256项OK/5旧skip（251实际PASS）/24.082秒；DEFAULT291PASS/0skip/110.834秒；真实Go一方法三实际模式PASS/0skip/17.558秒，仍不计未知缓存写入者清理通过。编译-j1、治理/双语官网/竞品排期/diff已通过。不同QUALITY与新完整preflight结果尚待回收；失联的上一守护句柄没有捕获终态，不能当最终通过。仍未提交本片，不计新SHA原生或R2/R3完成。

### 本片提交前终态

不同QUALITY独立批准：48PASS/0skip/6.146秒、十项旧runner/broker关键关联PASS/0skip/0.343秒，三项Go转义代理码点RAM负控均拒绝，无Critical/Important/Minor；七源码/测试摘要前后一致。根代理新完整preflight句柄54700实际退出0、三道全部通过（密钥扫描、子模块完整性、全量unittest）。该守护不打印全量测试数/skip数，不能据此宣称全量零skip。七源码摘要与冻结值仍一致，vendor固定169干净；提交前对最后文档再跑密钥/治理/官网/竞品/diff。按已授权main提交推送，不创建分支或发布Release；精确提交的远端原生结果后续另记。

【架构级自检报告】（仅本片已测边界）

- ✅ 语法/编译：compileall-j1、实际导入及diff通过。
- ✅ 依赖/调用链：宿主计划→共享broker/原有有界reader→完整结果闭合，未注册模型工具。
- ✅ 逻辑/边界：首败早停、零/全skip、源码/计划/工具漂移和完整输出通过。
- ✅ 异常处理：真实FD/缓存生命周期与12复合异常场景通过，中断优先级及原对象保留。
- ✅ 关联模块：十关联256项无失败/5既有skip，DEFAULT291与双独立审查通过。
- ✅ 兼容安全：旧默认API/receipt不变，精确缓存替换保护和unsupported拒启，不扩大readiness。
- ✅ 可运行性：本机宿主片、Go诊断三模式和全仓守护通过；原生策略正控、Windows/macOS、新证据往返及实际产品/模型总门仍未完成，不报告100%整体验收。
