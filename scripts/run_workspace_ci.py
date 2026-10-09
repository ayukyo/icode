#!/usr/bin/env python3
"""运行跨平台 workspace 回归，并把失败摘要写入 GitHub 检查注解。"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path


# Keep the cross-platform R3 regression matrix bounded while exercising the
# real task-to-tree and task-receipt CLI chains on every workspace platform.
CROSS_PLATFORM_R3_TESTS = (
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
    "tests.test_r3_regression.TestResultCommitTreeBinding.test_commit_tree读取只读对象并且不改用户index",
    "tests.test_r3_regression.TestResultCommitTreeBinding.test_commit_tree读取忽略replace_refs",
    "tests.test_r3_regression.TestResultCommitTreeBinding.test_commit_tree读取支持SHA256对象格式",
    "tests.test_r3_regression.TestResultCommitTreeBinding.test_result_commit只接受完整commit对象SHA",
    "tests.test_r3_regression.TestResultCommitTreeBinding.test_git只读查询清除继承环境且禁止惰性网络取对象",
    "tests.test_r3_regression.TestResultCommitTreeBinding.test_result_commit绑定受测tree且纳入最终回执指纹",
    "tests.test_r3_regression.TestResultCommitTreeBinding.test_result_commit树不匹配时报告失败关闭",
    "tests.test_r3_regression.TestResultCommitTreeBinding.test_不存在的结果commit对象失败关闭并保留请求SHA",
    "tests.test_r3_regression.TestResultCommitTreeBinding.test_commit对象内容与OID不匹配时失败关闭",
    "tests.test_r3_regression.TestResultCommitTreeBinding.test_tree对象内容与OID不匹配时失败关闭",
    "tests.test_r3_regression.TestResultCommitTreeBinding.test_tree对象超出读取预算时失败关闭",
    "tests.test_r3_regression.TestResultCommitTreeBinding.test_commit正文读取预算绑定预查大小",
    "tests.test_r3_regression.TestResultCommitTreeBinding.test_tree正文读取预算绑定预查大小",
    "tests.test_r3_regression.TestResultCommitTreeBinding.test_Git原始对象读取超出输出上限时提前终止",
    "tests.test_r3_regression.TestResultCommitTreeBinding.test_partial_clone缺少tree时拒绝惰性取回",
    "tests.test_r3_regression.TestResultCommitTreeBinding.test无稳定受测tree时拒绝读取结果提交",
    "tests.test_r3_regression.TestResultCommitTreeBinding.test_same_tree的后测commit仅标记内容匹配不倒推测试时序",
)

_CONTRACT_ENGINEERING_PREFIX = "tests.test_contract_engineering.TestContractEngineering."
# Select portable orchestration methods explicitly. POSIX captured-input FD
# proofs are not Windows/native credit and are never hidden DEFAULT skips.
CONTRACT_ENGINEERING_TESTS = tuple(_CONTRACT_ENGINEERING_PREFIX + name for name in (
    "test_policy_code_missing_plan_refuses_before_control_write_and_model",
    "test_wrong_plan_binding_and_unavailable_resource_refuse_before_cp",
    "test_plan_environment_platform_directory_and_tool_drift_refuse_before_cp",
    "test_session_identity_mismatch_refuses_before_cp",
    "test_strict_record_accepts_actual_first_and_replay_responses",
    "test_strict_record_rejects_transport_payload_and_replay_mismatch",
    "test_native_provider_required_and_exception_are_stable_before_adapter",
    "test_host_gate_failure_saves_full_actual_attempt_and_records_failed_cp_run",
    "test_contract_consumes_gate_after_last_artifact_registration",
    "test_reviewer_accepts_policy_and_session_as_explicit_optional_inputs",
    "test_unknown_engineering_evidence_is_blocking_even_without_nonzero_exit",
    "test_resume_engineering_requires_trusted_workspace_policy_plan_and_session",
    "test_engineering_checkpoint_without_identity_cannot_fall_back_to_diagnostic",
    "test_engineering_gate_is_selected_once_in_bounded_ci",
    "test_passed_gate_consumes_real_reviewer_read_submit_and_shared_policy",
    "test_completed_operation_request_replay_cannot_rerun_engineering_payload",
    "test_zero_skipped_nonzero_and_unknown_scope_never_receive_quality_credit",
    "test_exception_after_confirmed_start_retains_unknown_action",
    "test_finalizer_context_keeps_policy_session_and_same_shared_budget",
    "test_reviewer_blocking_incomplete_read_nosubmit_budget_and_source_change_block",
    "test_saved_complete_binding_is_rechecked_before_final_step_finish",
    "test_fixed_review_scope_is_only_available_to_policy_engineering_deepcheck",
    "test_resume_checks_actual_attempt_unknown_and_completed_actions_before_model",
    "test_resume_original_baseline_missing_invalid_or_alone_refuses_before_cp",
    "test_resume_original_attempt_reviews_pre_interrupt_and_resumed_changes",
    "test_each_turn_negative_marker_survives_restart_without_granting_authority",
    "test_final_boundary_rechecks_actual_cp_protected_input_after_reviewer",
    "test_incremental_cp_worklist_history_without_old_bodies_blocks_export",
    "test_save_record_and_operation_ack_failures_retain_checkpoint_without_quality",
    "test_contract_and_resume_reject_same_bytes_other_cp_root_before_write_or_model",
    "test_build_only_and_required_not_run_plan_never_gain_quality_credit",
    "test_native_legacy_code_actual_cp_to_independent_pack",
))
POSIX_CONTRACT_ENGINEERING_TESTS = tuple(_CONTRACT_ENGINEERING_PREFIX + name for name in (
    "test_protected_deepcheck_scope_requires_unique_captured_current_cp_facts",
    "test_deepcheck_scope_rejects_missing_gate_changed_list_other_root_and_link",
    "test_scope_source_reads_enforce_existing_host_budget_before_materialization",
    "test_workspace_control_receipts_are_real_git_tree_drift_not_source_credit",
    "test_native_legacy_deepcheck_actual_cp_to_independent_pack",
))

POSIX_R3_TESTS = (
    "tests.test_r3_regression.TestWorktreeGitTreeOID.test_tree_oid与Git写树一致并覆盖忽略项链接和模式",
    *POSIX_CONTRACT_ENGINEERING_TESTS,
)

DEFAULT_MODULES = (
    "tests.test_workspace",
    "tests.test_workspace_hook_contract",
    "tests.test_windows_snapshot_rejection_diagnostic",
    "tests.test_backend_transport_privacy",
    "tests.test_autonomy",
    "tests.test_workbench",
    "tests.test_workbench_rejected_body",
    "tests.test_cli_resume_sandbox",
    "tests.test_shared_runtime_budget",
    "tests.test_contract_finalization",
    # Portable build/transport contracts only; host C fixtures are not native
    # Windows proof and are intentionally not selected as required coverage.
    "tests.test_windows_bootstrap_binding.TestWindowsBootstrapBinding",
    "tests.test_windows_direct_volume.TestWindowsDirectVolume",
    "tests.test_windows_build_context.TestWindowsBuildContext",
    "tests.test_windows_pe_capture.TestWindowsPeCapture",
    "tests.test_windows_pe_reader",
    *CONTRACT_ENGINEERING_TESTS,
    # Host/framework contracts are bounded; optional Go SDK diagnostics are
    # separate and do not stand in for native resource-scope acceptance.
    "tests.test_engineering_verification.TestEngineeringVerification",
    "tests.test_engineering_verification.TestEngineeringAdapters",
    "tests.test_engineering_verification.TestEngineeringResourceDispatch",
    "tests.test_engineering_verification.TestPythonIsolatedTemplate",
    "tests.test_engineering_evidence.TestEngineeringEvidence",
    "tests.test_engineering_evidence.TestEngineeringReceiptValidation",
    "tests.test_engineering_evidence.TestEngineeringEvidencePack",
    # Keep the integration matrix bounded while exercising task-tree capture,
    # result-commit binding, and receipt export/import on each workspace platform.
    *CROSS_PLATFORM_R3_TESTS,
    # The no-follow POSIX tree walker is shared by Linux and macOS; don't add
    # this POSIX-only Git differential to the Windows workspace test selection.
    *(POSIX_R3_TESTS if os.name == "posix" else ()),
)


def _workflow_escape(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def main(modules: tuple[str, ...] = DEFAULT_MODULES) -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        for test, traceback in (*result.failures, *result.errors):
            details = traceback[-1800:] if traceback else "test failed without traceback"
            summary = _workflow_escape(f"{test.id()}:\n{details}")
            print(f"::error title=Workspace regression test failure::{summary}", flush=True)
    # unittest reports skipped tests as successful; this selected Git oracle
    # is required coverage, so only a skip of an explicitly selected POSIX
    # differential makes this bounded workspace matrix fail.
    required_test_ids = frozenset(POSIX_R3_TESTS).intersection(modules)
    skipped_required_tests = sorted({
        test.id()
        for test, _reason in result.skipped
        if test.id() in required_test_ids
    })
    if skipped_required_tests:
        print(
            "Required POSIX workspace regression test was skipped: "
            + ", ".join(skipped_required_tests),
            file=sys.stderr,
        )
        return 1
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main(tuple(sys.argv[1:]) or DEFAULT_MODULES))
