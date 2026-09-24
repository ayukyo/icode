"""R2.3 AppContainer 文件/网络边界实验；不是生产后端 ready 证明。"""

from __future__ import annotations

import http.client
import http.server
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from urllib.parse import urlsplit

from icode.windows_appcontainer import _AppContainerSetupError
from icode.windows_appcontainer import _walk_workspace, run_windows_appcontainer


class TestWindowsAppContainer(unittest.TestCase):
    def _workflow_notice(self, name: str, detail: str) -> None:
        """Expose only bounded probe outcomes in public Actions annotations."""
        if os.environ.get("GITHUB_ACTIONS") != "true":
            return
        safe_detail = detail[:500].replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::notice title=R2.3 {name}::{safe_detail}", flush=True)

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

    @unittest.skipUnless(sys.platform == "win32", "需 Windows AppContainer 原生实测")
    def test_在AppContainer中运行Python并解析工作路径(self) -> None:
        """Verify the actual pip-installed runtime shape, not only cmd.exe."""
        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-python-") as raw:
            root = Path(raw).resolve()
            workspace = root / "task"
            workspace.mkdir()
            marker = workspace / "python-probe.json"
            probe = (
                "import json\n"
                "from pathlib import Path\n"
                "import sys\n"
                "result = {}\n"
                "for label, value in [('cwd', Path.cwd()), ('executable', Path(sys.executable))]:\n"
                "    try:\n"
                "        result[label] = str(value.resolve(strict=True))\n"
                "    except Exception as exc:\n"
                "        result[label] = f'{type(exc).__name__}: {exc}'\n"
                f"Path({str(marker)!r}).write_text(json.dumps(result), encoding='utf-8')\n"
            )
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
            for label, value in resolved.items():
                self.assertTrue(
                    Path(value).is_absolute(),
                    f"AppContainer could not resolve {label}: {value}",
                )

    @unittest.skipUnless(sys.platform == "win32", "需 Windows AppContainer 原生实测")
    def test_仅开放工单目录且默认拒绝网络(self) -> None:
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
                allowed_write = workspace / "new-output.txt"
                copied_secret = workspace / "outside-copy.txt"
                copied_nested = workspace / "nested-copy.txt"
                child_started = workspace / "child-started.txt"
                child_late = workspace / "child-late.txt"
                child_script = workspace / "child.cmd"
                child_script.write_text(
                    "@echo off\r\n"
                    f'echo started> "{child_started}"\r\n'
                    "timeout /t 3 /nobreak >nul\r\n"
                    f'echo late> "{child_late}"\r\n',
                    encoding="utf-8",
                )
                script = workspace / "probe.cmd"
                script.write_text(
                    "@echo off\r\n"
                    f'echo workspace-write-ok> "{allowed_write}"\r\n'
                    f'type "{nested / "input.txt"}" > "{copied_nested}"\r\n'
                    f'type "{outside_secret}" > "{copied_secret}"\r\n'
                    f'echo escape> "{outside_write}"\r\n'
                    f'"{curl}" --noproxy "*" --connect-timeout 1 --max-time 2 '
                    f'"{url}" > "{workspace / "network.txt"}" 2>&1\r\n'
                    f'start "" /b "{command}" /d /c "{child_script}"\r\n'
                    "timeout /t 1 /nobreak >nul\r\n"
                    "exit /b 0\r\n",
                    encoding="utf-8",
                )
                result = run_windows_appcontainer(
                    [str(command), "/d", "/c", str(script)],
                    cwd=workspace, timeout_seconds=12, process_limit=8,
                )
                self._workflow_notice(
                    "workspace and network probe",
                    f"executed={result.executed} exit={result.exit_code} error={result.error} "
                    f"cleanup={result.cleanup_ok} detail={result.detail}",
                )

                self.assertTrue(result.executed, result)
                self.assertEqual(result.exit_code, 0, result)
                self.assertIsNone(result.error, result)
                self.assertTrue(result.cleanup_ok, result)
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
                self.assertTrue(child_started.is_file(), "AppContainer descendant did not start")
                time.sleep(3.2)
                self.assertFalse(child_late.exists(), "AppContainer Job left a descendant alive")

                child_started.unlink()
                timeout_script = workspace / "timeout-parent.cmd"
                timeout_script.write_text(
                    "@echo off\r\n"
                    f'start "" /b "{command}" /d /c "{child_script}"\r\n'
                    "timeout /t 8 /nobreak >nul\r\n",
                    encoding="utf-8",
                )
                timed_out = run_windows_appcontainer(
                    [str(command), "/d", "/c", str(timeout_script)],
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
                time.sleep(3.2)
                self.assertFalse(child_late.exists(), "timeout left an AppContainer descendant alive")

                limited_marker = workspace / "process-limit-child.txt"
                limited_child = workspace / "process-limit-child.cmd"
                limited_child.write_text(
                    f'echo escaped> "{limited_marker}"\r\n', encoding="utf-8",
                )
                limited_parent = workspace / "process-limit-parent.cmd"
                limited_parent.write_text(
                    "@echo off\r\n"
                    f'start "" /b "{command}" /d /c "{limited_child}"\r\n'
                    "timeout /t 1 /nobreak >nul\r\n",
                    encoding="utf-8",
                )
                limited = run_windows_appcontainer(
                    [str(command), "/d", "/c", str(limited_parent)],
                    cwd=workspace, timeout_seconds=5, process_limit=1,
                )
                self._workflow_notice(
                    "process limit probe",
                    f"executed={limited.executed} exit={limited.exit_code} error={limited.error} "
                    f"cleanup={limited.cleanup_ok} detail={limited.detail}",
                )
                self.assertTrue(limited.executed, limited)
                self.assertTrue(limited.cleanup_ok, limited)
                self.assertFalse(limited_marker.exists(), "Job active-process limit was not enforced")
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
