"""Real Win32 adapter algorithms over synthetic ABI memory; software proof only."""
from __future__ import annotations
import ctypes as c
from ctypes import wintypes as t
import importlib
import struct
from types import SimpleNamespace as N
import unittest

NAME = "scripts.windows_positive_loopback_admin_win32"
try:
    native = importlib.import_module(NAME)
except ModuleNotFoundError as exc:
    if exc.name != NAME: raise
    native = None


def put(pointer, kind, value):
    c.cast(pointer, c.POINTER(kind))[0] = value


class ByteFileOS:
    def __init__(self, initial=b"old trailing data"):
        self.bytes = initial
        self.position = 0
        self.events = []
        self.fail = None
        self.short = False

    def SetFilePointerEx(self, handle, distance, output, method):
        if handle != 90 or distance != 0 or method != 0: raise AssertionError("seek")
        self.events.append("seek"); self.position = 0
        return self.fail != "seek"

    def WriteFile(self, handle, data, length, count, overlap):
        self.events.append("write")
        if handle != 90 or overlap is not None: raise AssertionError("write handle")
        actual = length - 1 if self.short else length
        self.bytes = c.string_at(data, actual) + self.bytes[actual:]
        self.position = actual
        put(count, t.DWORD, actual)
        return self.fail != "write"

    def ReadFile(self, handle, buffer, length, count, overlap):
        self.events.append("read")
        value = self.bytes[:length]
        c.memmove(buffer, value, len(value)); put(count, t.DWORD, len(value))
        return self.fail != "read"

    def SetEndOfFile(self, handle):
        self.events.append("truncate"); self.bytes = self.bytes[:self.position]
        return self.fail != "truncate"

    def FlushFileBuffers(self, handle):
        self.events.append("flush")
        return self.fail != "flush"


class TestAdminWin32(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(native, "new Win32 adapter absent; expected facility RED")
        self.w = native.Win32.__new__(native.Win32)

    def test_write_changes_bytes_truncates_and_flushes_in_order(self):
        model = ByteFileOS(); self.w.k = model
        self.w.write(90, b"new")
        self.assertEqual(model.bytes, b"new")
        self.assertEqual(model.events, ["seek", "write", "truncate", "flush"])

    def test_write_short_or_each_boundary_failure_never_claims_durable_success(self):
        for failure in ("seek", "write", "truncate", "flush", "short"):
            model = ByteFileOS(); self.w.k = model
            model.fail = failure; model.short = failure == "short"
            with self.subTest(failure=failure), self.assertRaises(native.Failure):
                self.w.write(90, b"new")
            if failure in ("seek", "write", "short"):
                self.assertNotIn("flush", model.events)

    def test_read_real_buffer_limit_and_actual_bytes(self):
        for value, limit in ((b"abc", 3), (b"", 0)):
            model = ByteFileOS(value); self.w.k = model
            self.assertEqual(self.w.read(90, limit), value)
        self.w.k = ByteFileOS(b"abcd")
        with self.assertRaises(native.Failure): self.w.read(90, 3)
        model = ByteFileOS(b"abc"); model.fail = "read"; self.w.k = model
        with self.assertRaises(native.Failure): self.w.read(90, 3)

    def job(self, pids, *, assigned=None, listed=None, returned=None, ok=True):
        pids = tuple(pids)
        def query(job, information, output, capacity, size):
            self.assertEqual((job, information), (80, 3))
            header = struct.pack("<II", len(pids) if assigned is None else assigned,
                                 len(pids) if listed is None else listed)
            c.memmove(output, header, 8)
            values = c.cast(c.byref(output, 8), c.POINTER(c.c_size_t))
            for index, pid in enumerate(pids): values[index] = pid
            put(size, t.DWORD, returned if returned is not None else
                8 + len(pids) * c.sizeof(c.c_size_t))
            return ok
        self.w.k = N(QueryInformationJobObject=query)
        return self.w.job_pids(80)

    def test_job_query_real_pid_list_empty_single_nested_and_max(self):
        for values in ((), (1234,), (1234, 4321), tuple(range(1, 33))):
            self.assertEqual(self.job(values), values)

    def test_job_query_incomplete_duplicate_zero_and_api_failure_reject(self):
        cases = [dict(pids=(1234,), assigned=2), dict(pids=(), assigned=33, listed=33),
                 dict(pids=(1234,), returned=8), dict(pids=(1234, 1234)),
                 dict(pids=(0,)), dict(pids=(1234,), ok=False),
                 dict(pids=(1234,), returned=9 + 32*c.sizeof(c.c_size_t))]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(native.Failure): self.job(**case)

    def test_file_info_identity_reparse_hardlink_and_directory_shape(self):
        for attrs, links, directory, accepted in ((0,1,False,True), (0x10,1,True,True),
                (0x400,1,False,False), (0,2,False,False), (0x10,1,False,False),
                (0,1,True,False)):
            def info(handle, output):
                value = c.cast(output, c.POINTER(native.FILE_INFO)).contents
                value.attributes=attrs; value.links=links; value.volume=7
                value.index_high=2; value.index_low=3
                return 1
            self.w.k = N(GetFileInformationByHandle=info)
            if accepted:
                self.assertEqual(self.w.info(90, directory=directory), (7, (2 << 32) | 3))
            else:
                with self.subTest(attrs=attrs, links=links), self.assertRaises(native.Failure):
                    self.w.info(90, directory=directory)

    def test_security_reads_actual_owner_acl_bytes_and_protection_bit(self):
        owner = c.create_string_buffer(bytes((1,1)) + b"\0"*5 + b"\5" + struct.pack("<I",18))
        acl = c.create_string_buffer(struct.pack("<BBHHH",2,0,8,0,0))
        def dacl(descriptor, present, output, defaulted):
            put(present,t.BOOL,1); put(defaulted,t.BOOL,0)
            put(output,c.c_void_p,c.addressof(acl)); return 1
        def owner_fn(descriptor, output, defaulted):
            put(output,c.c_void_p,c.addressof(owner)); put(defaulted,t.BOOL,0); return 1
        def control(descriptor, output, revision):
            put(output,t.WORD,0x1000); put(revision,t.DWORD,1); return 1
        self.w.a = N(GetSecurityDescriptorDacl=dacl, GetSecurityDescriptorOwner=owner_fn,
            GetSecurityDescriptorControl=control, IsValidSid=lambda value: 1,
            GetLengthSid=lambda value: 12)
        self.assertEqual(self.w.security(10), (owner.raw[:12], acl.raw[:8], True))
        self.w.a.IsValidSid = lambda value: 0
        with self.assertRaises(native.Failure): self.w.security(10)

    def test_process_creation_time_uses_full_filetime(self):
        def times(handle, created, exited, kernel, user):
            value = c.cast(created,c.POINTER(t.FILETIME)).contents
            value.dwHighDateTime=0x12345678; value.dwLowDateTime=0xabcdef01
            return 1
        self.w.k=N(GetProcessTimes=times)
        self.assertEqual(self.w.process_created(123), 0x12345678abcdef01)
        self.w.k.GetProcessTimes=lambda *args: 0
        with self.assertRaises(native.Failure): self.w.process_created(123)

    def test_open_file_final_descriptor_free_failure_closes_unreturned_handle(self):
        owner=c.create_string_buffer(bytes((1,1))+b"\0"*5+b"\5"+struct.pack("<I",18))
        acl=c.create_string_buffer(struct.pack("<BBHHH",2,0,8,0,0))
        alive=set();descriptors=set();closed=[];counter=[700]
        def descriptor(text,revision,output,size):
            value=counter[0];counter[0]+=1;descriptors.add(value)
            put(output,c.c_void_p,value);return 1
        def info(handle,output):
            value=c.cast(output,c.POINTER(native.FILE_INFO)).contents
            value.links=1;value.volume=7;value.index_low=90;return 1
        def dacl(pointer,present,output,defaulted):
            put(present,t.BOOL,1);put(defaulted,t.BOOL,0)
            put(output,c.c_void_p,c.addressof(acl));return 1
        def own(pointer,output,defaulted):
            put(defaulted,t.BOOL,0);put(output,c.c_void_p,c.addressof(owner));return 1
        def control(pointer,output,revision):
            put(output,t.WORD,0x1000);put(revision,t.DWORD,1);return 1
        def security(handle,kind,flags,a,b,d,e,output):
            descriptors.add(799);put(output,c.c_void_p,799);return 0
        def create(*args):alive.add(90);return 90
        def final(handle,buffer,size,flags):buffer.value="/model/private.bin";return len(buffer.value)
        def close(handle):
            if handle not in alive:raise AssertionError("unowned/double close")
            alive.remove(handle);closed.append(handle);return 1
        def free(pointer):
            value=pointer.value
            if value not in descriptors:raise AssertionError("unowned/double descriptor free")
            if value==700:return value  # Outer allocation fails only after inner verification succeeds.
            descriptors.remove(value);return 0
        self.w.k=N(CreateFileW=create,GetFileInformationByHandle=info,
            GetFinalPathNameByHandleW=final,CloseHandle=close,LocalFree=free)
        self.w.a=N(ConvertStringSecurityDescriptorToSecurityDescriptorW=descriptor,
            GetSecurityInfo=security,GetSecurityDescriptorDacl=dacl,
            GetSecurityDescriptorOwner=own,GetSecurityDescriptorControl=control,
            IsValidSid=lambda pointer:1,GetLengthSid=lambda pointer:12)
        with self.assertRaises(native.Failure):self.w.open_file("/model/private.bin","private")
        self.assertEqual(alive,set(),"failed return must not strand acquired file handle")
        self.assertEqual(closed,[90])

    def test_process_user_real_token_buffer_sid_bounds_and_release(self):
        for mode in ("ok", "grow", "null", "outside", "invalid", "sid_overflow"):
            closed, freed = [], []
            text = c.create_unicode_buffer("S-1-5-21-1-2-3-1001")
            def open_token(process, access, output):
                self.assertEqual((process,access),(123,8)); put(output,t.HANDLE,321); return 1
            def token_info(token, information, buffer, capacity, needed):
                self.assertEqual((token.value,information),(321,1)); put(needed,t.DWORD,64)
                if buffer is None: return 0
                record = c.cast(buffer,c.POINTER(native.TOKEN_USER)).contents
                address = c.addressof(buffer) + c.sizeof(native.TOKEN_USER)
                c.memmove(address, bytes((1,1))+b"\0"*5+b"\5"+struct.pack("<I",18),12)
                record.sid = (0 if mode == "null" else c.addressof(buffer)-1
                              if mode == "outside" else address)
                if mode == "grow": put(needed,t.DWORD,65)
                return 1
            def convert(sid, output):
                put(output,t.LPWSTR,c.cast(text,t.LPWSTR)); return 1
            self.w.k=N(CloseHandle=lambda handle: closed.append(handle.value if hasattr(handle,"value") else handle) or 1,
                       LocalFree=lambda pointer: freed.append(pointer) or 0)
            self.w.a=N(OpenProcessToken=open_token,GetTokenInformation=token_info,
                IsValidSid=lambda pointer: mode != "invalid",
                GetLengthSid=lambda pointer: 68 if mode == "sid_overflow" else 12,
                ConvertSidToStringSidW=convert)
            if mode == "ok":
                self.assertEqual(self.w.process_user(123),text.value)
                self.assertEqual(len(freed),1)
            else:
                with self.subTest(mode=mode),self.assertRaises(native.Failure):
                    self.w.process_user(123)
                self.assertEqual(freed,[])
            self.assertEqual(closed,[321])

    def test_ancestor_acl_real_ace_bytes_reject_untrusted_writer(self):
        identities = {name: bytes((1,1))+b"\0"*5+b"\5"+struct.pack("<I",number)
            for name,number in (("S-1-5-32-544",544),("S-1-5-18",18),
                                 ("S-1-5-21-1",1001),("foreign",2001))}
        self.w.sid_binary=lambda text: identities[text]
        self.w.process_user=lambda handle: "S-1-5-21-1"
        self.w.k=N(GetCurrentProcess=lambda: 1,LocalFree=lambda value: 0)
        def get_security(handle, kind, flags, owner, group, dacl, sacl, output):
            put(output,c.c_void_p,700); return 0
        self.w.a=N(GetSecurityInfo=get_security)
        for owner,ace_kind,ace_flags,mask,trust,expected in (
            ("S-1-5-18",0,0,0x40000000,False,False),
            ("S-1-5-18",0,0,0x00000004,False,False),
            ("S-1-5-18",0,0,0x40000000,True,True),
            ("S-1-5-18",0,0,0x80000000,False,True),
            ("S-1-5-18",0,8,0x40000000,False,True),
            ("S-1-5-18",1,0,0x40000000,False,True),
            ("foreign",0,0,0x80000000,False,False)):
            sid=identities["S-1-5-32-544" if trust else "foreign"]
            ace=struct.pack("<BBHI",ace_kind,ace_flags,8+len(sid),mask)+sid
            acl=struct.pack("<BBHHH",2,0,8+len(ace),1,0)+ace
            self.w.security=lambda descriptor: (identities[owner],acl,False)
            if expected: self.w.verify_ancestor(90)
            else:
                with self.subTest(owner=owner,mask=mask),self.assertRaises(native.Failure):
                    self.w.verify_ancestor(90)

    def test_effective_access_preserves_actual_granted_mask_and_releases_owned_handles(self):
        for mode in ("read_only","write","denied","oversize","api_failure"):
            closed,freed=[],[]
            def security(handle,kind,flags,owner,group,dacl,sacl,output):
                self.assertEqual((handle,kind,flags),(90,1,7))
                put(output,c.c_void_p,700); return 0
            def token(process,access,output):
                self.assertEqual((process,access),(123,10)); put(output,t.HANDLE,321); return 1
            def duplicate(source,level,output):
                self.assertEqual((source.value,level),(321,2)); put(output,t.HANDLE,322); return 1
            def access(descriptor,impersonation,desired,mapping,privileges,size,granted,allowed):
                self.assertEqual(desired,0x02000000)
                actual=c.cast(mapping,c.POINTER(native.GENERIC_MAPPING)).contents
                self.assertEqual((actual.read,actual.write,actual.execute,actual.all),
                                 (0x120089,0x120116,0x1200A0,0x1F01FF))
                put(size,t.DWORD,16385 if mode=="oversize" else 8)
                put(granted,t.DWORD,0x120116 if mode=="write" else 0x120089)
                put(allowed,t.BOOL,mode!="denied")
                return mode!="api_failure"
            self.w.a=N(GetSecurityInfo=security,OpenProcessToken=token,
                       DuplicateToken=duplicate,AccessCheck=access)
            self.w.k=N(CloseHandle=lambda handle: closed.append(handle.value if hasattr(handle,"value") else handle) or 1,
                       LocalFree=lambda pointer: freed.append(pointer) or 0)
            if mode in ("oversize","api_failure"):
                with self.subTest(mode=mode),self.assertRaises(native.Failure):
                    self.w.effective_access(90,123)
            else:
                observed=self.w.effective_access(90,123)
                self.assertEqual(observed["granted"],0x120116 if mode=="write" else 0x120089)
                self.assertEqual(observed["access_status"],mode!="denied")
                self.assertEqual(observed["privilege_bytes"],8)
            self.assertEqual(closed,[322,321]); self.assertEqual(len(freed),1)

    def test_effective_access_cleanup_attempts_all_and_preserves_body_first_error(self):
        for failed in (322,321,700):
            for body_failed in (False,True):
                with self.subTest(failed=failed,body_failed=body_failed):
                    acquired=set();attempted=[];body=native.Failure("modeled_access_body")
                    def security(handle,kind,flags,a,b,d,e,output):
                        acquired.add(700);put(output,c.c_void_p,700);return 0
                    def token(process,access,output):
                        acquired.add(321);put(output,t.HANDLE,321);return 1
                    def duplicate(source,level,output):
                        acquired.add(322);put(output,t.HANDLE,322);return 1
                    def access(descriptor,impersonation,desired,mapping,privileges,size,granted,allowed):
                        if body_failed:raise body
                        put(size,t.DWORD,8);put(granted,t.DWORD,0);put(allowed,t.BOOL,1);return 1
                    def release(resource):
                        value=resource.value if hasattr(resource,"value") else resource
                        if value not in acquired:raise AssertionError("unowned/double release")
                        attempted.append(value)
                        if value==failed:return 0
                        acquired.remove(value);return 1
                    self.w.a=N(GetSecurityInfo=security,OpenProcessToken=token,
                        DuplicateToken=duplicate,AccessCheck=access)
                    self.w.k=N(CloseHandle=release,LocalFree=lambda pointer:0 if release(pointer) else pointer.value)
                    with self.assertRaises(native.Failure) as caught:self.w.effective_access(90,123)
                    self.assertEqual(attempted,[322,321,700],"one cleanup failure must not skip remaining owned resources")
                    self.assertEqual(acquired,{failed})
                    if body_failed:self.assertIs(caught.exception,body)
                    self.assertTrue(any(note.startswith("cleanup_unknown:")
                                        for note in getattr(caught.exception,"__notes__",())))

    def test_verify_security_reports_caller_category_and_unprotected_flag(self):
        owner=c.create_string_buffer(bytes((1,1))+b"\0"*5+b"\5"+struct.pack("<I",18))
        actual_acl=c.create_string_buffer(struct.pack("<BBHHH",2,0,8,0,0))
        variant_acl=c.create_string_buffer(struct.pack("<BBHHH",2,1,8,0,0))
        wanted_acl=c.create_string_buffer(struct.pack("<BBHHH",2,0,16,0,0))
        for control_value,mode,expected in ((0x1000,"length","root_security_changed_dacl_length"),
                                            (0x1000,"variant","root_security_changed"),
                                            (0,"same","root_security_changed_unprotected")):
            with self.subTest(control=control_value,mode=mode,expected=expected):
                def descriptor(text,revision,output,size):put(output,c.c_void_p,701);return 1
                def security(handle,kind,flags,a,b,d,e,output):put(output,c.c_void_p,700);return 0
                def dacl(pointer,present,output,defaulted):
                    put(present,t.BOOL,1);put(defaulted,t.BOOL,0)
                    target = actual_acl
                    if pointer.value != 700:
                        target = {"length":wanted_acl,"variant":variant_acl}.get(mode,actual_acl)
                    put(output,c.c_void_p,c.addressof(target));return 1
                def own(pointer,output,defaulted):
                    put(defaulted,t.BOOL,0);put(output,c.c_void_p,c.addressof(owner));return 1
                def control(pointer,output,revision):
                    put(output,t.WORD,control_value);put(revision,t.DWORD,1);return 1
                self.w.k=N(LocalFree=lambda pointer:0)
                self.w.a=N(ConvertStringSecurityDescriptorToSecurityDescriptorW=descriptor,
                    GetSecurityInfo=security,GetSecurityDescriptorDacl=dacl,
                    GetSecurityDescriptorOwner=own,GetSecurityDescriptorControl=control,
                    IsValidSid=lambda pointer:1,GetLengthSid=lambda pointer:12)
                with self.assertRaises(native.Failure) as caught:
                    self.w.verify_security(90,"private",category="root_security_changed")
                self.assertEqual(str(caught.exception),expected)
                if mode=="variant":
                    self.assertEqual(getattr(caught.exception,"winerror",None),1)

    def test_verify_security_owner_assertion_is_optional_for_kernel_objects(self):
        actual_owner=c.create_string_buffer(bytes((1,1))+b"\0"*5+b"\5"+struct.pack("<I",18))
        wanted_owner=c.create_string_buffer(bytes((1,1))+b"\0"*5+b"\5"+struct.pack("<I",32))
        acl=c.create_string_buffer(struct.pack("<BBHHH",2,0,8,0,0))
        def install():
            def descriptor(text,revision,output,size):put(output,c.c_void_p,701);return 1
            def security(handle,kind,flags,a,b,d,e,output):put(output,c.c_void_p,700);return 0
            def dacl(pointer,present,output,defaulted):
                put(present,t.BOOL,1);put(defaulted,t.BOOL,0)
                put(output,c.c_void_p,c.addressof(acl));return 1
            def own(pointer,output,defaulted):
                put(defaulted,t.BOOL,0)
                put(output,c.c_void_p,c.addressof(actual_owner if pointer.value==700 else wanted_owner));return 1
            def control(pointer,output,revision):
                put(output,t.WORD,0x1000);put(revision,t.DWORD,1);return 1
            self.w.k=N(LocalFree=lambda pointer:0)
            self.w.a=N(ConvertStringSecurityDescriptorToSecurityDescriptorW=descriptor,
                GetSecurityInfo=security,GetSecurityDescriptorDacl=dacl,
                GetSecurityDescriptorOwner=own,GetSecurityDescriptorControl=control,
                IsValidSid=lambda pointer:1,GetLengthSid=lambda pointer:12)
        install()
        with self.assertRaises(native.Failure) as caught:
            self.w.verify_security(90,"private",category="job_security_changed")
        self.assertEqual(str(caught.exception),"job_security_changed_owner")
        self.assertIsNone(getattr(caught.exception,"winerror",None))
        install()
        self.assertIsNone(self.w.verify_security(90,"private",object_type=6,owner=False,
                                                 category="job_security_changed"))

    def test_verify_security_cleanup_attempts_both_descriptors_and_preserves_body(self):
        owner=c.create_string_buffer(bytes((1,1))+b"\0"*5+b"\5"+struct.pack("<I",18))
        acl=c.create_string_buffer(struct.pack("<BBHHH",2,0,8,0,0))
        for failed in (700,701):
            for body_failed in (False,True):
                with self.subTest(failed=failed,body_failed=body_failed):
                    acquired=set();attempted=[];body=native.Failure("modeled_security_body")
                    def descriptor(text,revision,output,size):
                        acquired.add(701);put(output,c.c_void_p,701);return 1
                    def security(handle,kind,flags,a,b,d,e,output):
                        acquired.add(700);put(output,c.c_void_p,700);return 0
                    def dacl(pointer,present,output,defaulted):
                        put(present,t.BOOL,1);put(defaulted,t.BOOL,0)
                        put(output,c.c_void_p,c.addressof(acl));return 1
                    def own(pointer,output,defaulted):
                        put(defaulted,t.BOOL,0);put(output,c.c_void_p,c.addressof(owner));return 1
                    def control(pointer,output,revision):
                        if body_failed:raise body
                        put(output,t.WORD,0x1000);put(revision,t.DWORD,1);return 1
                    def free(pointer):
                        value=pointer.value
                        if value not in acquired:raise AssertionError("unowned/double free")
                        attempted.append(value)
                        if value==failed:return value
                        acquired.remove(value);return 0
                    self.w.k=N(LocalFree=free)
                    self.w.a=N(ConvertStringSecurityDescriptorToSecurityDescriptorW=descriptor,
                        GetSecurityInfo=security,GetSecurityDescriptorDacl=dacl,
                        GetSecurityDescriptorOwner=own,GetSecurityDescriptorControl=control,
                        IsValidSid=lambda pointer:1,GetLengthSid=lambda pointer:12)
                    with self.assertRaises(native.Failure) as caught:self.w.verify_security(90,"private")
                    self.assertEqual(attempted,[700,701],"actual descriptor free failure must not strand expected descriptor")
                    self.assertEqual(acquired,{failed})
                    if body_failed:self.assertIs(caught.exception,body)
                    self.assertTrue(any(note.startswith("cleanup_unknown:")
                                        for note in getattr(caught.exception,"__notes__",())))

    def test_win32_remaining_owners_keep_body_and_attempt_independent_cleanup(self):
        targets={"open_file":"GetFileInformationByHandle","pin_ancestor":"GetFileInformationByHandle",
            "create_directory":"CreateDirectoryW","set_root_dacl":"SetSecurityInfo",
            "sid_binary":"IsValidSid","assert_admin":"CheckTokenMembership",
            "verify_ancestor":"GetSecurityDescriptorOwner","observe_security":"GetSecurityDescriptorOwner",
            "process_user":"GetTokenInformation"}
        for owner,target in targets.items():
            with self.subTest(owner=owner):
                owned=set();attempted=[];failed=[];counter=[700];active=[False]
                body=native.Failure("modeled_"+owner+"_body")
                sid=c.create_string_buffer(bytes((1,1))+b"\0"*5+b"\5"+struct.pack("<I",18))
                acl=c.create_string_buffer(struct.pack("<BBHHH",2,0,8,0,0))
                def trip(name):
                    if name==target:active[0]=True;raise body
                def allocation(output):
                    value=counter[0];counter[0]+=1;owned.add(value);put(output,c.c_void_p,value);return 1
                def descriptor(text,revision,output,size):return allocation(output)
                def security(handle,kind,flags,a,b,d,e,output):allocation(output);return 0
                def own(pointer,output,defaulted):
                    trip("GetSecurityDescriptorOwner");put(defaulted,t.BOOL,0)
                    put(output,c.c_void_p,c.addressof(sid));return 1
                def dacl(pointer,present,output,defaulted):
                    put(present,t.BOOL,1);put(defaulted,t.BOOL,0);put(output,c.c_void_p,c.addressof(acl));return 1
                def control(pointer,output,revision):put(output,t.WORD,0x1000);put(revision,t.DWORD,1);return 1
                def valid(pointer):trip("IsValidSid");return 1
                def create(*args):owned.add(90);return 90
                def info(handle,output):
                    trip("GetFileInformationByHandle")
                    value=c.cast(output,c.POINTER(native.FILE_INFO)).contents
                    value.attributes=0;value.links=1;value.volume=7;value.index_low=90;return 1
                def release(resource):
                    value=resource.value if hasattr(resource,"value") else resource
                    if value not in owned:raise AssertionError("unowned/double release")
                    if active[0]:attempted.append(value)
                    if active[0] and not failed:
                        failed.append(value);raise native.Failure("modeled_cleanup")
                    owned.remove(value);return 1
                def free(resource):release(resource);return 0
                def create_dir(*args):trip("CreateDirectoryW");return 1
                def set_security(*args):trip("SetSecurityInfo");return 0
                def convert_sid(text,output):owned.add(c.addressof(sid));put(output,c.c_void_p,c.addressof(sid));return 1
                def membership(*args):trip("CheckTokenMembership");return 1
                def open_token(process,access,output):owned.add(321);put(output,t.HANDLE,321);return 1
                def token_info(token,kind,buffer,capacity,needed):
                    put(needed,t.DWORD,64)
                    if buffer is None:return 0
                    trip("GetTokenInformation");return 1
                self.w.k=N(CreateFileW=create,GetFileInformationByHandle=info,CloseHandle=release,
                    LocalFree=free,CreateDirectoryW=create_dir)
                self.w.a=N(ConvertStringSecurityDescriptorToSecurityDescriptorW=descriptor,
                    GetSecurityInfo=security,GetSecurityDescriptorOwner=own,GetSecurityDescriptorDacl=dacl,
                    GetSecurityDescriptorControl=control,IsValidSid=valid,GetLengthSid=lambda pointer:12,
                    SetSecurityInfo=set_security,ConvertStringSidToSidW=convert_sid,
                    CheckTokenMembership=membership,OpenProcessToken=open_token,GetTokenInformation=token_info)
                with self.assertRaises(native.Failure) as caught:
                    if owner=="open_file":self.w.open_file("/model/private.bin","private")
                    elif owner=="pin_ancestor":self.w.pin_ancestor("/model")
                    elif owner=="create_directory":self.w.create_directory("/model/new","private")
                    elif owner=="set_root_dacl":self.w.set_root_dacl(90,"old","new")
                    elif owner=="sid_binary":self.w.sid_binary("S-1-5-18")
                    elif owner=="assert_admin":self.w.assert_admin()
                    elif owner=="verify_ancestor":self.w.verify_ancestor(90)
                    elif owner=="observe_security":self.w.observe_security(90)
                    else:self.w.process_user(90)
                self.assertTrue(active[0],"case must reach intended real owner body")
                self.assertEqual(owned,set(failed),"every other acquired resource must be attempted")
                self.assertIs(caught.exception,body)
                self.assertTrue(any(n.startswith("cleanup_unknown:") for n in getattr(body,"__notes__",())))


if __name__ == "__main__":
    unittest.main()
