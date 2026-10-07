"""Doctor displays evidence already collected without enabling automation."""

from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace
import unittest
from unittest import mock

from tests._support import require_skill, temp_workspace
from icode.cli import cmd_doctor
from icode.config import ConfigError
from icode.isolation import NoIsolation


class TestDoctorConformanceDisplay(unittest.TestCase):
    def _render(self, passed: int, *, executed: bool = True, ready: bool = False) -> str:
        settings = require_skill()
        report = {
            "selected": NoIsolation().describe(), "honest_label": "应用层限制",
            "probes": [], "policy_schema_version": 1,
            "bundled_linux_helper": {"minimal_probe_passed": False, "detail": "未安装"},
            "macos_group_cleanup": {"detail": "未确认"},
            "windows_job_cleanup": {"detail": "未确认"},
            "conformance_contract": {
                "executed": executed,
                "score": {"passed": passed, "total": 10, "platform_critical_passed": ready, "ready": ready},
            },
        }
        output = StringIO()
        with temp_workspace() as root, \
             mock.patch("icode.cli.load_settings", return_value=settings), \
             mock.patch("icode.isolation.capability_report", return_value=report) as collect, \
             mock.patch("icode.cli.resolve_api_key", side_effect=ConfigError("offline")), \
             mock.patch("icode.config.llm_no_proxy", return_value=True), \
             redirect_stdout(output):
            self.assertEqual(cmd_doctor(SimpleNamespace(skill_root=None, workspace=str(root))), 0)
            collect.assert_called_once_with()
        return output.getvalue()

    def test_collected_partial_evidence_is_displayed_as_partial_not_unexecuted(self) -> None:
        for passed in (0, 6):
            with self.subTest(passed=passed):
                output = self._render(passed)
                self.assertIn(f"本次诊断证据：{passed}/10 项已确认", output)
                self.assertNotIn("一致性测试：尚未执行", output)
                self.assertIn("未取得证据的能力仍为未验证", output)
                self.assertIn("不代表完整阶段验收", output)
                self.assertIn("自动模式仍拒绝外部命令", output)

    def test_unexecuted_report_does_not_display_stale_score(self) -> None:
        output = self._render(10, executed=False, ready=True)
        self.assertIn("一致性检查：尚未执行", output)
        self.assertNotIn("10/10", output)
        self.assertIn("自动模式仍拒绝外部命令", output)

    def test_complete_diagnostic_score_is_not_a_product_launch_grant(self) -> None:
        output = self._render(10, ready=True)
        self.assertIn("本次诊断证据：10/10 项已确认", output)
        self.assertIn("不代表完整阶段验收", output)
        self.assertIn("自动模式仍拒绝外部命令", output)
