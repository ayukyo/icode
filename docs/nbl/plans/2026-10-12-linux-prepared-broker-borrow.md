# Linux prepared broker borrowing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development (recommended) or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 两公共observed入口借用真实S1b attachment，全部已返回的每命令资源收尾后归还；独立清理unknown或不透明构造失败使attachment永久失效，helper仍由原创建者关闭。

**Architecture:** 复用唯一observed core，显式区分旧None owning与新borrowing；独立cleanup_unknown及五创建点的construction_failed任一成立时只结束消费。借用不新开/关闭helper/session/lease；process与manager query通知不销毁资源、不供应确认信用，A不授未返回工厂内部清理。

**Tech Stack:** Python 3.11+、unittest、真实 Linux FD/socket、现有 WorkspaceManager/Git 夹具；无新依赖、服务、权限。

---

## 0. 状态、合同与范围

当前状态：Task1/2/2R/2A/2B 已实际实施，returned-receiver-I3 已修复；fresh SOURCE SPEC→不同QUALITY均零遗留，root新33与旧163通过，原完整 preflight 三门通过。下方原五路径执行资产保留为历史；Task2B 与 receiver-cleanup DESIGN 明确扩为八路径并取代最终发布命令，不得执行旧五路径 stage。最终文档/index核对及main发布收尾中；仍不授 S2 产品接线、S3 installed、CP、模型、ready、自动模式或 R2/R3 整体信用。

母合同：[单步准备 DESIGN](../specs/2026-10-12-linux-prepared-step-scope-design.md) §4、§6、§7；母文档 SHA256 `121a36a8f3ed376195668d61db063f94e0061e81d4f18b17c99d41c822132ec2` 不修改。当前 main `cfd14b3f86124232bc3f1ee4736961d37c200f72`，S1b SOURCE SHA256 `f165ba45cb07152079c0bb4a3ea1bb3059b7af28a23732cd5b70f74155547075`、TEST SHA256 `219af2af4906422a2e4957fb52d798e3f4b2b3a13f1be0916980e96da28e38e3` 不变。root 报告 S1b 原唯一 preflight session74699 exit0/footer03:39:49 UTC、精确四路径实际 commit/push；本 writer不把该信用授给未实施S1c。S1c 实施前再次核实际基线与两源码摘要。

本片待改 broker 基线 SHA256 `81ea0b0f9b7cf9122dc93bcfd96ca173a56b15aa89786a11d0b8974e39c4c108`。母文档、S1b module/test与broker本 writer只读，不声明整工作树clean；root 可并行追加自己的 live 记录。

三问：真实问题是broker仍每dispatch owning、首信号可能隐藏独立process cleanup unknown，且创建未返回时外层不能观察内部资源；复用唯一core、S1b attachment及已有cleanup选择器，A只保守结束消费；调用链限定两public→唯一observed core→创建调用及原process core，旧None行为/kwargs不变。

精确五路径（新增补充 DESIGN 已独立 SPEC→不同 QUALITY 零遗留，SHA256 `79badff6b9dd2a6029a8323c418a77508d3937889d7cfa6044de9e05db50fafc`）：

| 路径 | 职责 |
| --- | --- |
| `src/icode/execution_broker.py` | public 传参、显式借用、unknown 记录与归还、私有进程 cleanup 通知 |
| `tests/test_linux_prepared_broker.py` | 完整新软件契约测试；复用实际 S1b 夹具但不继承其测试类 |
| 本 PLAN | 逐项实际 TDD/独立审查/原完整预检与发布记录 |
| `docs/nbl/specs/2026-10-12-linux-prepared-broker-construction-design.md` | 已批准未返回资源的 A 边界及 B 债务，原字节不修改 |
| `docs/agent-landscape-live.md` | 最小研究取舍及验收信用更新，由 root 更新 |

禁止修改生命周期模块/旧测试/vendor/ToolContext/runner/registry/selector/ready、native helper、CI、工单状态机；禁止 fallback、捕获 TypeError 重试或更换 helper。用户 main-only 覆盖技能 worktree 默认；不得新分支/worktree。

### 接口细化与债务（必须独立审查，不偷偷扩母合同）

母 §4 拟新增 `prepared_step=None, workspace_session=None`。S1b 已落实 `view.borrow(..., attempt=...)`，因此两 public 与唯一 core 另需 keyword-only `prepared_attempt=None`，由可信 caller 本次栈的实际 attempt 显式提供。不能从 view `_attempt` 反取期望值、接受任意 token 自证或复制 CP 状态。本片测试使用明确标记的 software attempt 和可信只读校验函数，仅测试传递/生命周期，不授真实 CP；S2 必须核真实 runner `cp.step_start` 返回值及原 CP 的只读 observer。

私有 `_execute_policy_command` 新增 `on_cleanup_unknown=None`。必要性：旧 process finally 在首 KI/SE 与 selector/stop/pipe unknown 同时发生时仍传播首信号，外层不能从异常推断 unknown。新通知只记录事实；在独立资源全部尽力收尾后、borrow 仍 active 时 broker 标记 sticky faulted。普通 body 异常本身不算 cleanup unknown。通知自身异常也不能跳过剩余独立清理、覆盖首信号。此为兑现母 §6 的最小内部细化，不新增认证/隔离能力；独立审查若认为需要 DESIGN 补充，先返审而不实施。

旧 None public 不向 core 增加三个 borrowing keyword；旧 core 不向 process core 传新通知 keyword。wrapper 始终只收到既有 `helper_object`，不收到 session/attempt/view。新 scope 配空/错 session/attempt、raw owner、其它 sandbox 或 legacy helper mode 均固定拒绝，不 factory，不建 channel，不退旧路径。

补充DESIGN的A：独立`construction_failed`只在有效borrow内五个实际创建调用未正常返回时记录；不是cleanup unknown/泄漏证明。归还前两事实任一成立即sticky faulted，但ordinary body清理错误优先仅由cleanup_unknown触发；成功构造后的普通wrapper/body失败仍可继续借用。broker保持实际收到的首KI/SE对象，不追回工厂内部覆盖的不可见信号。工厂内部FD残留、析构/重复close与内部signal选择器归B独立债务，必须在R2/R3整体验收前闭合；A不回收未返回资源、不授权下一命令补救、不授内部清理。

## 1. 研究输入与不授信用

复用 root 当前 `docs/agent-landscape-live.md` 2026-10-12 03:31:29–03:32:12 UTC 独立只读观察：Codex `27065a91ccbf5ba8532844be3777fcf83b77820d`、OpenHands SDK `3934349da2db0433238621542173a00a8af7439c`。本 writer 未重取上游，不称最新 HEAD 或完整二十项刷新。

采纳：borrow 前核实际引用，独立清理期间仍持 borrow，unknown 在归还前 faulted、owner active、creator 最后唯一关闭。Codex `process.rs` 228–253 的 terminate 与 terminate_confirmed 分账提醒区分动作和确认；652–655 的 Drop 普通异步 terminate 且忽略结果不能供应确认信用。暂缓：跨命令缓存/并行执行/自动准入；不适配：callback/token/类型自证、Drop 当确认、上游行为替代 ICODE 首信号或 CP 实证。已核 Apache-2.0/MIT，仅借鉴机制，不复制源码，不增加依赖/权限。

## 2. Task 1：完整测试先行及有效 public 接线 RED

**状态**
- [ ] 任务完成

**Dependencies:** None（开始实施前 S1b 必须发布且上述字节固定）
**Parallelizable:** No（唯一新测试 writer；root 复现有效 RED 前不可实施 SOURCE）

- [ ] **Step 1: 仅新增 `tests/test_linux_prepared_broker.py`，使用以下完整代码。**

~~~python
"""S1c real-FD lifecycle software tests; no payload/CP/installed credit."""
from __future__ import annotations
from contextlib import ExitStack
from dataclasses import replace
import errno
import inspect
import os
import socket
import stat
import sys
import time
import unittest
from unittest.mock import patch
from tests import test_linux_prepared_step as fixture
from tests import test_linux_helper_dispatch as dispatch
from icode import execution_broker as broker
from icode import linux_helper_object as factory
from icode import linux_prepared_step as prepared
from icode import linux_seccomp_notify as seccomp
from icode import linux_task_scope as task_module


@unittest.skipUnless(sys.platform.startswith('linux') and callable(getattr(os, 'pread', None)),
    'Linux real-resource software fixture; skip is not acceptance')
class PreparedBrokerTests(unittest.TestCase):
    setUp = fixture.PreparedTests.setUp
    write_image = fixture.PreparedTests.write_image
    precheck_fixture = fixture.PreparedTests.precheck_fixture
    cleanup_scopes = fixture.PreparedTests.cleanup_scopes
    prepare = fixture.PreparedTests.prepare
    attach = fixture.PreparedTests.attach
    bind = fixture.PreparedTests.bind
    borrow = fixture.PreparedTests.borrow

    def entry(self, resource):
        return (broker.execute_linux_resource_observed_command if resource
                else broker.execute_linux_violation_observed_command)

    def call(self, resource, view, **changes):
        entry = self.entry(resource)
        arguments = dict(cwd=self.session.workspace_root, sandbox=self.sandbox,
            policy=self.policy, timeout=1, command_wrapper=self.wrapper,
            prepared_step=view, workspace_session=self.session,
            prepared_attempt='software-attempt')
        arguments.update(changes)
        # Baseline public exists. Missing new signature is exercised by calling
        # its actual old API, then asserting the requested forwarding below.
        # No missing-module/TypeError is counted as an effective RED.
        supported = inspect.signature(entry).parameters
        for name in ('prepared_step', 'workspace_session', 'prepared_attempt'):
            if name not in supported:
                arguments.pop(name)
        return entry(['/usr/bin/true'], **arguments)

    def wrapper(self, argv, sender, *resources, helper_object):
        self.owners.append(helper_object)
        binding = dict(policy=self.policy, control_socket=sender,
            helper_object=helper_object, workspace_fd=self.session.workspace_fd,
            workspace_identity=self.session.workspace_fd_identity)
        if resources:
            return self.sandbox.wrap_policy_with_resource_receipt(argv,
                resource_socket=resources[0], unit=resources[1], **binding)
        return self.sandbox.wrap_policy_with_violation_receipt(argv, **binding)

    def target_forwarding(self, resource):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        self.assertEqual(scope._consume_state, 'attached_bound')
        self.assertEqual(scope._owner_state, 'active')
        self.precheck_fixture()
        with patch.object(broker, '_execute_linux_observed_command',
                return_value=object()) as core:
            self.call(resource, view)
        self.assertEqual(core.call_count, 1)
        actual = core.call_args.kwargs
        self.assertIs(actual.get('prepared_step'), view)
        self.assertIs(actual.get('workspace_session'), self.session)
        self.assertEqual(actual.get('prepared_attempt'), 'software-attempt')

    def test_violation_public_forwarding_target(self):
        self.target_forwarding(False)

    def test_resource_public_forwarding_target(self):
        self.target_forwarding(True)

    def exercise(self, resource, view, *, body=None, fault=None, result=None,
            changes=None, notification=False, mutation=None, manager_stage=None,
            manager_answer=None, manager_body=None, manager_notification=False,
            construction=None, construction_body=None):
        self.owners, channels, events = [], [], []
        self.manager_keywords = []
        task, receiver = dispatch.Scope(), dispatch.Resource()
        monitor = dispatch.Monitor(None)
        def observe(label):
            self.assertTrue(view._scope._inflight)
            self.assertEqual(view._scope._owner_state, 'active')
            events.append(label)
        def channel():
            observe('channel')
            kind = 'resource_channel' if resource and not channels else 'seccomp_channel'
            if construction == kind:
                raise construction_body
            host, sender = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
            if fault == 'endpoint_close' and not channels:
                class UnknownHost(socket.socket):
                    def __init__(self, *args, **kwargs):
                        super().__init__(*args, **kwargs)
                        self.original_fd = self.fileno()
                        self.attempts = 0
                    def close(self):
                        observe('endpoint_close')
                        self.attempts += 1
                        raise OSError('private endpoint detail')
                host = UnknownHost(fileno=host.detach())
            pair = host, sender
            channels.extend(pair)
            return pair
        def monitored(host):
            if construction == 'monitor':
                observe('monitor_constructor')
                raise construction_body
            monitor.host = host
            return monitor
        def received(*args, **kwargs):
            if construction == 'receiver':
                observe('receiver_constructor')
                raise construction_body
            return receiver
        for label, target, name in (('monitor_close', monitor, 'close'),
                ('resource_wait', receiver, 'wait'), ('resource_close', receiver, 'close'),
                ('scope_collected', task, 'collected'), ('scope_close', task, 'close')):
            original = getattr(target, name)
            def operation(*args, _label=label, _original=original, **kwargs):
                observe(_label)
                answer = _original(*args, **kwargs)
                if fault == _label:
                    raise OSError('private cleanup detail')
                if fault == _label + '_false':
                    return False
                return answer
            setattr(target, name, operation)
        if fault == 'scope_state':
            task.cleanup_state = 'unknown'
        if fault == 'resource_terminal':
            receiver.receipt = lambda: dict(channel_status='complete',
                payload_started=None, terminal='cleanup_failed')
        def run(argv, **kwargs):
            if argv == ['/usr/bin/systemctl', '--user', 'show']:
                observe('manager_process')
                self.manager_keywords.append(dict(kwargs))
                hook = kwargs.get('on_cleanup_unknown')
                if manager_notification and callable(hook):
                    hook()
                if manager_body is not None:
                    raise manager_body
                return manager_answer or broker.ExecutionResult(0, '', 0,
                    None, False, True, None, raw_output=b'fixture-manager')
            observe('launch')
            kwargs['before_spawn']()
            if notification:
                kwargs['on_cleanup_unknown']()
            if body is not None:
                raise body
            return result or broker.ExecutionResult(0, '', 0, None, False, True, None)
        def create_scope(*, limit, query):
            observe('scope_constructor')
            if construction == 'scope':
                raise construction_body
            def request():
                return query(['/usr/bin/systemctl', '--user', 'show'],
                    dict(task.environment), time.monotonic() + 2)
            if manager_stage == 'constructor':
                request()  # task_scope assignment has not completed yet.
            elif manager_stage == 'wrap':
                original_wrap = task.wrap
                def queried_wrap(helper):
                    request()
                    return original_wrap(helper)
                task.wrap = queried_wrap
            return task
        original_wrapper = self.wrapper
        def wrapped_wrapper(*args, **kwargs):
            self.assertEqual(set(kwargs), {'helper_object'})
            command = original_wrapper(*args, **kwargs)
            if mutation is not None:
                mutation(command)
            return command
        try:
            with ExitStack() as stack:
                stack.enter_context(patch.object(self, 'wrapper', side_effect=wrapped_wrapper))
                opening = stack.enter_context(patch.object(factory,
                    'open_linux_helper_object', side_effect=AssertionError('borrow must not factory')))
                closing = stack.enter_context(patch.object(view._scope._owner,
                    'close', side_effect=AssertionError('broker must not close helper')))
                stack.enter_context(patch('icode.linux_seccomp_notify.create_seccomp_listener_handoff_channel', side_effect=channel))
                stack.enter_context(patch('icode.linux_task_resource.create_task_resource_channel', side_effect=channel))
                stack.enter_context(patch('icode.linux_seccomp_notify.LinuxSeccompViolationMonitor', side_effect=monitored))
                stack.enter_context(patch('icode.linux_task_scope.LinuxTaskScope', side_effect=create_scope))
                stack.enter_context(patch('icode.linux_task_resource.LinuxTaskResourceReceiver', side_effect=received))
                stack.enter_context(patch.object(broker, '_execute_policy_command', side_effect=run))
                answer, error = dispatch.capture(lambda: self.call(resource, view, **(changes or {})))
                opening.assert_not_called()
                closing.assert_not_called()
            self.assertFalse(view._scope._inflight)
            self.assertEqual(view._scope._owner_state, 'active')
            os.fstat(view._scope._owner.fileno())
            os.fstat(self.session.workspace_fd)
            self.session.lease._validate_active()
            self.assertTrue(all(endpoint.fileno() == -1 for endpoint in channels))
            for endpoint in channels:
                if hasattr(endpoint, 'attempts'):
                    self.assertEqual(endpoint.attempts, 1)
            return answer, error, events
        finally:
            # Test-owned final fixture release is separate from broker credit;
            # this helper retains the original known-live FD for injected faults.
            dispatch.cleanup_test_channels(channels)

    def test_sequential_both_entries_same_owner_and_creator_closes_last(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        for resource in (False, True, False, True):
            answer, error, events = self.exercise(resource, view)
            self.assertIsNone(error)
            self.assertIsNone(answer.error)
            self.assertEqual(self.owners, [scope._owner])
            self.assertIn('monitor_close', events)
            self.assertEqual(scope._consume_state, 'attached_bound')
        descriptor = scope._owner.fileno()
        view.finish()
        scope.close()
        with self.assertRaises(OSError) as caught:
            os.fstat(descriptor)
        self.assertEqual(caught.exception.errno, errno.EBADF)
        os.fstat(self.session.workspace_fd)
        self.session.lease._validate_active()

    def test_reject_caller_facts_before_channels_and_no_fallback(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        wrong = ({'workspace_session': None}, {'workspace_session': replace(self.session)},
            {'policy': replace(self.policy)}, {'prepared_attempt': None},
            {'prepared_attempt': 'other-attempt'}, {'prepared_step': scope},
            {'prepared_step': object()}, {'sandbox': object()})
        for resource in (False, True):
            for change in wrong:
                with self.subTest(resource=resource, names=tuple(change)):
                    answer, error, events = self.exercise(resource, view, changes=change)
                    self.assertIsNone(error)
                    self.assertEqual(answer.error, 'isolation_unavailable')
                    self.assertIs(answer.payload_started, False)
                    self.assertEqual(events, [])
        self.assertEqual(scope._consume_state, 'attached_bound')

    def test_pending_spent_and_active_reentry_reject_before_channels(self):
        scope = self.prepare()
        view = self.attach(scope)
        answer, error, events = self.exercise(False, view)
        self.assertIsNone(error)
        self.assertEqual(answer.error, 'isolation_unavailable')
        self.assertEqual(events, [])
        self.bind(view)
        with self.borrow(view):
            with patch('icode.linux_seccomp_notify.create_seccomp_listener_handoff_channel') as channels:
                answer = self.call(False, view)
            channels.assert_not_called()
            self.assertEqual(answer.error, 'isolation_unavailable')
        view.finish()
        answer, error, events = self.exercise(True, view)
        self.assertIsNone(error)
        self.assertEqual(answer.error, 'isolation_unavailable')
        self.assertEqual(events, [])

    def test_body_errors_and_signals_without_unknown_remain_borrowable(self):
        for body in (RuntimeError('private body'), KeyboardInterrupt(), SystemExit(19)):
            scope = self.prepare()
            view = self.bind(self.attach(scope))
            answer, error, events = self.exercise(True, view, body=body)
            self.assertIsNone(answer)
            self.assertIs(error, body)
            self.assertEqual(scope._consume_state, 'attached_bound')
            self.assertIn('scope_close', events)
            with self.borrow(view) as owner:
                self.assertIs(owner, scope._owner)

    def test_borrowed_wrapper_binding_rejects_without_owner_replacement(self):
        def swapped(command):
            command.helper_object = object()
        def duplicated(command):
            command.pass_fds += command.pass_fds
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        for resource in (False, True):
            for mutation in (swapped, duplicated):
                with self.subTest(resource=resource, mutation=mutation.__name__):
                    answer, error, events = self.exercise(resource, view, mutation=mutation)
                    self.assertIsNone(error)
                    self.assertEqual(answer.error, 'isolation_unavailable')
                    self.assertIs(answer.payload_started, False)
                    self.assertNotIn('launch', events)
                    self.assertEqual(scope._consume_state, 'attached_bound')
        with self.borrow(view) as owner:
            self.assertIs(owner, scope._owner)

    def test_cleanup_unknown_matrix_blocks_next_command_but_keeps_owner(self):
        faults = ('monitor_close', 'monitor_close_false', 'resource_wait',
            'resource_close', 'resource_close_false', 'scope_collected',
            'scope_collected_false', 'scope_close', 'scope_state', 'resource_terminal',
            'endpoint_close')
        for fault in faults:
            with self.subTest(fault=fault):
                scope = self.prepare()
                view = self.bind(self.attach(scope))
                answer, error, events = self.exercise(True, view, fault=fault)
                self.assertEqual(scope._consume_state, 'faulted')
                self.assertIn('scope_close', events)
                self.assertIn('monitor_close', events)
                with self.assertRaises(prepared.LinuxPreparedStepError):
                    with self.borrow(view):
                        pass
                second, second_error, second_events = self.exercise(False, view)
                self.assertIsNone(second_error)
                self.assertEqual(second.error, 'isolation_unavailable')
                self.assertEqual(second_events, [])
                view.finish()
                self.assertEqual(scope._consume_state, 'faulted')
                scope.close()
                self.assertEqual(scope._owner_state, 'closed')

    def test_first_signal_and_unknown_keep_original_and_all_cleanup(self):
        for body in (KeyboardInterrupt(), SystemExit(71)):
            scope = self.prepare()
            view = self.bind(self.attach(scope))
            answer, error, events = self.exercise(True, view,
                body=body, fault='resource_close')
            self.assertIsNone(answer)
            self.assertIs(error, body)
            self.assertEqual(scope._consume_state, 'faulted')
            self.assertIn('monitor_close', events)
            self.assertIn('scope_close', events)

    def test_ordinary_body_cannot_hide_cleanup_unknown(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        body = RuntimeError('private body')
        for fault in ('scope_close', 'scope_collected', 'resource_close', 'endpoint_close'):
            scope = self.prepare()
            view = self.bind(self.attach(scope))
            answer, error, events = self.exercise(True, view, body=body, fault=fault)
            self.assertIsNone(answer)
            self.assertIsInstance(error, factory.LinuxHelperObjectError)
            self.assertIsNot(error, body)
            self.assertEqual(scope._consume_state, 'faulted')
            self.assertNotIn('private', str(error))

    def test_process_unknown_result_and_signal_notification_fault_attachment(self):
        for body in (None, KeyboardInterrupt(), SystemExit(29)):
            scope = self.prepare()
            view = self.bind(self.attach(scope))
            answer, error, events = self.exercise(False, view, body=body,
                notification=True, result=broker.ExecutionResult(0, '', 0,
                    'cleanup_failed', False, False, errno.EBUSY))
            self.assertEqual(scope._consume_state, 'faulted')
            if body is not None:
                self.assertIs(error, body)
            else:
                self.assertIsNone(error)
                self.assertIs(answer.cleanup_ok, False)

    def test_manager_constructor_unknown_target(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        self.precheck_fixture()
        answer, error, events = self.exercise(True, view, manager_stage='constructor',
            manager_answer=broker.ExecutionResult(None, '', 0,
                'cleanup_failed', False, False, errno.EBUSY))
        self.assertIsNone(error)
        self.assertEqual(answer.error, 'isolation_unavailable')
        self.assertEqual(events, ['scope_constructor', 'manager_process'])
        self.assertEqual(len(self.manager_keywords), 1)
        self.assertEqual(scope._owner_state, 'active')
        self.assertFalse(scope._inflight)
        # This is the effective target on the reachable Task2 intermediate.
        self.assertEqual(scope._consume_state, 'faulted')

    def test_manager_later_unknown_blocks_next_command(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        answer, error, events = self.exercise(True, view, manager_stage='wrap',
            manager_answer=broker.ExecutionResult(None, '', 0,
                'cleanup_failed', False, False, errno.EBUSY))
        self.assertEqual(scope._consume_state, 'faulted')
        self.assertIn('scope_close', events)
        self.assertEqual(len(self.manager_keywords), 1)
        self.assertNotIn('launch', events)
        with self.assertRaises(prepared.LinuxPreparedStepError):
            with self.borrow(view):
                pass

    def test_manager_ordinary_body_with_unknown_notice_cannot_hide_cleanup(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        answer, error, events = self.exercise(True, view, manager_stage='constructor',
            manager_body=Exception('private manager body'), manager_notification=True)
        self.assertIsNone(answer)
        self.assertIsInstance(error, factory.LinuxHelperObjectError)
        self.assertEqual(scope._consume_state, 'faulted')
        self.assertNotIn('private', str(error))

    def test_manager_signal_with_unknown_notice_keeps_original_and_faulted(self):
        for stage in ('constructor', 'wrap'):
            for first in (KeyboardInterrupt(), SystemExit(61)):
                scope = self.prepare()
                view = self.bind(self.attach(scope))
                answer, error, events = self.exercise(True, view,
                    manager_stage=stage, manager_body=first, manager_notification=True)
                self.assertIsNone(answer)
                self.assertIs(error, first)
                self.assertEqual(len(self.manager_keywords), 1)
                self.assertEqual(scope._consume_state, 'faulted')
                if stage == 'wrap':
                    self.assertIn('scope_close', events)

    def test_construction_manager_ordinary_failure_consumes_without_cleanup_claim(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        answer, error, events = self.exercise(True, view,
            manager_stage='constructor', manager_body=RuntimeError('private manager body'))
        self.assertIsNone(error)
        self.assertEqual(answer.error, 'isolation_unavailable')
        self.assertEqual(scope._consume_state, 'faulted')
        self.assertEqual(events, ['scope_constructor', 'manager_process'])

    def test_construction_seccomp_real_unreturned_socket_target(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        self.precheck_fixture()
        held, attempts = [], []
        actual_pair = seccomp.socket.socketpair
        actual_set_inheritable = seccomp.os.set_inheritable
        class UnknownHost(seccomp.socket.socket):
            def close(self):
                attempts.append(self.fileno())
                raise OSError('private factory close')
        def pair(*args, **kwargs):
            host, sender = actual_pair(*args, **kwargs)
            host = UnknownHost(fileno=host.detach())
            held.extend((host, sender))
            return host, sender
        def inheritable(descriptor, value):
            if held and descriptor == held[0].fileno():
                raise OSError('private factory initialization')
            return actual_set_inheritable(descriptor, value)
        try:
            with patch.object(seccomp.socket, 'socketpair', side_effect=pair), \
                    patch.object(seccomp.os, 'set_inheritable', side_effect=inheritable), \
                    patch.object(factory, 'open_linux_helper_object') as opening, \
                    patch.object(scope._owner, 'close') as closing:
                answer, error = dispatch.capture(lambda: self.call(False, view))
            opening.assert_not_called()
            closing.assert_not_called()
            self.assertIsNone(error)
            self.assertEqual(answer.error, 'isolation_unavailable')
            self.assertEqual(len(held), 2)
            descriptor = held[0].fileno()
            self.assertEqual(attempts, [descriptor])
            self.assertTrue(stat.S_ISSOCK(os.fstat(descriptor).st_mode))
            self.assertFalse(scope._inflight)
            self.assertEqual(scope._owner_state, 'active')
            os.fstat(scope._owner.fileno())
            os.fstat(self.session.workspace_fd)
            self.assertEqual(scope._consume_state, 'faulted')
            with self.assertRaises(prepared.LinuxPreparedStepError):
                with self.borrow(view):
                    pass
        finally:
            # Test hygiene only; A does not recover this unreturned socket.
            for endpoint in held:
                seccomp.socket.socket.close(endpoint)

    def test_construction_scope_real_unreturned_tool_fd_target(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        self.precheck_fixture()
        held = []
        actual_close = task_module.os.close
        def closing(descriptor):
            if os.readlink('/proc/self/fd/' + str(descriptor)) == '/usr/bin/systemd-run':
                held.append(descriptor)
                raise OSError('private trusted-tool close')
            return actual_close(descriptor)
        try:
            with patch.object(task_module.os, 'close', side_effect=closing), \
                    patch.object(factory, 'open_linux_helper_object') as opening, \
                    patch.object(scope._owner, 'close') as helper_close:
                answer, error = dispatch.capture(lambda: self.call(True, view))
            opening.assert_not_called()
            helper_close.assert_not_called()
            self.assertIsNone(error)
            self.assertEqual(answer.error, 'isolation_unavailable')
            self.assertEqual(len(held), 1)
            self.assertTrue(stat.S_ISREG(os.fstat(held[0]).st_mode))
            self.assertFalse(scope._inflight)
            self.assertEqual(scope._owner_state, 'active')
            os.fstat(scope._owner.fileno())
            self.session.lease._validate_active()
            self.assertEqual(scope._consume_state, 'faulted')
            with self.assertRaises(prepared.LinuxPreparedStepError):
                with self.borrow(view):
                    pass
        finally:
            # Explicit saved test-owned FD release; not broker cleanup credit.
            for descriptor in held:
                actual_close(descriptor)

    def test_construction_five_failures_consume_and_keep_received_signals(self):
        for construction in ('scope', 'resource_channel', 'seccomp_channel', 'receiver', 'monitor'):
            for body in (RuntimeError('private constructor'), KeyboardInterrupt(), SystemExit(67)):
                with self.subTest(construction=construction, kind=type(body).__name__):
                    scope = self.prepare()
                    view = self.bind(self.attach(scope))
                    answer, error, events = self.exercise(True, view,
                        construction=construction, construction_body=body)
                    self.assertEqual(scope._consume_state, 'faulted')
                    if isinstance(body, Exception):
                        self.assertIsNone(error)
                        self.assertEqual(answer.error, 'isolation_unavailable')
                    else:
                        self.assertIsNone(answer)
                        self.assertIs(error, body)
                    if construction != 'scope':
                        self.assertIn('scope_close', events)
                    with self.assertRaises(prepared.LinuxPreparedStepError):
                        with self.borrow(view):
                            pass

    def test_construction_real_factory_received_signal_keeps_identity(self):
        for first in (KeyboardInterrupt(), SystemExit(71)):
            scope = self.prepare()
            view = self.bind(self.attach(scope))
            actual_pair = seccomp.socket.socketpair
            actual_set = seccomp.os.set_inheritable
            held = []
            def pair(*args, **kwargs):
                endpoints = actual_pair(*args, **kwargs)
                held.extend(endpoints)
                return endpoints
            def inheritable(descriptor, value):
                if held and descriptor == held[0].fileno():
                    raise first
                return actual_set(descriptor, value)
            try:
                with patch.object(seccomp.socket, 'socketpair', side_effect=pair), \
                        patch.object(seccomp.os, 'set_inheritable', side_effect=inheritable):
                    answer, error = dispatch.capture(lambda: self.call(False, view))
                self.assertIsNone(answer)
                self.assertIs(error, first)
                self.assertTrue(all(endpoint.fileno() == -1 for endpoint in held))
                self.assertEqual(scope._consume_state, 'faulted')
                self.assertFalse(scope._inflight)
            finally:
                for endpoint in held:
                    seccomp.socket.socket.close(endpoint)

    def test_construction_old_none_keeps_original_factory_failure_contract(self):
        for first in (RuntimeError('old ctor'), KeyboardInterrupt(), SystemExit(73)):
            with patch.object(task_module, 'LinuxTaskScope', side_effect=first), \
                    patch('icode.linux_task_resource.create_task_resource_channel') as channels:
                answer, error = dispatch.capture(lambda: broker.execute_linux_resource_observed_command(
                    ['/usr/bin/true'], cwd=self.session.workspace_root, sandbox=self.sandbox,
                    policy=self.policy, timeout=1, command_wrapper=self.wrapper))
            channels.assert_not_called()
            if isinstance(first, Exception):
                self.assertIsNone(error)
                self.assertEqual(answer.error, 'isolation_unavailable')
            else:
                self.assertIsNone(answer)
                self.assertIs(error, first)
            os.fstat(self.session.workspace_fd)
            self.session.lease._validate_active()

    def test_old_none_manager_query_does_not_add_notification_keyword(self):
        held, keywords = [], []
        actual_factory = factory.open_linux_helper_object
        def opening(*args):
            owner = actual_factory(*args)
            held.append((owner, owner.fileno()))
            return owner
        def run(argv, **kwargs):
            keywords.append(dict(kwargs))
            return broker.ExecutionResult(0, '', 0, None, False, True, None,
                raw_output=b'fixture-manager')
        def create_scope(*, limit, query):
            query(['/usr/bin/systemctl', '--user', 'show'], {}, time.monotonic() + 2)
            raise RuntimeError('stop fixture before channels')
        with patch.object(factory, 'open_linux_helper_object', side_effect=opening), \
                patch('icode.linux_task_scope.LinuxTaskScope', side_effect=create_scope), \
                patch.object(broker, '_execute_policy_command', side_effect=run), \
                patch('icode.linux_task_resource.create_task_resource_channel') as channels:
            answer = broker.execute_linux_resource_observed_command(['/usr/bin/true'],
                cwd=self.session.workspace_root, sandbox=self.sandbox,
                policy=self.policy, timeout=1, command_wrapper=self.wrapper)
        self.assertEqual(answer.error, 'isolation_unavailable')
        channels.assert_not_called()
        self.assertEqual(len(keywords), 1)
        self.assertNotIn('on_cleanup_unknown', keywords[0])
        self.assertEqual(len(held), 1)
        self.assertEqual(held[0][0]._state, 'closed')
        with self.assertRaises(OSError) as caught:
            os.fstat(held[0][1])
        self.assertEqual(caught.exception.errno, errno.EBADF)
        os.fstat(self.session.workspace_fd)

    def test_process_core_unknown_notifies_and_notification_fault_keeps_cleanup(self):
        actual_core = broker._execute_policy_command
        for body in (None, KeyboardInterrupt(), SystemExit(37)):
            for notice_error in (None, RuntimeError('private notification'),
                    KeyboardInterrupt(), SystemExit(41)):
                scope = self.prepare()
                view = self.bind(self.attach(scope))
                calls, processes = [], []
                actual_popen, actual_stop = broker.subprocess.Popen, broker._stop_group
                def popen(*args, **kwargs):
                    process = actual_popen(*args, **kwargs)
                    processes.append(process)
                    return process
                def stop(process):
                    actual_stop(process)
                    return False, errno.EBUSY
                def notice():
                    self.assertTrue(scope._inflight)
                    calls.append('unknown')
                    view._mark_faulted()
                    if notice_error is not None:
                        raise notice_error
                def spawned(process, deadline):
                    if body is not None:
                        raise body
                with self.borrow(view), patch.object(broker.subprocess, 'Popen', side_effect=popen), \
                        patch.object(broker, '_stop_group', side_effect=stop):
                    answer, error = dispatch.capture(lambda: actual_core(
                        [sys.executable, '-c', 'pass'], cwd=self.session.workspace_root,
                        policy=self.policy, timeout=1, on_spawn=spawned,
                        on_cleanup_unknown=notice))
                self.assertEqual(calls, ['unknown'])
                self.assertEqual(scope._consume_state, 'faulted')
                self.assertEqual(len(processes), 1)
                self.assertIsNotNone(processes[0].poll())
                self.assertTrue(processes[0].stdout.closed)
                if body is not None:
                    self.assertIs(error, body)
                elif notice_error is not None:
                    self.assertIs(error, notice_error)
                else:
                    self.assertIsNone(error)
                    self.assertIs(answer.cleanup_ok, False)

    def test_process_first_cleanup_signal_precedes_notification_signal(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        first, second = KeyboardInterrupt(), SystemExit(53)
        actual_stop, actual_popen = broker._stop_group, broker.subprocess.Popen
        processes = []
        def popen(*args, **kwargs):
            process = actual_popen(*args, **kwargs)
            processes.append(process)
            return process
        def stop(process):
            actual_stop(process)
            raise first
        def notice():
            self.assertTrue(scope._inflight)
            view._mark_faulted()
            raise second
        with self.borrow(view), patch.object(broker.subprocess, 'Popen', side_effect=popen), \
                patch.object(broker, '_stop_group', side_effect=stop):
            answer, error = dispatch.capture(lambda: broker._execute_policy_command(
                [sys.executable, '-c', 'pass'], cwd=self.session.workspace_root,
                policy=self.policy, timeout=1, on_cleanup_unknown=notice))
        self.assertIsNone(answer)
        self.assertIs(error, first)
        self.assertEqual(scope._consume_state, 'faulted')
        self.assertIsNotNone(processes[0].poll())
        self.assertTrue(processes[0].stdout.closed)

    def test_process_selector_stop_and_pipe_unknown_each_notify(self):
        for stage in ('selector_close', 'stop_raise', 'pipe_close'):
            with self.subTest(stage=stage):
                scope = self.prepare()
                view = self.bind(self.attach(scope))
                fault = RuntimeError('private owned cleanup')
                calls, processes = [], []
                selector = broker.selectors.DefaultSelector()
                actual_selector_close = selector.close
                actual_stop, actual_popen = broker._stop_group, broker.subprocess.Popen
                class FaultPipe:
                    def __init__(self, stream):
                        self.stream = stream
                    def __getattr__(self, name):
                        return getattr(self.stream, name)
                    def close(self):
                        self.stream.close()
                        raise fault
                def popen(*args, **kwargs):
                    process = actual_popen(*args, **kwargs)
                    if stage == 'pipe_close':
                        process.stdout = FaultPipe(process.stdout)
                    processes.append(process)
                    return process
                def stop(process):
                    answer = actual_stop(process)
                    if stage == 'stop_raise':
                        raise fault
                    return answer
                def selector_close():
                    actual_selector_close()
                    if stage == 'selector_close':
                        raise fault
                def notice():
                    self.assertTrue(scope._inflight)
                    calls.append(stage)
                    view._mark_faulted()
                try:
                    with self.borrow(view), patch.object(broker.subprocess, 'Popen', side_effect=popen), \
                            patch.object(broker, '_stop_group', side_effect=stop), \
                            patch.object(broker.selectors, 'DefaultSelector', return_value=selector), \
                            patch.object(selector, 'close', side_effect=selector_close):
                        answer, error = dispatch.capture(lambda: broker._execute_policy_command(
                            [sys.executable, '-c', 'pass'], cwd=self.session.workspace_root,
                            policy=self.policy, timeout=1, on_cleanup_unknown=notice))
                    self.assertIsNone(answer)
                    self.assertIs(error, fault)
                    self.assertEqual(calls, [stage])
                    self.assertEqual(scope._consume_state, 'faulted')
                    self.assertIsNotNone(processes[0].returncode)
                    self.assertTrue(processes[0].stdout.closed)
                finally:
                    actual_selector_close()
                    for process in processes:
                        actual_stop(process)
                        stream = getattr(process.stdout, 'stream', process.stdout)
                        stream.close()

    def test_old_none_public_core_keyword_shape_remains_unchanged(self):
        for resource in (False, True):
            entry = self.entry(resource)
            with patch.object(broker, '_execute_linux_observed_command', return_value=object()) as core:
                entry(['/usr/bin/true'], cwd=self.session.workspace_root,
                    sandbox=self.sandbox, policy=self.policy, timeout=1,
                    command_wrapper=self.wrapper)
            for name in ('prepared_step', 'workspace_session', 'prepared_attempt'):
                self.assertNotIn(name, core.call_args.kwargs)
~~~

- [ ] **Step 2: fresh Task1 writer 仅跑两目标 RED，禁止 SOURCE 改动或骨架。**

~~~sh
.venv/bin/python -B -m unittest tests.test_linux_prepared_broker.PreparedBrokerTests.test_violation_public_forwarding_target tests.test_linux_prepared_broker.PreparedBrokerTests.test_resource_public_forwarding_target -v
~~~

预期：2 tests / 2 assertion failures，均命中 `actual.get('prepared_step') is view`，0 errors/skip，exit 1。真实工单目录、lease、session FD、policy、S0 static/source 与 S1b bound owner 在断言前已成立；既有 public 已调用既有 core，只是未接线。ImportError、TypeError、夹具错误、权限错误均无效，不授 RED。Task1 报告精确测试 SHA、实际原输出并停止，root 全读新测试并独立复现后才能交给不同 Task2 writer。

## 3. Task 2：唯一 core 的最小 GREEN

**状态**
- [ ] 任务完成

**Dependencies:** Task 1（root 两有效 assertion RED）
**Parallelizable:** No（不同 fresh SOURCE writer；同文件无并行 writer）

- [ ] **Step 1: 仅对同一 SOURCE 文件应用以下完整最小差分，不复制 broker 全文、不重构。**

以下是 Task2 唯一中间生产代码资产，保持原17-hunk投影以让public borrowing可达，故意尚不包含已实证缺失的manager query通知；不是最终GREEN资产。writer先核实际基线摘要和各上下文，再使用apply_patch，不得重复插入或先实现Task2R再删门。Task2首次完成后须运行新manager constructor目标取得有效assertion RED并停止；root独立复现后才由不同fresh Task2R writer补最小query修复。所有Task1新tests均已先写，本片计划编写不落SOURCE。

~~~diff
--- a/src/icode/execution_broker.py
+++ b/src/icode/execution_broker.py
@@ -176,11 +176,15 @@
     argv: list[str], *, cwd: Path, sandbox: object, policy: SandboxPolicy,
     timeout: int | float, output_limit_bytes: int | None = None,
     command_wrapper: _LinuxViolationCommandWrapper,
+    prepared_step=None, workspace_session=None, prepared_attempt=None,
 ) -> ExecutionResult:
+    borrowing_keywords = (dict(prepared_step=prepared_step,
+        workspace_session=workspace_session, prepared_attempt=prepared_attempt)
+        if prepared_step is not None else {})
     return _execute_linux_observed_command(
         argv, cwd=cwd, sandbox=sandbox, policy=policy, timeout=timeout,
         output_limit_bytes=output_limit_bytes, command_wrapper=command_wrapper,
-        resource_mode=False, helper_object_mode=True,
+        resource_mode=False, helper_object_mode=True, **borrowing_keywords,
     )
-
+
-
+
@@ -189,13 +193,17 @@
     timeout: int | float, output_limit_bytes: int | None = None,
     command_wrapper: _LinuxResourceCommandWrapper,
     verification_cache_root: Path | None = None,
+    prepared_step=None, workspace_session=None, prepared_attempt=None,
 ) -> ExecutionResult:
     """Actual policy-command quota chain; not an automatic-mode support grant."""
+    borrowing_keywords = (dict(prepared_step=prepared_step,
+        workspace_session=workspace_session, prepared_attempt=prepared_attempt)
+        if prepared_step is not None else {})
     return _execute_linux_observed_command(
         argv, cwd=cwd, sandbox=sandbox, policy=policy, timeout=timeout,
         output_limit_bytes=output_limit_bytes, command_wrapper=command_wrapper,
         resource_mode=True, helper_object_mode=True,
-        verification_cache_root=verification_cache_root,
+        verification_cache_root=verification_cache_root, **borrowing_keywords,
     )
-
+
-
+
@@ -272,6 +280,7 @@
     command_wrapper: Callable[..., list[str]], resource_mode: bool,
     verification_cache_root: Path | None = None,
     helper_object_mode: bool = False,
+    prepared_step=None, workspace_session=None, prepared_attempt=None,
 ) -> ExecutionResult:
     """Run a Linux deny-only command with a pre-exec USER_NOTIF observer.
-
+
@@ -280,7 +289,17 @@
     prevents payload execution and never degrades to an unobserved command.
     """
     owner = None
+    borrow_context = None
+    borrowing = False
+    cleanup_unknown = False
+    def note_cleanup_unknown():
+        nonlocal cleanup_unknown
+        cleanup_unknown = True
     try:
+        if prepared_step is not None and (not sys.platform.startswith("linux")
+                or helper_object_mode is not True):
+            return ExecutionResult(None, "", 0, "isolation_unavailable", False, True, None,
+                violation_observer_status="incomplete", payload_started=False)
         if type(helper_object_mode) is not bool:
             return ExecutionResult(None, "", 0, "invalid_violation_scope", False, True, None)
         if not sys.platform.startswith("linux"):
@@ -300,6 +319,9 @@
             or policy.network_mode is not NetworkMode.DENY
             or policy.allowed_domains
         ):
+            if prepared_step is not None:
+                return ExecutionResult(None, "", 0, "isolation_unavailable", False, True, None,
+                    violation_observer_status="incomplete", payload_started=False)
             return ExecutionResult(None, "", 0, "invalid_violation_scope", False, True, None)
-
+
         if verification_cache_root is not None:
@@ -389,9 +411,14 @@
                             resource.wait(timeout_seconds=0.2)
                         elif operation == "resource_close" and resource is not None:
                             resource_closed = resource.close()
+                            if resource_closed is not True:
+                                note_cleanup_unknown()
                         elif operation == "monitor_close" and monitor is not None:
                             monitor_closed = monitor.close()
+                            if monitor_closed is not True:
+                                note_cleanup_unknown()
                     except BaseException as error:
+                        note_cleanup_unknown()
                         cleanup_error = _select_cleanup_error(cleanup_error, error)
             return cleanup_error
-
+
@@ -411,6 +438,7 @@
                     return
                 endpoint.close()
             except BaseException as error:
+                note_cleanup_unknown()
                 # Disarm both stale identities and ambiguous close outcomes.
                 # Detach never closes a numeric FD or supplies cleanup credit;
                 # it prevents __del__ from making an unsafe second close.
@@ -444,6 +472,7 @@
                         from .linux_task_scope import LinuxTaskScopeError
                         raise LinuxTaskScopeError()
                 except BaseException as error:
+                    note_cleanup_unknown()
                     cleanup_error = _select_cleanup_error(cleanup_error, error)
             if helper_object_mode:
                 if cleanup_error is None:
@@ -471,7 +500,21 @@
                 or not argv[0]
             ):
                 raise ValueError("invalid argv")
-            if helper_object_mode:
+            if prepared_step is not None:
+                from .linux_prepared_step import _LinuxStepAttachment, LinuxPreparedStepError
+                if not helper_object_mode or type(prepared_step) is not _LinuxStepAttachment:
+                    raise LinuxPreparedStepError()
+                try:
+                    same_sandbox = prepared_step._current()._sandbox is sandbox
+                except AttributeError:
+                    raise LinuxPreparedStepError() from None
+                if not same_sandbox:
+                    raise LinuxPreparedStepError()
+                borrow_context = prepared_step.borrow(policy=policy,
+                    workspace_session=workspace_session, attempt=prepared_attempt)
+                owner = borrow_context.__enter__()
+                borrowing = True
+            elif helper_object_mode:
                 from .linux_helper_object import open_linux_helper_object
                 if sandbox.manifest is None:
                     raise RuntimeError("helper manifest is unavailable")
@@ -600,6 +643,8 @@
                 launch_env = _policy_environment(policy.workspace_root, verification_cache_root=verification_cache_root)
                 for key in ("XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS"):
                     launch_env[key] = task_scope.environment[key]
+            cleanup_keywords = ({"on_cleanup_unknown": note_cleanup_unknown}
+                                if borrowing else {})
             result = _execute_policy_command(
                 wrapped,
                 cwd=working_directory,
@@ -612,7 +657,10 @@
                 launch_env=launch_env,
                 manager_stderr=resource_mode,
                 before_spawn=before_spawn if helper_object_mode else None,
+                **cleanup_keywords,
             )
+            if result.cleanup_ok is not True:
+                note_cleanup_unknown()
             if helper_object_mode and result.error == "invalid_handoff":
                 result = replace(result, payload_started=False)
         finally:
@@ -620,7 +668,10 @@
             try:
                 if task_scope is not None:
                     scope_cleanup_ok = task_scope.collected(time.monotonic() + 1)
+                    if scope_cleanup_ok is not True:
+                        note_cleanup_unknown()
             except BaseException as exception:
+                note_cleanup_unknown()
                 cleanup_error = _select_cleanup_error(cleanup_error, exception)
             finally:
                 try:
@@ -667,6 +718,8 @@
             outcome = replace(outcome, resource_receipt=resource_receipt,
                               scope_cleanup_ok=scope_cleanup_ok, payload_started=started)
             terminal = resource_receipt["terminal"] if complete else None
+            if terminal == "cleanup_failed":
+                note_cleanup_unknown()
             if terminal in ("preexec_failed", "cleanup_failed"):
                 outcome = replace(outcome, error="resource_setup_failed" if terminal == "preexec_failed"
                                   else "resource_cleanup_failed")
@@ -674,7 +727,7 @@
                 outcome = replace(outcome, output="", raw_output=b"", output_bytes=0)
         return outcome
     finally:
-        if owner is not None:
+        if owner is not None and not borrowing:
             active_exception = sys.exc_info()[1]
             try:
                 owner.close()
@@ -689,6 +742,22 @@
                     selected = _select_cleanup_error(active_exception, cleanup_error)
                 if selected is not active_exception:
                     raise selected
+        if borrowing:
+            active_exception = sys.exc_info()[1]
+            try:
+                if cleanup_unknown:
+                    prepared_step._mark_faulted()
+                    if isinstance(active_exception, Exception):
+                        from .linux_helper_object import LinuxHelperObjectError
+                        if not isinstance(active_exception, LinuxHelperObjectError):
+                            raise LinuxHelperObjectError() from None
+            except BaseException as cleanup_error:
+                selected = (active_exception if active_exception is not None
+                    and not isinstance(active_exception, Exception) else cleanup_error)
+                if selected is not active_exception:
+                    raise selected
+            finally:
+                borrow_context.__exit__(None, None, None)
-
+
-
+
 def _execute_policy_command(
@@ -700,6 +769,7 @@
     launch_env: dict[str, str] | None = None,
     manager_stderr: bool = False,
     before_spawn: Callable[[], None] | None = None,
+    on_cleanup_unknown: Callable[[], None] | None = None,
 ) -> ExecutionResult:
     """Private process core with a narrowly scoped trusted-launch hook."""
     if os.name != "posix":
@@ -830,20 +900,32 @@
         from .linux_task_resource import _select_cleanup_error
         active_exception = sys.exc_info()[1]
         cleanup_error = active_exception
+        def notify_cleanup_unknown():
+            nonlocal cleanup_error
+            if on_cleanup_unknown is not None:
+                try:
+                    on_cleanup_unknown()
+                except BaseException as exception:
+                    cleanup_error = _select_cleanup_error(cleanup_error, exception)
         try:
             if selector is not None:
                 selector.close()
         except BaseException as exception:
             cleanup_error = _select_cleanup_error(cleanup_error, exception)
+            notify_cleanup_unknown()
         try:
             cleanup_ok, cleanup_errno = _stop_group(process)
+            if cleanup_ok is not True:
+                notify_cleanup_unknown()
         except BaseException as exception:
             cleanup_error = _select_cleanup_error(cleanup_error, exception)
+            notify_cleanup_unknown()
         for stream in (process.stdout, process.stderr):
             try:
                 if stream is not None:
                     stream.close()
             except BaseException as exception:
                 cleanup_error = _select_cleanup_error(cleanup_error, exception)
+                notify_cleanup_unknown()
         if cleanup_error is not None and cleanup_error is not active_exception:
             raise cleanup_error
~~~

通知位置账：resource/monitor close非True及cleanup catch、endpoint close/detach unknown、scope.close异常/未confirmed、collected非True/异常、process result cleanup非True、resource terminal cleanup_failed。incomplete protocol本身不推断资源未关闭。ordinary body只有与真实unknown同时发生才固定转换；首信号原对象优先。标faulted后归还期间不关闭helper、不finish attachment；无scope保持旧返回、kwargs和factory/close责任。

- [ ] **Step 2: 同一 SOURCE writer 运行中间分片既有16方法GREEN，再跑新manager有效RED并停止。**

~~~sh
.venv/bin/python -B - <<'PY'
import unittest
from tests import test_linux_prepared_broker as module
names = unittest.defaultTestLoader.getTestCaseNames(module.PreparedBrokerTests)
names = [name for name in names if not name.startswith(('test_manager_', 'test_construction_'))]
assert len(names) == 16
suite = unittest.TestSuite(module.PreparedBrokerTests(name) for name in names)
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() and not result.skipped else 1)
PY
.venv/bin/python -B -m unittest tests.test_linux_prepared_broker.PreparedBrokerTests.test_manager_constructor_unknown_target -v
~~~

第一条16methods预期0F/E/skip、exit0；第二条1 test / 1 assertion failure、0 errors/skip、exit1，前提明确为真实bound view已进入borrow，Scope constructor在task_scope赋值前执行真实manager_query、原process core返回cleanup_ok=False/error=cleanup_failed，公共返回isolation_unavailable但消费状态仍attached_bound。目标断言必须精确命中faulted期待，不把普通body/KeyError/未接线/夹具错误算RED。Task2报告中间SOURCE SHA、原输出并停写；root全读且独立复现第二条后才能派不同freshTask2R。Task2不是完整GREEN，不运行原full preflight/提交。

旧关联回归可在上述目标前运行，命令为：

~~~sh
.venv/bin/python -B -m unittest tests.test_linux_prepared_step tests.test_linux_helper_dispatch tests.test_execution_broker tests.test_linux_task_resource tests.test_linux_violation_receipt tests.test_linux_helper_object -v
~~~

旧 native/OS 相关skip按原输出独立记录，不授本片acceptance，已有软件用例不许降断言。Task2中间自审必须明确manager门未修，不能写七维全部通过或完整可运行交付。

## 3R. Task 2R：manager query 最小通知配对修复

**状态**
- [ ] 任务完成

**Dependencies:** Task 2（root在实际中间SOURCE独立复现manager有效assertion RED）
**Parallelizable:** No（不同fresh Task2R SOURCE writer，唯一同文件writer）

- [ ] **Step 1: 仅在 Task2 的manager_query函数应用以下完整最小差分。**

~~~diff
--- a/src/icode/execution_broker.py
+++ b/src/icode/execution_broker.py
@@ -394,9 +394,13 @@
             if remaining <= 0:
                 raise LinuxTaskScopeError()
             query_policy = replace(policy, output_limit_bytes=_MANAGER_STDOUT_LIMIT_BYTES, wall_timeout_seconds=1)
+            cleanup_keywords = ({"on_cleanup_unknown": note_cleanup_unknown}
+                                if borrowing else {})
             answer = _execute_policy_command(command, cwd=working_directory, policy=query_policy,
                                              timeout=remaining, output_limit_bytes=_MANAGER_STDOUT_LIMIT_BYTES,
-                                             launch_env=environment, manager_stderr=True)
+                                             launch_env=environment, manager_stderr=True, **cleanup_keywords)
+            if borrowing and answer.cleanup_ok is not True:
+                note_cleanup_unknown()
             if answer.error is not None or answer.exit_code != 0:
                 raise LinuxTaskScopeError()
             return answer.raw_output
~~~

该私有query闭包被constructor及后续manager操作复用；所有调用都依同一borrowing事实获得通知。保留原remaining/output预算、environment、original error/exit检查、返回raw_output，无scope不新增keyword。返回cleanup_ok非True只记unknown，不把普通body异常猜成unknown，不授清理确认。实际process core的cleanup_ok=False原返回error=cleanup_failed，query原门仍阻断；首signal走通知通道，不依赖不存在的answer。constructor失败时task_scope尚未赋值也须在active borrow最外finally标faulted后归还，helper仍active、创建者唯一关闭。

- [ ] **Step 2: Task2R运行非construction的20方法GREEN及manager目标，再取两个真实construction目标有效RED。**

~~~sh
.venv/bin/python -B - <<'PY'
import unittest
from tests import test_linux_prepared_broker as module
names = unittest.defaultTestLoader.getTestCaseNames(module.PreparedBrokerTests)
names = [name for name in names if not name.startswith('test_construction_')]
assert len(names) == 20
suite = unittest.TestSuite(module.PreparedBrokerTests(name) for name in names)
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() and not result.skipped else 1)
PY
.venv/bin/python -B -m unittest tests.test_linux_prepared_broker.PreparedBrokerTests.test_manager_constructor_unknown_target tests.test_linux_prepared_broker.PreparedBrokerTests.test_manager_signal_with_unknown_notice_keeps_original_and_faulted tests.test_linux_prepared_broker.PreparedBrokerTests.test_old_none_manager_query_does_not_add_notification_keyword -v
.venv/bin/python -B -m unittest tests.test_linux_prepared_step tests.test_linux_helper_dispatch tests.test_execution_broker tests.test_linux_task_resource tests.test_linux_violation_receipt tests.test_linux_helper_object -v
.venv/bin/python -B -m unittest tests.test_linux_prepared_broker.PreparedBrokerTests.test_construction_seccomp_real_unreturned_socket_target tests.test_linux_prepared_broker.PreparedBrokerTests.test_construction_scope_real_unreturned_tool_fd_target -v
~~~

20methods及三个manager目标均0F/E/skip、exit0；最后两个真实construction目标须2assertFAIL/0errors/skip、exit1，分别在真实socket和真实trusted-tool FD仍活、工厂未返回、borrow已归还/owneractive的前提命中attached_bound≠faulted。新manager普通构造失败期待在Task1就改为faulted，并列construction方法，不能临时改测试制造RED。旧native/OS skip独立记；Task2R报告中间源码/原失败并停写，root全文核并实际独立复现后不同freshTask2A才实施A。不能报完整GREEN，不自行fullguard/提交。

## 3A. Task 2A：仅五创建点的保守消费结束门

**状态**
- [ ] 任务完成

**Dependencies:** Task 2R（root在实际query修复后SOURCE复现两个真实construction有效RED）
**Parallelizable:** No（不同freshTask2A writer，同文件唯一writer）

- [ ] **Step 1: 对Task2R中间SOURCE仅应用以下完整最小A差分。**

~~~diff
--- a/src/icode/execution_broker.py
+++ b/src/icode/execution_broker.py
@@ -292,9 +292,18 @@
     borrow_context = None
     borrowing = False
     cleanup_unknown = False
+    construction_failed = False
     def note_cleanup_unknown():
         nonlocal cleanup_unknown
         cleanup_unknown = True
+    def construct(factory, *args, **kwargs):
+        nonlocal construction_failed
+        try:
+            return factory(*args, **kwargs)
+        except BaseException:
+            # Failure before return is opaque; do not claim internal cleanup.
+            construction_failed = True
+            raise
     try:
         if prepared_step is not None and (not sys.platform.startswith("linux")
                 or helper_object_mode is not True):
@@ -526,10 +535,13 @@
             if resource_mode:
                 from .linux_task_scope import LinuxTaskScope
                 from .linux_task_resource import create_task_resource_channel
-                task_scope = LinuxTaskScope(limit=policy.process_limit, query=manager_query)
-                resource_host, resource_sender = create_task_resource_channel()
+                task_scope = (construct(LinuxTaskScope, limit=policy.process_limit, query=manager_query)
+                              if borrowing else LinuxTaskScope(limit=policy.process_limit, query=manager_query))
+                resource_host, resource_sender = (construct(create_task_resource_channel)
+                                                 if borrowing else create_task_resource_channel())
                 snapshot_endpoints(resource_host, resource_sender)
-            host_control, sender_control = create_seccomp_listener_handoff_channel()
+            host_control, sender_control = (construct(create_seccomp_listener_handoff_channel)
+                                            if borrowing else create_seccomp_listener_handoff_channel())
             snapshot_endpoints(host_control, sender_control)
         except (IndexError, OSError, RuntimeError, TypeError, ValueError):
             close_endpoints()
@@ -576,8 +588,10 @@
                 def configured(deadline: float) -> None:
                     task_scope.configured(min(deadline, launch_start + _RESOURCE_CONFIGURE_TIMEOUT_SECONDS))
-
+
-                resource = LinuxTaskResourceReceiver(resource_host, unit=task_scope.unit,
-                                                     limit=policy.process_limit, on_configured=configured)
+                resource = (construct(LinuxTaskResourceReceiver, resource_host, unit=task_scope.unit,
+                                      limit=policy.process_limit, on_configured=configured)
+                            if borrowing else LinuxTaskResourceReceiver(resource_host, unit=task_scope.unit,
+                                                                         limit=policy.process_limit, on_configured=configured))
             else:
                 wrapped = command_wrapper(argv, sender_control, **wrapper_keywords)
                 helper_index, scope_prefix = 0, ()
@@ -608,7 +622,8 @@
                                          launch_fds=launch_fds, argv_snapshot=argv_snapshot)
             if helper_object_mode:
                 before_spawn()
-            monitor = LinuxSeccompViolationMonitor(host_control)
+            monitor = (construct(LinuxSeccompViolationMonitor, host_control)
+                       if borrowing else LinuxSeccompViolationMonitor(host_control))
         except (IndexError, OSError, RuntimeError, TypeError, ValueError):
             close_endpoints()
             return ExecutionResult(
@@ -749,12 +764,12 @@
         if borrowing:
             active_exception = sys.exc_info()[1]
             try:
-                if cleanup_unknown:
+                if cleanup_unknown or construction_failed:
                     prepared_step._mark_faulted()
-                    if isinstance(active_exception, Exception):
-                        from .linux_helper_object import LinuxHelperObjectError
-                        if not isinstance(active_exception, LinuxHelperObjectError):
-                            raise LinuxHelperObjectError() from None
+                if cleanup_unknown and isinstance(active_exception, Exception):
+                    from .linux_helper_object import LinuxHelperObjectError
+                    if not isinstance(active_exception, LinuxHelperObjectError):
+                        raise LinuxHelperObjectError() from None
             except BaseException as cleanup_error:
                 selected = (active_exception if active_exception is not None
                     and not isinstance(active_exception, Exception) else cleanup_error)
~~~

仅已进入borrow才调用construct；旧None直接原factory，参数与异常对象不变。五个调用都是创建操作，不包task_scope.wrap、全部业务body、前置检查或owner factory。已返回的其它资源仍按原cleanup处理，未返回资源不冒领/重试；A最终faulted不表示cleanup_ok、ownerclosed或内部FD已回收。

- [ ] **Step 2: 完整26方法GREEN及两个真实目标复验、旧关联回归。**

~~~sh
.venv/bin/python -B -m unittest tests.test_linux_prepared_broker -v
.venv/bin/python -B -m unittest tests.test_linux_prepared_broker.PreparedBrokerTests.test_construction_seccomp_real_unreturned_socket_target tests.test_linux_prepared_broker.PreparedBrokerTests.test_construction_scope_real_unreturned_tool_fd_target -v
.venv/bin/python -B -m unittest tests.test_linux_prepared_step tests.test_linux_helper_dispatch tests.test_execution_broker tests.test_linux_task_resource tests.test_linux_violation_receipt tests.test_linux_helper_object -v
~~~

26methods与两目标0F/E/skip、exit0；真实两个目标仍须先证明未返回资源实际live，再断消费faulted/后续borrow拒绝。tests finally明确自身释放只是卫生，FD残留与内部signal B债务不能记成通过；源码作者七维自审、实际输出与摘要后停写，root全读独立复验→freshSPEC→不同QUALITY→原full preflight，不自行交接/提交。

## 4. Task 3：独立审查、统一冻结与原完整预检

**状态**
- [ ] 任务完成

**Dependencies:** Task 2A
**Parallelizable:** No（fresh SPEC 完成后不同 QUALITY；root 唯一 original full preflight）

- [ ] **Step 1: root 全读新源码/测试与差分，独立复现新模块及两目标 GREEN。**

~~~sh
.venv/bin/python -B -m unittest tests.test_linux_prepared_broker -v
.venv/bin/python -B -m unittest tests.test_linux_prepared_broker.PreparedBrokerTests.test_violation_public_forwarding_target tests.test_linux_prepared_broker.PreparedBrokerTests.test_resource_public_forwarding_target -v
git diff --check
~~~

核 helper factory/close 0 次，实际 owner/session/lease 仍活；顺序两 public 同引用；未知 cleanup 在归还前 faulted，原首信号 object unchanged，各独立资源仍尽力回收。需追加 endpoint unknown 的现有旧 dispatch 回归确认，不能只看新 monitor/resource 模拟。原 test suite `TestDispatchOwner` 已含 endpoint close/detach unknown、metadata 漂移与所有 owning 首信号合同，本片不得修改它。

- [ ] **Step 2: fresh SPEC 全读母/本 PLAN/实际 SOURCE/test，随后不同 QUALITY。**

必须审查 code 中实际所有通知点，不以计划自评替代；两个 reviewers 不能互相复用结论。若 I/C，冻结撤销、原失败保留、测试先行修复后重新审；不得跳过整套兼容。validator 前提仅可信只读 CP observer：主动改变生命周期的 arbitrary callback 不属于当前合同，但 S2 必须核真实 observer，不宣称任意 callback 安全。

- [ ] **Step 3: source/test 冻结后 root 一次原完整 preflight，最多 -j1。**

~~~sh
validation_log_dir=$(mktemp -d /tmp/icode-s1c-preflight.XXXXXX)
printf '%s\n' "$validation_log_dir/typescript"
script -q -e -f -c 'CMAKE_BUILD_PARALLEL_LEVEL=1 MAKEFLAGS=-j1 .venv/bin/python -B -u scripts/preflight.py' "$validation_log_dir/typescript"
~~~

记录真实原 log、started/done、三 guard/exit；不能以 focused/CI 或作者命令替代。源码再改即撤销该次信用。等待期间仅 DOCS/只读 CI 研究，不启动下片 SOURCE。

- [ ] **Step 4: root 填实证记录、最小 live 更新，文档审计原脚本运行两遍。**

~~~sh
.venv/bin/python -B /home/orbbec/.agents/skills/doc-contract-consistency-audit/scripts/check_consistency.py docs/nbl/plans/2026-10-12-linux-prepared-broker-borrow.md docs/nbl/specs/2026-10-12-linux-prepared-broker-construction-design.md docs/agent-landscape-live.md
.venv/bin/python -B /home/orbbec/.agents/skills/doc-contract-consistency-audit/scripts/check_consistency.py docs/nbl/plans/2026-10-12-linux-prepared-broker-borrow.md docs/nbl/specs/2026-10-12-linux-prepared-broker-construction-design.md docs/agent-landscape-live.md
git diff --check
~~~

按实际原 raw finding/exit 登记并逐项人工判定；代码 fence 中参数/异常名误报不得写为 raw=0。文档最后更改后两次重新运行，不能改 scanner 绕过。

- [ ] **Step 5: fresh secret/submodule 单项 gate、精确五路径 index bytes 与 SHA 校核后提交推送 main。**

原单项入口已读取 `scripts/preflight.py` 的 argparse/guard mapping，完整命令如下。确认 vendor 固定 `21566a589cbe98bd35372a04bbb6ca1c51d8eed2` 且 clean；测试 KEY 不读正文/复制/上传。此前候选三工作流需全部 terminal，避免新 push 取消未收证据的工作流。

~~~sh
.venv/bin/python -B scripts/preflight.py --only secrets
.venv/bin/python -B scripts/preflight.py --only submodule
~~~

~~~sh
git add src/icode/execution_broker.py tests/test_linux_prepared_broker.py docs/agent-landscape-live.md
git add -f docs/nbl/plans/2026-10-12-linux-prepared-broker-borrow.md docs/nbl/specs/2026-10-12-linux-prepared-broker-construction-design.md
git diff --cached --name-only
git diff --cached --check
git commit -m "feat(linux): borrow prepared helper per observed command"
git push origin main
git ls-remote --heads origin
~~~

index只能上述五路径，`git show :path`与冻结工作bytes五项相等；补充DESIGN必须仍批准SHA79badff6...，母DESIGN不stage；记录实际commit/push/remote main，不新分支、不顺带unrelated files。

- [ ] **Step 6: readonly observer 收同 SHA 三工作流及已有 native Linux 四格，开始 S2 精确设计。**

原 84 dispatch 记录仍不是 S1c installed credit，因为尚未新增 installed prepare/borrow 场景；Reviewer timeout/10035/缺 WFP 保持 inconclusive，不称 R2/R3 PASS。S2 才接真实 run_chain/runner/ToolContext/工程 verification，S3 才新 installed 四格，后续 LA-2 正式准入仍不翻 ready。

## 5. 作者自审与执行约束

规格覆盖：Task1/2处理public caller facts/同owner/逐资源清理，Task2R补manager返回与异常通知，Task2A补五创建未返回的保守消费结束；Task3处理fresh双审/原full guard/原scanner/精确五路径发布。真实两个资源反例先证FD live再证消费结束，成功创建普通body仍bound，旧None不变；B工厂内部清理/析构/内部首signal及S2/S3/正式准入不由A完成。

类型一致性：`_LinuxStepAttachment.borrow(policy, workspace_session, attempt)`、`_current()`、`_mark_faulted()` 使用实际 S1b 符号，`PreparedCommand` 与 held launch gate保持原实现。新参数名称统一 `prepared_attempt`，仅进入 borrow 时映射为 `attempt`。callback 只通知 cleanup unknown，不返回 bool 信用。

PLAN作者原稿RAM可行性历史（不计Task1/2实施信用）：当前public两个目标各命中`None is not view`，2assertionFAIL/0error/skip、0.099s；原17-hunk中间投影曾14/1.106s及15/1.301s均0F/E/skip，但这些旧测试没有覆盖manager query，不表示完整GREEN。所有诊断harness自身exit0仅表示预期检查成立。

freshPLAN SPEC随后实证I1：原17-hunk manager_query未传通知或核answer.cleanup_ok，Scope constructor在task_scope赋值前经真实query取得cleanup_ok=False/error=cleanup_failed后，public isolation_unavailable、scope attached_bound/owneractive/inflightFalse；目标faulted为1assertFAIL/0errors/skip、0.088s。root03:54:03 UTC独立采用原完整harness复现1assertFAIL/0errors/skip、0.095s，同样manager_notice_present=False，磁盘SOURCE未变。旧freeze撤销；保留此失败，不用15方法旧GREEN掩盖。

前次I1的DOCS返修新增六个manager方法，RAM中间16/1.293s零F/E/skip→constructor1assertFAIL/0E/skip、0.060s→query修复后21/1.509s零F/E/skip。此为历史可行性，不授实施；随后QUALITY的真实未返回资源反例使该旧freeze被阻断。

QUALITY随后发现未返回资源反例，root真实两目标2assertFAIL/0E/skip、0.147s；不是正式落盘TDD RED。35e63旧freeze被阻断，未实施SOURCE；批准补充DESIGN79badff6...采用A，工厂内部B债务保留。当前最终test资产Task1一次先写26方法，manager普通构造失败期待也事先改faulted，不临时改断言。作者仅RAM验证query中间20/1.382s零F/E/skip→两真实construction目标2assertFAIL/0E/skip、0.102s，再应用五hunk A初验完整26/1.794s零F/E/skip；最终字节又对六construction方法+成功构造普通body方法共7/0.511s零F/E/skip实核。此为可行性，不替实际Task2R construction RED/root独立复现或Task2A生产GREEN。

资产摘要：完整test代码块不含fence、无尾LF正文SHA256 `f6da81b69ed9bf6adae8d492d5373cc5f408382c745b05be9454908d9f85f485`；实际拟落`tests/test_linux_prepared_broker.py`在正文末尾保留单LF，文件SHA256 `58a4d13703e99b2c5373b5c264485598ab0cd7da9e9be555c884ffa8d9b3641c`。Task2原17-hunk中间SOURCE投影SHA256仍`f8ffcf83736a56af6cfe90fc3757c7a0e1074ae4a7dacd0f98ed3cbe65875693`；Task2R query单hunk中间SOURCE投影SHA256 `04508782dd54384feee2390aba91680662c0bfdf2171f87481efe5c426eb9823`；Task2A五hunk最终SOURCE投影SHA256 `3212f07039ceb72435b92bef0ade2c1f62ec0ea6452b55a53334e9401d321ca9`。Task1按单尾LF文件口径核test，三SOURCE阶段分别核中间/最终同字节；摘要/语法不替独立验收。

【架构级自检报告】（计划文档，不是实施结果）

- 语法/编译：已核完整test及17+1+5各阶段RAM差分上下文/compile；生产源码未改，不报告实施完成。
- 依赖/调用链：两 public → 唯一 observed core → 原 process core 明确，旧 callback 不扩散。
- 逻辑/边界：caller session/attempt 不反取，owning/borrowing 分账；pending/spent/reentry/unknown拒绝。
- 异常处理：26方法资产覆盖manager与五创建操作失败，broker收到的首signal对象不变；工厂内部首signal/FD债务保留，仍待正式TDD与独立复审。
- 关联模块：精确SOURCE/test/PLAN/已批准补充DESIGN/live五路径，无vendor/runner/ToolContext/ready修改。
- 兼容安全：None kwargs形状不变，无 fallback/新依赖/权限；新增接口细化显式返审。
- 可运行性：仅 DOCS ONLY 静态自审，不报告100%、CP/installed/整体完成。

**Execution Mode:** serial

仅PLAN writer按委托停止；不执行技能自动交接。root独立PLAN SPEC复审→不同QUALITY后启动freshTask1最终完整test writer；root public baseline RED后，不同freshTask2写原17-hunk，manager RED/root复现后不同freshTask2R仅补query。真实construction两目标RED/root复现后，不同freshTask2A最小A修复，最终完整GREEN再freshSOURCE双审与root原full preflight，阶段main-only精确五路径提交推送。不得先写A再删门取得RED。

## 6. Task2B：已返回接收器清理确认（当前执行修订）

依据：[receiver-cleanup DESIGN](../specs/2026-10-12-linux-prepared-receiver-cleanup-design.md)。仅新增 tests/test_linux_resource_cleanup.py 与修改 src/icode/linux_task_resource.py；broker3212f070 与原新测试58a4d137保持不变。新增 DESIGN 独立 SPEC→不同 QUALITY 后才开始本项。

本项 DESIGN SHA256 `4298d18944534d1690fbf497beeeb445cab8aa5ebfdc2e87a2260caeb96d5fd8`，不同独立设计 SPEC 与 QUALITY 均正式 C0/I0/M0；旧 receiver 基线 `2c7158a6b3d5ef67d42578ebe675a12aeb97a1896e3790c9bbdca22d42cf6217`。测试作者获 GO，源码作者只读准备，尚未供应正式新 RED/GREEN 信用。

随后正式新测试冻结 `c95280d20ffcec97b67909794ed84f82a9cb00d93a3176105d8a2a5d445a1282`；作者/root 实际7方法、6有效assertionFAIL（含三种异常subtest）、0error/skip、exit1，0.360s/0.383s。实际rights/selector FD留存及worker停止先成立，三个broker目标在 attached_bound≠faulted 失败；OSError目标在closeTrue≠False失败，KI/SE目标在后续FD未尝试失败，三个兼容控制通过。卫生只剔除/proc枚举自身已关闭FD，未改变目标；SOURCE仍原2c7158a6，不同源码作者才获最终GO。

不同源码作者随后仅修改 receiver，冻结 `3f2317f32d710ba3407f6255bdad73055ec5ff4992ef68f955fc3d6780c8b46d`。作者新7/0.358s、26/1.734s、旧163/21.069s均0F/E/skip；root实际新两模块33/2.182s、旧六模块163/21.105s均0F/E/skip。root读组件原全文与完整最小diff；compileall-j1、site/governance、diff检查通过。未知只在收到FD关闭、selector创建未返回或selector关闭失败设置，普通协议失败不设，所有权/schema不变。fresh SOURCE SPEC进行中，原fullguard与发布仍未执行。

fresh 实际 SOURCE SPEC→不同 QUALITY 随后均正式 C0/I0/M0；各自新33 GREEN2.155s/2.076s，0F/E/skip，四源码/测试摘要一致。root 原唯一完整 preflight session21171 于05:03:56 UTC观察启动，日志 `/tmp/icode-s1c-preflight.tyNlsR/typescript`，CMAKE_BUILD_PARALLEL_LEVEL=1/MAKEFLAGS=-j1；目前进行中，未授完整通过或发布。历史失败与B债务不被删除。

原唯一完整 preflight 现exit0：日志footer05:13:12 UTC，root05:13:38 UTC取得三门OK。原入口成功时不输出全量测试数量，本片不推测总数。四源码/测试冻结不变；最终文档、单门复核和八路径index核对后才发布main。B内部工厂/析构/内部signal、deadline竞争、真实CP/S2/S3/跨平台仍不由本片关闭。

- [x] 不同测试作者完整读组件/夹具后，仅用 apply_patch 新增测试；实际 worker 与 SCM_RIGHTS/selector FD留存先成立，再断言 close=False、attachment faulted与下一借用拒绝，不能用缺符号/TypeError算RED。另覆盖多个收到的FD独立一次清理、普通malformed可继续借用、selector未正常返回的保守未知、未启动close与重复close sticky。测试自身清理仅卫生。
- [x] root 完整读新测试，独立实际执行有效 assertion RED，冻结测试；不得提前写生产修复再删门。
- [x] 不同源码作者最小 sticky未知/selector显式finally/close完整确认；FD异常继续后续原delivery，不重试，不转移socket/process所有权。仅一个源码作者，不修改旧测试或broker。
- [x] 作者/root 新测试、26项、receiver与原163回归；fresh SOURCE SPEC→不同QUALITY覆盖八路径修订和实际源码，任一遗留先返修，不启动fullguard。
- [x] root 原完整 preflight，最终文档一致性两轮及 fresh secret/submodule 门；七维自检按实际结果报告（最终元数据修改后再原样复核两轮及单门，不跳过）。
- [ ] 精确八路径 index/worktree 字节相等、cached diff检查后提交推送main；不stage母设计/vendor/旧测试/CI。新DESIGN取代上文Task3的五路径发布命令，不新分支。

正式 Task1 author/root public 两有效FAIL（0.100s/0.106s）；Task2 root16 GREEN1.245s且manager1有效FAIL0.055s；Task2R root20 GREEN1.420s且construction两有效FAIL0.142s；Task2A root26 GREEN1.807s、旧163 GREEN21.105s，均0error/skip。上述阶段不重跑删门制造RED。returned-receiver-I3新组件必须独立测试先行；原 SOURCE SPEC零遗留不覆盖后续 QUALITY重要缺陷。
