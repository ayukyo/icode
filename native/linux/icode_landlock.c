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
#include <net/if.h>
#include <netinet/in.h>
#include <poll.h>
#include <sched.h>
#include <signal.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/ioctl.h>
#include <sys/random.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/uio.h>
#include <sys/wait.h>
#include <time.h>
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
#define ICODE_SOCK_TYPE_MASK 0x0fU
enum { ICODE_HANDOFF_NONCE_SIZE = 16 };

struct metadata_read_root {
    const char *path;
    uint64_t device;
    uint64_t inode;
};

struct execute_only_file {
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

static int close_inherited_descriptors(int preserved_descriptor) {
    if (preserved_descriptor < 0) {
        return (int)syscall(SYS_close_range, 3U, UINT_MAX, 0U);
    }
    if (preserved_descriptor < 3) {
        errno = EINVAL;
        return -1;
    }
    if (preserved_descriptor > 3 &&
        syscall(SYS_close_range, 3U,
                (unsigned int)preserved_descriptor - 1U, 0U) != 0) {
        return -1;
    }
    if (syscall(SYS_close_range,
                (unsigned int)preserved_descriptor + 1U, UINT_MAX, 0U) != 0) {
        return -1;
    }
    return 0;
}

static int validate_proxy_control_descriptor(int descriptor) {
    if (descriptor < 3) {
        errno = EINVAL;
        return -1;
    }
    int domain = 0;
    int type = 0;
    struct ucred peer = {0};
    socklen_t length = sizeof(int);
    if (getsockopt(descriptor, SOL_SOCKET, SO_DOMAIN, &domain, &length) != 0 ||
        length != sizeof(domain) || domain != AF_UNIX) {
        errno = EPERM;
        return -1;
    }
    length = sizeof(int);
    if (getsockopt(descriptor, SOL_SOCKET, SO_TYPE, &type, &length) != 0 ||
        length != sizeof(type) || type != SOCK_SEQPACKET) {
        errno = EPERM;
        return -1;
    }
    length = sizeof(peer);
    if (getsockopt(descriptor, SOL_SOCKET, SO_PEERCRED, &peer, &length) != 0 ||
        length != sizeof(peer) || peer.pid != getppid()) {
        errno = EPERM;
        return -1;
    }
    return 0;
}

static int validate_violation_control_descriptor(int descriptor) {
    if (descriptor < 3) {
        errno = EINVAL;
        return -1;
    }
    int domain = 0;
    int type = 0;
    struct ucred peer = {0};
    socklen_t length = sizeof(int);
    if (getsockopt(descriptor, SOL_SOCKET, SO_DOMAIN, &domain, &length) != 0 ||
        length != sizeof(domain) || domain != AF_UNIX) {
        errno = EPERM;
        return -1;
    }
    length = sizeof(int);
    if (getsockopt(descriptor, SOL_SOCKET, SO_TYPE, &type, &length) != 0 ||
        length != sizeof(type) || type != SOCK_SEQPACKET) {
        errno = EPERM;
        return -1;
    }
    length = sizeof(peer);
    if (getsockopt(descriptor, SOL_SOCKET, SO_PEERCRED, &peer, &length) != 0 ||
        length != sizeof(peer) || peer.pid != getppid()) {
        errno = EPERM;
        return -1;
    }
    return 0;
}

static int send_seccomp_listener_handoff(int control_descriptor, int listener) {
    static const char handoff_message[] = "ICODE_SECCOMP_LISTENER_V1";
    static const char expected_ack[] = "ICODE_SECCOMP_LISTENER_ACK_V1";
    struct iovec data = {
        .iov_base = (void *)handoff_message,
        .iov_len = sizeof(handoff_message) - 1,
    };
    union {
        struct cmsghdr alignment;
        char bytes[CMSG_SPACE(sizeof(listener))];
    } ancillary = {0};
    struct msghdr message = {
        .msg_iov = &data,
        .msg_iovlen = 1,
        .msg_control = ancillary.bytes,
        .msg_controllen = sizeof(ancillary.bytes),
    };
    struct cmsghdr *header = CMSG_FIRSTHDR(&message);
    if (!header) {
        errno = EINVAL;
        return -1;
    }
    header->cmsg_level = SOL_SOCKET;
    header->cmsg_type = SCM_RIGHTS;
    header->cmsg_len = CMSG_LEN(sizeof(listener));
    memcpy(CMSG_DATA(header), &listener, sizeof(listener));

    ssize_t sent;
    do {
        sent = sendmsg(control_descriptor, &message, MSG_NOSIGNAL);
    } while (sent < 0 && errno == EINTR);
    if (sent != (ssize_t)(sizeof(handoff_message) - 1)) {
        if (sent >= 0) errno = EIO;
        return -1;
    }

    struct pollfd wait_socket = {.fd = control_descriptor, .events = POLLIN};
    int ready;
    do {
        ready = poll(&wait_socket, 1, 5000);
    } while (ready < 0 && errno == EINTR);
    if (ready <= 0 || !(wait_socket.revents & POLLIN)) {
        if (ready == 0) errno = ETIMEDOUT;
        else if (ready > 0) errno = EPIPE;
        return -1;
    }

    unsigned char payload[sizeof(expected_ack)];
    union {
        struct cmsghdr alignment;
        char bytes[CMSG_SPACE(sizeof(int) * 4)];
    } response_ancillary = {0};
    struct iovec response_data = {
        .iov_base = payload,
        .iov_len = sizeof(payload),
    };
    struct msghdr response = {
        .msg_iov = &response_data,
        .msg_iovlen = 1,
        .msg_control = response_ancillary.bytes,
        .msg_controllen = sizeof(response_ancillary.bytes),
    };
    ssize_t received;
    do {
        received = recvmsg(control_descriptor, &response, MSG_CMSG_CLOEXEC);
    } while (received < 0 && errno == EINTR);
    int malformed = (response.msg_flags & (MSG_TRUNC | MSG_CTRUNC)) != 0;
    for (struct cmsghdr *item = CMSG_FIRSTHDR(&response); item;
         item = CMSG_NXTHDR(&response, item)) {
        if (item->cmsg_level == SOL_SOCKET &&
            item->cmsg_type == SCM_RIGHTS && item->cmsg_len >= CMSG_LEN(0)) {
            size_t bytes = item->cmsg_len - CMSG_LEN(0);
            size_t complete = bytes - (bytes % sizeof(int));
            const unsigned char *raw = (const unsigned char *)CMSG_DATA(item);
            for (size_t offset = 0; offset < complete; offset += sizeof(int)) {
                int unexpected = -1;
                memcpy(&unexpected, raw + offset, sizeof(unexpected));
                if (unexpected >= 0) close(unexpected);
            }
        }
        malformed = 1;
    }
    if (received != (ssize_t)(sizeof(expected_ack) - 1) || malformed ||
        memcmp(payload, expected_ack, sizeof(expected_ack) - 1) != 0) {
        errno = EPROTO;
        return -1;
    }
    return 0;
}

static int64_t monotonic_milliseconds(void) {
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC, &now) != 0) return -1;
    return (int64_t)now.tv_sec * 1000 + (int64_t)now.tv_nsec / 1000000;
}

static int fill_handoff_nonce(unsigned char *nonce, size_t length) {
    size_t offset = 0;
    while (offset < length) {
        ssize_t received = getrandom(
            nonce + offset, length - offset, GRND_NONBLOCK);
        if (received < 0 && errno == EINTR) continue;
        if (received <= 0) {
            if (received == 0) errno = EIO;
            return -1;
        }
        offset += (size_t)received;
    }
    return 0;
}

static int wait_for_proxy_handoff_ack(
    int descriptor,
    const unsigned char *nonce,
    size_t nonce_length
) {
    static const char expected_ack[] = "ICODE_PROXY_LISTENER_ACK_V1";
    unsigned char expected_payload[
        sizeof(expected_ack) - 1 + ICODE_HANDOFF_NONCE_SIZE];
    if (nonce_length != ICODE_HANDOFF_NONCE_SIZE ||
        nonce_length > sizeof(expected_payload) -
        (sizeof(expected_ack) - 1)) {
        errno = EINVAL;
        return -1;
    }
    memcpy(expected_payload, expected_ack, sizeof(expected_ack) - 1);
    memcpy(expected_payload + sizeof(expected_ack) - 1, nonce, nonce_length);
    int64_t start = monotonic_milliseconds();
    if (start < 0) return -1;
    int64_t deadline = start + 30000;

    for (;;) {
        int64_t now = monotonic_milliseconds();
        if (now < 0) return -1;
        int64_t remaining = deadline - now;
        if (remaining <= 0) {
            errno = ETIMEDOUT;
            return -1;
        }
        struct pollfd wait_socket = {.fd = descriptor, .events = POLLIN};
        int ready = poll(&wait_socket, 1,
                         remaining > INT_MAX ? INT_MAX : (int)remaining);
        if (ready < 0 && errno == EINTR) continue;
        if (ready < 0) return -1;
        if (ready == 0) continue;
        if (!(wait_socket.revents & POLLIN)) {
            errno = EPIPE;
            return -1;
        }

        unsigned char payload[sizeof(expected_payload)];
        union {
            struct cmsghdr alignment;
            char bytes[CMSG_SPACE(sizeof(int) * 4)];
        } ancillary = {0};
        struct iovec data = {.iov_base = payload, .iov_len = sizeof(payload)};
        struct msghdr message = {
            .msg_iov = &data,
            .msg_iovlen = 1,
            .msg_control = ancillary.bytes,
            .msg_controllen = sizeof(ancillary.bytes),
        };
        ssize_t received = recvmsg(descriptor, &message, MSG_CMSG_CLOEXEC);
        if (received < 0 && errno == EINTR) continue;
        if (received < 0) return -1;

        int malformed = (message.msg_flags & (MSG_TRUNC | MSG_CTRUNC)) != 0;
        for (struct cmsghdr *header = CMSG_FIRSTHDR(&message); header;
             header = CMSG_NXTHDR(&message, header)) {
            if (header->cmsg_level == SOL_SOCKET &&
                header->cmsg_type == SCM_RIGHTS &&
                header->cmsg_len >= CMSG_LEN(0)) {
                size_t bytes = header->cmsg_len - CMSG_LEN(0);
                size_t complete = bytes - (bytes % sizeof(int));
                const unsigned char *raw = (const unsigned char *)CMSG_DATA(header);
                for (size_t offset = 0; offset < complete; offset += sizeof(int)) {
                    int unexpected = -1;
                    memcpy(&unexpected, raw + offset, sizeof(unexpected));
                    if (unexpected >= 0) close(unexpected);
                }
            }
            malformed = 1;
        }
        if (malformed || received != (ssize_t)(sizeof(expected_payload)) ||
            memcmp(payload, expected_payload, sizeof(expected_payload)) != 0) {
            errno = EPROTO;
            return -1;
        }
        return 0;
    }
}

static int handoff_loopback_listener(int control_descriptor) {
    static const char handoff_message[] = "ICODE_PROXY_LISTENER_V1";
    int listener = -1;
    struct sockaddr_in address = {0};
    socklen_t address_length = sizeof(address);
    char endpoint[64];
    unsigned char nonce[ICODE_HANDOFF_NONCE_SIZE];
    unsigned char handoff_payload[
        sizeof(handoff_message) - 1 + ICODE_HANDOFF_NONCE_SIZE];

    /* SCM_RIGHTS shares the open-file-description status flags with the host.
     * Nonblocking accept is required before the listener is handed off so a
     * stale readiness event cannot strand the host proxy in blocking accept. */
    listener = socket(
        AF_INET, SOCK_STREAM | SOCK_CLOEXEC | SOCK_NONBLOCK, IPPROTO_TCP);
    if (listener < 0) goto fail;
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    address.sin_port = 0;
    if (bind(listener, (struct sockaddr *)&address, sizeof(address)) != 0 ||
        listen(listener, 16) != 0 ||
        getsockname(listener, (struct sockaddr *)&address, &address_length) != 0)
        goto fail;
    if (address_length != sizeof(address) ||
        address.sin_addr.s_addr != htonl(INADDR_LOOPBACK) ||
        ntohs(address.sin_port) == 0) {
        errno = EINVAL;
        goto fail;
    }
    int endpoint_size = snprintf(endpoint, sizeof(endpoint), "127.0.0.1:%u",
                                 (unsigned int)ntohs(address.sin_port));
    if (endpoint_size < 0 || (size_t)endpoint_size >= sizeof(endpoint)) {
        errno = EINVAL;
        goto fail;
    }
    if (setenv("ICODE_PROXY_LISTENER", endpoint, 1) != 0) {
        goto fail;
    }
    if (fill_handoff_nonce(nonce, sizeof(nonce)) != 0) goto fail;
    memcpy(handoff_payload, handoff_message, sizeof(handoff_message) - 1);
    memcpy(handoff_payload + sizeof(handoff_message) - 1,
           nonce, sizeof(nonce));

    struct iovec data = {
        .iov_base = handoff_payload,
        .iov_len = sizeof(handoff_payload),
    };
    union {
        struct cmsghdr alignment;
        char bytes[CMSG_SPACE(sizeof(listener))];
    } ancillary = {0};
    struct msghdr message = {
        .msg_iov = &data,
        .msg_iovlen = 1,
        .msg_control = ancillary.bytes,
        .msg_controllen = sizeof(ancillary.bytes),
    };
    struct cmsghdr *header = CMSG_FIRSTHDR(&message);
    if (!header) {
        errno = EINVAL;
        goto fail;
    }
    header->cmsg_level = SOL_SOCKET;
    header->cmsg_type = SCM_RIGHTS;
    header->cmsg_len = CMSG_LEN(sizeof(listener));
    memcpy(CMSG_DATA(header), &listener, sizeof(listener));
    ssize_t sent;
    do {
        sent = sendmsg(control_descriptor, &message, MSG_NOSIGNAL);
    } while (sent < 0 && errno == EINTR);
    if (sent != (ssize_t)sizeof(handoff_payload)) {
        if (sent >= 0) errno = EIO;
        goto fail;
    }
    if (wait_for_proxy_handoff_ack(
            control_descriptor, nonce, sizeof(nonce)) != 0) goto fail;

    if (close(listener) != 0) goto fail;
    listener = -1;
    if (close(control_descriptor) != 0) goto fail;
    return 0;

fail: {
        int saved_errno = errno ? errno : EIO;
        if (listener >= 0) close(listener);
        close(control_descriptor);
        unsetenv("ICODE_PROXY_LISTENER");
        errno = saved_errno;
        perror("loopback listener handoff");
        return -1;
    }
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

static int install_execute_only(const struct execute_only_file *allowed_files,
                                size_t allowed_file_count) {
    if (!allowed_files || allowed_file_count == 0) {
        errno = EINVAL;
        return -1;
    }
    int ruleset = (int)syscall(
        SYS_landlock_create_ruleset,
        &(struct landlock_ruleset_attr){
            .handled_access_fs = LANDLOCK_ACCESS_FS_EXECUTE,
        },
        sizeof(struct landlock_ruleset_attr), 0);
    if (ruleset < 0) {
        perror("execute-only ruleset");
        return -1;
    }

    for (size_t i = 0; i < allowed_file_count; ++i) {
        const struct execute_only_file *allowed_file = &allowed_files[i];
        int file_fd = open_metadata_path(allowed_file->path);
        if (file_fd < 0) {
            fprintf(stderr, "execute-only file rejected\n");
            close(ruleset);
            return -1;
        }
        struct stat status;
        if (fstat(file_fd, &status) != 0 || !S_ISREG(status.st_mode) ||
            (uint64_t)status.st_dev != allowed_file->device ||
            (uint64_t)status.st_ino != allowed_file->inode) {
            fprintf(stderr, "execute-only file identity changed\n");
            close(file_fd);
            close(ruleset);
            return -1;
        }
        struct landlock_path_beneath_attr rule = {
            .allowed_access = LANDLOCK_ACCESS_FS_EXECUTE,
            .parent_fd = file_fd,
        };
        int result = (int)syscall(SYS_landlock_add_rule, ruleset,
                                  LANDLOCK_RULE_PATH_BENEATH, &rule, 0);
        close(file_fd);
        if (result != 0) {
            perror("execute-only file rule");
            close(ruleset);
            return -1;
        }
    }
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0 ||
        syscall(SYS_landlock_restrict_self, ruleset, 0) != 0) {
        perror("execute-only restrict self");
        close(ruleset);
        return -1;
    }
    close(ruleset);
    return 0;
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

static int install_network_deny(int violation_control_descriptor) {
    /*
     * Ordinary helper runs preserve direct ERRNO denial. When the trusted host
     * broker explicitly requests a receipt, denied socket syscalls instead go
     * through USER_NOTIF; the broker only answers EPERM and must ACK before
     * the payload is allowed to exec.
     */
    unsigned int deny_action = violation_control_descriptor >= 0
        ? SECCOMP_RET_USER_NOTIF
        : (SECCOMP_RET_ERRNO | EPERM);
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
        /* No socket() calls; keep only AF_UNIX socketpair() for local IPC. */
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, SYS_socket, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, deny_action),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, SYS_socketpair, 0, 13),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS,
                 offsetof(struct seccomp_data, args[0])),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, AF_UNIX, 1, 0),
        BPF_STMT(BPF_RET | BPF_K, deny_action),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS,
                 offsetof(struct seccomp_data, args[1])),
        BPF_STMT(BPF_ALU | BPF_AND | BPF_K, ICODE_SOCK_TYPE_MASK),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, SOCK_STREAM, 2, 0),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, SOCK_DGRAM, 1, 0),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, SOCK_SEQPACKET, 0, 2),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS,
                 offsetof(struct seccomp_data, args[2])),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, 0, 1, 0),
        BPF_STMT(BPF_RET | BPF_K, deny_action),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW),
        BPF_STMT(BPF_RET | BPF_K, deny_action),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, SYS_io_uring_setup, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, deny_action),
        /* PID namespace lifetime, not process-group membership, owns cleanup. */
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW),
    };
    struct sock_fprog program = {
        .len = (unsigned short)(sizeof(instructions) / sizeof(instructions[0])),
        .filter = instructions,
    };
    if (violation_control_descriptor < 0) {
        if (prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &program) != 0) {
            perror("PR_SET_SECCOMP");
            return -1;
        }
        return 0;
    }

    int listener = (int)syscall(
        SYS_seccomp,
        SECCOMP_SET_MODE_FILTER,
        SECCOMP_FILTER_FLAG_NEW_LISTENER,
        &program);
    if (listener < 0) {
        perror("seccomp NEW_LISTENER");
        return -1;
    }
    int handoff_result = send_seccomp_listener_handoff(
        violation_control_descriptor, listener);
    int saved_errno = errno;
    if (close(listener) != 0 && handoff_result == 0) {
        saved_errno = errno;
        handoff_result = -1;
    }
    if (handoff_result != 0) {
        errno = saved_errno ? saved_errno : EIO;
        perror("seccomp listener handoff");
        return -1;
    }
    return 0;
}

static int install_network_loopback_only(void) {
    /*
     * This private helper mode is a bridge prerequisite, not a product grant:
     * its network namespace has only an enabled loopback interface. The filter
     * permits TCP stream sockets for a future local proxy, but denies UDP,
     * raw, AF_UNIX socket() calls and other socket families. socketpair() is
     * restricted to AF_UNIX local IPC (stream/datagram/seqpacket, protocol 0).
     * Without a bridge, a task cannot reach services in the host namespace
     * through 127.0.0.1.
     */
    struct sock_filter instructions[] = {
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS,
                 offsetof(struct seccomp_data, arch)),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, ICODE_AUDIT_ARCH, 1, 0),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS,
                 offsetof(struct seccomp_data, nr)),
#if defined(__x86_64__)
        /* x32 shares AUDIT_ARCH_X86_64 but adds a syscall-number bit. */
        BPF_JUMP(BPF_JMP | BPF_JSET | BPF_K, ICODE_X32_SYSCALL_BIT, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS),
#endif
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, SYS_io_uring_setup, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM),
        /* Validate network-capable socket() separately from local socketpair(). */
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, SYS_socket, 0, 11),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS,
                 offsetof(struct seccomp_data, args[0])),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, AF_INET, 1, 0),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, AF_INET6, 0, 7),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS,
                 offsetof(struct seccomp_data, args[1])),
        BPF_STMT(BPF_ALU | BPF_AND | BPF_K, ICODE_SOCK_TYPE_MASK),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, SOCK_STREAM, 0, 4),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS,
                 offsetof(struct seccomp_data, args[2])),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, 0, 1, 0),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, IPPROTO_TCP, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, SYS_socketpair, 0, 13),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS,
                 offsetof(struct seccomp_data, args[0])),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, AF_UNIX, 1, 0),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS,
                 offsetof(struct seccomp_data, args[1])),
        BPF_STMT(BPF_ALU | BPF_AND | BPF_K, ICODE_SOCK_TYPE_MASK),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, SOCK_STREAM, 2, 0),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, SOCK_DGRAM, 1, 0),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, SOCK_SEQPACKET, 0, 2),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS,
                 offsetof(struct seccomp_data, args[2])),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, 0, 1, 0),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW),
    };
    struct sock_fprog program = {
        .len = (unsigned short)(sizeof(instructions) / sizeof(instructions[0])),
        .filter = instructions,
    };
    if (prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &program) != 0) {
        perror("PR_SET_SECCOMP loopback-only");
        return -1;
    }
    return 0;
}

static void report_loopback_setup_failure(const char *stage, const char *message) {
    int saved_errno = errno;
    fprintf(stderr, "ICODE_LOOPBACK_SETUP_FAILURE stage=%s errno=%d\n",
            stage, saved_errno);
    errno = saved_errno;
    perror(message);
    errno = saved_errno;
}

static int bring_loopback_up(void) {
    int fd = socket(AF_INET, SOCK_DGRAM | SOCK_CLOEXEC, 0);
    if (fd < 0) {
        report_loopback_setup_failure("socket", "open loopback control socket");
        return -1;
    }
    struct ifreq interface = {0};
    if (strlen("lo") >= sizeof(interface.ifr_name)) {
        close(fd);
        errno = EINVAL;
        report_loopback_setup_failure("validate", "loopback interface name");
        return -1;
    }
    memcpy(interface.ifr_name, "lo", sizeof("lo"));
    if (ioctl(fd, SIOCGIFFLAGS, &interface) != 0) {
        report_loopback_setup_failure("read", "read loopback interface flags");
        close(fd);
        return -1;
    }
    interface.ifr_flags = (short)(interface.ifr_flags | IFF_UP);
    if (ioctl(fd, SIOCSIFFLAGS, &interface) != 0) {
        report_loopback_setup_failure("enable", "enable loopback interface");
        close(fd);
        return -1;
    }
    if (close(fd) != 0) {
        report_loopback_setup_failure("close", "close loopback control socket");
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
                                 const char *uid_map_path,
                                 int network_loopback_only) {
    uid_t outer_uid = geteuid();
    gid_t outer_gid = getegid();
    int namespace_flags = CLONE_NEWUSER | CLONE_NEWPID;
    if (network_loopback_only) namespace_flags |= CLONE_NEWNET;
    if (unshare(namespace_flags) != 0) {
        perror(network_loopback_only
            ? "unshare user/pid/network namespace"
            : "unshare user/pid namespace");
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
            install_parent_death_signal(host_parent) != 0 ||
            (network_loopback_only && bring_loopback_up() != 0)) return -1;
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
    if (install_parent_death_signal(host_parent) != 0 ||
        (network_loopback_only && bring_loopback_up() != 0)) return -1;
    return 0;
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
                              size_t metadata_root_count,
                              const struct execute_only_file *execute_only,
                              size_t execute_only_count,
                              char **command,
                              int workspace_read_only, int mapless,
                              int network_loopback_only,
                              int violation_control_descriptor) {
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
            (execute_only && install_execute_only(
                execute_only, execute_only_count) != 0) ||
            (network_loopback_only
                ? install_network_loopback_only()
                : install_network_deny(violation_control_descriptor)) != 0) _exit(1);
        if (violation_control_descriptor >= 0 &&
            close(violation_control_descriptor) != 0) _exit(1);
        execvp(command[0], command);
        perror("execvp");
        _exit(127);
    }
    if (violation_control_descriptor >= 0) {
        close(violation_control_descriptor);
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
                          size_t metadata_root_count,
                          const struct execute_only_file *execute_only,
                          size_t execute_only_count,
                          char **command,
                          int workspace_read_only,
                          int network_loopback_only,
                          int proxy_control_descriptor,
                          int violation_control_descriptor,
                          const char *setgroups_path,
                          const char *uid_map_path) {
    int mapless = enter_task_namespaces(
        host_parent, setgroups_path, uid_map_path, network_loopback_only);
    if (mapless < 0) return 1;
    if (proxy_control_descriptor >= 0 &&
        handoff_loopback_listener(proxy_control_descriptor) != 0) {
        return 1;
    }
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
            metadata_roots, metadata_root_count, execute_only,
            execute_only_count, command,
            workspace_read_only, mapless, network_loopback_only,
            violation_control_descriptor);
        close(control[0]);
        _exit(result);
    }
    close(control[0]);
    if (violation_control_descriptor >= 0) {
        close(violation_control_descriptor);
    }
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
    if (argc < 7 || strcmp(argv[1], "--workspace") != 0 ||
        strcmp(argv[3], "--parent-pid") != 0) {
        fprintf(stderr,
                "usage: icode-landlock --workspace PATH --parent-pid PID "
                "[--workspace-read-only] [--network-loopback-only] "
                "[--proxy-control-fd FD | --violation-control-fd FD] "
                "[--runtime-read PATH]... "
                "[--metadata-read PATH DEVICE INODE]... "
                "[--execute-only PATH DEVICE INODE] "
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
    struct execute_only_file *execute_only = calloc(
        (size_t)argc, sizeof(*execute_only));
    if (!runtime_roots || !metadata_roots || !execute_only) {
        perror("calloc");
        free(runtime_roots);
        free(metadata_roots);
        free(execute_only);
        return 2;
    }
    size_t runtime_root_count = 0;
    size_t metadata_root_count = 0;
    size_t execute_only_count = 0;
    int workspace_read_only = 0;
    int network_loopback_only = 0;
    int proxy_control_descriptor = -1;
    int violation_control_descriptor = -1;
    int command_index = 5;
    while (command_index < argc && strcmp(argv[command_index], "--") != 0) {
        if (strcmp(argv[command_index], "--workspace-read-only") == 0) {
            if (workspace_read_only) {
                fprintf(stderr, "duplicate workspace read-only option\n");
                free(runtime_roots);
                free(metadata_roots);
                free(execute_only);
                return 2;
            }
            workspace_read_only = 1;
            command_index += 1;
        } else if (strcmp(argv[command_index], "--network-loopback-only") == 0) {
            if (network_loopback_only) {
                fprintf(stderr, "duplicate loopback-only network option\n");
                free(runtime_roots);
                free(metadata_roots);
                free(execute_only);
                return 2;
            }
            network_loopback_only = 1;
            command_index += 1;
        } else if (strcmp(argv[command_index], "--proxy-control-fd") == 0) {
            uint64_t descriptor_value = 0;
            if (proxy_control_descriptor >= 0 ||
                command_index + 1 >= argc ||
                parse_u64_decimal(argv[command_index + 1], &descriptor_value) != 0 ||
                descriptor_value < 3 || descriptor_value > INT_MAX) {
                fprintf(stderr, "invalid proxy control descriptor\n");
                free(runtime_roots);
                free(metadata_roots);
                free(execute_only);
                return 2;
            }
            proxy_control_descriptor = (int)descriptor_value;
            command_index += 2;
        } else if (strcmp(argv[command_index], "--violation-control-fd") == 0) {
            uint64_t descriptor_value = 0;
            if (violation_control_descriptor >= 0 ||
                command_index + 1 >= argc ||
                parse_u64_decimal(argv[command_index + 1], &descriptor_value) != 0 ||
                descriptor_value < 3 || descriptor_value > INT_MAX) {
                fprintf(stderr, "invalid violation control descriptor\n");
                free(runtime_roots);
                free(metadata_roots);
                free(execute_only);
                return 2;
            }
            violation_control_descriptor = (int)descriptor_value;
            command_index += 2;
        } else if (strcmp(argv[command_index], "--runtime-read") == 0) {
            if (command_index + 1 >= argc || argv[command_index + 1][0] != '/') {
                fprintf(stderr, "invalid runtime root\n");
                free(runtime_roots);
                free(metadata_roots);
                free(execute_only);
                return 2;
            }
            runtime_roots[runtime_root_count++] = argv[command_index + 1];
            command_index += 2;
        } else if (strcmp(argv[command_index], "--metadata-read") == 0) {
            if (command_index + 3 >= argc || argv[command_index + 1][0] != '/') {
                fprintf(stderr, "invalid metadata root\n");
                free(runtime_roots);
                free(metadata_roots);
                free(execute_only);
                return 2;
            }
            struct metadata_read_root root = {.path = argv[command_index + 1]};
            if (parse_u64_decimal(argv[command_index + 2], &root.device) != 0) {
                fprintf(stderr, "invalid metadata device identity\n");
                free(runtime_roots);
                free(metadata_roots);
                free(execute_only);
                return 2;
            }
            if (parse_u64_decimal(argv[command_index + 3], &root.inode) != 0) {
                fprintf(stderr, "invalid metadata inode identity\n");
                free(runtime_roots);
                free(metadata_roots);
                free(execute_only);
                return 2;
            }
            for (size_t i = 0; i < metadata_root_count; ++i) {
                if (strcmp(metadata_roots[i].path, root.path) == 0) {
                    fprintf(stderr, "duplicate metadata root\n");
                    free(runtime_roots);
                    free(metadata_roots);
                    free(execute_only);
                    return 2;
                }
            }
            metadata_roots[metadata_root_count++] = root;
            command_index += 4;
        } else if (strcmp(argv[command_index], "--execute-only") == 0) {
            if (command_index + 3 >= argc || argv[command_index + 1][0] != '/') {
                fprintf(stderr, "invalid execute-only file\n");
                free(runtime_roots);
                free(metadata_roots);
                free(execute_only);
                return 2;
            }
            struct execute_only_file file = {.path = argv[command_index + 1]};
            if (parse_u64_decimal(argv[command_index + 2], &file.device) != 0 ||
                parse_u64_decimal(argv[command_index + 3], &file.inode) != 0) {
                fprintf(stderr, "invalid execute-only identity\n");
                free(runtime_roots);
                free(metadata_roots);
                free(execute_only);
                return 2;
            }
            for (size_t i = 0; i < execute_only_count; ++i) {
                if (strcmp(execute_only[i].path, file.path) == 0) {
                    fprintf(stderr, "duplicate execute-only file\n");
                    free(runtime_roots);
                    free(metadata_roots);
                    free(execute_only);
                    return 2;
                }
            }
            execute_only[execute_only_count++] = file;
            command_index += 4;
        } else {
            fprintf(stderr, "unknown read-only root option\n");
            free(runtime_roots);
            free(metadata_roots);
            free(execute_only);
            return 2;
        }
    }
    if (command_index + 1 >= argc) {
        fprintf(stderr, "missing command\n");
        free(runtime_roots);
        free(metadata_roots);
        free(execute_only);
        return 2;
    }
    ++command_index;
    if (proxy_control_descriptor >= 0 &&
        (violation_control_descriptor >= 0 || !network_loopback_only)) {
        fprintf(stderr, "proxy control descriptor requires loopback-only mode\n");
        free(runtime_roots);
        free(metadata_roots);
        free(execute_only);
        return 2;
    }
    if (violation_control_descriptor >= 0 && network_loopback_only) {
        fprintf(stderr, "violation control descriptor requires network-deny mode\n");
        free(runtime_roots);
        free(metadata_roots);
        free(execute_only);
        return 2;
    }
    if (proxy_control_descriptor >= 0 &&
        validate_proxy_control_descriptor(proxy_control_descriptor) != 0) {
        fprintf(stderr, "proxy control descriptor is not a trusted channel\n");
        free(runtime_roots);
        free(metadata_roots);
        free(execute_only);
        return 1;
    }
    if (violation_control_descriptor >= 0 &&
        validate_violation_control_descriptor(violation_control_descriptor) != 0) {
        fprintf(stderr, "violation control descriptor is not a trusted channel\n");
        free(runtime_roots);
        free(metadata_roots);
        free(execute_only);
        return 1;
    }
    /* Preserve only the one authenticated bootstrap endpoint, if requested. */
    int preserved_descriptor = proxy_control_descriptor >= 0
        ? proxy_control_descriptor : violation_control_descriptor;
    if (close_inherited_descriptors(preserved_descriptor) != 0) {
        perror("close_range inherited descriptors");
        if (proxy_control_descriptor >= 0) close(proxy_control_descriptor);
        if (violation_control_descriptor >= 0) close(violation_control_descriptor);
        free(runtime_roots);
        free(metadata_roots);
        free(execute_only);
        return 1;
    }
    if (install_parent_death_signal((pid_t)parent_value) != 0 ||
        restore_child_reaping() != 0) {
        free(runtime_roots);
        free(metadata_roots);
        free(execute_only);
        return 1;
    }
    char *workspace = realpath(argv[2], NULL);
    if (!workspace) {
        perror("workspace realpath");
        free(runtime_roots);
        free(metadata_roots);
        free(execute_only);
        return 2;
    }
    if (chdir(workspace) != 0) {
        perror("chdir workspace");
        free(workspace);
        free(runtime_roots);
        free(metadata_roots);
        free(execute_only);
        return 1;
    }
    int result = supervise_task(
        (pid_t)parent_value, workspace, runtime_roots, runtime_root_count,
        metadata_roots, metadata_root_count,
        execute_only_count > 0 ? execute_only : NULL, execute_only_count,
        argv + command_index,
        workspace_read_only, network_loopback_only,
        proxy_control_descriptor, violation_control_descriptor,
        setgroups_path, uid_map_path);
    free(workspace);
    free(runtime_roots);
    free(metadata_roots);
    free(execute_only);
    return result;
}

int main(int argc, char **argv) {
    return run_helper(argc, argv, "/proc/self/setgroups", "/proc/self/uid_map");
}
