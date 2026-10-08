/* Test-only delegated cgroup probe, not a shipped runner or readiness receipt. */
#define _GNU_SOURCE
#include "icode_task_quota.h"
#include <pthread.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>

#define CHECK(condition) do { if (!(condition)) { \
    fprintf(stderr, "probe:assertion_failed:%d\n", __LINE__); return 1; } } while (0)

static int read_text(int directory, const char *name, char *text, size_t size) {
    int fd = openat(directory, name, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) return -1;
    ssize_t n = read(fd, text, size - 1);
    int saved = errno;
    close(fd);
    errno = saved;
    if (n < 0 || (size_t)n == size - 1) return -1;
    text[n] = '\0';
    return 0;
}

static int fixture_root(void) {
    FILE *stream = fopen("/proc/self/cgroup", "re");
    if (!stream) return -1;
    char line[4096], path[4096];
    int found = 0;
    while (fgets(line, sizeof(line), stream)) {
        if (strncmp(line, "0::/", 4) == 0) {
            line[strcspn(line, "\n")] = '\0';
            if (snprintf(path, sizeof(path), "/sys/fs/cgroup%s", line + 3) >= (int)sizeof(path)) {
                fclose(stream); return -1;
            }
            found++;
        }
    }
    fclose(stream);
    return found == 1 ? open(path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC) : -1;
}

static int prerequisites(int root) {
    char text[4096];
    struct stat status;
    if (root < 0 || fstat(root, &status) || status.st_uid != geteuid() ||
        read_text(root, "cgroup.controllers", text, sizeof(text)) ||
        !strstr(text, "pids") || faccessat(root, "cgroup.procs", W_OK, 0) ||
        faccessat(root, "cgroup.subtree_control", W_OK, 0)) return 0;
#ifdef SYS_clone3
    errno = 0;
    (void)syscall(SYS_clone3, NULL, 0);
    if (errno == ENOSYS || errno == EPERM) return 0;
#else
    return 0;
#endif
    return 1;
}

static uint64_t counter(int directory, const char *name) {
    char text[512];
    if (read_text(directory, name, text, sizeof(text))) return UINT64_MAX;
    if (!strcmp(name, "pids.events")) {
        char *max = strstr(text, "max ");
        return max ? strtoull(max + 4, NULL, 10) : UINT64_MAX;
    }
    return strtoull(text, NULL, 10);
}

static int exists(int root, const char *name) {
    struct stat status;
    return fstatat(root, name, &status, AT_SYMLINK_NOFOLLOW) == 0;
}

struct child_report { int closed, created, denied, marker; };
static void *thread_marker(void *argument) {
    *(int *)argument = 1;
    return NULL;
}

static int payload(const char *mode, const int managed[3], int report, int release) {
    struct child_report result = {1, 0, 0, 0};
    for (int i = 0; i < 3; i++) {
        errno = 0;
        if (fcntl(managed[i], F_GETFD) != -1 || errno != EBADF) result.closed = 0;
    }
    pid_t descendant = -1;
    int descendant_release[2] = {-1, -1};
    if (!strcmp(mode, "cap2")) {
        int ready[2];
        if (pipe2(ready, O_CLOEXEC) || pipe2(descendant_release, O_CLOEXEC)) return 2;
        descendant = fork();
        if (descendant == 0) {
            char byte = '1';
            close(ready[0]); close(descendant_release[1]);
            if (write(ready[1], &byte, 1) != 1) _exit(2);
            close(ready[1]);
            if (read(descendant_release[0], &byte, 1) != 1) _exit(2);
            _exit(0);
        }
        close(ready[1]); close(descendant_release[0]);
        char byte;
        if (descendant < 0 || read(ready[0], &byte, 1) != 1) return 2;
        close(ready[0]); result.created = 1; result.marker = 1;
    } else if (!strcmp(mode, "cap1")) {
        descendant = fork();
        if (descendant == 0) _exit(3); /* Unexpected child is a failure, not a fake denial. */
        if (descendant > 0) {
            int status; waitpid(descendant, &status, 0); result.marker = 1;
        } else result.denied = errno;
    } else if (!strcmp(mode, "thread1")) {
        pthread_t thread;
        result.denied = pthread_create(&thread, NULL, thread_marker, &result.marker);
        if (!result.denied) pthread_join(thread, NULL);
    }
    if (write(report, &result, sizeof(result)) != (ssize_t)sizeof(result)) return 2;
    char byte;
    if (read(release, &byte, 1) != 1) return 2;
    if (!strcmp(mode, "cap2")) {
        int status;
        if (write(descendant_release[1], &byte, 1) != 1 ||
            waitpid(descendant, &status, 0) != descendant || !WIFEXITED(status) ||
            WEXITSTATUS(status) != 0) return 2;
        close(descendant_release[1]);
    }
    return 0;
}

static int invalid_inputs(void) {
    struct icode_task_quota state = ICODE_TASK_QUOTA_STATE_INIT;
    CHECK(state.root_fd == -1 && state.supervisor_fd == -1 && state.payload_fd == -1);
    const char *bad[] = {NULL, "", "../icode-task-0123456789abcdef0123456789abcdef.scope",
        "icode-task-0123456789ABCDEF0123456789abcdef.scope",
        "icode-task-0123456789abcdef0123456789abcdef.scope/", "app.scope"};
    for (size_t i = 0; i < sizeof(bad) / sizeof(bad[0]); i++) {
        errno = 0;
        CHECK(icode_task_quota_prepare(bad[i], 1, &state) == -1 && errno == EINVAL);
        CHECK(state.root_fd == -1 && state.supervisor_fd == -1 && state.payload_fd == -1);
    }
    const char *unit = "icode-task-0123456789abcdef0123456789abcdef.scope";
    const uint64_t bad_limits[] = {0, (uint64_t)INT_MAX + 1, UINT64_MAX};
    for (size_t i = 0; i < sizeof(bad_limits) / sizeof(bad_limits[0]); i++) {
        errno = 0;
        CHECK(icode_task_quota_prepare(unit, bad_limits[i], &state) == -1 && errno == EINVAL);
    }
    CHECK(icode_task_quota_prepare(unit, 1, NULL) == -1 && errno == EINVAL);
    CHECK(icode_task_quota_fork(&state) == -1);
    CHECK(icode_task_quota_finish(&state) == -1);
    icode_task_quota_close(&state);
    icode_task_quota_init(&state);
    CHECK(state.root_fd == -1 && state.supervisor_fd == -1 && state.payload_fd == -1);
    puts("probe:invalid_inputs_rejected=1");
    puts("probe:conformance_credit=none");
    return 0;
}

int main(int argc, char **argv) {
    alarm(10);
    if (argc == 2 && !strcmp(argv[1], "invalid")) return invalid_inputs();
    CHECK(argc == 3);
    const char *mode = argv[1], *unit = argv[2];
    int root = fixture_root();
    CHECK(root >= 0);
    struct icode_task_quota state = ICODE_TASK_QUOTA_STATE_INIT;
    if (!strcmp(mode, "scope-not-writable")) {
        /* Delegate=no alone does not revoke rights delegated at an ancestor.
         * Remove write permission only from this new exclusive scope so the
         * negative control actually lacks permission to create child cgroups.
         */
        struct stat status;
        CHECK(fstat(root, &status) == 0);
        int changed = status.st_uid == geteuid();
        if (changed) CHECK(fchmod(root, status.st_mode & 07777 & ~0222) == 0);
        int prepared = icode_task_quota_prepare(unit, 1, &state);
        if (changed) CHECK(fchmod(root, status.st_mode & 07777) == 0);
        CHECK(prepared == -1);
        CHECK(!exists(root, "payload") && !exists(root, "supervisor"));
        icode_task_quota_close(&state); close(root);
        puts("probe:scope_not_writable_rejected=1");
        puts("probe:conformance_credit=none"); return 0;
    }
    if (!prerequisites(root)) {
        close(root); puts("probe:prerequisite_unavailable=1"); return 77;
    }
    /* A correct-looking but different unit must not adopt this scope. */
    CHECK(icode_task_quota_prepare("icode-task-00000000000000000000000000000000.scope",
                                  1, &state) == -1);
    CHECK(!exists(root, "payload") && !exists(root, "supervisor"));
    if (!strcmp(mode, "nonexclusive")) {
        int ready[2], release[2];
        CHECK(pipe2(ready, O_CLOEXEC) == 0 && pipe2(release, O_CLOEXEC) == 0);
        pid_t extra = fork();
        CHECK(extra >= 0);
        if (extra == 0) {
            char byte = '1';
            close(ready[0]); close(release[1]);
            if (write(ready[1], &byte, 1) != 1 || read(release[0], &byte, 1) != 1) _exit(2);
            _exit(0);
        }
        close(ready[1]); close(release[0]);
        char byte; int status;
        CHECK(read(ready[0], &byte, 1) == 1);
        CHECK(icode_task_quota_prepare(unit, 1, &state) == -1 && errno == EBUSY);
        CHECK(!exists(root, "payload") && !exists(root, "supervisor"));
        CHECK(write(release[1], &byte, 1) == 1 && waitpid(extra, &status, 0) == extra &&
              WIFEXITED(status) && WEXITSTATUS(status) == 0);
        close(ready[0]); close(release[1]); close(root);
        puts("probe:nonexclusive_rejected=1"); puts("probe:conformance_credit=none"); return 0;
    }
    if (!strcmp(mode, "collision")) {
        CHECK(mkdirat(root, "payload", 0755) == 0);
        struct stat before, after;
        CHECK(fstatat(root, "payload", &before, AT_SYMLINK_NOFOLLOW) == 0);
        CHECK(icode_task_quota_prepare(unit, 1, &state) == -1);
        CHECK(!exists(root, "supervisor"));
        CHECK(fstatat(root, "payload", &after, AT_SYMLINK_NOFOLLOW) == 0 &&
              before.st_dev == after.st_dev && before.st_ino == after.st_ino);
        CHECK(unlinkat(root, "payload", AT_REMOVEDIR) == 0);
        close(root); puts("probe:collision_preserved=1");
        puts("probe:conformance_credit=none"); return 0;
    }
    if (!strcmp(mode, "other-empty") || !strcmp(mode, "other-populated")) {
        CHECK(mkdirat(root, "other", 0755) == 0);
        int other = openat(root, "other", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
        CHECK(other >= 0);
        struct stat before, after;
        char controller_before[512], controller_after[512];
        char members_before[4096], members_after[4096], root_members[4096], self[64];
        CHECK(fstat(other, &before) == 0);
        CHECK(read_text(root, "cgroup.subtree_control", controller_before, sizeof(controller_before)) == 0);
        int ready[2] = {-1, -1}, release[2] = {-1, -1};
        pid_t member = -1;
        if (!strcmp(mode, "other-populated")) {
            CHECK(pipe2(ready, O_CLOEXEC) == 0 && pipe2(release, O_CLOEXEC) == 0);
            member = fork();
            CHECK(member >= 0);
            if (member == 0) {
                alarm(8);
                char pid[64], byte = '1';
                close(ready[0]); close(release[1]);
                snprintf(pid, sizeof(pid), "%ld\n", (long)getpid());
                if (icode_quota_write(other, "cgroup.procs", pid) ||
                    write(ready[1], &byte, 1) != 1 || read(release[0], &byte, 1) != 1) _exit(2);
                _exit(0);
            }
            close(ready[1]); close(release[0]);
            char byte;
            CHECK(read(ready[0], &byte, 1) == 1);
        }
        /* This reproduces the review finding: only self in root is insufficient
         * when another process lives in an existing descendant cgroup.
         */
        snprintf(self, sizeof(self), "%ld\n", (long)getpid());
        CHECK(read_text(root, "cgroup.procs", root_members, sizeof(root_members)) == 0);
        CHECK(!strcmp(root_members, self));
        CHECK(read_text(other, "cgroup.procs", members_before, sizeof(members_before)) == 0);
        if (member > 0) {
            char expected_member[64];
            snprintf(expected_member, sizeof(expected_member), "%ld\n", (long)member);
            CHECK(!strcmp(members_before, expected_member));
        } else CHECK(!*members_before);
        int prepared = icode_task_quota_prepare(unit, 1, &state);
        int prepare_errno = errno;
        CHECK(prepared == -1 && prepare_errno == EEXIST);
        CHECK(!exists(root, "payload") && !exists(root, "supervisor"));
        CHECK(fstatat(root, "other", &after, AT_SYMLINK_NOFOLLOW) == 0 &&
              before.st_dev == after.st_dev && before.st_ino == after.st_ino);
        CHECK(read_text(other, "cgroup.procs", members_after, sizeof(members_after)) == 0 &&
              !strcmp(members_before, members_after));
        CHECK(read_text(root, "cgroup.subtree_control", controller_after, sizeof(controller_after)) == 0 &&
              !strcmp(controller_before, controller_after));
        CHECK(read_text(root, "cgroup.procs", root_members, sizeof(root_members)) == 0 &&
              !strcmp(root_members, self));
        CHECK(state.root_fd == -1 && state.supervisor_fd == -1 && state.payload_fd == -1);
        if (member > 0) {
            char byte = '1'; int status;
            CHECK(write(release[1], &byte, 1) == 1 && waitpid(member, &status, 0) == member &&
                  WIFEXITED(status) && WEXITSTATUS(status) == 0);
            close(ready[0]); close(release[1]);
        }
        CHECK(unlinkat(root, "other", AT_REMOVEDIR) == 0);
        icode_task_quota_close(&state); close(other); close(root);
        puts(member > 0 ? "probe:existing_populated_child_preserved=1" :
                          "probe:existing_empty_child_preserved=1");
        puts("probe:conformance_credit=none"); return 0;
    }
    unsigned limit = !strcmp(mode, "cap2") ? 2 : (!strcmp(mode, "max-cap") ? INT_MAX : 1);
    int prepared = icode_task_quota_prepare(unit, limit, &state);
    if (!strcmp(mode, "max-cap")) {
        if (prepared == 0) {
            CHECK(counter(state.payload_fd, "pids.max") == INT_MAX);
            CHECK(icode_task_quota_finish(&state) == 0 && !exists(root, "payload"));
        } else {
            /* Kernel pids.max may reject a legal API value above PID_MAX_LIMIT.
             * Never map that rejection to the unlimited "max" sentinel.
             */
            CHECK(prepared == -1 && !exists(root, "payload") && !state.prepared);
            CHECK(state.root_fd == -1 && state.supervisor_fd == -1 && state.payload_fd == -1);
        }
        icode_task_quota_close(&state); close(root);
        puts("probe:large_cap_exact_or_rejected=1"); puts("probe:conformance_credit=none"); return 0;
    }
    CHECK(prepared == 0);
    CHECK(icode_task_quota_prepare(unit, limit, &state) == -1 && errno == EALREADY);
    CHECK(counter(state.payload_fd, "pids.current") == 0);
    if (!strcmp(mode, "modified-limit")) {
        CHECK(icode_quota_write(state.payload_fd, "pids.max", "2\n") == 0);
        pid_t child = icode_task_quota_fork(&state);
        if (child == 0) _exit(3);
        if (child > 0) { int status; waitpid(child, &status, 0); }
        CHECK(child == -1 && counter(state.payload_fd, "pids.current") == 0);
        CHECK(icode_task_quota_finish(&state) == 0);
        icode_task_quota_close(&state); close(root);
        puts("probe:modified_limit_rejected=1"); puts("probe:conformance_credit=none"); return 0;
    }
    char supervisors[128], expected[128];
    CHECK(read_text(state.supervisor_fd, "cgroup.procs", supervisors, sizeof(supervisors)) == 0);
    snprintf(expected, sizeof(expected), "%ld\n", (long)getpid());
    CHECK(!strcmp(supervisors, expected));
    if (!strcmp(mode, "close")) {
        int managed[] = {state.root_fd, state.supervisor_fd, state.payload_fd};
        icode_task_quota_close(&state);
        CHECK(exists(root, "payload"));
        for (int i = 0; i < 3; i++) CHECK(fcntl(managed[i], F_GETFD) == -1 && errno == EBADF);
        CHECK(icode_task_quota_finish(&state) == -1);
        CHECK(unlinkat(root, "payload", AT_REMOVEDIR) == 0);
        close(root); puts("probe:close_is_not_finish=1");
        puts("probe:conformance_credit=none"); return 0;
    }
    if (!strcmp(mode, "replaced")) {
        CHECK(unlinkat(root, "payload", AT_REMOVEDIR) == 0);
        CHECK(mkdirat(root, "payload", 0755) == 0);
        CHECK(icode_task_quota_finish(&state) == -1 && exists(root, "payload"));
        CHECK(unlinkat(root, "payload", AT_REMOVEDIR) == 0);
        icode_task_quota_close(&state); close(root);
        puts("probe:replacement_preserved=1");
        puts("probe:conformance_credit=none"); return 0;
    }
    int report[2], release[2];
    CHECK(pipe2(report, O_CLOEXEC) == 0 && pipe2(release, O_CLOEXEC) == 0);
    int managed[] = {state.root_fd, state.supervisor_fd, state.payload_fd};
    uint64_t before_events = counter(state.payload_fd, "pids.events");
    CHECK(before_events != UINT64_MAX);
    pid_t child = icode_task_quota_fork(&state);
    if (child == 0) {
        close(root); close(report[0]); close(release[1]);
        _exit(payload(mode, managed, report[1], release[0]));
    }
    CHECK(child > 0);
    close(report[1]); close(release[0]);
    struct child_report result;
    CHECK(read(report[0], &result, sizeof(result)) == (ssize_t)sizeof(result));
    CHECK(result.closed == 1);
    uint64_t tasks = counter(state.payload_fd, "pids.current");
    CHECK(tasks == limit);
    CHECK(icode_task_quota_finish(&state) == -1 && errno == EBUSY && exists(root, "payload"));
    if (!strcmp(mode, "cap2")) CHECK(result.created == 1 && result.marker == 1);
    if (!strcmp(mode, "cap1") || !strcmp(mode, "thread1")) {
        CHECK(result.denied == EAGAIN && result.marker == 0);
        CHECK(counter(state.payload_fd, "pids.events") > before_events);
        puts("probe:creation_denied=EAGAIN");
        puts("probe:descendant_marker=0"); puts("probe:pids_event_increased=1");
    }
    char byte = '1'; int status;
    CHECK(write(release[1], &byte, 1) == 1);
    CHECK(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0);
    CHECK(icode_task_quota_finish(&state) == 0 && !exists(root, "payload"));
    printf("probe:payload_tasks=%llu\n", (unsigned long long)tasks);
    if (result.created) puts("probe:descendant_created=1");
    puts("probe:supervisor_outside_payload=1"); puts("probe:management_fds_closed=1");
    puts("probe:populated_cleanup_rejected=1"); puts("probe:empty_cleanup=1");
    puts("probe:conformance_credit=none");
    icode_task_quota_close(&state); close(root); close(report[0]); close(release[1]);
    return 0;
}
