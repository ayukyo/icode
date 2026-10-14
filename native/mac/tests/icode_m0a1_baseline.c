#include "icode_m0a1_limit.h"
int m0_apply_limit(rlim_t cap,int enabled) {
    (void)cap; (void)enabled; return 0;
}
int m0_check_limit(rlim_t cap,int enabled) {
    (void)cap; (void)enabled; return 0;
}
const char *m0_variant(void) { return "baseline"; }
