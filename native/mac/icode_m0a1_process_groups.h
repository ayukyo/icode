#ifndef ICODE_M0A1_PROCESS_GROUPS_H
#define ICODE_M0A1_PROCESS_GROUPS_H
#include <sys/types.h>
int m0_process_getgroups(int capacity, gid_t groups[]);
int m0_process_credentials(uid_t uid);
#endif
