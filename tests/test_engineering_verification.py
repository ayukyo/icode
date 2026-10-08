"""Host-only engineering checks; diagnostic fixtures are not native isolation."""

from __future__ import annotations

import dataclasses
import importlib
import importlib.util
import json
import os
import platform
from pathlib import Path
import shutil
import sys
import time
import unittest
from unittest.mock import patch

from tests._support import temp_workspace
from icode.isolation import NoIsolation
from icode.execution_broker import ExecutionResult
from icode.tools import ToolContext, default_registry


class _EngineeringHelpers:
    def api(self):
        # Missing entry point is a structural FAIL, not a fixture ImportError.
        self.assertIsNotNone(importlib.util.find_spec("icode.engineering_verification"))
        return importlib.import_module("icode.engineering_verification")

    def check(self, api, *, check_id="tests", kind="test", argv=None, **kw):
        return api.VerificationCheck(
            check_id=check_id, kind=kind,
            argv=argv or (sys.executable, "-B", "-m", "unittest"),
            adapter="unittest_summary_v1" if kind == "test" else "exit_status_v1",
            timeout_seconds=5, output_limit_bytes=65536, **kw,
        )

    def plan(self, api, root, checks, **kw):
        return api.VerificationPlan(
            workspace_root=root.resolve(), run_id="engineering-test",
            ticket_id="ENG-1", checks=checks, **kw,
        )

    def execute(self, api, plan, *, ctx=None):
        return api.execute_verification_plan(
            plan, ctx=ctx or ToolContext(root=plan.workspace_root, sandbox=NoIsolation()),
            step="task", attempt="1",
        )

    def fixture(self, root, body="self.assertEqual(2 + 2, 4)"):
        (root / "test_actual.py").write_text(
            "import unittest\nclass Actual(unittest.TestCase):\n"
            "    def test_actual(self):\n        " + body + "\n", encoding="utf-8",
        )


class TestEngineeringVerification(_EngineeringHelpers, unittest.TestCase):
    def test_actual_python_nonzero_test_and_source_window(self):
        api = self.api()
        with temp_workspace() as root:
            self.fixture(root)
            plan = self.plan(api, root, (self.check(api),))
            run = self.execute(api, plan)
            self.assertTrue(run.passed)
            self.assertEqual(run.checks[0].tests_passed, 1)
            self.assertEqual(run.checks[0].status, "passed")
            self.assertEqual(run.plan_digest, plan.digest)
            self.assertEqual(run.source_before, run.source_after)
            self.assertFalse(run.os_enforced)
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["test_actual.py"])

    def test_zero_and_all_skipped_tests_never_pass(self):
        api = self.api()
        for mode in ("empty", "skip"):
            with self.subTest(mode=mode), temp_workspace() as root:
                if mode == "skip":
                    self.fixture(root, "self.skipTest('not run')")
                run = self.execute(api, self.plan(api, root, (self.check(api),)))
                self.assertFalse(run.passed)
                self.assertEqual(run.checks[0].tests_passed, 0)
                self.assertEqual(run.checks[0].status, "failed")

    def test_first_failure_stops_later_commands(self):
        api = self.api()
        with temp_workspace() as root:
            self.fixture(root, "self.fail('actual failure')")
            (root / "later.py").write_text(
                "from pathlib import Path\nPath('later-started').touch()\n", encoding="utf-8",
            )
            checks = (
                self.check(api),
                self.check(api, check_id="later", kind="lint", argv=(sys.executable, "-B", "later.py")),
            )
            run = self.execute(api, self.plan(api, root, checks))
            self.assertFalse(run.passed)
            self.assertEqual([item.status for item in run.checks], ["failed", "not_run"])
            self.assertFalse((root / "later-started").exists())

    def test_multiple_real_checks_aggregate_without_last_exit_override(self):
        api = self.api()
        with temp_workspace() as root:
            self.fixture(root)
            (root / "lint_actual.py").write_text(
                "import ast\nfrom pathlib import Path\nast.parse(Path('test_actual.py').read_text())\n",
                encoding="utf-8",
            )
            checks = (
                self.check(api, check_id="lint", kind="lint", argv=(sys.executable, "-B", "lint_actual.py")),
                self.check(api),
            )
            run = self.execute(api, self.plan(api, root, checks))
            self.assertTrue(run.passed)
            self.assertEqual([item.exit_code for item in run.checks], [0, 0])
            self.assertEqual(run.checks[0].tests_passed, 0)
            self.assertEqual(run.checks[1].tests_passed, 1)

    def test_source_write_is_not_a_successful_verification_window(self):
        api = self.api()
        with temp_workspace() as root:
            self.fixture(root, "__import__('pathlib').Path('changed.txt').write_text('changed')")
            run = self.execute(api, self.plan(api, root, (self.check(api),)))
            self.assertFalse(run.passed)
            self.assertEqual(run.status, "source_changed")
            self.assertNotEqual(run.source_before, run.source_after)
            self.assertEqual(run.checks[0].exit_code, 0)
            self.assertTrue((root / "changed.txt").is_file())

    def test_deep_immutable_plan_and_digest(self):
        api = self.api()
        with temp_workspace() as root:
            check = self.check(api)
            plan = self.plan(api, root, (check,))
            same = self.plan(api, root, (self.check(api),))
            self.assertEqual(plan.digest, same.digest)
            with self.assertRaises(dataclasses.FrozenInstanceError):
                check.required = False
            with self.assertRaises(dataclasses.FrozenInstanceError):
                plan.checks = ()
            other = self.plan(api, root, (self.check(api, check_id="different"),))
            self.assertNotEqual(plan.digest, other.digest)

    def test_empty_build_only_and_nonrequired_test_plans_are_rejected(self):
        api = self.api()
        with temp_workspace() as root:
            for checks in ((), (self.check(api, kind="lint"),), (self.check(api, required=False),)):
                with self.subTest(checks=checks), self.assertRaises(ValueError):
                    self.plan(api, root, checks)

    def test_strict_check_types_limits_cwd_adapter_and_duplicate_ids(self):
        api = self.api()
        with temp_workspace() as root:
            valid = dict(check_id="one", kind="test", argv=(sys.executable, "-B", "-m", "unittest"),
                         adapter="unittest_summary_v1", timeout_seconds=5, output_limit_bytes=1024)
            for changes in (
                {"argv": list(valid["argv"])}, {"argv": "python -m unittest"},
                {"required": 1}, {"timeout_seconds": True}, {"timeout_seconds": float("nan")},
                {"output_limit_bytes": 0}, {"cwd": "../outside"}, {"cwd": str(root)},
                {"adapter": "unknown"}, {"adapter": "exit_status_v1"},
                {"check_id": "a\x00b"}, {"argv": (sys.executable, "\ud800")},
            ):
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    api.VerificationCheck(**dict(valid, **changes))
            with self.assertRaises(ValueError):
                self.plan(api, root, (self.check(api), self.check(api)))

    def test_context_workspace_step_platform_and_readonly_binding_before_launch(self):
        api = self.api()
        with temp_workspace() as root, temp_workspace() as other:
            self.fixture(root)
            plan = self.plan(api, root, (self.check(api),))
            for ctx in (
                ToolContext(root=other, sandbox=NoIsolation()),
                ToolContext(root=root, sandbox=NoIsolation(), read_only_workspace=True),
            ):
                with self.subTest(ctx=ctx), patch("icode.runner._run_unittest_with_bounded_output") as execute:
                    run = self.execute(api, plan, ctx=ctx)
                    self.assertFalse(run.passed)
                    execute.assert_not_called()
            with patch("icode.runner._run_unittest_with_bounded_output") as execute:
                run = api.execute_verification_plan(plan, ctx=ToolContext(root=root), step="review", attempt="1")
                self.assertFalse(run.passed)
                execute.assert_not_called()
            with self.assertRaises(ValueError):
                self.plan(api, root, (self.check(api),), platforms=("Unsupported",))
            foreign = self.plan(api, root, (self.check(api),),
                                platforms=("Windows" if platform.system() != "Windows" else "Linux",))
            with patch("icode.runner._run_unittest_with_bounded_output") as execute:
                run = self.execute(api, foreign)
                self.assertFalse(run.passed)
                execute.assert_not_called()

    def test_output_limit_and_timeout_are_incomplete_not_tests_passed(self):
        api = self.api()
        for body, limits in (
            ("print('x' * 20000)", {"output_limit_bytes": 64}),
            ("__import__('time').sleep(2)", {"timeout_seconds": 1}),
        ):
            with self.subTest(body=body), temp_workspace() as root:
                self.fixture(root, body)
                check = dataclasses.replace(self.check(api), **limits)
                run = self.execute(api, self.plan(api, root, (check,)))
                self.assertFalse(run.passed)
                self.assertEqual(run.checks[0].status, "output_incomplete")
                self.assertIsNone(run.checks[0].output)
                self.assertEqual(run.checks[0].tests_passed, 0)

    def test_tool_replaced_after_freeze_is_rejected_before_execution(self):
        api = self.api()
        with temp_workspace() as root:
            self.fixture(root)
            check = self.check(api)
            plan = self.plan(api, root, (check,))
            # A changed observed identity is transport injection, not a claim
            # that this test changed the user's system interpreter.
            with patch("icode.engineering_verification._executable_identity", return_value="0" * 64), \
                    patch("icode.runner._run_unittest_with_bounded_output") as execute:
                run = self.execute(api, plan)
            self.assertFalse(run.passed)
            self.assertEqual(run.checks[0].status, "tool_changed")
            execute.assert_not_called()

    def test_interruptions_keep_original_object(self):
        api = self.api()
        for error in (KeyboardInterrupt("sentinel"), SystemExit(19)):
            with self.subTest(error=type(error).__name__), temp_workspace() as root:
                self.fixture(root)
                plan = self.plan(api, root, (self.check(api),))
                with patch("icode.runner._run_unittest_with_bounded_output", side_effect=error):
                    with self.assertRaises(type(error)) as caught:
                        self.execute(api, plan)
                self.assertIs(caught.exception, error)

    def test_check_construction_descriptor_cleanup_preserves_exception_priority(self):
        api = self.api()
        cases = (
            (KeyboardInterrupt("read cancel"), OSError("close fault")),
            (SystemExit(41), OSError("close fault")),
            (KeyboardInterrupt("read cancel"), SystemExit(42)),
            (SystemExit(43), KeyboardInterrupt("close cancel")),
            (OSError("read fault"), KeyboardInterrupt("close cancel")),
            (OSError("read fault"), SystemExit(44)),
        )
        for first, following in cases:
            with self.subTest(first=type(first).__name__, following=type(following).__name__):
                real_open, real_read, real_close = os.open, os.read, os.close
                opened, closed, read_descriptors = [], [], []
                def tracked_open(*args, **kwargs):
                    descriptor = real_open(*args, **kwargs)
                    opened.append(descriptor)
                    return descriptor
                def interrupted_read(descriptor, size):
                    real_read(descriptor, size)
                    read_descriptors.append(descriptor)
                    raise first
                def faulty_close(descriptor):
                    real_close(descriptor)
                    closed.append(descriptor)
                    raise following
                observed = None
                try:
                    with patch("icode.engineering_verification.os.open", side_effect=tracked_open), \
                            patch("icode.engineering_verification.os.read", side_effect=interrupted_read), \
                            patch("icode.engineering_verification.os.close", side_effect=faulty_close):
                        try:
                            self.check(api)
                        except BaseException as error:
                            observed = error
                    expected = following if isinstance(first, Exception) else first
                    self.assertIs(observed, expected)
                    self.assertEqual(len(opened), 1)
                    self.assertEqual(read_descriptors, opened)
                    self.assertEqual(closed, opened)
                    for descriptor in opened:
                        with self.assertRaises(OSError):
                            os.fstat(descriptor)
                finally:
                    # Reclaim only this fixture's owned FDs if its RED fails.
                    for descriptor in set(opened):
                        try:
                            os.fstat(descriptor)
                        except OSError:
                            continue
                        real_close(descriptor)

    @unittest.skipUnless(os.name == "posix", "held cache POSIX lifecycle only")
    def test_execute_terminal_cache_cleanup_preserves_exception_priority(self):
        api = self.api()
        cases = (
            (KeyboardInterrupt("remove cancel"), SystemExit(45)),
            (SystemExit(46), KeyboardInterrupt("close cancel")),
            (OSError("remove fault"), KeyboardInterrupt("close cancel")),
            (OSError("remove fault"), SystemExit(47)),
            (OSError("remove fault"), OSError("close fault")),
            (None, OSError("close fault")),
        )
        for first, following in cases:
            with self.subTest(first=type(first).__name__, following=type(following).__name__), temp_workspace() as root:
                fake_go = root / "go"
                shutil.copyfile(sys.executable, fake_go)
                check = api.VerificationCheck(check_id="go", kind="test", adapter="go_test_json_v1",
                    argv=(str(fake_go), "test", "-json", "-count=1", "-p", "1", "-parallel", "1", "-mod=readonly", "./..."))
                plan = self.plan(api, root, (check,))
                real_open, real_dup, real_close = os.open, os.dup, os.close
                real_remove, real_cache_close = api._PinnedVerificationCache.remove, api._PinnedVerificationCache.close
                opened, owners = [], []
                def tracked_open(*args, **kwargs):
                    descriptor = real_open(*args, **kwargs)
                    opened.append(descriptor)
                    return descriptor
                def tracked_dup(descriptor):
                    duplicate = real_dup(descriptor)
                    opened.append(duplicate)
                    return duplicate
                def remove_then_fail(owned):
                    owners.append(owned)
                    real_remove(owned)
                    if first is not None:
                        raise first
                def close_then_fail(owned):
                    real_cache_close(owned)
                    raise following
                # Complete transport facts exercise the terminal host cache
                # lifecycle only; they do not count as native isolation evidence.
                result = api.EngineeringCheckResult("go", "passed", exit_code=0, tests_passed=1,
                    output=b"complete transport fixture", cleanup_ok=True, cleanup_scope="linux_task_scope",
                    cache_owner_cleanup_confirmed=True, scope_cleanup_ok=True,
                    resource_channel_status="complete", violation_observer_status="complete",
                    resource_receipt_sha256="0" * 64)
                observed, run = None, None
                try:
                    with patch("icode.engineering_verification.os.open", side_effect=tracked_open), \
                            patch("icode.engineering_verification.os.dup", side_effect=tracked_dup), \
                            patch("icode.engineering_verification._execute_check", return_value=result), \
                            patch.object(api._PinnedVerificationCache, "remove", remove_then_fail), \
                            patch.object(api._PinnedVerificationCache, "close", close_then_fail):
                        try:
                            run = self.execute(api, plan)
                        except BaseException as error:
                            observed = error
                    if not isinstance(following, Exception):
                        expected = first if first is not None and not isinstance(first, Exception) else following
                        self.assertIs(observed, expected)
                    else:
                        self.assertIsNone(observed)
                        self.assertFalse(run.passed)
                        self.assertEqual(run.status, "cache_cleanup_unconfirmed")
                    self.assertEqual(len(owners), 1)
                    self.assertIsNone(owners[0].descriptor)
                    self.assertIsNone(owners[0].parent_fd)
                    self.assertFalse(owners[0].path.exists())
                    self.assertTrue(opened)
                    for descriptor in set(opened):
                        with self.assertRaises(OSError):
                            os.fstat(descriptor)
                finally:
                    for descriptor in set(opened):
                        try:
                            os.fstat(descriptor)
                        except OSError:
                            continue
                        real_close(descriptor)

    def test_executor_is_not_a_model_tool(self):
        self.api()
        self.assertNotIn("execute_verification_plan", default_registry().names())

    def test_unavailable_source_snapshot_fails_without_launch_or_invented_fingerprint(self):
        api = self.api()
        from icode.workspace_snapshot import WorktreeTreeUnavailable
        for stage in ("before", "after"):
            with self.subTest(stage=stage), temp_workspace() as root:
                self.fixture(root)
                plan = self.plan(api, root, (self.check(api),))
                snapshot = api.snapshot_workspace(root)
                sequence = [WorktreeTreeUnavailable("PRIVATE_SENTINEL")] if stage == "before" else [
                    snapshot, snapshot, WorktreeTreeUnavailable("PRIVATE_SENTINEL")]
                with patch("icode.engineering_verification.snapshot_workspace", side_effect=sequence), \
                        patch("icode.engineering_verification._execute_check", return_value=api.EngineeringCheckResult(
                            "tests", "passed", exit_code=0, tests_passed=1, output=b"fixture", cleanup_ok=True)) as dispatch:
                    run = self.execute(api, plan)
                self.assertFalse(run.passed)
                self.assertEqual(run.status, "source_unavailable")
                self.assertEqual(run.source_after, "")
                self.assertEqual(dispatch.call_count, 0 if stage == "before" else 1)

    def test_first_source_write_stops_later_successful_command(self):
        api = self.api()
        with temp_workspace() as root:
            self.fixture(root, "__import__('pathlib').Path('changed.txt').touch()")
            (root / "later.py").write_text("from pathlib import Path\nPath('later-started').touch()\n", encoding="utf-8")
            checks = (self.check(api), self.check(api, check_id="later", kind="lint",
                                               argv=(sys.executable, "-B", "later.py")))
            run = self.execute(api, self.plan(api, root, checks))
            self.assertFalse(run.passed)
            self.assertEqual(run.status, "source_changed")
            self.assertEqual(run.checks[1].status, "not_run")
            self.assertFalse((root / "later-started").exists())

    def test_policy_broker_exceptions_preserve_original_tool_error_semantics(self):
        self.api()
        from tests.test_execution_broker import _context
        with temp_workspace() as root:
            with patch("icode.tools.builtin.execute_policy_command", side_effect=RuntimeError("sentinel")):
                result = default_registry().invoke("run_command", _context(root.resolve()),
                                                  {"argv": [sys.executable, "-B", "-m", "unittest"]})
            self.assertEqual(result.meta["error"], "tool_exception")

    def test_actual_postspawn_fault_cannot_claim_payload_not_started(self):
        self.api()
        from tests.test_execution_broker import _context
        if os.name != "posix":
            self.skipTest("existing POSIX policy broker diagnostic, not native isolation")
        with temp_workspace() as root:
            marker = root / "actual-started"
            def fail_after_actual_start():
                deadline = time.monotonic() + 1
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(0.005)
                self.assertTrue(marker.exists())
                raise ValueError("post-spawn diagnostic fault")
            with patch("icode.execution_broker.selectors.DefaultSelector", side_effect=fail_after_actual_start):
                result = default_registry().invoke("run_command", _context(root.resolve()),
                    {"argv": [sys.executable, "-I", "-B", "-c",
                              "from pathlib import Path; Path(" + repr(str(marker)) + ").touch()"], "timeout": 3})
            self.assertTrue(marker.exists())
            self.assertEqual(result.meta["error"], "tool_exception")
            self.assertNotEqual(result.meta.get("payload_started"), False)

    def test_selected_venv_launch_path_and_actual_prefix_are_preserved(self):
        api = self.api()
        import venv
        with temp_workspace() as root, temp_workspace() as runtime:
            venv.EnvBuilder(with_pip=False, symlinks=os.name == "posix").create(runtime)
            python = runtime / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            # macOS's launcher canonicalizes parent directories, while the
            # selected executable spelling must still remain unchanged.
            self.fixture(root,
                "self.assertEqual(__import__('pathlib').Path(__import__('sys').prefix).resolve(strict=True), "
                "__import__('pathlib').Path(" + repr(str(runtime)) + ").resolve(strict=True)); "
                "self.assertNotEqual(__import__('pathlib').Path(__import__('sys').prefix).resolve(strict=True), "
                "__import__('pathlib').Path(__import__('sys').base_prefix).resolve(strict=True))")
            check = self.check(api, argv=(str(python), "-B", "-m", "unittest"))
            self.assertEqual(check.argv[0], str(python))
            run = self.execute(api, self.plan(api, root, (check,)))
            self.assertTrue(run.passed, {"status": run.status,
                "checks": [(item.status, item.exit_code, item.error, item.cleanup_scope,
                            item.cleanup_ok) for item in run.checks]})

    @unittest.skipUnless(os.name == "posix", "actual parent-directory alias fixture")
    def test_selected_venv_parent_alias_still_binds_the_same_runtime(self):
        api = self.api()
        import venv
        with temp_workspace() as root, temp_workspace() as parent:
            runtime = parent / "runtime"
            runtime.mkdir()
            alias = parent / "runtime-alias"
            alias.symlink_to(runtime, target_is_directory=True)
            venv.EnvBuilder(with_pip=False, symlinks=True).create(runtime)
            python = alias / "bin/python"
            self.fixture(root,
                "self.assertEqual(__import__('pathlib').Path(__import__('sys').prefix).resolve(strict=True), "
                "__import__('pathlib').Path(" + repr(str(runtime)) + ").resolve(strict=True)); "
                "self.assertNotEqual(__import__('pathlib').Path(__import__('sys').prefix).resolve(strict=True), "
                "__import__('pathlib').Path(__import__('sys').base_prefix).resolve(strict=True))")
            check = self.check(api, argv=(str(python), "-B", "-m", "unittest"))
            self.assertEqual(check.argv[0], str(python))
            run = self.execute(api, self.plan(api, root, (check,)))
            self.assertTrue(run.passed, {"status": run.status,
                "checks": [(item.status, item.exit_code, item.error) for item in run.checks]})

    def test_known_parallel_frontends_require_explicit_bounded_build_jobs(self):
        api = self.api()
        with temp_workspace() as root:
            ninja = root / ("ninja.exe" if os.name == "nt" else "ninja")
            shutil.copyfile(sys.executable, ninja)
            for argv in ((str(ninja),), (str(ninja), "-j"), (str(ninja), "-j7")):
                with self.subTest(argv=argv), self.assertRaises(ValueError):
                    api.VerificationCheck(check_id="build", kind="build", adapter="exit_status_v1", argv=argv)
            for jobs in (1, 6):
                api.VerificationCheck(check_id="build", kind="build", adapter="exit_status_v1",
                                      argv=(str(ninja), "-j" + str(jobs)))
            for name in ("make", "cmake"):
                frontend = root / (name + (".exe" if os.name == "nt" else ""))
                shutil.copyfile(sys.executable, frontend)
                prefix = (str(frontend), "--build", ".", "-j6", "--") if name == "cmake" else (str(frontend),)
                for args in (("--jobs",), ("--jobs=100",), ("--jobs", "100"),
                             ("-kj100",), ("-skj", "7"), ("-Lj100",), ("--jobserver-auth=fifo:/tmp/pool",)):
                    with self.subTest(frontend=name, args=args), self.assertRaises(ValueError):
                        api.VerificationCheck(check_id="build", kind="build", adapter="exit_status_v1", argv=prefix + args)
                for args in (("--jobs=6",), ("--jobs", "1"), ("-kj6",), ("-skj", "1"), ("-Lj6",)):
                    api.VerificationCheck(check_id="build", kind="build", adapter="exit_status_v1", argv=prefix + args)

    def test_process_group_diagnostic_does_not_authorize_cache_owner_cleanup(self):
        api = self.api()
        if os.name != "posix":
            self.skipTest("held cache POSIX lifecycle only")
        with temp_workspace() as root:
            self.fixture(root)
            fake_go = root / ("go.exe" if os.name == "nt" else "go")
            shutil.copyfile(sys.executable, fake_go)
            check = api.VerificationCheck(check_id="go", kind="test", adapter="go_test_json_v1",
                argv=(str(fake_go), "test", "-json", "-count=1", "-p", "1", "-parallel", "1", "-mod=readonly", "./..."))
            observed = api.EngineeringCheckResult("go", "passed", exit_code=0, tests_passed=1,
                output=b"transport diagnostic", cleanup_ok=True, cleanup_scope="process_group")
            with patch("icode.engineering_verification._execute_check", return_value=observed) as dispatch:
                run = self.execute(api, self.plan(api, root, (check, self.check(api))))
            self.assertFalse(run.passed)
            self.assertEqual(run.status, "cache_cleanup_unconfirmed")
            self.assertTrue(any(root.glob(".icode-verification-*")))
            self.assertEqual(run.checks[1].status, "not_run")
            dispatch.assert_called_once()

    @unittest.skipUnless(os.name == "posix", "held cache POSIX lifecycle only")
    def test_actual_cache_delete_recreate_stops_next_command_and_preserves_replacement(self):
        api = self.api()
        with temp_workspace() as root:
            self.fixture(root, "__import__('pathlib').Path('later-started').touch()")
            fake_go = root / "go"
            shutil.copyfile(sys.executable, fake_go)
            script = ("import os, shutil\nfrom pathlib import Path\n"
                      "cache=Path(os.environ['HOME']).parent\nshutil.rmtree(cache)\n"
                      "cache.mkdir()\n(cache/'foreign.txt').write_bytes(b'keep replacement')\n")
            (root / "replace.py").write_text(script, encoding="utf-8")
            checks = (self.check(api, check_id="replace", kind="lint", argv=(sys.executable, "-B", "replace.py")),
                      self.check(api), api.VerificationCheck(check_id="go", kind="test", adapter="go_test_json_v1",
                      argv=(str(fake_go), "test", "-json", "-count=1", "-p", "1", "-parallel", "1", "-mod=readonly", "./...")))
            run = self.execute(api, self.plan(api, root, checks))
            self.assertFalse(run.passed)
            self.assertEqual([item.status for item in run.checks], ["passed", "not_run", "not_run"])
            self.assertFalse((root / "later-started").exists())
            self.assertEqual([p.read_bytes() for p in root.glob(".icode-verification-*/foreign.txt")],
                             [b"keep replacement"])

    @unittest.skipUnless(os.name == "posix", "finite detached writer POSIX diagnostic only")
    def test_actual_detached_cache_writer_prevents_cleanup_and_later_execution(self):
        api = self.api()
        with temp_workspace() as root:
            self.fixture(root, "__import__('pathlib').Path('later-started').touch()")
            fake_go = root / "go"
            shutil.copyfile(sys.executable, fake_go)
            # This trusted fixture's detached child is finite and touches no
            # data. Its live PID demonstrates group cleanup is not tree proof.
            (root / "detach.py").write_text(
                "import subprocess,sys\np=subprocess.Popen([sys.executable,'-I','-B','-c',"
                "'import time; time.sleep(2)'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,"
                "stderr=subprocess.DEVNULL,start_new_session=True)\nprint(p.pid,flush=True)\n", encoding="utf-8")
            go = api.VerificationCheck(check_id="go", kind="test", adapter="go_test_json_v1",
                argv=(str(fake_go), "test", "-json", "-count=1", "-p", "1", "-parallel", "1", "-mod=readonly", "./..."))
            checks = (self.check(api, check_id="detach", kind="lint", argv=(sys.executable, "-B", "detach.py")),
                      self.check(api), go)
            started = time.monotonic()
            try:
                run = self.execute(api, self.plan(api, root, checks))
                self.assertFalse(run.passed)
                self.assertEqual(run.status, "cache_cleanup_unconfirmed")
                self.assertEqual([item.status for item in run.checks], ["passed", "not_run", "not_run"])
                os.kill(int(run.checks[0].output.strip()), 0)
                self.assertTrue(any(root.glob(".icode-verification-*")))
                self.assertFalse((root / "later-started").exists())
            finally:
                # Let only this finite fixture expire before temp cleanup.
                remaining = 2.2 - (time.monotonic() - started)
                if remaining > 0:
                    time.sleep(remaining)

    @unittest.skipUnless(os.name == "posix", "held cache POSIX lifecycle only")
    def test_cache_close_attempts_all_descriptors_and_preserves_first_error(self):
        api = self.api()
        with temp_workspace() as root:
            owned = api._PinnedVerificationCache(self.plan(api, root, (self.check(api),)))
            descriptors = (owned.descriptor, owned.parent_fd)
            close = os.close
            error = OSError("first close fault")
            def faulty(descriptor):
                close(descriptor)
                if descriptor == descriptors[0]:
                    raise error
            with patch("icode.engineering_verification.os.close", side_effect=faulty) as observed:
                with self.assertRaises(OSError) as caught:
                    owned.close()
            self.assertIs(caught.exception, error)
            self.assertEqual([call.args[0] for call in observed.call_args_list], list(descriptors))
            owned.close()

    @unittest.skipUnless(os.name == "posix", "held cache POSIX lifecycle only")
    def test_cleanup_traverses_held_original_not_replacement_at_delete_entry(self):
        api = self.api()
        with temp_workspace() as root:
            owned = api._PinnedVerificationCache(self.plan(api, root, (self.check(api),)))
            original = owned.path.with_name(owned.name + "-original")
            remove = shutil.rmtree
            mutated = False
            def replace_at_actual_delete(path, **kwargs):
                nonlocal mutated
                if not mutated:
                    mutated = True
                    owned.path.rename(original)
                    owned.path.mkdir()
                    (owned.path / "foreign.txt").write_bytes(b"keep replacement at delete")
                return remove(path, **kwargs)
            try:
                with patch("icode.engineering_verification.shutil.rmtree", side_effect=replace_at_actual_delete):
                    with self.assertRaises(ValueError):
                        owned.remove()
                self.assertEqual((owned.path / "foreign.txt").read_bytes(), b"keep replacement at delete")
                self.assertTrue(original.is_dir())
            finally:
                owned.close()

    @unittest.skipUnless(os.name == "posix", "held cache POSIX lifecycle only")
    def test_cache_construction_close_fault_reclaims_locals_and_keeps_original_exception(self):
        api = self.api()
        for error in (OSError("close sentinel"), KeyboardInterrupt("close sentinel"), SystemExit(29)):
            with self.subTest(error=type(error).__name__), temp_workspace() as root:
                plan = self.plan(api, root, (self.check(api),))
                real_open, real_dup, real_close = os.open, os.dup, os.close
                opened = []
                target = None
                faulted = False
                def tracked_open(*args, **kwargs):
                    descriptor = real_open(*args, **kwargs)
                    opened.append(descriptor)
                    return descriptor
                def tracked_dup(descriptor):
                    nonlocal target
                    result = real_dup(descriptor)
                    opened.append(result)
                    if target is None:
                        target = result
                    return result
                def faulty_close(descriptor):
                    nonlocal faulted
                    real_close(descriptor)
                    if descriptor == target and not faulted:
                        faulted = True
                        raise error
                try:
                    with patch("icode.engineering_verification.os.open", side_effect=tracked_open), \
                            patch("icode.engineering_verification.os.dup", side_effect=tracked_dup), \
                            patch("icode.engineering_verification.os.close", side_effect=faulty_close):
                        with self.assertRaises(type(error)) as caught:
                            api._PinnedVerificationCache(plan)
                    self.assertIs(caught.exception, error)
                    for descriptor in set(opened):
                        with self.assertRaises(OSError):
                            os.fstat(descriptor)
                finally:
                    # Reclaim only descriptors this bounded fixture created,
                    # even when running its RED against an old implementation.
                    for descriptor in set(opened):
                        try:
                            os.fstat(descriptor)
                        except OSError:
                            continue
                        real_close(descriptor)

    @unittest.skipUnless(os.name == "posix", "held cache POSIX lifecycle only")
    def test_cache_close_never_suppresses_later_interruption(self):
        api = self.api()
        for interruption in (KeyboardInterrupt("cancel sentinel"), SystemExit(31)):
            with self.subTest(error=type(interruption).__name__), temp_workspace() as root:
                owned = api._PinnedVerificationCache(self.plan(api, root, (self.check(api),)))
                descriptors = (owned.descriptor, owned.parent_fd)
                close = os.close
                def faulty(descriptor):
                    close(descriptor)
                    if descriptor == descriptors[0]:
                        raise OSError("earlier close fault")
                    raise interruption
                with patch("icode.engineering_verification.os.close", side_effect=faulty) as observed:
                    with self.assertRaises(type(interruption)) as caught:
                        owned.close()
                self.assertIs(caught.exception, interruption)
                self.assertEqual([call.args[0] for call in observed.call_args_list], list(descriptors))
                owned.close()

    def test_go_build_uses_owned_offline_cache_and_cannot_bypass_platform_gate(self):
        api = self.api()
        with temp_workspace() as root:
            self.fixture(root)
            fake_go = root / ("go.exe" if os.name == "nt" else "go")
            shutil.copyfile(sys.executable, fake_go)
            build = api.VerificationCheck(check_id="build", kind="build", adapter="exit_status_v1",
                                         argv=(str(fake_go), "build", "-p", "1", "./..."))
            contexts = []
            def observed(_check, _ctx, cache):
                contexts.append(cache)
                self.assertIsNotNone(cache)
                environment = api._policy_environment(root.resolve(), verification_cache_root=cache)
                self.assertEqual(environment["GOTOOLCHAIN"], "local")
                self.assertEqual(environment["GOPROXY"], "off")
                self.assertTrue(Path(environment["GOCACHE"]).is_relative_to(cache))
                return api.EngineeringCheckResult("build", "passed", exit_code=0, output=b"fixture",
                                                  cleanup_ok=True, cleanup_scope="process_group")
            with patch("icode.engineering_verification._execute_check", side_effect=observed):
                run = self.execute(api, self.plan(api, root, (build, self.check(api))))
            self.assertFalse(run.passed)
            if os.name == "posix":
                self.assertEqual(len(contexts), 1)
                self.assertEqual(run.status, "cache_cleanup_unconfirmed")
                self.assertEqual(run.checks[1].status, "not_run")
            else:
                self.assertEqual(contexts, [])
                self.assertEqual(run.status, "execution_unavailable")

    def test_plan_rejects_unhashable_members_and_huge_timeout_without_type_error(self):
        api = self.api()
        with temp_workspace() as root:
            for changes in ({"steps": ([],)}, {"platforms": ({},)}):
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    self.plan(api, root, (self.check(api),), **changes)
            with self.assertRaises(ValueError):
                dataclasses.replace(self.check(api), timeout_seconds=10 ** 1000)

    def test_host_owned_cache_replacement_and_cleanup_failure_never_delete_foreign_data(self):
        api = self.api()
        if os.name != "posix":
            self.skipTest("held cache POSIX lifecycle only")
        for failure in ("replace", "cleanup"):
            with self.subTest(failure=failure), temp_workspace() as root, temp_workspace() as outside:
                self.fixture(root)
                fake_go = root / ("go.exe" if os.name == "nt" else "go")
                shutil.copyfile(sys.executable, fake_go)
                check = api.VerificationCheck(check_id="go", kind="test", adapter="go_test_json_v1",
                    argv=(str(fake_go), "test", "-json", "-count=1", "-p", "1", "-parallel", "1", "-mod=readonly", "./..."))
                plan = self.plan(api, root, (check,))
                sentinel = outside / "keep.txt"
                sentinel.write_bytes(b"keep foreign data")
                def observed(_check, _ctx, cache):
                    if failure == "replace":
                        cache.rename(cache.with_name(cache.name + "-original"))
                        cache.mkdir()
                        (cache / "keep.txt").write_bytes(b"keep replacement data")
                    return api.EngineeringCheckResult("go", "passed", exit_code=0, tests_passed=1,
                        output=b"transport fixture", cleanup_ok=True, cleanup_scope="linux_task_scope",
                        cache_owner_cleanup_confirmed=True)
                with patch("icode.engineering_verification._execute_check", side_effect=observed):
                    if failure == "cleanup":
                        with patch("icode.engineering_verification.shutil.rmtree", side_effect=OSError("PRIVATE_SENTINEL")):
                            run = self.execute(api, plan)
                    else:
                        run = self.execute(api, plan)
                self.assertFalse(run.passed)
                self.assertEqual(run.status, "cache_cleanup_unconfirmed")
                self.assertEqual(sentinel.read_bytes(), b"keep foreign data")
                if failure == "replace":
                    self.assertTrue(any(path.read_bytes() == b"keep replacement data"
                                        for path in root.glob(".icode-verification-*/keep.txt")))


class TestEngineeringResourceDispatch(_EngineeringHelpers, unittest.TestCase):
    def context(self, root):
        from icode.isolation import LandlockSandbox
        from icode.sandbox_policy import NetworkMode, SandboxPolicy
        policy = SandboxPolicy(schema_version=1, run_id="engineering-test", ticket_id="ENG-1", step="code",
            workspace_root=root.resolve(), read_roots=(root.resolve(),), write_roots=(root.resolve(),),
            deny_read_roots=(), deny_write_roots=(), network_mode=NetworkMode.DENY, allowed_domains=(),
            process_limit=64, wall_timeout_seconds=5, output_limit_bytes=65536, protected_paths=())
        return ToolContext(root=root.resolve(), policy=policy,
                           sandbox=LandlockSandbox(helper="not-executed-transport-fixture"))

    def test_complete_resource_dispatch_and_each_incomplete_fact_fail_closed(self):
        api = self.api()
        output = b"Ran 1 test in 0.01s\n\nOK\n"
        resource = dict(schema_version=1, resource="linux_payload_tasks", limit=64, configured=True,
                        payload_started=None, terminal="finished", channel_status="complete")
        good = ExecutionResult(0, "display is not evidence", len(output), None, False, True, None,
            raw_output=output, resource_receipt=resource, scope_cleanup_ok=True,
            violation_observer_status="complete")
        variants = (
            {}, {"scope_cleanup_ok": None}, {"cleanup_ok": False}, {"output_truncated": True},
            {"resource_receipt": None}, {"violation_observer_status": "incomplete"},
            {"resource_receipt": dict(resource, terminal="cleanup_failed")},
            {"resource_receipt": dict(resource, schema_version=True)},
            {"resource_receipt": dict(resource, payload_started=True)},
            {"resource_receipt": dict(resource, extra={"private": "PRIVATE_SENTINEL"})},
            {"resource_receipt": dict(resource, channel_status={"unbounded": object()})},
            {"resource_receipt": dict(resource, terminal=["finished"])},
            {"raw_output": output[:-1]}, {"exit_code": None},
        )
        for changes in variants:
            with self.subTest(changes=changes), temp_workspace() as root:
                self.fixture(root)
                plan = self.plan(api, root, (self.check(api),))
                ctx = self.context(root)
                with patch("icode.tools.builtin.sys.platform", "linux"), \
                        patch("icode.tools.builtin.execute_linux_resource_observed_command",
                              return_value=dataclasses.replace(good, **changes)) as dispatch, \
                        patch("icode.tools.builtin.execute_policy_command") as fallback:
                    run = api.execute_verification_plan(plan, ctx=ctx, step="code", attempt="same-attempt")
                self.assertEqual(run.passed, not changes)
                dispatch.assert_called_once()
                fallback.assert_not_called()
                self.assertEqual(run.checks[0].output, output if not changes else None)

    def test_no_policy_cross_identity_readonly_and_unsupported_paths_do_not_launch(self):
        api = self.api()
        from icode.sandbox_policy import NetworkMode
        with temp_workspace() as root:
            self.fixture(root)
            plan = self.plan(api, root, (self.check(api),))
            contexts = []
            for change in ({"run_id": "other"}, {"ticket_id": "other"},
                           {"network_mode": NetworkMode.PROXY_ALLOWLIST, "allowed_domains": ("example.com",)}):
                ctx = self.context(root)
                ctx.policy = dataclasses.replace(ctx.policy, **change)
                contexts.append(ctx)
            readonly = self.context(root)
            readonly.read_only_workspace = True
            contexts.append(readonly)
            ordinary = self.context(root)
            ordinary.sandbox = NoIsolation()
            contexts.append(ordinary)
            for ctx in contexts:
                with self.subTest(ctx=ctx), patch("icode.tools.builtin.execute_linux_resource_observed_command") as resource, \
                        patch("icode.tools.builtin.execute_policy_command") as fallback, \
                        patch("icode.runner._run_unittest_with_bounded_output") as plain:
                    run = api.execute_verification_plan(plan, ctx=ctx, step="code", attempt="1")
                self.assertFalse(run.passed)
                resource.assert_not_called()
                fallback.assert_not_called()
                plain.assert_not_called()

    def test_dispatch_itself_rejects_cwd_outside_context(self):
        self.api()
        from icode.tools.builtin import _controlled_dispatch
        from icode.tools.base import IsolationUnavailable
        with temp_workspace() as root, temp_workspace() as outside:
            with patch("icode.tools.builtin.execute_linux_resource_observed_command") as dispatch, \
                    self.assertRaises(IsolationUnavailable):
                _controlled_dispatch(self.context(root), [sys.executable], cwd=outside, timeout=1, require_resource=True)
            dispatch.assert_not_called()


class TestEngineeringAdapters(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec("icode.engineering_verification"))
        return importlib.import_module("icode.engineering_verification")

    def test_unittest_requires_positive_complete_ok_and_not_all_skipped(self):
        api = self.api()
        cases = (
            (b"Ran 2 tests in 0.010s\n\nOK\n", 2),
            (b"Ran 2 tests in 0.010s\n\nOK (skipped=1)\n", 1),
            (b"Ran 1 test in 0.010s\n\nOK (skipped=1)\n", 0),
            (b"Ran 0 tests in 0.010s\n\nOK\n", 0),
            (b"Ran 1 test in 0.010s\n", 0),
            (b"OK\n", 0), (b"Ran 1 test in 0.010s\nFAILED (failures=1)\n", 0),
            (b"Ran 1 test in 0.010s\nOK\nnot complete\n", 0),
            (b"Ran 1 test in 0.010s\nOK\n\xff", 0),
        )
        for output, count in cases:
            with self.subTest(output=output):
                self.assertEqual(api.parse_test_result("unittest_summary_v1", output), count)

    def test_go_json_requires_real_reported_test_and_closed_package(self):
        api = self.api()
        events = [
            {"Action": "start", "Package": "example.test"},
            {"Action": "run", "Package": "example.test", "Test": "TestActual"},
            {"Action": "output", "Package": "example.test", "Test": "TestActual", "Output": "actual\n"},
            {"Action": "pass", "Package": "example.test", "Test": "TestActual"},
            {"Action": "pass", "Package": "example.test"},
        ]
        encode = lambda items: ("\n".join(json.dumps(item) for item in items) + "\n").encode()
        self.assertEqual(api.parse_test_result("go_test_json_v1", encode(events)), 1)
        for bad in (
            [], events[:-1], events[1:], [events[0], events[-1]],
            [*events[:3], dict(events[3], Action="skip"), events[-1]],
            [*events[:3], dict(events[3], Action="fail"), events[-1]],
            [*events, {"Action": "future", "Package": "example.test"}],
            [*events[:3], events[-1]],
        ):
            with self.subTest(events=bad):
                self.assertEqual(api.parse_test_result("go_test_json_v1", encode(bad)), 0)
        self.assertEqual(api.parse_test_result("go_test_json_v1", b"warning\n" + encode(events)), 0)
        self.assertEqual(api.parse_test_result("go_test_json_v1", encode(events).rstrip()), 0)

    def test_go_metadata_and_binary_logs_do_not_add_or_remove_test_credit(self):
        api = self.api()
        events = [
            {"Action": "start", "Package": "example.test"},
            {"Action": "output", "Package": "example.test", "Test": "TestOutputNameOnly", "Output": "a\x00b\n"},
            {"Action": "run", "Package": "example.test", "Test": "TestActual"},
            {"Action": "attr", "Package": "example.test", "Test": "TestActual", "Key": "", "Value": "value"},
            {"Action": "artifacts", "Package": "example.test", "Test": "TestActual", "Path": "observation-only"},
            {"Action": "pass", "Package": "example.test", "Test": "TestActual"},
            {"Action": "run", "Package": "example.test", "Test": "ExampleActual"},
            {"Action": "pass", "Package": "example.test", "Test": "ExampleActual"},
            {"Action": "run", "Package": "example.test", "Test": "FuzzActual/seed#0"},
            {"Action": "pass", "Package": "example.test", "Test": "FuzzActual/seed#0"},
            {"Action": "pass", "Package": "example.test"},
        ]
        output = ("\n".join(json.dumps(event) for event in events) + "\n").encode()
        self.assertEqual(api.parse_test_result("go_test_json_v1", output), 1)

    def test_go_duplicate_terminal_progress_is_idempotent_not_extra_execution(self):
        api = self.api()
        start = {"Action": "start", "Package": "example.test"}
        begin = {"Action": "run", "Package": "example.test", "Test": "TestActual"}
        passed = dict(begin, Action="pass")
        end = dict(start, Action="pass")
        encode = lambda items: ("\n".join(json.dumps(item) for item in items) + "\n").encode()
        self.assertEqual(api.parse_test_result("go_test_json_v1", encode([start, begin, passed, passed, end])), 1)
        self.assertEqual(api.parse_test_result("go_test_json_v1", encode([start, begin, passed, begin, passed, end])), 2)
        for terminal in ("skip", "fail"):
            self.assertEqual(api.parse_test_result("go_test_json_v1", encode(
                [start, begin, passed, dict(passed, Action=terminal), end])), 0)
        self.assertEqual(api.parse_test_result("go_test_json_v1", encode([start, passed, passed, end])), 0)


@unittest.skipUnless(os.name == "posix" and (os.environ.get("ICODE_TEST_GO") or shutil.which("go")),
                     "existing Go toolchain required; not native isolation acceptance")
class TestRealGoEngineeringVerification(_EngineeringHelpers, unittest.TestCase):
    def test_real_go_framework_observations_remain_unaccepted_without_scope_cleanup(self):
        api = self.api()
        go = os.environ.get("ICODE_TEST_GO") or shutil.which("go")
        for mode in ("pass", "zero", "compile_failure"):
            with self.subTest(mode=mode), temp_workspace() as root:
                (root / "go.mod").write_text("module example.test\n\ngo 1.23\n", encoding="utf-8")
                (root / "actual.go").write_text("package actual\nfunc Add(a,b int) int { return a+b }\n", encoding="utf-8")
                if mode != "zero":
                    body = "if Add(2,2)!=4 {t.Fatal(\"bad\")}"
                    if mode == "compile_failure":
                        body = "this is not Go"
                    (root / "actual_test.go").write_text(
                        "package actual\nimport \"testing\"\nfunc TestActual(t *testing.T){" + body + "}\n",
                        encoding="utf-8",
                    )
                check = api.VerificationCheck(
                    check_id="go-tests", kind="test", adapter="go_test_json_v1",
                    argv=(str(go), "test", "-json", "-count=1", "-p", "1", "-parallel", "1", "-mod=readonly", "./..."),
                    timeout_seconds=120, output_limit_bytes=1024 * 1024,
                )
                run = self.execute(api, self.plan(api, root, (check,)))
                diagnostic = (run.status, [(item.status, item.exit_code, item.error,
                                            (item.output or b"")[-1000:]) for item in run.checks],
                              sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()))
                self.assertFalse(run.passed, diagnostic)
                self.assertEqual(run.status, "cache_cleanup_unconfirmed", diagnostic)
                self.assertEqual(run.checks[0].status, "passed" if mode == "pass" else "failed", diagnostic)
                self.assertEqual(run.checks[0].tests_passed, 1 if mode == "pass" else 0)
                self.assertTrue(any(root.glob(".icode-verification-*")))
                self.assertNotEqual(run.source_before, run.source_after, diagnostic)
                self.assertFalse(run.os_enforced)


if __name__ == "__main__":
    unittest.main()
