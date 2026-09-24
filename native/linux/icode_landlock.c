/* R2.2 prototype: Landlock filesystem boundary plus seccomp network denial.
 * This helper is packaged in Linux wheels but intentionally not selected for
 * user runs until policy binding, protected metadata and conformance are in place.
 */
#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <linux/audit.h>
#include <linux/filter.h>
#include <linux/landlock.h>
#include <linux/seccomp.h>
#include <signal.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <unistd.h>

#ifndef LANDLOCK_ACCESS_FS_REFER
#define LANDLOCK_ACCESS_FS_REFER (1ULL << 13)
#endif
#ifndef LANDLOCK_ACCESS_FS_TRUNCATE
#define LANDLOCK_ACCESS_FS_TRUNCATE (1ULL << 14)
#endif

#if defined(__x86_64__)
#define ICODE_AUDIT_ARCH AUDIT_ARCH_X86_64
#define ICODE_X32_SYSCALL_BIT 0x40000000U
#elif defined(__aarch64__)
#define ICODE_AUDIT_ARCH AUDIT_ARCH_AARCH64
#else
#error "R2.2 Landlock helper only supports x86_64 and aarch64"
#endif

#define FS_READ (LANDLOCK_ACCESS_FS_EXECUTE | LANDLOCK_ACCESS_FS_READ_FILE | \
                 LANDLOCK_ACCESS_FS_READ_DIR)
#define FS_WRITE (LANDLOCK_ACCESS_FS_WRITE_FILE | LANDLOCK_ACCESS_FS_REMOVE_DIR | \
                  LANDLOCK_ACCESS_FS_REMOVE_FILE | LANDLOCK_ACCESS_FS_MAKE_CHAR | \
                  LANDLOCK_ACCESS_FS_MAKE_DIR | LANDLOCK_ACCESS_FS_MAKE_REG | \
                  LANDLOCK_ACCESS_FS_MAKE_SOCK | LANDLOCK_ACCESS_FS_MAKE_FIFO | \
                  LANDLOCK_ACCESS_FS_MAKE_BLOCK | LANDLOCK_ACCESS_FS_MAKE_SYM | \
                  LANDLOCK_ACCESS_FS_REFER | LANDLOCK_ACCESS_FS_TRUNCATE)

static int add_path(int ruleset, const char *path, uint64_t rights, int required) {
    int fd = open(path, O_PATH | O_CLOEXEC);
    if (fd < 0) {
        if (!required && errno == ENOENT) return 0;
        perror(path);
        return -1;
    }
    struct landlock_path_beneath_attr rule = {
        .allowed_access = rights,
        .parent_fd = fd,
    };
    int result = (int)syscall(SYS_landlock_add_rule, ruleset,
                              LANDLOCK_RULE_PATH_BENEATH, &rule, 0);
    close(fd);
    if (result != 0) perror(path);
    return result;
}

static int install_filesystem(const char *workspace,
                              const char *const *runtime_roots,
                              size_t runtime_root_count) {
    int abi = (int)syscall(SYS_landlock_create_ruleset, NULL, 0,
                           LANDLOCK_CREATE_RULESET_VERSION);
    /* ABI 3 is required to restrict both truncate and cross-directory refer. */
    if (abi < 3) {
        fprintf(stderr, "Landlock ABI 3 or newer is required (found %d)\n", abi);
        return -1;
    }
    struct landlock_ruleset_attr rules = {.handled_access_fs = FS_READ | FS_WRITE};
    int fd = (int)syscall(SYS_landlock_create_ruleset, &rules, sizeof(rules), 0);
    if (fd < 0) {
        perror("landlock_create_ruleset");
        return -1;
    }
    const char *system_roots[] = {"/usr", "/bin", "/lib", "/lib64", "/sbin"};
    for (size_t i = 0; i < sizeof(system_roots) / sizeof(system_roots[0]); ++i) {
        if (add_path(fd, system_roots[i], FS_READ, 0) != 0) goto fail;
    }
    const char *system_files[] = {"/etc/ld.so.cache", "/etc/passwd", "/etc/nsswitch.conf",
                                  "/dev/urandom"};
    for (size_t i = 0; i < sizeof(system_files) / sizeof(system_files[0]); ++i) {
        if (add_path(fd, system_files[i], LANDLOCK_ACCESS_FS_READ_FILE, 0) != 0) goto fail;
    }
    if (add_path(fd, "/dev/null", LANDLOCK_ACCESS_FS_READ_FILE |
                 LANDLOCK_ACCESS_FS_WRITE_FILE, 1) != 0) goto fail;
    if (add_path(fd, workspace, FS_READ | FS_WRITE, 1) != 0) goto fail;
    for (size_t i = 0; i < runtime_root_count; ++i) {
        if (add_path(fd, runtime_roots[i], FS_READ, 1) != 0) goto fail;
    }
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0) {
        perror("PR_SET_NO_NEW_PRIVS");
        goto fail;
    }
    if (syscall(SYS_landlock_restrict_self, fd, 0) != 0) {
        perror("landlock_restrict_self");
        goto fail;
    }
    close(fd);
    return 0;
fail:
    close(fd);
    return -1;
}

static int install_network_deny(void) {
    struct sock_filter instructions[] = {
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, arch)),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, ICODE_AUDIT_ARCH, 1, 0),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, nr)),
#if defined(__x86_64__)
        /* x32 shares AUDIT_ARCH_X86_64 but adds a syscall-number bit. */
        BPF_JUMP(BPF_JMP | BPF_JSET | BPF_K, ICODE_X32_SYSCALL_BIT, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS),
#endif
        /* No direct TCP, UDP or host Unix sockets. Proxy access comes in R2.4. */
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, SYS_socket, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, SYS_io_uring_setup, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM),
        /* Broker cleanup owns one process group; children may not escape it. */
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, SYS_setsid, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, SYS_setpgid, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW),
    };
    struct sock_fprog program = {
        .len = (unsigned short)(sizeof(instructions) / sizeof(instructions[0])),
        .filter = instructions,
    };
    if (prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &program) != 0) {
        perror("PR_SET_SECCOMP");
        return -1;
    }
    return 0;
}

static int install_parent_death_signal(void) {
    pid_t parent = getppid();
    if (parent <= 1) {
        fprintf(stderr, "sandbox parent is already gone\n");
        return -1;
    }
    if (prctl(PR_SET_PDEATHSIG, SIGKILL, 0, 0, 0) != 0) {
        perror("PR_SET_PDEATHSIG");
        return -1;
    }
    /* Parent exit between getppid and prctl would otherwise leave us alive. */
    if (getppid() != parent) {
        fprintf(stderr, "parent exited before sandbox setup\n");
        return -1;
    }
    return 0;
}

int main(int argc, char **argv) {
    if (argc < 5 || strcmp(argv[1], "--workspace") != 0) {
        fprintf(stderr, "usage: icode-landlock --workspace PATH [--runtime-read PATH]... -- COMMAND [ARG...]\n");
        return 2;
    }
    const char **runtime_roots = calloc((size_t)argc, sizeof(*runtime_roots));
    if (!runtime_roots) {
        perror("calloc");
        return 2;
    }
    size_t runtime_root_count = 0;
    int command_index = 3;
    while (command_index < argc && strcmp(argv[command_index], "--") != 0) {
        if (strcmp(argv[command_index], "--runtime-read") != 0 ||
            command_index + 1 >= argc || argv[command_index + 1][0] != '/') {
            fprintf(stderr, "invalid runtime read root\n");
            free(runtime_roots);
            return 2;
        }
        runtime_roots[runtime_root_count++] = argv[command_index + 1];
        command_index += 2;
    }
    if (command_index + 1 >= argc) {
        fprintf(stderr, "missing command\n");
        free(runtime_roots);
        return 2;
    }
    ++command_index;
    if (install_parent_death_signal() != 0) {
        free(runtime_roots);
        return 1;
    }
    char *workspace = realpath(argv[2], NULL);
    if (!workspace) {
        perror("workspace realpath");
        free(runtime_roots);
        return 2;
    }
    if (chdir(workspace) != 0 ||
        install_filesystem(workspace, runtime_roots, runtime_root_count) != 0 ||
        install_network_deny() != 0) {
        free(workspace);
        free(runtime_roots);
        return 1;
    }
    free(workspace);
    free(runtime_roots);
    execvp(argv[command_index], argv + command_index);
    perror("execvp");
    return 127;
}
