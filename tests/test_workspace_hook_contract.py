"""Hook safety evidence must not depend on shared-runner elapsed time."""

from types import SimpleNamespace
import subprocess
import unittest
from unittest import mock

from tests import test_workspace


class TestWorkspaceHookContract(unittest.TestCase):
    def test_real_hook_contract_is_independent_of_slow_runner_clock(self):
        case = test_workspace.TestWorkspaceManager(
            "test_git创建不执行post_checkout_hook_真实正控有效"
        )
        # Replace only the test module's clock, not the product timeout clock.
        clock = SimpleNamespace(monotonic=mock.Mock(side_effect=[0.0, 2.141]))
        result = unittest.TestResult()
        with mock.patch.object(test_workspace, "time", clock):
            case.run(result)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.failures, [])
        self.assertEqual(result.skipped, [])

    def test_unobservable_positive_control_cannot_pass_hook_contract(self):
        case = test_workspace.TestWorkspaceManager(
            "test_git创建不执行post_checkout_hook_真实正控有效"
        )
        run = subprocess.run

        def omit_control(argv, *args, **kwargs):
            if argv[-3:] == ["checkout", "--detach", "HEAD"]:
                return subprocess.CompletedProcess(argv, 0, "", "")
            return run(argv, *args, **kwargs)

        result = unittest.TestResult()
        with mock.patch.object(test_workspace.subprocess, "run", side_effect=omit_control):
            case.run(result)
        self.assertEqual(result.errors, [])
        self.assertEqual(len(result.failures), 1)
        self.assertIn("正控必须可执行", result.failures[0][1])
