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
        # Normalize only the authorized old budget, not whitespace or commands.
        normalized = self.prefix.replace(b"    timeout-minutes: 15\n", b"    timeout-minutes: 25\n", 1)
        self.assertEqual(
            hashlib.sha256(normalized).hexdigest(),
            "b322e73c257fa7271cc50429a16fb940d8296ee08e2cd68c72a44b1d32c0896c",
        )

    def test_entire_signing_job_unchanged(self):
        self.assertEqual(
            hashlib.sha256(self.sign).hexdigest(),
            "839f562f965cd95e6a3bda85ec6425d65d5ab352735e10fb6da469cf1b5a7ba6",
        )
