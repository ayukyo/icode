"""Portable host identity contracts; fake DLLs do not provide native credit."""
import importlib.util
import ctypes
import inspect
import os
import re
import struct
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from icode.windows_startup_security import StartupSecurityError


class TokenUser(ctypes.Structure):
    _fields_ = [('Sid', ctypes.c_void_p), ('Attributes', ctypes.c_uint32)]


class Function:
    def __init__(self, action):
        self.action = action
        self.calls = []

    def __call__(self, *arguments):
        self.calls.append(arguments)
        return self.action(*arguments)


class TokenFixture:
    """Only write and copy buffers allocated by the code under test."""
    def __init__(self):
        self.header = ctypes.sizeof(TokenUser)
        self.sid = bytes([1, 1, 0, 0, 0, 0, 0, 5]) + struct.pack('<I', 18)
        self.offset = self.header
        self.capacity = self.header + 12
        self.returned = self.capacity
        self.token = 31
        self.process = ctypes.c_void_p(-1).value
        self.open_result = 1
        self.open_error = self.process_error = None
        self.sizing_result = 0
        self.last_error = 122
        self.second_result = 1
        self.query_error = None
        self.query_error_stage = 2
        self.close_result = 1
        self.close_error = None
        self.closed = []
        self.attributes = 0
        self.pointer = None
        self.poison_on_close = False
        self.buffer_address = None
        self.kernel = SimpleNamespace(
            GetCurrentProcess=Function(self.current_process),
            CloseHandle=Function(self.close))
        self.advapi = SimpleNamespace(
            OpenProcessToken=Function(self.open),
            GetTokenInformation=Function(self.query))

    def current_process(self):
        if self.process_error is not None:
            raise self.process_error
        return self.process

    def open(self, process, access, output):
        ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p))[0] = self.token
        if self.open_error is not None:
            raise self.open_error
        return self.open_result

    def query(self, token, kind, buffer, capacity, output):
        stage = 1 if buffer is None else 2
        ctypes.cast(output, ctypes.POINTER(ctypes.c_uint32))[0] = (
            self.capacity if stage == 1 else self.returned)
        if stage == 2:
            # These addresses originate from the tested allocation, never a SID
            # pointer or arbitrary fixture integer. Pointer mutations stay data.
            self.buffer_address = ctypes.addressof(buffer)
            ctypes.memset(self.buffer_address, 0xA5, capacity)
            pointer = self.buffer_address + self.offset if self.pointer is None else self.pointer
            header = TokenUser(pointer, self.attributes)
            ctypes.memmove(self.buffer_address, ctypes.byref(header), min(self.header, capacity))
            padding_start = TokenUser.Attributes.offset + ctypes.sizeof(ctypes.c_uint32)
            if self.header > padding_start:
                ctypes.memset(self.buffer_address + padding_start, 0xA5, self.header - padding_start)
            if 0 <= self.offset <= capacity and len(self.sid) <= capacity - self.offset:
                ctypes.memmove(self.buffer_address + self.offset, self.sid, len(self.sid))
        if self.query_error is not None and stage == self.query_error_stage:
            raise self.query_error
        return self.sizing_result if stage == 1 else self.second_result

    def close(self, token):
        self.closed.append(token)
        if self.poison_on_close and self.buffer_address is not None:
            # Retain the actual buffer before testing post-copy mutation.
            buffer = self.advapi.GetTokenInformation.calls[-1][2]
            ctypes.memset(ctypes.addressof(buffer), 0, len(buffer))
        if self.close_error is not None:
            raise self.close_error
        return self.close_result

    def identity(self, module):
        def load(name, **kwargs):
            return {'kernel32': self.kernel, 'advapi32': self.advapi}[name]
        with patch.object(module.os, 'name', 'nt'), patch.object(
                module.ctypes, 'WinDLL', create=True, side_effect=load) as loader:
            identity = module.WindowsStartupHostIdentity()
        self.loads = loader.call_args_list
        return identity


def identity_module(test):
    test.assertIsNotNone(importlib.util.find_spec('icode.windows_startup_host_identity'))
    import icode.windows_startup_host_identity as module
    test.assertTrue(hasattr(module, 'ctypes'), 'native transport must use ctypes')
    return module


class HostIdentityConstructorTests(unittest.TestCase):
    def setUp(self):
        self.module = identity_module(self)

    def test_non_windows_rejected_without_loading(self):
        with patch.object(self.module.os, 'name', 'posix'), patch.object(
                self.module.ctypes, 'WinDLL', create=True) as loader:
            with self.assertRaises(StartupSecurityError):
                self.module.WindowsStartupHostIdentity()
            loader.assert_not_called()

    def test_missing_each_api_rejected(self):
        for dll, name in [('kernel', 'GetCurrentProcess'), ('kernel', 'CloseHandle'),
                          ('advapi', 'OpenProcessToken'), ('advapi', 'GetTokenInformation')]:
            with self.subTest(api=name):
                fixture = TokenFixture()
                delattr(getattr(fixture, dll), name)
                with self.assertRaises(StartupSecurityError):
                    fixture.identity(self.module)

    def test_loading_ordinary_exception_redacted(self):
        with patch.object(self.module.os, 'name', 'nt'), patch.object(
                self.module.ctypes, 'WinDLL', create=True, side_effect=OSError('private-path')):
            with self.assertRaises(StartupSecurityError) as caught:
                self.module.WindowsStartupHostIdentity()
        self.assertNotIn('private-path', str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)

    def test_loading_interrupts_preserve_identity(self):
        for error in (KeyboardInterrupt('private-path'), SystemExit('private-path')):
            with self.subTest(error=type(error).__name__), patch.object(self.module.os, 'name', 'nt'), patch.object(
                    self.module.ctypes, 'WinDLL', create=True, side_effect=error):
                with self.assertRaises(type(error)) as caught:
                    self.module.WindowsStartupHostIdentity()
                self.assertIs(caught.exception, error)


class HostIdentityTransportTests(unittest.TestCase):
    def setUp(self):
        self.module = identity_module(self)
        self.fixture = TokenFixture()
        self.identity = self.fixture.identity(self.module)

    def capture(self):
        with patch.object(self.module.ctypes, 'get_last_error', create=True,
                          side_effect=lambda: self.fixture.last_error):
            return self.identity.capture()

    def assert_rejected(self, closes=1):
        with self.assertRaises(StartupSecurityError) as caught:
            self.capture()
        self.assertNotIn('private-path', str(caught.exception))
        self.assertEqual(len(self.fixture.closed), closes)
        return caught.exception

    def test_fixed_dlls_abi_and_current_primary_token(self):
        try:
            result = self.capture()
        except NotImplementedError:
            self.fail('capture must query and return the current primary token SID')
        self.assertEqual(result, 'S-1-5-18')
        self.assertEqual(set((call.args[0], tuple(call.kwargs.items())) for call in self.fixture.loads),
                         {('kernel32', (('use_last_error', True),)), ('advapi32', (('use_last_error', True),))})
        signatures = [(self.fixture.kernel.GetCurrentProcess, [], ctypes.c_void_p),
                      (self.fixture.kernel.CloseHandle, [ctypes.c_void_p], ctypes.c_int32),
                      (self.fixture.advapi.OpenProcessToken,
                       [ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)], ctypes.c_int32),
                      (self.fixture.advapi.GetTokenInformation,
                       [ctypes.c_void_p, ctypes.c_int32, ctypes.c_void_p, ctypes.c_uint32,
                        ctypes.POINTER(ctypes.c_uint32)], ctypes.c_int32)]
        for function, arguments, result in signatures:
            self.assertEqual(function.argtypes, arguments)
            self.assertIs(function.restype, result)
        self.assertEqual(self.fixture.kernel.GetCurrentProcess.calls, [()])
        self.assertEqual(self.fixture.advapi.OpenProcessToken.calls[0][:2], (self.fixture.process, 8))
        queries = self.fixture.advapi.GetTokenInformation.calls
        self.assertEqual(queries[0][:4], (31, 1, None, 0))
        self.assertEqual(queries[1][:2], (31, 1))
        self.assertEqual(queries[1][3], self.fixture.capacity)
        self.assertEqual(self.fixture.closed, [31])
        self.assertFalse(self.identity.cleanup_unconfirmed)
        self.assertEqual(list(inspect.signature(self.identity.capture).parameters), [])

    def test_native_pointer_alignment(self):
        header = self.module._TokenUser
        self.assertEqual(header.Sid.offset, 0)
        self.assertEqual(header.Attributes.offset, ctypes.sizeof(ctypes.c_void_p))
        self.assertEqual(ctypes.sizeof(header), ctypes.sizeof(TokenUser))
        self.assertNotIn('_pack_', header.__dict__)

    def test_attributes_padding_gap_and_smaller_returned_are_legal(self):
        self.fixture.attributes = 0xFFFFFFFF
        self.fixture.offset = self.fixture.header + 7
        self.fixture.returned = self.fixture.offset + len(self.fixture.sid)
        self.fixture.capacity = self.fixture.returned + 13
        self.assertEqual(self.capture(), 'S-1-5-18')
        self.assertEqual(self.fixture.closed, [31])

    def test_copy_is_owned_before_close(self):
        self.fixture.poison_on_close = True
        self.assertEqual(self.capture(), 'S-1-5-18')

    def test_parser_receives_owned_exact_returned_bytes(self):
        self.fixture.capacity += 17
        parser = self.module._sid
        with patch.object(self.module, '_sid', wraps=parser) as called:
            self.assertEqual(self.capture(), 'S-1-5-18')
        raw, offset, limit = called.call_args.args
        self.assertIs(type(raw), bytes)
        self.assertEqual(len(raw), self.fixture.returned)
        self.assertEqual((offset, limit), (self.fixture.header, self.fixture.returned))

    def test_copy_faults_are_redacted_or_preserve_interrupt_identity(self):
        for error in (MemoryError('private-copy'), KeyboardInterrupt('private-copy'), SystemExit('private-copy')):
            with self.subTest(error=type(error).__name__):
                self.setUp()
                capacity = self.fixture.capacity

                class FaultyBuffer(ctypes.c_char * capacity):
                    def __getattribute__(self, name):
                        if name == 'raw':
                            raise error
                        return super().__getattribute__(name)

                with patch.object(self.module.ctypes, 'create_string_buffer', side_effect=lambda size: FaultyBuffer()):
                    if isinstance(error, Exception):
                        with self.assertRaises(StartupSecurityError) as caught:
                            self.capture()
                        self.assertNotIn('private-copy', str(caught.exception))
                        self.assertTrue(caught.exception.__suppress_context__)
                    else:
                        with self.assertRaises(type(error)) as caught:
                            self.capture()
                        self.assertIs(caught.exception, error)
                self.assertEqual(self.fixture.closed, [31])

    def test_bounded_copy_and_return_line_interrupts_close_once(self):
        # This checks exactly the named Python line events, not arbitrary
        # asynchronous bytecode windows. Trace is always restored in finally.
        source, start = inspect.getsourcelines(self.module.WindowsStartupHostIdentity.capture)
        for marker in ('raw = buffer.raw', 'return sid'):
            line = next(start + index for index, text in enumerate(source) if marker in text)
            for error in (KeyboardInterrupt('private-line'), SystemExit('private-line')):
                with self.subTest(marker=marker, error=type(error).__name__):
                    self.setUp()
                    fired = []

                    def trace(frame, event, argument):
                        if event == 'line' and frame.f_code is self.module.WindowsStartupHostIdentity.capture.__code__ and frame.f_lineno == line:
                            fired.append(True)
                            raise error
                        return trace

                    previous = sys.gettrace()
                    try:
                        sys.settrace(trace)
                        with self.assertRaises(type(error)) as caught:
                            self.capture()
                    finally:
                        sys.settrace(previous)
                    self.assertIs(caught.exception, error)
                    self.assertEqual(fired, [True])
                    self.assertEqual(self.fixture.closed, [31])
                    self.assertFalse(self.identity.cleanup_unconfirmed)

    def test_success_repeat_acquires_independent_tokens(self):
        self.assertEqual(self.capture(), 'S-1-5-18')
        self.fixture.token = 32
        self.assertEqual(self.capture(), 'S-1-5-18')
        self.assertEqual(self.fixture.closed, [31, 32])

    def test_open_null_and_invalid_never_closed(self):
        for token in (0, ctypes.c_void_p(-1).value):
            with self.subTest(token_shape='null' if not token else 'invalid'):
                self.setUp()
                self.fixture.token = token
                self.assert_rejected(0)
                self.assertEqual(self.fixture.advapi.GetTokenInformation.calls, [])

    def test_open_false_with_owned_output_closes(self):
        self.fixture.open_result = 0
        self.assert_rejected()

    def test_open_false_without_owned_output_never_closes(self):
        self.fixture.token = 0
        self.fixture.open_result = 0
        self.assert_rejected(0)

    def test_output_before_ordinary_open_error_closes_and_redacts(self):
        self.fixture.open_error = OSError('private-path')
        error = self.assert_rejected()
        self.assertTrue(error.__suppress_context__)

    def test_output_before_open_interrupts_closes_and_preserves(self):
        for error in (KeyboardInterrupt('private-path'), SystemExit('private-path')):
            with self.subTest(error=type(error).__name__):
                self.setUp()
                self.fixture.open_error = error
                with self.assertRaises(type(error)) as caught:
                    self.capture()
                self.assertIs(caught.exception, error)
                self.assertEqual(self.fixture.closed, [31])

    def test_open_errors_with_null_or_invalid_output_never_close(self):
        for token in (0, ctypes.c_void_p(-1).value):
            for error in (OSError('private-path'), KeyboardInterrupt('private-path'), SystemExit('private-path')):
                with self.subTest(output='null' if not token else 'invalid', error=type(error).__name__):
                    self.setUp()
                    self.fixture.token, self.fixture.open_error = token, error
                    if isinstance(error, Exception):
                        self.assert_rejected(0)
                    else:
                        with self.assertRaises(type(error)) as caught:
                            self.capture()
                        self.assertIs(caught.exception, error)
                        self.assertEqual(self.fixture.closed, [])

    def test_process_api_error_has_no_owned_token(self):
        self.fixture.process_error = OSError('private-path')
        self.assert_rejected(0)
        self.assertEqual(self.fixture.advapi.OpenProcessToken.calls, [])

    def test_sizing_requires_false_and_immediate_insufficient_buffer(self):
        for result, last_error in ((1, 122), (0, 0), (0, 5)):
            with self.subTest(result=result, last_error=last_error):
                self.setUp()
                self.fixture.sizing_result, self.fixture.last_error = result, last_error
                self.assert_rejected()
                self.assertEqual(len(self.fixture.advapi.GetTokenInformation.calls), 1)

    def test_last_error_read_before_allocation_and_second_query(self):
        events = []
        original_query = self.fixture.query
        original_allocate = self.module.ctypes.create_string_buffer

        def query(*args):
            events.append('sizing' if args[2] is None else 'query')
            return original_query(*args)

        def last_error():
            events.append('last_error')
            return 122

        def allocate(size):
            events.append('allocate')
            return original_allocate(size)

        self.fixture.advapi.GetTokenInformation.action = query
        with patch.object(self.module.ctypes, 'get_last_error', create=True, side_effect=last_error), patch.object(
                self.module.ctypes, 'create_string_buffer', side_effect=allocate):
            self.assertEqual(self.identity.capture(), 'S-1-5-18')
        self.assertEqual(events, ['sizing', 'last_error', 'allocate', 'query'])

    def test_sizing_small_and_over_budget_rejected(self):
        for capacity in (0, self.fixture.header + 7, 4097):
            with self.subTest(capacity=capacity):
                self.setUp()
                self.fixture.capacity = capacity
                self.assert_rejected()
                self.assertEqual(len(self.fixture.advapi.GetTokenInformation.calls), 1)

    def test_budget_upper_bound_accepted(self):
        self.fixture.capacity = 4096
        self.assertEqual(self.capture(), 'S-1-5-18')

    def test_second_query_requires_success(self):
        self.fixture.second_result = 0
        self.assert_rejected()
        self.assertEqual(len(self.fixture.advapi.GetTokenInformation.calls), 2)

    def test_second_returned_window_bounds(self):
        for returned in (0, self.fixture.header + 7, self.fixture.capacity + 1):
            with self.subTest(returned=returned):
                self.setUp()
                self.fixture.returned = returned
                self.assert_rejected()
                self.assertEqual(len(self.fixture.advapi.GetTokenInformation.calls), 2)

    def test_sid_pointer_null_low_header_tail_and_outside_rejected(self):
        for shape in ('null', 'low', 'header', 'tail', 'outside'):
            with self.subTest(shape=shape):
                self.setUp()
                if shape == 'null':
                    self.fixture.pointer = 0
                elif shape == 'low':
                    self.fixture.pointer = 1
                else:
                    original = self.fixture.query

                    def query(*args, shape=shape):
                        result = original(*args)
                        if args[2] is not None:
                            offset = {'header': self.fixture.header - 1,
                                      'tail': self.fixture.returned - 7,
                                      'outside': self.fixture.returned + 1}[shape]
                            header = TokenUser(self.fixture.buffer_address + offset, 0)
                            ctypes.memmove(self.fixture.buffer_address, ctypes.byref(header), self.fixture.header)
                        return result

                    self.fixture.advapi.GetTokenInformation.action = query
                self.assert_rejected()

    def test_sid_revision_count_and_truncated_body_rejected(self):
        for shape in ('revision', 'count', 'body'):
            with self.subTest(shape=shape):
                self.setUp()
                if shape == 'revision':
                    self.fixture.sid = bytes([2]) + self.fixture.sid[1:]
                elif shape == 'count':
                    self.fixture.sid = bytes([1, 16]) + self.fixture.sid[2:]
                else:
                    self.fixture.returned -= 1
                self.assert_rejected()

    def test_sid_subauthority_extremes_and_zero_count(self):
        for count, authority, values in ((0, 0, ()), (15, (1 << 48) - 1, (0xFFFFFFFF,) * 15)):
            with self.subTest(count=count):
                self.setUp()
                self.fixture.sid = bytes([1, count]) + authority.to_bytes(6, 'big') + struct.pack(f'<{count}I', *values)
                self.fixture.capacity = self.fixture.returned = self.fixture.header + len(self.fixture.sid)
                expected = 'S-1-' + str(authority) + ''.join('-' + str(value) for value in values)
                self.assertEqual(self.capture(), expected)

    def test_query_errors_and_interrupts_release_once(self):
        for stage in (1, 2):
            for error in (OSError('private-path'), KeyboardInterrupt('private-path'), SystemExit('private-path')):
                with self.subTest(stage=stage, error=type(error).__name__):
                    self.setUp()
                    self.fixture.query_error_stage, self.fixture.query_error = stage, error
                    if isinstance(error, Exception):
                        self.assert_rejected()
                    else:
                        with self.assertRaises(type(error)) as caught:
                            self.capture()
                        self.assertIs(caught.exception, error)
                        self.assertEqual(self.fixture.closed, [31])

    def test_allocation_parser_and_structure_errors_are_redacted_and_released(self):
        for target in ('create_string_buffer', 'from_buffer_copy', '_sid'):
            with self.subTest(target=target):
                self.setUp()
                owner = (self.module.ctypes if target == 'create_string_buffer'
                         else self.module._TokenUser if target == 'from_buffer_copy' else self.module)
                with patch.object(owner, target, side_effect=ValueError('private-path')):
                    error = self.assert_rejected()
                self.assertTrue(error.__suppress_context__)

    def test_close_nonzero_is_confirmation(self):
        self.fixture.close_result = -1
        self.assertEqual(self.capture(), 'S-1-5-18')
        self.assertFalse(self.identity.cleanup_unconfirmed)

    def test_close_zero_or_exception_quarantines_without_retry(self):
        for error in (None, OSError('private-path'), KeyboardInterrupt('private-path'), SystemExit('private-path')):
            with self.subTest(error=type(error).__name__):
                self.setUp()
                self.fixture.close_result = 0
                self.fixture.close_error = error
                expected = type(error) if error is not None and not isinstance(error, Exception) else StartupSecurityError
                with self.assertRaises(expected) as caught:
                    self.capture()
                if expected is not StartupSecurityError:
                    self.assertIs(caught.exception, error)
                else:
                    self.assertNotIn('private-path', str(caught.exception))
                self.assertTrue(self.identity.cleanup_unconfirmed)
                before = (len(self.fixture.kernel.GetCurrentProcess.calls), len(self.fixture.advapi.OpenProcessToken.calls),
                          len(self.fixture.advapi.GetTokenInformation.calls))
                for _ in range(3):
                    self.assert_rejected()
                    self.assertEqual(before, (len(self.fixture.kernel.GetCurrentProcess.calls),
                                             len(self.fixture.advapi.OpenProcessToken.calls),
                                             len(self.fixture.advapi.GetTokenInformation.calls)))

    def test_close_after_recorded_closed_then_raise_stays_unknown(self):
        # The fixture records closure before throwing, simulating the fault
        # window where a caller cannot recover ownership from the exception.
        error = KeyboardInterrupt('private-after-close')
        self.fixture.close_error = error
        with self.assertRaises(KeyboardInterrupt) as caught:
            self.capture()
        self.assertIs(caught.exception, error)
        self.assertEqual(self.fixture.closed, [31])
        self.assertTrue(self.identity.cleanup_unconfirmed)
        self.assert_rejected()

    def test_ordinary_body_error_and_failed_cleanup_only_expose_fixed_text(self):
        self.fixture.open_error = OSError('private-body')
        self.fixture.close_error = OSError('private-close')
        error = self.assert_rejected()
        self.assertEqual(str(error), 'startup host identity capture failed')
        self.assertEqual(error.__notes__, ['Startup host identity cleanup unconfirmed'])
        self.assertTrue(error.__suppress_context__)
        self.assertTrue(self.identity.cleanup_unconfirmed)

    def test_body_error_preserved_when_close_fails(self):
        for original in (KeyboardInterrupt('private-body'), SystemExit('private-body')):
            for cleanup in (OSError('private-close'), KeyboardInterrupt(), SystemExit()):
                with self.subTest(body=type(original).__name__, cleanup=type(cleanup).__name__):
                    self.setUp()
                    self.fixture.open_error, self.fixture.close_error = original, cleanup
                    with self.assertRaises(type(original)) as caught:
                        self.capture()
                    self.assertIs(caught.exception, original)
                    self.assertEqual(original.__notes__[-1], 'Startup host identity cleanup unconfirmed')
                    self.assertTrue(self.identity.cleanup_unconfirmed)
                    self.assertEqual(self.fixture.closed, [31])

    def test_hostile_notes_cannot_replace_original_interrupt(self):
        for kind in (KeyboardInterrupt, SystemExit):
            class Hostile(kind):
                def __getattribute__(self, name):
                    if name == '__notes__':
                        raise RuntimeError('private-note')
                    return super().__getattribute__(name)

            with self.subTest(kind=kind.__name__):
                self.setUp()
                original = Hostile('private-body')
                self.fixture.open_error = original
                self.fixture.close_result = 0
                with self.assertRaises(kind) as caught:
                    self.capture()
                self.assertIs(caught.exception, original)
                self.assertEqual(self.fixture.closed, [31])


class HostIdentityInterfaceTests(unittest.TestCase):
    def test_module_and_capture_exist(self):
        self.assertIsNotNone(importlib.util.find_spec('icode.windows_startup_host_identity'))
        import icode.windows_startup_host_identity as module
        identity = getattr(module, 'WindowsStartupHostIdentity', None)
        self.assertTrue(callable(identity))
        self.assertTrue(callable(getattr(identity, 'capture', None)))


@unittest.skipUnless(os.name == 'nt', 'Windows native identity required')
class WindowsHostIdentityTests(unittest.TestCase):
    """Real current primary token and an independent OS SID string oracle.

    Only TOKEN_QUERY is requested. No token or ACL is modified, and private
    SID/handle values never enter assertion messages or exception diagnostics.
    """

    def test_token_user_abi_matches_native_64_bit_layout(self):
        module = identity_module(self)
        self.assertEqual(ctypes.sizeof(ctypes.c_void_p), 8)
        for header in (module._TokenUser, TokenUser):
            self.assertEqual(header.Sid.offset, 0)
            self.assertEqual(header.Attributes.offset, 8)
            self.assertEqual(ctypes.sizeof(header), 16)
            self.assertNotIn('_pack_', header.__dict__)

    def independent_os_sid(self):
        # Fixed DLLs and independent signatures: never use the product's
        # transport, SID parser, token structure, or returned SID as the oracle.
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        advapi = ctypes.WinDLL('advapi32', use_last_error=True)
        void, u32, i32 = ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int32
        for function, arguments, result in (
                (kernel.GetCurrentProcess, [], void),
                (advapi.OpenProcessToken, [void, u32, ctypes.POINTER(void)], i32),
                (advapi.GetTokenInformation,
                 [void, i32, void, u32, ctypes.POINTER(u32)], i32),
                (advapi.IsValidSid, [void], i32),
                (advapi.ConvertSidToStringSidW, [void, ctypes.POINTER(void)], i32),
                (kernel.LocalFree, [void], void),
                (kernel.CloseHandle, [void], i32)):
            function.argtypes, function.restype = arguments, result
        token, text = void(), void()
        # Protect acquisition itself: both APIs may write owned output before
        # an unsuccessful return. Each owned resource is released once only.
        try:
            process = kernel.GetCurrentProcess()
            opened = advapi.OpenProcessToken(process, 8, ctypes.byref(token))
            self.assertTrue(bool(opened), 'independent token acquisition failed')
            self.assertTrue(token.value is not None and token.value != void(-1).value,
                            'independent token handle unavailable')
            required = u32()
            sized = advapi.GetTokenInformation(token.value, 1, None, 0, ctypes.byref(required))
            error = ctypes.get_last_error()
            minimum = ctypes.sizeof(TokenUser) + 8
            self.assertTrue(not sized and error == 122, 'independent token sizing failed')
            self.assertTrue(minimum <= required.value <= 4096, 'independent token size invalid')
            capacity = required.value
            buffer = ctypes.create_string_buffer(capacity)
            returned = u32()
            queried = advapi.GetTokenInformation(
                token.value, 1, buffer, capacity, ctypes.byref(returned))
            self.assertTrue(bool(queried), 'independent token query failed')
            self.assertTrue(minimum <= returned.value <= capacity, 'independent return window invalid')
            raw = buffer.raw[:returned.value]
            pointer = TokenUser.from_buffer_copy(raw).Sid
            self.assertTrue(pointer is not None, 'independent SID missing')
            offset = pointer - ctypes.addressof(buffer)
            # Prove header and complete body belong to the returned window
            # before passing the address to IsValidSid (which requires a SID).
            self.assertTrue(ctypes.sizeof(TokenUser) <= offset and offset + 8 <= returned.value,
                            'independent SID header outside owned window')
            revision, count = raw[offset:offset + 2]
            self.assertTrue(revision == 1 and count <= 15
                            and offset + 8 + count * 4 <= returned.value,
                            'independent SID body outside owned window')
            self.assertTrue(bool(advapi.IsValidSid(pointer)), 'independent OS SID invalid')
            converted = advapi.ConvertSidToStringSidW(pointer, ctypes.byref(text))
            self.assertTrue(bool(converted) and bool(text.value), 'independent SID conversion failed')
            sid = ctypes.wstring_at(text.value)
            self.assertTrue(type(sid) is str and re.fullmatch(r'S-1-(?:0|[1-9][0-9]*)(?:-(?:0|[1-9][0-9]*))*', sid)
                            is not None, 'independent SID text is not canonical')
            return sid
        finally:
            try:
                if text.value:
                    self.assertTrue(kernel.LocalFree(text.value) is None,
                                    'independent SID allocation cleanup unconfirmed')
            finally:
                if token.value and token.value != void(-1).value:
                    self.assertTrue(bool(kernel.CloseHandle(token.value)),
                                    'independent token cleanup unconfirmed')

    def test_capture_repeated_matches_independent_os_sid_and_closes(self):
        try:
            module = identity_module(self)
            identity = module.WindowsStartupHostIdentity()
            for _ in range(3):
                expected = self.independent_os_sid()
                actual = identity.capture()
                self.assertTrue(type(actual) is str, 'capture did not return owned SID text')
                self.assertTrue(actual == expected, 'capture disagrees with independent OS SID')
                self.assertFalse(identity.cleanup_unconfirmed, 'capture cleanup unconfirmed')
        except Exception:
            # Windows DLL/API/fixture problems are failures, never platform
            # skips; redact any underlying private OS value from diagnostics.
            raise AssertionError('Windows native host identity verification failed') from None


if __name__ == '__main__':
    unittest.main()
