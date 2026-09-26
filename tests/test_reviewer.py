"""R3 独立 Reviewer 测试：只读上下文 + 证据引用。"""

from __future__ import annotations

import unittest

from tests import _support  # noqa: F401  # Add the repository's src/ to sys.path.

from icode.guard import Decision
from icode.reviewer import (
    SEVERITY_BLOCKING,
    SEVERITY_INFO,
    IndependentReviewer,
    is_review_read_only,
    reviewer_guard,
    verify_read_only,
)
from icode.self_verify import FAILURE_CODE, VerificationEvidence


class ReviewerGuardTestCase(unittest.TestCase):
    def test_精确文件白名单不扩展到同目录文件或后代路径(self) -> None:
        with _support.temp_workspace() as ws:
            from icode.guard import Decision

            changed = ws / "src" / "changed.py"
            changed.parent.mkdir()
            changed.write_text("value = 1\n", encoding="utf-8")
            (changed.parent / "secret.txt").write_text("secret", encoding="utf-8")
            guard = reviewer_guard(ws, allowed_read_files=(changed,))

            self.assertIs(guard.check_read(changed).decision, Decision.ALLOW)
            self.assertIs(
                guard.check_read(changed.parent / "secret.txt").decision,
                Decision.DENY,
            )
            self.assertIs(
                guard.check_read(changed / "child.txt").decision,
                Decision.DENY,
            )
            self.assertIs(
                guard.check_read(ws / ".icode_output" / "ledger.json").decision,
                Decision.DENY,
            )

    def test_只读上下文拒绝写但允许读(self) -> None:
        with _support.temp_workspace() as ws:
            (ws / "readme.md").write_text("x", encoding="utf-8")
            guard = reviewer_guard(ws)
            self.assertTrue(verify_read_only(guard, ws))
            self.assertTrue(is_review_read_only(guard, ws))
            self.assertIs(guard.check_write(str(ws / "probe.md")).decision,
                          Decision.DENY)
            self.assertIs(guard.check_write(str(ws / "readme.md")).decision,
                          Decision.DENY)
            self.assertIn(guard.check_read(str(ws / "readme.md")).decision,
                          (Decision.ALLOW, Decision.REQUIRE_APPROVAL))

    def test_可写作用域不是审查只读(self) -> None:
        with _support.temp_workspace() as ws:
            from icode.guard import Guard, Scope

            writable = Guard(Scope(workspace_root=ws.resolve()))
            self.assertFalse(verify_read_only(writable, ws))


class IndependentReviewerTestCase(unittest.TestCase):
    def make_evidence(self, exit_code: int = 1, **overrides) -> VerificationEvidence:
        base: dict = dict(
            step="code", attempt="1", kind="test",
            command=("python", "-m", "unittest"), exit_code=exit_code,
            output="AssertionError", environment_fingerprint="env-1",
            category=FAILURE_CODE,
        )
        base.update(overrides)
        return VerificationEvidence(**base)

    def test_失败证据产生blocking且引用指纹(self) -> None:
        with _support.temp_workspace() as ws:
            evidence = self.make_evidence(exit_code=1)
            report = IndependentReviewer(workspace=ws).review(
                ["calc.py"], evidence=evidence,
            )
            self.assertTrue(report.read_only_verified)
            self.assertFalse(report.ok)
            self.assertEqual(report.reviewed_files, ["calc.py"])
            blocking = [f for f in report.findings if f.severity == SEVERITY_BLOCKING]
            self.assertEqual(len(blocking), 1)
            self.assertEqual(blocking[0].category, FAILURE_CODE)
            self.assertTrue(blocking[0].evidence_ref)
            from icode.self_verify import evidence_fingerprint

            self.assertEqual(blocking[0].evidence_ref, evidence_fingerprint(evidence))

    def test_通过证据产生info(self) -> None:
        with _support.temp_workspace() as ws:
            report = IndependentReviewer(workspace=ws).review(
                ["calc.py"], evidence=self.make_evidence(exit_code=0),
            )
            self.assertTrue(report.ok)
            info = [f for f in report.findings if f.severity == SEVERITY_INFO]
            self.assertEqual(len(info), 1)

    def test_无证据不算自验证结论(self) -> None:
        with _support.temp_workspace() as ws:
            report = IndependentReviewer(workspace=ws).review(["calc.py"], evidence=None)
            self.assertTrue(report.ok)
            # 没有证据引用时不应产出「通过/失败」的验证性结论
            self.assertEqual(report.findings, [])

    def test_符号链接被审对象拒绝(self) -> None:
        import os
        with _support.temp_workspace() as ws:
            outside = ws.parent / "outside-secret"
            outside.write_text("secret", encoding="utf-8")
            link = ws / "alias.py"
            link.symlink_to(outside)
            report = IndependentReviewer(workspace=ws).review(
                ["alias.py"], evidence=self.make_evidence(exit_code=0),
            )
            self.assertFalse(report.ok)
            self.assertTrue(any(
                f.severity == SEVERITY_BLOCKING and f.category == "side_effect_unknown"
                for f in report.findings
            ))

    def test_只读自检失败时拒绝结论(self) -> None:
        with _support.temp_workspace() as ws:
            from icode.guard import Guard, Scope

            writable_guard = Guard(Scope(workspace_root=ws.resolve()))
            report = IndependentReviewer(workspace=ws, guard=writable_guard).review(
                ["calc.py"], evidence=self.make_evidence(exit_code=1),
            )
            self.assertFalse(report.read_only_verified)
            self.assertFalse(report.ok)
            self.assertIn("拒绝产出结论", report.error)


if __name__ == "__main__":
    unittest.main()
