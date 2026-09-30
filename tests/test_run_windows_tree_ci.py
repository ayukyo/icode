"""GitHub Actions annotations for native Windows worktree-tree tests."""

from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import sys
import unittest
from unittest.mock import patch

from tests import _support  # noqa: F401

from scripts.run_windows_tree_ci import (
    emit_failure_annotations,
    load_windows_tree_suite,
    run_windows_tree_suite,
)


class _TestIdentity:
    def __init__(self, identifier: str) -> None:
        self._identifier = identifier

    def id(self) -> str:
        return self._identifier


class TestWindowsTreeCiFailureAnnotations(unittest.TestCase):
    def test_native_windows_job_runs_production_tree_oid_suite(self) -> None:
        class TrackingLoader:
            def __init__(self) -> None:
                self.loaded: list[str] = []

            def loadTestsFromName(self, name: str) -> unittest.TestSuite:
                self.loaded.append(name)
                return unittest.TestSuite()

        loader = TrackingLoader()

        suite = load_windows_tree_suite(loader=loader)  # type: ignore[arg-type]

        self.assertIsInstance(suite, unittest.TestSuite)
        self.assertEqual(loader.loaded, ["tests.test_windows_worktree_tree_oid"])

    def test_failure_and_error_annotations_expose_safe_ids_only(self) -> None:
        result = unittest.TestResult()
        result.failures.append(
            (
                _TestIdentity("tests.test_windows_worktree_tree_oid.test_snapshot"),
                "private traceback and local path",
            ),
        )
        result.errors.append(
            (
                _TestIdentity("tests.test_windows_worktree_tree_oid.test_git_oid"),
                "private exception detail",
            ),
        )
        output = StringIO()

        emit_failure_annotations(result, output)

        self.assertEqual(
            output.getvalue().splitlines(),
            [
                "::error title=windows-tree-test-failure::"
                "tests.test_windows_worktree_tree_oid.test_snapshot (failure)",
                "::error title=windows-tree-test-error::"
                "tests.test_windows_worktree_tree_oid.test_git_oid "
                "(error;exception=unknown)",
            ],
        )
        self.assertNotIn("private", output.getvalue())

    def test_error_summary_keeps_only_allowlisted_class_and_code(self) -> None:
        from scripts import run_windows_tree_ci as wrapper

        summarize = getattr(wrapper, "_safe_error_summary", None)
        self.assertTrue(callable(summarize), "safe_error_summary_missing")
        self.assertEqual(
            summarize(
                "Traceback (most recent call last):\n"
                "WorktreeTreeUnavailable: "
                "windows_directory_entry_change_time_changed:"
                "name=private.txt entry_id=deadbeef"
            ),
            "exception=WorktreeTreeUnavailable;"
            "code=windows_directory_entry_change_time_changed",
        )
        self.assertEqual(
            summarize(
                "Traceback (most recent call last):\n"
                "OSError: snapshot unavailable "
                "(windows_entry_identity_changed:name=private.txt "
                "volume=42 entry_id=deadbeef)"
            ),
            "exception=OSError;phase=snapshot;"
            "code=windows_entry_identity_changed",
        )
        self.assertEqual(
            summarize(
                "Traceback (most recent call last):\n"
                "OSError: snapshot unavailable "
                "(windows_directory_entry_change_time_changed:"
                "name=private.txt);safe_diag="
                "try1_repo_root_git_child+try2_git_metadata_descendant"
            ),
            "exception=OSError;phase=snapshot;"
            "code=windows_directory_entry_change_time_changed;"
            "loc=try1_root_git+try2_git_desc",
        )
        self.assertEqual(
            summarize(
                "OSError: snapshot unavailable "
                "(windows_directory_entry_change_time_changed:private);safe_diag="
                "try1_private.txt+try2_other_descendant"
            ),
            "exception=OSError;phase=snapshot;"
            "code=windows_directory_entry_change_time_changed",
        )
        self.assertEqual(
            summarize(
                "OSError: snapshot unavailable "
                "(unrecognized_private_code:name=private.txt)"
            ),
            "exception=OSError",
        )
        self.assertEqual(
            summarize(
                "Traceback (most recent call last):\n"
                "PermissionError: [WinError 5] Access is denied: "
                "'C:\\\\private\\\\repo\\\\secret.txt'"
            ),
            "exception=PermissionError;winerror=5",
        )
        self.assertEqual(
            summarize("AssertionError: private message and ::error injection"),
            "exception=AssertionError",
        )

    def test_error_annotation_emits_safe_summary_without_traceback_fields(self) -> None:
        result = unittest.TestResult()
        result.errors.append(
            (
                _TestIdentity("tests.test_windows_worktree_tree_oid.test_tree"),
                "Traceback (most recent call last):\n"
                "OSError: snapshot unavailable "
                "(windows_directory_entry_change_time_changed:"
                "name=private.txt volume=42 entry_id=deadbeef) "
                "::error::private-injection",
            ),
        )
        output = StringIO()

        emit_failure_annotations(result, output)

        text = output.getvalue()
        self.assertIn(
            "(error;exception=OSError;phase=snapshot;"
            "code=windows_directory_entry_change_time_changed)",
            text,
        )
        for private_value in (
            "private.txt", "volume=42", "deadbeef", "private-injection",
        ):
            self.assertNotIn(private_value, text)

    def test_annotation_neutralizes_controls_unicode_and_bounds_test_id(self) -> None:
        result = unittest.TestResult()
        result.failures.append(
            (
                _TestIdentity("案例\n::error::injected" + "x" * 300),
                "not emitted",
            ),
        )
        output = StringIO()

        emit_failure_annotations(result, output)

        annotation = output.getvalue().rstrip("\n")
        payload = annotation.split("::", 2)[-1]
        safe_id = payload.removesuffix(" (failure)")
        self.assertEqual(safe_id, "_____error__injected" + "x" * 236)
        self.assertLessEqual(len(safe_id), 256)
        self.assertEqual(len(output.getvalue().splitlines()), 1)

    def test_runner_discards_raw_unittest_traceback_output(self) -> None:
        class FailingTest(unittest.TestCase):
            def runTest(self) -> None:
                print("::error::injected stdout command")
                print("::warning::injected stderr command", file=sys.stderr)
                self.fail("private detail\n::error::injected annotation")

        output = StringIO()
        raw_stdout = StringIO()

        with patch(
            "scripts.run_windows_tree_ci.secrets.token_hex",
            return_value="test-token",
        ):
            with redirect_stdout(raw_stdout):
                exit_code = run_windows_tree_suite(
                    unittest.TestSuite([FailingTest()]),
                    stream=output,
                )

        self.assertEqual(exit_code, 1)
        self.assertEqual(
            output.getvalue().splitlines()[:2],
            ["::stop-commands::test-token", "::test-token::"],
        )
        self.assertIn("1 run, 1 failures, 0 errors", output.getvalue())
        self.assertIn("windows-tree-test-failure", output.getvalue())
        self.assertNotIn("private detail", output.getvalue())
        self.assertNotIn("::error::injected", output.getvalue())
        self.assertNotIn("::warning::injected", output.getvalue())
        self.assertEqual(raw_stdout.getvalue(), "")

    def test_runner_resumes_workflow_commands_if_suite_raises(self) -> None:
        class ExplodingSuite(unittest.TestSuite):
            def run(self, result: unittest.TestResult, debug: bool = False):
                raise RuntimeError("not forwarded")

        output = StringIO()
        with patch(
            "scripts.run_windows_tree_ci.secrets.token_hex",
            return_value="test-token",
        ):
            with self.assertRaisesRegex(RuntimeError, "not forwarded"):
                run_windows_tree_suite(ExplodingSuite(), stream=output)

        self.assertEqual(
            output.getvalue().splitlines(),
            ["::stop-commands::test-token", "::test-token::"],
        )


if __name__ == "__main__":
    unittest.main()
