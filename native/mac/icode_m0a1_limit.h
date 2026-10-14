#ifndef ICODE_M0A1_LIMIT_H
#define ICODE_M0A1_LIMIT_H
#include <sys/resource.h>
int m0_apply_limit(rlim_t cap, int enabled);
int m0_check_limit(rlim_t cap, int enabled);
const char *m0_variant(void);
#endif
