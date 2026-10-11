# Windows 导入与全部资源静态检查设计

2026-10-11；基线main `532dae1`。这是已授权CI原始PE检查路线的后续设计，不新增权限、运行依赖或生产解析器。用户已要求自主继续及main阶段发布，覆盖设计技能默认的逐阶段等待和工作树选择；新的网络capability/Reviewer隔离路线仍各自等待确认，不能由本授权替代。

## 问题、复用与方案

已完整核现有 `windows_pe_reader.py`、`probe_windows_pe_capture.py` 及基础设计：PeImage只有头部/RVA；capture的dumpbin与mt #1样本不枚举全部资源，三个验证标志明确false。真实缺口是缺少目录消费，不是这些false字段写错。

沿已选原始bytes路线A：新增CI目录层，复用不可变PeImage的严格完整区间读取。路线B（工具文本与原始PE双重全解析）引入工具格式/本地化双合同，暂缓；第三方容错parser作为准入不适配，不复制pefile或新增包依赖。

源码研究对应 [Microsoft PE Format](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format) 的导入、延迟和资源结构；原始RVA与文件偏移不可混用，全部资源不能用mt单个ID代替。下述预算、bound/VA拒绝、名称和manifest语义是ICODE受限CI策略，不宣称通用PE规范只允许这些形态。

## 接口与闭合范围

新 `scripts/windows_pe_directories.py`，接口 `inspect_directories(image: bytes, *, expected_arch: str)`，只读、无I/O/日志/执行；构造PeImage，不更改原基础接口或轻量machine API。返回不可变记录：architecture、ordinary与delay导入模块/符号、全部resource叶的完整路径/长度/hash、全部RT_MANIFEST叶及其原bytes/hash/语义。repr不得含原bytes或XML正文。

独立 `PeDirectoryError(ValueError)` 仅固定reason；基础PeFormatError原样传播，不捕获并变成空目录。新reason为 `directory_pair_invalid`、`directory_not_declared`、`budget_exceeded`、`unterminated_table`、`invalid_import`、`unsupported_bound_import`、`unsupported_delay_mode`、`invalid_resource`、`resource_cycle_or_alias`、`invalid_manifest`。不得输出字段实际值/bytes/path，不吞KeyboardInterrupt/SystemExit。

成功只证明 `imports_delay_manifest` 范围在本受限策略下完整验证，不授whole PE、其它目录、DLL来源或可加载性。缺少所需目录元数据声明不能补成合法空；本产品固定C要求声明至少14目录项以涵盖ordinary/resource/delay，合法空由该项精确(0,0)证明，单边零拒绝。

## 有限预算与目录共用规则

输入8MiB沿基础层；所有被访问区间由read_rva完整检查。目录层每次全解析最多16MiB累计读取（包括重复读取，基础层有界头部读取另按其既有合同）、4096个导入符号、128个ordinary/delay模块合计、1024B每个ASCII字符串（含NUL，最长正文1023B）、4096个资源entry与叶合计（每访问一个entry扣1，若为叶再扣1）、4096B每个manifest、64KiB全部manifest原bytes。目录读取预算必须在read_rva/slice之前扣除，manifest字节预算在decode/XML/hash之前扣除；不因循环或重复内容重置。耗尽整体拒绝，不返回前缀。

dir address/size均非零时完整声明范围先核file backing；描述符必须在该范围内且有全零终止项。名称/thunk/payload分别按其RVA映射，可在不同section；不要求它们属于描述符目录范围或同一section。目录在终止项之后的剩余bytes不能被错当新的描述符，也不要求整块尾部全零（可有其它表数据）。

## ordinary 与delay

ordinary模块读取完整描述符到全零终止；DLL名须非空可打印ASCII basename，不接受分隔符、驱动器/路径、dot/dotdot或空名。名称导入读取hint及非空NUL终止符号；ordinal保留16bit号码，不当作名称RVA。PE32+ thunk按64bit读取并要求完整零终止；仅接受有效ordinal位组合或32bit名称RVA，不截断高位。

本CI接受未bound ordinary：timestamp必须0、bound目录(index11)必须合法空；OFT非零使用独立lookup表，OFT零可用未bound IAT解析名称。IAT必须有同长度且零终止的完整file-backed空间，并核未bound表的一致性。带bound状态拒绝为unsupported_bound_import，不把地址值猜成hint/name。

delay只接受RVA-based属性恰1；VA-based/未知属性明确unsupported_delay_mode。模块名、INT、IAT、module-handle均分别核完整区间，INT解析真实导入符号；不能把delay IAT的resolver地址按名称解析。bound delay IAT或timestamp非零拒绝；unload表如有必须核与INT一致的长度及零终止。未声明/截断/未终止不返回空模块。

重复DLL按精确原名保留不同模块顺序，不能去重隐藏重复descriptor；模块/符号统计包含重复项，以防预算绕过。全解析结果不提供动态依赖允许名单。

## 全部资源与manifest

按资源根相对偏移遍历Type→Name→Language三层全部分支，不仅RT_MANIFEST或ID1。表/header/UTF16名字/data-entry完整位于声明resource范围；payload的OffsetToData是另一个RVA，可在不同section。名字是长度前缀UTF16，严格decode、拒绝空/嵌入NUL；数字ID保留整数。named/id计数字段与各entry标记一致；同层重复key拒绝。

任何重复directory节点（含跨父共享）、回到祖先、错误层级、入口/叶类型不符、相对offset越界及保留字段非零均拒绝。三层与禁止别名是本CI子集，不称所有通用资源树必须如此。每个非零叶读取全部原payload并计算hash。非manifest零payload只接受OffsetToData=0或不超过已核SizeOfImage的32bit值（包括恰等SizeOfImage），保留该元数据与SHA256(empty)，不调用read_rva且不授任何file-backing；大于SizeOfImage为invalid_resource。RT_MANIFEST零payload拒绝。具名测试零RVA、image末端、末端加1及非映射gap的零payload；此规则是ICODE空区间子集，不冒充loader合法性。

RT_MANIFEST为数字type24，枚举其所有Name（数字/字符串）和Language叶；不把命名type猜成系统manifest。每叶严格UTF8/UTF8-BOM/UTF16-BOM解码后检查DTD/entity禁止，完整XML解析且无尾随垃圾。root必须为urn:schemas-microsoft-com:asm.v1的assembly且manifestVersion=1.0；直接trustInfo及其security/requestedPrivileges/requestedExecutionLevel链必须恰一条，全部为urn:schemas-microsoft-com:asm.v3。requestedExecutionLevel恰有level=asInvoker、uiAccess=false两个属性、无children，text只能缺失或空白。全XML任何namespace下局部名为requestedExecutionLevel的第二元素，即使值相同，也拒绝；security链错namespace/错误层级拒绝，不以子串匹配。其它well-formed非security结构（包括assemblyIdentity/dependency及编译器标准扩展）允许，但不为动态依赖或whole-manifest loader语义授信用。至少存在一个manifest；任意其它ID/语言叶不符则整体拒绝。manifest语义是固定bootstrap策略，不是PE格式有效性的定义。

## 实际消费与协议兼容

在 `probe_windows_pe_capture.capture` 已记录helper/dumpbin/mt摘要后，读取用于解析的helper原bytes为raw，立即强制SHA256(raw)==digests[0]，同一raw传给目录检查并绑定static_directory_check。末尾原三对象摘要重读保留，但仅证明端点一致，不证明整段窗口不曾A→B→A变化，也不是HANDLE/ACL或可信启动锁。增加A→B→A夹具：中间raw为B、端点均A，仍必须拒绝而无成功回执。继续保留两个工具样本及旧三个false：`parse_complete`、`runtime_load_verified`、`source_launch_verified`。

capture闭集schema升到2，增加 `static_directory_check`：固定scope=imports_delay_manifest、complete=true、绑定helper_sha256、ordinary/delay模块和符号数、resource/manifest计数、manifest原bytes摘要及全部level语义通过标志；不公开DLL/符号名、XML、资源路径或payload。旧schema1消费者明确处理，不隐式兼容混合字段。更新对应工作流/回执合同测试；不因本窄scope而解除生产三个false。

解析或预算失败停止该签名前检查，不生成成功capture；固定分类不泄漏payload。任意code错误不被“诊断只读”宽容接受。CLI输出与同SHA四格Windows实际消费才是成品静态证据；未接入capture的纯函数单测不能称阶段完成。

## 验证与实施顺序

独立SPEC及不同QUALITY先审设计。随后实施计划分依赖任务：目录层及实际bytes正负控 → capture schema/消费及旧合同回归 → 同SHA四格真实Windows静态检查。主代理先读后改，源码不与当前文档门禁运行并发改动；每任务TDD及独立复审，编译j1。

测试必须覆盖x64/ARM64、合法全空imports/delay与完整manifest、多ID/语言/命名资源、OFT0、ordinal、独立section、delay resolver值、零非manifest资源；以及目录单边零/未声明、截断、非零高位、非法ordinal、缺终止、边界预算、bound/VA、名字非法、资源循环/共享节点/重复key/错层/UTF16损坏、漏掉第二manifest、DTD/entity、manifest冲突及原bytes不变。没有read_rva/table/解析器mock，真实合成完整PE结构；调用外部工具可沿capture旧隔离边界，不把mock输出称实际PE。

全量回归、完整preflight、governance/site/landscape、diff及双审通过才精确main发布。四Windows格（x64/ARM64×Python3.11/3.12）必须实际新schema与新scope；否则安装/签名成功不授本静态阶段信用。总R2/R3、生产加载/首次UAC、网络和Reviewer权限仍各自未闭合。

## 当前状态

仅设计；尚无目录层源码、TDD或实际Windows新scope证据。独立SPEC首审C0/I1/M1：解析快照未直接绑定摘要、零payload偏移策略未定；已补同raw摘要比较、A→B→A负控及空区间策略，复审C0/I0/M0。不同QUALITY为C0/I0/M2、无阻断：字符串NUL/资源entry+leaf/先扣预算，以及manifest namespace/合法dependency/同值重复level需明确；现已具名纳入。可进入实施计划，不等于代码或Windows验收通过。

独立只读研究2026-10-11核 pefile HEAD [`84b1100c3faeb96a64f2fca141bdf17706d4d6c2`](https://github.com/erocarrera/pefile/commit/84b1100c3faeb96a64f2fca141bdf17706d4d6c2)，提交时间2026-10-10 12:55:35 UTC，[LICENSE仍MIT](https://github.com/erocarrera/pefile/blob/84b1100c3faeb96a64f2fca141bdf17706d4d6c2/LICENSE)。[ordinary](https://github.com/erocarrera/pefile/blob/84b1100c3faeb96a64f2fca141bdf17706d4d6c2/pefile.py#L5849)、[delay](https://github.com/erocarrera/pefile/blob/84b1100c3faeb96a64f2fca141bdf17706d4d6c2/pefile.py#L5647)、[resource](https://github.com/erocarrera/pefile/blob/84b1100c3faeb96a64f2fca141bdf17706d4d6c2/pefile.py#L4604)保留某些warning/break后返回部分结果；只借鉴遍历与预算机制，不能直接用该容错结果授完整信用。2026-10-09旧固定只作历史，不能伪装当前HEAD；没有源码复制/新依赖。
