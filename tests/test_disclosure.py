"""渐进披露测试：门禁强制注入 + 背景按需加载。

这是成本生死线（roadmap §3 Phase 1），必须可测：
- 强制层存在且受预算约束；
- 全文远大于强制层（证明懒加载确有收益）；
- 章节可按需单独取用。
"""

from __future__ import annotations

import unittest

from tests._support import require_skill

from icode.contracts import ContractSet
from icode.disclosure import DEFAULT_MANDATORY_BUDGET, load_guide, resolve_step_doc, summarize


class TestDisclosure(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = require_skill()
        cls.contracts = ContractSet.load(cls.settings.gates_json)

    def test_步骤文档按实时清单解析_不写死编号(self) -> None:
        path = resolve_step_doc(self.settings.steps_dir, "plan")
        self.assertIsNotNone(path)
        self.assertEqual(path.name, "01_plan.md")
        self.assertIsNone(resolve_step_doc(self.settings.steps_dir, "no_such_step"))

    def test_强制层存在且不超预算(self) -> None:
        guide = load_guide(self.settings.steps_dir, "plan")
        self.assertIsNotNone(guide)
        brief, _truncated = guide.mandatory_brief(self.contracts.step("plan"))
        self.assertTrue(brief.strip())
        self.assertLessEqual(
            len(brief), DEFAULT_MANDATORY_BUDGET,
            "强制层必须受预算约束，否则渐进披露失效",
        )

    def test_强制层包含机器契约要点(self) -> None:
        guide = load_guide(self.settings.steps_dir, "plan")
        brief, _ = guide.mandatory_brief(self.contracts.step("plan"))
        # 机器契约优先级最高：产物端口与复检点必须在简报里完整出现
        for token in ("01_plan.md", "before_write", "before_transition", "漂移回流"):
            self.assertIn(token, brief)

    def test_懒加载确实有收益(self) -> None:
        guide = load_guide(self.settings.steps_dir, "plan")
        st = guide.stats(self.contracts.step("plan"))
        self.assertGreater(st.total_chars, st.mandatory_chars * 3,
                           "步骤文档应远大于强制层，否则渐进披露没有意义")
        self.assertLess(st.ratio, 0.35)

    def test_强制层不重复拼接标题(self) -> None:
        """回归：章节正文本身含标题行，拼接时不得再加一次。"""
        for step in self.contracts.steps():
            guide = load_guide(self.settings.steps_dir, step)
            if guide is None:
                continue
            brief, _ = guide.mandatory_brief(self.contracts.step(step))
            heads = [ln for ln in brief.splitlines() if ln.lstrip().startswith("#")]
            for a, b in zip(heads, heads[1:]):
                self.assertNotEqual(a, b, f"{step} 的门禁简报出现连续重复标题：{a}")

    def test_相对链接被降级为纯文本(self) -> None:
        """回归：简报里的 `../references/x.md` 会诱导模型访问工作区外的文件。

        实测浪费了整轮工具调用（模型连续 3 次尝试读工作区外路径被拒），
        因此简报必须把相对链接降级，并明确声明这些路径不可读。
        """
        from icode.disclosure import neutralize_links

        self.assertEqual(neutralize_links("[依懒检查](../references/a.md)"), "依懒检查")
        self.assertEqual(neutralize_links("[限流](../steps/limit.md)"), "限流")
        # 外链保留（对模型无害）
        self.assertEqual(neutralize_links("[doc](https://example.com/a)"),
                         "[doc](https://example.com/a)")

    def test_简报声明上游路径不可读(self) -> None:
        guide = load_guide(self.settings.steps_dir, "plan")
        brief, _ = guide.mandatory_brief(self.contracts.step("plan"))
        self.assertIn("无法读取", brief)
        self.assertNotIn("](../", brief, "简报中不应残留相对链接")

    def test_章节可按需取用(self) -> None:
        guide = load_guide(self.settings.steps_dir, "plan")
        sections = guide.outline()
        self.assertGreater(len(sections), 3)
        first = sections[0]
        text = guide.section_text(first.title)
        self.assertTrue(text.strip())
        self.assertLessEqual(len(text), first.chars)
        with self.assertRaises(KeyError):
            guide.section_text("__不存在的章节__")

    def test_章节索引不含正文(self) -> None:
        guide = load_guide(self.settings.steps_dir, "plan")
        for section in guide.outline():
            self.assertEqual(len(section.title), len(section.title.strip()))
            self.assertGreater(section.chars, 0)

    def test_全步骤披露统计(self) -> None:
        stats = tuple(
            s for s in (
                (load_guide(self.settings.steps_dir, name) or None)
                for name in self.contracts.steps()
            ) if s is not None
        )
        self.assertTrue(stats)
        for guide in stats:
            st = guide.stats()
            self.assertGreater(st.total_chars, 0)
            self.assertLessEqual(st.mandatory_chars, DEFAULT_MANDATORY_BUDGET)
        self.assertIn("强制注入", summarize([g.stats() for g in stats]))


if __name__ == "__main__":
    unittest.main()
