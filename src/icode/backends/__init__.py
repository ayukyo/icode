"""模型后端。core 零依赖；真模型后端用标准库实现。"""

from .anthropic import AnthropicBackend
from .base import AssistantMessage, Backend, ToolCall, strip_think
from .fake import FakeBackend
from .gemini import GeminiBackend
from .ollama import OllamaBackend
from .openai_compatible import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    BackendError,
    OpenAICompatibleBackend,
    Usage,
    build_backend,
)

__all__ = [
    "AnthropicBackend",
    "AssistantMessage",
    "Backend",
    "BackendError",
    "DEFAULT_BASE_URL",
    "DEFAULT_MODEL",
    "FakeBackend",
    "GeminiBackend",
    "OllamaBackend",
    "OpenAICompatibleBackend",
    "ToolCall",
    "Usage",
    "build_backend",
    "strip_think",
]
