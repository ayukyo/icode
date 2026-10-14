# macOS M0a1 harness 最小诊断实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 仅补充受审 native TEST driver 的失败观察，定位第一处 configured / ready 屏障失败；不猜测修复，不授 quota 或语义 RED 信用。

**Architecture:** 固定整数诊断写现有 stderr，不接入 delivery、root audit 或正式 oracle。worker 初始化失败仍在原操作后以原退出码终止；root 分别保留读取结果与实际 wait 状态。保留原 release、profile、NOTE_EXEC、receipt-loss 保护和全部正式期望。

**Tech Stack:** C11 / SDK；Python stdlib unittest；Linux cc 仅验证抽取的实际整数 emitter，macOS 原生双格另验。无新依赖。

---

## 0. 基线与授权

2026-10-14，root 实际 sequential-thinking 三步记录 `e9e8eb`。本作者完整读取 bug-investigation-baseline-checklist、writing-plans、TDD 及 anti-patterns。用户授权主任务及 root 下发任务仅允许本次新建本文；**没有写 SOURCE/TEST/CI、运行本文资产、提交、推送或创建工作区**。本次文档不能自动触发执行技能；root 全文阅读、fresh SPEC → 不同 QUALITY 后方可实施。

- Agent runtime / analysis：`b8cc1e737587fc4b40b3ed2bc167b045d51bc03f`，WSL `/home/orbbec/projects/icode`，main。实际 HEAD 已核一致；已有 handoff 文档改动保留。
- vendor：`21566a589cbe98bd35372a04bbb6ca1c51d8eed2`，不改固定版本。
- driver SHA-256：`32089c63d3e3fc8bb658a57c564f9a60a0cd6ee97467b4f200fb45e957d28c3f`。
- 原批准 DESIGN：`774e33f4c2485da553f6b41572ef9641c4b30dea307a8e466c2bbdca7b2e5b23`；PLAN：`37e4852cb9c25dfa2154ec8356d5416859125271f14b27d8d45f46bc44168ee7`。
- 双格 run `38495800553` / attempt1；官方 GitHub 下载工具取得 artifacts 后纯内存解压，实际读 metadata/stdout/stderr；source hashes 对应冻结资产。

| 目标 | 原始 artifact / binary SHA-256 | 实际平台 |
| --- | --- | --- |
| Intel | `11862864535` / `33b022091cacb7e84417085021ad7568f566fee88df75f2242017a4bd4ce5c37` | x86_64 / 15.7.9 / 24G830 / kernel24.6.0 |
| ARM | `11862819665` / `e3b54c2e652f5f67d6dfc2305fffa4acbc5635f8673e60c77df19d5822246c3b` | arm64 / 26.6.2 / 25G83 / kernel25.6.0 |

两格 native exit2，全部7个 launch released0，前6个 confirmation=false，receipt_loss 仅 launch；没有最终 audit manifest，controller 如实拒绝基础设施故障。stdout SHA-256 均为 `5475848ccb56d45c0c11971d9cb6d0db561f264175a3f02e16ac424d1ccb1814`；Intel stderr `b72430269686a25bd7ab9a2a355a93b0ced5414fad1ce2eaf920cf32eb5a96e2`，ARM stderr `d4685618a7193bd094d8126f94831d7eb6b4264090a8405ff3a3f79862124123`。

现象上限 `observation_only`：尚无 configured / ready 读取错误、wire phase/error 或 wait_status，不能命名第一失败 syscall。末尾 `die()` 的 errno60 是多个后续 syscall 后的 ambient errno，不等同配置/读取错误。保留该旧日志及原 die，不回填含义。无 profile 的 seatbelt_positive 同样未释放，不足以把问题归因于单一 profile，但也不证明其实际失败阶段。runner 物理身份、精确事件时刻和既有0600根审计内容未获取，不能伪装已知。

修订历史：旧本文SHA-256 `0e3e7d493aae695f72bb1bcb13132e6dcea269acf741d84a474606ee4d24b64e` 的独立 QUALITY 为 C0/I1/M0，未批准：worker恢复SIGPIPE默认处置后，setup_fail的stderr写入可能因broken pipe直接信号终止，从而改变原exitcode。作者重新核 [Apple官方pipe(2)](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/pipe.2.html)，其明确闭读端管道写入触发SIGPIPE。本文仅在已进入必定_exit的setup_fail路径临时阻塞SIGPIPE，阻塞失败则不写诊断、仍原_exit；不恢复会递送pending信号的mask，不改正常worker/payload信号mask。新增真实匿名broken-pipe负控，旧3测试保留。该修订仍需fresh SPEC → 不同 QUALITY，不能抹掉旧I1或自授批准。

## 1. 范围、字段及不变量

后续实施白名单只有 `tests/test_macos_m0a1_diagnostics.py`（新 TEST）与 `native/mac/tests/icode_m0a1_driver.c`（以下完整 patch）；root 可另记交接文档。禁止改正式 TEST、controller、CI、profile、limit 原语和旧批准 PLAN 资产。

诊断行固定格式：`M0A1_DIAG version=1 case_index=<u> stage=<u> error=<d> detail=<d> result=<d>\n`。无字符串参数、路径、argv、环境或用户内容；192字节栈缓冲，溢出不输出，不重试。emit 保存/恢复 errno；root原有SIGPIPE忽略不变，setup_fail仅在最终退出路径成功阻塞SIGPIPE后才写，阻塞失败则不写仍原_exit，不恢复mask。所有调用次数固定：每 case 最多8条 root诊断、最多1条 worker初始化失败，7 case总≤63行、≤12096字节，保留原64KiB stderr上限。

| stage | error | detail | result |
| --- | --- | --- | --- |
| 101 configured read | read_record 返回值 | 完整读到则原 phase，否则-1 | 完整读到则原 error，否则-1 |
| 102 configured validation | 0 | 完整读到则原 pid，否则-1 | configured_ok |
| 103 ready read | 实际返回值；未尝试为-1 | 完整读到则原 phase，否则-1 | 完整读到则原 error，否则-1 |
| 104 ready validation | 0 | ready_attempted | ready_ok |
| 105 observer terminal | 0 | observer_kill_sent | raw wait_status |
| 106 decoded exit | 0 | WIFEXITED 则 exitcode，否则-1 | WIFSIGNALED 则 signal，否则0 |
| 107 barrier | 0 | registered | released |
| 108 limit bound | 0 | configured_ok | ready_ok |

phase/error 仅完整读取后展示，未通过 valid_gate 的数据仍是不可信 wire 观察，不授配置成功；stage102保留整体 valid_gate 结果。不更改 valid_gate 字段规则。stage1–16 为固定 worker 初始化阶段，具体 syscall、detail和原 exit 见 patch。error 为该失败调用立即保存的 errno；纯 readback mismatch 的 error=0，result 保留原退出码，不冒充系统 errno。

## 2. Task 1：独立 TESTOnly，先看有效断言 RED

**Dependencies:** None
**Parallelizable:** No（TEST作者独立于 driver patch 作者；先冻结 TEST）

- [x] 仅创建下面完整 TEST；RED时原 driver 不改。Linux 开发环境只运行此针对性测试。
- [x] 实际执行4个测试方法、5条 `DIAGNOSTIC_EMITTER_ABSENT` AssertionError（末方法两个subTest），无 ImportError/编译错误/skip。完整日志与SHA已存用户home，见执行记录；不把方法数量等同failure数量。
- [ ] 不以新函数名不存在导致的链接错误当 RED：TEST在编译前显式断言当前 driver 缺少需要的可观察 emitter；这是诊断缺失的结构断言，后续实际编译执行则验证内容，不等同 macOS 屏障修复。

完整 `tests/test_macos_m0a1_diagnostics.py`：

```python
import errno
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "native/mac/tests/icode_m0a1_driver.c"

@unittest.skipUnless(sys.platform == "linux", "Linux-only emitter software test; no native credit")
class TestM0a1Diagnostics(unittest.TestCase):
    def run_emitter(self, mode):
        source = DRIVER.read_text(encoding="utf-8")
        found = re.search(
            r"/\* M0A1_DIAGNOSTIC_EMITTER_BEGIN \*/\n(.*?)"
            r"/\* M0A1_DIAGNOSTIC_EMITTER_END \*/", source, re.S)
        self.assertIsNotNone(found, "DIAGNOSTIC_EMITTER_ABSENT")
        self.assertEqual(sys.platform, "linux", "portable emitter proof is Linux only")
        cc = shutil.which("cc")
        self.assertIsNotNone(cc, "Linux C compiler required; not a skip")
        harness = r'''
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <limits.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
EMITTER
int main(int argc,char **argv) {
    if(argc!=2) return 2;
    int mode=atoi(argv[1]);
    if(mode==3 || mode==4) {
        sigset_t unblocked;
        if(signal(SIGPIPE,SIG_DFL)==SIG_ERR || sigemptyset(&unblocked)<0 ||
           sigaddset(&unblocked,SIGPIPE)<0 ||
           sigprocmask(SIG_UNBLOCK,&unblocked,NULL)<0) return 7;
        if(mode==3) {
            int endpoints[2];
            if(pipe(endpoints)<0 || close(endpoints[0])<0 ||
               dup2(endpoints[1],STDERR_FILENO)<0 || close(endpoints[1])<0) return 8;
        }
        if(setvbuf(stderr,NULL,_IONBF,0)) return 9;
        setup_fail(0,15,EPIPE,0,111);
        return 10;
    }
    if(mode==2) {
        if(!freopen("/dev/full","w",stderr)) return 3;
        if(setvbuf(stderr,NULL,_IONBF,0)) return 4;
    }
    errno=EAGAIN;
    if(mode==1) emit_diagnostic(UINT_MAX,UINT_MAX,INT_MIN,INT_MAX,INT_MIN);
    else emit_diagnostic(0,101,EPIPE,-1,-1);
    if(errno!=EAGAIN) return 5;
    if(mode==2 && !ferror(stderr)) return 6;
    return 0;
}
'''.replace("EMITTER", found.group(1))
        with tempfile.TemporaryDirectory(prefix="icode-m0a1-emit-") as tmp:
            directory = Path(tmp)
            cpath, binary = directory / "probe.c", directory / "probe"
            cpath.write_text(harness, encoding="ascii", newline="\n")
            built = subprocess.run(
                [cc, "-std=c11", "-Wall", "-Wextra", "-Werror", str(cpath), "-o", str(binary)],
                capture_output=True, timeout=30, check=False)
            self.assertEqual(built.returncode, 0, built.stderr.decode("utf-8", "replace"))
            self.assertEqual(built.stdout, b"")
            actual = subprocess.run([str(binary), str(mode)], capture_output=True,
                                    timeout=5, check=False)
            self.assertEqual(actual.returncode, 111 if mode in (3, 4) else 0, actual.stderr)
            self.assertEqual(actual.stdout, b"")
            return actual.stderr

    def test_actual_diagnostic_fields_and_errno_preserved(self):
        expected = ("M0A1_DIAG version=1 case_index=0 stage=101 error="
                    + str(errno.EPIPE) + " detail=-1 result=-1\n").encode("ascii")
        self.assertEqual(self.run_emitter(0), expected)

    def test_integer_extremes_are_ascii_single_bounded_record(self):
        raw = self.run_emitter(1)
        self.assertLess(len(raw), 192)
        self.assertEqual(raw.count(b"\n"), 1)
        self.assertRegex(raw.decode("ascii"),
                         r"^M0A1_DIAG version=1 case_index=4294967295 stage=4294967295 "
                         r"error=-2147483648 detail=2147483647 result=-2147483648\n$")

    def test_write_failure_does_not_replace_callers_errno(self):
        self.assertEqual(self.run_emitter(2), b"")

    def test_setup_failure_preserves_exit_with_real_broken_pipe(self):
        with self.subTest(stderr="closed_read_end"):
            self.assertEqual(self.run_emitter(3), b"")
        with self.subTest(stderr="healthy_pipe_positive_control"):
            expected = ("M0A1_DIAG version=1 case_index=0 stage=15 error="
                        + str(errno.EPIPE) + " detail=0 result=111\n").encode("ascii")
            self.assertEqual(self.run_emitter(4), expected)
```

此 TEST 抽取 actual driver 唯一标记区间中的实际 emit_diagnostic 与 setup_fail 两函数，未模拟 emit或mask调用；其余 Mac driver 不在 Linux 编译。非Linux默认发现跳过这4个host-only测试，不授其软件或原生信用；本片必要的Linux针对性验收必须4个实际执行、无skip。测试C类型期望明确为Linux常见32位int/unsigned，编译器/ABI不同则失败而非默默接受。`/dev/full` 是 Linux 限定错误出口；第四方法先真正恢复默认SIGPIPE并unblock，匿名管道关闭全部读端，再将写端dup到stderr，必须exit111而不是SIGPIPE终止；同一方法的健康stderr正控必须真实收到诊断，避免完全不写也算通过。stdout必须为空。不访问用户文件；临时目录只含自生成C和binary，由 TemporaryDirectory 管理，不是用户工程清理。

## 3. Task 2：不同作者应用完整 driver patch

**Dependencies:** Task 1 的真实断言 RED及TEST冻结
**Parallelizable:** No（不同作者；只能写 driver）

- [x] 应用下列完整 patch，未顺手修 getdtablesize、signal、Seatbelt 或其它假设。
- [x] 同一4 TEST真实 GREEN，无错误/skip；旧5个便携协议 TEST亦GREEN。正式 native类未在本机运行。
- [x] driver diff 与 patch 逐字节一致；旧正式 TEST/controller/CI/profile、quota文件不存在状态保持。

```diff
--- a/native/mac/tests/icode_m0a1_driver.c
+++ b/native/mac/tests/icode_m0a1_driver.c
@@
-static void worker_fail(int error) { send_gate(FAILED,error); _exit(94); }
+/* M0A1_DIAGNOSTIC_EMITTER_BEGIN */
+static void emit_diagnostic(unsigned index,unsigned stage,int error,int detail,int result) {
+    int saved=errno;
+    char row[192];
+    int n=snprintf(row,sizeof(row),
+        "M0A1_DIAG version=1 case_index=%u stage=%u error=%d detail=%d result=%d\n",
+        index,stage,error,detail,result);
+    if(n>0 && (size_t)n<sizeof(row)) (void)fwrite(row,1,(size_t)n,stderr);
+    errno=saved;
+}
+static void setup_fail(unsigned index,unsigned stage,int error,int detail,int code) {
+    sigset_t blocked;
+    /* This path must exit: never restore a mask that could deliver pending SIGPIPE. */
+    if(sigemptyset(&blocked)==0 && sigaddset(&blocked,SIGPIPE)==0 &&
+       sigprocmask(SIG_BLOCK,&blocked,NULL)==0)
+        emit_diagnostic(index,stage,error,detail,code);
+    _exit(code);
+}
+/* M0A1_DIAGNOSTIC_EMITTER_END */
+static void worker_fail(int error) { send_gate(FAILED,error); _exit(94); }
@@
-        if(setrlimit(RLIMIT_CPU,&cpu)<0 || setrlimit(RLIMIT_FSIZE,&files)<0) _exit(104);
+        if(setrlimit(RLIMIT_CPU,&cpu)<0) setup_fail(index,1,errno,RLIMIT_CPU,104);
+        if(setrlimit(RLIMIT_FSIZE,&files)<0) setup_fail(index,2,errno,RLIMIT_FSIZE,104);
         struct rlimit actual;
-        if(getrlimit(RLIMIT_CPU,&actual)<0 || actual.rlim_cur!=2 || actual.rlim_max!=2 ||
-           getrlimit(RLIMIT_FSIZE,&actual)<0 || actual.rlim_cur!=65536 || actual.rlim_max!=65536)
-            _exit(116);
+        if(getrlimit(RLIMIT_CPU,&actual)<0) setup_fail(index,3,errno,RLIMIT_CPU,116);
+        if(actual.rlim_cur!=2 || actual.rlim_max!=2) setup_fail(index,4,0,RLIMIT_CPU,116);
+        if(getrlimit(RLIMIT_FSIZE,&actual)<0) setup_fail(index,5,errno,RLIMIT_FSIZE,116);
+        if(actual.rlim_cur!=65536 || actual.rlim_max!=65536) setup_fail(index,6,0,RLIMIT_FSIZE,116);
         int limit=getdtablesize();
-        if(limit<6 || limit>65536) _exit(105);
-        if(dup2(status_pipe[1],3)<0 || dup2(release_pipe[0],4)<0 || dup2(data_pipe[1],5)<0) _exit(106);
+        if(limit<6 || limit>65536) setup_fail(index,7,limit<0 ? errno : 0,limit,105);
+        if(dup2(status_pipe[1],3)<0) setup_fail(index,8,errno,3,106);
+        if(dup2(release_pipe[0],4)<0) setup_fail(index,8,errno,4,106);
+        if(dup2(data_pipe[1],5)<0) setup_fail(index,8,errno,5,106);
         for(int f=6;f<limit;f++) {
-            if(close(f)<0 && errno!=EBADF) _exit(114);
+            if(close(f)<0 && errno!=EBADF) setup_fail(index,9,errno,f,114);
         }
         int null=open("/dev/null",O_RDWR);
-        if(null<0) _exit(107);
+        if(null<0) setup_fail(index,10,errno,0,107);
         /* Preserve bounded fixed-tool stderr as raw evidence, never as a receipt. */
-        for(int f=0;f<2;f++) if(dup2(null,f)<0) _exit(108);
+        for(int f=0;f<2;f++) if(dup2(null,f)<0) setup_fail(index,11,errno,f,108);
         if(null>5) close(null);
         for(int s=1;s<NSIG;s++) {
-            if(s!=SIGKILL && s!=SIGSTOP && signal(s,SIG_DFL)==SIG_ERR) _exit(115);
+            if(s!=SIGKILL && s!=SIGSTOP && signal(s,SIG_DFL)==SIG_ERR)
+                setup_fail(index,12,errno,s,115);
         }
         sigset_t empty; sigemptyset(&empty);
-        if(sigprocmask(SIG_SETMASK,&empty,NULL)<0) _exit(109);
-        if(chdir(directory)<0) _exit(110);
+        if(sigprocmask(SIG_SETMASK,&empty,NULL)<0) setup_fail(index,13,errno,0,109);
+        if(chdir(directory)<0) setup_fail(index,14,errno,0,110);
         char start=0;
-        if(all_read(4,&start,1) || start!='A') _exit(111);
+        int start_error=all_read(4,&start,1);
+        if(start_error || start!='A') setup_fail(index,15,start_error,(unsigned char)start,111);
@@
-        execve(image,args,env); _exit(112);
+        execve(image,args,env); setup_fail(index,16,errno,0,112);
@@
-    struct gate_record configured,ready,late; memset(&ready,0,sizeof(ready));
+    struct gate_record configured,ready,late;
+    memset(&configured,0,sizeof(configured)); memset(&ready,0,sizeof(ready));
     ready.canary_errno=-1;
     int e=read_record(status_pipe[0],&configured,sizeof(configured));
+    int configured_read_errno=e,ready_attempted=0,ready_read_errno=-1;
     int configured_ok=!e && valid_gate(&configured,pid,uid,CONFIGURED);
-    if(configured_ok) e=read_record(status_pipe[0],&ready,sizeof(ready));
+    if(configured_ok) {
+        ready_attempted=1;
+        e=read_record(status_pipe[0],&ready,sizeof(ready));
+        ready_read_errno=e;
+    }
     int ready_ok=configured_ok && !e && valid_gate(&ready,pid,uid,SANDBOXED);
@@
-    if(!released && c->fault!=1 && c->fault!=2) (void)kill(pid,SIGKILL);
+    int observer_kill_sent=0;
+    if(!released && c->fault!=1 && c->fault!=2) {
+        (void)kill(pid,SIGKILL); observer_kill_sent=1;
+    }
@@
-        if(!exited) (void)kill(pid,SIGKILL);
+        if(!exited) { (void)kill(pid,SIGKILL); observer_kill_sent=1; }
@@
     if(wait_owned(pid,&status)<0) die("owned-waitpid");
+    emit_diagnostic(index,101,configured_read_errno,
+        configured_read_errno ? -1 : (int)configured.phase,
+        configured_read_errno ? -1 : configured.error);
+    emit_diagnostic(index,102,0,configured_read_errno ? -1 : configured.pid,configured_ok);
+    emit_diagnostic(index,103,ready_read_errno,
+        ready_read_errno ? -1 : (int)ready.phase,ready_read_errno ? -1 : ready.error);
+    emit_diagnostic(index,104,0,ready_attempted,ready_ok);
+    emit_diagnostic(index,105,0,observer_kill_sent,status);
+    emit_diagnostic(index,106,0,WIFEXITED(status) ? WEXITSTATUS(status) : -1,
+        WIFSIGNALED(status) ? WTERMSIG(status) : 0);
+    emit_diagnostic(index,107,0,registered,released);
+    emit_diagnostic(index,108,0,configured_ok,ready_ok);
     if(kq>=0) close(kq);
```

这是无行号、精确上下文的完整变更资产，不直接用 `git apply` 解析 `@@` 无行号块；实施作者使用 apply_patch 的对应上下文替换并核完整差异。原注释、未列函数/正式case输出完全保持。最早失败 syscall errno 在函数参数求值时按值传入；调用 emitter 不再查询其来源 errno。原合取短路拆分保持调用顺序与原退出位置/退出码；readback不符不再打印ambienterrno。`observer_kill_sent`仅表示调用发生，不声明kill成功、进程原来存活或因观察者而死。

getrlimit mismatch目前只定位CPU或FSIZE与exit116，不展示可能为64位的实际limit值；这是刻意最小化。若两格证明该分支，后续独立最小诊断可冻结真实宽度字段，不在本片截断或猜数。trampoline/gate既有 send_gate(FAILED,error) 不加重复日志：root完整读取的 wire phase/error 已足够定位到配置/ready阶段，具体syscall仍需后续证据。

## 4. Task 3：审查、本机必要检查与线上双格

**Dependencies:** Task 2
**Parallelizable:** No（fresh SPEC → 不同 QUALITY；原候选终结后 root 发布）

- [ ] 本机实际4个新便携TEST GREEN、原 TestM0a1Protocol 5个 GREEN，无error/skip；AST、diff whitespace、秘密、固定vendor检查通过。没有全量本机或本机macOS编译信用。
- [ ] 独立审查核所有旧 `_exit` 值/失败操作/顺序不变；无重试/放宽；诊断不参与 release/exec/三态/classification；新 TEST 仅抽取实际 emitter，不用替身。
- [ ] root 复核当前候选所有相关线上结果已采集且终结；按 main-only 线上优先流程提交推送待验收候选，不创建分支/tag、不取消旧run、不rerun隐藏失败。
- [ ] 不改CI；原双格照常编译并执行同一formalRED入口。分别绑定实际SHA、job、artifact、OS/build/kernel/arch、binary/source hashes、nativeexit与原始stdout/stderr。
- [ ] stderr最早stage优先于末尾ambienterrno；记录每case101–108行与worker首失败行。stdout缺失/audit缺失/原生exit非0继续是ERROR，不能改成RED。
- [ ] 真正formalRED仍仅是原 `test_cap1_quota_semantic` 因实际fork成功出现指定断言失败，其他全部正式case通过、无ERROR/SKIP；两个平台均达到后才能另派不同SOURCE作者。诊断GREEN不满足此门。

未取得最早分支时继续保留未知，不归咎平台/资源/Seatbelt。若worker被观察者kill掩盖原退出，现有wait_status只能证明实际终态；不能据其推原原因。后续需要新增握手/改变kill时序时，必须另设计审查，不在本片偷改流程。

## 5. 自审、交接与信用边界

实施记录（下方完整代码资产逐字不变）：原冻结双审文档SHA为ad54f89e，本节进度追加及checkbox改变当前文档摘要，不伪称原审批覆盖新字节。TEST作者与root各正式RED4方法/5AssertionFail/0ERRORskip，root5fc5ab/.002s；TEST d27d3ad2840cfa913e6beb15eda6918ccea07b9a32535cb6a2285d6fc1a997f1与fence相等。不同SOURCE作者仅7hunk，实际driver01814ba499cf43e2247562c67bbc6cd89b2275d9de544b11e9345f956c8b22c7；作者GREEN9，root fa2303 9/.328s/0F/Eskip，实际freshSPEC→不同QUALITY均C0/I0/M0。作者完整日志`/home/orbbec/icode-m0a1-source-evidence.O28lhE/green-nine.log` SHA35fe877f106287e00c9b5b98338761cf1521cc902fe4b8ff3067b7b67b2e980a。只授诊断软件，原生两架构待新SHA；没有limit.c或quotaGREEN。

需求覆盖：真实问题/旧实现/调用链在§0；第一configured/ready观察与workerexit在§1/3；缺诊断的有效结构断言RED与实际emitter host执行在§2；全部原formal门与线上优先在§4。完整M0a2/M0b/M1/M2/M3/installed/至少90%/R2/R3均不由本诊断解除。macOS group清理例外不变。

【架构级自检报告】

- 语法/编译：修订后已实际静态解析本文1段Python TEST AST（99行、4个test方法），完整driver patch为110行、7个hunk，旧上下文在冻结driver中各精确匹配1次；fence成对，文档whitespace检查无诊断。C patch仅文档，未编译，不宣称原生通过。
- 依赖/调用链：已完整读driver/trampoline/gate/controller/oracle和批准设计计划；只诊断，不接产品。
- 逻辑/边界：固定整数/固定行数/192字节；wire完整才展示字段，语义valid另列。
- 异常处理：立即保存真实错误；root原SIGPIPE忽略不变，setup_fail最终退出路径成功阻塞SIGPIPE才写、失败不写仍原exit，不恢复pending mask；真实brokenpipe及健康出口正控已冻结但未运行。ambient错误不作归因。
- 关联模块：本次仅本文；后续严格两文件，旧formal/CI/controller/profile不改。
- 兼容安全：没有放宽阈值、权限、release、清理或quota门；无新系统安装。
- 可运行性：文档待fresh双审；未来便携测试只有Linux整数emitter软件信用，真实macOS第一失败点及formalRED仍待验收。

---
**Execution Mode:** serial

本次doconly授权覆盖技能默认自动执行/新worktree流程：写完冻结SHA后立即停止写，等待root完整阅读及fresh SPEC → 不同 QUALITY。不提交、不推送、不运行文档资产。
