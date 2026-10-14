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
        marker=b'#include "icode_m0a1_fixed_helpers.inc"\n'
        if marker in content:
            self.assertEqual(content.count(marker),1)
            common=(driver.parent/"icode_m0a1_fixed_helpers.inc").read_bytes()
            self.assertEqual(common.count(b"static int canaries("),1)
            self.assertEqual(content.count(b"static void gate("),1)
            split=common.index(b"static int canaries(")
            content=content.replace(marker,common[:split],1)
            content=content.replace(b"static void gate(",common[split:]+b"static void gate(",1)
        marker=b'#include "icode_m0a1_identity_lease.inc"\n'
        if marker in content:
            self.assertEqual(content.count(marker),1)
            lease=(driver.parent/"icode_m0a1_identity_lease.inc").read_bytes()
            # Reverse only the reviewed zombie-query semantic projection, then prove the old full hash.
            zombie_query=b"proc_pidinfo(pids[i],PROC_PIDTBSDINFO,1,&b,sizeof(b)); /* Include listed zombies in this identity census. */"
            original_query=b"proc_pidinfo(pids[i],PROC_PIDTBSDINFO,0,&b,sizeof(b));"
            if zombie_query in lease:
                self.assertEqual(lease.count(zombie_query),1)
                lease=lease.replace(zombie_query,original_query,1)
            self.assertEqual(lease.count(original_query),1)
            if b"/* IDENTITY_SNAPSHOT_DIAGNOSTIC_BEGIN */\n" in lease:
                self.assertEqual(hashlib.sha256(lease).hexdigest(),
                    "3c8e74cffa0dfda2fc8e7cf91e67cd6db99c7a5c88167ab9c95925887356ada5")
                # Strip only the reviewed diagnostic projection; keep the original hash below.
                diagnostic=rb"/\* IDENTITY_SNAPSHOT_DIAGNOSTIC_BEGIN \*/\n.*?/\* IDENTITY_SNAPSHOT_DIAGNOSTIC_END \*/\n"
                algorithm=rb"/\* IDENTITY_SNAPSHOT_ALGORITHM_BEGIN \*/\n.*?/\* IDENTITY_SNAPSHOT_ALGORITHM_END \*/\n"
                self.assertEqual(len(re.findall(diagnostic,lease,re.S)),1)
                self.assertEqual(len(re.findall(algorithm,lease,re.S)),1)
                original_count=b"""static int process_count(uid_t uid) {
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
"""
                lease=re.sub(diagnostic,b"",lease,count=1,flags=re.S)
                lease=re.sub(algorithm,lambda _:original_count,lease,count=1,flags=re.S)
                lease=lease.replace(
                    b"uid_t uid=UID_FIRST+i; struct process_snapshot before_snapshot;\n"
                    b"        int before=process_count_snapshot(uid,&before_snapshot);",
                    b"uid_t uid=UID_FIRST+i; int before=process_count(uid);",1)
                lease=lease.replace(
                    b'if(before<0) {\n'
                    b'            emit_process_snapshot("reserve-process-snapshot",uid,&before_snapshot);\n'
                    b'            die("reserve-process-snapshot");\n'
                    b'        }',b'if(before<0) die("reserve-process-snapshot");',1)
                lease=lease.replace(
                    b"struct process_snapshot after_snapshot;\n"
                    b"        int after=process_count_snapshot(uid,&after_snapshot);\n"
                    b'        if(after<0) emit_process_snapshot("reserve-contaminated",uid,&after_snapshot);\n'
                    b'        if(after!=0) die("reserve-contaminated");',
                    b'if(process_count(uid)!=0) die("reserve-contaminated");',1)
            content=content.replace(marker,lease,1)
        self.assertEqual(hashlib.sha256(content).hexdigest(),
            "a65f067ec9c6b32eb3bb7cc7afd803fe465d02273b5484561b237db59c31f673")

@unittest.skipUnless(sys.platform=="linux","Linux lease software model only; no native credit")
class TestW1LeaseSnapshotSoftware(unittest.TestCase):
    def test_actual_reservation_unknown_collision_and_success(self):
        native=ROOT/"native/mac/tests/icode_m0a1_process_groups_native.c"
        self.assertTrue(native.is_file(),"native TEST asset absent is infrastructure, not RED")
        source=native.read_text(encoding="utf-8")
        marker='#include "icode_m0a1_unused_identity.inc"\n'
        if marker in source:
            self.assertEqual(source.count(marker),1)
            source=source.replace(marker,(native.parent/"icode_m0a1_unused_identity.inc").read_text(encoding="utf-8"),1)
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
