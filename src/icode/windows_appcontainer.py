"""R2.3 AppContainer 实验入口：仅开放临时工单目录，默认无网络能力。

本模块尚未接入自动工单；调用方必须传入独立的任务工作区，而不能传入原始仓库。
"""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
import stat
import sys
import uuid
from ctypes import wintypes
from typing import Sequence

from .windows_job import WindowsJobResult, run_windows_job


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


class _AppContainerSetupError(RuntimeError):
    def __init__(self, error: str, detail: str) -> None:
        super().__init__(detail)
        self.error = error
        self.detail = detail


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
) -> WindowsJobResult:
    """在无网络能力的 AppContainer + 独立 Job 中运行单条命令。

    此为 R2.3 开发期原生实验，不接自动工单。它临时给 ``cwd`` 的 AppContainer
    Package SID 授权，并在进程退出后恢复 ACL；cwd 必须是独立任务工作区，不能是原始仓库。
    """
    if sys.platform != "win32":
        return WindowsJobResult(False, None, "unsupported_platform", False, "仅适用于 Windows")
    if not argv or not Path(argv[0]).is_absolute() or not Path(argv[0]).is_file():
        return WindowsJobResult(False, None, "invalid_command", False, "命令入口必须是存在的绝对路径")
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

    profile = f"icode-{uuid.uuid4().hex}"
    sid = ctypes.c_void_p()
    profile_created = False
    original_dacl: bytes | None = None
    acl_api: tuple[ctypes.WinDLL, ctypes.WinDLL] | None = None
    main = WindowsJobResult(False, None, "appcontainer_setup_failed", False, "AppContainer 未启动")
    details: list[str] = []
    cleanup_ok = True
    try:
        hr = int(userenv.CreateAppContainerProfile(
            profile, "ICODE task", "Temporary task isolation", None, 0, ctypes.byref(sid),
        ))
        profile_created = hr == 0
        if hr != 0 or not sid.value:
            raise _AppContainerSetupError(
                "appcontainer_creation_failed", f"CreateAppContainerProfile hr=0x{hr & 0xFFFFFFFF:08x}",
            )
        original_dacl, advapi, kernel_for_acl = _grant_workspace_acl(root, sid)
        acl_api = (advapi, kernel_for_acl)
        main = run_windows_job(
            argv, cwd=root, timeout_seconds=timeout_seconds,
            process_limit=process_limit, _appcontainer_sid=int(sid.value),
        )
    except _AppContainerSetupError as exc:
        main = WindowsJobResult(False, None, exc.error, False, exc.detail)
    except OSError as exc:
        main = WindowsJobResult(
            False, None, "appcontainer_setup_failed", False,
            f"{type(exc).__name__} err={exc.errno}",
        )
    except Exception as exc:  # noqa: BLE001 - 原生包装异常必须保持 fail-closed
        main = WindowsJobResult(
            False, None, "appcontainer_setup_failed", False,
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
            elif main.executed:
                # Prove the just-used identity no longer has write access to the task directory.
                marker = root / f".icode-appcontainer-revocation-{uuid.uuid4().hex}"
                command = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "cmd.exe"
                try:
                    revoke = run_windows_job(
                        [str(command), "/d", "/c", f'echo denied> "{marker}"'],
                        cwd=root, timeout_seconds=5, process_limit=2,
                        _appcontainer_sid=int(sid.value),
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
            try:
                hr = int(userenv.DeleteAppContainerProfile(profile))
            except Exception:  # noqa: BLE001 - 资源清理异常必须显式失败
                cleanup_ok = False
                details.append("profile_delete_failed")
            else:
                if hr != 0:
                    cleanup_ok = False
                    details.append(f"profile_delete_failed:0x{hr & 0xFFFFFFFF:08x}")
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
    detail = "; ".join(part for part in (main.detail, *details) if part)
    return WindowsJobResult(
        main.executed, main.exit_code, error, final_cleanup_ok, detail,
    )
