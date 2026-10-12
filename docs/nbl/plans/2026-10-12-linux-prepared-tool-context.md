# Linux S2a ToolContext Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development (recommended) or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 本文只授计划；root 在 B2 完整验收和 main 发布后另发 GO，才可启动 fresh 测试作者。writer 完成后停止，不自动 handoff。

**Goal:** 在可信 ToolContext 与现有 Linux resource broker 之间保留并配对转发准备 attachment/session/attempt，保持旧 None 调用形状。

**Architecture:** 两个借用字段、一个局部构造适配、一个 dispatch 前置形状门；真正资格验证及唯一 borrow 保留在既有 broker。context 不拥有准备对象，不 attach/bind/finish/close owner；生产 runner、真实 CP 与 finally 完整生命周期留 S2b。

**Tech Stack:** Python 3.11+、dataclass、unittest、既有 Linux session/FD/lease/channel 与软件资源 fixture；无新依赖、权限或模型 schema。

---

## 批准依据、暂停线及精确范围

批准 [DESIGN](../specs/2026-10-12-linux-prepared-tool-context-design.md) SHA256 `1f6405a2d9ea3a75d4f1b6a0037fc0144db0a8a8be7ddd47274c8556e8a34758`，独立 SPEC 与不同 QUALITY 均 C0/I0/M0。母合同 [prepared-step DESIGN](../specs/2026-10-12-linux-prepared-step-scope-design.md) 只读。真实问题、已有实现及调用链三问已确认：生产 context 缺借用引用，复用 S1/S1c 已有 attachment 与 broker，不增加 owner 或二次 borrow。

writer开始时 main `80f36ec`、B2 guard96748运行中，仅允许DOCS预备。root随后实际完成B2五路径commit/push，当前实施基线 main `60325a4e2a98f14714911ba75da444b4a027a454`，HEAD/remote同SHA及clean已核；三S2a SOURCE和批准DESIGN字节不变。本文仍DOCS ONLY，下一片SOURCE/TEST尚未实施；root fresh PLAN双审及另发GO之前Task1不启动。正式实施仍先核实际HEAD/B2终态证据，若有漂移不得猜测或复用旧资产。当前三 SOURCE 的 SHA256 为：

| 路径 | 基线 SHA256 | 职责 |
| --- | --- | --- |
| `src/icode/tools/base.py` | `9515d0beb02ec45c752fb5f2aaa7e7d923e86403f285ba5b0897518e08cc6833` | 追加两个 keyword-only 借用字段，Linux 类型只 TYPE_CHECKING 导入 |
| `src/icode/tools/builtin.py` | `12cfa163a9fa61f1a762c6f3cd87edd83d34e28b9a6e4a2b993954ffbbac637d` | 实际 dispatch 内部 wrapper/broker 之前成对形状门与三 keyword 转发 |
| `src/icode/runner.py` | `5477acc209e82cf25687de37cb6690095bb3c7631ea2e569d6ea21ca7fad8e5c` | 仅 `_make_ctx` 局部两个可选参数与条件传入 |
| `tests/test_linux_prepared_tool_context.py` | 新建，完整资产见 Task 1 | 新字段、旧形状、直接 dispatch 门及实际 resource broker 消费 |
| `docs/nbl/specs/2026-10-12-linux-prepared-tool-context-design.md` | 上述批准字节 | root 最后只追加真实实施证据 |
| `docs/nbl/plans/2026-10-12-linux-prepared-tool-context.md` | 本文 | 操作、资产、有限信用和真实证据 |
| `docs/agent-landscape-live.md` | 实施前记录实际字节 | root 更新固定研究取舍与有限实施结论 |

严格七路径；旧 tests、scope/attachment/broker/native/vendor/CI、母设计只读。main-only，不建 branch/worktree；用户与 root 的边界覆盖技能 worktree/frequent-commit/自动 handoff 建议。测试作者、不同 SOURCE 作者、独立 SOURCE SPEC、不同 QUALITY 各自隔离上下文；只有 root 可跑完整 guard 和七路径一次 commit/push。

研究复用 DESIGN 真实 GET 窗口 2026-10-12 05:47:02–05:47:10 UTC 的 [OpenHands LocalWorkspace 固定3934349d](https://github.com/OpenHands/software-agent-sdk/blob/3934349da2db0433238621542173a00a8af7439c/openhands-sdk/openhands/sdk/workspace/local.py) 与 MIT LICENSE，不称最新 HEAD 或完整二十项刷新。采纳共享执行入口和生命周期分账；成本是三个局部适配与兼容负控；暂缓 callback 自动汇报；不适配直接宿主 bash、结果/typed 对象自证隔离。无复制、依赖或权限增加。验收是本片软件断言与原守护，不能替换 CP、安装包或自动准入。

### Task 1：fresh 测试作者落盘唯一新测试，root 重复有效 RED

**状态**

- [x] 任务完成

**Dependencies:** None（必须先满足 B2 发布及 root 另发 GO）
**Parallelizable:** No (冻结线、独立 TEST ONLY 与 root 重复 RED 后才 SOURCE)

- [x] **Step 1：root 只读确认 main、index 为空、三 SOURCE 和批准 DESIGN 字节一致，记录 B2 实际发布 SHA。**

~~~bash
git branch --show-current
git rev-parse HEAD
git status --short
git diff --cached --name-only
sha256sum src/icode/tools/base.py src/icode/tools/builtin.py src/icode/runner.py docs/nbl/specs/2026-10-12-linux-prepared-tool-context-design.md
~~~

预期 main、无其它 staged 路径、三 SOURCE 与本表一致。若不一致先返回 PLAN 重新核上下文和双审，不应用旧投影，不 reset 用户文件。B2 SHA 由真实日志/HEAD 核得，不由本文预填。

- [x] **Step 2：不同 fresh 作者以 apply_patch 新建 `tests/test_linux_prepared_tool_context.py`，完整内容如下。**

资产复用 S1 真 session/目录 FD/活 lease、合成 ELF 与固定软件 validator；软件 seam 不等于真实 CP、真实 payload、native/installed 验收。S1c `exercise` 只提供真实 channel 与 manager/payload 软件 seam；本类覆盖 `call`，每次必须真实 `_controlled_dispatch`→公共 resource broker→既有唯一 borrow。不得直接调用旧 fixture 的 `call`。Linux imports 条件化，非 Linux collection 不加载 Linux fixture；skip 不授能力。

~~~python
"""S2a thin adapter software contract; no CP/native/installed credit."""
from __future__ import annotations

from dataclasses import fields, replace
import inspect
import os
import sys
import unittest
from unittest.mock import patch

from icode import runner
from icode.tools import builtin
from icode.tools.base import IsolationUnavailable, ToolContext

LINUX = sys.platform.startswith('linux') and callable(getattr(os, 'pread', None))
if LINUX:
    from tests import test_linux_prepared_step as fixture
    from tests import test_linux_prepared_broker as broker_fixture
    from icode import execution_broker as broker
    from icode import linux_helper_object as factory
    from icode import linux_prepared_step as prepared


@unittest.skipUnless(LINUX, 'Linux software fixture; skip is not acceptance')
class PreparedToolContextTests(unittest.TestCase):
    if LINUX:
        setUp = fixture.PreparedTests.setUp
        write_image = fixture.PreparedTests.write_image
        precheck_fixture = fixture.PreparedTests.precheck_fixture
        cleanup_scopes = fixture.PreparedTests.cleanup_scopes
        prepare = fixture.PreparedTests.prepare
        attach = fixture.PreparedTests.attach
        bind = fixture.PreparedTests.bind
        borrow = fixture.PreparedTests.borrow
        exercise = broker_fixture.PreparedBrokerTests.exercise
        wrapper = broker_fixture.PreparedBrokerTests.wrapper

    def context(self, view=None, attempt=None, **changes):
        ctx = ToolContext(root=self.session.workspace_root, sandbox=self.sandbox,
            policy=self.policy, workspace_session=self.session)
        # Actual baseline dispatch is exercised without constructor TypeError.
        ctx.prepared_step, ctx.prepared_attempt = view, attempt
        for name, value in changes.items():
            setattr(ctx, name, value)
        return ctx

    def dispatch(self, ctx, **options):
        return builtin._controlled_dispatch(ctx, ['/usr/bin/true'],
            cwd=self.session.workspace_root, timeout=1, **options)

    def call(self, resource, view, **changes):
        self.assertIs(resource, True)
        ctx = getattr(self, 'closed_context', None)
        if ctx is None:
            ctx = self.context(view, 'software-attempt', **changes)
        ctx.wrap_command_with_resource_receipt = self.wrapper
        return self.dispatch(ctx)

    def test_old_eleven_positional_mapping_and_new_field_contract(self):
        values = (self.session.workspace_root, 77, self.sandbox, self.policy,
            object(), {'a': 'b'}, False, True, (), self.session, None)
        ctx = ToolContext(*values)
        names = ('root', 'output_limit', 'sandbox', 'policy', 'artifact_broker',
            'change_baseline', 'read_only_workspace', 'review_submission_enabled',
            'deny_read_roots', 'workspace_session', 'allowed_read_files')
        for name, value in zip(names, values):
            self.assertIs(getattr(ctx, name), value)
        by_name = {item.name: item for item in fields(ToolContext)}
        self.assertIn('prepared_step', by_name)
        self.assertIn('prepared_attempt', by_name)
        for name in ('prepared_step', 'prepared_attempt'):
            self.assertTrue(by_name[name].kw_only)
            self.assertFalse(by_name[name].repr)
            self.assertIsNone(by_name[name].default)
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        ctx = ToolContext(*values, prepared_step=view, prepared_attempt='software-attempt')
        self.assertIs(ctx.prepared_step, view)
        self.assertNotIn('prepared_step=', repr(ctx))
        self.assertNotIn('prepared_attempt=', repr(ctx))
        with self.assertRaises(TypeError):
            ToolContext(*values, view, 'software-attempt')

    def test_make_ctx_same_references_no_lifecycle_and_none_old_kwargs(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        old = dict(root=self.session.workspace_root, sandbox=self.sandbox,
            policy=self.policy, artifact_broker=None, change_baseline=None,
            read_only_workspace=False, review_submission_enabled=False,
            deny_read_roots=(), allowed_read_files=None, workspace_session=self.session)
        supported = inspect.signature(runner._make_ctx).parameters
        for step, attempt in ((None, None), (view, 'software-attempt'), (None, '')):
            passed = {'prepared_step': step, 'prepared_attempt': attempt}
            passed = {name: value for name, value in passed.items() if name in supported}
            with patch.object(runner, 'ToolContext', return_value=object()) as constructor, \
                    patch.object(prepared, 'open_linux_helper_object') as opening, \
                    patch.object(scope, '_attach') as attaching, \
                    patch.object(view, '_bind_attempt') as binding:
                runner._make_ctx(self.session.workspace_root, self.sandbox,
                    policy=self.policy, workspace_session=self.session, **passed)
            expected = dict(old)
            if step is not None or attempt is not None:
                expected.update(prepared_step=step, prepared_attempt=attempt)
            self.assertEqual(constructor.call_args.kwargs, expected)
            opening.assert_not_called()
            attaching.assert_not_called()
            binding.assert_not_called()
        kwargs = dict(policy=self.policy, workspace_session=self.session)
        kwargs.update({name: value for name, value in
            (('prepared_step', view), ('prepared_attempt', 'software-attempt'))
            if name in supported})
        actual = runner._make_ctx(self.session.workspace_root, self.sandbox, **kwargs)
        self.assertIs(getattr(actual, 'prepared_step', None), view)
        self.assertEqual(getattr(actual, 'prepared_attempt', None), 'software-attempt')

    def test_none_exact_resource_kwargs_with_output_and_cache(self):
        ctx = self.context()
        cache = self.session.workspace_root / 'cache'
        for output in (None, 900):
            for directory in (None, cache):
                with self.subTest(output=output, cache=directory):
                    with patch.object(builtin, 'execute_linux_resource_observed_command') as entry:
                        self.dispatch(ctx, output_limit_bytes=output,
                            verification_cache_root=directory)
                    expected = dict(cwd=self.session.workspace_root, sandbox=self.sandbox,
                        policy=self.policy, timeout=1,
                        command_wrapper=ctx.wrap_command_with_resource_receipt)
                    if output is not None:
                        expected['output_limit_bytes'] = output
                    if directory is not None:
                        expected['verification_cache_root'] = directory
                    self.assertEqual(entry.call_args.kwargs, expected)

    def test_none_exact_ordinary_kwargs_and_cache_refusal(self):
        ctx = self.context(sandbox=object())
        for output in (None, 900):
            with patch.object(ctx, 'wrap_command', return_value=['wrapped']) as wrapper, \
                    patch.object(builtin, 'execute_policy_command') as entry, \
                    patch.object(builtin, 'execute_linux_resource_observed_command') as resource:
                self.dispatch(ctx, output_limit_bytes=output)
            expected = dict(cwd=self.session.workspace_root, policy=self.policy, timeout=1)
            if output is not None:
                expected['output_limit_bytes'] = output
            self.assertEqual(entry.call_args.kwargs, expected)
            self.assertEqual(entry.call_args.args, (['wrapped'],))
            wrapper.assert_called_once()
            resource.assert_not_called()
        with patch.object(ctx, 'wrap_command') as wrapper, \
                patch.object(builtin, 'execute_policy_command') as entry:
            with self.assertRaises(IsolationUnavailable):
                self.dispatch(ctx, verification_cache_root=self.session.workspace_root / 'cache')
        wrapper.assert_not_called()
        entry.assert_not_called()

    def test_valid_dispatch_forwards_three_keywords_once_no_ordinary(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        ctx = self.context(view, 'software-attempt')
        with patch.object(builtin, 'execute_linux_resource_observed_command') as entry, \
                patch.object(builtin, 'execute_policy_command') as ordinary, \
                patch.object(view, 'borrow') as borrowing:
            self.dispatch(ctx)
        expected = dict(cwd=self.session.workspace_root, sandbox=self.sandbox,
            policy=self.policy, timeout=1, command_wrapper=ctx.wrap_command_with_resource_receipt,
            prepared_step=view, workspace_session=self.session,
            prepared_attempt='software-attempt')
        self.assertEqual(entry.call_args.kwargs, expected)
        entry.assert_called_once()
        ordinary.assert_not_called()
        borrowing.assert_not_called()

    def test_shape_and_mutated_context_reject_before_all_dispatch_calls(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        cases = [dict(prepared_step=None, prepared_attempt='software-attempt'),
            dict(prepared_step=None, prepared_attempt=''),
            dict(prepared_step=scope), dict(prepared_step=object()),
            dict(workspace_session=None), dict(workspace_session=object()),
            dict(read_only_workspace=True), dict(sandbox=object())]
        cases.extend(dict(prepared_attempt=value) for value in
            (None, '', ' ', True, 1, 'bad\nvalue', 'bad\x7fvalue'))
        for change in cases:
            with self.subTest(change=tuple(change)):
                ctx = self.context(view, 'software-attempt')
                for name, value in change.items():
                    setattr(ctx, name, value)
                with patch.object(ctx, '_policy_command_wrapper') as binding, \
                        patch.object(ctx, 'wrap_command') as wrapper, \
                        patch.object(builtin, 'execute_linux_resource_observed_command') as resource, \
                        patch.object(builtin, 'execute_policy_command') as ordinary, \
                        patch.object(factory, 'open_linux_helper_object') as opening, \
                        patch.object(broker, '_execute_policy_command') as payload:
                    with self.assertRaises(IsolationUnavailable) as caught:
                        self.dispatch(ctx)
                self.assertEqual(str(caught.exception), '准备对象工具上下文不可用')
                self.assertIsNone(caught.exception.__cause__)
                for spy in (binding, wrapper, resource, ordinary, opening, payload):
                    spy.assert_not_called()

    def test_wrong_identity_view_and_attempt_reach_unique_borrow_gate(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        other_scope = self.prepare()
        other_view = self.bind(self.attach(other_scope))
        # Well-shaped but genuinely stale view; helper/session remain active.
        other_view.finish()
        clone = replace(self.session)
        self.assertEqual(clone, self.session)
        self.assertIsNot(clone, self.session)
        self.assertIs(clone.lease, self.session.lease)
        self.assertIs(clone._workspace_object, self.session._workspace_object)
        cases = ((view, {'workspace_session': clone}),
            (other_view, {}), (view, {'prepared_attempt': 'other-attempt'}))
        for target, changes in cases:
            with self.subTest(changes=tuple(changes), stale=target is other_view):
                original = target.borrow
                with patch.object(target, 'borrow', wraps=original) as borrowing, \
                        patch.object(builtin, 'execute_policy_command') as ordinary, \
                        patch.object(builtin, 'execute_linux_resource_observed_command',
                            wraps=broker.execute_linux_resource_observed_command) as entry:
                    answer, error, events = self.exercise(True, target, changes=changes)
                entry.assert_called_once()
                borrowing.assert_called_once()
                ordinary.assert_not_called()
                self.assertIsNone(error)
                self.assertEqual(answer.error, 'isolation_unavailable')
                self.assertIs(answer.payload_started, False)
                self.assertEqual(events, [])
        self.assertEqual(scope._consume_state, 'attached_bound')
        self.session.lease._validate_active()

    def test_ctx_close_then_two_actual_dispatch_consumptions_owner_lives(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        ctx = self.context(view, 'software-attempt')
        helper_fd = scope._owner.fileno()
        with patch.object(view, 'finish') as finish, patch.object(scope, 'close') as close:
            ctx.close()
        finish.assert_not_called()
        close.assert_not_called()
        self.closed_context = ctx
        original = view.borrow
        for _ in range(2):
            with patch.object(view, 'borrow', wraps=original) as borrowing, \
                    patch.object(builtin, 'execute_policy_command') as ordinary, \
                    patch.object(builtin, 'execute_linux_resource_observed_command',
                        wraps=broker.execute_linux_resource_observed_command) as entry:
                answer, error, events = self.exercise(True, view)
            entry.assert_called_once()
            borrowing.assert_called_once()
            ordinary.assert_not_called()
            self.assertIsNone(error)
            self.assertIsNone(answer.error)
            self.assertEqual(self.owners, [scope._owner])
            self.assertIn('launch', events)
            self.assertIn('scope_close', events)
            self.assertEqual(scope._consume_state, 'attached_bound')
            self.assertFalse(scope._inflight)
            self.assertEqual(scope._owner_state, 'active')
            os.fstat(helper_fd)
            os.fstat(self.session.workspace_fd)
            self.session.lease._validate_active()
        # External fixture creator alone ends eligibility and owns final close.
        view.finish()
        self.assertEqual(scope._consume_state, 'spent')
        os.fstat(helper_fd)
        scope.close()
        self.assertEqual(scope._owner_state, 'closed')
        with self.assertRaises(OSError):
            os.fstat(helper_fd)
        os.fstat(self.session.workspace_fd)
        self.session.lease._validate_active()


if __name__ == '__main__':
    unittest.main()
~~~

- [x] **Step 3：测试作者运行新模块，保存实际 assertion RED；root 独立重复同命令。**

~~~bash
.venv/bin/python -B -m unittest tests.test_linux_prepared_tool_context -v
~~~

预期旧 SOURCE 的字段存在、constructor 转发、三 keyword、固定前门和真实消费断言失败；不得以 missing-keyword TypeError、缺依赖、收集错误、fixture failure 或 skip 记有效 RED。先核 baseline target assertions 与 0 errors/skip。若 fixture/测试有真实问题返回 PLAN 修订并双审，不能先改 SOURCE 将其隐藏。root 保存每次原输出、SHA、F/E/skip与具体目标断言。

### Task 2：不同 fresh SOURCE 作者应用唯一最小六 hunk 差分

**状态**

- [x] 任务完成

**Dependencies:** Task 1
**Parallelizable:** No (正式双 RED 已取证；作者不同；不触旧 tests)

- [x] **Step 1：SOURCE ONLY 作者核冻结 test SHA 与三基线，apply_patch 等价应用以下唯一差分。**

~~~diff
--- a/src/icode/tools/base.py
+++ b/src/icode/tools/base.py
@@ -21,6 +21,7 @@
-
+
 if TYPE_CHECKING:
     from ..linux_helper_object import LinuxHelperObject
+    from ..linux_prepared_step import _LinuxStepAttachment
-
+
 # 工具输出回灌模型时的字符上限（渐进披露原则：不要把大段正文塞回上下文）
 DEFAULT_OUTPUT_LIMIT = 8000
@@ -94,6 +95,12 @@
     # None preserves ordinary workspace/policy behavior; an empty tuple denies
     # every file read.
     allowed_read_files: tuple[Path, ...] | None = None
+    prepared_step: _LinuxStepAttachment | None = field(
+        default=None, kw_only=True, repr=False,
+    )
+    prepared_attempt: str | None = field(
+        default=None, kw_only=True, repr=False,
+    )
     _pinned_read_only_workspace: object | None = field(
         default=None, init=False, repr=False,
     )
--- a/src/icode/runner.py
+++ b/src/icode/runner.py
@@ -2178,8 +2178,13 @@
     deny_read_roots: tuple[Path, ...] = (),
     allowed_read_files: tuple[Path, ...] | None = None,
     workspace_session: WorkspaceSession | None = None,
+    prepared_step: object | None = None,
+    prepared_attempt: str | None = None,
 ) -> ToolContext:
     """构造工具上下文；未显式指定时按本机实测能力自动选隔离后端。"""
+    options = {}
+    if prepared_step is not None or prepared_attempt is not None:
+        options = {"prepared_step": prepared_step, "prepared_attempt": prepared_attempt}
     return ToolContext(
         root=workspace, sandbox=sandbox if sandbox is not None else select_sandbox(),
         policy=policy, artifact_broker=artifact_broker,
@@ -2188,6 +2193,7 @@
         deny_read_roots=deny_read_roots,
         allowed_read_files=allowed_read_files,
         workspace_session=workspace_session,
+        **options,
     )
-
-
+
+
--- a/src/icode/tools/builtin.py
+++ b/src/icode/tools/builtin.py
@@ -746,6 +746,24 @@
     except (OSError, RuntimeError, TypeError, ValueError):
         raise IsolationUnavailable("工单执行目录与策略绑定不一致") from None
     resource_dispatch = _uses_resource_dispatch(ctx)
+    # Only shape is checked here; the existing broker is the sole borrower.
+    prepared_options = {}
+    if ctx.prepared_step is not None or ctx.prepared_attempt is not None:
+        if not resource_dispatch or ctx.read_only_workspace:
+            raise IsolationUnavailable("准备对象工具上下文不可用") from None
+        from ..linux_prepared_step import _LinuxStepAttachment
+
+        attempt = ctx.prepared_attempt
+        if (not isinstance(ctx.prepared_step, _LinuxStepAttachment)
+                or not isinstance(ctx.workspace_session, WorkspaceSession)
+                or type(attempt) is not str or not attempt.strip()
+                or any(ord(char) < 32 or ord(char) == 127 for char in attempt)):
+            raise IsolationUnavailable("准备对象工具上下文不可用") from None
+        prepared_options = {
+            "prepared_step": ctx.prepared_step,
+            "workspace_session": ctx.workspace_session,
+            "prepared_attempt": attempt,
+        }
     if require_resource and (ctx.read_only_workspace or not resource_dispatch):
         raise IsolationUnavailable("当前边界未提供宿主工程检查所需的单任务资源回执")
     if verification_cache_root is not None and not resource_dispatch:
@@ -764,7 +782,7 @@
         return execute_linux_resource_observed_command(
             argv, cwd=workdir, sandbox=ctx.sandbox, policy=ctx.policy,
             timeout=timeout, command_wrapper=ctx.wrap_command_with_resource_receipt,
-            **options,
+            **options, **prepared_options,
         )
     try:
         prepared = ctx.wrap_command(argv)
~~~

字段只在 TYPE_CHECKING 引入 Linux 类型，旧11 positional不变，None 不新增 constructor/broker kwargs。形状门仅实际 dispatch，真实 lease/identity/attempt资格由已有 borrow 核；不捕获 TypeError重试，不输出输入/FD/路径/异常正文。runner局部止于 `_make_ctx`，不接 invocation、`_run_agent`、CP/Reviewer/resume/engineering 生命周期。`ctx.close` 原方法不动。`policy=None` 的 `run_command` wrap 与工程 `_execute_check` bounded-output旧入口仍未经过此门，不能宣传为已阻断或授准备对象信用；S2b独立设计其前置门与负控。

- [x] **Step 2：新模块 GREEN 后跑有限回归，保存实际结果和 SOURCE/test SHA。**

~~~bash
.venv/bin/python -B -m unittest tests.test_linux_prepared_tool_context -v
CMAKE_BUILD_PARALLEL_LEVEL=1 MAKEFLAGS=-j1 .venv/bin/python -B -m unittest tests.test_tools tests.test_runner tests.test_engineering_verification tests.test_contract_engineering tests.test_linux_contract_engineering tests.test_linux_workspace_fd tests.test_linux_prepared_step tests.test_linux_prepared_broker tests.test_linux_channel_factory_cleanup tests.test_linux_scope_temporary_cleanup -v
git diff --check
sha256sum src/icode/tools/base.py src/icode/tools/builtin.py src/icode/runner.py tests/test_linux_prepared_tool_context.py
~~~

新模块必须0F/E/skip；有限既有平台 skip逐项说明，不把skip授Linux能力；任何新失败先定位、返回PLAN而非扩到旧tests/broker修补。SOURCE作者只报告，不能跑完整guard/改DESIGN/live/提交/启动下一作者。

### Task 3：fresh 实际 SOURCE 双审、root唯一完整预检与最终文档门

**状态**

- [x] 任务完成

**Dependencies:** Task 2
**Parallelizable:** No (先实际 SOURCE SPEC，再不同 QUALITY，SOURCE/test冻结)

- [x] **Step 1：root 按 frozen SOURCE/test SHA 先独立 SPEC 后不同 QUALITY；每位直接读实际文件、DESIGN/PLAN与原日志，分别输出C/I/M及实证。**

SPEC核七路径、六hunk、字段/kwargs shape、真实dispatch消费、目标负控不被其它早门代替、None/Reviewer/非resource/漂移边界与不授S2b信用；QUALITY核异常固定错误、旧callback兼容、owner/borrow/FD收尾、测试collection及fixture前提。两者各自运行新模块同命令，保存输出；任何遗留返回PLAN/作者最小修补，改SOURCE/test后撤销旧审查和完整门信用，重取两审，不自动复用。两位都C0/I0/M0后才下一步。

- [x] **Step 2：root 以新冻结SHA只运行一次原完整guard，编译最多j1。**

~~~bash
validation_log_dir=$(mktemp -d /tmp/icode-s2a-preflight.XXXXXX)
script -q -e -f -c 'CMAKE_BUILD_PARALLEL_LEVEL=1 MAKEFLAGS=-j1 .venv/bin/python -B -u scripts/preflight.py' "$validation_log_dir/typescript"
~~~

保存started/done UTC、原日志路径/footer、三门与实际exit；不猜原入口未输出测试数量、不改入口或降门。过程中60秒内更新进展，短轮询、不第二个完整guard、不取消尚未取终态运行；SOURCE/test冻结，仅root如实补文档。B2 guard96748不是本片guard。

- [x] **Step 3：root 以apply_patch只追加真实DESIGN/PLAN实施证据，并按固定OpenHands窗口更新live采纳/暂缓/不适配；最终文档原scanner两轮与fresh单门。**

~~~bash
.venv/bin/python -B /home/orbbec/.agents/skills/doc-contract-consistency-audit/scripts/check_consistency.py docs/nbl/plans/2026-10-12-linux-prepared-tool-context.md docs/nbl/specs/2026-10-12-linux-prepared-tool-context-design.md docs/agent-landscape-live.md
.venv/bin/python -B /home/orbbec/.agents/skills/doc-contract-consistency-audit/scripts/check_consistency.py docs/nbl/plans/2026-10-12-linux-prepared-tool-context.md docs/nbl/specs/2026-10-12-linux-prepared-tool-context-design.md docs/agent-landscape-live.md
.venv/bin/python -B scripts/preflight.py --only secrets
.venv/bin/python -B scripts/preflight.py --only submodule
git diff --check
~~~

每轮原scanner raw finding0/exit0，无whitelist/修改scanner；若文档再变重做两轮及单门。只核密钥门结果，不读取外部凭据正文；vendor不变。报告真实RED/GREEN、回归F/E/skip、源码摘要、两审、原fullguard、有限信用；审批DESIGN原摘要与追加证据的新摘要分别记录，不冒称相同字节。无模型KEY/CP/installed/native/Windows/macOS/R2/R3整体验收。

### Task 4：root精确七路径index核验、一次main提交与推送

**状态**

- [ ] 任务完成

**Dependencies:** Task 3
**Parallelizable:** No (全部证据终态、最终文档字节冻结后)

发布前收齐当前基线 `60325a4` 的 CI、provenance、Pages 三个 workflow 的终态及原始日志，登记 ARM 超时分类异常与 Windows Reviewer 失败的真实结果。不取消运行、不以旧绿色推断本批，不要求本片顺带修改 CI 或旧源码。

- [ ] **Step 1：root核index初始为空，记录七路径工作SHA，精确stage并核路径集合和每个index字节。**

~~~bash
git diff --cached --name-only
sha256sum src/icode/tools/base.py src/icode/tools/builtin.py src/icode/runner.py tests/test_linux_prepared_tool_context.py docs/nbl/specs/2026-10-12-linux-prepared-tool-context-design.md docs/nbl/plans/2026-10-12-linux-prepared-tool-context.md docs/agent-landscape-live.md
git add src/icode/tools/base.py src/icode/tools/builtin.py src/icode/runner.py tests/test_linux_prepared_tool_context.py docs/agent-landscape-live.md
git add -f docs/nbl/specs/2026-10-12-linux-prepared-tool-context-design.md docs/nbl/plans/2026-10-12-linux-prepared-tool-context.md
git diff --cached --check
git diff --cached --name-only | sort | diff - <(printf '%s\n' src/icode/tools/base.py src/icode/tools/builtin.py src/icode/runner.py tests/test_linux_prepared_tool_context.py docs/nbl/specs/2026-10-12-linux-prepared-tool-context-design.md docs/nbl/plans/2026-10-12-linux-prepared-tool-context.md docs/agent-landscape-live.md | sort)
for path in src/icode/tools/base.py src/icode/tools/builtin.py src/icode/runner.py tests/test_linux_prepared_tool_context.py docs/nbl/specs/2026-10-12-linux-prepared-tool-context-design.md docs/nbl/plans/2026-10-12-linux-prepared-tool-context.md docs/agent-landscape-live.md; do
    git show ":$path" | cmp -s "$path" - || exit 1
done
git diff --cached --stat
~~~

任何其它stage路径或字节不符立即停止，不reset/覆盖用户改动。母设计/vendor/CI不能入index；确认main与root阶段发布授权仍有效。本task命令只由root在实际门均满足后执行，writer无GIT写权限。

- [ ] **Step 2：root在当前main一次commit/push并只读核remote同SHA。**

~~~bash
git commit -m "feat(linux): adapt prepared attachment tool context"
git push origin main
git rev-parse HEAD
git ls-remote origin refs/heads/main
git status --short
~~~

预期remote完整SHA=实际HEAD，本片无未提交遗留；不预写提交SHA、不force、不删分支。后续同SHA CI只读取终态，不能替本片本地RED/完整guard或安装包证据。S2b需独立设计/计划审查；已有持续开发授权保持有效，仅必要扩权时询问。本writer不能从本PLAN自动展开。

## writer内置自审与七维有限报告

writing-plans自审：规格每项映射到Task1资产、Task2六hunk、Task3审查/门、Task4七路径发布；无占位code或未定义方法；S1/S1c真实fixture符号已核，覆盖call而不绕实际dispatch。类型/命名一致，CODE阶段无SOURCE/TEST落盘。执行复杂且依赖纯链，判定serial；用户main-only及root的DOCS ONLY/STOP覆盖技能自动handoff建议。writer停止后root另做fresh PLAN SPEC→不同QUALITY，不能把内置自审替独立审查。

writer实际资产诊断（仅RAM，不授正式TDD）：严格逐行核原上下文、各hunk旧/新行数和三基线投影，实际6个hunk，测试资产及三投影SOURCE compile成功。最终测试资产在未改磁盘SOURCE上RAM运行8个测试、22个assertion failure（含subtest）、0error/skip；字段存在、kwargs转发、shape门与factory禁止目标都真实失败，无constructor缺keyword错误作RED。RAM投影后8个测试0F/E/skip、0.451s。初次诊断的RAM module重载遗漏`icode.tools`package导出，曾出现1个旧ToolContext constructor TypeError；修正RAM依赖加载顺序后消失，属诊断脚手架，不记作有效RED或生产修复。磁盘SOURCE/TEST均未写；正式双RED、GREEN、回归/审查/完整门仍待root GO。

| 完整资产或投影 | SHA256 |
| --- | --- |
| Task1完整Python测试fence（末尾换行计入） | `8579198d90435cf16d4a51359e6f8f936a55531782954788dd56c077bde20e0c` |
| Task2完整六hunk unified-diff fence（末尾换行计入） | `dbb2a276e386dc0ec0b1e53ed4b1a01d3cba309fc322793fe7165443559b9a45` |
| RAM base.py完整投影 | `9961e4638e7521ef619d52d097632fc1683682bd1e779200f3e7f18c8c6df4f7` |
| RAM builtin.py完整投影 | `04c1fe57f86bb2d622398e8324e518e653b5c3db656683ee6f0f0ff8f068a49c` |
| RAM runner.py完整投影 | `56abe98e31f02cc96327a364c52ace9aef5b7c60e6594025058e2de48f15a63d` |

【架构级自检报告】（PLAN资产范围）

- 语法/编译：完整测试及三SOURCE资产RAM compile/严格六hunk投影通过；生产源码未改。
- 依赖/调用链：字段→_make_ctx→真实dispatch→现有公共resource broker→唯一borrow，未新建owner核。
- 逻辑/边界：旧11 positional、全None精确kwargs、形状与漂移、真实session/view/attempt负控逐项断言。
- 异常处理：固定输入无关拒绝；无TypeError降级；既有broker错误合同保持。
- 关联模块：七路径明确，runner仅_make_ctx，旧policyNone入口事实保留。
- 兼容安全：无依赖/模型参数/权限/新执行通道；ctx.close不结束借用owner。
- 可运行性：只授计划资产诊断，正式双RED/GREEN、回归、SOURCE双审及原完整guard待GO后执行，不报告100%。

---
**Execution Mode:** serial

## root实际执行证据（2026-10-12，S2a有限片）

批准PLAN8f8eca00/DESIGN1f6405a2均经独立SPEC与不同QUALITY零遗留。正式TEST8579198d先落盘：作者/root新8方法22有效assertFAIL/0E/skip、exit1（0.451s/0.474s），原三SOURCE未改；不同作者随后仅六hunk，实际三投影摘要与上表吻合。作者/root新8GREEN（0.459s/0.462s），限定333tests/6skip（121.139s/118.790s）均0F/E；compileall-j1/site/governance/diff通过。六skip为旧macOS zombie1、Windows Job/pipe3、显式CI Reviewer1、Go工具链1，不授能力。

fresh实际SOURCE SPEC C0/I0/M0，独立新8/0.444s及相关50/3.164s均0F/E/skip；不同QUALITY C0/I0/M0，独立新8/0.447s及相关89/3.366s均0F/E/skip。root唯一原完整guard session98093、日志 `/tmp/icode-s2a-preflight.1jqDuD/typescript`，07:13:02 UTC已观察启动、j1，尚未返回，不预授完整门或发布。

root提前只读检查发现新PLAN补丁示例四处空context行尾随空格；仅等价改为删除/添加空行。完整diff新摘要dbb2a276，root实际严格核六hunk上下文/旧新行数/位置，三个投影仍与当前冻结SOURCE逐字节相等；测试和SOURCE未变。原46d1c4f5是审查时资产的历史摘要，不冒称当前字节。发布仍需最终scanner两轮、单门与七index bytes/cached检查。

当前基线60325a4三workflow全部终态原日志已收，root核同SHA完整jobs：CI38213836897=40success/3failure/3skip，provenance38213837130=5/5success，Pages38213836941=2/2success。双Python各3184/86skip；ARM旧timeout误分类与Windows双Reviewer网络/WFP失败独立保留。签装owner_untrusted且protected/compatibility/launchfalse，不授产品启动；没有取消或重跑。S2a只授薄适配软件信用，真实runner/CP、legacy前门、S2b/S3及installed/native/整体验收仍待。

root原唯一完整guard98093现实际exit0，日志footer07:22:27 UTC，root07:23:18 UTC取得三门PASS；原入口未输出测试数量，不猜总计。四SOURCE/test冻结摘要再次一致。Task3最终文档双scanner/fresh单门及Task4七路径index/发布仍待，不预写SHA或提交结果。上述“尚未返回”为启动时历史记录。

最终三文档原scanner两轮各raw0/exit0，fresh secrets/submodule单门均PASS。此完成记录后再次对最终字节执行相同两轮及单门，再核七路径index/工作bytes及cached whitespace门；任一失败都禁止发布。Task4不提前勾完成，实际main/remote SHA由发布后live记录，不预填。

writer完成即STOP；不调用执行技能、不启动测试/源码作者、不跑fullguard/读取KEY/写GIT。
