"""Landlock Reviewer 的固定目录对象，不替代完整策略验收。"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from icode.isolation import LandlockSandbox, PreparedCommand


@unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("cc"),
                     "需要 Linux 和 C 编译器")
class TestLinuxWorkspaceFd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="icode-workspace-fd-")
        cls.addClassCleanup(cls.temporary.cleanup)
        root = Path(cls.temporary.name)
        cls.helper = root / "icode-landlock"
        source = Path(__file__).resolve().parents[1] / "native/linux/icode_landlock.c"
        result = subprocess.run(
            [shutil.which("cc"), "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
             str(source), "-o", str(cls.helper)], capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stderr)
        cls.manifest = root / "icode-landlock.sha256"
        cls.manifest.write_text(hashlib.sha256(cls.helper.read_bytes()).hexdigest() + "\n",
                                encoding="ascii")
        # Inject replacement precisely after native object validation and
        # before cwd/rule setup; production functions and denial stay real.
        driver = root / "replace-after-validation.c"
        driver.write_text(
            '#define _GNU_SOURCE\n#include <unistd.h>\nstatic int replaced_fchdir(int);\n'
            '#define fchdir replaced_fchdir\n#define main original_main\n'
            f'#include "{source}"\n#undef main\n#undef fchdir\n'
            'static int replaced_fchdir(int fd) {\n'
            ' const char *root = getenv("ICODE_TEST_REPLACE_ROOT");\n'
            ' char old[4096];\n'
            ' if (!root || snprintf(old,sizeof(old),"%s-old",root) >= (int)sizeof(old)) return -1;\n'
            ' if (rename(root,old) || mkdir(root,0700)) return -1;\n'
            ' return fchdir(fd);\n}\n'
            'int main(int argc,char **argv) { return original_main(argc,argv); }\n',
            encoding="ascii")
        cls.race_helper = root / "replace-after-validation"
        result = subprocess.run(
            [shutil.which("cc"), "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
             str(driver), "-o", str(cls.race_helper)], capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stderr)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="icode-workspace-fd-case-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.workspace = self.root / "代码 空间"
        self.workspace.mkdir()
        (self.workspace / "source").write_text("original", encoding="ascii")
        self.sandbox = LandlockSandbox(str(self.helper), manifest=str(self.manifest))

    def pin(self):
        method = getattr(self.sandbox, "pin_read_only_workspace", None)
        self.assertTrue(callable(method), "Landlock 必须提供固定目录对象入口")
        pinned = method(self.workspace)
        self.addCleanup(os.close, pinned.fd)
        return pinned

    def native(self, fd, *options, script="print('executed')"):
        return subprocess.run(
            [str(self.helper), "--workspace", str(self.workspace), "--parent-pid",
             str(os.getpid()), "--workspace-read-only", "--workspace-fd", str(fd),
             *options, "--", "/usr/bin/python3", "-c", script],
            pass_fds=(fd,), capture_output=True, text=True, timeout=15)

    def test_wrapper_preserves_exact_fd_and_read_only_launch_contract(self):
        pinned = self.pin()
        prepared = self.sandbox.wrap_read_only(
            ["/usr/bin/python3", "-c", "print('read')"],
            workspace=pinned.path, workspace_fd=pinned.fd)
        self.assertIsInstance(prepared, PreparedCommand)
        self.assertEqual(prepared.pass_fds, (pinned.fd,))
        self.assertEqual(prepared.cwd, "/")
        index = prepared.index("--workspace-fd")
        self.assertEqual(prepared[index + 1], str(pinned.fd))
        self.assertFalse(self.sandbox.policy_contract_ready)

    def test_native_reads_original_object_without_inheriting_root_fd(self):
        fd = os.open(self.workspace, os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
        self.addCleanup(os.close, fd)
        result = self.native(fd, script=(
            "import os; assert open('source').read() == 'original'; "
            f"assert not os.path.exists('/proc/self/fd/{fd}'); print('pinned')"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "pinned")

    def test_native_read_only_and_outside_boundaries_remain_enforced(self):
        fd = os.open(self.workspace, os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
        self.addCleanup(os.close, fd)
        secret = self.root / "secret"
        secret.write_text("outside", encoding="ascii")
        result = self.native(fd, script=(
            "import pathlib; paths = ['source', 'created']; "
            "\nfor name in paths:\n"
            " try: pathlib.Path(name).write_text('bad')\n"
            " except PermissionError: pass\n"
            " else: raise AssertionError('write permitted')\n"
            f"try: pathlib.Path({str(secret)!r}).read_text()\n"
            "except PermissionError: pass\n"
            "else: raise AssertionError('outside read permitted')\n"
            "print('boundaries')"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "boundaries")
        self.assertEqual((self.workspace / "source").read_text(), "original")
        self.assertFalse((self.workspace / "created").exists())

    def test_replaced_directory_is_rejected_by_wrapper_and_native(self):
        pinned = self.pin()
        self.workspace.rename(self.root / "old-object")
        self.workspace.mkdir()
        (self.workspace / "source").write_text("replacement")
        with self.assertRaises(ValueError):
            self.sandbox.wrap_read_only(["/usr/bin/true"], workspace=pinned.path,
                                        workspace_fd=pinned.fd)
        result = self.native(pinned.fd)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("executed", result.stdout)

    def test_native_duplicate_and_writable_fd_options_are_rejected(self):
        pinned = self.pin()
        result = self.native(pinned.fd, "--workspace-fd", str(pinned.fd))
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("executed", result.stdout)
        argv = [str(self.helper), "--workspace", str(self.workspace), "--parent-pid",
                str(os.getpid()), "--workspace-fd", str(pinned.fd), "--",
                "/usr/bin/python3", "-c", "print('executed')"]
        result = subprocess.run(argv, pass_fds=(pinned.fd,), capture_output=True,
                                text=True, timeout=15)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("executed", result.stdout)

    def test_wrong_file_closed_and_scalar_fds_cannot_prepare_command(self):
        pinned = self.pin()
        file_fd = os.open(self.workspace / "source", os.O_RDONLY)
        self.addCleanup(os.close, file_fd)
        other_fd = os.open(self.root, os.O_PATH | os.O_DIRECTORY)
        self.addCleanup(os.close, other_fd)
        closed_fd = os.dup(pinned.fd)
        os.close(closed_fd)
        for fd in (True, -1, 0, "3", file_fd, other_fd, closed_fd):
            with self.subTest(fd=fd), self.assertRaises((ValueError, OSError)):
                self.sandbox.wrap_read_only(["/usr/bin/true"], workspace=pinned.path,
                                            workspace_fd=fd)
        for fd in (file_fd, other_fd):
            with self.subTest(native_fd=fd):
                result = self.native(fd)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("executed", result.stdout)

    def test_legacy_unpinned_wrapper_keeps_original_return_contract(self):
        prepared = self.sandbox.wrap_read_only(["/usr/bin/true"], workspace=self.workspace)
        self.assertIs(type(prepared), list)
        self.assertNotIn("--workspace-fd", prepared)
        self.assertIn("--workspace-read-only", prepared)

    def test_replacement_after_native_validation_cannot_redirect_rule_or_cwd(self):
        fd = os.open(self.workspace, os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
        self.addCleanup(os.close, fd)
        script = (
            "import pathlib; assert pathlib.Path('source').read_text() == 'original';\n"
            f"try: list(pathlib.Path({str(self.workspace)!r}).iterdir())\n"
            "except PermissionError: pass\n"
            "else: raise AssertionError('replacement directory authorized')\n"
            "print('original-object')")
        result = subprocess.run(
            [str(self.race_helper), "--workspace", str(self.workspace), "--parent-pid",
             str(os.getpid()), "--workspace-read-only", "--workspace-fd", str(fd),
             "--", "/usr/bin/python3", "-c", script], pass_fds=(fd,),
            env={**os.environ, "ICODE_TEST_REPLACE_ROOT": str(self.workspace)},
            capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "original-object")
        self.assertTrue(Path(str(self.workspace) + "-old", "source").is_file())
        self.assertFalse((self.workspace / "source").exists())
