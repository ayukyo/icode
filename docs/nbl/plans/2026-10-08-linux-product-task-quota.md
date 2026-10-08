# Linux 产品命令进程配额 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development to implement this plan task-by-task. 用户要求 main 原地开发、验证后提交推送；不建立分支或 worktree。平台配额口径已经批准，不新增权限或安装步骤。单实施者写代码，研究、SPEC、QUALITY独立只读。

**Goal:** 让真实 `policy → ToolContext → run_command → broker → scope → native` 链逐命令执行 RL-0 配额，并保留实际资源、拒绝和清理事实。

**Architecture:** 复用已冻结的原生 supervisor/payload、clone3、resource/USER_NOTIF 双端点及执行核心。新增窄的可信 user-manager scope 生命周期对象，在 CONFIGURED→ACK 之间绑定本次 Popen/cgroup 身份；不以随机名作为所有权。任务输出和管理诊断分流，不修改评分、自动选择或模型 schema。

**Tech Stack:** Python3.11 stdlib、既有 user systemd manager、Linux cgroup2/Landlock/seccomp；pip用户不需要新增编译器、服务或管理员步骤。

---

## 固定输入与调用链

三问均确认：process_limit 存在但当前产品链未消费；native/header/receiver均已有实现；唯一直接生产调用者为 builtin，安装 receipt 与 AgentLoop测试间接走 registry。实际产品探针不能迁回旧诊断 API 冒充接线完成。

当前 native C0700aa／resource header341b36／quota header960c8c 已冻结，本片不加 native-only 功能。依据 [配额设计](../specs/2026-10-08-linux-payload-quota-design.md) 和 [RL-0](../specs/2026-10-08-r2-process-limit-contract.md)：仅根任务及后代计数、Linux线程计入、宿主监督程序确实在额度外、两个并发命令不共享上限。超过 INT_MAX 的合法policy值在启动前固定拒绝，不截断、不改schema。

文件职责：

- 新增 `src/icode/linux_task_scope.py`：当前UID user bus与系统工具检查、nonce unit、scope argv、ACK前目录身份固定、只读GC。无扫描／删除／systemctl stop或kill。
- 修改 `src/icode/linux_task_resource.py`：可选可信 `on_configured(deadline)`，验证第一帧后、ACK前运行；异常不ACK，终止本次已绑定process。默认None保持现有组件合同。
- 修改 `src/icode/execution_broker.py`：共用 observed routine、真实资源入口、最小启动环境、独立管理stderr、结果事实。旧 violation API签名保留。
- 修改 `src/icode/isolation.py`、`src/icode/tools/base.py`：仅可信内部双socket／unit／policy cap wrapper；复用root/read-only／helper哈希／runtime检查。
- 修改 `src/icode/tools/builtin.py`：真实Landlock DENY policy命令使用新资源入口；metadata只投影固定资源事实，不泄管理路径、诊断或原argv。
- 新增 `tests/test_linux_product_task_quota.py`，修改关联模块测试及安装receipt探针的断言；不将生产测试改成诊断路径。

## Task 1: 真实 registry 命令链与生命周期

**状态**
- [x] 任务完成

**Dependencies:** 管理环境／标准流分片提交并确认remote SHA。
**Parallelizable:** No（修改共同broker和ToolContext；研究／复审只读）

- [x] **Step 1: 真实入口 RED**

复用 `TestLinuxViolationReceipt.setUpClass` 的真实编译helper／manifest方式及 `_context`，不要继承其全部test methods。新增类可以使用其context helper，实例真实 registry：

```python
context.policy = replace(context.policy, process_limit=1)
result = default_registry().invoke('run_command', context, {
    'argv': [sys.executable, '-c',
             'import os, errno\n'
             'try: child = os.fork()\n'
             'except OSError as e: assert e.errno == errno.EAGAIN\n'
             'else:\n'
             '    if child == 0: os._exit(0)\n'
             '    os.waitpid(child, 0); raise AssertionError("quota absent")\n'],
    'timeout': 8,
})
self.assertTrue(result.ok, result.meta)
self.assertEqual(result.meta['resource_receipt']['limit'], 1)
self.assertIs(result.meta['resource_receipt']['configured'], True)
self.assertIsNone(result.meta['payload_started'])
self.assertIs(result.meta['scope_cleanup_ok'], True)
```

Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_linux_product_task_quota -v`。
Expected: 实际旧链创建孩子而断言失败；不是缺import、主机条件或mockargv造成的失败。实体记录 kernel／systemd版本与user-manager条件；无条件不能计通过。

- [x] **Step 2: 最小可信 scope 与 ACK 前所有权**

`LinuxTaskScope` 内部生成 `icode-task-<secrets.token_hex(16)>.scope`，拒绝root。固定 `/usr/bin/systemd-run`、`/usr/bin/systemctl` 及祖先 root-owned、非链接、不可被普通用户写、regular executable；固定 `/run/user/<uid>` UID／非链接／目录保护和bus UID／socket，socket0666在父0700下合法。通过本次短连接 SO_PEERCRED核对user bus peer UID，不继承宿主DBUS地址。

scope argv 使用 `--user --scope --quiet --collect --no-ask-password --description=ICODE task command --unit=<nonce> --property=Delegate=pids -- <helper...>`。真实检测固定工具版本；249不传新增展开选项，254+显式 `--expand-environment=no`。不经shell、固定description，不保存payload原argv到description。

管理查询也调用现有私有执行core，固定stdout8192-byte cap／短timeout／stderr独立丢弃／pass_fds=()；不另写进程读取循环。manager env仅固定PATH/LANG与当前UID两条bus变量，不带payload HOME/PYTHONPATH或宿主密钥。

receiver新增参数：

```python
on_configured: Callable[[float], None] | None = None
```

在第一帧magic／nonce／cap／credentials校验完成之后、发送ACK之前调用，之后重新检查deadline。回调运行上限 `min(command_deadline, launch_start + 2.0)`，launch_start在实际core启动前记录。不得把fixture10秒manager查询搬进native3秒ACK窗口。

回调读取本次 `/proc/<Popen.pid>/cgroup`，只接受唯一统一层级路径、规范absolute且无点分量、末尾 `<unit>/supervisor`；固定root/supervisor/payload的FD／dev／ino／UID，以O_NOFOLLOW逐祖先打开。查询仅本次unit，闭集字段Id／LoadState／ActiveState／ControlGroup／InvocationID／Transient，缺失／重复／越界／错路径拒绝。要求Id精确、loaded／active／transient、有效invocation、ControlGroup精确等于上述root、supervisor只含本次launcher、payload为空且pids.max精确原cap；ACK前重新核对目录身份。所有失败不ACK，只kill/reap本次Popen，不能触碰同名碰撞单元。

- [x] **Step 3: 复用执行核心与工具绑定**

新增产品入口 `execute_linux_resource_observed_command`，参数同旧observed入口但可信wrapper增加resource端点和unit；旧API保留且标明诊断上限。抽私有共用routine，避免复制整段observer流程。ToolContext先 `_policy_command_wrapper()` 再调用新Landlock wrapper：

```python
def wrap_command_with_resource_receipt(
    self, argv: list[str], control_socket: object,
    resource_socket: object, unit: str,
) -> list[str]:
    self._policy_command_wrapper()
    wrap = getattr(self.sandbox, 'wrap_policy_with_resource_receipt', None)
    if not callable(wrap):
        raise IsolationUnavailable('原生资源回执通道不可用，命令已拒绝')
    try:
        return list(wrap(argv, policy=self.policy, control_socket=control_socket,
                         resource_socket=resource_socket, unit=unit))
    except Exception:
        raise IsolationUnavailable('工单隔离策略绑定失败，命令已拒绝') from None
```

Landlock内部复用现有helper/root/runtime检查，验证两个live AF_UNIX/SEQPACKET FD不同且≥3，unit严格格式，limit来自policy；包装只加入三私有CLI项，不给模型新的参数。`on_spawn`关闭发送端、绑定实际process/hostUID/GID，先start resource receiver，再start USER_NOTIF。不能同步等配置后才起resource线程。

core仅增加私有可信启动环境与管理stderr开关，默认保持旧 `_policy_environment`／STDOUT。新模式仍同一selector和monotonic deadline，管理stderr独立固定65536字节预算，读后丢弃、不存chunk、不计任务output；超额固定 `manager_output_limit`，不伪称任务超额。payload.stderr由既有native合入stdout。finally分别尝试selector／ownedgroup／两pipe关闭，KeyboardInterrupt等在尝试清理后传播。

`ExecutionResult`末尾追加默认None字段，保留旧positional兼容：

```python
resource_receipt: dict[str, object] | None = None
scope_cleanup_ok: bool | None = None
payload_started: bool | None = None
```

复用 `dataclasses.replace` 投影，不在重建时丢字段。`cleanup_ok`保留进程组原语义；resource finished只证明native leaf、scope_cleanup_ok只证明已绑定本次unit和固定目录消失。配置/setup明确未启动固定错误并丢输出；完整phase2为false，其它通道缺失／phase4为unknown，绝不写exec=true。resource缺失／scope清理false不能ok。违规receipt仍只有实际USER_NOTIF事件能产生。

- [x] **Step 4: GREEN、碰撞和生命周期负控**

真实registry矩阵：cap1 fork／thread拒绝与pids.events、cap2根＋setsid孩子及第三task拒绝、两supervisor不占payload、管理FD全关闭、literal `$X/${X}/$$/空格/空串/-dash`、currentvenv、管理变量移除／payload两stream合流、短命令／exit13／missingexec。保留既有receipt与AgentLoop路径，不改为旧API。

ACK前错CG／重复字段／查询超时／callback异常不exec marker；限制只在本次查询或组件边界注入，不改机器配置。nonce碰撞用真实自有旧scope，旧成员/目录/配额保持不变，新命令拒绝；不manager kill/stop。无bus/错tool/cap超native范围启动前拒绝，无模型bypass。

正常／timeout／output／read失败／selector失败／Thread.start失败／KeyboardInterrupt／两个并发命令各自cap，以及host SIGKILL＋setsid：每次观察确切scope与目录身份，host-kill由外部观察者核对后代PID/marker、unitGC，不能依赖死掉Python的finally或借旧无quota测试。已有每条socket／receiver／pipe／scopeFD均独立清理；正常先wait完整terminal/EOF再close；close不是complete。只读轮询本次unit和pinned目录，缺失查询=unknown、仍存在=false、不扫其它目录。

Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_linux_product_task_quota tests.test_linux_violation_receipt tests.test_execution_broker tests.test_tools tests.test_linux_task_resource -v`。
Expected: 支持主机全部实证通过；新矩阵冻结20轮，轮数绑定最终源码，0SKIP才记录本机host_verified。

- [x] **Step 5: 独立审查、安装与提交**

独立SPEC→QUALITY；主代理sdist→wheel→干净pip安装，已安装registry复验配额／receipt／清理；`scripts/run_native_wheel_ci.py`原产品receipt阶段继续新链，不将环境缺失改成通过。全部preflight三道、governance／site／landscape和diff-check，精确ownedfiles提交／推送main、确认remote SHA；新CI不足不报告整体完成。

## 研究采纳与验收上限

2026-10-08独立只读源码核对systemd249 f6278558、254 994c7978（LGPL-2.1-or-later）：采纳scope注册自身PID／mode=fail／直接exec／INVOCATION_ID剥离、254显式禁展开；仅借机制不复制代码。暂缓新特权manager/自动安装服务；不适配UID全局rlimit／轮询事后kill／nonce所有权／EOF成功推断。固定链接及已有Codex/Linux证据见持续对照与配额规范。

本片最多认证Linux真实命令资源合同和本机生命周期，不代替Landlock文件拒绝独立审计、网络lease生产门、其它架构/Windows/macOS、R3真实模型1→6链。`policy_contract_ready`、评分、自动模式均不变。macOS专属UID／管理员quota机制仍缺新授权，不借Linux实现解除。

## 最终冻结验证进度（2026-10-08；尚未提交）

独立 SPEC 复现了 pin、broker 端点、resource factory 端点和工具校验收尾四个中断边界：首个关闭产生中断时可能漏清其它资源或把用户取消改成普通 setup 失败。实施者另对本片目录打开与核心两管道关闭做真实 FD 负控，确认后续普通错误可能覆盖中断。六边界均以真实 FD/socket/子进程 RED→GREEN，采用共享中断优先、同优先级首错误及逐资源独立清理；不扩为全工程清理重构。

此前 35 方法×20（700 次）以及中途 37 方法的六完整轮（222 次）仅保留历史诊断，后续源码修正使它们不能作为最终冻结验收。最终新矩阵为 42 方法，九文件与原生三文件摘要冻结后重新执行20轮，840/840通过、0 SKIP，每轮前后九文件摘要一致。

最终 SPEC 静态六边界闭合；独立 ownership 10 方法、核心两真实管道三异常顺序实验均通过，实际 FD 基线恢复、子进程已回收。独立关联五模块实际 156/156、25.102 秒、0 SKIP/失败/错误。本机 Linux 6.8.0-138-generic x86_64、systemd 249.11-0ubuntu3.22、Python3.11.15，不能外推较新 systemd 或其它架构。

主代理从冻结源码构建 sdist 和直接 wheel，再从该 sdist 重建 wheel，干净 venv 仅 `pip install --no-deps` 安装；八个相关模块的归档、重建 wheel 与已安装字节均与源码一致。已安装实际 registry 通过 USER_NOTIF 网络拒绝、AF_UNIX 正控、普通 exit13 不误判、cap1 fork/线程计数、cap2 setsid 后代与第三 task 拒绝、资源回执及 scope GC；无 checkout import、诊断 API 替代或环境 SKIP。助手946784字节、SHA-256 `dae215a648760d5f56a06a9ed496b9273011bd7c72f87f0c3b46aeec0ccde388`。

native wheel完整十阶段实际PASS；其中host-crash和network lease沿既有独立探针验收，不把它们冒充新的产品quota全合同。实施者最终关联扩大至185/185、26.642秒、0 SKIP，PID namespace/mapless关联25/25、0 SKIP；九摘要保持冻结。独立 QUALITY 实际42/42、9.862秒及关联156/156、25.096秒，均0 SKIP；九文件AST/差异/前后摘要通过，无遗留阻断。

主代理完整preflight三道门、compileall `-j6`及治理/官网/竞品/diff守护通过，最后文档修改后密钥/子模块守护再次通过。本机分片已具备提交条件；精确提交推送及新SHA原生矩阵仍另行记录，不提前关闭线上门。上述配置与回收证据不签发 exec=true，也不开放自动模式或关闭 R2/R3。

### be31b98 精确提交及原生安装门

与无源码交叠的R3真实性分片共同冻结为18文件受测树，已提交推送main `be31b9895681e651737714f667d8ceb8e3a56f7d`，主代理提交后ls-remote核对一致。[主CI37736905277](https://github.com/ayukyo/icode/actions/runs/37736905277)最终32 success、2 Windows Reviewer candidate failure、3 skipped；完整37计数由独立观察者保存全页取得，主代理connector首页30只有28 success/2 failure，未将首页冒充全量。

主代理实际读取Python3.11/3.12日志，各1959方法、412.253/463.095秒，OK、71平台SKIP。另实际读取四个Linux安装job：22.04 x64 `113178408620`、ARM64 `113178408650`、24.04/latest x64 `113178408683`、24.04 ARM64 `113178408559`，四个新registry USER_NOTIF/根payload cap1 fork配额安装子门均PASS；对应当前随包探针强制limit1、配置、scope GC及未知exec状态，不是诊断API。22.04两架构lease PASS、24.04两架构SKIP，全部conformance_credit=none；不能将安装job成功推成lease全平台行为通过。

本Task关闭的是实际产品配额接线、限定本机矩阵与四架构安装子门；完整R2隔离/统一文件拒绝/lease产品门、Windows/macOS资源机制及R3真实模型链仍未关闭。上述两个旧Windows失败不被抹掉或解释为资源门通过。

**Execution Mode:** serial

## a21 线上新增测试竞态及窄修复（2026-10-08；待新SHA）

预算提交 `a21dbb5fcaef79a35266a0f80387faf4e3bde002` 的main实际37jobs为31success、3failure、3skip；两既有Windows候选失败不变，新增Python3.12 [job113185110661](https://github.com/ayukyo/icode/actions/runs/37739007207/job/113185110661)在1968方法/431.950秒/71SKIP中出现1error：实际host SIGKILL测试在status.exists与read_text之间被reap，f.read抛ProcessLookupError/ESRCH。主代理实际抓取该日志；不是观察到quota逃逸，也不能把这轮全量说成通过。3.11同轮1968方法/409.828秒、71SKIP通过；签名及官网各自success不替代失败套件。

只修测试：取消proc exists预检查，单次读取仅接受FileNotFoundError/ProcessLookupError；活S与未知状态仍断言失败，EIO/permission/KI/SystemExit仍原实例抛出。原精确scope inode、cap2、SIGKILL返回、GC、迟到marker及managerunit不存在断言全部保留，生产文件不变。初始helper缺失NameError仅结构RED；RAM原exists/read逻辑结合存在正控，3方法中的ENOENT/ESRCH两个实际错误RED，其它正负控通过。

最终测试SHA256 `b04d5996799c66bcc86709cc1e201fc0718d214a1af01ce34d758e70b1db9418`；3helper方法与实际host崩溃一项连续20轮=80/80、0SKIP，轮前后摘要一致；完整该模块45/45、10.235秒、0SKIP。独立SPEC4/4（2.611秒）及QUALITY4/4（2.605秒）均0SKIP、无遗留发现，QUALITY另独立实际活自身PID拒绝/已wait回收子进程接受正反控制通过。此测试修复与R3测量片联合完整守护、提交后才能认作新SHA结果，旧42×20对应be31冻结仍保留其历史范围。

### 3c5 联合提交回归

联合提交已推送main `3c5b587d1de0b0e0ca60aef70fd7f31c7a1c54c1`并实际核对远端。[主CI37741452467](https://github.com/ayukyo/icode/actions/runs/37741452467)终态32success/2既有Windows候选failure/3skip；Python3.11与3.12实际各1983方法、71平台SKIP、均OK，后一run不再见ESRCH。独立观察者从已保存job名称及实际日志复核四Linux安装/native receipt/host-crash/Git门PASS：x64 22.04 `113192860806`、ARM64 22.04 `113192860990`、x64 latest（24.04）`113192860751`、ARM64 24.04 `113192860866`；22.04 lease PASS、24.04 lease SKIP，conformance_credit=none。此线上证据不改quota生产逻辑，不把SKIP算通过、不可外推所有竞态消除；Windows网络、macOS资源及R2/R3总体门仍未通过。该SHA主CI/签名/官网均终态后已停止重复查询。
