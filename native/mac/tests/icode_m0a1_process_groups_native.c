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
#include "icode_m0a1_unused_identity.inc"
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
