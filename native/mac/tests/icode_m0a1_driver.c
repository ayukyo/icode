#define _DARWIN_C_SOURCE 1
#include "icode_m0a1_limit.h"
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
#include <pwd.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/acl.h>
#include <sys/event.h>
#include <sys/stat.h>
#include <sys/sysctl.h>
#include <sys/utsname.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

enum { UID_FIRST=60000, UID_COUNT=1024, MAX_PIDS=8192,
       MAX_IMAGE=16*1024*1024, MAGIC=0x4d304131, CONFIGURED=1,
       SANDBOXED=2, FAILED=3 };
struct gate_record {
    uint32_t magic,version,length,phase;
    int32_t error,pid;
    uint32_t uid,euid,gid,egid,groups,group;
    uint64_t current,maximum;
    int32_t canary_errno,canary_allowed;
};
struct payload_record {
    uint32_t magic,version,length,pid,uid,euid,gid,egid;
    int32_t fd3_errno,fd4_errno,recover_uid_errno,recover_gid_errno;
    int32_t fork_pid,fork_errno,child_byte,entered,groups,group;
    uint64_t current,maximum;
    int32_t canary_errno,canary_allowed;
};
_Static_assert(sizeof(struct gate_record)==72,"gate ABI changed");
_Static_assert(sizeof(struct payload_record)==96,"payload ABI changed");
struct case_def { const char *name; int quota,sandbox,fault; };
static const struct case_def cases[]={
    {"cap1_fork",1,1,0},{"control_fork",0,1,0},
    {"seatbelt_positive",0,0,0},{"profile_error",1,1,1},
    {"release_eof",1,1,2},{"exec_error",1,1,3},{"receipt_loss",1,1,4}
};
static volatile sig_atomic_t owned_child;
static const char lease_root[]="/private/var/icode-m0a1-leases";
static const char owner_text[]="ICODE-M0A1-v1\n";
static char image[PATH_MAX],directory[PATH_MAX],binary_hash[65],sandbox_hash[65];
static unsigned char unavailable[UID_COUNT];
static int canary_errno=-1,canary_allowed;
static void expire(int sig) {
    (void)sig;
    if(owned_child>0) (void)kill((pid_t)owned_child,SIGKILL);
    _exit(124);
}
static void die(const char *stage) {
    int e=errno ? errno : EPROTO;
    fprintf(stderr,"M0A1 infrastructure stage=%s errno=%d\n",stage,e);
    if(!strncmp(directory,"/private/var/icode-m0a1.",sizeof("/private/var/icode-m0a1.")-1))
        fprintf(stderr,"M0A1 retained directory=%s cleanup=unknown\n",directory);
    if(owned_child>0) (void)kill((pid_t)owned_child,SIGKILL);
    exit(2);
}
static int all_write(int fd,const void *buf,size_t n) {
    const unsigned char *p=buf;
    while(n) {
        ssize_t r=write(fd,p,n);
        if(r<0 && errno==EINTR) continue;
        if(r<=0) return errno ? errno : EIO;
        p+=r; n-=(size_t)r;
    }
    return 0;
}
static int all_read(int fd,void *buf,size_t n) {
    unsigned char *p=buf;
    while(n) {
        ssize_t r=read(fd,p,n);
        if(r<0 && errno==EINTR) continue;
        if(r<=0) return r==0 ? EPIPE : errno;
        p+=r; n-=(size_t)r;
    }
    return 0;
}
static int read_record(int fd,void *buf,size_t n) {
    struct pollfd p={.fd=fd,.events=POLLIN};
    int r;
    do { r=poll(&p,1,11000); } while(r<0 && errno==EINTR);
    if(r<=0) return r==0 ? ETIMEDOUT : errno;
    return all_read(fd,buf,n); /* Fixed writer plus child alarm bounds read. */
}
static int hex_string(const char *s,size_t n) {
    if(strlen(s)!=n) return 0;
    for(size_t i=0;i<n;i++)
        if(!((s[i]>='0' && s[i]<='9') || (s[i]>='a' && s[i]<='f'))) return 0;
    return 1;
}
static int numeric(const char *s,int low,int high) {
    char *end=NULL; errno=0; long v=strtol(s,&end,10);
    if(errno || end==s || *end || v<low || v>high) die("numeric");
    return (int)v;
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
            acl_entry_t entry; errno=0;
            int r=acl_get_entry(acl,i==0 ? ACL_FIRST_ENTRY : ACL_NEXT_ENTRY,&entry);
            if(r<0 && errno==EINVAL) break; /* Valid ACL, validated iterator exhausted. */
            if(r!=0 || i==ACL_MAX_ENTRIES) { e=EPROTO; break; }
            acl_tag_t tag; acl_permset_mask_t permissions=0;
            if(acl_get_tag_type(entry,&tag)<0 || acl_get_permset_mask_np(entry,&permissions)<0) {
                e=errno; break;
            }
            if(tag!=ACL_EXTENDED_ALLOW && tag!=ACL_EXTENDED_DENY) { e=EPROTO; break; }
            /* Conservative: no principal may gain mutation rights through an ALLOW ACE. */
            if(tag==ACL_EXTENDED_ALLOW && (permissions&~read_mask)) { e=EPERM; break; }
        }
    }
    if(acl && acl!=(acl_t)_FILESEC_REMOVE_ACL && acl_free(acl)<0 && !e) e=errno;
    filesec_free(sec);
    return e;
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
        char saved=*p; *p=0; struct stat st;
        e=getuid()==0 ? acl_safe(copy,&st) : (lstat(copy,&st)<0 ? errno : 0);
        if(e) return e;
        if(st.st_uid!=0 || (st.st_mode&022) || S_ISLNK(st.st_mode)) return EPERM;
        *p=saved; if(!saved) break;
    }
    return 0;
}
static void self_path(void) {
    char buf[PATH_MAX]; uint32_t n=sizeof(buf);
    if(_NSGetExecutablePath(buf,&n)!=0 || !realpath(buf,image)) die("self-path");
    strcpy(directory,image);
    char *slash=strrchr(directory,'/');
    if(!slash) die("self-directory");
    *slash=0;
}
static int hash_fd(int fd,char out[65],size_t bound) {
    CC_SHA256_CTX ctx; unsigned char buf[65536],digest[CC_SHA256_DIGEST_LENGTH];
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
    out[64]=0; return 0;
}
static int protected_image(const char *expected) {
    const char prefix[]="/private/var/icode-m0a1.";
    if(strncmp(directory,prefix,sizeof(prefix)-1)!=0) return EPERM;
    int e=secure_chain(image);
    if(e) return e;
    int fd=open(image,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
    if(fd<0) return errno;
    struct stat st; char digest[65];
    e=fstat(fd,&st)<0 ? errno : (!S_ISREG(st.st_mode) ? EINVAL : 0);
    if(!e) e=hash_fd(fd,digest,MAX_IMAGE);
    if(close(fd)<0 && !e) e=errno;
    if(!e && strcmp(digest,expected)) e=EPERM;
    return e;
}
static void create_file(const char *name,const void *data,size_t n,mode_t mode) {
    char path[PATH_MAX];
    if(snprintf(path,sizeof(path),"%s/%s",directory,name)>=(int)sizeof(path)) die("path");
    int fd=open(path,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    if(fd<0 || all_write(fd,data,n) || fchmod(fd,mode)<0 || fsync(fd)<0) die("create-file");
    if(close(fd)<0) die("close-file");
}
static void prepare_image(const char *expected) {
    int in=open(image,O_RDONLY|O_NOFOLLOW|O_CLOEXEC); struct stat st;
    if(in<0 || fstat(in,&st)<0 || !S_ISREG(st.st_mode) || st.st_size<=0 || st.st_size>MAX_IMAGE)
        die("source-image");
    struct mach_header_64 mh;
    if(all_read(in,&mh,sizeof(mh)) || mh.magic!=MH_MAGIC_64) die("native-Mach-O");
#if defined(__arm64__)
    if(mh.cputype!=CPU_TYPE_ARM64) die("Mach-O-arm64");
#elif defined(__x86_64__)
    if(mh.cputype!=CPU_TYPE_X86_64) die("Mach-O-x86_64");
#else
#error Unsupported native macOS architecture
#endif
    char observed[65];
    if(hash_fd(in,observed,MAX_IMAGE) || strcmp(observed,expected)) die("source-hash");
    if(secure_chain("/private/var")) die("protected-parent");
    strcpy(directory,"/private/var/icode-m0a1.XXXXXX");
    if(!mkdtemp(directory) || chmod(directory,0755)<0 || secure_chain(directory)) die("fixture-directory");
    char target[PATH_MAX];
    if(snprintf(target,sizeof(target),"%s/probe",directory)>=(int)sizeof(target)) die("copy-path");
    int out=open(target,O_RDWR|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    if(out<0 || lseek(in,0,SEEK_SET)<0) die("copy-open");
    unsigned char buf[65536]; size_t copied=0;
    for(;;) {
        ssize_t n=read(in,buf,sizeof(buf));
        if(n<0 && errno==EINTR) continue;
        if(n<0) die("copy-read");
        if(!n) break;
        if((size_t)n>MAX_IMAGE-copied || all_write(out,buf,(size_t)n)) die("copy-bound");
        copied+=(size_t)n;
    }
    if(hash_fd(out,observed,MAX_IMAGE) || strcmp(observed,expected) ||
       fchmod(out,0555)<0 || fsync(out)<0) die("protected-copy-hash");
    if(close(in)<0 || close(out)<0) die("copy-close");
    strcpy(image,target); strcpy(binary_hash,expected);
    create_file("allowed","A",1,0444); create_file("denied","D",1,0444);
    const char bad[]="(version 1)(";
    create_file("bad.sb",bad,sizeof(bad)-1,0444);
    char profile[4096];
    int n=snprintf(profile,sizeof(profile),
        "(version 1)\n(deny default)\n(allow process-exec)\n(allow process-fork)\n"
        "(allow signal (target same-sandbox))\n(allow process-info* (target same-sandbox))\n"
        "(allow sysctl-read)\n"
        "(allow file-read-metadata file-test-existence (path-ancestors \"%s\"))\n"
        "(allow file-read* file-test-existence (literal \"/\") "
        "(subpath \"/usr/lib\") (subpath \"/System/Library\") "
        "(literal \"%s\") (literal \"%s/profile.sb\") (literal \"%s/allowed\") "
        "(literal \"%s/not-created\"))\n",
        image,image,directory,directory,directory);
    if(n<=0 || n>=(int)sizeof(profile)) die("profile-bound");
    create_file("profile.sb",profile,(size_t)n,0444);
}
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
static int credentials(uid_t uid) {
    gid_t g=0;
    if(getuid()!=uid || geteuid()!=uid || getgid()!=uid || getegid()!=uid ||
       getgroups(0,NULL)!=1 || getgroups(1,&g)!=1 || g!=uid) return EPERM;
    return 0;
}
static void send_gate(unsigned phase,int error) {
    struct gate_record r; memset(&r,0,sizeof(r));
    r.magic=MAGIC; r.version=1; r.length=sizeof(r); r.phase=phase;
    r.error=error; r.pid=getpid(); r.uid=getuid(); r.euid=geteuid();
    r.gid=getgid(); r.egid=getegid(); gid_t g=0; int n=getgroups(1,&g);
    r.groups=n<0 ? UINT32_MAX : (uint32_t)n; r.group=g;
    struct rlimit l;
    if(getrlimit(RLIMIT_NPROC,&l)<0) { r.phase=FAILED; r.error=errno; }
    else { r.current=l.rlim_cur; r.maximum=l.rlim_max; }
    r.canary_errno=canary_errno; r.canary_allowed=canary_allowed;
    if(all_write(3,&r,sizeof(r))) _exit(93);
}
/* M0A1_DIAGNOSTIC_EMITTER_BEGIN */
static void emit_diagnostic(unsigned index,unsigned stage,int error,int detail,int result) {
    int saved=errno;
    char row[192];
    int n=snprintf(row,sizeof(row),
        "M0A1_DIAG version=1 case_index=%u stage=%u error=%d detail=%d result=%d\n",
        index,stage,error,detail,result);
    if(n>0 && (size_t)n<sizeof(row)) (void)fwrite(row,1,(size_t)n,stderr);
    errno=saved;
}
static void setup_fail(unsigned index,unsigned stage,int error,int detail,int code) {
    sigset_t blocked;
    /* This path must exit: never restore a mask that could deliver pending SIGPIPE. */
    if(sigemptyset(&blocked)==0 && sigaddset(&blocked,SIGPIPE)==0 &&
       sigprocmask(SIG_BLOCK,&blocked,NULL)==0)
        emit_diagnostic(index,stage,error,detail,code);
    _exit(code);
}
/* M0A1_DIAGNOSTIC_EMITTER_END */
/* M0A1_GATE_OBSERVER_BEGIN */
static void emit_gate_observation(unsigned index,unsigned slot,uint32_t expected_uid,
                                  int received,const struct gate_record *r) {
    int saved=errno;
    char row[512],group[11];
    int n;
    if(!received) {
        n=snprintf(row,sizeof(row),
            "M0A1_GATE_DIAG format_version=1 case_index=%u slot=%u received=0 "
            "raw_magic=unknown wire_version=unknown length=unknown pid=unknown "
            "phase=unknown error=unknown expected_uid=%" PRIu32 " uid=unknown euid=unknown "
            "gid=unknown egid=unknown groups=unknown group_observed=0 group=unknown\n",
            index,slot,expected_uid);
    } else {
        /* group is meaningful only when the existing wire reports one group. */
        const char *observed_group="unknown";
        if(r->groups==1) {
            int g=snprintf(group,sizeof(group),"%" PRIu32,r->group);
            if(g>0 && (size_t)g<sizeof(group)) observed_group=group;
        }
        n=snprintf(row,sizeof(row),
            "M0A1_GATE_DIAG format_version=1 case_index=%u slot=%u received=1 "
            "raw_magic=%" PRIu32 " wire_version=%" PRIu32 " length=%" PRIu32
            " pid=%" PRId32 " phase=%" PRIu32 " error=%" PRId32
            " expected_uid=%" PRIu32 " uid=%" PRIu32 " euid=%" PRIu32
            " gid=%" PRIu32 " egid=%" PRIu32 " groups=%" PRIu32
            " group_observed=%d group=%s\n",
            index,slot,r->magic,r->version,r->length,r->pid,r->phase,r->error,
            expected_uid,r->uid,r->euid,r->gid,r->egid,r->groups,
            r->groups==1,observed_group);
    }
    if(n>0 && (size_t)n<sizeof(row)) (void)fwrite(row,1,(size_t)n,stderr);
    errno=saved;
}
/* M0A1_GATE_OBSERVER_END */
static void worker_fail(int error) { send_gate(FAILED,error); _exit(94); }
static void trampoline(unsigned index,uid_t uid,const char *hash) {
    if(getuid()!=0 || protected_image(hash)) worker_fail(EPERM);
    const struct case_def *c=&cases[index]; gid_t gid=uid;
    int e=m0_apply_limit(1,c->quota);
    if(e) worker_fail(e);
    if(setgroups(1,&gid)<0 || setgid(gid)<0 || setuid(uid)<0) worker_fail(errno);
    e=credentials(uid);
    if(e) worker_fail(e);
    e=m0_check_limit(1,c->quota);
    if(e) worker_fail(e);
    send_gate(CONFIGURED,0);
    char idx[16],id[16],profile[PATH_MAX];
    snprintf(idx,sizeof(idx),"%u",index); snprintf(id,sizeof(id),"%u",uid);
    char *env[]={"PATH=/usr/bin:/bin",NULL};
    char *args[]={image,"G",idx,id,(char *)hash,NULL};
    if(!c->sandbox) { execve(image,args,env); worker_fail(errno); }
    if(snprintf(profile,sizeof(profile),"%s/%s",directory,c->fault==1 ? "bad.sb" : "profile.sb")
       >=(int)sizeof(profile)) worker_fail(ENAMETOOLONG);
    char *sandbox_args[]={"/usr/bin/sandbox-exec","-f",profile,image,"G",idx,id,(char *)hash,NULL};
    execve("/usr/bin/sandbox-exec",sandbox_args,env); worker_fail(errno);
}
static int canaries(int sandbox) {
    char path[PATH_MAX]; snprintf(path,sizeof(path),"%s/allowed",directory);
    int f=open(path,O_RDONLY|O_NOFOLLOW);
    if(f<0) return errno;
    char value=0;
    int e=all_read(f,&value,1);
    if(close(f)<0 && !e) e=errno;
    if(e || value!='A') return e ? e : EPROTO;
    canary_allowed=1;
    snprintf(path,sizeof(path),"%s/denied",directory); errno=0;
    f=open(path,O_RDONLY|O_NOFOLLOW); canary_errno=f<0 ? errno : 0;
    if(f>=0) {
        e=all_read(f,&value,1);
        if(close(f)<0 && !e) e=errno;
        if(e || value!='D') return e ? e : EPROTO;
    }
    return (sandbox && canary_errno!=EPERM && canary_errno!=EACCES) ||
           (!sandbox && canary_errno) ? EPROTO : 0;
}
static void gate(unsigned index,uid_t uid,const char *hash) {
    const struct case_def *c=&cases[index]; int e=protected_image(hash);
    if(e) worker_fail(e);
    e=credentials(uid);
    if(e) worker_fail(e);
    e=m0_check_limit(1,c->quota);
    if(e) worker_fail(e);
    e=canaries(c->sandbox);
    if(e) worker_fail(e);
    send_gate(SANDBOXED,0);
    char release=0;
    if(all_read(4,&release,1) || release!='R') worker_fail(ECANCELED);
    if(close(4)<0) worker_fail(errno);
    if(fcntl(3,F_SETFD,FD_CLOEXEC)<0) worker_fail(errno);
    char idx[16],id[16]; snprintf(idx,sizeof(idx),"%u",index); snprintf(id,sizeof(id),"%u",uid);
    char *args[]={image,"P",idx,id,(char *)hash,NULL};
    char *env[]={"PATH=/usr/bin:/bin",NULL};
    char path[PATH_MAX];
    if(c->fault==3) {
        snprintf(path,sizeof(path),"%s/not-created",directory);
        execve(path,args,env);
    } else execve(image,args,env);
    worker_fail(errno);
}
static void payload(unsigned index,uid_t uid,const char *hash) {
    if(protected_image(hash) || credentials(uid)) _exit(95);
    if(canaries(cases[index].sandbox)) _exit(113);
    struct payload_record r; memset(&r,0,sizeof(r)); struct rlimit l;
    r.magic=MAGIC; r.version=1; r.length=sizeof(r); r.pid=getpid(); r.entered=1;
    r.uid=getuid(); r.euid=geteuid(); r.gid=getgid(); r.egid=getegid();
    gid_t g=0; r.groups=getgroups(1,&g); r.group=(int32_t)g;
    errno=0;
    if(write(3,"X",1)<0) r.fd3_errno=errno;
    errno=0;
    if(write(4,"X",1)<0) r.fd4_errno=errno;
    (void)all_write(STDOUT_FILENO,"SANDBOXED EXEC_OK\n",17);
    errno=0;
    if(seteuid(0)<0) r.recover_uid_errno=errno; else _exit(96);
    errno=0;
    if(setegid(0)<0) r.recover_gid_errno=errno; else _exit(97);
    if(getrlimit(RLIMIT_NPROC,&l)<0) _exit(98);
    r.current=l.rlim_cur; r.maximum=l.rlim_max;
    r.canary_errno=canary_errno; r.canary_allowed=canary_allowed;
    int marker[2];
    if(pipe(marker)<0) _exit(99);
    errno=0; pid_t p=fork(); r.fork_pid=p; r.fork_errno=p<0 ? errno : 0;
    if(p==0) { ssize_t n=write(marker[1],"C",1); _exit(n==1 ? 0 : 100); }
    close(marker[1]);
    if(p>0) {
        int s; pid_t w;
        do { w=waitpid(p,&s,0); } while(w<0 && errno==EINTR);
        if(w!=p || !WIFEXITED(s) || WEXITSTATUS(s)) _exit(101);
    }
    char byte=0; ssize_t n;
    do { n=read(marker[0],&byte,1); } while(n<0 && errno==EINTR);
    if(n<0 || (n==1 && byte!='C')) _exit(102);
    r.child_byte=(int32_t)n; close(marker[0]);
    if(all_write(5,&r,sizeof(r))) _exit(103);
    close(5); _exit(0);
}
static int valid_gate(const struct gate_record *r,pid_t pid,uid_t uid,unsigned phase) {
    return r->magic==MAGIC && r->version==1 && r->length==sizeof(*r) &&
        r->phase==phase && !r->error && r->pid==pid && r->uid==uid &&
        r->euid==uid && r->gid==uid && r->egid==uid && r->groups==1 && r->group==uid;
}
static int wait_owned(pid_t pid,int *status) {
    sigset_t mask,old; sigemptyset(&mask); sigaddset(&mask,SIGALRM);
    for(unsigned attempt=0;attempt<100;attempt++) {
        if(sigprocmask(SIG_BLOCK,&mask,&old)<0) return -1;
        pid_t r=waitpid(pid,status,WNOHANG); int saved=errno;
        if(r==pid) owned_child=0;
        if(sigprocmask(SIG_SETMASK,&old,NULL)<0) return -1;
        if(r==pid) return 0;
        if(r<0 && saved!=EINTR) { errno=saved; return -1; }
        (void)usleep(10000);
    }
    errno=ETIMEDOUT; return -1;
}
static void run_case(unsigned index,uid_t uid,int ledger,const char *sha,const char *kernel,
                     const char *os_build,const char *arch,const char *profile_hash) {
    const struct case_def *c=&cases[index];
    int status_pipe[2],release_pipe[2],data_pipe[2];
    if(pipe(status_pipe)<0 || pipe(release_pipe)<0 || pipe(data_pipe)<0) die("pipes");
    pid_t pid=fork();
    if(pid<0) die("observer-fork");
    if(pid==0) {
        alarm(10); owned_child=0;
        struct rlimit cpu={2,2},files={65536,65536};
        if(setrlimit(RLIMIT_CPU,&cpu)<0) setup_fail(index,1,errno,RLIMIT_CPU,104);
        if(setrlimit(RLIMIT_FSIZE,&files)<0) setup_fail(index,2,errno,RLIMIT_FSIZE,104);
        struct rlimit actual;
        if(getrlimit(RLIMIT_CPU,&actual)<0) setup_fail(index,3,errno,RLIMIT_CPU,116);
        if(actual.rlim_cur!=2 || actual.rlim_max!=2) setup_fail(index,4,0,RLIMIT_CPU,116);
        if(getrlimit(RLIMIT_FSIZE,&actual)<0) setup_fail(index,5,errno,RLIMIT_FSIZE,116);
        if(actual.rlim_cur!=65536 || actual.rlim_max!=65536) setup_fail(index,6,0,RLIMIT_FSIZE,116);
        int limit=getdtablesize();
        if(limit<6 || limit>65536) setup_fail(index,7,limit<0 ? errno : 0,limit,105);
        if(dup2(status_pipe[1],3)<0) setup_fail(index,8,errno,3,106);
        if(dup2(release_pipe[0],4)<0) setup_fail(index,8,errno,4,106);
        if(dup2(data_pipe[1],5)<0) setup_fail(index,8,errno,5,106);
        for(int f=6;f<limit;f++) {
            if(close(f)<0 && errno!=EBADF) setup_fail(index,9,errno,f,114);
        }
        int null=open("/dev/null",O_RDWR);
        if(null<0) setup_fail(index,10,errno,0,107);
        /* Preserve bounded fixed-tool stderr as raw evidence, never as a receipt. */
        for(int f=0;f<2;f++) if(dup2(null,f)<0) setup_fail(index,11,errno,f,108);
        if(null>5) close(null);
        for(int s=1;s<NSIG;s++) {
            if(s!=SIGKILL && s!=SIGSTOP && signal(s,SIG_DFL)==SIG_ERR)
                setup_fail(index,12,errno,s,115);
        }
        sigset_t empty; sigemptyset(&empty);
        if(sigprocmask(SIG_SETMASK,&empty,NULL)<0) setup_fail(index,13,errno,0,109);
        if(chdir(directory)<0) setup_fail(index,14,errno,0,110);
        char start=0;
        int start_error=all_read(4,&start,1);
        if(start_error || start!='A') setup_fail(index,15,start_error,(unsigned char)start,111);
        char idx[16],id[16];
        snprintf(idx,sizeof(idx),"%u",index); snprintf(id,sizeof(id),"%u",uid);
        char *args[]={image,"T",idx,id,binary_hash,NULL};
        char *env[]={"PATH=/usr/bin:/bin",NULL};
        execve(image,args,env); setup_fail(index,16,errno,0,112);
    }
    owned_child=pid;
    close(status_pipe[1]); close(release_pipe[0]); close(data_pipe[1]);
    struct proc_bsdinfo initial,cred; memset(&cred,0,sizeof(cred));
    if(proc_pidinfo(pid,PROC_PIDTBSDINFO,0,&initial,sizeof(initial))!=(int)sizeof(initial))
        die("start-identity");
    if(all_write(release_pipe[1],"A",1)) die("start-release");
    struct gate_record configured,ready,late;
    memset(&configured,0,sizeof(configured)); memset(&ready,0,sizeof(ready));
    ready.canary_errno=-1;
    int e=read_record(status_pipe[0],&configured,sizeof(configured));
    int configured_read_errno=e,ready_attempted=0,ready_read_errno=-1;
    int configured_ok=!e && valid_gate(&configured,pid,uid,CONFIGURED);
    if(configured_ok) {
        ready_attempted=1;
        e=read_record(status_pipe[0],&ready,sizeof(ready));
        ready_read_errno=e;
    }
    int ready_ok=configured_ok && !e && valid_gate(&ready,pid,uid,SANDBOXED);
    int count=-1,cred_ok=0,kq=-1,registered=0,released=0,exec_seen=0,exec_error=0;
    if(ready_ok) {
        if(proc_pidinfo(pid,PROC_PIDTBSDINFO,0,&cred,sizeof(cred))==(int)sizeof(cred)) {
            cred_ok=cred.pbi_pid==(uint32_t)pid && cred.pbi_ruid==uid && cred.pbi_uid==uid &&
                cred.pbi_svuid==uid && cred.pbi_rgid==uid && cred.pbi_gid==uid && cred.pbi_svgid==uid &&
                cred.pbi_start_tvsec==initial.pbi_start_tvsec &&
                cred.pbi_start_tvusec==initial.pbi_start_tvusec;
        }
        count=process_count(uid);
        /* The TEST baseline deliberately ignores quota; SOURCE cannot do so. */
        int limits_ok=!c->quota || strcmp(m0_variant(),"baseline")==0 ||
            (ready.current==1 && ready.maximum==1 && configured.current==1 && configured.maximum==1);
        if(cred_ok && count==1 && limits_ok) {
            kq=kqueue();
            struct kevent change,receipt; struct timespec zero={0,0};
            EV_SET(&change,pid,EVFILT_PROC,EV_ADD|EV_ENABLE|EV_CLEAR|EV_RECEIPT,NOTE_EXEC|NOTE_EXIT,0,NULL);
            if(kq>=0 && kevent(kq,&change,1,&receipt,1,&zero)==1 &&
               (receipt.flags&EV_ERROR) && receipt.data==0) registered=1;
        }
    }
    if(registered && c->fault!=2) {
        if(!all_write(release_pipe[1],"R",1)) released=1;
    }
    close(release_pipe[1]);
    char launch[256];
    int launch_n=snprintf(launch,sizeof(launch),
        "{\"kind\":\"launch\",\"version\":1,\"case\":\"%s\",\"released\":%d}\n",c->name,released);
    if(launch_n<=0 || launch_n>=(int)sizeof(launch) ||
       all_write(STDOUT_FILENO,launch,(size_t)launch_n)) die("delivery-launch");
    int observer_kill_sent=0;
    if(!released && c->fault!=1 && c->fault!=2) {
        (void)kill(pid,SIGKILL); observer_kill_sent=1;
    }
    if(released) {
        struct kevent event; struct timespec timeout={11,0}; int exited=0;
        while(!exited) {
            int n=kevent(kq,NULL,0,&event,1,&timeout);
            if(n<0 && errno==EINTR) continue;
            if(n!=1 || (event.flags&EV_ERROR) || event.ident!=(uintptr_t)pid) break;
            if(event.fflags&NOTE_EXEC) exec_seen=1;
            if(event.fflags&NOTE_EXIT) exited=1;
        }
        if(!exited) { (void)kill(pid,SIGKILL); observer_kill_sent=1; }
    }
    int status=0;
    if(wait_owned(pid,&status)<0) die("owned-waitpid");
    emit_diagnostic(index,101,configured_read_errno,
        configured_read_errno ? -1 : (int)configured.phase,
        configured_read_errno ? -1 : configured.error);
    emit_diagnostic(index,102,0,configured_read_errno ? -1 : configured.pid,configured_ok);
    emit_diagnostic(index,103,ready_read_errno,
        ready_read_errno ? -1 : (int)ready.phase,ready_read_errno ? -1 : ready.error);
    emit_diagnostic(index,104,0,ready_attempted,ready_ok);
    emit_diagnostic(index,105,0,observer_kill_sent,status);
    emit_diagnostic(index,106,0,WIFEXITED(status) ? WEXITSTATUS(status) : -1,
        WIFSIGNALED(status) ? WTERMSIG(status) : 0);
    emit_diagnostic(index,107,0,registered,released);
    emit_diagnostic(index,108,0,configured_ok,ready_ok);
    emit_gate_observation(index,1,(uint32_t)uid,configured_read_errno==0,&configured);
    emit_gate_observation(index,2,(uint32_t)uid,ready_attempted && ready_read_errno==0,&ready);
    if(kq>=0) close(kq);
    unsigned char raw[sizeof(late)+1]; size_t used=0;
    for(;;) {
        ssize_t n=read(status_pipe[0],raw+used,sizeof(raw)-used);
        if(n<0 && errno==EINTR) continue;
        if(n<0) die("status-drain");
        if(!n) break;
        used+=(size_t)n;
        if(used==sizeof(raw)) die("status-extra-bytes");
    }
    close(status_pipe[0]);
    if(used) {
        if(used!=sizeof(late)) die("status-short-packet");
        memcpy(&late,raw,sizeof(late));
        if(late.magic!=MAGIC || late.version!=1 || late.length!=sizeof(late) ||
           late.phase!=FAILED || late.pid!=pid || late.error<=0) die("status-late-contract");
        exec_error=late.error;
    }
    struct payload_record p; memset(&p,0,sizeof(p)); p.canary_errno=-1; int entered=0;
    size_t data_used=0;
    while(data_used<sizeof(p)) {
        ssize_t n=read(data_pipe[0],(unsigned char *)&p+data_used,sizeof(p)-data_used);
        if(n<0 && errno==EINTR) continue;
        if(n<0) die("payload-data-read");
        if(!n) break;
        data_used+=(size_t)n;
    }
    if(data_used && data_used!=sizeof(p)) die("payload-short-packet");
    char extra;
    if(data_used==sizeof(p)) {
        if(p.magic!=MAGIC || p.version!=1 || p.length!=sizeof(p) || p.pid!=(uint32_t)pid ||
           p.uid!=uid || p.euid!=uid || p.gid!=uid || p.egid!=uid || p.entered!=1 ||
           read(data_pipe[0],&extra,1)!=0) die("payload-data-contract");
        entered=1;
    }
    close(data_pipe[0]);
    int remaining=process_count(uid);
    const char *started=exec_seen ? "true" : (!released || exec_error ? "false" : "unknown");
    int normal_exit=WIFEXITED(status) && WEXITSTATUS(status)==0;
    char saved_uid[32]="null",saved_gid[32]="null";
    if(cred_ok) {
        snprintf(saved_uid,sizeof(saved_uid),"%u",cred.pbi_svuid);
        snprintf(saved_gid,sizeof(saved_gid),"%u",cred.pbi_svgid);
    }
    char row[4096];
    int n=snprintf(row,sizeof(row),
        "{\"kind\":\"case\",\"version\":1,\"candidate_sha\":\"%s\",\"variant\":\"%s\","
        "\"case\":\"%s\",\"kernel\":\"%s\",\"os_build\":\"%s\",\"arch\":\"%s\",\"translated\":0,"
        "\"binary_sha256\":\"%s\",\"profile_sha256\":\"%s\",\"sandbox_exec_sha256\":\"%s\",\"observer_pid\":%d,"
        "\"observer_uid\":%u,\"pid\":%d,\"start_sec\":%" PRIu64 ",\"start_usec\":%" PRIu64 ","
        "\"uid\":%u,\"gid\":%u,\"saved_uid\":%s,\"saved_gid\":%s,\"credentials_valid\":%d,"
        "\"configured\":%d,\"sandboxed\":%d,\"quota_enabled\":%d,\"profile_enabled\":%d,"
        "\"cur\":%" PRIu64 ",\"hard\":%" PRIu64 ",\"uid_count_at_barrier\":%d,"
        "\"registered\":%d,\"released\":%d,\"kernel_exec\":%d,\"payload_started\":\"%s\","
        "\"exec_errno\":%d,\"entered\":%d,\"normal_exit\":%d,"
        "\"payload_pid\":%u,\"payload_cur\":%" PRIu64 ",\"payload_hard\":%" PRIu64 ","
        "\"fd3_errno\":%d,\"fd4_errno\":%d,\"recover_uid_errno\":%d,\"recover_gid_errno\":%d,"
        "\"groups\":%d,\"group\":%d,\"fork_pid\":%d,\"fork_errno\":%d,\"child_byte\":%d,"
        "\"gate_canary_errno\":%d,\"gate_canary_allowed\":%d,"
        "\"payload_canary_errno\":%d,\"payload_canary_allowed\":%d,"
        "\"wait_status\":%d,\"exit_code\":%d,\"term_signal\":%d,"
        "\"remaining\":%d,\"cleanup_scope\":\"owned_root_only\",\"retained\":true}\n",
        sha,m0_variant(),c->name,kernel,os_build,arch,binary_hash,profile_hash,sandbox_hash,(int)getpid(),getuid(),
        (int)pid,initial.pbi_start_tvsec,initial.pbi_start_tvusec,uid,uid,saved_uid,saved_gid,
        cred_ok,configured_ok,ready_ok,c->quota,c->sandbox,ready.current,ready.maximum,count,
        registered,released,exec_seen,started,exec_error,entered,normal_exit,p.pid,
        p.current,p.maximum,p.fd3_errno,p.fd4_errno,p.recover_uid_errno,p.recover_gid_errno,
        p.groups,p.group,p.fork_pid,p.fork_errno,p.child_byte,
        ready.canary_errno,ready.canary_allowed,p.canary_errno,p.canary_allowed,
        status,WIFEXITED(status) ? WEXITSTATUS(status) : -1,WIFSIGNALED(status) ? WTERMSIG(status) : 0,remaining);
    if(n<=0 || n>=(int)sizeof(row) || all_write(ledger,row,(size_t)n) || fsync(ledger)<0)
        die("audit-write");
    /* Actual sender-side delivery fault: omit the confirmation bytes, not the
       kernel event or root audit row. No case-specific "unknown" is emitted. */
    char confirmation[256];
    int confirmation_n=snprintf(confirmation,sizeof(confirmation),
        "{\"kind\":\"confirmation\",\"version\":1,\"case\":\"%s\",\"payload_started\":\"%s\"}\n",
        c->name,started);
    if(confirmation_n<=0 || confirmation_n>=(int)sizeof(confirmation)) die("confirmation-format");
    if(c->fault==4 && !exec_seen) die("receipt-loss-requires-real-exec");
    if(c->fault!=4 && all_write(STDOUT_FILENO,confirmation,(size_t)confirmation_n))
        die("delivery-confirmation");
    if(remaining!=0) die("remaining-unknown-or-contamination");
}
int main(int argc,char **argv) {
    self_path();
    if(argc==5 && (!strcmp(argv[1],"T") || !strcmp(argv[1],"G") || !strcmp(argv[1],"P"))) {
        unsigned index=(unsigned)numeric(argv[2],0,(int)(sizeof(cases)/sizeof(cases[0]))-1);
        uid_t uid=(uid_t)numeric(argv[3],UID_FIRST,UID_FIRST+UID_COUNT-1);
        if(!hex_string(argv[4],64)) die("worker-hash-argument");
        if(!strcmp(argv[1],"T")) trampoline(index,uid,argv[4]);
        if(!strcmp(argv[1],"G")) gate(index,uid,argv[4]);
        payload(index,uid,argv[4]); return 2;
    }
    if(argc!=3 || getuid()!=0 || geteuid()!=0 || !hex_string(argv[1],40) || !hex_string(argv[2],64))
        die("observer-arguments");
    umask(077);
    if(signal(SIGALRM,expire)==SIG_ERR || signal(SIGPIPE,SIG_IGN)==SIG_ERR) die("signals");
    alarm(120); struct rlimit cpu={20,20};
    if(setrlimit(RLIMIT_CPU,&cpu)<0) die("observer-cpu");
    struct rlimit actual_cpu;
    if(getrlimit(RLIMIT_CPU,&actual_cpu)<0 || actual_cpu.rlim_cur!=20 || actual_cpu.rlim_max!=20)
        die("observer-cpu-readback");
    for(int f=3;f<6;f++) if(open("/dev/null",O_RDWR|O_CLOEXEC)!=f) die("fd-layout");
    struct utsname u; char os_build[64]; size_t os_n=sizeof(os_build);
    if(uname(&u)<0 || sysctlbyname("kern.osversion",os_build,&os_n,NULL,0)<0) die("os-identity");
    for(const char *s=os_build;*s;s++)
        if(!((*s>='0' && *s<='9') || (*s>='A' && *s<='Z') || (*s>='a' && *s<='z')))
            die("os-build-format");
    for(const char *s=u.release;*s;s++)
        if(!((*s>='0' && *s<='9') || *s=='.')) die("kernel-format");
    if(strcmp(u.machine,"arm64") && strcmp(u.machine,"x86_64")) die("runtime-arch");
    int translation=-1; size_t translation_size=sizeof(translation); errno=0;
    int query=sysctlbyname("sysctl.proc_translated",&translation,&translation_size,NULL,0);
    int native_process=(query==0 && translation_size==sizeof(translation) && translation==0) ||
                       (query<0 && errno==ENOENT);
    if(!native_process) die("translated-or-unknown-process");
    if(secure_chain("/usr/bin/sandbox-exec")) die("system-seatbelt-ancestry");
    int sf=open("/usr/bin/sandbox-exec",O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
    struct stat system_image;
    if(sf<0 || fstat(sf,&system_image)<0 || !S_ISREG(system_image.st_mode) ||
       !(system_image.st_mode&0111) || (system_image.st_mode&(S_ISUID|S_ISGID)) ||
       hash_fd(sf,sandbox_hash,MAX_IMAGE) || close(sf)<0)
        die("system-seatbelt-image");
    prepare_image(argv[2]); directory_accounts(); int leases=lease_directory();
    char ledger_path[PATH_MAX],profile_path[PATH_MAX],profile_hash[65];
    snprintf(ledger_path,sizeof(ledger_path),"%s/native.jsonl",directory);
    snprintf(profile_path,sizeof(profile_path),"%s/profile.sb",directory);
    int pf=open(profile_path,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
    if(pf<0 || hash_fd(pf,profile_hash,4096) || close(pf)<0) die("profile-hash");
    int ledger=open(ledger_path,O_RDWR|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    if(ledger<0) die("ledger-open");
    for(unsigned i=0;i<sizeof(cases)/sizeof(cases[0]);i++) {
        uid_t uid=reserve_uid(leases,argv[1]);
        run_case(i,uid,ledger,argv[1],u.release,os_build,u.machine,profile_hash);
    }
    char digest[65];
    /* Audit-only export: root-owned protected directory remains nonwritable.
       Nonroot controller reads this file only AFTER freezing its delivery view.
       It contains this finite fixture's evidence, no credentials/secrets. */
    if(hash_fd(ledger,digest,65536) || fchmod(ledger,0444)<0 || fsync(ledger)<0 ||
       close(ledger)<0 || close(leases)<0) die("ledger-hash");
    printf("{\"kind\":\"audit\",\"version\":1,\"ledger_sha256\":\"%s\","
           "\"root_directory\":\"%s\",\"retained\":true}\n",digest,directory);
    if(fflush(stdout)==EOF) die("final-audit");
    alarm(0); return 0;
}
