# R3 Python 安全默认工程模板（合同接线后的独立片）

> REQUIRED SUB-SKILL: nbl.test-driven-development、nbl.subagent-driven-development。本文件仅设计候选，未实现、未验收。先完成合同接线冻结、独立SPEC→不同QUALITY、完整守护及main提交推送；不与合同唯一源码写者同时修改执行器。

2026-10-08补充：原十项候选曾按 `27e29318df73271c1e2b242b2266040ba0bf467b8ed848e5019fc972caa782bf` 获静态SPEC批准。随后独立研究发现 `-I` 同时忽略broker现有 `PYTHONUTF8`，根代理按三步结构化评估选择下述十二项作为可逆推荐候选，并向用户发出默认编码偏好询问（尚未收到回答，不称用户已确认）。这是明确设计变更，不继承旧十项批准，须重新独立SPEC→不同QUALITY；合同冻结源码、adapter与验证规则未改。

## 真实问题、现有实现与调用链

2026-10-08只读研究绑定aaaa448，核对工程executor/broker及正式CPython3.11.15：现unittest adapter只接受`-B -m unittest`，该启动路径可被工程内unittest.py遮蔽；Settings/CLI/workbench尚无默认可信计划工厂。固定解释器本身的身份观察不认证模块、stdlib、site-packages或测试质量。三问均有源码/实际RAM依据，本片复用VerificationCheck/Plan、实际dispatch/输出adapter、snapshot窗口和宿主provider，不新造执行通道。

最小语法片先于默认工厂及CLI入口片：先明确定义安全启动并验证正常工程imports，再注入宿主生成计划，最后做干净pip→CLI→workbench→Native→真实合同与独立验包。仅支持已明确的Python unittest，不自动选其他技术栈、安装依赖或下载编译器；Windows/macOS仍受既有原生硬门约束。

## 精确参数合同与兼容边界

- 旧`-B -m unittest`分支及既有额外参数行为不变，只保留既有观察/诊断上限。
- 新候选必须恰好12项：`(lexical_sys_executable, "-I", "-B", "-X", "utf8", "-m", "unittest", "discover", "-s", root, "-t", root)`；cwd固定`"."`。只接纳一个新形式，不同时默许原十项候选；不接受额外flags、调序、`utf8=0/1`、通用`-c`或其他模块。
- Check核对固定tokens/长度、两个绝对root相同；Plan再核对两个root精确等于其规范workspace_root；执行前重核。合法Check不能通过另一工程的Plan获得本工程信用。
- 解释器使用当前`sys.executable`的词法路径，不将argv0 resolve为基础解释器。复用既有_executable_identity对requested/resolved及别名观察；venv prefix语义必须实际验证。
- 不改变现有resource dispatch、策略准入、输出/清理/源窗口、零测试及整体unknown门；unsupported没有裸subprocess fallback。

新模板的`-I`忽略启动cwd、PYTHONPATH及user-site；stdlib unittest先加载，discover才加入top-level root并加载测试。root普通imports可用；只依赖src路径或尚未安装的依赖会失败，不通过回填全局PYTHONPATH、修改工程布局或自动安装掩盖。高级仓外宿主模板的配置入口另片，不将仓内TOML、工单JSON或浏览器字段升为执行授权。

固定 `-X utf8` 是明确的启动配置，不依赖被 `-I` 忽略的环境变量。它还改变默认文本文件/文件名编码，依赖legacy默认编码的工程可能失败；旧分支保留，不能改strict decode为replace掩盖。这改善双语默认体验，不保证测试不能主动改流、写非法bytes或伪造摘要。

## 一手依据、实际观察与支持上限

独立研究已读[CPython v3.11.15命令行](https://github.com/python/cpython/blob/v3.11.15/Doc/using/cmdline.rst#L275)、[unittest loader](https://github.com/python/cpython/blob/v3.11.15/Lib/unittest/loader.py#L290)及[PSF许可](https://github.com/python/cpython/blob/v3.11.15/LICENSE#L54)，并与本机同版源码核对。仅调用已有解释器和stdlib，无实现复制、运行依赖或权限增加。

同日编码补充的一手核对：[显式-X utf8](https://github.com/python/cpython/blob/v3.11.15/Doc/using/cmdline.rst#L480)、[preconfig先消费命令行再查环境](https://github.com/python/cpython/blob/v3.11.15/Python/preconfig.c#L551)。根代理实际3.11.15词法venv启动RAM：`PYTHONUTF8=1/PYTHONIOENCODING=latin1`下 `-I -B` 的utf8_mode仍0；相反环境加显式 `-I -B -X utf8` 后utf8_mode1、stdout/stderr UTF-8且中文输出正常，两者venv prefix均保留。两次仅验证本机CLI flags，不是新Check准入或Windows实测。复用[Aider固定命令配置](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/args.py#L548)与[实际cmd_test消费](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/commands.py#L993)，仅采纳明确命令/实际执行分离，不借shell宽语法；Apache-2.0许可沿持续对照，无代码复制。

研究者此前实际RAM：词法venv的prefix与base_prefix不同，resolved基础解释器则相同；root/src同时有unittest.py/sitecustomize.py时**原十项-I discover候选**实际1test/OK，启动marker未出现且无pyc；root正常imports可用，src-only实际ModuleNotFoundError。根代理另一次实际broker环境观察已证明旧shadow失败、原十项-I discover的1测试通过，但当前Check拒绝-I。新增十二项的组合shadow/import/完整执行仍待TDD；上段显式-X的两次flags RAM不能代替它。实验不是原生资源成功或模型质量证明。

`-I`不是`-S`，仍运行宿主site/.pth/sitecustomize；宿主解释器、stdlib及已配置依赖属于可信环境假设。项目测试加载后也可修改模块/输出。研究者实际测试打印7项OK后os._exit(0)，现parser计7：框架摘要是可伪造观察，不认证完整执行。**采纳**精确模板/路径身份/stdlib先载入；**暂缓**src-only和额外依赖推荐；**不适配**泛化flags、-c bootstrap、把-I或摘要称质量认证。独立Reviewer、控制面及原生运行门必须分别验，不能以模板改善替代。

## 独立TDD与验收

1. 先真实RED新十二项形式被拒，再最小两分支实现；未选十项及变体拒绝，旧-B参数/golden/receipt保持。
2. 新形式缺、多、调序flags、-c、错module/discover/root、非绝对或不同root、非点号cwd均拒；合法Check/错Plan root在执行前拒。
3. root/src启动shadow负控、root普通imports正控；词法venv正控及resolve丢语义对照，无pyc。
4. 实际失败、缺依赖、src-only、零测试、全skip、输出不完整与源/工具别名漂移不通过；无安装或全局路径变更。
5. 无实际资源通道、unknown清理及policy身份错误继续阻断，普通组只观察不授整树信用；如实保留框架输出非认证上限。
6. 独立SPEC→不同QUALITY后冻结；新矩阵20轮、执行器/broker/旧task/证据与独立验包关联、DEFAULT、干净pip、完整preflight、compileall-j1、治理/官网/竞品/diff/密钥/子模块门通过后按授权main提交推送。

7. 合成 `PYTHONUTF8=0/PYTHONIOENCODING=latin1`不能覆盖显式模式；实际管道中文正常，非法bytes/截断/缺摘要继续拒绝。Linux/macOS/Windows各自观察，不用本机UTF-8 locale代替Windows证据；新argv/cwd摘要及receipt/离仓验包绑定，旧golden不重录。

当前以上新实现证据均unobserved；readonly/RAM只支持设计与启动来源问题，不支持正式模板、CLI用户闭环、真实模型1→6、90%SKILL矩阵或R2/R3整体通过。宿主工厂具体接口应在合同provider验收后冻结，不预报不存在API。

**Execution Mode:** serial implementation, independent read-only research/reviews

静态新窗口收尾：修正旧十项RAM被简称为“新形式”的低严重性标签后，`6246b3e8d3588cb64b52700ee9a2394ed043417c62dafc138ec8e7aefab910ea` 获独立SPEC复核批准，再由不同审查者静态QUALITY批准（0/0/0）。旧 `ddc5eb18... / Minor1` 保留历史，不继承未测信用。本段为审查记录，仍未实现或运行十二项完整模板，合同阶段完整守护/提交须先完成。
