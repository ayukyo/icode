# macOS M0a1 进程实际组列表接口修正设计

- 日期：2026-10-14；状态：DESIGN 候选，待 root 全文阅读、fresh SPEC → 不同 QUALITY；本文不是实施 PLAN，也不授软件或原生通过信用。
- 工作区：WSL `/home/orbbec/projects/icode`，main；起草 fence `2c593046e5a9aa4d0c36e04ae7b6bbb26c6625a5`；vendor `21566a589cbe98bd35372a04bbb6ca1c51d8eed2`。
- driver SHA-256：`1fe2b712636ed31d51e9192783e977fd1e35657fcc434bf5960a7030e4fcfd43`。已有用户修改保留；本次只新建本文，没有 TEST/SOURCE/CI/Git/系统写操作。
- 根设计：[任务专用身份与硬配额](2026-10-13-macos-task-identity-quota-design.md)；现行 [M0a1 PLAN](../plans/2026-10-13-macos-task-identity-quota-m0.md)、[失败诊断 PLAN](../plans/2026-10-14-macos-m0a1-harness-diagnostics.md)、[gate 观察 PLAN](../plans/2026-10-14-macos-m0a1-gate-observation.md) 的协议和安全边界继续有效。

## 1. 三问、结构化推演与证据边界

真实问题已确认：M0 夹具刻意使用没有目录账户的碰撞检查数字 UID；当前 driver 首行定义 `_DARWIN_C_SOURCE`，实际交付 Mach-O 导入了目录扩展版 getgroups，读取对象与原设计要求的进程凭据不一致。已有实现可复用：严格 `credentials(uid)`、四处组查询、CMake 共用 `m0_target`、固定 root 身份租约与现有诊断，不另建身份服务。调用链已确认：root reserve → trampoline 降权与 credentials → CONFIGURED → sandbox-exec 同 PID → gate credentials → SANDBOXED → root 注册/RELEASE → payload credentials 与组采样。

root 已实际完成 sequential-thinking 三步，记录 `fe4453`；作者不冒称另调工具。需求分解：读取真实凭据且维持“仅一个任务 GID”断言；方案分析：用独立 POSIX 翻译单元隔离 SDK 特性宏，并让真实原生正负控调用同一严格 predicate；风险评估：宏泄漏、只改 predicate 遗漏 wire 采样、复制验证逻辑、自证式测试、目录账户 workaround 及将基础设施 ERROR 错算 quota RED，均设明确拒绝门。

独立线上观察员读取原 artifact 后由 root 转交的候选证据为 run `38549105737`：Intel job `115802400557` / artifact `11884984876`，ARM job `115802400524` / artifact `11885278722`。本文作者未重复下载原 artifact。两格 native exit=2、controller ERROR、cleanup=unknown，均非正式 RED。七 case 第一 slot 完整收到 FAILED=3/error=1，uid/euid/gid/egid 等于各自 expected 60000…60006；groups 为 UINT32_MAX 失败哨兵、group unknown；第二 slot 未收到，worker exit94。它证明所收 wire 的采样形态，不证明 credentials 两次调用各自的 errno 或唯一失败 syscall；send_gate 还可能改写 phase/error。

实际 baseline Mach-O：ARM 72448 bytes，SHA-256 `3c382f2ee55ff30f1c6392e8f44a8df58e8dbad75840a5a1de884c24fb93da92`；Intel 47216 bytes，`f6a2db29bb728f350c1156c721a0c38d80020c583a53e66627c98925f9f19c90`。线上观察员纯内存解析 LC_SYMTAB，与 metadata 摘要匹配，唯一 getgroups 未定义导入为 `_getgroups$DARWIN_EXTSN`（n_type=1）。这是二进制接口证据；不代替下一候选的真实运行。

## 2. 主源核对与路线选择

观察日期 2026-10-14，采用 root 的只读并行研究，作者另打开 Apple 固定提交主源核对。公开源码版本不冒称 runner 的逐字 SDK/libSystem/kernel 版本，实际 SDK 展开和运行另验。

| 主源与版本 | 与本设计相关的机制 | 决策与影响 |
| --- | --- | --- |
| [Apple Libc unistd.h](https://github.com/apple-oss-distributions/Libc/blob/4e34d0559e3a1b081afeb8604d9e204a1f31321d/include/unistd.h#L449-L453)，Libc-1752.120.2，peeled commit `4e34d0559e3a1b081afeb8604d9e204a1f31321d` | Darwin 特性宏参与 getgroups 扩展选择 | 采纳：TU 级 POSIX 宏隔离；须实测两个实际 SDK 的展开及最终符号 |
| [同版 sys/getgroups.c](https://github.com/apple-oss-distributions/Libc/blob/4e34d0559e3a1b081afeb8604d9e204a1f31321d/sys/getgroups.c#L38-L54)；root 另核 Libc-1725.0.11 / `55b54c0a0c37b3b24393b42b90a4c561d6c606b1` 同条件 | 扩展函数查询 passwd/目录组；没有 UID 账户时返回失败 | 不适配：用此目录结果验证降权后的实际组；不创建账户掩盖接口错选 |
| [XNU kern_prot.c](https://github.com/apple-oss-distributions/xnu/blob/ac9718fb1af618d5ce8678d0dc6e8a58f252216f/bsd/kern/kern_prot.c#L399-L451)，xnu-12377.121.6 / `ac9718fb1af618d5ce8678d0dc6e8a58f252216f` | 普通 getgroups 从凭据组向量读取；setgroups 涉及目录成员查询状态，空组并非应使用的本片语义 | 采纳：保留 setgroups(1,task_gid) 顺序及运行读回；不外推身份逃逸/全部 OS 通过 |

许可：所读 Apple 文件含 APSL-2.0、Berkeley 等文件声明，只借公开 API 机制与隔离思路；不复制 Apple 实现，不新增第三方包或许可义务假设。暂缓任何 quota、persona、长期 launcher 与目录账户调整。既有竞品研究用于诊断/协议分账的结论继续有效，本片接口选择以直接相关 Apple 主源为准，不声称刷新全部观察名单。

| 候选 | 取舍 | 理由与成本 |
| --- | --- | --- |
| A：独立 POSIX TU＋最小私有头 | 采纳 | driver 保留 Darwin API；新增一个 TU/头与同一 predicate；能直接编译真实 helper、检查最终绑定并做原生反例 |
| B：在 driver 中局部 undef 宏、重 include unistd.h | 不采纳 | header guard 与先前声明/SDK alias 已生效；依赖 include 顺序，难证明所有消费者一致 |
| C：raw syscall、私有 __getgroups 或 asm 指定符号 | 不适配 | 引入编号/私有 ABI/符号拼写耦合；本问题已有公共 POSIX API，无需增加平台风险 |

## 3. 推荐接口与最小职责

新增私有 `native/mac/icode_m0a1_process_groups.h` / `.c`。设计固定两个内部函数：`int m0_process_getgroups(int capacity, gid_t groups[])` 与 `int m0_process_credentials(uid_t uid)`；只服务受审 M0 夹具，不安装、不导出为产品 API。头仅声明并引入必要公共类型，不定义特性宏、不放实现或测试开关。

`.c` 在任何 header 前定义 `_POSIX_C_SOURCE 200809L`，在 include 前后均拒绝 `_DARWIN_C_SOURCE`、`_DARWIN_UNLIMITED_GETGROUPS` 污染；若外部已定义不同 `_POSIX_C_SOURCE` 值，同样明确编译失败，不静默改写。宏检查必须在 Linux 软件测试可验证，平台 SDK 的其他宏状态仍由 native 展开证据核定。CMake 不把 `_DARWIN_C_SOURCE` 设为此 TU 的全局定义。

`m0_process_getgroups` 是公共 getgroups 的薄封装：直接返回真实返回值，保留 syscall/libc 留下的 errno，不查询名字、不归一化失败、不缓存组、不重试、不改进程凭据。capacity=0/NULL 和 capacity=1 的既有行为保持；该函数不是“恰一组”判定器。

`m0_process_credentials` 由现 driver 七行 predicate 机械移动而成，只有 getgroups 调用替换为上述封装。保留 getuid/geteuid/getgid/getegid 顺序、短路顺序、count==1、read==1、group==uid 及失败统一 EPERM、成功0。GID 与 UID 同数值是当前夹具合同，不自由扩展为通用身份框架；saved credentials 仍由 root 独立 proc_pidinfo 核，不从此 predicate 推导。

仅增加薄 wrapper、把 predicate 留在 driver 虽更少移动行数，但独立 native 负控会被迫复制 predicate 或 include 整个 driver；选择机械抽取共用函数能验证真实调用者采用的拒绝条件。不得抽象为可注入凭据提供器或修改原判断以便利测试。Linux 测试替身仅用于可控软件错误语义和短路验收，不授原生组事实。

| 文件 / 调用者 | 后续责任与必须覆盖的点 |
| --- | --- |
| 新 `.c` / `.h` | POSIX 绑定与同一严格 predicate；真实代码可单独链接到 native TEST |
| `native/mac/tests/icode_m0a1_driver.c` | 保留首行 Darwin 宏供其它 Mac API；trampoline、gate、payload 三个 credentials 调用统一私有函数；原 credentials 中两次查询、send_gate 一次、payload 一次共四个源码消费点全部迁移；禁止残留直接 getgroups |
| `native/mac/CMakeLists.txt` | 共用 `m0_target` 加入同一 TU，baseline/source 必须一致；新增独立 native TEST target 不借 driver main；维持 native 架构/C11/警告门 |
| `scripts/run_macos_m0_ci.py` | 必要时将新增 TU/头纳入 source_hashes；新测试证据单独记录，原正式分类逻辑不改 |
| 新针对性软件 TEST / 原生 TEST | PLAN 冻结实际文件路径及完整资产；调用真实 TU 与真实 predicate，不复制条件，不 include 整个 driver |

gate/payload ABI 仍为72/96字节；groups 失败哨兵、unknown 展示和 group 有效性规则不变。原七 case、setgroups→setgid→setuid、phase/exit、valid_gate、release、NOTE_EXEC、receipt_loss、正式 TEST/assertion 与分类 oracle 均不变。不得创建 `icode_m0a1_limit.c`。

## 4. 真实验收门：一次覆盖软件、绑定与运行

后续完整 PLAN 必须先经 root 全文、fresh SPEC → 不同 QUALITY，再由独立 TEST 作者冻结 TEST、取得有效 RED，交不同 SOURCE 作者。以下是验收合同，不是本次执行记录。Linux 检查只在 WSL 跑必要针对性测试；全量/跨平台/native 优先 GitHub CI，main-only，不新建 worktree，不使用模型 KEY。

| 门 | 必需证据 | 不接受的替代 |
| --- | --- | --- |
| Linux 软件 TDD | 真实新 TU 的正常编译/执行；count/read 成功与真实调用返回值/errno保留；四 UID/GID及组数/值不符、count/read错误与短路顺序；编译宏污染负控（两种 Darwin 宏及不同 POSIX 值）；可控旧目录接口“无账户失败”的错误语义反例 | 仅函数缺失造成链接失败、伪 native wire、复制生产 predicate、只做文本包含断言；旧接口 Linux 替身不称真实 Darwin 运行 |
| 双架构实际 SDK 选择 | 每格记录 compiler、SDK路径/版本、实际编译参数、头展开；helper object及最终 Mach-O/nm 的普通 `_getgroups` 未定义绑定，绝无 `_getgroups$DARWIN_EXTSN`；baseline 与未来 source 共用 TU | 公开头文件版本当实际 SDK、仅源码宏/符号存在当运行通过 |
| 原生单组正控 | 新鲜、无目录 UID/GID，碰撞检查后实际 setgroups(1)→setgid→setuid；真实 count=1/read=1/[task_gid]、四 UID/GID一致、共用严格 predicate=0；同 PID exec 后重复核验实际继承 | case 常量填 observed 值、只核 syscall 成功、建立账户再查目录、跳过 exec |
| 原生额外组负控 | 新鲜无目录 UID；冻结 task_gid=uid、extra_gid!=task_gid，两者均为各自碰撞检查/独占的专用非零 GID；实际 setgroups(2) 后降权；调用同一生产 predicate 前独立核 getuid/geteuid/getgid/getegid 全等其入参 UID，count=2、以capacity=2完整读回并核集合恰为 {task_gid,extra_gid}；仅此前置全部满足且该 predicate 返回 EPERM 才授额外组拒绝信用 | UID/GID先行短路的EPERM、只传capacity=1取得EINVAL、使用host/root组0、模拟count2、测试另写predicate |
| 失败封闭与有界性 | 负控没有 release/payload；父observer核真实子PID/start identity/退出，单独TEST账本、超时/输出界、身份退役/保留状态；任何清理观察不足=unknown | 增加原七case或改变其含义、根据case名字生成“已拒绝”、宣称全树无残留 |
| 原M0a1正式RED | 两个平台原七case完整进入原formal oracle，只有指定 `test_cap1_quota_semantic` 的 `M0A1_QUOTA_REJECTION` 因真实baseline fork成功而FAIL；其余必要项通过、无ERROR/SKIP | helper GREEN、负控成功、编译成功或controller基础设施ERROR算quota RED |

原生 TEST 可为独立受控 root executable，只运行固定验证目标；不得增加 daemon/账户/服务/system component。复用既有 finite fixture 的安全机制与原语，PLAN 必须冻结具体可运行复用边界；不为避免复制而把整个 driver 或无限制 root 通用接口暴露给测试。额外 GID 必须也有有限持久租约、目录/进程碰撞核验、同job不复用与耗尽拒绝；不借扩大范围解决容量。

正负控独立使用新身份，root observer 不迁入任务 UID，不新增同UID helper；exec 用原地替换，不能多算一根。双组负控先固定 task_gid=uid、extra_gid!=task_gid，实际 supplementary 集合为 {task_gid,extra_gid}；降权后、调用同一生产 predicate 前，独立四项 UID/GID 全等入参 UID 与完整 count/read=2 集合观察必须全部成立，以排除身份项先行短路。任何前置失败均为负控无效，不能由随后 EPERM 授组数门拒绝信用。严格 predicate 仍保持原 capacity=1 逻辑与短路，不为补诊断改变其正常调用顺序。失败重试不得重新迁移同 UID，未知身份/残留继续隔离保留。

## 5. 有界失败诊断与恢复

若后续 PLAN 加最小失败点诊断，只记录已实际尝试的 setgroups/setgid/setuid、count/read 与身份检查点；每个调用先存返回值并立即存失败 errno，成功才记相应真实输出，未尝试或失败的输出标 unknown。predicate 仍返回原 EPERM；不能把 ambient errno 称原始失败原因。保持原短路：不为补一行日志而执行本应跳过的组读取。

诊断只走受控 stderr/独立 TEST 账本，不回填 gate/payload wire，不参与正式 success/release/classification。需冻结固定整数点位、每行与全job上限、SIGPIPE错误出口和errno恢复，并用现有 emitter/GateObservation 的实际 helper 测试模式覆盖健康出口及真实坏管道。不能把诊断缺失当未知字段为0，不能借追加诊断放宽现有64KiB截断拒绝门。

任何宏污染、SDK异常展开、符号绑定不符、原生正控失败、负控未拒绝、exec继承未知或输出超界都停止该候选验收，保留原日志/二进制/摘要与待隔离状态；不降组要求、不加目录账户、不换rawsyscall、不修改正式oracle。修复限于重新审查候选；不清理原证据或通过取消/反复重跑隐藏失败。

只有接口修正软件门、双native正负控与原七case正式RED在同候选精确证据上满足后，才允许另派不同作者实施已受审 quota SOURCE。该门不授 M0a1 GREEN、完整M0a2/M0b、M1安装、产品ready、R2/R3或至少90%信用；后续阶段依赖保持。

## 6. 文档自审与交接

本文只描述当前已确认接口缺陷与推荐最小机制；没有实施资产占位代码，没有运行 TEST、编译、native、CI或系统安装。独立 TEST/SOURCE 完整 PLAN 仍需另写并审查，不能直接按此 DESIGN 改代码。文档最终完整摘要由交接记录承载，避免自哈希循环。

修订历史：前一候选 `7bf68dec7e3434a87070cde372f4682315c9e6c58b0a8b1048305d63554fa441` 的 fresh SPEC 为 C0/I1/M0，未批准：双组负控尚未排除四项 UID/GID 先行短路；本修订仅补齐 §4 前置与信用门，仍待 fresh SPEC → 不同 QUALITY，不回写旧审查为通过。

【架构级自检报告】

- 语法/编译：本文为 Markdown，已检查结构、链接目标与新增文本；没有 C/SDK 编译信用，实际宏和符号门待验。
- 依赖/调用链：已读现 driver/CMake/controller/formal及现 helper 测试；列出三次 credentials 调用与四处 getgroups 源码消费点，baseline/source共用构建责任明确。
- 逻辑/边界：原七行predicate机械抽取、短路和EPERM不变；§4 双组负控冻结 task_gid=uid/独立extra_gid，四项UID/GID及完整两项集合前置全部成立才凭同一predicate的EPERM授组数拒绝信用；count2独立观察不改变predicate行为，单组正控与exec继承仍分别待验。
- 异常处理：真实返回值/立即errno/unknown、有界诊断、SDK污染拒绝、超时与租约未知隔离门完整列明；未虚报覆盖已运行。
- 关联模块：本次只新增本文；后续头/TU/driver/CMake/摘要/独立测试责任成对列出，正式wire/oracle/CI分类冻结。
- 兼容安全：不新增权限/账号/daemon/配额放宽；root ownership、有限lease、身份不重用与macOS清理例外保持。
- 可运行性：推荐设计可进入完整PLAN及fresh双审；没有软件GREEN或原生通过结论，quota SOURCE仍禁止提前创建。
