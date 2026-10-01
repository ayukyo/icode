"""跨平台 workspace workflow 的测试覆盖合同。"""

from __future__ import annotations

import unittest

from scripts.run_workspace_ci import CROSS_PLATFORM_R3_TESTS, DEFAULT_MODULES


class TestWorkspaceCiCoverage(unittest.TestCase):
    def test_cross_platform_matrix_selects_os_neutral_R3_regressions(self) -> None:
        self.assertEqual(len(CROSS_PLATFORM_R3_TESTS), 23)
        self.assertTrue(set(CROSS_PLATFORM_R3_TESTS).issubset(DEFAULT_MODULES))
        required_tree_evidence_tests = {
            "tests.test_r3_regression.TestTaskReviewAndDiffBinding.test_run_task证据锚定真实Git基线和含预存脏改动的快照",
            "tests.test_r3_regression.TestTaskReviewAndDiffBinding.test_SHA256基线自动选择对应tree对象格式",
            "tests.test_r3_regression.TestResultCommitTreeBinding.test_run_task显式参数自动绑定结果commit",
            "tests.test_r3_regression.TestResultCommitTreeBinding.test_run_task成功测试绑定受测tree和结果commit",
            "tests.test_evidence.TestEvidencePack.test真实task回执经CLI保存导入证据包并独立校验",
            "tests.test_runner.TestReviewStepReadOnlyContext.test_review阶段无隔离沙箱时命令在启动前拒绝且不产生标记",
        }
        self.assertTrue(required_tree_evidence_tests.issubset(
            CROSS_PLATFORM_R3_TESTS,
        ))
        self.assertNotIn("tests.test_r3_regression.TestResultCommitTreeBinding", DEFAULT_MODULES)
