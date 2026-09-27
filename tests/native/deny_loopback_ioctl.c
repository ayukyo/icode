#define _GNU_SOURCE

#include <errno.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <net/if.h>
#include <stddef.h>
#include <stdio.h>
#include <sys/ioctl.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <unistd.h>

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: deny-loopback-ioctl command [args...]\n");
        return 2;
    }

    struct sock_filter instructions[] = {
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS,
                 (unsigned int)offsetof(struct seccomp_data, nr)),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, SYS_ioctl, 0, 3),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS,
                 (unsigned int)offsetof(struct seccomp_data, args[1])),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, SIOCSIFFLAGS, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW),
    };
    struct sock_fprog program = {
        .len = (unsigned short)(sizeof(instructions) / sizeof(instructions[0])),
        .filter = instructions,
    };
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0 ||
        prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &program) != 0) {
        perror("install test seccomp filter");
        return 1;
    }

    execvp(argv[1], argv + 1);
    perror("execvp");
    return errno == ENOENT ? 127 : 126;
}
