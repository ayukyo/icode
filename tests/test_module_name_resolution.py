"""模块级名字解析守卫：静态发现只在特定平台分支才会触发的 NameError。

Windows 跑不到 POSIX/macOS 分支，所以那里的 `NameError` 在本机完全不可见，
只在 CI 的对应腿上炸。用 `symtable`（标准库）静态解析每个模块的全局名，
把「引用了但模块级没定义」的名字在提交前就揪出来。
"""
from __future__ import annotations

import builtins
import os
import symtable
import unittest
from pathlib import Path

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_ROOT = Path(REPO_ROOT, "src", "icode")


def _module_defined_names(table: symtable.SymbolTable) -> set[str]:
    """模块作用域里真正定义或导入的名字。"""
    names: set[str] = set()
    for symbol in table.get_symbols():
        if symbol.is_assigned() or symbol.is_imported() or symbol.is_parameter():
            names.add(symbol.get_name())
    return names


def _unresolved_globals(table: symtable.SymbolTable, module_names: set[str],
                        path: str = "") -> list[tuple[str, int]]:
    """收集引用了但解析不到模块级定义的全局名。"""
    out: list[tuple[str, int]] = []
    for symbol in table.get_symbols():
        name = symbol.get_name()
        if symbol.is_global() and not symbol.is_assigned():
            # __file__ / __name__ / __doc__ 等是解释器注入的模块全局，
            # 不在 symtable 的 assigned/imported 集合里，但确实可用。
            if (name in module_names or name in dir(builtins)
                    or name in ("__file__", "__name__", "__doc__", "__package__",
                                "__spec__", "__loader__", "__builtins__", "__debug__")):
                continue
            out.append((f"{path}/{name}", table.get_lineno()))
    for child in table.get_children():
        out += _unresolved_globals(child, module_names, f"{path}/{child.get_name()}")
    return out


class ModuleNameResolutionTests(unittest.TestCase):
    """每个 src/icode 模块的全局名都必须可解析。"""

    def test_all_modules_resolve_their_global_names(self) -> None:
        offenders: list[str] = []
        checked = 0
        for path in sorted(SRC_ROOT.rglob("*.py")):
            if "__pycache__" in str(path):
                continue
            checked += 1
            source = path.read_text(encoding="utf-8")
            try:
                table = symtable.symtable(source, str(path), "exec")
            except SyntaxError as error:  # pragma: no cover - 语法错误另有门禁
                offenders.append(f"{path.relative_to(REPO_ROOT)}: 语法错误 {error}")
                continue
            module_names = _module_defined_names(table)
            for name, lineno in _unresolved_globals(table, module_names):
                offenders.append(
                    f"{path.relative_to(REPO_ROOT)}: {name} (line {lineno})"
                )
        self.assertEqual(
            [], offenders,
            "以下模块引用了未定义的全局名（只在对应平台分支才会触发 NameError）：\n  "
            + "\n  ".join(offenders),
        )
        self.assertGreater(checked, 90, f"只检查了 {checked} 个模块，覆盖面异常")

    def test_extracted_modules_resolve_their_global_names(self) -> None:
        """被搬迁出来的模块单独再查一遍（它们的平台分支最多）。"""
        for name in ("verification_process.py", "runner.py",
                     "orchestration_context.py"):
            path = SRC_ROOT / name
            self.assertTrue(path.is_file(), f"缺少 {name}")
            source = path.read_text(encoding="utf-8")
            table = symtable.symtable(source, str(path), "exec")
            module_names = _module_defined_names(table)
            bad = _unresolved_globals(table, module_names)
            self.assertEqual(
                [], bad,
                f"{name} 引用了未定义的全局名：{bad}",
            )


if __name__ == "__main__":
    unittest.main()
