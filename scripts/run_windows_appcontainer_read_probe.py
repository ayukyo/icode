#!/usr/bin/env python3
"""Run the Windows-only, non-production AppContainer read-handle POC."""

from __future__ import annotations

import ctypes
import hashlib
import ipaddress
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
import subprocess
import sys
import tempfile
import time
import uuid
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
_ERROR_SUCCESS = 0
_NETISO_ERROR_TYPE_PRIVATE_NETWORK = 1
_WSAE_CONNECTION_REFUSED = 10061
_WSAE_TIMED_OUT = 10060
_NETWORK_ISOLATION_FAILURE_CODES = frozenset({10013, 10060})
_WFP_NETWORK_CAPABILITY_LABELS = {
    0: "internet_client",
    1: "internet_client_server",
    2: "private_network",
}
_RFC1918_NETWORKS = (
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.168.0.0/16"),
)
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
    explicit_aces: tuple[bytes, ...] = ()
    inherited_aces: tuple[bytes, ...] = ()


def _format_network_error(value: object) -> str:
    """Expose only a bounded numeric Winsock code in CI diagnostics."""
    if type(value) is int and 0 <= value <= 0xFFFF:
        return str(value)
    return "unknown"


def _is_rfc1918_ipv4(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        address = ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError:
        return False
    return any(address in network for network in _RFC1918_NETWORKS)


def _select_private_network_probe_address(probe_executable: Path) -> str:
    """Choose a configured RFC1918 address through read-only Win32 enumeration."""

    try:
        result = subprocess.run(
            [str(probe_executable), "--select-private-network-target"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        raise OSError("private_network_probe_address_unavailable") from None

    selected_lines = result.stdout.splitlines() if isinstance(result.stdout, str) else []
    if result.returncode != 0 or len(selected_lines) != 1:
        raise OSError("private_network_probe_address_unavailable")
    local_address = selected_lines[0]
    if not _is_rfc1918_ipv4(local_address):
        raise OSError("private_network_probe_address_unavailable")
    return local_address


def _network_isolation_denial_verified(
    receipt: object,
    *,
    network_target_is_private: bool,
    host_listener_control: bool,
    no_network_connection: bool,
) -> bool:
    """Require a native missing-capability diagnosis and a failed live-listener probe."""
    if not isinstance(receipt, dict):
        return False
    network_error = receipt.get("network_error")
    isolation_status = receipt.get("network_isolation_status")
    isolation_error = receipt.get("network_isolation_error_type")
    if (
        receipt.get("token_is_appcontainer") is not True
        or receipt.get("network_connect_attempted") is not True
        or receipt.get("network_connected") is not False
        or receipt.get("network_isolation_diagnostic_ok") is not True
        or type(isolation_status) is not int
        or isolation_status != _ERROR_SUCCESS
        or type(network_error) is not int
        or network_error not in _NETWORK_ISOLATION_FAILURE_CODES
        or type(isolation_error) is not int
        or isolation_error != _NETISO_ERROR_TYPE_PRIVATE_NETWORK
        or network_target_is_private is not True
        or host_listener_control is not True
        or no_network_connection is not True
    ):
        return False
    return True


def _classify_listener_port_comparison(
    receipt: object,
    *,
    live_listener_control: bool,
    control_port_reserved: bool,
) -> str:
    """Narrow the result only against a same-address closed-port control."""
    if (
        not isinstance(receipt, dict)
        or live_listener_control is not True
        or control_port_reserved is not True
        or receipt.get("network_connect_attempted") is not True
        or receipt.get("network_connected") is not False
        or receipt.get("network_control_connect_attempted") is not True
        or receipt.get("network_control_connected") is not False
    ):
        return "inconclusive"

    live_error = receipt.get("network_error")
    control_error = receipt.get("network_control_error")
    if (
        type(live_error) is int
        and live_error == _WSAE_TIMED_OUT
        and type(control_error) is int
        and control_error == _WSAE_CONNECTION_REFUSED
    ):
        return "listener_path_narrowed"
    return "inconclusive"


def _classify_wfp_target_drop_receipt(
    receipt: object, *, collector_exit_code: int | None,
) -> str:
    """Attribute only completed exact capability/classify-drop evidence."""
    if (
        type(collector_exit_code) is not int
        or collector_exit_code != 0
        or not isinstance(receipt, dict)
        or type(receipt.get("schema_version")) is not int
        or receipt.get("schema_version") != 5
        or receipt.get("subscription_ok") is not True
        or receipt.get("unsubscribe_ok") is not True
        or receipt.get("network_events_collected") is not True
    ):
        return "evidence_unavailable"
    count_fields = (
        "event_callback_count",
        "capability_drop_event_count",
        "classify_drop_event_count",
        "matched_capability_drop_count",
        "matched_classify_drop_count",
    )
    counts = {field: receipt.get(field) for field in count_fields}
    if any(
        type(value) is not int or not 0 <= value <= 0xFFFF
        for value in counts.values()
    ):
        return "evidence_unavailable"
    callback_count = counts["event_callback_count"]
    capability_event_count = counts["capability_drop_event_count"]
    classify_event_count = counts["classify_drop_event_count"]
    capability_count = counts["matched_capability_drop_count"]
    classify_count = counts["matched_classify_drop_count"]
    if (
        capability_event_count + classify_event_count > callback_count
        or capability_count > capability_event_count
        or classify_count > classify_event_count
    ):
        return "evidence_unavailable"
    capability_id = receipt.get("matched_network_capability_id")
    capability_id_consistent = receipt.get("network_capability_id_consistent")
    if (
        type(capability_id_consistent) is not bool
        or (
            capability_id is not None
            and (
                type(capability_id) is not int
                or capability_id not in _WFP_NETWORK_CAPABILITY_LABELS
            )
        )
    ):
        return "evidence_unavailable"
    if capability_count > 0:
        if capability_id_consistent is not True or type(capability_id) is not int:
            return "evidence_unavailable"
        capability_label = _WFP_NETWORK_CAPABILITY_LABELS[capability_id]
        return f"capability_drop_{capability_label}_attributed"
    if capability_id is not None or capability_id_consistent is not True:
        return "evidence_unavailable"
    if classify_count > 0:
        return "classify_drop_attributed"
    return "evidence_unavailable"


def _classify_wfp_ipv6_loopback_receipt(
    receipt: object, *, collector_exit_code: int | None,
) -> str:
    """Attribute only a complete, exact IPv6-loopback capability-drop receipt."""
    if (
        type(collector_exit_code) is not int
        or collector_exit_code != 0
        or not isinstance(receipt, dict)
        or type(receipt.get("schema_version")) is not int
        or receipt.get("schema_version") != 6
        or type(receipt.get("target_ip_version")) is not int
        or receipt.get("target_ip_version") != 6
        or receipt.get("target_is_loopback") is not True
        or receipt.get("subscription_ok") is not True
        or receipt.get("unsubscribe_ok") is not True
        or receipt.get("network_events_collected") is not True
    ):
        return "evidence_unavailable"

    count_fields = (
        "event_callback_count",
        "capability_drop_event_count",
        "classify_drop_event_count",
        "matched_capability_drop_count",
        "matched_classify_drop_count",
    )
    counts = {field: receipt.get(field) for field in count_fields}
    if any(
        type(value) is not int or not 0 <= value <= 0xFFFF
        for value in counts.values()
    ):
        return "evidence_unavailable"

    callback_count = counts["event_callback_count"]
    capability_count = counts["capability_drop_event_count"]
    classify_count = counts["classify_drop_event_count"]
    matched_capability_count = counts["matched_capability_drop_count"]
    if (
        callback_count == 0
        or capability_count != callback_count
        or classify_count != 0
        or matched_capability_count == 0
        or matched_capability_count > capability_count
        or counts["matched_classify_drop_count"] != 0
    ):
        return "evidence_unavailable"

    capability_id = receipt.get("matched_network_capability_id")
    if (
        type(receipt.get("network_capability_id_consistent")) is not bool
        or receipt.get("network_capability_id_consistent") is not True
        or type(capability_id) is not int
        or capability_id not in _WFP_NETWORK_CAPABILITY_LABELS
    ):
        return "evidence_unavailable"
    return "capability_drop_ipv6_loopback_attributed"


def _wfp_observer_diagnostic_summary(
    *,
    process_started: bool,
    paths: tuple[Path, Path, Path] | None,
    receipt: object,
    collector_exit_code: int | None,
) -> dict[str, object]:
    """Return fixed-schema observer state without disclosing paths or raw receipt data."""
    ready_state = "missing"
    if paths is not None:
        ready_path, _stop_path, _result_path = paths
        try:
            if ready_path.stat().st_size > 64:
                ready_state = "invalid"
            else:
                marker = ready_path.read_bytes()
                ready_state = {
                    b"ready\n": "ready",
                    b"unavailable\n": "unavailable",
                }.get(marker, "invalid")
        except OSError:
            ready_state = "missing"

    receipt_dict = receipt if isinstance(receipt, dict) else {}
    def bounded_count(key: str) -> int | None:
        value = receipt_dict.get(key)
        return value if type(value) is int and 0 <= value <= 0xFFFF else None

    capability_id = receipt_dict.get("matched_network_capability_id")
    capability_id_consistent = receipt_dict.get("network_capability_id_consistent")

    return {
        "started": process_started is True,
        "ready_state": ready_state,
        "collector_exit_code": (
            collector_exit_code if type(collector_exit_code) is int else None
        ),
        "subscription_ok": (
            receipt_dict.get("subscription_ok")
            if type(receipt_dict.get("subscription_ok")) is bool else None
        ),
        "unsubscribe_ok": (
            receipt_dict.get("unsubscribe_ok")
            if type(receipt_dict.get("unsubscribe_ok")) is bool else None
        ),
        "network_events_collected": (
            receipt_dict.get("network_events_collected")
            if type(receipt_dict.get("network_events_collected")) is bool else None
        ),
        "event_callback_count": bounded_count("event_callback_count"),
        "capability_drop_event_count": bounded_count("capability_drop_event_count"),
        "classify_drop_event_count": bounded_count("classify_drop_event_count"),
        "matched_capability_drop_count": bounded_count("matched_capability_drop_count"),
        "matched_classify_drop_count": bounded_count("matched_classify_drop_count"),
        "matched_network_capability_id": (
            capability_id
            if type(capability_id) is int
            and capability_id in _WFP_NETWORK_CAPABILITY_LABELS
            else None
        ),
        "network_capability_id_consistent": (
            capability_id_consistent
            if type(capability_id_consistent) is bool
            else None
        ),
    }


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
    return not _workspace_dacl_baseline_normalization_failure_codes(before, after)


def _workspace_dacl_baseline_normalization_failure_codes(
    before: _DaclSnapshot, after: _DaclSnapshot,
) -> tuple[str, ...]:
    """Return fixed, path-free labels for every violated normalization invariant."""
    failures: list[str] = []
    control_delta = before.control ^ after.control
    if not (
        control_delta == _SE_DACL_AUTO_INHERITED
        and not before.control & _SE_DACL_AUTO_INHERITED
        and bool(after.control & _SE_DACL_AUTO_INHERITED)
    ):
        failures.append("control")
    if before.control & _SE_DACL_PROTECTED or after.control & _SE_DACL_PROTECTED:
        failures.append("protected")
    if before.explicit_aces != after.explicit_aces:
        failures.append("explicit_aces")
    inherited_after = iter(after.inherited_aces)
    inherited_preserved = all(
        any(candidate == previous for candidate in inherited_after)
        for previous in before.inherited_aces
    )
    if not inherited_preserved:
        failures.append("inherited_aces")
    added_inherited: list[bytes] = []
    inherited_before_index = 0
    for ace in after.inherited_aces:
        if (
            inherited_before_index < len(before.inherited_aces)
            and ace == before.inherited_aces[inherited_before_index]
        ):
            inherited_before_index += 1
        else:
            added_inherited.append(ace)
    if inherited_preserved:
        if after.ace_count - before.ace_count != len(added_inherited):
            failures.append("ace_count")
        added_inherited_bytes = sum(len(ace) for ace in added_inherited)
        if after.acl_bytes_in_use - before.acl_bytes_in_use != added_inherited_bytes:
            failures.append("acl_length")
    if before.revision != after.revision:
        failures.append("revision")
    if before.present is not True or after.present is not True:
        failures.append("dacl_presence")
    if before.defaulted is not False or after.defaulted is not False:
        failures.append("dacl_defaulted")
    if before.file_identity != after.file_identity:
        failures.append("file_identity")
    return tuple(failures)


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
    explicit_aces: list[bytes] = []
    inherited_aces: list[bytes] = []
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
        normalized_ace = _normalize_inherited_ace_flag(ace)
        normalized_acl[ace_offset:ace_offset + ace_size] = normalized_ace
        if ace_flags & _INHERITED_ACE:
            inherited_ace_count += 1
            inherited_aces.append(normalized_ace)
        else:
            explicit_aces.append(ace)
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
        explicit_aces=tuple(explicit_aces),
        inherited_aces=tuple(inherited_aces),
    )


def _normalize_disposable_workspace_dacl_baseline(workspace: Path) -> int:
    """Normalize only an empty CI workspace before capturing its DACL baseline."""
    stage = "path_guard"
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
        stage = "before_snapshot"
        before = _dacl_snapshot(target)
        stage = "precondition_check"
        if (
            not before.present
            or before.defaulted
            or before.control & _SE_DACL_PROTECTED
        ):
            raise OSError("workspace DACL cannot be normalized safely")
        if before.control & _SE_DACL_AUTO_INHERITED:
            return 0

        stage = "set_dacl"
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
        stage = "after_snapshot"
        after = _dacl_snapshot(target)
        stage = "normalization_check"
        if not _workspace_dacl_baseline_normalization_valid(before, after):
            failures = _workspace_dacl_baseline_normalization_failure_codes(before, after)
            stage = f"normalization_check_{'_'.join(failures) or 'unknown'}"
            raise OSError("workspace DACL baseline changed outside normalization contract")
        return after.control ^ before.control
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        diagnostic = f"dacl_baseline_{stage}"
        for attribute, label in (("winerror", "win"), ("errno", "errno")):
            code = getattr(exc, attribute, None)
            if type(code) is int and 0 <= code <= 0xFFFF:
                diagnostic += f"_{label}_{code}"
                break
        raise OSError(diagnostic) from exc


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


def _start_wfp_event_probe(
    executable: Path,
    profile_name: str,
    remote_address: str,
    remote_port: int,
    root: Path,
) -> tuple[subprocess.Popen[bytes] | None, tuple[Path, Path, Path] | None]:
    """Start the bounded host-side observer; failure is diagnostic-only."""
    if (
        not isinstance(profile_name, str)
        or re.fullmatch(r"icode-[0-9a-f]{32}", profile_name) is None
    ):
        return None, None
    if (
        not _is_rfc1918_ipv4(remote_address)
        or type(remote_port) is not int
        or not 1 <= remote_port <= 65535
    ):
        return None, None
    canonical_address = str(ipaddress.IPv4Address(remote_address))
    token = profile_name[6:]
    ready_path = root / f"wfp-{token}.ready"
    stop_path = root / f"wfp-{token}.stop"
    result_path = root / f"wfp-{token}.json"
    try:
        process = subprocess.Popen(
            [
                str(executable), profile_name, canonical_address,
                str(remote_port),
                str(ready_path), str(stop_path), str(result_path),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        return None, None

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and not ready_path.is_file():
        if process.poll() is not None:
            break
        time.sleep(0.025)
    return process, (ready_path, stop_path, result_path)


def _start_wfp_ipv6_loopback_event_probe(
    executable: Path,
    profile_name: str,
    remote_port: int,
    root: Path,
) -> tuple[subprocess.Popen[bytes] | None, tuple[Path, Path, Path] | None]:
    """Start a test-only observer restricted to one AppContainer and ::1 TCP port."""
    if (
        not isinstance(profile_name, str)
        or re.fullmatch(r"icode-[0-9a-f]{32}", profile_name) is None
        or type(remote_port) is not int
        or not 1 <= remote_port <= 65535
    ):
        return None, None
    token = profile_name[6:]
    ready_path = root / f"wfp-{token}.ready"
    stop_path = root / f"wfp-{token}.stop"
    result_path = root / f"wfp-{token}.json"
    try:
        process = subprocess.Popen(
            [
                str(executable), "--collect-ipv6-loopback", profile_name,
                str(remote_port), str(ready_path), str(stop_path), str(result_path),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        return None, None

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and not ready_path.is_file():
        if process.poll() is not None:
            break
        time.sleep(0.025)
    return process, (ready_path, stop_path, result_path)


def _stop_wfp_event_probe(
    process: subprocess.Popen[bytes] | None,
    paths: tuple[Path, Path, Path] | None,
) -> tuple[dict[str, object] | None, int | None]:
    """Request unsubscribe, bound the wait, and parse only the tiny fixed receipt."""
    if process is None or paths is None:
        return None, None
    _ready_path, stop_path, result_path = paths
    try:
        stop_path.touch(exist_ok=True)
    except OSError:
        try:
            process.terminate()
        except OSError:
            pass
    try:
        exit_code = process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            process.terminate()
        except OSError:
            pass
        try:
            exit_code = process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except OSError:
                pass
            try:
                exit_code = process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                exit_code = None

    receipt: dict[str, object] | None = None
    try:
        if result_path.is_file() and result_path.stat().st_size <= 4096:
            decoded = json.loads(result_path.read_text(encoding="ascii"))
            if isinstance(decoded, dict):
                receipt = decoded
    except (OSError, UnicodeError, json.JSONDecodeError):
        receipt = None
    return receipt, exit_code


def _safe_diagnostics(detail: str) -> str:
    """Keep only path-free key/value diagnostics from the native wrapper."""
    safe_parts = [
        part for part in detail.split("; ")
        if 0 < len(part) <= 160
        and not _SID_PATTERN.search(part)
        and all(character.isalnum() or character in "._=-" for character in part)
    ]
    return ",".join(safe_parts)[:1024] or "none"


def _run(probe_executable: Path, wfp_probe_executable: Path) -> int:
    if sys.platform != "win32":
        print("windows_platform=false")
        return 2
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUNNER_OS") != "Windows":
        print("github_windows_runner=false")
        return 2
    try:
        probe_executable = probe_executable.resolve(strict=True)
        wfp_probe_executable = wfp_probe_executable.resolve(strict=True)
    except OSError:
        print("native_probe_executables_available=false")
        return 2
    if not probe_executable.is_file() or probe_executable.name.casefold() != (
        "icode-appcontainer-read-probe.exe"
    ) or not wfp_probe_executable.is_file() or wfp_probe_executable.name.casefold() != (
        "icode-wfp-event-probe.exe"
    ) or probe_executable.parent != wfp_probe_executable.parent:
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

            network_address = _select_private_network_probe_address(probe_executable)
            with (
                socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener,
                socket.socket(socket.AF_INET, socket.SOCK_STREAM) as control_socket,
            ):
                listener.bind((network_address, 0))
                listener.listen(2)
                listener.settimeout(3)
                control_socket.bind((network_address, 0))
                host_listener_control = _host_listener_is_live(listener)
                if not host_listener_control:
                    print("host_listener_control=false")
                    return 1
                network_port = listener.getsockname()[1]
                control_host, control_port = control_socket.getsockname()
                control_port_reserved = (
                    control_host == network_address
                    and type(control_port) is int
                    and 0 < control_port <= 65535
                    and control_port != network_port
                    and control_socket.getsockopt(
                        socket.SOL_SOCKET,
                        socket.SO_ACCEPTCONN,
                    ) == 0
                )
                if not control_port_reserved:
                    print("control_port_reserved=false")
                    return 1
                profile_name = f"icode-{uuid.uuid4().hex}"
                wfp_process, wfp_paths = None, None
                wfp_receipt: dict[str, object] | None = None
                wfp_exit_code: int | None = None

                try:
                    wfp_process, wfp_paths = _start_wfp_event_probe(
                        wfp_probe_executable,
                        profile_name,
                        network_address,
                        network_port,
                        root,
                    )
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
                            "--network-address", network_address,
                            "--network-port", str(network_port),
                            "--network-control-port", str(control_port),
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
                                _diagnostic_profile_name=profile_name,
                            )
                        finally:
                            if prior_opt_in is None:
                                os.environ.pop("ICODE_DIAGNOSTIC_READ_HANDLE", None)
                            else:
                                os.environ["ICODE_DIAGNOSTIC_READ_HANDLE"] = prior_opt_in
                finally:
                    wfp_receipt, wfp_exit_code = _stop_wfp_event_probe(
                        wfp_process, wfp_paths,
                    )

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
                no_network_connection = not unexpected_network_client

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

            listener_port_comparison = _classify_listener_port_comparison(
                receipt,
                live_listener_control=host_listener_control,
                control_port_reserved=control_port_reserved,
            )

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
                "network_isolation_denied": _network_isolation_denial_verified(
                    receipt,
                    network_target_is_private=_is_rfc1918_ipv4(network_address),
                    host_listener_control=host_listener_control,
                    no_network_connection=no_network_connection,
                ),
                "host_listener_control": host_listener_control,
                "no_network_connection": no_network_connection,
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
                f"connect_attempted:{receipt.get('network_connect_attempted') is True},"
                f"connected:{receipt.get('network_connected') is True},"
                f"winsock_error:{_format_network_error(receipt.get('network_error'))},"
                f"winsock_access_denied:{receipt.get('network_error') == 10013},"
                f"control_connect_attempted:{receipt.get('network_control_connect_attempted') is True},"
                f"control_connected:{receipt.get('network_control_connected') is True},"
                "control_winsock_error:"
                f"{_format_network_error(receipt.get('network_control_error'))},"
                f"listener_port_comparison:{listener_port_comparison},"
                f"target_is_rfc1918:{_is_rfc1918_ipv4(network_address)},"
                f"isolation_diagnostic_ok:{receipt.get('network_isolation_diagnostic_ok') is True},"
                f"isolation_status:{_format_network_error(receipt.get('network_isolation_status'))},"
                f"isolation_error_type:{_format_network_error(receipt.get('network_isolation_error_type'))}"
            )
            print(
                "  wfp_target_drop_evidence="
                f"{_classify_wfp_target_drop_receipt(wfp_receipt, collector_exit_code=wfp_exit_code)}"
            )
            print(
                "  wfp_observer_diagnostics="
                + json.dumps(
                    _wfp_observer_diagnostic_summary(
                        process_started=wfp_process is not None,
                        paths=wfp_paths,
                        receipt=wfp_receipt,
                        collector_exit_code=wfp_exit_code,
                    ),
                    sort_keys=True,
                    separators=(",", ":"),
                )
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
        diagnostic = "unclassified"
        if len(exc.args) == 1 and type(exc.args[0]) is str:
            candidate = exc.args[0]
            if candidate == "private_network_probe_address_unavailable":
                diagnostic = candidate
            elif re.fullmatch(
                r"dacl_baseline_[a-z_]+(?:_(?:win|errno)_\d+)?", candidate,
            ):
                diagnostic = candidate
        print(
            "windows_appcontainer_read_handle_probe "
            f"error={type(exc).__name__} code={diagnostic}"
        )
        return 1


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: run_windows_appcontainer_read_probe.py <probe-exe> <wfp-probe-exe>")
        return 2
    return _run(Path(sys.argv[1]), Path(sys.argv[2]))


if __name__ == "__main__":
    raise SystemExit(main())
