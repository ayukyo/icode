"""Safely enumerate selected CAB members on Windows without extracting them."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
from ctypes import wintypes
from pathlib import Path


_MAX_CABINET_BYTES = 64 * 1024 * 1024
_MAX_CABINET_MEMBERS = 4096
_TARGET_BASENAME = "wfpdiag.xml"
_XML_SUFFIX = ".xml"

_SPFILENOTIFY_CABINETINFO = 0x10
_SPFILENOTIFY_FILEINCABINET = 0x11
_SPFILENOTIFY_NEEDNEWCABINET = 0x12
_SPFILENOTIFY_FILEEXTRACTED = 0x13
_FILEOP_ABORT = 0
_FILEOP_SKIP = 2
_NO_ERROR = 0
_ERROR_NOT_SUPPORTED = 50

_RESULT_STATUSES = frozenset({
    "listed",
    "invalid_archive",
    "archive_too_large",
    "unsupported_platform",
    "api_unavailable",
    "api_failed",
    "multi_volume",
    "member_error",
    "member_limit_exceeded",
    "callback_error",
})


class _FileInCabinetInfoW(ctypes.Structure):
    """Prefix-compatible declaration of the documented SetupAPI structure."""

    _fields_ = [
        ("NameInCabinet", wintypes.LPCWSTR),
        ("FileSize", wintypes.DWORD),
        ("Win32Error", wintypes.DWORD),
        ("DosDate", wintypes.WORD),
        ("DosTime", wintypes.WORD),
        ("DosAttribs", wintypes.WORD),
        ("FullTargetName", wintypes.WCHAR * 260),
    ]


def is_target_cabinet_member(member_name: object) -> bool:
    """Match only the exact ASCII basename, independent of CAB path separators."""
    basename = _cabinet_member_basename(member_name)
    return basename is not None and basename.lower() == _TARGET_BASENAME


def is_xml_cabinet_member(member_name: object) -> bool:
    """Count an ASCII XML filename by suffix without retaining its name or path."""
    basename = _cabinet_member_basename(member_name)
    return basename is not None and basename.lower().endswith(_XML_SUFFIX)


def _cabinet_member_basename(member_name: object) -> str | None:
    if not isinstance(member_name, str) or not member_name:
        return None
    basename = member_name.replace("\\", "/").rsplit("/", 1)[-1]
    if not basename.isascii() or not basename:
        return None
    return basename


def _safe_summary(
    status: str,
    *,
    member_count: int = 0,
    target_match_count: int | None = None,
    xml_member_count: int | None = None,
) -> dict[str, int | str | None]:
    """Return fixed fields only; never include paths, names, or native errors."""
    safe_status = status if status in _RESULT_STATUSES else "api_failed"
    bounded_member_count = min(max(int(member_count), 0), _MAX_CABINET_MEMBERS + 1)
    bounded_match_count = target_match_count
    if bounded_match_count is not None:
        bounded_match_count = min(max(int(bounded_match_count), 0), _MAX_CABINET_MEMBERS)
    bounded_xml_member_count = xml_member_count
    if bounded_xml_member_count is not None:
        bounded_xml_member_count = min(
            max(int(bounded_xml_member_count), 0), _MAX_CABINET_MEMBERS,
        )
    return {
        "schema_version": 2,
        "status": safe_status,
        "member_count": bounded_member_count,
        "target_match_count": bounded_match_count,
        "xml_member_count": bounded_xml_member_count,
    }


def _handle_setupapi_notification(
    notification: int,
    param1: int,
    state: dict[str, int | str],
) -> int:
    """Handle cabinet metadata and member notifications without extracting."""
    if notification == _SPFILENOTIFY_CABINETINFO:
        # Cabinet metadata is not needed for basename matching; continue safely.
        return _NO_ERROR

    if notification == _SPFILENOTIFY_FILEINCABINET:
        next_member_count = int(state["member_count"]) + 1
        state["member_count"] = next_member_count
        if next_member_count > _MAX_CABINET_MEMBERS:
            state["status"] = "member_limit_exceeded"
            return _FILEOP_ABORT

        if not param1:
            state["status"] = "callback_error"
            return _FILEOP_ABORT
        info = ctypes.cast(
            ctypes.c_void_p(param1),
            ctypes.POINTER(_FileInCabinetInfoW),
        ).contents
        if info.Win32Error != _NO_ERROR:
            # A member-level system error must not count as a valid name match.
            state["status"] = "member_error"
            return _FILEOP_ABORT

        if is_target_cabinet_member(info.NameInCabinet):
            state["target_match_count"] = int(state["target_match_count"]) + 1
        if is_xml_cabinet_member(info.NameInCabinet):
            state["xml_member_count"] = int(state["xml_member_count"]) + 1

        # Enumeration is intentionally non-extracting for every member.
        return _FILEOP_SKIP

    if notification == _SPFILENOTIFY_NEEDNEWCABINET:
        state["status"] = "multi_volume"
        return _ERROR_NOT_SUPPORTED
    if notification == _SPFILENOTIFY_FILEEXTRACTED:
        return _NO_ERROR

    state["status"] = "callback_error"
    return _ERROR_NOT_SUPPORTED


def _enumerate_windows_cabinet(archive_path: Path) -> dict[str, int | str | None]:
    try:
        setupapi = ctypes.WinDLL("setupapi.dll", use_last_error=True)
        setup_iterate_cabinet = setupapi.SetupIterateCabinetW
    except (AttributeError, OSError):
        return _safe_summary("api_unavailable")

    state: dict[str, int | str] = {
        "member_count": 0,
        "target_match_count": 0,
        "xml_member_count": 0,
    }

    callback_type = ctypes.WINFUNCTYPE(
        wintypes.UINT,
        wintypes.LPVOID,
        wintypes.UINT,
        ctypes.c_size_t,
        ctypes.c_size_t,
    )

    @callback_type
    def cabinet_callback(_context, notification, param1, _param2):
        try:
            return _handle_setupapi_notification(notification, param1, state)
        except BaseException:
            # Python exceptions must never cross the native callback boundary.
            state["status"] = "callback_error"
            return _FILEOP_ABORT

    setup_iterate_cabinet.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        callback_type,
        wintypes.LPVOID,
    ]
    setup_iterate_cabinet.restype = wintypes.BOOL
    try:
        succeeded = bool(setup_iterate_cabinet(str(archive_path), 0, cabinet_callback, None))
    except (OSError, TypeError, ValueError):
        return _safe_summary("api_failed")

    status = state.get("status")
    member_count = int(state["member_count"])
    if status:
        return _safe_summary(str(status), member_count=member_count)
    if not succeeded:
        return _safe_summary("api_failed", member_count=member_count)
    return _safe_summary(
        "listed",
        member_count=member_count,
        target_match_count=int(state["target_match_count"]),
        xml_member_count=int(state["xml_member_count"]),
    )


def inspect_cabinet_members(archive: str | Path) -> dict[str, int | str | None]:
    """Enumerate a bounded cabinet and return only a fixed, privacy-safe receipt."""
    try:
        archive_path = Path(archive)
        if not archive_path.is_file():
            return _safe_summary("invalid_archive")
        archive_size = archive_path.stat().st_size
    except (OSError, TypeError, ValueError):
        return _safe_summary("invalid_archive")

    if archive_size > _MAX_CABINET_BYTES:
        return _safe_summary("archive_too_large")
    if os.name != "nt":
        return _safe_summary("unsupported_platform")
    try:
        return _enumerate_windows_cabinet(archive_path)
    except Exception:
        # Native errors remain a fixed category; do not echo exception text or paths.
        return _safe_summary("api_failed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, help="local CAB file to enumerate")
    args = parser.parse_args(argv)
    result = inspect_cabinet_members(args.archive)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "listed" else 1


if __name__ == "__main__":
    sys.exit(main())
