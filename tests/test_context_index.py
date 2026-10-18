"""仓库索引与有界上下文选取：大仓库不需要全量注入源码（R4/G3）。"""

from __future__ import annotations

import unittest

from icode.context_index import build_index, select_context
from tests._support import temp_workspace

BODY_MARKER = "BODY_SECRET_SHOULD_NEVER_BE_RENDERED"


class TestContextIndex(unittest.TestCase):
    def setUp(self) -> None:
        self._ws = temp_workspace()
        root = self._ws.__enter__()
        (root / "src").mkdir()
        (root / "src" / "policy.py").write_text(
            "from __future__ import annotations\n\n"
            f"SECRET = {BODY_MARKER!r}\n\n"
            "class PolicyEngine:\n    def evaluate(self, x):\n        return x\n\n"
            "def load_policy(path):\n    return path\n",
            encoding="utf-8",
        )
        (root / "src" / "unrelated.py").write_text(
            "def unrelated_helper():\n    return 1\n", encoding="utf-8",
        )
        (root / "docs").mkdir()
        (root / "docs" / "policy.md").write_text("# policy notes\n", encoding="utf-8")
        (root / ".git").mkdir()
        (root / ".git" / "config.txt").write_text("ignored\n", encoding="utf-8")
        self.root = root

    def tearDown(self) -> None:
        self._ws.__exit__(None, None, None)

    def test_索引只含结构与符号且跳过忽略目录(self) -> None:
        index = build_index(self.root, changed=["src/policy.py"])
        paths = [entry.path for entry in index.files]
        self.assertIn("src/policy.py", paths)
        self.assertNotIn(".git/config.txt", paths)
        names = {symbol.name for symbol in index.symbols}
        self.assertIn("PolicyEngine", names)
        self.assertIn("load_policy", names)
        self.assertEqual(index.changed, ["src/policy.py"])
        policy = next(entry for entry in index.files if entry.path == "src/policy.py")
        self.assertEqual(len(policy.sha256), 64)

    def test_选取落在预算内且不含源码正文(self) -> None:
        index = build_index(self.root, changed=["src/policy.py"])
        selection = select_context(index, query="policy 规则", budget_chars=600)
        self.assertLessEqual(selection.chars, 600)
        self.assertIn("src/policy.py", selection.files)
        self.assertIn("PolicyEngine", selection.text)
        self.assertIn("[changed]", selection.text)
        # 关键不变式：正文标记绝不出现
        self.assertNotIn(BODY_MARKER, selection.text)
        self.assertGreaterEqual(selection.dropped_files, 0)

    def test_关键词命中相关文件且无关文件靠后(self) -> None:
        index = build_index(self.root)
        selection = select_context(index, query="unrelated", budget_chars=400,
                                   limit_files=1)
        self.assertEqual(selection.files, ("src/unrelated.py",))

    def test_非法预算与上限拒绝(self) -> None:
        index = build_index(self.root)
        with self.assertRaises(ValueError):
            select_context(index, query="x", budget_chars=0)
        with self.assertRaises(ValueError):
            select_context(index, query="x", limit_files=0)


if __name__ == "__main__":
    unittest.main()
