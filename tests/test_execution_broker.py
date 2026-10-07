"""策略命令的主机侧执行边界；测试后端仅用于验证 broker，不代表原生隔离。"""

from __future__ import annotations

from contextlib import ExitStack
import errno
import json
import os
import selectors
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

from tests._support import temp_workspace

from icode.execution_broker import execute_policy_command
from icode import execution_broker
from icode.isolation import PreparedCommand
from icode.sandbox_policy import NetworkMode, SandboxPolicy
from icode.tools import ToolContext, default_registry


class _TestOnlyPolicyBackend:
    is_real_isolation = True

    def describe(self) -> dict[str, str]:
        return {"claim": "test-only-policy-wrapper"}

    def wrap_policy(self, argv: list[str], *, policy: SandboxPolicy, network: bool = False) -> list[str]:
        return list(argv)


def _context(root: Path, *, wall_timeout: int = 5, output_limit: int = 1024) -> ToolContext:
    policy = SandboxPolicy(
        schema_version=1, run_id="broker-test", ticket_id="broker-test", step="code",
        workspace_root=root, read_roots=(root,), write_roots=(root,),
        deny_read_roots=(), deny_write_roots=(root / ".git",),
        network_mode=NetworkMode.DENY, allowed_domains=(), process_limit=8,
        wall_timeout_seconds=wall_timeout, output_limit_bytes=output_limit,
        protected_paths=(root / ".git",),
    )
    return ToolContext(root=root, sandbox=_TestOnlyPolicyBackend(), policy=policy)


class TestUnsupportedPolicyCommandBackend(unittest.TestCase):
    def test_不支持的平台明确提示命令未启动(self) -> None:
        with temp_workspace() as raw_root:
            root = raw_root.resolve()
            context = _context(root)
            command_secret = "ICODE_UNSUPPORTED_PLATFORM_COMMAND_SENTINEL"

            def execute_on_unsupported_platform(*args, **kwargs):
                if os.name != "posix":
                    return execute_policy_command(*args, **kwargs)
                with mock.patch("icode.execution_broker.os.name", "nt"):
                    return execute_policy_command(*args, **kwargs)

            with (
                mock.patch(
                    "icode.tools.builtin.execute_policy_command",
                    side_effect=execute_on_unsupported_platform,
                ),
                mock.patch("icode.execution_broker.subprocess.Popen") as process_start,
            ):
                result = default_registry().invoke("run_command", context, {
                    "argv": [sys.executable, "-c", "pass", command_secret],
                })

            process_start.assert_not_called()
            self.assertFalse(result.ok)
            self.assertEqual(result.meta["error"], "unsupported_platform")
            self.assertEqual(result.meta["error_code"], "unsupported_platform")
            self.assertIs(result.meta["payload_started"], False)
            self.assertIsNone(result.meta["exit_code"])
            self.assertEqual(result.meta["cleanup_scope"], "not_started")
            self.assertIn("命令未启动", result.content)
            self.assertNotIn("exit=None", result.content)
            self.assertNotIn(command_secret, result.content)


@unittest.skipUnless(os.name == "posix", "R2.2 仅覆盖 POSIX 策略命令")
class TestPolicyCommandBroker(unittest.TestCase):
    def test_prepared_policy_command_preserves_descriptor_and_launcher_cwd(self) -> None:
        with temp_workspace() as raw_root:
            root = raw_root.resolve()
            descriptor = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            policy = _context(root).policy
            assert policy is not None
            prepared = PreparedCommand(
                [
                    sys.executable,
                    "-c",
                    f"import os; assert os.fstat({descriptor}); "
                    "assert os.getcwd() == '/'; print('launch-contract-ok')",
                ],
                pass_fds=(descriptor,),
                cwd="/",
            )
            try:
                result = execute_policy_command(
                    prepared, cwd=root, policy=policy, timeout=5,
                )
            finally:
                os.close(descriptor)

        self.assertIsNone(result.error)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.output.strip(), "launch-contract-ok")

    def test_普通命令非零退出不伪报策略拒绝(self) -> None:
        with temp_workspace() as root:
            context = _context(root.resolve())
            result = default_registry().invoke("run_command", context, {
                "argv": [sys.executable, "-c", "raise SystemExit(13)"],
            })

        self.assertFalse(result.ok)
        self.assertEqual(result.meta["exit_code"], 13)
        self.assertNotIn("error_code", result.meta)

    def test_policy_command_preserves_raw_bytes_for_binary_protocols(self) -> None:
        with temp_workspace() as root:
            root = root.resolve()
            result = execute_policy_command(
                [
                    sys.executable,
                    "-c",
                    "import sys; sys.stdout.buffer.write(bytes((0, 255, 65)))",
                ],
                cwd=root,
                policy=_context(root).policy,
                timeout=5,
            )

            self.assertIsNone(result.error)
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.raw_output, b"\x00\xffA")
            self.assertEqual(result.output, "\x00\ufffdA")

    def test_fractional_timeout_is_enforced_without_rounding_up(self) -> None:
        with temp_workspace() as root:
            root = root.resolve()
            started = time.monotonic()
            result = execute_policy_command(
                [sys.executable, "-c", "import time; time.sleep(2)"],
                cwd=root,
                policy=_context(root, wall_timeout=5).policy,
                timeout=0.2,
            )

            self.assertEqual(result.error, "timeout")
            self.assertTrue(result.cleanup_ok)
            self.assertLess(time.monotonic() - started, 0.8)

    def test_command_close_output_streams_early_still_waits_for_exit(self) -> None:
        import threading

        with temp_workspace() as root:
            root = root.resolve()
            ready = root / "child-ready"
            release = root / "allow-exit"
            script = (
                "import os, time; from pathlib import Path\n"
                f"Path({str(ready)!r}).touch()\n"
                "os.close(1); os.close(2)\n"
                f"while not Path({str(release)!r}).exists(): time.sleep(0.01)\n"
            )
            result_holder = []
            finished = threading.Event()

            def run_command() -> None:
                result_holder.append(execute_policy_command(
                    [sys.executable, "-c", script],
                    cwd=root,
                    policy=_context(root).policy,
                    timeout=3,
                ))
                finished.set()

            worker = threading.Thread(target=run_command, daemon=True)
            worker.start()
            deadline = time.monotonic() + 2
            while not ready.exists() and time.monotonic() < deadline:
                time.sleep(0.005)
            try:
                self.assertTrue(ready.exists(), "child did not reach the stream-close point")
                self.assertFalse(
                    finished.wait(0.1),
                    "EOF on stdout must not be mistaken for command exit",
                )
            finally:
                release.touch()
            worker.join(timeout=3)

            self.assertFalse(worker.is_alive(), "command waiter did not finish")
            self.assertEqual(len(result_holder), 1)
            self.assertIsNone(result_holder[0].error)
            self.assertEqual(result_holder[0].exit_code, 0)

    def test_git_status_environment_is_fixed_and_output_limit_is_tighter(self) -> None:
        with temp_workspace() as root:
            root = root.resolve()
            with mock.patch.dict(
                os.environ,
                {
                    "GIT_DIR": "/host/secret/git",
                    "GIT_INDEX_FILE": "/host/secret/index",
                    "GIT_CONFIG_KEY_0": "core.fsmonitor=evil",
                    "GIT_OPTIONAL_LOCKS": "1",
                },
            ):
                result = execute_policy_command(
                    [
                        sys.executable,
                        "-c",
                        "import json, os; print(json.dumps({k: os.environ.get(k) for k in "
                        "('GIT_DIR', 'GIT_INDEX_FILE', 'GIT_CONFIG_KEY_0', "
                        "'GIT_OPTIONAL_LOCKS', 'GIT_CONFIG_NOSYSTEM', 'GIT_PAGER', 'PATH')}))",
                    ],
                    cwd=root,
                    policy=_context(root).policy,
                    timeout=5,
                    git_status=True,
                    output_limit_bytes=1024,
                )

            self.assertIsNone(result.error)
            environment = json.loads(result.output)
            self.assertEqual(environment["GIT_DIR"], None)
            self.assertEqual(environment["GIT_INDEX_FILE"], None)
            self.assertEqual(environment["GIT_CONFIG_KEY_0"], None)
            self.assertEqual(environment["GIT_OPTIONAL_LOCKS"], "0")
            self.assertEqual(environment["GIT_CONFIG_NOSYSTEM"], "1")
            self.assertEqual(environment["GIT_PAGER"], "cat")
            self.assertEqual(environment["PATH"], "/usr/bin:/bin")

            bounded = execute_policy_command(
                [sys.executable, "-c", "print('abcdefgh')"],
                cwd=root,
                policy=_context(root).policy,
                timeout=5,
                git_status=True,
                output_limit_bytes=4,
            )
            self.assertEqual(bounded.error, "output_limit")
            self.assertTrue(bounded.output_truncated)
            self.assertEqual(bounded.output_bytes, 4)
            self.assertEqual(bounded.raw_output, b"abcd")

    def test_策略命令不继承密钥且回执不含原始参数(self) -> None:
        with temp_workspace() as root:
            ctx = _context(root.resolve())
            secret = "ICODE_TEST_SECRET_DO_NOT_LOG"
            with mock.patch.dict(os.environ, {"ICODE_TEST_SECRET": secret}):
                result = default_registry().invoke("run_command", ctx, {
                    "argv": [sys.executable, "-c", "import os; print(os.getenv('ICODE_TEST_SECRET', 'clean'))", secret],
                })
            self.assertTrue(result.ok, f"{result.content} meta={result.meta}")
            self.assertIn("clean", result.content)
            self.assertNotIn(secret, result.content)
            self.assertNotIn(secret, str(result.meta))
            self.assertEqual(result.meta["policy_hash"], ctx.policy.policy_hash)
            self.assertIn("cleanup_errno", result.meta)
            self.assertEqual(result.meta["cleanup_scope"], "process_group")

    def test_策略命令仍能运行本地_src_布局项目(self) -> None:
        with temp_workspace() as root:
            root = root.resolve()
            (root / "src").mkdir()
            (root / "src" / "project_module.py").write_text("VALUE = 42\n", encoding="utf-8")
            result = default_registry().invoke("run_command", _context(root), {
                "argv": [sys.executable, "-c", "import project_module; print(project_module.VALUE)"],
            })
            self.assertTrue(result.ok, f"{result.content} meta={result.meta}")
            self.assertIn("42", result.content)

    def test_策略命令输出超限即停止且回执有界(self) -> None:
        with temp_workspace() as root:
            ctx = _context(root.resolve(), output_limit=1024)
            result = default_registry().invoke("run_command", ctx, {
                "argv": [sys.executable, "-c", "print('x' * 1000000)"],
            })
            self.assertFalse(result.ok)
            self.assertEqual(result.meta["error"], "output_limit")
            self.assertTrue(result.meta["output_truncated"])
            self.assertLess(len(result.content), 1500)

    def test_策略命令启动失败返回稳定错误(self) -> None:
        with temp_workspace() as root:
            ctx = _context(root.resolve())
            result = default_registry().invoke("run_command", ctx, {
                "argv": [str(root / "not-installed-tool")],
            })
            self.assertFalse(result.ok)
            self.assertEqual(result.meta["error"], "launch_failed")
            self.assertTrue(result.meta["cleanup_ok"])
            self.assertEqual(result.meta["cleanup_scope"], "not_started")
            malformed = default_registry().invoke("run_command", ctx, {
                "argv": ["bad\x00command"],
            })
            self.assertFalse(malformed.ok)
            # 畸形参数在 broker 启动前即由工具入口拒绝。
            self.assertEqual(malformed.meta["error"], "invalid_argv")

    def test_策略超时回收继承管道的子进程(self) -> None:
        with temp_workspace() as root:
            root = root.resolve()
            ctx = _context(root, wall_timeout=1)
            marker = root / "child_survived"
            child = "import time, pathlib; time.sleep(1.5); pathlib.Path('child_survived').touch()"
            script = (
                "import subprocess, sys, time; "
                f"subprocess.Popen([sys.executable, '-c', {child!r}]); "
                "time.sleep(5)"
            )
            start = time.monotonic()
            result = default_registry().invoke("run_command", ctx, {
                "argv": [sys.executable, "-c", script], "timeout": 10,
            })
            self.assertFalse(result.ok)
            self.assertEqual(result.meta["error"], "timeout")
            self.assertTrue(result.meta["cleanup_ok"])
            self.assertLess(time.monotonic() - start, 4.0)
            time.sleep(1.6)
            self.assertFalse(marker.exists(), "超时后子进程仍在写工作区")


@unittest.skipUnless(os.name == "posix", "POSIX broker resource ownership")
class TestPolicyCommandResourceCleanup(unittest.TestCase):
    def _run_with_fault(self, stage: str, fault: BaseException, *, cleanup_errno: int | None = None):
        """Inject only the failing API; launch, kill/reap and pipe are real."""
        processes = []
        real_popen = subprocess.Popen
        real_stop = execution_broker._stop_group
        selector = selectors.DefaultSelector() if stage != "constructor" else None

        def launch(*args, **kwargs):
            process = real_popen(*args, **kwargs)
            processes.append(process)
            return process

        def close_selector():
            assert selector is not None
            real_close()
            raise fault

        def stop_group(process):
            real_stop(process)
            if cleanup_errno is not None:
                # Simulate an unconfirmed cleanup result only after physical
                # reaping; never leave a real process behind for this contract.
                return False, cleanup_errno
            raise fault

        if selector is not None:
            real_close = selector.close
        with temp_workspace() as raw_root:
            root = raw_root.resolve()
            policy = _context(root).policy
            assert policy is not None
            with ExitStack() as patches:
                patches.enter_context(mock.patch.object(
                    execution_broker.subprocess, "Popen", side_effect=launch,
                ))
                patches.enter_context(mock.patch.object(
                    execution_broker.selectors, "DefaultSelector",
                    **({"side_effect": fault} if stage == "constructor" else {"return_value": selector}),
                ))
                if stage == "stop" or cleanup_errno is not None:
                    patches.enter_context(mock.patch.object(
                        execution_broker, "_stop_group", side_effect=stop_group,
                    ))
                if stage not in {"constructor", "stop", "timeout"}:
                    patches.enter_context(mock.patch.object(
                        selector, stage,
                        side_effect=close_selector if stage == "close" else fault,
                    ))
                try:
                    outcome = None
                    caught = None
                    try:
                        outcome = execute_policy_command(
                            [sys.executable, "-c", "import time; time.sleep(5)"],
                            cwd=root, policy=policy, timeout=0.1,
                        )
                    except BaseException as error:
                        caught = error
                    self.assertEqual(len(processes), 1)
                    process = processes[0]
                    # poll() itself can reap a zombie. Check the cached status
                    # first so the test cannot finish the broker's job for it.
                    self.assertIsNotNone(process.returncode, "broker did not reap its child")
                    self.assertIsNotNone(process.poll(), "broker left its child running")
                    self.assertTrue(process.stdout.closed, "broker left its output pipe open")
                    return outcome, caught
                finally:
                    # RED failures must not leave the real short-lived child behind.
                    for process in processes:
                        real_stop(process)
                        if process.stdout is not None:
                            process.stdout.close()
                    if selector is not None:
                        real_close()

    def test_selector_constructor_io_error_returns_failure_after_cleanup(self) -> None:
        fault = OSError(errno.EMFILE, "private-selector-detail", "/private/selector")
        result, caught = self._run_with_fault("constructor", fault)
        self.assertIsNone(caught)
        self.assertEqual(result.error, "read_failed")
        self.assertTrue(result.cleanup_ok)
        self.assertEqual(result.raw_output, b"")
        self.assertNotIn("private-selector", str(result))

    def test_selector_constructor_program_errors_and_interrupts_propagate_after_cleanup(self) -> None:
        for fault in (ValueError("program error"), KeyboardInterrupt(), SystemExit(7)):
            with self.subTest(exception=type(fault).__name__):
                result, caught = self._run_with_fault("constructor", fault)
                self.assertIsNone(result)
                self.assertIs(caught, fault)

    def test_selector_close_failures_propagate_after_process_and_pipe_cleanup(self) -> None:
        for fault in (OSError(errno.EIO, "selector close"), RuntimeError("close"), KeyboardInterrupt()):
            with self.subTest(exception=type(fault).__name__):
                result, caught = self._run_with_fault("close", fault)
                self.assertIsNone(result)
                self.assertIs(caught, fault)

    def test_stop_failure_still_closes_output_pipe(self) -> None:
        fault = RuntimeError("cleanup failed after reaping")
        result, caught = self._run_with_fault("stop", fault)
        self.assertIsNone(result)
        self.assertIs(caught, fault)

    def test_register_and_select_io_errors_keep_existing_failure_contract(self) -> None:
        for stage in ("register", "select"):
            with self.subTest(stage=stage):
                result, caught = self._run_with_fault(stage, OSError(errno.EIO, stage))
                self.assertIsNone(caught)
                self.assertEqual(result.error, "read_failed")
                self.assertTrue(result.cleanup_ok)

    def test_unconfirmed_cleanup_overrides_timeout_and_selector_failure(self) -> None:
        for stage in ("timeout", "constructor"):
            with self.subTest(stage=stage):
                result, caught = self._run_with_fault(
                    stage, OSError(errno.EMFILE, "constructor"), cleanup_errno=errno.EIO,
                )
                self.assertIsNone(caught)
                self.assertEqual(result.error, "cleanup_failed")
                self.assertFalse(result.cleanup_ok)
                self.assertEqual(result.cleanup_errno, errno.EIO)


if __name__ == "__main__":
    unittest.main()
