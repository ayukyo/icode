"""Keep the full-suite CI budget distinct from product execution limits."""

from pathlib import Path
import re
import unittest


class TestFullSuiteCiBudget(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        workflow = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.job = workflow.split("\n  test:\n", 1)[1].split(
            "\n  packaged-skill-install:\n", 1
        )[0]

    def test_full_suite_has_twenty_five_minute_job_budget(self):
        self.assertEqual(
            re.findall(r"^    timeout-minutes: (\d+)$", self.job, re.MULTILINE),
            ["25"],
        )

    def test_required_gates_run_once_in_order(self):
        commands = re.findall(r"^        run: (.+)$", self.job, re.MULTILINE)
        self.assertEqual(commands, [
            'python -m pip install "setuptools>=80"',
            "python -B -c \"import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_windows_loopback_config_observation.py'); assert s.countTestCases()==12, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))\"",
            "python -B -c \"import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_windows_loopback_notice_budget.py'); assert s.countTestCases()==3, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))\"",
            "python -B -c \"import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_windows_wfp_cab_observation.py'); assert s.countTestCases()==10, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))\"",
            "python -m compileall -q src tests scripts",
            "python -u scripts/run_full_suite_ci.py",
            "python scripts/preflight.py --only secrets",
            "python scripts/preflight.py --only submodule",
        ])

    def test_matrix_and_failure_semantics_remain_required(self):
        self.assertIn('python-version: ["3.12"]', self.job)
        self.assertIn("fail-fast: false", self.job)
        self.assertIn("persist-credentials: false", self.job)
        self.assertIn("submodules: recursive", self.job)
        for bypass in ("continue-on-error:", "if:", "timeout-minutes: 0", "|| true"):
            with self.subTest(bypass=bypass):
                self.assertNotIn(bypass, self.job)
