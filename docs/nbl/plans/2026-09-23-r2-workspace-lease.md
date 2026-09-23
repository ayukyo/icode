# R2.1 Workspace Isolation And Lease Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development (recommended) or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为每个自主工单创建独立 Git worktree 或文件快照，以跨进程租约保证同一工单只有一个执行者，并把原工作树、Git 元数据和 ICODE 控制面目录编译为默认受保护路径。

**Architecture:** 新增 `workspace.py` 作为宿主侧 Workspace Manager，先取得 ticket 级文件锁，再创建或复用带版本清单的任务工作区。`AutonomyManager` 只在明确注入 Workspace Manager 时切换到隔离 checkout，现有会话模式和测试注入保持兼容；R2.1 只生成 R2.0 的策略合同，不宣称操作系统已强制执行，真正原生阻断留给 R2.2/R2.3。

**Tech Stack:** Python 3.11 标准库、`fcntl`/`msvcrt` 平台文件锁、Git CLI、现有 `SandboxPolicy`、`unittest`/`pytest`。

---

## 文件结构

- 新建 `src/icode/workspace.py`：数据目录选择、跨进程租约、Git/snapshot 工作区、清单校验、受保护路径与策略生成。
- 新建 `tests/test_workspace.py`：真实子进程互斥、Git 原工作树不变、非 Git 快照、清单拒绝漂移、策略保护路径。
- 修改 `src/icode/autonomy.py`：把租约和隔离 checkout 绑定到自主 run 生命周期。
- 修改 `src/icode/workbench.py`：自动模式默认构造 Workspace Manager，交互模式不变。
- 修改 `tests/test_autonomy.py`、`tests/test_workbench.py`：验证接入、失败收敛和兼容行为。
- 修改 `docs/roadmap.md`：只把 R2.1 已验证边界标为完成，继续声明原生阻断属于后续阶段。

### Task 1: 跨进程工单租约

**状态**
- [x] 任务完成

**Dependencies:** None
**Parallelizable:** No (后续所有工作区操作必须先持有同一租约)

- [x] **Step 1: Write the failing tests**

在 `tests/test_workspace.py` 新增真实多进程测试，约定公开接口：

```python
from icode.workspace import TicketLease, WorkspaceBusyError

def test_same_ticket_cannot_be_leased_by_second_process(self):
    lease = TicketLease.acquire(self.data_root, "project-a", "ticket-1", "run-a")
    try:
        result = _probe_lease_in_subprocess(
            self.data_root, "project-a", "ticket-1", "run-b"
        )
        self.assertEqual(result, "busy")
    finally:
        lease.release()

def test_different_tickets_can_hold_leases(self):
    first = TicketLease.acquire(self.data_root, "project-a", "ticket-1", "run-a")
    second = TicketLease.acquire(self.data_root, "project-a", "ticket-2", "run-b")
    second.release()
    first.release()

def test_released_lease_can_be_reacquired(self):
    TicketLease.acquire(self.data_root, "project-a", "ticket-1", "run-a").release()
    TicketLease.acquire(self.data_root, "project-a", "ticket-1", "run-b").release()
```

子进程探针必须通过 `python -c` 导入已检出的真实包，不能 mock 文件锁。

- [x] **Step 2: Run tests to verify RED**

Run: `python -m pytest tests/test_workspace.py -q`

Expected: FAIL，原因是 `icode.workspace` 尚不存在。

- [x] **Step 3: Implement the minimal lease**

在 `src/icode/workspace.py` 实现：

```python
class WorkspaceError(RuntimeError): ...
class WorkspaceBusyError(WorkspaceError): ...

@dataclass
class TicketLease:
    path: Path
    project_id: str
    ticket_id: str
    run_id: str
    _stream: BinaryIO | None

    @classmethod
    def acquire(cls, data_root: Path, project_id: str,
                ticket_id: str, run_id: str) -> "TicketLease": ...
    def release(self) -> None: ...
    def __enter__(self) -> "TicketLease": ...
    def __exit__(self, exc_type, exc, traceback) -> None: ...
```

要求：

- 锁文件名只使用 `sha256(project_id + NUL + ticket_id)`，不把不可信 ID 当路径；
- POSIX 使用 `fcntl.flock(LOCK_EX | LOCK_NB)`，Windows 使用 `msvcrt.locking(..., LK_NBLCK, 1)`；
- 锁成功后原子更新只含稳定 ID、run ID、PID 的诊断元数据；元数据不能作为互斥依据；
- 重复 `release()` 安全，锁失败统一抛 `WorkspaceBusyError`，其它 I/O 错误统一抛 `WorkspaceError`。

- [x] **Step 4: Run tests to verify GREEN**

Run: `python -m pytest tests/test_workspace.py -q`

Expected: PASS。

- [x] **Step 5: Self-review and commit**

检查 Windows 单字节锁初始化、异常时句柄关闭、ID 不进入路径和子进程确实竞争同一个锁，然后提交：

```bash
git add src/icode/workspace.py tests/test_workspace.py
git commit -m "feat: add cross-process ticket leases"
```

### Task 2: Git worktree、非 Git 快照与保护策略

**状态**
- [x] 任务完成

**Dependencies:** Task 1
**Parallelizable:** No (复用 Task 1 的租约并定义 Task 3 的 session 接口)

- [x] **Step 1: Write the failing workspace tests**

在 `tests/test_workspace.py` 增加：

```python
def test_git_session_uses_detached_worktree_and_keeps_source_clean(self):
    before = _git(self.source, "status", "--porcelain=v1", "--untracked-files=all")
    with self.manager.open("ticket-1", "run-1") as session:
        self.assertNotEqual(session.workspace_root, self.source.resolve())
        (session.workspace_root / "tracked.txt").write_text("changed\n", encoding="utf-8")
        self.assertEqual((self.source / "tracked.txt").read_text(encoding="utf-8"), "base\n")
        self.assertEqual(session.kind, "git_worktree")
    self.assertEqual(
        _git(self.source, "status", "--porcelain=v1", "--untracked-files=all"),
        before,
    )

def test_non_git_session_is_a_manifested_snapshot(self):
    with manager.open("ticket-2", "run-2") as session:
        self.assertEqual(session.kind, "snapshot")
        self.assertEqual((session.workspace_root / "input.txt").read_text(), "source")
        self.assertTrue(session.manifest_path.is_file())

def test_existing_workspace_with_mismatched_manifest_fails_closed(self):
    ...

def test_session_policy_protects_source_git_control_and_runtime_paths(self):
    policy = session.policy(step="code")
    self.assertEqual(policy.write_roots, (session.workspace_root,))
    for path in session.protected_paths:
        self.assertIn(path, policy.protected_paths)
        self.assertTrue(any(path == root or path.is_relative_to(root)
                            for root in policy.deny_write_roots))
```

同时覆盖：不存在源目录、源路径为文件、checkout 路径冲突、外部符号链接、Git 命令失败、同 ticket 复用同一已验证工作区。

- [x] **Step 2: Run focused tests to verify RED**

Run: `python -m pytest tests/test_workspace.py -q`

Expected: FAIL，缺少 `WorkspaceManager`/`WorkspaceSession`。

- [x] **Step 3: Implement Workspace Manager**

在 `src/icode/workspace.py` 增加：

```python
WORKSPACE_SCHEMA_VERSION = 1

@dataclass
class WorkspaceSession:
    project_id: str
    ticket_id: str
    run_id: str
    kind: Literal["git_worktree", "snapshot"]
    source_root: Path
    workspace_root: Path
    runtime_root: Path
    receipts_root: Path
    manifest_path: Path
    protected_paths: tuple[Path, ...]
    lease: TicketLease

    def policy(self, *, step: str, process_limit: int = 64,
               wall_timeout_seconds: int = 1800,
               output_limit_bytes: int = 16 * 1024 * 1024) -> SandboxPolicy: ...
    def close(self) -> None: ...

class WorkspaceManager:
    def __init__(self, source_root: Path, data_root: Path,
                 project_id: str, *, extra_protected_paths: Iterable[Path] = ()): ...
    def open(self, ticket_id: str, run_id: str) -> WorkspaceSession: ...
```

约束：

- `default_data_root()` 仅用标准库按 Windows/macOS/XDG 规则返回用户数据目录，并支持 `ICODE_DATA_HOME` 显式覆盖；
- 目录布局固定为 `workspaces/<project-hash>/<ticket-hash>/{checkout,runtime,receipts,workspace.json}`；
- Git 源使用宿主执行的 `git worktree add --detach <checkout> <source-HEAD>`，记录 Git 顶层、common gitdir、revision 和源内相对子目录；
- 非 Git 源先复制到同父临时目录，再原子改名；拒绝解析后离开源根的符号链接和特殊文件；清单包含相对路径、类型、大小与 SHA-256，并计算总清单哈希；
- 已存在目录必须完整匹配 schema、项目、ticket、规范化源路径、kind 和 revision/清单，否则 fail-closed，禁止删除或覆盖未知目录；
- `protected_paths` 至少包含原始源根、原 `.git`/common gitdir、原 `.icode_output`、任务 checkout 内 `.git`、runtime、receipts 和额外保护路径；
- `policy()` 使用 R2.0 `SandboxPolicy`，只允许读写 checkout，默认断网，并把全部保护路径纳入 deny-write/protected；不声称已经执行原生隔离；
- 任何创建失败都释放租约，且只清理由本次创建、位于计算后 ticket 根内的临时目录。

- [x] **Step 4: Run focused tests to verify GREEN**

Run: `python -m pytest tests/test_workspace.py -q`

Expected: PASS。

- [x] **Step 5: Run policy regression and commit**

Run: `python -m pytest tests/test_workspace.py tests/test_sandbox_policy.py tests/test_conformance.py -q`

Expected: PASS。

```bash
git add src/icode/workspace.py tests/test_workspace.py
git commit -m "feat: create isolated ticket workspaces"
```

### Task 3: 自主执行生命周期接入

**状态**
- [ ] 任务完成

**Dependencies:** Task 2
**Parallelizable:** No (依赖稳定的 WorkspaceSession 生命周期)

- [ ] **Step 1: Write failing autonomy tests**

修改 `tests/test_autonomy.py` 与 `tests/test_workbench.py`，增加：

```python
def test_autonomous_run_executes_in_ticket_workspace_and_releases_it(self):
    manager = AutonomyManager(
        self.service,
        executor=executor,
        enabled=True,
        workspace_manager=workspace_manager,
    )
    manager.handle_intent(ticket_id, {"intent": "start", "request_id": "start-1"})
    self.assertTrue(executor.started.wait(2))
    self.assertEqual(executor.context.workspace, expected_checkout)
    ...
    self.assertTrue(workspace_manager.can_reacquire(ticket_id))

def test_workspace_busy_rejects_before_worker_or_state_transition(self): ...
def test_workspace_setup_failure_uses_stable_error_and_starts_no_worker(self): ...
def test_worker_start_failure_releases_workspace_session(self): ...
def test_workbench_autonomous_mode_constructs_default_workspace_manager(self): ...
def test_workbench_interactive_mode_does_not_create_workspace_data(self): ...
```

- [ ] **Step 2: Run tests to verify RED**

Run: `python -m pytest tests/test_autonomy.py tests/test_workbench.py -q`

Expected: FAIL，构造器不接受 `workspace_manager`，执行上下文仍指向原工程。

- [ ] **Step 3: Implement lifecycle binding**

修改 `src/icode/autonomy.py`：

- `AutonomyManager.__init__` 新增可选 `workspace_manager: WorkspaceManager | None`；
- `RunControl` 保存可选 `WorkspaceSession`；
- `_start_or_resume_locked` 在持久化 `starting` 前取得 session，busy 映射为 `AutonomyError("workspace_busy", ...)`，其它 setup 错误映射为 `workspace_setup_failed`；
- `_execution_context` 在当前 control 有 session 时使用 `session.workspace_root`，`out_dir` 仍指向宿主控制面的真实工单目录；
- worker 启动失败、正常终态、暂停/取消、异常和 shutdown 的所有释放路径统一经 `_release_worker_locked` 关闭 session；
- 保留 `_PROCESS_WORKERS` 作为同进程快速门禁，跨进程正确性由 TicketLease 提供；
- 没有注入 Workspace Manager 时行为完全兼容现有调用方。

修改 `src/icode/workbench.py`：仅当 `enable_autonomous` 且 executor 可用时，根据可信 workspace、project ID 与默认用户数据根构造 `WorkspaceManager`；交互模式不创建目录。把 `vendor/icode-skill`/实际 skill root 作为额外保护路径传入。

- [ ] **Step 4: Run tests to verify GREEN**

Run: `python -m pytest tests/test_autonomy.py tests/test_workbench.py tests/test_workspace.py -q`

Expected: PASS。

- [ ] **Step 5: Run related regression and commit**

Run: `python -m pytest tests/test_chain_offline.py tests/test_guard.py tests/test_runner.py tests/test_autonomy.py tests/test_workbench.py tests/test_workspace.py -q`

Expected: PASS。

```bash
git add src/icode/autonomy.py src/icode/workbench.py tests/test_autonomy.py tests/test_workbench.py
git commit -m "feat: bind autonomous runs to isolated workspaces"
```

### Task 4: 文档、打包与阶段验收

**状态**
- [ ] 任务完成

**Dependencies:** Task 3
**Parallelizable:** No (只能记录实际已通过的行为)

- [ ] **Step 1: Add the failing documentation contract test**

在 `tests/test_workspace.py` 增加路线图断言，要求同时出现：

```python
roadmap = (REPO_ROOT / "docs" / "roadmap.md").read_text(encoding="utf-8")
self.assertIn("R2.1", roadmap)
self.assertIn("跨进程租约", roadmap)
self.assertIn("不等于操作系统强制隔离", roadmap)
```

- [ ] **Step 2: Run test to verify RED**

Run: `python -m pytest tests/test_workspace.py -q`

Expected: FAIL，路线图尚未记录 R2.1 已验证边界。

- [ ] **Step 3: Update roadmap without changing homepage claims**

修改 `docs/roadmap.md`：

- 把 R2.1 标为完成并列出真实退出证据：跨进程锁测试、Git 原工作树内容/status 不变、非 Git 清单快照、受保护路径策略；
- 明确这些是宿主工作区边界和策略合同，**不等于操作系统强制隔离**；
- R2.2–R2.5 继续保持未完成；
- 官网不添加阶段标签，继续只展示最终能力和效果。

- [ ] **Step 4: Run complete validation**

Run:

```bash
python -m pytest -q
python -m compileall -q src tests
python scripts/preflight.py
python scripts/check_site.py
python scripts/check_governance.py
git diff --check
```

Expected: 全部 PASS；仅保留项目既有条件性 skip。

- [ ] **Step 5: Verify the installed wheel**

Run:

```bash
python -m build --wheel --outdir /tmp/icode-r21-dist
python -m venv /tmp/icode-r21-venv
/tmp/icode-r21-venv/bin/pip install /tmp/icode-r21-dist/icode_agent-*.whl
/tmp/icode-r21-venv/bin/python -c "from icode.workspace import WorkspaceManager, TicketLease; print('R2.1 wheel OK')"
```

Expected: `R2.1 wheel OK`。

- [ ] **Step 6: Commit**

```bash
git add docs/roadmap.md tests/test_workspace.py docs/nbl/plans/2026-09-23-r2-workspace-lease.md
git commit -m "docs: record R2.1 workspace guarantees"
```

---

## 自检结果

- 规格覆盖：Git、非 Git、跨进程互斥、受保护目录、Autonomy 接入、兼容模式与阶段文档均有对应任务。
- 占位符扫描：省略号只出现在测试骨架的局部 setup，实施约束和公开接口均已明确；实现任务不得保留占位符。
- 类型一致性：全计划统一使用 `WorkspaceManager.open()`、`WorkspaceSession.workspace_root`、`WorkspaceSession.policy()`、`TicketLease.acquire()`。

**Execution Mode:** serial
