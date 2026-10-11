"""CI-only sibling creation observation; never a launch/security authority."""
import ctypes
import json
import os

from tests.windows_private_dacl_fixture import (
    _Fixture, _ConvertedDacl, _CONTENT, _marker, _stable,
)
from icode.windows_startup_native import (
    _INFO_CLASSES, _OBJECT_ATTRIBUTES, _IO_STATUS_BLOCK, _UNICODE_STRING,
)
from icode.windows_startup_pin import StartupFileMetadata, _metadata

_U32, _I32, _VOID = ctypes.c_uint32, ctypes.c_int32, ctypes.c_void_p
_INVALID = _VOID(-1).value

_DENIED = frozenset((5, 32, 33))
_NT_DENIED = frozenset((0xC0000022, 0xC0000043, 0xC0000054))
_PHASES = ('unpinned', 'pinned', 'released')
_ROUTES, _KINDS = ('win32', 'nt_relative'), ('file', 'directory')
_FAILURE = 'private_sibling_window_failed'

_STAGES = frozenset((
    'fixture', 'prepare', 'child_sd', 'initial', 'start_pin', 'release_pin',
    'cleanup', 'wire',
) + tuple(phase + '_' + step for phase in _PHASES
          for step in ('before', 'direct_add', 'create', 'after', 'child')))


class _StageFailure(RuntimeError):
    """Internal finite diagnostic; validated again at the public boundary."""


def failure_message(error):
    if type(error) is _StageFailure:
        args = error.args
        if (type(args) is tuple and len(args) == 1
                and type(args[0]) is str and args[0] in _STAGES):
            return _FAILURE + ':' + args[0]
    return _FAILURE


def _require(condition):
    if not condition:
        raise ValueError('invalid_private_sibling_receipt')


def _object(value, keys):
    _require(type(value) is dict and value.keys() == keys)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _encode(data):
    return (json.dumps(data, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=True).encode('ascii') + b'\n')


def validate_wire(wire):
    try:
        _require(type(wire) is bytes and 1 <= len(wire) <= 8192)
        data = json.loads(wire.decode('ascii', 'strict'), object_pairs_hook=_unique)
        _require(_encode(data) == wire)
        _object(data, {'scope', 'schema_version', 'route', 'kind', 'windows',
                       'cleanup_confirmed', 'consumer_ready',
                       'compatibility_accepted', 'launch_authorized'})
        _require(type(data['scope']) is str
                 and data['scope'] == 'private_sibling_window_observation')
        _require(type(data['schema_version']) is int and data['schema_version'] == 1)
        _require(type(data['route']) is str and data['route'] in _ROUTES)
        _require(type(data['kind']) is str and data['kind'] in _KINDS)
        _require(data['cleanup_confirmed'] is True)
        for field in ('consumer_ready', 'compatibility_accepted', 'launch_authorized'):
            _require(data[field] is False)
        windows = data['windows']
        _require(type(windows) is list and len(windows) == 3)
        for event, phase in zip(windows, _PHASES):
            _object(event, {'window', 'direct_add', 'create', 'effect',
                            'parent_metadata_changed', 'leaf_metadata_changed',
                            'identity_stable', 'bytes_stable',
                            'parent_sd_stable', 'leaf_sd_stable', 'child'})
            _require(type(event['window']) is str and event['window'] == phase)
            for field in ('identity_stable', 'bytes_stable',
                          'parent_sd_stable', 'leaf_sd_stable'):
                _require(event[field] is True)
            for field in ('parent_metadata_changed', 'leaf_metadata_changed'):
                _require(type(event[field]) is bool)
            _object(event['direct_add'], {'access', 'result'})
            _require(type(event['direct_add']['access']) is int
                     and event['direct_add']['access'] == (2 if data['kind'] == 'file' else 4))
            _require(type(event['direct_add']['result']) is int
                     and event['direct_add']['result'] in ({0} | _DENIED))
            effect = event['effect']
            _require(type(effect) is str and effect in ('created', 'blocked'))
            _require(phase == 'pinned' or effect == 'created')
            created = effect == 'created'
            native = event['create']
            if data['route'] == 'win32':
                _object(native, {'result'})
                _require(type(native['result']) is int)
                _require(native['result'] == 0 if created else native['result'] in _DENIED)
            else:
                _object(native, {'return_u32', 'iosb'} if created else {'return_u32'})
                _require(type(native['return_u32']) is int)
                if created:
                    _require(native['return_u32'] == 0)
                    _object(native['iosb'], {'status_u32', 'information'})
                    _require(type(native['iosb']['status_u32']) is int
                             and native['iosb']['status_u32'] == 0)
                    _require(type(native['iosb']['information']) is int
                             and native['iosb']['information'] == 2)
                else:
                    _require(native['return_u32'] in _NT_DENIED)
            if created:
                child = event['child']
                _object(child, {'identity_distinct', 'volume_matches', 'kind_matches',
                                'nonreparse', 'not_delete_pending', 'protected',
                                'template_verified', 'empty_file'})
                for field in child.keys() - {'empty_file'}:
                    _require(child[field] is True)
                _require(child['empty_file'] is (True if data['kind'] == 'file' else None))
            else:
                _require(event['child'] is None)
        return data
    except Exception:
        raise ValueError('invalid_private_sibling_receipt') from None


class _SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [('nLength', _U32), ('lpSecurityDescriptor', _VOID),
                ('bInheritHandle', _I32)]


def _valid_handle(value):
    return type(value) is int and 0 < value < _INVALID


def _choose(first, error):
    if first is None:
        return error
    if isinstance(first, (KeyboardInterrupt, SystemExit)):
        return first
    if isinstance(error, (KeyboardInterrupt, SystemExit)):
        return error
    return first


class _Slot:
    def __init__(self, path, directory):
        self.path, self.directory = path, directory
        self.owned_path = False
        self.handle = None
        self.close_attempted = self.close_confirmed = False
        self.remove_attempted = self.remove_confirmed = False


class _Ledger:
    def __init__(self, base):
        self.base = base
        self.active, self.retired, self.unknown = set(), set(), set()

    def known(self):
        values = self.active | self.unknown
        observer = self.base.observer
        if observer is not None:
            values |= {owner.value for owner in observer.handles.values()}
        if self.base.pin is not None:
            values |= set(self.base.pin._handles)
            backend = self.base.pin._backend
            values |= set(getattr(backend, '_unknown', ()))
        return values

    def claim(self, slot, handle):
        if not _valid_handle(handle) or handle in self.known():
            raise RuntimeError(_FAILURE)
        slot.handle = handle
        self.active.add(handle)

    def recover(self, slot, handle):
        # A collision is an existing owner, never this acquisition's resource.
        if slot.handle is None and _valid_handle(handle) and handle not in self.known():
            slot.handle = handle
            self.active.add(handle)

    def close(self, slot):
        if slot.close_attempted:
            if not slot.close_confirmed:
                raise RuntimeError(_FAILURE)
            return
        slot.close_attempted = True
        if slot.handle is None:
            slot.close_confirmed = True
            return
        value = slot.handle
        self.active.discard(value)
        self.retired.add(value)
        try:
            result = self.base.api.kernel.CloseHandle(value)
            if type(result) is not int or result == 0:
                raise RuntimeError(_FAILURE)
            slot.close_confirmed = True
        except BaseException:
            self.unknown.add(value)
            raise


class _Creation:
    def __init__(self, base, ledger):
        self.base, self.ledger = base, ledger
        self.kernel = base.api.kernel
        self.kernel.CreateDirectoryW.argtypes = [ctypes.c_wchar_p, _VOID]
        self.kernel.CreateDirectoryW.restype = _I32
        self.ntdll = ctypes.WinDLL('ntdll')
        self.ntdll.NtCreateFile.argtypes = [
            ctypes.POINTER(_VOID), _U32, ctypes.POINTER(_OBJECT_ATTRIBUTES),
            ctypes.POINTER(_IO_STATUS_BLOCK), _VOID, _U32, _U32, _U32, _U32, _VOID, _U32,
        ]
        self.ntdll.NtCreateFile.restype = _I32

    def direct_add(self, kind):
        slot = _Slot(None, True)
        value = None
        try:
            value = self.kernel.CreateFileW(self.base.parent, 2 if kind == 'file' else 4,
                7, None, 3, 0x2200000, None)
            if value == _INVALID:
                code = ctypes.get_last_error()
                if type(code) is not int or code not in _DENIED:
                    raise RuntimeError(_FAILURE)
                return code
            self.ledger.claim(slot, value)
            self.ledger.close(slot)
            return 0
        except BaseException as original:
            try:
                self.ledger.recover(slot, value)
                self.ledger.close(slot)
            except BaseException as cleanup:
                selected = _choose(original, cleanup)
                if selected is not original:
                    raise selected
            raise

    def create(self, route, kind, phase, full_sd, root, slot):
        # Buffers, output containers, result and exact path exist before acquire.
        sa = _SECURITY_ATTRIBUTES(ctypes.sizeof(_SECURITY_ATTRIBUTES), full_sd, 0)
        output, ios = _VOID(), _IO_STATUS_BLOCK()
        basename = 'sibling-' + phase
        encoded = basename.encode('utf-16-le', 'strict')
        if not encoded or len(encoded) + 2 > 65535:
            raise RuntimeError(_FAILURE)
        buffer = ctypes.create_string_buffer(encoded + b'\0\0')
        name = _UNICODE_STRING(len(encoded), len(encoded) + 2, ctypes.addressof(buffer))
        oa = _OBJECT_ATTRIBUTES(ctypes.sizeof(_OBJECT_ATTRIBUTES), root,
            ctypes.pointer(name), 0x1040, full_sd, None)
        result, value = None, None
        confirmed_create = False
        try:
            if route == 'nt_relative':
                result = self.ntdll.NtCreateFile(ctypes.byref(output), 0x120081,
                    ctypes.byref(oa), ctypes.byref(ios), None, 0, 7, 2,
                    0x200020 | (1 if kind == 'directory' else 0x40), None, 0)
                value = output.value
                if type(result) is not int or not -(2**31) <= result < 2**31:
                    raise RuntimeError(_FAILURE)
                unsigned = result & 0xffffffff
                if result != 0:
                    if value is not None or unsigned not in _NT_DENIED:
                        raise RuntimeError(_FAILURE)
                    # Non-pending failure IOSB is not a return-value authority.
                    return 'blocked', {'return_u32': unsigned}
                confirmed_create = ios.u.Status == 0 and ios.Information == 2
                if not confirmed_create:
                    raise RuntimeError(_FAILURE)
                self.ledger.claim(slot, value)
                slot.owned_path = True
                return 'created', {'return_u32': unsigned, 'iosb': {
                    'status_u32': ios.u.Status & 0xffffffff, 'information': ios.Information}}
            if kind == 'directory':
                result = self.kernel.CreateDirectoryW(slot.path, ctypes.byref(sa))
                if type(result) is not int:
                    raise RuntimeError(_FAILURE)
                if result == 0:
                    code = ctypes.get_last_error()
                    if type(code) is not int or code not in _DENIED:
                        raise RuntimeError(_FAILURE)
                    return 'blocked', {'result': code}
                confirmed_create = True
                slot.owned_path = True
                value = self.kernel.CreateFileW(slot.path, 0x120081, 7, None, 3, 0x2200000, None)
                self.ledger.claim(slot, value)
            else:
                result = self.kernel.CreateFileW(slot.path, 0x120081, 7,
                    ctypes.byref(sa), 1, 0x200000, None)
                value = result
                if value == _INVALID:
                    code = ctypes.get_last_error()
                    if type(code) is not int or code not in _DENIED:
                        raise RuntimeError(_FAILURE)
                    return 'blocked', {'result': code}
                # Valid CREATE_NEW result proves pathname creation, but a known
                # numeric owner collision still makes this observation fail.
                confirmed_create = _valid_handle(value) and value not in self.ledger.known()
                self.ledger.claim(slot, value)
                slot.owned_path = True
            return 'created', {'result': 0}
        except BaseException as original:
            # Re-read direct native output; unknown status never authorizes path removal.
            if route == 'nt_relative':
                value = output.value
                confirmed_create = (type(result) is int and result == 0
                                    and ios.u.Status == 0 and ios.Information == 2
                                    and _valid_handle(value)
                                    and (value == slot.handle or value not in self.ledger.known()))
            elif kind == 'directory':
                confirmed_create = type(result) is int and result != 0
            else:
                # Interrupt may arrive after result was stored but before
                # the separate value assignment; recover the native result.
                value = result
                confirmed_create = (_valid_handle(result)
                                    and (result == slot.handle or result not in self.ledger.known()))
            if confirmed_create:
                slot.owned_path = True
            try:
                self.ledger.recover(slot, value)
                self.ledger.close(slot)
            except BaseException as cleanup:
                selected = _choose(original, cleanup)
                if selected is not original:
                    raise selected
            raise


def _query(api, handle, directory):
    file_type = api.kernel.GetFileType(handle)
    if type(file_type) is not int or file_type != 1:
        raise RuntimeError(_FAILURE)
    values = {}
    for info, structure in _INFO_CLASSES.items():
        value = structure()
        result = api.kernel.GetFileInformationByHandleEx(handle, info,
            ctypes.byref(value), ctypes.sizeof(value))
        if type(result) is not int or result == 0:
            raise RuntimeError(_FAILURE)
        values[info] = value
    basic, standard, tag, identity = (values[key] for key in (0, 1, 9, 18))
    if (basic.FileAttributes != tag.FileAttributes or tag.ReparseTag
            or standard.Directory not in (0, 1) or standard.DeletePending not in (0, 1)
            or bool(basic.FileAttributes & 0x10) != bool(standard.Directory)):
        raise RuntimeError(_FAILURE)
    return StartupFileMetadata(identity.VolumeSerialNumber, bytes(identity.FileId),
        bool(standard.Directory), bool(basic.FileAttributes & 0x400),
        bool(standard.DeletePending), 'disk', standard.NumberOfLinks,
        standard.EndOfFile, basic.ChangeTime)


def _child_metadata(meta, directory):
    if type(meta) is not StartupFileMetadata or type(directory) is not bool:
        raise RuntimeError(_FAILURE)
    for field, low, high in (
        ('volume_serial', 0, 2**64 - 1), ('links', 0, 2**32 - 1),
        ('size', 0, 2**63 - 1), ('change_time', -(2**63), 2**63 - 1),
    ):
        value = getattr(meta, field)
        if type(value) is not int or not low <= value <= high:
            raise RuntimeError(_FAILURE)
    if (type(meta.file_id) is not bytes or len(meta.file_id) != 16
            or any(type(getattr(meta, field)) is not bool
                   for field in ('directory', 'reparse', 'delete_pending'))
            or type(meta.file_type) is not str or meta.file_type != 'disk'
            or meta.directory is not directory or meta.reparse or meta.delete_pending
            or (not directory and (meta.links != 1 or meta.size != 0))):
        raise RuntimeError(_FAILURE)
    return meta


def _identity(meta):
    return meta.volume_serial, meta.file_id, meta.directory, meta.file_type


class _Observation:
    def __init__(self, base):
        self.base = base
        self.raw_baseline = None
        self.child_ids = set()

    def sample(self, phase):
        base = self.base
        if phase == 'pinned':
            pin = base.pin
            pin._require_open()
            if not 2 <= len(pin._handles) <= 32:
                raise RuntimeError(_FAILURE)
            parent_handle, leaf_handle = pin._handles[-2:]
            backend = pin._backend
            parent = _metadata(backend.query(parent_handle), directory=True, max_bytes=4096)
            leaf = _metadata(backend.query(leaf_handle), directory=False, max_bytes=4096)
            if (len(pin._baseline) != len(pin._handles)
                    or _identity(pin._baseline[-2]) != _identity(parent)
                    or _identity(pin._baseline[-1]) != _identity(leaf)):
                raise RuntimeError(_FAILURE)
            parent_raw = backend.query_security(parent_handle)
            leaf_raw = backend.query_security(leaf_handle)
            if backend._security_reader.cleanup_unconfirmed:
                raise RuntimeError(_FAILURE)
            content = backend.read(leaf_handle, 0, len(_CONTENT))
        else:
            observer = base.observer
            parent, leaf = observer.query('parent'), observer.query('leaf')
            parent_raw = observer.reader.read(observer.handles['parent'].value)
            leaf_raw = observer.reader.read(observer.handles['leaf'].value)
            if observer.reader.cleanup_unconfirmed:
                raise RuntimeError(_FAILURE)
            handle = observer.handles['leaf'].value
            position, count = ctypes.c_int64(), _U32()
            buffer = ctypes.create_string_buffer(len(_CONTENT))
            result = base.api.kernel.SetFilePointerEx(handle, 0, ctypes.byref(position), 0)
            if type(result) is not int or result == 0 or position.value != 0:
                raise RuntimeError(_FAILURE)
            result = base.api.kernel.ReadFile(handle, buffer, len(_CONTENT), ctypes.byref(count), None)
            if type(result) is not int or result == 0 or count.value != len(_CONTENT):
                raise RuntimeError(_FAILURE)
            content = buffer.raw
        sample = {'parent': parent, 'leaf': leaf, 'bytes': content,
                  'parent_raw': parent_raw, 'leaf_raw': leaf_raw}
        _stable(base.initial, sample)
        for raw in (parent_raw, leaf_raw):
            if type(raw) is not bytes:
                raise RuntimeError(_FAILURE)
            _marker(raw, base.host, 0x80)
        if self.raw_baseline is None:
            # prepare retained only the leaf raw SD; parent continuity starts here.
            if phase != 'unpinned' or leaf_raw != base.initial['raw']:
                raise RuntimeError(_FAILURE)
            self.raw_baseline = (parent_raw, leaf_raw)
        if (parent_raw, leaf_raw) != self.raw_baseline:
            raise RuntimeError(_FAILURE)
        return sample

    def root(self, phase):
        if phase != 'pinned':
            return self.base.observer.handles['parent'].value
        pin = self.base.pin
        pin._require_open()
        if not 2 <= len(pin._handles) <= 32:
            raise RuntimeError(_FAILURE)
        # The immediately preceding sample already bound this position/identity.
        return pin._handles[-2]

    def child(self, slot, kind, before):
        meta = _child_metadata(_query(self.base.api, slot.handle, kind == 'directory'),
                               kind == 'directory')
        key = (meta.volume_serial, meta.file_id)
        reserved = {(before[role].volume_serial, before[role].file_id)
                    for role in ('parent', 'leaf')}
        if (meta.volume_serial != before['parent'].volume_serial
                or key in reserved or key in self.child_ids):
            raise RuntimeError(_FAILURE)
        raw = self.base.observer.reader.read(slot.handle)
        if self.base.observer.reader.cleanup_unconfirmed:
            raise RuntimeError(_FAILURE)
        _marker(raw, self.base.host, 0x80)
        self.child_ids.add(key)
        return {'identity_distinct': True, 'volume_matches': True, 'kind_matches': True,
                'nonreparse': True, 'not_delete_pending': True, 'protected': True,
                'template_verified': True, 'empty_file': True if kind == 'file' else None}


def _remove(slot):
    if not slot.owned_path or slot.remove_attempted:
        return
    slot.remove_attempted = True
    if slot.directory:
        os.rmdir(slot.path)
    else:
        os.unlink(slot.path)
    slot.remove_confirmed = True


def _cleanup(base, ledger, slots, sd, original):
    failure = original
    operations = []
    if base.pin is not None:
        operations.append(base.pin.close)
    if sd is not None:
        operations.append(sd.close)
    for slot in reversed(slots):
        operations.append(lambda slot=slot: ledger.close(slot))
        operations.append(lambda slot=slot: _remove(slot))
    operations.append(base.close)
    for operation in operations:
        try:
            operation()
        except BaseException as error:
            failure = _choose(failure, error)
    if sd is not None and not sd.confirmed:
        failure = _choose(failure, _StageFailure('cleanup'))
    for slot in slots:
        if not slot.close_confirmed or (slot.owned_path and not slot.remove_confirmed):
            failure = _choose(failure, _StageFailure('cleanup'))
    return failure


def _run_variant(route, kind):
    stage, base, ledger, sd = 'fixture', None, None, None
    slots, events, original = [], [], None
    try:
        base = _Fixture('parent', 'new')
        ledger = _Ledger(base)
        stage = 'prepare'
        base.prepare()
        stage = 'initial'
        observe = _Observation(base)
        create = _Creation(base, ledger)
        stage = 'child_sd'
        sd = _ConvertedDacl(base.api)
        sd.acquire(base.host, 0x80)
        # acquire returns an interior DACL pointer, not the full creation SD.
        full_sd = sd.output.value
        if not _valid_handle(full_sd):
            raise RuntimeError(_FAILURE)
        for phase in _PHASES:
            if phase == 'pinned':
                stage = 'start_pin'
                base.start_pin()
            elif phase == 'released':
                stage = 'release_pin'
                values = tuple(base.pin._handles)
                base.pin.close()
                if base.pin.close_confirmed is not True:
                    raise RuntimeError(_FAILURE)
                ledger.retired.update(values)
                base.pin = None
            stage = phase + '_before'
            before = observe.sample(phase)
            stage = phase + '_direct_add'
            direct_error = None
            try:
                direct = create.direct_add(kind)
            except Exception as error:
                direct_error = error
            # KI/SE from ADD is deliberately outside this ordinary-error branch.
            slot = _Slot(os.path.join(base.parent, 'sibling-' + phase), kind == 'directory')
            slots.append(slot)
            stage = phase + '_create'
            try:
                effect, native = create.create(route, kind, phase, full_sd, observe.root(phase), slot)
            except BaseException as error:
                if direct_error is not None:
                    raise _choose(direct_error, error)
                raise
            if direct_error is not None:
                stage = phase + '_direct_add'
                raise direct_error
            stage = phase + '_after'
            after = observe.sample(phase)
            stage = phase + '_child'
            if phase != 'pinned' and effect != 'created':
                raise RuntimeError(_FAILURE)
            child = observe.child(slot, kind, before) if effect == 'created' else None
            events.append({'window': phase, 'direct_add': {
                'access': 2 if kind == 'file' else 4, 'result': direct},
                'create': native, 'effect': effect,
                'parent_metadata_changed': before['parent'] != after['parent'],
                'leaf_metadata_changed': before['leaf'] != after['leaf'],
                'identity_stable': True, 'bytes_stable': True,
                'parent_sd_stable': True, 'leaf_sd_stable': True, 'child': child})
    except BaseException as error:
        original = error if isinstance(error, (KeyboardInterrupt, SystemExit)) else _StageFailure(stage)
    if base is not None:
        error = _cleanup(base, ledger, slots, sd, original)
        if error is not None:
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise error
            raise original if original is not None else _StageFailure('cleanup')
    elif original is not None:
        raise original
    data = {'scope': 'private_sibling_window_observation', 'schema_version': 1,
            'route': route, 'kind': kind, 'windows': events, 'cleanup_confirmed': True,
            'consumer_ready': False, 'compatibility_accepted': False, 'launch_authorized': False}
    try:
        wire = _encode(data)
        validate_wire(wire)
        return wire
    except Exception:
        raise _StageFailure('wire') from None


def run_variant(route, kind):
    if (type(route) is not str or route not in _ROUTES
            or type(kind) is not str or kind not in _KINDS or os.name != 'nt'):
        raise RuntimeError(_FAILURE)
    try:
        return _run_variant(route, kind)
    except Exception as error:
        if failure_message(error) != _FAILURE:
            raise _StageFailure(error.args[0]) from None
        raise RuntimeError(_FAILURE) from None
