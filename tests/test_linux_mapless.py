"""无 UID 映射的 PID namespace 回退必须保留真实 OS 防线。"""

from __future__ import annotations

import os
import select
import shutil
import signal
import subprocess
import sys
import time
import unittest
from pathlib import Path

from tests._support import temp_workspace
from tests.test_linux_pidns_cleanup import _open_verified_descendant_pidfd


@unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("cc"),
                     "需要 Linux user/PID namespace 和 C 编译器")
class TestLinuxMaplessFallback(unittest.TestCase):
    system_python = "/usr/bin/python3"

    def _driver(self, root: Path) -> Path:
        source = Path(__file__).resolve().parents[1] / "native/linux/icode_landlock.c"
        driver = root / "mapless-driver.c"
        driver.write_text(
            f'#define main icode_helper_main\n#include "{source}"\n#undef main\n'
            'int main(int argc, char **argv) {\n'
            '    const char *path = getenv("ICODE_TEST_UID_MAP_PATH");\n'
            '    return run_helper(argc, argv, "/proc/self/setgroups",\n'
            '                      path ? path : "/proc/self/uid_map");\n'
            '}\n',
            encoding="ascii",
        )
        executable = root / "mapless-driver"
        build = subprocess.run(
            [shutil.which("cc") or "cc", "-std=c11", "-O2", "-Wall", "-Wextra",
             "-Werror", str(driver), "-o", str(executable)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(build.returncode, 0, build.stderr)
        return executable

    def test_权限拒绝只允许无映射且无能力的受限命令(self) -> None:
        with temp_workspace() as root:
            helper = self._driver(root)
            workspace = root / "code"
            workspace.mkdir()
            outside = root / "outside-secret"
            outside.write_text("secret", encoding="ascii")
            denied_uid_map = root / "uid-map-readonly"
            denied_uid_map.write_text("unmapped", encoding="ascii")
            denied_uid_map.chmod(0o444)
            code = (
                "import ctypes, os, socket\nfrom pathlib import Path\n"
                "assert os.getpid() == 2 and os.getppid() == 1\n"
                "assert os.getuid() == 65534 and os.getgid() == 65534\n"
                "class H(ctypes.Structure):\n"
                "    _fields_ = [('version', ctypes.c_uint32), ('pid', ctypes.c_int)]\n"
                "class D(ctypes.Structure):\n"
                "    _fields_ = [('effective', ctypes.c_uint32), "
                "('permitted', ctypes.c_uint32), ('inheritable', ctypes.c_uint32)]\n"
                "libc = ctypes.CDLL(None, use_errno=True)\n"
                "caps = (D * 2)()\n"
                "assert libc.capget(ctypes.byref(H(0x20080522, 0)), ctypes.byref(caps)) == 0\n"
                "assert all(not (c.effective or c.permitted or c.inheritable) for c in caps)\n"
                "assert libc.prctl(39, 0, 0, 0, 0) == 1\n"  # PR_GET_NO_NEW_PRIVS
                "Path('allowed').write_text('ok')\n"
                f"for path in ({str(outside)!r},):\n"
                "    try: Path(path).read_text()\n"
                "    except PermissionError: pass\n"
                "    else: raise AssertionError('outside read allowed')\n"
                "    try: Path(path).write_text('bad')\n"
                "    except PermissionError: pass\n"
                "    else: raise AssertionError('outside write allowed')\n"
                "try: socket.socket(socket.AF_INET)\n"
                "except PermissionError: pass\n"
                "else: raise AssertionError('network socket allowed')\n"
                "print('mapless-restricted')\n"
            )
            env = os.environ.copy()
            env["ICODE_TEST_UID_MAP_PATH"] = str(denied_uid_map)
            result = subprocess.run(
                [str(helper), "--workspace", str(workspace), "--parent-pid",
                 str(os.getpid()), "--", self.system_python, "-c", code],
                cwd=workspace, env=env, capture_output=True, text=True,
                timeout=5, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("mapless-restricted", result.stdout)
            self.assertEqual((workspace / "allowed").read_text(encoding="ascii"), "ok")
            self.assertEqual(outside.read_text(encoding="ascii"), "secret")

    def test_非权限类_uid_map_错误不能执行负载(self) -> None:
        with temp_workspace() as root:
            helper = self._driver(root)
            workspace = root / "code"
            workspace.mkdir()
            marker = workspace / "must-not-run"
            env = os.environ.copy()
            env["ICODE_TEST_UID_MAP_PATH"] = str(root / "missing-uid-map")
            result = subprocess.run(
                [str(helper), "--workspace", str(workspace), "--parent-pid",
                 str(os.getpid()), "--", self.system_python, "-c",
                 f"from pathlib import Path; Path({str(marker)!r}).write_text('bad')"],
                cwd=workspace, env=env, capture_output=True, text=True,
                timeout=5, check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(marker.exists())

    def test_无映射宿主强杀后主动脱组后代不残留(self) -> None:
        with temp_workspace() as root:
            helper = self._driver(root)
            workspace = root / "code"
            workspace.mkdir()
            denied_uid_map = root / "uid-map-readonly"
            denied_uid_map.write_text("unmapped", encoding="ascii")
            denied_uid_map.chmod(0o444)
            started = workspace / "started"
            survived = workspace / "survived"
            grandchild = (
                "import os, time\nfrom pathlib import Path\n"
                "os.setsid()\n"
                f"Path({str(started)!r}).write_text('detached:' + str(os.getpid()))\n"
                "time.sleep(1.2)\n"
                f"Path({str(survived)!r}).write_text('escaped')\n"
            )
            payload = (
                "import subprocess, sys, time\n"
                f"subprocess.Popen([sys.executable, '-c', {grandchild!r}], "
                "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, "
                "stderr=subprocess.DEVNULL)\n"
                "time.sleep(5)\n"
            )
            host = (
                "import os, subprocess, sys, time\n"
                f"subprocess.Popen([{str(helper)!r}, '--workspace', {str(workspace)!r}, "
                f"'--parent-pid', str(os.getpid()), '--', {self.system_python!r}, '-c', {payload!r}], "
                "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, "
                "stderr=subprocess.DEVNULL, env=os.environ.copy())\n"
                "time.sleep(10)\n"
            )
            env = os.environ.copy()
            env["ICODE_TEST_UID_MAP_PATH"] = str(denied_uid_map)
            parent = subprocess.Popen([sys.executable, "-c", host], env=env,
                                      stdin=subprocess.DEVNULL,
                                      stdout=subprocess.DEVNULL,
                                      stderr=subprocess.DEVNULL)
            pidfd: int | None = None
            try:
                for _ in range(300):
                    if started.exists() or parent.poll() is not None:
                        break
                    time.sleep(0.01)
                self.assertTrue(started.exists(), "mapless 负载未启动")
                marker = started.read_text(encoding="ascii")
                self.assertTrue(marker.startswith("detached:"), marker)
                pidfd = _open_verified_descendant_pidfd(
                    int(marker.split(":", 1)[1]), survived,
                )
                os.kill(parent.pid, signal.SIGKILL)
                parent.wait(timeout=3)
                exit_events = select.poll()
                exit_events.register(pidfd, select.POLLIN)
                self.assertTrue(exit_events.poll(1000), "mapless 脱组后代仍在运行")
                time.sleep(1.4)
                self.assertFalse(survived.exists(), "宿主退出后仍有脱组后代写入")
            finally:
                if pidfd is not None:
                    os.close(pidfd)
                if parent.poll() is None:
                    parent.kill()
                    parent.wait(timeout=3)


if __name__ == "__main__":
    unittest.main()
