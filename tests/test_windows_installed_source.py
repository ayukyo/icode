"""Portable probe contracts only; fake APIs never grant native evidence."""
import copy
import ctypes
import importlib.util
import io
import json
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr
import unittest
from unittest.mock import patch
from contextlib import ExitStack
from types import SimpleNamespace
from tests.test_windows_startup_security import descriptor, acl, ace, sid
from tests.test_windows_startup_native import Function


SHA = 'a' * 40
PYTHON = [3, 12]
WINDOWS = [10, 0, 26100]
PROBE = Path(__file__).resolve().parents[1] / 'scripts/probe_windows_installed_source.py'


def load_probe():
    spec = importlib.util.spec_from_file_location('installed_source_probe_tests', PROBE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def receipt(rejected=True, count=2):
    nodes = [('helper', index) for index in range(count)] + [('verifier', index) for index in range(count)]
    events = nodes[:1] if rejected else nodes
    return {'schema_version': 1, 'scope': 'installed_source_consumer_observation',
            'source_sha': SHA, 'architecture': 'x64', 'python': PYTHON[:], 'windows': WINDOWS[:],
            'observation_complete': True,
            'baseline': {'outcome': 'rejected' if rejected else 'ready',
                         'close_confirmed': None if rejected else True},
            'consumer': {'outcome': 'rejected' if rejected else 'ready',
                         'reason': 'owner_untrusted' if rejected else 'pass'},
            'resources': [{'resource': name, 'nodes': count, 'opened': count,
                           'confirmed_closes': count, 'unconfirmed_closes': 0}
                          for name in ('helper', 'verifier')],
            'policy_events': [{'resource': resource, 'index': index,
                               'result': 'owner_untrusted' if rejected else 'pass',
                               'security_reads': 2, 'confirmed_frees': 2}
                              for resource, index in events],
            'security_reads': 2 * len(events), 'allocations': 2 * len(events),
            'confirmed_frees': 2 * len(events), 'unconfirmed_frees': 0,
            'close_order': [{'resource': resource, 'index': index} for resource, index in reversed(nodes)],
            'reverse_close_confirmed': True, 'compatibility_accepted': False,
            'launch_authorized': False, 'protected_observed': False}


def wire(data):
    return json.dumps(data, separators=(',', ':')).encode('ascii') + b'\n'


class SourceProbeInterfaceTests(unittest.TestCase):
    def test_interface_exists(self):
        self.assertTrue(PROBE.is_file(), 'installed consumer probe is missing')
        module = load_probe()
        for name in ('probe', 'validate_wire', 'main'):
            self.assertTrue(callable(getattr(module, name, None)))


class SourceReceiptTests(unittest.TestCase):
    def setUp(self):
        self.m = load_probe()

    def validate(self, data):
        return self.m.validate_wire(wire(data), SHA, 'x64',
                                    expected_python=PYTHON, expected_windows=WINDOWS)

    def accepted(self, data):
        try:
            return self.validate(data)
        except ValueError:
            self.fail('valid finite receipt was rejected')

    def test_valid_ready_and_each_rejection(self):
        for rejected in (False, True):
            data = receipt(rejected)
            if not rejected:
                self.assertEqual(self.accepted(data), data)
            else:
                for reason in ('owner_untrusted', 'mutation_untrusted', 'empty_dacl'):
                    data['consumer']['reason'] = data['policy_events'][-1]['result'] = reason
                    self.assertEqual(self.accepted(data), data)

    def test_exact_keys_types_versions_and_authority(self):
        data = receipt()
        changes = [('schema_version', True), ('scope', 'other'), ('source_sha', 'b' * 40),
                   ('architecture', 'arm64'), ('python', [3, 13]), ('windows', [10, 0, 26200]),
                   ('observation_complete', 1), ('reverse_close_confirmed', False),
                   ('compatibility_accepted', True), ('launch_authorized', True),
                   ('protected_observed', True), ('security_reads', True), ('allocations', 0),
                   ('confirmed_frees', 0), ('unconfirmed_frees', 1)]
        for key, value in changes:
            with self.subTest(key=key):
                bad = copy.deepcopy(data)
                bad[key] = value
                with self.assertRaisesRegex(ValueError, '^invalid_installed_source_receipt$'):
                    self.validate(bad)
        for obj in (data, data['baseline'], data['consumer'], data['resources'][0],
                    data['policy_events'][0], data['close_order'][0]):
            obj['private_path'] = 'secret'
            with self.assertRaises(ValueError):
                self.validate(data)
            del obj['private_path']

    def test_baseline_and_consumer_consistency(self):
        for rejected in (False, True):
            for key, value in (('close_confirmed', False), ('outcome', 'other')):
                data = receipt(rejected)
                data['baseline'][key] = value
                with self.assertRaises(ValueError):
                    self.validate(data)
        data = receipt()
        data['baseline']['close_confirmed'] = True
        with self.assertRaises(ValueError):
            self.validate(data)
        data = receipt(False)
        data['baseline']['close_confirmed'] = None
        with self.assertRaises(ValueError):
            self.validate(data)

    def test_resource_close_prefix_and_budget(self):
        for field in ('nodes', 'opened', 'confirmed_closes', 'unconfirmed_closes'):
            for value in (True, 1, 33) if field == 'unconfirmed_closes' else (True, 0, 33):
                data = receipt()
                data['resources'][0][field] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    self.validate(data)
        for change in (lambda d: d['resources'].reverse(),
                       lambda d: d['close_order'].reverse(),
                       lambda d: d['close_order'].pop(),
                       lambda d: d['close_order'].append(d['close_order'][0]),
                       lambda d: d['policy_events'].clear(),
                       lambda d: d['policy_events'][0].update(index=1),
                       lambda d: d['policy_events'][0].update(resource='verifier'),
                       lambda d: d['policy_events'][0].update(security_reads=0),
                       lambda d: d['policy_events'][0].update(confirmed_frees=True)):
            data = receipt()
            change(data)
            with self.assertRaises(ValueError):
                self.validate(data)
        data = receipt(False)
        data['policy_events'][0]['result'] = 'owner_untrusted'
        with self.assertRaises(ValueError):
            self.validate(data)

    def test_wire_and_expected_inputs_are_strict(self):
        valid = wire(receipt())
        for bad in (valid[:-1], valid + b'\n', b' ' + valid, valid.replace(b',', b', ', 1),
                    valid.replace(b'"schema_version":1', b'"schema_version":1,"schema_version":1'),
                    b'x' * 32769, b'\xff\n', valid.decode('ascii')):
            with self.subTest(kind=type(bad)), self.assertRaises(ValueError):
                self.m.validate_wire(bad, SHA, 'x64', expected_python=PYTHON, expected_windows=WINDOWS)
        try:
            result = self.m.validate_wire(valid[:-1] + b'\r\n', SHA, 'x64',
                                           expected_python=PYTHON, expected_windows=WINDOWS)
        except ValueError:
            self.fail('valid CRLF receipt was rejected')
        self.assertEqual(result, receipt())
        for expected in (None, (3, 12), [3, True], [3, 10], [3, 11], [3, 13]):
            with self.assertRaises(ValueError):
                self.m.validate_wire(valid, SHA, 'x64', expected_python=expected, expected_windows=WINDOWS)
        for expected in (None, (10, 0, 26100), [True, 0, 26100], [10, -1, 26100]):
            with self.assertRaises(ValueError):
                self.m.validate_wire(valid, SHA, 'x64', expected_python=PYTHON, expected_windows=expected)

    def test_matching_unsupported_python_receipts_are_rejected(self):
        self.assertEqual(self.accepted(receipt()), receipt())
        for minor in (10, 11, 13):
            data = receipt()
            data['python'] = [3, minor]
            with self.subTest(minor=minor), self.assertRaises(ValueError):
                self.m.validate_wire(wire(data), SHA, 'x64',
                                     expected_python=[3, minor], expected_windows=WINDOWS)

    def test_maximum_counts_ready_and_rejected_terminal(self):
        data = receipt(False, 32)
        self.assertEqual(self.accepted(data), data)
        data['baseline'] = {'outcome': 'rejected', 'close_confirmed': None}
        data['consumer'] = {'outcome': 'rejected', 'reason': 'mutation_untrusted'}
        data['policy_events'][-1]['result'] = 'mutation_untrusted'
        self.assertEqual(self.accepted(data), data)
        data['policy_events'].append(data['policy_events'][-1])
        with self.assertRaises(ValueError):
            self.validate(data)


class ConsumerFixture:
    """Fake DLL only; consumer, pin, native transport and reader remain real."""
    def __init__(self, module, rejected=True):
        self.module = module
        self.raw = descriptor(owner=sid(5, (99,)) if rejected else sid(5, (18,)),
                              dacl=acl((ace(),)))
        self.buffer = ctypes.create_string_buffer(self.raw)
        self.handles = {}
        self.raw_by_handle = {}
        self.next_handle = 10
        self.close_result = 1
        self.free_result = None
        self.open_error = self.query_error = self.free_error = self.close_error = None
        self.fail_open_at = self.fail_query_at = self.fail_free_at = self.fail_close_at = None
        self.kernel = SimpleNamespace(
            QueryDosDeviceW=Function(self.mapping), GetFileType=Function(lambda h: 1),
            GetFileInformationByHandleEx=Function(self.info),
            SetFilePointerEx=Function(self.seek), ReadFile=Function(self.read),
            CloseHandle=Function(self.close), LocalFree=Function(self.free))
        self.ntdll = SimpleNamespace(NtCreateFile=Function(self.open))
        self.advapi = SimpleNamespace(
            GetSecurityInfo=Function(self.security), IsValidSecurityDescriptor=Function(lambda p: 1),
            GetSecurityDescriptorControl=Function(self.control),
            GetSecurityDescriptorLength=Function(lambda p: len(self.raw)))

    def mapping(self, drive, buffer, count):
        raw = '\\Device\\HarddiskVolume1\0\0'.encode('utf-16-le')
        ctypes.memmove(buffer, raw, len(raw))
        return len(raw) // 2

    def open(self, output, access, oa, ios, alloc, attrs, share, disposition, opts, ea, length):
        handle = self.next_handle
        self.next_handle += 1
        self.handles[handle] = bool(opts & 1)
        ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p))[0] = handle
        if len(self.ntdll.NtCreateFile.calls) == self.fail_open_at:
            raise self.open_error
        return 0

    def info(self, handle, kind, output, size):
        from icode.windows_startup_native import _INFO_CLASSES
        value = ctypes.cast(output, ctypes.POINTER(_INFO_CLASSES[kind])).contents
        directory = self.handles[handle]
        if kind in (0, 9):
            value.FileAttributes = 16 if directory else 128
            if kind == 0:
                value.ChangeTime = 7
        elif kind == 1:
            value.Directory, value.NumberOfLinks, value.EndOfFile = directory, 1, 3
        else:
            value.VolumeSerialNumber = 9
            value.FileId[0] = handle
        return 1

    def seek(self, handle, offset, position, origin):
        ctypes.cast(position, ctypes.POINTER(ctypes.c_int64))[0] = offset
        return 1

    def read(self, handle, buffer, count, actual, overlap):
        ctypes.memmove(buffer, b'abc', count)
        ctypes.cast(actual, ctypes.POINTER(ctypes.c_uint32))[0] = count
        return 1

    def security(self, *args):
        if args[0] in self.raw_by_handle:
            self.raw = self.raw_by_handle[args[0]]
            self.buffer = ctypes.create_string_buffer(self.raw)
        ctypes.cast(args[-1], ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.addressof(self.buffer)
        if len(self.advapi.GetSecurityInfo.calls) == self.fail_query_at:
            raise self.query_error
        return 0

    def control(self, pointer, control, revision):
        ctypes.cast(control, ctypes.POINTER(ctypes.c_uint16))[0] = 0x8004
        ctypes.cast(revision, ctypes.POINTER(ctypes.c_uint32))[0] = 1
        return 1

    def free(self, pointer):
        if len(self.kernel.LocalFree.calls) == self.fail_free_at:
            if self.free_error is not None:
                raise self.free_error
            return self.free_result
        return None

    def close(self, handle):
        if len(self.kernel.CloseHandle.calls) == self.fail_close_at:
            if self.close_error is not None:
                raise self.close_error
            return self.close_result
        return 1

    def environment(self):
        stack = ExitStack()
        m = self.module
        stack.enter_context(patch.object(m.sys, 'platform', 'win32'))
        stack.enter_context(patch.object(m.sys, 'version_info', SimpleNamespace(major=3, minor=12)))
        stack.enter_context(patch.object(m.sys, 'getwindowsversion', create=True,
                                        return_value=SimpleNamespace(major=10, minor=0, build=26100)))
        stack.enter_context(patch.object(m.sysconfig, 'get_platform', return_value='win-amd64'))
        stack.enter_context(patch.object(m.source.os, 'name', 'nt'))
        stack.enter_context(patch.object(m.source, '_installed_resources',
                                        return_value=(('helper', 'C:\\h.exe'), ('verifier', 'C:\\v.exe'))))
        stack.enter_context(patch.object(m.source, 'WindowsStartupHostIdentity', return_value=
                                        SimpleNamespace(capture=lambda: 'S-1-5-21-1', cleanup_unconfirmed=False)))
        stack.enter_context(patch.object(ctypes, 'WinDLL', create=True,
                                        side_effect=lambda name, **kw: {'kernel32': self.kernel,
                                                                      'ntdll': self.ntdll,
                                                                      'advapi32': self.advapi}[name]))
        return stack


class SourceConsumerObservationTests(unittest.TestCase):
    def setUp(self):
        self.m = load_probe()

    def test_two_real_consumer_calls_ready_and_policy_rejection(self):
        for rejected in (False, True):
            fixture = ConsumerFixture(self.m, rejected)
            original = self.m.source.pin_installed_startup_sources
            with fixture.environment(), patch.object(self.m.source, 'pin_installed_startup_sources',
                                                      wraps=original) as calls:
                try:
                    result = self.m.probe(SHA)
                except ValueError:
                    self.fail('installed consumer observations missing')
            self.assertEqual(calls.call_args_list, [unittest.mock.call(), unittest.mock.call()])
            self.assertEqual(result, receipt(rejected))
            self.assertEqual(len(fixture.kernel.CloseHandle.calls), 8)
            self.assertEqual(len(fixture.advapi.GetSecurityInfo.calls), 4 if rejected else 16)
            self.assertEqual(len(fixture.kernel.LocalFree.calls), 4 if rejected else 16)
            self.m.validate_wire(wire(result), SHA, 'x64', expected_python=PYTHON, expected_windows=WINDOWS)

    def test_input_rejected_before_native_or_consumer(self):
        with patch.object(self.m.source, 'pin_installed_startup_sources') as entry:
            for platform in ('win32', 'linux'):
                # A valid SHA is rejected by the platform gate only off Windows.
                values = (None, True, 'A' * 40, 'a' * 39)
                if platform != 'win32':
                    values += (SHA,)
                with self.subTest(platform=platform), patch.object(self.m.sys, 'platform', platform):
                    for value in values:
                        with self.assertRaises(ValueError):
                            self.m.probe(value)
            entry.assert_not_called()

    def test_unsupported_python_producer_stops_before_consumers(self):
        fixture = ConsumerFixture(self.m)
        for minor in (10, 11, 13):
            with self.subTest(minor=minor), fixture.environment(), \
                 patch.object(self.m.sys, 'version_info', SimpleNamespace(major=3, minor=minor)), \
                 patch.object(self.m.source, 'pin_installed_startup_sources') as entry, \
                 patch.object(self.m, '_observe_consumer') as observe:
                with self.assertRaises(ValueError):
                    self.m.probe(SHA)
                entry.assert_not_called()
                observe.assert_not_called()

    def test_observed_native_faults_restore_bindings_and_preserve_interrupts(self):
        for kind in (RuntimeError, KeyboardInterrupt, SystemExit):
            for operation, number in (('open', 3), ('query', 1), ('free', 1), ('close', 1)):
                with self.subTest(kind=kind, operation=operation):
                    fixture = ConsumerFixture(self.m)
                    error = kind('private native value')
                    setattr(fixture, 'fail_' + operation + '_at', number)
                    setattr(fixture, operation + '_error', error)
                    bindings = (self.m.source.WindowsStartupPinBackend, self.m.source.check_startup_security,
                                self.m.security_native.WindowsStartupSecurityReader)
                    with fixture.environment(), self.assertRaises(BaseException) as caught:
                        self.m._observe_consumer()
                    if kind is not RuntimeError and operation != 'close':
                        self.assertIs(caught.exception, error)
                    self.assertEqual(bindings, (self.m.source.WindowsStartupPinBackend,
                                               self.m.source.check_startup_security,
                                               self.m.security_native.WindowsStartupSecurityReader))
                    self.assertEqual(len(fixture.kernel.LocalFree.calls), 0 if operation == 'open' else 1 if operation in ('query', 'free') else 2)
                    self.assertEqual(len(fixture.kernel.CloseHandle.calls), 3 if operation == 'open' else 4)

    def test_unknown_close_and_free_never_issue_receipts(self):
        for operation in ('close', 'free'):
            fixture = ConsumerFixture(self.m)
            setattr(fixture, 'fail_' + operation + '_at', 1)
            setattr(fixture, operation + '_result', 0 if operation == 'close' else ctypes.addressof(fixture.buffer))
            with fixture.environment(), self.assertRaises((ValueError, self.m.StartupSecurityError)):
                self.m._observe_consumer()
            self.assertEqual(len(fixture.kernel.CloseHandle.calls), 4)
            self.assertEqual(len(fixture.kernel.LocalFree.calls), 2 if operation == 'close' else 1)

    def test_reader_or_parser_matching_policy_message_is_not_policy_credit(self):
        for position in ('native', 'parser'):
            fixture = ConsumerFixture(self.m)
            error = self.m.StartupSecurityError('startup security owner is not trusted for role')
            with fixture.environment(), ExitStack() as stack:
                if position == 'native':
                    fixture.fail_query_at, fixture.query_error = 1, error
                else:
                    stack.enter_context(patch.object(self.m.security_native, 'parse_startup_security', side_effect=error))
                with self.assertRaises((ValueError, self.m.StartupSecurityError)):
                    self.m._observe_consumer()
            self.assertEqual(len(fixture.kernel.LocalFree.calls), 1)
            self.assertEqual(len(fixture.kernel.CloseHandle.calls), 4)

    def test_baseline_unknown_error_stops_before_observation(self):
        error = RuntimeError('private baseline error')
        fixture = ConsumerFixture(self.m)
        with fixture.environment(), patch.object(self.m.source, 'pin_installed_startup_sources', side_effect=error) as entry:
            with self.assertRaises(RuntimeError) as caught:
                self.m.probe(SHA)
        self.assertIs(caught.exception, error)
        entry.assert_called_once_with()

    def test_baseline_visible_cleanup_failure_stops_before_second_call(self):
        for error in (None, KeyboardInterrupt('private close'), SystemExit('private close'),
                      MemoryError('private close')):
            fixture = ConsumerFixture(self.m)
            fixture.fail_close_at, fixture.close_result, fixture.close_error = 1, 0, error
            original = self.m.source.pin_installed_startup_sources
            with self.subTest(error=type(error)), fixture.environment(), patch.object(
                    self.m.source, 'pin_installed_startup_sources', wraps=original) as entry:
                with self.assertRaises(self.m.StartupSecurityError):
                    self.m.probe(SHA)
            entry.assert_called_once_with()
            self.assertEqual(len(fixture.kernel.CloseHandle.calls), 4)

    def test_baseline_notes_are_fail_closed_without_inspecting_values(self):
        class Hostile:
            def __bool__(self):
                raise KeyboardInterrupt('private bool')
            def __str__(self):
                raise SystemExit('private str')
        class Notes(list):
            def __bool__(self):
                raise KeyboardInterrupt('private notes bool')
        for notes in (['Startup source cleanup unconfirmed'], ['private unknown'],
                      None, (), Hostile(), Notes()):
            error = self.m.StartupSecurityError('startup security owner is not trusted for role')
            error.__dict__['__notes__'] = notes
            fixture = ConsumerFixture(self.m)
            with self.subTest(notes_type=type(notes)), fixture.environment(), patch.object(
                    self.m.source, 'pin_installed_startup_sources', side_effect=error) as entry:
                with self.assertRaises(self.m.StartupSecurityError) as caught:
                    self.m.probe(SHA)
            self.assertIs(caught.exception, error)
            entry.assert_called_once_with()
        fixture = ConsumerFixture(self.m)
        original_policy = self.m.source.check_startup_security
        def empty_notes(*args, **kwargs):
            try:
                return original_policy(*args, **kwargs)
            except self.m.StartupSecurityError as error:
                error.__notes__ = []
                raise
        with fixture.environment(), patch.object(self.m.source, 'check_startup_security', side_effect=empty_notes):
            self.assertEqual(self.m.probe(SHA), receipt())

    def test_hostile_policy_subclass_does_not_replace_baseline_exception(self):
        class Hostile(self.m.StartupSecurityError):
            def __getattribute__(self, name):
                if name in ('args', '__notes__'):
                    raise KeyboardInterrupt('private attribute')
                return super().__getattribute__(name)
        error = Hostile()
        fixture = ConsumerFixture(self.m)
        with fixture.environment(), patch.object(self.m.source, 'pin_installed_startup_sources', side_effect=error) as entry:
            with self.assertRaises(Hostile) as caught:
                self.m.probe(SHA)
        self.assertIs(caught.exception, error)
        entry.assert_called_once_with()

    def test_main_valid_wire_and_fixed_failures(self):
        for rejected in (False, True):
            output, errors = io.StringIO(), io.StringIO()
            with patch.object(self.m, 'probe', return_value=receipt(rejected)), redirect_stdout(output), redirect_stderr(errors):
                self.assertEqual(self.m.main(['--source-sha', SHA]), 0)
            self.assertEqual(output.getvalue().encode('ascii'), wire(receipt(rejected)))
            self.assertEqual(errors.getvalue(), '')
        for error, code in ((RuntimeError('private path'), 1), (KeyboardInterrupt('private value'), 130), (SystemExit('private value'), 1)):
            output, errors = io.StringIO(), io.StringIO()
            with patch.object(self.m, 'probe', side_effect=error), redirect_stdout(output), redirect_stderr(errors):
                self.assertEqual(self.m.main(['--source-sha', SHA]), code)
            self.assertEqual(output.getvalue(), '')
            self.assertEqual(errors.getvalue(), 'windows_installed_source_observation_failed\n')

    def test_main_invalid_arguments_and_receipts_never_print_private_values(self):
        for argv in ([], ['--unknown', 'private value'], ['--source-sha']):
            output, errors = io.StringIO(), io.StringIO()
            with redirect_stdout(output), redirect_stderr(errors):
                self.assertEqual(self.m.main(argv), 1)
            self.assertEqual(output.getvalue(), '')
            self.assertEqual(errors.getvalue(), 'windows_installed_source_observation_failed\n')
        bad = receipt()
        bad['private_path'] = 'private value'
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(self.m, 'probe', return_value=bad), redirect_stdout(output), redirect_stderr(errors):
            self.assertEqual(self.m.main(['--source-sha', SHA]), 1)
        self.assertEqual(output.getvalue(), '')
        self.assertEqual(errors.getvalue(), 'windows_installed_source_observation_failed\n')

    def test_second_resource_rejection_is_exact_prefix(self):
        fixture = ConsumerFixture(self.m, False)
        rejected = descriptor(owner=sid(5, (99,)), dacl=acl((ace(),)))
        fixture.raw_by_handle[12] = rejected
        with fixture.environment():
            result, observation = self.m._observe_consumer()
        self.assertEqual(result, {'outcome': 'rejected', 'reason': 'owner_untrusted'})
        self.assertEqual([(event['resource'], event['index'], event['result']) for event in observation['policy_events']],
                         [('helper', 0, 'pass'), ('helper', 1, 'pass'), ('verifier', 0, 'owner_untrusted')])
        self.assertEqual(observation['security_reads'], 6)
        self.assertEqual(len(fixture.kernel.CloseHandle.calls), 4)

    def test_two_round_disagreement_fails(self):
        fixture = ConsumerFixture(self.m, False)
        fixture.raw_by_handle[14] = descriptor(owner=sid(5, (99,)), dacl=acl((ace(),)))
        with fixture.environment(), self.assertRaisesRegex(ValueError, '^installed_source_observation_failed$'):
            self.m.probe(SHA)

    def test_ready_close_interrupt_is_original_and_unknown_never_retried(self):
        for kind in (KeyboardInterrupt, SystemExit):
            fixture = ConsumerFixture(self.m, False)
            error = kind('private close')
            fixture.fail_close_at, fixture.close_error = 1, error
            with fixture.environment(), self.assertRaises(kind) as caught:
                self.m._observe_consumer()
            self.assertIs(caught.exception, error)
            self.assertEqual(len(fixture.kernel.CloseHandle.calls), 4)

    def test_policy_arguments_and_return_are_preserved(self):
        fixture = ConsumerFixture(self.m, False)
        original = self.m.source.check_startup_security
        results = []
        def observe_return(*args, **kwargs):
            value = original(*args, **kwargs)
            results.append(value)
            return value
        with fixture.environment(), patch.object(self.m.source, 'check_startup_security', side_effect=observe_return) as call:
            result, observation = self.m._observe_consumer()
        self.assertEqual(len(results), 4)
        self.assertTrue(all(type(result).__name__ == 'StartupSecurityDescriptor' for result in results))
        for ordinal, (args, kwargs) in enumerate(call.call_args_list):
            self.assertEqual(len(args), 1)
            self.assertEqual(kwargs, {'role': 'source', 'host_sid': 'S-1-5-21-1',
                                      'directory': ordinal % 2 == 0})

    def test_policy_rejection_requires_same_exception_witness(self):
        fixture = ConsumerFixture(self.m)
        original = self.m.source.pin_installed_startup_sources
        foreign = self.m.StartupSecurityError('startup security owner is not trusted for role')
        def replaced_exception():
            try:
                return original()
            except self.m.StartupSecurityError:
                raise foreign
        with fixture.environment(), patch.object(self.m.source, 'pin_installed_startup_sources',
                                                 side_effect=replaced_exception):
            with self.assertRaises(self.m.StartupSecurityError) as caught:
                self.m._observe_consumer()
        self.assertIs(caught.exception, foreign)

    def test_query_recording_fault_cannot_replace_original_interrupt(self):
        for kind in (KeyboardInterrupt, SystemExit):
            fixture = ConsumerFixture(self.m)
            original = kind('private body')
            fixture.fail_query_at, fixture.query_error = 1, original
            with fixture.environment(), patch.object(self.m._Observation, 'allocated',
                                                      side_effect=KeyboardInterrupt('recording fault')):
                with self.assertRaises(BaseException) as caught:
                    self.m._observe_consumer()
            self.assertIs(caught.exception, original)
            self.assertEqual(len(fixture.kernel.LocalFree.calls), 1)
            self.assertEqual(len(fixture.kernel.CloseHandle.calls), 4)

    def test_acquired_handle_recording_interrupt_closes_once_and_preserves_body(self):
        fixture = ConsumerFixture(self.m)
        original = KeyboardInterrupt('private handle registration')
        with fixture.environment(), patch.object(self.m._Observation, 'opened', side_effect=original):
            with self.assertRaises(KeyboardInterrupt) as caught:
                self.m._observe_consumer()
        self.assertIs(caught.exception, original)
        self.assertEqual(len(fixture.ntdll.NtCreateFile.calls), 1)
        self.assertEqual(len(fixture.kernel.CloseHandle.calls), 1)

    def test_free_recording_interrupt_does_not_prevent_actual_release(self):
        for body_error in (None, KeyboardInterrupt('private query')):
            for kind in (KeyboardInterrupt, SystemExit, MemoryError):
                fixture = ConsumerFixture(self.m)
                recording_error = kind('private recording')
                if body_error is not None:
                    fixture.fail_query_at, fixture.query_error = 1, body_error
                with self.subTest(body=type(body_error), kind=kind), fixture.environment(), patch.object(
                        self.m._Observation, 'freeing', side_effect=recording_error):
                    with self.assertRaises(BaseException) as caught:
                        self.m._observe_consumer()
                self.assertIs(caught.exception, body_error if body_error is not None else recording_error)
                self.assertEqual(len(fixture.kernel.LocalFree.calls), 1)
                self.assertEqual(len(fixture.kernel.CloseHandle.calls), 4)

    def test_successful_native_recording_faults_do_not_skip_owned_cleanup(self):
        for hook in ('opened', 'allocated', 'close'):
            for kind in (KeyboardInterrupt, SystemExit, MemoryError):
                fixture = ConsumerFixture(self.m, hook != 'close')
                recording_error = kind('private recording')
                with self.subTest(hook=hook, kind=kind), fixture.environment(), patch.object(
                        self.m._Observation, hook, side_effect=recording_error):
                    with self.assertRaises(BaseException) as caught:
                        self.m._observe_consumer()
                if hook != 'close' or kind is not MemoryError:
                    self.assertIs(caught.exception, recording_error)
                self.assertEqual(len(fixture.kernel.CloseHandle.calls), 1 if hook == 'opened' else 4)
                self.assertEqual(len(fixture.kernel.LocalFree.calls), 0 if hook == 'opened' else 1 if hook == 'allocated' else 8)

    def test_hostile_exception_attributes_and_notes_do_not_replace_body(self):
        class Hostile(KeyboardInterrupt):
            def __getattribute__(self, name):
                if name in ('args', '__notes__'):
                    raise SystemExit('private attribute')
                return super().__getattribute__(name)
            def __str__(self):
                raise SystemExit('private formatting')
        fixture = ConsumerFixture(self.m)
        original = Hostile()
        fixture.fail_query_at, fixture.query_error = 1, original
        fixture.fail_free_at, fixture.free_error = 1, RuntimeError('private free')
        with fixture.environment(), self.assertRaises(Hostile) as caught:
            self.m._observe_consumer()
        self.assertIs(caught.exception, original)
        self.assertEqual(len(fixture.kernel.LocalFree.calls), 1)
        self.assertEqual(len(fixture.kernel.CloseHandle.calls), 4)


class SourceObservationLedgerTests(unittest.TestCase):
    def setUp(self):
        self.m = load_probe()

    def ledger(self):
        ledger = self.m._Observation()
        ledger.backends = 2
        for handle, resource in enumerate((0, 0, 1, 1), 10):
            ledger.opened(resource, handle)
        for node in ledger.nodes[0] + ledger.nodes[1]:
            ledger.current = node
            for _ in range(2):
                ledger.allocated(100)
                allocation = ledger.freeing(100)
                ledger.freed(100, allocation, None)
                ledger.reads.append(node)
                ledger.pending.append((node, b'raw'))
            ledger.policy(b'raw', 'pass')
        for handle in (13, 12, 11, 10):
            ledger.close(handle, 1)
        return ledger

    def test_same_node_association_not_just_equal_totals(self):
        for field in ('reads', 'allocations'):
            ledger = self.ledger()
            if field == 'reads':
                ledger.reads[0] = (1, 0)
            else:
                ledger.allocations[0]['node'] = (1, 0)
            with self.subTest(field=field), self.assertRaises(ValueError):
                ledger.receipt()

    def test_reverse_close_duplicates_unknown_and_unmatched_reads_fail(self):
        for change in (lambda l: l.closed.reverse(), lambda l: l.closed.pop(),
                       lambda l: l.close(13, 1), lambda l: l.close(999, 1),
                       lambda l: l.close(13, 0), lambda l: l.pending.append(((0, 0), b'raw')),
                       lambda l: l.reads.pop(), lambda l: l.allocations.pop(),
                       lambda l: l.allocations[0].update(confirmed=False)):
            ledger = self.ledger()
            change(ledger)
            with self.assertRaises(ValueError):
                ledger.receipt()

    def test_live_pointer_collision_duplicate_and_unknown_free_fail(self):
        for change in (lambda l: l.allocated(100), lambda l: l.freeing(999),
                       lambda l: (l.freeing(100), l.freeing(100)),
                       lambda l: l.freed(100, l.freeing(100), 100)):
            ledger = self.ledger()
            ledger.current = (0, 0)
            ledger.allocated(100)
            change(ledger)
            with self.assertRaises(ValueError):
                ledger.receipt()

    def test_policy_needs_exact_two_reads_same_node_and_terminal_rejection(self):
        for pending in ([], [((0, 0), b'raw')], [((0, 0), b'raw')] * 3,
                        [((0, 0), b'raw'), ((1, 0), b'raw')],
                        [((0, 0), b'raw'), ((0, 0), b'drift')]):
            ledger = self.m._Observation()
            ledger.opened(0, 10)
            ledger.opened(0, 11)
            ledger.pending = pending
            ledger.policy(b'raw', 'pass')
            self.assertTrue(ledger.fault)
        ledger = self.ledger()
        ledger.events[-1]['result'] = 'owner_untrusted'
        ledger.pending = [((1, 1), b'raw')] * 2
        ledger.policy(b'raw', 'pass')
        self.assertTrue(ledger.fault)

    def test_native_budgets_and_legal_address_reuse(self):
        ledger = self.ledger()
        self.assertEqual(ledger.receipt()['allocations'], 8)
        self.assertFalse(ledger.fault)
        for budget in ('nodes', 'allocations'):
            ledger = self.m._Observation()
            ledger.current = (0, 0)
            for ordinal in range(33 if budget == 'nodes' else 129):
                if budget == 'nodes':
                    ledger.opened(0, ordinal + 1)
                else:
                    ledger.allocated(100)
                    allocation = ledger.freeing(100)
                    ledger.freed(100, allocation, None)
            self.assertTrue(ledger.fault)
            self.assertLessEqual(len(ledger.nodes[0]), 32)
            self.assertLessEqual(len(ledger.allocations), 128)
