# Linux Prepared Step Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development (recommended) or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** 建立真实 Linux helper 与活 session/policy 的内部单步准备、一次 attachment、排他借用和唯一 helper 回收。

**Architecture:** 新增内部 linux_prepared_step.py，复用 S0a 同 FD 静态检查、S0b 来源观察和 S1a lease 活性检查。scope 独占 helper，借用 workspace/lease；attachment 自身就是可信宿主本次调用视图，消费状态与回收状态分账。本片零 broker/runner/工具/ready 生产接线，S1c broker 与 S2 runner 另立 PLAN。

**Tech Stack:** Python >=3.11、标准库 unittest、Linux fstat/lstat/pread、现有 LandlockSandbox/SandboxPolicy/WorkspaceManager。

---

## 0. 状态、前门与三问

状态：PLAN ONLY。作者只新建本文件；未创建源码/scaffold/test、未执行文内代码/测试/预检、未 Git 写入。已全文读 writing-plans 技能（无其它 required reference）、母 [DESIGN](../specs/2026-10-12-linux-prepared-step-scope-design.md)、S0a/b 模块及真实 workspace/policy/CP 相关符号。用户 main 工作区覆盖技能 worktree 默认；DOCS ONLY 覆盖技能自动实施交接。

实读 HEAD 为 main 3ee3b48ff9a14be9f39b36968561fdb6870ab1fc，实际 S0b commit/push。S1a [活 lease PLAN](./2026-10-12-linux-live-lease-validation.md) 已计划双审，其 SOURCE 尚未发布；本 writer 初读到临时 scaffold，随后实际重读最终 `_validate_active`：真实 stream 存在/未关闭、精确 int FD≥3、原锁 identity 校验、普通 Exception 固定包装及原信号传播。root 报最终 workspace SHA c8692242d1392e6170e075d208c042e7c6b33cc65eaeaa93d7fa9d0bcc12e368，fresh SPEC→不同 QUALITY C0/I0/M0，complete preflight 45514 在途；这不是发布证据。**S1b SOURCE 开始前 root 必须核 S1a 原 complete preflight、实际 main commit/push、应等 CI terminal，冻结新的真实 HEAD 与源码摘要。** 不得以计划时点 HEAD、scaffold 或未终态 SOURCE 接管 S1a。

三问：真实问题是单步 prepare→consume 生命周期缺失；已有实现为 open_linux_helper_object、validate_static_linux_helper、observe_linux_helper_source、真实 WorkspaceSession 的目录 owner/FD 以及将发布的 TicketLease._validate_active；调用链限定新内部模块和测试，生产调用方暂为零。root sequential-thinking 173–175 已记录需求分解、复用、风险，本 writer 不扩 SOURCE 授权。

| 精确四路径 | 责任 |
| --- | --- |
| 新建 src/icode/linux_prepared_step.py | prepare/原引用绑定/一次 attachment/borrow/close |
| 新建 tests/test_linux_prepared_step.py | 真实 session/lease/FD/factory 与状态/故障负控 |
| 本 docs/nbl/plans/2026-10-12-linux-prepared-step-lifecycle.md | 计划与后续实际观察 |
| 最小更新 docs/agent-landscape-live.md | 固定研究与实际软件阶段边界 |

不得改母 DESIGN、S0a/b/S1a 源码、旧测试、broker、runner、ToolContext、registry、CLI/MCP、ready、vendor 或安装脚本。第五路径先报 root，不自行扩范围。本片不授整体 S1、S2、installed、自动模式、LA-2、R2/R3。

## 1. 最小内部接口与实际 caller 映射

prepare_linux_step(sandbox, *, policy, workspace_session) 没有 path/hash/ready/owner override。直接 LinuxPreparedStep(...) 也走同一 factory 与全部门。真实 class 只筛输入，不认证来源；不承诺防 object.__new__/反射篡改/恶意 Python 宿主，不加 secret/全局注册表。普通手构对象缺真实资源校验不能通过。

scope._attach(*, policy, workspace_session) 一次生成实际 _LinuxStepAttachment 引用，原子保存并返回；该 view 本身就是未来 runner 本次栈内 invocation owner，ctx 持同引用，无第二 token。view._bind_attempt(attempt, *, validate_attempt) 一次绑定未来真实 cp.step_start 的返回值。validator 是可信 runner 栈内捕获实际 CP/out_dir/ticket/step/attempt 的只读函数，成功返回 None，失败抛异常；True/False 均拒绝。绑定与每 borrow 都执行它，不缓存 bool 自证。

**S1b 只有内部软件模型信用。** 任意 callback 无法认证真实 runner；测试 validator 明确软件 double。S2 不得以 lambda 返回 None、typed view、UUID 或 caller attempt 字符串代替实际 CP 事实，也不能扩大母设计可信宿主上限。

实读已有 ControlPlane.step_start(out_dir, step, *, ticket_id, request)、trace(out_dir, *, limit=50)；runner._step_start_request 读取 events type/event_type 和 payload.step/attempt。没有通用 verify_step_started。run_contract_step 当前真实 step_start 在 1319–1326；deepcheck 有专用有限事件验证，不当所有 step 的通用 API。

S2 必须先完成原身份/能力/CP前置，再在本次真实栈 claim attachment，执行原 cp.step_start；可信 validator 核真实 CP 成功、本次 ticket/step/attempt 与实际返回一致、存在对应 start 且未 finish。pending/CP失败 finally 也结束 view。ToolContext 必须同时持当前实际 session/policy/view/attempt；不得从 scope 反取 expected 冒充 caller。第二次同名 runner 调用在第二 CP start/model/payload 之前拒绝重新 attach，外部 owner 仍 active 的目标负控留 S2。

未来 S1c broker 的借用形状如下（此片不写 broker）：

~~~python
with prepared_step.borrow(
    policy=policy, workspace_session=workspace_session, attempt=attempt,
) as helper_object:
    # Existing unique command core uses this same owner.
    # On command resource cleanup unknown, before releasing borrow:
    prepared_step._mark_faulted()
~~~

prepared_step 是实际 ctx attachment；其余事实是 caller 当前 ctx/栈中的实际值。母设计列出的两新增 observed 参数不等于禁止传必需内部 attempt；S1c 精确 PLAN 必须明确传递本次 attempt 的最终 signature，不只向 scope 查询 expected。若 caller 无法提供事实，先返审，不能在本片隐藏债务。

| 状态轴 | 合同 |
| --- | --- |
| 消费 | prepared→attached_pending→attached_bound→spent；命令 cleanup unknown→sticky faulted；finish 不清 faulted |
| helper 回收 | active→closed/unknown；unknown 不重试；confirmed repeat noop |
| borrow | 单 in-flight，同时/重入拒绝；单命令退出只释放排他，不关 helper/结束 attachment |
| workspace/lease | 借原引用，只读校验；创建者仍唯一关闭 |

S0b 来源观察以同一个固定错误包装 body 与临时目录/manifest FD cleanup unknown，调用方不能据异常类型精确区分。因此借用阶段该观察任何失败都保守置 sticky faulted：拒绝之后继续消费，helper 回收责任仍留创建者；普通 caller reference 或无 owned resource 的 static 失败不借此伪报 helper close unknown。不是新的 source API，不重试观察补成功。

## 2. 固定独立研究

复用独立研究者窗口 **2026-10-12 01:41:43–01:42:24 UTC**，不是本作者本轮重新实取，也非最新 HEAD/20 项刷新。

| 固定 primary source | 观察与取舍、收益/成本、验收 |
| --- | --- |
| Codex 27065a91ccbf5ba8532844be3777fcf83b77820d [process_manager.rs L899–911](https://github.com/openai/codex/blob/27065a91ccbf5ba8532844be3777fcf83b77820d/codex-rs/core/src/unified_exec/process_manager.rs#L899-L911)、[L1155–1177](https://github.com/openai/codex/blob/27065a91ccbf5ba8532844be3777fcf83b77820d/codex-rs/core/src/unified_exec/process_manager.rs#L1155-L1177) | L909/L1165 Arc::ptr_eq：采纳 actual reference，成本是显式 caller 参数/负控；equal-but-new session/policy 必须命中目标 identity 门。root 实际复取同固定提交确认路径；本作者只修链接，未声称本轮实取。 |
| 同提交 [bundled_bwrap.rs L65–101 / L158–184](https://github.com/openai/codex/blob/27065a91ccbf5ba8532844be3777fcf83b77820d/codex-rs/linux-sandbox/src/bundled_bwrap.rs#L65) | held File/procfd 分层采纳，复用 ICODE 同 FD factory/static/source；expected None 跳 hash 不适配；验收无 override/第二 factory/fallback。 |
| OpenHands SDK 3934349da2db0433238621542173a00a8af7439c [base.py L58–64 / L158–169](https://github.com/OpenHands/software-agent-sdk/blob/3934349da2db0433238621542173a00a8af7439c/openhands-sdk/openhands/sdk/workspace/base.py#L58)、[local.py L36–80](https://github.com/OpenHands/software-agent-sdk/blob/3934349da2db0433238621542173a00a8af7439c/openhands-sdk/openhands/sdk/workspace/local.py#L36) | 默认 exit 不清理，callback/result 非 cleanup 信用；不适配成功结果即回收。采纳显式 ownership；成本为 unknown/信号矩阵。 |

[Codex LICENSE](https://github.com/openai/codex/blob/27065a91ccbf5ba8532844be3777fcf83b77820d/LICENSE) Apache-2.0；[OpenHands LICENSE](https://github.com/OpenHands/software-agent-sdk/blob/3934349da2db0433238621542173a00a8af7439c/LICENSE) MIT。只借机制，无复制/新依赖/新权限。暂缓跨调用缓存、完整 loader 信任、密封与正式准入；兼容影响限新内部有限门，旧 caller 不接线。

## 3. 串行任务

### Task 1: 真实 fixture 与有效 assertion RED

**状态**

- [x] 任务完成

**Dependencies:** None（先满足 §0 S1a 已发布前门）
**Parallelizable:** No（唯一 SOURCE writer；不与在途 S1a 重叠）

- [x] **Step 1:** root 核真实新 HEAD/S1a terminal/摘要，全文核 _validate_active 最终实现；不合合同先停止 S1b。
- [x] **Step 2:** 新建 tests/test_linux_prepared_step.py，完整正文如下。复用已读 tests/test_linux_workspace_fd.py 的 session() 和 tests/test_linux_contract_engineering.py 的真实 layered Git fixture。Git 在测试临时目录创建，不是本 writer 执行；保留 session.policy 全保护集合，不删除 snapshot .git 保护换正控。外置 pipx-like actual locator/runtime 映射只属软件 fixture，不算 installed。

~~~python
"""Real resources/internal lifecycle; no CP, installed or runner credit."""
from __future__ import annotations
import copy
from dataclasses import replace
import hashlib
import os
from pathlib import Path
import pickle
import stat
import struct
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch
from tests._support import temp_workspace
import icode.native_helper as locator
import icode.linux_helper_object as factory
import icode.linux_prepared_step as subject
from icode.isolation import LandlockSandbox
from icode.linux_static_helper import validate_static_linux_helper
from icode.linux_helper_source import observe_linux_helper_source
from icode.workspace import WorkspaceManager, _WorkspaceObject

REAL_CLOSE, REAL_FSTAT = os.close, os.fstat
ERROR = 'Linux prepared step is unavailable'

def image(types=(1,)):
    h = bytearray(64)
    h[:7] = b'\x7fELF\x02\x01\x01'
    struct.pack_into('<HHI', h, 16, 2, 62, 1)
    struct.pack_into('<Q', h, 32, 64)
    struct.pack_into('<HHH', h, 52, 64, 56, len(types))
    return bytes(h) + b''.join(struct.pack('<IIQQQQQQ', t, 5, 0, 0, 0,
        64 + 56 * len(types), 64 + 56 * len(types), 4096) for t in types)

@unittest.skipUnless(sys.platform.startswith('linux') and callable(getattr(os, 'pread', None)),
    'Linux real resource fixture; skip is not acceptance')
class PreparedTests(unittest.TestCase):
    def setUp(self):
        d = temp_workspace()
        self.root = d.__enter__()
        self.addCleanup(d.__exit__, None, None, None)
        source = self.root / 'source'
        source.mkdir()
        (source / 'data.txt').write_text('real git fixture\n')
        for args in (('init', '-q'), ('add', 'data.txt'),
                ('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                 '-c', 'core.hooksPath=' + str(self.root / 'absent-hooks'),
                 'commit', '-qm', 'prepared fixture')):
            subprocess.run(['git', '-C', str(source), *args], check=True,
                capture_output=True, timeout=15)
        self.manager = WorkspaceManager(source, self.root / 'data',
            'prepared-project', isolate_git_metadata=True)
        self.session = self.manager.open('prepared-ticket', 'prepared-run')
        self.addCleanup(self.session.close)
        self.policy = self.session.policy('code', process_limit=16,
            wall_timeout_seconds=30, output_limit_bytes=4096)
        self.assertEqual(self.session.workspace_root, self.session.git_status_identity.code_root)
        self.assertFalse((self.session.workspace_root / '.git').exists())
        self.prefix = self.root / 'pipx' / 'venvs' / 'icode-agent'
        package = self.prefix / 'lib' / 'python3.11' / 'site-packages' / 'icode'
        native = package / 'native'
        native.mkdir(parents=True)
        module = package / 'native_helper.py'
        module.write_text('# actual locator mapping fixture\n')
        self.binary, self.manifest = native / 'icode-landlock', native / 'icode-landlock.sha256'
        self.write_image(image())
        for target, name, value in ((locator, '__file__', str(module)),
                (sys, 'prefix', str(self.prefix)), (sys, 'base_prefix', '/usr')):
            p = patch.object(target, name, value)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(factory.platform, 'machine', return_value='x86_64')
        p.start()
        self.addCleanup(p.stop)
        self.sandbox = LandlockSandbox(str(self.binary), manifest=str(self.manifest))
        self.scopes = []
        self.addCleanup(self.cleanup_scopes)
        self.precheck_fixture()

    def precheck_fixture(self):
        # Existing S0/S1a functions establish real fixture premises only.
        # This separate owner is closed here; it does not authorize the scaffold.
        self.policy.validate()
        self.sandbox.prepare_policy(self.policy)
        self.session.lease._validate_active()
        fd = self.session.workspace_fd
        self.assertIs(type(fd), int)
        self.assertGreaterEqual(fd, 3)
        held, path = REAL_FSTAT(fd), os.lstat(self.session.workspace_root)
        self.assertTrue(stat.S_ISDIR(held.st_mode))
        self.assertTrue(stat.S_ISDIR(path.st_mode))
        self.assertEqual((held.st_dev, held.st_ino), self.session.workspace_fd_identity)
        self.assertEqual((path.st_dev, path.st_ino), self.session.workspace_fd_identity)
        with factory.open_linux_helper_object(self.binary, self.manifest) as owner:
            validate_static_linux_helper(owner)
            observed = observe_linux_helper_source(self.sandbox, policy=self.policy, owner=owner)
            self.assertEqual(observed.helper_path, self.binary)
            self.assertEqual(observed.manifest_path, self.manifest)

    def write_image(self, data):
        self.binary.write_bytes(data)
        self.binary.chmod(0o700)
        self.manifest.write_text(hashlib.sha256(data).hexdigest() + '\n', encoding='ascii')

    def cleanup_scopes(self):
        for scope in self.scopes:
            if scope._owner_state == 'active':
                scope.close()

    def prepare(self):
        scope = subject.prepare_linux_step(self.sandbox,
            policy=self.policy, workspace_session=self.session)
        self.scopes.append(scope)
        return scope

    def attach(self, scope):
        return scope._attach(policy=self.policy, workspace_session=self.session)

    def bind(self, view):
        def validator(actual):
            if actual != 'software-attempt':
                raise RuntimeError('private attempt')
        view._bind_attempt('software-attempt', validate_attempt=validator)
        return view

    def borrow(self, view, **changes):
        args = dict(policy=self.policy, workspace_session=self.session, attempt='software-attempt')
        args.update(changes)
        return view.borrow(**args)

    def enter(self, context):
        with context:
            pass  # assertRaises outside must report the target "not raised".

    def reject(self, call):
        with self.assertRaises(subject.LinuxPreparedStepError) as caught:
            call()
        self.assertEqual(str(caught.exception), ERROR)
        self.assertIsNone(caught.exception.__cause__)
        self.assertTrue(caught.exception.__suppress_context__)

    def test_wrong_session_reference_target(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        clone = replace(self.session)
        self.assertIs(clone.lease, self.session.lease)
        self.assertIs(clone._workspace_object, self.session._workspace_object)
        self.assertEqual(clone, self.session)
        self.reject(lambda: self.enter(self.borrow(view, workspace_session=clone)))
        with self.borrow(view) as owner:
            self.assertIs(owner, scope._owner)

    def test_equal_policy_reference_target(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        equal = replace(self.policy)
        self.assertEqual(equal.policy_hash, self.policy.policy_hash)
        self.reject(lambda: self.enter(self.borrow(view, policy=equal)))
        with self.borrow(view):
            pass

    def test_second_attach_active_owner_target(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        self.assertEqual(scope._owner_state, 'active')
        self.assertEqual(scope._consume_state, 'attached_bound')
        self.reject(lambda: self.attach(scope))
        self.assertIs(scope._attachment, view)

    def test_equal_policy_attach_target(self):
        scope = self.prepare()
        equal = replace(self.policy)
        self.assertEqual(equal.policy_hash, self.policy.policy_hash)
        self.reject(lambda: scope._attach(policy=equal, workspace_session=self.session))

    def test_same_owner_factory_once_and_borrowed_session_survives(self):
        original = subject.open_linux_helper_object
        opened = []
        def opening(*args):
            result = original(*args)
            opened.append(result)
            return result
        with patch.object(subject, 'open_linux_helper_object', side_effect=opening):
            scope = self.prepare()
            view = self.bind(self.attach(scope))
            fd = scope._owner.fileno()
            for _ in range(2):
                with self.borrow(view) as owner:
                    self.assertIs(owner, opened[0])
                    self.assertEqual(owner.fileno(), fd)
            self.assertEqual(len(opened), 1)
            self.assertEqual(scope._consume_state, 'attached_bound')
            view.finish()
            self.assertEqual(scope._consume_state, 'spent')
            self.assertEqual(scope._owner.fileno(), fd)
            scope.close()
            scope.close()
        self.assertEqual(scope._owner_state, 'closed')
        with self.assertRaises(OSError):
            REAL_FSTAT(fd)
        self.session.lease._validate_active()
        self.assertIsNotNone(self.session.workspace_fd_identity)

    def test_snapshot_nested_protection_is_not_removed(self):
        source = self.root / 'snapshot-source'
        source.mkdir()
        (source / 'data').write_text('snapshot')
        session = WorkspaceManager(source, self.root / 'snapshot-data', 'snapshot').open('ticket', 'run')
        try:
            policy = session.policy('code')
            self.assertIn(session.workspace_root / '.git', policy.protected_paths)
            self.reject(lambda: subject.prepare_linux_step(self.sandbox,
                policy=policy, workspace_session=session))
        finally:
            session.close()

    def test_bad_types_names_and_gates_before_factory(self):
        from types import SimpleNamespace
        from icode.sandbox_policy import NetworkMode
        root = self.session.workspace_root
        cases = ((SimpleNamespace(), self.policy, self.session),
            (self.sandbox, SimpleNamespace(), self.session),
            (self.sandbox, self.policy, SimpleNamespace()),
            (self.sandbox, replace(self.policy, run_id='other'), self.session),
            (self.sandbox, replace(self.policy, ticket_id='other'), self.session),
            (self.sandbox, replace(self.policy, write_roots=()), self.session),
            (self.sandbox, replace(self.policy, network_mode=NetworkMode.PROXY_ALLOWLIST,
                allowed_domains=('example.invalid',)), self.session),
            (self.sandbox, replace(self.policy, deny_write_roots=(*self.policy.deny_write_roots, root / 'nested'),
                protected_paths=(*self.policy.protected_paths, root / 'nested')), self.session))
        with patch.object(subject, 'open_linux_helper_object') as opening:
            for sandbox, policy, session in cases:
                self.reject(lambda: subject.prepare_linux_step(sandbox,
                    policy=policy, workspace_session=session))
            opening.assert_not_called()

    def test_lease_live_names_and_same_fields_new_lease_reference(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        original = self.session.lease
        clone = replace(original)
        self.assertIs(clone._stream, original._stream)
        self.session.lease = clone
        try:
            self.reject(lambda: self.enter(self.borrow(view)))
        finally:
            self.session.lease = original
        for target in (self.session, original):
            for field in ('project_id', 'ticket_id', 'run_id'):
                old = getattr(target, field)
                try:
                    setattr(target, field, old + '-drift')
                    self.reject(lambda: self.enter(self.borrow(view)))
                finally:
                    setattr(target, field, old)
        original.release()
        self.reject(lambda: self.enter(self.borrow(view)))
        self.reject(self.prepare)

    def test_workspace_same_fd_different_owner_reference(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        original = self.session._workspace_object
        self.session._workspace_object = _WorkspaceObject(original.descriptor, original.identity)
        try:
            self.reject(lambda: self.enter(self.borrow(view)))
        finally:
            self.session._workspace_object = original
        with self.borrow(view):
            pass

    def test_workspace_fd_values_identity_and_nofollow_path(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        obj, path = self.session._workspace_object, self.session.workspace_root
        original = obj.descriptor
        for value in (None, True, False, -1, 0, 1, 2):
            obj.descriptor = value
            try:
                self.reject(lambda: self.enter(self.borrow(view)))
            finally:
                obj.descriptor = original
        directory = self.root / 'wrong'
        directory.mkdir()
        for candidate in (directory, self.binary):
            fd = os.open(candidate, os.O_RDONLY)
            try:
                obj.descriptor = fd
                self.reject(lambda: self.enter(self.borrow(view)))
            finally:
                obj.descriptor = original
                REAL_CLOSE(fd)
        saved = path.with_name('saved-code')
        path.rename(saved)
        try:
            path.symlink_to(saved, target_is_directory=True)
            self.reject(lambda: self.enter(self.borrow(view)))
            path.unlink()
            path.mkdir()
            self.reject(lambda: self.enter(self.borrow(view)))
            path.rmdir()
        finally:
            saved.rename(path)
        with self.borrow(view):
            pass

    def test_closed_workspace_reused_fd_and_identity_drift(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        obj = self.session._workspace_object
        identity = obj.identity
        obj.identity = (identity[0], identity[1] + 1)
        try:
            self.reject(lambda: self.enter(self.borrow(view)))
        finally:
            obj.identity = identity
        other = self.root / 'different'
        other.mkdir()
        replacement = os.open(other, os.O_RDONLY | os.O_DIRECTORY)
        fd = obj.descriptor
        try:
            os.dup2(replacement, fd)
            self.reject(lambda: self.enter(self.borrow(view)))
        finally:
            REAL_CLOSE(fd)
            obj.descriptor = None
            REAL_CLOSE(replacement)
        self.reject(lambda: self.enter(self.borrow(view)))

    def test_policy_and_sandbox_drift(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        for field, value in (('step', 'deepcheck'), ('process_limit', 17),
                ('workspace_root', self.root)):
            old = getattr(self.policy, field)
            try:
                object.__setattr__(self.policy, field, value)
                self.reject(lambda: self.enter(self.borrow(view)))
            finally:
                object.__setattr__(self.policy, field, old)
        for field in ('helper', 'manifest'):
            old = getattr(self.sandbox, field)
            try:
                setattr(self.sandbox, field, old + '-other')
                self.reject(lambda: self.enter(self.borrow(view)))
            finally:
                setattr(self.sandbox, field, old)

    def test_static_recheck_source_replace_and_workspace_install(self):
        self.write_image(image((1, 3)))
        self.reject(self.prepare)
        self.write_image(image())
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        with self.binary.open('r+b') as stream:
            stream.seek(64)
            stream.write(struct.pack('<I', 2))
        self.reject(lambda: self.enter(self.borrow(view)))
        self.write_image(image())
        fresh = self.prepare()
        fresh_view = self.bind(self.attach(fresh))
        self.binary.rename(self.binary.with_name('original-helper'))
        self.write_image(image())
        self.reject(lambda: self.enter(self.borrow(fresh_view)))
        self.assertEqual(fresh._owner_state, 'active')
        # Real locator mapped into the policy RW root must be refused.
        package = self.session.workspace_root / 'installed-icode'
        native = package / 'native'
        native.mkdir(parents=True)
        module = package / 'native_helper.py'
        module.write_text('# writable source fixture\n')
        binary, manifest = native / 'icode-landlock', native / 'icode-landlock.sha256'
        binary.write_bytes(image())
        binary.chmod(0o700)
        manifest.write_text(hashlib.sha256(image()).hexdigest() + '\n')
        sandbox = LandlockSandbox(str(binary), manifest=str(manifest))
        with patch.object(locator, '__file__', str(module)):
            self.reject(lambda: subject.prepare_linux_step(sandbox,
                policy=self.policy, workspace_session=self.session))

    def test_pending_binding_bad_attempt_and_boolean_validator(self):
        scope = self.prepare()
        view = self.attach(scope)
        self.reject(lambda: self.enter(self.borrow(view)))
        for attempt in ('', ' ', True, None, 'bad\nvalue'):
            self.reject(lambda: view._bind_attempt(attempt, validate_attempt=lambda _: None))
        self.reject(lambda: view._bind_attempt('software-attempt', validate_attempt=lambda _: True))
        self.bind(view)
        self.reject(lambda: view._bind_attempt('software-attempt', validate_attempt=lambda _: None))
        self.reject(lambda: self.enter(self.borrow(view, attempt='other-attempt')))

    def test_validator_rechecks_each_borrow(self):
        scope = self.prepare()
        view = self.attach(scope)
        calls, active = [], True
        def validator(attempt):
            calls.append(attempt)
            if not active:
                raise RuntimeError('private CP model')
        view._bind_attempt('software-attempt', validate_attempt=validator)
        with self.borrow(view):
            pass
        active = False
        self.reject(lambda: self.enter(self.borrow(view)))
        self.assertEqual(calls, ['software-attempt'] * 3)

    def test_reentry_concurrent_and_close_active_borrow(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        outcomes = []
        def competing():
            try:
                with self.borrow(view):
                    outcomes.append('entered')
            except subject.LinuxPreparedStepError:
                outcomes.append('rejected')
        with self.borrow(view):
            self.reject(lambda: self.enter(self.borrow(view)))
            self.reject(scope.close)
            self.reject(view.finish)
            thread = threading.Thread(target=competing)
            thread.start()
            thread.join(5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(outcomes, ['rejected'])
        with self.borrow(view):
            pass

    def test_pending_bound_spent_faulted(self):
        for bound in (False, True):
            scope = self.prepare()
            view = self.attach(scope)
            if bound:
                self.bind(view)
            view.finish()
            view.finish()
            self.assertEqual(scope._consume_state, 'spent')
            self.reject(lambda: self.enter(self.borrow(view)))
            self.reject(lambda: self.attach(scope))
            self.assertEqual(scope._owner_state, 'active')
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        with self.borrow(view):
            view._mark_faulted()
        self.assertFalse(scope._inflight)
        view.finish()
        self.assertEqual(scope._consume_state, 'faulted')
        self.reject(lambda: self.enter(self.borrow(view)))
        self.reject(lambda: self.attach(scope))
        scope.close()
        self.assertEqual(scope._owner_state, 'closed')

    def test_copy_pickle_handbuilt_cannot_inject_owner(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        for value in (scope, view):
            for operation in (copy.copy, copy.deepcopy, pickle.dumps):
                self.reject(lambda: operation(value))
        self.reject(lambda: subject._LinuxStepAttachment())
        with patch.object(subject, 'open_linux_helper_object', side_effect=OSError('private')):
            self.reject(lambda: subject.LinuxPreparedStep(self.sandbox,
                policy=self.policy, workspace_session=self.session))

    def test_prepare_postfactory_failure_once_cleanup_and_signals(self):
        for body in (OSError('private'), KeyboardInterrupt('first'), SystemExit(7)):
            captured = []
            original = subject.open_linux_helper_object
            def opening(*args):
                owner = original(*args)
                captured.append(owner)
                return owner
            with patch.object(subject, 'open_linux_helper_object', side_effect=opening), \
                    patch.object(subject, 'validate_static_linux_helper', side_effect=body):
                if isinstance(body, Exception):
                    self.reject(self.prepare)
                else:
                    with self.assertRaises(type(body)) as caught:
                        self.prepare()
                    self.assertIs(caught.exception, body)
            self.assertEqual(len(captured), 1)
            self.assertEqual(captured[0]._state, 'closed')
            self.session.lease._validate_active()

    def test_prepare_body_cleanup_combination(self):
        for body in (OSError('body'), KeyboardInterrupt('first'), SystemExit(3)):
            for cleanup in (OSError('cleanup'), KeyboardInterrupt('later'), SystemExit(8)):
                original, held, closed = subject.open_linux_helper_object, [], []
                def opening(*args):
                    owner = original(*args)
                    held.append(owner.fileno())
                    return owner
                def closing(fd):
                    closed.append(fd)
                    REAL_CLOSE(fd)
                    if fd in held:
                        raise cleanup
                with patch.object(subject, 'open_linux_helper_object', side_effect=opening), \
                        patch.object(subject, 'validate_static_linux_helper', side_effect=body), \
                        patch.object(subject.os, 'close', side_effect=closing):
                    with self.assertRaises(BaseException) as caught:
                        self.prepare()
                self.assertEqual(closed.count(held[0]), 1)
                expected = body if not isinstance(body, Exception) else cleanup
                if isinstance(expected, Exception):
                    self.assertIsInstance(caught.exception, subject.LinuxPreparedStepError)
                else:
                    self.assertIs(caught.exception, expected)

    def test_close_unknown_never_retry_body_cleanup_priority(self):
        for body in (None, RuntimeError('body'), KeyboardInterrupt('first'), SystemExit(5)):
            scope = self.prepare()
            fd, closed = scope._owner.fileno(), []
            def closing(actual):
                REAL_CLOSE(actual)
                if actual == fd:
                    closed.append(actual)
                    raise OSError('unknown close')
            with patch.object(subject.os, 'close', side_effect=closing):
                with self.assertRaises(BaseException) as caught:
                    with scope:
                        if body is not None:
                            raise body
                self.assertEqual(scope._owner_state, 'unknown')
                self.reject(scope.close)
            self.assertEqual(closed, [fd])
            if body is not None and not isinstance(body, Exception):
                self.assertIs(caught.exception, body)
            else:
                self.assertIsInstance(caught.exception, subject.LinuxPreparedStepError)

    def test_borrow_body_signal_releases_not_close(self):
        for body in (RuntimeError('body'), KeyboardInterrupt('first'), SystemExit(5)):
            scope = self.prepare()
            view = self.bind(self.attach(scope))
            with self.assertRaises(type(body)) as caught:
                with self.borrow(view):
                    raise body
            self.assertIs(caught.exception, body)
            self.assertFalse(scope._inflight)
            self.assertEqual(scope._owner_state, 'active')
            with self.borrow(view):
                pass

    def test_checks_faults_fixed_and_signals_original(self):
        for target in ('validate_static_linux_helper', 'observe_linux_helper_source'):
            for error in (OSError('private'), KeyboardInterrupt('first'), SystemExit(9)):
                scope = self.prepare()
                view = self.bind(self.attach(scope))
                with patch.object(subject, target, side_effect=error):
                    if isinstance(error, Exception):
                        self.reject(lambda: self.enter(self.borrow(view)))
                    else:
                        with self.assertRaises(type(error)) as caught:
                            with self.borrow(view):
                                self.fail('entered')
                        self.assertIs(caught.exception, error)
                self.assertFalse(scope._inflight)
                self.assertEqual(scope._owner_state, 'active')

    def test_source_cleanup_unknown_sticky_no_retry_helper_still_owned(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        helper_fd, workspace_fd = scope._owner.fileno(), self.session.workspace_fd
        closed = []
        def closing(fd):
            REAL_CLOSE(fd)
            closed.append(fd)
            if len(closed) == 1:
                raise OSError('source cleanup unknown')
        with patch.object(subject.os, 'close', side_effect=closing):
            self.reject(lambda: self.enter(self.borrow(view)))
        self.assertGreater(len(closed), 1)
        self.assertEqual(len(closed), len(set(closed)))
        self.assertNotIn(helper_fd, closed)
        self.assertNotIn(workspace_fd, closed)
        self.assertEqual(scope._consume_state, 'faulted')
        self.assertEqual(scope._owner_state, 'active')
        self.assertFalse(scope._inflight)
        with patch.object(subject, 'observe_linux_helper_source') as observe:
            self.reject(lambda: self.enter(self.borrow(view)))
            observe.assert_not_called()
        view.finish()
        self.assertEqual(scope._consume_state, 'faulted')
        scope.close()
        self.assertEqual(scope._owner_state, 'closed')
        self.session.lease._validate_active()

if __name__ == '__main__':
    unittest.main()
~~~

- [x] **Step 3:** 首跑缺模块只登记诊断，不授 RED。

~~~bash
.venv/bin/python -B -m unittest tests.test_linux_prepared_step.PreparedTests.test_wrong_session_reference_target -v
~~~

Expected: missing module/import error exit1，不是 assertion RED。
- [x] **Step 4:** root 明确允许 Task1 临时非授权 scaffold 后，只在新模块写下列完整最小正文。它仅使四个真实 fixture 目标断言可达：持真实 factory owner，提供简单 view/状态和唯一 close；故意不核 caller、不限制二次 attach。**Task1 不写 Task2 production 正文，也不从完整实现删门伪作先 RED。** 真实包/session/policy/lease/目录前提由 test 的 precheck_fixture 复用既有门观察，不能赋予 scaffold 授权；无 payload/caller/registry 接线。Task2 fresh writer 在 root 复现有效 RED 后才写完整 GREEN。

~~~python
"""Temporary RED reachability scaffold. Never authorization or production wiring."""
from contextlib import contextmanager
from pathlib import Path
from .linux_helper_object import open_linux_helper_object

class LinuxPreparedStepError(RuntimeError):
    def __init__(self):
        super().__init__('Linux prepared step is unavailable')

class LinuxPreparedStep:
    def __init__(self, sandbox, *, policy, workspace_session):
        self._owner = open_linux_helper_object(Path(sandbox.helper), Path(sandbox.manifest))
        self._owner_state, self._consume_state = 'active', 'prepared'
        self._attachment = None

    def _attach(self, *, policy, workspace_session):
        view = _LinuxStepAttachment(self)
        self._attachment, self._consume_state = view, 'attached_pending'
        return view

    def close(self):
        if self._owner_state == 'closed':
            return
        if self._owner_state != 'active':
            raise LinuxPreparedStepError()
        self._owner_state = 'unknown'
        self._owner.close()
        self._owner_state = 'closed'

class _LinuxStepAttachment:
    def __init__(self, scope):
        self._scope = scope

    def _bind_attempt(self, attempt, *, validate_attempt):
        self._scope._consume_state = 'attached_bound'

    @contextmanager
    def borrow(self, *, policy, workspace_session, attempt):
        yield self._scope._owner

def prepare_linux_step(sandbox, *, policy, workspace_session):
    return LinuxPreparedStep(sandbox, policy=policy, workspace_session=workspace_session)
~~~

- [x] **Step 5:** 四个独立目标 assertion RED，各自其它真实条件保持 valid。

~~~bash
.venv/bin/python -B -m unittest tests.test_linux_prepared_step.PreparedTests.test_wrong_session_reference_target tests.test_linux_prepared_step.PreparedTests.test_equal_policy_reference_target tests.test_linux_prepared_step.PreparedTests.test_equal_policy_attach_target tests.test_linux_prepared_step.PreparedTests.test_second_attach_active_owner_target -v
~~~

Expected: 四个目标 LinuxPreparedStepError not raised 的 assertion FAIL，0 errors/0 skip；无 missing symbol/fixture nested 早拒。root 全文读新 tests/scaffold，独立复现并冻结 SHA/原输出；Task1 writer 停止，不提交 scaffold，不授 GREEN。

### Task 2: 最小 GREEN 与完整异常/资源软件矩阵

**状态**

- [x] 任务完成

**Dependencies:** Task 1
**Parallelizable:** No（fresh SOURCE writer，统一冻结候选）

- [x] **Step 1:** 用以下完整正文替换 src/icode/linux_prepared_step.py 临时模块。

~~~python
"""Private trusted-host lifecycle, not CP/runner or isolation authorization."""
from __future__ import annotations
from contextlib import contextmanager
import os
import stat
import sys
import threading
from .isolation import LandlockSandbox
from .linux_helper_object import open_linux_helper_object
from .linux_static_helper import validate_static_linux_helper
from .linux_helper_source import observe_linux_helper_source, _source_paths
from .sandbox_policy import SandboxPolicy
from .workspace import WorkspaceSession, TicketLease, _WorkspaceObject

_ERROR = 'Linux prepared step is unavailable'

class LinuxPreparedStepError(RuntimeError):
    def __init__(self):
        super().__init__(_ERROR)

def _raise(error):
    if not isinstance(error, Exception):
        raise error
    raise LinuxPreparedStepError() from None

def _cleanup_choice(body, cleanup):
    # First signal survives; ordinary body cannot conceal unknown cleanup.
    return body if body is not None and not isinstance(body, Exception) else cleanup

def _names(session):
    return session.project_id, session.ticket_id, session.run_id

def _directory_binding(session, policy):
    if not isinstance(session, WorkspaceSession) or not isinstance(policy, SandboxPolicy):
        raise LinuxPreparedStepError()
    policy.validate()
    if (session.ticket_id != policy.ticket_id or session.run_id != policy.run_id
            or session.workspace_root != policy.workspace_root):
        raise LinuxPreparedStepError()
    lease = session.lease
    if not isinstance(lease, TicketLease) or _names(lease) != _names(session):
        raise LinuxPreparedStepError()
    lease._validate_active()
    obj = session._workspace_object
    if not isinstance(obj, _WorkspaceObject):
        raise LinuxPreparedStepError()
    fd, expected = session.workspace_fd, session.workspace_fd_identity
    if type(fd) is not int or fd < 3 or type(expected) is not tuple or len(expected) != 2:
        raise LinuxPreparedStepError()
    if any(type(value) is not int for value in expected):
        raise LinuxPreparedStepError()
    held, path = os.fstat(fd), os.lstat(session.workspace_root)
    if (not stat.S_ISDIR(held.st_mode) or not stat.S_ISDIR(path.st_mode)
            or (held.st_dev, held.st_ino) != expected
            or (path.st_dev, path.st_ino) != expected):
        raise LinuxPreparedStepError()
    return lease, obj, fd, expected

class LinuxPreparedStep:
    def __init__(self, sandbox, *, policy, workspace_session):
        owner = None
        try:
            if not sys.platform.startswith('linux') or not isinstance(sandbox, LandlockSandbox):
                raise LinuxPreparedStepError()
            lease, obj, fd, identity = _directory_binding(workspace_session, policy)
            sandbox.prepare_policy(policy)
            _, _, binary, manifest = _source_paths(sandbox)
            self._sandbox, self._policy, self._session = sandbox, policy, workspace_session
            self._lease, self._workspace_object = lease, obj
            self._workspace_fd, self._workspace_identity = fd, identity
            self._workspace_root = workspace_session.workspace_root
            self._session_names = _names(workspace_session)
            self._policy_names = (policy.ticket_id, policy.run_id, policy.step)
            self._policy_hash = policy.policy_hash
            self._sandbox_paths = (sandbox.helper, sandbox.manifest)
            self._gate = threading.RLock()
            self._attachment, self._inflight = None, False
            self._consume_state, self._owner_state = 'prepared', 'active'
            # One owning factory; resolver has no owner creation/fallback.
            owner = open_linux_helper_object(binary, manifest)
            self._owner = owner
            self._helper_fd = owner.fileno()
            held = os.fstat(self._helper_fd)
            self._helper_identity = held.st_dev, held.st_ino
            self._helper_metadata = owner.architecture, owner.sha256
            validate_static_linux_helper(owner)
            source = observe_linux_helper_source(sandbox, policy=policy, owner=owner)
            self._source_binding = (source.helper_path, source.manifest_path, source.directory_identities)
            self._check(policy=policy, workspace_session=workspace_session)
        except BaseException as body:
            selected = body
            if owner is not None:
                try:
                    owner.close()
                except BaseException as cleanup:
                    selected = _cleanup_choice(body, cleanup)
            _raise(selected)

    def _check(self, *, policy, workspace_session):
        try:
            if policy is not self._policy or workspace_session is not self._session:
                raise LinuxPreparedStepError()
            if self._owner_state != 'active':
                raise LinuxPreparedStepError()
            lease, obj, fd, identity = _directory_binding(workspace_session, policy)
            if (lease is not self._lease or obj is not self._workspace_object
                    or fd != self._workspace_fd or identity != self._workspace_identity
                    or workspace_session.workspace_root != self._workspace_root
                    or _names(workspace_session) != self._session_names
                    or (policy.ticket_id, policy.run_id, policy.step) != self._policy_names
                    or policy.policy_hash != self._policy_hash
                    or (self._sandbox.helper, self._sandbox.manifest) != self._sandbox_paths):
                raise LinuxPreparedStepError()
            helper_fd = self._owner.fileno()
            held = os.fstat(helper_fd)
            if (helper_fd != self._helper_fd
                    or (held.st_dev, held.st_ino) != self._helper_identity
                    or (self._owner.architecture, self._owner.sha256) != self._helper_metadata):
                raise LinuxPreparedStepError()
            validate_static_linux_helper(self._owner)
            try:
                source = observe_linux_helper_source(self._sandbox, policy=policy, owner=self._owner)
            except BaseException:
                # Source uses one fixed error for body/temporary cleanup unknown.
                # Conservatively block all further consumption; creator still owns helper.
                self._consume_state = 'faulted'
                raise
            if (source.helper_path, source.manifest_path, source.directory_identities) != self._source_binding:
                raise LinuxPreparedStepError()
        except BaseException as error:
            _raise(error)

    def _attach(self, *, policy, workspace_session):
        try:
            with self._gate:
                if self._consume_state != 'prepared':
                    raise LinuxPreparedStepError()
                self._check(policy=policy, workspace_session=workspace_session)
                view = object.__new__(_LinuxStepAttachment)
                view._scope, view._attempt, view._validator = self, None, None
                self._attachment, self._consume_state = view, 'attached_pending'
                return view
        except BaseException as error:
            _raise(error)

    def close(self):
        try:
            with self._gate:
                if self._inflight:
                    raise LinuxPreparedStepError()
                if self._owner_state == 'closed':
                    return
                if self._owner_state != 'active':
                    raise LinuxPreparedStepError()
                if self._consume_state != 'faulted':
                    self._consume_state = 'spent'
                self._owner_state = 'unknown'
                self._owner.close()
                self._owner_state = 'closed'
        except BaseException as error:
            _raise(error)

    def __enter__(self):
        try:
            with self._gate:
                # Cleanup convenience only; attach/borrow perform admission.
                # Do not re-observe source or retry unknown on context entry.
                if self._owner_state != 'active' or self._inflight:
                    raise LinuxPreparedStepError()
                return self
        except BaseException as error:
            _raise(error)

    def __exit__(self, kind, body, traceback):
        try:
            self.close()
        except BaseException as cleanup:
            if _cleanup_choice(body, cleanup) is cleanup:
                raise
        return False

    def __copy__(self):
        raise LinuxPreparedStepError() from None

    def __deepcopy__(self, memo):
        raise LinuxPreparedStepError() from None

    def __reduce_ex__(self, protocol):
        raise LinuxPreparedStepError() from None

class _LinuxStepAttachment:
    def __init__(self):
        raise LinuxPreparedStepError() from None

    def _current(self):
        scope = self._scope
        if scope._attachment is not self:
            raise LinuxPreparedStepError()
        return scope

    def _validate_attempt(self, attempt):
        if (type(attempt) is not str or not attempt.strip()
                or any(ord(c) < 32 or ord(c) == 127 for c in attempt)
                or not callable(self._validator) or attempt != self._attempt):
            raise LinuxPreparedStepError()
        # Trusted runner-owned CP observer in S2; callback alone grants nothing.
        if self._validator(attempt) is not None:
            raise LinuxPreparedStepError()

    def _bind_attempt(self, attempt, *, validate_attempt):
        try:
            scope = self._current()
            with scope._gate:
                if scope._consume_state != 'attached_pending' or scope._inflight:
                    raise LinuxPreparedStepError()
                scope._check(policy=scope._policy, workspace_session=scope._session)
                previous = self._attempt, self._validator
                self._attempt, self._validator = attempt, validate_attempt
                try:
                    self._validate_attempt(attempt)
                except BaseException:
                    self._attempt, self._validator = previous
                    raise
                scope._consume_state = 'attached_bound'
        except BaseException as error:
            _raise(error)

    @contextmanager
    def borrow(self, *, policy, workspace_session, attempt):
        try:
            scope = self._current()
            with scope._gate:
                if scope._consume_state != 'attached_bound' or scope._inflight:
                    raise LinuxPreparedStepError()
                scope._check(policy=policy, workspace_session=workspace_session)
                self._validate_attempt(attempt)
                scope._inflight = True
        except BaseException as error:
            _raise(error)
        try:
            yield scope._owner
        finally:
            # The body and command cleanup have ended; this sole borrower's
            # final single-field return performs no fallible lock operation.
            # No subsequent state writes can overwrite a new borrower.
            # No helper/session/lease close; do not clear sticky faulted.
            scope._inflight = False

    def _mark_faulted(self):
        try:
            scope = self._current()
            with scope._gate:
                if not scope._inflight or scope._consume_state not in ('attached_bound', 'faulted'):
                    raise LinuxPreparedStepError()
                scope._consume_state = 'faulted'
        except BaseException as error:
            _raise(error)

    def finish(self):
        try:
            scope = self._current()
            with scope._gate:
                if scope._inflight or scope._consume_state == 'prepared':
                    raise LinuxPreparedStepError()
                if scope._consume_state != 'faulted':
                    scope._consume_state = 'spent'
        except BaseException as error:
            _raise(error)

    def __copy__(self):
        raise LinuxPreparedStepError() from None

    def __deepcopy__(self, memo):
        raise LinuxPreparedStepError() from None

    def __reduce_ex__(self, protocol):
        raise LinuxPreparedStepError() from None

def prepare_linux_step(sandbox, *, policy, workspace_session):
    return LinuxPreparedStep(sandbox, policy=policy, workspace_session=workspace_session)
~~~

- [x] **Step 2:** 跑有效目标 GREEN、新完整矩阵与原相关回归。

~~~bash
.venv/bin/python -B -m unittest tests.test_linux_prepared_step.PreparedTests.test_wrong_session_reference_target tests.test_linux_prepared_step.PreparedTests.test_equal_policy_reference_target tests.test_linux_prepared_step.PreparedTests.test_equal_policy_attach_target tests.test_linux_prepared_step.PreparedTests.test_second_attach_active_owner_target -v
.venv/bin/python -B -m unittest tests.test_linux_prepared_step -v
.venv/bin/python -B -m unittest tests.test_linux_live_lease tests.test_linux_helper_object tests.test_linux_static_helper tests.test_linux_helper_source tests.test_linux_workspace_fd tests.test_workspace tests.test_sandbox_policy -v
~~~

Expected: 本机 Linux 新矩阵无 skip、目标断言全部 GREEN、原合同保持。test_linux_live_lease 名称先以 S1a 实际发布文件复核，不虚构未来结果。
- [x] **Step 3:** 受控不落盘删单门诊断，确认测试真鉴别；完整 harness 如下。它把 caller clone 映射为 scope 原引用，其余真实核验保持，四目标中 session/policy identity 应分别 assertion FAIL。

~~~bash
.venv/bin/python -B - <<'PY'
from tests._support import SRC
import unittest
from unittest.mock import patch
import icode.linux_prepared_step as subject
original = subject.LinuxPreparedStep._check
def without_reference(self, *, policy, workspace_session):
    if policy == self._policy:
        policy = self._policy
    if workspace_session == self._session:
        workspace_session = self._session
    return original(self, policy=policy, workspace_session=workspace_session)
for name in ('test_wrong_session_reference_target', 'test_equal_policy_reference_target',
             'test_equal_policy_attach_target'):
    suite = unittest.defaultTestLoader.loadTestsFromName('tests.test_linux_prepared_step.PreparedTests.' + name)
    with patch.object(subject.LinuxPreparedStep, '_check', without_reference):
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    assert result.testsRun == 1 and len(result.failures) == 1 and not result.errors and not result.skipped
    assert 'not raised' in result.failures[0][1]
PY
~~~

Expected: 每目标 unittest 输出 1 assertion FAIL，harness 仅精确诊断成立 exit0，绝非 GREEN。恢复后重新运行目标 GREEN。second attach 的鉴别已由 Task1 独立目标 RED 证明；workspace owner/lease identity 负控保持同资源/name，不能靠名字错误代拒。
- [x] **Step 4:** fresh SPEC 全文母 DESIGN/PLAN/actual SOURCE；不同 QUALITY 核 ownership、优先级、测试目标前提与调用事实债务。writer 报 SHA/diff/原输出/七维自审后停止；修复重跑关联，独立双审 C0/I0/M0 才交 root 冻结。

### Task 3: root 冻结、原完整守护、双轮文档与 main 发布

**状态**

- [ ] 任务完成

**Dependencies:** Task 2
**Parallelizable:** No（单候选冻结/精确 stage，前阶段 CI terminal 后发布）

- [x] **Step 1:** root 全文读新模块/测试，独立复现目标/矩阵；核仅四路径、零生产接线，实际输出/状态/摘要一致。
- [x] **Step 2:** SOURCE freeze 后仅一次原 complete preflight，低资源 j1（用户最高 j6）。

~~~bash
.venv/bin/python -B -m compileall -q -j1 src/icode/linux_prepared_step.py tests/test_linux_prepared_step.py
CMAKE_BUILD_PARALLEL_LEVEL=1 MAKEFLAGS=-j1 .venv/bin/python -B -u scripts/preflight.py
.venv/bin/python -B scripts/check_site.py
.venv/bin/python -B scripts/check_governance.py
git diff --check
~~~

Expected: 原完整守护逐门真实 exit0；运行前后 SOURCE SHA 相同。不得伪造隐藏全量数、跳过检查或把 skip/unknown/缺能力写 PASS。
- [x] **Step 3:** 本 PLAN 与 live 最小条目写实际 HEAD/UTC/SHA/RED/GREEN/fault/signals/独立审查/完整预检；连续两轮文档审计分别登记 scanner 原疑似数、人工排除代码 fence 假阳性数、真实遗留数，非零原扫描不可伪称零。核 vendor 固定/secret guard，不读 KEY 正文。
- [ ] **Step 4:** 上阶段所有应等 CI terminal 后，root 按既有阶段发布授权精确四路径 stage；核 index 字节与冻结工作树一致，没有第五路径或用户 dirty 修改。

~~~bash
git add src/icode/linux_prepared_step.py tests/test_linux_prepared_step.py
git add -f docs/nbl/plans/2026-10-12-linux-prepared-step-lifecycle.md docs/agent-landscape-live.md
git diff --cached --check
git diff --cached --name-only
git commit -m "feat(linux): add internal prepared step lifecycle"
git push origin main
git ls-remote --heads origin
~~~

Expected: 仅 main，远程 main 精确同实际 commit；不在 S1a CI 未 terminal 时覆盖推送造成 cancel-in-progress。新 CI 继续实际监控，不提前授 installed/整体 PASS。S1c 另 PLAN，不以本片文档启动 broker。

## 4. 验收矩阵与债务

| 目标 | 有鉴别力观察 |
| --- | --- |
| prepare/identity | 真类型/原 policy/session/lease/object；dataclass samefields newreference 其余资源与名字相同；policy validate/hash 每次重核 |
| live/FD/root | releasedlease、names漂移、bool/FD0–2/closed/reused/non-directory、session既有identity、no-follow symlink/replace；借用对象不关 |
| static/source | 实际一次 factory，无备用或legacyfallback；prepare/每borrow static与source复核同FD；helper替换/路径/来源RW拒绝 |
| attach/attempt | pending不可borrow、绑定一次、bad/空/bool/不同attempt、validator每borrow核；same names secondattach owner仍active独立目标 |
| concurrency | 同时/重入拒绝；单command退出只释放inflight；普通body/KI/SE不closehelper |
| spent/faulted | pending/bound finish→spent；旧view不可borrow/再claim；commandcleanupunknown stickyfaulted，finally不清；creator仍closehelper |
| close/exception | activeborrow禁止close；confirmedrepeatnoop；unknown一次不retry；postfactory失败close一次；ordinary固定码、首signal原对象、body不盖cleanupunknown |
| compatibility | 原DENY/singleRW/nested/protected gates完整；layered Git正控不删保护，snapshot原policy负控；copy/deepcopy/pickle拒绝，旧callers零接线 |

本片合成 ELF 未执行 payload，只授有限软件模型；真实 installed static/OS隔离/CP事件/runner不算已证。S1c 必须在唯一原 command core 接 owning/borrowing 与独立 command 资源清理、两公共入口/sameowner/held wrapper第二跳。S2须首次模型前prepare、本次CPstart、普通/补救/工程checks同attachment，各finally及Reviewer不借；S3四Linux同SHA实际build/install和prepare窗口变化负控。ready=False自动前门、LA-3网络、正式LA-2/R2十门/R3真实性债务不变。

## 5. 两阶段作者静态自审

SPEC逐项：母 §4 的 factory无override、原对象/session/lease/FD/hash/name、一次attach/attempt、排他/spent/faulted/owner分账映射 Task1/2；§5 sameFD静态与实际包来源每次复核映射Task2；§6 helper唯一owner、workspace/lease不关、unknown/signal和旧caller隔离映射Task1/2；§7前门/独立审查/原完整守护/发布及信用映射Task3。没有无caller的CP认证声称，没有删除母保护门。

QUALITY逐项：只写指定PLAN；完整module/test与最小scaffold代码，无未定义新API/占位；scaffold只开放四目标需要的可达面，私有view构造是阶段临时形式，不授最终接口/授权信用。Task1未使用Task2生产正文，四个独立assertRaises的RED必须来自目标“not raised”，不以borrow body人为fail代替；Task2 fresh writer才替换完整实现。复用真实 layered Git fixture，实际session.policy保留保护根；test独立预核既有static/source/lease/FD门只确认fixture，不授scaffold授权；无fakeowner/mockstream/dataclass成功冒充，equalclone仅负控。RLock保护排他，固定普通错误、首signal原对象、unknown先置不retry，body普通不盖cleanupunknown；无注册表/随机token/新依赖/权限，未来caller facts明确从实际ctx传入，S2真实CP信用独立。

返修静态SPEC：root指出原Task1先写完整production再放松两门违反有效RED前禁止production；现改完整最小未授权scaffold、独立fixture预核和root四目标断言，完整GREEN只在Task2。源码研究链接改实际core/src/unified_exec路径和两段行锚；root已实取，本作者不冒称重取。原source观察异常保守faulted及unknown一次close测试保留，未来attempt参数/真实CP债务不扩SOURCE。返修静态QUALITY：复读所有改段，scaffold真实owner无mockstream，无payload/registry/caller接线，测试enter只空body以确保assertRaises精确目标FAIL，阶段差异与非授权边界明确；本轮仍未执行文内代码/测试/Git写入。

【架构级自检报告】（PLAN静态自审，非运行结果）

- 语法/编译：正文和代码结构/真实符号已静态核对；未编译执行，不声明程序通过。
- 依赖/调用链：复用S0a/b和S1a发布后方法；零broker/runner/工具接线，真实CP符号及S2债务明确。
- 逻辑/边界：原引用/hash/name/live/FD/source逐次复核；attachment一次、borrow排他、spent/faulted不可恢复，待实测。
- 异常处理：普通固定码、原KI/SE、postfactory唯一close、unknown不retry和body/cleanup组合均有具体代码/测试，待实测。
- 关联模块：精确四路径；原protected/nested/runtime门保持；正控复用真实layered Git而非删snapshot保护。
- 兼容安全：无新依赖/权限/publicregistry/ready/旧kwargs改变；可信宿主边界不扩大。
- 可运行性：完整代码/验证规划已给，当前未创建SOURCE/测试/CI，不能报告100%或整体完成。

复杂且需要真实资源探索，不满足inline四条件。Task1→Task2→Task3纯依赖链，serial，每任务freshwriter，阶段freshSPEC→不同QUALITY；本DOCS ONLY writer不调用实施交接、不接管S1a、不启动子agent。

---
**Execution Mode:** serial

## Root 计划返修与独立审查记录（2026-10-12）

初稿Task1曾要求先写完整Task2 production再放松两门，root仅在PLAN阶段撤回该顺序；现为真实fixture预核＋最小未授权scaffold＋四assert notraised有效RED，之后不同fresh Task2才完整GREEN。Codex链接已改真实core/src/unified_exec路径。未执行任何计划代码，也未创建本片SOURCE。

fresh SPEC发现两个实际合同缺口：七个copy/pickle/view直接拒绝没有from None，与测试上下文要求不符；borrow finally再次取得/释放RLock可能以归还异常遮蔽body首signal。root核母合同和当前控制流，仅补七处from None，并删除finally多余锁操作：body期间本来不持锁，唯一借用者最后单字段_inflight=False后无后续写入，竞争者此前保守拒绝、此后重新检查所有门；不清faulted、不增加unknown状态或重试。不是防任意字节码信号的绝对保证。

修订资产SHA `ab6ba0aa819a291ac7220eab17586fcfd1c45692dd751b555c2e7f967ad6f321`，root全文1149行及母合同实读；fresh SPEC→不同QUALITY完整核验后均C0/I0/M0，两个I实际关闭。SOURCE仍不存在，不授运行或S1b完成。S1a已实际发布74163aa，但其ARM22.04安装probe有timeout错误种类违约、WindowsReviewer仍失败；当前Windowsfinite片先串行实施，完整守护在运行中，本片不得接管其源码或并行创建模块。SOURCE开工时须重新核实际最新发布/工作树归属与前CI终态，保留所有验收债务。

## S1b SOURCE 开始记录（2026-10-12 UTC）

前一Linux有限诊断已实际发布main `ddf8b757c2dcb7071f9cc9ca5314111f1bf76131`，root精确六路径index/工作树字节一致、commit/push成功，远端仅main同SHA且clean。其原完整preflight唯一session60796 exit0，日志 `/tmp/icode-linux-diagnostic-preflight.w0Ej2V/typescript` footer03:06:46 UTC，三门OK；原三SOURCE摘要保持。更前d05三CI全部终态由root03:00 jobs API复核，S1a741三CI也已终态。ddf新CI在独立只读观察，本片下次push前须待其全部终态，不取消或重跑。

root再次实读母DESIGN、完整Task1测试/scaffold及Task2资产；workspace仍 `c8692242d1392e6170e075d208c042e7c6b33cc65eaeaa93d7fa9d0bcc12e368`，实际 `_validate_active`复用原stream/FD/lock身份、普通固定异常及KI/SE传播；母DESIGN摘要 `121a36a8f3ed376195668d61db063f94e0061e81d4f18b17c99d41c822132ec2`未改。root sequential-thinking188–190再次核真实问题、复用与风险。只授权唯一fresh Task1创建24方法真实夹具和未授权reachability scaffold；四目标assertion RED冻结/作者停写并由root独立复现前，不写完整GREEN或生产接线。

独立研究03:10:10–03:10:16 UTC重新实际GET固定Codex27065a91 process_manager/bundled_bwrap及Apache-2.0、OpenHands SDK3934349 base/local及MIT LICENSE，实际原始行锚与取舍记录在live。采纳等待后原引用重核、held对象消费、独占owner与borrow、结果/资源终态分账；暂缓跨step/cache/密封/准入，typed view/随机token/软件validator不授真实CP或原生信用，无代码复制、新依赖/权限。研究与SOURCE独立，不预授S1b实现通过。

## S1b 有效 RED、GREEN 与 SOURCE 双审（2026-10-12 UTC）

独立Task1作者先创建24方法测试；首次缺模块1error仅为诊断。随后授权最小41行非授权scaffold（SHA `5c7f9a39c9fca2c1041b7d873a6fa2c50eb2bbf4baf95f0bfb47048faa1b6563`），作者四目标4assertion FAIL/0error/skip/exit1，0.205s；root全文读测试和scaffold后独立复现4assertion FAIL/0error/skip/exit1，0.231s。均命中not raised而非前置失败；Task1停止后不同fresh Task2才替换完整280行GREEN。

最终SOURCE SHA `f165ba45cb07152079c0bb4a3ea1bb3059b7af28a23732cd5b70f74155547075`，TEST SHA `219af2af4906422a2e4957fb52d798e3f4b2b3a13f1be0916980e96da28e38e3`，字节与批准PLAN资产一致。作者24tests/1.208s及旧七模块199均0F/E/skip；root独立新24/1.303s、旧199/11.933s均exit0/0skip。root03:29再次RAM-only三caller引用删门，各1not-raised assertion FAIL/0error/skip（0.054/0.053/0.051s），harness exit0仅说明负控鉴别；恢复后四目标4/0.199s GREEN。compileall-j1、site、governance与diff检查通过。

fresh SOURCE SPEC与不同QUALITY均C0/I0/M0，分别全文母合同/PLAN/实际SOURCE/TEST及真实依赖，并各独立新24+旧199无skip；两者均复现RAM引用删门与恢复GREEN，QUALITY另复现移除二次attach门的有效assertion FAIL。root已冻结两SOURCE，唯一原完整preflight session74699在运行，日志 `/tmp/icode-s1b-preflight.RwkAIb/typescript`；未提前记完整守护或发布通过。

两审另独立复现一个合同外边界：validator主动借同view并保留内层可产生双活跃上下文。PLAN §1明确validator为可信runner栈内只读CP观察，这种主动scope操作违反前提，故不计当前合同内缺陷；现有body重入测试不证明任意callback入口排他。S2必须实审真实validator及整个CP观察调用栈，不能包含borrow、scope修改或dispatch回调；若扩大合同必须先返设计及有效目标RED，不静默放宽安全声称。

前候选ddf三工作流已全部终态；root03:29实际jobs API重核精确SHA：CI38198600906为41success/2Reviewerfailure/3skip，Windows provenance38198600878为5/5success，Pages38198600896为2/2success，running0。root四Linux原日志与独立观察者各复核336记录，其中208fault六字段全部存在且有限值合法、None保留；四格16timeout本次均timeout/-9，旧741 ARM resource_channel_failed只未重现、不称修复。双Reviewer105/ipv4_connect_timeout、candidate78/双10035/wait_expired仍不授DENY或ready；签装不替UAC/launch。前CI等待解除，不授本S1b installed或R2/R3完成。

【架构级自检报告】（S1b SOURCE，完整守护尚在途）

- 语法/编译：compileall-j1及实际223项导入运行通过。
- 依赖/调用链：真实factory/static/source/session/lease/policy链已核；零生产调用方，不冒称产品接线。
- 逻辑/边界：原引用、一次attach、排他借用、spent/faulted及copy/pickle拒绝矩阵通过；只读validator前提和入口重入限制如上。
- 异常处理：首KI/SE原对象、普通body与cleanupunknown、creator唯一关闭、不重试及借用finally矩阵通过。
- 关联模块：旧七模块199项通过，母合同及vendor固定版本未改。
- 兼容安全：不新增权限/依赖/registry/ready，不修改旧调用参数；source/helper包来源门保留。
- 可运行性：本机限定内部软件矩阵通过；完整preflight仍在运行，不报告100%、installed、S1c/S2/S3或R2/R3完成。

## 原完整守护结果与最终文档核验（2026-10-12 UTC）

原完整preflight唯一session74699现实际exit0，root03:40:05 UTC获取完成结果，三门均OK；原日志 `/tmp/icode-s1b-preflight.RwkAIb/typescript` 保留启动/结束footer，不推算被guard隐藏的全量test数量。两个冻结SOURCE摘要未变。此时仅授限定软件子项完整守护通过，不授生产接线、installed/ready或整体R2/R3。提交前密钥与固定vendor两单门另实跑exit0；母DESIGN摘要保持。此前两次文档scanner均raw0/人工排除0/真实遗留0，随后最终内容还须连续两次原scanner核验。

【架构级自检报告】（冻结 S1b 软件候选）

- 语法/编译：compileall-j1、定向223项及原完整preflight通过。
- 依赖/调用链：真实资源依赖完整；本片零生产接线，其债务未计完成。
- 逻辑/边界：批准内部合同通过，可信只读validator前提及合同外入口重入观察保留。
- 异常处理：目标信号/unknown/唯一owner收尾矩阵与独立双审通过。
- 关联模块：原七模块199项、完整测试守护及母合同/vendor核对通过。
- 兼容安全：旧caller/后端参数未改，新依赖/权限/ready为零，secret guard通过。
- 可运行性：本机限定内部模块及完整软件守护通过；不能报告产品或跨平台100%验收。

原preflight footer精确为03:29:46 UTC开始、03:39:49 UTC结束，COMMAND_EXIT_CODE=0。最终两文档原scanner连续两轮均exit0、raw0/人工排除0/真实遗留0；记录加入后再双轮复核最终字节。当前仅四路径为本片stage目标，S1c未来PLAN不得混入。
