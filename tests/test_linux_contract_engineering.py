"""Source-only Linux engineering bridge; Native and model quality stay unverified."""
from __future__ import annotations

import contextlib
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tests._support import REPO_ROOT, require_skill
from icode import runner
from icode.backends import FakeBackend
from icode.budget import BudgetTracker
from icode.control import ControlPlane
from icode.contracts import ContractSet
from icode.engineering_verification import VerificationCheck, VerificationPlan
from icode.evidence import build_evidence_pack, load_verification_receipts
from icode.handshake import next_out_dir
from icode.isolation import LandlockSandbox
from icode.loop import LoopConfig
from icode.operations import OperationRecorder
from icode.pack_verify import verify_pack
from icode.tools import builtin
from icode.workspace import WorkspaceManager


def digest_bytes(content):
    return hashlib.sha256(content).hexdigest()


def canonical_digest(value):
    return digest_bytes(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                   ensure_ascii=False).encode("utf-8"))


def repository_provenance():
    result = {}
    for name, root in (("main", REPO_ROOT), ("vendor", REPO_ROOT / "vendor/icode-skill")):
        captured = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, timeout=10, check=False)
        if captured.returncode != 0:
            raise AssertionError("bridge_repository_identity_unavailable")
        result[name + "_sha"] = captured.stdout.decode("ascii", errors="strict").strip()
    files = ("src/icode/runner.py", "src/icode/workspace.py", "src/icode/isolation.py",
             "src/icode/linux_task_scope.py", "src/icode/engineering_verification.py",
             "src/icode/engineering_evidence.py", "src/icode/evidence.py",
             "src/icode/control.py", "src/icode/operations.py", "src/icode/chain.py",
             "vendor/icode-skill/tools/icode_control.py",
             "vendor/icode-skill/tools/inspection_worklist.py")
    result["source_sha256"] = {relative: digest_bytes((REPO_ROOT / relative).read_bytes())
                               for relative in files}
    return result


def test_source(body="self.assertEqual(changed.value, 1)"):
    return ("import unittest\nimport changed\nclass Value(unittest.TestCase):\n"
            " def test_value(self):\n  " + body + "\n")


def reviewer_script(*, read=True, submit=True, finding=None, denied=False):
    responses = []
    if read:
        responses.append({"tool_calls": [{"id": "read", "name": "read_file",
            "arguments": {"path": "../outside.py" if denied else "changed.py"}}]})
    if submit:
        responses.append({"tool_calls": [{"id": "submit", "name": "submit_review",
            "arguments": {"summary": "Read fixture value", "findings": [] if finding is None else [finding]}}]})
    responses.append("done")
    return responses


class _Bridge:
    def __init__(self, case, step="code", *, body=None, full=False,
                 timeout=5, output_limit=65536, later=False):
        # Linux-only imports belong to the real fixture, never module discovery.
        from icode.linux_task_scope import LinuxTaskScope
        from tests import test_linux_product_task_quota as quota_fixture
        self._scope_type = LinuxTaskScope
        self._collection_assert = quota_fixture.TestLinuxProductTaskQuota.assert_collected
        self.case, self.step = case, step
        self.raw = Path(tempfile.mkdtemp(prefix="icode-linux-bridge-")).resolve()
        self.raw_identity = (self.raw.stat().st_dev, self.raw.stat().st_ino)
        self.uncertain_cleanup = False
        self.pending_cleanup = False
        self.dispatch_started = 0
        self.observation_error = False
        self.source, self.data, self.control, self.pack_root = (
            self.raw / name for name in ("source", "data", "control", "pack"))
        for root in (self.source, self.data, self.control, self.pack_root):
            root.mkdir()
        case.addCleanup(self.close)
        self.session = None
        self.ticket_id, self.run_id = "LINUX-BRIDGE", "linux-bridge-run"
        (self.source / "changed.py").write_text("value = 0\n", encoding="utf-8")
        (self.source / "test_value.py").write_text(test_source() if body is None else body,
                                                  encoding="utf-8")
        commands = (("init", "-q"), ("add", "changed.py", "test_value.py"),
                    ("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                     "-c", "core.hooksPath=" + str(self.raw / "absent-hooks"),
                     "commit", "-qm", "owned bridge fixture"))
        for argv in commands:
            result = subprocess.run(["git", "-C", str(self.source), *argv],
                capture_output=True, timeout=10, check=False)
            case.assertEqual(result.returncode, 0, "fixture_git_initialization_failed")
        self.settings = case.settings
        self.manager = WorkspaceManager(self.source, self.data, "linux-bridge-project",
            extra_protected_paths=(self.settings.skill_root,), isolate_git_metadata=True)
        self.session = self.manager.open(self.ticket_id, self.run_id)
        self.root = self.session.workspace_root
        case.assertEqual(self.root, self.session.git_status_identity.code_root)
        case.assertFalse((self.root / ".git").exists())
        self.sandbox = LandlockSandbox(str(case.helper), manifest=str(case.manifest))
        self.policy = self.session.policy(step, process_limit=8,
            wall_timeout_seconds=30, output_limit_bytes=65536)
        self.sandbox.prepare_policy(self.policy)
        self.cp = ControlPlane(self.settings)
        self.directory = next_out_dir(self.control).resolve()
        if step == "deepcheck":
            # Final source and scope exist before the CP captures step inputs.
            (self.root / "changed.py").write_text("value = 1\n", encoding="utf-8")
        self.baseline = runner._snapshot(self.root)
        self.git_baseline = runner._read_task_git_state(self.root, workspace_session=self.session)
        check = VerificationCheck("python-unittest", "test",
            (sys.executable, "-I", "-B", "-X", "utf8", "-m", "unittest", "discover",
             "-s", str(self.root), "-t", str(self.root)), "unittest_summary_v1",
            timeout_seconds=timeout, output_limit_bytes=output_limit)
        checks = (check, replace(check, check_id="later")) if later else (check,)
        self.plan = VerificationPlan(self.root, self.run_id, self.ticket_id, checks,
                                     steps=(step,), platforms=("Linux",))
        if full:
            # Explicit fixture_seed only. No earlier model phase is claimed.
            self.directory.mkdir(parents=True)
            legacy = dict(ticket_id=self.ticket_id, requirement="change value",
                created_at="2026-10-09T00:00:00Z", status=step + "_in_progress",
                completed_steps=["1", "2", "3"], code_files=["changed.py"],
                workflow_gate_schema_version=1, thinking_gate_schema_version=1,
                mcp_gate_schema_version=2, semantic_decisions=[], requirement_deltas=[],
                project_path=str(self.control))
            (self.directory / ".ico_metadata.json").write_text(json.dumps(legacy), encoding="utf-8")
            case.assertTrue(self.cp.run("migration", "--dir", str(self.directory), "--apply").ok)
        else:
            created = self.cp.create(self.directory, ticket_id=self.ticket_id,
                requirement="change value", birth="plan", metadata_json=json.dumps({
                    "code_files": ["changed.py"]}))
            case.assertTrue(created.ok)
        bound = self.cp.bind_execution_root(
            self.directory, ticket_id=self.ticket_id, execution_root=self.root)
        case.assertTrue(bound.ok)
        (self.directory / "03_plan_final.md").write_text("# Accepted fixture plan\n", encoding="utf-8")
        projection = self.cp.run("action-policy", "--dir", str(self.directory))
        case.assertEqual(projection.data.get("ticket_id"), self.ticket_id)
        case.assertEqual(projection.data.get("execution_root"), str(self.root))
        self.report = runner.StepReport(step, False, str(self.directory))
        self.attempt = ""
        self.scopes, self.actual_results, self.configured_facts = [], [], []
        self.operations = OperationRecorder(self.cp, self.directory, self.ticket_id, scope=step)
        if not full:
            self.attempt = self.cp.step_start(self.directory, step, ticket_id=self.ticket_id)
            if step == "code":
                (self.root / "changed.py").write_text("value = 1\n", encoding="utf-8")
            for occurrence, boundary in enumerate(ContractSet.load(self.settings.gates_json).step(step).required_checks, 1):
                checked = self.cp.step_check(self.directory, step, self.attempt,
                    boundary, ticket_id=self.ticket_id, occurrence=occurrence)
                case.assertEqual(checked.data.get("result"), "pass")

    def close(self):
        if self.session is not None:
            self.session.close()
        if self.pending_cleanup or self.uncertain_cleanup:
            print("linux-bridge-owned-fixture retained; cleanup_credit=none", flush=True)
            return
        if self.raw.exists():
            self.case.assertEqual((self.raw.stat().st_dev, self.raw.stat().st_ino), self.raw_identity)
            shutil.rmtree(self.raw)

    def events(self, kind):
        return [row for line in (self.directory / ".ico_events.jsonl").read_text(encoding="utf-8").splitlines()
                if (row := json.loads(line))["event_type"] == kind]

    @contextlib.contextmanager
    def observe(self, *, fault=None, after_command=None):
        original_configured = self._scope_type.configured
        original_dispatch = builtin._controlled_dispatch
        def configured(scope, deadline):
            original_return = original_configured(scope, deadline)
            # ACK is still pending: capture only the original validator's cache.
            # Keep original configured exceptions outside this observer-only try.
            try:
                self.scopes.append(scope)
                identities = tuple(scope._identities)
                if (len(identities) != 3 or any(len(identity) != 2 for identity in identities)
                        or scope._owned is not True or not scope._invocation):
                    raise ValueError("configured_memory_cache_incomplete")
                self.configured_facts.append(dict(unit_sha256=digest_bytes(scope.unit.encode()),
                    object_identity=list(identities[0]),
                    owned_identity_cache=[list(identity) for identity in identities],
                    payload_limit=scope.limit, systemd_version=scope.version,
                    invocation_sha256=digest_bytes(scope._invocation.encode()),
                    source="original_configured_validated_memory_cache"))
            except BaseException:
                # An observation fault must not turn into an ACK/configuration fault.
                self.observation_error = True
            return original_return
        def dispatch(*args, **kwargs):
            self.pending_cleanup = True
            self.dispatch_started += 1
            try:
                result = original_dispatch(*args, **kwargs)
                self.actual_results.append(result)
                if result.scope_cleanup_ok is not True:
                    self.uncertain_cleanup = True
                if after_command is not None:
                    after_command()
                return replace(result, **fault) if fault else result
            except BaseException:
                self.uncertain_cleanup = True
                raise
        with patch.object(self._scope_type, "configured", new=configured), \
             patch.object(builtin, "_controlled_dispatch", new=dispatch):
            try:
                yield
            except BaseException:
                if self.pending_cleanup:
                    self.uncertain_cleanup = True
                # No new I/O, retry or CP finish while propagating the original abort.
                raise
            else:
                self.confirm_collected()
                self.case.assertFalse(self.observation_error, "bridge_memory_observation_unavailable")

    def confirm_collected(self):
        if not self.pending_cleanup:
            return
        try:
            self.case.assertEqual(len(self.actual_results), self.dispatch_started,
                                  "dispatch_result_missing_cleanup_unknown")
            self.case.assertTrue(self.scopes, "actual_manager_scope_missing")
            self._collection_assert(self.case, self.scopes)
            self.case.assertTrue(all(result.scope_cleanup_ok is True for result in self.actual_results),
                                 "original_dispatch_cleanup_unconfirmed")
        except BaseException:
            self.uncertain_cleanup = True
            raise
        else:
            # This confirms the pending window only; earlier unknown is sticky.
            self.pending_cleanup = False

    def arguments(self, backend):
        return dict(cp=self.cp, out_dir=self.directory, ticket_id=self.ticket_id,
            step=self.step, attempt=self.attempt, report=self.report, plan=self.plan,
            policy=self.policy, sandbox=self.sandbox, workspace_session=self.session,
            workspace=self.root, baseline=self.baseline, git_baseline=self.git_baseline,
            operations=self.operations, backend=backend, requirement="change value",
            loop_config=LoopConfig(), budget_tracker=BudgetTracker())

    def run_gate(self, backend=None, *, fault=None, after_command=None):
        backend = backend if backend is not None else FakeBackend(reviewer_script())
        with self.observe(fault=fault, after_command=after_command):
            passed = runner._contract_engineering_gate(**self.arguments(backend))
        self.publish_observation(layer="injected_fault" if fault else "source_host_model_double")
        return passed, backend

    def receipt(self):
        paths = list(self.directory.glob(".engineering-*.json"))
        self.case.assertEqual(len(paths), 1)
        self.case.assertEqual(str(paths[0]), self.report.verification_receipt_path)
        return load_verification_receipts(paths)[0]

    def publish_observation(self, *, layer):
        identity = self.root.stat()
        rows = []
        for result in self.actual_results:
            rows.append(dict(exit_code=result.exit_code, error=result.error,
                resource_receipt_sha256=canonical_digest(result.resource_receipt),
                payload_started=result.resource_receipt.get("payload_started")
                    if type(result.resource_receipt) is dict else None,
                scope_cleanup_ok=result.scope_cleanup_ok,
                violation_observer_status=result.violation_observer_status))
        public = dict(layer=layer, step=self.step, run_id=self.run_id, ticket_id=self.ticket_id,
            repository=repository_provenance(),
            uid=os.getuid(), kernel=os.uname().release, architecture=os.uname().machine,
            helper_sha256=digest_bytes(self.case.helper.read_bytes()),
            manifest_sha256=digest_bytes(self.case.manifest.read_bytes()),
            native_source_sha256=digest_bytes((REPO_ROOT / "native/linux/icode_landlock.c").read_bytes()),
            python_version=sys.version.split()[0],
            python_lexical_path_sha256=digest_bytes(sys.executable.encode()),
            python_resolved_path_sha256=digest_bytes(str(Path(sys.executable).resolve()).encode()),
            workspace_identity=[identity.st_dev, identity.st_ino], plan_digest=self.plan.digest,
            environment_sha256=canonical_digest(self.plan.environment),
            executable_identity=self.plan.checks[0].executable_identity,
            cp_attempt=self.attempt, base_commit_sha=self.git_baseline[1],
            object_format=self.git_baseline[0], configured_scopes=self.configured_facts,
            current_git_state=list(runner._read_task_git_state(self.root, workspace_session=self.session)),
            operation_links=[dict(name=event["payload"]["name"], attempt=event["payload"]["attempt"])
                             for event in self.events("operation_started")],
            actual_resource_observations=rows, model_quality_credit="none", native_ready=False)
        if self.report.verification_evidence is not None:
            row = self.receipt()
            public.update(receipt_fingerprint=row["fingerprint"], tested_tree=row["binding"]["tested_git_tree_oid"],
                tree_status=row["binding"]["tested_git_tree_status"], source_before=row["run"]["source_before"],
                source_after=row["run"]["source_after"])
        (self.directory / "bridge-observation.json").write_text(json.dumps(public, sort_keys=True) + "\n", encoding="utf-8")
        print("linux-engineering-bridge observation=" + json.dumps(public, sort_keys=True), flush=True)

    def export_and_verify(self):
        row = self.receipt()
        target = self.pack_root / "partial"
        exported = build_evidence_pack(self.directory, dest=target,
            gates_json=self.settings.gates_json, verifications=[row], clean=False)
        self.case.assertTrue(exported.ok, "partial_pack_export_rejected")
        self.case.assertEqual(verify_pack(target), [])
        outside = self.raw / "outside-verifier-cwd"
        outside.mkdir()
        independent = subprocess.run([sys.executable, "-I", "-B", str(target / "verify.py"), str(target)],
            cwd=outside, capture_output=True, timeout=15, check=False)
        self.case.assertEqual(independent.returncode, 0, "independent_partial_pack_rejected")
        manifest = target / "manifest.json"
        self.case.assertTrue(manifest.is_file())
        manifest_digest = digest_bytes(manifest.read_bytes())
        observation = self.directory / "bridge-observation.json"
        public = json.loads(observation.read_text(encoding="utf-8"))
        public["pack_manifest_sha256"] = manifest_digest
        observation.write_text(json.dumps(public, sort_keys=True) + "\n", encoding="utf-8")
        print("linux-engineering-bridge pack_manifest_sha256=" + manifest_digest, flush=True)
        return target


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux bridge only; conformance_credit=none")
class TestLinuxContractEngineering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("cc")
        bus = Path(f"/run/user/{os.getuid()}/bus")
        if compiler is None or os.getuid() == 0 or not bus.exists() or not stat.S_ISSOCK(bus.lstat().st_mode) or bus.lstat().st_uid != os.getuid():
            raise unittest.SkipTest("compiler/non-root same-user bus required; conformance_credit=none")
        cls.settings = require_skill()
        if cls.settings.skill_root.resolve() != (REPO_ROOT / "vendor/icode-skill").resolve():
            raise AssertionError("bridge_requires_fixed_vendor_skill")
        cls.helper_dir = tempfile.TemporaryDirectory(prefix="icode-linux-bridge-helper-")
        cls.addClassCleanup(cls.helper_dir.cleanup)
        cls.helper = Path(cls.helper_dir.name) / "icode-landlock"
        built = subprocess.run([compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
            str(REPO_ROOT / "native/linux/icode_landlock.c"), "-o", str(cls.helper)],
            capture_output=True, timeout=30, check=False)
        if built.returncode != 0:
            raise AssertionError("actual_bridge_helper_compile_failed")
        cls.manifest = Path(cls.helper_dir.name) / "icode-landlock.sha256"
        cls.manifest.write_text(digest_bytes(cls.helper.read_bytes()) + "\n", encoding="ascii")

    def test_bridge_code_cp_receipt_and_pack(self):
        f = _Bridge(self, "code")
        passed, reviewer = f.run_gate()
        self.assertTrue(passed, f.report.error)
        row = f.receipt()
        self.assertTrue(row["passed"])
        self.assertEqual(row["binding"]["attempt"], f.attempt)
        self.assertEqual(row["run"]["attempt"], f.attempt)
        self.assertEqual(row["public_plan"]["run_id"], f.session.run_id)
        self.assertEqual(row["run"]["source_before"], row["run"]["source_after"])
        self.assertEqual(row["binding"]["tested_git_tree_status"], "stable")
        self.assertGreaterEqual(row["run"]["checks"][0]["tests_passed"], 1)
        self.assertEqual(len(f.actual_results), 1)
        self.assertEqual(len(reviewer.calls), 3)
        self.assertIsNone(f.actual_results[0].resource_receipt["payload_started"])
        self.assertFalse(f.cp.trace(f.directory).data["open_operations"])
        self.assertEqual(len(f.events("operation_started")), 1)
        self.assertEqual(len(f.events("operation_finished")), 1)
        self.assertNotEqual(f.events("operation_started")[0]["payload"]["attempt"], f.attempt)
        self.assertEqual(len(f.events("verification_recorded")), 1)
        self.assertEqual(f.events("verification_recorded")[0]["payload"]["evidence"], row["fingerprint"])
        self.assertTrue(runner._record_contract_engineering(f.cp, f.directory, f.ticket_id, f.report.verification_evidence))
        self.assertEqual(len(f.events("verification_recorded")), 1)
        self.assertEqual(f.events("step_finished"), [])
        self.assertTrue(f.cp.trace(f.directory).data["open_steps"])
        f.export_and_verify()

    def test_bridge_deepcheck_fixed_scope_cp_receipt_and_pack(self):
        f = _Bridge(self, "deepcheck")
        before = runner._snapshot(f.root)
        passed, reviewer = f.run_gate()
        self.assertTrue(passed, f.report.error)
        self.assertEqual(runner._snapshot(f.root), before)
        self.assertEqual(f.report.verification_review_files, ("changed.py",))
        self.assertEqual(f.receipt()["binding"]["tested_git_tree_status"], "stable")
        self.assertEqual(len(f.actual_results), 1)
        self.assertEqual(len(reviewer.calls), 3)
        self.assertEqual(f.events("step_finished"), [])
        f.export_and_verify()

class TestBridgeObservationSafety(unittest.TestCase):
    def _small_fixture(self):
        bridge = _Bridge.__new__(_Bridge)
        bridge.case, bridge.session = self, None
        bridge.pending_cleanup, bridge.uncertain_cleanup = False, False
        bridge.dispatch_started, bridge.observation_error = 0, False
        bridge.scopes, bridge.actual_results, bridge.configured_facts = [], [], []
        bridge.raw = Mock(name="owned_fixture_root")
        bridge.raw.exists.return_value = True
        bridge.raw.stat.return_value = SimpleNamespace(st_dev=17, st_ino=19)
        bridge.raw_identity = (17, 19)
        class PortableScope:
            @staticmethod
            def configured(scope, deadline):
                raise AssertionError("portable_scope_requires_explicit_double")
        bridge._scope_type = PortableScope
        bridge._collection_assert = Mock(name="portable_owned_collection_double")
        scope = SimpleNamespace(unit="fixture.scope", _identities=[(1, 2), (1, 3), (1, 4)],
                                limit=8, version=249, _owned=True, _invocation="fixture-invocation")
        return bridge, scope

    def test_memory_observer_preserves_original_result_and_ack_order_without_io(self):
        bridge, scope = self._small_fixture()
        configured_return = object()
        dispatch_return = SimpleNamespace(scope_cleanup_ok=True)
        deadline = object()
        events = []
        def configured(actual_scope, actual_deadline):
            self.assertIs(actual_scope, scope)
            self.assertIs(actual_deadline, deadline)
            events.append("configured")
            return configured_return
        def dispatch(*args, **kwargs):
            self.assertTrue(bridge.pending_cleanup)
            observed_return = bridge._scope_type.configured(scope, deadline)
            self.assertIs(observed_return, configured_return)
            events.extend(("ack", "dispatch_return"))
            return dispatch_return
        original_dispatch = Mock(side_effect=dispatch)
        def collected(actual_case, actual_scopes):
            self.assertIs(actual_case, self)
            self.assertEqual(actual_scopes, [scope])
            events.append("collected")
        with patch.object(bridge._scope_type, "configured", new=configured), \
             patch.object(builtin, "_controlled_dispatch", new=original_dispatch), \
             patch.object(bridge, "_collection_assert", side_effect=collected), \
             patch.object(Path, "stat", side_effect=AssertionError("observer_extra_stat")), \
             patch.object(Path, "read_text", side_effect=AssertionError("observer_extra_path_read")), \
             patch.object(subprocess, "run", side_effect=AssertionError("observer_extra_query")), \
             patch.object(time, "sleep", side_effect=AssertionError("observer_extra_sleep")):
            with bridge.observe():
                actual = builtin._controlled_dispatch("payload", label="fixture")
                self.assertIs(actual, dispatch_return)
                self.assertTrue(bridge.pending_cleanup)
        original_dispatch.assert_called_once_with("payload", label="fixture")
        self.assertEqual(events, ["configured", "ack", "dispatch_return", "collected"])
        self.assertFalse(bridge.pending_cleanup)
        self.assertFalse(bridge.uncertain_cleanup)
        self.assertFalse(bridge.observation_error)
        self.assertEqual(bridge.actual_results, [dispatch_return])
        self.assertEqual(bridge.configured_facts[0]["owned_identity_cache"], [[1, 2], [1, 3], [1, 4]])
        self.assertEqual(bridge.configured_facts[0]["object_identity"], [1, 2])
        self.assertEqual(bridge.configured_facts[0]["payload_limit"], 8)

        # Fresh-process import contract, not a native Windows execution claim.
        import_probe = (
            "import importlib.abc, os, sys\n"
            "blocked = {'icode.linux_task_scope', 'icode.linux_seccomp_notify', "
            "'tests.test_linux_product_task_quota', 'tests.test_linux_violation_receipt', 'fcntl'}\n"
            "class DenyLinuxImport(importlib.abc.MetaPathFinder):\n"
            " def find_spec(self, fullname, path=None, target=None):\n"
            "  if fullname in blocked: raise ImportError('forbidden_eager_linux_import')\n"
            "sys.meta_path.insert(0, DenyLinuxImport())\n"
            "for name in ('O_DIRECTORY', 'O_NOFOLLOW', 'O_CLOEXEC'):\n"
            " if hasattr(os, name): delattr(os, name)\n"
            "import tests.test_linux_contract_engineering\n"
            "assert not (blocked - {'fcntl'}) & set(sys.modules)\n"
        )
        imported = subprocess.run([sys.executable, "-B", "-c", import_probe],
            cwd=REPO_ROOT, capture_output=True, timeout=15, check=False)
        self.assertEqual(imported.returncode, 0, "portable_bridge_import_contract_failed")

    def test_observer_fault_keeps_ack_but_original_abort_is_rethrown(self):
        # A missing memory cache is only an observer error after the original ACK.
        bridge, scope = self._small_fixture()
        scope._identities = []
        marker = object()
        result = SimpleNamespace(scope_cleanup_ok=True)
        events = []
        def configured(actual_scope, deadline):
            events.append("configured")
            return marker
        def dispatch(*args, **kwargs):
            self.assertIs(bridge._scope_type.configured(scope, 1), marker)
            events.append("ack")
            return result
        with patch.object(bridge._scope_type, "configured", new=configured), \
             patch.object(builtin, "_controlled_dispatch", new=dispatch), \
             patch.object(bridge, "_collection_assert") as collected:
            with self.assertRaisesRegex(AssertionError, "bridge_memory_observation_unavailable"):
                with bridge.observe():
                    self.assertIs(builtin._controlled_dispatch(), result)
        self.assertEqual(events, ["configured", "ack"])
        collected.assert_called_once_with(self, [scope])
        self.assertTrue(bridge.observation_error)
        self.assertFalse(bridge.pending_cleanup)

        # Original configured/dispatch exceptions are outside observer swallowing.
        for boundary in ("configured", "dispatch"):
            for abort_type in (RuntimeError, KeyboardInterrupt):
                with self.subTest(boundary=boundary, abort_type=abort_type.__name__):
                    bridge, scope = self._small_fixture()
                    abort = abort_type("original_abort")
                    events = []
                    def configured(actual_scope, deadline):
                        events.append("configured")
                        if boundary == "configured":
                            raise abort
                        return marker
                    def dispatch(*args, **kwargs):
                        self.assertIs(bridge._scope_type.configured(scope, 1), marker)
                        events.append("ack")
                        raise abort
                    original_dispatch = Mock(side_effect=dispatch)
                    with patch.object(bridge._scope_type, "configured", new=configured), \
                         patch.object(builtin, "_controlled_dispatch", new=original_dispatch), \
                         patch.object(bridge, "_collection_assert") as collected:
                        with self.assertRaises(abort_type) as caught:
                            with bridge.observe():
                                builtin._controlled_dispatch("payload")
                    self.assertIs(caught.exception, abort)
                    original_dispatch.assert_called_once_with("payload")
                    collected.assert_not_called()
                    self.assertEqual(events, ["configured"] if boundary == "configured" else ["configured", "ack"])
                    self.assertTrue(bridge.pending_cleanup)
                    self.assertTrue(bridge.uncertain_cleanup)
                    self.assertEqual(bridge.actual_results, [])
                    with patch.object(shutil, "rmtree") as removed:
                        bridge.close()
                    removed.assert_not_called()

    def test_pending_and_sticky_unknown_protect_owned_root_until_confirmed(self):
        # No dispatch: the original inode-bound cleanup remains allowed.
        bridge, _scope = self._small_fixture()
        with patch.object(shutil, "rmtree") as removed:
            bridge.close()
        removed.assert_called_once_with(bridge.raw)

        # A normal result is still pending until the independent owned check.
        bridge, scope = self._small_fixture()
        result = SimpleNamespace(scope_cleanup_ok=True)
        def configured(actual_scope, deadline):
            return None
        def dispatch(*args, **kwargs):
            bridge._scope_type.configured(scope, 1)
            return result
        with patch.object(bridge._scope_type, "configured", new=configured), \
             patch.object(builtin, "_controlled_dispatch", new=dispatch), \
             patch.object(bridge, "_collection_assert"), \
             patch.object(shutil, "rmtree") as removed:
            with bridge.observe():
                self.assertIs(builtin._controlled_dispatch(), result)
                bridge.close()
                removed.assert_not_called()
                self.assertTrue(bridge.pending_cleanup)
            self.assertFalse(bridge.pending_cleanup)
            bridge.close()
            removed.assert_called_once_with(bridge.raw)

        # Collection failure/abort is sticky even if a later window is confirmed.
        for abort_type in (AssertionError, RuntimeError, KeyboardInterrupt):
            with self.subTest(collection_abort=abort_type.__name__):
                bridge, scope = self._small_fixture()
                abort = abort_type("owned_collection_unconfirmed")
                with patch.object(bridge._scope_type, "configured", new=configured), \
                     patch.object(builtin, "_controlled_dispatch", new=dispatch), \
                     patch.object(bridge, "_collection_assert", side_effect=abort):
                    with self.assertRaises(abort_type) as caught:
                        with bridge.observe():
                            builtin._controlled_dispatch()
                self.assertIs(caught.exception, abort)
                self.assertTrue(bridge.pending_cleanup)
                self.assertTrue(bridge.uncertain_cleanup)
                with patch.object(bridge._scope_type, "configured", new=configured), \
                     patch.object(builtin, "_controlled_dispatch", new=dispatch), \
                     patch.object(bridge, "_collection_assert"):
                    with bridge.observe():
                        builtin._controlled_dispatch()
                self.assertFalse(bridge.pending_cleanup)
                self.assertTrue(bridge.uncertain_cleanup)
                with patch.object(shutil, "rmtree") as removed:
                    bridge.close()
                removed.assert_not_called()

        # A returned unknown cleanup also cannot be changed into deletion credit.
        bridge, scope = self._small_fixture()
        result = SimpleNamespace(scope_cleanup_ok=None)
        with patch.object(bridge._scope_type, "configured", new=configured), \
             patch.object(builtin, "_controlled_dispatch", new=dispatch), \
             patch.object(bridge, "_collection_assert"):
            with self.assertRaisesRegex(AssertionError, "original_dispatch_cleanup_unconfirmed"):
                with bridge.observe():
                    builtin._controlled_dispatch()
        self.assertTrue(bridge.pending_cleanup)
        self.assertTrue(bridge.uncertain_cleanup)
        with patch.object(shutil, "rmtree") as removed:
            bridge.close()
        removed.assert_not_called()
