#!/usr/bin/env python3
"""Run the Windows-only, non-production AppContainer read-handle POC."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import platform
import re
import shutil
import socket
import stat
import sys
import tempfile
from ctypes import wintypes

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from icode.windows_job import _READ_HANDLE_PLACEHOLDER  # noqa: E402
from icode.windows_appcontainer import run_windows_appcontainer  # noqa: E402


_DACL_SECURITY_INFORMATION = 0x00000004
_SE_FILE_OBJECT = 1
_INHERITED_ACE = 0x10
_SE_DACL_AUTO_INHERITED = 0x0400
_SE_DACL_PROTECTED = 0x1000
_FILE_ATTRIBUTE_REPARSE_POINT = 0x0400
_ERROR_INSUFFICIENT_BUFFER = 122
_EXPECTED_SOURCE_CONTENTS = b"ICODE-READ-HANDLE-PROBE-v1\n"
_DISPOSABLE_WORKSPACE_PREFIX = "icode-appcontainer-read-handle-"
_SID_PATTERN = re.compile(r"(?i)(?<![A-Z0-9])S-\d+(?:-\d+)+(?![A-Z0-9])")


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(64 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class _DaclSnapshot:
    descriptor_digest: str
    acl_digest: str
    acl_bytes: bytes
    acl_capacity_bytes: bytes
    normalized_acl_digest: str
    control: int
    revision: int
    present: bool
    defaulted: bool
    file_identity: tuple[int, int]
    ace_count: int
    inherited_ace_count: int
    acl_bytes_in_use: int


def _format_network_error(value: object) -> str:
    """Expose only a bounded numeric Winsock code in CI diagnostics."""
    if type(value) is int and 0 <= value <= 0xFFFF:
        return str(value)
    return "unknown"


def _normalize_inherited_ace_flag(ace: bytes) -> bytes:
    """Clear only the ACE-origin marker, retaining access and inheritance flags."""
    if len(ace) < 4 or int.from_bytes(ace[2:4], "little") != len(ace):
        raise ValueError("ACE header length is invalid")
    normalized = bytearray(ace)
    normalized[1] &= ~_INHERITED_ACE
    return bytes(normalized)


def _workspace_dacl_entries_equivalent(
    before: _DaclSnapshot, after: _DaclSnapshot,
) -> bool:
    """Allow only Windows' auto-inheritance control/origin markers to differ."""
    control_delta = before.control ^ after.control
    auto_inherited_transition = (
        control_delta == _SE_DACL_AUTO_INHERITED
        and not before.control & _SE_DACL_AUTO_INHERITED
        and bool(after.control & _SE_DACL_AUTO_INHERITED)
    )
    return (
        before.normalized_acl_digest == after.normalized_acl_digest
        and (control_delta == 0 or auto_inherited_transition)
        and before.revision == after.revision
        and before.present == after.present
        and before.defaulted == after.defaulted
        and before.file_identity == after.file_identity
        and before.acl_bytes_in_use == after.acl_bytes_in_use
    )


def _workspace_dacl_baseline_normalization_valid(
    before: _DaclSnapshot, after: _DaclSnapshot,
) -> bool:
    """Require only the one-way auto-inheritance normalization on one object."""
    control_delta = before.control ^ after.control
    return (
        control_delta == _SE_DACL_AUTO_INHERITED
        and not before.control & _SE_DACL_AUTO_INHERITED
        and bool(after.control & _SE_DACL_AUTO_INHERITED)
        and not before.control & _SE_DACL_PROTECTED
        and not after.control & _SE_DACL_PROTECTED
        and before.normalized_acl_digest == after.normalized_acl_digest
        and before.revision == after.revision
        and before.present is True
        and after.present is True
        and before.defaulted is False
        and after.defaulted is False
        and before.file_identity == after.file_identity
        and before.ace_count == after.ace_count
        and before.acl_bytes_in_use == after.acl_bytes_in_use
    )


def _dacl_state_equal(before: _DaclSnapshot, after: _DaclSnapshot) -> bool:
    """Compare the complete DACL state without relying on SD serialization offsets."""
    return (
        before.acl_bytes == after.acl_bytes
        and before.control == after.control
        and before.revision == after.revision
        and before.present == after.present
        and before.defaulted == after.defaulted
        and before.file_identity == after.file_identity
        and before.ace_count == after.ace_count
        and before.acl_bytes_in_use == after.acl_bytes_in_use
    )


def _stat_is_reparse_point(file_info: os.stat_result) -> bool:
    """Detect symlinks and Windows junction/reparse attributes without following them."""
    return stat.S_ISLNK(file_info.st_mode) or bool(
        getattr(file_info, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT
    )


def _dacl_snapshot(path: Path) -> _DaclSnapshot:
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    advapi.GetFileSecurityW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi.GetFileSecurityW.restype = wintypes.BOOL
    advapi.GetSecurityDescriptorDacl.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.BOOL),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.BOOL),
    ]
    advapi.GetSecurityDescriptorDacl.restype = wintypes.BOOL
    advapi.GetSecurityDescriptorControl.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(wintypes.WORD), ctypes.POINTER(wintypes.DWORD),
    ]
    advapi.GetSecurityDescriptorControl.restype = wintypes.BOOL

    class ACL_SIZE_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("AceCount", wintypes.DWORD),
            ("AclBytesInUse", wintypes.DWORD),
            ("AclBytesFree", wintypes.DWORD),
        ]

    advapi.GetAclInformation.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.c_int,
    ]
    advapi.GetAclInformation.restype = wintypes.BOOL
    advapi.GetAce.argtypes = [
        ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi.GetAce.restype = wintypes.BOOL
    required = wintypes.DWORD()
    ctypes.set_last_error(0)
    first_ok = bool(advapi.GetFileSecurityW(
        str(path), _DACL_SECURITY_INFORMATION, None, 0, ctypes.byref(required),
    ))
    first_error = ctypes.get_last_error()
    if first_ok or first_error != _ERROR_INSUFFICIENT_BUFFER or required.value <= 0:
        raise OSError(first_error, "GetFileSecurityW(size)")
    descriptor = ctypes.create_string_buffer(required.value)
    if not advapi.GetFileSecurityW(
        str(path), _DACL_SECURITY_INFORMATION, descriptor,
        required.value, ctypes.byref(required),
    ):
        raise OSError(ctypes.get_last_error(), "GetFileSecurityW")
    present = wintypes.BOOL()
    dacl = ctypes.c_void_p()
    defaulted = wintypes.BOOL()
    if not advapi.GetSecurityDescriptorDacl(
        descriptor, ctypes.byref(present), ctypes.byref(dacl), ctypes.byref(defaulted),
    ):
        raise OSError(ctypes.get_last_error(), "GetSecurityDescriptorDacl")
    control = wintypes.WORD()
    revision = wintypes.DWORD()
    if not advapi.GetSecurityDescriptorControl(
        descriptor, ctypes.byref(control), ctypes.byref(revision),
    ):
        raise OSError(ctypes.get_last_error(), "GetSecurityDescriptorControl")
    if not present.value or not dacl.value:
        raise OSError("DACL is absent or null")
    size_info = ACL_SIZE_INFORMATION()
    if not advapi.GetAclInformation(
        dacl, ctypes.byref(size_info), ctypes.sizeof(size_info), 2,
    ):
        raise OSError(ctypes.get_last_error(), "GetAclInformation")
    acl_bytes_in_use = int(size_info.AclBytesInUse)
    if acl_bytes_in_use < 8:
        raise OSError("DACL length is invalid")
    descriptor_start = ctypes.addressof(descriptor)
    descriptor_end = descriptor_start + int(required.value)
    dacl_start = int(dacl.value)
    acl_capacity = acl_bytes_in_use + int(size_info.AclBytesFree)
    if (
        dacl_start < descriptor_start
        or dacl_start + acl_capacity > descriptor_end
        or acl_bytes_in_use > acl_capacity
    ):
        raise OSError("DACL range is outside its security descriptor")
    acl_capacity_bytes = ctypes.string_at(dacl, acl_capacity)
    if int.from_bytes(acl_capacity_bytes[2:4], "little") != acl_capacity:
        raise OSError("DACL size does not match its allocated range")
    acl_bytes = acl_capacity_bytes[:acl_bytes_in_use]
    normalized_acl = bytearray(acl_bytes)
    file_info = path.lstat()
    inherited_ace_count = 0
    for ace_index in range(int(size_info.AceCount)):
        ace_pointer = ctypes.c_void_p()
        if not advapi.GetAce(dacl, ace_index, ctypes.byref(ace_pointer)) or not ace_pointer.value:
            raise OSError(ctypes.get_last_error(), "GetAce")
        ace_start = int(ace_pointer.value)
        ace_offset = ace_start - dacl_start
        if ace_offset < 8 or ace_offset + 4 > acl_bytes_in_use:
            raise OSError("ACE header is outside its DACL")
        ace_header = ctypes.string_at(ace_pointer, 4)
        ace_flags = ace_header[1]
        ace_size = int.from_bytes(ace_header[2:4], "little")
        if ace_offset < 8 or ace_size < 4 or ace_offset + ace_size > acl_bytes_in_use:
            raise OSError("ACE range is outside its DACL")
        ace = ctypes.string_at(ace_pointer, ace_size)
        normalized_acl[ace_offset:ace_offset + ace_size] = _normalize_inherited_ace_flag(ace)
        if ace_flags & _INHERITED_ACE:
            inherited_ace_count += 1
    return _DaclSnapshot(
        descriptor_digest=hashlib.sha256(
            descriptor.raw[:required.value],
        ).hexdigest(),
        acl_digest=hashlib.sha256(acl_bytes).hexdigest(),
        acl_bytes=acl_bytes,
        acl_capacity_bytes=acl_capacity_bytes,
        normalized_acl_digest=hashlib.sha256(normalized_acl).hexdigest(),
        control=int(control.value),
        revision=int(revision.value),
        present=bool(present.value),
        defaulted=bool(defaulted.value),
        file_identity=(int(file_info.st_dev), int(file_info.st_ino)),
        ace_count=int(size_info.AceCount),
        inherited_ace_count=inherited_ace_count,
        acl_bytes_in_use=acl_bytes_in_use,
    )


def _normalize_disposable_workspace_dacl_baseline(workspace: Path) -> int:
    """Normalize only an empty CI workspace before capturing its DACL baseline."""
    try:
        temp_root = Path(tempfile.gettempdir()).resolve(strict=True)
        raw_workspace = Path(os.path.abspath(os.fspath(workspace)))
        raw_root = raw_workspace.parent
        if _stat_is_reparse_point(raw_root.lstat()) or _stat_is_reparse_point(
            raw_workspace.lstat(),
        ):
            raise OSError("workspace path contains a reparse point")
        root = raw_root.resolve(strict=True)
        target = raw_workspace.resolve(strict=True)
        if (
            target.name != "execution"
            or target.parent != root
            or not root.name.startswith(_DISPOSABLE_WORKSPACE_PREFIX)
            or not root.is_relative_to(temp_root)
            or root == temp_root
            or not target.is_dir()
            or next(target.iterdir(), None) is not None
        ):
            raise OSError("workspace is not an empty disposable execution directory")
        before = _dacl_snapshot(target)
        if (
            not before.present
            or before.defaulted
            or before.control & _SE_DACL_PROTECTED
        ):
            raise OSError("workspace DACL cannot be normalized safely")
        if before.control & _SE_DACL_AUTO_INHERITED:
            return 0

        advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        advapi.SetNamedSecurityInfoW.argtypes = [
            wintypes.LPWSTR, ctypes.c_int, wintypes.DWORD,
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
        ]
        advapi.SetNamedSecurityInfoW.restype = wintypes.DWORD
        original_acl = ctypes.create_string_buffer(before.acl_capacity_bytes)
        status = advapi.SetNamedSecurityInfoW(
            str(target), _SE_FILE_OBJECT, _DACL_SECURITY_INFORMATION,
            None, None, ctypes.cast(original_acl, ctypes.c_void_p), None,
        )
        if status != 0:
            raise OSError(int(status), "SetNamedSecurityInfoW")
        after = _dacl_snapshot(target)
        if not _workspace_dacl_baseline_normalization_valid(before, after):
            raise OSError("workspace DACL baseline changed outside normalization contract")
        return after.control ^ before.control
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise OSError("disposable workspace DACL normalization failed") from exc


@contextmanager
def _open_read_handle(path: Path) -> Iterator[int]:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.CreateFileW(
        str(path), 0x80000000, 0x00000001 | 0x00000002 | 0x00000004,
        None, 3, 0x00000080, None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if not handle or handle == invalid_handle:
        raise OSError(ctypes.get_last_error(), "CreateFileW(read fixture)")
    try:
        yield int(handle)
    finally:
        kernel.CloseHandle(handle)


def _host_listener_is_live(listener: socket.socket) -> bool:
    try:
        with socket.create_connection(listener.getsockname(), timeout=3):
            accepted, _ = listener.accept()
            accepted.close()
        return True
    except OSError:
        return False


def _safe_diagnostics(detail: str) -> str:
    """Keep only path-free key/value diagnostics from the native wrapper."""
    safe_parts = [
        part for part in detail.split("; ")
        if 0 < len(part) <= 160
        and not _SID_PATTERN.search(part)
        and all(character.isalnum() or character in "._=-" for character in part)
    ]
    return ",".join(safe_parts)[:1024] or "none"


def _run(probe_executable: Path) -> int:
    if sys.platform != "win32":
        print("windows_platform=false")
        return 2
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUNNER_OS") != "Windows":
        print("github_windows_runner=false")
        return 2
    try:
        probe_executable = probe_executable.resolve(strict=True)
    except OSError:
        print("probe_executable_available=false")
        return 2
    if not probe_executable.is_file() or probe_executable.name.casefold() != (
        "icode-appcontainer-read-probe.exe"
    ):
        print("probe_executable_contract=false")
        return 2

    try:
        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-read-handle-") as raw:
            root = Path(raw)
            workspace = root / "execution"
            protected = root / "protected-source"
            outside = root / "outside"
            synthetic_profile = root / "synthetic-user-profile"
            workspace.mkdir()
            protected.mkdir()
            outside.mkdir()
            synthetic_profile.mkdir()

            helper = workspace / probe_executable.name
            source = protected / "approved.bin"
            sibling = protected / "sibling.bin"
            outside_file = outside / "outside.bin"
            profile_file = synthetic_profile / "profile-sentinel.bin"
            marker = protected / "must-not-be-created.bin"
            report = workspace / "probe-receipt.json"
            source.write_bytes(_EXPECTED_SOURCE_CONTENTS)
            sibling.write_bytes(b"sibling must stay hidden\n")
            outside_file.write_bytes(b"outside must stay hidden\n")
            profile_file.write_bytes(b"synthetic profile must stay hidden\n")

            protected_files = (source, sibling, outside_file, profile_file)
            protected_directories = (root, protected, outside, synthetic_profile)
            file_digests_before = {path: _file_digest(path) for path in protected_files}
            protected_dacl_paths = (*protected_directories, *protected_files)
            protected_dacls_before_normalization = {
                path: _dacl_snapshot(path) for path in protected_dacl_paths
            }
            workspace_dacl_normalization_delta = (
                _normalize_disposable_workspace_dacl_baseline(workspace)
            )
            protected_dacls_after_normalization = {
                path: _dacl_snapshot(path) for path in protected_dacl_paths
            }
            if not all(
                _dacl_state_equal(
                    protected_dacls_before_normalization[path],
                    protected_dacls_after_normalization[path],
                )
                for path in protected_dacl_paths
            ):
                raise OSError("workspace DACL normalization changed protected sample state")

            shutil.copyfile(probe_executable, helper)
            dacl_snapshots_before = {
                path: _dacl_snapshot(path)
                for path in (*protected_dacl_paths, workspace, helper)
            }
            workspace_dacl_before = dacl_snapshots_before[workspace]
            workspace_helper_dacl_before = dacl_snapshots_before[helper]

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
                listener.bind(("127.0.0.1", 0))
                listener.listen(2)
                listener.settimeout(3)
                if not _host_listener_is_live(listener):
                    print("host_listener_control=false")
                    return 1
                network_port = listener.getsockname()[1]

                with _open_read_handle(source) as read_handle:
                    argv = [
                        str(helper),
                        "--input-handle", _READ_HANDLE_PLACEHOLDER,
                        "--source-path", str(source),
                        "--sibling-path", str(sibling),
                        "--outside-path", str(outside_file),
                        "--profile-path", str(profile_file),
                        "--marker-path", str(marker),
                        "--report-path", str(report),
                        "--network-address", "127.0.0.1",
                        "--network-port", str(network_port),
                    ]
                    prior_opt_in = os.environ.get("ICODE_DIAGNOSTIC_READ_HANDLE")
                    os.environ["ICODE_DIAGNOSTIC_READ_HANDLE"] = "true"
                    try:
                        result = run_windows_appcontainer(
                            argv,
                            cwd=workspace,
                            timeout_seconds=12,
                            process_limit=2,
                            _diagnostic_read_handle=read_handle,
                        )
                    finally:
                        if prior_opt_in is None:
                            os.environ.pop("ICODE_DIAGNOSTIC_READ_HANDLE", None)
                        else:
                            os.environ["ICODE_DIAGNOSTIC_READ_HANDLE"] = prior_opt_in

                unexpected_network_client = False
                listener.settimeout(0.25)
                try:
                    accepted, _ = listener.accept()
                except TimeoutError:
                    pass
                except OSError:
                    unexpected_network_client = True
                else:
                    unexpected_network_client = True
                    accepted.close()

            if not report.is_file():
                receipt: dict[str, object] = {}
            else:
                try:
                    decoded_receipt = json.loads(report.read_text(encoding="ascii"))
                    receipt = (
                        decoded_receipt if isinstance(decoded_receipt, dict) else {}
                    )
                except (OSError, UnicodeError, json.JSONDecodeError):
                    receipt = {}

            file_digests_after = {path: _file_digest(path) for path in protected_files}
            dacl_snapshots_after = {
                path: _dacl_snapshot(path)
                for path in (*protected_dacl_paths, workspace, helper)
            }
            checks = {
                "process_executed": result.executed,
                "process_exit_zero": result.exit_code == 0,
                "job_cleanup_verified": result.cleanup_ok,
                "appcontainer_token": receipt.get("token_is_appcontainer") is True,
                "approved_handle_read": receipt.get("handle_read_ok") is True,
                "approved_handle_write_denied": receipt.get("handle_write_denied") is True,
                "source_path_denied": receipt.get("source_path_denied") is True,
                "sibling_path_denied": receipt.get("sibling_path_denied") is True,
                "outside_path_denied": receipt.get("outside_path_denied") is True,
                "profile_path_denied": receipt.get("profile_path_denied") is True,
                "marker_create_denied": receipt.get("marker_create_denied") is True,
                "network_denied": (
                    receipt.get("network_denied") is True
                    and receipt.get("network_error") == 10013
                ),
                "host_listener_control": True,
                "no_network_connection": not unexpected_network_client,
                "protected_content_unchanged": file_digests_before == file_digests_after,
                "protected_dacls_unchanged": all(
                    _dacl_state_equal(
                        dacl_snapshots_before[path], dacl_snapshots_after[path],
                    )
                    for path in protected_dacl_paths
                ),
                "workspace_dacl_restored": _dacl_state_equal(
                    workspace_dacl_before, dacl_snapshots_after[workspace],
                ),
                "workspace_helper_dacl_restored": _dacl_state_equal(
                    workspace_helper_dacl_before, dacl_snapshots_after[helper],
                ),
                "no_write_marker": not marker.exists(),
                "native_receipt_finalized": receipt.get("stage") == 5,
            }
            print(
                "windows_appcontainer_read_handle_probe "
                f"architecture={platform.machine()} "
                f"error={result.error or 'none'} "
                f"native_stage={receipt.get('stage', 0)} "
                f"diagnostics={_safe_diagnostics(result.detail)} "
                f"checks={sum(value is True for value in checks.values())}/{len(checks)}"
            )
            workspace_dacl_after = dacl_snapshots_after[workspace]
            print(
                "  native_network_receipt="
                f"denied:{receipt.get('network_denied') is True},"
                f"error:{_format_network_error(receipt.get('network_error'))}"
            )
            print(
                "  workspace_dacl_baseline="
                f"normalization_delta:0x{workspace_dacl_normalization_delta:04x}"
            )
            print(
                "  workspace_dacl_diagnostics="
                f"descriptor_blob_equal:{workspace_dacl_before.descriptor_digest == workspace_dacl_after.descriptor_digest},"
                f"acl_equal:{workspace_dacl_before.acl_digest == workspace_dacl_after.acl_digest},"
                f"dacl_state_equal:{_dacl_state_equal(workspace_dacl_before, workspace_dacl_after)},"
                "entries_equivalent:"
                f"{_workspace_dacl_entries_equivalent(workspace_dacl_before, workspace_dacl_after)},"
                f"control_before:0x{workspace_dacl_before.control:04x},"
                f"control_after:0x{workspace_dacl_after.control:04x},"
                f"ace_count:{workspace_dacl_before.ace_count}/{workspace_dacl_after.ace_count},"
                f"inherited_aces:{workspace_dacl_before.inherited_ace_count}/{workspace_dacl_after.inherited_ace_count},"
                f"acl_bytes:{workspace_dacl_before.acl_bytes_in_use}/{workspace_dacl_after.acl_bytes_in_use},"
                f"present:{workspace_dacl_before.present}/{workspace_dacl_after.present},"
                f"defaulted:{workspace_dacl_before.defaulted}/{workspace_dacl_after.defaulted}"
            )
            for name, passed in checks.items():
                print(f"  {name}={'pass' if passed else 'fail'}")
            return 0 if all(checks.values()) else 1
    except Exception as exc:  # noqa: BLE001 - keep runner output path-free and bounded
        print(f"windows_appcontainer_read_handle_probe error={type(exc).__name__}")
        return 1


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: run_windows_appcontainer_read_probe.py <probe-exe>")
        return 2
    return _run(Path(sys.argv[1]))


if __name__ == "__main__":
    raise SystemExit(main())
