"""Internal fixed installed source consumer; no launch or publisher authority."""
import os
from pathlib import PureWindowsPath
import sysconfig

from .native_helper import windows_arch_from_platform
from .windows_startup_pin import (StartupPinError, StartupPinCloseError, MAX_STARTUP_BYTES,
                                  _local_components, _metadata, pin_startup_file)
from .windows_startup_native import WindowsStartupPinBackend
from .windows_startup_host_identity import WindowsStartupHostIdentity
from .windows_startup_security import (StartupSecurityError, _validate_host_sid,
                                       parse_startup_security, check_startup_security)


_MAX_CHAIN_NODES = 32
_MAX_SNAPSHOT_ACES = 512


def _installed_resources():
    _local_components(__file__)
    module = PureWindowsPath(__file__)
    if module.name != 'windows_startup_source.py' or module.parent.name != 'icode':
        raise StartupPinError('invalid installed startup source module')
    arch = windows_arch_from_platform(sysconfig.get_platform())
    resources = tuple((resource, str(module.parent / 'native' / name))
                      for resource, name in (
                          ('helper', f'icode-sandbox-windows-{arch}.exe'),
                          ('verifier', f'icode-provenance-windows-{arch}.exe')))
    for _, path in resources:
        _, components = _local_components(path)
        if not 2 <= len(components) + 1 <= _MAX_CHAIN_NODES:
            raise StartupPinError('startup source chain exceeds node budget')
    return resources


class PinnedStartupSources:
    """Single trusted actor owns both source chains; private fields are not isolation."""

    def __init__(self, host_sid):
        self._host_sid = host_sid
        self._owners = []
        self._snapshots = ()
        self._ready = False
        self._closed = False
        self._close_errors = ()

    def __copy__(self):
        raise StartupPinError('startup source owner cannot be copied')

    def __deepcopy__(self, memo):
        raise StartupPinError('startup source owner cannot be copied')

    def __reduce_ex__(self, protocol):
        raise StartupPinError('startup source owner cannot be serialized')

    @property
    def closed(self):
        return self._closed

    @property
    def close_confirmed(self):
        return self._closed and all(owner.close_confirmed for _, owner in self._owners)

    @property
    def close_errors(self):
        return self._close_errors

    def _require_open(self):
        if self._closed or not self._ready:
            raise StartupPinError('startup source owner is closed or uninitialized')

    def _resource(self, resource):
        self._require_open()
        if type(resource) is not str or resource not in ('helper', 'verifier'):
            raise StartupPinError('invalid startup source resource')
        for name, owner in self._owners:
            if name == resource:
                return owner
        raise StartupPinError('invalid startup source resource')

    def content(self, resource):
        return self._resource(resource).content

    def sha256(self, resource):
        return self._resource(resource).sha256

    def _verify_metadata(self, owner):
        owner._require_open()
        if (not 2 <= len(owner._handles) <= _MAX_CHAIN_NODES
                or len(owner._handles) != len(owner._baseline)):
            raise StartupPinError('invalid startup source chain shape')
        # Never use the child revalidator: failures must close both resources
        # in global reverse acquisition order, not prematurely close this child.
        for handle, baseline in zip(owner._handles, owner._baseline):
            current = _metadata(owner._backend.query(handle), directory=baseline.directory,
                                max_bytes=MAX_STARTUP_BYTES)
            if current != baseline:
                raise StartupPinError('pinned startup source metadata changed')

    def _verify(self):
        budget = 0
        snapshots = []
        for _, owner in self._owners:
            self._verify_metadata(owner)
            raws = []
            for handle, baseline in zip(owner._handles, owner._baseline):
                before = _metadata(owner._backend.query(handle), directory=baseline.directory,
                                   max_bytes=MAX_STARTUP_BYTES)
                if before != baseline:
                    raise StartupPinError('pinned startup source metadata changed')
                first = owner._backend.query_security(handle)
                second = owner._backend.query_security(handle)
                after = _metadata(owner._backend.query(handle), directory=baseline.directory,
                                  max_bytes=MAX_STARTUP_BYTES)
                if before != baseline or after != baseline:
                    raise StartupPinError('pinned startup source metadata changed')
                if type(first) is not bytes or type(second) is not bytes or first != second:
                    raise StartupSecurityError('startup source security snapshots differ')
                budget += len(parse_startup_security(first).entries)
                budget += len(parse_startup_security(second).entries)
                if budget > _MAX_SNAPSHOT_ACES:
                    raise StartupSecurityError('startup source security entry budget exceeded')
                check_startup_security(first, role='source', host_sid=self._host_sid,
                                       directory=baseline.directory)
                raws.append(first)
            self._verify_metadata(owner)
            snapshots.append(tuple(raws))
        result = tuple(snapshots)
        if self._snapshots and result != self._snapshots:
            raise StartupSecurityError('startup source security changed since pin')
        return result

    def revalidate(self):
        self._require_open()
        try:
            self._verify()
        except BaseException as original:
            self._close_preserving_exception(original)
            raise

    def close(self):
        if self._closed:
            return
        self._closed = True
        errors = []
        for _, owner in reversed(self._owners):
            try:
                owner.close()
            except BaseException as error:
                errors.append(error)
        self._close_errors = tuple(errors)
        if errors:
            for error in errors:
                if not isinstance(error, Exception):
                    raise error
            raise StartupPinCloseError(self._close_errors)

    def _close_preserving_exception(self, original):
        already_closed = self._closed
        try:
            self.close()
        except BaseException:
            pass
        if not self.close_confirmed and not already_closed:
            try:
                BaseException.add_note(original, 'Startup source cleanup unconfirmed')
            except BaseException:
                pass

    def __enter__(self):
        self._require_open()
        return self

    def __exit__(self, exc_type, exc, traceback):
        if exc is not None:
            self._close_preserving_exception(exc)
        else:
            self.close()
        return False


def pin_installed_startup_sources():
    if os.name != 'nt':
        raise StartupPinError('native Windows startup source consumer unavailable')
    resources = _installed_resources()
    identity = WindowsStartupHostIdentity()
    host_sid = identity.capture()
    if identity.cleanup_unconfirmed is not False:
        raise StartupSecurityError('Startup host identity cleanup unconfirmed')
    _validate_host_sid(host_sid)
    result = PinnedStartupSources(host_sid)
    pending = None
    try:
        for resource, path in resources:
            pending = pin_startup_file(path, _backend=WindowsStartupPinBackend())
            # Protect the acquisition-to-registration window, including an
            # append that registered its value before raising an interrupt.
            result._owners.append((resource, pending))
            pending = None
        result._snapshots = result._verify()
        result._ready = True
        return result
    except BaseException as original:
        if pending is not None:
            pending._close_preserving_exception(original)
        result._close_preserving_exception(original)
        raise
