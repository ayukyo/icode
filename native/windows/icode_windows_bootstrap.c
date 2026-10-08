/* Package/bootstrap milestone only: no setup, token, IPC, or command execution.
 * Metadata is not publisher provenance or proof of installed isolation policy.
 */
#if !defined(_WIN32)
#error windows_only_bootstrap
#endif

#if defined(_M_ARM64)
#define ICODE_BOOTSTRAP_ARCH "arm64"
#define ICODE_BOOTSTRAP_MACHINE 0xAA64
#elif defined(_M_X64)
#define ICODE_BOOTSTRAP_ARCH "x64"
#define ICODE_BOOTSTRAP_MACHINE 0x8664
#elif defined(__aarch64__)
#define ICODE_BOOTSTRAP_ARCH "arm64"
#define ICODE_BOOTSTRAP_MACHINE 0xAA64
#elif defined(__x86_64__)
#define ICODE_BOOTSTRAP_ARCH "x64"
#define ICODE_BOOTSTRAP_MACHINE 0x8664
#else
#error unsupported_windows_architecture
#endif

#include <stdio.h>
#include <string.h>
/* Angle inclusion prevents an old source-adjacent header from shadowing the
 * current generated build-directory header supplied by CMake. */
#include <icode_windows_verifier_binding.h>

/* Only the current build's generator supplies this header. No default digest
 * or old header schema may silently produce a signable bootstrap. */
#if ICODE_VERIFIER_BINDING_SCHEMA != 1
#error unsupported_verifier_binding_schema
#endif
#if ICODE_VERIFIER_BINDING_MACHINE != ICODE_BOOTSTRAP_MACHINE
#error verifier_binding_architecture_mismatch
#endif
_Static_assert(sizeof(ICODE_VERIFIER_BINDING_SHA256) == 65,
               "invalid_verifier_binding_digest_length");

enum { ICODE_UNSUPPORTED_OPERATION = 78 };

int main(int argc, char **argv) {
    if (argc == 2 && strcmp(argv[1], "--verifier-binding-json") == 0) {
        if (fputs("{\"helper\":\"icode-windows-bootstrap\",\"binding_schema_version\":1,"
                  "\"architecture\":\"" ICODE_BOOTSTRAP_ARCH "\",\"verifier_sha256\":\""
                  ICODE_VERIFIER_BINDING_SHA256 "\",\"setup_complete\":false,"
                  "\"command_execution\":false,\"isolation_ready\":false,"
                  "\"launch_authorized\":false}\n", stdout) == EOF
            || fflush(stdout) == EOF) {
            return 1;
        }
        return 0;
    }
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
