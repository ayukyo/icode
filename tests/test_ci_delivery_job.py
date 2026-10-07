"""The main CI job must check every delivery gate without duplicate tests."""

from pathlib import Path
import unittest


class TestCiDeliveryJob(unittest.TestCase):
    def test_full_tests_and_each_delivery_guard_run_once_in_order(self) -> None:
        workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml").read_text(
            encoding="utf-8",
        )
        job = workflow.split("  test:\n", 1)[1].split("\n  verification-output-lifecycle:", 1)[0]
        commands = (
            "run: python -m compileall -q src tests scripts",
            "run: python -m unittest\n",
            "run: python scripts/preflight.py --only secrets\n",
            "run: python scripts/preflight.py --only submodule\n",
        )
        for command in commands:
            self.assertEqual(job.count(command), 1, command)
        self.assertEqual([job.index(c) for c in commands], sorted(job.index(c) for c in commands))
        self.assertNotIn("run: python scripts/preflight.py\n", job)
        self.assertNotIn("continue-on-error:", job)
        self.assertNotIn("if:", job)
        self.assertIn("submodules: recursive", job)
        self.assertIn('python-version: ["3.11", "3.12"]', job)
