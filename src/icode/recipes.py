"""Skills / Recipes：声明式组合，不新增执行旁路（R5/W6）。

v1 范围：

- **Recipe** 是声明式组合：只引用**既有步骤**（``ContractSet.steps()`` 词表）
  与**已注册 hook**；recipe 自己不引入工具、不执行动作——执行仍走既有
  ``run_contract_step`` 链路，recipe 只是把顺序与引用固定成可审计工件。
- **Skills** 不新增机制：skill 的发现与暂存继续走既有
  ``config.find_skill_root`` / ``skill_resources`` 白名单流程（见测试对
  该流程的引用），本模块不得旁路。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping

from .extension_contract import ExtensionManifest, ExtensionRegistry
from .tools.base import OPCLASS_READ_ONLY

_MAX_STEPS = 16
_MAX_HOOKS = 8


class RecipeError(RuntimeError):
    """recipe 错误；``code`` 稳定。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True)
class Recipe:
    """一个声明式组合工件。"""

    name: str
    version: str
    steps: tuple[str, ...]
    description: str = ""
    hooks: tuple[str, ...] = ()
    manifest: ExtensionManifest | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise RecipeError("recipe_name", "name 必须为非空字符串")
        if len(self.name) > 64:
            raise RecipeError("recipe_name", "name 过长")
        if not isinstance(self.steps, tuple) or not self.steps:
            raise RecipeError("recipe_steps", "steps 必须为非空元组")
        if len(self.steps) > _MAX_STEPS:
            raise RecipeError("recipe_steps", "steps 超出 16 步上限")
        if len(set(self.steps)) != len(self.steps):
            raise RecipeError("recipe_steps", "steps 不得重复")
        if len(self.hooks) > _MAX_HOOKS:
            raise RecipeError("recipe_hooks", "hooks 超出 8 个上限")
        if len(set(self.hooks)) != len(self.hooks):
            raise RecipeError("recipe_hooks", "hooks 不得重复")
        if len(self.description) > 500:
            raise RecipeError("recipe_description", "description 过长")


@dataclass(frozen=True)
class RecipeStepOutcome:
    step: str
    ok: bool


@dataclass(frozen=True)
class RecipeRun:
    """一次 recipe 执行的有界结果。"""

    recipe: str
    ok: bool
    outcomes: tuple[RecipeStepOutcome, ...] = ()
    refused: str = ""


class RecipeRegistry:
    """注册表：recipe 只能引用既有步骤词表与已注册 hook。"""

    def __init__(
        self,
        step_vocabulary: Iterable[str] = (),
        hook_registry: Any | None = None,
    ) -> None:
        self._steps = frozenset(step_vocabulary)
        self._hooks = hook_registry
        self._manifests = ExtensionRegistry()
        self._recipes: dict[str, Recipe] = {}

    def register(self, recipe: Recipe) -> Recipe:
        if not isinstance(recipe, Recipe):
            raise RecipeError("recipe_type", "需要 Recipe")
        manifest = recipe.manifest
        if manifest is None:
            raise RecipeError("recipe_manifest", "recipe 必须携带 manifest")
        if manifest.kind != "recipe":
            raise RecipeError("recipe_manifest_kind", "manifest 类型必须是 recipe")
        if manifest.name != recipe.name:
            raise RecipeError("recipe_manifest_name", "manifest 与 recipe 不同名")
        unknown_steps = sorted(set(recipe.steps) - self._steps)
        if unknown_steps:
            raise RecipeError("unknown_step", f"词表外步骤：{unknown_steps}")
        if self._hooks is not None:
            registered = set(self._hooks.names())
            unknown_hooks = sorted(set(recipe.hooks) - registered)
            if unknown_hooks:
                raise RecipeError("unknown_hook", f"未注册 hook：{unknown_hooks}")
        if recipe.name in self._recipes:
            raise RecipeError("recipe_duplicate", recipe.name)
        self._manifests.register(manifest)
        self._recipes[recipe.name] = recipe
        return recipe

    def get(self, name: str) -> Recipe | None:
        return self._recipes.get(name)

    def names(self) -> list[str]:
        return sorted(self._recipes)


def recipe_plan(recipe: Recipe) -> tuple[str, ...]:
    """纯函数：执行计划即声明顺序（不重排、不补步）。"""
    if not isinstance(recipe, Recipe):
        raise RecipeError("recipe_type", "需要 Recipe")
    return tuple(recipe.steps)


def run_recipe(
    recipe: Recipe,
    step_runner: Callable[[str], Any],
) -> RecipeRun:
    """按声明顺序驱动既有步骤链路；任一步失败即停（fail-fast）。

    ``step_runner`` 在生产中包住 ``run_contract_step``——recipe 不创建第二条
    执行路径，也不直接触碰工具处理器。
    """
    if not isinstance(recipe, Recipe):
        raise RecipeError("recipe_type", "需要 Recipe")
    if not callable(step_runner):
        raise RecipeError("recipe_runner", "step_runner 必须可调用")
    outcomes: list[RecipeStepOutcome] = []
    for step in recipe_plan(recipe):
        try:
            result = step_runner(step)
        except Exception:  # noqa: BLE001 - 步骤异常不外泄正文
            outcomes.append(RecipeStepOutcome(step=step, ok=False))
            return RecipeRun(recipe=recipe.name, ok=False,
                             outcomes=tuple(outcomes), refused="step_failed")
        ok = getattr(result, "ok", None)
        if ok is None and isinstance(result, Mapping):
            ok = result.get("ok")
        outcomes.append(RecipeStepOutcome(step=step, ok=bool(ok)))
        if not ok:
            return RecipeRun(recipe=recipe.name, ok=False,
                             outcomes=tuple(outcomes), refused="step_failed")
    return RecipeRun(recipe=recipe.name, ok=True, outcomes=tuple(outcomes))


def build_recipe(
    *,
    name: str,
    steps: tuple[str, ...],
    hooks: tuple[str, ...] = (),
    description: str = "",
) -> Recipe:
    """组装携带 manifest 的 recipe（recipe 自身只读、必须声明证据）。"""
    manifest = ExtensionManifest(
        name=name, version="1.0.0", kind="recipe",
        source=f"recipe:{name}"[:256], opclass=OPCLASS_READ_ONLY,
        description=description[:500],
        side_effects=(),
        evidence=frozenset({"output_sha256"}),
    )
    return Recipe(name=name, version="1.0.0", steps=steps,
                  description=description[:500], hooks=hooks, manifest=manifest)
