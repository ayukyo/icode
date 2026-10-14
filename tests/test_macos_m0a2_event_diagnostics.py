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
#undef sigemptyset
#undef sigaddset
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
        program=probe_source(CFILE.read_text(encoding="utf-8"),HELPER.read_text(encoding="utf-8"))
        marker="#define kill model_kill\n"
        self.assertEqual(program.count(marker),1)
        # System headers may expose POSIX signal operations as function-like macros.
        program=program.replace(marker,
            "#undef sigemptyset\n#undef sigaddset\n"
            "#define sigemptyset(set) (sigemptyset)(set)\n"
            "#define sigaddset(set,signum) (sigaddset)((set),(signum))\n"+marker,1)
        built=subprocess.run([shutil.which("cc"),"-std=c11","-Wall","-Wextra","-Werror",
                              "-Wno-unused-function","-x","c","-","-o",
                              str(Path(self.temporary.name)/"macro-probe")],
                             input=program.encode("ascii"),capture_output=True,timeout=30)
        self.assertEqual(built.returncode,0,built.stderr.decode("utf-8","replace"))
        self.assertEqual(built.stderr,b"")
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
