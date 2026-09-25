"""策略命令的主机侧执行边界；测试后端仅用于验证 broker，不代表原生隔离。"""

from __future__ import annotations

import json
import os
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

from tests._support import temp_workspace

from icode.execution_broker import execute_policy_command
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


@unittest.skipUnless(os.name == "posix", "R2.2 仅覆盖 POSIX 策略命令")
class TestPolicyCommandBroker(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
