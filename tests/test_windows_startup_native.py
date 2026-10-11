"""Native ABI transport tests do not establish Windows OS enforcement."""
import importlib.util
import importlib
import os
import unittest
import ctypes as C
import inspect
import sys
from unittest.mock import patch
from types import SimpleNamespace
from icode.windows_startup_pin import StartupPinError


class Function:
    def __init__(self, impl):
        self.impl = impl
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        return self.impl(*args)


class NativeTransportTests(unittest.TestCase):
    """Fake DLL boundary checks production ctypes construction/consumption only."""
    def setUp(self):
        self.m = importlib.import_module('icode.windows_startup_native')
        self.assertTrue(hasattr(self.m.WindowsStartupPinBackend, 'open_root'))
        self.next_handle = 10
        self.mapping = '\\Device\\HarddiskVolume12\0\0'
        self.failure = ''
        self.k = SimpleNamespace(
            QueryDosDeviceW=Function(self.dos),
            GetFileType=Function(lambda h: 2 if self.failure == 'type' else 1),
            GetFileInformationByHandleEx=Function(self.info),
            SetFilePointerEx=Function(self.seek), ReadFile=Function(self.read),
            CloseHandle=Function(lambda h: int(self.failure != 'close')))
        self.n = SimpleNamespace(NtCreateFile=Function(self.open))
        with patch.object(self.m.os, 'name', 'nt'), patch.object(
                self.m.ctypes, 'WinDLL', side_effect=[self.k, self.n], create=True):
            self.b = self.m.WindowsStartupPinBackend()

    def dos(self, name, buffer, count):
        units = self.mapping.encode('utf-16-le')
        C.memmove(buffer, units, len(units))
        return 0 if self.failure == 'dos' else len(units) // 2

    def open(self, output, access, oa, ios, alloc, attrs, share, disposition, opts, ea, length):
        self.oa = C.cast(oa, C.POINTER(self.m._OBJECT_ATTRIBUTES)).contents
        us = self.oa.ObjectName.contents
        self.name = C.string_at(us.Buffer, us.Length).decode('utf-16-le')
        self.params = access, share, disposition, opts, self.oa.Attributes
        C.cast(output, C.POINTER(C.c_void_p))[0] = self.next_handle
        self.next_handle += 1
        return -1 if self.failure == 'open' else 0

    def info(self, handle, kind, output, size):
        struct = self.m._INFO_CLASSES[kind]
        value = C.cast(output, C.POINTER(struct)).contents
        directory = self.b._active[handle]
        if kind == 0:
            value.FileAttributes = 16 if directory else 128
            value.ChangeTime = 7
        elif kind == 1:
            value.Directory = directory
            value.NumberOfLinks = 1
            value.EndOfFile = 3
        elif kind == 9:
            value.FileAttributes = 16 if directory else 128
        else:
            value.VolumeSerialNumber = 9
            value.FileId[0] = handle
        return int(self.failure != 'info' + str(kind))

    def seek(self, handle, offset, position, origin):
        C.cast(position, C.POINTER(C.c_int64))[0] = offset + (self.failure == 'position')
        return int(self.failure != 'seek')

    def read(self, handle, buf, count, actual, overlap):
        C.memmove(buf, b'abc', min(count, 3))
        C.cast(actual, C.POINTER(C.c_uint32))[0] = count + 1 if self.failure == 'count' else min(count, 3)
        return int(self.failure != 'read')

    def test_root_is_direct_nt_volume_and_strict_sharing(self):
        self.assertEqual(self.b.open_root('C:'), 10)
        self.assertEqual(self.name, '\\Device\\HarddiskVolume12\\')
        access, share, disposition, opts, attributes = self.params
        self.assertEqual(share, 1)
        self.assertEqual(disposition, 1)
        self.assertEqual(attributes, 0x1040)
        self.assertTrue(access & 1)
        self.assertTrue(access & 0x20000)
        self.assertEqual(access, 0x120081)
        self.assertTrue(access & 0x100000)
        self.assertTrue(opts & 1)

    def test_child_relative_role_query_and_read(self):
        root = self.b.open_root('C:')
        file = self.b.open_child(root, '启动.py', directory=False)
        self.assertEqual(self.oa.RootDirectory, root)
        self.assertEqual(self.name, '启动.py')
        self.assertTrue(self.params[3] & 0x40)
        meta = self.b.query(file)
        self.assertEqual((meta.volume_serial, len(meta.file_id), meta.size), (9, 16, 3))
        self.assertEqual(self.b.read(file, 0, 3), b'abc')
        self.b.close(file)
        with self.assertRaises(StartupPinError):
            self.b.query(file)

    def test_reject_drive_mapping_and_component_boundaries(self):
        for drive in ('C:\\', 'CC:', 'é:', '1:', True):
            with self.subTest(drive=drive), self.assertRaises(StartupPinError):
                self.b.open_root(drive)
        for mapping in ('\\??\\C:\\tmp\0\0', '\\Device\\Mup\0\0',
                        '\\Device\\HarddiskVolume1\0', '\\Device\\HarddiskVolume1x\0\0'):
            self.mapping = mapping
            with self.subTest(mapping=mapping), self.assertRaises(StartupPinError):
                self.b.open_root('C:')
        self.mapping = '\\Device\\HarddiskVolume12\0\0'
        root = self.b.open_root('C:')
        for name in ('', '.', '..', 'a/b', 'a\\b', 'a:b', 'a\0b', '\ud800', 'x' * 256):
            with self.subTest(name=repr(name)), self.assertRaises(StartupPinError):
                self.b.open_child(root, name, directory=False)

    def test_api_failures_and_close_single_attempt(self):
        for fail in ('dos', 'open'):
            self.failure = fail
            with self.assertRaises(StartupPinError):
                self.b.open_root('C:')
        self.failure = ''
        root = self.b.open_root('C:')
        file = self.b.open_child(root, 'a', directory=False)
        for fail in ('type', 'info0', 'info1', 'info9', 'info18'):
            self.failure = fail
            with self.subTest(fail=fail), self.assertRaises(StartupPinError):
                self.b.query(file)
        for fail in ('seek', 'position', 'read', 'count'):
            self.failure = fail
            with self.subTest(fail=fail), self.assertRaises(StartupPinError):
                self.b.read(file, 0, 3)
        self.failure = 'close'
        with self.assertRaises(StartupPinError):
            self.b.close(file)
        calls = len(self.k.CloseHandle.calls)
        with self.assertRaises(StartupPinError):
            self.b.close(file)
        self.assertEqual(len(self.k.CloseHandle.calls), calls)

    def test_roles_and_read_bounds(self):
        root = self.b.open_root('C:')
        file = self.b.open_child(root, 'a', directory=False)
        for handle, offset, count in ((root, 0, 1), (999, 0, 1), (True, 0, 1),
                                     (file, True, 1), (file, -1, 1), (file, 0, 65537),
                                     (file, 0, True), (file, 2**63, 1)):
            with self.subTest(params=(handle, offset, count)), self.assertRaises(StartupPinError):
                self.b.read(handle, offset, count)
        with self.assertRaises(StartupPinError):
            self.b.open_child(file, 'b', directory=False)

    def test_device_aliases_rejected_by_native_entry(self):
        root = self.b.open_root('C:')
        for name in ('CON', 'nul.py', 'COM1', 'LPT¹.txt', 'CONIN$', 'CLOCK$'):
            with self.subTest(name=name), self.assertRaises(StartupPinError):
                self.b.open_child(root, name, directory=False)

    def test_native_exception_after_output_cleans_owned_handle(self):
        for exception in (OSError('private path'), KeyboardInterrupt(), SystemExit()):
            def interrupted(*args):
                self.open(*args)
                raise exception
            self.n.NtCreateFile.impl = interrupted
            before = len(self.k.CloseHandle.calls)
            expected = StartupPinError if isinstance(exception, OSError) else type(exception)
            with self.assertRaises(BaseException) as caught:
                self.b.open_root('C:')
            self.assertIsInstance(caught.exception, expected)
            self.assertEqual(len(self.k.CloseHandle.calls), before + 1)
            self.assertNotIn('private path', str(caught.exception))

    def test_cleanup_note_failure_preserves_original_interrupt(self):
        class NotesInterrupt(KeyboardInterrupt):
            def __getattribute__(self, name):
                if name == '__notes__':
                    raise RuntimeError('notes unavailable')
                return BaseException.__getattribute__(self, name)

        class NotesExit(SystemExit):
            __getattribute__ = NotesInterrupt.__getattribute__

        for kind in (NotesInterrupt, NotesExit):
            original = kind('original interrupt')
            def interrupted(*args):
                self.open(*args)
                raise original
            self.n.NtCreateFile.impl = interrupted
            self.k.CloseHandle.impl = lambda handle: 0
            before = len(self.k.CloseHandle.calls)
            handle = self.next_handle
            with self.subTest(kind=kind.__name__):
                with self.assertRaises(BaseException) as caught:
                    self.b.open_root('C:')
                self.assertIs(caught.exception, original)
                self.assertIn(handle, self.b._unknown)
                self.assertNotIn(handle, self.b._active)
                self.assertEqual(len(self.k.CloseHandle.calls), before + 1)

    def _interrupt_open_at(self, statement, original):
        # Bounded Python line events after a successful API output, not a claim
        # that arbitrary asynchronous bytecode interruption is atomic.
        function = self.m.WindowsStartupPinBackend._open
        lines, start = inspect.getsourcelines(function)
        target = next(start + i for i, line in enumerate(lines)
                      if line.strip() == statement)
        triggered = []
        def trace(frame, event, arg):
            if frame.f_code is function.__code__ and event == 'line' and frame.f_lineno == target:
                triggered.append(True)
                raise original
            return trace
        previous = sys.gettrace()
        try:
            sys.settrace(trace)
            with self.assertRaises(BaseException) as caught:
                self.b.open_root('C:')
        finally:
            sys.settrace(previous)
        self.assertEqual(triggered, [True])
        self.assertIs(caught.exception, original)

    def test_successful_output_interrupt_is_cleaned_through_return(self):
        for statement in ('handle = output.value', 'self._active[handle] = directory', 'return handle'):
            for kind in (KeyboardInterrupt, SystemExit):
                for close_ok in (True, False):
                    handle = self.next_handle
                    self.k.CloseHandle.impl = lambda h: int(close_ok)
                    before = len(self.k.CloseHandle.calls)
                    original = kind()
                    with self.subTest(statement=statement, kind=kind.__name__, close_ok=close_ok):
                        self._interrupt_open_at(statement, original)
                        self.assertEqual(self.k.CloseHandle.calls[before:], [(handle,)])
                        self.assertNotIn(handle, self.b._active)
                        self.assertIn(handle, self.b._retired)
                        self.assertEqual(handle in self.b._unknown, not close_ok)
                        if not close_ok:
                            self.assertIn('Startup acquired HANDLE cleanup unconfirmed', original.__notes__)
                        with self.assertRaises(StartupPinError):
                            self.b.close(handle)
                        self.assertEqual(self.k.CloseHandle.calls[before:], [(handle,)])

    def test_output_interrupt_does_not_close_active_or_unknown_collision(self):
        for state in ('active', 'unknown', 'retired'):
            handle = self.next_handle
            if state == 'active':
                self.b._active[handle] = False
            else:
                getattr(self.b, '_' + state).add(handle)
            before = len(self.k.CloseHandle.calls)
            with self.subTest(state=state):
                self._interrupt_open_at('handle = output.value', KeyboardInterrupt())
                expected = [(handle,)] if state == 'retired' else []
                self.assertEqual(self.k.CloseHandle.calls[before:], expected)
                if state == 'active':
                    self.assertIs(self.b._active[handle], False)
                else:
                    self.assertIn(handle, getattr(self.b, '_' + state))

    def test_api_interrupt_collision_preserves_existing_owner(self):
        for state in ('active', 'unknown', 'retired'):
            for kind in (KeyboardInterrupt, SystemExit):
                handle = self.next_handle
                original = kind()
                if state == 'active':
                    self.b._active[handle] = False
                else:
                    getattr(self.b, '_' + state).add(handle)
                def interrupted(*args):
                    self.open(*args)
                    raise original
                self.n.NtCreateFile.impl = interrupted
                before = len(self.k.CloseHandle.calls)
                with self.subTest(state=state, kind=kind.__name__):
                    with self.assertRaises(BaseException) as caught:
                        self.b.open_root('C:')
                    self.assertIs(caught.exception, original)
                    self.assertEqual(self.k.CloseHandle.calls[before:],
                                     [(handle,)] if state == 'retired' else [])
                    if state == 'active':
                        self.assertIs(self.b._active[handle], False)
                    else:
                        self.assertIn(handle, getattr(self.b, '_' + state))

    def test_close_exception_marks_unknown_and_never_retries(self):
        root = self.b.open_root('C:')
        def interrupted(handle):
            raise OSError('private path')
        self.k.CloseHandle.impl = interrupted
        with self.assertRaises(BaseException) as caught:
            self.b.close(root)
        self.assertIsInstance(caught.exception, StartupPinError)
        self.assertIn(root, self.b._unknown)
        before = len(self.k.CloseHandle.calls)
        with self.assertRaises(StartupPinError):
            self.b.close(root)
        self.assertEqual(before, len(self.k.CloseHandle.calls))

    def test_multisz_current_precedes_history_and_has_strict_extent(self):
        self.mapping = '\\Device\\HarddiskVolume12\0\\??\\old-mapping\0\0'
        self.b.open_root('C:')
        self.assertEqual(self.name, '\\Device\\HarddiskVolume12\\')
        for mapping in ('\0\0', '\\Device\\HarddiskVolume1\0\0junk',
                        '\\Device\\HarddiskVolume1\0\0\0'):
            self.mapping = mapping
            with self.subTest(mapping=repr(mapping)), self.assertRaises(StartupPinError):
                self.b.open_root('C:')

    def test_native_unicode_maximum_length_does_not_wrap(self):
        self.mapping = '\\Device\\HarddiskVolume' + '1' * (32766 - 22) + '\0\0'
        with self.assertRaises(StartupPinError):
            self.b.open_root('C:')
        for length in (True, 1, 32769):
            self.k.QueryDosDeviceW.impl = lambda *args: length
            with self.subTest(length=length), self.assertRaises(StartupPinError):
                self.b.open_root('C:')

    def test_api_signatures_and_64bit_layout(self):
        for name in vars(self.k):
            fn = getattr(self.k, name)
            self.assertIsNotNone(fn.argtypes)
            self.assertIsNotNone(fn.restype)
        self.assertEqual(self.n.NtCreateFile.restype, C.c_int32)
        self.assertEqual(C.sizeof(self.m._FILE_BASIC_INFO), 40)
        self.assertEqual(C.sizeof(self.m._FILE_STANDARD_INFO), 24)
        self.assertEqual(C.sizeof(self.m._FILE_ID_INFO), 24)
        if C.sizeof(C.c_void_p) == 8:
            self.assertEqual(C.sizeof(self.m._OBJECT_ATTRIBUTES), 48)
            self.assertEqual(C.sizeof(self.m._UNICODE_STRING), 16)
            self.assertEqual(C.sizeof(self.m._IO_STATUS_BLOCK), 16)

    def test_missing_api_refuses_backend(self):
        del self.k.ReadFile
        with patch.object(self.m.os, 'name', 'nt'), patch.object(
                self.m.ctypes, 'WinDLL', side_effect=[self.k, self.n], create=True):
            with self.assertRaises(StartupPinError):
                self.m.WindowsStartupPinBackend()

    def test_dll_load_errors_are_fixed_and_do_not_disclose(self):
        with patch.object(self.m.os, 'name', 'nt'), patch.object(
                self.m.ctypes, 'WinDLL', side_effect=ValueError('private path'), create=True):
            with self.assertRaises(BaseException) as caught:
                self.m.WindowsStartupPinBackend()
            self.assertIsInstance(caught.exception, StartupPinError)
            self.assertNotIn('private path', str(caught.exception))

    def test_failed_open_cleanup_error_is_explicit_and_not_retried(self):
        self.failure = 'open'
        self.k.CloseHandle.impl = lambda handle: 0
        with self.assertRaises(StartupPinError):
            self.b.open_root('C:')
        self.assertIn(10, self.b._unknown)
        with self.assertRaises(StartupPinError):
            self.b.close(10)
        self.assertEqual(self.k.CloseHandle.calls, [(10,)])

    def test_native_null_and_invalid_output_are_not_close_targets(self):
        for handle in (0, C.c_void_p(-1).value):
            self.next_handle = handle
            with self.subTest(handle=handle), self.assertRaises(StartupPinError):
                self.b.open_root('C:')
        self.assertEqual(self.k.CloseHandle.calls, [])

    def test_role_type_and_utf16_byte_limit(self):
        root = self.b.open_root('C:')
        with self.assertRaises(StartupPinError):
            self.b.open_child(root, 'x', directory=1)
        with self.assertRaises(StartupPinError):
            self.b.open_child(root, '😀' * 128, directory=False)
        self.b.open_child(root, 'x' * 255, directory=False)

    def test_failed_open_cleanup_and_active_collision_is_not_closed(self):
        self.failure = 'open'
        with self.assertRaises(StartupPinError):
            self.b.open_root('C:')
        self.assertEqual(self.k.CloseHandle.calls, [(10,)])
        self.failure = ''
        root = self.b.open_root('C:')
        self.next_handle = root
        with self.assertRaises(StartupPinError):
            self.b.open_child(root, 'x', directory=False)
        self.assertEqual(self.k.CloseHandle.calls, [(10,)])
        self.assertIn(root, self.b._active)

    def test_retired_output_rejected_and_cleaned_unknown_is_not_closed(self):
        root = self.b.open_root('C:')
        self.b.close(root)
        self.next_handle = root
        with self.assertRaises(StartupPinError):
            self.b.open_root('C:')
        self.assertEqual(self.k.CloseHandle.calls, [(root,), (root,)])
        root = self.b.open_root('C:')
        self.failure = 'close'
        with self.assertRaises(StartupPinError):
            self.b.close(root)
        before = len(self.k.CloseHandle.calls)
        self.next_handle = root
        with self.assertRaises(StartupPinError):
            self.b.open_root('C:')
        self.assertEqual(before, len(self.k.CloseHandle.calls))

    def test_metadata_inconsistencies_fail_closed(self):
        root = self.b.open_root('C:')
        file = self.b.open_child(root, 'x', directory=False)
        mutations = ((0, 'FileAttributes', 16), (1, 'Directory', 1),
                     (1, 'Directory', 2), (1, 'DeletePending', 2),
                     (1, 'EndOfFile', -1), (9, 'FileAttributes', 0x400),
                     (9, 'ReparseTag', 0xA0000003))
        for kind, field, value in mutations:
            def modified(handle, actual_kind, output, size):
                result = self.info(handle, actual_kind, output, size)
                if kind == actual_kind:
                    obj = C.cast(output, C.POINTER(self.m._INFO_CLASSES[kind])).contents
                    setattr(obj, field, value)
                return result
            self.k.GetFileInformationByHandleEx.impl = modified
            with self.subTest(field=field, value=value), self.assertRaises(StartupPinError):
                self.b.query(file)

    def test_owner_consumes_native_transport(self):
        from icode.windows_startup_pin import pin_startup_file
        with pin_startup_file('C:\\parent\\x.py', _backend=self.b) as owner:
            self.assertEqual(owner.content, b'abc')
            owner.revalidate()
        self.assertEqual(self.k.CloseHandle.calls, [(12,), (11,), (10,)])

    def test_read_eof_and_zero_count(self):
        root = self.b.open_root('C:')
        file = self.b.open_child(root, 'x', directory=False)
        self.assertEqual(self.b.read(file, 0, 0), b'')
        def eof(handle, buf, count, actual, overlap):
            C.cast(actual, C.POINTER(C.c_uint32))[0] = 0
            return 1
        self.k.ReadFile.impl = eof
        self.assertEqual(self.b.read(file, 3, 1), b'')

    def _security_query(self):
        query = getattr(self.b, 'query_security', None)
        self.assertTrue(callable(query), 'query_security must be callable')
        return query

    def test_security_query_lazy_reader_uses_same_active_handle(self):
        query = self._security_query()
        module = importlib.import_module('icode.windows_startup_security_native')
        from tests.test_windows_startup_security_native import NativeFixture
        fixture = NativeFixture()
        reader = fixture.reader(module)
        root = self.b.open_root('C:')
        file = self.b.open_child(root, 'x', directory=False)
        before = len(self.n.NtCreateFile.calls)
        with patch.object(module, 'WindowsStartupSecurityReader', return_value=reader) as factory:
            for handle in (file, root, file):
                metadata = self.b.query(handle)
                self.assertEqual(query(handle), fixture.raw)
                self.assertEqual(self.b.query(handle), metadata)
            factory.assert_called_once_with()
        self.assertEqual([args[0] for args in fixture.advapi.GetSecurityInfo.calls], [file, root, file])
        self.assertEqual(len(self.n.NtCreateFile.calls), before)
        self.assertEqual(len(fixture.kernel.LocalFree.calls), 3)
        self.assertEqual(self.k.CloseHandle.calls, [])
        self.assertEqual(self.b.read(file, 0, 3), b'abc')
        self.b.close(file)
        with self.assertRaises(StartupPinError):
            query(file)
        self.assertEqual(len(fixture.advapi.GetSecurityInfo.calls), 3)

    def test_security_query_rejects_unowned_before_import_or_dll_load(self):
        query = self._security_query()
        root = self.b.open_root('C:')
        self.b.close(root)
        unknown = self.b.open_root('C:')
        self.failure = 'close'
        with self.assertRaises(StartupPinError):
            self.b.close(unknown)
        with patch('builtins.__import__', side_effect=AssertionError('unexpected lazy import')), patch.object(
                self.m.ctypes, 'WinDLL', create=True, side_effect=AssertionError('unexpected DLL')):
            for handle in (root, unknown, 999, None, True, 0, -1, self.m._INVALID, 10.0):
                with self.subTest(handle=handle), self.assertRaises(StartupPinError):
                    query(handle)

    def test_security_reader_import_and_constructor_failure_are_fixed(self):
        query = self._security_query()
        root = self.b.open_root('C:')
        module = importlib.import_module('icode.windows_startup_security_native')
        for error in (OSError('private path'), ImportError('private path')):
            with patch('builtins.__import__', side_effect=error), self.assertRaises(StartupPinError) as caught:
                query(root)
            self.assertNotIn('private path', str(caught.exception))
            with patch.object(module, 'WindowsStartupSecurityReader', side_effect=error), self.assertRaises(StartupPinError) as caught:
                query(root)
            self.assertNotIn('private path', str(caught.exception))
        for error in (KeyboardInterrupt(), SystemExit()):
            with patch('builtins.__import__', side_effect=error), self.assertRaises(BaseException) as caught:
                query(root)
            self.assertIs(caught.exception, error)
            with patch.object(module, 'WindowsStartupSecurityReader', side_effect=error), self.assertRaises(BaseException) as caught:
                query(root)
            self.assertIs(caught.exception, error)

    def test_security_query_reader_failures_keep_handle_and_interrupt_identity(self):
        self._security_query()
        module = importlib.import_module('icode.windows_startup_security_native')
        from tests.test_windows_startup_security_native import NativeFixture
        for error in (OSError('private path'), KeyboardInterrupt(), SystemExit()):
            with patch.object(self.m.os, 'name', 'nt'), patch.object(
                    self.m.ctypes, 'WinDLL', side_effect=[self.k, self.n], create=True):
                backend = self.m.WindowsStartupPinBackend()
            fixture = NativeFixture()
            fixture.query_error = error
            reader = fixture.reader(module)
            root = backend.open_root('C:')
            with patch.object(module, 'WindowsStartupSecurityReader', return_value=reader):
                with self.assertRaises(BaseException) as caught:
                    backend.query_security(root)
            if isinstance(error, OSError):
                self.assertIsInstance(caught.exception, StartupPinError)
                self.assertNotIn('private path', str(caught.exception))
            else:
                self.assertIs(caught.exception, error)
            self.assertIn(root, backend._active)
            self.assertEqual(len(fixture.kernel.LocalFree.calls), 1)
            self.assertEqual(self.k.CloseHandle.calls, [])

    def test_security_query_cleanup_unknown_keeps_reader_quarantine(self):
        query = self._security_query()
        module = importlib.import_module('icode.windows_startup_security_native')
        from tests.test_windows_startup_security_native import NativeFixture
        fixture = NativeFixture()
        fixture.free_result = C.addressof(fixture.buffer)
        reader = fixture.reader(module)
        root = self.b.open_root('C:')
        with patch.object(module, 'WindowsStartupSecurityReader', return_value=reader) as factory:
            for _ in range(2):
                with self.assertRaises(StartupPinError):
                    query(root)
            factory.assert_called_once_with()
        self.assertTrue(reader.cleanup_unconfirmed)
        self.assertEqual(len(fixture.advapi.GetSecurityInfo.calls), 1)
        self.assertEqual(len(fixture.kernel.LocalFree.calls), 1)
        self.assertIn(root, self.b._active)

class NativeModuleTests(unittest.TestCase):
    def test_inheritance_shape_check_rejects_equal_or_missing_flags(self):
        import struct
        from icode.windows_startup_security import parse_startup_security
        from tests.test_windows_startup_security_native import descriptor
        check = globals().get('_assert_distinct_inheritance_shapes')
        self.assertTrue(callable(check), 'inheritance shape check must be callable')

        def snapshot(flags):
            # Real parser snapshots from bounded, owned synthetic bytes.
            raw = descriptor()
            owner = raw[20:32]
            ace = struct.pack('<BBHI', 0, flags, 8 + len(owner), 1) + owner
            return parse_startup_security(raw[:32] + struct.pack('<BBHHH', 2, 0, 8 + len(ace), 1, 0) + ace)

        check(self, snapshot(0x13), snapshot(0x10))
        for directory, file in ((0x13, 0x13), (0, 0x10), (0x13, 0)):
            with self.subTest(directory=directory, file=file), self.assertRaises(AssertionError):
                check(self, snapshot(directory), snapshot(file))

    def test_native_backend_exists(self):
        self.assertIsNotNone(importlib.util.find_spec('icode.windows_startup_native'))

    def test_backend_interface_and_platform_gate(self):
        module = importlib.import_module('icode.windows_startup_native')
        self.assertTrue(hasattr(module, 'WindowsStartupPinBackend'))
        if os.name != 'nt':
            from icode.windows_startup_pin import StartupPinError
            with self.assertRaises(StartupPinError):
                module.WindowsStartupPinBackend()


def _assert_distinct_inheritance_shapes(test, directory, file):
    # ACE_HEADER semantics: OBJECT_INHERIT=1, CONTAINER_INHERIT=2,
    # INHERITED=16. Compare all five inheritance bits, independent of SID,
    # ACE order/count, or access masks. Official contract:
    # https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-ace_header
    directory_flags = {entry.flags & 0x1f for entry in directory.entries}
    file_flags = {entry.flags & 0x1f for entry in file.entries}
    test.assertTrue(any(flags & 0x03 for flags in directory_flags),
                    'default directory must retain child inheritance flags')
    test.assertTrue(any(flags & 0x10 for flags in file_flags),
                    'default child file must contain an inherited ACE')
    test.assertNotEqual(directory_flags, file_flags,
                        'directory and child file must expose distinct inheritance shapes')


@unittest.skipUnless(os.name == 'nt', 'Windows security query unavailable on this host')
class WindowsSecurityQueryTests(unittest.TestCase):
    """Actual backend queries on fresh objects, with no host ACL changes.

    Require actual directory/child file flags to show distinct inheritance
    forms; a default fixture lacking them fails without changing host ACLs.
    Unsupported descriptor formats and fixture/API errors fail on Windows.
    The complete fixture HANDLE lifetime runs on one actor.
    """

    def setUp(self):
        import tempfile
        from pathlib import Path
        from icode.windows_startup_native import WindowsStartupPinBackend
        self.tmp = tempfile.TemporaryDirectory(prefix='icode-native-security-')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.directory = self.base / 'ancestor'
        self.directory.mkdir()
        self.file = self.directory / 'startup.py'
        self.content = b'print("security snapshot")\n'
        self.file.write_bytes(self.content)
        self.backend = WindowsStartupPinBackend()
        self.handles = []
        self.addCleanup(self.close_handles)
        handle = self.backend.open_root(self.base.drive)
        self.handles.append(handle)
        for part in self.directory.parts[1:]:
            handle = self.backend.open_child(handle, part, directory=True)
            self.handles.append(handle)
        self.directory_handle = handle
        self.file_handle = self.backend.open_child(handle, self.file.name, directory=False)
        self.handles.append(self.file_handle)

    def close_handles(self):
        # Try every owned close once, even if a preceding close fails.
        errors = []
        while self.handles:
            try:
                self.backend.close(self.handles.pop())
            except BaseException as error:
                errors.append(error)
        if errors:
            raise errors[0]

    def test_file_security_copy_repeated_query_identity_read_and_close(self):
        from icode.windows_startup_security import parse_startup_security
        handle = self.file_handle
        before = self.backend.query(handle)
        raw = self.backend.query_security(handle)
        self.assertIs(type(raw), bytes)
        snapshot = parse_startup_security(raw)
        self.assertEqual(snapshot.raw, raw)
        self.assertEqual(self.backend.query_security(handle), raw)
        self.assertEqual(self.backend.query(handle), before)
        self.assertEqual(self.backend.read(handle, 0, len(self.content)), self.content)
        self.handles.remove(handle)
        self.backend.close(handle)
        with self.assertRaises(StartupPinError):
            self.backend.query_security(handle)
        self.assertEqual(parse_startup_security(raw), snapshot)

    def test_default_directory_and_child_inheritance_descriptors_parse(self):
        from icode.windows_startup_security import parse_startup_security
        snapshots = []
        for handle, directory in ((self.directory_handle, True), (self.file_handle, False)):
            with self.subTest(directory=directory):
                before = self.backend.query(handle)
                raw = self.backend.query_security(handle)
                self.assertIs(type(raw), bytes)
                snapshot = parse_startup_security(raw)
                snapshots.append(snapshot)
                self.assertTrue(snapshot.owner_sid.startswith('S-1-'))
                self.assertEqual(self.backend.query_security(handle), raw)
                self.assertEqual(self.backend.query(handle), before)
                self.assertEqual(before.directory, directory)
        _assert_distinct_inheritance_shapes(self, *snapshots)


@unittest.skipUnless(os.name == 'nt', 'Windows OS enforcement unavailable on this host')
class WindowsEnforcementTests(unittest.TestCase):
    """Each mutation targets only fresh objects created by this test fixture.

    A root share conflict is a test failure (unsupported host), never a reason
    to broaden sharing or claim native success from the portable tests.
    """
    def setUp(self):
        import tempfile
        from pathlib import Path
        self.tmp = tempfile.TemporaryDirectory(prefix='icode-native-pin-')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.parent = self.base / 'ancestor'
        self.parent.mkdir()
        self.file = self.parent / 'startup.py'
        self.file.write_bytes(b'print("held")\n')
        self.k = C.WinDLL('kernel32', use_last_error=True)
        self.k.CreateFileW.argtypes = [C.c_wchar_p, C.c_uint32, C.c_uint32,
                                      C.c_void_p, C.c_uint32, C.c_uint32, C.c_void_p]
        self.k.CreateFileW.restype = C.c_void_p
        self.k.CloseHandle.argtypes = [C.c_void_p]
        self.k.CloseHandle.restype = C.c_int32

    def pin(self, path=None):
        from icode.windows_startup_pin import pin_startup_file
        return pin_startup_file(str(path or self.file))

    def test_native_bytes_hash_and_close_restore_access(self):
        import hashlib
        expected = self.file.read_bytes()
        with self.pin() as owner:
            self.assertEqual(owner.content, expected)
            self.assertEqual(owner.sha256, hashlib.sha256(expected).hexdigest())
            owner.revalidate()
        self.file.write_bytes(b'changed')
        self.file.rename(self.parent / 'after.py')

    def test_held_image_rejects_write_delete_rename(self):
        with self.pin():
            with self.assertRaises(OSError):
                self.file.write_bytes(b'blocked')
            with self.assertRaises(OSError):
                self.file.unlink()
            with self.assertRaises(OSError):
                self.file.rename(self.parent / 'moved.py')

    def test_every_created_ancestor_rename_is_rejected(self):
        with self.pin():
            for ancestor in (self.parent, self.base):
                with self.subTest(ancestor=ancestor.name), self.assertRaises(OSError):
                    ancestor.rename(ancestor.with_name(ancestor.name + '-moved'))

    def test_preexisting_write_and_delete_openers_reject_pin(self):
        for access in (0x40000000, 0x10000):
            handle = self.k.CreateFileW(str(self.file), access, 7, None, 3, 0, None)
            self.assertNotIn(handle, (None, C.c_void_p(-1).value), 'fixture opener unavailable')
            try:
                with self.subTest(access=access), self.assertRaises(StartupPinError):
                    self.pin()
            finally:
                self.assertTrue(self.k.CloseHandle(handle))
        with self.pin():
            pass

    def test_hardlink_rejected(self):
        link = self.parent / 'linked.py'
        os.link(self.file, link)
        with self.assertRaises(StartupPinError):
            self.pin()
        link.unlink()
        with self.pin():
            pass

    def test_junction_ancestor_rejected(self):
        import struct
        junction = self.base / 'junction'
        junction.mkdir()
        # Create a mount-point reparse object without shell execution, elevation
        # or changing ACLs. Insufficient fixture permissions fail visibly.
        target = ('\\??\\' + str(self.parent)).encode('utf-16-le')
        display = str(self.parent).encode('utf-16-le')
        names = target + b'\0\0' + display + b'\0\0'
        data = struct.pack('<IHHHHHH', 0xA0000003, len(names) + 8, 0,
                           0, len(target), len(target) + 2, len(display)) + names
        handle = self.k.CreateFileW(str(junction), 0x40000000, 7, None, 3,
                                    0x02000000 | 0x00200000, None)
        self.assertNotIn(handle, (None, C.c_void_p(-1).value), 'junction fixture open unavailable')
        self.k.DeviceIoControl.argtypes = [C.c_void_p, C.c_uint32, C.c_void_p,
                                          C.c_uint32, C.c_void_p, C.c_uint32,
                                          C.POINTER(C.c_uint32), C.c_void_p]
        self.k.DeviceIoControl.restype = C.c_int32
        actual = C.c_uint32()
        buffer = C.create_string_buffer(data)
        try:
            self.assertTrue(self.k.DeviceIoControl(handle, 0x900A4, buffer, len(data),
                                                  None, 0, C.byref(actual), None),
                            'junction fixture creation unavailable')
        finally:
            self.assertTrue(self.k.CloseHandle(handle))
        try:
            with self.assertRaises(StartupPinError):
                self.pin(junction / self.file.name)
        finally:
            junction.rmdir()
