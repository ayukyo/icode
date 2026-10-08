# R2 pip安装的固定SKILL运行资源闭包

> REQUIRED SUB-SKILL: nbl.test-driven-development、nbl.subagent-driven-development。实施前设计与清单保留历史；包内核心资源已在fd68完成七项真实原生安装验收，详见末尾。不能把它等同整个SKILL、90%一致性或R2/R3总门通过。

**Goal:** 干净Python包安装后，无源码checkout、外部SKILL配置、用户Skill或运行时下载也能进入doctor及工单工作台，并消费同一固定ICODE-SKILL控制面。

**Architecture:** 构建时从固定gitlink只读提取必要运行资源，保留原布局、原字节和许可，wheel内解包为稳定只读资源目录；运行时定位包内默认来源。不复制实现逻辑、不另造CP或自动clone最新源码，不用PPT模板授权不明资源补充功能。

## 三问及实体基线

2026-10-08主代理隔离构建wheel、干净venv pip --no-deps安装，在临时cwd/-I/无ICODE_SKILL_ROOT下实际find_skill_root返回ConfigError。独立只读审查确认config只查外部显式/env/local/vendor/sibling/home、setup/MANIFEST无SKILL运行资源，doctor/workbench先load_settings，README仍clone子模块+editable；Skill独立install.sh不是Agent的pip fallback。已有安装API验收显式消费开发仓SKILL，不能称新机独立安装。

现有运行依赖通过Settings.control_script/gates_json/steps_dir、ControlPlane、ReasoningGate及CP动态inspection/linter加载；全部复用。构建与运行入口变化影响setup.py、MANIFEST/包数据、config.py、资源清单和安装/源码归属测试，不改vendor子模块或契约源。

## Task 1: 固定资源与许可闭包

- [ ] 完成
- [ ] 固定gitlink `b74c4c40f2246a6c4eea77e494dd57c642f3a9a3`、工作树/文件身份、原LICENSE及每个member hash；显式allowlist，不用全仓递归打包，也不从model/project输入路径选择资源。
- [ ] 审核候选：SKILL/LICENSE、schemas/steps/references、tools/icode_control.py与inspection_worklist.py/3lint脚本、workflow/reasoning/cheap-research gates。独立初步候选72tracked regular、1,922,179字节、0symlink只是候选；还须实际核对动态导入、lint数据、工作台和各catalog索引所需资源，不能先声称90%能力一致。
- [ ] 原字节/布局保留，不在打包时悄改gates或source。缺失、symlink/路径逃逸、摘要失配拒绝构建/定位；构建来源/成员/版本manifest与许可清单一并入包。sdist必须含同样闭包，脱离git构建也能验证，不能只在源码wheel成立。
- [ ] 禁止分发第三方PPT template.pptx/preview.png与无许可资产；MIT代码/元数据与受限素材分别处理，保留作者声明。包内无需runtime联网提取最新Skill，也不把zip解压到用户全局skills目录。

## Task 2: 默认来源及解释器边界

- [ ] 完成
- [ ] config新增明确包内来源，开发子模块/显式外部配置保持兼容；默认安装不靠当前工作目录补足资源。包内缺失/验证失败不得静默降成不完整源或裸运行，错误稳定且给普通用户可执行说明。
- [ ] 真实核对catalog中的python3命令和CP linter执行：Windows/非PATH pipx venv不能依赖系统同名解释器。先查已有可信接口；没有兼容接口时另定最小源码/上游契约变更，不生成不安全shell shim或篡改固定字节。Settings.python与资源root必须贯穿实际子进程。
- [ ] 资源只读，工单及checkpoint仍只写任务目录；并发实例不修改包数据，不制造全局安装状态。显式外部Skill是原高级能力，不将它冒称包内来源。

## Task 3: 真正安装验收

- [ ] 完成
- [ ] RED→GREEN：无外部源码/环境/用户Skill、-I、临时cwd、实际installed module字节归属；不只运行--help或mock load_settings。
- [ ] 直接wheel及脱离checkout的sdist重建wheel，独立比对manifest/成员字节/许可排除，pip --no-deps安装后实际doctor、步骤索引、handshake、CP三linters和状态转换、workbench真实建单/查找/列表/中英入口。doctor隔离分仍如实展示未通过，不用readonly UI等于auto ready。
- [ ] 新矩阵20轮、本机关联config/control/workbench/契约/evidence、独立SPEC→QUALITY、7维自检、完整preflight及compileall≤j6、治理/官网/竞品/diff；然后main提交推送、跨平台原生安装CI。Windows x64/ARM64与mac Intel/Apple Silicon都必须实际无外部Skill，不以Linux安装或skip替代。

## 取舍与未覆盖

本片只闭合现有工作流资源的分发和定位，不解决Windows正式启动/UAC/WFP或macOS单任务配额；不发布未测完整R2/自动模式。Git/构建工具链、可选Office素材与安装脚本不是被打包即可宣称所有能力已覆盖，相关前置及缺项需实测和另片处理。

观察2026-10-08：ICODE-SKILL固定gitlink根LICENSE为MIT；主代理完整读tools/ppt/NOTICE及[第三方素材当前NOTICE](https://github.com/lmori1301/Agent-PPTSkill/blob/main/NOTICE.md)，模板仅学习研究/非商业限制明确，不套用根MIT。采纳固定资源与许可边界；不适配无筛选vendor打包/移除署名/运行时拉main。独立研究不改变素材授权，也不替代实际安装测试。

**Execution Mode:** serial implementation, independent read-only research/reviews

## 独立实施前审查与已授权前置

独立审查复算72候选的组成为2根文件、3catalog、28references、7schemas、27steps、5tools，数量/字节/普通文件性一致；动态inspection与三lint源在内，但steps仍引用未含Office/TB/study工具，因此不得称整个SKILL能力闭包。无写实体负控：绝对Python启动CP、仅该子进程PATH为空，三gate均fail_closed且实际尝试python3；无现成解释器参数/环境接口。进程局部C locale且关闭UTF8模式时，action-policy缺路径失败产生UnicodeEncodeError/stdout空；-X utf8同命令返回合法ok:false JSON。

主代理已核对本机上游最新 `74473e5`（工作树干净）仍同一python3执行机制，不能假设新版本已修复。2026-10-08用户已明确授权最小ICODE-SKILL三lint当前解释器/UTF8及对应测试修改，验收后上游main提交推送，再更新本工程固定gitlink。上游在独立目录实施、独立审查；当前CLI冻结验收仍使用原gitlink，不并发改vendor。其它已授权CLI/shared预算工作继续，不能用PATH shim/运行时monkeypatch绕过这个前置。

### 上游最小修复验收及发布

ICODE-SKILL main已提交推送 `1693651c1bd7daad3272eb054f0f81d6f254d08d`，主代理git push成功及新鲜ls-remote一致，工作树干净。严格仅两个文件：tools/icode_control.py与新增tests/test_control_linter_runtime.py。仅三个固定gate id及原argv前两项精确匹配才用sys.executable/-Xutf8；二进制捕获在主线程严格UTF8解码两输出，损坏编码失败关闭并继续收集。自定义命令保持原text/locale、旧str测试替身兼容，catalog/strict/step/audit-verified/cwd/180秒timeout/OSerror及原对象中断合同未变。

TDD新12方法中5断言FAIL/0 ERROR，GREEN后20轮240 PASS/0 SKIP（没有记录汇总耗时，不追填）；实施者Python3.11.15关联pytest七模块184 PASS+17子场景，43.88秒/0 SKIP；下游显式消费本次新CP关联46 PASS。宿主3.10.12原shell metadata9/transition13/close23/thinking48/cheap54全部PASS，含真实本地stdio。未运行会make clean/写仓内demo的workflow shell，不将其记为通过。

主代理独立SPEC全读本片运行函数/上下文/两测试文件及完整regression322行，实际311新12+index4共16/0 SKIP/0.715秒，nice10原regression shell宿主3.10实际26 PASS；其20项索引writer不是编译，未更改脚本并发或-j6构建要求。不同代理QUALITY独立16/0 SKIP，加三项真实子进程坏UTF8 stdout/坏UTF8 stderr/坏JSON负控皆失败关闭，后续真实gates仍收集通过。两文件AST/compileall-j6/diff与限定凭据扫描PASS，只有两授权文件入上游commit。

生产SHA256 `0b7e2577844f135269bdcc78bee195ad974a350f20792af7de46b2bdae76564c`，新测试 `aeb7473b3c8a0d2586f362fdbd349b4824458bc4aaa746370512e81e90e42b83`；两独立审查前后完全一致，7维自检本机通过。采用CPython v3.11.15官方sys.executable/启动UTF8/binary capture机制，PSF2及本仓MIT，无复制或新运行依赖。未声称Windows原生或整个上游全仓测试通过。

本工程gitlink仍保持旧固定版本，待共享预算片完成冻结交付再独立bump/完整兼容回归，不混入其受测树。相对旧gitlink到上游修复前74473e54，CP/gates/schemas无额外变化；steps/docx/install有已存在文档变化，仍需新固定资源清单重核。outer CP UTF8、包内资源和真正pip-only安装尚未实现，不以此提交关闭它们或R2/R3。

### 固定版本接入（2026-10-08，单独验收）

共享预算片已独立提交并推送 `edbfbe83a97e1fc2a72beb6b024aa57632696708`，fresh ls-remote一致。随后本工程vendor仅detach到已授权的 `1693651c1bd7daad3272eb054f0f81d6f254d08d`，暂存精确gitlink，子模块工作树干净且现有guard通过；上段“仍保持旧版本”是升级前历史，不代表当前状态。

独立读取b74→169完整50文件差异并区分：CP唯一本轮变化是最小三lint修复；workflow/reasoning gates、schema、三lint、inspection_worklist和LICENSE/NOTICE均未变。crosscheck有真实scope/范围债务语义变化，但Agent核心不调用该入口；核心既有chain inspection prepare的allow-incomplete是另一合同，不混称。WorkBuddy安装/MCP和DOCX默认自动获取/用户runtime写入确有其它既有变化，未运行这些安装器/渲染器，不用核心通过外推它们。

主代理新vendor实际固定lint12/12、0SKIP、0.546秒，并连续20轮240 PASS、0SKIP、10.714秒，CP摘要每轮一致；含真实空PATH、C locale关闭UTF8/中文路径及strict拒绝。安装后的既有Agent wheel在仓库外/-I/无环境Skill下显式消费新vendor，六预算+五CLI恢复实际11项全部PASS；更新临时CLI验收fixture的runner预期摘要到共享预算最终版本，不改产品或放宽断言。这仍是外部Skill兼容，不是包内免配置。

独立SPEC：项目3.11.15上游12/12、0SKIP、0.534秒；下游13模块183/183、0SKIP、82.882秒，合195 PASS，涵盖control/contracts/handshake/chain/chain_offline/CLI/恢复/sharedbudget/hardstop/workbench/disclosure/reasoningbudget/recovery；真实失败finish/checkpoint、未知副作用不重放、审查产物不伪造与自动模式关闭保持。CP/新lint测试/workflowgate/reasoninggate前后摘要一致。不同QUALITY及最终全仓门禁另行验收后才提交本工程gitlink。

不同作者QUALITY实跑上游12/0SKIP/0.498秒，下游八模块81/0SKIP/31.738秒，外加真实坏stdout UTF8/坏stderr UTF8/坏JSON三负控均失败关闭且剩余gates仍收集；无阻断。限定CP与测试摘要前后保持，无进入Office/MCP/install分支。非阻断文档问题：上游steps/install.md:42合并了两行表格，后续另行修文，不扩本片最小源码授权。主代理最终preflight于08:42 UTC三道全部PASS，发现2030项；compileall-j6/治理/官网/竞品/diff及新固定子模块完整性通过。

【架构级自检报告】

- ✅ 语法/编译：固定差异AST/Shell及本工程compileall-j6通过。
- ✅ 依赖/调用链：新vendor真实进入现有控制面及契约链。
- ✅ 逻辑/边界：空PATH/中文/strict、共享计费300/301及治理拒绝通过。
- ✅ 异常处理：UTF8/JSON/超时/启动失败/中断与checkpoint保持通过。
- ✅ 关联模块：195独立SPEC、93独立QUALITY及11安装包实际场景通过。
- ✅ 兼容安全：自定义lint/旧状态门/未知副作用/自动模式关闭保持，无KEY。
- ✅ 可运行性：Ubuntu新固定版本与全仓守护通过；异平台和pip-only另验。

### 包内资源下一片的独立复核

独立研究固定SWE-agent `3ea751c087f32b16e039a2233dd6eefecef325d5`（MIT），实际源码仍依赖clone/父目录config/tools，不能用作pip-only成功例；记录及原始链接见[持续竞品对照](../../agent-landscape-live.md)。采纳PyPA包内数据与wheel/sdist分别验证，不复制上游或加依赖。

新169候选仍72tracked普通文件，1,928,781 bytes，较旧版本五成员变化，必须重新固定全部hash。机器CP直接源/动态inspection/三lint闭包未发现候选外必读项，但指南另有43个真实候选外字面引用，不承诺整个SKILL或90%能力闭包。资源共同staging必须先于setup.py Linux提前return；sdist release tree也生成同一原字节闭包，脱离Git验证构建，不能只build_py成功。最低Python3.11不返回as_file的已清理临时目录。默认包内损坏/缺件明确拒绝，显式外部高级Settings独立兼容；只读消费不冒充OS级不可修改或manifest等于签名。

### 包内入口及构建接线：本机最终冻结验收（2026-10-08）

上面任务清单和旧b74字节数保留为实施前历史。本轮固定169的72文件共1,928,781 bytes，分组2根文件/3catalog/28references/7schemas/27steps/5tools；manifest SHA256 `1afcdfa48214a5a0c16f14c9bf25617bb1015e8fbda7e3de3a613d8dc2b6986c`。共同build_py/sdist staging、安装默认来源及outer CP当前解释器/-B/-X utf8已实现，显式/env/local高级来源与开发vendor/sibling兼容。资源完整性在默认Settings发现时验证，不承诺每次CP的原子校验、OS不可修改或发布者签名。损坏安装包即使存在合法HOME Skill也拒绝默认降级。

生产冻结：setup `379b05227b6c6036b820f4b1f1c5417a6e173156f655315a29f5b17e74f7a79b`，MANIFEST `8dcb411289fde525e42dc346c8ed9ace2f1ef7e5ea3c1c9ae06b9c061974031d`，pyproject `be6b67a19438de2681ac8ecbd17823048370c14e035a2e27e3b86181059dc99f`，config `dbacfa889e3600659f064613746f535519042582440b725ebfafa57f22e5f75a`，control `bab7da59d06d52c3fa5383c1676baa15b3c0ec109c92ba4a9812ebd7dffe8781`，skill_resources `9b2c51e4f3d75fc26f2a5b84bc8db87cbabb16ae49dfe24f373b605e91c480d9`，最终测试 `4141221e69616b4bbe933dfbf073f8d358060905c833d3b305da215d24760cba`。核心运行依赖仍为零；setuptools>=80仅构建/开发验收，不把本机79的诊断构建记为正式通过。

正式环境Python3.11.15/setuptools84.0.0。最终18方法连续20轮360 PASS、0FAIL/ERROR/SKIP、308.713秒，各轮八文件摘要一致；此前360/265.831秒使用旧测试摘要，仅历史。关联十模块303 PASS、0SKIP、161.208秒。独立SPEC18+176共194 PASS、0SKIP；不同作者QUALITY18+48共66 PASS、0SKIP，加实际staging重复运行、最后源件损坏前零写入、目标外部symlink拒绝三负控，摘要保持一致。

直接wheel及仓库外无.git/vendor的sdist重建wheel各自安装到新venv，pip --no-index --no-deps、-I、空PATH、临时HOME/cwd、关闭locale UTF8，实际执行doctor/steps/handshake/三lint及真实动态inspection prepare/check失败关闭；工作台两语言真实建单/列表/搜索/详情。验收未通过的handshake/inspection状态如实保留init_in_progress及空open_steps，不能把fixture计划称最终审定计划或全流程成功。测试显式移除PYTHONDONTWRITEBYTECODE环境，记录真实installed bundle的原字节/成员不变；只在可丢弃venv清理测试缓存。移除outer CP的-B的独立RAM负控实际1FAIL、0ERROR，新增inspection_worklist pyc被发现，证明确实覆盖动态导入而非仅mock。

许可：原MIT LICENSE入包；受限第三方PPT模板/预览不入包，steps中的MIT说明仍可分发；43条候选外指南引用未补齐，因此本片不是全SKILL能力或90%一致验收。安装脚本、MCP、Office/TB外部能力没有因打包而自动运行或宣布通过。

CI本机冻结：ci `843b137bb4da8a29347e17e191e18c88f85e2725928c4b2868f574cfd8431993`，provenance workflow `65c28e7984bdd8beb88de045782233734de33289c93720e093b3381910609a22`，新接线测试 `3499445bc339d616a201752db255a2d563229a524de1e2d04a37a6ec022a7fbf`。新增七项真实安装矩阵覆盖Ubuntu/mac Apple/mac Intel/Windows x64/ARM64的311及Windows双架构312；四既有wheel构建入口同步递归固定子模块，七消费者首次checkout用步骤局部GIT_CONFIG_COUNT禁止autocrlf，避免子模块CRLF破坏原字节。没有修改core依赖、全局Git配置或CI权限；OIDC/attestations仍只限可信main签名job。独立CI SPEC25 PASS，QUALITY35 PASS且七新方法20轮140 PASS、0SKIP/23.093秒；40次本地真实递归clone的CRLF负控/原字节正控均成立，原仓Git配置不变。

【架构级自检报告】

- ✅ 语法/编译：本片AST/JSON/TOML及workflow YAML解析通过，整体最终门禁另记。
- ✅ 依赖/调用链：构建→默认Settings→CP→三lint/动态inspection→工作台实际安装链闭合。
- ✅ 逻辑/边界：固定原字节、缺件/损坏/路径/硬链接及不安全目标均有负控。
- ✅ 异常处理：损坏编码/JSON、构建失败、默认资源失败关闭及原中断合同保持。
- ✅ 关联模块：303本机关联、194独立SPEC与66不同QUALITY通过。
- ✅ 兼容安全：高级外部来源、strict/状态/自动模式关闭不变；无素材越权或新运行依赖。
- ✅ 可运行性：Ubuntu真实wheel/sdist安装闭合；新SHA七项原生安装CI待验，不外推Windows正式运行器或R2/R3整体验收。

整体冻结后最终preflight于2026-10-08 09:52 UTC三道全部PASS，发现2067项；守护成功时不输出unittest skip明细，不声称2067项零skip。最终DEFAULT238 PASS、0SKIP、97.310秒。compileall-j6/治理/官网/严格竞品/diff通过，包内八文件、CI三文件及最终UI四文件冻结摘要未变。新SHA远端矩阵待推送后核验，当前版本未发布PyPI或Release。

### 精确main发布与原生安装门收口（2026-10-08）

root已commit/push `fd68b1f77d9050776e3e2fd263d19b4931affa66`，git push及新鲜ls-remote/独立GitHub main读取一致；24文件1781+/29-，当时工作树干净。先前“新SHA待验”为历史。本轮未发布PyPI/Release，不新增分支。

[主CI37759817771](https://github.com/ayukyo/icode/actions/runs/37759817771) attempt1完整44项=39success/2既有Reviewerfailure/3skip。独立只读观察实际逐项安装日志，并由主代理完整44项job页面核对七success；不是只看运行名称或Action completed。

| 包内安装原生门 | Job | 实际18方法结果 |
| --- | --- | --- |
| Ubuntu / 3.11 | 113253227047 | 18PASS / 0SKIP / 19.951秒 |
| macOS Apple / 3.11 | 113253227005 | 18PASS / 0SKIP / 91.044秒 |
| macOS Intel / 3.11 | 113253227157 | 18PASS / 0SKIP / 97.863秒 |
| Windows x64 / 3.11 | 113253227307 | 18PASS / 0SKIP / 47.238秒 |
| Windows x64 / 3.12 | 113253227190 | 18PASS / 0SKIP / 48.344秒 |
| Windows ARM64 / 3.11 | 113253227145 | 18PASS / 0SKIP / 48.575秒 |
| Windows ARM64 / 3.12 | 113253227360 | 18PASS / 0SKIP / 48.477秒 |

总126实际PASS、0SKIP，含directwheel、detachedsdist、默认来源、CP/inspection原字节无pyc写入、双语工单与损坏/链接负控；链接拒绝均实际执行。全Python311 job113253226953为2067/451.633秒、312 job113253227078为2067/533.109秒，均OK及71既有skip，不能称全2067实际跨平台通过。workspace Ubuntu238/139.758秒、mac238/189.140秒均0skip，WinARM237/224.120秒、Winx64237/229.466秒各9既有skip。

[来源证明37759817844](https://github.com/ayukyo/icode/actions/runs/37759817844)实际5/5success：validate113253226485真实Go/license9/preflight3道；签名x64311 job113255868266/artifact11541719102，x64312 job113255868232/artifact11541773777，ARM311 job113255868275/artifact11542920310，ARM312 job113255868388/artifact11541803931，四者实际crypto/离线/原生正负控及metadata/setup命令拒绝PASS，仍launch_authorized=false。[Pages37759817724](https://github.com/ayukyo/icode/actions/runs/37759817724)2/2success，deploy113253285612的pages_build_version为精确fd68，artifact11540874675。

旧Reviewer ARM113253227001/x64113253227297仍exit78/双栈10035/等待过期，不是DENY或新增安装失败；四Linux installed探针通过但22lease无完整conformance信用、24lease两skip，不外推完整隔离。本次10053未复现不证明根因永久消除。三run已终态停止观察；后续只观察新SHA。包内核心安装本片收口，Windows正式执行、macOS每任务quota、宿主工程验证/Reviewer/模型1→6与90%矩阵仍独立待验。
