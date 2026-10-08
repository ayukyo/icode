# Linux 根命令与后代配额接线

依据用户已确认的 [RL-0](./2026-10-08-r2-process-limit-contract.md)，继续现有 [RL-1 计划](../plans/2026-09-28-r2-resource-limit-and-violation-receipt.md)。本设计细化已有 cgroup 候选，不新增管理员安装、常驻服务、全局 controller 配置或用户级 RLIMIT。

## 已核对的问题与复用

`SandboxPolicy.process_limit` 尚未进入 `execution_broker → Landlock helper → namespace PID1 → fork(payload)`。把整个 helper 包在 `TasksMax=N` 中会计入 launcher/PID1，违背已确认合同。继续复用 namespace/PDEATHSIG 清理、默认网络拒绝、USER_NOTIF/lease 认证端点和现有策略调用链；不另建进程树回收系统。

## 选择

采用每命令随机独占用户级 transient scope（`Delegate=pids`），其内分为 `supervisor` 和 `payload` 两个 leaf。broker/observer 在 scope 外；launcher/PID1 在 supervisor；仅 payload 使用 `pids.max=policy.process_limit`。PID1 在已有 fork 点使用 `clone3(CLONE_INTO_CGROUP)` 原子创建根 payload，创建时即计 1，线程与后代继承限额。不能退回普通 fork 后迁移或加入 helper 补偿值。

只使用主机已存在的用户 manager 与委托；无用户 bus、非 cgroup v2、未实际取得 pids、配置/readback/clone3 失败时，命令启动前失败关闭。不得接管当前 IDE/app scope，不要求用户手工传 cgroup 路径，也不接受模型/项目提供 unit、FD 或 root。临时 scope 名由 broker 生成，固定 `icode-task-<32 lower hex>.scope`。

## 分片实现边界

1. **原生配额内核组件**：单独 `native/linux/icode_task_quota.h`，不接 CLI。内部接口 `icode_task_quota_prepare(unit, limit, state)` 检查合法 unit、当前唯一进程所在的正确 scope、cgroup2 文件系统/UID/非链接路径、controller 与新建节点；创建前拒绝所有既有子 cgroup（包括空子组），不能把根 procs 唯一当作子树独占；将自己移入新建 supervisor，创建空 payload，写入并读回 pids.max。`icode_task_quota_fork(state)` 使用 clone3，子进程立即关闭全部管理 FD。`icode_task_quota_finish(state)` 只在确认自己的 payload leaf 为空且目录身份未变时回收；关闭 FD 不等于清理成功。阶段只验证组件，不修改评分或调用入口。
2. **helper 与可信启动通道**：将组件接到 namespace PID1；保留现有 FD 身份验证，同时新增私有 resource channel。所有 cgroup 管理 FD 在 exec 前关闭，Landlock 不增加 `/sys` 授权。setup 拒绝、确认 exec 和丢失通道分别表达 false/true/unknown，不能由退出码猜测 `payload_started=false`。只有固定的 native 握手允许主机归一化结果；用户 stdout/stderr 不能伪造。
3. **真实命令链**：policy 经 ToolContext、broker 转为独占 scope 与原生限制。管理工具为固定受信路径，环境只传必要的当前 UID 用户 bus 参数；payload 不继承这些管理环境。普通未绑定 R2 策略的旧调用保持兼容，不提供“忽略配额”的生产开关。系统工具错误不得作为用户 payload 输出泄露；确认未启动返回固定 unsupported/setup failure。
4. **生命周期与验收**：在正常、超时、输出超限、取消、异常、host SIGKILL 和 setsid 后代下验证 namespace 回收及 scope/leaf 收束。host 崩溃时不能依赖 Python finally；进程清理和空目录/manager unit 回收分开核实。失败的 partial setup 只处理本次已创建节点，禁止广泛扫描删除。

scope launcher 必须采用固定 description，避免 manager 将用户 argv 当描述保存，并要求失败任务也回收单元。systemd v257 固定 [man/systemd-run.xml](https://github.com/systemd/systemd/blob/70bae7648f2c18010187c9cf20093155eaa26029/man/systemd-run.xml) 的 `--collect` 对应 transient unit `CollectMode=inactive-or-failed`，不等于吞掉命令失败；禁止 `--ignore-failure`。`--expand-environment=no` 在 v254 才引入，不能无条件传给本机 v249；生产接线须验证旧 scope 的 literal argv 或新版本显式禁扩展，缺证据失败关闭，不依据未来默认行为猜测。

## 组件 API 与错误合同

状态拥有 root/supervisor/payload FD、各自目录身份和 limit；初始化为 FD=-1。prepare/fork/finish 返回正常值或 -1/errno，不打印路径/原生错误。finish 不杀不属于自己的进程、不删除 scope 根或 supervisor（调用者仍在其中，交给 manager 在退出后收束）。拒绝重复 prepare、非整数/越界 cap、已存在节点、不匹配 unit/UID/文件系统、controller/readback 不完整；任一步失败不产生 payload。fork 无无配额回退。

组件输入范围为 1..INT_MAX，但内核 pids.max 还存在自身可表示范围：输入合法不代表主机能设置成功，必须精确写入并读回原数值。内核拒绝或读回 `max` 一律启动前失败，禁止截断、放大或变成 unlimited。`Delegate=no` 元数据也不自动撤销祖先已有的文件权限；组件判断实际 cgroup 权限/controller，生产 broker 仍只能新建明确 `Delegate=pids` 的自有 scope。不可写负控只改本次随机 scope 的目录 mode 并恢复，不改变全局委托配置。

## 验收

组件真实 cap=2 根+一后代正例、cap=1 fork/线程无 marker 负例、父/监督进程不在 payload leaf、pids.events 增量；无 scope/错误 unit/错误 cap 在创建 payload 前拒绝、既有目录不覆盖、FD 关闭、payload 身份改变或仍 populated 时不误回收。随后必须以真实 Agent/workbench 命令再次证明这些属性及两个并发命令独立计数。环境 SKIP、raw 组件、临时脚本或交叉构建都不计 `resource_limits` 分数。

## 2026-10-08 本机可行性，不是生产证明

Ubuntu kernel 6.8.0-138 / systemd 249，当前 app scope 为 Delegate=no；user manager 已获 memory/pids 委托。使用临时独占 user scope 的低负载脚本创建 supervisor/payload，clone3 原子入组，cap=2 fork 成功、cap=1 EAGAIN，pids.events max=1，监督进程不在 payload。脚本完成后 unit not-found/inactive、scope 目录不存在。此脚本没有 namespace/Landlock/工单接线，`conformance_credit=none`。

独立组件 TDD：header 存在断言 RED，deny-only stub 编译成功但真实 cap=2 正控 RED，配额被外部修改后的启动负控 RED；随后实现转 GREEN。本机 `tests.test_linux_task_quota` 13/13、两次各 20 轮 260/260、0 SKIP；C11 `-Wall -Wextra -Werror -fanalyzer` 通过。涵盖 cap=1 fork/线程拒绝、事件计数、cap=2 根和后代、管理 FD 关闭、重复 prepare、错误 unit/cap、碰撞、非独占、不可写 scope、INT_MAX 精确设置或启动前拒绝、修改配额、非空/替换不误删及 close 不冒充 finish。此组件仍未接 namespace/Landlock 或真实命令入口，不计资源分；全仓门禁和独立 SPEC/QUALITY 另行记录。

独立 SPEC 真实复现初版漏检：根 procs 唯一，但既有 `other` 子组仍有进程时 prepare 错误接受。补充既有空/带进程子组两项，旧版分别 RED，新增创建前目录枚举后 15/15、20 轮 300/300、0 SKIP；负控检查原节点身份、成员、根组成员与 controller 均未变。独立 SPEC 重核、独立 QUALITY、修复冻结后的完整 preflight 3/3 通过；其余生命周期和产品门仍未验收，不将组件正例算作独占工单命令链通过。

## 并行研究与许可

采纳 Linux v6.17 `e5f0a698b34ed76002dc5cff3804a61c80233a7a` 的系统原语：[pids 在 task 创建前收费](https://github.com/torvalds/linux/blob/e5f0a698b34ed76002dc5cff3804a61c80233a7a/kernel/cgroup/pids.c#L146-L184)、[clone3 原子入组与权限](https://github.com/torvalds/linux/blob/e5f0a698b34ed76002dc5cff3804a61c80233a7a/kernel/cgroup/cgroup.c#L6196-L6248)。源码 GPL-2.0-only，仅调用内核 ABI，不复制实现。

采纳 systemd v257 `70bae7648f2c18010187c9cf20093155eaa26029` 的 [delegation/single-writer](https://github.com/systemd/systemd/blob/70bae7648f2c18010187c9cf20093155eaa26029/docs/CGROUP_DELEGATION.md#L169-L211)，文档 LGPL-2.1-or-later；不复制实现，不新增 Python dependency。暂缓任何需要新 root 部署的方案。Codex 的 session soft cap 与 UID 全局 rlimit 不适配 RL-0（已有固定快照记录见持续竞品对照）。

### 同日：私有回执与 scope 启动接线研究

采纳 Codex [`1fbe15c` 的 FD 生命周期](https://github.com/openai/codex/blob/1fbe15c962cc3d8eabec36d67987c83cfc4eeec9/codex-rs/linux-sandbox/src/proxy_lifecycle.rs#L51-L86)中 CLOEXEC、截断拒绝、精确 FD 数量与失败关闭机制（Apache-2.0）；复用本仓 namespace/PDEATHSIG/parent pipe，不复制上游代码。新增 resource endpoint 必须与既有 proxy/violation endpoint 成对白名单，不能把任意 FD 放行或将 cgroup 管理 FD 传给 payload。

CPython [`v3.12.10 _posixsubprocess.c`](https://github.com/python/cpython/blob/v3.12.10/Modules/_posixsubprocess.c)的 exec-error pipe 可用于明确 pre-exec 错误；**不适配**把 CLOEXEC pipe EOF 当作成功 exec：成功 exec、pre-exec SIGKILL 或其它未写错误的退出均可能关闭 writer。READY/ACK 也只证明 exec 前状态。丢通道保留 unknown；若以后必须证明任意短命令的 exec=true，内核 exec 事件观察只是待验证候选，不能未经 LSM/信号/reap/兼容性验收直接引入。

Linux [unix(7)](https://man7.org/linux/man-pages/man7/unix.7.html)中 SO_PEERCRED 是连接/socketpair 建立时凭据，不能当作 fork 后每帧写入者身份。逐消息身份应使用 SO_PASSCRED/SCM_CREDENTIALS 并处理 PID namespace 可见性；nonce 仅关联与防重放，不替代身份及端点所有权。现 helper 的 namespace 前 host-parent 校验继续保留。

systemd [`v249 / f6278558da0304ec6b646bb172ce4688c7f162a5`](https://github.com/systemd/systemd/blob/f6278558da0304ec6b646bb172ce4688c7f162a5/src/run/run.c)与 [`v254 / 994c7978608a0bd9b317f4f74ff266dd50a3e74e`](https://github.com/systemd/systemd/blob/994c7978608a0bd9b317f4f74ff266dd50a3e74e/src/run/run.c)均以 scope 注册自身 PID 后直接 exec，不经 shell；v254 新增环境展开选项。采纳受信固定路径、固定 description、随机 unit、--collect、--no-ask-password；v249 不传不支持的选项，v254+ 显式禁环境展开（LGPL-2.1-or-later，仅借机制）。broker 接线必须真实核对 `$X`、`${X}`、`$$`、空格、前导 dash 和 FD 通过，不能仅靠版本字符串或 argv mock；--collect 不是进程/目录回收证明。以上研究未改变产品入口、评分或自动模式。

## helper 分片验证合同与调用链上限

本片只把原生 CLI 的 unit/limit 交给已验收组件，并在 namespace PID1 原子创建 payload；不声称 policy→ToolContext→broker 已完成。验收环境为本机非 root 用户、既有 user manager、cgroup v2 与真实 Landlock/user/PID namespace；基线 main `02685069466cbe14fecb9f6acac310baef8c2e43` 上的 helper 补丁，安装验收必须绑定新构建 wheel 内的真实 helper。源码 probe 不替代安装产物或其它架构证据。

| 边界/消费者 | 原始合同与观察 | 必需层 / 验收项 |
|---|---|---|
| CLI→prepare | 严格成对随机 unit、1..INT_MAX decimal；当前 scope 独占 | static＋host：缺失、重复、非法、错误 scope 在 payload 前拒绝 |
| prepare→namespace→PID1 | host UID 下配置；namespace 后仅根 payload 原子入 charged leaf | host：映射与 mapless、cap=2 根＋后代成功、supervisor 两进程在额度外 |
| pids controller→后代 | Linux task/TID，setsid 不改变继承；精确 readback | host：cap=1 fork/线程 EAGAIN、无超额 marker、事件增量及真实 membership |
| payload→exec | 关闭管理 FD，不新增 /sys 读写；旧无 quota 原生诊断兼容 | host：FD/文件边界、既有 PID namespace/mapless/host-crash 回归 |
| wait(init)→finish→manager | 只删除本次身份匹配、已空 payload；close≠finish | host：正常/exit13、namespace/map/clone 失败；精确 unit 与 scope 消失 |
| sdist→wheel→干净 pip | 编译依赖 header 在 sdist，安装者无需 C 编译器 | build＋deploy＋host：归档包含 header，安装包内真实 helper 正负控 |
| ToolContext→broker | process_limit 尚未接这条产品链 | unknown：私有通道、并发命令、取消/超时/host-crash 后目录收束另验 |

上述边界属于单个原生接线分片，覆盖数按其实际正负场景记录，不用整个工程符号数量虚构已覆盖链路。Windows 新 SHA 的 license_tests failure 与 macOS 新身份授权缺口是独立问题；不能通过 Linux 本机成功抵消。阶段 verdict 仅可为 helper partially_verified/host_verified，R2 resource_limits、完整调用链及 R2/R3 readiness 保持未通过；主代理在填写结果前独立复核行为与产物。

### 本机冻结验证记录

helper 接线仅变更 `icode_landlock.c`、MANIFEST 与新测试。14 方法含显式 mapless cap1 fork/线程、cap2 setsid；实施者和主代理分别 20 轮 280/280、0 SKIP。额外默认 cap2 实测 UID=0、显式 mapless cap2 UID=65534；其余默认用例允许两模式，不外推全部 mapped 组合。独立 SPEC 在项目 Python 3.11.15 下 79/79 真实通过、0 SKIP；初次误用不符合项目要求的系统 Python 3.10 已定位为 hashlib.file_digest 缺失，不冒充回归或通过证据。独立 QUALITY 完整回读 helper/header/测试与分发声明，另跑 14 项真实 quota 与 7 项 resolver 回归通过、0 SKIP，无遗留问题；未增加 broker/资源私有通道。

主代理构建 sdist＋wheel、核对 header 在归档、真实从 sdist 再构建 wheel，并在干净 venv pip 安装。两种构建的 helper 均 942336 bytes、SHA-256 `96abe96cc750f524388eaa864274be59db6340c2fb5fee0416466e4a404062ad`，逐字节相等；C 源冻结 SHA-256 `c7e207018dbde21e32d16d4a34a08bd09ddceefb895d075ad7d6873e8b6c7913`。安装包内 helper 的 cap1 fork/线程、cap2 根＋setsid 后代及第三 task 拒绝、exit13 精确保留均实际通过，检查 pids.max/current/events、两 supervisor 在额度外、管理 FD 关闭、/sys 拒绝和本次 unit/scope 消失。无 scope/unpaired/zero-cap 三项安装负控没有 payload marker。

原有安装包十阶段（含 USER_NOTIF 回执、host-crash namespace 清理、lease expiry、Git broker）通过，冻结生产源码完整 preflight 密钥/子模块/全仓 unittest 三道通过。安装回归中旧 host-crash 未启用新 quota，不能写成新配额生命周期通过。当前允许结论为 native helper/安装产物 host_verified；其它架构、真实工单 broker、并发、超时/取消/host-crash 的新 scope 收束仍待验，`conformance_credit=none`。

## 下一分片：私有资源事实回执（不接产品入口）

增加只供可信 launcher 的 resource endpoint，与既有 violation/proxy FD 严格不同；继承白名单最多两端点，所有其余 FD 关闭。模型 schema 不增加 unit/FD/nonce 参数。外 launcher 是唯一 host-facing writer，PID1/payload 关闭此副本；host socket 启用 SO_PASSCRED，逐帧匹配实际 Popen PID 及 host UID/GID，不能用 SO_PEERCRED 的 creator 凭据冒充逐帧身份。

resource 初始化必须显式设置并核对 FD_CLOEXEC（Popen.pass_fds 会清除此标志）；PID1 的关闭失败必须写专用 pre-exec 错误并退出，不能继续创建 payload。独立规范审查在只对 `close(resourceFD)` 返回 EPERM、其它 syscall 允许的本次进程继承 seccomp 负控中，真实复现旧路径把 flags=0 的 socket FD 留进 payload exec，虽最终 scope GC 成功仍违反合同。因此普通正例与 GC 不能抵消 FD 生命周期失败；该负控必须在修复后证明无 payload marker、明确 phase2 与本次 scope 收束。不修改宿主策略或旧 proxy 后端。

固定 wire 为 `ICQR1`（5 bytes）＋phase（1）＋本次 unit 的 nonce（16）＋big-endian cap（4），共 26 bytes；ACK 为 `ICQA1`＋nonce＋cap，共 25 bytes。只允许 configured=1、明确 preexec_failed=2、finished=3、cleanup_failed=4。configured 在 prepare 精确 readback 后发出，正确 ACK 前不进入 namespace/payload；ACK 在 host credential/namespace 变化前校验。最多 configured＋一个 terminal，或初始 setup 失败的一帧 terminal。wait/finish 后 cleanup_failed 优先，其次可信 pre-exec 失败，否则 finished；任何 terminal 后额外帧拒绝。phase2 只证明未启动，不泛称 scope/目录清理成功；phase3 只证明本次 payload leaf 的 finish，不证明 manager GC。

PID1/payload 使用专用 CLOEXEC error pipe 向 launcher 报告实际 namespace/clone/隔离/exec 前失败，不能污染 parent-death pipe。EOF、exit0/127/13、用户输出、READY/ACK 都不证明成功 exec；未获独立 exec 证据的结果保持 unknown。协议截断、额外 FD、错 nonce/cap/PID/UID/GID、重复/乱序或缺 terminal 一律 channel failure/unknown，不把失去通道写成 false。接收后即拥有 ancillary FD 并在所有失败路径关闭。host 接收可先起窄线程，再让既有 USER_NOTIF 完成 ACK，避免串行等待死锁；不引入 ptrace、新权限、服务或 quota fallback。是否要求全部短命令确证 exec 已另询用户，组件开发不假定获准额外观察方案。

SOCK_SEQPACKET 的零长 packet 不能当 EOF：本机真实 recvmsg 在 SO_PASSCRED 下为零长 packet 附加凭据，端点真实关闭才返回零长 body 且无 ancillary。有 ancillary 的空 body 一律为非法帧，包括 terminal 后或错误 writer 发送；否则会过早接受 terminal 并漏检后续坏帧。逐消息解析异常也必须依据原始 ancillary 扫描并关闭全部已交付 rights，不能依赖尚未完整登记的 FD 列表。

主代理在已安装的 `6fda570` helper 上额外实际核对 systemd 249：scope exec 后 launcher PID 是 Popen.pid、原 host-parent 校验通过、既有 USER_NOTIF FD 经 scope 可达且真实 socket 被拒绝，`$X`/`${X}`/`$$`/空格/前导 dash/空字符串 argv 保持原样，scope 最后消失。此实验只有旧单 endpoint，没有证明新增双 FD、v254+、私有终态或产品调用链；下一 TDD 必须另测。原生组件先独立规范/质量审查，再接真实 broker 与管理/载荷环境分离；进程上限和 readiness 不因回执源码存在而加分。

### 独立只读研究补充：逐消息身份与 ancillary 所有权

2026-10-08 在 kernel 6.8.0-138 上，独立研究使用无 scope 的有界 fork/namespace 实验并等待全部子进程退出。host 收到 mapped/mapless 外 launcher 的原 host PID 与 UID/GID；PID1 的消息带另一 host PID，不能冒充 launcher。外 launcher 的 `unshare(CLONE_NEWPID)` 不迁移其自身，只有后创建的孩子进入新 PID namespace；凭据 UID/GID 按**接收线程**当前 user namespace 翻译（[固定 Linux v6.17 SCM 实现](https://github.com/torvalds/linux/blob/e5f0a698b34ed76002dc5cff3804a61c80233a7a/net/core/scm.c)、[PID namespace 文档](https://man7.org/linux/man-pages/man7/pid_namespaces.7.html)）。因此采纳 host 绑定实际 Popen PID＋host 身份，native ACK 在 namespace 变化前验证；不比较跨 namespace 的缓存 UID 数值。

采纳内核自动附加 SCM_CREDENTIALS，接收端在发送前启用 SO_PASSCRED；不手填 mapless 的 `getuid()==65534`，空 uid_map 下该值不能反向映射，可导致 EINVAL。ACK 不接受任何 SCM_RIGHTS；`recvmsg(MSG_CMSG_CLOEXEC)` 后即拥有所有已交付 FD，必须先逐个关闭，再报告任何截断/协议错误。独立发送 1/7/40 个 FD 时实际交付 1/4/4 个，后两次 MSG_CTRUNC；关闭后 FD 基线恢复，证明不能在 CTRUNC 分支提前返回。以上仅为本机 API 机制实验，不代替新 native/Python 组件正负验收，无源码复制、依赖或权限变化。

## 后续真实命令链的接线前置项（尚未实现）

### 私有回执冻结 v3 本机验证（2026-10-08）

原生源码 SHA-256 `ca21ceca2d59c9be2c83e59b6a906ac386a38fe0a5611a6d078a7d5151343bb5`；资源头 `341b36cb2db869cc12c128396cb051d436813ab75d9d48c14a68076f082ac4bf`；Python receiver `af131cda3517de5be8b3f51b64b3d52e6d446dbd77644c7d6a88c3bb7a6d1ca5`。最终新增 36 方法 ×20 轮为 720/720，实施者冻结关联 117/117；独立 SPEC 116/116，另真实单 scope 的 close(resourceFD)→EPERM 精确负控确认 exit1、无 payload marker、stdout 空、preexec_failed/false 与本次 GC；独立 QUALITY 36+7 项实际通过。以上全部 0 SKIP，C11 严格编译/静态分析通过，原 quota header 未变。v1/v2 的重复轮数不是 v3 最终验收，不合并虚增计数。

主代理实际构建 sdist 与 wheel、从该 sdist 重建 wheel，逐字节核对新 header/receiver 在归档中。两种 wheel 的 helper 与干净 pip 安装的 helper 完全相同，946728 bytes，SHA-256 `4152b76056205104d3b965f5b1bca2b9e61d074d80935024c0256e35b8ebbc0a`。真实 installed helper 的 cap2、cap1 fork、cap1 thread、resource+USER_NOTIF 双 FD、missing exec 共 5/5，逐项核实本次 unit/scope GC；前三种成功任务仍 unknown，missing exec 为 false，不伪造 exec=true。旧安装十阶段回归全部 PASS，其中旧 host-crash 未启用新 quota，不外推新 quota 生命周期。独立 SPEC/QUALITY 与安装产物闭环只认证此组件，不认证真实工单链或 R2/R3 readiness；`conformance_credit=none`。

后续环境/标准流边界按 [独立小步计划](../plans/2026-10-08-linux-payload-management-boundary.md) 实施；以下产品接线项仍未完成。

### e2bd25d 云端测试夹具失败（2026-10-08，尚未复验通过）

| 基线 | 已确认对象 / 缺口 |
|---|---|
| identity / time | GitHub hosted Linux job `113153153744`，04:47 UTC；物理机器身份不可得，按固定 run/job 绑定 |
| runtime / analysis / verification | 远端为已推送 `e2bd25dac31d9f192bf18da210bc7ace6e5ec329`；分析与本机验证为其上未提交的管理边界 C `0700aa0a9fb8f18d60d1fe2f8320d8a1a03d4c0be9e189d10922fc2ada0a1ea3`；子模块未变，测试夹具正在修正 |
| artifact / evidence | main [37728854887](https://github.com/ayukyo/icode/actions/runs/37728854887)，通过已授权 GitHub connector 取得该 job 真实解码日志；远端 helper hash 未取得，不称安装验证 |
| direct facts | 1892 tests / 238.284s，4 failures / 1 error / 71 skips；四项 default ready=false，cleanup 优先级搬外 scope PID 时 cgroup.procs PermissionError13 |
| completed matrix | main 最终 37 jobs：30 success / 4 failure / 3 skipped；Python3.12 job `113153153855` 独立日志为 1892 tests / 372.758s，相同4失败/1错误/71跳过。另外两失败为旧 Windows Reviewer；site [37728854808](https://github.com/ayukyo/icode/actions/runs/37728854808) success。旧 run 已结束，不重复轮询 |
| related gate | provenance [37728854732](https://github.com/ayukyo/icode/actions/runs/37728854732) validate `113153152528` 的签名 fixture 9/9 成功，但全仓 preflight 为相同4失败/1错误，1892 tests / 238.831s；四原生矩阵均未执行，不能借6fda570通过结论认证新SHA |
| unresolved / owner | 远端 default 任务的实际 UID/原生 stderr 未保留，ready=false 单独不能定根因；主代理与实施者修夹具、独立复审后以新 SHA 复验 |
| ceiling | `candidate_path` 对远端四项；本机实体空 uid_map 复现默认硬断言缺陷，不是远端实际 UID 证明；不抬 R2/R3 readiness |

本机主代理以本次实体空 uid_map，保持 default 标签而非 forced mapless 参数，实际观察 UID65534→AssertionError65534、exit1、configured/finished/unknown 及本次 GC。此机制证明测试硬要求 UID0 不符合既有自动 mapless 合同；远端四项具体 UID 仍未知。default 夹具改为 UID0/65534 都可，forced mapless 仍严格65534，名称与文档区分 default/mapped。cleanup 负控改为原 prepare 成功后，仅在测试 driver 中调用真实 quota_fork 创建本 scope 有限寿命 charged 子进程，所有管理副本关闭，最后 waitpid 自有孩子；真实非空 leaf 导致 preexec 失败及 cleanup_failed 优先，不声称到达 clone3/EAGAIN。无 sudo、全局配置、生产 quota 行为或失败条件放宽；新冻结测试与远端结果另记。

### 管理环境／标准流分片冻结（2026-10-08，本机证据）

C 冻结 SHA-256 `0700aa0a9fb8f18d60d1fe2f8320d8a1a03d4c0be9e189d10922fc2ada0a1ea3`，测试冻结 `87db9cfa01a7934cf3d219c4267b28fa78ed9af84dee4ec8707ccf61d2b9fd33`；两个 header 和 Python receiver 均未改。resource 模式在 payload exec 前移除三个管理变量并把 stderr 接到 stdout；无 resource 的旧路径保留环境与独立标准流。实际 exec 失败只写已有专用 F，不输出 perror。

新增7方法先取得8项真实失败断言，随后正常/forced mapless/双FD、dup2(1,2)→EPERM、三个 unsetenv→ENOMEM、missing exec 与 legacy 均 GREEN。最终全部43方法×20轮 860/860；实施者关联124/124、独立 SPEC123/123，全部0 SKIP。此前中间版本的140/430轮不计入最终冻结验收。独立QUALITY实际43资源＋14旧quota＝57/57、0 SKIP，无遗留缺陷，前后五个文件摘要一致。C严格编译／静态分析、compileall、diff-check通过；最终全仓门禁结果另记，不借旧源码门禁。

主代理实际 sdist→wheel、从 sdist 重建 wheel、干净venv pip安装。两种 wheel 与安装包 helper 逐字节相同，946784 bytes，SHA-256 `dae215a648760d5f56a06a9ed496b9273011bd7c72f87f0c3b46aeec0ccde388`；sdist C 与上述冻结摘要匹配。安装包内真实 helper 六项通过：默认管理变量／两种载荷marker、resource+USER_NOTIF双FD、missing exec、cap1 fork、cap1 thread、legacy环境／流兼容；逐项 exact unit/scope GC。安装轮未用生产测试hook强制mapless，也未注入unset/dup故障，不冒称覆盖这些安装场景。旧安装十阶段回归也全部PASS，host-crash仍是无新quota的旧回归。以上不认证产品broker接线、远端新SHA、其它平台或R2/R3 readiness。

最终冻结后重新运行完整 preflight，密钥／子模块完整性／全仓 unittest 三道通过；governance／site／landscape、严格 C 静态分析、compileall、diff-check亦通过。早先在测试夹具修正期间运行的门禁不用于此最终源码认证。提交推送仅将此本机分片纳入 main，云端新 SHA 的 suite／provenance／安装验证仍独立核实。

复用 `execution_broker._execute_policy_command` 的 monotonic deadline、输出 byte cap、selector 和最终进程组清理，不另建执行循环。新增可信 scope 层只接受内部产生的 nonce unit、policy 原整数 cap 和最多两私有端点；先核对 cap 在 native 可表达范围，超过 INT_MAX 在启动前拒绝，不改 schema 或截断。USER_NOTIF receiver 之前先启动 resource receiver，以免两条 ACK 互相等待。

管理环境仅在原 policy environment 上增加固定当前 UID 的 user bus 参数；先核对 `/run/user/<uid>` 与 bus 的身份/类型/非链接边界，不继承任意 DBUS 地址或宿主环境。systemd scope 源码还注入 INVOCATION_ID，native 在 payload exec 前移除这三项管理环境变量。固定受信 systemd-run/systemctl 路径、literal argv 及实际版本能力需在支持主机验收；不增加全局配置、管理员服务或共享 scope。

当前管理程序/native stderr 与 payload stderr 合流，直接沿用会让失败的管理错误进入模型结果。接线片应在私有 resource 模式下，由 native 在 exec 前将 payload stderr 接到 payload stdout；重定向之后原生 exec 错误只写 F，不再 perror，避免通道同时失效时仍泄露诊断。host 另用有界读取丢弃管理 stderr。旧无 resource 调用保持既有行为。明确 phase2 或配置失败只返回固定脱敏结果，丢弃收集输出；没有可信启动失败事实时保留 unknown。不能以 quiet flag、输出关键字或退出码替代这个分流边界。

进程组 kill 成功、native leaf finish 与 manager scope/unit GC 分别记事实。每次只核对本次随机 unit 和 scope，不扫描删除其它 cgroup。StartTransientUnit mode=fail 防覆盖，不证明失败时同名 scope 归本次所有；未得到可信 configured 或其它本次 scope/Popen 身份凭据时，不能仅凭随机名称 systemctl stop/kill。创建碰撞负控必须保留旧成员及目录，只 kill/reap 本次 Popen，身份不符返回固定 cleanup 失败。真实 `run_command` 后还需并发 cap 独立、普通非零退出、timeout、超量、取消、异常和 host SIGKILL（含 setsid 后代）的新 quota 生命周期；源码正控、旧无 quota host-crash 和空目录 GC 均不替代这些验收。不因此设计或组件通过开放自动模式。
