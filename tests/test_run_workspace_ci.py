"""跨平台 workspace workflow 的测试覆盖合同。"""

from __future__ import annotations

import unittest

from scripts.run_workspace_ci import CROSS_PLATFORM_GIT_OBJECT_TESTS, DEFAULT_MODULES


class TestWorkspaceCiCoverage(unittest.TestCase):
    def test_cross_platform_matrix_selects_os_neutral_git_object_tests(self) -> None:
        self.assertEqual(len(CROSS_PLATFORM_GIT_OBJECT_TESTS), 17)
        self.assertTrue(set(CROSS_PLATFORM_GIT_OBJECT_TESTS).issubset(DEFAULT_MODULES))
        self.assertNotIn(
            "tests.test_r3_regression.TestResultCommitTreeBinding.test_run_task显式参数自动绑定结果commit",
            DEFAULT_MODULES,
            "Windows tree OID is intentionally fail-closed, so do not run this integration case there",
        )
        self.assertNotIn("tests.test_r3_regression.TestResultCommitTreeBinding", DEFAULT_MODULES)
