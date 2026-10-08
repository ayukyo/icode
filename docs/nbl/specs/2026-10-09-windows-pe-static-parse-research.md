# Windows PE 完整性检查：只读研究输入

日期2026-10-09；基线main `ccbe67bb65d5246a61fb3078b85c83fba5aa7c42`。独立研究只读，root另读下列固定源码和Microsoft原文。未改解析器、运行依赖、权限或签名工作流；本文件不是实施设计或验收通过。

## 已有样本与真实缺口

四格Windows来源run37840482713全部success，具体目标/tool SHA、原样bytes摘要及19项后续安装结果见[采集计划](../plans/2026-10-09-windows-pe-capture.md)。x64/ARM imports为3924/3771字节；manifest为406字节、UTF8 BOM、asInvoker/uiAccess=false。采集回执仍明确`parse_complete=false`、`runtime_load_verified=false`、`source_launch_verified=false`。

现有`dumpbin /nopdb /imports`报告与`mt ...;#1`只提供样本。#1存在不能证明#2/#3、命名ID、其它语言或所有资源不存在；mt输出可能重新序列化，不把其bytes相等当嵌入资源同一性证明。现有轻量PE machine API被wheel/tool/Go等调用，不直接升级其语义或破坏旧消费者。

## 固定开源与官方来源

- Codex Apache-2.0，固定`9b738582b13c2cdbeff54af0afd04c50c3e7ba09`：[build.rs](https://github.com/openai/codex/blob/9b738582b13c2cdbeff54af0afd04c50c3e7ba09/codex-rs/windows-sandbox-rs/build.rs)仅给setup binary绑定manifest；[setup.rs](https://github.com/openai/codex/blob/9b738582b13c2cdbeff54af0afd04c50c3e7ba09/codex-rs/windows-sandbox-rs/src/setup.rs#L969-L1056)区分非提权保留handles路径和提权ShellExecuteExW路径。采纳“构建元数据与实际启动分层”；这不是ICODE首次UAC对象绑定已解决的证据。
- pefile MIT，固定`4b3b1e2e568a88d4f1897d694d684f23d9e270c4`、源码版本2024.8.26：[目录分派](https://github.com/erocarrera/pefile/blob/4b3b1e2e568a88d4f1897d694d684f23d9e270c4/pefile.py#L3688)、[资源](https://github.com/erocarrera/pefile/blob/4b3b1e2e568a88d4f1897d694d684f23d9e270c4/pefile.py#L4609)、[delay imports](https://github.com/erocarrera/pefile/blob/4b3b1e2e568a88d4f1897d694d684f23d9e270c4/pefile.py#L5675)、[ordinary imports](https://github.com/erocarrera/pefile/blob/4b3b1e2e568a88d4f1897d694d684f23d9e270c4/pefile.py#L5872)。有结构分层/计数/深度机制，但某些坏结构只warning并返回None、break或继续；实例化成功或没有目录属性不能作为完整且有效的拒绝式检查。借鉴机制，不复制源码、不安装新依赖。
- root另读[Microsoft PE Format](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format)的RVA、ordinary/delay目录、资源Type/Name/Language及相对偏移；[manifest资源ID](https://learn.microsoft.com/en-us/windows/win32/sbscs/using-side-by-side-assemblies-as-a-resource)说明1/2/3有不同作用。规范结构是解析依据，严格接受子集/预算则必须写明为ICODE策略，不宣称PE格式仅有该子集。

## 采纳候选与取舍

候选A：独立CI专用、标准库受限raw-PE解析，保留dumpbin/mt为诊断。校验PE32+、x64/ARM64、完整header/section/目录范围及唯一RVA映射，拒绝重叠/截断/无file backing；遍历ordinary与RVA-based delay描述符、名称和thunks，明确终止及预算；按Type/Name/Language遍历全部资源目录并枚举全部manifest叶，拒绝重复/循环/超深/越界。不存在只能来自合法空目录，不来自解析失败。之后单独核严格manifest语义。成本为受限格式的合成正负控制与四格实际PE重验；收益是避免把人读工具格式当完整结构合同。

候选B：先严格解析whole dumpbin报告、再raw PE互证。完整banner、块、函数、summary、EOF及未知行拒绝能避免只regex抽DLL，但仍不能补齐mt漏枚举资源；需维护两套格式，版本/编码/本地化成本较高。独立研究偏向分两步，root未据此决定实施；当前优先比较A的最小性。

暂缓：生产解析器、直接依赖允许策略、动态/传递DLL来源、首次UAC对象绑定、TLS/load-config等其它目录。KERNEL32样本和LoadLibraryExW/GetProcAddress函数存在均不能推断全部依赖来源安全。不泛放行api-/ext-名字或假定API-set合约就是System32中同名文件。

不适配：宽容warning视成功、#1代替所有资源、只抽DLL名、泛称whole PE完整或取消现有三个false。后续若实现窄范围，应另定义`imports_delay_manifest` scope，不能给全PE/pre-main/实际加载信用。

## 后续验收前置

先有范围/预算/明确错误分类的独立设计、SPEC→不同QUALITY，再TDD、完整软件守卫和同SHA四格真实PE。原始结构读取须只读、有界、固定受验证目标，并保持采集前后目标bytes不变；不用本机mock代替原生或标准用户/Win10验证。当前研究结论为`unverified`，不关闭R2/R3任何执行门。

## 2026-10-09 当前上游复核（保留旧固定观察）

本轮基线main118a262，独立只读研究复核公开refs及相关函数，root另读下列构建/启动、ordinary/delay、资源及读取函数。Codex新固定`2c3156adf4c9454f0e01c839669255c6a32b5416`：[build.rs](https://github.com/openai/codex/blob/2c3156adf4c9454f0e01c839669255c6a32b5416/codex-rs/windows-sandbox-rs/build.rs)、[setup.rs](https://github.com/openai/codex/blob/2c3156adf4c9454f0e01c839669255c6a32b5416/codex-rs/windows-sandbox-rs/src/setup.rs#L940)相关分层未变。pefile新固定`cc9f5501ba93938e505858eaa3230608b6fbc34f`，源码版本仍2024.8.26：[ordinary](https://github.com/erocarrera/pefile/blob/cc9f5501ba93938e505858eaa3230608b6fbc34f/pefile.py#L5849)、[delay](https://github.com/erocarrera/pefile/blob/cc9f5501ba93938e505858eaa3230608b6fbc34f/pefile.py#L5647)、[resource](https://github.com/erocarrera/pefile/blob/cc9f5501ba93938e505858eaa3230608b6fbc34f/pefile.py#L4604)、[读取](https://github.com/erocarrera/pefile/blob/cc9f5501ba93938e505858eaa3230608b6fbc34f/pefile.py#L6341)。独立逐函数比较报告变化主要为格式、异常收窄、NameIsString及ordinal标记，宽容partial、截短/回退和未遇NUL仍返回片段的语义没有消失。两个新固定LICENSE分别[Apache2](https://github.com/openai/codex/blob/2c3156adf4c9454f0e01c839669255c6a32b5416/LICENSE)/[MIT](https://github.com/erocarrera/pefile/blob/cc9f5501ba93938e505858eaa3230608b6fbc34f/LICENSE)，独立比较未变；无复制或新依赖。

**采纳候选补充：**完整区间唯一file-backed映射，描述符与name/thunk各自映射；ImportDir Size不必包住后两者。resource目录/名字/data-entry位置用root相对偏移，data-entry的OffsetToData另作RVA；跨section不能无依据称格式非法。普通未绑定IAT与ILT可相等，delay IAT则不能强套hint/name解释。[Microsoft导入/资源格式](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format)为结构依据。该页[delay Attributes专节](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format#attributes)明确bit0为RvaBased，而前表仍写Must be zero，设计应记录此原文不一致并依据专节，不机械沿表格。

**暂缓：**whole-parser、工具文本双解析、manifest语义与生产准入。**不适配：**overlay RVA=offset回退、截短/零填充冒充原bytes、预算耗尽返回已解析部分、#1替全部资源、目录检查授加载信用。若采用A，先独立头部/RVA基础，再导入/资源遍历和四格CI消费；现有machine API/消费者不改，三false保留。具体接受子集（例如目录数、VirtualSize零、raw padding、bound/VA-delay）必须明确标ICODE策略及兼容成本。本轮不刷新完整20名单，不以研究更新通过R2/R3。
