# macOS M0a2：继承、并发准入与启动故障验证设计

- 日期：2026-10-14；状态：DESIGN 待 fresh SPEC → 不同 QUALITY；仅本文新增，未实施 TEST/SOURCE/CI，未取得 M0a2 原生信用。
- 基线源码候选 `db47b1299bfa2016adfc88cd7d23c51da919afa3`；root 后续确认 main `8273cba0fbd82ede73bb9da7f0ba7d2845266b1f` 仅追加 handoff/live，native/controller/CI 未变；vendor 固定 `21566a589cbe98bd35372a04bbb6ca1c51d8eed2`。权威工作区 `/home/orbbec/projects/icode`。
- 绑定原 [124 行 DESIGN](2026-10-13-macos-task-identity-quota-design.md)，SHA-256 `774e33f4c2485da553f6b41572ef9641c4b30dea307a8e466c2bbdca7b2e5b23`；原 [1664 行 M0 PLAN](../plans/2026-10-13-macos-task-identity-quota-m0.md)，SHA-256 `37e4852cb9c25dfa2154ec8356d5416859125271f14b27d8d45f46bc44168ee7`，特别是 §2.3/§3/§4。本文不改其原要求。
- root 实际 sequential-thinking `17c5f5` 三步：cap1 GREEN 只属必要分片；M0a2 保留全部原向量；预算与身份/收尾/启动事实独立核验。本文记录作者分析，不冒称作者另有 MCP 调用。
- root 已独立核 db47 的 run `38566753418`、两 Mac job `115861273271` / `115861273402`：旧 baseline 唯一 quota assertion RED、SOURCE protocol5/native5 GREEN、W0/W1 与 owned-root 原件匹配。该事实由 root 提供，不是本文作者重新运行；全部55 job 终态为50 success、2 Reviewer failure、3 skipped，不能称全绿或完整阶段通过。

## 1. 三问、范围和唯一推荐

真实问题：cap1 已验证不等于 cap2、后代继承、原子竞争、身份域独立和完整启动故障已验证。已有实现：固定 root observer、受保护 native copy、普通公共 `getgroups` TU/共享 predicate、持久不复用数字身份租约、独立 audit/delivery、同 PID Seatbelt→gate→payload 已存在，优先复用。调用链影响：本片仍不接 `run_command → _controlled_dispatch → ToolContext → execution_broker`，不改 `policy_contract_ready=False`；产品接线属于 M2。

唯一推荐：新增独立、固定、有界 M0a2 TEST 驱动与正式 observer，沿当前安全原语做最小机械复用；新版本审计与旧 M0a1 协议并存。先冻结完整 PLAN 资产与独立 TEST，取得可运行无 quota 基线的真实语义 RED，再由不同 SOURCE 作者扩展私有 quota 原语，最后同一新候选 SHA 双原生验收全部前提和新片。本文不是该 PLAN，不提供可直接实施的代码资产，也不启动执行技能。

当前 `native/mac/icode_m0a1_limit.c` 刻意只接受 cap1；cap2 的 `EINVAL` 是“未具备/基础设施拒绝”，不是 quota RED。后续推荐仅将该私有原语扩至本片实际需要的 cap2/cap4，保留原 cap1，仍 exact cur/max 读回、disabled 不调用 OS；其余 cap 不因最大预算8而自动开放。该 SOURCE 改动必须在新 TEST 的真实语义 RED 之后，不能在设计或 TEST 阶段提前放开。

| 替代 | 决策与代价 |
| --- | --- |
| 把所有向量塞回旧 driver/旧72与96字节结构 | 不采纳：将已验 oracle、phase、classification 与 W1 修复绑进大改，回归面过大 |
| 新增另一套 quota SOURCE 或整份复制旧 driver | 暂缓：重复安全逻辑容易漂移；只有完整 PLAN 证明最小机械复用不可行才重新设计，不擅自复制 |
| 加大 N、同 UID helper、轮询后 kill、删减 race/control | 不适配：改变合同或把事后回收误作硬准入 |
| VM / ES / 新 root 服务 | 不适配本片：原路线尚可被有限验证，不能为通过测试引入新系统权限或产品架构 |

## 2. 复用边界、对象与可信顺序

旧 driver、baseline、正式7 case/5条 native TEST、72/96 wire、phase、release、三态算法、classification、正常 profile 模板及 W1 原生双组/同 PID exec TEST 保留；不得用原 PLAN 旧 hunk 覆盖当前 W0/W1/diagnostics。新 TEST 使用新的固定 target、记录版本/字段白名单，不向旧 wire 填更多字段。固定 mode enum 只选择审过的 case/shard，无任意路径、argv、程序或通用 root 入口，无安装、daemon、账户创建。

直接链接现 `icode_m0a1_process_groups.c`，不复制 credential predicate，不 include 整 driver。租约复用现 `icode_m0a1_identity_lease.inc` 的同一 `lease_root`、`owner_text`、依赖与隔离状态；若需要共享 ancestry/hash/copy/FD 等 helper，只准独立 PLAN 列完整机械抽取前后资产、全部变量/头依赖及 exact-inverse 对照，旧调用原语和错误语义不变。不得为了复用增加通用 root/path 参数。W1 的 supplementary collision 与 unknown 立即拒绝机制须保留，新身份分配也覆盖 real/effective/saved UID/GID 和 supplementary GID 碰撞，不把未知当空。

每 case 先冻结 cap、身份、attempt、固定角色路径和 digest；root fork 后在第一个 A 屏障读取真实 PID/start identity，再让可信 child 配置 quota、单组→GID→UID、共享 predicate 与 root 独立 saved IDs，之后原地执行系统 Seatbelt 和固定 gate。健康 profile 的生成模板逐字保留；每 fixture 路径不同导致 profile 实例 bytes/hash 不同，必须各记真实值，不能要求不同路径的 hash 相等。新子/孙与原根都核实际身份、继承限值及 canary；需要调用复杂查询的 fork child 先 `execve` 固定受保护 probe，再查询，不在多线程 fork 后调用 unsafe 库。

parent 在 ready 后建立新 kqueue、取得注册 receipt，再 RELEASE；无旧 exec 累积。控制 FD 在 payload exec 时关闭，数据/普通 stdout 与 root delivery 分离。根 payload 计1；observer 与非特权 collector 均在任务 UID 外。额外同 UID coordinator 不存在，barrier 使用预建 pipe，不通过增 N 补偿。

新驱动持有最多8个 owned process slot，每个槽记录 PID/start identity、父子关系、首 byte、release、exit/reap 与归属可信度。这是固定实验表，不是通用进程树 supervisor。正常由直接父逐个 reap，root 只 wait 自己的直接 child；无法确认后代终结只能 quarantine/保留，不声明整树零残留，也不按 UID/进程名/宽路径 kill 或递归删除。

## 3. 必选向量、正控与严格 oracle

下表除注明外每行2个独立实际实例：SOURCE quota 与相同非 root 身份类型/相同 profile/同向量的创建正控。关闭任务 quota 仅不设置任务 NPROC，保留 inherited safe host limit，预检它足够本序列；不设置无限额，不以 root 代普通任务正控。每次 fork 立刻保存 rc/errno；成功 child 第一条可观察操作写专属 byte，随后阻塞；随后意外子被 kill 也不能抹掉超额创建事实。`posix_spawn` 读取函数返回的错误码，不读 ambient errno；失败时 PID 输出未定义，不把初始化值未改变当 oracle。

| ID / cap | 实际序列与必须结果 | 独立正控 / 收尾 |
| --- | --- | --- |
| V1 fork-exec /1 | 根 fork=-1/EAGAIN，无 child 首 byte/exec；父不把 exec 失败当 fork 拒绝 | quota off 同固定 child exec 成功、身份/profile/进入证据齐；直接父 wait |
| V2 posix-spawn /1 | 固定绝对 probe、无特权属性，返回 EAGAIN 且没有创建 child | quota off rc0、有效 PID、实际进入及 wait0；file actions/attr 初始化和销毁逐项核 |
| V3 root-child-third /2 | root+首 child 保持 pipe 屏障存活，root 再 fork=-1/EAGAIN，无第三成员首 byte | quota off 第三成员成功并阻塞，最大3个任务进程；逐个放行/reap |
| V4 reap-refork /2 | 首 child 已退出且 waitpid 确证 reap，再 fork 成功；二 child 串行，不靠 sleep 猜 reap | 独立新 UID 无 profile 对照执行同序列，仍保留 quota2，排除 profile 阻断；两边都核0退出 |
| V5 grandchild /2 | root 与 child 保持存活，child fork=-1/EAGAIN；独立 root 记录父子身份与继承2/2 | quota off 孙真实成功，child 负责 reap 孙，root 再 reap child |
| V6 pthread /1 | 先创建3个barrier worker并全部join，再创建第4个worker并join；累计4次pthread_create、峰值main+3=4总线程、进程计数仍1；全部join后fork=-1/EAGAIN | quota off 同分波代码4次创建/join，随后fork成功；记录总创建数/线程峰值/两波顺序，禁止仍多线程时fork后用unsafe库 |
| V7 zombie /2 | root 保持存活，child exit 后用非 reap 观察确认同 PID/start 的 zombie，再尝试 fork；保存真实 rc/errno；之后 waitpid reap，再 fork 必须成功 | quota off 同样未 reap 序列必须能创建额外 child；两例都记录 zombie→reaped 转换及所有退出 |
| V8 lower-soft-restore /2 | 已降权 payload 将 soft1/hard2 exact 读回，fork EAGAIN；恢复 soft2/hard2 rc0/读回，再 fork 成功 | quota off 新 UID 同 fork 路径确实成功，记录 inherited 限值；不让 root 执行被测 restore |
| V9 raise-hard /2 | 非 root payload 提到3/3=-1/EPERM，读回仍2/2；不是 EINVAL、EACCES 或 profile 错误 | 另一个非 root quota-off healthy 实例可 fork；另加独立 root calibration 设置3/3并读回验证宿主支持，校准不是非 root 正控，共3实例 |
| V10 independent-UIDs /各2 | A持 child、B不同 UID 也持 child；A/B各第三 fork EAGAIN，无彼此污染 | quota-off 两 UID 各第三成功（最多6任务进程）；另1共享 UID故障反例，两 root由受控迁移占2槽后各 fork EAGAIN，证明共享会污染，共3实例 |
| V11 double-migration /1 | 同 attempt/UID 第二次启动在 root parent 的 one-shot 状态门拒绝，未 fork第二 trampoline、未迁移/执行第二 payload | 独立 TEST-only 反例仅故意旁路该门，两个固定 root child 迁入同一 UID，实际计数2且每个读回1/1；证明 setuid 不替代 fork 准入，2实例；禁止产品入口 |

V7 不预写所有支持 OS 的 zombie 计数结论。当前固定 XNU 的 reap 路径才减 realUID 计数，推测未 reap 时 EAGAIN，但推测不能当实测。正式证据必须记录非 reap 观察（拟 `waitid(..., WEXITED|WNOWAIT)` 加 root PID/start/state 观察，具体 SDK API 在 PLAN 冻结），不能 `waitpid` 后冒称 zombie。若实际未 reap 已释放额度，必须记录成功创建和计数；未有独立 SPEC 对“已死亡但未 reap 是否属于同时存在进程”合同映射批准前，此 case 不给 PASS、M0a2 阻断，不默默接受两种结果。不得为了固定期望修改合同。

原文“创建4个线程并join；随后fork”没有要求4个worker同时活跃。兼容原预算采用分波：先3个worker同步存活/握手并join，再第4个worker启动/握手/join；实际pthread_create成功总数4、join总数4，峰值总活跃线程4（含main）。不减为仅创建3个，不放宽至main+4=5；只证明此分波序列，不声称已证明4worker同时并发。两波都由同一payload执行，没有额外进程/线程协调器；最后fork只在全部join后进行。

### 3.1 32轮原子竞争：64个实际实例

cap4：根先创建两个单线程 child，三个成员在屏障上都存活；两个 child 均准备完毕后同一 release barrier 各尝试且只尝试1次 fork，成功者孙持续阻塞到结果全部记录。必须恰1成功/首 byte、另1=-1/EAGAIN，最大4任务进程；不能让先成功的孙提前退出后使另一方成功。每轮独立新 UID 的 quota-off 对照要求两孙都成功并保持屏障，最大5任务进程。没有重试、没有 fork loop；谁先成功不固定，但每轮两方结果完整。

32轮 quota +32轮 control=64实际 case，分两个独立原生 job，各16轮/32case。索引精确0..15和16..31，重复/缺轮/错片不接受；不能用一个“race logical case”隐藏64次运行。任一轮正控失败/前置不成立，该轮负控无效，不能只统计其余成功轮。两个片必须同候选 SHA、各自原件齐全后合取。

## 4. 启动故障完整映射：不把测试注入当生产逃逸

原 PLAN §2.3 的 profile syntax invalid、RELEASE EOF、payload ENOENT、真实 exec 后隐藏确认，仍由同新 SHA 的旧7 case 重跑覆盖，原 TEST 不改。剩余11项按下表各1个故障实例+1个新 UID 健康配对实例，共22。故障开关仅固定 TEST target 内 enum，root冻结，不能由 payload/任意 argv控制；正式新 observer 同样读取真实 gate/canary/OS结果，不按 case 名预填结果。

| 故障项 | 可验证注入边界与真实观察 | 必须拒绝/三态/健康配对 |
| --- | --- | --- |
| quota syscall 失败 | TEST-only OS wrapper 将本次 real setrlimit 参数改为 cur>max，实际 syscall=-1/EINVAL；保留原/实际参数 | 失败即退出、无 RELEASE/exec；健康 wrapper 不改参数并进入；不是 SOURCE 无文件或 cap2 EINVAL RED |
| soft 读回不一致 | TEST-only 配置 real cur0/max1，再走真实 getrlimit+exact checker | checker ERANGE、无 RELEASE；健康1/1通过；不伪造 getrlimit 返回结构 |
| hard 读回不一致 | 独立 root 可信阶段 real cur1/max2，再真实 checker 比1/1 | ERANGE、无 RELEASE；健康1/1通过；宽 hard 仅隔离 TEST故障，绝不 release/影响正常 profile |
| setgroups 失败 | 固定非法 count 使实际 setgroups=-1/EINVAL；无伪 errno | 短路，不再 setgid/setuid/RELEASE；配对单组/GID/UID全部成功 |
| setgid 失败 | TEST故障先按正常单组/GID/setuid顺序永久降为task UID，再尝试另一个独占 GID，实际 EPERM | 本次不代表普通 root setgid 天然失败；记录故障身份/目标，短路退出；健康 root顺序成功 |
| setuid 失败 | TEST故障先不可逆降为新 task UID，再尝试另一个独占 UID，实际 EPERM | 保存真实 IDs/EPERM，后续未执行；健康固定顺序成功；额外身份同样租约/不重用 |
| canary 意外可读 | 独立固定 TEST-only 错 profile 只添加本 fixture denied 文件 literal read allow，实际 open/read成功；正常profile模板完全不改，故障profile root-owned0444/受保护祖先，两份bytes/digest独立冻结 | 同 canary判定拒绝，未 RELEASE、未 payload；健康 canonicalprofile拒 denied且读allowed成功。此证明门拒绝故障profile，不宣称真实 Seatbelt被绕过，不在产品/正常准入路径扩权 |
| 受保护 gate 不存在 | TEST-only argv选择同 protectedfixture 下固定 absent目标，真实系统启动路径失败；独立核不存在/无 gate ready | 无 RELEASE/无payloadexec；仅有直接可信 exec错误才记errno，不能从 sandbox-exec退出码/文字猜errno；健康gate实际进入 |
| payload EACCES | gate exec固定 existing root-owned0444 allowed文件（本身不可exec），真实 execve=-1/EACCES | RELEASE可为1，但无 NOTE_EXEC、固定FAILED/EACCES、false；健康同受保护可执行probe NOTE_EXEC/true |
| exec后 observer通道中断 | root已记录 NOTE_EXEC并fsync独立ledger后，对sender临时接入read端已关闭的固定pipe，真实publish write=-1/EPIPE（屏蔽SIGPIPE）；恢复独立导出通道 | root审计true；未收到confirmation的controller先冻结unknown，不audit回填；健康同publisher完整送达。注入是delivery边界，不冒称observer被杀后仍完成收尾 |
| 假 SANDBOXED/EXEC_OK输出 | 固定非特权 TEST role在普通stdout写假字符串，再执行真实 preexec失败；不持有rootdeliverywriter，不伪造typedwire。另健康payload写同字符串且真实exec | 错误样本仍false/unknown按真实事件，不解析stdout当ready；健康只有独立NOTE_EXEC才true；明确失败样本的noise emitter不是已执行payload |

故障实例的“期望拒绝”是 TEST 自校验负控，不冒称已部署 SOURCE 有bug；故障返回/短路应来自实际受测 helper或gate路径，OS wrapper只选择故障入参，不替代 predicate/checker/observer，不构造假 native wire。新 controller 验收行为必须另有执行真实旧函数的语义 RED（例如旧门接受缺失/坏 M0a2 证据，新合同要求拒绝）；若旧接口并不存在可运行的相关接受路径，就如实只做新 TEST设施自校验，不用 missing import/function/compile error充生产RED。

## 5. 预算、分片与身份容量

实例指实际启动的一套独立 case，quota/control/错误基线/健康配对都单独计数；同 PID exec 前后观察不另算新实例，两个 UID 的配对场景虽1case却如实列实际多个root/进程。正式候选除24个SOURCE向量实例，还要重跑一个新 TESTOnly cap2 root-child-third无quota baseline及其独立创建正控，共2实例；它们不是额外隐藏在build步骤的运行。

| 每架构 job | 必须实例与总数 | 任务进程峰值 / 加rootobserver | 名义新租约ID数 |
| --- | --- | --- | --- |
| A：旧M0a1+W0/W1 | baseline7+SOURCE7+REDphase W1单组1/双组1+GREENphase W1单组1/双组1=18；W1每phase的5观察行不是5case | ≤2 /≤3 | 20（14旧UID+两phase各3 W1身份） |
| B：M0a2 vectors | V1..V8各2=16，V9三实例、V10三实例、V11两实例，SOURCE共24；另cap2错误基线1/独立创建正控1，共26 | ≤6 /≤7 | 27（rootcalibration不占taskUID，双UID场景另计） |
| C：M0a2 faults | §4的11故障+11健康，共22 | ≤2 /≤3 | 24（setgid/setuid故障各另租1ID） |
| D：race0 | 轮0..15各quota/control，共32 | ≤5 /≤6 | 32 |
| E：race1 | 轮16..31各quota/control，共32 | ≤5 /≤6 | 32 |

以上是拟议后续计划，尚未运行：每架构5个原生job、130实际case；arm64与x86_64合计10job/260case，每job最大32<48。旧已验18例不是由db47旧artifact替新候选，必须在最终同SHA重跑；分片增加job数量而不扩大每job原上限。最大任务进程6、加observer7，低于8；controller/systemtool并非任务成员，另记录祖先/工具PID，不用它们冒充taskhelper。V6累计新增pthread4、峰值总线程4，实际口径见§3。全部case串行，只有case规定的后代并发。

每job仍≤48case、每case≤15s（含reserve、准备、启动、屏障及收尾，绝对monotonic deadline，EINTR不重置），整job≤10min、导出全量日志/证据总≤16MiB、每case≤64KiB。建议native/collector整体480s硬deadline，配置构建绑定最多90s，封存上传留30s，合计600s；任一阶段超界失败，不延长、不截断后PASS。race片32×15s已等于480s，实际准备需占剩余时间，因此接近最坏时会失败，不能保证所有case各耗满15s仍完成；这是上限不是时间配额承诺。新 PLAN 若发现现实耗时不可行须提前重设计分片，不擅自加时。

保留当前固定夹具的CPU/文件安全预算：每任务进程CPU soft/hard2秒、regularfile64KiB，rootobserver CPU soft/hard20秒并读回；这些限值不能代NPROC oracle，若先耗尽则基础设施失败。新case15秒总deadline不放宽旧M0a1/W1本来更短的alarm。不得在任务UID内增加watchdog；超时监控在observer侧。

每job fixture仍只搜索UID/GID60000..61023，共1024；主/额外ID核目录服务、进程含supplementary、持久O_EXCL lease。上表是无碰撞名义消费，碰撞烧lease也计入同1024容量；unknown立即失败，已用/碰撞永不重发、耗尽ENOSPC不扩池。不同runner的数字可相同但不能相互授身份隔离信用；同宿主不同job/重试必须共享持久lease命名空间，不靠重新启动collector清空。每个新job各自新protected目录、ledger和artifact，不合并覆盖。

## 6. 审计、失败收尾和同 SHA 合取

新版本每case绑定 candidate/run/job/attempt/shard/case/round、实际OSbuild/kernel/arch/native translation状态、全部源码摘要、compiler/SDK/compileargv/header展开、helperobject/final普通 `_getgroups`且无`DARWIN_EXTSN`、每binary/profile/systemtool digest。每个实际成员记录角色、父PID、PID/start、real/effective/savedUID/GID、count1/read1单组、capcur/max、继承阶段、forkrc/errno或spawnrc、首byte、barrier与exec/exit/reap顺序、observer/collector各自三态、cleanupscope与retained/quarantine。未知字段显式unknown，不用0/默认成功掩盖。

root audit写0600、逐步fsync后封0444，受保护祖先/owner/mode/nlink/device/inode/size和读前后身份核验；collector先冻结真实delivery视图，再读独立root账本验digest。严格schema/顺序/完整case集合/类型/重复键/尾字节/跨候选/跨片拒绝。任一timeout、非零退出、超量、缺原件、observer拒绝均无成功result发布；保留有界原始stderr/stdout、实际退出状态/bytecounts/digests与已知protectedtarget，不能ERROR转quotaRED或SKIP转GREEN。

正常收尾是各直接父取得所有ownedchild wait0，再核有限身份快照无残留，sealedledger记录真实scope。超时/管道断裂/PIDstart不符/未知成员时停止新case，按已验证exactownedPID终结可证归属成员，失败保留；没有完整树证明只报owned-root回收，不升级成整树清零。fixture/UID/GID/lease保留直到runner销毁，不删除账户、不撤系统安全策略、不递归清理root/workspace。普通输出EOF、leader退出、子孙退出、root退出、审计封存是不同事件，均在同一deadline内验证。

最终验收是同候选SHA下A..E两架构全部强制门合取，不拼旧SHA、不取某片最新成功覆盖同候选失败。A保留原7case baseline真实RED+SOURCEGREEN、W0SDK/object/final绑定、W1单组/双组/同PIDexec与独立rawhash；B保留新cap2真实语义RED和全部向量SOURCE结果；C/D/E保留故障自校验与32轮全部正负控。每job独立artifact含原binary/源码manifest/rawaudit/delivery/log/退出状态，各hash核实后独立观察员复核；单job成功不能直接授M0a2完成。

## 7. 后续合法门与未完成依赖

本文先freshSPEC→不同QUALITY。下一步另写完整PLAN冻结新增TEST/driver/baseline/oracle/controller/CMake/CI与最小复用资产；不把本DESIGN当可执行PLAN。TEST作者先运行可编译、可启动、前置有效的错误基线：不施任务quota而V3真实根+child+third成功、errno0/首byte存在，正式“第三fork应EAGAIN”assert唯一语义FAIL；所有身份/启动/正控/协议非退化且0ERROR/0SKIP。不能拿当前cap2 EINVAL、缺文件/链接失败替代，也不能用人为wrongscenario宣称生产quota已回归。

新错误基线必须如实记录inherited cur/max（至少足够3个成员），不伪报2/2；仅固定TEST baseline variant的准入允许该已记录“不施quota”状态进入同一受保护payload，正式quota断言仍期望EAGAIN而实际创建第三成员。SOURCE variant依然配置/读回2/2才能RELEASE。此baseline差异须在独立PLAN完整资产中冻结、不可暴露为产品旁路；基线正常退出后才有语义RED信用，不以配置失败绕进断言。

不同SOURCE作者随后最小扩展cap域，保留exact读回与cap1语义，软件OS边界故障覆盖后经fresh实际双审；最终新SHA重跑§6全部门。软件model/编译/observer负控不能授macnative信用。若完整PLAN太大可按vectors、faults、race分成可审实施片，但最终M0a2必须在同候选重新合取，不能减门或提前启用产品。

M0b独立设计/完整PLAN仍是阻断：UID/GID/saved/groups全部改变入口、setuid/setgid executable、spawn替代UID/GID/groups、persona、线程身份、launchd、Mach、Launch Services外部代启动、task-port注入。每项必须同非root可达有效正控及带profile负控；仅setter成功、无权限EPERM、服务不存在、GUI不可用或跨UID天然拒绝不能封闭。M0a2不偷偷增加persona/daemon/账号/entitlement来合并CI；M0b可证伪路线，发现反例停下修订DESIGN。

即使M0a2全部通过，也只有M0a必要验证完成；M0b未全封闭，完整M0仍BLOCKED，M1未启用；M1安装/peer/重启租约、M2真实broker链、M3installed矩阵、M0b所有逃逸、R2/R3与≥90%/ready各自验收，不能由本片外推。当前无聚合内存硬限信用。

## 8. 独立只读主源研究与许可取舍

观察日2026-10-14，复用 [持续竞品对照](../../agent-landscape-live.md) 的Apple/Codex固定主源；本作者通过web实际读取下列固定版本与Apple归档API说明。公开源码标识不保证等于runner内核/SDK bytes，运行平台绑定另做。没有复制上游实现，无新第三方依赖；root负责另行同步live/handoff，本文不编辑它们。

| 主源、证据类别 | 观察、取舍与可验证收益/成本 |
| --- | --- |
| Apple实际源码：[XNU xnu-12377.1.9 kern_fork.c](https://github.com/apple-oss-distributions/xnu/blob/xnu-12377.1.9/bsd/kern/kern_fork.c) fork1/proc_limitfork | 采纳realUID增计/softNPROC准入与plimit继承作为待证伪机制；成本是独占身份/真实并发oracle；验收V1..V5/32轮，不从读源码授mac通过 |
| Apple实际源码：[kern_resource.c](https://github.com/apple-oss-distributions/xnu/blob/xnu-12377.1.9/bsd/kern/kern_resource.c) dosetrlimit | 采纳soft≤hard、hardraise权限与NPROC钳制说明，要求逐字段读回；验收V8/V9与失败注入；不静默接受较小cap |
| Apple实际源码：[kern_exit.c](https://github.com/apple-oss-distributions/xnu/blob/xnu-12377.1.9/bsd/kern/kern_exit.c) reap_child_locked及[sys/wait.h](https://github.com/apple-oss-distributions/xnu/blob/xnu-12377.1.9/bsd/sys/wait.h) | 采纳exit/reap分离观察；具体减计出现在reap路径，不能先验宣称zombie释放或占槽跨OS恒定；验收V7，未知映射阻断 |
| Apple官方归档：[posix_spawn(2)](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/posix_spawn.2.html) | 采纳函数returncode与失败PID未定义、FD/rlimit继承的API边界，拒绝只看errno或未变PID；归档不是当前SDK验收，验收V2实际运行 |
| OpenAI实际源码：[Codex 27065a91ccbf5ba8532844be3777fcf83b77820d exec.rs](https://github.com/openai/codex/blob/27065a91ccbf5ba8532844be3777fcf83b77820d/codex-rs/core/src/exec.rs) consume_output | 采纳“leader退出与后代持pipe/输出drain/expiration不同步”的收尾机制提醒；成本是固定deadline与独立状态；不采纳空输出/合成退出状态来替代native证据，不以groupkill授硬quota |

许可：所读Apple XNU文件各有APSL-2.0和文件内Berkeley等声明，Apple归档文档只引用接口事实；Codex固定 [LICENSE](https://github.com/openai/codex/blob/27065a91ccbf5ba8532844be3777fcf83b77820d/LICENSE) 为Apache-2.0。只借机制/链接，不复制APSL实现、私有syscall ABI或Codex实现；本片不改安装许可或系统安全配置。ES/VM沿原DESIGN暂缓/不适配，不靠研究替代原生正负控。

## 9. 作者 SPEC / QUALITY 自审及交付

SPEC自审：原§2.3全部故障映射§4+同SHA旧7case，原§3全部剩余向量映射§3/§3.1，原§4所有M0b仍§7阻断；预算/实例/身份分片显式§5；旧M0a1/W0/W1与新SHA合取§6；没有把cap2接口拒绝当RED。QUALITY自审：未改源码/TEST/CI/权限/Git；正常profile与故障profile信用分开，真实OS失败与TEST自校验分开，4次pthread创建与峰值总4按分波同时满足，zombie映射待实际观察/审查；无缺证据默许，无新root产品入口。本自审不替fresh独立双审，本文hash在外部交接记录，避免selfhash循环。

【架构级自检报告】

- 语法/编译：文档UTF-8/LF与链接/表结构静态核验；未新增可编译代码，不声称macOS编译已通过。
- 依赖/调用链：旧原语/协议/W0/W1与最终同SHA依赖明确，M2产品调用链未改。
- 逻辑/边界：root计1、后代/线程/zombie口径、32轮64实例及130实例/架构明确；未确认合同映射不PASS。
- 异常处理：身份/limit/profile/exec/交付/超时/超量/未知均拒绝或quarantine；不将ERROR当RED、不以audit回填确认。
- 关联模块：只新增本文；原DESIGN/PLAN及native/controller/formal/CI保留，live/handoff由root处理。
- 兼容安全：原预算未放宽，cap1旧接口当前未改，无root正控替非root，无权限/账号/服务扩张，无M0b/M1/ready信用。
- 可运行性：交付可进入fresh双审的DESIGN，不是可执行资产；后续完整PLAN/TEST真实RED/不同SOURCE/同SHA双native全部未执行，不写100%运行通过。
