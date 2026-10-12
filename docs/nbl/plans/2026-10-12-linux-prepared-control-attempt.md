# Linux S2b1 原始控制面 attempt 与新鲜绑定观察 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development to implement this plan task-by-task. 用户覆盖 worktree、model override、分散 commit 和自动 handoff：main-only，TEST ONLY 与不同 SOURCE 作者串行，作者无 stage/commit/push 权限。本文交付后 STOP，等待 root 独立 PLAN SPEC、不同 QUALITY 及明确 GO。

**Goal:** 保留原始 CP start 回执，在现有 attachment 绑定与每次 borrow 时查询真实 CP 当前 open_steps，严格核捕获坐标。

**Architecture:** ControlPlane 新增私有 raw start seam，公开 step_start 保留全部旧语义。独立 portable 私有适配捕获真实 CP、Path、ticket、step、attempt，只负责有限校验与 fresh trace，不承担 helper/session/lease 生命周期。

**Tech Stack:** Python 3.11+、标准库 unittest、固定 vendor CLI、既有 Linux PreparedTests 实际资源 fixture。

---

## 边界、基线与技能

设计：[S2b1 DESIGN](../specs/2026-10-12-linux-prepared-control-attempt-design.md)，直接母合同：[单步 scope](../specs/2026-10-12-linux-prepared-step-scope-design.md)、[S2a context](../specs/2026-10-12-linux-prepared-tool-context-design.md)。2026-10-12 writer 实查 main `667c92af7b338b9983c9829251a0f70128dd1d8e`；此前 deadline 已由 root 实际发布。DESIGN 批准 SHA256 `35fa37229e7279e610a5ccb42dfbdcc27ad64125ca5eec93ab10716b7aad49bb`；本 PLAN 尚待独立双审。本 writer 使用 writing-plans 技能形成完整资产，用 TDD/antipattern 约束正式顺序，用 subagent-driven 模板约束两自审及独立审核，用文档契约技能运行原 scanner；不自动触发实施。

三问成立：truthy attempt 的 str 转换确有类型丢失；复用现有 run、trace 与 attachment observer；仅新严格分支改变未来准备链，公开接口/旧调用链不收紧。结构化 MCP 已完成需求、方案、风险三步；结论是有限 raw seam + fresh observer，真实正例与有限负控分账，无第二资源 owner。

| 六个未来发布路径 | 责任 / 当前状态 |
| --- | --- |
| `src/icode/control.py` | 仅 step_start seam；基线 SHA256 `acda84bf6bdec0488199c7c4620e9037203e37968e89d8c2b6a6aa80b765279e` |
| `src/icode/linux_prepared_control.py` | 新 portable 严格 CP binding 模块，当前不存在 |
| `tests/test_linux_prepared_control_attempt.py` | 新完整正式 TEST，当前不存在 |
| `docs/nbl/specs/2026-10-12-linux-prepared-control-attempt-design.md` | root 唯一维护批准设计和实际追加证据 |
| `docs/nbl/plans/2026-10-12-linux-prepared-control-attempt.md` | 本 writer 唯一可写路径 |
| `docs/agent-landscape-live.md` | root 唯一维护；已有 dirty 证据必须保留 |

`src/icode/linux_prepared_step.py` 只读 SHA256 `f165ba45cb07152079c0bb4a3ea1bb3059b7af28a23732cd5b70f74155547075`。deadline/runner/tools/chain/attachment/core/native/vendor/CI 和所有旧 tests 只读。固定 vendor 实查 `21566a589cbe98bd35372a04bbb6ca1c51d8eed2`；不借 installed/模型/KEY/六步/90% 或 R2/R3 验收信用。CP fresh 查询不是跨系统事务锁，仍受可信宿主禁止并发修改合同约束。

任务链：PLAN 双审/GO → Task 1 作者/root有效 RED → Task 2 不同源码作者/root GREEN → Task 3 fresh SOURCE SPEC/不同 QUALITY、root 唯一完整门及最终文档 → Task 4 root 精确 index/一次 main 发布。下文资产与writer记录是初始计划上下文；checkbox只按后续真实证据更新，末节正式记录与原计划诊断分账，不用命令存在推定已执行。

## Task 1：fresh TEST ONLY 完整资产与真实 RED

**状态**

- [x] 任务完成

**Dependencies:** None（正式执行先有 PLAN 双审零遗留及 root GO）
**Parallelizable:** No (TEST 落盘与作者/root RED 串行，禁止提前 SOURCE)

- [x] **Step 1：作者核 main/三基线/vendor，root 提供完整任务和上下文，fresh TEST 作者只 apply_patch 新 TEST。**

~~~bash
set -euo pipefail
test "$(git branch --show-current)" = main
test "$(git rev-parse HEAD)" = 667c92af7b338b9983c9829251a0f70128dd1d8e
test "$(git -C vendor/icode-skill rev-parse HEAD)" = 21566a589cbe98bd35372a04bbb6ca1c51d8eed2
sha256sum src/icode/control.py src/icode/linux_prepared_step.py docs/nbl/specs/2026-10-12-linux-prepared-control-attempt-design.md
git status --short
~~~

任一基线漂移返回 root，不改未知改动；测试 fixture 自己新建 temp 目录，可在其中 git init/add/commit，不能改用户工程或 vendor。结果注入仅用于 raw extraction seam 和严格拒绝负控，真实 CP 正例不 mock trace。测试文件完整内容如下（asset: TEST）：

~~~python
"""Real CP events and existing resources; no runner/installed/isolation credit."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from tests._support import REPO_ROOT
from icode.config import Settings
from icode.control import ControlError, ControlPlane, ControlResult, make_request
from icode.handshake import next_out_dir

MODULE = 'icode.linux_prepared_control'
if importlib.util.find_spec(MODULE) is None:
    binding = None
else:
    from icode.linux_prepared_control import _prepared_control_attempt_binding as binding

ERROR = 'Linux prepared control attempt is unavailable'
VENDOR = REPO_ROOT / 'vendor' / 'icode-skill'


class Guarded(unittest.TestCase):
    def require_binding(self):
        # A real assertion failure on the unchanged source, never ImportError RED.
        self.assertTrue(callable(binding), 'prepared binding callable is missing')
        return binding

    def raw(self, cp, out_dir, *, ticket='CP-PREPARED', step='plan', request='start-one'):
        target = getattr(cp, '_step_start_result', None)
        self.assertTrue(callable(target), 'raw step start callable is missing')
        return target(out_dir, step, ticket_id=ticket, request=request)

    def reject(self, call):
        with self.assertRaises(ControlError) as caught:
            call()
        error = caught.exception
        self.assertEqual(str(error), ERROR)
        self.assertIsNone(error.returncode)
        self.assertEqual(error.stderr, '')
        self.assertIsNone(error.__cause__)
        self.assertTrue(error.__suppress_context__)


class RawCompatibilityTests(Guarded):
    def test_raw_keeps_result_identity_and_original_single_run_shape(self):
        cp = ControlPlane(Settings(VENDOR), check=False)
        target = getattr(cp, '_step_start_result', None)
        self.assertTrue(callable(target), 'raw step start callable is missing')
        for request in (None, '', 'explicit-request'):
            sentinel = object()
            result = ControlResult((), 7, {'attempt': sentinel})
            with patch.object(cp, 'run', return_value=result) as run:
                got = target(Path('/host/ticket'), 'plan', ticket_id='T', request=request)
            self.assertIs(got, result)
            self.assertIs(got.data['attempt'], sentinel)
            run.assert_called_once_with('step', '--dir', '/host/ticket', '--step',
                'plan', '--phase', 'start', '--request',
                request or make_request('T', 'step-plan-start'))

    def test_public_old_truthy_str_error_and_ok_semantics(self):
        cp = ControlPlane(Settings(VENDOR), check=False)
        self.assertTrue(ControlResult((), 0, {}).ok)
        self.assertTrue(ControlResult((), False, {'ok': 1}).ok)
        for value in ('attempt', ' ', 3, True, ['a'], {'a': 1}):
            result = ControlResult((), 0, {'attempt': value})
            with patch.object(cp, 'run', return_value=result) as run:
                self.assertEqual(cp.step_start('/host/ticket', 'plan', ticket_id='T'), str(value))
            run.assert_called_once_with('step', '--dir', '/host/ticket', '--step',
                'plan', '--phase', 'start', '--request', make_request('T', 'step-plan-start'))
        for value in (None, '', 0, False, [], {}):
            data = {'attempt': value}
            with patch.object(cp, 'run', return_value=ControlResult((), 0, data)):
                with self.assertRaises(ControlError) as caught:
                    cp.step_start('/host/ticket', 'plan', ticket_id='T')
            self.assertEqual(str(caught.exception), f'step start 未返回 attempt：{data}')
        for error in (ControlError('legacy body'), KeyboardInterrupt(), SystemExit(2)):
            with patch.object(cp, 'run', side_effect=error):
                with self.assertRaises(type(error)) as caught:
                    cp.step_start('/host/ticket', 'plan', ticket_id='T')
            self.assertIs(caught.exception, error)


class RealCPTests(Guarded):
    def setUp(self):
        self.require_binding()
        self.assertTrue(Settings(VENDOR).exists(), 'fixed vendor fixture is unavailable')
        temporary = tempfile.TemporaryDirectory(prefix='icode_cp_prepared_')
        self.addCleanup(temporary.cleanup)
        self.cp_root = Path(temporary.name)
        self.out = next_out_dir(self.cp_root)
        self.ticket = 'CP-PREPARED'
        self.cp = ControlPlane(Settings(VENDOR))
        created = self.cp.create(self.out, ticket_id=self.ticket,
            requirement='isolated prepared control fixture', birth='plan')
        self.assertIs(created.data.get('ok'), True)
        self.start = self.raw(self.cp, self.out)
        self.attempt = self.start.data['attempt']

    def pair(self, result=None, **changes):
        args = dict(out_dir=self.out, ticket_id=self.ticket, step='plan',
            start_result=self.start if result is None else result)
        args.update(changes)
        return self.require_binding()(self.cp, **args)

    def stopped(self):
        finish = self.cp.step_finish(self.out, 'plan', self.attempt, 'blocked',
            ticket_id=self.ticket, request='finish-one', evidence=['software-fixture:closed'])
        self.assertIs(finish.data.get('ok'), True)

    def test_actual_start_replay_window_trace_and_new_attempt(self):
        self.assertNotIn('ticket_id', self.start.data)
        replay = self.raw(self.cp, self.out)
        self.assertNotIn('phase', replay.data)
        self.assertIs(replay.data.get('already_applied'), True)
        attempt, observer = self.pair(replay)
        self.assertEqual(attempt, self.attempt)
        # Append a real later event so limit=1 excludes the target start.
        updated = self.cp.step_check(self.out, 'plan', attempt, 'before_write',
            ticket_id=self.ticket, request='later-event')
        self.assertIs(updated.data.get('ok'), True)
        trace = self.cp.trace(self.out, limit=1)
        self.assertEqual(len(trace.data['events']), 1)
        self.assertNotEqual((trace.data['events'][0]).get('type'), 'step_started')
        self.assertIn(attempt, trace.data['open_steps'])
        self.assertNotIn('step', trace.data)
        with patch.object(self.cp, 'trace', wraps=self.cp.trace) as query:
            self.assertIsNone(observer(attempt))
            self.assertIsNone(observer(attempt))
            self.assertEqual(query.call_count, 2)
            query.assert_called_with(self.out, limit=1)
        self.stopped()
        self.reject(lambda: observer(attempt))
        newer = self.raw(self.cp, self.out, request='start-two')
        next_attempt, next_observer = self.pair(newer)
        self.assertNotEqual(next_attempt, attempt)
        self.assertIsNone(next_observer(next_attempt))
        self.reject(lambda: next_observer(attempt))
        self.reject(lambda: observer(next_attempt))
        self.reject(lambda: observer(attempt))

    def test_raw_bad_attempt_types_and_no_conversion(self):
        class NoString:
            def __str__(self):
                raise AssertionError('must never stringify an attempt')
        for value in (None, False, True, 0, 1, [], {}, NoString(), '', ' ', '\t', 'a\n', 'a\x7f'):
            with self.subTest(value_type=type(value).__name__):
                data = dict(self.start.data, attempt=value)
                self.reject(lambda: self.pair(ControlResult((), 0, data)))

    def test_start_receipt_type_returncode_ok_step_matrix(self):
        bad = [None, {}, object(), ControlResult((), 0, []),
            ControlResult((), False, self.start.data), ControlResult((), True, self.start.data),
            ControlResult((), 0.0, self.start.data), ControlResult((), 1, self.start.data)]
        for key, values in (('ok', (None, False, 1, 'true')),
                ('step', (None, True, 1, 'code', 'plan\n'))):
            missing = dict(self.start.data)
            missing.pop(key, None)
            bad.append(ControlResult((), 0, missing))
            bad.extend(ControlResult((), 0, dict(self.start.data, **{key: value})) for value in values)
        for result in bad:
            self.reject(lambda result=result: self.require_binding()(self.cp,
                out_dir=self.out, ticket_id=self.ticket, step='plan', start_result=result))

    def test_captured_coordinates_invalid_inputs_and_fresh_wrong_ticket_step(self):
        bind = self.require_binding()
        for key, values in (('ticket_id', (None, True, '', ' ', 'T\n')),
                ('step', (None, True, '', ' ', 'plan\n')),
                ('out_dir', (None, {}, '', ' ', '/host\n'))):
            for value in values:
                self.reject(lambda key=key, value=value: self.pair(**{key: value}))
        self.reject(lambda: bind({}, out_dir=self.out, ticket_id=self.ticket,
            step='plan', start_result=self.start))
        supplied = dict(out_dir=str(self.out), ticket_id=self.ticket, step='plan', start_result=self.start)
        attempt, observer = bind(self.cp, **supplied)
        supplied.update(out_dir=self.cp_root / 'other', ticket_id='OTHER', step='code')
        with patch.object(self.cp, 'trace', wraps=self.cp.trace) as query:
            self.assertIsNone(observer(attempt))
            query.assert_called_once_with(self.out, limit=1)
        _, wrong_ticket = self.pair(ticket_id='OTHER')
        self.reject(lambda: wrong_ticket(attempt))
        wrong_start = ControlResult((), 0, dict(self.start.data, step='code'))
        _, wrong_step = self.pair(wrong_start, step='code')
        self.reject(lambda: wrong_step(attempt))
        for actual in (None, True, 1, '', ' ', attempt + '-other'):
            with patch.object(self.cp, 'trace', wraps=self.cp.trace) as query:
                self.reject(lambda actual=actual: observer(actual))
                query.assert_not_called()

    def test_trace_strict_schema_negative_controls(self):
        attempt, observer = self.pair()
        original = self.cp.trace(self.out, limit=1)
        bad = [None, {}, object(), ControlResult((), 0, []),
            ControlResult((), False, original.data), ControlResult((), True, original.data),
            ControlResult((), 0.0, original.data),
            ControlResult((), 1, original.data)]
        for key, values in (('ok', (None, False, 1, 'true')),
                ('ticket_id', (None, True, 'OTHER')),
                ('open_steps', (None, [], {}, {attempt: None}, {attempt: []},
                    {attempt: {}}, {attempt: {'step': True}}, {attempt: {'step': 'code'}}))):
            missing = dict(original.data)
            missing.pop(key, None)
            bad.append(ControlResult((), 0, missing))
            bad.extend(ControlResult((), 0, dict(original.data, **{key: value})) for value in values)
        for result in bad:
            with patch.object(self.cp, 'trace', return_value=result) as query:
                self.reject(lambda: observer(attempt))
                query.assert_called_once_with(self.out, limit=1)
        # Recovery uses a fresh real query; a bad result never caches authority.
        self.assertIsNone(observer(attempt))

    def test_exact_dict_and_str_subclasses_rejected(self):
        class DictSubclass(dict):
            pass
        class StringSubclass(str):
            pass
        class IntSubclass(int):
            pass
        for result in (ControlResult((), 0, DictSubclass(self.start.data)),
                ControlResult((), IntSubclass(0), self.start.data),
                ControlResult((), 0, dict(self.start.data, step=StringSubclass('plan'))),
                ControlResult((), 0, dict(self.start.data, attempt=StringSubclass(self.attempt)))):
            self.reject(lambda result=result: self.pair(result))
        attempt, observer = self.pair()
        original = self.cp.trace(self.out, limit=1)
        for data in (DictSubclass(original.data), dict(original.data,
                ticket_id=StringSubclass(self.ticket)), dict(original.data,
                open_steps=DictSubclass(original.data['open_steps'])), dict(original.data,
                open_steps={attempt: DictSubclass(step='plan')}), dict(original.data,
                open_steps={attempt: {'step': StringSubclass('plan')}})):
            with patch.object(self.cp, 'trace', return_value=ControlResult((), 0, data)):
                self.reject(lambda: observer(attempt))

    def test_ordinary_fault_fixed_and_signals_original(self):
        attempt, observer = self.pair()
        for error in (ControlError('private path/body', stderr='private body'),
                OSError('private path/body'), ValueError('private receipt')):
            with patch.object(self.cp, 'trace', side_effect=error):
                self.reject(lambda: observer(attempt))
        for signal in (KeyboardInterrupt('private signal'), SystemExit(7)):
            with patch.object(self.cp, 'trace', side_effect=signal):
                with self.assertRaises(type(signal)) as caught:
                    observer(attempt)
            self.assertIs(caught.exception, signal)

    def test_actual_broken_event_chain_rejects_observer(self):
        attempt, observer = self.pair()
        self.assertIsNone(observer(attempt))
        events = self.out / '.ico_events.jsonl'
        # Deliberate fault injection in this newly owned temp ticket only.
        # This is not a product writer or an alternate observer/read path.
        with events.open('a', encoding='utf-8') as stream:
            stream.write('{invalid isolated event\n')
        self.reject(lambda: observer(attempt))


# Never import Linux-only fixture at module top on a non-Linux platform.
if sys.platform.startswith('linux'):
    from tests import test_linux_prepared_step as prepared_fixture

    class AttachmentCPTests(Guarded):
        def setUp(self):
            self.require_binding()
            self.resources = prepared_fixture.PreparedTests(methodName='runTest')
            self.addCleanup(self.resources.doCleanups)
            self.resources.setUp()
            self.resources.policy = self.resources.session.policy('plan', process_limit=16,
                wall_timeout_seconds=30, output_limit_bytes=4096)
            temporary = tempfile.TemporaryDirectory(prefix='icode_cp_attachment_')
            self.addCleanup(temporary.cleanup)
            self.out = next_out_dir(Path(temporary.name))
            self.ticket = self.resources.session.ticket_id
            self.cp = ControlPlane(Settings(VENDOR))
            self.cp.create(self.out, ticket_id=self.ticket,
                requirement='isolated actual attachment binding', birth='plan')
            self.start = self.raw(self.cp, self.out, ticket=self.ticket)
            self.attempt, self.observer = self.require_binding()(self.cp,
                out_dir=self.out, ticket_id=self.ticket, step='plan', start_result=self.start)
            self.scope = self.resources.prepare()
            self.assertEqual(self.resources.policy.step, self.start.data['step'])
            self.assertEqual(self.resources.policy.ticket_id, self.ticket)
            self.view = self.resources.attach(self.scope)
            self.helper_fd = self.scope._owner.fileno()

        def borrow(self, **changes):
            args = dict(policy=self.resources.policy,
                workspace_session=self.resources.session, attempt=self.attempt)
            args.update(changes)
            return self.view.borrow(**args)

        def owner_live(self):
            self.assertEqual(self.scope._owner_state, 'active')
            self.assertEqual(self.scope._owner.fileno(), self.helper_fd)
            prepared_fixture.REAL_FSTAT(self.helper_fd)
            self.resources.session.lease._validate_active()
            self.assertIsNotNone(self.resources.session.workspace_fd_identity)

        def finish_cp(self):
            self.cp.step_finish(self.out, 'plan', self.attempt, 'blocked',
                ticket_id=self.ticket, request='attachment-finish', evidence=['software-fixture:closed'])

        def test_real_bind_and_each_actual_borrow_requeries_then_external_close(self):
            with patch.object(self.cp, 'trace', wraps=self.cp.trace) as query:
                self.view._bind_attempt(self.attempt, validate_attempt=self.observer)
                self.assertEqual(query.call_count, 1)
                for expected in (2, 3):
                    with self.borrow() as owner:
                        self.assertIs(owner, self.scope._owner)
                        self.assertEqual(query.call_count, expected)
                    self.owner_live()
                query.assert_called_with(self.out, limit=1)
            self.assertEqual(self.scope._consume_state, 'attached_bound')
            self.view.finish()
            self.owner_live()
            self.scope.close()
            with self.assertRaises(OSError):
                prepared_fixture.REAL_FSTAT(self.helper_fd)
            self.resources.session.lease._validate_active()

        def test_closed_or_broken_cp_before_wrapper_payload_owner_stays_external(self):
            self.view._bind_attempt(self.attempt, validate_attempt=self.observer)
            payload = []
            with self.borrow():
                payload.append('actual allowed borrow')
            self.finish_cp()
            with self.assertRaises(prepared_fixture.subject.LinuxPreparedStepError):
                with self.borrow():
                    payload.append('wrapper/payload must not run')
            self.assertEqual(payload, ['actual allowed borrow'])
            self.owner_live()
            self.view.finish()
            self.owner_live()
            self.scope.close()
            with self.assertRaises(OSError):
                prepared_fixture.REAL_FSTAT(self.helper_fd)

        def test_chain_damage_after_bind_before_wrapper_payload(self):
            self.view._bind_attempt(self.attempt, validate_attempt=self.observer)
            events = self.out / '.ico_events.jsonl'
            # Intentional negative control, confined to this new temp ticket.
            with events.open('a', encoding='utf-8') as stream:
                stream.write('{invalid attachment fixture event\n')
            payload = []
            with self.assertRaises(prepared_fixture.subject.LinuxPreparedStepError):
                with self.borrow():
                    payload.append('wrapper/payload must not run')
            self.assertEqual(payload, [])
            self.owner_live()
            self.view.finish()
            self.scope.close()

        def test_bind_fault_does_not_grant_bound_or_close_owner_and_signals_survive(self):
            for error in (OSError('private body'), KeyboardInterrupt(), SystemExit(3)):
                with patch.object(self.cp, 'trace', side_effect=error):
                    kind = prepared_fixture.subject.LinuxPreparedStepError if isinstance(error, Exception) else type(error)
                    with self.assertRaises(kind) as caught:
                        self.view._bind_attempt(self.attempt, validate_attempt=self.observer)
                if not isinstance(error, Exception):
                    self.assertIs(caught.exception, error)
                self.assertEqual(self.scope._consume_state, 'attached_pending')
                self.assertIsNone(self.view._attempt)
                self.assertIsNone(self.view._validator)
                self.owner_live()
            self.view._bind_attempt(self.attempt, validate_attempt=self.observer)
            for signal in (KeyboardInterrupt(), SystemExit(4)):
                with patch.object(self.cp, 'trace', side_effect=signal):
                    with self.assertRaises(type(signal)) as caught:
                        with self.borrow():
                            self.fail('payload must not run')
                self.assertIs(caught.exception, signal)
                self.assertFalse(self.scope._inflight)
                self.owner_live()
            self.view.finish()
            self.scope.close()

        def test_actual_closed_cp_before_bind_remains_pending_external_owner_live(self):
            self.finish_cp()
            with self.assertRaises(prepared_fixture.subject.LinuxPreparedStepError):
                self.view._bind_attempt(self.attempt, validate_attempt=self.observer)
            self.assertEqual(self.scope._consume_state, 'attached_pending')
            self.assertIsNone(self.view._attempt)
            self.assertIsNone(self.view._validator)
            self.owner_live()
            self.view.finish()
            self.owner_live()
            self.scope.close()
            with self.assertRaises(OSError):
                prepared_fixture.REAL_FSTAT(self.helper_fd)

        def test_cp_success_does_not_replace_actual_session_policy_helper_gates(self):
            from dataclasses import replace
            self.view._bind_attempt(self.attempt, validate_attempt=self.observer)
            for changes in (dict(workspace_session=replace(self.resources.session)),
                    dict(policy=replace(self.resources.policy)), dict(attempt='other-attempt')):
                with self.assertRaises(prepared_fixture.subject.LinuxPreparedStepError):
                    with self.borrow(**changes):
                        self.fail('payload must not run')
            self.owner_live()
            with self.borrow() as owner:
                self.assertIs(owner, self.scope._owner)
            # CP remains open, but actual held/source helper validation still wins.
            self.resources.write_image(prepared_fixture.image((1, 1)))
            self.assertIsNone(self.observer(self.attempt))
            with self.assertRaises(prepared_fixture.subject.LinuxPreparedStepError):
                with self.borrow():
                    self.fail('helper drift must block payload')
            self.view.finish()
            self.scope.close()


if __name__ == '__main__':
    unittest.main()
~~~

本 TEST 在 prepare 前通过真实 session.policy('plan') 建立与 CP 工单相同 ticket/step 的实际政策；不改原 fixture，CP观测与真实scope坐标一致。这里只测试 observer 在原 bind/borrow 内被调用，S2b2仍须在真实runner接线。合成 ELF fixture 非实际 installed/native payload，borrow body 的标记表示 wrapper/payload 前界限，不能授实际命令执行信用。复用原 fixture 的 git commit 仅发生在它自己的新 temp source。

- [x] **Step 2：作者运行正式 TEST，记录有效 assertion RED；root 在同 BASE 独立重复。**

~~~bash
.venv/bin/python -B -m unittest -v tests.test_linux_prepared_control_attempt
~~~

预期 exit1，缺 raw callable 和 binding callable 的 assertTrue 失败；旧公开兼容测试应通过。不得把 ImportError、TypeError、fixture 错误或 skip 算有效 RED，不能为变绿改预期。作者报告 tests/failures/errors/skips、原输出、实际时间、TEST SHA256及不变的两源码摘要；root独立运行并保留双方原日志。负控详细矩阵要在实现后真正命中严格分支，不把 setUp 的缺 callable 断言当各负控已验证。

- [x] **Step 3：TEST 作者内置 SPEC→QUALITY 两自审后返回，root确认两份有效 RED 再放行不同 SOURCE 作者。**

逐项核完整可收集、guarded断言、portable CP与条件Linuxfixture、真实正例、负控seam、无用户/vendor写入；核 fixture 卫生和首信号、有效失败原因。仅新TEST变化，禁止stage/commit。

## Task 2：不同 fresh SOURCE 作者实施唯一精确补丁

**状态**

- [x] 任务完成

**Dependencies:** Task 1（作者/root有效正式 RED，实际TEST与资产字节一致）
**Parallelizable:** No (不同作者、仅两SOURCE、无并发实现)

- [x] **Step 1：源码作者完整读取实际TEST/设计/control/只读attachment，再仅 apply_patch 两源码。**

`control.py` 唯一统一差分（asset: CONTROL_DIFF）：

~~~diff
--- a/src/icode/control.py
+++ b/src/icode/control.py
@@ -185,9 +185,15 @@
     def step_start(self, out_dir: Path | str, step: str, *, ticket_id: str, request: str | None = None) -> str:
-        result = self.run(
+        result = self._step_start_result(out_dir, step, ticket_id=ticket_id, request=request)
+        attempt = result.data.get("attempt")
+        if not attempt:
+            raise ControlError(f"step start 未返回 attempt：{result.data}")
+        return str(attempt)
+
+    def _step_start_result(
+        self, out_dir: Path | str, step: str, *, ticket_id: str, request: str | None = None,
+    ) -> ControlResult:
+        """Private raw receipt; public step_start retains its historical semantics."""
+        return self.run(
             "step", "--dir", str(out_dir), "--step", step, "--phase", "start",
             "--request", request or make_request(ticket_id, f"step-{step}-start"),
         )
-        attempt = result.data.get("attempt")
-        if not attempt:
-            raise ControlError(f"step start 未返回 attempt：{result.data}")
-        return str(attempt)
~~~

新 `src/icode/linux_prepared_control.py` 全文（asset: SOURCE）：

~~~python
"""Private portable CP observation; it owns no execution or OS resources."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from .control import ControlError, ControlPlane, ControlResult

_ERROR = 'Linux prepared control attempt is unavailable'


def _text(value: object) -> bool:
    return (type(value) is str and bool(value.strip())
        and not any(ord(char) < 32 or ord(char) == 127 for char in value))


def _receipt(result: object) -> dict:
    if (type(result) is not ControlResult or type(result.returncode) is not int
            or result.returncode != 0 or type(result.data) is not dict
            or result.data.get('ok') is not True):
        raise ControlError(_ERROR)
    return result.data


def _prepared_control_attempt_binding(
    control: ControlPlane, *, out_dir: Path | str, ticket_id: str, step: str,
    start_result: ControlResult,
) -> tuple[str, Callable[[str], None]]:
    """Capture trusted host coordinates; every observer invocation queries CP."""
    try:
        if (not isinstance(control, ControlPlane) or not _text(ticket_id) or not _text(step)
                or not isinstance(out_dir, (Path, str))
                or (isinstance(out_dir, str) and not _text(out_dir))):
            raise ControlError(_ERROR)
        captured_dir = Path(out_dir)
        data = _receipt(start_result)
        if type(data.get('step')) is not str or data['step'] != step:
            raise ControlError(_ERROR)
        attempt = data.get('attempt')
        if not _text(attempt):
            raise ControlError(_ERROR)
    except Exception:
        raise ControlError(_ERROR) from None

    def observer(actual: str) -> None:
        try:
            if type(actual) is not str or actual != attempt:
                raise ControlError(_ERROR)
            # limit limits displayed records, never the full-chain open_steps view.
            observed = _receipt(control.trace(captured_dir, limit=1))
            if type(observed.get('ticket_id')) is not str or observed['ticket_id'] != ticket_id:
                raise ControlError(_ERROR)
            opened = observed.get('open_steps')
            if type(opened) is not dict:
                raise ControlError(_ERROR)
            entry = opened.get(attempt)
            if (type(entry) is not dict or type(entry.get('step')) is not str
                    or entry['step'] != step):
                raise ControlError(_ERROR)
        except Exception:
            # Fixed, input-free ordinary rejection; KI/SE propagate as original objects.
            raise ControlError(_ERROR) from None

    return attempt, observer
~~~

无 kwargs/check 改动，无 raw attempt 提取/str；public truthy/原错误/str与全局 ok 不变。start 不强求 ticket/phase，observer 不强求 trace 顶层 step。不缓存、不读磁盘、不fallback、无finish/close/第二start，资源核验仍走原attachment。`Exception`包装保留原KI/SE；不输出原错误/body/data/path。

- [x] **Step 2：作者运行新TEST与明确限定回归，root在同字节独立重复。**

~~~bash
.venv/bin/python -B -m unittest -v tests.test_linux_prepared_control_attempt
.venv/bin/python -B -m unittest -v tests.test_control tests.test_runner tests.test_reasoning_budget tests.test_shared_runtime_budget tests.test_contract_budget_stop tests.test_linux_prepared_step tests.test_linux_prepared_broker tests.test_linux_prepared_tool_context
git diff --check
sha256sum src/icode/control.py src/icode/linux_prepared_control.py tests/test_linux_prepared_control_attempt.py src/icode/linux_prepared_step.py
~~~

这些模块当前实际存在，retry覆盖位于 `tests.test_runner`，不虚构 tests.test_retry。预期 exit0/无failure/error；非Linuxattachment不收集，无skip信用；本机有fixture机制则不把fixture缺失变skip。记录实际数量/时长/skips/footers，失败保留全历史，不以任意sleeps或假时钟修测试。

- [x] **Step 3：作者按模板内置 SPEC→QUALITY 两自审，核scope/异常/兼容/全文与差分投影字节，再返回。**

实际TEST与SOURCE全文精确一致，实际control严格diff投影一致；不能只用 AST 等价冒充字节相同。作者/root GREEN 是新的正式证据，PLAN RAM诊断不替代。两个源码或TEST变化使已取得审查失效，重新相关门。源码作者不改旧TEST/docs/vendor/CI、不stage/commit。

## Task 3：独立 SOURCE 审查、root 唯一完整门与最终文档

**状态**

- [x] 任务完成

**Dependencies:** Task 2
**Parallelizable:** No (先 fresh SPEC 后不同 QUALITY，之后冻结原完整门)

- [x] **Step 1：fresh SOURCE SPEC→不同 QUALITY 独立读取实际字节和双方原日志，各自运行新TEST。**

root给完整上下文，不以作者报告替源码审查。SPEC逐行核设计/六范围/原CLI/真实CP/strict矩阵/回放/窗口/fresh/关闭/chain坏/信号/原attachment前界限；QUALITY核维护性、无typed fake正例、无cache/resourceowner、两基线、portable collection及temp-only负控。两者 C0/I0/M0 方可前进；修订→fresh复审，不能接受“只剩minor”。

- [x] **Step 2：root唯一执行原完整preflight-j1，冻结SOURCE/TEST，记录真实started/done UTC、原log与footers。**

~~~bash
validation_log_dir=$(mktemp -d /tmp/icode-cp-prepared-preflight.XXXXXX)
script -q -e -f -c 'CMAKE_BUILD_PARALLEL_LEVEL=1 MAKEFLAGS=-j1 .venv/bin/python -B -u scripts/preflight.py' "$validation_log_dir/typescript"
~~~

仅root一个fullguard，不并跑第二完整门；不取消、降门、改入口；源码与TEST冻结摘要。60秒内短进展/轮询，保留原日志，输出未给的数量不猜。旧deadline/S2a完整门不授本片。源码/TEST再变必须重新审查和原完整门。

- [x] **Step 3：root apply_patch仅追加实际证据到三DOCS，阶段首尾刷新live相关研究，再运行两轮原scanner和fresh单门。**

研究沿已实际GET固定Codex/OpenHands证据；注明继承观察时间和固定提交，采纳原字段/身份配对/观察与资源分账；暂缓缓存/全局schema/runner合流；不适配typed身份授runtime执行权。许可MIT/Apache-2.0，无源码复制、权限依赖新增。需要新查询时独立只读调研，不把继承证据伪装fresh GET/HEAD或二十名单全复核。

~~~bash
.venv/bin/python -B /home/orbbec/.agents/skills/doc-contract-consistency-audit/scripts/check_consistency.py docs/nbl/plans/2026-10-12-linux-prepared-control-attempt.md docs/nbl/specs/2026-10-12-linux-prepared-control-attempt-design.md docs/agent-landscape-live.md
.venv/bin/python -B /home/orbbec/.agents/skills/doc-contract-consistency-audit/scripts/check_consistency.py docs/nbl/plans/2026-10-12-linux-prepared-control-attempt.md docs/nbl/specs/2026-10-12-linux-prepared-control-attempt-design.md docs/agent-landscape-live.md
.venv/bin/python -B scripts/preflight.py --only secrets
.venv/bin/python -B scripts/preflight.py --only submodule
git diff --check
~~~

每轮原scanner raw finding0/exit0，无whitelist/改脚本。文档再变重做两轮及fresh单门/diff。批准设计/计划摘要与实际追加后摘要分账；记录全部正式失败、重跑、footers和可信度边界，不预授未来checkbox。

## Task 4：root 六路径 fail-fast index 与一次 main 发布

**状态**

- [ ] 任务完成

**Dependencies:** Task 3（先次发布同SHA三CI全部终态及完整原日志齐）
**Parallelizable:** No (root sole publish)

- [ ] **Step 1：root收当前667c92a同SHA CI/provenance/Pages全部终态、metadata/jobs/full raw，保留外部失败；确认index初空及授权，再精确add。**

不取消/重跑外部失败、不用旧绿或猜ARM原因；仍运行则持续只读监控，不能靠任意sleep猜结束。待先次三CI日志齐与本地门全通过后：

~~~bash
set -euo pipefail
test "$(git branch --show-current)" = main
test -z "$(git diff --cached --name-only)"
sha256sum src/icode/control.py src/icode/linux_prepared_control.py tests/test_linux_prepared_control_attempt.py docs/nbl/specs/2026-10-12-linux-prepared-control-attempt-design.md docs/nbl/plans/2026-10-12-linux-prepared-control-attempt.md docs/agent-landscape-live.md
git add src/icode/control.py src/icode/linux_prepared_control.py tests/test_linux_prepared_control_attempt.py
git add -f docs/agent-landscape-live.md docs/nbl/specs/2026-10-12-linux-prepared-control-attempt-design.md docs/nbl/plans/2026-10-12-linux-prepared-control-attempt.md
git diff --cached --check
git diff --cached --name-only | sort | diff - <(printf '%s\n' src/icode/control.py src/icode/linux_prepared_control.py tests/test_linux_prepared_control_attempt.py docs/nbl/specs/2026-10-12-linux-prepared-control-attempt-design.md docs/nbl/plans/2026-10-12-linux-prepared-control-attempt.md docs/agent-landscape-live.md | sort)
for path in src/icode/control.py src/icode/linux_prepared_control.py tests/test_linux_prepared_control_attempt.py docs/nbl/specs/2026-10-12-linux-prepared-control-attempt-design.md docs/nbl/plans/2026-10-12-linux-prepared-control-attempt.md docs/agent-landscape-live.md; do
    git show ":$path" | cmp -s "$path" -
done
git diff --cached --stat
~~~

任一字节/集合/whitespace/基线不符立即返回，不reset用户改动，不用末尾stat exit0掩盖前面失败。三DOCS统一-f、SOURCE/TEST另add；writer/TEST/SOURCE作者无index权限。

- [ ] **Step 2：root唯一一次main commit/push，验证实际HEAD=remote，继续追新同SHA CI。**

~~~bash
set -euo pipefail
git commit -m "feat(linux): validate prepared attempts with fresh control trace"
git push origin main
git rev-parse HEAD
git ls-remote origin refs/heads/main
git status --short
~~~

发布SHA只能从真实返回取得，不能预写自引用未来SHA；不force/分散commit/worktree。新CI/installed/native、后续S2b2/S2c仍单列；本片成功仅授有限CP适配软件信用。

## writer 两自审、证据与停止线

SPEC自审映射：raw/旧接口→RawCompatibilityTests及CONTROL_DIFF；strict结果/坐标→RealCPTests矩阵及SOURCE；回放/窗口/fullchain/不同request新attempt→真实CP测试；bind/逐次实际borrow/failure不bound/外部owner→AttachmentCPTests；resource gates不被CP替代→真实session/policy负控及原prepared回归；portability→条件Linux import；发布/冻结/三CI/精确index→Task3–4。所有源码/TEST资产完整，无未定义fixture API，无占位，不扩runner或旧tests。

QUALITY自审：单一CP职责，无新owner/cache/协议/依赖，旧参数shape不变，普通错误固定、首信号原对象；temp-only事件破坏明确是负控。Linux实际session政策与CP相同ticket/step，scope既有门仍必核，不授生产runner或真正wrapper执行。必须从真实正式结果填门，不能依靠typed fake、RAM或文档自审替代。

writer内存诊断未落盘SOURCE/TEST。最终资产严格提取为围栏正文加一个LF（UTF-8）；TEST `20868a62bff6138ce3f1ff8d25faf25ed14b57a69fb6f92c22503d5606d22f80`（21930 bytes），CONTROL_DIFF `4d5af54cdcd254787b4ad2e7df3ff5ef04ff723648265f8838498b4b0fd3f4c0`（1183 bytes），SOURCE `875635c99689a7e95c6c5d48670727f1453ef3fa05fa6ebf714440747d3596a0`（2640 bytes）。统一diff old/new行数14/20与声明相等，原文第183行起上下文逐字节匹配；投影control `ffdaec53c10a23deed7b4383415fe48e1b54af706bee908a4f80fdece127c5ff`。三Python资产（TEST/SOURCE/投影control）compile通过。正式作者必须用最终字节运行，不能继承RAM为正式门。

最终RAM原基线16 tests/15有效assertion FAIL/0error/0skip，runner footer `Ran 16 tests in 0.002s`、`FAILED (failures=15)`；wrapper实测0.003s。RAM投影16/0F/E/skip，原footer `Ran 16 tests in 5.138s`、`OK`，wrapper5.139s，诊断命令实际exit0。原输出由exec session43282及completion9be448保存于本次工具记录，无磁盘源码/TEST。模拟sys.platform为darwin/win32分别成功收集10项且无Linuxfixture导入；这是条件collection诊断，非真Windows/macOS执行信用。

失败历史保留：初次apply_patch因误带diff加号定位行失败，未改变文件，随后纠正；首次RAM统一diff声明12/19而实际14/20触发AssertionError（未运行测试），行号186也在严格投影前改为183。下一RAM基线15/14有效FAIL/0E/skip/0.003s；投影15/13fixture ERROR/1.178s，因为自造temp ticket路径不属于真实`.icode_output`体系，修为原next_out_dir。这是fixture合同错误，不是正式RED或产品缺陷。metadata_update未被execution_trace收为tracked record，窗口正例改真实before_write；root独立temp诊断发现finish blocked缺必需evidence，本资产所有finish已明确固定引用。修正后的RAM15/0F/E/skip/4.893s；随后加入真实helper漂移负控，RAM15/0F/E/skip/4.863s；最后补真实closed-before-bind与trace bool-returncode负控，取得上面的最终16结果。未用任意sleep/假时钟或降低预期，任何正式失败仍须另保留。

两内置自审完成：Stage1 SPEC PASSED（完整要求映射，无未覆盖设计项）；Stage2 QUALITY FIXED并复核PASSED（统一diff、真实tempCP fixture条件、实际policy/CP坐标、helper门及关闭前bind负控均修正）。两源码、DESIGN批准摘要未变，正式新SOURCE/TEST实际仍不存在。本文结束即STOP，等待root PLAN fresh SPEC→不同QUALITY C0/I0/M0及GO，不自动handoff。

【架构级自检报告】（PLAN范围）

- 语法/编译：完整TEST/SOURCE/投影control已RAM compile通过，严格diff行数/上下文/字节核验通过；正式源码未落盘。
- 依赖/调用链：仅原run/trace到既有bind/borrow；回归模块已核实际存在。
- 逻辑/边界：raw类型、精确返回、回放、显示窗口、关闭、坏链、逐次fresh矩阵完整。
- 异常处理：固定普通拒绝，KI/SE原对象；owner责任维持原外部scope创建者。
- 关联模块：仅六路径，当前writer仅PLAN，旧scope/runner/core/vendor/CI只读。
- 兼容安全：旧step_start/ok/run参数形状保持，Linux fixture条件导入。
- 可运行性：最终16项RAM投影全部通过、模拟非Linux条件collection通过；正式TDD、完整门、发布均未执行，不报告100%。

---
**Execution Mode:** serial（仅计划；无自动执行）

## 正式执行证据（root后续维护，原writer诊断不替代）

PLAN批准855091d7通过fresh SPEC及不同QUALITY各C0/I0/M0后，TEST作者仅apply_patch批准21930B20868a62；作者3c03f5/root42e998正式原footer各 `Ran 16 tests in 0.003s`、`FAILED (failures=15)`，exit1，15有效callable断言/0E/skip，旧compat通过。缺新接口不授其后真实CP/资源矩阵已经执行。
不同SOURCE作者仅批准control单hunk与新module；作者ff6a26 `Ran 16 tests in 5.620s`、`OK`，限定八模块完整e6eb2b→ea7556→a0a1e6 `Ran 196 tests in 41.456s`、`OK (skipped=5)`，各exit0。root新16工具596833→49e54f原footer5.190s/OK/0F/E/skip；回归15439最终6e67dd原footer196/39.682s/OK(skipped=5)/exit0，首段11ea68截断，不冒称该首段完整日志。两方compileall-j1/diff通过，三个实际资产严格等批准字节，attachment/control其余/vendor未改。
fresh实际SOURCE SPEC758268新16/5.136s/OK与不同QUALITY aa6d98新16/5.270s/OK，各0F/E/skip/exit0及C0/I0/M0。作者两次提取器ASCII括号IndexError（a38d9f/df1b17）和SPEC第一次漏补fence末LF投影AssertionError均测试前诊断，纠正后exact通过、未改资产，不是产品失败或正式RED。
root唯一原fullguard74867于09:10:18 UTC开始，原日志 `/tmp/icode-cp-prepared-preflight.dOMmDP/typescript`；secrets/submodule已PASS，全量原结果待，不借deadline或S2a门。三个SOURCE/TEST冻结；Task3完整门/最终scanner及Task4精确index/发布尚未完成，checkbox不预授。
先次667c92a三个run38223965245/38223965156/38223965290已由root重新GET同SHA/push/main/attempt1全部终态与jobs，并保留全部50执行job完整decoded raw（3skip无执行日志）：CI41success/2Reviewer failure/3skip，provenance5/5、Pages2/2。双Python各3205/86skip，四Linux各84旧dispatch无新prepared信用，双Reviewer10035未知而非DENY，四provenance owner_untrusted/launch false且回收确认；具体job/footer/研究采纳与边界见live，外部失败未取消/重跑/降门。
随后同一root原guard09:20:00 UTC footer `COMMAND_EXIT_CODE="0"`，09:20:20 UTC工具215244取得第三门及全部三门PASS、session74867 exit0；09:20:45工具86f934核日志与三freeze不变。没有第二完整门，不猜原守护未输出的全量数量。Task3最终文档原scanner/单门、Task4精确index与发布仍待，原running文字是时序记录而非当前状态。
最终实际证据追加后三DOCS原scanner两轮bc44f8/c69351各raw0/exit0，无白名单；fresh secrets3b1b7c、submodule5dbc9b均PASS，diff/index/main基线4e9b39通过。故Task3确认完成；本次checkbox与此记录追加后仍重新两轮原scanner及fresh单门，不以记录存在推定未执行门。Task4精确index/提交/推送待实际执行，不预写未来发布SHA。
提交前原cached diff gate a992a7实际exit2，阻断PLAN差分围栏的两条空白context行尾空格；未commit/push。仅裁掉hunk外缘五条未修改context行，原批准183 old14/new20改展示185 old9/new15，不改任何加减内容或源码/TEST。原CONTROL_DIFF1183B4d5af54c及原严格批准历史保留上节；最终展示重新严格对原control投影，必须仍ffdaec53且SOURCE875635c9/TEST20868a62不变。文档等价修正需独立SPEC→不同QUALITY及两轮原scanner/单门/index重新核，不借此跳过whitespace gate或重新伪造RED。
