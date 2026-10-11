"""CI-only private DACL window fixture; never a security or launch authority."""
import ctypes
import json
import os
import tempfile

from icode.windows_startup_pin import StartupFileMetadata, _metadata, _local_components, pin_startup_file
from icode.windows_startup_native import _INFO_CLASSES
from icode.windows_startup_security_native import WindowsStartupSecurityReader
from icode.windows_startup_security import parse_startup_security, _validate_host_sid
from icode.windows_startup_host_identity import WindowsStartupHostIdentity


_DENIED = {5, 32, 33}
_U32, _I32, _VOID = ctypes.c_uint32, ctypes.c_int32, ctypes.c_void_p
_INVALID = _VOID(-1).value
_CONTENT = b'private-dacl-fixture\n'
_MAX_NODES = 32
_MAX_BYTES = 4096
_MAX_SD = 128 * 1024
_FAILURE = 'private_dacl_window_failed'


def _require(condition):
    if not condition:
        raise ValueError('invalid_private_dacl_receipt')


def _object(value, keys):
    _require(type(value) is dict and value.keys() == keys)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def run_variant(target, opener):
    if (os.name != 'nt' or type(target) is not str or target not in ('parent', 'leaf')
            or type(opener) is not str or opener not in ('preexisting', 'new')):
        raise RuntimeError(_FAILURE)
    try:
        return _run_variant(target, opener)
    except Exception:
        raise RuntimeError(_FAILURE) from None


class _Native:
    def __init__(self):
        if os.name != 'nt':
            raise RuntimeError(_FAILURE)
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.advapi = ctypes.WinDLL('advapi32', use_last_error=True)
        signatures = (
            (self.kernel.CreateFileW, [ctypes.c_wchar_p, _U32, _U32, _VOID, _U32, _U32, _VOID], _VOID),
            (self.kernel.CloseHandle, [_VOID], _I32),
            (self.kernel.LocalFree, [_VOID], _VOID),
            (self.kernel.GetFileType, [_VOID], _U32),
            (self.kernel.GetFileInformationByHandleEx, [_VOID, _I32, _VOID, _U32], _I32),
            (self.kernel.SetFilePointerEx, [_VOID, ctypes.c_int64, ctypes.POINTER(ctypes.c_int64), _U32], _I32),
            (self.kernel.ReadFile, [_VOID, _VOID, _U32, ctypes.POINTER(_U32), _VOID], _I32),
            (self.kernel.GetVolumeInformationByHandleW,
             [_VOID, ctypes.c_wchar_p, _U32, ctypes.POINTER(_U32), ctypes.POINTER(_U32),
              ctypes.POINTER(_U32), ctypes.c_wchar_p, _U32], _I32),
            (self.advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW,
             [ctypes.c_wchar_p, _U32, ctypes.POINTER(_VOID), ctypes.POINTER(_U32)], _I32),
            (self.advapi.IsValidSecurityDescriptor, [_VOID], _I32),
            (self.advapi.GetSecurityDescriptorLength, [_VOID], _U32),
            (self.advapi.GetSecurityDescriptorDacl,
             [_VOID, ctypes.POINTER(_I32), ctypes.POINTER(_VOID), ctypes.POINTER(_I32)], _I32),
            (self.advapi.SetSecurityInfo, [_VOID, _I32, _U32, _VOID, _VOID, _VOID, _VOID], _U32),
        )
        for function, arguments, result in signatures:
            function.argtypes, function.restype = arguments, result

    @staticmethod
    def call(function, *arguments):
        try:
            return function(*arguments)
        except Exception:
            raise RuntimeError(_FAILURE) from None

    def open(self, path, directory, *, observe=False):
        owner = _OwnedHandle(self)
        value = None
        try:
            value = self.call(self.kernel.CreateFileW, path, 0x120081 if observe else 0x60000,
                              7, None, 3, 0x200000 | (0x2000000 if directory else 0), None)
            if value == _INVALID:
                code = ctypes.get_last_error()
                if type(code) is not int or code not in _DENIED:
                    raise RuntimeError(_FAILURE)
                return None, code
            if type(value) is not int or not 0 < value < _INVALID:
                raise RuntimeError(_FAILURE)
            owner.value = value
            return owner, 0
        except BaseException:
            # Acquisition was not returned to its caller. Retire this value
            # once even if assignment/registration was interrupted.
            try:
                if type(value) is int and 0 < value < _INVALID:
                    if owner.value is None:
                        owner.value = value
                    owner.close()
            except BaseException:
                pass
            raise

    def require_ntfs(self, handle):
        filesystem = ctypes.create_unicode_buffer(32)
        serial, maximum, flags = _U32(), _U32(), _U32()
        result = self.call(self.kernel.GetVolumeInformationByHandleW, handle, None, 0,
                           ctypes.byref(serial), ctypes.byref(maximum), ctypes.byref(flags), filesystem, 32)
        if type(result) is not int or result == 0 or filesystem.value != 'NTFS':
            raise RuntimeError(_FAILURE)

    def set_marker(self, handle, host, marker):
        _validate_host_sid(host)
        if type(marker) is not int or marker not in (0x80, 0x100):
            raise RuntimeError(_FAILURE)
        owner = _ConvertedDacl(self)
        try:
            dacl = owner.acquire(host, marker)
            result = self.call(self.advapi.SetSecurityInfo, handle, 1, 0x80000004,
                               None, None, dacl, None)
            if type(result) is not int or not 0 <= result <= 2**32 - 1:
                raise RuntimeError(_FAILURE)
        except BaseException:
            try:
                owner.close()
            except BaseException:
                pass
            raise
        owner.close()
        return result


class _OwnedHandle:
    def __init__(self, api):
        self.api, self.value = api, None
        self.closed = self.confirmed = False

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.value is None:
            self.confirmed = True
            return
        result = self.api.call(self.api.kernel.CloseHandle, self.value)
        if type(result) is not int or result == 0:
            raise RuntimeError(_FAILURE)
        self.confirmed = True


class _ConvertedDacl:
    def __init__(self, api):
        self.api, self.output = api, _VOID()
        self.closed = self.confirmed = False

    def acquire(self, host, marker):
        text = f'D:P(A;;FA;;;{host})(A;;FA;;;SY)(A;;FA;;;BA)(A;;0x{marker:x};;;WD)'
        length = _U32()
        result = self.api.call(self.api.advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW,
                               text, 1, ctypes.byref(self.output), ctypes.byref(length))
        if (type(result) is not int or result == 0 or not self.output.value
                or not 20 <= length.value <= _MAX_SD
                or not self.api.call(self.api.advapi.IsValidSecurityDescriptor, self.output.value)
                or self.api.call(self.api.advapi.GetSecurityDescriptorLength, self.output.value) != length.value):
            raise RuntimeError(_FAILURE)
        present, defaulted, dacl = _I32(), _I32(), _VOID()
        result = self.api.call(self.api.advapi.GetSecurityDescriptorDacl, self.output.value,
                               ctypes.byref(present), ctypes.byref(dacl), ctypes.byref(defaulted))
        if (type(result) is not int or result == 0 or present.value != 1 or defaulted.value != 0
                or not dacl.value or not self.output.value <= dacl.value <= self.output.value + length.value - 8):
            raise RuntimeError(_FAILURE)
        return dacl.value

    def close(self):
        if self.closed:
            return
        self.closed = True
        if not self.output.value:
            self.confirmed = True
            return
        if self.api.call(self.api.kernel.LocalFree, self.output.value) is not None:
            raise RuntimeError(_FAILURE)
        self.confirmed = True


class _Observer:
    """Separate full-share handles: never inserted into the pin backend."""
    def __init__(self, api, parent, leaf):
        self.api, self.handles, self.closed = api, {}, False
        self.reader = WindowsStartupSecurityReader()
        pending = None
        try:
            for role, path in (('parent', parent), ('leaf', leaf)):
                pending, status = api.open(path, role == 'parent', observe=True)
                if status != 0:
                    raise RuntimeError(_FAILURE)
                self.handles[role] = pending
                pending = None
            api.require_ntfs(self.handles['parent'].value)
        except BaseException:
            try:
                if pending is not None:
                    pending.close()
            except BaseException:
                pass
            try:
                self.close()
            except BaseException:
                pass
            raise

    def query(self, role):
        handle = self.handles[role].value
        if self.api.call(self.api.kernel.GetFileType, handle) != 1:
            raise RuntimeError(_FAILURE)
        values = {}
        for kind, structure in _INFO_CLASSES.items():
            value = structure()
            result = self.api.call(self.api.kernel.GetFileInformationByHandleEx,
                                   handle, kind, ctypes.byref(value), ctypes.sizeof(value))
            if type(result) is not int or result == 0:
                raise RuntimeError(_FAILURE)
            values[kind] = value
        basic, standard, tag, identity = (values[k] for k in (0, 1, 9, 18))
        if (basic.FileAttributes != tag.FileAttributes or tag.ReparseTag or standard.EndOfFile < 0
                or standard.Directory not in (0, 1) or standard.DeletePending not in (0, 1)
                or bool(basic.FileAttributes & 16) != bool(standard.Directory)):
            raise RuntimeError(_FAILURE)
        return _metadata(StartupFileMetadata(identity.VolumeSerialNumber, bytes(identity.FileId),
            bool(standard.Directory), bool(basic.FileAttributes & 0x400), bool(standard.DeletePending),
            'disk', standard.NumberOfLinks, standard.EndOfFile, basic.ChangeTime),
            directory=role == 'parent', max_bytes=_MAX_BYTES)

    def sample(self, target):
        if self.closed or target not in ('parent', 'leaf'):
            raise RuntimeError(_FAILURE)
        parent, leaf = self.query('parent'), self.query('leaf')
        handle = self.handles['leaf'].value
        position = ctypes.c_int64()
        result = self.api.call(self.api.kernel.SetFilePointerEx, handle, 0, ctypes.byref(position), 0)
        if type(result) is not int or result == 0 or position.value != 0:
            raise RuntimeError(_FAILURE)
        buffer, count = ctypes.create_string_buffer(leaf.size), _U32()
        result = self.api.call(self.api.kernel.ReadFile, handle, buffer, leaf.size, ctypes.byref(count), None)
        if type(result) is not int or result == 0 or count.value != leaf.size:
            raise RuntimeError(_FAILURE)
        raw = self.reader.read(self.handles[target].value)
        if self.reader.cleanup_unconfirmed:
            raise RuntimeError(_FAILURE)
        return {'parent': parent, 'leaf': leaf, 'raw': raw, 'bytes': buffer.raw}

    def close(self):
        if self.closed:
            return
        self.closed = True
        _close_all(list(reversed(list(self.handles.values()))))


def _close_all(owners):
    failure = None
    for owner in owners:
        try:
            owner.close()
            confirmed = owner.close_confirmed if hasattr(owner, 'close_confirmed') else owner.confirmed
            if confirmed is not True:
                raise RuntimeError(_FAILURE)
        except BaseException as error:
            if failure is None or isinstance(error, (KeyboardInterrupt, SystemExit)):
                failure = error
    if failure is not None:
        raise failure


def _marker(raw, host, marker):
    parsed = parse_startup_security(raw)
    expected = sorted([(True, 0, 0x1f01ff, value) for value in
                       (host, 'S-1-5-18', 'S-1-5-32-544')] + [(True, 0, marker, 'S-1-1-0')])
    actual = sorted((entry.allowed, entry.flags, entry.mask, entry.sid) for entry in parsed.entries)
    if not parsed.control & 0x1000 or actual != expected:
        raise RuntimeError(_FAILURE)


def _stable(before, after):
    for role in ('parent', 'leaf'):
        first, last = before[role], after[role]
        _metadata(first, directory=role == 'parent', max_bytes=_MAX_BYTES)
        _metadata(last, directory=role == 'parent', max_bytes=_MAX_BYTES)
        if (first.volume_serial, first.file_id, first.directory, first.file_type) != (
                last.volume_serial, last.file_id, last.directory, last.file_type):
            raise RuntimeError(_FAILURE)
    if before['bytes'] != _CONTENT or after['bytes'] != _CONTENT:
        raise RuntimeError(_FAILURE)


def _event(target, phase, opened, status, before, after, host):
    try:
        if (target not in ('parent', 'leaf') or phase not in ('unpinned', 'pinned', 'released')
                or (opened is not None and (type(opened) is not int or opened not in ({0} | _DENIED)))):
            raise RuntimeError(_FAILURE)
        denied = opened in _DENIED
        if ((denied and status is not None) or (not denied and
                (type(status) is not int or status not in ({0} | _DENIED)))):
            raise RuntimeError(_FAILURE)
        changed = not denied and status == 0
        if phase != 'pinned' and not changed:
            raise RuntimeError(_FAILURE)
        _validate_host_sid(host)
        _marker(before['raw'], host, 0x80)
        _marker(after['raw'], host, 0x100 if changed else 0x80)
        _stable(before, after)
        if (before['raw'] != after['raw']) is not changed:
            raise RuntimeError(_FAILURE)
        return {'window': phase, 'open_result': opened, 'set_result': status,
                'effect': 'changed' if changed else 'blocked', 'sd_changed': changed,
                'metadata_changed': before[target] != after[target], 'identity_stable': True,
                'bytes_stable': True, 'protected': True}
    except Exception:
        raise RuntimeError(_FAILURE) from None


def _windows(fixture, target):
    events = []
    fixture.reset()
    before = fixture.sample()
    opened, status = fixture.operate()
    events.append(_event(target, 'unpinned', opened, status, before, fixture.sample(), fixture.host))
    # Reset BEFORE pinning, never while the restrictive owner is alive.
    fixture.reset()
    baseline = fixture.sample()
    fixture.start_pin()
    before = fixture.pinned_sample()
    _stable(baseline, before)
    _marker(before['raw'], fixture.host, 0x80)
    opened, status = fixture.operate()
    events.append(_event(target, 'pinned', opened, status, before, fixture.pinned_sample(), fixture.host))
    _close_all([fixture.pin])
    fixture.pin = None
    fixture.reset()
    before = fixture.sample()
    opened, status = fixture.operate()
    events.append(_event(target, 'released', opened, status, before, fixture.sample(), fixture.host))
    return events


class _Fixture:
    """Own only objects created by this one private observation."""
    def __init__(self, target, opener):
        self.target, self.opener = target, opener
        self.root = self.parent = self.leaf = None
        self.parent_created = self.leaf_created = False
        self.observer = self.writer = self.pending = self.pin = None
        self.initial = None
        identity = WindowsStartupHostIdentity()
        self.host = identity.capture()
        if identity.cleanup_unconfirmed:
            raise RuntimeError(_FAILURE)
        self.api = _Native()

    def prepare(self):
        root = None
        try:
            root = tempfile.mkdtemp(prefix='icode-private-dacl-')
            self.root = root
        except BaseException:
            if root is not None:
                try:
                    os.rmdir(root)
                except BaseException:
                    pass
            raise
        self.parent = os.path.join(self.root, 'parent')
        created = object()
        try:
            created = os.mkdir(self.parent)
            self.parent_created = True
        except BaseException:
            # mkdir's known successful return is None. An attempted/failed
            # creation is not ownership of a pre-existing directory.
            if created is None:
                self.parent_created = True
            raise
        self.leaf = os.path.join(self.parent, 'leaf')
        stream = None
        try:
            stream = open(self.leaf, 'xb')
            self.leaf_created = True
            if stream.write(_CONTENT) != len(_CONTENT):
                raise RuntimeError(_FAILURE)
        except BaseException:
            if stream is not None:
                self.leaf_created = True
                try:
                    stream.close()
                except BaseException:
                    pass
            raise
        stream.close()
        _, components = _local_components(self.leaf)
        if not 2 <= len(components) + 1 <= _MAX_NODES:
            raise RuntimeError(_FAILURE)
        for role in ('parent', 'leaf'):
            code = self.acquire(role, 'pending')
            if code != 0 or self.api.set_marker(self.pending.value, self.host, 0x80) != 0:
                raise RuntimeError(_FAILURE)
            _close_all([self.pending])
            self.pending = None
        self.start_observer()
        for role in ('parent', 'leaf'):
            initial = self.observer.sample(role)
            _marker(initial['raw'], self.host, 0x80)
            _stable(initial, initial)
            if self.initial is not None:
                _stable(self.initial, initial)
            self.initial = initial
        if self.opener == 'preexisting':
            code = self.acquire(self.target, 'writer')
            if code != 0:
                raise RuntimeError(_FAILURE)

    def sample(self):
        value = self.observer.sample(self.target)
        if self.initial is not None:
            _stable(self.initial, value)
        return value

    def acquire(self, role, slot):
        owner = None
        try:
            owner, code = self.api.open(getattr(self, role), role == 'parent')
            setattr(self, slot, owner)
            return code
        except BaseException:
            if owner is not None:
                try:
                    owner.close()
                except BaseException:
                    pass
            raise

    def start_observer(self):
        owner = None
        try:
            owner = _Observer(self.api, self.parent, self.leaf)
            self.observer = owner
        except BaseException:
            if owner is not None:
                try:
                    owner.close()
                except BaseException:
                    pass
            raise

    def reset(self):
        if self.writer is not None:
            result = self.api.set_marker(self.writer.value, self.host, 0x80)
        else:
            code = self.acquire(self.target, 'pending')
            if code != 0:
                raise RuntimeError(_FAILURE)
            result = self.api.set_marker(self.pending.value, self.host, 0x80)
            _close_all([self.pending])
            self.pending = None
        if result != 0:
            raise RuntimeError(_FAILURE)

    def operate(self):
        if self.writer is not None:
            return None, self.api.set_marker(self.writer.value, self.host, 0x100)
        opened = self.acquire(self.target, 'pending')
        if opened != 0:
            return opened, None
        result = self.api.set_marker(self.pending.value, self.host, 0x100)
        _close_all([self.pending])
        self.pending = None
        return opened, result

    def start_pin(self):
        owner = None
        try:
            owner = pin_startup_file(self.leaf, max_bytes=_MAX_BYTES)
            self.pin = owner
        except BaseException:
            if owner is not None:
                try:
                    owner.close()
                except BaseException:
                    pass
            raise

    def pinned_sample(self):
        self.pin._require_open()
        if not 2 <= len(self.pin._handles) <= _MAX_NODES:
            raise RuntimeError(_FAILURE)
        backend = self.pin._backend
        parent, leaf = self.pin._handles[-2:]
        first = _metadata(backend.query(parent), directory=True, max_bytes=_MAX_BYTES)
        last = _metadata(backend.query(leaf), directory=False, max_bytes=_MAX_BYTES)
        raw = backend.query_security(parent if self.target == 'parent' else leaf)
        content = backend.read(leaf, 0, last.size)
        value = {'parent': first, 'leaf': last, 'raw': raw, 'bytes': content}
        if self.initial is not None:
            _stable(self.initial, value)
        return value

    def close(self):
        failure = None
        for owner in (self.pending, self.pin, self.writer, self.observer):
            if owner is None:
                continue
            try:
                if owner is self.observer:
                    owner.close()
                else:
                    _close_all([owner])
            except BaseException as error:
                if failure is None or isinstance(error, (KeyboardInterrupt, SystemExit)):
                    failure = error
        for path, directory, created in ((self.leaf, False, self.leaf_created),
                (self.parent, True, self.parent_created), (self.root, True, self.root is not None)):
            if not created:
                continue
            try:
                if directory:
                    os.rmdir(path)
                else:
                    os.unlink(path)
            except BaseException as error:
                if failure is None or isinstance(error, (KeyboardInterrupt, SystemExit)):
                    failure = error
        if failure is not None:
            raise failure


def _run_variant(target, opener):
    fixture = _Fixture(target, opener)
    try:
        fixture.prepare()
        windows = _windows(fixture, target)
    except BaseException:
        try:
            fixture.close()
        except BaseException:
            pass
        raise
    fixture.close()
    data = {'scope': 'private_dacl_window_observation', 'schema_version': 1,
            'target': target, 'opener': opener,
            'acquisition': {'phase': 'before_windows', 'result': 0} if opener == 'preexisting' else None,
            'windows': windows, 'cleanup_confirmed': True, 'consumer_ready': False,
            'compatibility_accepted': False, 'launch_authorized': False}
    wire = json.dumps(data, separators=(',', ':')).encode('ascii') + b'\n'
    validate_wire(wire)
    return wire


def validate_wire(wire):
    try:
        _require(type(wire) is bytes and 1 <= len(wire) <= 8192 and wire.endswith(b'\n'))
        data = json.loads(wire.decode('ascii', 'strict'), object_pairs_hook=_unique)
        _require(json.dumps(data, separators=(',', ':')).encode('ascii') + b'\n' == wire)
        _object(data, {'scope', 'schema_version', 'target', 'opener', 'acquisition', 'windows',
                       'cleanup_confirmed', 'consumer_ready', 'compatibility_accepted', 'launch_authorized'})
        _require(type(data['scope']) is str and data['scope'] == 'private_dacl_window_observation')
        _require(type(data['schema_version']) is int and data['schema_version'] == 1)
        _require(type(data['target']) is str and data['target'] in ('parent', 'leaf'))
        _require(type(data['opener']) is str and data['opener'] in ('preexisting', 'new'))
        for key in ('consumer_ready', 'compatibility_accepted', 'launch_authorized'):
            _require(data[key] is False)
        _require(data['cleanup_confirmed'] is True)
        preexisting = data['opener'] == 'preexisting'
        if preexisting:
            _object(data['acquisition'], {'phase', 'result'})
            _require(type(data['acquisition']['phase']) is str and data['acquisition']['phase'] == 'before_windows')
            _require(type(data['acquisition']['result']) is int and data['acquisition']['result'] == 0)
        else:
            _require(data['acquisition'] is None)
        windows = data['windows']
        _require(type(windows) is list and len(windows) == 3)
        for event, phase in zip(windows, ('unpinned', 'pinned', 'released')):
            _object(event, {'window', 'open_result', 'set_result', 'effect', 'sd_changed',
                            'metadata_changed', 'identity_stable', 'bytes_stable', 'protected'})
            _require(type(event['window']) is str and event['window'] == phase)
            for key in ('identity_stable', 'bytes_stable', 'protected'):
                _require(event[key] is True)
            for key in ('sd_changed', 'metadata_changed'):
                _require(type(event[key]) is bool)
            opened, status = event['open_result'], event['set_result']
            if preexisting:
                _require(opened is None)
            else:
                _require(type(opened) is int and opened in ({0} | _DENIED))
            denied_open = not preexisting and opened in _DENIED
            if denied_open:
                _require(status is None)
            else:
                _require(type(status) is int and status in ({0} | _DENIED))
            changed = not denied_open and status == 0
            _require(type(event['effect']) is str and event['effect'] == ('changed' if changed else 'blocked'))
            _require(event['sd_changed'] is changed)
            _require(phase == 'pinned' or changed)
        return data
    except Exception:
        raise ValueError('invalid_private_dacl_receipt') from None
