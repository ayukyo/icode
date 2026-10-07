"""CLI 用户可见事件的安全提示测试。"""

from __future__ import annotations

import contextlib
import io
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from icode.cli import _build_runner, _native_violation_summary, cmd_evidence, main


class TestCliEvidenceErrors(unittest.TestCase):
    def _args(self):
        return SimpleNamespace(
            skill_root=None, receipt=[], receipt_from=None,
            ticket="ticket-input", dest="pack-output",
        )

    def test_evidence_io_failure_returns_error_without_private_exception_text(self) -> None:
        for error_type in (OSError, PermissionError, FileNotFoundError):
            with self.subTest(error=error_type.__name__):
                error = io.StringIO()
                output = io.StringIO()
                with (
                    patch("icode.cli.load_settings", return_value=SimpleNamespace(gates_json=None)),
                    patch("icode.evidence.load_verification_receipts", return_value=[]),
                    patch("icode.evidence.build_evidence_pack", side_effect=error_type("PRIVATE_IO_PATH")),
                    contextlib.redirect_stderr(error), contextlib.redirect_stdout(output),
                ):
                    code = cmd_evidence(self._args())
                self.assertEqual(code, 2)
                self.assertIn("证据包导出失败", error.getvalue())
                self.assertIn(error_type.__name__, error.getvalue())
                self.assertNotIn("PRIVATE_IO_PATH", error.getvalue())
                self.assertNotIn("Traceback", error.getvalue())
                self.assertNotIn("独立校验", output.getvalue())

    def test_evidence_recovery_error_keeps_backup_location(self) -> None:
        from icode.evidence import EvidenceError

        error = io.StringIO()
        message = "旧包恢复失败；旧包备份保留于：recoverable-backup/previous"
        with (
            patch("icode.cli.load_settings", return_value=SimpleNamespace(gates_json=None)),
            patch("icode.evidence.load_verification_receipts", return_value=[]),
            patch("icode.evidence.build_evidence_pack", side_effect=EvidenceError(message)),
            contextlib.redirect_stderr(error),
        ):
            code = cmd_evidence(self._args())
        self.assertEqual(code, 2)
        self.assertIn(message, error.getvalue())

    def test_main_evidence_io_error_omits_both_paths_and_exception_notes(self) -> None:
        failure = OSError(5, "PRIVATE_IO_MESSAGE", "PRIVATE_SOURCE", None, "PRIVATE_DEST")
        failure.add_note("PRIVATE_RECOVERY_NOTE")
        error = io.StringIO()
        output = io.StringIO()
        with (
            patch("icode.cli.load_settings", return_value=SimpleNamespace(gates_json=None)),
            patch("icode.evidence.load_verification_receipts", return_value=[]),
            patch("icode.evidence.build_evidence_pack", side_effect=failure),
            contextlib.redirect_stderr(error), contextlib.redirect_stdout(output),
        ):
            code = main(["evidence", "--ticket", "ticket-input", "--dest", "pack-output"])
        self.assertEqual(code, 2)
        self.assertIn("证据包导出失败", error.getvalue())
        self.assertIn("OSError", error.getvalue())
        self.assertNotIn("PRIVATE_", error.getvalue())
        self.assertNotIn("独立校验", output.getvalue())


class TestCliToolEvents(unittest.TestCase):
    def test_应用策略拒绝结果显示统一用户提示(self) -> None:
        args = SimpleNamespace(
            backend="fake", key_file="", model="", base_url="", proxy="",
            no_proxy=None, approve=False, budget_tokens=1000, quiet=False,
            isolation="auto",
        )
        output = io.StringIO()

        with (
            patch("icode.backends.build_backend", return_value=object()),
            patch("icode.isolation.select_sandbox", return_value=object()),
            contextlib.redirect_stdout(output),
        ):
            _, _, _, on_event, _ = _build_runner(args)
            on_event("tool_result", {
                "tool": "read_file",
                "ok": False,
                "meta": {"error_code": "policy_denied"},
                "user_message": "此操作超出当前任务范围，已阻止。",
            })

        self.assertIn("[拒绝] 此操作超出当前任务范围，已阻止。", output.getvalue())

    def test_原生拒绝事件显示稳定隔离摘要且不回显参数(self) -> None:
        args = SimpleNamespace(
            backend="fake", key_file="", model="", base_url="", proxy="",
            no_proxy=None, approve=False, budget_tokens=1000, quiet=False,
            isolation="auto",
        )
        output = io.StringIO()

        with (
            patch("icode.backends.build_backend", return_value=object()),
            patch("icode.isolation.select_sandbox", return_value=object()),
            contextlib.redirect_stdout(output),
        ):
            _, _, _, on_event, _ = _build_runner(args)
            on_event("tool_result", {
                "tool": "run_command",
                "ok": False,
                "meta": {
                    "error_code": "policy_denied",
                    "argv": ["python", "-c", "PRIVATE_COMMAND_MARKER"],
                    "violation_receipt": {
                        "schema_version": 1,
                        "enforcement_layer": "os_seccomp_user_notif",
                        "os_enforced": True,
                        "category": "network_socket",
                        "source": "seccomp_user_notif",
                        "count": 1,
                        "private_detail": "PRIVATE_RECEIPT_MARKER",
                    },
                },
                "user_message": "此操作超出当前任务范围，已阻止。",
            })

        rendered = output.getvalue()
        self.assertIn("[系统隔离拦截] network_socket × 1", rendered)
        self.assertIn("此操作超出当前任务范围，已阻止。", rendered)
        self.assertNotIn("PRIVATE_COMMAND_MARKER", rendered)
        self.assertNotIn("PRIVATE_RECEIPT_MARKER", rendered)

    def test_多类别原生拒绝回执仍显示系统隔离摘要(self) -> None:
        args = SimpleNamespace(
            backend="fake", key_file="", model="", base_url="", proxy="",
            no_proxy=None, approve=False, budget_tokens=1000, quiet=False,
            isolation="auto",
        )
        output = io.StringIO()

        with (
            patch("icode.backends.build_backend", return_value=object()),
            patch("icode.isolation.select_sandbox", return_value=object()),
            contextlib.redirect_stdout(output),
        ):
            _, _, _, on_event, _ = _build_runner(args)
            on_event("tool_result", {
                "tool": "run_command",
                "ok": False,
                "meta": {
                    "error_code": "policy_denied",
                    "violation_receipt": {
                        "schema_version": 1,
                        "enforcement_layer": "os_seccomp_user_notif",
                        "os_enforced": True,
                        "category": "multiple",
                        "source": "seccomp_user_notif",
                        "count": 2,
                    },
                },
                "user_message": "此操作超出当前任务范围，已阻止。",
            })

        self.assertIn("[系统隔离拦截] multiple × 2", output.getvalue())

    def test_多类别回执计数不足时不认作原生隔离摘要(self) -> None:
        receipt = {
            "schema_version": 1,
            "enforcement_layer": "os_seccomp_user_notif",
            "os_enforced": True,
            "category": "multiple",
            "source": "seccomp_user_notif",
            "count": 1,
        }

        self.assertIsNone(_native_violation_summary({"violation_receipt": receipt}))

    def test_畸形类别类型的回执安全降级且不抛异常(self) -> None:
        base_receipt = {
            "schema_version": 1,
            "enforcement_layer": "os_seccomp_user_notif",
            "os_enforced": True,
            "source": "seccomp_user_notif",
            "count": 2,
        }

        for category in ([], {}):
            with self.subTest(category_type=type(category).__name__):
                receipt = {**base_receipt, "category": category}
                self.assertIsNone(
                    _native_violation_summary({"violation_receipt": receipt}),
                )

    def test_非零退出码不会误显示为隔离拒绝(self) -> None:
        args = SimpleNamespace(
            backend="fake", key_file="", model="", base_url="", proxy="",
            no_proxy=None, approve=False, budget_tokens=1000, quiet=False,
            isolation="auto",
        )
        output = io.StringIO()

        with (
            patch("icode.backends.build_backend", return_value=object()),
            patch("icode.isolation.select_sandbox", return_value=object()),
            contextlib.redirect_stdout(output),
        ):
            _, _, _, on_event, _ = _build_runner(args)
            on_event("tool_result", {
                "tool": "run_command",
                "ok": False,
                "meta": {"exit_code": 13, "violation_observer_status": "complete"},
            })

        rendered = output.getvalue()
        self.assertIn("失败", rendered)
        self.assertNotIn("拒绝", rendered)
        self.assertNotIn("隔离拦截", rendered)

    def test_原生观察器不完整时提示结果不能判定为成功(self) -> None:
        args = SimpleNamespace(
            backend="fake", key_file="", model="", base_url="", proxy="",
            no_proxy=None, approve=False, budget_tokens=1000, quiet=False,
            isolation="auto",
        )
        output = io.StringIO()

        with (
            patch("icode.backends.build_backend", return_value=object()),
            patch("icode.isolation.select_sandbox", return_value=object()),
            contextlib.redirect_stdout(output),
        ):
            _, _, _, on_event, _ = _build_runner(args)
            on_event("tool_result", {
                "tool": "run_command",
                "ok": False,
                "meta": {
                    "error": "violation_observer_failed",
                    "violation_observer_status": "incomplete",
                    "argv": ["PRIVATE_COMMAND_MARKER"],
                },
                "user_message": "PRIVATE_USER_MESSAGE",
            })

        rendered = output.getvalue()
        self.assertIn("[隔离结果未确认]", rendered)
        self.assertIn("不要据此判断命令成功", rendered)
        self.assertNotIn("拒绝", rendered)
        self.assertNotIn("系统隔离拦截", rendered)
        self.assertNotIn("PRIVATE_COMMAND_MARKER", rendered)
        self.assertNotIn("PRIVATE_USER_MESSAGE", rendered)

    def test_平台后端不支持且确认未启动时显示固定提示(self) -> None:
        args = SimpleNamespace(
            backend="fake", key_file="", model="", base_url="", proxy="",
            no_proxy=None, approve=False, budget_tokens=1000, quiet=False,
            isolation="auto",
        )
        output = io.StringIO()

        with (
            patch("icode.backends.build_backend", return_value=object()),
            patch("icode.isolation.select_sandbox", return_value=object()),
            contextlib.redirect_stdout(output),
        ):
            _, _, _, on_event, _ = _build_runner(args)
            on_event("tool_result", {
                "tool": "run_command",
                "ok": False,
                "meta": {
                    "error_code": "unsupported_platform",
                    "payload_started": False,
                    "argv": ["PRIVATE_COMMAND_MARKER"],
                },
            })

        rendered = output.getvalue()
        self.assertIn("[未启动] 当前平台暂未开放受控命令执行", rendered)
        self.assertNotIn("失败", rendered)
        self.assertNotIn("PRIVATE_COMMAND_MARKER", rendered)


if __name__ == "__main__":
    unittest.main()
