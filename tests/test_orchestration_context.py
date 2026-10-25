"""编排上下文（P0 参数收敛）的验收测试。

对应 SPEC `docs/nbl/specs/2026-10-25-architecture-consolidation.md` §3.4：

  A0.1 对外签名基线快照逐字段不变
  A0.2 上下文内部版本参数数 ≤ 8
  A0.3 `_run_agent` 参数数 ≤ 8
  A0.4 上下文装配与旧扁平实参等价
  A0.5 RunContext / StepRequest 不可变
"""
from __future__ import annotations

import dataclasses
import inspect
import json
import os
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINE_PATH = os.path.join(REPO_ROOT, "docs", "nbl", "specs", "baseline_signatures.json")


def _baseline() -> dict:
    with open(BASELINE_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _current_signature(func) -> dict:
    sig = inspect.signature(func)
    params = []
    for name, param in sig.parameters.items():
        params.append({
            "name": name,
            "kind": str(param.kind),
            "default": None if param.default is inspect.Parameter.empty else repr(param.default),
            "has_default": param.default is not inspect.Parameter.empty,
        })
    return {"param_count": len(params), "params": params}


class OutwardSignatureTests(unittest.TestCase):
    """A0.1：对外编排函数签名逐字段不变。"""

    def test_outward_signatures_match_baseline(self) -> None:
        import importlib

        baseline = _baseline()["signatures"]
        for key, expected in baseline.items():
            module_name, func_name = key.rsplit(".", 1)
            func = getattr(importlib.import_module(module_name), func_name)
            actual = _current_signature(func)
            self.assertEqual(
                expected["params"], actual["params"],
                f"{key} 的对外签名发生变化：重构不得改动公开契约",
            )
            self.assertEqual(expected["param_count"], actual["param_count"], key)

    def test_baseline_file_is_present_and_non_trivial(self) -> None:
        """基线快照本身必须存在且覆盖全部四个对外函数。"""
        data = _baseline()
        self.assertIn("signatures", data)
        self.assertEqual(
            {"icode.runner.run_contract_step", "icode.runner.resume_contract_step",
             "icode.runner.run_task", "icode.chain.run_chain"},
            set(data["signatures"]),
        )


class ContextConvergenceTests(unittest.TestCase):
    """A0.2 / A0.3：上下文版本的参数收敛。"""

    def test_run_agent_parameter_count_within_budget(self) -> None:
        from icode import runner

        count = len(inspect.signature(runner._run_agent).parameters)
        self.assertLessEqual(
            count, 8,
            f"_run_agent 仍有 {count} 个参数（P0 目标 ≤8）",
        )

    def test_run_agent_parameters_are_keyword_only(self) -> None:
        """全部关键字传参，保证调用点形态稳定、mock 友好。"""
        from icode import runner

        sig = inspect.signature(runner._run_agent)
        for name, param in sig.parameters.items():
            self.assertEqual(
                param.kind, inspect.Parameter.KEYWORD_ONLY,
                f"_run_agent 的 {name} 不是关键字参数",
            )

    def test_context_version_parameter_count_within_budget(self) -> None:
        """A0.2：上下文内部版本同样 ≤8。"""
        from icode import runner

        # 上下文版本就是 _run_agent 本身（ctx + request + 4 个差异参数 = 6）
        count = len(inspect.signature(runner._run_agent).parameters)
        self.assertLessEqual(count, 8)


class ContextAssemblyTests(unittest.TestCase):
    """A0.4：上下文装配与旧扁平实参严格等价。"""

    def test_from_arguments_maps_every_field(self) -> None:
        from icode.orchestration_context import RunContext

        sentinel = object()
        kwargs = {
            "backend": "BACKEND",
            "approver": "APPROVER",
            "loop_config": "LOOP",
            "budget": "BUDGET",
            "budget_tracker": "TRACKER",
            "on_event": "EVENT",
            "checkpointer": "CKPT",
            "sandbox": "SANDBOX",
            "policy": "POLICY",
            "workspace_session": "SESSION",
            "inspection_runner": "INSPECTION",
        }
        ctx = RunContext.from_arguments(**kwargs)
        for field, value in kwargs.items():
            self.assertEqual(
                getattr(ctx, field), value,
                f"RunContext.{field} 未忠实映射传入实参",
            )

    def test_from_arguments_accepts_payload_only_fields(self) -> None:
        """载荷类字段不属于上下文，不得污染环境。"""
        from icode.orchestration_context import RunContext

        ctx = RunContext.from_arguments(
            backend="B", change_baseline={"a": "b"}, operations="OPS",
            resume_context="RESUME", prepared_step="STEP", prepared_attempt="ATTEMPT",
        )
        for field in ("change_baseline", "operations", "resume_context",
                      "prepared_step", "prepared_attempt"):
            self.assertFalse(
                hasattr(ctx, field),
                f"RunContext 不应承载载荷字段 {field}",
            )


class ContextImmutabilityTests(unittest.TestCase):
    """A0.5：上下文不可变。"""

    def test_run_context_is_frozen(self) -> None:
        from icode.orchestration_context import RunContext

        ctx = RunContext.from_arguments(backend="B")
        self.assertTrue(dataclasses.is_dataclass(ctx))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            ctx.backend = "OTHER"  # type: ignore[misc]

    def test_step_request_is_frozen(self) -> None:
        from icode.orchestration_context import StepRequest

        request = StepRequest(brief="B")
        self.assertTrue(dataclasses.is_dataclass(request))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            request.brief = "OTHER"  # type: ignore[misc]

    def test_prepared_call_pairs_step_and_attempt(self) -> None:
        """prepared_step 与 prepared_attempt 必须成对，不能只传一半。"""
        from icode.orchestration_context import PreparedCall

        call = PreparedCall(step="S", attempt="A")
        self.assertTrue(call.is_bound)
        self.assertFalse(PreparedCall().is_bound)


if __name__ == "__main__":
    unittest.main()
