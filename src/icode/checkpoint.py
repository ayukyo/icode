"""检查点：让被中断的运行可以恢复（Phase 4）。

设计原则（与项目立场一致，不要绕过）：

1. **真源永远是事件链，不是检查点。**
   检查点只是"我走到哪了"的快速标记；若两者冲突，**一律以事件链为准**，
   检查点被丢弃（见 `recovery.py`）。
2. **不保存模型正文。**
   检查点里只有回合计数、工具调用数、历史摘要与未决审批计数 ——
   模型对话内容既不落盘（安全），也不作为证据（审计）。
   恢复时**从事件链重新水合上下文**，而不是回放聊天记录。
3. **原子写。**
   先写临时文件再 `os.replace`，避免崩溃时留下半截检查点。
4. **挂起的审批不因重启而放行。**
   `pending_approvals > 0` 的检查点，恢复后必须重新取得人工确认（fail-closed）。
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

CHECKPOINT_NAME = ".agent_checkpoint.json"
CHECKPOINT_SCHEMA_VERSION = 1


class CheckpointError(RuntimeError):
    """检查点读写失败。"""


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def history_digest(history: list[dict]) -> str:
    """对话历史的摘要（只用于比对"恢复的是不是同一段进程"，不用于还原）。"""
    material = json.dumps(history, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass
class LoopCheckpoint:
    """一次运行的可恢复进度标记。**不含模型正文**。"""

    ticket_id: str
    step: str
    attempt: str
    turn_index: int = 0
    tool_calls: int = 0
    history_digest: str = ""
    pending_approvals: int = 0
    stop_reason: str = ""
    updated_at: str = ""
    schema_version: int = CHECKPOINT_SCHEMA_VERSION
    generator: dict = field(default_factory=dict)
    note: str = "不保存模型正文；恢复时以事件链为准重新水合上下文"

    def as_dict(self) -> dict:
        data = asdict(self)
        data["updated_at"] = self.updated_at or _now()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> LoopCheckpoint:
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


class Checkpointer:
    """工单目录内的检查点读写器。"""

    def __init__(self, out_dir: Path | str, *, ticket_id: str, step: str, attempt: str) -> None:
        self.out_dir = Path(out_dir)
        self.ticket_id = ticket_id
        self.step = step
        self.attempt = attempt
        self.path = self.out_dir / CHECKPOINT_NAME

    # ---- 写 ----

    def save(
        self,
        *,
        turn_index: int,
        tool_calls: int,
        history: list[dict] | None = None,
        pending_approvals: int = 0,
        stop_reason: str = "",
    ) -> LoopCheckpoint:
        from . import __version__

        state = LoopCheckpoint(
            ticket_id=self.ticket_id,
            step=self.step,
            attempt=self.attempt,
            turn_index=turn_index,
            tool_calls=tool_calls,
            history_digest=history_digest(history or []),
            pending_approvals=pending_approvals,
            stop_reason=stop_reason,
            updated_at=_now(),
            generator={"name": "icode-agent", "version": __version__},
        )
        _atomic_write_json(self.path, state.as_dict())
        return state

    # ---- 读 ----

    def load(self) -> LoopCheckpoint | None:
        if not self.path.is_file():
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise CheckpointError(f"检查点不可解析：{exc}") from None
        if not isinstance(data, dict):
            raise CheckpointError("检查点结构异常")
        return LoopCheckpoint.from_dict(data)

    def clear(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

    def exists(self) -> bool:
        return self.path.is_file()


def _atomic_write_json(path: Path, data: dict) -> None:
    """先写 .tmp 再 os.replace —— 崩溃时要么旧文件要么新文件，不会半截。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    tmp.write_bytes(payload.encode("utf-8"))
    os.replace(tmp, path)
