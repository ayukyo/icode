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


if __name__ == "__main__":
    unittest.main()
