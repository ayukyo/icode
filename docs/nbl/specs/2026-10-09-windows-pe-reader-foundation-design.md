# Windows 原始 PE 只读基础层设计（候选 A）

日期2026-10-09；基线main`118a2621cef92a5fcda510db295ea8c7658e5d4f`。范围只到头部及完整RVA区间映射，不授目录完整性、加载或生产准入。用户已授权连续开发、阶段通过后main提交推送；A/B取舍已异步呈现，本稿是A的最小基础设计，尚未实施，不把默认选项当用户已提交答案。独立设计SPEC→不同QUALITY及计划是实施前置。

## 三问、替代方案与依赖

真实缺口：已有PE采集只记录工具原样样本，三个验证标志仍false；没有严格raw-PE目录检查。全仓相关检索及已有源码核对显示，`windows_pe_architecture`只检查MZ/PE/COFF machine，不能复用为完整地址读取器。wheel、bootstrap binding、direct-volume、wheel runner、capture等消费者依赖其轻量合同，必须保留。

A为新增CI专用标准库字节读取层，分片补目录检查；B为whole dumpbin文本再与raw结构双解析，成本为两套格式/版本/编码。优先A，但本片不提前接入capture或workflow。复用已有不可变bytes与架构拼写、8MiB采集上限、DEFAULT选择接点；不复制pefile代码、不安装库。B暂缓；把warning/空结果当完整成功不适配。

只有基础层的软件合同通过后，后续才设计ordinary/delay、全部资源/manifest枚举及同SHA四格CI消费。本片没有模型、特权、UAC、上游Git管道或隔离配额改变。

## 文件与接口

拟新增`scripts/windows_pe_reader.py`和`tests/test_windows_pe_reader.py`；修改`scripts/run_workspace_ci.py`与`tests/test_run_workspace_ci.py`仅将新portable模块选择一次并配对校验。旧machine API、全部消费者、capture回执、签名/CI工作流及vendor不修改。reader不import生产执行器或原生API，没有CLI、I/O、日志或可执行入口。

`PeImage(image: bytes, *, expected_arch: str)`构造只读对象，输入必须精确bytes，expected_arch必须精确str且只接受x64/arm64；其它类型（含bytearray/memoryview/bytes或str子类）拒绝，不隐式复制或转换。保留原bytes引用，不存可变输入、文件路径或第三方parser实例。内部所有元数据为不可变标量/tuple，外部不能替换image/sections/目录字段；image的repr不包含正文。有效输入不改原bytes。

`architecture`只读字符串是已解析COFF machine与expected_arch精确匹配的结果。`data_directories`只读tuple保存可选头声明的`(address, size)`原始整数对，**仅结构读取，不验证目录内容或把每个address都当RVA**；index4安全目录是文件偏移，不能错误地对它做RVA校验。未声明的项不补成“已检查为空”，没有parse_complete属性/成功回执。

`rva_to_offset(rva: int, size: int) -> int`与`read_rva(rva: int, size: int) -> bytes`只处理严格正长度的完整区间。参数必须精确int（bool、float、负数和零size拒绝），rva在0..2**32-1，size≤8MiB，rva+size≤2**32且≤SizeOfImage。不能截短、拼多段、补零、取首个匹配、调整对齐或作RVA=offset的overlay回退。read_rva先完整映射再精确切片，长度必须等于size；无缓存或全树历史。

所有已定义的输入/格式/策略/映射拒绝抛`PeFormatError(ValueError)`，其`reason`仅为下列闭集之一，异常文本仅等于reason，不含输入bytes、路径、字段实际值或原异常repr：

- `invalid_input`：image/expected_arch类型或值错误。
- `image_limit`：image为空或大于8MiB。
- `truncated_headers`：DOS/PE/COFF/可选头/声明目录数组/section表所需区间不足。
- `invalid_signature`：MZ、PE或PE32+ magic不匹配。
- `architecture_mismatch`：machine不支持或不等于expected_arch。
- `unsupported_section_count`：section数不在1..96。
- `unsupported_directory_count`：声明目录数大于16。
- `invalid_header_range`：e_lfanew低于64或SizeOfHeaders/SizeOfImage不符合下述范围。
- `invalid_section_range`：section的raw或virtual完整区间越界。
- `overlapping_sections`：非空raw/virtual区间与headers或另一section重叠。
- `invalid_rva_range`：读取参数或整体RVA范围非法。
- `rva_not_file_backed`：范围位于间隙、零填充、raw padding或跨映射区。

不catch KeyboardInterrupt/SystemExit/MemoryError后返回对象，不将实现Bug转换为空目录；struct读取必须先显式检查所需区间，以免已列拒绝泄漏struct.error。

## 头部与范围合同

8MiB是ICODE CI采集策略，不是PE格式上限；1..96 sections沿Microsoft loader上限，但本片拒绝零section也是ICODE子集。目录数0..16是当前ICODE接受策略，PE规范本身不保证固定16。PE32+/x64/ARM64是本产品目标，不是通用解析器。没有完整loader合法性检查（对齐、flags、重定位、TLS等不在本片），不能将本构造成功称有效可加载PE。

依次检查64字节DOS头；e_lfanew≥64及其指向完整4字节signature+20字节COFF；声明可选头完整且至少112字节，magic=0x20b；NumberOfRvaAndSizes数组`112+8*count`全部在声明可选头内；随后`40*section_count`完整section表。只在边界检查之后读各字段；e_lfanew在文件内，无16MiB额外例外，因为输入已有8MiB上限。

SizeOfHeaders必须非零、覆盖完整section表、≤len(image)、≤SizeOfImage；SizeOfImage必须非零。headers可读RVA区间为`[0, SizeOfHeaders)`，映射同值文件offset。允许header-backed读取，但不授文件头外gap/overlay同值映射。头部与所有非空section virtual/raw区间不得重叠；相邻半开区间合法。

每section用原VirtualAddress、VirtualSize、SizeOfRawData、PointerToRawData，不调整或假设section名字。raw_size>0时raw_start及raw_start+raw_size必须在文件内；raw_size=0时没有raw区间且不使用raw_start。virtual_extent为VirtualSize非零时该值，否则SizeOfRawData；这是ICODE为VirtualSize=0采用的明确兼容策略。非空virtual区间末端≤SizeOfImage且≤2**32；两者都为零的section保留但不能提供映射。

完整virtual span用于拒绝歧义/重叠，不能只比较file-backed前缀。完整raw span用于拒绝物理重叠，不因raw padding不映射就忽略它。header重叠与section间重叠统一报overlapping_sections；边界数值错误先报invalid_section_range。section顺序不要求地址排序，比较有界96项可使用排序后的区间副本；不依赖输入顺序或section名称。

每非空section的file-backed可读范围仅为`[virtual_start, virtual_start + min(raw_size, virtual_extent))`，offset为raw_start+(rva-virtual_start)。VirtualSize>raw_size的尾部是零填充，不返回虚构零字节；raw_size>VirtualSize的尾部是raw padding，本片不赋RVA读取信用。跨headers/section或跨两个相邻section的单次请求即使各字节分别有backing，也报rva_not_file_backed：单次完整映射要求一个区域是ICODE策略，不宣称PE全格式禁止组合读取。**不同请求可以落在不同section**，后续name/thunk/resource payload不必与描述符同section。

输入存储≤8MiB原引用，元数据≤96section/16目录；一次read最多8MiB新bytes，映射搜索≤97区域。构造和单次读取有界；后续目录层需另外设总遍历/字符串/输出预算，不把本层单次有界当全解析预算。

## 正负控与调用链保护

TDD使用实际合成完整PE32+ bytes，不mock reader/边界/mapping；先缺接口及合法最小构造取得assertion RED，再实现GREEN。正控x64/ARM64、0/16目录、1/96sections、头部读取、section读取、边界恰好、未排序section、相邻不重叠、VirtualSize=0/raw_size=0/两者零、VirtualSize大于及小于raw_size、分别读取两不同section。

负控覆盖：精确输入类型及arch拼写；8MiB恰好/加1；每层起点合法但尾部截断；e_lfanew低于64/越文件；可选头magic/长度/声明目录越头/计数17；section0/97；headers没覆盖表/越文件/越image；section raw/virtual起点末端越界、32-bit端点、header与virtual/raw重叠、两个section raw/virtual全跨度重叠（包括zero-fill尾部）；读取bool/负/零长度/加法越界/超过单次预算；virtual gap/zero-fill/raw padding/overlay/跨区请求。所有负例精确异常类/闭reason，不只assertRaises(Exception)。校验输入bytes前后摘要、不可变元数据和无stdout/stderr。

接口具名向量还必须覆盖：空bytes→image_limit；MZ、PE两signature分别损坏→invalid_signature；不支持machine及支持machine与expected_arch不匹配→architecture_mismatch；SizeOfImage=0→invalid_header_range。声明目录0项时data_directories精确为`()`，声明项原始整数对逐项相同，不补未声明项；index4指向文件overlay证书区域（不是可映射RVA）仍构造成功并保留原值，read_rva请求该无backing区域另行拒绝。普通目录的未映射address或address/size单边为零也仅保留元信息，不能提前增加目录内容校验/回执。每个已列拒绝断言`type(exc) is PeFormatError`、精确reason及`str(exc)==exc.reason`，对象repr不含原image测试正文marker。

新增DEFAULT一次的配对选择断言及无skip。定点还回归旧native_helper、bootstrap binding、PE capture、workspace CI选择合同，证明旧最小machine fixture继续接受，reader更严格拒绝同fixture也不改变旧消费者。旧capture三false和原样样本保持；本片不调用reader替换其machine校验。

设计独立SPEC→不同QUALITY后再写明确计划；作者按TDD、自审、冻结后STOP。实施再新鲜SPEC→不同QUALITY，root回读源码、独立定点、20轮portable关键路径、DEFAULT、原三道完整preflight串行；compileall-j1/governance/site/landscape/文档两轮/diff通过才main精确发布。未经本片后续CI接入，原生job消费portable模块不是实际成品解析信用。全部七维据实报告，不授R2/R3整体通过。

## 研究选择、许可与当前状态

采用候选为完整区间唯一backing、有界不可变bytes、构建/启动/解析分层；暂缓导入/resource walker及whole工具文本；不适配pefile宽容partial、direct-offset/零填充回退或whole PE安全称谓。固定来源、当前上游变化及许可见[研究输入](2026-10-09-windows-pe-static-parse-research.md)。收益是后续目录层能复用一个严格地址合同；成本四个测试/选择文件、合成边界与后续实际PE验证。无上游代码复制/新依赖/权限/生产兼容变更。

root已完成需求分解→方案分析→风险评估三步结构化记录及草稿自检：不存在空预算或未定义enum；结构读取与目录内容分开，index4不误当RVA，raw/virtual/headers区间及VirtualSize零策略明确。首轮独立SPEC对fdf06705稿C0/I1/M0，缺接口/目录元信息验收向量；已按其最低建议具名补齐，不改算法或扩大范围。当前等待重新SPEC→不同QUALITY及A/B方案反馈；尚无实施、测试或原生通过。
