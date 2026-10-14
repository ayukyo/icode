# macOS 身份预留进程快照有界诊断 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: 使用 nbl.executing-plans 串行执行；仅 root 全文审阅与 fresh SPEC → 不同 QUALITY 全零、独立 TEST → 不同 SOURCE 后执行。当前 PLAN ONLY。用户 main-only、唯一文档和 root 单独发布覆盖技能默认 worktree、独立 spec、自动实施、stage/commit/push。

**Goal:** 区分身份预留实际消费的进程快照未知分支，保留当次返回值/errno，维持所有未知拒绝与原成功行为。

**Architecture:** 将现有 process_count 算法移至带局部结果值的私有函数，兼容 wrapper 保留原签名。仅 reserve_uid 的原初次未知及租约后未知拒绝消费结果并输出一行；其它调用、目录查询、扫描次数、arg0 与准入门不变。

**Tech Stack:** C11、既有 POSIX/libproc 调用；Python3.11 unittest 和小型 Linux/macOS C 软件 OS 边界探针。无新增第三方依赖、原生服务或系统配置。

---

## 1. 基线、真实问题与三步思考

观察日 2026-10-15。runtime失败基线为 b233b66431984aed78266d294a88653586b8caec；本修订analysis为main 35e07bcdc79475cd5bb4d7c9c46af7661bc8a847（父b233），vendor仍21566a589cbe98bd35372a04bbb6ca1c51d8eed2，Mac原native/controller字节未变。权威WSL /home/orbbec/projects/icode，Windows D:\Projects\icode 及链接保留。本文只修唯一PLAN；root进度文档及既有event TEST宏修dirty保留。正式Task1按root已公布的main候选和本表逐字核对，不能把b233运行基线误当必须回退的开发HEAD。

三问已确认：真实问题是 reserve-process-snapshot 只带被后续调用覆盖的 errno，不能区分拒绝来源；已有 process_count/reserve_uid、原 controller/raw artifact 与有限软件 OS 边界可复用；影响共享 A/W1/B include 与 groups 原逆向测试，必须同步摘要及机械逆还原，不改变 quota/准入。

root 实际官方 sequential-thinking stdio 三步 542c9a / exit0 已回报：需求为仅消费拒绝时诊断；方案为 per-call 值保存 list/info/kill 的当次返回及 errno，不在扫描内打印；风险为保持8192边界/扫描次数/arg0/未知拒绝与断管退出、原 inverse、正式独立 TDD/双审及线上同 SHA。作者工具目录无该 MCP，只如实记录 root 调用，不冒称亲调。之前 root 的 PATH shim 失败不计思考信用。

Intel A run38600577901/job115978478588/attempt1，UTC2026-10-14 16:44:08–16:44:48；macOS15.7.9/build24G830/kernel24.6.0/SDK15.5/x86_64。artifact11913448211 ZIP109353B/88entries，独立观察员逐 size/CRC88/88与API digest核一致：
f00d6982dc9f0a47fbf56d7fbf37cff157bd3d27932969961dd2aaf5b9a221e7。
SOURCE binary b14843725a81f770a3c1c7f9d861c4e9ffe91aa43a6ad2f6835f8399847de3c4；原stdout6行仅cap1_fork/control_fork/seatbelt_positive的launch+confirmation，stderr末为 reserve-process-snapshot errno100、retained目录cleanupunknown。native_exit2，无audit/formal/delivery-view；ZIP完整不等于运行账本完整。

旧5ad Intel run38590561344/job115943997131/artifact11907407064同SOURCE binary、同lease/driver/helper/limit字节，7+7及W1四root=18通过；本次baseline7及W1四root正常、ARM A18通过，不能给Intel缺失的SOURCE后4case信用。B因A依赖skip，native/formal实际0。错误UID、扫描PID、n、r及即时errno未记录，不由前三UID/PID猜测。结论上限为 observation_only，尚无本次底层根因。

修订账：此前687L/39064a4b41186ae4b9b520174f7b424590ae1aa5adbbba8fdad51a218ddb62dd经root全文检查发现I1：Asset C整体剥离marker算法前未核其完整批准字节，篡改marker内逻辑仍可能通过原a65。该版未获审核通过。本修订在剥离前先assert完整lease SHA3c8e74cffa0dfda2fc8e7cf91e67cd6db99c7a5c88167ab9c95925887356ada5，原a65目标与断言均保留；B源码、A新12资产不变，fresh SPEC→不同QUALITY仍待进行。

解释性输入更新：root回报35e双A各18通过，不撤销b233快照未知记录；双B仅strict12 setUpClass遇Darwin已有sigemptyset/sigaddset宏重定义-Werror，native/formal实际0。root紧急独立修既有event TEST364/a399→380/8cfbe010826115648e3b46a9e4284419ab70fe12ddcf9802644814b8a299c5ac（新增宏负控、仅两#undef），其正式RED/GREEN及SPEC为root回报，不是本片重跑或新snapshot根因证据；本片仅更新输入表。

CI接线分工：Windows notice D已由root提交于35e，实际CI2508/8045df800fde72f6ff2a94f1ea74cb039ed9a24abc1979c7189cb79e3b9307a6。Mac SOURCE作者只落B/D/E，绝不落F；F由root在Mac实际SOURCE双审全零后保留notice D再加入，并单独审组合CI。原F正文/13L/12f8eea2不变：历史29a7输入时单独投影2509/75becd78；当前8045加F后最终2511/c331b43681964eae1d62543b15fe1c43d4f4c6bbab346a33c5184c2d573cb5ca。本作者已匿名静态亲核F-on8045逐hunk唯一匹配、结果hash和唯一逆回8045。D→F与F→D精确相等、双逆回29a7为root9b89ff独立RAM回报，不冒称作者亲跑双顺序。

## 2. 全调用与不可变约束

|消费者|实际位置与用途|本片行为|
|---|---|---|
|A driver|main reserve_uid；run_case凭据前count与结束remaining|只reserve_uid两未知拒绝可新增行；其它原process_count wrapper无日志|
|W1|main reserve_unused_id→reserve_uid；pre-fork、live、end、extra快照|只内层reserve_uid消费未知可新增行；外层门/计数不改|
|B vectors|run_case reserve_unused_id；record_event与retained-identity门|只内层reserve_uid消费未知可新增行；data诊断、成功ACK与cap不改|
|共享unused_identity|reserve_uid后supplementary_free和process_count|不改，不将其未知提升为成功|
|旧groups TEST|展开fixed helper＋identity lease后核a65f067e原始driver|Asset C先机械逆还原本片增量，最终原hash保持|
|旧vectors TEST|只展开fixed helper或unused_identity，不展开lease|原944c9268/eb51b489目标不变，无需修改|

全部process_count调用已文本核对：lease初次/后验，unused_identity24，W1 native275/276/305/335/382，vectors421/633/634，driver313/401；reserve_uid只有driver main498和unused_identity21。新wrapper无全局缓存，局部结构分别属于本次before/after，不受下一次扫描污染。仅capture与赋值新增，无malloc/线程/新PID访问/额外kill。

原PLAN docs/nbl/plans/2026-10-13-macos-task-identity-quota-m0.md §1/§8要求读不全或身份不明拒绝；8192PID、有界UID60000–61023、永久lease、不重用、目录查询错误拒绝均保留。原process_count只在info长度不符且kill0明确ESRCH时continue；不得扩大这一规则，不增加findzomb/arg1、重扫或盲重试。

## 3. 有界诊断合同与信号前提

每次扫描填局部process_snapshot：list_count/list_errno；仅第一个实际导致本次返回-1的info记录填写bad_index/bad_pid/info_result/info_expected/info_errno/kill_result/kill_errno。原ESRCH被允许continue的记录不充拒绝原因；后续第一个未能消歧的记录才成为bad。没有info/kill尝试时各字段-1，info_expected始终sizeof当前实际结构。返回0/正数仍原语义。

errno在各调用返回后立即存值；不靠最后errno定因。list/info成功时保存的errno可能是旧值；info短正返回仅证明长度不完整，不能把即时errno自动解释为原因。bad_index=-1明确表示没有用于拒绝的info/kill尝试；bad_index>=0才表示该组结果已采样，区分实际返回-1与未调用sentinel。info长度不符后原errno=0及kill0仍原顺序。wrapper保留原返回值、次数和ambient errno，软件分别核list错误、info错误、kill成功/EPERM/ESRCH和完整成功路径的最终errno。emit保存/恢复其入口errno，因此原die仍观察目录查询后留下的值，不偷偷修原错误行含义。新增行才是当次调用的独立诊断。

仅两个消费者发出：
- before<0，且两次目录查询都返回0且NULL，原stage reserve-process-snapshot。
- 租约创建后after<0，原stage reserve-contaminated；after>0仍原拒绝且无新增行。

before未知但pw/gr已有条目而continue，或目录查询自身出错，均不打印快照。实际身份/lease碰撞与成功count不增加快照行，成功路径stderr保持空；旧wrapper自身无输出，其调用方原拒绝输出保留。任一真正消费均马上沿原die退出2，不接纳stderr为成功或oracle。

发出函数私有、stage仅以上两个字面量。384字节栈缓冲，格式化边界检查后单次write(2)，不重试；即使按所有int极值/UID最大值/最长stage计算，固定行≤293字节；每个执行体最多一条后即终结。原64KiB/15秒/120秒/480秒/10分钟/16MiB预算不变；stdout无新增。

SIGPIPE前提必须独立检查：A driver main在signal(SIGALRM,expire)/signal(SIGPIPE,SIG_IGN)检查成功后才建fixture与reserve循环；W1 main在原signal检查成功后才lease/reserve_unused_id；B main同样在root-signals检查后才run_case→reserve。各worker/leaf路径均不调用reserve_uid，普通wrapper不emit。因此现有三个观察者根路径已忽略SIGPIPE；本片不新增/恢复mask或全局信号配置。真实无读端pipe软件负控：原前提SIG_IGN下仍exit2；故意破坏为SIG_DFL时原/新都可-13，清楚证明前提必要，不假称emit对任意未来caller安全。未来新增reserve消费者必须独立验证该前提，否则不得复用诊断。软件信号负控只作用于自己的小进程，不发真实kill或操作账户。

## 4. 主源取舍与测试边界

2026-10-15亲核固定Apple xnu-12377.1.9原raw真实行号：
[libproc.c](https://github.com/apple-oss-distributions/xnu/blob/xnu-12377.1.9/libsyscall/wrappers/libproc/libproc.c)包装底层失败返回；
[proc_info.c#L405](https://github.com/apple-oss-distributions/xnu/blob/xnu-12377.1.9/bsd/kern/proc_info.c#L405)及[L470](https://github.com/apple-oss-distributions/xnu/blob/xnu-12377.1.9/bsd/kern/proc_info.c#L470)包含活进程与僵尸列表，[L2167](https://github.com/apple-oss-distributions/xnu/blob/xnu-12377.1.9/bsd/kern/proc_info.c#L2167)按arg选择僵尸查询。网页呈现压缩行号不作为blob锚点。所读两文件声明APSL-2.0；只借机制不复制实现，不刷新上游HEAD、不等同runner闭源内核。
- 采纳：当次返回/errno分开观察；收益是定位未知来源，成本一份局部结构/终结行/机械inverse；兼容性由本片正负控及旧合同验证。
- 暂缓：僵尸/退出竞争修复与原errno行为修复；公开机制仅候选，没有本次badPID证据。
- 不适配：未知跳过、扩cap/UID、arg1、盲重试、用成功软件probe替原生或反复重跑刷绿。

Asset A提取实际process_count/reserve_uid和可用新增函数，旧版本没有helper时直接编译真实旧算法；不会以missinghelper/compileERROR充RED。只stub libproc/kill0/目录查询/lease写等OS边界，真实signal/write/无读端pipe执行在小软件probe。fake kill要求signal0，仅接收synthetic101/102，绝不发送系统信号。软件proc_bsdinfo仅6个被算法读取的字段，sizeof24为模型ABI，不冒充Darwin结构大小。

12方法覆盖list0/-1/8192、info0/短/-1与kill0/EPERM/EINVAL、先ESRCH后未知、后验未知、skip_pw/gr静默、目录错误优先、正常/已用/lease碰撞/8191边界/非正PID、六身份字段、原ESRCH规则、wrapper静默、写错/短写、真实断管/前提破坏及现有三条根调用信号顺序。边界stub严格核调用参数/arg0和次数。

匿名RAM探索先后核候选与旧源码；最终冻结299L资产再按旧RED→新GREEN顺序实跑：旧81L12方法中5父红7绿、10 Assertion/0ERRORskip(.119s/exit1)，候选117L为12P/0F/Eskip(.115s/exit0)。只属计划预演，不充正式TDD信用；正式Task1必须先在实际旧源码落独立TEST并亲见语义RED。旧红来自8次缺快照断言及2次缺诊断write断言，不是quotaRED。所有五patch共8hunk正向投影/逆还原精确；AST通过；旧groups原inverse1P(.001s)，vectors原inverse1P(.001s)，原目标hash均不变。匿名映射只替RAM读入的lease，未改工作区源/TEST。

## 5. 冻结输入

新TEST路径必须不存在。下表任一漂移先核差异重审，不覆盖并行dirty；本文自hash由交付另报，避免自引用。

|路径|行数|SHA256|
|---|---:|---|
|native/mac/tests/icode_m0a1_identity_lease.inc|81|3f8563da5c30d55469776a212b397e4515a33b090dae4d387d8439ffc0226e82|
|tests/test_macos_process_groups_native.py|485|78e30df5c19ab97feb9eabcdf6f314602b7df96399b5ba6a7fbe8d6fdaf21927|
|scripts/run_macos_m0_ci.py|429|823c8b219ed72040cab2f1029c37c181b7ded81529ac14f338d4c1e8f7359814|
|scripts/run_macos_m0a2_vectors.py|328|ce4d254f70d4140275c17a5c33519cb554a82e1c737d4b2b73a46d20030def13|
|.github/workflows/ci.yml|2508|8045df800fde72f6ff2a94f1ea74cb039ed9a24abc1979c7189cb79e3b9307a6|
|native/mac/tests/icode_m0a1_driver.c|511|141bedc63deadad332eb1d46a474d24d68c837248fd89247d04bea4819f1bf9a|
|native/mac/tests/icode_m0a1_process_groups_native.c|389|ebe6071bd7b9e26c4948d1bbc87f496a149766e352231a5c0a5675d9f45194aa|
|native/mac/tests/icode_m0a2_vectors.c|736|2546c73e5e17511d9431401461df924a77a56aa59ae00f9e0affce6e6da99e1c|
|native/mac/tests/icode_m0a1_unused_identity.inc|30|a6916f73f63275ea43e1653a0d9ced53b4daceb594846a795cedd24b13035619|
|native/mac/tests/icode_m0a1_fixed_helpers.inc|203|de74f6b77a9d91fd3d9fdf2801adfe4dc8685ff685480a7b09bb0e9c58f10546|
|native/mac/icode_m0a1_limit.c|16|507b26a2d2ff1cca663c4c52f8ead50b1a4991563f1942e0f7d2a8f39dcc208c|
|tests/test_macos_m0a2_vectors.py|990|f924880a575c6e11aebac1fdbaa1d114691e1fe88c59fb1093a22e18b510285e|
|tests/test_macos_m0a2_event_diagnostics.py|380|8cfbe010826115648e3b46a9e4284419ab70fe12ddcf9802644814b8a299c5ac|
|docs/nbl/plans/2026-10-13-macos-task-identity-quota-m0.md|1664|37e4852cb9c25dfa2154ec8356d5416859125271f14b27d8d45f46bc44168ee7|

## 6. 串行任务与正式停止门

### Task 1: 独立 TEST 与机械inverse同步，然后实际语义RED

**Dependencies:** root全文＋fresh SPEC → 不同 QUALITY全零。  
**Parallelizable:** No（必须在SOURCE之前）。

- [ ] 核HEAD/vendor/全部输入及新TEST不存在；仅apply_patch新增完整Asset A，并执行Asset C旧inverse机械同步。旧hash目标不变，生产inc/controller/CI不提前改。
- [ ] 新strict12实际旧源码应12方法/5父红7绿/10Assertion、0ERRORskip、exit1；fixture/import/compiler不可用先停，不改断言补绿。保留原始输出、方法计数、时间、退出。
- [ ] 旧groups strict13保持13P0skip；旧vectors默认15为9P6skip、optin为9P/唯一M0A2_CAP2_API断言F/5native skip、0ERROR；原event strict12仍12P0skip。仅定点；不本机native/system/full。
- [ ] root核原件并安排独立实际TEST审；新TEST字节冻结。Asset C在旧源码无标记时走原inverse且原a65目标必须通过。

### Task 2: 不同 SOURCE作者，仅批准patch

**Dependencies:** Task1实际语义RED＋独立TEST审通过。  
**Parallelizable:** No（独立TEST先行）。

- [ ] 重新核冻结输入，注意Task1只改变两个TEST路径；SOURCE作者仅apply_patch Asset B/D/E，完整正文不另造实现或格式化。Asset F归root后续组合，不由SOURCE作者改CI。
- [ ] 新strict12实际12P0F/Eskip；上述旧13/15/12结果保持；controller只同步摘要，当前CI8045不改；未来root组合F仅在A job增加一个严格软件步骤，B M0A2_SOURCE仍0，原quota cap1不改。
- [ ] 全文diff、各hunk唯一匹配/正投影/内存inverse/完整字节hash及AST核对；所有不改输入原hash保持。编译默认j1，最多j6，仅小probe。
- [ ] 作者self SPEC→self QUALITY及七维自检后，root fresh actual SPEC→不同 QUALITY清零。未清零不stage/push，不改冻结新TEST/旧oracle。

### Task 3: root同候选线上有限观察，然后按实际结果停止

**Dependencies:** Task2独立实际双审清零＋root确认当前在途run终态。  
**Parallelizable:** No（root单独发布；不自行branch/tag/worktree）。

- [ ] root在Mac实际SOURCE双审全零后才将冻结F与既有notice D组合，核最终CI2511/c331b436及精确逆向、安排组合CI独立审查；不扩job/env/权限。当前35e的CI38607765925/prov38607765946/Pages38607765929由独立observer观察，必须全部终态后才允许下次Agent发布，不取消或重跑。
- [ ] 组合CI审查通过后，仅root可main-only发布待验候选触发正常CI；不扩大权限/UID/cap，未知仍拒绝。
- [ ] 双Mac A分别核完整7+7及W1四root，绑定同SHA/run/job/attempt/OS/SDK/object/binary/sourcehash。原baseline真实quotaRED与SOURCE正式GREEN门均不放宽。
- [ ] 若新快照行出现，仅报告其当次n/r/errno/kill0结果与stage，未尝试字段-1，不自动解释成功errno。仍native_exit2或缺audit时为ERROR/unknown，不能授A18或B。
- [ ] A成功才会运行B；B仍可能原native_exit2，按已有M0A2有界诊断合同观察。跳过的B实际native/formal仍0。
- [ ] 定位新分支后停止本诊断片；修复另立设计。C22/D32/E32/M0b/M1/R2/R3、90%与ready均不由诊断GREEN授信。Windows notice865预算计划独立。

### 唯一实际软件命令（从WSL仓库根，指定venv）

~~~bash
/home/orbbec/icode-r2r3-env.DL2JQJ/bin/python -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_macos_identity_snapshot_diagnostics.py'); assert s.countTestCases()==12, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
/home/orbbec/icode-r2r3-env.DL2JQJ/bin/python -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_macos_process_groups*.py'); assert s.countTestCases()==13, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
/home/orbbec/icode-r2r3-env.DL2JQJ/bin/python -B -m unittest discover -s tests -p test_macos_m0a2_vectors.py -v
ICODE_M0A2_LIMIT_SOFTWARE=1 /home/orbbec/icode-r2r3-env.DL2JQJ/bin/python -B -m unittest discover -s tests -p test_macos_m0a2_vectors.py -v
/home/orbbec/icode-r2r3-env.DL2JQJ/bin/python -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_macos_m0a2_event_diagnostics.py'); assert s.countTestCases()==12; r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
~~~

本片不增加controller parser/result分类，不将新增行当root ledger。A既有source_hashes baseline17/source18→19/20，B既有24/25→26/27，仅加新TEST/本PLAN。既有失败输出/metadata原hash/always artifact保留；成功ACK、封账manifest及正式native oracle不变。

## 7. 完整冻结资产

各围栏正文保留唯一末LF。A为完整新TEST；B–F为完整patch；C由独立TEST作者落、B/D/E由不同SOURCE作者落、F仅root后续组合。若工具不接受GNU行号，只规范化@@头，正文不变；F行号基于历史29a7，但正文已唯一匹配当前8045。当前只修本PLAN，以下均未执行到实际工作区。

### Asset A: tests/test_macos_identity_snapshot_diagnostics.py

```python
"""Identity snapshot diagnostics: real C algorithms, software OS boundaries only."""
import errno
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
LEASE_SOURCE=(ROOT/"native/mac/tests/icode_m0a1_identity_lease.inc").read_text(encoding="utf-8")

def function(source,name):
    matches=list(re.finditer(r"^static [^\n]*\b"+re.escape(name)+r"\([^;]*?\{",source,re.M))
    if len(matches)!=1:
        raise AssertionError("actual function not unique: "+name)
    start=matches[0].start();brace=matches[0].end()-1;depth=0
    for token in re.finditer(r'"(?:\\.|[^"\\])*"|/\*.*?\*/|//[^\n]*|[{}]',source[brace:],re.S):
        if token[0]=="{": depth+=1
        elif token[0]=="}":
            depth-=1
            if depth==0: return source[start:brace+token.end()]+"\n"
    raise AssertionError("actual function incomplete: "+name)

def program(source):
    actual=""
    if "struct process_snapshot {" in source:
        declared=re.findall(r"^struct process_snapshot \{.*?^\};\n",source,re.M|re.S)
        if len(declared)!=1: raise AssertionError("snapshot declaration not unique")
        actual=declared[0]+function(source,"emit_process_snapshot")+function(source,"process_count_snapshot")
    actual+=function(source,"process_count")+function(source,"reserve_uid")
    return PRELUDE+actual+TRAILER

PRELUDE=r'''
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <pwd.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <unistd.h>
enum {UID_FIRST=60000,UID_COUNT=1024,MAX_PIDS=8192,PROC_PIDTBSDINFO=3};
struct proc_bsdinfo {uid_t pbi_ruid,pbi_uid,pbi_svuid,pbi_rgid,pbi_gid,pbi_svgid;};
static unsigned char unavailable[UID_COUNT];
static const char *scenario;
static int scans,infos,kills,lookups,leases,writes;
static int is(const char *s) {return !strcmp(scenario,s);}
static int bad_list(void) {
 return is("list_zero") || is("list_negative") || is("list_full") || is("write_error") || is("short_write") ||
        ((is("skip_pw") || is("skip_gr") || is("lookup_error")) && scans==1) ||
        (is("post_unknown") && scans==2);
}
static int fake_list(void *buffer,int bytes) {
 if(bytes!=(int)(MAX_PIDS*sizeof(pid_t))) _exit(200);
 scans++;errno=EBADF;
 if(bad_list()) {
  if(is("list_negative")) {errno=ENOMEM;return -1;}
  if(is("list_full")) {errno=E2BIG;return MAX_PIDS;}
  return 0;
 }
 pid_t *p=buffer;
 if(is("info_chain")) {p[0]=101;p[1]=102;return 2;}
 if(is("nonpositive")) {p[0]=0;p[1]=-1;p[2]=101;return 3;}
 if(is("near_cap")) {
  memset(buffer,0,(size_t)bytes);p[MAX_PIDS-2]=101;return MAX_PIDS-1;
 }
 if(is("six_fields")) {for(int i=0;i<6;i++)p[i]=101+i;return 6;}
 p[0]=101;return 1;
}
static int fake_info(int pid,int flavor,unsigned long long arg,void *buffer,int bytes) {
 if(pid<101 || pid>106 || flavor!=PROC_PIDTBSDINFO || arg ||
    bytes!=(int)sizeof(struct proc_bsdinfo)) _exit(201);
 infos++;errno=EACCES;
 if(is("info_zero") || is("info_chain") || is("info_esrch")) return 0;
 if(is("info_short")) {errno=EIO;return bytes-1;}
 if(is("info_negative")) {errno=EBADF;return -1;}
 struct proc_bsdinfo *p=buffer;memset(p,0,sizeof(*p));
 if(is("six_fields")) {
  uid_t *fields[]={&p->pbi_ruid,&p->pbi_uid,&p->pbi_svuid,&p->pbi_rgid,&p->pbi_gid,&p->pbi_svgid};
  *fields[pid-101]=UID_FIRST;
 }
 if((is("collision") && scans==1) || (is("post_positive") && scans==2)) p->pbi_svuid=UID_FIRST;
 return bytes;
}
static int fake_kill(pid_t pid,int sig) {
 if(sig || (pid!=101 && pid!=102)) _exit(202);
 kills++;
 if(is("info_esrch") || (is("info_chain") && pid==101)) {errno=ESRCH;return -1;}
 if(is("info_short") || is("info_chain")) {errno=EPERM;return -1;}
 if(is("info_negative")) {errno=EINVAL;return -1;}
 errno=0;return 0;
}
static int fake_pw(uid_t uid,struct passwd *pw,char *buf,size_t n,struct passwd **result) {
 if(uid<UID_FIRST || uid>=UID_FIRST+UID_COUNT || n!=16384 || !buf) _exit(203);
 lookups++;*result=is("skip_pw") && uid==UID_FIRST ? pw : NULL;
 errno=100;
 return is("lookup_error") ? EIO : 0;
}
static int fake_gr(gid_t gid,struct group *gr,char *buf,size_t n,struct group **result) {
 if(gid<UID_FIRST || gid>=UID_FIRST+UID_COUNT || n!=16384 || !buf) _exit(204);
 lookups++;*result=is("skip_gr") && gid==UID_FIRST ? gr : NULL;errno=100;return 0;
}
static int fake_openat(int dir,const char *name,int flags,mode_t mode) {
 if(dir!=9 || strncmp(name,"uid-",4) || flags!=(O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC) ||
    mode!=0600) _exit(205);
 if(is("lease_collision") && scans==1) {errno=EEXIST;return -1;}
 leases++;return 8;
}
static int all_write(int fd,const void *buf,size_t n) {
 if(fd!=8 || n!=40 || strcmp(buf,"0123456789012345678901234567890123456789")) _exit(206);
 return 0;
}
static int fake_fsync(int fd) {if(fd!=8)_exit(207);return 0;}
static int fake_close(int fd) {if(fd!=8)_exit(208);return 0;}
static ssize_t fake_write(int fd,const void *buf,size_t n) {
 if(fd!=2 || n>=384) _exit(209);
 writes++;
 if(is("write_error")) {errno=EPIPE;return -1;}
 if(is("short_write")) return (ssize_t)n-1;
 return write(fd,buf,n);
}
static _Noreturn void die(const char *stage) {
 fprintf(stderr,"REFUSAL stage=%s scans=%d infos=%d kills=%d lookups=%d leases=%d errno=%d writes=%d\n",
         stage,scans,infos,kills,lookups,leases,errno,writes);
 exit(2);
}
#define proc_listallpids fake_list
#define proc_pidinfo fake_info
#define kill fake_kill
#define getpwuid_r fake_pw
#define getgrgid_r fake_gr
#define openat fake_openat
#define fsync fake_fsync
#define close fake_close
#define write fake_write
'''
TRAILER=r'''
int main(int argc,char **argv) {
 if(argc!=3) return 210;
 scenario=argv[1];
 /* Production reserve callers are root observers that already ignore SIGPIPE. */
 if(signal(SIGPIPE,!strcmp(argv[2],"default") ? SIG_DFL : SIG_IGN)==SIG_ERR) return 211;
 errno=EINVAL;
 if(!strncmp(scenario,"direct_",7)) {
  scenario+=7;int result=process_count(UID_FIRST);
  printf("count=%d scans=%d infos=%d kills=%d errno=%d\n",result,scans,infos,kills,errno);return 0;
 }
 uid_t uid=reserve_uid(9,"0123456789012345678901234567890123456789");
 printf("uid=%u scans=%d infos=%d kills=%d lookups=%d leases=%d\n",
        (unsigned)uid,scans,infos,kills,lookups,leases);
 return 0;
}
'''

@unittest.skipUnless(sys.platform in ('linux','darwin'),'POSIX software only; no native credit')
class TestIdentitySnapshotDiagnostics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler=shutil.which("cc")
        if compiler is None: raise AssertionError("C compiler unavailable: infrastructure, not RED")
        cls.temporary=tempfile.TemporaryDirectory(prefix="identity-snapshot-software-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.binary=Path(cls.temporary.name)/"probe"
        built=subprocess.run([compiler,"-std=c11","-Wall","-Wextra","-Werror","-Wno-unused-function",
                              "-x","c","-","-o",str(cls.binary)],
                             input=program(LEASE_SOURCE).encode("ascii"),capture_output=True,timeout=30)
        if built.returncode or built.stdout or built.stderr:
            raise AssertionError("C infrastructure: "+built.stderr.decode("utf-8","replace"))
    def probe(self,scenario):
        actual=subprocess.run([str(self.binary),scenario,"ignore"],capture_output=True,timeout=5)
        self.assertLessEqual(len(actual.stdout)+len(actual.stderr),4096)
        return actual
    def rejection(self,scenario,stage="reserve-process-snapshot"):
        actual=self.probe(scenario)
        self.assertEqual(actual.returncode,2,actual.stderr)
        self.assertEqual(actual.stdout,b"")
        self.assertIn(("REFUSAL stage="+stage).encode(),actual.stderr)
        lines=[line for line in actual.stderr.splitlines() if line.startswith(b"M0A1_SNAPSHOT ")]
        self.assertEqual(len(lines),1,"IDENTITY_SNAPSHOT_REQUIRED")
        fields=dict(item.split("=",1) for item in lines[0].decode().split()[1:])
        self.assertEqual(fields.pop("stage"),stage)
        self.assertEqual(fields.pop("cleanup"),"unknown")
        return {key:int(value) for key,value in fields.items()},actual
    def test_list_zero_negative_and_full_capture_immediate_errno(self):
        for case,count,error in (("list_zero",0,errno.EBADF),("list_negative",-1,errno.ENOMEM),
                                 ("list_full",8192,errno.E2BIG)):
            with self.subTest(case=case):
                fields,actual=self.rejection(case)
                self.assertEqual(fields,dict(uid=60000,list_count=count,cap=8192,list_errno=error,
                    bad_index=-1,bad_pid=-1,info_result=-1,info_expected=24,info_errno=-1,kill_result=-1,kill_errno=-1))
                self.assertIn(b"scans=1 infos=0 kills=0 lookups=2 leases=0 errno=100",actual.stderr)
    def test_info_result_and_independent_kill_result_are_retained(self):
        for case,result,info_error,kill_result,kill_error in (
            ("info_zero",0,errno.EACCES,0,0),("info_short",23,errno.EIO,-1,errno.EPERM),
            ("info_negative",-1,errno.EBADF,-1,errno.EINVAL)):
            with self.subTest(case=case):
                fields,actual=self.rejection(case)
                self.assertEqual(fields,dict(uid=60000,list_count=1,cap=8192,list_errno=errno.EBADF,
                    bad_index=0,bad_pid=101,info_result=result,info_expected=24,info_errno=info_error,
                    kill_result=kill_result,kill_errno=kill_error))
                self.assertIn(b"scans=1 infos=1 kills=1 lookups=2 leases=0 errno=100",actual.stderr)
    def test_first_decisive_unknown_after_existing_esrch_rule(self):
        fields,actual=self.rejection("info_chain")
        self.assertEqual(fields["bad_index"],1)
        self.assertEqual(fields["bad_pid"],102)
        self.assertEqual(fields["kill_errno"],errno.EPERM)
        self.assertIn(b"scans=1 infos=2 kills=2",actual.stderr)
    def test_post_lease_unknown_keeps_original_stage(self):
        fields,actual=self.rejection("post_unknown","reserve-contaminated")
        self.assertEqual(fields["list_count"],0)
        self.assertEqual(fields["list_errno"],errno.EBADF)
        self.assertIn(b"scans=2 infos=1 kills=0 lookups=2 leases=1",actual.stderr)
    def test_skipped_directory_identities_do_not_emit_stale_unknown(self):
        for case,lookups in (("skip_pw",3),("skip_gr",4)):
            with self.subTest(case=case):
                actual=self.probe(case)
                self.assertEqual(actual.returncode,0,actual.stderr)
                self.assertEqual(actual.stderr,b"")
                self.assertEqual(actual.stdout,
                    f"uid=60001 scans=3 infos=2 kills=0 lookups={lookups} leases=1\n".encode())
    def test_lookup_error_is_not_consumption_of_snapshot(self):
        actual=self.probe("lookup_error")
        self.assertEqual(actual.returncode,2)
        self.assertNotIn(b"M0A1_SNAPSHOT ",actual.stderr)
        self.assertIn(b"REFUSAL stage=uid-directory-lookup",actual.stderr)
    def test_normal_collision_and_full_positive_count_stay_silent(self):
        for case,uid,scans,infos in (("valid",60000,2,2),("collision",60001,3,3),
                                    ("lease_collision",60001,3,3),("near_cap",60000,2,2),
                                    ("nonpositive",60000,2,2)):
            with self.subTest(case=case):
                actual=self.probe(case)
                self.assertEqual(actual.returncode,0,actual.stderr)
                self.assertEqual(actual.stderr,b"")
                self.assertEqual(actual.stdout,
                    f"uid={uid} scans={scans} infos={infos} kills=0 lookups={2*(scans-1)} leases=1\n".encode())
        actual=self.probe("post_positive")
        self.assertEqual(actual.returncode,2)
        self.assertNotIn(b"M0A1_SNAPSHOT ",actual.stderr)
        self.assertIn(b"REFUSAL stage=reserve-contaminated",actual.stderr)
    def test_existing_esrch_continue_and_all_six_identity_fields(self):
        actual=self.probe("info_esrch")
        self.assertEqual(actual.returncode,0,actual.stderr)
        self.assertEqual(actual.stderr,b"")
        self.assertEqual(actual.stdout,b"uid=60000 scans=2 infos=2 kills=2 lookups=2 leases=1\n")
        actual=self.probe("direct_six_fields")
        self.assertEqual(actual.returncode,0,actual.stderr)
        self.assertEqual(actual.stderr,b"")
        self.assertEqual(actual.stdout,f"count=6 scans=1 infos=6 kills=0 errno={errno.EACCES}\n".encode())
    def test_legacy_wrapper_has_no_immediate_diagnostic(self):
        for case,result,infos,kills,error in (("list_zero",-1,0,0,errno.EBADF),
                ("info_zero",-1,1,1,0),("info_short",-1,1,1,errno.EPERM),
                ("info_esrch",0,1,1,errno.ESRCH),("valid",0,1,0,errno.EACCES)):
            with self.subTest(case=case):
                actual=self.probe("direct_"+case)
                self.assertEqual(actual.returncode,0,actual.stderr)
                self.assertEqual(actual.stderr,b"")
                self.assertEqual(actual.stdout,
                    f"count={result} scans=1 infos={infos} kills={kills} errno={error}\n".encode())
    def test_write_error_and_short_write_do_not_change_failure(self):
        for case in ("write_error","short_write"):
            with self.subTest(case=case):
                actual=self.probe(case)
                self.assertEqual(actual.returncode,2,actual.stderr)
                self.assertEqual(actual.stdout,b"")
                self.assertIn(b"REFUSAL stage=reserve-process-snapshot",actual.stderr)
                self.assertIn(b"errno=100 writes=1",actual.stderr)
    def test_real_broken_pipe_uses_verified_observer_signal_precondition(self):
        for mode,status in (("ignore",2),("default",-signal.SIGPIPE)):
            with self.subTest(mode=mode):
                reader,writer=os.pipe();os.close(reader)
                try:
                    actual=subprocess.run([str(self.binary),"list_zero",mode],stdout=subprocess.PIPE,
                                          stderr=writer,restore_signals=True,timeout=5)
                finally: os.close(writer)
                self.assertEqual(actual.returncode,status)
                self.assertEqual(actual.stdout,b"")
    def test_all_real_emitter_paths_are_after_existing_sigpipe_ignore(self):
        driver=(ROOT/"native/mac/tests/icode_m0a1_driver.c").read_text()
        groups=(ROOT/"native/mac/tests/icode_m0a1_process_groups_native.c").read_text()
        vectors=(ROOT/"native/mac/tests/icode_m0a2_vectors.c").read_text()
        for source,call in ((driver,"uid_t uid=reserve_uid(leases,argv[1]);"),
                            (groups,"uid_t positive=reserve_unused_id(leases)"),
                            (vectors,"run_case((int)i,ledger,leases,os,u.release,u.machine);")):
            with self.subTest(call=call):
                # Main, not any worker branch, must establish the existing condition first.
                main=source[source.index("int main("):]
                self.assertIn(call,main)
                self.assertLess(main.rfind("signal(SIGPIPE,SIG_IGN)",0,main.index(call)),main.index(call))
                self.assertGreaterEqual(main.rfind("signal(SIGPIPE,SIG_IGN)",0,main.index(call)),0)

if __name__=="__main__":
    unittest.main()
```

### Asset B: native/mac/tests/icode_m0a1_identity_lease.inc

```diff
*** Begin Patch
*** Update File: native/mac/tests/icode_m0a1_identity_lease.inc
@@ -18,16 +18,40 @@
     e=errno; endgrent();
     if(e) { errno=e; die("group-enumeration"); }
 }
-static int process_count(uid_t uid) {
+/* IDENTITY_SNAPSHOT_DIAGNOSTIC_BEGIN */
+struct process_snapshot {
+    int list_count,list_errno,bad_index,bad_pid,info_result,info_expected,info_errno,kill_result,kill_errno;
+};
+static void emit_process_snapshot(const char *stage,uid_t uid,const struct process_snapshot *s) {
+    /* Only root observers consume this on a terminal refusal, after SIGPIPE=SIG_IGN. */
+    int saved=errno;
+    char line[384];
+    int n=snprintf(line,sizeof(line),
+        "M0A1_SNAPSHOT stage=%s uid=%u list_count=%d cap=%d list_errno=%d bad_index=%d bad_pid=%d info_result=%d info_expected=%d info_errno=%d kill_result=%d kill_errno=%d cleanup=unknown\n",
+        stage,(unsigned)uid,s->list_count,MAX_PIDS,s->list_errno,s->bad_index,s->bad_pid,
+        s->info_result,s->info_expected,s->info_errno,s->kill_result,s->kill_errno);
+    if(n>0 && n<(int)sizeof(line)) (void)write(2,line,(size_t)n);
+    errno=saved;
+}
+/* IDENTITY_SNAPSHOT_DIAGNOSTIC_END */
+/* IDENTITY_SNAPSHOT_ALGORITHM_BEGIN */
+static int process_count_snapshot(uid_t uid,struct process_snapshot *s) {
     pid_t pids[MAX_PIDS]; int n=proc_listallpids(pids,sizeof(pids)),count=0;
+    int list_errno=errno;
+    *s=(struct process_snapshot){n,list_errno,-1,-1,-1,(int)sizeof(struct proc_bsdinfo),-1,-1,-1};
     if(n<=0 || n>=MAX_PIDS) return -1;
     for(int i=0;i<n;i++) {
         if(pids[i]<=0) continue;
         struct proc_bsdinfo b;
         int r=proc_pidinfo(pids[i],PROC_PIDTBSDINFO,0,&b,sizeof(b));
+        int info_errno=errno;
         if(r!=(int)sizeof(b)) {
             errno=0;
-            if(kill(pids[i],0)<0 && errno==ESRCH) continue;
+            int exists=kill(pids[i],0);
+            int kill_errno=errno;
+            if(exists<0 && kill_errno==ESRCH) continue;
+            s->bad_index=i;s->bad_pid=(int)pids[i];s->info_result=r;
+            s->info_errno=info_errno;s->kill_result=exists;s->kill_errno=kill_errno;
             return -1;
         }
         if(b.pbi_ruid==uid || b.pbi_uid==uid || b.pbi_svuid==uid ||
@@ -35,6 +59,11 @@
     }
     return count;
 }
+static int process_count(uid_t uid) {
+    struct process_snapshot snapshot;
+    return process_count_snapshot(uid,&snapshot);
+}
+/* IDENTITY_SNAPSHOT_ALGORITHM_END */
 static int lease_directory(void) {
     int fresh=mkdir(lease_root,0700)==0;
     if(!fresh && errno!=EEXIST) die("lease-mkdir");
@@ -59,7 +88,8 @@
 static uid_t reserve_uid(int dir,const char *sha) {
     for(unsigned i=0;i<UID_COUNT;i++) {
         if(unavailable[i]) continue;
-        uid_t uid=UID_FIRST+i; int before=process_count(uid);
+        uid_t uid=UID_FIRST+i; struct process_snapshot before_snapshot;
+        int before=process_count_snapshot(uid,&before_snapshot);
         char lookup[16384]; struct passwd pw,*pw_result=NULL; struct group gr,*gr_result=NULL;
         int lookup_error=getpwuid_r(uid,&pw,lookup,sizeof(lookup),&pw_result);
         if(lookup_error) { errno=lookup_error; die("uid-directory-lookup"); }
@@ -67,14 +97,20 @@
         lookup_error=getgrgid_r(uid,&gr,lookup,sizeof(lookup),&gr_result);
         if(lookup_error) { errno=lookup_error; die("gid-directory-lookup"); }
         if(gr_result) continue;
-        if(before<0) die("reserve-process-snapshot");
+        if(before<0) {
+            emit_process_snapshot("reserve-process-snapshot",uid,&before_snapshot);
+            die("reserve-process-snapshot");
+        }
         if(before) continue;
         char name[32]; snprintf(name,sizeof(name),"uid-%u",uid);
         int f=openat(dir,name,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
         if(f<0 && errno==EEXIST) continue;
         if(f<0 || all_write(f,sha,40) || fsync(f)<0 || close(f)<0) die("reserve-lease");
         unavailable[i]=1;
-        if(process_count(uid)!=0) die("reserve-contaminated");
+        struct process_snapshot after_snapshot;
+        int after=process_count_snapshot(uid,&after_snapshot);
+        if(after<0) emit_process_snapshot("reserve-contaminated",uid,&after_snapshot);
+        if(after!=0) die("reserve-contaminated");
         return uid;
     }
     errno=ENOSPC; die("reserve-exhausted"); return 0;
*** End Patch
```

### Asset C: tests/test_macos_process_groups_native.py

```diff
*** Begin Patch
*** Update File: tests/test_macos_process_groups_native.py
@@ -187,6 +187,49 @@
         if marker in content:
             self.assertEqual(content.count(marker),1)
             lease=(driver.parent/"icode_m0a1_identity_lease.inc").read_bytes()
+            if b"/* IDENTITY_SNAPSHOT_DIAGNOSTIC_BEGIN */\n" in lease:
+                self.assertEqual(hashlib.sha256(lease).hexdigest(),
+                    "3c8e74cffa0dfda2fc8e7cf91e67cd6db99c7a5c88167ab9c95925887356ada5")
+                # Strip only the reviewed diagnostic projection; keep the original hash below.
+                diagnostic=rb"/\* IDENTITY_SNAPSHOT_DIAGNOSTIC_BEGIN \*/\n.*?/\* IDENTITY_SNAPSHOT_DIAGNOSTIC_END \*/\n"
+                algorithm=rb"/\* IDENTITY_SNAPSHOT_ALGORITHM_BEGIN \*/\n.*?/\* IDENTITY_SNAPSHOT_ALGORITHM_END \*/\n"
+                self.assertEqual(len(re.findall(diagnostic,lease,re.S)),1)
+                self.assertEqual(len(re.findall(algorithm,lease,re.S)),1)
+                original_count=b"""static int process_count(uid_t uid) {
+    pid_t pids[MAX_PIDS]; int n=proc_listallpids(pids,sizeof(pids)),count=0;
+    if(n<=0 || n>=MAX_PIDS) return -1;
+    for(int i=0;i<n;i++) {
+        if(pids[i]<=0) continue;
+        struct proc_bsdinfo b;
+        int r=proc_pidinfo(pids[i],PROC_PIDTBSDINFO,0,&b,sizeof(b));
+        if(r!=(int)sizeof(b)) {
+            errno=0;
+            if(kill(pids[i],0)<0 && errno==ESRCH) continue;
+            return -1;
+        }
+        if(b.pbi_ruid==uid || b.pbi_uid==uid || b.pbi_svuid==uid ||
+           b.pbi_rgid==uid || b.pbi_gid==uid || b.pbi_svgid==uid) count++;
+    }
+    return count;
+}
+"""
+                lease=re.sub(diagnostic,b"",lease,count=1,flags=re.S)
+                lease=re.sub(algorithm,lambda _:original_count,lease,count=1,flags=re.S)
+                lease=lease.replace(
+                    b"uid_t uid=UID_FIRST+i; struct process_snapshot before_snapshot;\n"
+                    b"        int before=process_count_snapshot(uid,&before_snapshot);",
+                    b"uid_t uid=UID_FIRST+i; int before=process_count(uid);",1)
+                lease=lease.replace(
+                    b'if(before<0) {\n'
+                    b'            emit_process_snapshot("reserve-process-snapshot",uid,&before_snapshot);\n'
+                    b'            die("reserve-process-snapshot");\n'
+                    b'        }',b'if(before<0) die("reserve-process-snapshot");',1)
+                lease=lease.replace(
+                    b"struct process_snapshot after_snapshot;\n"
+                    b"        int after=process_count_snapshot(uid,&after_snapshot);\n"
+                    b'        if(after<0) emit_process_snapshot("reserve-contaminated",uid,&after_snapshot);\n'
+                    b'        if(after!=0) die("reserve-contaminated");',
+                    b'if(process_count(uid)!=0) die("reserve-contaminated");',1)
             content=content.replace(marker,lease,1)
         self.assertEqual(hashlib.sha256(content).hexdigest(),
             "a65f067ec9c6b32eb3bb7cc7afd803fe465d02273b5484561b237db59c31f673")
*** End Patch
```

### Asset D: scripts/run_macos_m0_ci.py

```diff
*** Begin Patch
*** Update File: scripts/run_macos_m0_ci.py
@@ -297,6 +297,8 @@
             "native/mac/tests/icode_m0a1_unused_identity.inc",
             "native/mac/tests/icode_m0a1_process_groups_native.c",
             "tests/test_macos_process_groups_native.py",
+            "tests/test_macos_identity_snapshot_diagnostics.py",
+            "docs/nbl/plans/2026-10-15-macos-identity-snapshot-diagnostics.md",
             "tests/test_macos_process_groups.py",
             "tests/test_macos_task_quota_probe.py",
             "native/mac/CMakeLists.txt",
*** End Patch
```

### Asset E: scripts/run_macos_m0a2_vectors.py

```diff
*** Begin Patch
*** Update File: scripts/run_macos_m0a2_vectors.py
@@ -276,6 +276,8 @@
             "tests/test_macos_task_quota_probe.py","tests/test_macos_process_groups_native.py",
             "tests/test_macos_process_groups.py","tests/test_macos_m0a2_vectors.py",
             "tests/test_macos_m0a2_event_diagnostics.py",
+            "tests/test_macos_identity_snapshot_diagnostics.py",
+            "docs/nbl/plans/2026-10-15-macos-identity-snapshot-diagnostics.md",
             "docs/nbl/plans/2026-10-14-macos-m0a2-event-diagnostics.md",
             "scripts/run_macos_m0_ci.py","scripts/run_macos_m0a2_vectors.py",
             "native/mac/CMakeLists.txt",".github/workflows/ci.yml",
*** End Patch
```

### Asset F: .github/workflows/ci.yml

```diff
*** Begin Patch
*** Update File: .github/workflows/ci.yml
@@ -2406,6 +2406,9 @@
         uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97
         with:
           python-version: "3.11"
+      - name: Identity snapshot diagnostic software contract
+        shell: bash
+        run: python -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_macos_identity_snapshot_diagnostics.py'); assert s.countTestCases()==12, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
       - name: Build the TESTOnly wrong baseline without SOURCE
         shell: bash
         run: |
*** End Patch
```

## 8. 投影与资产摘要

|未来文件|行数|SHA256|
|---|---:|---|
|tests/test_macos_identity_snapshot_diagnostics.py|299|ec4c4c552203548d399b07d5aafd1ff59a71530f6982d115839d00c2f43b0d96|
|native/mac/tests/icode_m0a1_identity_lease.inc|117|3c8e74cffa0dfda2fc8e7cf91e67cd6db99c7a5c88167ab9c95925887356ada5|
|tests/test_macos_process_groups_native.py|528|c87354483a29ffaa412c83f623af1d0f8f73b03aff4d44975bc36ab47aa60475|
|scripts/run_macos_m0_ci.py|431|d6bceacd396b95580c3abfe281b9a2d8a80d3d219a52e18944c05abd03723938|
|scripts/run_macos_m0a2_vectors.py|330|ff21e16cc166fb9298c78b1be28f7be0c428ad40ec9ae1272fbfaec0094de69b|
|.github/workflows/ci.yml（root加F并保留notice D后的最终组合）|2511|c331b43681964eae1d62543b15fe1c43d4f4c6bbab346a33c5184c2d573cb5ca|

|资产|行数|SHA256|hunks|
|---|---:|---|---:|
|A完整TEST|299|ec4c4c552203548d399b07d5aafd1ff59a71530f6982d115839d00c2f43b0d96|新增文件|
|B patch|91|488d119562cc0a53e06413b570a7efdebee5f44c65d75555b996c546f84dccc6|4|
|C patch|53|ba97d1791baee9117c73ba6d405cd8d9f197e56b0d658a90717cfb08dc880c21|1|
|D patch|12|b81baf2c661155a58c1ee04c940c8b14f7efa006173c603431b15bf781eb3c51|1|
|E patch|12|2e0515dc00a007bcbe7c0f2e1bf41944194e863c2d6471a5d8cc42acac963374|1|
|F patch|13|12f8eea218d73f75206f3a9aff190d7b855d35c92489f430657ae6d7803799f1|1|

## 9. 自审与边界

SPEC自审：两拒绝消费者、局部即时结果、成功静默、原unknown/arg0/8192/UID/lease/调用次数全保留；新TEST真实提取算法而不复制生产算法，旧版本无helper仍可编译并取得语义RED。旧inverse目标a65保持，controllers只加两个摘要路径，F由root后续组合且只增严格软件一步。 修订I1已按完整lease哈希门封闭；匿名实际旧inverse精确批准投影1P/0.001s，marker内count++→count+=2的单条逻辑篡改被该门以1Assertion/0ERRORskip拒绝/0.001s，未到原a65断言；新C正投影及唯一逆回485L原输入通过。未重跑未变新12、旧全套或原生；旧探索结果仅保留历史信用。

QUALITY自审：无全局缓存/新增扫描，完整结构字段仅在相应读取成功时解释；bad只记第一个决定拒绝的PID，不让已消失PID替下一处未知背锅。固定一行≤293B/384缓冲不重试，emit恢复原errno，真实断管依赖已核根观察者SIG_IGN。破坏该前提负控明确暴露-13，不向未来消费者提供虚假的通用安全保证。机械inverse不替代新算法行为测试或原生观察。

【架构级自检报告】
✅ 语法/编译：冻结TEST/投影Python AST、小C软件probe严格编译通过；完整Darwin SDK未做。
✅ 依赖/调用链：A/W1/B共享调用逐处核，两个真实消费点才emit；manifest与旧inverse配套。
✅ 逻辑/边界：list边界/info长度/kill0分支、目录优先、before/post、六凭据字段与静默正控覆盖。
✅ 异常处理：短写/EPIPE/真实无读端pipe和信号前提破坏，保留原拒绝/退出与unknown。
✅ 关联模块：C新增完整批准lease哈希门，篡改负控必拒绝；原a65目标保持，944c/eb51原目标不变。F-on8045精确2511/c331及逆回8045；双顺序为root独立回报。
✅ 兼容安全：原profile/配额/成功ACK/UID池/扫描次数/arg0/原接受门不变，无root系统操作。
✅ 可运行性：完整资产与严格命令可执行；仅匿名软件预演信用，正式独立TDD、实际双审及双Mac仍待验，不写100%。

---
**Execution Mode:** serial。STOP：只交唯一PLAN，等root全文和fresh SPEC → 不同QUALITY；不得自动执行资产、stage/commit/push、native/system/full、re-run/cancel或放宽准入。
