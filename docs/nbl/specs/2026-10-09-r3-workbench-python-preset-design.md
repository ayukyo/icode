# R3 工作台宿主 Python 测试预设设计

日期：2026-10-09。设计基线为已推送 main `6ded1d3c16c265fda16fa6506cb57c29067b5fbd`，vendor `1693651c1bd7daad3272eb054f0f81d6f254d08d`。本文为新切片设计，不是实现或工程运行验收；前一传输片的线上流程仍独立观察。用户自主决定阶段、持续执行及 main-only 授权覆盖常规等待/分支惯例，不覆盖资源、模型端点、权限或测试门。

## 真实缺口与复用

root 全文回读 CLI、NativeChainExecutor/AutonomyManager、engineering_verification，并核 runner 准入及 builtin→broker 限额路径。`cmd_workbench()` 构造原生执行器但未传现有 `verification_plan_provider`；正式 code/deepcheck 因此返回 `verification_plan_required`。已有 `(ExecutionContext, SandboxPolicy) -> VerificationPlan` 接口、孤立 unittest 模板、解释器/目录/环境身份验证、资源通道、独立 Reviewer、受测 tree 与 CP/evidence 门可复用，不另造模型或测试执行框架。

内置工厂不能每步生成新计划：Check/Plan 构造会重新观察身份，直接重复构造可能把步骤间漂移当新授权。原任意 provider 的每步调用是既有合同，本片只为新内置预设固定同次执行计划。独立只读设计复核发现这一风险，root 需求→方案→风险记录130–132；新实现前还需独立设计/计划双审及 TDD。

## 候选与阶段选择

A（选择）：可信服务启动者显式选择一个内置 `python-unittest` 预设，不提供任意命令。普通用户只需一次选择测试类型，工程步骤仍按真实检查结果阻断。

B（暂缓）：自动读取项目配置或猜语言/测试命令。便利但会扩大项目文件的授权作用，解释器、依赖、命令和信任优先级需另设计。

C（暂缓）：任意测试命令及通用 provider 注册。适用面更广，但新增 argv/env 配置、安全、预算及兼容合同，超过当前接线缺口。

root 依既有自主阶段授权选择 A。默认不选择预设时仍沿现有阻断；本片不自动安装依赖、不改用户环境、不从浏览器/模型/自然语言取得命令权限。

## 接口与生命周期

CLI 仅在 workbench 增加 `--verification-preset`，唯一可选值 `python-unittest`，默认 `None`。不搭配 `--enable-autonomous` 时，在 load_settings、模型构造或 Server 构造之前抛固定 ConfigError `--verification-preset 需要 --enable-autonomous`，现有 main 返回2。未知值由 argparse 拒绝；旧手工 Namespace 用 getattr 兼容。

新增小模块 `src/icode/verification_presets.py`，提供冻结的 `PythonUnittestPlanProvider(executable: Path)`。CLI 显式传 `Path(sys.executable)`；要求非空绝对 lexical 路径，不调用 absolute/resolve 改写 launcher，不搜索 PATH 或选择其它 Python，保留 venv 语义。构造时捕获既有 `_executable_identity`；普通不可用故障转固定 ConfigError，不回显路径或异常正文，fatal 不转换为普通配置提示。

provider `__call__(context, policy)` 复用既有接口：校验 context/policy 的 canonical workspace、ticket 及 code/deepcheck 步骤，run_id 只取实际 policy。调用前核启动解释器身份；构造 Check 后再核其捕获身份等于启动值。生成一个 required test：check_id `python-unittest`、adapter `unittest_summary_v1`、cwd `.`，argv 精确为 `(exe, -I, -B, -X, utf8, -m, unittest, discover, -s, root, -t, root)`；root 来自 session/policy，不来自浏览器。沿用 Check 180秒/1MiB 默认限额，Plan.steps 固定 code/deepcheck，其他既有校验保留。

NativeChainExecutor.execute 增加 invocation-local 计划变量，仅对 `type(provider) is PythonUnittestPlanProvider` 保存第一次工程步骤通过既有 type/identity 检查的 Plan，后续工程步骤复用同一对象。普通 provider 仍每步调用，自定义 executor/step_adapter 的签名与行为不变；不采用鸭子类型缓存协议、共享 run 字典或实例级缓存。新的 execute/run 创建新计划，不把旧计划带入另一工单或 resume 调用。

冻结时点必须如实：解释器身份在可信 CLI 启动时；工程 root inode、环境与 run/ticket 在本次执行第一工程步骤。后续 runner 继续核 frozen plan，不能因新步骤重新采集扩大授权。它不承诺从 intent/session 创建起冻结所有目录对象，不替代既有持有对象/权限保护。

## 限额、错误与原生边界

现有 broker 实际使用 `min(policy.output_limit_bytes, requested_output_limit)` 和 `min(check timeout, policy.wall_timeout_seconds)`（execution_broker.py:479、481）；资源通道和普通策略入口均收敛到它。后续策略更严格也不会被复用计划放宽。工厂不另造预算，保留 invocation-local BudgetTracker；这是每命令上限，不宣称整个 run 累计墙钟预算。

运行期 provider 普通异常继续固定 `verification_plan_provider_failed`，错误类型/身份/资源拒绝沿现有执行器及 runner 稳定码；不新增公共错误协议，不保存可信输入或原异常正文。runner 在对应工程步骤 CP step_start/模型调用前核 plan/session/tool/environment/resource；之前 CP trace、safe_point、prepare_policy 及 intent 的 starting/running/工作区审计动作仍可能发生，不宣称整个 intent 或 execute 零写入。

工程资源通道当前只接受 Linux/Landlock/network DENY/空 domains；macOS/Windows 不能因预设存在或 Plan 的平台名被开放。无普通 subprocess fallback。CLI/UI 现有“已配置；任务仍需通过执行检查”、enabled、按钮、API 和自定义 executor 不改，也不新增 readiness 协议。

孤立模板忽略 PYTHONPATH；src-only 工程、缺依赖、零测试、全 skip、断言失败可拒绝，不以路径注入、安装依赖或空测试取绿。框架输出可能被项目代码伪造，测试报告不是工程质量的全部证明；最终独立 Reviewer、受测 tree、CP/evidence 与独立验包门不变。

## 文件范围与验收

预计三生产文件：新 verification_presets.py、cli.py、autonomy.py；三个测试文件：新 tests/test_verification_presets.py、既有 test_workbench.py 与 test_autonomy.py；两 CI 选择文件：run_workspace_ci.py 和 test_run_workspace_ci.py。DEFAULT 已包含 workbench/autonomy，旧选择不删，新增 preset 模块唯一完整加载并有无静态 skip 配对守卫。其余 runner/verification/broker/config/loop/GUI/native/vendor/workflow/依赖不改；必要文档只记设计、计划和定点研究/持续对照。

TDD 正负控至少包含：真实参数解析/实际 cmd_workbench 到真实 NativeChainExecutor 的接线；无预设旧行为、未知值和未启用自动时前置拒绝；lexical 解释器原样、启动后及 Check 构造期间身份漂移；code/deepcheck 同一 Plan、新 execute/并发工单无共享；根/环境/身份漂移不重授权；任意 provider/custom adapter 原每步调用与签名保持。portable 测试不得用平台不便建 symlink 作跳过理由，身份变动 fixture 与真实解释器正控分开。

复用既有真实孤立 unittest 的成功/零测试/全 skip/失败/缺依赖、资源拒绝与独立 Reviewer/tree/evidence 回归，不复制另一个执行框架。软件模拟接线、实际子进程测试和实际 Linux 全工程往返分层记录；本片软件通过不能关闭后者、真实模型1→6/≥90%或 R2/R3 总门。设计双审→详细计划双审→单 writer TDD及自审→fresh全局规格/不同质量→root关联/20轮/DEFAULT/原完整preflight/compile-j1/七维自检/文档两轮/精确main发布→新SHA观察；不并行写源和全量验证。

## 研究输入与当前状态

历史[工作台预研](2026-10-09-r3-workbench-verification-research.md)保留3ef4时点；其旧“已启用”描述不代表当前文案。[本片独立刷新](2026-10-09-workbench-preset-upstream-refresh.md)已完成，Aider 固定 `5dc9490bb35f9729ef2c95d00a19ccd30c26339c`、Codex 固定 `0ada5d8806cdad498230d5b1b2924091e04c8feb`，两许可证完整读取为 Apache-2.0。采纳显式测试预配置、项目配置与可信授权分离、能力不足拒绝；暂缓任意命令和持久批准机制。新记录区分独立研究与 root 定点读取范围，并纠正旧 Aider 测试选项链接为 548–563；不把设计候选或上游单测当 ICODE 运行证明。无上游源码复制、新依赖或权限。

root 静态自审：方案 A 窄接线、默认不增授权；启动解释器与首次工程计划的冻结时点分开；精确内置类型局部缓存保留第三方语义；限额复用实际broker最小值，原生门与UI措辞不抬升。本设计尚未获得独立双审，未实现、运行新测试或发布；下一门为 fresh SPEC→不同 QUALITY。
