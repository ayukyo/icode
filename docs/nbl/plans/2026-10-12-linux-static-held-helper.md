# Linux held helper 有限静态加载子检查 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development (recommended) or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增一个私有、有限、同 FD 的 ELF 静态加载子检查，绑定真实 helper owner 的摘要，保持旧 factory 及全部执行调用链合同。

**Architecture:** 在 `linux_static_helper.py` 中对既有 owner 借用 `fileno()`，用 `pread` 解析有限 ELF64LE header/program-header 表并重核全文摘要和读前后快照。检查不拥有或关闭 owner，不重开路径，不改变共享 offset；以后准备工厂负责调用并唯一收尾。本片没有生产调用接线，不授来源认证或执行权限。

**Tech Stack:** Python >=3.11 标准库 os/stat/struct/hashlib/unittest；既有 LinuxHelperObject 和 linux_elf_architecture；无 readelf 运行依赖，无新服务/依赖；编译并发 1。

---

状态：Task1/Task2软件候选、最终独立双审及Task3完整软件守护通过；本记录时尚未提交/推送，发布将另核远端实际SHA。冻结源码为 main `206057e`，不是母设计记录的历史源码 SHA。母设计为 [Linux 单步准备对象设计](../specs/2026-10-12-linux-prepared-step-scope-design.md)，其修订正文独立 SPEC 与不同 QUALITY 均 C0/I0/M0；设计信用不代软件或原生验收。

这是 S0 的 **S0a 静态加载子项**，不覆盖整个 S0，更不覆盖 S1/S2/S3 或 LA-2。来源可写边界、祖先/映射核验、lease、scope、attachment、broker、runner、selector、ready、环境构造、FD 关闭均不修改；相应后续独立 PLAN 必须再审。本片仅新增两个源码/测试路径，不修改 `linux_helper_object.py`、`native_helper.py`、旧测试、旧 docs、vendor、KEY 或 CI。

用户明确 main 单分支及推荐常规选择自主继续，覆盖技能默认 worktree/新分支；不用新 branch/worktree。本作者的委派范围仅写本 PLAN，覆盖 writing-plans 的“立即调用执行技能”默认，不实施下面代码、不跑全测试、不做 Git 写操作；这不是用户要求暂停持续开发。未来实现阶段仍逐任务串行、fresh SPEC 后不同 QUALITY，由 root 统一验收/发布。

三问已核：真实缺口是现 factory 只核64字节 ELF头，接受 ET_DYN 且无 program-header 加载检查；已有 owner/factory/头解析器可复用；新增私有独立函数尚无调用方，不收紧既有合同。已用 sequential-thinking 三步记录需求分解、方案及风险。本片不再新开上游调研：复用母设计固定日期/提交的 Codex 与 OpenHands 研究及本轮独立只读调研记录，不能伪称最新 HEAD；实现 root 阶段按仓库约定刷新相关研究记录，不改本 PLAN 以外旧文档。采纳同对象摘要分层；暂缓密封/来源/正式准入；不适配 typed constructor 自证授权。只写标准库原创逻辑，无上游代码复制/许可新增。

| 路径 | 责任 |
| --- | --- |
| 新增 `src/icode/linux_static_helper.py` | `validate_static_linux_helper(owner) -> None` 私有加载子检查；固定错误沿用 LinuxHelperObjectError |
| 新增 `tests/test_linux_static_helper.py` | 真实 factory owner、完整 synthetic program-header 表、目标负控与同 FD/预算/异常测试 |
| 新增 `docs/nbl/specs/2026-10-12-linux-prepared-step-scope-design.md` | root已登记双审actual的母DESIGN；当前untracked且受ignore，随本软件分片精确发布，不由本作者修改 |
| 本 PLAN | 仅计划/证据边界；root 在实施后记录真实结果，未执行结果只标预期 |

不能用 `LinuxHelperObject(...)` 构造成功认证来源，`isinstance` 仅限制内部接口类型。该子检查重新校验持有字节与 owner 摘要，不认证 owner 曾经经过 factory；真正准备工厂仍必须实际取得包内 factory owner。trusted host 不得并发修改 owner 或外部 close/dup2；本片不消除 ABA、持续内容变更、同 UID 宿主攻击或 publisher 风险。

### Task 1: 建立可执行目标 RED 与完整真实 FD fixture

**状态**
- [x] 任务完成（真实目标RED；未发布scaffold已由Task2完整替换）

**Dependencies:** None
**Parallelizable:** No (先确认目标 assertion RED，后续实现依赖该证据)

- [x] **Step 1: 冻结前置并完整读上下文**

```bash
git rev-parse --abbrev-ref HEAD
git rev-parse HEAD
git status --short
git diff -- src/icode/linux_helper_object.py src/icode/native_helper.py tests/test_linux_helper_object.py tests/test_linux_helper_elf.py
```

预期：main，HEAD 前缀206057e；若源码基线变了或目标新路径已有非本片内容，停止交 root 重冻结，不覆盖用户改动。完整读 AGENTS.md、上述四文件、tests/_support.py、母设计与本计划；不读取 KEY 正文。当前写计划者已读，不算实现阶段运行结果。

- [x] **Step 2: 先用 apply_patch 新建完整测试文件**

文件 `tests/test_linux_static_helper.py` 全文如下。fixture 有完整 ELF header 与 program-header 表，不执行合成文件；旧 factory 本身必须接受动态目标 fixture，不能改旧 factory 绕过 RED。

```python
"""Finite static-load subcheck on real factory owners; no execution grant."""
from __future__ import annotations

import hashlib
import os
import struct
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tests._support import temp_workspace
import icode.linux_helper_object as factory
import icode.linux_static_helper as subject

REAL_PREAD = getattr(os, "pread", None)
REAL_FSTAT = os.fstat
ERROR = "Linux helper object is unavailable"


def image(*, machine=62, kind=2, types=(1,), phoff=64, entsize=56,
          count=None, tail=b""):
    header = bytearray(64)
    header[:7] = b"\x7fELF\x02\x01\x01"
    struct.pack_into("<HHI", header, 16, kind, machine, 1)
    struct.pack_into("<Q", header, 32, phoff)
    struct.pack_into("<HHH", header, 52, 64, entsize,
                     len(types) if count is None else count)
    table = b"".join(struct.pack("<IIQQQQQQ", ptype, 5, 0, 0, 0,
                                  64 + 56 * len(types), 64 + 56 * len(types), 4096)
                     for ptype in types)
    return bytes(header) + table + tail


def pair(root, data):
    binary, manifest = root / "helper", root / "helper.sha256"
    binary.write_bytes(data)
    binary.chmod(0o700)
    manifest.write_bytes(hashlib.sha256(data).hexdigest().encode() + b"\n")
    return binary, manifest


class PortableTests(unittest.TestCase):
    def test_unsupported_platform_refuses_before_owner(self):
        # Typed negative sentinel only: no FD resource, factory provenance or authority.
        # Never close it; the platform gate must precede any owner access.
        owner = factory.LinuxHelperObject(-1, (-1, -1), "x86_64", "0" * 64)
        for platform in ("win32", "darwin", "freebsd"):
            with self.subTest(platform=platform), patch.object(subject.sys, "platform", platform):
                with patch.object(factory.LinuxHelperObject, "fileno") as fileno, patch.object(
                    subject.os, "pread", side_effect=AssertionError("unexpected read"), create=True
                ) as read:
                    with self.assertRaises(factory.LinuxHelperObjectError) as caught:
                        subject.validate_static_linux_helper(owner)
                    self.assertEqual(str(caught.exception), ERROR)
                    fileno.assert_not_called()
                    read.assert_not_called()

    def test_missing_pread_refuses_before_owner(self):
        # Same resource-free type sentinel; construction is not factory verification.
        owner = factory.LinuxHelperObject(-1, (-1, -1), "x86_64", "0" * 64)
        with patch.object(subject.sys, "platform", "linux"), patch.object(
            subject.os, "pread", None, create=True
        ), patch.object(factory.LinuxHelperObject, "fileno") as fileno:
            with self.assertRaises(factory.LinuxHelperObjectError):
                subject.validate_static_linux_helper(owner)
            fileno.assert_not_called()


@unittest.skipUnless(sys.platform.startswith("linux") and REAL_PREAD is not None,
                     "real Linux pread cases; no installed-package credit")
class StaticTests(unittest.TestCase):
    def setUp(self):
        host = patch.object(factory.platform, "machine", return_value="x86_64")
        host.start()
        self.addCleanup(host.stop)

    def reject(self, owner):
        with self.assertRaises(factory.LinuxHelperObjectError) as caught:
            subject.validate_static_linux_helper(owner)
        self.assertEqual(str(caught.exception), ERROR)
        self.assertIsNone(caught.exception.__cause__)
        self.assertTrue(caught.exception.__suppress_context__)

    def test_dynamic_targets_old_factory_accepts_new_check_rejects(self):
        for data in (image(kind=3), image(types=(1, 3)), image(types=(1, 2))):
            with self.subTest(data=data[16:18]), temp_workspace() as root:
                with factory.open_linux_helper_object(*pair(root, data)) as owner:
                    fd = owner.fileno()
                    self.reject(owner)
                    self.assertEqual(owner.fileno(), fd)

    def test_static_and_architectures_offset_same_fd_and_no_close(self):
        for machine, host, tail in ((62, "x86_64", b""), (183, "aarch64", b""),
                                    (62, "x86_64", b"x" * (65536 + 17))):
            with self.subTest(machine=machine, tail_size=len(tail)), temp_workspace() as root, patch.object(
                factory.platform, "machine", return_value=host
            ):
                data = image(machine=machine, tail=tail)
                with factory.open_linux_helper_object(*pair(root, data)) as owner:
                    fd = owner.fileno()
                    os.lseek(fd, 7, os.SEEK_SET)
                    calls = []
                    def pread(descriptor, length, offset):
                        calls.append((descriptor, length, offset))
                        return REAL_PREAD(descriptor, length, offset)
                    with patch.object(subject.os, "pread", side_effect=pread), patch.object(
                        subject.os, "open", side_effect=AssertionError("reopened")
                    ), patch.object(subject.os, "close") as closed:
                        self.assertIsNone(subject.validate_static_linux_helper(owner))
                        closed.assert_not_called()
                    self.assertTrue(all(descriptor == fd for descriptor, _, _ in calls))
                    self.assertLessEqual(max(length for _, length, _ in calls), 65536)
                    self.assertLessEqual(sum(length for _, length, _ in calls), 64 + 56 + len(data) + 1)
                    if len(data) > 65536:
                        self.assertEqual(calls[2:], [(fd, 65536, 0),
                                                    (fd, len(data) - 65536, 65536),
                                                    (fd, 1, len(data))])
                    self.assertEqual(os.lseek(fd, 0, os.SEEK_CUR), 7)
                    self.assertEqual(owner.fileno(), fd)

    def test_program_table_boundaries_and_extended_counts(self):
        bad = (image(entsize=0), image(entsize=55), image(entsize=57),
               image(count=0), image(count=1025), image(count=65535),
               image(phoff=0), image(phoff=63), image(phoff=2**64 - 1),
               image(phoff=121), image(count=2), image()[:-1])
        for data in bad:
            with self.subTest(length=len(data)), temp_workspace() as root:
                with factory.open_linux_helper_object(*pair(root, data)) as owner:
                    self.reject(owner)
        with temp_workspace() as root:
            with factory.open_linux_helper_object(*pair(root, image(types=(1,) * 1024))) as owner:
                self.assertIsNone(subject.validate_static_linux_helper(owner))

    def test_header_and_architecture_drift_after_factory(self):
        for offset, replacement in ((0, b"BAD!"), (4, b"\x01"), (5, b"\x02"),
                                    (6, b"\x00"), (18, b"\xb7\x00"),
                                    (20, b"\x00" * 4), (52, b"\x3f\x00")):
            with self.subTest(offset=offset), temp_workspace() as root:
                binary, manifest = pair(root, image())
                with factory.open_linux_helper_object(binary, manifest) as owner:
                    with binary.open("r+b") as stream:
                        stream.seek(offset)
                        stream.write(replacement)
                    self.reject(owner)

    def test_digest_drift_with_valid_header_is_target_rejection(self):
        with temp_workspace() as root:
            binary, manifest = pair(root, image(tail=b"old"))
            with factory.open_linux_helper_object(binary, manifest) as owner:
                binary.write_bytes(image(tail=b"new"))
                self.reject(owner)
                self.assertGreaterEqual(owner.fileno(), 0)

    def test_pre_post_snapshot_drift(self):
        for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns"):
            with self.subTest(field=field), temp_workspace() as root:
                with factory.open_linux_helper_object(*pair(root, image())) as owner:
                    reads = []
                    fstat_calls = 0
                    injected = False
                    def pread(fd, length, offset):
                        reads.append((length, offset))
                        return REAL_PREAD(fd, length, offset)
                    def fstat(fd):
                        nonlocal fstat_calls, injected
                        fstat_calls += 1
                        actual = REAL_FSTAT(fd)
                        # Calls 1/3 belong to owner.fileno; 2/4 are parser before/after.
                        # Only mutate parser after: no earlier owner identity gate can reject.
                        if fstat_calls == 4:
                            fields = {name: getattr(actual, name) for name in
                                      ("st_dev", "st_ino", "st_size", "st_mtime_ns",
                                       "st_ctime_ns", "st_mode")}
                            fields[field] += 1
                            injected = True
                            return SimpleNamespace(**fields)
                        return actual
                    with patch.object(subject.os, "pread", side_effect=pread), patch.object(
                        subject.os, "fstat", side_effect=fstat
                    ):
                        self.reject(owner)
                    self.assertEqual(fstat_calls, 4)
                    self.assertTrue(injected)
                    self.assertEqual(reads, [(64, 0), (56, 64), (120, 0), (1, 120)])
                    self.assertGreaterEqual(owner.fileno(), 0)

    def test_short_pread_each_stage_rejects_without_close(self):
        for stage in (1, 2, 3):
            with self.subTest(stage=stage), temp_workspace() as root:
                with factory.open_linux_helper_object(*pair(root, image())) as owner:
                    calls = 0
                    def pread(fd, length, offset):
                        nonlocal calls
                        calls += 1
                        data = REAL_PREAD(fd, length, offset)
                        return data[:-1] if calls == stage else data
                    with patch.object(subject.os, "pread", side_effect=pread), patch.object(
                        subject.os, "close"
                    ) as closed:
                        self.reject(owner)
                        closed.assert_not_called()

    def test_eof_growth_is_rejected_and_bounded(self):
        with temp_workspace() as root:
            data = image()
            with factory.open_linux_helper_object(*pair(root, data)) as owner:
                calls = []
                def pread(fd, length, offset):
                    calls.append((length, offset))
                    return b"x" if offset == len(data) else REAL_PREAD(fd, length, offset)
                with patch.object(subject.os, "pread", side_effect=pread):
                    self.reject(owner)
                self.assertEqual(calls[-1], (1, len(data)))
                self.assertLessEqual(sum(length for length, _ in calls), 64 + 56 + len(data) + 1)

    def test_size_limit_exact_and_plus_one(self):
        self.assertEqual(subject._BINARY_LIMIT, 64 * 1024 * 1024)
        self.assertEqual(subject._READ_CHUNK, 64 * 1024)
        for tail, accepted in ((b"x" * 8, True), (b"x" * 9, False)):
            with self.subTest(accepted=accepted), temp_workspace() as root:
                with factory.open_linux_helper_object(*pair(root, image(tail=tail))) as owner:
                    with patch.object(subject, "_BINARY_LIMIT", 128):
                        if accepted:
                            self.assertIsNone(subject.validate_static_linux_helper(owner))
                        else:
                            self.reject(owner)

    def test_internal_read_range_types_refuse_before_os(self):
        invalid = ((True, 1, 120), (0, True, 120), (0, 1, True),
                   (-1, 1, 120), (0, -1, 120), (121, 0, 120),
                   (119, 2, 120), (2**64, 1, 120), (0, 65537, 65537))
        with patch.object(subject.os, "pread") as read:
            for offset, length, size in invalid:
                with self.subTest(offset=offset, length=length, size=size):
                    with self.assertRaises(factory.LinuxHelperObjectError):
                        subject._read_exact(3, offset, length, size)
            read.assert_not_called()

    def test_rename_unlink_replace_uses_held_object(self):
        for operation in ("rename", "unlink", "replace"):
            with self.subTest(operation=operation), temp_workspace() as root:
                binary, manifest = pair(root, image())
                with factory.open_linux_helper_object(binary, manifest) as owner:
                    fd = owner.fileno()
                    if operation == "unlink":
                        binary.unlink()
                    else:
                        binary.rename(root / "saved")
                        if operation == "replace":
                            binary.write_bytes(image(types=(2,)))
                    # Path changes happen before the subcheck snapshot; no ctime immunity claim.
                    self.assertIsNone(subject.validate_static_linux_helper(owner))
                    self.assertEqual(owner.fileno(), fd)

    def test_wrong_closed_and_reused_owner(self):
        with patch.object(subject.os, "pread") as read:
            for value in (None, False, object(), SimpleNamespace(fileno=lambda: 0)):
                self.reject(value)
            read.assert_not_called()
        with temp_workspace() as root:
            binary, manifest = pair(root, image())
            owner = factory.open_linux_helper_object(binary, manifest)
            owner.close()
            self.reject(owner)
            owner = factory.open_linux_helper_object(binary, manifest)
            fd = owner.fileno()
            other = root / "other"
            other.write_bytes(image())
            replacement = os.open(other, os.O_RDONLY)
            try:
                os.dup2(replacement, fd)
                with patch.object(subject.os, "close") as closed:
                    self.reject(owner)
                    closed.assert_not_called()
                self.assertEqual(REAL_FSTAT(fd).st_ino, other.stat().st_ino)
            finally:
                # Explicit test ownership after violating the trusted-host contract.
                os.close(fd)
                os.close(replacement)

    def test_every_os_stage_fixed_fault_and_original_signals(self):
        # fileno 1/2; fstat owner 1/3 and parser 2/4; pread header/table/digest/EOF 1..4.
        for stage, ordinals in (("fileno", (1, 2)), ("fstat", (1, 2, 3, 4)),
                                ("pread", (1, 2, 3, 4))):
            for ordinal in ordinals:
                for error in (OSError("private-data"), KeyboardInterrupt("private-signal"), SystemExit(17)):
                    with self.subTest(stage=stage, ordinal=ordinal,
                                      error=type(error).__name__), temp_workspace() as root:
                        with factory.open_linux_helper_object(*pair(root, image())) as owner:
                            target = owner if stage == "fileno" else subject.os
                            original = getattr(target, stage)
                            calls = 0
                            def operation(*args):
                                nonlocal calls
                                calls += 1
                                if calls == ordinal:
                                    raise error
                                return original(*args)
                            with patch.object(target, stage, side_effect=operation), patch.object(
                                subject.os, "close"
                            ) as closed:
                                if isinstance(error, Exception):
                                    self.reject(owner)
                                else:
                                    with self.assertRaises(type(error)) as caught:
                                        subject.validate_static_linux_helper(owner)
                                    self.assertIs(caught.exception, error)
                                self.assertEqual(calls, ordinal)
                                closed.assert_not_called()
                            self.assertGreaterEqual(owner.fileno(), 0)


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 3: 记录缺符号状态，再建立未发布最小接口 scaffold**

先运行下面目标命令。新module缺失预计 ImportError/exit1，可以记录原始状态，但不能授有效RED。然后用apply_patch新建 `src/icode/linux_static_helper.py`，全文如下。它只复用旧 header 检查，不是有效实现；不得提交、发布或授验收信用。

```bash
./.venv/bin/python -m unittest tests.test_linux_static_helper.StaticTests.test_dynamic_targets_old_factory_accepts_new_check_rejects -v
```

```python
"""Unpublished TDD scaffold; header check only, no static-load claim."""
from __future__ import annotations

import os

from .linux_helper_object import LinuxHelperObjectError
from .native_helper import linux_elf_architecture


def validate_static_linux_helper(owner) -> None:
    if linux_elf_architecture(os.pread(owner.fileno(), 64, 0)) != owner.architecture:
        raise LinuxHelperObjectError()
```

- [x] **Step 4: 只跑动态目标，记录有效 assertion RED**

```bash
./.venv/bin/python -m unittest tests.test_linux_static_helper.StaticTests.test_dynamic_targets_old_factory_accepts_new_check_rejects -v
```

预期：1 test method、3 subTest assertion failures（`LinuxHelperObjectError not raised`）、exit1；ET_DYN、PT_INTERP、无 PT_INTERP 的 PT_DYNAMIC 三目标均由旧 factory 实际接受后命中新子检查缺口。ImportError、scaffold 无 sys 等其它方法失败、旧模块失败不算 RED。本步只跑该目标方法；不得把 scaffold 提交。

### Task 2: 完整有限解析、快照和摘要绑定

**状态**
- [x] 任务完成（软件候选；最终双审与完整守护后续通过，见实际记录）

**Dependencies:** Task 1
**Parallelizable:** No (必须先保留有效目标 RED，再替换 scaffold)

- [x] **Step 1: apply_patch 完整替换 scaffold**

`src/icode/linux_static_helper.py` 全文如下；不修改旧 factory/头解析器。

```python
"""Private bounded static-load subcheck; never provenance or execution authority.

Borrow an existing owner without opening/closing descriptors or moving offsets.
The preparing creator remains the unique close owner, including on failure.
Trusted host callers must not close/dup2 or concurrently mutate the owner.
"""
from __future__ import annotations

import hashlib
import os
import stat
import struct
import sys

from .linux_helper_object import LinuxHelperObject, LinuxHelperObjectError
from .native_helper import linux_elf_architecture

_BINARY_LIMIT = 64 * 1024 * 1024
_READ_CHUNK = 64 * 1024
_HEADER_SIZE = 64
_PH_ENTRY_SIZE = 56
_PH_COUNT_LIMIT = 1024
_TABLE_READ_LIMIT = 64 * 1024
_FORBIDDEN_TYPES = (2, 3)  # PT_DYNAMIC, PT_INTERP; static PIE is outside this slice.


def _snapshot(status):
    return (status.st_dev, status.st_ino, status.st_size,
            status.st_mtime_ns, status.st_ctime_ns)


def _read_exact(fd: int, offset: int, length: int, size: int) -> bytes:
    # Validate before calling the OS; bool is not an integer contract input.
    if (type(offset) is not int or type(length) is not int or type(size) is not int
            or offset < 0 or length < 0 or length > _READ_CHUNK
            or offset > size or length > size - offset):
        raise LinuxHelperObjectError()
    data = os.pread(fd, length, offset)
    if type(data) is not bytes or len(data) != length:
        raise LinuxHelperObjectError()
    return data


def validate_static_linux_helper(owner: LinuxHelperObject) -> None:
    """Check finite ET_EXEC/no-loader shape and held digest; no factory attestation."""
    try:
        if (not sys.platform.startswith("linux")
                or not callable(getattr(os, "pread", None))
                or not isinstance(owner, LinuxHelperObject)):
            raise LinuxHelperObjectError()
        fd = owner.fileno()
        if type(fd) is not int or fd < 0:
            raise LinuxHelperObjectError()
        before = os.fstat(fd)
        size = before.st_size
        if (not stat.S_ISREG(before.st_mode) or type(size) is not int
                or size < _HEADER_SIZE or size > _BINARY_LIMIT):
            raise LinuxHelperObjectError()
        header = _read_exact(fd, 0, _HEADER_SIZE, size)
        architecture = owner.architecture
        if (type(architecture) is not str or architecture not in ("x86_64", "arm64")
                or linux_elf_architecture(header) != architecture
                or struct.unpack_from("<H", header, 16)[0] != 2):
            raise LinuxHelperObjectError()
        phoff = struct.unpack_from("<Q", header, 32)[0]
        entsize, count = struct.unpack_from("<HH", header, 54)
        table_size = entsize * count
        if (entsize != _PH_ENTRY_SIZE or not 1 <= count <= _PH_COUNT_LIMIT
                or phoff < _HEADER_SIZE or table_size > _TABLE_READ_LIMIT
                or phoff > size or table_size > size - phoff):
            raise LinuxHelperObjectError()
        table = _read_exact(fd, phoff, table_size, size)
        for offset in range(0, table_size, _PH_ENTRY_SIZE):
            if struct.unpack_from("<I", table, offset)[0] in _FORBIDDEN_TYPES:
                raise LinuxHelperObjectError()

        digest = hashlib.sha256()
        offset = 0
        while offset < size:
            count = min(_READ_CHUNK, size - offset)
            digest.update(_read_exact(fd, offset, count, size))
            offset += count
        # At most size+1 digest bytes; unexpected EOF growth is an independent refusal.
        eof = os.pread(fd, 1, size)
        if type(eof) is not bytes or eof != b"":
            raise LinuxHelperObjectError()
        if owner.fileno() != fd:
            raise LinuxHelperObjectError()
        after = os.fstat(fd)
        if (_snapshot(before) != _snapshot(after)
                or digest.hexdigest() != owner.sha256):
            raise LinuxHelperObjectError()
    except BaseException as error:
        # No parser-owned resources exist; the first signal is the original object.
        if not isinstance(error, Exception):
            raise
        raise LinuxHelperObjectError() from None
```

该实现读 header64、table至多57344（预算≤65536+64）；全文摘要最多64MiB加1 EOF字节，块≤64KiB。短 pread 固定拒绝，不累计补齐造成额外预算；无扩展计数、无外部readelf、无整数溢出（Python整数+先范围核验）、offset/length拒bool。仅解析所需 table 类型，不宣称完整 ELF 可加载性或段映射验证。合法 rename/unlink 在初始 snapshot 前发生允许同 FD继续；检查窗口内 ctime 漂移仍拒绝，不把它写成inode变化。

- [x] **Step 2: 跑目标 GREEN 和新完整测试**

```bash
./.venv/bin/python -m unittest tests.test_linux_static_helper.StaticTests.test_dynamic_targets_old_factory_accepts_new_check_rejects -v
./.venv/bin/python -m unittest tests.test_linux_static_helper -v
```

预期（不是实测）：目标1 method PASS；完整15 methods，在具备Linux pread的本机15 PASS/0F/0E/0skip。Portable2 + Static13；故障方法含10个实际OS调用位置×普通异常/KI/SE共30个subTest，快照方法5个字段都仅在parser末次fstat注入，正控方法含真实大于64KiB的跨摘要块fixture；这些subTest不算额外方法，也不算installed证据。不猜其它平台通过数。若预期计数不符，保存实际结果并核测试发现，不能默改为“全绿”。

- [x] **Step 3: 检查调用链边界与旧合同回归**

```bash
rg -n 'validate_static_linux_helper|linux_static_helper' src tests
git diff -- src/icode/linux_helper_object.py src/icode/native_helper.py tests/test_linux_helper_object.py tests/test_linux_helper_elf.py
./.venv/bin/python -m unittest tests.test_linux_helper_object tests.test_linux_helper_elf -v
```

预期：新符号仅新模块/新测试；四旧路径diff为空；旧套件exit0，实际总数/skip记录，不能先宣称数目或将既有原生skip算PASS。ET_DYN/header-only旧正控仍成立。未来准备创建者必须在自身finally唯一close，本 parser失败不关闭，不能以 parser PASS 代替 owner factory、source 或 scope 核验。

### Task 3: 独立审查、root守护与软件分片交付

**状态**
- [ ] 任务完成

**Dependencies:** Task 2
**Parallelizable:** No (同一候选冻结后顺序 SPEC→不同 QUALITY→root验收)

- [x] **Step 1: 作者自审后冻结两个新文件；fresh SPEC→不同 QUALITY**

```bash
sha256sum src/icode/linux_static_helper.py tests/test_linux_static_helper.py
git diff --check
```

root将冻结源码/测试/本 PLAN 与母设计交给新的SPEC reviewer，再交不同QUALITY reviewer；检查本片仅S0a、目标RED来源、真实factory同FD、旧合同、错误/信号、有限预算、owner关闭责任。reviewer不得读模型KEY、改旧文件或运行全仓测试；发现问题按同范围修复，重新冻结并双审，不复用旧候选review信用。本任务采用serial鲜context审查，不以作者自评替代。

- [x] **Step 2: root独立相关回归、compile-j1及原完整preflight**

```bash
./.venv/bin/python -m unittest tests.test_linux_static_helper tests.test_linux_helper_object tests.test_linux_helper_elf tests.test_native_helper tests.test_linux_helper_dispatch tests.test_linux_helper_task_quota -v
./.venv/bin/python -m compileall -q -j1 src/icode/linux_static_helper.py tests/test_linux_static_helper.py
CMAKE_BUILD_PARALLEL_LEVEL=1 MAKEFLAGS=-j1 ./.venv/bin/python -u scripts/preflight.py
git diff --check
```

预期exit0；只对已双审冻结候选跑一次原完整preflight三守护，不缩减、跳过或并行重复全测，保存真实rc/输出/方法数与skip，preflight成功未公开计数时不猜数字。若失败先归因修复，再重冻结/重审/重跑必要门，失败仍保留历史。编译并发1满足用户≤6；本片不改C编译。此处命令是实施验收计划，当前写PLAN阶段禁止执行。

- [x] **Step 3: 可选、本机已安装旧artifact独立实验**

以下完整命令从本机现有 `icode-agent` 安装元数据定位资源；拒绝定位到checkout、资源缺失或元数据缺失。实验不重新安装，不使用synthetic fixture或源码编译产物；root记录所打印的规范路径、摘要和架构，另核该旧artifact身份。

```bash
./.venv/bin/python - <<'PY'
from importlib.metadata import distribution, PackageNotFoundError
from pathlib import Path
import sys
sys.path.insert(0, str(Path.cwd() / "src"))
from icode.linux_helper_object import open_linux_helper_object
from icode.linux_static_helper import validate_static_linux_helper

try:
    package = distribution("icode-agent")
except PackageNotFoundError:
    raise SystemExit("NOT_RUN: no installed metadata")
members = {str(item): item for item in package.files or ()}
names = ("icode/native/icode-landlock", "icode/native/icode-landlock.sha256")
if any(name not in members for name in names):
    raise SystemExit("NOT_RUN: no installed helper members")
binary, manifest = (Path(package.locate_file(members[name])).resolve() for name in names)
checkout = (Path.cwd() / "src").resolve()
if any(path.is_relative_to(checkout) or not path.is_file() for path in (binary, manifest)):
    raise SystemExit("NOT_RUN: source or missing helper")
print("installed_binary=" + str(binary))
print("installed_manifest=" + str(manifest))
owner = open_linux_helper_object(binary, manifest)
try:
    print("digest=" + owner.sha256)
    print("architecture=" + owner.architecture)
    validate_static_linux_helper(owner)
    print("static_load_subcheck=PASS")
finally:
    owner.close()
PY
```

若输出NOT_RUN，记录“未运行：未定位旧installed artifact”，不试猜路径、不从checkout补替身、不授PASS。这里以新源码检查器核旧installed字节，明确不是新检查器已经installed，也不是完整安装消费链。实验只属于该旧artifact加载子项；母设计中旧readelf观察不是新实现实测。完整同候选SHA四Linux runner实际build/install、来源/内部consume及终态分账继续待S3，本片软件通过不能关闭这些门。

- [ ] **Step 4: root精确暂存/提交，推送等206057e四Windows gate终态**

先由root记录七维实际自检。提交前沿现有流程fresh secrets/submodule守护；stage只列确切路径，两份新docs受ignore时仅这两路径add-f。母DESIGN尚未发布，是本片关联的新文档，不属于禁止改动的已发布旧docs。此PLAN author阶段不执行Git写操作。

```bash
./.venv/bin/python scripts/preflight.py --only secrets
./.venv/bin/python scripts/preflight.py --only submodule
git add -- src/icode/linux_static_helper.py tests/test_linux_static_helper.py
git add -f -- docs/nbl/specs/2026-10-12-linux-prepared-step-scope-design.md docs/nbl/plans/2026-10-12-linux-static-held-helper.md
git add -- docs/agent-landscape-live.md docs/nbl/plans/2026-10-12-windows-installed-chain-role-diagnostic.md
git diff --cached --name-only
git diff --cached --check
git commit -m "feat(linux): add bounded held static helper subcheck"
```

cached最终必须仅上述六精确路径：两个SOURCE、新DESIGN、本PLAN、live及Windows阶段PLAN；后两文档仅root补已独立回读的206057e终态和本片实证，不含Windows源码或准入修改。若已有用户stage则不擅自撤销或混交，交root处理具体stage边界。原计划四路径及live可选第五的边界已按实际收尾清单更新；关联记录变更须执行受影响文档复核和守护。本PLAN不授权作者修改其它文件，不用 `git add .` 扩大范围。禁止除此两份收尾记录外的旧docs变更、vendor/KEY/Git回退。root推送之前必须确认当前206057e四Windows gate均已终态，防 `.github/workflows/ci.yml`/Windows provenance的 `cancel-in-progress: true`取消旧native观察；未终态继续安全监测，不提前推送触发取消。终态失败保留失败账，不能借本片通过抹掉。获得现有发布授权并满足原门后，root才执行：

```bash
git push origin main
git ls-remote origin refs/heads/main
```

读回远端SHA应等本次提交，发布标签仅“软件S0a有限静态加载子检查”。没有来源前置、真实installed四格、生产接线、ready/selector、LA-2、R2/R3或设备验收信用。

## 计划自审与交付边界

覆盖母设计§5第一项；第二项来源前置及§4/§6/§7 S1–S3故意留独立计划。代码接口与实际 factory/架构映射一致，文件责任完整；任务依赖为1→2→3。当前没有实现、测试、编译、preflight、提交或发布结果。实施时Task3必须补真实结果，不能把下述文档自检改成程序“100%”。

【架构级自检报告】（PLAN文档）

- 语法/编译：已完整检查代码示例与命令结构；未编译/运行，不声称源码编译通过。
- 依赖/调用链：复用真实owner/factory/header API；新检查无现有生产调用，不改旧接口。
- 逻辑/边界：ET_EXEC/架构、表大小/计数/范围、有限pread、EOF/摘要/快照及offset均有具体实现和测试。
- 异常处理：固定输入无关错误、首KI/SE原对象、不关闭borrowed owner明确；未知close仍归创建者，未实测。
- 关联模块：仅新增两个路径；来源/lease/scope/broker/runner和旧docs不在本片实现范围。
- 兼容安全：旧factory仍接受ET_DYN/header-only；无路径重开/readelf依赖、无权限或ready变化。
- 可运行性：提供完整fixture/实现/测试/验收命令；仅计划自审，真实软件/installed结果待执行，不能报告100%。

---
**Execution Mode:** serial

原因：有限OS对象解析、目标RED和独立审查需要上下文隔离；Task1→Task2→Task3严格依赖，不符合机械inline条件。当前只交PLAN给root fresh审查，不自动invoke执行技能；这是本作者仅写PLAN的委派范围，不是用户暂停持续开发的指令。

## 实际实施记录（2026-10-12）

初版635行PLAN冻结`c3463e40e614a85ea3f8f3fbf39325aae626526cf6411346450b750f98e4802f` 已经独立复审C0/I0/M0；snapshot目标改为仅第4parser fstat、跨64KiB摘要正控及30实际OS故障/信号subTest。root全文读取原计划及所有修订，sequential-thinking158–160，沿用户main单分支授权开始串行实施。

Task1先新增15方法测试，缺module实际errors=1明确不授RED；随后只加未发布header scaffold，作者与root分别取得1method/3目标assertFAIL/0error/skip、0.002s、rc1，旧factory实际接受三动态目标。Task2 fresh writer另重现RED后完整替换，目标1GREEN/0.001s、新15GREEN/0.066s、旧相关34GREEN/4.202s，均0skip。作者两阶段自审零遗留；root完整读取两新文件并独立15GREEN/0.065s，未将作者输出代完整root门。

Task2初次候选摘要：`src/icode/linux_static_helper.py` 为`efc18c6902e4df803764d37a294f3ef50bac516e5ae83bab16df8052b5625c86`，当时新测试为`c8d9792892698fac2b523184837659065283a0becbc635795d7b7124e58272e0`；这不是下述修复后的测试摘要。旧factory/ELF四路径diff仍空；不授来源、installed或LA-2信用。

root关联文档交付清单补充：前置`206057e`四Windows native签装门已全部终态、原日志与固定validator独立核完，允许后续完成软件门后推送而不取消旧CI。阶段收尾同步`docs/agent-landscape-live.md`研究实证及`docs/nbl/plans/2026-10-12-windows-installed-chain-role-diagnostic.md`旧阶段Task5实际状态；没有Windows SOURCE改动或权限放宽。最终stage限定为两个新SOURCE、新DESIGN、本PLAN、live和Windows阶段PLAN这六精确路径，经相关文档复核/守护后暂存，不扩`git add .`。

首次全量SOURCE规格审查的零遗留结论已撤销为C0/I1/M0：两Portable方法传`object()`，后续类型门掩盖目标平台/pread门缺失。原测试内存AST仅移目标单守卫，各1方法仍PASS，不能授目标拒绝证据。fresh修复作者仅改两测试及本PLAN相应示例，采用不持FD的typed负控哨兵并隔离另一门；不改生产解析器、不关闭哨兵、不认证来源。修后相同内存突变取得平台3/pread1目标`fileno`断言FAIL、0error/skip；真实2方法GREEN/0.001s，新15GREEN/0.030s，旧34GREEN/4.200s。此为测试鉴别力修复，不伪称生产历史bug RED。

修后冻结生产摘要仍`efc18c6902e4df803764d37a294f3ef50bac516e5ae83bab16df8052b5625c86`；测试为`91c295dd51c81fea8ba5b46f37b9fdfbd83787a88995a5aaa3de2ea3fd47ba03`。fresh SPEC实际49方法/4.267s/0F/E/skip，并独立重现两目标突变3/1断言FAIL及原两方法GREEN；SOURCE2为C0/I0/M0，记录旧摘要的Minor已在此明确历史并补修复证据。不同QUALITY与完整preflight仍待，不复用首次被撤销结论。

root完整读取修复，独立相关111方法/5.722s/0F/E/skip；此前未修复候选111/5.706s仅为历史。另从已知旧安装venv的`importlib.metadata.distribution("icode-agent")`定位实际包内helper/manifest，确认非checkout，使用新源码检查器仅检查旧artifact，不执行helper、不重新安装：`/tmp/icode-task4-wheel-7EN8vB/venv/lib/python3.11/site-packages/icode/native/icode-landlock`，x86_64，SHA256 `f7dee11ab61d7b2605368625b0390304dd4fdca2dbb41a9deac22c835ff08ae6`。有限静态子检查PASS、检查后同FD owner仍live，唯一创建者退出确认EBADF。这不是新检查器installed、完整安装消费链或同候选SHA四runner信用。

不同fresh QUALITY完整读两源码、计划、设计及依赖，另实跑49方法/4.267s/0F/E/skip、rc0，最终C0/I0/M0；已核上段历史摘要和修复记录，不复用首次被撤销SPEC。root随后compileall-j1/diffcheck实际exit0。冻结SOURCE2开始唯一一次原完整preflight，session43706，CMAKE_BUILD_PARALLEL_LEVEL=1/MAKEFLAGS=-j1，尚待终态，不提前标成功。

上述session43706于2026-10-12 00:44:16 UTC已实际exit0，密钥扫描、固定vendor完整性、原全量测试三道全部OK。成功stdout未公开全量计数，不猜执行项数或skip；指定相关111/0skip是独立运行的已知计数。root另核site/governance各exit0，SOURCE2摘要与双审冻结相同，旧四路径diff空。最后交付文档复核C0/I0/M1的live状态旧记已同步；最终两轮一致性/精确stage及提交推送另行执行。

【架构级自检报告】（S0a软件分片）

- 语法/编译：真实导入、compileall-j1、diffcheck及原全量守护通过。
- 依赖/调用链：复用旧owner/header；旧四路径未改，尚无生产调用接线。
- 逻辑/边界：有限格式、预算、摘要/快照及负控鉴别力经双审和root111实测。
- 异常处理：普通固定错误、KI/SE原对象及借用owner不关闭已验证。
- 关联模块：新SOURCE2与母设计/计划/研究及旧Windows终态记录同步，无vendor修改。
- 兼容安全：旧ET_DYN/header-only工厂合同保留；无新权限、依赖、ready/selector变化。
- 可运行性：本片软件门通过；旧installed观察仅该产物子项，不授新四runner、来源、S0整体、LA-2或R2/R3。
