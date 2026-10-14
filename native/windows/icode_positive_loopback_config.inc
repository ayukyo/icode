/* Fixed positive-profile diagnostic only; no profile/network/config mutation. */
typedef DWORD (WINAPI *PositiveLoopbackGetConfigFn)(DWORD *, PSID_AND_ATTRIBUTES *);
_Static_assert(sizeof(DWORD) == 4, "Win32 DWORD width");
_Static_assert(sizeof(((SID_AND_ATTRIBUTES *)0)->Attributes) == 4, "SDK attributes width");

static int observe_positive_loopback_config(const wchar_t *profile) {
    HMODULE library = NULL;
    PositiveLoopbackGetConfigFn query = NULL;
    PSID target = NULL;
    PSID_AND_ATTRIBUTES entries = NULL;
    PSID pointers[4096];
    DWORD count = 0, code = 0, attributes = 0;
    unsigned attempted = 0, confirmed = 0, index, previous;
    int code_present = 0, count_present = 0, match = -1, target_alias = 0;
    int ownership_safe = 1, targets = 0;
    const char *status = "complete", *stage = "none";
    const char *array_release = "not_acquired", *target_release = "not_acquired";
    const char *library_release = "not_acquired";
    wchar_t path[MAX_PATH + 32];
    UINT length;
    HRESULT derived;
    if (!is_generated_profile_name(profile)) return 2;

    length = GetSystemDirectoryW(path, (UINT)(sizeof(path) / sizeof(path[0])));
    if (!length || length >= sizeof(path) / sizeof(path[0]) ||
        length + wcslen(L"\\FirewallAPI.dll") >= sizeof(path) / sizeof(path[0])) {
        status = "load_failed"; stage = "load";
        code = length ? ERROR_INSUFFICIENT_BUFFER : GetLastError(); code_present = 1;
        goto cleanup;
    }
    if (length < 3 || path[1] != L':' || path[2] != L'\\') {
        status = "load_failed"; stage = "load"; code = ERROR_INVALID_DATA; code_present = 1;
        goto cleanup;
    }
    wcscat(path, L"\\FirewallAPI.dll");
    library = LoadLibraryExW(path, NULL, LOAD_LIBRARY_SEARCH_SYSTEM32);
    if (!library) {
        status = "load_failed"; stage = "load"; code = GetLastError(); code_present = 1;
        goto cleanup;
    }
    library_release = "unknown";
    query = (PositiveLoopbackGetConfigFn)GetProcAddress(library, "NetworkIsolationGetAppContainerConfig");
    if (!query) {
        status = "unsupported"; stage = "export"; code = GetLastError(); code_present = 1;
        goto cleanup;
    }
    derived = DeriveAppContainerSidFromAppContainerName(profile, &target);
    stage = "derive"; code = (DWORD)derived; code_present = 1;
    if (target) target_release = "unknown";
    if (derived != S_OK) {
        status = "api_error";
        /* Failed derivation does not establish a safe owned SID. */
        goto cleanup;
    }
    if (!target || !IsValidSid(target)) {
        status = "invalid_data"; stage = "validate"; code = ERROR_INVALID_DATA;
        goto cleanup;
    }
    target_release = "confirmed"; /* Acquired and validated; actually freed below. */
    stage = "query"; code = query(&count, &entries); code_present = 1;
    if (entries) array_release = "unknown";
    if (code != ERROR_SUCCESS) {
        status = "api_error"; ownership_safe = 0;
        goto cleanup;
    }
    if (count > 4096) {
        status = "limit_reached"; ownership_safe = 0;
        goto cleanup;
    }
    count_present = 1;
    if (count && !entries) {
        status = "invalid_data"; stage = "validate"; code = ERROR_INVALID_DATA;
        goto cleanup;
    }
    if ((void *)entries == (void *)target && entries) {
        status = "invalid_data"; stage = "validate"; code = ERROR_INVALID_DATA;
        ownership_safe = 0; target_alias = 1;
        goto cleanup;
    }
    /* Validate the complete bounded ownership graph before comparisons/frees. */
    for (index = 0; index < count; ++index) {
        pointers[index] = entries[index].Sid;
        if (!pointers[index] || (void *)pointers[index] == (void *)entries ||
            pointers[index] == target) {
            if (pointers[index] == target) target_alias = 1;
            status = "invalid_data"; stage = "validate"; code = ERROR_INVALID_DATA;
            ownership_safe = 0;
            goto cleanup;
        }
        for (previous = 0; previous < index; ++previous) {
            if (pointers[index] == pointers[previous]) {
                status = "invalid_data"; stage = "validate"; code = ERROR_INVALID_DATA;
                ownership_safe = 0;
                goto cleanup;
            }
        }
        if (!IsValidSid(pointers[index])) {
            status = "invalid_data"; stage = "validate"; code = ERROR_INVALID_DATA;
            ownership_safe = 0;
            goto cleanup;
        }
    }
    for (index = 0; index < count; ++index) {
        if (EqualSid(target, pointers[index])) {
            targets++;
            attributes = entries[index].Attributes;
        }
    }
    if (targets > 1) {
        status = "invalid_data"; stage = "validate"; code = ERROR_INVALID_DATA;
    } else match = targets == 1;

cleanup:
    if (entries && ownership_safe) {
        for (index = 0; index < count; ++index) {
            attempted++;
            if (HeapFree(GetProcessHeap(), 0, pointers[index])) confirmed++;
        }
        array_release = HeapFree(GetProcessHeap(), 0, entries) ? "confirmed" : "failed";
    }
    if (target_alias) target_release = "unknown";
    if (target && !target_alias && strcmp(target_release, "confirmed") == 0)
        target_release = FreeSid(target) == NULL ? "confirmed" : "failed";
    if (library) library_release = FreeLibrary(library) ? "confirmed" : "failed";
    if (strcmp(status, "complete") || attempted != confirmed ||
        strcmp(array_release, "failed") == 0 || strcmp(array_release, "unknown") == 0 ||
        strcmp(target_release, "confirmed") ||
        strcmp(library_release, "confirmed"))
        match = -1;
    {
        char code_text[16], count_text[16], attributes_text[16];
        if (code_present) (void)snprintf(code_text, sizeof(code_text), "%lu", (unsigned long)code);
        else strcpy(code_text, "null");
        if (count_present) (void)snprintf(count_text, sizeof(count_text), "%lu", (unsigned long)count);
        else strcpy(count_text, "null");
        if (match == 1) (void)snprintf(attributes_text, sizeof(attributes_text), "%lu", (unsigned long)attributes);
        else strcpy(attributes_text, "null");
        printf("{\"schema_version\":1,\"scope\":\"positive_loopback_config_sample\","
            "\"status\":\"%s\",\"api_stage\":\"%s\",\"api_code\":%s,\"entry_count\":%s,"
            "\"target_match\":%s,\"target_attributes\":%s,"
            "\"sid_frees_attempted\":%u,\"sid_frees_confirmed\":%u,"
            "\"array_release\":\"%s\",\"derived_sid_release\":\"%s\",\"library_release\":\"%s\"}\n",
            status, stage, code_text, count_text, match < 0 ? "null" : match ? "true" : "false",
            attributes_text, attempted, confirmed, array_release, target_release, library_release);
    }
    return 0;
}
