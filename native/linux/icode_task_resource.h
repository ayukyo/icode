/* Private, bounded task-resource transcript. No successful-exec assertion. */
#ifndef ICODE_TASK_RESOURCE_H
#define ICODE_TASK_RESOURCE_H
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdint.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

#define ICODE_RESOURCE_CONFIGURED 1U
#define ICODE_RESOURCE_PREEXEC_FAILED 2U
#define ICODE_RESOURCE_FINISHED 3U
#define ICODE_RESOURCE_CLEANUP_FAILED 4U

struct icode_task_resource {
    int fd;
    unsigned char nonce[16];
    uint32_t limit;
    struct ucred host;
};

static inline int icode_resource_init(struct icode_task_resource *state, int fd,
                                     const char *unit, uint32_t limit) {
    state->fd = fd;
    state->limit = limit;
    socklen_t length = sizeof(state->host);
    int enabled = 1;
    int descriptor_flags = fcntl(fd, F_GETFD);
    if (getsockopt(fd, SOL_SOCKET, SO_PEERCRED, &state->host, &length) != 0 ||
        length != sizeof(state->host) || state->host.pid != getppid() ||
        state->host.uid != getuid() || state->host.gid != getgid() ||
        setsockopt(fd, SOL_SOCKET, SO_PASSCRED, &enabled, sizeof(enabled)) != 0 ||
        descriptor_flags < 0 || fcntl(fd, F_SETFD, descriptor_flags | FD_CLOEXEC) != 0) {
        errno = EPERM;
        return -1;
    }
    descriptor_flags = fcntl(fd, F_GETFD);
    if (descriptor_flags < 0 || !(descriptor_flags & FD_CLOEXEC)) {
        errno = EPERM;
        return -1;
    }
    for (size_t i = 0; i < sizeof(state->nonce); i++) {
        unsigned value = 0;
        for (size_t j = 0; j < 2; j++) {
            unsigned char digit = (unsigned char)unit[11 + 2 * i + j];
            value = value * 16 + (digit <= '9' ? digit - '0' : digit - 'a' + 10);
        }
        state->nonce[i] = (unsigned char)value;
    }
    return 0;
}

static inline int icode_resource_send(const struct icode_task_resource *state,
                                     unsigned char phase) {
    unsigned char frame[26];
    memcpy(frame, "ICQR1", 5);
    frame[5] = phase;
    memcpy(frame + 6, state->nonce, sizeof(state->nonce));
    uint32_t limit = htonl(state->limit);
    memcpy(frame + 22, &limit, sizeof(limit));
    ssize_t sent;
    do { sent = send(state->fd, frame, sizeof(frame), MSG_NOSIGNAL | MSG_DONTWAIT); }
    while (sent < 0 && errno == EINTR);
    if (sent != (ssize_t)sizeof(frame)) { errno = EPROTO; return -1; }
    return 0;
}

/* ACK is consumed under host credentials, before entering a user namespace.
 * Require the actual host writer's kernel credentials, not just peer creator.
 * No rights are accepted; every delivered FD is closed before rejection.
 */
static inline int icode_resource_ack(const struct icode_task_resource *state) {
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC, &now)) return -1;
    int64_t deadline = (int64_t)now.tv_sec * 1000 + now.tv_nsec / 1000000 + 3000;
    struct pollfd descriptor = {.fd = state->fd, .events = POLLIN};
    for (;;) {
        if (clock_gettime(CLOCK_MONOTONIC, &now)) return -1;
        int64_t remaining = deadline - ((int64_t)now.tv_sec * 1000 + now.tv_nsec / 1000000);
        if (remaining <= 0) { errno = ETIMEDOUT; return -1; }
        int ready = poll(&descriptor, 1, (int)remaining);
        if (ready < 0 && errno == EINTR) continue;
        if (ready <= 0 || !(descriptor.revents & POLLIN)) { errno = EPROTO; return -1; }
        break;
    }
    unsigned char ack[26];
    union { struct cmsghdr align; unsigned char data[CMSG_SPACE(sizeof(int) * 32)
        + CMSG_SPACE(sizeof(struct ucred))]; } ancillary;
    struct iovec vector = {.iov_base = ack, .iov_len = sizeof(ack)};
    struct msghdr message = {.msg_iov = &vector, .msg_iovlen = 1,
                            .msg_control = ancillary.data, .msg_controllen = sizeof(ancillary.data)};
    ssize_t length;
    do { length = recvmsg(state->fd, &message, MSG_CMSG_CLOEXEC | MSG_DONTWAIT); }
    while (length < 0 && errno == EINTR);
    int extra = 0;
    int credential_count = 0;
    struct ucred credentials = {0};
    if (length >= 0) {
        for (struct cmsghdr *header = CMSG_FIRSTHDR(&message); header;
             header = CMSG_NXTHDR(&message, header)) {
            if (header->cmsg_level == SOL_SOCKET && header->cmsg_type == SCM_RIGHTS &&
                header->cmsg_len >= CMSG_LEN(0)) {
                extra = 1;
                size_t bytes = header->cmsg_len - CMSG_LEN(0);
                for (size_t position = 0; position + sizeof(int) <= bytes; position += sizeof(int)) {
                    int received;
                    memcpy(&received, (unsigned char *)CMSG_DATA(header) + position, sizeof(received));
                    close(received);
                }
            } else if (header->cmsg_level == SOL_SOCKET && header->cmsg_type == SCM_CREDENTIALS &&
                       header->cmsg_len == CMSG_LEN(sizeof(credentials))) {
                credential_count++;
                memcpy(&credentials, CMSG_DATA(header), sizeof(credentials));
            } else extra = 1;
        }
    }
    uint32_t limit = htonl(state->limit);
    if (length != 25 || extra || credential_count != 1 ||
        credentials.pid != state->host.pid || credentials.uid != state->host.uid ||
        credentials.gid != state->host.gid || (message.msg_flags & (MSG_TRUNC | MSG_CTRUNC)) ||
        memcmp(ack, "ICQA1", 5) || memcmp(ack + 5, state->nonce, 16) ||
        memcmp(ack + 21, &limit, sizeof(limit))) { errno = EPROTO; return -1; }
    return 0;
}

/* An error pipe records actual native pre-exec failures only. EOF is unknown. */
static inline void icode_resource_preexec_failure(int descriptor) {
    if (descriptor < 0) return;
    unsigned char failure = 'F';
    ssize_t written;
    do { written = write(descriptor, &failure, sizeof(failure)); }
    while (written < 0 && errno == EINTR);
}
#endif
