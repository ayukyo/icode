"""Run the native Windows worktree-tree suite with safe Actions output."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import re
import secrets
import sys
import unittest
from pathlib import Path
from typing import TextIO


_SAFE_TEST_ID_CHARACTERS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._"
)
_WINDOWS_TREE_TEST_MODULES = ("tests.test_windows_worktree_tree_oid",)
_SAFE_EXCEPTION_TYPES = frozenset({
    "AssertionError",
    "CalledProcessError",
    "FileNotFoundError",
    "IndexError",
    "KeyError",
    "NotImplementedError",
    "OSError",
    "OverflowError",
    "PermissionError",
    "RuntimeError",
    "TimeoutError",
    "TypeError",
    "UnicodeError",
    "ValueError",
    "WorktreeTreeUnavailable",
})
_SAFE_WORKTREE_ERROR_CODES = frozenset({
    "windows_directory_entry_change_time_changed",
    "windows_entry_identity_changed",
})
_WINERROR_RE = re.compile(r"\[WinError ([0-9]{1,6})\]")


def _safe_test_id(value: object) -> str:
    """Return a bounded, ASCII-only test ID safe for workflow annotations."""

    if type(value) is not str:
        return "unknown_test"
    safe = "".join(
        character if character in _SAFE_TEST_ID_CHARACTERS else "_"
        for character in value[:256]
    )
    return safe or "unknown_test"


def _safe_error_summary(formatted_traceback: object) -> str:
    """Expose bounded error categories while dropping message/path data."""
    if type(formatted_traceback) is not str:
        return "exception=unknown"
    final_line = next(
        (line.strip() for line in reversed(formatted_traceback.splitlines())
         if line.strip()),
        "",
    )
    exception_name, separator, message = final_line.partition(": ")
    if not separator:
        return "exception=unknown"
    exception_name = exception_name.rsplit(".", 1)[-1]
    if exception_name not in _SAFE_EXCEPTION_TYPES:
        exception_name = "OtherError"
    summary = f"exception={exception_name}"
    if exception_name == "WorktreeTreeUnavailable":
        error_code = message.split(":", 1)[0]
        if error_code in _SAFE_WORKTREE_ERROR_CODES:
            summary += f";code={error_code}"
    elif exception_name == "OSError" and message.startswith(
        "snapshot unavailable (",
    ):
        reason_text = message[len("snapshot unavailable ("):].rstrip(")")
        error_code = reason_text.split(":", 1)[0]
        if error_code in _SAFE_WORKTREE_ERROR_CODES:
            summary += f";phase=snapshot;code={error_code}"
    winerror_match = _WINERROR_RE.search(message)
    if winerror_match is not None and exception_name in {
        "FileNotFoundError", "OSError", "PermissionError", "TimeoutError",
    }:
        summary += f";winerror={winerror_match.group(1)}"
    return summary[:128]


def emit_failure_annotations(result: unittest.TestResult, stream: TextIO) -> None:
    """Emit safe test IDs and bounded error categories, never tracebacks."""

    for kind, failed_tests in (
        ("failure", result.failures),
        ("error", result.errors),
    ):
        for test, formatted_traceback in failed_tests:
            test_id = _safe_test_id(test.id())
            detail = (
                ""
                if kind == "failure"
                else f";{_safe_error_summary(formatted_traceback)}"
            )
            print(
                f"::error title=windows-tree-test-{kind}::"
                f"{test_id} ({kind}{detail})",
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
