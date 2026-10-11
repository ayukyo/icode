"""Portable transport/lifetime tests; fake DLLs provide no Windows OS credit."""
import importlib.util
import ctypes
import struct
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from icode.windows_startup_security import StartupSecurityError


def descriptor():
    owner = bytes([1, 1, 0, 0, 0, 0, 0, 5]) + struct.pack('<I', 18)
    return struct.pack('<BBHIIII', 1, 0, 0x8004, 20, 0, 0, 32) + owner + struct.pack('<BBHHH', 2, 0, 8, 0, 0)


class Function:
    def __init__(self, action):
        self.action = action
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        return self.action(*args)


class NativeFixture:
    """Own actual storage for every pointer the tested reader dereferences."""
    def __init__(self):
        self.raw = descriptor()
        self.buffer = ctypes.create_string_buffer(self.raw)
        self.status, self.valid, self.control_ok = 0, 1, 1
        self.control, self.revision, self.length = 0x8004, 1, len(self.raw)
        self.output = True
        self.query_error = self.free_error = None
        self.free_result = None
        self.poison_on_free = False
        self.advapi = SimpleNamespace(
            GetSecurityInfo=Function(self.query),
            IsValidSecurityDescriptor=Function(lambda p: self.valid),
            GetSecurityDescriptorControl=Function(self.receipt),
            GetSecurityDescriptorLength=Function(lambda p: self.length))
        self.kernel = SimpleNamespace(LocalFree=Function(self.free))

    def query(self, *args):
        if self.output:
            ctypes.cast(args[-1], ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.addressof(self.buffer)
        if self.query_error:
            raise self.query_error
        return self.status

    def receipt(self, p, control, revision):
        ctypes.cast(control, ctypes.POINTER(ctypes.c_uint16))[0] = self.control
        ctypes.cast(revision, ctypes.POINTER(ctypes.c_uint32))[0] = self.revision
        return self.control_ok

    def free(self, p):
        if self.poison_on_free:
            ctypes.memset(ctypes.addressof(self.buffer), 0, len(self.raw))
        if self.free_error:
            raise self.free_error
        return self.free_result

    def reader(self, module):
        def load(name, **kwargs):
            return self.advapi if name == 'advapi32' else self.kernel
        with patch.object(module.os, 'name', 'nt'), patch.object(module.ctypes, 'WinDLL', create=True, side_effect=load) as loader:
            reader = module.WindowsStartupSecurityReader()
        self.loader_calls = loader.call_args_list
        return reader


def native_module(test):
    test.assertIsNotNone(importlib.util.find_spec('icode.windows_startup_security_native'))
    import icode.windows_startup_security_native as module
    reader = getattr(module, 'WindowsStartupSecurityReader', None)
    test.assertTrue(callable(reader), 'WindowsStartupSecurityReader must be callable')
    test.assertTrue(callable(getattr(reader, 'read', None)),
                    'WindowsStartupSecurityReader.read must be callable')
    return module


class SecurityReaderTransportTests(unittest.TestCase):
    def setUp(self):
        self.module = native_module(self)
        self.fixture = NativeFixture()
        self.reader = self.fixture.reader(self.module)

    def test_fixed_abi_and_query_arguments(self):
        self.assertEqual(self.reader.read(7), descriptor())
        void = ctypes.c_void_p
        self.assertEqual(self.fixture.advapi.GetSecurityInfo.argtypes,
                         [void, ctypes.c_int32, ctypes.c_uint32] + [ctypes.POINTER(void)] * 5)
        self.assertIs(self.fixture.advapi.GetSecurityInfo.restype, ctypes.c_uint32)
        self.assertEqual(self.fixture.advapi.IsValidSecurityDescriptor.argtypes, [void])
        self.assertIs(self.fixture.advapi.IsValidSecurityDescriptor.restype, ctypes.c_int32)
        self.assertEqual(self.fixture.advapi.GetSecurityDescriptorControl.argtypes,
                         [void, ctypes.POINTER(ctypes.c_uint16), ctypes.POINTER(ctypes.c_uint32)])
        self.assertIs(self.fixture.advapi.GetSecurityDescriptorControl.restype, ctypes.c_int32)
        self.assertEqual(self.fixture.advapi.GetSecurityDescriptorLength.argtypes, [void])
        self.assertIs(self.fixture.advapi.GetSecurityDescriptorLength.restype, ctypes.c_uint32)
        self.assertEqual(self.fixture.kernel.LocalFree.argtypes, [void])
        self.assertIs(self.fixture.kernel.LocalFree.restype, void)
        args = self.fixture.advapi.GetSecurityInfo.calls[0]
        self.assertEqual(args[:7], (7, 1, 5, None, None, None, None))
        self.assertEqual([call.args[0] for call in self.fixture.loader_calls], ['advapi32', 'kernel32'])
        self.assertTrue(all(call.kwargs == {'use_last_error': True} for call in self.fixture.loader_calls))
        self.assertEqual(len(self.fixture.kernel.LocalFree.calls), 1)

    def test_handles_require_exact_positive_pointer_width_integer(self):
        maximum = (1 << (8 * ctypes.sizeof(ctypes.c_void_p))) - 1
        for value in (None, True, 0, -1, maximum, maximum + 1, 1.0, ctypes.c_void_p(7)):
            with self.subTest(value=value), self.assertRaises(StartupSecurityError):
                self.reader.read(value)
        self.assertEqual(self.fixture.advapi.GetSecurityInfo.calls, [])
        self.assertEqual(self.reader.read(maximum - 1), descriptor())

    def test_validation_gates_free_once_without_unsafe_reads(self):
        cases = [('status', 5), ('status', True), ('valid', 0), ('control_ok', 0),
                 ('revision', 2), ('control', 4), ('length', 19), ('length', 131073),
                 ('length', True), ('length', 40.0), ('control', 0x9004)]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                fixture = NativeFixture()
                setattr(fixture, field, value)
                reader = fixture.reader(self.module)
                with self.assertRaises(StartupSecurityError):
                    reader.read(7)
                self.assertEqual(len(fixture.kernel.LocalFree.calls), 1)

    def test_null_output_never_freed(self):
        self.fixture.output = False
        with self.assertRaises(StartupSecurityError):
            self.reader.read(7)
        self.assertEqual(self.fixture.kernel.LocalFree.calls, [])

    def test_query_exception_without_output_never_frees(self):
        self.fixture.output = False
        self.fixture.query_error = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt) as caught:
            self.reader.read(7)
        self.assertIs(caught.exception, self.fixture.query_error)
        self.assertEqual(self.fixture.kernel.LocalFree.calls, [])

    def test_native_gate_errors_free_once_and_preserve_interrupt_identity(self):
        for name in ('IsValidSecurityDescriptor', 'GetSecurityDescriptorControl',
                     'GetSecurityDescriptorLength'):
            for error in (OSError('private path'), KeyboardInterrupt(), SystemExit()):
                with self.subTest(api=name, error=type(error)):
                    fixture = NativeFixture()
                    reader = fixture.reader(self.module)
                    def fail(*args):
                        raise error
                    getattr(fixture.advapi, name).action = fail
                    with self.assertRaises(BaseException) as caught:
                        reader.read(7)
                    if isinstance(error, (KeyboardInterrupt, SystemExit)):
                        self.assertIs(caught.exception, error)
                    else:
                        self.assertIsInstance(caught.exception, StartupSecurityError)
                        self.assertNotIn('private path', str(caught.exception))
                    self.assertEqual(len(fixture.kernel.LocalFree.calls), 1)

    def test_parser_error_identity_has_fixed_cleanup_note(self):
        error = StartupSecurityError('parser refusal')
        self.fixture.free_result = ctypes.addressof(self.fixture.buffer)
        with patch.object(self.module, 'parse_startup_security', side_effect=error):
            with self.assertRaises(StartupSecurityError) as caught:
                self.reader.read(7)
        self.assertIs(caught.exception, error)
        self.assertEqual(error.__notes__, ['Startup security descriptor cleanup unconfirmed'])
        self.assertEqual(len(self.fixture.kernel.LocalFree.calls), 1)

    def test_parser_refusal_and_receipt_mismatch_free_once(self):
        for offset, value in ((0, 2), (1, 1), (20, 2)):
            with self.subTest(offset=offset):
                fixture = NativeFixture()
                fixture.buffer[offset] = bytes([value])
                with self.assertRaises(StartupSecurityError):
                    fixture.reader(self.module).read(7)
                self.assertEqual(len(fixture.kernel.LocalFree.calls), 1)

    def test_owned_copy_survives_free_and_has_no_view(self):
        self.fixture.poison_on_free = True
        value = self.reader.read(7)
        self.assertIs(type(value), bytes)
        self.assertEqual(value, descriptor())
        self.assertNotEqual(self.fixture.buffer.raw[:len(value)], value)

    def test_query_output_then_error_always_freed_preserving_interrupts(self):
        for error in (OSError('private path'), KeyboardInterrupt(), SystemExit(3)):
            with self.subTest(error=type(error)):
                fixture = NativeFixture()
                fixture.query_error = error
                reader = fixture.reader(self.module)
                with self.assertRaises(BaseException) as caught:
                    reader.read(7)
                if isinstance(error, (KeyboardInterrupt, SystemExit)):
                    self.assertIs(caught.exception, error)
                else:
                    self.assertIsInstance(caught.exception, StartupSecurityError)
                    self.assertNotIn('private path', str(caught.exception))
                self.assertEqual(len(fixture.kernel.LocalFree.calls), 1)

    def test_cleanup_unknown_quarantines_without_retry_or_further_api(self):
        for error in (None, OSError('secret'), KeyboardInterrupt(), SystemExit()):
            with self.subTest(error=type(error)):
                fixture = NativeFixture()
                fixture.free_error = error
                fixture.free_result = ctypes.addressof(fixture.buffer)
                fixture.poison_on_free = True
                reader = fixture.reader(self.module)
                with self.assertRaises(BaseException) as caught:
                    reader.read(7)
                if isinstance(error, (KeyboardInterrupt, SystemExit)):
                    self.assertIs(caught.exception, error)
                else:
                    self.assertIsInstance(caught.exception, StartupSecurityError)
                with self.assertRaises(StartupSecurityError):
                    reader.read(7)
                self.assertTrue(reader.cleanup_unconfirmed)
                self.assertEqual(len(fixture.kernel.LocalFree.calls), 1)
                self.assertEqual(len(fixture.advapi.GetSecurityInfo.calls), 1)

    def test_body_error_priority_with_guarded_notes(self):
        class HostileInterrupt(KeyboardInterrupt):
            def __getattribute__(self, name):
                if name == '__notes__':
                    raise SystemExit('hostile')
                return super().__getattribute__(name)
        for error in (KeyboardInterrupt(), SystemExit(), HostileInterrupt()):
            with self.subTest(error=type(error)):
                fixture = NativeFixture()
                fixture.query_error = error
                fixture.free_error = OSError('secret')
                reader = fixture.reader(self.module)
                with self.assertRaises(BaseException) as caught:
                    reader.read(7)
                self.assertIs(caught.exception, error)
                self.assertTrue(reader.cleanup_unconfirmed)
                self.assertEqual(len(fixture.kernel.LocalFree.calls), 1)

    def test_after_copy_interrupt_frees_once(self):
        error = KeyboardInterrupt()
        with patch.object(self.module, 'parse_startup_security', side_effect=error):
            with self.assertRaises(KeyboardInterrupt) as caught:
                self.reader.read(7)
        self.assertIs(caught.exception, error)
        self.assertEqual(len(self.fixture.kernel.LocalFree.calls), 1)

    def test_copy_failure_uses_fixed_error_and_frees(self):
        with patch.object(self.module.ctypes, 'string_at', side_effect=OSError('private path')):
            with self.assertRaises(BaseException) as caught:
                self.reader.read(7)
        self.assertIsInstance(caught.exception, StartupSecurityError)
        self.assertNotIn('private path', str(caught.exception))
        self.assertEqual(len(self.fixture.kernel.LocalFree.calls), 1)

    def test_internal_byte_budget_accepts_boundary_with_real_storage(self):
        self.fixture.raw += bytes(128 * 1024 - len(self.fixture.raw))
        self.fixture.buffer = ctypes.create_string_buffer(self.fixture.raw)
        self.fixture.length = len(self.fixture.raw)
        self.assertEqual(self.reader.read(7), self.fixture.raw)

    def test_return_side_line_interrupt_never_frees_twice(self):
        error = KeyboardInterrupt()
        def trace(frame, event, argument):
            if (frame.f_code is self.reader.read.__func__.__code__ and event == 'line'
                    and len(self.fixture.kernel.LocalFree.calls) == 1):
                raise error
            return trace
        previous = sys.gettrace()
        try:
            sys.settrace(trace)
            with self.assertRaises(KeyboardInterrupt) as caught:
                self.reader.read(7)
        finally:
            sys.settrace(previous)
        self.assertIs(caught.exception, error)
        self.assertFalse(self.reader.cleanup_unconfirmed)
        self.assertEqual(len(self.fixture.kernel.LocalFree.calls), 1)


class SecurityReaderConstructorTests(unittest.TestCase):
    def test_nonwindows_and_loader_failures_are_fixed(self):
        module = native_module(self)
        with patch.object(module.os, 'name', 'posix'), self.assertRaises(StartupSecurityError):
            module.WindowsStartupSecurityReader()
        for error in (OSError('secret'), AttributeError('secret')):
            with patch.object(module.os, 'name', 'nt'), patch.object(module.ctypes, 'WinDLL', create=True, side_effect=error):
                with self.assertRaises(StartupSecurityError) as caught:
                    module.WindowsStartupSecurityReader()
                self.assertNotIn('secret', str(caught.exception))

    def test_missing_api_and_constructor_interrupt(self):
        module = native_module(self)
        with patch.object(module.os, 'name', 'nt'), patch.object(module.ctypes, 'WinDLL', create=True, return_value=SimpleNamespace()):
            with self.assertRaises(StartupSecurityError):
                module.WindowsStartupSecurityReader()
        for error in (KeyboardInterrupt(), SystemExit()):
            with patch.object(module.os, 'name', 'nt'), patch.object(module.ctypes, 'WinDLL', create=True, side_effect=error):
                with self.assertRaises(BaseException) as caught:
                    module.WindowsStartupSecurityReader()
                self.assertIs(caught.exception, error)


class SecurityReaderInterfaceTests(unittest.TestCase):
    def test_native_security_reader_module_exists(self):
        self.assertIsNotNone(importlib.util.find_spec('icode.windows_startup_security_native'))

    def test_native_security_reader_class_and_read_are_callable(self):
        native_module(self)
