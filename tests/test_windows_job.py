"""R2.3 Windows 工单级 Job Object 原生清理试验。"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest import mock

from tests._support import temp_workspace

from icode.windows_job import (
    WindowsJobResult,
    _allocate_attribute_list_buffer,
    _append_windows_environment_value,
    _build_windows_environment_block,
    _is_fixed_system_whoami_probe,
    probe_windows_job_cleanup,
    run_windows_job,
)


class TestWindowsJob(unittest.TestCase):
    def test_AppContainer属性列表缓冲区有足够大小并按指针对齐(self) -> None:
        import ctypes

        for required_size in (1, 37, 64):
            with self.subTest(required_size=required_size):
                storage, pointer = _allocate_attribute_list_buffer(required_size)
                self.assertGreaterEqual(ctypes.sizeof(storage), required_size)
                self.assertEqual(
                    pointer.value % ctypes.sizeof(ctypes.c_void_p), 0,
                )

    def test_AppContainer属性列表拒绝非正大小(self) -> None:
        for required_size in (0, -1):
            with self.subTest(required_size=required_size):
                with self.assertRaises(ValueError):
                    _allocate_attribute_list_buffer(required_size)

    def test_lpApplicationName诊断仅允许固定whoami绝对路径(self) -> None:
        system_root = r"C:\Windows"
        accepted = (
            [r"C:\Windows\System32\whoami.exe"],
            [r"c:\windows\SYSTEM32\whoami.exe"],
        )
        for argv in accepted:
            with self.subTest(argv=argv):
                self.assertTrue(_is_fixed_system_whoami_probe(argv, system_root))

        rejected = (
            [],
            [r"C:\Windows\System32\whoami.exe", "/all"],
            [r"C:\Windows\System32\cmd.exe"],
            [r"C:\Windows\System32\..\whoami.exe"],
            [r"System32\whoami.exe"],
            [r"D:\Windows\System32\whoami.exe"],
        )
        for argv in rejected:
            with self.subTest(argv=argv):
                self.assertFalse(_is_fixed_system_whoami_probe(argv, system_root))

    def test_lpApplicationName诊断拒绝普通Job和其它可执行文件(self) -> None:
        with temp_workspace() as workspace, \
             mock.patch("icode.windows_job.sys.platform", "win32"), \
             mock.patch("icode.windows_job.Path.is_absolute", return_value=True), \
             mock.patch("icode.windows_job.Path.is_file", return_value=True), \
             mock.patch("ctypes.WinDLL", create=True) as load_api:
            ordinary_job = run_windows_job(
                [r"C:\Windows\System32\whoami.exe"], cwd=workspace,
                timeout_seconds=2, _diagnostic_null_application_name=True,
            )
            other_executable = run_windows_job(
                [sys.executable], cwd=workspace, timeout_seconds=2,
                _appcontainer_sid=123, _diagnostic_null_application_name=True,
            )
        for result in (ordinary_job, other_executable):
            self.assertFalse(result.executed)
            self.assertEqual(result.error, "invalid_diagnostic_probe")
        load_api.assert_not_called()

    def test_lpApplicationName诊断仅将NULL传给固定AppContainer探针(self) -> None:
        import ctypes

        api = mock.Mock()
        api.CreateJobObjectW.return_value = 1
        api.SetInformationJobObject.return_value = 1
        api.UpdateProcThreadAttribute.return_value = 1
        api.CreateProcessW.return_value = 0
        api.CloseHandle.return_value = 1

        def initialize_attribute_list(
            attribute_list: object, count: int, flags: int, size: object,
        ) -> int:
            if attribute_list is None:
                ctypes.cast(size, ctypes.POINTER(ctypes.c_size_t)).contents.value = 64
                return 0
            return 1

        api.InitializeProcThreadAttributeList.side_effect = initialize_attribute_list
        with temp_workspace() as workspace, \
             mock.patch("icode.windows_job.sys.platform", "win32"), \
             mock.patch("icode.windows_job.Path.is_absolute", return_value=True), \
             mock.patch("icode.windows_job.Path.is_file", return_value=True), \
             mock.patch("icode.windows_job.Path.resolve", return_value=Path(r"C:\task")), \
             mock.patch("icode.windows_job.Path.is_dir", return_value=True), \
             mock.patch("ctypes.WinDLL", return_value=api, create=True), \
             mock.patch("ctypes.set_last_error", create=True), \
             mock.patch("ctypes.get_last_error", side_effect=(122, 203), create=True), \
             mock.patch("ctypes.FormatError", return_value="diagnostic failure", create=True):
            result = run_windows_job(
                [r"C:\Windows\System32\whoami.exe"], cwd=workspace,
                timeout_seconds=2, _appcontainer_sid=123,
                _diagnostic_null_application_name=True,
            )

        self.assertEqual(result.error, "native_api_failed")
        self.assertTrue(result.cleanup_ok)
        create_args = api.CreateProcessW.call_args.args
        self.assertIsNone(create_args[0])
        self.assertIn("C:\\Windows\\System32\\whoami.exe", ctypes.wstring_at(create_args[1]))
        self.assertEqual(create_args[5], 0x00080404)

    def test_自定义环境块保留驱动器目录但不继承宿主变量(self) -> None:
        block = _build_windows_environment_block(
            r"D:\Python\python.exe", r"E:\tickets\task-1", r"D:\Windows",
        )
        entries = [entry for entry in block.split("\0") if entry]
        names = [
            entry[:entry.index("=", 1)] if entry.startswith("=")
            else entry.split("=", 1)[0]
            for entry in entries
        ]
        self.assertTrue(block.endswith("\0\0"))
        self.assertEqual(names, sorted(names, key=str.casefold))
        self.assertEqual(entries[0], "=D:=D:\\")
        self.assertEqual(entries[1], r"=E:=E:\tickets\task-1")
        self.assertIn(r"D:\Python;D:\Windows\System32", block)
        self.assertNotIn("OPENAI_API_KEY", block)
        self.assertNotIn("GIT_DIR", block)

    def test_只追加LOCALAPPDATA时其它环境项保持不变(self) -> None:
        baseline = _build_windows_environment_block(
            r"C:\Windows\System32\whoami.exe", r"C:\tickets\task-1", r"C:\Windows",
        )
        candidate = _append_windows_environment_value(
            baseline, "LOCALAPPDATA", r"C:\Users\runner\AppData\Local\Packages\icode\AC",
        )

        def parse(block: str) -> dict[str, str]:
            entries: dict[str, str] = {}
            for entry in block.split("\0"):
                if not entry:
                    continue
                separator = entry.index("=", 1) if entry.startswith("=") else entry.index("=")
                entries[entry[:separator]] = entry[separator + 1:]
            return entries

        baseline_entries = parse(baseline)
        candidate_entries = parse(candidate)
        self.assertNotIn("LOCALAPPDATA", baseline_entries)
        self.assertEqual(
            {key: value for key, value in candidate_entries.items() if key != "LOCALAPPDATA"},
            baseline_entries,
        )
        self.assertEqual(
            candidate_entries["LOCALAPPDATA"],
            r"C:\Users\runner\AppData\Local\Packages\icode\AC",
        )

    def test_AppContainer_LOCALAPPDATA要求有效SID和绝对路径(self) -> None:
        with temp_workspace() as workspace, \
             mock.patch("icode.windows_job.sys.platform", "win32"), \
             mock.patch("icode.windows_job.Path.is_absolute", return_value=True), \
             mock.patch("icode.windows_job.Path.is_file", return_value=True), \
             mock.patch("ctypes.WinDLL", create=True) as load_api:
            ordinary_job = run_windows_job(
                [r"C:\Windows\System32\whoami.exe"], cwd=workspace,
                timeout_seconds=2, _appcontainer_localappdata=r"C:\sandbox\profile",
            )
            relative_profile = run_windows_job(
                [r"C:\Python\python.exe"], cwd=workspace,
                timeout_seconds=2, _appcontainer_sid=123,
                _appcontainer_localappdata="relative-profile",
            )
        for result in (ordinary_job, relative_profile):
            self.assertFalse(result.executed)
            self.assertEqual(result.error, "invalid_diagnostic_probe")
        load_api.assert_not_called()

    @unittest.skipUnless(sys.platform == "win32", "需 Windows Job Object 实测")
    def test_空环境块下普通Job可启动系统程序(self) -> None:
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        executable = system_root / "System32" / "whoami.exe"
        with temp_workspace() as workspace, mock.patch(
            "icode.windows_job._build_windows_environment_block", return_value="\0\0",
        ):
            result = run_windows_job([str(executable)], cwd=workspace, timeout_seconds=10)
        if os.environ.get("GITHUB_ACTIONS") == "true":
            detail = (
                result.detail[:300].replace("%", "%25")
                .replace("\r", "%0D").replace("\n", "%0A")
            )
            print(
                "::notice title=R2.3 ordinary Job empty-environment control::"
                f"executed={result.executed} exit={result.exit_code} error={result.error} "
                f"cleanup={result.cleanup_ok} detail={detail}",
                flush=True,
            )
        self.assertTrue(result.executed, result)
        self.assertEqual(result.exit_code, 0, result)
        self.assertTrue(result.cleanup_ok, result)

    def test_非_windows_不能运行(self) -> None:
        if sys.platform == "win32":
            self.skipTest("仅校验非 Windows 拒绝")
        result = run_windows_job([sys.executable, "-V"], cwd=os.getcwd(), timeout_seconds=2)
        self.assertFalse(result.executed)
        self.assertFalse(result.cleanup_ok)
        probe = probe_windows_job_cleanup()
        self.assertFalse(probe.executed)
        self.assertFalse(probe.passed)

    def test_CreateProcess失败时保留原始错误且不误报清理失败(self) -> None:
        api = mock.Mock()
        api.CreateJobObjectW.return_value = 1
        api.SetInformationJobObject.return_value = 1
        api.CreateProcessW.return_value = 0
        api.CloseHandle.return_value = 1
        with temp_workspace() as workspace, \
             mock.patch("icode.windows_job.sys.platform", "win32"), \
             mock.patch("ctypes.WinDLL", return_value=api, create=True), \
             mock.patch("ctypes.get_last_error", return_value=203, create=True), \
             mock.patch("ctypes.FormatError", return_value="environment missing", create=True):
            result = run_windows_job(
                [sys.executable], cwd=workspace, timeout_seconds=2,
            )
        self.assertFalse(result.executed)
        self.assertEqual(result.error, "native_api_failed")
        self.assertTrue(result.cleanup_ok)
        self.assertIn("err=203", result.detail)
        self.assertEqual(api.CreateProcessW.call_args.args[0], sys.executable)

    def test_AppContainer启动环境保留盘符伪变量(self) -> None:
        import ctypes

        api = mock.Mock()
        api.CreateJobObjectW.return_value = 1
        api.SetInformationJobObject.return_value = 1
        attribute_addresses: list[int] = []

        def initialize_attribute_list(
            attribute_list: object, count: int, flags: int, size: object,
        ) -> int:
            if attribute_list is None:
                ctypes.cast(size, ctypes.POINTER(ctypes.c_size_t)).contents.value = 64
                return 0
            address = ctypes.cast(attribute_list, ctypes.c_void_p).value
            attribute_addresses.append(address or 0)
            return 1

        api.InitializeProcThreadAttributeList.side_effect = initialize_attribute_list
        api.UpdateProcThreadAttribute.return_value = 1
        environment: dict[str, str] = {}

        def fail_create_process(*args: object) -> int:
            block = args[6]
            environment["block"] = ctypes.wstring_at(
                ctypes.addressof(block), len(block),
            )
            return 0

        api.CreateProcessW.side_effect = fail_create_process
        api.CloseHandle.return_value = 1
        with temp_workspace() as workspace, \
             mock.patch("icode.windows_job.Path.resolve", return_value=Path("C:\\task")), \
             mock.patch("icode.windows_job.Path.is_dir", return_value=True), \
             mock.patch("icode.windows_job.sys.platform", "win32"), \
             mock.patch("ctypes.WinDLL", return_value=api, create=True), \
             mock.patch("ctypes.set_last_error", create=True), \
             mock.patch("ctypes.get_last_error", side_effect=(122, 203), create=True), \
             mock.patch("ctypes.FormatError", return_value="environment missing", create=True):
            result = run_windows_job(
                [sys.executable], cwd=workspace, timeout_seconds=2,
                _appcontainer_sid=123,
            )
        self.assertEqual(result.error, "native_api_failed")
        self.assertEqual(len(attribute_addresses), 1)
        self.assertEqual(
            attribute_addresses[0] % ctypes.sizeof(ctypes.c_void_p), 0,
        )
        self.assertIn("attr_size_query_expected=True", result.detail)
        self.assertIn("attr_size_query_error=122", result.detail)
        self.assertIn("attr_init_ok=True", result.detail)
        self.assertIn("security_attribute=0x00020009", result.detail)
        self.assertIn("attr_update_ok=True", result.detail)
        self.assertIn("flags=0x00080404", result.detail)
        entries = [entry for entry in environment["block"].split("\0") if entry]
        self.assertIn(r"=C:=C:\task", entries)
        system_root = os.environ.get("SystemRoot", "C:\\Windows")
        self.assertIn(f"SystemRoot={system_root}", entries)
        self.assertTrue(any(entry.startswith("PATH=") for entry in entries))

    def test_局部自检启动失败不能误报通过(self) -> None:
        failed = WindowsJobResult(False, None, "job_creation_failed", False, "failed")
        with mock.patch("icode.windows_job.sys.platform", "win32"), \
             mock.patch("icode.windows_job.run_windows_job", return_value=failed) as launch:
            probe = probe_windows_job_cleanup()
        self.assertEqual(launch.call_count, 2)
        self.assertTrue(probe.executed)
        self.assertFalse(probe.passed)
        self.assertEqual(probe.checks, {"normal_exit": False, "timeout": False})

    @unittest.skipUnless(sys.platform == "win32", "需 Windows Job Object 实测")
    def test_正常退出与超时均回收后代(self) -> None:
        with temp_workspace() as workspace:
            for mode, delay, timeout in (("normal", 1.5, 5), ("timeout", 3, 1)):
                started = workspace / f"{mode}-started"
                residue = workspace / f"{mode}-residue"
                child_code = (
                    "import time\nfrom pathlib import Path\n"
                    f"Path({str(started)!r}).write_text('ready')\n"
                    f"time.sleep({delay})\n"
                    f"Path({str(residue)!r}).write_text('late')\n"
                )
                parent_code = (
                    "import subprocess, sys, time\nfrom pathlib import Path\n"
                    f"subprocess.Popen([sys.executable, '-c', {child_code!r}], "
                    "creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)\n"
                    f"for _ in range(200):\n    if Path({str(started)!r}).exists(): break\n"
                    "    time.sleep(0.01)\n"
                    "else: raise RuntimeError('child did not start')\n"
                    + ("time.sleep(8)\n" if mode == "timeout" else "")
                )
                result = run_windows_job(
                    [sys.executable, "-c", parent_code],
                    cwd=workspace, timeout_seconds=timeout,
                )
                self.assertTrue(result.executed, result)
                self.assertTrue(started.is_file(), result)
                self.assertTrue(result.cleanup_ok, result)
                self.assertEqual(result.error, "timeout" if mode == "timeout" else None)
                time.sleep(delay + 0.2)
                self.assertFalse(residue.exists(), result)

    @unittest.skipUnless(sys.platform == "win32", "需 Windows Job Object 实测")
    def test_局部自检不冒充完整沙箱(self) -> None:
        from icode.isolation import capability_report

        report = capability_report()
        probe = report["windows_job_cleanup"]
        self.assertTrue(probe["executed"])
        self.assertEqual(probe["checks"], {"normal_exit": True, "timeout": True})
        self.assertTrue(probe["passed"], probe["detail"])
        # Scoring is executed, but a Job-only cleanup probe is not a complete
        # backend self-test or process-tree cleanup proof.
        contract = report["conformance_contract"]
        self.assertTrue(contract["executed"])
        self.assertFalse(contract["outcomes"]["doctor_self_test"])
        self.assertFalse(contract["outcomes"]["process_tree_cleanup"])

    @unittest.skipUnless(sys.platform == "win32", "需 Windows Job Object 崩溃实测")
    def test_宿主崩溃关闭job句柄也回收后代(self) -> None:
        with temp_workspace() as workspace:
            started = workspace / "crash-started"
            residue = workspace / "crash-residue"
            child_code = (
                "import time\nfrom pathlib import Path\n"
                f"Path({str(started)!r}).write_text('ready')\n"
                "time.sleep(2)\n"
                f"Path({str(residue)!r}).write_text('late')\n"
            )
            task_code = (
                "import subprocess, sys, time\n"
                f"subprocess.Popen([sys.executable, '-c', {child_code!r}], "
                "creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)\n"
                "time.sleep(8)\n"
            )
            source = Path(__file__).resolve().parents[1] / "src"
            broker_code = (
                "import sys\n"
                f"sys.path.insert(0, {str(source)!r})\n"
                "from icode.windows_job import run_windows_job\n"
                f"run_windows_job([sys.executable, '-c', {task_code!r}], "
                f"cwd={str(workspace)!r}, timeout_seconds=15)\n"
            )
            broker = subprocess.Popen(
                [sys.executable, "-c", broker_code], cwd=workspace,
                env={
                    "SystemRoot": os.environ.get("SystemRoot", r"C:\Windows"),
                    "PATH": str(Path(sys.executable).parent),
                    "PYTHONUTF8": "1",
                },
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                until = time.monotonic() + 5
                while time.monotonic() < until and not started.is_file():
                    if broker.poll() is not None:
                        self.fail("Job broker exited before descendant startup")
                    time.sleep(0.02)
                self.assertTrue(started.is_file(), "Job descendant did not start")
            finally:
                if broker.poll() is None:
                    broker.kill()
                broker.wait(timeout=5)
            time.sleep(2.2)
            self.assertFalse(residue.exists(), "Broker crash left a Job descendant alive")


if __name__ == "__main__":
    unittest.main()
