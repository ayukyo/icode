"""Internal current-process primary-token identity capture.

Single actor only: capture calls must not overlap. No access or launch authority.
"""
import ctypes
import os

from .windows_startup_security import StartupSecurityError, _sid


_U32 = ctypes.c_uint32
_I32 = ctypes.c_int32
_VOID = ctypes.c_void_p
_INVALID = _VOID(-1).value
_TOKEN_QUERY = 0x8
_TOKEN_USER = 1
_ERROR_INSUFFICIENT_BUFFER = 122
_MAX_BYTES = 4096  # Internal capture budget, not a Windows universal maximum.
_CLEANUP_NOTE = 'Startup host identity cleanup unconfirmed'


class _TokenUser(ctypes.Structure):
    _fields_ = [('Sid', _VOID), ('Attributes', _U32)]


_MIN_BYTES = ctypes.sizeof(_TokenUser) + 8


class WindowsStartupHostIdentity:
    """Capture the current process primary token user, then close its token."""

    def __init__(self):
        if os.name != 'nt':
            raise StartupSecurityError('native Windows startup host identity unavailable')
        self.cleanup_unconfirmed = False
        try:
            self._kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            self._advapi32 = ctypes.WinDLL('advapi32', use_last_error=True)
            signatures = [
                (self._kernel32.GetCurrentProcess, [], _VOID),
                (self._advapi32.OpenProcessToken, [_VOID, _U32, ctypes.POINTER(_VOID)], _I32),
                (self._advapi32.GetTokenInformation,
                 [_VOID, _I32, _VOID, _U32, ctypes.POINTER(_U32)], _I32),
                (self._kernel32.CloseHandle, [_VOID], _I32),
            ]
            for function, arguments, result in signatures:
                function.argtypes, function.restype = arguments, result
        except Exception:
            raise StartupSecurityError('native Windows startup host identity API unavailable') from None

    def _release(self, output, original=None):
        if not output.value or output.value == _INVALID:
            return
        # A failed call can already have closed the token. Never retry its old
        # numeric value; only a nonzero BOOL confirms the ownership receipt.
        self.cleanup_unconfirmed = True
        try:
            try:
                result = self._kernel32.CloseHandle(output.value)
            except Exception:
                raise StartupSecurityError(_CLEANUP_NOTE) from None
            if type(result) is not int or result == 0:
                raise StartupSecurityError(_CLEANUP_NOTE)
            self.cleanup_unconfirmed = False
        except BaseException:
            if original is None:
                raise
            try:
                BaseException.add_note(original, _CLEANUP_NOTE)
            except BaseException:
                pass

    def capture(self) -> str:
        """Return owned canonical SID text only after confirmed token cleanup."""
        if self.cleanup_unconfirmed:
            raise StartupSecurityError(_CLEANUP_NOTE)
        output = _VOID()
        try:
            # Acquisition itself is protected: the API can write output before
            # returning false or raising, including KeyboardInterrupt/SystemExit.
            process = self._kernel32.GetCurrentProcess()
            opened = self._advapi32.OpenProcessToken(process, _TOKEN_QUERY, ctypes.byref(output))
            if not opened or not output.value or output.value == _INVALID:
                raise StartupSecurityError('startup host token query failed')
            required = _U32()
            sized = self._advapi32.GetTokenInformation(
                output.value, _TOKEN_USER, None, 0, ctypes.byref(required))
            error = ctypes.get_last_error()
            if (sized or error != _ERROR_INSUFFICIENT_BUFFER
                    or not _MIN_BYTES <= required.value <= _MAX_BYTES):
                raise StartupSecurityError('invalid startup host token size receipt')
            capacity = required.value
            buffer = ctypes.create_string_buffer(capacity)
            returned = _U32()
            queried = self._advapi32.GetTokenInformation(
                output.value, _TOKEN_USER, buffer, capacity, ctypes.byref(returned))
            if not queried or not _MIN_BYTES <= returned.value <= capacity:
                raise StartupSecurityError('invalid startup host token data receipt')
            # Copy only the successful returned window. The embedded pointer is
            # interpreted as an offset into this allocation, never dereferenced.
            raw = buffer.raw[:returned.value]
            header = _TokenUser.from_buffer_copy(raw)
            pointer = header.Sid
            if pointer is None:
                raise StartupSecurityError('invalid startup host token SID range')
            offset = pointer - ctypes.addressof(buffer)
            if offset < ctypes.sizeof(_TokenUser) or offset + 8 > returned.value:
                raise StartupSecurityError('invalid startup host token SID range')
            sid, _ = _sid(raw, offset, returned.value)
        except BaseException as original:
            if isinstance(original, Exception) and not isinstance(original, StartupSecurityError):
                safe = StartupSecurityError('startup host identity capture failed')
                self._release(output, safe)
                raise safe from None
            self._release(output, original)
            raise
        # Outside the body handler: a tested return-side interrupt must not
        # route a successfully closed token into a second CloseHandle attempt.
        self._release(output)
        return sid
