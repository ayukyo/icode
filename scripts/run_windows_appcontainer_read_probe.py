#!/usr/bin/env python3
"""Run the Windows-only, non-production AppContainer read-handle POC."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
import platform
import shutil
import socket
import sys
import tempfile
from ctypes import wintypes

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from icode.windows_job import _READ_HANDLE_PLACEHOLDER  # noqa: E402
from icode.windows_appcontainer import run_windows_appcontainer  # noqa: E402


_DACL_SECURITY_INFORMATION = 0x00000004
_ERROR_INSUFFICIENT_BUFFER = 122
_EXPECTED_SOURCE_CONTENTS = b"ICODE-READ-HANDLE-PROBE-v1\n"


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(64 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _dacl_digest(path: Path) -> str:
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    advapi.GetFileSecurityW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi.GetFileSecurityW.restype = wintypes.BOOL
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
    return hashlib.sha256(descriptor.raw[:required.value]).hexdigest()


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
            shutil.copyfile(probe_executable, helper)
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
            dacl_digests_before = {
                path: _dacl_digest(path)
                for path in (*protected_directories, *protected_files, workspace)
            }
            workspace_dacl_before = dacl_digests_before[workspace]

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
            dacl_digests_after = {
                path: _dacl_digest(path)
                for path in (*protected_directories, *protected_files, workspace)
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
                    dacl_digests_before[path] == dacl_digests_after[path]
                    for path in (*protected_directories, *protected_files)
                ),
                "workspace_dacl_restored": (
                    workspace_dacl_before == dacl_digests_after[workspace]
                ),
                "no_write_marker": not marker.exists(),
            }
            print(
                "windows_appcontainer_read_handle_probe "
                f"architecture={platform.machine()} "
                f"error={result.error or 'none'} "
                f"checks={sum(value is True for value in checks.values())}/{len(checks)}"
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
