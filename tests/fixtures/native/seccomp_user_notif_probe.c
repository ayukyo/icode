/* Test-only seccomp USER_NOTIF handoff probe; not shipped in the ICODE wheel. */
#define _GNU_SOURCE

#include <errno.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <poll.h>
#include <signal.h>
#include <unistd.h>

enum {
    MESSAGE_READY = 1,
    MESSAGE_SETUP_FAILED = 2,
    MESSAGE_HANDSHAKE_REJECTED = 3,
    MESSAGE_PAYLOAD_RESULT = 4,
};

struct probe_message {
    uint32_t kind;
    int32_t first_result;
    int32_t second_result;
};

static const char ack_token[] = "ICODE_SECCOMP_NOTIFY_ACK_V1";
static const char nack_token[] = "ICODE_SECCOMP_NOTIFY_NACK_V1";

static int send_message(int control, const struct probe_message *message,
                        int descriptor) {
    struct iovec data = {
        .iov_base = (void *)message,
        .iov_len = sizeof(*message),
    };
    union {
        struct cmsghdr alignment;
        char bytes[CMSG_SPACE(sizeof(int))];
    } ancillary = {0};
    struct msghdr packet = {
        .msg_iov = &data,
        .msg_iovlen = 1,
    };
    if (descriptor >= 0) {
        packet.msg_control = ancillary.bytes;
        packet.msg_controllen = sizeof(ancillary.bytes);
        struct cmsghdr *header = CMSG_FIRSTHDR(&packet);
        if (!header) return -1;
        header->cmsg_level = SOL_SOCKET;
        header->cmsg_type = SCM_RIGHTS;
        header->cmsg_len = CMSG_LEN(sizeof(int));
        memcpy(CMSG_DATA(header), &descriptor, sizeof(descriptor));
    }
    ssize_t sent;
    do {
        sent = sendmsg(control, &packet, MSG_NOSIGNAL);
    } while (sent < 0 && errno == EINTR);
    return sent == (ssize_t)sizeof(*message) ? 0 : -1;
}

static int receive_message(int control, struct probe_message *message,
                           int *received_descriptor) {
    struct iovec data = {
        .iov_base = message,
        .iov_len = sizeof(*message),
    };
    union {
        struct cmsghdr alignment;
        char bytes[CMSG_SPACE(sizeof(int) * 4)];
    } ancillary = {0};
    struct msghdr packet = {
        .msg_iov = &data,
        .msg_iovlen = 1,
        .msg_control = ancillary.bytes,
        .msg_controllen = sizeof(ancillary.bytes),
    };
    ssize_t received;
    do {
        received = recvmsg(control, &packet, MSG_CMSG_CLOEXEC);
    } while (received < 0 && errno == EINTR);
    int found = -1;
    int malformed = received != (ssize_t)sizeof(*message) ||
                    (packet.msg_flags & (MSG_TRUNC | MSG_CTRUNC)) != 0;
    for (struct cmsghdr *header = CMSG_FIRSTHDR(&packet); header;
         header = CMSG_NXTHDR(&packet, header)) {
        if (header->cmsg_level != SOL_SOCKET ||
            header->cmsg_type != SCM_RIGHTS ||
            header->cmsg_len < CMSG_LEN(sizeof(int))) {
            malformed = 1;
            continue;
        }
        size_t bytes = header->cmsg_len - CMSG_LEN(0);
        size_t count = bytes / sizeof(int);
        if (bytes % sizeof(int) != 0) malformed = 1;
        int *descriptors = (int *)CMSG_DATA(header);
        for (size_t index = 0; index < count; ++index) {
            if (!malformed && found < 0 && count == 1) {
                found = descriptors[index];
            } else {
                close(descriptors[index]);
                malformed = 1;
            }
        }
    }
    if (malformed) {
        if (found >= 0) close(found);
        return -1;
    }
    *received_descriptor = found;
    return 0;
}

static int wait_for_acknowledgement(int control) {
    char token[sizeof(ack_token)] = {0};
    ssize_t received;
    do {
        received = recv(control, token, sizeof(token), 0);
    } while (received < 0 && errno == EINTR);
    return received == (ssize_t)(sizeof(ack_token) - 1) &&
           memcmp(token, ack_token, sizeof(ack_token) - 1) == 0;
}

static int install_notification_filter(void) {
    struct sock_filter instructions[] = {
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS,
                 offsetof(struct seccomp_data, nr)),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, SYS_socket, 0, 3),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS,
                 offsetof(struct seccomp_data, args[0])),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, AF_INET, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_USER_NOTIF),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW),
    };
    struct sock_fprog program = {
        .len = (unsigned short)(sizeof(instructions) / sizeof(instructions[0])),
        .filter = instructions,
    };
    return (int)syscall(SYS_seccomp, SECCOMP_SET_MODE_FILTER,
                        SECCOMP_FILTER_FLAG_NEW_LISTENER, &program);
}

static void child_send_failure(int control, int error_number) {
    struct probe_message message = {
        .kind = MESSAGE_SETUP_FAILED,
        .first_result = error_number,
        .second_result = 0,
    };
    (void)send_message(control, &message, -1);
    _exit(71);
}

static void child_main(int control) {
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0) {
        child_send_failure(control, errno);
    }
    int listener = install_notification_filter();
    if (listener < 0) child_send_failure(control, errno);

    struct probe_message ready = {
        .kind = MESSAGE_READY,
        .first_result = 0,
        .second_result = 0,
    };
    if (send_message(control, &ready, listener) != 0) {
        close(listener);
        _exit(72);
    }
    close(listener);

    if (!wait_for_acknowledgement(control)) {
        struct probe_message rejected = {
            .kind = MESSAGE_HANDSHAKE_REJECTED,
            .first_result = 0,
            .second_result = 0,
        };
        (void)send_message(control, &rejected, -1);
        _exit(70);
    }

    int local_pair[2] = {-1, -1};
    int allowed = socketpair(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC,
                             0, local_pair) == 0;
    if (allowed) {
        close(local_pair[0]);
        close(local_pair[1]);
    }
    errno = 0;
    int denied_socket = (int)syscall(SYS_socket, AF_INET,
                                     SOCK_STREAM | SOCK_CLOEXEC, 0);
    int denied_errno = errno;
    if (denied_socket >= 0) close(denied_socket);

    struct probe_message result = {
        .kind = MESSAGE_PAYLOAD_RESULT,
        .first_result = allowed,
        .second_result = denied_errno,
    };
    int sent = send_message(control, &result, -1);
    _exit(sent == 0 && allowed && denied_socket < 0 &&
          denied_errno == EPERM ? 0 : 73);
}

static int send_acknowledgement(int control, int accepted) {
    const char *token = accepted ? ack_token : nack_token;
    size_t length = accepted ? sizeof(ack_token) - 1 : sizeof(nack_token) - 1;
    ssize_t sent;
    do {
        sent = send(control, token, length, MSG_NOSIGNAL);
    } while (sent < 0 && errno == EINTR);
    return sent == (ssize_t)length ? 0 : -1;
}

static int wait_for_notification(int listener, pid_t child,
                                 int *request_matched) {
    struct pollfd wait_socket = {.fd = listener, .events = POLLIN};
    int ready;
    do {
        ready = poll(&wait_socket, 1, 3000);
    } while (ready < 0 && errno == EINTR);
    if (ready != 1 || !(wait_socket.revents & POLLIN)) return -1;

    struct seccomp_notif request = {0};
    if (ioctl(listener, SECCOMP_IOCTL_NOTIF_RECV, &request) != 0) return -1;
    *request_matched = request.pid == (uint32_t)child &&
                       request.data.nr == SYS_socket &&
                       request.data.args[0] == AF_INET;

    struct seccomp_notif_resp response = {
        .id = request.id,
        .val = 0,
        .error = -EPERM,
        .flags = 0,
    };
    if (ioctl(listener, SECCOMP_IOCTL_NOTIF_ID_VALID, &request.id) != 0 ||
        ioctl(listener, SECCOMP_IOCTL_NOTIF_SEND, &response) != 0) return -1;
    return 0;
}

static int wait_for_child(pid_t child, int *status) {
    pid_t result;
    do {
        result = waitpid(child, status, 0);
    } while (result < 0 && errno == EINTR);
    return result == child ? 0 : -1;
}

static void terminate_child(pid_t child) {
    (void)kill(child, SIGKILL);
    int status = 0;
    (void)wait_for_child(child, &status);
}

static int fail_stage(const char *stage, int error_number) {
    if (error_number > 0) {
        printf("probe:error=%s errno=%d\n", stage, error_number);
    } else {
        printf("probe:error=%s\n", stage);
    }
    return 1;
}

static int run_probe(int reject_handshake) {
    int control[2] = {-1, -1};
    if (socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, control) != 0) {
        return fail_stage("control_socketpair", errno);
    }
    pid_t child = fork();
    if (child < 0) {
        int saved_errno = errno;
        close(control[0]);
        close(control[1]);
        return fail_stage("fork", saved_errno);
    }
    if (child == 0) {
        close(control[0]);
        child_main(control[1]);
    }
    close(control[1]);

    struct probe_message message = {0};
    int listener = -1;
    if (receive_message(control[0], &message, &listener) != 0) {
        close(control[0]);
        terminate_child(child);
        return fail_stage("receive_listener", 0);
    }
    if (message.kind != MESSAGE_READY || listener < 0) {
        int error_number = message.first_result;
        if (listener >= 0) close(listener);
        close(control[0]);
        int status = 0;
        (void)wait_for_child(child, &status);
        return fail_stage(message.kind == MESSAGE_SETUP_FAILED
                          ? "setup_failed" : "unexpected_handoff", error_number);
    }

    if (send_acknowledgement(control[0], !reject_handshake) != 0) {
        close(listener);
        close(control[0]);
        terminate_child(child);
        return fail_stage("send_handshake", errno);
    }
    if (reject_handshake) {
        struct probe_message rejected = {0};
        int received_fd = -1;
        if (receive_message(control[0], &rejected, &received_fd) != 0 ||
            received_fd >= 0 || rejected.kind != MESSAGE_HANDSHAKE_REJECTED) {
            if (received_fd >= 0) close(received_fd);
            close(listener);
            close(control[0]);
            terminate_child(child);
            return fail_stage("rejected_handshake_result", 0);
        }
        close(listener);
        close(control[0]);
        int status = 0;
        if (wait_for_child(child, &status) != 0 || !WIFEXITED(status) ||
            WEXITSTATUS(status) != 70) {
            return fail_stage("rejected_handshake_child_status", 0);
        }
        puts("probe:handshake_rejected=1");
        puts("probe:payload_started=0");
        puts("probe:conformance_credit=none");
        return 0;
    }

    int request_matched = 0;
    if (wait_for_notification(listener, child, &request_matched) != 0) {
        close(listener);
        close(control[0]);
        terminate_child(child);
        return fail_stage("notification_or_reply", errno);
    }
    close(listener);

    struct probe_message result = {0};
    int received_fd = -1;
    if (receive_message(control[0], &result, &received_fd) != 0 ||
        received_fd >= 0 || result.kind != MESSAGE_PAYLOAD_RESULT) {
        if (received_fd >= 0) close(received_fd);
        close(control[0]);
        terminate_child(child);
        return fail_stage("payload_result", 0);
    }
    close(control[0]);
    int status = 0;
    if (wait_for_child(child, &status) != 0 || !WIFEXITED(status) ||
        WEXITSTATUS(status) != 0 || !request_matched ||
        result.first_result != 1 || result.second_result != EPERM) {
        return fail_stage("probe_assertions", 0);
    }

    puts("probe:observer_ack_before_syscall=1");
    puts("probe:seccomp_user_notification=received");
    puts("probe:broker_reply=EPERM");
    puts("probe:allowed_unix_socketpair=1");
    puts("probe:payload_denied_errno=EPERM");
    puts("probe:conformance_credit=none");
    return 0;
}

int main(int argc, char **argv) {
    if (argc == 2 && strcmp(argv[1], "--exit-13") == 0) return 13;
    if (argc == 2 && strcmp(argv[1], "--reject-handshake") == 0) {
        return run_probe(1);
    }
    if (argc != 1) return 2;
    return run_probe(0);
}
