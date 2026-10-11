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

- [ ] exact scoped add/commit/push main核remote，与user无关改动分离。
- [ ] 新SHA Windows x64/ARM64×Python3.11/3.12四格完整raw日志核native两方法/各两变体三窗口实际回执；正控/cleanup/finite schema实际验证，不以job success顶替。
- [ ] 根拒绝/网络Reviewer/DACL机制/installedconsumer分账；继续sibling/继承与加载合同，不自动policy放宽或授R2/R3。

设计SPEC两轮已定位并修复全sharing观察器/owner绑定、精确wire与先行生命周期，以及pin内reset抢先失败问题；最终C0/I0/M0，后续不同独立QUALITY亦C0/I0/M0，冻结design SHA256 `8ee8d8c4900fb38fb57a07c209f121319f32799f3b493fdfbdeb59a53db834d4`。ROOT实际sequential-thinking77–79分解真实缺口、复用与风险；Task1单writer已开始真实TDD，未授软件/原生信用。研究14:59–15:01 UTC仅机制借鉴，无复制源、新依赖/权限，不以研究代实验。

实施前预算口径澄清：四格窗口Set/SDDL最多24，另初始parent/leaf配置8，总32/每变体8；GetSecurityInfo allocation及HANDLE关闭另计。该澄清SPEC后不同QUALITY均C0/I0/M0，新design SHA256 `ab8fc3b4701599f81970bf6ae76755c70acd02123d7349231e104a263eacf010`，旧design摘要仅历史。writer已10便携合同PASS，observer/窗口尚未实施；为root修前片e783 Windows测试平台假设、完整守护6118稳定，暂冻结两draft、只读预算研究。不是阶段完成/原生信用，root守护后恢复真实TDD。
