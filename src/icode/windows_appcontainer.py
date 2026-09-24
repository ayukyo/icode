"""R2.3 AppContainer 文件/网络边界实验；不是生产后端 ready 证明。

执行边界包含工单工作区和当前临时 profile 的私有 LOCALAPPDATA。后者允许容器写临时应用数据，
profile 销毁后必须确认该目录已消失；残留或无法核验均作为清理失败处理。
本模块尚未接入自动工单；调用方必须传入独立的任务工作区，而不能传入原始仓库。
"""

from __future__ import annotations

import ctypes
import ntpath
import os
from pathlib import Path
import stat
import sys
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


def _walk_workspace(root: Path) -> list[Path]:
    """拒绝重解析点和硬链接，避免 ACL 沿路径/文件别名扩大到工作区外。"""
    try:
        root_info = root.lstat()
    except OSError as exc:
        raise _AppContainerSetupError("invalid_workspace", "无法检查任务目录") from exc
    if not stat.S_ISDIR(root_info.st_mode) or _is_reparse(root_info):
        raise _AppContainerSetupError("invalid_workspace", "任务目录必须是普通目录")

    paths = [root]
    try:
        for current, directories, files in os.walk(root, topdown=True, followlinks=False):
            current_path = Path(current)
            for name in [*directories, *files]:
                path = current_path / name
                info = path.lstat()
                if _is_reparse(info):
                    raise _AppContainerSetupError(
                        "unsupported_workspace_entry", "任务目录含重解析点，AppContainer 拒绝启动",
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


def _read_dacl(
    path: Path, advapi: ctypes.WinDLL, kernel: ctypes.WinDLL,
) -> tuple[bytes, bool]:
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
        if not dacl.value:
            raise _AppContainerSetupError(
                "workspace_acl_unavailable", "任务目录存在 null DACL，拒绝扩大访问",
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
        return ctypes.string_at(dacl, acl_size), bool(control.value & _SE_DACL_PROTECTED)
    finally:
        if descriptor.value:
            kernel.LocalFree(descriptor)


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
) -> WindowsJobResult:
    """在无网络能力的 AppContainer + 独立 Job 中运行单条命令。

    此为 R2.3 开发期原生实验，不接自动工单。它临时给 ``cwd`` 的 AppContainer
    Package SID 授权，并提供当前 profile 专属的 LOCALAPPDATA 临时存储；退出后恢复工作区 ACL，
    删除 profile 并核验其私有数据目录不存在。cwd 必须是独立任务工作区，不能是原始仓库。
    私有启动差分仅允许无参数的系统 whoami 探针，不用于任何工单命令。
    """
    if sys.platform != "win32":
        return WindowsJobResult(False, None, "unsupported_platform", False, "仅适用于 Windows")
    if not argv or not Path(argv[0]).is_absolute() or not Path(argv[0]).is_file():
        return WindowsJobResult(False, None, "invalid_command", False, "命令入口必须是存在的绝对路径")
    if not isinstance(_diagnostic_null_application_name, bool):
        return WindowsJobResult(False, None, "invalid_diagnostic_probe", False, "诊断启动模式无效")
    if not isinstance(_diagnostic_omit_localappdata, bool):
        return WindowsJobResult(False, None, "invalid_diagnostic_probe", False, "诊断启动模式无效")
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
