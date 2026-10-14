# macOS M0a1 已接收 gate 只读观察 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 起草时仅交付 PLAN；此后 root 完整阅读、新 SPEC → 不同 QUALITY 零遗留，已按独立 TEST → 实际 RED → 不同 SOURCE 执行，当前状态见执行记录。原生观察仍待新候选，不提前实施 quota。

**Goal:** root observer 展示现有完整接收 gate 的原始标识及凭据，缩小 pre-CONFIGURED FAILED/EPERM 的未知范围，不猜修复、不实现 quota SOURCE。

**Architecture:** 仅在现有 root wait 后增加两个固定、有界 stderr 行，读取 configured/ready 的现有 struct 字段。完整接收与协议有效性分账；未接收完整记录不读取初始化内容，groups!=1 时 group 不授观察信用。诊断失败恢复 errno，不参与原 release、phase、exit、正式断言或 CI 分类。

**Tech Stack:** 现有 C11、inttypes.h、stdio；Python stdlib unittest；Linux cc 仅执行实际 helper 的软件测试，无新依赖。

---

## 基线、范围及三问

观察日期 2026-10-14。权威工作区 `/home/orbbec/projects/icode`，main HEAD `14211972bb1e824bbd993dbe423bceafa882693f`；vendor 固定 `21566a589cbe98bd35372a04bbb6ca1c51d8eed2` 不动。root 已实际完成 sequential-thinking `a0baab` 三步：先观察已有字段 → root-only → unsigned/unknown 不改变 formal 边界。本作者完整读 writing-plans、driver、现 diagnostics TEST、controller、前一 diagnostics PLAN；不把旧 PLAN 的旧候选结果当新候选证据。

起草时基线文件 SHA-256（实施后摘要见执行记录）：

| 文件 | SHA-256 |
| --- | --- |
| `native/mac/tests/icode_m0a1_driver.c` | `01814ba499cf43e2247562c67bbc6cd89b2275d9de544b11e9345f956c8b22c7` |
| `tests/test_macos_m0a1_diagnostics.py` | `d27d3ad2840cfa913e6beb15eda6918ccea07b9a32535cb6a2285d6fc1a997f1` |
| `scripts/run_macos_m0_ci.py` | `770669a24e8aa9437b5c586a0d57c65d90aaf833a785eec70bdb575f346058ad` |
| 前一 `2026-10-14-macos-m0a1-harness-diagnostics.md` | `9387aa766ec6b48dde4358be4481fd916a74bbf0c6e63dc526d7eb7f6d650a60` |

真实问题：root 已完整收到第一 gate，但只展示 phase/error/pid，无法区分 root/image guard、降权短路和凭据后置检查的观察形态。已有实现：72 字节 gate 已含 magic/version/length/pid/phase/error 和六个 uint32 凭据；复用它，不加 wire 字段。调用链：trampoline → send_gate → root read_record → valid_gate → ready → release；新 helper 只在 wait_owned 成功后、旧 101–108 诊断旁调用，不影响这些判定。

root 提供的新候选实际证据：两个 native 编译通过；native exit2、controller infrastructure error、cleanup unknown，不是正式 RED。各 case 已见 stage101 error0/detail3/result1（完整收到 FAILED/EPERM）、102 configured0、103 -1/-1/-1（ready 未读）、105 raw24064、106 exit94、108 configured0/ready0；末尾 errno60 为 ambient。当前证据未输出 gate 凭据；不能仅凭 EPERM 指定失败 syscall。`send_gate` 的 getrlimit 失败还能改写原 phase/error，因此新输出仍不是无条件的第一失败 errno。

只允许后续两文件：TEST 向现 `tests/test_macos_m0a1_diagnostics.py` 末尾追加完整类；SOURCE 仅 `native/mac/tests/icode_m0a1_driver.c` 下列两处 patch。正式 TEST `tests/test_macos_task_quota_probe.py`、baseline、limit 源、controller、CI、profile、wire ABI、signal、release 条件、phase、exit 均冻结。起草阶段实际只新增本文；后续已按执行记录实施 TEST/SOURCE，CI未改。作者不 Git 写操作、不创建 worktree，root按用户 main-only 统一交付；起草时 doc-only 限制覆盖 skill 的自动执行建议。

## 研究输入与归因上限

复用 `docs/agent-landscape-live.md` 的固定 Codex 证据及 root 2026-10-14 独立只读研究：[Codex exec.rs L965–L1021](https://github.com/openai/codex/blob/27065a91ccbf5ba8532844be3777fcf83b77820d/codex-rs/core/src/exec.rs#L965-L1021)，版本 `27065a91ccbf5ba8532844be3777fcf83b77820d`、Apache-2.0，仅借 transport/protocol/exit 分账机制，无代码复制、依赖或权限新增，不声称刷新 HEAD/全部20项。[Apple getgroups(2)](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/getgroups.2.html) 与 [setgroups(2)](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/setgroups.2.html) 为官方语义参照，观察日期 2026-10-14；当前源码 `credentials` 两次 getgroups 与 `send_gate` 再次 getgroups 是不同采样，不互作成功证明。

采纳：展示已收到 gate 的原字段；收益是无需改 worker/wire 即缩小凭据变化位置，成本是一个 helper 和两条固定调用。暂缓：任何 getgroups/setgroups/setgid/setuid 修复、root/image guard 拆分和 quota SOURCE。不适配：用 case 常量填 observed 值、unsigned 转成 -1、zeroed group 当真实观察、编译通过或软件 GREEN 当原生 RED。

即使 uid/euid/gid/egid 全零，也只能说该 gate 采样仍 root，不能区分 guard 与 setgroups 失败；部分已降权也不独立证明哪一 syscall 失败。全等 expected_uid 仍不能证明两次 credentials getgroups 曾通过，也不能排除 limit 相关返回或 send_gate getrlimit 覆盖。groups 为 UINT32_MAX 仅表示 wire 的 getgroups 失败哨兵，不伪装 signed -1。下一决策必须等新候选原始日志。

## 输出合同

marker 固定 `M0A1_GATE_DIAG`，`format_version=1` 是诊断格式版本，`wire_version` 才是收到的 wire version。slot1/2 表示 configured/ready 读取位置，不能代替实际 phase。`received=1` 仅当原 read_record 返回0；不要求 valid_gate 成功，坏 magic/version/length 也原样显示。`expected_uid` 是 observer 已保留的 uid，明确不叫 observed。未收完整记录输出 `received=0`，全部 wire 字段 `unknown`；不读部分缓冲或 memset0。group 只有完整接收且 groups==1 时 `group_observed=1` 并显示 unsigned 值，其余 `group_observed=0 group=unknown`。不查名字、路径、argv、环境或其它用户数据。

每行栈缓冲512字节，snprintf 越界则不写；每调用一次 fwrite、不重试、不调用 die、保存恢复 errno。root 原 SIGPIPE ignore 保持；没有新增 signal 操作。最多7case×2=14条、每条严格<512字节，总新输出<7168字节；原诊断最大12096字节，新旧固定诊断合计<19264字节，低于既有65536 stderr预算。外部固定工具的未知输出不由此证明有界；controller 原 truncation 拒绝机制不变。

## Task 1：不同 TEST 作者冻结实际断言 RED

**Dependencies:** None（但必须先 root 全文阅读及 fresh SPEC → 不同 QUALITY 零遗留）
**Parallelizable:** No（先 TEST 冻结，SOURCE 作者不能先写 helper）

- [x] TEST 作者只在现文件末尾追加下列完整类；前4个测试逐字不动。测试从真实 driver 抽取实际 gate struct 和 helper；不以重写 emitter 的 mock 作为通过证据。
- [x] 运行 `python3 -m unittest discover -s tests -p test_macos_m0a1_diagnostics.py -v`；预期旧4方法通过、新6方法出现有效 `GATE_OBSERVER_ABSENT` 断言 RED，无 ImportError/编译失败/skip。记录方法数与 subTest failure数分别统计，不硬写成相同数量。
- [x] TEST 作者交给 root 全文及文件 SHA；root 复现必要针对性 RED。不能把此诊断软件 RED 当 `M0A1_QUOTA_REJECTION` 原生正式 RED。

追加代码（复用该文件已有 imports/ROOT/DRIVER）：

```python
@unittest.skipUnless(sys.platform == "linux", "Linux gate observer software only; no native credit")
class TestM0a1GateObservation(unittest.TestCase):
    def run_gate(self, mode):
        source = DRIVER.read_text(encoding="utf-8")
        found = re.search(
            r"/\* M0A1_GATE_OBSERVER_BEGIN \*/\n(.*?)"
            r"/\* M0A1_GATE_OBSERVER_END \*/", source, re.S)
        self.assertIsNotNone(found, "GATE_OBSERVER_ABSENT")
        record = re.search(r"struct gate_record \{.*?\n\};", source, re.S)
        self.assertIsNotNone(record, "actual gate struct required")
        cc = shutil.which("cc")
        self.assertIsNotNone(cc, "Linux cc required; not a skip")
        harness = r'''
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <inttypes.h>
#include <limits.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
RECORD
HELPER
int main(int argc,char **argv) {
    if(argc!=2) return 9;
    int mode=atoi(argv[1]);
    struct gate_record r={.magic=123,.version=7,.length=99,.phase=3,
        .error=EPERM,.pid=42,.uid=0,.euid=60001,.gid=0,.egid=60002,
        .groups=1,.group=UINT32_MAX};
    if(mode==1) {
        r.magic=r.version=r.length=r.phase=UINT32_MAX;
        r.error=r.pid=INT32_MIN;
        r.uid=r.euid=r.gid=r.egid=r.groups=r.group=UINT32_MAX;
    }
    if(mode==6) r.groups=0;
    if(mode==7) r.groups=2;
    if(mode==3) {
        if(!freopen("/dev/full","w",stderr) || setvbuf(stderr,NULL,_IONBF,0)) return 8;
    }
    if(mode==4) {
        int fds[2];
        if(signal(SIGPIPE,SIG_IGN)==SIG_ERR || pipe(fds)<0 ||
           close(fds[0])<0 || dup2(fds[1],2)<0 || close(fds[1])<0 ||
           setvbuf(stderr,NULL,_IONBF,0)) return 7;
    }
    struct gate_record before=r;
    errno=EAGAIN;
    if(mode==2) emit_gate_observation(0,1,60000,0,NULL);
    else if(mode==5) {
        for(unsigned i=0;i<7;i++) {
            emit_gate_observation(i,1,60000,1,&r);
            emit_gate_observation(i,2,60000,0,NULL);
        }
    } else emit_gate_observation(UINT_MAX,2,UINT32_MAX,1,&r);
    if(errno!=EAGAIN || memcmp(&r,&before,sizeof(r))) return 6;
    if((mode==3 || mode==4) && !ferror(stderr)) return 5;
    return mode==5 ? 2 : 0;
}
'''.replace("RECORD", record.group(0)).replace("HELPER", found.group(1))
        with tempfile.TemporaryDirectory(prefix="icode-m0a1-gate-") as tmp:
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
            self.assertEqual(actual.returncode, 2 if mode==5 else 0, actual.stderr)
            self.assertEqual(actual.stdout, b"")
            return actual.stderr

    def test_actual_fields_and_unsigned_group_positive_control(self):
        raw = self.run_gate(0)
        expected = (
            "M0A1_GATE_DIAG format_version=1 case_index=4294967295 slot=2 received=1 "
            "raw_magic=123 wire_version=7 length=99 pid=42 phase=3 error=" + str(errno.EPERM) +
            " expected_uid=4294967295 uid=0 euid=60001 gid=0 egid=60002 "
            "groups=1 group_observed=1 group=4294967295\n")
        self.assertEqual(raw, expected.encode("ascii"))

    def test_unsigned_extremes_and_group_failure_unknown(self):
        raw = self.run_gate(1).decode("ascii")
        expected = (
            "M0A1_GATE_DIAG format_version=1 case_index=4294967295 slot=2 received=1 "
            "raw_magic=4294967295 wire_version=4294967295 length=4294967295 "
            "pid=-2147483648 phase=4294967295 error=-2147483648 "
            "expected_uid=4294967295 uid=4294967295 euid=4294967295 "
            "gid=4294967295 egid=4294967295 groups=4294967295 group_observed=0 group=unknown\n")
        self.assertEqual(raw, expected)
        self.assertLess(len(raw.encode("ascii")), 512)

    def test_unreceived_record_has_no_fabricated_values(self):
        expected = (
            "M0A1_GATE_DIAG format_version=1 case_index=0 slot=1 received=0 "
            "raw_magic=unknown wire_version=unknown length=unknown pid=unknown "
            "phase=unknown error=unknown expected_uid=60000 uid=unknown euid=unknown "
            "gid=unknown egid=unknown groups=unknown group_observed=0 group=unknown\n")
        self.assertEqual(self.run_gate(2), expected.encode("ascii"))

    def test_non_single_group_is_not_observed(self):
        for mode, count in ((6, 0), (7, 2)):
            with self.subTest(groups=count):
                raw = self.run_gate(mode).decode("ascii")
                self.assertIn(" groups=" + str(count) + " group_observed=0 group=unknown\n", raw)
                self.assertNotIn("group=4294967295", raw)

    def test_failed_outputs_preserve_errno_and_exit(self):
        for mode in (3, 4):
            with self.subTest(mode=mode):
                self.assertEqual(self.run_gate(mode), b"")
        # Healthy output is required by the first test, so a silent helper cannot pass.

    def test_fixed_call_bound_and_root_only_integration(self):
        raw = self.run_gate(5)
        self.assertEqual(raw.count(b"\n"), 14)
        self.assertLess(len(raw), 14 * 512)
        self.assertTrue(all(len(line)+1 < 512 for line in raw.splitlines()))
        source = DRIVER.read_text(encoding="utf-8")
        self.assertEqual(source.count("emit_gate_observation("), 3)
        root = source[source.index("    if(wait_owned(pid,&status)<0)"):
                      source.index("    if(kq>=0) close(kq);")]
        self.assertIn("emit_gate_observation(index,1,(uint32_t)uid,configured_read_errno==0,&configured);", root)
        self.assertIn("emit_gate_observation(index,2,(uint32_t)uid,ready_attempted && ready_read_errno==0,&ready);", root)
        worker = source[source.index("static void trampoline("):source.index("static int valid_gate(")]
        self.assertNotIn("emit_gate_observation(", worker)
```

测试把 magic123/version7/length99 等故意不合法 wire 原样输出，证明 helper 不把协议失败隐藏成未知；这些值仅软件输入，不是原生 case 观察。NULL+received0 强制不读取缺失 record；两种非单组和失败哨兵验证 group 不伪造。实际 helper 编译、健康输出精确正控、真实 /dev/full 与匿名 broken pipe 负控共同防止恒定不输出通过。mode5 对实际传入的整个 record 做逐字节前后比较（包含 error），检查 errno 并仍 exit2；不借一个未传入 helper 的局部错误常量充当保护证明。整个 native driver 的外部 e/退出语义仍由两hunk差异审查与新原生候选核实，不能由 harness 冒领。root-only integration 静态断言只证明接线位置，后续差异审查仍须核 child 全部无变更。

## Task 2：不同 SOURCE 作者应用最小 patch

**Dependencies:** Task 1 的 TEST 冻结、有效断言 RED、root 复核
**Parallelizable:** No（不同作者；只允许 driver 两处改动）

- [x] 使用 apply_patch 按以下精确上下文加入 helper 与两行调用；这是上下文 patch 资产，不以无行号 `@@` 交给 git apply。

```diff
--- a/native/mac/tests/icode_m0a1_driver.c
+++ b/native/mac/tests/icode_m0a1_driver.c
@@
 /* M0A1_DIAGNOSTIC_EMITTER_END */
+/* M0A1_GATE_OBSERVER_BEGIN */
+static void emit_gate_observation(unsigned index,unsigned slot,uint32_t expected_uid,
+                                  int received,const struct gate_record *r) {
+    int saved=errno;
+    char row[512],group[11];
+    int n;
+    if(!received) {
+        n=snprintf(row,sizeof(row),
+            "M0A1_GATE_DIAG format_version=1 case_index=%u slot=%u received=0 "
+            "raw_magic=unknown wire_version=unknown length=unknown pid=unknown "
+            "phase=unknown error=unknown expected_uid=%" PRIu32 " uid=unknown euid=unknown "
+            "gid=unknown egid=unknown groups=unknown group_observed=0 group=unknown\n",
+            index,slot,expected_uid);
+    } else {
+        /* group is meaningful only when the existing wire reports one group. */
+        const char *observed_group="unknown";
+        if(r->groups==1) {
+            int g=snprintf(group,sizeof(group),"%" PRIu32,r->group);
+            if(g>0 && (size_t)g<sizeof(group)) observed_group=group;
+        }
+        n=snprintf(row,sizeof(row),
+            "M0A1_GATE_DIAG format_version=1 case_index=%u slot=%u received=1 "
+            "raw_magic=%" PRIu32 " wire_version=%" PRIu32 " length=%" PRIu32
+            " pid=%" PRId32 " phase=%" PRIu32 " error=%" PRId32
+            " expected_uid=%" PRIu32 " uid=%" PRIu32 " euid=%" PRIu32
+            " gid=%" PRIu32 " egid=%" PRIu32 " groups=%" PRIu32
+            " group_observed=%d group=%s\n",
+            index,slot,r->magic,r->version,r->length,r->pid,r->phase,r->error,
+            expected_uid,r->uid,r->euid,r->gid,r->egid,r->groups,
+            r->groups==1,observed_group);
+    }
+    if(n>0 && (size_t)n<sizeof(row)) (void)fwrite(row,1,(size_t)n,stderr);
+    errno=saved;
+}
+/* M0A1_GATE_OBSERVER_END */
 static void worker_fail(int error) { send_gate(FAILED,error); _exit(94); }
@@
     emit_diagnostic(index,108,0,configured_ok,ready_ok);
+    emit_gate_observation(index,1,(uint32_t)uid,configured_read_errno==0,&configured);
+    emit_gate_observation(index,2,(uint32_t)uid,ready_attempted && ready_read_errno==0,&ready);
     if(kq>=0) close(kq);
```

- [x] 运行 Task 1 同一命令，预期10个方法全部实际执行、0failure/error/skip；旧4方法保持 GREEN，新增6方法通过。
- [x] 运行 `python3 -m unittest discover -s tests -p test_macos_task_quota_probe.py -k TestM0a1Protocol -v`，预期旧5协议测试通过，不运行正式 native 类，不授原生信用。若当前 Python 不支持 -k，先核版本，不能偷偷改 TEST 或跳过协议检查。
- [x] root 确认实际 driver diff 与上述两hunk逐字一致；没有 child/wire/signal/limit/formal/controller/CI/baseline 改动。冻结 TEST/driver 全 SHA，并保留完整 stdout/stderr/退出状态。

## Task 3：fresh 双审与线上双平台观察

**Dependencies:** Task 2
**Parallelizable:** No（SPEC → 不同 QUALITY；root 负责候选发布）

- [x] 新 SPEC 审查者逐条核输出合同、unsigned/group/unknown、调用顺序及旧 formal 边界；不同 QUALITY 审查者核真实测试正负控、固定输出预算、错误/exit 保持和两hunk最小范围。不得复用作者自审作独立批准。
- [ ] root 必要本机密钥扫描、固定 vendor、AST/whitespace 和针对性回归通过后，沿用户 main-only 线上优先授权提交推送待验收候选；不建分支/tag、不取消或反复重跑覆盖原失败。具体发布由 root 统一安排，本 PLAN 作者不执行。
- [ ] 保持原 CI，分别收集 arm64/x86_64 实际 candidate SHA、run/job/attempt、平台身份、artifact、binary/source SHA、原始stdout/stderr和退出状态。两格 compilepass 不等于正式 RED；nativeexit非0/truncation/cleanupunknown继续报 infrastructure ERROR。
- [ ] 每case先记录完整原始 M0A1_GATE_DIAG 行，再与101–108读结果/wait终态对照。received1且phaseFAILED/errorEPERM不单独推出 syscall；received0或groupunknown保留未知，不借case名/预期uid/root审计补造 observed。不要用尾部 ambienterrno60覆盖实际wireerror。
- [ ] 未达原正式 RED 继续独立诊断，不派 quota SOURCE。真正 RED 仍是原 controller 要求的唯一 `test_cap1_quota_semantic` / `M0A1_QUOTA_REJECTION` fork成功断言、其它正式case通过且无ERROR/SKIP；两个平台均满足后才不同 SOURCE 作者进入后续 quota 实现。

## 自审及交接

### 2026-10-14 实际执行记录（优先于起草时 doc-only 描述）

批准原 PLAN SHA256 `8153545cbb45448c0f416be3c90c8c5650bdaf6ce5f4b99d61be699aaeac2d4b`，root 仓外原文 `/home/orbbec/icode-frozen-gate-8153545/approved-plan.md` 已核同摘要。本次仅更新进度，不改两个代码围栏资产。PLAN fresh SPEC→不同 QUALITY、实际 SOURCE fresh SPEC→不同 QUALITY，四审均 C0/I0/M0；不把两次计划审查替代实际源码审查。

独立 TEST 作者仅追加130行，旧4280字节原样；新 TEST SHA256 `8d953cccde75edc8e78423a8ad2c59ddd25c5079eaf3ec405eec27883961df68`。作者与 root 都实际10方法/8条 `GATE_OBSERVER_ABSENT` AssertionError/0ERROR/skip/exit1，root工具0d95f1/.409s。不同 SOURCE 作者仅37行/2hunk，driver `1fe2b712636ed31d51e9192783e977fd1e35657fcc434bf5960a7030e4fcfd43`，与批准投影逐字一致，TEST未改。作者实际10/1.166s+5/.001s，root实际10/1.320s+5/.001s，均0failure/error/skip/exit0；实际SPEC另15通过，QUALITY另新增6/.882s通过。全部仅 Linux helper 软件及旧协议，不授完整macOS编译、正式RED或quota。

root 完整工具输出逐字保存于同一仓外目录：`root-red.log` SHA `3eba48b77a8f4b89f94e42570dac22d9ac947f7111293b92c8ee6bf4f627b436`；`root-green-0.log` SHA `527df2183f1cbd3432f521b57a8819dcdf1c2513d8cd81a9b78a335bd123f1bb`；`root-green-1.log` SHA `ea2f8c1b44d831a2b41e43857a8a9408bac84fdcc1fec8ccf02f10b4005fd5f6`。这是工具输出完整转录，非进程直接重定向，不冒充其它来源日志。秘密原单门99c826与固定子仓原单门062cca实际通过，原 CI55job均终态后才安排新候选，不取消旧失败。main候选提交及新双架构原生结果仍待，limit.c不存在。

覆盖映射：Task1实际 helper正负控覆盖unsigned/缺包/group未知/错误不变/有限输出；Task2只有observer helper与两root调用；Task3保留CI/formal/baseline及实际双格证据边界。root/imageguard、降权短路、credentials两次getgroups与send_gate getrlimit覆盖风险只解释观察上限，不在本片修复。无额外遥测框架或产品新接口。

【架构级自检报告】

- 语法/编译：嵌入Python及实际抽取helper的Linux严格C编译通过；完整macOS driver待线上编译。
- 依赖/调用链：复用已有 gate_record 与 inttypes.h；不加wire字段，不改 child/send_gate/valid_gate。
- 逻辑/边界：完整收包才读raw；全部uint32明确unsigned；groups仅等1才观察group；expected_uid明确是observer预期。
- 异常处理：snprintf边界、单次fwrite、errno恢复；root原SIGPIPE处置保持，输出失败不替换原error/exit。
- 关联模块：已实施现诊断TEST追加和driver两hunk，formal/controller/CI不变。
- 兼容安全：release/phase/exit/RED/baseline均冻结；固定白名单数字与unknown，不含路径/名字/秘密。
- 可运行性：实际Linux10诊断+5协议通过，零失败/错误/跳过；原生与正式RED仍待新SHA双平台实证。

---
**Execution Mode:** serial

原 doc-only 交接后已按上述链完成软件实施与实际双审，下一步是 root 线上候选及真实原生观察。任何测试/编译/原生通过只能追加实际证据，不能由本计划的预期冒领。
