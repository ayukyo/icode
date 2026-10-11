# Linux Helper Same-object Dispatch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development (recommended) or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Linux DENY observed 建立每次 dispatch 唯一 owner、同一已核验 helper 对象启动和可独立验收的私有候选；四格原生门完成后才能另行合流。

**Architecture:** 方案 A：复用 `LinuxHelperObject`、现有 observed 监督 core 和 native FD 清理，不复制 supervisor。wrapper 仅借用 owner；broker 最外层负责 close，最终 Popen 前核引用、对象、角色和 argv。保留普通、Git、Reviewer、leased 默认调用与 selector，候选失败不降级。

**Tech Stack:** Python 3.11+、标准库 unittest、Linux regular ELF/procfs、Landlock/seccomp USER_NOTIF、systemd user scope、现有原生 C helper。

---

## 基线、职责与执行边界

基线 `b923688`；设计 `docs/nbl/specs/2026-10-12-linux-helper-dispatch-design.md` SHA256 `b5eedcd775bbd0e64a9584b6e14bc3475fd976a330a5ee76b2b1818fe4e0af00`。执行前按符号核对，不能覆盖其它 writer 的变更。用户要求 main-only，不创建 worktree/branch；本轮仅交付计划，不自动实施。阶段由 root 完成 fresh SPEC→不同 QUALITY，零 C/I/M 后 root 在 main 做阶段 commit，不由计划 writer 提交或推送。

| 文件 | 唯一责任 |
| --- | --- |
| `src/icode/isolation.py` | 兼容默认借用字段；held wrapper 和 workspace/resource 元数据传递 |
| `src/icode/linux_task_scope.py` | Task1 scope重建保留借用；Task2独立sticky清理证据查询，不增加FD白名单或第二跳保证 |
| `src/icode/execution_broker.py` | 私有 adapter；单一 observed core 的 owner 外层、收尾、Popen 前合同 |
| `tests/test_linux_helper_dispatch.py` | 真实 regular ELF/FD 的软件行为 RED/GREEN；mock 不授原生身份信用 |
| `tests/native/linux_helper_fd_probe.c` | 首次 fstat 验证 EBADF；初始 FD 身份、DENY、ready/release 有界 payload |
| `scripts/probe_installed_linux_helper_object.py` | 实际安装包/宿主/拓扑、运行身份及 cleanup 原生证据；不依赖源码tests导入 |
| `scripts/run_native_wheel_ci.py`、`.github/workflows/ci.yml` | 复用实际安装venv，在现有四Linux native job执行新probe |
| `native/linux/icode_landlock.c` | 本方案不改；现有 close_range 已清 startup FD，保留原白名单 |
| `docs/agent-landscape-live.md` | root 独立研究刷新，本 writer 不修改 |

真实问题、现有实现和调用链已在设计确认。已回读 `PreparedCommand`、Landlock policy/metadata/runtime/execute-only/workspace/resource wrappers、owner active/closed/unknown、scope wrap/bind/configured/collected/close、observed/process cores、native main→close_range→CONFIGURED/ACK→supervise_task→fork init→waitpid→payload，以及现有 isolation、helper-object、violation/resource/product-quota/broker 测试。符号定位优先 `rg`；使用 `.venv/bin/python`，不使用系统 Python 3.10。

实施每个 Task 由一个 fresh writer 串行完成。以下代码块是精确增改资产；“保留原块”表示不修改已回读的原合同，不是重新实现或留空。任务内每次 RED 必须 0 collection ERROR、明确行为 assertion FAIL；缺字段、缺函数或签名 TypeError 不计 RED。先兼容脚手架，再加入正向行为测试，后实现。未跑原生四格不阻塞软件候选阶段，但禁止合流、ready 或原生 PASS。

## Task 1：兼容脚手架、held wrapper 和元数据

**Dependencies:** None
**Parallelizable:** No (同一 isolation/scope 元数据链，唯一 writer 串行)

- [x] 在 `PreparedCommand.__init__` 增加 `helper_object: object | None = None` keyword，并赋值 `self.helper_object = helper_object`。四个 wrapper 签名增加同名兼容 keyword：`wrap_policy_with_violation_receipt`、`wrap_policy_with_resource_receipt`、`_wrap_policy_with_metadata_roots`、`_wrap_with_metadata_roots`。先在这四个方法入口拒绝非 None：

```python
if helper_object is not None:
    raise RuntimeError("held helper dispatch is unavailable")
```

- [x] 新建 `tests/test_linux_helper_dispatch.py`，添加完整 fixture 和 wrapper 行为测试；此时收集成功且正向 held wrapper 的 assertion FAIL（用下面 `capture` 捕获拒绝，不把异常算有效 RED）。

```python
from __future__ import annotations
from contextlib import ExitStack
from dataclasses import replace
import errno
import hashlib
import os
from pathlib import Path
import shutil
import socket
import sys
import unittest
from unittest import mock

from tests._support import temp_workspace
from icode import execution_broker as broker
from icode.isolation import LandlockSandbox, PreparedCommand
from icode.linux_helper_object import LinuxHelperObject, LinuxHelperObjectError, open_linux_helper_object
from icode.linux_task_scope import LinuxTaskScope
from icode.sandbox_policy import NetworkMode, SandboxPolicy

REAL_CLOSE = os.close

def policy_for(root):
    return SandboxPolicy(1, "dispatch", "dispatch", "code", root, (root,),
                         (root,), (), (), NetworkMode.DENY, (), 8, 8, 2048, ())

def pair(root):
    # Real host ELF. No synthetic header and no platform.machine patch.
    source = Path("/usr/bin/true").resolve(strict=True)
    binary = root / "helper"
    shutil.copyfile(source, binary)
    binary.chmod(0o700)
    manifest = root / "helper.sha256"
    manifest.write_text(hashlib.sha256(binary.read_bytes()).hexdigest() + "\n", encoding="ascii")
    return binary, manifest

def capture(call):
    try:
        return call(), None
    except BaseException as error:
        return None, error

@unittest.skipUnless(sys.platform.startswith("linux"), "Linux real-FD software contract")
class TestHeldWrappers(unittest.TestCase):
    def test_held_wrappers_preserve_workspace_resource_scope_after_unlink(self):
        with temp_workspace() as raw, ExitStack() as stack:
            root = raw.resolve()
            binary, manifest = pair(root)
            owner = stack.enter_context(open_linux_helper_object(binary, manifest))
            helper_fd = owner.fileno()
            workspace_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
            stack.callback(REAL_CLOSE, workspace_fd)
            status = os.fstat(workspace_fd)
            identity = (status.st_dev, status.st_ino)
            endpoints = [socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET) for _ in range(2)]
            for endpoints_pair in endpoints:
                for endpoint in endpoints_pair:
                    stack.callback(endpoint.close)
            control, resource = endpoints[0][1], endpoints[1][1]
            binary.unlink()
            manifest.unlink()
            sandbox = LandlockSandbox(str(binary), manifest=str(manifest))
            with mock.patch("icode.native_helper.verify_native_helper", side_effect=AssertionError("path reopened")):
                wrapped, error = capture(lambda: sandbox.wrap_policy_with_resource_receipt(
                    ["/usr/bin/true", "--", "literal"], policy=policy_for(root),
                    control_socket=control, resource_socket=resource,
                    unit="icode-task-0123456789abcdef0123456789abcdef.scope",
                    workspace_fd=workspace_fd, workspace_identity=identity,
                    helper_object=owner))
            self.assertIsNone(error, "held branch must work without pathname selection")
            self.assertIs(wrapped.helper_object, owner)
            self.assertEqual(wrapped[0], f"/proc/self/fd/{helper_fd}")
            self.assertEqual(wrapped.pass_fds, (helper_fd, workspace_fd))
            self.assertEqual(wrapped.cwd, "/")
            scope = object.__new__(LinuxTaskScope)
            scope.version, scope.unit = 254, "icode-task-0123456789abcdef0123456789abcdef.scope"
            scoped = scope.wrap(wrapped)
            self.assertIs(scoped.helper_object, owner)
            self.assertEqual(scoped.pass_fds, wrapped.pass_fds)
            self.assertEqual(scoped.cwd, "/")
            self.assertEqual(scoped[scoped.index("--") + 1], wrapped[0])
            self.assertEqual(os.fstat(helper_fd).st_ino, owner._identity[1])
            self.assertTrue(os.fstat(workspace_fd))

    def test_held_policy_validation_still_rejects_unexpressible_policy(self):
        with temp_workspace() as raw:
            root = raw.resolve()
            binary, manifest = pair(root)
            with open_linux_helper_object(binary, manifest) as owner:
                host, control = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
                try:
                    changed = replace(policy_for(root), write_roots=(root / "nested",))
                    with self.assertRaises(ValueError):
                        LandlockSandbox(str(binary), manifest=str(manifest)).wrap_policy_with_violation_receipt(
                            ["true"], policy=changed, control_socket=control, helper_object=owner)
                finally:
                    host.close(); control.close()

    def test_old_prepared_command_defaults_to_no_helper_binding(self):
        self.assertIsNone(PreparedCommand(["true"], pass_fds=(), cwd="/").helper_object)
```

- [x] RED：`.venv/bin/python -m unittest tests.test_linux_helper_dispatch.TestHeldWrappers.test_held_wrappers_preserve_workspace_resource_scope_after_unlink -v`；期望正向 assertion FAIL，0 ERROR。
- [x] 删除入口拒绝骨架，按以下精确编辑完成 held 分支。`isolation.py` 不增加顶层 Linux-only import（Windows import兼容）。

```python
# _wrap_policy_with_metadata_roots: replace only self.prepare_policy(policy)
if helper_object is None:
    self.prepare_policy(policy)
else:
    from .linux_helper_object import LinuxHelperObject
    if type(helper_object) is not LinuxHelperObject:
        raise ValueError("invalid helper object binding")
    helper_object.fileno()
    self._checked_policy_workspace(policy)
# Its _wrap_with_metadata_roots call additionally forwards:
# helper_object=helper_object,

# _wrap_with_metadata_roots: replace the existing helper path/verify block
if helper_object is None:
    helper = Path(self.helper)
    if not helper.is_file():
        raise RuntimeError("Landlock helper is unavailable")
    if self.manifest is not None:
        from .native_helper import verify_native_helper
        if not verify_native_helper(helper, Path(self.manifest)):
            raise RuntimeError("Landlock helper integrity check failed")
    program = str(helper)
else:
    from .linux_helper_object import LinuxHelperObject
    if type(helper_object) is not LinuxHelperObject:
        raise ValueError("invalid helper object binding")
    descriptor = helper_object.fileno()
    if type(descriptor) is not int or descriptor < 3:
        raise ValueError("invalid helper descriptor")
    program = f"/proc/self/fd/{descriptor}"
# In the existing wrapped list, replace str(helper) with program.
# Replace its return [*wrapped, "--", *argv] with:
command = [*wrapped, "--", *argv]
return (PreparedCommand(command, pass_fds=(descriptor,), cwd=str(Path(workspace).resolve()),
                        helper_object=helper_object)
        if helper_object is not None else command)
```

`wrap_policy_with_violation_receipt` 的 `_wrap_policy_with_metadata_roots(...)` 调用传 `helper_object=helper_object`；`wrap_policy_with_resource_receipt` 的 violation 调用同样传；保留原 control/workspace/resource 输入与 alias 校验。`_with_workspace_object_fd` 在现有 identity 核验后、`index=wrapped.index("--")` 前增加下列合并，替换构造参数。

```python
borrowed = getattr(wrapped, "pass_fds", ())
if (type(borrowed) is not tuple
        or any(type(fd) is not int or fd < 3 for fd in borrowed)
        or len(set(borrowed)) != len(borrowed)
        or descriptor in borrowed):
    raise ValueError("invalid workspace descriptor roles")
# Existing PreparedCommand construction uses:
# pass_fds=(*borrowed, descriptor), cwd="/",
# helper_object=getattr(wrapped, "helper_object", None),
```

resource 的 `PreparedCommand(command, ...)` 和 `LinuxTaskScope.wrap` 的 `PreparedCommand(wrapped, ...)` 均增加 `helper_object=wrapped.helper_object` / `helper_object=helper.helper_object`。没有 workspace FD 时原 PreparedCommand 原样返回。未绑定旧 wrapper 不改路径核验；prepare_policy 本体不改。

- [x] GREEN：`.venv/bin/python -m unittest tests.test_linux_helper_dispatch.TestHeldWrappers tests.test_isolation tests.test_git_broker tests.test_linux_helper_object -q`；期望无失败；native 环境 skip 逐项记录为未验收。
- [x] root 审查并阶段提交：`31f42aecc7e56d2a6f2eeac3a376d0c753657d7d`（`feat(linux): preserve held helper binding through wrappers`）。六个精确路径包含本 Task 源码及已审设计、计划、研究记录；owner 工厂零修改，远端仅 main。

## Task 2：唯一 broker owner、角色与最终启动核校

**Dependencies:** Task 1
**Parallelizable:** No (single observed core 生命周期；不可并写 broker)

- [x] 先在 `_execute_linux_observed_command` 签名添加 `helper_object_mode: bool = False`，方法入口为 True 时返回 `ExecutionResult(None, "", 0, "isolation_unavailable", False, True, None, violation_observer_status="incomplete", payload_started=False)`。添加下述私有 adapter；此骨架使新测试可收集。

Task2新增scope查询也先提供可收集的兼容骨架（在本Task内被实际查询实现替换，不独立交付）：

```python
@property
def cleanup_state(self) -> str:
    return "confirmed"
```

scope真实before-close故障测试的RED是 `assertEqual(scope.cleanup_state, "unknown")`失败，不能把缺API/AttributeError算RED。

```python
def _execute_linux_helper_observed_candidate(
    argv: list[str], *, cwd: Path, sandbox: object, policy: SandboxPolicy,
    timeout: int | float, resource_mode: bool,
    output_limit_bytes: int | None = None,
    command_wrapper: Callable[..., list[str]],
    verification_cache_root: Path | None = None,
) -> ExecutionResult:
    return _execute_linux_observed_command(
        argv, cwd=cwd, sandbox=sandbox, policy=policy, timeout=timeout,
        output_limit_bytes=output_limit_bytes, command_wrapper=command_wrapper,
        resource_mode=resource_mode, verification_cache_root=verification_cache_root,
        helper_object_mode=True,
    )
```

- [x] 在同一测试文件添加以下真实 FD、软件监督 fixture 和行为测试。`run` mock 仅调用最终核校并模拟既有 core 结果；不会运行 `/usr/bin/true` 冒充 Landlock。

```python
class Monitor:
    def __init__(self, host):
        self.host, self._started, self.failed = host, True, False
        self.closes = 0
    def close(self):
        self.closes += 1
        return True
    def receipt(self):
        return None

class Scope:
    version = 254
    unit = "icode-task-0123456789abcdef0123456789abcdef.scope"
    environment = {"XDG_RUNTIME_DIR": "/run/user/1000", "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus"}
    cleanup_state = "confirmed"
    def __init__(self): self.closed = 0
    def wrap(self, helper): return LinuxTaskScope.wrap(self, helper)
    def collected(self, deadline): return True
    def close(self): self.closed += 1

class Resource:
    def __init__(self): self.closed = 0
    def wait(self, **kwargs): return True
    def close(self): self.closed += 1; return True
    def receipt(self):
        return {"channel_status": "complete", "payload_started": None, "terminal": "finished"}

@unittest.skipUnless(sys.platform.startswith("linux"), "Linux real-FD broker software contract")
class TestDispatchOwner(unittest.TestCase):
    def exercise(self, root, *, mutate=None, fault=None, timeout=1, close_fault=None,
                 candidate=True, wrapper_fault=None, monitor_fault=None,
                 resource_mode=False, scope_fault=None, receiver_fault=None, mutate_roles=None,
                 cleanup_stage=None, cleanup_fault=None, output_limit_bytes=None, workspace_fd=None,
                 endpoint_fault=None, scope_state="confirmed"):
        binary, manifest = pair(root)
        owners, closes, launches, channels = [], [], [], []
        real_factory = open_linux_helper_object
        def factory(*args):
            owner = real_factory(*args)
            descriptor = owner.fileno()
            owners.append((owner, descriptor))
            real_close = owner.close
            def close():
                closes.append(descriptor)
                real_close()
                if close_fault is not None:
                    raise close_fault
            owner.close = close
            return owner
        def channel():
            host, sender = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
            if endpoint_fault is not None and not channels:
                class UnknownHost(socket.socket):
                    attempts = 0
                    def close(self):
                        self.attempts += 1
                        raise endpoint_fault  # Before real close: socket stays live.
                host = UnknownHost(fileno=host.detach())
                host.original_fd = host.fileno()
            answer = (host, sender)
            channels.extend(answer)
            return answer
        task_scope, receiver = Scope(), Resource()
        task_scope.cleanup_state = scope_state
        if cleanup_stage in ("resource_close", "scope_close", "scope_collected"):
            target, attribute = ((receiver, "close") if cleanup_stage == "resource_close" else
                                 (task_scope, "close" if cleanup_stage == "scope_close" else "collected"))
            real_operation = getattr(target, attribute)
            def cleanup(*args, **kwargs):
                real_operation(*args, **kwargs)
                raise cleanup_fault
            setattr(target, attribute, cleanup)
        def monitor(host):
            if monitor_fault is not None: raise monitor_fault
            value = Monitor(host)
            if cleanup_stage == "monitor_close":
                original_close = value.close
                def close():
                    original_close(); raise cleanup_fault
                value.close = close
            return value
        def scoped(helper):
            if scope_fault is not None: raise scope_fault
            return Scope.wrap(task_scope, helper)
        task_scope.wrap = scoped
        def wrapper(argv, sender, *resource_args, helper_object=None):
            if wrapper_fault is not None:
                raise wrapper_fault
            if helper_object is None:
                return PreparedCommand(["/usr/bin/true"], pass_fds=(), cwd=str(root),
                                       helper_object=object())
            sandbox = LandlockSandbox(str(binary), manifest=str(manifest))
            workspace_identity = None
            if workspace_fd is not None:
                pinned = os.fstat(workspace_fd)
                workspace_identity = (pinned.st_dev, pinned.st_ino)
            workspace_binding = dict(workspace_fd=workspace_fd, workspace_identity=workspace_identity)
            if resource_args:
                prepared = sandbox.wrap_policy_with_resource_receipt(argv, policy=policy_for(root), control_socket=sender,
                    resource_socket=resource_args[0], unit=resource_args[1], helper_object=helper_object, **workspace_binding)
            else:
                prepared = sandbox.wrap_policy_with_violation_receipt(argv, policy=policy_for(root), control_socket=sender,
                    helper_object=helper_object, **workspace_binding)
            if mutate_roles is not None:
                mutate_roles(prepared, helper_object, sender, resource_args)
            if mutate is not None:
                mutate(prepared, helper_object)
            return prepared
        actual_core = broker._execute_policy_command
        def run(argv, **kwargs):
            if timeout != 1 or output_limit_bytes is not None:
                return actual_core(argv, **kwargs)
            hook = kwargs.get("before_spawn")
            if hook is not None:
                hook()
            launches.append((tuple(argv), kwargs["pass_fds"]))
            if fault is not None:
                raise fault
            return broker.ExecutionResult(0, "software-contract", 17, None, False, True, None)
        with mock.patch("icode.linux_helper_object.open_linux_helper_object", side_effect=factory), \
             mock.patch("icode.linux_seccomp_notify.create_seccomp_listener_handoff_channel", side_effect=channel), \
             mock.patch("icode.linux_seccomp_notify.LinuxSeccompViolationMonitor",
                        side_effect=monitor), \
             mock.patch("icode.linux_task_scope.LinuxTaskScope", return_value=task_scope), \
             mock.patch("icode.linux_task_resource.create_task_resource_channel", side_effect=channel), \
             mock.patch("icode.linux_task_resource.LinuxTaskResourceReceiver",
                        **({"side_effect": receiver_fault} if receiver_fault is not None else {"return_value": receiver})), \
             mock.patch.object(broker, "_execute_policy_command", side_effect=run):
            entry = broker._execute_linux_helper_observed_candidate if candidate else broker.execute_linux_violation_observed_command
            arguments = dict(cwd=root, sandbox=LandlockSandbox(str(binary), manifest=str(manifest)),
                             policy=policy_for(root), timeout=timeout, command_wrapper=wrapper,
                             output_limit_bytes=output_limit_bytes)
            if candidate:
                arguments["resource_mode"] = resource_mode
            result, error = capture(lambda: entry(["/usr/bin/true"], **arguments))
        self.last_scope, self.last_receiver = task_scope, receiver
        return result, error, owners, closes, launches, channels

    def assert_closed(self, fd):
        with self.assertRaises(OSError) as caught:
            os.fstat(fd)
        self.assertEqual(caught.exception.errno, errno.EBADF)

    def test_candidate_owns_once_and_launches_held_descriptor(self):
        with temp_workspace() as raw:
            result, error, owners, closes, launches, channels = self.exercise(raw.resolve())
            self.assertIsNone(error)
            self.assertIsNone(result.error, "candidate must dispatch rather than reject skeleton")
            self.assertEqual(len(owners), 1)
            owner, fd = owners[0]
            self.assertEqual(closes, [fd])
            self.assertEqual(launches[0][0][0], f"/proc/self/fd/{fd}")
            self.assertIn(fd, launches[0][1])
            self.assert_closed(fd)
            self.assertTrue(all(channel.fileno() == -1 for channel in channels))

    def test_dropped_swapped_alias_extra_and_payload_decoy_bindings_deny(self):
        def drop(prepared, owner): prepared.helper_object = None
        def swap(prepared, owner): prepared.helper_object = object()
        def duplicate(prepared, owner): prepared.pass_fds += prepared.pass_fds
        def extra(prepared, owner): prepared.pass_fds += (987654,)
        def payload_decoy(prepared, owner):
            prepared.extend([prepared[0]])
            prepared[0] = "/usr/bin/true"
        for mutate in (drop, swap, duplicate, extra, payload_decoy):
            with self.subTest(mutate=mutate.__name__), temp_workspace() as raw:
                result, error, owners, closes, launches, channels = self.exercise(raw.resolve(), mutate=mutate)
                self.assertIsNone(error)
                self.assertEqual(result.error, "isolation_unavailable")
                self.assertEqual(launches, [])
                self.assertEqual(closes, [owners[0][1]])
                self.assert_closed(owners[0][1])
                self.assertTrue(all(channel.fileno() == -1 for channel in channels))

    def test_ordinary_observed_rejects_unexpected_binding_without_factory(self):
        with temp_workspace() as raw:
            result, error, owners, closes, launches, channels = self.exercise(raw.resolve(), candidate=False)
            self.assertIsNone(error)
            self.assertEqual(result.error, "isolation_unavailable")
            self.assertEqual((owners, closes, launches), ([], [], []))
            self.assertTrue(all(channel.fileno() == -1 for channel in channels))

    def test_owner_covers_wrapper_monitor_core_failure_and_signals(self):
        for key in ("wrapper_fault", "monitor_fault", "fault"):
            for injected in (RuntimeError("private detail"), KeyboardInterrupt(), SystemExit(19)):
                with self.subTest(stage=key, fault=type(injected).__name__), temp_workspace() as raw:
                    result, error, owners, closes, launches, channels = self.exercise(raw.resolve(), **{key: injected})
                    self.assertEqual(len(owners), 1)
                    self.assertEqual(closes, [owners[0][1]])
                    self.assert_closed(owners[0][1])
                    self.assertTrue(all(channel.fileno() == -1 for channel in channels))
                    if not isinstance(injected, Exception) or key == "fault":
                        self.assertIs(error, injected)
                    else:
                        self.assertIsNone(error)
                        self.assertEqual(result.error, "isolation_unavailable")

    def test_owner_close_unknown_never_returns_success_and_preserves_signal(self):
        for primary in (None, KeyboardInterrupt(), SystemExit(23)):
            with self.subTest(primary=type(primary).__name__), temp_workspace() as raw:
                failure = LinuxHelperObjectError()
                result, error, owners, closes, launches, channels = self.exercise(
                    raw.resolve(), fault=primary, close_fault=failure)
                self.assertIsNone(result)
                self.assertIs(error, primary if primary is not None else failure)
                self.assertEqual(closes, [owners[0][1]])
                self.assertTrue(all(channel.fileno() == -1 for channel in channels))

    def test_unknown_live_close_does_not_retry_and_drains_all_other_resources(self):
        watched, attempts = [], []
        def remember(prepared, owner): watched.append(owner.fileno())
        def close(fd):
            if fd in watched:
                attempts.append(fd)
                raise OSError(errno.EIO, "before-close fault")
            return REAL_CLOSE(fd)
        with temp_workspace() as raw:
            try:
                with mock.patch("os.close", side_effect=close):
                    result, error, owners, closes, launches, channels = self.exercise(
                        raw.resolve(), mutate=remember, resource_mode=True)
                self.assertIsNone(result)
                self.assertIsInstance(error, LinuxHelperObjectError)
                owner, fd = owners[0]
                self.assertEqual(owner._state, "unknown")
                self.assertTrue(os.fstat(fd), "fault occurred before actual close; FD must remain live")
                self.assertEqual(attempts, [fd])
                with self.assertRaises(LinuxHelperObjectError): owner.close()
                self.assertEqual(attempts, [fd])
                self.assertTrue(all(channel.fileno() == -1 for channel in channels))
                self.assertEqual(self.last_receiver.closed, 1)
                self.assertEqual(self.last_scope.closed, 1)
            finally:
                for fd in watched:
                    try: REAL_CLOSE(fd)
                    except OSError: pass

    def test_scope_and_receiver_construction_faults_drain_owner_and_channels(self):
        for stage in ("scope_fault", "receiver_fault", "monitor_fault"):
            for injected in (RuntimeError("private"), KeyboardInterrupt(), SystemExit(31)):
                with self.subTest(stage=stage, injected=type(injected).__name__), temp_workspace() as raw:
                    result, error, owners, closes, launches, channels = self.exercise(
                        raw.resolve(), resource_mode=True, **{stage: injected})
                    self.assertEqual(launches, [])
                    self.assertEqual(closes, [owners[0][1]])
                    self.assert_closed(owners[0][1])
                    self.assertTrue(all(channel.fileno() == -1 for channel in channels))
                    self.assertEqual(self.last_scope.closed, 1)
                    if stage == "monitor_fault": self.assertEqual(self.last_receiver.closed, 1)
                    if isinstance(injected, Exception):
                        self.assertIsNone(error); self.assertEqual(result.error, "isolation_unavailable")
                    else: self.assertIs(error, injected)

    def test_real_channel_aliases_and_scope_payload_decoy_never_launch(self):
        def alias_control(prepared, owner, control, args): prepared.pass_fds += (control.fileno(),)
        def alias_resource(prepared, owner, control, args): prepared.pass_fds += (args[0].fileno(),)
        def workspace_alias(prepared, owner, control, args):
            index = prepared.index("--")
            fd = control.fileno()
            prepared[index:index] = ["--workspace-object-fd", str(fd), "0", "1"]
            prepared.pass_fds += (fd,)
        def payload_decoy(prepared, owner, control, args):
            prepared.extend([prepared[0]]); prepared[0] = "/usr/bin/true"
        for mutate in (alias_control, alias_resource, workspace_alias, payload_decoy):
            with self.subTest(mutate=mutate.__name__), temp_workspace() as raw:
                result, error, owners, closes, launches, channels = self.exercise(
                    raw.resolve(), resource_mode=True, mutate_roles=mutate)
                self.assertIsNone(error); self.assertEqual(result.error, "isolation_unavailable")
                self.assertEqual(launches, [])
                self.assert_closed(owners[0][1])
                self.assertTrue(all(channel.fileno() == -1 for channel in channels))

    def test_resource_cleanup_fault_attempts_remaining_resources_and_owner(self):
        for stage in ("resource_close", "monitor_close", "scope_collected", "scope_close"):
            for injected in (RuntimeError("private cleanup"), KeyboardInterrupt(), SystemExit(37)):
                with self.subTest(stage=stage, fault=type(injected).__name__), temp_workspace() as raw:
                    result, error, owners, closes, launches, channels = self.exercise(raw.resolve(),
                        resource_mode=True, cleanup_stage=stage, cleanup_fault=injected)
                    self.assertIsNone(result)
                    if stage == "scope_close" and isinstance(injected, Exception):
                        self.assertIsInstance(error, LinuxHelperObjectError)
                    else:
                        self.assertIs(error, injected)
                    self.assertEqual(closes, [owners[0][1]])
                    self.assert_closed(owners[0][1])
                    self.assertTrue(all(channel.fileno() == -1 for channel in channels))
                    self.assertEqual(self.last_receiver.closed, 1)
                    self.assertEqual(self.last_scope.closed, 1)

    def test_live_endpoint_close_fault_is_not_hidden_by_ordinary_body_error(self):
        real_socket_close = socket.socket.close
        for body in (RuntimeError("private ordinary wrapper"), KeyboardInterrupt(), SystemExit(41)):
            for endpoint_error in (OSError(errno.EIO, "private before-close"), KeyboardInterrupt()):
                channels = []
                with self.subTest(body=type(body).__name__, cleanup=type(endpoint_error).__name__), temp_workspace() as raw:
                    try:
                        result, error, owners, closes, launches, channels = self.exercise(raw.resolve(),
                            resource_mode=True, wrapper_fault=body, endpoint_fault=endpoint_error)
                        self.assertIsNone(result)
                        if not isinstance(body, Exception):
                            self.assertIs(error, body)
                        elif not isinstance(endpoint_error, Exception):
                            self.assertIs(error, endpoint_error)
                        else:
                            self.assertIsInstance(error, LinuxHelperObjectError)
                            self.assertNotIn("private", str(error))
                        self.assertEqual(launches, [])
                        unknown = channels[0]
                        self.assertEqual(unknown.attempts, 1)
                        self.assertGreaterEqual(unknown.original_fd, 3)
                        self.assertEqual(unknown.fileno(), -1, "unknown socket must relinquish destructor close")
                        self.assertTrue(os.fstat(unknown.original_fd), "before-close socket must still be live")
                        self.assertTrue(all(channel.fileno() == -1 for channel in channels[1:]))
                        self.assertEqual(self.last_scope.closed, 1)
                        self.assertEqual(closes, [owners[0][1]])
                        self.assert_closed(owners[0][1])
                    finally:
                        # Bypass the faulting override; do not give cleanup credit.
                        for channel in channels:
                            real_socket_close(channel)
                            descriptor = getattr(channel, "original_fd", None)
                            if descriptor is not None:
                                try: REAL_CLOSE(descriptor)
                                except OSError: pass

    def test_owner_covers_actual_process_core_input_early_returns(self):
        for options, expected in (({"timeout": float("nan")}, "invalid_timeout"),
                                  ({"output_limit_bytes": 0}, "invalid_output_limit")):
            with self.subTest(expected=expected), temp_workspace() as raw, \
                 mock.patch.object(broker.subprocess, "Popen") as started:
                result, error, owners, closes, launches, channels = self.exercise(raw.resolve(), **options)
                self.assertIsNone(error); self.assertEqual(result.error, expected)
                started.assert_not_called()
                self.assertEqual(closes, [owners[0][1]])
                self.assert_closed(owners[0][1])
                self.assertTrue(all(channel.fileno() == -1 for channel in channels))

    def test_each_dispatch_owner_closes_without_closing_session_workspace(self):
        with temp_workspace() as raw:
            root = raw.resolve()
            pinned = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
            try:
                for number in range(2):
                    result, error, owners, closes, launches, channels = self.exercise(root, workspace_fd=pinned)
                    self.assertIsNone(error); self.assertIsNone(result.error)
                    self.assertEqual(len(owners), 1); self.assert_closed(owners[0][1])
                    self.assertIn(pinned, launches[0][1], "workspace must actually be borrowed by dispatch")
                    self.assertIn("--workspace-object-fd", launches[0][0])
                    self.assertTrue(os.fstat(pinned), f"dispatch {number} stole session workspace")
            finally:
                REAL_CLOSE(pinned)

    def test_candidate_rejects_unconfirmed_or_unknown_scope_after_all_attempts(self):
        for state in ("unconfirmed", "unknown"):
            with self.subTest(state=state), temp_workspace() as raw:
                result, error, owners, closes, launches, channels = self.exercise(
                    raw.resolve(), resource_mode=True, scope_state=state)
                self.assertIsNone(result); self.assertIsInstance(error, LinuxHelperObjectError)
                self.assertEqual(self.last_scope.closed, 1)
                self.assertEqual(self.last_receiver.closed, 1)
                self.assertTrue(all(channel.fileno() == -1 for channel in channels))
                self.assertEqual(closes, [owners[0][1]]); self.assert_closed(owners[0][1])
```

- [x] RED：`.venv/bin/python -m unittest tests.test_linux_helper_dispatch.TestDispatchOwner.test_candidate_owns_once_and_launches_held_descriptor -v`；期望 `result.error` 的 assertion FAIL，0 ERROR。
- [x] 删除 candidate 拒绝骨架。在 `execution_broker.py` 增加下列完整最终校验函数，纯内部 consumer，不对模型暴露：

```python
def _check_held_helper_launch(wrapped, owner, *, policy, helper_index,
                            scope_prefix, channel_fds, launch_fds, argv_snapshot):
    from .isolation import PreparedCommand
    from .linux_helper_object import LinuxHelperObject
    if (type(owner) is not LinuxHelperObject or not isinstance(wrapped, PreparedCommand)
            or wrapped.helper_object is not owner or tuple(wrapped) != argv_snapshot):
        raise ValueError("invalid helper object binding")
    helper_fd = owner.fileno()  # regular and same dev/ino; dead/reused fails here.
    if type(helper_fd) is not int or helper_fd < 3:
        raise ValueError("invalid helper descriptor")
    if (type(helper_index) is not int or helper_index < 0
            or helper_index >= len(wrapped)
            or tuple(wrapped[:helper_index]) != scope_prefix
            or wrapped[helper_index] != f"/proc/self/fd/{helper_fd}"):
        raise ValueError("invalid helper program position")
    inner = wrapped[helper_index:]
    separator = inner.index("--")
    flags = inner[1:separator]
    roles = [helper_fd, *channel_fds]
    for flag, fd in zip(("--violation-control-fd", "--resource-control-fd"), channel_fds, strict=False):
        if flags.count(flag) != 1 or flags[flags.index(flag) + 1] != str(fd):
            raise ValueError("invalid channel role")
    if len(channel_fds) == 1 and "--resource-control-fd" in flags:
        raise ValueError("unexpected resource role")
    if "--workspace-fd" in flags:
        raise ValueError("unexpected Reviewer role")
    if "--workspace-object-fd" in flags:
        if flags.count("--workspace-object-fd") != 1:
            raise ValueError("duplicate workspace role")
        index = flags.index("--workspace-object-fd")
        raw_fd, raw_dev, raw_ino = flags[index + 1:index + 4]
        workspace_fd, device, inode = int(raw_fd), int(raw_dev), int(raw_ino)
        if (str(workspace_fd), str(device), str(inode)) != (raw_fd, raw_dev, raw_ino) or workspace_fd < 3:
            raise ValueError("invalid workspace role")
        pinned, current = os.fstat(workspace_fd), policy.workspace_root.lstat()
        if (not stat.S_ISDIR(pinned.st_mode) or not stat.S_ISDIR(current.st_mode)
                or (pinned.st_dev, pinned.st_ino) != (device, inode)
                or (current.st_dev, current.st_ino) != (device, inode)):
            raise ValueError("invalid workspace identity")
        roles.append(workspace_fd)
    expected = tuple(roles)
    if (type(wrapped.pass_fds) is not tuple or type(launch_fds) is not tuple
            or any(type(fd) is not int or fd < 3 for fd in launch_fds)
            or len(set(expected)) != len(expected)
            or len(set(launch_fds)) != len(launch_fds)
            or set(launch_fds) != set(expected)
            or set(wrapped.pass_fds) != set(expected) - set(channel_fds)
            or len(set(wrapped.pass_fds)) != len(wrapped.pass_fds)):
        raise ValueError("invalid helper descriptor roles")
```

校验错误只在调用点映射固定错误，不输出异常原文。若 flags 缺值产生 IndexError/解包错误，同样按启动合同拒绝；调用点统一捕获 `IndexError`、`OSError`、`RuntimeError`、`TypeError`、`ValueError`，不捕获信号。

- [x] 对原 `_execute_linux_observed_command` 做下面精确结构编辑。禁止复制原监督函数、新建第二套 run loop 或把 owner 放在 adapter/global/session：

1. 原 docstring 后加入 `owner = None`。将原整个函数体（从 Linux guard 至 `return outcome`）缩进到新增外层 `try`；外层唯一 `finally` 使用以下代码。type helper mode 在任何 filesystem/channel操作之前核为 bool，错误返回 `invalid_violation_scope`。

```python
finally:
    if owner is not None:
        active_exception = sys.exc_info()[1]
        try:
            owner.close()
        except BaseException as cleanup_error:
            from .linux_task_resource import _select_cleanup_error
            from .linux_helper_object import LinuxHelperObjectError
            if (isinstance(active_exception, Exception)
                    and not isinstance(active_exception, LinuxHelperObjectError)
                    and isinstance(cleanup_error, LinuxHelperObjectError)):
                raise cleanup_error  # Unknown cleanup is not hidden by ordinary body failure.
            selected = _select_cleanup_error(active_exception, cleanup_error)
            if selected is not active_exception:
                raise selected
```

2. 已有 resource/scope/channel 前置准备成功后，第二个 `try` 的第一行取得 owner；加入原有 fixed-error except 范围。工厂失败没有 owner，工厂已负责清理。输入/workspace/verification guard 保持先于工厂。timeout/output精确校验继续位于现有process core，兼容原错误码；即便它们早返，也不调用Popen或启动payload，已取得owner仍由外层finally关闭。这里的前置安全条件与设计一致，保留process core输入早返不授运行信用。

```python
if helper_object_mode:
    from .linux_helper_object import open_linux_helper_object
    if sandbox.manifest is None:
        raise RuntimeError("helper manifest is unavailable")
    owner = open_linux_helper_object(Path(sandbox.helper), Path(sandbox.manifest))
wrapper_keywords = {"helper_object": owner} if helper_object_mode else {}
```

3. 两个 `command_wrapper(...)` 调用增加 `**wrapper_keywords`；resource 模式先将结果保存为 `helper_command`，再 `wrapped=task_scope.wrap(helper_command)`。scope 前核 `helper_command[0]`，scope 后保存可信 helper位置。无 scope 为 0。只从 scope 生成的第一处 `--` 得出位置；完整外壳必须等于当前 `task_scope.wrap` 的固定生成结果（使用一次结果快照，不在 Popen 前再 wrap）。

```python
if resource_mode:
    helper_command = command_wrapper(argv, sender_control, resource_sender, task_scope.unit, **wrapper_keywords)
    wrapped = task_scope.wrap(helper_command)
    if helper_object_mode:
        helper_index = wrapped.index("--") + 1
        scope_prefix = tuple(wrapped[:helper_index])
        if (wrapped[0] != "/usr/bin/systemd-run" or tuple(wrapped[helper_index:]) != tuple(helper_command)
                or "--" in wrapped[:helper_index - 1]):
            raise ValueError("invalid trusted scope wrapping")
    else:
        helper_index, scope_prefix = 0, ()
else:
    wrapped = command_wrapper(argv, sender_control, **wrapper_keywords)
    helper_index, scope_prefix = 0, ()
if not helper_object_mode and getattr(wrapped, "helper_object", None) is not None:
    raise ValueError("unexpected helper binding")
argv_snapshot = tuple(wrapped)
```

4. 保留现有 `workspace_fds/channel_fds/launch_fds` 输入/重复检查。在 monitor 构造前 candidate 调用 `_check_held_helper_launch` 一次，拒绝错误进入原 `isolation_unavailable` 返回；`payload_started=False`（candidate 确知未启动）。保存 closure 再传 process core，最终一遍不得重新包装/合并：

```python
def before_spawn():
    _check_held_helper_launch(wrapped, owner, policy=policy, helper_index=helper_index,
                             scope_prefix=scope_prefix, channel_fds=channel_fds,
                             launch_fds=launch_fds, argv_snapshot=argv_snapshot)
if helper_object_mode:
    before_spawn()
# Existing _execute_policy_command call additionally uses:
# before_spawn=before_spawn if helper_object_mode else None,
```

在原observer outcome映射（当前407–416）保留旧allowlist，另增加candidate-only未启动错误豁免。替换 `if not observer_ok and error not in (...)` 的条件为下面完整条件；原旧allowlist内容逐字保留在 `preserved_errors`，普通mode不新增错误信用：

```python
preserved_errors = ("timeout", "output_limit", "cleanup_failed", "invalid_timeout",
                    "invalid_output_limit", "launch_failed")
candidate_not_started = (helper_object_mode and result.payload_started is False
                         and error in ("isolation_unavailable", "invalid_handoff"))
if not observer_ok and error not in preserved_errors and not candidate_not_started:
    error = "violation_observer_failed"
```

在process core所有输入早返的candidate调用中，原invalid_handoff结果需要可证明未启动：调用处若 `helper_object_mode and result.error == "invalid_handoff"`，执行 `result=replace(result, payload_started=False)`。没有Popen发生的合同由process core输入校验保证，不凭observer是否_started猜测。

5. 现有初始化旁增加 `monitor_closed = resource_closed = components_drained = False`；抽取原resource wait/close、monitor close为以下内部函数。正常finally先drain、再scope.collected、最后endpoints，保留旧次序；准备失败的close_endpoints也调用同一drain，确保receiver已建而monitor构造失败会清理。

```python
def drain_components(cleanup_error):
    nonlocal monitor_closed, resource_closed, components_drained
    if not components_drained:
        components_drained = True  # Drain once, even if close raises.
        for operation in ("resource_wait", "resource_close", "monitor_close"):
            try:
                if operation == "resource_wait" and resource is not None:
                    resource.wait(timeout_seconds=0.2)
                elif operation == "resource_close" and resource is not None:
                    resource_closed = resource.close()
                elif operation == "monitor_close" and monitor is not None:
                    monitor_closed = monitor.close()
            except BaseException as error:
                cleanup_error = _select_cleanup_error(cleanup_error, error)
    return cleanup_error
# Normal Popen-finally: replace old wait/close blocks with:
# cleanup_error = drain_components(None)
# then existing scope.collected, close_endpoints, error selection.
```

Popen 后 finally保留 scope.collected 和 close_endpoints 的全部attempt及 `_select_cleanup_error`，删除原局部 `monitor_closed=False/resource_closed=False` 重置和已移走的 wait/close。将 `close_endpoints` 全文替换如下；candidate清理错误独立于body普通异常收集，确保收尾全attempt后抛固定失败。旧模式保留既有优先关系；原信号优先，helper owner最后收尾且不重试。scope/observer/resource完整结果转换保持原实现。

```python
def close_endpoints() -> None:
    active_exception = sys.exc_info()[1]
    cleanup_error = drain_components(None if helper_object_mode else active_exception)
    for endpoint in (resource_sender, resource_host, sender_control, host_control):
        if endpoint is None:
            continue
        try:
            endpoint.close()
        except OSError as error:
            if helper_object_mode:
                cleanup_error = _select_cleanup_error(cleanup_error, error)
        except BaseException as error:
            cleanup_error = _select_cleanup_error(cleanup_error, error)
    if task_scope is not None:
        try:
            task_scope.close()
            if helper_object_mode and task_scope.cleanup_state != "confirmed":
                from .linux_task_scope import LinuxTaskScopeError
                raise LinuxTaskScopeError()
        except BaseException as error:
            cleanup_error = _select_cleanup_error(cleanup_error, error)
    if helper_object_mode:
        if cleanup_error is None:
            return
        # Signals keep their exact original object; an ordinary body exception
        # must never hide an independent unknown cleanup and yield cleanup_ok.
        if active_exception is not None and not isinstance(active_exception, Exception):
            return  # Existing unwinding propagates the original signal.
        if not isinstance(cleanup_error, Exception):
            raise cleanup_error
        from .linux_helper_object import LinuxHelperObjectError
        raise LinuxHelperObjectError() from None
    if cleanup_error is not None and cleanup_error is not active_exception:
        raise cleanup_error
```

- [x] `_execute_policy_command` 签名新增 `before_spawn: Callable[[], None] | None = None`。原 launch `try` 中先计算环境，后核校，再立即 Popen；before_spawn拒绝不调用 Popen、返回 `isolation_unavailable` / incomplete / payload_started=False。公共普通入口拒绝 Unexpected binding。

```python
# execute_policy_command: before delegating to _execute_policy_command
if getattr(argv, "helper_object", None) is not None:
    return ExecutionResult(None, "", 0, "invalid_handoff", False, True, None, payload_started=False)

# _execute_policy_command: replace only the beginning of its launch try
try:
    environment = (launch_env if launch_env is not None else
                   _policy_environment(policy.workspace_root, git_status=git_status))
    launch_options = {"pass_fds": pass_fds} if pass_fds else {}
    if before_spawn is not None:
        try:
            before_spawn()
        except (IndexError, OSError, RuntimeError, TypeError, ValueError):
            return ExecutionResult(None, "", 0, "isolation_unavailable", False, True, None,
                                   violation_observer_status="incomplete", payload_started=False)
    # Existing Popen follows immediately; replace its env expression with environment.
```

- [x] 添加 process core实际早返/final核校、dead/reused和会话独立测试（使用下列代码）。

```python
@unittest.skipUnless(os.name == "posix", "POSIX process core launch contract")
class TestFinalLaunchContract(unittest.TestCase):
    def test_final_check_follows_environment_and_denies_before_popen(self):
        with temp_workspace() as raw:
            root = raw.resolve()
            events = []
            def environment(*args, **kwargs):
                events.append("environment"); return {}
            def check():
                events.append("check"); raise ValueError("private final detail")
            with mock.patch.object(broker, "_policy_environment", side_effect=environment), \
                 mock.patch.object(broker.subprocess, "Popen") as launched:
                answer = broker._execute_policy_command(["/usr/bin/true"], cwd=root,
                    policy=policy_for(root), timeout=1, before_spawn=check)
            self.assertEqual(events, ["environment", "check"])
            self.assertEqual(answer.error, "isolation_unavailable")
            self.assertIs(answer.payload_started, False)
            launched.assert_not_called()

    def test_input_early_returns_are_real_and_never_call_final_hook(self):
        with temp_workspace() as raw:
            root = raw.resolve()
            for override, expected in (({"timeout": float("nan")}, "invalid_timeout"),
                                       ({"output_limit_bytes": 0}, "invalid_output_limit"),
                                       ({"pass_fds": (True,)}, "invalid_handoff")):
                with self.subTest(expected=expected), mock.patch.object(broker.subprocess, "Popen") as launch:
                    hook = mock.Mock()
                    options = dict(cwd=root, policy=policy_for(root), timeout=1, before_spawn=hook)
                    options.update(override)
                    result = broker._execute_policy_command(["/usr/bin/true"], **options)
                    self.assertEqual(result.error, expected)
                    hook.assert_not_called(); launch.assert_not_called()

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux real FD reuse")
    def test_dead_or_reused_owner_never_closes_foreign_descriptor(self):
        for reuse in (False, True):
            with self.subTest(reuse=reuse), temp_workspace() as raw:
                root = raw.resolve(); binary, manifest = pair(root)
                owner = open_linux_helper_object(binary, manifest)
                fd = owner.fileno(); REAL_CLOSE(fd)
                foreign = -1
                try:
                    if reuse:
                        foreign = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
                        if foreign != fd:
                            os.dup2(foreign, fd); REAL_CLOSE(foreign); foreign = fd
                    with self.assertRaises(LinuxHelperObjectError): owner.fileno()
                    with self.assertRaises(LinuxHelperObjectError): owner.close()
                    with self.assertRaises(LinuxHelperObjectError): owner.close()
                    if reuse: self.assertTrue(os.fstat(fd))
                finally:
                    if foreign >= 0: REAL_CLOSE(foreign)
```

- [x] 增加真正 observed core→环境构造后篡改→最后hook的集成负控。原monitor对象保持 `_started=False`（没有Popen/ACK），验证错误不被observer映射覆盖；真实owner与socket全部实际关闭。加入 `TestDispatchOwner`：

```python
    def test_observed_final_hook_preserves_not_started_error_after_environment_mutation(self):
        for mutation in ("argv", "binding", "extra-fd"):
            with self.subTest(mutation=mutation), temp_workspace() as raw:
                root = raw.resolve(); binary, manifest = pair(root)
                owners, prepared, endpoints = [], [], []
                real_factory = open_linux_helper_object
                real_environment = broker._policy_environment
                def factory(*args):
                    owner = real_factory(*args); owners.append((owner, owner.fileno())); return owner
                def channel():
                    pair_value = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
                    endpoints.extend(pair_value); return pair_value
                def wrap(argv, control, *, helper_object):
                    value = LandlockSandbox(str(binary), manifest=str(manifest)).wrap_policy_with_violation_receipt(
                        argv, policy=policy_for(root), control_socket=control, helper_object=helper_object)
                    prepared.append(value); return value
                def environment(*args, **kwargs):
                    result = real_environment(*args, **kwargs)
                    if mutation == "argv": prepared[0][0] = "/usr/bin/true"
                    elif mutation == "binding": prepared[0].helper_object = None
                    else: prepared[0].pass_fds += (987654,)
                    return result
                def monitor(host):
                    value = Monitor(host); value._started = False; return value
                with mock.patch("icode.linux_helper_object.open_linux_helper_object", side_effect=factory), \
                     mock.patch("icode.linux_seccomp_notify.create_seccomp_listener_handoff_channel", side_effect=channel), \
                     mock.patch("icode.linux_seccomp_notify.LinuxSeccompViolationMonitor", side_effect=monitor), \
                     mock.patch.object(broker, "_policy_environment", side_effect=environment), \
                     mock.patch.object(broker.subprocess, "Popen") as start:
                    result = broker._execute_linux_helper_observed_candidate(["true"], cwd=root,
                        sandbox=LandlockSandbox(str(binary), manifest=str(manifest)), policy=policy_for(root),
                        timeout=1, resource_mode=False, command_wrapper=wrap)
                start.assert_not_called()
                self.assertEqual(result.error, "isolation_unavailable")
                self.assertIs(result.payload_started, False)
                self.assertEqual(result.violation_observer_status, "incomplete")
                self.assertEqual(len(owners), 1); self.assert_closed(owners[0][1])
                self.assertTrue(all(endpoint.fileno() == -1 for endpoint in endpoints))
```

- [x] `linux_task_scope.py`增加最小只读 `cleanup_state`属性；旧`close()`签名和旧OSError吞处理不变，unknown记录不可消失、不重试已pop的FD。属性只回答本scope目录FD关闭证据，不等价于cgroup collected。构造器初始化 `_cleanup_unknown=False`；object.__new__旧fixture用getattr默认兼容。新增方法并替换 `_close_pins`：

```python
@property
def cleanup_state(self) -> str:
    if getattr(self, "_cleanup_unknown", False):
        return "unknown"
    if not self._lifecycle.acquire(blocking=False):
        return "unconfirmed"
    try:
        if getattr(self, "_cleanup_unknown", False):
            return "unknown"  # Recheck after acquiring; callback may just finish.
        return "unconfirmed" if self._fds else "confirmed"
    finally:
        self._lifecycle.release()

def _close_owned_descriptor(self, descriptor: int) -> None:
    try:
        os.close(descriptor)
    except BaseException:
        self._cleanup_unknown = True
        raise

def _close_pins(self) -> None:
    close_error = None
    while self._fds:
        descriptor = self._fds.pop()  # Never retry a possibly reused number.
        try:
            self._close_owned_descriptor(descriptor)
        except OSError:
            pass  # Legacy exception contract; cleanup_state still says unknown.
        except BaseException as error:
            close_error = _select_cleanup_error(close_error, error)
    if close_error is not None:
        raise close_error
```

`_configure_locked`的临时recheck descriptor `finally: os.close(descriptor)`改为 `finally: self._close_owned_descriptor(descriptor)`，配置失败路径已有 `_close_pins`也会记录unknown。锁忙close仍立即返回；candidate端点/组件全部attempt后查询unconfirmed固定失败，不能等待或假定callback日后会关好。callback释放锁后已有deferred close继续尝试未pop资源，unknown不能被重置为confirmed。

- [x] 真目录FD scope关闭负控（加本测试文件）；保持现有 `test_linux_product_task_quota` 的deferred/signal测试兼容：

```python
class TestScopeCleanupEvidence(unittest.TestCase):
    @unittest.skipUnless(sys.platform.startswith("linux"), "real Linux directory descriptors")
    def test_partial_before_close_failure_stays_unknown_and_never_retries(self):
        import threading
        with temp_workspace() as raw:
            scope = object.__new__(LinuxTaskScope)
            scope._fds = [os.open(raw, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC) for _ in range(3)]
            scope._lifecycle, scope._close_requested = threading.Lock(), threading.Event()
            descriptors = list(scope._fds); watched = descriptors[-1]; attempted = []
            def close(fd):
                attempted.append(fd)
                if fd == watched: raise OSError(errno.EIO, "before-close")
                REAL_CLOSE(fd)
            try:
                with mock.patch("icode.linux_task_scope.os.close", side_effect=close): scope.close()
                self.assertEqual(set(attempted), set(descriptors))
                self.assertTrue(os.fstat(watched)); self.assertEqual(scope.cleanup_state, "unknown")
                for fd in descriptors[:-1]:
                    with self.assertRaises(OSError): os.fstat(fd)
                scope.close(); self.assertEqual(len(attempted), 3)
                self.assertEqual(scope.cleanup_state, "unknown")
            finally:
                for fd in descriptors:
                    try: REAL_CLOSE(fd)
                    except OSError: pass

    @unittest.skipUnless(sys.platform.startswith("linux"), "real Linux deferred directory close")
    def test_active_callback_close_is_unconfirmed_then_confirmed_or_sticky_unknown(self):
        import threading
        for fault in (None, KeyboardInterrupt(), SystemExit(43)):
            with self.subTest(fault=type(fault).__name__), temp_workspace() as raw:
                scope = object.__new__(LinuxTaskScope)
                scope._fds = [os.open(raw, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)]
                scope._lifecycle, scope._close_requested = threading.Lock(), threading.Event()
                scope._owned = False
                descriptor = scope._fds[0]; entered, release = threading.Event(), threading.Event()
                caught = []
                def callback(deadline):
                    entered.set()
                    if not release.wait(1): raise RuntimeError("bounded callback expired")
                    scope._owned = True
                scope._configure_locked = callback
                def close(fd):
                    REAL_CLOSE(fd)
                    if fd == descriptor and fault is not None: raise fault
                def run():
                    try: scope.configured(0)
                    except BaseException as error: caught.append(error)
                try:
                    with mock.patch("icode.linux_task_scope.os.close", side_effect=close):
                        worker = threading.Thread(target=run); worker.start()
                        self.assertTrue(entered.wait(1)); scope.close()
                        self.assertEqual(scope.cleanup_state, "unconfirmed")
                        self.assertTrue(os.fstat(descriptor)); release.set(); worker.join(2)
                    self.assertFalse(worker.is_alive())
                    self.assertEqual(scope.cleanup_state, "confirmed" if fault is None else "unknown")
                    if fault is not None: self.assertIs(caught[0], fault)
                    with self.assertRaises(OSError): os.fstat(descriptor)
                finally:
                    release.set()
                    try: REAL_CLOSE(descriptor)
                    except OSError: pass
```

为覆盖configured失败自身drain，在 `test_partial_before_close_failure...`同类新增以scope `_membership=lambda: "/icode-task/supervisor"`、`_open_directory`返回已记录真实目录FD、首次 `os.fstat`抛`LinuxTaskScopeError`的调用；下面精确测试不得仅观察query字符串：

```python
    @unittest.skipUnless(sys.platform.startswith("linux"), "configured failure owns a real directory FD")
    def test_configured_failure_drain_keeps_unknown_evidence(self):
        import threading
        from icode.linux_task_scope import LinuxTaskScopeError
        with temp_workspace() as raw:
            scope = object.__new__(LinuxTaskScope)
            scope._fds, scope._identities = [], []
            scope.uid = os.getuid()
            scope._lifecycle, scope._close_requested = threading.Lock(), threading.Event()
            scope._membership = lambda: "/icode-task/supervisor"
            fd = os.open(raw, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
            try:
                with mock.patch("icode.linux_task_scope._open_directory", return_value=fd), \
                     mock.patch("icode.linux_task_scope.os.fstat", side_effect=LinuxTaskScopeError()), \
                     mock.patch("icode.linux_task_scope.os.close", side_effect=OSError(errno.EIO, "before-close")):
                    with self.assertRaises(LinuxTaskScopeError): scope.configured(0)
                self.assertTrue(os.fstat(fd)); self.assertEqual(scope._fds, [])
                self.assertEqual(scope.cleanup_state, "unknown")
                scope.close(); self.assertTrue(os.fstat(fd))
            finally: REAL_CLOSE(fd)
```

实施前调用链补全（root，2026-10-12；不改变公共入口或原生硬门）：最终 hook 同时核 argv、绑定和实际启动所用 cwd/pass_fds 元数据快照。候选的 on_spawn 与最终 drain 共用对象级单次 endpoint close 记录；before-real-close 失败不可重试，未知结果固定拒绝、首 signal 对象不变，继续尝试其余资源。scope 的 configured/configure_locked/collected 收尾沿现有 selector 保留原 signal；collected 临时目录 FD 关闭也记录 sticky unknown，保留既有 OSError/return None 合同。以上均须真实 FD / socket 行为断言 RED 后 GREEN；不把软件夹具当作 ACK、镜像身份或 cgroup GC 实测。

首轮源码 SPEC 补全（C0/I2/M0，尚未通过）：真实关闭 socket 及 raw-close 后目录 FD 复用负控证明，只有 argv 数字集合不足以核角色，且收尾可能误关 foreign FD。端点取得时须保存真实 fd/fstat 身份，启动初核/终核及关闭前均确认 live same-object；漂移记 unknown，不关闭或重试 foreign。owner 外层普通 body error 也不得隐藏固定 unknown 清理异常；首 KI/SystemExit 原对象及已有同级固定异常优先。上方 outer finally 示例已同步补全，此为已审资产的需求缺口，不将按旧示例实现归咎作者。修复须 RED→GREEN，再 fresh SPEC 复核通过后不同 QUALITY；不降低原生四格门。

后续 SPEC 补全：ambiguous socket close 本身失败后也必须 detach，防止 Python 析构函数绕过 attempt 计数再次 raw close。detach 不提供关闭成功信用，实际未知 FD 仍 live，状态不得升级；测试保存原 fd 验证并自行 REAL_CLOSE，不能用 fileno=-1 冒充关闭完成。源作者取得真实 GC 行为断言 RED（1 test / 3 failures / 0 ERROR）后最小修复；第三轮 fresh SPEC 完整复核 C0/I0/M0，独立 177 focused / 29.305s / 0 skip，并独立验证三种信号/普通故障 GC 后原 FD 仍 live。随后不同 QUALITY 97 项 / 51.993s / 0 skip 和 16 项独立角色负控通过，C0/I0/M0；root 冻结后实际 177 focused / 29.314s / 0 skip 通过。完整软件 preflight 已启动，终态尚待观察，未发布。以上均为软件证据，不授原生信用。

- [x] GREEN focused：`.venv/bin/python -m unittest tests.test_linux_helper_dispatch tests.test_execution_broker tests.test_linux_product_task_quota tests.test_linux_task_resource tests.test_linux_violation_receipt tests.test_linux_helper_object -q`。须记录未执行native prerequisite，不能把skip算通过。
- [x] 结果/故障映射自审：factory/wrap/scope/role/monitor准备错误→固定 isolation_unavailable且明确未启动；timeout/output_limit/launch_failed/invalid_timeout/invalid_output_limit/invalid_handoff保留；observer/resource/scope终态仍原合同；owner.close错误→固定异常、unknown不可冒充收回；KeyboardInterrupt/SystemExit原对象在其余清理后抛出。
- [x] root 双审/完整软件门后已阶段提交推送 main `574033a4df8311a569230bbd0522a0e1be717d8a`（`feat(linux): own and validate held helper dispatch`），远端仅 main。普通与公共 observed selector仍未接候选。

## Task 3：实际包四格原生 identity/FD 探针

**Dependencies:** Task 2
**Parallelizable:** No (先固定软件候选hash；独立readonly研究由root并行，不是第二writer)

- [x] 固定 Task 2候选 SHA，root 完整软件门通过后，创建下列原生fixture。无需改生产 C；helper启动FD由现有 close_range 关闭，禁止增加保留角色。首个FD观察严格在payload自身open/枚举前；运行库启动复用若使此FD非EBADF就是该格负结果，不能改为晚些时候再测。

```c
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

int main(int argc, char **argv) {
    if (argc != 8) return 2;
    int helper_fd = atoi(argv[1]);
    struct stat status;
    errno = 0;
    /* First descriptor operation: before opening or enumerating anything. */
    if (fstat(helper_fd, &status) != -1 || errno != EBADF) return 11;
    unsigned long long device = strtoull(argv[2], NULL, 10);
    unsigned long long inode = strtoull(argv[3], NULL, 10);
    int workspace_fd = atoi(argv[4]);
    unsigned long long workspace_device = strtoull(argv[5], NULL, 10);
    unsigned long long workspace_inode = strtoull(argv[6], NULL, 10);
    errno = 0;
    if (fstat(workspace_fd, &status) != -1 || errno != EBADF) return 21;
    /* No /proc read grant: scan the full current descriptor-number range.
     * Never open anything before this scan; first-fstat above is independent.
     */
    long cap = sysconf(_SC_OPEN_MAX);
    if (cap < 3 || cap > 1048576) return 12;
    for (int fd = 3; fd < cap; ++fd) {
        if (fstat(fd, &status) == 0 && (unsigned long long)status.st_dev == device
                && (unsigned long long)status.st_ino == inode) return 13;
        if (fstat(fd, &status) == 0 && (unsigned long long)status.st_dev == workspace_device
                && (unsigned long long)status.st_ino == workspace_inode) return 22;
    }
    errno = 0;
    int network = socket(AF_INET, SOCK_STREAM, 0);
    if (network >= 0) { close(network); return 14; }
    if (errno != EPERM) return 15;
    if (strstr(argv[7], "SCOPE") != NULL) {
        errno = 0;
        pid_t child = fork();
        if (child == 0) _exit(23);
        if (child >= 0 || errno != EAGAIN) return 19;
    }
    int ready = open("ready", O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
    if (ready < 0 || write(ready, "ready", 5) != 5 || close(ready) != 0) return 16;
    struct timespec start, now, delay = {.tv_sec = 0, .tv_nsec = 10000000};
    if (clock_gettime(CLOCK_MONOTONIC, &start) != 0) return 17;
    while (access("release", F_OK) != 0) {
        if (clock_gettime(CLOCK_MONOTONIC, &now) != 0 || now.tv_sec - start.tv_sec >= 4) return 18;
        nanosleep(&delay, NULL);
    }
    if (strstr(argv[7], "OUTPUT") != NULL) {
        for (;;) if (write(STDOUT_FILENO, "xxxxxxxxxxxxxxxx", 16) != 16) return 23;
    }
    puts(argv[7]);
    return 0;
}
```

- [x] 创建 `scripts/probe_installed_linux_helper_object.py`。固定以下运行身份算法，不新增生产pause/debug/权限：捕获实际Popen对象；立即 pin `/proc/PID`目录FD。无scope在完整observer握手和真实ready后、release前核 outer helper（`supervise_task`在waitpid保持该镜像）；scope在已认证CONFIGURED的 `LinuxTaskScope.configured`回调、既有ACK前核同一个Popen PID，并在ready后再次核第二跳。同一proc目录相对stat→exeFD fstat→stat核field22及状态、防PID复用；exe是内核magic link，允许跟随，不对它用O_NOFOLLOW。身份匹配是PASS必要条件而非单靠argv/owner证明。

```python
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from dataclasses import replace
import errno
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from icode import execution_broker as broker
from icode.isolation import LandlockSandbox
from icode.linux_helper_object import open_linux_helper_object
from icode.linux_task_scope import LinuxTaskScope
from icode.native_helper import linux_arch_from_machine, linux_elf_architecture
from icode.sandbox_policy import NetworkMode, SandboxPolicy

@contextmanager
def temp_workspace():
    with tempfile.TemporaryDirectory(prefix="icode-installed-dispatch-") as raw:
        yield Path(raw)

def policy_for(root):
    return SandboxPolicy(1, "dispatch", "dispatch", "code", root, (root,),
                         (root,), (), (), NetworkMode.DENY, (), 8, 8, 2048, ())

def stat_identity(directory):
    descriptor = os.open("stat", os.O_RDONLY | os.O_CLOEXEC, dir_fd=directory)
    try:
        raw = os.read(descriptor, 8192)
    finally:
        os.close(descriptor)
    close = raw.rfind(b")")
    if close < 0: raise ValueError("proc stat unavailable")
    fields = raw[close + 2:].split()
    # fields[0] is field 3 (state); fields[19] is field 22 (starttime).
    if len(fields) < 20 or fields[0] in (b"Z", b"X", b"x"):
        raise ProcessLookupError("not live")
    return fields[19]

def running_identity(process, directory, expected, deadline):
    try:
        if time.monotonic() >= deadline or process.poll() is not None:
            return "inconclusive"
        before = stat_identity(directory)
        executable = os.open("exe", os.O_RDONLY | os.O_CLOEXEC, dir_fd=directory)
        try:
            current = os.fstat(executable)
        finally:
            os.close(executable)
        after = stat_identity(directory)
        if before != after or process.poll() is not None or time.monotonic() >= deadline:
            return "inconclusive"
        return "pass" if (current.st_dev, current.st_ino) == expected else "fail"
    except (OSError, ValueError):
        return "inconclusive"

@unittest.skipUnless(sys.platform.startswith("linux"), "Linux installed-package native gate")
class TestInstalledHelperDispatch(unittest.TestCase):
    def probe(self, resource_mode, mutation):
        installed = LandlockSandbox.from_bundle()
        if installed is None:
            self.skipTest("inconclusive: real installed helper package unavailable; no native credit")
        source, manifest_source = Path(installed.helper), Path(installed.manifest)
        architecture = linux_arch_from_machine(platform.machine())
        self.assertEqual(linux_elf_architecture(source.read_bytes()[:64]), architecture)
        compiler = shutil.which("cc")
        if compiler is None:
            self.skipTest("inconclusive: native payload compiler unavailable; no native credit")
        if resource_mode and (os.getuid() == 0 or not Path(f"/run/user/{os.getuid()}/bus").exists()):
            self.skipTest("inconclusive: non-root user manager unavailable; no scope credit")
        with temp_workspace() as raw, ExitStack() as stack:
            root = raw.resolve(); workspace = root / "workspace"; workspace.mkdir()
            workspace_fd = os.open(workspace, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
            stack.callback(os.close, workspace_fd)
            workspace_status = os.fstat(workspace_fd)
            workspace_identity = (workspace_status.st_dev, workspace_status.st_ino)
            helper, manifest = root / "helper", root / "helper.sha256"
            shutil.copyfile(source, helper); helper.chmod(0o700)
            shutil.copyfile(manifest_source, manifest)
            payload = workspace / "fd-probe"
            subprocess.run([compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                str(Path(__file__).resolve().parents[1] / "tests/native/linux_helper_fd_probe.c"), "-o", str(payload)],
                check=True, capture_output=True, timeout=30)
            sandbox = LandlockSandbox(str(helper), manifest=str(manifest))
            processes, procdirs, observations, owner_fds = [], [], [], []
            expected = []
            native_policy = replace(policy_for(workspace), process_limit=1)
            real_popen = subprocess.Popen
            def launch(argv, **kwargs):
                process = real_popen(argv, **kwargs)
                # Manager version/show commands are not the dispatch process.
                if expected and (str(argv[0]).startswith("/proc/self/fd/")
                                 or (argv[0] == "/usr/bin/systemd-run" and "--scope" in argv)):
                    processes.append(process)
                    try:
                        directory = os.open(f"/proc/{process.pid}", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
                    except OSError:
                        directory = None
                    if directory is not None:
                        stack.callback(os.close, directory)
                    procdirs.append(directory)
                return process
            def factory(binary, digest):
                owner = open_linux_helper_object(binary, digest)
                fd = owner.fileno(); owner_fds.append(fd)
                current = os.fstat(fd); expected.append((current.st_dev, current.st_ino))
                try:
                    if mutation == "rename": helper.rename(root / "held-renamed")
                    elif mutation == "unlink": helper.unlink()
                    elif mutation == "replace":
                        helper.rename(root / "held-replaced")
                        # A real ELF decoy. It prints a distinguishable marker if selected.
                        decoy = root / "decoy.c"
                        decoy.write_text('#include <stdio.h>\nint main(void){puts("DECOY-STARTED");return 0;}\n')
                        subprocess.run([compiler, str(decoy), "-o", str(helper)], check=True,
                                       capture_output=True, timeout=30)
                except BaseException as error:
                    # Factory wrapper has not returned: broker owns nothing yet.
                    owner.__exit__(type(error), error, error.__traceback__)
                    raise
                return owner
            def wrap(argv, control, *resource_args, helper_object):
                status = os.fstat(helper_object.fileno())
                command = [str(payload), str(helper_object.fileno()), str(status.st_dev), str(status.st_ino),
                           str(workspace_fd), str(workspace_identity[0]), str(workspace_identity[1]),
                           "HELD-PAYLOAD-SCOPE" if resource_mode else "HELD-PAYLOAD"]
                if resource_args:
                    return sandbox.wrap_policy_with_resource_receipt(command, policy=native_policy,
                        control_socket=control, resource_socket=resource_args[0], unit=resource_args[1],
                        helper_object=helper_object, workspace_fd=workspace_fd, workspace_identity=workspace_identity)
                return sandbox.wrap_policy_with_violation_receipt(command, policy=native_policy,
                    control_socket=control, helper_object=helper_object,
                    workspace_fd=workspace_fd, workspace_identity=workspace_identity)
            real_configured = LinuxTaskScope.configured
            def configured(scope, deadline):
                real_configured(scope, deadline)
                self.assertEqual(scope._pid, processes[-1].pid)
                # Receiver._message authenticated SCM_CREDENTIALS against bind_process first.
                result = (running_identity(processes[-1], procdirs[-1], expected[0], deadline)
                          if procdirs[-1] is not None else "inconclusive")
                observations.append(("configured-before-ack", result))
                if result != "pass": raise RuntimeError("native identity gate unavailable")
            stack.enter_context(mock.patch.object(broker.subprocess, "Popen", side_effect=launch))
            stack.enter_context(mock.patch("icode.linux_helper_object.open_linux_helper_object", side_effect=factory))
            stack.enter_context(mock.patch.object(LinuxTaskScope, "configured", new=configured))
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(broker._execute_linux_helper_observed_candidate,
                    [str(payload)], cwd=workspace, sandbox=sandbox, policy=native_policy,
                    timeout=6, resource_mode=resource_mode, command_wrapper=wrap)
                try:
                    deadline = time.monotonic() + 3
                    while not (workspace / "ready").exists() and not future.done() and time.monotonic() < deadline:
                        time.sleep(0.01)
                    if (workspace / "ready").exists() and len(processes) == 1:
                        result = (running_identity(processes[0], procdirs[0], expected[0], deadline)
                                  if procdirs[0] is not None else "inconclusive")
                        observations.append(("payload-ready-before-release", result))
                    else:
                        observations.append(("payload-ready-before-release", "inconclusive"))
                finally:
                    (workspace / "release").touch()
                answer = future.result(timeout=8)
            live_workspace = os.fstat(workspace_fd)
            workspace_live = (live_workspace.st_dev, live_workspace.st_ino) == workspace_identity
            record = dict(architecture=architecture, kernel=platform.release(), topology="scope" if resource_mode else "no-scope",
                          workspace_live=workspace_live,
                          package_helper_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                          manifest_sha256=hashlib.sha256(manifest_source.read_bytes()).hexdigest(),
                          mutation=mutation, observations=observations, error=answer.error,
                          cleanup_ok=answer.cleanup_ok, scope_cleanup_ok=answer.scope_cleanup_ok,
                          pids=[p.pid for p in processes], systemd=subprocess.run(["/usr/bin/systemd-run", "--version"],
                              capture_output=True, check=False, timeout=2).stdout.decode(errors="replace").splitlines()[:1])
            print(json.dumps(record, sort_keys=True))
            self.assertNotIn("DECOY-STARTED", answer.output)
            self.assertEqual(len(processes), 1)
            self.assertTrue(all(p.returncode is not None for p in processes), "broker did not reap its own child")
            self.assertTrue(workspace_live)
            self.assertEqual((live_workspace.st_dev, live_workspace.st_ino), workspace_identity)
            self.assertTrue(answer.cleanup_ok)
            if resource_mode: self.assertIs(answer.scope_cleanup_ok, True)
            for fd in owner_fds:
                with self.assertRaises(OSError) as caught: os.fstat(fd)
                self.assertEqual(caught.exception.errno, errno.EBADF)
            if any(result == "fail" for _, result in observations):
                self.fail("confirmed-negative: running helper is a different object")
            if any(result == "inconclusive" for _, result in observations):
                # Real helper/payload/cleanup errors remain FAIL; observation
                # unavailability alone can be inconclusive. CONFIGURED rejection
                # specifically caused by an unavailable exe observation is unknown.
                identity_blocked = resource_mode and observations[0] == ("configured-before-ack", "inconclusive")
                if not identity_blocked:
                    self.assertIsNone(answer.error)
                    self.assertEqual(answer.exit_code, 0)
                    self.assertIn("HELD-PAYLOAD", answer.output)
                    self.assertTrue(answer.cleanup_ok)
                self.skipTest("inconclusive: running identity/window unavailable; no native credit")
            self.assertIsNone(answer.error)
            self.assertEqual(answer.exit_code, 0)
            self.assertIn("HELD-PAYLOAD", answer.output)
            self.assertTrue(answer.cleanup_ok)
            self.assertEqual(answer.violation_observer_status, "complete")
            self.assertIsNotNone(answer.violation_receipt)
            if resource_mode:
                self.assertIs(answer.scope_cleanup_ok, True)
                self.assertEqual(answer.resource_receipt["channel_status"], "complete")

    def test_no_scope_actual_package_identity_and_fd_boundary(self):
        for mutation in ("none", "rename", "unlink", "replace"):
            with self.subTest(mutation=mutation): self.probe(False, mutation)

    def test_scope_actual_package_second_hop_identity_and_fd_boundary(self):
        for mutation in ("none", "rename", "unlink", "replace"):
            with self.subTest(mutation=mutation): self.probe(True, mutation)
```

在上述probe的`stack.enter_context`完成后，把`with ThreadPoolExecutor`到该次最后resource receipt断言整个块缩进到以下循环内，除此不重写其内容。每轮恢复实际包字节、清空该dispatch观测，复用同一个真实workspace pin。第二轮不新建workspace FD，不借旧probe代签；记录加`dispatch_number`，既有`workspace_live`来自发布记录前实际fstat和identity比较，两个owner都必须在该轮末尾EBADF。

```python
for dispatch_number in range(2):
    shutil.copyfile(source, helper); helper.chmod(0o700)
    shutil.copyfile(manifest_source, manifest)
    for marker in (workspace / "ready", workspace / "release"):
        marker.unlink(missing_ok=True)
    processes.clear(); procdirs.clear(); observations.clear(); owner_fds.clear(); expected.clear()
    # Indent existing with ThreadPoolExecutor through receipt assertions here.
```

循环里的记录`dict(...)`仅增加`dispatch_number=dispatch_number`，保留实际派生的`workspace_live=workspace_live`。fixture首helper fstat后、任何open前另核原workspace数字EBADF，并对原workspace dev/ino也做初始全FD扫描，验证CLOEXEC与没有目录capability；宿主在每次dispatch末尾fstat同一pin仍可用。copy目标只在本probe独占temp根内，前轮真实进程已由brokerreap，不修改实际安装包。

该测试patch只观测已有组件，不替换native helper、不patch宿主架构、不提供额外权限；probe复制实际安装包字节做路径变更，源包hash关联证据。`from_bundle`返回None属于package prerequisite未达，不得借source编译包替代安装包签字。观察proc目录由ExitStack全部关闭；真实进程仍由broker负责回收。payload无/proc read grant，首fstat后扫描完整当前FD编号范围（最多1M次fstat，不open），扫描耗时计入broker启动预算，ready/release的4s窗口从扫描后开始；慢宿主超时属于未通过，不能缩小扫描范围伪造通过。每个scope payload还实测cap=1 fork得到EAGAIN。故障测试自身保存真实清理方法，RED失败不得残留真实进程，也不得帮broker补清后授PASS。

- [x] 原生负控 RED：测试观测函数先以持有 `/usr/bin/true` owner的identity核本测试进程，完整stat/exe读取必须得到 `fail`；拒绝“只有match测试”。另外将观察deadline置过去必须 `inconclusive`。以下加入本文件：

```python
class TestIdentityEvidence(unittest.TestCase):
    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux procfs identity")
    def test_real_wrong_object_is_negative_and_elapsed_window_is_unknown(self):
        class Current:
            pid = os.getpid()
            def poll(self): return None
        directory = os.open(f"/proc/{os.getpid()}", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        foreign = os.open("/usr/bin/true", os.O_RDONLY | os.O_CLOEXEC)
        try:
            status = os.fstat(foreign)
            expected = (status.st_dev, status.st_ino)
            self.assertEqual(running_identity(Current(), directory, expected, time.monotonic() + 1), "fail")
            self.assertEqual(running_identity(Current(), directory, expected, time.monotonic() - 1), "inconclusive")
        finally:
            os.close(foreign); os.close(directory)
```

- [x] 在同一probe末尾加入严格runner：skip/inconclusive返回77，失败返回1，只有全部实测成功返回0。安装CI不允许77转PASS。

```python
def main():
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful(): return 1
    if result.skipped: return 77
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

- [x] 在 `scripts/run_native_wheel_ci.py` 的 `_run`签名加入 `publish_output: bool = False, timeout_seconds: int = 180`，subprocess timeout使用timeout_seconds。仅新stage在处理returncode/skip之前解析发布受控JSON（失败也保留记录），其它stage输出合同不变。新增模块imports `hashlib,json,re`，并加入下列过滤器；不发布raw stdout、argv、payload、异常正文或绝对路径。仅新stage失败stderr输出固定受控摘要（长度与是否截断），其它stage沿原最多1800字符诊断，不扩大。

```python
def _publish_helper_dispatch_records(output: str) -> None:
    enums = {
        "architecture": {"x86_64", "arm64"}, "topology": {"scope", "no-scope"},
        "mutation": {"none", "rename", "unlink", "replace"},
        "scenario": {"bad_ack", "missing_ack", "observer_start", "observer_runtime", "observer_close",
                     "resource_start", "resource_configured", "resource_close", "scope_close_unknown",
                     "timeout", "output_limit", "launch_failed", "keyboardinterrupt", "systemexit", "helper_close_unknown"},
        "exception": {None, "LinuxHelperObjectError", "KeyboardInterrupt", "SystemExit"},
    }
    booleans = {"cleanup_ok", "scope_cleanup_ok", "workspace_live", "process_closed", "channels_closed", "threads_stopped"}
    hashes = {"package_helper_sha256", "manifest_sha256"}
    errors = {None, "raised", "timeout", "output_limit", "launch_failed", "proxy_setup_failed", "read_failed",
              "violation_observer_failed", "resource_channel_failed", "scope_cleanup_failed", "resource_setup_failed",
              "resource_cleanup_failed", "isolation_unavailable", "cleanup_failed"}
    for line in output.splitlines():
        if len(line) > 8192:
            print("::notice::helper-dispatch-record rejected=oversized"); continue
        try:
            record = json.loads(line)
        except (ValueError, TypeError):
            print("::notice::helper-dispatch-record rejected=not-json"); continue
        if type(record) is not dict:
            print("::notice::helper-dispatch-record rejected=not-object"); continue
        safe = {}
        for name, allowed in enums.items():
            value = record.get(name)
            if name in record and (type(value) is str or value is None) and value in allowed:
                safe[name] = value
        for name in booleans:
            value = record.get(name)
            if name in record and (type(value) is bool or (name == "scope_cleanup_ok" and value is None)): safe[name] = value
        for name in hashes:
            value = record.get(name)
            if type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value): safe[name] = value
        value = record.get("error")
        if (type(value) is str or value is None) and value in errors: safe["error"] = value
        value = record.get("dispatch_number")
        if type(value) is int and value in (0, 1): safe["dispatch_number"] = value
        value = record.get("kernel")
        if type(value) is str and re.fullmatch(r"[0-9A-Za-z.+_-]{1,128}", value): safe["kernel"] = value
        value = record.get("pids")
        if type(value) is list and len(value) <= 4 and all(type(pid) is int and pid > 1 for pid in value): safe["pids"] = value
        for name in ("owner_states", "scope_states"):
            value = record.get(name)
            if type(value) is list and len(value) <= 4 and all(type(item) is str and item in
                    ("active", "closed", "unknown", "confirmed", "unconfirmed") for item in value): safe[name] = value
        value = record.get("observations")
        if type(value) is list and len(value) <= 4 and all(type(pair) is list and len(pair) == 2 and
                type(pair[0]) is str and type(pair[1]) is str and
                pair[0] in ("configured-before-ack", "payload-ready-before-release") and
                pair[1] in ("pass", "fail", "inconclusive") for pair in value): safe["observations"] = value
        value = record.get("systemd")
        if type(value) is list and len(value) == 1 and type(value[0]) is str:
            match = re.match(r"systemd ([0-9]+)(?:\s|$)", value[0])
            if match: safe["systemd_version"] = int(match.group(1))
        if safe.get("topology") in ("scope", "no-scope") and safe.get("architecture") in ("x86_64", "arm64"):
            print("helper-dispatch-record " + json.dumps(safe, sort_keys=True))
        else:
            print("::notice::helper-dispatch-record rejected=missing-identity")
```

`_run`在subprocess返回后、任何returncode分支之前插入下列完整代码；不要在success分支再重复发布。仅新stage失败转固定错误，不将payload/tracebackstdout回显，其他stage原异常处理保留。

```python
if publish_output:
    _publish_helper_dispatch_records(result.stdout)
    if result.returncode != 0:
        print("::notice::helper-dispatch-stderr bytes=" + str(len(result.stderr.encode("utf-8", errors="replace")))
              + " bounded_summary=true")
        raise RuntimeError(f"{stage} exit={result.returncode}: helper_dispatch_probe_failed")
```

在 `tests/test_linux_helper_dispatch.py` 增加受控publisher失败记录行为测试；复用本测试文件mock/capture，不增加依赖。测试资产在Task3脚本完成后执行，old `_run`先补兼容publish_output keyword但不发布的骨架时，此测试必须在输出assertion RED而非TypeError。

```python
class TestInstalledProbeRecordPublishing(unittest.TestCase):
    def test_failed_new_stage_publishes_safe_json_before_fixed_failure(self):
        import contextlib
        import importlib.util
        import io
        import json
        import subprocess
        source = Path(__file__).resolve().parents[1] / "scripts/run_native_wheel_ci.py"
        spec = importlib.util.spec_from_file_location("native_wheel_ci_dispatch_test", source)
        subject = importlib.util.module_from_spec(spec); spec.loader.exec_module(subject)
        record = {"architecture": "x86_64", "topology": "no-scope", "mutation": "none",
                  "observations": [["payload-ready-before-release", "fail"]], "error": None,
                  "ignored_payload": "PRIVATE-PAYLOAD-SENTINEL"}
        completed = subprocess.CompletedProcess([], 1, stdout=json.dumps(record) + "\nPRIVATE-PAYLOAD-SENTINEL\n",
                                                stderr="PRIVATE-STDERR-SENTINEL")
        output = io.StringIO()
        with mock.patch.object(subject.subprocess, "run", return_value=completed), contextlib.redirect_stdout(output):
            result, error = capture(lambda: subject._run("probe installed Linux helper same-object dispatch",
                ["fixed-program"], cwd=Path("/"), publish_output=True))
        self.assertIsNone(result); self.assertIsInstance(error, RuntimeError)
        self.assertIn("helper-dispatch-record", output.getvalue())
        self.assertIn('"fail"', output.getvalue())
        self.assertNotIn("PRIVATE-PAYLOAD-SENTINEL", output.getvalue() + str(error))
        self.assertNotIn("PRIVATE-STDERR-SENTINEL", output.getvalue() + str(error))
        self.assertIn("helper_dispatch_probe_failed", str(error))
```

Focused：`.venv/bin/python -m unittest tests.test_linux_helper_dispatch.TestInstalledProbeRecordPublishing -v`，期望1PASS，不能legacy publishersuccess代签。

下列新stage调用位于既有 installed workspace-object probe之后；复用刚安装的wheel/venv和去PYTHONPATH环境，`-I`不从源码导入icode；实际wheel SHA另打印到日志。

```python
import hashlib  # module imports
# In main, immediately before this new _run:
print("installed-linux-helper-dispatch wheel_sha256=" + hashlib.sha256(wheels[0].read_bytes()).hexdigest())
_run("probe installed Linux helper same-object dispatch",
     [str(python), "-I", str(repository / "scripts/probe_installed_linux_helper_object.py")],
     cwd=root, env=clean_env, publish_output=True, timeout_seconds=600)
```

`.github/workflows/ci.yml`现有 `native-probe`的4Linux runner为 `ubuntu-latest`、`ubuntu-24.04-arm`、`ubuntu-22.04`、`ubuntu-22.04-arm`，每个都执行 `Build and verify installed Linux wheel`→`python scripts/run_native_wheel_ci.py`。只重命名step为 `Build installed Linux wheel and verify same-object helper dispatch`，不增runner/服务/权限；该step新增调用是接线，不把旧resolver probe算新信用。运行 `.venv/bin/python -I scripts/probe_installed_linux_helper_object.py`为本机实际安装包诊断；CI由现有wheel临时venv调用。

- [x] 每格实际 x86_64或aarch64，不借QEMU/patch machine授对应真实宿主信用。root软件candidate发布后追同一新SHA这4jobs原始日志，提取上述新stage每种拓扑与四种路径变化观察，不仅看job绿色。保存stdout、候选SHA/源码hash、wheel/helper/manifesthash、发行版/内核/systemd版本、proc窗口/实际PopenPID、进程FD终态和回执。没有执行/77/缺字段皆未验收，保持私有候选。后续 `1e2e4ab` 四格已实际通过，详见末尾与持续对照新台账；仍未实施公共合流。

| 硬门 | 初始状态 | PASS条件 |
| --- | --- | --- |
| Linux x64 / x86_64 no-scope | 未执行，未验收 | installed ELF、ready窗口运行identity、EBADF/无对象FD、原DENY、正常收尾全部通过 |
| Linux x64 / x86_64 scope | 未执行，未验收 | 上述 + authenticated CONFIGURED-before-ACK同PID/时限 + ready第二跳 + quota/scope回收 |
| Linux ARM64 / aarch64 no-scope | 未执行，未验收 | 实际ARM64同样证据；不能用x64替代 |
| Linux ARM64 / aarch64 scope | 未执行，未验收 | 实际ARM64及scope第二跳全部证据 |

原支持Ubuntu22/24的发行版/内核/systemd组合分别记录，不扩大或削减原支持声明。skip/inconclusive都未验收；真实可读wrong identity为FAIL（confirmed-negative），不是inconclusive。scope identity失败时不ACK、不取消scope、不旧path fallback。若outer生命周期/proc读权限实证不成立，停在私有候选，设计返审，不新增pause/API/权限。

- [ ] Legacy原生回归：`.venv/bin/python -m unittest tests.test_linux_violation_receipt tests.test_linux_task_resource tests.test_linux_product_task_quota tests.test_linux_pidns_cleanup -q`。这些旧模块不设置helper_object_mode=True，只给兼容回归信用。新candidate原生故障由下列同脚本资产真实执行，命令仍是安装venv的 `python -I scripts/probe_installed_linux_helper_object.py`，不可由旧模块代签。

新增 `TestInstalledCandidateFaults`到脚本（放在main之前）。所有mock仅注入具体host故障，Popen/native包/握手/进程监督仍真实；每种dispatch只有一个factory owner。坏ACK修改现有ACK常量，缺ACK阻止现有ack方法，均不新增生产gate。预期异常/错误不是native正控PASS；记录故障成功拒绝与进程/FD终态，unknown-close明确保留unknown，测试最后保存realclose清残留。

```python
class TestInstalledCandidateFaults(unittest.TestCase):
    def run_fault(self, resource_mode, scenario):
        from icode import linux_seccomp_notify as notify
        from icode import linux_task_resource as resources
        import socket
        import threading
        sandbox = LandlockSandbox.from_bundle()
        if sandbox is None: self.skipTest("inconclusive: installed native package unavailable")
        self.assertEqual(linux_elf_architecture(Path(sandbox.helper).read_bytes()[:64]),
                         linux_arch_from_machine(platform.machine()))
        if resource_mode and (os.getuid() == 0 or not Path(f"/run/user/{os.getuid()}/bus").exists()):
            self.skipTest("inconclusive: non-root user manager unavailable")
        compiler = shutil.which("cc")
        if compiler is None: self.skipTest("inconclusive: C compiler unavailable")
        real_popen, real_stop, real_close = subprocess.Popen, broker._stop_group, os.close
        monitor_start = notify.LinuxSeccompViolationMonitor.start
        monitor_close = notify.LinuxSeccompViolationMonitor.close
        record_original = notify.LinuxSeccompViolationMonitor._record
        acknowledge_original = notify.LinuxSeccompViolationMonitor._acknowledge_if_healthy
        resource_close = resources.LinuxTaskResourceReceiver.close
        scope_configured = LinuxTaskScope.configured
        owner_factory = open_linux_helper_object
        monitors, receivers, scopes, processes, endpoints, owners, leaked = [], [], [], [], [], [], []
        hits, directory_fds = [], set()
        injected = KeyboardInterrupt() if scenario == "keyboardinterrupt" else SystemExit(47)
        with temp_workspace() as raw, ExitStack() as stack:
            root = raw.resolve(); workspace = root / "workspace"; workspace.mkdir()
            workspace_fd = os.open(workspace, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
            stack.callback(real_close, workspace_fd)
            workspace_status = os.fstat(workspace_fd)
            identity = (workspace_status.st_dev, workspace_status.st_ino)
            payload = workspace / "fault-payload"
            subprocess.run([compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                str(Path(__file__).resolve().parents[1] / "tests/native/linux_helper_fd_probe.c"), "-o", str(payload)],
                check=True, capture_output=True, timeout=30)
            policy = replace(policy_for(workspace), process_limit=1, wall_timeout_seconds=6, output_limit_bytes=256)
            def factory(*args):
                owner = owner_factory(*args); owners.append((owner, owner.fileno())); return owner
            notify_channel = notify.create_seccomp_listener_handoff_channel
            resource_channel = resources.create_task_resource_channel
            def channel(factory):
                answer = factory(); endpoints.extend(answer); return answer
            def monitor_factory(*args):
                value = original_monitor(*args); monitors.append(value); return value
            def receiver_factory(*args, **kwargs):
                value = original_receiver(*args, **kwargs); receivers.append(value); return value
            def scope_factory(*args, **kwargs):
                value = original_scope(*args, **kwargs); scopes.append(value); return value
            original_monitor = notify.LinuxSeccompViolationMonitor
            original_receiver = resources.LinuxTaskResourceReceiver
            original_scope = LinuxTaskScope
            def launch(argv, **kwargs):
                dispatch = str(argv[0]).startswith("/proc/self/fd/") or (argv[0] == "/usr/bin/systemd-run" and "--scope" in argv)
                if dispatch and scenario == "launch_failed":
                    hits.append(scenario); raise OSError(errno.ENOEXEC, "fixed launch fault")
                process = real_popen(argv, **kwargs)
                if dispatch: processes.append(process)
                return process
            def wrap(argv, control, *resource_args, helper_object):
                status = os.fstat(helper_object.fileno())
                marker = "OUTPUT" if scenario == "output_limit" else "HELD-PAYLOAD"
                if resource_mode: marker += "-SCOPE"
                command = [str(payload), str(helper_object.fileno()), str(status.st_dev), str(status.st_ino),
                           str(workspace_fd), str(identity[0]), str(identity[1]), marker]
                options = dict(policy=policy, control_socket=control, helper_object=helper_object,
                               workspace_fd=workspace_fd, workspace_identity=identity)
                if resource_args:
                    return sandbox.wrap_policy_with_resource_receipt(command, resource_socket=resource_args[0],
                        unit=resource_args[1], **options)
                return sandbox.wrap_policy_with_violation_receipt(command, **options)
            def start(monitor, *, deadline_monotonic):
                if scenario == "observer_start":
                    hits.append(scenario); raise RuntimeError("fixed observer start fault")
                monitor_start(monitor, deadline_monotonic=deadline_monotonic)
                if scenario in ("keyboardinterrupt", "systemexit"):
                    hits.append(scenario); raise injected
            def record(monitor, category):
                record_original(monitor, category)
                if scenario == "observer_runtime":
                    hits.append(scenario); monitor._fail()
            def configured(scope, deadline):
                scope_configured(scope, deadline)
                if scenario == "resource_configured":
                    hits.append(scenario); raise RuntimeError("fixed CONFIGURED failure")
            def close(fd):
                if scenario == "helper_close_unknown" and any(fd == owned_fd for _, owned_fd in owners):
                    hits.append(scenario); leaked.append(fd); raise OSError(errno.EIO, "before helper close")
                if scenario == "scope_close_unknown" and fd in directory_fds:
                    hits.append(scenario); leaked.append(fd); raise OSError(errno.EIO, "before scope directory close")
                return real_close(fd)
            def close_resource(receiver):
                result = resource_close(receiver)
                if scenario == "resource_close": hits.append(scenario)
                return False if scenario == "resource_close" else result
            def close_monitor(monitor):
                result = monitor_close(monitor)
                if scenario == "observer_close": hits.append(scenario)
                return False if scenario == "observer_close" else result
            def acknowledge(monitor, deadline):
                if scenario == "missing_ack":
                    self.assertTrue(monitor._ready.is_set())
                    self.assertFalse(monitor.failed)
                    self.assertTrue(monitor._thread.is_alive())
                    hits.append(scenario); return
                acknowledge_original(monitor, deadline)
                if scenario == "bad_ack":
                    self.assertTrue(monitor._started); hits.append(scenario)
            def start_resource(receiver, *, deadline_monotonic, configured_deadline_monotonic=None):
                hits.append(scenario); raise RuntimeError("fixed resource start fault")
            stack.enter_context(mock.patch.object(broker.subprocess, "Popen", side_effect=launch))
            stack.enter_context(mock.patch("icode.linux_helper_object.open_linux_helper_object", side_effect=factory))
            stack.enter_context(mock.patch.object(notify, "create_seccomp_listener_handoff_channel", side_effect=lambda: channel(notify_channel)))
            stack.enter_context(mock.patch.object(resources, "create_task_resource_channel", side_effect=lambda: channel(resource_channel)))
            stack.enter_context(mock.patch.object(notify, "LinuxSeccompViolationMonitor", side_effect=monitor_factory))
            stack.enter_context(mock.patch.object(resources, "LinuxTaskResourceReceiver", side_effect=receiver_factory))
            stack.enter_context(mock.patch("icode.linux_task_scope.LinuxTaskScope", side_effect=scope_factory))
            stack.enter_context(mock.patch.object(original_monitor, "start", new=start))
            stack.enter_context(mock.patch.object(original_monitor, "_record", new=record))
            stack.enter_context(mock.patch.object(original_monitor, "close", new=close_monitor))
            stack.enter_context(mock.patch.object(original_receiver, "close", new=close_resource))
            stack.enter_context(mock.patch.object(original_scope, "configured", new=configured))
            stack.enter_context(mock.patch("os.close", side_effect=close))
            if scenario == "bad_ack": stack.enter_context(mock.patch.object(notify, "_HANDOFF_ACK", b"INVALID_ACK"))
            if scenario in ("bad_ack", "missing_ack"):
                stack.enter_context(mock.patch.object(original_monitor, "_acknowledge_if_healthy", new=acknowledge))
            if scenario == "resource_start":
                stack.enter_context(mock.patch.object(original_receiver, "start", new=start_resource))
            if scenario == "scope_close_unknown":
                # _close_pins pops before close, so target exact acquired identities.
                def configured_capture(scope, deadline):
                    configured(scope, deadline); directory_fds.update(scope._fds)
                stack.enter_context(mock.patch.object(original_scope, "configured", new=configured_capture))
                # Only os.close is faulted: production _close_owned_descriptor
                # must set sticky unknown itself, with no manual state or retry.
            if scenario not in ("timeout", "bad_ack", "missing_ack", "observer_start", "resource_start", "resource_configured"):
                (workspace / "release").touch()
            result, error = None, None
            try:
                try:
                    result = broker._execute_linux_helper_observed_candidate([str(payload)], cwd=workspace,
                        sandbox=sandbox, policy=policy, timeout=3 if scenario == "timeout" else 4,
                        resource_mode=resource_mode, command_wrapper=wrap)
                except BaseException as exception:
                    error = exception
                # Snapshot broker terminal evidence before any fixture self-cleanup.
                process_closed = all(process.returncode is not None and
                    (process.stdout is None or process.stdout.closed) and
                    (process.stderr is None or process.stderr.closed) for process in processes)
                channels_closed = all(endpoint.fileno() == -1 for endpoint in endpoints)
                threads_stopped = all(monitor._thread is None or not monitor._thread.is_alive() for monitor in monitors)
                threads_stopped = threads_stopped and all(receiver._thread is None or not receiver._thread.is_alive() for receiver in receivers)
                owner_states = [owner._state for owner, _ in owners]
                scope_states = [scope.cleanup_state for scope in scopes]
                owned_scopes = [scope for scope in scopes if scope._path is not None]
                scope_gc = all(not scope._path.exists() for scope in owned_scopes) if owned_scopes else None
                print(json.dumps(dict(scenario=scenario, topology="scope" if resource_mode else "no-scope",
                    architecture=linux_arch_from_machine(platform.machine()), process_closed=process_closed,
                    channels_closed=channels_closed, threads_stopped=threads_stopped,
                    owner_states=owner_states, scope_states=scope_states, scope_cleanup_ok=scope_gc,
                    error=result.error if result is not None else "raised", exception=type(error).__name__ if error is not None else None), sort_keys=True))
                self.assertEqual(len(owners), 1); self.assertTrue(process_closed)
                self.assertTrue(channels_closed); self.assertTrue(threads_stopped)
                if scenario not in ("timeout", "output_limit"):
                    self.assertIn(scenario, hits, "requested native fault site was never reached")
                self.assertEqual(len(processes), 0 if scenario == "launch_failed" else 1)
                self.assertTrue(os.fstat(workspace_fd))
                if owned_scopes: self.assertIs(scope_gc, True, "owned scope cgroup remains")
                if scenario in ("keyboardinterrupt", "systemexit"):
                    self.assertIs(error, injected); self.assertIsNone(result)
                elif scenario in ("helper_close_unknown", "scope_close_unknown"):
                    self.assertIsNone(result); self.assertEqual(type(error).__name__, "LinuxHelperObjectError")
                    self.assertTrue(leaked); self.assertEqual(len(leaked), len(set(leaked)))
                    for fd in leaked: self.assertTrue(os.fstat(fd))
                else:
                    self.assertIsNone(error); self.assertIsNotNone(result)
                    self.assertTrue(result.error is not None or result.exit_code != 0)
                    if scenario in ("timeout", "output_limit", "launch_failed"):
                        self.assertEqual(result.error, scenario)
                    if scenario == "launch_failed": self.assertIs(result.payload_started, False)
                    if scenario == "timeout": self.assertTrue((workspace / "ready").exists())
                    if scenario in ("timeout", "output_limit"): hits.append(scenario)
                    if scenario in ("bad_ack", "missing_ack", "observer_start", "resource_start", "resource_configured"):
                        self.assertFalse((workspace / "ready").exists())
                    self.assertTrue(result.cleanup_ok)
                self.assertIn(scenario, hits)
                if scenario in ("observer_close", "resource_close", "helper_close_unknown", "scope_close_unknown"):
                    self.assertTrue((workspace / "ready").exists(), "cleanup fault cannot substitute an earlier startup failure")
                    self.assertEqual(processes[0].returncode, 0)
                for owner, fd in owners:
                    if scenario != "helper_close_unknown":
                        with self.assertRaises(OSError) as caught: os.fstat(fd)
                        self.assertEqual(caught.exception.errno, errno.EBADF)
                    else: self.assertEqual(owner._state, "unknown")
                if scenario == "scope_close_unknown": self.assertIn("unknown", scope_states)
                else: self.assertTrue(all(state == "confirmed" for state in scope_states))
            finally:
                # RED/fault leftovers are cleaned with saved real methods only
                # after the terminal snapshot; these attempts confer no credit.
                for process in processes:
                    if process.returncode is None: real_stop(process)
                    for stream in (process.stdout, process.stderr):
                        if stream is not None: stream.close()
                for monitor in monitors: monitor_close(monitor)
                for receiver in receivers: resource_close(receiver)
                for endpoint in endpoints: socket.socket.close(endpoint)
                for fd in set(leaked):
                    try: real_close(fd)
                    except OSError: pass

    def test_real_candidate_faults_no_scope(self):
        for scenario in ("bad_ack", "missing_ack", "observer_start", "observer_runtime", "observer_close",
                         "timeout", "output_limit", "launch_failed", "keyboardinterrupt", "systemexit", "helper_close_unknown"):
            with self.subTest(scenario=scenario): self.run_fault(False, scenario)

    def test_real_candidate_faults_scope(self):
        for scenario in ("bad_ack", "missing_ack", "observer_start", "observer_runtime", "observer_close",
                         "resource_start", "resource_configured", "resource_close", "scope_close_unknown",
                         "timeout", "output_limit", "launch_failed", "keyboardinterrupt", "systemexit", "helper_close_unknown"):
            with self.subTest(scenario=scenario): self.run_fault(True, scenario)
```

faultrunner沿正控同一安装包；fixture的timeout在真实ready/release等待中触发（须assert ready出现），缺ACK则没有ready。所有资源终态在测试自清理之前断言；故障残留unknown允许物理FD仍活但candidate必须失败，不写全部回收。安装CI新stage传入600秒，现有nativejob15分钟预算沿用，整个软件full不重复。
- [x] root fresh SPEC/QUALITY零遗留及完整软件门后提交推送 main `1e2e4ab5d0101acf00d609af37add9893e4c57ef`（`test(linux): verify installed helper same-object dispatch`）；远端仅 main。仍交付私有候选，不能写“已完成合流”。

## Task 4：独立生产合流出口与完整门

**Dependencies:** Task 3 (四格必须全部实际PASS；软件门不能替代)
**Parallelizable:** No (需要root硬门及独立审批；本计划不授权公共入口变更)

- [ ] 当前交付保留私有候选，禁止永久无消费test-only接口：root在四格完成后开独立合流阶段，两个原公共observed入口直接设置同一个 `helper_object_mode=True`并使用Task1held adapter，不另建supervisor、不允许candidate失败回旧模式。该阶段必须先给出精准source/test diff与fresh双审；本PLAN不提前改公共入口、selector、CLI/MCP、`policy_contract_ready`。
- [ ] Task1/2各自focused与双审；主软件阶段结束运行一次完整门，Task3后因新增CI资产再跑相关脚本检查与原生四jobs。无需每个机械文档步骤触发全量CI：

```bash
.venv/bin/python -m unittest tests.test_linux_helper_dispatch tests.test_isolation tests.test_execution_broker tests.test_git_broker tests.test_linux_helper_object tests.test_linux_task_resource tests.test_linux_product_task_quota tests.test_linux_violation_receipt tests.test_linux_pidns_cleanup -q
.venv/bin/python scripts/preflight.py
git diff --check
```

使用仓库现有preflight全三道/ICODE-SKILL原合同；required checks一个也不能降门。generic/Windows明确脚本回归沿原完整门，不把Linux机器mock算Windowsnative。native C若出现必要改动，必须设计返审及完整C编译/四格复验，不能在此方案偷偷追加startup FD保存。

- [ ] 后续单独计划普通broker早返、Git remaining deadline、Reviewer角色限制、leased/模型前prepare生命周期；本片不授这些路径same-FD信用。workspace借用不得关闭、ToolContext不抢owner，同session下一命令仍可用；每dispatch独立factory，无cache。
- [ ] 最终交付报告保留七维证据与所有未验收格；同对象执行不能写成内容封印、发布者认证、依赖可信或整体R2/R3 ready。每Task的root commit建议是阶段动作，writer本轮无提交/推送。

## 自审和交接

- [ ] 对照设计1–8节：方案A/owner单一/借用传播/最终角色/清理信号/原生第二跳/四格/合流出口逐项有Task；未增permission/service/cache/selector。
- [ ] 占位扫描：`rg -n '(T[B]D|TO[D]O|implement lat[e]r|fill i[n]|function not defin[e]d)' docs/nbl/plans/2026-10-12-linux-helper-dispatch.md`，期望无匹配；所有新调用签名一致，RED有效且0ERROR。
- [ ] root fresh SPEC→不同QUALITY审查本PLAN代码资产；源实现writer需先完整回读当时文件并按精确patch适配已有变更，不覆盖用户dirty worktree。

【架构级自检报告】（计划文档，未实施源码）

- ✅ 语法/编译：30个Python代码块（含2个明确try/finally上下文patch包装）AST通过；原生fixture的C11/Wall/Wextra/Werror静态语法通过。没有运行源码/full/native测试。
- ✅ 依赖/调用链：唯一observed core→wrapper→scope→before_spawn→Popen→native，兼容默认和后续公共合流出口完整。
- ✅ 逻辑/边界：exact FD角色、对象/argv核校、scope可信第一分隔符、payload启动FD首fstat边界明确。
- ✅ 异常处理：真实socket/目录FD的before-close未知、配置失败、活动callback、原信号均有资产；新candidate原生故障独立于legacy回归。publisher失败先保存受控证据，unknown不success、不重试陌生FD。
- ✅ 关联模块：session/workspace/ToolContext/Reviewer各自owner不转移，研究与软件/原生验证分开。
- ✅ 兼容安全：普通/Git/Reviewer/leased默认保留；候选不fallback、无新增权限/服务、无ready降门。
- ✅ 可运行性：本轮仅PLAN；软件与四格未执行，不能报告100%。

---
**Execution Mode:** serial

计划保存后交root独立审查；本轮仅PLAN的显式范围覆盖writing-plans自动invoke执行建议，不由writer启动实施/reviewer。

阶段进度（root本阶段报告，2026-10-12）：完整PLAN冻结858c235222716f5899c134af4fe431d21d68fe794ba6cebbc78a8f92028ccf2a已原SPEC→不同QUALITY双审C0/I0/M0。Task1软件和publication已完成，main已提交推送31f42ae；root focused共148项（137通过、11跳过），21:21 UTC完整preflight三道全PASS，跳过项不计原生信用。Task2软件已实现并经修复后fresh SPEC→不同QUALITY均C0/I0/M0；root最终177项/29.314s/0 skip通过，2026-10-11 22:03 UTC观察完整preflight 75874 exit0、三道全PASS，compileall-j1/site/governance/landscape检查通过。Task2软件步骤已勾选，publication为下一操作。源码冻结broker 224612d605eea3784581e87682b2978982d516b8e21e4f3e32b75b9c03914d4e、scope 776ab721fec0e18e73e21fbdbdfdc75cf123c68e2b7868aa25a0dee03c5c8b69、test 751efb547dd925e1ca392502b14ac47447d14d130718f35339d7e1ebad55ac2e。设计历史摘要保留，第1–7节安全合同不变。Task3仅完成只读准备，未实施、未跑同对象native；不把已审资产或软件结果当成原生证据。

【架构级自检报告】（Task2软件候选）

- ✅ 语法/编译：compileall-j1、diff格式检查通过。
- ✅ 依赖/调用链：唯一observed core与wrapper/scope/channel收尾经独立双审及177项focused验证。
- ✅ 逻辑/边界：最终元数据/活对象拒绝、普通异常及首signal优先级、unknown不重试已测试。
- ✅ 异常处理：准备、启动、监控、资源及关闭故障矩阵软件测试通过；未声称所有原生故障已验。
- ✅ 关联模块：现有全量测试通过，ICODE-SKILL固定版本未改变。
- ✅ 兼容安全：默认旧入口保持，未新增权限、政策例外或失败fallback。
- ✅ 可运行性：完整软件preflight通过；实际安装包原生四格尚未执行，不报告整体100%。

后续 publication：Task2 六路径冻结已提交推送 main `574033a4df8311a569230bbd0522a0e1be717d8a`，root 核远端仅 main、发布后 clean。Task3 随后已开始实现五个批准路径；publisher 已取得有效 assertion RED/0 ERROR 后 GREEN，C fixture 实际单编译通过。此为实施中状态，未获源码双审、完整软件门或实际安装包原生四格信用，新 SHA CI 尚待终态。

Task3 后续源码冻结：fresh SPEC→不同 QUALITY 均 C0/I0/M0。root 直接核原始工具记录中三个 publisher 的有效 assertion RED/0 ERROR 与后续 GREEN；源码冻结 C 78c4155ee2b3aa8b4bce4f50e1b5d5298a0d9dcae391a439ec0d30b64348af1f、probe ea820d044d485d469b06a92d2cee2dbc394fa211a12212f709ea3e2707ed3633、wheel runner 7b2034e2774baa076952f93f56681fb723d7b28724a728ee354ef2db2879cc94、CI 4a54af74b0e9f956fdde009d07dd77e14c656ef4a01f5a5a92a9bc4599c6095d、tests 053db749d1f361bdcdd9e19b8ab66b56eeae9626e8c0b6aa8ed62b59fe09b729。

SPEC 独立最终 installed 脚本 6 tests / 38.488s / 0 skip、0 inconclusive；本机 x86_64/Ubuntu22/kernel6.8/systemd249 的两拓扑各四 mutation×两 dispatch，16 正控、26 故障、24 实际 identity pass。QUALITY 独立36 focused/0 skip、2实际identity/socket负控及额外恶意发布/unknown分支通过。root最终180 focused/29.188s/0 skip、真实C11/O2/Wall/Wextra/Werror单编译与compileall-j1/site/governance/landscape检查通过；完整preflight 28455正在运行，未预记终态。channel数字复用观察修正保存关闭前身份、真实socket.close正常返回与即时EBADF，再核终态失能；detach本身不授信用。四新CI格与Task3发布仍未完成，Task4仅只读调用链/设计准备，不实施合流。

后续完整门纠错：28455 实际 exit1，3032 tests / 533.192s / 2 failures / 74 skipped，阻止发布；旧 lease 主流程夹具仅模拟虚假 wheel 路径，新 wheel 哈希读取令成功测试提前拒绝。root 最小同步 `tests/test_installed_lease_ci_notice.py` 两处读取夹具，并增加失败路径必须到达 lease 阶段的断言：先实际 1 test / 1 assertion FAIL / 0 ERROR，再修复后 41 tests / 0.172s / 0 skip 通过；独立复审 C0/I0/M0，生产读取、77/SKIP 和无符合性信用保持。新增文件冻结 e4888c1c4b49912a40fd790b9dc93461efbb6a3474d8d45a7d0df2e07f5ec558。中间全量 48741 在冻结变更后主动中断 exit130，不计通过；最终冻结全量 32828 已启动、尚待终态。

Task4 提前 DESIGN 已保存为 [公共消费设计](../specs/2026-10-12-linux-helper-public-consumption-design.md)，187 行冻结 c504bd9033247e5d8556917079f4cd5b3f434b0fec07ff090605f8f02128b96b，fresh SPEC→不同 QUALITY 均 C0/I0/M0，root 完整阅读并核 session.policy 实际接口。只授设计信用；Task3 同 SHA 四新原生格实际通过前不实施公共合流。

最终软件门：root 于 2026-10-11 22:40:50 UTC 实际观察最终冻结 preflight 32828 exit0，密钥/子模块/全量测试三道通过。六源冻结未漂移；关联 lease fixture 修复已独立复审，格式、语法、站点、治理与五文档一致性检查通过。Task3 软件候选可提交供新四格实际验证；并行 Windows 角色 DESIGN 已独立双审零遗留，仅授静态设计信用，精确计划准备另行进行。

【架构级自检报告】（Task3 软件候选）

- ✅ 语法/编译：Python compileall-j1、实际 C11/O2/Wall/Wextra/Werror 编译、格式检查通过。
- ✅ 依赖/调用链：安装包私有 core 探针、CI runner/受控发布及旧 lease 夹具同步，独立审查零遗留。
- ✅ 逻辑/边界：本机正控、真实身份与故障终态验证通过，数字 FD 复用与 detach 信用区分清楚。
- ✅ 异常处理：受控失败/超时/启动异常与未知关闭拒绝经测试；未声称所有平台实测通过。
- ✅ 关联模块：完整 preflight 三道通过；固定 ICODE-SKILL 不变，五份设计/计划/研究文档一致性通过。
- ✅ 兼容安全：生产入口和 ready/selector 未变，旧 lease SKIP 无符合性信用，未新增权限或降级路径。
- ✅ 可运行性：完整软件门通过，本机已安装探针通过；新 SHA 四 CI、公共合流与整体 R2/R3 尚未通过，不报告整体 100%。

Task3 后续实际矩阵验收：main `1e2e4ab5d0101acf00d609af37add9893e4c57ef` 已推送，四新 Linux job 均终态 success。root 与独立观察者各直接取实际原日志：每格 42 条受控记录＝16 唯一 topology/mutation/dispatch 正控＋26 故障，24 identity pass，0 发布拒绝、0 正控 unknown/inconclusive/skip；正控 owner closed、scope confirmed、cleanup true，每条 process/channels/threads/workspace 正常。三项预设未知关闭故障各正确抛 LinuxHelperObjectError，不把 live FD 记为回收成功。完整平台/包摘要与 job 见 [持续对照最新四格台账](../../agent-landscape-live.md)。Task4 前置原生门已满足，root 自动启动其精确公共消费 PLAN；公开入口、ready/selector 尚未修改，Windows Reviewer unknown 与整体 R2/R3 缺口仍保留。
