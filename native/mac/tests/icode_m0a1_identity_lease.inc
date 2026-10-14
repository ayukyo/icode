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
/* IDENTITY_SNAPSHOT_DIAGNOSTIC_BEGIN */
struct process_snapshot {
    int list_count,list_errno,bad_index,bad_pid,info_result,info_expected,info_errno,kill_result,kill_errno;
};
static void emit_process_snapshot(const char *stage,uid_t uid,const struct process_snapshot *s) {
    /* Only root observers consume this on a terminal refusal, after SIGPIPE=SIG_IGN. */
    int saved=errno;
    char line[384];
    int n=snprintf(line,sizeof(line),
        "M0A1_SNAPSHOT stage=%s uid=%u list_count=%d cap=%d list_errno=%d bad_index=%d bad_pid=%d info_result=%d info_expected=%d info_errno=%d kill_result=%d kill_errno=%d cleanup=unknown\n",
        stage,(unsigned)uid,s->list_count,MAX_PIDS,s->list_errno,s->bad_index,s->bad_pid,
        s->info_result,s->info_expected,s->info_errno,s->kill_result,s->kill_errno);
    if(n>0 && n<(int)sizeof(line)) (void)write(2,line,(size_t)n);
    errno=saved;
}
/* IDENTITY_SNAPSHOT_DIAGNOSTIC_END */
/* IDENTITY_SNAPSHOT_ALGORITHM_BEGIN */
static int process_count_snapshot(uid_t uid,struct process_snapshot *s) {
    pid_t pids[MAX_PIDS]; int n=proc_listallpids(pids,sizeof(pids)),count=0;
    int list_errno=errno;
    *s=(struct process_snapshot){n,list_errno,-1,-1,-1,(int)sizeof(struct proc_bsdinfo),-1,-1,-1};
    if(n<=0 || n>=MAX_PIDS) return -1;
    for(int i=0;i<n;i++) {
        if(pids[i]<=0) continue;
        struct proc_bsdinfo b;
        int r=proc_pidinfo(pids[i],PROC_PIDTBSDINFO,0,&b,sizeof(b));
        int info_errno=errno;
        if(r!=(int)sizeof(b)) {
            errno=0;
            int exists=kill(pids[i],0);
            int kill_errno=errno;
            if(exists<0 && kill_errno==ESRCH) continue;
            s->bad_index=i;s->bad_pid=(int)pids[i];s->info_result=r;
            s->info_errno=info_errno;s->kill_result=exists;s->kill_errno=kill_errno;
            return -1;
        }
        if(b.pbi_ruid==uid || b.pbi_uid==uid || b.pbi_svuid==uid ||
           b.pbi_rgid==uid || b.pbi_gid==uid || b.pbi_svgid==uid) count++;
    }
    return count;
}
static int process_count(uid_t uid) {
    struct process_snapshot snapshot;
    return process_count_snapshot(uid,&snapshot);
}
/* IDENTITY_SNAPSHOT_ALGORITHM_END */
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
        uid_t uid=UID_FIRST+i; struct process_snapshot before_snapshot;
        int before=process_count_snapshot(uid,&before_snapshot);
        char lookup[16384]; struct passwd pw,*pw_result=NULL; struct group gr,*gr_result=NULL;
        int lookup_error=getpwuid_r(uid,&pw,lookup,sizeof(lookup),&pw_result);
        if(lookup_error) { errno=lookup_error; die("uid-directory-lookup"); }
        if(pw_result) continue;
        lookup_error=getgrgid_r(uid,&gr,lookup,sizeof(lookup),&gr_result);
        if(lookup_error) { errno=lookup_error; die("gid-directory-lookup"); }
        if(gr_result) continue;
        if(before<0) {
            emit_process_snapshot("reserve-process-snapshot",uid,&before_snapshot);
            die("reserve-process-snapshot");
        }
        if(before) continue;
        char name[32]; snprintf(name,sizeof(name),"uid-%u",uid);
        int f=openat(dir,name,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
        if(f<0 && errno==EEXIST) continue;
        if(f<0 || all_write(f,sha,40) || fsync(f)<0 || close(f)<0) die("reserve-lease");
        unavailable[i]=1;
        struct process_snapshot after_snapshot;
        int after=process_count_snapshot(uid,&after_snapshot);
        if(after<0) emit_process_snapshot("reserve-contaminated",uid,&after_snapshot);
        if(after!=0) die("reserve-contaminated");
        return uid;
    }
    errno=ENOSPC; die("reserve-exhausted"); return 0;
}
