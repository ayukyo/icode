"""编排层的协作者上下文（P0 参数收敛）。

编排函数此前需要同时接收 20+ 个参数（`_run_agent` 24 参、`run_contract_step`
22 参），导致：

- 编排层**无法在无平台环境构造** → 单元测试只能整块 mock；
- 新增一个协作者要改所有调用点。

本模块把「环境类协作者」与「本次调用载荷」打包为不可变上下文对象，
让编排函数的签名回到可读、可测的规模。

**对外契约不变**：现有 `run_contract_step` / `resume_contract_step` /
`run_task` / `run_chain` 的签名保持逐字段不变（见
`docs/nbl/specs/baseline_signatures.json`），它们内部把实参装配成上下文后
转调上下文版本。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class PreparedCall:
    """prepared（预准备）调用的绑定参数。

    `prepared_step` 与 `prepared_attempt` 必须成对出现，拆成两个独立参数容易
    传错一半，故合并为一个对象。
    """

    step: Any = None
    attempt: Any = None

    @property
    def is_bound(self) -> bool:
        return self.step is not None


@dataclass(frozen=True)
class StepRequest:
    """本次调用的**内容载荷**。

    与 `RunContext` 的区别：这些字段描述「这一次要做什么」，而不是
    「运行环境是什么样」。
    """

    brief: str = ""
    contract: Any = None
    requirement: str = ""
    change_baseline: dict[str, str] | None = None
    operations: Any = None
    prepared_call: PreparedCall | None = None
    extra_instructions: str = ""
    resume_context: str = ""


@dataclass(frozen=True)
class RunContext:
    """编排层共享的**环境类协作者**集合（不可变）。

    字段顺序按「生命周期」排列：后端与审批 → 循环与预算 → 沙箱与策略 →
    工作区 → 记账与观测。
    """

    backend: Any
    approver: Any = None
    loop_config: Any = None
    budget: Any = None
    budget_tracker: Any = None
    on_event: Callable[[str, dict], None] | None = None
    checkpointer: Any = None
    sandbox: Any = None
    policy: Any = None
    workspace_session: Any = None
    inspection_runner: Callable | None = None

    # -- 构造适配器 --------------------------------------------------
    @classmethod
    def from_arguments(
        cls,
        *,
        backend: Any,
        approver: Any = None,
        loop_config: Any = None,
        budget: Any = None,
        on_event: Callable[[str, dict], None] | None = None,
        checkpointer: Any = None,
        resume_context: str = "",
        sandbox: Any = None,
        policy: Any = None,
        change_baseline: dict[str, str] | None = None,
        operations: Any = None,
        budget_tracker: Any = None,
        workspace_session: Any = None,
        inspection_runner: Callable | None = None,
        prepared_step: Any = None,
        prepared_attempt: Any = None,
    ) -> "RunContext":
        """从旧的扁平实参装配上下文。

        这是**兼容外观**到上下文版本的唯一转换点；每个字段必须与传入实参
        严格一致（由 tests/test_orchestration_context.py 断言）。
        """
        return cls(
            backend=backend,
            approver=approver,
            loop_config=loop_config,
            budget=budget,
            budget_tracker=budget_tracker,
            on_event=on_event,
            checkpointer=checkpointer,
            sandbox=sandbox,
            policy=policy,
            workspace_session=workspace_session,
            inspection_runner=inspection_runner,
        )

    @classmethod
    def from_step_request(
        cls, ctx: "RunContext", request: StepRequest
    ) -> "RunContext":
        """返回带上 request 派生字段的上下文副本。

        目前 `resume_context` 属于调用状态而非环境，故留在 `StepRequest`；
        若将来它需要被协作者读取，可在此复制进上下文。
        """
        return ctx


__all__ = ["PreparedCall", "RunContext", "StepRequest"]
