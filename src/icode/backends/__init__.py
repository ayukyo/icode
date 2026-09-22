"""模型后端。Phase 1 仅提供离线 FakeBackend。"""

from .base import AssistantMessage, Backend, ToolCall, strip_think
from .fake import FakeBackend

__all__ = ["AssistantMessage", "Backend", "FakeBackend", "ToolCall", "strip_think"]
