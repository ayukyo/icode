# LA-2a 策略步骤保留宿主会话实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `nbl.superpowers:nbl.subagent-driven-development` to implement this serial plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 每阶段一个实施写者；独立 SPEC 后由不同审查者做 QUALITY；root 最终自检、完整守护及 main 发布。本文只交付计划，不能自动开始 CODE。

**Goal:** 让合法身份的非工程策略步骤借用宿主原 WorkspaceSession，独立保留 Git 工具资格及 code/deepcheck 原身份拒绝。

**Architecture:** 只在 `run_chain` 循环内以已有 SandboxPolicy/WorkspaceSession 身份字段筛选 `policy_session`，非 code/deepcheck 步骤传原对象。工程步骤仍传原 workspace_session，包括错误对象，让 runner 原门负责拒绝；不建新 policy、FD 或租约，不修改工具权限与后端。

**Tech Stack:** Python 3.11/3.12、stdlib unittest/mock、现有 chain/runner/WorkspaceSession/SandboxPolicy；无新增依赖。

---

冻结 [设计](../specs/2026-10-12-chain-policy-session-design.md) 经独立 SPEC→不同 QUALITY 各 C0/I0/M0。读取时 main 为 `f648812`；调用链源基线 `8b1afd4`，LA-1 软件诊断已发布。root已完整自审计划并修正精确发布守护；fresh计划SPEC→不同QUALITY各C0/I0/M0，审查候选SHA256为 `558dce26eb4bdaefb6369beba948868ff66e81db300d0975d140ba2b85513b23`。两者各自纯内存演练确认旧源码新七方法13断言FAIL/0ERROR、原四方法通过、最小内存补丁后11方法通过；该记录不是磁盘TDD或原生证据。随后实际磁盘TDD、11方法GREEN、70项关联回归与fresh实际CODE SPEC→不同QUALITY均通过，详见Task1–3记录；Task4完整preflight/main发布、原生安装、模型与真实broker仍未验收。三问及 root sequential-thinking 104–109 分别记录设计与实施风险边界。

文件职责和边界：

| 文件 | 操作和职责 |
| --- | --- |
| `src/icode/chain.py` | 唯一生产源码改动：删 Git 专用筛选，换身份筛选与下游实参；移除不再用的 GitWorkspaceIdentity import |
| `tests/test_chain.py` | 保留原四方法；追加下面完整 class，真实调用 run_chain，记录下游实参；真实 runner 早拒错和工具资格负控 |
| 本计划 | root 登记实际 RED/GREEN、审查、守护与发布 SHA；不是实现证据 |
| `src/icode/autonomy.py`、`runner.py`、`tools/base.py`、`tools/builtin.py`、`workspace.py` | 只读关联核验；不修改 |
| Windows sibling 新文件 | 另一实施片所有；禁止混入本片暂存或修改 |

无需新测试文件：原 `temp_workspace`、StepReport、GitWorkspaceIdentity/WorkspaceSession 构造足够；新 class 将同一既有构造局部复用，无 WorkspaceManager、Git init、helper 编译或真实 FD 创建。`lease` 是 Mock，只验证 chain 不释放借用对象。没有原生 FD 的测试 session 不授 FD 稳定/cleanup 或准入信用。

## Task 1：冻结测试合同，先取得真实断言 RED

状态：已完成。唯一测试writer只追加测试后停止；root独立磁盘RED两方法13 assertion FAIL/0ERROR（exit1），原四方法4通过（exit0）。旧chain SHA256 `2ff2e579a3a5a32269ef075a675a3a639b95bf89f37dfb96dc40e38c2e18dba3`，测试候选 `1837e7c64ec3137b3b3b1aae7a569a45413e40965153be0c713fbe37a5ad44e5`。writer实际全新七方法13FAIL/0ERROR，其余安全负控通过；不借用先前纯内存演练作为此RED。以下为执行合同原文。

**Dependencies:** 冻结设计、计划 root self-review、fresh 计划 SPEC→不同 QUALITY 均 C0/I0/M0。
**Parallelizable:** No（同一测试文件唯一写者；RED 必须在旧生产源码上完成）。

- [x] 完整回读设计与实际 `run_chain`、`NativeChainExecutor.execute`、`run_contract_step`/`_contract_plan_error`/`_run_agent`、ToolContext、`_git_status_available`/`git_status`、WorkspaceSession.policy/close 及原 `tests/test_chain.py`。核对 session.owner 与参数传递/Git授权/执行授权的三个边界。
- [x] 原 `tests/test_chain.py` import 区增加以下 imports（既有 `patch` import 改为 `Mock, patch`，其它 imports 保留），并在文件末追加完整 class。先只写测试，chain.py 保持原实现。

```python
import sys
from dataclasses import replace
from unittest.mock import Mock, patch

from icode import runner
from icode.engineering_verification import VerificationCheck, VerificationPlan
from icode.isolation import LandlockSandbox
from icode.tools.base import ToolContext
from icode.tools.builtin import _git_status_available, default_registry, git_status


class TestChainPolicySessionForwarding(unittest.TestCase):
    POLICY_STEPS = ("plan", "audit", "merge", "review")

    def _session(self, root, *, kind="snapshot"):
        identity = None
        protected = ()
        if kind == "git_worktree":
            identity = GitWorkspaceIdentity(
                checkout_root=root, code_root=root, workspace_root=root,
                top_level=root, common_dir=root / "common", git_dir=root / "git",
                revision="a" * 40, identity_token="secret",
                source_relative_path=Path("."),
            )
            protected = (root / ".git", identity.common_dir)
        return WorkspaceSession(
            project_id="project", ticket_id="ticket", run_id="run-1",
            kind=kind, source_root=root, workspace_root=root,
            runtime_root=root / "runtime", receipts_root=root / "receipts",
            manifest_path=root / "workspace.json", protected_paths=protected,
            lease=Mock(), git_status_identity=identity,
        )

    def _invoke(self, root, step, policy, session, *, record=True, plan=None):
        calls = []

        def step_runner(*args, **kwargs):
            calls.append(kwargs)
            return StepReport(step=step, ok=False, out_dir="", error="stop")

        with patch("icode.chain.ControlPlane"), patch(
            "icode.chain.ContractSet.load", return_value=object(),
        ), patch("icode.chain._snapshot", return_value={}):
            kwargs = dict(
                backend=object(), workspace=root, ticket_id="ticket",
                requirement="policy session", steps=(step,), policy=policy,
                workspace_session=session, verification_plan=plan,
            )
            settings = SimpleNamespace(gates_json=root / "gates.json")
            if record:
                with patch("icode.chain.run_contract_step", side_effect=step_runner):
                    report = run_chain(settings, **kwargs)
            else:
                # Leave run_contract_step real: its early identity gate must fire.
                with patch.object(runner, "ControlPlane") as downstream_cp:
                    report = run_chain(settings, **kwargs)
                    downstream_cp.assert_not_called()
        return report, calls

    def test_snapshot_and_git_policy_steps_borrow_original_objects(self):
        with temp_workspace() as root:
            for kind in ("snapshot", "git_worktree"):
                session = self._session(root, kind=kind)
                for step in self.POLICY_STEPS:
                    with self.subTest(kind=kind, step=step), patch.object(
                        session, "close",
                    ) as close:
                        policy = session.policy(step)
                        report, calls = self._invoke(root, step, policy, session)
                        self.assertEqual(len(calls), 1)
                        self.assertIs(calls[0]["workspace_session"], session)
                        self.assertIs(calls[0]["policy"], policy)
                        self.assertEqual(report.reason, "stop")
                        close.assert_not_called()
                        session.lease.release.assert_not_called()

    def test_custom_resource_policy_is_not_replaced_or_git_filtered(self):
        with temp_workspace() as root:
            for kind in ("snapshot", "git_worktree"):
                session = self._session(root, kind=kind)
                for step in self.POLICY_STEPS:
                    with self.subTest(kind=kind, step=step):
                        policy = session.policy(
                            step, process_limit=8, wall_timeout_seconds=30,
                            output_limit_bytes=65536,
                        )
                        self.assertNotEqual(policy, session.policy(step))
                        _, calls = self._invoke(root, step, policy, session)
                        self.assertEqual(len(calls), 1)
                        self.assertIs(calls[0]["workspace_session"], session)
                        self.assertIs(calls[0]["policy"], policy)
                        session.lease.release.assert_not_called()

    def test_nonengineering_invalid_session_or_missing_policy_is_none(self):
        with temp_workspace() as root:
            for step in self.POLICY_STEPS:
                session = self._session(root)
                policy = session.policy(step)
                cases = [("absent", None), ("not-session", object())]
                for label, changes in (
                    ("stale-run", {"run_id": "stale"}),
                    ("wrong-ticket", {"ticket_id": "other"}),
                    ("wrong-root", {"workspace_root": root / "other"}),
                ):
                    cases.append((label, replace(session, **changes)))
                for label, candidate in cases:
                    with self.subTest(step=step, label=label):
                        _, calls = self._invoke(root, step, policy, candidate)
                        self.assertEqual(len(calls), 1)
                        self.assertIsNone(calls[0]["workspace_session"])
                _, calls = self._invoke(root, step, None, session)
                self.assertEqual(len(calls), 1)
                self.assertIsNone(calls[0]["workspace_session"])

    def test_engineering_preserves_matching_and_wrong_objects(self):
        with temp_workspace() as root:
            session = self._session(root)
            for step in ("code", "deepcheck"):
                policy = session.policy(step)
                for candidate in (
                    session, replace(session, run_id="wrong"),
                    replace(session, ticket_id="other"),
                    replace(session, workspace_root=root / "other"), object(),
                ):
                    with self.subTest(step=step, candidate=type(candidate).__name__):
                        _, calls = self._invoke(root, step, policy, candidate)
                        self.assertEqual(len(calls), 1)
                        self.assertIs(calls[0]["workspace_session"], candidate)
                        self.assertIs(calls[0]["policy"], policy)
                _, calls = self._invoke(root, step, None, session)
                self.assertIsNone(calls[0]["workspace_session"])

    def test_policy_wrong_step_ticket_or_root_keeps_chain_early_rejection(self):
        with temp_workspace() as root:
            session = self._session(root)
            policy = session.policy("plan")
            for changes in (
                {"step": "audit"}, {"ticket_id": "other"},
                {"workspace_root": root / "other", "read_roots": (root / "other",),
                 "write_roots": (root / "other",)},
            ):
                with self.subTest(changes=changes), patch(
                    "icode.chain.run_contract_step",
                ) as downstream:
                    with self.assertRaisesRegex(ValueError, "单步链路身份不匹配"):
                        self._invoke(root, "plan", replace(policy, **changes), session,
                                     record=False)
                    downstream.assert_not_called()

    def test_wrong_engineering_session_real_runner_refuses_before_cp(self):
        with temp_workspace() as root:
            session = self._session(root)
            check = VerificationCheck(
                "tests", "test", (sys.executable, "-B", "-m", "unittest"),
                "unittest_summary_v1",
            )
            plan = VerificationPlan(root, "run-1", "ticket", (check,))
            for step in ("code", "deepcheck"):
                for candidate in (replace(session, run_id="wrong"), object()):
                    with self.subTest(step=step, candidate=type(candidate).__name__):
                        report, calls = self._invoke(
                            root, step, session.policy(step), candidate,
                            record=False, plan=plan,
                        )
                        self.assertEqual(calls, [])
                        self.assertEqual(report.reason, "verification_session_identity_mismatch")
                        self.assertEqual(report.stopped_at, step)
                        self.assertFalse(report.delivered)

    def test_git_eligibility_remains_independent_of_session_forwarding(self):
        with temp_workspace() as root:
            session = self._session(root, kind="git_worktree")
            sandbox = LandlockSandbox("not-executed-helper")
            with patch("icode.tools.builtin.sys.platform", "linux"), patch(
                "icode.tools.builtin.execute_git_status",
            ) as broker:
                default = session.policy("plan")
                ctx = ToolContext(root=root, sandbox=sandbox, policy=default,
                                  workspace_session=session)
                self.assertTrue(_git_status_available(ctx))
                self.assertIn("git_status", default_registry(git_status_context=ctx).names())
                custom = session.policy("plan", process_limit=8,
                    wall_timeout_seconds=30, output_limit_bytes=65536)
                ctx.policy = custom
                self.assertFalse(_git_status_available(ctx))
                self.assertNotIn("git_status", default_registry(git_status_context=ctx).names())
                result = git_status(ctx)
                self.assertFalse(result.ok)
                self.assertEqual(result.meta["error"], "git_broker_unavailable")
                for step, read_only in (("review", False), ("plan", True), ("review", True)):
                    with self.subTest(step=step, read_only=read_only):
                        ctx.policy = session.policy(step)
                        ctx.read_only_workspace = read_only
                        self.assertFalse(_git_status_available(ctx))
                        self.assertNotIn("git_status", default_registry(git_status_context=ctx).names())
                        result = git_status(ctx)
                        self.assertFalse(result.ok)
                        self.assertEqual(result.meta["error"], "git_broker_unavailable")
                broker.assert_not_called()
```

- [x] RED（旧源码、新测试）执行：

```bash
./.venv/bin/python -m unittest -v tests.test_chain.TestChainPolicySessionForwarding.test_snapshot_and_git_policy_steps_borrow_original_objects tests.test_chain.TestChainPolicySessionForwarding.test_custom_resource_policy_is_not_replaced_or_git_filtered
```

预期 2 方法正常加载，13 个 subTest 断言 FAIL、0 ERROR：snapshot 默认四步4FAIL、Git默认review1FAIL、两类custom四步8FAIL。具体失败是 `assertIs(..., session)` 收到 None；不能用 ImportError、属性/fixture ERROR 当 RED。若计数不同先定位实际对象/源代码，不调整期望来迎合生产缺口。
- [x] 在尚未改 chain 的同一候选运行原四方法，确保已有合同 baseline：

```bash
./.venv/bin/python -m unittest -v tests.test_chain.TestChainReviewArtifactHonesty tests.test_chain.TestChainGitIdentityForwarding
```

预期 4 方法、0 FAIL/ERROR。新 class 的安全负控可先运行，全7方法总 RED 仍只允许上述13个断言失败。记录真实命令、源码/测试候选、退出码、FAIL/ERROR及临时 fixture 范围；不记原生或模型通过。

## Task 2：最小 policy_session 身份筛选与传递

状态：已完成。不同fresh源码writer独立复现同磁盘RED后，仅改chain三处并停止；全11方法通过，测试hash不变。最终chain SHA256 `28244144023c85548ca0e9bcb68235a935d648d53b8367ae80cde67f746508de`。root全文回读实际测试与生产差异，并独立11方法通过、两文件compileall-j1和diff检查exit0。root实施前sequential-thinking107–109将源码范围/权限/所有权/守护风险分账，没有重建会话或新增授权。以下为执行合同原文。

**Dependencies:** Task 1 有效 RED 与原四方法通过。
**Parallelizable:** No（只在 RED 后替换单一生产函数，并取得同一候选 GREEN）。

- [x] `src/icode/chain.py` import 从 `from .workspace import GitWorkspaceIdentity, WorkspaceSession` 改为：

```python
from .workspace import WorkspaceSession
```

- [x] 将循环起始从 `git_status_session = None` 至旧筛选 try/except 全部替换为以下完整代码；`instructions` 及后续 callback 原样保留：

```python
        # Borrow the host session by policy identity; Git authorization is
        # independently enforced by the tool registry and broker boundary.
        policy_session = None
        if (
            isinstance(policy, SandboxPolicy)
            and isinstance(workspace_session, WorkspaceSession)
            and workspace_session.ticket_id == ticket_id == policy.ticket_id
            and workspace_session.run_id == policy.run_id
            and workspace_session.workspace_root == policy.workspace_root == workspace
            and policy.step == name
        ):
            policy_session = workspace_session
```

- [x] `run_contract_step` 的 `workspace_session` 实参只改 else 为 `policy_session`，完整实参为：

```python
            workspace_session=(workspace_session if policy is not None and name in ("code", "deepcheck")
                               else policy_session),
```

不调用 `session.policy`，不要求 kind/git identity/default policy 等值，不把工程 wrong 对象筛成 None；不新增异常捕获、不重试副作用、不改接口/owner/ready。前置 policy.step/root/ticket 检查仍在 loop 前拒绝。消费边界负责 FD 有效性和执行资格。
- [x] 原先 RED 命令再次执行，预期 2 方法0FAIL/ERROR；然后完整本文件：

```bash
./.venv/bin/python -m unittest -v tests.test_chain
git diff --check -- src/icode/chain.py tests/test_chain.py
```

预期总11方法（原4+新7）、0FAIL/ERROR，diff 检查 exit0；不得借用此前内存 patch 演练结果作为此磁盘候选 GREEN。

## Task 3：关联安全门、独立实现审查

状态：软件关联及fresh审查已完成，完整守护与发布仍待Task4。root实际执行本节第一命令4方法通过；第二命令66方法通过，均0FAIL/ERROR/skip。fresh实际CODE SPEC→不同QUALITY各C0/I0/M0，各自独立磁盘11方法通过，并只读核验Git默认等值门、Reviewer独立只读wrapper/pin与会话FD消费门。SPEC把三个生产改动反向还原后精确匹配旧源码hash，核实没有扩散；QUALITY另补工程错ticket/root与无FD拒绝五例。后两者均非native或真实payload验证。审查绑定Task2上述源码/测试hash，全文计划演练不充当实现GREEN。以下为执行合同原文。

**Dependencies:** Task 2 同一磁盘候选 GREEN。
**Parallelizable:** No（SPEC 完成后才由不同 QUALITY 审查；修改则重新有效 RED/GREEN并 fresh SPEC→不同QUALITY）。

- [x] 运行真实 runner 工程早拒错与原 Reviewer 应用层拒写/只读包装回归：

```bash
./.venv/bin/python -m unittest -v tests.test_contract_engineering.TestContractEngineering.test_session_identity_mismatch_refuses_before_cp tests.test_contract_engineering.TestContractEngineering.test_reviewer_accepts_policy_and_session_as_explicit_optional_inputs tests.test_runner.TestReviewStepReadOnlyContext.test_review阶段无隔离沙箱时命令在启动前拒绝且不产生标记 tests.test_runner.TestReviewStepReadOnlyContext.test_策略化review也拒绝源码写入
./.venv/bin/python -m unittest -v tests.test_autonomy.TestNativeChainExecutor tests.test_autonomy.TestNativePythonPreset tests.test_tools tests.test_reviewer
```

预期无 FAIL/ERROR；既有平台/原生 skip 逐项登记，不能算通过。第一命令4方法没有新 native/helper/broker payload；第二命令既有套件可能包含平台条件原生项目，root 必须遵守当前执行授权：当前只计划阶段不运行，实施守护按已授权流程执行。record-only chain 测试不证明拒错；新 `test_wrong_engineering_session_real_runner_refuses_before_cp` 与原负控才证明该早拒绝边界。新 Git 门双控只运行谓词/registry和直接拒绝，broker Mock assert_not_called，不授真实 Git 执行信用。
- [x] fresh 独立 SPEC 逐项对冻结设计、磁盘源码/测试、实际 RED/GREEN核验：正常 Git/snapshot/custompolicy 全四步；错身份/legacy None；code/deepcheck 原对象；owner不close；review与资源policy的Git限制。要求 C0/I0/M0，指出源文件与具体测试证据。
- [x] 由不同审查者 fresh QUALITY 审查相同候选：无权限扩大、无可写Reviewer回退、无吞KI/SE、无重复FD或策略重建、无跨片修改；检查原 runner `_run_agent` 仍派生 read_only policy、Scope.allowed_write_roots=()、隐藏 ticket roots；ToolContext.wrap_command仍走独立 readonly wrapper/pin，传session不等于Reviewer借FD。要求 C0/I0/M0；源码改动后不能复用前候选审查。
- [x] root 按冻结设计自审七维，实际结果写入本计划；暂缺证据标未验收，不写“异常全覆盖/可运行100%”。实现审查不能被上游研究或测试通过替代。

## Task 4：root 完整守护、精确 whitelist main 发布

**Dependencies:** Task 3 同一候选 fresh SPEC→不同 QUALITY各 C0/I0/M0及root七维通过。
**Parallelizable:** No（完整守护、fresh提交前守护与发布串行；源码若变从所需门重跑）。

- [ ] root 确认当前分支和差异，不回退或覆盖其它片。完整守护精确命令：

```bash
git branch --show-current
git status --short
git diff --check
./.venv/bin/python -m compileall -q -j1 src scripts tests
./.venv/bin/python scripts/preflight.py
./.venv/bin/python scripts/check_site.py
./.venv/bin/python scripts/preflight.py --only secrets
./.venv/bin/python scripts/preflight.py --only submodule
```

预期分支 `main`；其余必需exit0，完整 preflight必须三道全通过（secrets、submodule、tests），不能只 `--only tests` 或旧软件结果冒充。不读取、展示key正文；secret守护只是既有扫描。完整测试原生跳过/运行分账，不提升 ready，不授LA-2整体、installed x64/arm64、模型90%或R2/R3信用。若完整守护出现既有native问题如Win10035/wait_expired，保留原fail-closed分类，不降级或放行。
- [ ] root 完整回读 staged 精确 whitelist。root本轮核定六路径：两个代码文件、此计划和冻结设计、持续对照中的本轮证据，以及LA-1设计头部已发布状态纠正；后两者仅记录事实，不修改LA-1合同。不使用 `git add .`：

```bash
git add -f -- src/icode/chain.py tests/test_chain.py docs/nbl/plans/2026-10-12-chain-policy-session.md docs/nbl/specs/2026-10-12-chain-policy-session-design.md docs/agent-landscape-live.md docs/nbl/specs/2026-10-12-linux-admission-receipt-design.md
git diff --cached --name-only
git diff --cached --check
git diff --cached -- src/icode/chain.py tests/test_chain.py docs/nbl/plans/2026-10-12-chain-policy-session.md docs/nbl/specs/2026-10-12-chain-policy-session-design.md docs/agent-landscape-live.md docs/nbl/specs/2026-10-12-linux-admission-receipt-design.md
git commit -m "fix(chain): preserve matching policy workspace sessions"
git push origin main
git rev-parse HEAD
```

只有 root 且既有阶段发布授权满足时执行上述Git写；计划作者、实施者、审查者不得执行。docs/nbl 草稿受忽略规则影响，故仅对六个明确路径使用 `-f`；不得扩大路径。各命令分别检查退出码，add 失败不能接着 commit/push。cached 名单必须与本片六路径 whitelist 完全相等，并逐文件核对索引与已审查磁盘字节一致；若此前其它片已暂存，先协调owner，不替其取消暂存或混提交。若 branch、守护、审查不满足就停在具体阻断，禁止推送。记录最终精确 SHA、守护起止时间及真实统计，不能把预计统计当实测。

## 覆盖与交付记录规则

| 设计验收项 | 本计划证据 |
| --- | --- |
| snapshot plan/audit/merge/review 有效 RED | Task1真实 run_chain recorder13断言FAIL中的snapshot/default4 |
| Git/default 与 custom原session/policy、不close | 新class前两方法及原Git正控 |
| 无policy/非会话/stale/ticket/root | 第3方法、原Git stale/no-policy；错policy仍前置拒绝第5方法 |
| 工程原参数+真实拒错 | 第4方法实参；第6方法real runner+原test_contract_engineering负控 |
| review/read_only无Git、customGitFalse/defaultTrue | 第7方法原工具谓词/registry/直接拒绝及broker不调用；Task3原readonly回归 |
| Git/FD/准备/资源/CLI/MCP不放宽 | Task2最小patch、Task3独立SPEC→不同QUALITY、Task4root守护 |

【架构级自检报告】（计划文本状态，实施后由root用实测更新）

- 语法/编译：代码块提供完整真实符号，尚未对实施候选 compileall。
- 依赖/调用链：autonomy→chain→runner→ToolContext传播规则明确；仅chain与test变更。
- 逻辑/边界：正常/错身份/缺policy/工程特殊分支均给具体测试；未实际TDD。
- 异常处理：源码不新增try/retry/catch；原runner和工具fail-closed保留，待实际回归。
- 关联模块：独立Git资格、只读reviewer派生与pin不改；Windows片不纳入。
- 兼容安全：原4方法和关联负控命令明确；待实测与独立审查。
- 可运行性：只有计划文本，软件/原生/模型总体均未授通过；禁止报告100%。

证据分账：文本AST/内存演练可以记为计划可演练，不是磁盘候选TDD；旧源码+新测试有效断言RED、完整最小patch后的GREEN、fresh候选审查、完整preflight、main发布各自登记。任何pure-in-memory验证记录必须注明载入源、测试方法、断言FAIL/ERROR、是否替身，不能替代实际实施或原生。本文不执行native、model、key、Git/CI写、fullpreflight、真实broker。

---

【架构级自检报告】（root 实际CODE候选）

- 语法/编译：chain/test compileall-j1、diff检查通过；模块11方法实际通过。
- 依赖/调用链：autonomy→chain→runner→ToolContext原签名保留，仅独立筛选和原引用传递。
- 逻辑/边界：root磁盘13断言RED→11GREEN；snapshot/Git/custom、错身份/无policy和工程原对象覆盖。
- 异常处理：无新增捕获/重试；真实runner在ControlPlane前拒工程错对象，4项原身份/readonly回归通过。
- 关联模块：66项autonomy/tools/reviewer回归通过；Git权限、Reviewer独立只读及owner关闭责任未改。
- 兼容安全：原四方法保留，fresh SPEC→不同QUALITY各零遗留；没有准入/ready/selector放宽。
- 可运行性：上述81项软件回归0FAIL/ERROR/skip；完整preflight session81741三道通过/exit0；GLOBAL SPEC→不同QUALITY零遗留。main发布、原生FD与产品准入仍未验收，不写100%。
**Execution Mode:** serial。需要真实调用链探索且不是机械改动，不能选inline；Task1→Task2→Task3→Task4均依赖前一候选门。只读研究可独立进行，但不并发写共享文件。计划 self-review及fresh SPEC→不同QUALITY由root先完成，本轮不会按技能handoff自动进入CODE。
