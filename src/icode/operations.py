"""长动作回执包装：让副作用**不可盲重放**（roadmap Phase 2）。

控制面契约：
- 每个有副作用的动作必须先 `operation --phase start`、执行后 `--phase finish`；
- 同名副作用动作只有 start、没有 finish 时，再次 start 会返回
  `ambiguous_side_effect` —— 此时**必须停止并核对真实状态**，绝不能再执行一次。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .control import ControlPlane


@dataclass(frozen=True)
class StartedOperation:
    name: str
    opclass: str
    attempt: str | None
    ok: bool
    ambiguous: bool
    detail: str = ""

    @property
    def can_execute(self) -> bool:
        """只有拿到 attempt 且不歧义，才允许真正执行副作用。"""
        return self.ok and not self.ambiguous and bool(self.attempt)


class OperationRecorder:
    """把副作用动作包进控制面回执。"""

    def __init__(self, control: ControlPlane, out_dir: Path | str, ticket_id: str) -> None:
        self.control = control
        self.out_dir = Path(out_dir)
        self.ticket_id = ticket_id
        self._counters: dict[str, int] = {}

    def _next_occurrence(self, name: str) -> int:
        self._counters[name] = self._counters.get(name, 0) + 1
        return self._counters[name]

    def start(self, *, name: str, opclass: str, input_desc: str) -> StartedOperation:
        res = self.control.operation_start(
            self.out_dir,
            ticket_id=self.ticket_id,
            name=name,
            opclass=opclass,
            input_desc=input_desc,
            occurrence=self._next_occurrence(name),
        )
        attempt = res.data.get("attempt")
        ambiguous = bool(res.data.get("ambiguous_side_effect")) or (
            str(res.data.get("error", "")).find("ambiguous_side_effect") >= 0
        )
        ok = res.returncode == 0 and res.data.get("ok") is True
        return StartedOperation(
            name=name,
            opclass=opclass,
            attempt=str(attempt) if attempt else None,
            ok=ok,
            ambiguous=ambiguous,
            detail=str(res.data.get("error") or res.data.get("message") or "")[:300],
        )

    def finish(
        self,
        attempt: str,
        *,
        outcome: str,
        evidence: str,
        check_ref: str,
        failure: str | None = None,
    ) -> bool:
        res = self.control.operation_finish(
            self.out_dir,
            attempt=attempt,
            outcome=outcome,
            evidence=evidence[:120],
            check_ref=check_ref[:200],
            failure=failure,
        )
        return res.returncode == 0 and res.data.get("ok") is True
