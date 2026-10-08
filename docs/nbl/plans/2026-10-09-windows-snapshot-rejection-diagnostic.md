# Windows 快照拒绝测试诊断 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development (recommended) or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在原 `windows_directory_changed` 拒绝发生时输出一次脱敏、闭集、两槽的测试诊断，区分实际 listing 与 held-handle 拒绝，保留原快照行为。

**Architecture:** 测试 helper 用真函数 wrapper 观察原签名返回值及真实 walker 异常；同时覆盖递归引用和 Windows adapter 的已导入别名。专有非阻塞锁限定一个安装 owner，观察只发生在 owner 线程；软件向量运行原 walker/validators/signatures，native backend 是唯一平台替身。生产源码、重试次数和异常合同都不修改。

**Tech Stack:** 既有 Python 验收虚拟环境、标准库 `unittest` / `contextlib.ExitStack` / `unittest.mock.patch` / `threading.Lock` / `json`，无新依赖。本机实际解释器为 `/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python`（3.11.15）；下文 `.venv/bin/python` 是工作区命令示例，实际验收均替换为此既有解释器并沿既有 Go 路径，不自动安装。

---

## 冻结输入、授权与三问

实施基线为 main `b3897f57cb8f258834486e1fb31c8b85e9ecae5d`。冻结设计为 `docs/nbl/specs/2026-10-09-windows-snapshot-rejection-diagnostic-design.md`，SHA-256 `16b93aef50a8dfb3bb3fb93bc7905e7d9d041c8b08218b78a64c21cd8c750f87`，已由独立 SPEC 与不同 QUALITY 增量完整回读审查且各零问题。设计首页的 ccbe67 与“当前文案仍跑守卫”是设计创建时快照；文案片现已发布，此计划按 b389 实施，不回写冻结设计。root 独有的文案发布记录与目录变化研究脏改动由 root 管理，实现者不得改动或暂存；它们是 b389 的实测收尾，root 完整回读并核相关范围后可作为本阶段必要记录精确提交，不纳其它用户改动。

root 已核 b389 主 CI 终态 37 success / 4 failure / 3整job skip / 0 cancel；两个 Windows workspace 在本窗口未复现目录变化，仍有 inspection Git10093/legacy10038 失败。本片是诊断，不称目录问题已修或因未复现关闭门。

本文件最初是实施方案，禁止预填验收数字。起草者只写本文件，没有实施、运行测试/native/CI/model、访问 KEY/凭据或执行 Git。执行阶段沿用户“只 main、持续自主推进、不等阶段命令”的既有授权；覆盖技能默认 worktree/分支/再次人工确认要求，但不扩大成新权限、修改 CI 或关闭其它平台门。原计划冻结 SHA `a777333c0050a16112e8935a25276bb3718623b78306f20c24be4667bfbbbd71`，随后 root 按实际 TDD 修正同步两份完整代码样例并追加执行记录；原计划静态审查不等于 GREEN。

三问均已确认：

1. 真实问题：公开 x64 workspace 日志 `CI37840482757/job113528293532` 中 contract fixture 的初始 baseline 因 `windows_directory_changed` 失败，日志没有两个拒绝点的区别；ARM 同 SHA 的 Git10093 不作为同根因证据。
2. 已有实现：`workspace_snapshot._walk_windows_directory()` 已有 listing 与 held-directory 双比较；`windows_worktree.snapshot_windows_workspace_windows()` 已有两次全新尝试。复用真实函数，旧 `windows_tree_snapshot_probe` 只作 hook 与平台替身先例，不复用其 name 字典分类器、额外查询或异常重建。
3. 调用链：`gate_fixture(git_workspace=True)` → `runner._snapshot(root)` → Windows adapter 别名 → 递归 walker → 两个 signature。hook 只包初始 baseline 一个调用，非 Windows 或非 git_workspace 不安装。

研究沿同日 `docs/agent-landscape-live.md` 与 `docs/nbl/specs/2026-10-09-windows-directory-change-research.md` 的独立只读记录：观察日 2026-10-09；Aider `5dc9490bb35f9729ef2c95d00a19ccd30c26339c` 的 [args](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/args.py#L547-L563) / [main](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/main.py#L1056-L1063)、Codex `fe50d010e203a9b8dda2c7737d7d8e4a80e6ab44` 的 [windows](https://github.com/openai/codex/blob/fe50d010e203a9b8dda2c7737d7d8e4a80e6ab44/codex-rs/sandboxing/src/windows.rs#L72-L129) 已区分配置与真实执行，两份固定许可为 Apache2。**采纳**证据分层与不可兑现能力不授信用的机制，收益为不拿软件或诊断代替原生，成本为配对测试和新 SHA 复验；不复制代码、无新依赖或权限。**暂缓**生产异常 reason、稳定性修复；**不适配**加重试/sleep/skip、忽略 ChangeTime 或归因 Git/Defender。这些上游不被声称有同款 Windows 诊断。Task 2 开始/结束由 root 刷新阶段记录，保留历史日期，不把本片当完整 20 项复核。

## 文件边界

| Task | 文件 | 责任 |
|---|---|---|
| 1 create | `tests/windows_snapshot_rejection_diagnostic.py` | 有界观察、安装/恢复、脱敏两槽回执 |
| 1 create | `tests/test_windows_snapshot_rejection_diagnostic.py` | 纯 portable 软件向量，零新增 skip |
| 1 modify | `tests/test_contract_engineering.py` | 仅 git_workspace 初始 baseline 的 context |
| 1 modify | `scripts/run_workspace_ci.py` | 新测试 module 在 DEFAULT 选择一次 |
| 1 modify | `tests/test_run_workspace_ci.py` | DEFAULT/fixture 的配对合同 |
| 2 root governance | 本计划、`docs/agent-landscape-live.md` 与既有阶段记录 | 实际验收、发布和新 SHA 原生观察记录；不改冻结设计 |

Task 1 仅上表五个源码/测试文件，作者不能写其它文件；root 负责阶段记录。两 Task 串行，作者不是验收人；每个实现 Task 使用新鲜作者，独立 SPEC 后再不同 QUALITY，root 回读后自己验证。

### Task 1: 五文件 TDD 实现与接线

**状态**

- [x] 任务完成

**Dependencies:** None
**Parallelizable:** No (同一进程四处 hook 与同一 fixture/DEFAULT 合同必须一起实施；独立只读研究/审查可以并行但不改作者文件)

- [x] **Step 1: 创建下文完整测试模块，先不创建 helper；在 paired 文件先加入本节 Step 5 的两条合同方法。**

测试的 `diagnostic()` 用 `find_spec` 与 `getattr` 做安全断言：缺文件/缺功能是明确 assertion FAIL，而不是 ImportError/loader ERROR。完整测试代码在本 Task Step 4；先把该代码原样放入新测试文件。先仅运行：

```bash
PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m unittest tests.test_windows_snapshot_rejection_diagnostic.TestWindowsSnapshotRejectionDiagnostic.test_stable_result_identity_and_no_output tests.test_run_workspace_ci.TestWorkspaceCiCoverage.test_snapshot_rejection_diagnostic_selected_once_portably -v
```

Expected：第一项 `AssertionError: diagnostic helper is not implemented`，第二项 selection count `0 != 1`；两项都是 FAIL，零 ERROR/skip。保存原始 RED 摘要与当时五文件 diff。RED 不符先纠正测试，不能将拼写/导入错误算 RED。

- [x] **Step 2: 用 apply_patch 新建 helper，完整内容如下。**

`patch.object(new=wrapper)` 不使用 `Mock`/`side_effect`，避免 mock 自动保留全树参数/结果历史。frames 最多 129；仅持有当前 frame 的第一份原 tuple 引用，第二份比较后释放。两指针额外空间为常数；`_scope` 仅生成闭集标签，不保留路径。第三根调用是软件故障向量，生产仍只有两次：它违反 context 一个最多两次 snapshot 的合同，整个 context 停观察且不输出，保留前两槽，不新增或覆盖任何槽；原对象仍透传。

```python
"""Test-only observation of the existing Windows snapshot rejection gates."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
import json
import threading
from unittest.mock import patch

from icode import workspace_snapshot as ws
from icode import windows_worktree as ww


PREFIX = "ICODE_WINDOWS_SNAPSHOT_REJECTION="
MAX_FRAMES = 129
_OWNER = threading.Lock()


def _slot(attempt, status="not_observed"):
    stage = "not_observed" if status == "not_observed" else "none"
    return dict(attempt=attempt, status=status, scope="unavailable",
                reject_stage=stage, changed_entry_class="not_observed",
                listing_difference_mask=None, handle_observation="not_observed",
                handle_difference_mask=None)


def _unavailable(attempt):
    return dict(attempt=attempt, status="diagnostic_unavailable",
                scope="unavailable", reject_stage="unavailable",
                changed_entry_class="unavailable", listing_difference_mask=None,
                handle_observation="unavailable", handle_difference_mask=None)


def _scope(parts):
    if type(parts) is not tuple:
        return "unavailable"
    for part in parts:
        if type(part) is not str or not part or part in (".", ".."):
            return "unavailable"
        if any(char in part for char in ("\0", "/", "\\", ":")):
            return "unavailable"
    if not parts:
        return "root"
    return "git_metadata" if parts[0] == ".git" else "other_descendant"


def _entry_class(name, scope):
    if scope == "unavailable":
        raise ValueError("scope unavailable")
    if scope == "git_metadata" or (scope == "root" and name == ".git"):
        return 1
    if name in (".icode_output", "__pycache__"):
        return 2
    return 4


def _listing_difference(before, after, scope):
    """Merge the already sorted unique-name production signature tuples."""
    i = j = mask = classes = 0
    while i < len(before) or j < len(after):
        if j == len(after) or (i < len(before) and before[i][0] < after[j][0]):
            mask |= 1
            classes |= _entry_class(before[i][0], scope)
            i += 1
        elif i == len(before) or after[j][0] < before[i][0]:
            mask |= 1
            classes |= _entry_class(after[j][0], scope)
            j += 1
        else:
            difference = 0
            for field, bit in ((1, 2), (2, 4), (3, 8), (4, 16), (5, 32)):
                if before[i][field] != after[j][field]:
                    difference |= bit
            if difference:
                mask |= difference
                classes |= _entry_class(before[i][0], scope)
            i += 1
            j += 1
    label = {0: "not_observed", 1: "git_metadata", 2: "ignored_control",
             4: "other"}.get(classes, "mixed")
    return mask, label


def _handle_difference(before, after):
    mask = 0
    for index in range(8):
        if before[index] != after[index]:
            mask |= 1 << index
    return mask


@dataclass(slots=True)
class _Frame:
    slot_index: int
    scope: str
    unavailable: bool = False
    listing_count: int = 0
    listing_before: object = None
    listing_mask: int | None = None
    entry_class: str = "not_observed"
    handle_count: int = 0
    handle_before: object = None
    handle_mask: int | None = None


class _Observer:
    def __init__(self):
        self.thread = threading.get_ident()
        self.frames = []
        self.suspended = 0
        self.root_count = 0
        self.current_slot = 0
        self.records = [_slot(1), _slot(2)]
        self.seen_rejection = False
        self.invalid_context = False
        self.output_failed = False

    def _make_frame(self, slot_index, parts):
        return _Frame(slot_index, _scope(parts))

    def _active(self):
        if (threading.get_ident() != self.thread or self.invalid_context
                or self.suspended or not self.frames):
            return None
        return self.frames[-1]

    def _listing(self, value):
        frame = self._active()
        if frame is None or frame.unavailable:
            return
        frame.listing_count += 1
        if frame.listing_count == 1:
            frame.listing_before = value
        elif frame.listing_count == 2:
            try:
                frame.listing_mask, frame.entry_class = _listing_difference(
                    frame.listing_before, value, frame.scope)
            finally:
                frame.listing_before = None
        else:
            frame.unavailable = True

    def _handle(self, value):
        frame = self._active()
        # File and symlink signatures precede the two final listing signatures.
        if frame is None or frame.unavailable or frame.listing_mask != 0:
            return
        frame.handle_count += 1
        if frame.handle_count == 1:
            frame.handle_before = value
        elif frame.handle_count == 2:
            try:
                frame.handle_mask = _handle_difference(frame.handle_before, value)
            finally:
                frame.handle_before = None
        else:
            frame.unavailable = True

    def signature(self, original, observe):
        def wrapped(*args, **kwargs):
            value = original(*args, **kwargs)
            if threading.get_ident() == self.thread and not self.invalid_context:
                try:
                    observe(value)
                except Exception:
                    try:
                        frame = self._active()
                        if frame is not None:
                            frame.unavailable = True
                    except Exception:
                        self.output_failed = True
            return value
        return wrapped

    def _rejected(self, frame, slot_index):
        self.seen_rejection = True
        if self.records[slot_index]["status"] in (
                "directory_rejected", "diagnostic_unavailable"):
            return  # First unwinding frame is the deepest actual rejection.
        if frame is None or frame.unavailable or frame.scope == "unavailable":
            self.records[slot_index] = _unavailable(slot_index + 1)
            return
        record = _slot(slot_index + 1, "directory_rejected")
        record["scope"] = frame.scope
        if frame.listing_mask:
            record.update(reject_stage="listing", changed_entry_class=frame.entry_class,
                          listing_difference_mask=frame.listing_mask)
        elif frame.listing_mask == 0 and frame.handle_count == 2 and frame.handle_mask:
            record.update(reject_stage="held_handle", listing_difference_mask=0,
                          handle_observation="different",
                          handle_difference_mask=frame.handle_mask)
        else:
            record = _unavailable(slot_index + 1)
        self.records[slot_index] = record

    def _restore(self, length, suspended, slot_index):
        del self.frames[length:]
        self.suspended = suspended
        self.current_slot = slot_index

    def walker(self, original):
        def wrapped(*args, **kwargs):
            if threading.get_ident() != self.thread or self.invalid_context:
                return original(*args, **kwargs)
            prior_length = len(self.frames)
            prior_suspended = self.suspended
            prior_slot = self.current_slot
            frame = None
            root = kwargs.get("is_root") is True and kwargs.get("depth") == 0
            slot_index = self.current_slot
            try:
                if root:
                    self.root_count += 1
                    if self.root_count > 2:
                        self.invalid_context = True
                    else:
                        slot_index = self.root_count - 1
                        self.current_slot = slot_index
                if self.invalid_context:
                    pass
                elif self.suspended or prior_length >= MAX_FRAMES:
                    self.suspended += 1
                else:
                    frame = self._make_frame(slot_index, kwargs.get("snapshot_parts"))
                    self.frames.append(frame)
            except Exception:
                self.suspended = prior_suspended + 1
                frame = None
            if self.invalid_context:
                return original(*args, **kwargs)
            try:
                try:
                    value = original(*args, **kwargs)
                except Exception as error:
                    try:
                        if (isinstance(error, ws.WorktreeTreeUnavailable)
                                and error.reason == "windows_directory_changed"):
                            self._rejected(frame, slot_index)
                        elif root and self.records[slot_index]["status"] == "not_observed":
                            self.records[slot_index] = _slot(slot_index + 1, "other_error")
                    except Exception:
                        if (isinstance(error, ws.WorktreeTreeUnavailable)
                                and error.reason == "windows_directory_changed"):
                            self.seen_rejection = True
                            try:
                                self.records[slot_index] = _unavailable(slot_index + 1)
                            except Exception:
                                self.output_failed = True
                        else:
                            self.output_failed = True
                    raise
                try:
                    if root and self.records[slot_index]["status"] == "not_observed":
                        self.records[slot_index] = _slot(slot_index + 1, "completed")
                except Exception:
                    self.output_failed = True
                return value
            finally:
                # No callbacks or new I/O during frame restoration.
                try:
                    self._restore(prior_length, prior_suspended, prior_slot)
                    if frame is not None:
                        frame.listing_before = frame.handle_before = None
                except Exception:
                    self.invalid_context = True
                    self.frames = []
                    self.suspended = prior_suspended
                    self.current_slot = prior_slot
        return wrapped

    def emit(self, sink, outcome):
        if self.invalid_context or self.output_failed or not self.seen_rejection:
            return
        try:
            payload = dict(schema_version=1, call_outcome=outcome, attempts=self.records)
            line = PREFIX + json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
            sink(line)
        except Exception:
            pass  # Diagnostic serialization/output cannot replace snapshot failure.


def _close_hooks(stack, references):
    failed = False
    try:
        stack.close()
    except Exception:
        failed = True
    finally:
        # Also roll back a partial installation or a failed ExitStack close.
        # Only restore this owner's wrappers; never remove an unrelated hook.
        for module, name, original, replacement in references:
            try:
                if getattr(module, name) is replacement:
                    setattr(module, name, original)
            except Exception:
                failed = True
    return not failed


@contextmanager
def windows_snapshot_rejection_diagnostic(*, enabled=True, sink=print):
    if not enabled or not _OWNER.acquire(blocking=False):
        yield
        return
    stack = None
    observer = None
    installed = False
    owns_lock = True
    returned = False
    references = ()
    try:
        try:
            stack = ExitStack()
            observer = _Observer()
            listing = observer.signature(ws._windows_directory_listing_signature, observer._listing)
            handle = observer.signature(ws._windows_handle_signature, observer._handle)
            recursive = observer.walker(ws._walk_windows_directory)
            top = observer.walker(ww._walk_windows_directory)
            references = (
                (ws, "_windows_directory_listing_signature", ws._windows_directory_listing_signature, listing),
                (ws, "_windows_handle_signature", ws._windows_handle_signature, handle),
                (ws, "_walk_windows_directory", ws._walk_windows_directory, recursive),
                (ww, "_walk_windows_directory", ww._walk_windows_directory, top))
            for module, name, original, replacement in references:
                stack.enter_context(patch.object(module, name, new=replacement))
            installed = True
        except Exception:
            try:
                if observer is not None:
                    observer.thread = None  # Unrestorable wrappers remain transparent.
                _close_hooks(stack, references)  # Roll back before the unobserved body.
            finally:
                _OWNER.release()
                owns_lock = False
        yield
        returned = True
    finally:
        if owns_lock:
            try:
                if observer is not None:
                    # Stop observation without invalidating the collected receipt.
                    observer.thread = None
                if not _close_hooks(stack, references) and observer is not None:
                    observer.output_failed = True
            finally:
                _OWNER.release()
        if installed:
            try:
                observer.emit(sink, "returned" if returned else "raised")
            except Exception:
                pass  # Even an observer entry-point fault preserves the body.
```

注意：仅 `Exception` 用于观察器降级；不吞 `KeyboardInterrupt/SystemExit`。body 未被捕获，异常栈由原测试正常展示；walker 内异常使用 bare raise。普通部分安装/close 故障在 body 前或退出时恢复 hook 并释放锁，失败 observer 不输出。若 ExitStack 和直接恢复均被故障阻断，不声称引用已恢复：先关闭本 owner 观察，残余 wrapper 仅透传原 callable；故障替身测试最终自行恢复。正常 owner 持锁至恢复尝试结束，随后 emit 不修改 hook；正常退出仍输出已观察的真实拒绝。

- [x] **Step 3: 单项 GREEN，再继续剩余软件负控。**

```bash
PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m unittest tests.test_windows_snapshot_rejection_diagnostic.TestWindowsSnapshotRejectionDiagnostic.test_stable_result_identity_and_no_output -v
```

Expected：PASS/0skip，返回对象 `is` 不变，原 callable 调用一次，稳定成功不输出。随后执行 Step 4 全模块，逐个故障向量按 RED→GREEN 补齐，不能删除失败向量、mock validator/signature 或以跳过授信用。

- [x] **Step 4: 新软件测试模块完整代码。**

以下是新文件 `tests/test_windows_snapshot_rejection_diagnostic.py` 的完整内容。所有后端调用序列仅由替身记录在测试自身；helper 不代理 backend、不保存调用历史。底层身份拒绝通过保存真正 walker 抛出的对象验证 `is`，不 mock 身份校验器；synthetic callable 只用于透明性、hook故障/帧容量边界，不授原walker可达信用。

```python
"""Portable controls for the test-only snapshot observer; no native credit."""

from contextlib import nullcontext
from dataclasses import replace
import importlib
import importlib.util
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

from icode import workspace_snapshot as ws
from icode import windows_worktree as ww


def info(**changes):
    return replace(ws._WindowsHandleInfo(7, bytes([17]) * 16, 16, 0, 1, 0, True, False),
                   **changes)


def entry(name, **changes):
    return replace(ws._WindowsDirectoryEntry(name, 16, 0, bytes([17]) * 16, 1, 0),
                   **changes)


class Backend:
    def __init__(self, *, listings=None, infos=None, open_error=None, close_error=None,
                 data=b"payload", query_error=None):
        self.listings = listings or {(): ((), ())}
        self.infos = infos or {(): (info(), info())}
        self.open_error = open_error
        self.close_error = close_error
        self.query_error = query_error
        self.data = data
        self.q = {}
        self.e = {}
        self.offset = {}
        self.trace = []

    def open_root(self, root):
        self.trace.append(("open_root",))
        if self.open_error is not None:
            raise self.open_error
        return ()

    def query_info(self, handle):
        self.trace.append(("query", handle))
        if self.query_error is not None:
            raise self.query_error
        count = self.q.get(handle, 0)
        self.q[handle] = count + 1
        values = self.infos[handle]
        return values[min(count, len(values) - 1)]

    def enumerate_directory(self, handle):
        self.trace.append(("enumerate", handle))
        count = self.e.get(handle, 0)
        self.e[handle] = count + 1
        return self.listings[handle][min(count, 1)]

    def open_child(self, handle, child, *, directory, reparse=False):
        self.trace.append(("open_child", handle, child.name, directory, reparse))
        return (*handle, child.name)

    def read_file(self, handle, size):
        self.trace.append(("read", handle, size))
        offset = self.offset.get(handle, 0)
        self.offset[handle] = offset + size
        return self.data[offset:offset + size]

    def read_symlink_target(self, handle):
        self.trace.append(("symlink", handle))
        return "private-target"

    def close_handle(self, handle):
        self.trace.append(("close", handle))

    def close_root(self, handle):
        self.trace.append(("close_root",))
        if self.close_error is not None:
            raise self.close_error


def tree(parts=(), *, drift=True):
    listings = {}
    infos = {}
    for depth in range(len(parts) + 1):
        path = parts[:depth]
        infos[path] = (info(),) * 4
        if depth < len(parts):
            before = after = (entry(parts[depth]),)
        else:
            before = (entry(".icode_output"),)
            after = () if drift else before
        listings[path] = before, after
    return Backend(listings=listings, infos=infos)


def file_tree(*, held_change=False, directory_symlink=False):
    payload = b"payload"
    normal = entry("private-file", attributes=0x80, end_of_file=len(payload))
    attributes = 0x490 if directory_symlink else 0x480
    link = entry("private-link", attributes=attributes, reparse_tag=0xA000000C)
    file_info = info(attributes=0x80, is_directory=False, end_of_file=len(payload))
    link_info = info(attributes=attributes, reparse_tag=0xA000000C,
                     is_directory=directory_symlink)
    return Backend(listings={(): ((normal, link), (normal, link))},
                   infos={(): (info(), info(change_time=2 if held_change else 1)),
                          (normal.name,): (file_info, file_info),
                          (link.name,): (link_info, link_info)})


class TestWindowsSnapshotRejectionDiagnostic(unittest.TestCase):
    def diagnostic(self):
        name = "tests.windows_snapshot_rejection_diagnostic"
        self.assertIsNotNone(importlib.util.find_spec(name), "diagnostic helper is not implemented")
        module = importlib.import_module(name)
        for symbol in ("windows_snapshot_rejection_diagnostic", "_listing_difference",
                       "_handle_difference", "_Observer", "_scope"):
            self.assertTrue(callable(getattr(module, symbol, None)), symbol + " is not implemented")
        return module

    def call(self, backends, *, observed=True):
        module = self.diagnostic()
        lines = []
        pending = iter(backends)
        created = []
        def factory():
            backend = next(pending)
            created.append(backend)
            return backend
        context = module.windows_snapshot_rejection_diagnostic(sink=lines.append) if observed else nullcontext()
        result = error = None
        try:
            with patch.object(ww, "_WindowsNativeWorktreeBackend", new=factory), context:
                result = ww.snapshot_windows_workspace_windows(Path("private-workspace"))
        except Exception as caught:
            error = caught
        return result, error, lines, created

    def receipt(self, lines):
        module = self.diagnostic()
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith(module.PREFIX))
        self.assertTrue(lines[0].isascii())
        receipt = json.loads(lines[0][len(module.PREFIX):])
        self.assertEqual(set(receipt), {"schema_version", "call_outcome", "attempts"})
        self.assertIs(type(receipt["schema_version"]), int)
        self.assertEqual(receipt["schema_version"], 1)
        self.assertIn(receipt["call_outcome"], ("returned", "raised"))
        self.assertEqual(len(receipt["attempts"]), 2)
        keys = {"attempt", "status", "scope", "reject_stage", "changed_entry_class",
                "listing_difference_mask", "handle_observation", "handle_difference_mask"}
        for ordinal, record in enumerate(receipt["attempts"], 1):
            self.assertEqual(set(record), keys)
            self.assertIs(type(record["attempt"]), int)
            self.assertEqual(record["attempt"], ordinal)
            self.assertIn(record["status"], ("directory_rejected", "completed", "other_error",
                                           "not_observed", "diagnostic_unavailable"))
            self.assertIn(record["scope"], ("root", "git_metadata", "other_descendant", "unavailable"))
            self.assertIn(record["reject_stage"], ("listing", "held_handle", "none", "not_observed", "unavailable"))
            self.assertIn(record["changed_entry_class"], ("git_metadata", "ignored_control", "other",
                                                        "mixed", "not_observed", "unavailable"))
            self.assertIn(record["handle_observation"], ("not_observed", "same", "different", "unavailable"))
            if record["status"] == "directory_rejected":
                if record["reject_stage"] == "listing":
                    self.assertIn(record["listing_difference_mask"], range(1, 64))
                    self.assertEqual(record["handle_observation"], "not_observed")
                    self.assertIsNone(record["handle_difference_mask"])
                else:
                    self.assertEqual(record["reject_stage"], "held_handle")
                    self.assertEqual(record["listing_difference_mask"], 0)
                    self.assertEqual(record["changed_entry_class"], "not_observed")
                    self.assertEqual(record["handle_observation"], "different")
                    self.assertIn(record["handle_difference_mask"], range(1, 256))
            elif record["status"] == "diagnostic_unavailable":
                self.assertEqual([record[key] for key in ("scope", "reject_stage", "changed_entry_class",
                                                         "handle_observation")], ["unavailable"] * 4)
                self.assertIsNone(record["listing_difference_mask"])
                self.assertIsNone(record["handle_difference_mask"])
            else:
                self.assertEqual(record["scope"], "unavailable")
                self.assertEqual(record["changed_entry_class"], "not_observed")
                self.assertEqual(record["handle_observation"], "not_observed")
                self.assertIsNone(record["listing_difference_mask"])
                self.assertIsNone(record["handle_difference_mask"])
                self.assertEqual(record["reject_stage"], "not_observed" if record["status"] == "not_observed" else "none")
        return receipt

    def test_stable_result_identity_and_no_output(self):
        module = self.diagnostic()
        value = object()
        calls = []
        def original(*args, **kwargs):
            calls.append((args, kwargs))
            return value
        lines = []
        with patch.object(ws, "_walk_windows_directory", new=original), module.windows_snapshot_rejection_diagnostic(sink=lines.append):
            returned = ws._walk_windows_directory("sentinel", snapshot_parts=(), is_root=True, depth=0)
        self.assertIs(returned, value)
        self.assertEqual(calls, [(("sentinel",), dict(snapshot_parts=(), is_root=True, depth=0))])
        self.assertEqual(lines, [])
        result, error, lines, created = self.call([Backend()])
        self.assertEqual(result, {})
        self.assertIsNone(error)
        self.assertEqual(lines, [])
        self.assertEqual(len(created), 1)

    def test_listing_classifier_all_fields_membership_and_categories(self):
        module = self.diagnostic()
        base = entry("secret-name", attributes=0x80)
        before = ws._windows_directory_listing_signature((base,))
        vectors = (("attributes", 0x81, 2), ("reparse_tag", 0xA000000C, 4),
                   ("file_id", bytes([34]) * 16, 8), ("change_time", 2, 16), ("end_of_file", 9, 32))
        for field, value, bit in vectors:
            with self.subTest(field=field):
                initial = replace(base, attributes=0x480) if field == "reparse_tag" else base
                a = ws._windows_directory_listing_signature((initial,))
                b = ws._windows_directory_listing_signature((replace(initial, **{field: value}),))
                self.assertEqual(module._listing_difference(a, b, "root"), (bit, "other"))
        self.assertEqual(module._listing_difference(before, (), "root"), (1, "other"))
        self.assertEqual(module._listing_difference((), before, "root"), (1, "other"))
        self.assertEqual(module._listing_difference(before, before, "root"), (0, "not_observed"))
        for scope, names, expected in (("root", (".git",), "git_metadata"),
                                       ("root", (".icode_output", "__pycache__"), "ignored_control"),
                                       ("other_descendant", (".git",), "other"),
                                       ("git_metadata", (".icode_output", "secret"), "git_metadata"),
                                       ("root", (".git", ".icode_output", "secret"), "mixed")):
            signatures = ws._windows_directory_listing_signature(tuple(entry(name) for name in names))
            self.assertEqual(module._listing_difference((), signatures, scope), (1, expected))
        mixed = ws._windows_directory_listing_signature((entry(".git"), entry(".icode_output"), base))
        changed = ws._windows_directory_listing_signature((entry(".git", change_time=2), replace(base, end_of_file=8)))
        self.assertEqual(module._listing_difference(mixed, changed, "root"), (1 | 16 | 32, "mixed"))

    def test_handle_classifier_eight_bits_is_not_walker_credit(self):
        module = self.diagnostic()
        before = ws._windows_handle_signature(info())
        for index, value in enumerate((8, bytes([34]) * 16, 0x50, 0xA000000C, 2, 9, False, True)):
            after = list(before)
            after[index] = value
            self.assertEqual(module._handle_difference(before, tuple(after)), 1 << index)
        self.assertEqual(module._handle_difference(before, before), 0)
        self.assertEqual(module._handle_difference(before, (8, bytes([34]) * 16, 0x50, 1, 2, 9, False, True)), 255)

    def test_actual_listing_rejection_and_retry_do_not_query_final_handle(self):
        first = tree()
        second = Backend()
        result, error, lines, created = self.call([first, second])
        self.assertIsNone(error)
        self.assertEqual(result, {})
        self.assertEqual(len(created), 2)
        self.assertEqual(first.q[()], 1)
        receipt = self.receipt(lines)
        self.assertEqual(receipt["call_outcome"], "returned")
        a, b = receipt["attempts"]
        self.assertEqual((a["status"], a["scope"], a["reject_stage"], a["changed_entry_class"],
                          a["listing_difference_mask"]), ("directory_rejected", "root", "listing", "ignored_control", 1))
        self.assertEqual(b["status"], "completed")

    def test_actual_listing_each_field_and_root_classes(self):
        # Ignored entries are listed/validated but never opened, so every legal
        # listing field reaches the actual listing rejection without bypasses.
        vectors = (("attributes", 0x11, 2), ("file_id", bytes([34]) * 16, 8),
                   ("change_time", 2, 16), ("end_of_file", 8, 32),
                   ("reparse_tag", 0xA000000C, 4))
        for field, value, bit in vectors:
            with self.subTest(field=field):
                base = entry(".icode_output", attributes=0x410 if field == "reparse_tag" else 16)
                backend = Backend(listings={(): ((base,), (replace(base, **{field: value}),))})
                _, error, lines, _ = self.call([backend, Backend()])
                self.assertIsNone(error)
                self.assertEqual(self.receipt(lines)["attempts"][0]["listing_difference_mask"], bit)
                self.assertEqual(backend.q[()], 1)
        for additions, expected in (((entry(".git"),), "git_metadata"),
                                     ((entry("private-name"),), "other"),
                                     ((entry(".git"), entry("__pycache__"), entry("private-name")), "mixed")):
            backend = Backend(listings={(): ((), additions)})
            _, error, lines, _ = self.call([backend, Backend()])
            self.assertIsNone(error)
            self.assertEqual(self.receipt(lines)["attempts"][0]["changed_entry_class"], expected)

    def test_actual_held_handle_reachable_fields_and_two_rejections(self):
        original = ww._walk_windows_directory
        for field, value, bit in (("file_id", bytes([34]) * 16, 2), ("change_time", 2, 16), ("end_of_file", 8, 32)):
            with self.subTest(field=field):
                captured = []
                def capture(*args, **kwargs):
                    try:
                        return original(*args, **kwargs)
                    except Exception as error:
                        captured.append(error)
                        raise
                backends = [Backend(infos={(): (info(), info(**{field: value}))}) for _ in range(2)]
                with patch.object(ww, "_walk_windows_directory", new=capture):
                    _, error, lines, created = self.call(backends)
                self.assertIsInstance(error, ws.WorktreeTreeUnavailable)
                self.assertIs(error, captured[-1])
                self.assertEqual(error.args, ("windows_directory_changed",))
                self.assertEqual(error.reason, "windows_directory_changed")
                self.assertEqual(len(created), 2)
                receipt = self.receipt(lines)
                self.assertEqual(receipt["call_outcome"], "raised")
                for record in receipt["attempts"]:
                    self.assertEqual((record["status"], record["reject_stage"], record["listing_difference_mask"],
                                      record["handle_difference_mask"]), ("directory_rejected", "held_handle", 0, bit))

    def test_actual_validator_errors_keep_original_object_and_no_receipt(self):
        module = self.diagnostic()
        cases = (dict(volume_serial_number=8), dict(attributes=0), dict(attributes=0x50),
                 dict(is_directory=False), dict(delete_pending=True), dict(reparse_tag=-1),
                 dict(reparse_tag=0x100000000), dict(attributes=0x410, reparse_tag=0xA000000C))
        original = ws._walk_windows_directory
        for changes in cases:
            captured = []
            def capture(*args, **kwargs):
                try:
                    return original(*args, **kwargs)
                except Exception as error:
                    captured.append(error)
                    raise
            backend = Backend(infos={(): (info(), info(**changes))})
            with self.subTest(changes=changes), patch.object(ww, "_walk_windows_directory", new=capture):
                _, error, lines, created = self.call([backend])
                self.assertIs(error, captured[0])
                self.assertEqual(error.reason, "windows_directory_identity_invalid")
                self.assertEqual(lines, [])
                self.assertEqual(len(created), 1)
        for raw in (1, 0xA000000C, 0xFFFFFFFF):
            _, error, lines, _ = self.call([Backend(infos={(): (info(), info(reparse_tag=raw))})])
            self.assertIsNone(error)
            self.assertEqual(lines, [])
        self.assertEqual(module._scope((".git", "hooks")), "git_metadata")
        self.assertEqual(module._scope(("subdir", ".git")), "other_descendant")
        for bad in (None, [], ("..",), ("a/b",), ("",), (3,)):
            self.assertEqual(module._scope(bad), "unavailable")

    def test_deepest_git_and_nested_git_scopes_parent_does_not_overwrite(self):
        for parts, scope, changed in (((".git", "hooks"), "git_metadata", "git_metadata"),
                                       (("subdir", ".git"), "other_descendant", "ignored_control")):
            first = tree(parts)
            _, error, lines, _ = self.call([first, Backend()])
            self.assertIsNone(error)
            record = self.receipt(lines)["attempts"][0]
            self.assertEqual((record["scope"], record["changed_entry_class"]), (scope, changed))
            self.assertEqual(record["reject_stage"], "listing")
            self.assertEqual(first.e[parts], 2)
            self.assertEqual(first.e[()], 1)
            self.assertFalse(any(call[0] == "open_child" and call[2] == ".icode_output" for call in first.trace))

    def test_open_close_boundaries_slots_and_original_other_errors(self):
        for second, expected in ((Backend(open_error=ws.WorktreeTreeUnavailable("open-private")), "not_observed"),
                                 (Backend(close_error=ws.WorktreeTreeUnavailable("close-private")), "completed"),
                                 (Backend(query_error=ws.WorktreeTreeUnavailable("query-private")), "other_error")):
            _, error, lines, _ = self.call([tree(), second])
            self.assertIs(error, second.open_error or second.close_error or second.query_error)
            receipt = self.receipt(lines)
            self.assertEqual(receipt["call_outcome"], "raised")
            self.assertEqual(receipt["attempts"][1]["status"], expected)
        for backend in (Backend(open_error=ws.WorktreeTreeUnavailable("open-private")),
                        Backend(query_error=ws.WorktreeTreeUnavailable("query-private"))):
            _, error, lines, created = self.call([backend])
            self.assertIs(error, backend.open_error or backend.query_error)
            self.assertEqual(len(created), 1)
            self.assertEqual(lines, [])

    def test_file_and_symlink_signatures_are_not_directory_handle_pair(self):
        for directory_symlink in (False, True):
            backend = file_tree(held_change=True, directory_symlink=directory_symlink)
            _, error, lines, _ = self.call([backend, Backend()])
            self.assertIsNone(error)
            record = self.receipt(lines)["attempts"][0]
            self.assertEqual((record["reject_stage"], record["handle_difference_mask"]), ("held_handle", 16))
            self.assertTrue(any(item[0] == "read" for item in backend.trace))
            self.assertTrue(any(item[0] == "symlink" for item in backend.trace))
        payload = b"payload"
        normal = entry("private-file", attributes=0x80, end_of_file=len(payload))
        file_info = info(attributes=0x80, is_directory=False, end_of_file=len(payload))
        bad_file = Backend(listings={(): ((normal,), (normal,))},
                           infos={(): (info(), info()), (normal.name,): (file_info, replace(file_info, change_time=2))})
        _, error, lines, created = self.call([bad_file])
        self.assertEqual(error.reason, "windows_entry_identity_changed")
        self.assertEqual(lines, [])
        self.assertEqual(len(created), 1)

    def test_backend_sequences_identical_with_and_without_hooks(self):
        for maker in (Backend, tree, file_tree,
                      lambda: file_tree(held_change=True, directory_symlink=True),
                      lambda: tree((".git", "hooks")),
                      lambda: Backend(infos={(): (info(), info(change_time=2))}),
                      lambda: Backend(infos={(): (info(), info(delete_pending=True))})):
            plain = [maker(), Backend()]
            observed = [maker(), Backend()]
            a, ae, _, ac = self.call(plain, observed=False)
            b, be, lines, bc = self.call(observed)
            self.assertEqual(a, b)
            self.assertEqual(getattr(ae, "reason", None), getattr(be, "reason", None))
            self.assertEqual([backend.trace for backend in ac], [backend.trace for backend in bc])
            if lines:
                self.receipt(lines)

    def test_hook_aliases_restore_and_signature_result_identity(self):
        module = self.diagnostic()
        references = ((ws, "_windows_directory_listing_signature"), (ws, "_windows_handle_signature"),
                      (ws, "_walk_windows_directory"), (ww, "_walk_windows_directory"))
        original = [getattr(owner, name) for owner, name in references]
        lines = []
        with module.windows_snapshot_rejection_diagnostic(sink=lines.append):
            for (owner, name), value in zip(references, original):
                self.assertIsNot(getattr(owner, name), value)
                self.assertFalse(hasattr(getattr(owner, name), "mock_calls"))
            backend = tree((".git",))
            with self.assertRaises(ws.WorktreeTreeUnavailable):
                ws._walk_windows_directory((), backend, object_format=None, include_in_tree=False,
                    snapshot_output={}, snapshot_parts=(), snapshot_enabled=True, is_root=True, depth=0)
        self.assertEqual(self.receipt(lines)["attempts"][0]["scope"], "git_metadata")
        for (owner, name), value in zip(references, original):
            self.assertIs(getattr(owner, name), value)
        returned = (entry("private"),)
        calls = []
        def signature(*args, **kwargs):
            calls.append((args, kwargs))
            return returned
        observer = module._Observer()
        wrapped = observer.signature(signature, observer._listing)
        self.assertIs(wrapped("value", flag=1), returned)
        self.assertEqual(calls, [(("value",), {"flag": 1})])
        failure = ws.WorktreeTreeUnavailable("unchanged-private")
        def failing(*args, **kwargs):
            calls.append((args, kwargs))
            raise failure
        wrapped = observer.signature(failing, observer._listing)
        with self.assertRaises(ws.WorktreeTreeUnavailable) as raised:
            wrapped("error", flag=2)
        self.assertIs(raised.exception, failure)
        self.assertEqual(failure.reason, "unchanged-private")
        self.assertEqual(failure.args, ("unchanged-private",))
        self.assertEqual(calls[-1], (("error",), {"flag": 2}))
        self.assertEqual(len(calls), 2)

    def test_owner_nested_and_other_thread_contexts_are_nonblocking_transparent(self):
        module = self.diagnostic()
        outer = []
        nested = []
        other = []
        done = threading.Event()
        errors = []
        references = []
        def worker():
            try:
                before = ws._walk_windows_directory
                with module.windows_snapshot_rejection_diagnostic(sink=other.append):
                    references.append(ws._walk_windows_directory is before)
                    with self.assertRaises(ws.WorktreeTreeUnavailable):
                        ww._walk_windows_directory((), tree(), object_format=None, include_in_tree=False,
                            snapshot_output={}, snapshot_parts=(), snapshot_enabled=True, is_root=True, depth=0)
                references.append(ws._walk_windows_directory is before)
            except Exception as error:
                errors.append(error)
            finally:
                done.set()
        with module.windows_snapshot_rejection_diagnostic(sink=outer.append):
            installed = ws._walk_windows_directory
            with module.windows_snapshot_rejection_diagnostic(sink=nested.append):
                self.assertIs(ws._walk_windows_directory, installed)
                self.assertIsNone(ww._walk_windows_directory((), Backend(), object_format=None,
                    include_in_tree=False, snapshot_output={}, snapshot_parts=(),
                    snapshot_enabled=True, is_root=True, depth=0))
            thread = threading.Thread(target=worker)
            thread.start()
            self.assertTrue(done.wait(2), "non-owner context must not wait for owner")
            thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertIs(ws._walk_windows_directory, installed)
            with self.assertRaises(ws.WorktreeTreeUnavailable):
                ww._walk_windows_directory((), tree(), object_format=None, include_in_tree=False,
                    snapshot_output={}, snapshot_parts=(), snapshot_enabled=True, is_root=True, depth=0)
        self.assertEqual(errors, [])
        self.assertEqual(references, [True, True])
        self.assertEqual(nested, [])
        self.assertEqual(other, [])
        self.assertEqual([record["status"] for record in self.receipt(outer)["attempts"]],
                         ["completed", "directory_rejected"])

    def test_active_references_released_and_actual_frame_count_bounded(self):
        module = self.diagnostic()
        observer = module._Observer()
        frame = observer._make_frame(0, ())
        observer.frames.append(frame)
        listing = observer.signature(ws._windows_directory_listing_signature, observer._listing)
        before = listing((entry("private-name"),))
        self.assertIs(frame.listing_before, before)
        listing((entry("private-name"),))
        self.assertIsNone(frame.listing_before)
        handle = observer.signature(ws._windows_handle_signature, observer._handle)
        before = handle(info())
        self.assertIs(frame.handle_before, before)
        handle(info())
        self.assertIsNone(frame.handle_before)
        self.assertNotIn("snapshot_parts", module._Frame.__slots__)
        self.assertEqual(len(observer.records), 2)
        observer.frames.clear()
        actual_observers = []
        peaks = []
        original_class = module._Observer
        original_make_frame = module._Observer._make_frame
        def factory():
            created = original_class()
            actual_observers.append(created)
            return created
        def make_frame(self, slot_index, parts):
            peaks.append(len(self.frames) + 1)
            return original_make_frame(self, slot_index, parts)
        with patch.object(original_class, "_make_frame", new=make_frame), patch.object(module, "_Observer", new=factory):
            _, error, lines, _ = self.call([tree(("d",) * 128), Backend()])
        self.assertIsNone(error)
        self.assertEqual(max(peaks), 129)
        self.assertEqual(len(actual_observers), 1)
        self.assertEqual(actual_observers[0].frames, [])
        self.assertEqual(len(actual_observers[0].records), 2)
        self.receipt(lines)

    def test_real_depth_129_and_synthetic_130_frames_do_not_borrow_parent(self):
        module = self.diagnostic()
        _, error, lines, _ = self.call([tree(("d",) * 128), Backend()])
        self.assertIsNone(error)
        self.assertEqual(self.receipt(lines)["attempts"][0]["status"], "directory_rejected")
        _, error, lines, _ = self.call([tree(("d",) * 129)])
        self.assertEqual(error.reason, "worktree_too_deep")
        self.assertEqual(lines, [])
        failure = ws.WorktreeTreeUnavailable("windows_directory_changed")
        peak = []
        def synthetic(*args, **kwargs):
            peak.append(kwargs["depth"])
            if kwargs["depth"] == 129:
                raise failure
            return ws._walk_windows_directory(snapshot_parts=(*kwargs["snapshot_parts"], "d"),
                    is_root=False, depth=kwargs["depth"] + 1)
        lines = []
        with patch.object(ws, "_walk_windows_directory", new=synthetic), module.windows_snapshot_rejection_diagnostic(sink=lines.append):
            with self.assertRaises(ws.WorktreeTreeUnavailable) as raised:
                ws._walk_windows_directory(snapshot_parts=(), is_root=True, depth=0)
        self.assertIs(raised.exception, failure)
        self.assertEqual(max(peak), 129)
        self.assertEqual(self.receipt(lines)["attempts"][0]["status"], "diagnostic_unavailable")

    def test_observer_bookkeeping_comparison_slot_and_sink_failures_preserve_original(self):
        module = self.diagnostic()
        def broken(*args, **kwargs):
            raise ValueError("private observer error")
        for owner, symbol in ((module._Observer, "_make_frame"), (module._Observer, "_listing"),
                              (module, "_scope"), (module, "_entry_class"),
                              (module, "_listing_difference"), (module._Observer, "_handle"),
                              (module, "_handle_difference"), (module._Observer, "_rejected")):
            maker = (lambda: Backend(infos={(): (info(), info(change_time=2))})) if "handle" in symbol else tree
            with self.subTest(symbol=symbol), patch.object(owner, symbol, new=broken):
                _, error, lines, _ = self.call([maker(), maker()])
            self.assertEqual(error.reason, "windows_directory_changed")
            self.assertEqual([slot["status"] for slot in self.receipt(lines)["attempts"]],
                             ["diagnostic_unavailable", "diagnostic_unavailable"])
        for owner, symbol in ((module.json, "dumps"),):
            with patch.object(owner, symbol, new=broken):
                result, error, lines, _ = self.call([tree(), Backend()])
            self.assertEqual(result, {})
            self.assertIsNone(error)
            self.assertEqual(lines, [])
        value = object()
        for failure in (None, ws.WorktreeTreeUnavailable("original-private")):
            def original(*args, **kwargs):
                raise ws.WorktreeTreeUnavailable("windows_directory_changed")
            returned = None
            try:
                with patch.object(ws, "_walk_windows_directory", new=original), module.windows_snapshot_rejection_diagnostic(sink=broken):
                    try:
                        ws._walk_windows_directory(snapshot_parts=(), is_root=True, depth=0)
                    except ws.WorktreeTreeUnavailable:
                        pass
                    if failure is not None:
                        raise failure
                    returned = value
            except ws.WorktreeTreeUnavailable as raised:
                self.assertIs(raised, failure)
            else:
                self.assertIsNone(failure)
                self.assertIs(returned, value)
        for original_error in (KeyboardInterrupt(), SystemExit(7)):
            with self.assertRaises(type(original_error)) as raised:
                with module.windows_snapshot_rejection_diagnostic(sink=broken):
                    raise original_error
            self.assertIs(raised.exception, original_error)

    def test_restore_slot_failure_and_overflow_exit_preserve_original(self):
        module = self.diagnostic()
        def broken(*args, **kwargs):
            raise ValueError("private bookkeeping")
        for symbol in ("_restore",):
            with patch.object(module._Observer, symbol, new=broken):
                result, error, lines, _ = self.call([Backend()])
                self.assertEqual(result, {})
                self.assertIsNone(error)
                self.assertEqual(lines, [])
                _, error, lines, _ = self.call([tree(), tree()])
                self.assertEqual(error.reason, "windows_directory_changed")
                self.assertEqual(lines, [])
        with patch.object(module, "_unavailable", new=broken), patch.object(module._Observer, "_make_frame", new=broken):
            _, error, lines, _ = self.call([tree(), tree()])
        self.assertEqual(error.reason, "windows_directory_changed")
        self.assertEqual(lines, [])
        # Keep a parent active, overfill only its subtree, then return from the
        # subtree and feed the parent real production signatures again.
        observer = module._Observer()
        parent = observer._make_frame(0, ())
        observer.frames = [parent] * module.MAX_FRAMES
        value = object()
        wrapped = observer.walker(lambda **kwargs: value)
        self.assertIs(wrapped(snapshot_parts=("private",), is_root=False, depth=129), value)
        self.assertEqual(len(observer.frames), module.MAX_FRAMES)
        self.assertEqual(observer.suspended, 0)
        self.assertIs(observer._active(), parent)
        before = ws._windows_directory_listing_signature(())
        after = ws._windows_directory_listing_signature((entry(".icode_output"),))
        observer._listing(before)
        observer._listing(after)
        self.assertEqual((parent.listing_mask, parent.entry_class), (1, "ignored_control"))
        observer.frames.clear()

    def test_partial_install_rolls_back_before_body_and_releases_owner(self):
        module = self.diagnostic()
        actual = module.patch.object
        originals = (ws._windows_directory_listing_signature, ws._windows_handle_signature,
                     ws._walk_windows_directory, ww._walk_windows_directory)
        for fail_at in range(1, 5):
            calls = []
            def installing(*args, **kwargs):
                calls.append(1)
                if len(calls) == fail_at:
                    raise ValueError("partial install")
                return actual(*args, **kwargs)
            lines = []
            with patch.object(module.patch, "object", new=installing):
                with module.windows_snapshot_rejection_diagnostic(sink=lines.append):
                    self.assertEqual((ws._windows_directory_listing_signature, ws._windows_handle_signature,
                                      ws._walk_windows_directory, ww._walk_windows_directory), originals)
                    self.assertTrue(module._OWNER.acquire(blocking=False))
                    module._OWNER.release()
            self.assertEqual(lines, [])
        for interruption in (KeyboardInterrupt(), SystemExit(7)):
            calls = []
            def interrupted_install(*args, **kwargs):
                calls.append(1)
                if len(calls) == 4:
                    raise interruption
                return actual(*args, **kwargs)
            with patch.object(module.patch, "object", new=interrupted_install):
                with self.assertRaises(type(interruption)) as raised:
                    with module.windows_snapshot_rejection_diagnostic(sink=lambda line: self.fail("interrupted install must not emit")):
                        self.fail("interrupted installation must propagate")
            self.assertIs(raised.exception, interruption)
            self.assertEqual((ws._windows_directory_listing_signature, ws._windows_handle_signature,
                              ws._walk_windows_directory, ww._walk_windows_directory), originals)
            self.assertTrue(module._OWNER.acquire(blocking=False))
            module._OWNER.release()
        result, error, lines, _ = self.call([tree(), Backend()])
        self.assertEqual(result, {})
        self.assertIsNone(error)
        self.receipt(lines)

        def broken_stack():
            raise ValueError("private stack construction failure")
        with patch.object(module, "ExitStack", new=broken_stack):
            result, error, lines, _ = self.call([Backend()])
        self.assertEqual(result, {})
        self.assertIsNone(error)
        self.assertEqual(lines, [])
        self.assertEqual((ws._windows_directory_listing_signature, ws._windows_handle_signature,
                          ws._walk_windows_directory, ww._walk_windows_directory), originals)
        self.assertTrue(module._OWNER.acquire(blocking=False))
        module._OWNER.release()

        def pending_close(stack):
            raise ValueError("private pending rollback failure")
        calls = []
        def installing(*args, **kwargs):
            calls.append(1)
            if len(calls) == 4:
                raise ValueError("private installation failure")
            return actual(*args, **kwargs)
        with patch.object(module.ExitStack, "close", new=pending_close), \
                patch.object(module.patch, "object", new=installing):
            with module.windows_snapshot_rejection_diagnostic(sink=lambda line: self.fail("failed install must not emit")):
                self.assertEqual((ws._windows_directory_listing_signature, ws._windows_handle_signature,
                                  ws._walk_windows_directory, ww._walk_windows_directory), originals)
                self.assertTrue(module._OWNER.acquire(blocking=False))
                module._OWNER.release()

    def test_context_cleanup_and_emit_failures_keep_original_results(self):
        module = self.diagnostic()
        actual_close = module.ExitStack.close
        references = ((ws, "_windows_directory_listing_signature"),
                      (ws, "_windows_handle_signature"),
                      (ws, "_walk_windows_directory"), (ww, "_walk_windows_directory"))
        def failed_close(stack):
            actual_close(stack)
            raise ValueError("private cleanup failure")
        def failed_before_close(stack):
            raise ValueError("private pending cleanup failure")
        def failed_emit(*args, **kwargs):
            raise ValueError("private observer failure")
        for owner, symbol, replacement in ((module.ExitStack, "close", failed_close),
                                            (module.ExitStack, "close", failed_before_close),
                                            (module._Observer, "emit", failed_emit)):
            for failure in (None, ws.WorktreeTreeUnavailable("original-private")):
                with self.subTest(symbol=symbol, raised=failure is not None):
                    value = object()
                    calls = []
                    def original(*args, **kwargs):
                        calls.append((args, kwargs))
                        if failure is not None:
                            raise failure
                        return value
                    lines = []
                    with patch.object(ws, "_walk_windows_directory", new=original):
                        originals = [getattr(owner, name) for owner, name in references]
                        with patch.object(owner, symbol, new=replacement):
                            try:
                                with module.windows_snapshot_rejection_diagnostic(sink=lines.append):
                                    result = ws._walk_windows_directory(snapshot_parts=(), is_root=True, depth=0)
                            except Exception as error:
                                self.assertIs(error, failure)
                            else:
                                self.assertIsNone(failure)
                                self.assertIs(result, value)
                        self.assertEqual([getattr(owner, name) for owner, name in references], originals)
                    self.assertEqual(len(calls), 1)
                    self.assertEqual(lines, [])
                    self.assertTrue(module._OWNER.acquire(blocking=False))
                    module._OWNER.release()

        for owner, symbol in ((module.ExitStack, "close"), (module._Observer, "emit")):
            for interruption in (KeyboardInterrupt(), SystemExit(7)):
                def interrupted(*args, **kwargs):
                    raise interruption
                originals = [getattr(owner, name) for owner, name in references]
                with patch.object(owner, symbol, new=interrupted):
                    with self.assertRaises(type(interruption)) as raised:
                        with module.windows_snapshot_rejection_diagnostic(sink=lambda line: self.fail("interruption must not emit")):
                            pass
                self.assertIs(raised.exception, interruption)
                self.assertEqual([getattr(owner, name) for owner, name in references], originals)
                self.assertTrue(module._OWNER.acquire(blocking=False))
                module._OWNER.release()

    def test_failed_fallback_restoration_leaves_only_transparent_wrappers(self):
        module = self.diagnostic()
        references = ((ws, "_windows_directory_listing_signature"),
                      (ws, "_windows_handle_signature"),
                      (ws, "_walk_windows_directory"), (ww, "_walk_windows_directory"))
        observers = []
        actual_observer = module._Observer
        def factory():
            observer = actual_observer()
            observers.append(observer)
            return observer
        def broken(*args, **kwargs):
            raise ValueError("private unrecoverable cleanup")
        value = object()
        calls = []
        failure = ws.WorktreeTreeUnavailable("private-original-failure")
        def original(*args, **kwargs):
            calls.append((args, kwargs))
            if kwargs.get("fail"):
                raise failure
            return value
        with patch.object(ws, "_walk_windows_directory", new=original):
            originals = [getattr(owner, name) for owner, name in references]
            try:
                lines = []
                with patch.object(module, "_Observer", new=factory), \
                        patch.object(module.ExitStack, "close", new=broken), \
                        patch.object(module, "setattr", new=broken, create=True):
                    try:
                        with module.windows_snapshot_rejection_diagnostic(sink=lines.append):
                            result = ws._walk_windows_directory(snapshot_parts=(), is_root=True, depth=0)
                    except Exception as error:
                        self.fail("cleanup replaced the original result: " + type(error).__name__)
                self.assertIs(result, value)
                self.assertTrue(all(getattr(owner, name) is not old for (owner, name), old in zip(references, originals)))
                self.assertIs(ws._walk_windows_directory(snapshot_parts=(), is_root=True, depth=0), value)
                with self.assertRaises(ws.WorktreeTreeUnavailable) as raised:
                    ws._walk_windows_directory(snapshot_parts=(), is_root=True, depth=0, fail=True)
                self.assertIs(raised.exception, failure)
                self.assertEqual(observers[0].root_count, 1)
                self.assertEqual(len(calls), 3)
                self.assertEqual(lines, [])
                self.assertTrue(module._OWNER.acquire(blocking=False))
                module._OWNER.release()
            finally:
                # The fault intentionally prevented restoration; the test
                # restores its own injected references after the assertions.
                for (owner, name), old in zip(references, originals):
                    setattr(owner, name, old)

    def test_extra_root_returns_and_errors_suppress_output_keep_slots_and_identity(self):
        module = self.diagnostic()
        failure = ws.WorktreeTreeUnavailable("windows_directory_changed")
        value = object()
        actual_walker = ws._walk_windows_directory
        for third_error in (None, failure):
            calls = []
            observer = module._Observer()
            def original(*args, **kwargs):
                calls.append(kwargs)
                if len(calls) < 3:
                    return actual_walker(*args, **kwargs)
                if third_error is not None:
                    raise failure
                return value
            wrapped = observer.walker(original)
            listing = observer.signature(ws._windows_directory_listing_signature, observer._listing)
            handle = observer.signature(ws._windows_handle_signature, observer._handle)
            arguments = dict(object_format=None, include_in_tree=False, snapshot_output={},
                             snapshot_parts=(), snapshot_enabled=True, is_root=True, depth=0)
            with patch.object(ws, "_windows_directory_listing_signature", new=listing), patch.object(ws, "_windows_handle_signature", new=handle):
                for _ in range(2):
                    with self.assertRaises(ws.WorktreeTreeUnavailable):
                        wrapped((), tree(), **arguments)
                before_lines = []
                observer.emit(before_lines.append, "raised")
                self.assertEqual([record["status"] for record in self.receipt(before_lines)["attempts"]],
                                 ["directory_rejected", "directory_rejected"])
                previous = [dict(record) for record in observer.records]
                if third_error is None:
                    self.assertIs(wrapped((), Backend(), **arguments), value)
                else:
                    with self.assertRaises(ws.WorktreeTreeUnavailable) as raised:
                        wrapped((), Backend(), **arguments)
                    self.assertIs(raised.exception, failure)
            self.assertEqual(len(calls), 3)
            self.assertEqual(observer.records, previous)
            self.assertEqual(len(observer.records), 2)
            self.assertTrue(observer.invalid_context)
            lines = []
            observer.emit(lines.append, "raised" if third_error else "returned")
            self.assertEqual(lines, [])

    def test_redacted_closed_output(self):
        _, _, lines, _ = self.call([tree((".git", "private-directory")), Backend()])
        self.receipt(lines)
        for forbidden in ("private", ".git", ".icode_output", "__pycache__", "file_id", "volume",
                          "change_time", "end_of_file", "traceback", "reason", "signature"):
            self.assertNotIn(forbidden, lines[0])


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 5: fixture/DEFAULT/paired 三文件成对接线。**

`tests/test_contract_engineering.py` 的 import 区新增：

```python
from tests.windows_snapshot_rejection_diagnostic import windows_snapshot_rejection_diagnostic
```

只把 `gate_fixture()` 中紧接 Git init/add/commit 后的那一行 baseline 替换为：

```python
        with windows_snapshot_rejection_diagnostic(enabled=os.name == "nt" and git_workspace):
            baseline = runner._snapshot(root)
```

不包后续 `changed.py` 写入、CP create、inspection、其它 baseline 或整个 method。`enabled=False` 在进入时短路，非 Windows 和非 git fixture 均不取锁/安装 hook；原 snapshot 仍调用一次。

`scripts/run_workspace_ci.py` 的 `DEFAULT_MODULES` 内，紧接 `"tests.test_workspace_hook_contract",` 新增且仅新增：

```python
    "tests.test_windows_snapshot_rejection_diagnostic",
```

`tests/test_run_workspace_ci.py` 的 `TestWorkspaceCiCoverage` 新增以下完整方法。第二项只抽取真实 fixture 的 baseline `With` 语句执行；用 namespace 设置平台，不全局改 `os.name`，不执行 CP、模型或 Git，既验证实际语句选择又检验非 Windows 无 hook。此是 fixture 接线软件信用，原生信用仍来自已有 workspace job。

```python
    def test_snapshot_rejection_diagnostic_selected_once_portably(self):
        name = "tests.test_windows_snapshot_rejection_diagnostic"
        self.assertEqual(DEFAULT_MODULES.count(name), 1)
        module = importlib.import_module(name)
        test_class = getattr(module, "TestWindowsSnapshotRejectionDiagnostic", None)
        self.assertTrue(isinstance(test_class, type))
        methods = unittest.defaultTestLoader.getTestCaseNames(test_class)
        self.assertTrue(methods)
        self.assertFalse(getattr(test_class, "__unittest_skip__", False))
        for method in methods:
            self.assertFalse(getattr(getattr(test_class, method), "__unittest_skip__", False))
        def cases(suite):
            for test in suite:
                if isinstance(test, unittest.TestSuite):
                    yield from cases(test)
                else:
                    yield test
        expected = {name + ".TestWindowsSnapshotRejectionDiagnostic." + method for method in methods}
        actual = [test.id() for selection in DEFAULT_MODULES
                  if selection == name or selection.startswith(name + ".")
                  for test in cases(unittest.defaultTestLoader.loadTestsFromName(selection))]
        self.assertEqual(set(actual), expected)
        self.assertEqual(len(actual), len(expected))

    def test_contract_git_baseline_only_uses_platform_gated_context_once(self):
        import ast
        import inspect
        import importlib.util
        import textwrap
        from contextlib import contextmanager
        from types import SimpleNamespace
        from icode import workspace_snapshot as ws, windows_worktree as ww
        from tests.test_contract_engineering import TestContractEngineering
        name = "tests.windows_snapshot_rejection_diagnostic"
        self.assertIsNotNone(importlib.util.find_spec(name), "diagnostic helper is not implemented")
        helper = importlib.import_module(name)
        context = getattr(helper, "windows_snapshot_rejection_diagnostic", None)
        self.assertTrue(callable(context), "diagnostic context is not implemented")
        source = textwrap.dedent(inspect.getsource(TestContractEngineering.gate_fixture))
        parsed = ast.parse(source)
        contexts = [node for node in ast.walk(parsed) if isinstance(node, ast.With)
                    and any(isinstance(child, ast.Assign)
                            and any(isinstance(target, ast.Name) and target.id == "baseline" for target in child.targets)
                            for child in node.body)]
        self.assertEqual(len(contexts), 1, "only the initial fixture baseline must be wrapped")
        statement = contexts[0]
        self.assertEqual(len(statement.body), 1)
        self.assertEqual(len(statement.items), 1)
        self.assertIsInstance(statement.items[0].context_expr.func, ast.Name)
        self.assertEqual(statement.items[0].context_expr.func.id, "windows_snapshot_rejection_diagnostic")
        code = compile(ast.fix_missing_locations(ast.Module(body=[statement], type_ignores=[])),
                       "fixture-baseline-contract", "exec")
        originals = (ws._windows_directory_listing_signature, ws._windows_handle_signature,
                     ws._walk_windows_directory, ww._walk_windows_directory)
        for platform, git_workspace, expected in (("nt", True, True), ("nt", False, False),
                                                   ("posix", True, False), ("posix", False, False)):
            calls = []
            enabled_values = []
            root = object()
            result = {"private-name": "private-value"}
            def snapshot(received):
                calls.append(received)
                current = (ws._windows_directory_listing_signature, ws._windows_handle_signature,
                           ws._walk_windows_directory, ww._walk_windows_directory)
                self.assertEqual(current != originals, expected)
                return result
            @contextmanager
            def recording_context(*, enabled):
                enabled_values.append(enabled)
                with context(enabled=enabled, sink=lambda line: self.fail("stable fixture must not emit")):
                    yield
            namespace = dict(os=SimpleNamespace(name=platform), git_workspace=git_workspace,
                             root=root, runner=SimpleNamespace(_snapshot=snapshot),
                             windows_snapshot_rejection_diagnostic=recording_context)
            exec(code, namespace)
            self.assertIs(namespace["baseline"], result)
            self.assertEqual(calls, [root])
            self.assertEqual(enabled_values, [expected])
            self.assertEqual((ws._windows_directory_listing_signature, ws._windows_handle_signature,
                              ws._walk_windows_directory, ww._walk_windows_directory), originals)
```

- [x] **Step 6: 全部五文件定点 GREEN 与作者自审，冻结后 STOP。**

```bash
PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m unittest tests.test_windows_snapshot_rejection_diagnostic tests.test_run_workspace_ci tests.test_windows_worktree_tree_oid.TestWindowsWorkspaceSnapshotDispatch tests.test_windows_worktree_tree_oid.TestProductionWindowsWorktreeTreeBuilder tests.test_contract_engineering.TestContractEngineering.test_incremental_cp_worklist_history_without_old_bodies_blocks_export -v
```

Expected：退出0、0 FAIL/ERROR；新增软件模块0skip，定点旧模块若出现 skip 必须按原选择查原因，不得新增或隐瞒。记录实际 total/PASS/skip/耗时，不能按计划方法数推算实测。

```bash
PYTHONPATH=src:. .venv/bin/python -B -m compileall -q -j 1 tests/windows_snapshot_rejection_diagnostic.py tests/test_windows_snapshot_rejection_diagnostic.py tests/test_contract_engineering.py scripts/run_workspace_ci.py tests/test_run_workspace_ci.py
git diff --check
sha256sum tests/windows_snapshot_rejection_diagnostic.py tests/test_windows_snapshot_rejection_diagnostic.py tests/test_contract_engineering.py scripts/run_workspace_ci.py tests/test_run_workspace_ci.py
```

Expected：编译与 diffcheck 退出0；冻结五个 SHA 并报实际 RED/GREEN 与向量 coverage。作者自己逐条 SPEC→QUALITY 自审，再报告唯一范围与风险 STOP；此阶段不得 commit/push、开20轮/DEFAULT/full/native/模型。源码返回 root 之后停止写入，任何重改均重冻结/双审。

Task 1 实测履历：首轮指定2项为2 assertion FAIL/0ERROR/0skip，0.000秒；stable单项1PASS/0skip，0.003秒。完整原样例20项先4 assertion FAIL，0.045秒，原因是测试在 context 内吞获原异常；把捕获移到 with 外后保留原 call_outcome 合同。fixture配对21项中20PASS/1FAIL、0.087秒，接线后通过。context cleanup/emit负控1方法6失败子向量、0.004秒，以及 ExitStack 构造/fallback恢复失败均分别取得 assertion RED 后修正 GREEN。最终作者指定定点62PASS/0FAIL/ERROR/skip、0.713秒，新模块22方法；五文件 compileall-j1退出0、0.055秒，缓存仅在仓外临时目录；diffcheck退出0。作者内置 SPEC→QUALITY 自审后已 STOP，没有运行20/DEFAULT/full/native/model或提交。

冻结五 SHA（helper/test/fixture/DEFAULT/paired）：`c75dd03f858f00dfbbc2d45f90f605553db4ee8d9d226dc684a3c56086f822c0` / `ba8ca9dda7a4a73ad19b61356c90a73d0ebe64b0d1db320e7bb2df3e68ce9b15` / `f4845043d0ad2d4b5f39c54cf3143b8c09479f31f49c06114c589e8efa2bb6a9` / `8684d9032eec84f2468ebab4d5d2d250372d21bbbc301f429c0429b102bcc9af` / `946c54d6bd26cfad09c2f9875270719dd9654f69a5a8384765c97eee6045334d`。同顺序 sha256sum 标准输出再 SHA aggregate `484ae70b18c23b92f7be1e22b1e084941d1482c8106bd4453a81fd9510d2e27b`；实际行数352/855/1041/185/288。root完整回读新两文件及原三文件/actual diff与生产上下游，核五 SHA匹配。样例同步仅文档，不修改已冻结源码或设计。

### Task 2: 独立双审、root 软件门、治理发布与新 SHA 原生只读复验

**状态**

- [ ] 任务完成

**Dependencies:** Task 1
**Parallelizable:** No (必须同五文件冻结SHA，SPEC先于不同QUALITY，root定点→20轮→DEFAULT→full串行，发布后才有对应新SHA原生)

- [x] **Step 1: root 完整回读设计、计划、五文件和现有相关源码；先新鲜 SPEC，再不同 QUALITY。**

独立审查者均只读，不替作者修改、不访问KEY/凭据、不请求模型/API、不改变native/CI/Git/权限；各自确认设计16b93a与五个冻结SHA，并实际执行 Step 6 的定点命令。SPEC按本计划下表逐行核设计；QUALITY重点核原函数一次/异常与返回对象、wrapper无Mock历史、两指针常数额外内存、owner生命周期/rollback、第三root合同、原查询序列与敏感输出。报告 Critical/Important/Minor 和真实测试摘要；有问题回作者原范围修正，重走冻结→SPEC→不同QUALITY，不沿用前SHA批准。

root再次读实际 diff，特别核 fixture仅一处context、DEFAULT一次、所有 validator/signature 原判据未动及 `src/`/vendor/workflows零修改。然后单独执行 Step 6 命令，不能拿作者/审查者结果替root定点。

- [x] **Step 2: root 串行20轮关键路径；每轮新 suite，失败/skip立即阻断。**

这是将来执行命令，起草时不执行。全模块覆盖全部关键正负控，20轮只运行portable新增模块，避免重复20次重CP/Git成本。

```bash
PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 GOMAXPROCS=1 GOFLAGS=-p=1 GOTOOLCHAIN=local CMAKE_BUILD_PARALLEL_LEVEL=1 .venv/bin/python -B - <<'PY'
import sys
import unittest
for ordinal in range(1, 21):
    suite = unittest.defaultTestLoader.loadTestsFromName("tests.test_windows_snapshot_rejection_diagnostic")
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    passed = result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped)
    print(f"round={ordinal} total={result.testsRun} passed={passed} skipped={len(result.skipped)} failures={len(result.failures)} errors={len(result.errors)}", flush=True)
    if not result.wasSuccessful() or result.skipped:
        sys.exit(1)
PY
```

Expected：20轮实际全部退出0/0skip/0F/E。记录每轮与累计实际数，任何改动使旧20轮信用失效；不同时跑DEFAULT/full。

- [x] **Step 3: 20轮结束后DEFAULT，结束后完整preflight。**

```bash
PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 GOMAXPROCS=1 GOFLAGS=-p=1 GOTOOLCHAIN=local CMAKE_BUILD_PARALLEL_LEVEL=1 .venv/bin/python -B scripts/run_workspace_ci.py
```

Expected：退出0，新模块0skip且选择一次；记录实际 summary与耗时。DEFAULT结束后才执行：

```bash
PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 GOMAXPROCS=1 GOFLAGS=-p=1 GOTOOLCHAIN=local CMAKE_BUILD_PARALLEL_LEVEL=1 .venv/bin/python -B scripts/preflight.py
```

Expected：三道全部通过，完整 unittest0F/E，既有环境skip另计；preflight的失败尾部不能替完整summary。root可沿现有只读wrapper捕获 `guard_tests` 原 `subprocess.run` 的完整summary，但须保持解释器/argv/cwd/env/返回码，不改测试选择或守卫。长过程保持每60秒内commentary，不启动第二套全量。PATH只沿已有批准Python/Go路径，不安装工具或取密钥。

- [x] **Step 4: 编译1与治理/站点/竞品排期/diff及冻结复核。**

```bash
PYTHONPATH=src:. .venv/bin/python -B -m compileall -q -j 1 src scripts tests
.venv/bin/python -B scripts/check_governance.py
.venv/bin/python -B scripts/check_site.py
.venv/bin/python -B scripts/check_agent_landscape.py
git diff --check
sha256sum tests/windows_snapshot_rejection_diagnostic.py tests/test_windows_snapshot_rejection_diagnostic.py tests/test_contract_engineering.py scripts/run_workspace_ci.py tests/test_run_workspace_ci.py
```

Expected：全部退出0，源码五SHA仍相同；`check_agent_landscape`只证日期/20项结构，不证20个上游已刷新。root用apply_patch向阶段记录与landscape写实际软件摘要和研究采纳/暂缓/不适配，保留未通过平台门及历史日期。文档更新后再跑治理/site/landscape/diff和preflight的secrets/submodule门；不再修改源码，如改源码须回Step1。root要逐一记录下面七维实际证据，不写未经测试的“异常全覆盖”或“可运行100%”。

- [ ] **Step 5: 仅已授权main精确提交推送，再绑定新SHA。**

提交前 `git branch --show-current` 必须main，`git status --short` 与实际diff确定精确目标；不用 `git add .`，不纳其它用户dirty。仅暂存本片五文件、本计划、必要的原冻结设计、新landscape段及上述两份由root独自写入的 b389 收尾记录；精确清单必须重新核对。忽略docs只对这些必要路径显式force-add，不扩大到其它候选方案。

```bash
git add -- tests/windows_snapshot_rejection_diagnostic.py tests/test_windows_snapshot_rejection_diagnostic.py tests/test_contract_engineering.py scripts/run_workspace_ci.py tests/test_run_workspace_ci.py docs/agent-landscape-live.md docs/nbl/specs/2026-10-09-windows-directory-change-research.md docs/nbl/plans/2026-10-09-r3-autonomy-configuration-wording.md
git add -f -- docs/nbl/plans/2026-10-09-windows-snapshot-rejection-diagnostic.md docs/nbl/specs/2026-10-09-windows-snapshot-rejection-diagnostic-design.md
git diff --cached --stat
git diff --cached --check
git diff --cached -- docs/agent-landscape-live.md
git status --short
```

landscape若与root历史记录共用dirty文件，只以 `git apply --cached` 作用于已回读的本片patch或逐hunk暂存，不能整文件顺带发布。完成精确staged审查、五SHA及三守卫仍对应后：

```bash
git commit -m "test: diagnose Windows snapshot directory rejection"
git push origin main
git rev-parse HEAD
git ls-remote origin refs/heads/main
```

Expected：提交/push退出0、local HEAD与origin main完整SHA相等；保留其它dirty。受本会话既有main提交推送授权，不重复问分支/批准；命令失败先解释并定位，不能强推、清工作区或绕守卫。这里只是源码阶段发布，不包含release/tag或额外CI权限。

- [ ] **Step 6: 新SHA原生仅观察，完整回读x64与ARM workspace日志。**

发布自动触发的既有CI由独立只读观察者绑定精确source SHA、workflow/run/job，读取元数据及完整decoded日志；root另独立回读。可用既有`gh api`只读或官方公开GET，不调用dispatch/rerun/cancel/修改workflow或下载执行native。具体run/job ID来自该新SHA实际列表，不沿用b389/ccbe的ID；当前没有可预填的新SHA/run。对每格记录平台/image、actualPython、total/PASS/FAIL/ERROR/既有skip、实际fixture是否越过baseline、是否出现 `ICODE_WINDOWS_SNAPSHOT_REJECTION=`。若有行，按冻结schema逐字段读两槽与call_outcome，禁止从mask推Git/Defender/正文根因；若无行仅表示该格本窗口未观察actual目录拒绝，不作稳定性修复结论。

Git10093/10038、网络10035/WFP、macOS quota、PE静态解析/加载/首UAC和模型六步门单独保留。即使新fixture和portable模块通过，也不关闭R2/R3。job终态后停止对应观察者，不重跑/取消/继续轮询终态。若本窗口无拒绝，诊断接线原生窗口已观察，根因仍未确认，下一步由新证据决定，不追加稳定性修改。

## 设计条款与明确向量映射

| 条款 | 实际测试方法/向量 | 信用边界 |
|---|---|---|
| 原call一次、args/kwargs、返回对象、稳定无输出 | `test_stable_result_identity_and_no_output`，真函数sentinel＋真实空walker | sentinel是透明性；空walker是真实算法 |
| listing六bit、OR、mixed、membership-only | `test_listing_classifier_all_fields_membership_and_categories`、`test_actual_listing_each_field_and_root_classes` | classifier用生产signature；真实ignored entry可达listing |
| handle八bit全向量 | `test_handle_classifier_eight_bits_is_not_walker_credit` | 直接classifier，不授validator之后可达信用 |
| 真实held FileId/ChangeTime/EOF | `test_actual_held_handle_reachable_fields_and_two_rejections` | 真实validators/signatures与两次新backend |
| volume/type/directory/delete_pending/tag先身份拒绝 | `test_actual_validator_errors_keep_original_object_and_no_receipt` | 真walker抛对象被捕获再bare raise，单次不retry |
| 合法raw tag归零、非法raw/Reparse拒绝 | `test_actual_validator_errors_keep_original_object_and_no_receipt`：1/A000000C/FFFFFFFF接受；-1/2**32/Reparse负例 | 不mock normalization/validator |
| listing失败不观察final handle | `test_actual_listing_rejection_and_retry_do_not_query_final_handle`，first.q(root)=1 | 第二次成功仍一行returned |
| deepest/git subtree/nested.git/ignored不走walker | `test_deepest_git_and_nested_git_scopes_parent_does_not_overwrite`、实际root additions | 首深slot冻结，父异常不覆盖 |
| 两次拒绝/第二open/第二close/第二othererror | `test_actual_held_handle_reachable_fields_and_two_rejections`、`test_open_close_boundaries_slots_and_original_other_errors` | root walker槽不等外围attempt/cleanup |
| 非目录错误与file/symlink pair不混 | `test_open_close_boundaries_slots_and_original_other_errors`、`test_file_and_symlink_signatures_are_not_directory_handle_pair` | 保原error与单次backend |
| 双alias真实覆盖、退出恢复、无Mock历史 | `test_hook_aliases_restore_and_signature_result_identity`，actual `.git` recursion | 真函数new，无自动历史 |
| 活跃tuple引用退出释放、有限frame与两record | `test_active_references_released_and_actual_frame_count_bounded` | 原tuple引用不复制，真实depth128测peak129且退出frames空 |
| owner线程、nested/其它线程/overlap非阻塞 | `test_owner_nested_and_other_thread_contexts_are_nonblocking_transparent` | Event2秒只测试非阻塞，不改product超时 |
| 129/130帧、subtree暂停、实际depth门 | `test_real_depth_129_and_synthetic_130_frames_do_not_borrow_parent` | depth129原行为worktree_too_deep；synthetic只测观察器容量 |
| 比较/classification/slot/frame安装/serialization/sink故障 | `test_observer_bookkeeping_comparison_slot_and_sink_failures_preserve_original`、`test_restore_slot_failure_and_overflow_exit_preserve_original`、`test_partial_install_rolls_back_before_body_and_releases_owner` | ownFailure不授稳定性；每个部分安装点1..4 |
| 第三root返回与抛错、两槽不变不输出 | `test_extra_root_returns_and_errors_suppress_output_keep_slots_and_identity` | 观察合同超限，不能重写第二槽 |
| backend query/enumerate/open/read/close全序列一致 | `test_backend_sequences_identical_with_and_without_hooks` | 两套独立backends同输入比全trace，未加product调用 |
| ASCII/精确字段/闭枚举/0与null/脱敏 | `receipt()`＋`test_redacted_closed_output` | 不输出path/name/ID/volume/time/size/rawerror/tuple |
| fixture单调用平台门、DEFAULT一次无skip | 两条新`TestWorkspaceCiCoverage`合同 | AST执行真实baseline语句；完整contract原回归保留 |

## root最终七维报告与分层交付

实施交付时必须报告下列七项的真实证据和未验边界；计划阶段都未运行，不能把复核代码文本当GREEN：

【架构级自检报告】

- [x] 语法/编译：五文件及全仓compileall-j1实际退出0。
- [x] 依赖/调用链：两个walker alias/两signature均覆盖恢复，fixture与DEFAULT配对通过。
- [x] 逻辑/边界：两指针bits/固定两槽/最深scope/129与130/第三root实际向量通过。
- [x] 异常处理：原error对象、identity早拒绝、ownfailure/partial install/sink降级实际通过；不声称所有OS异常已实测。
- [x] 关联模块：五文件原调用序列相等，旧dispatch/builder/contract回归及full通过。
- [x] 兼容安全：源码范围没有生产、vendor、workflow权限/重试改变；main精确发布门另由Step5记录，不以此勾选冒充已推送。
- [x] 可运行性：实际RED→GREEN、独立双审、root定点/20轮/DEFAULT/full均由同冻结源码取得；新SHA双架构观察另列。

实际后续记录：Task1已实现、作者STOP。新鲜GLOBAL SPEC全文核冻结设计/计划/源码与调用链，C/I/M及missing/extra/mismatch均0，独立62PASS/0skip、0.949秒；之后不同GLOBAL QUALITY完整回读，C/I/M均0，独立62PASS/0skip、0.685秒。两审前后设计16b93a、原计划a777及五SHA/aggregate保持；两个审查者都STOP，没有以自审替独立审。root独立指定定点62PASS/0skip、0.737秒；退出后20轮新模块每轮22PASS/0skip，共440PASS/0F/E、wall0.776秒。20轮退出后才开始DEFAULT，结果见下段，不授原生通过。

root计划复核：实现前全文回读1384行原计划，确认步骤/调用链/向量映射完整；真实TDD发现样例catch与出口故障不足后已同步actual代码，并明确不可恢复故障上限。冻结设计正文没有变化；起草时的等待审查状态属于历史，当前批准与执行状态以本计划实测履历为准。文档契约一致性技能用于字段/枚举、相对链接、围栏、计数及代码样例相等核对，不替软件或原生验收。

后续实际状态：DEFAULT已退出0，485PASS/0FAIL/ERROR/skip、163.460秒，installed bootstrap verifier byte binding为PASS。文档技能脚本对精确10个相关文件连续两轮0疑似项；人工核两槽、scope与entry分类、mask/状态枚举及段引用一致。六个Python代码块去共同缩进后AST解析通过，两完整样例与实际源码逐字相同，新模块实际22方法、十个共享schema字段在设计/实现/测试均有消费。首轮自制AST checker未去fixture语句缩进而自身报IndentationError，已改为dedent并重验；没有改源码、删除负控或将此checker ERROR算RED。DEFAULT退出后才启动原三道完整preflight，未取得其结果前不填写full通过。

完整守护后续实测：原三道preflight实际退出0，secrets/submodule均通过；原unittest命令2339 total/2280PASS/59既有环境skip/0FAIL/ERROR、481.407秒，子进程退出0、wall481.694秒。没有改原解释器、argv、cwd、env、测试选择或返回码。结束后全仓compileall-j1退出0、0.543秒，pycache仅仓外临时目录；governance/site/landscape（显式2026-10-09）及diffcheck均退出0。五源码SHA、设计16b93a保持，vendor仍1693651且干净。文档最终更新后的两轮一致性及三个文档检查/密钥/子模块门会在精确stage之前重验；发布和新SHA原生尚未取得，不填写总门通过。

---

**Execution Mode:** serial
