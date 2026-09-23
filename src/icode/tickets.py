"""单工程工单目录与受控建单意图。

浏览器只接触不透明项目/工单标识和业务字段。目录分配、metadata 与事件链写入
全部交给固定版本的 ICODE-SKILL 控制面；本模块只读取并生成公开投影。
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import Settings
from .control import ControlPlane

SUPPORTED_LOCALES = frozenset({"zh-CN", "en-US"})
EXECUTION_MODES = frozenset({"interactive", "autonomous"})
PRIORITIES = frozenset({"low", "normal", "high", "urgent"})
CREATE_TICKET_FIELDS = frozenset({
    "project_id",
    "title",
    "description",
    "expected_result",
    "priority",
    "locale",
    "execution_mode",
    "request_id",
})

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,140}$")
_OUT_DIR_RE = re.compile(r"^\.icode_output_([0-9]+)$")
_METADATA_READ_ATTEMPTS = 5
_METADATA_READ_RETRY_SECONDS = 0.01

AUTONOMOUS_RUN_STATES = frozenset({
    "pending",
    "starting",
    "running",
    "pause_requested",
    "paused",
    "cancel_requested",
    "cancelled",
    "succeeded",
    "failed",
    "blocked",
    "interrupted",
})
_AUTONOMOUS_RUN_TIMESTAMP_FIELDS = frozenset({
    "requested_at",
    "started_at",
    "updated_at",
    "finished_at",
})
_RUNTIME_TOKEN_RE = re.compile(r"^[A-Za-z0-9._:-]{1,96}$")
_RUNTIME_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_RUNTIME_TIMESTAMP_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?Z$"
)

STATUS_STAGE_KEYS = {
    "log_in_progress": "understanding",
    "log_done": "understanding",
    "init_in_progress": "submitted",
    "plan_done": "reviewing_plan",
    "review_in_progress": "reviewing_plan",
    "review_done": "finalizing_plan",
    "plan_finalized": "ready_to_implement",
    "code_in_progress": "working",
    "code_done": "checking",
    "deepcheck_in_progress": "checking",
    "deepcheck_done": "preparing_delivery",
    "completed": "completed",
    "debug_in_progress": "working",
    "debug_done": "completed",
}


class TicketError(RuntimeError):
    """工单请求或公开投影无法被安全解释。"""


@dataclass(frozen=True)
class _TicketRecord:
    """仅供服务端执行器使用的可信工单记录；不得进入公开投影。"""

    out_dir: Path
    metadata: dict[str, Any]


def _required_text(payload: dict[str, Any], field: str, *, limit: int) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise TicketError(f"{field} 必须是非空文本")
    value = value.strip()
    if len(value) > limit:
        raise TicketError(f"{field} 最长 {limit} 字符")
    return value


def normalize_create_ticket_payload(payload: object) -> dict[str, str]:
    """收敛不可信浏览器 JSON；未知字段一律拒绝。"""
    if not isinstance(payload, dict):
        raise TicketError("请求 JSON 根必须是对象")
    unknown = sorted(set(payload) - CREATE_TICKET_FIELDS)
    if unknown:
        raise TicketError(f"请求含未知字段：{unknown}")
    missing = sorted(CREATE_TICKET_FIELDS - set(payload))
    if missing:
        raise TicketError(f"请求缺少字段：{missing}")

    clean = {
        "project_id": _required_text(payload, "project_id", limit=80),
        "title": _required_text(payload, "title", limit=160),
        "description": _required_text(payload, "description", limit=5600),
        "expected_result": _required_text(payload, "expected_result", limit=1600),
        "priority": _required_text(payload, "priority", limit=16),
        "locale": _required_text(payload, "locale", limit=16),
        "execution_mode": _required_text(payload, "execution_mode", limit=16),
        "request_id": _required_text(payload, "request_id", limit=140),
    }
    if clean["priority"] not in PRIORITIES:
        raise TicketError("priority 必须是 low/normal/high/urgent")
    if clean["locale"] not in SUPPORTED_LOCALES:
        raise TicketError("locale 必须是 zh-CN/en-US")
    if clean["execution_mode"] not in EXECUTION_MODES:
        raise TicketError("execution_mode 必须是 interactive/autonomous")
    if _REQUEST_ID_RE.fullmatch(clean["request_id"]) is None:
        raise TicketError("request_id 格式非法")
    return clean


def _project_id(workspace: Path) -> str:
    digest = hashlib.sha256(str(workspace).encode("utf-8")).hexdigest()[:12]
    return f"project-{digest}"


def _load_metadata(path: Path) -> dict[str, Any]:
    for attempt in range(_METADATA_READ_ATTEMPTS):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, PermissionError) as exc:
            # Windows 原子替换 metadata 时，读句柄可能短暂无法打开目标。
            if attempt + 1 == _METADATA_READ_ATTEMPTS:
                raise TicketError("工单 metadata 不可读") from exc
            time.sleep(_METADATA_READ_RETRY_SECONDS)
            continue
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TicketError("工单 metadata 不可读") from exc
        if not isinstance(value, dict):
            raise TicketError("工单 metadata 必须是对象")
        return value
    raise TicketError("工单 metadata 不可读")


class TicketService:
    """可信单工程的目录册和建单入口。"""

    def __init__(
        self,
        settings: Settings,
        *,
        workspace: Path | str,
        index_path: Path | str | None = None,
        control: ControlPlane | None = None,
    ) -> None:
        root = Path(workspace).expanduser().resolve()
        if not root.is_dir() or root == Path("/"):
            raise TicketError("workspace 必须是已存在且非系统根目录的工程目录")
        self.settings = settings
        self.workspace = root
        self.index_path = Path(index_path).expanduser() if index_path is not None else None
        self.control = control or ControlPlane(settings)
        self.project_id = _project_id(root)

    def _ticket_dirs(self) -> list[tuple[int, Path]]:
        output_root = self.workspace / ".icode_output"
        if not output_root.is_dir():
            return []
        result: list[tuple[int, Path]] = []
        for item in output_root.iterdir():
            match = _OUT_DIR_RE.fullmatch(item.name)
            if match and item.is_dir() and not item.is_symlink():
                result.append((int(match.group(1)), item))
        return sorted(result)

    @staticmethod
    def _agent_extension(metadata: dict[str, Any]) -> dict[str, Any]:
        extensions = metadata.get("extensions")
        if not isinstance(extensions, dict):
            return {}
        value = extensions.get("icode_agent")
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _public_autonomous_run(agent: dict[str, Any]) -> dict[str, Any] | None:
        runtime = agent.get("autonomous_run")
        if not isinstance(runtime, dict):
            return None
        public: dict[str, Any] = {}
        state = runtime.get("state")
        if state in AUTONOMOUS_RUN_STATES:
            public["state"] = state
        revision = runtime.get("revision")
        if isinstance(revision, int) and not isinstance(revision, bool) and revision >= 0:
            public["revision"] = revision
        for field in ("run_id", "last_step"):
            value = runtime.get(field)
            if isinstance(value, str) and _RUNTIME_TOKEN_RE.fullmatch(value) is not None:
                public[field] = value
        error_code = runtime.get("error_code")
        if isinstance(error_code, str) and _RUNTIME_CODE_RE.fullmatch(error_code) is not None:
            public["error_code"] = error_code
        for field in _AUTONOMOUS_RUN_TIMESTAMP_FIELDS:
            value = runtime.get(field)
            if isinstance(value, str) and _RUNTIME_TIMESTAMP_RE.fullmatch(value) is not None:
                public[field] = value
        return public

    def _public_ticket(self, metadata: dict[str, Any]) -> dict[str, Any]:
        ticket_id = metadata.get("ticket_id")
        if not isinstance(ticket_id, str) or not ticket_id:
            raise TicketError("工单 ticket_id 缺失")
        status = metadata.get("status") if isinstance(metadata.get("status"), str) else "unknown"
        agent = self._agent_extension(metadata)
        title = agent.get("title")
        if not isinstance(title, str) or not title:
            title = metadata.get("requirement_summary")
        if not isinstance(title, str) or not title:
            title = ticket_id
        public = {
            "ticket_id": ticket_id,
            "project_id": self.project_id,
            "project_name": self.workspace.name or "project",
            "title": title,
            "summary": metadata.get("requirement_summary")
            if isinstance(metadata.get("requirement_summary"), str) else "",
            "status": status,
            "stage_key": STATUS_STAGE_KEYS.get(status, "unknown"),
            "priority": agent.get("priority") if agent.get("priority") in PRIORITIES else "normal",
            "locale": agent.get("locale") if agent.get("locale") in SUPPORTED_LOCALES else "zh-CN",
            "requested_execution_mode": agent.get("requested_execution_mode")
            if agent.get("requested_execution_mode") in EXECUTION_MODES else "interactive",
            "effective_execution_mode": agent.get("effective_execution_mode")
            if agent.get("effective_execution_mode") in EXECUTION_MODES else "interactive",
            "mode_status": agent.get("mode_status")
            if agent.get("mode_status") in {"active", "pending_activation"} else "active",
            "updated_at": metadata.get("updated_at")
            if isinstance(metadata.get("updated_at"), str)
            else metadata.get("created_at", ""),
        }
        autonomous_run = self._public_autonomous_run(agent)
        if autonomous_run is not None:
            public["autonomous_run"] = autonomous_run
        return public

    def _resolve_ticket_record(self, ticket_id: str) -> _TicketRecord:
        """按不透明 ID 唯一解析可信目录和 metadata。"""
        if not isinstance(ticket_id, str) or not ticket_id:
            raise TicketError("工单不存在或身份不唯一")
        matches: list[_TicketRecord] = []
        for _, out_dir in self._ticket_dirs():
            try:
                metadata = _load_metadata(out_dir / ".ico_metadata.json")
            except TicketError:
                continue
            if metadata.get("ticket_id") == ticket_id:
                matches.append(_TicketRecord(out_dir=out_dir, metadata=metadata))
        if len(matches) != 1:
            raise TicketError("工单不存在或身份不唯一")
        return matches[0]

    def snapshot(self, *, query: str | None = None) -> dict[str, Any]:
        tickets: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        needle = (query or "").strip().casefold()
        for slot, out_dir in self._ticket_dirs():
            try:
                metadata = _load_metadata(out_dir / ".ico_metadata.json")
                public = self._public_ticket(metadata)
            except TicketError:
                errors.append({"code": "ticket_metadata_unreadable", "slot": slot})
                continue
            searchable = " ".join((
                public["ticket_id"], public["title"], public["summary"], public["status"],
            )).casefold()
            if needle and needle not in searchable:
                continue
            tickets.append(public)
        tickets.sort(key=lambda item: (item["updated_at"], item["ticket_id"]), reverse=True)
        return {
            "schema_version": 1,
            "projects": [{
                "project_id": self.project_id,
                "name": self.workspace.name or "project",
                "ticket_count": len(tickets),
            }],
            "tickets": tickets,
            "errors": errors,
        }

    def ticket_detail(self, ticket_id: str) -> dict[str, Any]:
        metadata = self._resolve_ticket_record(ticket_id).metadata
        public = self._public_ticket(metadata)
        public["requirement"] = metadata.get("requirement") \
            if isinstance(metadata.get("requirement"), str) else ""
        agent = self._agent_extension(metadata)
        public["description"] = agent.get("description") \
            if isinstance(agent.get("description"), str) else ""
        public["expected_result"] = agent.get("expected_result") \
            if isinstance(agent.get("expected_result"), str) else ""
        public["completed_steps"] = [
            str(item) for item in metadata.get("completed_steps", [])
        ] if isinstance(metadata.get("completed_steps"), list) else []
        return public

    def update_agent_extension(
        self,
        ticket_id: str,
        patch: dict[str, Any],
        *,
        request_id: str,
    ) -> dict[str, Any]:
        """经控制面合并 ``extensions.icode_agent``，并返回安全公开投影。"""
        if not isinstance(patch, dict):
            raise TicketError("Agent 扩展补丁必须是对象")
        if not isinstance(request_id, str) or _REQUEST_ID_RE.fullmatch(request_id) is None:
            raise TicketError("request_id 格式非法")
        record = self._resolve_ticket_record(ticket_id)
        extensions = record.metadata.get("extensions")
        merged_extensions = dict(extensions) if isinstance(extensions, dict) else {}
        merged_agent = dict(self._agent_extension(record.metadata))
        merged_agent.update(patch)
        merged_extensions["icode_agent"] = merged_agent
        updated = self.control.metadata_update(
            record.out_dir,
            ticket_id=ticket_id,
            set_json={"extensions": merged_extensions},
            request=request_id,
        )
        if not updated.ok:
            raise TicketError("Agent 扩展更新被控制面拒绝")
        return self.ticket_detail(ticket_id)

    @staticmethod
    def _requirement(clean: dict[str, str]) -> str:
        labels = (
            ("Title", "Description", "Expected result", "Priority")
            if clean["locale"] == "en-US"
            else ("标题", "问题或需求", "希望结果", "紧急程度")
        )
        return (
            f"{labels[0]}: {clean['title']}\n\n"
            f"{labels[1]}:\n{clean['description']}\n\n"
            f"{labels[2]}:\n{clean['expected_result']}\n\n"
            f"{labels[3]}: {clean['priority']}"
        )

    def _trusted_out_dir(self, raw: object) -> Path:
        if not isinstance(raw, str):
            raise TicketError("控制面建单回执不完整")
        candidate = Path(raw).resolve()
        expected_root = (self.workspace / ".icode_output").resolve()
        try:
            relative = candidate.relative_to(expected_root)
        except ValueError as exc:
            raise TicketError("控制面返回了工程外工单目录") from exc
        if len(relative.parts) != 1 or _OUT_DIR_RE.fullmatch(relative.name) is None:
            raise TicketError("控制面返回的工单目录格式非法")
        return candidate

    def create_ticket(self, payload: object) -> dict[str, Any]:
        clean = normalize_create_ticket_payload(payload)
        if clean["project_id"] != self.project_id:
            raise TicketError("project_id 不存在或不属于当前工作台")
        requirement = self._requirement(clean)
        if len(requirement) > 8000:
            raise TicketError("组合后的 requirement 超过 8000 字符")

        created = self.control.create_next(
            workspace=self.workspace,
            requirement=requirement,
            request_id=clean["request_id"],
            index_path=self.index_path,
        )
        ticket_id = created.data.get("ticket_id")
        if not isinstance(ticket_id, str) or not ticket_id:
            raise TicketError("控制面建单回执缺少 ticket_id")
        out_dir = self._trusted_out_dir(created.data.get("out_dir"))
        metadata = _load_metadata(out_dir / ".ico_metadata.json")
        if metadata.get("ticket_id") != ticket_id:
            raise TicketError("控制面回执与 metadata 身份不一致")

        extensions = metadata.get("extensions")
        merged_extensions = dict(extensions) if isinstance(extensions, dict) else {}
        requested = clean["execution_mode"]
        agent_extension: dict[str, Any] = {
            "title": clean["title"],
            "description": clean["description"],
            "expected_result": clean["expected_result"],
            "priority": clean["priority"],
            "locale": clean["locale"],
            "communication_locale": clean["locale"],
            "requested_execution_mode": requested,
            "effective_execution_mode": "interactive",
            "mode_status": "active" if requested == "interactive" else "pending_activation",
        }
        if requested == "autonomous":
            agent_extension["autonomous_run"] = {"state": "pending", "revision": 0}
        merged_extensions["icode_agent"] = agent_extension
        updated = self.control.metadata_update(
            out_dir,
            ticket_id=ticket_id,
            set_json={"extensions": merged_extensions},
            request=f"{clean['request_id']}:intake",
        )
        if not updated.ok:
            raise TicketError("工单已创建，但业务字段登记被控制面拒绝")
        return {
            "ok": True,
            "already_applied": bool(created.data.get("already_applied")),
            "ticket": self.ticket_detail(ticket_id),
        }
