"""契约层测试：gates.json 动态读取 + 与 steps/ 的交叉校验。"""

from __future__ import annotations

import unittest

from tests._support import require_skill

from icode.contracts import ContractError, ContractSet, check_steps_alignment


class TestContractSet(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = require_skill()
        cls.contracts = ContractSet.load(cls.settings.gates_json)

    def test_步骤表来自契约而非写死(self) -> None:
        steps = self.contracts.steps()
        self.assertGreater(len(steps), 0)
        for expected in ("plan", "review", "code", "deepcheck", "audit"):
            self.assertIn(expected, steps)

    def test_plan_契约的产物与复检点(self) -> None:
        plan = self.contracts.step("plan")
        outputs = {p.value for p in plan.outputs}
        self.assertIn("01_plan.md", outputs)
        self.assertEqual(list(plan.required_checks), ["before_write", "before_transition"])
        self.assertTrue(any(p.required for p in plan.required_inputs))

    def test_受保护输入可识别(self) -> None:
        plan = self.contracts.step("plan")
        self.assertTrue(plan.protected_inputs, "plan 应存在受保护输入（漂移即 fail-closed）")

    def test_漂移回流有默认路由(self) -> None:
        plan = self.contracts.step("plan")
        self.assertEqual(plan.route_for("不存在的输入"), "plan")

    def test_边界与分类枚举(self) -> None:
        self.assertEqual(
            set(self.contracts.boundaries()),
            {"before_write", "after_wait", "before_side_effect", "before_transition"},
        )
        self.assertEqual(len(self.contracts.operation_classes()), 4)
        self.assertEqual(len(self.contracts.failure_policies()), 6)

    def test_未知步骤抛错且提示已登记(self) -> None:
        with self.assertRaises(ContractError) as ctx:
            self.contracts.step("no_such_step")
        self.assertIn("已登记", str(ctx.exception))

    def test_契约与步骤文档一致性(self) -> None:
        issues = check_steps_alignment(self.contracts, self.settings.steps_dir)
        self.assertIsInstance(issues, tuple)
        # 反向缺失（契约有、文档无）不应出现：每个登记步骤都必须有文档
        missing_docs = [i for i in issues if i.kind == "contract_without_doc"]
        self.assertEqual(missing_docs, [], f"契约登记的步骤缺少 steps/ 文档：{missing_docs}")

    def test_契约文件缺失时抛出明确错误(self) -> None:
        with self.assertRaises(ContractError):
            ContractSet.load(self.settings.gates_json.parent / "__not_exist__.json")


if __name__ == "__main__":
    unittest.main()
