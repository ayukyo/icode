"""受控多 Agent 的角色契约与身份（R6/W1）。

封闭角色词表（§13.10）。约束：

- 角色是**冻结数据**：能力在定义时固定，运行期没有任何 grant / escalate /
  delegate 入口——子代理不得自行扩大权限，也无法把写能力委派给未知 Agent。
- 只有 executor 可以写；reviewer / verifier / auditor 默认只读。
- 每个 spawn 出的实例拿到稳定身份 ``role#ticket#ordinal``；身份即 operation
  身份的载体（与 `operations.OperationRecorder` 的 scope 纪律对齐）。
- 角色只能产出自己职责内的结论类型（门禁只认角色完成的契约）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

ROLE_PLANNER = "planner"
ROLE_EXECUTOR = "executor"
ROLE_REVIEWER = "reviewer"
ROLE_VERIFIER = "verifier"
ROLE_AUDITOR = "auditor"

ROLES = frozenset({
    ROLE_PLANNER, ROLE_EXECUTOR, ROLE_REVIEWER, ROLE_VERIFIER, ROLE_AUDITOR,
})

# 每个角色唯一可产出的结论类型（门禁按角色核对，不做跨角色顶替）。
ROLE_CONCLUSION_KIND = {
    ROLE_PLANNER: "plan",
    ROLE_EXECUTOR: "execution",
    ROLE_REVIEWER: "review",
    ROLE_VERIFIER: "verification",
    ROLE_AUDITOR: "audit",
}

_TICKET_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_AGENT_ID_RE = re.compile(
    r"^(planner|executor|reviewer|verifier|auditor)#[A-Za-z0-9._-]{1,64}#[0-9]{1,6}$"
)


class RoleError(RuntimeError):
    """角色/身份错误；``code`` 稳定。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True)
class AgentRole:
    """一个角色的能力声明（不可变）。"""

    name: str
    may_write: bool
    conclusions_kind: str
    description: str = ""

    @property
    def may_delegate(self) -> bool:
        """恒为 False：没有任何角色可以把能力转授他人。"""
        return False


_ROLES: dict[str, AgentRole] = {
    ROLE_PLANNER: AgentRole(ROLE_PLANNER, False, ROLE_CONCLUSION_KIND[ROLE_PLANNER],
                            "任务分解与计划"),
    ROLE_EXECUTOR: AgentRole(ROLE_EXECUTOR, True, ROLE_CONCLUSION_KIND[ROLE_EXECUTOR],
                            "在分配写范围内执行实现"),
    ROLE_REVIEWER: AgentRole(ROLE_REVIEWER, False, ROLE_CONCLUSION_KIND[ROLE_REVIEWER],
                             "只读审查，出具审查结论"),
    ROLE_VERIFIER: AgentRole(ROLE_VERIFIER, False,
                             ROLE_CONCLUSION_KIND[ROLE_VERIFIER], "只读验证，出具验证结论"),
    ROLE_AUDITOR: AgentRole(ROLE_AUDITOR, False, ROLE_CONCLUSION_KIND[ROLE_AUDITOR],
                            "只读审计证据链，出具审计结论"),
}


def role(name: object) -> AgentRole:
    """按名取角色；未知角色 fail-closed。"""
    if not isinstance(name, str) or name not in _ROLES:
        raise RoleError("unknown_role", f"未知角色：{name!r}")
    return _ROLES[name]


def roles() -> tuple[AgentRole, ...]:
    return tuple(_ROLES[name] for name in sorted(_ROLES))


def read_only_roles() -> tuple[str, ...]:
    return tuple(sorted(name for name, item in _ROLES.items() if not item.may_write))


@dataclass(frozen=True)
class AgentIdentity:
    """一个 Agent 实例的稳定身份。"""

    agent_id: str
    role: str
    ticket_id: str
    ordinal: int

    def __post_init__(self) -> None:
        prefix, ticket, ordinal = parse_agent_id(self.agent_id)
        role_obj = role(self.role)
        if not isinstance(self.ticket_id, str) or _TICKET_RE.match(self.ticket_id) is None:
            raise RoleError("invalid_ticket", "ticket_id 形态非法")
        if type(self.ordinal) is not int or not 1 <= self.ordinal <= 999999:
            raise RoleError("invalid_ordinal", "ordinal 必须是 1..999999 的整数")
        if prefix != self.role or ticket != self.ticket_id or ordinal != self.ordinal:
            raise RoleError("agent_id_mismatch", "agent_id 与身份字段不一致")
        del role_obj

    @property
    def may_write(self) -> bool:
        return role(self.role).may_write


def is_valid_ticket_id(ticket_id: object) -> bool:
    """工单号形态校验（供编排器复用，避免私有名导入）。"""
    return isinstance(ticket_id, str) and _TICKET_RE.match(ticket_id) is not None


def parse_agent_id(agent_id: object) -> tuple[str, str, int]:
    """校验 agent_id 形态并拆出 (role, ticket_id, ordinal)；不做注册表核对。"""
    if not isinstance(agent_id, str) or _AGENT_ID_RE.match(agent_id) is None:
        raise RoleError("invalid_agent_id", "agent_id 形态非法")
    prefix, ticket, ordinal = agent_id.split("#", 2)
    return prefix, ticket, int(ordinal)


class RoleRegistry:
    """spawn 分配身份；已发放身份只增不改。"""

    def __init__(self) -> None:
        self._identities: dict[str, AgentIdentity] = {}
        self._ordinals: dict[tuple[str, str], int] = {}

    def spawn(self, role_name: object, ticket_id: object) -> AgentIdentity:
        role_obj = role(role_name)
        if not isinstance(ticket_id, str) or _TICKET_RE.match(ticket_id) is None:
            raise RoleError("invalid_ticket", "ticket_id 形态非法")
        key = (role_obj.name, ticket_id)
        ordinal = self._ordinals.get(key, 0) + 1
        self._ordinals[key] = ordinal
        identity = AgentIdentity(
            agent_id=f"{role_obj.name}#{ticket_id}#{ordinal}",
            role=role_obj.name, ticket_id=ticket_id, ordinal=ordinal,
        )
        self._identities[identity.agent_id] = identity
        return identity

    def identity(self, agent_id: object) -> AgentIdentity | None:
        if not isinstance(agent_id, str):
            return None
        return self._identities.get(agent_id)

    def require(self, agent_id: object) -> AgentIdentity:
        identity = self.identity(agent_id)
        if identity is None:
            raise RoleError("unknown_agent", "agent 身份未在本注册表发放")
        return identity

    def assert_may_write(self, identity: AgentIdentity) -> None:
        """写能力校验：只读角色一律拒绝，不降级。"""
        known = self.identity(identity.agent_id) if isinstance(identity, AgentIdentity) else None
        if known is None or known != identity:
            raise RoleError("unknown_agent", "agent 身份未在本注册表发放")
        if not known.may_write:
            raise RoleError("role_write_denied",
                            f"角色 {known.role} 默认只读，不授予写能力")

    def assert_conclusion_kind(self, identity: AgentIdentity, kind: object) -> str:
        """结论类型必须落在角色职责内；跨角色顶替一律拒绝。"""
        known = self.identity(identity.agent_id) if isinstance(identity, AgentIdentity) else None
        if known is None or known != identity:
            raise RoleError("unknown_agent", "agent 身份未在本注册表发放")
        expected = role(known.role).conclusions_kind
        if not isinstance(kind, str) or kind != expected:
            raise RoleError("conclusion_out_of_role",
                            f"角色 {known.role} 只能产出 {expected} 结论")
        return expected
