/* Independent Linux cgroup-v2 task quota. Call prepare before PID unshare.
 * The caller owns an exclusive delegated scope; no existing cgroup is adopted.
 * This header uses public kernel ABIs, not copied kernel implementation code.
 */
#ifndef ICODE_TASK_QUOTA_H
#define ICODE_TASK_QUOTA_H
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdint.h>
#include <inttypes.h>
#include <linux/magic.h>
#include <linux/sched.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/vfs.h>
#include <unistd.h>

struct icode_task_quota {
    int root_fd, supervisor_fd, payload_fd;
    struct stat root_identity, supervisor_identity, payload_identity;
    uint64_t limit;
    int prepared, created_supervisor, created_payload;
};
#define ICODE_TASK_QUOTA_STATE_INIT { .root_fd = -1, .supervisor_fd = -1, .payload_fd = -1 }

static inline void icode_task_quota_init(struct icode_task_quota *state) {
    if (!state) return;
    memset(state, 0, sizeof(*state));
    state->root_fd = state->supervisor_fd = state->payload_fd = -1;
}

/* Closing ownership handles is not proof that the kernel cgroup was removed. */
static inline void icode_task_quota_close(struct icode_task_quota *state) {
    if (!state) return;
    int saved = errno;
    if (state->root_fd >= 0) close(state->root_fd);
    if (state->supervisor_fd >= 0) close(state->supervisor_fd);
    if (state->payload_fd >= 0) close(state->payload_fd);
    icode_task_quota_init(state);
    errno = saved;
}

static inline int icode_quota_read(int directory, const char *name,
                                  char *buffer, size_t size) {
    int fd = openat(directory, name, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0) return -1;
    size_t used = 0;
    int failure = 0;
    for (;;) {
        char extra;
        ssize_t count = used < size - 1 ? read(fd, buffer + used, size - 1 - used) :
                                        read(fd, &extra, 1);
        if (count < 0 && errno == EINTR) continue;
        if (count < 0) { failure = errno; break; }
        if (!count) break;
        if (used == size - 1) { failure = EOVERFLOW; break; }
        used += (size_t)count;
    }
    close(fd);
    if (failure) { errno = failure; return -1; }
    if (memchr(buffer, '\0', used)) { errno = EINVAL; return -1; }
    buffer[used] = '\0';
    return 0;
}

static inline int icode_quota_write(int directory, const char *name, const char *value) {
    int fd = openat(directory, name, O_WRONLY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0) return -1;
    size_t length = strlen(value);
    ssize_t count;
    do { count = write(fd, value, length); } while (count < 0 && errno == EINTR);
    int failure = count < 0 ? errno : ((size_t)count == length ? 0 : EIO);
    close(fd);
    if (failure) { errno = failure; return -1; }
    return 0;
}

static inline int icode_quota_unit_valid(const char *unit) {
    if (!unit || strlen(unit) != 49 || strncmp(unit, "icode-task-", 11) ||
        strcmp(unit + 43, ".scope")) return 0;
    for (size_t i = 11; i < 43; i++)
        if (!((unit[i] >= '0' && unit[i] <= '9') || (unit[i] >= 'a' && unit[i] <= 'f')))
            return 0;
    return 1;
}

static inline int icode_quota_has_word(const char *text, const char *word) {
    size_t length = strlen(word);
    for (const char *start = text; *start;) {
        while (*start == ' ' || *start == '\n' || *start == '\t') start++;
        const char *end = start;
        while (*end && *end != ' ' && *end != '\n' && *end != '\t') end++;
        if ((size_t)(end - start) == length && !memcmp(start, word, length)) return 1;
        start = end;
    }
    return 0;
}

static inline int icode_quota_same(const struct stat *left, const struct stat *right) {
    return S_ISDIR(right->st_mode) && left->st_dev == right->st_dev &&
           left->st_ino == right->st_ino && right->st_uid == geteuid() &&
           !(right->st_mode & (S_IWGRP | S_IWOTH));
}

/* Each managed name must still resolve to the directory whose handle we own. */
static inline int icode_quota_identity(struct icode_task_quota *state,
                                     int directory, const char *name,
                                     const struct stat *identity) {
    struct stat root, held, named;
    if (fstat(state->root_fd, &root) || !icode_quota_same(&state->root_identity, &root) ||
        fstat(directory, &held) || !icode_quota_same(identity, &held) ||
        fstatat(state->root_fd, name, &named, AT_SYMLINK_NOFOLLOW) ||
        !icode_quota_same(identity, &named)) { errno = ESTALE; return -1; }
    return 0;
}

static inline int icode_quota_empty(int directory, int require_pids) {
    char text[4096];
    if (icode_quota_read(directory, "cgroup.events", text, sizeof(text))) return -1;
    int populated = -1;
    for (char *line = text; line && *line;) {
        char *next = strchr(line, '\n');
        if (next) *next++ = '\0';
        if (!strcmp(line, "populated 0")) { if (populated != -1) { errno = EINVAL; return -1; } populated = 0; }
        else if (!strncmp(line, "populated ", 10)) { errno = EBUSY; return -1; }
        line = next;
    }
    if (populated != 0) { errno = EINVAL; return -1; }
    if (icode_quota_read(directory, "cgroup.procs", text, sizeof(text))) return -1;
    if (*text) { errno = EBUSY; return -1; }
    if (require_pids) {
        if (icode_quota_read(directory, "pids.current", text, sizeof(text))) return -1;
        if (strcmp(text, "0\n")) { errno = EBUSY; return -1; }
    }
    return 0;
}

/* Walk only the current cgroup-v2 path, through pinned non-symlink handles.
 * Shared ancestors are root/self owned and not group/world writable; the
 * delegated scope itself must be owned by the current effective UID.
 */
static inline int icode_quota_open_scope(const char *unit) {
    char membership[PATH_MAX + 128], path[PATH_MAX];
    if (icode_quota_read(AT_FDCWD, "/proc/self/cgroup", membership, sizeof(membership))) return -1;
    int found = 0;
    for (char *line = membership; line && *line;) {
        char *next = strchr(line, '\n');
        if (!next) { errno = EINVAL; return -1; }
        *next++ = '\0';
        if (!strncmp(line, "0::", 3)) {
            if (++found != 1 || line[3] != '/' || strlen(line + 3) >= sizeof(path)) {
                errno = EINVAL; return -1;
            }
            strcpy(path, line + 3);
        }
        line = next;
    }
    const char *basename = found == 1 ? strrchr(path, '/') : NULL;
    if (!basename || strcmp(basename + 1, unit)) { errno = EINVAL; return -1; }
    int directory = open("/sys", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (directory < 0) return -1;
    const char *prefix[] = {"fs", "cgroup"};
    for (size_t i = 0; i < 2; i++) {
        int next = openat(directory, prefix[i], O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
        int saved = errno; close(directory); directory = next;
        if (directory < 0) { errno = saved; return -1; }
    }
    struct stat initial;
    struct statfs filesystem;
    if (fstat(directory, &initial) || fstatfs(directory, &filesystem) ||
        filesystem.f_type != CGROUP2_SUPER_MAGIC ||
        (initial.st_uid != 0 && initial.st_uid != geteuid()) ||
        (initial.st_mode & (S_IWGRP | S_IWOTH))) {
        close(directory); errno = EPERM; return -1;
    }
    for (char *part = path + 1; *part;) {
        char *slash = strchr(part, '/');
        if (slash) *slash = '\0';
        if (!*part || !strcmp(part, ".") || !strcmp(part, "..")) {
            close(directory); errno = EINVAL; return -1;
        }
        int next = openat(directory, part, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
        int saved = errno;
        close(directory); directory = next;
        if (directory < 0) { errno = saved; return -1; }
        struct stat status;
        if (fstat(directory, &status) || fstatfs(directory, &filesystem) ||
            status.st_dev != initial.st_dev || filesystem.f_type != CGROUP2_SUPER_MAGIC ||
            (status.st_uid != 0 && status.st_uid != geteuid()) ||
            (status.st_mode & (S_IWGRP | S_IWOTH)) || (!slash && status.st_uid != geteuid())) {
            close(directory); errno = EPERM; return -1;
        }
        if (!slash) break;
        part = slash + 1;
    }
    return directory;
}

static inline int icode_quota_new_leaf(struct icode_task_quota *state,
                                     const char *name, int *fd, struct stat *identity,
                                     int *created) {
    if (mkdirat(state->root_fd, name, 0755)) return -1;
    *created = 1;
    *fd = openat(state->root_fd, name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (*fd < 0 || fstat(*fd, identity)) return -1;
    if (identity->st_uid != geteuid() || identity->st_dev != state->root_identity.st_dev ||
        (identity->st_mode & (S_IWGRP | S_IWOTH))) { errno = EPERM; return -1; }
    return icode_quota_identity(state, *fd, name, identity);
}

/* Root membership alone does not establish exclusive ownership of its subtree.
 * Reject every pre-existing child, even an empty one. Inspect actual inode mode,
 * not readdir d_type; a separate open avoids changing the root handle's offset.
 */
static inline int icode_quota_no_children(int root_fd) {
    int fd = openat(root_fd, ".", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0) return -1;
    DIR *directory = fdopendir(fd);
    if (!directory) {
        int saved = errno;
        close(fd);
        errno = saved;
        return -1;
    }
    int failure = 0;
    for (;;) {
        errno = 0;
        struct dirent *entry = readdir(directory);
        if (!entry) { failure = errno; break; }
        if (!strcmp(entry->d_name, ".") || !strcmp(entry->d_name, "..")) continue;
        struct stat status;
        if (fstatat(root_fd, entry->d_name, &status, AT_SYMLINK_NOFOLLOW)) {
            failure = errno;
            break;
        }
        if (S_ISDIR(status.st_mode)) { failure = EEXIST; break; }
    }
    if (closedir(directory) && !failure) failure = errno;
    if (failure) { errno = failure; return -1; }
    return 0;
}

/* Never remove a name that predated prepare, nor delete a populated cgroup.
 * A moved supervisor stays occupied by the caller and is reclaimed by systemd
 * after scope exit. Even partial setup does not attempt broad manager cleanup.
 */
static inline void icode_quota_abort(struct icode_task_quota *state) {
    int saved = errno;
    if (state->created_payload && state->payload_fd >= 0 &&
        !icode_quota_identity(state, state->payload_fd, "payload", &state->payload_identity) &&
        !icode_quota_empty(state->payload_fd, 0))
        (void)unlinkat(state->root_fd, "payload", AT_REMOVEDIR);
    if (state->created_supervisor && state->supervisor_fd >= 0 &&
        !icode_quota_identity(state, state->supervisor_fd, "supervisor", &state->supervisor_identity) &&
        !icode_quota_empty(state->supervisor_fd, 0))
        (void)unlinkat(state->root_fd, "supervisor", AT_REMOVEDIR);
    icode_task_quota_close(state);
    errno = saved;
}

static inline int icode_task_quota_prepare(const char *unit, uint64_t limit,
                                         struct icode_task_quota *state) {
    if (!state || !icode_quota_unit_valid(unit) || !limit || limit > INT_MAX) {
        errno = EINVAL; return -1;
    }
    if (state->prepared || state->root_fd != -1 || state->supervisor_fd != -1 || state->payload_fd != -1) {
        errno = EALREADY; return -1;
    }
    state->root_fd = icode_quota_open_scope(unit);
    if (state->root_fd < 0) return -1;
    char text[4096], expected[64];
    if (fstat(state->root_fd, &state->root_identity) ||
        icode_quota_read(state->root_fd, "cgroup.procs", text, sizeof(text))) goto failure;
    snprintf(expected, sizeof(expected), "%ld\n", (long)getpid());
    if (strcmp(text, expected)) { errno = EBUSY; goto failure; }
    if (icode_quota_read(state->root_fd, "cgroup.controllers", text, sizeof(text))) goto failure;
    if (!icode_quota_has_word(text, "pids")) { errno = ENOTSUP; goto failure; }
    if (icode_quota_no_children(state->root_fd)) goto failure;
    struct stat existing;
    const char *names[] = {"supervisor", "payload"};
    for (size_t i = 0; i < 2; i++) {
        if (!fstatat(state->root_fd, names[i], &existing, AT_SYMLINK_NOFOLLOW)) {
            errno = EEXIST; goto failure;
        }
        if (errno != ENOENT) goto failure;
    }
    if (icode_quota_new_leaf(state, "supervisor", &state->supervisor_fd,
                             &state->supervisor_identity, &state->created_supervisor) ||
        icode_quota_new_leaf(state, "payload", &state->payload_fd,
                             &state->payload_identity, &state->created_payload)) goto failure;
    if (icode_quota_write(state->supervisor_fd, "cgroup.procs", expected) ||
        icode_quota_read(state->root_fd, "cgroup.procs", text, sizeof(text))) goto failure;
    if (*text) { errno = EBUSY; goto failure; }
    if (icode_quota_write(state->root_fd, "cgroup.subtree_control", "+pids") ||
        icode_quota_read(state->root_fd, "cgroup.subtree_control", text, sizeof(text))) goto failure;
    if (!icode_quota_has_word(text, "pids")) { errno = EIO; goto failure; }
    if (icode_quota_empty(state->payload_fd, 1)) goto failure;
    snprintf(expected, sizeof(expected), "%" PRIu64 "\n", limit);
    if (icode_quota_write(state->payload_fd, "pids.max", expected) ||
        icode_quota_read(state->payload_fd, "pids.max", text, sizeof(text))) goto failure;
    if (strcmp(text, expected)) { errno = EIO; goto failure; }
    if (icode_quota_identity(state, state->payload_fd, "payload", &state->payload_identity) ||
        icode_quota_identity(state, state->supervisor_fd, "supervisor", &state->supervisor_identity) ||
        icode_quota_empty(state->payload_fd, 1)) goto failure;
    state->limit = limit;
    state->prepared = 1;
    return 0;
failure:
    icode_quota_abort(state);
    return -1;
}

static inline pid_t icode_task_quota_fork(struct icode_task_quota *state) {
    if (!state || !state->prepared || state->payload_fd < 0) { errno = EINVAL; return -1; }
    if (icode_quota_identity(state, state->payload_fd, "payload", &state->payload_identity) ||
        icode_quota_identity(state, state->supervisor_fd, "supervisor", &state->supervisor_identity) ||
        icode_quota_empty(state->payload_fd, 1)) return -1;
    char configured[64], expected[64];
    snprintf(expected, sizeof(expected), "%" PRIu64 "\n", state->limit);
    if (icode_quota_read(state->payload_fd, "pids.max", configured, sizeof(configured))) return -1;
    if (strcmp(configured, expected)) { errno = EPERM; return -1; }
#ifdef SYS_clone3
    struct clone_args arguments;
    memset(&arguments, 0, sizeof(arguments));
    arguments.flags = CLONE_INTO_CGROUP;
    arguments.exit_signal = SIGCHLD;
    arguments.cgroup = (uint64_t)state->payload_fd;
    pid_t child = (pid_t)syscall(SYS_clone3, &arguments, sizeof(arguments));
    if (child == 0) icode_task_quota_close(state);
    return child;
#else
    errno = ENOSYS;
    return -1;
#endif
}

static inline int icode_task_quota_finish(struct icode_task_quota *state) {
    if (!state || !state->prepared || !state->created_payload || state->payload_fd < 0) {
        errno = EINVAL; return -1;
    }
    if (icode_quota_identity(state, state->payload_fd, "payload", &state->payload_identity) ||
        icode_quota_empty(state->payload_fd, 1) ||
        icode_quota_identity(state, state->payload_fd, "payload", &state->payload_identity)) return -1;
    /* Kernel rmdir also rejects populated cgroups; the exclusive scope is the
     * single-writer boundary against same-UID host-side name replacement. */
    if (unlinkat(state->root_fd, "payload", AT_REMOVEDIR)) return -1;
    close(state->payload_fd);
    state->payload_fd = -1;
    state->created_payload = 0;
    state->prepared = 0;
    return 0;
}
#endif
