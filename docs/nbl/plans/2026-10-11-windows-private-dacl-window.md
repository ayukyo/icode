# 私有直接DACL窗口：实施计划

软件基线main `e7833509030392e88a6ce11e9b455064925c0e06`。按[设计](../specs/2026-10-11-windows-private-dacl-window-design.md)，用户推荐方案自主执行/main-only，不重复停点；TDD、双独立审查、实际原生与安全边界保留。固定consumer新原生CI另验，不借信用。编译-j1。

当前接续基线已为main `023a0c0c3f71170cb167011f1c997266406fb9e7`：仅修前片输入负控测试的平台假设，生产代码及权限不变。15:28 UTC推送核remote后，Task1恢复独立observer与三窗口控制器TDD；之前10项draft暂冻仅是完整守护的稳定窗口，不代表Task1完成。新四格Windows复验与本片开发并行，未闭合前不授跨平台软件通过。

Task1实现首轮SPEC指出初始身份绑定、caller登记、创建ownership及metadata范围问题，修后SPEC零问题。不同QUALITY另指出mkdir/exclusive-open成功至created登记之间的中断清理窗口；writer继续真实trace RED后最小修复，修前30项/600轮便携和278关联仅历史候选，不授最终冻结。本片仍未接入CI或取得Windows原生信用。

## Task1：测试专用运输与真实窗口

单writer只新建 `tests/windows_private_dacl_fixture.py`、`tests/test_windows_private_dacl_window.py`，不改生产、vendor、CI或文档。

- [x] 先完整读设计/相关源、真实sequential-thinking三步；写纯assertion RED/0ERROR的便携fixture/ABI/有限schema/生命周期合同，未Windows只授fake契约。
- [x] 实现限唯一owned临时目录的固定模板、实际identity/NTFS、SDDL/DACL once释放及CreateFile once关闭；独立全sharing观察器不伪注册外来HANDLE。
- [x] Windows native两方法parent/leaf，各preexisting/new四独立fixture三窗口；pin前reset、原pinnedHANDLE读取及身份核对、实际效果/blocked+前后正控，所有清理结束后finite schema才输出。仅软件实现，原生尚未跑。
- [x] 关联/20轮便携零skip/F/E、compile-j1/diff、自SPEC后不同QUALITY零C/I/M；冻结两文件实际摘要/counts。实际Windows未跑则明确待验。

### Task1软件冻结（不授原生）

writer修后独立SPEC→不同QUALITY均C0/I0/M0；有效RED共13组21assertion failure/0error，随后GREEN。生命周期首次写法2F/1E修后重新取RED，不计错误轮信用；暂停撤回的observer RED不重复计入。四便携class实际5/11/3/13共32方法，原生class2方法另待Windows。最终writer32PASS、20轮640PASS/0skip/F/E，关联9模块278run=268PASS/10既有可选skip/0F/E，compile-j1及diff检查通过。root已全文回读两最终文件（包含新增创建登记边界），独立32PASS、20轮640PASS/0skip/F/E，循环前后摘要一致。

fixture SHA256 `6b9f35626770aba6574422bce5152e75dc35cb934a889b16cea70e8e26ceb698`；test `da71f5e1757d828202142b09363f65c1e51b3cafc3e683161daaaeedca84c92c`。四变体最大32次Set/转换、36次SD reader，SD allocation/free总68；额外HANDLE30、pin≤128、token4，显式kernel32 CloseHandle≤162；Python exclusive创建与关闭4文件另列，不混入162。便携fake预算不是实际Windows计数。Task2另一单writer已开始；root真实sequential-thinking80–82复核选择器复用、四便携/nt-only原生与skip边界、原生分账及完整守护风险。生产/vendor/权限不变，本片未发布。

## Task2：必需CI与完整软件验收

Task1冻结后另一单writer只修改 `scripts/run_workspace_ci.py` 与 `tests/test_windows_startup_pin_ci.py`。

- [x] 便携class一次进入全平台startup/DEFAULT，native class只nt必需；actualloader counts，先RED方法/class/fixture/subTest skip及旧可选语义，后GREEN。
- [x] 关联与20轮、自SPEC后不同QUALITY；仅两文件冻结，不扩其它workflow/权限。
- [x] root完整回读四功能文件及上下游、全片独立SPEC后不同QUALITY、关联/20轮、完整preflight三道、docs/site/秘密/vendor/diff、七维真实范围报告。

Task2候选真实TDD：首次12项guard为137assertion F/0E，扩展定点另2F/0E；分批有重叠不可相加。独立SPEC用内存加载023旧脚本对最终13项回放取得138F/0E/0skip，不回退工作树。候选GREEN13，旧startup269/279 ID全部保留且unique，新posix301/nt313，DEFAULT Linux966/Windows958均actual loader，不算Windows执行。root独立guard13PASS、314项selector+guard×20轮6280PASS/0skip/F/E，四功能摘要前后一致；root关联先11模块354run/342PASS/12平台skip，再单独run_workspace_ci27PASS，两次调用分账，不伪装同一381套件。writer12模块381run/369PASS/12skip。Task2不同QUALITY尚在结尾，不授最终冻结或完整守护。

Task2最终SPEC→不同QUALITY均C0/I0/M0；不同QUALITY独立6280便携轮次及内存旧脚本RED138F/0E均复现。两接线摘要冻结：workspace `c8ae51e9bd22c196fba820883b12fb6ede642c71a8fc8aec23bc45b90c05a19f`；guard `5675d5b215d47bfebe775a831d4bfe7fe7286e162c7ec546df4bb873d720c200`。root再实核actual loader posix301/nt313、Linux966/Windows958皆unique，未授Windows执行。全片不同SPEC已启动，后续不同QUALITY；完整preflight76246当前前两道通过/全仓测试运行，四功能文件保持冻结。上段“QUALITY尚待”保留为历史候选窗口，不是当前状态。

全片独立SPEC后不同QUALITY均C0/I0/M0，各自行全文核四源及production pin/backend/reader/token/parser调用链、45定点PASS/0skip/F/E及同次12模块381run/369PASS/12平台native skip/0F/E，四摘要前后一致。root完整回读四源、6280便携轮次、354+27分账关联、compile-j1及docs三文件0疑似/site检查通过；site9个外部导航未fetch。完整preflight76246仍须最终exit0，不预报通过或发布。阶段结束独立研究15:49–15:51 UTC复取固定Codex/SRT/Apache2及Microsoft主源，确认预算分账和API成功不等于效果/安全，不复制源码/新增依赖权限。

2026-10-11 16:06 UTC，root新完整preflight76246三道全部通过/exit0；工具不打印全仓成功方法数，不估算。四功能摘要从守护前后相同，vendor固定21566a5无改动；只关闭本片软件门，待main发布和新SHA四Windows原生。上段“仍跑”为历史运行窗口。

【架构级自检报告】

- 语法/编译：compileall-j1、完整preflight通过。
- 依赖/调用链：四功能与真实pin/reader/token及CI接线完整，双独立全片审查通过。
- 逻辑/边界：三窗口、真实效果/身份及有限schema合同、6280便携轮次通过。
- 异常处理：取得/登记/创建中断、once回收、未知失败、KI/SE及隐私负控通过。
- 关联模块：354+27分账关联无F/E，12既定/新增native平台skip不授原生信用；文档同步。
- 兼容安全：旧ID/可选语义保留，生产/vendor/权限不改，三个授权false保持。
- 可运行性：便携软件及完整回归通过；Windows原生四格、默认兼容、加载/UAC/R2/R3仍待，不能称跨平台100%。

## Task3：发布与原生窗口

- [x] exact scoped add/commit/push main核remote，与user无关改动分离。
- [ ] 新SHA Windows x64/ARM64×Python3.11/3.12四格完整raw日志核native两方法/各两变体三窗口实际回执；正控/cleanup/finite schema实际验证，不以job success顶替。
- [ ] 根拒绝/网络Reviewer/DACL机制/installedconsumer分账；继续sibling/继承与加载合同，不自动policy放宽或授R2/R3。

### 57e69e4 原生失败与最小诊断接续

2026-10-11 16:08 UTC，八个范围内文件提交并推送 main `57e69e47948e88d6abeb2c5ff5630965b98f0233`，实际远端摘要一致、工作树干净。软件门不等于原生门。新 CI run `38154185334` 四个 Windows workspace job `114513634433 / 114513634475 / 114513634627 / 114513634596` 均实际958run、20既有可选skip、2F/1E；private native两个方法均失败、没有任何canonical窗口回执，因此不授12窗口或changed/blocked信用。独立观察者核四格完整raw，root另直接核x64/3.11完整raw。

guard ERROR已由真实栈定位：`patch.object` 未设置 `create=True`，Windows上 `skipUnless(True)` 不创建 `__unittest_skip__` 属性。两个private native失败被既有外层脱敏，内部根因尚未知，不猜测DACL被阻断，也不以放宽策略修复。接续仅修该guard平台假设，并先增加代码常量白名单的有限阶段诊断；不得输出异常正文、路径、SID、HANDLE或SD。新候选独立验证后再推main取新原生窗口；sibling下一片暂缓，先闭环当前失败。生产、vendor、访问/权限策略及三个授权false保持不变。

故障基线与结论上限：

| 项目 | 已核事实 / 未知边界 |
| --- | --- |
| identity | GitHub ephemeral runner，以实际job绑定x64/ARM及Python网格；物理设备序列未知，不主张设备级验证。 |
| time_window | root核x64/3.11原始终段为16:14:45 UTC；四格分别按job原始日志绑定，不拼接成同一次运行。 |
| repo_matrix | runtime/analysis均57e69e4，vendor21566a5；verification为后续未发布候选，不能借旧SHA原生信用。 |
| artifact_identity | workspace直接运行上述提交测试；无成功DACL wire，不主张随包或UAC绑定。 |
| evidence_sources | 四完整raw由独立observer核，root直接核114513634433原始栈；每格958/20skip/2F/1E。 |
| unresolved | `_observe`先preexisting，失败后new未必执行；prepare/API/效果/cleanup内部阶段未知，root负责有限诊断后新SHA复验。 |
| conclusion_ceiling | guard仅平台测试根因有原始栈支持；DACL仅observation_only，禁止推断四变体都执行、blocked、清理成功或安全通过。 |

| 声明 | 类型 / 来源 | 结论边界 / 状态 |
| --- | --- | --- |
| 57 guard缺skip属性导致ERROR | fact；四原始job栈，root逐份核对 | 已支持平台测试根因；不解释另外两个native FAIL。 |
| 私有DACL操作被阻断或安全 | unobserved；四格零窗口wire | 未确认，禁止授该信用。 |
| 已有句柄可能导致start_pin失败 | inference；只读调用链核对 | 未证实，仅候选诊断点；不改策略或常量。 |

同SHA签名安装分账：provenance run `38154185331` validate及四格 `114516270103`（x64/3.11）、`114516270036`（x64/3.12）、`114516270094`（ARM/3.11）、`114516270040`（ARM/3.12）均success；root逐份读取新原始sourceconsumer wire并用冻结validator、固定job网格和独立runner OS版本验证，四份均通过解析。每格helper/verifier各13 opened/13 confirmed closes（合计26），2 SD read/alloc/free；四格共104关闭、8 SD allocation/free。baseline仍rejected/close_confirmed=null，consumer为owner_untrusted，仅helper index0事件；逆序关闭确认、compatibility/launch/protected全false。它们不补私有DACL窗口、叶策略或UAC门。Pages run `38154185365`成功；主CI `38154185334`失败，独立observer实际46job=37success/6failure/3条件skip（四workspace及两旧Reviewer）。两全仓Python job分别2911run/83skip由observer读取，不借为Windows原生通过。

16:31 UTC有限诊断候选冻结：仅三个测试文件，无CI脚本/生产/vendor改动；单writer真实RED为guard缺属性1F/0E、最终五功能合同对内存57原fixture回放5F/0E（包含初始2F，不能相加）、新增包装资源窗口trace3F/0E、非法target诊断1F/0E；首次内存回放4F/1E因测试缺import断言，修后重新回放，不计错误轮。三处创建包装已撤回，保持直接取得与成功局部登记；KI/SE保持原对象，未知错误固定脱敏，真实stage仅精确私有类型与有限常量，native只附固定target/opener。成功wire及安全/API常量不变。

writer45PASS、20轮900PASS/0skip/F/E、381run/369PASS/12native平台skip；root独立45PASS、同次381run/369PASS/12skip、compile-j1、site通过（9外部导航未fetch），20轮与完整preflight71746仍运行，独立SPEC后不同QUALITY待结束。32便携/2native/13guard方法数保持不变。冻结SHA256：fixture `838a2503d60f905e3e18282940d8cc58a181e4c24283390f392016a47553db6a`；private test `75ced021de03796cfb1be6b28cf45c241e81ef0c272ac1a5b1ca57e906f21cc9`；guard `b5a9a7e76111f2b155711e4bb0fb444cc19463be9b44573262488b3901a7520b`。该候选未发布/未授Windows原生，不能将诊断实现当根因修复。

16:33 UTC，独立SPEC为C0/I1/M0，阻断上述候选：guard新无属性模拟采用嵌套patch和手动del，Windows原本无本地skip属性时外层退出再次del，实际内存模拟1run/1ERROR（不是有效TDD RED）。Linux45/381与root20轮900PASS仍只是该历史候选的便携结果，不能遮蔽I1；71746已启动但guard接续修订，不能作为最终冻结守护。writer仅修guard恢复边界，随后重新取断言RED、复审和新完整preflight；fixture/private test仍冻结，生产和安全门不变。

16:39 UTC最终候选：guard SHA256改为 `67cef255a0517661525c6a8c11d5a22d6a184d28ed9b274999655e7dde0f5943`，fixture/private test摘要不变。guard真实无属性完整入口1F/0E、删除至try之间trace1F/0E，分别修后GREEN；先进入try才首次修改，单层patch及finally原值/无属性恢复。独立SPEC复审C0/I0/M0后不同QUALITY亦C0/I0/M0，各自行3种初态正常恢复、6种KI/SE trace、45及381关联验证；QUALITY独立20轮900PASS。root另实核3态及KI/SE边界、重跑同次381run/369PASS/12平台skip和最终20轮900PASS/0skip/F/E，三摘要前后一致。root还实际复现旧nestedpatch错误，并逐份取另外三Windows raw确认四格958/20skip/2F1E及零DACL wire。不授最终完整守护或原生，71746仅旧候选运行窗口。

16:50 UTC，冻结最终三文件后新完整preflight10115三道全部通过/exit0，实际不打印方法总数，不估计。旧71746也exit0但跨越候选guard修订，仅保留历史，不借最终信用。三最终摘要不变，vendor21566a5干净，docs两文件0疑似、site/compile-j1/diff通过；待本片范围提交送新Windows原生窗口。同期只读Linux缺口研究独立记录在持续对照，未改生产评分/readiness；仓外模型凭据摘要未变，原401边界仍待有效凭据，未复制正文或重试API。

【架构级自检报告：诊断修复最终软件范围】

- 语法/编译：compileall-j1及冻结后新完整preflight三道通过。
- 依赖/调用链：pin/native/reader/token/parser和CI选择器核对，独立SPEC后不同QUALITY零遗留。
- 逻辑/边界：有限阶段、固定变体、skip缺属性与恢复矩阵、900轮及381关联通过。
- 异常处理：真实KI/SE身份/状态恢复、创建登记trace、隐私负控与一次回收保持；未知仍失败。
- 关联模块：旧测试ID/方法数与全仓回归保持，文档同步；12平台skip不授原生。
- 兼容安全：生产/vendor/API/ACL/成功wire/三个授权false未变，无新增依赖/权限。
- 可运行性：本机最终软件通过；Windows新SHA原生、DACL真实根因与R2/R3总验收仍待，不主张跨平台100%。

设计SPEC两轮已定位并修复全sharing观察器/owner绑定、精确wire与先行生命周期，以及pin内reset抢先失败问题；最终C0/I0/M0，后续不同独立QUALITY亦C0/I0/M0，冻结design SHA256 `8ee8d8c4900fb38fb57a07c209f121319f32799f3b493fdfbdeb59a53db834d4`。ROOT实际sequential-thinking77–79分解真实缺口、复用与风险；Task1单writer已开始真实TDD，未授软件/原生信用。研究14:59–15:01 UTC仅机制借鉴，无复制源、新依赖/权限，不以研究代实验。

实施前预算口径澄清：四格窗口Set/SDDL最多24，另初始parent/leaf配置8，总32/每变体8；GetSecurityInfo allocation及HANDLE关闭另计。该澄清SPEC后不同QUALITY均C0/I0/M0，新design SHA256 `ab8fc3b4701599f81970bf6ae76755c70acd02123d7349231e104a263eacf010`，旧design摘要仅历史。writer已10便携合同PASS，observer/窗口尚未实施；为root修前片e783 Windows测试平台假设、完整守护6118稳定，暂冻结两draft、只读预算研究。不是阶段完成/原生信用，root守护后恢复真实TDD。
