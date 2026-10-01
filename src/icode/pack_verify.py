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
import stat
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath

_WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT = stat.FILE_ATTRIBUTE_REPARSE_POINT
_SHA256_FILE_READ_SIZE = 1024 * 1024

GENESIS_HASH = "0" * 64
MANIFEST_NAME = "manifest.json"
EVENTS_REL = "ticket/events.jsonl"

# 事件链首事件必须属于这两类（与上游一致）
ALLOWED_FIRST_EVENT = {"ticket_created", "migration_applied"}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while True:
            chunk = stream.read(_SHA256_FILE_READ_SIZE)
            if not chunk:
                break
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


def _reject_non_interoperable_values(value: object) -> None:
    """Reject lone surrogates and numbers that canonical JSON cannot represent."""
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, str):
            if any(0xD800 <= ord(char) <= 0xDFFF for char in current):
                raise ValueError("JSON 字符串包含孤立 UTF-16 代理项")
        elif isinstance(current, float) and not math.isfinite(current):
            raise ValueError("JSON 数值转换为非有限 binary64")
        elif isinstance(current, dict):
            pending.extend(current.keys())
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)


def loads_json_value(text: str) -> object:
    """Parse JSON under the same strict interoperability rules used by verify.py."""
    value = json.loads(
        text,
        object_pairs_hook=_json_object_without_duplicates,
        parse_constant=_reject_non_json_numeric_constant,
    )
    _reject_non_interoperable_values(value)
    return value


def _load_json(path: Path) -> dict:
    value = loads_json_value(Path(path).read_text(encoding="utf-8"))
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
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as iterator:
            entries = sorted(iterator, key=lambda entry: entry.name)
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
    problems: list[str] = []

    manifest_path = _package_member_path(pack, MANIFEST_NAME)
    if manifest_path is None:
        return [f"清单包内路径无效（必须是普通文件）：{MANIFEST_NAME}"]
    if not manifest_path.is_file():
        return [f"缺少清单文件：{MANIFEST_NAME}"]
    try:
        manifest = _load_json(manifest_path)
    except (OSError, ValueError, RecursionError) as exc:
        return [f"清单文件不可解析：{exc}"]

    # ① 清单完整性
    file_entries = manifest.get("files")
    if file_entries is None:
        file_entries = []
    if not isinstance(file_entries, list):
        problems.append("清单 files 结构无效（必须是数组）")
        file_entries = []
    if not file_entries:
        problems.append("清单 files 为空")
    entries: list[dict] = []
    for index, entry in enumerate(file_entries, 1):
        if not isinstance(entry, dict):
            problems.append(f"清单 files 第 {index} 项结构无效（必须是对象）")
            continue
        if not isinstance(entry.get("path"), str) or not isinstance(entry.get("sha256"), str):
            problems.append(f"清单 files 第 {index} 项缺少有效 path 或 sha256")
            continue
        entries.append(entry)
    for entry in entries:
        rel = entry["path"]
        target = _package_member_path(pack, rel)
        if target is None:
            problems.append("清单文件项包内路径无效（必须是规范相对普通文件路径）")
            continue
        if not target.is_file():
            problems.append(f"清单登记的文件缺失：{rel}")
            continue
        actual = sha256_file(target)
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
    except (OSError, RuntimeError, ValueError):
        problems.append("证据包目录无法完整枚举")

    # ② 事件链完整性
    events_path = _package_member_path(pack, EVENTS_REL)
    if events_path is None:
        problems.append("事件链包内路径无效（必须是普通文件）")
    elif not events_path.is_file():
        problems.append(f"缺少事件链：{EVENTS_REL}")
    else:
        try:
            events, chain_problems = _verify_event_chain(events_path)
            problems.extend(chain_problems)
            # ③ 正文与链上哈希对应
            problems.extend(_verify_artifact_binding(pack, events))
        except (OSError, ValueError, RecursionError) as exc:
            problems.append(f"事件链或正文索引无法读取：{type(exc).__name__}")

    return problems


def _verify_event_chain(path: Path) -> tuple[list[dict], list[str]]:
    problems: list[str] = []
    events: list[dict] = []
    try:
        stream = path.open(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return events, [f"事件链无法读取：{type(exc).__name__}"]

    try:
        with stream:
            for lineno, line in enumerate(stream, 1):
                # JSONL framing follows physical CR/LF lines. splitlines() also splits Unicode
                # separators (NEL/LS/PS) that are valid JSON string data.
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(
                        line, object_pairs_hook=_json_object_without_duplicates,
                        parse_constant=_reject_non_json_numeric_constant,
                    )
                    _reject_non_interoperable_values(event)
                except (RecursionError, ValueError) as exc:
                    problems.append(
                        f"事件链第 {lineno} 行 JSON 不可解析（疑似截断/篡改）：{exc}"
                    )
                    return events, problems
                if not isinstance(event, dict):
                    problems.append(f"事件链第 {lineno} 行结构无效（必须是对象）")
                    return events, problems
                events.append(event)
    except (OSError, UnicodeError) as exc:
        return [], [f"事件链无法读取：{type(exc).__name__}"]

    prev = GENESIS_HASH
    seen_ids: set[str] = set()
    for idx, event in enumerate(events, 1):
        event_id = event.get("event_id")
        if not isinstance(event_id, str) or not event_id:
            problems.append(f"第 {idx} 条事件 event_id 结构无效（必须是非空字符串）")
        elif event_id in seen_ids:
            problems.append(f"第 {idx} 条事件 event_id 重复：{event_id!r}")
        else:
            seen_ids.add(event_id)
        if event.get("previous_event_hash") != prev:
            problems.append(f"第 {idx} 条事件 previous_event_hash 断链（疑似删改事件）")
        if event.get("event_hash") != canonical_event_hash(event):
            problems.append(f"第 {idx} 条事件 event_hash 与内容不符（疑似篡改）")
        prev = event.get("event_hash", prev)

    if events and (
        not isinstance(events[0].get("event_type"), str)
        or events[0].get("event_type") not in ALLOWED_FIRST_EVENT
    ):
        problems.append(
            f"首条事件类型为 {events[0].get('event_type')!r}，应为 {sorted(ALLOWED_FIRST_EVENT)} 之一"
        )
    return events, problems


def _verify_artifact_binding(pack: Path, events: list[dict]) -> list[str]:
    """正文快照必须与事件链上记录的 sha256 一致（D11 的核心）。"""
    problems: list[str] = []
    if not events:
        return problems

    chain_artifacts: dict[str, str] = {}
    chain_paths: dict[str, str] = {}
    for event in events:
        if event.get("event_type") != "artifact_written":
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            problems.append("artifact_written 事件 payload 结构无效（必须是对象）")
            continue
        digest = payload.get("sha256")
        if digest:
            chain_artifacts[str(digest)] = str(event.get("event_id"))
            chain_paths[str(digest)] = str(payload.get("path") or "")

    if not chain_artifacts:
        return problems

    index_path = _package_member_path(pack, "artifacts.json")
    if index_path is None:
        problems.append("artifacts.json 包内路径无效（必须是普通文件）")
        return problems
    if not index_path.is_file():
        problems.append("事件链存在产物记录，但缺少 artifacts.json（正文对应表）")
        return problems

    try:
        index = _load_json(index_path)
    except (OSError, ValueError, RecursionError) as exc:
        problems.append(f"artifacts.json 不可解析：{exc}")
        return problems

    artifact_entries = index.get("artifacts")
    if artifact_entries is None:
        artifact_entries = []
    if not isinstance(artifact_entries, list):
        problems.append("artifacts.json 的 artifacts 结构无效（必须是数组）")
        artifact_entries = []
    bound_digests: set[str] = set()
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
        actual = sha256_file(snapshot)
        if chain_hash and actual != chain_hash:
            problems.append(
                f"正文快照与事件链记录不符（疑似篡改）：{snapshot_rel} "
                f"链上={chain_hash[:12]} 实际={actual[:12]}"
            )
        if chain_hash and chain_hash not in chain_artifacts:
            problems.append(f"artifacts.json 引用了事件链上不存在的哈希：{chain_hash[:12]}")
        bound_digests.add(actual)

    missing = set(chain_artifacts) - bound_digests
    for digest in sorted(missing):
        problems.append(
            f"事件链记录的产物缺少正文快照（hash {digest[:12]}，源路径 {chain_paths.get(digest, '?')}）"
        )
    return problems


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
            ticket_info = _load_json(manifest_path).get("ticket")
            if isinstance(ticket_info, dict):
                ticket = ticket_info.get("ticket_id", "")
        except (OSError, ValueError, RecursionError):
            ticket = "?"

    if problems:
        print(f"证据包校验失败：{pack}")
        print(f"  工单：{ticket or '?'}")
        print(f"  问题 {len(problems)} 处：")
        for p in problems:
            print(f"    - {p}")
        return 1

    print(f"证据包校验通过：{pack}")
    print(f"  工单：{ticket or '?'}")
    print("  已核验：清单完整性 · 事件链哈希链 · 正文与链上哈希对应 · 包摘要")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
