"""工具集测试（离线）。"""

from __future__ import annotations

import unittest
from pathlib import Path

from tests._support import temp_workspace

from icode.tools import OPCLASS_MANAGED_WRITE, OPCLASS_READ_ONLY, ToolContext, default_registry


class TestFileTools(unittest.TestCase):
    def setUp(self) -> None:
        self._ws = temp_workspace()
        self.root: Path = self._ws.__enter__()
        (self.root / "pkg").mkdir()
        (self.root / "pkg" / "m.py").write_text(
            "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n",
            encoding="utf-8",
        )
        (self.root / "pkg" / "note.txt").write_text("TODO: 补测试\n", encoding="utf-8")
        self.reg = default_registry()
        self.ctx = ToolContext(root=self.root)

    def tearDown(self) -> None:
        self._ws.__exit__(None, None, None)

    def test_读文件带行号(self) -> None:
        r = self.reg.invoke("read_file", self.ctx, {"path": "pkg/m.py"})
        self.assertTrue(r.ok)
        self.assertIn("1| def add", r.content)
        self.assertEqual(r.meta["total_lines"], 6)

    def test_分段读(self) -> None:
        r = self.reg.invoke("read_file", self.ctx, {"path": "pkg/m.py", "offset": 5, "limit": 2})
        self.assertTrue(r.ok)
        self.assertIn("def sub", r.content)
        self.assertIn("共 6 行", r.content)

    def test_读不存在文件(self) -> None:
        r = self.reg.invoke("read_file", self.ctx, {"path": "nope.py"})
        self.assertFalse(r.ok)
        self.assertEqual(r.meta["error"], "not_found")

    def test_glob(self) -> None:
        r = self.reg.invoke("glob", self.ctx, {"pattern": "**/*.py"})
        self.assertTrue(r.ok)
        self.assertIn("pkg/m.py", r.content)

    def test_grep_返回_file_line(self) -> None:
        r = self.reg.invoke("grep", self.ctx, {"pattern": r"def \w+"})
        self.assertTrue(r.ok)
        self.assertIn("pkg/m.py:1:", r.content)

    def test_grep_非法正则不炸(self) -> None:
        r = self.reg.invoke("grep", self.ctx, {"pattern": "([unclosed"})
        self.assertFalse(r.ok)
        self.assertEqual(r.meta["error"], "bad_regex")

    def test_写文件用LF(self) -> None:
        r = self.reg.invoke("write_file", self.ctx, {"path": "new/a.py", "content": "x = 1\ny = 2\n"})
        self.assertTrue(r.ok)
        self.assertEqual(r.opclass, OPCLASS_MANAGED_WRITE)
        self.assertNotIn(b"\r\n", (self.root / "new" / "a.py").read_bytes())

    def test_edit_要求唯一匹配(self) -> None:
        ok = self.reg.invoke("edit_file", self.ctx, {
            "path": "pkg/m.py", "old": "return a + b", "new": "return a + b  # noqa"})
        self.assertTrue(ok.ok)

        missing = self.reg.invoke("edit_file", self.ctx, {
            "path": "pkg/m.py", "old": "不存在的片段", "new": "x"})
        self.assertFalse(missing.ok)
        self.assertEqual(missing.meta["error"], "no_match")

        ambiguous = self.reg.invoke("edit_file", self.ctx, {
            "path": "pkg/m.py", "old": "def ", "new": "def _"})
        self.assertFalse(ambiguous.ok)
        self.assertEqual(ambiguous.meta["error"], "not_unique")

    def test_未知工具给出可用清单(self) -> None:
        r = self.reg.invoke("rm_rf", self.ctx, {})
        self.assertFalse(r.ok)
        self.assertIn("可用：", r.content)

    def test_参数不合法被兜住(self) -> None:
        r = self.reg.invoke("read_file", self.ctx, {"unexpected": 1})
        self.assertFalse(r.ok)
        self.assertEqual(r.meta["error"], "bad_arguments")

    def test_schema_可用于_function_calling(self) -> None:
        schemas = self.reg.schemas()
        names = {s["function"]["name"] for s in schemas}
        self.assertIn("read_file", names)
        for s in schemas:
            self.assertEqual(s["type"], "function")
            self.assertIn("parameters", s["function"])


class TestRunCommand(unittest.TestCase):
    def setUp(self) -> None:
        self._ws = temp_workspace()
        self.root: Path = self._ws.__enter__()
        self.reg = default_registry()
        self.ctx = ToolContext(root=self.root)

    def tearDown(self) -> None:
        self._ws.__exit__(None, None, None)

    def test_执行并取退出码(self) -> None:
        import sys

        r = self.reg.invoke("run_command", self.ctx, {"argv": [sys.executable, "-c", "print('hi')"]})
        self.assertTrue(r.ok)
        self.assertEqual(r.meta["exit_code"], 0)
        self.assertIn("hi", r.content)

    def test_非零退出码被如实反映(self) -> None:
        import sys

        r = self.reg.invoke("run_command", self.ctx, {"argv": [sys.executable, "-c", "raise SystemExit(3)"]})
        self.assertFalse(r.ok)
        self.assertEqual(r.meta["exit_code"], 3)

    def test_只读命令归类为_read_only(self) -> None:
        r = self.reg.invoke("run_command", self.ctx, {"argv": ["git", "status"]})
        self.assertEqual(r.opclass, OPCLASS_READ_ONLY)

    def test_git_写操作不算只读(self) -> None:
        r = self.reg.invoke("run_command", self.ctx, {"argv": ["git", "commit", "-m", "x"]})
        self.assertEqual(r.opclass, OPCLASS_MANAGED_WRITE)


if __name__ == "__main__":
    unittest.main()
