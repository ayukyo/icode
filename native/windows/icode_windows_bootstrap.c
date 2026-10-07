/* Package/bootstrap milestone only: no setup, token, IPC, or command execution.
 * Metadata is not publisher provenance or proof of installed isolation policy.
 */
#if !defined(_WIN32)
#error windows_only_bootstrap
#endif

#if defined(_M_ARM64)
#define ICODE_BOOTSTRAP_ARCH "arm64"
#elif defined(_M_X64)
#define ICODE_BOOTSTRAP_ARCH "x64"
#elif defined(__aarch64__)
#define ICODE_BOOTSTRAP_ARCH "arm64"
#elif defined(__x86_64__)
#define ICODE_BOOTSTRAP_ARCH "x64"
#else
#error unsupported_windows_architecture
#endif

#include <stdio.h>
#include <string.h>

enum { ICODE_UNSUPPORTED_OPERATION = 78 };

int main(int argc, char **argv) {
    if (argc != 2 || strcmp(argv[1], "--version-json") != 0) {
        fputs("icode_windows_bootstrap: unsupported_operation\n", stderr);
        return ICODE_UNSUPPORTED_OPERATION;
    }
    if (fputs("{\"helper\":\"icode-windows-bootstrap\",\"bootstrap_version\":1,"
              "\"runner_protocol_version\":1,\"architecture\":\""
              ICODE_BOOTSTRAP_ARCH "\",\"setup_complete\":false,"
              "\"command_execution\":false,\"isolation_ready\":false}\n", stdout) == EOF
        || fflush(stdout) == EOF) {
        return 1;
    }
    return 0;
}
