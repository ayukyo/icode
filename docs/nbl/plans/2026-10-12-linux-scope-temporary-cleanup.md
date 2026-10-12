# Linux B2 scope 临时资源清理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development (recommended) or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 使已取得 scope 临时 FD 的未知关闭进入既有 sticky unknown，保留首中断，并由既有 broker 撤销后续借用。

**Architecture:** 两个私有 helper 增加默认 None 的关闭参数，scope 所有临时取得点配对传既有 owning-close。runtime probe 和 parent 独立收尾；探针关闭未知时基类 detach 只解除自动 owning，不重试未知 FD 数字、不确认 OS 回收。broker、工厂、工作区、native 均不改。

**Tech Stack:** Python 3.11+、标准库 unittest、真实 Linux 目录/regular/socket FD、现有 prepared-step 软件 fixtures。

---

## 执行边界与冻结基线

批准 DESIGN：`docs/nbl/specs/2026-10-12-linux-scope-temporary-cleanup-design.md`，SHA256 `703dc274b4b38046313a2a57b091728dca2c0835471fa9e2272dc74cf52652ba`，独立 SPEC 与不同 QUALITY 均 C0/I0/M0。当前基线 main `80f36ec25ca0ecb17bb3817f932f3babd1d7d66a`；B1 已实际提交推送，scope 基线仍 `776ab721fec0e18e73e21fbdbdfdc75cf123c68e2b7868aa25a0dee03c5c8b69`。本 PLAN 生成阶段只写本文，未实施 tests/SOURCE，不自动移交执行；root 明确 GO 后才按下面顺序执行。

用户 main-only 覆盖技能默认 worktree。只允许五路径：

| 路径 | 责任 |
|---|---|
| `src/icode/linux_task_scope.py` | 最小私有 close 配对与首信号收尾 |
| `tests/test_linux_scope_temporary_cleanup.py` | 新的真实 FD、异常身份与实际 broker 消费负控 |
| `docs/nbl/specs/2026-10-12-linux-scope-temporary-cleanup-design.md` | 批准设计和历史基线，不改成虚假已完成 |
| `docs/nbl/plans/2026-10-12-linux-scope-temporary-cleanup.md` | 本计划与实际证据 |
| `docs/agent-landscape-live.md` | root 唯一写者，采纳/暂缓/不适配及日期记录 |

其余原 B1 两工厂/测试、broker、母设计、vendor/native/CI 只读。若真实旧 fixture 不兼容，停止 SOURCE 并补独立设计证据，不能扩大路径或捕获 TypeError 重试探接口。

三问已确认：真实 FD RAM 显示临时关闭未知后误报 confirmed、收尾覆盖原 KI/SE；复用已有 owning-close/_select_cleanup_error；配置五 read、两类配置 walk、runtime 与 collected 配对均在本文件内。独立只读研究证据与许可取舍见批准 DESIGN；不以竞品观察替代验收。

### Task 1：新测试作者落盘真实 FD 负控并正式 RED

**状态**

- [x] 任务完成

**Dependencies:** None
**Parallelizable:** No (root GO、源码基线与完整 PLAN 双审必须先通过，测试和源码作者串行不同)

- [x] **Step 1：root 完整阅读本文与 DESIGN；独立 PLAN SPEC 和不同 QUALITY 对照资产通过。**

核验命令：

~~~bash
git status --short
git rev-parse HEAD
sha256sum src/icode/linux_task_scope.py docs/nbl/specs/2026-10-12-linux-scope-temporary-cleanup-design.md
~~~

预期 HEAD 为以上 80f36ec 完整 SHA、scope/DESIGN 字节为以上固定 SHA；若 root 已明确记录新的未改 scope 主分支基线，可记录实际 SHA，不能猜测。确认 index 没有其它人的 staged changes。RAM 编译/投影可以检查资产，不授正式 TDD。

- [x] **Step 2：fresh 测试作者仅用 apply_patch 新增以下完整模块。**

~~~python
"""B2 actual FD/software ownership; no native manager or installed credit."""
from __future__ import annotations
from contextlib import ExitStack, contextmanager
import errno
import inspect
import os
from pathlib import Path
import socket
import stat
import struct
import sys
import threading
import time
import unittest
from unittest.mock import patch
from tests._support import temp_workspace

LINUX = sys.platform.startswith("linux")
if LINUX:
    from icode import linux_task_scope as subject
    from icode import linux_prepared_step as prepared
    from icode import execution_broker as broker
    from tests import test_linux_prepared_broker as previous
    from tests import test_linux_prepared_step as fixture
    from tests import test_linux_helper_dispatch as dispatch

REAL_OPEN, REAL_CLOSE, REAL_FSTAT = os.open, os.close, os.fstat
BASE_SOCKET = socket.socket
BASE_DETACH, BASE_CLOSE = BASE_SOCKET.detach, BASE_SOCKET.close


def capture(operation):
    try:
        return operation(), None
    except BaseException as error:
        return None, error


def release_live(descriptors):
    # Only test-owned, known-live before-close faults; never production credit.
    for descriptor in set(descriptors):
        try:
            REAL_FSTAT(descriptor)
        except OSError:
            continue
        REAL_CLOSE(descriptor)


@unittest.skipUnless(LINUX, "Linux actual FD software; skip is not acceptance")
class TemporaryScopeTests(unittest.TestCase):
    @contextmanager
    def tree(self, kind=None, failure=None, reuse=False):
        with temp_workspace() as root:
            group = root / "group"
            group.mkdir(mode=0o700)
            (group / "supervisor").mkdir(mode=0o700)
            (group / "payload").mkdir(mode=0o700)
            pid = os.getpid()
            for parent, name, data in (
                (group, "cgroup.procs", ""),
                (group / "supervisor", "cgroup.procs", str(pid)),
                (group / "payload", "cgroup.procs", ""),
                (group / "payload", "pids.current", "0"),
                (group / "payload", "pids.max", "16"),
            ):
                (parent / name).write_text(data, encoding="ascii")
            task = object.__new__(subject.LinuxTaskScope)
            task.uid, task.limit, task._pid = os.getuid(), 16, pid
            task.unit = "icode-task-" + "a" * 32 + ".scope"
            task.version = 249
            task.environment = dict(dispatch.Scope.environment)
            task._fds, task._identities = [], []
            task._cleanup_unknown = False
            task._path, task._invocation, task._owned = None, None, False
            task._lifecycle, task._close_requested = threading.Lock(), threading.Event()
            task._membership = lambda: "/group/supervisor"
            task._show = lambda deadline: dict(LoadState="loaded", ActiveState="active",
                Transient="yes", InvocationID="b" * 32, ControlGroup="/group")
            trace = dict(opened=[], attempts=[], watched=None, foreign=None, roots=0,
                         read_names=[], fault_hits=0, watched_before=0)
            def opening(path, flags, *args, **kwargs):
                actual = root if path == "/" else path
                descriptor = REAL_OPEN(actual, flags, *args, **kwargs)
                trace["opened"].append(descriptor)
                if path == "/":
                    trace["roots"] += 1
                    selected = ((kind == "initialwalk" and trace["roots"] == 1)
                        or (kind == "revalidationwalk" and trace["roots"] == 4)
                        or kind == "collectwalk")
                    if selected and trace["watched"] is None:
                        trace["watched"] = descriptor
                        trace["watched_before"] = trace["attempts"].count(descriptor)
                elif stat.S_ISREG(REAL_FSTAT(descriptor).st_mode):
                    trace["read_names"].append(str(path))
                    if (kind in ("read", "read2", "read3", "read4", "read5")
                            and len(trace["read_names"]) == (1 if kind == "read" else int(kind[-1]))
                            and trace["watched"] is None):
                        trace["watched"] = descriptor
                        trace["watched_before"] = trace["attempts"].count(descriptor)
                return descriptor
            def closing(descriptor):
                trace["attempts"].append(descriptor)
                if descriptor == trace["watched"] and trace["fault_hits"] == 0:
                    trace["fault_hits"] += 1
                    if reuse:
                        REAL_CLOSE(descriptor)
                        foreign = REAL_OPEN("/dev/null", os.O_RDONLY | os.O_CLOEXEC)
                        if foreign != descriptor:
                            os.dup2(foreign, descriptor)
                            REAL_CLOSE(foreign)
                        trace["foreign"] = descriptor
                    raise failure
                REAL_CLOSE(descriptor)
            trace["opening"], trace["closing"] = opening, closing
            try:
                with patch.object(subject, "_CGROUP", Path("/")), \
                     patch.object(subject.os, "open", side_effect=opening), \
                     patch.object(subject.os, "close", side_effect=closing):
                    yield task, trace
            finally:
                # Release the actual pins before taking test-owned residuals.
                with patch.object(subject.os, "close", side_effect=REAL_CLOSE):
                    task.close()
                release_live(trace["opened"])

    def test_configure_read_initial_walk_and_revalidation_unknown_targets(self):
        for kind in ("read", "read2", "read3", "read4", "read5", "initialwalk", "revalidationwalk"):
            with self.subTest(kind=kind), self.tree(kind, OSError(errno.EIO, "before close")) as (task, trace):
                _, error = capture(lambda: task.configured(time.monotonic() + 1))
                self.assertIsInstance(error, OSError)
                descriptor = trace["watched"]
                self.assertIsNotNone(descriptor)
                self.assertTrue(REAL_FSTAT(descriptor))
                self.assertEqual(trace["fault_hits"], 1)
                self.assertEqual(trace["attempts"].count(descriptor) - trace["watched_before"], 1)
                self.assertEqual(task._fds, [])
                self.assertFalse(task._lifecycle.locked())
                for other in set(trace["opened"]) - {descriptor}:
                    with self.assertRaises(OSError):
                        REAL_FSTAT(other)
                self.assertEqual(task.cleanup_state, "unknown")
                task.close()
                self.assertTrue(REAL_FSTAT(descriptor))
                self.assertEqual(task.cleanup_state, "unknown")

    def test_collected_walk_unknown_target_and_lock_release(self):
        with self.tree("collectwalk", OSError(errno.EIO, "before close")) as (task, trace):
            task._owned, task._path, task._invocation = True, Path("/group"), "b" * 32
            self.assertIsNone(task.collected(time.monotonic() + 1))
            self.assertTrue(REAL_FSTAT(trace["watched"]))
            self.assertEqual(trace["fault_hits"], 1)
            self.assertEqual(trace["attempts"].count(trace["watched"]) - trace["watched_before"], 1)
            self.assertFalse(task._lifecycle.locked())
            self.assertEqual(task.cleanup_state, "unknown")

    def test_after_close_reuse_is_not_retried_and_remains_unknown_target(self):
        with self.tree("read", OSError(errno.EIO, "after close"), reuse=True) as (task, trace):
            _, error = capture(lambda: task.configured(time.monotonic() + 1))
            self.assertIsInstance(error, OSError)
            self.assertTrue(stat.S_ISCHR(REAL_FSTAT(trace["foreign"]).st_mode))
            self.assertEqual(trace["attempts"].count(trace["watched"]) - trace["watched_before"], 1)
            task.close()
            self.assertTrue(REAL_FSTAT(trace["foreign"]))
            self.assertEqual(task.cleanup_state, "unknown")

    def test_success_configure_all_reads_revalidation_and_default_none_helpers(self):
        with self.tree() as (task, trace):
            task.configured(time.monotonic() + 1)
            self.assertTrue(task._owned)
            self.assertEqual(trace["roots"], 6)
            self.assertEqual(trace["read_names"], ["cgroup.procs", "cgroup.procs",
                "cgroup.procs", "pids.current", "pids.max"])
            descriptor = subject._open_directory(Path("/group/payload"), uid=task.uid)
            try:
                self.assertEqual(subject._read_at(descriptor, "pids.max"), b"16")
                with self.assertRaises(subject.LinuxTaskScopeError):
                    subject._read_at(descriptor, "pids.max", limit=0)
            finally:
                REAL_CLOSE(descriptor)
            task.close()
            self.assertEqual(task.cleanup_state, "confirmed")

    def test_collected_real_missing_directory_success(self):
        with self.tree() as (task, trace):
            task._owned, task._path = True, Path("/absent")
            task._show = lambda deadline: dict(LoadState="not-found", ControlGroup="")
            self.assertIs(task.collected(time.monotonic() + 1), True)
            self.assertFalse(task._lifecycle.locked())
            self.assertEqual(task.cleanup_state, "confirmed")

    def test_read_first_signal_identity_target_and_cleanup_signal_control(self):
        for body in (KeyboardInterrupt(), SystemExit(81), RuntimeError("body")):
            for cleanup in (OSError(errno.EIO, "close"), KeyboardInterrupt(), SystemExit(82)):
                with self.subTest(body=type(body).__name__, cleanup=type(cleanup).__name__), temp_workspace() as root:
                    (root / "data").write_bytes(b"data")
                    directory = REAL_OPEN(root, os.O_RDONLY | os.O_DIRECTORY)
                    opened, attempts = [], []
                    def opening(*args, **kwargs):
                        fd = REAL_OPEN(*args, **kwargs)
                        opened.append(fd)
                        return fd
                    def closing(fd):
                        attempts.append(fd)
                        REAL_CLOSE(fd)
                        raise cleanup
                    try:
                        with patch.object(subject.os, "open", side_effect=opening), \
                             patch.object(subject.os, "read", side_effect=body), \
                             patch.object(subject.os, "close", side_effect=closing):
                            _, error = capture(lambda: subject._read_at(directory, "data"))
                        expected = body if not isinstance(body, Exception) or isinstance(cleanup, Exception) else cleanup
                        self.assertEqual(attempts, opened)
                        for fd in opened:
                            with self.assertRaises(OSError):
                                REAL_FSTAT(fd)
                        self.assertIs(error, expected)
                    finally:
                        REAL_CLOSE(directory)


@unittest.skipUnless(LINUX, "Linux constructor actual directory/socket FD")
class RuntimeProbeTests(unittest.TestCase):
    @contextmanager
    def construction(self, body=None, probe_error=None, parent_error=None,
                     detached_error=None, unavailable=False, reuse=False):
        with temp_workspace() as root:
            parent = REAL_OPEN(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
            original = REAL_FSTAT(parent)
            uid = 1001
            status = type("Status", (), dict(st_uid=uid, st_mode=stat.S_IFDIR | 0o700))()
            bus = type("Bus", (), dict(st_uid=uid, st_mode=stat.S_IFSOCK | 0o600))()
            trace = dict(parent=[], probe=[], detach=[], foreign=None, queries=[])
            class Probe(BASE_SOCKET):
                def settimeout(self, seconds):
                    trace["timeout"] = seconds
                def connect(self, path):
                    trace["connect"] = path
                    if body is not None:
                        raise body
                def getsockopt(self, *args):
                    return struct.pack("3i", os.getpid(), uid, os.getgid())
                def close(self):
                    trace["probe"].append(self.fileno())
                    if probe_error is not None:
                        if reuse:
                            fd = self.fileno()
                            BASE_CLOSE(self)
                            foreign = REAL_OPEN("/dev/null", os.O_RDONLY)
                            if foreign != fd:
                                os.dup2(foreign, fd)
                                REAL_CLOSE(foreign)
                            trace["foreign"] = fd
                        raise probe_error
                    BASE_CLOSE(self)
                def detach(self):
                    raise AssertionError("must not use overridden detach")
            probe = Probe(socket.AF_UNIX, socket.SOCK_STREAM)
            probe_fd = probe.fileno()
            def factory(*args):
                if unavailable:
                    raise body
                return probe
            def detach(endpoint):
                trace["detach"].append(endpoint)
                if detached_error is not None:
                    raise detached_error
                return BASE_DETACH(endpoint)
            class SocketShim:
                pass
            SocketShim.detach = staticmethod(detach)
            SocketShim.__new__ = staticmethod(lambda cls, *args: factory(*args))
            def closing(fd):
                trace["parent"].append(fd)
                if parent_error is not None:
                    raise parent_error
                REAL_CLOSE(fd)
            def fstat(fd):
                return status if fd == parent else REAL_FSTAT(fd)
            def query(argv, environment, deadline):
                trace["queries"].append((argv, environment, deadline))
                return b"systemd 249\n"
            try:
                with ExitStack() as stack:
                    stack.enter_context(patch.object(subject.os, "getuid", return_value=uid))
                    stack.enter_context(patch.object(subject, "_trusted_tool"))
                    stack.enter_context(patch.object(subject, "_open_directory", return_value=parent))
                    stack.enter_context(patch.object(subject.os, "fstat", side_effect=fstat))
                    stack.enter_context(patch.object(subject.os, "stat", return_value=bus))
                    stack.enter_context(patch.object(subject.os, "close", side_effect=closing))
                    stack.enter_context(patch.object(subject.socket, "socket", SocketShim))
                    value, error = capture(lambda: subject.LinuxTaskScope(limit=16, query=query))
                yield value, error, probe, probe_fd, parent, trace
            finally:
                # Base detach prevents fixture finalization from retrying any reused number.
                BASE_DETACH(probe)
                release_live([parent, probe_fd, trace["foreign"]] if trace["foreign"] is not None
                             else [parent, probe_fd])

    def test_runtime_body_first_signal_probe_and_parent_failures_target(self):
        for first in (KeyboardInterrupt(), SystemExit(83)):
            with self.subTest(first=type(first).__name__), self.construction(
                    first, RuntimeError("probe close"), RuntimeError("parent close")) as (value, error, probe, probe_fd, parent, trace):
                self.assertTrue(REAL_FSTAT(probe_fd))
                self.assertTrue(REAL_FSTAT(parent))
                self.assertEqual(trace["probe"], [probe_fd])
                self.assertEqual(trace["parent"], [parent])
                self.assertIs(error, first)
                self.assertEqual(probe.fileno(), -1)

    def test_unavailable_probe_still_closes_parent_and_preserves_first_signal_target(self):
        for first in (KeyboardInterrupt(), SystemExit(84)):
            with self.subTest(first=type(first).__name__), self.construction(
                    first, parent_error=RuntimeError("parent close"), unavailable=True) as (value, error, probe, probe_fd, parent, trace):
                self.assertEqual(trace["probe"], [])
                self.assertEqual(trace["parent"], [parent])
                self.assertTrue(REAL_FSTAT(parent))
                self.assertIs(error, first)

    def test_detach_fault_keeps_first_signal_and_still_drains_parent(self):
        first = KeyboardInterrupt()
        with self.construction(first, RuntimeError("probe close"), None,
                SystemExit(85)) as (value, error, probe, probe_fd, parent, trace):
            self.assertIs(error, first)
            self.assertEqual(trace["detach"], [probe])
            self.assertEqual(trace["parent"], [parent])
            with self.assertRaises(OSError):
                REAL_FSTAT(parent)
            self.assertTrue(REAL_FSTAT(probe_fd))

    def test_probe_after_close_reuse_survives_parent_drain(self):
        first = RuntimeError("probe close")
        with self.construction(probe_error=first, reuse=True) as (value, error, probe, probe_fd, parent, trace):
            self.assertIs(error, first)
            self.assertEqual(trace["probe"], [probe_fd])
            self.assertEqual(probe.fileno(), -1)
            self.assertTrue(stat.S_ISCHR(REAL_FSTAT(trace["foreign"]).st_mode))
            self.assertEqual(trace["parent"], [parent])

    def test_runtime_ordinary_body_cleanup_signal_priority_and_remaining_parent(self):
        body = RuntimeError("connect")
        for cleanup in (OSError(errno.EIO, "probe close"), KeyboardInterrupt(), SystemExit(86)):
            with self.subTest(cleanup=type(cleanup).__name__), self.construction(
                    body, cleanup, RuntimeError("parent close")) as (value, error, probe, probe_fd, parent, trace):
                self.assertEqual(trace["probe"], [probe_fd])
                self.assertEqual(trace["parent"], [parent])
                self.assertEqual(probe.fileno(), -1)
                self.assertTrue(REAL_FSTAT(probe_fd))
                self.assertTrue(REAL_FSTAT(parent))
                self.assertIs(error, body if isinstance(cleanup, Exception) else cleanup)

    def test_success_constructor_contract(self):
        with self.construction() as (value, error, probe, probe_fd, parent, trace):
            self.assertIsNone(error)
            self.assertEqual(value.version, 249)
            self.assertEqual(trace["timeout"], subject._BUS_CONNECT_TIMEOUT_SECONDS)
            self.assertEqual(trace["connect"], "/run/user/1001/bus")
            self.assertEqual(trace["probe"], [probe_fd])
            self.assertEqual(trace["parent"], [parent])
            self.assertEqual(len(trace["queries"]), 1)
            self.assertEqual(value.cleanup_state, "confirmed")


@unittest.skipUnless(LINUX, "Linux prepared borrow with actual scope state")
class BrokerScopeTests(unittest.TestCase):
    if LINUX:
        setUp = fixture.PreparedTests.setUp
        write_image = fixture.PreparedTests.write_image
        precheck_fixture = fixture.PreparedTests.precheck_fixture
        cleanup_scopes = fixture.PreparedTests.cleanup_scopes
        prepare = fixture.PreparedTests.prepare
        attach = fixture.PreparedTests.attach
        bind = fixture.PreparedTests.bind
        borrow = fixture.PreparedTests.borrow
        call = previous.PreparedBrokerTests.call
        entry = previous.PreparedBrokerTests.entry
        wrapper = previous.PreparedBrokerTests.wrapper

    def test_actual_returned_scope_unknown_faults_attachment_before_next_borrow(self):
        for kind in ("read", "initialwalk"):
            with self.subTest(kind=kind):
                owner = self.prepare()
                view = self.bind(self.attach(owner))
                self.owners = []
                helper = TemporaryScopeTests()
                with helper.tree(kind, OSError(errno.EIO, "before close")) as (task, trace):
                    task.limit = self.policy.process_limit
                    # Real returned scope, real configured and close methods.
                    # Manager/payload/receiver are software seams, not native proof.
                    task.collected = lambda deadline: True
                    def run(argv, **kwargs):
                        kwargs["before_spawn"]()
                        with patch.object(subject.os, "open", side_effect=trace["opening"]), \
                             patch.object(subject.os, "close", side_effect=trace["closing"]):
                            _, configured_error = capture(lambda: task.configured(time.monotonic() + 1))
                        self.assertIsInstance(configured_error, OSError)
                        return broker.ExecutionResult(0, "", 0, None, False, True, None)
                    with patch.object(subject.os, "open", side_effect=REAL_OPEN), \
                         patch.object(subject.os, "close", side_effect=REAL_CLOSE), \
                         patch.object(subject, "LinuxTaskScope", return_value=task), \
                         patch("icode.linux_task_resource.LinuxTaskResourceReceiver", return_value=dispatch.Resource()), \
                         patch("icode.linux_seccomp_notify.LinuxSeccompViolationMonitor", side_effect=dispatch.Monitor), \
                         patch.object(broker, "_execute_policy_command", side_effect=run):
                        _, error = capture(lambda: self.call(True, view))
                    self.assertTrue(REAL_FSTAT(trace["watched"]))
                    self.assertEqual(trace["attempts"].count(trace["watched"]) - trace["watched_before"], 1)
                    self.assertFalse(task._lifecycle.locked())
                    self.assertFalse(owner._inflight)
                    self.assertEqual(owner._owner_state, "active")
                    REAL_FSTAT(owner._owner.fileno())
                    REAL_FSTAT(self.session.workspace_fd)
                    self.assertEqual(owner._consume_state, "faulted")
                    self.assertEqual(task.cleanup_state, "unknown")
                    self.assertIsInstance(error, RuntimeError)
                    with self.assertRaises(prepared.LinuxPreparedStepError):
                        with self.borrow(view):
                            self.fail("faulted borrow re-entered")


if __name__ == "__main__":
    unittest.main()
~~~

说明：非 Linux 条件 import 使 Windows 能 collection，并正确逐项 skip；skip 不授原生能力。真实 scope 方法经 __new__ 完整状态 fixture 调用，manager membership/show、runtime 信任/身份前提、payload/receiver 均明确局部注入，不宣称真实 systemd manager/内核/native/安装证明。root-owned临时目录映射只包住实际 walk/read；broker 的 helper/工作区验证在真实正常 os.open/os.close 下运行。数字曾复用时只比较目标被取得后的关闭次数，不把历史同数字关闭误算。finally 卫生释放仅针对测试明确保留的真实残留与外来 FD，不计生产回收。

- [x] **Step 3：作者实际跑 RED，root 独立重复；此时 SOURCE 必须仍为 776ab721 基线。**

~~~bash
.venv/bin/python -B -m unittest tests.test_linux_scope_temporary_cleanup -v
sha256sum src/icode/linux_task_scope.py
~~~

预期：13 个方法，其中真实 unknown/身份负控 assertion FAIL，0 error；Linux 不应 skip。RAM 基线观察为 26 个子断言 FAIL，正式结果必须以各自新输出记录，不能搬 RAM 数字充信用。成功 constructor/default None/configure/collected 与既有优先级对照可通过。任何 missing-module、TypeError、None FD、卫生错误或信任前提未成立都不是有效 RED，先改 TEST 资产并重新双审/RED，不改 SOURCE。root 检查真实 FD 仍活、其余 pins 已关闭、锁释放前置及 actual broker 目标确实到达；未达到目标不得 SOURCE GO。

实际Task1：PLAN原审查字节e01f34b2，fresh SPEC/不同QUALITY均C0/I0/M0；TEST ef8e45a701f3db54619f427637fdf67e601830a2c1b2bab83331eedd6f585037正式落盘。作者13方法0.112s、root独立13方法0.149s，均26有效assertFAIL/0error/skip、exit1；root另一次0.137s同结果。原scope776ab721不变，真实FD仍活/其余pins关闭/锁释放及broker owneractive/inflight归还前置均通过，失败发生于unknown/首异常身份/attachment消费目标；失败后被截断的next-borrow等断言不预授通过。root已全文actual420行测试，授权不同fresh SOURCE作者唯一最小scope差分。测试卫生只属fixture，不授production回收或native/installed信用。

### Task 2：不同源码作者实施唯一最小 scope 差分

**状态**

- [x] 任务完成

**Dependencies:** Task 1
**Parallelizable:** No (root 接受正式 RED 后，different fresh SOURCE 作者仅改一个模块)

- [x] **Step 1：核基线，应用以下完整唯一差分。**

~~~diff
--- a/src/icode/linux_task_scope.py
+++ b/src/icode/linux_task_scope.py
@@ -33,10 +33,12 @@
         super().__init__("Linux task scope is unavailable")
-
+
-
+
-def _open_directory(path: Path, *, uid: int, cgroup: bool = False) -> int:
+def _open_directory(path: Path, *, uid: int, cgroup: bool = False,
+                    close_descriptor: Callable[[int], None] | None = None) -> int:
     """Walk pinned non-link ancestors, accepting only root/current-UID owners."""
     if not path.is_absolute() or any(part in ("", ".", "..") for part in path.parts[1:]):
         raise LinuxTaskScopeError()
+    close = os.close if close_descriptor is None else close_descriptor
     current = os.open("/", _DIRECTORY_FLAGS)
     try:
         device = None
@@ -44,7 +46,7 @@
             following = os.open(component, _DIRECTORY_FLAGS, dir_fd=current)
             previous = current
             current = following
-            os.close(previous)
+            close(previous)
             status = os.fstat(current)
             if status.st_uid not in (0, uid) or status.st_mode & 0o022:
                 raise LinuxTaskScopeError()
@@ -55,7 +57,7 @@
         return current
     except BaseException as error:
         try:
-            os.close(current)
+            close(current)
         except BaseException as cleanup_error:
             selected = _select_cleanup_error(error, cleanup_error)
             if selected is not error:
@@ -90,7 +92,8 @@
                 raise selected
-
+
-
+
-def _read_at(directory: int, name: str, limit: int = _CGROUP_READ_LIMIT_BYTES) -> bytes:
+def _read_at(directory: int, name: str, limit: int = _CGROUP_READ_LIMIT_BYTES, *,
+             close_descriptor: Callable[[int], None] | None = None) -> bytes:
     descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
     try:
         result = bytearray()
@@ -101,7 +104,13 @@
             result.extend(chunk)
         raise LinuxTaskScopeError()
     finally:
-        os.close(descriptor)
+        active_exception = sys.exc_info()[1]
+        try:
+            (os.close if close_descriptor is None else close_descriptor)(descriptor)
+        except BaseException as cleanup_error:
+            selected = _select_cleanup_error(active_exception, cleanup_error)
+            if selected is not active_exception:
+                raise selected
-
+
-
+
 class LinuxTaskScope:
@@ -132,21 +141,42 @@
         for path in ("/usr/bin/systemd-run", "/usr/bin/systemctl"):
             _trusted_tool(path, self.uid)
         runtime = Path(f"/run/user/{self.uid}")
-        parent = _open_directory(runtime, uid=self.uid)
+        parent = _open_directory(runtime, uid=self.uid,
+                                 close_descriptor=self._close_owned_descriptor)
+        probe = None
         try:
             status = os.fstat(parent)
             bus = os.stat("bus", dir_fd=parent, follow_symlinks=False)
             if (status.st_uid != self.uid or stat.S_IMODE(status.st_mode) != 0o700
                     or not stat.S_ISSOCK(bus.st_mode) or bus.st_uid != self.uid):
                 raise LinuxTaskScopeError()
-            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
-                probe.settimeout(_BUS_CONNECT_TIMEOUT_SECONDS)
-                probe.connect(str(runtime / "bus"))
-                _pid, peer_uid, _gid = struct.unpack("3i", probe.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
-                if peer_uid != self.uid:
-                    raise LinuxTaskScopeError()
+            probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
+            probe.settimeout(_BUS_CONNECT_TIMEOUT_SECONDS)
+            probe.connect(str(runtime / "bus"))
+            _pid, peer_uid, _gid = struct.unpack("3i", probe.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
+            if peer_uid != self.uid:
+                raise LinuxTaskScopeError()
         finally:
-            os.close(parent)
+            active_exception = sys.exc_info()[1]
+            close_error = None
+            if probe is not None:
+                try:
+                    probe.close()
+                except BaseException as error:
+                    self._cleanup_unknown = True
+                    close_error = _select_cleanup_error(close_error, error)
+                    try:
+                        socket.socket.detach(probe)
+                    except BaseException as cleanup_error:
+                        close_error = _select_cleanup_error(close_error, cleanup_error)
+            try:
+                self._close_owned_descriptor(parent)
+            except BaseException as error:
+                close_error = _select_cleanup_error(close_error, error)
+            if close_error is not None:
+                selected = _select_cleanup_error(active_exception, close_error)
+                if selected is not active_exception:
+                    raise selected
         self.environment = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C",
                             "XDG_RUNTIME_DIR": str(runtime),
                             "DBUS_SESSION_BUS_ADDRESS": f"unix:path={runtime / 'bus'}"}
@@ -239,7 +269,8 @@
         path = _CGROUP / group.lstrip("/")
         try:
             for candidate in (path, path / "supervisor", path / "payload"):
-                descriptor = _open_directory(candidate, uid=self.uid, cgroup=True)
+                descriptor = _open_directory(candidate, uid=self.uid, cgroup=True,
+                                             close_descriptor=self._close_owned_descriptor)
                 self._fds.append(descriptor)
                 status = os.fstat(descriptor)
                 if status.st_uid != self.uid:
@@ -250,16 +281,22 @@
                     or fields["Transient"] != "yes" or not _INVOCATION.fullmatch(fields["InvocationID"])
                     or fields["ControlGroup"] != group):
                 raise LinuxTaskScopeError()
-            if (_read_at(self._fds[0], "cgroup.procs").strip()
-                    or _read_at(self._fds[1], "cgroup.procs").strip() != str(self._pid).encode("ascii")
-                    or _read_at(self._fds[2], "cgroup.procs").strip()
-                    or _read_at(self._fds[2], "pids.current").strip() != b"0"
-                    or _read_at(self._fds[2], "pids.max").strip() != str(self.limit).encode("ascii")):
+            if (_read_at(self._fds[0], "cgroup.procs",
+                            close_descriptor=self._close_owned_descriptor).strip()
+                    or _read_at(self._fds[1], "cgroup.procs",
+                            close_descriptor=self._close_owned_descriptor).strip() != str(self._pid).encode("ascii")
+                    or _read_at(self._fds[2], "cgroup.procs",
+                            close_descriptor=self._close_owned_descriptor).strip()
+                    or _read_at(self._fds[2], "pids.current",
+                            close_descriptor=self._close_owned_descriptor).strip() != b"0"
+                    or _read_at(self._fds[2], "pids.max",
+                            close_descriptor=self._close_owned_descriptor).strip() != str(self.limit).encode("ascii")):
                 raise LinuxTaskScopeError()
             if self._membership() != membership:
                 raise LinuxTaskScopeError()
             for candidate, identity in zip((path, path / "supervisor", path / "payload"), self._identities, strict=True):
-                descriptor = _open_directory(candidate, uid=self.uid, cgroup=True)
+                descriptor = _open_directory(candidate, uid=self.uid, cgroup=True,
+                                             close_descriptor=self._close_owned_descriptor)
                 try:
                     status = os.fstat(descriptor)
                     if (status.st_dev, status.st_ino) != identity:
@@ -309,7 +346,8 @@
             try:
                 fields = self._show(deadline)
                 try:
-                    descriptor = _open_directory(self._path, uid=self.uid, cgroup=True)
+                    descriptor = _open_directory(self._path, uid=self.uid, cgroup=True,
+                                                 close_descriptor=self._close_owned_descriptor)
                 except FileNotFoundError:
                     return fields["LoadState"] == "not-found" and not fields["ControlGroup"]
                 else:
~~~

接口保持默认 None 旧 caller 可用；scope 九个 hook 调用为 runtime 1、配置 walk 两个源码位置、collected 1、五 read。_trusted_tool 不变，其已有两 FD drain/首信号控制由原回归确认。probe 未取得也收尾 parent，已取得 probe close 失败先 sticky unknown、基类 detach 失败也选择异常后继续 parent。原 KI/SE 对象不会被普通 cleanup 或后续信号替换；普通 body+普通 cleanup 复用已有首异常规则。detach 返回的数字丢弃、不 retry，未知不作回收信用。

- [x] **Step 2：源码作者与 root 各自执行新模块及原模块回归，记录所有 skip。**

~~~bash
.venv/bin/python -B -m unittest tests.test_linux_scope_temporary_cleanup -v
.venv/bin/python -B -m unittest tests.test_linux_channel_factory_cleanup tests.test_linux_resource_cleanup tests.test_linux_prepared_broker -v
.venv/bin/python -B -m unittest tests.test_linux_prepared_step tests.test_linux_helper_dispatch tests.test_execution_broker tests.test_linux_task_resource tests.test_linux_violation_receipt tests.test_linux_helper_object
.venv/bin/python -B -m unittest tests.test_linux_product_task_quota -v
.venv/bin/python -B -m compileall -q -j 1 src/icode/linux_task_scope.py tests/test_linux_scope_temporary_cleanup.py
git diff --check
~~~

预期新模块 13/13、B1 新8+原33=41 个方法、旧六模块163全绿；实际方法数量可能随真实上游变化，必须核当前输入，不能硬授数字。product quota 原真实 FD/首信号对照全绿，原生因环境 skip逐项列出，不报告原生通过。禁止为通过改旧测试、延长 deadline、放宽权限或在未知状态 retry。检查后续借用实际异常、helper owner 仍 active、工作区/owner 真 FD 可用、inflight=False，与 unknown→faulted 分账。

实际Task2：不同fresh作者仅scope唯一9hunk，SOURCE 7de59a7a96a120c2776c254b97420939c7877fffd6247a3b305cc79e0ca6bfb4、TEST ef8e45a7不变。作者新13/0.115s、原41/2.328s、旧163/21.415s、quota46/10.239s；root全文最终scope/test，独立新13/0.102s、原41/2.552s、旧163/21.388s、quota46/10.301s均0F/E/skip。quota实际无skip，不能虚填环境skip或授新B2四格installed。compileall-j1/diff通过，root site/governance通过。作者内建SPEC/QUALITY各C0/I0/M0不替fresh独立审查；actual broker next-borrow已执行拒绝、helper/session仍活，未知不因pins清空转confirmed。root已启动fresh SOURCE SPEC，完整预检尚未运行。

### Task 3：fresh 双 SOURCE 审查及 root 原完整验收

**状态**

- [x] 任务完成

**Dependencies:** Task 2
**Parallelizable:** No (同一 frozen SOURCE/test，先 SPEC 再不同 QUALITY；唯一 fullguard)

- [x] **Step 1：fresh SPEC 全文核 DESIGN/PLAN/SOURCE/test/调用方，C0/I0/M0 后不同 QUALITY 重核。**

明确验收范围：所有已取得临时 FD 各一次；五 read 和配置首次/身份重核/collected walk 路径没有遗漏；未知 sticky不能被清空 pins或close成功覆盖；旧 None/read限额/flags/版本/成功合同不变；after-close复用数字不误关；基类 detach 不绕成 override、不能给 OS 回收信用；实际 broker 状态和 next borrow 不是纯字段 mock。审查发现新真实问题需 withdrawal冻结→有效新RED→最小SOURCE→重新双审，不用旧 GREEN 抹问题。

实际SOURCE审查：fresh SPEC C0/I0/M0，独立54方法2.340s全绿；之后不同QUALITY C0/I0/M0，独立54方法2.508s全绿，均0F/E/skip。QUALITY另模拟darwin13收集/13skip，非原生非Linux运行信用。两者核实际SOURCE/TEST全文和broker链，冻结7de59a7a/ef8e45a7不变；未把作者回归或软件seams算自身native证明。

- [x] **Step 2：root 冻结实际源码/测试 SHA，运行唯一原完整预检，最多-j1。**

~~~bash
validation_log_dir=$(mktemp -d /tmp/icode-b2-preflight.XXXXXX)
printf '%s\n' "$validation_log_dir/typescript"
script -q -e -f -c 'CMAKE_BUILD_PARALLEL_LEVEL=1 MAKEFLAGS=-j1 .venv/bin/python -B -u scripts/preflight.py' "$validation_log_dir/typescript"
~~~

预期原三门全部通过、原日志真实 footer exit0；只有 runner 返回 0 或模型自述不能替代原日志。原完整入口若不输出全量 unittest 数量不猜数字。期间短轮询并每60秒内说明有变化进展，不能同时跑第二个 fullguard。完整期间 SOURCE/test冻结，文档可如实记录。当前 main 80f36ec 三个同SHA流程应由独立只读观察者收齐 terminal，再推下一片，避免取消未取证的运行；绿色 provenance/Pages 不等于 Reviewer/平台整体验收。

root唯一原完整guard已启动session96748、日志 `/tmp/icode-b2-preflight.6l2e9d/typescript`，06:28:48 UTC已实际观察启动，j1；最终结果待返回，不提前勾本步骤。当前main80f36ec三同SHA流程已实际全部终态取证，不取消流程。

该唯一guard随后实际exit0，原日志footer06:39:05 UTC，root06:39:15 UTC收完整三门PASS；源码/测试冻结不变。原入口未打印全量unittest数量，不借远端数字填空。前述“待返回”为启动时记录，不是当前仍未验；最终文档两轮原scanner/fresh单门与精确五路径index/工作字节核定后才发布。

- [x] **Step 3：root 记录实际证据并更新 live；最终文档修改后原 scanner 连续两轮与 fresh 单门。**

只记录真实命令、测试/失败/skip、SHA、原日志、双审意见、研究取舍，不预填完成/提交SHA。不重新请求或读取/回显模型 KEY；vendor固定版本不改。沿用 DESIGN 2026-10-12 CPython v3.11.15 PSF-2.0 / Codex固定提交 Apache-2.0 实际资料窗口，未查新HEAD不称“当前最新”。本片不承担 opaque socketpair/selector、monitor parser/listener、timeout竞争因果、S2/S3、Windows/macOS、模型六步和 R2/R3 整体。

~~~bash
.venv/bin/python -B /home/orbbec/.agents/skills/doc-contract-consistency-audit/scripts/check_consistency.py docs/nbl/plans/2026-10-12-linux-scope-temporary-cleanup.md docs/nbl/specs/2026-10-12-linux-scope-temporary-cleanup-design.md docs/agent-landscape-live.md
.venv/bin/python -B /home/orbbec/.agents/skills/doc-contract-consistency-audit/scripts/check_consistency.py docs/nbl/plans/2026-10-12-linux-scope-temporary-cleanup.md docs/nbl/specs/2026-10-12-linux-scope-temporary-cleanup-design.md docs/agent-landscape-live.md
.venv/bin/python -B scripts/preflight.py --only secrets
.venv/bin/python -B scripts/preflight.py --only submodule
git diff --check
~~~

每轮必须原 scanner raw finding0/exit0，不 whitelist不改scanner；若文档又变重新两轮。fresh secret/submodule须0，不读取敏感外部文件正文。若 scanner 本文问题，最小调整文档后保持可执行资产严格投影一致。

实际最终文档原scanner两轮各raw0/exit0，fresh secrets/submodule各PASS；本记录与勾选补入后再两轮和单门，不能用前一次校验给修改后字节信用。SOURCE/TEST仍7de59a7a/ef8e45a7，下一S2a文档不在本片index集合。

### Task 4：精确五路径发布 main 并直接继续下一有限片

**状态**

- [ ] 任务完成

**Dependencies:** Task 3
**Parallelizable:** No (全部证据与源字节冻结、当前 main 三流程 terminal已取证后)

- [ ] **Step 1：root 以五路径冻结 SHA，stage 后路径集与 index/工作字节逐一核一致。**

~~~bash
sha256sum src/icode/linux_task_scope.py tests/test_linux_scope_temporary_cleanup.py docs/nbl/specs/2026-10-12-linux-scope-temporary-cleanup-design.md docs/nbl/plans/2026-10-12-linux-scope-temporary-cleanup.md docs/agent-landscape-live.md
git add src/icode/linux_task_scope.py tests/test_linux_scope_temporary_cleanup.py docs/agent-landscape-live.md
git add -f docs/nbl/specs/2026-10-12-linux-scope-temporary-cleanup-design.md docs/nbl/plans/2026-10-12-linux-scope-temporary-cleanup.md
git diff --cached --check
git diff --cached --name-only | sort | diff - <(printf '%s\n' src/icode/linux_task_scope.py tests/test_linux_scope_temporary_cleanup.py docs/nbl/specs/2026-10-12-linux-scope-temporary-cleanup-design.md docs/nbl/plans/2026-10-12-linux-scope-temporary-cleanup.md docs/agent-landscape-live.md | sort)
for path in src/icode/linux_task_scope.py tests/test_linux_scope_temporary_cleanup.py docs/nbl/specs/2026-10-12-linux-scope-temporary-cleanup-design.md docs/nbl/plans/2026-10-12-linux-scope-temporary-cleanup.md docs/agent-landscape-live.md; do
    git show ":$path" | cmp -s "$path" - || exit 1
done
git diff --cached --stat
~~~

index初始为空已在Task1确认。任何新增未授权 staged路径或不同字节立即停止发布，不reset用户文件；修补资产空上下文尾随空白可用本差分的等价 -/+空行，必须重新RAM严格投影与最终doc两轮/单门；不重演正式RED信用。

- [ ] **Step 2：按用户阶段发布授权 commit/push，仅 main，不建分支。**

~~~bash
git commit -m "fix(linux): own scope temporary resource cleanup"
git push origin main
git rev-parse HEAD
git ls-remote origin refs/heads/main
git status --short
~~~

预期推送成功、remote完整SHA=实际HEAD、工作树与index无本片遗留。不预填SHA、不强推、不删未合分支。新同SHA CI/Windows provenance/Pages交独立只读观察，终态前不授平台信用。有限七维报告后 root直接继续已授权下一片，不因本片GREEN称 R2/R3完成。

## 七维自审（原PLAN生成时历史，不是实际代码完成）

- 语法/编译：完整测试与唯一源码差分已RAM compile/运行投影，不改磁盘 tests/SOURCE；正式语法门待执行。
- 依赖/调用链：scope九hook位点、actual broker cleanup_state与下一borrow连接；工厂/broker外部接口不改。
- 逻辑/边界：每取得FD一次，before/after close分账、未知sticky、身份重核与锁释放。
- 异常处理：原首KI/SE对象、普通异常选择、probe未得、detach故障后parent仍drain，未知数字不重试。
- 关联模块：五路径；原41/163与quota真实FD信号回归及原生skip明确。
- 兼容安全：默认None旧参数形状、read限额/walk flags/构造成功保持，不增权限依赖。
- 可运行性：RAM资产有限结果基线13方法26 assertion FAIL/0error/skip，投影13/13 GREEN/0error/skip（0.101s）；仅PLAN资产诊断，正式TDD、SOURCE双审、全预检和发布尚未执行。

---
**Execution Mode:** serial

本委派只准 DOCS；自动 handoff规则由root显式范围覆盖。完成本文与摘要后停止，root取得独立PLAN双审并另GO才启动fresh测试作者。

## 实际交付自检（B2有限片）

语法/编译：compileall-j1/diff通过；依赖/调用链：九hook与actual broker消费/下一borrow拒绝通过；逻辑/边界：一次close/数字复用/unknown sticky/锁释放通过；异常处理：批准首signal与probe/detach/parent矩阵通过；关联模块：作者/root新13+41+163+quota46回归均0F/E/skip；兼容安全：默认None/成功合同与原接口保持，无新权限/依赖；可运行性：fresh SOURCE双审零遗留、root原唯一完整三门通过。该报告不授新installed四格、跨平台、S2/S3或R2/R3整体验收；发布仍以实际index/commit/push为准，不预填SHA。
