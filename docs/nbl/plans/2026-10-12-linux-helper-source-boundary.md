# Linux helper 来源有限观测 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development (recommended) or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 对真实 factory 已持 helper，新增实际包内来源、目录身份及执行 write roots 的有限只读观测，不重开 helper、不授执行权。

**Architecture:** 新私有模块通过真实 `native_helper.__file__` 定位固定包内 native 目录；从 `/` 逐级 no-follow 打开目录并核目录项与 held identity，两端核同一路径和 helper FD。manifest 单独打开、有限读取并绑定 owner 摘要，所有本次目录/manifest FD 逆序一次清理后才返回不可变 observation。S1 以后另行实现真实工厂与每次借用重核；本片不生产接线。

**Tech Stack:** Python >=3.11 标准库 pathlib/os/stat/re/dataclasses/unittest；既有 LandlockSandbox、SandboxPolicy、LinuxHelperObject；无新依赖、服务、权限；构建最多 -j1。

---

状态：PLAN ONLY；作者未创建源码、未运行测试、未发布。主源码基线 main `206057e`；母 [DESIGN](../specs/2026-10-12-linux-prepared-step-scope-design.md) 已独立 SPEC→不同 QUALITY 零遗留。S0a 候选生产源码 SHA256 `efc18c6902e4df803764d37a294f3ef50bac516e5ae83bab16df8052b5625c86`、测试前缀 `91c295`；S0a 最终独立 SPEC→不同 QUALITY 已通过，root 相关回归实际111项/5.722秒/0 skip；完整 preflight 会话43706仍在运行，尚未发布，不宣称完整守护或主阶段通过，也没有新提交 SHA。开始实施时 root 必须冻结已实际验收的 S0a 基线，不能照抄历史 HEAD 作为当前证据。

实施开始更新：上述为作者冻结计划时点。655行修订正文`8a5f4cd1cbf5297dca689db9496bc11ccd574e57715aaeede20e2396c9b4a0d0`经fresh SPEC→不同QUALITY C0/I0/M0，root全文读取。S0a完整preflight session43706于00:44:16 UTC实际三道exit0，六精确路径已提交/推送main `d10cd46dc7220a8cc5c87d46e0d1dd41a547f11c`；root读回远端仅main同SHA。当前S0b实施源码基线采用d10cd46，不以原206057e历史状态补授新来源信用。d10cd46新CI由独立只读观察者监测；未终态不推下一提交以免取消旧实证。

仅母 DESIGN §5 第二项 **S0b 来源前置**。不修改 old resolver/factory、S0a、workspace/lease、scope/attachment、runner/broker、ready/selector、环境构造、native C、CI、vendor 或 KEY。原两个新路径的失败候选现触发 Task2R 最小关联修复：仅 `isolation.py` 三个私有 runtime/policy 方法新增默认False严格解析路径；默认行为及旧无keyword调用形状保留。母 DESIGN §5 附最小契约补充，root记录本 PLAN、live与旧S0a PLAN关联实证，不另扩产品能力。用户 main 单分支要求覆盖技能 worktree 默认。当前 writer 仅受托写计划与指定母设计补充，覆盖技能立即实施默认；主 root 持续开发不因本文停止。

三问：实际缺口是 leaf 工厂及 resolver 未核来源祖先/可写控制；复用真实包定位、现 policy 子集/runtime roots 和 borrowed owner；新增模块当前无生产调用方，不收紧旧显式候选合同。root 已 sequential-thinking 164–166 记录需求、复用与风险，本作者完整读母设计、owner、resolver、Landlock 子集及 policy 类型。

| 新路径 | 职责 |
| --- | --- |
| `src/icode/linux_helper_source.py` | `observe_linux_helper_source(sandbox, *, policy, owner) -> LinuxHelperSourceObservation`；仅本次来源观测，无 expected path/hash 或执行授权参数 |
| `tests/test_linux_helper_source.py` | 实际临时目录、真实旧 factory owner、合法单根策略、目标断言负控与逐 OS 故障矩阵 |
| `src/icode/isolation.py`（仅Task2R三私有方法） | 严格runtime解析opt-in，不变更默认解析、策略门或ready |
| 本 PLAN | 精确任务及实证日志；作者不替 root 的审查/守护/提交 |

## 边界决策

- 包路径来自模块文件规范父目录，再固定 `native/icode-landlock` 与 `.sha256`；不调用 resolver 重开 helper。显式 sandbox 两路径 resolve 后须相等，可接受合法词法 alias；canonical native 链 no-follow。路径规范化不是 typed 来源认证。
- write root 若是源目录的祖先/相等，能控制目录或 dirname entry，拒绝；write root 若在 native 子树，亦拒绝。公共 `/`、`/home`、用户目录祖先不因「包含 workspace」而一律拒绝。正常外置 pip/pipx 用户可写前缀允许，因为原威胁模型不防已控制同 UID 宿主；项目执行 write 权才是本门对象。runtime 只读规则不会撤销 workspace 的既有 write 权。
- 要求 native 实际位于现 runtime roots 下，复用原子集门及真实映射；新source专用严格opt-in调用为 `_checked_policy_workspace(policy, strict_runtime=True)` 与两处 `_runtime_read_roots(strict=True)`，默认旧入口仍完全不传keyword。不新增 read root。安装在执行 workspace 的 venv 即使也是 sys.prefix，仍拒绝。pipx launcher/解释器 alias 不在本函数输入中，不新设全局 symlink 禁令。
- helper 只取公开 fileno/fstat，目录相对 stat 必须与同 held helper dev/ino 及完整五字段快照一致。prepare 后 rename/unlink/replace 或祖先替换允许固定拒绝，不为正控重开 decoy。文件摘要/静态字节由 S0a 单独核验，不虚称本片内容封印。
- factory 已关闭自己的 manifest，故本片不能证明再次读的是 factory manifest 同对象。本片选择**新的独立 manifest 观测**：固定 canonical 位置，no-follow 单次打开，正则至多65字节正文（67字节 pread 观察过长），两端 fstat/目录项身份/时间大小一致，文本摘要等于 owner.sha256。返回的是本次 manifest 身份与内容绑定；manifest ABA/持续宿主变更不保证。将来 S1 prepare 在真实 factory + S0a + 此观测后才形成准备绑定。
- 路径按 `os.fsencode` 文件系统编码总预算4096字节、目录层级128；不是平台最长路径承诺，超出固定拒绝。目录每次打开 O_DIRECTORY/O_NOFOLLOW/O_CLOEXEC；manifest O_NONBLOCK 防 special-file 阻塞，regular/nlink1。借用 helper 不移动 offset、不关闭。未知 close 不返回 observation、不重试；首 KI/SE 保留原对象，其他独立 FD 尽力收尾。
- observation 的 frozen dataclass 只是有限证据容器，构造、相等或历史缓存都不是权限。无 previous/expected 参数；未来 S1 的重复实际观测及消费约束另计划，不能只比 caller 传入对象。

### Task 1: 完整 fixture 与目标 assertion RED

**状态**
- [x] 任务完成（仅有效RED与完整测试，未发布scaffold）

**Dependencies:** None
**Parallelizable:** No (先冻结 S0a，再实际断言 RED)

- [x] **Step 1: 冻结基线与全文读取**

```bash
git rev-parse --abbrev-ref HEAD
git rev-parse HEAD
git status --short
git diff -- src/icode/native_helper.py src/icode/linux_helper_object.py src/icode/isolation.py src/icode/sandbox_policy.py
```

预期 main、root 刚验收的 S0a SHA；两个新目标路径不得有他人内容。完整读 AGENTS、母 DESIGN、本 PLAN、上述四模块及 S0a 源码/测试和 tests/_support.py；不读 KEY。若实际母合同变化，交 root 修订而非覆盖用户文件。

- [x] **Step 2: apply_patch 新建完整测试文件**

文件 `tests/test_linux_helper_source.py` 全文：

```python
"""Source observations on real owners; fixtures are not installed-package proof."""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from tests._support import temp_workspace
from tests.test_linux_static_helper import image
import icode.native_helper as locator
import icode.linux_helper_object as factory
import icode.linux_helper_source as subject
from icode.isolation import LandlockSandbox
from icode.sandbox_policy import SandboxPolicy, NetworkMode

REAL = {name: getattr(os, name, None) for name in ('open', 'close', 'fstat', 'stat', 'pread')}

def policy(root):
    return SandboxPolicy(1, 'run-source', 'ticket-source', 'code', root,
        (root,), (root,), (), (), NetworkMode.DENY, (), 16, 30, 4096, ())

@unittest.skipUnless(sys.platform.startswith('linux') and REAL['pread'], 'Linux source fixture; no installed credit')
class SourceTests(unittest.TestCase):
    def setUp(self):
        self.directory = temp_workspace()
        self.root = self.directory.__enter__()
        self.addCleanup(self.directory.__exit__, None, None, None)
        self.prefix = self.root / 'user-pipx' / 'venvs' / 'icode-agent'
        self.package = self.prefix / 'lib' / 'python3.11' / 'site-packages' / 'icode'
        self.native = self.package / 'native'
        self.native.mkdir(parents=True)
        self.module = self.package / 'native_helper.py'
        self.module.write_text('# source fixture\n')
        self.binary = self.native / 'icode-landlock'
        self.manifest = self.native / 'icode-landlock.sha256'
        self.binary.write_bytes(image())
        self.binary.chmod(0o700)
        self.digest = hashlib.sha256(self.binary.read_bytes()).hexdigest()
        self.manifest.write_text(self.digest + '\n', encoding='ascii')
        self.workspace = self.root / 'project'
        self.workspace.mkdir()
        self.policy = policy(self.workspace)
        self.sandbox = LandlockSandbox(str(self.binary), manifest=str(self.manifest))
        for target, name, value in ((locator, '__file__', str(self.module)),
                (sys, 'prefix', str(self.prefix)), (sys, 'base_prefix', '/usr')):
            mock = patch.object(target, name, value)
            mock.start()
            self.addCleanup(mock.stop)
        machine = patch.object(factory.platform, 'machine', return_value='x86_64')
        machine.start()
        self.addCleanup(machine.stop)
        self.owner = factory.open_linux_helper_object(self.binary, self.manifest)
        self.addCleanup(self.owner.close)
        self.fd = self.owner.fileno()

    def observe(self):
        return subject.observe_linux_helper_source(self.sandbox, policy=self.policy, owner=self.owner)

    def reject(self):
        with self.assertRaises(factory.LinuxHelperObjectError) as caught:
            self.observe()
        self.assertEqual(str(caught.exception), 'Linux helper object is unavailable')
        self.assertTrue(caught.exception.__suppress_context__)
        self.assertEqual(self.owner.fileno(), self.fd)

    def test_workspace_install_is_target_rejection(self):
        # Other premises valid: same real package, owner, source and runtime prefix.
        self.policy = policy(self.prefix)
        self.reject()

    def test_external_user_writable_prefix_and_public_ancestors_pass(self):
        os.lseek(self.fd, 7, os.SEEK_SET)
        opened, closed = [], []
        def opening(path, flags, **kw):
            result = REAL['open'](path, flags, **kw)
            opened.append((path, flags, result))
            return result
        def closing(fd):
            closed.append(fd)
            return REAL['close'](fd)
        with patch.object(subject.os, 'open', side_effect=opening), patch.object(subject.os, 'close', side_effect=closing):
            result = self.observe()
        self.assertEqual(result.helper_path, self.binary)
        self.assertEqual(result.helper_snapshot[:2], (REAL['fstat'](self.fd).st_dev, REAL['fstat'](self.fd).st_ino))
        self.assertEqual(result.manifest_digest, self.digest)
        self.assertEqual(closed, [entry[2] for entry in reversed(opened)])
        self.assertNotIn(self.fd, closed)
        self.assertFalse(any(path == self.binary or path == self.binary.name for path, _, _ in opened))
        self.assertEqual(os.lseek(self.fd, 0, os.SEEK_CUR), 7)
        self.assertEqual(self.owner.fileno(), self.fd)

    def test_native_root_and_native_child_write_reject(self):
        child = self.native / 'project'
        child.mkdir()
        for workspace in (self.native, child):
            with self.subTest(workspace=workspace):
                self.policy = policy(workspace)
                self.reject()

    def test_alias_real_target_and_exact_package_match(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.native, target_is_directory=True)
        self.sandbox = LandlockSandbox(str(alias / self.binary.name), manifest=str(alias / self.manifest.name))
        self.assertEqual(self.observe().helper_path, self.binary)
        self.policy = policy(self.prefix)
        self.reject()
        self.policy = policy(self.workspace)
        other = self.root / 'other'
        other.mkdir()
        replacement = other / self.binary.name
        replacement.write_bytes(image())
        self.sandbox = LandlockSandbox(str(replacement), manifest=str(self.manifest))
        self.reject()

    def test_helper_unlink_replace_and_wrong_held_identity(self):
        old = self.binary.with_name('old-helper')
        self.binary.rename(old)
        self.reject()
        self.binary.write_bytes(image())
        self.binary.chmod(0o700)
        self.reject()
        self.assertEqual(self.owner.fileno(), self.fd)

    def test_ancestor_replacement_and_canonical_native_symlink_reject(self):
        actual_stat = REAL['stat']
        injected = False
        old = self.native.with_name('old-native')
        def changed(path, *args, **kw):
            nonlocal injected
            result = actual_stat(path, *args, **kw)
            if path == self.binary.name and kw.get('dir_fd') is not None and not injected:
                injected = True
                self.native.rename(old)
                self.native.mkdir()
                # Complete decoy keeps later path/manifest premises valid;
                # rejection must distinguish the original held directory.
                self.binary.write_bytes(image())
                self.binary.chmod(0o700)
                self.manifest.write_text(self.digest + '\n', encoding='ascii')
            return result
        with patch.object(subject.os, 'stat', side_effect=changed):
            self.reject()
        self.assertTrue(injected)
        self.binary.unlink()
        self.manifest.unlink()
        self.native.rmdir()
        self.native.symlink_to(old, target_is_directory=True)
        self.reject()

    def test_manifest_is_new_bound_observation_not_factory_identity(self):
        old = self.manifest.with_name('old-manifest')
        self.manifest.rename(old)
        self.manifest.write_text(self.digest + '\n')
        self.assertEqual(self.observe().manifest_digest, self.digest)
        for contents in ('0' * 64 + '\n', self.digest + '\nextra', self.digest.upper() + '\n'):
            with self.subTest(contents=contents[:1]):
                self.manifest.write_text(contents)
                self.reject()
        self.manifest.unlink()
        self.manifest.symlink_to(old)
        self.reject()

    def test_alias_drift_after_first_resolution_rejects(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.native, target_is_directory=True)
        other = self.root / 'decoy'
        other.mkdir()
        (other / self.binary.name).write_bytes(image())
        (other / self.manifest.name).write_text(self.digest + '\n')
        self.sandbox = LandlockSandbox(str(alias / self.binary.name), manifest=str(alias / self.manifest.name))
        original = REAL['pread']
        def changed(fd, length, offset):
            result = original(fd, length, offset)
            alias.unlink()
            alias.symlink_to(other, target_is_directory=True)
            return result
        with patch.object(subject.os, 'pread', side_effect=changed):
            self.reject()

    def test_finite_budgets_and_runtime_mapping(self):
        with patch.object(subject, '_PATH_BYTES', 1):
            self.reject()
        with patch.object(subject, '_DIRECTORY_LIMIT', 1):
            self.reject()
        with patch.object(sys, 'prefix', '/usr'):
            self.reject()

    def test_every_actual_os_position_fault_and_once_cleanup(self):
        # Discover calls on real successful fixture; then recreate for each target.
        counts = dict.fromkeys(REAL, 0)
        def counted(name):
            def call(*args, **kw):
                counts[name] += 1
                return REAL[name](*args, **kw)
            return call
        from contextlib import ExitStack
        with ExitStack() as stack:
            for name in REAL:
                stack.enter_context(patch.object(subject.os, name, side_effect=counted(name)))
            self.observe()
        for name, total in counts.items():
            for position in range(1, total + 1):
                for error_type in (OSError, KeyboardInterrupt, SystemExit):
                    with self.subTest(name=name, position=position, error_type=error_type):
                        error = error_type('private detail')
                        calls = 0
                        opened, closed = [], []
                        def opening(*args, **kw):
                            nonlocal calls
                            if name == 'open':
                                calls += 1
                                if calls == position:
                                    raise error
                            fd = REAL['open'](*args, **kw)
                            opened.append(fd)
                            return fd
                        def closing(fd):
                            nonlocal calls
                            closed.append(fd)
                            # Fault after actual close: unknown must not be retried.
                            REAL['close'](fd)
                            if name == 'close':
                                calls += 1
                                if calls == position:
                                    raise error
                        def target(*args, **kw):
                            nonlocal calls
                            calls += 1
                            if calls == position:
                                raise error
                            return REAL[name](*args, **kw)
                        with ExitStack() as stack:
                            stack.enter_context(patch.object(subject.os, 'open', side_effect=opening))
                            stack.enter_context(patch.object(subject.os, 'close', side_effect=closing))
                            if name not in ('open', 'close'):
                                stack.enter_context(patch.object(subject.os, name, side_effect=target))
                            with self.assertRaises(BaseException) as caught:
                                self.observe()
                        self.assertGreaterEqual(calls, position)
                        if error_type is OSError:
                            self.assertIsInstance(caught.exception, factory.LinuxHelperObjectError)
                        else:
                            self.assertIs(caught.exception, error)
                        self.assertEqual(closed, list(reversed(opened)))
                        self.assertNotIn(self.fd, closed)
                        self.assertEqual(self.owner.fileno(), self.fd)

    def test_first_signal_survives_later_cleanup_signal(self):
        first, following = KeyboardInterrupt('first'), SystemExit('later')
        opened, closed = [], []
        def opening(*args, **kw):
            fd = REAL['open'](*args, **kw)
            opened.append(fd)
            return fd
        def closing(fd):
            closed.append(fd)
            REAL['close'](fd)
            raise following
        with patch.object(subject.os, 'open', side_effect=opening), patch.object(subject.os, 'pread', side_effect=first), patch.object(subject.os, 'close', side_effect=closing):
            with self.assertRaises(KeyboardInterrupt) as caught:
                self.observe()
        self.assertIs(caught.exception, first)
        self.assertEqual(closed, list(reversed(opened)))
        self.assertEqual(self.owner.fileno(), self.fd)
```

- [x] **Step 3: 缺模块只能记 collection error；补最小未发布 scaffold**

先运行：`.venv/bin/python -B -m unittest tests.test_linux_helper_source.SourceTests.test_workspace_install_is_target_rejection -v`。ImportError 不算 RED。若新模块确实尚不存在，用 apply_patch 添加以下完整临时 scaffold（仅本片，不提交）：

```python
"""Unpublished source-boundary TDD scaffold, never an execution grant."""
def observe_linux_helper_source(sandbox, *, policy, owner):
    owner.fileno()
    return None
```

- [x] **Step 4: 实际 assertion RED，记录 root 独立复现**

运行同一 target 命令。预期1方法、1 FAIL「LinuxHelperObjectError not raised」、0 ERROR/skip；真实 factory、包匹配及 runtime 前提仍有效，不能通过坏 owner/其它门造 RED。record 实际命令、scaffold SHA、fixture SHA、计数和退出码。Task1 不提交 scaffold；root 在同一 main 冻结后复现再交 Task2 fresh implementer。

### Task 2: 同目录 FD 来源观测 GREEN

**状态**
- [x] 任务完成（Task2R后root独立完整关联GREEN；原失败历史保留，发布仍待Task3）

**Dependencies:** Task 1
**Parallelizable:** No (必须保持已复现 RED，单 SOURCE writer)

- [x] **Step 1: 新 implementer 重跑实际 target RED**

运行 Task1 Step4 命令，预期相同目标断言；不是重复全仓测试。完整读取本计划与上下文，不能留下临时 scaffold。

- [x] **Step 2: apply_patch 用以下完整模块替换 scaffold**

文件 `src/icode/linux_helper_source.py` 全文：

以下保留原Task2候选的完整代码以便核对失败基线；**不是修复后的最终代码**，Task2R三调用点补丁必须成对应用，不能跳过Task2R把此旧候选发布为成功。

```python
"""Finite package-source observation; not authentication or execution authority."""
from __future__ import annotations
from dataclasses import dataclass
import os
from pathlib import Path
import re
import stat
import sys
from . import native_helper
from .isolation import LandlockSandbox
from .sandbox_policy import SandboxPolicy
from .linux_helper_object import (
    LinuxHelperObject, LinuxHelperObjectError, _select, _raise_fixed_or_signal,
)

_PATH_BYTES = 4096
_DIRECTORY_LIMIT = 128
_MANIFEST_READ = 67
_DIGEST_LINE = re.compile(rb'[0-9a-f]{64}\n?\Z')

@dataclass(frozen=True)
class LinuxHelperSourceObservation:
    helper_path: Path
    manifest_path: Path
    directory_identities: tuple[tuple[Path, int, int], ...]
    helper_snapshot: tuple[int, int, int, int, int]
    manifest_snapshot: tuple[int, int, int, int, int]
    manifest_digest: str

def _identity(value):
    return value.st_dev, value.st_ino

def _snapshot(value):
    return (*_identity(value), value.st_size, value.st_mtime_ns, value.st_ctime_ns)

def _regular(value):
    if not stat.S_ISREG(value.st_mode) or value.st_nlink != 1:
        raise LinuxHelperObjectError()

def _bounded(path):
    if not path.is_absolute() or len(os.fsencode(path)) > _PATH_BYTES:
        raise LinuxHelperObjectError()

def _source_paths(sandbox):
    module = Path(native_helper.__file__).resolve(strict=True)
    native = module.parent / 'native'
    binary = native / 'icode-landlock'
    manifest = native / 'icode-landlock.sha256'
    for path in (module, native, binary, manifest):
        _bounded(path)
    if (sandbox.manifest is None
            or Path(sandbox.helper).resolve(strict=True) != binary
            or Path(sandbox.manifest).resolve(strict=True) != manifest):
        raise LinuxHelperObjectError()
    return module, native, binary, manifest

def _write_boundary(native, policy):
    # Ancestors are not bidirectional conflicts: a sibling workspace cannot
    # control source entries in the shared /home/user or /tmp ancestor.
    for root in policy.write_roots:
        resolved = root.resolve(strict=True)
        if native.is_relative_to(resolved) or resolved.is_relative_to(native):
            raise LinuxHelperObjectError()

def observe_linux_helper_source(sandbox: LandlockSandbox, *,
        policy: SandboxPolicy, owner: LinuxHelperObject) -> LinuxHelperSourceObservation:
    """Borrow helper; own only temporary directories and one fresh manifest FD."""
    owned = []
    selected = None
    result = None
    try:
        if (not sys.platform.startswith('linux') or not callable(getattr(os, 'pread', None))
                or not isinstance(sandbox, LandlockSandbox)
                or not isinstance(policy, SandboxPolicy)
                or not isinstance(owner, LinuxHelperObject)):
            raise LinuxHelperObjectError()
        directory_flags = os.O_RDONLY
        for name in ('O_CLOEXEC', 'O_NOFOLLOW', 'O_DIRECTORY'):
            flag = getattr(os, name, None)
            if type(flag) is not int or flag <= 0:
                raise LinuxHelperObjectError()
            directory_flags |= flag
        nonblock = getattr(os, 'O_NONBLOCK', None)
        if type(nonblock) is not int or nonblock <= 0:
            raise LinuxHelperObjectError()
        file_flags = (directory_flags & ~os.O_DIRECTORY) | nonblock
        # Preserve the actual existing DENY/single-root/runtime conflict checks.
        sandbox._checked_policy_workspace(policy)
        initial_paths = _source_paths(sandbox)
        module, native, binary, manifest = initial_paths
        _write_boundary(native, policy)
        runtime = sandbox._runtime_read_roots()
        if not any(native.is_relative_to(root) for root in runtime):
            raise LinuxHelperObjectError()
        parts = native.parts[1:]
        if len(parts) + 1 > _DIRECTORY_LIMIT:
            raise LinuxHelperObjectError()
        helper_fd = owner.fileno()
        helper_before = os.fstat(helper_fd)
        _regular(helper_before)
        root_fd = os.open('/', directory_flags)
        owned.append(root_fd)
        root_status = os.fstat(root_fd)
        if not stat.S_ISDIR(root_status.st_mode):
            raise LinuxHelperObjectError()
        # Keep each parent and child handle so later ancestor replacement is
        # checked via its original parent entry, not by a fresh trusted pathname.
        nodes = [(Path('/'), root_fd, _identity(root_status))]
        links = []
        parent_fd, parent_path = root_fd, Path('/')
        for part in parts:
            entry = os.stat(part, dir_fd=parent_fd, follow_symlinks=False)
            if not stat.S_ISDIR(entry.st_mode):
                raise LinuxHelperObjectError()
            child_fd = os.open(part, directory_flags, dir_fd=parent_fd)
            owned.append(child_fd)
            held = os.fstat(child_fd)
            if not stat.S_ISDIR(held.st_mode) or _identity(entry) != _identity(held):
                raise LinuxHelperObjectError()
            child_path = parent_path / part
            nodes.append((child_path, child_fd, _identity(held)))
            links.append((parent_fd, part, child_fd, _identity(held)))
            parent_fd, parent_path = child_fd, child_path
        helper_entry = os.stat(binary.name, dir_fd=parent_fd, follow_symlinks=False)
        _regular(helper_entry)
        if _snapshot(helper_entry) != _snapshot(helper_before):
            raise LinuxHelperObjectError()
        manifest_entry = os.stat(manifest.name, dir_fd=parent_fd, follow_symlinks=False)
        _regular(manifest_entry)
        manifest_fd = os.open(manifest.name, file_flags, dir_fd=parent_fd)
        owned.append(manifest_fd)
        manifest_before = os.fstat(manifest_fd)
        _regular(manifest_before)
        if _snapshot(manifest_entry) != _snapshot(manifest_before):
            raise LinuxHelperObjectError()
        if not 64 <= manifest_before.st_size <= 65:
            raise LinuxHelperObjectError()
        contents = os.pread(manifest_fd, _MANIFEST_READ, 0)
        if (type(contents) is not bytes or len(contents) != manifest_before.st_size
                or _DIGEST_LINE.fullmatch(contents) is None
                or contents.rstrip(b'\n').decode('ascii') != owner.sha256):
            raise LinuxHelperObjectError()
        manifest_after = os.fstat(manifest_fd)
        _regular(manifest_after)
        manifest_final_entry = os.stat(manifest.name, dir_fd=parent_fd, follow_symlinks=False)
        _regular(manifest_final_entry)
        if (_snapshot(manifest_before) != _snapshot(manifest_after)
                or _snapshot(manifest_after) != _snapshot(manifest_final_entry)):
            raise LinuxHelperObjectError()
        helper_final_entry = os.stat(binary.name, dir_fd=parent_fd, follow_symlinks=False)
        _regular(helper_final_entry)
        if owner.fileno() != helper_fd:
            raise LinuxHelperObjectError()
        helper_after = os.fstat(helper_fd)
        _regular(helper_after)
        if (_snapshot(helper_before) != _snapshot(helper_after)
                or _snapshot(helper_after) != _snapshot(helper_final_entry)):
            raise LinuxHelperObjectError()
        root_entry = os.stat('/', follow_symlinks=False)
        if not stat.S_ISDIR(root_entry.st_mode) or _identity(root_entry) != nodes[0][2]:
            raise LinuxHelperObjectError()
        for parent, name, child, expected in links:
            entry = os.stat(name, dir_fd=parent, follow_symlinks=False)
            held = os.fstat(child)
            if (not stat.S_ISDIR(entry.st_mode) or not stat.S_ISDIR(held.st_mode)
                    or _identity(entry) != expected or _identity(held) != expected):
                raise LinuxHelperObjectError()
        if initial_paths != _source_paths(sandbox):
            raise LinuxHelperObjectError()
        _write_boundary(native, policy)
        if runtime != sandbox._runtime_read_roots():
            raise LinuxHelperObjectError()
        result = LinuxHelperSourceObservation(binary, manifest,
            tuple((path, *identity) for path, _, identity in nodes),
            _snapshot(helper_after), _snapshot(manifest_after), owner.sha256)
    except BaseException as error:
        selected = error
    finally:
        while owned:
            fd = owned.pop()
            try:
                os.close(fd)
            except BaseException as error:
                selected = _select(selected, error)
    if selected is not None:
        _raise_fixed_or_signal(selected)
    return result
```

- [x] **Step 3: 先目标 GREEN，再全新增/旧合同回归**

```bash
.venv/bin/python -B -m unittest tests.test_linux_helper_source.SourceTests.test_workspace_install_is_target_rejection -v
.venv/bin/python -B -m unittest tests.test_linux_helper_source -v
.venv/bin/python -B -m unittest tests.test_linux_static_helper tests.test_linux_helper_object tests.test_linux_helper_elf tests.test_native_helper tests.test_linux_helper_dispatch tests.test_linux_helper_task_quota -q
```

预期目标1 PASS；新测试全方法、所有实际 fault subtests 0 ERROR/skip；旧相关回归0失败，实际数量与耗时运行后记录，不先造数字。fixture 不运行 helper，不授 installed/原生/kernel 权限。

- [x] **Step 4: root 独立目标复现并检查调用链未动**

root 重跑 target 与新增模块；原Task2阶段old path diff空、仅新module/test consumer，无生产接线。当前已实际复现全套9个OSError subtest失败，不能以target GREEN替代全GREEN；冻结失败两文件SHA，转Task2R诊断前置。Task2R完成后才可标Task2整体GREEN并交双审；不自行提交/推送，避免 root 守护未完成。

### Task 2R: 严格 runtime 解析最小兼容修复

**状态**
- [x] 任务完成（有效RED→GREEN、root独立125项与531故障通过；双审/完整守护另属Task3）

**Dependencies:** Task 1；Task 2 当前失败候选已冻结且root独立诊断前置完成（不依赖Task2全GREEN，避免依赖死锁）
**Parallelizable:** No (先fresh SPEC→不同QUALITY审核本文与母补充，后单SOURCE writer；修复后才解除Task2阻塞)

root三问与sequential-thinking167–169已记录：是真实9负控失败；原策略门可复用，只补私有strict入口；调用链默认shape必须完整保留。不能复制policy gate、全局猴补Path、删除负控或将OSError改成允许结果。

- [x] **Step 1: 完整读冻结失败候选、实际stdlib与返修双审记录**

使用上述现存source/test，不覆盖他人修改。失败生产模块SHA256 `c4d965a3fc46381e1e16e2e4586c9ce26d085e871086cff1b3d4295c54f6e7f3`、测试SHA256 `227756bdb27f4a5d3bb09af14efe81a18105f8eb015154602c8713256c6416f4`；读取现 `isolation.py` 三方法及root实际inspect的 `/home/orbbec/.local/share/uv/python/cpython-3.11.15-linux-x86_64-gnu/lib/python3.11/pathlib.py` 对应 `Path.resolve`。这是本机Python辅助解析，不是设备故障或helper原生隔离实证。先完成母补充/本PLAN双审，不因补代码容易跳过关卡。

- [x] **Step 2: apply_patch先增加3个完整测试方法与lstat矩阵项**

以下是对Task1完整测试的精确补丁；保留原11方法与9失败的原预期。新的strict spy调用现有observe，不直接给不存在的方法传strict keyword，确保旧候选是实际assertion FAIL而非TypeError/ImportError。`Path.resolve` wrapper调用真实原方法，所有文件、策略、owner仍有效。

```diff
--- a/tests/test_linux_helper_source.py
+++ b/tests/test_linux_helper_source.py
@@
-REAL = {name: getattr(os, name, None) for name in ('open', 'close', 'fstat', 'stat', 'pread')}
+REAL = {name: getattr(os, name, None) for name in ('open', 'close', 'fstat', 'stat', 'lstat', 'pread')}
```

在上述现有方法之前插入以下3方法，缩进位于现 `SourceTests`；不要改原故障矩阵逻辑：

```python
    def test_runtime_resolutions_are_strict_in_source_observation(self):
        original = Path.resolve
        observed = []
        tracked = {Path.home(), Path(sys.prefix), Path(sys.base_prefix)}
        def resolving(path, *args, **kwargs):
            if path in tracked:
                observed.append((path, kwargs.get('strict')))
            return original(path, *args, **kwargs)
        with patch.object(Path, 'resolve', new=resolving):
            self.assertIsNotNone(self.observe())
        self.assertTrue(observed)
        self.assertEqual({path for path, _ in observed}, tracked)
        self.assertTrue(all(strict is True for _, strict in observed), observed)

    def test_default_checked_policy_keeps_zero_keyword_runtime_callback(self):
        roots = (self.prefix, Path('/usr'))
        with patch.object(self.sandbox, '_runtime_read_roots', side_effect=lambda: roots) as callback:
            self.assertEqual(self.sandbox._checked_policy_workspace(self.policy), self.workspace)
        callback.assert_called_once_with()

    def test_default_runtime_keeps_prefix_only_validation_callback(self):
        roots = (self.prefix, Path('/usr'))
        with patch.object(self.sandbox, '_validated_runtime_roots', side_effect=lambda prefixes: roots) as callback:
            self.assertEqual(self.sandbox._runtime_read_roots(), roots)
        callback.assert_called_once_with((Path(sys.prefix), Path(sys.base_prefix)))
```

`REAL['lstat']`在本Linux实际平台可用，增加后原动态矩阵自动逐真实lstat位置注入OSError/KI/SE，继承所有独立资源逆序一次close、unknown不返回和首信号原对象断言；其它平台整个class继续原skip合同，不新增Linux信用。没有新增runtime遍历总预算或多用户安全承诺，sourcecanonical预算保持原有限合同。

- [x] **Step 3: fresh implementer与root独立复现有效strict assertion RED**

```bash
.venv/bin/python -B -m unittest tests.test_linux_helper_source.SourceTests.test_runtime_resolutions_are_strict_in_source_observation -v
```

在未修production候选上预期1方法/1 assertion FAIL，0 ERROR/skip；observe真实成功返回，但所记录home/prefix/base_prefix resolve没有strict=True，最后断言失败。记录实际源码/测试SHA、命令和耗时；同时原9失败仍应保存为历史证据，不能先删或预期允许。此步骤不应直接调用不存在的strict API。

- [x] **Step 4: apply_patch成对修改isolation三方法与source三个调用点**

`src/icode/isolation.py` 仅用以下完整3方法替换原同名方法；其余方法、import、policy gate、异常正文和默认caller不动：

```python
    @staticmethod
    def _validated_runtime_roots(
        prefixes: Sequence[Path], *, strict: bool = False,
    ) -> tuple[Path, ...]:
        """仅授权 Python 安装前缀；source观察可显式要求严格解析。"""
        if strict:
            home = Path.home().resolve(strict=True)
            roots = tuple(sorted({path.resolve(strict=True) for path in prefixes}, key=str))
        else:
            # Preserve legacy Path.resolve invocation shape and behavior.
            home = Path.home().resolve()
            roots = tuple(sorted({path.resolve() for path in prefixes}, key=str))
        broad = {Path("/"), Path("/tmp"), Path("/var"), Path("/home")}
        for root in roots:
            if (
                root in broad or home.is_relative_to(root)
                or not root.is_dir()
            ):
                raise RuntimeError("Python 运行时前缀过宽或不可用")
        return roots

    def _runtime_read_roots(self, *, strict: bool = False) -> tuple[Path, ...]:
        prefixes = (Path(sys.prefix), Path(sys.base_prefix))
        if strict:
            return self._validated_runtime_roots(prefixes, strict=True)
        return self._validated_runtime_roots(prefixes)

    def _checked_policy_workspace(
        self, policy: SandboxPolicy, *, strict_runtime: bool = False,
    ) -> Path:
        """仅核对当前助手能表达的文件/网络子集；不是完整策略绑定。"""
        workspace = policy.workspace_root

        def intersects(left: Path, right: Path) -> bool:
            return left.is_relative_to(right) or right.is_relative_to(left)

        if policy.network_mode is not NetworkMode.DENY or policy.allowed_domains:
            raise ValueError("Landlock helper 尚不支持网络临时授权")
        if policy.read_roots != (workspace,) or policy.write_roots != (workspace,):
            raise ValueError("Landlock helper 仅支持单一代码读写根")
        if any(
            intersects(path, workspace)
            for path in (*policy.deny_read_roots, *policy.deny_write_roots)
        ):
            raise ValueError("Landlock 无法从可写根中排除受保护子路径")

        # 助手有 Python/动态链接器所需的固定系统只读白名单，以及 /dev/null
        # 这一写入例外。拒绝规则若与这些路径重叠，不能宣称已完整执行策略。
        runtime_read = (
            "/usr", "/bin", "/lib", "/lib64", "/sbin",
            "/etc/ld.so.cache", "/etc/passwd", "/etc/nsswitch.conf",
            "/dev/urandom", "/dev/null",
        )
        if strict_runtime:
            runtime_roots = self._runtime_read_roots(strict=True)
        else:
            runtime_roots = self._runtime_read_roots()
        runtime_paths = tuple(map(Path, runtime_read)) + runtime_roots
        if any(
            intersects(denied, allowed)
            for denied in policy.deny_read_roots
            for allowed in runtime_paths
        ):
            raise ValueError("Landlock 系统运行时读取白名单与拒读路径冲突")
        if any(
            intersects(denied, Path("/dev/null"))
            for denied in policy.deny_write_roots
        ):
            raise ValueError("Landlock /dev/null 写入例外与拒写路径冲突")
        return workspace
```

`src/icode/linux_helper_source.py` 对Task2完整模块只改以下三调用点，无fallback、无复制门、无catch TypeError重试：

```diff
--- a/src/icode/linux_helper_source.py
+++ b/src/icode/linux_helper_source.py
@@
-        sandbox._checked_policy_workspace(policy)
+        sandbox._checked_policy_workspace(policy, strict_runtime=True)
@@
-        runtime = sandbox._runtime_read_roots()
+        runtime = sandbox._runtime_read_roots(strict=True)
@@
-        if runtime != sandbox._runtime_read_roots():
+        if runtime != sandbox._runtime_read_roots(strict=True):
```

strict path中的真实解析OSError向外传播到既有source固定错误包装；KI/SE仍原对象。只增加显式私有模式，不开启ready/selector、不改变旧namespace callbacks、不加权限/安装步骤，不用非严格解析回退为成功。

- [x] **Step 5: strict GREEN、14方法完整矩阵与兼容回归，再解除Task2阻塞**

```bash
.venv/bin/python -B -m unittest tests.test_linux_helper_source.SourceTests.test_runtime_resolutions_are_strict_in_source_observation -v
.venv/bin/python -B -m unittest tests.test_linux_helper_source -v
.venv/bin/python -B -m unittest tests.test_linux_static_helper tests.test_linux_helper_object tests.test_linux_helper_elf tests.test_native_helper tests.test_linux_helper_dispatch tests.test_linux_helper_task_quota -q
```

预期target1 PASS、新模块14方法全部GREEN、原9拒绝不退化、新全部实际lstat故障拒绝、0 ERROR/skip；数量/实际新fault位置总数、耗时运行后由root填，不照搬276或预造新计数。旧stat编号只是失败基线，不是修复后稳定调用身份；strict路径可能改变stat/lstat数量，root须按实际调用路径核新矩阵覆盖home/prefix/baseprefix，而不是把相同序号视作相同目标。两个旧默认callback方法须证明零kwargs旧shape，旧相关111合同不退化。root独立复验、冻结source/isolation/test三SHA后才同时标Task2整体与Task2R完成，进入Task3双审；任何unknown/失败均不解锁。

### Task 3: 双审、目标区分性、完整守护与精确 main 发布

**状态**
- [ ] 任务完成

**Dependencies:** Task 2R 与 Task 2 修复后的实际全GREEN（不是原target单项GREEN）
**Parallelizable:** No (SOURCE 冻结，SPEC 通过才不同 QUALITY，root 最后完整守护)

- [x] **Step 1: fresh SPEC 逐项核目标，再不同 fresh QUALITY**

审查从文件实际读取，不采作者自报；检查母§5第二项、全部source/private API、无 factory-manifest 同对象伪称、目录两端/项目write控制及 pipx 正控、闭环逆序清理；firstsignal/unknown不能被覆盖。逐条报告 C/I/M；任何遗留回修，再 fresh SPEC→不同 QUALITY，不能带已知 Important 跑发布。两 reviewer 不写代码。

- [x] **Step 2: 在内存 AST 中删目标 predicate，证明负控不是旁门早拒**

root 用以下完整脚本，仅解析内存新模块、临时替换测试引用，不编辑生产文件、不运行 helper：

```bash
.venv/bin/python -B - <<'PY'
import ast
from pathlib import Path
import types
import unittest
import tests.test_linux_helper_source as suite
source = Path('src/icode/linux_helper_source.py').read_text()
tree = ast.parse(source)
function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_write_boundary')
loop = next(node for node in function.body if isinstance(node, ast.For))
target = next(node for node in loop.body if isinstance(node, ast.If))
target.test = ast.Constant(False)
ast.fix_missing_locations(tree)
mutant = types.ModuleType('icode._source_boundary_mutant')
mutant.__package__ = 'icode'
import sys
sys.modules[mutant.__name__] = mutant
try:
    exec(compile(tree, '<in-memory-source-boundary-mutant>', 'exec'), mutant.__dict__)
    original = suite.subject
    suite.subject = mutant
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([
        suite.SourceTests('test_workspace_install_is_target_rejection')]))
    if result.testsRun != 1 or len(result.failures) != 1 or result.errors or result.skipped:
        raise SystemExit('target mutation was not an exact assertion failure')
finally:
    if 'original' in locals():
        suite.subject = original
    sys.modules.pop(mutant.__name__, None)
PY
```

预期脚本exit0，但内部1方法/1真实断言FAIL「未抛固定错误」，0 ERROR/skip；不是生产失败，而是目标测试区分性。fresh SPEC另审 leaf identity、dirname identity、alias漂移目标fixture有效性，不能用坏owner替代目标命中。生产 unmodified 新测试应全部 GREEN。无新「完成」能力声明。

- [x] **Step 3: root 源码冻结后的完整门与文档两次一致性**

```bash
.venv/bin/python -B -m unittest tests.test_linux_helper_source tests.test_linux_static_helper tests.test_linux_helper_object tests.test_linux_helper_elf tests.test_native_helper tests.test_linux_helper_dispatch tests.test_linux_helper_task_quota -q
.venv/bin/python -m compileall -q -j1 src scripts tests
```

按 root 项目现行完整守护命令一次执行：`CMAKE_BUILD_PARALLEL_LEVEL=1 MAKEFLAGS=-j1 .venv/bin/python -u scripts/preflight.py`。完整守护包括 secret/vendor 等现合同；实际stdout/exit确认，不凭 shell启动或空报告称通过。root 最后 apply_patch 仅更新本 PLAN 实际状态、双审、SHA、计数/skip/unknown、研究live来源前置条目及当前未通过边界，再对母 DESIGN、本 PLAN 与 S0a PLAN 执行文档一致性检查两次连续0问题。最后一次文档修改后重新跑两次，不用前次结果代替。

四 installed runner、新scope、新自动合流、LA-2/R2/R3不在本软件门信用内。安装 metadata 定位留 S3；这套源码fixture在普通用户可写 pipx-like布局的正控不等于真正 pipx install/新wheel安装验收。

- [ ] **Step 4: root 精确提交 main、推送并只读观察同 SHA CI**

```bash
git diff --check
git status --short
git diff --stat
git add src/icode/linux_helper_source.py src/icode/isolation.py tests/test_linux_helper_source.py
git add -f docs/nbl/plans/2026-10-12-linux-helper-source-boundary.md
git add -f docs/nbl/specs/2026-10-12-linux-prepared-step-scope-design.md docs/nbl/plans/2026-10-12-linux-static-held-helper.md
git add docs/agent-landscape-live.md
git diff --cached --check
git diff --cached --name-only
git commit -m "feat(linux): observe held helper package source boundaries"
git push origin main
git ls-remote --heads origin
```

执行前 root 核下列七精确路径只含本阶段必要修改，不能 `git add .`；若研究live未改则该add无新内容。不包含 vendor/KEY/无关文件。此前阶段工作流若仍在跑，遵守项目 cancel-in-progress 同 SHA 实证保护，先只读等到 terminal 再推送。不新branch、不猜 remoteonlymain。推送/CI实际失败就保持失败边界，不隐去skip，不把 Windows Reviewer Win10035 timeout称 DENY。main用户阶段提交授权已在上文给出。

root后续交付清单修订：三代码路径为新source、其新测试、`src/icode/isolation.py` 三私有方法；四文档为本PLAN、母DESIGN最小strict补充、live与旧S0a PLAN。共七个必要精确路径，不纳其它文件。旧S0a PLAN仅补实际d10cd46发布及前阶段关闭，不能改S0a源码或扩大准入；root必须全文读取全部改动，fresh SPEC→不同QUALITY以及关联文档两轮核验。

## 研究复用与自审

2026-10-12：复用母 DESIGN 的固定 Codex `27065a91ccbf5ba8532844be3777fcf83b77820d` [bundled_bwrap](https://github.com/openai/codex/blob/27065a91ccbf5ba8532844be3777fcf83b77820d/codex-rs/linux-sandbox/src/bundled_bwrap.rs) 和 OpenHands SDK `3934349da2db0433238621542173a00a8af7439c` [LocalWorkspace](https://github.com/OpenHands/software-agent-sdk/blob/3934349da2db0433238621542173a00a8af7439c/openhands-sdk/openhands/sdk/workspace/local.py)。不是最新 HEAD；本 writer未新增上游取数。pipx [官方原理](https://pipx.pypa.io/stable/explanation/how-pipx-works.html) 初次观察来自独立研究者于2026-10-12 00:31 UTC的读取，root于00:35–00:36 UTC另行复取该官方页面及上述两份固定源码。独立用户 venv与应用launcher映射意味着不能以「用户可写」或解释器alias一律拒绝正常安装。root实现阶段按 repo规则记录实际观察，不假称本作者在线实测。

采纳：打开对象与来源分层、有限目录观测、项目权限与宿主可写权限区分。暂缓：publisher、密封、持续不可变、S1生命周期与S3安装验收。不适配：可选hash绕过、typed/snapshot自证执行、直接宿主Popen。本原创计划不复制上游代码；既核Apache-2.0/MIT不新增依赖/许可义务，成本是有限目录FD和manifest读，兼容旧候选无变化。

作者自审：§5第二项对应Task2完整代码与Task1 fixture；本次真实失败对应Task2R完整三私有方法、三source调用diff、3新测试与lstat矩阵扩展。接口只有真实sandbox/policy/owner，无caller expected覆写；Task1→Task2失败冻结→Task2R→Task3串行，Task2全GREEN不是Task2R前置。budget/typed/snapshot/新manifest与factory旧manifest边界均明确，旧11方法保持失败历史；不实施后续scope、不把软件host实证替原生/installed/LA-2。

【架构级自检报告】（计划文档，未执行源码）

- 语法/编译：文档与代码块静态核；未编译/测试，不宣称运行通过。
- 依赖/调用链：复用现真实符号；仅三私有strict路径成对计划，无生产接线，不改变runner/broker或旧callback形状。
- 逻辑/边界：来源、write根、runtime映射、目录项和同held identity成对；manifest仅新观测。
- 异常处理：普通固定错误、首信号原对象、独立逆序一次close与unknown不成功已给完整代码/矩阵。
- 关联模块：仅最小isolation三私有方法与母DESIGN补充；不改工厂、静态解析、CP、vendor、KEY；S1/S3另计划。
- 兼容安全：合法外置用户可写安装不一律拒绝，workspace venv拒绝新来源信用；旧显式入口未改变。
- 可运行性：本作者仅写PLAN，未实施/测试/CI；root独立双审及实际完整守护后才可交付本软件分片。

---
**Execution Mode:** serial

复杂的来源/FD/异常合同非机械修改，Task1→Task2失败冻结→Task2R→Task3纯串行。由主root采用 nbl.subagent-driven-development，返修计划/母补充先双审、fresh implementer与独立审查交接；当前文档writer到此停写，不越过委派执行。

## 实际实施记录（2026-10-12）

Task1 fresh writer完整上下文及两阶段自审零遗留，仅新增11方法测试与4行scaffold。00:50:01 UTC缺模块实际rc1/errors1、ModuleNotFoundError不授RED；00:50:07 UTC补未发布scaffold后同target实际1method/1目标assertFAIL/0error/skip、0.002s、rc1。独立fixture只读校验确认真实旧factory owner、合法policy/runtime、包路径相等与write overlap目标，未执行helper。root全文读新两文件并独立重现同1/1/0/0、0.002s；临时scaffold SHA256 `796ebb2312dc555b6b467f9808843ba2349d4ea7b4d1326cc1615c82a256de46`，测试`227756bdb27f4a5d3bb09af14efe81a18105f8eb015154602c8713256c6416f4`。旧四路径未改，S0a冻结摘要不变。Task2 fresh writer现仅获生产模块GREEN替换范围，不得提交scaffold或改旧合同；完整行为/清理/双审及root全量门仍待。

文档扫描已发现10个疑似相对断链，全为fenced Python中的`REAL['open'](...)`等字典调用，被原检查器正则误识为链接。root已全文核它们为代码，不是Markdown引用；保留原扫描疑似项并人工排除，不改源码/测试消警、不宣称原脚本输出0。最终连续两轮须分别报告原疑似数、代码误报排除数与真实遗留数。

### Task2 失败基线与 claim ledger（00:54–00:56 UTC）

以下为root提供且独立复现的实际记录，本DOCS返修者未运行测试或源码；保留原stderr完整记录，不改写失败为成功。

| 基线项 | 实际证据与限制 |
| --- | --- |
| 对象/设备 | 软件宿主Linux；物理设备序列号N/A，无设备/原生隔离root-cause信用 |
| 分析基线 | main `d10cd46dc7220a8cc5c87d46e0d1dd41a547f11c` +未发布dirty生产模块 `c4d965a3fc46381e1e16e2e4586c9ce26d085e871086cff1b3d4295c54f6e7f3`；测试 `227756bdb27f4a5d3bb09af14efe81a18105f8eb015154602c8713256c6416f4` |
| runtime provenance | root实际inspect Python3.11.15 uv stdlib `/home/orbbec/.local/share/uv/python/cpython-3.11.15-linux-x86_64-gnu/lib/python3.11/pathlib.py` 的 `Path.resolve`；先猜 `/usr/local` 不存在是诊断路径猜测失败，未改SOURCE，不是实际源码来源 |
| verification状态 | Task2目标RED→GREEN实际1方法/0.002秒；新11方法全套actor0.272秒、root独立0.290秒，均9个OSError subtestFAIL、0 ERROR/skip；尚未修复/完整验收 |
| 原故障矩阵 | 成功路径实际open12、close12、fstat27、stat40、pread1，共92实际位置×3=276故障case；267通过、9失败，失败全部为stat1/2/3、6/7/8、36/37/38的OSError |
| 调用边界 | source88/92/171→isolation963/964的home、prefix、baseprefix非严格resolve；3轮×3路径吞OSError，源wrapper没有收到拒绝异常 |
| 原因支持 | root读取本机真实3.11.15 `Path.resolve(strict=False)`：非严格分支的 `p.stat()` catch普通OSError仅检查ELOOP；另9次只读fixture诊断逐目标独立复现ignored-OSError，实际 `sys._getframe` 栈为Path.stat1013→Path.resolve1003→isolation963/964→runtime975→source88/92/171；诊断doCleanups收尾前borrowed owner仍live。支持本host辅助解析根因，不外推所有Python版本/设备/原生helper |
| 旧合同与vendor | actor旧相关111项/5.626秒/0 skip；vendor固定 `21566a589cbe98bd35372a04bbb6ca1c51d8eed2` 无修改，不改变已有旧回归证据 |

| claim | 状态 | 边界 |
| --- | --- | --- |
| 原source workspace-write目标负控有效、目标已GREEN | fact | 仅一个目标，不代表来源全套完成 |
| 9个runtime stat OSError原候选会静默成功 | fact | actor及root同host独立复现 |
| source wrapper已保证任意runtime OSError固定拒绝 | refuted | 原9负控直接反驳，不删除、不降预期 |
| 非严格辅助Path.resolve吞错误解释本host失败 | root_cause_supported | 本机stdlib+调用位置+实际fail相互对应，非设备归因 |
| Task2R strict修复已通过14方法/新lstat矩阵 | unobserved | 仅返修计划，数量与实际结果实施后填 |
| 旧默认无keyword callbacks已实测兼容新修复 | unobserved | 新两方法实施/运行后才授信用 |
| source/install/LA-2/ready/R2/R3整体已通过 | unobserved | 本片未发布且无installed/自动前门信用 |

### Task2R返修设计双审与实施起点

root全文读取865行返修PLAN及母§5补充，冻结PLAN `aec0bfff6730beb7464759701257b85f961170dc008a40a675af62ef7bc088d8`、DESIGN `7741bb7a573ab18f89c4285a5b6fe3ec1d0d554cc7fcbbde734c5fb7503b4cfe`；fresh独立SPEC及不同QUALITY均C0/I0/M0。此结论只允许实施Task2R，不撤销原9失败、不授源码GREEN。唯一SOURCE writer仅获三代码路径；先新增strict spy和两旧shape测试、lstat矩阵，实际有效assertion RED后停写待root独立复现，再修三私有方法/三个调用点。未运行或未来结果不提前填写。

Task2R测试先行实际：仅新增三方法+lstat，TEST `a55ffd918f07b028ac552481b389ccc20830258ba050b0236e788b35f4428a5b`；生产模块仍`c4d965…`、isolation仍`003a2e91242c310753091314d1f8ffe5372664acd962efd8c2af2456db3f580b`。strict target作者及root独立均1method/1assertionFAIL/0ERROR/skip、0.003s、rc1；正常observe已返回，最后断言实际9个tracked resolve均strict=None，非TypeError或ImportError。root全文核实际fixture/三新方法和三SHA后允许精确GREEN修改，结果仍待。

Task2R随后精确GREEN：source `da627af22ade2514389c8ddb3eb876df6102f1c2ea6cbc356c9b9b3a8eb62e56`、isolation `2854e7ce90ab68d0291c8608544e9fea99efa1f7316a1f71e118bfa4066ba880`，TEST保持RED冻结摘要。作者target1/0.002s、14新方法/0.468s、旧111/5.666s均0FAIL/ERROR/skip、rc0；真实矩阵open12/close12/fstat27/stat31/lstat94/pread1，共177位置×3=531故障全部通过。root逐实际diff读取三方法/三调用点，独立关联125方法/6.174s/0FAIL/ERROR/skip；另独立发现同177位置并用真实addSubTest计数实测531/0.403s/0FAIL/ERROR/skip。保留原9失败及原stat编号历史，不拿旧编号冒充新覆盖。两旧callback方法、borrowowner仍live/无offset变化、逆序一次close及首信号合同在实际测试内；SOURCE现冻结停止写入，交fresh SPEC→不同QUALITY，完整守护及发布仍待，不能授installed/ready或R2/R3。

root内存目标区分性：仅把`_write_boundary`的相交predicate置False时，合法workspace-install目标实际1method/1assertionFAIL/0ERROR/skip、0.003s；仅把严格runtime分支两处`resolve(strict=True)`的True置False时，strict spy实际1method/1assertionFAIL/0ERROR/skip、0.002s。脚本主动确认期望失败后exit0；生产文件未修改、未运行helper。此证据仅对应这两个目标；目录身份/alias等其它负控仍由fresh SPEC实际核验，不能据此补授全部鉴别力。

最终SOURCE首轮SPEC撤回为C0/I1/M0：仅测试目标区分性缺口，非生产Bug。原祖先替换fixture创建空new native，后置路径缺失会提前拒绝；独立审查者及root各在内存删末端dirname身份predicate后实际target仍1PASS/0ERROR/skip、0.003s，证明原测试不能鉴别目标。root仅给新目录填完整合法helper字节、mode及matching manifest，再清除这两个替身后保留原symlink负控；不改生产门、不降低失败预期。原候选GREEN仍是历史，不作为最终双审；修复后的区分性、回归及fresh SPEC→不同QUALITY重新实际核验后填。

此测试修复实际TEST `26ec85c6a90a1b30a0abb0b9f744f2a1995efe60a344ac8d84850095826744c1`；root同dirname mutant现1assertionFAIL/0ERROR/skip/0.003s，unmodified target+模块实际15方法/0.446s/0skip GREEN。fresh独立SPEC复审C0/I0/M0：125关联/6.147s、531故障/0.403s全部通过；dirname/helper快照/alias漂移三个目标删除实际各1assertionFAIL/0ERROR/skip，分别0.003/0.002/0.002s。不同QUALITY仍在核验，完整preflight未跑，旧测试弱鉴别与原9失败历史不抹去。

不同fresh QUALITY现C0/I0/M0：实际正确七模块125/6.130s、531故障/0.414s全部通过；三个身份/alias目标内存删除各恰1assertFAIL/0ERROR/skip。QUALITY首次自选命令误引三个不存在模块，collection errors3，立即改用PLAN真实模块；保留为审查harness路径错误，非产品测试RED或通过证据。root三源码冻结摘要已核，S0a源码/测试摘要保持旧值；compileall全src/scripts/tests -j1、site和governance各exit0。原完整preflight session5456已启动，密钥/vendor两道已OK，全量仍在运行，未授最终守护或发布。

原文档scanner当前实测11疑似：10项为fenced Python字典调用，另1项是前述扫描说明中的inline-code示例。root逐匹配位置核两类都非Markdown链接；真实断链/Unicode/结构遗留0，不把原11改报0。最终关联四文档仍需最后编辑后连续两轮原扫描，并保留原数、代码误报数、实际遗留数。

01:27 UTC续跑核验：原session5456句柄实际Unknown process id，已知父/子PID1931824/1931847均不再存在；此前仅密钥/vendor两道OK，全量退出记录不可取回，不授完整守护成功。SOURCE三文件与S0a两文件摘要实际不变。保持冻结后重跑同原完整命令，使用script工具保存原输出及真实COMMAND_EXIT_CODE于仓外`/tmp/icode-s0b-preflight.VdrE1y/typescript`，仍-j1；不是观察超时后盲目重启，也不把中断当产品失败或全量通过。

完整守护续跑于2026-10-12 01:37:38 UTC实际结束：session36490原命令exit0，仓外原日志尾记录COMMAND_EXIT_CODE=0，密钥/vendor/全量测试三道均OK。守护成功路径不输出unittest计数，故不虚报本机全量项数。三SOURCE冻结摘要与双审对象保持一致。关联四文档最后编辑后执行两轮原扫描及逐误报排除；真实遗留非零则禁止提交。本片仅软件来源观察通过，未授installed/ready或LA-2/R2/R3。

root实际两轮关联四文档扫描均原11疑似，逐位置排除10 fenced代码及1 inline代码误报，真实遗留0；密钥和固定vendor守护随后各exit0。此记录写入后再次跑同两轮原扫描及误报核验，结果不符就禁止交付；原扫描器和SOURCE均不修改。

【架构级自检报告】（S0b软件候选，发布前）

- 语法/编译：compileall -j1、差异格式检查通过。
- 依赖/调用链：三私有strict入口成对，旧无keyword回调及125关联测试通过，无生产准入接线。
- 逻辑/边界：14新方法、531真实位置故障及三身份目标区分性通过。
- 异常处理：首信号、普通固定拒绝、逆序一次关闭与unknown拒绝有实际覆盖；不声称所有平台异常穷尽。
- 关联模块：site/governance通过，固定vendor不变，无KEY、控制面或runner改动。
- 兼容安全：旧111项回归包含于关联125项，旧默认行为不变；新观察不授授权。
- 可运行性：原完整预检三道exit0；安装包、跨平台及整体自动模式尚未通过，不报告整体100%。
