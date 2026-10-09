#!/usr/bin/env python3
"""证据包独立校验器（零依赖，**不 import 本仓任何代码**）。

这个文件会被原样复制进证据包。它的存在意义是：
**审计方不需要安装、也不需要信任 icode-agent，就能独立校验证据包是否被篡改。**

它主要验证五类内容：
    ① 清单完整性 —— manifest.files 里每个文件的 sha256 与实际一致
    ② 事件链与元数据语义 —— 哈希链、镜像、v3 状态机及快照启用时的 execution-model v1 配对
    ③ 正文与链上哈希对应 —— 产物正文快照的 sha256 必须等于事件 payload 里记录的 sha256
    ④ 包摘要 —— 重算 pack_digest 与 manifest 声明值一致
    ⑤ 包结构 —— 拒绝未登记文件、路径逃逸、链接和超限输入

用法：
    python verify.py <证据包目录>
退出码：
    0 = 通过；1 = 校验失败（被篡改/缺失）；2 = 用法或结构错误
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath

_WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT = stat.FILE_ATTRIBUTE_REPARSE_POINT
_SHA256_FILE_READ_SIZE = 1024 * 1024
_JSON_FILE_READ_SIZE = 64 * 1024
_MAX_JSON_CONTAINER_DEPTH = 128
_MAX_JSON_STRUCTURAL_TOKENS = 500_000
_MAX_MANIFEST_JSON_BYTES = 16 * 1024 * 1024
_MAX_METADATA_JSON_BYTES = 8 * 1024 * 1024
_MAX_ARTIFACT_INDEX_JSON_BYTES = 8 * 1024 * 1024
_MAX_VERIFICATIONS_JSON_BYTES = 8 * 1024 * 1024
_MAX_VERIFICATION_RECEIPTS = 10_000
_MAX_MANIFEST_FILE_ENTRIES = 50_000
_MAX_ARTIFACT_INDEX_ENTRIES = 50_000
_MAX_PACKAGE_ENTRY_COUNT = 100_000
_MAX_EVENT_CHAIN_DIAGNOSTIC_SAMPLES = 32
_MAX_PACKAGE_DIAGNOSTIC_SAMPLES = 32
_MAX_DIAGNOSTIC_MESSAGE_CHARS = 512
_MAX_DIAGNOSTIC_SUMMARY_MESSAGES = 8
_MAX_EVENT_CHAIN_LINE_BYTES = 1024 * 1024
_MAX_EVENT_CHAIN_TOTAL_BYTES = 64 * 1024 * 1024
_MAX_EVENT_CHAIN_EVENT_COUNT = 100_000
# Product-selected evidence-pack bounds; these are not borrowed from Agent UI limits.
_MAX_PACKAGE_FILE_BYTES = 256 * 1024 * 1024
_MAX_PACKAGE_HASH_READ_BYTES = 4 * 1024 * 1024 * 1024
_MAX_PACKAGE_ARTIFACT_BYTES = 256 * 1024 * 1024
_MAX_CONTRACTS_JSON_BYTES = 8 * 1024 * 1024
_MAX_TICKET_STATES = 256
_MAX_TICKET_TRANSITIONS = 4096
_MAX_CLOSE_PHASES = 64
_MAX_EXECUTION_MODEL_STEPS = 4096
_MAX_EXECUTION_MODEL_ENUM_VALUES = 256
_MAX_EXECUTION_MODEL_NAME_CHARS = 128
_DELIVERY_VERDICTS = frozenset({
    "verified", "verification_pending", "blocked", "not_applicable",
})
_TICKET_INITIAL_STATES = {
    "init": "init_in_progress",
    "plan": "init_in_progress",
    "log": "log_in_progress",
    "debug-init": "debug_in_progress",
    "debug-log": "debug_in_progress",
}
_UNSET_METADATA_EVENT_MIRRORS = object()
_UNSET_METADATA_AGENT_SPAWNS = object()
_UNSET_EXPECTED_METADATA_HASH = object()
_UNSET_TICKET_STATE_MACHINE = object()
_UNSET_TICKET_METADATA = object()
_UNSET_EXECUTION_MODEL = object()
_UNSET_COMPLETION_RECEIPT = object()

GENESIS_HASH = "0" * 64
MANIFEST_NAME = "manifest.json"
EVENTS_REL = "ticket/events.jsonl"

# 事件链首事件必须属于这两类（与上游一致）
ALLOWED_FIRST_EVENT = {"ticket_created", "migration_applied"}
ALLOWED_EVENT_TYPES = frozenset({
    "ticket_created",
    "step_started",
    "step_finished",
    "artifact_written",
    "gate_checked",
    "operation_started",
    "operation_finished",
    "state_changed",
    "metadata_updated",
    "claim_recorded",
    "verification_recorded",
    "skill_run_recorded",
    "snapshot_written",
    "close_phase",
    "ticket_reopened",
    "requirement_delta",
    "agent_spawned",
    "agent_result",
    "doc_module_status",
    "index_updated",
    "migration_applied",
    "idempotent_hit",
    "external_note",
})
_METADATA_EVENT_MIRROR_PATHS = {
    "verification_recorded": ("verification_runs",),
    "claim_recorded": ("claims",),
    "skill_run_recorded": ("extensions", "skills", "runs"),
}
_METADATA_AGENT_SPAWNS_PATH = ("extensions", "agent", "spawns")
_METADATA_AGENT_SPAWNS_FIELD = ".".join(_METADATA_AGENT_SPAWNS_PATH)
_AGENT_LIFECYCLE_EVENT_TYPES = frozenset({"agent_spawned", "agent_result"})
_AGENT_SPAWN_REQUIRED_FIELDS = frozenset({
    "spawn_id", "at", "task_scope", "expected_artifact", "evidence_boundary",
    "join_condition", "backend", "model", "capabilities",
})
_AGENT_SPAWN_ALLOWED_FIELDS = _AGENT_SPAWN_REQUIRED_FIELDS | {"exclusive_key"}
_AGENT_RESULT_REQUIRED_FIELDS = frozenset({
    "spawn_id", "result", "adopted", "adoption_reason", "result_at",
    "evidence_refs", "summary_digest",
})
_AGENT_RESULT_ALLOWED_FIELDS = _AGENT_RESULT_REQUIRED_FIELDS | {"error_class"}
_AGENT_CAPABILITIES = frozenset({"text", "image", "tools", "reasoning"})
_AGENT_RESULTS = frozenset({"joined", "timed_out", "stopped", "failed"})
_AGENT_ADOPTION_VALUES = frozenset({"yes", "partial", "no"})
_MAX_OPEN_AGENT_SPAWNS = 3
_METADATA_EVENT_MIRROR_FIELDS = {
    event_type: ".".join(path)
    for event_type, path in _METADATA_EVENT_MIRROR_PATHS.items()
}
_INVALID_METADATA_EVENT_MIRROR = object()
ALLOWED_EVENT_ACTORS = frozenset({"icode", "user", "watch", "system"})
EVENT_SCHEMA_VERSION = 1
EVENT_REQUIRED_FIELDS = frozenset({
    "schema_version",
    "event_id",
    "ticket_id",
    "timestamp",
    "actor",
    "event_type",
    "payload",
    "previous_event_hash",
    "event_hash",
})
EVENT_SCHEMA_FIELDS = frozenset({
    *EVENT_REQUIRED_FIELDS,
    "request_id",
})
EVENT_ID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
EVENT_TIMESTAMP_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
EVENT_HASH_PATTERN = r"^[0-9a-f]{64}$"


def event_schema_issues(
    event: dict, *, expected_ticket_id: str | None = None,
) -> set[str]:
    """Return bounded field labels that violate the pinned ICODE-SKILL v1 event schema."""
    issues = set(EVENT_REQUIRED_FIELDS.difference(event))
    if any(key not in EVENT_SCHEMA_FIELDS for key in event):
        issues.add("additionalProperties")

    schema_version = event.get("schema_version")
    if type(schema_version) is not int or schema_version != EVENT_SCHEMA_VERSION:
        issues.add("schema_version")

    event_id = event.get("event_id")
    if not isinstance(event_id, str) or re.fullmatch(EVENT_ID_PATTERN, event_id) is None:
        issues.add("event_id")

    ticket_id = event.get("ticket_id")
    if not isinstance(ticket_id, str) or not ticket_id:
        issues.add("ticket_id")
    elif expected_ticket_id is not None and ticket_id != expected_ticket_id:
        issues.add("ticket_id")

    if "request_id" in event:
        request_id = event["request_id"]
        if request_id is not None and not isinstance(request_id, str):
            issues.add("request_id")

    timestamp = event.get("timestamp")
    if (
        not isinstance(timestamp, str)
        or re.search(EVENT_TIMESTAMP_PATTERN, timestamp, flags=re.ASCII) is None
    ):
        issues.add("timestamp")

    actor = event.get("actor")
    if not isinstance(actor, str) or actor not in ALLOWED_EVENT_ACTORS:
        issues.add("actor")

    event_type = event.get("event_type")
    if not isinstance(event_type, str) or event_type not in ALLOWED_EVENT_TYPES:
        issues.add("event_type")

    if not isinstance(event.get("payload"), dict):
        issues.add("payload")

    for field in ("previous_event_hash", "event_hash"):
        value = event.get(field)
        if not isinstance(value, str) or re.fullmatch(EVENT_HASH_PATTERN, value) is None:
            issues.add(field)

    return issues


def _event_payload_metadata_record(payload: dict) -> dict:
    """Return the control-plane metadata view of a mirrored event payload."""
    return {
        key: value for key, value in payload.items()
        if key != "metadata_hash_after"
    }


def _metadata_event_mirror_records(metadata: object, event_type: str) -> object:
    """Read a mirrored metadata array by path; missing/null path parts mean empty."""
    path = _METADATA_EVENT_MIRROR_PATHS.get(event_type)
    if path is None:
        return _INVALID_METADATA_EVENT_MIRROR
    return _metadata_records_at_path(metadata, path)


def _metadata_agent_spawn_records(metadata: object) -> object:
    """Read the materialized Agent lifecycle array; missing/null remains empty."""
    return _metadata_records_at_path(metadata, _METADATA_AGENT_SPAWNS_PATH)


def _metadata_records_at_path(metadata: object, path: tuple[str, ...]) -> object:
    value = metadata
    for field in path:
        if value is None:
            return []
        if not isinstance(value, dict):
            return _INVALID_METADATA_EVENT_MIRROR
        value = value.get(field)
    return [] if value is None else value


def _event_payload_matches_metadata_record(payload: dict, metadata_record: dict) -> bool:
    """Compare JSON records canonically, preserving distinctions such as true vs 1."""
    event_record = _event_payload_metadata_record(payload)
    return json.dumps(
        event_record, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ) == json.dumps(
        metadata_record, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )


class _AgentLifecycleMirror:
    """Reconstruct Agent spawn records from ordered events, retaining only open calls."""

    def __init__(self, metadata_records: object) -> None:
        self.structurally_valid = isinstance(metadata_records, list) and all(
            isinstance(record, dict) for record in metadata_records
        )
        self.records = metadata_records if self.structurally_valid else []
        self.record_index = 0
        self.open_records: dict[str, tuple[dict, dict]] = {}
        self.valid = self.structurally_valid
        if self.structurally_valid:
            expected_spawn_ids: set[str] = set()
            for record in self.records:
                spawn_id = record.get("spawn_id")
                if isinstance(spawn_id, str):
                    if spawn_id in expected_spawn_ids:
                        self.valid = False
                    expected_spawn_ids.add(spawn_id)

    @staticmethod
    def _has_nonempty_text(value: object) -> bool:
        return isinstance(value, str) and bool(value.strip())

    @classmethod
    def _valid_spawn_payload(cls, payload: dict) -> bool:
        if not _AGENT_SPAWN_REQUIRED_FIELDS.issubset(payload):
            return False
        if not _AGENT_SPAWN_ALLOWED_FIELDS.issuperset(payload):
            return False
        if not all(cls._has_nonempty_text(payload.get(key)) for key in (
            "spawn_id", "at", "task_scope", "expected_artifact",
            "evidence_boundary", "join_condition", "backend", "model",
        )):
            return False
        if "exclusive_key" in payload:
            exclusive_key = payload.get("exclusive_key")
            if not cls._has_nonempty_text(exclusive_key) or len(exclusive_key) > 80:
                return False
        capabilities = payload.get("capabilities")
        if not isinstance(capabilities, list) or not capabilities \
                or not all(isinstance(item, str) for item in capabilities):
            return False
        return (
            "text" in capabilities
            and all(item in _AGENT_CAPABILITIES for item in capabilities)
            and len(set(capabilities)) == len(capabilities)
        )

    @classmethod
    def _valid_result_payload(cls, payload: dict) -> bool:
        if not _AGENT_RESULT_REQUIRED_FIELDS.issubset(payload):
            return False
        if not _AGENT_RESULT_ALLOWED_FIELDS.issuperset(payload):
            return False
        if not cls._has_nonempty_text(payload.get("spawn_id")):
            return False
        result = payload.get("result")
        if not isinstance(result, str) or result not in _AGENT_RESULTS:
            return False
        adopted = payload.get("adopted")
        if not isinstance(adopted, str) or adopted not in _AGENT_ADOPTION_VALUES:
            return False
        if result != "joined" and adopted != "no":
            return False
        if not cls._has_nonempty_text(payload.get("adoption_reason")):
            return False
        if not cls._has_nonempty_text(payload.get("result_at")):
            return False
        evidence_refs = payload.get("evidence_refs")
        if not isinstance(evidence_refs, list) or not evidence_refs \
                or not all(cls._has_nonempty_text(item) for item in evidence_refs):
            return False
        digest = payload.get("summary_digest")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            return False
        return "error_class" not in payload or cls._has_nonempty_text(
            payload.get("error_class"),
        )

    def consume(self, event_type: str, payload: object) -> None:
        if not self.structurally_valid or event_type not in _AGENT_LIFECYCLE_EVENT_TYPES:
            return
        if not isinstance(payload, dict):
            self.valid = False
            return
        record = _event_payload_metadata_record(payload)
        if event_type == "agent_spawned":
            if not self._valid_spawn_payload(record):
                self.valid = False
                return
            spawn_id = record["spawn_id"]
            if len(self.open_records) >= _MAX_OPEN_AGENT_SPAWNS:
                self.valid = False
                return
            if self.record_index >= len(self.records):
                self.valid = False
                return
            expected = self.records[self.record_index]
            if expected.get("spawn_id") != spawn_id:
                self.valid = False
            self.record_index += 1
            self.open_records[spawn_id] = (record, expected)
            return

        if not self._valid_result_payload(record):
            self.valid = False
            return
        spawn_id = record["spawn_id"]
        open_record = self.open_records.pop(spawn_id, None)
        if open_record is None:
            self.valid = False
            return
        reconstructed, expected = open_record
        reconstructed.update({key: value for key, value in record.items() if key != "spawn_id"})
        if not _event_payload_matches_metadata_record(reconstructed, expected):
            self.valid = False

    def finish(self) -> bool:
        if not self.structurally_valid:
            return False
        if self.record_index != len(self.records):
            self.valid = False
        for reconstructed, expected in self.open_records.values():
            if not _event_payload_matches_metadata_record(reconstructed, expected):
                self.valid = False
        return self.valid


class _BoundedProblemReport(list[str]):
    """List-compatible problem report with exact counts behind its bounded samples."""

    def __init__(
        self,
        values: list[str],
        *,
        total_count: int,
        sample_count: int,
        summary_messages: tuple[str, ...] = (),
    ) -> None:
        super().__init__(values)
        self.total_count = total_count
        self.sample_count = sample_count
        self.summary_messages = summary_messages


class _ProblemCollector:
    """Retain bounded diagnostics while callers continue validating all inputs."""

    def __init__(self) -> None:
        self._samples: list[str] = []
        self._summaries: list[str] = []
        self._total = 0

    @staticmethod
    def _bounded_message(message: object) -> str:
        rendered = str(message)
        if len(rendered) > _MAX_DIAGNOSTIC_MESSAGE_CHARS:
            return rendered[:_MAX_DIAGNOSTIC_MESSAGE_CHARS - 3] + "..."
        return rendered

    def _retain_sample(self, message: object) -> None:
        if len(self._samples) < _MAX_PACKAGE_DIAGNOSTIC_SAMPLES:
            self._samples.append(self._bounded_message(message))

    def _retain_summary(self, message: object) -> None:
        if len(self._summaries) < _MAX_DIAGNOSTIC_SUMMARY_MESSAGES:
            self._summaries.append(self._bounded_message(message))

    def append(self, message: str) -> None:
        self._total += 1
        self._retain_sample(message)

    def extend(self, messages: list[str]) -> None:
        if isinstance(messages, _BoundedProblemReport):
            self._total += messages.total_count
            for message in messages[:messages.sample_count]:
                self._retain_sample(message)
            for message in messages.summary_messages:
                self._retain_summary(message)
            return
        for message in messages:
            self.append(message)

    def render(self) -> _BoundedProblemReport:
        omitted = max(0, self._total - len(self._samples))
        rendered = [*self._samples, *self._summaries]
        if omitted:
            rendered.append(
                f"校验共发现 {self._total} 处问题；展示前 {len(self._samples)} 条，"
                f"省略 {omitted} 条。"
            )
        return _BoundedProblemReport(
            rendered,
            total_count=self._total,
            sample_count=len(self._samples),
            summary_messages=tuple(self._summaries),
        )


class _EventChainDiagnostics:
    """Keep verifier diagnostics bounded without stopping validation of later events."""

    def __init__(self) -> None:
        self._samples: list[str] = []
        self._counts: dict[str, int] = {}
        self._total = 0

    def add(self, category: str, message: str) -> None:
        # Categories are fixed call-site labels; message text must not be copied
        # from schema-invalid input without a strict bound.
        self._total += 1
        self._counts[category] = self._counts.get(category, 0) + 1
        if len(self._samples) < _MAX_EVENT_CHAIN_DIAGNOSTIC_SAMPLES:
            self._samples.append(message)

    def render(self) -> _BoundedProblemReport:
        rendered = list(self._samples)
        omitted = self._total - len(self._samples)
        summary_messages: tuple[str, ...] = ()
        if omitted:
            categories = ", ".join(
                f"{name}={count}" for name, count in sorted(self._counts.items())
            )
            summary = (
                f"事件链校验发现 {self._total} 个链问题；仅展示前 {len(self._samples)} 条，"
                f"省略 {omitted} 条（{categories}）"
            )
            rendered.append(summary)
            summary_messages = (summary,)
        return _BoundedProblemReport(
            rendered,
            total_count=self._total,
            sample_count=len(self._samples),
            summary_messages=summary_messages,
        )


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class _FileSizeLimitExceeded(Exception):
    """Raised when a caller requested a bounded file hash and the limit is crossed."""


class _PackageEntryLimitExceeded(Exception):
    """Raised before sorting or retaining more than the package-entry budget."""


class _HashReadBudgetExceeded(Exception):
    """Raised when hashing would read beyond the shared package byte budget."""


class _HashReadBudget:
    """Track actual file bytes consumed by related hashes in one operation."""

    def __init__(self, max_bytes: int) -> None:
        self.max_bytes = max_bytes
        self.bytes_read = 0

    @property
    def remaining(self) -> int:
        return self.max_bytes - self.bytes_read

    def consume(self, amount: int) -> None:
        if amount < 0 or amount > self.remaining:
            raise _HashReadBudgetExceeded
        self.bytes_read += amount


def sha256_file(
    path: Path,
    *,
    max_bytes: int | None = None,
    read_budget: _HashReadBudget | None = None,
) -> str:
    if max_bytes is not None and max_bytes < 0:
        raise ValueError("单文件摘要输入字节上限不能小于零")
    digest = hashlib.sha256()
    total_bytes = 0
    with Path(path).open("rb") as stream:
        while True:
            read_size = _SHA256_FILE_READ_SIZE
            if max_bytes is not None:
                # Read no more than one byte past the declared budget, even when
                # the file grows after the caller's initial stat check.
                read_size = min(read_size, max_bytes - total_bytes + 1)
            if read_budget is not None:
                # Keep the actual stream read to the shared budget plus one
                # sentinel byte, including the artifact-binding re-hash pass.
                read_size = min(read_size, read_budget.remaining + 1)
            chunk = stream.read(read_size)
            if not chunk:
                break
            total_bytes += len(chunk)
            if max_bytes is not None and total_bytes > max_bytes:
                raise _FileSizeLimitExceeded
            if read_budget is not None:
                if len(chunk) > read_budget.remaining:
                    raise _HashReadBudgetExceeded
                read_budget.consume(len(chunk))
            digest.update(chunk)
    return digest.hexdigest()


def canonical_event_hash(event: dict) -> str:
    """与上游 icode_control.py 的 canonical_event_hash 逐字对齐。"""
    material = {k: v for k, v in event.items() if k != "event_hash"}
    raw = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_bytes(raw.encode("utf-8"))


def _metadata_content_hash(metadata: dict) -> str:
    """与 pinned ICODE-SKILL metadata_hash 保持相同的全对象摘要合同。"""
    raw = json.dumps(
        metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return sha256_bytes(raw.encode("utf-8"))


def _normalize_ticket_state_machine(value: object) -> dict:
    """Keep the independently-verifiable ticket-state contract small and explicit."""
    if not isinstance(value, dict):
        raise ValueError("state_machine 必须是对象")
    states = value.get("states")
    transitions = value.get("transitions")
    close_phases = value.get("close_phases")
    if (
        not isinstance(states, list)
        or not 1 <= len(states) <= _MAX_TICKET_STATES
        or not all(isinstance(state, str) and 0 < len(state) <= 128 for state in states)
        or len(set(states)) != len(states)
    ):
        raise ValueError("state_machine.states 结构无效")
    if (
        not isinstance(transitions, list)
        or len(transitions) > _MAX_TICKET_TRANSITIONS
    ):
        raise ValueError("state_machine.transitions 结构无效")
    normalized_transitions: list[dict[str, str]] = []
    for transition in transitions:
        if not isinstance(transition, dict):
            raise ValueError("state_machine.transitions 项必须是对象")
        source = transition.get("from")
        target = transition.get("to")
        if (
            not isinstance(source, str)
            or not isinstance(target, str)
            or source not in states
            or target not in states
        ):
            raise ValueError("state_machine.transitions 引用未知状态")
        normalized_transitions.append({"from": source, "to": target})
    if (
        not isinstance(close_phases, list)
        or not 1 <= len(close_phases) <= _MAX_CLOSE_PHASES
        or not all(
            isinstance(phase, str) and 0 < len(phase) <= 128
            for phase in close_phases
        )
        or len(set(close_phases)) != len(close_phases)
        or close_phases[-1] != "closed"
    ):
        raise ValueError("state_machine.close_phases 结构无效")
    return {
        "states": list(states),
        "transitions": normalized_transitions,
        "close_phases": list(close_phases),
    }


_EXECUTION_EVENT_TYPES = frozenset({
    "step_started", "gate_checked", "artifact_written", "step_finished",
    "operation_started", "operation_finished",
})
_EXECUTION_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_SUCCESS_OPERATION_DECISION_FIELDS = frozenset({
    "action", "reason", "conclusion_ceiling", "auto_retry",
})


def _normalize_execution_model(value: object, *, snapshot: bool = False) -> dict:
    """Normalize the small v1 catalog needed to independently replay event pairing."""
    if not isinstance(value, dict):
        raise ValueError("execution_model 必须是对象")
    version = value.get("schema_version")
    if type(version) is not int or version != 1:
        raise ValueError("execution_model.schema_version 必须为 1")

    raw_steps = value.get("steps" if snapshot else "step_contracts")
    if snapshot:
        if not isinstance(raw_steps, list):
            raise ValueError("execution_model.steps 必须是数组")
        steps = raw_steps
    elif isinstance(raw_steps, dict):
        steps = list(raw_steps)
    else:
        raise ValueError("execution_model.step_contracts 必须是对象")

    def normalize_names(
        field_name: str, raw_names: object, *, maximum: int,
        allow_empty: bool = False,
    ) -> list[str]:
        if (
            not isinstance(raw_names, list)
            or len(raw_names) > maximum
            or (not allow_empty and not raw_names)
            or not all(
                isinstance(name, str)
                and 0 < len(name) <= _MAX_EXECUTION_MODEL_NAME_CHARS
                for name in raw_names
            )
            or len(set(raw_names)) != len(raw_names)
        ):
            raise ValueError(f"execution_model.{field_name} 结构无效")
        return list(raw_names)

    normalized_steps = normalize_names(
        "steps", steps, maximum=_MAX_EXECUTION_MODEL_STEPS,
    )
    boundaries = normalize_names(
        "boundaries", value.get("boundaries"),
        maximum=_MAX_EXECUTION_MODEL_ENUM_VALUES,
    )
    step_outcomes = normalize_names(
        "step_outcomes", value.get("step_outcomes"),
        maximum=_MAX_EXECUTION_MODEL_ENUM_VALUES,
    )
    raw_classes = value.get("operation_classes")
    if snapshot:
        operation_classes = normalize_names(
            "operation_classes", raw_classes,
            maximum=_MAX_EXECUTION_MODEL_ENUM_VALUES,
        )
    elif isinstance(raw_classes, dict):
        operation_classes = normalize_names(
            "operation_classes", list(raw_classes),
            maximum=_MAX_EXECUTION_MODEL_ENUM_VALUES,
        )
    else:
        raise ValueError("execution_model.operation_classes 必须是对象")

    failure_classes: list[str] | None = None
    failure_field = "failure_classes" if snapshot else "failure_policies"
    if failure_field in value:
        raw_failures = value[failure_field]
        if snapshot:
            failure_names = raw_failures
        elif isinstance(raw_failures, dict):
            failure_names = list(raw_failures)
        else:
            raise ValueError("execution_model.failure_policies 必须是对象")
        failure_classes = normalize_names(
            "failure_classes", failure_names,
            maximum=_MAX_EXECUTION_MODEL_ENUM_VALUES,
        )

    normalized_model = {
        "schema_version": 1,
        "steps": sorted(normalized_steps),
        "boundaries": boundaries,
        "step_outcomes": step_outcomes,
        "operation_classes": sorted(operation_classes),
    }
    if failure_classes is not None:
        normalized_model["failure_classes"] = sorted(failure_classes)
    if snapshot and "success_decision_version" in value:
        success_decision_version = value.get("success_decision_version")
        if type(success_decision_version) is not int or success_decision_version != 1:
            raise ValueError(
                "execution_model.success_decision_version 必须为 1"
            )
        normalized_model["success_decision_version"] = success_decision_version
    return normalized_model


def _execution_model_snapshot_from_raw(raw_contracts: dict) -> dict | None:
    value = raw_contracts.get("execution_model")
    if not isinstance(value, dict) or type(value.get("schema_version")) is not int:
        return None
    if value.get("schema_version") != 1:
        return None
    snapshot = _normalize_execution_model(value)
    # Bind new snapshots to the narrow, fixed success-decision check below. The
    # marker keeps already-exported v1 packs on their historical acceptance rule.
    snapshot["success_decision_version"] = 1
    return snapshot


def _normalize_completion_receipt(value: object) -> dict:
    """Validate the small contract linking completed state to one execution step."""
    if not isinstance(value, dict):
        raise ValueError("completion_receipt 必须是对象")
    if set(value) != {"schema_version", "target", "step", "required_checks"}:
        raise ValueError("completion_receipt 字段集合无效")
    if type(value.get("schema_version")) is not int or value["schema_version"] != 1:
        raise ValueError("completion_receipt.schema_version 必须为 1")
    target = value.get("target")
    if target != "completed":
        raise ValueError("completion_receipt.target 必须为 completed")
    step = value.get("step")
    if (
        not isinstance(step, str)
        or not step
        or len(step) > _MAX_EXECUTION_MODEL_NAME_CHARS
    ):
        raise ValueError("completion_receipt.step 结构无效")
    required_checks = value.get("required_checks")
    if (
        not isinstance(required_checks, list)
        or not 1 <= len(required_checks) <= _MAX_EXECUTION_MODEL_ENUM_VALUES
        or not all(
            isinstance(boundary, str)
            and 0 < len(boundary) <= _MAX_EXECUTION_MODEL_NAME_CHARS
            for boundary in required_checks
        )
        or len(set(required_checks)) != len(required_checks)
    ):
        raise ValueError("completion_receipt.required_checks 结构无效")
    return {
        "schema_version": 1,
        "target": target,
        "step": step,
        "required_checks": list(required_checks),
    }


def _completion_receipt_snapshot_from_raw(raw_contracts: dict) -> dict | None:
    """Snapshot completed→audit receipt policy from the pinned workflow contract."""
    state_machine = raw_contracts.get("state_machine")
    if not isinstance(state_machine, dict):
        return None
    gate_policy = state_machine.get("gate_policy")
    if not isinstance(gate_policy, dict):
        return None
    step_by_target = gate_policy.get("step_by_target")
    if not isinstance(step_by_target, dict):
        raise ValueError("state_machine.gate_policy.step_by_target 结构无效")
    if "completed" not in step_by_target:
        return None
    step = step_by_target.get("completed")
    if (
        not isinstance(step, str)
        or not step
        or len(step) > _MAX_EXECUTION_MODEL_NAME_CHARS
    ):
        raise ValueError("state_machine.gate_policy.step_by_target.completed 结构无效")

    execution_model = raw_contracts.get("execution_model")
    if (
        not isinstance(execution_model, dict)
        or type(execution_model.get("schema_version")) is not int
        or execution_model["schema_version"] != 1
    ):
        raise ValueError("completed 映射要求 execution_model v1 契约")
    step_contracts = execution_model.get("step_contracts")
    if not isinstance(step_contracts, dict) or step not in step_contracts:
        raise ValueError("completed 映射步骤缺 execution_model.step_contracts")
    step_contract = step_contracts[step]
    if not isinstance(step_contract, dict):
        raise ValueError("completed 映射步骤契约结构无效")
    required_checks = step_contract.get("required_checks")
    boundaries = execution_model.get("boundaries")
    if (
        not isinstance(boundaries, list)
        or not all(isinstance(boundary, str) for boundary in boundaries)
    ):
        raise ValueError("execution_model.boundaries 结构无效")
    snapshot = _normalize_completion_receipt({
        "schema_version": 1,
        "target": "completed",
        "step": step,
        "required_checks": required_checks,
    })
    if any(boundary not in boundaries for boundary in snapshot["required_checks"]):
        raise ValueError("completion_receipt.required_checks 含未知 boundary")
    return snapshot


class _TicketStateMirror:
    """Stream v3 ticket state/close semantics without retaining the event chain."""

    def __init__(self, state_machine: object, metadata: object) -> None:
        self.enabled = (
            isinstance(metadata, dict)
            and type(metadata.get("schema_version")) is int
            and metadata.get("schema_version") == 3
            and state_machine is not _UNSET_TICKET_STATE_MACHINE
            and state_machine is not None
        )
        self.metadata = metadata if isinstance(metadata, dict) else {}
        self.problems = _ProblemCollector()
        self.current_state: str | None = None
        self.close_state: str | None = None
        self.birth_count = 0
        self.migration_count = 0
        self.state_machine: dict | None = None
        self.states: set[str] = set()
        self.transitions: set[tuple[str, str]] = set()
        self.close_phases: list[str] = []
        self.close_phase_indexes: dict[str, int] = {}

        if not self.enabled:
            return
        try:
            normalized = _normalize_ticket_state_machine(state_machine)
        except (TypeError, ValueError, RecursionError):
            self.problems.append("contracts.json state_machine 结构无效")
            return
        self.state_machine = normalized
        self.states = set(normalized["states"])
        self.transitions = {
            (item["from"], item["to"])
            for item in normalized["transitions"]
        }
        self.close_phases = normalized["close_phases"]
        self.close_phase_indexes = {
            phase: index for index, phase in enumerate(self.close_phases)
        }

    def consume(self, event: dict, event_index: int) -> None:
        if not self.enabled or self.state_machine is None:
            return
        event_type = event.get("event_type")
        payload = event.get("payload")
        if not isinstance(payload, dict):
            return

        if event_index == 1 and (
            not isinstance(event_type, str) or event_type not in ALLOWED_FIRST_EVENT
        ):
            self.problems.append(
                "首条事件必须是 ticket_created 或 migration_applied"
            )

        if event_type == "ticket_created":
            self.birth_count += 1
            if self.birth_count > 1:
                self.problems.append("ticket_created 事件只能出现一次")
            if self.migration_count:
                self.problems.append(
                    "事件链同时含 ticket_created 与 migration_applied，工单来源多义"
                )
            if event_index != 1:
                self.problems.append("ticket_created 必须是事件链首事件")
            birth_kind = payload.get("birth_kind")
            initial_state = (
                _TICKET_INITIAL_STATES.get(birth_kind)
                if isinstance(birth_kind, str) else None
            )
            if initial_state is None:
                self.problems.append("ticket_created.birth_kind 非法或缺失")
            self.current_state = initial_state
            expected_debug = (
                isinstance(birth_kind, str) and birth_kind.startswith("debug-")
            )
            if bool(self.metadata.get("debug")) != expected_debug:
                self.problems.append(
                    "ticket_created.birth_kind 与 metadata.debug 不一致"
                )
        elif event_type == "migration_applied":
            self.migration_count += 1
            if self.migration_count > 1:
                self.problems.append("migration_applied 事件只能出现一次")
            if self.birth_count:
                self.problems.append(
                    "事件链同时含 ticket_created 与 migration_applied，工单来源多义"
                )

        if event_type == "state_changed":
            source = payload.get("from")
            target = payload.get("to")
            if (
                not isinstance(source, str) or source not in self.states
                or not isinstance(target, str) or target not in self.states
            ):
                self.problems.append(
                    f"第 {event_index} 条 state_changed.from/to 不在状态词表"
                )
                return
            if self.current_state is not None and source != self.current_state:
                self.problems.append(
                    f"第 {event_index} 条 state_changed.from 与事件序列当前状态不一致"
                )
            if (source, target) not in self.transitions:
                self.problems.append(
                    f"第 {event_index} 条 state_changed 记录非法状态流转"
                )
            delivery = payload.get("delivery_verdict")
            if target == "completed" and (
                not isinstance(delivery, str) or delivery not in _DELIVERY_VERDICTS
            ):
                self.problems.append(
                    f"第 {event_index} 条 completed 流转缺合法 delivery_verdict"
                )
            if target != "completed" and delivery is not None:
                self.problems.append(
                    f"第 {event_index} 条非 completed 流转携带 delivery_verdict"
                )
            self.current_state = target

        elif event_type == "close_phase":
            source = payload.get("from")
            target = payload.get("to")
            expected_index = (
                0 if self.close_state is None
                else self.close_phase_indexes[self.close_state] + 1
            )
            expected_target = (
                self.close_phases[expected_index]
                if expected_index < len(self.close_phases) else None
            )
            if source != self.close_state or target != expected_target:
                self.problems.append(
                    f"第 {event_index} 条 close_phase 顺序非法"
                )
            if isinstance(target, str) and target in self.close_phase_indexes:
                self.close_state = target

        elif event_type == "ticket_reopened":
            if (
                self.close_state != "closed"
                or payload.get("from") != "closed"
                or payload.get("to") is not None
            ):
                self.problems.append(
                    f"第 {event_index} 条 ticket_reopened 只能从 closed 原子解冻到 null"
                )
            self.close_state = None

    def finish(self) -> list[str]:
        if not self.enabled:
            return []
        if self.state_machine is not None:
            if (
                self.current_state is not None
                and self.current_state != self.metadata.get("status")
            ):
                self.problems.append(
                    "事件序列最终状态与 metadata.status 不一致"
                )
            if self.close_state != self.metadata.get("close_state"):
                self.problems.append(
                    "事件序列最终 close_state 与 metadata.close_state 不一致"
                )
        return self.problems.render()


class _ExecutionEventMirror:
    """Replay versioned execution pairing and status-transition receipts."""

    def __init__(
        self, execution_model: object,
        completion_receipt: object = _UNSET_COMPLETION_RECEIPT,
    ) -> None:
        self.enabled = (
            execution_model is not _UNSET_EXECUTION_MODEL
            and execution_model is not None
        )
        self.problems = _ProblemCollector()
        self.has_versioned_events = False
        self.steps: dict[bytes, dict[str, object]] = {}
        self.operations: dict[bytes, dict[str, object]] = {}
        self.open_side_effect_operations: set[bytes] = set()
        self.completion_policy: dict | None = None
        self.versioned_ticket_birth = False
        self.completed_transition_seen = False
        self.latest_completion_attempt: bytes | None = None
        self.latest_completion_state: dict[str, object] | None = None
        self.step_names: set[str] = set()
        self.boundaries: set[str] = set()
        self.step_outcomes: set[str] = set()
        self.operation_classes: set[str] = set()
        self.failure_classes: set[str] | None = None
        self.success_decision_version: int | None = None
        if completion_receipt is not _UNSET_COMPLETION_RECEIPT:
            try:
                self.completion_policy = _normalize_completion_receipt(
                    completion_receipt,
                )
            except (TypeError, ValueError, RecursionError):
                self.problems.append("contracts.json completion_receipt 结构无效")
        if self.completion_policy is not None and not self.enabled:
            self.problems.append(
                "contracts.json completion_receipt 缺 execution_model 快照"
            )
        if not self.enabled:
            return
        try:
            normalized = _normalize_execution_model(execution_model, snapshot=True)
        except (TypeError, ValueError, RecursionError):
            self.problems.append("contracts.json execution_model 结构无效")
            self.enabled = False
            return
        self.step_names = set(normalized["steps"])
        self.boundaries = set(normalized["boundaries"])
        self.step_outcomes = set(normalized["step_outcomes"])
        self.operation_classes = set(normalized["operation_classes"])
        if self.completion_policy is not None and (
            self.completion_policy["step"] not in self.step_names
            or any(
                boundary not in self.boundaries
                for boundary in self.completion_policy["required_checks"]
            )
        ):
            self.problems.append(
                "contracts.json completion_receipt 与 execution_model 不一致"
            )
        raw_failure_classes = normalized.get("failure_classes")
        if isinstance(raw_failure_classes, list):
            self.failure_classes = set(raw_failure_classes)
        raw_success_decision_version = normalized.get("success_decision_version")
        if type(raw_success_decision_version) is int:
            self.success_decision_version = raw_success_decision_version

    def _track_completion_attempt(
        self, event_type: object, payload: dict, event_index: int,
    ) -> None:
        """Retain only the latest mapped step attempt and its bounded gate receipt."""
        policy = self.completion_policy
        if policy is None:
            return
        attempt = payload.get("attempt")
        if not isinstance(attempt, str) or not attempt:
            return
        attempt_key = self._fingerprint(attempt)
        step = policy["step"]
        if event_type == "step_started" and payload.get("step") == step:
            self.latest_completion_attempt = attempt_key
            self.latest_completion_state = {
                "step": step,
                "started_at": event_index,
                "gate_results": {},
                "outcome": None,
                "checks": None,
                "finished_at": None,
            }
            return
        state = self.latest_completion_state
        if (
            state is None
            or attempt_key != self.latest_completion_attempt
            or payload.get("step") != step
        ):
            return
        if event_type == "gate_checked":
            boundary = payload.get("boundary")
            result = payload.get("result")
            if isinstance(boundary, str) and isinstance(result, str):
                state["gate_results"][boundary] = result
        elif event_type == "step_finished":
            state["outcome"] = payload.get("outcome")
            state["checks"] = payload.get("checks")
            state["finished_at"] = event_index

    def _check_completion_receipt(
        self, payload: dict, event_index: int,
    ) -> None:
        policy = self.completion_policy
        if policy is None:
            return
        state = self.latest_completion_state
        has_attempt = state is not None
        skipped = payload.get("gates_skipped_for_test") is True
        required = has_attempt or (self.versioned_ticket_birth and not skipped)
        if not required:
            return
        if state is None:
            self.problems.append(
                f"第 {event_index} 条 state_changed.completed 缺 completion_receipt "
                f"{policy['step']} step_started"
            )
            return
        finish_index = state.get("finished_at")
        if not isinstance(finish_index, int) or finish_index >= event_index:
            self.problems.append(
                f"第 {event_index} 条 state_changed.completed 缺先于迁移的 "
                f"completion_receipt {policy['step']} step_finished"
            )
            return
        outcome = state.get("outcome")
        if not isinstance(outcome, str) or outcome not in {"success", "degraded"}:
            self.problems.append(
                f"第 {event_index} 条 state_changed.completed 的 "
                "completion_receipt outcome 不可推进"
            )
        latest_checks = state.get("gate_results")
        finish_checks = state.get("checks")
        if not isinstance(latest_checks, dict):
            latest_checks = {}
        if not isinstance(finish_checks, dict) or finish_checks != latest_checks:
            self.problems.append(
                f"第 {event_index} 条 state_changed.completed 的 "
                "completion_receipt finish checks 与 gate_checked 不一致"
            )
        for boundary in policy["required_checks"]:
            if latest_checks.get(boundary) != "pass":
                self.problems.append(
                    f"第 {event_index} 条 state_changed.completed 的 "
                    f"completion_receipt 最新必需检查未通过：{boundary}"
                )

    @staticmethod
    def _fingerprint(value: str) -> bytes:
        # Event JSON lines are already limited to 1 MiB. Keep only a fixed-size
        # key so attacker-controlled attempt/name strings do not accumulate.
        return hashlib.sha256(value.encode("utf-8", errors="surrogatepass")).digest()

    @staticmethod
    def _valid_digest(value: object) -> bool:
        return (
            isinstance(value, str)
            and _EXECUTION_DIGEST_PATTERN.fullmatch(value) is not None
        )

    @staticmethod
    def _has_pinned_success_decision(decision: dict) -> bool:
        """Match the pinned producer's fixed success decision, not failure policy."""
        return (
            decision.keys() == _SUCCESS_OPERATION_DECISION_FIELDS
            and decision.get("action") == "complete"
            and decision.get("reason") == "operation_succeeded"
            and decision.get("conclusion_ceiling") == "verified"
            # JSON numbers compare equal to bools in Python, so require identity.
            and decision.get("auto_retry") is False
        )

    def consume(self, event: dict, event_index: int) -> None:
        event_type = event.get("event_type")
        payload = event.get("payload")
        if not isinstance(payload, dict):
            return
        if event_type == "ticket_created":
            marker = payload.get("execution_contract_version")
            if type(marker) is int and marker == 1:
                self.versioned_ticket_birth = True
            return
        if event_type == "state_changed":
            if self.open_side_effect_operations:
                self.problems.append(
                    f"第 {event_index} 条 state_changed 在有副作用 operation 未终结时推进状态"
                )
            if payload.get("to") == "completed":
                self.completed_transition_seen = True
                self._check_completion_receipt(payload, event_index)
            return
        if payload.get("execution_model_version") != 1:
            return
        self.has_versioned_events = True
        self._track_completion_attempt(event_type, payload, event_index)
        if not self.enabled:
            attempt = payload.get("attempt")
            if not isinstance(attempt, str) or not attempt:
                return
            attempt_key = self._fingerprint(attempt)
            if event_type == "operation_started":
                if payload.get("class") != "read_only":
                    self.open_side_effect_operations.add(attempt_key)
            elif event_type == "operation_finished":
                self.open_side_effect_operations.discard(attempt_key)
            return

        type_label = (
            event_type[:64] if isinstance(event_type, str)
            else type(event_type).__name__
        )
        attempt = payload.get("attempt")
        if not isinstance(attempt, str) or not attempt:
            self.problems.append(
                f"第 {event_index} 条 {type_label} 缺非空 attempt"
            )
            return
        attempt_key = self._fingerprint(attempt)

        if event_type == "step_started":
            step = payload.get("step")
            if not isinstance(step, str) or step not in self.step_names:
                self.problems.append(
                    f"第 {event_index} 条 step_started.step 非法"
                )
            if attempt_key in self.steps:
                self.problems.append(
                    f"第 {event_index} 条 step_started attempt 重复启动"
                )
            if not self._valid_digest(payload.get("input_digest")):
                self.problems.append(
                    f"第 {event_index} 条 step_started.input_digest 非法"
                )
            if not self._valid_digest(payload.get("contract_digest")):
                self.problems.append(
                    f"第 {event_index} 条 step_started.contract_digest 非法"
                )
            self.steps[attempt_key] = {
                "step": step if isinstance(step, str) else None,
                "finished": False,
            }
            return

        if event_type in {
            "gate_checked", "artifact_written", "step_finished",
        }:
            state = self.steps.get(attempt_key)
            if state is None:
                self.problems.append(
                    f"第 {event_index} 条 {type_label} 引用不存在的 step attempt"
                )
                return
            if state["finished"]:
                if event_type == "step_finished":
                    self.problems.append(
                        f"第 {event_index} 条 step attempt 重复终结"
                    )
                else:
                    self.problems.append(
                        f"第 {event_index} 条 {type_label} 出现在 step_finished 之后"
                    )
            if payload.get("step") != state["step"]:
                self.problems.append(
                    f"第 {event_index} 条 {type_label}.step 与启动事件不一致"
                )
            if event_type == "gate_checked":
                boundary = payload.get("boundary")
                if not isinstance(boundary, str) or boundary not in self.boundaries:
                    self.problems.append(
                        f"第 {event_index} 条 gate_checked.boundary 非法"
                    )
                result = payload.get("result")
                if not isinstance(result, str) or result not in {"pass", "blocked"}:
                    self.problems.append(
                        f"第 {event_index} 条 gate_checked.result 非法"
                    )
                for field_name in ("captured_digest", "current_digest"):
                    if not self._valid_digest(payload.get(field_name)):
                        self.problems.append(
                            f"第 {event_index} 条 gate_checked.{field_name} 非法"
                        )
            elif event_type == "artifact_written":
                if not self._valid_digest(payload.get("sha256")):
                    self.problems.append(
                        f"第 {event_index} 条 artifact_written.sha256 非法"
                    )
            else:
                outcome = payload.get("outcome")
                if (
                    not isinstance(outcome, str)
                    or outcome not in self.step_outcomes
                ):
                    self.problems.append(
                        f"第 {event_index} 条 step_finished.outcome 非法"
                    )
                duration = payload.get("duration_ms")
                if not isinstance(duration, int) or duration < 0:
                    self.problems.append(
                        f"第 {event_index} 条 step_finished.duration_ms 非法"
                    )
                state["finished"] = True
            return

        if event_type == "operation_started":
            name = payload.get("name")
            op_class = payload.get("class")
            if not isinstance(name, str) or not name:
                self.problems.append(
                    f"第 {event_index} 条 operation_started.name 非法"
                )
            if (
                not isinstance(op_class, str)
                or op_class not in self.operation_classes
            ):
                self.problems.append(
                    f"第 {event_index} 条 operation_started.class 非法"
                )
            if not self._valid_digest(payload.get("input_digest")):
                self.problems.append(
                    f"第 {event_index} 条 operation_started.input_digest 非法"
                )
            if not isinstance(payload.get("idempotency_provided"), bool):
                self.problems.append(
                    f"第 {event_index} 条 operation_started.idempotency_provided 非布尔"
                )
            if attempt_key in self.operations:
                self.problems.append(
                    f"第 {event_index} 条 operation attempt 重复启动"
                )
            self.operations[attempt_key] = {
                "name": (
                    self._fingerprint(name) if isinstance(name, str) else None
                ),
                "class": op_class if isinstance(op_class, str) else None,
                "finished": False,
            }
            if op_class != "read_only":
                self.open_side_effect_operations.add(attempt_key)
            return

        if event_type == "operation_finished":
            state = self.operations.get(attempt_key)
            if state is None:
                self.problems.append(
                    f"第 {event_index} 条 operation_finished 引用不存在的 attempt"
                )
                return
            if state["finished"]:
                self.problems.append(
                    f"第 {event_index} 条 operation attempt 重复终结"
                )
            name = payload.get("name")
            if (
                not isinstance(name, str)
                or self._fingerprint(name) != state["name"]
                or payload.get("class") != state["class"]
            ):
                self.problems.append(
                    f"第 {event_index} 条 operation_finished 与启动事件身份不一致"
                )
            outcome = payload.get("outcome")
            if (
                not isinstance(outcome, str)
                or outcome not in self.step_outcomes
            ):
                self.problems.append(
                    f"第 {event_index} 条 operation_finished.outcome 非法"
                )
            duration = payload.get("duration_ms")
            if not isinstance(duration, int) or duration < 0:
                self.problems.append(
                    f"第 {event_index} 条 operation_finished.duration_ms 非法"
                )
            for field_name in ("evidence", "after_check"):
                value = payload.get(field_name)
                if not isinstance(value, str) or not value.strip():
                    self.problems.append(
                        f"第 {event_index} 条 operation_finished 缺 {field_name}"
                    )
            decision = payload.get("decision")
            if not isinstance(decision, dict):
                self.problems.append(
                    f"第 {event_index} 条 operation_finished 缺 decision 对象"
                )
            if self.failure_classes is not None:
                failure = payload.get("failure")
                if outcome == "success":
                    if failure is not None and failure != "":
                        self.problems.append(
                            f"第 {event_index} 条 operation_finished.failure 与 success 冲突"
                        )
                elif not isinstance(failure, str) or not failure.strip():
                    self.problems.append(
                        f"第 {event_index} 条 operation_finished.failure 缺失"
                    )
                elif failure not in self.failure_classes:
                    self.problems.append(
                        f"第 {event_index} 条 operation_finished.failure 未登记"
                    )
            if (
                self.success_decision_version == 1
                and outcome == "success"
                and isinstance(decision, dict)
                and not self._has_pinned_success_decision(decision)
            ):
                self.problems.append(
                    f"第 {event_index} 条 operation_finished.decision 与 success policy 不一致"
                )
            state["finished"] = True
            if state["class"] != "read_only":
                self.open_side_effect_operations.discard(attempt_key)

    def finish(self) -> list[str]:
        # The pinned v1 validator does not require open attempts to be closed at EOF.
        return self.problems.render()


def pack_digest(entries: list[dict]) -> str:
    """与生成端逐字对齐：对 (path, sha256) 排序后做规范 JSON 再取 sha256。"""
    material = sorted(
        ({"path": str(e["path"]), "sha256": str(e["sha256"])} for e in entries),
        key=lambda e: e["path"],
    )
    raw = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_bytes(raw.encode("utf-8"))


def _json_object_without_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """拒绝重复 JSON 成员名，避免独立审计工具对同一内容产生不同解释。"""
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("JSON 对象包含重复 JSON 成员名")
        value[key] = item
    return value


def _reject_non_json_numeric_constant(_value: str) -> object:
    """Python's decoder accepts JavaScript NaN/Infinity tokens by default."""
    raise ValueError("JSON 含有非标准 JSON 数值常量")


def _check_json_structural_token_budget(
    text: str, *, max_depth: int | None = None,
) -> None:
    """Pre-scan JSON punctuation and optionally container depth without parsing."""
    in_string = False
    escaped = False
    token_count = 0
    container_stack: list[str] = []
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "{}[],:":
            token_count += 1
            if token_count > _MAX_JSON_STRUCTURAL_TOKENS:
                raise ValueError("JSON结构标点超过安全上限")
            if max_depth is not None:
                if char in "{[":
                    container_stack.append(char)
                    if len(container_stack) > max_depth:
                        raise ValueError("JSON 容器嵌套深度超过安全上限")
                elif char in "}]":
                    expected_open = "{" if char == "}" else "["
                    if container_stack and container_stack[-1] == expected_open:
                        container_stack.pop()


def _reject_non_interoperable_values(value: object) -> None:
    """Reject values unsafe for the shared parser/hash/serializer contract."""
    pending: list[tuple[object, int]] = [(value, 0)]
    while pending:
        current, parent_depth = pending.pop()
        if isinstance(current, str):
            if any(0xD800 <= ord(char) <= 0xDFFF for char in current):
                raise ValueError("JSON 字符串包含孤立 UTF-16 代理项")
        elif isinstance(current, float) and not math.isfinite(current):
            raise ValueError("JSON 数值转换为非有限 binary64")
        elif isinstance(current, dict):
            depth = parent_depth + 1
            if depth > _MAX_JSON_CONTAINER_DEPTH:
                raise ValueError("JSON 容器嵌套深度超过安全上限")
            pending.extend((item, depth) for item in current.keys())
            pending.extend((item, depth) for item in current.values())
        elif isinstance(current, list):
            depth = parent_depth + 1
            if depth > _MAX_JSON_CONTAINER_DEPTH:
                raise ValueError("JSON 容器嵌套深度超过安全上限")
            pending.extend((item, depth) for item in current)


def loads_json_value(text: str) -> object:
    """Parse JSON under the same strict interoperability rules used by verify.py."""
    _check_json_structural_token_budget(text)
    value = json.loads(
        text,
        object_pairs_hook=_json_object_without_duplicates,
        parse_constant=_reject_non_json_numeric_constant,
    )
    _reject_non_interoperable_values(value)
    return value


# Engineering observations have one closed, stdlib-only contract. This module
# is also the exported verify.py; no host producer imports are needed here.
_ENGINEERING_COVERAGE = {
    "record_scope": "engineering_result_snapshot",
    "session_replay": "not_included",
    "unrecorded_side_effects": "not_proven",
    "execution_source": "not_authenticated",
    "test_quality": "not_authenticated",
}
_ENGINEERING_BINDING_TEXT_FIELDS = (
    "step", "attempt", "execution_attempt", "verify_kind", "environment_fingerprint",
    "diff_fingerprint", "base_commit_sha", "initial_worktree_fingerprint",
    "tested_worktree_fingerprint", "git_object_format", "test_head_before_sha",
    "test_head_after_sha", "test_head_status", "tested_git_tree_oid", "tested_git_tree_status",
    "result_commit_sha", "result_commit_tree_oid", "result_commit_tree_status",
    "result_commit_timing_status", "result_commit_checked_at", "captured_at",
)
# A repair key carries source/runtime facts, not arbitrary annotation changes.
# Keep an explicit allowlist so new audit labels cannot silently grant retries.
_ENGINEERING_REPAIR_BINDING_FIELDS = (
    "environment_fingerprint", "artifact_hashes_sha256", "diff_fingerprint", "base_commit_sha",
    "initial_worktree_fingerprint", "tested_worktree_fingerprint", "git_object_format", "tested_git_tree_oid",
)
# POSIX signals may be negative; Windows APIs preserve the unsigned DWORD.
_ENGINEERING_MIN_EXIT_CODE = -(2 ** 31)
_ENGINEERING_MAX_EXIT_CODE = 2 ** 32 - 1
_ENGINEERING_CHECK_STATUSES = frozenset({
    "passed", "failed", "not_run", "tool_changed", "missing_command",
    "execution_unavailable", "output_incomplete",
})
_ENGINEERING_RUN_STATUSES = _ENGINEERING_CHECK_STATUSES - {"not_run"} | frozenset({
    "source_changed", "source_unavailable", "binding_changed", "cache_cleanup_unconfirmed",
})
_ENGINEERING_FIXED_ERRORS = frozenset({
    "", "invalid_cwd", "binding_changed", "isolation_unavailable", "execution_receipt_incomplete",
    "VerificationOutputError", "VerificationOutputLimitError", "VerificationOutputCaptureError", "TimeoutExpired",
    # The executor records only a fixed class name, never an exception message.
    "OSError", "BlockingIOError", "ChildProcessError", "ConnectionError", "BrokenPipeError",
    "ConnectionAbortedError", "ConnectionRefusedError", "ConnectionResetError", "FileExistsError",
    "FileNotFoundError", "InterruptedError", "IsADirectoryError", "NotADirectoryError",
    "PermissionError", "ProcessLookupError", "TimeoutError",
})


def _engineering_digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _engineering_shape(value: object, fields: set[str]) -> dict:
    if type(value) is not dict or set(value) != fields:
        raise ValueError("engineering_verification 字段集合无效")
    return value


def _engineering_text(value: object, *, required: bool = False, maximum: int = 8192) -> None:
    if type(value) is not str or "\x00" in value or required and not value:
        raise ValueError("engineering_verification 文本字段无效")
    if len(value) > maximum or len(value.encode("utf-8")) > maximum:
        raise ValueError("engineering_verification 文本超过安全上限")


def _engineering_hash(value: object, *, empty: bool = False) -> None:
    if type(value) is not str or not (empty and value == "" or re.fullmatch(r"[0-9a-f]{64}", value)):
        raise ValueError("engineering_verification SHA256 无效")


def engineering_receipt_values(receipt: object, *, compute_digests: bool = True) -> dict:
    """Validate closed observations and derive digests, without trusting labels.

    Hidden tool/argument/environment digests are host claims, not recoverable
    values or authenticated execution. Reported test counts are observations.
    """
    row = _engineering_shape(receipt, {"kind", "schema_version", "coverage", "binding",
        "public_plan", "public_projection_digest", "run", "category", "passed", "fingerprint", "repair_fingerprint"})
    if row["kind"] != "engineering_verification" or type(row["schema_version"]) is not int or row["schema_version"] != 1:
        raise ValueError("engineering_verification schema_version 必须为严格整数 1")
    if row["coverage"] != _ENGINEERING_COVERAGE:
        raise ValueError("engineering_verification coverage 无效")
    binding = _engineering_shape(row["binding"], set(_ENGINEERING_BINDING_TEXT_FIELDS) | {
        "exit_code", "command_sha256", "artifact_hashes_sha256", "output_sha256"})
    for field in _ENGINEERING_BINDING_TEXT_FIELDS:
        _engineering_text(binding[field], required=field in {"step", "attempt", "execution_attempt"})
    for field in ("command_sha256", "artifact_hashes_sha256", "output_sha256"):
        _engineering_hash(binding[field])
    if binding["exit_code"] is not None and type(binding["exit_code"]) is not int:
        raise ValueError("engineering_verification exit_code 无效")
    plan = _engineering_shape(row["public_plan"], {"run_id", "ticket_id", "workspace_sha256",
        "environment_sha256", "steps", "platforms", "checks"})
    for field in ("run_id", "ticket_id"):
        _engineering_text(plan[field], required=True, maximum=256)
    for field in ("workspace_sha256", "environment_sha256"):
        _engineering_hash(plan[field])
    for field, allowed in (("steps", {"task", "code", "deepcheck"}),
                           ("platforms", {"Linux", "Darwin", "Windows"})):
        items = plan[field]
        if type(items) is not list or not 1 <= len(items) <= 3 or any(type(v) is not str or v not in allowed for v in items) or len(set(items)) != len(items):
            raise ValueError("engineering_verification 适用范围无效")
    checks = plan["checks"]
    if type(checks) is not list or not 1 <= len(checks) <= 16:
        raise ValueError("engineering_verification 检查数量无效")
    ids = set()
    timeout_total = output_total = 0
    for check in checks:
        _engineering_shape(check, {"check_id", "kind", "adapter", "required", "tool_sha256",
                                  "parameters_sha256", "timeout_seconds", "output_limit_bytes"})
        identity = check["check_id"]
        if type(identity) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", identity) or identity in ids:
            raise ValueError("engineering_verification 检查身份重复或无效")
        ids.add(identity)
        if type(check["kind"]) is not str or check["kind"] not in {"test", "lint", "build"} or type(check["required"]) is not bool:
            raise ValueError("engineering_verification 检查类型无效")
        adapters = {"unittest_summary_v1", "go_test_json_v1"} if check["kind"] == "test" else {"exit_status_v1"}
        if type(check["adapter"]) is not str or check["adapter"] not in adapters:
            raise ValueError("engineering_verification adapter 无效")
        for field in ("tool_sha256", "parameters_sha256"):
            _engineering_hash(check[field])
        timeout = check["timeout_seconds"]
        limit = check["output_limit_bytes"]
        if type(timeout) not in (int, float) or not 0 < timeout <= 1800 or not math.isfinite(timeout) or type(limit) is not int or not 1 <= limit <= 8 * 1024 * 1024:
            raise ValueError("engineering_verification 检查限额无效")
        timeout_total += timeout
        output_total += limit
    if timeout_total > 1800 or output_total > 8 * 1024 * 1024 or not any(c["required"] and c["kind"] == "test" for c in checks):
        raise ValueError("engineering_verification 计划限额或必需测试无效")
    run = _engineering_shape(row["run"], {"plan_digest", "step", "attempt", "status", "source_before",
                                            "source_after", "os_enforced", "checks"})
    _engineering_hash(run["plan_digest"])
    for field in ("step", "attempt"):
        _engineering_text(run[field], required=True, maximum=256)
    if run["step"] != binding["step"] or run["step"] not in plan["steps"] or run["attempt"] != binding["execution_attempt"]:
        raise ValueError("engineering_verification 执行身份不一致")
    for field in ("source_before", "source_after"):
        _engineering_hash(run[field], empty=True)
    if binding["tested_worktree_fingerprint"] != run["source_after"]:
        raise ValueError("engineering_verification 受测源码绑定不一致")
    if type(run["status"]) is not str or run["status"] not in _ENGINEERING_RUN_STATUSES or type(run["os_enforced"]) is not bool:
        raise ValueError("engineering_verification 执行状态无效")
    if run["status"] == "passed" and run["source_before"] and run["source_after"] and run["source_before"] != run["source_after"]:
        raise ValueError("engineering_verification passed 与源码变化矛盾")
    results = run["checks"]
    if type(results) is not list or len(results) != len(checks):
        raise ValueError("engineering_verification 结果数量不一致")
    unknown = not run["source_before"] or not run["source_after"] or run["source_before"] != run["source_after"]
    failed = []
    stopped = False
    for check, result in zip(checks, results):
        _engineering_shape(result, {"check_id", "status", "exit_code", "tests_passed", "output_sha256", "output_bytes",
            "cleanup_ok", "cleanup_scope", "cache_owner_cleanup_confirmed", "scope_cleanup_ok",
            "resource_channel_status", "violation_observer_status", "resource_receipt_sha256", "error"})
        if result["check_id"] != check["check_id"] or type(result["status"]) is not str or result["status"] not in _ENGINEERING_CHECK_STATUSES:
            raise ValueError("engineering_verification 结果身份或状态无效")
        status, code, count = result["status"], result["exit_code"], result["tests_passed"]
        if code is not None and (type(code) is not int or not _ENGINEERING_MIN_EXIT_CODE <= code <= _ENGINEERING_MAX_EXIT_CODE):
            raise ValueError("engineering_verification 退出码无效")
        if type(count) is not int or not 0 <= count <= 10_000_000 or check["kind"] != "test" and count != 0:
            raise ValueError("engineering_verification 测试计数无效")
        if type(result["output_bytes"]) is not int or not 0 <= result["output_bytes"] <= check["output_limit_bytes"]:
            raise ValueError("engineering_verification 输出限额无效")
        _engineering_hash(result["output_sha256"], empty=True)
        _engineering_hash(result["resource_receipt_sha256"], empty=True)
        for field in ("cleanup_ok", "scope_cleanup_ok", "cache_owner_cleanup_confirmed"):
            if result[field] is not None and type(result[field]) is not bool:
                raise ValueError("engineering_verification 清理状态无效")
        if type(result["cleanup_scope"]) is not str or result["cleanup_scope"] not in {"unknown", "not_started", "process_group", "job_tree", "linux_task_scope"}:
            raise ValueError("engineering_verification 清理范围无效")
        for field in ("resource_channel_status", "violation_observer_status"):
            if type(result[field]) is not str or result[field] not in {"not_required", "complete", "incomplete"}:
                raise ValueError("engineering_verification 通道状态无效")
        if type(result["error"]) is not str or result["error"] not in _ENGINEERING_FIXED_ERRORS:
            raise ValueError("engineering_verification 固定错误无效")
        if stopped and status != "not_run":
            raise ValueError("engineering_verification 首败后仍执行检查")
        if status == "not_run":
            if code is not None or count or result["output_sha256"] or result["output_bytes"]:
                raise ValueError("engineering_verification 未运行检查含结果信用")
            stopped = True
            continue
        if status in {"passed", "failed"}:
            if code is None or not result["output_sha256"]:
                raise ValueError("engineering_verification 完整结果缺退出或输出")
            expected_pass = code == 0 and (check["kind"] != "test" or count > 0)
            if (status == "passed") != expected_pass or status == "failed" and count:
                raise ValueError("engineering_verification passed/exit/count 矛盾")
        elif count or result["output_sha256"] or result["output_bytes"]:
            raise ValueError("engineering_verification 未知执行含完整结果信用")
        closed = (result["cleanup_ok"] is True and result["cache_owner_cleanup_confirmed"] is True
                  and (result["cleanup_scope"] == "job_tree"
                       and result["scope_cleanup_ok"] is not False
                       and result["resource_channel_status"] == "not_required"
                       and result["violation_observer_status"] == "not_required"
                       and not result["resource_receipt_sha256"]
                       or result["cleanup_scope"] == "linux_task_scope"
                       and result["scope_cleanup_ok"] is True and result["resource_channel_status"] == "complete"
                       and result["violation_observer_status"] == "complete" and bool(result["resource_receipt_sha256"])))
        unknown |= not closed or status not in {"passed", "failed"} or bool(result["error"])
        if status != "passed":
            stopped = True
            failed.append({"check_id": check["check_id"], "kind": check["kind"], "status": status,
                           "exit_code": code, "tests_passed": count, "error": result["error"]})
    all_passed = all(r["status"] == "passed" for r in results)
    if run["status"] == "passed" and not all_passed or run["status"] == "failed" and not failed:
        raise ValueError("engineering_verification 聚合状态矛盾")
    if run["status"] not in {"passed", "failed"}:
        unknown = True
    passed = run["status"] == "passed" and all_passed and not unknown
    category = "side_effect_unknown" if unknown else "code" if failed else "test"
    derived_exit = 0 if passed else next((f["exit_code"] for f in failed if f["exit_code"] is not None), None)
    if not compute_digests:
        return {"category": category, "passed": passed, "binding_exit_code": derived_exit}
    audit_binding = {k: v for k, v in binding.items() if k not in {"attempt", "execution_attempt", "captured_at", "result_commit_checked_at"}}
    audit_run = {k: v for k, v in run.items() if k != "attempt"}
    projection = _engineering_digest(plan)
    fingerprint = _engineering_digest({"domain": "icode.engineering.audit.v1", "schema_version": 1,
        "coverage": row["coverage"], "binding": audit_binding, "public_plan": plan, "run": audit_run,
        "category": category, "passed": passed})
    repair = _engineering_digest({"domain": "icode.engineering.repair.v1", "schema_version": 1,
        "step": run["step"], "public_plan": {k: v for k, v in plan.items() if k not in {"run_id", "ticket_id"}},
        "source_before": run["source_before"], "source_after": run["source_after"],
        "binding": {k: binding[k] for k in _ENGINEERING_REPAIR_BINDING_FIELDS},
        "status": run["status"], "category": category, "failures": failed})
    return {"public_projection_digest": projection, "fingerprint": fingerprint,
            "repair_fingerprint": repair, "category": category, "passed": passed,
            "binding_exit_code": derived_exit}


def validate_engineering_receipt(receipt: object, *, expected_ticket_id: str | None = None) -> dict | None:
    """Legacy/unknown kinds carry no engineering credit; new kinds cannot downgrade."""
    if type(receipt) is not dict or receipt.get("kind") != "engineering_verification":
        return None
    values = engineering_receipt_values(receipt)
    if expected_ticket_id is not None and receipt["public_plan"]["ticket_id"] != expected_ticket_id:
        raise ValueError("engineering_verification ticket_id 与工单不一致")
    if receipt["binding"]["exit_code"] != values["binding_exit_code"] or any(
        type(receipt[field]) is not type(value) or receipt[field] != value
        for field, value in values.items() if field != "binding_exit_code"
    ):
        raise ValueError("engineering_verification 语义或摘要不一致")
    return values


def load_verifications_json(path: Path, *, expected_ticket_id: str | None = None) -> dict:
    """Only this wrapper admits two extra containers; each receipt stays at 128."""
    text = read_bounded_bytes(path, max_bytes=_MAX_VERIFICATIONS_JSON_BYTES).decode("utf-8")
    _check_json_structural_token_budget(text, max_depth=_MAX_JSON_CONTAINER_DEPTH + 2)
    value = json.loads(text, object_pairs_hook=_json_object_without_duplicates,
                       parse_constant=_reject_non_json_numeric_constant)
    _engineering_shape(value, {"schema_version", "receipts"})
    if type(value["schema_version"]) is not int or value["schema_version"] != 1 or type(value["receipts"]) is not list or len(value["receipts"]) > _MAX_VERIFICATION_RECEIPTS:
        raise ValueError("verifications.json 包装结构无效")
    for receipt in value["receipts"]:
        _reject_non_interoperable_values(receipt)
        validate_engineering_receipt(receipt, expected_ticket_id=expected_ticket_id)
    return value


def read_bounded_bytes(path: Path, *, max_bytes: int) -> bytes:
    """Read at most max_bytes + 1 bytes using bounded chunks."""
    if max_bytes < 0:
        raise ValueError("控制JSON超过输入字节上限")
    chunks: list[bytes] = []
    total_bytes = 0
    with Path(path).open("rb") as stream:
        while True:
            read_size = min(_JSON_FILE_READ_SIZE, max_bytes - total_bytes + 1)
            chunk = stream.read(read_size)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > max_bytes:
                raise ValueError("控制JSON超过输入字节上限")
            chunks.append(chunk)
    return b"".join(chunks)


def load_json_value(path: Path, *, max_bytes: int) -> object:
    """Read at most max_bytes + 1 bytes, then parse under the JSON budget."""
    raw = read_bounded_bytes(path, max_bytes=max_bytes)
    return loads_json_value(raw.decode("utf-8"))


def _load_json(path: Path, *, max_bytes: int) -> dict:
    value = load_json_value(Path(path), max_bytes=max_bytes)
    if not isinstance(value, dict):
        raise ValueError("JSON 根节点必须是对象")
    return value


def _load_contract_snapshot(path: Path) -> dict:
    """Parse contracts with duplicate-key/size guards while preserving legacy NaN values."""
    raw = read_bounded_bytes(Path(path), max_bytes=_MAX_CONTRACTS_JSON_BYTES)
    text = raw.decode("utf-8")
    _check_json_structural_token_budget(text, max_depth=_MAX_JSON_CONTAINER_DEPTH)
    value = json.loads(text, object_pairs_hook=_json_object_without_duplicates)
    if not isinstance(value, dict):
        raise ValueError("contracts.json 根节点必须是对象")
    return value


def _package_member_path(pack: Path, relative: str) -> Path | None:
    """只接受包根内规范相对路径，并拒绝任何符号链接/reparse point。"""
    if not isinstance(relative, str) or not relative or "\x00" in relative or "\\" in relative:
        return None

    parts = relative.split("/")
    posix_path = PurePosixPath(relative)
    windows_path = PureWindowsPath(relative)
    if (
        posix_path.is_absolute()
        or windows_path.is_absolute()
        or windows_path.drive
        or any(part in ("", ".", "..") for part in parts)
    ):
        return None

    root = pack.resolve()
    target = pack.joinpath(*parts)
    current = pack
    for part in parts:
        current = current / part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            break
        except (OSError, RuntimeError, ValueError):
            return None
        if stat.S_ISLNK(metadata.st_mode) or (
            getattr(metadata, "st_file_attributes", 0)
            & _WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT
        ):
            return None

    try:
        resolved = target.resolve(strict=False)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return None
    return target


def _walk_package_entries(pack: Path):
    """遍历包项时不跟随符号链接或 Windows reparse point。"""
    pending = [pack]
    entry_count = 0
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as iterator:
            entries = []
            for entry in iterator:
                entry_count += 1
                if entry_count > _MAX_PACKAGE_ENTRY_COUNT:
                    raise _PackageEntryLimitExceeded
                entries.append(entry)
            entries.sort(key=lambda entry: entry.name)
        child_directories: list[Path] = []
        for entry in entries:
            path = Path(entry.path)
            metadata = entry.stat(follow_symlinks=False)
            is_link = stat.S_ISLNK(metadata.st_mode) or bool(
                getattr(metadata, "st_file_attributes", 0)
                & _WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT
            )
            if is_link:
                yield path, "link"
            elif stat.S_ISDIR(metadata.st_mode):
                child_directories.append(path)
            elif stat.S_ISREG(metadata.st_mode):
                yield path, "file"
            else:
                yield path, "special"
        pending.extend(reversed(child_directories))


def verify_pack(pack_dir: Path) -> list[str]:
    """返回问题列表；空列表表示校验通过。"""
    pack = Path(pack_dir)
    problems = _ProblemCollector()

    manifest_path = _package_member_path(pack, MANIFEST_NAME)
    if manifest_path is None:
        return [f"清单包内路径无效（必须是普通文件）：{MANIFEST_NAME}"]
    if not manifest_path.is_file():
        return [f"缺少清单文件：{MANIFEST_NAME}"]
    try:
        manifest = _load_json(manifest_path, max_bytes=_MAX_MANIFEST_JSON_BYTES)
    except (OSError, ValueError, RecursionError) as exc:
        return [f"清单文件不可解析：{exc}"]

    # ① 清单完整性
    file_entries = manifest.get("files")
    if file_entries is None:
        file_entries = []
    if not isinstance(file_entries, list):
        problems.append("清单 files 结构无效（必须是数组）")
        file_entries = []
    elif len(file_entries) > _MAX_MANIFEST_FILE_ENTRIES:
        problems.append("清单 files 条目数量超过安全上限")
        file_entries = []
    if not file_entries:
        problems.append("清单 files 为空")
    entries: list[dict] = []
    seen_entry_paths: set[str] = set()
    for index, entry in enumerate(file_entries, 1):
        if not isinstance(entry, dict):
            problems.append(f"清单 files 第 {index} 项结构无效（必须是对象）")
            continue
        if not isinstance(entry.get("path"), str) or not isinstance(entry.get("sha256"), str):
            problems.append(f"清单 files 第 {index} 项缺少有效 path 或 sha256")
            continue
        if entry["path"] in seen_entry_paths:
            problems.append(f"清单 files 第 {index} 项 path 重复")
            continue
        seen_entry_paths.add(entry["path"])
        entries.append(entry)
    hash_budget = _HashReadBudget(_MAX_PACKAGE_HASH_READ_BYTES)
    hash_budget_exceeded = False
    for entry in entries:
        rel = entry["path"]
        target = _package_member_path(pack, rel)
        if target is None:
            problems.append("清单文件项包内路径无效（必须是规范相对普通文件路径）")
            continue
        if not target.is_file():
            problems.append(f"清单登记的文件缺失：{rel}")
            continue
        try:
            target_size = target.stat().st_size
        except OSError:
            problems.append("清单登记的文件无法读取：OSError")
            continue
        if target_size > _MAX_PACKAGE_FILE_BYTES:
            problems.append("清单登记的文件超过单文件安全上限")
            continue
        if rel == EVENTS_REL:
            if target_size > _MAX_EVENT_CHAIN_TOTAL_BYTES:
                problems.append("事件链超过总输入字节数上限")
                continue
        json_limit = None
        if rel == "ticket/metadata.json":
            json_limit = _MAX_METADATA_JSON_BYTES
        elif rel == "artifacts.json":
            json_limit = _MAX_ARTIFACT_INDEX_JSON_BYTES
        elif rel == "contracts.json":
            json_limit = _MAX_CONTRACTS_JSON_BYTES
        if json_limit is not None:
            if target_size > json_limit:
                problems.append("清单登记的控制JSON超过输入字节上限")
                continue
        try:
            file_limit = _MAX_PACKAGE_FILE_BYTES
            if rel == EVENTS_REL:
                file_limit = min(file_limit, _MAX_EVENT_CHAIN_TOTAL_BYTES)
            if json_limit is not None:
                file_limit = min(file_limit, json_limit)
            actual = sha256_file(
                target, max_bytes=file_limit, read_budget=hash_budget,
            )
        except _FileSizeLimitExceeded:
            if rel == EVENTS_REL:
                problems.append("事件链超过总输入字节数上限")
            elif json_limit is not None:
                problems.append("清单登记的控制JSON超过输入字节上限")
            else:
                problems.append("清单登记的文件超过单文件安全上限")
            continue
        except _HashReadBudgetExceeded:
            problems.append("证据包累计摘要读取超过安全上限")
            hash_budget_exceeded = True
            break
        if actual != entry["sha256"]:
            problems.append(
                f"文件内容与清单不符（疑似篡改）：{rel} "
                f"清单={entry['sha256'][:12]} 实际={actual[:12]}"
            )
        size = entry.get("size")
        if isinstance(size, int) and target.stat().st_size != size:
            problems.append(f"文件大小与清单不符：{rel}")

    # ④ 包摘要
    declared = manifest.get("pack_digest")
    if declared:
        recomputed = pack_digest(entries)
        if recomputed != declared:
            problems.append(
                f"包摘要不符（清单被改动过）：声明={str(declared)[:12]} 重算={recomputed[:12]}"
            )
    else:
        problems.append("清单缺少 pack_digest")

    # ⑤ 未登记的额外文件（防止夹带内容而不被发现）
    listed = {str(e.get("path", "")) for e in entries}
    try:
        for path, kind in _walk_package_entries(pack):
            rel = path.relative_to(pack).as_posix()
            if kind in ("link", "special"):
                problems.append(f"证据包包含不允许的链接或特殊文件：{rel}")
            elif path.name != MANIFEST_NAME and rel not in listed:
                problems.append(f"存在未登记的额外文件（清单未覆盖）：{rel}")
    except _PackageEntryLimitExceeded:
        problems.append("证据包目录条目数量超过安全上限")
    except (OSError, RuntimeError, ValueError):
        problems.append("证据包目录无法完整枚举")

    # ② 工单身份：manifest、metadata 与每条 event 必须指向同一工单。
    manifest_ticket_id: str | None = None
    manifest_ticket = manifest.get("ticket")
    if not isinstance(manifest_ticket, dict):
        problems.append("清单 ticket 结构无效（必须是对象）")
    else:
        candidate = manifest_ticket.get("ticket_id")
        if not isinstance(candidate, str) or not candidate:
            problems.append("清单 ticket.ticket_id 无效")
        else:
            manifest_ticket_id = candidate

    metadata_ticket_id: str | None = None
    metadata_event_mirrors: object = _UNSET_METADATA_EVENT_MIRRORS
    metadata_agent_spawns: object = _UNSET_METADATA_AGENT_SPAWNS
    expected_metadata_hash: object = _UNSET_EXPECTED_METADATA_HASH
    expected_ticket_metadata: object = _UNSET_TICKET_METADATA
    expected_ticket_state_machine: object = _UNSET_TICKET_STATE_MACHINE
    expected_execution_model: object = _UNSET_EXECUTION_MODEL
    expected_completion_receipt: object = _UNSET_COMPLETION_RECEIPT
    metadata_path = _package_member_path(pack, "ticket/metadata.json")
    if metadata_path is None:
        problems.append("工单 metadata 包内路径无效（必须是普通文件）")
    elif not metadata_path.is_file():
        problems.append("缺少工单 metadata：ticket/metadata.json")
    else:
        try:
            metadata = _load_json(metadata_path, max_bytes=_MAX_METADATA_JSON_BYTES)
        except (OSError, ValueError, RecursionError):
            problems.append("工单 metadata 不可解析")
        else:
            expected_ticket_metadata = metadata
            try:
                expected_metadata_hash = _metadata_content_hash(metadata)
            except (TypeError, ValueError, RecursionError, UnicodeError):
                problems.append("工单 metadata 无法计算 metadata_hash_after 摘要")
                expected_metadata_hash = None
            metadata_event_mirrors = {
                event_type: _metadata_event_mirror_records(metadata, event_type)
                for event_type in _METADATA_EVENT_MIRROR_FIELDS
            }
            metadata_agent_spawns = _metadata_agent_spawn_records(metadata)
            candidate = metadata.get("ticket_id")
            if not isinstance(candidate, str) or not candidate:
                problems.append("工单 metadata.ticket_id 无效")
            else:
                metadata_ticket_id = candidate

    contracts_path = _package_member_path(pack, "contracts.json")
    if contracts_path is None:
        problems.append("contracts.json 包内路径无效（必须是普通文件）")
    elif contracts_path.is_file():
        try:
            contracts_snapshot = _load_contract_snapshot(contracts_path)
        except (OSError, ValueError, RecursionError):
            problems.append("contracts.json 不可解析或超过安全上限")
        else:
            raw_state_machine = contracts_snapshot.get("state_machine")
            if raw_state_machine is not None:
                try:
                    expected_ticket_state_machine = (
                        _normalize_ticket_state_machine(raw_state_machine)
                    )
                except (TypeError, ValueError, RecursionError):
                    problems.append("contracts.json state_machine 结构无效")
            raw_execution_model = contracts_snapshot.get("execution_model")
            if raw_execution_model is not None:
                try:
                    expected_execution_model = _normalize_execution_model(
                        raw_execution_model, snapshot=True,
                    )
                except (TypeError, ValueError, RecursionError):
                    problems.append("contracts.json execution_model 结构无效")
            if "completion_receipt" in contracts_snapshot:
                expected_completion_receipt = contracts_snapshot[
                    "completion_receipt"
                ]
    if (
        manifest_ticket_id is not None
        and metadata_ticket_id is not None
        and manifest_ticket_id != metadata_ticket_id
    ):
        problems.append("清单与工单 metadata 的 ticket_id 不一致")

    # ③ 事件链完整性
    verifications_path = _package_member_path(pack, "verifications.json")
    if verifications_path is None:
        problems.append("verifications.json 包内路径无效（必须是普通文件）")
    elif verifications_path.is_file():
        try:
            load_verifications_json(verifications_path, expected_ticket_id=metadata_ticket_id)
        except (OSError, TypeError, ValueError, UnicodeError, RecursionError, OverflowError):
            problems.append("verifications.json 不可解析或工程回执语义无效")
    events_path = _package_member_path(pack, EVENTS_REL)
    if events_path is None:
        problems.append("事件链包内路径无效（必须是普通文件）")
    elif not events_path.is_file():
        problems.append(f"缺少事件链：{EVENTS_REL}")
    else:
        try:
            artifact_facts, chain_problems = _verify_event_chain(
                events_path,
                expected_ticket_id=metadata_ticket_id,
                expected_event_mirrors=metadata_event_mirrors,
                expected_agent_spawns=metadata_agent_spawns,
                expected_metadata_hash=expected_metadata_hash,
                expected_ticket_state_machine=expected_ticket_state_machine,
                expected_execution_model=expected_execution_model,
                expected_completion_receipt=expected_completion_receipt,
                expected_ticket_metadata=expected_ticket_metadata,
            )
            problems.extend(chain_problems)
            # ④ 正文与链上哈希对应
            if not hash_budget_exceeded:
                problems.extend(_verify_artifact_binding(
                    pack, artifact_facts, read_budget=hash_budget,
                ))
        except (OSError, ValueError, RecursionError) as exc:
            problems.append(f"事件链或正文索引无法读取：{type(exc).__name__}")

    return problems.render()


MAX_EXECUTION_BINDING_ANCESTORS = 256


def execution_binding_shape_ok(binding):
    """Validate portable recorded identities without accessing the filesystem."""
    if not isinstance(binding, dict) or set(binding) != {"version", "path", "ancestors"}:
        return False
    if type(binding["version"]) is not int or binding["version"] != 1:
        return False
    raw = binding["path"]
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        return False
    cls = PureWindowsPath if PureWindowsPath(raw).is_absolute() else PurePosixPath
    root = cls(raw)
    if not root.is_absolute() or str(root) != raw or ".." in root.parts:
        return False
    depth = len(root.parents) + 1
    if depth > MAX_EXECUTION_BINDING_ANCESTORS:
        return False
    chain = list(reversed(root.parents)) + [root]
    rows = binding["ancestors"]
    if not isinstance(rows, list) or len(rows) != depth:
        return False
    for row, expected in zip(rows, chain):
        if not isinstance(row, dict) or set(row) != {"path", "device", "inode"}:
            return False
        if row["path"] != str(expected):
            return False
        if type(row["device"]) is not int or row["device"] < 0:
            return False
        if type(row["inode"]) is not int or row["inode"] <= 0:
            return False
    return True


def execution_binding_topology_ok(meta):
    if "execution_binding" not in meta:
        return True
    history = meta.get("checkout_history") or []
    return (execution_binding_shape_ok(meta["execution_binding"])
            and meta.get("active_checkout") is None
            and isinstance(history, list)
            and not any(isinstance(row, dict) and row.get("state") == "active"
                        for row in history))



class ExecutionBindingMirror:
    """Stream binding consistency and open IDs, without duplicating the event log."""
    def __init__(self, metadata):
        self.metadata = metadata
        self.binding = None
        self.seen = False
        self.open_steps = set()
        self.open_operations = set()
        self.open_agents = set()
        self.closed = False
        self.issues = set()

    def consume(self, event):
        kind = event.get("event_type")
        payload = event.get("payload")
        if not isinstance(payload, dict):
            # Missing pairing identities still represent unclosed execution.
            payload = {}
        for start, finish, key, opened in (
            ("step_started", "step_finished", "attempt", self.open_steps),
            ("operation_started", "operation_finished", "attempt", self.open_operations),
            ("agent_spawned", "agent_result", "spawn_id", self.open_agents),
        ):
            identity = payload.get(key)
            if kind == start:
                if isinstance(identity, str) and identity:
                    opened.add(identity)
                else:
                    # Legacy starts without pairing identity cannot prove quiescence.
                    opened.add(None)
            elif kind == finish and isinstance(identity, str):
                opened.discard(identity)
        if kind == "close_phase":
            self.closed = True
        elif kind == "ticket_reopened":
            self.closed = False
            if self.seen:
                self.issues.add("binding_checkout_conflict")
        if kind != "metadata_updated":
            if "execution_root_binding" in payload:
                self.issues.add("binding_wrong_event_type")
            return
        updates = payload.get("set")
        appends = payload.get("append")
        touches = ((isinstance(updates, dict) and "execution_binding" in updates)
                   or (isinstance(appends, dict) and "execution_binding" in appends))
        marked = "execution_root_binding" in payload
        if not touches and not marked:
            if self.seen:
                for change in (updates, appends):
                    if isinstance(change, dict) and change.get("active_checkout") is not None:
                        self.issues.add("binding_checkout_conflict")
                    history = change.get("checkout_history") if isinstance(change, dict) else None
                    if isinstance(history, list) and any(
                        isinstance(row, dict) and row.get("state") == "active" for row in history
                    ):
                        self.issues.add("binding_checkout_conflict")
            return
        required = {"execution_root_binding", "set", "append", "metadata_hash_after"}
        recorded_hash = payload.get("metadata_hash_after")
        if (type(payload.get("execution_root_binding")) is not int
                or payload.get("execution_root_binding") != 1
                or set(payload) != required
                or not isinstance(recorded_hash, str)
                or re.fullmatch(r"[0-9a-f]{64}", recorded_hash) is None
                or not isinstance(updates, dict)
                or set(updates) != {"execution_binding"}
                or appends != {}
                or not isinstance(event.get("request_id"), str)
                or not event["request_id"].strip()
                or event.get("actor") != "icode"):
            self.issues.add("binding_event_shape")
        if self.seen:
            self.issues.add("binding_event_duplicate")
        if self.open_steps or self.open_operations or self.open_agents or self.closed:
            self.issues.add("binding_not_quiescent")
        candidate = updates.get("execution_binding") if isinstance(updates, dict) else None
        if not execution_binding_shape_ok(candidate):
            self.issues.add("binding_shape")
        self.binding = candidate
        self.seen = True

    def finish(self):
        meta = self.metadata
        if isinstance(meta, dict):
            if not execution_binding_topology_ok(meta):
                self.issues.add("binding_checkout_conflict")
            if ("execution_binding" in meta) != self.seen:
                self.issues.add("binding_metadata_mismatch")
            elif self.seen and meta["execution_binding"] != self.binding:
                self.issues.add("binding_metadata_mismatch")
        return sorted(self.issues)


def _verify_event_chain(
    path: Path, *, expected_ticket_id: str | None = None,
    expected_event_mirrors: object = _UNSET_METADATA_EVENT_MIRRORS,
    expected_agent_spawns: object = _UNSET_METADATA_AGENT_SPAWNS,
    expected_metadata_hash: object = _UNSET_EXPECTED_METADATA_HASH,
    expected_ticket_state_machine: object = _UNSET_TICKET_STATE_MACHINE,
    expected_execution_model: object = _UNSET_EXECUTION_MODEL,
    expected_completion_receipt: object = _UNSET_COMPLETION_RECEIPT,
    expected_ticket_metadata: object = _UNSET_TICKET_METADATA,
) -> tuple[dict[str, tuple[str, str]], list[str]]:
    """逐条校验事件，只保留去重 ID 与产物绑定所需的紧凑事实。"""
    problems = _ProblemCollector()
    chain_problems = _EventChainDiagnostics()
    artifact_facts: dict[str, tuple[str, str]] = {}
    seen_ids: set[str] = set()
    previous_hash = GENESIS_HASH
    event_count = 0
    first_event_type_valid = False
    first_event_type_label = ""
    invalid_payload_kinds: set[str] = set()
    invalid_event_type_seen = False
    invalid_schema_fields: set[str] = set()
    last_metadata_hash_after: object = None
    has_metadata_hash_after = False
    compare_event_mirrors = (
        expected_event_mirrors is not _UNSET_METADATA_EVENT_MIRRORS
    )
    event_mirror_records: dict[str, list[dict]] = {}
    if compare_event_mirrors:
        if not isinstance(expected_event_mirrors, dict):
            problems.append("工单 metadata 事件镜像结构无效")
            compare_event_mirrors = False
        else:
            for event_type, metadata_field in _METADATA_EVENT_MIRROR_FIELDS.items():
                records = expected_event_mirrors.get(event_type, [])
                if records is None:
                    records = []
                if not isinstance(records, list) or not all(
                    isinstance(record, dict) for record in records
                ):
                    problems.append(
                        f"工单 metadata.{metadata_field} 结构无效 "
                        "（必须是仅含对象的数组或 null）"
                    )
                    continue
                event_mirror_records[event_type] = records
    event_mirror_indexes = {
        event_type: 0 for event_type in event_mirror_records
    }
    event_mirror_mismatches: set[str] = set()
    agent_lifecycle_mirror = None
    if expected_agent_spawns is not _UNSET_METADATA_AGENT_SPAWNS:
        agent_lifecycle_mirror = _AgentLifecycleMirror(expected_agent_spawns)
        if not agent_lifecycle_mirror.structurally_valid:
            problems.append(
                f"工单 metadata.{_METADATA_AGENT_SPAWNS_FIELD} 结构无效 "
                "（必须是仅含对象的数组或 null）"
            )
    ticket_state_mirror = _TicketStateMirror(
        expected_ticket_state_machine, expected_ticket_metadata,
    )
    binding_mirror = ExecutionBindingMirror(expected_ticket_metadata)
    execution_event_mirror = _ExecutionEventMirror(
        expected_execution_model, expected_completion_receipt,
    )

    def append_payload_shape_problems(target: _ProblemCollector) -> None:
        # Bound retained diagnostics even if a hostile event stream contains many
        # malformed payloads; one finding per category is enough to reject the pack.
        if "event" in invalid_payload_kinds:
            target.append("事件 payload 结构无效（必须是对象）")
        if "artifact_written" in invalid_payload_kinds:
            target.append("artifact_written 事件 payload 结构无效（必须是对象）")

    def append_event_type_problem(target: _ProblemCollector) -> None:
        if invalid_event_type_seen:
            target.append("事件 event_type 无效（不属于允许类型）")

    def append_event_schema_problem(target: _ProblemCollector) -> None:
        if invalid_schema_fields:
            fields = ", ".join(sorted(invalid_schema_fields))
            target.append(f"事件不符合 pinned ticket-event schema（字段：{fields}）")

    try:
        if path.stat().st_size > _MAX_EVENT_CHAIN_TOTAL_BYTES:
            problems.append("事件链超过总输入字节数上限")
            return {}, problems.render()
    except (OSError, UnicodeError) as exc:
        problems.extend(chain_problems.render())
        problems.append(f"事件链无法读取：{type(exc).__name__}")
        return {}, problems.render()

    try:
        # newline="" enables universal CR/LF framing without translating the
        # terminator, while retaining RFC-valid Unicode separators in JSON text.
        stream = path.open(encoding="utf-8", newline="")
    except (OSError, UnicodeError) as exc:
        problems.extend(chain_problems.render())
        problems.append(f"事件链无法读取：{type(exc).__name__}")
        return artifact_facts, problems.render()

    try:
        with stream:
            lineno = 0
            total_input_bytes = 0
            while True:
                # TextIO's size is in decoded characters; this is a conservative
                # allocation bound before enforcing the exact UTF-8 byte limit.
                line = stream.readline(_MAX_EVENT_CHAIN_LINE_BYTES + 1)
                if not line:
                    break
                lineno += 1
                if len(line) > _MAX_EVENT_CHAIN_LINE_BYTES:
                    problems.extend(chain_problems.render())
                    problems.append(
                        f"事件链第 {lineno} 行超过单条物理行字节数上限"
                    )
                    return {}, problems.render()
                line_bytes = len(line.encode("utf-8"))
                if line_bytes > _MAX_EVENT_CHAIN_LINE_BYTES:
                    problems.extend(chain_problems.render())
                    problems.append(
                        f"事件链第 {lineno} 行超过单条物理行字节数上限"
                    )
                    return {}, problems.render()
                total_input_bytes += line_bytes
                if total_input_bytes > _MAX_EVENT_CHAIN_TOTAL_BYTES:
                    problems.extend(chain_problems.render())
                    problems.append("事件链超过总输入字节数上限")
                    return {}, problems.render()
                # JSONL framing follows physical CR/LF lines. splitlines() also splits Unicode
                # separators (NEL/LS/PS) that are valid JSON string data.
                line = line.strip()
                if not line:
                    continue
                if event_count >= _MAX_EVENT_CHAIN_EVENT_COUNT:
                    problems.extend(chain_problems.render())
                    problems.append("事件链超过最大事件条数上限")
                    return {}, problems.render()
                try:
                    event = loads_json_value(line)
                except (RecursionError, ValueError) as exc:
                    problems.append(
                        f"事件链第 {lineno} 行 JSON 不可解析（疑似截断/篡改）：{exc}"
                    )
                    problems.extend(chain_problems.render())
                    append_payload_shape_problems(problems)
                    append_event_type_problem(problems)
                    append_event_schema_problem(problems)
                    return artifact_facts, problems.render()
                if not isinstance(event, dict):
                    problems.append(f"事件链第 {lineno} 行结构无效（必须是对象）")
                    problems.extend(chain_problems.render())
                    append_payload_shape_problems(problems)
                    append_event_type_problem(problems)
                    append_event_schema_problem(problems)
                    return artifact_facts, problems.render()

                event_count += 1
                schema_issues = event_schema_issues(
                    event, expected_ticket_id=expected_ticket_id,
                )
                invalid_schema_fields.update(schema_issues)
                if event_count == 1:
                    first_type = event.get("event_type")
                    first_event_type_valid = (
                        isinstance(first_type, str)
                        and first_type in ALLOWED_FIRST_EVENT
                    )
                    if isinstance(first_type, str):
                        first_event_type_label = repr(first_type[:160])
                        if len(first_type) > 160:
                            first_event_type_label += "..."
                    else:
                        first_event_type_label = f"<{type(first_type).__name__}>"

                event_id = event.get("event_id")
                if not isinstance(event_id, str) or not event_id:
                    chain_problems.add(
                        "event_id",
                        f"第 {event_count} 条事件 event_id 结构无效（必须是非空字符串）"
                    )
                elif "event_id" in schema_issues:
                    # Invalid IDs are already represented by the bounded schema
                    # summary. Do not retain arbitrary-length attacker strings in
                    # the duplicate-detection set or diagnostic text.
                    pass
                elif event_id in seen_ids:
                    chain_problems.add(
                        "event_id_duplicate",
                        f"第 {event_count} 条事件 event_id 重复：{event_id!r}",
                    )
                else:
                    seen_ids.add(event_id)
                if event.get("previous_event_hash") != previous_hash:
                    chain_problems.add(
                        "previous_event_hash",
                        f"第 {event_count} 条事件 previous_event_hash 断链（疑似删改事件）"
                    )
                if event.get("event_hash") != canonical_event_hash(event):
                    chain_problems.add(
                        "event_hash",
                        f"第 {event_count} 条事件 event_hash 与内容不符（疑似篡改）"
                    )
                previous_hash = event.get("event_hash", previous_hash)

                event_type = event.get("event_type")
                payload = event.get("payload")
                ticket_state_mirror.consume(event, event_count)
                binding_mirror.consume(event)
                execution_event_mirror.consume(event, event_count)
                if isinstance(payload, dict):
                    marker = payload.get("metadata_hash_after")
                    if marker:
                        last_metadata_hash_after = marker
                        has_metadata_hash_after = True
                if not isinstance(event_type, str) or event_type not in ALLOWED_EVENT_TYPES:
                    invalid_event_type_seen = True
                if (
                    agent_lifecycle_mirror is not None
                    and isinstance(event_type, str)
                    and event_type in _AGENT_LIFECYCLE_EVENT_TYPES
                ):
                    agent_lifecycle_mirror.consume(event_type, payload)
                if not isinstance(payload, dict):
                    invalid_payload_kinds.add(
                        "artifact_written" if event_type == "artifact_written" else "event"
                    )
                elif event_type == "artifact_written":
                    digest = payload.get("sha256")
                    if digest:
                        artifact_facts[str(digest)] = (
                            str(event.get("event_id")),
                            str(payload.get("path") or ""),
                        )
                if (
                    compare_event_mirrors
                    and isinstance(event_type, str)
                    and event_type in _METADATA_EVENT_MIRROR_FIELDS
                    and event_type in event_mirror_records
                ):
                    metadata_field = _METADATA_EVENT_MIRROR_FIELDS[event_type]
                    expected_records = event_mirror_records[event_type]
                    record_index = event_mirror_indexes[event_type]
                    mismatch = record_index >= len(expected_records)
                    if (
                        not mismatch
                        and isinstance(payload, dict)
                        and not _event_payload_matches_metadata_record(
                            payload, expected_records[record_index],
                        )
                    ):
                        mismatch = True
                    if mismatch and event_type not in event_mirror_mismatches:
                        problems.append(
                            f"{event_type} 事件与 metadata.{metadata_field} 不一致"
                        )
                        event_mirror_mismatches.add(event_type)
                    event_mirror_indexes[event_type] += 1
    except (OSError, UnicodeError) as exc:
        problems.append(f"事件链无法读取：{type(exc).__name__}")
        problems.extend(chain_problems.render())
        append_event_schema_problem(problems)
        return {}, problems.render()

    problems.extend(chain_problems.render())
    if event_count and not first_event_type_valid:
        problems.append(
            f"首条事件类型为 {first_event_type_label}，应为 {sorted(ALLOWED_FIRST_EVENT)} 之一"
        )
    append_payload_shape_problems(problems)
    append_event_type_problem(problems)
    append_event_schema_problem(problems)
    if (
        has_metadata_hash_after
        and expected_metadata_hash is not _UNSET_EXPECTED_METADATA_HASH
        and last_metadata_hash_after != expected_metadata_hash
    ):
        problems.append(
            "事件链最终 metadata_hash_after 与工单 metadata 摘要不一致"
        )
    for event_type, records in event_mirror_records.items():
        if (
            event_mirror_indexes[event_type] != len(records)
            and event_type not in event_mirror_mismatches
        ):
            metadata_field = _METADATA_EVENT_MIRROR_FIELDS[event_type]
            problems.append(
                f"{event_type} 事件与 metadata.{metadata_field} 不一致"
            )
    if (
        agent_lifecycle_mirror is not None
        and agent_lifecycle_mirror.structurally_valid
        and not agent_lifecycle_mirror.finish()
    ):
        problems.append(
            "agent_spawned/agent_result 事件与 "
            f"metadata.{_METADATA_AGENT_SPAWNS_FIELD} 不一致"
        )
    problems.extend(ticket_state_mirror.finish())
    problems.extend(binding_mirror.finish())
    problems.extend(execution_event_mirror.finish())
    return artifact_facts, problems.render()


def _verify_artifact_binding(
    pack: Path, artifact_facts: dict[str, tuple[str, str]],
    *, read_budget: _HashReadBudget | None = None,
) -> list[str]:
    """正文快照必须与事件链上记录的 sha256 一致（D11 的核心）。"""
    problems = _ProblemCollector()
    if not artifact_facts:
        return problems.render()

    index_path = _package_member_path(pack, "artifacts.json")
    if index_path is None:
        problems.append("artifacts.json 包内路径无效（必须是普通文件）")
        return problems.render()
    if not index_path.is_file():
        problems.append("事件链存在产物记录，但缺少 artifacts.json（正文对应表）")
        return problems.render()

    try:
        index = _load_json(
            index_path, max_bytes=_MAX_ARTIFACT_INDEX_JSON_BYTES,
        )
    except (OSError, ValueError, RecursionError) as exc:
        problems.append(f"artifacts.json 不可解析：{exc}")
        return problems.render()

    artifact_entries = index.get("artifacts")
    if artifact_entries is None:
        artifact_entries = []
    if not isinstance(artifact_entries, list):
        problems.append("artifacts.json 的 artifacts 结构无效（必须是数组）")
        artifact_entries = []
    elif len(artifact_entries) > _MAX_ARTIFACT_INDEX_ENTRIES:
        problems.append("artifacts.json 的 artifacts 条目数量超过安全上限")
        return problems.render()
    snapshot_bytes = 0
    seen_snapshots: set[str] = set()
    for item in artifact_entries:
        if not isinstance(item, dict):
            continue
        snapshot_rel = item.get("snapshot")
        if not isinstance(snapshot_rel, str) or snapshot_rel in seen_snapshots:
            continue
        seen_snapshots.add(snapshot_rel)
        snapshot = _package_member_path(pack, snapshot_rel)
        if snapshot is None or not snapshot.is_file():
            continue
        try:
            snapshot_bytes += snapshot.stat().st_size
        except OSError:
            continue
        if snapshot_bytes > _MAX_PACKAGE_ARTIFACT_BYTES:
            problems.append("产物快照累计字节超过安全上限")
            return problems.render()
    bound_digests: set[str] = set()
    binding_incomplete = False
    for index_number, item in enumerate(artifact_entries, 1):
        if not isinstance(item, dict):
            problems.append(f"artifacts.json 第 {index_number} 项结构无效（必须是对象）")
            continue
        snapshot_rel = item.get("snapshot")
        if not isinstance(snapshot_rel, str):
            problems.append(f"artifacts.json 第 {index_number} 项快照包内路径无效")
            continue
        chain_hash = str(item.get("chain_sha256") or "")
        snapshot = _package_member_path(pack, snapshot_rel)
        if snapshot is None:
            problems.append(f"artifacts.json 第 {index_number} 项快照包内路径无效")
            continue
        if not snapshot.is_file():
            problems.append(f"正文快照缺失：{snapshot_rel}")
            continue
        try:
            actual = sha256_file(
                snapshot,
                max_bytes=_MAX_PACKAGE_FILE_BYTES,
                read_budget=read_budget,
            )
        except _FileSizeLimitExceeded:
            problems.append("正文快照超过单文件安全上限")
            binding_incomplete = True
            continue
        except _HashReadBudgetExceeded:
            problems.append("证据包累计摘要读取超过安全上限")
            return problems.render()
        if chain_hash and actual != chain_hash:
            problems.append(
                f"正文快照与事件链记录不符（疑似篡改）：{snapshot_rel} "
                f"链上={chain_hash[:12]} 实际={actual[:12]}"
            )
        if chain_hash and chain_hash not in artifact_facts:
            problems.append(f"artifacts.json 引用了事件链上不存在的哈希：{chain_hash[:12]}")
        bound_digests.add(actual)

    if binding_incomplete:
        return problems.render()
    missing = set(artifact_facts) - bound_digests
    for digest in sorted(missing):
        _event_id, source_path = artifact_facts[digest]
        problems.append(
            f"事件链记录的产物缺少正文快照（hash {digest[:12]}，源路径 {source_path}）"
        )
    return problems.render()


def _print_diagnostic(message: str, *, file=None) -> None:
    """Escape only characters the current diagnostic stream cannot encode."""
    stream = sys.stdout if file is None else file
    encoding = getattr(stream, "encoding", None)
    if encoding:
        # Preserve the caller's stream configuration and verifier exit status;
        # narrow consoles can still show every diagnostic as readable escapes.
        message = message.encode(encoding, errors="backslashreplace").decode(encoding)
    print(message, file=stream)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        _print_diagnostic(__doc__.strip())
        _print_diagnostic("\n用法：python verify.py <证据包目录>", file=sys.stderr)
        return 2

    pack = Path(args[0])
    if not pack.is_dir():
        _print_diagnostic(f"不是目录：{pack}", file=sys.stderr)
        return 2

    problems = verify_pack(pack)
    manifest_path = _package_member_path(pack, MANIFEST_NAME)
    ticket = ""
    if manifest_path is not None and manifest_path.is_file():
        try:
            ticket_info = _load_json(
                manifest_path, max_bytes=_MAX_MANIFEST_JSON_BYTES,
            ).get("ticket")
            if isinstance(ticket_info, dict):
                ticket = ticket_info.get("ticket_id", "")
        except (OSError, ValueError, RecursionError):
            ticket = "?"

    if problems:
        _print_diagnostic(f"证据包校验失败：{pack}")
        _print_diagnostic(f"  工单：{ticket or '?'}")
        total_count = getattr(problems, "total_count", len(problems))
        sample_count = getattr(problems, "sample_count", len(problems))
        _print_diagnostic(f"  问题 {total_count} 处（诊断样本 {sample_count} 条）：")
        for p in problems:
            _print_diagnostic(f"    - {p}")
        return 1

    _print_diagnostic(f"证据包校验通过：{pack}")
    _print_diagnostic(f"  工单：{ticket or '?'}")
    _print_diagnostic("  已核验：清单完整性 · 事件链哈希链 · 正文与链上哈希对应 · 包摘要")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
