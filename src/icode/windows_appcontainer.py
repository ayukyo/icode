"""R2.3 AppContainer 文件/网络边界实验；不是生产后端 ready 证明。

执行边界包含工单工作区和当前临时 profile 的私有 LOCALAPPDATA。后者允许容器写临时应用数据，
profile 销毁后必须确认该目录已消失；残留或无法核验均作为清理失败处理。
本模块尚未接入自动工单；调用方必须传入独立的任务工作区，而不能传入原始仓库。
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass, field
import ntpath
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import time
import uuid
from ctypes import wintypes
from typing import Sequence

from .windows_job import (
    WindowsJobResult,
    _is_fixed_system_whoami_probe,
    run_windows_job,
)


_SE_FILE_OBJECT = 1
_DACL_SECURITY_INFORMATION = 0x00000004
_SE_DACL_PROTECTED = 0x1000
_SE_DACL_AUTO_INHERITED = 0x0400
_FILE_GENERIC_READ = 0x00120089
_FILE_GENERIC_WRITE = 0x00120116
_FILE_GENERIC_EXECUTE = 0x001200A0
_DELETE = 0x00010000
_FILE_DELETE_CHILD = 0x00000040
_WORKSPACE_ACCESS = (
    _FILE_GENERIC_READ | _FILE_GENERIC_WRITE | _FILE_GENERIC_EXECUTE
    | _DELETE | _FILE_DELETE_CHILD
)
_OBJECT_INHERIT_ACE = 0x01
_CONTAINER_INHERIT_ACE = 0x02
_GRANT_ACCESS = 1
_TRUSTEE_IS_SID = 0
_TRUSTEE_IS_UNKNOWN = 0
_PROFILE_DELETE_ATTEMPTS = 2
_MAX_RUNTIME_ACL_OBJECTS = 100_000
_MAX_RUNTIME_ACL_SNAPSHOT_SECONDS = 30


@dataclass(frozen=True)
class _DaclSnapshot:
    path: Path
    dacl: bytes
    control: int
    revision: int
    present: bool
    defaulted: bool
    file_identity: tuple[int, int]

    @property
    def protected(self) -> bool:
        return bool(self.control & _SE_DACL_PROTECTED)


@dataclass
class _RuntimeAclTransaction:
    roots: tuple[Path, ...]
    entries: tuple[_DaclSnapshot, ...]
    advapi: ctypes.WinDLL
    kernel: ctypes.WinDLL
    snapshot_duration_ms: int
    modified_roots: list[Path] = field(default_factory=list)


class _AppContainerSetupError(RuntimeError):
    def __init__(self, error: str, detail: str) -> None:
        super().__init__(detail)
        self.error = error
        self.detail = detail


def _get_appcontainer_localappdata_path(
    sid: ctypes.c_void_p,
    userenv: ctypes.WinDLL,
    advapi: ctypes.WinDLL,
    kernel: ctypes.WinDLL,
    ole32: ctypes.WinDLL,
) -> str:
    """Resolve LOCALAPPDATA from this profile SID, never from the host environment."""
    advapi.ConvertSidToStringSidW.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi.ConvertSidToStringSidW.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    userenv.GetAppContainerFolderPath.argtypes = [
        wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p),
    ]
    userenv.GetAppContainerFolderPath.restype = ctypes.c_long
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole32.CoTaskMemFree.restype = None

    sid_string = ctypes.c_void_p()
    profile_path = ctypes.c_void_p()
    cleanup_errors: list[str] = []
    try:
        if not advapi.ConvertSidToStringSidW(sid, ctypes.byref(sid_string)):
            raise _AppContainerSetupError(
                "appcontainer_profile_path_failed",
                f"ConvertSidToStringSidW err={ctypes.get_last_error()}",
            )
        if not sid_string.value:
            raise _AppContainerSetupError(
                "appcontainer_profile_path_failed", "SID 字符串为空",
            )
        hr = int(userenv.GetAppContainerFolderPath(
            ctypes.wstring_at(sid_string), ctypes.byref(profile_path),
        ))
        if hr != 0 or not profile_path.value:
            raise _AppContainerSetupError(
                "appcontainer_profile_path_failed",
                f"GetAppContainerFolderPath hr=0x{hr & 0xFFFFFFFF:08x}",
            )
        path = ctypes.wstring_at(profile_path)
        if not path or "\0" in path or not ntpath.isabs(path):
            raise _AppContainerSetupError(
                "appcontainer_profile_path_failed", "profile 路径不是绝对 Windows 路径",
            )
        return path
    finally:
        if profile_path.value:
            try:
                ole32.CoTaskMemFree(profile_path)
            except Exception:  # noqa: BLE001 - 必须仍释放另一个原生输出
                cleanup_errors.append("CoTaskMemFree failed")
        if sid_string:
            try:
                if kernel.LocalFree(sid_string):
                    cleanup_errors.append("LocalFree did not release SID string")
            except Exception:  # noqa: BLE001 - 资源释放错误必须 fail closed
                cleanup_errors.append("LocalFree failed")
        if cleanup_errors:
            raise _AppContainerSetupError(
                "appcontainer_profile_path_cleanup_failed", "; ".join(cleanup_errors),
            )


def _delete_appcontainer_profile(
    profile: str, userenv: ctypes.WinDLL, local_app_data_path: str | None,
) -> tuple[bool, str]:
    """Retry profile removal and fail if its known private data directory remains."""
    last_hresult: int | None = None
    for _attempt in range(_PROFILE_DELETE_ATTEMPTS):
        try:
            last_hresult = int(userenv.DeleteAppContainerProfile(profile))
        except Exception:  # noqa: BLE001 - native cleanup errors must remain explicit
            last_hresult = None
            continue
        if last_hresult != 0:
            continue
        if local_app_data_path is None:
            return True, ""
        try:
            os.lstat(local_app_data_path)
        except FileNotFoundError:
            return True, ""
        except (OSError, ValueError):
            # An uninspectable path is not evidence that private data was removed.
            continue

    if local_app_data_path is not None:
        try:
            os.lstat(local_app_data_path)
        except FileNotFoundError:
            if last_hresult == 0:
                return True, ""
            if last_hresult is None:
                return False, "profile_delete_failed"
            return False, f"profile_delete_failed:0x{last_hresult & 0xFFFFFFFF:08x}"
        except (OSError, ValueError):
            return False, "profile_storage_unverified"
        return False, "profile_storage_residual"
    if last_hresult is None:
        return False, "profile_delete_failed"
    return False, f"profile_delete_failed:0x{last_hresult & 0xFFFFFFFF:08x}"


def _win32_error_code(detail: str) -> str:
    """Extract only a numeric Win32 error from a bounded native diagnostic."""
    marker = "(err="
    start = detail.find(marker)
    if start < 0:
        return "unknown"
    value = detail[start + len(marker):].partition(")")[0]
    return value if value.isdecimal() else "unknown"


def _walk_workspace(
    root: Path, *, max_entries: int | None = None, deadline: float | None = None,
) -> list[Path]:
    """拒绝重解析点和硬链接，避免 ACL 沿路径/文件别名扩大到工作区外。"""
    try:
        root_info = root.lstat()
    except OSError as exc:
        raise _AppContainerSetupError("invalid_workspace", "无法检查任务目录") from exc
    if not stat.S_ISDIR(root_info.st_mode) or _is_reparse(root_info):
        raise _AppContainerSetupError("invalid_workspace", "任务目录必须是普通目录")
    if max_entries is not None and max_entries < 1:
        raise _AppContainerSetupError("invalid_workspace", "目录扫描上限无效")

    paths = [root]
    try:
        for current, directories, files in os.walk(root, topdown=True, followlinks=False):
            current_path = Path(current)
            for names in (directories, files):
                for name in names:
                    if deadline is not None and time.monotonic() > deadline:
                        raise _AppContainerSetupError(
                            "runtime_acl_preflight_too_slow", "目录安全扫描超过时间上限",
                        )
                    if max_entries is not None and len(paths) >= max_entries:
                        raise _AppContainerSetupError(
                            "runtime_acl_preflight_too_large", "目录安全扫描超过对象数上限",
                        )
                    path = current_path / name
                    info = path.lstat()
                    if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
                        raise _AppContainerSetupError(
                            "unsupported_workspace_entry",
                            f"目录含重解析点类别={_reparse_kind(info)}，AppContainer 拒绝启动",
                        )
                    if stat.S_ISREG(info.st_mode) and info.st_nlink > 1:
                        raise _AppContainerSetupError(
                            "unsupported_workspace_entry", "任务目录含硬链接，AppContainer 拒绝启动",
                        )
                    if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
                        raise _AppContainerSetupError(
                            "unsupported_workspace_entry", "任务目录含非普通文件，AppContainer 拒绝启动",
                        )
                    paths.append(path)
    except _AppContainerSetupError:
        raise
    except OSError as exc:
        raise _AppContainerSetupError("workspace_inspection_failed", "任务目录检查失败") from exc
    return paths


def _is_reparse(info: os.stat_result) -> bool:
    return bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _reparse_kind(info: os.stat_result) -> str:
    """Return a small path-free category for Windows reparse diagnostics."""
    if stat.S_ISLNK(info.st_mode):
        return "symbolic_link"
    tag = int(getattr(info, "st_reparse_tag", 0))
    if tag == getattr(stat, "IO_REPARSE_TAG_SYMLINK", 0xA000000C):
        return "symbolic_link"
    if tag == getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", 0xA0000003):
        return "mount_point"
    return "other_reparse"


def _classify_runtime_link_target(
    raw_target: str, link_parent: str | os.PathLike[str],
    runtime_root: str | os.PathLike[str], *, windows: bool | None = None,
) -> str:
    """Classify a link target lexically without opening or following it."""
    if not raw_target:
        return "unknown"
    if windows is None:
        windows = os.name == "nt"

    if windows:
        target = raw_target
        if target.startswith("\\\\?\\UNC\\"):
            target = "\\\\" + target[8:]
        elif target.startswith("\\\\?\\"):
            target = target[4:]
        if target.startswith(("\\??\\", "\\Device\\", "\\\\.\\")):
            return "unknown"
        target_drive, _target_tail = ntpath.splitdrive(target)
        if target_drive.startswith("\\\\"):
            return "outside_root"
        if not ntpath.isabs(target):
            if target_drive:
                return "unknown"
            target = ntpath.join(os.fspath(link_parent), target)
        if not ntpath.isabs(target):
            return "unknown"

        root = os.fspath(runtime_root)
        if root.startswith("\\\\?\\"):
            root = root[4:]
        root_drive, _root_tail = ntpath.splitdrive(root)
        if not root_drive or root_drive.startswith("\\\\"):
            return "unknown"
        target = ntpath.normcase(ntpath.normpath(target))
        root = ntpath.normcase(ntpath.normpath(root))
        try:
            common = ntpath.commonpath((root, target))
        except ValueError:
            return "outside_root"
        return "inside_root" if common == root else "outside_root"

    target_path = Path(raw_target)
    if not target_path.is_absolute():
        target_path = Path(link_parent) / target_path
    target = os.path.normcase(os.path.abspath(os.path.normpath(str(target_path))))
    root = os.path.normcase(os.path.abspath(os.path.normpath(os.fspath(runtime_root))))
    try:
        common = os.path.commonpath((root, target))
    except ValueError:
        return "outside_root"
    return "inside_root" if common == root else "outside_root"


def _runtime_reparse_inventory(
    root: str | os.PathLike[str], *, max_entries: int = _MAX_RUNTIME_ACL_OBJECTS,
    deadline: float | None = None,
) -> dict[str, int]:
    """Count reparse categories and lexical target relations without following links."""
    root_path = Path(root)
    if not root_path.is_absolute() or max_entries < 1:
        raise _AppContainerSetupError(
            "runtime_reparse_inventory_failed", "runtime reparse inventory input is invalid",
        )
    if deadline is None:
        deadline = time.monotonic() + _MAX_RUNTIME_ACL_SNAPSHOT_SECONDS
    try:
        root_info = root_path.lstat()
        if not stat.S_ISDIR(root_info.st_mode) or _is_reparse(root_info):
            raise _AppContainerSetupError(
                "runtime_reparse_inventory_failed", "runtime root is not a regular directory",
            )
        root_comparison = Path(os.path.abspath(os.fspath(root_path)))
        for component in reversed(root_path.parents):
            if _is_reparse(component.lstat()):
                raise _AppContainerSetupError(
                    "runtime_reparse_inventory_failed", "runtime root path contains a reparse point",
                )
    except _AppContainerSetupError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise _AppContainerSetupError(
            "runtime_reparse_inventory_failed", "runtime root cannot be inspected safely",
        ) from exc

    summary = {
        "entries": 0,
        "symbolic_link": 0,
        "mount_point": 0,
        "other_reparse": 0,
        "link_target_inside_root": 0,
        "link_target_outside_root": 0,
        "link_target_unknown": 0,
    }
    pending = [root_path]
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as children:
                for child in children:
                    summary["entries"] += 1
                    if summary["entries"] > max_entries:
                        raise _AppContainerSetupError(
                            "runtime_reparse_inventory_too_large",
                            "runtime reparse inventory exceeds object limit",
                        )
                    if time.monotonic() > deadline:
                        raise _AppContainerSetupError(
                            "runtime_reparse_inventory_too_slow",
                            "runtime reparse inventory exceeded time limit",
                        )
                    info = child.stat(follow_symlinks=False)
                    if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
                        kind = _reparse_kind(info)
                        summary[kind] += 1
                        if kind == "symbolic_link":
                            try:
                                raw_target = os.readlink(child.path)
                            except (OSError, ValueError):
                                relation = "unknown"
                            else:
                                relation = _classify_runtime_link_target(
                                    raw_target, directory, root_comparison,
                                )
                            summary[f"link_target_{relation}"] += 1
                        continue
                    if stat.S_ISDIR(info.st_mode):
                        pending.append(Path(child.path))
        except _AppContainerSetupError:
            raise
        except (OSError, RuntimeError, ValueError) as exc:
            raise _AppContainerSetupError(
                "runtime_reparse_inventory_failed",
                "runtime reparse inventory could not inspect an entry",
            ) from exc
    return summary


def _copy_runtime_tree_for_diagnostic(
    source_root: str | os.PathLike[str],
    destination_root: str | os.PathLike[str],
) -> dict[str, int]:
    """Copy a runtime into a disposable tree, materializing only in-root links.

    This is a CI diagnostic primitive, not a production runtime cache. The
    source remains untouched; reparse points with non-local/unknown targets and
    all non-symbolic reparse kinds are rejected before copying. The caller must
    own and remove the disposable parent and separately verify staged DACL
    restoration before cleanup.
    """
    source = Path(source_root)
    destination = Path(destination_root)
    if not source.is_absolute() or not destination.is_absolute():
        raise _AppContainerSetupError(
            "runtime_staging_copy_failed", "runtime staging paths must be absolute",
        )
    source_abs = Path(os.path.abspath(os.fspath(source)))
    destination_abs = Path(os.path.abspath(os.fspath(destination)))
    if (
        source_abs == destination_abs
        or source_abs in destination_abs.parents
        or destination_abs in source_abs.parents
    ):
        raise _AppContainerSetupError(
            "runtime_staging_copy_failed", "runtime staging paths overlap",
        )

    try:
        parent = destination_abs.parent
        if not parent.is_dir():
            raise _AppContainerSetupError(
                "runtime_staging_copy_failed", "runtime staging parent is invalid",
            )
        temp_root = Path(tempfile.gettempdir()).resolve(strict=True)
        parent_resolved = parent.resolve(strict=True)
        if (
            not destination_abs.name.startswith("icode-runtime-staging-")
            or (parent_resolved != temp_root and temp_root not in parent_resolved.parents)
        ):
            raise _AppContainerSetupError(
                "runtime_staging_copy_failed",
                "runtime staging destination must be a named child of the temp directory",
            )
        current = Path(parent.anchor)
        for component in parent.parts[1:]:
            current = current / component
            info = current.lstat()
            if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
                raise _AppContainerSetupError(
                    "runtime_staging_copy_failed", "runtime staging parent contains a reparse point",
                )
        try:
            destination_abs.lstat()
        except FileNotFoundError:
            pass
        else:
            raise _AppContainerSetupError(
                "runtime_staging_copy_failed", "runtime staging destination already exists",
            )
    except _AppContainerSetupError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise _AppContainerSetupError(
            "runtime_staging_copy_failed", "runtime staging destination cannot be inspected",
        ) from exc

    before = _runtime_reparse_inventory(source_abs)
    if (
        before["mount_point"]
        or before["other_reparse"]
        or before["symbolic_link"] != before["link_target_inside_root"]
    ):
        raise _AppContainerSetupError(
            "runtime_staging_unsafe_reparse", "runtime tree has unsafe reparse targets",
        )
    # copytree(symlinks=False) recursively follows directory symlinks. Even a
    # lexically in-root directory target can alias a subtree and make copying
    # unbounded or ambiguous, so only links resolving to regular files are
    # materialized by this diagnostic.
    pending = [source_abs]
    try:
        while pending:
            directory = pending.pop()
            with os.scandir(directory) as children:
                for child in children:
                    info = child.stat(follow_symlinks=False)
                    if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
                        try:
                            resolved_target = Path(child.path).resolve(strict=True)
                            target_info = resolved_target.stat()
                        except (OSError, RuntimeError, ValueError) as exc:
                            raise _AppContainerSetupError(
                                "runtime_staging_unsafe_reparse",
                                "runtime link target cannot be resolved safely",
                            ) from exc
                        if (
                            resolved_target != source_abs
                            and source_abs not in resolved_target.parents
                        ) or not stat.S_ISREG(target_info.st_mode):
                            raise _AppContainerSetupError(
                                "runtime_staging_unsafe_reparse",
                                "runtime staging supports only in-root regular-file links",
                            )
                    elif stat.S_ISDIR(info.st_mode):
                        pending.append(Path(child.path))
    except _AppContainerSetupError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise _AppContainerSetupError(
            "runtime_staging_copy_failed", "runtime tree could not be inspected before copy",
        ) from exc
    try:
        # The checked-in CI source has no concurrent mutator. The post-copy
        # inventory below still verifies that the staged tree is reparse-free.
        shutil.copytree(source_abs, destination_abs, symlinks=False)
    except (OSError, shutil.Error, RuntimeError, ValueError) as exc:
        raise _AppContainerSetupError(
            "runtime_staging_copy_failed", "runtime tree could not be copied safely",
        ) from exc

    after = _runtime_reparse_inventory(source_abs)
    staged = _runtime_reparse_inventory(destination_abs)
    if after != before or any(
        staged[name]
        for name in (
            "symbolic_link", "mount_point", "other_reparse",
            "link_target_inside_root", "link_target_outside_root", "link_target_unknown",
        )
    ):
        raise _AppContainerSetupError(
            "runtime_staging_copy_failed", "runtime tree changed or staging contains reparse points",
        )
    return {
        "source_entries": before["entries"],
        "materialized_links": before["symbolic_link"],
        "staged_entries": staged["entries"],
    }


def _is_unc_runtime_root(raw_root: str | os.PathLike[str], *, windows: bool | None = None) -> bool:
    """Recognize Windows UNC roots lexically, before touching the share."""
    if windows is None:
        windows = os.name == "nt"
    if not windows:
        return False
    drive, _tail = ntpath.splitdrive(os.fspath(raw_root))
    return drive.startswith(("\\\\", "//"))


def _validate_runtime_roots(
    roots: Sequence[Path], *, workspace: Path,
) -> tuple[Path, ...]:
    """Validate narrow, disjoint local runtime roots before any ACL mutation."""
    try:
        workspace_path = Path(workspace)
        if not workspace_path.is_absolute():
            raise ValueError("workspace must be absolute")
        workspace_path = workspace_path.resolve(strict=True)
        home = Path.home().resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise _AppContainerSetupError(
            "invalid_runtime_root", "runtime/workspace boundary cannot be resolved",
        ) from exc

    def intersects(left: Path, right: Path) -> bool:
        left_text = os.path.normcase(os.path.normpath(str(left)))
        right_text = os.path.normcase(os.path.normpath(str(right)))
        try:
            common = os.path.commonpath((left_text, right_text))
        except ValueError:
            return False
        return common == left_text or common == right_text

    unique: dict[str, Path] = {}
    for raw_root in roots:
        if _is_unc_runtime_root(raw_root):
            raise _AppContainerSetupError(
                "unsupported_runtime_root", "UNC or non-local runtime roots are unsupported",
            )
        try:
            candidate = Path(raw_root)
            if not candidate.is_absolute():
                raise ValueError("runtime root must be absolute")
            # Inspect each path component before resolve() so a junction/symlink
            # cannot silently redirect the DACL target to a different tree.
            current = Path(candidate.anchor)
            for component in candidate.parts[1:]:
                current = current / component
                info = current.lstat()
                if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
                    raise _AppContainerSetupError(
                        "unsupported_runtime_root",
                        f"runtime path contains a reparse point ({_reparse_kind(info)})",
                    )
            root = candidate.resolve(strict=True)
            root_info = root.lstat()
        except _AppContainerSetupError:
            raise
        except (OSError, RuntimeError, ValueError) as exc:
            raise _AppContainerSetupError(
                "invalid_runtime_root", "runtime root is not a resolvable local directory",
            ) from exc

        if (
            not stat.S_ISDIR(root_info.st_mode)
            or stat.S_ISLNK(root_info.st_mode)
            or _is_reparse(root_info)
        ):
            raise _AppContainerSetupError(
                "invalid_runtime_root", "runtime root must be a regular directory",
            )
        if root == Path(root.anchor):
            raise _AppContainerSetupError(
                "unsupported_runtime_root", "filesystem root is too broad for runtime access",
            )
        if os.name == "nt":
            drive, _tail = ntpath.splitdrive(str(root))
            if not drive or drive.startswith("\\\\"):
                raise _AppContainerSetupError(
                    "unsupported_runtime_root", "UNC or non-local runtime roots are unsupported",
                )
            if root == Path(root.anchor):
                raise _AppContainerSetupError(
                    "unsupported_runtime_root", "filesystem root is too broad for runtime access",
                )
            try:
                kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
                kernel.GetDriveTypeW.restype = wintypes.UINT
                drive_type = int(kernel.GetDriveTypeW(root.anchor))
            except (AttributeError, OSError, TypeError, ValueError) as exc:
                raise _AppContainerSetupError(
                    "invalid_runtime_root", "runtime volume type cannot be verified",
                ) from exc
            if drive_type != 3:  # DRIVE_FIXED; reject removable and mapped drives.
                raise _AppContainerSetupError(
                    "unsupported_runtime_root", "runtime root must reside on a fixed local drive",
                )
        if home.is_relative_to(root):
            raise _AppContainerSetupError(
                "unsupported_runtime_root", "runtime root includes the user home directory",
            )
        if intersects(root, workspace_path):
            raise _AppContainerSetupError(
                "unsupported_runtime_root", "runtime root overlaps the writable task workspace",
            )
        if os.name == "nt":
            system_root_raw = os.environ.get("SystemRoot", r"C:\Windows")
            try:
                system_root = Path(system_root_raw).resolve(strict=True)
            except (OSError, RuntimeError):
                raise _AppContainerSetupError(
                    "invalid_runtime_root", "Windows system root cannot be verified",
                ) from None
            if intersects(root, system_root):
                raise _AppContainerSetupError(
                    "unsupported_runtime_root", "Windows system directories are not runtime roots",
                )

        key = os.path.normcase(os.path.normpath(str(root)))
        unique[key] = root

    result = tuple(sorted(unique.values(), key=lambda path: os.path.normcase(str(path))))
    for index, root in enumerate(result):
        for other in result[index + 1:]:
            if intersects(root, other):
                raise _AppContainerSetupError(
                    "unsupported_runtime_root", "runtime roots overlap or are nested",
                )
    if not result:
        raise _AppContainerSetupError("invalid_runtime_root", "no Python runtime roots were provided")
    return result


def _validate_diagnostic_runtime_roots(
    roots: Sequence[str | os.PathLike[str]], *,
    executable: str | os.PathLike[str],
    workspace: Path,
) -> tuple[Path, ...]:
    """Accept only one named staging root under the runner's temp directory."""
    if isinstance(roots, (str, bytes)) or len(roots) != 1:
        raise _AppContainerSetupError(
            "invalid_diagnostic_probe", "staging diagnostic requires exactly one runtime root",
        )
    try:
        temp_root = Path(tempfile.gettempdir()).resolve(strict=True)
        validated = _validate_runtime_roots(tuple(Path(root) for root in roots), workspace=workspace)
        root = validated[0]
        executable_path = Path(executable).resolve(strict=True)
    except _AppContainerSetupError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise _AppContainerSetupError(
            "invalid_diagnostic_probe", "staging diagnostic paths cannot be verified",
        ) from exc
    if (
        root == temp_root
        or not root.is_relative_to(temp_root)
        or not root.name.startswith("icode-runtime-staging-")
        or executable_path == root
        or not executable_path.is_relative_to(root)
        or not executable_path.is_file()
    ):
        raise _AppContainerSetupError(
            "invalid_diagnostic_probe", "staging runtime is outside its dedicated temp root",
        )
    return validated


def _read_dacl_state(
    path: Path, advapi: ctypes.WinDLL, kernel: ctypes.WinDLL,
) -> _DaclSnapshot:
    dacl = ctypes.c_void_p()
    descriptor = ctypes.c_void_p()
    status = advapi.GetNamedSecurityInfoW(
        str(path), _SE_FILE_OBJECT, _DACL_SECURITY_INFORMATION,
        None, None, ctypes.byref(dacl), None, ctypes.byref(descriptor),
    )
    if status != 0:
        raise _AppContainerSetupError(
            "workspace_acl_unavailable", f"GetNamedSecurityInfoW err={int(status)}",
        )
    try:
        present = wintypes.BOOL()
        descriptor_dacl = ctypes.c_void_p()
        defaulted = wintypes.BOOL()
        if not advapi.GetSecurityDescriptorDacl(
            descriptor, ctypes.byref(present), ctypes.byref(descriptor_dacl),
            ctypes.byref(defaulted),
        ):
            raise _AppContainerSetupError(
                "workspace_acl_unavailable",
                f"GetSecurityDescriptorDacl err={ctypes.get_last_error()}",
            )
        if not present.value or not dacl.value or not descriptor_dacl.value:
            raise _AppContainerSetupError(
                "workspace_acl_unavailable", "目标存在 absent/null DACL，拒绝扩大访问",
            )
        class ACL_SIZE_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("AceCount", wintypes.DWORD),
                ("AclBytesInUse", wintypes.DWORD),
                ("AclBytesFree", wintypes.DWORD),
            ]

        size_info = ACL_SIZE_INFORMATION()
        if not advapi.GetAclInformation(
            dacl, ctypes.byref(size_info), ctypes.sizeof(size_info), 2,
        ):
            raise _AppContainerSetupError(
                "workspace_acl_unavailable",
                f"GetAclInformation err={ctypes.get_last_error()}",
            )
        acl_size = int(size_info.AclBytesInUse + size_info.AclBytesFree)
        if acl_size < 8:
            raise _AppContainerSetupError("workspace_acl_unavailable", "任务目录 ACL 长度无效")
        control = wintypes.WORD()
        revision = wintypes.DWORD()
        if not advapi.GetSecurityDescriptorControl(
            descriptor, ctypes.byref(control), ctypes.byref(revision),
        ):
            raise _AppContainerSetupError(
                "workspace_acl_unavailable",
                f"GetSecurityDescriptorControl err={ctypes.get_last_error()}",
            )
        info = path.lstat()
        file_identity = (int(info.st_dev), int(info.st_ino))
        return _DaclSnapshot(
            path=path,
            dacl=ctypes.string_at(dacl, acl_size),
            control=int(control.value),
            revision=int(revision.value),
            present=bool(present.value),
            defaulted=bool(defaulted.value),
            file_identity=file_identity,
        )
    finally:
        if descriptor.value:
            kernel.LocalFree(descriptor)


def _read_dacl(
    path: Path, advapi: ctypes.WinDLL, kernel: ctypes.WinDLL,
) -> tuple[bytes, bool]:
    snapshot = _read_dacl_state(path, advapi, kernel)
    return snapshot.dacl, snapshot.protected


def _contains_sid(
    dacl: bytes, sid: ctypes.c_void_p, advapi: ctypes.WinDLL,
) -> bool:
    class ACE_HEADER(ctypes.Structure):
        _fields_ = [
            ("AceType", ctypes.c_ubyte),
            ("AceFlags", ctypes.c_ubyte),
            ("AceSize", wintypes.WORD),
        ]

    class ACL_SIZE_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("AceCount", wintypes.DWORD),
            ("AclBytesInUse", wintypes.DWORD),
            ("AclBytesFree", wintypes.DWORD),
        ]

    storage = ctypes.create_string_buffer(dacl)
    acl = ctypes.cast(storage, ctypes.c_void_p)
    size_info = ACL_SIZE_INFORMATION()
    if not advapi.GetAclInformation(
        acl, ctypes.byref(size_info), ctypes.sizeof(size_info), 2,
    ):
        return True
    for index in range(int(size_info.AceCount)):
        ace_ptr = ctypes.c_void_p()
        if not advapi.GetAce(acl, index, ctypes.byref(ace_ptr)):
            return True
        header = ctypes.cast(ace_ptr, ctypes.POINTER(ACE_HEADER)).contents
        # The package SID ACE installed here is a basic ACCESS_ALLOWED_ACE.
        if header.AceType not in (0, 1) or header.AceSize < 8:
            continue
        ace_sid = ctypes.c_void_p(ace_ptr.value + ctypes.sizeof(ACE_HEADER) + 4)
        if advapi.EqualSid(ace_sid, sid):
            return True
    return False


def _set_dacl(
    path: Path, dacl: ctypes.c_void_p, advapi: ctypes.WinDLL,
) -> None:
    status = advapi.SetNamedSecurityInfoW(
        str(path), _SE_FILE_OBJECT, _DACL_SECURITY_INFORMATION,
        None, None, dacl, None,
    )
    if status != 0:
        raise _AppContainerSetupError(
            "workspace_acl_failed", f"SetNamedSecurityInfoW err={int(status)}",
        )


def _normalize_staged_runtime_acl_baseline(
    root: Path, advapi: ctypes.WinDLL, kernel: ctypes.WinDLL,
) -> int:
    """Normalize Windows' auto-inherited DACL marker on a disposable staging root.

    This is deliberately limited to the explicitly opted-in GitHub Windows
    staging diagnostic. It establishes the baseline before temporary Package
    SID access is added; it is not a production ACL restoration fallback.
    """
    if (
        os.environ.get("GITHUB_ACTIONS") != "true"
        or os.environ.get("RUNNER_OS") != "Windows"
        or os.environ.get("ICODE_DIAGNOSTIC_RUNTIME_STAGING") != "true"
    ):
        raise _AppContainerSetupError(
            "invalid_diagnostic_probe", "staging ACL normalization requires explicit CI opt-in",
        )
    try:
        temp_root = Path(tempfile.gettempdir()).resolve(strict=True)
        root_abs = Path(os.path.abspath(os.fspath(root)))
        if (
            not root_abs.is_absolute()
            or not root_abs.is_relative_to(temp_root)
            or not root_abs.name.startswith("icode-runtime-staging-")
        ):
            raise _AppContainerSetupError(
                "invalid_diagnostic_probe", "ACL normalization target is not disposable staging",
            )
        before = _read_dacl_state(root_abs, advapi, kernel)
        if before.protected or before.defaulted or not before.present:
            raise _AppContainerSetupError(
                "unsupported_runtime_acl", "staging root DACL cannot be normalized safely",
            )
        if before.control & _SE_DACL_AUTO_INHERITED:
            return 0

        original_acl = ctypes.create_string_buffer(before.dacl)
        _set_dacl(root_abs, ctypes.cast(original_acl, ctypes.c_void_p), advapi)
        after = _read_dacl_state(root_abs, advapi, kernel)
    except _AppContainerSetupError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise _AppContainerSetupError(
            "runtime_acl_normalization_failed", "staging root ACL baseline cannot be normalized safely",
        ) from exc

    control_delta = before.control ^ after.control
    if (
        after.dacl != before.dacl
        or after.revision != before.revision
        or after.present != before.present
        or after.defaulted != before.defaulted
        or after.file_identity != before.file_identity
        or control_delta != _SE_DACL_AUTO_INHERITED
        or not (after.control & _SE_DACL_AUTO_INHERITED)
    ):
        raise _AppContainerSetupError(
            "runtime_acl_normalization_failed",
            f"staging root normalization changed unexpected state (control_delta={control_delta})",
        )
    return control_delta


def _grant_workspace_acl(
    root: Path, sid: ctypes.c_void_p,
) -> tuple[bytes, ctypes.WinDLL, ctypes.WinDLL]:
    paths = _walk_workspace(root)
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)

    class TRUSTEE_W(ctypes.Structure):
        _fields_ = [
            ("pMultipleTrustee", ctypes.c_void_p),
            ("MultipleTrusteeOperation", ctypes.c_int),
            ("TrusteeForm", ctypes.c_int),
            ("TrusteeType", ctypes.c_int),
            ("ptstrName", ctypes.c_void_p),
        ]

    class EXPLICIT_ACCESS_W(ctypes.Structure):
        _fields_ = [
            ("grfAccessPermissions", wintypes.DWORD),
            ("grfAccessMode", ctypes.c_int),
            ("grfInheritance", wintypes.DWORD),
            ("Trustee", TRUSTEE_W),
        ]

    advapi.GetNamedSecurityInfoW.argtypes = [
        wintypes.LPWSTR, ctypes.c_int, wintypes.DWORD, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi.GetNamedSecurityInfoW.restype = wintypes.DWORD
    advapi.GetAclInformation.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.c_int]
    advapi.GetAclInformation.restype = wintypes.BOOL
    advapi.GetSecurityDescriptorControl.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(wintypes.WORD), ctypes.POINTER(wintypes.DWORD),
    ]
    advapi.GetSecurityDescriptorControl.restype = wintypes.BOOL
    advapi.GetSecurityDescriptorDacl.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(wintypes.BOOL),
        ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.BOOL),
    ]
    advapi.GetSecurityDescriptorDacl.restype = wintypes.BOOL
    advapi.SetEntriesInAclW.argtypes = [
        wintypes.ULONG, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi.SetEntriesInAclW.restype = wintypes.DWORD
    advapi.SetNamedSecurityInfoW.argtypes = [
        wintypes.LPWSTR, ctypes.c_int, wintypes.DWORD, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
    ]
    advapi.SetNamedSecurityInfoW.restype = wintypes.DWORD
    advapi.GetAce.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)]
    advapi.GetAce.restype = wintypes.BOOL
    advapi.EqualSid.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    advapi.EqualSid.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p

    # Ensure every existing child can inherit the temporary ACE before mutating the root.
    original_dacl: bytes | None = None
    for path in paths:
        dacl, protected = _read_dacl(path, advapi, kernel)
        if protected:
            raise _AppContainerSetupError(
                "unsupported_workspace_acl", "任务目录含受保护 ACL，拒绝不完整授权",
            )
        if path == root:
            original_dacl = dacl
    if original_dacl is None:
        raise _AppContainerSetupError("workspace_acl_unavailable", "任务目录 ACL 不存在")

    dacl, _ = _read_dacl(root, advapi, kernel)
    old_acl = ctypes.create_string_buffer(dacl)
    explicit = EXPLICIT_ACCESS_W()
    explicit.grfAccessPermissions = _WORKSPACE_ACCESS
    explicit.grfAccessMode = _GRANT_ACCESS
    explicit.grfInheritance = _OBJECT_INHERIT_ACE | _CONTAINER_INHERIT_ACE
    explicit.Trustee = TRUSTEE_W(
        None, 0, _TRUSTEE_IS_SID, _TRUSTEE_IS_UNKNOWN,
        ctypes.cast(sid, ctypes.c_void_p),
    )
    new_acl = ctypes.c_void_p()
    status = advapi.SetEntriesInAclW(
        1, ctypes.byref(explicit), ctypes.cast(old_acl, ctypes.c_void_p),
        ctypes.byref(new_acl),
    )
    if status != 0 or not new_acl.value:
        raise _AppContainerSetupError(
            "workspace_acl_failed", f"SetEntriesInAclW err={int(status)}",
        )
    try:
        _set_dacl(root, new_acl, advapi)
    finally:
        kernel.LocalFree(new_acl)
    return original_dacl, advapi, kernel


def _snapshot_runtime_acl_roots(
    roots: Sequence[Path], *, workspace: Path,
    advapi: ctypes.WinDLL, kernel: ctypes.WinDLL,
) -> _RuntimeAclTransaction:
    """Capture every target DACL/control state before a runtime ACL experiment."""
    validated_roots = _validate_runtime_roots(roots, workspace=workspace)
    started = time.monotonic()
    deadline = started + _MAX_RUNTIME_ACL_SNAPSHOT_SECONDS
    entries: list[_DaclSnapshot] = []
    for root in validated_roots:
        remaining_entries = _MAX_RUNTIME_ACL_OBJECTS - len(entries)
        if remaining_entries < 1:
            raise _AppContainerSetupError(
                "runtime_acl_preflight_too_large", "runtime ACL snapshot exceeds object limit",
            )
        try:
            paths = _walk_workspace(
                root, max_entries=remaining_entries, deadline=deadline,
            )
        except _AppContainerSetupError as exc:
            if exc.error in {
                "runtime_acl_preflight_too_large", "runtime_acl_preflight_too_slow",
            }:
                raise
            raise _AppContainerSetupError(
                "unsupported_runtime_root",
                f"runtime tree preflight rejected: {exc.error}; {exc.detail}",
            ) from exc
        for path in paths:
            try:
                snapshot = _read_dacl_state(path, advapi, kernel)
            except _AppContainerSetupError as exc:
                raise _AppContainerSetupError(
                    "runtime_acl_unavailable", "runtime tree DACL cannot be snapshotted safely",
                ) from exc
            if not snapshot.file_identity[1]:
                raise _AppContainerSetupError(
                    "runtime_acl_unavailable",
                    "runtime object has no stable filesystem identity",
                )
            if snapshot.protected or snapshot.defaulted or not snapshot.present:
                raise _AppContainerSetupError(
                    "unsupported_runtime_acl",
                    "runtime tree contains protected or non-restorable DACL state",
                )
            entries.append(snapshot)
            if time.monotonic() > deadline:
                raise _AppContainerSetupError(
                    "runtime_acl_preflight_too_slow", "runtime ACL snapshot exceeded time limit",
                )
    return _RuntimeAclTransaction(
        roots=validated_roots,
        entries=tuple(entries),
        advapi=advapi,
        kernel=kernel,
        snapshot_duration_ms=int((time.monotonic() - started) * 1000),
    )


def _add_runtime_acl(
    root: Path, sid: ctypes.c_void_p, access: int, original_dacl: bytes,
    advapi: ctypes.WinDLL, kernel: ctypes.WinDLL,
) -> None:
    """Add one inheritable, read-only ACE based on the captured root DACL."""
    class TRUSTEE_W(ctypes.Structure):
        _fields_ = [
            ("pMultipleTrustee", ctypes.c_void_p),
            ("MultipleTrusteeOperation", ctypes.c_int),
            ("TrusteeForm", ctypes.c_int),
            ("TrusteeType", ctypes.c_int),
            ("ptstrName", ctypes.c_void_p),
        ]

    class EXPLICIT_ACCESS_W(ctypes.Structure):
        _fields_ = [
            ("grfAccessPermissions", wintypes.DWORD),
            ("grfAccessMode", ctypes.c_int),
            ("grfInheritance", wintypes.DWORD),
            ("Trustee", TRUSTEE_W),
        ]

    original_acl = ctypes.create_string_buffer(original_dacl)
    explicit = EXPLICIT_ACCESS_W()
    explicit.grfAccessPermissions = access
    explicit.grfAccessMode = _GRANT_ACCESS
    explicit.grfInheritance = _OBJECT_INHERIT_ACE | _CONTAINER_INHERIT_ACE
    explicit.Trustee = TRUSTEE_W(
        None, 0, _TRUSTEE_IS_SID, _TRUSTEE_IS_UNKNOWN,
        ctypes.cast(sid, ctypes.c_void_p),
    )
    new_acl = ctypes.c_void_p()
    status = advapi.SetEntriesInAclW(
        1, ctypes.byref(explicit), ctypes.cast(original_acl, ctypes.c_void_p),
        ctypes.byref(new_acl),
    )
    if status != 0 or not new_acl.value:
        raise _AppContainerSetupError(
            "runtime_acl_failed", f"SetEntriesInAclW err={int(status)}",
        )
    try:
        _set_dacl(root, new_acl, advapi)
    finally:
        kernel.LocalFree(new_acl)


def _grant_runtime_acl_roots(
    transaction: _RuntimeAclTransaction, sid: ctypes.c_void_p,
) -> None:
    """Grant only read/execute to the current Package SID, tracking partial writes."""
    access = _FILE_GENERIC_READ | _FILE_GENERIC_EXECUTE
    for root in transaction.roots:
        root_snapshot = next(
            item for item in transaction.entries if item.path == root
        )
        current = _read_dacl_state(root, transaction.advapi, transaction.kernel)
        if current != root_snapshot or _contains_sid(
            current.dacl, sid, transaction.advapi,
        ):
            raise _AppContainerSetupError(
                "runtime_acl_changed_during_preflight",
                "runtime root DACL changed after its snapshot",
            )
        # Track before the native mutation so finally can restore even when the
        # API reports an error after partially changing the security descriptor.
        transaction.modified_roots.append(root)
        _add_runtime_acl(
            root, sid, access, root_snapshot.dacl,
            transaction.advapi, transaction.kernel,
        )


def _runtime_acl_matches_snapshot(
    transaction: _RuntimeAclTransaction, sid: ctypes.c_void_p,
) -> bool:
    """Compare every original object, DACL byte, control flag and file identity."""
    try:
        for root in transaction.roots:
            actual_paths = _walk_workspace(root)
            expected = {
                item.path: item for item in transaction.entries
                if item.path == root or item.path.is_relative_to(root)
            }
            if set(actual_paths) != set(expected):
                return False
            for path in actual_paths:
                actual = _read_dacl_state(
                    path, transaction.advapi, transaction.kernel,
                )
                before = expected[path]
                if actual != before or _contains_sid(
                    actual.dacl, sid, transaction.advapi,
                ):
                    return False
        return True
    except (OSError, _AppContainerSetupError, ValueError):
        return False


def _restore_runtime_acl_roots(
    transaction: _RuntimeAclTransaction, sid: ctypes.c_void_p,
) -> bool:
    """Restore root DACLs and require exact per-object state before reporting clean."""
    restore_ok = True
    for root in reversed(transaction.modified_roots):
        original = next(item for item in transaction.entries if item.path == root)
        original_acl = ctypes.create_string_buffer(original.dacl)
        try:
            _set_dacl(root, ctypes.cast(original_acl, ctypes.c_void_p), transaction.advapi)
        except Exception:  # noqa: BLE001 - keep restoring other roots, then fail closed
            restore_ok = False
    if not restore_ok:
        return False

    # Inheritable ACE propagation can complete after SetNamedSecurityInfoW returns.
    for attempt in range(21):
        if _runtime_acl_matches_snapshot(transaction, sid):
            transaction.modified_roots.clear()
            return True
        if attempt < 20:
            time.sleep(0.1)
    return False


def _restore_workspace_acl(
    root: Path, original_dacl: bytes, sid: ctypes.c_void_p,
    advapi: ctypes.WinDLL, kernel: ctypes.WinDLL,
) -> bool:
    restored = False
    original_acl = ctypes.create_string_buffer(original_dacl)
    try:
        _set_dacl(root, ctypes.cast(original_acl, ctypes.c_void_p), advapi)
        actual, protected = _read_dacl(root, advapi, kernel)
        if protected or _contains_sid(actual, sid, advapi):
            return False
        # Inheritable ACE removal must reach existing and newly created descendants.
        for path in _walk_workspace(root):
            dacl, child_protected = _read_dacl(path, advapi, kernel)
            if child_protected or _contains_sid(dacl, sid, advapi):
                return False
        restored = True
    except (OSError, _AppContainerSetupError):
        restored = False
    return restored


def run_windows_appcontainer(
    argv: Sequence[str], *, cwd: str | Path, timeout_seconds: int,
    process_limit: int = 8,
    _diagnostic_null_application_name: bool = False,
    _diagnostic_omit_localappdata: bool = False,
    _diagnostic_runtime_acl: bool = False,
    _diagnostic_runtime_roots: Sequence[str | os.PathLike[str]] | None = None,
) -> WindowsJobResult:
    """在无网络能力的 AppContainer + 独立 Job 中运行单条命令。

    此为 R2.3 开发期原生实验，不接自动工单。它临时给 ``cwd`` 的 AppContainer
    Package SID 授权，并提供当前 profile 专属的 LOCALAPPDATA 临时存储；退出后恢复工作区 ACL，
    删除 profile 并核验其私有数据目录不存在。cwd 必须是独立任务工作区，不能是原始仓库。
    runtime ACL 差分仅允许 GitHub Windows runner 当前 Python 或专用 temp staging 树的只读诊断，
    不用于工单命令。
    其它私有启动差分仅允许固定无参数 whoami 探针，不用于任何工单命令。
    """
    if not isinstance(_diagnostic_runtime_acl, bool):
        return WindowsJobResult(False, None, "invalid_diagnostic_probe", True, "诊断 ACL 模式无效")
    diagnostic_acl_opt_in = (
        "ICODE_DIAGNOSTIC_RUNTIME_STAGING"
        if _diagnostic_runtime_roots is not None
        else "ICODE_DIAGNOSTIC_RUNTIME_ACL"
    )
    if _diagnostic_runtime_roots is not None and (
        not _diagnostic_runtime_acl
        or isinstance(_diagnostic_runtime_roots, (str, bytes))
        or not isinstance(_diagnostic_runtime_roots, Sequence)
        or len(_diagnostic_runtime_roots) != 1
    ):
        return WindowsJobResult(
            False, None, "invalid_diagnostic_probe", True,
            "显式 runtime 根仅允许单根 staging ACL 诊断",
        )
    if sys.platform != "win32":
        return WindowsJobResult(False, None, "unsupported_platform", False, "仅适用于 Windows")
    if not argv or not Path(argv[0]).is_absolute() or not Path(argv[0]).is_file():
        return WindowsJobResult(False, None, "invalid_command", False, "命令入口必须是存在的绝对路径")
    if not isinstance(_diagnostic_null_application_name, bool):
        return WindowsJobResult(False, None, "invalid_diagnostic_probe", False, "诊断启动模式无效")
    if not isinstance(_diagnostic_omit_localappdata, bool):
        return WindowsJobResult(False, None, "invalid_diagnostic_probe", False, "诊断启动模式无效")
    if _diagnostic_runtime_acl:
        if os.environ.get(diagnostic_acl_opt_in) != "true":
            return WindowsJobResult(
                False, None, "invalid_diagnostic_probe", False,
                "runtime ACL 差分未显式启用",
            )
        try:
            requested_executable = os.path.normcase(os.path.realpath(argv[0]))
            current_executable = os.path.normcase(os.path.realpath(sys.executable))
        except (OSError, TypeError, ValueError):
            requested_executable = ""
            current_executable = "<unavailable>"
        if (
            os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("RUNNER_OS") != "Windows"
            or (
                _diagnostic_runtime_roots is None
                and requested_executable != current_executable
            )
        ):
            return WindowsJobResult(
                False, None, "invalid_diagnostic_probe", False,
                "runtime ACL 差分仅允许 GitHub Windows runner 的受控诊断 runtime",
            )
    if _diagnostic_omit_localappdata and (
        _diagnostic_null_application_name
        or not _is_fixed_system_whoami_probe(
            argv, os.environ.get("SystemRoot", r"C:\Windows"),
        )
    ):
        return WindowsJobResult(
            False, None, "invalid_diagnostic_probe", False,
            "LOCALAPPDATA 差分仅允许固定 whoami 探针",
        )
    if _diagnostic_null_application_name and not _is_fixed_system_whoami_probe(
        argv, os.environ.get("SystemRoot", r"C:\Windows"),
    ):
        return WindowsJobResult(
            False, None, "invalid_diagnostic_probe", False,
            "NULL lpApplicationName 仅允许固定 whoami 探针",
        )
    if not 1 <= timeout_seconds <= 86400 or not 1 <= process_limit <= 1024:
        return WindowsJobResult(False, None, "invalid_limit", False, "超时或进程上限无效")
    try:
        root = Path(os.path.abspath(os.fspath(cwd)))
        if not root.is_absolute():
            raise OSError("workspace path is not absolute")
        if root.drive.startswith("\\\\"):
            return WindowsJobResult(
                False, None, "invalid_workspace", False,
                "暂不支持网络共享目录作为工单工作区",
            )
        # A reparse point in any ancestor could redirect ACL changes outside the
        # workspace even when the final directory itself is ordinary.
        for component in reversed((root, *root.parents)):
            info = component.lstat()
            if _is_reparse(info):
                return WindowsJobResult(
                    False, None, "invalid_workspace", False,
                    "工作目录路径包含重解析点",
                )
    except OSError:
        return WindowsJobResult(False, None, "invalid_workspace", False, "工作目录不存在")
    try:
        root_info = root.lstat()
    except OSError:
        return WindowsJobResult(False, None, "invalid_workspace", False, "工作目录不存在")
    if not stat.S_ISDIR(root_info.st_mode) or _is_reparse(root_info):
        return WindowsJobResult(False, None, "invalid_workspace", False, "工作目录不存在")

    runtime_acl_roots: tuple[Path, ...] | None = None
    if _diagnostic_runtime_acl:
        if _diagnostic_runtime_roots is None:
            runtime_acl_roots = (Path(sys.prefix), Path(sys.base_prefix))
        else:
            try:
                runtime_acl_roots = _validate_diagnostic_runtime_roots(
                    _diagnostic_runtime_roots, executable=argv[0], workspace=root,
                )
            except _AppContainerSetupError as exc:
                return WindowsJobResult(
                    False, None, exc.error, True, exc.detail,
                )

    try:
        userenv = ctypes.WinDLL("userenv", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        ole32 = ctypes.WinDLL("ole32", use_last_error=True)
    except OSError as exc:
        return WindowsJobResult(
            False, None, "appcontainer_api_unavailable", False,
            f"Win32 API unavailable (err={exc.errno})",
        )
    userenv.CreateAppContainerProfile.argtypes = [
        wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR,
        ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p),
    ]
    userenv.CreateAppContainerProfile.restype = ctypes.c_long
    userenv.DeleteAppContainerProfile.argtypes = [wintypes.LPCWSTR]
    userenv.DeleteAppContainerProfile.restype = ctypes.c_long
    advapi.FreeSid.argtypes = [ctypes.c_void_p]
    advapi.FreeSid.restype = ctypes.c_void_p
    advapi.IsValidSid.argtypes = [ctypes.c_void_p]
    advapi.IsValidSid.restype = wintypes.BOOL
    advapi.GetLengthSid.argtypes = [ctypes.c_void_p]
    advapi.GetLengthSid.restype = wintypes.DWORD

    profile = f"icode-{uuid.uuid4().hex}"
    sid = ctypes.c_void_p()
    profile_created = False
    original_dacl: bytes | None = None
    acl_api: tuple[ctypes.WinDLL, ctypes.WinDLL] | None = None
    main = WindowsJobResult(False, None, "appcontainer_setup_failed", False, "AppContainer 未启动")
    details: list[str] = []
    diagnostics: list[str] = []
    cleanup_ok = True
    # No process has been attempted yet, so Job cleanup is a verified no-op.
    # Before each primary launch, flip this closed; only the returned Job result
    # may reopen it. Unexpected exceptions must not be reported as clean.
    primary_job_cleanup_ok = True
    diagnostic_process_executed = False
    profile_local_app_data: str | None = None
    runtime_acl_transaction: _RuntimeAclTransaction | None = None
    try:
        hr = int(userenv.CreateAppContainerProfile(
            profile, "ICODE task", "Temporary task isolation", None, 0, ctypes.byref(sid),
        ))
        profile_created = hr == 0
        sid_valid = bool(sid.value and advapi.IsValidSid(sid))
        sid_length = int(advapi.GetLengthSid(sid)) if sid_valid else 0
        diagnostics.append(
            f"profile_create_hr=0x{hr & 0xFFFFFFFF:08x} "
            f"sid_present={bool(sid.value)} sid_valid={sid_valid} sid_bytes={sid_length}"
        )
        if hr != 0 or not sid.value:
            raise _AppContainerSetupError(
                "appcontainer_creation_failed", f"CreateAppContainerProfile hr=0x{hr & 0xFFFFFFFF:08x}",
            )
        if not sid_valid or sid_length <= 0:
            raise _AppContainerSetupError(
                "appcontainer_sid_invalid", "CreateAppContainerProfile returned an invalid SID",
            )
        original_dacl, advapi, kernel_for_acl = _grant_workspace_acl(root, sid)
        acl_api = (advapi, kernel_for_acl)
        if _diagnostic_runtime_acl:
            assert runtime_acl_roots is not None
            if _diagnostic_runtime_roots is not None:
                control_delta = _normalize_staged_runtime_acl_baseline(
                    runtime_acl_roots[0], advapi, kernel_for_acl,
                )
                diagnostics.append(
                    "runtime_acl_baseline_normalized=true "
                    f"control_delta={control_delta}"
                )
            runtime_acl_transaction = _snapshot_runtime_acl_roots(
                runtime_acl_roots,
                workspace=root, advapi=advapi, kernel=kernel_for_acl,
            )
            diagnostics.append(
                "runtime_acl_snapshot="
                f"roots:{len(runtime_acl_transaction.roots)},"
                f"objects:{len(runtime_acl_transaction.entries)},"
                f"ms:{runtime_acl_transaction.snapshot_duration_ms}"
            )
            _grant_runtime_acl_roots(runtime_acl_transaction, sid)
            diagnostics.append("runtime_acl_access=read_execute")
        profile_local_app_data = _get_appcontainer_localappdata_path(
            sid, userenv, advapi, kernel, ole32,
        )
        if _diagnostic_omit_localappdata or _diagnostic_null_application_name:
            primary_job_cleanup_ok = False
            baseline = run_windows_job(
                argv, cwd=root, timeout_seconds=timeout_seconds,
                process_limit=process_limit, _appcontainer_sid=int(sid.value),
                _appcontainer_localappdata=(
                    None if _diagnostic_omit_localappdata else profile_local_app_data
                ),
            )
            primary_job_cleanup_ok = baseline.cleanup_ok
            diagnostic_process_executed = baseline.executed
            if not baseline.cleanup_ok:
                main = baseline
                cleanup_ok = False
                raise _AppContainerSetupError(
                    "appcontainer_diagnostic_cleanup_failed",
                    "LOCALAPPDATA 基线启动后的 Job 清理未验证",
                )
            primary_job_cleanup_ok = False
            candidate = run_windows_job(
                argv, cwd=root, timeout_seconds=timeout_seconds,
                process_limit=process_limit, _appcontainer_sid=int(sid.value),
                _appcontainer_localappdata=profile_local_app_data,
                _diagnostic_null_application_name=_diagnostic_null_application_name,
            )
            primary_job_cleanup_ok = candidate.cleanup_ok
            diagnostic_process_executed = diagnostic_process_executed or candidate.executed
            diagnostic_name = (
                "localappdata_ab" if _diagnostic_omit_localappdata else "application_name_ab"
            )
            details.append(
                f"{diagnostic_name}="
                f"baseline:executed:{baseline.executed},exit:{baseline.exit_code},"
                f"error:{baseline.error},baseline_win32_error:{_win32_error_code(baseline.detail)},"
                f"cleanup:{baseline.cleanup_ok};"
                f"candidate:executed:{candidate.executed},exit:{candidate.exit_code},"
                f"error:{candidate.error},candidate_win32_error:{_win32_error_code(candidate.detail)},"
                f"cleanup:{candidate.cleanup_ok}"
            )
            if not candidate.cleanup_ok:
                cleanup_ok = False
            main = candidate
        else:
            primary_job_cleanup_ok = False
            main = run_windows_job(
                argv, cwd=root, timeout_seconds=timeout_seconds,
                process_limit=process_limit, _appcontainer_sid=int(sid.value),
                _appcontainer_localappdata=profile_local_app_data,
                _diagnostic_null_application_name=_diagnostic_null_application_name,
            )
            primary_job_cleanup_ok = main.cleanup_ok
    except _AppContainerSetupError as exc:
        main = WindowsJobResult(
            False, None, exc.error, primary_job_cleanup_ok, exc.detail,
        )
    except OSError as exc:
        main = WindowsJobResult(
            False, None, "appcontainer_setup_failed", primary_job_cleanup_ok,
            f"{type(exc).__name__} err={exc.errno}",
        )
    except Exception as exc:  # noqa: BLE001 - 原生包装异常必须保持 fail-closed
        main = WindowsJobResult(
            False, None, "appcontainer_setup_failed", primary_job_cleanup_ok,
            f"{type(exc).__name__} during native setup",
        )
    finally:
        if runtime_acl_transaction is not None:
            try:
                runtime_acl_restored = _restore_runtime_acl_roots(
                    runtime_acl_transaction, sid,
                )
            except Exception:  # noqa: BLE001 - 不可验证的 runtime DACL 恢复必须 fail closed
                runtime_acl_restored = False
            if not runtime_acl_restored:
                cleanup_ok = False
                details.append("runtime_acl_restore_failed")
            else:
                diagnostics.append("runtime_acl_restore_verified=true")
        if original_dacl is not None and acl_api is not None and sid.value:
            try:
                acl_restored = _restore_workspace_acl(root, original_dacl, sid, *acl_api)
            except Exception:  # noqa: BLE001 - 清理异常不能跳过 profile 删除
                acl_restored = False
            if not acl_restored:
                cleanup_ok = False
                details.append("workspace_acl_restore_failed")
            elif (
                (main.executed or diagnostic_process_executed)
                and main.cleanup_ok and cleanup_ok
            ):
                # Prove the just-used identity no longer has write access to the task directory.
                marker = root / f".icode-appcontainer-revocation-{uuid.uuid4().hex}"
                command = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "cmd.exe"
                try:
                    revoke = run_windows_job(
                        [str(command), "/d", "/c", f'echo denied> "{marker}"'],
                        cwd=root, timeout_seconds=5, process_limit=2,
                        _appcontainer_sid=int(sid.value),
                        _appcontainer_localappdata=profile_local_app_data,
                    )
                except Exception:  # noqa: BLE001 - 未验证撤权就不能报告 clean
                    revoke = WindowsJobResult(False, None, "native_api_failed", False, "撤权自检异常")
                if marker.exists():
                    try:
                        marker.unlink()
                    except OSError:
                        pass
                if not revoke.executed or not revoke.cleanup_ok or marker.exists():
                    cleanup_ok = False
                    details.append("workspace_acl_revocation_unverified")
        if profile_created:
            deleted, delete_detail = _delete_appcontainer_profile(
                profile, userenv, profile_local_app_data,
            )
            if not deleted:
                cleanup_ok = False
                details.append(delete_detail)
        if sid.value:
            try:
                advapi.FreeSid(sid)
            except Exception:  # noqa: BLE001 - SID 释放失败不能中断结果回执
                cleanup_ok = False
                details.append("sid_release_failed")

    final_cleanup_ok = bool(main.cleanup_ok and cleanup_ok)
    error = main.error
    if not final_cleanup_ok:
        error = "cleanup_failed"
    detail = "; ".join(part for part in (main.detail, *diagnostics, *details) if part)
    return WindowsJobResult(
        main.executed, main.exit_code, error, final_cleanup_ok, detail,
    )
