"""宿主 cheap-research gate trace 适配器的确定性合同测试。"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from icode.config import load_settings
from icode.control import ControlPlane
from icode.mcp_gates import TRACE_NAME, record_step_gate_trace


class TestMcpGateTraceAdapter(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = load_settings()
        cls.linter = cls.settings.skill_root / "tools" / "lint_mcp_coverage.py"

    def _ticket(self, out_dir: Path, ticket_id: str = "MCP-GATE-1") -> None:
        ControlPlane(self.settings).create(
            out_dir, ticket_id=ticket_id, requirement="gate trace adapter", birth="plan"
        )

    def _lint(self, out_dir: Path, step: str) -> dict:
        proc = subprocess.run(
            [sys.executable, str(self.linter), str(out_dir), "--strict", "--json", "--step", step],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return json.loads(proc.stdout)

    def test_review_trace_is_complete_and_idempotent(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            out = root / ".icode_output" / ".icode_output_1"
            out.mkdir(parents=True)
            self._ticket(out)
            (out / "02_review.md").write_text("# review\n", encoding="utf-8")
            (out / "review_round_1.json").write_text(
                json.dumps({"round": 1, "new_issues": [], "refuted_issues": [],
                            "pending_verification": []}), encoding="utf-8"
            )
            record_step_gate_trace(
                out, step="review", ticket_id="MCP-GATE-1",
                workspace=Path(__file__).resolve().parents[1],
                skill_root=self.settings.skill_root,
            )
            record_step_gate_trace(
                out, step="review", ticket_id="MCP-GATE-1",
                workspace=Path(__file__).resolve().parents[1],
                skill_root=self.settings.skill_root,
            )
            rows = [json.loads(line) for line in (out / TRACE_NAME).read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows), 2)
            self.assertEqual(
                {row["gate_id"] for row in rows},
                {"review.dedup", "review.result_summary"},
            )
            report = self._lint(out, "review")
            self.assertEqual(report["missing_gate"], 0)
            self.assertEqual(report["schema_errors"], 0)
            self.assertEqual(report["sensitive_data"], 0)

    def test_merge_trace_records_skip_and_unavailable_paths(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            out = root / ".icode_output" / ".icode_output_1"
            out.mkdir(parents=True)
            self._ticket(out, "MCP-GATE-2")
            (out / "review_round_1.json").write_text("{}", encoding="utf-8")
            record_step_gate_trace(
                out, step="merge", ticket_id="MCP-GATE-2", workspace=root,
                skill_root=self.settings.skill_root,
            )
            report = self._lint(out, "merge")
            self.assertEqual(report["missing_gate"], 0)
            self.assertEqual(report["skipped_not_eligible"], 1)

            (out / "review_round_2.json").write_text("{}", encoding="utf-8")
            record_step_gate_trace(
                out, step="merge", ticket_id="MCP-GATE-2", workspace=root,
                skill_root=self.settings.skill_root,
            )
            report = self._lint(out, "merge")
            self.assertEqual(report["missing_gate"], 0)
            self.assertEqual(report["unavailable_before_call"], 1)


if __name__ == "__main__":
    unittest.main()
