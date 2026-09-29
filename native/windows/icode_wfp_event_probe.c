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

typedef struct WfpProbeContext {
    PSID expected_package_sid;
    UINT16 expected_remote_port;
    volatile LONG matched_capability_drop_count;
    volatile LONG matched_classify_drop_count;
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
        header->ipVersion != FWP_IP_VERSION_V4 ||
        header->ipProtocol != IPPROTO_TCP ||
        header->remoteAddrV4 != INADDR_LOOPBACK ||
        header->remotePort != context->expected_remote_port) {
        return FALSE;
    }
    return TRUE;
}

static BOOL event_matches_target(
    const FWPM_NET_EVENT3 *event,
    const WfpProbeContext *context
) {
    return event != NULL &&
        event->type == FWPM_NET_EVENT_TYPE_CAPABILITY_DROP &&
        event->capabilityDrop != NULL && event->capabilityDrop->isLoopback &&
        event_header_matches_target(event, context);
}

static BOOL event_matches_classify_drop(
    const FWPM_NET_EVENT3 *event,
    const WfpProbeContext *context
) {
    return event != NULL &&
        event->type == FWPM_NET_EVENT_TYPE_CLASSIFY_DROP &&
        event->classifyDrop != NULL && event->classifyDrop->isLoopback &&
        event_header_matches_target(event, context);
}

static void CALLBACK on_net_event(void *raw_context, const FWPM_NET_EVENT3 *event) {
    WfpProbeContext *context = (WfpProbeContext *)raw_context;

    /* The callback reads only borrowed event data and retains no event pointer. */
    if (event_matches_target(event, context)) {
        InterlockedIncrement(&context->matched_capability_drop_count);
    } else if (event_matches_classify_drop(event, context)) {
        InterlockedIncrement(&context->matched_classify_drop_count);
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

static BOOL probe_paths_are_safe(
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

    if (!is_generated_profile_name(profile_name) ||
        !get_full_path(ready_path, full_ready) ||
        !get_full_path(stop_path, full_stop) ||
        !get_full_path(result_path, full_result)) {
        return FALSE;
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
        return FALSE;
    }

    ready_leaf = wcsrchr(full_ready, L'\\');
    stop_leaf = wcsrchr(full_stop, L'\\');
    result_leaf = wcsrchr(full_result, L'\\');
    if (ready_leaf == NULL || stop_leaf == NULL || result_leaf == NULL ||
        _wcsicmp(ready_leaf + 1, expected_ready) != 0 ||
        _wcsicmp(stop_leaf + 1, expected_stop) != 0 ||
        _wcsicmp(result_leaf + 1, expected_result) != 0 ||
        !path_is_below_temp_root(full_ready) ||
        !path_is_below_temp_root(full_stop) ||
        !path_is_below_temp_root(full_result)) {
        return FALSE;
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
        return FALSE;
    }

    /* CREATE_NEW below provides a second, race-safe no-overwrite check. */
    return path_is_missing(full_ready) && path_is_missing(full_stop) &&
        path_is_missing(full_result);
}

static BOOL write_ascii_file(const wchar_t *path, const char *contents) {
    HANDLE file;
    DWORD written = 0;
    size_t length;
    BOOL ok;

    if (path == NULL || contents == NULL) {
        return FALSE;
    }
    length = strlen(contents);
    if (length > 4096) {
        return FALSE;
    }
    file = CreateFileW(
        path, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_NEW,
        FILE_ATTRIBUTE_NORMAL, NULL
    );
    if (file == INVALID_HANDLE_VALUE) {
        return FALSE;
    }
    ok = WriteFile(file, contents, (DWORD)length, &written, NULL) &&
        written == (DWORD)length;
    if (!CloseHandle(file)) {
        ok = FALSE;
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
    BOOL capability_subscription_ok,
    BOOL classify_drop_subscription_ok,
    BOOL unsubscribe_ok,
    BOOL network_events_state_known,
    BOOL network_events_collected,
    LONG matched_capability_drop_count,
    LONG matched_classify_drop_count
) {
    char json[512];
    int written = _snprintf_s(
        json, sizeof(json), _TRUNCATE,
        "{\"schema_version\":3,\"capability_subscription_ok\":%s,"
        "\"classify_drop_subscription_ok\":%s,"
        "\"unsubscribe_ok\":%s,\"network_events_collected\":%s,"
        "\"matched_capability_drop_count\":%ld,"
        "\"matched_classify_drop_count\":%ld}\n",
        capability_subscription_ok ? "true" : "false",
        classify_drop_subscription_ok ? "true" : "false",
        unsubscribe_ok ? "true" : "false",
        network_events_state_known
            ? (network_events_collected ? "true" : "false")
            : "null",
        matched_capability_drop_count,
        matched_classify_drop_count
    );
    return written > 0 && (size_t)written < sizeof(json) &&
        write_ascii_file(path, json);
}

static BOOL classifier_self_test(void) {
    FWPM_NET_EVENT3 event;
    FWPM_NET_EVENT_CAPABILITY_DROP0 drop;
    FWPM_NET_EVENT_CLASSIFY_DROP2 classify_drop;
    WfpProbeContext context = {0};
    PSID expected_sid = NULL;
    PSID other_sid = NULL;
    wchar_t temp_path[MAX_PROBE_PATH];
    wchar_t ready_path[MAX_PROBE_PATH];
    wchar_t stop_path[MAX_PROBE_PATH];
    wchar_t result_path[MAX_PROBE_PATH];
    wchar_t mismatched_path[MAX_PROBE_PATH];
    DWORD temp_length;
    BOOL passed = FALSE;

    if (!ConvertStringSidToSidW(L"S-1-15-2-1", &expected_sid) ||
        !ConvertStringSidToSidW(L"S-1-15-2-2", &other_sid)) {
        goto cleanup;
    }
    ZeroMemory(&event, sizeof(event));
    ZeroMemory(&drop, sizeof(drop));
    ZeroMemory(&classify_drop, sizeof(classify_drop));
    ZeroMemory(&context, sizeof(context));
    context.expected_package_sid = expected_sid;
    context.expected_remote_port = 54321;
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
    event.header.remoteAddrV4 = INADDR_LOOPBACK;
    event.header.remotePort = context.expected_remote_port;
    event.capabilityDrop = &drop;
    drop.isLoopback = TRUE;
    classify_drop.isLoopback = TRUE;

    if (!event_matches_target(&event, &context)) {
        goto cleanup;
    }
    event.type = FWPM_NET_EVENT_TYPE_CLASSIFY_DROP;
    event.classifyDrop = &classify_drop;
    if (!event_matches_classify_drop(&event, &context)) {
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
    event.header.remoteAddrV4 = 0x7f000002;
    if (event_matches_target(&event, &context)) {
        goto cleanup;
    }
    event.header.remoteAddrV4 = INADDR_LOOPBACK;
    event.header.flags &= ~FWPM_NET_EVENT_FLAG_PACKAGE_ID_SET;
    if (event_matches_target(&event, &context)) {
        goto cleanup;
    }
    event.header.flags |= FWPM_NET_EVENT_FLAG_PACKAGE_ID_SET;
    drop.isLoopback = FALSE;
    if (event_matches_target(&event, &context)) {
        goto cleanup;
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
    UINT16 remote_port,
    const wchar_t *ready_path,
    const wchar_t *stop_path,
    const wchar_t *result_path
) {
    PSID expected_sid = NULL;
    HANDLE engine = NULL;
    HANDLE capability_subscription_handle = NULL;
    HANDLE classify_drop_subscription_handle = NULL;
    FWPM_NET_EVENT_ENUM_TEMPLATE0 capability_event_template;
    FWPM_NET_EVENT_ENUM_TEMPLATE0 classify_drop_event_template;
    FWPM_FILTER_CONDITION0 capability_event_type_condition;
    FWPM_FILTER_CONDITION0 classify_drop_event_type_condition;
    FWPM_NET_EVENT_SUBSCRIPTION0 capability_subscription;
    FWPM_NET_EVENT_SUBSCRIPTION0 classify_drop_subscription;
    WfpProbeContext context = {0};
    HRESULT derive_result;
    DWORD api_result;
    DWORD close_result = ERROR_SUCCESS;
    FWP_VALUE0 *network_event_option = NULL;
    DWORD option_result = ERROR_SUCCESS;
    BOOL capability_subscription_ok = FALSE;
    BOOL classify_drop_subscription_ok = FALSE;
    BOOL unsubscribe_ok = FALSE;
    BOOL network_events_state_known = FALSE;
    BOOL network_events_collected = FALSE;
    BOOL stop_seen = FALSE;
    BOOL ready_written = FALSE;
    BOOL result_written = FALSE;
    LONG matched_capability_drop_count = 0;
    LONG matched_classify_drop_count = 0;
    int exit_code = 1;

    derive_result = DeriveAppContainerSidFromAppContainerName(
        profile_name, &expected_sid
    );
    if (FAILED(derive_result) || expected_sid == NULL || !IsValidSid(expected_sid)) {
        goto cleanup;
    }
    api_result = FwpmEngineOpen0(
        NULL, RPC_C_AUTHN_WINNT, NULL, NULL, &engine
    );
    if (api_result != ERROR_SUCCESS || engine == NULL) {
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

    ZeroMemory(&capability_event_template, sizeof(capability_event_template));
    ZeroMemory(&classify_drop_event_template, sizeof(classify_drop_event_template));
    ZeroMemory(&capability_event_type_condition, sizeof(capability_event_type_condition));
    ZeroMemory(&classify_drop_event_type_condition, sizeof(classify_drop_event_type_condition));
    ZeroMemory(&capability_subscription, sizeof(capability_subscription));
    ZeroMemory(&classify_drop_subscription, sizeof(classify_drop_subscription));
    ZeroMemory(&context, sizeof(context));
    context.expected_package_sid = expected_sid;
    context.expected_remote_port = remote_port;

    capability_event_type_condition.fieldKey = FWPM_CONDITION_NET_EVENT_TYPE;
    capability_event_type_condition.matchType = FWP_MATCH_EQUAL;
    capability_event_type_condition.conditionValue.type = FWP_UINT32;
    capability_event_type_condition.conditionValue.uint32 =
        FWPM_NET_EVENT_TYPE_CAPABILITY_DROP;
    capability_event_template.numFilterConditions = 1;
    capability_event_template.filterCondition = &capability_event_type_condition;
    capability_subscription.enumTemplate = &capability_event_template;

    classify_drop_event_type_condition.fieldKey = FWPM_CONDITION_NET_EVENT_TYPE;
    classify_drop_event_type_condition.matchType = FWP_MATCH_EQUAL;
    classify_drop_event_type_condition.conditionValue.type = FWP_UINT32;
    classify_drop_event_type_condition.conditionValue.uint32 =
        FWPM_NET_EVENT_TYPE_CLASSIFY_DROP;
    classify_drop_event_template.numFilterConditions = 1;
    classify_drop_event_template.filterCondition = &classify_drop_event_type_condition;
    classify_drop_subscription.enumTemplate = &classify_drop_event_template;

    api_result = FwpmNetEventSubscribe2(
        engine, &capability_subscription, on_net_event, &context,
        &capability_subscription_handle
    );
    capability_subscription_ok = api_result == ERROR_SUCCESS &&
        capability_subscription_handle != NULL;

    api_result = FwpmNetEventSubscribe2(
        engine, &classify_drop_subscription, on_net_event, &context,
        &classify_drop_subscription_handle
    );
    classify_drop_subscription_ok = api_result == ERROR_SUCCESS &&
        classify_drop_subscription_handle != NULL;

    if (!capability_subscription_ok && !classify_drop_subscription_ok) {
        goto cleanup;
    }
    ready_written = write_ascii_file(ready_path, "ready\n");
    if (!ready_written) {
        goto cleanup;
    }
    stop_seen = wait_for_stop(stop_path);

cleanup:
    unsubscribe_ok = TRUE;
    if (capability_subscription_handle != NULL && engine != NULL) {
        /* Unsubscribe drains callbacks before shared context/SID release. */
        api_result = FwpmNetEventUnsubscribe0(engine, capability_subscription_handle);
        if (api_result != ERROR_SUCCESS) {
            unsubscribe_ok = FALSE;
        }
        capability_subscription_handle = NULL;
    }
    if (classify_drop_subscription_handle != NULL && engine != NULL) {
        api_result = FwpmNetEventUnsubscribe0(engine, classify_drop_subscription_handle);
        if (api_result != ERROR_SUCCESS) {
            unsubscribe_ok = FALSE;
        }
        classify_drop_subscription_handle = NULL;
    }
    if (engine != NULL) {
        close_result = FwpmEngineClose0(engine);
        engine = NULL;
    }
    if (expected_sid != NULL) {
        FreeSid(expected_sid);
        expected_sid = NULL;
    }
    if ((capability_subscription_ok || classify_drop_subscription_ok) &&
        (!stop_seen || !unsubscribe_ok || close_result != ERROR_SUCCESS)) {
        unsubscribe_ok = FALSE;
    } else if (close_result != ERROR_SUCCESS) {
        unsubscribe_ok = FALSE;
    }
    if (!capability_subscription_ok && !classify_drop_subscription_ok &&
        !ready_written) {
        ready_written = write_ascii_file(ready_path, "unavailable\n");
    }
    matched_capability_drop_count = context.matched_capability_drop_count;
    matched_classify_drop_count = context.matched_classify_drop_count;
    result_written = write_result(
        result_path, capability_subscription_ok, classify_drop_subscription_ok,
        unsubscribe_ok, network_events_state_known, network_events_collected,
        matched_capability_drop_count, matched_classify_drop_count
    );
    if (result_written && ready_written && close_result == ERROR_SUCCESS &&
        (!(capability_subscription_ok || classify_drop_subscription_ok) ||
         (stop_seen && unsubscribe_ok))) {
        exit_code = 0;
    }
    return exit_code;
}

int wmain(int argc, wchar_t **argv) {
    UINT16 remote_port;

    if (argc == 2 && wcscmp(argv[1], L"--self-test") == 0) {
        return classifier_self_test() ? 0 : 1;
    }
    if (argc != 6 || !is_generated_profile_name(argv[1]) ||
        !parse_port(argv[2], &remote_port) ||
        argv[3][0] == L'\0' || argv[4][0] == L'\0' || argv[5][0] == L'\0' ||
        _wcsicmp(argv[3], argv[4]) == 0 || _wcsicmp(argv[3], argv[5]) == 0 ||
        _wcsicmp(argv[4], argv[5]) == 0) {
        return 2;
    }
    if (!probe_paths_are_safe(argv[1], argv[3], argv[4], argv[5])) {
        return 2;
    }
    return run_collector(argv[1], remote_port, argv[3], argv[4], argv[5]);
}
