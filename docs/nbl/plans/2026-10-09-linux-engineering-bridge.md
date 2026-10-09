# Linux 工程桥接部分实施与剩余阻塞 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development (recommended) or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改生产准入的前提下，把真实 Linux plan 命令接到 CP operation、工程 receipt、fresh Reviewer 与独立 partial-pack 验证；实测普通步骤的现存阻塞，不伪称完整步骤成功。

**Architecture:** 使用真实 `WorkspaceManager(isolate_git_metadata=True)`、四个互不重叠的 owned 根、原 Landlock/helper/manager/私有通道和真实控制面。模型只提供明确标注的确定性协议 double，正控不替换 dispatch、资源回执、CP 或 Git tree；生产 Git 修复是外部先决条件。公共 resume 未决重放拒绝、内部 gate fresh-recorder 重入缺口、普通 inspection 的 Git 来源缺口分别记账。

**Tech Stack:** Python 标准库 unittest、Git fixture、现有 C helper（串行 cc）、systemd user scope/cgroup v2、Landlock/USER_NOTIF、固定 ICODE-SKILL 控制面。

---

日期：2026-10-09。本文是**实施计划，不是运行结果**。计划作者只写本文、只读核接口，运行测试/import/编译/安装/模型 HTTP 数均 0。基线 main `8d53670192e3e2cbfebaa0300d697fb3036308be`，vendor `1693651c1bd7daad3272eb054f0f81d6f254d08d`。实施时先登记实际新基线，不把本文旧行号当接口。

用户连续自主推进、main-only 授权覆盖技能的例行问答等待、worktree/分支与逐任务提交惯例。本文不创建 worktree、不发布；任务串行实施，全部软件门通过后由 root 正常提交推送 main。权限、失败关闭、独立审查与跨平台门不被该授权覆盖。

## 0. 已确认依赖与不可升级的信用

输入已完整阅读：

- [桥接设计](../specs/2026-10-09-linux-engineering-bridge-design.md)，SHA256 `75d9e8c25d99330e7d2d207d768c46a5eafc42d24d1b3ae9df3f35d42d0b9564`；root 通知已通过两位独立审查，作者不把设计内旧等待文字当当前结果。
- [配套定点研究](../specs/2026-10-09-linux-engineering-bridge-upstream-research.md)，SHA256 `dc84da3661550553f310429621775996e116ca61a04af0a76a07e9de9dbb8835`；只借鉴分层/失败关闭，不复制上游代码、不新增依赖。
- [root 已运行命令层记录](../specs/2026-10-09-linux-bridge-command-evidence.md)，SHA256 `eef02bdcfe84e51cc9c9eb515cc2cf5a1c92f87e9a437960f4497d04e0bebec3`：已有 40P/0F/E/skip、13.129s（25 quota + 15 violation）。这是旧 source L1 窗口，不是本计划的新运行，也没有保留该次 binary/manifest 摘要，不是 installed 证明。
- [外部 session-aware Git 修复设计](../specs/2026-10-09-session-git-tree-design.md)，SHA256 `cb50043d8314a8fd7793e3b4fae5d0f0171440390bc9f0866a43292911c2f679`。它的 13 向量由独立 slice 实施、验收；本片不重复造 Git 修复或改 tree double。

**G0（硬依赖）**：root 必须确认 session Git 修复的生产源码、callers、独立 SPEC/QUALITY、本地软件门实际通过，并登记其冻结 SHA。未过 G0，Task 1–3 不实施、不把 split code 根变成普通根、不移动 `.git`、不清空身份、不降 tree 断言。新源码接线后仍不支持 split result-commit binding，不授额外信用。

静态规划新发现的两个缺口已经先报告 root，并获 root 指示保留阻塞：

以下为初始设计诊断历史；G0/G1 当前已在独立分片验收并发布，现状见末尾发布交接与 Task2 更新。G2 仍保持原阻塞，不改写下表原始证据。

| ID | 实际来源与机制 | 本片能验证什么 | 必需剩余门 |
| --- | --- | --- | --- |
| G1：内部 gate 未决重入 | vendor `cmd_operation` 4845–4902 先返回相同 request 的 idempotent start，后判断同名未决；runner gate 只核 returned attempt 在 open_operations。fresh recorder 重置 occurrence 后，内部同 attempt gate 不是安全重试 API | 同 recorder 新 occurrence 的真实 ambiguous 拒绝；公共 resume 2658–2688 的 open/started action 拒绝。不得据此称任意内部 fresh-recorder 重入安全 | root 另立最小 production 修复设计与验收；不从 CP 幂等外推 payload 幂等，不在 test-only 片改 vendor |
| G2：普通 inspection 分离 Git 来源 | vendor `inspection_worklist.py:_repo` 114–120 只搜索 workspace 内 `.git`；split code 根返回 None，build_worklist 274–286 加真实 no-Git debt，311–314 得 partial；validate_worklist 与 CP success finish 严格拒绝 | 两个完整 runner 入口的实际部分证据与原 success 拒绝、保留 partial/debt。不能填虚假 reads 或删 debt | root 另立身份/范围设计及相应最小授权；code/deepcheck 完整成功正控继续 blocked |

root 后续 [admission-only 实际诊断](../specs/2026-10-09-linux-bridge-blockers.md) 已确认 G1：载荷执行数0，fresh recorder 相同 request 返回 already_applied、can_execute=True，原 recorder新 occurrence返回 gate_id=ambiguous_side_effect、can_execute=False、ambiguous字段却False。记录保留错误工单路径与错误 ambiguous 断言两次诊断失败历史；不是源码 RED/GREEN，不是实际 gate 重放载荷。本作者完整回读该记录，但未重复该诊断。

同一记录现 SHA256 `0fea61497092a63ae87bbfe73a87d38c981a410bedd3c89347f3082b66fa4f57` 也包含 root 后续实际 worklist 复现：借用现有 owned Git/manager fixture，原 vendor build/validate 命令 exit 0；workspace 为 checkout/code、父层有 `.git`，`_repo` 返回 None，原始 partial/no-affected-Git 债务保留，validate 同时报告未接受的债务和缺少 Read。它没有执行完整 CP 步骤、填 reads、删债务或模型；不能把该 helper 诊断当完整 step-finish 负控，更不能写成完整成功。本作者仅回读，不重跑。

G1/G2 不是本片批准的修改范围。18 向量表仍保留全部要求，CP-02/STEP-01 不得整体 PASS；即使其已实现负控通过也只记子向量通过。不得改 Landlock `policy_contract_ready=False`，不放行 Native、不改 native/vendor/schema/权限/依赖，不读 KEY 或猜模型 endpoint。

## 文件责任与执行顺序

| 文件 | 责任 | 实施任务 |
| --- | --- | --- |
| `tests/test_linux_contract_engineering.py`（新增） | 实际 source helper + 真实 session/CP/plan/Reviewer/pack；独立 portable fixture 观察/保留守卫；正负例与 fixed 公共观察 | Task 1–3 |
| `scripts/run_native_probe_ci.py`（最小改动） | 先修原单用例 helper 的纯类 setup skip 分类，再给现有 Linux native job 追加一次具名桥接诊断；不映射 readiness 或 conformance 评分 | Task 4 |
| `tests/test_run_native_probe_ci.py`（最小改动） | 原 helper 的真实生命周期守卫先 RED→GREEN，再核实际 loader 单次选中与诊断三态/无评分 | Task 4 |
| 本计划与 root 的阶段证据文档 | 实际结果、G0/G1/G2、source/installed 分层 | Task 5，由 root 指定文档范围 |

不改 `run_workspace_ci.DEFAULT_MODULES`：新 class 有真实 Linux/helper/user-manager 前置条件，把它放便携 DEFAULT 会引入静态环境 skip。source 独立命令与 Linux 原生 job 才选择此 class；原完整 unittest discovery 仍按本机真实条件选中/skip，不能用 DEFAULT 零 skip 冒充 full 零 skip。

root新增静态兼容发现 I3：原计划顶层导入 `icode.linux_task_scope`，该模块的 `_DIRECTORY_FLAGS` 在导入时求值 `os.O_DIRECTORY/O_NOFOLLOW/O_CLOEXEC`；class级 skip 来不及保护 Windows discovery。Python 3.11 官方说明 `O_CLOEXEC` 仅Unix，`O_DIRECTORY/O_NOFOLLOW` 取决于底层C库。[官方 os flags 文档](https://docs.python.org/3.11/library/os.html#os.O_CLOEXEC) 同类关联还有原顶层 quota fixture → violation fixture → `linux_seccomp_notify` → `fcntl`，后者也仅Unix。[官方 fcntl 文档](https://docs.python.org/3.11/library/fcntl.html) 观察日期2026-10-09；这些是当前文本与官方可用性证据，不是Windows运行结果。

因此新test模块顶层不导入真实LinuxScope或旧quota fixture；真实 `_Bridge.__init__` 才加载它们，并保存原class `_scope_type` 与原owned检查 `_collection_assert`。native fixture仍使用真实生产class/既有收束检查，不用 `getattr(..., 0)` 掩盖标志。独立portable class显式设置 FakeScope/collection double，不依赖Linux模块，不给整个module/class加skip来绕过它。其第一个方法附加fresh进程import子场景：禁止这些Linux导入、移除Unix flags后导入新模块，明确只验证导入契约，不模拟整个Windows运行时；原生Windows的完整discovery与portable方法仍需后续实际CI验收。剩余top imports已定点核头部/引用：runner/autonomy/workspace/builtin、engineering_verification→linux_task_resource、execution_broker，以及公共fixture/support和其它已列标准接口；后两条真实LinuxScope/seccomp加载在调用期，resource模块没有顶层Unix flags求值。该核对不是全工程跨平台审计；如fresh import或Windowsfull发现其它阻塞须保留失败，不扩大production修复范围。

installed 片**不在本次写入范围**：现有 `run_native_wheel_ci.py` 建干净 venv、安装 wheel、移除 PYTHONPATH，并已有 `probe_installed_linux_violation_receipt.py`。本计划只给 source 信用；未来 installed 工程桥接须独立计划、fresh bundled skill/helper、实际 wheel/package/helper/manifest digest、非 checkout import、相同 venv/cwd 与真实 CP/pack，再接该调度一次。不得从本 source module 的 `tests._support` 注入 src 路径或复制测试到 venv 假装 installed。

## Task 1：真实 fixture 与 L2a code/deepcheck 工程窗口

**状态**

- [x] 任务完成：前置绑定修复后5项实际通过，接入独立双审、阶段20轮及全量复验通过；具体证据见末尾及绑定执行记录。

**Dependencies:** G0（外部 session Git 修复源码软件验收）
**Parallelizable:** No (生产接线依赖；本文件单 writer 与真实 scope 测试必须串行)

- [ ] **Step 1：写 source-only 的 fixture 与具名正控。**

新增文件以下完整公共支撑。`_Bridge` 不是 TestCase，不被 discovery 额外运行；观察包装调用原函数且原调用次数/参数/结果保持。只在标明 `injected_fault` 的负例消费修改后的结果。fixture 自己的 Git commit 只在 owned source 根，不操作 main checkout。正常已确认收束时回收 fixture；任何真实 scope 清理不确定保留 owned 根，公开日志只给摘要，不能输出其路径。

```python
"""Source-only Linux engineering bridge; Native and model quality stay unverified."""
from __future__ import annotations

import contextlib
from dataclasses import replace
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tests._support import REPO_ROOT, require_skill
from icode import runner
from icode.autonomy import ExecutionContext, NativeChainExecutor
from icode.backends import FakeBackend
from icode.budget import BudgetTracker
from icode.chain import set_code_files
from icode.checkpoint import Checkpointer
from icode.control import ControlPlane, ControlResult
from icode.contracts import ContractSet
from icode.engineering_verification import VerificationCheck, VerificationPlan
from icode.evidence import EvidenceError, build_evidence_pack, load_verification_receipts
from icode.handshake import next_out_dir
from icode.isolation import LandlockSandbox
from icode.loop import LoopConfig
from icode.operations import OperationRecorder
from icode.pack_verify import verify_pack
from icode.self_verify import evidence_fingerprint
from icode.tools import builtin
from icode.workspace import WorkspaceManager


def digest_bytes(content):
    return hashlib.sha256(content).hexdigest()


def canonical_digest(value):
    return digest_bytes(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                   ensure_ascii=False).encode("utf-8"))


def repository_provenance():
    result = {}
    for name, root in (("main", REPO_ROOT), ("vendor", REPO_ROOT / "vendor/icode-skill")):
        captured = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, timeout=10, check=False)
        if captured.returncode != 0:
            raise AssertionError("bridge_repository_identity_unavailable")
        result[name + "_sha"] = captured.stdout.decode("ascii", errors="strict").strip()
    files = ("src/icode/runner.py", "src/icode/workspace.py", "src/icode/isolation.py",
             "src/icode/linux_task_scope.py", "src/icode/engineering_verification.py",
             "src/icode/engineering_evidence.py", "src/icode/evidence.py",
             "src/icode/control.py", "src/icode/operations.py", "src/icode/chain.py",
             "vendor/icode-skill/tools/icode_control.py",
             "vendor/icode-skill/tools/inspection_worklist.py")
    result["source_sha256"] = {relative: digest_bytes((REPO_ROOT / relative).read_bytes())
                               for relative in files}
    return result


def test_source(body="self.assertEqual(changed.value, 1)"):
    return ("import unittest\nimport changed\nclass Value(unittest.TestCase):\n"
            " def test_value(self):\n  " + body + "\n")


def reviewer_script(*, read=True, submit=True, finding=None, denied=False):
    responses = []
    if read:
        responses.append({"tool_calls": [{"id": "read", "name": "read_file",
            "arguments": {"path": "../outside.py" if denied else "changed.py"}}]})
    if submit:
        responses.append({"tool_calls": [{"id": "submit", "name": "submit_review",
            "arguments": {"summary": "Read fixture value", "findings": [] if finding is None else [finding]}}]})
    responses.append("done")
    return responses


class _Bridge:
    def __init__(self, case, step="code", *, body=None, full=False,
                 timeout=5, output_limit=65536, later=False):
        # Linux-only imports belong to the real fixture, never module discovery.
        from icode.linux_task_scope import LinuxTaskScope
        from tests import test_linux_product_task_quota as quota_fixture
        self._scope_type = LinuxTaskScope
        self._collection_assert = quota_fixture.TestLinuxProductTaskQuota.assert_collected
        self.case, self.step = case, step
        self.raw = Path(tempfile.mkdtemp(prefix="icode-linux-bridge-")).resolve()
        self.raw_identity = (self.raw.stat().st_dev, self.raw.stat().st_ino)
        self.uncertain_cleanup = False
        self.pending_cleanup = False
        self.dispatch_started = 0
        self.observation_error = False
        self.source, self.data, self.control, self.pack_root = (
            self.raw / name for name in ("source", "data", "control", "pack"))
        for root in (self.source, self.data, self.control, self.pack_root):
            root.mkdir()
        case.addCleanup(self.close)
        self.session = None
        self.ticket_id, self.run_id = "LINUX-BRIDGE", "linux-bridge-run"
        (self.source / "changed.py").write_text("value = 0\n", encoding="utf-8")
        (self.source / "test_value.py").write_text(test_source() if body is None else body,
                                                  encoding="utf-8")
        commands = (("init", "-q"), ("add", "changed.py", "test_value.py"),
                    ("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                     "-c", "core.hooksPath=" + str(self.raw / "absent-hooks"),
                     "commit", "-qm", "owned bridge fixture"))
        for argv in commands:
            result = subprocess.run(["git", "-C", str(self.source), *argv],
                capture_output=True, timeout=10, check=False)
            case.assertEqual(result.returncode, 0, "fixture_git_initialization_failed")
        self.settings = case.settings
        self.manager = WorkspaceManager(self.source, self.data, "linux-bridge-project",
            extra_protected_paths=(self.settings.skill_root,), isolate_git_metadata=True)
        self.session = self.manager.open(self.ticket_id, self.run_id)
        self.root = self.session.workspace_root
        case.assertEqual(self.root, self.session.git_status_identity.code_root)
        case.assertFalse((self.root / ".git").exists())
        self.sandbox = LandlockSandbox(str(case.helper), manifest=str(case.manifest))
        self.policy = self.session.policy(step, process_limit=8,
            wall_timeout_seconds=30, output_limit_bytes=65536)
        self.sandbox.prepare_policy(self.policy)
        self.cp = ControlPlane(self.settings)
        self.directory = next_out_dir(self.control).resolve()
        if step == "deepcheck":
            # Final source and scope exist before the CP captures step inputs.
            (self.root / "changed.py").write_text("value = 1\n", encoding="utf-8")
        self.baseline = runner._snapshot(self.root)
        self.git_baseline = runner._read_task_git_state(self.root, workspace_session=self.session)
        check = VerificationCheck("python-unittest", "test",
            (sys.executable, "-I", "-B", "-X", "utf8", "-m", "unittest", "discover",
             "-s", str(self.root), "-t", str(self.root)), "unittest_summary_v1",
            timeout_seconds=timeout, output_limit_bytes=output_limit)
        checks = (check, replace(check, check_id="later")) if later else (check,)
        self.plan = VerificationPlan(self.root, self.run_id, self.ticket_id, checks,
                                     steps=(step,), platforms=("Linux",))
        if full:
            # Explicit fixture_seed only. No earlier model phase is claimed.
            self.directory.mkdir(parents=True)
            legacy = dict(ticket_id=self.ticket_id, requirement="change value",
                created_at="2026-10-09T00:00:00Z", status=step + "_in_progress",
                completed_steps=["1", "2", "3"], code_files=["changed.py"],
                workflow_gate_schema_version=1, thinking_gate_schema_version=1,
                mcp_gate_schema_version=2, semantic_decisions=[], requirement_deltas=[],
                project_path=str(self.root))
            (self.directory / ".ico_metadata.json").write_text(json.dumps(legacy), encoding="utf-8")
            case.assertTrue(self.cp.run("migration", "--dir", str(self.directory), "--apply").ok)
        else:
            created = self.cp.create(self.directory, ticket_id=self.ticket_id,
                requirement="change value", birth="plan", metadata_json=json.dumps({
                    "project_path": str(self.root), "code_files": ["changed.py"]}))
            case.assertTrue(created.ok)
        (self.directory / "03_plan_final.md").write_text("# Accepted fixture plan\n", encoding="utf-8")
        projection = self.cp.run("action-policy", "--dir", str(self.directory))
        case.assertEqual(projection.data.get("ticket_id"), self.ticket_id)
        case.assertEqual(projection.data.get("execution_root"), str(self.root))
        self.report = runner.StepReport(step, False, str(self.directory))
        self.attempt = ""
        self.scopes, self.actual_results, self.configured_facts = [], [], []
        self.operations = OperationRecorder(self.cp, self.directory, self.ticket_id, scope=step)
        if not full:
            self.attempt = self.cp.step_start(self.directory, step, ticket_id=self.ticket_id)
            if step == "code":
                (self.root / "changed.py").write_text("value = 1\n", encoding="utf-8")
            for occurrence, boundary in enumerate(ContractSet.load(self.settings.gates_json).step(step).required_checks, 1):
                checked = self.cp.step_check(self.directory, step, self.attempt,
                    boundary, ticket_id=self.ticket_id, occurrence=occurrence)
                case.assertEqual(checked.data.get("result"), "pass")

    def close(self):
        if self.session is not None:
            self.session.close()
        if self.pending_cleanup or self.uncertain_cleanup:
            print("linux-bridge-owned-fixture retained; cleanup_credit=none", flush=True)
            return
        if self.raw.exists():
            self.case.assertEqual((self.raw.stat().st_dev, self.raw.stat().st_ino), self.raw_identity)
            shutil.rmtree(self.raw)

    def events(self, kind):
        return [row for line in (self.directory / ".ico_events.jsonl").read_text(encoding="utf-8").splitlines()
                if (row := json.loads(line))["event_type"] == kind]

    @contextlib.contextmanager
    def observe(self, *, fault=None, after_command=None):
        original_configured = self._scope_type.configured
        original_dispatch = builtin._controlled_dispatch
        def configured(scope, deadline):
            original_return = original_configured(scope, deadline)
            # ACK is still pending: capture only the original validator's cache.
            # Keep original configured exceptions outside this observer-only try.
            try:
                self.scopes.append(scope)
                identities = tuple(scope._identities)
                if (len(identities) != 3 or any(len(identity) != 2 for identity in identities)
                        or scope._owned is not True or not scope._invocation):
                    raise ValueError("configured_memory_cache_incomplete")
                self.configured_facts.append(dict(unit_sha256=digest_bytes(scope.unit.encode()),
                    object_identity=list(identities[0]),
                    owned_identity_cache=[list(identity) for identity in identities],
                    payload_limit=scope.limit, systemd_version=scope.version,
                    invocation_sha256=digest_bytes(scope._invocation.encode()),
                    source="original_configured_validated_memory_cache"))
            except BaseException:
                # An observation fault must not turn into an ACK/configuration fault.
                self.observation_error = True
            return original_return
        def dispatch(*args, **kwargs):
            self.pending_cleanup = True
            self.dispatch_started += 1
            try:
                result = original_dispatch(*args, **kwargs)
                self.actual_results.append(result)
                if result.scope_cleanup_ok is not True:
                    self.uncertain_cleanup = True
                if after_command is not None:
                    after_command()
                return replace(result, **fault) if fault else result
            except BaseException:
                self.uncertain_cleanup = True
                raise
        with patch.object(self._scope_type, "configured", new=configured), \
             patch.object(builtin, "_controlled_dispatch", new=dispatch):
            try:
                yield
            except BaseException:
                if self.pending_cleanup:
                    self.uncertain_cleanup = True
                # No new I/O, retry or CP finish while propagating the original abort.
                raise
            else:
                self.confirm_collected()
                self.case.assertFalse(self.observation_error, "bridge_memory_observation_unavailable")

    def confirm_collected(self):
        if not self.pending_cleanup:
            return
        try:
            self.case.assertEqual(len(self.actual_results), self.dispatch_started,
                                  "dispatch_result_missing_cleanup_unknown")
            self.case.assertTrue(self.scopes, "actual_manager_scope_missing")
            self._collection_assert(self.case, self.scopes)
            self.case.assertTrue(all(result.scope_cleanup_ok is True for result in self.actual_results),
                                 "original_dispatch_cleanup_unconfirmed")
        except BaseException:
            self.uncertain_cleanup = True
            raise
        else:
            # This confirms the pending window only; earlier unknown is sticky.
            self.pending_cleanup = False

    def arguments(self, backend):
        return dict(cp=self.cp, out_dir=self.directory, ticket_id=self.ticket_id,
            step=self.step, attempt=self.attempt, report=self.report, plan=self.plan,
            policy=self.policy, sandbox=self.sandbox, workspace_session=self.session,
            workspace=self.root, baseline=self.baseline, git_baseline=self.git_baseline,
            operations=self.operations, backend=backend, requirement="change value",
            loop_config=LoopConfig(), budget_tracker=BudgetTracker())

    def run_gate(self, backend=None, *, fault=None, after_command=None):
        backend = backend if backend is not None else FakeBackend(reviewer_script())
        with self.observe(fault=fault, after_command=after_command):
            passed = runner._contract_engineering_gate(**self.arguments(backend))
        self.publish_observation(layer="injected_fault" if fault else "source_host_model_double")
        return passed, backend

    def receipt(self):
        paths = list(self.directory.glob(".engineering-*.json"))
        self.case.assertEqual(len(paths), 1)
        self.case.assertEqual(str(paths[0]), self.report.verification_receipt_path)
        return load_verification_receipts(paths)[0]

    def publish_observation(self, *, layer):
        identity = self.root.stat()
        rows = []
        for result in self.actual_results:
            rows.append(dict(exit_code=result.exit_code, error=result.error,
                resource_receipt_sha256=canonical_digest(result.resource_receipt),
                payload_started=result.resource_receipt.get("payload_started")
                    if type(result.resource_receipt) is dict else None,
                scope_cleanup_ok=result.scope_cleanup_ok,
                violation_observer_status=result.violation_observer_status))
        public = dict(layer=layer, step=self.step, run_id=self.run_id, ticket_id=self.ticket_id,
            repository=repository_provenance(),
            uid=os.getuid(), kernel=os.uname().release, architecture=os.uname().machine,
            helper_sha256=digest_bytes(self.case.helper.read_bytes()),
            manifest_sha256=digest_bytes(self.case.manifest.read_bytes()),
            native_source_sha256=digest_bytes((REPO_ROOT / "native/linux/icode_landlock.c").read_bytes()),
            python_version=sys.version.split()[0],
            python_lexical_path_sha256=digest_bytes(sys.executable.encode()),
            python_resolved_path_sha256=digest_bytes(str(Path(sys.executable).resolve()).encode()),
            workspace_identity=[identity.st_dev, identity.st_ino], plan_digest=self.plan.digest,
            environment_sha256=canonical_digest(self.plan.environment),
            executable_identity=self.plan.checks[0].executable_identity,
            cp_attempt=self.attempt, base_commit_sha=self.git_baseline[1],
            object_format=self.git_baseline[0], configured_scopes=self.configured_facts,
            current_git_state=list(runner._read_task_git_state(self.root, workspace_session=self.session)),
            operation_links=[dict(name=event["payload"]["name"], attempt=event["payload"]["attempt"])
                             for event in self.events("operation_started")],
            actual_resource_observations=rows, model_quality_credit="none", native_ready=False)
        if self.report.verification_evidence is not None:
            row = self.receipt()
            public.update(receipt_fingerprint=row["fingerprint"], tested_tree=row["binding"]["tested_git_tree_oid"],
                tree_status=row["binding"]["tested_git_tree_status"], source_before=row["run"]["source_before"],
                source_after=row["run"]["source_after"])
        (self.directory / "bridge-observation.json").write_text(json.dumps(public, sort_keys=True) + "\n", encoding="utf-8")
        print("linux-engineering-bridge observation=" + json.dumps(public, sort_keys=True), flush=True)

    def export_and_verify(self):
        row = self.receipt()
        target = self.pack_root / "partial"
        exported = build_evidence_pack(self.directory, dest=target,
            gates_json=self.settings.gates_json, verifications=[row], clean=False)
        self.case.assertTrue(exported.ok, "partial_pack_export_rejected")
        self.case.assertEqual(verify_pack(target), [])
        outside = self.raw / "outside-verifier-cwd"
        outside.mkdir()
        independent = subprocess.run([sys.executable, "-I", "-B", str(target / "verify.py"), str(target)],
            cwd=outside, capture_output=True, timeout=15, check=False)
        self.case.assertEqual(independent.returncode, 0, "independent_partial_pack_rejected")
        manifest = target / "manifest.json"
        self.case.assertTrue(manifest.is_file())
        manifest_digest = digest_bytes(manifest.read_bytes())
        observation = self.directory / "bridge-observation.json"
        public = json.loads(observation.read_text(encoding="utf-8"))
        public["pack_manifest_sha256"] = manifest_digest
        observation.write_text(json.dumps(public, sort_keys=True) + "\n", encoding="utf-8")
        print("linux-engineering-bridge pack_manifest_sha256=" + manifest_digest, flush=True)
        return target


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux bridge only; conformance_credit=none")
class TestLinuxContractEngineering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("cc")
        bus = Path(f"/run/user/{os.getuid()}/bus")
        if compiler is None or os.getuid() == 0 or not bus.exists() or not stat.S_ISSOCK(bus.lstat().st_mode):
            raise unittest.SkipTest("compiler/non-root same-user bus required; conformance_credit=none")
        cls.settings = require_skill()
        cls.helper_dir = tempfile.TemporaryDirectory(prefix="icode-linux-bridge-helper-")
        cls.addClassCleanup(cls.helper_dir.cleanup)
        cls.helper = Path(cls.helper_dir.name) / "icode-landlock"
        built = subprocess.run([compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
            str(REPO_ROOT / "native/linux/icode_landlock.c"), "-o", str(cls.helper)],
            capture_output=True, timeout=30, check=False)
        if built.returncode != 0:
            raise AssertionError("actual_bridge_helper_compile_failed")
        cls.manifest = Path(cls.helper_dir.name) / "icode-landlock.sha256"
        cls.manifest.write_text(digest_bytes(cls.helper.read_bytes()) + "\n", encoding="ascii")

    def test_bridge_code_cp_receipt_and_pack(self):
        f = _Bridge(self, "code")
        passed, reviewer = f.run_gate()
        self.assertTrue(passed, f.report.error)
        row = f.receipt()
        self.assertTrue(row["passed"])
        self.assertEqual(row["binding"]["attempt"], f.attempt)
        self.assertEqual(row["run"]["attempt"], f.attempt)
        self.assertEqual(row["public_plan"]["run_id"], f.session.run_id)
        self.assertEqual(row["run"]["source_before"], row["run"]["source_after"])
        self.assertEqual(row["binding"]["tested_git_tree_status"], "stable")
        self.assertGreaterEqual(row["run"]["checks"][0]["tests_passed"], 1)
        self.assertEqual(len(f.actual_results), 1)
        self.assertEqual(len(reviewer.calls), 3)
        self.assertIsNone(f.actual_results[0].resource_receipt["payload_started"])
        self.assertFalse(f.cp.trace(f.directory).data["open_operations"])
        self.assertEqual(len(f.events("operation_started")), 1)
        self.assertEqual(len(f.events("operation_finished")), 1)
        self.assertNotEqual(f.events("operation_started")[0]["payload"]["attempt"], f.attempt)
        self.assertEqual(len(f.events("verification_recorded")), 1)
        self.assertEqual(f.events("verification_recorded")[0]["payload"]["evidence"], row["fingerprint"])
        self.assertTrue(runner._record_contract_engineering(f.cp, f.directory, f.ticket_id, f.report.verification_evidence))
        self.assertEqual(len(f.events("verification_recorded")), 1)
        self.assertEqual(f.events("step_finished"), [])
        self.assertTrue(f.cp.trace(f.directory).data["open_steps"])
        f.export_and_verify()

    def test_bridge_deepcheck_fixed_scope_cp_receipt_and_pack(self):
        f = _Bridge(self, "deepcheck")
        before = runner._snapshot(f.root)
        passed, reviewer = f.run_gate()
        self.assertTrue(passed, f.report.error)
        self.assertEqual(runner._snapshot(f.root), before)
        self.assertEqual(f.report.verification_review_files, ("changed.py",))
        self.assertEqual(f.receipt()["binding"]["tested_git_tree_status"], "stable")
        self.assertEqual(len(f.actual_results), 1)
        self.assertEqual(len(reviewer.calls), 3)
        self.assertEqual(f.events("step_finished"), [])
        f.export_and_verify()
```

- [ ] **Step 1b：同文件新增独立 portable fixture 守卫，不挂真实 helper class。**

以下 `TestBridgeObservationSafety` 只有3方法，不继承 `TestLinuxContractEngineering`，没有 Linux decorator/setUpClass/G0/native 前置；通过 `__new__` 构造最小观察对象，明确设置 FakeScope/collection double，文件删除亦只观测 mock，不能授实际ACK/资源/CP/清理信用。它验证fixture自己的调用/返回/异常/保留机制，第一个方法中的fresh进程import子场景在observer窗口之外执行；source native probe仍只选真实class的一个具名方法。若实施树已落原错误fixture，先用这些guards记录其真实失败再修fixture；若首次按本修订正确代码实施，记录实际首次验收结果，不故意落错fixture、坏断言或伪称产品RED。

```python
class TestBridgeObservationSafety(unittest.TestCase):
    def _small_fixture(self):
        bridge = _Bridge.__new__(_Bridge)
        bridge.case, bridge.session = self, None
        bridge.pending_cleanup, bridge.uncertain_cleanup = False, False
        bridge.dispatch_started, bridge.observation_error = 0, False
        bridge.scopes, bridge.actual_results, bridge.configured_facts = [], [], []
        bridge.raw = Mock(name="owned_fixture_root")
        bridge.raw.exists.return_value = True
        bridge.raw.stat.return_value = SimpleNamespace(st_dev=17, st_ino=19)
        bridge.raw_identity = (17, 19)
        class PortableScope:
            @staticmethod
            def configured(scope, deadline):
                raise AssertionError("portable_scope_requires_explicit_double")
        bridge._scope_type = PortableScope
        bridge._collection_assert = Mock(name="portable_owned_collection_double")
        scope = SimpleNamespace(unit="fixture.scope", _identities=[(1, 2), (1, 3), (1, 4)],
                                limit=8, version=249, _owned=True, _invocation="fixture-invocation")
        return bridge, scope

    def test_memory_observer_preserves_original_result_and_ack_order_without_io(self):
        bridge, scope = self._small_fixture()
        configured_return = object()
        dispatch_return = SimpleNamespace(scope_cleanup_ok=True)
        deadline = object()
        events = []
        def configured(actual_scope, actual_deadline):
            self.assertIs(actual_scope, scope)
            self.assertIs(actual_deadline, deadline)
            events.append("configured")
            return configured_return
        def dispatch(*args, **kwargs):
            self.assertTrue(bridge.pending_cleanup)
            observed_return = bridge._scope_type.configured(scope, deadline)
            self.assertIs(observed_return, configured_return)
            events.extend(("ack", "dispatch_return"))
            return dispatch_return
        original_dispatch = Mock(side_effect=dispatch)
        def collected(actual_case, actual_scopes):
            self.assertIs(actual_case, self)
            self.assertEqual(actual_scopes, [scope])
            events.append("collected")
        with patch.object(bridge._scope_type, "configured", new=configured), \
             patch.object(builtin, "_controlled_dispatch", new=original_dispatch), \
             patch.object(bridge, "_collection_assert", side_effect=collected), \
             patch.object(Path, "stat", side_effect=AssertionError("observer_extra_stat")), \
             patch.object(Path, "read_text", side_effect=AssertionError("observer_extra_path_read")), \
             patch.object(subprocess, "run", side_effect=AssertionError("observer_extra_query")), \
             patch.object(time, "sleep", side_effect=AssertionError("observer_extra_sleep")):
            with bridge.observe():
                actual = builtin._controlled_dispatch("payload", label="fixture")
                self.assertIs(actual, dispatch_return)
                self.assertTrue(bridge.pending_cleanup)
        original_dispatch.assert_called_once_with("payload", label="fixture")
        self.assertEqual(events, ["configured", "ack", "dispatch_return", "collected"])
        self.assertFalse(bridge.pending_cleanup)
        self.assertFalse(bridge.uncertain_cleanup)
        self.assertFalse(bridge.observation_error)
        self.assertEqual(bridge.actual_results, [dispatch_return])
        self.assertEqual(bridge.configured_facts[0]["owned_identity_cache"], [[1, 2], [1, 3], [1, 4]])
        self.assertEqual(bridge.configured_facts[0]["object_identity"], [1, 2])
        self.assertEqual(bridge.configured_facts[0]["payload_limit"], 8)

        # Fresh-process import contract, not a native Windows execution claim.
        import_probe = (
            "import importlib.abc, os, sys\n"
            "blocked = {'icode.linux_task_scope', 'icode.linux_seccomp_notify', "
            "'tests.test_linux_product_task_quota', 'tests.test_linux_violation_receipt', 'fcntl'}\n"
            "class DenyLinuxImport(importlib.abc.MetaPathFinder):\n"
            " def find_spec(self, fullname, path=None, target=None):\n"
            "  if fullname in blocked: raise ImportError('forbidden_eager_linux_import')\n"
            "sys.meta_path.insert(0, DenyLinuxImport())\n"
            "for name in ('O_DIRECTORY', 'O_NOFOLLOW', 'O_CLOEXEC'):\n"
            " if hasattr(os, name): delattr(os, name)\n"
            "import tests.test_linux_contract_engineering\n"
            "assert not (blocked - {'fcntl'}) & set(sys.modules)\n"
        )
        imported = subprocess.run([sys.executable, "-B", "-c", import_probe],
            cwd=REPO_ROOT, capture_output=True, timeout=15, check=False)
        self.assertEqual(imported.returncode, 0, "portable_bridge_import_contract_failed")

    def test_observer_fault_keeps_ack_but_original_abort_is_rethrown(self):
        # A missing memory cache is only an observer error after the original ACK.
        bridge, scope = self._small_fixture()
        scope._identities = []
        marker = object()
        result = SimpleNamespace(scope_cleanup_ok=True)
        events = []
        def configured(actual_scope, deadline):
            events.append("configured")
            return marker
        def dispatch(*args, **kwargs):
            self.assertIs(bridge._scope_type.configured(scope, 1), marker)
            events.append("ack")
            return result
        with patch.object(bridge._scope_type, "configured", new=configured), \
             patch.object(builtin, "_controlled_dispatch", new=dispatch), \
             patch.object(bridge, "_collection_assert") as collected:
            with self.assertRaisesRegex(AssertionError, "bridge_memory_observation_unavailable"):
                with bridge.observe():
                    self.assertIs(builtin._controlled_dispatch(), result)
        self.assertEqual(events, ["configured", "ack"])
        collected.assert_called_once_with(self, [scope])
        self.assertTrue(bridge.observation_error)
        self.assertFalse(bridge.pending_cleanup)

        # Original configured/dispatch exceptions are outside observer swallowing.
        for boundary in ("configured", "dispatch"):
            for abort_type in (RuntimeError, KeyboardInterrupt):
                with self.subTest(boundary=boundary, abort_type=abort_type.__name__):
                    bridge, scope = self._small_fixture()
                    abort = abort_type("original_abort")
                    events = []
                    def configured(actual_scope, deadline):
                        events.append("configured")
                        if boundary == "configured":
                            raise abort
                        return marker
                    def dispatch(*args, **kwargs):
                        self.assertIs(bridge._scope_type.configured(scope, 1), marker)
                        events.append("ack")
                        raise abort
                    original_dispatch = Mock(side_effect=dispatch)
                    with patch.object(bridge._scope_type, "configured", new=configured), \
                         patch.object(builtin, "_controlled_dispatch", new=original_dispatch), \
                         patch.object(bridge, "_collection_assert") as collected:
                        with self.assertRaises(abort_type) as caught:
                            with bridge.observe():
                                builtin._controlled_dispatch("payload")
                    self.assertIs(caught.exception, abort)
                    original_dispatch.assert_called_once_with("payload")
                    collected.assert_not_called()
                    self.assertEqual(events, ["configured"] if boundary == "configured" else ["configured", "ack"])
                    self.assertTrue(bridge.pending_cleanup)
                    self.assertTrue(bridge.uncertain_cleanup)
                    self.assertEqual(bridge.actual_results, [])
                    with patch.object(shutil, "rmtree") as removed:
                        bridge.close()
                    removed.assert_not_called()

    def test_pending_and_sticky_unknown_protect_owned_root_until_confirmed(self):
        # No dispatch: the original inode-bound cleanup remains allowed.
        bridge, _scope = self._small_fixture()
        with patch.object(shutil, "rmtree") as removed:
            bridge.close()
        removed.assert_called_once_with(bridge.raw)

        # A normal result is still pending until the independent owned check.
        bridge, scope = self._small_fixture()
        result = SimpleNamespace(scope_cleanup_ok=True)
        def configured(actual_scope, deadline):
            return None
        def dispatch(*args, **kwargs):
            bridge._scope_type.configured(scope, 1)
            return result
        with patch.object(bridge._scope_type, "configured", new=configured), \
             patch.object(builtin, "_controlled_dispatch", new=dispatch), \
             patch.object(bridge, "_collection_assert"), \
             patch.object(shutil, "rmtree") as removed:
            with bridge.observe():
                self.assertIs(builtin._controlled_dispatch(), result)
                bridge.close()
                removed.assert_not_called()
                self.assertTrue(bridge.pending_cleanup)
            self.assertFalse(bridge.pending_cleanup)
            bridge.close()
            removed.assert_called_once_with(bridge.raw)

        # Collection failure/abort is sticky even if a later window is confirmed.
        for abort_type in (AssertionError, RuntimeError, KeyboardInterrupt):
            with self.subTest(collection_abort=abort_type.__name__):
                bridge, scope = self._small_fixture()
                abort = abort_type("owned_collection_unconfirmed")
                with patch.object(bridge._scope_type, "configured", new=configured), \
                     patch.object(builtin, "_controlled_dispatch", new=dispatch), \
                     patch.object(bridge, "_collection_assert", side_effect=abort):
                    with self.assertRaises(abort_type) as caught:
                        with bridge.observe():
                            builtin._controlled_dispatch()
                self.assertIs(caught.exception, abort)
                self.assertTrue(bridge.pending_cleanup)
                self.assertTrue(bridge.uncertain_cleanup)
                with patch.object(bridge._scope_type, "configured", new=configured), \
                     patch.object(builtin, "_controlled_dispatch", new=dispatch), \
                     patch.object(bridge, "_collection_assert"):
                    with bridge.observe():
                        builtin._controlled_dispatch()
                self.assertFalse(bridge.pending_cleanup)
                self.assertTrue(bridge.uncertain_cleanup)
                with patch.object(shutil, "rmtree") as removed:
                    bridge.close()
                removed.assert_not_called()

        # A returned unknown cleanup also cannot be changed into deletion credit.
        bridge, scope = self._small_fixture()
        result = SimpleNamespace(scope_cleanup_ok=None)
        with patch.object(bridge._scope_type, "configured", new=configured), \
             patch.object(builtin, "_controlled_dispatch", new=dispatch), \
             patch.object(bridge, "_collection_assert"):
            with self.assertRaisesRegex(AssertionError, "original_dispatch_cleanup_unconfirmed"):
                with bridge.observe():
                    builtin._controlled_dispatch()
        self.assertTrue(bridge.pending_cleanup)
        self.assertTrue(bridge.uncertain_cleanup)
        with patch.object(shutil, "rmtree") as removed:
            bridge.close()
        removed.assert_not_called()
```

```bash
env PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 /tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B -m unittest tests.test_linux_contract_engineering.TestBridgeObservationSafety -v
```

Expected：3 portable方法 PASS/0F/E/skip，原configured/dispatch调用参数、同返回对象和原异常对象、ACK先后、pending/sticky/不删根以及fresh module import全部具名断言；无真实helper编译、scope、manager、CP或payload。import子场景不单计新方法/runtime向量。此命令只选择独立portable class，不能用整个module或真实class来“先跑unit”，也不把fake ACK时序当真实broker已验收或此import守卫当原生Windows通过。本文作者不执行它。

| Portable fixture方法 | 验收子场景数 | 明确边界 |
| --- | --- | --- |
| `test_memory_observer_preserves_original_result_and_ack_order_without_io` | 2：内存观察正常路径；fresh import边界 | 原调用/返回对象、ACK时序和cache；模拟缺Unix flags/禁止Linux导入，不是原生Windows |
| `test_observer_fault_keeps_ack_but_original_abort_is_rethrown` | 5：cache观察错误；configured/dispatch × RuntimeError/KeyboardInterrupt | 自有观察错误不改ACK；原异常对象保留，无重试或异常时新查询 |
| `test_pending_and_sticky_unknown_protect_owned_root_until_confirmed` | 6：无dispatch；pending；3种收束失败/中断；原返回cleanup未知 | 只删已确认原owned根；后续成功不清sticky unknown |

合计3方法/13个portable fixture验收子场景；它们不进入18 runtime向量、不扩21 native方法或bridge单case选择。Task 4生命周期guard另有9子场景，属于其1个portable选择guard，不能并入上述13或Native通过数。

- [ ] **Step 2：实际运行两个正控，不声明虚构的产品 RED。**

这是 test-only 连接验收，不应为满足形式而故意坏断言、删除 prerequisite 或制造 TypeError。G0 的真实产品 RED→GREEN属于外部修复；本片新正控在 G0 后首次执行即是实际验收。若失败是原 CP/pack/manager 门，应保留失败并标此层 blocked，不能改生产门取绿。

```bash
env PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 GOMAXPROCS=1 GOFLAGS=-p=1 CMAKE_BUILD_PARALLEL_LEVEL=1 /tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B -m unittest tests.test_linux_contract_engineering.TestLinuxContractEngineering.test_bridge_code_cp_receipt_and_pack tests.test_linux_contract_engineering.TestLinuxContractEngineering.test_bridge_deepcheck_fixed_scope_cp_receipt_and_pack -v
```

Expected：2 方法 actual PASS/0F/E/skip、各实际一个 dispatch/owned scope、实际 CP/receipt/partial pack；若实际环境缺 prerequisite，则记录 skip/无信用而非授 2P。执行前核该 lexical Python仍存在及版本；失效时登记新可信解释器与环境，不偷偷 resolve成系统Python。不得重新称此前40方法为本次2方法。

`configured_facts` 只复制原配置成功后留下的内存事实：`_identities` 是按 root/supervisor/payload 顺序保存的3个 `(st_dev, st_ino)` 双元组列表，root身份取 `[0]`；`limit`、`version`、`_owned`、`_invocation` 已由原配置器验证/写入。这里不是新的 kernel/pids.max 读取；callback 禁止额外 stat/path read/manager query/subprocess/sleep，不将缺失cache造为有效值。原 `configured` 返回/异常不变，自有观察错误只置宿主验收错误，返回后仍沿原broker ACK路径；观察错误不授宿主证据信用。内存复制/摘要也有成本，不能绝对保证callback时间预算不受影响。公开 observation 把本次 repository/source 指纹、解释器/helper、scope、Plan、CP step/operation、receipt 与后续 pack manifest 摘要连接，省去私有路径/argv/env。本文 source 计划不伪造旧 L1 缺失的这些历史字段。

所有实际入口统一经 `observe` 的退出路径确认既有 owned scopes。dispatch开始即 pending；正常原result与独立 `assert_collected` 都确认后才解除本次pending。原dispatch/broker finally 中断、无返回、后续宿主异常或独立收束断言/查询失败都令 unknown sticky，并原样传播；异常传播时不再发起外部检查以免覆盖原中断。后续成功只能解除其pending，不能清除此前unknown。`close` 在 pending 或 unknown 时保留原owned根，无dispatch fixture仍按原inode绑定清理；没有新增 stop unit/扩展删除/重试载荷/CP finish。上述状态仅为fixture保留策略，不能生成生产resource receipt、operation事件或Native信用。

- [ ] **Step 3：作者 selfSPEC→selfQUALITY，fresh SPEC→不同 QUALITY；不开下一 writer。**

核 source/session/layout/CP身份、code/deepcheck时点、真实调用次数、资源None状态、各原门与独立验包。代码实际实现范围只此新文件，不提交单任务；Task 2等审查通过后串行进行。

## Task 2：实际确定失败/不完整/漂移/Reviewer与公共恢复负控

**状态**

- [ ] 任务完成

**Dependencies:** Task 1
**Parallelizable:** No (同文件/真实 scope 串行，不能跨 writer 修改或重叠运行)

- [ ] **Step 1：在上述 class 内追加以下完整方法。**

正控直接用原生产路径；fault 字段仅在明确负例中修改**已经真实执行并实际回收**的返回值，原 result 另保存；不能说这些故障是现场自然发生。未决 operation 不补 finish、不自动重放。

追加前同步三个实际依赖：从 `icode.checkpoint` 导入 `Checkpointer`，现有 `icode.control` 导入补 `ControlResult`，现有 `icode.evidence` 导入补 `EvidenceError`。这些只用于下列负控，不增加运行时依赖。当前固定子仓库已提供一次性绑定，但错误工单负控应合法保持未绑定，使其默认根自然不同于隔离代码目录，不能再向 create 注入受保护的 project_path。

```python
    def test_real_session_prepare_rejects_nested_deny_without_deleting_protection(self):
        f = _Bridge(self)
        original = f.policy
        self.assertFalse(f.sandbox.policy_contract_ready)
        with self.assertRaises(ValueError):
            f.sandbox.prepare_policy(replace(original,
                deny_write_roots=(*original.deny_write_roots, f.root / "protected")))
        self.assertEqual(f.policy.protected_paths, f.session.protected_paths)
        self.assertEqual(f.policy, original)
        self.assertEqual(f.actual_results, [])

    def test_real_assertion_and_import_failures_close_failure_and_stop_later_check(self):
        for body in (test_source("self.assertEqual(changed.value, 99)"),
                     "import missing_bridge_dependency\n"):
            with self.subTest(kind="assertion" if "99" in body else "missing_dependency"):
                f = _Bridge(self, body=body, later=True)
                passed, reviewer = f.run_gate()
                self.assertFalse(passed)
                row = f.receipt()
                self.assertFalse(row["passed"])
                self.assertEqual(row["run"]["checks"][0]["status"], "failed")
                self.assertEqual(row["run"]["checks"][1]["status"], "not_run")
                self.assertEqual(len(f.actual_results), 1)
                self.assertEqual(reviewer.calls, [])
                self.assertFalse(f.cp.trace(f.directory).data["open_operations"])
                self.assertEqual(f.events("operation_finished")[0]["payload"]["outcome"], "failure")
                self.assertEqual(f.events("step_finished"), [])

    def test_real_timeout_and_output_limit_keep_action_unresolved(self):
        cases = ((test_source("__import__('time').sleep(2)"), .1, 65536),
                 (test_source("print('x' * 100000)"), 5, 1024))
        for body, timeout, limit in cases:
            with self.subTest(timeout=timeout, limit=limit):
                f = _Bridge(self, body=body, timeout=timeout, output_limit=limit)
                passed, reviewer = f.run_gate()
                self.assertFalse(passed)
                self.assertEqual(f.receipt()["run"]["checks"][0]["status"], "output_incomplete")
                self.assertTrue(f.cp.trace(f.directory).data["open_operations"])
                self.assertEqual(f.events("operation_finished"), [])
                self.assertEqual(reviewer.calls, [])

    def test_injected_observer_channel_cleanup_faults_never_close_action(self):
        for fault in ({"violation_observer_status": "incomplete"}, {"scope_cleanup_ok": None},
                      {"resource_receipt": None}):
            with self.subTest(field=next(iter(fault))):
                f = _Bridge(self)
                passed, reviewer = f.run_gate(fault=fault)
                self.assertFalse(passed)
                self.assertEqual(f.receipt()["run"]["checks"][0]["status"], "output_incomplete")
                self.assertTrue(f.cp.trace(f.directory).data["open_operations"])
                self.assertEqual(f.events("operation_finished"), [])
                self.assertEqual(reviewer.calls, [])
                self.assertIs(f.actual_results[0].scope_cleanup_ok, True)
                self.assertEqual(f.actual_results[0].violation_observer_status, "complete")

    def test_frozen_plan_tool_environment_root_and_platform_admission_drift(self):
        cases = ("environment", "workspace_identity", "executable_identity", "platforms", "run_id")
        for field in cases:
            with self.subTest(field=field):
                f = _Bridge(self)
                if field == "executable_identity":
                    object.__setattr__(f.plan.checks[0], field, "0" * 64)
                    expected = "verification_tool_changed"
                else:
                    value = {"environment": (), "workspace_identity": (-1, -1),
                             "platforms": ("Darwin",), "run_id": "other-run"}[field]
                    object.__setattr__(f.plan, field, value)
                    expected = "verification_plan_identity_mismatch"
                before = f.cp.trace(f.directory).data["event_count"]
                backend = FakeBackend(reviewer_script())
                passed = runner._contract_engineering_gate(**f.arguments(backend))
                self.assertFalse(passed)
                self.assertEqual(f.report.error, expected)
                self.assertEqual(backend.calls, [])
                self.assertEqual(f.cp.trace(f.directory).data["event_count"], before)
                self.assertEqual(f.actual_results, [])

    def test_real_test_source_write_invalidates_tested_window(self):
        body = test_source("__import__('pathlib').Path('changed.py').write_text('value = 9\\n')")
        f = _Bridge(self, body=body)
        passed, reviewer = f.run_gate()
        self.assertFalse(passed)
        self.assertFalse(f.receipt()["passed"])
        self.assertNotEqual(f.receipt()["run"]["source_before"], f.receipt()["run"]["source_after"])
        self.assertEqual(reviewer.calls, [])

    def test_actual_head_change_after_command_fails_identity_without_new_receipt(self):
        f = _Bridge(self)
        head = f.session.git_status_identity.git_dir / "HEAD"
        def change_head():
            head.write_text("0" * len(f.git_baseline[1]) + "\n", encoding="ascii")
        with self.assertRaises(ValueError):
            f.run_gate(after_command=change_head)
        self.assertEqual(len(f.actual_results), 1)
        self.assertTrue(f.pending_cleanup)
        self.assertTrue(f.uncertain_cleanup)
        self.assertTrue(f.cp.trace(f.directory).data["open_operations"])
        self.assertEqual(list(f.directory.glob(".engineering-*.json")), [])

    def test_deepcheck_source_and_scope_after_start_are_rejected_without_recapture(self):
        for kind in ("source", "scope"):
            with self.subTest(kind=kind):
                f = _Bridge(self, "deepcheck")
                starts = f.events("step_started")
                if kind == "source":
                    (f.root / "changed.py").write_text("value = 9\n", encoding="utf-8")
                else:
                    changed = f.cp.metadata_update(f.directory, ticket_id=f.ticket_id,
                        request="bridge-scope-drift", set_json={"code_files": ["changed.py", "test_value.py"]})
                    self.assertTrue(changed.ok)
                self.assertIsNone(runner._contract_deepcheck_review_files(f.cp,
                    f.directory, f.root, f.ticket_id, f.attempt))
                self.assertEqual(f.events("step_started"), starts)
                self.assertEqual(f.events("step_finished"), [])
                self.assertEqual(f.actual_results, [])

    def test_reviewer_protocol_negatives_preserve_actual_command_credit_only(self):
        blocking = dict(file="changed.py", line=1, severity="blocking", category="correctness",
                        message="Fixture blocking finding")
        scripts = (reviewer_script(read=False), reviewer_script(submit=False),
                   reviewer_script(denied=True), reviewer_script(finding=blocking),
                   [{"tool_calls": [{"id": "bad", "name": "submit_review",
                       "arguments": {"summary": "", "findings": []}}]}, "done"])
        for index, script in enumerate(scripts):
            with self.subTest(index=index):
                f = _Bridge(self)
                passed, backend = f.run_gate(FakeBackend(script))
                self.assertFalse(passed)
                self.assertEqual(f.report.error, "engineering_reviewer_failed")
                self.assertTrue(f.receipt()["passed"])
                self.assertEqual(len(f.actual_results), 1)
                self.assertFalse(f.cp.trace(f.directory).data["open_operations"])
                self.assertEqual(f.events("step_finished"), [])

    def test_actual_reviewer_after_submit_source_drift_invalidates_quality(self):
        f = _Bridge(self)
        class DriftingReviewer(FakeBackend):
            def complete(self, *args, **kwargs):
                result = super().complete(*args, **kwargs)
                if len(self.calls) == 3:
                    (f.root / "changed.py").write_text("value = 8\n", encoding="utf-8")
                return result
        passed, backend = f.run_gate(DriftingReviewer(reviewer_script()))
        self.assertFalse(passed)
        self.assertEqual(f.report.error, "engineering_reviewer_failed")
        self.assertTrue(f.receipt()["passed"])
        self.assertEqual(f.events("step_finished"), [])

    def test_final_boundary_rejects_real_source_and_wrong_cp_attempt(self):
        for mutation in ("source", "attempt"):
            with self.subTest(mutation=mutation):
                f = _Bridge(self)
                self.assertTrue(f.run_gate()[0])
                if mutation == "source":
                    (f.root / "changed.py").write_text("value = 7\n", encoding="utf-8")
                error = runner._contract_engineering_binding_error(f.report, f.plan, f.root,
                    f.step, f.ticket_id, f.policy, f.sandbox, f.session,
                    cp=f.cp, out_dir=f.directory, attempt="other-attempt" if mutation == "attempt" else f.attempt)
                self.assertEqual(error, "engineering_final_binding_changed" if mutation == "source"
                                 else "engineering_final_control_binding_changed")
                self.assertEqual(f.events("step_finished"), [])

    def test_real_control_execution_root_mismatch_refuses_before_model(self):
        f = _Bridge(self, full=True)
        wrong_root = f.control / "wrong-project"
        wrong_root.mkdir()
        wrong = next_out_dir(wrong_root).resolve()
        self.assertTrue(f.cp.create(wrong, ticket_id=f.ticket_id,
            requirement="mismatch", birth="plan").ok)
        projected = f.cp.run("action-policy", "--dir", str(wrong))
        self.assertEqual(projected.data["execution_root"], str(wrong_root))
        self.assertNotEqual(projected.data["execution_root"], str(f.root))
        before = f.cp.trace(wrong).data["event_count"]
        backend = FakeBackend(reviewer_script())
        report = runner.run_contract_step(f.settings, backend=backend, workspace=f.root,
            step=f.step, ticket_id=f.ticket_id, out_dir=wrong, policy=f.policy,
            sandbox=f.sandbox, verification_plan=f.plan, workspace_session=f.session)
        self.assertEqual(report.error, "engineering_control_workspace_mismatch")
        self.assertEqual(backend.calls, [])
        self.assertEqual(f.cp.trace(wrong).data["event_count"], before)

    def test_public_resume_refuses_actual_unknown_action_without_reexecuting(self):
        f = _Bridge(self, timeout=.1, body=test_source("__import__('time').sleep(2)"))
        self.assertFalse(f.run_gate()[0])
        self.assertTrue(f.cp.trace(f.directory).data["open_operations"])
        checkpoint = Checkpointer(f.directory, ticket_id=f.ticket_id, step=f.step, attempt=f.attempt)
        checkpoint.save(turn_index=0, tool_calls=0, history=[], stop_reason="engineering_verification_pending")
        before = f.cp.trace(f.directory).data["event_count"]
        backend = FakeBackend(reviewer_script())
        with f.observe():
            resumed = runner.resume_contract_step(f.settings, backend=backend, out_dir=f.directory,
                workspace=f.root, step=f.step, ticket_id=f.ticket_id, policy=f.policy,
                sandbox=f.sandbox, verification_plan=f.plan, workspace_session=f.session,
                change_baseline=f.baseline)
        self.assertEqual(resumed.error, "engineering_recovery_attempt_unconfirmed")
        self.assertEqual(len(f.actual_results), 1)
        self.assertEqual(backend.calls, [])
        self.assertEqual(f.cp.trace(f.directory).data["event_count"], before)
        self.assertTrue(checkpoint.exists())

    def test_same_recorder_new_occurrence_refuses_open_action_but_not_claim_fresh_reentry(self):
        f = _Bridge(self, timeout=.1, body=test_source("__import__('time').sleep(2)"))
        self.assertFalse(f.run_gate()[0])
        backend = FakeBackend(reviewer_script())
        with f.observe():
            self.assertFalse(runner._contract_engineering_gate(**f.arguments(backend)))
        self.assertEqual(f.report.error, "engineering_operation_start_unconfirmed")
        self.assertEqual(len(f.actual_results), 1)
        self.assertEqual(backend.calls, [])
        self.assertTrue(f.cp.trace(f.directory).data["open_operations"])

    def test_injected_record_and_operation_ack_failure_never_gain_success(self):
        for method in ("record_verification", "operation_finish"):
            with self.subTest(method=method):
                f = _Bridge(self)
                with patch.object(f.cp, method, return_value=ControlResult((), 1, {"ok": True})):
                    self.assertFalse(f.run_gate()[0])
                self.assertEqual(f.report.error, "engineering_verification_failed")
                self.assertEqual(f.events("step_finished"), [])
                self.assertEqual(len(f.actual_results), 1)
                if method == "operation_finish":
                    self.assertTrue(f.cp.trace(f.directory).data["open_operations"])

    def test_pack_import_rejects_bad_binding_digest_duplicate_and_missing_fields(self):
        f = _Bridge(self)
        self.assertTrue(f.run_gate()[0])
        original = f.receipt()
        for kind in ("binding", "digest", "duplicate", "missing"):
            with self.subTest(kind=kind):
                candidate = json.loads(json.dumps(original))
                path = f.control / ("bad-" + kind + ".json")
                if kind == "binding":
                    candidate["binding"]["attempt"] = "other-attempt"
                elif kind == "digest":
                    candidate["fingerprint"] = "0" * 64
                elif kind == "missing":
                    candidate.pop("public_plan")
                encoded = json.dumps(candidate)
                if kind == "duplicate":
                    encoded = '{"kind":"engineering_verification",' + encoded[1:]
                path.write_text(encoded, encoding="utf-8")
                with self.assertRaises(EvidenceError):
                    load_verification_receipts([path])
        f.export_and_verify()
```

- [ ] **Step 2：实际运行新增 class，逐方法/子向量记录真实结果。**

```bash
env PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 GOMAXPROCS=1 GOFLAGS=-p=1 CMAKE_BUILD_PARALLEL_LEVEL=1 /tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B -m unittest tests.test_linux_contract_engineering.TestLinuxContractEngineering -v
```

Expected：Task 1–2 当前 18 方法实际通过，故障注入与真实窗口分开；每个资源实际调用均 own scope collected，不完整 evidence 的 CP action 仍 open。方法数是在本文所列两段代码的静态计数，不是已经运行数；Task 3 会再增加方法。G1 fresh-recorder 准入已在020aceb修复并单独验收，不再标blocked；本片16个新增方法不含该向量。同recorder新occurrence仍应拒绝为 engineering_operation_start_unconfirmed，不改成replay错误；不运行第二个未决payload来冒充恢复成功。

- [ ] **Step 3：作者自SPEC/QUALITY、fresh SPEC→不同QUALITY。**

核每个 negative 的真正入口、无 fake summary/result正控、legacy/admission原参数兼容；只审本任务增量和关联fixture，不预授整体安全。审查通过才进入Task 3。

## Task 3：普通 code/deepcheck 原门阻塞的实际运行与 Native 负控

**状态**

- [ ] 任务完成

**Dependencies:** Task 2
**Parallelizable:** No (同文件/CP/helper，不能跨 writer 或并行改输入)

- [ ] **Step 1：在 `_Bridge` 内追加真实 inspection 装配。**

它保留原清单的 `partial/unobserved`，逐阶段真实读取生成摘要，再走原 inspection read 入口；不手改 worklist 的 reads、scope、baseline 或债务。deepcheck coverage 的 partial 明确反映同一无法识别Git的关联范围，不能用 `not_eligible` 把 debt 清掉。

```python
    def post_inspection_with_actual_debt(self, path, step, attempt):
        self.case.assertEqual(path, self.directory)
        self.case.assertEqual(step, self.step)
        self.attempt = attempt
        if step == "code":
            changed, updated = set_code_files(self.cp, path, self.ticket_id, self.root, self.baseline)
            self.case.assertEqual(changed, ["changed.py"])
            self.case.assertTrue(updated)
        prepared = self.cp.run("inspection", "--dir", str(path), "--step", step,
            "--attempt", attempt, "--phase", "prepare", "--scope", ".",
            "--request", "bridge-inspection-prepare")
        self.case.assertTrue(prepared.ok)
        target = path / (step + "_worklist.json")
        worklist = json.loads(target.read_text(encoding="utf-8"))
        self.case.assertEqual(worklist["coverage_status"], "partial")
        self.case.assertTrue(any("no affected Git repository" in row["debt_reason"]
                                 for row in worklist["unobserved"]))
        read_phases = {}
        for phase in worklist["required_phases"]:
            read_phases[phase] = {}
            for unit in worklist["units"]:
                for file in unit["files"]:
                    relative = file["path"]
                    actual = digest_bytes((self.root / relative).read_bytes())
                    self.case.assertEqual(actual, file["sha256"])
                    read_phases[phase][relative] = actual
                    accepted = self.cp.run("inspection", "--dir", str(path), "--step", step,
                        "--attempt", attempt, "--phase", "read", "--read-phase", phase,
                        "--path", relative, "--request", "bridge-read-" + canonical_digest([phase, relative]))
                    self.case.assertTrue(accepted.ok)
        worklist = json.loads(target.read_text(encoding="utf-8"))
        self.case.assertEqual(worklist["coverage_status"], "partial")
        self.case.assertTrue(worklist["unobserved"])
        strict = self.cp.run("inspection", "--dir", str(path), "--step", step,
            "--attempt", attempt, "--phase", "check", check=False)
        self.case.assertFalse(strict.ok)
        self.case.assertTrue(strict.data.get("violations"))
        if step == "code":
            self.case.assertTrue(self.cp.artifact(path, step, attempt, "changed.py",
                ticket_id=self.ticket_id, scope="workspace").ok)
        else:
            from icode.artifact_broker import ArtifactBroker
            declared_debt = sorted({item["path"] for item in worklist["unobserved"]})
            coverage = dict(schema_version=1, ticket_id=self.ticket_id, attempt=attempt,
                review_scope=["changed.py"], coverage_status="partial", unobserved=declared_debt,
                debt_reason="Split metadata is outside the inspection repository discovery boundary",
                dedup_status="partial", dedup_unobserved=declared_debt, read_phases=read_phases)
            broker = ArtifactBroker(path, ContractSet.load(self.settings.gates_json).step(step), 65536)
            broker.submit("deepcheck_coverage.json", json.dumps(coverage))
```

- [ ] **Step 2：在新 class 内追加两个独立完整入口负控与 Native 负控。**

两个 runner 负控分别运行 code/deepcheck，保留真实 ordinary boundary/inspection/工程/推演/finish 调用。不替换 `_finish_step`、CP结果或 readonly Reviewer。观察式 `ControlPlane.step_finish` 包装只读它的实际返回值，不改变调用结果。pack成功正控仅Task 1；本完整步骤 partial 的多版本 worklist 历史无法凭当前文件补造，所以不把它伪导出为“完整成功包”。

```python
    def _run_full_entry_with_original_inspection_block(self, step):
        f = _Bridge(self, step, full=True)
        calls = []
        if step == "code":
            calls.append({"id": "write", "name": "write_file", "arguments": {
                "path": "changed.py", "content": "value = 1\n"}})
        output = "04_code_review_fix.md" if step == "code" else "05_deepcheck.md"
        calls.append({"id": "report", "name": "submit_artifact", "arguments": {
            "name": output, "content": "# Actual protocol fixture report\n"}})
        thought = json.dumps({"step": "Recheck actual current fixture boundary", "next_thought_needed": False})
        backend = FakeBackend([{"tool_calls": calls}, "done", *reviewer_script(), thought, thought, thought])
        finish_results = []
        original_finish = ControlPlane.step_finish
        def observe_finish(control, *args, **kwargs):
            result = original_finish(control, *args, **kwargs)
            finish_results.append(result)
            return result
        frozen_start = runner._snapshot(f.root)
        with f.observe(), patch.object(ControlPlane, "step_finish", new=observe_finish):
            f.report = runner.run_contract_step(f.settings, backend=backend, workspace=f.root,
                step=step, ticket_id=f.ticket_id, requirement="change value", out_dir=f.directory,
                sandbox=f.sandbox, policy=f.policy, verification_plan=f.plan,
                workspace_session=f.session, change_baseline=f.baseline,
                post_write=f.post_inspection_with_actual_debt)
        starts = f.events("step_started")
        self.assertEqual(len(starts), 1)
        f.attempt = starts[0]["payload"]["attempt"]
        self.assertEqual(f.events("step_finished"), [])
        self.assertFalse(f.report.ok)
        self.assertNotEqual(f.report.finish_outcome, "success")
        self.assertTrue(finish_results, "actual_success_finish_call_was_not_reached")
        self.assertFalse(finish_results[-1].ok)
        self.assertEqual(finish_results[-1].data.get("gate_id"), "step_receipt")
        self.assertIn("inspection_worklist:", repr(finish_results[-1].data.get("missing_outputs", ()))
                      + repr(finish_results[-1].data.get("missing_output_receipts", ())))
        worklist = json.loads((f.directory / (step + "_worklist.json")).read_text(encoding="utf-8"))
        self.assertEqual(worklist["coverage_status"], "partial")
        self.assertTrue(worklist["unobserved"])
        row = f.receipt()
        self.assertTrue(row["passed"], "host_engineering_subgate_did_not_pass")
        self.assertEqual(row["binding"]["attempt"], f.attempt)
        self.assertEqual(len(f.actual_results), 1)
        self.assertFalse(f.pending_cleanup)
        self.assertFalse(f.cp.trace(f.directory).data["open_operations"])
        self.assertTrue(f.cp.trace(f.directory).data["open_steps"])
        self.assertTrue(all(event["payload"]["result"] == "pass" for event in f.events("gate_checked")))
        self.assertTrue(f.report.reasoning_rows)
        self.assertFalse(f.report.advance_status)
        if step == "deepcheck":
            self.assertEqual(runner._snapshot(f.root), frozen_start)
            self.assertEqual(f.report.verification_review_files, ("changed.py",))
        f.publish_observation(layer="source_host_model_double_full_step_blocked")

    def test_full_code_original_inspection_debt_blocks_success(self):
        self._run_full_entry_with_original_inspection_block("code")

    def test_full_deepcheck_original_inspection_debt_blocks_success(self):
        self._run_full_entry_with_original_inspection_block("deepcheck")

    def test_native_ready_false_blocks_before_provider_model_and_step_start(self):
        f = _Bridge(self, "code", full=True)
        trace = f.cp.trace(f.directory)
        self.assertTrue(trace.ok)
        context = ExecutionContext(f.ticket_id, f.directory, f.root, "change value",
                                   trace.data["status"], ())
        safe_points = []
        control = SimpleNamespace(session=f.session, ticket_id=f.ticket_id, run_id=f.run_id,
                                  safe_point=lambda step: safe_points.append(step))
        backend = FakeBackend(["must not be called"])
        provider = Mock(return_value=f.plan)
        executor = NativeChainExecutor(f.settings, backend=backend, sandbox=f.sandbox,
                                       verification_plan_provider=provider)
        with patch.object(executor, "_step_runner", wraps=executor._step_runner) as step_runner:
            result = executor.execute(context, control)
        self.assertEqual(result.state, "blocked")
        self.assertEqual(result.error_code, "isolation_unavailable")
        self.assertFalse(f.sandbox.policy_contract_ready)
        self.assertTrue(safe_points)
        provider.assert_not_called()
        step_runner.assert_not_called()
        self.assertEqual(backend.calls, [])
        self.assertEqual(f.events("step_started"), [])
        self.assertEqual(f.actual_results, [])
```

- [ ] **Step 3：运行具名三个方法；如果运行时止于其它普通门，标 blocked，不降断言。**

```bash
env PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 GOMAXPROCS=1 GOFLAGS=-p=1 CMAKE_BUILD_PARALLEL_LEVEL=1 /tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B -m unittest tests.test_linux_contract_engineering.TestLinuxContractEngineering.test_full_code_original_inspection_debt_blocks_success tests.test_linux_contract_engineering.TestLinuxContractEngineering.test_full_deepcheck_original_inspection_debt_blocks_success tests.test_linux_contract_engineering.TestLinuxContractEngineering.test_native_ready_false_blocks_before_provider_model_and_step_start -v
```

Expected：3 方法实际通过；前2个方法通过的含义是**原 success 正控被真实债务拒绝**且各已过子门如实记录，不是 code/deepcheck成功。第三个方法使用真实 session/原 Landlock/正常状态派生，未改 chain_steps/readiness；safe_point是观察驱动，不声称整个 AutonomyManager run零控制写。

真实 `TestLinuxContractEngineering` 在本计划代码内共21方法（18 + 3）；同文件另有 `TestBridgeObservationSafety` 的3个portable fixture方法，所以新文件共24方法，不是24原生方法。子向量与表中的18 ID不是方法数。真正完整成功正控仍 G2 blocked，不删除 requirements；G1 fresh-recorder内部重入已由020aceb独立验收。新增最小授权或独立修复到位后须另审更新G2计划/正控，不能直接把本方法的原拒绝断言反转成成功。

- [ ] **Step 4：作者自SPEC/QUALITY、fresh SPEC→不同QUALITY。**

重点审完整步骤所有真调用、真实读取/每阶段hash、debt未删、deepcheck前固定与开始后不改、实际推演/finish/无advance；失败状态与partial pack不能偷换六步或模型成功。

## Task 4：单次 Linux 原生诊断选择与便携选择守卫

**状态**

- [ ] 任务完成

**Dependencies:** Task 3
**Parallelizable:** No (同native调度调用链，必须在已过source正控后加入，不和原生测试并行)

本任务包含两个不同的真实 RED→GREEN：先修原 `_run_unittest_probe` 生命周期分类，再接缺失的 bridge loader。Task 1 的 `setUpClass` 在必要 compiler/non-root bus 缺失时抛 `SkipTest`，`require_skill()` 也可能在该阶段抛出它；真实 `TestSuite` 此时 `testsRun=0`、只有 `setUpClass` holder 的 skip。原 helper 48–60 行先拒绝 `testsRun != 1`，所以会把合法缺前置条件诊断误报 failed。只 mock `ProbeExecution` 三态不能发现此缺口。下面只扩大已列 Task 4 两文件的必要 helper/guard 内容，不增加工程运行向量、不修 G0/G1/G2、不改评分/ready。

- [ ] **Step 0a：先新增原 helper 的真实生命周期守卫，记录真实 RED。**

在 `tests/test_run_native_probe_ci.py:TestNativeProbeCi` 追加下列一个方法；此时不得先添加 Step 3 的新 `setUp`，也不得先修 helper。原 helper 已存在，测试不导入新 bridge、不编译或调用 native/helper/CP。每个子场景先运行标准 `TestSuite/TestResult` 核原始生命周期，再用 fresh 小 class fixture 调原 helper 核分类；不 mock suite/result/helper。8 个类场景加 1 个普通零测试非法输入，共 9 子场景，仍只计 1 个 portable guard 方法。

```python
    def test_unittest_probe_real_class_setup_skip_and_failure_lifecycle(self):
        events = []
        scenarios = (
            ("setup_skip", "skipped", 0, 1, 0, 0),
            ("setup_error", "failed", 0, 0, 0, 1),
            ("normal", "passed", 1, 0, 0, 0),
            ("method_skip", "skipped", 1, 1, 0, 0),
            ("cleanup_error", "failed", 1, 0, 0, 1),
            ("setup_skip_cleanup_error", "failed", 0, 1, 0, 1),
            ("method_skip_cleanup_error", "failed", 1, 1, 0, 1),
            ("failure_with_teardown_skip", "failed", 1, 1, 1, 0),
        )

        def make_case(mode):
            class FixtureCase(unittest.TestCase):
                @classmethod
                def setUpClass(cls):
                    events.append("setup")
                    def cleanup():
                        events.append("cleanup")
                        if mode in {"cleanup_error", "setup_skip_cleanup_error",
                                    "method_skip_cleanup_error"}:
                            raise RuntimeError("fixture_cleanup_error")
                    cls.addClassCleanup(cleanup)
                    if mode in {"setup_skip", "setup_skip_cleanup_error"}:
                        raise unittest.SkipTest("fixture_setup_prerequisite_unavailable")
                    if mode == "setup_error":
                        raise RuntimeError("fixture_setup_error")

                @classmethod
                def tearDownClass(cls):
                    events.append("teardown")
                    if mode == "failure_with_teardown_skip":
                        raise unittest.SkipTest("fixture_teardown_skip")

                def runTest(self):
                    events.append("method")
                    if mode in {"method_skip", "method_skip_cleanup_error"}:
                        self.skipTest("fixture_method_skip")
                    if mode == "failure_with_teardown_skip":
                        self.fail("fixture_method_failure")
            return FixtureCase()

        for mode, status, methods, skips, failures, errors in scenarios:
            with self.subTest(mode=mode):
                events.clear()
                raw = unittest.TestResult()
                unittest.TestSuite((make_case(mode),)).run(raw)
                self.assertEqual((raw.testsRun, len(raw.skipped), len(raw.failures), len(raw.errors)),
                                 (methods, skips, failures, errors))
                expected_events = (["setup", "cleanup"] if methods == 0 else
                                   ["setup", "method", "teardown", "cleanup"])
                self.assertEqual(events, expected_events)
                events.clear()
                classified = run_native_probe_ci._run_unittest_probe(make_case(mode))
                self.assertEqual(classified.status, status, classified.detail)
                self.assertEqual(events, expected_events)
                if mode == "setup_skip":
                    self.assertEqual(classified.detail, "fixture_setup_prerequisite_unavailable")
                if mode == "method_skip":
                    self.assertEqual(classified.detail, "fixture_method_skip")
        with self.subTest(mode="ordinary_zero_tests_invalid_input"):
            raw = unittest.TestResult()
            unittest.TestSuite().run(raw)
            self.assertEqual((raw.testsRun, raw.skipped, raw.failures, raw.errors), (0, [], [], []))
            classified = run_native_probe_ci._run_unittest_probe(unittest.TestSuite())
            self.assertEqual(classified.status, "failed")
            self.assertEqual(classified.detail, "expected one test, ran 0")
```

```bash
env PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 /tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B -m unittest tests.test_run_native_probe_ci.TestNativeProbeCi.test_unittest_probe_real_class_setup_skip_and_failure_lifecycle -v
```

Expected RED：旧 helper 在 `setup_skip` 子场景把 `failed` 与 `skipped` 断言不等，detail 为 `expected one test, ran 0`；原始 lifecycle 断言先通过，证明不是 fixture/import/TypeError 失败。旧 helper 还可能因先看 skipped 而漏掉 skip 伴 error/failure，保留各实际失败明细；这些均是 helper 分类缺陷，不归因 compiler/native/manager。作者本轮不执行该命令。

- [ ] **Step 0b：仅替换原 helper 分类分支，再记录同一守卫真实 GREEN。**

`scripts/run_native_probe_ci.py` 的 `_run_unittest_probe` 最小替换为以下完整函数。先拒绝任何 failure/error；只有原 suite 实际报告 `testsRun=0`、恰好一个对应当前类 `setUpClass` 的 holder skip 且无 failure/error，才允许 skipped。不直接放行任意零测试或 module setup skip，不依赖私有 `_ErrorHolder` 类型；holder 的 `id()` 精确核类全名。普通零测试继续 failed；一个实际方法的原 skip/passed 分类保持。该共享 helper 的旧 Linux lease/receipt/bounds callers 仍走同一接口，须回归原生命周期/三态单测。

```python
def _run_unittest_probe(test_case: unittest.TestCase) -> ProbeExecution:
    """Run one case; a pure class setup skip grants no capability credit."""
    result = unittest.TestResult()
    unittest.TestSuite((test_case,)).run(result)
    failures = result.failures + result.errors
    if failures:
        return ProbeExecution("failed", " ".join(failures[0][1].split())[-500:])
    if result.testsRun == 0 and len(result.skipped) == 1:
        skipped_case, reason = result.skipped[0]
        case_class = type(test_case)
        setup_id = f"setUpClass ({case_class.__module__}.{case_class.__qualname__})"
        if (isinstance(test_case, unittest.TestCase)
                and not isinstance(skipped_case, unittest.TestCase)
                and skipped_case.id() == setup_id):
            return ProbeExecution("skipped", reason)
    if result.testsRun != 1:
        return ProbeExecution("failed", f"expected one test, ran {result.testsRun}")
    if result.skipped:
        return ProbeExecution("skipped", result.skipped[0][1])
    if result.wasSuccessful():
        return ProbeExecution("passed", "")
    return ProbeExecution("failed", "unittest did not report success")
```

```bash
env PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 /tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B -m unittest tests.test_run_native_probe_ci.TestNativeProbeCi.test_unittest_probe_real_class_setup_skip_and_failure_lifecycle tests.test_run_native_probe_ci.TestNativeProbeCi.test_unittest探针结果区分通过跳过和失败 tests.test_run_native_probe_ci.TestNativeProbeCi.test_unittest探针执行测试类级资源生命周期 -v
```

Expected：新 guard 与两个既有方法各 PASS/0F/E/skip；内部真实 skip 只被 guard 断言，不是外层测试 skip。确认 RED→GREEN 和调用方兼容后才进入下列 loader RED→GREEN，不以新 loader mock 通过替代本门。

- [ ] **Step 1：先追加实际缺选断言，取得真实 RED。**

在 `tests/test_run_native_probe_ci.py:TestNativeProbeCi` 追加下列 loader 方法。新增 setUp 在 Step 3 才落地；旧源码没有该function时首断言就是 AssertionError，不是 fixture异常/TypeError。Step 3后 `real_engineering_bridge_probe`由新setUp保存原function，此处不会调用实际helper/CP。

```python
    def test_linux_engineering_bridge_loader_selects_one_existing_case(self):
        probe = getattr(run_native_probe_ci, "_probe_linux_engineering_bridge", None)
        self.assertTrue(callable(probe), "engineering bridge case is not selected by native CI")
        from tests.test_linux_contract_engineering import TestLinuxContractEngineering
        with mock.patch.object(run_native_probe_ci.sys, "platform", "linux"), \
             mock.patch.object(run_native_probe_ci, "_run_unittest_probe",
                               return_value=run_native_probe_ci.ProbeExecution("passed", "")) as selected:
            result = self.real_engineering_bridge_probe()
        self.assertEqual(result.status, "passed")
        selected.assert_called_once()
        case = selected.call_args.args[0]
        self.assertIs(type(case), TestLinuxContractEngineering)
        self.assertEqual(case._testMethodName, "test_bridge_code_cp_receipt_and_pack")
```

```bash
env PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 /tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B -m unittest tests.test_run_native_probe_ci.TestNativeProbeCi.test_linux_engineering_bridge_loader_selects_one_existing_case -v
```

Expected RED：该方法 AssertionError `engineering bridge case is not selected by native CI`。确认实际失败种类/断言后才接线；不把G1 admission诊断或某脚本import错误当这项RED。

- [ ] **Step 2：新增 probe，按原 `_check` 接线以下精确增量。**

`scripts/run_native_probe_ci.py` 在 `_probe_linux_observed_command_bounds` 之后追加完整函数：

```python
def _probe_linux_engineering_bridge() -> ProbeExecution:
    """Actual source bridge diagnostic; never a Native readiness capability."""
    if not sys.platform.startswith("linux"):
        return ProbeExecution("skipped", "linux_only")
    repository_root = str(Path(__file__).resolve().parents[1])
    if repository_root not in sys.path:
        sys.path.insert(0, repository_root)
    try:
        from tests.test_linux_contract_engineering import TestLinuxContractEngineering
        case = TestLinuxContractEngineering("test_bridge_code_cp_receipt_and_pack")
    except Exception:
        return ProbeExecution("failed", "engineering_bridge_case_unavailable")
    result = _run_unittest_probe(case)
    if result.status == "passed":
        return ProbeExecution("passed", "source_cp_receipt_partial_pack_observed")
    if result.status == "skipped":
        return ProbeExecution("skipped", "engineering_bridge_prerequisite_unavailable")
    return ProbeExecution("failed", "engineering_bridge_rejected")
```

`_check` 原变量/调用/结果路径最小修改（以下是全部新增逻辑；既有原判断保留）：

```diff
@@ function-local probe results
     observed_command_bounds_result = None
+    engineering_bridge_result = None
@@ Linux branch, after the existing bounds probe
         observed_command_bounds_result = _probe_linux_observed_command_bounds()
+        engineering_bridge_result = _probe_linux_engineering_bridge()
@@ function-local failure flags
     observed_command_bounds_failed = False
+    engineering_bridge_failed = False
@@ before iterating the original result.checks and scoring
+    if engineering_bridge_result is not None:
+        bridge_status = engineering_bridge_result.status
+        if bridge_status not in {"passed", "skipped", "failed"}:
+            bridge_status = "failed"
+        engineering_bridge_failed = bridge_status == "failed"
+        print(f"::notice::linux-engineering-bridge status={bridge_status} conformance_credit=none native_ready=false")
+        print(f"{backend.name} engineering_bridge: {bridge_status.upper()}")
@@ original failure condition
         not native_ready or group_failed or lease_expiry_failed
         or violation_receipt_failed or observed_command_bounds_failed
+        or engineering_bridge_failed
@@ fixed failure messages, after observed_command_bounds_failed
+        if engineering_bridge_failed:
+            failures.append("source engineering bridge: failed")
```

没有 `checks.update`、score参数、`native_ready` 赋值、ready flag新逻辑；诊断失败令现有job失败，确缺 prerequisite 的skip不令诊断PASS、不授conformance。非Linux branch不调用。source probe保留真实helper class lifecycle，不重复选择整class；root另独立执行完整21方法。

- [ ] **Step 3：补便携 unit 测试隔离与诊断三态/无评分断言。**

在同 `TestNativeProbeCi` class新增以下setUp，避免旧 portable `_check`单测意外启动真实新helper或scope。只影响新诊断 seam；原已有各种mock/路径不改。新增guard方法调用保存的realfunction并mock原 `_run_unittest_probe`，明确仅加载协议层；原fixture生命周期unit仍保留。以下方法不复制native通过数。

```python
    def setUp(self):
        self.real_engineering_bridge_probe = run_native_probe_ci._probe_linux_engineering_bridge
        default_probe = mock.patch.object(run_native_probe_ci, "_probe_linux_engineering_bridge",
            return_value=run_native_probe_ci.ProbeExecution("skipped", "portable_unit_test_no_native_credit"))
        self.bridge_probe_double = default_probe.start()
        self.addCleanup(default_probe.stop)

    def test_linux_engineering_bridge_skip_and_failure_keep_three_states(self):
        for status in ("passed", "skipped", "failed"):
            with self.subTest(status=status), mock.patch.object(run_native_probe_ci.sys, "platform", "linux"), \
                 mock.patch.object(run_native_probe_ci, "_run_unittest_probe",
                     return_value=run_native_probe_ci.ProbeExecution(status, "non-sensitive fixture")) as execute:
                result = self.real_engineering_bridge_probe()
            self.assertEqual(result.status, status)
            execute.assert_called_once()
        with mock.patch.object(run_native_probe_ci.sys, "platform", "darwin"), \
             mock.patch.object(run_native_probe_ci, "_run_unittest_probe") as execute:
            self.assertEqual(self.real_engineering_bridge_probe().status, "skipped")
        execute.assert_not_called()

    def test_linux_engineering_bridge_diagnostic_selected_once_never_scored(self):
        for status in ("passed", "skipped", "failed", "unknown"):
            with self.subTest(status=status):
                self.bridge_probe_double.reset_mock()
                self.bridge_probe_double.return_value = SimpleNamespace(status=status, detail="fixture")
                result, lease, score, output = self._run_linux_check_with_lease_expiry(
                    run_native_probe_ci.ProbeExecution("passed", "fixture"))
                self.bridge_probe_double.assert_called_once_with()
                self.assertEqual(result, 1 if status in ("failed", "unknown") else 0)
                self.assertIn("linux-engineering-bridge status=" + ("failed" if status == "unknown" else status), output)
                self.assertIn("conformance_credit=none native_ready=false", output)
                self.assertNotIn("engineering_bridge", score.call_args.args[0])
                self.assertNotIn("engineering_bridge", score.call_args.kwargs)
```

- [ ] **Step 4：实际 GREEN 与 source Linux诊断分开运行。**

```bash
env PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 /tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B -m unittest tests.test_run_native_probe_ci -v
env PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 GOMAXPROCS=1 GOFLAGS=-p=1 CMAKE_BUILD_PARALLEL_LEVEL=1 /tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B scripts/run_native_probe_ci.py
```

第一命令：原portable unittest加4新方法（1真实生命周期guard + 3 loader/诊断guard）实际all0F/E/skip；生命周期的9子场景不另算方法。第二命令：新的bridge诊断实际一方法；真实类setup缺前置条件仅 skipped/无信用，setup/cleanup错误及skip伴failure/error仍 failed；原native其他门如不通过，job整体仍failure并如实记录，不把bridge诊断成功顶掉原ready/conformance结果。native helper/compiler均串行，测试不和其它真实scope/full并行。

- [ ] **Step 5：作者自SPEC/QUALITY、fresh SPEC→不同QUALITY。**

核旧unit不意外真实启动、原helper两类RED归因及共享callers回归、新的真实Linuxjob恰好选一个case/执行class资源lifecycle、纯setup skip与零测试/混合错误分类、失败注解固定且无path/rawstderr；所有conformance/ready原合同保持。

## Task 5：全局软件验收、阶段证据、main 发布与新 SHA 观察

**状态**

- [ ] 任务完成

**Dependencies:** Task 1, Task 2, Task 3, Task 4
**Parallelizable:** No (writer全部STOP，同冻结源、软件门与发布必须串行)

- [ ] **Step 1：fresh全局SPEC→不同QUALITY，root读实际新增全文与所有接线diff。**

scope应仅新测试/native调度及守卫、本片证据文档；实际runner Git生产diff必须来自G0独立slice，不计本片偷加。冻结source SHA256及vendor gitlink；本片21 native方法、3 portable fixture方法与4新增portable选择方法分别登记实际distinct IDs，native probe单case诊断不能充完整matrix。源码基线变化重核当前期望，不把8d旧softwarefull再跑一遍充新完成。

- [ ] **Step 2：点测→20轮→DEFAULT→同冻结源原full恰好一次。**

```bash
env PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 GOMAXPROCS=1 GOFLAGS=-p=1 CMAKE_BUILD_PARALLEL_LEVEL=1 /tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B -m unittest tests.test_linux_contract_engineering tests.test_run_native_probe_ci tests.test_contract_engineering tests.test_engineering_verification.TestPythonIsolatedTemplate tests.test_engineering_evidence -v
```

20轮选择固定source正控 code/deepcheck2方法、3 portable fixture guard及4 native选择portable guard（每轮9方法，180个actual运行）串行；每轮actualexit0/外层无skip才计正控，生命周期guard内部的预期skip不授native信用。全21 native方法另点测，不能把20轮同方法算180个不同功能；18工程向量与21原生方法计数不变。执行20轮的完整host脚本：

```python
import subprocess
import sys
names = (
    "tests.test_linux_contract_engineering.TestLinuxContractEngineering.test_bridge_code_cp_receipt_and_pack",
    "tests.test_linux_contract_engineering.TestLinuxContractEngineering.test_bridge_deepcheck_fixed_scope_cp_receipt_and_pack",
    "tests.test_linux_contract_engineering.TestBridgeObservationSafety.test_memory_observer_preserves_original_result_and_ack_order_without_io",
    "tests.test_linux_contract_engineering.TestBridgeObservationSafety.test_observer_fault_keeps_ack_but_original_abort_is_rethrown",
    "tests.test_linux_contract_engineering.TestBridgeObservationSafety.test_pending_and_sticky_unknown_protect_owned_root_until_confirmed",
    "tests.test_run_native_probe_ci.TestNativeProbeCi.test_unittest_probe_real_class_setup_skip_and_failure_lifecycle",
    "tests.test_run_native_probe_ci.TestNativeProbeCi.test_linux_engineering_bridge_loader_selects_one_existing_case",
    "tests.test_run_native_probe_ci.TestNativeProbeCi.test_linux_engineering_bridge_skip_and_failure_keep_three_states",
    "tests.test_run_native_probe_ci.TestNativeProbeCi.test_linux_engineering_bridge_diagnostic_selected_once_never_scored",
)
for number in range(1, 21):
    result = subprocess.run([sys.executable, "-B", "-m", "unittest", *names, "-v"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, check=False)
    print(f"bridge round={number} exit={result.returncode}", flush=True)
    print(result.stderr, flush=True)
    assert result.returncode == 0 and "skipped=" not in result.stderr
    assert "Ran 9 tests" in result.stderr
```

root通过exec持久session的产品机制执行该脚本；不要用shell写临时文件或把敏感env打印出来。Python只用于执行测试，不编辑/读写计划。

```bash
env PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 GOMAXPROCS=1 GOFLAGS=-p=1 CMAKE_BUILD_PARALLEL_LEVEL=1 /tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B scripts/run_workspace_ci.py
env PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 GOMAXPROCS=1 GOFLAGS=-p=1 CMAKE_BUILD_PARALLEL_LEVEL=1 /tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B scripts/preflight.py
```

DEFAULT仅原portable集合，不新增Linux静态skip。原full子进程保持原argv/kwargs/环境，恰好一次；实际total/P/F/E/skip与bootstrap binding独立记录，不猜动态方法总数。无源变化的文档收尾不重复full，源发生修复则更新冻结身份、重过所需软件门，不能称旧full为新源证据。

- [ ] **Step 3：编译j1、非测试守卫、文档连续两clean和七维报告。**

```bash
env PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 /tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B -m compileall -q -j 1 src tests scripts
env PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 /tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B scripts/preflight.py --only secrets
env PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 /tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B scripts/preflight.py --only submodule
env PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 /tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B scripts/check_governance.py
env PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 /tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B scripts/check_site.py
env PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 /tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B scripts/check_agent_landscape.py --today 2026-10-09
git diff --check
```

root更新当前18向量实际结果与G1/G2，闭与未闭分层。doc-contract脚本跑本文/设计/研究/L1/新增blockers/实际证据两轮，各0疑似项并人工核方法数、枚举、阶段、字段、版本/链接。代码assert通过只授对应软件层；报告可运行性仅实际执行范围，不写R2/R3或Native100%。

- [ ] **Step 4：仅验收后的exact main commit/push，绑定新SHA观察。**

root重新只读核dirty和允许文件，对本文ignored路径仅force exact单个文件；不得stage他人改动、批量force docs目录。提交前所有source冻结、七维与文档两clean成立，正常gitcommit和push main；用户已授权阶段推送。原8d所有线上runs已STOP，本片只观察新commit实际CI/Pages/Windows provenance直到终态，不反复轮询旧runs。源Linux诊断、installed wheel现有诊断、native其他门与模型分开记录；不因Pages/签名绿色宣布R2/R3整体通过。

## 18 向量逐项映射与剩余门（不是18方法或当前PASS）

| ID | 具体实际入口/方法或已存在证据 | 本计划允许结果 |
| --- | --- | --- |
| CMD-01 | L1 quota `test_registry_cap_one_enforces_real_fork_quota`、`test_thread_is_charged_and_supervisor_is_outside_payload`、`test_cap_two_sets_id_child_cannot_create_third_task` | 旧L1本机source观察；本片新scope只补same-run连接，不复数 |
| CMD-02 | L1 violation `test_caught_network_socket_denial_returns_os_enforced_receipt`、`test_allowed_unix_socketpair_does_not_emit_violation_receipt`、`test_landlock_file_write_denial_is_not_misattributed_to_seccomp` | 原已覆盖类别，非uniform所有类别 |
| CMD-03 | L1 quota `test_sys_cgroup_is_not_authorized_and_stdout_cannot_forge_receipt`、violation `test_ordinary_exit_13_does_not_emit_violation_receipt` | old source通道区分，无stdout来源认证 |
| CMD-04 | L1 quota `test_timeout_and_output_limit_collect_exact_scope`、新增fixture observe/assert_collected及真实timeout/outputlimit方法 | exact owned scope，不授他人/global cleanup |
| CMD-05 | L1 quota `test_no_bus_wrong_tool_and_out_of_range_cap_fail_before_launch`、`test_ack_wrong_fields_timeout_and_callback_exception_never_release_payload`；violation4 observer/ack failure方法 | 明确故障注入/前置拒绝，不把None写exec started |
| CMD-06 | L1 quota `test_two_concurrent_scopes_are_independent`、`test_host_sigkill_removes_charged_setsid_descendants_without_python_finally` | 旧source命令层；dead zombie允许，不称init已回收 |
| ENG-01 | 新 `test_real_session_prepare_rejects_nested_deny_without_deleting_protection` | prepare可表达子集与拒绝，不授ready |
| ENG-02 | 新code/deepcheck2 L2a方法，实际framework≥1、original dispatch/resource/scope | 真实source plan→gate子门 |
| ENG-03 | 新 assertion/import failure方法（2子向量/2checks） | deterministicfailure→闭failure，later not_run，无Reviewer |
| ENG-04 | 新真实timeout/outputlimit、injected observer/channel/cleanup方法 | unknown action保留，CP不补finish |
| ENG-05 | 新 frozen-plan drift方法（5子向量） | originaladmission，零本次dispatch；无平台fallback |
| ENG-06 | 新实际test源码写、HEAD变化、Reviewer后源码、deepcheck开始后source/scope、finalCP方法 | G0通过后的真实树/稳定窗口；split结果commit仍不支持 |
| CP-01 | code L2a method的actualoperation不同attempt、唯一receipt、first/replayverification事件与指纹 | host CP已消费，step未关闭不报成功 |
| CP-02 | 新execution-root/wrongattempt/recordack/publicresume/同recorder新occurrence方法 | G1已单独验收；本片其余真实子向量待运行，当前不授整项通过 |
| REV-01 | L2a fresh只读read/submit及5协议负例、实际源码漂移 | model_double协议/应用只读，不授语义/独立OS沙箱 |
| PACK-01 | L2a真实partial导出/原verify_pack/外部cwd新processverify.py；4坏receipt负例 | 结构一致性，不授认证/整流程/完整历史body |
| STEP-01 | 新full-code/full-deepcheck方法真实读取/partial debt/工程/推演/successfinish拒绝 | **G2完整成功正控blocked**；仅原拒绝及已过子门，无先前三步模型信用 |
| NATIVE-01 | 新realLandlock/session普通Native派生，provider/model/stepstart未调 | 原readyFalse继续拒绝；不称整个run零控制写 |

CMD系列原40方法可按root实际证据追溯，不在新文件wrapper调用旧方法来重复选或虚增新方法数；新class不继承两个旧TestCase，也不加载整个class两次。需要新基线命令层refresh时root显式运行旧两class单次并记录新run/binary/manifest，不能从已有记录抹掉来源缺口。

## 实际读取、自审、交付范围与未完成门

计划作者全文读 writing-plans、doc-contract技能及其实际`check_consistency.py`210行；三步sequential-thinking结果记录context（需求→复用→风险）。完整读4输入文档（第一次合并输出外层截断后分别补读已选全段）与root新增blockers记录。实际本仓阅读：tests/_support全文；operations全文；chain全文1–390；control1–400；runner1153–1610/1713–1927/2015–2110/2432–2525/2567–2768/3017–3140/3280–3465；workspace363–494/1609–1705/2080–2220；isolation860–1035；engineering_verification100–290/419–545/672–750；engineering_evidence1–210；evidence1006–1105；tests契约1–220/340–410/476–558/795–848/860–1060；quota15–62/449–622，violation1–132；native source runner全文1–415，wheel1–190和installedviolation全文；native选择测试1–135/190–225；workspace选择1–200及guard头部；vendor inspection1–425（未全文余46行），control1180–1265/1280–1312/1490–1575/1674–1752/4470–4538/4545–4765/4845–4908，execution contract235–267。其余只rg符号定位，不能冒称整工程/native C安全审查。

原稿作者没有运行import/测试/compile/install/native/provider、网络查询或模型HTTP，没有读取KEY；其上游结论来自已经完整回读的独立研究记录，不伪称新抓取当前HEAD或全20项目。本轮仅为root新增I3只读核上述两页Python3.11官方可用性文档及已列入口的顶层import文本，没有执行任何应用import或测试，也未开展新竞品研究。

作者自SPEC：将设计18ID完整映射，G0先决、G1/G2新缺口保留，完整source正控仅L2a，ordinarysuccess目标未删而明确blocked；未知清理/None/假summary/partial/真实模型均不upgrade，计划代码定义与使用一致。作者自QUALITY：最小单文件fixture，既有接口复用，原CP/dispatch/保护/gates/ready未改，source selection一次且legacyportable不意外启动native，所有构建串行；仍待fresh独立SPEC与不同QUALITY。自审修订历史：纠正 Reviewer 枚举、合法 `.icode_output` 路径、治理脚本实际文件名；以 module 别名复用旧 quota assert，避免 unittest 将直接导入的旧 TestCase 再次收集。任何后续审查发现问题须保留修订历史，不把自审当独立批准。

只读冻结说明：本作者没有任何 source 写入。root 已另授权 Git Task 1 的唯一源码作者并行工作，故本计划的源文件末次指纹是观察时点，不承诺整仓继续保持旧 8d；并行源码变化不归本文作者，也不替代 G0 全片软件验收。只过外部 Git Task 1 核心接口 GREEN 不足以开始 bridge。

原文档作者两轮 selfSPEC/QUALITY 曾给出 C0/I0/M0（只限静态计划范围），该自审遗漏了真实类 setup skip 分类缺口。随后 fresh 独立 SPEC 对原计划 SHA256 `ddf94e1d11af57cbabbf223319f93b532a5f9e8688c57009ee86e9be9089470f` 给出 **C0/I1/M0**：Task 1 的 `setUpClass SkipTest` 和原 helper 的先判计数冲突，Task 4 三态 mock 不覆盖真实生命周期。此结论属于原稿审查历史，不能用作者修订自审覆盖或写成独立复审已通过。

前次 I1 修订作者完整回读本文1136行原稿、设计192行、blockers全文、仓库 AGENTS、writing-plans/doc-contract技能全文和其检查脚本；另只读核 `scripts/run_native_probe_ci.py:1–90`（SHA256 `2bd6c3ab81738d803944d66988172bd2758428ecf33bf416f8648b56db4baa76`）、现有选择测试1–145及实际可信解释器对应 Python 3.11.15 标准库的 class fixture/holder ID 接口。三步 sequential-thinking 已记录 context。原计划作者更广阅读范围保留为其历史，不挪给本次修订作者。本文以外并行 source writer/QUALITY 的变化不归本作者；外部 Git slice 冻结与 G0 状态仍由 root 登记，不因本次文档修订重开 G0/G1/G2。

前次先 selfSPEC：核 I1 的真实失败路径、Step 0a→0b→loader RED→GREEN、已列两文件责任、9生命周期子场景/1 guard、4新增portable方法/当时每轮6方法/120次与18向量/21原生方法一致；再 selfQUALITY：核原suite/result/helper无mock生命周期、纯对应类setup skip判定、零测试/setup error/cleanup error/skip伴failure或error失败、既有method skip与正常生命周期保留、共享callers和无评分/ready影响。该次修订作者自审 C0/I0/M0 仅是静态计划判断，未发现下述QUALITY问题，不是独立审查通过。

different QUALITY 对上一版本文 SHA256 `0887707ca80821c539cf9d9542a0d3557508030785f290dadb015caffe6d4541`（1261行）最终给出 **C0/I2/M0** 并STOP，root独立复核接受：I1 是原dispatch无返回/中断及独立收束assert失败没有锁unknown，fixture可能删owned根；I2 是ACK前configured observer额外stat/path read/pids.max解析，观察异常/时间成本可能改变broker配置路径。原SPEC I1的修订及上次作者漏审历史保留；不能用新自审结果覆盖这次QUALITY记录。

其后root另发现 I3：新模块顶层LinuxScope导入会因Unix flags在Windows失败，且原classskip无法保护import。它是root新增问题，不归入此前differentQUALITY的C0/I2/M0。作者随后静态核发现旧quota fixture的间接 `fcntl` 顶层路径，故两者均延迟到真实Linux构造；portable观察用显式FakeScope和collection double，加fresh import子场景，方法数仍3。不修改生产LinuxScope/seccomp/flags，不通过默认0或全classskip隐藏不兼容；I3只获静态修订信用，实际Windows门未通过。

本轮仅修计划fixture观察/保留和3个独立portable guard。root实读提供的当前接口事实是 `_identities` 为3个inode双元组的list，`limit` 为已验证int、`version` 为查询缓存int，原配置成功末尾记录 `_owned/_invocation/_path`；旧描述中的“三元组”不正确，本轮已按准确cache更正。设计要求未知收束保留owned根，原broker finally可抛BaseException、原quota收束检查可抛异常；这两个生产机制不在本轮修改范围。原configured异常在observer-only try之外原样传播；自身cache观察异常记录为host拒绝信用，callback沿原返回继续ACK。不存在对callback时间预算零成本或真实新kernel观测的承诺。

本轮先 selfSPEC：核 dispatch开始pending→正常原result+独立owned收束确认才解pending，任何无返回/异常/收束失败unknown sticky，全入口含full/负控统一observe，close拒绝pending/unknown删除，后续成功不清历史unknown；再核原配置内存copy、原返回/异常/ACK合同、Linux依赖只在真实构造加载、独立portable class的FakeScope/collection与import子场景不受native skip、21native+3fixture/4选择guard及20轮9方法180次。再 selfQUALITY：原中断对象不吞不换、不在异常传播时发新查询，观察错误不污染ACK，禁止新I/O/query/sleep，根inode绑定不扩大、无retry/补CPfinish/stop他人unit，顶层关联fcntl路径同步收紧、官方平台文档与真实Windows信用区分，fake unit与真实native信用分开。三步sequential-thinking已记context。修订作者静态自审 C0/I0/M0，下一门为同一SPEC→同一differentQUALITY复审；不授独立批准或运行信用。本轮root通知新Git Task 2 source writer已STOP并进入审核，源变化不归本作者，G0仍未closed，G1/G2及ordinary完整成功/installed/model门不变。

本次仅写本文；实际执行为独立文档检查脚本两轮连续0疑似项和本文 `git diff --check`；本文尚未被 Git 跟踪，故另用 `git diff --no-index --check /dev/null docs/nbl/plans/2026-10-09-linux-engineering-bridge.md` 检查全文空白错误，不能以空 tracked diff 代替检查。上述不是 ICODE import/测试/编译。测试/import/native/helper编译/安装/model HTTP/KEY访问/commit/push/新子代理均0。计划源码必须等原软件门后由获准作者实际验证，本文不提前授运行信用。

【架构级自检报告】（仅计划文档层）

- ✅ 语法/结构：Markdown/代码围栏/表格/路径与具体命令已静态核对，运行语法/编译未执行。
- ✅ 依赖/调用链：G0→实际plan/CP/operation/Reviewer/pack→普通门→native选择逐项明确；统一owned收束检查、原helper生命周期先RED→GREEN，G1/G2分别未闭。
- ✅ 逻辑/边界：code/deepcheck冻结时点、real/injected/model_double、CP UUID与host run、18向量/21native/3fixture/4选择guard/20轮180次不混淆。
- ✅ 异常处理：原BaseException原样传播，pending/unknown保留根且unknown sticky，观察错误独立拒绝信用不污染ACK；纯类setup skip仅skipped，零测试/混合错误failed；不重放或清partial债务。
- ✅ 关联模块：本次作者只修本文；未来fixture与portable守卫在原new test文件，helper分类/选择守卫限原已列Task 4两文件，不暗改其它production/vendor/平台准入。
- ✅ 兼容安全：LinuxScope/quota依赖延迟到真实构造，独立portable class显式double且有import守卫；原DEFAULT、旧tests签名、source/installed来源、权限/KEY边界保留，Windows原生尚未验收。
- ⚠️ 可运行性：完整代码与实际接口静态可审，尚未实施/执行，不写100%运行或R2/R3完成。

未完成门（作者交付时）：本计划独立双审、G0生产修复软件门、source实际L2a/矩阵/诊断与全局软件发布；G1内部重入修复；G2新增授权/身份范围设计/完整步骤正控；installed工程桥接与helper来源；Native完整政策、Windows/macOS剩余、真实modelendpoint/1→6/≥90%与R2/R3整体。本文允许交付“可执行部分桥接实施计划与新增阻塞”，不允许“Linux工程完整完成”。

### root 当前审查记录（2026-10-09）

修订后1556行计划冻结 SHA256 `b0ede81f6f8858595484fb5864c102c7c01069052df2baada85acf2e1c520171` 已经同 SPEC `/root/linux_bridge_plan_spec` 全文复审 C0/I0/M0、同不同 QUALITY `/root/linux_bridge_plan_quality` 全文复审 C0/I0/M0，两者均只读、零 import/test/compile，并已STOP。原 QUALITY I1/I2 与 root 独立 I3 仅在计划层关闭；上文原审查历史不删除。root实读原1136行全文、随后生命周期修订与当前观察/收束/portable导入、计数/全入口及历史增量，另核实际 scope/cache/ACK/broker finally/收束与传递 fcntl 导入。root仅追加此状态记录，不改获准计划代码或授运行信用。

当前外部 Git slice 的 Task1–3 与全局独立双审已通过；root定点102项、20×15共300次及DEFAULT595项均0F/E/skip。新冻结原full恰好一次2454total/2395P/59环境skip/0F/E、j1编译及非测试守卫已通过；文档/索引/main发布门正在收尾。本计划尚未开始实施，G0待实际收尾登记，不因静态批准授bridge运行信用。G1/G2、source L2a完整矩阵、installed、Native与模型门继续未验；后续以该片新基线登记为准。

---
**Execution Mode:** serial

执行交接由root使用nbl.subagent-driven-development，每任务fresh writer与双审，全局审查后发布。本计划作者STOP，不依技能惯例自行启动下一任务或新agents（任务明确只规划、外部依赖未过）。

## root实施启动（2026-10-09）

本片实际基线为已发布main `020acebf51b61179bf401181ac703cb3d71446b6`，vendor仍1693651。G0已在923完成生产接线、独立审查和软件发布；G1随后在020aceb修复旧start回执的执行许可，四任务及全局独立双审通过，root定点141P、20轮320次、DEFAULT609P、原full一次2469total/2410P/59skip/0F/E、j1/守卫/文档及精确main发布通过。前述G0/G1 blocked属于旧设计窗口，当前不再阻止本片启动；它们的软件信用仍不替本片真实Linux运行。

root已完整回读本计划全部任务与四份设计/研究/命令证据/阻塞记录，另核现scope配置cache、原收束检查、实际gate/loader，sequential-thinking172–174完成需求、复用和风险评估。Task1唯一writer `/root/linux_bridge_task1_writer` 仅新增测试文件并独占runtime；root只更新文档与读结果，CI观察独立只读。获准fixture与任务代码未变，原18向量/21native+3portable/4选择guard边界保持。G2额外vendor授权和完整步骤成功、installed、Native及模型门继续未通过。

并行独立研究 `/root/linux_bridge_stage_start_research` 已DONE STOP，窗口08:02:07–08:05:59 UTC：Codex main2351d9e、Aider main5dc9490，固定来源与取舍补充到配套研究记录。只读研究未运行本工程或修改文件，不授实际资源/恢复/清理信用。

### Task1首次执行：控制面创建契约阻塞（2026-10-09）

作者仅新增 `tests/test_linux_contract_engineering.py`，604行，SHA256 `e14e2c6c61811ba5b645e7c7eb8791442cfb2af53b2e80b6bbfe256102eeba58`。portable实际3P/0F/0E/0skip、13子场景、0.170秒、rc0；两个Linux正控实际0P/0F/2E/0skip、0.875秒、rc1。helper编译成功，但未登记该次二进制/manifest摘要。两例均在create被拒，错误为 `--metadata-json 含控制面受保护字段: ['project_path']`；dispatch、Reviewer、receipt、pack均为0。原cleanup已回收两个未dispatch的owned目录，并只读确认不存在；无运行中scope。

root核对vendor `cmd_create`、`classify_ticket_dir`、`trusted_execution_workspace`和生产runner：create从标准工单目录推导workspace并自动填写受保护project_path；去掉seed字段会绑定control根而非session代码根。active_checkout又要求实际独立Git checkout，与当前无.git代码树不符。生产runner复用工单时严格比较action-policy.execution_root，因此不能靠只改测试断言解决。批准示例与现存契约冲突；此前计划静态双审没有发现此问题，不授运行信用。

Task1作者selfSPEC仍有I1，selfQUALITY未宣告通过，Task2未启动。保留失败文件；不直接写保护字段、不伪造legacy迁移、不把控制数据移进代码树。root已请求独立只读复核现存入口，并单独询问新增最小受校验、事件化宿主绑定接口的vendor授权；该事项超出已完成的三个Python校验器授权。授权和契约设计未完成前，不修改vendor，不声称Linux工程桥接完成。其它不依赖此项的工作继续。

随后用户明确答复“允许最小契约修复及验收后推送”。独立只读复核确认create-next、reopen、migration也不能提供现成可信split绑定。新设计见 [执行根绑定](../specs/2026-10-09-execution-root-binding-design.md)：先修专用宿主绑定、在线根消费与离线语义，再恢复Task1。只此授权已解除；G2 inspection Git身份与Windows Git管道的额外授权不因此扩展。子仓库独立main及远端main实核仍1693651，工作区干净；计划阶段不改vendor固定副本。

### 前置绑定合同已发布，主工程接入复核中

子仓库最小绑定实现经独立 SPEC、不同 QUALITY、五项旧契约、23项新增模块20轮共460P零skip及j1语法检查，已提交推送 main `d935a5218ca2970bce8157814bfda1f03aa6c9c4` 并核远端。root 已将干净 vendor 固定到该 SHA。主工程 wrapper/离线验证/fixture/CI 接线四模块217P零skip；发现并同步随包固定来源与72成员清单，完整安装测试18P零skip，实际wheel和独立sdist安装消费新入口。完整接入正在独立双审，尚未再次运行本文件两个真实Linux正控，因此创建阻塞解除不能提前记为dispatch/Reviewer/receipt/pack通过。详细冻结与证据见[绑定执行记录](2026-10-09-execution-root-binding.md)。

接入独立SPEC随后51P零skip、无问题。root首次恢复实跑本模块5P/0F/0E/0skip、5.633s、rc0，包括3portable与2真实Linux code/deepcheck正控：每例实际命令exit0、scope_cleanup_ok true、observer complete，CP operation/verification回执和fresh Reviewer三调用断言通过，独立partial pack通过。测试使用模型double且step保持开放，native_ready仍false；不称完整步骤、installed工程桥接或R2/R3通过。helper、源、receipt和pack摘要已记绑定执行记录。主仓软件全局门与发布仍待执行，再继续本计划后续负控/普通步骤/诊断接线。

### 下一任务静态就绪核对

绑定片全局预检期间，独立只读 `/root/linux_bridge_next_readiness` 核对 Task2 的16个新增方法与当前实际接口，发现并由root修正：wrong-ticket fixture 不能再通过create注入project_path，改合法普通建单并明确核action-policy根等于wrong_root且不等于f.root；追加 Checkpointer/ControlResult/EvidenceError 三个已有模块导入说明。独立复核确认两项已修正。Task2/Task3当前说明与CP-02表同步G1已由020aceb验收，历史诊断保留并加历史标记；同recorder新occurrence仍断言 engineering_operation_start_unconfirmed，HEAD变化仍按实际包装异常断言ValueError，不把它们改成另一错误来凑通过。

本次只修实施计划，没有新增负控方法或运行它们；18 runtime向量、后续21 native+3portable方法计数不变。源码冻结与正在运行的绑定片full预检未受影响。下一writer在绑定片发布后接手此文件，仍保留G2/Windows/model及未知清理边界。

绑定片发布前全局复验已通过：DEFAULT614P零skip，原full2479total/2420P/59skip/0F/E，j1编译、治理/站点/排期检查通过。首次full的旧HEAD检出测试2个subTest失败保留在绑定记录，最小修正为暂存树检出后完整重跑成功，未先提交绕过检查。此处Task1已完成；Task2尚未写入或执行，下一作者仅接手16个新增负控，不能将这里的全量结果转记为后续方法已通过。
