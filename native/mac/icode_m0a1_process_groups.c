#if defined(_DARWIN_C_SOURCE) || defined(_DARWIN_UNLIMITED_GETGROUPS)
#error M0_PROCESS_GROUPS_FEATURE_MACRO_DARWIN_BEFORE_HEADERS
#endif
#if defined(_POSIX_C_SOURCE) && _POSIX_C_SOURCE != 200809L
#error M0_PROCESS_GROUPS_FEATURE_MACRO_POSIX_CONFLICT
#endif
#ifndef _POSIX_C_SOURCE
#define _POSIX_C_SOURCE 200809L
#endif
#include "icode_m0a1_process_groups.h"
#include <errno.h>
#include <unistd.h>
#if defined(_DARWIN_C_SOURCE) || defined(_DARWIN_UNLIMITED_GETGROUPS)
#error M0_PROCESS_GROUPS_FEATURE_MACRO_DARWIN_AFTER_HEADERS
#endif
int m0_process_getgroups(int capacity, gid_t groups[]) {
    return getgroups(capacity,groups);
}
int m0_process_credentials(uid_t uid) {
    gid_t g=0;
    if(getuid()!=uid || geteuid()!=uid || getgid()!=uid || getegid()!=uid ||
       m0_process_getgroups(0,NULL)!=1 || m0_process_getgroups(1,&g)!=1 || g!=uid) return EPERM;
    return 0;
}
