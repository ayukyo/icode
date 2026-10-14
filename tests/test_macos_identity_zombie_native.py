"""Explicit opt-in Darwin owned-child CI fixture, not all-host enumeration proof."""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import sys
import unittest

from tests.test_macos_identity_snapshot_diagnostics import function

ROOT = Path(__file__).resolve().parents[1]
LEASE = ROOT / "native/mac/tests/icode_m0a1_identity_lease.inc"

PRELUDE = r'''
#define _DARWIN_C_SOURCE 1
#include <errno.h>
#include <inttypes.h>
#include <libproc.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/proc.h>
#include <sys/proc_info.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
enum { MAX_PIDS=8192 };
static pid_t selected;
static volatile sig_atomic_t interrupted;
static struct proc_bsdinfo observed;
static int query_result,query_errno;
static uint64_t query_arg;
static void interrupt_handler(int value) { interrupted=value; }
static int owned_list(void *buffer,int size) {
 if(selected<=0 || size!=(int)(MAX_PIDS*sizeof(pid_t))) abort();
 ((pid_t *)buffer)[0]=selected;return 1;
}
static int observed_query(int pid,int flavor,uint64_t arg,void *buffer,int size) {
 int result=proc_pidinfo(pid,flavor,arg,buffer,size);
 int saved=errno;query_arg=arg;query_result=result;query_errno=saved;
 memset(&observed,0,sizeof(observed));
 if(result==(int)sizeof(observed)) memcpy(&observed,buffer,sizeof(observed));
 errno=saved;return result;
}
#define proc_listallpids owned_list
#define proc_pidinfo observed_query
'''
TRAILER = r'''
#undef proc_listallpids
#undef proc_pidinfo
static int one_byte(int fd,char *value,int writing) {
 ssize_t n;
 do {n=writing ? write(fd,value,1) : read(fd,value,1);}
 while(n<0 && errno==EINTR && !interrupted);
 return n==1 ? 0 : -1;
}
static int same_identity(const struct proc_bsdinfo *a,const struct proc_bsdinfo *b) {
 return a->pbi_pid==b->pbi_pid && a->pbi_ppid==b->pbi_ppid &&
        a->pbi_start_tvsec==b->pbi_start_tvsec && a->pbi_start_tvusec==b->pbi_start_tvusec;
}
static int same_six(const struct proc_bsdinfo *a,const struct proc_bsdinfo *b) {
 return a->pbi_ruid==b->pbi_ruid && a->pbi_uid==b->pbi_uid && a->pbi_svuid==b->pbi_svuid &&
        a->pbi_rgid==b->pbi_rgid && a->pbi_gid==b->pbi_gid && a->pbi_svgid==b->pbi_svgid;
}
static int matches(uid_t uid,const struct proc_bsdinfo *b) {
 return b->pbi_ruid==uid || b->pbi_uid==uid || b->pbi_svuid==uid ||
        b->pbi_rgid==uid || b->pbi_gid==uid || b->pbi_svgid==uid;
}
int main(void) {
 int ready[2]={-1,-1},release[2]={-1,-1},rc=2,reaped=0,status=0;
 pid_t child=-1;const char *stage="setup";
 struct proc_bsdinfo live,zombie;
 memset(&live,0,sizeof(live));memset(&zombie,0,sizeof(zombie));
 struct sigaction action;memset(&action,0,sizeof(action));
 action.sa_handler=interrupt_handler;
 if(sigemptyset(&action.sa_mask)<0 || sigaction(SIGALRM,&action,NULL)<0 ||
    sigaction(SIGTERM,&action,NULL)<0) goto done;
 if(signal(SIGPIPE,SIG_IGN)==SIG_ERR || signal(SIGCHLD,SIG_DFL)==SIG_ERR) goto done;
 alarm(10);
 if(pipe(ready)<0 || pipe(release)<0) goto done;
 child=fork();
 if(child<0) goto done;
 if(child==0) {
  if(signal(SIGALRM,SIG_DFL)==SIG_ERR) _exit(21);
  alarm(8);
  close(ready[0]);close(release[1]);
  char byte='R';
  if(one_byte(ready[1],&byte,1)<0) _exit(22);
  if(one_byte(release[0],&byte,0)<0 || byte!='X') _exit(23);
  close(ready[1]);close(release[0]);_exit(0);
 }
 selected=child;
 close(ready[1]);ready[1]=-1;close(release[0]);release[0]=-1;
 char byte=0;
 stage="live-ready";
 if(one_byte(ready[0],&byte,0)<0 || byte!='R') goto done;
 struct process_snapshot snapshot;
 stage="live-count";
 if(process_count_snapshot(getuid(),&snapshot)!=1 || query_result!=(int)sizeof(live)) goto done;
 live=observed;
 if(live.pbi_pid!=(uint32_t)child || live.pbi_ppid!=(uint32_t)getpid() ||
    live.pbi_status==SZOMB || live.pbi_start_tvsec==0 || live.pbi_start_tvusec>=1000000 ||
    !matches(getuid(),&live)) goto done;
 stage="release";
 byte='X';if(one_byte(release[1],&byte,1)<0) goto done;
 close(release[1]);release[1]=-1;
 stage="waitid-wnowait";
 siginfo_t info;int waited;
 do {memset(&info,0,sizeof(info));waited=waitid(P_PID,(id_t)child,&info,WEXITED|WNOWAIT);}
 while(waited<0 && errno==EINTR && !interrupted);
 if(waited<0 || interrupted || info.si_pid!=child || info.si_code!=CLD_EXITED || info.si_status!=0) goto done;
 stage="zombie-count";
 if(process_count_snapshot(getuid(),&snapshot)!=1 || query_result!=(int)sizeof(zombie)) goto done;
 zombie=observed;
 if(query_arg!=1 || zombie.pbi_status!=SZOMB || !same_identity(&live,&zombie) ||
    !same_six(&live,&zombie)) goto done;
 uid_t foreign=0;
 while(matches(foreign,&zombie)) foreign++;
 stage="foreign-zombie";
 if(process_count_snapshot(foreign,&snapshot)!=0 || query_result!=(int)sizeof(zombie) ||
    !same_identity(&zombie,&observed) || !same_six(&zombie,&observed)) goto done;
 stage="reap";
 pid_t got;
 do {got=waitpid(child,&status,0);} while(got<0 && errno==EINTR && !interrupted);
 if(got!=child) goto done;
 reaped=1;child=-1;
 if(!WIFEXITED(status) || WEXITSTATUS(status)!=0) goto done;
 stage="old-identity-after-reap";
 /* A reused PID must never be accepted as the old child or signalled below.
    A complete different-start query is observation interference, not success. */
 int count=process_count_snapshot(getuid(),&snapshot);
 if(query_result==(int)sizeof(observed)) {
  if(same_identity(&live,&observed)) stage="reaped-old-identity-still-visible";
  else stage="pid-reuse-observation-inconclusive";
  goto done;
 }
 if(count!=0 || query_result!=0 || query_errno!=ESRCH) goto done;
 rc=0;
done:
 {
  int saved=errno;
  for(unsigned i=0;i<2;i++) {
   if(ready[i]>=0) close(ready[i]);
   if(release[i]>=0) close(release[i]);
  }
  if(child>0) {
   /* child is unreaped: PID ownership is retained, so it cannot be reused. */
   if(kill(child,SIGKILL)<0 && errno!=ESRCH) rc=2;
   pid_t got;
   do {got=waitpid(child,&status,0);} while(got<0 && errno==EINTR);
   if(got==child) reaped=1;
   else rc=2;
  }
  alarm(0);
  if(interrupted) rc=2;
  if(rc || !reaped) {
   fprintf(stderr,"ZOMBIE_NATIVE_FAILURE stage=%s errno=%d query_arg=%" PRIu64
           " query_result=%d query_errno=%d cleanup=%s\n",
           stage,saved,query_arg,query_result,query_errno,reaped ? "owned_child_reaped" : "unknown");
   return 2;
  }
  printf("{\"version\":1,\"pid\":%u,\"parent\":%u,\"start\":[%" PRIu64 ",%" PRIu64
         "],\"live_status\":%u,\"zombie_status\":%u,\"query_arg\":1,"
         "\"counts\":[1,1,0,0],\"six_fields\":[%u,%u,%u,%u,%u,%u],"
         "\"waited_exit\":0,\"reaped\":true,\"identity_rejected\":true,"
         "\"cleanup\":\"owned_child_reaped\"}\n",
         live.pbi_pid,live.pbi_ppid,(uint64_t)live.pbi_start_tvsec,(uint64_t)live.pbi_start_tvusec,
         live.pbi_status,zombie.pbi_status,(unsigned)live.pbi_ruid,(unsigned)live.pbi_uid,
         (unsigned)live.pbi_svuid,(unsigned)live.pbi_rgid,(unsigned)live.pbi_gid,(unsigned)live.pbi_svgid);
  return 0;
 }
}
'''


def native_program(source):
    declarations = re.findall(r"^struct process_snapshot \{.*?^\};\n", source, re.M | re.S)
    if len(declarations) != 1:
        raise AssertionError("actual snapshot declaration unavailable")
    return PRELUDE + declarations[0] + function(source, "process_count_snapshot") + TRAILER


@unittest.skipUnless(
    sys.platform == "darwin" and os.environ.get("ICODE_RUN_IDENTITY_ZOMBIE_NATIVE") == "1",
    "explicit Darwin owned-child compatibility gate only")
class TestIdentityZombieNative(unittest.TestCase):
    """CI fixture is opt-in; default local discovery needs no GitHub environment."""
    def test_owned_child_live_zombie_and_reap_use_actual_snapshot_query(self):
        self.assertNotEqual(os.getuid(), 0, "native compatibility fixture must remain nonroot")
        self.assertNotEqual(os.geteuid(), 0, "native compatibility fixture must remain nonroot")
        expected_arch = os.environ.get("ICODE_ZOMBIE_EXPECTED_ARCH")
        self.assertIn(expected_arch, ("arm64", "x86_64"))
        self.assertEqual(platform.machine(), expected_arch)
        candidate = os.environ.get("GITHUB_SHA", "")
        self.assertRegex(candidate, r"^[0-9a-f]{40}$")
        runtime = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
        output = runtime / "icode-identity-zombie-native"
        self.assertFalse(output.exists() or output.is_symlink())
        output.mkdir(mode=0o700)
        binding = dict(version=1, candidate_sha=candidate, arch=platform.machine(),
                       kernel=platform.release(), result="unaccepted", cleanup="unknown",
                       enumeration="projected_owned_child_only", run_id=os.environ["GITHUB_RUN_ID"],
                       run_attempt=os.environ["GITHUB_RUN_ATTEMPT"])
        records = []

        def collect(label, command, *, timeout=15, input_bytes=None):
            try:
                result = subprocess.run(command, cwd=ROOT, input=input_bytes,
                                        capture_output=True, timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                (output / (label + ".stdout")).write_bytes(exc.stdout or b"")
                (output / (label + ".stderr")).write_bytes(exc.stderr or b"")
                records.append(dict(label=label, argv=list(map(str, command)),
                                    exit_code=None, timed_out=True))
                raise
            self.assertLessEqual(len(result.stdout) + len(result.stderr), 131072)
            (output / (label + ".stdout")).write_bytes(result.stdout)
            (output / (label + ".stderr")).write_bytes(result.stderr)
            records.append(dict(label=label, argv=list(map(str, command)), exit_code=result.returncode))
            self.assertEqual(result.returncode, 0, result.stderr[:4096])
            return result.stdout.decode("utf-8", "strict").strip()

        try:
            self.assertEqual(collect("candidate", ["git", "rev-parse", "HEAD"]), candidate)
            binding["os_version"] = collect("os-version", ["/usr/bin/sw_vers", "-productVersion"])
            binding["os_build"] = collect("os-build", ["/usr/bin/sw_vers", "-buildVersion"])
            compiler = collect("compiler", ["/usr/bin/xcrun", "--find", "clang"])
            sdk = collect("sdk", ["/usr/bin/xcrun", "--show-sdk-path"])
            binding["sdk_version"] = collect("sdk-version", ["/usr/bin/xcrun", "--show-sdk-version"])
            binding["compiler_version"] = collect("compiler-version", [compiler, "--version"])
            headers = ("libproc.h", "sys/proc_info.h", "sys/proc.h")
            binding["sdk_header_sha256"] = {
                name: hashlib.sha256((Path(sdk) / "usr/include" / name).read_bytes()).hexdigest()
                for name in headers
            }
            source = LEASE.read_bytes()
            code = native_program(source.decode("utf-8")).encode("ascii")
            (output / "probe.c").write_bytes(code)
            binding.update(source_sha256=hashlib.sha256(source).hexdigest(),
                           test_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                           probe_sha256=hashlib.sha256(code).hexdigest(), sdk=sdk)
            executable = output / "probe"
            command = [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                       "-Wno-unused-function", "-isysroot", sdk, "-x", "c", "-", "-o", str(executable)]
            collect("compile", command, timeout=30, input_bytes=code)
            binding["binary_sha256"] = hashlib.sha256(executable.read_bytes()).hexdigest()
            binding["binary_arch"] = collect("binary-arch", ["/usr/bin/lipo", "-archs", str(executable)])
            self.assertEqual(binding["binary_arch"], expected_arch)
            symbols = collect("symbols", ["/usr/bin/nm", "-u", str(executable)])
            imported = {line.split()[-1] for line in symbols.splitlines() if line.strip()}
            self.assertTrue({"_proc_pidinfo", "_kill", "_waitid", "_waitpid"} <= imported)
            self.assertNotIn("_proc_listallpids", imported)
            child = subprocess.Popen([str(executable)], cwd=ROOT,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            timed_out = False
            try:
                stdout, stderr = child.communicate(timeout=15)
            except subprocess.TimeoutExpired:
                timed_out = True
                child.terminate()
                try:
                    stdout, stderr = child.communicate(timeout=3)
                except subprocess.TimeoutExpired:
                    child.kill()
                    stdout, stderr = child.communicate(timeout=3)
            finally:
                if child.poll() is None:
                    child.kill()
                    child.communicate(timeout=3)
            self.assertLessEqual(len(stdout) + len(stderr), 8192)
            (output / "native.stdout").write_bytes(stdout)
            (output / "native.stderr").write_bytes(stderr)
            records.append(dict(label="native", argv=[str(executable)], exit_code=child.returncode,
                                timed_out=timed_out))
            self.assertFalse(timed_out, "owned-child timeout; cleanup remains unknown")
            self.assertEqual(child.returncode, 0, stderr.decode("utf-8", "replace"))
            self.assertEqual(stderr, b"")
            receipt = json.loads(stdout)
            self.assertEqual(set(receipt), {"version", "pid", "parent", "start", "live_status",
                                           "zombie_status", "query_arg", "counts", "six_fields",
                                           "waited_exit", "reaped", "identity_rejected", "cleanup"})
            self.assertEqual(receipt["version"], 1)
            self.assertEqual(receipt["query_arg"], 1)
            self.assertEqual(receipt["counts"], [1, 1, 0, 0])
            self.assertEqual(len(receipt["six_fields"]), 6)
            self.assertEqual(len(receipt["start"]), 2)
            self.assertTrue(receipt["reaped"] and receipt["identity_rejected"])
            self.assertEqual(receipt["cleanup"], "owned_child_reaped")
            binding.update(result="owned_child_query_verified", cleanup=receipt["cleanup"], receipt=receipt)
        finally:
            binding["commands"] = records
            binding["raw_sha256"] = {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(output.glob("*.stdout")) + sorted(output.glob("*.stderr"))
            }
            (output / "binding.json").write_text(
                json.dumps(binding, ensure_ascii=True, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        print("IDENTITY_ZOMBIE_NATIVE:" + json.dumps(binding, ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
