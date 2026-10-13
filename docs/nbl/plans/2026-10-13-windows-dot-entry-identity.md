# Windows Dot Entry Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development (recommended) or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 正确排除 Windows 准确 dot 伪项，同时保持真实子项零/FF ID 与全部记录边界拒绝。

**Architecture:** 复用既有 parser 的准确名称过滤，仅将 ID sentinel 判据移入输出真实 child 的分支。真实 collector 和 public snapshot/OID 回归验证调用链；root/child handle identity 完全不变。

**Tech Stack:** Python 3.11+、unittest、struct、hashlib、既有 Windows native backend；无新增依赖。

---

基线 main `0a980e0130873020881a6892d88715948af909a7`，权威工作区 `/home/orbbec/projects/icode`。关联 [DESIGN](../specs/2026-10-13-windows-dot-entry-identity-design.md)。初稿作者仅交付文档（历史）；root在fresh SPEC与不同QUALITY零遗留后已按正式TEST→SOURCE流程实施，当前进度见任务勾选及文末执行记录。用户 main-only / 线上优先授权优先于技能 worktree 和频繁提交示例；不建 worktree、分支、标签，不清理旧 Windows 链接。

文件职责：`src/icode/workspace_snapshot.py` 的 parser 改判据位置；新 `tests/test_windows_dot_entry_identity.py` 承载准确伪项正控、安全负控、真实 collector、Windows native 自有临时目录回归；`scripts/run_windows_tree_ci.py` 固定 tuple 加新模块，`tests/test_run_windows_tree_ci.py` 唯一 loader.loaded 断言精确同步；两个 DESIGN/PLAN、`docs/agent-landscape-live.md`、`docs/development-handoff.md` 承载决策与证据，共八路径。其余文件受保护，特别不改 `tests/test_control.py`、`windows_worktree.py`、权限/helper/isolation/vendor/workflow。所有 WSL 命令用已存在 Python 3.11 venv `/home/orbbec/icode-r2r3-env.DL2JQJ/bin/python`，不用 system Python 3.10。

## Task 1: TEST ONLY 与正式 RED

**Dependencies:** None
**Parallelizable:** No（root 文档双审 GO 后唯一 TEST 作者；未确认正式 RED 前不能写 SOURCE）

- [x] root 完整读 DESIGN/PLAN，由 fresh SPEC→不同 QUALITY 确认 C/I/M 均 0；记录两文档 SHA256、测试 fence SHA256、review 对象与日期。root 已真实三步 sequential-thinking 9c225a，结论见 DESIGN。主代理同时独立只读研究并刷新 live，研究不能改判据或代替测试。
- [x] TEST 作者确认 HEAD/工作区字节和源码未变，仅通过 apply_patch 新建下列完整文件。不得复制 fence 到物理 SOURCE；不 mock parser/collector/public native 入口。

### TEST fence: tests/test_windows_dot_entry_identity.py

```python
"""Exact Windows dot exclusion retains record and child identity checks."""

from __future__ import annotations

import hashlib
import os
import struct
import tempfile
import unittest
from pathlib import Path

from icode import workspace_snapshot as ws
from icode.workspace_snapshot import WorktreeTreeUnavailable
from tests.test_windows_worktree_tree_oid import _directory_record


_VALID_ID = bytes.fromhex("00112233445566778899aabbccddeeff")
_SENTINELS = (bytes(16), bytes([0xFF]) * 16)


def _observe_parse(payload: bytes):
    # A baseline rejection is an assertion difference, never a test ERROR.
    try:
        return ws._parse_windows_directory_entries(payload)
    except WorktreeTreeUnavailable as exc:
        return ("rejected", exc.reason)


def _observe_collect(responses):
    remaining = iter(responses)
    calls = []

    def read_page(information_class: int, buffer_bytes: int):
        calls.append((information_class, buffer_bytes))
        return next(remaining)

    try:
        result = ws._collect_windows_directory_entries(read_page, buffer_bytes=4096)
    except WorktreeTreeUnavailable as exc:
        result = ("rejected", exc.reason)
    return result, calls


def _dot_page(file_id: bytes = bytes(16)) -> bytes:
    return (
        _directory_record(".", file_id=file_id, attributes=0x10, next_entry_offset=96)
        + _directory_record("..", file_id=file_id, attributes=0x10)
    )


def _git_sha1(kind: bytes, content: bytes) -> bytes:
    return hashlib.sha1(kind + b" " + str(len(content)).encode("ascii") + b"\0" + content).digest()


def _observe_native(operation):
    try:
        return operation()
    except (OSError, WorktreeTreeUnavailable):
        # Native production refusal remains an assertion failure, never skip.
        return ("rejected", "native_workspace_rejection")


class TestWindowsDotEntryIdentity(unittest.TestCase):
    def test_exact_dot_sentinel_ids_are_excluded(self) -> None:
        for name in (".", ".."):
            for file_id in (*_SENTINELS, _VALID_ID):
                with self.subTest(name=name, identity=file_id):
                    self.assertEqual(
                        _observe_parse(_directory_record(name, file_id=file_id, attributes=0x10)),
                        (),
                    )

    def test_mixed_page_keeps_every_real_child_field(self) -> None:
        child = _directory_record(
            "café.bin", file_id=_VALID_ID, attributes=0x400,
            reparse_tag=0xA000000C, change_time=123456, end_of_file=17,
        )
        payload = (
            _directory_record(".", file_id=bytes(16), attributes=0x10, next_entry_offset=96)
            + _directory_record("..", file_id=bytes(16), attributes=0x10, next_entry_offset=96)
            + child
        )
        self.assertEqual(_observe_parse(payload), (
            ws._WindowsDirectoryEntry("café.bin", 0x400, 0xA000000C, _VALID_ID, 123456, 17),
        ))

    def test_real_and_near_dot_children_reject_sentinel_ids(self) -> None:
        for name in ("child.txt", ". ", ".. ", "..."):
            for file_id in _SENTINELS:
                with self.subTest(name=name, identity=file_id):
                    self.assertEqual(
                        _observe_parse(_directory_record(name, file_id=file_id)),
                        ("rejected", "windows_directory_record_invalid"),
                    )

    def test_dot_records_keep_structure_and_name_rejections(self) -> None:
        cases = []
        for name in (".", ".."):
            for file_id in (*_SENTINELS, _VALID_ID):
                for name_length in (0, 1, 512, 510):
                    invalid = bytearray(_directory_record(name, file_id=file_id))
                    struct.pack_into("<I", invalid, 60, name_length)
                    cases.append((bytes(invalid), "windows_directory_record_invalid"))
                for position in (32, 40):
                    invalid = bytearray(_directory_record(name, file_id=file_id))
                    struct.pack_into("<q", invalid, position, -1)
                    cases.append((bytes(invalid), "windows_directory_record_invalid"))
                invalid = bytearray(_directory_record(name, file_id=file_id))
                invalid[88:90] = b"\x00\xd8"
                cases.append((bytes(invalid), "windows_directory_name_invalid"))
        for name in ("\0", "./", ".\\", ".:"):
            cases.append((
                _directory_record(name, file_id=bytes(16)),
                "windows_directory_name_invalid",
            ))
        for payload, reason in cases:
            with self.subTest(reason=reason, header=payload[:88]):
                self.assertEqual(_observe_parse(payload), ("rejected", reason))

    def test_dot_records_keep_offset_trailing_and_header_rejections(self) -> None:
        for name in (".", ".."):
            for file_id in (*_SENTINELS, _VALID_ID):
                base = _directory_record(name, file_id=file_id)
                for next_offset in (1, 88, 4096):
                    invalid = bytearray(base)
                    struct.pack_into("<I", invalid, 0, next_offset)
                    with self.subTest(name=name, identity=file_id, offset=next_offset):
                        self.assertEqual(
                            _observe_parse(bytes(invalid)),
                            ("rejected", "windows_directory_offset_invalid"),
                        )
                self.assertEqual(
                    _observe_parse(base + b"\x01"),
                    ("rejected", "windows_directory_record_trailing_data"),
                )
        self.assertEqual(
            _observe_parse(b"\x01" + bytes(86)),
            ("rejected", "windows_directory_record_truncated"),
        )

    def test_first_dot_only_page_continues_then_keeps_child(self) -> None:
        child = _directory_record("child.txt", file_id=_VALID_ID)
        result, calls = _observe_collect([
            (True, 0, _dot_page()), (True, 0, child), (False, 18, b""),
        ])
        self.assertEqual(result, (ws._WindowsDirectoryEntry("child.txt", 0x80, 0, _VALID_ID, 0, 0),))
        self.assertEqual(calls, [(20, 4096), (19, 4096), (19, 4096)])

    def test_first_dot_only_page_requires_native_eof(self) -> None:
        result, calls = _observe_collect([(True, 0, _dot_page()), (False, 18, b"")])
        self.assertEqual(result, ())
        self.assertEqual(calls, [(20, 4096), (19, 4096)])

    def test_second_dot_only_page_is_no_progress(self) -> None:
        result, calls = _observe_collect([(True, 0, _dot_page()), (True, 0, _dot_page())])
        self.assertEqual(result, ("rejected", "windows_directory_enumeration_no_progress"))
        self.assertEqual(calls, [(20, 4096), (19, 4096)])


@unittest.skipUnless(os.name == "nt", "requires actual Windows native directory APIs")
class TestWindowsDotEntryIdentityNative(unittest.TestCase):
    def test_native_empty_directory_snapshot_and_oid(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-dot-empty-") as temporary:
            root = Path(temporary).resolve()
            self.assertEqual(_observe_native(lambda: ws.snapshot_workspace(root)), {})
            self.assertEqual(
                _observe_native(lambda: ws.worktree_git_tree_oid(root, object_format="sha1")),
                _git_sha1(b"tree", b"").hex(),
            )
        self.assertFalse(root.exists())

    def test_native_file_and_nested_empty_directories(self) -> None:
        content = b"dot identity\n"
        with tempfile.TemporaryDirectory(prefix="icode-dot-child-") as temporary:
            root = Path(temporary).resolve()
            (root / "empty" / "nested").mkdir(parents=True)
            (root / "child.txt").write_bytes(content)
            # Literal pieces avoid Python octal escape ambiguity in the oracle.
            expected_snapshot = hashlib.sha256(
                b"icode-workspace-entry-v2\0" + b"file\0" + b"100644\0" + content,
            ).hexdigest()
            self.assertEqual(
                _observe_native(lambda: ws.snapshot_workspace(root)),
                {"child.txt": expected_snapshot},
            )
            tree_body = b"100644 child.txt\0" + _git_sha1(b"blob", content)
            self.assertEqual(
                _observe_native(lambda: ws.worktree_git_tree_oid(root, object_format="sha1")),
                _git_sha1(b"tree", tree_body).hex(),
            )
        self.assertFalse(root.exists())


if __name__ == "__main__":
    unittest.main()
```

- [x] TEST ONLY 同时 apply_patch 以下既有 TEST 的唯一断言差分，仍不改 runner SOURCE：

```diff
--- a/tests/test_run_windows_tree_ci.py
+++ b/tests/test_run_windows_tree_ci.py
@@
             loader.loaded,
-            ["tests.test_windows_worktree_tree_oid"],
+            [
+                "tests.test_windows_worktree_tree_oid",
+                "tests.test_windows_dot_entry_identity",
+            ],
```

- [x] 在权威 WSL 运行两项正控 RED：`PYTHONPATH=src /home/orbbec/icode-r2r3-env.DL2JQJ/bin/python -m unittest tests.test_windows_dot_entry_identity.TestWindowsDotEntryIdentity.test_exact_dot_sentinel_ids_are_excluded tests.test_run_windows_tree_ci.TestWindowsTreeCiFailureAnnotations.test_native_windows_job_runs_production_tree_oid_suite -v`。预期 2 方法 / 5 assertion failures（两个准确名 × zero/FF 共四，加 loader 一项）、0 ERROR、0 skip、exit 1；valid ID 的两个 subtest PASS。实际数量若不同保留实际结果并定位，不能假称预期已成立。ImportError、SyntaxError、夹具/依赖失败不授 RED。记录真实原日志与两个正式 TEST SHA256。
- [x] root 全读正式 TEST 并独立执行同命令，核 SOURCE 与基线物理字节未变；两次有效正式 RED 后才给不同 SOURCE 作者 GO。本计划的 RAM/compile 诊断无正式 RED 信用。

## Task 2: 最小 SOURCE 与定点 GREEN

**Dependencies:** Task 1
**Parallelizable:** No（正式 RED 与 root SOURCE GO 后，不同作者单独改 SOURCE）

- [x] SOURCE 作者完整读当前 parser/collector/identity 调用链和 CI safe runner，仅 apply_patch 此 parser 生产 diff：

```diff
--- a/src/icode/workspace_snapshot.py
+++ b/src/icode/workspace_snapshot.py
@@
             or change_time < 0
             or end_of_file < 0
-            or file_id in (bytes(16), bytes([0xFF]) * 16)
         ):
@@
         if name:
+            # Exact dot records never produce child handles or child identities.
+            if file_id in (bytes(16), bytes([0xFF]) * 16):
+                raise WorktreeTreeUnavailable("windows_directory_record_invalid")
             if name in names:
```

- [x] 同一 SOURCE 作者仅给 CI safe runner 固定 tuple 加唯一新模块：

```diff
--- a/scripts/run_windows_tree_ci.py
+++ b/scripts/run_windows_tree_ci.py
@@
 _WINDOWS_TREE_TEST_MODULES = (
     "tests.test_windows_worktree_tree_oid",
+    "tests.test_windows_dot_entry_identity",
 )
```

- [x] 不改变 dot→空逻辑，不引入提前 continue，不改 root/child identity 函数或 runner 日志防注入/错误分类/权限/workflow。再次核两个正式 TEST SHA256 与 Task1 完全相同。
- [x] 权威 WSL 定点：`PYTHONPATH=src /home/orbbec/icode-r2r3-env.DL2JQJ/bin/python -m unittest tests.test_windows_dot_entry_identity.TestWindowsDotEntryIdentity tests.test_windows_worktree_tree_oid.TestProductionWindowsDirectoryEntryParser tests.test_windows_worktree_tree_oid.TestProductionWindowsDirectoryPageCollector tests.test_run_windows_tree_ci -v`。源码静态方法数为 8 新 portable + 5 既有 parser + 5 既有 collector + 7 safe runner = 25 方法；须记录实际运行数量，预期全部 PASS、0 ERROR/FAIL/skip、exit 0。不默认本机全量。
- [x] root 独立重验同定点集，fresh 实际 SOURCE SPEC→不同 QUALITY 审查 sentinel/near-dot/边界/no-progress/不变 identity，必须 C0/I0/M0。失败回正式 TEST/SOURCE 环节，禁止改断言隐藏失败。
- [x] 轻量语法与 whitespace：`PYTHONPATH=src /home/orbbec/icode-r2r3-env.DL2JQJ/bin/python -m py_compile src/icode/workspace_snapshot.py scripts/run_windows_tree_ci.py tests/test_windows_dot_entry_identity.py tests/test_run_windows_tree_ci.py`；`git diff --check`。预期 exit 0。py_compile 生成的忽略缓存不入发布。

## Task 3: 原生与候选线上门

**Dependencies:** Task 2
**Parallelizable:** No（冻结实际 SOURCE/TEST 后绑定新候选；旧 SHA 终态先完成）

- [ ] root 记录两 SOURCE/TEST SHA256、文档 SHA256、实际审查对象、定点日志及 exit；检查原 `windows_worktree.py`、identity 函数、vendor 固定子仓、受保护文件均未改变。独立研究的采纳/暂缓/不适配同步到 live 与 handoff；历史失败不删。
- [ ] 本机 Windows 若做必要原生最小诊断，用实际解释器而非 mock `os.name`，设置绝对 `$env:PYTHONPATH='\\wsl.localhost\Ubuntu-22.04\home\orbbec\projects\icode;\\wsl.localhost\Ubuntu-22.04\home\orbbec\projects\icode\src'` 后运行 `& 'C:\Users\orbbec\AppData\Local\Programs\Python\Python311\python.exe' -m unittest tests.test_windows_dot_entry_identity -v`。root 可等价用 Python subprocess argv、cwd=权威 UNC、env 中绝对 PYTHONPATH，避免 shell cd 歧义。预期 10 方法 PASS、0 ERROR/FAIL/skip、exit 0。无权限提升、无 shell Git；空目录/文件/nested empty 的真实回归与 portable 分开记信用，不默认原 34 项或全量。WSL 跑整新模块只可得 8 PASS/2 明确 native skip，不能叫原生通过。
- [ ] root 先取得基线 `0a980e0130873020881a6892d88715948af909a7` 对应 CI 终态与原日志，失败先归因。再按现有 CI 优先授权，密钥扫描/固定子仓完整性/必要局部回归及独立审查通过后才 main 提交推送下个候选，不新增分支/标签。不在本片执行任意 `git add .`；只暂存以下精确八路径：

```bash
git add -- src/icode/workspace_snapshot.py scripts/run_windows_tree_ci.py tests/test_windows_dot_entry_identity.py tests/test_run_windows_tree_ci.py docs/agent-landscape-live.md docs/development-handoff.md
git add -f -- docs/nbl/specs/2026-10-13-windows-dot-entry-identity-design.md docs/nbl/plans/2026-10-13-windows-dot-entry-identity.md
git diff --cached --name-only
git diff --cached --check
```

- [ ] root 核 cached 精确白名单、索引与冻结 bytes 一致，遵循现有检查器的实际命令，不能臆造 scanner/CI workflow 命令。待发布对象具体可审查后执行已授权 main 提交推送；本计划作者无发布权限。
- [ ] 新 SHA 的 GitHub CI 原生 Windows 与其它必要平台完整终态绑定 workflow/job/platform/raw log/exit；确保新 TEST 已收集、Windows native 两项实际 hit、无新增隐藏 skip。必要完整验收不以局部 GREEN、旧 SHA、失败重跑或 portable bytes 替代。失败保留原始终态，从原日志定位再做本机最小复现；本片通过后继续下一阶段，不声称 R2/R3 整体完成。

## 自审与当前状态

SPEC C0/I0/M0：DESIGN 矩阵均由 TEST fence 八 portable 方法/两 native 方法与既有 loader 唯一断言实现，两个生产 diff 仅移动原判据及固定 tuple 增一模块；root/child identity 与权限边界均无变更。QUALITY C0/I0/M0：RED 捕获原生产拒绝后用 assertion 判差，signed 负值夹具有效，page progression 与 EOF 分开，SHA1/SHA256 oracle 不依赖生产 hash helper，CI 收集旧漏项已纳入正式双RED；无模糊步骤替代代码、无新平台依赖。此为作者两个自审，不代表独立审查批准。

作者轻量验证：用 PowerShell 提取唯一 python fence，实际 CPython ast.parse/compile exit 0，AST 确认 8 portable / 2 native 方法；权威 WSL `git diff --check` exit 0。未运行测试或生成正式 TEST/SOURCE。第一次验证命令因 PowerShell native 引号丢失报 NameError，在执行 fence 前退出；修正命令后 compile 成功，不作为 RED 或测试失败信用。root 初读指出 native 直接拒绝会变 ERROR，资产已改为仅在生产 operation 内透明捕获 OSError/WorktreeTreeUnavailable 后 assertion 判差；目录创建/依赖/语法错误仍不吞。实际 check-ignore 发现 `.gitignore:119:docs/` 忽略两新文档，发布命令仅对这两个精确新路径使用 `git add -f`；不改 ignore 规则、不把 status 未列出的文档称为无改动。

【架构级自检报告】
- ✅ 语法/编译：唯一 TEST fence ast.parse/compile 通过，10 方法；SOURCE 未改。
- ✅ 依赖/调用链：原 helper、parser、collector、public 入口与字段匹配。
- ✅ 逻辑/边界：准确 dot、安全 sentinel、结构/名称/尾部及分页边界完整。
- ✅ 异常处理：生产固定 reason；baseline 拒绝通过 assertion 形成 RED。
- ✅ 关联模块：完整矩阵追踪两投影，控制路径断言另片处理。
- ✅ 兼容安全：身份/重试/权限/隔离/原生门保留。
- ✅ 可运行性：完整 TEST/diff/定点命令具备；正式实施与 CI 未执行。

**Execution Mode:** serial。初稿仅文档交付的停止条件是历史；root已在双审之后执行正式TEST→SOURCE，继续实际SOURCE双审及同SHA线上门。

## 2026-10-13 正式执行记录

批准资产DESIGN `e6a6ebfb734c02c6a87293140dba13a319fc38d9f1ae75e9fbaed7527df0c22b`、PLAN `bcde3dcc144922404f555149fa5fbccaff3901e8ca5b39278cca02e7ee8d26da`，fresh SPEC→不同QUALITY均C0/I0/M0；当前任务状态和证据追加改变文档摘要，不改变完整代码/差分围栏资产。

- Task1正式TEST作者与root分别2方法 / 0.002s / 5有效AssertionError / 0 ERROR、skip / exit1。两次原日志恰同bytes，仓外`windows-dotentry-author-red.log`与`windows-dotentry-root-red.log` SHA256均`a426476f6c2fa13aef619a60cb5a228c9f4bcfc9eb5366dd2dfa5737921d71bc`。root首次exec返回running时误作完成解析，未保存结果不授信用；bed896重验才授root RED。
- 新TEST保持8494bytes/68aacc摘要；既有TEST唯一loader期待差分后SHA256 `93c61cd3f21cfa8435dcfbe02b0f7e2282d580b0eac2da0d8724a62550215d1c`。RED时两SOURCE原56cdd444/04db3893不变。
- 不同SOURCE作者按两精确生产差分实施。当前`workspace_snapshot.py` SHA256 `7d9826d66a5e4a045a8b304ff5eb3c09fba230fc7c5eaffa045f8826bc2cdcc3`，safe runner SHA256 `7cbe2f234362e96378a48e0feffc406e74d8cbd69784f440989a47ad54c92a5d`；两个TEST及`windows_worktree.py`未漂移。
- 作者25 / 0.010s / 0 FAIL、ERROR、skip / exit0；root独立25 / 0.004s / 0 FAIL、ERROR、skip / exit0。仓外原日志`windows-dotentry-author-green.log` SHA256 `8f9a5ba56970824404985487e6f17c94db772c4461c0ad9f692d6ef5361b550b`；`windows-dotentry-root-green.log` SHA256 `88a52ac490b914859dfc84601719894224a7e80dc732b4cfc1d7900cd189a49f`。
- root本机真实Windows10 build19045 / AMD64 / CPython3.11.4运行新完整模块：10 / 0.129s / 0 FAIL、ERROR、skip / exit0。仓外原日志`windows-dotentry-root-native.log` SHA256 `fc06c95e3862c3d01579134c264b6bf3cf64425668155d13774968993a14f28d`，含两实际WindowsAPI空目录/文件及nested empty正控。只授本机窄parser/walker兼容，不代其它平台、新SHA CI或原生隔离。
- 上述日志根均为`/home/orbbec/icode-s2b2-evidence.Y3xrfh`。实际SOURCE fresh SPEC（windows_dotentry_actual_spec）→不同QUALITY（windows_dotentry_actual_quality）均C0/I0/M0；原27个非parser函数全文不变，safe runner去新增tuple行后全文与HEAD相同。阶段新SHA线上门仍待，不以本机GREEN或审查勾阶段完成；不运行本机全量。
- root409f24在真实Windows解释器只加载、不执行安全CI suite，实际platform=nt、总57、新module10、native2，native class skipped=false。后续新SHA x64/ARM job须绑定冻结tuple/TEST与57项实际runner结果，不只凭绿色授new native hit；旧symlink条件skip仍不得外推为通过。
- root38eaeb实际native WSL git核vendor工作树空、gitlink21566a5不带dirty；WindowsGit对UNC中Linux symlink的dirty呈现不作为权威内容变更，不清理任何链接或子仓。新S2c设计/计划仅并行技术准备，不入本片八路径。
