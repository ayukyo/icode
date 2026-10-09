"""Admission protocol and real offline CP; never model/native isolation credit."""

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from icode.approvals import DenyAllApprover
from icode.backends import FakeBackend
from icode.budget import BudgetTracker
from icode.control import ControlPlane, ControlResult, make_request
from icode.guard import Guard, Scope
from icode.handshake import next_out_dir
from icode.loop import AgentLoop, LoopConfig
from icode.operations import OperationRecorder, StartedOperation
from icode.tools import Tool, ToolContext, ToolRegistry, ToolResult
from tests._support import require_skill, temp_workspace


class _ResponseCP:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def operation_start(self, out_dir, **kwargs):
        self.calls.append((out_dir, kwargs))
        return self.result


class TestOperationAdmissionProtocol(unittest.TestCase):
    def record(self, data, returncode=0, scope=""):
        raw = ControlResult((), returncode, data)
        cp = _ResponseCP(raw)
        rec = OperationRecorder(cp, Path("fixture-output"), "ADMISSION", scope=scope)
        result = rec.start(name="probe", opclass="managed_write", input_desc="fixture")
        self.assertIs(cp.result, raw)
        self.assertIs(cp.result.data, data)
        return result, raw, cp, rec

    def test_legacy_construction_and_strict_permission(self):
        old = StartedOperation("probe", "managed_write", "a1", True, False, "detail")
        self.assertTrue(old.can_execute)
        self.assertIs(getattr(old, "already_applied", None), False)
        keyword = StartedOperation(
            name="probe", opclass="managed_write", attempt="a1",
            ok=True, ambiguous=False, detail="detail",
        )
        self.assertEqual(old, keyword)
        for marker in (True, 0, 1, None, "false", [], {}):
            with self.subTest(marker=marker):
                self.assertFalse(replace(old, already_applied=marker).can_execute)
        for changed in (
            {"ok": False}, {"ambiguous": True}, {"attempt": None}, {"attempt": ""},
        ):
            self.assertFalse(replace(old, **changed).can_execute)

    def test_missing_false_and_true_response_markers(self):
        for value in ("missing", False, True):
            with self.subTest(value=value):
                data = {"ok": True, "attempt": "a1"}
                if value != "missing":
                    data["already_applied"] = value
                result, raw, _cp, _rec = self.record(data)
                self.assertTrue(result.ok)
                self.assertEqual(result.attempt, "a1")
                self.assertIs(getattr(result, "already_applied", None), value is True)
                self.assertIs(result.can_execute, value is not True)
                self.assertEqual(raw.data, data)
                self.assertFalse(result.ambiguous)

    def test_malformed_marker_is_normalized_without_mutating_raw(self):
        for value in (0, 1, "false", None, [], {}):
            with self.subTest(value=value):
                data = {"ok": True, "attempt": "a1", "already_applied": value}
                result, raw, _cp, _rec = self.record(data)
                self.assertFalse(result.ok)
                self.assertFalse(result.can_execute)
                self.assertIs(result.already_applied, False)
                self.assertEqual(
                    result.detail,
                    "operation_start_protocol_invalid: already_applied 必须是 bool",
                )
                self.assertIs(raw.data["already_applied"], value)

    def test_structured_ambiguity_old_fallback_and_transport(self):
        for extra in (
            {"gate_id": "ambiguous_side_effect", "error": "同名动作未终结"},
            {"ambiguous_side_effect": True},
            {"error": "ambiguous_side_effect"},
        ):
            with self.subTest(extra=extra):
                result, _raw, _cp, _rec = self.record(dict(ok=False, **extra), returncode=1)
                self.assertTrue(result.ambiguous)
                self.assertFalse(result.can_execute)
        for data, code in (
            ({"ok": True, "attempt": "a1"}, 1),
            ({"ok": 1, "attempt": "a1"}, 0),
            ({"ok": True, "attempt": ""}, 0),
        ):
            result, _raw, _cp, _rec = self.record(data, code)
            self.assertFalse(result.can_execute)
        result, _raw, _cp, _rec = self.record(
            {"ok": True, "attempt": 7, "message": "m" * 400}
        )
        self.assertEqual(result.attempt, "7")
        self.assertEqual(result.detail, "m" * 300)

    def test_occurrence_and_scope_preserve_exact_double_calls(self):
        _first, _raw, cp, rec = self.record({"ok": True, "attempt": "a1"}, scope="plan")
        rec.start(name="probe", opclass="managed_write", input_desc="fixture")
        self.assertEqual([call[1]["occurrence"] for call in cp.calls], [1, 3])
        self.assertEqual(
            [call[1]["request"] for call in cp.calls],
            [
                make_request("ADMISSION", "op-plan-probe-start", occurrence=2),
                make_request("ADMISSION", "op-plan-probe-start", occurrence=4),
            ],
        )
        self.assertEqual(rec._counters, {"probe": 4})
        self.assertEqual(cp.calls[0][1]["name"], "probe")
        self.assertEqual(cp.calls[0][1]["opclass"], "managed_write")
        self.assertEqual(cp.calls[0][1]["input_desc"], "fixture")
        other, _raw, other_cp, _rec = self.record(
            {"ok": True, "attempt": "a2"}, scope="review"
        )
        self.assertTrue(other.can_execute)
        self.assertNotEqual(cp.calls[0][1]["request"], other_cp.calls[0][1]["request"])


def _probe_input():
    safe = {"arg_keys": [], "args_sha256": hashlib.sha256(b"{}").hexdigest()}
    return json.dumps(safe, ensure_ascii=False)


def _make_loop(root, recorder, events, *, read_only=False):
    registry = ToolRegistry()

    def handler(ctx):
        if read_only:
            return ToolResult(True, "read-only fixture")
        marker = ctx.root / "payload-marker.txt"
        previous = marker.read_text(encoding="utf-8") if marker.exists() else ""
        marker.write_text(previous + "x", encoding="utf-8")
        return ToolResult(True, "done")

    registry.register(Tool(
        "admission_probe", "owned test marker",
        {"type": "object", "properties": {}, "required": []}, handler,
        opclass="read_only" if read_only else "managed_write",
    ))
    return AgentLoop(
        backend=FakeBackend([]), registry=registry,
        guard=Guard(Scope(workspace_root=root)), ctx=ToolContext(root=root),
        approver=DenyAllApprover(), operations=recorder,
        budget=BudgetTracker(), config=LoopConfig(),
        on_event=lambda kind, payload: events.append((kind, payload)),
    )


class TestOperationAdmissionRealCP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.settings = require_skill()
        except unittest.SkipTest as exc:
            # These are explicitly required admission tests, not optional diagnostics.
            raise RuntimeError("Required admission CP fixture unavailable") from exc

    def ticket(self):
        root = self.enterContext(temp_workspace()).resolve()
        cp = ControlPlane(self.settings)
        directory = next_out_dir(root).resolve()
        created = cp.create(
            directory, ticket_id="ADMISSION", requirement="owned replay", birth="plan",
        )
        self.assertIs(created.data.get("ok"), True)
        return root, cp, directory

    def recorder(self, cp, directory):
        return OperationRecorder(cp, directory, "ADMISSION", scope="plan")

    def marker(self, root):
        path = root / "payload-marker.txt"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def open_attempts(self, cp, directory):
        trace = cp.trace(directory)
        self.assertEqual(trace.returncode, 0)
        self.assertIs(trace.data.get("ok"), True)
        return trace.data["open_operations"]

    def seed(self, cp, directory):
        recorder = self.recorder(cp, directory)
        started = recorder.start(
            name="tool:admission_probe", opclass="managed_write", input_desc=_probe_input(),
        )
        self.assertTrue(started.can_execute, started.detail)
        return recorder, started

    def test_actual_first_raw_open_replay_and_structured_next_occurrence(self):
        _root, cp, directory = self.ticket()
        raw = []
        original = cp.operation_start

        def observed(*args, **kwargs):
            response = original(*args, **kwargs)
            raw.append(response)
            return response

        with patch.object(cp, "operation_start", side_effect=observed):
            original_recorder, first = self.seed(cp, directory)
            replay_recorder = self.recorder(cp, directory)
            replay = replay_recorder.start(
                name="tool:admission_probe", opclass="managed_write", input_desc=_probe_input(),
            )
            ambiguous = replay_recorder.start(
                name="tool:admission_probe", opclass="managed_write", input_desc=_probe_input(),
            )
        self.assertNotIn("already_applied", raw[0].data)
        self.assertIs(raw[1].data.get("already_applied"), True)
        self.assertTrue(replay.ok)
        self.assertTrue(replay.already_applied)
        self.assertFalse(replay.can_execute)
        self.assertEqual(replay.attempt, first.attempt)
        self.assertEqual(raw[2].data.get("gate_id"), "ambiguous_side_effect")
        self.assertNotEqual(raw[2].returncode, 0)
        self.assertTrue(ambiguous.ambiguous)
        self.assertFalse(ambiguous.can_execute)
        self.assertIn(first.attempt, self.open_attempts(cp, directory))
        self.assertEqual(original_recorder._counters, {"tool:admission_probe": 2})
        self.assertEqual(replay_recorder._counters, {"tool:admission_probe": 4})

    def test_open_replay_refuses_loop_with_zero_or_one_prior_effect(self):
        for before in ("", "x"):
            with self.subTest(before=before):
                root, cp, directory = self.ticket()
                _original, first = self.seed(cp, directory)
                if before:
                    (root / "payload-marker.txt").write_text(before, encoding="utf-8")
                fresh = self.recorder(cp, directory)
                events = []
                loop = _make_loop(root, fresh, events)
                with (
                    patch.object(fresh, "finish", wraps=fresh.finish) as finish,
                    patch.object(loop.registry, "invoke", wraps=loop.registry.invoke) as invoke,
                ):
                    result = loop._invoke("admission_probe", {})
                self.assertFalse(result.approved)
                self.assertFalse(result.result.ok)
                self.assertIn("此前动作的回执不能用于再次执行", result.result.content)
                self.assertIn("此前动作的回执不能用于再次执行", result.note)
                self.assertEqual(self.marker(root), before)
                self.assertIn(first.attempt, self.open_attempts(cp, directory))
                invoke.assert_not_called()
                finish.assert_not_called()
                self.assertNotIn("tool_start", [kind for kind, _payload in events])

    def test_completed_replay_refuses_and_new_occurrence_remains_usable(self):
        root, cp, directory = self.ticket()
        original, first = self.seed(cp, directory)
        (root / "payload-marker.txt").write_text("x", encoding="utf-8")
        self.assertTrue(original.finish(
            first.attempt, outcome="success", evidence="observed", check_ref="owned marker",
        ))
        fresh = self.recorder(cp, directory)
        loop = _make_loop(root, fresh, [])
        with patch.object(fresh, "finish", wraps=fresh.finish) as finish:
            replay = loop._invoke("admission_probe", {})
            self.assertFalse(replay.approved)
            self.assertEqual(self.marker(root), "x")
            finish.assert_not_called()
            new = loop._invoke("admission_probe", {})
        self.assertTrue(new.approved)
        self.assertTrue(new.result.ok)
        self.assertEqual(self.marker(root), "xx")
        self.assertEqual(finish.call_count, 1)
        self.assertNotEqual(finish.call_args.args[0], first.attempt)
        self.assertFalse(self.open_attempts(cp, directory))

    def test_old_duck_success_and_read_only_do_not_require_new_attribute(self):
        for read_only in (False, True):
            with self.subTest(read_only=read_only):
                root = self.enterContext(temp_workspace()).resolve()
                duck = SimpleNamespace(
                    start=Mock(return_value=SimpleNamespace(
                        can_execute=True, attempt="duck-a1", detail="",
                    )),
                    finish=Mock(return_value=True),
                )
                result = _make_loop(root, duck, [], read_only=read_only)._invoke("admission_probe", {})
                self.assertTrue(result.approved)
                self.assertTrue(result.result.ok)
                self.assertEqual(self.marker(root), "" if read_only else "x")
                self.assertEqual(duck.start.call_count, 0 if read_only else 1)
                self.assertEqual(duck.finish.call_count, 0 if read_only else 1)

    def test_start_exception_invoke_exception_and_finish_false_do_not_fake_closure(self):
        for failure in ("start", "malformed", "invoke", "handler", "finish"):
            with self.subTest(failure=failure):
                root, cp, directory = self.ticket()
                recorder = self.recorder(cp, directory)
                loop = _make_loop(root, recorder, [])
                with patch.object(recorder, "finish", wraps=recorder.finish) as finish:
                    if failure == "start":
                        with patch.object(cp, "operation_start", side_effect=OSError("start unavailable")):
                            with self.assertRaises(OSError):
                                loop._invoke("admission_probe", {})
                        self.assertFalse(self.open_attempts(cp, directory))
                        self.assertEqual(self.marker(root), "")
                        finish.assert_not_called()
                    elif failure == "malformed":
                        raw = ControlResult((), 0, {"ok": True, "attempt": "bad", "already_applied": 1})
                        with (
                            patch.object(cp, "operation_start", return_value=raw),
                            patch.object(loop.registry, "invoke", wraps=loop.registry.invoke) as invoke,
                        ):
                            result = loop._invoke("admission_probe", {})
                        self.assertFalse(result.approved)
                        self.assertFalse(result.result.ok)
                        self.assertEqual(self.marker(root), "")
                        self.assertIs(raw.data["already_applied"], 1)
                        self.assertFalse(self.open_attempts(cp, directory))
                        invoke.assert_not_called()
                        finish.assert_not_called()
                    elif failure == "invoke":
                        # Exception in the registry invocation boundary, not a normalized handler failure.
                        with patch.object(loop.registry, "invoke", side_effect=OSError("unknown invocation")):
                            with self.assertRaises(OSError):
                                loop._invoke("admission_probe", {})
                        self.assertTrue(self.open_attempts(cp, directory))
                        self.assertEqual(self.marker(root), "")
                        finish.assert_not_called()
                    elif failure == "handler":
                        with patch.object(
                            loop.registry.get("admission_probe"), "handler",
                            side_effect=OSError("normalized handler failure"),
                        ):
                            result = loop._invoke("admission_probe", {})
                        self.assertFalse(result.result.ok)
                        self.assertEqual(result.result.meta["error"], "tool_exception")
                        self.assertEqual(self.marker(root), "")
                        self.assertFalse(self.open_attempts(cp, directory))
                        self.assertEqual(finish.call_count, 1)
                        self.assertEqual(finish.call_args.kwargs["failure"], "deterministic_failure")
                    else:
                        with patch.object(
                            cp, "operation_finish", return_value=ControlResult((), 1, {"ok": False}),
                        ):
                            result = loop._invoke("admission_probe", {})
                        self.assertTrue(result.result.meta["operation_finish_failed"])
                        self.assertEqual(self.marker(root), "x")
                        self.assertTrue(self.open_attempts(cp, directory))
                        self.assertEqual(finish.call_count, 1)

    def test_real_child_restart_reuses_durable_cp_but_never_reexecutes_payload(self):
        root, cp, directory = self.ticket()
        child = r'''
import json, os, sys
from pathlib import Path
from icode.config import Settings
from icode.control import ControlPlane
from icode.operations import OperationRecorder
from tests.test_operation_admission import _make_loop, _probe_input
skill, root, directory = map(Path, sys.argv[1:4])
cp = ControlPlane(Settings(skill_root=skill, python=sys.executable))
recorder = OperationRecorder(cp, directory, "ADMISSION", scope="plan")
if sys.argv[4] == "seed":
    result = recorder.start(name="tool:admission_probe", opclass="managed_write", input_desc=_probe_input())
    if not result.can_execute:
        raise AssertionError(result.detail)
    (root / "payload-marker.txt").write_text("x", encoding="utf-8")
    print(json.dumps({"pid": os.getpid(), "attempt": result.attempt}))
else:
    finished = []
    original_finish = recorder.finish
    def observed_finish(*args, **kwargs):
        finished.append(args)
        return original_finish(*args, **kwargs)
    recorder.finish = observed_finish
    events = []
    invocation = _make_loop(root, recorder, events)._invoke("admission_probe", {})
    trace = cp.trace(directory)
    if trace.returncode != 0 or trace.data.get("ok") is not True:
        raise AssertionError("trace unavailable")
    print(json.dumps({"pid": os.getpid(), "approved": invocation.approved,
        "ok": invocation.result.ok, "finish_calls": len(finished),
        "tool_start": sum(kind == "tool_start" for kind, _ in events),
        "content": invocation.result.content, "open": list(trace.data["open_operations"])}))
'''
        outputs = []
        for mode in ("seed", "replay"):
            proc = subprocess.run(
                [sys.executable, "-B", "-c", child, str(self.settings.skill_root),
                 str(root), str(directory), mode],
                cwd=str(Path(__file__).resolve().parents[1]),
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=30, shell=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            outputs.append(json.loads(proc.stdout))
            self.assertNotEqual(outputs[-1]["pid"], os.getpid())
        self.assertEqual(self.marker(root), "x")
        self.assertFalse(outputs[1]["approved"])
        self.assertFalse(outputs[1]["ok"])
        self.assertEqual(outputs[1]["finish_calls"], 0)
        self.assertEqual(outputs[1]["tool_start"], 0)
        self.assertIn("此前动作的回执不能用于再次执行", outputs[1]["content"])
        self.assertIn(outputs[0]["attempt"], outputs[1]["open"])
        self.assertIn(outputs[0]["attempt"], self.open_attempts(cp, directory))

    def test_converged_read_only_observation_preserves_open_receipt_and_effect(self):
        root, cp, directory = self.ticket()
        _original, first = self.seed(cp, directory)
        (root / "payload-marker.txt").write_text("x", encoding="utf-8")
        self.assertFalse(
            _make_loop(root, self.recorder(cp, directory), [])._invoke("admission_probe", {}).approved,
        )
        event_bytes = (directory / ".ico_events.jsonl").read_bytes()
        started = time.monotonic()
        for _ in range(3):
            threading.Event().wait(0.05)
            self.assertIn(first.attempt, self.open_attempts(cp, directory))
            self.assertEqual(self.marker(root), "x")
            self.assertEqual((directory / ".ico_events.jsonl").read_bytes(), event_bytes)
        self.assertGreaterEqual(time.monotonic() - started, 0.15)
