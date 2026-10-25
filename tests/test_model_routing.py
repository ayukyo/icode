"""模型路由：纯选择、确定性、不产生状态第二真源（R4/G4）。"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from icode.backends import FakeBackend
from icode.contracts import ContractSet
from icode.handshake import next_out_dir
from icode.isolation import NoIsolation
from icode.model_routing import (ModelRoute, RouteError, apply_route,
                                 resolve_route, route_table)
from icode.runner import _run_agent
from icode.orchestration_context import RunContext, StepRequest
from tests._support import require_skill, temp_workspace


class TestRouteResolution(unittest.TestCase):
    def test_环境路由表解析与缺省(self) -> None:
        table = route_table({
            "ICODE_MODEL_ROUTE_CODE": "anthropic:claude-x",
            "ICODE_MODEL_ROUTE_REVIEW": "gemini:flash",
            "ICODE_MODEL_ROUTE_BAD": "",
            "UNRELATED": "x",
        })
        self.assertEqual(table["code"], ModelRoute("code", "anthropic", "claude-x"))
        self.assertNotIn("bad", table)
        self.assertNotIn("unrelated", table)

    def test_解析优先级_显式大于只读默认大于全局默认(self) -> None:
        table = route_table({"ICODE_MODEL_ROUTE_REVIEW": "gemini:flash"})
        self.assertEqual(resolve_route("code", table=table).backend, "openai-compatible")
        self.assertEqual(resolve_route("review", table=table).backend, "gemini")
        self.assertEqual(resolve_route("deepcheck", table=table).backend, "gemini")
        explicit = route_table({"ICODE_MODEL_ROUTE_CODE": "ollama:llama3"})
        self.assertEqual(resolve_route("code", table=explicit).backend, "ollama")

    def test_解析是纯函数且不修改入参(self) -> None:
        table = route_table({"ICODE_MODEL_ROUTE_CODE": "anthropic:m"})
        before = dict(table)
        first = resolve_route("code", table=table)
        second = resolve_route("code", table=table)
        self.assertEqual(first, second)
        self.assertEqual(table, before)

    def test_装配只调用一次且不保存状态(self) -> None:
        calls = []

        def builder(backend, model):
            calls.append((backend, model))
            return {"backend": backend, "model": model}

        built = apply_route(resolve_route("code", table=route_table(
            {"ICODE_MODEL_ROUTE_CODE": "gemini:g1"})), builder=builder)
        self.assertEqual(calls, [("gemini", "g1")])
        self.assertEqual(built, {"backend": "gemini", "model": "g1"})

    def test_非法步骤拒绝(self) -> None:
        for step in ("", None, 7):
            with self.subTest(step=step):
                with self.assertRaises(ValueError):
                    resolve_route(step)  # type: ignore[arg-type]


class TestStepBackendSelection(unittest.TestCase):
    """runner 按步选后端：未配置不变、配置即生效、构造失败不回落。"""

    def test_未配置路由保持主后端(self) -> None:
        from icode.runner import _step_backend

        primary = FakeBackend(["x"])
        self.assertIs(_step_backend("review", primary, None, None), primary)
        self.assertIs(_step_backend("review", primary, {}, None), primary)
        self.assertIs(_step_backend("code", primary,
                                    {"review": ModelRoute("review", "gemini", "g")},
                                    None), primary)

    def test_配置路由则用构造出的后端(self) -> None:
        from icode.runner import _step_backend

        primary = FakeBackend(["x"])
        routed = FakeBackend(["y"])
        calls = []

        def builder(kind, model):
            calls.append((kind, model))
            return routed

        built = _step_backend("review", primary,
                              {"review": ModelRoute("review", "gemini", "g1")},
                              builder)
        self.assertIs(built, routed)
        self.assertEqual(calls, [("gemini", "g1")])

    def test_构造失败失败封闭且不回落(self) -> None:
        from icode.model_routing import RouteError
        from icode.runner import _step_backend

        primary = FakeBackend(["x"])

        def broken(kind, model):
            raise RuntimeError("boom")

        with self.assertRaises(RouteError):
            _step_backend("review", primary,
                          {"review": ModelRoute("review", "gemini", "g1")}, broken)
        self.assertEqual(primary.calls, [])

    def test_空构造结果也失败封闭(self) -> None:
        from icode.model_routing import RouteError
        from icode.runner import _step_backend

        with self.assertRaises(RouteError):
            _step_backend("review", FakeBackend(["x"]),
                          {"review": ModelRoute("review", "gemini", "g1")},
                          lambda kind, model: None)


class TestModelSwitchKeepsSingleTruth(unittest.TestCase):
    """同脚本、不同模型身份：产物逐字节一致，模型名不进入状态。"""

    def _run_once(self, workspace_root, name: str) -> dict[str, bytes]:
        workspace = workspace_root / f"ws-{name}"
        workspace.mkdir()
        out_dir = next_out_dir(workspace)
        contract = ContractSet.load(require_skill().gates_json).step("review")
        backend = FakeBackend([
            {"content": "", "tool_calls": [{
                "id": "submit-review", "name": "submit_artifact",
                "arguments": {"name": "02_review.md",
                              "content": "# Review\n\nNo findings.\n"},
            }]},
            "审查产物已提交",
        ])
        backend.name = name

        class _Operations:
            def start(self, **_kwargs):
                return SimpleNamespace(can_execute=True, attempt="attempt-1", detail="")

            def finish(self, *_args, **_kwargs):
                return True

        report = _run_agent(
            ctx=RunContext.from_arguments(
                backend=backend, approver=None, loop_config=None,
                budget=None, on_event=None,
                sandbox=NoIsolation(reason="route switch equivalence"),
            ),
            request=StepRequest(
                brief="Review the current changes.",
                contract=contract,
                requirement="Keep the Reviewer read-only.",
                operations=_Operations(),
            ),
            workspace=workspace,
            out_dir=out_dir,
            ticket_id="ROUTE-SWITCH",
            step="review",
        )
        self.assertTrue(report.requests_ok if hasattr(report, "requests_ok") else True)
        artifacts: dict[str, bytes] = {}
        for path in sorted(out_dir.rglob("*")):
            if path.is_file():
                artifacts[path.relative_to(out_dir).as_posix()] = path.read_bytes()
        return artifacts

    def test_两条路由产物逐字节一致(self) -> None:
        with temp_workspace() as root:
            first = self._run_once(root, "fake-a")
            second = self._run_once(root, "fake-b")
        self.assertEqual(first, second, "模型身份不得进入产物或状态")
        self.assertIn("02_review.md", first)


if __name__ == "__main__":
    unittest.main()
