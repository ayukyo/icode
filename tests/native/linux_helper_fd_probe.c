#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

int main(int argc, char **argv) {
    if (argc != 8) return 2;
    int helper_fd = atoi(argv[1]);
    struct stat status;
    errno = 0;
    /* First descriptor operation: before opening or enumerating anything. */
    if (fstat(helper_fd, &status) != -1 || errno != EBADF) return 11;
    unsigned long long device = strtoull(argv[2], NULL, 10);
    unsigned long long inode = strtoull(argv[3], NULL, 10);
    int workspace_fd = atoi(argv[4]);
    unsigned long long workspace_device = strtoull(argv[5], NULL, 10);
    unsigned long long workspace_inode = strtoull(argv[6], NULL, 10);
    errno = 0;
    if (fstat(workspace_fd, &status) != -1 || errno != EBADF) return 21;
    /* No /proc read grant: scan the full current descriptor-number range.
     * Never open anything before this scan; first-fstat above is independent.
     */
    long cap = sysconf(_SC_OPEN_MAX);
    if (cap < 3 || cap > 1048576) return 12;
    for (int fd = 3; fd < cap; ++fd) {
        if (fstat(fd, &status) == 0 && (unsigned long long)status.st_dev == device
                && (unsigned long long)status.st_ino == inode) return 13;
        if (fstat(fd, &status) == 0 && (unsigned long long)status.st_dev == workspace_device
                && (unsigned long long)status.st_ino == workspace_inode) return 22;
    }
    errno = 0;
    int network = socket(AF_INET, SOCK_STREAM, 0);
    if (network >= 0) { close(network); return 14; }
    if (errno != EPERM) return 15;
    if (strstr(argv[7], "SCOPE") != NULL) {
        errno = 0;
        pid_t child = fork();
        if (child == 0) _exit(23);
        if (child >= 0 || errno != EAGAIN) return 19;
    }
    int ready = open("ready", O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
    if (ready < 0 || write(ready, "ready", 5) != 5 || close(ready) != 0) return 16;
    struct timespec start, now, delay = {.tv_sec = 0, .tv_nsec = 10000000};
    if (clock_gettime(CLOCK_MONOTONIC, &start) != 0) return 17;
    while (access("release", F_OK) != 0) {
        if (clock_gettime(CLOCK_MONOTONIC, &now) != 0 || now.tv_sec - start.tv_sec >= 4) return 18;
        nanosleep(&delay, NULL);
    }
    if (strstr(argv[7], "OUTPUT") != NULL) {
        for (;;) if (write(STDOUT_FILENO, "xxxxxxxxxxxxxxxx", 16) != 16) return 23;
    }
    puts(argv[7]);
    return 0;
}
