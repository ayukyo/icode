# Linux Resource Runtime Deadline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development (recommended) or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking. 本 writer 仅 DOCS ONLY；S2a 真实发布、root fresh PLAN 双审及另发 GO 前禁止 TEST/SOURCE 落盘，完成后 STOP，不自动 handoff。

**Goal:** 保存真实 resource worker 已确认的运行截止事实，在 core 无错误的 EOF/退出竞争中恢复 timeout，不推断历史原生根因。

**Architecture:** receiver 私有、锁保护、sticky bool 与所有 stop 写入共用线性化点；kill/join 保留锁外。outer 仅 core error None 且事实 is True 补 timeout，沿用原 observer/terminal/cleanup 优先级，不扩 preserved_errors。

**Tech Stack:** Python 3.11+、unittest、真实 Linux recvmsg/SCM_CREDENTIALS/CONFIGURED ACK、socket、child/pipe 与既有 prepared/session 软件夹具；无新依赖或权限。

---

## 批准合同、冻结线与范围

批准 [DESIGN](../specs/2026-10-12-linux-resource-runtime-deadline-design.md) SHA256 d31876bfa2c6ba87ea1bdfb1e27dab27a20b35d65876eabc2caf99cec5bdd24d，fresh SPEC 与不同 QUALITY 均 C0/I0/M0。三问已确认：真实 worker 到期会 kill，但原因可在 core EOF/退出竞争中丢失；复用原 receiver 锁和 broker 收尾，不更改 process core 完成观察合同。

writer 开始时 main60325a4、S2a 唯一 guard98093 正在运行，S2a 四 SOURCE/test 冻结。下列两 SOURCE 与 DESIGN 字节实核，未改；实施前 root 必须核 S2a 真正发布后的实际 HEAD/remote 和三 workflow 终态，不预填未来 SHA，不把本 RAM 当正式 RED。

root 随后实际完成 S2a 原完整 guard exit0、最终文档两轮 scanner/单门及七 index 字节核验，提交推送 main01e22a43198f3eb4d2770b4f2940da13bc71697f，远端同 SHA、工作树 clean；两 SOURCE 基线未变。本片正式实施基线为这一真实 SHA；新 CI/provenance/Pages 仍在 GET 观察，下一 push 前必须全部同 SHA 终态并取得原日志。此事实不撤销本 PLAN fresh 双审及 root GO 的暂停线。

| 路径 | 基线 SHA256 / 职责 |
| --- | --- |
| src/icode/linux_task_resource.py | f75932afa50ab6bc82af9a4019211d3ec22b535a6594565dd2189cc99e65a217；私有事实和 stop 共锁 |
| src/icode/execution_broker.py | 3212f07039ceb72435b92bef0ade2c1f62ec0ea6452b55a53334e9401d321ca9；收尾后、observer 分类前 None 补记 |
| tests/test_linux_resource_runtime_deadline.py | 新建；完整资产见 Task 1 |
| docs/nbl/specs/2026-10-12-linux-resource-runtime-deadline-design.md | 批准字节；root 最后只追加实际证据 |
| docs/nbl/plans/2026-10-12-linux-resource-runtime-deadline.md | 本文；操作/资产/证据 |
| docs/agent-landscape-live.md | root 更新研究取舍与有限结论 |

仅六发布路径。process core、旧 tests、scope/attachment、runner/ToolContext、S2a docs、native/vendor/CI 只读。main-only，不创建 branch/worktree；用户和 root 边界覆盖 skill 的 worktree/频繁分散 commit/自动 handoff 建议。TEST 作者、不同 SOURCE 作者、fresh SOURCE SPEC、不同 QUALITY 依序，root 唯一完整 guard 和一次 main commit/push。

复用 DESIGN 真实源码 GET 2026-10-12 06:56:37–06:56:40 UTC、LICENSE 06:57:35–06:57:39 UTC：固定 [Codex27065a91 exec 分账](https://github.com/openai/codex/blob/27065a91ccbf5ba8532844be3777fcf83b77820d/codex-rs/core/src/exec.rs#L1017-L1075)（Apache-2.0）及 [CPython v3.11.15 select 后截止检查](https://github.com/python/cpython/blob/v3.11.15/Lib/subprocess.py#L2105-L2116)（PSF-2.0）。采纳独立结束原因；暂缓 core 完成观察和历史 ARM 因果结论；不适配 -9/EOF/晚观察自证到期。未刷新 HEAD/二十名单、未复制代码或新增依赖。

### Task 1：fresh TEST 作者与 root 正式 RED

**状态**

- [x] 任务完成

**Dependencies:** None（先满足 S2a 发布、PLAN 双审及 root GO）
**Parallelizable:** No (TEST ONLY 与 root RED 后才 SOURCE)

- [x] **Step 1：root 只读核 main/index 和基线。**

~~~bash
git branch --show-current
git rev-parse HEAD
git status --short
git diff --cached --name-only
sha256sum src/icode/linux_task_resource.py src/icode/execution_broker.py docs/nbl/specs/2026-10-12-linux-resource-runtime-deadline-design.md
~~~

预期 main/index 空、两 SOURCE 和 DESIGN 符合表值；实际 S2a HEAD/remote 及三 workflow 终态另记。漂移须返回 PLAN 重核上下文/双审，不 reset 用户文件或套旧投影。

- [x] **Step 2：fresh 作者以 apply_patch 只新建完整 TEST。**

夹具仅复用 PreparedTests 在新建隔离临时目录的 git init/add/commit；root 已精确澄清允许此软件 fixture，不触本仓库/子仓库/用户目录 Git。实际 helper/session/lease/borrow 和公共 broker 保持；原 held wrapper before_spawn 先真正核验，随后测试 launcher seam 把 native/systemd argv 换成隔离 Python child，再调原 core。scope/systemd、seccomp monitor 是既有 doubles，不授原生/payload成功/installed信用。

receiver 构造、真实 worker/_receive、recvmsg/凭据、CONFIGURED callback/ACK 均未替换。线程路由真实 selector：core 在同一次 select 收齐真实 stdout/stderr 两个 EOF readiness（逐个实际读到空字节，重复读取EOF不消费数据），保留原 registered keys至真实worker kill/reap后再交回原core读取；worker 确认真正configured之后才等 EOF 屏障，再以 Event.wait 等实际单调 deadline，返回空 readiness，让生产循环实采样、在 _fail kill 前记事实。首轮worker空readiness和core轮询拖过截止点均有负控，不把get_map清空后才等待当作可靠同步。无假时钟/手设正例 fact/__new__/直接_fail/sleep猜竞争。5秒收齐/屏障是卫生上限而非产品时限；不增大原0.3秒fixture运行时限。truthy property patch 只 strict-bool 负控；core_error replace 只是错误选择 seam，不声称实际触发五类 core 故障。

~~~python
"""Real receiver/runtime facts; software launch seam, no native credit."""
from __future__ import annotations
from contextlib import ExitStack
from dataclasses import replace
import os
import selectors
import socket
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

LINUX = sys.platform.startswith("linux") and callable(getattr(os, "pread", None))
if LINUX:
    from tests import test_linux_prepared_step as fixture
    from tests import test_linux_prepared_broker as forwarding
    from tests import test_linux_helper_dispatch as dispatch
    from icode import execution_broker as broker
    from icode import linux_task_resource as resource
    from icode import linux_task_scope as scopes
    from icode import linux_seccomp_notify as seccomp
    from icode import linux_helper_object as factory

CHILD = r"""
import os, socket, struct, sys
sender = socket.socket(fileno=int(sys.argv[1]))
mode = sys.argv[2]
nonce = bytes.fromhex("0123456789abcdef0123456789abcdef")
limit = int(sys.argv[3])
frame = lambda phase: b"ICQR1" + bytes([phase]) + nonce + struct.pack("!I", limit)
sender.send(frame(1))
ack = sender.recv(64)
assert ack == b"ICQA1" + nonce + struct.pack("!I", limit)
if mode == "finished":
    sender.send(frame(3))
    sender.close()
elif mode == "preexec":
    sender.send(frame(2))
    sender.close()
elif mode == "cleanup":
    sender.send(frame(4))
    sender.close()
elif mode == "early":
    sender.close()
elif mode == "bad":
    sender.send(b"bad")
    sender.close()
else:
    os.close(1)
    os.close(2)
    sender.recv(1)
"""

@unittest.skipUnless(LINUX, "Linux real-resource software tests; skip is not acceptance")
class RuntimeDeadlineTests(unittest.TestCase):
    if LINUX:
        setUp = fixture.PreparedTests.setUp
        write_image = fixture.PreparedTests.write_image
        precheck_fixture = fixture.PreparedTests.precheck_fixture
        cleanup_scopes = fixture.PreparedTests.cleanup_scopes
        prepare = fixture.PreparedTests.prepare
        attach = fixture.PreparedTests.attach
        bind = fixture.PreparedTests.bind
        borrow = fixture.PreparedTests.borrow
        wrapper = forwarding.PreparedBrokerTests.wrapper

    def run_chain(self, mode="timeout", *, core_error=None, observer_failed=False,
                  resource_close_unknown=False, close_wins=False, external_kill=False,
                  configured_failure=False, configured_expiration=False, fake_fact=None,
                  initial_empty_readiness=False, core_empty_readiness=False):
        self.owners = []
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        task = dispatch.Scope()
        task.configured = lambda deadline: None
        if configured_failure:
            def configured(deadline):
                raise RuntimeError("fixed callback fixture")
            task.configured = configured
        if configured_expiration:
            def configured(deadline):
                threading.Event().wait(max(0, deadline - time.monotonic()) + 0.001)
            task.configured = configured
        monitor = dispatch.Monitor(None)
        monitor.failed = observer_failed
        originals = dict(selector=selectors.DefaultSelector,
                         core=broker._execute_policy_command,
                         receiver=resource.LinuxTaskResourceReceiver)
        eof = threading.Event()
        killed = threading.Event()
        release = threading.Event()
        worker_blocked = threading.Event()
        state = dict(receivers=[], processes=[], before_kill=[], core=[], selectors=[], close_threads=[])
        timeout = 0.3 if mode == "timeout" else 3.0

        def complete_eof_barrier():
            eof.set()
            if external_kill:
                state["processes"][0].kill()
            elif close_wins:
                self.assertTrue(worker_blocked.wait(5))
                receiver = state["receivers"][0]
                closer = threading.Thread(target=receiver.close, name="deadline-test-close")
                state["close_threads"].append(closer)
                closer.start()
                self.assertTrue(receiver._stop.wait(5))
                threading.Event().wait(max(0, state["deadline"] - time.monotonic()) + 0.001)
                release.set()
            self.assertTrue(killed.wait(5))

        class RoutedSelector:
            def __init__(inner):
                inner.actual = originals["selector"]()
                inner.worker = threading.current_thread().name == "icode-task-resource"
                inner.calls = 0
                inner.polls = 0
                state["selectors"].append(inner)
            def register(inner, *args, **kwargs):
                return inner.actual.register(*args, **kwargs)
            def unregister(inner, *args, **kwargs):
                return inner.actual.unregister(*args, **kwargs)
            def get_map(inner):
                return inner.actual.get_map()
            def select(inner, timeout=None):
                inner.calls += 1
                if inner.worker and inner.calls == 1 and initial_empty_readiness:
                    return []  # A legal empty poll must not imply CONFIGURED.
                if (inner.worker and mode == "timeout"
                        and state["receivers"][0].receipt()["configured"] is True):
                    worker_blocked.set()
                    self.assertTrue(eof.wait(5))
                    if close_wins:
                        self.assertTrue(release.wait(5))
                    elif external_kill:
                        return inner.actual.select(timeout)
                    else:
                        threading.Event().wait(max(0, state["deadline"] - time.monotonic()) + 0.001)
                    return []
                if not inner.worker and mode == "timeout":
                    process = state["processes"][0]
                    expected = {process.stdout.fileno(), process.stderr.fileno()}
                    self.assertEqual(set(inner.actual.get_map()), expected)
                    ready = {}
                    hygiene_deadline = time.monotonic() + 5
                    while set(ready) != expected:
                        remaining = hygiene_deadline - time.monotonic()
                        self.assertGreater(remaining, 0, "real pipe EOF barrier expired")
                        inner.polls += 1
                        if core_empty_readiness and inner.polls == 1:
                            # Diagnostic empty poll arriving after the actual
                            # deadline; never hand-set a receiver expiry fact.
                            threading.Event().wait(max(0, state["deadline"] - time.monotonic()) + 0.001)
                            events = []
                        else:
                            events = inner.actual.select(min(remaining, 0.05))
                        for key, mask in events:
                            self.assertIn(key.fd, expected)
                            self.assertEqual(os.read(key.fd, 1), b"")
                            ready[key.fd] = (key, mask)
                    # Keep both genuine EOF keys in this core iteration until
                    # the real worker has killed/reaped the real child.
                    complete_eof_barrier()
                    return list(ready.values())
                return inner.actual.select(timeout)
            def close(inner):
                inner.actual.close()

        def received(*args, **kwargs):
            receiver = (originals["receiver"])(*args, **kwargs)
            state["receivers"].append(receiver)
            original_start = receiver.start
            def start(**keywords):
                state["deadline"] = keywords["deadline_monotonic"]
                original_start(**keywords)
            receiver.start = start
            if resource_close_unknown:
                original_close = receiver.close
                def close():
                    original_close()
                    return False
                receiver.close = close
            return receiver

        def core(argv, **keywords):
            # Authenticate the real held wrapper before a software-only argv
            # substitution. No native helper/scope/payload success is claimed.
            keywords.pop("before_spawn")()
            original_spawn = keywords["on_spawn"]
            def spawn(process, deadline):
                state["processes"].append(process)
                original_kill = process.kill
                def kill():
                    receiver = state["receivers"][0]
                    state["before_kill"].append(
                        getattr(receiver, "_runtime_deadline_expired", None))
                    original_kill()
                    process.wait(timeout=5)
                    killed.set()
                process.kill = kill
                original_spawn(process, deadline)
            keywords["on_spawn"] = spawn
            actual = [sys.executable, "-I", "-c", CHILD,
                      str(keywords["pass_fds"][-1]), mode, str(self.policy.process_limit)]
            answer = (originals["core"])(actual, **keywords)
            state["core"].append(answer)
            if core_error is not None:
                answer = replace(answer, error=core_error,
                                 cleanup_ok=core_error != "cleanup_failed")
            return answer

        try:
            with ExitStack() as stack:
                stack.enter_context(patch.object(scopes, "LinuxTaskScope", return_value=task))
                stack.enter_context(patch.object(seccomp, "LinuxSeccompViolationMonitor", return_value=monitor))
                stack.enter_context(patch.object(resource, "LinuxTaskResourceReceiver", side_effect=received))
                stack.enter_context(patch.object(broker, "_execute_policy_command", side_effect=core))
                stack.enter_context(patch.object(selectors, "DefaultSelector", side_effect=RoutedSelector))
                if fake_fact is not None:
                    # Only the classification strict-bool negative uses a
                    # receipt double; real worker positives never set the fact.
                    stack.enter_context(patch.object(originals["receiver"],
                        "_runtime_deadline_expired", property(lambda instance: fake_fact),
                        create=True))
                answer = broker.execute_linux_resource_observed_command(
                    ["/usr/bin/true"], cwd=self.session.workspace_root,
                    sandbox=self.sandbox, policy=self.policy, timeout=timeout,
                    command_wrapper=self.wrapper, prepared_step=view,
                    workspace_session=self.session, prepared_attempt="software-attempt")
            self.assertEqual(len(state["receivers"]), 1)
            self.assertEqual(len(state["processes"]), 1)
            self.assertEqual(len(state["core"]), 1)
            self.assertTrue(any(selector.worker for selector in state["selectors"]))
            self.assertTrue(any(not selector.worker for selector in state["selectors"]))
            self.assertTrue(state["receivers"][0]._done.is_set())
            self.assertIsNotNone(state["processes"][0].poll())
            self.assertTrue(state["processes"][0].stdout.closed)
            self.assertTrue(state["processes"][0].stderr.closed)
            self.assertFalse(scope._inflight)
            self.assertEqual(scope._owner_state, "active")
            self.session.lease._validate_active()
            self.assertTrue(os.fstat(self.session.workspace_fd))
            return answer, state, scope, view
        finally:
            release.set()
            eof.set()
            for process in state["processes"]:
                if process.poll() is None:
                    subprocess.Popen.kill(process)
                process.wait(timeout=5)
            for receiver in state["receivers"]:
                receiver.close()
            for closer in state["close_threads"]:
                closer.join(timeout=5)
                self.assertFalse(closer.is_alive())

    def fact(self, state):
        value = getattr(state["receivers"][0], "_runtime_deadline_expired", None)
        self.assertIs(type(value), bool)
        return value

    def test_real_runtime_expiry_precedes_kill_and_repairs_eof_core_race(self):
        answer, state, scope, view = self.run_chain()
        self.assertIsNone(state["core"][0].error)
        self.assertEqual(state["core"][0].exit_code, -9)
        self.assertIs(state["core"][0].cleanup_ok, True)
        self.assertEqual(state["before_kill"], [True])
        self.assertIs(self.fact(state), True)
        self.assertEqual(answer.error, "timeout")
        self.assertEqual(answer.resource_receipt["channel_status"], "incomplete")
        self.assertIs(answer.scope_cleanup_ok, True)
        self.assertEqual(scope._consume_state, "attached_bound")
        self.assertNotIn("runtime_deadline_expired", answer.resource_receipt)
        view.finish()
        self.assertIs(self.fact(state), True)

    def test_timeout_survives_failed_observer_without_new_preserved_errors(self):
        answer, state, scope, view = self.run_chain(observer_failed=True)
        self.assertIsNone(state["core"][0].error)
        self.assertIs(self.fact(state), True)
        self.assertEqual(answer.error, "timeout")
        self.assertEqual(answer.violation_observer_status, "incomplete")

    def test_initial_empty_readiness_waits_for_real_configured_before_barrier(self):
        answer, state, scope, view = self.run_chain(initial_empty_readiness=True)
        self.assertIsNone(state["core"][0].error)
        self.assertEqual(state["core"][0].exit_code, -9)
        self.assertEqual(state["before_kill"], [True])
        self.assertIs(self.fact(state), True)
        self.assertIs(answer.resource_receipt["configured"], True)
        self.assertEqual(answer.error, "timeout")
        self.assertIs(answer.scope_cleanup_ok, True)

    def test_core_empty_readiness_cannot_escape_same_iteration_eof_barrier(self):
        answer, state, scope, view = self.run_chain(core_empty_readiness=True)
        self.assertIsNone(state["core"][0].error)
        self.assertEqual(state["core"][0].exit_code, -9)
        self.assertEqual(state["before_kill"], [True])
        self.assertIs(self.fact(state), True)
        self.assertEqual(answer.error, "timeout")
        self.assertIs(answer.scope_cleanup_ok, True)

    def test_existing_core_errors_are_not_replaced_by_runtime_fact(self):
        for error in ("output_limit", "cleanup_failed", "read_failed",
                      "manager_output_limit", "proxy_setup_failed"):
            for failed in (False, True):
                with self.subTest(error=error, failed=failed):
                    answer, state, scope, view = self.run_chain(
                        core_error=error, observer_failed=failed)
                    self.assertIs(self.fact(state), True)
                    expected = ("violation_observer_failed" if failed and error in
                        ("read_failed", "manager_output_limit", "proxy_setup_failed") else error)
                    self.assertEqual(answer.error, expected)
                    if error == "cleanup_failed":
                        self.assertEqual(scope._consume_state, "faulted")

    def test_complete_and_early_protocol_outcomes_do_not_invent_expiry(self):
        for mode, expected in (("finished", None), ("preexec", "resource_setup_failed"),
                               ("cleanup", "resource_cleanup_failed"),
                               ("early", "resource_channel_failed"), ("bad", "resource_channel_failed")):
            with self.subTest(mode=mode):
                answer, state, scope, view = self.run_chain(mode)
                self.assertIs(self.fact(state), False)
                self.assertEqual(answer.error, expected)
                if mode in ("finished", "preexec", "cleanup"):
                    self.assertEqual(answer.resource_receipt["channel_status"], "complete")
                else:
                    self.assertEqual(answer.resource_receipt["channel_status"], "incomplete")
                if mode == "cleanup":
                    self.assertEqual(scope._consume_state, "faulted")

    def test_external_kill_is_not_runtime_expiry(self):
        answer, state, scope, view = self.run_chain(external_kill=True)
        self.assertIs(self.fact(state), False)
        self.assertEqual(answer.exit_code, -9)
        self.assertEqual(answer.error, "resource_channel_failed")

    def test_configuration_failure_and_cutoff_do_not_invent_expiry(self):
        for cutoff in (False, True):
            with self.subTest(cutoff=cutoff):
                answer, state, scope, view = self.run_chain("finished",
                    configured_failure=not cutoff, configured_expiration=cutoff)
                self.assertIs(self.fact(state), False)
                self.assertEqual(answer.error, "resource_channel_failed")
                self.assertIs(answer.resource_receipt["configured"], False)

    def test_close_linearized_before_runtime_cutoff_does_not_invent_expiry(self):
        answer, state, scope, view = self.run_chain(close_wins=True)
        self.assertTrue(state["receivers"][0]._stop.is_set())
        self.assertGreaterEqual(time.monotonic(), state["deadline"])
        self.assertIs(self.fact(state), False)
        self.assertEqual(answer.error, "resource_channel_failed")

    def test_complete_transcript_cleanup_unknown_remains_faulted_not_timeout(self):
        answer, state, scope, view = self.run_chain("finished", resource_close_unknown=True)
        self.assertIs(self.fact(state), False)
        self.assertEqual(answer.resource_receipt["channel_status"], "incomplete")
        self.assertEqual(answer.error, "resource_channel_failed")
        self.assertEqual(scope._consume_state, "faulted")
        with self.assertRaises(Exception):
            with self.borrow(view):
                pass

    def test_truthy_non_bool_observation_cannot_grant_timeout(self):
        for value in (1, "true", object()):
            with self.subTest(type=type(value).__name__):
                answer, state, scope, view = self.run_chain("early", fake_fact=value)
                self.assertEqual(answer.error, "resource_channel_failed")

    def test_existing_eof_alive_core_path_still_times_out(self):
        with fixture.temp_workspace() as root:
            result = broker._execute_policy_command(
                [sys.executable, "-I", "-c",
                 "import os,time;os.close(1);os.close(2);time.sleep(5)"],
                cwd=root, policy=dispatch.policy_for(root), timeout=0.1,
                manager_stderr=True)
        self.assertEqual(result.error, "timeout")
        self.assertEqual(result.exit_code, -9)
        self.assertIs(result.cleanup_ok, True)

    def test_all_stop_writes_share_receiver_lock(self):
        host, sender = resource.create_task_resource_channel()
        receiver = resource.LinuxTaskResourceReceiver(host,
            unit=dispatch.Scope.unit, limit=2)
        receiver.bind(expected_pid=os.getpid(), expected_uid=os.getuid(),
                      expected_gid=os.getgid())
        actual = receiver._stop
        writes = []
        class Stop:
            def set(inner):
                writes.append(receiver._lock.locked())
                return actual.set()
            def is_set(inner):
                return actual.is_set()
        receiver._stop = Stop()
        try:
            with patch.object(threading.Thread, "start", side_effect=RuntimeError("thread fixture")):
                with self.assertRaises(RuntimeError):
                    receiver.start(deadline_monotonic=time.monotonic() + 1)
            self.assertEqual(writes, [True])
            writes.clear()
            receiver.close()
            self.assertEqual(writes, [True])
        finally:
            host.close()
            sender.close()
~~~

- [x] **Step 3：作者未改两 SOURCE 正式 RED 后 STOP，root 独立重复。**

~~~bash
.venv/bin/python -B -m unittest tests.test_linux_resource_runtime_deadline -v
sha256sum src/icode/linux_task_resource.py src/icode/execution_broker.py tests/test_linux_resource_runtime_deadline.py
~~~

预期13方法/25 assertion failure（含subtest）/0error/skip/exit1；缺精确 bool、kill 前事实与 stop 未共锁是真目标，不以缺模块/TypeError作RED。root 保存完整原输出与实测，不拿期望代实测。core 真 error None/exit-9/cleanup true 是正例先验；失败后的未执行断言不预授。任何错误/挂起或不同前置失败先返回资产审查，不改SOURCE造RED，不跑fullguard/native/installed/模型。

### Task 2：不同 fresh SOURCE 作者、严格六 hunk GREEN

**状态**

- [x] 任务完成

**Dependencies:** Task 1（作者与root有效正式RED）
**Parallelizable:** No (两 SOURCE 可写，TEST 冻结)

- [x] **Step 1：root GO 后不同作者只 apply_patch 下列完整补丁。**

~~~diff
--- a/src/icode/linux_task_resource.py
+++ b/src/icode/linux_task_resource.py
@@ -103,6 +103,7 @@
         self._terminal: int | None = None
         self._complete = False
         self._cleanup_unknown = False
+        self._runtime_expired = False
         self._on_configured = on_configured
-
+
     def bind(self, *, expected_pid: int, expected_uid: int, expected_gid: int) -> None:
@@ -145,7 +146,8 @@
         try:
             worker.start()
         except BaseException:
-            self._stop.set()
+            with self._lock:
+                self._stop.set()
             self._fail()
             raise
-
+
@@ -220,6 +222,11 @@
                 while not self._stop.is_set():
                     remaining = deadline - time.monotonic()
                     if remaining <= 0:
+                        # Linearize expiry against every explicit stop writer.
+                        # Keep kill and worker joins outside the shared lock.
+                        with self._lock:
+                            if not self._stop.is_set():
+                                self._runtime_expired = True
                         raise LinuxTaskResourceError(_ERROR)
                     if not selector.select(min(remaining, 0.05)):
                         continue
@@ -269,6 +276,12 @@
         finally:
             self._done.set()
-
+
+    @property
+    def _runtime_deadline_expired(self) -> bool:
+        """Host-observed runtime expiry, independent of transcript/cleanup."""
+        with self._lock:
+            return self._runtime_expired
+
     def wait(self, *, timeout_seconds: float) -> bool:
         if (
             isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
@@ -278,7 +291,8 @@
         return self._done.wait(timeout_seconds)
-
+
     def close(self) -> bool:
-        self._stop.set()
+        with self._lock:
+            self._stop.set()
         worker = self._thread
         completed = True
         if worker is not None and worker.ident is not None:
--- a/src/icode/execution_broker.py
+++ b/src/icode/execution_broker.py
@@ -713,6 +713,9 @@
         observer_ok = monitor_closed and monitor._started and not monitor.failed
         receipt = monitor.receipt() if observer_ok else None
         error = result.error
+        if error is None and getattr(resource, "_runtime_deadline_expired", False) is True:
+            # Preserve only a worker-confirmed cause; EOF/exit code are not proof.
+            error = "timeout"
         preserved_errors = ("timeout", "output_limit", "cleanup_failed", "invalid_timeout",
                             "invalid_output_limit", "launch_failed")
         candidate_not_started = (helper_object_mode and result.payload_started is False
~~~

严格六 hunk，空 context 行用等价删除/添加空行避免 PLAN whitespace 缺陷；逐行核旧上下文/旧新行数/位置，再核整文件投影，不 fuzzy apply 或改 core。到期重查 stop、两处 stop.set 共 _lock；_fail kill 与 close join 锁外。私有精确 bool 只读/sticky，仅真实运行到期分支写 true；配置/协议/EOF/close 不授事实。旧 double 缺属性按 false，truthy 不授 timeout；None 补记后 preserved_errors/terminal 原样。

- [x] **Step 2：作者新 GREEN、限定回归/语法，root 独立重复。**

~~~bash
.venv/bin/python -B -m unittest tests.test_linux_resource_runtime_deadline -v
CMAKE_BUILD_PARALLEL_LEVEL=1 MAKEFLAGS=-j1 .venv/bin/python -B -m unittest tests.test_linux_task_resource tests.test_linux_resource_cleanup tests.test_linux_helper_dispatch tests.test_linux_prepared_broker tests.test_linux_cleanup_runtime tests.test_linux_channel_factory_cleanup tests.test_execution_broker -v
.venv/bin/python -B -m compileall -q -j 1 src/icode/linux_task_resource.py src/icode/execution_broker.py tests/test_linux_resource_runtime_deadline.py
git diff --check
sha256sum src/icode/linux_task_resource.py src/icode/execution_broker.py tests/test_linux_resource_runtime_deadline.py
~~~

新13须0F/E/skip；既有 skip 逐项说明、不授能力。root 重复新13及限定回归，保存原输出/实际数量。作者只报告、不跑完整guard/改docs/旧tests/提交。

### Task 3：fresh SOURCE 双审与 root 唯一原完整门

**状态**

- [x] 任务完成

**Dependencies:** Task 2
**Parallelizable:** No (先SPEC、不同QUALITY；SOURCE/TEST冻结)

- [x] **Step 1：fresh SPEC、不同 QUALITY 直接读实际文件与原日志，独立执行新13。**

SPEC核runtime实采样、stop线性化、kill/join锁外、None/is True及原错误顺序、六hunk/范围；QUALITY核真实worker/credentials/ACK/child/EOF前提、无手造事实、close先赢/到期先赢sticky、负控、真实faulted及下一borrow拒绝、平台collection和卫生。均C0/I0/M0才下一步。SOURCE/test变更撤销旧审查/guard，重新两审，不继承RAM或旧片信用。

- [x] **Step 2：root 唯一原完整 preflight，j1，记录实际started/done UTC和原footer。**

~~~bash
validation_log_dir=$(mktemp -d /tmp/icode-runtime-deadline-preflight.XXXXXX)
script -q -e -f -c 'CMAKE_BUILD_PARALLEL_LEVEL=1 MAKEFLAGS=-j1 .venv/bin/python -B -u scripts/preflight.py' "$validation_log_dir/typescript"
~~~

源码/TEST冻结；不并跑第二fullguard、不改入口/降门/取消运行，60秒内简短进展/短轮询。只按原输出登记门及exit，不猜未输出总数；S2a guard98093不授本片门。

- [x] **Step 3：root apply_patch只追加真实证据到DESIGN/PLAN/live，再原scanner两轮和fresh单门。**

~~~bash
.venv/bin/python -B /home/orbbec/.agents/skills/doc-contract-consistency-audit/scripts/check_consistency.py docs/nbl/plans/2026-10-12-linux-resource-runtime-deadline.md docs/nbl/specs/2026-10-12-linux-resource-runtime-deadline-design.md docs/agent-landscape-live.md
.venv/bin/python -B /home/orbbec/.agents/skills/doc-contract-consistency-audit/scripts/check_consistency.py docs/nbl/plans/2026-10-12-linux-resource-runtime-deadline.md docs/nbl/specs/2026-10-12-linux-resource-runtime-deadline-design.md docs/agent-landscape-live.md
.venv/bin/python -B scripts/preflight.py --only secrets
.venv/bin/python -B scripts/preflight.py --only submodule
git diff --check
~~~

原scanner每轮raw finding0/exit0，无whitelist/改scanner；文档再变重做。不读外部KEY正文/重试模型401，不改vendor。批准DESIGN摘要与追加事实后摘要分开，不冒称同字节。仅软件分类，不授历史ARM根因/安装/自动准入/R2R3整体验收。

### Task 4：root 六路径 fail-fast index 与一次 main 发布

**状态**

- [ ] 任务完成

**Dependencies:** Task 3
**Parallelizable:** No (全部门及当前基线三workflow终态收齐)

- [ ] **Step 1：root 收实际S2a基线同SHA CI/provenance/Pages终态/原日志，再冻结六路径字节。**

不取消运行/用旧绿或patch猜ARM根因；失败原样登记，不把Windows外部缺口写通过。root确认index初始空、main、现有阶段发布授权及本地门全部满足后才执行：

~~~bash
set -euo pipefail
test "$(git branch --show-current)" = main
test -z "$(git diff --cached --name-only)"
sha256sum src/icode/linux_task_resource.py src/icode/execution_broker.py tests/test_linux_resource_runtime_deadline.py docs/nbl/specs/2026-10-12-linux-resource-runtime-deadline-design.md docs/nbl/plans/2026-10-12-linux-resource-runtime-deadline.md docs/agent-landscape-live.md
git add src/icode/linux_task_resource.py src/icode/execution_broker.py tests/test_linux_resource_runtime_deadline.py
git add -f docs/agent-landscape-live.md docs/nbl/specs/2026-10-12-linux-resource-runtime-deadline-design.md docs/nbl/plans/2026-10-12-linux-resource-runtime-deadline.md
git diff --cached --check
git diff --cached --name-only | sort | diff - <(printf '%s\n' src/icode/linux_task_resource.py src/icode/execution_broker.py tests/test_linux_resource_runtime_deadline.py docs/nbl/specs/2026-10-12-linux-resource-runtime-deadline-design.md docs/nbl/plans/2026-10-12-linux-resource-runtime-deadline.md docs/agent-landscape-live.md | sort)
for path in src/icode/linux_task_resource.py src/icode/execution_broker.py tests/test_linux_resource_runtime_deadline.py docs/nbl/specs/2026-10-12-linux-resource-runtime-deadline-design.md docs/nbl/plans/2026-10-12-linux-resource-runtime-deadline.md docs/agent-landscape-live.md; do
    git show ":$path" | cmp -s "$path" -
done
git diff --cached --stat
~~~

任何路径/字节/whitespace不符立即停，不reset用户改动，不用最终stat exit0掩前面失败。writer/TEST/SOURCE作者无stage/commit权限。

- [ ] **Step 2：root 一次 main commit/push、核HEAD=remote，继续下一片并跟踪新同SHA四Linux installed原生格。**

~~~bash
set -euo pipefail
git commit -m "fix(linux): preserve receiver runtime deadline cause"
git push origin main
git rev-parse HEAD
git ls-remote origin refs/heads/main
git status --short
~~~

只按真实返回补发布事实，不预写SHA、不force/删除分支。旧探针不是本片新矩阵，成功不证明历史ARM根因，失败不放宽预期。资产不覆盖worker未采样的所有竞争，不闭core完成观察/monitor截止/opaque factory/其它平台模型整体债务。后续常规独立开发已授权，仅必要新扩权询问。

## writer内置自审、实际RAM与摘要

规格映射：runtime实采样/kill前→Task1正例/Task2；stop共锁→写入/close先赢；精确bool→属性/truthy负控；错误顺序→五core error×observer两态；协议/配置/提前退出/外部kill→负控；完整transcript清理unknown→真实faulted/下一borrow拒绝；EOF活进程→原core等待；正式流程/范围/门/发布→Task1–4。无占位code或未定义fixture方法，类型/命名一致。

writer RAM 未改磁盘SOURCE/TEST：基线11方法/23有效assert FAIL/0error/skip/7.043s/exit1；RAM投影11方法/0F/E/skip/6.916s/exit0，仅计划资产诊断，不是正式双RED/GREEN/原生证明。正式结果必须作者/root独立记录。初始RAM overlay命令曾因shell argument list过长被拒、未执行；改为RAM读原源码并投影后才成功，不记产品缺陷/有效RED。

原 scanner 首检将两处 Python 下标紧接调用误识为 Markdown 链接；只为函数表达式添加括号，实际 AST dump（不含位置）与已运行 RAM 资产完全一致，compile 成功。原 RAM 测试字节 SHA 为 56e0d986d236a789b804ba9428adbe97774eab77ebe085b5b7f6506ab6bcf0fe；下表为最终等价语法资产，未声称以最终字节重新执行 RAM。正式作者/root及 fresh 审查仍须实际执行最终资产，不继承 AST 等价为正式门。

严格核六hunk原上下文、行数/位置及两完整投影，末尾换行计SHA：

| 完整资产 | SHA256 |
| --- | --- |
| Task1 TEST fence | 9c8c3a525e081c3f2fdc232e5ca492bbffd77684b86b8f267d9411a81b93fc89 |
| Task2 unified-diff fence | ad14147eb22131b4db8d77c6668fbb46e927816b54cdb3457c48906f548e85e7 |
| receiver 完整投影 | 3dcff10286cad966bb28408dd9b89fd328a2730e928cfa94dc71a28bdf34a13c |
| broker 完整投影 | 9de4f953d5e39b17c6a752b94add442dcca82de90ef2a94ab865696555d94cbb |

### root测试资产返修记录（保留上述writer历史）

原11方法881265bc资产的PLAN QUALITY为C0/I1/M0：首轮合法空readiness时按calls>1提前阻塞，真实CONFIGURED/ACK未完成；root与QUALITY独立各1F/0E/skip（2.601s/2.607s）。真实configured门控后同负控各1GREEN（0.405s/0.404s），仅解决这项前置缺陷。12方法a2b3a13e完整root RAM原基线24有效assertFAIL/0E/skip（7.422s），拟修投影仍1F/0E/skip（8.723s），目标core返回timeout而非None；不拿随后8次时间诊断GREEN抵消失败。QUALITY另以首次core轮询拖过真实截止点证明旧屏障缺口，1assertFAIL/0E/skip（2.565s）、真实core timeout/receiver doneFalse；同iteration骨架同负控1GREEN（0.361s）、正常12GREEN（7.364s），骨架当时未加收齐上限，不供应最终资产验收。

root最终仅DOCS修订为本407行/13方法资产，真实两pipe EOF收齐循环有5秒卫生上限及精确FD断言，永久保留两个空轮询负控；生产两SOURCE/六hunk未改。最终字节独立RAM：原基线13方法25有效assertFAIL/0E/skip（7.767s），严格六hunk完整投影13GREEN/0F/E/skip（7.775s）。这是计划资产诊断，不是正式双RED/GREEN；旧PLAN放行撤销，修订后须fresh SPEC及不同QUALITY重新审查再root GO。DESIGN批准字节未变，不改产品时限/core语义/权限/依赖，不宣称历史原生根因。

### 正式实施记录（2026-10-12 UTC）

最终407行/13方法TEST9c8c3a52与批准PLAN c8f9fe25先经fresh SPEC和不同QUALITY零遗留。正式TEST作者与root原基线分别13方法/25有效assertFAIL/0E/skip（7.685s、7.743s），两SOURCE保持f75932af/3212f070；真实core None/-9/cleanupTrue及worker/EOF前置已通过，不是fixture错误。不同fresh SOURCE作者仅六hunk，最终receiver3dcff102/broker9de4f953逐字吻合投影，TEST不变。

作者/root新13GREEN（7.798s、7.817s），七模块148GREEN（13.414s、13.444s），均0F/E/skip；compileall-j1/diff通过。fresh SOURCE SPEC与随后不同QUALITY均C0/I0/M0，各自独立新13（7.775s、7.788s）及148（13.667s、13.606s），均0F/E/skip。SOURCE/TEST三freeze保持；这只授有限软件矩阵，不替历史ARM因果、四格新installed或整体。

root唯一原完整guard session80104、j1，08:18:05 UTC启动，原日志 `/tmp/icode-runtime-deadline-preflight.VpUpXl/typescript`，08:27:41 UTC原footer/exit0，root08:27:42取得完整三门PASS；三freeze不变，无全量数量不猜。最终文档单门/index/发布仍待，Task4发布事实只在真实完成后记入后续阶段记录，不为自引用commit提前编造。S2a同SHA三workflow已全部终态并由root取得原metadata/jobs/raw：CI40success/3failure/3skip（46），provenance5/5、Pages2/2；外部失败保持，不取消/重跑。下一片S2b1只准备设计与只读研究，不进入本片六路径或提前落盘SOURCE/TEST。

【架构级自检报告】（PLAN资产范围）

- 语法/编译：完整测试/两投影RAM可执行，严格六hunk通过；未改生产源码。
- 依赖/调用链：实际公共broker→真实core/receiver→原收尾；唯一borrow保持。
- 逻辑/边界：deadline实采样/kill前、stop线性化、非到期及错误矩阵覆盖。
- 异常处理：保留observer/terminal/cleanup顺序，不扩preserved_errors/猜退出码。
- 关联模块：仅六发布路径，旧core/scope/runner/vendor/CI只读。
- 兼容安全：无公开receipt/schema/权限/新依赖，旧double无属性按false。
- 可运行性：只授RAM诊断；正式双RED/GREEN、回归、双审、原完整门、安装格未实施，不报告100%。

---
**Execution Mode:** serial

纯依赖链及真实线程/子进程竞态，不属inline。root按subagent-driven-development启动fresh作者/不同审查者。本writer完成后STOP，等root PLAN SPEC/不同QUALITY与GO，不自动handoff。
