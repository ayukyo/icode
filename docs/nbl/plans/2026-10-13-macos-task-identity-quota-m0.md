# macOS M0a1 完整资产实施计划；M0a2 / M0b 与完整 M0 仍待验

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development (recommended) or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在可销毁的原生 macOS CI 验证独占非零 real UID、精确 hard NPROC 与同 PID Seatbelt 启动的必要前提；不授完整 M0、M1、产品 ready 或 90% 验收信用。

**Architecture:** 一个固定 native root observer 只迁移一个可信 trampoline 到空 UID；trampoline 全面降权后原地 exec 系统 sandbox-exec，再 exec 受保护的可信 gate，最后同 PID exec 固定测试 payload。Python 只做非特权测试控制与回执断言；observer、审计、计时及收尾位于任务 UID 之外。M0b 必选逃逸向量是完整 M0 的未完成依赖，不能用 M0a 通过替代。

**Tech Stack:** macOS 系统 C11、Clang、CMake、libSystem、kqueue/kevent、系统 sandbox-exec；Python unittest。无新第三方运行时依赖；不复制 Apple 实现代码。

---

## 0. 精确 fence、状态与本次交付

观察日期 2026-10-13；资产补全日期 2026-10-14。本文件仅为文档候选，本次没有新增 TEST/SOURCE、没有编译或原生运行、没有新 CI、安装、账户、系统权限、提交或推送。

| 项目 | 冻结值 |
| --- | --- |
| 权威工作区 | `/home/orbbec/projects/icode` |
| PLAN 作者读取 HEAD | `6e893f0170b74c32d7143680636d85f400ecc7c9` |
| vendor gitlink | `21566a589cbe98bd35372a04bbb6ca1c51d8eed2` |
| DESIGN | `docs/nbl/specs/2026-10-13-macos-task-identity-quota-design.md` |
| DESIGN SHA-256 | `774e33f4c2485da553f6b41572ef9641c4b30dea307a8e466c2bbdca7b2e5b23`；root 独立 SPEC / QUALITY 均 C0/I0/M0 |
| 本次写入白名单 | 本 PLAN 一个文件 |
| 启动时CI候选（历史fence） | `6e893f0170b74c32d7143680636d85f400ecc7c9`；是否已终结由root核线上原日志，不取消覆盖未采集的运行 |
| 原生目标 | `macos-latest` 实测须为 arm64；`macos-15-intel` 实测须为 x86_64 |

真实问题：现有 `MacSeatbeltSandbox.policy_contract_ready=False`，macOS 未实际消费 `SandboxPolicy.process_limit` 为任务硬配额。已有实现：保留 `src/icode/isolation.py` 的 profile 与 `_MAC_PROCESS_RULES` 风格、现有 `native/windows/CMakeLists.txt` 的平台拒绝/C11/独立 native 目录模式、`.github/workflows/ci.yml` 双 macOS runner。调用链：本片故意不修改 `run_command → _controlled_dispatch → ToolContext.wrap_command → execution_broker.execute_policy_command`；M2 独立验证接线。

结构化推演：需求为根占 1、后代准入、独占计数域和启动事实；方案为 kernel fork admission 与可信同 PID gate；风险为 UID 迁移无准入检查、saved credentials、root bypass、额外 helper、exec 回执断链与未封闭外部代启动。root 已记录 DESIGN 的 sequential-thinking `352dff`；本 PLAN 作者工具目录未提供该 MCP，不虚构调用。

**修订历史：**2026-10-13原partialPLAN SHA-256 `eafdc9c6f18dfac0dc7d9b4f4a1b6fce44416c85b9b49df8edd83adb59351283`，Q1/Q3缺资产，未获批准。2026-10-14作者再次读取该实际hash与HEAD；root消息提及的`54f278`不是本次实际读取的bytes，不能据其授审查信用。本文追加§8完整M0a1资产并改§5任务；不回溯把原partialPLAN写成通过。

**首slice：**M0a1只验cap1 fork-only准入、单根UID迁移、samePID系统Seatbelt→gate→payload、具体文件canary正负控、savedcredential实际观察、preexec/postexec三态及控制FD关闭。§3其他case与§2.3其他fault为M0a2必须完成的原要求，**没有冻结完整M0a2资产，也不能称完整M0a通过**。§4M0b仍是完整M0/M1阻断依赖。§8提供首slice全部TEST/CMake/controller/CI与不同作者SOURCE资产；须freshSPEC→不同QUALITY审查，无任何代码块自带原生通过信用。

2026-10-14前一完整资产候选 SHA-256 45b03326dc25593f937f7b607e6a71cd86e54588696dd03c62a1ad036b853ad5 的独立 SPEC 为 C0/I2/M2，**未批准**：专用 supplementary GID 与旧 DESIGN 不符、receipt_loss 仅按 case 常量赋 unknown、Task2 测试名与实际方法不符、只读 marker 的文字误称可写。本修订绑定 root 已双审的 DESIGN 774e33（移除全部继承 host/root 组、只留专用 GID），旧 6be2 摘要仅属历史；其余三项按实际资产修正。修订 PLAN 仍需 fresh SPEC → 不同 QUALITY，不借 DESIGN 审查结果授 PLAN 信用。

## 1. 文件职责与执行白名单

下列是后续实施文件，当前均不创建。不要把探针塞入产品的正式 ready/doctor 路径。

| 文件 | 唯一职责 | 作者阶段 |
| --- | --- | --- |
| `tests/test_macos_task_quota_probe.py` | M0a1协议与正式nativeoracle；RED/GREEN不改期望 | TESTOnly，§8.5 |
| `native/mac/tests/icode_m0a1_driver.c` | 独立固定native实验驱动；observer/trampoline/gate/payload都在受审TEST夹具内，没有产品入口 | TESTOnly，§8.3 |
| `native/mac/tests/icode_m0a1_baseline.c` | 故意不施任务quota的可运行语义RED基线，不参与正式产品 | TESTOnly，§8.2 |
| `native/mac/icode_m0a1_limit.h` | 固定quota原语签名，baseline与SOURCE链接同一驱动 | TESTOnly冻结，§8.1 |
| `native/mac/icode_m0a1_limit.c` | 仅exactNPROC配置与读回，独立SOURCE作者在正式RED后创建 | SOURCE，§8.4 |
| `native/mac/CMakeLists.txt` | TESTOnly先只构建baseline；SOURCE加入后显式ON构建source实验target；无安装/service | TESTOnly驱动设施，§8.6 |
| `scripts/run_macos_m0_ci.py` | 非rootcontroller，限量rawlog/metadata、nativeRED分类和正式oracle | TESTOnly驱动设施，§8.7 |
| `.github/workflows/ci.yml` | 固定双格有限实验，先RED，再按trackedSOURCE执行GREEN；禁止本次实际修改 | 独立审查后的TESTOnly原生设施，§8.8 |

审计 JSONL 保存在本 job 受保护目录，逐 case 限 64 KiB、全 job 限 16 MiB；最多 48 个 case，每 case 15 秒、全原生步骤 10 分钟；最大 N=8，固定 payload 同时最多 8 进程、4 pthread，禁止 fork bomb。达到日志/时间/数量边界返回失败或 unknown，不能截断后继续计通过。

每个 native executable 由无特权 Clang 构建；root parent 启动前核固定候选的文件 digest、regular file、无 symlink、祖先、原生 Mach-O 架构与构建 manifest。root 建立自身所有的专用目录并复制固定 bytes；trampoline/gate/payload 使用该目录冻结绝对路径，parent 保存 device/inode/hash，任务不能写入替换。observer 不是服务，不接收模型请求、路径到 sudo 或任意 argv。root 进程不导入 repo Python，不执行 repo shell、构建插件或工作区 payload。只有固定 native child 能在降权前运行。

M0 的数字 UID 可由碰撞检查选择尚无目录服务账户、当前无进程的非零 ID，**不要求创建账户**；这是单个可销毁 runner 的 kernel 夹具，不冒充 M1 目录服务身份池。扫描可用数字区间是配置输入，边界须显式记录；`getpwuid`/目录查询错误不能当“不存在”，用原生 `getpwent` 完整枚举并核结束 errno、`proc_listallpids` 完整快照与 `proc_pidinfo(PROC_PIDTBSDINFO)` 核 UID。容量变化重读至上限，读不全/进程身份不明即 BLOCKED。GID 同样碰撞检查；native root parent 单线程串行独占 reserve，每个 case 使用新 UID，不复用。全 job 名额耗尽退出失败，不扩大区间或删除用户账户。

## 2. 受控同 PID 启动与确认协议

### 2.1 必须执行的原语顺序

root parent 冻结 N、UID/GID、profile hash、三个固定路径与 case ID。无同 UID 进程、无已用 UID、同 attempt 只能一次迁移；只 fork 一个 native child。parent 仍保持 root UID，属于 observer 而不属于任务根。

child 保留 stdin/stdout/stderr、gate status write FD、RELEASE read FD；清全部其他 FD、信号 handler/mask、环境、cwd。先 exact `setrlimit(RLIMIT_NPROC,{N,N})`、完整 `getrlimit` 读回；然后 `setgroups(1,&task_gid)` 将组列表收敛为唯一专用组、`setgid(gid)`、`setuid(uid)`。每一步失败同步回报固定错误记录并 `_exit`；绝不裸执行。这里不照搬Linux的“零组”假设：所读XNU `setgroups_internal`会把ngrp<1转换为group0；不能`setgroups(0,NULL)`后假定`getgroups`返回0。明确单个专用组可排除root/host额外组，具体runtime读回仍必须验。

```c
/* 独立原创的冻结调用顺序；上游代码不复制。 */
struct rlimit desired = { .rlim_cur = cap, .rlim_max = cap }, observed;
if (setrlimit(RLIMIT_NPROC, &desired) == -1) return errno;
if (getrlimit(RLIMIT_NPROC, &observed) == -1) return errno;
if (observed.rlim_cur != cap || observed.rlim_max != cap) return ERANGE;
if (setgroups(1, &task_gid) == -1) return errno;
if (setgid(task_gid) == -1) return errno;
if (setuid(task_uid) == -1) return errno;
if (getuid() != task_uid || geteuid() != task_uid ||
    getgid() != task_gid || getegid() != task_gid) return EPERM;
gid_t observed_group;
if (getgroups(0, NULL) != 1 || getgroups(1, &observed_group) != 1 ||
    observed_group != task_gid) return EPERM;
```

macOS 不假设 Linux `getresuid/getresgid` 存在。2026-10-14实际核固定XNU `proc_info.h`的`proc_bsdinfo.pbi_svuid/pbi_svgid`：rootobserver在gate阻塞且释放前用`proc_pidinfo(PROC_PIDTBSDINFO)`直接核real/effective/savedUID/GID与startidentity。payload另做降权后`seteuid(0)`/`setegid(0)`EPERM负例。这纠正原partialPLAN仅以setid语义推断saved值的盲点；具体runtime返回长度/字段必须正确，读不全不release。M0b其他saved identity、线程/persona完整向量仍未证实。

child 在降权后 `execve("/usr/bin/sandbox-exec", argv, clean_env)`，argv 固定为 `sandbox-exec -f <root-owned profile> <root-owned gate> <fixed case>`；gate 检验同 PID、凭据与 quota 读回并执行 profile canary。gate 不 fork，只同 PID exec 固定 payload。cap1 必须真实成功进入 payload，不存在“cap+helper”补偿。

profile 固定从已实际使用的规则构造：`(version 1)(deny default)`，沿现有 `_MAC_PROCESS_RULES` 的 `process-exec`/`process-fork`/same-sandbox signal/process-info，系统只读路径与固定受管 executable/profile 读权限、专用 workspace 的所需读写权限。不新增猜测的 set-id/persona/launchd deny operation。系统依赖路径必须从真实最小 probe 收敛，冻结具体 profile bytes 与 hash，禁止全 `file-read*` 或放开整个 host home。

设置一个 root-owned、mode 0444、普通任务 DAC 可读取、**没有 profile allow** 的 canary 文件；同 UID 无 Seatbelt 正控须 `open(O_RDONLY)` 成功，gate 在真实 profile 下须返回 EACCES/EPERM。另一个显式 allow 的 marker 文件正控只读，同为 0444；不新增写权限，防止 profile 把一切都拒绝。gate 不能把 DAC 拒绝当 Seatbelt 生效。任何 profile 编译/canary/凭据/quota 故障均在 RELEASE 前退出。

### 2.2 固定 gate 协议与 exec 观察

协议不是 M1 的服务 peer 认证。单 root observer fork 建立匿名管道，child 只持有写端；没有 pathname socket、nonce token 对 payload 暴露。

wire结构以§8.3的实际gate_record（72字节）/payload_record（96字节）为唯一真源：magic/version/length固定；phase为CONFIGURED=1、SANDBOXED=2、FAILED=3；FAILED涵盖配置或exec错误。gate报告real/effective凭据、group、cur/max与canary结果；root独立补saved凭据/startidentity与NOTE_EXEC事实。输出三态使用false/true/unknown字符串，不另定义与实际资产不一致的枚举或头文件。

使用 `write/read` 精确长度循环，EINTR 重试、短读缓存、EOF/trailing bytes/重复 phase 均失败；固定单个 writer 与短记录，不能把任意 payload 输出解析成 gate record。gate 等待一个 RELEASE byte；EOF、错误 byte、deadline 到期均不执行 payload。可信 gate 核 canary 完成后发送 `M0_SANDBOXED`；parent 此时 child 阻塞，不存在待消费 exec 事件。

parent 此时创建**新的** kqueue 并注册 child 的 `EVFILT_PROC`；禁止从此前 sandbox-exec→gate 的事件累计中推算“第几个 exec”。

```c
struct kevent registration, receipt;
EV_SET(&registration, child_pid, EVFILT_PROC,
       EV_ADD | EV_ENABLE | EV_CLEAR | EV_RECEIPT,
       NOTE_EXEC | NOTE_EXIT, 0, NULL);
struct timespec zero = {0, 0};
int count = kevent(kq, &registration, 1, &receipt, 1, &zero);
/* count != 1、非EV_ERROR receipt、receipt.data != 0 均拒绝 RELEASE。 */
```

只有注册成功且所有配置读回成立，parent 才给 RELEASE。gate 在最后 exec 前把 status write FD 设置 FD_CLOEXEC、关闭 RELEASE FD、移除协议路径/FD 参数并执行固定 payload；execve 返回失败时在仍打开的 status FD 写 `M0_EXEC_ERROR`，然后退出。若 status FD 的 close-on-exec 配置失败，也不执行 payload。

payload_started 真值规则：

| 观察 | 三态 | 动作 |
| --- | --- | --- |
| RELEASE 前可信阶段错误，且 child 已终结 | false | 保留错误，UID 退役/quarantine |
| RELEASE 后收到固定 gate EXEC_ERROR 且无 NOTE_EXEC | false | 终结，保留 errno，不重试 |
| RELEASE 后该新 kqueue 收到同 PID NOTE_EXEC | true | 记录 OS 事件与 phase，不能要求 payload 自报 READY |
| EOF、连接断开、observer 超时、注册错误、只有 NOTE_EXIT 且无足够证据 | unknown | quarantine；不能重试或推断 false |
| NOTE_EXEC 后日志/回执传递中断 | 已记录事件者 true；仅收到缺失摘要的 controller unknown | 各层如实保留事实，不改为 false |

NOTE_EXEC 证明成功 exec；与 gate 在 RELEASE 后只有一个冻结目标的代码和受保护 bytes 合起来才绑定 payload。它不证明 payload main 已到达，报告中分开 `payload_started` 与 `payload_probe_entered`。进程表、marker、status EOF 都不单独证明 exec；不能让 payload 持有 status write FD 或 RELEASE FD 伪造确认。fault injection 的“忽略 NOTE_EXEC”只由 native observer 测试开关执行，不改变 kernel 或 profile。

### 2.3 外部启动故障的完整 case

固定 case：设置 quota syscall 失败、soft/hard 读回不一致、setgroups/setgid/setuid 失败、canary 意外可读、profile syntax invalid、受保护 gate 不存在、RELEASE EOF、exec payload ENOENT、exec payload EACCES、exec 成功后隐藏原生确认输出、成功 exec 后 observer 通道中断。前八项禁止 RELEASE或可信目标exec；payload exec失败两项须实际 EXEC_ERROR+无 NOTE_EXEC；后两项不能产生 false。payload 的 stdout 写假 `SANDBOXED/EXEC_OK` 不应改变 parent 三态。固定 executable 路径不允许调用者替换成 shell或任意工作区命令。

## 3. M0a case oracle 与非退化对照

所有 case 都要有 native `errno`/spawn 返回码、返回 PID、实际凭据、读回 quota、父/子同步屏障与 child 首指令执行证据。child 在 fork 成功分支的第一条可观察操作向专属 pipe 写固定 byte；越限时这个分支根本不能执行。即使随后 kill了意外子进程，该 case 仍失败。observer 宿主采样仅辅助归属，不能证明从未超过 N。

| case | 限额 | 严格 oracle | 对照 |
| --- | --- | --- | --- |
| root-exec | 1 | 同一个 child PID历经trampoline/Seatbelt/gate/payload；非零UID；cur=max=1；payload进入 | 同固定路径无 profile 可进入；profile canary 正负控 |
| fork-only / fork-exec / posix-spawn | 1 | fork返回-1且errno=EAGAIN；posix_spawn返回EAGAIN、无有效child；child首byte不存在 | 每个向量在新UID、NPROC保持原宿主安全上限时创建1个child并回收成功 |
| root-child-third | 2 | 根+首child在pipe屏障均存在；根第三次fork EAGAIN | 关闭任务quota后同序列第三个创建成功，最多3进程 |
| reap-refork | 2 | 首child退出且waitpid确认reap后，下一fork成功 | 无profile对照排除profile错误阻止fork |
| grandchild | 2 | 根和child均存活时child的fork EAGAIN；root不提前退出 | 关闭quota后grandchild成功、同UID、继承读回 |
| concurrent-parents | 4 | 根+2个child在统一barrier后同时竞争最后1槽；恰1成功、另一EAGAIN，成功grandchild保持阻塞 | 关闭quota后两个grandchild都成功；最多5进程；32轮有界重复 |
| pthread | 1 | 创建4个线程并join；随后fork仍EAGAIN；记录4线程不增加进程计数 | 同native代码无quota线程也成功，随后fork成功 |
| zombie | 2 | child已exit、未waitpid；root再fork的真实结果及errno逐项记录；reap后可fork | 不预写XNU zombie计数结论；不能缺样本仍通过 |
| lower-soft-restore | 2 | 先把soft降至1、hard保留2，fork EAGAIN；恢复soft=2成功且读回；fork成功 | payload已经降权，不能由root执行恢复测试 |
| raise-hard | 2 | 非root payload把soft/hard提高3返回EPERM且读回仍2 | root observer在独立新夹具可设置3并读回，验证宿主容许3 |
| independent-UIDs | 每根2 | task A持有1个child时，另UID的B仍能持有1个child；各第三次EAGAIN | 单个共享UID负控需显示额度污染而非独立成功 |
| double-migration | 1 | 同attempt/UID第二次root迁移在parent拒绝，未执行第二payload | 专门故障fixture去掉reserve检查以显示setuid迁移能越過fork quota；该負控故意失败不能送产品 |

关闭 quota 指 native child 不施加任务 NPROC、保留安全宿主 limit，不设置 RLIM_INFINITY，不解除Seatbelt。这是 **同 UID 类型/同 privilege/同系统路径/同向量** 的创建正控。Seatbelt身份逃逸的正控则另外只去掉profile，不能混淆两种对照。正控失败则该负控无效、case BLOCKED；禁止借宿主资源不足的EAGAIN授予quota通过。

root/child/grandchild各在固定pipe上握手确认存活；竞争barrier由root与两个child预先建pipe，无额外同UID coordinator。父子持有的所有barrier FD均close-on-exec或在exec前关闭；超过期望窗口、短读或任何unexpected PID均失败。pthread夹具不得从多线程进程fork后调用非async-signal-safe库；fork child只write+_exit或execve固定目标。

zombie case记录未reap时的实际XNU口径。若未reap的死进程释放quota，不能假装符合“僵尸占槽”假设；对应合同映射必须在SPEC中明确允许或拒绝，未经审查不计此case通过。

## 4. 完整 M0b 不得删减的阻断表

这些不是M0a测试占位，也不是M1的安装/peer协议。尚未冻结完整可执行夹具的项目显式 BLOCKED。全部封闭后才能称完整 M0通过；任一必选向量未证实即阻止M1。

| 必选向量 | 具体已知入口 | 有效正控要求与当前状态 |
| --- | --- | --- |
| UID/GID/saved/groups | `setuid/seteuid/setreuid/setgid/setegid/setregid/setgroups`，set-id固定probe | 同UID、无profile、受控root-owned setuid/setgid executable实际获得目标身份；降权普通用户本来EPERM仅证明kernel拒绝，不证明Seatbelt额外封闭 |
| spawn替代身份 | `posix_spawnattr_set_uid_np/gid_np/groups_np` | 固定libsyscall签名已找到；需证明属性设置成功后真实spawn目标凭据；仅属性setter成功不够；不得以未授权调用EPERM当profile封闭 |
| persona | `posix_spawnattr_set_persona_np`及persona uid/gid/groups np | wrapper签名可查；运行OS上persona创建/查询/有效迁移正控与可用符号还没冻结，BLOCKED；不得猜syscall编号或私有struct ABI |
| 线程身份 | XNU `settid/gettid` kernel路径；pthread wrapper须逐OS核 | 不复制kernel参数ABI；尚无固定SDK/导出wrapper与有效正控，BLOCKED |
| setuid/setgid exec | 固定native身份probe，mode4755/2755，root-owned受保护bytes | 在同非root任务UID、不套profile时真实身份变化；带profile同路径无法改变任务计数域/权限；nosuid或SIP导致正控失败算BLOCKED |
| launchd外部代启动 | 固定系统launchctl和有界owned临时job | 必须同任务UID有真实可达的代启动正控，识别执行者UID/quota/profile；不会用root正控代替普通任务可达性；无临时job安装清单/身份域夹具，BLOCKED |
| Mach外部代启动 | `bootstrap_look_up`与native Mach send/receive | 独立受控服务确实接收到同UID无profile请求并新启动固定child；完整boundedserver协议未冻结，BLOCKED；查找不存在服务失败不是封闭 |
| Launch Services | 固定应用fixture与系统LS API | 同UID原生会话中真实应用启动正控、PID/身份归属；无GUI会话/API失败不能算封闭；当前BLOCKED |
| task-port注入 | `task_for_pid`、`mach_vm_write`/线程API | 固定受控victim、同UID可写目标的无profile正控须实际改变canary；跨UID天然无权只证明DAC；fixture尚未冻结，BLOCKED |

M0b 可以证伪本路线；发现set-id或代启动可逃逸即停止，保留证据并修订DESIGN。不临时增加任务权限、关闭系统安全策略、授entitlement、扩大profile或增加第三方服务来换通过。M1的受保护installer、native peer/audit实例认证、长期租约/重启恢复、Python入口另写PLAN；M2的真实broker dispatch另验。

## 5. M0a1 五个有界任务及交接门

### Task 1：审查完整 M0a1 PLAN 资产

**Dependencies:** None
**Parallelizable:** No（先freshSPEC，后不同QUALITY；本文不自授通过）

- [ ] SPEC作者完整读取§8全部资产，核首slice只授M0a1、§2.3/§3剩余M0a2与§4M0b条件均未移除。
- [ ] 不同QUALITY作者逐行核native权限/ownedtargets/sourcehash/FD/独占UID/新kqueue时序、controllerRED分类及CI退出状态。
- [ ] 核TESTOnly阶段含运行自身夹具所必需的CMake/controller/CI，不含§8.4 SOURCE limit；baseline正式oracle失败不是编译/权限ERROR。
- [ ] C0/I0/M0清零才写reviewartifact与PLANhash；任何安全先验或接口未成立记明确BLOCKED，不实施。

本任务是文档审查。资产代码在Markdown中，不从PLAN自动执行或提取运行。

### Task 2：TESTOnly，先获得真正的语义 RED

**Dependencies:** Task 1
**Parallelizable:** No（TESTOnly author必须独立于SOURCE作者）

- [ ] 只创建§8.1/8.2/8.3/8.5/8.6/8.7 TESTOnly资产与审查后的§8.8有限CIjob；不得创建§8.4 SOURCE limit。
- [ ] 使用§8.2 baseline的无quota函数链接同一完整nativeTESTdriver，运行§8.7 `--phase red`。正式`test_cap1_quota_semantic`必须因实际fork成功、errno0与EAGAIN不符而FAIL，其他正控/凭据/同PID/profile/FD/三态测试全部PASS，无ERROR/SKIP。
- [ ] 两格各保留baselinebinary/hash、nativeledger摘要与正式assertionRED；当前候选CI未结束前不新push/取消它。
- [ ] 将上述文件digest与完整case清单冻结交不同SOURCE作者，正式TEST期望不改；不是执行源文件不存在而制造ImportError。

TESTOnly原生入口与预期：

```bash
cmake -S native/mac -B "$RUNNER_TEMP/icode-m0a1-build" -DM0_BUILD_SOURCE=OFF
cmake --build "$RUNNER_TEMP/icode-m0a1-build" --parallel 1
python scripts/run_macos_m0_ci.py --build-dir "$RUNNER_TEMP/icode-m0a1-build" --output "$RUNNER_TEMP/icode-m0a1-red" --phase red --expected-arch "$ICODE_M0A1_ARCH"
```

### Task 3：不同 SOURCE 作者配置精确原语

**Dependencies:** Task 2
**Parallelizable:** No（SOURCE作者不同于TEST作者，依赖两格正式RED）

- [ ] 仅创建§8.4 `native/mac/icode_m0a1_limit.c`，不修改冻结TESTdriver/baseline/oracle/profile/CI/接口或产品隔离类。
- [ ] SOURCE `m0_apply_limit/m0_check_limit`每次exact读回；fork前仍可信native，全面降权后gate核验；任何错误不得releasepayload。
- [ ] 经不同SPEC/QUALITY与必要本机密钥/子仓/静态检查后按已有main-only授权提交推送，线上原生GREEN；本机不冒充macOS编译/运行。
- [ ] 同一个candidatejob仍跑baseline正式RED以及source正式GREEN，证明去掉quota后oracle恢复FAIL，而不是降低期望。

```bash
cmake -S native/mac -B "$RUNNER_TEMP/icode-m0a1-build" -DM0_BUILD_SOURCE=ON
cmake --build "$RUNNER_TEMP/icode-m0a1-build" --parallel 1
python scripts/run_macos_m0_ci.py --build-dir "$RUNNER_TEMP/icode-m0a1-build" --output "$RUNNER_TEMP/icode-m0a1-green" --phase green --expected-arch "$ICODE_M0A1_ARCH"
```

预期CMake仅Darwin，C11，`-Wall -Wextra -Werror`；libSystem与SDK自带依赖，构建目录由runner临时路径管理，SOURCE代码不在构建时生成reviewedTEST资产。

### Task 4：M0a1 有限线上原生双格核验

**Dependencies:** Task 3
**Parallelizable:** Yes（两台隔离runner可并行；同台UID分配与case必须串行）

- [ ] 确认当前`6e893f...`CI已终结并收集原始结果；本片不得取消它。SOURCE候选独立审查、本机密钥/子仓与必要回归通过后才按既有授权push main。
- [ ] 只使用§8.8有限M0a1 job，矩阵精确`macos-latest`/`macos-15-intel`，`fail-fast:false`、job10分钟；没有`continue-on-error`或缺权限SKIP转PASS。
- [ ] 复用现CI pinnedcheckout `3d3c42e5aac5ba805825da76410c181273ba90b1`与setuppython `5fda3b95a4ea91299a34e894583c3862153e4b97`，`persist-credentials:false`；uploadartifact固定`ea165f8d65b6e75b540449e92b4886f43607fa02`，2026-10-14实际GitHubAPI查询v4 ref返回commit，不猜SHA。
- [ ] 使用§8.7的完整argv数组启动nativeobserver：固定sudo/env、绝对baseline/source目标、actualcandidateSHA与binarydigest；rootparser仅收两个有界hex参数。不能root运行Python/shell；nativeparent核受保护copy及系统Seatbelt/祖先。
- [ ] 正控/负控/故障case完整输出；`always()`上传受保护回执和原始native日志，附件哈希、exitstatus、实际SHA/job/OS均有，失败仍保留；下载/发布controller不具备更改root回执的成功字段权限。

§8.7控制器是本slice唯一执行入口；此处命令仅为计划，当前不执行：

```bash
python scripts/run_macos_m0_ci.py --build-dir "$RUNNER_TEMP/icode-m0a1-build" --output "$RUNNER_TEMP/icode-m0a1-green" --phase green --expected-arch "$ICODE_M0A1_ARCH"
```

controller拒绝root启动，记录`git rev-parse HEAD`与`GITHUB_SHA`一致、`sw_vers`/`uname`实值、manifest/hash并调用native；它的成功exitcode只能来自全部必选case完整且正控有效。runnerlabel并不证明OS/arch，实际arm64/x86_64不符则失败，不能自动转Rosetta或调整目标。

### Task 5：验收、保留与完整 M0 阻断交接

**Dependencies:** Task 4
**Parallelizable:** No（最终验收需合并双格绑定证据）

- [ ] 原生每case完整绑定`candidate_sha / run_id / job / OS_build / kernel / arch / observer_PID / task_PID_start_identity / UID_GID / groups / credential_verification / cap_cur_max / syscall_rc_errno / barrier / control_success / exec_phase / payload_started / payload_probe_entered / cleanup_scope / unknown_reason / retained_targets`。
- [ ] root写固定摘要后，收尾只处理manifest中该experiment所有的exactPID与device/inode校验对象；不按用户名、模糊进程名、宽UID范围或通配目录kill/delete。
- [ ] 任务UID不复用；rootobserver不能确证所有后代结束时quarantine并保留对象/回执。只报告groupcleanup，脱组残留不冒称整树清零；UID未知成员不贸然kill。
- [ ] 保留测试UID与ownedfixture直到runner销毁，**不删除任何用户账户**，不递归清理`/private/var/root`、`RUNNER_TEMP`或workspace。已有createdobjects可列manifest，移除必须exactownedtarget验证；验证失败保留并报失败。
- [ ] 两格M0a1全部首slicecasePASS仍只记“M0a1必要前提原生通过”；M0a2原knownvectors/fault与M0b未封闭继续BLOCKED，完整M0/M1/M2/M3/90%与产品ready不放行。任何首slice强制case失败则M0a1失败，按原日志最小定位，不扩大权限重跑掩盖。

## 6. 主源与取舍记录

观察日2026-10-13，采用固定Apple发布标识`xnu-12377.1.9`，不能映射成当前runner二进制已匹配；实际OS/kernel必须独立记录。只阅读机制，不复制Apple文件；XNU有APSL-2.0及具体文件内Berkeley/其他声明，私有接口阅读不等于获得稳定ABI保证。

- **采纳：**[kern_fork.c](https://github.com/apple-oss-distributions/xnu/blob/xnu-12377.1.9/bsd/kern/kern_fork.c)、[kern_resource.c](https://github.com/apple-oss-distributions/xnu/blob/xnu-12377.1.9/bsd/kern/kern_resource.c)的realUID准入/soft与hard约束作为待原生证伪假设；收益是独占域可能复用内核准入，成本是root可信边界与不重用容量，兼容影响仅测试native文件，验收§3正负控。
- **采纳为M0a观察：**[sys/event.h](https://github.com/apple-oss-distributions/xnu/blob/xnu-12377.1.9/bsd/sys/event.h)的EVFILT_PROC/NOTE_EXEC/EV_RECEIPT与[kern_event.c](https://github.com/apple-oss-distributions/xnu/blob/xnu-12377.1.9/bsd/kern/kern_event.c)实现路径；收益为payload不可伪造OSexec事件，成本为可信gate唯一exec目标与FD/注册时序，验收§2失败/回执丢失。未实测前不称macOS所有版本保证。
- **暂缓：**[libsyscall spawn_private.h](https://github.com/apple-oss-distributions/xnu/blob/xnu-12377.1.9/libsyscall/wrappers/spawn/spawn_private.h)与[posix_spawn.c](https://github.com/apple-oss-distributions/xnu/blob/xnu-12377.1.9/libsyscall/wrappers/spawn/posix_spawn.c)确有persona/替代UID/GID/groups入口；收益为具体向量，成本为privateABI/运行OS可用性与有效正控，当前M0bBLOCKED，不把固定header存在当运行成功。
- **不适配：**用sampling+kill、AUTH_EXEC代替fork准入、root代普通任务正控、隐藏socket/path代认证，以及假设set-idprofile规则。不会新增依赖、复制许可不明代码或改现行调用链。

root负责把本观察与[持续竞品对照](../../agent-landscape-live.md)/[handoff](../../development-handoff.md)同步；作者不写这两个文件，不覆盖其他并行记录。

2026-10-14补核主源：[固定XNU proc_info.h](https://github.com/apple-oss-distributions/xnu/blob/xnu-12377.1.9/bsd/sys/proc_info.h)与[libproc.h](https://github.com/apple-oss-distributions/xnu/blob/xnu-12377.1.9/libsyscall/wrappers/libproc/libproc.h)提供具体savedUID/GID/startidentity字段；[固定Apple Libc acl.h](https://github.com/apple-oss-distributions/Libc/blob/71bbe350ab79eef58113991d817ccc6165061a64/include/sys/acl.h)、[acl_entry.c](https://github.com/apple-oss-distributions/Libc/blob/71bbe350ab79eef58113991d817ccc6165061a64/posix1e/acl_entry.c)、[filesec.c](https://github.com/apple-oss-distributions/Libc/blob/71bbe350ab79eef58113991d817ccc6165061a64/gen/filesec.c)、[statx_np.c](https://github.com/apple-oss-distributions/Libc/blob/71bbe350ab79eef58113991d817ccc6165061a64/sys/statx_np.c)明确DarwinACL iterator成功=0、结束EINVAL，不能套Linux返回值。采纳root阶段ACL只读检查，任何ALLOW修改权/未知读取失败拒绝，不修改系统ACL换通过；已核Libc commit，header为APSL-1.1、所读实现为APSL-2.0、man页有BSD声明，只用接口、不复制实现。收益为补mode-only盲点，成本为可能保守拒绝合法ACL，验收为nativesetup实际成功或可区分infrastructureERROR。

[Apple Rosetta文档](https://developer.apple.com/documentation/apple-silicon/about-the-rosetta-translation-environment)的官方dataJSON实际已读，sysctl.proc_translated=1表示翻译、ENOENT作为native未翻译路径；代码独立写检测与长度/错误校验，未知/翻译均拒绝，不以runnerlabel冒原生。uploadartifact v4 ref于2026-10-14通过GitHubAPI实际返回commit ea165f8d65b6e75b540449e92b4886f43607fa02；采用固定SHA，CI之外不新增依赖或权限。

## 7. 首slice与完整阶段的信用边界

M0a1原生GREEN只证明固定probe中cur/hard=1、fork创建时EAGAIN，以及所列启动/文件/凭据观察。UID枚举只辅助归属，persona/线程credential的实际计数域仍未知，不能从一个数字UID推断“内核计数域=完整task”；cap2/继承/并发/所有逃逸向量仍待M0a2/M0b。其他安装、peer、长期池、broker真实dispatch、installed矩阵独立验收。两格TESTOnlyRED不是M0a1通过；M0a1通过不是完整quota/M0/M1通过；现行ready与90%门不变。

## 8. M0a1 完整资产（代码仅存于本文，不实施）

固定7个case：cap1_fork/control_fork/seatbelt_positive/profile_error/release_eof/exec_error/receipt_loss。nativeTEST-onlydriver运行受保护的同一可执行文件；baseline与SOURCE只更换quota原语，正式oracle/profile/gate/凭据/屏障不变。receipt_loss是交付故障：nativeledger记录true，controller消费unknown。payload stdout/status/data严格分离，status/RELEASE FD在payloadexec时关闭。每observer7case，总wall120秒/CPU20秒；每childwall10秒/CPU2秒、regularfile64KiB、最多fork1个立即退出child；copy≤16MiB、snapshot≤8192PID、目录服务各≤16384条、输出≤64KiB。无forkloop/任意程序/argv。UID60000–61023仅为有界搜索范围，逐项核账户/组/进程/已用lease；原生root-ownedO_EXCLmarker避免baseline/source复用UID。不可确定或耗尽即失败，不放宽搜索、不删账户/lease/fixture。

交付确认与审计严格分账：root stdout 只发每 case 的 launch（含实际 released）及独立 confirmation，最后发 audit manifest；不镜像完整 case audit 行。receipt_loss 在真实 NOTE_EXEC 后的 sender 交付点实际不写 confirmation bytes，仍 fsync 完整 root ledger。controller 先仅解析该 delivery 通道，对任何实际缺失 confirmation 一律保守 unknown，并落盘 delivery-view.json；之后才非特权读取已完成的 root-owned native.jsonl 作独立原生 oracle。root 在结束时将 ledger 从 0600 改为 0444，只开放有限实验审计读，不开放写；root-owned 0755 目录及已核祖先阻止任务/host 替换，失败未导出仍保留原对象。native.audit.jsonl 和 delivery 原始 stdout 分别 hash 绑定，audit 的 true 不反填 missing confirmation；payload stdout 为 /dev/null，不持有 root delivery writer。

### 8.1 TESTOnly：native/mac/icode_m0a1_limit.h

```c
#ifndef ICODE_M0A1_LIMIT_H
#define ICODE_M0A1_LIMIT_H
#include <sys/resource.h>
int m0_apply_limit(rlim_t cap, int enabled);
int m0_check_limit(rlim_t cap, int enabled);
const char *m0_variant(void);
#endif
```

### 8.2 TESTOnly错误基线：native/mac/tests/icode_m0a1_baseline.c

明确不施quota、不伪造读回，仅为正式RED；其他代码与SOURCE运行同一driver。

```c
#include "icode_m0a1_limit.h"
int m0_apply_limit(rlim_t cap,int enabled) {
    (void)cap; (void)enabled; return 0;
}
int m0_check_limit(rlim_t cap,int enabled) {
    (void)cap; (void)enabled; return 0;
}
const char *m0_variant(void) { return "baseline"; }
```

### 8.3 TESTOnly：native/mac/tests/icode_m0a1_driver.c

下面为一个完整文件。仅使用SDK声明的接口，不复制Apple实现；libproc无法编译/返回完整记录是ERROR。初次root进入已审候选nativebuild属于本次有限CI实验，不授M1产品installer来源认证信用；rootchild执行前已复制并hash核验到protectedbytes。所有代码仍在本文，禁止本次实际创建C文件。

```c
#define _DARWIN_C_SOURCE 1
#include "icode_m0a1_limit.h"
#include <CommonCrypto/CommonDigest.h>
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <inttypes.h>
#include <libproc.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <mach-o/loader.h>
#include <poll.h>
#include <pwd.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/acl.h>
#include <sys/event.h>
#include <sys/stat.h>
#include <sys/sysctl.h>
#include <sys/utsname.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

enum { UID_FIRST=60000, UID_COUNT=1024, MAX_PIDS=8192,
       MAX_IMAGE=16*1024*1024, MAGIC=0x4d304131, CONFIGURED=1,
       SANDBOXED=2, FAILED=3 };
struct gate_record {
    uint32_t magic,version,length,phase;
    int32_t error,pid;
    uint32_t uid,euid,gid,egid,groups,group;
    uint64_t current,maximum;
    int32_t canary_errno,canary_allowed;
};
struct payload_record {
    uint32_t magic,version,length,pid,uid,euid,gid,egid;
    int32_t fd3_errno,fd4_errno,recover_uid_errno,recover_gid_errno;
    int32_t fork_pid,fork_errno,child_byte,entered,groups,group;
    uint64_t current,maximum;
    int32_t canary_errno,canary_allowed;
};
_Static_assert(sizeof(struct gate_record)==72,"gate ABI changed");
_Static_assert(sizeof(struct payload_record)==96,"payload ABI changed");
struct case_def { const char *name; int quota,sandbox,fault; };
static const struct case_def cases[]={
    {"cap1_fork",1,1,0},{"control_fork",0,1,0},
    {"seatbelt_positive",0,0,0},{"profile_error",1,1,1},
    {"release_eof",1,1,2},{"exec_error",1,1,3},{"receipt_loss",1,1,4}
};
static volatile sig_atomic_t owned_child;
static const char lease_root[]="/private/var/icode-m0a1-leases";
static const char owner_text[]="ICODE-M0A1-v1\n";
static char image[PATH_MAX],directory[PATH_MAX],binary_hash[65],sandbox_hash[65];
static unsigned char unavailable[UID_COUNT];
static int canary_errno=-1,canary_allowed;
static void expire(int sig) {
    (void)sig;
    if(owned_child>0) (void)kill((pid_t)owned_child,SIGKILL);
    _exit(124);
}
static void die(const char *stage) {
    int e=errno ? errno : EPROTO;
    fprintf(stderr,"M0A1 infrastructure stage=%s errno=%d\n",stage,e);
    if(!strncmp(directory,"/private/var/icode-m0a1.",sizeof("/private/var/icode-m0a1.")-1))
        fprintf(stderr,"M0A1 retained directory=%s cleanup=unknown\n",directory);
    if(owned_child>0) (void)kill((pid_t)owned_child,SIGKILL);
    exit(2);
}
static int all_write(int fd,const void *buf,size_t n) {
    const unsigned char *p=buf;
    while(n) {
        ssize_t r=write(fd,p,n);
        if(r<0 && errno==EINTR) continue;
        if(r<=0) return errno ? errno : EIO;
        p+=r; n-=(size_t)r;
    }
    return 0;
}
static int all_read(int fd,void *buf,size_t n) {
    unsigned char *p=buf;
    while(n) {
        ssize_t r=read(fd,p,n);
        if(r<0 && errno==EINTR) continue;
        if(r<=0) return r==0 ? EPIPE : errno;
        p+=r; n-=(size_t)r;
    }
    return 0;
}
static int read_record(int fd,void *buf,size_t n) {
    struct pollfd p={.fd=fd,.events=POLLIN};
    int r;
    do { r=poll(&p,1,11000); } while(r<0 && errno==EINTR);
    if(r<=0) return r==0 ? ETIMEDOUT : errno;
    return all_read(fd,buf,n); /* Fixed writer plus child alarm bounds read. */
}
static int hex_string(const char *s,size_t n) {
    if(strlen(s)!=n) return 0;
    for(size_t i=0;i<n;i++)
        if(!((s[i]>='0' && s[i]<='9') || (s[i]>='a' && s[i]<='f'))) return 0;
    return 1;
}
static int numeric(const char *s,int low,int high) {
    char *end=NULL; errno=0; long v=strtol(s,&end,10);
    if(errno || end==s || *end || v<low || v>high) die("numeric");
    return (int)v;
}
static int acl_safe(const char *path,struct stat *st) {
    filesec_t sec=filesec_init();
    if(!sec) return errno ? errno : ENOMEM;
    int e=0,present=0;
    if(lstatx_np(path,st,sec)<0) e=errno;
    if(!e && filesec_query_property(sec,FILESEC_ACL,&present)<0) e=errno;
    acl_t acl=NULL;
    if(!e && present) {
        if(filesec_get_property(sec,FILESEC_ACL,&acl)<0) e=errno;
        if(!e && (!acl || acl==(acl_t)_FILESEC_REMOVE_ACL || acl_valid(acl)<0)) e=EINVAL;
        acl_permset_mask_t read_mask=ACL_READ_DATA|ACL_EXECUTE|ACL_READ_ATTRIBUTES|
            ACL_READ_EXTATTRIBUTES|ACL_READ_SECURITY|ACL_SYNCHRONIZE;
        for(unsigned i=0;!e && i<=ACL_MAX_ENTRIES;i++) {
            acl_entry_t entry; errno=0;
            int r=acl_get_entry(acl,i==0 ? ACL_FIRST_ENTRY : ACL_NEXT_ENTRY,&entry);
            if(r<0 && errno==EINVAL) break; /* Valid ACL, validated iterator exhausted. */
            if(r!=0 || i==ACL_MAX_ENTRIES) { e=EPROTO; break; }
            acl_tag_t tag; acl_permset_mask_t permissions=0;
            if(acl_get_tag_type(entry,&tag)<0 || acl_get_permset_mask_np(entry,&permissions)<0) {
                e=errno; break;
            }
            if(tag!=ACL_EXTENDED_ALLOW && tag!=ACL_EXTENDED_DENY) { e=EPROTO; break; }
            /* Conservative: no principal may gain mutation rights through an ALLOW ACE. */
            if(tag==ACL_EXTENDED_ALLOW && (permissions&~read_mask)) { e=EPERM; break; }
        }
    }
    if(acl && acl!=(acl_t)_FILESEC_REMOVE_ACL && acl_free(acl)<0 && !e) e=errno;
    filesec_free(sec);
    return e;
}
static int secure_chain(const char *path) {
    char copy[PATH_MAX];
    if(path[0]!='/' || strlen(path)>=sizeof(copy)) return EINVAL;
    struct stat root;
    int e=getuid()==0 ? acl_safe("/",&root) : (lstat("/",&root)<0 ? errno : 0);
    if(e) return e;
    if(root.st_uid!=0 || (root.st_mode&022) || !S_ISDIR(root.st_mode)) return EPERM;
    strcpy(copy,path);
    for(char *p=copy+1;;p++) {
        if(*p!='/' && *p) continue;
        char saved=*p; *p=0; struct stat st;
        e=getuid()==0 ? acl_safe(copy,&st) : (lstat(copy,&st)<0 ? errno : 0);
        if(e) return e;
        if(st.st_uid!=0 || (st.st_mode&022) || S_ISLNK(st.st_mode)) return EPERM;
        *p=saved; if(!saved) break;
    }
    return 0;
}
static void self_path(void) {
    char buf[PATH_MAX]; uint32_t n=sizeof(buf);
    if(_NSGetExecutablePath(buf,&n)!=0 || !realpath(buf,image)) die("self-path");
    strcpy(directory,image);
    char *slash=strrchr(directory,'/');
    if(!slash) die("self-directory");
    *slash=0;
}
static int hash_fd(int fd,char out[65],size_t bound) {
    CC_SHA256_CTX ctx; unsigned char buf[65536],digest[CC_SHA256_DIGEST_LENGTH];
    if(lseek(fd,0,SEEK_SET)<0 || CC_SHA256_Init(&ctx)!=1) return EIO;
    size_t total=0;
    for(;;) {
        ssize_t n=read(fd,buf,sizeof(buf));
        if(n<0 && errno==EINTR) continue;
        if(n<0) return errno;
        if(!n) break;
        if((size_t)n>bound-total) return EFBIG;
        total+=(size_t)n;
        if(CC_SHA256_Update(&ctx,buf,(CC_LONG)n)!=1) return EIO;
    }
    if(CC_SHA256_Final(digest,&ctx)!=1) return EIO;
    for(size_t i=0;i<sizeof(digest);i++) sprintf(out+2*i,"%02x",digest[i]);
    out[64]=0; return 0;
}
static int protected_image(const char *expected) {
    const char prefix[]="/private/var/icode-m0a1.";
    if(strncmp(directory,prefix,sizeof(prefix)-1)!=0) return EPERM;
    int e=secure_chain(image);
    if(e) return e;
    int fd=open(image,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
    if(fd<0) return errno;
    struct stat st; char digest[65];
    e=fstat(fd,&st)<0 ? errno : (!S_ISREG(st.st_mode) ? EINVAL : 0);
    if(!e) e=hash_fd(fd,digest,MAX_IMAGE);
    if(close(fd)<0 && !e) e=errno;
    if(!e && strcmp(digest,expected)) e=EPERM;
    return e;
}
static void create_file(const char *name,const void *data,size_t n,mode_t mode) {
    char path[PATH_MAX];
    if(snprintf(path,sizeof(path),"%s/%s",directory,name)>=(int)sizeof(path)) die("path");
    int fd=open(path,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    if(fd<0 || all_write(fd,data,n) || fchmod(fd,mode)<0 || fsync(fd)<0) die("create-file");
    if(close(fd)<0) die("close-file");
}
static void prepare_image(const char *expected) {
    int in=open(image,O_RDONLY|O_NOFOLLOW|O_CLOEXEC); struct stat st;
    if(in<0 || fstat(in,&st)<0 || !S_ISREG(st.st_mode) || st.st_size<=0 || st.st_size>MAX_IMAGE)
        die("source-image");
    struct mach_header_64 mh;
    if(all_read(in,&mh,sizeof(mh)) || mh.magic!=MH_MAGIC_64) die("native-Mach-O");
#if defined(__arm64__)
    if(mh.cputype!=CPU_TYPE_ARM64) die("Mach-O-arm64");
#elif defined(__x86_64__)
    if(mh.cputype!=CPU_TYPE_X86_64) die("Mach-O-x86_64");
#else
#error Unsupported native macOS architecture
#endif
    char observed[65];
    if(hash_fd(in,observed,MAX_IMAGE) || strcmp(observed,expected)) die("source-hash");
    if(secure_chain("/private/var")) die("protected-parent");
    strcpy(directory,"/private/var/icode-m0a1.XXXXXX");
    if(!mkdtemp(directory) || chmod(directory,0755)<0 || secure_chain(directory)) die("fixture-directory");
    char target[PATH_MAX];
    if(snprintf(target,sizeof(target),"%s/probe",directory)>=(int)sizeof(target)) die("copy-path");
    int out=open(target,O_RDWR|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    if(out<0 || lseek(in,0,SEEK_SET)<0) die("copy-open");
    unsigned char buf[65536]; size_t copied=0;
    for(;;) {
        ssize_t n=read(in,buf,sizeof(buf));
        if(n<0 && errno==EINTR) continue;
        if(n<0) die("copy-read");
        if(!n) break;
        if((size_t)n>MAX_IMAGE-copied || all_write(out,buf,(size_t)n)) die("copy-bound");
        copied+=(size_t)n;
    }
    if(hash_fd(out,observed,MAX_IMAGE) || strcmp(observed,expected) ||
       fchmod(out,0555)<0 || fsync(out)<0) die("protected-copy-hash");
    if(close(in)<0 || close(out)<0) die("copy-close");
    strcpy(image,target); strcpy(binary_hash,expected);
    create_file("allowed","A",1,0444); create_file("denied","D",1,0444);
    const char bad[]="(version 1)(";
    create_file("bad.sb",bad,sizeof(bad)-1,0444);
    char profile[4096];
    int n=snprintf(profile,sizeof(profile),
        "(version 1)\n(deny default)\n(allow process-exec)\n(allow process-fork)\n"
        "(allow signal (target same-sandbox))\n(allow process-info* (target same-sandbox))\n"
        "(allow sysctl-read)\n"
        "(allow file-read-metadata file-test-existence (path-ancestors \"%s\"))\n"
        "(allow file-read* file-test-existence (literal \"/\") "
        "(subpath \"/usr/lib\") (subpath \"/System/Library\") "
        "(literal \"%s\") (literal \"%s/profile.sb\") (literal \"%s/allowed\") "
        "(literal \"%s/not-created\"))\n",
        image,image,directory,directory,directory);
    if(n<=0 || n>=(int)sizeof(profile)) die("profile-bound");
    create_file("profile.sb",profile,(size_t)n,0444);
}
static void directory_accounts(void) {
    size_t n=0; errno=0; setpwent(); struct passwd *pw;
    while((pw=getpwent())!=NULL) {
        if(++n>16384) die("passwd-bound");
        if(pw->pw_uid>=UID_FIRST && pw->pw_uid<UID_FIRST+UID_COUNT)
            unavailable[pw->pw_uid-UID_FIRST]=1;
        errno=0;
    }
    int e=errno; endpwent();
    if(e) { errno=e; die("passwd-enumeration"); }
    n=0; errno=0; setgrent(); struct group *gr;
    while((gr=getgrent())!=NULL) {
        if(++n>16384) die("group-bound");
        if(gr->gr_gid>=UID_FIRST && gr->gr_gid<UID_FIRST+UID_COUNT)
            unavailable[gr->gr_gid-UID_FIRST]=1;
        errno=0;
    }
    e=errno; endgrent();
    if(e) { errno=e; die("group-enumeration"); }
}
static int process_count(uid_t uid) {
    pid_t pids[MAX_PIDS]; int n=proc_listallpids(pids,sizeof(pids)),count=0;
    if(n<=0 || n>=MAX_PIDS) return -1;
    for(int i=0;i<n;i++) {
        if(pids[i]<=0) continue;
        struct proc_bsdinfo b;
        int r=proc_pidinfo(pids[i],PROC_PIDTBSDINFO,0,&b,sizeof(b));
        if(r!=(int)sizeof(b)) {
            errno=0;
            if(kill(pids[i],0)<0 && errno==ESRCH) continue;
            return -1;
        }
        if(b.pbi_ruid==uid || b.pbi_uid==uid || b.pbi_svuid==uid ||
           b.pbi_rgid==uid || b.pbi_gid==uid || b.pbi_svgid==uid) count++;
    }
    return count;
}
static int lease_directory(void) {
    int fresh=mkdir(lease_root,0700)==0;
    if(!fresh && errno!=EEXIST) die("lease-mkdir");
    if(secure_chain(lease_root)) die("lease-chain");
    int dir=open(lease_root,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if(dir<0) die("lease-open");
    struct stat st;
    if(fstat(dir,&st)<0 || (st.st_mode&0777)!=0700) die("lease-mode");
    if(fresh) {
        int f=openat(dir,"owner",O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
        if(f<0 || all_write(f,owner_text,sizeof(owner_text)-1) || fsync(f)<0 || close(f)<0)
            die("lease-owner-write");
    }
    int f=openat(dir,"owner",O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
    char buf[sizeof(owner_text)];
    if(f<0 || fstat(f,&st)<0 || st.st_uid!=0 || !S_ISREG(st.st_mode) ||
       (st.st_mode&0777)!=0600 || st.st_size!=(off_t)(sizeof(owner_text)-1) ||
       all_read(f,buf,sizeof(owner_text)-1) || memcmp(buf,owner_text,sizeof(owner_text)-1) ||
       close(f)<0) die("lease-owner-read");
    return dir;
}
static uid_t reserve_uid(int dir,const char *sha) {
    for(unsigned i=0;i<UID_COUNT;i++) {
        if(unavailable[i]) continue;
        uid_t uid=UID_FIRST+i; int before=process_count(uid);
        char lookup[16384]; struct passwd pw,*pw_result=NULL; struct group gr,*gr_result=NULL;
        int lookup_error=getpwuid_r(uid,&pw,lookup,sizeof(lookup),&pw_result);
        if(lookup_error) { errno=lookup_error; die("uid-directory-lookup"); }
        if(pw_result) continue;
        lookup_error=getgrgid_r(uid,&gr,lookup,sizeof(lookup),&gr_result);
        if(lookup_error) { errno=lookup_error; die("gid-directory-lookup"); }
        if(gr_result) continue;
        if(before<0) die("reserve-process-snapshot");
        if(before) continue;
        char name[32]; snprintf(name,sizeof(name),"uid-%u",uid);
        int f=openat(dir,name,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
        if(f<0 && errno==EEXIST) continue;
        if(f<0 || all_write(f,sha,40) || fsync(f)<0 || close(f)<0) die("reserve-lease");
        unavailable[i]=1;
        if(process_count(uid)!=0) die("reserve-contaminated");
        return uid;
    }
    errno=ENOSPC; die("reserve-exhausted"); return 0;
}
static int credentials(uid_t uid) {
    gid_t g=0;
    if(getuid()!=uid || geteuid()!=uid || getgid()!=uid || getegid()!=uid ||
       getgroups(0,NULL)!=1 || getgroups(1,&g)!=1 || g!=uid) return EPERM;
    return 0;
}
static void send_gate(unsigned phase,int error) {
    struct gate_record r; memset(&r,0,sizeof(r));
    r.magic=MAGIC; r.version=1; r.length=sizeof(r); r.phase=phase;
    r.error=error; r.pid=getpid(); r.uid=getuid(); r.euid=geteuid();
    r.gid=getgid(); r.egid=getegid(); gid_t g=0; int n=getgroups(1,&g);
    r.groups=n<0 ? UINT32_MAX : (uint32_t)n; r.group=g;
    struct rlimit l;
    if(getrlimit(RLIMIT_NPROC,&l)<0) { r.phase=FAILED; r.error=errno; }
    else { r.current=l.rlim_cur; r.maximum=l.rlim_max; }
    r.canary_errno=canary_errno; r.canary_allowed=canary_allowed;
    if(all_write(3,&r,sizeof(r))) _exit(93);
}
static void worker_fail(int error) { send_gate(FAILED,error); _exit(94); }
static void trampoline(unsigned index,uid_t uid,const char *hash) {
    if(getuid()!=0 || protected_image(hash)) worker_fail(EPERM);
    const struct case_def *c=&cases[index]; gid_t gid=uid;
    int e=m0_apply_limit(1,c->quota);
    if(e) worker_fail(e);
    if(setgroups(1,&gid)<0 || setgid(gid)<0 || setuid(uid)<0) worker_fail(errno);
    e=credentials(uid);
    if(e) worker_fail(e);
    e=m0_check_limit(1,c->quota);
    if(e) worker_fail(e);
    send_gate(CONFIGURED,0);
    char idx[16],id[16],profile[PATH_MAX];
    snprintf(idx,sizeof(idx),"%u",index); snprintf(id,sizeof(id),"%u",uid);
    char *env[]={"PATH=/usr/bin:/bin",NULL};
    char *args[]={image,"G",idx,id,(char *)hash,NULL};
    if(!c->sandbox) { execve(image,args,env); worker_fail(errno); }
    if(snprintf(profile,sizeof(profile),"%s/%s",directory,c->fault==1 ? "bad.sb" : "profile.sb")
       >=(int)sizeof(profile)) worker_fail(ENAMETOOLONG);
    char *sandbox_args[]={"/usr/bin/sandbox-exec","-f",profile,image,"G",idx,id,(char *)hash,NULL};
    execve("/usr/bin/sandbox-exec",sandbox_args,env); worker_fail(errno);
}
static int canaries(int sandbox) {
    char path[PATH_MAX]; snprintf(path,sizeof(path),"%s/allowed",directory);
    int f=open(path,O_RDONLY|O_NOFOLLOW);
    if(f<0) return errno;
    char value=0;
    int e=all_read(f,&value,1);
    if(close(f)<0 && !e) e=errno;
    if(e || value!='A') return e ? e : EPROTO;
    canary_allowed=1;
    snprintf(path,sizeof(path),"%s/denied",directory); errno=0;
    f=open(path,O_RDONLY|O_NOFOLLOW); canary_errno=f<0 ? errno : 0;
    if(f>=0) {
        e=all_read(f,&value,1);
        if(close(f)<0 && !e) e=errno;
        if(e || value!='D') return e ? e : EPROTO;
    }
    return (sandbox && canary_errno!=EPERM && canary_errno!=EACCES) ||
           (!sandbox && canary_errno) ? EPROTO : 0;
}
static void gate(unsigned index,uid_t uid,const char *hash) {
    const struct case_def *c=&cases[index]; int e=protected_image(hash);
    if(e) worker_fail(e);
    e=credentials(uid);
    if(e) worker_fail(e);
    e=m0_check_limit(1,c->quota);
    if(e) worker_fail(e);
    e=canaries(c->sandbox);
    if(e) worker_fail(e);
    send_gate(SANDBOXED,0);
    char release=0;
    if(all_read(4,&release,1) || release!='R') worker_fail(ECANCELED);
    if(close(4)<0) worker_fail(errno);
    if(fcntl(3,F_SETFD,FD_CLOEXEC)<0) worker_fail(errno);
    char idx[16],id[16]; snprintf(idx,sizeof(idx),"%u",index); snprintf(id,sizeof(id),"%u",uid);
    char *args[]={image,"P",idx,id,(char *)hash,NULL};
    char *env[]={"PATH=/usr/bin:/bin",NULL};
    char path[PATH_MAX];
    if(c->fault==3) {
        snprintf(path,sizeof(path),"%s/not-created",directory);
        execve(path,args,env);
    } else execve(image,args,env);
    worker_fail(errno);
}
static void payload(unsigned index,uid_t uid,const char *hash) {
    if(protected_image(hash) || credentials(uid)) _exit(95);
    if(canaries(cases[index].sandbox)) _exit(113);
    struct payload_record r; memset(&r,0,sizeof(r)); struct rlimit l;
    r.magic=MAGIC; r.version=1; r.length=sizeof(r); r.pid=getpid(); r.entered=1;
    r.uid=getuid(); r.euid=geteuid(); r.gid=getgid(); r.egid=getegid();
    gid_t g=0; r.groups=getgroups(1,&g); r.group=(int32_t)g;
    errno=0;
    if(write(3,"X",1)<0) r.fd3_errno=errno;
    errno=0;
    if(write(4,"X",1)<0) r.fd4_errno=errno;
    (void)all_write(STDOUT_FILENO,"SANDBOXED EXEC_OK\n",17);
    errno=0;
    if(seteuid(0)<0) r.recover_uid_errno=errno; else _exit(96);
    errno=0;
    if(setegid(0)<0) r.recover_gid_errno=errno; else _exit(97);
    if(getrlimit(RLIMIT_NPROC,&l)<0) _exit(98);
    r.current=l.rlim_cur; r.maximum=l.rlim_max;
    r.canary_errno=canary_errno; r.canary_allowed=canary_allowed;
    int marker[2];
    if(pipe(marker)<0) _exit(99);
    errno=0; pid_t p=fork(); r.fork_pid=p; r.fork_errno=p<0 ? errno : 0;
    if(p==0) { ssize_t n=write(marker[1],"C",1); _exit(n==1 ? 0 : 100); }
    close(marker[1]);
    if(p>0) {
        int s; pid_t w;
        do { w=waitpid(p,&s,0); } while(w<0 && errno==EINTR);
        if(w!=p || !WIFEXITED(s) || WEXITSTATUS(s)) _exit(101);
    }
    char byte=0; ssize_t n;
    do { n=read(marker[0],&byte,1); } while(n<0 && errno==EINTR);
    if(n<0 || (n==1 && byte!='C')) _exit(102);
    r.child_byte=(int32_t)n; close(marker[0]);
    if(all_write(5,&r,sizeof(r))) _exit(103);
    close(5); _exit(0);
}
static int valid_gate(const struct gate_record *r,pid_t pid,uid_t uid,unsigned phase) {
    return r->magic==MAGIC && r->version==1 && r->length==sizeof(*r) &&
        r->phase==phase && !r->error && r->pid==pid && r->uid==uid &&
        r->euid==uid && r->gid==uid && r->egid==uid && r->groups==1 && r->group==uid;
}
static int wait_owned(pid_t pid,int *status) {
    sigset_t mask,old; sigemptyset(&mask); sigaddset(&mask,SIGALRM);
    for(unsigned attempt=0;attempt<100;attempt++) {
        if(sigprocmask(SIG_BLOCK,&mask,&old)<0) return -1;
        pid_t r=waitpid(pid,status,WNOHANG); int saved=errno;
        if(r==pid) owned_child=0;
        if(sigprocmask(SIG_SETMASK,&old,NULL)<0) return -1;
        if(r==pid) return 0;
        if(r<0 && saved!=EINTR) { errno=saved; return -1; }
        (void)usleep(10000);
    }
    errno=ETIMEDOUT; return -1;
}
static void run_case(unsigned index,uid_t uid,int ledger,const char *sha,const char *kernel,
                     const char *os_build,const char *arch,const char *profile_hash) {
    const struct case_def *c=&cases[index];
    int status_pipe[2],release_pipe[2],data_pipe[2];
    if(pipe(status_pipe)<0 || pipe(release_pipe)<0 || pipe(data_pipe)<0) die("pipes");
    pid_t pid=fork();
    if(pid<0) die("observer-fork");
    if(pid==0) {
        alarm(10); owned_child=0;
        struct rlimit cpu={2,2},files={65536,65536};
        if(setrlimit(RLIMIT_CPU,&cpu)<0 || setrlimit(RLIMIT_FSIZE,&files)<0) _exit(104);
        struct rlimit actual;
        if(getrlimit(RLIMIT_CPU,&actual)<0 || actual.rlim_cur!=2 || actual.rlim_max!=2 ||
           getrlimit(RLIMIT_FSIZE,&actual)<0 || actual.rlim_cur!=65536 || actual.rlim_max!=65536)
            _exit(116);
        int limit=getdtablesize();
        if(limit<6 || limit>65536) _exit(105);
        if(dup2(status_pipe[1],3)<0 || dup2(release_pipe[0],4)<0 || dup2(data_pipe[1],5)<0) _exit(106);
        for(int f=6;f<limit;f++) {
            if(close(f)<0 && errno!=EBADF) _exit(114);
        }
        int null=open("/dev/null",O_RDWR);
        if(null<0) _exit(107);
        /* Preserve bounded fixed-tool stderr as raw evidence, never as a receipt. */
        for(int f=0;f<2;f++) if(dup2(null,f)<0) _exit(108);
        if(null>5) close(null);
        for(int s=1;s<NSIG;s++) {
            if(s!=SIGKILL && s!=SIGSTOP && signal(s,SIG_DFL)==SIG_ERR) _exit(115);
        }
        sigset_t empty; sigemptyset(&empty);
        if(sigprocmask(SIG_SETMASK,&empty,NULL)<0) _exit(109);
        if(chdir(directory)<0) _exit(110);
        char start=0;
        if(all_read(4,&start,1) || start!='A') _exit(111);
        char idx[16],id[16];
        snprintf(idx,sizeof(idx),"%u",index); snprintf(id,sizeof(id),"%u",uid);
        char *args[]={image,"T",idx,id,binary_hash,NULL};
        char *env[]={"PATH=/usr/bin:/bin",NULL};
        execve(image,args,env); _exit(112);
    }
    owned_child=pid;
    close(status_pipe[1]); close(release_pipe[0]); close(data_pipe[1]);
    struct proc_bsdinfo initial,cred; memset(&cred,0,sizeof(cred));
    if(proc_pidinfo(pid,PROC_PIDTBSDINFO,0,&initial,sizeof(initial))!=(int)sizeof(initial))
        die("start-identity");
    if(all_write(release_pipe[1],"A",1)) die("start-release");
    struct gate_record configured,ready,late; memset(&ready,0,sizeof(ready));
    ready.canary_errno=-1;
    int e=read_record(status_pipe[0],&configured,sizeof(configured));
    int configured_ok=!e && valid_gate(&configured,pid,uid,CONFIGURED);
    if(configured_ok) e=read_record(status_pipe[0],&ready,sizeof(ready));
    int ready_ok=configured_ok && !e && valid_gate(&ready,pid,uid,SANDBOXED);
    int count=-1,cred_ok=0,kq=-1,registered=0,released=0,exec_seen=0,exec_error=0;
    if(ready_ok) {
        if(proc_pidinfo(pid,PROC_PIDTBSDINFO,0,&cred,sizeof(cred))==(int)sizeof(cred)) {
            cred_ok=cred.pbi_pid==(uint32_t)pid && cred.pbi_ruid==uid && cred.pbi_uid==uid &&
                cred.pbi_svuid==uid && cred.pbi_rgid==uid && cred.pbi_gid==uid && cred.pbi_svgid==uid &&
                cred.pbi_start_tvsec==initial.pbi_start_tvsec &&
                cred.pbi_start_tvusec==initial.pbi_start_tvusec;
        }
        count=process_count(uid);
        /* The TEST baseline deliberately ignores quota; SOURCE cannot do so. */
        int limits_ok=!c->quota || strcmp(m0_variant(),"baseline")==0 ||
            (ready.current==1 && ready.maximum==1 && configured.current==1 && configured.maximum==1);
        if(cred_ok && count==1 && limits_ok) {
            kq=kqueue();
            struct kevent change,receipt; struct timespec zero={0,0};
            EV_SET(&change,pid,EVFILT_PROC,EV_ADD|EV_ENABLE|EV_CLEAR|EV_RECEIPT,NOTE_EXEC|NOTE_EXIT,0,NULL);
            if(kq>=0 && kevent(kq,&change,1,&receipt,1,&zero)==1 &&
               (receipt.flags&EV_ERROR) && receipt.data==0) registered=1;
        }
    }
    if(registered && c->fault!=2) {
        if(!all_write(release_pipe[1],"R",1)) released=1;
    }
    close(release_pipe[1]);
    char launch[256];
    int launch_n=snprintf(launch,sizeof(launch),
        "{\"kind\":\"launch\",\"version\":1,\"case\":\"%s\",\"released\":%d}\n",c->name,released);
    if(launch_n<=0 || launch_n>=(int)sizeof(launch) ||
       all_write(STDOUT_FILENO,launch,(size_t)launch_n)) die("delivery-launch");
    if(!released && c->fault!=1 && c->fault!=2) (void)kill(pid,SIGKILL);
    if(released) {
        struct kevent event; struct timespec timeout={11,0}; int exited=0;
        while(!exited) {
            int n=kevent(kq,NULL,0,&event,1,&timeout);
            if(n<0 && errno==EINTR) continue;
            if(n!=1 || (event.flags&EV_ERROR) || event.ident!=(uintptr_t)pid) break;
            if(event.fflags&NOTE_EXEC) exec_seen=1;
            if(event.fflags&NOTE_EXIT) exited=1;
        }
        if(!exited) (void)kill(pid,SIGKILL);
    }
    int status=0;
    if(wait_owned(pid,&status)<0) die("owned-waitpid");
    if(kq>=0) close(kq);
    unsigned char raw[sizeof(late)+1]; size_t used=0;
    for(;;) {
        ssize_t n=read(status_pipe[0],raw+used,sizeof(raw)-used);
        if(n<0 && errno==EINTR) continue;
        if(n<0) die("status-drain");
        if(!n) break;
        used+=(size_t)n;
        if(used==sizeof(raw)) die("status-extra-bytes");
    }
    close(status_pipe[0]);
    if(used) {
        if(used!=sizeof(late)) die("status-short-packet");
        memcpy(&late,raw,sizeof(late));
        if(late.magic!=MAGIC || late.version!=1 || late.length!=sizeof(late) ||
           late.phase!=FAILED || late.pid!=pid || late.error<=0) die("status-late-contract");
        exec_error=late.error;
    }
    struct payload_record p; memset(&p,0,sizeof(p)); p.canary_errno=-1; int entered=0;
    size_t data_used=0;
    while(data_used<sizeof(p)) {
        ssize_t n=read(data_pipe[0],(unsigned char *)&p+data_used,sizeof(p)-data_used);
        if(n<0 && errno==EINTR) continue;
        if(n<0) die("payload-data-read");
        if(!n) break;
        data_used+=(size_t)n;
    }
    if(data_used && data_used!=sizeof(p)) die("payload-short-packet");
    char extra;
    if(data_used==sizeof(p)) {
        if(p.magic!=MAGIC || p.version!=1 || p.length!=sizeof(p) || p.pid!=(uint32_t)pid ||
           p.uid!=uid || p.euid!=uid || p.gid!=uid || p.egid!=uid || p.entered!=1 ||
           read(data_pipe[0],&extra,1)!=0) die("payload-data-contract");
        entered=1;
    }
    close(data_pipe[0]);
    int remaining=process_count(uid);
    const char *started=exec_seen ? "true" : (!released || exec_error ? "false" : "unknown");
    int normal_exit=WIFEXITED(status) && WEXITSTATUS(status)==0;
    char saved_uid[32]="null",saved_gid[32]="null";
    if(cred_ok) {
        snprintf(saved_uid,sizeof(saved_uid),"%u",cred.pbi_svuid);
        snprintf(saved_gid,sizeof(saved_gid),"%u",cred.pbi_svgid);
    }
    char row[4096];
    int n=snprintf(row,sizeof(row),
        "{\"kind\":\"case\",\"version\":1,\"candidate_sha\":\"%s\",\"variant\":\"%s\","
        "\"case\":\"%s\",\"kernel\":\"%s\",\"os_build\":\"%s\",\"arch\":\"%s\",\"translated\":0,"
        "\"binary_sha256\":\"%s\",\"profile_sha256\":\"%s\",\"sandbox_exec_sha256\":\"%s\",\"observer_pid\":%d,"
        "\"observer_uid\":%u,\"pid\":%d,\"start_sec\":%" PRIu64 ",\"start_usec\":%" PRIu64 ","
        "\"uid\":%u,\"gid\":%u,\"saved_uid\":%s,\"saved_gid\":%s,\"credentials_valid\":%d,"
        "\"configured\":%d,\"sandboxed\":%d,\"quota_enabled\":%d,\"profile_enabled\":%d,"
        "\"cur\":%" PRIu64 ",\"hard\":%" PRIu64 ",\"uid_count_at_barrier\":%d,"
        "\"registered\":%d,\"released\":%d,\"kernel_exec\":%d,\"payload_started\":\"%s\","
        "\"exec_errno\":%d,\"entered\":%d,\"normal_exit\":%d,"
        "\"payload_pid\":%u,\"payload_cur\":%" PRIu64 ",\"payload_hard\":%" PRIu64 ","
        "\"fd3_errno\":%d,\"fd4_errno\":%d,\"recover_uid_errno\":%d,\"recover_gid_errno\":%d,"
        "\"groups\":%d,\"group\":%d,\"fork_pid\":%d,\"fork_errno\":%d,\"child_byte\":%d,"
        "\"gate_canary_errno\":%d,\"gate_canary_allowed\":%d,"
        "\"payload_canary_errno\":%d,\"payload_canary_allowed\":%d,"
        "\"wait_status\":%d,\"exit_code\":%d,\"term_signal\":%d,"
        "\"remaining\":%d,\"cleanup_scope\":\"owned_root_only\",\"retained\":true}\n",
        sha,m0_variant(),c->name,kernel,os_build,arch,binary_hash,profile_hash,sandbox_hash,(int)getpid(),getuid(),
        (int)pid,initial.pbi_start_tvsec,initial.pbi_start_tvusec,uid,uid,saved_uid,saved_gid,
        cred_ok,configured_ok,ready_ok,c->quota,c->sandbox,ready.current,ready.maximum,count,
        registered,released,exec_seen,started,exec_error,entered,normal_exit,p.pid,
        p.current,p.maximum,p.fd3_errno,p.fd4_errno,p.recover_uid_errno,p.recover_gid_errno,
        p.groups,p.group,p.fork_pid,p.fork_errno,p.child_byte,
        ready.canary_errno,ready.canary_allowed,p.canary_errno,p.canary_allowed,
        status,WIFEXITED(status) ? WEXITSTATUS(status) : -1,WIFSIGNALED(status) ? WTERMSIG(status) : 0,remaining);
    if(n<=0 || n>=(int)sizeof(row) || all_write(ledger,row,(size_t)n) || fsync(ledger)<0)
        die("audit-write");
    /* Actual sender-side delivery fault: omit the confirmation bytes, not the
       kernel event or root audit row. No case-specific "unknown" is emitted. */
    char confirmation[256];
    int confirmation_n=snprintf(confirmation,sizeof(confirmation),
        "{\"kind\":\"confirmation\",\"version\":1,\"case\":\"%s\",\"payload_started\":\"%s\"}\n",
        c->name,started);
    if(confirmation_n<=0 || confirmation_n>=(int)sizeof(confirmation)) die("confirmation-format");
    if(c->fault==4 && !exec_seen) die("receipt-loss-requires-real-exec");
    if(c->fault!=4 && all_write(STDOUT_FILENO,confirmation,(size_t)confirmation_n))
        die("delivery-confirmation");
    if(remaining!=0) die("remaining-unknown-or-contamination");
}
int main(int argc,char **argv) {
    self_path();
    if(argc==5 && (!strcmp(argv[1],"T") || !strcmp(argv[1],"G") || !strcmp(argv[1],"P"))) {
        unsigned index=(unsigned)numeric(argv[2],0,(int)(sizeof(cases)/sizeof(cases[0]))-1);
        uid_t uid=(uid_t)numeric(argv[3],UID_FIRST,UID_FIRST+UID_COUNT-1);
        if(!hex_string(argv[4],64)) die("worker-hash-argument");
        if(!strcmp(argv[1],"T")) trampoline(index,uid,argv[4]);
        if(!strcmp(argv[1],"G")) gate(index,uid,argv[4]);
        payload(index,uid,argv[4]); return 2;
    }
    if(argc!=3 || getuid()!=0 || geteuid()!=0 || !hex_string(argv[1],40) || !hex_string(argv[2],64))
        die("observer-arguments");
    umask(077);
    if(signal(SIGALRM,expire)==SIG_ERR || signal(SIGPIPE,SIG_IGN)==SIG_ERR) die("signals");
    alarm(120); struct rlimit cpu={20,20};
    if(setrlimit(RLIMIT_CPU,&cpu)<0) die("observer-cpu");
    struct rlimit actual_cpu;
    if(getrlimit(RLIMIT_CPU,&actual_cpu)<0 || actual_cpu.rlim_cur!=20 || actual_cpu.rlim_max!=20)
        die("observer-cpu-readback");
    for(int f=3;f<6;f++) if(open("/dev/null",O_RDWR|O_CLOEXEC)!=f) die("fd-layout");
    struct utsname u; char os_build[64]; size_t os_n=sizeof(os_build);
    if(uname(&u)<0 || sysctlbyname("kern.osversion",os_build,&os_n,NULL,0)<0) die("os-identity");
    for(const char *s=os_build;*s;s++)
        if(!((*s>='0' && *s<='9') || (*s>='A' && *s<='Z') || (*s>='a' && *s<='z')))
            die("os-build-format");
    for(const char *s=u.release;*s;s++)
        if(!((*s>='0' && *s<='9') || *s=='.')) die("kernel-format");
    if(strcmp(u.machine,"arm64") && strcmp(u.machine,"x86_64")) die("runtime-arch");
    int translation=-1; size_t translation_size=sizeof(translation); errno=0;
    int query=sysctlbyname("sysctl.proc_translated",&translation,&translation_size,NULL,0);
    int native_process=(query==0 && translation_size==sizeof(translation) && translation==0) ||
                       (query<0 && errno==ENOENT);
    if(!native_process) die("translated-or-unknown-process");
    if(secure_chain("/usr/bin/sandbox-exec")) die("system-seatbelt-ancestry");
    int sf=open("/usr/bin/sandbox-exec",O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
    struct stat system_image;
    if(sf<0 || fstat(sf,&system_image)<0 || !S_ISREG(system_image.st_mode) ||
       !(system_image.st_mode&0111) || (system_image.st_mode&(S_ISUID|S_ISGID)) ||
       hash_fd(sf,sandbox_hash,MAX_IMAGE) || close(sf)<0)
        die("system-seatbelt-image");
    prepare_image(argv[2]); directory_accounts(); int leases=lease_directory();
    char ledger_path[PATH_MAX],profile_path[PATH_MAX],profile_hash[65];
    snprintf(ledger_path,sizeof(ledger_path),"%s/native.jsonl",directory);
    snprintf(profile_path,sizeof(profile_path),"%s/profile.sb",directory);
    int pf=open(profile_path,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
    if(pf<0 || hash_fd(pf,profile_hash,4096) || close(pf)<0) die("profile-hash");
    int ledger=open(ledger_path,O_RDWR|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    if(ledger<0) die("ledger-open");
    for(unsigned i=0;i<sizeof(cases)/sizeof(cases[0]);i++) {
        uid_t uid=reserve_uid(leases,argv[1]);
        run_case(i,uid,ledger,argv[1],u.release,os_build,u.machine,profile_hash);
    }
    char digest[65];
    /* Audit-only export: root-owned protected directory remains nonwritable.
       Nonroot controller reads this file only AFTER freezing its delivery view.
       It contains this finite fixture's evidence, no credentials/secrets. */
    if(hash_fd(ledger,digest,65536) || fchmod(ledger,0444)<0 || fsync(ledger)<0 ||
       close(ledger)<0 || close(leases)<0) die("ledger-hash");
    printf("{\"kind\":\"audit\",\"version\":1,\"ledger_sha256\":\"%s\","
           "\"root_directory\":\"%s\",\"retained\":true}\n",digest,directory);
    if(fflush(stdout)==EOF) die("final-audit");
    alarm(0); return 0;
}
```

### 8.4 不同 SOURCE 作者：native/mac/icode_m0a1_limit.c

仅正式RED后创建；SOURCE不改driver/oracle/baseline/profile。

```c
#include "icode_m0a1_limit.h"
#include <errno.h>
int m0_check_limit(rlim_t cap,int enabled) {
    if(!enabled) return 0;
    struct rlimit actual;
    if(getrlimit(RLIMIT_NPROC,&actual)<0) return errno;
    return actual.rlim_cur==cap && actual.rlim_max==cap ? 0 : ERANGE;
}
int m0_apply_limit(rlim_t cap,int enabled) {
    if(!enabled) return 0;
    if(cap!=1) return EINVAL; /* Explicitly a cap1-only slice. */
    struct rlimit target={.rlim_cur=cap,.rlim_max=cap};
    if(setrlimit(RLIMIT_NPROC,&target)<0) return errno;
    return m0_check_limit(cap,1);
}
const char *m0_variant(void) { return "source"; }
```

### 8.5 TESTOnly：tests/test_macos_task_quota_probe.py

正式nativeoracle仅test_cap1_quota_semantic在baseline失败。协议测试另记便携账；便携PASS不能授原生quota信用。普通fullsuite未显式请求native时只跳该native类，不作为macOS验收；M0a1controller显式加载该类且拒绝任何SKIP。

```python
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import unittest

CASES = (
    "cap1_fork", "control_fork", "seatbelt_positive", "profile_error",
    "release_eof", "exec_error", "receipt_loss",
)
NORMAL = ("cap1_fork", "control_fork", "seatbelt_positive", "receipt_loss")
FIELDS = frozenset("""
kind version candidate_sha variant case kernel os_build arch translated binary_sha256
profile_sha256 sandbox_exec_sha256 observer_pid observer_uid pid start_sec start_usec uid gid
saved_uid saved_gid credentials_valid configured sandboxed quota_enabled
profile_enabled cur hard uid_count_at_barrier registered released kernel_exec
payload_started exec_errno entered normal_exit payload_pid
payload_cur payload_hard fd3_errno fd4_errno recover_uid_errno recover_gid_errno
groups group fork_pid fork_errno child_byte gate_canary_errno gate_canary_allowed
payload_canary_errno payload_canary_allowed wait_status exit_code term_signal
remaining cleanup_scope retained
""".split())

def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result

def started_state(kernel_exec, released, exec_errno):
    if kernel_exec == 1:
        return "true"
    if not released or exec_errno:
        return "false"
    return "unknown"

def delivered_state(confirmation):
    if confirmation is None:
        return "unknown"
    if confirmation not in ("false", "true", "unknown"):
        raise ValueError("invalid three-state value")
    return confirmation

def parse_delivery(raw):
    if len(raw) > 65536:
        raise ValueError("delivery size exceeded")
    launches, confirmations = {}, {}
    audit = None
    for line in raw.splitlines():
        row = json.loads(line, object_pairs_hook=unique_object)
        if audit is not None:
            raise ValueError("data after final audit manifest")
        kind = row.get("kind")
        if kind == "audit":
            if set(row) != {"kind", "version", "ledger_sha256", "root_directory", "retained"}:
                raise ValueError("audit schema mismatch")
            if row["version"] != 1 or row["retained"] is not True:
                raise ValueError("audit contract mismatch")
            if not re.fullmatch(r"[0-9a-f]{64}", row["ledger_sha256"]):
                raise ValueError("audit digest invalid")
            if not re.fullmatch(r"/private/var/icode-m0a1\.[A-Za-z0-9]+", row["root_directory"]):
                raise ValueError("root fixture target invalid")
            audit = row
            continue
        name = row.get("case")
        if name not in CASES or row.get("version") != 1:
            raise ValueError("delivery identity invalid")
        if kind == "launch":
            if set(row) != {"kind", "version", "case", "released"} or type(row["released"]) is not int:
                raise ValueError("launch schema invalid")
            if row["released"] not in (0, 1) or name in launches:
                raise ValueError("launch invalid or duplicated")
            if len(launches) >= len(CASES) or name != CASES[len(launches)]:
                raise ValueError("launch order invalid")
            launches[name] = row["released"]
        elif kind == "confirmation":
            if set(row) != {"kind", "version", "case", "payload_started"}:
                raise ValueError("confirmation schema invalid")
            if name not in launches or name in confirmations or name != next(reversed(launches)):
                raise ValueError("unsolicited or repeated confirmation")
            confirmations[name] = delivered_state(row["payload_started"])
        else:
            raise ValueError("unexpected delivery record")
    if tuple(launches) != CASES or audit is None:
        raise ValueError("delivery incomplete")
    views = {name: {"released": launches[name], "confirmation": confirmations.get(name),
                    "payload_started": delivered_state(confirmations.get(name))}
             for name in CASES}
    return views, audit

def bounded_json(path, bound):
    data = Path(path).read_bytes()
    if len(data) > bound:
        raise ValueError("evidence size exceeded")
    return json.loads(data, object_pairs_hook=unique_object)

def load_evidence(directory):
    directory = Path(directory)
    meta = bounded_json(directory / "metadata.json", 16384)
    delivery_raw = (directory / "native.stdout.jsonl").read_bytes()
    views, audit = parse_delivery(delivery_raw)
    if bounded_json(directory / "delivery-view.json", 4096) != views:
        raise ValueError("frozen delivery view differs from actual received bytes")
    if hashlib.sha256(delivery_raw).hexdigest() != meta["native_stdout_sha256"]:
        raise ValueError("delivery raw changed")
    raw = (directory / "native.audit.jsonl").read_bytes()
    if len(raw) > 65536:
        raise ValueError("native output size exceeded")
    if meta.get("truncated") or hashlib.sha256(raw).hexdigest() != meta["native_audit_sha256"]:
        raise ValueError("native audit export truncated or changed")
    lines = raw.splitlines(keepends=True)
    if len(lines) != len(CASES):
        raise ValueError("native evidence incomplete")
    objects = [json.loads(line, object_pairs_hook=unique_object) for line in lines]
    if hashlib.sha256(raw).hexdigest() != audit["ledger_sha256"]:
        raise ValueError("root ledger export hash mismatch")
    records = {}
    for name, row in zip(CASES, objects):
        if set(row) != FIELDS or row["case"] != name or row["kind"] != "case" or row["version"] != 1:
            raise ValueError("native case schema/order mismatch")
        if row["candidate_sha"] != meta["candidate_sha"] or row["arch"] != meta["arch"]:
            raise ValueError("native candidate/platform mismatch")
        if row["binary_sha256"] != meta["binary_sha256"] or row["variant"] != meta["variant"]:
            raise ValueError("native binary identity mismatch")
        if row["kernel"] != meta["kernel"] or row["os_build"] != meta["os_build"]:
            raise ValueError("native OS identity mismatch")
        for key in ("binary_sha256", "profile_sha256", "sandbox_exec_sha256"):
            if not re.fullmatch(r"[0-9a-f]{64}", row[key]):
                raise ValueError("native digest invalid")
        state = started_state(row["kernel_exec"], row["released"], row["exec_errno"])
        if row["payload_started"] != state:
            raise ValueError("native exec fact contradicted")
        if views[name]["released"] != row["released"]:
            raise ValueError("launch fact differs from root audit")
        if views[name]["confirmation"] is not None and views[name]["confirmation"] != state:
            raise ValueError("received confirmation differs from root audit")
        records[name] = row
    return meta, records, audit, views

class TestM0a1Protocol(unittest.TestCase):
    def test_no_release_is_false(self):
        self.assertEqual(started_state(0, 0, 0), "false")

    def test_exec_failure_is_false(self):
        self.assertEqual(started_state(0, 1, errno.ENOENT), "false")

    def test_eof_without_exec_evidence_is_unknown(self):
        self.assertEqual(started_state(0, 1, 0), "unknown")

    def test_native_exec_survives_receipt_loss(self):
        self.assertEqual(started_state(1, 1, 0), "true")
        wire = []
        for name in CASES:
            wire.append({"kind": "launch", "version": 1, "case": name, "released": 1})
            if name != "receipt_loss":
                wire.append({"kind": "confirmation", "version": 1, "case": name,
                             "payload_started": "true"})
        wire.append({"kind": "audit", "version": 1, "ledger_sha256": "0" * 64,
                     "root_directory": "/private/var/icode-m0a1.Protocol", "retained": True})
        views, _ = parse_delivery(("\n".join(json.dumps(row) for row in wire) + "\n").encode())
        self.assertIsNone(views["receipt_loss"]["confirmation"])
        self.assertEqual(views["receipt_loss"]["payload_started"], "unknown")
        self.assertEqual(views["cap1_fork"]["payload_started"], "true")

    def test_forged_or_invalid_receipt_rejected(self):
        with self.assertRaises(ValueError):
            delivered_state("SANDBOXED EXEC_OK")
        with self.assertRaises(ValueError):
            json.loads('{"version":1,"version":1}', object_pairs_hook=unique_object)

@unittest.skipUnless(os.environ.get("ICODE_M0A1_EVIDENCE"), "native evidence was not requested")
class TestNativeM0a1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform != "darwin":
            raise RuntimeError("macOS native evidence cannot be verified on another OS")
        cls.meta, cls.rows, cls.audit, cls.views = load_evidence(os.environ["ICODE_M0A1_EVIDENCE"])
        if cls.meta["native_exit"] != 0:
            raise RuntimeError("native driver failed, not semantic RED")

    def test_complete_native_identity_and_protocol(self):
        self.assertEqual(tuple(self.rows), CASES)
        self.assertEqual(len({r["uid"] for r in self.rows.values()}), len(CASES))
        for r in self.rows.values():
            with self.subTest(case=r["case"]):
                self.assertEqual(r["observer_uid"], 0)
                self.assertEqual(r["translated"], 0)
                self.assertGreater(r["observer_pid"], 0)
                self.assertGreater(r["pid"], 0)
                self.assertGreater(r["start_sec"], 0)
                self.assertGreaterEqual(r["uid"], 60000)
                self.assertLess(r["uid"], 61024)
                self.assertEqual(r["gid"], r["uid"])
                self.assertEqual(r["remaining"], 0)
                self.assertIs(r["retained"], True)
                self.assertEqual(r["cleanup_scope"], "owned_root_only")
        for name in NORMAL:
            r = self.rows[name]
            with self.subTest(case=name):
                for key in ("configured", "sandboxed", "credentials_valid", "registered",
                            "released", "kernel_exec", "entered", "normal_exit"):
                    self.assertEqual(r[key], 1, key)
                self.assertEqual(r["uid_count_at_barrier"], 1)
                self.assertEqual(r["payload_pid"], r["pid"])
                self.assertEqual(r["saved_uid"], r["uid"])
                self.assertEqual(r["saved_gid"], r["gid"])
                self.assertEqual(r["groups"], 1)
                self.assertEqual(r["group"], r["gid"])
                self.assertEqual(r["fd3_errno"], errno.EBADF)
                self.assertEqual(r["fd4_errno"], errno.EBADF)
                self.assertEqual(r["recover_uid_errno"], errno.EPERM)
                self.assertEqual(r["recover_gid_errno"], errno.EPERM)
                self.assertEqual(r["gate_canary_allowed"], 1)
                self.assertEqual(r["payload_canary_allowed"], 1)
                if r["profile_enabled"]:
                    self.assertIn(r["gate_canary_errno"], (errno.EPERM, errno.EACCES))
                    self.assertIn(r["payload_canary_errno"], (errno.EPERM, errno.EACCES))
                else:
                    self.assertEqual(r["gate_canary_errno"], 0)
                    self.assertEqual(r["payload_canary_errno"], 0)

    def test_positive_controls_really_execute(self):
        for name in ("control_fork", "seatbelt_positive"):
            r = self.rows[name]
            self.assertEqual(r["quota_enabled"], 0)
            self.assertGreater(r["fork_pid"], 0)
            self.assertEqual(r["fork_errno"], 0)
            self.assertEqual(r["child_byte"], 1)
            self.assertGreaterEqual(r["payload_cur"], 2)
        self.assertEqual(self.rows["control_fork"]["profile_enabled"], 1)
        self.assertEqual(self.rows["seatbelt_positive"]["profile_enabled"], 0)

    def test_cap1_quota_semantic(self):
        for name in ("cap1_fork", "receipt_loss"):
            r = self.rows[name]
            self.assertEqual(r["fork_errno"], errno.EAGAIN, "M0A1_QUOTA_REJECTION")
            self.assertEqual(r["fork_pid"], -1)
            self.assertEqual(r["child_byte"], 0)
            self.assertEqual(r["quota_enabled"], 1)
            self.assertEqual((r["cur"], r["hard"]), (1, 1))
            self.assertEqual((r["payload_cur"], r["payload_hard"]), (1, 1))

    def test_no_payload_before_release(self):
        for name in ("profile_error", "release_eof"):
            r = self.rows[name]
            self.assertEqual(r["configured"], 1)
            self.assertEqual(r["released"], 0)
            self.assertEqual(r["kernel_exec"], 0)
            self.assertEqual(r["entered"], 0)
            self.assertEqual(r["payload_started"], "false")
        self.assertEqual(self.rows["profile_error"]["sandboxed"], 0)
        self.assertEqual(self.rows["release_eof"]["sandboxed"], 1)
        self.assertEqual(self.rows["release_eof"]["exec_errno"], errno.ECANCELED)

    def test_exec_failure_and_lost_delivery_distinct(self):
        failed = self.rows["exec_error"]
        self.assertEqual(failed["released"], 1)
        self.assertEqual(failed["kernel_exec"], 0)
        self.assertEqual(failed["exec_errno"], errno.ENOENT)
        self.assertEqual(failed["entered"], 0)
        self.assertEqual(failed["payload_started"], "false")
        lost = self.rows["receipt_loss"]
        self.assertEqual(lost["kernel_exec"], 1)
        self.assertEqual(lost["entered"], 1)
        self.assertEqual(lost["payload_started"], "true")
        self.assertIsNone(self.views["receipt_loss"]["confirmation"])
        self.assertEqual(self.views["receipt_loss"]["payload_started"], "unknown")
        for name in CASES:
            if name != "receipt_loss":
                self.assertEqual(self.views[name]["confirmation"], self.rows[name]["payload_started"])
```

### 8.6 TESTOnly驱动设施：native/mac/CMakeLists.txt

不安装/service，不生成TEST代码。CommonCryptoSDK接口弃用警告单独禁用，其他Wall/Wextra/Werror保留；只使用系统接口，不新增hash包。

```cmake
cmake_minimum_required(VERSION 3.20)
project(icode_m0a1_experiment C)
if(NOT APPLE OR NOT CMAKE_SYSTEM_NAME STREQUAL "Darwin")
  message(FATAL_ERROR "M0a1 requires native macOS")
endif()
if(NOT CMAKE_SYSTEM_PROCESSOR MATCHES "^(arm64|x86_64)$")
  message(FATAL_ERROR "M0a1 requires a supported native architecture")
endif()
option(M0_BUILD_SOURCE "Build the independently reviewed exact quota primitive" OFF)
function(m0_target name implementation)
  add_executable(${name} tests/icode_m0a1_driver.c ${implementation})
  target_include_directories(${name} PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
  set_target_properties(${name} PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED YES C_EXTENSIONS NO)
  target_compile_options(${name} PRIVATE -Wall -Wextra -Werror -Wno-deprecated-declarations)
endfunction()
m0_target(icode_m0a1_baseline tests/icode_m0a1_baseline.c)
if(M0_BUILD_SOURCE)
  if(NOT EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/icode_m0a1_limit.c")
    message(FATAL_ERROR "SOURCE primitive is absent; do not call this semantic RED")
  endif()
  m0_target(icode_m0a1_source icode_m0a1_limit.c)
endif()
```

### 8.7 TESTOnly非特权控制器：scripts/run_macos_m0_ci.py

先记录rawnative日志/exitstatus，后跑正式unittest；RED只认可一个指定quota断言FAIL且实际baselinefork成功，禁止把ERROR/SKIP/缺证据算RED。每个阶段独立manifest，baseline+SOURCE在同candidate重复验证反例。nativestderr保留原始有限systemtool错误，仅作日志不作启动确认。

```python
import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import sys
import unittest

def checked_text(argv, cwd):
    p = subprocess.run(argv, cwd=cwd, check=True, capture_output=True, timeout=15)
    if len(p.stdout) > 4096 or p.stderr:
        raise RuntimeError("unexpected identity command output")
    return p.stdout.decode("utf-8").strip()

def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

def run_suite(suite, path):
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    report = stream.getvalue()
    if len(report.encode("utf-8")) > 65536:
        raise RuntimeError("test output exceeded")
    path.write_text(report, encoding="utf-8")
    print(report, end="")
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase", choices=("red", "green"), required=True)
    parser.add_argument("--expected-arch", choices=("arm64", "x86_64"), required=True)
    args = parser.parse_args()
    if sys.platform != "darwin" or os.getuid() == 0:
        raise RuntimeError("controller requires nonroot native macOS")
    repo = Path(__file__).resolve().parents[1]
    temporary = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    output = args.output.absolute()
    build = args.build_dir.resolve(strict=True)
    if output.is_symlink() or output.exists() or output.parent.resolve() != temporary:
        raise RuntimeError("output must be a fresh direct child of RUNNER_TEMP")
    if build.parent != temporary or not build.is_dir():
        raise RuntimeError("build must be a direct child of RUNNER_TEMP")
    output.mkdir(mode=0o700)
    metadata = {"phase": args.phase, "native_exit": None, "cleanup": "unknown"}
    try:
        sha = checked_text(["git", "rev-parse", "HEAD"], repo)
        if not re.fullmatch("[0-9a-f]{40}", sha) or sha != os.environ["GITHUB_SHA"]:
            raise RuntimeError("actual candidate SHA differs from GitHub candidate")
        arch = platform.machine()
        if arch != args.expected_arch:
            raise RuntimeError("runner label did not deliver expected native architecture")
        variant = "baseline" if args.phase == "red" else "source"
        binary = build / ("icode_m0a1_" + variant)
        if binary.is_symlink() or not binary.is_file() or not os.access(binary, os.X_OK):
            raise RuntimeError("native binary missing; not semantic RED")
        binary = binary.resolve(strict=True)
        if binary.parent != build:
            raise RuntimeError("native binary escaped build directory")
        image = binary.read_bytes()
        if not 0 < len(image) <= 16 * 1024 * 1024:
            raise RuntimeError("native binary size invalid")
        digest = hashlib.sha256(image).hexdigest()
        artifact_sources = (
            "native/mac/icode_m0a1_limit.h",
            "native/mac/tests/icode_m0a1_baseline.c",
            "native/mac/tests/icode_m0a1_driver.c",
            "tests/test_macos_task_quota_probe.py",
            "native/mac/CMakeLists.txt",
            "scripts/run_macos_m0_ci.py",
            ".github/workflows/ci.yml",
            "docs/nbl/specs/2026-10-13-macos-task-identity-quota-design.md",
            "docs/nbl/plans/2026-10-13-macos-task-identity-quota-m0.md",
        )
        source_hashes = {p: hashlib.sha256((repo / p).read_bytes()).hexdigest() for p in artifact_sources}
        if variant == "source":
            p = "native/mac/icode_m0a1_limit.c"
            source_hashes[p] = hashlib.sha256((repo / p).read_bytes()).hexdigest()
        metadata.update({
            "candidate_sha": sha, "variant": variant, "binary_sha256": digest,
            "arch": arch, "kernel": platform.release(),
            "os_build": checked_text(["/usr/bin/sw_vers", "-buildVersion"], repo),
            "os_version": checked_text(["/usr/bin/sw_vers", "-productVersion"], repo),
            "run_id": os.environ["GITHUB_RUN_ID"], "job": os.environ["GITHUB_JOB"],
            "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
            "source_hashes": source_hashes,
        })
        if arch == "x86_64" and metadata["os_version"].split(".")[0] != "15":
            raise RuntimeError("Intel target is explicitly macOS 15")
        write_json(output / "metadata.json", metadata)
        argv = ["/usr/bin/sudo", "-n", "--", "/usr/bin/env", "-i",
                "PATH=/usr/bin:/bin", str(binary), sha, digest]
        try:
            native = subprocess.run(argv, cwd="/", capture_output=True, timeout=135, check=False)
        except subprocess.TimeoutExpired as exc:
            (output / "native.stdout.jsonl").write_bytes((exc.stdout or b"")[:65536])
            (output / "native.stderr.log").write_bytes((exc.stderr or b"")[:65536])
            metadata.update({"native_exit": "timeout", "cleanup": "unknown", "truncated": True})
            raise RuntimeError("native timeout; retained targets unknown, never RED")
        (output / "native.stdout.jsonl").write_bytes(native.stdout[:65536])
        (output / "native.stderr.log").write_bytes(native.stderr[:65536])
        metadata.update({
            "native_exit": native.returncode,
            "native_stdout_sha256": hashlib.sha256(native.stdout).hexdigest(),
            "native_stderr_sha256": hashlib.sha256(native.stderr).hexdigest(),
            "truncated": len(native.stdout) > 65536 or len(native.stderr) > 65536,
        })
        write_json(output / "metadata.json", metadata)
        if native.returncode or metadata["truncated"]:
            raise RuntimeError("native infrastructure failure; preserve raw evidence, not RED")
        os.environ["ICODE_M0A1_EVIDENCE"] = str(output)
        test_path = repo / "tests/test_macos_task_quota_probe.py"
        spec = importlib.util.spec_from_file_location("m0a1_frozen_tests", test_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("formal TEST module unavailable")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        protocol = run_suite(unittest.defaultTestLoader.loadTestsFromTestCase(module.TestM0a1Protocol),
                             output / "protocol-tests.log")
        if not protocol.wasSuccessful() or protocol.skipped or protocol.testsRun != 5:
            raise RuntimeError("portable protocol gate failed")
        # Freeze the actual delivery interpretation BEFORE opening any audit
        # file. No case name or unseen root exec fact supplies a receipt.
        views, manifest = module.parse_delivery(native.stdout)
        write_json(output / "delivery-view.json", views)
        root_directory = Path(manifest["root_directory"])
        root_stat = root_directory.lstat()
        if (not stat.S_ISDIR(root_stat.st_mode) or root_stat.st_uid != 0
                or stat.S_IMODE(root_stat.st_mode) != 0o755):
            raise RuntimeError("protected audit directory identity invalid")
        fd = os.open(root_directory / "native.jsonl", os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != 0
                    or stat.S_IMODE(before.st_mode) != 0o444 or before.st_nlink != 1
                    or not 0 < before.st_size <= 65536):
                raise RuntimeError("protected audit file identity invalid")
            chunks = []
            total = 0
            while total <= 65536:
                chunk = os.read(fd, min(4096, 65537 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
            after = os.fstat(fd)
            if (total > 65536 or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                    != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
                raise RuntimeError("audit changed or exceeded size bound")
            audit_raw = b"".join(chunks)
        finally:
            os.close(fd)
        if hashlib.sha256(audit_raw).hexdigest() != manifest["ledger_sha256"]:
            raise RuntimeError("independent root audit export digest differs")
        (output / "native.audit.jsonl").write_bytes(audit_raw)
        metadata["native_audit_sha256"] = hashlib.sha256(audit_raw).hexdigest()
        write_json(output / "metadata.json", metadata)
        meta, rows, audit, frozen_views = module.load_evidence(output)
        formal = run_suite(unittest.defaultTestLoader.loadTestsFromTestCase(module.TestNativeM0a1),
                           output / "native-tests.log")
        metadata["protocol_ledger"] = {"passed": protocol.testsRun, "errors": 0, "skipped": 0}
        metadata["native_ledger"] = {
            "tests": formal.testsRun, "failures": len(formal.failures),
            "errors": len(formal.errors), "skipped": len(formal.skipped),
            "root_ledger_sha256": audit["ledger_sha256"], "root_directory": audit["root_directory"],
        }
        if formal.errors or formal.skipped or formal.testsRun != 5:
            raise RuntimeError("formal native suite incomplete; not RED")
        if args.phase == "red":
            failures = formal.failures
            observed = rows["cap1_fork"]
            if (len(failures) != 1 or failures[0][0]._testMethodName != "test_cap1_quota_semantic"
                    or "M0A1_QUOTA_REJECTION" not in failures[0][1]
                    or observed["fork_pid"] <= 0 or observed["fork_errno"] != 0
                    or observed["child_byte"] != 1 or observed["payload_cur"] < 2):
                raise RuntimeError("RED must be the genuine fork-success quota assertion")
            metadata["result"] = "semantic_RED_confirmed"
        elif not formal.wasSuccessful():
            raise RuntimeError("SOURCE native GREEN failed")
        else:
            metadata["result"] = "M0a1_GREEN_only"
        metadata["cleanup"] = "owned_root_reaped; targets_and_UIDs_retained; no_full_tree_credit"
        write_json(output / "metadata.json", metadata)
        return 0
    except Exception as exc:
        metadata["result"] = "ERROR_or_unaccepted_failure"
        metadata["error"] = str(exc)
        write_json(output / "metadata.json", metadata)
        raise

if __name__ == "__main__":
    raise SystemExit(main())
```

### 8.8 必要有限CI接线：.github/workflows/ci.yml 的 jobs 下新增

只在已审候选main的push/明确workflowdispatch上运行，不在未审PR运行root实验。TESTOnly候选没有SOURCE时只有正式RED信用；SOURCE存在时GREEN步骤必须执行且通过，跳过GREEN不能报告M0a1通过。红/绿都用同一冻结TEST资产；rawbuild/native/unittest日志与退出状态均保留。不是产品安装/服务。

```yaml
  macos-m0a1-finite:
    name: M0a1 finite native RED and SOURCE (${{ matrix.os }})
    if: github.ref == 'refs/heads/main' && (github.event_name == 'push' || github.event_name == 'workflow_dispatch')
    runs-on: ${{ matrix.os }}
    timeout-minutes: 10
    permissions:
      contents: read
    strategy:
      fail-fast: false
      matrix:
        include:
          - os: macos-latest
            arch: arm64
          - os: macos-15-intel
            arch: x86_64
    steps:
      - name: Check out exact candidate
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
        with:
          persist-credentials: false
          submodules: recursive
      - name: Set up nonroot controller Python
        uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97
        with:
          python-version: "3.11"
      - name: Build the TESTOnly wrong baseline without SOURCE
        shell: bash
        run: |
          set -euo pipefail
          cmake -S native/mac -B "$RUNNER_TEMP/icode-m0a1-build" -DM0_BUILD_SOURCE=OFF 2>&1 | tee "$RUNNER_TEMP/icode-m0a1-configure.log"
          cmake --build "$RUNNER_TEMP/icode-m0a1-build" --parallel 1 2>&1 | tee "$RUNNER_TEMP/icode-m0a1-build.log"
      - name: Prove formal native semantic RED, positive controls and protocol
        shell: bash
        run: >-
          python scripts/run_macos_m0_ci.py
          --build-dir "$RUNNER_TEMP/icode-m0a1-build"
          --output "$RUNNER_TEMP/icode-m0a1-red"
          --phase red --expected-arch "${{ matrix.arch }}"
      - name: Build the independently reviewed SOURCE if present
        if: hashFiles('native/mac/icode_m0a1_limit.c') != ''
        shell: bash
        run: |
          set -euo pipefail
          git ls-files --error-unmatch native/mac/icode_m0a1_limit.c
          cmake -S native/mac -B "$RUNNER_TEMP/icode-m0a1-build" -DM0_BUILD_SOURCE=ON 2>&1 | tee "$RUNNER_TEMP/icode-m0a1-source-configure.log"
          cmake --build "$RUNNER_TEMP/icode-m0a1-build" --parallel 1 2>&1 | tee "$RUNNER_TEMP/icode-m0a1-source-build.log"
      - name: Require formal SOURCE native GREEN if present
        if: hashFiles('native/mac/icode_m0a1_limit.c') != ''
        shell: bash
        run: >-
          python scripts/run_macos_m0_ci.py
          --build-dir "$RUNNER_TEMP/icode-m0a1-build"
          --output "$RUNNER_TEMP/icode-m0a1-green"
          --phase green --expected-arch "${{ matrix.arch }}"
      - name: Preserve bounded exact-candidate native evidence on success or failure
        if: always()
        uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02
        with:
          name: m0a1-${{ github.sha }}-${{ matrix.arch }}-${{ github.run_attempt }}
          if-no-files-found: error
          retention-days: 14
          path: |
            ${{ runner.temp }}/icode-m0a1-red/
            ${{ runner.temp }}/icode-m0a1-green/
            ${{ runner.temp }}/icode-m0a1-configure.log
            ${{ runner.temp }}/icode-m0a1-build.log
            ${{ runner.temp }}/icode-m0a1-source-configure.log
            ${{ runner.temp }}/icode-m0a1-source-build.log
            ${{ runner.temp }}/icode-m0a1-build/icode_m0a1_baseline
            ${{ runner.temp }}/icode-m0a1-build/icode_m0a1_source
```

main-only提交/推送仍由root在对应fresh审查、本机密钥/固定子仓完整性与必要针对性检查后执行；此PLAN写作不提交、不修改CI。现有concurrency未改；旧候选未结束不新push覆盖。若SOURCE不存在，CIjobsuccess仅表示TESTOnly语义RED确认，M0a1_GREEN_only证据缺失，阶段不完成。

## 9. 作者 SPEC / QUALITY 自审与待验边界

SPEC自审：DESIGN§1真实缺口/原入口→§0；§3/§5可信native/全面降权/同PID→§2及§8.3；§5/§8首slicequota/启动事实→§8.2–8.5；其余knownvectors/fault→§2.3/§3 M0a2原清单全部保留；身份/代启动/注入→§4M0b阻断原条件保留；候选/平台/原日志→§8.7/8.8及Task4/5。M0a1只授必要前提，无完整M0/90%/安装/broker信用；没有把未冻结的后续向量写成已完成。

QUALITY自审：原partialPLAN的Q1/Q3在M0a1文档资产范围已补齐：完整C/driver/baseline/SOURCE/TEST/controller/CMake/CI均列，TEST不依赖尚未存在的SOURCE；RED只认可nativefork真实成功后的指定正式assertionFAIL，API/编译/权限/缺日志/SKIP均ERROR。45b033 的 C0/I2/M2 不合格结果保留：组语义已绑定新 DESIGN，delivery 已分通道且真实丢弃 confirmation、controller 先实际 missing → unknown 落盘再读 audit，Task2 名称与只读 marker 文案已同步。作者再次静态核2段PythonAST、六个C块括号、native audit与TEST白名单58字段一致及diffcheck；不执行本文Python/native资产。修订结果仍需freshSPEC→不同QUALITY，不自授C0/I0/M0独立审查通过。**完整阶段BLOCKED：**M0a2资产尚未冻结、M0b有效正控未冻结，全部原要求保留，不能启动M1。

【架构级自检报告】

- 语法/编译：实际静态解析本文两段Python资产AST通过；六个C块文本括号配对通过，native audit/TEST白名单58字段一致；文档diffcheck零诊断。CMake/C/CI为文档资产，未调用macOS编译/运行，真实SDK编译与job退出状态仍待原生验收。
- 依赖/调用链：现行native风格/CI/Seatbelt已读取；M2调用链接线不在本片。
- 逻辑/边界：首slice7case与正式RED/GREEN、有限ROOT/childCPU/wall/log/process、O_EXCL不复用、startidentity/savedcredentials/barrier已完整列；cap2/其他fault/逃逸向量明确后续阻断而非首slice通过。
- 异常处理：preexec失败、exec错误、postexec真实 delivery 丢 confirmation 而 audit 保留 exec 的分账已列；controller 缺确认返回 unknown，不按 case 名赋值；未实际运行。
- 关联模块：仅本PLAN文件写入；native/tests/source/vendor/CI/系统状态未修改。
- 兼容安全：不授完整M0/M1/ready/90%；不解除profile/扩大权限或添加service；group例外与不重用保留。
- 可运行性：M0a1完整资产可进入独立文档双审；真实nativeAPI/编译/运行未验，不写100%通过；M0a2/M0b/完整M0/M1均待验。

---
**Execution Mode:** serial

本次任务明确只写PLAN，不调用执行技能启动开发。freshSPEC→不同QUALITY通过后分阶段交接完整M0a1资产；TESTOnly正式语义RED先于不同作者SOURCE；M0a2/M0b保留完整M0目标与阻断。最终PLANhash在root交接/审查artifact记录，不自嵌文件以避免selfhash循环。
