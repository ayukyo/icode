# macOS process groups W1 native verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development (recommended) or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用同一生产 POSIX TU/predicate，在 ARM/Intel 原生独立固定 TEST 中验证实际单组、同 PID exec 继承及额外组拒绝，并把 W1 证据纳入同候选接受门。

**Architecture:** 四个现有有限身份租约函数机械抽到私有 `.inc`，原 driver 原位 include，不增加通用 root 参数。独立 TEST executable 使用同一租约目录，为正控 UID、负控 UID 和额外 GID 永久保留三个独占数字身份；root observer 保持 root，子进程仅跑固定观测/原地 exec。controller 保留现有正式 oracle，新增独立 W1 证据执行/审计和先决门。

**Tech Stack:** C11/POSIX、macOS libproc/sysctl/ACL/CommonCrypto、CMake、Python unittest、现有双原生 GitHub CI。

---

## 本轮边界与冻结证据

仅新增本文；不实施 TEST/SOURCE/CI/Git/系统操作，不本机 native，不使用模型 KEY。用户 main-only/线上优先授权覆盖技能 worktree/自动提交/自动执行建议；作者不调用执行技能。root 全文与 fresh SPEC → 不同 QUALITY 通过之后，才独立 TEST→真实 gate RED→不同 SOURCE→实际双审→待验候选。既有 dirty handoff 保留。

工作区 `/home/orbbec/projects/icode`；基线 main `67cf60ed457c7ab264c4d4c5c498b2826b6e4bcc`；vendor `21566a589cbe98bd35372a04bbb6ca1c51d8eed2` 不改。DESIGN `docs/nbl/specs/2026-10-14-macos-process-groups-interface-design.md`，99 行，SHA `8fb4484dce9c11f673fdbed623951b36f344ce62d5931f53b5260f92c4141367`，root `1ccf80` 已重新全文批准。root `a7c396` 使用显式UTF-8、verified ASCII英文决策摘要实际调用 sequential-thinking 六步，前3步专用于W1：需求→最小机械复用/TEST自校验与生产GateRED区分→同SHA全门/UID/GID/cleanup风险；旧 `fd0ed2` 中文管道受PS5 ASCII传输影响，不授完整语义送达信用。本作者不冒称另调MCP，apply_patch与文件SHA原样传输不受该旧管道问题影响。

W0 历史结果由 root 提供，本作者不重复下载：Linux22；Intel job `115823170211` / artifact `11889367248` / SDK15.5 / binary摘要前缀 `dd6a336e`；ARM job `115823169998` / artifact `11890446569` / SDK26.5 / binary前缀 `b0f043d6`。两格 ordinary `_getgroups` object+final/14 raw hashes、7 audit cases、协议5/正式5，唯一 quota assertion failure、0 error/skip，`semantic_RED_confirmed`；cleanup仅 owned-root。该历史不是 quota GREEN，不替代 W1 新 SHA 的同项重跑。

| 当前只读核对文件 | SHA-256 |
| --- | --- |
| driver | `a65f067ec9c6b32eb3bb7cc7afd803fe465d02273b5484561b237db59c31f673` |
| controller | `9cbf42606725c020be28d82572102fce0f21519daa68d0adb19c5b7d1108ae7a` |
| process_groups.c | `b0a75c2ca2ee28334821c085c4460ab130ba6e1a02acc488d992491d57984ce6` |
| 原 formal TEST | `d0438e66bd356aefdfd2ebdd8edaa12529a88f18fb8c5556d2404c672291dafd` |
| 已发布 W0 PLAN | `18d761850913d3f76d915f6895b1e022a0f1e1cfcee2400d3dcd1dcb98f6d9ef` |

三问：真实缺口是 W1 独立原生双组反例与 exec 继承证据；已有正确 TU/predicate、有限 lease、root protected image、有限 observer 和 bounded binding 可复用；依赖为新 TEST target→独立审计→controller W1先决门→原7case正式分类。原 helper行为正确，W1 fixture本身是 TEST，不能人为制造已发布生产 bug 的 RED。

主源复用批准 DESIGN §2 的 Apple Libc `4e34d055...` / XNU `ac9718...` 固定公共机制和许可边界：采纳实际进程向量、TU隔离；不适配目录账户/rawsyscall/私有alias；暂缓 quota实现。新增 supplementary 碰撞扫描只用本机 SDK公开 `sysctl(KERN_PROC_PID)` 的 `kinfo_proc` 组向量，实际长度未知即拒绝。作者于2026-10-14另只读核对同一XNU固定提交的 [sysctl.h公开结构](https://github.com/apple-oss-distributions/xnu/blob/ac9718fb1af618d5ce8678d0dc6e8a58f252216f/bsd/sys/sysctl.h#L956-L989) 及 [fill_user64_eproc实际填充](https://github.com/apple-oss-distributions/xnu/blob/ac9718fb1af618d5ce8678d0dc6e8a58f252216f/bsd/kern/kern_sysctl.c#L1034-L1047)：接口提供有界组数和向量，来自进程credential；公开版本不冒称runner内核版本。只借公开字段/机制，不复制 Apple 实现或引入许可不明代码；实际SDK/原生支持仍待CI验证。

## 文件与职责

| 文件 | 责任 |
| --- | --- |
| 新 `tests/test_macos_process_groups_native.py` | 独立 W1账本断言、旧controller接受逻辑的真实语义RED、真实runner采集/审计/发布软件正负控、reservation软件模型、机械抽取inverse保护 |
| 新 `native/mac/tests/icode_m0a1_identity_lease.inc` | 原四函数逐字移动；不加root入口/参数 |
| `native/mac/tests/icode_m0a1_driver.c` | 仅原位替换四函数为 include，exactinverse复原当前字节 |
| 新 `native/mac/tests/icode_m0a1_process_groups_native.c` | 固定 root TEST、三租约、四ID/组观察、共用predicate、同PIDexec、root独立PID/start/exit审计 |
| `native/mac/CMakeLists.txt` | 独立 `icode_m0a1_groups_native` target 链接同真实 `icode_m0a1_process_groups.c` |
| `scripts/run_macos_m0_ci.py` | 独立W1运行/读取protected账本/验证/摘要与先决门；原formal条件不变 |

无需改 workflow：既有默认构建会构建新target，controller同一次调用执行W1，现有整个output目录及compile/build日志已上传。新native binary通过controller复制到output留证。W1不增加原七case、不改wire72/96/valid_gate/release/phase/exit/classification；不创建 `icode_m0a1_limit.c`。

### Task 1: 独立 TEST 冻结与 controller 真实语义 RED

**Dependencies:** None
**Parallelizable:** No (接受门RED先于不同SOURCE作者)

- [ ] TEST 作者完整阅读本文/DESIGN/W0 PLAN/当前driver/helper/controller/formal；新增下列完整 TEST 文件。新fixture是TEST增补，先冻结这些独立断言与软件自校验，再由不同作者实现fixture及接线；不为正确helper伪造生产回归。

`tests/test_macos_process_groups_native.py`：

```python
import ast
import copy
import errno
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
CONTROLLER=ROOT/"scripts/run_macos_m0_ci.py"
SHA="67cf60ed457c7ab264c4d4c5c498b2826b6e4bcc"

def controller():
    spec=importlib.util.spec_from_file_location("w1_controller",CONTROLLER)
    if spec is None or spec.loader is None:
        raise RuntimeError("controller module infrastructure unavailable")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def verify_groups(rows, sha, digest, arch):
    if len(rows)!=5:
        raise ValueError("W1_GROUPS record count")
    observations=rows[:3]
    ends=rows[3:]
    common={"candidate_sha","binary_sha256","arch","observer_uid","observer_pid","slot","uid","pid"}
    observation_fields=common|set("extra start_sec start_usec root_identity sample_pid live_count sample_uid sample_euid sample_gid sample_egid count count_errno capacity read read_errno group0 group1 predicate_attempted predicate image_stage kernel_exec".split())
    end_fields=common|{"exit_code","term_signal","remaining","retained","cleanup_scope"}
    strings={"candidate_sha","binary_sha256","arch","slot","cleanup_scope"}
    for index,r in enumerate(rows):
        if not isinstance(r,dict) or set(r)!=(observation_fields if index<3 else end_fields):
            raise ValueError("W1_GROUPS exact schema")
        for key,value in r.items():
            expected=str if key in strings else bool if key=="retained" else int
            if type(value) is not expected:raise ValueError("W1_GROUPS exact field type")
    if [r["slot"] for r in observations]!=["single_before","single_after","extra"]:
        raise ValueError("W1_GROUPS record order")
    for r in rows:
        if r["candidate_sha"]!=sha or r["binary_sha256"]!=digest or r["arch"]!=arch:
            raise ValueError("W1_GROUPS candidate/binary/platform")
        if r["observer_uid"]!=0 or r["observer_pid"]<=0:
            raise ValueError("W1_GROUPS root observer")
    a,b,n=observations
    if (a["uid"]==n["uid"] or n["extra"] in (0,a["uid"],n["uid"])
            or any(r["extra"]!=n["extra"] for r in observations)
            or any(not 60000<=value<61024 for value in (a["uid"],n["uid"],n["extra"]))
            or any(r["observer_pid"]!=a["observer_pid"] for r in rows)):
        raise ValueError("W1_GROUPS independent leases")
    for r in observations:
        if (r["uid"]<=0 or r["pid"]<=0 or r["start_sec"]<=0 or r["start_usec"]<0
                or r["observer_pid"]==r["pid"] or r["root_identity"]!=1
                or r["sample_pid"]!=r["pid"] or r["live_count"]!=1):
            raise ValueError("W1_GROUPS PID/start/identity")
        if [r[k] for k in ("sample_uid","sample_euid","sample_gid","sample_egid")]!=[r["uid"]]*4:
            raise ValueError("W1_GROUPS four identity preconditions")
        if r["count_errno"]!=0 or r["read_errno"]!=0:
            raise ValueError("W1_GROUPS reader failure")
        if r["slot"]=="extra":
            if (r["capacity"]!=2 or r["count"]!=2 or r["read"]!=2
                    or {r["group0"],r["group1"]}!={r["uid"],r["extra"]}):
                raise ValueError("W1_GROUPS complete two-group preconditions")
            if r["predicate_attempted"]!=1 or r["predicate"]!=errno.EPERM:
                raise ValueError("W1_GROUPS production predicate refusal")
        else:
            if (r["capacity"]!=1 or r["count"]!=1 or r["read"]!=1
                    or r["group0"]!=r["uid"] or r["group1"]!=4294967295
                    or r["predicate_attempted"]!=1 or r["predicate"]!=0):
                raise ValueError("W1_GROUPS actual single-group acceptance")
    if any(a[k]!=b[k] for k in ("pid","uid","extra","start_sec","start_usec")):
        raise ValueError("W1_GROUPS same PID exec inheritance")
    if (a["image_stage"]!=0 or b["image_stage"]!=1 or n["image_stage"]!=0
            or a["kernel_exec"]!=0 or b["kernel_exec"]!=1 or n["kernel_exec"]!=0):
        raise ValueError("W1_GROUPS fixed exec stage")
    for end,r in zip(ends,(a,n)):
        if (end["slot"]!="end" or end["pid"]!=r["pid"] or end["uid"]!=r["uid"]
                or end["exit_code"]!=0 or end["term_signal"]!=0 or end["remaining"]!=0
                or end["retained"] is not True or end["cleanup_scope"]!="owned_root_only"):
            raise ValueError("W1_GROUPS owned exit/retained identity")
    return True

def software_rows():
    common={"candidate_sha":SHA,"binary_sha256":"a"*64,"arch":"arm64",
            "observer_uid":0,"observer_pid":100}
    single=dict(common,slot="single_before",uid=60000,extra=60002,pid=101,
        start_sec=1000,start_usec=1,root_identity=1,sample_pid=101,live_count=1,
        sample_uid=60000,sample_euid=60000,sample_gid=60000,sample_egid=60000,
        count=1,count_errno=0,capacity=1,read=1,read_errno=0,group0=60000,
        group1=4294967295,predicate_attempted=1,predicate=0,image_stage=0,kernel_exec=0)
    after=dict(single,slot="single_after",image_stage=1,kernel_exec=1)
    negative=dict(single,slot="extra",uid=60001,pid=102,sample_pid=102,
        sample_uid=60001,sample_euid=60001,sample_gid=60001,sample_egid=60001,
        count=2,capacity=2,read=2,group0=60002,group1=60001,predicate=errno.EPERM)
    ends=[dict(common,slot="end",pid=r["pid"],uid=r["uid"],exit_code=0,
               term_signal=0,remaining=0,retained=True,cleanup_scope="owned_root_only")
          for r in (single,negative)]
    return [single,after,negative,*ends]

class TestW1Observer(unittest.TestCase):
    def test_healthy_software_rows_and_strict_negative_controls(self):
        rows=software_rows()
        self.assertTrue(verify_groups(rows,SHA,"a"*64,"arm64"))
        changes=[(2,"sample_euid",0),(2,"count",1),(2,"capacity",1),(2,"read",-1),
                 (2,"group1",0),(2,"extra",0),(2,"predicate",0),
                 (2,"predicate_attempted",0),(1,"pid",999),(1,"image_stage",0),(1,"kernel_exec",0),
                 (0,"root_identity",0),(3,"remaining",-1),(4,"exit_code",1),
                 (2,"candidate_sha","b"*40),(2,"binary_sha256","b"*64)]
        for index,key,value in changes:
            with self.subTest(index=index,key=key):
                bad=copy.deepcopy(rows);bad[index][key]=value
                with self.assertRaises(ValueError): verify_groups(bad,SHA,"a"*64,"arm64")
        with self.assertRaises(ValueError):verify_groups(rows[:-1],SHA,"a"*64,"arm64")

class TestW1ControllerAcceptance(unittest.TestCase):
    def run_actual_acceptance_tail(self, groups=None):
        module=controller()
        tree=ast.parse(CONTROLLER.read_text(encoding="utf-8"))
        main=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=="main")
        guarded=next(node for node in main.body if isinstance(node,ast.Try))
        start=next(i for i,node in enumerate(guarded.body)
                   if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Subscript)
                   and isinstance(node.targets[0].slice,ast.Constant)
                   and node.targets[0].slice.value=="protocol_ledger")
        arguments=ast.arguments(posonlyargs=[],args=[ast.arg(arg="metadata")],
            kwonlyargs=[],kw_defaults=[],defaults=[])
        function=ast.FunctionDef(name="actual_acceptance",args=arguments,
            body=guarded.body[start:],decorator_list=[],type_params=[])
        code=compile(ast.fix_missing_locations(ast.Module(body=[function],type_ignores=[])),
                     str(CONTROLLER),"exec")
        class Case:
            _testMethodName="test_cap1_quota_semantic"
        class Formal:
            errors=[];skipped=[];testsRun=5
            failures=[(Case(),"M0A1_QUOTA_REJECTION")]
        class Protocol:
            testsRun=5
        class Args:
            phase="red"
        namespace=dict(vars(module),formal=Formal(),protocol=Protocol(),args=Args(),
            audit={"ledger_sha256":"c"*64,"root_directory":"software-only"},
            rows={"cap1_fork":{"fork_pid":123,"fork_errno":0,"child_byte":1,"payload_cur":2}},
            output=Path("software-only"),write_json=lambda path,value: None)
        exec(code,namespace)
        metadata={"candidate_sha":SHA,"arch":"arm64"}
        if groups is not None:metadata["groups_native"]=groups
        return namespace["actual_acceptance"](metadata)

    def test_existing_acceptance_must_reject_absent_w1_evidence(self):
        with self.assertRaisesRegex(RuntimeError,"W1_GROUPS"):
            self.run_actual_acceptance_tail()

    def test_same_candidate_w1_gate_and_wrong_candidate_control(self):
        good={"result":"native_groups_verified","candidate_sha":SHA,"arch":"arm64",
              "binary_sha256":"a"*64,"ledger_sha256":"c"*64,"binding_sha256":"d"*64,
              "native_exit":0,"cleanup_scope":"owned_root_only_identities_retained"}
        self.assertEqual(self.run_actual_acceptance_tail(good),0)
        for key,value in (("candidate_sha","b"*40),("arch","x86_64"),
                          ("result","unknown"),("ledger_sha256","bad"),("native_exit",1),
                          ("cleanup_scope","unknown")):
            with self.subTest(key=key):
                bad=dict(good);bad[key]=value
                with self.assertRaisesRegex(RuntimeError,"W1_GROUPS"):
                    self.run_actual_acceptance_tail(bad)

class TestW1MechanicalLeaseExtraction(unittest.TestCase):
    def test_driver_inverse_is_exact_original(self):
        driver=ROOT/"native/mac/tests/icode_m0a1_driver.c"
        content=driver.read_bytes()
        marker=b'#include "icode_m0a1_identity_lease.inc"\n'
        if marker in content:
            self.assertEqual(content.count(marker),1)
            lease=(driver.parent/"icode_m0a1_identity_lease.inc").read_bytes()
            content=content.replace(marker,lease,1)
        self.assertEqual(hashlib.sha256(content).hexdigest(),
            "a65f067ec9c6b32eb3bb7cc7afd803fe465d02273b5484561b237db59c31f673")

@unittest.skipUnless(sys.platform=="linux","Linux lease software model only; no native credit")
class TestW1LeaseSnapshotSoftware(unittest.TestCase):
    def test_actual_reservation_unknown_collision_and_success(self):
        native=ROOT/"native/mac/tests/icode_m0a1_process_groups_native.c"
        self.assertTrue(native.is_file(),"native TEST asset absent is infrastructure, not RED")
        source=native.read_text(encoding="utf-8")
        found=re.findall(r"static uid_t reserve_unused_id\(int leases\) \{.*?\n\}",source,re.S)
        self.assertEqual(len(found),1,"actual reservation function must be extracted unambiguously")
        cc=shutil.which("cc")
        self.assertIsNotNone(cc,"required Linux compiler unavailable; not a skip")
        harness=r'''
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/types.h>
enum { UID_COUNT=1024 };
static const char *candidate="software-candidate";
static unsigned mode,lease_count,process_calls,supplementary_calls,first,last;
static unsigned char consumed[UID_COUNT];
static void report(const char *stage,uid_t uid) {
    printf("%s uid=%u leases=%u process=%u supplementary=%u first=%u last=%u\n",
        stage,(unsigned)uid,lease_count,process_calls,supplementary_calls,first,last);
}
static _Noreturn void die(const char *stage) {
    report(stage,0);exit(91);
}
/* Models the existing persistent reservation boundary; no real identity changes. */
static uid_t reserve_uid(int leases,const char *sha) {
    if(leases!=9 || sha!=candidate || lease_count>=UID_COUNT) exit(92);
    uid_t uid=(uid_t)(60000+lease_count);
    unsigned index=(unsigned)uid-60000;
    if(consumed[index]) exit(93);
    consumed[index]=1;
    if(!lease_count) first=(unsigned)uid;
    last=(unsigned)uid;lease_count++;
    return uid;
}
static int supplementary_free(gid_t gid) {
    if((unsigned)gid!=last) exit(94);
    supplementary_calls++;
    if(mode==3 && supplementary_calls==1) return 0;
    if(mode==4 && supplementary_calls==1) return -1;
    return 1;
}
static int process_count(uid_t uid) {
    if((unsigned)uid!=last) exit(95);
    process_calls++;
    if(mode==1 && process_calls==1) return -1;
    if(mode==2 && process_calls==1) return 1;
    if(mode==5) return 1;
    if(mode==6 && process_calls==1) return 1;
    if(mode==6 && process_calls==2) return -1;
    return 0;
}
ACTUAL_RESERVATION_FUNCTION
int main(int argc,char **argv) {
    if(argc!=2) return 96;
    mode=(unsigned)strtoul(argv[1],NULL,10);
    uid_t uid=reserve_unused_id(9);
    report("ok",uid);return 0;
}
'''.replace("ACTUAL_RESERVATION_FUNCTION",found[0])
        cases={
            0:(0,"ok",60000,1,1,1,60000),
            1:(91,"identity-process-snapshot",0,1,1,1,60000),
            2:(0,"ok",60001,2,2,2,60001),
            3:(0,"ok",60001,2,2,2,60001),
            4:(91,"supplementary-snapshot",0,1,0,1,60000),
            5:(91,"supplementary-exhausted",0,1024,1024,1024,61023),
            6:(91,"identity-process-snapshot",0,2,2,2,60001),
        }
        with tempfile.TemporaryDirectory(prefix="icode-w1-lease-software-") as temporary:
            directory=Path(temporary);cpath=directory/"probe.c";binary=directory/"probe"
            cpath.write_text(harness,encoding="ascii",newline="\n")
            built=subprocess.run([cc,"-std=c11","-Wall","-Wextra","-Werror",
                str(cpath),"-o",str(binary)],capture_output=True,timeout=30,check=False)
            self.assertLessEqual(len(built.stdout)+len(built.stderr),65536)
            self.assertEqual(built.returncode,0,built.stderr.decode("utf-8","replace"))
            self.assertEqual(built.stdout,b"")
            for mode,expected in cases.items():
                with self.subTest(mode=mode):
                    actual=subprocess.run([str(binary),str(mode)],capture_output=True,timeout=5,check=False)
                    self.assertLessEqual(len(actual.stdout)+len(actual.stderr),1024)
                    self.assertEqual(actual.stderr,b"")
                    code,stage,uid,leases,process,supplementary,last=expected
                    self.assertEqual(actual.returncode,code,actual.stdout)
                    self.assertEqual(actual.stdout,
                        (f"{stage} uid={uid} leases={leases} process={process} supplementary={supplementary} "
                         f"first=60000 last={last}\n").encode("ascii"))

@unittest.skipUnless(sys.platform=="linux","Linux runner software only; no native or root credit")
class TestW1NativeRunnerSoftware(unittest.TestCase):
    def exercise_runner(self,case):
        from contextlib import ExitStack
        from types import SimpleNamespace
        from unittest.mock import patch
        module=controller()
        self.assertTrue(callable(getattr(module,"run_w1_groups",None)),
                        "missing runner is infrastructure, not a valid semantic RED")
        with tempfile.TemporaryDirectory(prefix="icode-w1-runner-software-") as temporary:
            base=Path(temporary).resolve(strict=True)
            build=base/"build";output=base/"output";build.mkdir();output.mkdir()
            binary=build/"icode_m0a1_groups_native"
            image=b"software fixture bytes; not a Mach-O or native evidence\n"
            binary.write_bytes(image);binary.chmod(0o755)
            digest=hashlib.sha256(image).hexdigest()
            helper=ROOT/"native/mac/icode_m0a1_process_groups.c"
            obj=build/"CMakeFiles/icode_m0a1_groups_native.dir/icode_m0a1_process_groups.c.o"
            obj.parent.mkdir(parents=True);obj.write_bytes(b"software object bytes")
            sdk=base/"software-sdk";sdk.mkdir()
            compile_argv=[sys.executable,"-c",str(helper),"-o",str(obj)]
            (build/"compile_commands.json").write_text(json.dumps([
                {"directory":str(build),"file":str(helper),"arguments":compile_argv}]),encoding="utf-8")
            rows=software_rows()
            for row in rows:row["binary_sha256"]=digest
            if case=="observer_identity":rows[2]["sample_euid"]=0
            if case=="observer_groups":rows[2]["group1"]=0
            if case=="observer_predicate":rows[2]["predicate"]=0
            if case=="observer_exec":rows[1]["kernel_exec"]=0
            if case=="observer_candidate":rows[2]["candidate_sha"]="b"*40
            raw=b"".join((json.dumps(row,sort_keys=True)+"\n").encode("ascii") for row in rows)
            if case=="ledger_incomplete":raw=b"\n".join(raw.splitlines()[:4])+b"\n"
            if case=="ledger_no_final_lf":raw=raw[:-1]
            if case=="ledger_bad_json":raw=b"{bad json}\n"+b"\n".join(raw.splitlines()[1:])+b"\n"
            if case=="ledger_duplicate_key":
                raw=raw.replace(b'{"arch": "arm64",',b'{"arch": "arm64", "arch": "arm64",',1)
            if case=="ledger_read_overflow":raw=b"x"*16385
            ledger=base/"software-ledger.bytes";ledger.write_bytes(raw)
            protected=Path("/private/var/icode-m0a1-groups.SoftwareOnly")
            rootfile=protected/"groups.jsonl"
            manifest={"version":1,"root_directory":str(protected),
                      "ledger_sha256":hashlib.sha256(raw).hexdigest()}
            if case=="manifest_version":manifest["version"]=2
            if case=="manifest_version_bool":manifest["version"]=True
            if case=="manifest_path":manifest["root_directory"]="/private/var/icode-m0a1-groups.Bad/../escape"
            if case=="manifest_path_type":manifest["root_directory"]=123
            if case=="manifest_digest_syntax":manifest["ledger_sha256"]="bad"
            if case=="manifest_digest_type":manifest["ledger_sha256"]=123
            if case=="manifest_digest_mismatch":manifest["ledger_sha256"]="b"*64
            if case=="manifest_extra_key":manifest["unexpected"]=1
            stdout=(json.dumps(manifest,sort_keys=True)+"\n").encode("ascii")
            stderr=b"";returncode=0
            if case=="manifest_duplicate_key":stdout=stdout.replace(b'{"ledger_sha256":',b'{"version":1,"ledger_sha256":',1)
            if case=="manifest_bad_json":stdout=b"{"
            if case=="manifest_bad_utf8":stdout=b"\xff"
            if case=="manifest_not_object":stdout=b"[]\n"
            if case=="native_nonzero":returncode=2
            if case=="native_stderr":stderr=b"software failure\n"
            if case=="native_stdout_overflow":stdout=b"x"*513
            if case=="native_stderr_overflow":stderr=b"x"*257
            if case=="binary_missing":binary.unlink()
            if case=="binary_nonexec":binary.chmod(0o644)
            if case=="binary_empty":binary.write_bytes(b"")
            if case=="binary_symlink":
                other=base/"other";other.write_bytes(image);other.chmod(0o755)
                binary.unlink();binary.symlink_to(other)
            real_lstat=Path.lstat;real_stat=Path.stat;real_resolve=Path.resolve
            real_open=module.os.open;real_fstat=module.os.fstat
            real_read=module.os.read;real_close=module.os.close
            real_popen=module.subprocess.Popen
            active_fds=set();counts={"native":0,"binding":0,"fstat":0,"opened":0,"closed":0}
            def path_lstat(path,*args,**kwargs):
                if path==protected:
                    mode=stat.S_IFDIR|0o755;owner=0
                    if case=="directory_type":mode=stat.S_IFLNK|0o755
                    if case=="directory_owner":owner=1000
                    if case=="directory_mode":mode=stat.S_IFDIR|0o777
                    return SimpleNamespace(st_mode=mode,st_uid=owner)
                return real_lstat(path,*args,**kwargs)
            def path_stat(path,*args,**kwargs):
                actual=real_stat(path,*args,**kwargs)
                if path==binary and case=="binary_oversize":
                    return SimpleNamespace(st_mode=actual.st_mode,st_size=16*1024*1024+1)
                return actual
            def path_resolve(path,*args,**kwargs):
                if path==binary and case=="binary_escape":return base/"escaped-native"
                return real_resolve(path,*args,**kwargs)
            def open_boundary(path,flags,*args,**kwargs):
                if Path(path)==rootfile:
                    self.assertEqual(flags,module.os.O_RDONLY|module.os.O_NOFOLLOW|module.os.O_CLOEXEC)
                    if case=="ledger_open_error":raise OSError(errno.EACCES,"software permission refusal")
                    fd=real_open(ledger,flags,*args,**kwargs)
                    active_fds.add(fd);counts["opened"]+=1;return fd
                return real_open(path,flags,*args,**kwargs)
            def stat_boundary(fd):
                actual=real_fstat(fd)
                if fd not in active_fds:return actual
                counts["fstat"]+=1
                fields={key:getattr(actual,key) for key in
                    ("st_dev","st_ino","st_size","st_mtime_ns","st_mode","st_uid","st_nlink")}
                fields.update(st_mode=stat.S_IFREG|0o444,st_uid=0,st_nlink=1)
                if case=="ledger_type":fields["st_mode"]=stat.S_IFIFO|0o444
                if case=="ledger_owner":fields["st_uid"]=1000
                if case=="ledger_mode":fields["st_mode"]=stat.S_IFREG|0o600
                if case=="ledger_nlink":fields["st_nlink"]=2
                if case=="ledger_empty":fields["st_size"]=0
                if case=="ledger_oversize":fields["st_size"]=16385
                if case=="ledger_read_overflow":fields["st_size"]=16384
                if counts["fstat"]==2 and case.startswith("ledger_changed_"):
                    key={"ledger_changed_device":"st_dev","ledger_changed_inode":"st_ino",
                         "ledger_changed_size":"st_size","ledger_changed_mtime":"st_mtime_ns"}[case]
                    fields[key]+=1
                return SimpleNamespace(**fields)
            def read_boundary(fd,count):
                if fd in active_fds and case=="ledger_read_error":raise OSError(errno.EIO,"software read failure")
                return real_read(fd,count)
            def close_boundary(fd):
                result=real_close(fd)
                if fd in active_fds:active_fds.remove(fd);counts["closed"]+=1
                return result
            def tool_boundary(command,**kwargs):
                tool_stdout="";tool_stderr=""
                if "--version" in command:
                    counts["binding"]+=1;tool_stdout="software compiler version\n"
                elif "--show-sdk-path" in command:tool_stdout=str(sdk)+"\n"
                elif "--show-sdk-version" in command:tool_stdout="software SDK version\n"
                elif "-###" in command:tool_stderr='clang\n"-isysroot" '+json.dumps(str(sdk))+"\n"
                elif "-E" in command:tool_stdout="int getgroups(int, gid_t []);\n"
                elif command[0]=="/usr/bin/nm":
                    tool_stdout=" U _getgroups"+("$DARWIN_EXTSN" if case=="binding_failure" else "")+"\n"
                else:raise AssertionError("unexpected software tool boundary: "+repr(command))
                program="import sys;sys.stdout.write("+repr(tool_stdout)+");sys.stderr.write("+repr(tool_stderr)+")"
                return real_popen([sys.executable,"-c",program],**kwargs)
            def native_boundary(argv,**kwargs):
                counts["native"]+=1
                self.assertEqual(argv,["/usr/bin/sudo","-n","--","/usr/bin/env","-i",
                    "PATH=/usr/bin:/bin",str(binary),SHA,digest])
                self.assertEqual(kwargs,{"cwd":"/","capture_output":True,"timeout":50,"check":False})
                if case=="native_timeout":
                    raise subprocess.TimeoutExpired(argv,50,output=b"software partial",stderr=b"software timeout")
                return subprocess.CompletedProcess(argv,returncode,stdout,stderr)
            with ExitStack() as stack:
                stack.enter_context(patch.object(Path,"lstat",path_lstat))
                stack.enter_context(patch.object(Path,"stat",path_stat))
                stack.enter_context(patch.object(Path,"resolve",path_resolve))
                stack.enter_context(patch.object(module.os,"open",open_boundary))
                stack.enter_context(patch.object(module.os,"fstat",stat_boundary))
                stack.enter_context(patch.object(module.os,"read",read_boundary))
                stack.enter_context(patch.object(module.os,"close",close_boundary))
                stack.enter_context(patch.object(module.subprocess,"Popen",tool_boundary))
                stack.enter_context(patch.object(module.subprocess,"run",native_boundary))
                if case=="success":
                    record=module.run_w1_groups(ROOT,build,output,SHA,"arm64")
                    binding_digest=hashlib.sha256((output/"w1-binding/process-groups-binding.json").read_bytes()).hexdigest()
                    self.assertEqual(record,{"result":"native_groups_verified","candidate_sha":SHA,
                        "arch":"arm64","binary_sha256":digest,"ledger_sha256":hashlib.sha256(raw).hexdigest(),
                        "binding_sha256":binding_digest,"native_exit":0,
                        "cleanup_scope":"owned_root_only_identities_retained"})
                    self.assertEqual(json.loads((output/"w1-result.json").read_text()),record)
                    self.assertEqual((output/"w1-native.audit.jsonl").read_bytes(),raw)
                    self.assertEqual((output/"icode_m0a1_groups_native").read_bytes(),image)
                    self.assertEqual((counts["binding"],counts["native"],counts["opened"],counts["closed"]),(1,1,1,1))
                else:
                    with self.assertRaises((RuntimeError,ValueError,OSError)):
                        module.run_w1_groups(ROOT,build,output,SHA,"arm64")
                    self.assertFalse((output/"w1-result.json").exists(),"failed runner published success")
                self.assertFalse(active_fds,"root ledger descriptor leaked")
                self.assertEqual(counts["opened"],counts["closed"])
                if counts["native"]:
                    self.assertLessEqual((output/"w1-native.stdout.json").stat().st_size,512)
                    self.assertLessEqual((output/"w1-native.stderr.log").stat().st_size,256)
                    execution=json.loads((output/"w1-execution.json").read_text())
                    self.assertEqual(execution["candidate_sha"],SHA)
                    self.assertEqual(execution["native_exit"],"timeout" if case=="native_timeout" else returncode)
                    if case=="native_timeout":
                        self.assertEqual(execution["cleanup"],"unknown")
                        self.assertFalse(execution["raw_complete"])
                    else:
                        self.assertEqual(execution["stdout_sha256"],hashlib.sha256(stdout).hexdigest())
                        self.assertEqual(execution["stderr_sha256"],hashlib.sha256(stderr).hexdigest())
                        self.assertEqual(execution["raw_complete"],len(stdout)<=512 and len(stderr)<=256)

    def test_actual_runner_success_and_fail_closed_os_boundaries(self):
        cases=("success","binary_missing","binary_symlink","binary_nonexec","binary_empty",
            "binary_oversize","binary_escape","binding_failure","native_timeout","native_nonzero",
            "native_stderr","native_stdout_overflow","native_stderr_overflow","manifest_duplicate_key",
            "manifest_bad_json","manifest_bad_utf8","manifest_not_object","manifest_version",
            "manifest_version_bool","manifest_path","manifest_path_type","manifest_digest_syntax",
            "manifest_digest_type","manifest_digest_mismatch","manifest_extra_key","directory_type",
            "directory_owner","directory_mode","ledger_open_error","ledger_type","ledger_owner",
            "ledger_mode","ledger_nlink","ledger_empty","ledger_oversize","ledger_read_error",
            "ledger_read_overflow","ledger_changed_device","ledger_changed_inode","ledger_changed_size",
            "ledger_changed_mtime","ledger_incomplete","ledger_no_final_lf","ledger_bad_json",
            "ledger_duplicate_key","observer_identity","observer_groups","observer_predicate",
            "observer_exec","observer_candidate")
        for case in cases:
            with self.subTest(case=case):self.exercise_runner(case)
```

- [ ] 只跑 `python3 -m unittest tests.test_macos_process_groups_native.TestW1ControllerAcceptance.test_existing_acceptance_must_reject_absent_w1_evidence -v`。旧真实接受尾段在有合法原配额RED结果、没有W1证据时实际返回0，期望抛出 RuntimeError 的 assertion FAIL；这是新增controller先决门的真实语义RED。AST提取完整原接受逻辑，不复制if条件；只替换JSON写入边界为RAM，无假native wire、无root运行信用。编译/import/AST锚点失败不是RED，出现则 STOP NEEDS_CONTEXT。
- [ ] 跑 `TestW1Observer` 与 `TestW1MechanicalLeaseExtraction`，预期GREEN；这些是新增 TEST 的自校验/原语保护，不称生产bug修复RED。冻结 TEST摘要、真实命令/退出/原日志；不同 SOURCE 作者才进入Task2。

### Task 2: 有限身份原语机械共享

**Dependencies:** Task 1
**Parallelizable:** No (先冻结inverse保护)

- [ ] 新增 `native/mac/tests/icode_m0a1_identity_lease.inc`；文件逐字等于当前driver从 `static void directory_accounts(void)` 起到 `static void send_gate(` 前的全部字节（包含末尾换行），下列为完整内容，不添加guard/宏/参数：

```c
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
```

- [ ] 原driver上述整段仅替换为以下一行，其他字节不动；所有 include前置已在原位：`errno/fcntl/grp/libproc/pwd/signal/stdio/string/sysstat/unistd` 类型/函数，`UID_FIRST=60000/UID_COUNT=1024/MAX_PIDS=8192`、`unavailable[UID_COUNT]`、固定 `lease_root="/private/var/icode-m0a1-leases"`、`owner_text="ICODE-M0A1-v1\n"`、`die/secure_chain/all_read/all_write` 先定义。新fixture独立进程内同名静态状态，不共享内存；唯一共享状态是原同一个持久lease目录，防原7case与新三身份重复。

```c
#include "icode_m0a1_identity_lease.inc"
```

- [ ] 运行 `python3 -m unittest tests.test_macos_process_groups_native.TestW1MechanicalLeaseExtraction -v`，inverse SHA必须精确等于当前driver；这是机械共享GREEN，不计新行为RED。任何路径/owner/返回/errno变化均STOP，不借重构变更安全语义。

### Task 3: 固定独立 native TEST 完整资产

**Dependencies:** Task 2
**Parallelizable:** No (使用冻结共享lease及生产predicate)

- [ ] 新增 `native/mac/tests/icode_m0a1_process_groups_native.c`，完整资产如下。只接受 root observer两个hex参数、或已降权的固定 `after`入口；不能传任意目标/命令/路径。父子数据fd与ack是本TEST内部观测同步，不是原formal的release/payload。

```c
#define _DARWIN_C_SOURCE 1
#include "icode_m0a1_process_groups.h"
#include <CommonCrypto/CommonDigest.h>
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <inttypes.h>
#include <libproc.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <mach-o/loader.h>
#include <pwd.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/acl.h>
#include <sys/event.h>
#include <sys/param.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/sysctl.h>
#include <sys/user.h>
#include <sys/utsname.h>
#include <sys/wait.h>
#include <unistd.h>
enum { UID_FIRST=60000, UID_COUNT=1024, MAX_PIDS=8192, MAX_IMAGE=16*1024*1024 };
static const char lease_root[]="/private/var/icode-m0a1-leases";
static const char owner_text[]="ICODE-M0A1-v1\n";
static unsigned char unavailable[UID_COUNT];
static volatile sig_atomic_t owned_child;
static char image[PATH_MAX],directory[PATH_MAX],binary_hash[65];
static const char *candidate,*architecture;
static unsigned rows_written;
static void expire(int sig) {
    (void)sig;
    if(owned_child>0) (void)kill((pid_t)owned_child,SIGKILL);
    _exit(124);
}
static void die(const char *stage) {
    int e=errno ? errno : EPROTO;
    const char prefix[]="/private/var/icode-m0a1-groups.";
    fprintf(stderr,"W1_GROUPS stage=%s errno=%d cleanup=unknown identities=retained directory=%s\n",
        stage,e,strncmp(directory,prefix,sizeof(prefix)-1)==0 ? directory : "unknown");
    if(owned_child>0) (void)kill((pid_t)owned_child,SIGKILL);
    exit(2);
}
static int all_write(int fd,const void *buf,size_t n) {
    const unsigned char *p=buf;
    while(n) {
        ssize_t r=write(fd,p,n);
        if(r<0 && errno==EINTR) continue;
        if(r<=0) return errno ? errno : EIO;
        p+=r;n-=(size_t)r;
    }
    return 0;
}
static int all_read(int fd,void *buf,size_t n) {
    unsigned char *p=buf;
    while(n) {
        ssize_t r=read(fd,p,n);
        if(r<0 && errno==EINTR) continue;
        if(r<=0) return r==0 ? EPIPE : errno;
        p+=r;n-=(size_t)r;
    }
    return 0;
}
static int hex_string(const char *s,size_t n) {
    if(strlen(s)!=n) return 0;
    for(size_t i=0;i<n;i++)
        if(!((s[i]>='0' && s[i]<='9') || (s[i]>='a' && s[i]<='f'))) return 0;
    return 1;
}
static uid_t identity_number(const char *s) {
    char *end=NULL;errno=0;unsigned long value=strtoul(s,&end,10);
    if(errno || end==s || *end || value<UID_FIRST || value>=UID_FIRST+UID_COUNT) die("worker-identity");
    return (uid_t)value;
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
            acl_entry_t entry;errno=0;
            int r=acl_get_entry(acl,i==0 ? ACL_FIRST_ENTRY : ACL_NEXT_ENTRY,&entry);
            if(r<0 && errno==EINVAL) break;
            if(r!=0 || i==ACL_MAX_ENTRIES) { e=EPROTO;break; }
            acl_tag_t tag;acl_permset_mask_t permissions=0;
            if(acl_get_tag_type(entry,&tag)<0 || acl_get_permset_mask_np(entry,&permissions)<0) { e=errno;break; }
            if(tag!=ACL_EXTENDED_ALLOW && tag!=ACL_EXTENDED_DENY) { e=EPROTO;break; }
            if(tag==ACL_EXTENDED_ALLOW && (permissions&~read_mask)) { e=EPERM;break; }
        }
    }
    if(acl && acl!=(acl_t)_FILESEC_REMOVE_ACL && acl_free(acl)<0 && !e) e=errno;
    filesec_free(sec);return e;
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
        char saved=*p;*p=0;struct stat st;
        e=getuid()==0 ? acl_safe(copy,&st) : (lstat(copy,&st)<0 ? errno : 0);
        if(e) return e;
        if(st.st_uid!=0 || (st.st_mode&022) || S_ISLNK(st.st_mode)) return EPERM;
        *p=saved;if(!saved) break;
    }
    return 0;
}
static int hash_fd(int fd,char out[65],size_t bound) {
    CC_SHA256_CTX ctx;unsigned char buf[65536],digest[CC_SHA256_DIGEST_LENGTH];
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
    out[64]=0;return 0;
}
static void self_path(void) {
    char buf[PATH_MAX];uint32_t n=sizeof(buf);
    if(_NSGetExecutablePath(buf,&n)!=0 || !realpath(buf,image)) die("self-path");
    strcpy(directory,image);char *slash=strrchr(directory,'/');
    if(!slash) die("self-parent");
    *slash=0;
}
static int protected_image(const char *digest) {
    const char prefix[]="/private/var/icode-m0a1-groups.";
    if(strncmp(directory,prefix,sizeof(prefix)-1)) return EPERM;
    int e=secure_chain(image);
    if(e) return e;
    int fd=open(image,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);struct stat st;char actual[65];
    if(fd<0) return errno;
    e=fstat(fd,&st)<0 ? errno : (!S_ISREG(st.st_mode) || st.st_nlink!=1 || (st.st_mode&0777)!=0555 ? EPERM : 0);
    if(!e) e=hash_fd(fd,actual,MAX_IMAGE);
    if(close(fd)<0 && !e) e=errno;
    if(!e && strcmp(actual,digest)) e=EPERM;
    return e;
}
static void prepare_image(const char *digest) {
    int in=open(image,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);struct stat st;char actual[65];
    if(in<0 || fstat(in,&st)<0 || !S_ISREG(st.st_mode) || st.st_size<=0 || st.st_size>MAX_IMAGE) die("source-image");
    struct mach_header_64 mh;
    if(all_read(in,&mh,sizeof(mh)) || mh.magic!=MH_MAGIC_64) die("native-Mach-O");
#if defined(__arm64__)
    if(mh.cputype!=CPU_TYPE_ARM64) die("native-arm64");
#elif defined(__x86_64__)
    if(mh.cputype!=CPU_TYPE_X86_64) die("native-x86_64");
#else
#error Unsupported_native_architecture
#endif
    if(hash_fd(in,actual,MAX_IMAGE) || strcmp(actual,digest)) die("source-digest");
    if(secure_chain("/private/var")) die("protected-parent");
    strcpy(directory,"/private/var/icode-m0a1-groups.XXXXXX");
    if(!mkdtemp(directory) || chmod(directory,0755)<0 || secure_chain(directory)) die("protected-directory");
    char target[PATH_MAX];
    if(snprintf(target,sizeof(target),"%s/probe",directory)>=(int)sizeof(target)) die("protected-path");
    int out=open(target,O_RDWR|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    if(out<0 || lseek(in,0,SEEK_SET)<0) die("copy-open");
    unsigned char buf[65536];size_t total=0;
    for(;;) {
        ssize_t n=read(in,buf,sizeof(buf));
        if(n<0 && errno==EINTR) continue;
        if(n<0) die("copy-read");
        if(!n) break;
        if((size_t)n>MAX_IMAGE-total || all_write(out,buf,(size_t)n)) die("copy-write");
        total+=(size_t)n;
    }
    if(hash_fd(out,actual,MAX_IMAGE) || strcmp(actual,digest) || fchmod(out,0555)<0 || fsync(out)<0 ||
       close(out)<0 || close(in)<0) die("copy-seal");
    strcpy(image,target);strcpy(binary_hash,digest);
}
#include "icode_m0a1_identity_lease.inc"
/* Include dependencies are fixed above; same finite lease namespace as original TEST. */
static int supplementary_free(gid_t gid) {
    pid_t pids[MAX_PIDS];int n=proc_listallpids(pids,sizeof(pids));
    if(n<=0 || n>=MAX_PIDS) return -1;
    for(int i=0;i<n;i++) {
        if(pids[i]<=0) continue;
        struct kinfo_proc info;memset(&info,0,sizeof(info));size_t size=sizeof(info);
        int mib[]={CTL_KERN,KERN_PROC,KERN_PROC_PID,pids[i]};
        if(sysctl(mib,4,&info,&size,NULL,0)<0 || size!=sizeof(info)) {
            errno=0;
            if(kill(pids[i],0)<0 && errno==ESRCH) continue;
            return -1;
        }
        int count=info.kp_eproc.e_ucred.cr_ngroups;
        if(count<0 || count>NGROUPS) return -1;
        for(int j=0;j<count;j++) if(info.kp_eproc.e_ucred.cr_groups[j]==gid) return 0;
    }
    return 1;
}
static uid_t reserve_unused_id(int leases) {
    for(unsigned attempt=0;attempt<UID_COUNT;attempt++) {
        uid_t uid=reserve_uid(leases,candidate);
        int empty=supplementary_free((gid_t)uid);
        if(empty<0) die("supplementary-snapshot");
        int active=process_count(uid);
        if(active<0) die("identity-process-snapshot");
        if(empty==1 && active==0) return uid;
        /* A collision burns its permanent lease; no identity is retried or cleaned. */
    }
    errno=ENOSPC;die("supplementary-exhausted");return 0;
}
struct observation {
    uint32_t uid,euid,gid,egid,group0,group1;
    int32_t pid,count,count_errno,capacity,read,read_errno,predicate_attempted,predicate,image_stage;
};
struct end_record { pid_t pid;uid_t uid;int status,remaining; };
static void observe(uid_t uid,uid_t extra,int negative,int stage) {
    struct observation r;memset(&r,0,sizeof(r));
    r.uid=getuid();r.euid=geteuid();r.gid=getgid();r.egid=getegid();r.pid=getpid();
    r.group0=r.group1=UINT32_MAX;r.count=r.read=r.predicate=-1;
    r.count_errno=r.read_errno=-1;r.capacity=negative ? 2 : 1;r.image_stage=stage;
    errno=0;r.count=m0_process_getgroups(0,NULL);r.count_errno=r.count<0 ? errno : 0;
    gid_t groups[2]={UINT32_MAX,UINT32_MAX};
    if(r.count>=0 && r.count<=r.capacity) {
        errno=0;r.read=m0_process_getgroups(r.capacity,groups);r.read_errno=r.read<0 ? errno : 0;
        if(r.read>=1) r.group0=groups[0];
        if(r.read==2) r.group1=groups[1];
    }
    int identity=r.uid==uid && r.euid==uid && r.gid==uid && r.egid==uid;
    int vector=negative ? r.count==2 && r.read==2 &&
        ((r.group0==uid && r.group1==extra) || (r.group0==extra && r.group1==uid)) :
        r.count==1 && r.read==1 && r.group0==uid;
    /* Independent preconditions precede calling the one production predicate. */
    if(identity && vector) { r.predicate_attempted=1;r.predicate=m0_process_credentials(uid); }
    if(all_write(3,&r,sizeof(r))) _exit(70);
}
static void acknowledgement(char expected) {
    char value=0;
    if(all_read(4,&value,1) || value!=expected) _exit(71);
}
static void isolate_child(void) {
    int limit=getdtablesize();
    if(limit<5 || limit>65536) _exit(72);
    for(int f=5;f<limit;f++) if(close(f)<0 && errno!=EBADF) _exit(73);
    int null=open("/dev/null",O_RDWR);
    if(null<0) _exit(74);
    for(int f=0;f<3;f++) if(dup2(null,f)<0) _exit(75);
    if(null>4) close(null);
    for(int s=1;s<NSIG;s++)
        if(s!=SIGKILL && s!=SIGSTOP && signal(s,SIG_DFL)==SIG_ERR) _exit(76);
    sigset_t empty;sigemptyset(&empty);
    if(sigprocmask(SIG_SETMASK,&empty,NULL)<0 || signal(SIGALRM,expire)==SIG_ERR ||
       signal(SIGPIPE,SIG_IGN)==SIG_ERR) _exit(77);
    alarm(10);owned_child=0;
    struct rlimit cpu={2,2},files={65536,65536},actual;
    if(setrlimit(RLIMIT_CPU,&cpu)<0 || setrlimit(RLIMIT_FSIZE,&files)<0 ||
       getrlimit(RLIMIT_CPU,&actual)<0 || actual.rlim_cur!=2 || actual.rlim_max!=2 ||
       getrlimit(RLIMIT_FSIZE,&actual)<0 || actual.rlim_cur!=65536 || actual.rlim_max!=65536) _exit(78);
}
static void child(uid_t uid,uid_t extra,int negative) {
    acknowledgement('A');
    gid_t groups[2]={(gid_t)uid,(gid_t)extra};
    if(protected_image(binary_hash) || setgroups(negative ? 2 : 1,groups)<0 ||
       setgid((gid_t)uid)<0 || setuid(uid)<0) _exit(79);
    observe(uid,extra,negative,0);
    if(negative) { acknowledgement('D');_exit(0); }
    acknowledgement('C');
    char id[16],other[16];snprintf(id,sizeof(id),"%u",uid);snprintf(other,sizeof(other),"%u",extra);
    char *args[]={image,"after",id,other,binary_hash,NULL};
    char *env[]={"PATH=/usr/bin:/bin",NULL};
    execve(image,args,env);_exit(80);
}
static void ledger_row(int ledger,const char *row,int n) {
    if(n<=0 || n>=2048 || ++rows_written>5 || all_write(ledger,row,(size_t)n) || fsync(ledger)<0) die("ledger-write");
}
static int wait_owned(pid_t pid,int *status) {
    sigset_t mask,old;sigemptyset(&mask);sigaddset(&mask,SIGALRM);
    for(unsigned attempt=0;attempt<100;attempt++) {
        if(sigprocmask(SIG_BLOCK,&mask,&old)<0) return -1;
        pid_t r=waitpid(pid,status,WNOHANG);int saved=errno;
        if(r==pid) owned_child=0;
        if(sigprocmask(SIG_SETMASK,&old,NULL)<0) return -1;
        if(r==pid) return 0;
        if(r<0 && saved!=EINTR) { errno=saved;return -1; }
        (void)usleep(10000);
    }
    errno=ETIMEDOUT;return -1;
}
static struct end_record run_case(int ledger,uid_t uid,uid_t extra,int negative) {
    if(process_count(uid)!=0 || supplementary_free(uid)!=1 ||
       process_count(extra)!=0 || supplementary_free(extra)!=1) die("pre-fork-collision");
    int data[2],ack[2];
    if(pipe(data)<0 || pipe(ack)<0) die("pipes");
    pid_t pid=fork();
    if(pid<0) die("fork");
    if(pid==0) {
        if(dup2(data[1],3)<0 || dup2(ack[0],4)<0) _exit(81);
        isolate_child();child(uid,extra,negative);_exit(82);
    }
    owned_child=pid;close(data[1]);close(ack[0]);
    struct proc_bsdinfo initial;
    if(proc_pidinfo(pid,PROC_PIDTBSDINFO,0,&initial,sizeof(initial))!=(int)sizeof(initial) ||
       initial.pbi_pid!=(uint32_t)pid) die("initial-PID-start");
    int kq=-1;
    if(!negative) {
        struct kevent change,receipt;struct timespec zero={0,0};
        kq=kqueue();
        EV_SET(&change,pid,EVFILT_PROC,EV_ADD|EV_ENABLE|EV_CLEAR|EV_RECEIPT,NOTE_EXEC,0,NULL);
        if(kq<0 || kevent(kq,&change,1,&receipt,1,&zero)!=1 ||
           !(receipt.flags&EV_ERROR) || receipt.data!=0) die("exec-observer-registration");
    }
    if(all_write(ack[1],"A",1)) die("start-ack");
    for(int i=0;i<(negative ? 1 : 2);i++) {
        struct observation r;struct proc_bsdinfo current;
        if(all_read(data[0],&r,sizeof(r))) die("observation-read");
        if(proc_pidinfo(pid,PROC_PIDTBSDINFO,0,&current,sizeof(current))!=(int)sizeof(current)) die("live-PID-start");
        int identity=current.pbi_pid==(uint32_t)pid && current.pbi_ruid==uid && current.pbi_uid==uid &&
            current.pbi_svuid==uid && current.pbi_rgid==uid && current.pbi_gid==uid && current.pbi_svgid==uid &&
            current.pbi_start_tvsec==initial.pbi_start_tvsec && current.pbi_start_tvusec==initial.pbi_start_tvusec;
        int count=process_count(uid);
        int exec_seen=0;
        if(!negative && i==1) {
            struct kevent event;struct timespec bounded={1,0};
            int received=kevent(kq,NULL,0,&event,1,&bounded);
            exec_seen=received==1 && !(event.flags&EV_ERROR) && event.ident==(uintptr_t)pid &&
                (event.fflags&NOTE_EXEC)!=0;
        }
        char row[2048];
        int n=snprintf(row,sizeof(row),
            "{\"candidate_sha\":\"%s\",\"binary_sha256\":\"%s\",\"arch\":\"%s\","
            "\"observer_uid\":%u,\"observer_pid\":%d,\"slot\":\"%s\",\"uid\":%u,\"extra\":%u,"
            "\"pid\":%d,\"start_sec\":%" PRIu64 ",\"start_usec\":%" PRIu64 ",\"root_identity\":%d,"
            "\"sample_pid\":%d,\"live_count\":%d,\"sample_uid\":%u,\"sample_euid\":%u,"
            "\"sample_gid\":%u,\"sample_egid\":%u,\"count\":%d,\"count_errno\":%d,\"capacity\":%d,"
            "\"read\":%d,\"read_errno\":%d,\"group0\":%u,\"group1\":%u,"
            "\"predicate_attempted\":%d,\"predicate\":%d,\"image_stage\":%d,\"kernel_exec\":%d}\n",
            candidate,binary_hash,architecture,getuid(),(int)getpid(),negative ? "extra" : i==0 ? "single_before" : "single_after",
            uid,extra,(int)pid,initial.pbi_start_tvsec,initial.pbi_start_tvusec,identity,r.pid,count,
            r.uid,r.euid,r.gid,r.egid,r.count,r.count_errno,r.capacity,r.read,r.read_errno,r.group0,r.group1,
            r.predicate_attempted,r.predicate,r.image_stage,exec_seen);
        ledger_row(ledger,row,n);
        if(!identity || count!=1) die("independent-root-identity");
        if(all_write(ack[1],!negative && i==0 ? "C" : "D",1)) die("observation-ack");
    }
    close(ack[1]);char extra_byte;
    if(read(data[0],&extra_byte,1)!=0 || close(data[0])<0) die("observation-tail");
    int status=0;
    if(wait_owned(pid,&status)<0) die("owned-wait");
    if(kq>=0 && close(kq)<0) die("exec-observer-close");
    struct end_record end={pid,uid,status,process_count(uid)};
    if(!WIFEXITED(status) || WEXITSTATUS(status) || end.remaining!=0) die("owned-exit-unknown");
    return end;
}
int main(int argc,char **argv) {
    self_path();
    if(argc==5 && !strcmp(argv[1],"after")) {
        uid_t uid=identity_number(argv[2]),extra=identity_number(argv[3]);
        if(!hex_string(argv[4],64) || uid==extra || getuid()!=uid || geteuid()!=uid ||
           protected_image(argv[4])) _exit(83);
        if(signal(SIGALRM,expire)==SIG_ERR || signal(SIGPIPE,SIG_IGN)==SIG_ERR) _exit(84);
        alarm(10);observe(uid,extra,0,1);acknowledgement('D');_exit(0);
    }
    if(argc!=3 || getuid()!=0 || geteuid()!=0 || !hex_string(argv[1],40) || !hex_string(argv[2],64)) die("root-fixed-arguments");
    candidate=argv[1];umask(077);
    for(int f=0;f<3;f++) if(fcntl(f,F_GETFD)<0) die("standard-descriptor-layout");
    sigset_t empty;sigemptyset(&empty);
    if(signal(SIGALRM,expire)==SIG_ERR || signal(SIGPIPE,SIG_IGN)==SIG_ERR ||
       sigprocmask(SIG_SETMASK,&empty,NULL)<0) die("signals");
    alarm(40);struct rlimit cpu={10,10},actual;
    if(setrlimit(RLIMIT_CPU,&cpu)<0 || getrlimit(RLIMIT_CPU,&actual)<0 ||
       actual.rlim_cur!=10 || actual.rlim_max!=10) die("root-cpu");
    struct utsname u;
    if(uname(&u)<0 || (strcmp(u.machine,"arm64") && strcmp(u.machine,"x86_64"))) die("architecture");
    architecture=u.machine;int translated=-1;size_t size=sizeof(translated);errno=0;
    int query=sysctlbyname("sysctl.proc_translated",&translated,&size,NULL,0);
    if(!((query==0 && size==sizeof(translated) && translated==0) || (query<0 && errno==ENOENT))) die("translation");
    prepare_image(argv[2]);directory_accounts();int leases=lease_directory();
    uid_t positive=reserve_unused_id(leases),negative=reserve_unused_id(leases),extra=reserve_unused_id(leases);
    if(positive==negative || positive==extra || negative==extra) die("distinct-leases");
    char path[PATH_MAX];
    if(snprintf(path,sizeof(path),"%s/groups.jsonl",directory)>=(int)sizeof(path)) die("ledger-path");
    int ledger=open(path,O_RDWR|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    if(ledger<0) die("ledger-open");
    struct end_record ends[2];
    ends[0]=run_case(ledger,positive,extra,0);ends[1]=run_case(ledger,negative,extra,1);
    for(unsigned i=0;i<2;i++) {
        struct end_record *e=&ends[i];char row[2048];
        int n=snprintf(row,sizeof(row),
            "{\"candidate_sha\":\"%s\",\"binary_sha256\":\"%s\",\"arch\":\"%s\","
            "\"observer_uid\":%u,\"observer_pid\":%d,\"slot\":\"end\",\"pid\":%d,\"uid\":%u,"
            "\"exit_code\":%d,\"term_signal\":%d,\"remaining\":%d,\"retained\":true,\"cleanup_scope\":\"owned_root_only\"}\n",
            candidate,binary_hash,architecture,getuid(),(int)getpid(),(int)e->pid,e->uid,
            WIFEXITED(e->status) ? WEXITSTATUS(e->status) : -1,
            WIFSIGNALED(e->status) ? WTERMSIG(e->status) : 0,e->remaining);
        ledger_row(ledger,row,n);
    }
    if(process_count(extra)!=0 || supplementary_free(extra)!=1) die("retained-extra-unknown");
    char digest[65];
    if(rows_written!=5 || hash_fd(ledger,digest,16384) || fchmod(ledger,0444)<0 || fsync(ledger)<0 ||
       close(ledger)<0 || close(leases)<0) die("ledger-seal");
    printf("{\"version\":1,\"root_directory\":\"%s\",\"ledger_sha256\":\"%s\"}\n",directory,digest);
    if(fflush(stdout)==EOF) die("manifest-write");
    alarm(0);return 0;
}
```

- [ ] 新fixture资产落地后先执行独立软件负控：`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_macos_process_groups_native.TestW1LeaseSnapshotSoftware -v`。它从实际新native TEST文件提取唯一完整 `reserve_unused_id`，编译/链接/运行该函数，仅在 `reserve_uid/supplementary_free/process_count/die` OS及错误出口边界提供替身；不复制该函数的循环/判断，不调用任何身份修改/系统租约操作。七个实际进程场景覆盖正常、首次process未知、已知process碰撞、已知supplementary碰撞、supplementary未知、有限耗尽及已知碰撞后process未知。未知场景要求立刻退出91且lease消耗精确止于1或2；不能继续到随后正常快照。碰撞场景要求使用下一已消耗身份，永不再次返回此前身份；消耗bitset仅模型既有永久lease边界，不授本机实际磁盘持久性或原生碰撞信用。编译/链接/提取缺失不是RED；该项是fixture软件自校验，不制造已发布生产bug信用。原生真实lease/完整sysctl/proc证据仍由两CI格提供。

- [ ] 在现有 CMake 的 `m0_target(icode_m0a1_baseline tests/icode_m0a1_baseline.c)` 后插入完整独立target；不用 `m0_target`，避免链接原driver main；原 SOURCE 存在性门逐字保留：

```cmake
add_executable(icode_m0a1_groups_native tests/icode_m0a1_process_groups_native.c icode_m0a1_process_groups.c)
target_include_directories(icode_m0a1_groups_native PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
set_target_properties(icode_m0a1_groups_native PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED YES C_EXTENSIONS NO)
target_compile_options(icode_m0a1_groups_native PRIVATE -Wall -Wextra -Werror -Wno-deprecated-declarations)
```

fixture 最多两个 fork/正控一次exec/三个观测记录+两个退出记录。只有降权子进程迁入任务UID，observer始终root；extra只作为GID保留，不再创建该UID的进程。三个身份与原七case使用同一不可重用lease；新增supplementary扫描前后撞上则烧掉候选lease，未知即停；不会回收/删lease/创建目录账户。扫描只证明所见快照，不宣称对其它root并发行为提供原子全局隔离；最后碰撞或观察不足拒绝并保留。

stdout仅一个有界manifest（固定root前缀+短随机后缀+64hex，<512字节）；stderr最多固定stage失败一行（<256字节），子进程stderr去`/dev/null`，父失败报未知；每行ledger<2048字节、最多5行、整体<16384。observer alarm40/CPU10，child alarm10/CPU2/FSIZE65536并读回；超时kill仅自有未回收child，退出未确认不授清理完成；lease/目录永久保留。真实syscall失败只有错误出口，不伪造成功记录；count/read未尝试用-1、组值用原始UINT32_MAX未知哨兵，valid TEST从不拿这些值授信用。

### Task 4: controller 独立 W1 审计与先决门

**Dependencies:** Task 3
**Parallelizable:** No (同一原生候选、真实fixture先构建)

- [ ] 在当前controller `def main():` 之前增加以下完整函数；已有 `process_groups_binding` / 有界工具collector / 原 formal TEST不改。原controller已有所需import，无新增依赖。

```python
def require_w1_groups(metadata):
    record=metadata.get("groups_native")
    keys={"result","candidate_sha","arch","binary_sha256","ledger_sha256","binding_sha256","native_exit","cleanup_scope"}
    if (not isinstance(record,dict) or set(record)!=keys
            or record.get("result")!="native_groups_verified"
            or record.get("candidate_sha")!=metadata.get("candidate_sha")
            or record.get("arch")!=metadata.get("arch")
            or type(record.get("native_exit")) is not int or record["native_exit"]!=0
            or record.get("cleanup_scope")!="owned_root_only_identities_retained"
            or any(not isinstance(record.get(k),str) or not re.fullmatch("[0-9a-f]{64}",record[k])
                   for k in ("binary_sha256","ledger_sha256","binding_sha256"))):
        raise RuntimeError("W1_GROUPS same-candidate native evidence required")

def run_w1_groups(repo,build,output,sha,arch):
    binary=build/"icode_m0a1_groups_native"
    if binary.is_symlink() or not binary.is_file() or not os.access(binary,os.X_OK):
        raise RuntimeError("W1_GROUPS native TEST binary unavailable; not semantic RED")
    binary=binary.resolve(strict=True)
    if binary.parent!=build:
        raise RuntimeError("W1_GROUPS binary escaped build")
    size=binary.stat().st_size
    if not 0<size<=16*1024*1024:
        raise RuntimeError("W1_GROUPS binary size invalid")
    image=binary.read_bytes();digest=hashlib.sha256(image).hexdigest()
    (output/"icode_m0a1_groups_native").write_bytes(image)
    binding=output/"w1-binding";binding.mkdir(mode=0o700)
    binding_sha=process_groups_binding(repo,build,binary,"groups_native",binding)
    argv=["/usr/bin/sudo","-n","--","/usr/bin/env","-i","PATH=/usr/bin:/bin",str(binary),sha,digest]
    try:
        actual=subprocess.run(argv,cwd="/",capture_output=True,timeout=50,check=False)
    except subprocess.TimeoutExpired as exc:
        (output/"w1-native.stdout.json").write_bytes((exc.stdout or b"")[:512])
        (output/"w1-native.stderr.log").write_bytes((exc.stderr or b"")[:256])
        write_json(output/"w1-execution.json",{"candidate_sha":sha,"arch":arch,"binary_sha256":digest,
            "native_exit":"timeout","cleanup":"unknown","raw_complete":False})
        raise RuntimeError("W1_GROUPS timeout; identities retained cleanup unknown") from exc
    (output/"w1-native.stdout.json").write_bytes(actual.stdout[:512])
    (output/"w1-native.stderr.log").write_bytes(actual.stderr[:256])
    write_json(output/"w1-execution.json",{"candidate_sha":sha,"arch":arch,"binary_sha256":digest,
        "native_exit":actual.returncode,"stdout_bytes":len(actual.stdout),"stderr_bytes":len(actual.stderr),
        "stdout_sha256":hashlib.sha256(actual.stdout).hexdigest(),
        "stderr_sha256":hashlib.sha256(actual.stderr).hexdigest(),
        "raw_complete":len(actual.stdout)<=512 and len(actual.stderr)<=256})
    if actual.returncode or len(actual.stdout)>512 or len(actual.stderr)>256 or actual.stderr:
        raise RuntimeError("W1_GROUPS infrastructure failure/overflow; never quota RED")
    testpath=repo/"tests/test_macos_process_groups_native.py"
    spec=importlib.util.spec_from_file_location("w1_frozen_observer",testpath)
    if spec is None or spec.loader is None:
        raise RuntimeError("W1_GROUPS independent TEST unavailable")
    tests=importlib.util.module_from_spec(spec);spec.loader.exec_module(tests)
    def unique(pairs):
        value={}
        for key,item in pairs:
            if key in value:raise ValueError("W1_GROUPS duplicate JSON key")
            value[key]=item
        return value
    manifest=json.loads(actual.stdout,object_pairs_hook=unique)
    if (not isinstance(manifest,dict) or set(manifest)!={"version","root_directory","ledger_sha256"}
            or type(manifest["version"]) is not int or manifest["version"]!=1
            or not isinstance(manifest["root_directory"],str)
            or not re.fullmatch(r"/private/var/icode-m0a1-groups\.[A-Za-z0-9]+",manifest["root_directory"])
            or not isinstance(manifest["ledger_sha256"],str)
            or not re.fullmatch("[0-9a-f]{64}",manifest["ledger_sha256"])):
        raise RuntimeError("W1_GROUPS root manifest invalid")
    directory=Path(manifest["root_directory"])
    st=directory.lstat()
    if not stat.S_ISDIR(st.st_mode) or st.st_uid!=0 or stat.S_IMODE(st.st_mode)!=0o755:
        raise RuntimeError("W1_GROUPS protected directory invalid")
    fd=os.open(directory/"groups.jsonl",os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        before=os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid!=0 or before.st_nlink!=1
                or stat.S_IMODE(before.st_mode)!=0o444 or not 0<before.st_size<=16384):
            raise RuntimeError("W1_GROUPS protected ledger invalid")
        raw=bytearray()
        while len(raw)<=16384:
            chunk=os.read(fd,min(4096,16385-len(raw)))
            if not chunk:break
            raw.extend(chunk)
        after=os.fstat(fd)
        if (len(raw)>16384 or (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)
                !=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns)):
            raise RuntimeError("W1_GROUPS ledger changed/exceeded")
    finally:
        os.close(fd)
    raw=bytes(raw)
    if hashlib.sha256(raw).hexdigest()!=manifest["ledger_sha256"]:
        raise RuntimeError("W1_GROUPS root ledger digest differs")
    (output/"w1-native.audit.jsonl").write_bytes(raw)
    if not raw.endswith(b"\n") or len(raw.splitlines())!=5:
        raise RuntimeError("W1_GROUPS complete fixed ledger required")
    rows=[json.loads(line,object_pairs_hook=unique) for line in raw.splitlines()]
    if not tests.verify_groups(rows,sha,digest,arch):
        raise RuntimeError("W1_GROUPS independent TEST failed")
    record={"result":"native_groups_verified","candidate_sha":sha,"arch":arch,
            "binary_sha256":digest,"ledger_sha256":manifest["ledger_sha256"],"binding_sha256":binding_sha,
            "native_exit":0,"cleanup_scope":"owned_root_only_identities_retained"}
    write_json(output/"w1-result.json",record)
    return record
```

root输出虽采用与原native相同的capture方式，但新增executable本身将stdout/stderr行数/字节数固定封顶，CPU/壁钟有限，不是任意工具输出；收集后再拒超界，绝不把截断当成功。timeout50外层大于root40秒，不能声称Python能杀root进程组；父root自有超时kill+固定alarm才是身份保留边界。任何超时/异常保留原目录和lease，controller metadata原except记ERROR/cleanupunknown。

- [ ] `artifact_sources` 中在已有新helper条目之后加入完整三个输入，原条目不删：

```python
            "native/mac/tests/icode_m0a1_identity_lease.inc",
            "native/mac/tests/icode_m0a1_process_groups_native.c",
            "tests/test_macos_process_groups_native.py",
```

- [ ] 在当前 `metadata["process_groups_binding_sha256"] = process_groups_binding(...)` 的两行调用后、现有 `write_json(output / "metadata.json", metadata)` 前，插入：

```python
        metadata["groups_native"] = run_w1_groups(repo,build,output,sha,arch)
```

- [ ] 在当前 `metadata["native_ledger"] = {...}` 赋值结束后、`if formal.errors or formal.skipped or formal.testsRun != 5:` 前，插入：

```python
        require_w1_groups(metadata)
```

该调用进入 Task1 AST 抽取的实际接受尾段；坏/缺/异候选W1记录必须真实拒绝。原formal错误/skip检查、red/green分类分支和条件逐字不改；新验证是先决门，不把 W1 ERROR 当 quota assertion RED。W1多占用三身份，原七case随后自动使用其它新租约；两类证据独立账本，各自source/binaryhash，同一GitHub_SHA/arch。

- [ ] SOURCE接线后单独执行runner软件正负控：`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_macos_process_groups_native.TestW1NativeRunnerSoftware -v`。完整资产已在Task1同一TEST文件冻结：真实调用当前controller `run_w1_groups`，连同真实 `process_groups_binding`、selector collector、JSON/摘要/权限/变化校验、动态导入的真实独立 `verify_groups` 及实际结果写盘一起执行。仅OS/工具边界替身：root命令 `subprocess.run` 返回受控字节/退出，compiler/xcrun/nm启动 `Popen` 以真实有限Python子进程代工具，私有root路径的lstat/open/fstat/read映射到测试自有临时字节文件，其它真实文件/函数不替换。没有mock runner/绑定门/observer/write_json，没有真实sudo、账户/身份/lease/native/system写。

| runner软件覆盖 | 完整资产中的实际场景 |
| --- | --- |
| 成功采集/审计/发布 | `success`：真实五行账本通过真实observer后发布八字段结果；核真实输出bytes/二进制拷贝/绑定记录摘要/native_exit/只授owned-root范围 |
| binary/SDK前置 | missing/symlink/nonexec/empty/oversize/escaped binary；真实绑定检查由工具错误扩展符号触发拒绝，不启动native |
| native失败及输出界 | timeout/nonzero/非空stderr/stdout513/stderr257；核原执行状态、完整raw摘要或timeout unknown，以及落盘截断边界 |
| manifest解析/身份 | duplicate key/badJSON/badUTF8/non-object/版本2或bool/非法或非字符串路径/坏或非字符串摘要/额外字段/真实ledger摘要不匹配 |
| protected目录 | 非directory、owner非root、mode非0755 |
| ledger权限/资源 | open/read错误、非regular、owner非root、mode非0444、nlink2、size0或16385、实际读取超16384 |
| 同一读取稳定性 | 分别改变dev/ino/size/mtime_ns，触发真实before/after比较 |
| 完整账本与真实observer | 四行/末尾LF缺失/五行中坏JSON/重复键；真实独立observer拒绝错误四ID/双组/predicate/NOTE_EXEC/候选SHA |
| 失败发布与资源 | 每个非success场景必须抛错且不存在`w1-result.json`；全部实际打开的ledger fd已关闭，不能把失败标记成成功 |

这些软件字节显式标记software；临时image不是Mach-O，工具输出不是AppleSDK原事实，root元数据只在OS边界模型。通过仅证明真实runner的接线、采集/审计/拒绝/发布行为，绝不授原生组事实、SDK/符号或持久身份信用。fixture/runner缺失只算基础设施错误；controller真实语义RED仍严格按Task1原接受尾段取得，不能借新测试missing函数偷换。

- [ ] 针对性软件验收（不本机native、不全量）：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_macos_process_groups_native tests.test_macos_process_groups tests.test_macos_m0a1_diagnostics tests.test_macos_task_quota_probe.TestM0a1Protocol -v
```

预期新增observer1、gate2、inverse1、lease软件1（含7场景）、runner软件1（含50场景），加W0针对性22共28项在Linux实际执行GREEN，无ERROR/SKIP；以真实runner计数为准。AST旧接受门的RED现应GREEN，valid旧quotaRED+同候选W1记录仍接受，错候选/未知/digest错误拒绝。仅软件控制locals/字节、真实runner与实际C函数软件自校验，不授真实native信用。若新controller实现失败，先从真实trace定位，不改冻TEST使其通过。

### Task 5: 真实fixture接线的软件有界自校验与线上闭环

**Dependencies:** Task 4
**Parallelizable:** No (实际SOURCE双审后同候选)

- [ ] root完整阅读全部实际资产与diff，fresh SPEC → 不同 QUALITY C0/I0/M0；TEST与SOURCE作者不同，双审也独立。root按现有授权只做secret/submodule/必要针对性软件回归后，将待验候选main-only提交推送，作者不自动Git操作。
- [ ] 两架构CI默认构建新native target；同controller一次执行W0 actualSDK/object/final绑定、新native actualSDK/object/final绑定、三观测+两exit独立root账本、原七caseformalRED。新target任何warning/compile/link错误是基础设施失败，不是RED。先决失败使同候选失败，不跳过W1保原7case信用。
- [ ] root读取全部原artifact与metadata，记录新SHA/run/job/platform/attempt、compiler/SDK路径版本、实际argv/头展开/两object/final普通 `_getgroups`、每条rawhash、两个binary/两个rootledgerhash及退出状态。W1正控前后四ID=UID、count1/capacity1/read1/[UID]、同predicate0、同PID/start且root NOTE_EXEC=1；负控四ID=其UID、count2/capacity2/read2集合恰{UID,extra}、同predicate EPERM，extra非零独占且不等两UID，身份全部来自实际永久lease。父observer/rootsavedUIDGID/start/livecount/exit/remaining证据齐全；任何未知均拒绝。
- [ ] 原七case完整进入原formal oracle：protocol5/native5、唯一 `test_cap1_quota_semantic` 的真实 baseline fork成功触发 `M0A1_QUOTA_REJECTION`，0error/skip，controller `semantic_RED_confirmed`。W0旧67格仅历史，不能替代W1新候选。新的W1证据也不能替代原7case或quotaGREEN。
- [ ] 失败从原始日志定位，最多本机最小软件复现，不自动重复整套测试，不取消/重跑隐藏失败。超时、lease耗尽、sysctl/proc未知、root保护/manifest异常、组前置不成立、未调用predicate、错误拒绝值、exec未知、child/extra残留均保留身份和目录并拒绝。不得删账户/lease、放宽组数、用组0/hostgid、建目录账号或绕过macro/symbol门。
- [ ] 只有W1最终新SHA上述全部门通过，root才能另派不同作者实施已受审quotaSOURCE；quotaSOURCE仍需自己的新候选全门验收。本计划不含该SOURCE，不授M0a1GREEN/M0a2/M0b/M1/R2/R3/ready或90%信用。

## 两次自审与交接

第一次自审对DESIGN覆盖：§3真实TU/predicate链接、私有固定TESTtarget齐全；§4单组+同PIDexec/两组真实反例/额外独占有限GID/父PIDstart/独立账本/错误拒绝/同SHA原7case由Task2–5覆盖；§5不新增predicate内部诊断，不改变其短路。四函数抽取仅mechanical，inverse验证保护原7case原语，不扩为通用root工具。

第二次自审对信用边界：W1fixture是TEST，既有helper已正确；controller接受门RED跑真实旧AST尾段，缺W1证据仍返回0才是目标失败，名称缺失不计；software_rows只检验observer严拒，不是native事实；reserve_unused_id软件场景编译运行实际函数，仅模拟OS边界，验证未知立即拒绝及碰撞身份不重用，不授实际持久租约/native信用；runner新增完整正负控真实执行run_w1_groups、绑定门/collector/JSON/observer/发布，只有工具和OS边界替身；全部失败必须无成功文件且关闭账本fd。全部实际native/SHA/SDK/cleanup信用必须由CI原artifact取得。原7case分类条件保持，quota源码仍禁止提前创建。作者仅RAM解析五段Python资产AST，并核对81行lease块加末尾LF与现driver对应3571字节逐字相等（SHA `3f8563da5c30d55469776a212b397e4515a33b090dae4d387d8439ffc0226e82`）；没有import/执行资产，也没有编译/运行native或TEST，没有pycache/临时源码/二进制写入。

修订记录：前一947行候选 `b46aa2a25c50992ed6120aa5580cd7f4403f1102c145956bc6809ad66c5cfeba` 的freshSPEC为C0/I1/M0，未批准；本修订仅将reserve_unused_id的process快照保存为active，负值立即拒绝，已知碰撞烧lease继续，双快照均明确空闲才返回，并补齐实际该函数的软件7场景资产及Linux27项命令/计数。旧审查结论保留，等待root补读变更和新freshSPEC→不同QUALITY；不减少任何原hard门。

第二次修订记录：1049行候选 `6b137ce10310efc9ba89773f1803eaee9351015f23a543c413b5c3e6e2d443e8` 的freshQUALITY为C0/I1/M0，未批准。作者已读root转交的完整QUALITY I1原文：run_w1_groups原99行采集/审计路径缺少实际软件正负控，旧27项可能不触及该路径。仅补齐真实runner完整边界资产、独立命令/覆盖映射和Linux28项计数，controller/native/原hard门资产不改；不把旧QUALITY回写通过，等待新freshSPEC→不同QUALITY。

【架构级自检报告】

- 语法/编译：完整C/Python/CMake资产静态阅读；本轮未编译或执行，没有SDK编译通过信用。
- 依赖/调用链：四函数inc所有类型/变量/固定lease路径/错误出口前置列齐；driver inverse保护，独立target链接真实TU；新gate在原分类前。
- 逻辑/边界：正控setgroups1→setgid→setuid及exec后重复，负控setgroups2完整前置才调用同predicate；root独立PID/start/savedIDs/NOTE_EXEC/退出观察，额外GID有限lease与碰撞门；process快照负值立即拒绝，不能被后续成功隐藏，实际该函数软件7场景覆盖。
- 异常处理：宏/SDK/符号原门保持；超时/超界/解析/碰撞/未知/耗尽全拒绝，原始证据及永久身份保留；真实runner软件正负控覆盖元数据/读取变化/JSON/observer拒绝，所有失败不得发布成功文件且不泄漏账本fd；ERROR不当quotaRED。
- 关联模块：原wire/formal/release/phase/classification不变，新增CMake/摘要/TEST/controller门同步，W1新SHA重跑全部原门。
- 兼容安全：不建账号/daemon/任意命令root接口，不复制predicate或include整driver，不放宽原组数/清理信用；本轮只新增文档，dirty保留。
- 可运行性：完整实施资产和命令已列，仍需root全文/fresh双审/独立TEST与不同SOURCE及双native原日志；本轮不虚报100%运行通过。

---
**Execution Mode:** serial

作者停止于PLAN，不自动实施/提交/推送。行数与完整SHA交接另记，避免自哈希循环。
