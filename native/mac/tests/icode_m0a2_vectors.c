#define _DARWIN_C_SOURCE 1
#include "icode_m0a1_limit.h"
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
#include <poll.h>
#include <pthread.h>
#include <pwd.h>
#include <signal.h>
#include <spawn.h>
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
#include <time.h>
#include <unistd.h>
enum { UID_FIRST=60000,UID_COUNT=1024,MAX_PIDS=8192,MAX_IMAGE=16*1024*1024,
       VMAGIC=0x4d304132,CONFIG=100,READY=101,START=1,OP=2,FORKED=3,
       REAPED=4,THREADS=5,ZOMBIE=6,FINISH=7,DONE=8,
       FORK_OP=1,SPAWN_OP=2,LOWER=3,RESTORE=4,RAISE=5,DENY=6,CALIBRATE=7 };
struct definition { const char *name;int vector,quota,profile,cap,roots,shared; };
static const struct definition source_cases[]={
 {"fork_exec_q",1,1,1,1,1,0},{"fork_exec_c",1,0,1,1,1,0},
 {"spawn_q",2,1,1,1,1,0},{"spawn_c",2,0,1,1,1,0},
 {"third_q",3,1,1,2,1,0},{"third_c",3,0,1,2,1,0},
 {"refork_q",4,1,1,2,1,0},{"refork_c",4,1,0,2,1,0},
 {"grandchild_q",5,1,1,2,1,0},{"grandchild_c",5,0,1,2,1,0},
 {"pthread_q",6,1,1,1,1,0},{"pthread_c",6,0,1,1,1,0},
 {"zombie_q",7,1,1,2,1,0},{"zombie_c",7,0,1,2,1,0},
 {"soft_q",8,1,1,2,1,0},{"soft_c",8,0,1,2,1,0},
 {"hard_q",9,1,1,2,1,0},{"hard_c",9,0,1,2,1,0},
 {"hard_root_calibration",12,0,0,3,1,0},
 {"independent_q",10,1,1,2,2,0},{"independent_c",10,0,1,2,2,0},
 {"shared_counterexample",10,1,1,2,2,1},
 {"migration_guard",11,1,1,1,1,0},{"migration_counterexample",11,1,1,1,2,1}
};
static const struct definition baseline_cases[]={
 {"baseline_third",3,1,1,2,1,0},{"baseline_control",3,0,1,2,1,0}
};
struct event {
 uint32_t magic,version,length,kind,slot,other,op;
 int32_t pid,ppid,uid,euid,gid,egid,count,read,predicate,error,aux,fd3_errno,fd4_errno,canary_error,canary_allowed;
 int64_t rc;
 uint64_t group,current,maximum;
};
_Static_assert(sizeof(struct event)<=PIPE_BUF,"atomic event exceeds PIPE_BUF");
static const char lease_root[]="/private/var/icode-m0a1-leases";
static const char owner_text[]="ICODE-M0A1-v1\n";
static unsigned char unavailable[UID_COUNT];
static char image[PATH_MAX],directory[PATH_MAX],binary_hash[65],sandbox_hash[65];
static const char *candidate;
static int canary_errno=-1,canary_allowed;
static volatile sig_atomic_t owned[2];
static void expire(int sig) {
 (void)sig;
 for(unsigned i=0;i<2;i++) if(owned[i]>0) (void)kill((pid_t)owned[i],SIGKILL);
 _exit(124);
}
static void die(const char *stage) {
 int e=errno ? errno : EPROTO;
 fprintf(stderr,"M0A2 stage=%s errno=%d retained=%s cleanup=unknown\n",stage,e,directory);
 for(unsigned i=0;i<2;i++) if(owned[i]>0) (void)kill((pid_t)owned[i],SIGKILL);
 exit(2);
}
#include "icode_m0a1_fixed_helpers.inc"
#include "icode_m0a1_identity_lease.inc"
#include "icode_m0a1_unused_identity.inc"
static uint64_t experiment_deadline;
static uint64_t monotonic_ns(void) {
 struct timespec value;
 if(clock_gettime(CLOCK_MONOTONIC,&value)<0) die("monotonic-clock");
 if(value.tv_sec<0 || value.tv_nsec<0 || value.tv_nsec>=1000000000L ||
    (uint64_t)value.tv_sec>(UINT64_MAX-(uint64_t)value.tv_nsec)/1000000000ULL)
  die("monotonic-range");
 return (uint64_t)value.tv_sec*1000000000ULL+(uint64_t)value.tv_nsec;
}
static void parse_deadline(const char *text) {
 if(!hex_string(text,16)) die("deadline-hex16");
 char *end=NULL;errno=0;unsigned long long value=strtoull(text,&end,16);
 if(errno || end==text || *end || value>UINT64_MAX) die("deadline-overflow");
 uint64_t now=monotonic_ns();
 if((uint64_t)value<=now || (uint64_t)value-now>480000000000ULL) die("deadline-window");
 experiment_deadline=(uint64_t)value;
}
static unsigned remaining_seconds(void) {
 uint64_t now=monotonic_ns();
 if(now>=experiment_deadline || experiment_deadline-now<1000000000ULL) die("deadline-expired");
 return (unsigned)((experiment_deadline-now)/1000000000ULL);
}
static struct definition definition_at(int index) {
 if(!strcmp(m0_variant(),"baseline")) {
  if(index<0 || index>=2) die("baseline-index");
  return baseline_cases[index];
 }
 if(index<0 || index>=24) die("source-index");
 return source_cases[index];
}
static void sample(struct event *e,unsigned kind,unsigned slot,unsigned other,
                   unsigned op,int64_t rc,int error,int aux) {
 memset(e,0,sizeof(*e));
 e->magic=VMAGIC;e->version=1;e->length=sizeof(*e);e->kind=kind;e->slot=slot;
 e->other=other;e->op=op;e->rc=rc;e->error=error;e->aux=aux;
 e->pid=getpid();e->ppid=getppid();e->uid=getuid();e->euid=geteuid();
 e->gid=getgid();e->egid=getegid();gid_t g=UINT32_MAX;
 e->count=m0_process_getgroups(0,NULL);e->read=m0_process_getgroups(1,&g);e->group=g;
 e->predicate=m0_process_credentials((uid_t)e->uid);
 e->canary_error=canary_errno;e->canary_allowed=canary_allowed;
 errno=0;e->fd3_errno=fcntl(3,F_GETFD)<0 ? errno : 0;
 errno=0;e->fd4_errno=fcntl(4,F_GETFD)<0 ? errno : 0;
 struct rlimit actual;
 if(getrlimit(RLIMIT_NPROC,&actual)<0) _exit(80);
 e->current=actual.rlim_cur;e->maximum=actual.rlim_max;
}
static char send_event(unsigned kind,unsigned slot,unsigned other,unsigned op,
                       int64_t rc,int error,int aux) {
 struct event e;sample(&e,kind,slot,other,op,rc,error,aux);
 /* One bounded write: shared data writers cannot interleave a record. */
 ssize_t n;
 do { n=write(5,&e,sizeof(e)); } while(n<0 && errno==EINTR);
 char response=0;
 if(n!=(ssize_t)sizeof(e) || all_read(20+(int)slot,&response,1)) _exit(81);
 return response;
}
static void require_ack(char actual,char expected) { if(actual!=expected) _exit(82); }
static void status_event(unsigned kind,unsigned slot,int error) {
 struct event e;sample(&e,kind,slot,0,0,0,error,canary_errno);
 if(all_write(3,&e,sizeof(e))) _exit(83);
}
static void wait_child(pid_t child,unsigned slot,unsigned child_slot) {
 int status=0;pid_t result;
 do { result=waitpid(child,&status,0); } while(result<0 && errno==EINTR);
 if(result!=child || !WIFEXITED(status) || WEXITSTATUS(status)) _exit(84);
 require_ack(send_event(REAPED,slot,child_slot,0,child,0,status),'A');
}
static int block_diagnostic_sigpipe(void) {
 sigset_t blocked;
 return sigemptyset(&blocked)==0 && sigaddset(&blocked,SIGPIPE)==0 &&
        sigprocmask(SIG_BLOCK,&blocked,NULL)==0;
}
static _Noreturn void launch_failure(int index,unsigned slot,unsigned child_slot,
                                     const char *stage,int saved_errno) {
 if(!block_diagnostic_sigpipe()) _exit(85);
 char line[192];
 int n=snprintf(line,sizeof(line),
  "M0A2_LAUNCH case=%d slot=%u child_slot=%u stage=%s saved_errno=%d exit=85 cleanup=unknown\n",
  index,slot,child_slot,stage,saved_errno);
 if(n>0 && n<(int)sizeof(line)) (void)write(2,line,(size_t)n);
 _exit(85);
}
static int leaf_ack_fd(int fd,int index,unsigned slot) {
 /* leaf(vector 5,slot 2) alone launches the fixed descendant slot 4. */
 return fd==20+(int)slot ||
        (slot==2 && fd==20+4 && definition_at(index).vector==5);
}
static pid_t launch_child(int index,unsigned slot,unsigned child_slot,int spawning) {
 int marker[2];
 /* Occupy 8 before pipe allocation without opening a new sandbox path. */
 if(dup2(2,8)<0) launch_failure(index,slot,child_slot,"dup2",errno);
 if(fcntl(8,F_SETFD,FD_CLOEXEC)<0) launch_failure(index,slot,child_slot,"fcntl8",errno);
 if(pipe(marker)<0) launch_failure(index,slot,child_slot,"pipe",errno);
 if(fcntl(marker[0],F_SETFD,FD_CLOEXEC)<0) launch_failure(index,slot,child_slot,"fcntl_read",errno);
 if(fcntl(marker[1],F_SETFD,FD_CLOEXEC)<0) launch_failure(index,slot,child_slot,"fcntl_write",errno);
 char idx[16],target[16],parent[16];
 snprintf(idx,sizeof(idx),"%d",index);snprintf(target,sizeof(target),"%u",child_slot);
 snprintf(parent,sizeof(parent),"%u",slot);
 char *args[]={image,spawning ? "S" : "L",idx,target,parent,binary_hash,NULL};
 char *env[]={"PATH=/usr/bin:/bin",NULL};
 pid_t child=-1;int error=0,spawn_rc=0;
 if(spawning) {
  posix_spawn_file_actions_t actions;
  if(posix_spawn_file_actions_init(&actions)) _exit(86);
  /* Descriptor 8 is reserved explicitly before creating the marker pipe. */
  if(posix_spawn_file_actions_adddup2(&actions,marker[1],8) ||
     posix_spawn_file_actions_addclose(&actions,marker[0])) _exit(87);
  spawn_rc=posix_spawn(&child,image,&actions,NULL,args,env);
  if(posix_spawn_file_actions_destroy(&actions)) _exit(88);
  if(spawn_rc) { error=spawn_rc;child=-1; }
 } else {
  errno=0;child=fork();error=child<0 ? errno : 0;
  if(child==0) {
   if(write(marker[1],"C",1)!=1) _exit(89);
   alarm(10);
   char go=0;
   if(all_read(20+(int)child_slot,&go,1) || go!='C') _exit(90);
   if(close(marker[0])<0 || close(marker[1])<0) _exit(91);
   for(int fd=0;fd<65536;fd++)
    if(fd!=2 && fd!=5 && !leaf_ack_fd(fd,index,child_slot) &&
       close(fd)<0 && errno!=EBADF) _exit(92);
   execve(image,args,env);_exit(93);
  }
 }
 if(close(marker[1])<0) _exit(94);
 char byte=0;ssize_t n;
 do { n=read(marker[0],&byte,1); } while(n<0 && errno==EINTR);
 if(close(marker[0])<0 || n<0 || (n==1 && byte!='C') ||
    (child>0 && n!=1) || (child<0 && n!=0)) _exit(95);
 require_ack(send_event(child>0 ? FORKED : OP,slot,child_slot,
             spawning ? SPAWN_OP : FORK_OP,child,error,(int)n),'A');
 return child;
}
static pthread_mutex_t thread_lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t thread_cond=PTHREAD_COND_INITIALIZER;
static unsigned thread_arrived,thread_release;
static void *thread_worker(void *unused) {
 (void)unused;
 if(pthread_mutex_lock(&thread_lock)) _exit(96);
 thread_arrived++;
 if(pthread_cond_broadcast(&thread_cond)) _exit(97);
 while(!thread_release) if(pthread_cond_wait(&thread_cond,&thread_lock)) _exit(98);
 if(pthread_mutex_unlock(&thread_lock)) _exit(99);
 return NULL;
}
static void thread_wave(unsigned count,unsigned total,unsigned slot) {
 pthread_t workers[3];
 if(count>3 || pthread_mutex_lock(&thread_lock)) _exit(100);
 thread_arrived=thread_release=0;
 if(pthread_mutex_unlock(&thread_lock)) _exit(101);
 for(unsigned i=0;i<count;i++) if(pthread_create(&workers[i],NULL,thread_worker,NULL)) _exit(102);
 if(pthread_mutex_lock(&thread_lock)) _exit(103);
 while(thread_arrived!=count) if(pthread_cond_wait(&thread_cond,&thread_lock)) _exit(104);
 require_ack(send_event(THREADS,slot,total,0,count+1,0,(int)count),'A');
 thread_release=1;
 if(pthread_cond_broadcast(&thread_cond) || pthread_mutex_unlock(&thread_lock)) _exit(105);
 for(unsigned i=0;i<count;i++) if(pthread_join(workers[i],NULL)) _exit(106);
}
static void finished(unsigned slot,pid_t *children,unsigned *slots,unsigned count) {
 require_ack(send_event(FINISH,slot,0,0,count,0,0),'A');
 for(unsigned i=0;i<count;i++) if(children[i]>0) wait_child(children[i],slot,slots[i]);
 require_ack(send_event(DONE,slot,0,0,0,0,0),'A');
 _exit(0);
}
static void leaf(int index,unsigned slot,unsigned parent_slot) {
 struct definition c=definition_at(index);
 if(protected_image(binary_hash) || m0_process_credentials(getuid()) || canaries(c.profile)) _exit(107);
 char answer=send_event(START,slot,parent_slot,0,0,0,canary_errno);
 if(c.vector==5 && slot==2) {
  require_ack(answer,'A');
  pid_t children[1]={launch_child(index,slot,4,0)};unsigned slots[1]={4};
  finished(slot,children,slots,children[0]>0 ? 1 : 0);
 }
 if(answer!='X') {
  require_ack(answer,'H');char finish=0;
  if(all_read(20+(int)slot,&finish,1) || finish!='X') _exit(108);
 }
 _exit(0);
}
static void limit_change(unsigned slot,unsigned op,rlim_t current,rlim_t maximum) {
 struct rlimit desired={current,maximum};errno=0;
 int rc=setrlimit(RLIMIT_NPROC,&desired);int error=rc<0 ? errno : 0;
 require_ack(send_event(OP,slot,0,op,rc,error,0),'A');
}
static void payload(int index,unsigned slot) {
 struct definition c=definition_at(index);
 if(protected_image(binary_hash) || m0_process_credentials(getuid()) || canaries(c.profile)) _exit(109);
 require_ack(send_event(START,slot,0,0,0,0,canary_errno),'A');
 pid_t children[3]={0};unsigned slots[3]={0};unsigned count=0;
 if(c.vector==11) finished(slot,children,slots,0);
 if(c.vector==6) { thread_wave(3,3,slot);thread_wave(1,4,slot); }
 if(c.vector==8 && c.quota) {
  limit_change(slot,LOWER,1,2);
  pid_t unexpected=launch_child(index,slot,2,0);
  if(unexpected>0) { children[count]=unexpected;slots[count++]=2; }
  limit_change(slot,RESTORE,2,2);
 } else if(c.vector==9 && c.quota) limit_change(slot,RAISE,3,3);
 unsigned first=c.vector==8 && c.quota ? 4 : slot==0 ? 2 : 3;
 if(c.vector==1 || c.vector==2 || c.vector==6 || c.vector==8 || c.vector==9 ||
    (c.vector==10 && c.shared)) {
  pid_t p=launch_child(index,slot,first,c.vector==2);
  if(p>0) { children[count]=p;slots[count++]=first; }
 } else {
  pid_t first_pid=launch_child(index,slot,first,0);
  if(first_pid<=0) _exit(110);
  if(c.vector==4) {
   wait_child(first_pid,slot,first);
   unsigned next=slot==0 ? 4 : 5;
   pid_t p=launch_child(index,slot,next,0);
   if(p<=0) _exit(111);
   wait_child(p,slot,next);
  } else if(c.vector==7) {
   siginfo_t information;memset(&information,0,sizeof(information));errno=0;
   int rc=waitid(P_PID,(id_t)first_pid,&information,WEXITED|WNOWAIT);
   int error=rc<0 ? errno : 0;
   require_ack(send_event(ZOMBIE,slot,first,0,rc,error,information.si_pid),'A');
   unsigned next=4;
   pid_t p=launch_child(index,slot,next,0);
   if(p>0) { children[count]=p;slots[count++]=next; }
   wait_child(first_pid,slot,first);
   p=launch_child(index,slot,6,0);
   if(p<=0) _exit(112);
   children[count]=p;slots[count++]=6;
  } else {
   children[count]=first_pid;slots[count++]=first;
   if(c.vector==3 || c.vector==10) {
    unsigned next=slot==0 ? 4 : 5;
    pid_t p=launch_child(index,slot,next,0);
    if(p>0) { children[count]=p;slots[count++]=next; }
   }
  }
 }
 finished(slot,children,slots,count);
}
static void worker(int index,unsigned slot,uid_t uid,int gate_stage) {
 struct definition c=definition_at(index);
 if(protected_image(binary_hash)) _exit(113);
 if(!gate_stage) {
  struct rlimit cpu={2,2},files={65536,65536},actual;
  if(setrlimit(RLIMIT_CPU,&cpu)<0 || setrlimit(RLIMIT_FSIZE,&files)<0 ||
     getrlimit(RLIMIT_CPU,&actual)<0 || actual.rlim_cur!=2 || actual.rlim_max!=2 ||
     getrlimit(RLIMIT_FSIZE,&actual)<0 || actual.rlim_cur!=65536 || actual.rlim_max!=65536) _exit(114);
  gid_t gid=(gid_t)uid;
  if(m0_apply_limit((rlim_t)c.cap,c.quota) || setgroups(1,&gid)<0 ||
     setgid(gid)<0 || setuid(uid)<0 || m0_process_credentials(uid) ||
     m0_check_limit((rlim_t)c.cap,c.quota)) _exit(115);
  status_event(CONFIG,slot,0);
  char idx[16],position[16],identity[16],profile[PATH_MAX];
  snprintf(idx,sizeof(idx),"%d",index);snprintf(position,sizeof(position),"%u",slot);
  snprintf(identity,sizeof(identity),"%u",uid);
  char *env[]={"PATH=/usr/bin:/bin",NULL};
  char *args[]={image,"G",idx,position,identity,binary_hash,NULL};
  if(!c.profile) { execve(image,args,env);_exit(116); }
  if(snprintf(profile,sizeof(profile),"%s/profile.sb",directory)>=(int)sizeof(profile)) _exit(117);
  char *sandbox_args[]={"/usr/bin/sandbox-exec","-f",profile,image,"G",idx,position,identity,binary_hash,NULL};
  execve("/usr/bin/sandbox-exec",sandbox_args,env);_exit(118);
 }
 if(m0_process_credentials(uid) || m0_check_limit((rlim_t)c.cap,c.quota) || canaries(c.profile)) _exit(119);
 status_event(READY,slot,0);
 char release=0;
 if(all_read(4,&release,1) || release!='R' || close(4)<0 ||
    fcntl(3,F_SETFD,FD_CLOEXEC)<0) _exit(120);
 char idx[16],position[16],identity[16];
 snprintf(idx,sizeof(idx),"%d",index);snprintf(position,sizeof(position),"%u",slot);
 snprintf(identity,sizeof(identity),"%u",uid);
 char *args[]={image,"P",idx,position,identity,binary_hash,NULL};
 char *env[]={"PATH=/usr/bin:/bin",NULL};
 execve(image,args,env);_exit(121);
}
static int enter_attempt(unsigned *consumed) {
 if(*consumed) return EPERM;
 *consumed=1;return 0;
}
static int packet_valid(const struct event *e) {
 return e->magic==VMAGIC && e->version==1 && e->length==sizeof(*e) && e->slot<8;
}
struct member { pid_t pid;uint64_t sec,usec;uid_t uid;int parent,started,held,finished,reaped,completed; };
static int read_data_record(int fd,void *buf,size_t n,size_t *received) {
 *received=0;
 struct pollfd p={.fd=fd,.events=POLLIN};int r;
 do { r=poll(&p,1,11000); } while(r<0 && errno==EINTR);
 if(r<=0) return r==0 ? ETIMEDOUT : errno;
 unsigned char *bytes=buf;
 while(*received<n) {
  ssize_t amount=read(fd,bytes+*received,n-*received);
  if(amount<0 && errno==EINTR) continue;
  if(amount<=0) return amount==0 ? EPIPE : errno;
  *received+=(size_t)amount;
 }
 return 0;
}
static _Noreturn void reject_data_event(unsigned index,unsigned event_count,const char *reason,
                                       int read_result,size_t received,int last_kind,int last_slot) {
 if(!block_diagnostic_sigpipe()) {
  for(unsigned i=0;i<2;i++) if(owned[i]>0) (void)kill((pid_t)owned[i],SIGKILL);
  _exit(2);
 }
 char line[256];
 int n=snprintf(line,sizeof(line),
  "M0A2_DATA case=%u event_count=%u reason=%s read_result=%d received=%zu last_kind=%d last_slot=%d cleanup=unknown\n",
  index,event_count,reason,read_result,received,last_kind,last_slot);
 if(n>0 && n<(int)sizeof(line)) (void)write(2,line,(size_t)n);
 errno=read_result>0 ? read_result : EPROTO;
 die("data-event-contract");_exit(2);
}
static void next_data_event(int fd,struct event *e,struct member members[8],unsigned index,
                            unsigned *event_count,int last_kind,int last_slot) {
 size_t received=0;
 if(++*event_count>64) reject_data_event(index,*event_count,"count",-1,0,last_kind,last_slot);
 int result=read_data_record(fd,e,sizeof(*e),&received);
 if(result) reject_data_event(index,*event_count,"read",result,received,last_kind,last_slot);
 /* No field access above: an incomplete packet is never interpreted. */
 if(!packet_valid(e))
  reject_data_event(index,*event_count,e->slot>=8 ? "slot" : "packet",0,received,last_kind,last_slot);
 if(e->kind<START || e->kind>DONE)
  reject_data_event(index,*event_count,"kind",0,received,last_kind,last_slot);
 /* packet_valid has proved slot<8; only now may members be indexed. */
 if(!members[e->slot].pid)
  reject_data_event(index,*event_count,"member",0,received,last_kind,last_slot);
}
static void identify(struct member *m,pid_t pid,uid_t uid,int parent) {
 struct proc_bsdinfo b;
 if(proc_pidinfo(pid,PROC_PIDTBSDINFO,0,&b,sizeof(b))!=(int)sizeof(b) ||
    b.pbi_pid!=(uint32_t)pid) die("register-member-PID-start");
 *m=(struct member){.pid=pid,.sec=b.pbi_start_tvsec,.usec=b.pbi_start_tvusec,.uid=uid,.parent=parent};
}
static void acknowledgement(int ack[8][2],unsigned slot,char value) {
 if(slot>=8 || all_write(ack[slot][1],&value,1)) die("member-ack");
}
static void ledger_row(int fd,const char *row,int n) {
 if(n<=0 || n>=4096 || all_write(fd,row,(size_t)n) || fsync(fd)<0) die("bounded-ledger-row");
}
static void record_event(int ledger,const struct event *e,struct member members[8],
                         const struct definition *c,unsigned case_index) {
 struct member *m=&members[e->slot];struct proc_bsdinfo b;
 if(m->pid!=e->pid || proc_pidinfo(e->pid,PROC_PIDTBSDINFO,0,&b,sizeof(b))!=(int)sizeof(b) ||
    b.pbi_pid!=(uint32_t)e->pid || b.pbi_start_tvsec!=m->sec || b.pbi_start_tvusec!=m->usec ||
    b.pbi_ppid!=(uint32_t)m->parent) die("event-live-PID-start-parent");
 int credential=c->vector==12 ? b.pbi_ruid==0 && b.pbi_uid==0 && b.pbi_svuid==0 :
    b.pbi_ruid==m->uid && b.pbi_uid==m->uid && b.pbi_svuid==m->uid &&
    b.pbi_rgid==m->uid && b.pbi_gid==m->uid && b.pbi_svgid==m->uid;
 int count=c->vector==12 ? -1 : process_count(m->uid);
 if(!credential || (c->vector!=12 && (count<0 || count>8 || e->uid!=(int32_t)m->uid ||
    e->euid!=(int32_t)m->uid || e->gid!=(int32_t)m->uid || e->egid!=(int32_t)m->uid ||
    e->count!=1 || e->read!=1 || e->group!=m->uid || e->predicate))) die("independent-credential-snapshot");
 if(c->vector!=12 && (e->kind==CONFIG || e->kind==READY) &&
    count!=(c->shared ? (int)e->slot+1 : 1)) die("pre-release-UID-count");
 if(c->vector!=12 && e->kind==START && e->slot<(unsigned)c->roots &&
    count!=(c->shared ? c->roots : 1)) die("initial-UID-count");
 int threads=-1,zombie=-1;
 if(e->kind==THREADS) {
  struct proc_taskinfo task;
  if(proc_pidinfo(e->pid,PROC_PIDTASKINFO,0,&task,sizeof(task))!=(int)sizeof(task)) die("thread-snapshot");
  threads=task.pti_threadnum;
  if(threads<1 || threads>4) die("thread-budget");
 }
 if(e->kind==ZOMBIE) {
  if(e->other>=8 || !members[e->other].pid || e->aux!=members[e->other].pid) die("zombie-owned-PID");
  struct member *z=&members[e->other];struct kinfo_proc info;memset(&info,0,sizeof(info));
  size_t size=sizeof(info);int mib[]={CTL_KERN,KERN_PROC,KERN_PROC_PID,z->pid};
  if(sysctl(mib,4,&info,&size,NULL,0)<0 || size!=sizeof(info) ||
     info.kp_proc.p_pid!=z->pid || info.kp_proc.p_starttime.tv_sec!=(time_t)z->sec ||
     info.kp_proc.p_starttime.tv_usec!=(suseconds_t)z->usec) die("zombie-start-snapshot");
  zombie=info.kp_proc.p_stat;
 }
 char row[4096];
 int n=snprintf(row,sizeof(row),
  "{\"kind\":\"event\",\"version\":1,\"case_index\":%u,\"event\":%u,\"slot\":%u,\"other\":%u,"
  "\"op\":%u,\"pid\":%d,\"ppid\":%d,\"start_sec\":%" PRIu64 ",\"start_usec\":%" PRIu64 ","
  "\"uid\":%d,\"euid\":%d,\"gid\":%d,\"egid\":%d,\"saved_uid\":%u,\"saved_gid\":%u,"
  "\"count\":%d,\"read\":%d,\"group\":%" PRIu64 ",\"predicate\":%d,"
  "\"current\":%" PRIu64 ",\"maximum\":%" PRIu64 ",\"rc\":%" PRId64 ",\"error\":%d,\"aux\":%d,"
  "\"independent_credentials\":%d,\"live_count\":%d,\"threads\":%d,\"zombie_state\":%d,\"fd3_errno\":%d,\"fd4_errno\":%d,\"canary_error\":%d,\"canary_allowed\":%d}\n",
  case_index,e->kind,e->slot,e->other,e->op,e->pid,e->ppid,m->sec,m->usec,
  e->uid,e->euid,e->gid,e->egid,b.pbi_svuid,b.pbi_svgid,e->count,e->read,e->group,e->predicate,
  e->current,e->maximum,e->rc,e->error,e->aux,credential,count,threads,zombie,e->fd3_errno,e->fd4_errno,e->canary_error,e->canary_allowed);
 ledger_row(ledger,row,n);
}
static int register_exec(pid_t pid) {
 int kq=kqueue();struct kevent change,receipt;struct timespec zero={0,0};
 EV_SET(&change,pid,EVFILT_PROC,EV_ADD|EV_ENABLE|EV_CLEAR|EV_RECEIPT,NOTE_EXEC|NOTE_EXIT,0,NULL);
 if(kq<0 || kevent(kq,&change,1,&receipt,1,&zero)!=1 ||
    !(receipt.flags&EV_ERROR) || receipt.data!=0) die("new-exec-registration");
 return kq;
}
static void see_exec(int kq,pid_t pid) {
 struct kevent e;struct timespec timeout={1,0};int n;
 do { n=kevent(kq,NULL,0,&e,1,&timeout); } while(n<0 && errno==EINTR);
 if(n!=1 || (e.flags&EV_ERROR) || e.ident!=(uintptr_t)pid || !(e.fflags&NOTE_EXEC)) die("actual-payload-exec");
}
static int wait_root(unsigned slot,pid_t pid,int *status) {
 sigset_t mask,old;sigemptyset(&mask);sigaddset(&mask,SIGALRM);
 for(unsigned attempt=0;attempt<100;attempt++) {
  if(sigprocmask(SIG_BLOCK,&mask,&old)<0) return -1;
  pid_t result=waitpid(pid,status,WNOHANG);int saved=errno;
  if(result==pid || (result<0 && saved==ECHILD)) owned[slot]=0;
  if(sigprocmask(SIG_SETMASK,&old,NULL)<0) return -1;
  if(result==pid) return 0;
  if(result<0 && saved!=EINTR) { errno=saved;return -1; }
  (void)usleep(10000);
 }
 errno=ETIMEDOUT;return -1;
}
static void root_child(int index,unsigned slot,uid_t uid,int status[2],int release[2],
                       int data[2],int ack[8][2]) {
 owned[0]=owned[1]=0;alarm(10);
 if(dup2(status[1],3)<0 || dup2(release[0],4)<0 || dup2(data[1],5)<0) _exit(122);
 for(unsigned i=0;i<8;i++) if(dup2(ack[i][0],20+(int)i)<0) _exit(123);
 for(int fd=6;fd<65536;fd++)
  if((fd<20 || fd>27) && close(fd)<0 && errno!=EBADF) _exit(124);
 int null=open("/dev/null",O_RDWR);
 if(null<0 || dup2(null,0)<0 || dup2(null,1)<0) _exit(125);
 if(null>5 && close(null)<0) _exit(126);
 for(int sig=1;sig<NSIG;sig++) if(sig!=SIGKILL && sig!=SIGSTOP &&
    signal(sig,SIG_DFL)==SIG_ERR) _exit(127);
 sigset_t empty;sigemptyset(&empty);
 if(sigprocmask(SIG_SETMASK,&empty,NULL)<0) _exit(128);
 alarm(10);char start=0;
 if(all_read(4,&start,1) || start!='A') _exit(129);
 char idx[16],position[16],identity[16];
 snprintf(idx,sizeof(idx),"%d",index);snprintf(position,sizeof(position),"%u",slot);
 snprintf(identity,sizeof(identity),"%u",uid);
 struct definition c=definition_at(index);
 char *args[]={image,c.vector==12 ? "R" : "T",idx,position,identity,binary_hash,NULL};
 char *env[]={"PATH=/usr/bin:/bin",NULL};
 execve(image,args,env);_exit(130);
}
static void run_case(int index,int ledger,int leases,const char *os,const char *kernel,const char *arch) {
 struct definition c=definition_at(index);
 uid_t ids[2]={0,0};
 if(c.vector!=12) {
  ids[0]=reserve_unused_id(leases);
  if(c.roots==2) ids[1]=c.shared ? ids[0] : reserve_unused_id(leases);
 }
 int data[2],ack[8][2],status[2][2],release[2][2],kq[2]={-1,-1};
 if(pipe(data)<0) die("data-pipe");
 for(unsigned i=0;i<8;i++) if(pipe(ack[i])<0) die("ack-pipe");
 struct member members[8];memset(members,0,sizeof(members));
 char profile_path[PATH_MAX],profile_hash[65];
 if(snprintf(profile_path,sizeof(profile_path),"%s/profile.sb",directory)>=(int)sizeof(profile_path)) die("profile-path");
 int pf=open(profile_path,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
 if(pf<0 || hash_fd(pf,profile_hash,4096) || close(pf)<0) die("profile-digest");
 struct proc_bsdinfo observer;
 if(proc_pidinfo(getpid(),PROC_PIDTBSDINFO,0,&observer,sizeof(observer))!=(int)sizeof(observer) ||
    observer.pbi_pid!=(uint32_t)getpid() || observer.pbi_ruid!=0 || observer.pbi_uid!=0 ||
    observer.pbi_svuid!=0) die("observer-PID-start");
 char row[4096];
 int n=snprintf(row,sizeof(row),
  "{\"kind\":\"begin\",\"version\":1,\"candidate_sha\":\"%s\",\"variant\":\"%s\","
  "\"binary_sha256\":\"%s\",\"profile_sha256\":\"%s\",\"sandbox_exec_sha256\":\"%s\","
  "\"case_index\":%d,\"case\":\"%s\",\"vector\":%d,\"quota\":%d,\"profile\":%d,\"cap\":%d,"
  "\"roots\":%d,\"shared\":%d,\"uid0\":%u,\"uid1\":%u,\"observer_pid\":%d,\"observer_uid\":%u,"
  "\"observer_start_sec\":%" PRIu64 ",\"observer_start_usec\":%" PRIu64 ",\"deadline_ns\":%" PRIu64 ","
  "\"arch\":\"%s\",\"os_build\":\"%s\",\"kernel\":\"%s\"}\n",
  candidate,m0_variant(),binary_hash,profile_hash,sandbox_hash,index,c.name,c.vector,c.quota,c.profile,
  c.cap,c.roots,c.shared,ids[0],ids[1],getpid(),getuid(),observer.pbi_start_tvsec,
  observer.pbi_start_tvusec,experiment_deadline,arch,os,kernel);
 ledger_row(ledger,row,n);
 unsigned consumed=0;
 for(unsigned root=0;root<(unsigned)c.roots;root++) {
  if(c.vector==11 && (root==0 || !c.shared) && enter_attempt(&consumed)) die("first-attempt-rejected");
  if(pipe(status[root])<0 || pipe(release[root])<0) die("root-pipes");
  pid_t pid=fork();
  if(pid<0) die("root-fork");
  if(pid==0) root_child(index,root,ids[root],status[root],release[root],data,ack);
  owned[root]=pid;identify(&members[root],pid,ids[root],getpid());
  close(status[root][1]);close(release[root][0]);
  if(c.vector==12) kq[root]=register_exec(pid);
  if(all_write(release[root][1],"A",1)) die("initial-A");
  if(c.vector==12) { close(status[root][0]);close(release[root][1]);continue; }
  struct event configured,ready;
  if(read_record(status[root][0],&configured,sizeof(configured)) ||
     read_record(status[root][0],&ready,sizeof(ready)) ||
     !packet_valid(&configured) || !packet_valid(&ready) ||
     configured.kind!=CONFIG || ready.kind!=READY || configured.slot!=root || ready.slot!=root ||
     configured.pid!=pid || ready.pid!=pid || configured.error || ready.error ||
     configured.uid!=(int32_t)ids[root] || ready.uid!=(int32_t)ids[root] ||
     configured.predicate || ready.predicate || configured.count!=1 || configured.read!=1 ||
     ready.count!=1 || ready.read!=1 || ready.group!=ids[root] || configured.group!=ids[root])
   die("configured-ready-contract");
  if(c.quota && strcmp(m0_variant(),"baseline") &&
     (configured.current!=(uint64_t)c.cap || configured.maximum!=(uint64_t)c.cap ||
      ready.current!=(uint64_t)c.cap || ready.maximum!=(uint64_t)c.cap)) die("exact-limits-before-release");
  record_event(ledger,&configured,members,&c,(unsigned)index);
  record_event(ledger,&ready,members,&c,(unsigned)index);
  kq[root]=register_exec(pid); /* Fresh after READY: cannot credit T/G exec. */
  if(all_write(release[root][1],"R",1) || close(release[root][1])<0) die("release-R");
  if(close(status[root][0])<0) die("status-reader-close");
 }
 if(c.vector==11 && !c.shared) {
  int error=enter_attempt(&consumed);
  if(error!=EPERM) die("replay-admission-was-not-rejected");
  n=snprintf(row,sizeof(row),"{\"kind\":\"admission\",\"version\":1,\"case_index\":%d,\"observer_uid\":%u,\"consumed\":%u,\"error\":%d,\"second_forked\":0}\n",index,getuid(),consumed,error);
  ledger_row(ledger,row,n);
 }
 close(data[1]);for(unsigned i=0;i<8;i++) close(ack[i][0]);
 unsigned root_started=0,finished_count=0,done=0;
 int all_finished=0;unsigned event_count=0;int last_kind=-1,last_slot=-1;
 while(done<(unsigned)c.roots) {
  struct event e;
  next_data_event(data[0],&e,members,(unsigned)index,&event_count,last_kind,last_slot);
  record_event(ledger,&e,members,&c,(unsigned)index);
  last_kind=(int)e.kind;last_slot=(int)e.slot;
  if(e.kind==FORKED) {
   if(e.other>=8 || members[e.other].pid || e.rc<=0 || e.rc>INT_MAX || e.error || e.aux!=1) die("fork-registration");
   identify(&members[e.other],(pid_t)e.rc,members[e.slot].uid,e.pid);
   acknowledgement(ack,e.other,'C');acknowledgement(ack,e.slot,'A');
  } else if(e.kind==START) {
   if(members[e.slot].started) die("duplicate-start");
   members[e.slot].started=1;
   if(e.slot<(unsigned)c.roots) {
    see_exec(kq[e.slot],e.pid);root_started++;
    if(root_started==(unsigned)c.roots)
     for(unsigned root=0;root<(unsigned)c.roots;root++) acknowledgement(ack,root,'A');
   } else {
    int immediate=c.vector==4 || (c.vector==7 && e.slot==2) || all_finished;
    int grandparent=c.vector==5 && e.slot==2;
    acknowledgement(ack,e.slot,immediate ? 'X' : grandparent ? 'A' : 'H');
    members[e.slot].held=!immediate && !grandparent;
   }
  } else if(e.kind==FINISH) {
   if(members[e.slot].finished) die("duplicate-finish");
   members[e.slot].finished=1;finished_count++;
   unsigned required=(unsigned)c.roots+(c.vector==5 ? 1u : 0u);
   if(finished_count==required) {
    all_finished=1;
    for(unsigned i=0;i<8;i++) if(members[i].held) {
     acknowledgement(ack,i,'X');members[i].held=0;
    }
    for(unsigned i=0;i<8;i++) if(members[i].finished) acknowledgement(ack,i,'A');
   }
  } else if(e.kind==DONE) {
   if(!all_finished || !members[e.slot].finished || members[e.slot].completed) die("premature-done");
   members[e.slot].completed=1;
   if(e.slot<(unsigned)c.roots) done++;
   acknowledgement(ack,e.slot,'A');
  } else {
   if(e.kind==REAPED) {
    if(e.other>=8 || members[e.other].pid!=e.rc || members[e.other].parent!=e.pid ||
       members[e.other].reaped || e.error || e.aux) die("owned-reap-contract");
    members[e.other].reaped=1;
   }
   acknowledgement(ack,e.slot,'A');
  }
 }
 for(unsigned root=0;root<(unsigned)c.roots;root++) {
  int wait_status=0;
  if(wait_root(root,members[root].pid,&wait_status)<0 || !WIFEXITED(wait_status) ||
     WEXITSTATUS(wait_status)) die("owned-root-wait");
  members[root].reaped=1;
  if(close(kq[root])<0) die("kqueue-close");
 }
 for(unsigned i=0;i<8;i++) if(members[i].pid && !members[i].reaped) die("unreaped-member");
 if(c.vector!=12 && (process_count(ids[0])!=0 || supplementary_free(ids[0])!=1 ||
    (c.roots==2 && (process_count(ids[1])!=0 || supplementary_free(ids[1])!=1)))) die("retained-identity-unknown");
 char extra=0;
 if(read(data[0],&extra,1)!=0 || close(data[0])<0) die("data-tail");
 for(unsigned i=0;i<8;i++) if(close(ack[i][1])<0) die("ack-close");
 n=snprintf(row,sizeof(row),
  "{\"kind\":\"end\",\"version\":1,\"case_index\":%d,\"events\":%u,\"roots_reaped\":%d,"
  "\"remaining\":0,\"cleanup_scope\":\"owned_roots_and_observed_direct_parent_reaps\",\"retained\":true}\n",
  index,event_count+(c.vector==12 ? 0u : 2u*(unsigned)c.roots),c.roots);
 ledger_row(ledger,row,n);
}
static void root_calibration(unsigned slot) {
 if(protected_image(binary_hash) || getuid()!=0 || geteuid()!=0) _exit(131);
 struct rlimit cpu={2,2},files={65536,65536},actual;
 if(setrlimit(RLIMIT_CPU,&cpu)<0 || setrlimit(RLIMIT_FSIZE,&files)<0 ||
    getrlimit(RLIMIT_CPU,&actual)<0 || actual.rlim_cur!=2 || actual.rlim_max!=2 ||
    getrlimit(RLIMIT_FSIZE,&actual)<0 || actual.rlim_cur!=65536 || actual.rlim_max!=65536) _exit(132);
 require_ack(send_event(START,slot,0,0,0,0,0),'A');
 limit_change(slot,CALIBRATE,3,3);
 pid_t none[1]={0};unsigned slots[1]={0};finished(slot,none,slots,0);
}
int main(int argc,char **argv) {
 if(argc==6 && !strcmp(argv[1],"S")) {
  if(write(8,"C",1)!=1) _exit(137);
  alarm(10);
 }
 self_path();
 if(argc==6 && (!strcmp(argv[1],"T") || !strcmp(argv[1],"G") || !strcmp(argv[1],"P") || !strcmp(argv[1],"R"))) {
  int index=numeric(argv[2],0,!strcmp(m0_variant(),"baseline") ? 1 : 23);
  unsigned slot=(unsigned)numeric(argv[3],0,1);
  uid_t uid=(uid_t)numeric(argv[4],0,UID_FIRST+UID_COUNT-1);
  if(!hex_string(argv[5],64)) _exit(133);
  strcpy(binary_hash,argv[5]);struct definition c=definition_at(index);
  if(c.vector==12) {
   if(strcmp(argv[1],"R") || uid!=0) _exit(134);
   root_calibration(slot);
  }
  if(uid<UID_FIRST) _exit(135);
  if(!strcmp(argv[1],"T")) worker(index,slot,uid,0);
  if(!strcmp(argv[1],"G")) worker(index,slot,uid,1);
  if(strcmp(argv[1],"P") || getuid()!=uid) _exit(136);
  payload(index,slot);return 2;
 }
 if(argc==6 && (!strcmp(argv[1],"L") || !strcmp(argv[1],"S"))) {
  /* Spawn's first external action is the byte; fork already wrote it before exec. */
  /* Marker already written before self_path above. */
  int index=numeric(argv[2],0,!strcmp(m0_variant(),"baseline") ? 1 : 23);
  unsigned slot=(unsigned)numeric(argv[3],2,7),parent=(unsigned)numeric(argv[4],0,7);
  if(!hex_string(argv[5],64)) _exit(138);
  strcpy(binary_hash,argv[5]);
  if(argv[1][0]=='S') {
   alarm(10);char go=0;
   if(all_read(20+(int)slot,&go,1) || go!='C' || close(8)<0) _exit(139);
  }
  for(int fd=0;fd<65536;fd++)
   if(fd!=2 && fd!=5 && !leaf_ack_fd(fd,index,slot) &&
      close(fd)<0 && errno!=EBADF) _exit(140);
  leaf(index,slot,parent);return 2;
 }
 if(argc!=4 || getuid()!=0 || geteuid()!=0 || !hex_string(argv[1],40) || !hex_string(argv[2],64)) die("root-fixed-arguments");
 candidate=argv[1];parse_deadline(argv[3]);umask(077);
 if(signal(SIGALRM,expire)==SIG_ERR || signal(SIGPIPE,SIG_IGN)==SIG_ERR) die("root-signals");
 alarm(remaining_seconds());
 struct rlimit cpu={20,20},actual;
 if(setrlimit(RLIMIT_CPU,&cpu)<0 || getrlimit(RLIMIT_CPU,&actual)<0 ||
    actual.rlim_cur!=20 || actual.rlim_max!=20) die("observer-cpu20-readback");
 for(int fd=3;fd<32;fd++) if(open("/dev/null",O_RDWR|O_CLOEXEC)!=fd) die("reserved-FD-layout");
 struct utsname u;char os[64];size_t os_size=sizeof(os);
 if(uname(&u)<0 || sysctlbyname("kern.osversion",os,&os_size,NULL,0)<0 ||
    os_size<2 || os_size>sizeof(os) || os[os_size-1]!=0 ||
    (strcmp(u.machine,"arm64") && strcmp(u.machine,"x86_64"))) die("native-OS");
 for(const char *s=os;*s;s++) if(!((*s>='0' && *s<='9') || (*s>='A' && *s<='Z') ||
    (*s>='a' && *s<='z'))) die("OS-build-format");
 for(const char *s=u.release;*s;s++) if(!((*s>='0' && *s<='9') || *s=='.')) die("kernel-format");
 int translated=-1;size_t translation_size=sizeof(translated);errno=0;
 int query=sysctlbyname("sysctl.proc_translated",&translated,&translation_size,NULL,0);
 if(!((query==0 && translation_size==sizeof(translated) && translated==0) ||
      (query<0 && errno==ENOENT))) die("translation-or-unknown");
 if(secure_chain("/usr/bin/sandbox-exec")) die("system-seatbelt-chain");
 int system=open("/usr/bin/sandbox-exec",O_RDONLY|O_CLOEXEC|O_NOFOLLOW);struct stat st;
 if(system<0 || fstat(system,&st)<0 || !S_ISREG(st.st_mode) || !(st.st_mode&0111) ||
    (st.st_mode&(S_ISUID|S_ISGID)) || hash_fd(system,sandbox_hash,MAX_IMAGE) || close(system)<0) die("system-seatbelt-image");
 prepare_image(argv[2]);directory_accounts();int leases=lease_directory();
 char path[PATH_MAX];
 if(snprintf(path,sizeof(path),"%s/vectors.jsonl",directory)>=(int)sizeof(path)) die("ledger-path");
 int ledger=open(path,O_RDWR|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
 if(ledger<0) die("ledger-open");
 unsigned count=!strcmp(m0_variant(),"baseline") ? 2u : 24u;
 for(unsigned i=0;i<count;i++) {
  unsigned remaining=remaining_seconds();
  alarm(remaining<15 ? remaining : 15);
  off_t before=lseek(ledger,0,SEEK_CUR);
  if(before<0) die("case-position");
  run_case((int)i,ledger,leases,os,u.release,u.machine);
  off_t after=lseek(ledger,0,SEEK_CUR);
  if(after<before || after-before>65536) die("case-evidence-bound");
 }
 (void)remaining_seconds();
 char digest[65];
 if(hash_fd(ledger,digest,2*1024*1024) || fchmod(ledger,0444)<0 || fsync(ledger)<0 ||
    close(ledger)<0 || close(leases)<0) die("ledger-seal");
 printf("{\"version\":1,\"root_directory\":\"%s\",\"ledger_sha256\":\"%s\",\"cases\":%u}\n",directory,digest,count);
 if(fflush(stdout)==EOF) die("manifest-write");
 alarm(0);return 0;
}
