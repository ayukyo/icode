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
