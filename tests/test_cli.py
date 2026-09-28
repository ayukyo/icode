"""CLI 用户可见事件的安全提示测试。"""

from __future__ import annotations

import contextlib
import io
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from icode.cli import _build_runner


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


if __name__ == "__main__":
    unittest.main()
