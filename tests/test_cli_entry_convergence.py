"""CLI 入口收敛的验收测试（P3）。

对应 SPEC `docs/nbl/specs/2026-10-25-architecture-consolidation.md` §6.3：

  A3.1 `cli.py` 中 `LoopConfig(` 构造点 ≤ 1、`build_backend(` == 0、
       `CliApprover(` == 0
  A3.2 `cmd_task` 与 `cmd_step_run` 内不再自行拼装 `LoopConfig(` / `Budget(`
  A3.3 `tests/test_cli` + `tests/test_cli_resume_sandbox` 全绿
  A3.4 cli.py 的内部模块依赖数下降（观察指标）

P3 在 SPEC 里降级为「P2 之后的顺带清理」：目标是消除同一编排知识在多处维护，
不是削减 CLI 的合法职责（参数解析与协作者装配本来就属于入口层）。
"""
from __future__ import annotations

import ast
import os
import unittest
from pathlib import Path

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI_PATH = Path(REPO_ROOT, "src", "icode", "cli.py")


class CliEntryConvergenceTests(unittest.TestCase):
    """入口层的编排知识必须只存在于一处。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = CLI_PATH.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        cls.lines = cls.source.splitlines()

    # ------------------------------------------------------------------ A3.1
    def test_loop_config_constructed_once(self) -> None:
        """A3.1：`LoopConfig(` 在整个 cli.py 只允许出现一次真实构造。

        允许的例外是文档字符串里的说明性引用（不构成调用）。
        """
        constructions = [
            (i + 1, line) for i, line in enumerate(self.lines)
            if "LoopConfig(" in line and not line.lstrip().startswith(("#", '"', "'"))
            and "避免各" not in line
        ]
        self.assertEqual(
            1, len(constructions),
            f"cli.py 中 LoopConfig( 出现 {len(constructions)} 处："
            f"{[n for n, _ in constructions]}；编排知识应收敛到 _build_runner 一处",
        )
        line_no, text = constructions[0]
        self.assertIn("return backend, approver, budget, on_event, sandbox, LoopConfig(", text)
        # 该构造必须在 _build_runner 内
        self.assertLess(line_no, self._end_of("_build_runner"))

    def test_backend_and_approver_assembled_once(self) -> None:
        """A3.2：backend / approver / budget 的装配只发生在 _build_runner 内。"""
        for symbol in ("build_backend(", "CliApprover(", "Budget("):
            hits = [
                i + 1 for i, line in enumerate(self.lines)
                if symbol in line and not line.lstrip().startswith(("#", '"', "'"))
            ]
            self.assertEqual(
                1, len(hits),
                f"{symbol} 在 cli.py 出现 {len(hits)} 处：{hits}；应只在 _build_runner 内",
            )
            self.assertLess(
                hits[0], self._end_of("_build_runner"),
                f"{symbol} 的装配点必须位于 _build_runner 内",
            )

    # ------------------------------------------------------------------ A3.2
    def test_task_and_step_run_do_not_assemble_orchestration(self) -> None:
        """A3.3：cmd_task / cmd_step_run 不得自行拼装回路或预算。"""
        for func_name in ("cmd_task", "cmd_step_run"):
            start = self._start_of(func_name)
            end = self._end_of(func_name)
            body = "\n".join(self.lines[start - 1:end])
            for symbol in ("LoopConfig(", "Budget("):
                self.assertNotIn(
                    symbol, body,
                    f"{func_name} 内仍自行构造 {symbol}；编排知识应收敛到 _build_runner",
                )

    def test_build_runner_returns_loop_config(self) -> None:
        """_build_runner 必须一并返回回路配置，调用点才能零构造。"""
        start = self._start_of("_build_runner")
        end = self._end_of("_build_runner")
        body = "\n".join(self.lines[start - 1:end])
        self.assertIn("LoopConfig(", body, "_build_runner 未装配 LoopConfig")
        self.assertIn(
            "return backend, approver, budget, on_event, sandbox, LoopConfig(",
            body,
            "_build_runner 的返回元组应包含 LoopConfig",
        )

    def test_all_call_sites_unpack_six_elements(self) -> None:
        """所有调用点必须按 6 元素解包，否则会静默错位。"""
        call_sites = [
            i + 1 for i, line in enumerate(self.lines)
            if "_build_runner(args)" in line and "return" not in line
        ]
        self.assertGreaterEqual(len(call_sites), 4, f"调用点过少：{call_sites}")
        for line_no in call_sites:
            text = self.lines[line_no - 1]
            self.assertIn(
                "loop_config", text,
                f"第 {line_no} 行的调用点未解包 loop_config：{text.strip()}",
            )

    # ------------------------------------------------------------------ A3.4
    def test_cli_internal_dependency_count(self) -> None:
        """A3.4（观察指标）：记录内部依赖数，防止入口层继续膨胀。"""
        modules = set()
        for dirpath, dirnames, filenames in os.walk(
            os.path.join(REPO_ROOT, "src", "icode")
        ):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for filename in filenames:
                if filename.endswith(".py"):
                    rel = os.path.relpath(
                        os.path.join(dirpath, filename),
                        os.path.join(REPO_ROOT, "src", "icode"),
                    ).replace(os.sep, ".")
                    modules.add(rel[:-3])
        deps = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.level:
                deps.add(node.module)
        # 观察指标：不做硬门限，只记录
        self.assertLessEqual(
            len(deps), 30,
            f"cli.py 的相对导入模块数 {len(deps)} 异常膨胀",
        )

    # ------------------------------------------------------------------ helpers
    def _start_of(self, name: str) -> int:
        for node in self.tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node.lineno
        self.fail(f"找不到函数 {name}")

    def _end_of(self, name: str) -> int:
        for node in self.tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node.end_lineno
        self.fail(f"找不到函数 {name}")


class StepRunRouteBindingTests(unittest.TestCase):
    """`icode step-run` 必须真的把步骤路由表传下去。

    历史缺陷：`_build_runner` 内部算了 routes，但 `cmd_step_run` / `cmd_chain`
    引用了一个**并未定义**的 `routes` → 运行即 NameError，整条 step-run 命令
    不可用。该路径长期未被 CI 覆盖，直到静态名字解析守卫上线才暴露。
    """

    def test_cmd_step_run_passes_routes_without_name_error(self) -> None:
        import argparse
        from unittest.mock import patch

        from icode import cli

        args = argparse.Namespace(
            backend="fake", key_file="", model="", base_url="", proxy="",
            no_proxy=None, approve=False, budget_tokens=1000, quiet=False,
            isolation="auto", max_turns=3, skill_root="", step="plan",
            ticket_id="T1", workspace=".", requirement="r", out_dir=".",
        )
        with patch("icode.backends.build_backend", return_value=object()), \
             patch("icode.isolation.select_sandbox", return_value=object()), \
             patch("icode.runner.run_contract_step") as run:
            cli.cmd_step_run(args)
        self.assertIn("routes", run.call_args.kwargs,
                      "step-run 必须把路由表传给 run_contract_step")
        self.assertIsNone(run.call_args.kwargs["routes"])

    def test_build_runner_returns_routes(self) -> None:
        """`_build_runner` 必须返回路由表，否则调用方无从取得。"""
        import argparse
        from unittest.mock import patch

        from icode import cli

        args = argparse.Namespace(
            backend="fake", key_file="", model="", base_url="", proxy="",
            no_proxy=None, approve=False, budget_tokens=1000, quiet=False,
            isolation="auto", max_turns=3,
        )
        with patch("icode.backends.build_backend", return_value=object()), \
             patch("icode.isolation.select_sandbox", return_value=object()):
            built = cli._build_runner(args)
        self.assertEqual(7, len(built),
                         f"_build_runner 应返回 7 个元素，实际 {len(built)}")
        self.assertIsNone(built[6], "无路由配置时 routes 应为 None")


if __name__ == "__main__":
    unittest.main()
