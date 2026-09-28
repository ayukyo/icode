#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>

#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

enum {
    ARG_HANDLE = 1u << 0,
    ARG_SOURCE = 1u << 1,
    ARG_SIBLING = 1u << 2,
    ARG_OUTSIDE = 1u << 3,
    ARG_PROFILE = 1u << 4,
    ARG_MARKER = 1u << 5,
    ARG_REPORT = 1u << 6,
    ARG_ADDRESS = 1u << 7,
    ARG_PORT = 1u << 8,
    ARG_ALL = (1u << 9) - 1u,
};

static const unsigned char kExpectedContents[] = "ICODE-READ-HANDLE-PROBE-v1\n";
static const char kWriteProbe[] = "must-not-be-written";
static const char kNetworkProbe[] = "ICODE-APPCONTAINER-NETWORK-PROBE";

typedef struct ProbeArguments {
    HANDLE input_handle;
    const wchar_t *source_path;
    const wchar_t *sibling_path;
    const wchar_t *outside_path;
    const wchar_t *profile_path;
    const wchar_t *marker_path;
    const wchar_t *report_path;
    const wchar_t *network_address;
    unsigned short network_port;
} ProbeArguments;

typedef struct ProbeReceipt {
    BOOL token_is_appcontainer;
    BOOL handle_read_ok;
    BOOL handle_write_denied;
    BOOL source_path_denied;
    BOOL sibling_path_denied;
    BOOL outside_path_denied;
    BOOL profile_path_denied;
    BOOL marker_create_denied;
    BOOL network_denied;
    int network_error;
    BOOL report_written;
    unsigned completed_stage;
} ProbeReceipt;

static BOOL parse_handle(const wchar_t *value, HANDLE *handle_out) {
    wchar_t *end = NULL;
    unsigned __int64 parsed;

    if (value == NULL || value[0] == L'\0' || handle_out == NULL) {
        return FALSE;
    }
    errno = 0;
    parsed = _wcstoui64(value, &end, 10);
    if (errno != 0 || end == value || *end != L'\0' || parsed == 0 ||
        parsed > (unsigned __int64)UINTPTR_MAX) {
        return FALSE;
    }
    *handle_out = (HANDLE)(uintptr_t)parsed;
    return TRUE;
}

static BOOL parse_port(const wchar_t *value, unsigned short *port_out) {
    wchar_t *end = NULL;
    unsigned long parsed;

    if (value == NULL || value[0] == L'\0' || port_out == NULL) {
        return FALSE;
    }
    errno = 0;
    parsed = wcstoul(value, &end, 10);
    if (errno != 0 || end == value || *end != L'\0' || parsed == 0 || parsed > 65535) {
        return FALSE;
    }
    *port_out = (unsigned short)parsed;
    return TRUE;
}

static BOOL assign_argument(
    ProbeArguments *arguments,
    const wchar_t *name,
    const wchar_t *value,
    unsigned *seen
) {
    unsigned bit = 0;

    if (wcscmp(name, L"--input-handle") == 0) {
        bit = ARG_HANDLE;
        if (!parse_handle(value, &arguments->input_handle)) return FALSE;
    } else if (wcscmp(name, L"--source-path") == 0) {
        bit = ARG_SOURCE;
        arguments->source_path = value;
    } else if (wcscmp(name, L"--sibling-path") == 0) {
        bit = ARG_SIBLING;
        arguments->sibling_path = value;
    } else if (wcscmp(name, L"--outside-path") == 0) {
        bit = ARG_OUTSIDE;
        arguments->outside_path = value;
    } else if (wcscmp(name, L"--profile-path") == 0) {
        bit = ARG_PROFILE;
        arguments->profile_path = value;
    } else if (wcscmp(name, L"--marker-path") == 0) {
        bit = ARG_MARKER;
        arguments->marker_path = value;
    } else if (wcscmp(name, L"--report-path") == 0) {
        bit = ARG_REPORT;
        arguments->report_path = value;
    } else if (wcscmp(name, L"--network-address") == 0) {
        bit = ARG_ADDRESS;
        arguments->network_address = value;
    } else if (wcscmp(name, L"--network-port") == 0) {
        bit = ARG_PORT;
        if (!parse_port(value, &arguments->network_port)) return FALSE;
    } else {
        return FALSE;
    }

    if ((*seen & bit) != 0) return FALSE;
    *seen |= bit;
    return TRUE;
}

static BOOL parse_arguments(int argc, wchar_t **argv, ProbeArguments *arguments) {
    unsigned seen = 0;
    int index;

    if (argc != 1 + (2 * 9) || argv == NULL || arguments == NULL) return FALSE;
    ZeroMemory(arguments, sizeof(*arguments));
    for (index = 1; index < argc; index += 2) {
        if (!assign_argument(arguments, argv[index], argv[index + 1], &seen)) return FALSE;
    }
    return seen == ARG_ALL && arguments->network_address != NULL &&
        wcscmp(arguments->network_address, L"127.0.0.1") == 0;
}

static BOOL token_is_appcontainer(void) {
    HANDLE token = NULL;
    DWORD is_appcontainer = 0;
    DWORD returned = 0;
    BOOL result = FALSE;

    if (!OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &token)) return FALSE;
    /* TokenIsAppContainer is value 29 in the Windows SDK TOKEN_INFORMATION_CLASS. */
    if (GetTokenInformation(
            token, (TOKEN_INFORMATION_CLASS)29, &is_appcontainer,
            sizeof(is_appcontainer), &returned) && returned >= sizeof(is_appcontainer)) {
        result = is_appcontainer != 0;
    }
    CloseHandle(token);
    return result;
}

static BOOL read_approved_handle(HANDLE handle) {
    LARGE_INTEGER start;
    unsigned char contents[sizeof(kExpectedContents)];
    DWORD bytes_read = 0;
    unsigned char extra = 0;
    DWORD extra_bytes = 0;

    start.QuadPart = 0;
    if (!SetFilePointerEx(handle, start, NULL, FILE_BEGIN)) return FALSE;
    if (!ReadFile(handle, contents, (DWORD)(sizeof(kExpectedContents) - 1), &bytes_read, NULL) ||
        bytes_read != sizeof(kExpectedContents) - 1 ||
        memcmp(contents, kExpectedContents, sizeof(kExpectedContents) - 1) != 0) {
        return FALSE;
    }
    return ReadFile(handle, &extra, sizeof(extra), &extra_bytes, NULL) && extra_bytes == 0;
}

static BOOL write_to_handle_is_denied(HANDLE handle) {
    LARGE_INTEGER end;
    DWORD bytes_written = 0;
    BOOL write_ok;
    DWORD error;

    end.QuadPart = 0;
    if (!SetFilePointerEx(handle, end, NULL, FILE_END)) return FALSE;
    SetLastError(ERROR_SUCCESS);
    write_ok = WriteFile(handle, kWriteProbe, (DWORD)(sizeof(kWriteProbe) - 1), &bytes_written, NULL);
    error = GetLastError();
    return !write_ok && error == ERROR_ACCESS_DENIED && bytes_written == 0;
}

static BOOL path_read_is_denied(const wchar_t *path) {
    HANDLE file = CreateFileW(
        path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL
    );
    DWORD error;

    if (file != INVALID_HANDLE_VALUE) {
        CloseHandle(file);
        return FALSE;
    }
    error = GetLastError();
    return error == ERROR_ACCESS_DENIED;
}

static BOOL marker_create_is_denied(const wchar_t *path) {
    HANDLE file = CreateFileW(
        path, GENERIC_WRITE, 0, NULL, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, NULL
    );
    DWORD error;

    if (file != INVALID_HANDLE_VALUE) {
        CloseHandle(file);
        DeleteFileW(path);
        return FALSE;
    }
    error = GetLastError();
    return error == ERROR_ACCESS_DENIED;
}

static BOOL network_connect_is_denied(const ProbeArguments *arguments, int *error_out) {
    WSADATA winsock_data;
    SOCKET client = INVALID_SOCKET;
    struct sockaddr_in address;
    int startup_result;
    int connect_result;
    int error = 0;
    BOOL denied = FALSE;

    startup_result = WSAStartup(MAKEWORD(2, 2), &winsock_data);
    if (startup_result != 0) {
        *error_out = startup_result;
        return FALSE;
    }
    client = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (client == INVALID_SOCKET) {
        error = WSAGetLastError();
        denied = error == WSAEACCES;
    } else {
        ZeroMemory(&address, sizeof(address));
        address.sin_family = AF_INET;
        address.sin_port = htons(arguments->network_port);
        if (InetPtonW(AF_INET, arguments->network_address, &address.sin_addr) != 1) {
            error = WSAEINVAL;
        } else {
            connect_result = connect(client, (const struct sockaddr *)&address, sizeof(address));
            if (connect_result == 0) {
                (void)send(client, kNetworkProbe, (int)(sizeof(kNetworkProbe) - 1), 0);
            } else {
                error = WSAGetLastError();
                denied = error == WSAEACCES;
            }
        }
    }
    if (client != INVALID_SOCKET) closesocket(client);
    WSACleanup();
    *error_out = error;
    return denied;
}

static BOOL write_receipt(const wchar_t *path, ProbeReceipt *receipt, unsigned stage) {
    char json[768];
    int length;
    DWORD bytes_written = 0;
    HANDLE output;

    length = _snprintf_s(
        json, sizeof(json), _TRUNCATE,
        "{\"token_is_appcontainer\":%s,\"handle_read_ok\":%s,"
        "\"handle_write_denied\":%s,\"source_path_denied\":%s,"
        "\"sibling_path_denied\":%s,\"outside_path_denied\":%s,"
        "\"profile_path_denied\":%s,\"marker_create_denied\":%s,"
        "\"network_denied\":%s,\"network_error\":%d,\"stage\":%u}\n",
        receipt->token_is_appcontainer ? "true" : "false",
        receipt->handle_read_ok ? "true" : "false",
        receipt->handle_write_denied ? "true" : "false",
        receipt->source_path_denied ? "true" : "false",
        receipt->sibling_path_denied ? "true" : "false",
        receipt->outside_path_denied ? "true" : "false",
        receipt->profile_path_denied ? "true" : "false",
        receipt->marker_create_denied ? "true" : "false",
        receipt->network_denied ? "true" : "false",
        receipt->network_error,
        stage
    );
    if (length <= 0 || (size_t)length >= sizeof(json)) return FALSE;
    output = CreateFileW(
        path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS,
        FILE_ATTRIBUTE_NORMAL, NULL
    );
    if (output == INVALID_HANDLE_VALUE) return FALSE;
    receipt->report_written = WriteFile(output, json, (DWORD)length, &bytes_written, NULL) &&
        bytes_written == (DWORD)length;
    CloseHandle(output);
    return receipt->report_written;
}

int wmain(int argc, wchar_t **argv) {
    ProbeArguments arguments;
    ProbeReceipt receipt;
    BOOL all_checks;

    ZeroMemory(&receipt, sizeof(receipt));
    if (!parse_arguments(argc, argv, &arguments)) return 2;

    receipt.token_is_appcontainer = token_is_appcontainer();
    receipt.completed_stage = 1;
    receipt.report_written = write_receipt(
        arguments.report_path, &receipt, receipt.completed_stage
    );

    receipt.handle_read_ok = read_approved_handle(arguments.input_handle);
    if (receipt.handle_read_ok) {
        receipt.handle_write_denied = write_to_handle_is_denied(arguments.input_handle);
    }
    receipt.completed_stage = 2;
    receipt.report_written = write_receipt(
        arguments.report_path, &receipt, receipt.completed_stage
    );

    receipt.source_path_denied = path_read_is_denied(arguments.source_path);
    receipt.sibling_path_denied = path_read_is_denied(arguments.sibling_path);
    receipt.outside_path_denied = path_read_is_denied(arguments.outside_path);
    receipt.profile_path_denied = path_read_is_denied(arguments.profile_path);
    receipt.completed_stage = 3;
    receipt.report_written = write_receipt(
        arguments.report_path, &receipt, receipt.completed_stage
    );

    receipt.marker_create_denied = marker_create_is_denied(arguments.marker_path);
    receipt.completed_stage = 4;
    receipt.report_written = write_receipt(
        arguments.report_path, &receipt, receipt.completed_stage
    );

    receipt.network_denied = network_connect_is_denied(&arguments, &receipt.network_error);
    receipt.completed_stage = 5;
    receipt.report_written = write_receipt(
        arguments.report_path, &receipt, receipt.completed_stage
    );

    all_checks = receipt.token_is_appcontainer && receipt.handle_read_ok &&
        receipt.handle_write_denied && receipt.source_path_denied &&
        receipt.sibling_path_denied && receipt.outside_path_denied &&
        receipt.profile_path_denied && receipt.marker_create_denied &&
        receipt.network_denied && receipt.network_error == WSAEACCES &&
        receipt.report_written;
    return all_checks ? 0 : 1;
}
