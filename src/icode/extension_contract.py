"""扩展契约：权限、输入、输出、副作用与证据的结构化声明（R5/W1）。

ICODE 创新落地：扩展不是只有工具 schema，还必须携带**可执行权限与证据契约**。
声明不全的扩展默认不可执行（fail-closed）。约束：

- 权限裁定只有一个裁决点（Guard/Approver/治理链）；本契约只描述“扩展声称
  自己要什么”，不自行授予任何权力。
- 契约词表中**不存在**控制面/账本写入授权位：任何 manifest 只要把副作用
  指向控制面/账本产物（事件链、元数据、控制面进程工件）即被拒绝。
- 证据需求复用工程证据的绑定词表（command_sha256 / artifact_hashes_sha256 /
  output_sha256 / exit_code / execution_attempt），调用侧必须挂齐才能落账。
- 所有文本字段有界；所有错误码稳定，供审计与测试断言。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .tools.base import (
    OPCLASS_DESTRUCTIVE,
    OPCLASS_EXTERNAL,
    OPCLASS_MANAGED_WRITE,
    OPCLASS_READ_ONLY,
)

# 与 tools/base.py 同一份四档词表：扩展不得自创权限档位。
OPCLASSES = frozenset({
    OPCLASS_READ_ONLY,
    OPCLASS_MANAGED_WRITE,
    OPCLASS_EXTERNAL,
    OPCLASS_DESTRUCTIVE,
})

# 副作用类型词表：只允许这三类“可审计”的副作用；控制面/账本写入不在词表内，
# 因此结构性不可声明——不需要在运行时再依赖自觉。
SIDE_EFFECT_FILE_WRITE = "file_write"
SIDE_EFFECT_NETWORK = "network"
SIDE_EFFECT_PROCESS = "process"
SIDE_EFFECT_KINDS = frozenset({
    SIDE_EFFECT_FILE_WRITE, SIDE_EFFECT_NETWORK, SIDE_EFFECT_PROCESS,
})

# 证据绑定词表：与 engineering_evidence._public_binding 的字段同名，方便同一套
# 校验复用。execution_attempt 是身份字段，始终由调用侧注入而非扩展自报。
EVIDENCE_FIELDS = frozenset({
    "command_sha256",
    "artifact_hashes_sha256",
    "output_sha256",
    "exit_code",
    "execution_attempt",
})

# 控制面/账本产物特征：manifest 的副作用只要命中即拒绝（读授权同样拒绝：
# 扩展不需要直接读账本，事实投影由公开投影通道提供）。
_CONTROL_PLANE_MARKERS = (
    ".ico_events.jsonl",
    ".ico_metadata.json",
    ".icode_output_",
    ".git/AI-HANDOFF",
    "gates.json",
)

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_VERSION_RE = re.compile(r"^[0-9][0-9A-Za-z.+-]{0,31}$")
# 作用域模式：工作区相对、无绝对路径、无父目录逃逸、无家目录。
_PATTERN_RE = re.compile(r"^[A-Za-z0-9._*?/\[\]-]+$")

_MAX_DESCRIPTION = 500
_MAX_SOURCE = 256
_MAX_SIDE_EFFECTS = 16
_MAX_PATTERN = 200
_MAX_EVIDENCE = len(EVIDENCE_FIELDS)


class ContractError(ValueError):
    """扩展契约非法；错误码稳定，不随实现漂移。"""


def _text(value: object, code: str, *, maximum: int) -> str:
    if not isinstance(value, str) or not value:
        raise ContractError(f"{code}: 必须为非空字符串")
    if len(value) > maximum:
        raise ContractError(f"{code}: 超过 {maximum} 字符上限")
    return value


def _is_control_plane_target(pattern: str) -> bool:
    normalized = pattern.replace("\\", "/")
    return any(marker in normalized for marker in _CONTROL_PLANE_MARKERS)


def _validate_pattern(value: object, code: str) -> str:
    pattern = _text(value, code, maximum=_MAX_PATTERN)
    if pattern.startswith("/") or pattern.startswith("~") or re.match(r"^[A-Za-z]:", pattern):
        raise ContractError(f"{code}: 必须是工作区相对路径，拒绝绝对路径")
    if ".." in pattern.split("/"):
        raise ContractError(f"{code}: 拒绝父目录逃逸")
    if _PATTERN_RE.match(pattern) is None:
        raise ContractError(f"{code}: 含非法字符")
    if _is_control_plane_target(pattern):
        raise ContractError(f"{code}: 控制面/账本不是可声明目标")
    return pattern


@dataclass(frozen=True)
class SideEffect:
    """一条显式副作用声明：类型 + 有界目标模式。"""

    kind: str
    target: str

    def __post_init__(self) -> None:
        if self.kind not in SIDE_EFFECT_KINDS:
            raise ContractError(f"manifest_unknown_side_effect: {self.kind!r}")
        if self.kind == SIDE_EFFECT_NETWORK:
            target = _text(self.target, "manifest_side_effect_target", maximum=_MAX_PATTERN)
            if any(ch in target for ch in " \t/\\"):
                raise ContractError("manifest_side_effect_target: 网络目标只接受域名特征")
        else:
            target = _validate_pattern(self.target, "manifest_side_effect_target")

    def as_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "target": self.target}


@dataclass(frozen=True)
class ExtensionManifest:
    """扩展清单：名称/版本/来源 + 权限/输入/输出/副作用/证据五段声明。"""

    name: str
    version: str
    kind: str
    source: str
    opclass: str
    description: str = ""
    inputs: Mapping[str, Any] = field(default_factory=dict)
    outputs: Mapping[str, Any] = field(default_factory=dict)
    side_effects: tuple[SideEffect, ...] = ()
    evidence: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        name = _text(self.name, "manifest_name", maximum=64)
        if _NAME_RE.match(name) is None:
            raise ContractError("manifest_invalid_name: 只允许小写字母数字与 . _ -")
        version = _text(self.version, "manifest_version", maximum=32)
        if _VERSION_RE.match(version) is None:
            raise ContractError("manifest_invalid_version")
        kind = _text(self.kind, "manifest_kind", maximum=32)
        if kind not in EXTENSION_KINDS:
            raise ContractError(f"manifest_unknown_kind: {kind!r}")
        _text(self.source, "manifest_source", maximum=_MAX_SOURCE)
        description = _text(self.description, "manifest_description", maximum=_MAX_DESCRIPTION) \
            if self.description else ""
        opclass = _text(self.opclass, "manifest_opclass", maximum=32)
        if opclass not in OPCLASSES:
            raise ContractError(f"manifest_unknown_opclass: {opclass!r}")
        if not isinstance(self.inputs, Mapping):
            raise ContractError("manifest_inputs: 必须是对象")
        if not isinstance(self.outputs, Mapping):
            raise ContractError("manifest_outputs: 必须是对象")
        effects = tuple(self.side_effects)
        if len(effects) > _MAX_SIDE_EFFECTS:
            raise ContractError("manifest_side_effects: 超出 16 条上限")
        evidence = frozenset(self.evidence)
        if not evidence:
            # G4：未声明证据要求的扩展默认不可执行。
            raise ContractError("manifest_evidence_empty: 至少声明一个证据字段")
        if len(evidence) > _MAX_EVIDENCE:
            raise ContractError("manifest_evidence: 超出词表范围")
        unknown = sorted(evidence - EVIDENCE_FIELDS)
        if unknown:
            raise ContractError(f"manifest_unknown_evidence: {unknown}")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "description", description)
        object.__setattr__(self, "opclass", opclass)
        object.__setattr__(self, "side_effects", effects)
        object.__setattr__(self, "evidence", evidence)

    def as_dict(self) -> dict[str, Any]:
        """公开投影：只含声明本身，不含任何凭据或目标全文之外的运行数据。"""
        return {
            "name": self.name,
            "version": self.version,
            "kind": self.kind,
            "source": self.source,
            "opclass": self.opclass,
            "description": self.description,
            "inputs": dict(self.inputs),
            "outputs": dict(self.outputs),
            "side_effects": [effect.as_dict() for effect in self.side_effects],
            "evidence": sorted(self.evidence),
        }


EXTENSION_KINDS = frozenset({"tool", "connector", "hook", "recipe"})


class ExtensionRegistry:
    """扩展注册表：注册即校验；只有通过校验的扩展才可执行。"""

    def __init__(self) -> None:
        self._manifests: dict[str, ExtensionManifest] = {}

    def register(self, manifest: ExtensionManifest) -> ExtensionManifest:
        if not isinstance(manifest, ExtensionManifest):
            raise ContractError("manifest_type: 需要 ExtensionManifest")
        if manifest.name in self._manifests:
            raise ContractError(f"manifest_duplicate: {manifest.name}")
        self._manifests[manifest.name] = manifest
        return manifest

    def get(self, name: str) -> ExtensionManifest | None:
        return self._manifests.get(name)

    def names(self) -> list[str]:
        return sorted(self._manifests)

    def manifests(self) -> list[ExtensionManifest]:
        return [self._manifests[name] for name in self.names()]

    def assert_executable(self, name: str) -> ExtensionManifest:
        """调用点守卫：未注册（即未通过契约校验）的扩展不可执行。"""
        manifest = self._manifests.get(name)
        if manifest is None:
            raise ContractError(f"extension_not_registered: {name}")
        return manifest


def attach_evidence(
    manifest: ExtensionManifest, binding: Mapping[str, Any],
) -> dict[str, Any]:
    """校验调用侧证据绑定满足 manifest 的证据需求；缺项一律拒绝落账。

    `binding` 由调用侧（治理链/连接器）提供，字段名与工程证据绑定词表一致。
    """
    if not isinstance(manifest, ExtensionManifest):
        raise ContractError("manifest_type: 需要 ExtensionManifest")
    if not isinstance(binding, Mapping):
        raise ContractError("evidence_binding: 必须是对象")
    missing = sorted(
        name for name in manifest.evidence
        if name not in binding or binding[name] in (None, "")
    )
    if missing:
        raise ContractError(f"evidence_incomplete: {missing}")
    return {name: binding[name] for name in sorted(manifest.evidence)}


def tighten_guard_scope(
    base_deny: Iterable[str], base_allow: Iterable[str],
    candidate_deny: Iterable[str], candidate_allow: Iterable[str],
) -> tuple[frozenset[str], frozenset[str]]:
    """应用 Guard 侧收紧：返回 (deny, allow)；任何放宽都抛 ContractError。"""
    base_deny_set, base_allow_set = frozenset(base_deny), frozenset(base_allow)
    deny, allow = frozenset(candidate_deny), frozenset(candidate_allow)
    if not base_deny_set <= deny:
        raise ContractError("guard_tightening_removes_deny: 收紧不得移除既有拒绝")
    if not allow <= base_allow_set:
        raise ContractError("guard_tightening_expands_allowlist: 收紧不得扩张白名单")
    return deny, allow
