"""Read-only test support for comparing WFP ctypes layouts with the SDK.

This module is intentionally under ``tests``. It does not subscribe to WFP,
load a WFP DLL, or change any host network-event setting.
"""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile

_VS_DEVCMD_SETUP_FAILED_EXIT_CODE = 91
_VISUAL_CPP_COMPILER_UNAVAILABLE_EXIT_CODE = 92


class _Guid(ctypes.Structure):
    _fields_ = [
        ("data1", ctypes.c_uint32),
        ("data2", ctypes.c_uint16),
        ("data3", ctypes.c_uint16),
        ("data4", ctypes.c_ubyte * 8),
    ]


class _FileTime(ctypes.Structure):
    _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_uint32)]


class _FwpByteArray16(ctypes.Structure):
    _fields_ = [("bytes", ctypes.c_ubyte * 16)]


class _AddressUnion(ctypes.Union):
    _fields_ = [
        ("ipv4", ctypes.c_uint32),
        ("ipv6", _FwpByteArray16),
    ]


class _FwpByteBlob(ctypes.Structure):
    _fields_ = [("size", ctypes.c_uint32), ("data", ctypes.c_void_p)]


class _FwpmNetEventSubscription0(ctypes.Structure):
    _fields_ = [
        ("enum_template", ctypes.c_void_p),
        ("flags", ctypes.c_uint32),
        ("session_key", _Guid),
    ]


class _FwpmNetEventHeader3(ctypes.Structure):
    _fields_ = [
        ("time_stamp", _FileTime),
        ("flags", ctypes.c_uint32),
        ("ip_version", ctypes.c_uint32),
        ("ip_protocol", ctypes.c_uint8),
        ("local_address", _AddressUnion),
        ("remote_address", _AddressUnion),
        ("local_port", ctypes.c_uint16),
        ("remote_port", ctypes.c_uint16),
        ("scope_id", ctypes.c_uint32),
        ("app_id", _FwpByteBlob),
        ("user_id", ctypes.c_void_p),
        ("address_family", ctypes.c_uint32),
        ("package_sid", ctypes.c_void_p),
        ("enterprise_id", ctypes.c_void_p),
        ("policy_flags", ctypes.c_uint64),
        ("effective_name", _FwpByteBlob),
    ]


class _FwpmNetEventPayload(ctypes.Union):
    _fields_ = [
        ("ike_mm_failure", ctypes.c_void_p),
        ("ike_qm_failure", ctypes.c_void_p),
        ("ike_em_failure", ctypes.c_void_p),
        ("classify_drop", ctypes.c_void_p),
        ("ipsec_drop", ctypes.c_void_p),
        ("idp_drop", ctypes.c_void_p),
        ("classify_allow", ctypes.c_void_p),
        ("capability_drop", ctypes.c_void_p),
        ("capability_allow", ctypes.c_void_p),
        ("classify_drop_mac", ctypes.c_void_p),
    ]


class _FwpmNetEvent3(ctypes.Structure):
    _fields_ = [
        ("header", _FwpmNetEventHeader3),
        ("event_type", ctypes.c_uint32),
        ("payload", _FwpmNetEventPayload),
    ]


class _FwpmNetEventCapabilityDrop0(ctypes.Structure):
    _fields_ = [
        ("network_capability_id", ctypes.c_uint32),
        ("filter_id", ctypes.c_uint64),
        ("is_loopback", ctypes.c_int32),
    ]


def _classify_windows_sdk_compile_failure(compiler_output: str, return_code: int) -> str:
    """Return a bounded reason token without exposing SDK or runner output."""
    if return_code == _VS_DEVCMD_SETUP_FAILED_EXIT_CODE:
        return "visual_studio_environment_setup_failed"
    if return_code == _VISUAL_CPP_COMPILER_UNAVAILABLE_EXIT_CODE:
        return "compiler_unavailable_after_setup"
    normalized = compiler_output.casefold()
    if "is not recognized as an internal or external command" in normalized:
        return "compiler_unavailable"
    if "cannot find the path specified" in normalized:
        return "visual_studio_command_unavailable"
    if "fatal error c1083" in normalized and any(
        header in normalized for header in ("fwpmu.h", "windows.h")
    ):
        return "windows_sdk_header_unavailable"
    if "error c" in normalized or "fatal error c" in normalized:
        return "sdk_declaration_compile_error"
    if return_code != 0:
        return "compiler_failed_without_diagnostic"
    return "compiler_output_missing"


def _build_visual_studio_batch_script(
    dev_command: str,
    target_arch: str,
    host_arch: str,
) -> str:
    """Keep VS environment setup and compiler invocation in one cmd process."""
    return "\n".join(
        (
            "@echo off",
            f'call "{dev_command}" -arch={target_arch} -host_arch={host_arch} >NUL 2>NUL',
            f"if errorlevel 1 exit /b {_VS_DEVCMD_SETUP_FAILED_EXIT_CODE}",
            "where.exe cl >NUL 2>NUL",
            f"if errorlevel 1 exit /b {_VISUAL_CPP_COMPILER_UNAVAILABLE_EXIT_CODE}",
            "cl /nologo /W0 /Fewfp_sdk_layout_probe.exe wfp_sdk_layout_probe.c",
            "exit /b %errorlevel%",
            "",
        ),
    )


def _visual_studio_architectures(runner_arch: str, machine: str) -> tuple[str, str]:
    """Map runner names to supported VsDevCmd target/host architecture names."""
    runner = runner_arch.strip().casefold()
    host_machine = machine.strip().casefold()
    arm_runner = runner == "arm64" or host_machine in {"arm64", "aarch64"}
    x64_runner = runner in {"x64", "amd64"} or host_machine in {"amd64", "x86_64"}

    if arm_runner and not x64_runner:
        if runner in {"", "arm64"} and host_machine in {"", "arm64", "aarch64"}:
            # VsDevCmd documents amd64 as a host architecture for arm64 targets.
            return "arm64", "amd64"
    elif x64_runner and not arm_runner:
        if runner in {"", "x64", "amd64"} and host_machine in {"", "amd64", "x86_64"}:
            # The VsDevCmd spelling for a 64-bit x86 target is amd64, not x64.
            return "amd64", "amd64"
    raise RuntimeError("unsupported_windows_runner_architecture")


def ctypes_layout_snapshot() -> dict[str, int]:
    """Return only the sizes and offsets required by the future event parser."""
    return {
        "subscription.size": ctypes.sizeof(_FwpmNetEventSubscription0),
        "subscription.enum_template": _FwpmNetEventSubscription0.enum_template.offset,
        "subscription.flags": _FwpmNetEventSubscription0.flags.offset,
        "subscription.session_key": _FwpmNetEventSubscription0.session_key.offset,
        "header.size": ctypes.sizeof(_FwpmNetEventHeader3),
        "header.flags": _FwpmNetEventHeader3.flags.offset,
        "header.ip_version": _FwpmNetEventHeader3.ip_version.offset,
        "header.ip_protocol": _FwpmNetEventHeader3.ip_protocol.offset,
        "header.local_address": _FwpmNetEventHeader3.local_address.offset,
        "header.remote_address": _FwpmNetEventHeader3.remote_address.offset,
        "header.local_port": _FwpmNetEventHeader3.local_port.offset,
        "header.remote_port": _FwpmNetEventHeader3.remote_port.offset,
        "header.scope_id": _FwpmNetEventHeader3.scope_id.offset,
        "header.app_id": _FwpmNetEventHeader3.app_id.offset,
        "header.user_id": _FwpmNetEventHeader3.user_id.offset,
        "header.address_family": _FwpmNetEventHeader3.address_family.offset,
        "header.package_sid": _FwpmNetEventHeader3.package_sid.offset,
        "header.enterprise_id": _FwpmNetEventHeader3.enterprise_id.offset,
        "header.policy_flags": _FwpmNetEventHeader3.policy_flags.offset,
        "header.effective_name": _FwpmNetEventHeader3.effective_name.offset,
        "event.size": ctypes.sizeof(_FwpmNetEvent3),
        "event.type": _FwpmNetEvent3.event_type.offset,
        "event.capability_drop": _FwpmNetEvent3.payload.offset,
        "capability_drop.size": ctypes.sizeof(_FwpmNetEventCapabilityDrop0),
        "capability_drop.network_capability_id": (
            _FwpmNetEventCapabilityDrop0.network_capability_id.offset
        ),
        "capability_drop.filter_id": _FwpmNetEventCapabilityDrop0.filter_id.offset,
        "capability_drop.is_loopback": _FwpmNetEventCapabilityDrop0.is_loopback.offset,
    }


def run_windows_sdk_layout_probe() -> dict[str, int]:
    """Compile and run the tiny SDK-header probe on native 64-bit Windows."""
    if os.name != "nt" or ctypes.sizeof(ctypes.c_void_p) != 8:
        raise RuntimeError("unsupported_windows_abi_target")

    program_files_x86 = os.environ.get("ProgramFiles(x86)")
    if not program_files_x86:
        raise RuntimeError("visual_studio_locator_unavailable")
    vswhere = Path(program_files_x86) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    if not vswhere.is_file():
        raise RuntimeError("visual_studio_locator_unavailable")
    try:
        location = subprocess.run(
            [str(vswhere), "-latest", "-products", "*", "-property", "installationPath"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("visual_studio_discovery_failed") from None
    install_path_text = location.stdout.strip()
    if location.returncode != 0 or not install_path_text:
        raise RuntimeError("visual_studio_discovery_failed")
    dev_command = Path(install_path_text) / "Common7" / "Tools" / "VsDevCmd.bat"
    if not dev_command.is_file():
        raise RuntimeError("visual_studio_developer_command_unavailable")

    visual_studio_target_arch, visual_studio_host_arch = _visual_studio_architectures(
        os.environ.get("RUNNER_ARCH", ""),
        platform.machine(),
    )

    source = Path(__file__).resolve().parent / "fixtures" / "native" / "wfp_sdk_layout_probe.c"
    if not source.is_file():
        raise RuntimeError("windows_sdk_probe_source_unavailable")
    with tempfile.TemporaryDirectory(prefix="icode-wfp-sdk-abi-") as raw_directory:
        executable = Path(raw_directory) / "wfp_sdk_layout_probe.exe"
        source_copy = Path(raw_directory) / "wfp_sdk_layout_probe.c"
        batch_script = Path(raw_directory) / "wfp_sdk_layout_probe.cmd"
        try:
            shutil.copyfile(source, source_copy)
            batch_script.write_text(
                _build_visual_studio_batch_script(
                    str(dev_command),
                    visual_studio_target_arch,
                    visual_studio_host_arch,
                ),
                encoding="utf-8",
            )
        except OSError:
            raise RuntimeError("windows_sdk_probe_batch_creation_failed") from None
        try:
            compile_result = subprocess.run(
                ["cmd.exe", "/d", "/c", batch_script.name],
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=raw_directory,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise RuntimeError("windows_sdk_probe_compile_failed") from None
        if compile_result.returncode != 0 or not executable.is_file():
            output = "\n".join((compile_result.stdout, compile_result.stderr))
            failure_kind = _classify_windows_sdk_compile_failure(
                output,
                compile_result.returncode,
            )
            raise RuntimeError(
                f"windows_sdk_probe_compile_failed:{failure_kind}:"
                f"exit={compile_result.returncode}"
            )
        try:
            execution = subprocess.run(
                [str(executable)],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise RuntimeError("windows_sdk_probe_execution_failed") from None
        if execution.returncode != 0:
            raise RuntimeError("windows_sdk_probe_execution_failed")

    result: dict[str, int] = {}
    for line in execution.stdout.splitlines():
        key, separator, raw_value = line.partition("=")
        if not separator or key in result:
            raise RuntimeError("windows_sdk_probe_output_invalid")
        try:
            result[key] = int(raw_value, 10)
        except ValueError:
            raise RuntimeError("windows_sdk_probe_output_invalid") from None
    if result.keys() != ctypes_layout_snapshot().keys():
        raise RuntimeError("windows_sdk_probe_output_invalid")
    return result
