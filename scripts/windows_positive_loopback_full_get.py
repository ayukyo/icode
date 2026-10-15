"""Bounded complete Get worker. Its output is private evidence, never a notice."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import sys


class SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", ctypes.c_uint32)]


def _bind(library, name, result, arguments):
    function = getattr(library, name)
    function.restype = result
    function.argtypes = arguments
    return function


def _load():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    _bind(kernel, "FreeLibrary", wintypes.BOOL, [wintypes.HMODULE])
    system_directory = _bind(kernel, "GetSystemDirectoryW", wintypes.UINT,
                             [wintypes.LPWSTR, wintypes.UINT])
    buffer = ctypes.create_unicode_buffer(32768)
    length = system_directory(buffer, len(buffer))
    if not 0 < length < len(buffer):
        raise OSError("system_directory")
    system = Path(buffer.value)
    if not system.is_absolute() or system.name.casefold() != "system32":
        raise OSError("system_directory")
    advapi = ctypes.WinDLL(str(system / "advapi32.dll"), use_last_error=True, winmode=0x800)
    library = ctypes.WinDLL(str(system / "FirewallAPI.dll"), use_last_error=True, winmode=0x800)
    try:
        _bind(kernel, "GetProcessHeap", ctypes.c_void_p, [])
        _bind(kernel, "HeapFree", wintypes.BOOL,
              [ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p])
        _bind(advapi, "IsValidSid", wintypes.BOOL, [ctypes.c_void_p])
        _bind(advapi, "GetLengthSid", wintypes.DWORD, [ctypes.c_void_p])
        query = _bind(library, "NetworkIsolationGetAppContainerConfig", wintypes.DWORD,
                      [ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(ctypes.c_void_p)])
    except BaseException as primary:
        try:
            if not kernel.FreeLibrary(library._handle):
                raise OSError("free_library")
        except BaseException as error:
            primary.add_note(f"cleanup_unknown: {error!r}")
        raise
    return kernel, advapi, library, query


def _text_sid(value):
    if (type(value) is not bytes or len(value) < 12 or value[0] != 1
            or not 1 <= value[1] <= 15 or len(value) != 8 + 4 * value[1]):
        raise ValueError("invalid_sid")
    authority = int.from_bytes(value[2:8], "big")
    parts = [int.from_bytes(value[index:index + 4], "little")
             for index in range(8, len(value), 4)]
    return "S-1-" + str(authority) + "-" + "-".join(map(str, parts))


def collect():
    result = dict(schema=1, entries=[], api_code=None, complete=False,
                  sid_attempted=0, sid_freed=0, array_freed=False,
                  library_freed=False, process_reaped=None)
    kernel = advapi = library = query = None
    count = wintypes.DWORD()
    array = ctypes.c_void_p()
    pointers = []
    graph_safe = False
    valid = False
    try:
        kernel, advapi, library, query = _load()
        result["api_code"] = int(query(ctypes.byref(count), ctypes.byref(array)))
        if result["api_code"] != 0 or count.value > 4096 or (count.value and not array.value):
            raise ValueError("query_incomplete")
        if count.value:
            entries = ctypes.cast(array, ctypes.POINTER(SID_AND_ATTRIBUTES))
            for index in range(count.value):
                pointer = entries[index].Sid
                if not pointer or pointer == array.value or pointer in pointers:
                    raise ValueError("unsafe_ownership_graph")
                pointers.append(pointer)
                if not advapi.IsValidSid(pointer):
                    raise ValueError("invalid_sid")
            # Only a complete, nonaliased ownership graph may be individually
            # freed. Invalid pointers may crash this worker; parent treats that
            # as incomplete and never consumes a partial snapshot.
        graph_safe = True
        identities = set()
        for index, pointer in enumerate(pointers):
            length = int(advapi.GetLengthSid(pointer))
            if not 12 <= length <= 68:
                raise ValueError("invalid_sid_length")
            binary = ctypes.string_at(pointer, length)
            text = _text_sid(binary)
            if binary in identities:
                raise ValueError("duplicate_sid")
            identities.add(binary)
            attributes = int(entries[index].Attributes)
            result["entries"].append([text, attributes])
        valid = True
    except Exception:
        valid = False
    finally:
        # One failed HeapFree must not skip any other proven owned pointer.
        if graph_safe:
            try:
                heap = kernel.GetProcessHeap()
            except BaseException:
                heap = None
            if heap:
                for pointer in pointers:
                    result["sid_attempted"] += 1
                    try:
                        if kernel.HeapFree(heap, 0, pointer):
                            result["sid_freed"] += 1
                    except BaseException:
                        valid = False
                try:
                    result["array_freed"] = not array.value or bool(kernel.HeapFree(heap, 0, array))
                except BaseException:
                    valid = False
        if library is not None:
            try:
                result["library_freed"] = bool(kernel.FreeLibrary(library._handle))
            except BaseException:
                valid = False
        result["complete"] = bool(valid and graph_safe and result["array_freed"]
            and result["library_freed"] and result["sid_attempted"] == count.value
            and result["sid_freed"] == count.value and len(result["entries"]) == count.value)
    return result


def main():
    if sys.platform != "win32" or sys.argv[1:] != ["--full-get"]:
        return 2
    result = collect()
    wire = json.dumps(result, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")
    if len(wire) > 1048576:
        return 3
    sys.stdout.buffer.write(wire + b"\n")
    sys.stdout.buffer.flush()
    return 0 if result["complete"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
