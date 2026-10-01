"""跨平台 workspace workflow 的测试覆盖合同。"""

from __future__ import annotations

import unittest

from scripts.run_workspace_ci import CROSS_PLATFORM_R3_TESTS, DEFAULT_MODULES


class TestWorkspaceCiCoverage(unittest.TestCase):
    def test_cross_platform_matrix_selects_os_neutral_R3_regressions(self) -> None:
        self.assertEqual(len(CROSS_PLATFORM_R3_TESTS), 40)
        self.assertTrue(set(CROSS_PLATFORM_R3_TESTS).issubset(DEFAULT_MODULES))
        required_r3_evidence_tests = {
            "tests.test_r3_regression.TestTaskReviewAndDiffBinding.test_run_task证据锚定真实Git基线和含预存脏改动的快照",
            "tests.test_r3_regression.TestTaskReviewAndDiffBinding.test_SHA256基线自动选择对应tree对象格式",
            "tests.test_r3_regression.TestResultCommitTreeBinding.test_run_task显式参数自动绑定结果commit",
            "tests.test_r3_regression.TestResultCommitTreeBinding.test_run_task成功测试绑定受测tree和结果commit",
            "tests.test_evidence.TestEvidencePack.test真实task回执经CLI保存导入证据包并独立校验",
            "tests.test_evidence.TestEvidencePack.test_导出器保留JSON字符串中的Unicode行分隔符",
            "tests.test_evidence.TestEvidencePack.test_导出器拒绝非对象事件且在清理旧包前失败",
            "tests.test_evidence.TestEvidencePack.test_导出器不累计保留大量非产物事件payload",
            "tests.test_evidence.TestEvidencePack.test_evidence导入无效回执时返回用户错误且不触碰目标包",
            "tests.test_evidence.TestEvidencePack.test_evidence导入有限浮点回执后可生成并独立校验",
            "tests.test_evidence.TestEvidencePack.test_evidence导入最大嵌套深度回执可生成并独立校验",
            "tests.test_evidence.TestStandaloneVerifier.test_内置和独立校验器对畸形JSON结构返回失败而不抛异常",
            "tests.test_evidence.TestStandaloneVerifier.test_内置和独立校验器拒绝证据包路径越界",
            "tests.test_evidence.TestStandaloneVerifier.test_内置和独立校验器拒绝固定成员符号链接",
            "tests.test_evidence.TestStandaloneVerifier.test_内置和独立校验器不跟随未登记的外部链接目录",
            "tests.test_evidence.TestStandaloneVerifier.test_内置和独立校验器拒绝证据包中的重复JSON成员名",
            "tests.test_evidence.TestStandaloneVerifier.test_文件摘要采用有界内存分块读取",
            "tests.test_evidence.TestStandaloneVerifier.test_event_chain校验不累计保留非产物事件payload",
            "tests.test_evidence.TestStandaloneVerifier.test_event_chain校验仍拒绝重复event_id",
            "tests.test_evidence.TestStandaloneVerifier.test_所有Verifier拒绝孤立代理项并接受合法代理对",
            "tests.test_evidence.TestStandaloneVerifier.test_所有Verifier拒绝非标准非有限数值",
            "tests.test_evidence.TestStandaloneVerifier.test_内置和独立校验器接受JSON字符串中的Unicode行段符号",
            "tests.test_runner.TestReviewStepReadOnlyContext.test_review阶段无隔离沙箱时命令在启动前拒绝且不产生标记",
        }
        self.assertTrue(required_r3_evidence_tests.issubset(
            CROSS_PLATFORM_R3_TESTS,
        ))
        self.assertNotIn("tests.test_r3_regression.TestResultCommitTreeBinding", DEFAULT_MODULES)
