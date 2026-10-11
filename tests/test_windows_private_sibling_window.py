"""Private sibling portable contracts; no native credit."""
import copy
import ctypes
import inspect
from dataclasses import replace
import linecache
import sys
import tempfile
import unittest
from unittest.mock import patch
from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from tests.test_windows_startup_security_native import Function

import tests.windows_private_sibling_fixture as m
from icode.windows_startup_host_identity import WindowsStartupHostIdentity
from icode.windows_startup_pin import StartupFileMetadata
from tests.test_windows_private_dacl_window import ApiFixture, raw_marker, snapshot


class _Harness:
    def __init__(self):
        self.log, self.reads, self.next = [], [], 100
        self.error, self.add_error, self.block_phase = 5, None, None
        self.fail_witness, self.nt_return = False, 0
        self.nt_status, self.nt_information = 0, 2
        self.native_error, self.close_error, self.remove_error = None, None, None
        self.null_output, self.partial_output, self.forced_handle = False, False, None
        self.pin_error, self.raw_by_handle = None, {}
        self.allocations = []
        self.metadata = {10: snapshot()['parent'], 11: snapshot()['leaf']}
        self.f = ApiFixture(m)
        self.api = SimpleNamespace(kernel=self.f.kernel, advapi=self.f.advapi,
                                   call=lambda function, *args: function(*args))
        self.api.kernel.CreateFileW = Function(self.open)
        self.api.kernel.CreateDirectoryW = Function(self.mkdir)
        self.api.kernel.CloseHandle = Function(self.close)
        self.api.kernel.GetFileInformationByHandleEx = Function(self.info)
        self.ntdll = SimpleNamespace(NtCreateFile=Function(self.nt_create))
        self.reader = SimpleNamespace(read=self.read_sd, cleanup_unconfirmed=False)
        self.base = SimpleNamespace(parent='owned-parent', leaf='owned-parent/leaf',
            api=self.api, host='S-1-5-21-1', pin=None, initial=snapshot(),
            observer=SimpleNamespace(handles={'parent': SimpleNamespace(value=10),
                                             'leaf': SimpleNamespace(value=11)},
                                     reader=self.reader, query=self.query))
        self.base.prepare, self.base.start_pin, self.base.close = self.prepare, self.start_pin, self.base_close

    def prepare(self):
        self.log.append(('prepare',))
        # Exercise setup SD owners, independently of the child conversion owner.
        for role in ('leaf', 'parent'):
            owner = m._ConvertedDacl(self.api)
            owner.acquire(self.base.host, 0x80)
            owner.close()
            self.read_sd(11 if role == 'leaf' else 10)

    def allocate(self, directory):
        handle = self.next if self.forced_handle is None else self.forced_handle
        self.next += 1
        self.allocations.append(handle)
        self.metadata[handle] = StartupFileMetadata(1, handle.to_bytes(16, 'little'),
            directory, False, False, 'disk', 1, 0, 1)
        return handle

    def open(self, path, access, share, sa, disposition, flags, template):
        if access in (2, 4):
            self.log.append(('add', access))
            if self.add_error is not None:
                self.error = self.add_error
                return m._INVALID
            return self.allocate(True)
        if disposition == 1:
            self.log.append(('create', 'win32', 'file', path))
            attributes = ctypes.cast(sa, ctypes.POINTER(m._SECURITY_ATTRIBUTES)).contents
            self.log.append(('sa', attributes.nLength, attributes.lpSecurityDescriptor, attributes.bInheritHandle))
            if self.block_phase is not None and path.endswith('sibling-' + self.block_phase):
                return m._INVALID
            return None if self.null_output else self.allocate(False)
        self.log.append(('witness', path))
        return (m._INVALID if self.fail_witness else None if self.null_output else self.allocate(True))

    def mkdir(self, path, sa):
        self.log.append(('create', 'win32', 'directory', path))
        attributes = ctypes.cast(sa, ctypes.POINTER(m._SECURITY_ATTRIBUTES)).contents
        self.log.append(('sa', attributes.nLength, attributes.lpSecurityDescriptor, attributes.bInheritHandle))
        return 0 if self.block_phase is not None and path.endswith('sibling-' + self.block_phase) else 1

    def nt_create(self, output, access, attributes, iosb, allocation, attrs, share,
                  disposition, options, ea, ea_length):
        oa = ctypes.cast(attributes, ctypes.POINTER(m._OBJECT_ATTRIBUTES)).contents
        name = oa.ObjectName.contents
        basename = ctypes.string_at(name.Buffer, name.Length).decode('utf-16-le')
        self.log.append(('create', 'nt_relative', bool(options & 1), basename, oa.RootDirectory))
        status = self.nt_return
        if self.block_phase is not None and basename == 'sibling-' + self.block_phase:
            status = ctypes.c_int32(0xC0000022).value
        if (status == 0 and not self.null_output) or self.native_error is not None or self.partial_output:
            handle = self.allocate(bool(options & 1))
            ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p))[0] = handle
        ios = ctypes.cast(iosb, ctypes.POINTER(m._IO_STATUS_BLOCK)).contents
        ios.u.Status, ios.Information = self.nt_status, self.nt_information
        if self.native_error is not None:
            raise self.native_error
        return status

    def info(self, handle, info, output, length):
        value = ctypes.cast(output, ctypes.POINTER(m._INFO_CLASSES[info])).contents
        meta = self.metadata[handle]
        if info in (0, 9):
            value.FileAttributes = (16 if meta.directory else 128) | (0x400 if meta.reparse else 0)
            if info == 0:
                value.ChangeTime = meta.change_time
        elif info == 1:
            value.Directory, value.DeletePending = meta.directory, meta.delete_pending
            value.NumberOfLinks, value.EndOfFile = meta.links, meta.size
        else:
            value.VolumeSerialNumber = meta.volume_serial
            ctypes.memmove(value.FileId, meta.file_id, 16)
        return 1

    def query(self, role):
        return self.metadata[10 if role == 'parent' else 11]

    def read_sd(self, handle):
        self.reads.append(handle)
        return self.raw_by_handle.get(handle, raw_marker())

    def close(self, handle):
        self.log.append(('close', handle))
        if self.close_error is not None:
            raise self.close_error
        return 1

    def remove(self, path):
        self.log.append(('remove', path))
        if self.remove_error is not None:
            raise self.remove_error

    def start_pin(self):
        self.log.append(('pin_start',))
        self.metadata.update({20: self.metadata[10], 21: self.metadata[11]})
        pin = SimpleNamespace(_handles=[20, 21], _baseline=[self.metadata[20], self.metadata[21]],
                              close_confirmed=False)
        pin._require_open = lambda: None
        pin._backend = SimpleNamespace(query=lambda handle: self.metadata[handle],
            query_security=self.read_sd, _security_reader=self.reader,
            read=lambda handle, offset, count: m._CONTENT, _unknown=set())
        def close_pin():
            if not pin.close_confirmed:
                self.log.append(('pin_close',))
                if self.pin_error is not None:
                    raise self.pin_error
                pin.close_confirmed = True
        pin.close = close_pin
        self.base.pin = pin

    def base_close(self):
        self.log.append(('base_close',))

    def environment(self):
        stack = ExitStack()
        stack.enter_context(patch.object(m, '_Fixture', return_value=self.base))
        stack.enter_context(patch.object(ctypes, 'WinDLL', create=True, return_value=self.ntdll))
        stack.enter_context(patch.object(ctypes, 'get_last_error', create=True, side_effect=lambda: self.error))
        stack.enter_context(patch.object(m.os, 'unlink', side_effect=self.remove))
        stack.enter_context(patch.object(m.os, 'rmdir', side_effect=self.remove))
        return stack


@contextmanager
def _interrupt(function, needle, error, predicate=lambda local: True):
    previous, fired = sys.gettrace(), [False]
    def trace(frame, event, arg):
        if (frame.f_code is function.__code__ and not fired[0]
                and ((event == 'line' and needle in linecache.getline(frame.f_code.co_filename, frame.f_lineno))
                     or (event == 'return' and needle == '__return__'))
                and predicate(frame.f_locals)):
            fired[0] = True
            raise error
        return trace
    sys.settrace(trace)
    try:
        yield fired
    finally:
        sys.settrace(previous)


class PrivateSiblingPortableTests(unittest.TestCase):
    def test_native_abi_and_full_sd(self):
        h = _Harness()
        ledger = m._Ledger(h.base)
        with h.environment():
            create = m._Creation(h.base, ledger)
            self.assertEqual(create.ntdll.NtCreateFile.restype, ctypes.c_int32)
            self.assertEqual(len(create.ntdll.NtCreateFile.argtypes), 11)
            slot = m._Slot('owned-child', False)
            effect, result = create.create('nt_relative', 'file', 'unpinned', 12345, 10, slot)
            args = h.ntdll.NtCreateFile.calls[-1]
            oa = ctypes.cast(args[2], ctypes.POINTER(m._OBJECT_ATTRIBUTES)).contents
            self.assertEqual((oa.Length, oa.RootDirectory, oa.Attributes, oa.SecurityDescriptor,
                              oa.SecurityQualityOfService), (ctypes.sizeof(oa), 10, 0x1040, 12345, None))
            self.assertEqual(args[1], 0x120081)
            self.assertEqual(args[5:], (0, 7, 2, 0x200060, None, 0))
            self.assertEqual(effect, 'created')
            ledger.close(slot)
        self.assertEqual(m._SECURITY_ATTRIBUTES._fields_[0][1], ctypes.c_uint32)
        self.assertEqual(m._SECURITY_ATTRIBUTES._fields_[2][1], ctypes.c_int32)

    def test_win32_creation_and_directory_witness(self):
        for kind in m._KINDS:
            h = _Harness()
            with h.environment():
                create = m._Creation(h.base, m._Ledger(h.base))
                slot = m._Slot('owned-child', kind == 'directory')
                effect, native = create.create('win32', kind, 'unpinned', 12345, 10, slot)
                self.assertEqual((effect, native), ('created', {'result': 0}))
                self.assertTrue(slot.owned_path)
                self.assertIn(('sa', ctypes.sizeof(m._SECURITY_ATTRIBUTES), 12345, 0), h.log)
                args = h.api.kernel.CreateFileW.calls[-1]
                self.assertEqual((args[1], args[2], args[4], args[5]),
                    (0x120081, 7, 3 if kind == 'directory' else 1, 0x2200000 if kind == 'directory' else 0x200000))

    def test_nt_success_and_failure_outputs(self):
        for code in m._NT_DENIED:
            h = _Harness()
            h.nt_return, h.nt_status, h.nt_information = ctypes.c_int32(code).value, 7, 99
            with h.environment():
                create = m._Creation(h.base, m._Ledger(h.base))
                self.assertEqual(create.create('nt_relative', 'file', 'pinned', 12345, 10,
                    m._Slot('owned-child', False)), ('blocked', {'return_u32': code}))
        for ret, status, info in ((0x103, 0, 2), (1, 0, 2), (0, 1, 2), (0, 0, 1)):
            h = _Harness()
            h.nt_return, h.nt_status, h.nt_information = ret, status, info
            with h.environment():
                with self.assertRaises(RuntimeError):
                    m._Creation(h.base, m._Ledger(h.base)).create('nt_relative', 'file',
                        'pinned', 12345, 10, m._Slot('owned-child', False))
        for route in m._ROUTES:
            for kind in m._KINDS:
                for fault in ('null', 'partial', 'active', 'unknown'):
                    with self.subTest(route=route, kind=kind, fault=fault):
                        h = _Harness()
                        ledger = m._Ledger(h.base)
                        if fault == 'null':
                            h.null_output = True
                        elif fault == 'partial':
                            if route != 'nt_relative':
                                continue
                            h.nt_return = ctypes.c_int32(0xC0000022).value
                            h.partial_output = True
                        else:
                            h.forced_handle = 10 if fault == 'active' else 900
                            if fault == 'unknown':
                                ledger.unknown.add(900)
                        slot = m._Slot('owned-child', kind == 'directory')
                        with h.environment():
                            with self.assertRaises(RuntimeError):
                                m._Creation(h.base, ledger).create(route, kind, 'pinned', 12345, 10, slot)
                        if fault in ('active', 'unknown'):
                            self.assertFalse(any(row[0] == 'close' for row in h.log))
                        if fault == 'partial':
                            self.assertFalse(slot.owned_path)
                            self.assertEqual(sum(row[0] == 'close' for row in h.log), 1)

    def test_acquisition_registration_return_interrupts(self):
        # Trace actual source lines: after native result is saved, before claim,
        # after claim, and at the successful return boundary, for all variants.
        for route in m._ROUTES:
            for kind in m._KINDS:
                saved = ('value = output.value' if route == 'nt_relative' else
                         'value = result' if kind == 'file' else 'if type(result) is not int:')
                for boundary in (saved, 'self.ledger.claim(slot, value)',
                                 '__return__', "return 'created',"):
                    for error in (KeyboardInterrupt(), SystemExit()):
                        h = _Harness()
                        slot = m._Slot('owned-child', kind == 'directory')
                        predicate = lambda local: True
                        with self.subTest(route=route, kind=kind, boundary=boundary, signal=type(error)), h.environment():
                            create = m._Creation(h.base, m._Ledger(h.base))
                            target = create.ledger.claim if boundary == '__return__' else create.create
                            with _interrupt(target, boundary, error, predicate) as fired:
                                with self.assertRaises(type(error)) as caught:
                                    create.create(route, kind, 'unpinned', 12345, 10, slot)
                            self.assertTrue(fired[0])
                            self.assertIs(caught.exception, error)
                        self.assertTrue(slot.owned_path)
                        expected = 0 if route == 'win32' and kind == 'directory' and boundary == saved else 1
                        self.assertEqual(sum(row[0] == 'close' for row in h.log), expected)
        for error in (KeyboardInterrupt(), SystemExit()):
            h = _Harness()
            ledger = m._Ledger(h.base)
            actual = ledger.claim
            def claim(slot, value):
                actual(slot, value)
                raise error
            with h.environment(), patch.object(ledger, 'claim', side_effect=claim):
                slot = m._Slot('owned-child', False)
                with self.assertRaises(type(error)) as caught:
                    m._Creation(h.base, ledger).create('nt_relative', 'file', 'unpinned', 12345, 10, slot)
                self.assertIs(caught.exception, error)
            self.assertEqual(sum(row[0] == 'close' for row in h.log), 1)
            self.assertTrue(slot.owned_path)

    def test_unknown_outputs_and_known_owner_collision(self):
        h = _Harness()
        h.native_error = KeyboardInterrupt()
        slot = m._Slot('unknown-path', False)
        with h.environment():
            with self.assertRaises(KeyboardInterrupt):
                m._Creation(h.base, m._Ledger(h.base)).create('nt_relative', 'file',
                    'unpinned', 12345, 10, slot)
        self.assertFalse(slot.owned_path)
        self.assertEqual(sum(row[0] == 'close' for row in h.log), 1)
        h = _Harness()
        ledger = m._Ledger(h.base)
        for value in (10, 11):
            with self.assertRaises(RuntimeError):
                ledger.claim(m._Slot('owned-child', False), value)
        first = m._Slot('owned-first', False)
        ledger.claim(first, 500)
        h.close_error = RuntimeError()
        with self.assertRaises(RuntimeError):
            ledger.close(first)
        with self.assertRaises(RuntimeError):
            ledger.claim(m._Slot('owned-second', False), 500)
        h.close_error = None
        first = m._Slot('owned-first', False)
        ledger.claim(first, 501)
        ledger.close(first)
        second = m._Slot('owned-second', False)
        ledger.claim(second, 501)
        ledger.close(second)
        ledger.close(first)
        self.assertEqual(h.log.count(('close', 501)), 2)
        # Demonstrate numerical reuse from the actual native helper, not only
        # calling ledger.claim: first acquisition confirmed closed, second new.
        h = _Harness()
        ledger = m._Ledger(h.base)
        with h.environment():
            create = m._Creation(h.base, ledger)
            first = m._Slot('owned-first', False)
            create.create('win32', 'file', 'unpinned', 12345, 10, first)
            ledger.close(first)
            h.next = first.handle
            second = m._Slot('owned-second', False)
            create.create('win32', 'file', 'released', 12345, 10, second)
            self.assertEqual(first.handle, second.handle)
            self.assertTrue(second.owned_path)
            ledger.close(second)
        self.assertEqual(h.log.count(('close', first.handle)), 2)

    def receipt(self, route='win32', kind='file', blocked=False):
        windows = []
        for phase in m._PHASES:
            deny = blocked and phase == 'pinned'
            native = ({'result': 5 if deny else 0} if route == 'win32' else
                      {'return_u32': 0xC0000022} if deny else
                      {'return_u32': 0, 'iosb': {'status_u32': 0, 'information': 2}})
            child = None if deny else dict.fromkeys((
                'identity_distinct', 'volume_matches', 'kind_matches', 'nonreparse',
                'not_delete_pending', 'protected', 'template_verified'), True)
            if child is not None:
                child['empty_file'] = True if kind == 'file' else None
            windows.append({'window': phase, 'direct_add': {'access': 2 if kind == 'file' else 4, 'result': 0},
                'create': native, 'effect': 'blocked' if deny else 'created',
                'parent_metadata_changed': False, 'leaf_metadata_changed': False,
                'identity_stable': True, 'bytes_stable': True, 'parent_sd_stable': True,
                'leaf_sd_stable': True, 'child': child})
        return {'scope': 'private_sibling_window_observation', 'schema_version': 1,
                'route': route, 'kind': kind, 'windows': windows, 'cleanup_confirmed': True,
                'consumer_ready': False, 'compatibility_accepted': False, 'launch_authorized': False}

    def test_entry_rejects_before_loader(self):
        class Text(str):
            pass
        for route, kind in ((Text('win32'), 'file'), ('win32', Text('file')), ('other', 'file'), ('win32', None)):
            with patch.object(m, '_Fixture', create=True) as constructor, patch.object(m.os, 'name', 'nt'), \
                    patch.object(ctypes, 'WinDLL', create=True) as loader, \
                    patch.object(WindowsStartupHostIdentity, 'capture') as token, \
                    patch.object(tempfile, 'mkdtemp') as temporary:
                with self.assertRaises(RuntimeError):
                    m.run_variant(route, kind)
                constructor.assert_not_called()
                loader.assert_not_called()
                token.assert_not_called()
                temporary.assert_not_called()
        with patch.object(m, '_Fixture', create=True) as constructor, patch.object(m.os, 'name', 'posix'), \
                patch.object(ctypes, 'WinDLL', create=True) as loader, \
                patch.object(WindowsStartupHostIdentity, 'capture') as token, \
                patch.object(tempfile, 'mkdtemp') as temporary:
            with self.assertRaises(RuntimeError):
                m.run_variant('win32', 'file')
            constructor.assert_not_called()
            loader.assert_not_called()
            token.assert_not_called()
            temporary.assert_not_called()
        # Valid inputs reach the completed controller; ordinary failures are private.
        with patch.object(m.os, 'name', 'nt'), patch.object(m, '_run_variant',
                side_effect=RuntimeError('private path HANDLE SID SD')):
            with self.assertRaisesRegex(RuntimeError, '^private_sibling_window_failed$'):
                m.run_variant('win32', 'file')
        for signal in (KeyboardInterrupt(), SystemExit()):
            with patch.object(m.os, 'name', 'nt'), patch.object(m, '_run_variant', side_effect=signal):
                with self.assertRaises(type(signal)) as caught:
                    m.run_variant('win32', 'file')
                self.assertIs(caught.exception, signal)

    def test_wire_all_route_kind_and_effect_combinations(self):
        for route in m._ROUTES:
            for kind in m._KINDS:
                for blocked in (False, True):
                    for direct in (0, 5, 32, 33):
                        data = self.receipt(route, kind, blocked)
                        data['windows'][1]['direct_add']['result'] = direct
                        self.assertEqual(m.validate_wire(m._encode(data)), data)

    def test_wire_rejects_types_keys_and_canonical_drift(self):
        data = self.receipt()
        wire = m._encode(data)
        for invalid in (wire[:-1], wire + b'\n', b' ' + wire, wire.replace(b',', b', ', 1),
                        wire.replace(b'"schema_version":1', b'"schema_version":1,"schema_version":1'),
                        b'\xff\n', b'x' * 8193, wire.decode('ascii')):
            with self.assertRaises(ValueError):
                m.validate_wire(invalid)
        objects = [data, data['windows'][0], data['windows'][0]['direct_add'],
                   data['windows'][0]['create'], data['windows'][0]['child']]
        for obj in objects:
            for key in list(obj):
                value = obj.pop(key)
                with self.assertRaises(ValueError):
                    m.validate_wire(m._encode(data))
                obj[key] = value
            obj['extra'] = None
            with self.assertRaises(ValueError):
                m.validate_wire(m._encode(data))
            del obj['extra']
        for field in ('access', 'result'):
            bad = self.receipt()
            bad['windows'][0]['direct_add'][field] = True
            with self.assertRaises(ValueError):
                m.validate_wire(m._encode(bad))
        class Integer(int):
            pass
        with patch.object(m.json, 'loads', return_value=dict(data, schema_version=Integer(1))):
            with self.assertRaises(ValueError):
                m.validate_wire(wire)
        nt = self.receipt('nt_relative')
        for key in ('status_u32', 'information'):
            bad = copy.deepcopy(nt)
            del bad['windows'][0]['create']['iosb'][key]
            with self.assertRaises(ValueError):
                m.validate_wire(m._encode(bad))
            bad = copy.deepcopy(nt)
            bad['windows'][0]['create']['iosb'][key] = True
            with self.assertRaises(ValueError):
                m.validate_wire(m._encode(bad))

    def test_wire_positive_controls_and_authority(self):
        for phase in (0, 2):
            bad = self.receipt(blocked=True)
            bad['windows'][phase].update(effect='blocked', create={'result': 5}, child=None)
            with self.assertRaises(ValueError):
                m.validate_wire(m._encode(bad))
        for field in ('cleanup_confirmed', 'consumer_ready', 'compatibility_accepted', 'launch_authorized'):
            bad = self.receipt()
            bad[field] = 1
            with self.assertRaises(ValueError):
                m.validate_wire(m._encode(bad))
        for field in ('identity_stable', 'bytes_stable', 'parent_sd_stable', 'leaf_sd_stable'):
            bad = self.receipt()
            bad['windows'][1][field] = 1
            with self.assertRaises(ValueError):
                m.validate_wire(m._encode(bad))
        for field in ('parent_metadata_changed', 'leaf_metadata_changed'):
            bad = self.receipt()
            bad['windows'][1][field] = 0
            with self.assertRaises(ValueError):
                m.validate_wire(m._encode(bad))

    def test_direct_add_is_independent_of_create(self):
        for route in m._ROUTES:
            for kind in m._KINDS:
                h = _Harness()
                with h.environment():
                    m._run_variant(route, kind)
                calls = [args for args in h.api.kernel.CreateFileW.calls if args[1] in (2, 4)]
                self.assertEqual(len(calls), 3)
                for args in calls:
                    self.assertEqual(args, (h.base.parent, 2 if kind == 'file' else 4,
                                           7, None, 3, 0x2200000, None))
        for error in (5, 32, 33, 87):
            h = _Harness()
            h.add_error = error
            with h.environment():
                if error == 87:
                    with self.assertRaises(m._StageFailure):
                        m._run_variant('win32', 'file')
                else:
                    self.assertEqual(len(m.validate_wire(m._run_variant('win32', 'file'))['windows']), 3)
            self.assertTrue(any(row[0] == 'create' for row in h.log))
        h = _Harness()
        h.close_error = RuntimeError()
        with h.environment():
            with self.assertRaises(m._StageFailure):
                m._run_variant('win32', 'file')
        self.assertEqual(sum(row[0] == 'create' for row in h.log), 1)
        for error in (KeyboardInterrupt(), SystemExit()):
            h = _Harness()
            with h.environment(), patch.object(m._Creation, 'direct_add', side_effect=error):
                with self.assertRaises(type(error)) as caught:
                    m._run_variant('win32', 'file')
                self.assertIs(caught.exception, error)
            self.assertFalse(any(row[0] == 'create' for row in h.log))

    def test_controller_windows_pin_and_retention(self):
        for route in m._ROUTES:
            for kind in m._KINDS:
                h = _Harness()
                with h.environment():
                    data = m.validate_wire(m._run_variant(route, kind))
                self.assertEqual([event['window'] for event in data['windows']], list(m._PHASES))
                created = [index for index, row in enumerate(h.log) if row[0] == 'create']
                removed = [index for index, row in enumerate(h.log) if row[0] == 'remove']
                self.assertEqual(len(created), 3)
                self.assertGreater(min(removed), max(created))
                self.assertLess(h.log.index(('pin_close',)), created[2])
                if route == 'nt_relative':
                    self.assertEqual([row[4] for row in h.log if row[0] == 'create'], [10, 20, 10])
        # Actual Creation.create RETURN event is after its local try has ended.
        # The registered slot belongs to _run_variant, so outer cleanup closes
        # the acquired child and removes its confirmed owned path exactly once.
        for route in m._ROUTES:
            for kind in m._KINDS:
                for signal in (KeyboardInterrupt(), SystemExit()):
                    h = _Harness()
                    with self.subTest(route=route, kind=kind, boundary='create_actual_return', signal=type(signal)), h.environment():
                        with _interrupt(m._Creation.create, '__return__', signal) as fired:
                            with self.assertRaises(type(signal)) as caught:
                                m._run_variant(route, kind)
                        self.assertTrue(fired[0])
                        self.assertIs(caught.exception, signal)
                    self.assertEqual(sum(row[0] == 'create' for row in h.log), 1)
                    self.assertEqual(len(h.allocations), 2)
                    closes = [row[1] for row in h.log if row[0] == 'close']
                    self.assertCountEqual(closes, h.allocations)
                    self.assertEqual(len(closes), 2)
                    removes = [row[1] for row in h.log if row[0] == 'remove']
                    self.assertEqual(removes, [m.os.path.join(h.base.parent, 'sibling-unpinned')])
                    self.assertEqual(h.log[-1], ('base_close',))
        # Bind creation's full SD to the actual conversion owner allocation.
        for route in m._ROUTES:
            for kind in m._KINDS:
                h = _Harness()
                with h.environment():
                    m._run_variant(route, kind)
                full = ctypes.addressof(h.f.pointer)
                if route == 'win32':
                    self.assertEqual([row[2] for row in h.log if row[0] == 'sa'], [full] * 3)
                else:
                    h = _Harness()
                    full_pointers = []
                    def capture(*args):
                        oa = ctypes.cast(args[2], ctypes.POINTER(m._OBJECT_ATTRIBUTES)).contents
                        full_pointers.append(oa.SecurityDescriptor)
                        self.assertEqual(args[8], 0x200020 | (1 if kind == 'directory' else 0x40))
                        return h.nt_create(*args)
                    h.ntdll.NtCreateFile = Function(capture)
                    with h.environment():
                        m._run_variant(route, kind)
                    self.assertEqual(full_pointers, [ctypes.addressof(h.f.pointer)] * 3)
                self.assertNotEqual(full, full + 20)
        for route in m._ROUTES:
            for kind in m._KINDS:
                for phase in m._PHASES:
                    h = _Harness()
                    h.block_phase = phase
                    with h.environment():
                        if phase == 'pinned':
                            data = m.validate_wire(m._run_variant(route, kind))
                            self.assertEqual(data['windows'][1]['effect'], 'blocked')
                            self.assertIsNone(data['windows'][1]['child'])
                        else:
                            with self.assertRaises(m._StageFailure):
                                m._run_variant(route, kind)
        for error in (RuntimeError(), KeyboardInterrupt(), SystemExit()):
            h = _Harness()
            h.pin_error = error
            with h.environment():
                with self.assertRaises(type(error) if not isinstance(error, Exception) else m._StageFailure) as caught:
                    m._run_variant('nt_relative', 'directory')
                if not isinstance(error, Exception):
                    self.assertIs(caught.exception, error)
            self.assertEqual(sum(row[0] == 'create' for row in h.log), 2)

    def test_first_before_and_cross_window_raw(self):
        h = _Harness()
        observe = m._Observation(h.base)
        with h.environment():
            before = observe.sample('unpinned')
            self.assertEqual(observe.raw_baseline, (before['parent_raw'], before['leaf_raw']))
            h.reader.read = lambda handle: raw_marker(0x100)
            with self.assertRaises(RuntimeError):
                observe.sample('released')
        h = _Harness()
        h.base.initial['raw'] = raw_marker(0x100)
        with h.environment():
            with self.assertRaises(RuntimeError):
                m._Observation(h.base).sample('unpinned')
        # Both descriptors pass the same protected template, but raw bytes differ.
        from tests.test_windows_startup_security import descriptor, acl, ace, sid
        reordered = descriptor(control=0x9004, dacl=acl([
            ace(mask=0x80, trustee=sid(1, (0,))),
            ace(mask=0x1f01ff, trustee=sid(5, (32, 544))),
            ace(mask=0x1f01ff, trustee=sid(5, (18,))),
            ace(mask=0x1f01ff, trustee=sid(5, (21, 1))),
        ]))
        m._marker(reordered, 'S-1-5-21-1', 0x80)
        self.assertNotEqual(reordered, raw_marker())
        for role in ('parent', 'leaf'):
            h = _Harness()
            observe = m._Observation(h.base)
            with h.environment():
                observe.sample('unpinned')
                h.raw_by_handle[10 if role == 'parent' else 11] = reordered
                with self.assertRaises(RuntimeError):
                    observe.sample('released')

    def test_identity_bytes_and_metadata_change(self):
        h = _Harness()
        with h.environment():
            observe = m._Observation(h.base)
            observe.sample('unpinned')
            h.metadata[10] = replace(h.metadata[10], change_time=2)
            observe.sample('released')
            h.metadata[10] = replace(h.metadata[10], file_id=b'x' * 16)
            with self.assertRaises(RuntimeError):
                observe.sample('released')
        h = _Harness()
        with h.environment(), patch.object(h.api.kernel, 'ReadFile', return_value=0):
            with self.assertRaises(RuntimeError):
                m._Observation(h.base).sample('unpinned')
        h = _Harness()
        h.metadata[11] = replace(h.metadata[11], file_id=b'wrong-leaf-id---!')
        with h.environment():
            with self.assertRaises(Exception):
                m._Observation(h.base).sample('unpinned')
        h = _Harness()
        def wrong_bytes(handle, buffer, count, actual, overlap):
            ctypes.memmove(buffer, b'x' * count, count)
            ctypes.cast(actual, ctypes.POINTER(ctypes.c_uint32))[0] = count
            return 1
        with h.environment(), patch.object(h.api.kernel, 'ReadFile', side_effect=wrong_bytes):
            with self.assertRaises(RuntimeError):
                m._Observation(h.base).sample('unpinned')

    def test_child_metadata_and_actual_security(self):
        file = StartupFileMetadata(1, b'c' * 16, False, False, False, 'disk', 1, 0, 1)
        self.assertIs(m._child_metadata(file, False), file)
        self.assertIs(m._child_metadata(replace(file, directory=True, size=123, links=3), True).directory, True)
        for bad in (replace(file, size=1), replace(file, links=2), replace(file, reparse=True),
                    replace(file, delete_pending=True), replace(file, volume_serial=True)):
            with self.assertRaises(RuntimeError):
                m._child_metadata(bad, False)
        with self.assertRaises(Exception):
            m._metadata(file, directory=False, max_bytes=4096)
        h = _Harness()
        slot = m._Slot('owned-child', False)
        slot.handle = h.allocate(False)
        h.reader.read = lambda handle: raw_marker(0x100)
        with self.assertRaises(RuntimeError):
            m._Observation(h.base).child(slot, 'file', snapshot())

    def test_child_identity_retained_distinct(self):
        h = _Harness()
        observe = m._Observation(h.base)
        slot = m._Slot('owned-child', False)
        slot.handle = h.allocate(False)
        observe.child(slot, 'file', snapshot())
        with self.assertRaises(RuntimeError):
            observe.child(slot, 'file', snapshot())
        h.metadata[slot.handle] = replace(h.metadata[slot.handle], file_id=snapshot()['leaf'].file_id)
        with self.assertRaises(RuntimeError):
            m._Observation(h.base).child(slot, 'file', snapshot())

    def test_cleanup_one_attempt_reverse_and_priority(self):
        h = _Harness()
        h.fail_witness = True
        with h.environment():
            with self.assertRaises(m._StageFailure):
                m._run_variant('win32', 'directory')
        self.assertTrue(any(row[0] == 'remove' for row in h.log))
        h = _Harness()
        ledger = m._Ledger(h.base)
        slots = [m._Slot('owned-' + str(index), False) for index in range(3)]
        for index, slot in enumerate(slots):
            ledger.claim(slot, 600 + index)
            slot.owned_path = True
        h.remove_error = RuntimeError()
        original = KeyboardInterrupt()
        with h.environment():
            self.assertIs(m._cleanup(h.base, ledger, slots, None, original), original)
        self.assertEqual([row[1] for row in h.log if row[0] == 'close'], [602, 601, 600])
        self.assertEqual([row[1] for row in h.log if row[0] == 'remove'], ['owned-2', 'owned-1', 'owned-0'])
        self.assertEqual(h.log[-1], ('base_close',))
        self.assertIs(m._choose(RuntimeError(), original), original)
        self.assertIs(m._choose(original, SystemExit()), original)
        for signal in (KeyboardInterrupt(), SystemExit()):
            for stage in ('sd_free', 'remove'):
                h = _Harness()
                count = [0]
                def free(pointer):
                    count[0] += 1
                    if count[0] == 3:
                        raise signal
                    return None
                if stage == 'sd_free':
                    h.f.kernel.LocalFree = Function(free)
                else:
                    h.remove_error = signal
                with h.environment():
                    with self.assertRaises(type(signal)) as caught:
                        m._run_variant('win32', 'file')
                    self.assertIs(caught.exception, signal)
                self.assertEqual(h.log[-1], ('base_close',))
                self.assertEqual(sum(row[0] == 'remove' for row in h.log), 3)
        h = _Harness()
        count = [0]
        def unconfirmed_free(pointer):
            count[0] += 1
            return pointer if count[0] == 3 else None
        h.f.kernel.LocalFree = Function(unconfirmed_free)
        with h.environment():
            with self.assertRaises(m._StageFailure) as caught:
                m._run_variant('win32', 'file')
            self.assertEqual(caught.exception.args, ('cleanup',))
        self.assertEqual(count[0], 3)
        for phase in ('unpinned', 'pinned', 'released', 'child'):
            h = _Harness()
            actual_sample, actual_child = m._Observation.sample, m._Observation.child
            def sample(owner, current):
                if current == phase:
                    h.reader.cleanup_unconfirmed = True
                return actual_sample(owner, current)
            def child(owner, *args):
                if phase == 'child':
                    h.reader.cleanup_unconfirmed = True
                return actual_child(owner, *args)
            with h.environment(), patch.object(m._Observation, 'sample', sample), patch.object(m._Observation, 'child', child):
                with self.assertRaises(m._StageFailure):
                    m._run_variant('win32', 'file')

    def test_failure_diagnostic_is_finite_and_private(self):
        for stage in m._STAGES:
            self.assertEqual(m.failure_message(m._StageFailure(stage)), m._FAILURE + ':' + stage)
        class Hostile(RuntimeError):
            @property
            def args(self):
                raise AssertionError('must not read custom args')
        self.assertEqual(m.failure_message(Hostile()), m._FAILURE)
        self.assertEqual(m.failure_message(m._StageFailure('C:\\private\\secret')), m._FAILURE)
        # An invalid diagnostic object must not bypass the public boundary.
        for error in (Hostile(), m._StageFailure('private HANDLE SID SD'), m._StageFailure()):
            with patch.object(m.os, 'name', 'nt'), patch.object(m, '_run_variant', side_effect=error):
                with self.assertRaisesRegex(RuntimeError, '^private_sibling_window_failed$') as caught:
                    m.run_variant('win32', 'file')
                self.assertTrue(caught.exception.__suppress_context__)
        source = inspect.getsource(m._Creation.create)
        self.assertNotIn('._call(', source)
        self.assertNotIn('_at_stage(', source)

    def test_static_all_created_budget(self):
        total_reads, total_converts, total_frees, new_acquires, new_closes = 0, 0, 0, 0, 0
        for route in m._ROUTES:
            for kind in m._KINDS:
                h = _Harness()
                with h.environment():
                    m.validate_wire(m._run_variant(route, kind))
                self.assertEqual(len(h.reads), 17)
                self.assertEqual(sum(row[0] == 'add' for row in h.log), 3)
                self.assertEqual(sum(row[0] == 'create' for row in h.log), 3)
                total_reads += len(h.reads)
                total_converts += len(h.f.advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.calls)
                total_frees += len(h.f.kernel.LocalFree.calls)
                self.assertEqual(len(h.allocations), 6)
                closes = [row[1] for row in h.log if row[0] == 'close']
                self.assertCountEqual(closes, h.allocations)
                self.assertEqual(len(closes), 6)
                new_acquires += len(h.allocations)
                new_closes += len(closes)
        self.assertEqual((total_reads, total_converts, total_frees), (68, 12, 12))
        self.assertEqual(total_reads + total_converts, 80)
        self.assertEqual((new_acquires, new_closes), (24, 24))
        # Static upper bound from current real source/spec, not fake-native count:
        # base config+observer4, children3, ADD3, pin<=32, token1 per variant.
        self.assertEqual(4 * (4 + 3 + 3 + 32 + 1), 172)


@unittest.skipUnless(sys.platform == 'win32', 'native Windows only')
class WindowsPrivateSiblingWindowNativeTests(unittest.TestCase):
    def _observe(self, kind):
        from tests.windows_private_sibling_fixture import run_variant, validate_wire, failure_message
        for route in ('win32', 'nt_relative'):
            try:
                wire = run_variant(route, kind)
                validate_wire(wire)
            except BaseException as error:
                message = failure_message(error)
                if message != 'private_sibling_window_failed':
                    message += ':' + route + ':' + kind
                raise AssertionError(message) from None
            print(wire.decode('ascii'), end='')

    def test_private_sibling_file_three_windows(self):
        self._observe('file')

    def test_private_sibling_directory_three_windows(self):
        self._observe('directory')
