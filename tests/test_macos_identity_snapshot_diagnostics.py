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
#define _DARWIN_C_SOURCE 1
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
        # Match the native observers' Darwin header opt-in before including headers.
        self.assertIn("#define _DARWIN_C_SOURCE 1\n",PRELUDE)
        self.assertLess(PRELUDE.index("#define _DARWIN_C_SOURCE 1\n"),PRELUDE.index("#include"))
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
