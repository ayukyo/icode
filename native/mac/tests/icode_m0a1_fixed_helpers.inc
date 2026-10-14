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
