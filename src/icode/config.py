"""配置解析：定位 icode-skill 源仓 + 密钥安全加载。

安全底线（后续开发不要破坏）：
1. 密钥只存在于进程内存，绝不写入仓内文件、日志、事件链或异常信息。
2. 密钥文件位于仓外；本模块只读取，不复制、不缓存到磁盘。
3. 错误信息只回显脱敏形态（前缀 + 长度）。
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

LOCAL_CONFIG_NAMES = ("icode.local.toml",)

# 子模块默认位置（相对仓库根）
DEFAULT_SUBMODULE_REL = Path("vendor") / "icode-skill"


class ConfigError(RuntimeError):
    """配置缺失或不合法。"""


def repo_root() -> Path:
    """本仓库根目录（src/icode/config.py -> 上三级）。"""
    return Path(__file__).resolve().parents[2]


def _load_local_config() -> dict:
    for name in LOCAL_CONFIG_NAMES:
        p = repo_root() / name
        if p.is_file():
            try:
                with p.open("rb") as fh:
                    return tomllib.load(fh)
            except (OSError, tomllib.TOMLDecodeError):
                return {}
    return {}


@dataclass(frozen=True)
class Settings:
    skill_root: Path
    python: str = sys.executable
    skill_subcommand_timeout: int = 180

    @property
    def control_script(self) -> Path:
        return self.skill_root / "tools" / "icode_control.py"

    @property
    def gates_json(self) -> Path:
        return self.skill_root / "mcp" / "workflow-gate" / "gates.json"

    @property
    def steps_dir(self) -> Path:
        return self.skill_root / "steps"

    def exists(self) -> bool:
        return self.control_script.is_file() and self.gates_json.is_file()


def find_skill_root(explicit: str | os.PathLike[str] | None = None) -> Path:
    """定位 icode-skill 源仓根目录（只读消费，永不修改）。"""
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    env = os.environ.get("ICODE_SKILL_ROOT")
    if env:
        candidates.append(Path(env))
    local = _load_local_config().get("skill_root")
    if local:
        candidates.append(Path(local))
    candidates += [
        repo_root() / DEFAULT_SUBMODULE_REL,
        repo_root().parent / "icode-skill",
        Path.home() / "icode-skill",
    ]
    for c in candidates:
        root = c.expanduser()
        if (root / "tools" / "icode_control.py").is_file():
            return root.resolve()
    raise ConfigError(
        "未找到 icode-skill 源仓（需含 tools/icode_control.py）。"
        "请确认子模块已初始化（git submodule update --init），"
        "或用 --skill-root / ICODE_SKILL_ROOT 指定。"
    )


def mask_secret(secret: str | None) -> str:
    """脱敏：只保留可定位的形态，不泄露可用密钥。"""
    if not secret:
        return "<empty>"
    if len(secret) <= 10:
        return "*" * len(secret)
    return f"{secret[:4]}...{secret[-4:]} (len={len(secret)})"


_KEY_IN_JSON_RE = re.compile(r'"apiKey"\s*:\s*"([^"]+)"')
_KEY_RAW_RE = re.compile(r"\b(sk-[A-Za-z0-9_\-]{16,})\b")


def parse_key_text(text: str) -> str:
    """从密钥文件正文解析密钥。支持 OpenAI 兼容段与裸密钥。"""
    m = _KEY_IN_JSON_RE.search(text)
    if m:
        return m.group(1).strip()
    m = _KEY_RAW_RE.search(text)
    if m:
        return m.group(1).strip()
    stripped = text.strip()
    if stripped and "\n" not in stripped:
        return stripped
    raise ConfigError("无法从密钥文件解析出密钥（未找到 apiKey / sk- 形态）")


def resolve_api_key(key_file: str | os.PathLike[str] | None = None) -> str:
    """解析模型密钥。优先级：显式 key_file > 环境变量 > 本地（gitignore）配置。

    返回值仅供调用方在内存中使用，**不得写入任何文件**。
    """
    local = _load_local_config()
    chosen = key_file or os.environ.get("ICODE_LLM_KEY_FILE") or local.get("key_file")
    if chosen:
        p = Path(chosen).expanduser()
        if not p.is_file():
            raise ConfigError(f"密钥文件不存在：{p}")
        return parse_key_text(p.read_text(encoding="utf-8", errors="replace"))
    env_key = os.environ.get("ICODE_LLM_API_KEY")
    if env_key:
        return env_key.strip()
    raise ConfigError(
        "未提供模型密钥（Phase 1 离线流程不需要密钥）。可选来源：\n"
        "  1) --key-file <仓外密钥文件路径>\n"
        "  2) 环境变量 ICODE_LLM_KEY_FILE=<路径>\n"
        "  3) 环境变量 ICODE_LLM_API_KEY=<密钥>\n"
        "注意：密钥不得写入本仓库任何文件。"
    )


def load_settings(skill_root: str | os.PathLike[str] | None = None) -> Settings:
    return Settings(skill_root=find_skill_root(skill_root))


# ---------------------------------------------------------------------------
# 模型端点代理策略
#
# 默认跟随环境变量（HTTP(S)_PROXY）—— 最不意外，企业代理场景能正常工作。
# 但托管环境常注入内部隧道代理，它对模型端点可能直接 502，
# 因此必须提供显式绕过的开关，而不是让人去猜。
# ---------------------------------------------------------------------------


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def llm_no_proxy() -> bool:
    """是否强制直连：环境变量优先，其次本地（gitignore）配置。"""
    if _env_flag("ICODE_LLM_NO_PROXY"):
        return True
    return bool(_load_local_config().get("no_proxy", False))


def llm_proxy() -> str | None:
    """显式代理地址；未配置则返回 None（意为跟随环境）。"""
    return os.environ.get("ICODE_LLM_PROXY") or _load_local_config().get("proxy") or None


def dump_json(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False)
