"""人在环（HITL）审批协议（roadmap Phase 2 / B4）。

门禁要求"人工决定"时（工作区外读、白名单外命令、副作用动作），
运行时必须**暂停并显式提示**，由人确认后才继续 —— 而不是自己放行。

三种审批者：
- `DenyAllApprover`    默认。非交互环境下**拒绝**，绝不静默放行。
- `CliApprover`        交互式：打印完整上下文 + 等待显式确认（默认 No）。
- `ScriptedApprover`   测试用：按预设回答序列作答，且**必须显式构造**。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

AFFIRMATIVE = {"y", "yes", "是", "允许", "ok"}


@dataclass(frozen=True)
class ApprovalRequest:
    """一次审批请求的完整上下文（用户据此决定放行还是拒绝）。"""

    tool: str
    arguments: dict
    reason: str
    opclass: str = "read_only"
    workspace: str = ""

    def render(self) -> str:
        lines = [
            "",
            "─" * 66,
            "需要你确认（门禁要求人工决定）",
            f"  工具      : {self.tool}",
            f"  动作类别  : {self.opclass}",
            f"  判定理由  : {self.reason}",
            f"  工作区    : {self.workspace}",
            "  参数      :",
        ]
        for k, v in self.arguments.items():
            text = str(v)
            if len(text) > 400:
                text = text[:400] + " …（截断）"
            lines.append(f"    {k} = {text}")
        lines.append("─" * 66)
        return "\n".join(lines)


@runtime_checkable
class Approver(Protocol):
    def ask(self, request: ApprovalRequest) -> bool: ...


@dataclass
class DenyAllApprover:
    """默认审批者：一律拒绝（非交互环境下的安全默认）。"""

    note: str = "非交互环境：默认拒绝"

    def ask(self, request: ApprovalRequest) -> bool:
        return False


@dataclass
class CliApprover:
    """交互式审批：必须显式输入肯定词，回车默认拒绝。"""

    stream: object = sys.stdout
    prompt: str = "  放行？[y/N] "

    def ask(self, request: ApprovalRequest) -> bool:
        print(request.render(), file=self.stream)
        try:
            answer = input(self.prompt)
        except (EOFError, KeyboardInterrupt):
            print("  （无输入，视为拒绝）", file=self.stream)
            return False
        return answer.strip().lower() in AFFIRMATIVE


@dataclass
class ScriptedApprover:
    """测试用：按预设回答序列作答。

    注意：**必须显式构造**，绝不作为生产默认，避免静默放行。
    """

    answers: list[bool] = field(default_factory=list)
    default: bool = False
    seen: list[ApprovalRequest] = field(default_factory=list)

    def ask(self, request: ApprovalRequest) -> bool:
        self.seen.append(request)
        if not self.answers:
            return self.default
        return self.answers.pop(0)
