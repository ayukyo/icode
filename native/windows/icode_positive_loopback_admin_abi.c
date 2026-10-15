#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

_Static_assert(sizeof(DWORD) == 4, "DWORD");
_Static_assert(sizeof(BOOL) == 4, "BOOL");
_Static_assert(sizeof(FILETIME) == 8, "FILETIME");
_Static_assert(sizeof(ULONG_PTR) == sizeof(void *), "ULONG_PTR");

typedef BOOL (WINAPI *ProcessTimesFn)(HANDLE, LPFILETIME, LPFILETIME,
                                    LPFILETIME, LPFILETIME);

int main(int argc, char **argv) {
    ProcessTimesFn process_times = GetProcessTimes;
    FILETIME created, exited, kernel, user;
    BOOL call_ok;
    HANDLE heap;
    void *owned;
    BOOL freed;
    const char *machine;
    (void)argv;
    if (argc != 1) return 2;
#if defined(_M_ARM64)
    machine = "ARM64";
#elif defined(_M_X64)
    machine = "x64";
#else
#error Unsupported CI probe architecture
#endif
    call_ok = process_times(GetCurrentProcess(), &created, &exited, &kernel, &user);
    heap = GetProcessHeap();
    owned = heap ? HeapAlloc(heap, 0, 64) : NULL;
    freed = owned ? HeapFree(heap, 0, owned) : FALSE;
    if (!call_ok || !freed) return 3;
    printf("{\"schema\":1,\"machine\":\"%s\",\"DWORD\":%zu,\"BOOL\":%zu,"
           "\"FILETIME\":%zu,\"HANDLE\":%zu,\"SA\":%zu,\"FILE_INFO\":%zu,"
           "\"STARTUP\":%zu,\"STARTUP_EX\":%zu,\"PROCESS\":%zu,"
           "\"TOKEN_USER\":%zu,\"GENERIC_MAPPING\":%zu,\"EXTENDED_LIMITS\":%zu,"
           "\"sa_descriptor\":%zu,\"file_volume\":%zu,\"file_links\":%zu,"
           "\"startup_stdin\":%zu,\"startup_attributes\":%zu,\"process_pid\":%zu,"
           "\"token_sid\":%zu,\"job_pid_list\":%zu,\"job_list_attribute\":%llu,"
           "\"calling_convention_verified\":true,\"owned_buffer_freed\":true,\"layout\":{",
           machine, sizeof(DWORD), sizeof(BOOL), sizeof(FILETIME), sizeof(HANDLE),
           sizeof(SECURITY_ATTRIBUTES), sizeof(BY_HANDLE_FILE_INFORMATION),
           sizeof(STARTUPINFOW), sizeof(STARTUPINFOEXW), sizeof(PROCESS_INFORMATION),
           sizeof(TOKEN_USER), sizeof(GENERIC_MAPPING), sizeof(JOBOBJECT_EXTENDED_LIMIT_INFORMATION),
           offsetof(SECURITY_ATTRIBUTES, lpSecurityDescriptor),
           offsetof(BY_HANDLE_FILE_INFORMATION, dwVolumeSerialNumber),
           offsetof(BY_HANDLE_FILE_INFORMATION, nNumberOfLinks),
           offsetof(STARTUPINFOW, hStdInput),
           offsetof(STARTUPINFOEXW, lpAttributeList),
           offsetof(PROCESS_INFORMATION, dwProcessId),
           offsetof(TOKEN_USER, User),
           offsetof(JOBOBJECT_BASIC_PROCESS_ID_LIST, ProcessIdList),
           (unsigned long long)PROC_THREAD_ATTRIBUTE_JOB_LIST);
    /* Independent SDK oracle. Keys match every consumed Python field. */
#define S(key, type) printf("\"" key "\":%zu,", sizeof(type))
#define O(key, type, field) printf("\"" key "\":%zu,", offsetof(type, field))
    S("WORD", WORD); S("LONG", LONG); S("ULONG_PTR", ULONG_PTR);
    S("IO", IO_COUNTERS); S("LIMITS", JOBOBJECT_BASIC_LIMIT_INFORMATION);
    S("SID_AND_ATTRIBUTES", SID_AND_ATTRIBUTES);
    O("FILETIME.dwLowDateTime", FILETIME, dwLowDateTime);
    O("FILETIME.dwHighDateTime", FILETIME, dwHighDateTime);
    O("SA.length", SECURITY_ATTRIBUTES, nLength);
    O("SA.descriptor", SECURITY_ATTRIBUTES, lpSecurityDescriptor);
    O("SA.inherit", SECURITY_ATTRIBUTES, bInheritHandle);
    O("FILE_INFO.attributes", BY_HANDLE_FILE_INFORMATION, dwFileAttributes);
    O("FILE_INFO.created", BY_HANDLE_FILE_INFORMATION, ftCreationTime);
    O("FILE_INFO.accessed", BY_HANDLE_FILE_INFORMATION, ftLastAccessTime);
    O("FILE_INFO.written", BY_HANDLE_FILE_INFORMATION, ftLastWriteTime);
    O("FILE_INFO.volume", BY_HANDLE_FILE_INFORMATION, dwVolumeSerialNumber);
    O("FILE_INFO.size_high", BY_HANDLE_FILE_INFORMATION, nFileSizeHigh);
    O("FILE_INFO.size_low", BY_HANDLE_FILE_INFORMATION, nFileSizeLow);
    O("FILE_INFO.links", BY_HANDLE_FILE_INFORMATION, nNumberOfLinks);
    O("FILE_INFO.index_high", BY_HANDLE_FILE_INFORMATION, nFileIndexHigh);
    O("FILE_INFO.index_low", BY_HANDLE_FILE_INFORMATION, nFileIndexLow);
    O("STARTUP.cb", STARTUPINFOW, cb);
    O("STARTUP.reserved", STARTUPINFOW, lpReserved);
    O("STARTUP.desktop", STARTUPINFOW, lpDesktop);
    O("STARTUP.title", STARTUPINFOW, lpTitle);
    O("STARTUP.x", STARTUPINFOW, dwX); O("STARTUP.y", STARTUPINFOW, dwY);
    O("STARTUP.x_size", STARTUPINFOW, dwXSize);
    O("STARTUP.y_size", STARTUPINFOW, dwYSize);
    O("STARTUP.x_count", STARTUPINFOW, dwXCountChars);
    O("STARTUP.y_count", STARTUPINFOW, dwYCountChars);
    O("STARTUP.fill", STARTUPINFOW, dwFillAttribute);
    O("STARTUP.flags", STARTUPINFOW, dwFlags);
    O("STARTUP.show", STARTUPINFOW, wShowWindow);
    O("STARTUP.reserved_bytes", STARTUPINFOW, cbReserved2);
    O("STARTUP.reserved_pointer", STARTUPINFOW, lpReserved2);
    O("STARTUP.stdin", STARTUPINFOW, hStdInput);
    O("STARTUP.stdout", STARTUPINFOW, hStdOutput);
    O("STARTUP.stderr", STARTUPINFOW, hStdError);
    O("STARTUP_EX.startup", STARTUPINFOEXW, StartupInfo);
    O("STARTUP_EX.attributes", STARTUPINFOEXW, lpAttributeList);
    O("PROCESS.process", PROCESS_INFORMATION, hProcess);
    O("PROCESS.thread", PROCESS_INFORMATION, hThread);
    O("PROCESS.pid", PROCESS_INFORMATION, dwProcessId);
    O("PROCESS.tid", PROCESS_INFORMATION, dwThreadId);
    O("IO.read_ops", IO_COUNTERS, ReadOperationCount);
    O("IO.write_ops", IO_COUNTERS, WriteOperationCount);
    O("IO.other_ops", IO_COUNTERS, OtherOperationCount);
    O("IO.read_bytes", IO_COUNTERS, ReadTransferCount);
    O("IO.write_bytes", IO_COUNTERS, WriteTransferCount);
    O("IO.other_bytes", IO_COUNTERS, OtherTransferCount);
    O("LIMITS.process_time", JOBOBJECT_BASIC_LIMIT_INFORMATION, PerProcessUserTimeLimit);
    O("LIMITS.job_time", JOBOBJECT_BASIC_LIMIT_INFORMATION, PerJobUserTimeLimit);
    O("LIMITS.flags", JOBOBJECT_BASIC_LIMIT_INFORMATION, LimitFlags);
    O("LIMITS.minimum", JOBOBJECT_BASIC_LIMIT_INFORMATION, MinimumWorkingSetSize);
    O("LIMITS.maximum", JOBOBJECT_BASIC_LIMIT_INFORMATION, MaximumWorkingSetSize);
    O("LIMITS.active_limit", JOBOBJECT_BASIC_LIMIT_INFORMATION, ActiveProcessLimit);
    O("LIMITS.affinity", JOBOBJECT_BASIC_LIMIT_INFORMATION, Affinity);
    O("LIMITS.priority", JOBOBJECT_BASIC_LIMIT_INFORMATION, PriorityClass);
    O("LIMITS.scheduling", JOBOBJECT_BASIC_LIMIT_INFORMATION, SchedulingClass);
    O("EXTENDED_LIMITS.basic", JOBOBJECT_EXTENDED_LIMIT_INFORMATION, BasicLimitInformation);
    O("EXTENDED_LIMITS.io", JOBOBJECT_EXTENDED_LIMIT_INFORMATION, IoInfo);
    O("EXTENDED_LIMITS.process_memory", JOBOBJECT_EXTENDED_LIMIT_INFORMATION, ProcessMemoryLimit);
    O("EXTENDED_LIMITS.job_memory", JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JobMemoryLimit);
    O("EXTENDED_LIMITS.peak_process", JOBOBJECT_EXTENDED_LIMIT_INFORMATION, PeakProcessMemoryUsed);
    O("EXTENDED_LIMITS.peak_job", JOBOBJECT_EXTENDED_LIMIT_INFORMATION, PeakJobMemoryUsed);
    O("SID_AND_ATTRIBUTES.Sid", SID_AND_ATTRIBUTES, Sid);
    O("SID_AND_ATTRIBUTES.Attributes", SID_AND_ATTRIBUTES, Attributes);
    O("TOKEN_USER.sid", TOKEN_USER, User.Sid);
    O("TOKEN_USER.attributes", TOKEN_USER, User.Attributes);
    O("GENERIC_MAPPING.read", GENERIC_MAPPING, GenericRead);
    O("GENERIC_MAPPING.write", GENERIC_MAPPING, GenericWrite);
    O("GENERIC_MAPPING.execute", GENERIC_MAPPING, GenericExecute);
    O("GENERIC_MAPPING.all", GENERIC_MAPPING, GenericAll);
    O("JOB_PID.assigned", JOBOBJECT_BASIC_PROCESS_ID_LIST, NumberOfAssignedProcesses);
    O("JOB_PID.count", JOBOBJECT_BASIC_PROCESS_ID_LIST, NumberOfProcessIdsInList);
    printf("\"JOB_PID.pids\":%zu}}\n",
           offsetof(JOBOBJECT_BASIC_PROCESS_ID_LIST, ProcessIdList));
#undef O
#undef S
    return 0;
}
