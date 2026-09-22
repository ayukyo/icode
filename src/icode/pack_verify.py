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
import sys
from pathlib import Path

GENESIS_HASH = "0" * 64
MANIFEST_NAME = "manifest.json"
EVENTS_REL = "ticket/events.jsonl"

# 事件链首事件必须属于这两类（与上游一致）
ALLOWED_FIRST_EVENT = {"ticket_created", "migration_applied"}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


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


def _load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def verify_pack(pack_dir: Path) -> list[str]:
    """返回问题列表；空列表表示校验通过。"""
    pack = Path(pack_dir)
    problems: list[str] = []

    manifest_path = pack / MANIFEST_NAME
    if not manifest_path.is_file():
        return [f"缺少清单文件：{MANIFEST_NAME}"]
    try:
        manifest = _load_json(manifest_path)
    except (json.JSONDecodeError, OSError) as exc:
        return [f"清单文件不可解析：{exc}"]

    # ① 清单完整性
    entries = manifest.get("files") or []
    if not entries:
        problems.append("清单 files 为空")
    for entry in entries:
        rel = str(entry.get("path", ""))
        target = pack / rel
        if not target.is_file():
            problems.append(f"清单登记的文件缺失：{rel}")
            continue
        actual = sha256_file(target)
        if actual != entry.get("sha256"):
            problems.append(
                f"文件内容与清单不符（疑似篡改）：{rel} "
                f"清单={str(entry.get('sha256'))[:12]} 实际={actual[:12]}"
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
    for path in sorted(pack.rglob("*")):
        if not path.is_file() or path.name == MANIFEST_NAME:
            continue
        rel = path.relative_to(pack).as_posix()
        if rel not in listed:
            problems.append(f"存在未登记的额外文件（清单未覆盖）：{rel}")

    # ② 事件链完整性
    events_path = pack / EVENTS_REL
    if not events_path.is_file():
        problems.append(f"缺少事件链：{EVENTS_REL}")
    else:
        events, chain_problems = _verify_event_chain(events_path)
        problems.extend(chain_problems)
        # ③ 正文与链上哈希对应
        problems.extend(_verify_artifact_binding(pack, events))

    return problems


def _verify_event_chain(path: Path) -> tuple[list[dict], list[str]]:
    problems: list[str] = []
    events: list[dict] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as exc:
            problems.append(f"事件链第 {lineno} 行 JSON 不可解析（疑似截断/篡改）：{exc}")
            return events, problems

    prev = GENESIS_HASH
    seen_ids: set[str] = set()
    for idx, event in enumerate(events, 1):
        event_id = event.get("event_id")
        if event_id in seen_ids:
            problems.append(f"第 {idx} 条事件 event_id 重复：{event_id!r}")
        seen_ids.add(event_id)
        if event.get("previous_event_hash") != prev:
            problems.append(f"第 {idx} 条事件 previous_event_hash 断链（疑似删改事件）")
        if event.get("event_hash") != canonical_event_hash(event):
            problems.append(f"第 {idx} 条事件 event_hash 与内容不符（疑似篡改）")
        prev = event.get("event_hash", prev)

    if events and events[0].get("event_type") not in ALLOWED_FIRST_EVENT:
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
        payload = event.get("payload") or {}
        digest = payload.get("sha256")
        if digest:
            chain_artifacts[str(digest)] = str(event.get("event_id"))
            chain_paths[str(digest)] = str(payload.get("path") or "")

    if not chain_artifacts:
        return problems

    index_path = pack / "artifacts.json"
    if not index_path.is_file():
        problems.append("事件链存在产物记录，但缺少 artifacts.json（正文对应表）")
        return problems

    try:
        index = _load_json(index_path)
    except (json.JSONDecodeError, OSError) as exc:
        problems.append(f"artifacts.json 不可解析：{exc}")
        return problems

    bound_digests: set[str] = set()
    for item in index.get("artifacts") or []:
        snapshot_rel = str(item.get("snapshot") or "")
        chain_hash = str(item.get("chain_sha256") or "")
        snapshot = pack / snapshot_rel
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
    manifest_path = pack / MANIFEST_NAME
    ticket = ""
    if manifest_path.is_file():
        try:
            ticket = (_load_json(manifest_path).get("ticket") or {}).get("ticket_id", "")
        except (json.JSONDecodeError, OSError):
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
