"""Private HANDLE security snapshot transport; no access or launch authority.

The caller owns the file HANDLE and must serialize its complete query lifetime
against close/open. This reader is single-actor: calls must not overlap. Only
OS-owned, validated descriptor allocations are dereferenced; numeric HANDLE
validation does not prove ownership. The byte budget is an internal limit, not
a claim about the maximum descriptor supported by Windows.
"""
import ctypes
import os

from .windows_startup_security import StartupSecurityError, parse_startup_security


_U32 = ctypes.c_uint32
_U16 = ctypes.c_uint16
_I32 = ctypes.c_int32
_VOID = ctypes.c_void_p
_INVALID = _VOID(-1).value
_MIN_BYTES = 20
_MAX_BYTES = 128 * 1024
_SE_FILE_OBJECT = 1
_OWNER_AND_DACL_SECURITY_INFORMATION = 0x5
_SELF_RELATIVE = 0x8000
_CLEANUP_NOTE = 'Startup security descriptor cleanup unconfirmed'


class WindowsStartupSecurityReader:
    """Copy a bounded descriptor, releasing its allocation before returning."""

    def __init__(self):
        if os.name != 'nt':
            raise StartupSecurityError('native Windows startup security reader unavailable')
        self.cleanup_unconfirmed = False
        try:
            self._advapi32 = ctypes.WinDLL('advapi32', use_last_error=True)
            self._kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            signatures = {
                'GetSecurityInfo': ([_VOID, _I32, _U32] + [ctypes.POINTER(_VOID)] * 5, _U32),
                'IsValidSecurityDescriptor': ([_VOID], _I32),
                'GetSecurityDescriptorControl': (
                    [_VOID, ctypes.POINTER(_U16), ctypes.POINTER(_U32)], _I32),
                'GetSecurityDescriptorLength': ([_VOID], _U32),
            }
            for name, (arguments, result) in signatures.items():
                function = getattr(self._advapi32, name)
                function.argtypes, function.restype = arguments, result
            self._kernel32.LocalFree.argtypes = [_VOID]
            self._kernel32.LocalFree.restype = _VOID
        except Exception:
            raise StartupSecurityError('native Windows startup security API unavailable') from None

    @staticmethod
    def _call(function, *arguments):
        try:
            return function(*arguments)
        except Exception:
            raise StartupSecurityError('startup security native API invocation failed') from None

    def _release(self, output, original=None):
        if not output.value:
            return
        # Mark unknown before the call: even an allocator that frees then raises
        # cannot justify retrying the old address. Only a NULL receipt confirms.
        self.cleanup_unconfirmed = True
        try:
            result = self._call(self._kernel32.LocalFree, output.value)
            if result is not None:
                raise StartupSecurityError(_CLEANUP_NOTE)
            self.cleanup_unconfirmed = False
        except BaseException:
            if original is None:
                raise
            try:
                BaseException.add_note(original, _CLEANUP_NOTE)
            except BaseException:
                pass

    def read(self, handle: int) -> bytes:
        """Read owned immutable bytes; caller retains all HANDLE ownership."""
        if self.cleanup_unconfirmed:
            raise StartupSecurityError(_CLEANUP_NOTE)
        if type(handle) is not int or not 0 < handle < _INVALID:
            raise StartupSecurityError('invalid startup security HANDLE')
        output = _VOID()
        try:
            # The acquisition call itself belongs inside the cleanup boundary:
            # it can write the owned output and then raise an interrupt/error.
            status = self._call(self._advapi32.GetSecurityInfo, handle,
                                _SE_FILE_OBJECT, _OWNER_AND_DACL_SECURITY_INFORMATION,
                                None, None, None, None, ctypes.byref(output))
            if type(status) is not int or status != 0 or not output.value:
                raise StartupSecurityError('startup security descriptor query failed')
            if not self._call(self._advapi32.IsValidSecurityDescriptor, output.value):
                raise StartupSecurityError('invalid native startup security descriptor')
            control, revision = _U16(), _U32()
            if not self._call(self._advapi32.GetSecurityDescriptorControl, output.value,
                              ctypes.byref(control), ctypes.byref(revision)):
                raise StartupSecurityError('startup security descriptor control query failed')
            if revision.value != 1 or not control.value & _SELF_RELATIVE:
                raise StartupSecurityError('unsupported native startup security descriptor')
            length = self._call(self._advapi32.GetSecurityDescriptorLength, output.value)
            if type(length) is not int or not _MIN_BYTES <= length <= _MAX_BYTES:
                raise StartupSecurityError('invalid startup security descriptor length')
            raw = self._call(ctypes.string_at, output.value, length)
            snapshot = parse_startup_security(raw)
            if raw[0] != revision.value or snapshot.control != control.value:
                raise StartupSecurityError('inconsistent startup security descriptor receipt')
        except BaseException as original:
            self._release(output, original)
            raise
        # Cleanup is outside the body exception handler. A return-side interrupt
        # after a successful free cannot route back into a second free attempt.
        self._release(output)
        return raw
