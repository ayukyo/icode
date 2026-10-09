"""Host-owned Python preset contracts; fixtures do not grant native authority."""

from __future__ import annotations

import dataclasses
import importlib
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from icode.autonomy import ExecutionContext
from icode.config import ConfigError
from icode.engineering_verification import VerificationPlan, _executable_identity
from icode.sandbox_policy import NetworkMode, SandboxPolicy
from tests._support import temp_workspace


class TestPythonUnittestPlanProvider(unittest.TestCase):
    def _provider_type(self):
        name = "icode.verification_presets"
        self.assertIsNotNone(importlib.util.find_spec(name), "Python preset module is missing")
        module = importlib.import_module(name)
        provider_type = getattr(module, "PythonUnittestPlanProvider", None)
        self.assertTrue(callable(provider_type), "Python preset provider is missing")
        return provider_type

    def _inputs(self, root, *, step="code", ticket="PRESET-1", run="actual-run"):
        root = root.resolve()
        context = ExecutionContext(ticket, root / "ticket", root, "check", "code_in_progress", ())
        policy = SandboxPolicy(
            1, run, ticket, step, root, (root,), (root,), (), (root / ".git",),
            NetworkMode.DENY, (), 8, 30, 65536, (root / ".git",),
        )
        return context, policy

    def test_factory_interface_exists(self):
        self._provider_type()

    def test_real_interpreter_fixed_argv_steps_limits_and_policy_identity(self):
        provider_type = self._provider_type()
        executable = Path(sys.executable)
        provider = provider_type(executable)
        with temp_workspace() as root:
            context, policy = self._inputs(root)
            plan = provider(context, policy)
            self.assertIs(type(plan), VerificationPlan)
            self.assertEqual(plan.workspace_root, root.resolve())
            self.assertEqual((plan.run_id, plan.ticket_id), (policy.run_id, context.ticket_id))
            self.assertEqual(plan.steps, ("code", "deepcheck"))
            self.assertEqual(len(plan.checks), 1)
            check = plan.checks[0]
            self.assertEqual(check.argv, (
                str(executable), "-I", "-B", "-X", "utf8", "-m", "unittest",
                "discover", "-s", str(root.resolve()), "-t", str(root.resolve()),
            ))
            self.assertEqual(
                (check.check_id, check.kind, check.adapter, check.cwd, check.required),
                ("python-unittest", "test", "unittest_summary_v1", ".", True),
            )
            self.assertEqual((check.timeout_seconds, check.output_limit_bytes), (180, 1024 * 1024))
            self.assertEqual(check.executable_identity, _executable_identity(executable))
            self.assertEqual(plan.workspace_identity, (root.stat().st_dev, root.stat().st_ino))
            self.assertTrue(plan.environment)
            with self.assertRaises(dataclasses.FrozenInstanceError):
                provider.executable = executable

    def test_lexical_launcher_is_preserved_without_resolve_or_path_search(self):
        provider_type = self._provider_type()
        with temp_workspace() as root:
            context, policy = self._inputs(root)
            executable = root.resolve() / "selected-venv" / "bin" / "python"
            with (
                patch("icode.verification_presets._executable_identity", return_value="launch") as startup,
                patch("icode.engineering_verification._executable_identity", return_value="launch") as check_identity,
            ):
                provider = provider_type(executable)
                plan = provider(context, policy)
            self.assertEqual(provider.executable, executable)
            self.assertEqual(plan.checks[0].argv[0], str(executable))
            self.assertEqual([call.args[0] for call in startup.call_args_list], [executable, executable])
            check_identity.assert_called_once_with(executable)

    def test_constructor_rejects_nonabsolute_and_unavailable_without_details(self):
        provider_type = self._provider_type()
        for executable in (None, "", Path("."), Path("python")):
            with self.subTest(executable=executable), self.assertRaises(ConfigError) as caught:
                provider_type(executable)
            self.assertEqual(str(caught.exception), "Python unittest 预设解释器不可用")
        for error in (OSError("PRIVATE_PATH"), RuntimeError("PRIVATE_BODY"), ValueError("PRIVATE_BODY")):
            with (
                self.subTest(error=type(error).__name__),
                patch("icode.verification_presets._executable_identity", side_effect=error),
                self.assertRaises(ConfigError) as caught,
            ):
                provider_type(Path(sys.executable))
            self.assertEqual(str(caught.exception), "Python unittest 预设解释器不可用")
            self.assertNotIn("PRIVATE", str(caught.exception))
            self.assertNotIn(sys.executable, str(caught.exception))

    def test_constructor_fatal_exceptions_preserve_original_object(self):
        provider_type = self._provider_type()
        for error in (MemoryError("fatal"), KeyboardInterrupt("fatal"), SystemExit(19)):
            with (
                self.subTest(error=type(error).__name__),
                patch("icode.verification_presets._executable_identity", side_effect=error),
                self.assertRaises(type(error)) as caught,
            ):
                provider_type(Path(sys.executable))
            self.assertIs(caught.exception, error)

    def test_launch_identity_drift_refuses_before_check_construction(self):
        provider_type = self._provider_type()
        with temp_workspace() as root:
            context, policy = self._inputs(root)
            with patch("icode.verification_presets._executable_identity", side_effect=("startup", "changed")):
                provider = provider_type(Path(sys.executable))
                with patch("icode.verification_presets.VerificationCheck") as check, self.assertRaises(ValueError):
                    provider(context, policy)
                check.assert_not_called()

    def test_check_construction_identity_drift_refuses_before_plan(self):
        provider_type = self._provider_type()
        with temp_workspace() as root:
            context, policy = self._inputs(root)
            with (
                patch("icode.verification_presets._executable_identity", return_value="startup"),
                patch("icode.engineering_verification._executable_identity", return_value="changed"),
            ):
                provider = provider_type(Path(sys.executable))
                with patch("icode.verification_presets.VerificationPlan") as plan, self.assertRaises(ValueError):
                    provider(context, policy)
                plan.assert_not_called()

    def test_wrong_workspace_ticket_step_and_missing_policy_refuse_before_identity(self):
        provider_type = self._provider_type()
        provider = provider_type(Path(sys.executable))
        with temp_workspace() as root, temp_workspace() as other:
            context, policy = self._inputs(root)
            variants = (
                (context, None),
                (context, object()),
                (dataclasses.replace(context, ticket_id="OTHER"), policy),
                (dataclasses.replace(context, workspace=other.resolve()), policy),
                (context, dataclasses.replace(policy, step="plan")),
                (context, dataclasses.replace(policy, step="task")),
            )
            for candidate_context, candidate_policy in variants:
                with (
                    self.subTest(policy=candidate_policy),
                    patch("icode.verification_presets._executable_identity") as identity,
                    self.assertRaises(ValueError),
                ):
                    provider(candidate_context, candidate_policy)
                identity.assert_not_called()

    def test_direct_provider_calls_make_new_plans_for_actual_runs_and_steps(self):
        provider_type = self._provider_type()
        provider = provider_type(Path(sys.executable))
        with temp_workspace() as root:
            context, policy = self._inputs(root)
            first = provider(context, policy)
            second = provider(context, dataclasses.replace(policy, step="deepcheck", run_id="next-run"))
            self.assertIsNot(first, second)
            self.assertEqual((first.run_id, second.run_id), ("actual-run", "next-run"))
            self.assertEqual(first.steps, second.steps)


if __name__ == "__main__":
    unittest.main()
