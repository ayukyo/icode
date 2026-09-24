"""Linux 原生助手异常退出时的真实后代清理回归。"""

from __future__ import annotations

import ctypes
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
from icode.execution_broker import execute_policy_command
from icode.isolation import LandlockSandbox
from icode.sandbox_policy import NetworkMode, SandboxPolicy


def _open_verified_descendant_pidfd(namespace_pid: int, unique_path: Path) -> int:
    """仅按 NSpid + 唯一命令参数定位宿主进程；不向数值 PID 发信号。"""
    token = os.fsencode(str(unique_path))
    for process in Path("/proc").iterdir():
        if not process.name.isdecimal():
            continue
        try:
            status = (process / "status").read_text(encoding="ascii")
            nspid_line = next(line for line in status.splitlines()
                              if line.startswith("NSpid:"))
            if int(nspid_line.split()[-1]) != namespace_pid:
                continue
            if token not in (process / "cmdline").read_bytes():
                continue
            before = (process / "stat").read_text(encoding="ascii").rsplit(")", 1)[1]
            start_time = before.split()[19]  # /proc/<pid>/stat field 22
            if hasattr(os, "pidfd_open"):
                pidfd = os.pidfd_open(int(process.name))
            else:
                # 部分 Python 构建未暴露 os.pidfd_open，Linux 两目标架构
                # 均使用 asm-generic 的 pidfd_open syscall 号 434。
                pidfd = ctypes.CDLL(None, use_errno=True).syscall(434, int(process.name), 0)
                if pidfd < 0:
                    raise OSError(ctypes.get_errno(), "pidfd_open failed")
            try:
                after = (process / "stat").read_text(encoding="ascii").rsplit(")", 1)[1]
                if after.split()[19] == start_time and token in (process / "cmdline").read_bytes():
                    return pidfd
            except (OSError, ValueError, IndexError):
                pass
            os.close(pidfd)
        except (OSError, StopIteration, ValueError, IndexError):
            continue
    raise AssertionError("无法安全匹配宿主视角的测试后代")


@unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("cc"),
                     "需要 Linux C 编译器和进程命名空间")
class TestLinuxPidNamespaceCleanup(unittest.TestCase):
    def test_继承NOCLDWAIT和屏蔽SIGCHLD仍正确等待命令(self) -> None:
        source = Path(__file__).resolve().parents[1] / "native/linux/icode_landlock.c"
        launcher_source = Path(__file__).resolve().parent / "native/no_cldwait_launcher.c"
        system_python = Path("/usr/bin/python3")
        self.assertTrue(system_python.is_file())
        with temp_workspace() as root:
            helper = root / "icode-landlock"
            launcher = root / "no-cldwait-launcher"
            for source_file, executable in ((source, helper), (launcher_source, launcher)):
                subprocess.run(
                    [shutil.which("cc") or "cc", "-std=c11", "-O2", "-Wall", "-Wextra",
                     "-Werror", str(source_file), "-o", str(executable)],
                    check=True, capture_output=True, text=True,
                )
            result = subprocess.run(
                [str(launcher), str(helper), "--workspace", str(root),
                 "--parent-pid", str(os.getpid()), "--",
                 str(system_python), "-c", "print('payload-ok')"],
                capture_output=True, text=True, timeout=4, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("payload-ok", result.stdout)

    def test_宿主预开外部可写FD不能穿透Landlock(self) -> None:
        source = Path(__file__).resolve().parents[1] / "native/linux/icode_landlock.c"
        system_python = Path("/usr/bin/python3")
        self.assertTrue(system_python.is_file())
        with temp_workspace() as root:
            helper = root / "icode-landlock"
            subprocess.run(
                [shutil.which("cc") or "cc", "-std=c11", "-O2", "-Wall", "-Wextra",
                 "-Werror", str(source), "-o", str(helper)],
                check=True, capture_output=True, text=True,
            )
            workspace = root / "code"
            workspace.mkdir()
            outside = root / "outside-secret"
            outside.write_bytes(b"safe")
            with outside.open("r+b") as preopened:
                code = (
                    "import errno, os\n"
                    f"try: os.write({preopened.fileno()}, b'bad')\n"
                    "except OSError as exc:\n"
                    "    assert exc.errno == errno.EBADF, exc\n"
                    "    print('fd-closed')\n"
                    "else: print('fd-leaked')\n"
                )
                result = subprocess.run(
                    [str(helper), "--workspace", str(workspace),
                     "--parent-pid", str(os.getpid()), "--",
                     str(system_python), "-c", code],
                    pass_fds=(preopened.fileno(),), capture_output=True,
                    text=True, timeout=4, check=False,
                )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("fd-closed", result.stdout)
            self.assertEqual(outside.read_bytes(), b"safe")

    def test_忽略SIGCHLD的宿主仍正确等待命令(self) -> None:
        source = Path(__file__).resolve().parents[1] / "native/linux/icode_landlock.c"
        system_python = Path("/usr/bin/python3")
        self.assertTrue(system_python.is_file())
        with temp_workspace() as root:
            helper = root / "icode-landlock"
            subprocess.run(
                [shutil.which("cc") or "cc", "-std=c11", "-O2", "-Wall", "-Wextra",
                 "-Werror", str(source), "-o", str(helper)],
                check=True, capture_output=True, text=True,
            )
            # 驱动进程 exec 助手，外层 unittest 仍保持正常 SIGCHLD，以免
            # Python subprocess 将 ECHILD 误当作正常返回码。
            command = [str(helper), "--workspace", str(root),
                       "--parent-pid", str(os.getpid()), "--",
                       str(system_python), "-c", "print('payload-ok')"]
            driver = (
                "import os, signal\n"
                "signal.signal(signal.SIGCHLD, signal.SIG_IGN)\n"
                f"os.execv({str(helper)!r}, {command!r})\n"
            )
            result = subprocess.run([sys.executable, "-c", driver],
                                    capture_output=True, text=True, timeout=4,
                                    check=False)
            self.assertIn("payload-ok", result.stdout)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_命名空间创建失败绝不降级执行命令(self) -> None:
        source = Path(__file__).resolve().parents[1] / "native/linux/icode_landlock.c"
        denier_source = Path(__file__).resolve().parent / "native/deny_unshare.c"
        system_python = Path("/usr/bin/python3")
        self.assertTrue(system_python.is_file())
        with temp_workspace() as root:
            helper = root / "icode-landlock"
            denier = root / "deny-unshare"
            for source_file, executable in ((source, helper), (denier_source, denier)):
                subprocess.run(
                    [shutil.which("cc") or "cc", "-std=c11", "-O2", "-Wall", "-Wextra",
                     "-Werror", str(source_file), "-o", str(executable)],
                    check=True, capture_output=True, text=True,
                )
            marker = root / "must-not-run"
            code = f"from pathlib import Path; Path({str(marker)!r}).write_text('bad')"
            result = subprocess.run(
                [str(denier), str(helper), "--workspace", str(root),
                 "--parent-pid", str(os.getpid()), "--", str(system_python), "-c", code],
                capture_output=True, text=True, timeout=4, check=False,
            )
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("unshare user/pid namespace", result.stderr)
            self.assertFalse(marker.exists(), "命名空间启动失败却执行了受限命令")

    def test_超时也清理已脱组后代(self) -> None:
        source = Path(__file__).resolve().parents[1] / "native/linux/icode_landlock.c"
        with temp_workspace() as root:
            helper = root / "icode-landlock"
            subprocess.run(
                [shutil.which("cc") or "cc", "-std=c11", "-O2", "-Wall", "-Wextra",
                 "-Werror", str(source), "-o", str(helper)],
                check=True, capture_output=True, text=True,
            )
            workspace = root / "code"
            workspace.mkdir()
            started = workspace / "timeout-started"
            survived = workspace / "timeout-survived"
            grandchild = (
                "import os, time\nfrom pathlib import Path\n"
                "os.setsid()\n"
                f"Path({str(started)!r}).write_text('detached')\n"
                "time.sleep(1.6)\n"
                f"Path({str(survived)!r}).write_text('escaped')\n"
            )
            parent = (
                "import subprocess, sys, time\nfrom pathlib import Path\n"
                f"subprocess.Popen([sys.executable, '-c', {grandchild!r}], "
                "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, "
                "stderr=subprocess.DEVNULL)\n"
                f"for _ in range(200):\n    if Path({str(started)!r}).exists(): break\n"
                "    time.sleep(0.01)\n"
                "else: raise RuntimeError('grandchild did not start')\n"
                "print('detached-started', flush=True)\n"
                "time.sleep(5)\n"
            )
            policy = SandboxPolicy(
                schema_version=1, run_id="pidns-timeout", ticket_id="pidns-timeout",
                step="code", workspace_root=workspace, read_roots=(workspace,),
                write_roots=(workspace,), deny_read_roots=(), deny_write_roots=(),
                network_mode=NetworkMode.DENY, allowed_domains=(), process_limit=8,
                wall_timeout_seconds=1, output_limit_bytes=1024, protected_paths=(),
            )
            result = execute_policy_command(
                LandlockSandbox(helper=str(helper)).wrap(
                    [sys.executable, "-c", parent], workspace=workspace,
                ),
                cwd=workspace, policy=policy, timeout=1,
            )
            self.assertEqual(result.error, "timeout", result)
            self.assertTrue(result.cleanup_ok, result)
            self.assertIn("detached-started", result.output)
            self.assertEqual(started.read_text(encoding="ascii"), "detached")
            time.sleep(1.8)
            self.assertFalse(survived.exists())

    def test_输出超限也清理已脱组后代(self) -> None:
        source = Path(__file__).resolve().parents[1] / "native/linux/icode_landlock.c"
        with temp_workspace() as root:
            helper = root / "icode-landlock"
            subprocess.run(
                [shutil.which("cc") or "cc", "-std=c11", "-O2", "-Wall", "-Wextra",
                 "-Werror", str(source), "-o", str(helper)],
                check=True, capture_output=True, text=True,
            )
            workspace = root / "code"
            workspace.mkdir()
            started = workspace / "output-started"
            survived = workspace / "output-survived"
            grandchild = (
                "import os, time\nfrom pathlib import Path\n"
                "os.setsid()\n"
                f"Path({str(started)!r}).write_text('detached')\n"
                "time.sleep(1.2)\n"
                f"Path({str(survived)!r}).write_text('escaped')\n"
            )
            parent = (
                "import subprocess, sys, time\nfrom pathlib import Path\n"
                f"subprocess.Popen([sys.executable, '-c', {grandchild!r}], "
                "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, "
                "stderr=subprocess.DEVNULL)\n"
                f"for _ in range(200):\n    if Path({str(started)!r}).exists(): break\n"
                "    time.sleep(0.01)\n"
                "else: raise RuntimeError('grandchild did not start')\n"
                "print('X' * 1000, flush=True)\n"
                "time.sleep(5)\n"
            )
            policy = SandboxPolicy(
                schema_version=1, run_id="pidns-output", ticket_id="pidns-output",
                step="code", workspace_root=workspace, read_roots=(workspace,),
                write_roots=(workspace,), deny_read_roots=(), deny_write_roots=(),
                network_mode=NetworkMode.DENY, allowed_domains=(), process_limit=8,
                wall_timeout_seconds=5, output_limit_bytes=64, protected_paths=(),
            )
            sandbox = LandlockSandbox(helper=str(helper))
            result = execute_policy_command(
                sandbox.wrap([sys.executable, "-c", parent], workspace=workspace),
                cwd=workspace, policy=policy, timeout=5,
            )
            self.assertEqual(result.error, "output_limit", result)
            self.assertTrue(result.cleanup_ok, result)
            self.assertEqual(started.read_text(encoding="ascii"), "detached")
            time.sleep(1.4)
            self.assertFalse(survived.exists())

    def test_后台进程继承stdout也不能拖住已结束命令(self) -> None:
        source = Path(__file__).resolve().parents[1] / "native/linux/icode_landlock.c"
        system_python = Path("/usr/bin/python3")
        self.assertTrue(system_python.is_file())
        with temp_workspace() as root:
            helper = root / "icode-landlock"
            subprocess.run(
                [shutil.which("cc") or "cc", "-std=c11", "-O2", "-Wall", "-Wextra",
                 "-Werror", str(source), "-o", str(helper)],
                check=True, capture_output=True, text=True,
            )
            started = root / "stdout-started"
            survived = root / "stdout-survived"
            grandchild = (
                "import os, time\nfrom pathlib import Path\n"
                "os.setsid()\n"
                f"Path({str(started)!r}).write_text('ready')\n"
                "time.sleep(1.2)\n"
                f"Path({str(survived)!r}).write_text('escaped')\n"
            )
            parent = (
                "import subprocess, sys, time\nfrom pathlib import Path\n"
                f"subprocess.Popen([sys.executable, '-c', {grandchild!r}])\n"
                f"for _ in range(200):\n    if Path({str(started)!r}).exists(): break\n"
                "    time.sleep(0.01)\n"
                "else: raise RuntimeError('grandchild did not start')\n"
                "print('command-exited', flush=True)\n"
            )
            outcome = subprocess.run(
                [str(helper), "--workspace", str(root), "--parent-pid", str(os.getpid()),
                 "--", str(system_python), "-c", parent],
                capture_output=True, text=True, timeout=3, check=False,
            )
            self.assertEqual(outcome.returncode, 0, outcome.stderr)
            self.assertIn("command-exited", outcome.stdout)
            self.assertTrue(started.exists())
            time.sleep(1.4)
            self.assertFalse(survived.exists())

    def test_受限命令不是PID1且不能干扰可信监督者(self) -> None:
        source = Path(__file__).resolve().parents[1] / "native/linux/icode_landlock.c"
        system_python = Path("/usr/bin/python3")
        self.assertTrue(system_python.is_file())
        with temp_workspace() as root:
            helper = root / "icode-landlock"
            subprocess.run(
                [shutil.which("cc") or "cc", "-std=c11", "-O2", "-Wall", "-Wextra",
                 "-Werror", str(source), "-o", str(helper)],
                check=True, capture_output=True, text=True,
            )
            code = (
                "import ctypes, os, signal\n"
                "assert os.getpid() == 2 and os.getppid() == 1, "
                "(os.getpid(), os.getppid())\n"
                "libc = ctypes.CDLL(None, use_errno=True)\n"
                "class H(ctypes.Structure):\n"
                "    _fields_ = [('version', ctypes.c_uint32), ('pid', ctypes.c_int)]\n"
                "class D(ctypes.Structure):\n"
                "    _fields_ = [('effective', ctypes.c_uint32), "
                "('permitted', ctypes.c_uint32), ('inheritable', ctypes.c_uint32)]\n"
                "caps = (D * 2)()\n"
                "assert libc.capget(ctypes.byref(H(0x20080522, 0)), ctypes.byref(caps)) == 0\n"
                "assert all(not (c.effective or c.permitted or c.inheritable) for c in caps)\n"
                "assert libc.prctl(39, 0, 0, 0, 0) == 1\n"  # PR_GET_NO_NEW_PRIVS
                "assert libc.ptrace(16, 1, 0, 0) == -1\n"  # PTRACE_ATTACH
                "assert ctypes.get_errno() == 1\n"
                "class IOVec(ctypes.Structure):\n"
                "    _fields_ = [('base', ctypes.c_void_p), ('length', ctypes.c_size_t)]\n"
                "buffer = ctypes.create_string_buffer(1)\n"
                "local = IOVec(ctypes.cast(buffer, ctypes.c_void_p), 1)\n"
                "remote = IOVec(1, 1)\n"
                "ctypes.set_errno(0)\n"
                "assert libc.process_vm_readv(1, ctypes.byref(local), 1, "
                "ctypes.byref(remote), 1, 0) == -1\n"
                "assert ctypes.get_errno() == 1\n"
                "ctypes.set_errno(0)\n"
                "assert libc.process_vm_writev(1, ctypes.byref(local), 1, "
                "ctypes.byref(remote), 1, 0) == -1\n"
                "assert ctypes.get_errno() == 1\n"
                "os.kill(1, signal.SIGKILL)\n"  # 子 PID namespace 无权杀 PID 1
                "print('supervisor-intact', flush=True)\n"
            )
            result = subprocess.run(
                [str(helper), "--workspace", str(root), "--parent-pid", str(os.getpid()),
                 "--", str(system_python), "-c", code],
                capture_output=True, text=True, timeout=4, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("supervisor-intact", result.stdout)

    def test_宿主强杀后主动脱组的多层后代不能残留(self) -> None:
        source = Path(__file__).resolve().parents[1] / "native/linux/icode_landlock.c"
        system_python = Path("/usr/bin/python3")
        self.assertTrue(system_python.is_file())
        with temp_workspace() as root:
            helper = root / "icode-landlock"
            subprocess.run(
                [shutil.which("cc") or "cc", "-std=c11", "-O2", "-Wall", "-Wextra",
                 "-Werror", str(source), "-o", str(helper)],
                check=True, capture_output=True, text=True,
            )
            started = root / "started"
            survived = root / "survived"
            grandchild = (
                "import os, time\nfrom pathlib import Path\n"
                "try:\n    os.setsid()\n    detached = os.getsid(0) == os.getpid()\n"
                "except PermissionError:\n    detached = False\n"
                f"Path({str(started)!r}).write_text(('detached:' if detached else "
                "'denied:') + str(os.getpid()))\n"
                "time.sleep(1.2)\n"
                f"Path({str(survived)!r}).write_text('escaped')\n"
            )
            child = (
                "import subprocess, sys, time\n"
                f"subprocess.Popen([sys.executable, '-c', {grandchild!r}], "
                "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, "
                "stderr=subprocess.DEVNULL)\n"
                "time.sleep(3)\n"
            )
            host = (
                "import os, subprocess, sys, time\n"
                f"subprocess.Popen([{str(helper)!r}, '--workspace', {str(root)!r}, "
                f"'--parent-pid', str(os.getpid()), '--', {str(system_python)!r}, '-c', "
                f"{child!r}], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, "
                "stderr=subprocess.DEVNULL)\n"
                "time.sleep(10)\n"
            )
            parent = subprocess.Popen([sys.executable, "-c", host],
                                      stdin=subprocess.DEVNULL,
                                      stdout=subprocess.DEVNULL,
                                      stderr=subprocess.DEVNULL)
            pidfd: int | None = None
            try:
                for _ in range(400):
                    if started.exists():
                        break
                    if parent.poll() is not None:
                        break
                    time.sleep(0.01)
                self.assertTrue(started.exists(), "原生助手未启动后代")
                marker = started.read_text(encoding="ascii")
                self.assertTrue(marker.startswith("detached:"),
                                "必须真实覆盖已主动 setsid 脱组的后代")
                pidfd = _open_verified_descendant_pidfd(int(marker.split(":", 1)[1]),
                                                          survived)
                os.kill(parent.pid, signal.SIGKILL)
                parent.wait(timeout=3)
                exit_events = select.poll()
                exit_events.register(pidfd, select.POLLIN)
                self.assertTrue(exit_events.poll(1000),
                                "宿主视角的已脱组后代仍在运行")
                time.sleep(1.45)
                self.assertFalse(survived.exists(), "宿主已死，但原生助手后代仍可写入")
            finally:
                if pidfd is not None:
                    os.close(pidfd)
                if parent.poll() is None:
                    parent.kill()
                    parent.wait(timeout=3)


if __name__ == "__main__":
    unittest.main()
