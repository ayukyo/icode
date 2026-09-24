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
    _build_windows_environment_block,
    probe_windows_job_cleanup,
    run_windows_job,
)


class TestWindowsJob(unittest.TestCase):
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

    def test_非_windows_不能运行(self) -> None:
        if sys.platform == "win32":
            self.skipTest("仅校验非 Windows 拒绝")
        result = run_windows_job([sys.executable, "-V"], cwd=os.getcwd(), timeout_seconds=2)
        self.assertFalse(result.executed)
        self.assertFalse(result.cleanup_ok)
        probe = probe_windows_job_cleanup()
        self.assertFalse(probe.executed)
        self.assertFalse(probe.passed)

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
        self.assertFalse(report["conformance_contract"]["executed"])

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
