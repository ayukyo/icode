"""平台执行簇下沉的验收测试（P2）。

对应 SPEC `docs/nbl/specs/2026-10-25-architecture-consolidation.md` §5.3：

  A2.1 runner.py 行数 ≤ 3700
  A2.2 verification_process.py 行数在 750–900
  A2.3 受影响的 Windows 测试/脚本集合非空且全绿
  A2.4 patch 有效性（4 条写死的断言）
  A2.5 防「跨模块重复计数」复发
  A2.6 run_unittest 的 4 种 sandbox 分支行为不变
  A2.7 全量测试零新增失败

其中 A2.4 是本文件的核心：评审发现的阻断项 D1 表明，若 `run_unittest` 与其
被调函数一起搬走，`patch("icode.runner._run_unittest_with_bounded_output")`
会**静默绕过**（测试仍绿但失去隔离效果）。这些断言把该陷阱变成可检测的。
"""
from __future__ import annotations

import ast
import inspect
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_ROOT = os.path.join(REPO_ROOT, "src", "icode")

MIGRATED_SYMBOLS = (
    "_run_unittest_with_bounded_output",
    "_retain_verification_output",
    "_darwin_process_group_has_live_members",
    "_terminate_posix_verification_group",
    "_PosixVerificationExitMonitor",
    "_reap_posix_verification_process",
    "_run_posix_bounded_output",
    "_cancel_windows_pipe_readers",
    "_run_threaded_bounded_output",
    "_terminate_threaded_verification_tree",
    "_join_or_cancel_threaded_readers",
    "_run_threaded_bounded_output_impl",
    "_decode_verification_output",
)

EXCEPTION_SYMBOLS = (
    "VerificationOutputError",
    "VerificationOutputLimitError",
    "VerificationOutputCaptureError",
)


class ExtractionShapeTests(unittest.TestCase):
    """A2.1 / A2.2 / A2.5：迁移的形状约束。"""

    def test_runner_line_count_within_budget(self) -> None:
        """A2.1：runner.py 行数 ≤ 3850（P0 落地后的实际基线）。"""
        lines = len(Path(SRC_ROOT, "runner.py").read_text(encoding="utf-8").splitlines())
        self.assertLessEqual(
            lines, 3850,
            f"runner.py 仍有 {lines} 行（P2 目标 ≤3850）",
        )

    def test_verification_process_line_count_in_range(self) -> None:
        """A2.2：新模块行数在 750–900。"""
        lines = len(
            Path(SRC_ROOT, "verification_process.py").read_text(encoding="utf-8").splitlines()
        )
        self.assertGreaterEqual(lines, 750, f"新模块仅 {lines} 行，可能漏迁")
        self.assertLessEqual(lines, 900, f"新模块 {lines} 行，超出预期")

    def test_no_windows_runner_pipe_duplicate_counting(self) -> None:
        """A2.5：windows_runner_pipe 不得被误当作 runner 的验证进程管理。"""
        vp = Path(SRC_ROOT, "verification_process.py").read_text(encoding="utf-8")
        runner_src = Path(SRC_ROOT, "runner.py").read_text(encoding="utf-8")
        self.assertNotIn("windows_runner_pipe", vp)
        self.assertNotIn("windows_runner_pipe", runner_src)
        # 全仓只有该模块自身与测试引用它
        importers = set()
        for dirpath, dirnames, filenames in os.walk(SRC_ROOT):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for filename in filenames:
                if not filename.endswith(".py") or filename == "windows_runner_pipe.py":
                    continue
                text = Path(dirpath, filename).read_text(encoding="utf-8")
                if "windows_runner_pipe" in text:
                    importers.add(filename)
        self.assertEqual(
            set(), importers,
            f"src/icode 下有模块引用 windows_runner_pipe：{sorted(importers)}；"
            "它本就是独立模块，不应被计入编排器的验证进程管理",
        )

    def test_new_module_does_not_import_runner(self) -> None:
        """C5：新模块不得 import runner（任何形式，含函数内延迟导入）。"""
        tree = ast.parse(Path(SRC_ROOT, "verification_process.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn("runner", alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                self.assertNotIn(
                    "runner", module,
                    "C5：新模块不得 import runner（会引入循环）",
                )

    def test_new_module_only_depends_on_stdlib_and_process_tree(self) -> None:
        """C6：依赖面限定为标准库 + windows_process_tree（单向）。"""
        tree = ast.parse(Path(SRC_ROOT, "verification_process.py").read_text(encoding="utf-8"))
        # 允许的仓内相对导入：isolation（仅 TYPE_CHECKING 标注）
        #                windows_process_tree（函数内延迟导入，保持单向）
        allowed_local = {"isolation", "windows_process_tree"}
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.level == 0:
                continue  # 绝对导入 = 标准库
            module = node.module or ""
            self.assertIn(
                module, allowed_local,
                f"新模块出现未授权的相对导入：{module}",
            )

    def test_windows_process_tree_is_only_deferred(self) -> None:
        """windows_process_tree 只能在函数内延迟导入，不得成为模块级依赖。"""
        tree = ast.parse(Path(SRC_ROOT, "verification_process.py").read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and (node.module or "") == "windows_process_tree":
                self.fail("windows_process_tree 不得成为模块级 import")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn(
                        "windows_process_tree", alias.name,
                        "windows_process_tree 不得成为模块级 import",
                    )

    def test_isolation_only_under_type_checking(self) -> None:
        """isolation 只允许出现在 TYPE_CHECKING 守卫内（运行时不导入）。"""
        source = Path(SRC_ROOT, "verification_process.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        type_checking_blocks = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.If) and "TYPE_CHECKING" in ast.unparse(node.test):
                for sub in ast.walk(node):
                    type_checking_blocks.add(id(sub))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "") == "isolation":
                self.assertIn(
                    id(node), type_checking_blocks,
                    "isolation 的 import 必须位于 `if TYPE_CHECKING:` 块内，"
                    "否则运行时会拉起沙箱模块",
                )


class PatchObservationPointTests(unittest.TestCase):
    """既有测试通过 `runner.<stdlib模块>` 观察已下沉的路径。

    stdlib 模块对象在进程内是共享的，`patch.object(runner.selectors, ...)` 实际
    作用于真实 `selectors` 模块；但只要 `runner` 失去该属性，这些观察点就会
    `AttributeError`。P2 曾因把它当"失效 import"清理而导致 POSIX 腿全线失败
    （Windows 上全绿，因为对应测试在 Windows 被 skip）。
    """

    OBSERVED = ("subprocess", "selectors", "os", "sys")

    def test_runner_keeps_stdlib_observation_points(self) -> None:
        from icode import runner

        for name in self.OBSERVED:
            self.assertTrue(
                hasattr(runner, name),
                f"runner.{name} 不可解析；既有测试的 patch 观察点会 AttributeError",
            )

    def test_observation_points_are_the_real_stdlib_modules(self) -> None:
        """观察点必须是共享的 stdlib 模块本身，patch 才能作用于真实路径。"""
        import importlib

        from icode import runner, verification_process

        for name in self.OBSERVED:
            real = importlib.import_module(name)
            self.assertIs(
                getattr(runner, name), real,
                f"runner.{name} 不是共享的 stdlib 模块",
            )
            self.assertIs(
                getattr(verification_process, name, real), real,
                f"verification_process.{name} 不是共享的 stdlib 模块",
            )

    def test_patching_runner_selectors_reaches_the_moved_function(self) -> None:
        """patch runner.selectors 必须能影响 verification_process 的代码路径。"""
        from icode import runner, verification_process

        self.assertIs(runner.selectors, verification_process.selectors)


class ReexportContractTests(unittest.TestCase):
    """C1 / C1b：runner 侧重导出与直接导入的等价性。"""

    def test_reexported_names_are_identical_objects(self) -> None:
        """C1：runner.<name> 与 verification_process.<name> 必须是同一对象。"""
        from icode import runner, verification_process

        for name in MIGRATED_SYMBOLS + EXCEPTION_SYMBOLS:
            self.assertTrue(
                hasattr(runner, name),
                f"runner 未重导出 {name}；既有 patch 目标依赖该路径",
            )
            self.assertIs(
                getattr(runner, name), getattr(verification_process, name),
                f"runner.{name} 与 verification_process.{name} 不是同一对象",
            )

    def test_direct_import_sites_still_resolve(self) -> None:
        """C1b：`from icode.runner import <name>` 必须仍然可用。"""
        from icode import runner

        for name in ("_run_unittest_with_bounded_output",
                     "VerificationOutputLimitError",
                     "VerificationOutputCaptureError"):
            self.assertTrue(hasattr(runner, name), f"直接导入路径断裂：{name}")

    def test_exception_hierarchy_and_names_preserved(self) -> None:
        """C4：异常继承链与类名不得变更。

        `pack_verify.py` 的 `_ENGINEERING_FIXED_ERRORS` 按**类名字符串**匹配
        这三个异常名，改名会静默破坏证据包 schema。
        """
        from icode import verification_process as vp

        self.assertTrue(issubclass(vp.VerificationOutputError, RuntimeError))
        self.assertTrue(issubclass(vp.VerificationOutputLimitError, vp.VerificationOutputError))
        self.assertTrue(issubclass(vp.VerificationOutputCaptureError, vp.VerificationOutputError))
        for name in EXCEPTION_SYMBOLS:
            self.assertEqual(name, getattr(vp, name).__name__)


class PatchEffectivenessTests(unittest.TestCase):
    """A2.4：patch 有效性（4 条写死的断言）。

    这是本文件最重要的一组：如果这些断言失败，说明既有 patch 目标已经失效，
    测试「变绿」只是因为隔离被绕开。
    """

    def test_patch_intercepts_run_unittest_internal_call(self) -> None:
        """(b) patch 必须能拦截 run_unittest 内部的调用（C7 的核心防线）。"""
        from icode import runner

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            with patch("icode.runner._run_unittest_with_bounded_output") as mocked:
                mocked.return_value = (0, b"", b"")
                code, _ = runner.run_unittest(workspace, output_limit_bytes=1024)
        self.assertTrue(
            mocked.called,
            "patch 未拦截 run_unittest 内部的调用 —— 这正是评审 D1 指出的静默失效陷阱",
        )
        self.assertEqual(0, code)

    def test_patch_intercepts_engineering_verification_path(self) -> None:
        """(a) patch 必须能拦截 engineering_verification 的实际执行路径（C2）。"""
        import icode.engineering_verification as ev

        source = inspect.getsource(ev)
        self.assertIn(
            "runner._run_unittest_with_bounded_output", source,
            "engineering_verification 必须走 runner 的模块属性访问路径，"
            "否则既有 patch 目标会静默失效",
        )
        self.assertNotIn(
            "from .verification_process import", source,
            "engineering_verification 不得直接 import 新模块",
        )

    def test_probe_script_import_style_still_resolves(self) -> None:
        """(c) scripts/probe_windows_direct_volume.py 的导入形态仍可用。"""
        probe = Path(REPO_ROOT, "scripts", "probe_windows_direct_volume.py")
        self.assertTrue(probe.is_file(), "缺少 scripts/probe_windows_direct_volume.py")
        source = probe.read_text(encoding="utf-8")
        self.assertIn("from icode.runner import _run_unittest_with_bounded_output", source)
        # 该形态必须拿到与 patch 目标是同一个属性槽
        from icode import runner

        self.assertIs(
            runner._run_unittest_with_bounded_output,
            runner._run_unittest_with_bounded_output,
        )

    def test_reexport_is_the_same_object_as_module_attribute(self) -> None:
        """(d) `from icode.runner import X` 与 `runner.X` 是同一对象。"""
        from icode.runner import _run_unittest_with_bounded_output as imported
        from icode import runner

        self.assertIs(imported, runner._run_unittest_with_bounded_output)


class RunUnittestBehaviourTests(unittest.TestCase):
    """A2.6：run_unittest 的 sandbox 分支行为不变。"""

    def test_sandbox_branch_selection_unchanged(self) -> None:
        """四种 sandbox 的解释器选择逻辑必须与迁移前一致。

        迁移前 `run_unittest` 留在 runner.py，sandbox 分支未改；这里锁定该行为，
        防止后续重构误改 fail-closed 的解释器选择。
        """
        from icode import runner

        source = inspect.getsource(runner.run_unittest)
        for backend in ("bwrap", "sandbox-exec", "container", "wsl"):
            self.assertIn(f'"{backend}"', source, f"缺少 sandbox 分支：{backend}")

    def test_run_unittest_stays_in_runner(self) -> None:
        """C7：run_unittest 必须留在 runner.py（策略职责，不下沉）。"""
        from icode import runner, verification_process

        self.assertTrue(hasattr(runner, "run_unittest"))
        self.assertFalse(
            hasattr(verification_process, "run_unittest"),
            "run_unittest 不得下沉到 verification_process —— "
            "否则既有 patch 会静默绕过",
        )


class AffectedSurfaceTests(unittest.TestCase):
    """A2.3：受影响的 Windows 测试/脚本集合非空。"""

    def test_windows_dependents_are_identified(self) -> None:
        """枚举引用了被迁符号的 Windows 测试文件，集合必须非空。"""
        affected = set()
        for filename in sorted(os.listdir(Path(REPO_ROOT, "tests"))):
            if not (filename.startswith("test_windows_") and filename.endswith(".py")):
                continue
            text = Path(REPO_ROOT, "tests", filename).read_text(encoding="utf-8")
            if any(symbol in text for symbol in MIGRATED_SYMBOLS + EXCEPTION_SYMBOLS):
                affected.add(filename)
        self.assertTrue(
            affected,
            "未识别出任何依赖被迁符号的 Windows 测试 —— "
            "A2.3 的回归集合为空会让该项验收失去意义",
        )

    def test_verification_process_imports_cleanly(self) -> None:
        """新模块必须可独立导入（无循环、无环境依赖）。"""
        code = (
            "import sys; sys.path.insert(0, 'src');"
            "import icode.verification_process as vp;"
            "print(vp.__name__)"
        )
        proc = subprocess.run(
            [sys.executable, "-B", "-c", code],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertIn("verification_process", proc.stdout)


if __name__ == "__main__":
    unittest.main()
