"""代理结论账本（R6/W4）：身份 + 上下文边界 + 证据，缺一不可入账。

- ``completed`` 结论必须携带非空证据（字段名沿用工程证据绑定词表或调用方
  声明的有界键值）；``failed`` / ``refused`` 结论以稳定失败码为内容——身份、
  上下文边界与失败码仍然完整可追溯，但不存在的工作产物不伪造证据。
- ``context_digest`` 由编排器从真实策略/作用域计算（`agent_scope` 的
  ``policy_hash`` / ``scope_fingerprint``），不是 agent 自报。
- 账本只增有界：写满即拒绝新结论（fail-closed），不静默淘汰。
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass, field
from typing import Any, Mapping

from .roles import parse_agent_id, role as _role

_OUTCOMES = frozenset({"completed", "failed", "refused"})
_MAX_STEP = 64
_MAX_KIND = 64
_MAX_DETAIL = 200
_MAX_EVIDENCE_JSON = 4096
_DEFAULT_LIMIT = 256


class ConclusionError(RuntimeError):
    """结论错误；``code`` 稳定。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def _bounded_evidence(evidence: object) -> dict[str, Any]:
    if not isinstance(evidence, Mapping) or not evidence:
        raise ConclusionError("evidence_missing", "completed 结论必须携带非空证据")
    bounded: dict[str, Any] = {}
    for key, value in evidence.items():
        if not isinstance(key, str) or not key or len(key) > 32:
            raise ConclusionError("evidence_invalid", "证据键必须为 1..32 字符")
        if isinstance(value, (str, int, float, bool)) or value is None:
            bounded[key] = value
        else:
            raise ConclusionError("evidence_invalid", "证据值必须是标量")
    encoded = json.dumps(bounded, ensure_ascii=False, sort_keys=True)
    if len(encoded) > _MAX_EVIDENCE_JSON:
        raise ConclusionError("evidence_invalid", "证据超过 4096 字节上限")
    return bounded


def _conclusion_digest(fields: Mapping[str, Any]) -> str:
    encoded = json.dumps(fields, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AgentConclusion:
    """一条代理结论：身份、上下文边界、结论类型与证据/失败码。"""

    agent_id: str
    role: str
    ticket_id: str
    step: str
    kind: str
    context_digest: str
    outcome: str
    evidence: Mapping[str, Any] = field(default_factory=dict)
    detail: str = ""
    digest: str = field(default="", compare=False)

    def __post_init__(self) -> None:
        prefix, ticket, _ordinal = parse_agent_id(self.agent_id)
        role_obj = _role(self.role)
        if prefix != self.role or ticket != self.ticket_id:
            raise ConclusionError("agent_id_mismatch", "agent_id 与身份字段不一致")
        if not isinstance(self.ticket_id, str) or not self.ticket_id:
            raise ConclusionError("invalid_ticket", "ticket_id 必须为非空字符串")
        if not isinstance(self.step, str) or not self.step or len(self.step) > _MAX_STEP:
            raise ConclusionError("invalid_step", "step 必须为 1..64 字符")
        if not isinstance(self.kind, str) or not self.kind or len(self.kind) > _MAX_KIND:
            raise ConclusionError("invalid_kind", "kind 必须为 1..64 字符")
        if self.kind != role_obj.conclusions_kind:
            raise ConclusionError("conclusion_out_of_role",
                                  f"角色 {self.role} 只能产出 {role_obj.conclusions_kind} 结论")
        if (not isinstance(self.context_digest, str)
                or len(self.context_digest) != 64
                or any(ch not in "0123456789abcdef" for ch in self.context_digest)):
            raise ConclusionError("invalid_context_digest", "context_digest 必须是 sha256 hex")
        if self.outcome not in _OUTCOMES:
            raise ConclusionError("invalid_outcome", f"未知结论状态 {self.outcome!r}")
        if self.outcome == "completed":
            object.__setattr__(self, "evidence", _bounded_evidence(self.evidence))
        else:
            object.__setattr__(self, "evidence", {})
            if not isinstance(self.detail, str) or not self.detail:
                raise ConclusionError("detail_missing",
                                      "failed/refused 结论必须携带稳定失败码")
        if len(self.detail) > _MAX_DETAIL:
            raise ConclusionError("detail_oversize", "detail 超过 200 字符上限")
        fields = {
            "agent_id": self.agent_id, "role": self.role,
            "ticket_id": self.ticket_id, "step": self.step, "kind": self.kind,
            "context_digest": self.context_digest, "outcome": self.outcome,
            "evidence": dict(self.evidence), "detail": self.detail,
        }
        object.__setattr__(self, "digest", _conclusion_digest(fields))

    def project(self) -> dict[str, Any]:
        """公开投影：只含稳定字段，不含任何工作产物正文。"""
        return {
            "agent_id": self.agent_id, "role": self.role,
            "ticket_id": self.ticket_id, "step": self.step, "kind": self.kind,
            "context_digest": self.context_digest, "outcome": self.outcome,
            "evidence": dict(self.evidence), "detail": self.detail,
            "digest": self.digest,
        }


class ConclusionLedger:
    """只增有界结论账本；线程安全（编排器并行写入）。"""

    def __init__(self, limit: int = _DEFAULT_LIMIT) -> None:
        if type(limit) is not int or not 1 <= limit <= 4096:
            raise ConclusionError("invalid_limit", "limit 必须是 1..4096 的整数")
        self._limit = limit
        self._lock = threading.Lock()
        self._conclusions: list[AgentConclusion] = []
        self._digests: set[str] = set()

    def record(self, conclusion: object) -> str:
        if not isinstance(conclusion, AgentConclusion):
            raise ConclusionError("invalid_conclusion", "需要 AgentConclusion")
        with self._lock:
            if conclusion.digest in self._digests:
                return conclusion.digest  # 幂等重录
            if len(self._conclusions) >= self._limit:
                raise ConclusionError("ledger_full", "结论账本已满（fail-closed）")
            self._conclusions.append(conclusion)
            self._digests.add(conclusion.digest)
            return conclusion.digest

    def conclusions(self) -> tuple[AgentConclusion, ...]:
        with self._lock:
            return tuple(self._conclusions)

    def project(self) -> list[dict[str, Any]]:
        with self._lock:
            return [item.project() for item in self._conclusions]

    def has_completed(self, role_name: object, kind: object, step: object) -> bool:
        if not isinstance(role_name, str) or not isinstance(kind, str) \
                or not isinstance(step, str):
            return False
        with self._lock:
            return any(
                item.role == role_name and item.kind == kind
                and item.step == step and item.outcome == "completed"
                for item in self._conclusions
            )
