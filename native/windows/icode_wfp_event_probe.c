#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <fwpmu.h>
#include <rpcdce.h>
#include <sddl.h>
#include <userenv.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

#define MAX_PROFILE_NAME 38
#define MAX_PROBE_PATH 32768
#define COLLECTOR_TIMEOUT_MS 30000
#define EVENT_DRAIN_DELAY_MS 200
#define PROFILE_DERIVE_RETRY_MS 10000
#define MAX_RECEIPT_EVENT_COUNT 65536
#define TARGET_FILTER_CONDITION_COUNT 3
#define IPV6_LOOPBACK_FILTER_CONDITION_COUNT 4
#define RFC1918_10_ADDRESS 0x0A000000U
#define RFC1918_10_MASK 0xFF000000U
#define RFC1918_172_ADDRESS 0xAC100000U
#define RFC1918_172_MASK 0xFFF00000U
#define RFC1918_192_ADDRESS 0xC0A80000U
#define RFC1918_192_MASK 0xFFFF0000U
#define TEST_PRIVATE_TARGET_ADDRESS 0xC0A83811U

enum RunnerProbeExitCode {
    RUNNER_PROBE_UNAVAILABLE = 1,
    RUNNER_PROBE_PROFILE_CLEANUP_FAILED = 2,
    RUNNER_PROBE_INVALID_ARGUMENTS = 3,
    RUNNER_PROBE_INVALID_PROFILE_NAME = 4,
    RUNNER_PROBE_INVALID_PORT = 5,
    RUNNER_PROBE_INVALID_PATHS = 6,
    RUNNER_PROBE_PATH_FULL_PATH_FAILED = 7,
    RUNNER_PROBE_PATH_LEAF_NAME_MISMATCH = 8,
    RUNNER_PROBE_PATH_TEMP_ROOT_REJECTED = 9,
    RUNNER_PROBE_PATH_PARENT_MISMATCH = 10,
    RUNNER_PROBE_PATH_DESTINATION_NOT_MISSING = 11
};

enum ProbePathValidation {
    PROBE_PATHS_SAFE = 0,
    PROBE_PATHS_PROFILE_NAME_INVALID = 1,
    PROBE_PATHS_FULL_PATH_FAILED = 2,
    PROBE_PATHS_LEAF_NAME_MISMATCH = 3,
    PROBE_PATHS_TEMP_ROOT_REJECTED = 4,
    PROBE_PATHS_PARENT_MISMATCH = 5,
    PROBE_PATHS_DESTINATION_NOT_MISSING = 6
};

typedef struct WfpProbeContext {
    PSID expected_package_sid;
    UINT8 expected_ip_version;
    BOOL expected_loopback;
    UINT32 expected_remote_address;
    UINT8 expected_remote_address_v6[16];
    UINT16 expected_remote_port;
    volatile LONG event_callback_count;
    volatile LONG capability_drop_event_count;
    volatile LONG classify_drop_event_count;
    volatile LONG matched_capability_drop_count;
    volatile LONG matched_classify_drop_count;
    volatile LONG matched_network_capability_id;
    volatile LONG network_capability_id_consistent;
} WfpProbeContext;

static BOOL is_generated_profile_name(const wchar_t *value) {
    size_t index;

    if (value == NULL || wcslen(value) != MAX_PROFILE_NAME ||
        wcsncmp(value, L"icode-", 6) != 0) {
        return FALSE;
    }
    for (index = 6; index < MAX_PROFILE_NAME; ++index) {
        wchar_t character = value[index];
        if (!((character >= L'0' && character <= L'9') ||
              (character >= L'a' && character <= L'f'))) {
            return FALSE;
        }
    }
    return TRUE;
}

static BOOL parse_port(const wchar_t *value, UINT16 *port_out) {
    wchar_t *end = NULL;
    unsigned long parsed;

    if (value == NULL || value[0] == L'\0' || port_out == NULL) {
        return FALSE;
    }
    parsed = wcstoul(value, &end, 10);
    if (end == value || *end != L'\0' || parsed == 0 || parsed > 65535) {
        return FALSE;
    }
    *port_out = (UINT16)parsed;
    return TRUE;
}

static BOOL parse_private_ipv4(const wchar_t *value, UINT32 *address_out) {
    UINT32 address = 0;
    unsigned int octet_index;
    const wchar_t *cursor = value;

    if (cursor == NULL || address_out == NULL) {
        return FALSE;
    }
    for (octet_index = 0; octet_index < 4; ++octet_index) {
        UINT32 octet = 0;
        size_t digit_count = 0;

        if (*cursor < L'0' || *cursor > L'9') {
            return FALSE;
        }
        if (*cursor == L'0' && cursor[1] >= L'0' && cursor[1] <= L'9') {
            return FALSE;
        }
        while (*cursor >= L'0' && *cursor <= L'9') {
            UINT32 digit = (UINT32)(*cursor - L'0');
            if (octet > (255U - digit) / 10U) {
                return FALSE;
            }
            octet = octet * 10U + digit;
            ++cursor;
            ++digit_count;
        }
        if (digit_count == 0) {
            return FALSE;
        }
        address = (address << 8) | octet;
        if (octet_index < 3) {
            if (*cursor != L'.') {
                return FALSE;
            }
            ++cursor;
        } else if (*cursor != L'\0') {
            return FALSE;
        }
    }

    /* WFP IPv4 UINT32 values use host-order numeric addresses, not socket byte order. */
    if ((address & RFC1918_10_MASK) != RFC1918_10_ADDRESS &&
        (address & RFC1918_172_MASK) != RFC1918_172_ADDRESS &&
        (address & RFC1918_192_MASK) != RFC1918_192_ADDRESS) {
        return FALSE;
    }
    *address_out = address;
    return TRUE;
}

static void initialize_target_event_template(
    FWPM_NET_EVENT_ENUM_TEMPLATE0 *event_template,
    FWPM_FILTER_CONDITION0 conditions[TARGET_FILTER_CONDITION_COUNT],
    UINT32 remote_address,
    UINT16 remote_port
) {
    ZeroMemory(event_template, sizeof(*event_template));
    ZeroMemory(conditions, sizeof(FWPM_FILTER_CONDITION0) *
        TARGET_FILTER_CONDITION_COUNT);

    conditions[0].fieldKey = FWPM_CONDITION_IP_REMOTE_ADDRESS;
    conditions[0].matchType = FWP_MATCH_EQUAL;
    conditions[0].conditionValue.type = FWP_UINT32;
    conditions[0].conditionValue.uint32 = remote_address;

    conditions[1].fieldKey = FWPM_CONDITION_IP_REMOTE_PORT;
    conditions[1].matchType = FWP_MATCH_EQUAL;
    conditions[1].conditionValue.type = FWP_UINT16;
    conditions[1].conditionValue.uint16 = remote_port;

    conditions[2].fieldKey = FWPM_CONDITION_IP_PROTOCOL;
    conditions[2].matchType = FWP_MATCH_EQUAL;
    conditions[2].conditionValue.type = FWP_UINT8;
    conditions[2].conditionValue.uint8 = IPPROTO_TCP;

    event_template->numFilterConditions = TARGET_FILTER_CONDITION_COUNT;
    event_template->filterCondition = conditions;
}

static void initialize_ipv6_loopback_event_template(
    FWPM_NET_EVENT_ENUM_TEMPLATE0 *event_template,
    FWPM_FILTER_CONDITION0 conditions[IPV6_LOOPBACK_FILTER_CONDITION_COUNT],
    FWP_V6_ADDR_AND_MASK *loopback_address,
    UINT16 remote_port
) {
    ZeroMemory(event_template, sizeof(*event_template));
    ZeroMemory(conditions, sizeof(FWPM_FILTER_CONDITION0) *
        IPV6_LOOPBACK_FILTER_CONDITION_COUNT);
    ZeroMemory(loopback_address, sizeof(*loopback_address));
    loopback_address->addr[15] = 1;
    loopback_address->prefixLength = 128;

    conditions[0].fieldKey = FWPM_CONDITION_NET_EVENT_TYPE;
    conditions[0].matchType = FWP_MATCH_EQUAL;
    conditions[0].conditionValue.type = FWP_UINT32;
    conditions[0].conditionValue.uint32 = FWPM_NET_EVENT_TYPE_CAPABILITY_DROP;

    conditions[1].fieldKey = FWPM_CONDITION_IP_REMOTE_ADDRESS;
    conditions[1].matchType = FWP_MATCH_EQUAL;
    conditions[1].conditionValue.type = FWP_V6_ADDR_MASK;
    conditions[1].conditionValue.v6AddrMask = loopback_address;

    conditions[2].fieldKey = FWPM_CONDITION_IP_REMOTE_PORT;
    conditions[2].matchType = FWP_MATCH_EQUAL;
    conditions[2].conditionValue.type = FWP_UINT16;
    conditions[2].conditionValue.uint16 = remote_port;

    conditions[3].fieldKey = FWPM_CONDITION_IP_PROTOCOL;
    conditions[3].matchType = FWP_MATCH_EQUAL;
    conditions[3].conditionValue.type = FWP_UINT8;
    conditions[3].conditionValue.uint8 = IPPROTO_TCP;

    event_template->numFilterConditions = IPV6_LOOPBACK_FILTER_CONDITION_COUNT;
    event_template->filterCondition = conditions;
}

static void increment_saturating(volatile LONG *value) {
    LONG current = InterlockedCompareExchange(value, 0, 0);

    while (current < MAX_RECEIPT_EVENT_COUNT) {
        LONG previous = InterlockedCompareExchange(value, current + 1, current);
        if (previous == current) {
            return;
        }
        current = previous;
    }
}

static BOOL event_header_matches_target(
    const FWPM_NET_EVENT3 *event,
    const WfpProbeContext *context
) {
    const FWPM_NET_EVENT_HEADER3 *header;
    const UINT32 required_flags =
        FWPM_NET_EVENT_FLAG_IP_VERSION_SET |
        FWPM_NET_EVENT_FLAG_IP_PROTOCOL_SET |
        FWPM_NET_EVENT_FLAG_REMOTE_ADDR_SET |
        FWPM_NET_EVENT_FLAG_REMOTE_PORT_SET |
        FWPM_NET_EVENT_FLAG_PACKAGE_ID_SET;

    if (event == NULL || context == NULL || context->expected_package_sid == NULL ||
        event->header.packageSid == NULL) {
        return FALSE;
    }
    header = &event->header;
    if ((header->flags & required_flags) != required_flags ||
        header->packageSid == NULL || !IsValidSid(header->packageSid) ||
        !EqualSid(header->packageSid, context->expected_package_sid) ||
        header->ipProtocol != IPPROTO_TCP ||
        header->remotePort != context->expected_remote_port) {
        return FALSE;
    }
    if (context->expected_ip_version == FWP_IP_VERSION_V4) {
        return header->ipVersion == FWP_IP_VERSION_V4 &&
            header->remoteAddrV4 == context->expected_remote_address;
    }
    if (context->expected_ip_version == FWP_IP_VERSION_V6) {
        return header->ipVersion == FWP_IP_VERSION_V6 &&
            memcmp(
                header->remoteAddrV6.byteArray16,
                context->expected_remote_address_v6,
                sizeof(context->expected_remote_address_v6)
            ) == 0;
    }
    return FALSE;
}

static BOOL event_matches_target(
    const FWPM_NET_EVENT3 *event,
    const WfpProbeContext *context
) {
    return event != NULL && context != NULL &&
        event->type == FWPM_NET_EVENT_TYPE_CAPABILITY_DROP &&
        event->capabilityDrop != NULL &&
        event->capabilityDrop->isLoopback == context->expected_loopback &&
        event_header_matches_target(event, context);
}

static BOOL event_matches_classify_drop(
    const FWPM_NET_EVENT3 *event,
    const WfpProbeContext *context
) {
    return event != NULL && context != NULL &&
        event->type == FWPM_NET_EVENT_TYPE_CLASSIFY_DROP &&
        event->classifyDrop != NULL &&
        event->classifyDrop->isLoopback == context->expected_loopback &&
        event_header_matches_target(event, context);
}

static HRESULT derive_profile_sid_bounded(
    const wchar_t *profile_name,
    PSID *sid_out,
    BOOL wait_for_profile
) {
    HRESULT result = E_FAIL;
    ULONGLONG deadline = GetTickCount64() +
        (wait_for_profile ? PROFILE_DERIVE_RETRY_MS : 0);

    if (sid_out == NULL) {
        return E_INVALIDARG;
    }
    *sid_out = NULL;
    for (;;) {
        result = DeriveAppContainerSidFromAppContainerName(
            profile_name, sid_out
        );
        if (!FAILED(result) && *sid_out != NULL && IsValidSid(*sid_out)) {
            return result;
        }
        if (*sid_out != NULL) {
            FreeSid(*sid_out);
            *sid_out = NULL;
        }
        if (!wait_for_profile || GetTickCount64() >= deadline) {
            return result;
        }
        Sleep(25);
    }
}

static void record_matched_network_capability(
    WfpProbeContext *context,
    FWPM_APPC_NETWORK_CAPABILITY_TYPE capability_id
) {
    LONG capability_value = (LONG)capability_id;
    LONG previous;

    increment_saturating(&context->matched_capability_drop_count);
    if (capability_value < FWPM_APPC_NETWORK_CAPABILITY_INTERNET_CLIENT ||
        capability_value > FWPM_APPC_NETWORK_CAPABILITY_INTERNET_PRIVATE_NETWORK) {
        InterlockedExchange(&context->network_capability_id_consistent, FALSE);
        return;
    }
    previous = InterlockedCompareExchange(
        &context->matched_network_capability_id, capability_value, -1
    );
    if (previous != -1 && previous != capability_value) {
        InterlockedExchange(&context->network_capability_id_consistent, FALSE);
    }
}

static void CALLBACK on_net_event(void *raw_context, const FWPM_NET_EVENT3 *event) {
    WfpProbeContext *context = (WfpProbeContext *)raw_context;

    /* The callback reads only borrowed event data and retains no event pointer. */
    if (context == NULL) {
        return;
    }
    increment_saturating(&context->event_callback_count);
    if (event == NULL) {
        return;
    }
    if (event->type == FWPM_NET_EVENT_TYPE_CAPABILITY_DROP) {
        increment_saturating(&context->capability_drop_event_count);
        if (event_matches_target(event, context)) {
            record_matched_network_capability(
                context, event->capabilityDrop->networkCapabilityId
            );
        }
    } else if (event->type == FWPM_NET_EVENT_TYPE_CLASSIFY_DROP) {
        increment_saturating(&context->classify_drop_event_count);
        if (event_matches_classify_drop(event, context)) {
            increment_saturating(&context->matched_classify_drop_count);
        }
    }
}

static BOOL get_full_path(const wchar_t *path, wchar_t output[MAX_PROBE_PATH]) {
    DWORD length;
    DWORD index;

    if (path == NULL || path[0] == L'\0' || output == NULL) {
        return FALSE;
    }
    length = GetFullPathNameW(path, MAX_PROBE_PATH, output, NULL);
    if (length == 0 || length >= MAX_PROBE_PATH) {
        return FALSE;
    }
    for (index = 0; index < length; ++index) {
        if (output[index] == L'/') {
            output[index] = L'\\';
        }
    }
    return TRUE;
}

static BOOL path_is_below_temp_root(const wchar_t *path) {
    wchar_t temp_path[MAX_PROBE_PATH];
    wchar_t full_temp_path[MAX_PROBE_PATH];
    DWORD temp_length;
    size_t root_length;
    size_t path_length;

    temp_length = GetTempPathW(MAX_PROBE_PATH, temp_path);
    if (temp_length == 0 || temp_length >= MAX_PROBE_PATH ||
        !get_full_path(temp_path, full_temp_path)) {
        return FALSE;
    }
    root_length = wcslen(full_temp_path);
    while (root_length > 3 && full_temp_path[root_length - 1] == L'\\') {
        full_temp_path[--root_length] = L'\0';
    }
    path_length = wcslen(path);
    if (path_length <= root_length ||
        _wcsnicmp(path, full_temp_path, root_length) != 0) {
        return FALSE;
    }
    if (full_temp_path[root_length - 1] == L'\\') {
        return TRUE;
    }
    return path[root_length] == L'\\';
}

static BOOL path_is_missing(const wchar_t *path) {
    DWORD attributes = GetFileAttributesW(path);
    DWORD error;

    if (attributes != INVALID_FILE_ATTRIBUTES) {
        return FALSE;
    }
    error = GetLastError();
    return error == ERROR_FILE_NOT_FOUND || error == ERROR_PATH_NOT_FOUND;
}

static enum ProbePathValidation validate_probe_paths(
    const wchar_t *profile_name,
    const wchar_t *ready_path,
    const wchar_t *stop_path,
    const wchar_t *result_path
) {
    wchar_t full_ready[MAX_PROBE_PATH];
    wchar_t full_stop[MAX_PROBE_PATH];
    wchar_t full_result[MAX_PROBE_PATH];
    wchar_t expected_ready[64];
    wchar_t expected_stop[64];
    wchar_t expected_result[64];
    const wchar_t *ready_leaf;
    const wchar_t *stop_leaf;
    const wchar_t *result_leaf;
    const wchar_t *ready_separator;
    const wchar_t *stop_separator;
    const wchar_t *result_separator;
    size_t ready_parent_length;
    size_t stop_parent_length;
    size_t result_parent_length;

    if (!is_generated_profile_name(profile_name)) {
        return PROBE_PATHS_PROFILE_NAME_INVALID;
    }
    if (!get_full_path(ready_path, full_ready) ||
        !get_full_path(stop_path, full_stop) ||
        !get_full_path(result_path, full_result)) {
        return PROBE_PATHS_FULL_PATH_FAILED;
    }
    if (_snwprintf_s(
            expected_ready, _countof(expected_ready), _TRUNCATE,
            L"wfp-%ls.ready", profile_name + 6) < 0 ||
        _snwprintf_s(
            expected_stop, _countof(expected_stop), _TRUNCATE,
            L"wfp-%ls.stop", profile_name + 6) < 0 ||
        _snwprintf_s(
            expected_result, _countof(expected_result), _TRUNCATE,
            L"wfp-%ls.json", profile_name + 6) < 0) {
        return PROBE_PATHS_LEAF_NAME_MISMATCH;
    }

    ready_leaf = wcsrchr(full_ready, L'\\');
    stop_leaf = wcsrchr(full_stop, L'\\');
    result_leaf = wcsrchr(full_result, L'\\');
    if (ready_leaf == NULL || stop_leaf == NULL || result_leaf == NULL ||
        _wcsicmp(ready_leaf + 1, expected_ready) != 0 ||
        _wcsicmp(stop_leaf + 1, expected_stop) != 0 ||
        _wcsicmp(result_leaf + 1, expected_result) != 0) {
        return PROBE_PATHS_LEAF_NAME_MISMATCH;
    }
    if (!path_is_below_temp_root(full_ready) ||
        !path_is_below_temp_root(full_stop) ||
        !path_is_below_temp_root(full_result)) {
        return PROBE_PATHS_TEMP_ROOT_REJECTED;
    }

    ready_separator = wcsrchr(full_ready, L'\\');
    stop_separator = wcsrchr(full_stop, L'\\');
    result_separator = wcsrchr(full_result, L'\\');
    ready_parent_length = (size_t)(ready_separator - full_ready);
    stop_parent_length = (size_t)(stop_separator - full_stop);
    result_parent_length = (size_t)(result_separator - full_result);
    if (ready_parent_length != stop_parent_length ||
        ready_parent_length != result_parent_length ||
        _wcsnicmp(full_ready, full_stop, ready_parent_length) != 0 ||
        _wcsnicmp(full_ready, full_result, ready_parent_length) != 0) {
        return PROBE_PATHS_PARENT_MISMATCH;
    }

    /* CREATE_NEW below provides a second, race-safe no-overwrite check. */
    if (!path_is_missing(full_ready) || !path_is_missing(full_stop) ||
        !path_is_missing(full_result)) {
        return PROBE_PATHS_DESTINATION_NOT_MISSING;
    }
    return PROBE_PATHS_SAFE;
}

static BOOL probe_paths_are_safe(
    const wchar_t *profile_name,
    const wchar_t *ready_path,
    const wchar_t *stop_path,
    const wchar_t *result_path
) {
    return validate_probe_paths(
        profile_name, ready_path, stop_path, result_path
    ) == PROBE_PATHS_SAFE;
}

static BOOL write_ascii_file(const wchar_t *path, const char *contents) {
    wchar_t temporary_path[MAX_PROBE_PATH];
    HANDLE file;
    DWORD written = 0;
    size_t path_length;
    size_t length;
    BOOL ok = FALSE;

    if (path == NULL || contents == NULL) {
        return FALSE;
    }
    path_length = wcslen(path);
    if (path_length == 0 || path_length > MAX_PROBE_PATH - 5) {
        return FALSE;
    }
    wmemcpy(temporary_path, path, path_length);
    wmemcpy(temporary_path + path_length, L".tmp", 5);
    length = strlen(contents);
    if (length > 4096) {
        return FALSE;
    }
    file = CreateFileW(
        temporary_path, GENERIC_WRITE, 0, NULL, CREATE_NEW,
        FILE_ATTRIBUTE_NORMAL, NULL
    );
    if (file == INVALID_HANDLE_VALUE) {
        return FALSE;
    }
    ok = WriteFile(file, contents, (DWORD)length, &written, NULL) &&
        written == (DWORD)length && FlushFileBuffers(file);
    if (!CloseHandle(file)) {
        ok = FALSE;
    }
    if (ok) {
        /* Same-directory rename exposes only a complete, non-replaced receipt. */
        ok = MoveFileExW(
            temporary_path, path, MOVEFILE_WRITE_THROUGH
        );
    }
    if (!ok) {
        (void)DeleteFileW(temporary_path);
    }
    return ok;
}

static BOOL stop_requested(const wchar_t *path) {
    return GetFileAttributesW(path) != INVALID_FILE_ATTRIBUTES;
}

static BOOL wait_for_stop(const wchar_t *path) {
    ULONGLONG deadline = GetTickCount64() + COLLECTOR_TIMEOUT_MS;

    while (GetTickCount64() < deadline) {
        if (stop_requested(path)) {
            /* Give an already queued callback a brief chance to finish first. */
            Sleep(EVENT_DRAIN_DELAY_MS);
            return TRUE;
        }
        Sleep(25);
    }
    return FALSE;
}

static BOOL write_result(
    const wchar_t *path,
    BOOL ipv6_loopback,
    BOOL subscription_attempted,
    DWORD subscription_return_code,
    BOOL subscription_handle_present,
    BOOL subscription_ok,
    BOOL unsubscribe_ok,
    BOOL network_events_state_known,
    BOOL network_events_collected,
    LONG event_callback_count,
    LONG capability_drop_event_count,
    LONG classify_drop_event_count,
    LONG matched_capability_drop_count,
    LONG matched_classify_drop_count,
    LONG matched_network_capability_id,
    BOOL network_capability_id_consistent
) {
    char json[768];
    char capability_id_text[16];
    char subscription_code_text[16];
    int written;
    if (subscription_attempted) {
        _snprintf_s(
            subscription_code_text, sizeof(subscription_code_text), _TRUNCATE,
            "%lu", (unsigned long)subscription_return_code
        );
    } else {
        strcpy_s(subscription_code_text, sizeof(subscription_code_text), "null");
    }
    if (matched_network_capability_id >=
            FWPM_APPC_NETWORK_CAPABILITY_INTERNET_CLIENT &&
        matched_network_capability_id <=
            FWPM_APPC_NETWORK_CAPABILITY_INTERNET_PRIVATE_NETWORK) {
        _snprintf_s(
            capability_id_text, sizeof(capability_id_text), _TRUNCATE,
            "%ld", matched_network_capability_id
        );
    } else {
        strcpy_s(capability_id_text, sizeof(capability_id_text), "null");
    }
    if (ipv6_loopback) {
        written = _snprintf_s(
            json, sizeof(json), _TRUNCATE,
            "{\"schema_version\":7,\"target_ip_version\":6,"
            "\"target_is_loopback\":true,\"subscription_attempted\":%s,"
            "\"subscription_return_code\":%s,"
            "\"subscription_handle_present\":%s,\"subscription_ok\":%s,"
            "\"unsubscribe_ok\":%s,\"network_events_collected\":%s,"
            "\"event_callback_count\":%ld,"
            "\"capability_drop_event_count\":%ld,"
            "\"classify_drop_event_count\":%ld,"
            "\"matched_capability_drop_count\":%ld,"
            "\"matched_classify_drop_count\":%ld,"
            "\"matched_network_capability_id\":%s,"
            "\"network_capability_id_consistent\":%s}\n",
            subscription_attempted ? "true" : "false",
            subscription_code_text,
            subscription_handle_present ? "true" : "false",
            subscription_ok ? "true" : "false",
            unsubscribe_ok ? "true" : "false",
            network_events_state_known
                ? (network_events_collected ? "true" : "false")
                : "null",
            event_callback_count,
            capability_drop_event_count,
            classify_drop_event_count,
            matched_capability_drop_count,
            matched_classify_drop_count,
            capability_id_text,
            network_capability_id_consistent ? "true" : "false"
        );
    } else {
        written = _snprintf_s(
            json, sizeof(json), _TRUNCATE,
            "{\"schema_version\":6,\"subscription_attempted\":%s,"
            "\"subscription_return_code\":%s,"
            "\"subscription_handle_present\":%s,\"subscription_ok\":%s,"
            "\"unsubscribe_ok\":%s,\"network_events_collected\":%s,"
            "\"event_callback_count\":%ld,"
            "\"capability_drop_event_count\":%ld,"
            "\"classify_drop_event_count\":%ld,"
            "\"matched_capability_drop_count\":%ld,"
            "\"matched_classify_drop_count\":%ld,"
            "\"matched_network_capability_id\":%s,"
            "\"network_capability_id_consistent\":%s}\n",
            subscription_attempted ? "true" : "false",
            subscription_code_text,
            subscription_handle_present ? "true" : "false",
            subscription_ok ? "true" : "false",
            unsubscribe_ok ? "true" : "false",
            network_events_state_known
                ? (network_events_collected ? "true" : "false")
                : "null",
            event_callback_count,
            capability_drop_event_count,
            classify_drop_event_count,
            matched_capability_drop_count,
            matched_classify_drop_count,
            capability_id_text,
            network_capability_id_consistent ? "true" : "false"
        );
    }
    return written > 0 && (size_t)written < sizeof(json) &&
        write_ascii_file(path, json);
}

static BOOL classifier_self_test(void) {
    FWPM_NET_EVENT3 event;
    FWPM_NET_EVENT_CAPABILITY_DROP0 drop;
    FWPM_NET_EVENT_CLASSIFY_DROP2 classify_drop;
    FWPM_NET_EVENT_ENUM_TEMPLATE0 event_template;
    FWPM_FILTER_CONDITION0 filter_conditions[TARGET_FILTER_CONDITION_COUNT];
    WfpProbeContext context = {0};
    PSID expected_sid = NULL;
    PSID other_sid = NULL;
    wchar_t temp_path[MAX_PROBE_PATH];
    wchar_t ready_path[MAX_PROBE_PATH];
    wchar_t stop_path[MAX_PROBE_PATH];
    wchar_t result_path[MAX_PROBE_PATH];
    wchar_t mismatched_path[MAX_PROBE_PATH];
    DWORD temp_length;
    UINT32 parsed_target = 0;
    BOOL passed = FALSE;

    if (FWPM_APPC_NETWORK_CAPABILITY_INTERNET_CLIENT != 0 ||
        FWPM_APPC_NETWORK_CAPABILITY_INTERNET_CLIENT_SERVER != 1 ||
        FWPM_APPC_NETWORK_CAPABILITY_INTERNET_PRIVATE_NETWORK != 2 ||
        !parse_private_ipv4(L"192.168.56.17", &parsed_target) ||
        parsed_target != TEST_PRIVATE_TARGET_ADDRESS ||
        parse_private_ipv4(L"127.0.0.1", &parsed_target) ||
        parse_private_ipv4(L"172.32.1.2", &parsed_target) ||
        parse_private_ipv4(L"192.168.056.17", &parsed_target) ||
        parse_private_ipv4(L"192.168.56.256", &parsed_target)) {
        goto cleanup;
    }
    initialize_target_event_template(
        &event_template, filter_conditions,
        TEST_PRIVATE_TARGET_ADDRESS, 54321
    );
    if (event_template.numFilterConditions != TARGET_FILTER_CONDITION_COUNT ||
        event_template.filterCondition != filter_conditions ||
        !IsEqualGUID(
            &filter_conditions[0].fieldKey,
            &FWPM_CONDITION_IP_REMOTE_ADDRESS
        ) || filter_conditions[0].conditionValue.type != FWP_UINT32 ||
        filter_conditions[0].conditionValue.uint32 != TEST_PRIVATE_TARGET_ADDRESS ||
        !IsEqualGUID(
            &filter_conditions[1].fieldKey,
            &FWPM_CONDITION_IP_REMOTE_PORT
        ) || filter_conditions[1].conditionValue.type != FWP_UINT16 ||
        filter_conditions[1].conditionValue.uint16 != 54321 ||
        !IsEqualGUID(
            &filter_conditions[2].fieldKey,
            &FWPM_CONDITION_IP_PROTOCOL
        ) || filter_conditions[2].conditionValue.type != FWP_UINT8 ||
        filter_conditions[2].conditionValue.uint8 != IPPROTO_TCP) {
        goto cleanup;
    }
    if (!ConvertStringSidToSidW(L"S-1-15-2-1", &expected_sid) ||
        !ConvertStringSidToSidW(L"S-1-15-2-2", &other_sid)) {
        goto cleanup;
    }
    ZeroMemory(&event, sizeof(event));
    ZeroMemory(&drop, sizeof(drop));
    ZeroMemory(&classify_drop, sizeof(classify_drop));
    ZeroMemory(&context, sizeof(context));
    context.expected_package_sid = expected_sid;
    context.expected_ip_version = FWP_IP_VERSION_V4;
    context.expected_remote_address = TEST_PRIVATE_TARGET_ADDRESS;
    context.expected_remote_port = 54321;
    context.matched_network_capability_id = -1;
    context.network_capability_id_consistent = TRUE;
    event.type = FWPM_NET_EVENT_TYPE_CAPABILITY_DROP;
    event.header.flags =
        FWPM_NET_EVENT_FLAG_IP_VERSION_SET |
        FWPM_NET_EVENT_FLAG_IP_PROTOCOL_SET |
        FWPM_NET_EVENT_FLAG_REMOTE_ADDR_SET |
        FWPM_NET_EVENT_FLAG_REMOTE_PORT_SET |
        FWPM_NET_EVENT_FLAG_PACKAGE_ID_SET;
    event.header.packageSid = expected_sid;
    event.header.ipVersion = FWP_IP_VERSION_V4;
    event.header.ipProtocol = IPPROTO_TCP;
    event.header.remoteAddrV4 = context.expected_remote_address;
    event.header.remotePort = context.expected_remote_port;
    event.capabilityDrop = &drop;
    drop.isLoopback = FALSE;
    drop.networkCapabilityId =
        FWPM_APPC_NETWORK_CAPABILITY_INTERNET_PRIVATE_NETWORK;
    classify_drop.isLoopback = FALSE;

    if (!event_matches_target(&event, &context)) {
        goto cleanup;
    }
    on_net_event(&context, &event);
    if (context.event_callback_count != 1 ||
        context.capability_drop_event_count != 1 ||
        context.matched_capability_drop_count != 1 ||
        context.matched_network_capability_id !=
            FWPM_APPC_NETWORK_CAPABILITY_INTERNET_PRIVATE_NETWORK ||
        context.network_capability_id_consistent != TRUE) {
        goto cleanup;
    }
    event.type = FWPM_NET_EVENT_TYPE_CLASSIFY_DROP;
    event.classifyDrop = &classify_drop;
    if (!event_matches_classify_drop(&event, &context)) {
        goto cleanup;
    }
    on_net_event(&context, &event);
    if (context.event_callback_count != 2 ||
        context.capability_drop_event_count != 1 ||
        context.classify_drop_event_count != 1 ||
        context.matched_capability_drop_count != 1 ||
        context.matched_classify_drop_count != 1) {
        goto cleanup;
    }
    if (event_matches_target(&event, &context)) {
        goto cleanup;
    }
    event.type = FWPM_NET_EVENT_TYPE_CAPABILITY_DROP;
    event.capabilityDrop = &drop;
    event.header.packageSid = other_sid;
    if (event_matches_target(&event, &context)) {
        goto cleanup;
    }
    event.header.packageSid = expected_sid;
    event.header.remotePort++;
    if (event_matches_target(&event, &context)) {
        goto cleanup;
    }
    event.header.remotePort = context.expected_remote_port;
    event.header.remoteAddrV4 = context.expected_remote_address + 1U;
    if (event_matches_target(&event, &context)) {
        goto cleanup;
    }
    event.header.remoteAddrV4 = context.expected_remote_address;
    event.header.ipProtocol = IPPROTO_UDP;
    if (event_matches_target(&event, &context)) {
        goto cleanup;
    }
    event.header.ipProtocol = IPPROTO_TCP;
    event.header.ipVersion = FWP_IP_VERSION_V6;
    if (event_matches_target(&event, &context)) {
        goto cleanup;
    }
    event.header.ipVersion = FWP_IP_VERSION_V4;
    event.header.flags &= ~FWPM_NET_EVENT_FLAG_PACKAGE_ID_SET;
    if (event_matches_target(&event, &context)) {
        goto cleanup;
    }
    event.header.flags |= FWPM_NET_EVENT_FLAG_PACKAGE_ID_SET;
    drop.isLoopback = TRUE;
    if (event_matches_target(&event, &context)) {
        goto cleanup;
    }
    drop.isLoopback = FALSE;
    {
        WfpProbeContext mixed_context = {0};
        mixed_context.expected_package_sid = expected_sid;
        mixed_context.expected_ip_version = FWP_IP_VERSION_V4;
        mixed_context.expected_remote_address = context.expected_remote_address;
        mixed_context.expected_remote_port = context.expected_remote_port;
        mixed_context.matched_network_capability_id = -1;
        mixed_context.network_capability_id_consistent = TRUE;
        drop.networkCapabilityId =
            FWPM_APPC_NETWORK_CAPABILITY_INTERNET_PRIVATE_NETWORK;
        on_net_event(&mixed_context, &event);
        drop.networkCapabilityId =
            FWPM_APPC_NETWORK_CAPABILITY_INTERNET_CLIENT;
        on_net_event(&mixed_context, &event);
        if (mixed_context.matched_capability_drop_count != 2 ||
            mixed_context.matched_network_capability_id !=
                FWPM_APPC_NETWORK_CAPABILITY_INTERNET_PRIVATE_NETWORK ||
            mixed_context.network_capability_id_consistent != FALSE) {
            goto cleanup;
        }
    }

    {
        FWPM_FILTER_CONDITION0 ipv6_conditions[
            IPV6_LOOPBACK_FILTER_CONDITION_COUNT
        ];
        FWPM_NET_EVENT3 ipv6_event;
        FWPM_NET_EVENT_CAPABILITY_DROP0 ipv6_drop;
        FWPM_NET_EVENT_ENUM_TEMPLATE0 ipv6_template;
        FWP_V6_ADDR_AND_MASK ipv6_mask;
        WfpProbeContext ipv6_context = {0};
        UINT8 expected_loopback[16] = {0};

        expected_loopback[15] = 1;
        initialize_ipv6_loopback_event_template(
            &ipv6_template, ipv6_conditions, &ipv6_mask, 54322
        );
        if (ipv6_template.numFilterConditions !=
                IPV6_LOOPBACK_FILTER_CONDITION_COUNT ||
            ipv6_template.filterCondition != ipv6_conditions ||
            !IsEqualGUID(
                &ipv6_conditions[0].fieldKey,
                &FWPM_CONDITION_NET_EVENT_TYPE
            ) || ipv6_conditions[0].conditionValue.type != FWP_UINT32 ||
            ipv6_conditions[0].conditionValue.uint32 !=
                FWPM_NET_EVENT_TYPE_CAPABILITY_DROP ||
            !IsEqualGUID(
                &ipv6_conditions[1].fieldKey,
                &FWPM_CONDITION_IP_REMOTE_ADDRESS
            ) || ipv6_conditions[1].conditionValue.type != FWP_V6_ADDR_MASK ||
            ipv6_conditions[1].conditionValue.v6AddrMask != &ipv6_mask ||
            memcmp(ipv6_mask.addr, expected_loopback, sizeof(expected_loopback)) != 0 ||
            ipv6_mask.prefixLength != 128 ||
            !IsEqualGUID(
                &ipv6_conditions[2].fieldKey,
                &FWPM_CONDITION_IP_REMOTE_PORT
            ) || ipv6_conditions[2].conditionValue.type != FWP_UINT16 ||
            ipv6_conditions[2].conditionValue.uint16 != 54322 ||
            !IsEqualGUID(
                &ipv6_conditions[3].fieldKey,
                &FWPM_CONDITION_IP_PROTOCOL
            ) || ipv6_conditions[3].conditionValue.type != FWP_UINT8 ||
            ipv6_conditions[3].conditionValue.uint8 != IPPROTO_TCP) {
            goto cleanup;
        }

        ZeroMemory(&ipv6_event, sizeof(ipv6_event));
        ZeroMemory(&ipv6_drop, sizeof(ipv6_drop));
        ipv6_context.expected_package_sid = expected_sid;
        ipv6_context.expected_ip_version = FWP_IP_VERSION_V6;
        ipv6_context.expected_loopback = TRUE;
        memcpy(
            ipv6_context.expected_remote_address_v6,
            expected_loopback,
            sizeof(expected_loopback)
        );
        ipv6_context.expected_remote_port = 54322;
        ipv6_context.matched_network_capability_id = -1;
        ipv6_context.network_capability_id_consistent = TRUE;

        ipv6_event.type = FWPM_NET_EVENT_TYPE_CAPABILITY_DROP;
        ipv6_event.header.flags =
            FWPM_NET_EVENT_FLAG_IP_VERSION_SET |
            FWPM_NET_EVENT_FLAG_IP_PROTOCOL_SET |
            FWPM_NET_EVENT_FLAG_REMOTE_ADDR_SET |
            FWPM_NET_EVENT_FLAG_REMOTE_PORT_SET |
            FWPM_NET_EVENT_FLAG_PACKAGE_ID_SET;
        ipv6_event.header.packageSid = expected_sid;
        ipv6_event.header.ipVersion = FWP_IP_VERSION_V6;
        ipv6_event.header.ipProtocol = IPPROTO_TCP;
        memcpy(
            ipv6_event.header.remoteAddrV6.byteArray16,
            expected_loopback,
            sizeof(expected_loopback)
        );
        ipv6_event.header.remotePort = ipv6_context.expected_remote_port;
        ipv6_event.capabilityDrop = &ipv6_drop;
        ipv6_drop.isLoopback = TRUE;
        ipv6_drop.networkCapabilityId =
            FWPM_APPC_NETWORK_CAPABILITY_INTERNET_CLIENT;
        if (!event_matches_target(&ipv6_event, &ipv6_context)) {
            goto cleanup;
        }
        on_net_event(&ipv6_context, &ipv6_event);
        if (ipv6_context.event_callback_count != 1 ||
            ipv6_context.matched_capability_drop_count != 1 ||
            ipv6_context.matched_network_capability_id !=
                FWPM_APPC_NETWORK_CAPABILITY_INTERNET_CLIENT ||
            ipv6_context.network_capability_id_consistent != TRUE) {
            goto cleanup;
        }
        ipv6_drop.isLoopback = FALSE;
        if (event_matches_target(&ipv6_event, &ipv6_context)) {
            goto cleanup;
        }
        ipv6_drop.isLoopback = TRUE;
        ipv6_event.header.remoteAddrV6.byteArray16[15] = 2;
        if (event_matches_target(&ipv6_event, &ipv6_context)) {
            goto cleanup;
        }
        ipv6_event.header.remoteAddrV6.byteArray16[15] = 1;
        ipv6_event.header.remotePort++;
        if (event_matches_target(&ipv6_event, &ipv6_context)) {
            goto cleanup;
        }
        ipv6_event.header.remotePort--;
        ipv6_event.header.ipProtocol = IPPROTO_UDP;
        if (event_matches_target(&ipv6_event, &ipv6_context)) {
            goto cleanup;
        }
        ipv6_event.header.ipProtocol = IPPROTO_TCP;
        ipv6_event.header.packageSid = other_sid;
        if (event_matches_target(&ipv6_event, &ipv6_context)) {
            goto cleanup;
        }
        ipv6_event.header.packageSid = expected_sid;
        ipv6_event.header.ipVersion = FWP_IP_VERSION_V4;
        if (event_matches_target(&ipv6_event, &ipv6_context)) {
            goto cleanup;
        }
    }

    temp_length = GetTempPathW(MAX_PROBE_PATH, temp_path);
    if (temp_length == 0 || temp_length >= MAX_PROBE_PATH) {
        goto cleanup;
    }
    if (_snwprintf_s(
            ready_path, _countof(ready_path), _TRUNCATE,
            L"%lswfp-0123456789abcdef0123456789abcdef.ready", temp_path) < 0 ||
        _snwprintf_s(
            stop_path, _countof(stop_path), _TRUNCATE,
            L"%lswfp-0123456789abcdef0123456789abcdef.stop", temp_path) < 0 ||
        _snwprintf_s(
            result_path, _countof(result_path), _TRUNCATE,
            L"%lswfp-0123456789abcdef0123456789abcdef.json", temp_path) < 0 ||
        !probe_paths_are_safe(
            L"icode-0123456789abcdef0123456789abcdef",
            ready_path, stop_path, result_path)) {
        goto cleanup;
    }
    if (_snwprintf_s(
            mismatched_path, _countof(mismatched_path), _TRUNCATE,
            L"%lswfp-ffffffffffffffffffffffffffffffff.stop", temp_path) < 0 ||
        probe_paths_are_safe(
            L"icode-0123456789abcdef0123456789abcdef",
            ready_path, mismatched_path, result_path)) {
        goto cleanup;
    }
    passed = TRUE;

cleanup:
    if (other_sid != NULL) {
        LocalFree(other_sid);
    }
    if (expected_sid != NULL) {
        LocalFree(expected_sid);
    }
    return passed;
}

static int run_collector(
    const wchar_t *profile_name,
    UINT32 remote_address,
    UINT16 remote_port,
    BOOL ipv6_loopback,
    BOOL report_setup_stage,
    BOOL wait_for_profile,
    const wchar_t *ready_path,
    const wchar_t *stop_path,
    const wchar_t *result_path
) {
    PSID expected_sid = NULL;
    HANDLE engine = NULL;
    HANDLE subscription_handle = NULL;
    FWPM_NET_EVENT_ENUM_TEMPLATE0 event_template;
    FWPM_FILTER_CONDITION0 filter_conditions[IPV6_LOOPBACK_FILTER_CONDITION_COUNT];
    FWP_V6_ADDR_AND_MASK ipv6_loopback_address;
    FWPM_NET_EVENT_SUBSCRIPTION0 subscription;
    WfpProbeContext context = {0};
    HRESULT derive_result;
    DWORD api_result;
    DWORD close_result = ERROR_SUCCESS;
    FWP_VALUE0 *network_event_option = NULL;
    DWORD option_result = ERROR_SUCCESS;
    DWORD subscription_return_code = ERROR_SUCCESS;
    BOOL subscription_attempted = FALSE;
    BOOL subscription_handle_present = FALSE;
    BOOL subscription_ok = FALSE;
    BOOL unsubscribe_ok = FALSE;
    BOOL network_events_state_known = FALSE;
    BOOL network_events_collected = FALSE;
    BOOL stop_seen = FALSE;
    BOOL ready_written = FALSE;
    BOOL result_written = FALSE;
    const char *setup_failure_status = "unavailable\n";
    LONG event_callback_count = 0;
    LONG capability_drop_event_count = 0;
    LONG classify_drop_event_count = 0;
    LONG matched_capability_drop_count = 0;
    LONG matched_classify_drop_count = 0;
    LONG matched_network_capability_id = -1;
    BOOL network_capability_id_consistent = FALSE;
    int exit_code = 1;

    ZeroMemory(&ipv6_loopback_address, sizeof(ipv6_loopback_address));
    context.matched_network_capability_id = -1;
    context.network_capability_id_consistent = TRUE;
    derive_result = derive_profile_sid_bounded(
        profile_name, &expected_sid, wait_for_profile
    );
    if (FAILED(derive_result) || expected_sid == NULL || !IsValidSid(expected_sid)) {
        if (report_setup_stage) {
            setup_failure_status = "sid-derive-failed\n";
        }
        goto cleanup;
    }
    api_result = FwpmEngineOpen0(
        NULL, RPC_C_AUTHN_WINNT, NULL, NULL, &engine
    );
    if (api_result != ERROR_SUCCESS || engine == NULL) {
        if (report_setup_stage) {
            setup_failure_status = "engine-open-failed\n";
        }
        goto cleanup;
    }

    option_result = FwpmEngineGetOption0(
        engine, FWPM_ENGINE_COLLECT_NET_EVENTS, &network_event_option
    );
    if (option_result == ERROR_SUCCESS && network_event_option != NULL &&
        network_event_option->type == FWP_UINT32 &&
        network_event_option->uint32 <= 1) {
        network_events_state_known = TRUE;
        network_events_collected = network_event_option->uint32 == 1;
    }
    if (network_event_option != NULL) {
        FwpmFreeMemory0((void **)&network_event_option);
        network_event_option = NULL;
    }

    ZeroMemory(&subscription, sizeof(subscription));
    ZeroMemory(&context, sizeof(context));
    context.expected_package_sid = expected_sid;
    context.expected_remote_port = remote_port;
    context.matched_network_capability_id = -1;
    context.network_capability_id_consistent = TRUE;
    if (ipv6_loopback) {
        context.expected_ip_version = FWP_IP_VERSION_V6;
        context.expected_loopback = TRUE;
        context.expected_remote_address_v6[15] = 1;
        initialize_ipv6_loopback_event_template(
            &event_template, filter_conditions, &ipv6_loopback_address,
            remote_port
        );
    } else {
        context.expected_ip_version = FWP_IP_VERSION_V4;
        context.expected_loopback = FALSE;
        context.expected_remote_address = remote_address;
        initialize_target_event_template(
            &event_template, filter_conditions, remote_address, remote_port
        );
    }
    /* The subscription is limited to this endpoint; callback checks package SID. */
    subscription.enumTemplate = &event_template;
    subscription_attempted = TRUE;
    subscription_return_code = FwpmNetEventSubscribe2(
        engine, &subscription, on_net_event, &context, &subscription_handle
    );
    subscription_handle_present = subscription_handle != NULL;
    subscription_ok = subscription_return_code == ERROR_SUCCESS &&
        subscription_handle_present;
    if (!subscription_ok) {
        if (report_setup_stage) {
            setup_failure_status = "subscribe-failed\n";
        }
        goto cleanup;
    }
    ready_written = write_ascii_file(
        ready_path,
        report_setup_stage ? "subscription-ready\n" : "ready\n"
    );
    if (!ready_written) {
        goto cleanup;
    }
    stop_seen = wait_for_stop(stop_path);

cleanup:
    unsubscribe_ok = TRUE;
    if (subscription_handle != NULL && engine != NULL) {
        /* Unsubscribe drains callbacks before shared context/SID release. */
        api_result = FwpmNetEventUnsubscribe0(engine, subscription_handle);
        if (api_result != ERROR_SUCCESS) {
            /*
             * A failed unsubscribe does not guarantee callbacks were drained.
             * This one-shot helper must terminate before releasing callback
             * state; the parent treats its nonzero exit and missing receipt as
             * unavailable diagnostic evidence.
             */
            TerminateProcess(GetCurrentProcess(), ERROR_GEN_FAILURE);
            ExitProcess(ERROR_GEN_FAILURE);
        }
        subscription_handle = NULL;
    }
    if (engine != NULL) {
        close_result = FwpmEngineClose0(engine);
        engine = NULL;
    }
    if (expected_sid != NULL) {
        FreeSid(expected_sid);
        expected_sid = NULL;
    }
    if (subscription_ok &&
        (!stop_seen || !unsubscribe_ok || close_result != ERROR_SUCCESS)) {
        unsubscribe_ok = FALSE;
    } else if (close_result != ERROR_SUCCESS) {
        unsubscribe_ok = FALSE;
    }
    if (!subscription_ok && !ready_written) {
        ready_written = write_ascii_file(
            ready_path,
            report_setup_stage ? setup_failure_status : "unavailable\n"
        );
    }
    event_callback_count = context.event_callback_count;
    capability_drop_event_count = context.capability_drop_event_count;
    classify_drop_event_count = context.classify_drop_event_count;
    matched_capability_drop_count = context.matched_capability_drop_count;
    matched_classify_drop_count = context.matched_classify_drop_count;
    matched_network_capability_id = context.matched_network_capability_id;
    network_capability_id_consistent =
        context.network_capability_id_consistent != FALSE;
    result_written = write_result(
        result_path, ipv6_loopback, subscription_attempted,
        subscription_return_code, subscription_handle_present, subscription_ok,
        unsubscribe_ok, network_events_state_known, network_events_collected,
        event_callback_count, capability_drop_event_count,
        classify_drop_event_count,
        matched_capability_drop_count, matched_classify_drop_count,
        matched_network_capability_id, network_capability_id_consistent
    );
    if (result_written && ready_written && close_result == ERROR_SUCCESS &&
        (!subscription_ok || (stop_seen && unsubscribe_ok))) {
        exit_code = 0;
    }
    return exit_code;
}

static int run_runner_subscription_probe(
    const wchar_t *profile_name,
    UINT16 remote_port,
    const wchar_t *ready_path,
    const wchar_t *stop_path,
    const wchar_t *result_path
) {
    PSID created_sid = NULL;
    HRESULT create_result;
    HRESULT delete_result;
    int probe_result;

    /* A newly registered profile makes SID derivation a meaningful precondition. */
    create_result = CreateAppContainerProfile(
        profile_name,
        L"ICODE WFP Permission Probe",
        L"Temporary zero-capability CI diagnostic profile",
        NULL,
        0,
        &created_sid
    );
    if (create_result != S_OK) {
        (void)write_ascii_file(ready_path, "profile-create-failed\n");
        if (created_sid != NULL && IsValidSid(created_sid)) {
            FreeSid(created_sid);
        }
        /* In particular, never delete a profile that already existed. */
        return RUNNER_PROBE_UNAVAILABLE;
    }
    if (created_sid == NULL || !IsValidSid(created_sid)) {
        (void)write_ascii_file(ready_path, "profile-sid-invalid\n");
        if (created_sid != NULL && IsValidSid(created_sid)) {
            FreeSid(created_sid);
        }
        delete_result = DeleteAppContainerProfile(profile_name);
        return delete_result == S_OK
            ? RUNNER_PROBE_UNAVAILABLE
            : RUNNER_PROBE_PROFILE_CLEANUP_FAILED;
    }

    /* run_collector unsubscribes and closes its engine before it returns. */
    probe_result = run_collector(
        profile_name, 0, remote_port, TRUE, TRUE, FALSE,
        ready_path, stop_path, result_path
    );
    FreeSid(created_sid);
    created_sid = NULL;

    delete_result = DeleteAppContainerProfile(profile_name);
    if (delete_result != S_OK) {
        return RUNNER_PROBE_PROFILE_CLEANUP_FAILED;
    }
    return probe_result;
}

int wmain(int argc, wchar_t **argv) {
    UINT32 remote_address;
    UINT16 remote_port;
    enum ProbePathValidation path_status;

    if (argc == 2 && wcscmp(argv[1], L"--self-test") == 0) {
        return classifier_self_test() ? 0 : 1;
    }
    if (argc >= 2 && wcscmp(argv[1], L"--probe-runner-subscription") == 0) {
        if (argc != 7) {
            return RUNNER_PROBE_INVALID_ARGUMENTS;
        }
        if (!is_generated_profile_name(argv[2])) {
            return RUNNER_PROBE_INVALID_PROFILE_NAME;
        }
        if (!parse_port(argv[3], &remote_port)) {
            return RUNNER_PROBE_INVALID_PORT;
        }
        if (argv[4][0] == L'\0' || argv[5][0] == L'\0' || argv[6][0] == L'\0' ||
            _wcsicmp(argv[4], argv[5]) == 0 || _wcsicmp(argv[4], argv[6]) == 0 ||
            _wcsicmp(argv[5], argv[6]) == 0) {
            return RUNNER_PROBE_INVALID_PATHS;
        }
        path_status = validate_probe_paths(argv[2], argv[4], argv[5], argv[6]);
        switch (path_status) {
        case PROBE_PATHS_SAFE:
            break;
        case PROBE_PATHS_PROFILE_NAME_INVALID:
            return RUNNER_PROBE_INVALID_PROFILE_NAME;
        case PROBE_PATHS_FULL_PATH_FAILED:
            return RUNNER_PROBE_PATH_FULL_PATH_FAILED;
        case PROBE_PATHS_LEAF_NAME_MISMATCH:
            return RUNNER_PROBE_PATH_LEAF_NAME_MISMATCH;
        case PROBE_PATHS_TEMP_ROOT_REJECTED:
            return RUNNER_PROBE_PATH_TEMP_ROOT_REJECTED;
        case PROBE_PATHS_PARENT_MISMATCH:
            return RUNNER_PROBE_PATH_PARENT_MISMATCH;
        case PROBE_PATHS_DESTINATION_NOT_MISSING:
            return RUNNER_PROBE_PATH_DESTINATION_NOT_MISSING;
        default:
            return RUNNER_PROBE_INVALID_PATHS;
        }
        return run_runner_subscription_probe(
            argv[2], remote_port, argv[4], argv[5], argv[6]
        );
    }
    if (argc == 7 && wcscmp(argv[1], L"--collect-ipv6-loopback") == 0) {
        if (!is_generated_profile_name(argv[2]) ||
            !parse_port(argv[3], &remote_port) ||
            argv[4][0] == L'\0' || argv[5][0] == L'\0' || argv[6][0] == L'\0' ||
            _wcsicmp(argv[4], argv[5]) == 0 || _wcsicmp(argv[4], argv[6]) == 0 ||
            _wcsicmp(argv[5], argv[6]) == 0 ||
            !probe_paths_are_safe(argv[2], argv[4], argv[5], argv[6])) {
            return 2;
        }
        return run_collector(
            argv[2], 0, remote_port, TRUE, FALSE, FALSE,
            argv[4], argv[5], argv[6]
        );
    }
    if (argc == 7 &&
        wcscmp(argv[1], L"--collect-ipv6-loopback-wait-profile") == 0) {
        if (!is_generated_profile_name(argv[2]) ||
            !parse_port(argv[3], &remote_port) ||
            argv[4][0] == L'\0' || argv[5][0] == L'\0' || argv[6][0] == L'\0' ||
            _wcsicmp(argv[4], argv[5]) == 0 || _wcsicmp(argv[4], argv[6]) == 0 ||
            _wcsicmp(argv[5], argv[6]) == 0 ||
            !probe_paths_are_safe(argv[2], argv[4], argv[5], argv[6])) {
            return 2;
        }
        return run_collector(
            argv[2], 0, remote_port, TRUE, TRUE, TRUE,
            argv[4], argv[5], argv[6]
        );
    }
    if (argc != 7 || !is_generated_profile_name(argv[1]) ||
        !parse_private_ipv4(argv[2], &remote_address) ||
        !parse_port(argv[3], &remote_port) ||
        argv[4][0] == L'\0' || argv[5][0] == L'\0' || argv[6][0] == L'\0' ||
        _wcsicmp(argv[4], argv[5]) == 0 || _wcsicmp(argv[4], argv[6]) == 0 ||
        _wcsicmp(argv[5], argv[6]) == 0) {
        return 2;
    }
    if (!probe_paths_are_safe(argv[1], argv[4], argv[5], argv[6])) {
        return 2;
    }
    return run_collector(
        argv[1], remote_address, remote_port, FALSE, FALSE, FALSE,
        argv[4], argv[5], argv[6]
    );
}
