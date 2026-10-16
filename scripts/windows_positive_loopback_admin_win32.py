from __future__ import annotations

import ctypes as c
from ctypes import wintypes as t
from pathlib import Path
import os
import struct
import sys


class Failure(RuntimeError):
    pass


class SA(c.Structure):
    _fields_ = [("length", t.DWORD), ("descriptor", c.c_void_p), ("inherit", t.BOOL)]


class FILE_INFO(c.Structure):
    _fields_ = [("attributes", t.DWORD), ("created", t.FILETIME),
                ("accessed", t.FILETIME), ("written", t.FILETIME),
                ("volume", t.DWORD), ("size_high", t.DWORD), ("size_low", t.DWORD),
                ("links", t.DWORD), ("index_high", t.DWORD), ("index_low", t.DWORD)]


class STARTUP(c.Structure):
    _fields_ = [("cb", t.DWORD), ("reserved", t.LPWSTR), ("desktop", t.LPWSTR),
                ("title", t.LPWSTR), ("x", t.DWORD), ("y", t.DWORD),
                ("x_size", t.DWORD), ("y_size", t.DWORD), ("x_count", t.DWORD),
                ("y_count", t.DWORD), ("fill", t.DWORD), ("flags", t.DWORD),
                ("show", t.WORD), ("reserved_bytes", t.WORD),
                ("reserved_pointer", c.c_void_p), ("stdin", t.HANDLE),
                ("stdout", t.HANDLE), ("stderr", t.HANDLE)]


class STARTUP_EX(c.Structure):
    _fields_ = [("startup", STARTUP), ("attributes", c.c_void_p)]


class PROCESS(c.Structure):
    _fields_ = [("process", t.HANDLE), ("thread", t.HANDLE),
                ("pid", t.DWORD), ("tid", t.DWORD)]


class IO(c.Structure):
    _fields_ = [(name, c.c_ulonglong) for name in (
        "read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]


class LIMITS(c.Structure):
    _fields_ = [("process_time", c.c_longlong), ("job_time", c.c_longlong),
                ("flags", t.DWORD), ("minimum", c.c_size_t), ("maximum", c.c_size_t),
                ("active_limit", t.DWORD), ("affinity", c.c_size_t),
                ("priority", t.DWORD), ("scheduling", t.DWORD)]


class EXTENDED_LIMITS(c.Structure):
    _fields_ = [("basic", LIMITS), ("io", IO), ("process_memory", c.c_size_t),
                ("job_memory", c.c_size_t), ("peak_process", c.c_size_t),
                ("peak_job", c.c_size_t)]


class TOKEN_USER(c.Structure):
    _fields_ = [("sid", c.c_void_p), ("attributes", t.DWORD)]


class GENERIC_MAPPING(c.Structure):
    _fields_ = [("read", t.DWORD), ("write", t.DWORD),
                ("execute", t.DWORD), ("all", t.DWORD)]


def checked(value, stage):
    if not value:
        raise Failure(stage)
    return value


def _dacl_failure(category, actual, wanted):
    """Bounded DACL mismatch; the observed ACL byte length is the only number."""
    failure = Failure(category if len(actual) == len(wanted) else category + "_dacl_length")
    failure.winerror = len(actual)
    return failure


def _release_owned(primary, *actions):
    """Attempt each owned release; never replace an active body exception."""
    errors = []
    for action in actions:
        try:
            action()
        except BaseException as error:
            errors.append(error)
    if errors:
        failure = primary if primary is not None else errors[0]
        for error in errors:
            failure.add_note(f"cleanup_unknown: {error!r}")
        if primary is None:
            raise failure


class Win32:
    def __init__(self):
        if sys.platform != "win32" or sys.version_info < (3, 12):
            raise Failure("unsupported_host")
        self.k = c.WinDLL("kernel32", use_last_error=True)
        self.k.GetSystemDirectoryW.restype = t.UINT
        self.k.GetSystemDirectoryW.argtypes = [t.LPWSTR, t.UINT]
        system = c.create_unicode_buffer(32768)
        length = self.k.GetSystemDirectoryW(system, len(system))
        if not 0 < length < len(system) or Path(system.value).name.casefold() != "system32":
            raise Failure("system_directory")
        self.system_directory = Path(system.value)
        self.a = c.WinDLL(str(self.system_directory / "advapi32.dll"), use_last_error=True, winmode=0x800)
        self.u = c.WinDLL(str(self.system_directory / "userenv.dll"), use_last_error=True, winmode=0x800)
        specs = {
            "k": {
                "CloseHandle": (t.BOOL, [t.HANDLE]),
                "LocalFree": (c.c_void_p, [c.c_void_p]),
                "GetCurrentProcess": (t.HANDLE, []),
                "GetCurrentProcessId": (t.DWORD, []),
                "GetModuleHandleW": (t.HANDLE, [t.LPCWSTR]),
                "GetModuleFileNameW": (t.DWORD, [t.HANDLE, t.LPWSTR, t.DWORD]),
                "K32EnumProcessModules": (t.BOOL, [t.HANDLE, c.POINTER(t.HANDLE), t.DWORD, c.POINTER(t.DWORD)]),
                "GetFileAttributesW": (t.DWORD, [t.LPCWSTR]),
                "SetFileAttributesW": (t.BOOL, [t.LPCWSTR, t.DWORD]),
                "MoveFileExW": (t.BOOL, [t.LPCWSTR, t.LPCWSTR, t.DWORD]),
                "GetSystemDirectoryW": (t.UINT, [t.LPWSTR, t.UINT]),
                "GetTempPathW": (t.DWORD, [t.DWORD, t.LPWSTR]),
                "CreateDirectoryW": (t.BOOL, [t.LPCWSTR, c.POINTER(SA)]),
                "CreateFileW": (t.HANDLE, [t.LPCWSTR, t.DWORD, t.DWORD, c.POINTER(SA), t.DWORD, t.DWORD, t.HANDLE]),
                "GetFileInformationByHandle": (t.BOOL, [t.HANDLE, c.POINTER(FILE_INFO)]),
                "GetFinalPathNameByHandleW": (t.DWORD, [t.HANDLE, t.LPWSTR, t.DWORD, t.DWORD]),
                "ReadFile": (t.BOOL, [t.HANDLE, c.c_void_p, t.DWORD, c.POINTER(t.DWORD), c.c_void_p]),
                "WriteFile": (t.BOOL, [t.HANDLE, c.c_void_p, t.DWORD, c.POINTER(t.DWORD), c.c_void_p]),
                "SetFilePointerEx": (t.BOOL, [t.HANDLE, c.c_longlong, c.POINTER(c.c_longlong), t.DWORD]),
                "SetEndOfFile": (t.BOOL, [t.HANDLE]),
                "FlushFileBuffers": (t.BOOL, [t.HANDLE]),
                "CreateJobObjectW": (t.HANDLE, [c.POINTER(SA), t.LPCWSTR]),
                "OpenJobObjectW": (t.HANDLE, [t.DWORD, t.BOOL, t.LPCWSTR]),
                "SetInformationJobObject": (t.BOOL, [t.HANDLE, c.c_int, c.c_void_p, t.DWORD]),
                "QueryInformationJobObject": (t.BOOL, [t.HANDLE, c.c_int, c.c_void_p, t.DWORD, c.POINTER(t.DWORD)]),
                "AssignProcessToJobObject": (t.BOOL, [t.HANDLE, t.HANDLE]),
                "IsProcessInJob": (t.BOOL, [t.HANDLE, t.HANDLE, c.POINTER(t.BOOL)]),
                "TerminateJobObject": (t.BOOL, [t.HANDLE, t.UINT]),
                "TerminateProcess": (t.BOOL, [t.HANDLE, t.UINT]),
                "OpenProcess": (t.HANDLE, [t.DWORD, t.BOOL, t.DWORD]),
                "GetProcessTimes": (t.BOOL, [t.HANDLE, c.POINTER(t.FILETIME), c.POINTER(t.FILETIME), c.POINTER(t.FILETIME), c.POINTER(t.FILETIME)]),
                "GetExitCodeProcess": (t.BOOL, [t.HANDLE, c.POINTER(t.DWORD)]),
                "WaitForSingleObject": (t.DWORD, [t.HANDLE, t.DWORD]),
                "ResumeThread": (t.DWORD, [t.HANDLE]),
                "CreateProcessW": (t.BOOL, [t.LPCWSTR, t.LPWSTR, c.c_void_p, c.c_void_p, t.BOOL, t.DWORD, c.c_void_p, t.LPCWSTR, c.POINTER(STARTUP_EX), c.POINTER(PROCESS)]),
                "InitializeProcThreadAttributeList": (t.BOOL, [c.c_void_p, t.DWORD, t.DWORD, c.POINTER(c.c_size_t)]),
                "UpdateProcThreadAttribute": (t.BOOL, [c.c_void_p, t.DWORD, c.c_size_t, c.c_void_p, c.c_size_t, c.c_void_p, c.POINTER(c.c_size_t)]),
                "DeleteProcThreadAttributeList": (None, [c.c_void_p]),
            },
            "a": {
                "ConvertStringSidToSidW": (t.BOOL, [t.LPCWSTR, c.POINTER(c.c_void_p)]),
                "CheckTokenMembership": (t.BOOL, [t.HANDLE, c.c_void_p, c.POINTER(t.BOOL)]),
                "ConvertStringSecurityDescriptorToSecurityDescriptorW": (t.BOOL, [t.LPCWSTR, t.DWORD, c.POINTER(c.c_void_p), c.POINTER(t.DWORD)]),
                "GetSecurityInfo": (t.DWORD, [t.HANDLE, c.c_int, t.DWORD, c.POINTER(c.c_void_p), c.POINTER(c.c_void_p), c.POINTER(c.c_void_p), c.POINTER(c.c_void_p), c.POINTER(c.c_void_p)]),
                "SetSecurityInfo": (t.DWORD, [t.HANDLE, c.c_int, t.DWORD, c.c_void_p, c.c_void_p, c.c_void_p, c.c_void_p]),
                "GetSecurityDescriptorDacl": (t.BOOL, [c.c_void_p, c.POINTER(t.BOOL), c.POINTER(c.c_void_p), c.POINTER(t.BOOL)]),
                "GetSecurityDescriptorOwner": (t.BOOL, [c.c_void_p, c.POINTER(c.c_void_p), c.POINTER(t.BOOL)]),
                "GetSecurityDescriptorControl": (t.BOOL, [c.c_void_p, c.POINTER(t.WORD), c.POINTER(t.DWORD)]),
                "IsValidSid": (t.BOOL, [c.c_void_p]),
                "GetLengthSid": (t.DWORD, [c.c_void_p]),
                "ConvertSidToStringSidW": (t.BOOL, [c.c_void_p, c.POINTER(t.LPWSTR)]),
                "FreeSid": (c.c_void_p, [c.c_void_p]),
                "OpenProcessToken": (t.BOOL, [t.HANDLE, t.DWORD, c.POINTER(t.HANDLE)]),
                "GetTokenInformation": (t.BOOL, [t.HANDLE, c.c_int, c.c_void_p, t.DWORD, c.POINTER(t.DWORD)]),
                "DuplicateToken": (t.BOOL, [t.HANDLE, c.c_int, c.POINTER(t.HANDLE)]),
                "ImpersonateLoggedOnUser": (t.BOOL, [t.HANDLE]),
                "RevertToSelf": (t.BOOL, []),
                "LookupAccountNameW": (t.BOOL, [t.LPCWSTR, t.LPCWSTR, c.c_void_p, c.POINTER(t.DWORD), t.LPWSTR, c.POINTER(t.DWORD), c.POINTER(t.DWORD)]),
                "LookupAccountSidW": (t.BOOL, [t.LPCWSTR, c.c_void_p, t.LPWSTR, c.POINTER(t.DWORD), t.LPWSTR, c.POINTER(t.DWORD), c.POINTER(t.DWORD)]),
                "AccessCheck": (t.BOOL, [c.c_void_p, t.HANDLE, t.DWORD, c.POINTER(GENERIC_MAPPING), c.c_void_p, c.POINTER(t.DWORD), c.POINTER(t.DWORD), c.POINTER(t.BOOL)]),
            },
            "u": {"DeriveAppContainerSidFromAppContainerName": (c.c_long, [t.LPCWSTR, c.POINTER(c.c_void_p)])},
        }
        for module, names in specs.items():
            for name, (result, arguments) in names.items():
                function = getattr(getattr(self, module), name)
                function.restype, function.argtypes = result, arguments

    def close(self, handle):
        if handle:
            checked(self.k.CloseHandle(handle), "close_handle")

    def descriptor(self, text):
        pointer = c.c_void_p()
        checked(self.a.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            text, 1, c.byref(pointer), None), "descriptor")
        return pointer

    def security(self, descriptor):
        present, defaulted, owner_defaulted = t.BOOL(), t.BOOL(), t.BOOL()
        dacl, owner = c.c_void_p(), c.c_void_p()
        control, revision = t.WORD(), t.DWORD()
        checked(self.a.GetSecurityDescriptorDacl(descriptor, c.byref(present), c.byref(dacl), c.byref(defaulted)), "descriptor_dacl")
        checked(self.a.GetSecurityDescriptorOwner(descriptor, c.byref(owner), c.byref(owner_defaulted)), "descriptor_owner")
        checked(self.a.GetSecurityDescriptorControl(descriptor, c.byref(control), c.byref(revision)), "descriptor_control")
        if not present.value or defaulted.value or not dacl.value or not owner.value:
            raise Failure("descriptor_shape")
        size = struct.unpack("<BBHHH", c.string_at(dacl, 8))[2]
        if size < 8 or not self.a.IsValidSid(owner):
            raise Failure("descriptor_shape")
        return c.string_at(owner, self.a.GetLengthSid(owner)), c.string_at(dacl, size), bool(control.value & 0x1000)

    def verify_security(self, handle, expected_sddl, *, object_type=1,
                    category="security_changed", owner=True):
        descriptor, expected = c.c_void_p(), self.descriptor(expected_sddl)
        try:
            if self.a.GetSecurityInfo(handle, object_type, 5, None, None, None, None, c.byref(descriptor)) != 0:
                raise Failure("get_security")
            actual, wanted = self.security(descriptor), self.security(expected)
            if owner and actual[0] != wanted[0]:
                raise Failure(category + "_owner")
            if actual[1] != wanted[1]:
                raise _dacl_failure(category, actual[1], wanted[1])
            if not actual[2]:
                raise Failure(category + "_unprotected")
        finally:
            _release_owned(sys.exception(),
                *(lambda pointer=pointer: checked(not self.k.LocalFree(pointer), "free_descriptor") for pointer in (descriptor, expected) if pointer.value),
            )

    def info(self, handle, *, directory=False):
        info = FILE_INFO()
        checked(self.k.GetFileInformationByHandle(handle, c.byref(info)), "file_information")
        if bool(info.attributes & 0x10) != directory or info.attributes & 0x400 or (not directory and info.links != 1):
            raise Failure("file_shape")
        return (int(info.volume), (int(info.index_high) << 32) | int(info.index_low))

    def open_file(self, path, sddl, *, create=False, write=False, directory=False, inherit=False):
        descriptor = self.descriptor(sddl)
        handle = None
        transferred = False
        try:
            attributes = SA(c.sizeof(SA), descriptor, inherit)
            access = 0x00020080 | (0 if directory else 0x80000000) | (0x40000000 if write else 0)
            if directory and write:
                access |= 0x00040000
            handle = self.k.CreateFileW(str(path), access, 3 if directory else 1,
                c.byref(attributes), 1 if create else 3,
                0x00200000 | (0x02000000 if directory else 0), None)
            if handle in (None, c.c_void_p(-1).value):
                handle = None
                raise Failure("open_file", c.get_last_error())
            identity = self.info(handle, directory=directory)
            if not identity[1]:
                raise Failure("file_identity")
            self.verify_security(handle, sddl, category="create_directory_security_changed")
            final = c.create_unicode_buffer(32768)
            length = self.k.GetFinalPathNameByHandleW(handle, final, len(final), 0)
            checked(0 < length < len(final), "final_path")
            observed = final.value[4:] if final.value.startswith("\\\\?\\") else final.value
            if os.path.normcase(observed) != os.path.normcase(str(path)):
                raise Failure("file_namespace")
            # Transfer only after descriptor cleanup succeeds. A failure in a
            # return's finally must not strand a handle the caller never got.
            allocation, descriptor = descriptor, None
            _release_owned(None, lambda: checked(not self.k.LocalFree(allocation), "free_descriptor"))
            result = (handle, identity)
            transferred = True
            return result
        finally:
            _release_owned(sys.exception(),
                lambda: checked(not self.k.LocalFree(descriptor), "free_descriptor") if descriptor is not None else None,
                lambda: self.close(handle) if handle and not transferred else None,
            )

    def create_directory(self, path, sddl):
        descriptor = self.descriptor(sddl)
        try:
            attributes = SA(c.sizeof(SA), descriptor, False)
            checked(self.k.CreateDirectoryW(str(path), c.byref(attributes)), "create_directory")
        finally:
            _release_owned(sys.exception(),
                lambda: checked(not self.k.LocalFree(descriptor), 'free_descriptor'),
            )

    def set_root_dacl(self, handle, old_sddl, new_sddl):
        self.verify_security(handle, old_sddl, category="root_dacl_security_changed")
        descriptor = self.descriptor(new_sddl)
        try:
            dacl, present, defaulted = c.c_void_p(), t.BOOL(), t.BOOL()
            checked(self.a.GetSecurityDescriptorDacl(descriptor, c.byref(present), c.byref(dacl), c.byref(defaulted)), "root_dacl")
            if not present.value or defaulted.value or not dacl.value:
                raise Failure("root_dacl")
            if self.a.SetSecurityInfo(handle, 1, 0x80000004, None, None, dacl, None) != 0:
                raise Failure("root_dacl")
            self.verify_security(handle, new_sddl, category="root_dacl_security_changed")
        finally:
            _release_owned(sys.exception(),
                lambda: checked(not self.k.LocalFree(descriptor), 'free_descriptor'),
            )

    def pin_ancestor(self, path, *, observe_only=False):
        handle = self.k.CreateFileW(str(path), 0x00020080, 3, None, 3,
                                    0x02200000, None)
        if handle in (None, c.c_void_p(-1).value):
            raise Failure("pin_ancestor")
        try:
            self.info(handle, directory=True)
            if not observe_only:
                self.verify_ancestor(handle)
            return handle
        except BaseException:
            _release_owned(sys.exception(), lambda: self.close(handle))
            raise

    def read(self, handle, limit):
        checked(self.k.SetFilePointerEx(handle, 0, None, 0), "seek")
        data, count = c.create_string_buffer(limit + 1), t.DWORD()
        checked(self.k.ReadFile(handle, data, limit + 1, c.byref(count), None), "read")
        if count.value > limit:
            raise Failure("file_limit")
        return data.raw[:count.value]

    def write(self, handle, data):
        checked(self.k.SetFilePointerEx(handle, 0, None, 0), "seek")
        buffer, count = c.create_string_buffer(data), t.DWORD()
        checked(self.k.WriteFile(handle, buffer, len(data), c.byref(count), None), "write")
        if count.value != len(data):
            raise Failure("short_write")
        checked(self.k.SetEndOfFile(handle), "truncate")
        checked(self.k.FlushFileBuffers(handle), "flush")

    def process_created(self, handle):
        values = [t.FILETIME() for _ in range(4)]
        checked(self.k.GetProcessTimes(handle, *[c.byref(value) for value in values]), "process_times")
        return (int(values[0].dwHighDateTime) << 32) | int(values[0].dwLowDateTime)

    def sid_binary(self, text):
        pointer = c.c_void_p()
        checked(self.a.ConvertStringSidToSidW(text, c.byref(pointer)), "sid_parse")
        try:
            checked(self.a.IsValidSid(pointer), "sid_parse")
            return c.string_at(pointer, self.a.GetLengthSid(pointer))
        finally:
            _release_owned(sys.exception(),
                lambda: checked(not self.k.LocalFree(pointer), 'sid_free'),
            )

    def assert_admin(self):
        pointer, member = c.c_void_p(), t.BOOL()
        checked(self.a.ConvertStringSidToSidW("S-1-5-32-544", c.byref(pointer)), "admin_sid")
        try:
            checked(self.a.CheckTokenMembership(None, pointer, c.byref(member)), "admin_token")
            if not member.value:
                raise Failure("admin_token")
        finally:
            _release_owned(sys.exception(),
                lambda: checked(not self.k.LocalFree(pointer), 'sid_free'),
            )

    def verify_ancestor(self, handle):
        descriptor = c.c_void_p()
        if self.a.GetSecurityInfo(handle, 1, 5, None, None, None, None, c.byref(descriptor)) != 0:
            raise Failure("ancestor_security")
        try:
            owner, acl, _protected = self.security(descriptor)
            trusted = {self.sid_binary("S-1-5-32-544"), self.sid_binary("S-1-5-18"),
                       self.sid_binary(self.process_user(self.k.GetCurrentProcess()))}
            if owner not in trusted:
                raise Failure("ancestor_owner")
            count, offset = struct.unpack("<BBHHH", acl[:8])[3], 8
            for _ in range(count):
                if offset + 4 > len(acl):
                    raise Failure("ancestor_acl")
                kind, flags, size = struct.unpack("<BBH", acl[offset:offset + 4])
                if size < 4 or offset + size > len(acl):
                    raise Failure("ancestor_acl")
                if not flags & 8 and kind != 1:
                    if kind != 0 or size < 20:
                        raise Failure("ancestor_acl")
                    mask = struct.unpack("<I", acl[offset + 4:offset + 8])[0]
                    identity = acl[offset + 8:offset + size]
                    if mask & 0x500D0156 and identity not in trusted:
                        raise Failure("ancestor_writable")
                offset += size
            if offset > len(acl):
                raise Failure("ancestor_acl")
        finally:
            _release_owned(sys.exception(),
                lambda: checked(not self.k.LocalFree(descriptor), 'free_descriptor') if descriptor.value else None,
            )

    def observe_security(self, handle):
        descriptor = c.c_void_p()
        if self.a.GetSecurityInfo(handle, 1, 5, None, None, None, None, c.byref(descriptor)) != 0:
            raise Failure("observe_security")
        try:
            owner, acl, protected = self.security(descriptor)
            return dict(owner_binary=owner.hex(), dacl_binary=acl.hex(), protected=protected)
        finally:
            _release_owned(sys.exception(),
                lambda: checked(not self.k.LocalFree(descriptor), 'free_descriptor') if descriptor.value else None,
            )

    def effective_access(self, handle, parent_process):
        descriptor, token, impersonation = c.c_void_p(), t.HANDLE(), t.HANDLE()
        try:
            if self.a.GetSecurityInfo(handle, 1, 7, None, None, None, None, c.byref(descriptor)) != 0:
                raise Failure("access_descriptor")
            checked(self.a.OpenProcessToken(parent_process, 10, c.byref(token)), "access_token")
            checked(self.a.DuplicateToken(token, 2, c.byref(impersonation)), "access_impersonation")
            mapping = GENERIC_MAPPING(0x120089, 0x120116, 0x1200A0, 0x1F01FF)
            privileges = c.create_string_buffer(16384)
            size, granted, allowed = t.DWORD(len(privileges)), t.DWORD(), t.BOOL()
            checked(self.a.AccessCheck(descriptor, impersonation, 0x02000000,
                c.byref(mapping), privileges, c.byref(size), c.byref(granted),
                c.byref(allowed)), "effective_access")
            if size.value > len(privileges) or not 0 <= granted.value <= 0xFFFFFFFF:
                raise Failure("effective_access_incomplete")
            return dict(api_completed=True, access_status=bool(allowed.value),
                        granted=int(granted.value), privilege_bytes=int(size.value))
        finally:
            _release_owned(sys.exception(),
                *(lambda owned=owned: self.close(owned) for owned in (impersonation, token) if owned),
                lambda: checked(not self.k.LocalFree(descriptor), "free_descriptor") if descriptor.value else None,
            )

    def process_user(self, process):
        token, needed = t.HANDLE(), t.DWORD()
        checked(self.a.OpenProcessToken(process, 8, c.byref(token)), "process_token")
        try:
            self.a.GetTokenInformation(token, 1, None, 0, c.byref(needed))
            if not 0 < needed.value <= 4096:
                raise Failure("token_size")
            buffer = c.create_string_buffer(needed.value)
            checked(self.a.GetTokenInformation(token, 1, buffer, len(buffer), c.byref(needed)), "token_user")
            if not c.sizeof(TOKEN_USER) <= needed.value <= len(buffer):
                raise Failure("token_size")
            sid = c.cast(buffer, c.POINTER(TOKEN_USER)).contents.sid
            base = c.addressof(buffer)
            if not sid or not base + c.sizeof(TOKEN_USER) <= sid < base + needed.value:
                raise Failure("token_sid")
            checked(self.a.IsValidSid(sid), "token_sid")
            length = int(self.a.GetLengthSid(sid))
            if not 12 <= length <= 68 or sid + length > base + needed.value:
                raise Failure("token_sid")
            text = t.LPWSTR()
            checked(self.a.ConvertSidToStringSidW(sid, c.byref(text)), "sid_text")
            try:
                return text.value
            finally:
                _release_owned(sys.exception(),
                    lambda: checked(not self.k.LocalFree(text), 'free_sid_text'),
                )
        finally:
            _release_owned(sys.exception(),
                lambda: self.close(token),
            )

    def job_pids(self, job):
        # At most 32 fixed-chain members; do not truncate a larger live tree.
        size = 8 + 32 * c.sizeof(c.c_size_t)
        buffer, returned = c.create_string_buffer(size), t.DWORD()
        checked(self.k.QueryInformationJobObject(job, 3, buffer, size, c.byref(returned)), "job_query")
        assigned, listed = struct.unpack("<II", buffer.raw[:8])
        if (assigned != listed or listed > 32 or returned.value > size
                or returned.value < 8 + listed * c.sizeof(c.c_size_t)):
            raise Failure("job_query_incomplete")
        pointer = c.cast(c.byref(buffer, 8), c.POINTER(c.c_size_t))
        result = tuple(int(pointer[index]) for index in range(listed))
        if len(set(result)) != len(result) or any(pid < 1 for pid in result):
            raise Failure("job_query_identity")
        return result
