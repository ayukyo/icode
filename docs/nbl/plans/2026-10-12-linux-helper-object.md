# Linux Helper Object Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development (recommended) or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立私有 Linux helper 同 FD 核验及独立所有权对象，不启动 helper，不接生产执行链。

**Architecture:** 工厂先核真实宿主与必需打开机制，再以有限读取核 manifest、同 binary FD 的 ELF 与摘要及前后 fstat。owner 仅持有该 FD，明确 active / confirmed-closed / unknown 三态；失败清理遍历所有自有资源，信号优先，未知关闭禁止重试。

**Tech Stack:** Python 3.11+ 标准库、unittest、Linux open/fstat/read/lseek、现有 native_helper 有限 ELF 解析及 tests._support.temp_workspace。

---

## 冻结输入与执行边界

本文件原起草状态为draft，实际进展见完成记录；不得当作 root 全文自审、独立 SPEC→不同 QUALITY 或磁盘 TDD 的替代。设计 [2026-10-12-linux-helper-object-design.md](../specs/2026-10-12-linux-helper-object-design.md) 冻结输入SHA256=`39447b7e8483d464f401606cd47ebdcf1637374f6a4e2dbcbe8104fe134e2e3f`；设计已有独立双审零遗留。三问：真实问题是现有路径验证尚无执行 FD owner；已有 ELF/host 解析可复用；本片生产调用链不接线。计划作者实际 sequential-thinking 1–3 记录需求、方案、风险；root 实施实际119–121另记context。

root于2026-10-11 19:56 UTC全文回读991行原草稿并完成自审：补齐context主体普通错误/cleanup普通错误的同优先级负控，未改实现合同。修后root独立三块AST、骨架1 assertion FAIL/0ERROR→纯内存最终22方法PASS/0skip/F/E（4.190秒），FIFO child注入同一完整候选源码、strip-NONBLOCK真实超时kill/reap，未落盘source/test或执行helper。文档检查两处疑似链接实际为Python原函数表下标调用，已逐处人工核实且AST通过，非Markdown链接，无未解释项。root自审已零遗留，独立PLAN SPEC→不同QUALITY仍待实际完成，不能预记批准。

用户已要求常规推荐方案自主推进 main-only，不再创建 worktree/分支或重复询问。串行不同 writer 与审查者是职责隔离，不允许同一时刻多个写者。计划编制阶段唯一写入本文件，不执行源码、测试文件写入、完整 preflight、原生测试、key 或 Git 写操作。文档中的命令是后续步骤，均未预执行。

| 路径 | 责任 / 唯一写者 |
| --- | --- |
| `tests/test_linux_helper_object.py` | Task 1 唯一测试 writer；完整行为/FD/故障/平台矩阵 |
| `src/icode/linux_helper_object.py` | Task 1 仅最小可导入骨架（如确实需要）；Task 2 不同唯一源码 writer 实现完整 owner |
| `docs/nbl/plans/2026-10-12-linux-helper-object.md` | root 记录实际 RED/GREEN、审查、门禁，不预写通过 |
| `docs/nbl/specs/2026-10-12-linux-helper-object-design.md` | 冻结设计；仅必要的实际验收状态记录 |
| `docs/agent-landscape-live.md` | root 刷新本机制条目及阶段结束观察，不把旧观察日期写成今日上游 HEAD |

源码只新建一个内部模块；不改 native_helper、resolver、PreparedCommand、broker、scope、selector、CLI/MCP、C、vendor 或生产导入。无 workspace/channel FD，不能关闭全部 pass_fds。仅可信 caller，禁止外部 close/dup2 与并发操纵 owned FD；不同对象复用拒绝不误关，同对象复用检测、不可变/ABA、祖先可信、ACL执行能力及 exec 均不承诺。不依赖析构器。

独立只读研究复用冻结设计中 Codex `27065a91ccbf5ba8532844be3777fcf83b77820d` bundled_bwrap 证据及 Apache-2.0；阶段开始/结束各刷新相关 landscape 条目。采纳同打开对象摘要与所有权分账；暂缓 exec/密封；不适配可选摘要、链接打开和关闭全部 pass_fds。机制借鉴、无上游代码复制。此前 man-pages 超时仍无 procfd 加载保证；本片不刷新全部 20 项或伪造新 HEAD。

## Task 1: 唯一测试 writer 建立真实行为 RED

**状态**
- [x] 任务完成（实际证据见完成记录，骨架未作为成品发布）

**Dependencies:** None
**Parallelizable:** No (测试冻结后才允许不同源码 writer 接续；禁止并发写同模块)

- [ ] **Step 1: 回读冻结设计、native_helper 全文、tests._support 与本计划，核当前 main 和精确 dirty 状态。** 使用 `.venv/bin/python`；不读取 key，不改既有文件。若计划/设计有阻断问题先交 root，不自行扩权。

```bash
git branch --show-current
git status --short
sha256sum docs/nbl/specs/2026-10-12-linux-helper-object-design.md
```

预期 main、冻结 hash；其它用户草稿必须保留且不混提交。

- [ ] **Step 2: 若新模块确实不存在，由 Task 1 唯一 writer 用 apply_patch 创建以下完整最小可导入骨架。** 这仅让行为测试可收集，不是生产 stub，不允许生产导入；不修改任何其它源码。若模块已存在，不覆盖并通知 root 核身份。

```python
"""Private helper-object API under construction; no production consumer."""
from __future__ import annotations

import os
from pathlib import Path
import platform
import sys

_ERROR = "Linux helper object is unavailable"


class LinuxHelperObjectError(RuntimeError):
    def __init__(self) -> None:
        super().__init__(_ERROR)


class LinuxHelperObject:
    """Importable type only; the factory does not construct it yet."""


def open_linux_helper_object(binary: Path, manifest: Path) -> LinuxHelperObject:
    return None
```

`None` 是可导入、未实现的行为基线（实现后注解才真实成立），不得写成真实路径 bug 已复现。缺模块、ImportError、AttributeError、收集 ERROR 不授有效 RED。

- [ ] **Step 3: 用 apply_patch 创建 `tests/test_linux_helper_object.py`，完整内容如下。** 每个方法包含实际断言。Linux 正控使用真实临时文件/真实 FD；patch 只改变宿主、OS 故障、读块/预算与观察，不复制假工厂。FIFO 子进程只执行测试 Python，不执行 helper payload。

```python
"""Private same-FD verification/ownership; never executes a helper payload."""
from __future__ import annotations

import copy
import errno
import hashlib
import os
from pathlib import Path
import pickle
import socket
import struct
import subprocess
import sys
import unittest
from unittest.mock import patch

from tests._support import REPO_ROOT, temp_workspace
import icode.linux_helper_object as subject

REAL_OPEN, REAL_CLOSE = os.open, os.close
REAL_FSTAT, REAL_READ, REAL_LSEEK = os.fstat, os.read, os.lseek
ERROR = "Linux helper object is unavailable"


def image(machine: int = 62, tail: bytes = b"private fixture") -> bytes:
    header = bytearray(64)
    header[:7] = b"\x7fELF\x02\x01\x01"
    struct.pack_into("<HHI", header, 16, 2, machine, 1)
    struct.pack_into("<H", header, 52, 64)
    return bytes(header) + tail


def pair(root: Path, data: bytes | None = None, name: str = "helper"):
    data = image() if data is None else data
    binary, manifest = root / name, root / (name + ".sha256")
    binary.write_bytes(data)
    binary.chmod(0o700)
    manifest.write_bytes(hashlib.sha256(data).hexdigest().encode() + b"\n")
    return binary, manifest


class PortablePlatformTests(unittest.TestCase):
    def test_non_linux_rejects_before_host_or_open(self):
        for platform in ("win32", "darwin", "freebsd"):
            with self.subTest(platform=platform), patch.object(
                subject.sys, "platform", platform
            ), patch.object(subject.platform, "machine") as host, patch.object(
                subject.os, "open"
            ) as opened:
                with self.assertRaises(subject.LinuxHelperObjectError) as caught:
                    subject.open_linux_helper_object(Path("secret-path"), Path("manifest"))
                self.assertEqual(str(caught.exception), ERROR)
                self.assertIsNone(caught.exception.__cause__)
                host.assert_not_called()
                opened.assert_not_called()

    def test_bad_host_and_host_faults_reject_before_open(self):
        for answer in ("i686", "riscv64", "", None, OSError("private-host")):
            with self.subTest(answer=type(answer).__name__), patch.object(
                subject.sys, "platform", "linux"
            ), patch.object(subject.platform, "machine", **(
                {"side_effect": answer} if isinstance(answer, Exception)
                else {"return_value": answer}
            )), patch.object(subject.os, "open") as opened:
                with self.assertRaises(subject.LinuxHelperObjectError) as caught:
                    subject.open_linux_helper_object(Path("private"), Path("private"))
                self.assertEqual(str(caught.exception), ERROR)
                self.assertIsNone(caught.exception.__cause__)
                opened.assert_not_called()

    def test_host_interrupts_keep_identity(self):
        for signal in (KeyboardInterrupt("host"), SystemExit(17)):
            with self.subTest(signal=type(signal).__name__), patch.object(
                subject.sys, "platform", "linux"
            ), patch.object(subject.platform, "machine", side_effect=signal), patch.object(
                subject.os, "open"
            ) as opened:
                with self.assertRaises(type(signal)) as caught:
                    subject.open_linux_helper_object(Path("private"), Path("private"))
                self.assertIs(caught.exception, signal)
                opened.assert_not_called()


@unittest.skipUnless(sys.platform.startswith("linux"), "real Linux FD cases")
class LinuxHelperObjectTests(unittest.TestCase):
    def setUp(self):
        self.host = patch.object(subject.platform, "machine", return_value="x86_64")
        self.host.start()
        self.addCleanup(self.host.stop)

    def assert_closed(self, descriptor):
        with self.assertRaises(OSError) as caught:
            REAL_FSTAT(descriptor)
        self.assertEqual(caught.exception.errno, errno.EBADF)

    def reject(self, binary, manifest):
        with self.assertRaises(subject.LinuxHelperObjectError) as caught:
            subject.open_linux_helper_object(binary, manifest)
        self.assertEqual(str(caught.exception), ERROR)
        self.assertIsNone(caught.exception.__cause__)
        self.assertTrue(caught.exception.__suppress_context__)

    def test_real_regular_same_fd_metadata_offset_and_context(self):
        with temp_workspace() as root:
            binary, manifest = pair(root)
            reads, opens = [], []
            def opened(path, flags):
                fd = REAL_OPEN(path, flags)
                opens.append((Path(path), fd, flags))
                return fd
            def read(fd, size):
                reads.append((fd, REAL_LSEEK(fd, 0, os.SEEK_CUR), size))
                return REAL_READ(fd, size)
            with patch.object(subject.os, "open", side_effect=opened), patch.object(
                subject.os, "read", side_effect=read
            ):
                owner = subject.open_linux_helper_object(binary, manifest)
            self.assertIsInstance(owner, subject.LinuxHelperObject)
            with owner as entered:
                self.assertIs(entered, owner)
                fd = owner.fileno()
                self.assertFalse(os.get_inheritable(fd))
                self.assertEqual(owner.architecture, "x86_64")
                self.assertEqual(owner.sha256, hashlib.sha256(binary.read_bytes()).hexdigest())
                self.assertEqual([path for path, _, _ in opens], [binary, manifest])
                required = os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
                self.assertTrue(all(flags & required == required for _, _, flags in opens))
                binary_reads = [entry for entry in reads if entry[0] == fd]
                self.assertEqual(binary_reads[0][1:], (0, 64))
                self.assertEqual(binary_reads[1][1], 0)
                self.assertLessEqual(max(size for _, _, size in binary_reads), 64 * 1024)
                self.assert_closed(opens[1][1])
            self.assert_closed(fd)
            owner.close()
            with self.assertRaises(subject.LinuxHelperObjectError):
                owner.fileno()

    def test_supported_host_aliases_and_architecture_mismatch(self):
        for host, machine, architecture in (("x86_64", 62, "x86_64"),
                                             ("aarch64", 183, "arm64"),
                                             ("arm64", 183, "arm64")):
            with self.subTest(host=host), temp_workspace() as root, patch.object(
                subject.platform, "machine", return_value=host
            ):
                binary, manifest = pair(root, image(machine))
                with subject.open_linux_helper_object(binary, manifest) as owner:
                    self.assertEqual(owner.architecture, architecture)
                binary, manifest = pair(root, image(183 if machine == 62 else 62))
                self.reject(binary, manifest)

    def test_missing_required_flags_reject_before_open(self):
        for flag in ("O_NOFOLLOW", "O_CLOEXEC", "O_NONBLOCK"):
            with self.subTest(flag=flag), temp_workspace() as root:
                binary, manifest = pair(root)
                value = getattr(subject.os, flag)
                try:
                    delattr(subject.os, flag)
                    with patch.object(subject.os, "open") as opened:
                        self.reject(binary, manifest)
                        opened.assert_not_called()
                finally:
                    setattr(subject.os, flag, value)
                with patch.object(subject.os, flag, 0), patch.object(subject.os, "open") as opened:
                    self.reject(binary, manifest)
                    opened.assert_not_called()

    def test_manifest_grammar_limit_and_short_reads(self):
        with temp_workspace() as root:
            binary, manifest = pair(root)
            digest = hashlib.sha256(binary.read_bytes()).hexdigest().encode()
            for text in (digest, digest + b"\n"):
                manifest.write_bytes(text)
                with patch.object(subject.os, "read", side_effect=lambda fd, count:
                                  REAL_READ(fd, min(count, 3))):
                    with subject.open_linux_helper_object(binary, manifest) as owner:
                        self.assertGreaterEqual(owner.fileno(), 0)
            for text in (b"", digest.upper(), digest + b"\r\n", digest + b"\n\n",
                         digest + b"x", b" " + digest, b"\xff" * 64, b"a" * 4096):
                with self.subTest(length=len(text)):
                    manifest.write_bytes(text)
                    seen = []
                    def read(fd, count):
                        result = REAL_READ(fd, count)
                        seen.append((fd, len(result), count))
                        return result
                    with patch.object(subject.os, "read", side_effect=read):
                        self.reject(binary, manifest)
                    self.assertLessEqual(sum(size for _, size, _ in seen), 66)

    def test_missing_paths_wrong_header_digest_and_execute_mode(self):
        with temp_workspace() as root:
            binary, manifest = pair(root)
            self.reject(root / "absent", manifest)
            self.reject(binary, root / "absent")
            manifest.write_bytes(b"0" * 64 + b"\n")
            self.reject(binary, manifest)
            for data in (b"\x7fELF", image(3), b"not-elf" + b"x" * 80):
                binary, manifest = pair(root, data)
                self.reject(binary, manifest)
            binary, manifest = pair(root)
            binary.chmod(0o600)
            self.reject(binary, manifest)

    def test_directories_sockets_soft_and_hard_links_in_both_roles(self):
        for role in (0, 1):
            for kind in ("directory", "socket", "symlink", "hardlink"):
                with self.subTest(role=role, kind=kind), temp_workspace() as root:
                    paths = list(pair(root))
                    target = paths[role]
                    saved = root / "saved"
                    target.rename(saved)
                    endpoint = None
                    try:
                        if kind == "directory":
                            target.mkdir()
                        elif kind == "socket":
                            endpoint = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                            endpoint.bind(str(target))
                        elif kind == "symlink":
                            target.symlink_to(saved)
                        else:
                            os.link(saved, target)
                        self.reject(*paths)
                    finally:
                        if endpoint is not None:
                            endpoint.close()

    def _fifo_child(self, binary, manifest, remove_nonblock):
        script = r'''
import os, platform, sys
from pathlib import Path
from unittest.mock import patch
import icode.linux_helper_object as subject
real_open = os.open
def opened(path, flags):
    return real_open(path, flags & ~os.O_NONBLOCK if sys.argv[3] == "strip" else flags)
with patch.object(subject.platform, "machine", return_value="x86_64"), patch.object(subject.os, "open", side_effect=opened):
    try:
        subject.open_linux_helper_object(Path(sys.argv[1]), Path(sys.argv[2]))
    except subject.LinuxHelperObjectError:
        print("rejected", flush=True)
    else:
        raise AssertionError("FIFO accepted")
'''
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(REPO_ROOT / "src")
        process = subprocess.Popen(
            [sys.executable, "-c", script, str(binary), str(manifest),
             "strip" if remove_nonblock else "keep"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=environment,
        )
        try:
            output, errors = process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=2)
            self.assertIsNotNone(process.returncode)
            raise
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=2)
        return process.returncode, output, errors

    def test_real_fifo_without_writer_and_timeout_negative_control(self):
        for role in (0, 1):
            with self.subTest(role=role), temp_workspace() as root:
                paths = list(pair(root))
                paths[role].unlink()
                os.mkfifo(paths[role], 0o600)
                code, output, errors = self._fifo_child(*paths, False)
                self.assertEqual((code, output, errors), (0, "rejected\n", ""))
                with self.assertRaises(subprocess.TimeoutExpired):
                    self._fifo_child(*paths, True)

    def test_size_limit_exact_boundary_and_continuous_growth_are_bounded(self):
        self.assertEqual(subject._BINARY_LIMIT, 64 * 1024 * 1024)
        self.assertEqual(subject._READ_CHUNK, 64 * 1024)
        with temp_workspace() as root:
            binary, manifest = pair(root, image(tail=b"x" * 16))
            with patch.object(subject, "_BINARY_LIMIT", 80), patch.object(subject, "_READ_CHUNK", 7):
                with subject.open_linux_helper_object(binary, manifest) as owner:
                    self.assertGreaterEqual(owner.fileno(), 0)
                binary, manifest = pair(root, image(tail=b"x" * 17))
                self.reject(binary, manifest)
                binary, manifest = pair(root, image(tail=b"x" * 16))
                calls, total = [], []
                def growing(fd, count):
                    calls.append(count)
                    if REAL_FSTAT(fd).st_ino == binary.stat().st_ino:
                        with binary.open("ab") as stream:
                            stream.write(b"z" * 7)
                    result = REAL_READ(fd, count)
                    total.append(len(result))
                    return result
                with patch.object(subject.os, "read", side_effect=growing):
                    self.reject(binary, manifest)
                self.assertLessEqual(len(calls), 30)
                self.assertLessEqual(max(calls), 66)
                self.assertLessEqual(sum(total), 65 + 64 + 81)

    def test_visible_fstat_drift_rejects_even_with_matching_digest(self):
        for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns"):
            with self.subTest(field=field), temp_workspace() as root:
                binary, manifest = pair(root)
                binary_calls = 0
                inode = binary.stat().st_ino
                def status(fd):
                    nonlocal binary_calls
                    actual = REAL_FSTAT(fd)
                    if actual.st_ino == inode:
                        binary_calls += 1
                        if binary_calls == 2:
                            class Changed:
                                def __getattr__(self, name):
                                    value = getattr(actual, name)
                                    return value + 1 if name == field else value
                            return Changed()
                    return actual
                with patch.object(subject.os, "fstat", side_effect=status):
                    self.reject(binary, manifest)

    def test_pathname_replacement_after_open_does_not_change_held_reads(self):
        with temp_workspace() as root:
            binary, manifest = pair(root)
            expected = binary.read_bytes()
            saved = root / "old"
            # Replacement before binary's initial fstat avoids claiming ctime stability across rename.
            def opened(path, flags):
                fd = REAL_OPEN(path, flags)
                if Path(path) == binary:
                    binary.rename(saved)
                    binary.write_bytes(b"untrusted pathname replacement")
                return fd
            with patch.object(subject.os, "open", side_effect=opened):
                owner = subject.open_linux_helper_object(binary, manifest)
            with owner:
                fd = owner.fileno()
                self.assertEqual(owner.sha256, hashlib.sha256(expected).hexdigest())
                saved.unlink()
                REAL_LSEEK(fd, 0, os.SEEK_SET)
                self.assertEqual(REAL_READ(fd, 4096), expected)
                self.assertEqual(owner.fileno(), fd)
                self.assertEqual(REAL_FSTAT(fd).st_nlink, 0)

    def test_two_owners_are_independent(self):
        with temp_workspace() as root:
            binary, manifest = pair(root)
            first = subject.open_linux_helper_object(binary, manifest)
            second = subject.open_linux_helper_object(binary, manifest)
            try:
                a, b = first.fileno(), second.fileno()
                self.assertNotEqual(a, b)
                first.close()
                self.assert_closed(a)
                self.assertEqual(second.fileno(), b)
            finally:
                first.close()
                second.close()

    def test_copy_deepcopy_pickle_do_not_transfer_close_responsibility(self):
        with temp_workspace() as root:
            binary, manifest = pair(root)
            with subject.open_linux_helper_object(binary, manifest) as owner:
                fd = owner.fileno()
                for operation in (copy.copy, copy.deepcopy, pickle.dumps):
                    with self.subTest(operation=operation.__name__):
                        with self.assertRaises(subject.LinuxHelperObjectError) as caught:
                            operation(owner)
                        self.assertEqual(str(caught.exception), ERROR)
                        self.assertEqual(owner.fileno(), fd)

    def test_external_different_object_reuse_is_not_closed(self):
        with temp_workspace() as root:
            binary, manifest = pair(root)
            owner = subject.open_linux_helper_object(binary, manifest)
            fd = owner.fileno()
            other = root / "other"
            other.write_bytes(b"unrelated")
            replacement = REAL_OPEN(other, os.O_RDONLY)
            try:
                os.dup2(replacement, fd)
                with self.assertRaises(subject.LinuxHelperObjectError):
                    owner.fileno()
                with patch.object(subject.os, "close") as closed:
                    with self.assertRaises(subject.LinuxHelperObjectError):
                        owner.close()
                    with self.assertRaises(subject.LinuxHelperObjectError):
                        owner.close()
                    closed.assert_not_called()
                self.assertEqual(REAL_READ(fd, 64), b"unrelated")
            finally:
                REAL_CLOSE(fd)
                REAL_CLOSE(replacement)

    def test_close_failure_unknown_never_retries_even_if_fd_still_open(self):
        for error in (OSError("private-close"), KeyboardInterrupt("close"), SystemExit(19)):
            with self.subTest(error=type(error).__name__), temp_workspace() as root:
                binary, manifest = pair(root)
                owner = subject.open_linux_helper_object(binary, manifest)
                fd = owner.fileno()
                try:
                    with patch.object(subject.os, "close", side_effect=error) as closed:
                        with self.assertRaises(type(error) if not isinstance(error, Exception)
                                               else subject.LinuxHelperObjectError) as caught:
                            owner.close()
                        if not isinstance(error, Exception):
                            self.assertIs(caught.exception, error)
                        else:
                            self.assertEqual(str(caught.exception), ERROR)
                        with self.assertRaises(subject.LinuxHelperObjectError):
                            owner.close()
                        closed.assert_called_once_with(fd)
                    self.assertEqual(REAL_FSTAT(fd).st_ino, binary.stat().st_ino)
                    with self.assertRaises(subject.LinuxHelperObjectError):
                        owner.fileno()
                finally:
                    REAL_CLOSE(fd)

    def test_close_fstat_failure_does_not_guess_or_retry(self):
        with temp_workspace() as root:
            binary, manifest = pair(root)
            owner = subject.open_linux_helper_object(binary, manifest)
            fd = owner.fileno()
            try:
                with patch.object(subject.os, "fstat", side_effect=OSError("private")), patch.object(
                    subject.os, "close"
                ) as closed:
                    with self.assertRaises(subject.LinuxHelperObjectError):
                        owner.close()
                    with self.assertRaises(subject.LinuxHelperObjectError):
                        owner.close()
                    closed.assert_not_called()
                self.assertGreaterEqual(REAL_FSTAT(fd).st_ino, 0)
            finally:
                REAL_CLOSE(fd)

    def test_confirmed_close_and_enter_are_closed_under_context_errors(self):
        for error in (ValueError("body"), KeyboardInterrupt("body"), SystemExit(20)):
            with self.subTest(error=type(error).__name__), temp_workspace() as root:
                binary, manifest = pair(root)
                owner = subject.open_linux_helper_object(binary, manifest)
                fd = owner.fileno()
                with self.assertRaises(type(error)) as caught:
                    with owner:
                        raise error
                self.assertIs(caught.exception, error)
                self.assert_closed(fd)
                with patch.object(subject.os, "close") as closed:
                    owner.close()
                    owner.close()
                    closed.assert_not_called()
                with self.assertRaises(subject.LinuxHelperObjectError):
                    owner.__enter__()

    def test_context_cleanup_interrupt_priority(self):
        for body, cleanup in ((ValueError("body"), OSError("cleanup")),
                              (KeyboardInterrupt("body"), OSError("cleanup")),
                              (SystemExit(21), KeyboardInterrupt("cleanup")),
                              (ValueError("body"), KeyboardInterrupt("cleanup")),
                              (ValueError("body"), SystemExit(22))):
            with self.subTest(body=type(body).__name__, cleanup=type(cleanup).__name__), temp_workspace() as root:
                binary, manifest = pair(root)
                owner = subject.open_linux_helper_object(binary, manifest)
                fd = owner.fileno()
                def closing(descriptor):
                    REAL_CLOSE(descriptor)
                    raise cleanup
                selected = (body if not isinstance(body, Exception)
                            or isinstance(cleanup, Exception) else cleanup)
                with patch.object(subject.os, "close", side_effect=closing):
                    with self.assertRaises(type(selected)) as caught:
                        with owner:
                            raise body
                self.assertIs(caught.exception, selected)
                self.assert_closed(fd)
                with self.assertRaises(subject.LinuxHelperObjectError):
                    owner.close()

    def _factory_trace(self, binary, manifest, inject=None):
        originals = {"open": REAL_OPEN, "fstat": REAL_FSTAT, "read": REAL_READ,
                     "lseek": REAL_LSEEK, "close": REAL_CLOSE}
        events, owned, closes = [], [], []
        from contextlib import ExitStack
        def wrap(name):
            def operation(*args):
                event = (name, sum(old[0] == name for old in events) + 1)
                events.append(event)
                if name == "close":
                    closes.append(args[0])
                if inject is not None and event == inject[0]:
                    if name == "close":
                        originals[name](*args)
                    raise inject[1]
                answer = originals[name](*args)
                if name == "open":
                    owned.append(answer)
                return answer
            return operation
        with ExitStack() as stack:
            for name in originals:
                stack.enter_context(patch.object(subject.os, name, side_effect=wrap(name)))
            try:
                owner = subject.open_linux_helper_object(binary, manifest)
            except BaseException as error:
                return events, owned, closes, error
        owner.close()
        return events, owned, closes, None

    def test_every_factory_os_stage_fault_and_signal_cleans_actual_fds(self):
        with temp_workspace() as root:
            binary, manifest = pair(root)
            healthy, descriptors, _, error = self._factory_trace(binary, manifest)
            self.assertIsNone(error)
            self.assertEqual(set(name for name, _ in healthy), {"open", "fstat", "read", "lseek", "close"})
            for descriptor in descriptors:
                self.assert_closed(descriptor)
            for event in healthy:
                for fault in (OSError("private-os-stage"), KeyboardInterrupt("stage"), SystemExit(23)):
                    with self.subTest(event=event, fault=type(fault).__name__):
                        _, descriptors, closes, error = self._factory_trace(binary, manifest, (event, fault))
                        if isinstance(fault, Exception):
                            self.assertIsInstance(error, subject.LinuxHelperObjectError)
                            self.assertEqual(str(error), ERROR)
                            self.assertIsNone(error.__cause__)
                            self.assertTrue(error.__suppress_context__)
                        else:
                            self.assertIs(error, fault)
                        self.assertEqual(len(closes), len(set(closes)))
                        for descriptor in descriptors:
                            self.assert_closed(descriptor)

    def test_factory_cleanup_priority_and_all_resources_attempted(self):
        for primary, cleanup in ((OSError("read-private"), KeyboardInterrupt("cleanup")),
                                 (OSError("read-private"), SystemExit(24)),
                                 (KeyboardInterrupt("read"), OSError("close-private")),
                                 (SystemExit(25), KeyboardInterrupt("cleanup"))):
            with self.subTest(primary=type(primary).__name__, cleanup=type(cleanup).__name__), temp_workspace() as root:
                binary, manifest = pair(root)
                acquired, closed = [], []
                def opened(path, flags):
                    fd = REAL_OPEN(path, flags)
                    acquired.append(fd)
                    return fd
                def closing(fd):
                    closed.append(fd)
                    REAL_CLOSE(fd)
                    raise cleanup
                selected = primary if not isinstance(primary, Exception) else cleanup
                with patch.object(subject.os, "open", side_effect=opened), patch.object(
                    subject.os, "read", side_effect=primary
                ), patch.object(subject.os, "close", side_effect=closing):
                    with self.assertRaises(type(selected)) as caught:
                        subject.open_linux_helper_object(binary, manifest)
                self.assertIs(caught.exception, selected)
                self.assertEqual(set(closed), set(acquired))
                self.assertEqual(len(closed), len(acquired))
                for fd in acquired:
                    self.assert_closed(fd)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 4: 先只跑真实正控取得行为 assertion RED / 0 ERROR，再尝试完整测试收集。** Task 1 不授全套 RED 信用：骨架缺失辅助属性造成的 ERROR 要明确分账；有效 RED 必须下面单例的 `assertIsInstance(None, LinuxHelperObject)` 实际 FAIL，收集及方法本身 0 ERROR，不能省略骨架直接计缺模块。

```bash
.venv/bin/python -m unittest tests.test_linux_helper_object.LinuxHelperObjectTests.test_real_regular_same_fd_metadata_offset_and_context -v
.venv/bin/python -m unittest tests.test_linux_helper_object -v
sha256sum tests/test_linux_helper_object.py src/icode/linux_helper_object.py
```

预期 Linux 首条 1 test / 1 assertion FAIL / 0 ERROR；第二条用于掌握收集/未实现缺口，允许骨架 ERROR 但不得计有效 RED。非 Linux 首条 skip 不构成 RED，需在真实 Linux 落地该单例后才接续。记录实际输出、有效断言、骨架/测试 hash，然后 writer 停止，交不同 Task 2 writer。此阶段不提交未实现骨架。

## Task 2: 不同唯一源码 writer 实现 owner

**状态**
- [x] 任务完成（writer停止，source/test冻结，完整门及发布归Task3）

**Dependencies:** Task 1
**Parallelizable:** No (依赖测试冻结和实际行为 RED；只能单一源码 writer)

- [ ] **Step 1: 回读全部冻结输入，独立复现 Task 1 同一单例 assertion RED。** 确认测试 hash 未变，不修改新测试、旧生产或 vendor。未复现有效 RED 不实现。

- [ ] **Step 2: 用 apply_patch 将 `src/icode/linux_helper_object.py` 完整替换为以下代码。** 工厂仅输入两个 Path，不接受 caller 架构/摘要，复用现有解析；有限读循环每轮预算递减，不用 read_text/file_digest 或路径重开。manifest close 先摘资源再执行，未知结果不重试；工厂其它资源仍遍历回收。

```python
"""Private Linux helper verification/FD ownership, never an execution grant.

Trusted callers must not externally close/dup2 the owned FD or concurrently
mutate owner state. Identity checks detect different-object reuse, not reuse of
the same object. No immutable-content, ancestor-trust or publisher claim.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import platform
import re
import stat
import sys

from .native_helper import linux_arch_from_machine, linux_elf_architecture

_ERROR = "Linux helper object is unavailable"
_MANIFEST_LIMIT = 66
_BINARY_LIMIT = 64 * 1024 * 1024
_READ_CHUNK = 64 * 1024
_HEADER_SIZE = 64
_MANIFEST = re.compile(rb"[0-9a-f]{64}\n?\Z")


class LinuxHelperObjectError(RuntimeError):
    """An input-free failure of the private helper-object contract."""

    def __init__(self) -> None:
        super().__init__(_ERROR)


def _select(first: BaseException | None, following: BaseException) -> BaseException:
    # Match existing cleanup priority without importing the supervision chain.
    if first is None or (isinstance(first, Exception) and not isinstance(following, Exception)):
        return following
    return first


def _raise_fixed_or_signal(error: BaseException) -> None:
    if not isinstance(error, Exception):
        raise error
    raise LinuxHelperObjectError() from None


def _identity(status) -> tuple[int, int]:
    return status.st_dev, status.st_ino


def _snapshot(status) -> tuple[int, int, int, int, int]:
    return (*_identity(status), status.st_size, status.st_mtime_ns, status.st_ctime_ns)


def _regular(status, *, executable: bool) -> None:
    if (not stat.S_ISREG(status.st_mode) or status.st_nlink != 1
            or (executable and not status.st_mode & 0o111)):
        raise LinuxHelperObjectError()


def _read_prefix(fd: int, limit: int) -> bytes:
    result = bytearray()
    while len(result) < limit:
        chunk = os.read(fd, limit - len(result))
        if not chunk:
            break
        result.extend(chunk)
    return bytes(result)


class LinuxHelperObject:
    """Explicit owner; factory verification, not constructor identity authentication."""

    def __init__(self, fd: int, identity: tuple[int, int], architecture: str, digest: str) -> None:
        self._fd = fd
        self._identity = identity
        self._architecture = architecture
        self._sha256 = digest
        self._state = "active"

    @property
    def architecture(self) -> str:
        return self._architecture

    @property
    def sha256(self) -> str:
        return self._sha256

    def fileno(self) -> int:
        try:
            if self._state != "active":
                raise LinuxHelperObjectError()
            status = os.fstat(self._fd)
            # After acquisition unlink/rename may change nlink/ctime, not identity.
            if not stat.S_ISREG(status.st_mode) or _identity(status) != self._identity:
                raise LinuxHelperObjectError()
            return self._fd
        except BaseException as error:
            _raise_fixed_or_signal(error)

    def close(self) -> None:
        if self._state == "closed":
            return
        if self._state != "active":
            raise LinuxHelperObjectError()
        try:
            fd = self.fileno()
            # An exception from close may mean the integer has already been reused.
            self._state = "unknown"
            os.close(fd)
        except BaseException as error:
            self._state = "unknown"
            _raise_fixed_or_signal(error)
        self._state = "closed"

    def __enter__(self) -> LinuxHelperObject:
        self.fileno()
        return self

    def __copy__(self):
        raise LinuxHelperObjectError()

    def __deepcopy__(self, memo):
        raise LinuxHelperObjectError()

    def __reduce_ex__(self, protocol):
        raise LinuxHelperObjectError()

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        try:
            self.close()
        except BaseException as cleanup_error:
            selected = _select(exc_value, cleanup_error)
            if selected is cleanup_error:
                raise
        return False


def open_linux_helper_object(binary: Path, manifest: Path) -> LinuxHelperObject:
    """Verify one opened binary and return its independent non-executing owner."""
    owned: list[int] = []
    try:
        # True host checks and required mechanisms precede all filesystem access.
        if not sys.platform.startswith("linux"):
            raise LinuxHelperObjectError()
        architecture = linux_arch_from_machine(platform.machine())
        flags = os.O_RDONLY
        for name in ("O_CLOEXEC", "O_NOFOLLOW", "O_NONBLOCK"):
            value = getattr(os, name, None)
            if type(value) is not int or value <= 0:
                raise LinuxHelperObjectError()
            flags |= value

        binary_fd = os.open(binary, flags)
        owned.append(binary_fd)
        before = os.fstat(binary_fd)
        _regular(before, executable=True)
        if before.st_size < _HEADER_SIZE or before.st_size > _BINARY_LIMIT:
            raise LinuxHelperObjectError()

        manifest_fd = os.open(manifest, flags)
        owned.append(manifest_fd)
        _regular(os.fstat(manifest_fd), executable=False)
        expected = _read_prefix(manifest_fd, _MANIFEST_LIMIT)
        if _MANIFEST.fullmatch(expected) is None:
            raise LinuxHelperObjectError()
        # Relinquish retry responsibility before close, including close exceptions.
        owned.remove(manifest_fd)
        os.close(manifest_fd)

        os.lseek(binary_fd, 0, os.SEEK_SET)
        header = _read_prefix(binary_fd, _HEADER_SIZE)
        if linux_elf_architecture(header) != architecture:
            raise LinuxHelperObjectError()
        os.lseek(binary_fd, 0, os.SEEK_SET)
        digest = hashlib.sha256()
        total = 0
        while total <= _BINARY_LIMIT:
            chunk = os.read(binary_fd, min(_READ_CHUNK, _BINARY_LIMIT + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > _BINARY_LIMIT:
                raise LinuxHelperObjectError()
            digest.update(chunk)
        after = os.fstat(binary_fd)
        _regular(after, executable=True)
        actual = digest.hexdigest()
        if (_snapshot(before) != _snapshot(after) or total != after.st_size
                or actual.encode("ascii") != expected.rstrip(b"\n")):
            raise LinuxHelperObjectError()
        owner = LinuxHelperObject(binary_fd, _identity(after), architecture, actual)
        owned.remove(binary_fd)
        return owner
    except BaseException as error:
        selected = error
        # Drain every still-owned entry once even if cleanup raises a signal.
        while owned:
            fd = owned.pop()
            try:
                os.close(fd)
            except BaseException as cleanup_error:
                selected = _select(selected, cleanup_error)
        _raise_fixed_or_signal(selected)
```

本片不承诺任意异步字节码打断/open 返回登记间的原子所有权；测试证明命名 OS 阶段故障与 KI/SE、正常同步交接，不把 Python 行窗口当内核信号保证。未知 close 的实际 FD 可能仍开，模块不得 retry；测试用保存的真实 close 在 finally 回收，生产需可信 caller 遵守合同。

- [ ] **Step 3: 跑新套件并核 exact FD cleanup/输出，修复时只改唯一新源码。** 测试暴露计划错误需要 root 核新候选后由原测试 writer 修改，避免源码 writer 改弱断言。

```bash
.venv/bin/python -m unittest tests.test_linux_helper_object -v
.venv/bin/python -m unittest tests.test_linux_helper_object tests.test_linux_helper_elf tests.test_native_helper -v
.venv/bin/python -m compileall -q -j1 src/icode/linux_helper_object.py tests/test_linux_helper_object.py
sha256sum src/icode/linux_helper_object.py tests/test_linux_helper_object.py
git diff --check
```

预期所有当前 Linux 新方法 PASS/0 ERROR；PortablePlatformTests 在其它平台仍实跑，Linux 类 skips 单列，不能把 skip 当 Linux 信用。故障矩阵每个实际 healthy trace 的 open/fstat/read/lseek/manifest-close ordinal 均核普通错误及 KI/SE；真实 FD 用保存的 fstat 核 EBADF，manifest-close 注入先真实关再抛错，禁止二次 close。owner unknown-close 另用仍开 FD 验不 retry，并由测试真实 finally 回收。不授 helper 执行、安装包或 x64/ARM64 真实成品信用。

- [ ] **Step 4: writer 做七维自审并停止。** 交 root 全文、source/test hash、真实 RED/GREEN/计数、FIFO 两角色保护负控及故障矩阵结果；不提交、不 full preflight、不读 key、不执行 native/helper。

## Task 3: 独立双审、root 完整门、main 精确发布

**状态**
- [ ] 任务完成

**Dependencies:** Task 1, Task 2
**Parallelizable:** No (源码/测试冻结；先 root 全文回读及独立 SPEC，后不同 QUALITY，再完整门)

- [ ] **Step 1: root 完整回读两新文件和计划/设计，独立重跑关联并检查未接生产。** 不用 writer 自审替代 CODE review。fresh SPEC 审查者只读冻结源/test/设计/计划，运行 focused，不改文件；SPEC 零遗留后 fresh、不同 QUALITY 审查者独立复核，运行同关联及 FIFO/故障矩阵。任何 C/I/M 遗留交唯一 writer 修复、恢复 RED→GREEN并重做双审；root记录候选hash及真实终态。

```bash
.venv/bin/python -m unittest tests.test_linux_helper_object tests.test_linux_helper_elf tests.test_native_helper -v
.venv/bin/python -m unittest tests.test_isolation.TestSandboxWrapping.test_landlock_策略路径逐次校验助手摘要 -v
rg -n 'linux_helper_object|open_linux_helper_object|LinuxHelperObject' src scripts tests
git diff -- src/icode/native_helper.py src/icode/execution_broker.py src/icode/linux_task_scope.py
sha256sum src/icode/linux_helper_object.py tests/test_linux_helper_object.py
```

预期新模块只被专用新测试导入，不改现有生产源。`test_native_helper` 同时覆盖 generic 与 Windows 原回归；第二条精确方法已全文回读，造真实显式脚本而只 prepare/wrap，不执行 helper payload，Linux预期1PASS。记录实际命令/数量及平台 skip，不能把非 Linux skip 或假 fixture 当原生验证。其它既有 isolation 回归由 root 完整门覆盖。

- [ ] **Step 2: root 完成阶段结束 landscape 记录及三文档一致性检查。** 仅刷新相关条目并注明采纳/暂缓/不适配、实际观察日期、固定链接/版本、许可/安全/兼容影响与本片验收；完整 20 观察名单按排期检查，不声称都已今日刷新。设计继续保留未实施历史，不把“草稿/待验收”的时间窗口删除。文档记录不得声称 immutable、祖先可信、model 前 prepare 固定、原生 dispatch 或产品 ready。

```bash
.venv/bin/python scripts/check_governance.py
.venv/bin/python scripts/check_agent_landscape.py
.venv/bin/python /home/orbbec/.agents/skills/doc-contract-consistency-audit/scripts/check_consistency.py docs/nbl/plans/2026-10-12-linux-helper-object.md docs/nbl/specs/2026-10-12-linux-helper-object-design.md docs/agent-landscape-live.md --counts
```

预期治理/排期exit0，文档检查零未解释疑似项；源代码块是演练/后续实施候选，不能将其中的示例状态当已完成。有真实冲突先改唯一文档候选再检查，排期或链接失败不可跳过。

- [ ] **Step 3: root fresh 完整 preflight 三道及串行编译，未通过不得发布。** 这不是计划作者演练；限原生编译并发 j1，不访问/展示 key 正文，执行已有 secrets guard 是扫描门。

```bash
CMAKE_BUILD_PARALLEL_LEVEL=1 MAKEFLAGS=-j1 .venv/bin/python scripts/preflight.py
.venv/bin/python -m compileall -q -j1 src scripts tests
.venv/bin/python scripts/check_site.py
git diff --check
```

预期完整 preflight exit0，secrets/submodule/tests 三道全部通过；`--only tests`、focused、旧 SHA 门或已中断 full 不能替代。成功脚本若无总数不推算；原生旧 tests 的运行/skip 分账，不提升本对象为启动验证。需保留实际完整门进程终态与 source/test hash。语义变更后重跑完整门；仅实际结果文档记录追加可按现有 root 规则收尾。

- [ ] **Step 4: root fresh 发布前两道与精确索引守护，逐条成功才 commit/push。** 唯一允许以下五路径，所有未请求草稿保留。若 paths 已 staged 的其它内容存在先停止而非自动清理用户索引；index 必须逐字节等于审查后的磁盘候选。检查 main 与 remote 后才发布，不把授权 main-only 解读成危险删除/回退授权。

```bash
.venv/bin/python scripts/preflight.py --only secrets
.venv/bin/python scripts/preflight.py --only submodule
git branch --show-current
git diff --cached --name-only
git add -f -- src/icode/linux_helper_object.py tests/test_linux_helper_object.py docs/nbl/plans/2026-10-12-linux-helper-object.md docs/nbl/specs/2026-10-12-linux-helper-object-design.md docs/agent-landscape-live.md
git diff --cached --name-only
git diff --cached --check
git diff --exit-code -- src/icode/linux_helper_object.py tests/test_linux_helper_object.py docs/nbl/plans/2026-10-12-linux-helper-object.md docs/nbl/specs/2026-10-12-linux-helper-object-design.md docs/agent-landscape-live.md
git commit -m 'feat(linux): add verified helper object ownership'
git push origin main
git rev-parse HEAD
git ls-remote origin refs/heads/main
```

每条命令独立执行/检查 exit；发布前 cached 五路径名单恰好匹配（不得以模糊目录 add 代替）。最后磁盘/索引 diff0、cached格式0，未通过不继续；commit成功后再push，push成功后核远端main同SHA。若某冻结文档本已在 HEAD 且内容无需改，必须在提交前核发布合同并记录为何改变名单，不能伪造五路径changed；本计划默认本片设计/计划新文件和landscape实际更新。报告实际 SHA、守护、CI终态，不预填成功。

## 自审与验收映射（计划 draft）

| 设计合同 | 完整实现 / 实际验收入口 |
| --- | --- |
| Linux/真实host前拒、flag缺失无降级 | 工厂开头；PortablePlatformTests三方法、missing_required_flags |
| regular、单link、execute mode；目录/socket/links/FIFO | `_regular`；both_roles、wrong_header_digest_mode、真实FIFO双角色timeout负控 |
| manifest66、64lowercase可选LF、短读 | `_read_prefix`/regex；manifest_grammar_limit_and_short_reads |
| 同FD offset0 header/digest、64MiB/64KiB、增长有限 | 工厂两个lseek/有限digest；same_fd、size_limit/growth |
| 前后 dev/ino/size/mtime_ns/ctime_ns、可见漂移 | `_snapshot`；visible_fstat_drift（五字段） |
| held FD path replace/unlink、不复开 | owner identity；pathname_replacement、nlink0正控 |
| 独立owner/fileno/close/context、confirmed幂等 | two_owners、context_errors、same_fd |
| 外部不同对象复用不误关、unknown不retry | different_object_reuse、close_failure_unknown、close_fstat_failure |
| 工厂全资源故障清理、KI/SE identity/优先 | 每实际OS trace ordinal故障矩阵、factory_cleanup_priority、context_cleanup_priority |
| 不泄漏输入路径/原异常、不授exec | 固定错误from None/信号保留；reject及各故障断言，无helper调用 |
| 不接生产/generic/Windows脚本兼容、完整发布门 | Task3关联+rg、两轮CODE、root full三道与精确五路径 |

计划作者自审：无缺失代码步骤/引用类型；新API/type/property/signature一致；code块均为完整内容，不用“添加测试”代替方法。源内容仅计划候选，Task1骨架与Task2最终源码明确分开。root仍须完整自审及独立PLAN SPEC→不同QUALITY才派 Task1。

实际纯内存演练：三个Python代码块全AST解析；骨架单例实际1 assertion FAIL / 0 ERROR；最终source内存加载后22方法PASS / 0 skip / 0 FAIL / 0 ERROR（含真实临时regular/FD、fault矩阵及FIFO双角色）。FIFO子进程通过命令字符串注入同一完整source到内存模块，然后跑计划原脚本；未落盘source/test，未执行helper payload。strip-NONBLOCK负控两次实际超时、kill/reap；全套4.211秒。首轮演练发现growth测试把manifest66请求误按header64上限断言，已修成66并重跑上述全绿；不把首轮失败写成通过。此演练不是磁盘TDD、root自审或独立review，也不授原生/安装信用。

【架构级自检报告】（计划，不是软件验收）

- 语法/编译：三完整Python块纯内存AST通过；磁盘compileall-j1由Task2/3实跑后记结果。
- 依赖/调用链：只复用已有host/ELF函数及测试support；禁止生产集成。
- 逻辑/边界：有限读、前后stat、owner三态及外部复用合同已映射；无执行承诺。
- 异常处理：固定普通错误、所有资源一次清理、KI/SE优先矩阵及unknown不retry；未知关闭不伪造成功。
- 关联模块：新source/test仅两路径；其它三路径为发布文档记录，旧生产保持原回归。
- 兼容安全：可信caller限制、平台skip分账、无新权限/依赖/服务/helper执行。
- 可运行性：draft，尚未磁盘实现，不写100%或任何软件/设备通过。

## 完成记录（执行时填真实证据）

2026-10-11 20:14 UTC软件候选记录（后续完整门/发布另记）：冻结原计划SHA=`515652cae756a4fdcd12f1dcbe74aca6e8de494581d114fad27d227c79578e35`经root全文回读及独立PLAN SPEC→不同QUALITY各C0/I0/M0。Task1实际用apply_patch落盘批准模板；writer与root分别实跑单例1 assertion FAIL/0ERROR/0skip。完整骨架22方法出现34failure/22error，仅掌握未实现缺口，不计有效RED。Task1独立SPEC→不同QUALITY各零遗留后STOP。

不同Task2 writer再次复现同RED后，仅替换新源码为批准第三块，实际204行；测试实际563行未变。源码SHA=`88f1fe97e36c87ca6251ed9b9c887990f544fed1fafb0ea36779d8cd32d893e8`，测试SHA=`c4eefa8c0c1bb6592c87a3da95190461b813379ad7e9ff15312addfe24f31aa3`。writer22方法4.190秒/41关联4.205秒/显式prepare-wrap1方法0.003秒全PASS、0skip，独立内部SPEC→不同QUALITY零遗留后STOP。

root完整回读两新文件并实际42关联方法4.244秒PASS/0skip，另LA1 diagnostic23方法0.041秒PASS/0skip。fresh全局CODE SPEC→不同QUALITY各C0/I0/M0，分别42方法4.174秒/4.212秒PASS/0skip；QUALITY另真实宿主无patch工厂/context smoke通过，不是helper启动。新模块无生产consumer；FIFO两角色真实去NONBLOCK超时kill/reap、13个healthy OS ordinal×3故障、context5组及未知close实测通过。root全仓compileall-j1、site、governance、landscape排期及diff检查已通过；文档检查两处Python原函数表下标调用仍为已人工/AST核实的误报。完整preflight尚运行，未提交推送，不授原生/安装包/生产或R2/R3信用。以上只追加实际记录，三个批准Python块未改。

- [x] root全文自审及独立PLAN SPEC→不同QUALITY零遗留。
- [x] Task1有效 assertion RED / 0 ERROR、其它骨架ERROR分账、测试hash冻结。
- [x] Task2不同writer同RED→GREEN、源码hash、完整故障/FIFO/FD证据及七维报告。
- [x] 独立CODE SPEC→不同QUALITY零遗留，root关联回归，generic/Windows脚本证据。
- [x] root新full三道、compileall-j1、site/doc/landscape检查、actual平台skip分账。
- [ ] 精确索引/审查字节/五路径、commit/push与远端同SHA、实际CI终态。

后续完整门记录：root于2026-10-11 20:20:01 UTC取得本冻结候选实际完整preflight终态exit0，secrets/submodule/tests三道全部通过；实际命令为`.venv/bin/python scripts/preflight.py`，成功脚本不输出测试总数，故不推算数量。全仓compileall明确-j1；既有测试构建处的显式parallel1及配置环境已核，未新增并行编译。完整门前后source/test上述SHA完全一致。root已回读本次三文档状态追加并重跑一致性检查，两个Python下标调用误报已解释，无未解释项；site/governance/20项排期检查exit0（不代表20项目都已今日复核）。本片内部对象软件门通过，精确索引及main发布仍为下一操作，不授原生启动、安装包或产品ready。

【架构级自检报告】（本片内部对象软件，发布前）

- 语法/编译：实际导入、42关联及全仓compileall-j1通过。
- 依赖/调用链：复用已发布有限解析；全局仅专用测试导入新模块，无生产接线。
- 逻辑/边界：同FD有限读取、identity、三态及增长负控通过。
- 异常处理：39个OS阶段故障组合、KI/SE原对象、清理优先及未知关闭不重试通过；不承诺任意字节码原子窗口。
- 关联模块：原generic/Windows及显式脚本prepare-wrap回归通过，旧生产无修改。
- 兼容安全：完整密钥/子模块/测试守护三道通过；无权限、依赖、服务或vendor变更。
- 可运行性：内部对象软件验收通过，main发布与下一片原生执行另账，不授R2/R3整体100%。

---
**Execution Mode:** serial

Task 1 → Task 2 → Task 3。复杂所有权与故障语义不满足 inline 条件；由 root 依授权使用 nbl.subagent-driven-development，串行不同writer/独立审查。本文起草者到此停止，不能自动实施或代 root 复审。
