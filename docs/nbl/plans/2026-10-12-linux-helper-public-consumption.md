# Linux helper 同对象公共消费 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development (recommended) or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 两个公共 DENY observed 入口接通已有同对象 core，并让真实 ToolContext 借用本次 helper、保留原政策及 WorkspaceSession 绑定。

**Architecture:** broker 每 dispatch 独立取得并最终关闭 helper owner，callback 与 ToolContext 仅借用；复用已有 held wrapper、scope 第二跳、最终核验及完整收尾。直接 receipt 方法的 None 默认保持旧调用形状，公共 observed 不允许降级。

**Tech Stack:** Python 3.11+、typing.Protocol、unittest、已有 Landlock/seccomp/systemd scope 与 Linux installed-wheel CI；不引入依赖、权限或服务。

---

## 冻结证据与本轮边界

本轮只新增此 PLAN；不实施、不编译、不运行测试、不执行 Git 写操作、不读取 KEY。writing-plans 的自动执行、worktree 和逐步 commit 建议由本轮文档范围覆盖；交 root fresh SPEC→不同 QUALITY，C0/I0/M0 后再实施。本片有明确单一缺口、已有实现及唯一调用链，三问已确认。

设计基准：[DESIGN](../specs/2026-10-12-linux-helper-public-consumption-design.md)，187 行，SHA256 `c504bd9033247e5d8556917079f4cd5b3f434b0fec07ff090605f8f02128b96b`，root 已 fresh SPEC→不同 QUALITY 零遗留。设计起草时的“Task3 尚未四格通过”是历史状态，以下 root 新证据更新前置门，不改写设计历史。

root 已实际核对 Task3 候选 `1e2e4ab5d0101acf00d609af37add9893e4c57ef`，run `38181446068` 四新 Linux job 全部 PASS：

| runner | actual job |
| --- | --- |
| ubuntu-22.04 x64 | 114594685144 |
| ubuntu-22.04-arm | 114594685085 |
| ubuntu-24.04-arm | 114594685052 |
| ubuntu-latest x64 | 114594685151 |

各原日志 42 records：16 正控、26 故障、24 identity PASS、0 坏终态；其中 3 个 unknown 场景按预设正确拒绝，不能记为全部资源已回收。其余 CI 全量仍运行；上述证据只解除 Task4 公共合流前置门，不授整体 R2/R3 PASS。main 本轮基线 `1e2e4ab`，vendor/icode-skill `21566a5`；实施与发布均重新冻结完整 SHA/工作区及资产 hash，不复用旧候选审查。

生产允许改动仅 `src/icode/execution_broker.py`、`src/icode/tools/base.py`。CI 改动仅 `scripts/run_native_wheel_ci.py`、`scripts/probe_installed_linux_helper_object.py`；测试复用下表。`tools/builtin.py` 只读核调用链。不得顺带改变 isolation、scope、factory、native、selector、ready、普通/Git/Reviewer/leased 或模型前 prepare。若发现这些范围必须改，返回设计审查。

| 资产 | 责任 |
| --- | --- |
| execution_broker.py | 两公共 mode=True；两个私有 keyword Protocol |
| tools/base.py | 两 receipt keyword-only 借用；None 精确不传 keyword |
| test_linux_helper_dispatch.py | 公共行为 RED、owner/异常/无降级、private legacy 分账、publisher |
| test_linux_workspace_fd.py | 真实 ctx 双 receipt、None 兼容、原校验、collision 目标命中 |
| test_linux_product_task_quota.py | 有效 ELF/manifest、confirmed scope、第二 channel 信号目标命中 |
| test_linux_contract_engineering.py | 保留原 source helper→真实 tools bridge 验证，不必修改源码 |
| installed probe / wheel runner | 保留私有矩阵，追加公共入口＋真实 ctx/session 的正控与故障证据 |

以下 Python 代码块是完整新增函数/类或完整替换函数；标明插入类的方法需缩进四空格。现有函数内局部修改按给定精确替换片段成对执行，不能删掉片段外逻辑。代码资产不得整块覆盖原文件。

## Task 1：公共入口与原 owner 生命周期

**状态**

- [x] 任务完成（软件实现与自审；整片独立源码双审及安装包公共消费待验）

**Dependencies:** None
**Parallelizable:** No（先证明公共缺口；不能与同文件修改并行）

- [ ] 在 `TestDispatchOwner.exercise` 最后增加 `public=False, legacy=False`；将其 entry 选择完整替换如下，其余 fixture 不变。此测试夹具变化先于生产代码。

```python
if legacy:
    entry = broker._execute_linux_observed_command
elif public:
    entry = (broker.execute_linux_resource_observed_command if resource_mode
             else broker.execute_linux_violation_observed_command)
else:
    entry = broker._execute_linux_helper_observed_candidate
arguments = dict(cwd=root, sandbox=LandlockSandbox(str(binary), manifest=str(manifest)),
                 policy=policy_for(root), timeout=timeout, command_wrapper=wrapper,
                 output_limit_bytes=output_limit_bytes)
if legacy or not public:
    arguments["resource_mode"] = resource_mode
result, error = capture(lambda: entry(["/usr/bin/true"], **arguments))
```

原 `test_ordinary_observed_rejects_unexpected_binding_without_factory` 调用由 `candidate=False` 改为 `legacy=True`，更名 `test_private_legacy_observed_rejects_unexpected_binding_without_factory`；旧 `candidate` 参数删除，避免多套布尔语义。

- [ ] 在该类新增以下方法。已有有效 `pair()` 是真实宿主 regular ELF＋匹配 manifest，已有 monitor/scope/resource doubles 仅作软件合同证据。

```python
def test_public_entries_own_and_launch_same_object(self):
    for resource_mode in (False, True):
        with self.subTest(resource_mode=resource_mode), temp_workspace() as raw:
            result, error, owners, closes, launches, channels = self.exercise(
                raw.resolve(), public=True, resource_mode=resource_mode)
            self.assertIsNone(error)
            self.assertEqual(len(owners), 1, "public dispatch never acquired its owner")
            owner, fd = owners[0]
            self.assertIsNone(result.error)
            self.assertEqual(closes, [fd])
            self.assertEqual(len(launches), 1)
            self.assertIn(f"/proc/self/fd/{fd}", launches[0][0])
            self.assertIn(fd, launches[0][1])
            self.assertEqual(owner._state, "closed")
            self.assert_closed(fd)
            self.assertTrue(all(channel.fileno() == -1 for channel in channels))

def test_public_first_signal_survives_owner_cleanup_fault(self):
    for resource_mode in (False, True):
        for first in (KeyboardInterrupt(), SystemExit(71)):
            with self.subTest(resource_mode=resource_mode, first=type(first).__name__), temp_workspace() as raw:
                result, error, owners, closes, launches, channels = self.exercise(
                    raw.resolve(), public=True, resource_mode=resource_mode,
                    fault=first, close_fault=LinuxHelperObjectError())
                self.assertEqual(len(owners), 1)
                self.assertIsNone(result)
                self.assertIs(error, first)
                self.assertEqual(closes, [owners[0][1]])
                self.assertEqual(len(launches), 1, "signal site was not reached")
                self.assert_closed(owners[0][1])
                self.assertTrue(all(channel.fileno() == -1 for channel in channels))
```

- [ ] Run `.venv/bin/python -m unittest tests.test_linux_helper_dispatch.TestDispatchOwner.test_public_entries_own_and_launch_same_object -v`。必须是 1 方法 assertion FAIL、0 ERROR；预期 owner 数为 0。缺 API、TypeError、manifest 前门拒绝不算本目标 RED。保留实际输出和候选 hash。

- [ ] broker 添加 `from typing import TYPE_CHECKING, Protocol`，TYPE_CHECKING 块及两个私有 Protocol 放于两个公共入口之前。

```python
if TYPE_CHECKING:
    from .linux_helper_object import LinuxHelperObject

class _LinuxViolationCommandWrapper(Protocol):
    def __call__(self, argv: list[str], control_socket: socket.socket,
                 *, helper_object: LinuxHelperObject) -> list[str]: ...

class _LinuxResourceCommandWrapper(Protocol):
    def __call__(self, argv: list[str], control_socket: socket.socket,
                 resource_socket: socket.socket, unit: str,
                 *, helper_object: LinuxHelperObject) -> list[str]: ...
```

两 public 的 `command_wrapper` 标注分别替换为上述 Protocol；两 public 调 core 分别在 `resource_mode=False/True` 同行或后行增加 `helper_object_mode=True`。resource 原 `verification_cache_root` 完整保留。私有 candidate、core 默认 `helper_object_mode=False` 及所有清理代码不改。

- [ ] 同一 RED 命令转 GREEN；在该类新增下列公共故障/绑定回归，原私有方法不删。软件 injected scope/monitor 与实际 installed fault-hit 相互补充，软件结果不代签 native。

```python
def test_public_faults_and_binding_rejection_keep_owner_cleanup(self):
    for resource_mode in (False, True):
        for stage in ("wrapper_fault", "monitor_fault", "fault"):
            for injected in (RuntimeError("fixed fault"), KeyboardInterrupt(), SystemExit(19)):
                with self.subTest(resource_mode=resource_mode, stage=stage,
                                  fault=type(injected).__name__), temp_workspace() as raw:
                    result, error, owners, closes, launches, channels = self.exercise(
                        raw.resolve(), public=True, resource_mode=resource_mode, **{stage: injected})
                    self.assertEqual(len(owners), 1)
                    self.assertEqual(closes, [owners[0][1]])
                    self.assert_closed(owners[0][1])
                    self.assertEqual(len(launches), 1 if stage == "fault" else 0)
                    self.assertTrue(all(channel.fileno() == -1 for channel in channels))
                    if not isinstance(injected, Exception) or stage == "fault":
                        self.assertIs(error, injected)
                    else:
                        self.assertIsNone(error)
                        self.assertEqual(result.error, "isolation_unavailable")
        for change in (lambda command, owner: setattr(command, "helper_object", None),
                       lambda command, owner: setattr(command, "helper_object", object()),
                       lambda command, owner: setattr(command, "pass_fds", command.pass_fds * 2)):
            with self.subTest(resource_mode=resource_mode, change=change), temp_workspace() as raw:
                result, error, owners, closes, launches, channels = self.exercise(
                    raw.resolve(), public=True, resource_mode=resource_mode, mutate=change)
                self.assertIsNone(error)
                self.assertEqual(len(owners), 1)
                self.assertEqual(result.error, "isolation_unavailable")
                self.assertEqual(launches, [])
                self.assertEqual(closes, [owners[0][1]])
                self.assert_closed(owners[0][1])
                self.assertTrue(all(channel.fileno() == -1 for channel in channels))
```

Run `.venv/bin/python -m unittest tests.test_linux_helper_dispatch -v`，不得以某个 fault 因新前门拒绝提前返回当 GREEN。

- [ ] 未知旧 callback 单独新增下列完整方法，确认新 keyword 在 callback 调用处失败、callback body 从未执行、Popen 未执行，工厂实际开过对象。禁止 TypeError fallback。

```python
def test_public_old_callback_never_retries_legacy_body(self):
    for resource_mode in (False, True):
        with self.subTest(resource_mode=resource_mode), temp_workspace() as raw:
            root = raw.resolve()
            binary, manifest = pair(root)
            body = []
            def old(argv, control, *resource_args):
                body.append(True)
                return argv
            with mock.patch("icode.linux_helper_object.open_linux_helper_object",
                            wraps=open_linux_helper_object) as factory, \
                 mock.patch.object(broker.subprocess, "Popen") as launch, \
                 mock.patch("icode.linux_task_scope.LinuxTaskScope", return_value=Scope()), \
                 mock.patch("icode.linux_task_resource.LinuxTaskResourceReceiver", return_value=Resource()):
                entry = (broker.execute_linux_resource_observed_command if resource_mode
                         else broker.execute_linux_violation_observed_command)
                result = entry(["/usr/bin/true"], cwd=root,
                    sandbox=LandlockSandbox(str(binary), manifest=str(manifest)),
                    policy=policy_for(root), timeout=1, command_wrapper=old)
            factory.assert_called_once()
            launch.assert_not_called()
            self.assertEqual(body, [])
            self.assertEqual(result.error, "isolation_unavailable")
            self.assertIs(result.payload_started, False)
```

## Task 2：真实 ToolContext 借用与直接旧调用兼容

**状态**

- [x] 任务完成（软件透传与兼容回归；整片独立源码双审及安装包消费待验）

**Dependencies:** Task 1
**Parallelizable:** No（public→ctx 合同必须成对）

- [ ] 先建立机械接口脚手架：base typing import 加 `TYPE_CHECKING`，在 TYPE_CHECKING 块类型导入 `from ..linux_helper_object import LinuxHelperObject`。两现有方法签名各添加 `*, helper_object: LinuxHelperObject | None = None`，完整保留旧方法体、不转发此参数。这一步只消除签名障碍，不授 helper 借用/透传目标完成；尚不能把公共工具消费记为 GREEN。两签名准确形状如下，方法体此时仍是原代码：

```text
def wrap_command_with_violation_receipt(
    self, argv: list[str], control_socket: object,
    *, helper_object: LinuxHelperObject | None = None,
) -> list[str]:

def wrap_command_with_resource_receipt(
    self, argv: list[str], control_socket: object, resource_socket: object, unit: str,
    *, helper_object: LinuxHelperObject | None = None,
) -> list[str]:
```

- [ ] `tests/test_linux_workspace_fd.py` 新增 `import socket`、`from unittest import mock`、`from icode.linux_helper_object import open_linux_helper_object`。在 `TestLinuxWorkspaceFd` 内加入完整方法：

```python
def test_context_borrows_helper_in_both_receipts_without_owning_it(self):
    session = self.session()
    ctx = ToolContext(session.workspace_root, sandbox=self.sandbox,
                      policy=session.policy("code"), workspace_session=session)
    original_fd, original_identity = session.workspace_fd, session.workspace_fd_identity
    with open_linux_helper_object(self.helper, self.manifest) as owner:
        for resource_mode in (False, True):
            with self.subTest(resource_mode=resource_mode):
                control, peer = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
                resource, resource_peer = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
                try:
                    name = ("wrap_policy_with_resource_receipt" if resource_mode
                            else "wrap_policy_with_violation_receipt")
                    original = getattr(self.sandbox, name)
                    with mock.patch.object(self.sandbox, name, wraps=original) as called:
                        result, failure = None, None
                        try:
                            if resource_mode:
                                result = ctx.wrap_command_with_resource_receipt(
                                    ["/usr/bin/true"], control, resource,
                                    "icode-task-0123456789abcdef0123456789abcdef.scope",
                                    helper_object=owner)
                            else:
                                result = ctx.wrap_command_with_violation_receipt(
                                    ["/usr/bin/true"], control, helper_object=owner)
                        except Exception as error:
                            failure = error
                    self.assertIsNone(failure, "context must accept the broker's borrowed owner")
                    called.assert_called_once()
                    self.assertIs(called.call_args.kwargs.get("helper_object"), owner,
                                  "context must forward the same borrowed owner")
                    self.assertIs(called.call_args.kwargs["policy"], ctx.policy)
                    self.assertEqual(called.call_args.kwargs["workspace_fd"], original_fd)
                    self.assertEqual(called.call_args.kwargs["workspace_identity"], original_identity)
                    self.assertIs(result.helper_object, owner)
                    self.assertIn(owner.fileno(), result.pass_fds)
                    self.assertIn(original_fd, result.pass_fds)
                    ctx.close()
                    self.assertTrue(os.fstat(owner.fileno()))
                    self.assertEqual(session.workspace_fd_identity, original_identity)
                    self.assertTrue(os.fstat(original_fd))
                finally:
                    for endpoint in (control, peer, resource, resource_peer): endpoint.close()

def test_none_helper_keeps_exact_old_sandbox_keyword_shape(self):
    session = self.session()
    ctx = ToolContext(session.workspace_root, sandbox=self.sandbox,
                      policy=session.policy("code"), workspace_session=session)
    seen = []
    def violation(argv, *, policy, control_socket, workspace_fd, workspace_identity):
        seen.append((policy, control_socket, workspace_fd, workspace_identity))
        return list(argv)
    def resource(argv, *, policy, control_socket, resource_socket, unit,
                 workspace_fd, workspace_identity):
        seen.append((policy, control_socket, workspace_fd, workspace_identity))
        return list(argv)
    with mock.patch.object(self.sandbox, "wrap_policy_with_violation_receipt", new=violation), \
         mock.patch.object(self.sandbox, "wrap_policy_with_resource_receipt", new=resource):
        control, resource_control = object(), object()
        self.assertEqual(ctx.wrap_command_with_violation_receipt(["true"], control), ["true"])
        self.assertEqual(ctx.wrap_command_with_resource_receipt(
            ["true"], control, resource_control, "fixture.scope"), ["true"])
    self.assertEqual(len(seen), 2)
    for policy, control_seen, fd, identity in seen:
        self.assertIs(policy, ctx.policy)
        self.assertIs(control_seen, control)
        self.assertEqual((fd, identity), (session.workspace_fd, session.workspace_fd_identity))
```

- [ ] Run `.venv/bin/python -m unittest tests.test_linux_workspace_fd.TestLinuxWorkspaceFd.test_context_borrows_helper_in_both_receipts_without_owning_it -v`，预期 callback 实际成功调用一次、无签名异常，`.kwargs.get("helper_object")` 为 None 的同引用透传 assertion FAIL、0 ERROR。签名 ERROR、捕获 TypeError 后的失败断言或缺 manifest 前门拒绝均不是目标 RED。None 测试先 GREEN，实施后仍 GREEN；不能引入宽松 `**kwargs` 假冒旧 sandbox 兼容。

- [ ] base typing import 加 `TYPE_CHECKING`，类型导入同 Task1 路径改为 `from ..linux_helper_object import LinuxHelperObject`；完整替换两方法如下，不增加成员、不取得/缓存/关闭 owner。

```python
def wrap_command_with_violation_receipt(
    self, argv: list[str], control_socket: object,
    *, helper_object: LinuxHelperObject | None = None,
) -> list[str]:
    """Borrow this dispatch's helper without bypassing context binding."""
    self._policy_command_wrapper()
    wrap_receipt = getattr(self.sandbox, "wrap_policy_with_violation_receipt", None)
    if not callable(wrap_receipt):
        raise IsolationUnavailable("原生违规回执通道不可用，命令已拒绝")
    try:
        options = self._workspace_command_options()
        # Direct legacy calls retain their exact keyword shape.
        if helper_object is not None:
            options["helper_object"] = helper_object
        prepared = wrap_receipt(argv, policy=self.policy, control_socket=control_socket,
                                **options)
        return prepared if isinstance(prepared, PreparedCommand) else list(prepared)
    except Exception:
        raise IsolationUnavailable("工单隔离策略绑定失败，命令已拒绝") from None

def wrap_command_with_resource_receipt(
    self, argv: list[str], control_socket: object, resource_socket: object, unit: str,
    *, helper_object: LinuxHelperObject | None = None,
) -> list[str]:
    """Borrow the helper and keep the complete policy/session dual handoff."""
    self._policy_command_wrapper()
    wrap_receipt = getattr(self.sandbox, "wrap_policy_with_resource_receipt", None)
    if not callable(wrap_receipt):
        raise IsolationUnavailable("原生资源回执通道不可用，命令已拒绝")
    try:
        options = self._workspace_command_options()
        if helper_object is not None:
            options["helper_object"] = helper_object
        prepared = wrap_receipt(argv, policy=self.policy, control_socket=control_socket,
                                resource_socket=resource_socket, unit=unit, **options)
        return prepared if isinstance(prepared, PreparedCommand) else list(prepared)
    except Exception:
        raise IsolationUnavailable("工单隔离策略绑定失败，命令已拒绝") from None
```

- [ ] 两测试 GREEN；新增下列原政策检查负控，不把 helper keyword 当授权。关闭/FD复用原测试继续运行，不改原 frozen identity。

```python
def test_borrowed_helper_never_bypasses_context_policy_or_session(self):
    session = self.session()
    policy = session.policy("code")
    with open_linux_helper_object(self.helper, self.manifest) as owner:
        for bad_policy, read_only in ((replace(policy, ticket_id="other"), False),
                                      (replace(policy, run_id="other"), False),
                                      (replace(policy, workspace_root=self.workspace), False),
                                      (policy, True)):
            ctx = ToolContext(session.workspace_root, sandbox=self.sandbox,
                              policy=bad_policy, read_only_workspace=read_only,
                              workspace_session=session)
            for method, args in ((ctx.wrap_command_with_violation_receipt, (["true"], object())),
                                 (ctx.wrap_command_with_resource_receipt,
                                  (["true"], object(), object(), "fixture.scope"))):
                with self.subTest(policy=bad_policy, read_only=read_only, method=method.__name__), \
                     mock.patch.object(self.sandbox, "wrap_policy_with_violation_receipt") as v, \
                     mock.patch.object(self.sandbox, "wrap_policy_with_resource_receipt") as r:
                    with self.assertRaises(IsolationUnavailable): method(*args, helper_object=owner)
                    v.assert_not_called()
                    r.assert_not_called()
                    self.assertTrue(os.fstat(owner.fileno()))
```

## Task 3：同步现有 callback 与防止 fixture 假绿

**状态**

- [x] 任务完成（软件回归；安装包公共消费另见 Task 4）

**Dependencies:** Task 2
**Parallelizable:** No（基于公共 mode 的实际回归）

- [ ] wheel runner 内 quota closure 完整替换为：

```python
def wrap(argv, control_socket, resource_socket, unit, *, helper_object):
    return sandbox.wrap_policy_with_resource_receipt(
        argv, policy=policy, control_socket=control_socket,
        resource_socket=resource_socket, unit=unit, helper_object=helper_object,
    )
```

- [ ] workspace 的 `test_broker_rejects_channel_collision_before_payload` 将 callback 替换为下列完整片段，callback 后、原 result 断言前增加 `self.assertEqual(hits, [True])`。用原有效 helper/manifest，不再因 TypeError 在 collision 前拒绝。

```python
hits = []
def collision(argv, channel, *, helper_object):
    hits.append(True)
    command = self.sandbox.wrap_policy_with_violation_receipt(
        argv, policy=session.policy("code"), control_socket=channel,
        helper_object=helper_object, workspace_fd=session.workspace_fd,
        workspace_identity=session.workspace_fd_identity)
    command.pass_fds += (channel.fileno(),)
    return command
```

- [ ] quota 的 `test_broker_setup_cleanup_interrupt_closes_all_owned_resources` 在每个 temp_workspace 内、创建 channel 前新增：

```python
helper = root / "helper"
shutil.copyfile(Path("/usr/bin/true").resolve(strict=True), helper)
helper.chmod(0o700)
manifest = root / "helper.sha256"
manifest.write_text(hashlib.sha256(helper.read_bytes()).hexdigest() + "\n", encoding="ascii")
hits = []
def second_channel_failure():
    hits.append(True)
    raise RuntimeError("injected second channel failure")
```

该 `OwnedScope` 类增加 `cleanup_state = "confirmed"`。原 mock/`assertRaises`/结果断言部分完整替换为以下块；所有原 channel 构造、InterruptedSender（关闭后抛循环中的原 `error` 对象）、scope pin、baseline 与 finally 保留。先捕获首异常，再核 target hit，再核原信号对象与完整清理，不能让 `assertRaises` 的早期失败掩盖目标未命中：

```python
with mock.patch("icode.linux_task_scope.LinuxTaskScope", return_value=OwnedScope()), \
     mock.patch("icode.linux_task_resource.create_task_resource_channel", return_value=(host, sender)), \
     mock.patch("icode.linux_seccomp_notify.create_seccomp_listener_handoff_channel",
                side_effect=second_channel_failure):
    caught = None
    try:
        execution_broker.execute_linux_resource_observed_command(
            [sys.executable], cwd=root, policy=policy, timeout=2,
            sandbox=LandlockSandbox(helper=str(helper), manifest=str(manifest)),
            command_wrapper=lambda argv, *args, helper_object: argv)
    except BaseException as failure:
        caught = failure
self.assertEqual(hits, [True], "second channel fault was not reached")
self.assertIs(caught, error, "cleanup must preserve the original first signal")
self.assertEqual(host.fileno(), -1, "broker interruption skipped resource host endpoint")
self.assertEqual(scope_closed, [True], "broker interruption skipped owned scope pin")
with self.assertRaises(OSError): os.fstat(pin)
```

- [ ] fixture 分两步验证：workspace 先添加 `hits=[]` 与最终 `hits == [True]` 断言，保留旧callback；quota 先添加 `hits=[]`/`second_channel_failure`，用上述捕获及先验 hits 的块，但暂保留旧 `sandbox=LandlockSandbox(helper="/not-executed-owned-fixture")` 与旧callback、不创建有效 helper/manifest。运行两个精确方法，必须先在 target-hit assertion FAIL、0 ERROR；随后完成有效对象及callback注入同步后 GREEN。这个 RED 证明旧fixture被新前门短路，Task1/2已单独证明生产行为缺口。不要将签名 ERROR 或缺manifest当行为RED。然后运行：

```bash
.venv/bin/python -m unittest tests.test_linux_helper_dispatch tests.test_linux_workspace_fd tests.test_linux_product_task_quota tests.test_linux_contract_engineering -v
```

预期实际测试全绿，记录 skips 的真实环境原因；source helper、FakeBackend/model double、`native_ready=False` 的 engineering bridge 只授 sourcehost/软件 tools 消费信用，不授 installed/model/native ready。真实工具 `_controlled_dispatch` 调用既有公共 resource＋ctx 方法，无需修改 builtin 接线。

后续实际回归发现并纳入本Task的两项同文件测试契约同步（不扩大生产源码范围）：`test_no_bus_wrong_tool_and_out_of_range_cap_fail_before_launch` 的三个拒绝场景须证明目标scope设置实际命中，再按既有helper-object core固定前门 `isolation_unavailable` 验拒绝，原payload_started=false/Popen未调用/marker未创建保持。`test_active_callback_keeps_owned_pins_until_worker_returns` 在scope回调尚活动、关闭未确认时，已有helper-object core抛固定异常；ToolRegistry的tool_exception不能被补成payload_started=None。明确核固定错误及scope关闭状态，保留真实回调线程/FD仍活、release后receiver与pins最终关闭，不能修改生产unknown拒绝或伪造结果字段。首轮四模块实际130tests/56.951s/0skip/3FAIL+1ERROR阻止该Task完成；修订与复验尚待执行。

后续实施记录：仅同步上述两项既有测试合同，没有修改生产拒绝或清理逻辑。实现者复验四模块实际 130 tests / 56.600s / 0 skip / OK，内建 SPEC→QUALITY 均零遗留；root 独立阅读最终三方法差异并运行 collision、setup_cleanup_interrupt、no_bus、active_callback 四个精确方法，实际 4 tests / 3.566s / 0 skip / OK。Task3 冻结 runner `0fe1476864be440c3faa83e67623051a0ddc393eb524227eed605be90852c13a`、workspace tests `aaed190e79e0900adf460af72cf5fd37f7b7253c84a540cd8390daa8292537b2`、quota tests `540be8e59c7b31d8b306cdd08a7d84b7d79f217ad80c11c2d1f656a625b01f4b`；后续 Task4 可变更 runner 的 publisher，不复用这些 hash 作为最终候选。原首轮失败保留，不授 installed/model/native-ready 信用。

## Task 4：安装包公共＋真实 context 的同对象矩阵

**状态**

- [x] 任务完成（本机实际安装包；四 runner 最终 SHA 验收另见 Task 5）

**Dependencies:** Task 3
**Parallelizable:** No（须验收完整公共链与有效 wheel）

- [ ] installed probe import 增加 `from icode.tools.base import ToolContext`、`from icode.workspace import WorkspaceManager`。新增完整 helper；source/data 相邻且不重叠，真实 session.policy，无手工删除 protected_paths。Git 写仅发生于测试新建临时 source，不触及工作仓库。

```python
def probe_workspace(root, stack, consumer):
    if consumer == "candidate":
        workspace = root / "workspace"
        workspace.mkdir()
        fd = os.open(workspace, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        stack.callback(os.close, fd)
        return workspace, fd, descriptor_identity(fd), None
    if consumer != "context":
        raise ValueError("invalid probe consumer")
    source = root / "source"
    source.mkdir()
    (source / "source.txt").write_text("probe\n", encoding="ascii")
    for args in (("init", "-q"), ("add", "source.txt"),
                 ("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                  "commit", "-qm", "base")):
        subprocess.run(["git", "-C", str(source), *args], check=True,
                       capture_output=True, timeout=15)
    session = stack.enter_context(WorkspaceManager(
        source, root / "data", "installed-public", isolate_git_metadata=True
    ).open("public-ticket", "public-run"))
    fd = session.workspace_fd
    identity = session.workspace_fd_identity
    if type(fd) is not int or identity is None or descriptor_identity(fd) != identity:
        raise RuntimeError("invalid session workspace")
    return session.workspace_root, fd, identity, session

def observed_entry(resource_mode, consumer):
    if consumer == "candidate":
        return broker._execute_linux_helper_observed_candidate, {"resource_mode": resource_mode}
    if consumer != "context":
        raise ValueError("invalid probe consumer")
    return (broker.execute_linux_resource_observed_command if resource_mode
            else broker.execute_linux_violation_observed_command), {}
```

- [ ] `TestInstalledHelperDispatch.probe` 签名新增 `consumer="candidate"`。原 temp block 从 `root = raw.resolve()` 到 `workspace_identity` 赋值整个准备片段替换为：

```python
root = raw.resolve()
workspace, workspace_fd, workspace_identity, session = probe_workspace(root, stack, consumer)
```

原 native_policy 赋值替换为：

```python
native_policy = (session.policy("code", process_limit=1, wall_timeout_seconds=8,
                                output_limit_bytes=2048) if session is not None
                 else replace(policy_for(workspace), process_limit=1))
ctx = (ToolContext(workspace, sandbox=sandbox, policy=native_policy,
                   workspace_session=session) if session is not None else None)
context_calls = []
```

原 wrap 定义完整替换如下；adapter 只生成观测 payload 参数并调用真实 ctx，不能在 context 模式直接调用 sandbox。

```python
def wrap(argv, control, *resource_args, helper_object):
    status = os.fstat(helper_object.fileno())
    command = [str(payload), str(helper_object.fileno()), str(status.st_dev), str(status.st_ino),
               str(workspace_fd), str(workspace_identity[0]), str(workspace_identity[1]),
               "HELD-PAYLOAD-SCOPE" if resource_mode else "HELD-PAYLOAD"]
    if ctx is not None:
        context_calls.append(helper_object)
        if resource_args:
            prepared = ctx.wrap_command_with_resource_receipt(command, control,
                resource_args[0], resource_args[1], helper_object=helper_object)
        else:
            prepared = ctx.wrap_command_with_violation_receipt(command, control,
                                                               helper_object=helper_object)
        self.assertIs(prepared.helper_object, helper_object)
        self.assertIn(workspace_fd, prepared.pass_fds)
        return prepared
    if resource_args:
        return sandbox.wrap_policy_with_resource_receipt(command, policy=native_policy,
            control_socket=control, resource_socket=resource_args[0], unit=resource_args[1],
            helper_object=helper_object, workspace_fd=workspace_fd, workspace_identity=workspace_identity)
    return sandbox.wrap_policy_with_violation_receipt(command, policy=native_policy,
        control_socket=control, helper_object=helper_object,
        workspace_fd=workspace_fd, workspace_identity=workspace_identity)
```

两 dispatch 循环的每轮清空观察集合处加 `context_calls.clear()`；future 提交完整替换为：

```python
entry, entry_options = observed_entry(resource_mode, consumer)
future = pool.submit(entry, [str(payload)], cwd=workspace, sandbox=sandbox,
    policy=native_policy, timeout=6, command_wrapper=wrap, **entry_options)
```

每轮 record 创建后、打印前增加以下字段；实际 assert owner 个数之后补 ctx 断言。保留原 proc PID pin/starttime/前后存活/时限/exe fstat、authenticated CONFIGURED-before-ACK、ready-before-release、decoy、初始FD扫描、payload无workspace capability、DENY/quota/GC及所有终态断言。

```python
record.update(consumer=consumer, public_entry=("resource" if resource_mode else "violation")
              if ctx is not None else None, context_borrowed=ctx is not None)
if ctx is not None:
    self.assertEqual(context_calls, owners)
    self.assertIs(ctx.workspace_session, session)
    self.assertIs(ctx.policy, native_policy)
    self.assertEqual(session.workspace_fd, workspace_fd)
    self.assertEqual(session.workspace_fd_identity, workspace_identity)
```

新增测试方法，不替换两原 candidate 测试：

```python
def test_public_context_no_scope_actual_package_identity_and_fd_boundary(self):
    for mutation in ("none", "rename", "unlink", "replace"):
        with self.subTest(mutation=mutation): self.probe(False, mutation, "context")

def test_public_context_scope_actual_package_identity_and_fd_boundary(self):
    for mutation in ("none", "rename", "unlink", "replace"):
        with self.subTest(mutation=mutation): self.probe(True, mutation, "context")
```

每模式/拓扑/变异保留同一真实 session 的两 dispatch，fresh helper owner 每轮 EBADF/closed，workspace 原 FD/身份持续活；最后 session 自己关闭，不要求两轮 FD 号码不同，也不允许复用同 owner。上下文不 close workspace 或 helper。

- [ ] `TestInstalledCandidateFaults.run_fault` 增加 `consumer="candidate"`，原 root/workspace/manual FD 准备替换成 `probe_workspace(root, stack, consumer)`（返回 identity 局部名仍为 `identity`）。原 policy 赋值替换为下块：

```python
policy = (session.policy("code", process_limit=1, wall_timeout_seconds=6,
                         output_limit_bytes=256) if session is not None
          else replace(policy_for(workspace), process_limit=1,
                       wall_timeout_seconds=6, output_limit_bytes=256))
ctx = (ToolContext(workspace, sandbox=sandbox, policy=policy,
                   workspace_session=session) if session is not None else None)
context_calls = []
```

其 wrap 的 `options = dict(...)` 之前、已完整构建 `command` 后插入：

```python
if ctx is not None:
    context_calls.append(helper_object)
    if resource_args:
        prepared = ctx.wrap_command_with_resource_receipt(command, control,
            resource_args[0], resource_args[1], helper_object=helper_object)
    else:
        prepared = ctx.wrap_command_with_violation_receipt(command, control,
                                                           helper_object=helper_object)
    self.assertIs(prepared.helper_object, helper_object)
    return prepared
```

原 broker 调用完整替换为：

```python
entry, entry_options = observed_entry(resource_mode, consumer)
result = entry([str(payload)], cwd=workspace, sandbox=sandbox, policy=policy,
    timeout=3 if scenario == "timeout" else 4, command_wrapper=wrap, **entry_options)
```

原打印 dict 增加 `consumer=consumer, context_borrowed=ctx is not None, public_entry=("resource" if resource_mode else "violation") if ctx is not None else None`；在原 `self.assertEqual(len(owners), 1)` 后补 `if ctx is not None: self.assertEqual(context_calls, [owner for owner, _ in owners])`。这行不授 payload 成功；原 fault-hit、no-ready、异常原对象、unknown、scope_gc 与终态先于 finally 补救原样保留。追加两方法：

```python
def test_real_public_context_faults_no_scope(self):
    for scenario in ("bad_ack", "missing_ack", "observer_start", "observer_runtime", "observer_close",
                     "timeout", "output_limit", "launch_failed", "keyboardinterrupt", "systemexit", "helper_close_unknown"):
        with self.subTest(scenario=scenario): self.run_fault(False, scenario, "context")

def test_real_public_context_faults_scope(self):
    for scenario in ("bad_ack", "missing_ack", "observer_start", "observer_runtime", "observer_close",
                     "resource_start", "resource_configured", "resource_close", "scope_close_unknown",
                     "timeout", "output_limit", "launch_failed", "keyboardinterrupt", "systemexit", "helper_close_unknown"):
        with self.subTest(scenario=scenario): self.run_fault(True, scenario, "context")
```

新矩阵目标为原 candidate 42 records 原封保留＋context/public 42 records，共 84（32正控＋52故障，48 identity PASS）。新 context 记录就是公共入口真实消费者，不能仅凭标签授信用。6 个 unknown 记录仍预设拒绝，不写 cleanup 全部成功。缺/skip/inconclusive 任一格未验收。

- [ ] bounded publisher `enums` 增加 `"consumer": {"candidate", "context"}`、`"public_entry": {None, "violation", "resource"}`；`booleans` 集合增加 `"context_borrowed"`。不打印路径、原命令或任意 label；原 schema/8192上限/hash/状态验证、失败及 timeout 部分 records 发布保持。candidate 原记录亦明确 consumer，包/manifest hash 仍绑定每 record，wheel SHA、candidate SHA 和 job 身份由原 runner/job日志绑定，不能用 untrusted 字段覆写外部 job 身份。

- [ ] 在 `TestInstalledProbeRecordPublishing` 新增完整白名单回归，先 FAIL（标签被丢弃）、修后 GREEN：

```python
def test_public_context_labels_are_bounded_and_survive_publication(self):
    import contextlib
    import importlib.util
    import io
    import json
    source = Path(__file__).resolve().parents[1] / "scripts/run_native_wheel_ci.py"
    spec = importlib.util.spec_from_file_location("public_context_publish_test", source)
    subject = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(subject)
    raw = dict(architecture="x86_64", topology="scope", consumer="context",
               public_entry="resource", context_borrowed=True)
    output = io.StringIO()
    with contextlib.redirect_stdout(output): subject._publish_helper_dispatch_records(json.dumps(raw))
    line = output.getvalue().strip()
    published = json.loads(line.removeprefix("helper-dispatch-record "))
    for field in ("consumer", "public_entry", "context_borrowed"):
        self.assertIn(field, published, "publisher dropped a bounded public-context label")
    self.assertEqual(published["consumer"], "context")
    self.assertEqual(published["public_entry"], "resource")
    self.assertIs(published["context_borrowed"], True)
    raw.update(consumer="PRIVATE-PATH", public_entry="PRIVATE-COMMAND", context_borrowed="true")
    output = io.StringIO()
    with contextlib.redirect_stdout(output): subject._publish_helper_dispatch_records(json.dumps(raw))
    self.assertNotIn("PRIVATE", output.getvalue())
    published = json.loads(output.getvalue().strip().removeprefix("helper-dispatch-record "))
    for field in ("consumer", "public_entry", "context_borrowed"): self.assertNotIn(field, published)
```

## Task 5：fresh 审查、完整软件门与四 runner 实证

Task4 实施记录：publisher 原字段丢失 RED 为 1 assertion FAIL / 0 ERROR，最小白名单同步后4 publisher tests PASS；完整 dispatch 模块41 tests / 0.225s / 0 skip / OK。当前实际 wheel 在 `/tmp/icode-task4-wheel-7EN8vB` 构建，独立 venv 无 PYTHONPATH 注入、`-I` 执行探针，实际 10 tests / 77.970s / 0 skip / exit0。root 直接读 stderr 和全部 JSON 后重算：candidate/context 各42＝16正控＋26故障，各24 identity PASS，84终态的workspace/process/channels/threads均true，六预设unknown均raised/LinuxHelperObjectError、不授全回收。wheel `1d5cd536879880bfb3c207b8d88f227b1ca05b46d50855ee6199808653a42b10`、helper `f7dee11ab61d7b2605368625b0390304dd4fdca2dbb41a9deac22c835ff08ae6`、manifest `200b1017becc5806e8c154a8aa33aaf94d067b5f04739889d8ecb9810be44cce`；本机不是四CI新SHA或完整R2/R3验收。

**状态**

- [x] 任务完成（软件门与最终 SHA 四 Linux 公共消费矩阵；不代表整体 R2/R3）

**Dependencies:** Task 4
**Parallelizable:** No（冻结候选后审查、测试、发布依次执行）

- [ ] root 阅读实际 diff，核源代码只在两文件、各测试真实命中；验证所有文档代码 AST、导入、格式和脚本，无 API 名称占位。生产 ordinary/generic/Git/Windows/Reviewer/leased 回归原样，Linux mock 不作 Windows native。
- [ ] 运行 focused 软件门，实际命令如下；零 failures/errors 才前进，skip 原因逐项界定，不宣称全部 native 已通过。

```bash
.venv/bin/python -m unittest tests.test_linux_helper_dispatch tests.test_linux_helper_object tests.test_linux_workspace_fd tests.test_linux_product_task_quota tests.test_linux_contract_engineering tests.test_linux_violation_receipt -v
.venv/bin/python -m compileall -q src/icode/execution_broker.py src/icode/tools/base.py scripts/run_native_wheel_ci.py scripts/probe_installed_linux_helper_object.py
.venv/bin/python scripts/preflight.py
```

preflight 是原 secrets/submodule/完整 unittest 三道守护，不拆掉慢测试、不修改 skip 策略、不用focused替代完整门。同步核原 ICODE-SKILL 契约与子模块 clean；vendor 不因本片改动。
- [ ] 每个软件主阶段刷新固定研究结论与实际候选记录，由 root 按现有权限维护 live；writer 本轮不改 live。fresh SPEC 再由不同 QUALITY，C0/I0/M0；必要修复后重新冻结 SHA/hash，旧审查不能替代。
- [ ] 按用户既有授权/发布流程取得用于 CI 的最终候选；文档 writer 不执行提交、推送、发布或改分支。四 runner 沿现有 workflow、`scripts/run_native_wheel_ci.py` 的完整实际 build/install 接线，不新增权限或 runner。
- [ ] 每格 root 拉取同一 SHA actual job 原 logs：84 records 分层完备，candidate与context/public各16正控＋26故障；两拓扑、四mutation、同session两dispatch、包/manifest/wheel hash、48 identity、故障点及终态齐全。job PASS 之外还须逐 record 核 workspace_live、process/channels/threads、owner/scope状态，unknown拒绝与一次尝试、不授全部回收；补救前终态才有信用。
- [ ] public/context每格实际 PASS 才记阶段发布验收，旧Task3/private门与本机source bridge不能替代。其它CI完整状态另核，不由四Linux格推导总体R2/R3 ready、模型90%兼容、内容封印、发布者/动态库/祖先认证或prepare全生命周期固定。

## 固定研究复用与取舍

复用 [live](../../agent-landscape-live.md) 的独立只读证据；本轮未取得新 HEAD，未刷新20项。Codex观察2026-10-11 20:07 UTC、提交 `27065a91ccbf5ba8532844be3777fcf83b77820d`：[bundled_bwrap.rs](https://github.com/openai/codex/blob/27065a91ccbf5ba8532844be3777fcf83b77820d/codex-rs/linux-sandbox/src/bundled_bwrap.rs)、[exec_util.rs](https://github.com/openai/codex/blob/27065a91ccbf5ba8532844be3777fcf83b77820d/codex-rs/linux-sandbox/src/exec_util.rs)，Apache-2.0。systemd观察2026-10-11 20:30–20:40 UTC、固定v249 `f6278558da0304ec6b646bb172ce4688c7f162a5` 与v255 `db11bab38ccf1ed257f310d29070843d4c58ea01`：[path-util.c](https://github.com/systemd/systemd/blob/f6278558da0304ec6b646bb172ce4688c7f162a5/src/basic/path-util.c)、[run.c](https://github.com/systemd/systemd/blob/db11bab38ccf1ed257f310d29070843d4c58ea01/src/run/run.c)，LGPL-2.1-or-later。

采纳明确owner/借用/procfd对象消费与现有scope第二跳：ICODE已具有工厂、held wrapper及core，收益是接通真实公共消费者，成本是内部callback收紧与四runner实际复验；不复制上游源码，无许可/依赖/权限增量。暂缓sealed memfd、发布者/加载闭包认证及全入口生命周期，独立设计成本大且不解决本片接线缺口。不适配可选摘要、路径fallback、全局cache、TypeError旧回调重试及第一跳FD当第二跳证据；验收由同引用、实际exe身份、明确fault命中和unknown拒绝证明。

## 自审与交接

设计各节映射：§1–3→Task1/2，§4→Task1/3/4，§5→Task3/4，§6→Task5，§7→固定研究。owner/session职责、None精确omit、私有legacy、有效faultfixture、source bridge信用和四格同SHA门均有具体步骤。本轮只文档自审，root 的 fresh双审尚待执行；不能提前记录本片测试/CI通过。

【架构级自检报告】（仅 PLAN 静态自审）

- ✅ 语法/编译：完整代码资产与命令列明；本轮未编译，不授源码语法通过信用。
- ✅ 依赖/调用链：两 public→唯一core→真实ctx→held wrapper→scope/Popen/native，quota callback成对同步。
- ✅ 逻辑/边界：每dispatch独立owner，ctx只借用，None不传keyword，workspace跨dispatch仍活。
- ✅ 异常处理：首信号原对象、未知清理一次尝试、固定拒绝、目标命中及补救前终态均列明。
- ✅ 关联模块：生产两文件与必要fixture/probe/publisher，不扩展原ready或其它执行模式。
- ✅ 兼容安全：直接旧receipt形状保持；公共内部callback有意收紧，不承诺任意旧callback兼容。
- ✅ 可运行性：提供完整测试/替换函数与实际门；此轮未实施/测试/CI，不报告100%。

---
**Execution Mode:** serial

执行交接为 root fresh SPEC→不同 QUALITY 后的逐任务实施。本轮明确仅PLAN，未自动调用执行skill、未启动实施或子代理。

后续 root 执行记录：完整 PLAN 冻结 `c1cd62a5938df9265c9f446310bce12d3be3939af516273316d9bc0656ed5cbd` 已 fresh SPEC→不同 QUALITY C0/I0/M0，root 全文阅读及24 Python资产 AST通过。Task1 fresh实施者取得单方法两模式 owner=0 的实际 assertion RED（1 method/2 failures/0 errors/skip）后 GREEN；模块40/40通过，root独立复跑40项/0.239s/0skip通过并核两源diff。broker冻结 `81ea0b0f9b7cf9122dc93bcfd96ca173a56b15aa89786a11d0b8974e39c4c108`，test冻结 `b0971da83956298c228d23f10f3110f6635813adbea30c2f50948ba47af825c7`，唯一core/cleanup默认未变；Task2由fresh实施者继续。此为逐任务软件中间状态，尚未完整preflight、提交或公共installed四格，不授整体验收信用。用户既有直接main/远端仅main要求覆盖skill工作树默认，实施串行、阶段完整验证后才发布。

Task2实施时发现原真实resource测试资产的 `icode-fixture.scope` 不符合既有 `icode-task-[0-9a-f]{32}.scope` 合同，会在借用断言前拒绝。仅改该真实调用为既有合法fixture unit，不改生产验证规则；实施者两拓扑都取得真实同引用缺口 assertion RED（1 method/2 failures/0 errors）。None严格mock与政策拒绝测试无需真实scope，沿原fixture，不用其结果代真实透传信用。

Task2后续最小透传 GREEN：实施者新增3方法、既有6项focused回归通过；root独立实际复跑新增3项/0.872s/0skip通过并逐文件核diff。base冻结 `9515d0beb02ec45c752fb5f2aaa7e7d923e86403f285ba5b0897518e08cc6833`，workspace测试冻结 `5b7553adb844d27c01bfdbb27fc8e96609586f6b4e4a3415df499a4a4fdb1f5f`；原close、政策/会话核验与None旧shape保持。Task3同步旧fixture与installed quota callback已由fresh实施者串行开始；公共安装包原生矩阵及完整软件门尚未执行，不预记通过。

Task5 软件候选门（2026-10-11 23:29 UTC）：最终7个SOURCE已独立fresh SPEC→不同QUALITY C0/I0/M0，root阅读实际变更和调用上下文；相关六模块合168 tests / 0 skip / OK，compileall `-j1`、site/governance、文档代码AST与diff检查通过。冻结期间原完整preflight session69494实际exit0，secrets/submodule/full-unittest三道全通过；没有以focused替代全量。固定vendor `21566a589cbe98bd35372a04bbb6ca1c51d8eed2` clean；远端仅main。准备按已授权阶段流程发布供四Linux新SHA安装验证，Task5四格部分仍待办，不标整体完成。

最终审查SOURCE SHA-256：broker `81ea0b0f9b7cf9122dc93bcfd96ca173a56b15aa89786a11d0b8974e39c4c108`；base `9515d0beb02ec45c752fb5f2aaa7e7d923e86403f285ba5b0897518e08cc6833`；runner `5bc2c0358333e3dc642a705c950024b2d92b0977fbc5b89ea2ad4fd20112243b`；probe `c9cfa9e8a9ded6c828503ed573d663c4e91f4879618e7e5f059ed80f14c4b866`；dispatch tests `2361de3ac343674fb6a3ccbaafc0314ea93e410ee4ce5b3a1bb3613933a4691f`；workspace tests `aaed190e79e0900adf460af72cf5fd37f7b7253c84a540cd8390daa8292537b2`；quota tests `540be8e59c7b31d8b306cdd08a7d84b7d79f217ad80c11c2d1f656a625b01f4b`。

【架构级自检报告】（软件候选与本机安装包，不替代四格或整体R2/R3）

- ✅ 语法/编译：实际compileall与wheel构建通过。
- ✅ 依赖/调用链：两public→原core→真实ctx/session→held wrapper；关联callback已同步。
- ✅ 逻辑/边界：168相关回归及本机10项/84条矩阵通过。
- ✅ 异常处理：故障实际命中、首信号/unknown拒绝/真实终态保持。
- ✅ 关联模块：7SOURCE与批准文档成对审查；原完整三道门通过。
- ✅ 兼容安全：None/privatelegacy保持，公开内部callback有意收紧，无新增权限或ready放宽。
- ✅ 可运行性：本机实际安装包与完整软件门通过；最终SHA四CI、模型及整体R2/R3待验，不宣称100%。

后续四格验收：main `1c44aa09f1660929d0b6b8e63bf1952deed6f6e3` 的 CI38184549150，四 Linux native job `114603966674`、`114603966803`、`114603966841`、`114603966864` 均实际 success。root与独立观察者分别取得原日志重算：每格84记录、两consumer各16正控/26故障/24身份PASS，合336记录/192身份观察；终态检查无异常，六条预设unknown每格仍拒绝且不计全回收。成功runner隐藏脚本stderr，不声称日志打印Ran10。四格最终SHA门通过，整体CI仍有Windows Reviewer失败及未终态任务，模型/准入/整体R2/R3不由此补授。具体平台、wheel/helper/manifest标识同步持续竞品台账。
