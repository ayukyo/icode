#!/usr/bin/env python3
"""证据包独立校验器（零依赖，**不 import 本仓任何代码**）。

这个文件会被原样复制进证据包。它的存在意义是：
**审计方不需要安装、也不需要信任 icode-agent，就能独立校验证据包是否被篡改。**

它只做四件事：
    ① 清单完整性 —— manifest.files 里每个文件的 sha256 与实际一致
    ② 事件链完整性 —— 逐行复算 canonical_event_hash、检查 previous 链接、event_id 唯一
    ③ 正文与链上哈希对应 —— 产物正文快照的 sha256 必须等于事件 payload 里记录的 sha256
    ④ 包摘要 —— 重算 pack_digest 与 manifest 声明值一致

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
_UNSET_METADATA_EVENT_MIRRORS = object()

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
            metadata_event_mirrors = {
                event_type: _metadata_event_mirror_records(metadata, event_type)
                for event_type in _METADATA_EVENT_MIRROR_FIELDS
            }
            candidate = metadata.get("ticket_id")
            if not isinstance(candidate, str) or not candidate:
                problems.append("工单 metadata.ticket_id 无效")
            else:
                metadata_ticket_id = candidate
    if (
        manifest_ticket_id is not None
        and metadata_ticket_id is not None
        and manifest_ticket_id != metadata_ticket_id
    ):
        problems.append("清单与工单 metadata 的 ticket_id 不一致")

    # ③ 事件链完整性
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


def _verify_event_chain(
    path: Path, *, expected_ticket_id: str | None = None,
    expected_event_mirrors: object = _UNSET_METADATA_EVENT_MIRRORS,
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
                if not isinstance(event_type, str) or event_type not in ALLOWED_EVENT_TYPES:
                    invalid_event_type_seen = True
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
    for event_type, records in event_mirror_records.items():
        if (
            event_mirror_indexes[event_type] != len(records)
            and event_type not in event_mirror_mismatches
        ):
            metadata_field = _METADATA_EVENT_MIRROR_FIELDS[event_type]
            problems.append(
                f"{event_type} 事件与 metadata.{metadata_field} 不一致"
            )
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


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print(__doc__.strip())
        print("\n用法：python verify.py <证据包目录>", file=sys.stderr)
        return 2

    pack = Path(args[0])
    if not pack.is_dir():
        print(f"不是目录：{pack}", file=sys.stderr)
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
        print(f"证据包校验失败：{pack}")
        print(f"  工单：{ticket or '?'}")
        total_count = getattr(problems, "total_count", len(problems))
        sample_count = getattr(problems, "sample_count", len(problems))
        print(f"  问题 {total_count} 处（诊断样本 {sample_count} 条）：")
        for p in problems:
            print(f"    - {p}")
        return 1

    print(f"证据包校验通过：{pack}")
    print(f"  工单：{ticket or '?'}")
    print("  已核验：清单完整性 · 事件链哈希链 · 正文与链上哈希对应 · 包摘要")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
