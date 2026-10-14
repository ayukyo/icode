#include "icode_m0a1_limit.h"
#include <errno.h>
int m0_check_limit(rlim_t cap,int enabled) {
    if(!enabled) return 0;
    struct rlimit actual;
    if(getrlimit(RLIMIT_NPROC,&actual)<0) return errno;
    return actual.rlim_cur==cap && actual.rlim_max==cap ? 0 : ERANGE;
}
int m0_apply_limit(rlim_t cap,int enabled) {
    if(!enabled) return 0;
    if(cap!=1 && cap!=2) return EINVAL; /* cap1/cap2 only; cap4 awaits race RED. */
    struct rlimit target={.rlim_cur=cap,.rlim_max=cap};
    if(setrlimit(RLIMIT_NPROC,&target)<0) return errno;
    return m0_check_limit(cap,1);
}
const char *m0_variant(void) { return "source"; }
