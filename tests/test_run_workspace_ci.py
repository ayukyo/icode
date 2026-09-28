"""跨平台 workspace workflow 的测试覆盖合同。"""

from __future__ import annotations

import unittest

from scripts.run_workspace_ci import DEFAULT_MODULES


class TestWorkspaceCiCoverage(unittest.TestCase):
    def test_result_commit_tree_reader_is_in_cross_platform_matrix(self) -> None:
        self.assertIn(
            "tests.test_r3_regression.TestResultCommitTreeBinding",
            DEFAULT_MODULES,
        )
