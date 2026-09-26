"""Run the network lease test module with safe per-test Actions annotations."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import TextIO


_SAFE_TEST_ID_CHARACTERS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._"
)


def _safe_test_id(value: object) -> str:
    """Return a bounded test identifier safe for a workflow-command payload."""

    if type(value) is not str:
        return "unknown_test"
    safe = "".join(
        character if character in _SAFE_TEST_ID_CHARACTERS else "_"
        for character in value[:256]
    )
    return safe or "unknown_test"


def emit_failure_annotations(result: unittest.TestResult, stream: TextIO) -> None:
    """Emit only stable test IDs and failure kinds, never traceback contents."""

    for kind, failed_tests in (
        ("failure", result.failures),
        ("error", result.errors),
    ):
        for test, _traceback in failed_tests:
            test_id = _safe_test_id(test.id())
            print(
                f"::error title=network-lease-test-{kind}::{test_id} ({kind})",
                file=stream,
            )


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    suite = unittest.defaultTestLoader.loadTestsFromName("tests.test_network_lease")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    emit_failure_annotations(result, sys.stdout)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
