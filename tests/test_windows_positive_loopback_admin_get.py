"""Complete Get software boundary; fake Win32 ABI, never native evidence."""
from __future__ import annotations
import ctypes
from ctypes import wintypes
import importlib
import io
from pathlib import PureWindowsPath
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import patch


def optional(name):
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        if exc.name != name:
            raise
        return None


admin = optional("scripts.windows_positive_loopback_admin")
reader = optional("scripts.windows_positive_loopback_full_get")


def raw(entries):
    return dict(schema=1, entries=entries, api_code=0, complete=True,
                sid_attempted=len(entries), sid_freed=len(entries),
                array_freed=True, library_freed=True, process_reaped=True)


def binary(last):
    return bytes((1, 2)) + (15).to_bytes(6, "big") + struct.pack("<II", 2, last)


class MemoryOS:
    """Own real allocations; no callable here invokes the operating system."""
    def __init__(self, module, count=2):
        self.module = module
        self.buffers = [ctypes.create_string_buffer(binary(i + 1)) for i in range(count)]
        self.rows = (module.SID_AND_ATTRIBUTES * count)()
        for i, buffer in enumerate(self.buffers):
            self.rows[i].Sid = ctypes.addressof(buffer)
            self.rows[i].Attributes = 0x80000004 + i
        self.count = count
        self.code = 0
        self.null_array = False
        self.invalid = set()
        self.fail_free = set()
        self.lengths = {}
        self.freed = []
        self.events = []
        self.library = SimpleNamespace(_handle=700)
        self.library_ok = True

    def query(self, count, array):
        self.events.append("query")
        ctypes.cast(count, ctypes.POINTER(wintypes.DWORD))[0] = self.count
        ctypes.cast(array, ctypes.POINTER(ctypes.c_void_p))[0] = (
            0 if self.null_array else ctypes.addressof(self.rows))
        return self.code

    def IsValidSid(self, pointer):
        self.events.append(("valid", pointer))
        return pointer not in self.invalid

    def GetLengthSid(self, pointer):
        return self.lengths.get(pointer, 16)

    def GetProcessHeap(self):
        return 600

    def HeapFree(self, heap, flags, pointer):
        address = pointer.value if isinstance(pointer, ctypes.c_void_p) else pointer
        if heap != 600 or flags != 0 or address in self.freed:
            raise AssertionError("wrong allocator or double free")
        self.freed.append(address)
        self.events.append(("free", address))
        return address not in self.fail_free

    def FreeLibrary(self, handle):
        if handle != 700:
            raise AssertionError("wrong library handle")
        self.events.append("unload")
        return self.library_ok

    def load(self):
        return self, self, self.library, self.query


class TestAdminCompleteGet(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(admin, "new admin component absent; expected facility RED")
        self.assertIsNotNone(reader, "new complete Get component absent; expected facility RED")

    def collect(self, model):
        with patch.object(reader, "_load", model.load):
            return reader.collect()

    def test_mapping_binary_identity_and_order_independence(self):
        rows = [["S-1-15-2-1", 0x80000004], ["S-1-15-2-2", 0xffffffff]]
        self.assertEqual(admin._mapping(raw(rows)), admin._mapping(raw(rows[::-1])))
        self.assertEqual(set(admin._mapping(raw(rows)).values()), {0x80000004, 0xffffffff})

    def test_mapping_exact_schema_types_and_release_counts(self):
        good = raw([["S-1-15-2-1", 7]])
        cases = [dict(good, extra=1), {k:v for k,v in good.items() if k != "complete"}]
        for key in ("schema", "api_code", "sid_attempted", "sid_freed"):
            cases.append(dict(good, **{key: True}))
        for key in ("complete", "array_freed", "library_freed", "process_reaped"):
            for value in (False, None, 1):
                cases.append(dict(good, **{key:value}))
        for key in ("sid_attempted", "sid_freed"):
            for value in (0, 2, -1):
                cases.append(dict(good, **{key:value}))
        for case in cases:
            with self.subTest(case=case), self.assertRaises((admin.AdminError, ValueError)):
                admin._mapping(case)

    def test_mapping_duplicate_sid_attributes_and_limit(self):
        cases = [raw([["S-1-15-2-1", 1], ["S-1-15-2-1", 2]]),
                 raw([["S-1-15-2-01", 1]]), raw([["S-1-15-2-1", True]]),
                 raw([["S-1-15-2-1", -1]]), raw([["S-1-15-2-1", 1 << 32]]),
                 raw([["S-1-15-2-1", 1]] * 4097)]
        for case in cases:
            with self.subTest(case=case), self.assertRaises((admin.AdminError, ValueError)):
                admin._mapping(case)
        boundary = [["S-1-15-2-" + str(index + 1), index] for index in range(4096)]
        self.assertEqual(len(admin._mapping(raw(boundary))), 4096)

    def test_collect_real_buffers_all_entries_and_allocator_pairing(self):
        model = MemoryOS(reader)
        result = self.collect(model)
        self.assertTrue(result["complete"])
        self.assertIsNone(result["process_reaped"])
        self.assertEqual(result["entries"], [["S-1-15-2-1", 0x80000004],
                                             ["S-1-15-2-2", 0x80000005]])
        self.assertEqual(model.freed, [ctypes.addressof(b) for b in model.buffers]
                         + [ctypes.addressof(model.rows)])
        self.assertEqual((result["sid_attempted"], result["sid_freed"]), (2, 2))
        self.assertEqual(model.events[-1], "unload")

    def test_collect_zero_entries_is_complete_without_sid_free(self):
        model = MemoryOS(reader, 0)
        model.null_array = True
        result = self.collect(model)
        self.assertTrue(result["complete"])
        self.assertEqual(result["entries"], [])
        self.assertEqual(model.freed, [])

    def test_collect_no_partial_snapshot_for_bad_count_or_api(self):
        for mode in ("api", "limit", "null"):
            model = MemoryOS(reader)
            if mode == "api": model.code = 5
            if mode == "limit": model.count = 4097
            if mode == "null": model.null_array = True
            result = self.collect(model)
            self.assertFalse(result["complete"])
            self.assertEqual(result["entries"], [])
            self.assertEqual(model.freed, [])

    def test_collect_unsafe_ownership_graph_never_double_frees(self):
        for mode in ("null", "array_alias", "sid_alias", "invalid"):
            model = MemoryOS(reader)
            if mode == "null": model.rows[1].Sid = 0
            if mode == "array_alias": model.rows[1].Sid = ctypes.addressof(model.rows)
            if mode == "sid_alias": model.rows[1].Sid = model.rows[0].Sid
            if mode == "invalid": model.invalid.add(model.rows[1].Sid)
            result = self.collect(model)
            self.assertFalse(result["complete"])
            self.assertEqual(result["entries"], [])
            self.assertEqual(model.freed, [])

    def test_collect_binary_duplicate_releases_safe_distinct_allocations(self):
        model = MemoryOS(reader)
        ctypes.memmove(model.buffers[1], model.buffers[0], 16)
        result = self.collect(model)
        self.assertFalse(result["complete"])
        self.assertEqual(len(model.freed), 3)

    def test_collect_failed_release_or_sid_length_stays_incomplete(self):
        for mode in ("sid_free", "array_free", "library", "length"):
            model = MemoryOS(reader)
            if mode == "sid_free": model.fail_free.add(model.rows[0].Sid)
            if mode == "array_free": model.fail_free.add(ctypes.addressof(model.rows))
            if mode == "library": model.library_ok = False
            if mode == "length": model.lengths[model.rows[0].Sid] = 69
            self.assertFalse(self.collect(model)["complete"])

    def test_sid_binary_text_validation(self):
        self.assertEqual(reader._text_sid(binary(1)), "S-1-15-2-1")
        for value in (b"", binary(1)[:-1], bytes((2,)) + binary(1)[1:],
                      bytes((1, 0)) + b"\0" * 6, "S-1-15-2-1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                reader._text_sid(value)

    def test_load_binding_body_survives_free_library_failure(self):
        body=AttributeError("modeled_export_body");released=[]
        class Function:
            def __init__(self,body):self.body=body
            def __call__(self,*args):return self.body(*args)
        def directory(buffer,capacity):buffer.value=r"C:\Windows\System32";return len(buffer.value)
        def free(handle):released.append(handle);raise OSError("modeled_FreeLibrary_cleanup")
        kernel=SimpleNamespace(GetSystemDirectoryW=Function(directory),FreeLibrary=Function(free),
            GetProcessHeap=Function(lambda:600),HeapFree=Function(lambda *args:1))
        advapi=SimpleNamespace(IsValidSid=Function(lambda *args:1),GetLengthSid=Function(lambda *args:16))
        class Library:
            _handle=700
            def __getattr__(self,name):raise body
        def dll(name,**options):
            if name=="kernel32":return kernel
            if name==r"C:\Windows\System32\advapi32.dll":return advapi
            if name==r"C:\Windows\System32\FirewallAPI.dll":return Library()
            raise AssertionError("nonfixed library")
        with patch.object(reader,"Path",PureWindowsPath),patch.object(reader.ctypes,"WinDLL",dll,create=True):
            with self.assertRaises(Exception) as caught:reader._load()
        self.assertEqual(released,[700]);self.assertIs(caught.exception,body)
        self.assertTrue(any(n.startswith("cleanup_unknown:") for n in getattr(body,"__notes__",())))

    def test_load_system_directory_exports_and_failed_binding_release(self):
        class Function:
            def __init__(self, body): self.body = body
            def __call__(self, *args): return self.body(*args)
        for missing in (False, True):
            loaded, freed, exports = [], [], []
            def directory(buffer, capacity):
                buffer.value = r"C:\Windows\System32"
                return len(buffer.value)
            kernel = SimpleNamespace(
                GetSystemDirectoryW=Function(directory),
                FreeLibrary=Function(lambda handle: freed.append(handle) or 1),
                GetProcessHeap=Function(lambda: 600),
                HeapFree=Function(lambda *args: 1))
            advapi = SimpleNamespace(IsValidSid=Function(lambda *args: 1),
                                     GetLengthSid=Function(lambda *args: 16))
            class Library:
                _handle = 700
                def __getattr__(self, name):
                    exports.append(name)
                    if name != "NetworkIsolationGetAppContainerConfig" or missing:
                        raise AttributeError(name)
                    return Function(lambda *args: 0)
            library = Library()
            def dll(name, **options):
                loaded.append((name, options))
                if name == "kernel32": return kernel
                if name == r"C:\Windows\System32\advapi32.dll": return advapi
                if name == r"C:\Windows\System32\FirewallAPI.dll": return library
                raise AssertionError("non-system library requested")
            with patch.object(reader, "Path", PureWindowsPath), patch.object(
                    reader.ctypes, "WinDLL", dll, create=True):
                if missing:
                    with self.assertRaises(AttributeError): reader._load()
                    self.assertEqual(freed, [700])
                else:
                    self.assertIs(reader._load()[2], library)
                    self.assertEqual(freed, [])
            self.assertEqual(exports, ["NetworkIsolationGetAppContainerConfig"])
            self.assertEqual([name for name, options in loaded], ["kernel32",
                r"C:\Windows\System32\advapi32.dll",
                r"C:\Windows\System32\FirewallAPI.dll"])
            self.assertEqual([options.get("winmode") for name, options in loaded[1:]],
                             [0x800, 0x800])

    def test_worker_entry_exact_argv_and_private_complete_output(self):
        import json
        import sys
        result = raw([["S-1-15-2-1", 7]])
        result["process_reaped"] = None
        for platform, arguments in (("linux", ["reader", "--full-get"]),
                ("win32", ["reader", "--full-get", "extra"]),
                ("win32", ["reader", "--arbitrary-command"])):
            stream = SimpleNamespace(buffer=io.BytesIO())
            with patch.object(reader.sys, "platform", platform), patch.object(
                    reader.sys, "argv", arguments), patch.object(reader.sys, "stdout", stream):
                self.assertEqual(reader.main(), 2)
                self.assertEqual(stream.buffer.getvalue(), b"")
        for complete, expected in ((True, 0), (False, 4)):
            value = dict(result, complete=complete)
            stream = SimpleNamespace(buffer=io.BytesIO())
            with patch.object(reader.sys, "platform", "win32"), patch.object(
                    reader.sys, "argv", ["reader", "--full-get"]), patch.object(
                    reader.sys, "stdout", stream), patch.object(reader, "collect", lambda: value):
                self.assertEqual(reader.main(), expected)
            self.assertEqual(json.loads(stream.buffer.getvalue()), value)
            self.assertIsNone(json.loads(stream.buffer.getvalue())["process_reaped"])


if __name__ == "__main__":
    unittest.main()
