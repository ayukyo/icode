/* Test-only launcher: inherit SA_NOCLDWAIT and a blocked SIGCHLD into helper. */
#define _GNU_SOURCE
#include <signal.h>
#include <stdio.h>
#include <unistd.h>

int main(int argc, char **argv) {
    if (argc < 2) return 2;
    struct sigaction disposition = {.sa_handler = SIG_DFL, .sa_flags = SA_NOCLDWAIT};
    sigset_t blocked;
    if (sigemptyset(&disposition.sa_mask) != 0 ||
        sigaction(SIGCHLD, &disposition, NULL) != 0 ||
        sigemptyset(&blocked) != 0 ||
        sigaddset(&blocked, SIGCHLD) != 0 ||
        sigprocmask(SIG_BLOCK, &blocked, NULL) != 0) {
        perror("set test SIGCHLD state");
        return 1;
    }
    execvp(argv[1], argv + 1);
    perror("execvp test helper");
    return 127;
}
