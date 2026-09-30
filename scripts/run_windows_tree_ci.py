"""Run the native Windows worktree-tree suite with safe Actions output."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import secrets
import sys
import unittest
from pathlib import Path
from typing import TextIO


_SAFE_TEST_ID_CHARACTERS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._"
)
_WINDOWS_TREE_TEST_MODULES = ("tests.test_windows_worktree_tree_oid",)


def _safe_test_id(value: object) -> str:
    """Return a bounded, ASCII-only test ID safe for workflow annotations."""

    if type(value) is not str:
        return "unknown_test"
    safe = "".join(
        character if character in _SAFE_TEST_ID_CHARACTERS else "_"
        for character in value[:256]
    )
    return safe or "unknown_test"


def emit_failure_annotations(result: unittest.TestResult, stream: TextIO) -> None:
    """Emit safe test IDs only; never forward unittest's traceback text."""

    for kind, failed_tests in (
        ("failure", result.failures),
        ("error", result.errors),
    ):
        for test, _traceback in failed_tests:
            test_id = _safe_test_id(test.id())
            print(
                f"::error title=windows-tree-test-{kind}::{test_id} ({kind})",
                file=stream,
            )


def load_windows_tree_suite(
    *, loader: unittest.TestLoader | None = None,
) -> unittest.TestSuite:
    """Load production snapshot and Git-tree-OID contract tests."""

    selected_loader = loader or unittest.defaultTestLoader
    suite = unittest.TestSuite()
    for module_name in _WINDOWS_TREE_TEST_MODULES:
        suite.addTests(selected_loader.loadTestsFromName(module_name))
    return suite


def run_windows_tree_suite(suite: unittest.TestSuite, *, stream: TextIO) -> int:
    """Run tests without exposing arbitrary stdout/stderr as workflow commands."""

    captured_output = StringIO()
    command_token = secrets.token_hex(16)
    print(f"::stop-commands::{command_token}", file=stream, flush=True)
    try:
        with redirect_stdout(captured_output), redirect_stderr(captured_output):
            result = unittest.TextTestRunner(
                stream=captured_output,
                verbosity=2,
                buffer=True,
            ).run(suite)
    finally:
        print(f"::{command_token}::", file=stream, flush=True)
    print(
        "Windows worktree tree tests: "
        f"{result.testsRun} run, {len(result.failures)} failures, "
        f"{len(result.errors)} errors.",
        file=stream,
    )
    emit_failure_annotations(result, stream)
    return 0 if result.wasSuccessful() else 1


def main() -> int:
    repository_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository_root))
    suite = load_windows_tree_suite()
    return run_windows_tree_suite(suite, stream=sys.stdout)


if __name__ == "__main__":
    raise SystemExit(main())
