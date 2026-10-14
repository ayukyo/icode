# macOS M0a2 data-event-contract 有界诊断 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL nbl.executing-plans，仅本PLAN经root全文＋fresh SPEC→不同QUALITY全0后使用。当前PLAN ONLY；用户main-only及独立TEST/不同SOURCE覆盖技能默认worktree、自动执行和提交建议。
> **Goal:** 区分现有M0a2数据接收失败分支及launch85的当次OS错误，只增加有界诊断，不修quota、不放宽profile。
> **Architecture:** 仅新固定软件TEST＋vectors C私有诊断reader/guard/launch breadcrumb；共享helper和成功协议不变。controller只记录新增源码摘要，CI仅增加一个严格软件步骤。
> **Tech Stack:** C11/POSIX软件OS边界、Python3.11 unittest、既有两Mac CI；无新依赖、系统权限或原生服务。

## 1. 事实、问题与授权

root回报实际候选5ad08dd9708ad36c495f1ad719dbc14ac7f298a8：旧A两架构各18通过并独立核原件；新B ARM115944828995/Intel115944828636均native_exit2，stderr只有M0A2 stage=data-event-contract errno22 cleanupunknown，stdout0，无sealed audit/manifest/formal。构建/binding/22sourcehash匹配。这是基础设施失败，不是quota RED。root实际sequential-thinking 2ec721三步accepted：read_result/packet/kind/member/earlypayload分离，不据残留errno22定因；本作者不冒称亲调工具。

只读源码已确认：原guard把count/read_record/packet/kind/member五类OR合一；共享read_record返回错误码不设置errno，die使用残留errno。launch_child在sandbox后open /dev/null O_RDWR|O_CLOEXEC，profile为denydefault且未显式允许该路径写；该处是待原生验证的首要假设，不是已证根因。无childexit/分支证据不能由open表达式或errno22断言原因。固定FD符号模型无冲突也不是Darwin运行证明。

三问：真实问题是拒绝原因不可分辨；现有原helper/collector/固定C路径可复用；仅数据路径和launch85失败输出，原成功ACK/gate/协议/oracle调用链不变。推荐本片仅观测，不移除open、不预开FD修绕过、不改Seatbelt profile、不扩cap。root允许省略waitid：不新增root终态采样，不编造si_pid/code/status，未知保持unknown。

起草历史：root当时回报主CI38590561344全部50终态43S/4F/3skip，prov38590561256仍在途；该在途描述不再是当前状态。root现回报全部57终态50S/4F/3skip。状态来自root，不是本作者独立API查询，也不是发布授权。仍须本文fresh双审、独立正式TEST/不同SOURCE和实际双审后才可由root单独发布；当前不push/cancel/re-run，不借诊断授权系统/native、账号或其它修复。

修订账：前冻结597L/3f63d3e9ce6a8115c952a98a674d44a8bae013bf12b5c18d24f9cf83e9739343，freshSPEC最终C0/I1/M1。作者13a0bf匿名软件复现两真实stderr断管均-13，确认I1；root实际sequential-thinking 192e89三步accepted本局部mask方案，仅记录回报，不冒作者亲调。以下完整资产取代旧诊断资产，仍需freshSPEC→不同QUALITY，不因此解冻实施。

## 2. 冻结输入与未来唯一四路径

|输入|行数|SHA256|
|---|---:|---|
|native/mac/tests/icode_m0a2_vectors.c|675|c65a88c3f416948ed4df14639870885784c64832975dfe333a620329eea530c2|
|native/mac/tests/icode_m0a1_fixed_helpers.inc（不改）|203|de74f6b77a9d91fd3d9fdf2801adfe4dc8685ff685480a7b09bb0e9c58f10546|
|scripts/run_macos_m0a2_vectors.py|326|9aed0af65ef16a69d8f55f929238593038a190b0cbf9f863173af57e8fae648e|
|.github/workflows/ci.yml|2496|25ce291318d265335d8ec0a1b54050dd49adcf70e8229dc96c8a49f8702f8fd1|
|tests/test_macos_m0a2_vectors.py（不改）|990|f924880a575c6e11aebac1fdbaa1d114691e1fe88c59fb1093a22e18b510285e|
|tests/test_macos_process_groups_native.py（不改）|485|78e30df5c19ab97feb9eabcdf6f314602b7df96399b5ba6a7fbe8d6fdaf21927|
|native/mac/icode_m0a1_limit.c（不改）|16|507b26a2d2ff1cca663c4c52f8ead50b1a4991563f1942e0f7d2a8f39dcc208c|
|批准M0a2 DESIGN|152|39e4b5675e0864cd9daeef683f48b1e5e60b3f9138cb5fe0761d70314a62540e|
|批准vectors PLAN（原12fence＋兼容附录保留）|3084|2728eff0afa229037b9e854468c2d41aad607528d6df0443732d3de9aa7cded3|

未来四路径仅：新增tests/test_macos_m0a2_event_diagnostics.py；修改native/mac/tests/icode_m0a2_vectors.c、scripts/run_macos_m0a2_vectors.py、.github/workflows/ci.yml。新TEST必须不存在；输入漂移先核差异重审，不覆盖并行dirty。本文作者本轮只新增此PLAN，不修改任何上述文件、原vectorsPLAN或root进度文档。

## 3. 诊断合同、优先级与预算

|诊断|固定字段/含义|失败线|
|---|---|---|
|M0A2_DATA|case、event_count、reason、read_result、received、last_kind/last_slot、cleanup=unknown|仍die data-event-contract、exit2、stdout空|
|reason=count|++event_count>64，read_result=-1表示未尝试read，received0|不额外poll/read、不读包字段|
|reason=read|返回码为当次EPIPE/ETIMEDOUT/errno；received为实际成功累计字节|完整包前不读任何字段，errno22不覆盖返回码|
|reason=packet/slot|完整包后原packet_valid拒绝；slot>=8标slot，其余标packet|不索引members，若同时坏magic及slot，仍原packet层拒绝并标slot|
|reason=kind|原START..DONE范围拒绝|先packet/slot检查|
|reason=member|有效slot未登记PID|仅packet_valid证明slot<8后索引|
|M0A2_LAUNCH|case、slot、child_slot、stage、saved_errno、exit85、cleanupunknown|保持原_exit85；无fork/spawn成功信用|
|launch stage白名单|open/dup2/close/fcntl8/pipe/fcntl_read/fcntl_write|保持原短路顺序，错误当次立即取errno|

last_kind/last_slot初始-1；仅record_event已接受packet/独立身份后更新，表示最近通过该数据层的header，不冒称后续分支/exec/回收已成功。只读取完整包，不打印未初始化bytes或任意payload。所有新输出只固定标签和整数，不dump argv/env/path/UID列表，不将普通stderr提升为可信root ledger或配额oracle。

新增read_data_record仅用于data[0]：原poll11000ms/EINTR重试及随后all_read相同短路/返回语义，逐read累计received；不改共享all_read/read_record。保留原15秒case alarm/整体480秒、子alarm10、任务CPU2/FSIZE64KiB、新observer20与旧W1CPU10；EINTR仍受原case/整体alarm，不给重试新deadline。count上限64先于I/O，完整包大小/成功事件顺序/ACK完全不变。格式化/诊断write失败或短写仍原exit85/exit2，不重试、不放行、不增加任务/线程或profile权限。

两个_Noreturn失败函数在任何诊断输出前，仅当前执行线程局部SIG_BLOCK(SIGPIPE)：sigemptyset/sigaddset/sigprocmask任一失败，立即跳过全部输出并保留85或2。data路径在mask失败时只机械复用原die的owned直接子kill循环后_exit(2)，不调用会输出的die、不增强清理信用；launch仍_exit(85)。mask成功后不恢复，因为路径必终结，避免pending SIGPIPE在恢复时替换退出码。没有全局SIG_IGN或成功路径信号改变。真实无读端pipe负控使用默认SIGPIPE，非stub EPIPE，必须得到85/2而不是-13。

每条launch缓冲192、data缓冲256字节，输出长度超界直接不写；单次write最多191/255字节，stderr失败不改变失败结论。本B实际≤6任务，只有失败时各至多一launch行＋observer一data行，新增最坏≤1401字节，低于2KiB。collector原stdout≤512、stdout+stderr合计≤65536、job16MiB/10min/48case、单case15秒/64KiB、UID1024池均不放宽；不新增成功路径日志或case。stderr非空或native_exit2仍基础设施拒绝，不发布vectors-result/combinedsuccess，原failure artifact照常有界保留。

不新增waitid、reap/kill未知、树supervisor、状态轮询或任务UID内watchdog；原ownedroot清理照旧，root终态未观察，整树unknown，不因诊断行出现而声称cleanup通过。

## 4. TEST真实RED及覆盖映射

新TEST12方法直接提取当前真实C event/member/enum/packet_valid/die/launch_child/require_ack，以及实际while guard；旧源码没有新helper时执行真实旧guard＋共享read_record/all_read，不以helper缺失/签名/import/compile错误充RED。新源码提取真实新增helper和接线。软件仅stub poll/read/open/dup2/close/fcntl/pipe/fork/spawn/exec/write等OS边界，fork/spawn在故障阶段到达即trap；被测C不会实际fork/改rlimit/身份或调用Darwin/root。测试断言来自真实返回/exit/输出/FD8、marker和ACK流，不按mock存在判通过。新增仅1方法，总12。真实断管使用os.pipe关闭读端；probe启动显式SIG_DFL及空mask，正常sigset/mask操作执行真实软件OS调用；另对三操作分别注入失败。mask失败data分支将synthetic owned PID777交唯一model_kill计数，model_exit核确实执行原终止动作，绝不发送真实kill或增加清理信用。

|方法|实际正负控|
|---|---|
|launch_open_refusal|open EACCES→85，savederrno准确且未到fork/spawn|
|launch_other_setup_failures|其余6阶段逐一失败，白名单及当次errno|
|launch_setup_keeps_fd8|reserved6→dup8及reserved8原位；fork/spawn API均EAGAIN，原marker关闭和ACK|
|eof|原read返回EPIPE，旧残留errno22不能伪装本次原因|
|partial|先7字节再EOF，received7，不读字段|
|timeout_poll_read_errors|timeout、poll EBADF、read EIO，优先级正确|
|full_packet_rejections|magic/version/length/kind/UINT32_MAX slot/未登记member|
|count_limit|第65次先拒绝，OS poll若发生立即trap|
|valid_and_eintr|完整包/先EINTR两路径仍通过且无stderr|
|diagnostic_write_failure|stub EPIPE/短写及三种sigset/mask调用失败，仍85/2；mask失败stderr必须空|
|real_broken_stderr_pipe|真实os.pipe关闭读端、默认SIGPIPE，launch/data仍85/2，不以stub代替|
|second_failure|首包接受后EOF，last_kind1/slot0及count2|

旧软件正式预期：12方法中10失败方法/27 AssertionError记录、2正控方法通过、0ERROR/0skip；固定诊断字段以M0A2_DIAGNOSTIC_DATA_REQUIRED/M0A2_DIAGNOSTIC_LAUNCH_REQUIRED断言，另有真实SIGPIPE退出码与mask失败静默断言；不要求所有失败都同一消息。旧真实guard本来已failclosed，只是缺新诊断；这是诊断行为语义RED，不是quota绕过或V3 quotaRED。compile/fixture/loader/工具不可用均基础设施ERROR，不能获RED信用；不松断言补绿。

当前作者仅做匿名RAM小诊断，尚非正式独立TEST落地：本修订新12对旧675L真实代码27 assertion记录/0ERRORskip；对先前726L诊断投影14 assertion记录/0ERRORskip（6个mask失败场景＋8个真实断管/组合场景）；736L局部mask投影12GREEN/0ERRORskip。先前版本的11/20记录仅历史，不替本修订正式门。早期草案发现_Noreturn调用未标注die的编译错误，已在资产中用显式_exit(2)封闭；该错误不计RED。冻结版本正式TDD仍由独立TEST作者先落地并保留真实命令/输出/exit，再不同DIAGNOSTIC SOURCE作者实施。

## 5. 串行任务和停止门

### Task 1：独立TEST ONLY → 正式诊断RED

**Dependencies:** root全文本PLAN＋fresh SPEC→不同QUALITY全0。
**Parallelizable:** No（独立TEST先行）。
- [ ] 核全部输入、路径不存在；只apply_patch新增附录A完整TEST，末LF/hash一致；不提前改C/controller/CI。
- [ ] 运行下列strict命令，count12；应是上述语义assertionRED、0ERROR/0skip、exit1。独立实际TEST审和root核原件；不是本作者RAM替代。
- [ ] 原新15默认9P/6skip、optin9P/唯一APIassertF/5skip，旧groups13P0skip均保持；只定点，不本机全量/native/root。

~~~bash
python3 -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_macos_m0a2_event_diagnostics.py'); assert s.countTestCases()==12, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
python3 -B -m unittest discover -s tests -p test_macos_m0a2_vectors.py -v
ICODE_M0A2_LIMIT_SOFTWARE=1 python3 -B -m unittest discover -s tests -p test_macos_m0a2_vectors.py -v
python3 -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_macos_process_groups*.py'); assert s.countTestCases()==13; r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
~~~

### Task 2：不同DIAGNOSTIC SOURCE，严格三patch

**Dependencies:** Task1正式语义RED＋独立TEST审。
**Parallelizable:** No。
- [ ] 不同作者只apply_patch附录B/C/D三个精确patch；TEST字节冻结。quota limit/profile/sharedhelpers/原wire/oracle/classification/原vectorsPLAN不改。
- [ ] strict新12全部GREEN/0ERRORskip；原15/13结果同Task1。源码完整diff、输入与投影hash/AST/逆还原匹配；编译默认-j1。
- [ ] 作者SPEC/QUALITY自审，再root fresh actualSPEC→不同QUALITY；未清零不stage/push，不改TEST断言。两MacC完整SDK编译仍在线上，不冒称软件probe证明Darwin。

### Task 3：root同候选CI有界观察，然后停止

**Dependencies:** Task2实际双审清零＋root确认全部在途run终态。
**Parallelizable:** No（root单独发布）。
- [ ] root才可main-only发布待验诊断候选；不建branch/tag、不取消或反复重跑掩失败。CI多1个strict12软件步骤，仍M0A2_SOURCE=0，不开启SOURCE向量/扩cap。
- [ ] 同新SHA旧A两架构各18及W0/W1原件重核；B记录actualSDK/object/final/binary/hash与新24 baseline sourcehash（原22＋新TEST/本PLAN）。controller/API/oracle未放宽，SOURCE假如未来另解冻才25，不把未来形态当本片运行。
- [ ] B仍可能native_exit2、无manifest/audit/formal；这时保留native.stderr/stdout、metadata/rawhash/exit及完整原件，按固定字段区分原因，只报告ERROR/unknown。没有stderr时也不得编造根/child状态。若收到launch open EACCES breadcrumb，只能报告该已观察阶段拒绝；另行设计最小修复，不在诊断片移除open或增权限。
- [ ] 若意外得到完整V3真实RED，也须原严格5formal/唯一第三forkassert/首byte/同SHA原件独立核，不能由诊断软件GREEN自动授Task3 quotaSOURCE。当前没有此证据，cap2/CI1继续禁；C22/D32/E32/M0b/M1、R2/R3与ready仍阻断。

## 6. 原件绑定与不变量

新增controller只给sources tuple加tests/test_macos_m0a2_event_diagnostics.py及本PLAN两路径；现有C/controller/CI条目自然摘要新字节。无新parser/接受函数/result分类，不把diagnostic行解析为成功。实际metadata先写stdout/stderr摘要/exit再按原失败分支拒绝，always artifact保留；该证据可独立绑定候选SHA、run/job/attempt/OS/arch/SDK/compileargv/object/final。出错不补sealedledger、不将半账本当audit，不以源码摘要替运行证据。

旧A/W0/W1共享helper与普通_getgroups、四ID/组predicate、lease/identity/所有原guard仍冻结；新C诊断不会改原A TEST exactinverse。新增TEST只读实际C源码，不导入或复制生产quota算法，OSstub不能授native或hardquota信用。payload/root无新FD、无通用入口、无新增文件/权限/账户操作。

## 7. 完整冻结资产

围栏正文保留唯一末LF。patch可直接apply_patch；若不接受GNU行号，仅规范化@@头，正文不变。当前仅保存本文，以下未执行。

### Asset A: tests/test_macos_m0a2_event_diagnostics.py

```python
"""M0a2 diagnostic-only software contract; no Darwin/root/fork execution."""
import errno
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
CFILE=ROOT/"native/mac/tests/icode_m0a2_vectors.c"
HELPER=ROOT/"native/mac/tests/icode_m0a1_fixed_helpers.inc"

def function(source,name):
    matches=list(re.finditer(r"^static [^\n]*\b"+re.escape(name)+r"\([^;]*?\{",source,re.M))
    if len(matches)!=1:
        raise AssertionError("actual C function must be unique: "+name)
    match=matches[0];brace=match.end()-1;depth=0
    tokens=r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*.*?\*/|//[^\n]*|[{}]'
    for token in re.finditer(tokens,source[brace:],re.S):
        if token[0]=="{": depth+=1
        elif token[0]=="}":
            depth-=1
            if depth==0:
                return source[match.start():brace+token.end()]+"\n"
    raise AssertionError("actual C function braces incomplete: "+name)

def probe_source(source,shared):
    event=re.search(r"^struct event \{.*?^\};\n",source,re.M|re.S)
    member=re.search(r"^struct member \{[^\n]*\};\n",source,re.M)
    enum=re.search(r"^enum \{ UID_FIRST=.*? \};\n",source,re.M|re.S)
    if event is None or member is None or enum is None:
        raise AssertionError("actual C declarations unavailable")
    guard=re.search(r"  struct event e;\n(.*?)  record_event\(ledger,&e,members,&c,\(unsigned\)index\);\n"
                    r"(  last_kind=\(int\)e.kind;last_slot=\(int\)e.slot;\n)?",
                    source,re.S)
    if guard is None:
        raise AssertionError("actual data guard unavailable")
    actual=event[0]+member[0]+enum[0]+function(source,"packet_valid")
    actual+=function(shared,"all_read")+function(shared,"read_record")+function(source,"die")
    if "static int block_diagnostic_sigpipe(" in source:
        actual+=function(source,"block_diagnostic_sigpipe")
    if "static int read_data_record(" in source:
        actual+=function(source,"read_data_record")+function(source,"reject_data_event")+function(source,"next_data_event")
    if "static _Noreturn void launch_failure(" in source:
        actual+=function(source,"launch_failure")
    actual+=function(source,"require_ack")+function(source,"launch_child")
    return PRELUDE+actual+TRAILER.replace("ACTUAL_GUARD",guard[1]).replace("ACTUAL_ACCEPTED_UPDATE",guard[2] or "")

PRELUDE=r'''
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <unistd.h>
static char directory[]="software",image[]="fixed-image",binary_hash[]="fixed-hash";
static volatile sig_atomic_t owned[2];
static const char *scenario;
static int launch_mode,fail_stage,spawning_mode,reserved_eight,opens,dups,closes,fcntls,pipes,forks,spawns,acks;
static int fd8_ready,marker_read_closed,marker_write_closed,poll_calls,read_calls;
static size_t offset;
static int owned_kills;
static int model_kill(pid_t pid,int signum) {
 if(pid!=777 || signum!=SIGKILL) _exit(225);
 owned_kills++;return 0;
}
static _Noreturn void model_exit(int status) {
 if(owned[0]>0 && status==2 && owned_kills!=1) _exit(226);
 _exit(status);
}
static void reset_probe_signals(void) {
 sigset_t empty;
 if(sigemptyset(&empty)<0 || sigprocmask(SIG_SETMASK,&empty,NULL)<0 ||
    signal(SIGPIPE,SIG_DFL)==SIG_ERR) _exit(224);
}
typedef int posix_spawn_file_actions_t;
static int model_open(const char *path,int flags) {
 opens++;
 if(strcmp(path,"/dev/null") || flags!=(O_RDWR|O_CLOEXEC)) _exit(202);
 if(fail_stage==1) {errno=EACCES;return -1;}
 if(reserved_eight) fd8_ready=1;
 return reserved_eight ? 8 : 6;
}
static int model_dup2(int oldfd,int newfd) {
 dups++;
 if(oldfd!=6 || newfd!=8) _exit(203);
 if(fail_stage==2) {errno=EMFILE;return -1;}
 fd8_ready=1;return 8;
}
static int model_close(int fd) {
 closes++;
 if(fd==6 && fail_stage==3) {errno=EIO;return -1;}
 if(fd==10) marker_read_closed=1;
 if(fd==11) marker_write_closed=1;
 if(fd!=6 && fd!=10 && fd!=11) _exit(204);
 return 0;
}
static int model_fcntl(int fd,int command,int flags) {
 fcntls++;
 if(command!=F_SETFD || flags!=FD_CLOEXEC || fd!=(fcntls==1 ? 8 : fcntls==2 ? 10 : 11)) _exit(205);
 if((fail_stage==4 && fcntls==1) || (fail_stage==6 && fcntls==2) || (fail_stage==7 && fcntls==3))
  {errno=EBADF;return -1;}
 return 0;
}
static int model_pipe(int pair[2]) {
 pipes++;
 if(fail_stage==5) {errno=ENFILE;return -1;}
 pair[0]=10;pair[1]=11;return 0;
}
static pid_t model_fork(void) {if(fail_stage) _exit(219);forks++;errno=EAGAIN;return -1;}
static int model_actions_init(posix_spawn_file_actions_t *a) {*a=1;return 0;}
static int model_actions_dup(posix_spawn_file_actions_t *a,int from,int to) {
 if(*a!=1 || from!=11 || to!=8) _exit(206);
 return 0;
}
static int model_actions_close(posix_spawn_file_actions_t *a,int fd) {
 if(*a!=1 || fd!=10) _exit(207);
 return 0;
}
static int model_actions_destroy(posix_spawn_file_actions_t *a) {return *a==1 ? 0 : 1;}
static int model_spawn(pid_t *pid,const char *path,const posix_spawn_file_actions_t *a,
                       const void *attributes,char *const args[],char *const env[]) {
 if(fail_stage) _exit(219);
 spawns++;
 if(strcmp(path,image) || *a!=1 || attributes || strcmp(args[1],"S") ||
    strcmp(env[0],"PATH=/usr/bin:/bin") || env[1]) _exit(208);
 *pid=999;return EAGAIN;
}
static int model_exec(const char *path,char *const args[],char *const env[]) {
 (void)path;(void)args;(void)env;_exit(209);
}
static ssize_t model_write(int fd,const void *buf,size_t n) {
 if(fd!=2) _exit(210);
 if(strstr(scenario,"_mask_") && !strstr(scenario,"_realpipe")) _exit(223);
 if(!strcmp(scenario,"launch_write_failure") || !strcmp(scenario,"eof_write_failure")) {errno=EPIPE;return -1;}
 if(!strcmp(scenario,"launch_short_write")) return (ssize_t)n-1;
 return write(fd,buf,n);
}
static int model_poll(struct pollfd *p,nfds_t n,int timeout) {
 if(!strcmp(scenario,"count")) _exit(220);
 poll_calls++;
 if(n!=1 || p->fd!=9 || p->events!=POLLIN || timeout!=11000) _exit(211);
 if(!strcmp(scenario,"timeout")) return 0;
 if(!strcmp(scenario,"poll_error")) {errno=EBADF;return -1;}
 if(!strcmp(scenario,"eintr") && poll_calls==1) {errno=EINTR;return -1;}
 return 1;
}
static int model_sigemptyset(sigset_t *set) {
 if(strstr(scenario,"_mask_empty")) {errno=EINVAL;return -1;}
 return sigemptyset(set);
}
static int model_sigaddset(sigset_t *set,int signum) {
 if(signum!=SIGPIPE) _exit(221);
 if(strstr(scenario,"_mask_add")) {errno=EINVAL;return -1;}
 return sigaddset(set,signum);
}
static int model_sigprocmask(int how,const sigset_t *set,sigset_t *old) {
 if(how!=SIG_BLOCK || old) _exit(222);
 if(strstr(scenario,"_mask_block")) {errno=EPERM;return -1;}
 return sigprocmask(how,set,old);
}
static ssize_t model_read(int fd,void *buf,size_t n);
static char send_event(unsigned kind,unsigned slot,unsigned other,unsigned op,int64_t rc,int error,int aux) {
 if(kind!=2 || slot!=0 || other!=2 || op!=(spawning_mode ? 2u : 1u) ||
    rc!=-1 || error!=EAGAIN || aux || !fd8_ready || !marker_read_closed || !marker_write_closed) _exit(212);
 acks++;return 'A';
}
#define kill model_kill
#define _exit model_exit
#define sigemptyset model_sigemptyset
#define sigaddset model_sigaddset
#define sigprocmask model_sigprocmask
#define open model_open
#define dup2 model_dup2
#define close model_close
#define fcntl model_fcntl
#define pipe model_pipe
#define fork model_fork
#define execve model_exec
#define write model_write
#define poll model_poll
#define read model_read
#define posix_spawn_file_actions_init model_actions_init
#define posix_spawn_file_actions_adddup2 model_actions_dup
#define posix_spawn_file_actions_addclose model_actions_close
#define posix_spawn_file_actions_destroy model_actions_destroy
#define posix_spawn model_spawn
'''
TRAILER=r'''
static struct event packet;
static ssize_t model_read(int fd,void *buf,size_t n) {
 read_calls++;
 if(launch_mode) {if(fd!=10) _exit(213);return 0;}
 if(fd!=9) _exit(214);
 if(!strcmp(scenario,"eof") || !strcmp(scenario,"eof_write_failure") || !strncmp(scenario,"eof_mask_",9) || (!strcmp(scenario,"after") && offset==sizeof(packet))) return 0;
 if(!strcmp(scenario,"read_error")) {errno=EIO;return -1;}
 if(!strcmp(scenario,"eintr") && read_calls==1) {errno=EINTR;return -1;}
 if(!strcmp(scenario,"partial") && offset) return 0;
 size_t amount=!strcmp(scenario,"partial") ? 7 : sizeof(packet)-offset;
 if(amount>n) _exit(215);
 memcpy(buf,(unsigned char *)&packet+offset,amount);offset+=amount;
 return (ssize_t)amount;
}
static void guard_once(unsigned *counter,int *accepted_kind,int *accepted_slot) {
 int last_kind=*accepted_kind,last_slot=*accepted_slot;
 struct member members[8];memset(members,0,sizeof(members));members[0].pid=123;
 int data[2]={9,10},index=7;
 unsigned event_count=*counter;
 (void)index;(void)last_kind;(void)last_slot;
 struct event e;
ACTUAL_GUARD
ACTUAL_ACCEPTED_UPDATE
 *accepted_kind=last_kind;*accepted_slot=last_slot;
 *counter=event_count;
 if(e.kind!=START || e.slot!=0) _exit(216);
}
int main(int argc,char **argv) {
 if(argc!=3) return 217;
 reset_probe_signals();
 scenario=argv[1];errno=EINVAL;
 if(!strncmp(scenario,"eof_mask_",9)) owned[0]=777; /* Only model_kill can observe this synthetic PID. */
 if(!strncmp(scenario,"launch",6)) {
  launch_mode=1;fail_stage=atoi(argv[2]);spawning_mode=!strcmp(scenario,"launch_spawn");
  reserved_eight=!strcmp(scenario,"launch_reserved8");
  pid_t result=launch_child(7,0,2,spawning_mode);
  if(result!=-1 || opens!=1 || dups!=(reserved_eight ? 0 : 1) || fcntls!=3 || pipes!=1 ||
     forks!=(spawning_mode ? 0 : 1) || spawns!=(spawning_mode ? 1 : 0) || acks!=1) return 218;
  printf("launch_ok fd8=1 marker_closed=2 ack=1 fork=%d spawn=%d\n",forks,spawns);
  return 0;
 }
 packet=(struct event){.magic=VMAGIC,.version=1,.length=sizeof(packet),.kind=START,.slot=0};
 if(!strcmp(scenario,"magic")) packet.magic=0;
 if(!strcmp(scenario,"version")) packet.version=2;
 if(!strcmp(scenario,"length")) packet.length=1;
 if(!strcmp(scenario,"kind")) packet.kind=99;
 if(!strcmp(scenario,"slot")) packet.slot=UINT32_MAX;
 if(!strcmp(scenario,"member")) packet.slot=1;
 unsigned count=!strcmp(scenario,"count") ? 64u : 0u;
 int last_kind=-1,last_slot=-1;
 guard_once(&count,&last_kind,&last_slot);
 if(!strcmp(scenario,"after")) guard_once(&count,&last_kind,&last_slot);
 printf("guard_ok count=%u poll=%d read=%d\n",count,poll_calls,read_calls);
 return 0;
}
'''

class TestM0a2EventDiagnostics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc=shutil.which("cc")
        if cc is None:
            raise AssertionError("C compiler unavailable; infrastructure, not semantic RED")
        cls.temporary=tempfile.TemporaryDirectory(prefix="m0a2-diagnostic-software-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.binary=Path(cls.temporary.name)/"probe"
        program=probe_source(CFILE.read_text(encoding="utf-8"),HELPER.read_text(encoding="utf-8"))
        built=subprocess.run([cc,"-std=c11","-Wall","-Wextra","-Werror","-Wno-unused-function",
                              "-x","c","-","-o",str(cls.binary)],input=program.encode("ascii"),
                             capture_output=True,timeout=30)
        if built.returncode or built.stdout or len(built.stderr)>65536:
            raise AssertionError("C diagnostic probe infrastructure: "+built.stderr.decode("utf-8","replace"))
    def run_probe(self,scenario,stage=0):
        result=subprocess.run([str(self.binary),scenario,str(stage)],capture_output=True,timeout=5)
        self.assertLessEqual(len(result.stdout)+len(result.stderr),4096)
        return result
    def data_rejection(self,scenario,reason,result,received,last=(-1,-1),count=1):
        actual=self.run_probe(scenario)
        self.assertEqual(actual.returncode,2,actual.stderr)
        self.assertEqual(actual.stdout,b"")
        line=(f"M0A2_DATA case=7 event_count={count} reason={reason} read_result={result} "
              f"received={received} last_kind={last[0]} last_slot={last[1]} cleanup=unknown\n").encode()
        self.assertIn(line,actual.stderr,"M0A2_DIAGNOSTIC_DATA_REQUIRED")
        self.assertIn(b"M0A2 stage=data-event-contract",actual.stderr)
    def test_launch_open_refusal_has_saved_errno_without_creation(self):
        actual=self.run_probe("launch",1)
        self.assertEqual(actual.returncode,85)
        self.assertEqual(actual.stdout,b"")
        self.assertEqual(actual.stderr,
            f"M0A2_LAUNCH case=7 slot=0 child_slot=2 stage=open saved_errno={errno.EACCES} exit=85 cleanup=unknown\n".encode(),
            "M0A2_DIAGNOSTIC_LAUNCH_REQUIRED")
    def test_launch_other_setup_failures_are_exact_stages(self):
        for stage,name,error in ((2,"dup2",errno.EMFILE),(3,"close",errno.EIO),(4,"fcntl8",errno.EBADF),
                                 (5,"pipe",errno.ENFILE),(6,"fcntl_read",errno.EBADF),(7,"fcntl_write",errno.EBADF)):
            with self.subTest(stage=stage):
                actual=self.run_probe("launch",stage)
                self.assertEqual(actual.returncode,85)
                self.assertEqual(actual.stdout,b"")
                self.assertEqual(actual.stderr,
                    f"M0A2_LAUNCH case=7 slot=0 child_slot=2 stage={name} saved_errno={error} exit=85 cleanup=unknown\n".encode(),
                    "M0A2_DIAGNOSTIC_LAUNCH_REQUIRED")
    def test_launch_setup_keeps_fd8_marker_ack_and_api_paths(self):
        for scenario,forks,spawns in (("launch",1,0),("launch_spawn",0,1),("launch_reserved8",1,0)):
            with self.subTest(scenario=scenario):
                actual=self.run_probe(scenario)
                self.assertEqual(actual.returncode,0,actual.stderr)
                self.assertEqual(actual.stderr,b"")
                self.assertEqual(actual.stdout,
                    f"launch_ok fd8=1 marker_closed=2 ack=1 fork={forks} spawn={spawns}\n".encode())
    def test_eof_reports_read_result_not_stale_errno(self):
        self.data_rejection("eof","read",errno.EPIPE,0)
    def test_partial_read_reports_actual_byte_count(self):
        self.data_rejection("partial","read",errno.EPIPE,7)
    def test_timeout_poll_and_read_errors_preserve_priority(self):
        for scenario,error in (("timeout",errno.ETIMEDOUT),("poll_error",errno.EBADF),("read_error",errno.EIO)):
            with self.subTest(scenario=scenario):
                self.data_rejection(scenario,"read",error,0)
    def test_full_packet_magic_kind_slot_and_member_rejections(self):
        for scenario,reason in (("magic","packet"),("version","packet"),("length","packet"),
                                ("kind","kind"),("slot","slot"),("member","member")):
            with self.subTest(scenario=scenario):
                self.data_rejection(scenario,reason,0,120)
    def test_count_limit_precedes_read_and_packet(self):
        self.data_rejection("count","count",-1,0,count=65)
    def test_valid_and_eintr_paths_add_no_output(self):
        for scenario,polls,reads in (("valid",1,1),("eintr",2,2)):
            with self.subTest(scenario=scenario):
                actual=self.run_probe(scenario)
                self.assertEqual(actual.returncode,0,actual.stderr)
                self.assertEqual(actual.stderr,b"")
                self.assertEqual(actual.stdout,f"guard_ok count=1 poll={polls} read={reads}\n".encode())
    def test_diagnostic_write_failure_remains_failed_closed(self):
        for scenario,stage,status in (("launch_write_failure",1,85),("launch_short_write",1,85),
                                      ("eof_write_failure",0,2)):
            with self.subTest(scenario=scenario):
                actual=self.run_probe(scenario,stage)
                self.assertEqual(actual.returncode,status)
                self.assertEqual(actual.stdout,b"")
                self.assertNotIn(b"M0A2_DATA ",actual.stderr)
                self.assertNotIn(b"M0A2_LAUNCH ",actual.stderr)
        for operation in ("empty","add","block"):
            for prefix,stage,status in (("launch",1,85),("eof",0,2)):
                with self.subTest(mask_operation=operation,path=prefix):
                    actual=self.run_probe(prefix+"_mask_"+operation,stage)
                    self.assertEqual(actual.returncode,status)
                    self.assertEqual(actual.stdout,b"")
                    self.assertEqual(actual.stderr,b"","mask failure must skip every diagnostic output")
    def test_real_broken_stderr_pipe_preserves_original_exit_status(self):
        cases=[("launch",1,85),("eof",0,2)]
        cases += [(prefix+"_mask_"+operation+"_realpipe",stage,status)
                  for operation in ("empty","add","block")
                  for prefix,stage,status in (("launch",1,85),("eof",0,2))]
        for scenario,stage,status in cases:
            with self.subTest(path=scenario):
                reader,writer=os.pipe()
                os.close(reader)  # Genuine pipe without a reader; not a write/EPIPE stub.
                try:
                    actual=subprocess.run([str(self.binary),scenario,str(stage)],stdout=subprocess.PIPE,
                                          stderr=writer,restore_signals=True,timeout=5)
                finally:
                    os.close(writer)
                self.assertEqual(actual.returncode,status,"real SIGPIPE must not replace the original exit")
                self.assertEqual(actual.stdout,b"")
    def test_second_failure_retains_last_accepted_header(self):
        self.data_rejection("after","read",errno.EPIPE,0,last=(1,0),count=2)

if __name__=="__main__":
    unittest.main()
```

### Asset B: native/mac/tests/icode_m0a2_vectors.c

```diff
*** Begin Patch
*** Update File: native/mac/tests/icode_m0a2_vectors.c
@@ -148,13 +148,31 @@
  if(result!=child || !WIFEXITED(status) || WEXITSTATUS(status)) _exit(84);
  require_ack(send_event(REAPED,slot,child_slot,0,child,0,status),'A');
 }
+static int block_diagnostic_sigpipe(void) {
+ sigset_t blocked;
+ return sigemptyset(&blocked)==0 && sigaddset(&blocked,SIGPIPE)==0 &&
+        sigprocmask(SIG_BLOCK,&blocked,NULL)==0;
+}
+static _Noreturn void launch_failure(int index,unsigned slot,unsigned child_slot,
+                                     const char *stage,int saved_errno) {
+ if(!block_diagnostic_sigpipe()) _exit(85);
+ char line[192];
+ int n=snprintf(line,sizeof(line),
+  "M0A2_LAUNCH case=%d slot=%u child_slot=%u stage=%s saved_errno=%d exit=85 cleanup=unknown\n",
+  index,slot,child_slot,stage,saved_errno);
+ if(n>0 && n<(int)sizeof(line)) (void)write(2,line,(size_t)n);
+ _exit(85);
+}
 static pid_t launch_child(int index,unsigned slot,unsigned child_slot,int spawning) {
  int marker[2];
  int reserved=open("/dev/null",O_RDWR|O_CLOEXEC);
- if(reserved<0 || (reserved!=8 && dup2(reserved,8)<0)) _exit(85);
- if(reserved!=8 && close(reserved)<0) _exit(85);
- if(fcntl(8,F_SETFD,FD_CLOEXEC)<0 || pipe(marker)<0 ||
-    fcntl(marker[0],F_SETFD,FD_CLOEXEC)<0 || fcntl(marker[1],F_SETFD,FD_CLOEXEC)<0) _exit(85);
+ if(reserved<0) launch_failure(index,slot,child_slot,"open",errno);
+ if(reserved!=8 && dup2(reserved,8)<0) launch_failure(index,slot,child_slot,"dup2",errno);
+ if(reserved!=8 && close(reserved)<0) launch_failure(index,slot,child_slot,"close",errno);
+ if(fcntl(8,F_SETFD,FD_CLOEXEC)<0) launch_failure(index,slot,child_slot,"fcntl8",errno);
+ if(pipe(marker)<0) launch_failure(index,slot,child_slot,"pipe",errno);
+ if(fcntl(marker[0],F_SETFD,FD_CLOEXEC)<0) launch_failure(index,slot,child_slot,"fcntl_read",errno);
+ if(fcntl(marker[1],F_SETFD,FD_CLOEXEC)<0) launch_failure(index,slot,child_slot,"fcntl_write",errno);
  char idx[16],target[16],parent[16];
  snprintf(idx,sizeof(idx),"%d",index);snprintf(target,sizeof(target),"%u",child_slot);
  snprintf(parent,sizeof(parent),"%u",slot);
@@ -336,6 +354,49 @@
  return e->magic==VMAGIC && e->version==1 && e->length==sizeof(*e) && e->slot<8;
 }
 struct member { pid_t pid;uint64_t sec,usec;uid_t uid;int parent,started,held,finished,reaped,completed; };
+static int read_data_record(int fd,void *buf,size_t n,size_t *received) {
+ *received=0;
+ struct pollfd p={.fd=fd,.events=POLLIN};int r;
+ do { r=poll(&p,1,11000); } while(r<0 && errno==EINTR);
+ if(r<=0) return r==0 ? ETIMEDOUT : errno;
+ unsigned char *bytes=buf;
+ while(*received<n) {
+  ssize_t amount=read(fd,bytes+*received,n-*received);
+  if(amount<0 && errno==EINTR) continue;
+  if(amount<=0) return amount==0 ? EPIPE : errno;
+  *received+=(size_t)amount;
+ }
+ return 0;
+}
+static _Noreturn void reject_data_event(unsigned index,unsigned event_count,const char *reason,
+                                       int read_result,size_t received,int last_kind,int last_slot) {
+ if(!block_diagnostic_sigpipe()) {
+  for(unsigned i=0;i<2;i++) if(owned[i]>0) (void)kill((pid_t)owned[i],SIGKILL);
+  _exit(2);
+ }
+ char line[256];
+ int n=snprintf(line,sizeof(line),
+  "M0A2_DATA case=%u event_count=%u reason=%s read_result=%d received=%zu last_kind=%d last_slot=%d cleanup=unknown\n",
+  index,event_count,reason,read_result,received,last_kind,last_slot);
+ if(n>0 && n<(int)sizeof(line)) (void)write(2,line,(size_t)n);
+ errno=read_result>0 ? read_result : EPROTO;
+ die("data-event-contract");_exit(2);
+}
+static void next_data_event(int fd,struct event *e,struct member members[8],unsigned index,
+                            unsigned *event_count,int last_kind,int last_slot) {
+ size_t received=0;
+ if(++*event_count>64) reject_data_event(index,*event_count,"count",-1,0,last_kind,last_slot);
+ int result=read_data_record(fd,e,sizeof(*e),&received);
+ if(result) reject_data_event(index,*event_count,"read",result,received,last_kind,last_slot);
+ /* No field access above: an incomplete packet is never interpreted. */
+ if(!packet_valid(e))
+  reject_data_event(index,*event_count,e->slot>=8 ? "slot" : "packet",0,received,last_kind,last_slot);
+ if(e->kind<START || e->kind>DONE)
+  reject_data_event(index,*event_count,"kind",0,received,last_kind,last_slot);
+ /* packet_valid has proved slot<8; only now may members be indexed. */
+ if(!members[e->slot].pid)
+  reject_data_event(index,*event_count,"member",0,received,last_kind,last_slot);
+}
 static void identify(struct member *m,pid_t pid,uid_t uid,int parent) {
  struct proc_bsdinfo b;
  if(proc_pidinfo(pid,PROC_PIDTBSDINFO,0,&b,sizeof(b))!=(int)sizeof(b) ||
@@ -513,12 +574,12 @@
  }
  close(data[1]);for(unsigned i=0;i<8;i++) close(ack[i][0]);
  unsigned root_started=0,finished_count=0,done=0;
- int all_finished=0;unsigned event_count=0;
+ int all_finished=0;unsigned event_count=0;int last_kind=-1,last_slot=-1;
  while(done<(unsigned)c.roots) {
   struct event e;
-  if(++event_count>64 || read_record(data[0],&e,sizeof(e)) || !packet_valid(&e) ||
-     e.kind<START || e.kind>DONE || !members[e.slot].pid) die("data-event-contract");
+  next_data_event(data[0],&e,members,(unsigned)index,&event_count,last_kind,last_slot);
   record_event(ledger,&e,members,&c,(unsigned)index);
+  last_kind=(int)e.kind;last_slot=(int)e.slot;
   if(e.kind==FORKED) {
    if(e.other>=8 || members[e.other].pid || e.rc<=0 || e.rc>INT_MAX || e.error || e.aux!=1) die("fork-registration");
    identify(&members[e.other],(pid_t)e.rc,members[e.slot].uid,e.pid);
*** End Patch
```

### Asset C: scripts/run_macos_m0a2_vectors.py

```diff
*** Begin Patch
*** Update File: scripts/run_macos_m0a2_vectors.py
@@ -275,6 +275,8 @@
             "native/mac/icode_m0a1_process_groups.h","native/mac/icode_m0a1_process_groups.c",
             "tests/test_macos_task_quota_probe.py","tests/test_macos_process_groups_native.py",
             "tests/test_macos_process_groups.py","tests/test_macos_m0a2_vectors.py",
+            "tests/test_macos_m0a2_event_diagnostics.py",
+            "docs/nbl/plans/2026-10-14-macos-m0a2-event-diagnostics.md",
             "scripts/run_macos_m0_ci.py","scripts/run_macos_m0a2_vectors.py",
             "native/mac/CMakeLists.txt",".github/workflows/ci.yml",
             "docs/nbl/specs/2026-10-13-macos-task-identity-quota-design.md",
*** End Patch
```

### Asset D: .github/workflows/ci.yml

```diff
*** Begin Patch
*** Update File: .github/workflows/ci.yml
@@ -2473,6 +2473,9 @@
         uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97
         with:
           python-version: "3.11"
+      - name: Diagnostic-only C software contract
+        shell: bash
+        run: python -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_macos_m0a2_event_diagnostics.py'); assert s.countTestCases()==12, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
       - name: Targeted SOURCE software contract
         if: env.M0A2_SOURCE == '1'
         shell: bash
*** End Patch
```

## 8. 投影摘要

|未来文件|行数|SHA256|
|---|---:|---|
|tests/test_macos_m0a2_event_diagnostics.py|364|a39984568a6499435b3f810bf43010913fad5a78c5c0b0a6a4d244cf8d95d500|
|native/mac/tests/icode_m0a2_vectors.c|736|2546c73e5e17511d9431401461df924a77a56aa59ae00f9e0affce6e6da99e1c|
|scripts/run_macos_m0a2_vectors.py|328|ce4d254f70d4140275c17a5c33519cb554a82e1c737d4b2b73a46d20030def13|
|.github/workflows/ci.yml|2499|bf177747b718250a78d6a4e6a53003402e72977c166e93aee7edafe2fa908de4|

|冻结fence|行数|SHA256|
|---|---:|---|
|A 新TEST|364|a39984568a6499435b3f810bf43010913fad5a78c5c0b0a6a4d244cf8d95d500|
|B C诊断patch|105|0a8a14436a108ea2c3e646d60e46bfdc1fb57fdfde1e2f2d6d11574ad8c4d1b2|
|C manifest摘要patch|12|d118d20f79bf183b62afd1a40175daee245e60bc684c05991a251d79a4c695a2|
|D CI单步骤patch|13|83fbc5651f226152865dc60e584f072d76ac53fe36318383956b633201576bf8|

作者本修订a4bb01对三patch逐hunk唯一匹配并完整投影/逆还原原输入，全部摘要吻合；新TEST/投影controller AST通过。最终匿名RAM a96f35使用364L新TEST实际路径：旧675L为12方法27 assertion记录、0ERROR/0skip；先前726L为12方法14 assertion记录、0ERROR/0skip；736L局部mask投影12方法全GREEN、0ERROR/0skip。真实无读端pipe覆盖launch/data及各三种mask失败，共8组合，默认SIGPIPE＋空mask；正常mask是真实OS操作，非EPIPE stub。lastaccepted仍提取实际while中record_event之后的赋值，原11/20记录及早期原型仅历史，不代本修订正式TDD或Mac观察。

## 9. 固定研究复用、自审与交付

仅复用批准DESIGN§8的Apple XNU xnu-12377.1.9 fork/resource/exit与官方posix_spawn接口，以及Codex27065a91ccbf5ba8532844be3777fcf83b77820d exec.rs的leader/pipe/expiration分离机制；不重新宣称已刷新上游或runner等同公开内核。采纳当次返回值/错误与生命周期独立观察；暂缓实际根终态/整体树证明、quota修复与C/D/E；不适配放宽profile/权限或软件stub替native。仅链接/机制借鉴，不复制APSL/未知许可实现，不引新依赖。具体固定主源链接沿批准DESIGN原文保留。

SPEC自审：需求五类OR/launch85分段均有完整资产与真实旧路径RED，所有quota/成功/预算门未变。QUALITY自审：完整包前不读字段、slot安全后索引、返回码不取残留errno；局部SIGPIPE block成功或sigset/mask失败均保持85/2，且data静默分支执行原owned终止循环；TEST/helper存在检测不造成缺函数ERROR；controller只摘要，CI仅一步，不把stderr接纳为ready。本自审不替fresh独立审查。

【架构级自检报告】
✅ 语法/编译：Python AST与小C probe严格编译通过；完整Darwin编译/运行未做。
✅ 依赖/调用链：实际旧guard/launch和新接线可执行；共享helper不变，四未来文件责任闭合。
✅ 逻辑/边界：count/read/packet(slot)/kind/member优先级，partial bytes、lastaccepted、7阶段errno。
✅ 异常处理：真实断管/短写及三种sigset/mask失败均85或2，data静默分支保留原owned终止动作，unknown不授清理。
✅ 关联模块：摘要同步两新增路径，原15/13门与A/B/C/D/E依赖不减。
✅ 兼容安全：profile/限额/FD布局/成功ACK/原协议不变，无root产品入口、权限/账户变更。
✅ 可运行性：完整资产＋strict命令；仅有软件RAM信用，正式独立TDD/双Mac仍待验，不写100%。

**Execution Mode:** serial。STOP等待root全文＋freshSPEC→不同QUALITY；不自动执行、stage/commit/push、cancel/re-run或启用quotaSOURCE。
