"""真实 Linux run_command 的原生 seccomp 拒绝回执集成测试。"""

from __future__ import annotations

import hashlib
import array
from dataclasses import replace
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import threading
from unittest import mock
from pathlib import Path

from tests._support import temp_workspace

from icode.approvals import ScriptedApprover
from icode.backends import FakeBackend
from icode.guard import Guard, Scope
from icode.isolation import LandlockSandbox
from icode.loop import AgentLoop, LoopConfig
from icode.linux_seccomp_notify import create_seccomp_listener_handoff_channel
from icode.sandbox_policy import NetworkMode, SandboxPolicy
from icode.tools import POLICY_DENIED_USER_MESSAGE, ToolContext, default_registry


@unittest.skipUnless(
    sys.platform.startswith("linux") and shutil.which("cc"),
    "需要 Linux 与 C 编译器验证原生隔离命令路径",
)
class TestLinuxViolationReceipt(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._helper_directory = tempfile.TemporaryDirectory(
            prefix="icode-linux-violation-helper-",
        )
        cls.addClassCleanup(cls._helper_directory.cleanup)
        directory = Path(cls._helper_directory.name)
        source = (
            Path(__file__).resolve().parents[1]
            / "native"
            / "linux"
            / "icode_landlock.c"
        )
        cls._helper = directory / "icode-landlock"
        result = subprocess.run(
            [
                shutil.which("cc") or "cc",
                "-std=c11",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                str(source),
                "-o",
                str(cls._helper),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if result.returncode != 0:
            raise AssertionError(f"native helper compile failed: {result.stderr[-1200:]}")
        cls._manifest = directory / "icode-landlock.sha256"
        cls._manifest.write_text(
            hashlib.sha256(cls._helper.read_bytes()).hexdigest() + "\n",
            encoding="ascii",
        )

    def _context(self, root: Path) -> ToolContext:
        root = root.resolve()
        policy = SandboxPolicy(
            schema_version=1,
            run_id="linux-violation-test",
            ticket_id="linux-violation-test",
            step="code",
            workspace_root=root,
            read_roots=(root,),
            write_roots=(root,),
            deny_read_roots=(),
            deny_write_roots=(),
            network_mode=NetworkMode.DENY,
            allowed_domains=(),
            process_limit=8,
            wall_timeout_seconds=8,
            output_limit_bytes=2048,
            protected_paths=(),
        )
        return ToolContext(
            root=root,
            sandbox=LandlockSandbox(
                helper=str(self._helper), manifest=str(self._manifest),
            ),
            policy=policy,
        )

    def _run_python(self, root: Path, code: str, *, timeout: float = 8):
        return self._run_with_context(self._context(root), code, timeout=timeout)

    def _run_with_context(
        self, context: ToolContext, code: str, *, timeout: float = 8,
    ):
        return default_registry().invoke(
            "run_command",
            context,
            {"argv": [sys.executable, "-c", code], "timeout": timeout},
        )

    def test_caught_network_socket_denial_returns_os_enforced_receipt(self) -> None:
        with temp_workspace() as root:
            result = self._run_python(
                root,
                "import socket\n"
                "try:\n"
                "    socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
                "except PermissionError:\n"
                "    print('network denied')\n"
                "else:\n"
                "    raise SystemExit(17)\n",
            )

        self.assertFalse(result.ok)
        self.assertEqual(result.content, POLICY_DENIED_USER_MESSAGE)
        self.assertEqual(result.meta["violation_observer_status"], "complete")
        self.assertEqual(result.meta["error_code"], "policy_denied")
        self.assertEqual(
            result.meta["violation_receipt"],
            {
                "schema_version": 1,
                "enforcement_layer": "os_seccomp_user_notif",
                "os_enforced": True,
                "category": "network_socket",
                "source": "seccomp_user_notif",
                "count": 1,
            },
        )

    def test_multiple_os_denials_share_minimized_receipt_without_raw_syscall_data(self) -> None:
        with temp_workspace() as root:
            result = self._run_python(
                root,
                "import ctypes, errno, platform, socket\n"
                "try:\n"
                "    socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
                "except PermissionError as exc:\n"
                "    assert exc.errno == errno.EPERM, exc.errno\n"
                "else:\n"
                "    raise AssertionError('network socket was not denied')\n"
                "syscall_numbers = {'x86_64': 53, 'amd64': 53, "
                "'aarch64': 199, 'arm64': 199}\n"
                "syscall_number = syscall_numbers[platform.machine().lower()]\n"
                "libc = ctypes.CDLL(None, use_errno=True)\n"
                "libc.syscall.restype = ctypes.c_long\n"
                "sockets = (ctypes.c_int * 2)()\n"
                "ctypes.set_errno(0)\n"
                "status = libc.syscall(syscall_number, socket.AF_INET, "
                "socket.SOCK_STREAM, 0, sockets)\n"
                "assert status == -1 and ctypes.get_errno() == errno.EPERM, "
                "(status, ctypes.get_errno())\n",
            )

        self.assertFalse(result.ok)
        self.assertEqual(result.content, POLICY_DENIED_USER_MESSAGE)
        self.assertEqual(result.meta["violation_observer_status"], "complete")
        self.assertEqual(result.meta["error_code"], "policy_denied")
        receipt = result.meta["violation_receipt"]
        self.assertEqual(
            receipt,
            {
                "schema_version": 1,
                "enforcement_layer": "os_seccomp_user_notif",
                "os_enforced": True,
                "category": "multiple",
                "source": "seccomp_user_notif",
                "count": 2,
            },
        )
        self.assertNotIn("syscall_number", repr(receipt))
        self.assertNotIn("AF_INET", repr(receipt))

    def test_application_output_permission_denied_is_not_os_receipt(self) -> None:
        with temp_workspace() as root:
            result = self._run_python(
                root,
                "print('Permission denied')\n"
                "raise SystemExit(13)\n",
            )

        self.assertFalse(result.ok)
        self.assertEqual(result.meta["exit_code"], 13)
        self.assertEqual(result.meta["violation_observer_status"], "complete")
        self.assertNotIn("violation_receipt", result.meta)

    def test_landlock_file_write_denial_is_not_misattributed_to_seccomp(self) -> None:
        with temp_workspace() as root:
            outside = root.parent / f"icode-landlock-denied-{os.getpid()}-{time.time_ns()}"
            result = self._run_python(
                root,
                "from pathlib import Path\n"
                f"Path({str(outside)!r}).write_text('must not be written')\n",
            )

            self.assertFalse(outside.exists(), "Landlock did not deny the outside write")

        self.assertFalse(result.ok)
        self.assertEqual(result.meta["violation_observer_status"], "complete")
        self.assertNotIn("violation_receipt", result.meta)

    def test_deny_only_run_command_enforces_output_and_timeout_without_os_denial_receipt(
        self,
    ) -> None:
        with temp_workspace() as root:
            context = self._context(root)
            context.policy = replace(context.policy, output_limit_bytes=128)
            output_result = self._run_with_context(
                context,
                "import os; os.write(1, b'x' * 1000000)",
            )

        self.assertFalse(output_result.ok)
        self.assertEqual(output_result.meta["error"], "output_limit")
        self.assertEqual(output_result.meta["output_bytes"], 128)
        self.assertTrue(output_result.meta["output_truncated"])
        self.assertLess(len(output_result.content), 512)
        self.assertNotIn("violation_receipt", output_result.meta)

        with temp_workspace() as root:
            marker = root / "timeout-descendant-survived"
            context = self._context(root)
            context.policy = replace(context.policy, wall_timeout_seconds=2)
            child_code = (
                "import pathlib, time; time.sleep(2.5); "
                f"pathlib.Path({str(marker)!r}).touch()"
            )
            parent_code = (
                "import subprocess, sys, time; "
                f"subprocess.Popen([sys.executable, '-c', {child_code!r}]); "
                "time.sleep(10)"
            )
            started = time.monotonic()
            timeout_result = self._run_with_context(context, parent_code, timeout=8)
            self.assertLess(time.monotonic() - started, 5.5)
            time.sleep(1.0)
            self.assertFalse(
                marker.exists(), "timeout left a same-group descendant running",
            )

        self.assertFalse(timeout_result.ok)
        self.assertEqual(timeout_result.meta["error"], "timeout")
        self.assertTrue(timeout_result.meta["cleanup_ok"])
        self.assertEqual(timeout_result.meta["cleanup_scope"], "process_group")
        self.assertNotIn("violation_receipt", timeout_result.meta)

    def test_AgentLoop事件保留真实原生回执和统一用户提示(self) -> None:
        with temp_workspace() as root:
            context = self._context(root)
            probe_script = root / "network_denial_probe.py"
            probe_script.write_text(
                "import socket\n"
                "try:\n"
                "    socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
                "except PermissionError:\n"
                "    print('network denied')\n"
                "else:\n"
                "    raise SystemExit(17)\n",
                encoding="utf-8",
            )
            events: list[tuple[str, dict]] = []
            loop = AgentLoop(
                backend=FakeBackend([
                    {
                        "content": "",
                        "tool_calls": [{
                            "id": "native-denial",
                            "name": "run_command",
                            "arguments": {
                                "argv": [
                                    sys.executable,
                                    str(probe_script),
                                ],
                                "timeout": 8,
                            },
                        }],
                    },
                    "已根据隔离策略停止。",
                ]),
                registry=default_registry(),
                guard=Guard(Scope(workspace_root=root)),
                ctx=context,
                approver=ScriptedApprover(answers=[True]),
                config=LoopConfig(max_turns=3, max_tool_calls_per_turn=1),
                on_event=lambda kind, payload: events.append((kind, payload)),
            )

            result = loop.run([{"role": "user", "content": "验证网络默认拒绝"}])

        self.assertTrue(result.ok)
        tool_results = [payload for kind, payload in events if kind == "tool_result"]
        self.assertEqual(len(tool_results), 1)
        event = tool_results[0]
        self.assertFalse(event["ok"])
        self.assertEqual(event["meta"]["error_code"], "policy_denied")
        self.assertEqual(event["meta"]["violation_observer_status"], "complete")
        self.assertEqual(
            event["meta"]["violation_receipt"]["enforcement_layer"],
            "os_seccomp_user_notif",
        )
        self.assertEqual(
            event["meta"]["violation_receipt"]["category"], "network_socket",
        )
        self.assertEqual(event["user_message"], POLICY_DENIED_USER_MESSAGE)

    def test_allowed_unix_socketpair_does_not_emit_violation_receipt(self) -> None:
        with temp_workspace() as root:
            result = self._run_python(
                root,
                "import socket\n"
                "left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)\n"
                "left.sendall(b'ok')\n"
                "assert right.recv(2) == b'ok'\n"
                "left.close(); right.close()\n"
                "print('unix socketpair allowed')\n",
            )

        self.assertTrue(result.ok, f"{result.content} meta={result.meta}")
        self.assertEqual(result.meta["violation_observer_status"], "complete")
        self.assertNotIn("violation_receipt", result.meta)

    def test_ordinary_exit_13_does_not_emit_violation_receipt(self) -> None:
        with temp_workspace() as root:
            result = self._run_python(root, "raise SystemExit(13)")

        self.assertFalse(result.ok)
        self.assertEqual(result.meta["exit_code"], 13)
        self.assertEqual(result.meta["violation_observer_status"], "complete")
        self.assertNotIn("error_code", result.meta)
        self.assertNotIn("violation_receipt", result.meta)

    def test_policy_workspace_must_match_tool_context_root_before_payload(self) -> None:
        with temp_workspace() as root:
            context = self._context(root)
            context.policy = replace(
                context.policy,
                workspace_root=root.parent,
                read_roots=(root.parent,),
                write_roots=(root.parent,),
            )
            marker = root / "mismatched-policy-payload-started"
            result = self._run_with_context(
                context,
                f"from pathlib import Path; Path({str(marker)!r}).write_text('bad')",
            )
            self.assertFalse(marker.exists(), "payload ran with a broader policy workspace")

        self.assertFalse(result.ok)
        self.assertEqual(result.meta["error"], "isolation_unavailable")

    def test_policy_context_cannot_run_in_read_only_workspace_mode(self) -> None:
        with temp_workspace() as root:
            context = self._context(root)
            context.read_only_workspace = True
            marker = root / "readonly-policy-payload-started"
            result = self._run_with_context(
                context,
                f"from pathlib import Path; Path({str(marker)!r}).write_text('bad')",
            )
            self.assertFalse(marker.exists(), "payload ran under an unsupported read-only policy")

        self.assertFalse(result.ok)
        self.assertEqual(result.meta["error"], "isolation_unavailable")

    def test_expired_observer_start_deadline_never_acks_payload(self) -> None:
        with temp_workspace() as root:
            marker = root / "expired-observer-payload-started"
            original_parse_handoff = (
                __import__("icode.linux_seccomp_notify", fromlist=["_parse_handoff"])
                ._parse_handoff
            )

            def delay_observer_ready(control, *, timeout_seconds):
                handoff = original_parse_handoff(
                    control,
                    timeout_seconds=timeout_seconds,
                )
                time.sleep(0.15)
                return handoff

            with mock.patch(
                "icode.linux_seccomp_notify._parse_handoff",
                side_effect=delay_observer_ready,
            ):
                result = self._run_python(
                    root,
                    f"from pathlib import Path; Path({str(marker)!r}).write_text('bad')",
                    timeout=0.05,
                )
            self.assertFalse(marker.exists(), "payload ran after the observer deadline expired")

        self.assertFalse(result.ok)
        self.assertEqual(result.meta["violation_observer_status"], "incomplete")

    def test_observer_initialization_failure_never_acks_payload(self) -> None:
        class BrokenPoller:
            def register(self, *_args, **_kwargs):
                raise RuntimeError("injected observer setup failure")

        with temp_workspace() as root:
            marker = root / "observer-init-failure-payload-started"
            with (
                mock.patch(
                    "icode.linux_seccomp_notify.select.poll",
                    return_value=BrokenPoller(),
                ),
                mock.patch("threading.excepthook", lambda _args: None),
            ):
                result = self._run_python(
                    root,
                    f"from pathlib import Path; Path({str(marker)!r}).write_text('bad')",
                    timeout=1,
                )
            self.assertFalse(marker.exists(), "payload ran without a live observer")

        self.assertFalse(result.ok)
        self.assertEqual(result.meta["violation_observer_status"], "incomplete")

    def test_observer_thread_start_failure_closes_listener_descriptor(self) -> None:
        from icode import linux_seccomp_notify

        received_descriptors: list[int] = []
        original_parse_handoff = linux_seccomp_notify._parse_handoff
        original_thread_start = threading.Thread.start

        def capture_handoff(control, *, timeout_seconds):
            handoff = original_parse_handoff(
                control,
                timeout_seconds=timeout_seconds,
            )
            received_descriptors.append(handoff[0])
            return handoff

        def fail_observer_thread_start(thread, *args, **kwargs):
            if thread.name == "icode-seccomp-violation-monitor":
                raise RuntimeError("injected thread resource failure")
            return original_thread_start(thread, *args, **kwargs)

        with temp_workspace() as root:
            marker = root / "observer-thread-start-failure-payload-started"
            with (
                mock.patch(
                    "icode.linux_seccomp_notify._parse_handoff",
                    side_effect=capture_handoff,
                ),
                mock.patch.object(
                    threading.Thread,
                    "start",
                    new=fail_observer_thread_start,
                ),
            ):
                result = self._run_python(
                    root,
                    f"from pathlib import Path; Path({str(marker)!r}).write_text('bad')",
                    timeout=1,
                )
            self.assertFalse(marker.exists(), "payload ran without a started observer thread")

        self.assertFalse(result.ok)
        self.assertEqual(len(received_descriptors), 1)
        with self.assertRaises(OSError):
            os.fstat(received_descriptors[0])

    def test_native_helper_rejects_payload_start_when_observer_ack_is_invalid(self) -> None:
        with temp_workspace() as root:
            root = root.resolve()
            context = self._context(root)
            marker = root / "payload-started"
            host_control, sender_control = create_seccomp_listener_handoff_channel()
            wrapped = context.sandbox.wrap_policy_with_violation_receipt(
                [
                    sys.executable,
                    "-c",
                    f"from pathlib import Path; Path({str(marker)!r}).write_text('bad')",
                ],
                policy=context.policy,
                control_socket=sender_control,
            )
            process = subprocess.Popen(
                wrapped,
                cwd=root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                pass_fds=(sender_control.fileno(),),
            )
            sender_control.close()
            received_fds: list[int] = []
            try:
                payload, ancillary, flags, _address = host_control.recvmsg(
                    128,
                    socket.CMSG_SPACE(array.array("i").itemsize * 2),
                )
                self.assertEqual(payload, b"ICODE_SECCOMP_LISTENER_V1")
                self.assertEqual(flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC), 0)
                for level, kind, raw in ancillary:
                    self.assertEqual(level, socket.SOL_SOCKET)
                    self.assertEqual(kind, socket.SCM_RIGHTS)
                    descriptors = array.array("i")
                    descriptors.frombytes(raw[:len(raw) - len(raw) % descriptors.itemsize])
                    received_fds.extend(descriptors)
                self.assertEqual(len(received_fds), 1)
                host_control.sendall(b"invalid observer ack")
                output, _ = process.communicate(timeout=8)
            finally:
                host_control.close()
                sender_control.close()
                for descriptor in received_fds:
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=2)

            self.assertNotEqual(process.returncode, 0, output.decode("utf-8", errors="replace"))
            self.assertFalse(marker.exists(), "payload ran without observer ACK")


if __name__ == "__main__":
    unittest.main()
