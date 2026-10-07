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

    def test_posix_native_lifecycle_runs_broker_resource_cleanup(self) -> None:
        workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml").read_text(
            encoding="utf-8",
        )
        job = workflow.split("  verification-output-lifecycle:\n", 1)[1].split(
            "\n  windows-verification-lifecycle-python312:", 1,
        )[0]
        self.assertIn("os: [ubuntu-latest, macos-latest, macos-15-intel, windows-latest, windows-11-arm]", job)
        self.assertIn(
            "      - name: Verify POSIX command broker resource cleanup\n"
            "        if: runner.os != 'Windows'\n"
            "        run: python -m unittest tests.test_execution_broker.TestPolicyCommandResourceCleanup -v\n",
            job,
        )
