# LA-2b1：Linux 包内助手的有限 ELF 架构核验

状态：设计经独立SPEC→不同QUALITY各C0/I0/M0冻结，软件实现、独立CODE两审及root完整守护三道已通过；本记录提交前冻结，发布以main历史及CI新SHA为准。设计审查候选SHA256为`a7dbaa5f3e7a70fb132da69dabb3c160a8f3c39bb9720134063e1affffa6fd1a`。root已完成三问、实际sequential-thinking110–112，完整阅读native_helper、原七项helper测试、setup及wheel检查调用方。沿用户“推荐方式自主推进”采用下述A，无新权限、依赖或安装步骤。前片完整守护三道通过后已分别发布main fccb526/c153154，源码写入阶段互不混用守护。

## 1. 需求与选择

当前`bundled_linux_helper`只查可执行regular单link文件与邻接SHA-256；错机器ELF、脚本或文本只要摘要匹配也可能返回。setup只支持x86_64和arm64，包内解析应明确拒绝混架构。现有generic校验有合法文本测试及显式脚本调用，不应把所有generic调用一起收紧。

| 方案 | 收益 / 成本 | 结论 |
| --- | --- | --- |
| A：Linux专用有限ELF核验，包内resolver接入 | 最小兼容改动；补正确机器前置，不新增执行授权 | 采纳 |
| B：所有generic校验强制ELF | 会破坏显式脚本/旧测试及非Linux调用 | 不适配 |
| C：同FD摘要、prepare和真实exec绑定一次实现 | 需要PreparedCommand及资源/USER_NOTIF通道所有权联审 | 下一独立片，不由本片冒充 |

本片不保证ELF完整可加载、静态链接、发布者身份、原始内容不可变或核验后路径不变。generic摘要的既有race不会被静态头解析消除；当前ready/自动模式仍按原门阻断。

## 2. 职责与调用链

`src/icode/native_helper.py`添加Linux专用解析与验证，保留generic和Windows函数语义。只修改Linux包内resolver调用专用验证；新增`tests/test_linux_helper_elf.py`记录有限头、文件形态、摘要、当前宿主匹配和拒绝副作用。暂不改setup、wheel checker、isolation、selector、诊断schema、CLI/MCP或执行broker。

```mermaid
flowchart LR
    R[包内固定路径 resolver] --> H[真实宿主架构映射]
    H --> V[Linux专用文件与摘要核验]
    V --> E[有界读取64字节头并核机器]
    E --> P[返回候选Path 或 None]
    P --> G[既有准备及执行门 不新增授权]
```

根代理已完整读取技术设计模板和三规则文件；本Python内部函数采用其职责/接口/异常分层，不引入Java/Spring、HTTP/MQ、Entity、MySQL或存储表。没有工单状态机或产品权限变化。

## 3. 内部接口与有限合同

- `linux_elf_architecture(image: bytes) -> str | None`：不打开文件或执行。只接受exact bytes，至少64字节；只解析前64字节，返回`x86_64`、`arm64`或None。
- `linux_arch_from_machine(machine: str) -> str`：只接受exact str，lower后明确映射`x86_64`→x86_64，`aarch64`/`arm64`→arm64；其它固定ValueError，不接受模糊substring或x86/32位。既有Windows命名不改。
- `verify_linux_helper(binary: Path, manifest: Path, *, expected_arch: str) -> bool`：expected_arch只接受exact str的x86_64/arm64；先复用generic形态/权限/摘要门，后从binary有界读64字节并核机器；普通OSError/ValueError返回False，KI/SE原对象传播。没有subprocess、加载器、PATH、当前目录fallback或任务FD获取。
- `bundled_linux_helper()`：非Linux仍None；固定原包内文件名不变，读取真实`platform.machine()`映射当前架构；宿主读取/映射普通错误返回None，KI/SE原对象传播；仅专用验证True返回原Path。不暴露模型/项目可选expected_arch或helper来源。

ELF限定：magic为7f454c46；EI_CLASS=2、EI_DATA=1、EI_VERSION=1；小端e_type为ET_EXEC=2或ET_DYN=3，e_machine为62或183，e_version=1，e_ehsize=64。支持ET_DYN仅表示有限头可兼容PIE，不声称它是静态助手。未使用EI_OSABI、ABI version、padding、entry、program/section tables等字段，不将这些字段零值合成完整loader通过。魔数、长度和字段不符一律None，不调用外部file/readelf命令。

事实依据：[官方ELF Header](https://gabi.xinuos.com/elf/02-eheader.html)、[官方机器号表](https://gabi.xinuos.com/elf/a-emachine.html)。本轮读取官方机器表及完整Header检索内容，未运行上游loader；这只是有限静态格式依据。

## 4. 兼容与异常

`verify_native_helper`对文本/脚本、links/manifest和异常的现有行为不改；显式`LandlockSandbox(helper,manifest)`原路径不被本片强行ELF化。Linux包内resolver不再接受摘要匹配的非ELF/错机器，这是本片所需拒绝，不把它写成所有显式helper已经安全。

LA-1诊断通过真实resolver后错机器自然归helper_unavailable；不改schema/组合或评分。其现有collector tests用patch提供显式helper，此类软件替身不能声称新resolver真实核验通过。WindowsPE测试和包内resolver保持原语义。

普通错误无路径/原异常输出；无retry或fallback。专用文件read使用context manager，读取/解析失败及KI/SE关闭自有stream，不接收/关闭借用工作区FD。不改generic的已有资源所有权。

## 5. 验收

先测试后实现：新模块可导入骨架阶段缺函数仅是脚手架失败，不授有效RED；对旧Linuxresolver配置模拟包、正确manifest和可执行非ELF取得实际assertion RED，再实现最小专用门使其GREEN。

有限头正控分别覆盖两机器×ET_EXEC/ET_DYN；负控覆盖非bytes及subclass、0–63长度、magic、class32、big-endian、EI_VERSION、e_version、ET_REL/CORE、未知machine、e_ehsize。使用真实临时文件和SHA-256核专用验证，错架构即使摘要正确也False；摘要漂移、坏/缺manifest、软硬链接、目录、非执行文件拒绝。非法expected_arch、宿主未知/非str/错误读取和非Linux在打开或执行前拒绝。file read KI/SE保留原对象并关闭自有stream，普通读取错误False。

resolver正控模拟固定包内path及当前宿主，x86_64/arm64各验证返回原Path；错机器、文本、缺包内helper即None，PATH中同名候选不被查找。测试patch仅提供宿主/包位置或精确故障，不另写模拟resolver。原helper七项、LA-1二十三项、isolation相关回归、独立CODE SPEC→不同QUALITY、全preflight三道、compileall-j1、文档/site和main精确提交按原流程执行；平台skip不授通过。

安装包Linux x64/ARM64真实读取及后续同对象启动分别验收，不能用合成64字节头补信用。wheel checker暂不授ELF机器检查信用。当前没有完整LA-2、FD执行绑定、网络策略合流、CLI/MCP或R2/R3信用。

## 6. 并行研究取舍与自检

独立只读研究于2026-10-11 18:45 UTC刷新Codex `27065a91ccbf5ba8532844be3777fcf83b77820d`与OpenHands SDK `3934349da2db0433238621542173a00a8af7439c`；根许可Apache-2.0/MIT及具体源码见[持续对照](../../agent-landscape-live.md)。root另完整读取Codex bundled_bwrap/fd_mount/LICENSE；其同打开对象摘要后exec机制进入后续片，不照搬可选摘要、链接打开或主helper未证明的边界。OpenHands所查LocalWorkspace直接宿主Popen不是本片认证替代。没有代码复制或新许可依赖。

【架构级自检报告】（设计候选）

- 语法/文档：字段、真实符号、接口和官方头格式已核；独立设计SPEC→不同QUALITY各C0/I0/M0。
- 依赖/调用链：generic/Windows保留，只包内Linuxresolver接入新有限门。
- 逻辑/边界：静态头、摘要、宿主匹配与执行授权明确分开。
- 异常处理：固定失败、stream关闭、KI/SE传播合同明确，未实测。
- 关联模块：LA-1schema、selector、isolation和资源链不改。
- 兼容安全：显式旧helper入口不收紧；无权限/服务/依赖新增。
- 可运行性：设计阶段未编码，软件/安装包/执行绑定均不授通过。

实施状态补记：上述七维是设计冻结时记录。当前唯一源码writer已停止，source SHA256 `c5c5d88b8d3fb7c56cd0e574358bc125f3788cac0d0607c7c415ccefd336008c`；测试SHA256 `0ecaedb65cf875faa575847f03278f7912d946423a2d7810c21bf17fd4bc335d`。root全文回读，独立CODE SPEC→不同QUALITY各C0/I0/M0，三方各43项软件回归通过、零跳过；generic及全部Windows函数字节不变，compileall-j1通过。完整守护及main发布按实施计划另记；仍不授安装包、同FD执行或总体准入信用。
