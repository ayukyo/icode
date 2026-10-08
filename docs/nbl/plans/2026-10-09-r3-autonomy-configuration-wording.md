# R3 自动模式配置提示 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development task-by-task. Steps use checkbox tracking.

**Goal:** 区分自动模式已配置与真实执行检查已通过，不改变旧能力接口。

**Architecture:** 仅替换 CLI enforced 分支和 UI 同一翻译键的两个值；保留 server/API/custom executor/按钮/保护卡片逻辑。三文件唯一写者，root唯一文档写者，原生CI与研究只读独立。

**Tech Stack:** 既有 Python unittest/CLI、静态中英 JS 翻译，无新增依赖。

---

基线 main ccbe67；[设计](../specs/2026-10-09-r3-autonomy-configuration-wording-design.md) 冻结 SHA256 `e4705bacbfe83e3aa1b73d1f163890f4389e8b0d5cd9ac99dbf26f112172b177`，独立 SPEC→不同 QUALITY 均 Critical0/Important0/Minor0，实读当前调用链。用户自主连续开发及仅main授权覆盖技能默认工作树/分支/重复等待选择。不会放宽原生门或替待选择工厂作决定。

## Task 1：软件 TDD 与最小三文件显示修正

**状态**
- [x] 任务完成

新鲜唯一作者已STOP，Task1下述各实施步骤已完成。真实RED为2methods/2AssertionFAIL/0ERROR/0SKIP、0.011秒；三生产字符串替换后2GREEN/0SKIP、0.010秒，定点两模块86PASS/0FAIL/ERROR/SKIP、26.879秒。内置SPEC→QUALITY无未修问题；两Python compileall-j1、node --check、diffcheck均退出0。作者用实际字节比较确认两生产文件仅三字符串替换，测试仅加68行、旧断言未改。root另完整读实际diff、两生产文件及旧测试全文/新增方法，node检查/diffcheck通过；作者自审不替后续全局两审或root独立86复验。

冻结三源码SHA：cli `7848c4d7e57f61899cf4aac7621cb0d01a6753034ea44f1fc775d2a73bbe915f`；app.js `5370d67e01886195a36965e233b513a850a2582b78d641993d9b65d199415e71`；test_workbench `b76509630ec236ad8783ea964aa5773ff743e8a1c62ecf7bdb3850d8e481db21`。按此顺序sha256sum输出再sha256sum的aggregate `386ae46634b3407733527d76ec957689bc48d7ef00e6bfe425692d95b9b1d880`。源码停止写入；全局审必须核当前三SHA及冻结设计e4705b，不沿作者结果授通过。

**Dependencies:** None
**Parallelizable:** No（唯一三文件源码写者）

- [x] 全读 `src/icode/cli.py`、`src/icode/workbench_assets/app.js`、`tests/test_workbench.py`，核workbench/autonomy实际接口。只修改这三个文件，禁止重构或新增readiness属性/检查；root已有docs不碰。
- [x] 在 TestWorkbenchCLI 新增以下真实 cmd 调用软件测试；同现有fixture屏蔽模型配置/HTTP服务和永久等待，不屏蔽 cmd_workbench 的判据/输出。disabled不构造runner；三状态参数与stop保持。先执行必须因 enforced 旧文字而 AssertionFAIL，不因fixture异常：

```python
def test_自动模式配置提示不代表任务执行检查已通过(self) -> None:
    cases = (
        (False, False, "not_configured", "未启用"),
        (True, False, "policy_unavailable", "已配置，执行前阻断（策略级隔离未就绪）"),
        (True, True, "enforced", "已配置；任务仍需通过执行检查"),
    )
    for enabled, ready, isolation, expected in cases:
        with self.subTest(enabled=enabled, ready=ready):
            argv = ["workbench", "--workspace", "/srv/project", "--no-browser"]
            if enabled:
                argv.append("--enable-autonomous")
            args = _build_parser().parse_args(argv)
            sandbox = SimpleNamespace(is_real_isolation=True,
                policy_contract_ready=ready, wrap_policy=lambda *a, **k: None)
            output = StringIO()
            with patch("icode.cli.load_settings", return_value=object()), \
                 patch("icode.cli._build_runner", return_value=(None, None, None, None, sandbox)) as build, \
                 patch("icode.autonomy.NativeChainExecutor") as executor, \
                 patch("icode.workbench.WorkbenchServer") as server_class, \
                 patch("threading.Event") as event_class, redirect_stdout(output):
                server_class.return_value.start.return_value = "http://127.0.0.1:1234/"
                event_class.return_value.wait.side_effect = KeyboardInterrupt
                self.assertEqual(cmd_workbench(args), 0)
            self.assertIn("自主执行：" + expected, output.getvalue())
            self.assertNotIn("自主执行：已启用", output.getvalue())
            self.assertEqual(server_class.call_args.kwargs["enable_autonomous"], enabled)
            self.assertEqual(server_class.call_args.kwargs["autonomy_limits"], {
                "max_turns": args.max_turns, "budget_tokens": args.budget_tokens,
                "isolation_level": isolation,
            })
            if enabled:
                build.assert_called_once_with(args)
                self.assertIs(server_class.call_args.kwargs["autonomy_executor"], executor.return_value)
            else:
                build.assert_not_called()
                executor.assert_not_called()
                self.assertIsNone(server_class.call_args.kwargs["autonomy_executor"])
            server_class.return_value.stop.assert_called_once_with()
```

- [x] 在 TestWorkbenchAssets 新增精确中英文资源测试；必须先因缺新值 AssertionFAIL：

```python
def test_自动模式中英文配置提示不授执行就绪(self) -> None:
    js = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")
    self.assertIn('capabilityEnabled: "已配置；任务仍需通过执行检查"', js)
    self.assertIn('capabilityEnabled: "Configured; execution checks are still required for each task"', js)
    self.assertNotIn('capabilityEnabled: "已启用（仅服务端配置）"', js)
    self.assertNotIn('capabilityEnabled: "Enabled (server-side configuration only)"', js)
```

- [x] 精确两方法运行记录 RED：`PYTHONPATH=src:. python -B -m unittest tests.test_workbench.TestWorkbenchCLI.test_自动模式配置提示不代表任务执行检查已通过 tests.test_workbench.TestWorkbenchAssets.test_自动模式中英文配置提示不授执行就绪 -v`。预期2 methods失败、0ERROR/0SKIP，确认后只替换三处文字。CLI：`"已配置；任务仍需通过执行检查" if isolation_level == "enforced" else`；JS中两新值见上。不改任何其它source行。
- [x] 两方法 GREEN 后执行 `PYTHONPATH=src:. python -B -m unittest tests.test_workbench tests.test_autonomy -v`；真实数量/时长/skip记录，不猜。旧测试原样保留，软件 orchestration/mock 不计原生或模型证明。
- [x] 实现者内置 SPEC逐条→QUALITY逐条自审并修清，无未修问题才能报告DONE；compileall-j1两Python（JS不适用Python编译）、diffcheck、三文件SHA。不得commit/push或启动20/DEFAULT/full，STOP。

## Task 2：全局审查、串行守护与发布

**状态**
- [x] 任务完成

**Dependencies:** Task 1
**Parallelizable:** No（冻结源码后软件门串行；只读研究/原生观察并行）

GLOBAL SPEC已结束：新鲜审查者全读冻结三文件、设计及真实API/manager/provider链，逐字节核生产恰三处替换、旧tests移除新增两methods后等于HEAD；missing/extra/mismatch与Critical/Important/Minor均0。独立实际CLI+Assets两类16PASS/0SKIP、0.020秒，前后冻结SHA/aggregate一致。不同新鲜GLOBAL QUALITY正在只读审查；未获批准不开root定点/20/DEFAULT/full。

GLOBAL QUALITY现已结束（覆盖上一段待审状态）：不同新鲜审查者完整读取同一冻结源码及actual调用链，Critical/Important/Minor均0，独立CLI+Assets16PASS/0SKIP、0.022秒，node语法/diffcheck通过，设计及三SHA/aggregate前后保持。root已开始独立两模块86范围的实际定点，退出后才20轮，后再DEFAULT/full；这些未运行完成前不填软件门通过。

root独立定点已完成：86PASS/0FAIL/ERROR/SKIP、27.414秒，实际HTTP/custom executor/生命周期兼容保留。退出后才20轮CLI+Assets：每轮16PASS/0SKIP，共320PASS、0FAIL/ERROR/SKIP，wall0.480秒。20轮退出后才启动DEFAULT，目前仍运行；不是新增HTTP重复320次，也不据预计数量填写DEFAULT/full结果。

后续实际状态：DEFAULT已退出0，463PASS/0FAIL/ERROR/SKIP、164.734秒，installed bootstrap verifier byte binding为PASS。其退出后才启动原三守卫完整preflight；只读wrapper保留原`subprocess.run`解释器、argv、cwd及返回语义，仅打印实际unittest摘要和子进程wall。密钥扫描和子模块完整性已通过，full仍运行，暂不填数量或通过。

完整preflight现已实际退出0：2315 total/2256PASS/59既有环境SKIP/0FAIL/0ERROR，unittest482.365秒、子进程wall482.603秒，三道守卫全部通过。退出后才全src/scripts/tests compileall-j1、node --check、governance、site、landscape排期及diffcheck，全部退出0。三源码与设计冻结SHA未变，六PE源码保持923e226，vendor1693651c未改。新增二methods对应full/DEFAULT各比上一片增加2，不以预计计数填通过。

- [x] root全读三文件实际差异/上下游并冻结SHA。新鲜独立GLOBAL SPEC，之后不同GLOBAL QUALITY；自审不能替代独立审。无需整改，当前冻结两审各0问题。
- [x] root独立定点 `tests.test_workbench tests.test_autonomy`；通过后20轮 `tests.test_workbench.TestWorkbenchCLI tests.test_workbench.TestWorkbenchAssets`。每轮16、总320PASS，0SKIP；真实HTTP兼容在定点/full另测，20轮不冒充重复真实HTTP。
- [x] 20轮退出后运行 `PYTHONPATH=src:. python -B scripts/run_workspace_ci.py`，退出后才完整preflight；指定已有Python/Go路径、GOMAXPROCS1、GOFLAGS=-p=1、GOTOOLCHAIN=local、CMAKE_BUILD_PARALLEL_LEVEL1。完整 preflight 可用只读wrapper打印 guard_tests 实际子进程摘要，保持解释器/argv/cwd/返回码与测试选择。禁止改守护、加skip或并行两套全量。
- [x] `python -B -m compileall -q -j 1 src scripts tests`，governance/site/landscape/diff/密钥/子模块门通过；root记录7维及分层验收，吸收独立研究机制与未通过原生结果，不授R2/R3总门。
- [x] 精确stage三源码和必要文档，忽略docs仅精确force-add；核父ccbe、cached路径/hash/diff。完整守护通过后按用户授权main commit/push，独立查remote refs及官方main；不开新分支/release/PyPI，不改vendor/权限或取消原生run。新SHA网站/CI与本片软件门分别观察。

发布记录：main提交并推送`b3897f57cb8f258834486e1fb31c8b85e9ecae5d`，父ccbe67。root精确核9个index路径、三源码index bytes SHA/父及cached diff；普通add的ignored docs提示退出1已处理，仅对六个必要docs精确force-add并重新核清单，不扩大到下一片设计。push退出0，独立remote heads仅main且SHA相同，GitHub官方main与父亦精确一致，推后tracked工作树干净；没有vendor/分支/release/PyPI变更。

新SHA CI37845034256、provenance37845034221、Pages37845034262启动。root读取Pages元数据completed/success，仅此不能替actualdeploypayload；独立只读观察者继续逐run核新证据，旧ccbe三run已终态STOP。本片软件门和main发布已关闭，异平台原生/官网消费继续分层记录。

Pages原生消费已补核：独立观察者读validate113543670522精确checkout b389与artifact11579421645，root另回读deploy113543742515，actual payload artifact_id相同、pages_build_version完整b389，21:12:40UTC实际Reported success。Pages终态STOP；这证明新SHA网站发布，不给Windows或模型执行信用。新CI的x64Reviewer仍是10035等待过期与capture缺件，原生整体没有因此通过。

新主CI终态：run37845034256 completed/failure、完整44jobs=37success/4failure/3skip/0cancel，独立观察者与root各回读metadata及决定性日志。Linux3.11 full2315 total/2244PASS/71既有skip/0F/E、438.986秒；3.12同计数470.164秒。macworkspace463PASS266.623秒、lease75PASS3.752秒为该job非verbose摘要，不冒充逐method或资源门。Windowsx64/ARM workspace各457total/F1E1/20skip、331.690/325.984秒，incremental ERROR均为inspection Git10093、legacy code FAIL均Git10038；root分别全文检索两新log均未见windows_directory_changed，不能称旧错误已修。两个Reviewer仍双栈10035 wait_expired、IPv6 evidence_unavailable、no_matching_event/archive_member_missing及cap正控exit91；不授网络门。主CI已STOP，不取消或继续轮询。新provenancevalidate已通过，四签名格尚在构建，不能沿用ccbe的采集信用。

root另独立补取本轮两个Reviewer完整decoded日志：x64 job113543670976与ARM job113543670904均实际runner gate ready，但child订阅返回0x00000005、双栈10035/wait_expired/connect_denied=false，host observer no_matching_event、capture archive_member_missing。privateNetworkClientServer正控两格exit91/ipv4_connect、无canary、readiness_credit=false；原候选仍exit78。这是尚未证明网络拒绝，不把没有连接当已拒绝，也不据正控inconclusive提高权限或修改产品SID。回读后STOP。

来源工作流后续终态（覆盖上一段尚在构建状态）：run37845034221 completed/success，validate及x64/ARM64×Python3.11/3.12四格全部成功，四artifact均绑定b389、未过期。root独立读取四个新签名job的完整decoded日志和闭集receipt：x64 3.11 job113547877722/proof54105185/artifact11579777788；x64 3.12 job113547877830/proof54105350/artifact11579484002；ARM 3.11 job113547877707/proof54105708/artifact11579494081；ARM 3.12 job113547877704/proof54105417/artifact11579124494。每格实际采集先于attestation，helper SHA逐字匹配实际attestation digest；四格各19条带时间戳的安装脚本PASS阶段（不是19个unittest methods），包括最后signed-mode CI wheel exported阶段。root核新receipt的完整imports/manifest base64与先前独立严格解码回编码的ccbe字节完全相同；独立观察者另对本轮四格严格解码回编码。receipt三个标志parse_complete/runtime_load_verified/source_launch_verified仍全部false，actual CAPTURED production_authority=none。四来源格及工作流全部STOP，既有终态不再轮询。

本轮helper SHA：x64 3.11 `260b4e0c1e1ee0828968f2487dc43105bec71fa7330f3469e6110a883156bc69`；x64 3.12 `bfd61c0d2b8f2f5ff9f60a9d994e2b2a15b6082ee928aefc313a86d4df8a35da`；ARM 3.11 `afab46a560b2062fb8df93e841094912d74ace37b6719f5a2c2a0348469665d1`；ARM 3.12 `ce4f8ea766f501d74858c69d5557674216ceb8927bfa00f9f978a8835be5a4d2`。原生OS实际为Server2025 x64 image20260925.250.1与Win11 ARM image20261004.176.1，Python3.11.9/3.12.10；不冒充Win10、标准用户、首次UAC、完整PE解析、生产加载、配额或模型1→6证据。root未下载新二进制或授R2/R3整体通过。

## acceptance_contract / verification_matrix

| Layer | Required | Consumer | Scenario | Environment/device | Baseline/artifact | Action | Evidence | Result |
|---|---|---|---|---|---|---|---|---|
| static | yes | CLI/UI/API | 仅三文字，旧enabled/按钮/custom executor不变 | 当前源码 | ccbe/设计e4705b/源码386ae466 | 独立设计与实现双审、实际diff | 设计与实现双审各0问题，两个实现审各16PASS/0skip；生产恰三替换 | verified（本片静态） |
| unit/host | yes | cmd_workbench/翻译/HTTP/manager | 三状态、中英、旧兼容 | 本机软件 | ccbe/源码386ae466 | RED/GREEN、定点、20/DEFAULT/full | root86PASS，20轮320PASS，DEFAULT463PASS均0skip；full2315/59既有skip/0F/E，三道通过 | verified（本片软件） |
| native/model | no（本片不授信用） | R2/R3全阶段 | Windows网络/快照、真实六步等 | 跨平台 | 各自新SHA | 按各独立计划另验 | 本片不替代 | not_applicable（仅本片） |

## gaps / verdict

本片冻结实现、独立双审、root完整软件门与main提交推送已通过，发布记录见Task2。没有新增配置/执行权限，也未关闭工作台provider、资源门、模型六步、Windows/macOS隔离与配额缺口。`verified`仅限本片软件层及发布，不报告R2/R3完成。

## 架构级自检报告（限定三文字软件切片）

- ✅ 语法/编译：全src/scripts/tests compileall-j1、node语法及完整测试通过。
- ✅ 依赖/调用链：旧API/server/executor/翻译key不变，CLI三分支实际调用验证。
- ✅ 逻辑/边界：enabled只是配置，缺计划/策略仍按原流程阻断；双语与三状态覆盖。
- ✅ 异常处理：原停服/中断与HTTP错误路径在旧回归保留；未新增异常或原生处理。
- ✅ 关联模块：三文件成对、旧测试逐字保留，无工厂/资源/按钮/权限变动。
- ✅ 兼容安全：独立双审0问题、定点/20/DEFAULT/full通过，无新增skip或执行授权。
- ✅ 可运行性：仅本机软件范围已实际验证；原生/模型未由本片运行，不称R2/R3整体100%。

root计划自检：设计每节有Task1/2对应；无缺API/模糊步骤；三状态fixture、两语言、非适用CLI国际化边界清楚。root专有文档变化与正在观察的PE片保留分层。

---
**Execution Mode:** serial
