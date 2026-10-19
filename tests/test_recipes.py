"""Recipes：只引用既有步骤与已注册 hook，fail-fast，无第二执行路径（R5/W6）。"""

import unittest
from pathlib import Path
from types import SimpleNamespace

from icode.hooks import Hook, HookRegistry
from icode.recipes import Recipe, RecipeError, RecipeRegistry, build_recipe, recipe_plan, run_recipe
from icode.extension_contract import ExtensionManifest
from icode.tools.base import OPCLASS_READ_ONLY


class _HookNames:
    def __init__(self, names) -> None:
        self._names = set(names)

    def names(self):
        return sorted(self._names)


class TestRecipeRegistration(unittest.TestCase):
    def test_引用词表外步骤被拒绝(self) -> None:
        registry = RecipeRegistry(step_vocabulary=("plan", "code"))
        with self.assertRaises(RecipeError) as caught:
            registry.register(build_recipe(name="r", steps=("plan", "audit")))
        self.assertIn("unknown_step", caught.exception.code)

    def test_引用未注册hook被拒绝(self) -> None:
        registry = RecipeRegistry(step_vocabulary=("plan",), hook_registry=_HookNames(("tighten",)))
        recipe = build_recipe(name="r", steps=("plan",), hooks=("ghost",))
        with self.assertRaises(RecipeError) as caught:
            registry.register(recipe)
        self.assertIn("unknown_hook", caught.exception.code)

    def test_manifest类型与同名校验(self) -> None:
        registry = RecipeRegistry(step_vocabulary=("plan",))
        manifest = ExtensionManifest(
            name="other", version="1.0.0", kind="recipe", source="recipe:r",
            opclass=OPCLASS_READ_ONLY, evidence=frozenset({"output_sha256"}),
        )
        with self.assertRaises(RecipeError) as caught:
            registry.register(Recipe(name="r", version="1.0.0", steps=("plan",),
                                    manifest=manifest))
        self.assertEqual(caught.exception.code, "recipe_manifest_name")

    def test_缺manifest或重复注册被拒绝(self) -> None:
        registry = RecipeRegistry(step_vocabulary=("plan",))
        with self.assertRaises(RecipeError) as caught:
            registry.register(Recipe(name="r", version="1.0.0", steps=("plan",)))
        self.assertEqual(caught.exception.code, "recipe_manifest")
        registry.register(build_recipe(name="r", steps=("plan",)))
        with self.assertRaises(RecipeError) as caught:
            registry.register(build_recipe(name="r", steps=("plan",)))
        self.assertEqual(caught.exception.code, "recipe_duplicate")

    def test_步骤重复与超限被拒绝(self) -> None:
        with self.assertRaises(RecipeError):
            build_recipe(name="r", steps=("plan", "plan"))
        with self.assertRaises(RecipeError):
            build_recipe(name="r", steps=tuple(f"s{i}" for i in range(17)))


class TestRecipeExecution(unittest.TestCase):
    def test_计划即声明顺序(self) -> None:
        recipe = build_recipe(name="r", steps=("plan", "code", "review"))
        self.assertEqual(recipe_plan(recipe), ("plan", "code", "review"))

    def test_全部成功按序驱动既有链路(self) -> None:
        registry = RecipeRegistry(step_vocabulary=("plan", "code", "review"))
        recipe = registry.register(build_recipe(name="r", steps=("plan", "code", "review")))
        seen: list[str] = []

        def runner(step: str):
            seen.append(step)
            return SimpleNamespace(ok=True)

        run = run_recipe(recipe, runner)
        self.assertTrue(run.ok)
        self.assertEqual(seen, ["plan", "code", "review"])
        self.assertEqual([o.step for o in run.outcomes], ["plan", "code", "review"])

    def test_中途失败即停且不继续(self) -> None:
        registry = RecipeRegistry(step_vocabulary=("plan", "code", "review"))
        recipe = registry.register(build_recipe(name="r", steps=("plan", "code", "review")))
        seen: list[str] = []

        def runner(step: str):
            seen.append(step)
            return SimpleNamespace(ok=step != "code")

        run = run_recipe(recipe, runner)
        self.assertFalse(run.ok)
        self.assertEqual(seen, ["plan", "code"])
        self.assertEqual(run.refused, "step_failed")

    def test_步骤异常不外泄正文(self) -> None:
        registry = RecipeRegistry(step_vocabulary=("plan",))
        recipe = registry.register(build_recipe(name="r", steps=("plan",)))

        def runner(step: str):
            raise RuntimeError("敏感内部细节")

        run = run_recipe(recipe, runner)
        self.assertFalse(run.ok)
        self.assertEqual(run.refused, "step_failed")

    def test_模块不引入工具旁路(self) -> None:
        source = Path(__file__).resolve().parent.parent.joinpath(
            "src/icode/recipes.py").read_text(encoding="utf-8")
        for literal in ("Tool(", "ToolRegistry", "registry.invoke", "run_command"):
            self.assertNotIn(literal, source,
                             f"recipes.py 不得引入工具执行旁路：{literal}")


if __name__ == "__main__":
    unittest.main()
