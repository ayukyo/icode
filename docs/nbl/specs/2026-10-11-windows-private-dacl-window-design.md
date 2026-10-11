# WP0b：私有临时对象的直接 DACL 修改窗口

2026-10-11。前片固定 installed consumer 观测软件已冻结，完整回归及四格发布/原生仍分别验收。本文是下一片设计，不是实现或安全通过。

## 三问与阶段选择

真实缺口是持有 READ-only sharing 的文件/目录 HANDLE 是否阻止直接 WRITE_DAC，特别是已授访问的先行句柄。现有 pin、backend、security reader、真实主 token 身份和 Windows 必需 CI 选择可复用；调用链限测试/CI，不改生产 policy、固定 installed 入口、root ACL、服务、MSIX、权限或首次 UAC。

独立研究提出三组：新增 sibling、直接 DACL、继承传播。先实现直接 DACL 一组，祖先/叶、先行/新开访问分开；另两组下一片，避免 sibling ChangeTime 或继承污染当前窗口。此片只证明同宿主 actor 的 OS 机制，不证明不可信 principal、默认 pip 安装兼容、整窗稳定或启动授权。

## 最小接口与 fixture

新增测试专用模块 `tests/windows_private_dacl_fixture.py`，以及 `tests/test_windows_private_dacl_window.py` 的便携 transport 契约类和 Windows-only 原生类。没有产品 API、外部 path/SID/SDDL 参数或新的 CLI；只有 fixture 内部创建的唯一临时目录、一个父目录、一个最多4 KiB 的非私密叶文件可修改。临时目录外仅复用生产 pin 的只读祖先持有。

fixture 用真实 primary token SID，固定 SDDL 模板：保留宿主、SYSTEM、Administrators full-control；两种固定 Everyone marker 分别 READ_ATTRIBUTES(0x80) 与 WRITE_ATTRIBUTES(0x100)。父与叶均显式 protected、无继承 flags，避免本片偶然传播；这不是实际系统 ACL 或最小授权的模拟。不存在 NULL/absent DACL，owner/group/SACL 不写，任何 token privilege 不启用。

SDDL 经真实 ConvertStringSecurityDescriptorToSecurityDescriptorW，验证有效、长度有界、DACL present/nonNULL；GetSecurityDescriptorDacl 返回指针仅在原 allocation 生命周期使用；SetSecurityInfo 使用 SE_FILE_OBJECT / DACL_SECURITY_INFORMATION / PROTECTED_DACL_SECURITY_INFORMATION。SD allocation 独立于 GetSecurityInfo 的 allocation，一次 LocalFree 必须返回 NULL 确认；失败或中断不重试旧地址。实际读取与 parser 复用现有 reader，不输出 raw 或 SDDL。

额外文件 HANDLE 用 CreateFileW，仅请求 READ_CONTROL|WRITE_DAC，share READ|WRITE|DELETE；目录使用 BACKUP_SEMANTICS，均 OPEN_REPARSE_POINT。不要加入 GENERIC_WRITE/DELETE，避免内容 sharing 冲突冒充 DACL 锁。所有额外 HANDLE 一次 CloseHandle 非零才确认，失去确认后不重试。BOOL/LONG 为 int32、DWORD uint32、HANDLE/PVOID 指针宽度，SetSecurityInfo 的 DWORD 返回码不作 BOOL。

通过真实 HANDLE 的 GetVolumeInformationByHandleW 确认 NTFS；其它文件系统/共享冲突/fixture 失败在 Windows 为明确失败，不 skip 或扩大 sharing。实际文件身份从生产 backend.query 的 volume/FileId/type 核对，路径只定位自有对象，不当身份凭据。

观测 HANDLE与WRITE_DAC HANDLE分开。fixture内部以CreateFileW另开只读观察 HANDLE：READ_DATA/LIST_DIRECTORY|READ_ATTRIBUTES|READ_CONTROL|SYNCHRONIZE，share READ|WRITE|DELETE；parent/leaf均保持到三窗口结束。测试专用观察器用真实GetFileInformationByHandleEx及现有 `_INFO_CLASSES` ABI/StartupFileMetadata/_metadata 校验读取metadata，WindowsStartupSecurityReader读取SD，叶用真实SetFilePointerEx/ReadFile有界读取bytes；不把外来HANDLE伪注册至backend._active，不调用backend.query/read绕所有权，也不使用READ-only sharing作未pin正控。观察器仅接受自己持有的两固定内部对象，不能从外部注入HANDLE。

开始时同一只读观察HANDLE保存volume/FileId/type及叶bytes。pinned阶段由真实pin_startup_file(leaf,max_bytes=4096)取得整链；parent为其倒数第二HANDLE、leaf为最后HANDLE，要求metadata.directory位置正确且各volume/FileId/type等于观察器记录，然后仅借用该owner/backend的已有HANDLE query/query_security/read，ownership不转移。unpin/released由全sharing观察器读同一已持有对象，均须身份稳定；不能单凭路径读bytes或基线owner.content充当实时读取。

生命周期冻结：先创建/配置fixture→只读观察器取得parent/leaf→preexisting仅此时取得一次WRITE_DAC HANDLE→unpin reset/操作/回读（new的WRITE_DAC HANDLE当窗口结束即一次确认关闭）→真实reset及观察器回读基线→取得真实pin owner→pinned仅确认基线/一次被测操作/回读（new同样先关闭该窗口WRITE_DAC HANDLE）→owner全链逆序关闭且close_confirmed=true→released reset/操作/回读→new HANDLE确认关闭、preexisting唯一HANDLE确认关闭→只读观察器leaf/parent逆序确认关闭→删除唯一临时目录。pinned窗口不执行reset或额外写句柄，避免new-open被阻断时在被测操作之前先失败。先行WRITE_DAC跨三窗口保持；owner release不声称先行句柄已释放。任何中途失败仍收尾全部已取得对象，不进入后续窗口补信用。

## 四变体、三窗口与真实证据

两个目标 parent/leaf × 两种 opener preexisting/new，共四个独立 fixture。每个 fixture 依次 unpinned → pinned → released，同一目标保留身份；未pin及released在窗口操作前reset，pinned基线则在取得pin owner之前reset并回读，取得pin后仅用原HANDLE确认。回读真实 DACL/protected/marker确认设置，不依据 API success 自证。

preexisting 变体在 pin 前取得 WRITE_DAC HANDLE并保持到 release；new 变体各窗口新开一次 HANDLE，pin 窗口在 owner 存活时打开。先行 open 与当前 set 分开记账。正常未 pin/released 必须真实 open/set 成功且目标 marker 从0x80变0x100，否则缺正控、整格失败。pin 时不预设一定 blocked：实际 open 失败只接受精确 WinError5/32/33为有限拒绝（5不推断DACL根因），set 非零同样分开记录；其它码、未知状态失败。

pin 时若 open/set 成功，必须同原 pinned HANDLE回读真实 raw、protected、marker变化，并确认目标 FileId/type仍同一对象和叶 bytes未变。该结果明确为 `mutation_observed`，不是安全通过；未改变而 API返回成功属于效果未知、失败。pin时被拒绝必须仍能读同 pinned对象，marker保持基线，并有前后正控才能分类为 `mutation_blocked`。set拒绝也仅接受精确5/32/33，其它非零一律FAIL；成功 mutation 不授角色政策修改。

所有 pin窗口采样都先用既有 backend.query/query_security/read，不先调用会失败自关闭的 pin.revalidate；本片不调用 revalidate、不消费 source/protected pure policy，所以 raw SD变化与 metadata变化分别观察。metadata 中 ChangeTime可能改变，记录布尔不强行要求metadata完全相等；FileId/type/叶 bytes必须稳定。released正控只能在 owner.close_confirmed 为 true、额外相关 HANDLE回收安排明确后执行，不能用进程退出代替。

每格保证 fixture 生命周期互不污染；重置同样是真实 SetSecurityInfo/回读操作，不能忽略失败。所有清理在局部 owned临时目录内；优先关闭全部已取得 HANDLE/allocation，收集错误、保留主体 KI/SE，仅固定诊断；临时清理不成功使测试失败，禁止打印私密目录或静默忽略。宿主 full-control持续保留以允许收尾，禁止 broad recursive target。

## 输出与预算

不新增单独 JSON CLI/父侧采集器，复用必需 unittest 真实断言；每个完整原生变体仅在其所有清理结束后打印规范单行有限回执，失败仅固定安全错误且抑制原生值/私密 traceback。回执top exact keys为scope=`private_dacl_window_observation`、schema_version=1、target(parent/leaf)、opener(preexisting/new)、acquisition、windows、cleanup_confirmed=true、consumer_ready=false、compatibility_accepted=false、launch_authorized=false。preexisting的acquisition为exact object {phase:before_windows,result:0}，windows不能虚报重新open；new的acquisition为null。不得带 path/SID/SD/SDDL/HANDLE/地址或原异常，整个回执最多8 KiB。

windows为恰三项按unpinned/pinned/released顺序；每项exact keys为window、open_result、set_result、effect、sd_changed、metadata_changed、identity_stable、bytes_stable、protected。open_result：new为实际0/5/32/33，preexisting为null（仅top acquisition是一次open证据）；set_result为实际0/5/32/33，只有new open拒绝时为null未调用。effect仅changed/blocked；sd_changed/metadata_changed为exact bool，identity_stable/bytes_stable/protected均true。整数拒绝bool，文字exact str固定枚举，额外/缺失key拒绝。unpinned/released必须new open=0或preexisting null且set=0/effect=changed/sd_changed=true。pinned成功同组合；pinned拒绝只能new open=5/32/33、set=null，或new open=0/preexisting null、set=5/32/33，两者effect=blocked/sd_changed=false；不得set成功却blocked或缺效果。metadata_changed只观测不推断DACL原因。每变体的正控、清理及exact-schema validator均通过后才输出。

每方法四格中的两个同target变体，单格最多32 pin节点、叶4 KiB、DACL模板SD最多128 KiB（现reader上限）；只有固定三窗口及设置/回读，禁止无限重试。四格总事件12，窗口重置/被测设置最多24；另有每fixture初始parent/leaf配置2次，共8次，完整四格Set/SDDL转换及其LocalFree最多32次（每变体8次），不隐去setup。具体读取及HANDLE关闭预算和实际loader计数由实现调用图核算并冻结，不借研究中的估算授通过。全仓编译-j1，不新增网络、依赖、工作流权限或OS沙箱。

## 验收与接线

便携 TDD先覆盖 ABI/BOOL-vs-DWORD、固定模板和安全目标、absent/NULL DACL、非NTFS、success-without-effect、身份漂移、unknown-code、LocalFree/CloseHandle不确认、取得后中断及主体异常优先、有限输出、预算。fake仅授 transport软件，不算原生机制。

Windows native两方法分别 target parent/leaf，各真实执行preexisting/new变体三窗口，方法及fixture/subTest skip在nt必需；非Windows不选native，不把可选平台skip升级成通过。便携 class全平台必需一次；startup selector/guard counts以实际loader同步，旧ID及可选语义不变。新SHA x64/ARM64×Python3.11/3.12必须完整原始日志逐格核，失败继续阻断，不能用无pin或Linux fake顶替。

设计SPEC后不同QUALITY零C/I/M、单writer TDD、实现复核、20轮、关联、完整preflight三道、文档/site与七维自检通过后按既有授权 main提交推送；四格实际结果另记，不授系统祖先兼容/加载/UAC/R2/R3整体验收。下一片才处理sibling与继承，不能由本片结论自动修改policy。

## 研究取舍

独立只读2026-10-11 14:59–15:01 UTC，复用固定Codex `8c0f7011674145da7e10627769fb221c74fbf7a0` / SRT `5507fb0e639c00f845554336ece62e27af5b1bb7`（Apache-2.0），未刷HEAD/全部20项。root另核Microsoft官方原文。采纳先行授权、同对象真实效果与窗口分账；暂缓sibling/继承、TrustedInstaller、祖先policy和加载/UAC；不适配服务身份、mock根、read-sharing当SD冻结、同host当不可信principal。无源码复制、新依赖或许可影响，成本为测试专用ctypes及四格原生，收益仅为取得下一步操作角色设计的证据。

来源：[Codex祖先/目标分门](https://github.com/openai/codex/blob/8c0f7011674145da7e10627769fb221c74fbf7a0/codex-rs/windows-sandbox-service/src/ipc/home.rs#L80-L169)、[文件安全/访问](https://learn.microsoft.com/en-us/windows/win32/fileio/file-security-and-access-rights)、[SetSecurityInfo及传播限制](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-setsecurityinfo)、[CreateFileW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)、[SDDL转换](https://learn.microsoft.com/en-us/windows/win32/api/sddl/nf-sddl-convertstringsecuritydescriptortosecuritydescriptorw)、[GetSecurityDescriptorDacl](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-getsecuritydescriptordacl)、[GetVolumeInformationByHandleW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getvolumeinformationbyhandlew)。

设计SPEC首轮C0/I2/M0：补全全sharing独立只读观察器与三窗口HANDLE生命周期，冻结先行一次acquisition和new逐窗open、未调用set的null、精确拒绝码及exact schema合法组合。修复待复核，不授实施/原生信用。
