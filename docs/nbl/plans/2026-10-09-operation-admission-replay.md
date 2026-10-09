# G1 动作准入与旧回执重放 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development (recommended) or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让真实 CP 返回的旧 start 回执不再授权普通工具或工程载荷，同时保持首次响应、旧构造、错误类别与恢复前置兼容。

**Architecture:** 复用 `OperationRecorder`，向 `StartedOperation` 末尾追加严格布尔 replay marker，并让原 `can_execute` 在载荷前拒绝旧回执。两个生产消费者只消费该事实，不从 trace、重新编号或补 finish 推导新许可。CP 仍是持久真源。

**Tech Stack:** Python 标准库、unittest、固定 ICODE-SKILL 控制面；无新依赖、权限、schema 或 Native readiness 变化。

---

日期：2026-10-09。作者交付时仅为静态候选；当前Task1–4及全局独立双审通过，root定点141项、20轮320次、DEFAULT609项与原full2469项验收结束，编译及守卫通过。文档收尾与main发布待。基线 `923433b5d6be5e3bda05684ef4ed98daa69eb9e7`，原设计的8d观察历史保留；实际结果见末节。
设计 [G1 最小修复设计](../specs/2026-10-09-operation-admission-replay-design.md) 原作者快照为186行、SHA256 `1b2c718d1288c142f46c49fef0537b87a9791f5bbceec4ce1d0671a2af6106a8`；fresh SPEC `operation_admission_design_spec` 和不同 QUALITY `operation_admission_design_quality` 均 C0/I0/M0、纯静态。当前另附root实施记录，该历史摘要不代表当前整文件。
固定 vendor 为 `1693651c1bd7daad3272eb054f0f81d6f254d08d`。本作者只新增本文；不调用 CP/runtime import/模型/KEY，不测试、不改源码、不操作 Git index/commit/push、不派子代理。执行需本文独立双审和 root 批准；不进入执行技能。

## 约束、来源与文件职责

用户明确 main-only、连续推进、编译 j1 且不超过 j6；因此覆盖 writing-plans 默认 worktree 和每任务 commit 建议：不建分支/工作树，任务仅形成可审查增量，整片最终验证通过后一次精确提交推送。各任务唯一 writer，所有运行串行；独立只读研究、审查与新 SHA 观察可并行但不能与测试争用/改源。
三问已确认：真实问题是旧 admission 被 wrapper 丢失；已有 recorder、两个前置门和真实 CP fixture；调用链是 CP→recorder→loop / engineering gate。原两次 `_next_occurrence`、scope/name/action/input/request、finish 与 recovery 请求全部不改。

复用 [持续对照](../../agent-landscape-live.md) 2026-10-09 04:25–04:27 UTC 独立研究，不重新调查20项：LangGraph `bfcfea554ed5c7f7be562cebf8825e911b493ab1` 和官方 docs `be3028f3b446d7cfc63b434faf4e594689129251`。
来源是 [固定 runner](https://github.com/langchain-ai/langgraph/blob/bfcfea554ed5c7f7be562cebf8825e911b493ab1/libs/langgraph/langgraph/pregel/_runner.py#L747-L764) 与 [固定 Functional API](https://github.com/langchain-ai/docs/blob/be3028f3b446d7cfc63b434faf4e594689129251/src/oss/langgraph/functional-api.mdx#L790-L810)；此前研究者全文核两 MIT LICENSE，本作者只实读本地研究记录，不冒称本次联网或许可全文复核。06:15–06:16 UTC 独立 `/root/g1_replay_upstream_refresh` 再核官方main仍同pin，两源码和两license共四blob相同，定点重读runner738–773/885–921和functional780–820；没有新许可全文或全依赖审计，记录已由root更新到持续对照。
采纳：新 admission/旧 receipt/未知结果分离，复用本仓 wrapper，收益是避免 fresh recorder 重入，成本为严格类型兼容与负控。暂缓：业务 reconciliation、结果缓存、自动补偿。不适配：把未完成 task 自动重跑规则用于任意工程载荷、换键绕过、软件成功抵隔离。没有复制上游代码或引入依赖；不承诺 exactly-once。

| 源路径 | 唯一职责 | 所属任务 |
| --- | --- | --- |
| `src/icode/operations.py` | 字段顺序、归一、许可、结构化歧义 | Task 1 |
| 新 `tests/test_operation_admission.py` | 协议5方法、真实 CP/loop/restart7方法；无旧Case继承 | Task 1–2 |
| `src/icode/loop.py` | 旧回执专用中文拒绝，不改执行/finish顺序 | Task 2 |
| `src/icode/runner.py` | 工程早门保留旧 replay 错误类别 | Task 3 |
| `tests/test_contract_engineering.py` | 新工程2方法，复用现有 fixture | Task 3 |
| `scripts/run_workspace_ci.py` | 精准14方法选择及 required skip 拒绝 | Task 4 |
| `tests/test_run_workspace_ci.py` | 新1方法核方法身份、重复、静态与动态 skip | Task 4 |

合计七源；现有 loop/recovery/CLI 测试只运行不改。必要额外测试修改必须先解释真实缺口、给 root 更新 scope，不能临时增加框架。本文和设计及阶段研究/履历文档是独立文档路径，不算七源码。生产仅改字段/分支，不重构巨大 runner。

## 统一运行与审查合同

后续命令从 `/home/orbbec/git/icode` 执行，下列 `python` 指 root 已确认的当前解释器，不能退回 PATH 的 `python3`。沿用 root 当前严格环境：`PYTHONPATH=src:.`、`PYTHONDONTWRITEBYTECODE=1`、`GOMAXPROCS=1`、`GOFLAGS=-p=1`、`GOTOOLCHAIN=local`、`CMAKE_BUILD_PARALLEL_LEVEL=1`，PATH 保留已验 Python/Go 目录；不得读或改模型配置/KEY。
命令示例使用当前现存解释器 `/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python`。实施前 root 只读核它存在及版本；若路径消失，由 root 选已安装解释器并记录实际 cmd，不安装依赖、不用错误解释器取得假 RED。

```bash
env PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 GOMAXPROCS=1 GOFLAGS=-p=1 GOTOOLCHAIN=local CMAKE_BUILD_PARALLEL_LEVEL=1 /tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B -m unittest tests.test_operation_admission -v
```

各命令使用实际严格 PATH 前缀，不复制省略前缀的展示命令冒充原 cmd。真实 `require_skill()` 缺失不得跳过取绿；选择 required 方法的新 loader 明确失败。所有 RED 必须因合同断言失败，不是 ImportError、TypeError、未配置 fixture 或静态 skip。未新增字段阶段先用 `getattr(..., default)` 断言产生因果 RED，追加字段后才加入直接关键字构造兼容矩阵。
每 Task 作者全文读增量后 selfSPEC→selfQUALITY，修复并重新冻结；fresh SPEC→不同 QUALITY 独立检查源码、真实输出、source SHA，不共享运行信用。作者、审者、root 测试不并行。Task boxes 在实际完成前不勾选；原 full 恰好一次规则按新七源最终冻结，旧923/Git五源 full 不重跑。

### Task 1: 共用准入包装与协议边界

**状态**

- [x] 任务完成

**Dependencies:** None（外部：设计与本文独立双审、root批准）
**Parallelizable:** No（唯一源码作者，协议先于两消费者）

- [x] **Step 1: 新建协议 fixture 和五方法；只写测试，不实现。**

新 `tests/test_operation_admission.py` 起始全文如下。`_ResponseCP` 只是协议 double；其原 `ControlResult` 不变，未声称 vendor 会返回 malformed。所有辅助函数非 test，两个类不继承旧测试Case。

```python
"""Admission protocol and real offline CP; never model/native isolation credit."""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from icode.approvals import DenyAllApprover
from icode.backends import FakeBackend
from icode.budget import BudgetTracker
from icode.control import ControlPlane, ControlResult, make_request
from icode.guard import Guard, Scope
from icode.handshake import next_out_dir
from icode.loop import AgentLoop, LoopConfig
from icode.operations import OperationRecorder, StartedOperation
from icode.tools import Tool, ToolContext, ToolRegistry, ToolResult
from tests._support import require_skill, temp_workspace


class _ResponseCP:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def operation_start(self, out_dir, **kwargs):
        self.calls.append((out_dir, kwargs))
        return self.result


class TestOperationAdmissionProtocol(unittest.TestCase):
    def record(self, data, returncode=0, scope=""):
        raw = ControlResult((), returncode, data)
        cp = _ResponseCP(raw)
        rec = OperationRecorder(cp, Path("fixture-output"), "ADMISSION", scope=scope)
        result = rec.start(name="probe", opclass="managed_write", input_desc="fixture")
        self.assertIs(cp.result, raw)
        self.assertIs(cp.result.data, data)
        return result, raw, cp, rec

    def test_legacy_construction_and_strict_permission(self):
        old = StartedOperation("probe", "managed_write", "a1", True, False, "detail")
        self.assertTrue(old.can_execute)
        self.assertIs(getattr(old, "already_applied", None), False)
        keyword = StartedOperation(name="probe", opclass="managed_write", attempt="a1",
                                   ok=True, ambiguous=False, detail="detail")
        self.assertEqual(old, keyword)
        # After the missing-marker RED, these replacements cover direct constructors.
        for marker in (True, 0, 1, None, "false", [], {}):
            with self.subTest(marker=marker):
                self.assertFalse(replace(old, already_applied=marker).can_execute)
        for changed in ({"ok": False}, {"ambiguous": True}, {"attempt": None}, {"attempt": ""}):
            self.assertFalse(replace(old, **changed).can_execute)

    def test_missing_false_and_true_response_markers(self):
        for value in ("missing", False, True):
            with self.subTest(value=value):
                data = {"ok": True, "attempt": "a1"}
                if value != "missing":
                    data["already_applied"] = value
                result, raw, _cp, _rec = self.record(data)
                self.assertTrue(result.ok)
                self.assertEqual(result.attempt, "a1")
                self.assertIs(getattr(result, "already_applied", None), value is True)
                self.assertIs(result.can_execute, value is not True)
                self.assertEqual(raw.data, data)
                self.assertFalse(result.ambiguous)

    def test_malformed_marker_is_normalized_without_mutating_raw(self):
        for value in (0, 1, "false", None, [], {}):
            with self.subTest(value=value):
                data = {"ok": True, "attempt": "a1", "already_applied": value}
                result, raw, _cp, _rec = self.record(data)
                self.assertFalse(result.ok)
                self.assertFalse(result.can_execute)
                self.assertIs(result.already_applied, False)
                self.assertEqual(result.detail,
                    "operation_start_protocol_invalid: already_applied 必须是 bool")
                self.assertIs(raw.data["already_applied"], value)

    def test_structured_ambiguity_old_fallback_and_transport(self):
        for extra in ({"gate_id": "ambiguous_side_effect", "error": "同名动作未终结"},
                      {"ambiguous_side_effect": True}, {"error": "ambiguous_side_effect"}):
            with self.subTest(extra=extra):
                result, _raw, _cp, _rec = self.record(dict(ok=False, **extra), returncode=1)
                self.assertTrue(result.ambiguous)
                self.assertFalse(result.can_execute)
        for data, code in (({"ok": True, "attempt": "a1"}, 1),
                           ({"ok": 1, "attempt": "a1"}, 0),
                           ({"ok": True, "attempt": ""}, 0)):
            result, _raw, _cp, _rec = self.record(data, code)
            self.assertFalse(result.can_execute)
        result, _raw, _cp, _rec = self.record({"ok": True, "attempt": 7, "message": "m" * 400})
        self.assertEqual(result.attempt, "7")
        self.assertEqual(result.detail, "m" * 300)

    def test_occurrence_and_scope_preserve_exact_double_calls(self):
        _first, _raw, cp, rec = self.record({"ok": True, "attempt": "a1"}, scope="plan")
        rec.start(name="probe", opclass="managed_write", input_desc="fixture")
        self.assertEqual([call[1]["occurrence"] for call in cp.calls], [1, 3])
        self.assertEqual([call[1]["request"] for call in cp.calls], [
            make_request("ADMISSION", "op-plan-probe-start", occurrence=2),
            make_request("ADMISSION", "op-plan-probe-start", occurrence=4)])
        self.assertEqual(rec._counters, {"probe": 4})
        self.assertEqual(cp.calls[0][1]["name"], "probe")
        self.assertEqual(cp.calls[0][1]["opclass"], "managed_write")
        self.assertEqual(cp.calls[0][1]["input_desc"], "fixture")
        other, _raw, other_cp, _rec = self.record({"ok": True, "attempt": "a2"}, scope="review")
        self.assertTrue(other.can_execute)
        self.assertNotEqual(cp.calls[0][1]["request"], other_cp.calls[0][1]["request"])
```

- [x] **Step 2: 执行因果 RED。**

首先运行真实CP admission-only负控，不运行handler或模型；使用真实缺口的 `replay.can_execute` 断言，原始响应明确为True旧attempt。此诊断只在owned fixture中运行，生命周期结束清理，不补finish。

```bash
python -B - <<'PY'
from icode.control import ControlPlane
from icode.handshake import next_out_dir
from icode.operations import OperationRecorder
from tests._support import require_skill, temp_workspace
from unittest.mock import patch
settings = require_skill()
with temp_workspace() as root:
    cp = ControlPlane(settings)
    directory = next_out_dir(root)
    assert cp.create(directory, ticket_id="ADMISSION-RED", requirement="owned admission RED", birth="plan").data.get("ok") is True
    first = OperationRecorder(cp, directory, "ADMISSION-RED", scope="plan").start(
        name="probe", opclass="managed_write", input_desc="fixture")
    assert first.can_execute
    raw = []
    original = cp.operation_start
    def observed(*args, **kwargs):
        response = original(*args, **kwargs)
        raw.append(response)
        return response
    with patch.object(cp, "operation_start", side_effect=observed):
        replay = OperationRecorder(cp, directory, "ADMISSION-RED", scope="plan").start(
            name="probe", opclass="managed_write", input_desc="fixture")
    assert raw[0].data.get("already_applied") is True
    assert replay.attempt == first.attempt
    assert replay.can_execute is False, "old start receipt cannot grant execution"
PY
```

预期当前旧wrapper最后一条AssertionError/exit非零、实际CP成功且payload0；这不是unittest方法，因此不计方法/20轮数。若CP本身拒绝先诊断，不认作因果RED。再运行以下协议方法取得unittest断言RED；不以模型double导致的拒绝取代本真实许可断言。

```bash
python -B -m unittest tests.test_operation_admission.TestOperationAdmissionProtocol.test_missing_false_and_true_response_markers tests.test_operation_admission.TestOperationAdmissionProtocol.test_malformed_marker_is_normalized_without_mutating_raw tests.test_operation_admission.TestOperationAdmissionProtocol.test_structured_ambiguity_old_fallback_and_transport -v
```

实际期望至少 marker / structured gate_id 的断言 FAIL、0 ERROR/skip、非零exit；malformed 首条先检查 ok=False，故旧源在 getattr前断言失败。不要把未定义新字段的 replace TypeError 算 RED；先只运行上述三方法。保留原输出与源冻结摘要，不预报确切 failure 子项数。

- [x] **Step 3: 最小生产修改。**

`StartedOperation` 在 `detail` 后追加，property 保持原三条件：

```python
    already_applied: bool = False

    @property
    def can_execute(self) -> bool:
        """只有新 admission、有 attempt 且不歧义才允许副作用。"""
        return (self.ok and not self.ambiguous and bool(self.attempt)
                and self.already_applied is False)
```

`OperationRecorder.start` 原 CP 调用、两次计数完整不动，仅替换 `attempt = ...` 至返回块：

```python
        attempt = res.data.get("attempt")
        ambiguous = (
            bool(res.data.get("ambiguous_side_effect"))
            or res.data.get("gate_id") == "ambiguous_side_effect"
            or str(res.data.get("error", "")).find("ambiguous_side_effect") >= 0
        )
        ok = res.returncode == 0 and res.data.get("ok") is True
        detail = str(res.data.get("error") or res.data.get("message") or "")[:300]
        already_applied = res.data.get("already_applied", False)
        if type(already_applied) is not bool:
            ok = False
            already_applied = False
            detail = "operation_start_protocol_invalid: already_applied 必须是 bool"
        return StartedOperation(
            name=name, opclass=opclass,
            attempt=str(attempt) if attempt else None,
            ok=ok, ambiguous=ambiguous, detail=detail,
            already_applied=already_applied,
        )
```

- [x] **Step 4: 执行 GREEN 与作者/独立审。**

```bash
python -B -m unittest tests.test_operation_admission.TestOperationAdmissionProtocol -v
python -B -m unittest tests.test_loop tests.test_recovery -v
```

新5方法必须 0F/E/skip；旧方法数以实际 loader/summary记录，不能编造固定数量。完成 selfSPEC→selfQUALITY、fresh SPEC→不同 QUALITY 后冻结；不 commit，不开始下一Task直到该Task无未闭合重要问题。

### Task 2: 普通工具载荷前门、真实CP与进程重启

**状态**

- [x] 任务完成

**Dependencies:** Task 1
**Parallelizable:** No（共享新module、loop，真实CP/runtime串行）

- [x] **Step 1: 在新module追加下列完整fixture和七方法。**

本地 `admission_probe` handler 写 owned marker，真实 Registry.invoke 和 CP；无模型请求、shell、kernel sandbox。所有重放使用完全相同输入摘要和 scope，不换键。

```python
def _probe_input():
    safe = {"arg_keys": [], "args_sha256": hashlib.sha256(b"{}").hexdigest()}
    return json.dumps(safe, ensure_ascii=False)


def _make_loop(root, recorder, events, *, read_only=False):
    registry = ToolRegistry()

    def handler(ctx):
        if read_only:
            return ToolResult(True, "read-only fixture")
        marker = ctx.root / "payload-marker.txt"
        previous = marker.read_text(encoding="utf-8") if marker.exists() else ""
        marker.write_text(previous + "x", encoding="utf-8")
        return ToolResult(True, "done")

    registry.register(Tool("admission_probe", "owned test marker",
        {"type": "object", "properties": {}, "required": []}, handler,
        opclass="read_only" if read_only else "managed_write"))
    return AgentLoop(backend=FakeBackend([]), registry=registry,
        guard=Guard(Scope(workspace_root=root)), ctx=ToolContext(root=root),
        approver=DenyAllApprover(), operations=recorder,
        budget=BudgetTracker(), config=LoopConfig(),
        on_event=lambda kind, payload: events.append((kind, payload)))


class TestOperationAdmissionRealCP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.settings = require_skill()
        except unittest.SkipTest as exc:
            # These are explicitly required admission tests, not optional diagnostics.
            raise RuntimeError("Required admission CP fixture unavailable") from exc

    def ticket(self):
        root = self.enterContext(temp_workspace()).resolve()
        cp = ControlPlane(self.settings)
        directory = next_out_dir(root).resolve()
        created = cp.create(directory, ticket_id="ADMISSION", requirement="owned replay", birth="plan")
        self.assertIs(created.data.get("ok"), True)
        return root, cp, directory

    def recorder(self, cp, directory):
        return OperationRecorder(cp, directory, "ADMISSION", scope="plan")

    def marker(self, root):
        path = root / "payload-marker.txt"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def open_attempts(self, cp, directory):
        trace = cp.trace(directory)
        self.assertEqual(trace.returncode, 0)
        self.assertIs(trace.data.get("ok"), True)
        return trace.data["open_operations"]

    def seed(self, cp, directory):
        recorder = self.recorder(cp, directory)
        started = recorder.start(name="tool:admission_probe", opclass="managed_write",
                                 input_desc=_probe_input())
        self.assertTrue(started.can_execute, started.detail)
        return recorder, started

    def test_actual_first_raw_open_replay_and_structured_next_occurrence(self):
        _root, cp, directory = self.ticket()
        raw = []
        original = cp.operation_start

        def observed(*args, **kwargs):
            response = original(*args, **kwargs)
            raw.append(response)
            return response

        with patch.object(cp, "operation_start", side_effect=observed):
            original_recorder, first = self.seed(cp, directory)
            replay_recorder = self.recorder(cp, directory)
            replay = replay_recorder.start(name="tool:admission_probe", opclass="managed_write",
                                           input_desc=_probe_input())
            ambiguous = replay_recorder.start(name="tool:admission_probe", opclass="managed_write",
                                              input_desc=_probe_input())
        self.assertNotIn("already_applied", raw[0].data)
        self.assertIs(raw[1].data.get("already_applied"), True)
        self.assertTrue(replay.ok)
        self.assertTrue(replay.already_applied)
        self.assertFalse(replay.can_execute)
        self.assertEqual(replay.attempt, first.attempt)
        self.assertEqual(raw[2].data.get("gate_id"), "ambiguous_side_effect")
        self.assertNotEqual(raw[2].returncode, 0)
        self.assertTrue(ambiguous.ambiguous)
        self.assertFalse(ambiguous.can_execute)
        self.assertIn(first.attempt, self.open_attempts(cp, directory))
        self.assertEqual(original_recorder._counters, {"tool:admission_probe": 2})
        self.assertEqual(replay_recorder._counters, {"tool:admission_probe": 4})

    def test_open_replay_refuses_loop_with_zero_or_one_prior_effect(self):
        for before in ("", "x"):
            with self.subTest(before=before):
                root, cp, directory = self.ticket()
                _original, first = self.seed(cp, directory)
                if before:
                    (root / "payload-marker.txt").write_text(before, encoding="utf-8")
                fresh = self.recorder(cp, directory)
                events = []
                loop = _make_loop(root, fresh, events)
                with patch.object(fresh, "finish", wraps=fresh.finish) as finish, \
                        patch.object(loop.registry, "invoke", wraps=loop.registry.invoke) as invoke:
                    result = loop._invoke("admission_probe", {})
                self.assertFalse(result.approved)
                self.assertFalse(result.result.ok)
                self.assertIn("此前动作的回执不能用于再次执行", result.result.content)
                self.assertIn("此前动作的回执不能用于再次执行", result.note)
                self.assertEqual(self.marker(root), before)
                self.assertIn(first.attempt, self.open_attempts(cp, directory))
                invoke.assert_not_called()
                finish.assert_not_called()
                self.assertNotIn("tool_start", [kind for kind, _payload in events])

    def test_completed_replay_refuses_and_new_occurrence_remains_usable(self):
        root, cp, directory = self.ticket()
        original, first = self.seed(cp, directory)
        (root / "payload-marker.txt").write_text("x", encoding="utf-8")
        self.assertTrue(original.finish(first.attempt, outcome="success", evidence="observed",
                                       check_ref="owned marker"))
        fresh = self.recorder(cp, directory)
        loop = _make_loop(root, fresh, [])
        with patch.object(fresh, "finish", wraps=fresh.finish) as finish:
            replay = loop._invoke("admission_probe", {})
            self.assertFalse(replay.approved)
            self.assertEqual(self.marker(root), "x")
            finish.assert_not_called()
            new = loop._invoke("admission_probe", {})
        self.assertTrue(new.approved)
        self.assertTrue(new.result.ok)
        self.assertEqual(self.marker(root), "xx")
        self.assertEqual(finish.call_count, 1)
        self.assertNotEqual(finish.call_args.args[0], first.attempt)
        self.assertFalse(self.open_attempts(cp, directory))

    def test_old_duck_success_and_read_only_do_not_require_new_attribute(self):
        for read_only in (False, True):
            with self.subTest(read_only=read_only):
                root = self.enterContext(temp_workspace()).resolve()
                duck = SimpleNamespace(start=Mock(return_value=SimpleNamespace(
                    can_execute=True, attempt="duck-a1", detail="")), finish=Mock(return_value=True))
                result = _make_loop(root, duck, [], read_only=read_only)._invoke("admission_probe", {})
                self.assertTrue(result.approved)
                self.assertTrue(result.result.ok)
                self.assertEqual(self.marker(root), "" if read_only else "x")
                self.assertEqual(duck.start.call_count, 0 if read_only else 1)
                self.assertEqual(duck.finish.call_count, 0 if read_only else 1)

    def test_start_exception_invoke_exception_and_finish_false_do_not_fake_closure(self):
        for failure in ("start", "malformed", "invoke", "handler", "finish"):
            with self.subTest(failure=failure):
                root, cp, directory = self.ticket()
                recorder = self.recorder(cp, directory)
                loop = _make_loop(root, recorder, [])
                with patch.object(recorder, "finish", wraps=recorder.finish) as finish:
                    if failure == "start":
                        with patch.object(cp, "operation_start", side_effect=OSError("start unavailable")):
                            with self.assertRaises(OSError):
                                loop._invoke("admission_probe", {})
                        self.assertFalse(self.open_attempts(cp, directory))
                        self.assertEqual(self.marker(root), "")
                        finish.assert_not_called()
                    elif failure == "malformed":
                        raw = ControlResult((), 0, {"ok": True, "attempt": "bad",
                                                   "already_applied": 1})
                        with patch.object(cp, "operation_start", return_value=raw), \
                                patch.object(loop.registry, "invoke", wraps=loop.registry.invoke) as invoke:
                            result = loop._invoke("admission_probe", {})
                        self.assertFalse(result.approved)
                        self.assertFalse(result.result.ok)
                        self.assertEqual(self.marker(root), "")
                        self.assertIs(raw.data["already_applied"], 1)
                        self.assertFalse(self.open_attempts(cp, directory))
                        invoke.assert_not_called()
                        finish.assert_not_called()
                    elif failure == "invoke":
                        # Exception in the registry invocation boundary, not a normalized handler failure.
                        with patch.object(loop.registry, "invoke", side_effect=OSError("unknown invocation")):
                            with self.assertRaises(OSError):
                                loop._invoke("admission_probe", {})
                        self.assertTrue(self.open_attempts(cp, directory))
                        self.assertEqual(self.marker(root), "")
                        finish.assert_not_called()
                    elif failure == "handler":
                        with patch.object(loop.registry.get("admission_probe"), "handler",
                                          side_effect=OSError("normalized handler failure")):
                            result = loop._invoke("admission_probe", {})
                        self.assertFalse(result.result.ok)
                        self.assertEqual(result.result.meta["error"], "tool_exception")
                        self.assertEqual(self.marker(root), "")
                        self.assertFalse(self.open_attempts(cp, directory))
                        self.assertEqual(finish.call_count, 1)
                        self.assertEqual(finish.call_args.kwargs["failure"], "deterministic_failure")
                    else:
                        with patch.object(cp, "operation_finish", return_value=ControlResult((), 1, {"ok": False})):
                            result = loop._invoke("admission_probe", {})
                        self.assertTrue(result.result.meta["operation_finish_failed"])
                        self.assertEqual(self.marker(root), "x")
                        self.assertTrue(self.open_attempts(cp, directory))
                        self.assertEqual(finish.call_count, 1)

    def test_real_child_restart_reuses_durable_cp_but_never_reexecutes_payload(self):
        root, cp, directory = self.ticket()
        child = r'''
import json, os, sys
from pathlib import Path
from icode.config import Settings
from icode.control import ControlPlane
from icode.operations import OperationRecorder
from tests.test_operation_admission import _make_loop, _probe_input
skill, root, directory = map(Path, sys.argv[1:4])
cp = ControlPlane(Settings(skill_root=skill, python=sys.executable))
recorder = OperationRecorder(cp, directory, "ADMISSION", scope="plan")
if sys.argv[4] == "seed":
    result = recorder.start(name="tool:admission_probe", opclass="managed_write", input_desc=_probe_input())
    if not result.can_execute:
        raise AssertionError(result.detail)
    (root / "payload-marker.txt").write_text("x", encoding="utf-8")
    print(json.dumps({"pid": os.getpid(), "attempt": result.attempt}))
else:
    finished = []
    original_finish = recorder.finish
    def observed_finish(*args, **kwargs):
        finished.append(args)
        return original_finish(*args, **kwargs)
    recorder.finish = observed_finish
    events = []
    invocation = _make_loop(root, recorder, events)._invoke("admission_probe", {})
    trace = cp.trace(directory)
    if trace.returncode != 0 or trace.data.get("ok") is not True:
        raise AssertionError("trace unavailable")
    print(json.dumps({"pid": os.getpid(), "approved": invocation.approved,
        "ok": invocation.result.ok, "finish_calls": len(finished),
        "tool_start": sum(kind == "tool_start" for kind, _ in events),
        "content": invocation.result.content, "open": list(trace.data["open_operations"])}))
'''
        outputs = []
        for mode in ("seed", "replay"):
            proc = subprocess.run([sys.executable, "-B", "-c", child,
                str(self.settings.skill_root), str(root), str(directory), mode],
                cwd=str(Path(__file__).resolve().parents[1]), capture_output=True,
                text=True, encoding="utf-8", errors="replace", timeout=30, shell=False)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            outputs.append(json.loads(proc.stdout))
            self.assertNotEqual(outputs[-1]["pid"], os.getpid())
        self.assertEqual(self.marker(root), "x")
        self.assertFalse(outputs[1]["approved"])
        self.assertFalse(outputs[1]["ok"])
        self.assertEqual(outputs[1]["finish_calls"], 0)
        self.assertEqual(outputs[1]["tool_start"], 0)
        self.assertIn("此前动作的回执不能用于再次执行", outputs[1]["content"])
        self.assertIn(outputs[0]["attempt"], outputs[1]["open"])
        self.assertIn(outputs[0]["attempt"], self.open_attempts(cp, directory))

    def test_converged_read_only_observation_preserves_open_receipt_and_effect(self):
        root, cp, directory = self.ticket()
        _original, first = self.seed(cp, directory)
        (root / "payload-marker.txt").write_text("x", encoding="utf-8")
        self.assertFalse(_make_loop(root, self.recorder(cp, directory), [])._invoke(
            "admission_probe", {}).approved)
        event_bytes = (directory / ".ico_events.jsonl").read_bytes()
        started = time.monotonic()
        for _ in range(3):
            threading.Event().wait(0.05)
            self.assertIn(first.attempt, self.open_attempts(cp, directory))
            self.assertEqual(self.marker(root), "x")
            self.assertEqual((directory / ".ico_events.jsonl").read_bytes(), event_bytes)
        self.assertGreaterEqual(time.monotonic() - started, 0.15)
```

临时 fixture 由 `enterContext(temp_workspace())` 结束时清理，未知 open 不补 finish 取绿。真实 child seed 是已明确写一次 marker 的 owned 动作、不finish；下一独立解释器复用同 durable CP 负控。两次subprocess是不同运行生命期，不要求 pid不复用；不模拟 `os.name`，不启动长驻任务。协议类不 require_skill，真实类 require_skill，但本新required类只把资源缺失的SkipTest转为明示RuntimeError；不改变共享helper/旧可选测试。类setup产生0执行+1ERROR，因此main.wasSuccessful不能green，Task4实际生命周期guard核对该路径；不能仅靠required方法ID拦class holder。

- [x] **Step 2: 先运行缺中文回执说明的 RED，记录实际 failures。**

```bash
python -B -m unittest tests.test_operation_admission.TestOperationAdmissionRealCP.test_open_replay_refuses_loop_with_zero_or_one_prior_effect -v
```

Task1 已修 can_execute，期望真正调用门已拒绝、但旧文案断言 FAIL，0E/skip。载荷风险因果RED已由Task1真实CP旧许可断言证明；Task2不虚称文案FAIL等于新增payload。本方法GREEN仍必须actual invoke/finish0与marker0/1 delta不增长。若是CP错误或fixture路径问题，先修fixture再取因果RED，不改CP授许可。

- [x] **Step 3: 最小修改 loop 的早拒绝块。**

仅在原 `if not started.can_execute:` 内加入分类变量并替换 content/note，原 metadata/event/return保持：

```python
                replayed = getattr(started, "already_applied", False) is True
                prefix = (
                    "此前动作的回执不能用于再次执行："
                    if replayed else
                    "副作用回执不明确，已停止执行并等待人工核对（禁止盲目重放）："
                )
                inv.result = ToolResult(
                    False, prefix + (started.detail or "ambiguous_side_effect"),
                    {"error": "ambiguous_side_effect"}, opclass=tool.opclass,
                )
                inv.note = (
                    "此前动作的回执不能用于再次执行" if replayed
                    else "副作用歧义，拒绝重放"
                )
                self.on_event("operation_ambiguous", {"tool": call_name, "detail": started.detail})
                return inv
```

旧duck成功分支不读取marker；ToolRegistry已把普通handler Exception归一为 deterministic ToolResult，不能把这类失败泛称未知。本新增异常向量明确是 registry.invoke 边界抛错；只测试保留原行为，不新增异常策略。

- [x] **Step 4: 串行 GREEN 与关联回归，双审冻结。**

```bash
python -B -m unittest tests.test_operation_admission -v
python -B -m unittest tests.test_loop tests.test_recovery tests.test_cli_resume_sandbox -v
```

新module恰好12方法（5协议+7真实offline），0F/E/skip；完成作者/独立审后记录actualrawmarker/attempt/handler/finish/event/open和childsummary，原失败输出保留，不写业务rollback或原生通过。不 commit。

### Task 3: 工程早门与旧完成回执兼容

**状态**

- [x] 任务完成

**Dependencies:** Task 2
**Parallelizable:** No（共享runner和真实CP，旧fixture与门合同需串行）

- [x] **Step 1: 在现有 TestContractEngineering 追加两完整方法。**

复用 `gate_fixture()`，不继承或import旧Case到新module。原 `_contract_engineering_gate` 先运行一次真正start，再在 `execute_verification_plan` seam抛异常留下open；第二次 fresh同键早门必须拒绝。第一次host seam不是payload观察，第二次 `_controlled_dispatch` 必须0调用。

```python
    def test_open_operation_replay_refuses_before_host_payload_without_closing(self):
        for before in (b"", b"x"):
            with self.subTest(before=before):
                root, cp, directory, _outcome, report, args = self.gate_fixture()
                marker = root / "engineering-marker.txt"
                if before:
                    marker.write_bytes(before)
                with patch.object(runner, "execute_verification_plan", side_effect=OSError("fixture stop")), \
                        patch("icode.tools.builtin._controlled_dispatch") as first_dispatch:
                    with self.assertRaises(OSError):
                        runner._contract_engineering_gate(**args)
                first_dispatch.assert_not_called()
                trace = cp.trace(directory)
                self.assertEqual(trace.returncode, 0)
                self.assertIs(trace.data.get("ok"), True)
                opened = trace.data["open_operations"]
                self.assertEqual(len(opened), 1)
                args["operations"] = OperationRecorder(cp, directory, "ENG-CONTRACT", scope="code")
                fresh = args["operations"]
                with patch.object(fresh, "finish", wraps=fresh.finish) as finish, \
                        patch.object(runner, "execute_verification_plan") as host, \
                        patch("icode.tools.builtin._controlled_dispatch") as dispatch:
                    self.assertFalse(runner._contract_engineering_gate(**args))
                self.assertEqual(report.error, "engineering_operation_replay_refused")
                finish.assert_not_called()
                host.assert_not_called()
                dispatch.assert_not_called()
                self.assertEqual(marker.read_bytes() if marker.exists() else b"", before)
                self.assertEqual(cp.trace(directory).data["open_operations"], opened)
                self.assertEqual(self.event_rows(directory, "operation_finished"), [])

    def test_early_admission_failure_and_exact_replay_keep_old_error_categories(self):
        from icode.operations import StartedOperation
        for marker, ok, expected in ((False, False, "engineering_operation_start_unconfirmed"),
                                     (True, True, "engineering_operation_replay_refused"),
                                     (1, True, "engineering_operation_start_unconfirmed")):
            with self.subTest(marker=marker, ok=ok):
                _root, _cp, directory, _outcome, report, args = self.gate_fixture()
                started = StartedOperation("fixture", "managed_write", "a1", ok, False,
                                           "detail", marker)
                operations = SimpleNamespace(start=Mock(return_value=started), finish=Mock())
                args["operations"] = operations
                with patch.object(runner, "execute_verification_plan") as host, \
                        patch("icode.tools.builtin._controlled_dispatch") as dispatch:
                    self.assertFalse(runner._contract_engineering_gate(**args))
                self.assertEqual(report.error, expected)
                operations.finish.assert_not_called()
                host.assert_not_called()
                dispatch.assert_not_called()
                self.assertEqual(self.event_rows(directory, "operation_started"), [])
```

- [x] **Step 2: 运行真实open replay与旧completed replay的 RED。**

```bash
python -B -m unittest tests.test_contract_engineering.TestContractEngineering.test_open_operation_replay_refuses_before_host_payload_without_closing tests.test_contract_engineering.TestContractEngineering.test_completed_operation_request_replay_cannot_rerun_engineering_payload -v
```

Task1 新 can_execute 已阻止载荷，旧 early error分类会错误返回 start_unconfirmed，期望两个方法合同断言 FAIL、0E/skip。旧completed方法已有try EvidenceError兼容，必须保留原 dispatch count=1和旧 replay_refused，禁止改测试接受新错误。

- [x] **Step 3: runner 早门仅改 report.error 条件。**

```python
    if not started.can_execute:
        report.error = (
            "engineering_operation_replay_refused"
            if getattr(started, "already_applied", False) is True
            else "engineering_operation_start_unconfirmed"
        )
        report.add("工程动作开始确认", False)
        return False
```

后续 `cp.trace/open_action` 原身份重核原样保留；无需给旧success duck增加属性。真实CP open和completed事实不从报告推定。

- [x] **Step 4: GREEN / unknown/publicresume/旧兼容回归，双审冻结。**

```bash
python -B -m unittest tests.test_contract_engineering -v
python -B -m unittest tests.test_operation_admission tests.test_loop tests.test_recovery tests.test_cli_resume_sandbox -v
```

工程class原39+新2=41方法；本机POSIX无新增skip，既有平台差异按原选择说明。必须实跑现有 `test_resume_checks_actual_attempt_unknown_and_completed_actions_before_model`、`test_exception_after_confirmed_start_retains_unknown_action`、`test_save_record_and_operation_ack_failures_retain_checkpoint_without_quality` 与旧completed方法；公共resume在model/host之前拒绝，不能外推新普通resume获得许可。完成作者/独立审，不 commit。

### Task 4: 精准 CI 选择、required防掩盖与root整片发布

**状态**

- [x] 任务完成

**Dependencies:** Task 3
**Parallelizable:** No（选择数依赖最终methods，CI运行串行）

- [x] **Step 1: tests/test_run_workspace_ci.py 追加以下完整守护。**

```python
    def test_operation_admission_methods_selected_once_required_and_never_static_skipped(self):
        definitions = (
            ("tests.test_operation_admission", "TestOperationAdmissionProtocol", 5),
            ("tests.test_operation_admission", "TestOperationAdmissionRealCP", 7),
        )
        expected = set()
        classes = {}
        for module_name, class_name, count in definitions:
            test_class = getattr(importlib.import_module(module_name), class_name)
            methods = unittest.defaultTestLoader.getTestCaseNames(test_class)
            self.assertEqual(len(methods), count)
            self.assertFalse(getattr(test_class, "__unittest_skip__", False))
            for method in methods:
                test_id = module_name + "." + class_name + "." + method
                expected.add(test_id)
                classes[test_id] = test_class
                self.assertFalse(getattr(getattr(test_class, method), "__unittest_skip__", False))
        for method in (
            "test_open_operation_replay_refuses_before_host_payload_without_closing",
            "test_early_admission_failure_and_exact_replay_keep_old_error_categories",
        ):
            test_id = "tests.test_contract_engineering.TestContractEngineering." + method
            expected.add(test_id)
            classes[test_id] = importlib.import_module(
                "tests.test_contract_engineering").TestContractEngineering
        self.assertEqual(len(expected), 14)
        self.assertTrue(hasattr(run_workspace_ci, "OPERATION_ADMISSION_TESTS"))
        declared = run_workspace_ci.OPERATION_ADMISSION_TESTS
        self.assertEqual(set(declared), expected)
        self.assertEqual(len(declared), len(expected))

        def cases(suite):
            for test in suite:
                if isinstance(test, unittest.TestSuite):
                    yield from cases(test)
                else:
                    yield test

        selected = [test for entry in run_workspace_ci.DEFAULT_MODULES
            for test in cases(unittest.defaultTestLoader.loadTestsFromName(entry))
            if test.id() in expected or test.id().startswith("tests.test_operation_admission.")]
        self.assertEqual({test.id() for test in selected}, expected)
        self.assertEqual(len(selected), len(expected))
        for test_id in sorted(expected):
            with self.subTest(test_id=test_id):
                loaded = list(cases(unittest.defaultTestLoader.loadTestsFromName(test_id)))
                self.assertEqual(len(loaded), 1)
                self.assertIs(type(loaded[0]), classes[test_id])
                self.assertEqual(loaded[0].id(), test_id)
                self.assertFalse(getattr(getattr(loaded[0], loaded[0]._testMethodName), "__unittest_skip__", False))

                class SkippedRequiredTest(unittest.TestCase):
                    def id(self):
                        return test_id

                    def runTest(self):
                        self.skipTest("simulated missing admission dependency")

                with patch.object(run_workspace_ci.unittest.defaultTestLoader,
                    "loadTestsFromNames", return_value=unittest.TestSuite([SkippedRequiredTest()])), \
                        redirect_stderr(io.StringIO()):
                    self.assertEqual(run_workspace_ci.main((test_id,)), 1)

        # Run the actual class setup lifecycle: missing required skill becomes ERROR,
        # not a setUpClass(...) skip holder that method-ID intersection would miss.
        actual = []

        class ObservingRunner:
            def run(self, suite):
                result = unittest.TestResult()
                suite.run(result)
                actual.append(result)
                return result

        selected_id = (
            "tests.test_operation_admission.TestOperationAdmissionRealCP."
            "test_actual_first_raw_open_replay_and_structured_next_occurrence"
        )
        with patch("tests.test_operation_admission.require_skill",
                   side_effect=unittest.SkipTest("simulated required CP absent")), \
                patch.object(run_workspace_ci.unittest, "TextTestRunner", return_value=ObservingRunner()):
            self.assertEqual(run_workspace_ci.main((selected_id,)), 1)
        self.assertEqual(len(actual), 1)
        self.assertEqual(actual[0].testsRun, 0)
        self.assertEqual(len(actual[0].errors), 1)
        self.assertEqual(actual[0].failures, [])
        self.assertEqual(actual[0].skipped, [])
        self.assertIn("Required admission CP fixture unavailable", actual[0].errors[0][1])

        # Existing engineering class keeps its optional require_skill/SkipTest behavior.
        # Only a selected new required method promotes its exact fixture holder to failure.
        engineering_ids = (
            "tests.test_contract_engineering.TestContractEngineering."
            "test_open_operation_replay_refuses_before_host_payload_without_closing",
            "tests.test_contract_engineering.TestContractEngineering."
            "test_early_admission_failure_and_exact_replay_keep_old_error_categories",
        )
        holder_id = "setUpClass (tests.test_contract_engineering.TestContractEngineering)"
        for selected_id in engineering_ids:
            with self.subTest(required_engineering=selected_id):
                actual.clear()
                with patch("tests.test_contract_engineering.require_skill",
                           side_effect=unittest.SkipTest("simulated engineering CP absent")), \
                        patch.object(run_workspace_ci.unittest, "TextTestRunner", return_value=ObservingRunner()), \
                        redirect_stderr(io.StringIO()):
                    self.assertEqual(run_workspace_ci.main((selected_id,)), 1)
                self.assertEqual(len(actual), 1)
                self.assertEqual(actual[0].testsRun, 0)
                self.assertEqual(actual[0].errors, [])
                self.assertEqual(actual[0].failures, [])
                self.assertEqual(len(actual[0].skipped), 1)
                self.assertEqual(actual[0].skipped[0][0].id(), holder_id)
                self.assertTrue(actual[0].wasSuccessful())

        # Same real holder, but no selected new required method: preserve original optional semantics.
        actual.clear()
        optional_id = (
            "tests.test_contract_engineering.TestContractEngineering."
            "test_policy_code_missing_plan_refuses_before_control_write_and_model"
        )
        self.assertNotIn(optional_id, run_workspace_ci.OPERATION_ADMISSION_TESTS)
        self.assertNotIn(optional_id, run_workspace_ci.POSIX_R3_TESTS)
        with patch("tests.test_contract_engineering.require_skill",
                   side_effect=unittest.SkipTest("simulated optional engineering CP absent")), \
                patch.object(run_workspace_ci.unittest, "TextTestRunner", return_value=ObservingRunner()), \
                redirect_stderr(io.StringIO()):
            self.assertEqual(run_workspace_ci.main((optional_id,)), 0)
        self.assertEqual(len(actual), 1)
        self.assertEqual(actual[0].testsRun, 0)
        self.assertEqual(actual[0].errors, [])
        self.assertEqual(actual[0].failures, [])
        self.assertEqual(len(actual[0].skipped), 1)
        self.assertEqual(actual[0].skipped[0][0].id(), holder_id)
        self.assertTrue(actual[0].wasSuccessful())
```

- [x] **Step 2: 执行 RED。**

第一版测试先 `self.assertTrue(hasattr(run_workspace_ci, "OPERATION_ADMISSION_TESTS"))`，置于访问 declared之前，以缺选择合同 assertion FAIL代替AttributeError；完成实现后仍可保留此断言。

```bash
python -B -m unittest tests.test_run_workspace_ci.TestWorkspaceCiCoverage.test_operation_admission_methods_selected_once_required_and_never_static_skipped -v
```

预期1方法FAIL/0ERROR/skip，不运行整个DEFAULT取得RED。

- [x] **Step 3: loader 追加精准元组、DEFAULT一次及skip交集。**

在 `SESSION_GIT_PROJECTION_TESTS` 前增加下列完整元组；不要同时选择新module/class，否则重复收集。两新工程方法不同时加入原CONTRACT_ENGINEERING_TESTS。

```python
OPERATION_ADMISSION_TESTS = (
    "tests.test_operation_admission.TestOperationAdmissionProtocol.test_legacy_construction_and_strict_permission",
    "tests.test_operation_admission.TestOperationAdmissionProtocol.test_missing_false_and_true_response_markers",
    "tests.test_operation_admission.TestOperationAdmissionProtocol.test_malformed_marker_is_normalized_without_mutating_raw",
    "tests.test_operation_admission.TestOperationAdmissionProtocol.test_structured_ambiguity_old_fallback_and_transport",
    "tests.test_operation_admission.TestOperationAdmissionProtocol.test_occurrence_and_scope_preserve_exact_double_calls",
    "tests.test_operation_admission.TestOperationAdmissionRealCP.test_actual_first_raw_open_replay_and_structured_next_occurrence",
    "tests.test_operation_admission.TestOperationAdmissionRealCP.test_open_replay_refuses_loop_with_zero_or_one_prior_effect",
    "tests.test_operation_admission.TestOperationAdmissionRealCP.test_completed_replay_refuses_and_new_occurrence_remains_usable",
    "tests.test_operation_admission.TestOperationAdmissionRealCP.test_old_duck_success_and_read_only_do_not_require_new_attribute",
    "tests.test_operation_admission.TestOperationAdmissionRealCP.test_start_exception_invoke_exception_and_finish_false_do_not_fake_closure",
    "tests.test_operation_admission.TestOperationAdmissionRealCP.test_real_child_restart_reuses_durable_cp_but_never_reexecutes_payload",
    "tests.test_operation_admission.TestOperationAdmissionRealCP.test_converged_read_only_observation_preserves_open_receipt_and_effect",
    "tests.test_contract_engineering.TestContractEngineering.test_open_operation_replay_refuses_before_host_payload_without_closing",
    "tests.test_contract_engineering.TestContractEngineering.test_early_admission_failure_and_exact_replay_keep_old_error_categories",
)
```

`DEFAULT_MODULES` 在 `*CONTRACT_ENGINEERING_TESTS,` 后追加 `*OPERATION_ADMISSION_TESTS,`；`main`原 `required_test_ids` 至 `skipped_required_tests` 块完整替换为下列代码，后面的拒绝打印/return结构不变：

```python
    required_test_ids = frozenset((*POSIX_R3_TESTS, *OPERATION_ADMISSION_TESTS)).intersection(modules)
    selected_admission_ids = frozenset(OPERATION_ADMISSION_TESTS).intersection(modules)
    selected_admission_classes = {
        test_id.rsplit(".", 1)[0] for test_id in selected_admission_ids
    }
    selected_admission_modules = {
        class_id.rsplit(".", 1)[0] for class_id in selected_admission_classes
    }
    selected_fixture_ids = {
        f"{fixture} ({class_id})"
        for class_id in selected_admission_classes
        for fixture in ("setUpClass", "tearDownClass")
    } | {
        f"{fixture} ({module_id})"
        for module_id in selected_admission_modules
        for fixture in ("setUpModule", "tearDownModule")
    }
    skipped_required_tests = sorted({
        test.id()
        for test, _reason in result.skipped
        if test.id() in required_test_ids or test.id() in selected_fixture_ids
    })
```

原skip拒绝打印改为准确通用“Required workspace regression test was skipped: ”；作者实际检索现有CIguard没有该打印的精确断言，不改return、argv或平台分支。不要把optional/既有平台skip全部升格成required，也不把本新方法加入CROSS_PLATFORM_R3_TESTS（会改旧50方法合同并重复选择）。新版required覆盖14新向量但只有本次精确选中的方法IDs，原POSIX20保持。fixture集合仅从实选的新required方法派生，匹配带空格和括号的确切 `setUpClass (module.Class)` / `tearDownClass (module.Class)` / `setUpModule (module)` / `tearDownModule (module)`；不凭contains、异常文案或任意0methods拒绝，旧optional-only选择同一class holder仍原main0。新RealCP类缺skill仍RuntimeError，而现有工程class/shared helper完全不改。上述ObservingRunner只替代结果打印器，真实loader/suite/fixture与真实TestResult运行；没有预制Mock suite/result。分别实选两个new工程ID的0tests/1holderSkip/0E/F/wasSuccessful True却main1，与optional同holder/main0对照，不冒称默认TextTestRunner格式或CP运行。

- [x] **Step 4: GREEN并双审冻结。**

```bash
python -B -m unittest tests.test_run_workspace_ci -v
python -B scripts/run_workspace_ci.py tests.test_operation_admission.TestOperationAdmissionProtocol.test_missing_false_and_true_response_markers tests.test_contract_engineering.TestContractEngineering.test_open_operation_replay_refuses_before_host_payload_without_closing
```

guard原24+新1=25，精确脚本2方法均0F/E/skip/exit0；完整DEFAULT留root最终一轮。若已有断言精确依赖旧打印，唯一必要修复只换该断言，并重新RED/GREEN/冻结；七源scope不扩大。

执行中必要关联修订（2026-10-09 07:35 UTC，root授权）：现有同文件 `test_contract_engineering_selection_exists_once_without_native_readiness_claim` 原断言CONTRACT32与POSIX7并集等于工程class全部39方法；Task3新增后class实际41，旧断言必然漏两个新ID。root实读355–369确认真实缺口，准许在此原方法仅把equality并集增加 `OPERATION_ADMISSION_TESTS` 中精确前缀 `tests.test_contract_engineering.TestContractEngineering.` 的两个ID；保持旧两组不交断言、32/7选择和count循环不变，不把新2加入旧tuple、不减expected或放宽比较。作者先用此旧方法取真实缺2-ID assertion RED，最终25方法GREEN覆盖；不加方法/文件，七源及15新增/14required数量保持。此修订将由Task4及全局独立SPEC/QUALITY另核，不能冒称原静态计划已检出。

- [x] **Step 5: 全局fresh SPEC→不同QUALITY；root实读全部七源diff与上下游。**

确认作者 selfSPEC/selfQUALITY及每Task独立审，源SHA、方法12/工程41/guard25/选择14实际一致。review不能仅认可计划；对直接构造strictbool、raw/normalized、两个早门、旧duck、实际child、unknown/publicresume、两次occurrence逐条核。任何生产或测试源改动重新冻结并补相关门，旧冻结测试不挪信用。

- [x] **Step 6: root 定点与关联单轮。**

```bash
python -B -m unittest tests.test_operation_admission tests.test_contract_engineering tests.test_run_workspace_ci tests.test_loop tests.test_recovery tests.test_cli_resume_sandbox -v
```

实际total从loader和summary记录；不预填旧module计数。新12+工程新增2+guard新增1必须实际执行，无新增skip，失败停止定位不回写通过。

- [x] **Step 7: root串行20轮关键合同，DEFAULT只跑一次。**

每轮完整新12+两个新工程+旧completed+新CIguard=16方法，20轮累计320 executions；不是320不同方法。原helper不可偷加测试/吞stderr/把skip算成功。下列完整父进程脚本只编排真实子测试、检查实际summary与exit，shell=False无文件写，不是模拟测试结果。

```python
import re
import subprocess
import sys
import time
from scripts.run_workspace_ci import OPERATION_ADMISSION_TESTS
tests = (*OPERATION_ADMISSION_TESTS,
    "tests.test_contract_engineering.TestContractEngineering.test_completed_operation_request_replay_cannot_rerun_engineering_payload",
    "tests.test_run_workspace_ci.TestWorkspaceCiCoverage.test_operation_admission_methods_selected_once_required_and_never_static_skipped")
assert len(tests) == len(set(tests)) == 16
for round_number in range(1, 21):
    started = time.monotonic()
    result = subprocess.run([sys.executable, "-B", "-m", "unittest", *tests, "-v"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", shell=False)
    # unittest.TextTestRunner's actual default result stream is stderr.
    summary = result.stderr
    print(f"round={round_number} rc={result.returncode} wall={time.monotonic()-started:.3f}")
    print(summary)
    print(result.stdout)
    if (result.returncode != 0
            or re.search(r"^Ran 16 tests in [^\r\n]+\r?$", summary, re.MULTILINE) is None
            or re.search(r"(?:\A|\n)OK\r?\n?\Z", summary) is None):
        raise SystemExit(1)
```

```bash
python -B scripts/run_workspace_ci.py
```

本机POSIX DEFAULT预计595+14=609，不是610；guard新方法不被整module选择，DEFAULT新增12core+2工程。实际总数若与预计不同先核loader，不改预期数压绿。DEFAULT本机0F/E/skip/exit0；线上Windows/Python差异记录真实失败而非改源skip。
20轮父脚本只解析真实unittest默认stderr结果流的终态：returncode0、精确Ran16行和结果流最后裸行OK；stdout独立完整打印，不能由其正文提供假OK或扰乱真实终态。`OK (skipped=N)` / FAILED / ERROR不能通过。不得查任意substring `skipped`，因为合法guard方法本名含 `never_static_skipped`；保留原方法名和选择，不靠改名避开解析错误。

- [x] **Step 8: 新七源freeze原full唯一一次、j1和非测试守卫。**

```bash
python -B scripts/preflight.py
python -B -m compileall -q -j 1 src scripts tests
python -B scripts/check_governance.py
python -B scripts/check_site.py
python -B scripts/check_agent_landscape.py --today 2026-10-09
git diff --check
```

root必须按既有方式记录 `preflight.guard_tests` 原子调用 `[sys.executable, '-m', 'unittest']` 恰好1次，保留原cwd/capture/text/UTF8/errors/shell及返回对象，不替换测试函数或重跑full给新日志。源冻结变更则不得沿旧full；仅文档收尾不重跑full。完整总数预计2454+15=2469（新增12+2+1），最终以实际summary记total/P/F/E/skip，既有环境skip不是新增方法通过信用；原verbosity1没有逐ID列表不得编造。compile使用root-owned仓外临时cache，保持PYTHONDONTWRITEBYTECODE严格env，j1且不递归删宽路径。测试/守卫失败停止，不commit。

- [x] **Step 9: 文档手工计数/枚举/历史/字段检查及两轮clean。**

当前四文档：本文、设计、持续对照、root已更新的前片Git发布履历；更新stage状态及实际采纳/暂缓/不适配、源摘要、所有真实输出计数/elapsed/exit、独立审身份、七维报告与剩余门。设计原作者观察历史保留，新增root实施记录，不伪改作者已测试。若root同步额外已批准桥接文档，先列精确实际清单，再checker两轮；不能声称固定9文件检查但本片实际只选4。

```bash
python -B /home/orbbec/.agents/skills/doc-contract-consistency-audit/scripts/check_consistency.py docs/nbl/plans/2026-10-09-operation-admission-replay.md docs/nbl/specs/2026-10-09-operation-admission-replay-design.md docs/agent-landscape-live.md docs/nbl/plans/2026-10-09-session-git-tree.md
python -B /home/orbbec/.agents/skills/doc-contract-consistency-audit/scripts/check_consistency.py docs/nbl/plans/2026-10-09-operation-admission-replay.md docs/nbl/specs/2026-10-09-operation-admission-replay-design.md docs/agent-landscape-live.md docs/nbl/plans/2026-10-09-session-git-tree.md
git diff --check
```

完整新untracked/ignored文档在stage前另跑以下精确命令，不依赖当前tracked diff漏掉新文档。此主机实际 `--no-index --check /dev/null` 对无空白问题的新文档仍exit1且无诊断；作者不把它伪报exit0。检查记录同时保留实际exit与stdout/stderr：差异exit1加空诊断不等于空白错误；任何空白诊断必须修复。stage后 `git diff --cached --check` 必须exit0。

```bash
git diff --no-index --check /dev/null docs/nbl/plans/2026-10-09-operation-admission-replay.md
git diff --no-index --check /dev/null docs/nbl/specs/2026-10-09-operation-admission-replay-design.md
```

- [x] **Step 10: 六维逐项记录，不能以单测替代整体门。**

| 维度 | 本片实际计划证据 | 不能授予的信用 |
| --- | --- | --- |
| immediate | 实际首次raw无marker，fresh同keyTrue同attempt；普通/工程0新增payload | 没有整个业务 exactly-once |
| converged | 新真实方法三次0.05秒等待/trace/bytes/marker不变 | 仅有限窗口，不是无限后台保证 |
| restart | 两真实child独立生命期、同durableCP/marker1、不finish | fresh对象不能冒充重启；不是宿主崩溃/断电 |
| replay | open marker0/1、completed同key、明确finish后新occurrence | 不换键绕过，不缓存业务结果 |
| rollback | 拒绝/异常/finish失败不伪关闭；fixture仅owned清理 | 未实现外部补偿或真实cancel；状态partial，不称rollback全通过 |
| failure | malformed仅协议double；真实中文gateid；调用边界抛错/finishFalse/publicresume旧回归 | 不泛称handler未知；不是全故障或模型/OS验收 |

同时记录每行raw、normalized、attempt、marker、host/dispatch/invoke/finish计数、trace和清理；不得只写“全生命周期通过”。工程Broker/model保持double，loopFakeBackend离线；Native false、Linux工程桥接、Windows安装/Reviewer/WFP/Job/PE/UAC、macOS单任务quota、真实模型1→6和≥90%一致及vendor额外授权保持各自门，不能完成R2/R3总goal。

- [x] **Step 11: 仅实际完成root全门后精确main发布，启动新SHA观察并继续下一片。**

当前root已额外更新前片Git发布履历 `docs/nbl/plans/2026-10-09-session-git-tree.md`，本作者不改该文件。下一G1片需纳入该已批准元数据，因此精确11路径（七源+本文+设计+landscape+前片Git计划）；文档checker实际清单也增为这四文档，两轮clean后暂存。若另有批准同步文档，暂存前重列清单及计数，不能 `git add .`。

```bash
git add src/icode/operations.py src/icode/loop.py src/icode/runner.py tests/test_operation_admission.py tests/test_contract_engineering.py scripts/run_workspace_ci.py tests/test_run_workspace_ci.py docs/agent-landscape-live.md
git add -f docs/nbl/plans/2026-10-09-operation-admission-replay.md docs/nbl/specs/2026-10-09-operation-admission-replay-design.md docs/nbl/plans/2026-10-09-session-git-tree.md
git diff --cached --check
git diff --cached --name-only
git status --short
git rev-parse HEAD
git ls-remote --heads origin
```

root逐路径读取Git index blob并核SHA256与冻结bytes匹配，parent为实际当前main，vendor无变化、无Native/权限/KEY。若有其它stage/user改动保存且不混入，不reset；若remote推进停commit/push审查而不force。用户此前明确自动commit/push授权仍适用，不反复等常规命令。

```bash
for admission_path in src/icode/operations.py src/icode/loop.py src/icode/runner.py tests/test_operation_admission.py tests/test_contract_engineering.py scripts/run_workspace_ci.py tests/test_run_workspace_ci.py docs/agent-landscape-live.md docs/nbl/plans/2026-10-09-operation-admission-replay.md docs/nbl/specs/2026-10-09-operation-admission-replay-design.md docs/nbl/plans/2026-10-09-session-git-tree.md
do
    git show ":$admission_path" | sha256sum
done
```

```bash
git commit -m "fix: refuse operation receipt replay before payload execution"
git push origin main
git rev-parse HEAD
git ls-remote --heads origin
```

记录实际SHA/parent/tree/路径/remote仅main；预提交文档只写publishpending，避免自引用新SHA或提前声称push。下一批准片可补当前发布观察履历，不为selfref单独重跑full。只观察新SHA CI/Pages/provenance jobs/artifact，旧923窗口不重试/改写；签名安装成功非原生完成。主代理不等用户常规指令继续已授权下一片，外部权限/账号阻塞单列，安全可做工作继续。

## 作者自审、读范围与当前验收边界

### 原冻结与独立 SPEC 修订历史

原交付为997行，SHA256 `72252d02569b75f70c127e669949859c304da90474c6d9c4e0c6e685197f58a4`，作者selfSPEC→selfQUALITY曾报C0/I0/M0；该自审漏检以下两项，不能据此声称独立审查通过。fresh SPEC `/root/operation_admission_plan_spec` 实际最终C0/I2/M0 STOP，root复核接受，要求本作者只修本文；没有生产或测试执行。

I1（原line838）：method ID交集无法匹配现有工程class `require_skill()` 抛SkipTest产生的 `setUpClass (module.Class)` holder，单选任一新增required工程method仍可0执行/1classskip/main0。已修计划为仅从本次实选newrequired IDs派生四类确切fixture holder集合；新增同一guard内的真实suite生命周期两正控与optional负控。新RealCP原RuntimeError负控保持；旧class/shared helper/optional选择不改。不使用预制Mock result/suite，不泛化所有0执行或skip。这里“已修”仅文档方案，运行负控与same SPEC复审仍待root，不冒称漏洞源码已修。

I2（原line885）：20轮脚本广义substring `skipped` 命中正常guard方法名 `never_static_skipped`，使实际正常结果也被父脚本拒绝。已移除该substring检查，保留16方法及名字，解析真实stderr结果流的Ran16行、末尾裸行OK与exit0，stdout独立完整打印；`OK (skipped=N)`不通过。这里为静态修订，没有运行20轮或其它测试。

本次纯文本再读当前脚本main175–208、实际工程class/fixture1–130和 `_support` 的require_skill合同，核当前解释器symlink为现存CPython3.11.15；实际stdlib `unittest/suite.py` 100–390、`util.py`45–65、`result.py`相关skip入口只读。源码确认四类fixture用 `method_name + ' (' + parent + ')'` 构造 `_ErrorHolder.id()`，SkipTest走addSkip，suite不执行方法时testsRun0；未runtime import或运行这些生命周期。

修订作者selfSPEC→selfQUALITY重新检查：精确selected fixture边界、两工程单选与optional-only负控、真suite/结果、解析末行、原计数/构造/两消费者/四Task/七源/发布11路径不变，当前C0/I0/M0仅作者静态。必须same fresh SPEC复审后由不同QUALITY审查，旧作者结论和本次自审都不能代替独立审。

本文任务链 Task1→2→3→4 为serial，不满足inline条件；复杂协议和真实CP需要独立作者与双审。所有Task仅计划checkbox未执行。5协议/7真实=12新module，2新工程=14required，1新guard共15新增方法；20轮16×20=320执行，DEFAULT预计609、full预计2469，均是预测不是已运行事实。
原997行作者 selfSPEC记录：逐节核获准设计 strict bool/缺字段/旧位置、两消费者、structuredgate、原两次计数、未知/恢复、六维及scope；当时报告“无遗漏，C0/I0/M0”（仅作者静态，已被上述独立I1/I2纠正）。原selfQUALITY记录：先核因果RED避免新字段TypeError，再核新fixture无旧Case继承/重复loader、边界异常准确、真实child与等待窗口信用、发布单片/原full唯一；当时C0/I0/M0，仅历史作者结论。
已全文读 writing-plans261、doc-contract62、checker193、根AGENTS；sequential-thinking实际3步记录只写计划/复用链/信用及风险。源码实读 operations1–106全文、control1–90/270–315、loop164–269完整载荷链、runner1714–1815工程门决定性段；tools/base300–395和上下文1–200、__init__全文、config1–145配置/Settings决定性段；没有runtime import。
测试实际读 `_support`全文、工程1–160/430–515/655–690、loop1–135、recovery1–65/325–402、CLIresume1–120；CI脚本1–208全文、CIguard1–125、preflight1–169全文。combined输出截断处仅对完整可见段授阅读信用；获准设计1–149及150–186分别核读全文，landscape仅固定日期来源记录，不冒称完整历史/20源复核。
初读HEAD8d，root发布消息后本作者只读核HEAD923；发布只改HEAD、不改冻结源。初末摘要在作者交付时复核记录，正文未新增源写操作。

作者末次实际HEAD为 `923433b5d6be5e3bda05684ef4ed98daa69eb9e7`；以下现存六源与vendor摘要前后完全一致，新测试源尚不存在，不冒称七源已冻结：operations `2e72103a85e24b940f6a3147f0a92f186cf2e8580e15abd07951b984437687a0`；loop `1b3d9ddb17deabfe460c0ef0fa03a3d3f10a6307e4a3dd2b9d15a1af5cac3746`；runner `0bc0d5e0711e88e9aee35f3a693430eb529a6d597388a32c3ff0f2defe596a83`。
CI script `6e46fb09bae2673a583da0f41e9abe0b4fe638b0f5f0f08f35d6da75e339a4c7`；CI guard `4ce8d7eb98c6db73ea559e0d979bf1ac9b9948459266d7d8d43e1a3f6d055f58`；engineering tests `a807240ccfd6ad0d9a0add4104c312ce9c7a555596d8e5d3fcd00e9c24ef478d`；vendor control `0b7e2577844f135269bdcc78bee195ad974a350f20792af7de46b2bdae76564c`。此为只读输入绑定，不是本片执行provenance。

【架构级自检报告】范围仅本文静态计划：

- ✅ 语法/结构：实际Markdown checker和全文空白检查，不宣称代码已编译。
- ✅ 依赖/调用链：实际CP/recorder/loop/工程早门与已有resume回归对应。
- ✅ 逻辑/边界：缺字段、strictbool、旧回执/unknown/newoccurrence区分清楚。
- ✅ 异常处理：协议非法、start/invoke边界异常、finishFalse、旧恢复拒绝计划完整；运行未验。
- ✅ 关联模块：七源职责、14精确CI方法、旧回归及文档路径成对。
- ✅ 兼容安全：旧构造/duck/错误、计数、CP真源保留，无授权扩张。
- ⚠️ 可运行性：只文档可检查；所有实现/测试/模型/原生门尚未运行，不能报告生产100%。

作者完成两轮文档clean、全文noindexcheck、前后源摘要核对后交root DONE STOP；不执行下一技能。

---

**Execution Mode:** serial

## root 执行交接与实际履历

1079行修订计划核心 SHA256 `8a14dc4b95f10a73afae44dec1368a3deb332252c050aed97688c65a13bf1758` 已由同 fresh SPEC `/root/operation_admission_plan_spec` 全文复审 C0/I0/M0、不同 QUALITY `/root/operation_admission_plan_quality` 全文审查 C0/I0/M0，两者静态、STOP。原997行/72252及SPEC两I历史保留；本次root仅加交接元数据，不改获准代码/命令。root实读原997行全文与当前Task4/修订历史全增量、两生产门/现有Tools/Guard/Settings及实际标准库fixture与错误归一，不将这些静态读代替运行信用。

`8a14…1758` 是获准时1079行的历史摘要，不是执行中整文件摘要：root会更新头部当前状态、已完成checkbox及后附履历，所以不是仅追加、也不要求现前1079行保持同摘要。获准任务正文、代码与命令未改；每任务审查依实际源冻结和该合同，不把文档进度标记混作源漂移。

### Task1作者交付及独立双审通过

唯一 writer `/root/g1_task1_writer` 已DONE STOP，仅写operations与新协议test两个文件。实际固定来源 `settings.skill_root=/home/orbbec/git/icode/vendor/icode-skill`、python为本文venv、control SHA `0b7e2577844f135269bdcc78bee195ad974a350f20792af7de46b2bdae76564c`。真实CP causalRED first合法且同keyfresh replay raw okTrue/markerTrue/旧attempt、原can_executeTrue，最终assertion exit1/.176185247s；payload/model/Native0，不补finish，ownedtemp已清。三协议方法RED为3tests/10subcase failures/0E/skip/.001s/exit1，不因新字段TypeError取假RED。

作者GREEN协议5/.000s、旧loop/recovery54/4.406s均0F/E/skip/exit0；这59项是作者的软件执行，不挪给root或独立审者。作者没有另跑修后真实CP GREEN，其信用暂不授。作者selfSPEC→selfQUALITY均C0/I0/M0；最终ops SHA `478eaedeec1ec73ebdbc687a23908ab9a8330640c7474859efdf2e4cf7c485e3`、test SHA `39be03aa937289af30ac94cd7e5e38bd92babc6d9f3405fd5bceb270ca546138`。root已全文实读现ops121行、新test135行与实际diff，原counter/request/finish未改；独立Task SPEC正在核，different QUALITY未开始。Task1 checkbox仍待两审结束后勾选，不授整片/跨平台/installed/模型/Native完成。已知completed工程旧错误合同的中间依赖按Task3修，不改旧测试放宽。

随后独立 `/root/g1_task1_spec` 已 C0/I0/M0、missing/extra/mismatch 全0并 STOP。指定严格 prefix 串行实跑协议5/.001s及loop/recovery54/4.277s，全0F/E/skip/rc0。另真实固定 CP admission-only GREEN 实际 .4063682609703392s/rc0：first raw无marker且许可；fresh同request/input/scope，raw markerTrue、同attempt、okTrue/ambiguousFalse/can_executeFalse；前后open_operations相同，finish/payload/model/Native0，owned临时目录清理。此诊断不是 unittest 方法、不授消费者或真实进程重启信用。审前审后两源及loop/runner/vendor/design摘要不变；fresh不同 `/root/g1_task1_quality` 现在接手唯一 runtime。上段“正在核/未开始”保留作者交付时点历史，不代表当前状态。

不同 QUALITY `/root/g1_task1_quality` 已完成 C0/I0/M0、DONE STOP；指定严格 prefix 独立串行协议5/.001s、loop/recovery54/4.605s，全0F/E/skip/rc0，起止两源/设计/loop/runner/vendor SHA相同，未重跑真实CP诊断。root据两审实际结果勾Task1，并于07:07 UTC把完整Task2文本交fresh唯一 `/root/g1_task2_writer`；仅loop/newtest可写、runtime串行，不进入Task3或提交。Task1通过不等于消费者/重启/整片门通过。

### Task2作者交付及独立双审通过

`/root/g1_task2_writer` 已selfSPEC→selfQUALITY各C0/I0/M0、DONE STOP；只改loop早拒绝文案9增3删，新test前135行摘要保持Task1值，追加298行到433行。指定strict prefix串行RED1/.547s/rc1/2文案子场景F/0E/skip，原许可门已经拒绝，不冒称重复载荷因果RED；GREEN新module12/4.158s和loop/recovery/CLI resume63/15.692s，全0F/E/skip/rc0。真实CP断言分开first raw、旧receipt、结构化下一轮歧义、open marker0/1、completed及新occurrence、异常的原finish合同、两独立child与有限3×.05秒观察；child seed是fixture写一次，不冒称第一次handler观察或业务补偿。

最终loop SHA `a08bd2a69499a2b02ad838925ca15b29070938be08270c8318e7cda555001123`、newtest `be77a5b8a4a72a885892a8cc5c6ce237094ef9bef4875458e998a4622d5593d6`；ops/runner/vendor不变，ownedtemps随unittest清理。root实读完整新增136–433及loopdiff，连同前135即全文；fresh `/root/g1_task2_spec` 接手独占runtime，其后不同QUALITY，boxes暂不勾。未执行Task3、full、DEFAULT、模型或Native，未操作index/commit/push。

随后 SPEC `/root/g1_task2_spec` missing/extra/mismatch全0、C0/I0/M0，独立module12/4.049s与关联63/15.381s；不同 QUALITY `/root/g1_task2_quality` C0/I0/M0，独立module12/3.969s与关联63/14.976s。所有运行strict prefix串行、全0F/E/skip/rc0，两审起止source/design及前135摘要相同且DONE STOP。root据实际勾Task2；07:17 UTC交fresh唯一 `/root/g1_task3_writer` 完整Task3文本，只写runner/contract test并独占runtime。前段“boxes暂不勾”等是作者交付历史。Task3/4及整片root门仍待，不授R2/R3通过。

### Task3作者交付及独立双审通过

`/root/g1_task3_writer` selfSPEC→selfQUALITY均C0/I0/M0、DONE STOP。RED真实open和旧completed两方法1.946s/rc1/3F（两个open子场景及completed）/0E/skip，均是replay_refused与start_unconfirmed分类差异，不当payload重复因果RED。生产仅早门类别条件4净增；新两方法由作者QUALITY做原计划式多行排版，旧completed不改。排版前工程41/53.894s通过，最终冻结工程41/45.236s通过；关联admission/loop/recovery/CLI共75/22.808s通过，所有GREEN全0F/E/skip/rc0、strict prefix串行。

runner SHA `a29b6fdfea5eae9234c3f7b24ba5ec6ca5f8025539ae9ba3ef90a44bd7ff7f11`、contracttest `8c09a4389cdebe8c777c6272342a9393f7ceb3ee9ebbf74ba7cd25b7193ba8d7`；其它Task1/2、vendor及196 tracked源/测试中范围外摘要不变。root实读两路径完整diff及新排版，head/index不变，无授权外操作；fresh `/root/g1_task3_spec` 接手唯一runtime，different QUALITY尚待。真实CP/open/marker/finish/host不调用的范围是工程门负控，broker/host seam不是原生执行。Task4及整片门未运行，boxes待两审后勾。

随后 SPEC `/root/g1_task3_spec` missing/extra/mismatch全0、C0/I0/M0，工程41/42.768s与关联75/20.665s；不同 QUALITY `/root/g1_task3_quality` C0/I0/M0，工程41/49.980s与关联75/19.961s。所有实际运行完整strict prefix串行、全0F/E/skip/rc0，两审起止源/设计/vendor/head相同、DONE STOP。root据实际勾Task3，交fresh唯一 `/root/g1_task4_writer` 完整Step1–4文本，只写loader与guard并独占runtime。Task4 Step5–11留root全局审、最终门和精确发布，不由作者越界执行；此前尚待句保留交付历史。

### Task4作者与任务独立双审通过（root后续门待）

作者 `/root/g1_task4_writer` selfSPEC→selfQUALITY C0/I0/M0、DONE STOP，只写loader与guard。两实际RED各1F/0E/skip/rc1：新guard缺constant的hasattr/.089s，旧guard确切漏工程两个ID/.083s；后者按07:35root确认的必要同文件修订取绿，不能改旧tuple或减expected。作者GREEN外层guard25/.195s与精确脚本2/1.180s全0F/E/skip/rc0。nested14方法skip、真实RealCP setup0test1E/main1、两个new工程各0test1holderSkip/wasSuccessfulTrue但main1、oldoptional同holder/main0均由实际guard断言，不混入外层方法数量或授缺资源CP运行信用。

loader SHA `d1239d2614b9f6234afd218d03f1bcc4c9ac82cef0926692fd205bde37b93382`、guard `db3cab74db23aacb95cdcfb56478504452a2ad5210db8cb31e1dc4d88d5116ed`，前五源/vendor不变，root完整实读两文件diff。独立 SPEC `/root/g1_task4_spec` missing/extra/mismatch全0、C0/I0/M0，严格串行guard25/.169s及script2/1.190s全0F/E/skip/rc0，起止七源/设计/vendor/head一致、DONE STOP；不同 `/root/g1_task4_quality` 已接手唯一runtime。此时仍无全局审、root定点/20轮/DEFAULT/full或发布信用，Task4盒不提前勾完成。

不同 QUALITY `/root/g1_task4_quality` C0/I0/M0、DONE STOP，独立严格串行guard25/.168s及script2/1.203s，全0F/E/skip/rc0、七源/设计/vendor/head摘要不变。root据任务双审勾Task4 Step1–4；Task4任务整体盒保留未完成，Step5–11属全局审、root最终验证及精确main发布。fresh `/root/g1_global_spec` 现接手七源整片独立审与唯一runtime；different全局QUALITY未开始，不将任务成功外推整片通过。

### 全局独立审查（root最终门尚待）

fresh `/root/g1_global_spec` 已missing/extra/mismatch全0、C0/I0/M0、DONE STOP。独立完整strict prefix六模块点集单轮141/60.226s，全0F/E/skip/rc0（新12+工程41+guard25+旧关联63）；七源/设计/vendor/head起止完全相同。新方法数和nested缺资源验证不混计。different fresh `/root/g1_global_quality` 接手唯一runtime，root不抢跑原full或其它测试；本人读审查报告不冒领其独立运行信用。root已实读全部七源diff和新module全文、实际调用门及CP/registry/fixture/loader/preflight完整接口；最终定点、20轮、DEFAULT、原full唯一一次、j1、守卫及精确main发布仍待。

随后 different fresh `/root/g1_global_quality` C0/I0/M0、DONE STOP，独立完整strict prefix同六模块141/63.314s，全0F/E/skip/rc0、七源/设计/vendor/head起止不变。root据实际双审勾Step5，07:50 UTC接手唯一runtime，执行本文Step6原六模块命令；保持七源冻结，禁止在运行中修源码取绿。若最终门失败先定位/必要修复/重新冻结，原full按新freeze唯一一次，不能沿旧923 full或审者点集冒称root结果。

### root最终门实际记录（持续更新，不代表整体完成）

root单独按Step6原六模块命令完成141方法/63.194s/0F/E/skip/rc0，07:55 UTC收取终态；不是借用审者运行。七源与vendor control摘要复核相同，随后按Step7原脚本开始16方法×20轮串行关键合同。20轮、DEFAULT、原full、j1/守卫、文档双轮与main发布此时尚未全部结束；当前记录不能授R2/R3完成、Native或真实模型信用。

07:57:58 UTC root收取20轮终态，实际16个不同方法、320 executions、wall134.296s，各轮rc0及真实stderr末行裸OK，无F/E/skip。每轮wall依次为6.766、6.813、6.745、6.596、6.692、6.724、6.651、6.697、6.651、6.698、6.822、6.630、6.640、6.611、6.711、6.735、6.663、6.765、6.879、6.806秒；不是320不同方法或原生隔离测试。随后启动原DEFAULT一次，尚未取终态；Step7含DEFAULT，所以整体盒不提前勾。

08:01:01 UTC root收取原DEFAULT终态609/175.019s/0F/E/skip/rc0，符合595+14；实际bootstrap verifier byte binding PASS。原负控argparse拒绝是被断言的预期输出，不是外层ERROR。root勾Step7并按Step8启动preflight原三道：密钥与子模块均OK，完整子调用实际argv为 `[sys.executable, '-m', 'unittest']`（不新增子进程`-B`），原cwd/capture/text/UTF8/errors/shell参数全部原样。观察包装只前后记录并返回原CompletedProcess；本片唯一full调用已登记，不重复旧923 full，等待真实终态。

### 最终软件验收结果

2026-10-09 08:09:49 UTC实际收取完整终态：2469total、2410通过、59跳过、0失败/错误，unittest503.961s；原子child rc0/wall504.306956s，child_calls=1，preflight三道全通过、rc0/wall505.713562s。bootstrap verifier byte binding PASS。59跳过与前片本机数量相同，但原verbosity1没有逐ID列表，不声称逐ID核对或授通过信用。新增15方法在定点运行，DEFAULT精准选择新增14，因此两个集合分别为2469和609。

08:10:05 UTC compileall使用仓外自有cache、`-j 1`，rc0/wall.617493107s；governance、site、landscape排期均rc0。七源完整SHA与上述任务/全局审冻结一致；vendor保持1693651且clean。原full已完成，文档收尾不重复运行；提交推送尚待，本文头部及前段“正在运行”保留当时记录，当前状态以本节为准。

| 生命周期 | 实际断言 | 限制 |
| --- | --- | --- |
| immediate | first raw缺marker可执行；同key旧rawTrue、同attempt、归一后拒绝；普通invoke/finish/tool_start与工程host/dispatch/finish均无新增调用 | 不证明业务exactly-once |
| converged | 三次各.05秒观察，open attempt、marker和事件bytes保持 | 仅有限观察窗口 |
| restart | 两真实child共享durableCP，seed写x；后child实际loop拒绝，marker仍x、finish/tool_start0 | seed为fixture；非宿主崩溃或installed证明 |
| replay | open marker0/1、completed同key拒绝；明确finish后新occurrence可执行，x变xx、finish1、新attempt | 不自动换键绕未决或缓存结果 |
| rollback | 拒绝不finish；调用边界异常及finish失败仍open | 部分验证，未实现外部补偿或业务回滚 |
| failure | 非bool拒绝且raw不变；start异常、invoke边界异常、handler确定失败规范化、finishFalse及原resume负控通过 | 协议/故障double分列，不授全故障或模型/OS信用 |

【架构级自检报告】仅当前G1软件片：

- ✅ 语法/编译：定点、DEFAULT、原full及compileall-j1通过。
- ✅ 依赖/调用链：真实CP、recorder、两个载荷前门及CI选择完整；独立双审通过。
- ✅ 逻辑/边界：strictbool、缺字段、旧构造、open/completed、新occurrence及真实child覆盖。
- ✅ 异常处理：已列start/协议/invoke/handler/finish及required fixture负控通过。
- ✅ 关联模块：旧duck/read_only/错误分类、selection与公共恢复回归保持。
- ✅ 兼容安全：无vendor、依赖、权限、schema、Native准入或KEY变更。
- ✅ 可运行性：本机实际软件集合通过；59skip及其它平台、installed、真实模型不授完成。

原始工单随owned fixture清理，本片未另存可供第三方重放的原始事件包。Linux实际工程桥接、G2巡检额外授权/完整步骤、Windows Gitpipe/网络/WFP/PE/UAC、macOS单任务配额、真实模型1→6/≥90%及R2/R3整体仍未完成。下一步为四文档两轮检查、精确11路径main提交推送及新SHA观察，再继续已批准Linux桥接。

文档收尾实际四文件连续两轮0疑似项/rc0；手工核新增15/required14、DEFAULT609/full2469、六维边界及历史状态。tracked diff空白检查rc0；两个新增文档各no-index全文检查rc1且零诊断（差异返回码），无空白错误。此次进度标记更新后再次对同四文档两轮检查，提交前以最终工具结果为准；只剩精确索引、main提交推送与新SHA观察，Step11未提前完成。

### main发布与下一片交接

已提交推送 `020acebf51b61179bf401181ac703cb3d71446b6`，parent `923433b5d6be5e3bda05684ef4ed98daa69eb9e7`、tree `494ff7ccfef513489eb08a7e070b48eaa44a8ce2`，精确11路径、2093增20删。提交前11个index blob与工作区完整SHA逐项相同、cached check通过，最终四文档再两轮0疑似项，密钥及子模块守卫再通过。普通git add因docs ignore返回1，随后只对既定文档路径force add；实际index清单和摘要重新核实，无额外路径。push成功，远端仅main且同SHA，发布后工作区clean。此后元数据随下一片提交，避免提交自引用。

新SHA只读观察已启动：CI `37904311427`、Pages `37904311440`、provenance `37904311450`。观察者初次报告Pages两job成功，其余仍在运行；完整终态另记，不回填旧923或提前授跨平台通过。Step11已完成其要求的发布和新观察启动，root已交唯一writer开始批准的Linux桥接Task1。G1软件完成与R2/R3整体未完成同时成立。

后续只读观察：CI `37904311427` 全44 job终态为37success/4failure/3retired skip；Pages `37904311440` 两job成功。Ubuntu/macOS DEFAULT均609/609、零skip；双Linux full（jobs113733975163/113733975322）各2469total/2398P/71skip/0F/E。远端71skip与本机59skip分开，不宣称覆盖相同。双Windows DEFAULT（113733975497/113733975381）各589total/567P/20skip/1F/1E，仍为inspection baseline WinError10093和native legacy dispatch0/WinError10038；双Reviewer仍exit78、10035 wait_expired且denied=false。WFP观察者ready、目标valid但no_matching_event，不能给拒绝网络信用；child_token_receipt=None不误判为token查询失败。provenance验证job已成功，四平台签名安装矩阵仍在观察，待终态单独登记。

最终provenance `37904311450` attempt1已5/5成功，观察者DONE/STOP。四矩阵日志报告installed crypto/offline verifier/负控/bootstrap拒绝setup和commands通过；artifact元数据均绑定该run、main及完整020aceb SHA，未过期，ZIP摘要与上传日志一致：

| 矩阵 / job / artifact | helper SHA256 | ZIP SHA256 |
|---|---|---|
| x64/3.11 / 113737120537 / 11603954724 | f655a51ec930b654baaae72cb5ea59862a6104451817d55797446da9a5f808f0 | 50f716f1fa40badc2ba368da4396bcf81976b02f2fb67bfd5c2e8ac71c2e8942 |
| x64/3.12 / 113737120506 / 11604601260 | a0031579f2f2bd7c429086d9ea702c3b9dac6fa5c5f66b6ac328b162d3b9a03a | 44a76ec5795573271b910c275b89162f968b8fbdcf7ce824ff9e6a4645020027 |
| ARM/3.11 / 113737120455 / 11604182410 | e7e069811ea65222bf4112a69b7c5151f819225bd13b7e026f0cc8e91816d91b | b120a30dfd8303aa954c8f08d8e48d62060e12242a590c348321384d0ce931cf |
| ARM/3.12 / 113737120504 / 11604850186 | bd9b570cb333802306d7cddd783d46aa25de0268c862c8f3cba6634f800fd343 | 7a11d9baa91752226230da565308cb499f02978b9fc82da32d963383083561fb |

helper摘要与各自日志attestation subject、PE receipt一致，但PE的parse_complete/runtime_load_verified/source_launch_verified均false。观察仅日志及API元数据，没有下载包、独立解码statement或执行PE，不授实际生产Windows隔离信用。六native jobs虽success却全部ready=false：Ubuntu22双架构8/10、latest与24ARM7/10、macOS双架构6/10；评分不是整体完成。DEFAULT非verbose不能单凭远端日志逐项确认新增14个required测试身份。当前已无该SHA后台观察任务。
