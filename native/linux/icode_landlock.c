/* R2.2 prototype: Landlock filesystem boundary plus seccomp network denial.
 * This helper is packaged in Linux wheels but intentionally not selected for
 * user runs until policy binding, protected metadata and conformance are in place.
 */
#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <linux/audit.h>
#include <linux/capability.h>
#include <linux/filter.h>
#include <linux/landlock.h>
#include <linux/seccomp.h>
#include <linux/securebits.h>
#include <limits.h>
#include <poll.h>
#include <sched.h>
#include <signal.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/wait.h>
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
#define FS_READ_ONLY (LANDLOCK_ACCESS_FS_READ_FILE | LANDLOCK_ACCESS_FS_READ_DIR)
#define FS_WRITE (LANDLOCK_ACCESS_FS_WRITE_FILE | LANDLOCK_ACCESS_FS_REMOVE_DIR | \
                  LANDLOCK_ACCESS_FS_REMOVE_FILE | LANDLOCK_ACCESS_FS_MAKE_CHAR | \
                  LANDLOCK_ACCESS_FS_MAKE_DIR | LANDLOCK_ACCESS_FS_MAKE_REG | \
                  LANDLOCK_ACCESS_FS_MAKE_SOCK | LANDLOCK_ACCESS_FS_MAKE_FIFO | \
                  LANDLOCK_ACCESS_FS_MAKE_BLOCK | LANDLOCK_ACCESS_FS_MAKE_SYM | \
                  LANDLOCK_ACCESS_FS_REFER | LANDLOCK_ACCESS_FS_TRUNCATE)

struct metadata_read_root {
    const char *path;
    uint64_t device;
    uint64_t inode;
};

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

static int open_metadata_path(const char *path) {
    if (!path || path[0] != '/' || path[1] == '\0') {
        errno = EINVAL;
        return -1;
    }

    /* Pin each parent while walking; never follow a metadata-root symlink. */
    int current = open("/", O_PATH | O_DIRECTORY | O_CLOEXEC);
    if (current < 0) return -1;
    const char *component = path + 1;
    while (*component != '\0') {
        const char *separator = strchr(component, '/');
        size_t length = separator ? (size_t)(separator - component) : strlen(component);
        if (length == 0 || (length == 1 && component[0] == '.') ||
            (length == 2 && component[0] == '.' && component[1] == '.')) {
            close(current);
            errno = EINVAL;
            return -1;
        }
        char *name = strndup(component, length);
        if (!name) {
            close(current);
            return -1;
        }
        int flags = O_PATH | O_NOFOLLOW | O_CLOEXEC;
        if (separator) flags |= O_DIRECTORY;
        int next = openat(current, name, flags);
        free(name);
        if (next < 0) {
            close(current);
            return -1;
        }
        close(current);
        current = next;
        if (!separator) break;
        component = separator + 1;
    }

    struct stat status;
    if (fstat(current, &status) != 0) {
        int saved_errno = errno;
        close(current);
        errno = saved_errno;
        return -1;
    }
    if (!S_ISDIR(status.st_mode) && !S_ISREG(status.st_mode)) {
        close(current);
        errno = EINVAL;
        return -1;
    }
    return current;
}

static int parse_u64_decimal(const char *value, uint64_t *result) {
    if (!value || !*value || !result) return -1;
    for (const unsigned char *character = (const unsigned char *)value;
         *character; ++character) {
        if (*character < '0' || *character > '9') return -1;
    }
    errno = 0;
    char *end = NULL;
    unsigned long long parsed = strtoull(value, &end, 10);
    if (errno != 0 || !end || *end != '\0') return -1;
#if ULLONG_MAX > UINT64_MAX
    if (parsed > UINT64_MAX) return -1;
#endif
    *result = (uint64_t)parsed;
    return 0;
}

static int add_metadata_path(int ruleset, const struct metadata_read_root *root) {
    int fd = open_metadata_path(root->path);
    if (fd < 0) {
        fprintf(stderr, "metadata root rejected\n");
        return -1;
    }
    struct stat status;
    if (fstat(fd, &status) != 0 || (uint64_t)status.st_dev != root->device ||
        (uint64_t)status.st_ino != root->inode) {
        fprintf(stderr, "metadata root identity changed\n");
        close(fd);
        return -1;
    }
    struct landlock_path_beneath_attr rule = {
        .allowed_access = LANDLOCK_ACCESS_FS_READ_FILE |
            (S_ISDIR(status.st_mode) ? LANDLOCK_ACCESS_FS_READ_DIR : 0),
        .parent_fd = fd,
    };
    int result = (int)syscall(SYS_landlock_add_rule, ruleset,
                              LANDLOCK_RULE_PATH_BENEATH, &rule, 0);
    close(fd);
    if (result != 0) perror("metadata root rule");
    return result;
}

static int install_filesystem(const char *workspace,
                              const char *const *runtime_roots,
                              size_t runtime_root_count,
                              const struct metadata_read_root *metadata_roots,
                              size_t metadata_root_count,
                              int workspace_read_only) {
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
    uint64_t workspace_access = workspace_read_only
        ? FS_READ_ONLY
        : FS_READ | FS_WRITE;
    if (add_path(fd, workspace, workspace_access, 1) != 0) goto fail;
    for (size_t i = 0; i < runtime_root_count; ++i) {
        if (add_path(fd, runtime_roots[i], FS_READ, 1) != 0) goto fail;
    }
    for (size_t i = 0; i < metadata_root_count; ++i) {
        /* Git metadata is readable for the fixed status broker but never executable. */
        if (add_metadata_path(fd, &metadata_roots[i]) != 0) goto fail;
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
        /* PID namespace lifetime, not process-group membership, owns cleanup. */
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

static int install_parent_death_signal(pid_t expected_parent) {
    pid_t parent = getppid();
    if (parent <= 1 || parent != expected_parent) {
        fprintf(stderr, "sandbox parent identity changed before setup\n");
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

static int restore_child_reaping(void) {
    /* SIG_IGN survives execve and makes both trusted waitpid calls return ECHILD. */
    struct sigaction disposition = {.sa_handler = SIG_DFL};
    if (sigemptyset(&disposition.sa_mask) != 0 ||
        sigaction(SIGCHLD, &disposition, NULL) != 0) {
        perror("restore SIGCHLD disposition");
        return -1;
    }
    return 0;
}

static int write_mapping(const char *path, const char *value,
                         int uid_only_on_permission_error) {
    int fd = open(path, O_WRONLY | O_CLOEXEC);
    if (fd < 0) {
        if (uid_only_on_permission_error && (errno == EACCES || errno == EPERM))
            return 1;
        perror(path);
        return -1;
    }
    size_t length = strlen(value);
    ssize_t written;
    do {
        written = write(fd, value, length);
    } while (written < 0 && errno == EINTR);
    int saved_errno = errno;
    close(fd);
    if (written != (ssize_t)length) {
        errno = written < 0 ? saved_errno : EIO;
        if (uid_only_on_permission_error && (errno == EACCES || errno == EPERM))
            return 1;
        perror(path);
        return -1;
    }
    return 0;
}

static int ensure_setgroups_denied(const char *path) {
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) {
        perror(path);
        return -1;
    }
    char state[16];
    ssize_t length;
    do {
        length = read(fd, state, sizeof(state));
    } while (length < 0 && errno == EINTR);
    if (length < 0) {
        perror(path);
        close(fd);
        return -1;
    }
    if (close(fd) != 0) {
        perror(path);
        return -1;
    }
    /* A parent user namespace may already prohibit setgroups. Rewriting its
     * proc control is not always permitted, but an existing deny is sufficient.
     */
    if (length == 5 && memcmp(state, "deny\n", 5) == 0) return 0;
    /* Some host LSMs forbid writing this proc control. Only EACCES/EPERM
     * may take the verified UID-only path, without a spurious stderr error. */
    if (length == 6 && memcmp(state, "allow\n", 6) == 0)
        return write_mapping(path, "deny\n", 1);
    fprintf(stderr, "unexpected setgroups state\n");
    return -1;
}

static int verify_empty_mapping(const char *path) {
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) {
        perror(path);
        return -1;
    }
    char value;
    ssize_t length;
    do {
        length = read(fd, &value, 1);
    } while (length < 0 && errno == EINTR);
    if (length < 0) {
        int saved_errno = errno;
        close(fd);
        errno = saved_errno;
        perror(path);
        return -1;
    }
    if (close(fd) != 0) {
        perror(path);
        return -1;
    }
    if (length != 0) {
        if (strcmp(path, "/proc/self/gid_map") == 0)
            fprintf(stderr, "UID-only sandbox requires an empty gid_map\n");
        else
            fprintf(stderr, "sandbox requires an empty mapping: %s\n", path);
        return -1;
    }
    return 0;
}

static int verify_uid_only_mapping(void) {
    if (verify_empty_mapping("/proc/self/gid_map") != 0) return -1;
    errno = 0;
    if (setgroups(0, NULL) != -1 || errno != EPERM) {
        fprintf(stderr, "UID-only sandbox did not deny setgroups\n");
        return -1;
    }
    return 0;
}

/* Return 0 for mapped credentials, 1 for verified mapless PID namespace. */
static int enter_task_namespaces(pid_t host_parent, const char *setgroups_path,
                                 const char *uid_map_path) {
    uid_t outer_uid = geteuid();
    gid_t outer_gid = getegid();
    if (unshare(CLONE_NEWUSER | CLONE_NEWPID) != 0) {
        perror("unshare user/pid namespace");
        return -1;
    }
    char mapping[64];
    int setgroups_state = ensure_setgroups_denied(setgroups_path);
    if (setgroups_state < 0) return -1;
    int size = snprintf(mapping, sizeof(mapping), "0 %u 1\n", (unsigned)outer_uid);
    if (size < 0 || (size_t)size >= sizeof(mapping)) return -1;
    int uid_mapping = write_mapping(uid_map_path, mapping, 1);
    if (uid_mapping < 0) return -1;
    if (uid_mapping == 1) {
        /* Some Ubuntu AppArmor profiles permit PID namespaces but reject UID
         * mapping. No map is acceptable only for cleanup, never for file
         * confinement; Landlock and no-new-privileges still apply below. */
        if (verify_empty_mapping("/proc/self/uid_map") != 0 ||
            verify_uid_only_mapping() != 0 ||
            install_parent_death_signal(host_parent) != 0) return -1;
        return 1;
    }
    if (setgroups_state == 1) {
        if (verify_uid_only_mapping() != 0) return -1;
    } else {
        size = snprintf(mapping, sizeof(mapping), "0 %u 1\n", (unsigned)outer_gid);
        if (size < 0 || (size_t)size >= sizeof(mapping) ||
            write_mapping("/proc/self/gid_map", mapping, 0) != 0) return -1;
    }
    /* Moving to a user namespace can change credentials and clear PDEATHSIG. */
    return install_parent_death_signal(host_parent) == 0 ? 0 : -1;
}

static int drop_payload_capabilities(int mapless) {
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0) {
        perror("PR_SET_NO_NEW_PRIVS");
        return -1;
    }
    if (!mapless && prctl(PR_SET_SECUREBITS, SECBIT_KEEP_CAPS_LOCKED |
              SECBIT_NO_SETUID_FIXUP | SECBIT_NO_SETUID_FIXUP_LOCKED |
              SECBIT_NOROOT | SECBIT_NOROOT_LOCKED, 0, 0, 0) != 0) {
        perror("drop payload privileges");
        return -1;
    }
    if (prctl(PR_CAP_AMBIENT, PR_CAP_AMBIENT_CLEAR_ALL, 0, 0, 0) != 0) {
        perror("PR_CAP_AMBIENT_CLEAR_ALL");
        return -1;
    }
    /* Mapless AppArmor may deny CAP_SETPCAP. No-new-privileges plus empty
     * active capability sets prevent later exec from gaining bounding caps. */
    for (unsigned cap = 0; cap < 64; ++cap) {
        int present = prctl(PR_CAPBSET_READ, cap, 0, 0, 0);
        if (present < 0 && errno == EINVAL) break;
        if (present < 0 || (!mapless &&
            prctl(PR_CAPBSET_DROP, cap, 0, 0, 0) != 0)) {
            perror("PR_CAPBSET_DROP");
            return -1;
        }
    }
    errno = 0;
    if (prctl(PR_CAPBSET_READ, 64, 0, 0, 0) >= 0 || errno != EINVAL) {
        fprintf(stderr, "kernel capability set exceeds supported 64-bit sandbox ABI\n");
        return -1;
    }
    struct __user_cap_header_struct header = {
        .version = _LINUX_CAPABILITY_VERSION_3, .pid = 0,
    };
    struct __user_cap_data_struct empty[2] = {{0}, {0}};
    if (syscall(SYS_capset, &header, empty) != 0) {
        perror("capset");
        return -1;
    }
    struct __user_cap_data_struct actual[2] = {{0}, {0}};
    if (syscall(SYS_capget, &header, actual) != 0 ||
        prctl(PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) != 1) {
        perror("verify payload privileges");
        return -1;
    }
    for (size_t i = 0; i < 2; ++i) {
        if (actual[i].effective || actual[i].permitted || actual[i].inheritable) {
            fprintf(stderr, "payload retains capabilities\n");
            return -1;
        }
    }
    for (unsigned cap = 0; cap < 64; ++cap) {
        int ambient = prctl(PR_CAP_AMBIENT, PR_CAP_AMBIENT_IS_SET, cap, 0, 0);
        if (ambient < 0 && errno == EINVAL) break;
        if (ambient != 0) {
            fprintf(stderr, "payload retains ambient capabilities\n");
            return -1;
        }
    }
    return 0;
}

static int child_status(int status) {
    if (WIFEXITED(status)) return WEXITSTATUS(status);
    if (WIFSIGNALED(status)) return 128 + WTERMSIG(status);
    return 1;
}

static int run_namespace_init(int parent_pipe, const char *workspace,
                              const char *const *runtime_roots,
                              size_t runtime_root_count,
                              const struct metadata_read_root *metadata_roots,
                              size_t metadata_root_count, char **command,
                              int workspace_read_only, int mapless) {
    /* Namespace PID 1 sees its parent as PID 0, so getppid cannot validate it. */
    if (prctl(PR_SET_DUMPABLE, 0, 0, 0, 0) != 0 ||
        prctl(PR_SET_PDEATHSIG, SIGKILL, 0, 0, 0) != 0) {
        perror("namespace supervisor setup");
        return 1;
    }
    struct pollfd parent = {.fd = parent_pipe, .events = POLLIN | POLLHUP};
    if (poll(&parent, 1, 0) < 0 || parent.revents != 0) {
        fprintf(stderr, "sandbox parent exited before namespace setup\n");
        return 1;
    }
    pid_t payload = fork();
    if (payload < 0) {
        perror("fork sandbox payload");
        return 1;
    }
    if (payload == 0) {
        close(parent_pipe);
        if (drop_payload_capabilities(mapless) != 0 ||
            install_filesystem(workspace, runtime_roots, runtime_root_count,
                               metadata_roots, metadata_root_count,
                               workspace_read_only) != 0 ||
            install_network_deny() != 0) _exit(1);
        execvp(command[0], command);
        perror("execvp");
        _exit(127);
    }
    for (;;) {
        int status;
        pid_t waited = waitpid(payload, &status, WNOHANG);
        if (waited == payload) return child_status(status);
        if (waited < 0 && errno != EINTR) {
            perror("waitpid sandbox payload");
            return 1;
        }
        int ready = poll(&parent, 1, 50);
        if (ready < 0 && errno == EINTR) continue;
        if (ready < 0 || (ready > 0 && parent.revents != 0)) {
            /* Exiting PID 1 makes the kernel kill all namespace descendants. */
            return 1;
        }
    }
}

static int supervise_task(pid_t host_parent, const char *workspace,
                          const char *const *runtime_roots,
                          size_t runtime_root_count,
                          const struct metadata_read_root *metadata_roots,
                          size_t metadata_root_count, char **command,
                          int workspace_read_only,
                          const char *setgroups_path,
                          const char *uid_map_path) {
    int mapless = enter_task_namespaces(host_parent, setgroups_path, uid_map_path);
    if (mapless < 0) return 1;
    int control[2];
    if (pipe2(control, O_CLOEXEC) != 0) {
        perror("pipe2 sandbox parent");
        return 1;
    }
    pid_t init = fork();
    if (init < 0) {
        perror("fork namespace supervisor");
        close(control[0]);
        close(control[1]);
        return 1;
    }
    if (init == 0) {
        close(control[1]);
        int result = run_namespace_init(
            control[0], workspace, runtime_roots, runtime_root_count,
            metadata_roots, metadata_root_count, command,
            workspace_read_only, mapless);
        close(control[0]);
        _exit(result);
    }
    close(control[0]);
    int status;
    pid_t waited;
    do {
        waited = waitpid(init, &status, 0);
    } while (waited < 0 && errno == EINTR);
    close(control[1]);
    if (waited != init) {
        perror("waitpid namespace supervisor");
        return 1;
    }
    return child_status(status);
}

static int run_helper(int argc, char **argv, const char *setgroups_path,
                      const char *uid_map_path) {
    /* Landlock cannot revoke a writable file already open in the host. */
    if (syscall(SYS_close_range, 3U, UINT_MAX, 0U) != 0) {
        perror("close_range inherited descriptors");
        return 1;
    }
    if (argc < 7 || strcmp(argv[1], "--workspace") != 0 ||
        strcmp(argv[3], "--parent-pid") != 0) {
        fprintf(stderr,
                "usage: icode-landlock --workspace PATH --parent-pid PID "
                "[--workspace-read-only] [--runtime-read PATH]... "
                "[--metadata-read PATH DEVICE INODE]... "
                "-- COMMAND [ARG...]\n");
        return 2;
    }
    char *pid_end = NULL;
    errno = 0;
    long parent_value = strtol(argv[4], &pid_end, 10);
    if (errno != 0 || !pid_end || *pid_end != '\0' ||
        parent_value <= 1 || parent_value > INT_MAX) {
        fprintf(stderr, "invalid parent PID\n");
        return 2;
    }
    const char **runtime_roots = calloc((size_t)argc, sizeof(*runtime_roots));
    struct metadata_read_root *metadata_roots = calloc(
        (size_t)argc, sizeof(*metadata_roots));
    if (!runtime_roots || !metadata_roots) {
        perror("calloc");
        free(runtime_roots);
        free(metadata_roots);
        return 2;
    }
    size_t runtime_root_count = 0;
    size_t metadata_root_count = 0;
    int workspace_read_only = 0;
    int command_index = 5;
    while (command_index < argc && strcmp(argv[command_index], "--") != 0) {
        if (strcmp(argv[command_index], "--workspace-read-only") == 0) {
            if (workspace_read_only) {
                fprintf(stderr, "duplicate workspace read-only option\n");
                free(runtime_roots);
                free(metadata_roots);
                return 2;
            }
            workspace_read_only = 1;
            command_index += 1;
        } else if (strcmp(argv[command_index], "--runtime-read") == 0) {
            if (command_index + 1 >= argc || argv[command_index + 1][0] != '/') {
                fprintf(stderr, "invalid runtime root\n");
                free(runtime_roots);
                free(metadata_roots);
                return 2;
            }
            runtime_roots[runtime_root_count++] = argv[command_index + 1];
            command_index += 2;
        } else if (strcmp(argv[command_index], "--metadata-read") == 0) {
            if (command_index + 3 >= argc || argv[command_index + 1][0] != '/') {
                fprintf(stderr, "invalid metadata root\n");
                free(runtime_roots);
                free(metadata_roots);
                return 2;
            }
            struct metadata_read_root root = {.path = argv[command_index + 1]};
            if (parse_u64_decimal(argv[command_index + 2], &root.device) != 0) {
                fprintf(stderr, "invalid metadata device identity\n");
                free(runtime_roots);
                free(metadata_roots);
                return 2;
            }
            if (parse_u64_decimal(argv[command_index + 3], &root.inode) != 0) {
                fprintf(stderr, "invalid metadata inode identity\n");
                free(runtime_roots);
                free(metadata_roots);
                return 2;
            }
            for (size_t i = 0; i < metadata_root_count; ++i) {
                if (strcmp(metadata_roots[i].path, root.path) == 0) {
                    fprintf(stderr, "duplicate metadata root\n");
                    free(runtime_roots);
                    free(metadata_roots);
                    return 2;
                }
            }
            metadata_roots[metadata_root_count++] = root;
            command_index += 4;
        } else {
            fprintf(stderr, "unknown read-only root option\n");
            free(runtime_roots);
            free(metadata_roots);
            return 2;
        }
    }
    if (command_index + 1 >= argc) {
        fprintf(stderr, "missing command\n");
        free(runtime_roots);
        free(metadata_roots);
        return 2;
    }
    ++command_index;
    if (install_parent_death_signal((pid_t)parent_value) != 0 ||
        restore_child_reaping() != 0) {
        free(runtime_roots);
        free(metadata_roots);
        return 1;
    }
    char *workspace = realpath(argv[2], NULL);
    if (!workspace) {
        perror("workspace realpath");
        free(runtime_roots);
        free(metadata_roots);
        return 2;
    }
    if (chdir(workspace) != 0) {
        perror("chdir workspace");
        free(workspace);
        free(runtime_roots);
        free(metadata_roots);
        return 1;
    }
    int result = supervise_task(
        (pid_t)parent_value, workspace, runtime_roots, runtime_root_count,
        metadata_roots, metadata_root_count, argv + command_index,
        workspace_read_only, setgroups_path, uid_map_path);
    free(workspace);
    free(runtime_roots);
    free(metadata_roots);
    return result;
}

int main(int argc, char **argv) {
    return run_helper(argc, argv, "/proc/self/setgroups", "/proc/self/uid_map");
}
