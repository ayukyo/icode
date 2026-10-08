"""CI compatibility canary; not a file lock or executable launch grant."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import sysconfig

_PATH_CAPACITY = 32768
_IMAGE_LIMIT = 64 * 1024 * 1024
_WIRE_LIMIT = 512
_TIMEOUT = 30


def _nt_to_globalroot(path: str) -> str:
    if type(path) is not str:
        raise ValueError("invalid_volume_path")
    match = re.fullmatch(r"\\Device\\HarddiskVolume[0-9]+\\(.+)", path, re.IGNORECASE)
    if match is None:
        raise ValueError("invalid_volume_path")
    for part in match.group(1).split("\\"):
        if (not part or part in (".", "..") or part.endswith((".", " "))
                or any(ord(char) < 32 or char in ':<>"|?*/' for char in part)):
            raise ValueError("invalid_volume_path")
    return "\\\\?\\GLOBALROOT" + path


def _kernel():
    # Windows DWORD/BOOL remain 32-bit even on a 64-bit host. HANDLE is
    # pointer-width; the three signatures must not use ctypes' int default.
    dword = ctypes.c_uint32
    handle = ctypes.c_void_p
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, dword, dword,
        ctypes.c_void_p, dword, dword, handle]
    kernel.CreateFileW.restype = handle
    kernel.GetFinalPathNameByHandleW.argtypes = [handle,
        ctypes.POINTER(ctypes.c_wchar), dword, dword]
    kernel.GetFinalPathNameByHandleW.restype = dword
    kernel.CloseHandle.argtypes = [handle]
    kernel.CloseHandle.restype = ctypes.c_int32
    return kernel


def direct_volume_path(path: Path, *, directory: bool = False) -> str:
    if sys.platform != "win32" or type(directory) is not bool:
        raise ValueError("windows_probe_only")
    kernel = _kernel()
    flags = 0x02000000 if directory else 0
    handle = kernel.CreateFileW(str(path), 0x80, 7, None, 3, flags, None)
    if type(handle) is not int or handle in (0, -1, 0xffffffff, ctypes.c_void_p(-1).value):
        raise OSError("volume_path_open_failed")
    try:
        buffer = ctypes.create_unicode_buffer(_PATH_CAPACITY)
        length = kernel.GetFinalPathNameByHandleW(handle, buffer, len(buffer), 2)
        if type(length) is not int or not 0 < length < len(buffer):
            raise OSError("volume_path_query_failed")
        value = buffer.value
        # The API reports UTF-16 code units, not Python Unicode code points.
        if len(value.encode("utf-16-le", errors="strict")) // 2 != length:
            raise OSError("volume_path_query_incomplete")
        return _nt_to_globalroot(value)
    finally:
        if not kernel.CloseHandle(handle):
            raise OSError("volume_path_close_failed")


def _installed_resources():
    import icode
    from icode.native_helper import windows_arch_from_platform
    package = Path(icode.__file__).resolve().parent
    package.relative_to(Path(sysconfig.get_paths()["purelib"]).resolve())
    arch = windows_arch_from_platform(sysconfig.get_platform())
    native = package / "native"
    helper = native / f"icode-sandbox-windows-{arch}.exe"
    verifier = native / f"icode-provenance-windows-{arch}.exe"
    proof = Path(str(helper) + ".sigstore.json")
    return arch, native, helper, verifier, proof


def probe(source_sha: str) -> None:
    if (sys.platform != "win32" or type(source_sha) is not str
            or re.fullmatch(r"[0-9a-f]{40}", source_sha) is None):
        raise ValueError("invalid_probe_input")
    from icode.runner import _run_unittest_with_bounded_output
    from icode.native_helper import windows_pe_architecture
    arch, native, helper, verifier, proof = _installed_resources()
    info = helper.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or not 0 < info.st_size <= _IMAGE_LIMIT):
        raise ValueError("invalid_installed_artifact")
    with helper.open("rb") as stream:
        image = stream.read(_IMAGE_LIMIT + 1)
    if len(image) != info.st_size or windows_pe_architecture(image) != arch:
        raise ValueError("invalid_installed_artifact")
    executable = direct_volume_path(verifier)
    artifact = direct_volume_path(helper)
    bundle = direct_volume_path(proof)
    cwd = Path(direct_volume_path(native, directory=True))
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR") if key in os.environ}
    argv = [executable, "--artifact", artifact, "--bundle", bundle,
            "--source-sha", source_sha, "--arch", arch]
    expected = dict(schema_version=1, provenance_verified=True, launch_authorized=False,
        artifact_sha256=hashlib.sha256(image).hexdigest(), source_sha=source_sha, architecture=arch)
    # Compare the existing canonical Go wire, rejecting duplicate/extra fields,
    # bool/int aliases, decoding replacement and any trailing data together.
    expected_wire = json.dumps(expected, separators=(",", ":")).encode("ascii") + b"\n"
    result = _run_unittest_with_bounded_output(argv, workspace=cwd, timeout=_TIMEOUT,
        output_limit_bytes=_WIRE_LIMIT, environment=env)
    if (type(result) is not tuple or len(result) != 3
            or type(result[0]) is not int or result[0] != 0
            or type(result[1]) is not bytes or type(result[2]) is not bytes
            or result[1] != expected_wire or result[2] != b""):
        raise ValueError("direct_volume_positive_failed")
    wrong_source = "0" * 40 if source_sha != "0" * 40 else "1" * 40
    negative_argv = list(argv)
    negative_argv[6] = wrong_source
    result = _run_unittest_with_bounded_output(negative_argv, workspace=cwd, timeout=_TIMEOUT,
        output_limit_bytes=_WIRE_LIMIT, environment=env)
    if (type(result) is not tuple or len(result) != 3
            or type(result[0]) is not int or result[0] != 78
            or type(result[1]) is not bytes or type(result[2]) is not bytes
            or result[1] != b"" or result[2] != b"icode_provenance: verification_failed\n"):
        raise ValueError("direct_volume_negative_failed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args()
    try:
        probe(args.source_sha)
    except (ImportError, OSError, UnicodeError, ValueError, RuntimeError, subprocess.SubprocessError):
        print("::error::windows_direct_volume_probe_failed")
        return 1
    print("windows-direct-volume compatibility=PASS launch_authorized=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
