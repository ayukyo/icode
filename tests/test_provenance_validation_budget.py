"""Narrow finite job budget; no changes to provenance gates or permissions."""

import hashlib
from pathlib import Path
import re
import unittest


class TestProvenanceValidationBudget(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / ".github/workflows/windows-helper-provenance.yml"
        cls.prefix, cls.sign = path.read_bytes().split(b"\n  sign:\n", 1)

    def test_validate_has_finite_25_minute_budget(self):
        values = re.findall(rb"^    timeout-minutes: (\d+)$", self.prefix, re.MULTILINE)
        self.assertEqual(values, [b"25"])

    def test_all_validation_commands_and_permissions_unchanged(self):
        # Freeze the approved Python 3.12 baseline; normalize only the old budget.
        normalized = self.prefix.replace(b"    timeout-minutes: 15\n", b"    timeout-minutes: 25\n", 1)
        self.assertEqual(
            hashlib.sha256(normalized).hexdigest(),
            "18becfb47fe72171db12414a4770fb9fe9dac6858033ff3d38e6a8de4b900fb2",
        )

    def test_entire_signing_job_unchanged(self):
        # Includes the reviewed 48/6/3/14 selections and 71 unique required tests.
        self.assertEqual(
            hashlib.sha256(self.sign).hexdigest(),
            "d5faaac42bdf34bd2afbf4887878c93560c2b60bf5c10500bdd6539b9dcf2d32",
        )
