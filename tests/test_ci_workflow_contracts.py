"""CI 工作流必须显式运行安全边界原生回归。"""

from __future__ import annotations

from pathlib import Path
import unittest


class TestLinuxReviewerBoundaryCi(unittest.TestCase):
    def test_linux_native_matrix_requires_real_bubblewrap_reviewer_probe(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        workflow = (repository_root / ".github/workflows/ci.yml").read_text(
            encoding="utf-8",
        )
        required_step = """      - name: Verify Linux read-only Reviewer OS boundary
        if: runner.os == 'Linux'
        run: |
          sudo apt-get update
          sudo apt-get install --yes bubblewrap
          command -v bwrap
          python -m unittest tests.test_isolation.TestSandboxWrapping.test_bwrap_只读Reviewer实际隐藏工单账本且阻断所有写入 -v
          python -m unittest tests.test_isolation.TestSandboxWrapping.test_bwrap_只读Reviewer真实隐藏账本且阻断工作区内外写入 -v
"""

        self.assertIn(
            required_step,
            workflow,
            "Linux native-probe matrix must run the real Bubblewrap Reviewer boundary probe",
        )


if __name__ == "__main__":
    unittest.main()
