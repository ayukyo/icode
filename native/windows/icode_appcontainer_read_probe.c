#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <iphlpapi.h>
#include <netfw.h>

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
    ARG_CONTROL_PORT = 1u << 9,
    ARG_ALL = (1u << 10) - 1u,
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
    unsigned short network_control_port;
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
    BOOL network_connect_attempted;
    BOOL network_connected;
    int network_control_error;
    BOOL network_control_connect_attempted;
    BOOL network_control_connected;
    BOOL network_isolation_diagnostic_ok;
    DWORD network_isolation_status;
    DWORD network_isolation_error_type;
    BOOL report_written;
    unsigned completed_stage;
} ProbeReceipt;

typedef DWORD (WINAPI *NetworkIsolationDiagnoseConnectFailureAndGetInfoFn)(
    LPCWSTR server_name,
    NETISO_ERROR_TYPE *network_isolation_error
);

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

static BOOL is_rfc1918_octets(const unsigned int octets[4]) {
    if (octets == NULL) return FALSE;
    return octets[0] == 10 ||
        (octets[0] == 172 && octets[1] >= 16 && octets[1] <= 31) ||
        (octets[0] == 192 && octets[1] == 168);
}

static BOOL parse_ipv4_octets(const wchar_t *value, unsigned int octets[4]) {
    const wchar_t *cursor = value;
    unsigned int index;

    if (cursor == NULL || octets == NULL) return FALSE;
    for (index = 0; index < 4; ++index) {
        const wchar_t *component_start = cursor;
        unsigned int octet = 0;
        unsigned int digits = 0;

        while (*cursor >= L'0' && *cursor <= L'9') {
            unsigned int digit = (unsigned int)(*cursor - L'0');
            if (octet > 25 || (octet == 25 && digit > 5)) return FALSE;
            octet = (octet * 10) + digit;
            ++digits;
            ++cursor;
        }
        if (digits == 0 || (digits > 1 && component_start[0] == L'0')) {
            return FALSE;
        }
        octets[index] = octet;
        if (index < 3) {
            if (*cursor != L'.') return FALSE;
            ++cursor;
        } else if (*cursor != L'\0') {
            return FALSE;
        }
    }
    return TRUE;
}

static BOOL is_rfc1918_ipv4(const wchar_t *value) {
    unsigned int octets[4];

    if (!parse_ipv4_octets(value, octets)) return FALSE;
    return is_rfc1918_octets(octets);
}

static int print_private_network_target(void) {
    const ULONG flags = GAA_FLAG_SKIP_ANYCAST |
        GAA_FLAG_SKIP_MULTICAST | GAA_FLAG_SKIP_DNS_SERVER;
    ULONG buffer_size = 15u * 1024u;
    BYTE *buffer = (BYTE *)HeapAlloc(GetProcessHeap(), 0, buffer_size);
    ULONG status;
    PIP_ADAPTER_ADDRESSES adapters;
    PIP_ADAPTER_ADDRESSES adapter;

    if (buffer == NULL) return 1;
    adapters = (PIP_ADAPTER_ADDRESSES)buffer;
    status = GetAdaptersAddresses(AF_INET, flags, NULL, adapters, &buffer_size);
    if (status == ERROR_BUFFER_OVERFLOW && buffer_size != 0 &&
        buffer_size <= 1024u * 1024u) {
        HeapFree(GetProcessHeap(), 0, buffer);
        buffer = (BYTE *)HeapAlloc(GetProcessHeap(), 0, buffer_size);
        if (buffer == NULL) return 1;
        adapters = (PIP_ADAPTER_ADDRESSES)buffer;
        status = GetAdaptersAddresses(AF_INET, flags, NULL, adapters, &buffer_size);
    }
    if (status != NO_ERROR) {
        HeapFree(GetProcessHeap(), 0, buffer);
        return 1;
    }

    for (adapter = adapters; adapter != NULL; adapter = adapter->Next) {
        PIP_ADAPTER_UNICAST_ADDRESS unicast;
        if (adapter->OperStatus != IfOperStatusUp) continue;
        for (unicast = adapter->FirstUnicastAddress;
             unicast != NULL; unicast = unicast->Next) {
            const SOCKADDR *socket_address = unicast->Address.lpSockaddr;
            const SOCKADDR_IN *ipv4_address;
            unsigned long address;
            unsigned int octets[4];
            char formatted[16];
            int formatted_length;

            if (unicast->DadState != IpDadStatePreferred || socket_address == NULL ||
                socket_address->sa_family != AF_INET) {
                continue;
            }
            ipv4_address = (const SOCKADDR_IN *)socket_address;
            address = ntohl(ipv4_address->sin_addr.s_addr);
            octets[0] = (unsigned int)((address >> 24) & 0xffu);
            octets[1] = (unsigned int)((address >> 16) & 0xffu);
            octets[2] = (unsigned int)((address >> 8) & 0xffu);
            octets[3] = (unsigned int)(address & 0xffu);
            if (!is_rfc1918_octets(octets)) continue;
            formatted_length = snprintf(
                formatted, sizeof(formatted), "%u.%u.%u.%u",
                octets[0], octets[1], octets[2], octets[3]
            );
            if (formatted_length <= 0 ||
                (size_t)formatted_length >= sizeof(formatted)) {
                HeapFree(GetProcessHeap(), 0, buffer);
                return 1;
            }
            printf("%s\n", formatted);
            HeapFree(GetProcessHeap(), 0, buffer);
            return 0;
        }
    }

    HeapFree(GetProcessHeap(), 0, buffer);
    return 1;
}

static int self_test_network_target_parser(void) {
    static const wchar_t *const allowed[] = {
        L"10.0.0.1", L"172.16.0.1", L"172.31.255.254", L"192.168.1.9"
    };
    static const wchar_t *const rejected[] = {
        L"127.0.0.1", L"8.8.8.8", L"172.15.255.1", L"172.32.0.1",
        L"192.167.1.1", L"192.0.2.1", L"10.256.0.1", L"010.0.0.1",
        L"10.0.0", L"10.0.0.1.2", L"10.0.0.1suffix", L"10..0.1"
    };
    size_t index;

    for (index = 0; index < sizeof(allowed) / sizeof(allowed[0]); ++index) {
        if (!is_rfc1918_ipv4(allowed[index])) return 1;
    }
    for (index = 0; index < sizeof(rejected) / sizeof(rejected[0]); ++index) {
        if (is_rfc1918_ipv4(rejected[index])) return 1;
    }
    return 0;
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
    } else if (wcscmp(name, L"--network-control-port") == 0) {
        bit = ARG_CONTROL_PORT;
        if (!parse_port(value, &arguments->network_control_port)) return FALSE;
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

    if (argc != 1 + (2 * 10) || argv == NULL || arguments == NULL) return FALSE;
    ZeroMemory(arguments, sizeof(*arguments));
    for (index = 1; index < argc; index += 2) {
        if (!assign_argument(arguments, argv[index], argv[index + 1], &seen)) return FALSE;
    }
    return seen == ARG_ALL &&
        arguments->network_port != arguments->network_control_port &&
        is_rfc1918_ipv4(arguments->network_address);
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

static BOOL diagnose_missing_network_capability(
    const wchar_t *server_name,
    BOOL *diagnostic_ok_out,
    DWORD *diagnostic_status_out,
    DWORD *error_type_out
) {
    HMODULE firewall_api;
    NetworkIsolationDiagnoseConnectFailureAndGetInfoFn diagnose;
    NETISO_ERROR_TYPE error_type = NETISO_ERROR_TYPE_NONE;
    DWORD status;

    if (server_name == NULL || diagnostic_ok_out == NULL ||
        diagnostic_status_out == NULL || error_type_out == NULL) {
        return FALSE;
    }
    *diagnostic_ok_out = FALSE;
    *diagnostic_status_out = ERROR_INVALID_PARAMETER;
    *error_type_out = NETISO_ERROR_TYPE_NONE;
    firewall_api = LoadLibraryW(L"FirewallAPI.dll");
    if (firewall_api == NULL) {
        *diagnostic_status_out = GetLastError();
        return FALSE;
    }
    diagnose = (NetworkIsolationDiagnoseConnectFailureAndGetInfoFn)GetProcAddress(
        firewall_api, "NetworkIsolationDiagnoseConnectFailureAndGetInfo"
    );
    if (diagnose == NULL) {
        *diagnostic_status_out = GetLastError();
        FreeLibrary(firewall_api);
        return FALSE;
    }

    status = diagnose(server_name, &error_type);
    *diagnostic_status_out = status;
    FreeLibrary(firewall_api);
    *diagnostic_ok_out = status == ERROR_SUCCESS;
    *error_type_out = (DWORD)error_type;
    return *diagnostic_ok_out && error_type == NETISO_ERROR_TYPE_PRIVATE_NETWORK;
}

static BOOL network_connect_to_port(
    const wchar_t *network_address,
    unsigned short network_port,
    BOOL send_probe_payload,
    int *error_out,
    BOOL *connect_attempted_out,
    BOOL *connected_out
) {
    WSADATA winsock_data;
    SOCKET client = INVALID_SOCKET;
    struct sockaddr_in address;
    struct timeval connect_timeout;
    fd_set writable_sockets;
    fd_set exceptional_sockets;
    u_long nonblocking = 1;
    int startup_result;
    int connect_result;
    int select_result;
    int socket_error = 0;
    int socket_error_size = sizeof(socket_error);
    int error = 0;
    BOOL denied = FALSE;
    BOOL connected = FALSE;

    if (network_address == NULL || network_port == 0 || error_out == NULL ||
        connect_attempted_out == NULL || connected_out == NULL) {
        return FALSE;
    }
    *error_out = 0;
    *connect_attempted_out = FALSE;
    *connected_out = FALSE;
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
        address.sin_port = htons(network_port);
        if (InetPtonW(AF_INET, network_address, &address.sin_addr) != 1) {
            error = WSAEINVAL;
        } else if (ioctlsocket(client, FIONBIO, &nonblocking) == SOCKET_ERROR) {
            error = WSAGetLastError();
        } else {
            *connect_attempted_out = TRUE;
            connect_result = connect(client, (const struct sockaddr *)&address, sizeof(address));
            if (connect_result == SOCKET_ERROR) {
                error = WSAGetLastError();
                if (error == WSAEACCES) {
                    denied = TRUE;
                } else if (error == WSAEWOULDBLOCK || error == WSAEINPROGRESS ||
                    error == WSAEALREADY) {
                    /* Winsock reports connect success in writefds and failure in exceptfds. */
                    FD_ZERO(&writable_sockets);
                    FD_SET(client, &writable_sockets);
                    FD_ZERO(&exceptional_sockets);
                    FD_SET(client, &exceptional_sockets);
                    /* A timeout is inconclusive, never proof that the sandbox denied access. */
                    connect_timeout.tv_sec = 1;
                    connect_timeout.tv_usec = 0;
                    select_result = select(
                        0, NULL, &writable_sockets, &exceptional_sockets,
                        &connect_timeout
                    );
                    if (select_result > 0) {
                        if (!FD_ISSET(client, &writable_sockets) &&
                            !FD_ISSET(client, &exceptional_sockets)) {
                            error = WSAEINVAL;
                        } else if (getsockopt(
                                client, SOL_SOCKET, SO_ERROR,
                                (char *)&socket_error, &socket_error_size
                            ) == SOCKET_ERROR) {
                            error = WSAGetLastError();
                        } else {
                            error = socket_error;
                            connected = socket_error == 0;
                            denied = socket_error == WSAEACCES;
                        }
                    } else if (select_result == 0) {
                        error = WSAETIMEDOUT;
                    } else {
                        error = WSAGetLastError();
                    }
                }
            } else {
                connected = TRUE;
            }
            if (connected && send_probe_payload) {
                (void)send(client, kNetworkProbe, (int)(sizeof(kNetworkProbe) - 1), 0);
            }
        }
    }
    if (client != INVALID_SOCKET) closesocket(client);
    WSACleanup();
    *error_out = error;
    *connected_out = connected;
    return denied;
}

static BOOL write_receipt(const wchar_t *path, ProbeReceipt *receipt, unsigned stage) {
    char json[1536];
    int length;
    DWORD bytes_written = 0;
    HANDLE output;

    length = _snprintf_s(
        json, sizeof(json), _TRUNCATE,
        "{\"token_is_appcontainer\":%s,\"handle_read_ok\":%s,"
        "\"handle_write_denied\":%s,\"source_path_denied\":%s,"
        "\"sibling_path_denied\":%s,\"outside_path_denied\":%s,"
        "\"profile_path_denied\":%s,\"marker_create_denied\":%s,"
        "\"network_denied\":%s,\"network_error\":%d,"
        "\"network_connect_attempted\":%s,\"network_connected\":%s,"
        "\"network_control_error\":%d,"
        "\"network_control_connect_attempted\":%s,"
        "\"network_control_connected\":%s,"
        "\"network_isolation_diagnostic_ok\":%s,"
        "\"network_isolation_status\":%lu,"
        "\"network_isolation_error_type\":%lu,\"stage\":%u}\n",
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
        receipt->network_connect_attempted ? "true" : "false",
        receipt->network_connected ? "true" : "false",
        receipt->network_control_error,
        receipt->network_control_connect_attempted ? "true" : "false",
        receipt->network_control_connected ? "true" : "false",
        receipt->network_isolation_diagnostic_ok ? "true" : "false",
        (unsigned long)receipt->network_isolation_status,
        (unsigned long)receipt->network_isolation_error_type,
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

    if (argc == 2 && argv != NULL &&
        wcscmp(argv[1], L"--self-test-network-target") == 0) {
        return self_test_network_target_parser();
    }
    if (argc == 2 && argv != NULL &&
        wcscmp(argv[1], L"--select-private-network-target") == 0) {
        return print_private_network_target();
    }
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

    receipt.network_denied = network_connect_to_port(
        arguments.network_address, arguments.network_port, TRUE,
        &receipt.network_error,
        &receipt.network_connect_attempted, &receipt.network_connected
    );
    if (receipt.network_connect_attempted && !receipt.network_connected) {
        (void)diagnose_missing_network_capability(
            arguments.network_address,
            &receipt.network_isolation_diagnostic_ok,
            &receipt.network_isolation_status,
            &receipt.network_isolation_error_type
        );
    }
    (void)network_connect_to_port(
        arguments.network_address, arguments.network_control_port, FALSE,
        &receipt.network_control_error,
        &receipt.network_control_connect_attempted,
        &receipt.network_control_connected
    );
    receipt.completed_stage = 5;
    receipt.report_written = write_receipt(
        arguments.report_path, &receipt, receipt.completed_stage
    );

    all_checks = receipt.token_is_appcontainer && receipt.handle_read_ok &&
        receipt.handle_write_denied && receipt.source_path_denied &&
        receipt.sibling_path_denied && receipt.outside_path_denied &&
        receipt.profile_path_denied && receipt.marker_create_denied &&
        receipt.network_connect_attempted && !receipt.network_connected &&
        (receipt.network_error == WSAEACCES || receipt.network_error == WSAETIMEDOUT) &&
        receipt.network_isolation_diagnostic_ok &&
        receipt.network_isolation_status == ERROR_SUCCESS &&
        receipt.network_isolation_error_type == NETISO_ERROR_TYPE_PRIVATE_NETWORK &&
        receipt.report_written;
    return all_checks ? 0 : 1;
}
