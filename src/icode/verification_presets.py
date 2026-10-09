"""Explicit host-owned verification presets, never project command configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from .config import ConfigError
from .engineering_verification import VerificationCheck, VerificationPlan, _executable_identity
from .sandbox_policy import SandboxPolicy

if TYPE_CHECKING:
    from .autonomy import ExecutionContext


@dataclass(frozen=True)
class PythonUnittestPlanProvider:
    executable: Path
    _startup_identity: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        # Keep the lexical venv launcher: resolving argv0 can select base Python.
        if not isinstance(self.executable, Path) or not self.executable.is_absolute():
            raise ConfigError("Python unittest 预设解释器不可用")
        try:
            identity = _executable_identity(self.executable)
        except (OSError, RuntimeError, ValueError):
            raise ConfigError("Python unittest 预设解释器不可用") from None
        object.__setattr__(self, "_startup_identity", identity)

    def __call__(self, context: ExecutionContext, policy: SandboxPolicy) -> VerificationPlan:
        if not isinstance(policy, SandboxPolicy) or policy.step not in ("code", "deepcheck"):
            raise ValueError("invalid Python preset policy")
        root = context.workspace.resolve(strict=True)
        if (
            policy.workspace_root != root
            or policy.workspace_root != policy.workspace_root.resolve(strict=True)
            or policy.ticket_id != context.ticket_id
        ):
            raise ValueError("Python preset identity mismatch")
        if _executable_identity(self.executable) != self._startup_identity:
            raise ValueError("Python preset executable changed")
        check = VerificationCheck(
            check_id="python-unittest",
            kind="test",
            adapter="unittest_summary_v1",
            cwd=".",
            required=True,
            argv=(
                str(self.executable), "-I", "-B", "-X", "utf8", "-m", "unittest",
                "discover", "-s", str(root), "-t", str(root),
            ),
        )
        # Check observes the executable again; a construction-window swap fails.
        if check.executable_identity != self._startup_identity:
            raise ValueError("Python preset executable changed")
        return VerificationPlan(
            workspace_root=root,
            run_id=policy.run_id,
            ticket_id=context.ticket_id,
            checks=(check,),
            steps=("code", "deepcheck"),
        )
