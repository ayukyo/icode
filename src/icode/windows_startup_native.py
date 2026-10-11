"""Private Win32 startup pin transport; never a launch authorization."""
import os
import re
import ctypes
from .windows_startup_pin import StartupPinError, StartupFileMetadata

# Win32 widths are explicit: host c_long/c_wchar differ on portable test hosts.
_U32 = ctypes.c_uint32
_I64 = ctypes.c_int64
_HANDLE = ctypes.c_void_p
_U16 = ctypes.c_uint16
_VOID = ctypes.c_void_p
_MAX_READ = 64 * 1024
_DOS_UNITS = 32768
_INVALID = ctypes.c_void_p(-1).value
_FILE_READ_DATA_OR_LIST_DIRECTORY = 0x1
_FILE_READ_ATTRIBUTES = 0x80
_READ_CONTROL = 0x20000
_SYNCHRONIZE = 0x100000
_FILE_SHARE_READ = 0x1
_FILE_OPEN = 0x1
_FILE_DIRECTORY_FILE = 0x1
_FILE_NON_DIRECTORY_FILE = 0x40
_FILE_SYNCHRONOUS_IO_NONALERT = 0x20
_FILE_OPEN_REPARSE_POINT = 0x200000
_OBJ_CASE_INSENSITIVE = 0x40
_OBJ_DONT_REPARSE = 0x1000
_FILE_ATTRIBUTE_DIRECTORY = 0x10
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400
_FILE_TYPE_DISK = 0x1
_FILE_BEGIN = 0


class _FILE_BASIC_INFO(ctypes.Structure):
    _fields_ = [(name, _I64) for name in
                ('CreationTime', 'LastAccessTime', 'LastWriteTime', 'ChangeTime')] + [('FileAttributes', _U32)]


class _FILE_STANDARD_INFO(ctypes.Structure):
    _fields_ = [('AllocationSize', _I64), ('EndOfFile', _I64),
                ('NumberOfLinks', _U32), ('DeletePending', ctypes.c_ubyte),
                ('Directory', ctypes.c_ubyte)]


class _FILE_ATTRIBUTE_TAG_INFO(ctypes.Structure):
    _fields_ = [('FileAttributes', _U32), ('ReparseTag', _U32)]


class _FILE_ID_INFO(ctypes.Structure):
    _fields_ = [('VolumeSerialNumber', ctypes.c_uint64), ('FileId', ctypes.c_ubyte * 16)]


class _UNICODE_STRING(ctypes.Structure):
    _fields_ = [('Length', _U16), ('MaximumLength', _U16), ('Buffer', _VOID)]


class _OBJECT_ATTRIBUTES(ctypes.Structure):
    _fields_ = [('Length', _U32), ('RootDirectory', _HANDLE),
                ('ObjectName', ctypes.POINTER(_UNICODE_STRING)), ('Attributes', _U32),
                ('SecurityDescriptor', _VOID), ('SecurityQualityOfService', _VOID)]


class _IO_STATUS_UNION(ctypes.Union):
    _fields_ = [('Status', ctypes.c_int32), ('Pointer', _VOID)]


class _IO_STATUS_BLOCK(ctypes.Structure):
    _fields_ = [('u', _IO_STATUS_UNION), ('Information', ctypes.c_size_t)]


_INFO_CLASSES = {0: _FILE_BASIC_INFO, 1: _FILE_STANDARD_INFO,
                 9: _FILE_ATTRIBUTE_TAG_INFO, 18: _FILE_ID_INFO}


class WindowsStartupPinBackend:
    """Single actor: serialize all HANDLE use against close/open.

    Ownership must remain exclusive from _require through each native read;
    numeric registration alone does not provide thread-safe lifetime locking.
    """

    def __init__(self):
        if os.name != 'nt':
            raise StartupPinError('native Windows startup pin backend unavailable')
        self._active: dict[int, bool] = {}
        self._retired: set[int] = set()
        self._unknown: set[int] = set()
        try:
            self._kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            self._ntdll = ctypes.WinDLL('ntdll')
            self._configure_apis()
        except Exception:
            raise StartupPinError('native Windows startup API unavailable') from None

    def _configure_apis(self):
        signatures = {
            'QueryDosDeviceW': ([ctypes.c_wchar_p, ctypes.POINTER(_U16), _U32], _U32),
            'GetFileType': ([_HANDLE], _U32),
            'GetFileInformationByHandleEx': ([_HANDLE, ctypes.c_int32, _VOID, _U32], ctypes.c_int32),
            'SetFilePointerEx': ([_HANDLE, _I64, ctypes.POINTER(_I64), _U32], ctypes.c_int32),
            'ReadFile': ([_HANDLE, _VOID, _U32, ctypes.POINTER(_U32), _VOID], ctypes.c_int32),
            'CloseHandle': ([_HANDLE], ctypes.c_int32),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(self._kernel32, name)
            function.argtypes, function.restype = arguments, result
        function = self._ntdll.NtCreateFile
        function.argtypes = [ctypes.POINTER(_HANDLE), _U32,
                             ctypes.POINTER(_OBJECT_ATTRIBUTES), ctypes.POINTER(_IO_STATUS_BLOCK),
                             _VOID, _U32, _U32, _U32, _U32, _VOID, _U32]
        function.restype = ctypes.c_int32

    def _require(self, handle, directory=None):
        if (type(handle) is not int or handle not in self._active
                or (directory is not None and self._active[handle] != directory)):
            raise StartupPinError('invalid or unavailable startup HANDLE')
        return handle

    def _cleanup_new(self, handle):
        # Only an unregistered, valid output can belong to this failed open.
        # A collision must never close an existing owner's numeric HANDLE.
        if (type(handle) is int and 0 < handle < _INVALID
                and handle not in self._active and handle not in self._unknown):
            self._retired.add(handle)
            self._close_native(handle)

    def _call(self, function, *arguments):
        try:
            return function(*arguments)
        except Exception:
            raise StartupPinError('startup native API invocation failed') from None

    def _close_native(self, handle):
        try:
            if not self._call(self._kernel32.CloseHandle, handle):
                raise StartupPinError('startup HANDLE close unconfirmed')
        except BaseException:
            self._unknown.add(handle)
            raise

    def _open(self, parent, name, directory):
        encoded = name.encode('utf-16-le', 'strict')
        if len(encoded) > 65532:
            raise StartupPinError('invalid startup native object name length')
        buffer = ctypes.create_string_buffer(encoded + b'\0\0')
        string = _UNICODE_STRING(len(encoded), len(encoded) + 2, ctypes.addressof(buffer))
        attributes = _OBJECT_ATTRIBUTES(ctypes.sizeof(_OBJECT_ATTRIBUTES), parent,
                                       ctypes.pointer(string),
                                       _OBJ_DONT_REPARSE | _OBJ_CASE_INSENSITIVE, None, None)
        output = _HANDLE()
        ios = _IO_STATUS_BLOCK()
        # READ_DATA/LIST_DIRECTORY actually participates in the share boundary;
        # READ_ATTRIBUTES alone would not block a conflicting writer.
        access = (_FILE_READ_DATA_OR_LIST_DIRECTORY | _FILE_READ_ATTRIBUTES
                  | _READ_CONTROL | _SYNCHRONIZE)
        options = (_FILE_SYNCHRONOUS_IO_NONALERT | _FILE_OPEN_REPARSE_POINT
                   | (_FILE_DIRECTORY_FILE if directory else _FILE_NON_DIRECTORY_FILE))
        owned = False
        try:
            status = self._call(self._ntdll.NtCreateFile, ctypes.byref(output), access,
                                ctypes.byref(attributes), ctypes.byref(ios), None,
                                0, _FILE_SHARE_READ, _FILE_OPEN, options, None, 0)
            handle = output.value
            if (status != 0 or type(handle) is not int or not 0 < handle < _INVALID
                    or handle in self._active or handle in self._retired or handle in self._unknown):
                raise StartupPinError('startup native HANDLE open failed')
            # Claim only this acquisition, never an old active/unknown collision.
            # Keep registration and return inside the cleanup boundary as well.
            owned = True
            self._active[handle] = directory
            return handle
        except BaseException as original:
            try:
                if owned:
                    self._active.pop(handle, None)
                self._cleanup_new(output.value)
            except BaseException:
                # Notes are best effort: even an overridden __notes__ accessor
                # must not replace the original KeyboardInterrupt/SystemExit.
                try:
                    BaseException.add_note(original, 'Startup acquired HANDLE cleanup unconfirmed')
                except BaseException:
                    pass
            raise

    def open_root(self, drive: str) -> int:
        if type(drive) is not str or re.fullmatch('[A-Za-z]:', drive) is None:
            raise StartupPinError('invalid startup drive')
        buffer = (_U16 * _DOS_UNITS)()
        length = self._call(self._kernel32.QueryDosDeviceW, drive, buffer, _DOS_UNITS)
        if type(length) is not int or not 2 <= length <= _DOS_UNITS:
            raise StartupPinError('startup drive mapping query failed')
        raw = bytes(buffer)[:length * 2]
        try:
            mapping = raw.decode('utf-16-le', 'strict')
        except UnicodeError:
            raise StartupPinError('invalid startup drive mapping') from None
        if not mapping.endswith('\0\0') or '\0' not in mapping[:-1]:
            raise StartupPinError('invalid startup drive mapping')
        entries = mapping[:-2].split('\0')
        if not entries or any(not entry for entry in entries):
            raise StartupPinError('invalid startup drive mapping')
        # QueryDosDevice returns the current mapping first, with optional stale
        # historical mappings afterward. Only the first mapping binds this open.
        current = entries[0]
        if re.fullmatch(r'\\Device\\HarddiskVolume[0-9]+', current) is None:
            raise StartupPinError('unsupported startup volume mapping')
        return self._open(None, current + '\\', True)

    def open_child(self, parent: int, name: str, *, directory: bool) -> int:
        self._require(parent, True)
        if type(directory) is not bool or type(name) is not str:
            raise StartupPinError('invalid startup child parameters')
        try:
            encoded = name.encode('utf-16-le', 'strict')
        except UnicodeError:
            raise StartupPinError('invalid startup child component') from None
        if (not encoded or len(encoded) > 510 or name in ('.', '..')
                or name.endswith((' ', '.'))
                or any(ord(c) < 32 or c in '<>:"/\\|?*' for c in name)):
            raise StartupPinError('invalid startup child component')
        stem = name.split('.', 1)[0].rstrip(' ').upper()
        if (stem in {'CON', 'PRN', 'AUX', 'NUL', 'CONIN$', 'CONOUT$', 'CLOCK$'}
                or re.fullmatch(r'(?:COM|LPT)[1-9¹²³]', stem)):
            raise StartupPinError('invalid startup child component')
        return self._open(parent, name, directory)

    def query(self, handle: int) -> StartupFileMetadata:
        self._require(handle)
        if self._call(self._kernel32.GetFileType, handle) != _FILE_TYPE_DISK:
            raise StartupPinError('startup HANDLE is not disk')
        values = {}
        for kind, structure in _INFO_CLASSES.items():
            value = structure()
            if not self._call(self._kernel32.GetFileInformationByHandleEx,
                    handle, kind, ctypes.byref(value), ctypes.sizeof(value)):
                raise StartupPinError('startup HANDLE metadata query failed')
            values[kind] = value
        basic, standard, tag, identity = (values[k] for k in (0, 1, 9, 18))
        if (basic.FileAttributes != tag.FileAttributes or standard.EndOfFile < 0
                or standard.Directory not in (0, 1) or standard.DeletePending not in (0, 1)
                or bool(standard.Directory) != self._active[handle]
                or bool(basic.FileAttributes & _FILE_ATTRIBUTE_DIRECTORY) != bool(standard.Directory)
                or bool(tag.ReparseTag) != bool(tag.FileAttributes & _FILE_ATTRIBUTE_REPARSE_POINT)):
            raise StartupPinError('inconsistent startup HANDLE metadata')
        return StartupFileMetadata(identity.VolumeSerialNumber, bytes(identity.FileId),
                                   bool(standard.Directory),
                                   bool(tag.FileAttributes & _FILE_ATTRIBUTE_REPARSE_POINT),
                                   bool(standard.DeletePending), 'disk', standard.NumberOfLinks,
                                   standard.EndOfFile, basic.ChangeTime)

    def query_security(self, handle: int) -> bytes:
        """Read this active object's descriptor without changing HANDLE ownership."""
        self._require(handle)
        if not hasattr(self, '_security_reader'):
            try:
                from .windows_startup_security_native import WindowsStartupSecurityReader
                self._security_reader = WindowsStartupSecurityReader()
            except Exception:
                raise StartupPinError('native Windows startup security reader unavailable') from None
        return self._security_reader.read(handle)

    def read(self, handle: int, offset: int, count: int) -> bytes:
        self._require(handle, False)
        if (type(offset) is not int or not 0 <= offset < 2**63
                or type(count) is not int or not 0 <= count <= _MAX_READ
                or offset + count >= 2**63):
            raise StartupPinError('invalid startup HANDLE read bounds')
        position = _I64()
        if (not self._call(self._kernel32.SetFilePointerEx, handle, offset,
                          ctypes.byref(position), _FILE_BEGIN)
                or position.value != offset):
            raise StartupPinError('startup HANDLE seek failed')
        buffer = ctypes.create_string_buffer(count)
        actual = _U32()
        if not self._call(self._kernel32.ReadFile, handle, buffer, count, ctypes.byref(actual), None):
            raise StartupPinError('startup HANDLE read failed')
        if actual.value > count:
            raise StartupPinError('invalid startup HANDLE read length')
        return buffer.raw[:actual.value]

    def close(self, handle: int) -> None:
        self._require(handle)
        del self._active[handle]
        self._retired.add(handle)
        self._close_native(handle)
