"""Private DACL portable contracts and separately selected Windows observations."""
import importlib
import importlib.util
import copy
import json
import ctypes
import inspect
import sys
from types import SimpleNamespace
from unittest.mock import patch
from tests.test_windows_startup_security_native import Function
from tests.test_windows_startup_security import descriptor, acl, ace, sid
from dataclasses import replace
from icode.windows_startup_pin import StartupFileMetadata


HOST = 'S-1-5-21-1'


def raw_marker(marker=0x80):
    entries = [ace(mask=0x1f01ff, trustee=value) for value in
               (sid(5, (21, 1)), sid(5, (18,)), sid(5, (32, 544)))]
    entries.append(ace(mask=marker, trustee=sid(1, (0,))))
    return descriptor(control=0x9004, dacl=acl(entries))


def snapshot(marker=0x80):
    return {'parent': StartupFileMetadata(1, b'p' * 16, True, False, False, 'disk', 1, 0, 1),
            'leaf': StartupFileMetadata(1, b'l' * 16, False, False, False, 'disk', 1, 20, 1),
            'raw': raw_marker(marker), 'bytes': b'private-dacl-fixture\n'}
import unittest


class PrivateDaclTransportTests(unittest.TestCase):
    def test_fixture_interface_exists(self):
        self.assertIsNotNone(importlib.util.find_spec('tests.windows_private_dacl_fixture'),
                             'private DACL fixture missing')
        fixture = importlib.import_module('tests.windows_private_dacl_fixture')
        for name in ('run_variant', 'validate_wire'):
            self.assertTrue(callable(getattr(fixture, name, None)))

    def setUp(self):
        self.m = importlib.import_module('tests.windows_private_dacl_fixture')

    def receipt(self, target='parent', opener='new', blocked=False):
        windows = []
        for phase in ('unpinned', 'pinned', 'released'):
            deny = blocked and phase == 'pinned'
            windows.append({'window': phase, 'open_result': 0 if opener == 'new' else None,
                            'set_result': 5 if deny else 0, 'effect': 'blocked' if deny else 'changed',
                            'sd_changed': not deny, 'metadata_changed': False,
                            'identity_stable': True, 'bytes_stable': True, 'protected': True})
        return {'scope': 'private_dacl_window_observation', 'schema_version': 1,
                'target': target, 'opener': opener,
                'acquisition': {'phase': 'before_windows', 'result': 0} if opener == 'preexisting' else None,
                'windows': windows, 'cleanup_confirmed': True, 'consumer_ready': False,
                'compatibility_accepted': False, 'launch_authorized': False}

    def wire(self, data):
        return json.dumps(data, separators=(',', ':')).encode('ascii') + b'\n'

    def test_valid_schema_all_variants_and_rejection_positions(self):
        for target in ('parent', 'leaf'):
            for opener in ('new', 'preexisting'):
                for blocked in (False, True):
                    data = self.receipt(target, opener, blocked)
                    try:
                        result = self.m.validate_wire(self.wire(data))
                    except ValueError:
                        self.fail('valid finite private DACL receipt rejected')
                    self.assertEqual(result, data)
                if opener == 'new':
                    for code in (5, 32, 33):
                        data = self.receipt(target, opener, True)
                        data['windows'][1].update(open_result=code, set_result=None)
                        self.assertEqual(self.m.validate_wire(self.wire(data)), data)

    def test_schema_strict_types_keys_authority_and_window_combinations(self):
        data = self.receipt()
        for key, value in (('schema_version', True), ('target', 'root'), ('opener', 'other'),
                           ('cleanup_confirmed', 1), ('consumer_ready', True),
                           ('compatibility_accepted', True), ('launch_authorized', True),
                           ('acquisition', {'phase': 'before_windows', 'result': 0})):
            bad = copy.deepcopy(data)
            bad[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.m.validate_wire(self.wire(bad))
        for key, value in (('open_result', True), ('set_result', 1), ('effect', 'blocked'),
                           ('sd_changed', False), ('metadata_changed', 0),
                           ('identity_stable', False), ('bytes_stable', False), ('protected', False)):
            bad = copy.deepcopy(data)
            bad['windows'][1][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.m.validate_wire(self.wire(bad))
        for change in (lambda d: d.update(private='secret'), lambda d: d['windows'][0].update(private='secret'),
                       lambda d: d['windows'].reverse(), lambda d: d['windows'].pop(),
                       lambda d: d['windows'][0].update(set_result=5, effect='blocked', sd_changed=False)):
            bad = copy.deepcopy(data)
            change(bad)
            with self.assertRaises(ValueError):
                self.m.validate_wire(self.wire(bad))

    def test_wire_is_single_canonical_bounded_ascii_and_duplicate_free(self):
        valid = self.wire(self.receipt())
        for bad in (valid[:-1], valid + b'\n', b' ' + valid, valid.replace(b',', b', ', 1),
                    valid.replace(b'"schema_version":1', b'"schema_version":1,"schema_version":1'),
                    b'x' * 8193, b'\xff\n', valid.decode('ascii')):
            with self.assertRaises(ValueError):
                self.m.validate_wire(bad)

    def test_native_transport_and_owned_interfaces_exist(self):
        for name in ('_Native', '_OwnedHandle', '_ConvertedDacl', '_Observer'):
            self.assertTrue(callable(getattr(self.m, name, None)), name + ' missing')


class ApiFixture:
    def __init__(self, module):
        self.m = module
        self.pointer = ctypes.create_string_buffer(64)
        self.convert_ok, self.valid, self.present, self.dacl = 1, 1, 1, True
        self.set_result, self.close_result, self.free_result = 0, 1, None
        self.convert_error = self.close_error = self.free_error = None
        self.file_result, self.file_error = 70, 5
        self.filesystem = 'NTFS'
        self.next_handle, self.directories = 70, {}
        self.kernel = SimpleNamespace(CreateFileW=Function(self.open),
                                      CloseHandle=Function(self.close), LocalFree=Function(self.free),
                                      GetVolumeInformationByHandleW=Function(self.volume),
                                      GetFileType=Function(lambda h: 1),
                                      GetFileInformationByHandleEx=Function(self.info),
                                      SetFilePointerEx=Function(self.seek), ReadFile=Function(self.read))
        self.advapi = SimpleNamespace(
            ConvertStringSecurityDescriptorToSecurityDescriptorW=Function(self.convert),
            IsValidSecurityDescriptor=Function(lambda p: self.valid),
            GetSecurityDescriptorLength=Function(lambda p: 64),
            GetSecurityDescriptorDacl=Function(self.get_dacl),
            SetSecurityInfo=Function(lambda *args: self.set_result))

    def open(self, *args):
        if self.file_result != 70:
            return self.file_result
        handle = self.next_handle
        self.next_handle += 1
        self.directories[handle] = bool(args[5] & 0x2000000)
        return handle

    def info(self, handle, kind, output, size):
        value = ctypes.cast(output, ctypes.POINTER(self.m._INFO_CLASSES[kind])).contents
        directory = self.directories[handle]
        if kind in (0, 9):
            value.FileAttributes = 16 if directory else 128
            if kind == 0:
                value.ChangeTime = 1
        elif kind == 1:
            value.Directory, value.NumberOfLinks, value.EndOfFile = directory, 1, len(self.m._CONTENT)
        else:
            value.VolumeSerialNumber = 1
            value.FileId[0] = 1 if directory else 2
        return 1

    def seek(self, handle, offset, position, origin):
        ctypes.cast(position, ctypes.POINTER(ctypes.c_int64))[0] = offset
        return 1

    def read(self, handle, buffer, count, actual, overlap):
        ctypes.memmove(buffer, self.m._CONTENT, count)
        ctypes.cast(actual, ctypes.POINTER(ctypes.c_uint32))[0] = count
        return 1

    def convert(self, text, revision, output, length):
        ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.addressof(self.pointer)
        ctypes.cast(length, ctypes.POINTER(ctypes.c_uint32))[0] = 64
        if self.convert_error:
            raise self.convert_error
        return self.convert_ok

    def get_dacl(self, pointer, present, dacl, defaulted):
        ctypes.cast(present, ctypes.POINTER(ctypes.c_int32))[0] = self.present
        ctypes.cast(defaulted, ctypes.POINTER(ctypes.c_int32))[0] = 0
        if self.dacl:
            ctypes.cast(dacl, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.addressof(self.pointer) + 20
        return 1

    def free(self, pointer):
        if self.free_error:
            raise self.free_error
        return self.free_result

    def close(self, handle):
        if self.close_error:
            raise self.close_error
        return self.close_result

    def volume(self, handle, volume, volume_size, serial, maximum, flags, filesystem, size):
        filesystem.value = self.filesystem
        return 1

    def api(self):
        with patch.object(self.m.os, 'name', 'nt'), patch.object(ctypes, 'WinDLL', create=True,
                side_effect=lambda name, **kw: self.kernel if name == 'kernel32' else self.advapi):
            return self.m._Native()


class PrivateDaclNativeApiTests(unittest.TestCase):
    def setUp(self):
        self.m = importlib.import_module('tests.windows_private_dacl_fixture')
        self.fixture = ApiFixture(self.m)

    def test_fixed_open_abi_access_share_and_once_close(self):
        self.assertTrue(callable(getattr(self.m._Native, 'open', None)), 'open transport missing')
        api = self.fixture.api()
        for observe in (False, True):
            for directory in (False, True):
                owner, code = api.open('private', directory, observe=observe)
                self.assertEqual(code, 0)
                args = self.fixture.kernel.CreateFileW.calls[-1]
                self.assertEqual(args[1], 0x120081 if observe else 0x60000)
                self.assertEqual(args[2], 7)
                self.assertEqual(args[4], 3)
                self.assertEqual(args[5], 0x200000 | (0x2000000 if directory else 0))
                owner.close()
                count = len(self.fixture.kernel.CloseHandle.calls)
                owner.close()
                self.assertEqual(len(self.fixture.kernel.CloseHandle.calls), count)
                self.assertTrue(owner.confirmed)
        self.assertEqual(self.fixture.kernel.CloseHandle.argtypes, [ctypes.c_void_p])
        self.assertIs(self.fixture.kernel.CloseHandle.restype, ctypes.c_int32)
        self.assertIs(self.fixture.advapi.SetSecurityInfo.restype, ctypes.c_uint32)

    def test_open_denials_and_unknown_close_are_not_retried(self):
        self.assertTrue(callable(getattr(self.m._Native, 'open', None)))
        api = self.fixture.api()
        self.fixture.file_result = self.m._INVALID
        with patch.object(ctypes, 'get_last_error', create=True, return_value=32):
            owner, code = api.open('private', False)
        self.assertIsNone(owner)
        self.assertEqual(code, 32)
        self.fixture.file_result, self.fixture.close_result = 70, 0
        owner, _ = api.open('private', False)
        with self.assertRaises(RuntimeError):
            owner.close()
        owner.close()
        self.assertFalse(owner.confirmed)
        self.assertEqual(len(self.fixture.kernel.CloseHandle.calls), 1)

    def test_fixed_sddl_dacl_set_and_free_confirmation(self):
        self.assertTrue(callable(getattr(self.m._Native, 'set_marker', None)), 'DACL transport missing')
        api = self.fixture.api()
        owner, _ = api.open('private', False)
        for marker in (0x80, 0x100):
            self.assertEqual(api.set_marker(owner.value, 'S-1-5-21-1', marker), 0)
            text = self.fixture.advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.calls[-1][0]
            self.assertEqual(text, f'D:P(A;;FA;;;S-1-5-21-1)(A;;FA;;;SY)(A;;FA;;;BA)(A;;0x{marker:x};;;WD)')
            args = self.fixture.advapi.SetSecurityInfo.calls[-1]
            self.assertEqual(args[:3], (owner.value, 1, 0x80000004))
            self.assertEqual(args[3:5], (None, None))
            self.assertEqual(args[-1], None)
        self.assertEqual(len(self.fixture.kernel.LocalFree.calls), 2)
        self.fixture.set_result = 5
        self.assertEqual(api.set_marker(owner.value, 'S-1-5-21-1', 0x100), 5)
        owner.close()

    def test_nonnull_dacl_validation_and_query_body_cleanup_preserve_identity(self):
        self.assertTrue(callable(getattr(self.m._Native, 'set_marker', None)))
        for field, value in (('convert_ok', 0), ('valid', 0), ('present', 0), ('dacl', False)):
            fixture = ApiFixture(self.m)
            setattr(fixture, field, value)
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                fixture.api().set_marker(70, 'S-1-5-21-1', 0x80)
            self.assertEqual(len(fixture.kernel.LocalFree.calls), 1)
            self.assertEqual(fixture.advapi.SetSecurityInfo.calls, [])
        for kind in (KeyboardInterrupt, SystemExit):
            fixture = ApiFixture(self.m)
            original = kind('private value')
            fixture.convert_error, fixture.free_error = original, RuntimeError('private cleanup')
            with self.assertRaises(kind) as caught:
                fixture.api().set_marker(70, 'S-1-5-21-1', 0x80)
            self.assertIs(caught.exception, original)
            self.assertEqual(len(fixture.kernel.LocalFree.calls), 1)

    def test_ntfs_gate_and_nonwindows_fail_before_loading(self):
        self.assertTrue(callable(getattr(self.m._Native, 'require_ntfs', None)))
        api = self.fixture.api()
        api.require_ntfs(70)
        self.fixture.filesystem = 'ReFS'
        with self.assertRaises(RuntimeError):
            api.require_ntfs(70)
        with patch.object(self.m.os, 'name', 'posix'), patch.object(ctypes, 'WinDLL', create=True) as loader:
            with self.assertRaises(RuntimeError):
                self.m._Native()
            loader.assert_not_called()

    def test_acquired_open_validation_interrupt_closes_once_preserving_identity(self):
        api = self.fixture.api()
        lines, start = inspect.getsourcelines(self.m._Native.open)
        target = next(start + ordinal for ordinal, line in enumerate(lines)
                      if line.strip() == 'if value == _INVALID:')
        for kind in (KeyboardInterrupt, SystemExit):
            original = kind('private acquisition')
            fired = []
            def trace(frame, event, arg):
                if frame.f_code is self.m._Native.open.__code__ and event == 'line' and frame.f_lineno == target:
                    fired.append(True)
                    raise original
                return trace
            before = len(self.fixture.kernel.CloseHandle.calls)
            previous = sys.gettrace()
            try:
                sys.settrace(trace)
                with self.assertRaises(kind) as caught:
                    api.open('private', False)
            finally:
                sys.settrace(previous)
            self.assertIs(caught.exception, original)
            self.assertEqual(fired, [True])
            self.assertEqual(len(self.fixture.kernel.CloseHandle.calls), before + 1)

    def test_observer_and_window_effect_contracts_exist(self):
        for cls, method in ((self.m._Observer, 'sample'), (self.m, '_event'), (self.m, '_run_variant')):
            self.assertTrue(callable(getattr(cls, method, None)), method + ' missing')

    def test_independent_observer_owns_full_share_handles_real_metadata_and_bytes(self):
        self.assertTrue(callable(getattr(self.m._Observer, 'sample', None)), 'observer missing')
        reader = SimpleNamespace(cleanup_unconfirmed=False, read=lambda h: raw_marker())
        api = self.fixture.api()
        with patch.object(self.m, 'WindowsStartupSecurityReader', return_value=reader):
            observer = self.m._Observer(api, 'private-parent', 'private-leaf')
        before = observer.sample('parent')
        self.assertTrue(before['parent'].directory)
        self.assertFalse(before['leaf'].directory)
        self.assertEqual(before['bytes'], self.m._CONTENT)
        self.assertEqual(before['raw'], raw_marker())
        self.assertTrue(all(args[1:3] == (0x120081, 7) for args in self.fixture.kernel.CreateFileW.calls))
        observer.close()
        self.assertEqual(self.fixture.kernel.CloseHandle.calls, [(71,), (70,)])
        observer.close()
        self.assertEqual(len(self.fixture.kernel.CloseHandle.calls), 2)
        with self.assertRaises(RuntimeError):
            observer.sample('leaf')

    def test_observer_partial_open_and_read_faults_retire_all_once(self):
        api = self.fixture.api()
        original = KeyboardInterrupt('private observer')
        def open_then_fail(*args):
            if len(self.fixture.kernel.CreateFileW.calls) == 2:
                raise original
            return self.fixture.open(*args)
        self.fixture.kernel.CreateFileW.action = open_then_fail
        reader = SimpleNamespace(cleanup_unconfirmed=False, read=lambda h: raw_marker())
        with patch.object(self.m, 'WindowsStartupSecurityReader', return_value=reader):
            with self.assertRaises(KeyboardInterrupt) as caught:
                self.m._Observer(api, 'parent', 'leaf')
        self.assertIs(caught.exception, original)
        self.assertEqual(len(self.fixture.kernel.CloseHandle.calls), 1)

    def test_localfree_unknown_result_fails_without_retry(self):
        self.fixture.free_result = 90
        api = self.fixture.api()
        with self.assertRaises(RuntimeError):
            api.set_marker(70, HOST, 0x80)
        self.assertEqual(len(self.fixture.kernel.LocalFree.calls), 1)

    def test_observer_rejects_native_boolean_metadata_and_short_read(self):
        for fault in ('directory', 'delete', 'read'):
            fixture = ApiFixture(self.m)
            api = fixture.api()
            reader = SimpleNamespace(cleanup_unconfirmed=False, read=lambda h: raw_marker())
            with patch.object(self.m, 'WindowsStartupSecurityReader', return_value=reader):
                observer = self.m._Observer(api, 'parent', 'leaf')
            original_info = fixture.kernel.GetFileInformationByHandleEx.action
            def info(handle, kind, output, size):
                result = original_info(handle, kind, output, size)
                if kind == 1:
                    value = ctypes.cast(output, ctypes.POINTER(self.m._INFO_CLASSES[kind])).contents
                    if fault == 'directory': value.Directory = 2
                    if fault == 'delete': value.DeletePending = 2
                return result
            fixture.kernel.GetFileInformationByHandleEx.action = info
            if fault == 'read': fixture.kernel.ReadFile.action = lambda *a: 0
            with self.assertRaises(RuntimeError): observer.sample('parent')
            observer.close()


class PrivateDaclWindowContractTests(unittest.TestCase):
    def setUp(self):
        self.m = importlib.import_module('tests.windows_private_dacl_fixture')

    def test_success_and_blocked_are_actual_effect_not_return_code(self):
        self.assertTrue(callable(getattr(self.m, '_event', None)), 'event contract missing')
        for opener in ('new', 'preexisting'):
            opened = 0 if opener == 'new' else None
            changed = self.m._event('parent', 'pinned', opened, 0, snapshot(), snapshot(0x100), HOST)
            self.assertEqual(changed['effect'], 'changed')
            self.assertTrue(changed['sd_changed'])
            for code in (5, 32, 33):
                blocked = self.m._event('leaf', 'pinned', opened, code, snapshot(), snapshot(), HOST)
                self.assertEqual(blocked['effect'], 'blocked')
                self.assertFalse(blocked['sd_changed'])
        blocked = self.m._event('parent', 'pinned', 32, None, snapshot(), snapshot(), HOST)
        self.assertEqual(blocked['open_result'], 32)

    def test_effect_unknown_identity_bytes_and_marker_drift_fail(self):
        self.assertTrue(callable(getattr(self.m, '_event', None)))
        changes = [lambda s: s.update(bytes=b'changed'),
                   lambda s: s.update(parent=replace(s['parent'], file_id=b'q' * 16)),
                   lambda s: s.update(leaf=replace(s['leaf'], volume_serial=2)),
                   lambda s: s.update(raw=raw_marker(0x80)),
                   lambda s: s.update(raw=descriptor(dacl=acl((ace(),))))]
        for change in changes:
            after = snapshot(0x100)
            change(after)
            with self.assertRaises(RuntimeError):
                self.m._event('parent', 'pinned', 0, 0, snapshot(), after, HOST)
        for opened, status in ((0, 1), (4, None), (True, 0), (0, True), (0, None)):
            with self.assertRaises(RuntimeError):
                self.m._event('parent', 'pinned', opened, status, snapshot(), snapshot(), HOST)

    def test_metadata_change_observed_without_revalidation_or_false_identity(self):
        self.assertTrue(callable(getattr(self.m, '_event', None)))
        after = snapshot(0x100)
        after['parent'] = replace(after['parent'], change_time=9)
        result = self.m._event('parent', 'pinned', 0, 0, snapshot(), after, HOST)
        self.assertTrue(result['metadata_changed'])
        self.assertTrue(result['identity_stable'])


class PrivateDaclLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.m = importlib.import_module('tests.windows_private_dacl_fixture')

    def test_public_entry_validates_before_native_or_temp_and_sanitizes(self):
        self.assertTrue(callable(getattr(self.m, '_at_stage', None)), 'finite stage wrapper missing')
        self.assertTrue(callable(getattr(self.m, 'failure_message', None)), 'finite diagnostic validator missing')
        with patch.object(self.m, '_run_variant', return_value=b'finite') as run:
            with patch.object(self.m.os, 'name', 'nt'):
                try:
                    result = self.m.run_variant('parent', 'new')
                except RuntimeError:
                    self.fail('public entry did not delegate')
                self.assertEqual(result, b'finite')
            run.assert_called_once_with('parent', 'new')
            for target, opener in (('root', 'new'), ('parent', 'other'), (True, 'new')):
                with self.assertRaises(RuntimeError) as caught:
                    self.m.run_variant(target, opener)
                self.assertEqual(caught.exception.args, (self.m._FAILURE,))
            self.assertEqual(run.call_count, 1)
        original = KeyboardInterrupt('private')
        with patch.object(self.m.os, 'name', 'nt'), patch.object(self.m, '_run_variant', side_effect=original):
            with self.assertRaises(KeyboardInterrupt) as caught:
                self.m.run_variant('leaf', 'preexisting')
            self.assertIs(caught.exception, original)
        for stage in self.m._STAGES:
            private = RuntimeError('PRIVATE-VALUE-DO-NOT-OUTPUT')
            with self.assertRaises(RuntimeError) as caught:
                self.m._at_stage(stage, lambda: (_ for _ in ()).throw(private))
            expected = self.m._FAILURE + ':' + stage
            self.assertEqual(self.m.failure_message(caught.exception), expected)
            with patch.object(self.m.os, 'name', 'nt'), patch.object(
                    self.m, '_run_variant', side_effect=caught.exception):
                with self.assertRaises(RuntimeError) as outer:
                    self.m.run_variant('parent', 'new')
            self.assertEqual(self.m.failure_message(outer.exception), expected)
        for kind in (KeyboardInterrupt, SystemExit):
            original = kind('private interrupt')
            with self.assertRaises(kind) as caught:
                self.m._at_stage('prepare', lambda: (_ for _ in ()).throw(original))
            self.assertIs(caught.exception, original)
        class Hostile(RuntimeError):
            def __getattribute__(self, name):
                if name in ('args', 'stage', '__dict__'):
                    raise AssertionError('arbitrary exception attribute read')
                return super().__getattribute__(name)
        for error in (private, Hostile('private'), self.m._StageFailure('private'),
                      self.m._StageFailure('prepare', 'private')):
            self.assertEqual(self.m.failure_message(error), self.m._FAILURE)

    def test_window_controller_has_real_order_and_pinned_borrowed_sampling(self):
        self.assertTrue(callable(getattr(self.m, '_windows', None)), 'window controller missing')
        for opener in ('new', 'preexisting'):
            for blocked in (False, True):
                log, marker = [], [0x80]
                class Owner:
                    confirmed = close_confirmed = True
                    def close(self): log.append('close-pin')
                pin = Owner()
                fixture = SimpleNamespace(host=HOST, pin=None)
                fixture.reset = lambda: (log.append('reset'), marker.__setitem__(0, 0x80))
                fixture.sample = lambda: (log.append('sample'), snapshot(marker[0]))[1]
                fixture.start_pin = lambda: (log.append('pin'), setattr(fixture, 'pin', pin))
                fixture.pinned_sample = lambda: (log.append('borrow'), snapshot(marker[0]))[1]
                def operate():
                    log.append('operate')
                    denied = blocked and fixture.pin is not None
                    if not denied: marker[0] = 0x100
                    return (None if opener == 'preexisting' else 0), (5 if denied else 0)
                fixture.operate = operate
                data = self.m._windows(fixture, 'parent')
                self.assertEqual([event['window'] for event in data], ['unpinned', 'pinned', 'released'])
                self.assertEqual(log, ['reset','sample','operate','sample','reset','sample','pin',
                                       'borrow','operate','borrow','close-pin','reset','sample','operate','sample'])
                self.assertIsNone(fixture.pin)
                self.assertEqual(data[1]['effect'], 'blocked' if blocked else 'changed')
        # Fail each real controller callback position, not a mocked controller.
        sequence = ('unpinned_reset', 'unpinned_before', 'unpinned_operate', 'unpinned_after',
                    'prepin_reset', 'prepin_sample', 'start_pin', 'pinned_before',
                    'pinned_operate', 'pinned_after', 'release_pin', 'released_reset',
                    'released_before', 'released_operate', 'released_after')
        for failing, stage in enumerate(sequence):
            count, marker = [0], [0x80]
            def invoke(action):
                ordinal = count[0]
                count[0] += 1
                if ordinal == failing:
                    raise RuntimeError('PRIVATE-VALUE-DO-NOT-OUTPUT')
                return action()
            fixture = SimpleNamespace(host=HOST, pin=None)
            owner = SimpleNamespace(close_confirmed=True, close=lambda: invoke(lambda: None))
            fixture.reset = lambda: invoke(lambda: marker.__setitem__(0, 0x80))
            fixture.sample = fixture.pinned_sample = lambda: invoke(lambda: snapshot(marker[0]))
            fixture.start_pin = lambda: invoke(lambda: setattr(fixture, 'pin', owner))
            fixture.operate = lambda: invoke(lambda: (marker.__setitem__(0, 0x100), (0, 0))[1])
            with self.subTest(stage=stage), self.assertRaises(RuntimeError) as caught:
                self.m._windows(fixture, 'parent')
            self.assertTrue(callable(getattr(self.m, 'failure_message', None)), 'finite stage wrapper missing')
            self.assertEqual(self.m.failure_message(caught.exception), self.m._FAILURE + ':' + stage)
            self.assertEqual(count[0], failing + 1)

    def test_body_interrupt_stops_later_windows_and_cleanup_preserves_identity(self):
        self.assertTrue(callable(getattr(self.m, '_windows', None)))
        original = SystemExit('private')
        log = []
        fixture = SimpleNamespace(host=HOST, pin=None, reset=lambda: log.append('reset'),
            sample=lambda: snapshot(), operate=lambda: (_ for _ in ()).throw(original))
        with self.assertRaises(SystemExit) as caught:
            self.m._windows(fixture, 'leaf')
        self.assertIs(caught.exception, original)
        self.assertEqual(log, ['reset'])

    def test_pinned_sampling_delegates_only_real_owner_handles(self):
        self.assertTrue(callable(getattr(self.m, '_Fixture', None)), 'fixture owner missing')
        fixture = object.__new__(self.m._Fixture)
        fixture.target, fixture.initial = 'parent', None
        calls = []
        backend = SimpleNamespace(query=lambda h: (calls.append(('query', h)), snapshot()['parent' if h == 21 else 'leaf'])[1],
            query_security=lambda h: (calls.append(('security', h)), raw_marker())[1],
            read=lambda h, offset, count: (calls.append(('read', h, offset, count)), self.m._CONTENT)[1])
        fixture.pin = SimpleNamespace(_handles=[20,21,22], _backend=backend,
                                      _require_open=lambda: calls.append(('require',)))
        value = fixture.pinned_sample()
        self.assertEqual(value, snapshot())
        self.assertEqual(calls, [('require',),('query',21),('query',22),('security',21),('read',22,0,20)])

    def test_complete_fixture_cleanup_precedes_wire_and_body_identity_wins(self):
        original = KeyboardInterrupt('private')
        log = []
        fixture = SimpleNamespace(prepare=lambda: log.append('prepare'),
                                  close=lambda: log.append('close'))
        windows = PrivateDaclTransportTests().receipt()['windows']
        with patch.object(self.m, '_Fixture', return_value=fixture), patch.object(self.m, '_windows', return_value=windows):
            wire = self.m._run_variant('parent', 'new')
        self.assertEqual(log, ['prepare','close'])
        self.assertTrue(self.m.validate_wire(wire)['cleanup_confirmed'])
        def fail_close():
            log.append('close')
            raise RuntimeError('private cleanup')
        fixture.close = fail_close
        with patch.object(self.m, '_Fixture', return_value=fixture), patch.object(self.m, '_windows', side_effect=original):
            with self.assertRaises(KeyboardInterrupt) as caught:
                self.m._run_variant('leaf', 'new')
        self.assertIs(caught.exception, original)
        with patch.object(self.m, '_Fixture', return_value=fixture), patch.object(self.m, '_windows', return_value=windows):
            with self.assertRaises(RuntimeError) as caught:
                self.m._run_variant('leaf', 'new')
        self.assertTrue(callable(getattr(self.m, 'failure_message', None)), 'finite diagnostic validator missing')
        self.assertEqual(self.m.failure_message(caught.exception), self.m._FAILURE + ':cleanup')
        fixture.prepare = lambda: (_ for _ in ()).throw(RuntimeError('private prepare'))
        with patch.object(self.m, '_Fixture', return_value=fixture), patch.object(self.m, '_windows') as windows_call:
            with self.assertRaises(RuntimeError) as caught:
                self.m._run_variant('leaf', 'new')
        self.assertEqual(self.m.failure_message(caught.exception), self.m._FAILURE + ':prepare')
        windows_call.assert_not_called()

    def test_initial_identity_stays_bound_across_all_windows(self):
        fixture = object.__new__(self.m._Fixture)
        fixture.target, fixture.initial = 'parent', snapshot()
        drift = snapshot()
        drift['parent'] = replace(drift['parent'], file_id=b'q' * 16)
        fixture.observer = SimpleNamespace(sample=lambda target: drift)
        with self.assertRaises(RuntimeError):
            fixture.sample()

    def test_full_private_fixture_four_variants_real_controller_budget(self):
        import os
        for target in ('parent', 'leaf'):
            for opener in ('new', 'preexisting'):
                fixture = ApiFixture(self.m)
                api = fixture.api()
                markers, reads = {True:0x80, False:0x80}, []
                protected = {True:False, False:False}
                leaf_accessible, preparation = [True], []
                original_set = api.set_marker
                original_convert = fixture.advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.action
                converted_marker = [None]
                def convert(text, *arguments):
                    converted_marker[0] = 0x100 if '(A;;0x100;;;WD)' in text else 0x80
                    return original_convert(text, *arguments)
                fixture.advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.action = convert
                def set_security(handle, kind, information, *arguments):
                    directory = fixture.directories[handle]
                    # A low-level preparation contract, not a claim that this
                    # simulated denial reproduces the Windows failure cause.
                    # Parent updates may affect a still-unprotected child.
                    # This actor deliberately has no implicit-owner grant;
                    # the double is not a complete Windows access evaluator.
                    if directory and not protected[False]:
                        leaf_accessible[0] = False
                    protected[directory] = bool(information & 0x80000000)
                    markers[directory] = converted_marker[0]
                    preparation.append(('set', 'parent' if directory else 'leaf'))
                    return fixture.set_result
                fixture.advapi.SetSecurityInfo.action = set_security
                def open_file(*arguments):
                    if not arguments[5] & 0x2000000 and not leaf_accessible[0]:
                        return self.m._INVALID
                    return fixture.open(*arguments)
                fixture.kernel.CreateFileW.action = open_file
                def close_handle(handle):
                    preparation.append(('close', 'parent' if fixture.directories[handle] else 'leaf'))
                    return fixture.close(handle)
                fixture.kernel.CloseHandle.action = close_handle
                def security(handle):
                    directory = fixture.directories[handle]
                    raw = raw_marker(markers[directory])
                    if not protected[directory]:
                        raw = raw[:2] + (0x8004).to_bytes(2, 'little') + raw[4:]
                    reads.append((directory, markers[directory], protected[directory]))
                    return raw
                reader = SimpleNamespace(cleanup_unconfirmed=False, read=security)
                class Pin:
                    _handles = [100,101]
                    close_confirmed = False
                    def _require_open(self): pass
                    def close(self): self.close_confirmed = True
                pin = Pin()
                fixture.directories.update({100:True,101:False})
                def query(handle):
                    role = 'parent' if fixture.directories[handle] else 'leaf'
                    return replace(snapshot()[role], file_id=bytes([1 if role == 'parent' else 2])+b'\0'*15)
                pin._backend = SimpleNamespace(query=query, query_security=security,
                                                read=lambda handle, offset, count: self.m._CONTENT)
                with patch.object(self.m, '_Native', return_value=api), \
                     patch.object(self.m, 'WindowsStartupHostIdentity', return_value=SimpleNamespace(capture=lambda:HOST, cleanup_unconfirmed=False)), \
                     patch.object(self.m, 'WindowsStartupSecurityReader', return_value=reader), \
                     patch.object(self.m, '_local_components', return_value=('C:',['temp','parent','leaf'])), \
                     patch.object(self.m, 'pin_startup_file', return_value=pin) as create_pin, \
                     patch.object(ctypes, 'get_last_error', create=True, return_value=5):
                    try:
                        wire = self.m._run_variant(target, opener)
                    except RuntimeError as error:
                        self.fail('private preparation did not protect leaf before parent: ' +
                                  self.m.failure_message(error))
                data = self.m.validate_wire(wire)
                self.assertEqual(preparation[:4], [('set','leaf'),('close','leaf'),
                                                   ('set','parent'),('close','parent')])
                self.assertEqual(reads[:2], [(True,0x80,True),(False,0x80,True)])
                self.assertTrue(all(value[2] for value in reads))
                self.assertEqual([value[1] for value in reads[2:]],
                                 [0x80,0x100,0x80,0x80,0x100,0x80,0x100])
                self.assertTrue(all(event['effect'] == 'changed' for event in data['windows']))
                self.assertEqual(len(fixture.advapi.SetSecurityInfo.calls), 8)
                self.assertEqual(len(fixture.kernel.LocalFree.calls), 8)
                self.assertEqual(len(fixture.kernel.CreateFileW.calls), 5 if opener == 'preexisting' else 10)
                self.assertEqual(len(fixture.kernel.CloseHandle.calls), 5 if opener == 'preexisting' else 10)
                self.assertEqual(len(reads), 9)
                self.assertTrue(pin.close_confirmed)
                path = create_pin.call_args.args[0]
                self.assertFalse(os.path.exists(os.path.dirname(os.path.dirname(path))))
                for role, kind in ((role, kind) for role in ('parent', 'leaf')
                                   for kind in (RuntimeError, KeyboardInterrupt, SystemExit)):
                    roots = []
                    original = kind('PRIVATE-VALUE-DO-NOT-OUTPUT')
                    before_close = len(fixture.kernel.CloseHandle.calls)
                    real_create = self.m.tempfile.mkdtemp
                    def create(*args, **kwargs):
                        root = real_create(*args, **kwargs)
                        roots.append(root)
                        return root
                    def fail_set(handle, host, marker):
                        if fixture.directories[handle] == (role == 'parent'):
                            raise original
                        return original_set(handle, host, marker)
                    with patch.object(self.m, '_Native', return_value=api), \
                         patch.object(self.m, 'WindowsStartupHostIdentity', return_value=SimpleNamespace(capture=lambda:HOST, cleanup_unconfirmed=False)), \
                         patch.object(self.m, '_local_components', return_value=('C:',['temp','parent','leaf'])), \
                         patch.object(self.m.tempfile, 'mkdtemp', side_effect=create), \
                         patch.object(api, 'set_marker', side_effect=fail_set):
                        with self.assertRaises(kind) as caught:
                            self.m._run_variant(target, opener)
                    self.assertTrue(callable(getattr(self.m, 'failure_message', None)), 'finite diagnostic validator missing')
                    if kind is RuntimeError:
                        self.assertEqual(self.m.failure_message(caught.exception),
                                         self.m._FAILURE + ':initial_' + role + '_set')
                    else:
                        self.assertIs(caught.exception, original)
                    self.assertEqual(len(fixture.kernel.CloseHandle.calls) - before_close,
                                     2 if role == 'parent' else 1)
                    self.assertEqual(len(roots), 1)
                    self.assertFalse(os.path.exists(roots[0]))
                # An independent open denial must remain a finite failure,
                # even after the new ordering has protected that object.
                for role in ('leaf', 'parent'):
                    roots = []
                    before_set = len(fixture.advapi.SetSecurityInfo.calls)
                    def deny_open(*arguments):
                        if bool(arguments[5] & 0x2000000) == (role == 'parent'):
                            return self.m._INVALID
                        return fixture.open(*arguments)
                    with patch.object(self.m, '_Native', return_value=api), \
                         patch.object(self.m, 'WindowsStartupHostIdentity', return_value=SimpleNamespace(capture=lambda:HOST, cleanup_unconfirmed=False)), \
                         patch.object(self.m, '_local_components', return_value=('C:',['temp','parent','leaf'])), \
                         patch.object(self.m.tempfile, 'mkdtemp', side_effect=create), \
                         patch.object(fixture.kernel.CreateFileW, 'action', deny_open), \
                         patch.object(ctypes, 'get_last_error', create=True, return_value=5):
                        with self.assertRaises(RuntimeError) as caught:
                            self.m._run_variant(target, opener)
                    self.assertEqual(self.m.failure_message(caught.exception),
                                     self.m._FAILURE + ':initial_' + role + '_open')
                    self.assertEqual(len(fixture.advapi.SetSecurityInfo.calls) - before_set,
                                     1 if role == 'parent' else 0)
                    self.assertEqual(len(roots), 1)
                    self.assertFalse(os.path.exists(roots[0]))

    def test_registration_interrupt_retires_open_observer_and_pin_once(self):
        for slot in ('pending', 'observer', 'pin'):
            for kind in (KeyboardInterrupt, SystemExit):
                original, closes = kind('private registration'), []
                class Broken(self.m._Fixture):
                    def __setattr__(self, name, value):
                        if name == slot and value is not None:
                            raise original
                        object.__setattr__(self, name, value)
                value = object.__new__(Broken)
                for name, item in (('pending',None),('observer',None),('pin',None),('writer',None),
                                   ('target','parent'),('parent','private-parent'),('leaf','private-leaf')):
                    object.__setattr__(value, name, item)
                owner = SimpleNamespace(value=70, confirmed=True, close_confirmed=True,
                                        close=lambda: closes.append('close'))
                value.api = SimpleNamespace(open=lambda *a, **k: (owner,0))
                with patch.object(self.m, '_Observer', return_value=owner), \
                     patch.object(self.m, 'pin_startup_file', return_value=owner):
                    with self.assertRaises(kind) as caught:
                        if slot == 'pending': value.reset()
                        elif slot == 'pin': value.start_pin()
                        else:
                            self.assertTrue(callable(getattr(value,'start_observer',None)), 'observer registration helper missing')
                            value.start_observer()
                self.assertIs(caught.exception, original)
                self.assertEqual(closes, ['close'])

    def test_cleanup_never_deletes_uncreated_parent_or_leaf(self):
        fixture = object.__new__(self.m._Fixture)
        fixture.pending = fixture.pin = fixture.writer = fixture.observer = None
        fixture.root, fixture.parent, fixture.leaf = 'private-root','uncreated-parent','uncreated-leaf'
        fixture.parent_created = fixture.leaf_created = False
        with patch.object(self.m.os,'unlink') as unlink, patch.object(self.m.os,'rmdir') as rmdir:
            fixture.close()
        unlink.assert_not_called()
        rmdir.assert_called_once_with('private-root')

    def test_cleanup_attempts_all_owned_objects_and_body_original_wins(self):
        fixture = object.__new__(self.m._Fixture)
        fixture.root = fixture.parent = fixture.leaf = None
        fixture.parent_created = fixture.leaf_created = False
        calls = []
        def close(name, fail=False):
            calls.append(name)
            if fail: raise RuntimeError('private close')
        for name in ('pending','pin','writer','observer'):
            setattr(fixture,name,SimpleNamespace(confirmed=True,close_confirmed=True,
                close=lambda n=name: close(n,n=='pending')))
        with self.assertRaises(RuntimeError): fixture.close()
        self.assertEqual(calls,['pending','pin','writer','observer'])

    def test_native_outer_boundary_never_leaks_private_exception(self):
        import traceback
        self.assertTrue(callable(getattr(self.m, '_at_stage', None)), 'finite stage wrapper missing')
        self.assertTrue(callable(getattr(self.m, 'failure_message', None)), 'finite diagnostic validator missing')
        private = RuntimeError('PRIVATE-VALUE-DO-NOT-OUTPUT')
        case = WindowsPrivateDaclWindowNativeTests('test_private_parent_dacl_three_windows')
        with patch.object(self.m,'run_variant',side_effect=private):
            with self.assertRaises(AssertionError) as caught:
                case._observe('parent')
        rendered = ''.join(traceback.format_exception(caught.exception))
        self.assertNotIn('PRIVATE-VALUE-DO-NOT-OUTPUT',rendered)
        self.assertEqual(caught.exception.args,('private_dacl_window_failed',))
        with self.assertRaises(RuntimeError) as staged:
            self.m._at_stage('initial_parent_set', lambda: (_ for _ in ()).throw(private))
        with patch.object(self.m, 'run_variant', side_effect=staged.exception):
            with self.assertRaises(AssertionError) as caught:
                case._observe('parent')
        rendered = ''.join(traceback.format_exception(caught.exception))
        self.assertNotIn('PRIVATE-VALUE-DO-NOT-OUTPUT', rendered)
        self.assertEqual(caught.exception.args,
                         ('private_dacl_window_failed:initial_parent_set:parent:preexisting',))
        for target in ('PRIVATE-VALUE-DO-NOT-OUTPUT', True):
            with patch.object(self.m, 'run_variant', side_effect=staged.exception):
                with self.assertRaises(AssertionError) as caught:
                    case._observe(target)
            self.assertEqual(caught.exception.args, (self.m._FAILURE,))

    def test_created_parent_leaf_registration_interrupt_removes_owned_tree(self):
        import builtins
        import os
        for marker in ('self.parent_created = True','self.leaf_created = True'):
            for kind in (KeyboardInterrupt,SystemExit):
                lines, start = inspect.getsourcelines(self.m._Fixture.prepare)
                target = next(start+i for i,line in enumerate(lines) if line.strip()==marker)
                original = kind('private creation')
                identity = SimpleNamespace(capture=lambda:HOST,cleanup_unconfirmed=False)
                with patch.object(self.m,'WindowsStartupHostIdentity',return_value=identity), \
                     patch.object(self.m,'_Native',return_value=SimpleNamespace()):
                    fixture = self.m._Fixture('parent','new')
                fired = []
                streams = []
                real_open = builtins.open
                def tracked_open(*args, **kwargs):
                    stream = real_open(*args, **kwargs)
                    streams.append(stream)
                    return stream
                def trace(frame,event,arg):
                    if frame.f_code is self.m._Fixture.prepare.__code__ and event=='line' and frame.f_lineno==target:
                        fired.append(True)
                        raise original
                    return trace
                previous = sys.gettrace()
                try:
                    sys.settrace(trace)
                    with patch.object(builtins,'open',side_effect=tracked_open):
                        with self.assertRaises(kind) as caught: fixture.prepare()
                finally:
                    sys.settrace(previous)
                self.assertIs(caught.exception,original)
                self.assertEqual(fired,[True])
                self.assertTrue(all(stream.closed for stream in streams))
                try:
                    try:
                        fixture.close()
                    except OSError:
                        self.fail('created object was not registered for cleanup')
                    self.assertFalse(os.path.exists(fixture.root))
                finally:
                    # A RED must not itself leave its uniquely owned objects.
                    if os.path.exists(fixture.leaf or ''): os.unlink(fixture.leaf)
                    if os.path.exists(fixture.parent): os.rmdir(fixture.parent)
                    if os.path.exists(fixture.root): os.rmdir(fixture.root)

    def test_acquired_temp_root_registration_interrupt_removes_exact_owned_root(self):
        import os
        import builtins
        # A diagnostic wrapper must not introduce an unregistered-resource
        # return window around mkdtemp/mkdir/exclusive open.
        for phase in ('create_root', 'create_parent', 'create_leaf'):
            original, roots, streams = KeyboardInterrupt('private wrapper return'), [], []
            real_create, real_open = self.m.tempfile.mkdtemp, builtins.open
            def create(*args, **kwargs):
                root = real_create(*args, **kwargs)
                roots.append(root)
                return root
            def tracked_open(*args, **kwargs):
                stream = real_open(*args, **kwargs)
                streams.append(stream)
                return stream
            def trace(frame, event, value):
                if (frame.f_code is self.m._at_stage.__code__ and event == 'return'
                        and frame.f_locals['stage'] == phase):
                    raise original
                return trace
            identity = SimpleNamespace(capture=lambda:HOST, cleanup_unconfirmed=False)
            with patch.object(self.m, 'WindowsStartupHostIdentity', return_value=identity), \
                 patch.object(self.m, '_Native', return_value=SimpleNamespace()), \
                 patch.object(self.m.tempfile, 'mkdtemp', side_effect=create), \
                 patch.object(builtins, 'open', side_effect=tracked_open), \
                 patch.object(self.m, '_local_components', side_effect=original):
                fixture = self.m._Fixture('parent', 'new')
                previous = sys.gettrace()
                try:
                    sys.settrace(trace)
                    with self.assertRaises(KeyboardInterrupt) as caught:
                        fixture.prepare()
                finally:
                    sys.settrace(previous)
                self.assertIs(caught.exception, original)
            try:
                try:
                    fixture.close()
                except OSError:
                    pass
                with self.subTest(phase=phase):
                    self.assertTrue(all(stream.closed for stream in streams))
                    self.assertEqual(len(roots), 1)
                    self.assertFalse(os.path.exists(roots[0]))
            finally:
                for stream in streams:
                    stream.close()
                if os.path.exists(fixture.leaf or ''): os.unlink(fixture.leaf)
                if os.path.exists(fixture.parent or ''): os.rmdir(fixture.parent)
                if roots and os.path.exists(roots[0]): os.rmdir(roots[0])
        for kind in (KeyboardInterrupt,SystemExit):
            original, roots = kind('private root'), []
            class Broken(self.m._Fixture):
                def __setattr__(self,name,value):
                    if name=='root' and value is not None: raise original
                    object.__setattr__(self,name,value)
            identity = SimpleNamespace(capture=lambda:HOST,cleanup_unconfirmed=False)
            real_create = self.m.tempfile.mkdtemp
            def create(*args,**kwargs):
                root = real_create(*args,**kwargs)
                roots.append(root)
                return root
            with patch.object(self.m,'WindowsStartupHostIdentity',return_value=identity), \
                 patch.object(self.m,'_Native',return_value=SimpleNamespace()), \
                 patch.object(self.m.tempfile,'mkdtemp',side_effect=create):
                fixture = Broken('parent','new')
                with self.assertRaises(kind) as caught: fixture.prepare()
            self.assertIs(caught.exception,original)
            self.assertEqual(len(roots),1)
            try:
                self.assertFalse(os.path.exists(roots[0]))
            finally:
                if os.path.exists(roots[0]): os.rmdir(roots[0])


@unittest.skipUnless(sys.platform == 'win32', 'native Windows only')
class WindowsPrivateDaclWindowNativeTests(unittest.TestCase):
    def _observe(self, target):
        from tests.windows_private_dacl_fixture import run_variant, validate_wire, failure_message
        for opener in ('preexisting', 'new'):
            try:
                wire = run_variant(target, opener)
                validate_wire(wire)
            except BaseException as error:
                message = failure_message(error)
                if (message != 'private_dacl_window_failed'
                        and type(target) is str and target in ('parent', 'leaf')):
                    message += ':' + target + ':' + opener
                else:
                    message = 'private_dacl_window_failed'
                raise AssertionError(message) from None
            print(wire.decode('ascii'), end='')

    def test_private_parent_dacl_three_windows(self):
        self._observe('parent')

    def test_private_leaf_dacl_three_windows(self):
        self._observe('leaf')
