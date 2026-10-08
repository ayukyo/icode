"""跨平台 workspace workflow 的测试覆盖合同。"""

from __future__ import annotations

import io
import importlib
import os
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from scripts import run_workspace_ci
from scripts.run_workspace_ci import CROSS_PLATFORM_R3_TESTS, DEFAULT_MODULES


class TestWorkspaceCiCoverage(unittest.TestCase):
    def test_workspace_hook_evidence_contract_runs_on_every_platform(self) -> None:
        self.assertIn("tests.test_workspace_hook_contract", DEFAULT_MODULES)

    def test_cli_resume_sandbox_contract_runs_on_every_platform(self) -> None:
        self.assertIn("tests.test_cli_resume_sandbox", DEFAULT_MODULES)

    def test_shared_runtime_budget_contract_runs_on_every_platform(self) -> None:
        self.assertIn("tests.test_shared_runtime_budget", DEFAULT_MODULES)

    def test_rejected_post_transport_runs_on_every_platform(self) -> None:
        self.assertIn("tests.test_workbench_rejected_body", DEFAULT_MODULES)

    def test_cross_platform_matrix_selects_os_neutral_R3_regressions(self) -> None:
        self.assertEqual(len(CROSS_PLATFORM_R3_TESTS), 50)
        self.assertTrue(set(CROSS_PLATFORM_R3_TESTS).issubset(DEFAULT_MODULES))
        required_r3_evidence_tests = {
            "tests.test_r3_regression.TestTaskReviewAndDiffBinding.test_run_task证据锚定真实Git基线和含预存脏改动的快照",
            "tests.test_r3_regression.TestTaskReviewAndDiffBinding.test_SHA256基线自动选择对应tree对象格式",
            "tests.test_r3_regression.TestResultCommitTreeBinding.test_run_task显式参数自动绑定结果commit",
            "tests.test_r3_regression.TestResultCommitTreeBinding.test_run_task成功测试绑定受测tree和结果commit",
            "tests.test_run_workspace_ci.TestWorkspaceCiCoverage.test_cross_platform_matrix_only_names_existing_unittest_methods",
            "tests.test_evidence.TestEvidencePack.test真实task回执经CLI保存导入证据包并独立校验",
            "tests.test_evidence.TestEvidencePack.test_导出器保留JSON字符串中的Unicode行分隔符",
            "tests.test_evidence.TestEvidencePack.test_导出器拒绝非对象事件且在清理旧包前失败",
            "tests.test_evidence.TestEvidencePack.test_导出器拒绝任意事件类型的非对象payload并保留旧包",
            "tests.test_evidence.TestEvidencePack.test_非状态控制事件的空对象payload仍兼容导出和校验",
            "tests.test_evidence.TestEvidencePack.test_导出器拒绝不在SKILL枚举中的事件类型并保留旧包",
            "tests.test_evidence.TestEvidencePack.test_导出器拒绝不符合v1事件Schema的字段并保留旧包",
            "tests.test_evidence.TestEvidencePack.test_导出器拒绝缺失的工单身份且清理旧包前失败",
            "tests.test_evidence.TestEvidencePack.test_导出器不累计保留大量非产物事件payload",
            "tests.test_evidence.TestEvidencePack.test_evidence导入无效回执时返回用户错误且不触碰目标包",
            "tests.test_evidence.TestEvidencePack.test_evidence导入有限浮点回执后可生成并独立校验",
            "tests.test_evidence.TestEvidencePack.test_evidence导入最大嵌套深度回执可生成并独立校验",
            "tests.test_evidence.TestStandaloneVerifier.test_内置和独立校验器对畸形JSON结构返回失败而不抛异常",
            "tests.test_evidence.TestStandaloneVerifier.test_所有Verifier拒绝哈希自洽事件中的非对象payload",
            "tests.test_evidence.TestStandaloneVerifier.test_所有Verifier拒绝哈希自洽但未知的事件类型",
            "tests.test_evidence.TestStandaloneVerifier.test_所有Verifier拒绝哈希自洽但不符合v1事件Schema的包",
            "tests.test_evidence.TestStandaloneVerifier.test_内置和独立Verifier接受Schema允许省略的request_id",
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

    def test_cross_platform_matrix_only_names_existing_unittest_methods(self) -> None:
        for test_id in CROSS_PLATFORM_R3_TESTS:
            module_name, class_name, method_name = test_id.rsplit(".", 2)
            test_case = getattr(importlib.import_module(module_name), class_name)
            with self.subTest(test_id=test_id):
                self.assertTrue(callable(getattr(test_case, method_name, None)))

    def test_posix_workspace_matrix_runs_native_tree_oid_git_differential(self) -> None:
        tree_differential = (
            "tests.test_r3_regression.TestWorktreeGitTreeOID."
            "test_tree_oid与Git写树一致并覆盖忽略项链接和模式"
        )
        if os.name == "posix":
            self.assertIn(tree_differential, DEFAULT_MODULES)
        else:
            self.assertNotIn(tree_differential, DEFAULT_MODULES)

    def test_required_posix_tree_oid_differential_cannot_skip(self) -> None:
        required_test_id = (
            "tests.test_r3_regression.TestWorktreeGitTreeOID."
            "test_tree_oid与Git写树一致并覆盖忽略项链接和模式"
        )

        class SkippedRequiredTest(unittest.TestCase):
            def id(self) -> str:
                return required_test_id

            def runTest(self) -> None:
                self.skipTest("simulated unavailable symlink support")

        suite = unittest.TestSuite([SkippedRequiredTest()])
        with patch.object(
            run_workspace_ci.unittest.defaultTestLoader,
            "loadTestsFromNames",
            return_value=suite,
        ):
            with redirect_stderr(io.StringIO()):
                exit_code = run_workspace_ci.main(
                    modules=(required_test_id,),
                )

        self.assertEqual(exit_code, 1)
