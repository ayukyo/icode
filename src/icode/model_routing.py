"""按步骤/能力选择模型后端（R4/W4）。

约束：路由是**纯选择**——只决定构造哪个后端与哪个模型名，不写工单、不写
事件链、不改门禁；状态真源始终是控制面。路由表来自显式配置/环境变量，
解析结果不可变，重复解析结果一致。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Mapping

READ_ONLY_STEPS = frozenset({"review", "deepcheck"})


class RouteError(RuntimeError):
    """步骤路由配置非法或后端构造失败；失败封闭，不回落到其他模型。"""
DEFAULT_BACKEND = "openai-compatible"


@dataclass(frozen=True)
class ModelRoute:
    step: str
    backend: str
    model: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.step, str) or not self.step:
            raise ValueError("route step 必须为非空字符串")
        if not isinstance(self.backend, str) or not self.backend:
            raise ValueError("route backend 必须为非空字符串")


def route_table(env: Mapping[str, str] | None = None) -> dict[str, ModelRoute]:
    """读取 `ICODE_MODEL_ROUTE_<STEP>=backend[:model]`；非法项忽略。"""
    source = os.environ if env is None else env
    table: dict[str, ModelRoute] = {}
    for key, value in source.items():
        if not isinstance(key, str) or not key.startswith("ICODE_MODEL_ROUTE_"):
            continue
        if not isinstance(value, str) or not value.strip():
            continue
        step = key[len("ICODE_MODEL_ROUTE_"):].strip().lower().replace("_", "-")
        if not step:
            continue
        backend, _, model = value.strip().partition(":")
        if not backend.strip():
            continue
        table[step] = ModelRoute(step=step, backend=backend.strip(), model=model.strip())
    return table


def resolve_route(
    step: str,
    *,
    table: Mapping[str, ModelRoute] | None = None,
    default_backend: str = DEFAULT_BACKEND,
    default_model: str = "",
) -> ModelRoute:
    """解析步骤路由：显式 > 只读步骤默认 > 全局默认；纯函数，不读文件。"""
    if not isinstance(step, str) or not step:
        raise ValueError("step 必须为非空字符串")
    routes = dict(table or {})
    if step in routes:
        return routes[step]
    if step in READ_ONLY_STEPS and "review" in routes:
        return ModelRoute(step=step, backend=routes["review"].backend,
                          model=routes["review"].model)
    return ModelRoute(step=step, backend=default_backend, model=default_model)


def apply_route(route: ModelRoute, *,
                builder: Callable[[str, str], object]) -> object:
    """用调用方给的构造器实例化后端；只做一次装配，不保存任何状态。"""
    if not isinstance(route, ModelRoute):
        raise TypeError("apply_route 需要 ModelRoute")
    return builder(route.backend, route.model)
