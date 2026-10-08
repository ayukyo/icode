# R2 Windows 正式安装与命令运行器

> 本计划是下一产品片的实现顺序，不是已具备能力。先交付固定SKILL包内入口及其真实安装验收，再按WP0→WP1→WP2闭合；原生失败不改为应用层替代或自动模式通过。

## 真实缺口、已有实现及授权

用户已选择方案A：Python wheel内含匹配架构helper；第一次初始化有明确Windows UAC；专用低权限本地身份、restricted token、身份绑定WFP、任务ACL与Job。无需用户装Docker/Rust/Go/MSVC；不是把已安装不带helper的pure wheel假装正式Windows后端。没有新增SYSTEM服务、MSIX安装或SeAssignPrimaryToken/SeImpersonate等token特权授权。

当前 `windows_provenance.verify_bundled_windows_provenance` 已有固定身份及真实密码学正负原生矩阵，仍只返回 `launch_authorized=false`。`native/windows/icode_windows_bootstrap.c` 只有metadata，setup/spawn全部exit78。`windows_runner_pipe` 已有有界帧、logon SID ACL、原process handle及对端认证；`windows_runner_protocol` v1尚无完整policy/配额/可信身份。`windows_job` 可复用Job限制与清理，但不能把包含host supervisor的同Job算RL-0或认为数据原语已经接上产品。

调用链应为可信宿主配置→核验安装状态及受保护helper→精确启动对象→认证runner通道→本次policy的restricted payload/Job→实际输出、限制及清理回执→既有broker/工具/合同。API/安装失败在payload启动前拒绝；通道丢失等未知状态不能写成 `payload_started=false`。

## WP0：可信镜像晋升与事务

- 持有包内镜像、proof与父路径的no-reparse HANDLE，拒绝symlink/junction、非普通文件及不明确替换；保持不允许write/delete的共享边界，核对owner/DACL、架构、原字节与可信来源。验签回执只证明bytes，不自动授予执行。
- 从系统KnownFolder获得固定机器受保护根，不使用环境ProgramData、cwd/PATH或用户提供路径作为受保护根；文件和父路径必须拒绝普通用户写/重命名。Admin/SYSTEM拥有安装对象，payload只读执行，不能依赖mtime/长度。
- 初始化命令是固定操作与固定对象，不接收shell/模型argv。首次用户明确接受UAC；用户拒绝时可重试初始化，自动命令保持关闭。不代操作系统点击授权。
- 只在私有staging写本次核验原字节，目标再次核验后marker最后提交。journal记录本次真正创建的对象与原状态；碰撞拒绝，不接管同名陌生目录/账户/规则。失败回收本次拥有对象，不盲删旧安装。标记最后写不是完整事务恢复证明。
- root/task/kernel保护边界仍独立。禁止复制失败/读锁失败/ACL核验失败后回退pip用户路径、任意PATH镜像或裸运行。
- 提权后不能运行用户可写pip目录的未认证Go verifier，也不信任可一并修改的邻接sha。既有CI顺序支持Go→exactSHA→编译最终C→attest最终C；采纳由已attested C字节内绑定本架构Go摘要的构建设计。elevated C只把持锁原字节复制到私有protected stage，从目标HANDLE重新校验内嵌摘要/架构后以固定受保护路径调用。缺绑定摘要拒绝生产构建，损坏/缺件拒绝安装；当前C尚未实现该绑定或执行。绑定Go不能独立证明首个UAC C自身真实性，首次C仍依赖既有安装/发布TCB与精确核验→启动身份，UAC显示不是发布者认证。
- 现CMake `/MT`只代表静态CRT，不代表无DLL。采纳系统来源DLL与明确SYSTEM32动态加载约束，另验入口前PE imports、redirection/SxS及恶意邻接/cwd DLL canary；main中的SetDefaultDllDirectories不能为main之前加载补证。镜像和父路径HANDLE共享锁也不限制所有属性/ACL写入或目录新建子对象，不能单独当目录不可写证明；逐祖先no-reparse/file identity及owner/DACL必须独立核验。具体mitigation兼容性仍待原生实验，不先宣布已防劫持。

TDD及原生门：精确proof/digest/架构、文件与祖先junction、镜像/父路径替换、已存碰撞、部分写/异常/UAC拒绝/宿主退出、二次安装及本次对象回滚；同一实际对象核验→启动绑定。只允许固定metadata/拒绝正负控，WP0未关闭前不新增模型命令执行。

### WP0a 构建绑定与 WP0b 受保护晋升分片（2026-10-08，设计未实现）

2026-10-09 Asia/Shanghai开工前补充（基线已推送main`3d2f0d23d3c5c104102489c2510865dda8ba0ec2`，未实施WP0a）：独立只读研究固定0a后，根代理再次核对未变C/CMake与三个CI消费者。以下实施合同需新独立SPEC→不同QUALITY；旧静态设计批准不代替新增具体接口或TDD。

- 最小生产范围：`native/windows/icode_windows_bootstrap.c`、CMake、两workflow、`scripts/run_windows_wheel_ci.py`、构建专用新`windows_bootstrap_binding.py`及`MANIFEST.in`，配对bootstrap/构建/安装/选择合同测试。产品provenance API、runner协议、vendor、权限和自动模式不扩；新测试如进入DEFAULT仅选明确软件class，不包含Go SDK整体或平台skip冒充覆盖。
- 唯一新查询为`--verifier-binding-json`，argc须2。封闭8字段：helper=`icode-windows-bootstrap`、binding_schema_version严格int1、architecture本架构、verifier_sha256严格小写64hex，setup_complete/command_execution/isolation_ready/launch_authorized均严格false。原`--version-json`输出字节不变；其它入口/额外参数均78。metadata不是出版者认证或启动授权。
- 生产CMake默认构建bootstrap且必须显式传入真实匹配架构Go文件；生成器对同一受限原bytes（最多64MiB、普通单链接、非空、有效PE及machine）hash并生成build目录头，不读邻接sha作为可信输入。每次bootstrap build强制生成器成功并消费当前头，不靠configure/mtime；同尺寸/同mtime改Go必须重算。缺/错输入、生成失败即build失败并止签，不能复用旧头/旧EXE报告成功；重配必须重新绑定。可信builder状态不是并发敌对宿主隔离，运行时held HANDLE/祖先/DACL留WP0b。
- 两个probe-only消费者明确bootstrap OFF，分别只构建WFP或AppContainer+WFP原目标，不新增Go要求、不误称生产构建。unsigned bootstrap job同job编译真实架构Go作为CMake输入，仍仅原v1/refusal信用，不新增unsigned binding查询。synthetic packaging仍只传输层，不代替生产Go。
- signed安装顺序必须为gh独立核验安装C bytes/proof/固定身份→该已验证C新query→安装Go原bytes架构/hash匹配→运行Go离线验签及负控→原v1/refusal→导出wheel。gh失败零query/Go执行；绑定失败零Go执行/零wheel导出。新查询使用受限原始bytes、严格UTF-8/JSON、stdout≤512、stderr为空及固定timeout，不能沿普通_run的replace decode/无界捕获后宣称严格有界；优先复用已有受限子进程机制，不另造未验收生命周期。
- Windows C文本stdout正常可能以CRLF终止；新query明确只允许单个LF或CRLF终止符，保留实际原bytes，不用任意strip/replace吞额外行、空白或非法bytes。原v1现有text/universal-newline消费者不变。此处只约定输出兼容，不把CI核验后按路径查询当成WP0b的held-HANDLE同对象启动保证；可信私有builder窗口假设保持。
- host C逻辑测试须显式生成fixture头，仅逻辑信用；生产生成器进入sdist，生成头不入源码包，缺件/同步改Go+sha+RECORD/签后C漂移/重复与extra字段/bool数字别名/非法bytes/trailing输出等负控配对。保留现Go早于旧v1的顺序断言，新增binding早于Go执行的断言。
- 固定Codex9b738/SRT3f0bad的Apache2机制沿2026-10-08历史观察复用，本次未重新查HEAD；采纳原对象/认证纪律，不适配len/mtime或锁失败继续。新查询和hash不认证首UAC C、不解决protected promotion/DLL/DPAPI/Windows10支持或quota；必须实际x64/ARM×Python3.11/3.12签名安装矩阵后，仅记C→Go关系信用。

在R3合同接线独立开发期间，只读研究按aaaa448及主代理再次读取C/CMake/workflow/安装验收调用链，确认Go先构建、最终C后构建并获attestation的顺序已存在，但C没有内嵌Go摘要。下一Windows子片先做WP0a，不把一次大改的设计当生产执行：

1. 本次匹配架构的真实Go文件成为生产CMake必需输入，复用有界PE/架构检查、原字节SHA256；生成仅在build目录的绑定常量。缺输入、错架构/摘要或旧生成物复用拒绝，不接受邻接sha或默认零摘要。构建算法和metadata接口须独立TDD后冻结，不预报当前存在。
2. 保留现`--version-json`精确v1内容；新增独立固定参数的binding查询及封闭schema，声明本架构expected Go SHA和所有执行/初始化授权false。无任意path/shell/model argv；setup/spawn仍78。现v1 runner framing不升格正式spawn权限。
3. 计算Go原字节摘要→内嵌→编译最终C→attest最终C，签后不再改C。可信CI先独立gh核对安装C的实际bytes/proof/身份，再执行该明确构建并验签的C metadata，核对安装Go真实bytes与内嵌摘要；失败不导出wheel。不能执行任意发现的候选C来认证其真实性，也不能让产品locator因metadata而自动授权。
4. 两份同尺寸不同Go、同步改邻接sha/RECORD、缺件/错架构、签后C变化、新schema duplicate/extra/type alias/trailing output、重配生成物、原v1/拒绝入口均做正负控。Windows x64/ARM64及Python3.11/3.12实际安装签名矩阵只给C→Go bytes关系信用；synthetic PE/host编译只给逻辑/传输信用。

WP0b另做真实protected promotion/HANDLE/祖先/ACL/事务/DLL与同对象核验→启动，仍只固定操作，不提前接用户命令。首个UAC C真实性不由内嵌Go hash认证，既有安装/发布TCB、精确对象锁与启动绑定上限保持；不形成可改Go验C再由C担保Go的循环。原host用另一管理员凭据接受UAC时DPAPI身份、Windows10 22H2/Windows11、pre-main DLL/SxS、owned-only回滚全部需实际原生证明；不新增SYSTEM/MSIX/token特权或用户安装Go/MSVC。

## WP1：专用身份、凭据及网络边界

- 仅创建并记录本次拥有的低权限本地SID；固定账户名碰撞不能凭名字当旧安装。密码在内存生成，按明确host用户DPAPI及受保护窄ACL存储，不走argv/env/日志/工单或共享明文文件。
- WFP规则按实际身份精确绑定，IPv4/IPv6默认deny；只有已批准的代理路径可放行，代理允许目的地仍经宿主策略。host普通账户网络不受影响。持久provider/sublayer/filter只管理自有GUID/对象，恢复和卸载不清全局防火墙。
- 首先验证标准用户实际启动API：trusted runner由可信host保持原process handle和logon身份；restricted payload入Job及token readback在resume前完成。`CreateProcessAsUserW` 的restricted-caller豁免不能推定免除所有quota权限；1314/5须如实分类，不新增token特权或SYSTEM/service回退。
- 本阶段API正负控必须在x64/ARM64真实标准用户下闭合；签名runner或管理员正控不能代替。若已授权路线仍需要新增特权，应报告证据请求方向，继续其它独立开发，不擅自扩权限。

TDD及原生门：ownedSID/DPAPI错误用户、损坏状态/账户碰撞、WFP独立双栈canary与终态拒绝、代理目的地负控、host正控、规则真实readback、部分初始化回滚、卸载恢复。timeout/10035/no-canary/WFP无事件不等于DENY。

## WP2：每任务执行、配额与生命周期

- 完整封闭协议与C/Python对称升级，包含真实policy身份、workspace HANDLE绑定、process/memory/time/output额度、可信环境及request/attempt。旧v1不静默补宽权限。大小/字段/类型/重复JSON/correlation及EOF边界先拒绝。
- 双Job分责：host-owned且不继承的lifeline Job拥有runner并收束宿主死亡；inner payload Job只计根命令及后代，不计任务外监督。Windows线程不计process_limit，按已确认RL-0明示。禁止BREAKAWAY与仅轮询后kill冒充硬限额。
- suspend→精确token/restricting SID及DACL核对→Job限制readback及原hProcess入Job→resume；stdio使用明确HANDLE白名单。确认内核成功后才发布可信started，不以stdout或EOF补造执行事实。
- 同一专用账户SID不能单独提供并发任务文件隔离：每任务restricting SID与ACL交集、精确工作区/账本/原仓/用户路径及其它任务拒绝须真实证明。普通payload不得WMI等外部broker生成Job之外后代。
- 输出/取消/timeout/管道异常及host SIGKILL均核对实际ActiveProcesses=0、句柄/对象/任务ACL清理与残留工作区。每命令quota独立；成功、非0、短命令与并发正负控均不可缺。

产品门：接真实registry→broker→ToolContext→NativeChainExecutor，不只新模块/fixture；cap1拒fork/cap2根+后代、线程差异、内存、继承sandbox、受保护读写、双栈网络/代理/租约、并发、hostdeath、违规可信回执及独立证据导出。所有必需项具备前 `isolation_ready`、resource_limits、自动模式及R2/R3总门不开放。

## 调研采纳与许可（2026-10-08）

独立只读刷新Codex [`14c8b7771ab2b617a131f5d8e55e98d18e56ed09`](https://github.com/openai/codex/tree/14c8b7771ab2b617a131f5d8e55e98d18e56ed09) 与SRT [`3f0bad7345238f47736435e3f2b064399c1cad74`](https://github.com/anthropics/sandbox-runtime/tree/3f0bad7345238f47736435e3f2b064399c1cad74)，实际LICENSE均Apache2.0。采纳镜像/父路径锁、protected-root、PID/token认证及owned-object纪律，不直接复制源码或引入其runtime。原始代码及取舍见[持续对照](../../agent-landscape-live.md)。Microsoft [CreateProcessAsUser](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessasuserw)、[restricted token](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-createrestrictedtoken)与[nested Job](https://learn.microsoft.com/en-us/windows/win32/procthread/nested-jobs)用于API约束，文档不能替代实际标准用户行为。

同日WP0补充只读源码核对：[SRT锁](https://github.com/anthropics/sandbox-runtime/blob/3f0bad7345238f47736435e3f2b064399c1cad74/vendor/srt-win-src/src/self_protect.rs)失败warn-and-continue不适配ICODE fail-closed；[Codex copy](https://github.com/openai/codex/blob/14c8b7771ab2b617a131f5d8e55e98d18e56ed09/codex-rs/windows-sandbox-rs/src/helper_materialization/copy.rs)的len/mtime fresh判据及可删旧目的地不适配原字节/owned-only事务。主代理实际回读本仓CMake、36行metadata-only C及workflow Go先于C构建顺序；未执行Windows原生实验。[Microsoft DLL搜索](https://learn.microsoft.com/en-us/windows/win32/dlls/dynamic-link-library-search-order)、[SetDefaultDllDirectories](https://learn.microsoft.com/en-us/windows/win32/api/libloaderapi/nf-libloaderapi-setdefaultdlldirectories)、[CreateFile共享规则](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)和[CMake CRT属性](https://cmake.org/cmake/help/latest/prop_tgt/MSVC_RUNTIME_LIBRARY.html)为上述约束的一手依据。成本为构建绑定、受保护copy/hash、加载与事务双架构负控，不新增用户Go/MSVC安装或SYSTEM权限；WP1/WP2暂缓至WP0闭合，不以静态设计开readiness。

同日后续独立研究实际git ls-remote（官方API403后只读fallback）刷新Codex main为[`9b738582b13c2cdbeff54af0afd04c50c3e7ba09`](https://github.com/openai/codex/tree/9b738582b13c2cdbeff54af0afd04c50c3e7ba09)，package为0.0.0-dev；SRT仍固定3f0bad7/package0.0.79，两实际LICENSE均Apache2.0。新Codex[copy](https://github.com/openai/codex/blob/9b738582b13c2cdbeff54af0afd04c50c3e7ba09/codex-rs/windows-sandbox-rs/src/helper_materialization/copy.rs)仍len/mtime及删除旧destination；[runner client](https://github.com/openai/codex/blob/9b738582b13c2cdbeff54af0afd04c50c3e7ba09/codex-rs/windows-sandbox-rs/src/elevated/runner_client.rs#L449)原process HANDLE及认证两pipe后发送机制采纳，registered alias/MSIX分支不适配。SRT[cli](https://github.com/anthropics/sandbox-runtime/blob/3f0bad7345238f47736435e3f2b064399c1cad74/vendor/srt-win-src/src/cli.rs#L1428)锁失败继续仍不适配。上述只定点刷新，保留旧commit历史、不称全上游复核或原生已运行；WP0a明确采纳构建绑定、暂缓promotion至WP0b，独立源码/TDD/native验收不由研究代替。

## 共用交付门

每片真实RED→GREEN/20轮、旧消费者兼容、独立SPEC→不同QUALITY、七维自检、全量preflight、compile≤j6/治理/站点/竞品/diff后才main commit/push及精确SHA原生矩阵。WP0组件、签名、旧Reviewer诊断与完整产品门分别记录，不删除历史失败或把CI job绿等同skip/全R2通过。macOS清理豁免不豁免单任务quota，本计划也不授权其新增管理员初始化。

同日独立文档审查无阻断，下一片TDD明确补：普通host用户通过另一管理员凭据接受UAC时，凭据/DPAPI归属仍是原host，不误绑elevated管理员；批准的Windows10 22H2与Windows11基线不能由windows-latest双架构CI代替。此处只设计核对，没有执行提权或安装。

**Execution Mode:** serial implementation, independent read-only research/reviews
