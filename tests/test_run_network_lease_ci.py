"""GitHub Actions lease-test annotations contain only a safe test identifier."""

from __future__ import annotations

from io import StringIO
import unittest

from tests import _support  # noqa: F401

from scripts.run_network_lease_ci import emit_failure_annotations


class _TestIdentity:
    def __init__(self, identifier: str) -> None:
        self._identifier = identifier

    def id(self) -> str:
        return self._identifier


class TestLeaseCiFailureAnnotations(unittest.TestCase):
    def test_failure_annotation_contains_only_sanitized_test_identity(self) -> None:
        result = unittest.TestResult()
        result.failures.append(
            (_TestIdentity("tests.test_network_lease.test_socket_lifecycle"), "traceback"),
        )
        result.errors.append(
            (_TestIdentity("tests.test_network_lease.test_close_callback"), "traceback"),
        )
        output = StringIO()

        emit_failure_annotations(result, output)

        self.assertEqual(
            output.getvalue().splitlines(),
            [
                "::error title=network-lease-test-failure::"
                "tests.test_network_lease.test_socket_lifecycle (failure)",
                "::error title=network-lease-test-error::"
                "tests.test_network_lease.test_close_callback (error)",
            ],
        )
        self.assertNotIn("traceback", output.getvalue())

    def test_failure_annotation_neutralizes_workflow_command_characters(self) -> None:
        result = unittest.TestResult()
        result.failures.append(
            (_TestIdentity("case\n::error::injected"), "not emitted"),
        )
        output = StringIO()

        emit_failure_annotations(result, output)

        self.assertEqual(
            output.getvalue(),
            "::error title=network-lease-test-failure::case___error__injected (failure)\n",
        )


if __name__ == "__main__":
    unittest.main()
