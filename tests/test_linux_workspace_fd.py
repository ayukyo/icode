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
from dataclasses import replace

from icode.isolation import LandlockSandbox, PreparedCommand
from icode.tools import ToolContext
from icode.tools.base import IsolationUnavailable
from icode.workspace import WorkspaceManager


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

    def session(self):
        # The real split Git layout keeps protected metadata outside the code
        # root. Do not erase snapshot .git protection to make Landlock pass.
        for args in (("init", "-q"), ("add", "source"),
                     ("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                      "commit", "-qm", "base")):
            subprocess.run(["git", "-C", str(self.workspace), *args], check=True,
                           capture_output=True, timeout=15)
        session = WorkspaceManager(self.workspace, self.root / "data", "fd-project",
                                   isolate_git_metadata=True).open(
            "fd-ticket", "fd-run")
        self.addCleanup(session.close)
        return session

    def test_session_owns_fd_and_context_only_borrows_it(self):
        session = self.session()
        fd = getattr(session, "workspace_fd", None)
        self.assertIs(type(fd), int, "Linux session must own its workspace FD")
        status = os.fstat(fd)
        self.assertEqual(session.workspace_fd_identity, (status.st_dev, status.st_ino))
        ctx = ToolContext(session.workspace_root, sandbox=self.sandbox,
                          policy=session.policy("code"), workspace_session=session)
        prepared = ctx.wrap_command(["/usr/bin/python3", "-c",
                                     "open('new-source','w').write('created')"])
        self.assertIsInstance(prepared, PreparedCommand)
        self.assertEqual(prepared.pass_fds, (fd,))
        ctx.close()
        self.assertEqual(os.fstat(fd).st_ino, status.st_ino)
        result = subprocess.run(prepared, pass_fds=prepared.pass_fds, cwd=prepared.cwd,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((session.workspace_root / "new-source").read_text(), "created")
        session.close()
        self.assertIsNone(session.workspace_fd)
        with self.assertRaises(OSError):
            os.fstat(fd)
        with self.assertRaises(IsolationUnavailable):
            ctx.wrap_command(["/usr/bin/true"])

    def test_context_rejects_wrong_ticket_and_recycled_descriptor(self):
        session = self.session()
        ctx = ToolContext(session.workspace_root, sandbox=self.sandbox,
                          policy=session.policy("code"), workspace_session=session)
        ctx.policy = replace(ctx.policy, ticket_id="other-ticket")
        with self.assertRaises(IsolationUnavailable):
            ctx.wrap_command(["/usr/bin/true"])
        ctx.policy = session.policy("code")
        fd = session.workspace_fd
        os.close(fd)  # Explicit fault injection: external close/reuse of owner's FD.
        replacement = os.open(self.workspace, os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
        if replacement != fd:
            os.dup2(replacement, fd, inheritable=False)
            os.close(replacement)
        with self.assertRaises(IsolationUnavailable):
            ctx.wrap_command(["/usr/bin/true"])

    def test_broker_rejects_channel_collision_before_payload(self):
        from icode.execution_broker import execute_linux_violation_observed_command
        session = self.session()
        def collision(argv, channel):
            return PreparedCommand(argv, pass_fds=(channel.fileno(),), cwd="/")
        result = execute_linux_violation_observed_command(
            ["/usr/bin/touch", "created"], cwd=session.workspace_root,
            sandbox=self.sandbox, policy=session.policy("code"), timeout=3,
            command_wrapper=collision)
        self.assertEqual(result.error, "isolation_unavailable")
        self.assertFalse((session.workspace_root / "created").exists())
        self.assertTrue(os.fstat(session.workspace_fd))

    def test_prepared_command_rejects_reuse_after_host_validation(self):
        session = self.session()
        ctx = ToolContext(session.workspace_root, sandbox=self.sandbox,
                          policy=session.policy("code"), workspace_session=session)
        prepared = ctx.wrap_command(["/usr/bin/touch", "created"])
        # Replace both the path and the FD after Python validates them. Native
        # must compare its frozen claim, not merely compare these two new objects.
        original = session.workspace_root.with_name("original-code")
        session.workspace_root.rename(original)
        session.workspace_root.mkdir()
        fd = session.workspace_fd
        os.close(fd)
        replacement = os.open(session.workspace_root,
                              os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
        if replacement != fd:
            os.dup2(replacement, fd, inheritable=False)
            os.close(replacement)
        result = subprocess.run(prepared, pass_fds=prepared.pass_fds, cwd=prepared.cwd,
                                capture_output=True, timeout=15)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((session.workspace_root / "created").exists())
        self.assertFalse((original / "created").exists())

    def test_native_writable_fd_has_frozen_identity_and_is_closed_on_exec(self):
        fd = os.open(self.workspace, os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
        self.addCleanup(os.close, fd)
        status = os.fstat(fd)
        result = subprocess.run(
            [str(self.helper), "--workspace", str(self.workspace), "--parent-pid",
             str(os.getpid()), "--workspace-object-fd", str(fd), str(status.st_dev),
             str(status.st_ino), "--", "/usr/bin/python3", "-c",
             f"import os; assert not os.path.exists('/proc/self/fd/{fd}'); "
             "open('created','w').write('ok')"], pass_fds=(fd,),
            capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.workspace / "created").read_text(), "ok")

    def test_scope_wrap_preserves_workspace_launch_metadata(self):
        from icode.linux_task_scope import LinuxTaskScope
        scope = object.__new__(LinuxTaskScope)
        scope.version = 249
        scope.unit = "icode-task-0123456789abcdef0123456789abcdef.scope"
        command = PreparedCommand(["/usr/bin/true"], pass_fds=(17,), cwd="/")
        wrapped = scope.wrap(command)
        self.assertIsInstance(wrapped, PreparedCommand)
        self.assertEqual(wrapped.pass_fds, (17,))
        self.assertEqual(wrapped.cwd, "/")
        self.assertIs(type(scope.wrap(["/usr/bin/true"])), list)

    def test_session_copies_share_one_idempotent_descriptor_owner(self):
        session = self.session()
        copied = replace(session)
        fd = session.workspace_fd
        copied.close()
        self.assertIsNone(session.workspace_fd)
        replacement = os.open(self.workspace, os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
        if replacement != fd:
            os.dup2(replacement, fd, inheritable=False)
            os.close(replacement)
        self.addCleanup(os.close, fd)
        session.close()
        self.assertTrue(os.fstat(fd))

    def test_native_rejects_wrong_frozen_identity_before_payload(self):
        fd = os.open(self.workspace, os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
        self.addCleanup(os.close, fd)
        status = os.fstat(fd)
        result = subprocess.run(
            [str(self.helper), "--workspace", str(self.workspace), "--parent-pid",
             str(os.getpid()), "--workspace-object-fd", str(fd), str(status.st_dev),
             str(status.st_ino + 1), "--", "/usr/bin/touch", "created"],
            pass_fds=(fd,), cwd=self.workspace, capture_output=True, timeout=15)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.workspace / "created").exists())

    def test_real_resource_chain_retains_borrowed_workspace_object(self):
        from icode.execution_broker import execute_linux_resource_observed_command
        from tests.test_linux_product_task_quota import require_user_manager
        session = self.session()
        ctx = ToolContext(session.workspace_root, sandbox=self.sandbox,
                          policy=session.policy("code"), workspace_session=session)

        @require_user_manager
        def run(case):
            result = execute_linux_resource_observed_command(
                ["/usr/bin/python3", "-c",
                 f"import os; assert not os.path.exists('/proc/self/fd/{session.workspace_fd}'); "
                 "open('created','w').write('resource-chain')"],
                cwd=session.workspace_root, sandbox=self.sandbox, policy=ctx.policy,
                timeout=15, command_wrapper=ctx.wrap_command_with_resource_receipt)
            case.assertIsNone(result.error, result)
            case.assertEqual(result.exit_code, 0, result)
            case.assertEqual(result.violation_observer_status, "complete")
            case.assertIs(result.scope_cleanup_ok, True)
            # Resource v1 proves CONFIGURED/terminal, not positive exec receipt.
            # The created file independently proves this payload ran.
            case.assertIsNone(result.payload_started)
            case.assertIs(result.resource_receipt["configured"], True)
            case.assertEqual(result.resource_receipt["channel_status"], "complete")
            case.assertEqual((session.workspace_root / "created").read_text(), "resource-chain")
            case.assertTrue(os.fstat(session.workspace_fd))
            timed = execute_linux_resource_observed_command(
                ["/usr/bin/python3", "-c",
                 "import time; open('started-timeout','w').write('ok'); time.sleep(30)"],
                cwd=session.workspace_root, sandbox=self.sandbox, policy=ctx.policy,
                timeout=1, command_wrapper=ctx.wrap_command_with_resource_receipt)
            case.assertEqual(timed.error, "timeout", timed)
            case.assertIs(timed.cleanup_ok, True)
            case.assertIs(timed.scope_cleanup_ok, True)
            case.assertTrue((session.workspace_root / "started-timeout").is_file())
            case.assertTrue(os.fstat(session.workspace_fd))
        run(self)
