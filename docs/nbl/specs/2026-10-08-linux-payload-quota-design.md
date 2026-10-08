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
