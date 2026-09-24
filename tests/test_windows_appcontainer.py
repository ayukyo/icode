"""R2.3 AppContainer 文件/网络边界实验；不是生产后端 ready 证明。"""

from __future__ import annotations

import ctypes
import hashlib
import http.client
import http.server
import json
import os
from pathlib import Path
import subprocess
import sys
import sysconfig
import tempfile
import threading
import time
import unittest
from unittest import mock
from urllib.parse import urlsplit

from icode.windows_appcontainer import (
    _AppContainerSetupError,
    _delete_appcontainer_profile,
    _get_appcontainer_localappdata_path,
)
from icode.windows_appcontainer import _walk_workspace, run_windows_appcontainer
from icode.windows_job import (
    _append_windows_environment_value,
    _build_windows_environment_block,
    WindowsJobResult,
    run_windows_job,
)


class TestWindowsAppContainer(unittest.TestCase):
    def _workflow_notice(self, name: str, detail: str) -> None:
        """Expose only bounded probe outcomes in public Actions annotations."""
        if os.environ.get("GITHUB_ACTIONS") != "true":
            return
        safe_detail = detail[:500].replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::notice title=R2.3 {name}::{safe_detail}", flush=True)

    def _mock_profile_apis(self) -> dict[str, mock.Mock]:
        import ctypes

        apis = {name: mock.Mock() for name in ("userenv", "kernel32", "advapi32", "ole32")}

        def create_profile(*args: object) -> int:
            sid_output = args[-1]
            ctypes.cast(sid_output, ctypes.POINTER(ctypes.c_void_p)).contents.value = 123
            return 0

        apis["userenv"].CreateAppContainerProfile.side_effect = create_profile
        apis["userenv"].DeleteAppContainerProfile.return_value = 0
        apis["advapi32"].IsValidSid.return_value = True
        apis["advapi32"].GetLengthSid.return_value = 12
        return apis

    def test_workspace目录拒绝链接与硬链接(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-paths-") as raw:
            root = Path(raw)
            target = root / "outside.txt"
            target.write_text("outside", encoding="utf-8")
            workspace = root / "task"
            workspace.mkdir()
            try:
                (workspace / "link.txt").symlink_to(target)
            except OSError:
                pass  # Windows without developer mode may deny symlink creation.
            else:
                with self.assertRaises(_AppContainerSetupError):
                    _walk_workspace(workspace)

        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-hardlinks-") as raw:
            root = Path(raw)
            source = root / "outside.txt"
            source.write_text("outside", encoding="utf-8")
            workspace = root / "task"
            workspace.mkdir()
            try:
                os.link(source, workspace / "linked.txt")
            except OSError as exc:
                self.skipTest(f"文件系统不支持硬链接测试：{exc}")
            with self.assertRaises(_AppContainerSetupError):
                _walk_workspace(workspace)

    def test_非_windows平台明确拒绝(self) -> None:
        if sys.platform == "win32":
            self.skipTest("仅用于验证非 Windows 拒绝路径")
        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-unsupported-") as raw:
            result = run_windows_appcontainer(
                [sys.executable, "-V"], cwd=raw, timeout_seconds=2,
            )
        self.assertFalse(result.executed)
        self.assertFalse(result.cleanup_ok)
        self.assertEqual(result.error, "unsupported_platform")

    def test_lpApplicationName诊断在AppContainer外层拒绝其它命令(self) -> None:
        executable = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "whoami.exe"
        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-invalid-diagnostic-") as raw, \
             mock.patch("icode.windows_appcontainer.sys.platform", "win32"), \
             mock.patch("icode.windows_appcontainer.Path.is_absolute", return_value=True), \
             mock.patch("icode.windows_appcontainer.Path.is_file", return_value=True), \
             mock.patch("icode.windows_appcontainer.ctypes.WinDLL", create=True) as load_api:
            result = run_windows_appcontainer(
                [str(executable), "/all"], cwd=raw, timeout_seconds=2,
                _diagnostic_null_application_name=True,
            )
        self.assertFalse(result.executed)
        self.assertEqual(result.error, "invalid_diagnostic_probe")
        load_api.assert_not_called()

    def test_容器LOCALAPPDATA通过SID字符串查询并释放Win32内存(self) -> None:
        import ctypes

        sid_text = ctypes.create_unicode_buffer("S-1-15-2-123")
        profile_path = ctypes.create_unicode_buffer(
            r"C:\Users\runner\AppData\Local\Packages\icode\AC",
        )
        advapi = mock.Mock()
        userenv = mock.Mock()
        kernel = mock.Mock()
        ole32 = mock.Mock()

        def convert_sid(sid: object, output: object) -> int:
            self.assertEqual(getattr(sid, "value", sid), 123)
            ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p)).contents.value = (
                ctypes.addressof(sid_text)
            )
            return 1

        def get_appcontainer_path(sid_string: str, output: object) -> int:
            self.assertEqual(sid_string, "S-1-15-2-123")
            ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p)).contents.value = (
                ctypes.addressof(profile_path)
            )
            return 0

        advapi.ConvertSidToStringSidW.side_effect = convert_sid
        userenv.GetAppContainerFolderPath.side_effect = get_appcontainer_path
        kernel.LocalFree.return_value = None
        with mock.patch("icode.windows_appcontainer.sys.platform", "win32"):
            path = _get_appcontainer_localappdata_path(
                ctypes.c_void_p(123), userenv, advapi, kernel, ole32,
            )

        self.assertEqual(path, r"C:\Users\runner\AppData\Local\Packages\icode\AC")
        kernel.LocalFree.assert_called_once()
        ole32.CoTaskMemFree.assert_called_once()

    def test_容器LOCALAPPDATA查询失败时释放SID且不猜路径(self) -> None:
        import ctypes

        sid_text = ctypes.create_unicode_buffer("S-1-15-2-123")
        advapi = mock.Mock()
        userenv = mock.Mock()
        kernel = mock.Mock()
        ole32 = mock.Mock()

        def convert_sid(sid: object, output: object) -> int:
            ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p)).contents.value = (
                ctypes.addressof(sid_text)
            )
            return 1

        advapi.ConvertSidToStringSidW.side_effect = convert_sid
        userenv.GetAppContainerFolderPath.return_value = 0x80004005
        kernel.LocalFree.return_value = None
        with self.assertRaises(_AppContainerSetupError), \
             mock.patch("icode.windows_appcontainer.sys.platform", "win32"):
            _get_appcontainer_localappdata_path(
                ctypes.c_void_p(123), userenv, advapi, kernel, ole32,
            )
        kernel.LocalFree.assert_called_once()
        ole32.CoTaskMemFree.assert_not_called()

    def test_profile删除按官方约定重试并确认profile数据目录消失(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-profile-delete-") as raw:
            profile_path = Path(raw) / "AC"
            profile_path.mkdir()
            userenv = mock.Mock()

            def delete_profile(_profile: str) -> int:
                if userenv.DeleteAppContainerProfile.call_count == 2:
                    profile_path.rmdir()
                return 0

            userenv.DeleteAppContainerProfile.side_effect = delete_profile
            deleted, detail = _delete_appcontainer_profile(
                "icode-test", userenv, str(profile_path),
            )

        self.assertTrue(deleted, detail)
        self.assertEqual(detail, "")
        self.assertEqual(userenv.DeleteAppContainerProfile.call_count, 2)

    def test_profile数据目录残留时删除验证失败(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-profile-residue-") as raw:
            profile_path = Path(raw) / "AC"
            profile_path.mkdir()
            userenv = mock.Mock()
            userenv.DeleteAppContainerProfile.return_value = 0

            deleted, detail = _delete_appcontainer_profile(
                "icode-test", userenv, str(profile_path),
            )

        self.assertFalse(deleted)
        self.assertEqual(detail, "profile_storage_residual")
        self.assertEqual(userenv.DeleteAppContainerProfile.call_count, 2)

    def test_profile删除API连续失败时即使数据目录缺失也不报成功(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-profile-delete-error-") as raw:
            absent_path = Path(raw) / "already-missing"
            userenv = mock.Mock()
            userenv.DeleteAppContainerProfile.return_value = 0x80004005

            deleted, detail = _delete_appcontainer_profile(
                "icode-test", userenv, str(absent_path),
            )

        self.assertFalse(deleted)
        self.assertEqual(detail, "profile_delete_failed:0x80004005")
        self.assertEqual(userenv.DeleteAppContainerProfile.call_count, 2)

    def test_容器路径查询失败时不启动命令且保留准确清理结果(self) -> None:
        apis = self._mock_profile_apis()
        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-path-failure-") as raw, \
             mock.patch("icode.windows_appcontainer.sys.platform", "win32"), \
             mock.patch(
                 "icode.windows_appcontainer.ctypes.WinDLL",
                 create=True,
                 side_effect=lambda name, **_kwargs: apis[name],
             ), \
             mock.patch(
                 "icode.windows_appcontainer._grant_workspace_acl",
                 return_value=(b"original-dacl", apis["advapi32"], apis["kernel32"]),
             ), \
             mock.patch(
                 "icode.windows_appcontainer._get_appcontainer_localappdata_path",
                 side_effect=_AppContainerSetupError(
                     "appcontainer_profile_path_failed", "profile path unavailable",
                 ),
             ), \
             mock.patch("icode.windows_appcontainer._restore_workspace_acl", return_value=True), \
             mock.patch("icode.windows_appcontainer.run_windows_job") as run_job:
            result = run_windows_appcontainer(
                [sys.executable, "-c", "pass"], cwd=raw, timeout_seconds=2,
            )

        self.assertFalse(result.executed)
        self.assertEqual(result.error, "appcontainer_profile_path_failed")
        self.assertTrue(result.cleanup_ok)
        run_job.assert_not_called()
        apis["userenv"].DeleteAppContainerProfile.assert_called_once()
        apis["advapi32"].FreeSid.assert_called_once()

    def test_容器正常启动和撤权探针都只收到当前profile路径(self) -> None:
        profile_path = r"C:\Users\runner\AppData\Local\Packages\icode\AC"
        apis = self._mock_profile_apis()
        job_result = WindowsJobResult(True, 0, None, True, "")
        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-profile-path-") as raw, \
             mock.patch("icode.windows_appcontainer.sys.platform", "win32"), \
             mock.patch(
                 "icode.windows_appcontainer.ctypes.WinDLL",
                 create=True,
                 side_effect=lambda name, **_kwargs: apis[name],
             ), \
             mock.patch(
                 "icode.windows_appcontainer._grant_workspace_acl",
                 return_value=(b"original-dacl", apis["advapi32"], apis["kernel32"]),
             ), \
             mock.patch(
                 "icode.windows_appcontainer._get_appcontainer_localappdata_path",
                 return_value=profile_path,
             ), \
             mock.patch("icode.windows_appcontainer._restore_workspace_acl", return_value=True), \
             mock.patch(
                 "icode.windows_appcontainer.run_windows_job", return_value=job_result,
             ) as run_job:
            result = run_windows_appcontainer(
                [sys.executable, "-c", "pass"], cwd=raw, timeout_seconds=2,
            )

        self.assertTrue(result.executed)
        self.assertTrue(result.cleanup_ok)
        self.assertEqual(run_job.call_count, 2, "主命令和 ACL 撤权探针都应在同一容器中运行")
        for call in run_job.call_args_list:
            self.assertEqual(call.kwargs["_appcontainer_sid"], 123)
            self.assertEqual(call.kwargs["_appcontainer_localappdata"], profile_path)

    @unittest.skipUnless(sys.platform == "win32", "需 Windows AppContainer 原生实测")
    def test_profile专属目录可写且进程退出后删除(self) -> None:
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        command = system_root / "System32" / "cmd.exe"
        profile_paths: list[str] = []
        profile_directory_exists_before_launch: list[bool] = []
        marker_present_before_delete: list[bool] = []
        marker_name = "icode-profile-lifecycle-probe.txt"
        delete_profile = _delete_appcontainer_profile

        def get_profile_path(
            sid: ctypes.c_void_p,
            userenv: ctypes.WinDLL,
            advapi: ctypes.WinDLL,
            kernel: ctypes.WinDLL,
            ole32: ctypes.WinDLL,
        ) -> str:
            path = _get_appcontainer_localappdata_path(
                sid, userenv, advapi, kernel, ole32,
            )
            profile_paths.append(path)
            profile_directory_exists_before_launch.append(Path(path).is_dir())
            return path

        def observe_profile_delete(
            profile: str, userenv: ctypes.WinDLL, localappdata: str | None,
        ) -> tuple[bool, str]:
            marker_path = Path(localappdata or "") / marker_name
            marker_present_before_delete.append(marker_path.is_file())
            return delete_profile(profile, userenv, localappdata)

        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-profile-lifecycle-") as raw:
            workspace = Path(raw) / "task"
            workspace.mkdir()
            script = workspace / "profile-write.cmd"
            profile_env_state = workspace / "profile-env-state.txt"
            profile_directory_state = workspace / "profile-directory-state.txt"
            profile_write_status = workspace / "profile-write-status.txt"
            profile_write_stderr = workspace / "profile-write-stderr.txt"
            script.write_text(
                "@echo off\r\n"
                f'if defined LOCALAPPDATA (echo defined> "{profile_env_state.name}") '
                f'else (echo missing> "{profile_env_state.name}")\r\n'
                f'if exist "%LOCALAPPDATA%\\." (echo exists> "{profile_directory_state.name}") '
                f'else (echo missing> "{profile_directory_state.name}")\r\n'
                f'(echo profile-write-ok> "%LOCALAPPDATA%\\{marker_name}") '
                f'2> "{profile_write_stderr.name}"\r\n'
                f'echo %errorlevel%> "{profile_write_status.name}"\r\n',
                encoding="utf-8",
            )
            with mock.patch(
                "icode.windows_appcontainer._get_appcontainer_localappdata_path",
                side_effect=get_profile_path,
            ), mock.patch(
                "icode.windows_appcontainer._delete_appcontainer_profile",
                side_effect=observe_profile_delete,
            ):
                result = run_windows_appcontainer(
                    [str(command), "/d", "/c", f".\\{script.name}"],
                    cwd=workspace, timeout_seconds=8, process_limit=2,
                )

        try:
            profile_write_error = profile_write_stderr.read_text(
                encoding="utf-8", errors="replace",
            ).casefold()
        except OSError:
            profile_write_error = ""
        if "access is denied" in profile_write_error or "access denied" in profile_write_error:
            profile_write_error_class = "access_denied"
        elif "path not found" in profile_write_error or "cannot find the path" in profile_write_error:
            profile_write_error_class = "path_not_found"
        elif "file not found" in profile_write_error or "cannot find the file" in profile_write_error:
            profile_write_error_class = "file_not_found"
        elif profile_write_error:
            profile_write_error_class = "other_write_error"
        else:
            profile_write_error_class = "no_stderr"
        try:
            profile_write_status_value = int(profile_write_status.read_text(encoding="ascii").strip())
        except (OSError, ValueError):
            profile_write_status_value = None
        profile_env_defined = (
            profile_env_state.is_file()
            and profile_env_state.read_text(encoding="utf-8").strip() == "defined"
        )
        profile_directory_visible = (
            profile_directory_state.is_file()
            and profile_directory_state.read_text(encoding="utf-8").strip() == "exists"
        )

        self._workflow_notice(
            "profile storage lifecycle",
            f"executed={result.executed} exit={result.exit_code} error={result.error} "
            f"cleanup={result.cleanup_ok} localappdata_defined={profile_env_defined} "
            f"profile_dir_before_launch={profile_directory_exists_before_launch} "
            f"profile_dir_visible={profile_directory_visible} "
            f"write_status={profile_write_status_value} "
            f"write_error_class={profile_write_error_class} "
            f"marker_before_delete={marker_present_before_delete}",
        )
        self.assertTrue(result.executed, result)
        self.assertEqual(result.exit_code, 0, result)
        self.assertTrue(result.cleanup_ok, result)
        self.assertEqual(len(profile_paths), 1)
        self.assertEqual(marker_present_before_delete, [True])
        self.assertFalse(
            Path(profile_paths[0]).exists(),
            "profile storage must be removed when the AppContainer job ends",
        )

    def test_LOCALAPPDATA诊断在AppContainer外层拒绝用户命令(self) -> None:
        executable = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "whoami.exe"
        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-invalid-localappdata-") as raw, \
             mock.patch("icode.windows_appcontainer.sys.platform", "win32"), \
             mock.patch("icode.windows_appcontainer.Path.is_absolute", return_value=True), \
             mock.patch("icode.windows_appcontainer.Path.is_file", return_value=True), \
             mock.patch("icode.windows_appcontainer.ctypes.WinDLL", create=True) as load_api:
            result = run_windows_appcontainer(
                [str(executable), "/all"], cwd=raw, timeout_seconds=2,
                _diagnostic_omit_localappdata=True,
            )
        self.assertFalse(result.executed)
        self.assertEqual(result.error, "invalid_diagnostic_probe")
        load_api.assert_not_called()

    def test_省略LOCALAPPDATA差分不能与app_name差分叠加(self) -> None:
        executable = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "whoami.exe"
        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-overlapping-diagnostics-") as raw, \
             mock.patch("icode.windows_appcontainer.sys.platform", "win32"), \
             mock.patch("icode.windows_appcontainer.Path.is_absolute", return_value=True), \
             mock.patch("icode.windows_appcontainer.Path.is_file", return_value=True), \
             mock.patch("icode.windows_appcontainer.ctypes.WinDLL", create=True) as load_api:
            result = run_windows_appcontainer(
                [str(executable)], cwd=raw, timeout_seconds=2,
                _diagnostic_omit_localappdata=True,
                _diagnostic_null_application_name=True,
            )
        self.assertFalse(result.executed)
        self.assertEqual(result.error, "invalid_diagnostic_probe")
        load_api.assert_not_called()

    @unittest.skipUnless(sys.platform == "win32", "需 Windows AppContainer 原生实测")
    def test_诊断仅LOCALAPPDATA最小环境块下的系统程序启动(self) -> None:
        """The wrapper adds only its profile path to this intentionally empty base block."""
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        executable = system_root / "System32" / "whoami.exe"
        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-empty-env-") as raw:
            workspace = Path(raw) / "task"
            workspace.mkdir()
            safe_environment = _build_windows_environment_block(
                executable, workspace, system_root,
            )
            # The base block is intentionally empty; the wrapper adds only its profile path.
            # Never pass lpEnvironment=None, which would copy arbitrary runner variables.
            with mock.patch(
                "icode.windows_job._build_windows_environment_block",
                side_effect=("\0\0", safe_environment),
            ):
                result = run_windows_appcontainer(
                    [str(executable)], cwd=workspace, timeout_seconds=10, process_limit=2,
                )
            self._workflow_notice(
                "minimal base environment plus profile LOCALAPPDATA",
                f"executed={result.executed} exit={result.exit_code} error={result.error} "
                f"cleanup={result.cleanup_ok} detail={result.detail}",
            )
            self.assertTrue(result.executed, result)
            self.assertEqual(result.exit_code, 0, result)
            self.assertTrue(result.cleanup_ok, result)

    @unittest.skipUnless(sys.platform == "win32", "需 Windows AppContainer 原生实测")
    def test_AppContainer环境块仅比普通Job多容器LOCALAPPDATA(self) -> None:
        """AppContainer receives its own profile path, never the host profile variable."""
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        executable = system_root / "System32" / "whoami.exe"
        target_executable = os.path.normcase(str(executable))
        observed_blocks: list[str] = []
        appcontainer_blocks: list[str] = []
        append_environment_value = _append_windows_environment_value
        observed_metadata: list[str] = []

        def build_and_observe(
            executable_path: str | os.PathLike[str],
            cwd: str | os.PathLike[str],
            system_root_path: str | os.PathLike[str],
        ) -> str:
            block = _build_windows_environment_block(
                executable_path, cwd, system_root_path,
            )
            if os.path.normcase(os.fspath(executable_path)) == target_executable:
                observed_blocks.append(block)
                entries = [entry for entry in block.split("\0") if entry]
                names = [
                    entry[:entry.index("=", 1)] if entry.startswith("=")
                    else entry.split("=", 1)[0]
                    for entry in entries
                ]
                observed_metadata.append(
                    f"chars={len(block)} utf16_bytes={len(block.encode('utf-16-le'))} "
                    f"nul_chars={block.count(chr(0))} names={names} "
                    f"sha256={hashlib.sha256(block.encode('utf-16-le')).hexdigest()}"
                )
            return block

        def append_and_observe(block: str, name: str, value: str) -> str:
            result = append_environment_value(block, name, value)
            if name.casefold() == "localappdata":
                appcontainer_blocks.append(result)
            return result

        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-matched-env-") as raw:
            workspace = Path(raw) / "task"
            workspace.mkdir()
            with mock.patch(
                "icode.windows_job._build_windows_environment_block",
                side_effect=build_and_observe,
            ), mock.patch(
                "icode.windows_job._append_windows_environment_value",
                side_effect=append_and_observe,
            ):
                ordinary = run_windows_job(
                    [str(executable)], cwd=workspace, timeout_seconds=10,
                )
                appcontainer = run_windows_appcontainer(
                    [str(executable)], cwd=workspace, timeout_seconds=10,
                    process_limit=2,
                )

        self._workflow_notice(
            "AppContainer profile LOCALAPPDATA environment control",
            f"ordinary=executed:{ordinary.executed},exit:{ordinary.exit_code},"
            f"error:{ordinary.error},cleanup:{ordinary.cleanup_ok}; "
            f"appcontainer=executed:{appcontainer.executed},exit:{appcontainer.exit_code},"
            f"error:{appcontainer.error},cleanup:{appcontainer.cleanup_ok},"
            f"detail:{appcontainer.detail}; captured_blocks={len(observed_blocks)} "
            f"metadata={observed_metadata[:2]}",
        )

        self.assertTrue(ordinary.executed, ordinary)
        self.assertEqual(ordinary.exit_code, 0, ordinary)
        self.assertTrue(ordinary.cleanup_ok, ordinary)
        self.assertGreaterEqual(len(observed_blocks), 2, "both primary launches must build an environment")
        def parse(block: str) -> dict[str, str]:
            entries: dict[str, str] = {}
            for entry in block.split("\0"):
                if not entry:
                    continue
                separator = entry.index("=", 1) if entry.startswith("=") else entry.index("=")
                entries[entry[:separator]] = entry[separator + 1:]
            return entries

        ordinary_entries, appcontainer_base_entries = map(parse, observed_blocks[:2])
        self.assertEqual(observed_blocks[0], observed_blocks[1])
        self.assertEqual(appcontainer_base_entries, ordinary_entries)
        self.assertEqual(
            len(appcontainer_blocks), 2,
            "the AppContainer main command and ACL-revocation probe both use its profile variable",
        )
        appcontainer_entries = parse(appcontainer_blocks[0])
        self.assertNotIn("LOCALAPPDATA", ordinary_entries)
        self.assertIn("LOCALAPPDATA", appcontainer_entries)
        self.assertTrue(Path(appcontainer_entries["LOCALAPPDATA"]).is_absolute())
        self.assertEqual(
            [parse(block)["LOCALAPPDATA"] for block in appcontainer_blocks],
            [appcontainer_entries["LOCALAPPDATA"]] * len(appcontainer_blocks),
        )
        self.assertEqual(
            {key: value for key, value in appcontainer_entries.items() if key != "LOCALAPPDATA"},
            ordinary_entries,
        )
        self.assertTrue(appcontainer.executed, appcontainer)
        self.assertEqual(appcontainer.exit_code, 0, appcontainer)
        self.assertTrue(appcontainer.cleanup_ok, appcontainer)

    @unittest.skipUnless(sys.platform == "win32", "需 Windows AppContainer 原生实测")
    def test_诊断lpApplicationName显式路径与NULL差分(self) -> None:
        """Compare only lpApplicationName while keeping the suspended Job path intact."""
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        executable = system_root / "System32" / "whoami.exe"
        target_executable = os.path.normcase(str(executable))
        observed_blocks: list[str] = []
        appcontainer_blocks: list[str] = []
        append_environment_value = _append_windows_environment_value

        def build_and_observe(
            executable_path: str | os.PathLike[str],
            cwd: str | os.PathLike[str],
            system_root_path: str | os.PathLike[str],
        ) -> str:
            block = _build_windows_environment_block(
                executable_path, cwd, system_root_path,
            )
            if os.path.normcase(os.fspath(executable_path)) == target_executable:
                observed_blocks.append(block)
            return block

        def append_and_observe(block: str, name: str, value: str) -> str:
            result = append_environment_value(block, name, value)
            if name.casefold() == "localappdata":
                appcontainer_blocks.append(result)
            return result

        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-lpappname-") as raw:
            workspace = Path(raw) / "task"
            workspace.mkdir()
            with mock.patch(
                "icode.windows_job._build_windows_environment_block",
                side_effect=build_and_observe,
            ), mock.patch(
                "icode.windows_job._append_windows_environment_value",
                side_effect=append_and_observe,
            ):
                null_application_name = run_windows_appcontainer(
                    [str(executable)], cwd=workspace, timeout_seconds=10,
                    process_limit=2, _diagnostic_null_application_name=True,
                )

        env_equal = len(observed_blocks) == 2 and observed_blocks[0] == observed_blocks[1]
        self._workflow_notice(
            "lpApplicationName A/B diagnostic",
            f"candidate=executed:{null_application_name.executed},"
            f"exit:{null_application_name.exit_code},error:{null_application_name.error},"
            f"cleanup:{null_application_name.cleanup_ok}; environment_blocks="
            f"{len(observed_blocks)},equal:{env_equal}; "
            f"ab:{null_application_name.detail.partition('application_name_ab=')[2]}",
        )
        self.assertGreaterEqual(len(observed_blocks), 2, "both launches must reach environment setup")
        self.assertEqual(observed_blocks[0], observed_blocks[1])
        self.assertEqual(
            len(appcontainer_blocks), 3,
            "the A/B launches and ACL-revocation probe each use the same profile variable",
        )
        self.assertEqual(appcontainer_blocks[0], appcontainer_blocks[1])

        def profile_localappdata_value(block: str) -> str:
            entries = [
                entry for entry in block.split("\0") if entry
                and entry[:entry.index("=", 1)].casefold() == "localappdata"
            ]
            self.assertEqual(len(entries), 1, "final AppContainer block must contain one profile path")
            return entries[0].split("=", 1)[1]

        localappdata_values = [
            profile_localappdata_value(block) for block in appcontainer_blocks
        ]
        self.assertEqual(localappdata_values[1:], [localappdata_values[0]] * 2)
        self.assertTrue(null_application_name.executed, null_application_name)
        self.assertEqual(null_application_name.exit_code, 0, null_application_name)
        self.assertTrue(null_application_name.cleanup_ok, null_application_name)
        app_name_ab = null_application_name.detail.partition("application_name_ab=")[2]
        self.assertIn("baseline:executed:True,exit:0", app_name_ab)
        self.assertIn("candidate:executed:True,exit:0", app_name_ab)

    @unittest.skipUnless(sys.platform == "win32", "需 Windows AppContainer 原生实测")
    def test_诊断同一profile仅追加LOCALAPPDATA差分(self) -> None:
        """Keep profile SID and launch inputs fixed while adding its official local-data path."""
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        executable = system_root / "System32" / "whoami.exe"
        target_executable = os.path.normcase(str(executable))
        observed_blocks: list[str] = []
        appcontainer_blocks: list[str] = []
        append_environment_value = _append_windows_environment_value

        def build_and_observe(
            executable_path: str | os.PathLike[str],
            cwd: str | os.PathLike[str],
            system_root_path: str | os.PathLike[str],
        ) -> str:
            block = _build_windows_environment_block(
                executable_path, cwd, system_root_path,
            )
            if os.path.normcase(os.fspath(executable_path)) == target_executable:
                observed_blocks.append(block)
            return block

        def append_and_observe(block: str, name: str, value: str) -> str:
            result = append_environment_value(block, name, value)
            if name.casefold() == "localappdata":
                appcontainer_blocks.append(result)
            return result

        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-localappdata-") as raw:
            workspace = Path(raw) / "task"
            workspace.mkdir()
            with mock.patch(
                "icode.windows_job._build_windows_environment_block",
                side_effect=build_and_observe,
            ), mock.patch(
                "icode.windows_job._append_windows_environment_value",
                side_effect=append_and_observe,
            ):
                candidate = run_windows_appcontainer(
                    [str(executable)], cwd=workspace, timeout_seconds=10,
                    process_limit=2, _diagnostic_omit_localappdata=True,
                )

        ab_summary = candidate.detail.partition("localappdata_ab=")[2]
        self._workflow_notice(
            "same-profile LOCALAPPDATA A/B diagnostic",
            f"candidate=executed:{candidate.executed},exit:{candidate.exit_code},"
            f"error:{candidate.error},cleanup:{candidate.cleanup_ok}; "
            f"ab={ab_summary}; captured_blocks={len(observed_blocks)}",
        )
        self.assertEqual(len(observed_blocks), 2, "baseline and candidate must both launch")
        self.assertIn("baseline:executed:False", ab_summary)
        self.assertIn("baseline_win32_error:203", ab_summary)
        self.assertIn("candidate:executed:True,exit:0", ab_summary)

        def parse(block: str) -> dict[str, str]:
            entries: dict[str, str] = {}
            for entry in block.split("\0"):
                if not entry:
                    continue
                separator = entry.index("=", 1) if entry.startswith("=") else entry.index("=")
                entries[entry[:separator]] = entry[separator + 1:]
            return entries

        baseline_entries, candidate_base_entries = map(parse, observed_blocks)
        self.assertEqual(observed_blocks[0], observed_blocks[1])
        self.assertEqual(candidate_base_entries, baseline_entries)
        self.assertEqual(
            len(appcontainer_blocks), 2,
            "the A/B candidate and ACL-revocation probe use the profile variable",
        )
        candidate_entries = parse(appcontainer_blocks[0])
        self.assertNotIn("LOCALAPPDATA", baseline_entries)
        self.assertIn("LOCALAPPDATA", candidate_entries)
        self.assertEqual(
            parse(appcontainer_blocks[1])["LOCALAPPDATA"],
            candidate_entries["LOCALAPPDATA"],
        )
        self.assertEqual(
            {key: value for key, value in candidate_entries.items() if key != "LOCALAPPDATA"},
            baseline_entries,
        )
        self.assertTrue(candidate.executed, candidate)
        self.assertEqual(candidate.exit_code, 0, candidate)
        self.assertTrue(candidate.cleanup_ok, candidate)

    @unittest.skipUnless(sys.platform == "win32", "需 Windows AppContainer 原生实测")
    def test_诊断容器对宿主Python运行时文件的直接读取(self) -> None:
        """Distinguish runtime DACL access from a missing or misplaced dependency."""
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        command = system_root / "System32" / "cmd.exe"
        executable = Path(sys.executable)
        stdlib = Path(sysconfig.get_path("stdlib"))
        version = f"{sys.version_info.major}{sys.version_info.minor}"
        dll_name = sysconfig.get_config_var("DLLLIBRARY") or f"python{version}.dll"
        candidates = [
            ("system32_control", system_root / "System32" / "whoami.exe"),
            ("python_executable", executable),
            ("python_shared_library", executable.parent / dll_name),
            ("stdlib_pathlib", stdlib / "pathlib.py"),
            ("stdlib_encodings", stdlib / "encodings" / "__init__.py"),
            ("stdlib_archive", executable.parent / f"python{version}.zip"),
        ]
        runtime_files = [(label, path) for label, path in candidates if path.is_file()]
        self.assertGreaterEqual(
            len(runtime_files), 4,
            "Windows CI runtime layout changed; direct-read diagnostic lacks enough samples",
        )
        results: list[dict[str, object]] = []

        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-runtime-access-") as raw:
            workspace = Path(raw) / "task"
            workspace.mkdir()
            copy_script = workspace / "copy-runtime.cmd"
            copy_started = workspace / "copy-runtime-started.txt"
            for index, (label, source) in enumerate(runtime_files):
                destination_name = f"runtime-copy-{index}.bin"
                destination = workspace / destination_name
                copy_message = workspace / f"runtime-copy-{index}.message.txt"
                copy_started.unlink(missing_ok=True)
                copy_message.unlink(missing_ok=True)
                copy_script.write_text(
                    f'@echo off\r\necho started> "{copy_started.name}"\r\n'
                    f'copy /b "{source}" "{destination_name}" '
                    f'> "{copy_message.name}" 2>&1\r\n',
                    encoding="utf-8",
                )
                # The Package SID is granted the task directory, not its temp parents.
                result = run_windows_appcontainer(
                    [str(command), "/d", "/c", f".\\{copy_script.name}"],
                    cwd=workspace, timeout_seconds=8, process_limit=2,
                )
                copy_script_started = copy_started.is_file()
                source_size = source.stat().st_size
                copied_size = destination.stat().st_size if destination.is_file() else None
                try:
                    copy_output = copy_message.read_text(
                        encoding="utf-8", errors="replace",
                    ).casefold()
                except OSError:
                    copy_output = ""
                if copied_size == source_size:
                    copy_error_class = "read_ok"
                elif "access is denied" in copy_output or "access denied" in copy_output:
                    copy_error_class = "access_denied"
                elif "cannot find the path" in copy_output or "path not found" in copy_output:
                    copy_error_class = "path_not_found"
                elif "cannot find the file" in copy_output or "file not found" in copy_output:
                    copy_error_class = "file_not_found"
                elif copy_output:
                    copy_error_class = "other_copy_error"
                else:
                    copy_error_class = "no_copy_diagnostic"
                results.append({
                    "label": label,
                    "copy_script_started": copy_script_started,
                    "source_size": source_size,
                    "source_read_match": copied_size == source_size,
                    "copy_error_class": copy_error_class,
                    "executed": result.executed,
                    "exit_code": result.exit_code,
                    "error": result.error,
                    "cleanup_ok": result.cleanup_ok,
                    "copied_size": copied_size,
                })
                self.assertTrue(result.executed, result)
                self.assertIsNone(result.error, result)
                self.assertTrue(result.cleanup_ok, result)

        for result in results:
            self._workflow_notice(
                "Python runtime direct-read diagnostic",
                json.dumps(result, ensure_ascii=True, separators=(",", ":")),
            )
            self.assertTrue(
                result["copy_script_started"],
                "AppContainer did not start the workspace-relative copy script",
            )

    @unittest.skipUnless(sys.platform == "win32", "需 Windows AppContainer 原生实测")
    def test_在AppContainer中运行Python并解析工作路径(self) -> None:
        """Verify the host Python runtime and path behavior, not only System32 tools."""
        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-python-") as raw:
            root = Path(raw).resolve()
            workspace = root / "task"
            workspace.mkdir()
            marker = workspace / "python-probe.json"
            profile_paths: list[str] = []

            def get_profile_path(
                sid: ctypes.c_void_p,
                userenv: ctypes.WinDLL,
                advapi: ctypes.WinDLL,
                kernel: ctypes.WinDLL,
                ole32: ctypes.WinDLL,
            ) -> str:
                path = _get_appcontainer_localappdata_path(
                    sid, userenv, advapi, kernel, ole32,
                )
                profile_paths.append(path)
                return path

            probe = (
                "import json\n"
                "from pathlib import Path\n"
                "import sys\n"
                "import os\n"
                "result = {}\n"
                "for label, value in [('cwd', Path.cwd()), ('executable', Path(sys.executable))]:\n"
                "    try:\n"
                "        result[label] = str(value.resolve(strict=True))\n"
                "    except Exception as exc:\n"
                "        result[label] = f'{type(exc).__name__}: {exc}'\n"
                "profile_marker = Path(os.environ['LOCALAPPDATA']) / 'icode-profile-lifecycle-probe'\n"
                "profile_marker.write_text('temporary', encoding='utf-8')\n"
                f"Path({str(marker)!r}).write_text(json.dumps(result), encoding='utf-8')\n"
            )
            with mock.patch(
                "icode.windows_appcontainer._get_appcontainer_localappdata_path",
                side_effect=get_profile_path,
            ):
                result = run_windows_appcontainer(
                    [sys.executable, "-S", "-c", probe],
                    cwd=workspace, timeout_seconds=15, process_limit=4,
                )
            self._workflow_notice(
                "Python runtime",
                f"executed={result.executed} exit={result.exit_code} error={result.error} "
                f"cleanup={result.cleanup_ok} detail={result.detail}",
            )
            self.assertTrue(result.executed, result)
            self.assertEqual(result.exit_code, 0, result)
            self.assertTrue(result.cleanup_ok, result)
            self.assertTrue(marker.is_file(), "AppContainer Python did not write its workspace marker")
            path_result = marker.read_text(encoding="utf-8")
            self._workflow_notice("Python path resolution", path_result)
            resolved = json.loads(path_result)
            self.assertEqual(set(resolved), {"cwd", "executable"})
            self.assertEqual(len(profile_paths), 1)
            self.assertFalse(
                Path(profile_paths[0]).exists(),
                "容器退出后 profile 私有数据目录必须已删除",
            )
            for label, value in resolved.items():
                self.assertTrue(
                    Path(value).is_absolute(),
                    f"AppContainer could not resolve {label}: {value}",
                )

    @unittest.skipUnless(sys.platform == "win32", "需 Windows AppContainer 原生实测")
    def test_工作区ACL与容器profile隔离且默认拒绝网络(self) -> None:
        requests: list[str] = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - 标准库接口名
                requests.append(self.path)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"host-positive-control")

            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                pass

        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-test-") as raw:
            root = Path(raw).resolve()
            workspace = root / "task"
            workspace.mkdir()
            nested = workspace / "existing" / "nested"
            nested.mkdir(parents=True)
            (nested / "input.txt").write_text("existing-workspace-file", encoding="utf-8")
            outside_secret = root / "outside-secret.txt"
            outside_secret.write_text("must-not-enter-appcontainer", encoding="utf-8")
            outside_write = root / "outside-write.txt"

            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            url = f"http://127.0.0.1:{server.server_port}/probe"
            try:
                # 宿主正向对照：listener 确实可达，沙箱负例才有解释力。
                parsed = urlsplit(url)
                connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=3)
                connection.request("GET", parsed.path)
                response = connection.getresponse()
                self.assertEqual(response.read(), b"host-positive-control")
                connection.close()
                self.assertEqual(requests, ["/probe"])
                requests.clear()
                self._workflow_notice("host loopback positive control", "listener reachable")

                system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
                curl = system_root / "System32" / "curl.exe"
                command = system_root / "System32" / "cmd.exe"
                self.assertTrue(curl.is_file(), "Windows 目标环境需提供系统 curl.exe")
                inline_marker = workspace / "inline-write.txt"
                inline_write = run_windows_appcontainer(
                    [
                        str(command), "/d", "/c",
                        "echo inline-write-ok> inline-write.txt",
                    ],
                    cwd=workspace, timeout_seconds=8, process_limit=2,
                )
                self._workflow_notice(
                    "AppContainer relative cwd write control",
                    f"executed={inline_write.executed} exit={inline_write.exit_code} "
                    f"error={inline_write.error} cleanup={inline_write.cleanup_ok} "
                    f"marker={inline_marker.is_file()}",
                )
                self.assertTrue(inline_write.executed, inline_write)
                self.assertEqual(inline_write.exit_code, 0, inline_write)
                self.assertTrue(inline_write.cleanup_ok, inline_write)
                self.assertEqual(inline_marker.read_text(encoding="utf-8").strip(), "inline-write-ok")

                allowed_write = workspace / "new-output.txt"
                copied_secret = workspace / "outside-copy.txt"
                copied_nested = workspace / "nested-copy.txt"
                child_started = workspace / "child-started.txt"
                child_late = workspace / "child-late.txt"
                child_release = workspace / "child-release.txt"
                child_launch_log = workspace / "child-launch.log"
                script_complete = workspace / "probe-script-complete.txt"
                child_script = workspace / "child.cmd"
                child_script.write_text(
                    "@echo off\r\n"
                    f'echo started> "{child_started.name}"\r\n'
                    ":wait_for_release\r\n"
                    f'if not exist "{child_release.name}" goto wait_for_release\r\n'
                    f'echo late> "{child_late.name}"\r\n',
                    encoding="utf-8",
                )
                # Prove the exact child payload can observe release and write its
                # late marker when it is not under the AppContainer Job.
                host_control = subprocess.Popen(
                    [str(command), "/d", "/c", f".\\{child_script.name}"],
                    cwd=workspace,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                try:
                    deadline = time.monotonic() + 10
                    while (
                        not child_started.is_file()
                        and host_control.poll() is None
                        and time.monotonic() < deadline
                    ):
                        time.sleep(0.05)
                    self.assertTrue(
                        child_started.is_file(),
                        "host positive control did not start the descendant",
                    )
                    child_release.write_text("release", encoding="utf-8")
                    deadline = time.monotonic() + 5
                    while not child_late.is_file() and time.monotonic() < deadline:
                        time.sleep(0.05)
                    self.assertTrue(
                        child_late.is_file(),
                        "host positive control did not write the late marker",
                    )
                    host_control.wait(timeout=5)
                    self.assertEqual(host_control.returncode, 0)
                finally:
                    if not child_release.exists():
                        child_release.write_text("release", encoding="utf-8")
                    try:
                        host_control.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        host_control.kill()
                        host_control.wait(timeout=5)
                self._workflow_notice(
                    "descendant payload positive control",
                    f"started={child_started.is_file()} late_marker={child_late.is_file()} "
                    f"exit={host_control.returncode}",
                )
                child_started.unlink(missing_ok=True)
                child_late.unlink(missing_ok=True)
                child_release.unlink(missing_ok=True)
                script = workspace / "probe.cmd"
                script.write_text(
                    "@echo off\r\n"
                    f'echo workspace-write-ok> "{allowed_write.name}"\r\n'
                    f'type "{os.path.relpath(nested / "input.txt", workspace)}" '
                    f'> "{copied_nested.name}"\r\n'
                    f'type "{os.path.relpath(outside_secret, workspace)}" '
                    f'> "{copied_secret.name}"\r\n'
                    f'echo escape> "{os.path.relpath(outside_write, workspace)}"\r\n'
                    f'"{curl}" --noproxy "*" --connect-timeout 1 --max-time 2 '
                    f'"{url}" > "network.txt" 2>&1\r\n'
                    f'start "" /b cmd.exe /d /c .\\{child_script.name} '
                    f'> "{child_launch_log.name}" 2>&1\r\n'
                    ":wait_for_child\r\n"
                    f'if not exist "{child_started.name}" goto wait_for_child\r\n'
                    f'echo reached-end> "{script_complete.name}"\r\n'
                    "exit /b 0\r\n",
                    encoding="utf-8",
                )
                # Use a cwd-relative entry point so access stays within the task ACL.
                result = run_windows_appcontainer(
                    [str(command), "/d", "/c", f".\\{script.name}"],
                    cwd=workspace, timeout_seconds=12, process_limit=8,
                )
                try:
                    child_launch_output = child_launch_log.read_text(
                        encoding="utf-8", errors="replace",
                    ).casefold()
                except OSError:
                    child_launch_output = ""
                if "access is denied" in child_launch_output or "access denied" in child_launch_output:
                    child_launch_error_class = "access_denied"
                elif "not recognized" in child_launch_output or "cannot find" in child_launch_output:
                    child_launch_error_class = "command_or_script_not_found"
                elif child_launch_output:
                    child_launch_error_class = "other_output"
                else:
                    child_launch_error_class = "no_output"
                self._workflow_notice(
                    "workspace and network probe",
                    f"executed={result.executed} exit={result.exit_code} error={result.error} "
                    f"cleanup={result.cleanup_ok} script_complete={script_complete.is_file()} "
                    f"workspace_write={allowed_write.is_file()} nested_copy={copied_nested.is_file()} "
                    f"outside_write={outside_write.exists()} child_started={child_started.is_file()} "
                    f"child_launch_log={child_launch_log.is_file()} "
                    f"child_launch_error_class={child_launch_error_class} detail={result.detail}",
                )

                self.assertTrue(result.executed, result)
                self.assertIsNone(result.error, result)
                self.assertTrue(result.cleanup_ok, result)
                self.assertTrue(
                    script_complete.is_file(),
                    "AppContainer workspace probe did not reach its completion marker",
                )
                self.assertEqual(result.exit_code, 0, result)
                self.assertEqual(allowed_write.read_text(encoding="utf-8").strip(), "workspace-write-ok")
                self.assertEqual(
                    (nested / "input.txt").read_text(encoding="utf-8"),
                    "existing-workspace-file",
                )
                self.assertEqual(
                    copied_nested.read_text(encoding="utf-8").strip(),
                    "existing-workspace-file",
                )
                self.assertNotIn("must-not-enter-appcontainer", copied_secret.read_text(encoding="utf-8"))
                self.assertFalse(outside_write.exists())
                self.assertEqual(requests, [], "AppContainer unexpectedly reached localhost")
                self.assertTrue(
                    child_started.is_file(),
                    "AppContainer descendant did not start; check the bounded launch diagnostic",
                )
                child_release.write_text("release", encoding="utf-8")
                deadline = time.monotonic() + 5
                while not child_late.is_file() and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertFalse(child_late.exists(), "AppContainer Job left a descendant alive")

                child_started.unlink()
                child_late.unlink(missing_ok=True)
                child_release.unlink(missing_ok=True)
                timeout_script = workspace / "timeout-parent.cmd"
                timeout_script.write_text(
                    "@echo off\r\n"
                    f'start "" /b cmd.exe /d /c .\\{child_script.name}\r\n'
                    ":hold\r\n"
                    "goto hold\r\n",
                    encoding="utf-8",
                )
                timed_out = run_windows_appcontainer(
                    [str(command), "/d", "/c", f".\\{timeout_script.name}"],
                    cwd=workspace, timeout_seconds=2, process_limit=8,
                )
                self._workflow_notice(
                    "timeout cleanup probe",
                    f"executed={timed_out.executed} error={timed_out.error} "
                    f"cleanup={timed_out.cleanup_ok} detail={timed_out.detail}",
                )
                self.assertTrue(timed_out.executed, timed_out)
                self.assertEqual(timed_out.error, "timeout", timed_out)
                self.assertTrue(timed_out.cleanup_ok, timed_out)
                self.assertTrue(child_started.is_file(), "timeout descendant did not start")
                child_release.write_text("release", encoding="utf-8")
                deadline = time.monotonic() + 5
                while not child_late.is_file() and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertFalse(child_late.exists(), "timeout left an AppContainer descendant alive")

                limited_marker = workspace / "process-limit-child.txt"
                limited_parent_attempted = workspace / "process-limit-parent-attempted.txt"
                limited_status = workspace / "process-limit-launch-status.txt"
                limited_child = workspace / "process-limit-child.cmd"
                limited_child.write_text(
                    "@echo off\r\n"
                    f'echo escaped> "{limited_marker.name}"\r\n'
                    "exit /b 0\r\n",
                    encoding="utf-8",
                )
                limited_parent = workspace / "process-limit-parent.cmd"
                limited_parent.write_text(
                    "@echo off\r\n"
                    f'echo attempted> "{limited_parent_attempted.name}"\r\n'
                    f'cmd.exe /d /c .\\{limited_child.name}\r\n'
                    f'echo %errorlevel%> "{limited_status.name}"\r\n'
                    "exit /b 0\r\n",
                    encoding="utf-8",
                )
                limit_control = run_windows_appcontainer(
                    [str(command), "/d", "/c", f".\\{limited_parent.name}"],
                    cwd=workspace, timeout_seconds=5, process_limit=2,
                )
                try:
                    positive_launch_status = int(limited_status.read_text(encoding="ascii").strip())
                except (OSError, ValueError):
                    positive_launch_status = None
                self._workflow_notice(
                    "process limit positive control",
                    f"executed={limit_control.executed} exit={limit_control.exit_code} "
                    f"cleanup={limit_control.cleanup_ok} "
                    f"parent_attempted={limited_parent_attempted.is_file()} "
                    f"child_marker={limited_marker.is_file()} "
                    f"launch_status={positive_launch_status}",
                )
                self.assertTrue(limit_control.executed, limit_control)
                self.assertEqual(limit_control.exit_code, 0, limit_control)
                self.assertTrue(limit_control.cleanup_ok, limit_control)
                self.assertTrue(limited_parent_attempted.is_file(), "parent spawn attempt was not recorded")
                self.assertTrue(
                    limited_marker.is_file(),
                    "the process-limit payload must start without the one-process cap",
                )
                self.assertEqual(positive_launch_status, 0, "positive child launch must succeed")
                limited_marker.unlink()
                limited_parent_attempted.unlink()
                limited_status.unlink(missing_ok=True)
                limited = run_windows_appcontainer(
                    [str(command), "/d", "/c", f".\\{limited_parent.name}"],
                    cwd=workspace, timeout_seconds=5, process_limit=1,
                )
                try:
                    negative_launch_status = int(limited_status.read_text(encoding="ascii").strip())
                except (OSError, ValueError):
                    negative_launch_status = None
                self._workflow_notice(
                    "process limit probe",
                    f"executed={limited.executed} exit={limited.exit_code} error={limited.error} "
                    f"cleanup={limited.cleanup_ok} "
                    f"parent_attempted={limited_parent_attempted.is_file()} "
                    f"child_marker={limited_marker.is_file()} "
                    f"launch_status={negative_launch_status} detail={limited.detail}",
                )
                self.assertTrue(limited.executed, limited)
                self.assertEqual(limited.exit_code, 0, limited)
                self.assertTrue(limited.cleanup_ok, limited)
                self.assertTrue(limited_parent_attempted.is_file(), "parent did not reach child creation")
                self.assertFalse(limited_marker.exists(), "Job active-process limit was not enforced")
                self.assertIsNotNone(negative_launch_status, "child launch result was not recorded")
                self.assertNotEqual(negative_launch_status, 0, "one-process cap must reject child creation")
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
