# S1a：Linux Live Lease Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development (recommended) or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为已真实取得的 `TicketLease` 增加最小私有只读 `_validate_active() -> None`，使后续单步 scope 可复用既有锁文件身份校验，而不重新加锁或转移释放责任。

**Architecture:** 在 `workspace.py` 的原 `TicketLease` 内新增一个方法，先核仍活着的真实 stream 和合法 FD，再调用原 `_validate_lock_file_identity`。本片不创建 scope、不接 broker/runner、不授 ready；旧 acquire/release/session/caller 原样保留。

**Tech Stack:** Python 3.11 标准库、已有 `TicketLease`、真实文件锁、`unittest`；没有服务、安装步骤、依赖或权限新增。

---

## 0. 状态、基线和实施前门

状态：软件候选已实施，目标、关联测试、独立双审及原完整守护通过；精确 main 发布待执行。历史设计/计划状态保留其观察时点。
计划观察日期：2026-10-12。计划时点 main HEAD 为 `d10cd46dc7220a8cc5c87d46e0d1dd41a547f11c`；S0b 尚未发布，此 SHA 不是未来 S1a 实施冻结版本。
母设计：[Linux 单步准备对象与真实命令消费](../specs/2026-10-12-linux-prepared-step-scope-design.md) §4 的活 lease 只读入口；原实现合同：[R2.1 Workspace Isolation And Lease](./2026-09-23-r2-workspace-lease.md)。

root 已完成 sequential-thinking 170–172 的需求、复用与风险分析。本 writer 只写本 PLAN；不实施 SOURCE、测试、Git、模型 KEY 或其它文档。用户要求 main 单主分支，覆盖技能中的另建 worktree 默认；实施以串行唯一 SOURCE writer 和独立审查避免共享工作树碰撞。

实施前必须满足：S0b 实际软件阶段发布完成；root 冻结当时真实 HEAD、相关文件 SHA 和工作树归属；本 PLAN 完整 fresh SPEC → 不同代理 QUALITY 均通过。不能用本 PLAN、研究或旧 CI 代替这些前门。

## 1. 三问与有限保证

| 三问 | 当前源码事实 | 决定 |
| --- | --- | --- |
| 真实问题？ | 母 scope 需要构造/每次借用时核 live lease，当前没有只读入口 | 新增最小 private 方法 |
| 已有实现？ | `_stream`、`_validate_lock_file_identity(path, descriptor)` 已存在；后者用 lstat/fstat 核 regular、nlink=1、无链接/重解析、dev/ino 一致 | 复用，不复制规则、不读 PID 元数据 |
| 影响调用链？ | `WorkspaceManager.open` 取得 lease；`WorkspaceSession.close` finally 调原 release；当前其它调用方没有新方法 | 本片零接线，旧签名及生命周期不变 |

该方法只证明可信宿主生命周期下 stream 未释放/关闭、FD 可观察且与锁文件路径对象一致。它不重新获取 flock，不证明被外部显式 unlock 后仍持锁，不认证手工构造的 dataclass，也不能绝对检测同对象 FD 数字复用；可信宿主禁止外部 close/dup2/unlock 与并发变更。没有 typed 对象、PID、路径文本或检查成功缓存充当授权。

检查不是资源 owner：不 seek/read/write/flush/truncate/open/close、不写 `_stream` 或其它字段、不重新 acquire/release、不创建线程或 FD。成功返回 None；所有普通 Exception 固定转为 `WorkspaceError("工单租约不可用") from None`，不泄漏路径/FD/异常正文。`KeyboardInterrupt`、`SystemExit` 不捕获，保持首个原对象，没有本片自有资源需要清理。

## 2. 文件与许可边界

未来 SOURCE 阶段仅修改 `src/icode/workspace.py`（新增方法），新建 `tests/test_linux_live_lease.py`（真实 acquire 的有限负控）。阶段文档仅本 PLAN 与 `docs/agent-landscape-live.md` 的最小真实记录，共四个精确 stage 路径。若需要超出这个集合，先回 root 重新审查，不自行扩写。

本计划复用 root 转述的独立只读研究，观察窗口 2026-10-12 01:10–01:11 UTC；root 于 01:15 UTC 又真实复取固定 process_manager.rs 与 OpenHands base.py，修正源码行锚。其余源码/许可证来源仍为独立研究者观察，并非本 writer 本轮重新获取上游：

- Codex 固定 `27065a91ccbf5ba8532844be3777fcf83b77820d` 的 [process_manager.rs](https://github.com/openai/codex/blob/27065a91ccbf5ba8532844be3777fcf83b77820d/codex-rs/core/src/unified_exec/process_manager.rs#L1158-L1175)，审批前同引用检查为 L909、审批后 refresh/get_mut 的 `Arc::ptr_eq` 在 L1165；exec ID 在 L236 使用 uuid，ID 本身不是对象身份。[bundled_bwrap.rs](https://github.com/openai/codex/blob/27065a91ccbf5ba8532844be3777fcf83b77820d/codex-rs/linux-sandbox/src/bundled_bwrap.rs) 的 held File/procfd 和 [exec_util.rs](https://github.com/openai/codex/blob/27065a91ccbf5ba8532844be3777fcf83b77820d/codex-rs/linux-sandbox/src/exec_util.rs) 的借用生命周期亦供参考。采纳等待后重核实际引用与对象，而非一次配置成功缓存；成本为每次调用两次 OS 身份观察。许可证 Apache-2.0，只借机制、不复制代码。
- OpenHands SDK 固定 `3934349da2db0433238621542173a00a8af7439c` 的 [base workspace](https://github.com/OpenHands/software-agent-sdk/blob/3934349da2db0433238621542173a00a8af7439c/openhands-sdk/openhands/sdk/workspace/base.py#L58-L65) `__enter__` L58–65 与 `__exit__` L158–170，以及 [local workspace](https://github.com/OpenHands/software-agent-sdk/blob/3934349da2db0433238621542173a00a8af7439c/openhands-sdk/openhands/sdk/workspace/local.py)，context/result 不是 live lease 证明。不适配为本机授权；许可证 MIT，无复制或新增依赖。

暂缓完整 scope/attachment/broker 接线及 installed 消费；本片验收只对应以下真实 lease 测试，不授整个 S1、LA-2、R2/R3、四 CI、自动模式、模型质量或 90% 一致性信用。不是全部二十项目刷新或最新 HEAD 比较。

### Task 1: 真实 released lease 的有效 assertion RED

**状态**
- [x] 任务完成

**Dependencies:** None（外部前门为 §0 的 S0b 发布、实施冻结和 PLAN 双审）
**Parallelizable:** No（唯一 SOURCE writer；先固定 RED，后实施）

- [x] **Step 1: Write the complete test file**

新建 `tests/test_linux_live_lease.py`，完整内容如下。全部正控先调用真实 acquire；patch 只在 acquire 后注入明确负控或观察副作用，不用 mock stream 构造授权。恢复 patch 后由原创建者 release。

```python
"""Linux live lease 只读检查的真实对象与故障边界。"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

import icode.workspace as workspace_module
from icode.workspace import TicketLease, WorkspaceError
from tests._support import temp_workspace

ERROR = "工单租约不可用"
CHILD = """
from pathlib import Path
import sys
from icode.workspace import TicketLease, WorkspaceBusyError
try:
    lease = TicketLease.acquire(Path(sys.argv[1]), 'project', 'ticket', 'child')
except WorkspaceBusyError:
    print('busy')
else:
    lease.release()
    print('acquired')
"""


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux S1a lease slice")
class TestLinuxLiveLease(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = temp_workspace()
        self.root = self.workspace.__enter__()
        self.addCleanup(self.workspace.__exit__, None, None, None)
        self.lease = TicketLease.acquire(self.root, "project", "ticket", "run")
        self.addCleanup(self.release_owned)

    def release_owned(self) -> None:
        # External-close negative has already closed the true owner stream;
        # original release must still run and may report its existing error.
        stream = self.lease._stream
        externally_closed = stream is not None and stream.closed
        try:
            self.lease.release()
        except WorkspaceError:
            if not externally_closed or self.lease._stream is not None:
                raise

    def assert_fixed(self, action) -> None:
        with self.assertRaises(WorkspaceError) as caught:
            action()
        self.assertEqual(str(caught.exception), ERROR)
        self.assertIsNone(caught.exception.__cause__)
        self.assertTrue(caught.exception.__suppress_context__)

    def test_released_lease_is_rejected(self) -> None:
        self.lease.release()
        self.assert_fixed(self.lease._validate_active)
        self.assertIsNone(self.lease._stream)

    def test_live_lease_returns_none_and_preserves_owner(self) -> None:
        stream = self.lease._stream
        self.assertIsNotNone(stream)
        descriptor = stream.fileno()
        before = os.fstat(descriptor)
        self.assertIsNone(self.lease._validate_active())
        self.assertIs(self.lease._stream, stream)
        self.assertFalse(stream.closed)
        after = os.fstat(descriptor)
        self.assertEqual((before.st_dev, before.st_ino), (after.st_dev, after.st_ino))

    def test_actual_external_stream_close_is_rejected(self) -> None:
        stream = self.lease._stream
        stream.close()
        self.assert_fixed(self.lease._validate_active)
        self.assertIs(self.lease._stream, stream)
        self.assertTrue(stream.closed)

    def test_actual_path_replacement_is_rejected_without_owner_close(self) -> None:
        stream = self.lease._stream
        descriptor = stream.fileno()
        previous = self.lease.path.with_name(self.lease.path.name + ".previous")
        self.lease.path.rename(previous)
        self.lease.path.write_bytes(b"replacement")
        self.assert_fixed(self.lease._validate_active)
        self.assertIs(self.lease._stream, stream)
        self.assertFalse(stream.closed)
        self.assertEqual(os.fstat(descriptor).st_ino, os.lstat(previous).st_ino)

    def test_actual_unlink_is_rejected_without_owner_close(self) -> None:
        stream = self.lease._stream
        descriptor = stream.fileno()
        self.lease.path.unlink()
        self.assert_fixed(self.lease._validate_active)
        self.assertFalse(stream.closed)
        os.fstat(descriptor)

    def test_no_reacquire_unlock_or_stream_io(self) -> None:
        stream = self.lease._stream
        state = self.lease.__dict__.copy()
        offset = stream.tell()
        original = self.lease.path.read_bytes()
        with mock.patch.multiple(
            stream, seek=mock.DEFAULT, read=mock.DEFAULT, write=mock.DEFAULT,
            flush=mock.DEFAULT, truncate=mock.DEFAULT, close=mock.DEFAULT,
        ) as methods, mock.patch.object(
            workspace_module, "_acquire_file_lock"
        ) as acquire, mock.patch.object(
            workspace_module, "_release_file_lock"
        ) as release, mock.patch.object(
            workspace_module.os, "open"
        ) as opening, mock.patch.object(workspace_module.os, "close") as closing:
            self.assertIsNone(self.lease._validate_active())
            for observed in methods.values():
                observed.assert_not_called()
            for observed in (acquire, release, opening, closing):
                observed.assert_not_called()
        self.assertEqual(self.lease.__dict__, state)
        self.assertEqual(stream.tell(), offset)
        self.assertEqual(self.lease.path.read_bytes(), original)

    def test_other_process_remains_busy_after_check(self) -> None:
        self.lease._validate_active()
        env = os.environ.copy()
        source = str(Path(__file__).resolve().parents[1] / "src")
        env["PYTHONPATH"] = os.pathsep.join(
            part for part in (source, env.get("PYTHONPATH")) if part
        )
        result = subprocess.run(
            [sys.executable, "-c", CHILD, str(self.root)], env=env,
            check=True, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.stdout.strip(), "busy")

    def test_invalid_fileno_values_are_rejected_before_identity(self) -> None:
        stream = self.lease._stream
        for value in (True, False, -1, 0, 1, 2, "3", None):
            with self.subTest(value=value), mock.patch.object(
                stream, "fileno", return_value=value
            ), mock.patch.object(
                workspace_module, "_validate_lock_file_identity"
            ) as identity:
                self.assert_fixed(self.lease._validate_active)
                identity.assert_not_called()
        self.assertFalse(stream.closed)

    def test_fileno_ordinary_failure_has_fixed_error(self) -> None:
        with mock.patch.object(
            self.lease._stream, "fileno", side_effect=OSError("private fd detail")
        ):
            self.assert_fixed(self.lease._validate_active)

    def test_each_os_identity_observation_ordinary_failure_is_fixed(self) -> None:
        stream = self.lease._stream
        descriptor = stream.fileno()
        for name in ("lstat", "fstat"):
            with self.subTest(name=name), mock.patch.object(
                workspace_module.os, name, side_effect=OSError("private path detail")
            ) as observation:
                self.assert_fixed(self.lease._validate_active)
                observation.assert_called_once()
            self.assertIs(self.lease._stream, stream)
            self.assertFalse(stream.closed)
            os.fstat(descriptor)

    def test_first_signal_original_object_is_preserved(self) -> None:
        stream = self.lease._stream
        descriptor = stream.fileno()
        for name in ("lstat", "fstat"):
            for signal in (KeyboardInterrupt("stop"), SystemExit(23)):
                with self.subTest(name=name, kind=type(signal).__name__), mock.patch.object(
                    workspace_module.os, name, side_effect=signal
                ) as observation:
                    with self.assertRaises(type(signal)) as caught:
                        self.lease._validate_active()
                    self.assertIs(caught.exception, signal)
                    observation.assert_called_once()
                self.assertIs(self.lease._stream, stream)
                self.assertFalse(stream.closed)
                os.fstat(descriptor)


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Establish meaningful RED without claiming missing API credit**

Run: `.venv/bin/python -B -m unittest tests.test_linux_live_lease.TestLinuxLiveLease.test_released_lease_is_rejected -v`

初次不存在 method 导致 AttributeError，只记录发现/搭架，不算有效 RED。仅在 `TicketLease` 的 acquire 与 release 之间临时加以下无授权 scaffold（不提交、不接任何生产 caller）：

```python
    def _validate_active(self) -> None:
        return None
```

再跑同一命令；必须真实调用 acquire → release 后，出现 `WorkspaceError not raised` 的 **1 method / 1 assertion failure / 0 error / 0 skip**，退出码非零。若被其它门提早拒绝、没有调用 target 或是 API 错误，不算目标 RED。记录当时 SOURCE/TEST SHA、原输出和耗时，不预填。

- [x] **Step 3: Root independently repeats the same target**

root 全文读测试与 scaffold、独立运行同一命令核目标 assertion，冻结有效 RED 和文件 SHA。writer 完成自审后停止写；未确认 RED 不执行 Task 2。

### Task 2: 最小只读方法和有限 GREEN

**状态**
- [x] 任务完成

**Dependencies:** Task 1
**Parallelizable:** No（串行唯一 SOURCE writer，不修改原 acquire/release）

- [x] **Step 1: Replace only the temporary method**

在 `src/icode/workspace.py` 的同一位置用以下完整方法替换 scaffold；不修改 import、原 identity helper、其它方法或调用方：

```python
    def _validate_active(self) -> None:
        """只读核验已有租约对象；不重新加锁或转移释放责任。"""
        try:
            stream = self._stream
            if stream is None or stream.closed:
                raise WorkspaceError("工单租约不可用")
            descriptor = stream.fileno()
            if type(descriptor) is not int or descriptor < 3:
                raise WorkspaceError("工单租约不可用")
            _validate_lock_file_identity(self.path, descriptor)
        except Exception:
            raise WorkspaceError("工单租约不可用") from None
```

类型精确 `type(...) is int` 排除 bool；既有 helper 核 FD/path，不读取 stream 内容或元数据。仅 catch Exception，因此 KI/SE 原对象透传。FD≥3 是此新内部消费前门，不改旧 acquire/release 支持范围。

- [x] **Step 2: Run target and full new matrix**

Run:

```bash
.venv/bin/python -B -m unittest tests.test_linux_live_lease.TestLinuxLiveLease.test_released_lease_is_rejected -v
.venv/bin/python -B -m unittest tests.test_linux_live_lease -v
```

Expected: Linux 上目标 assertion 从 RED 转 GREEN；新文件 11 methods、0 error、0 skip。子测试实际计数、时间、退出码只在运行后登记；非 Linux 整类 skip 是范围限制，不算 Linux PASS。

- [x] **Step 3: Run old lifecycle and identity regressions**

Run: `.venv/bin/python -B -m unittest tests.test_workspace tests.test_autonomy tests.test_workbench -q`

Expected: 保持原平台条件 skip 口径；原跨进程互斥、释放后重取、初始化异常、锁路径 symlink/hardlink、session/workspace 与自动入口回归通过。执行者记录真实结果，不引用旧 R2.1 完成状态代替本轮。

- [x] **Step 4: Demonstrate test discrimination and freeze**

在独立内存诊断中暂时将 `TicketLease._validate_active` 替换为返回 None 的函数，不写文件，只运行 released 单目标，必须仍产生同一 assertion failure；恢复方法后新测试 GREEN。逐项检查 ordinary OSfault 是真实 helper 的 lstat/fstat 调用命中，不以其它 early rejection 算通过。

Run（只有内存替换，无 SOURCE/TEST 文件写入）：

```bash
.venv/bin/python -B -c '
import sys
import unittest
from unittest import mock
from icode.workspace import TicketLease
with mock.patch.object(TicketLease, "_validate_active", lambda self: None):
    suite = unittest.defaultTestLoader.loadTestsFromName(
        "tests.test_linux_live_lease.TestLinuxLiveLease.test_released_lease_is_rejected"
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
observed = (
    result.testsRun == 1 and len(result.failures) == 1
    and not result.errors and not result.skipped
    and "WorkspaceError not raised" in result.failures[0][1]
)
sys.exit(0 if observed else 1)
'
.venv/bin/python -B -m unittest tests.test_linux_live_lease -v
```

Expected: 第一命令原 unittest 输出目标 FAIL，但诊断 harness 仅在精确 1/1/0/0 及目标断言命中时退出 0；这是测试区分力证据，**不是 GREEN**。第二命令恢复原方法后才记录真实 GREEN。
SOURCE writer 提交 SHA、源码 diff、所有原输出及七维自审后停止写；fresh SPEC 全文对照母合同/PLAN/源码，different QUALITY 独立复核测试区分力与副作用。审查发现问题修复后重跑相关测试，不以自审替独立审查。

### Task 3: Root 冻结、真实记录与 main 发布

**状态**
- [ ] 任务完成

**Dependencies:** Task 2
**Parallelizable:** No（源码双审后只冻结一个候选，禁止在未终态 CI 上覆盖推送）

- [x] **Step 1: Root independently validates frozen SOURCE**

root 全文读 method/new test，独立跑 Task 2 两组命令与相关回归，并核测试没有 mock stream 产生授权。核所有新方法调用仅 tests、无 scope/broker/runner 接线；借用 FD 仍活、创建者 release 最终仍唯一负责。

- [x] **Step 2: Single original complete preflight after final SOURCE freeze**

Run:

```bash
.venv/bin/python -B -m compileall -q -j1 src/icode/workspace.py tests/test_linux_live_lease.py
CMAKE_BUILD_PARALLEL_LEVEL=1 MAKEFLAGS=-j1 .venv/bin/python -B -u scripts/preflight.py
.venv/bin/python -B scripts/check_site.py
.venv/bin/python -B scripts/check_governance.py
git diff --check
```

Expected: 原完整 preflight 的各项真实通过；不得输出隐藏的全量测试计数。资源上限保持 j1（用户最高 j6）；未知/skip/信号不改成通过。root 复核 SOURCE SHA 在运行后未改变。

- [x] **Step 3: Record only observed proof**

将本 PLAN 状态/任务 checkbox 和 `docs/agent-landscape-live.md` 最小 S1a 条目更新为实际观察；真实 HEAD、RED/GREEN、fault/signals、独立审查、preflight 原结果、SHA/UTC、阶段边界都按原记录写，不提前生成通过或发布 SHA。
两次连续文档审计，分别记录原扫描数、手核代码 fence 假阳性排除数、实际未解决数；不能把原 scanner 非零谎称零。核 vendor 固定版本与 secrets guard，绝不读取模型 KEY 正文。

- [ ] **Step 4: Exact four-path stage, verify and publish main**

用户既有阶段提交/推送授权适用，root 操作而非 writer；确认上阶段同候选所有应等 CI 已终态，避免 cancel-in-progress。stage 精确四路径，先核 index 字节等于冻结工作树并无第五个文件，文档若 ignored 可仅对两个精确文档 `git add -f`。

```bash
git add src/icode/workspace.py tests/test_linux_live_lease.py
git add -f docs/nbl/plans/2026-10-12-linux-live-lease-validation.md docs/agent-landscape-live.md
git diff --cached --check
git diff --cached --name-only
git commit -m "feat(linux): validate live borrowed ticket lease"
git push origin main
git ls-remote --heads origin
```

Expected: 仅 main、远程 main 精确等于本次实际 commit；若新增文件或 dirty 用户修改不属于本片，不 stage。发布成功仅为 S1a 软件阶段，随后自动推进精确 scope 子片设计/PLAN，不等待用户例行命令，不报告整体 S1/R2/R3 完成。新 CI 实际终态及其有限信用另记。

## 3. 自审、执行模式与证据债务

规格映射：live/released/externalclose/pathreplace/unlink → Task 1 真对象；无 I/O/reacquire/owner mutation → Task 1 副作用和 child busy；FD 输入与既有 identity → Task 1 负控；普通异常固定包装与原 KI/SE → Task 1 OSfault；最小方法 → Task 2；旧兼容与独立审查/冻结/发布 → Task 2–3。
全部代码步骤给出完整代码，接口统一 `_validate_active() -> None`；没有 scope 接线或新权限。复杂性在真实锁、身份、异常边界与验证，非机械修改，因此 serial，不符合 inline 四条件；所有任务为 Task 1 → Task 2 → Task 3。
本 writer 自审只审 PLAN，不执行文内测试。后续由 root 使用 subagent-driven-development 串行任务与 fresh SPEC → 不同 QUALITY；当前不自动启动 SOURCE，等待 §0 外部前门。

【架构级自检报告】（计划文档，非运行结果）

- 语法/编译：代码结构与真实符号已静态核对；未执行源码或编译，不声明通过。
- 依赖/调用链：复用原 identity helper，原 lease/session release 不改；零生产接线。
- 逻辑/边界：FD 精确 int≥3、活 stream、路径/对象身份及可信宿主上限已明确。
- 异常处理：普通 Exception 固定无正文包装；KI/SE 原对象；借用检查没有自身清理资源。
- 关联模块：后续 scope 只读借用入口具备计划，当前 helper/broker/runner/vendor 不受本 writer 修改。
- 兼容安全：旧 acquire/release/caller 完全保留，无新增依赖/权限，测试使用真实 acquire。
- 可运行性：提供完整实施与测试内容但尚未执行，未授 100% 或整体验收信用。

**Execution Mode:** serial

## 实施前独立审查记录

Task1实际RED：fresh唯一writer仅新增11方法测试及三行未发布scaffold；缺API首跑1test/0.002s、AttributeError、exit1不授RED；scaffold后同target1test/1assertFAIL/0error/skip、0.002s、exit1。root全文读取新测试与workspace差异，独立同目标1test/1assertFAIL/0error/skip、0.037s、exit1，实际断言为WorkspaceError not raised。冻结workspace `f1ebba788bf3107353b94f4c025e07f528f5d103c6cba2102a470db0ec635674`、TEST `78a0ecdf6a1b6122f6a49b0096601a080989f445027b621b6dd91fea8d4dde02`。原acquire/release没有改动；当前仅允许不同fresh Task2 writer最小GREEN替换，不提交scaffold或提前授完整通过。

Task2实际GREEN并停止写入：SOURCE `c8692242d1392e6170e075d208c042e7c6b33cc65eaeaa93d7fa9d0bcc12e368`，TEST保持Task1冻结摘要。作者目标1/0.002s、新11/0.105s、旧三模块162/31.701s均exit0/0skip；内存noop仅released目标1assertFAIL/0error/skip/0.003s，精确诊断harness exit0不是GREEN，恢复原方法新11/0.060s通过。root全文读取13行方法diff与完整新测试，独立新11/0.067s、旧162/32.265s均0error/failure/skip；同内存noop目标1assertFAIL/0error/skip/0.037s，原方法及测试字节未改。旧回归包含两条预期argparse拒绝输出，不能说零stderr。作者双阶段自审零遗留；fresh SPEC→不同QUALITY、完整守护和发布仍待，不授installed、scope接线或R2/R3。

fresh独立SOURCE SPEC实际C0/I0/M0，全文源码/PLAN逐项核验；独立新11方法两轮各0.096s、0failure/error/skip，内存noop目标1assertFAIL/0error/skip、0.005s。旧162采用root实测转述而非SPEC自跑。两SOURCE前后摘要相同。不同fresh QUALITY正在核验，最终完整守护未启动，不能用SPEC替代后续门。

不同fresh QUALITY实际C0/I0/M0：新11方法两轮0.098/0.068s、旧162/32.780s均exit0/0failure/error/skip；内存noop精确目标1assertFAIL/0error/skip/0.002s，harness exit0仅目标鉴别力。测试实际184行（委派中约187行只为描述误差，不是内容漂移），两SOURCE前后摘要一致。root另实跑released目标1/0.036s GREEN，compileall-j1/site/governance各exit0。SOURCE冻结保持，下一步单次原完整预检保存仓外原日志，不授尚未取得的守护/发布结果。

完整预检于2026-10-12 01:52:44 UTC实际启动，session45514；原命令通过script -e -f保留仓外日志`/tmp/icode-s1a-preflight.SHRyzp/typescript`，CMAKE_BUILD_PARALLEL_LEVEL=1、MAKEFLAGS=-j1。密钥/vendor两道实际OK，全量尚在运行，无最终COMMAND_EXIT_CODE或完整通过信用。未启动第二份全量测试。

上述唯一完整预检随后于2026-10-12 02:01:57 UTC完成，session45514实际exit0，原日志末尾COMMAND_EXIT_CODE="0"，密钥/固定vendor/全量三道均OK。root核原日志及最终两源码摘要未变，不猜隐藏全量计数。最后两次原文档扫描结果另由发布前真实执行记录；此时尚未生成本片发布SHA。

root原文档扫描连续两次各2文件/0疑似/0假阳性/0未解决，随后密钥和固定vendor守护各exit0，源码摘要保持、diff --check通过。以下记录编辑后发布前再执行两次同扫描，避免以旧文档扫描替代最终字节；上阶段三个同SHA workflow均终态，Windows Reviewer失败保留。

【架构级自检报告】（S1a软件候选实测，非R2/R3整体验收）

- 语法/编译：compileall-j1、原完整preflight通过。
- 依赖/调用链：复用既有identity helper，零生产接线，旧162项回归通过。
- 逻辑/边界：新11项真实lease及有效目标RED/GREEN通过，保留可信宿主限制。
- 异常处理：普通异常固定包装、原KI/SE与真实OS故障测试通过；不声称覆盖未知故障。
- 关联模块：acquire/release/helper/broker/runner/vendor未改，site/governance通过。
- 兼容安全：旧签名/释放责任保留，密钥扫描和固定vendor守护通过，无新权限/依赖。
- 可运行性：本片本机测试及完整守护通过；scope/installed/跨平台/整体仍未授通过。

实施前门实际关闭（2026-10-12）：S0b原完整预检session36490 exit0；root精确七路径stage并核index字节一致后提交 `3ee3b48ff9a14be9f39b36968561fdb6870ab1fc`，实际push exit0，ls-remote仅main且精确同SHA。当前tracked工作树清洁；本未发布PLAN不在S0b提交内。workspace.py实施前SHA256 `c9f717336d082f372b397110f12fcfd2216ec091bef52e11d5245542d931ac1d`。原计划双审零遗留仍为计划前门；现在只允许Task1真实RED，不提前授GREEN或安装/整体通过。

root全文读取402行作者冻结PLAN `7cc6e05f8d96078c968cf15b7f6ab3ed9390464c3707f7bc8b96da76eed2e3fa`，fresh独立SPEC→不同QUALITY均C0/I0/M0；SPEC只读文档扫描两关联文件实际0疑似，双方均未执行文内代码或测试。此结论仅通过计划前门；当前S0b原完整preflight session5456仍在运行，尚未发布，S1a源码、scaffold和测试未创建。实施前root必须另核实际S0b commit/push、SOURCE归属与SHA，不以计划时点d10补未来信用。
