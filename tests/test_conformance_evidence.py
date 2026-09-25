"""R2.2 一致性合同评分闭环测试：真实探针证据 → 十项能力评分。"""

from __future__ import annotations

import unittest

from tests import _support  # noqa: F401  # Add the repository's src/ to sys.path.

from icode.conformance_evidence import (
    ConformanceEvidenceError,
    apply_external_evidence,
    map_probe_checks,
    score_probe_evidence,
)

_CAPABILITY_IDS = {
    "workspace_write_boundary",
    "protected_paths",
    "sensitive_read_boundary",
    "network_default_deny",
    "network_temporary_allowlist",
    "child_inheritance",
    "process_tree_cleanup",
    "resource_limits",
    "uniform_violation",
    "doctor_self_test",
}

_FULL_CHECKS = {
    "workspace_write": True,
    "workspace_read": True,
    "outside_write_denied": True,
    "secret_read_denied": True,
    "child_inherits": True,
    "network_denied": True,
    "protected_write_denied": True,
    "network_allowlist_expiry": True,
}


class MapProbeChecksTestCase(unittest.TestCase):
    def test_最小探针只点亮有直接证据的能力(self) -> None:
        outcomes = map_probe_checks({
            "workspace_write": True,
            "workspace_read": True,
            "outside_write_denied": True,
            "secret_read_denied": True,
            "child_inherits": True,
            "network_denied": True,
        })
        self.assertEqual(
            outcomes["workspace_write_boundary"], True,
        )
        self.assertEqual(outcomes["sensitive_read_boundary"], True)
        self.assertEqual(outcomes["network_default_deny"], True)
        self.assertEqual(outcomes["child_inheritance"], True)
        # 没有独立证据的能力必须保守为 False
        self.assertEqual(outcomes["protected_paths"], False)
        self.assertEqual(outcomes["network_temporary_allowlist"], False)
        self.assertEqual(outcomes["process_tree_cleanup"], False)
        self.assertEqual(outcomes["resource_limits"], False)
        self.assertEqual(outcomes["uniform_violation"], False)
        self.assertEqual(outcomes["doctor_self_test"], False)
        self.assertEqual(set(outcomes), _CAPABILITY_IDS)

    def test_任一直接检查失败则该能力不通过(self) -> None:
        outcomes = map_probe_checks({
            "workspace_write": True,
            "outside_write_denied": False,
        })
        self.assertFalse(outcomes["workspace_write_boundary"])

    def test_非布尔检查被拒绝(self) -> None:
        with self.assertRaises(ConformanceEvidenceError):
            map_probe_checks({"workspace_write": "yes"})


class ApplyExternalEvidenceTestCase(unittest.TestCase):
    def test_none_保持未验证(self) -> None:
        outcomes = map_probe_checks({})
        merged = apply_external_evidence(outcomes)
        self.assertFalse(merged["process_tree_cleanup"])
        self.assertFalse(merged["resource_limits"])

    def test_独立证据点亮对应能力(self) -> None:
        outcomes = map_probe_checks({})
        merged = apply_external_evidence(
            outcomes,
            process_tree_cleanup=True,
            resource_limits=True,
            uniform_violation=True,
            doctor_self_test=True,
        )
        self.assertTrue(merged["process_tree_cleanup"])
        self.assertTrue(merged["resource_limits"])
        self.assertTrue(merged["uniform_violation"])
        self.assertTrue(merged["doctor_self_test"])

    def test_非布尔独立证据被拒绝(self) -> None:
        with self.assertRaises(ConformanceEvidenceError):
            apply_external_evidence({}, resource_limits="yes")


class ScoreProbeEvidenceTestCase(unittest.TestCase):
    def test_完整证据且平台关键项全过可ready(self) -> None:
        report = score_probe_evidence(
            _FULL_CHECKS,
            platform="linux",
            process_tree_cleanup=True,
            resource_limits=True,
            uniform_violation=True,
            doctor_self_test=True,
        )
        self.assertEqual(report["score"]["passed"], 10)
        self.assertEqual(report["score"]["total"], 10)
        self.assertTrue(report["score"]["critical_passed"])
        self.assertTrue(report["score"]["ready"])
        self.assertIn("honest_note", report)
        self.assertEqual(set(report["outcomes"]), _CAPABILITY_IDS)

    def test_最小探针单独不足以ready(self) -> None:
        report = score_probe_evidence(
            {
                "workspace_write": True,
                "workspace_read": True,
                "outside_write_denied": True,
                "secret_read_denied": True,
                "child_inherits": True,
                "network_denied": True,
            },
            platform="linux",
            doctor_self_test=True,
        )
        self.assertLess(report["score"]["passed"], 9)
        self.assertFalse(report["score"]["ready"])

    def test_关键项缺失则永不ready(self) -> None:
        report = score_probe_evidence(
            {
                "workspace_write": True,
                "outside_write_denied": True,
                "secret_read_denied": True,
                "child_inherits": True,
                "network_denied": True,
                "protected_write_denied": True,
                "network_allowlist_expiry": True,
            },
            platform="linux",
            process_tree_cleanup=True,
            resource_limits=True,
            uniform_violation=True,
            doctor_self_test=True,
        )
        # sensitive_read_boundary 需要 secret_read_denied —— 已给出，
        # 这里把 workspace_write_boundary 关键项以外的项全过，
        # 用 network_temporary_allowlist 作为关键项缺失样本。
        outcomes = report["outcomes"]
        # 构造一个关键项失败的样本
        self.assertTrue(outcomes["network_temporary_allowlist"])
        failed_report = score_probe_evidence(
            {
                "workspace_write": True,
                "outside_write_denied": True,
                "secret_read_denied": True,
                "child_inherits": True,
                "network_denied": True,
                "protected_write_denied": True,
            },
            platform="linux",
            process_tree_cleanup=True,
            resource_limits=True,
            uniform_violation=True,
            doctor_self_test=True,
        )
        self.assertFalse(failed_report["outcomes"]["network_temporary_allowlist"])
        self.assertFalse(failed_report["score"]["ready"])

    def test_macos平台例外字段存在(self) -> None:
        report = score_probe_evidence(
            _FULL_CHECKS,
            platform="macos",
            process_tree_cleanup=False,
            process_group_cleanup=True,
            resource_limits=True,
            uniform_violation=True,
            doctor_self_test=True,
        )
        self.assertEqual(report["score"]["platform"], "macos")
        self.assertTrue(report["score"]["platform_critical_passed"])
        self.assertEqual(report["score"]["exception"], "macos_process_group_only")

    def test_非法平台被拒绝(self) -> None:
        with self.assertRaises(ConformanceEvidenceError):
            score_probe_evidence({}, platform="freebsd")

    def test_证据来源逐项可核对(self) -> None:
        report = score_probe_evidence(
            _FULL_CHECKS,
            platform="linux",
            process_tree_cleanup=True,
            resource_limits=True,
            uniform_violation=True,
            doctor_self_test=True,
        )
        evidence = report["evidence"]
        self.assertIn("workspace_write", evidence["workspace_write_boundary"])
        self.assertIn("independent_probe", evidence["process_tree_cleanup"])
        self.assertIn("independent_probe", evidence["resource_limits"])
        # 未验证的能力来源标注 no_direct_evidence / no_independent_evidence
        missing_report = score_probe_evidence({}, platform="linux")
        self.assertEqual(missing_report["evidence"]["sensitive_read_boundary"],
                         ["no_direct_evidence"])


if __name__ == "__main__":
    unittest.main()
