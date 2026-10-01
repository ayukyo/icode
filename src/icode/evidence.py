"""证据包导出（Phase 3 · 产品形态）。

一句话：**把"过程"导出成外部可独立校验的凭证**。

包内包含（D11）：
    - 事件链原样（哈希序列，唯一执行账本）
    - **正文快照 + 与链上 sha256 的对应表**（链上只存摘要，审计方需要正文才能核实）
    - 产物及其 sha256
    - 验证回执（含外部命令退出码）
    - 该步骤的契约快照（来自 gates.json，只读）
    - **独立校验器 `verify.py`**（零依赖、不 import 本仓任何代码）

诚实边界（会写进包内 README，不得省略）：
    - 本包证明的是"事件链自洽 + 正文与链上哈希对应"，不是"代码绝对正确"；
    - 包摘要 `pack_digest` 需要**外部渠道锚定**才有抗抵赖力，否则可被整体重签；
    - 权限模型是**应用层限制，不是沙箱**（沙箱在 Phase 5 之前不存在）。
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import __version__
from .contracts import ContractSet
from .pack_verify import (
    ALLOWED_EVENT_TYPES,
    EVENTS_REL,
    event_schema_issues,
    loads_json_value,
    verify_pack,
)

METADATA_NAME = ".ico_metadata.json"
EVENTS_NAME = ".ico_events.jsonl"

PACK_KIND = "icode-evidence-pack"
PACK_SCHEMA_VERSION = 1


class EvidenceError(RuntimeError):
    """证据包构建失败。"""


@dataclass
class PackReport:
    ok: bool
    pack_dir: str
    ticket_id: str
    event_count: int = 0
    artifact_count: int = 0
    pack_digest: str = ""
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    selfcheck_ok: bool = False

    def render(self) -> str:
        lines = [
            "证据包导出",
            f"  包目录：{self.pack_dir}",
            f"  工单：{self.ticket_id}",
            f"  事件：{self.event_count} 条；产物：{self.artifact_count} 个",
            f"  包摘要：{self.pack_digest[:16]}…" if self.pack_digest else "  包摘要：（未生成）",
            f"  自校验（用包内 verify.py 逻辑回校）：{'通过' if self.selfcheck_ok else '未通过'}",
        ]
        if self.warnings:
            lines += ["", "  提示："] + [f"    - {w}" for w in self.warnings]
        if self.problems:
            lines += ["", "  问题："] + [f"    - {p}" for p in self.problems]
        lines += ["", "结果：" + ("通过" if self.ok else "未通过")]
        return "\n".join(lines)


@dataclass
class _EventSummary:
    """导出所需的紧凑事件事实，不保留非产物事件正文。"""

    event_count: int = 0
    steps: set[str] = field(default_factory=set)
    artifact_events: list[dict] = field(default_factory=list)


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _read_events(out_dir: Path, *, expected_ticket_id: str) -> _EventSummary:
    path = Path(out_dir) / EVENTS_NAME
    if not path.is_file():
        raise EvidenceError(f"事件链不存在：{path}")
    summary = _EventSummary()
    try:
        with path.open(encoding="utf-8") as stream:
            for lineno, line in enumerate(stream, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    event = loads_json_value(line)
                except (RecursionError, ValueError) as exc:
                    raise EvidenceError(
                        f"事件链第 {lineno} 行不可解析：{exc}"
                    ) from None
                if not isinstance(event, dict):
                    raise EvidenceError(
                        f"事件链第 {lineno} 行结构无效（必须是对象）"
                    )

                summary.event_count += 1
                event_type = event.get("event_type")
                if not isinstance(event_type, str) or event_type not in ALLOWED_EVENT_TYPES:
                    raise EvidenceError(
                        f"事件链第 {lineno} 行 event_type 无效（不属于允许类型）"
                    )
                payload = event.get("payload")
                if not isinstance(payload, dict):
                    raise EvidenceError(
                        f"事件链第 {lineno} 行 payload 结构无效（必须是对象）"
                    )
                schema_issues = event_schema_issues(
                    event, expected_ticket_id=expected_ticket_id,
                )
                if schema_issues:
                    fields = ", ".join(sorted(schema_issues))
                    raise EvidenceError(
                        f"事件链第 {lineno} 行不符合 pinned ticket-event schema "
                        f"（字段：{fields}）"
                    )
                if event_type not in ("step_started", "artifact_written"):
                    continue
                if event_type == "step_started":
                    step = payload.get("step")
                    if step:
                        summary.steps.add(str(step))
                    continue

                summary.artifact_events.append({
                    "event_id": event.get("event_id"),
                    "event_index": summary.event_count,
                    "payload": {
                        key: payload.get(key)
                        for key in ("path", "sha256", "output", "step", "scope", "size")
                    },
                })
    except (OSError, UnicodeError) as exc:
        raise EvidenceError(f"事件链无法读取：{type(exc).__name__}") from None
    return summary


def _safe_name(text: str) -> str:
    keep = [c if (c.isalnum() or c in "-_.") else "_" for c in text]
    return "".join(keep).strip("_") or "artifact"


def _snapshot_artifacts(
    out_dir: Path, artifact_events: list[dict], bodies_dir: Path
) -> tuple[list[dict], list[str], list[str]]:
    """把链上登记的产物正文快照进包里，并建立正文↔链上哈希的对应表。"""
    from .pack_verify import sha256_file

    entries: list[dict] = []
    problems: list[str] = []
    warnings: list[str] = []

    for event in artifact_events:
        index = event["event_index"]
        payload = event["payload"]
        source = Path(str(payload.get("path") or ""))
        chain_hash = str(payload.get("sha256") or "")
        output_id = str(payload.get("output") or "artifact")
        entry = {
            "output": output_id,
            "step": payload.get("step"),
            "scope": payload.get("scope"),
            "source_path": str(source),
            "chain_sha256": chain_hash,
            "snapshot": "",
            "snapshot_sha256": "",
            "size": payload.get("size"),
            "event_id": event.get("event_id"),
            "event_index": index,
            "matches_chain": False,
        }
        if not source.is_file():
            problems.append(f"链上登记的产物已不在原路径，无法取证：{source}（output={output_id}）")
            entries.append(entry)
            continue

        actual = sha256_file(source)
        if actual != chain_hash:
            warnings.append(
                f"产物当前内容与链上记录不一致（可能事后被修改）：{source} "
                f"链上={chain_hash[:12]} 实际={actual[:12]}"
            )
        name = _safe_name(f"{output_id}__{source.name}")
        snapshot = bodies_dir / name
        if snapshot.exists():
            name = _safe_name(f"{output_id}__{index}_{source.name}")
            snapshot = bodies_dir / name
        shutil.copyfile(source, snapshot)
        entry["snapshot"] = f"{EVENTS_REL.rsplit('/', 1)[0]}/bodies/{name}"
        entry["snapshot_sha256"] = sha256_file(snapshot)
        entry["matches_chain"] = entry["snapshot_sha256"] == chain_hash
        entries.append(entry)

    return entries, problems, warnings


def _contract_snapshot(gates_json: Path, steps: set[str]) -> dict:
    contracts = ContractSet.load(gates_json)
    out: dict[str, dict] = {}
    for step in sorted(steps):
        if not contracts.has(step):
            continue
        raw = contracts.raw().get("step_contracts", {}).get(step)
        if raw is not None:
            out[step] = raw
    return {
        "schema_version": PACK_SCHEMA_VERSION,
        "source": "icode-skill/mcp/workflow-gate/gates.json",
        "gates_schema_version": contracts.schema_version,
        "steps": out,
    }


PACK_README = """# 证据包（{ticket_id}）

由 **icode-agent {version}** 于 {generated_at} 导出。

## 这个包证明什么

1. **事件链自洽** —— 每条事件的 `event_hash` 与其内容一致，且 `previous_event_hash` 逐条链接，
   首条为 `ticket_created`。任何人删改、插入、重排事件都会被检出。
2. **正文与链上哈希对应** —— 链上只存 sha256（不存正文），本包附上正文快照 +
   `artifacts.json` 对应表；校验器会重算正文 sha256 并与链上记录比对。
3. **清单与包摘要** —— `manifest.json` 记录每个文件的 sha256 与 `pack_digest`。

## 校验方法（不需要安装 icode-agent）

```bash
python verify.py <本包目录>
```

`verify.py` 是**零依赖、不 import 本项目任何代码**的独立校验器，
只依赖 Python 标准库。退出码：0 通过 / 1 被篡改或缺缺失 / 2 用法错误。

## 诚实边界（请务必阅读）

- 本包证明的是「**过程记录自洽且未被篡改**」，**不是**「代码绝对正确」。
- `pack_digest` 需要**外部渠道锚定**（如发布到工单系统、邮件、日志留存）才具备抗抵赖力，
  否则持有整包的人可以整体重签。
- 当前权限模型是**应用层限制，不是内核级沙箱**；沙箱在路线图 Phase 5 之前并不存在，
  本项目不宣称"安全沙箱"。
- 推理门禁：本运行时尚未接入上游要求的 `sequential-thinking` 机制，
  相关 trace 会如实标记为 `degraded`，**不冒充已满足**。

## 目录结构

```
manifest.json      包清单 + 包摘要
ticket/events.jsonl    事件链（唯一执行账本，原样）
ticket/metadata.json   工单状态元数据
ticket/bodies/         产物正文快照
artifacts.json     正文快照 ↔ 链上哈希 对应表
contracts.json     本工单涉及步骤的契约快照（来自 gates.json）
verifications.json 外部验证回执（如测试命令退出码）
verify.py          独立校验器
```
"""


def build_evidence_pack(
    out_dir: Path | str,
    *,
    dest: Path | str,
    gates_json: Path | None = None,
    verifications: list[dict] | None = None,
    clean: bool = True,
) -> PackReport:
    """把一条完成（或部分完成）的工单导出为证据包。"""
    out_dir = Path(out_dir).resolve()
    dest = Path(dest).resolve()

    meta_path = out_dir / METADATA_NAME
    if not meta_path.is_file():
        raise EvidenceError(f"不是 v3 工单目录（缺 {METADATA_NAME}）：{out_dir}")
    try:
        meta = loads_json_value(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError) as exc:
        raise EvidenceError(
            f"工单 metadata 不可解析：{type(exc).__name__}"
        ) from None
    if not isinstance(meta, dict):
        raise EvidenceError("工单 metadata 结构无效（必须是对象）")
    ticket_id = meta.get("ticket_id")
    if not isinstance(ticket_id, str) or not ticket_id:
        raise EvidenceError("工单 metadata 缺少有效 ticket_id")

    event_summary = _read_events(out_dir, expected_ticket_id=ticket_id)
    if not event_summary.event_count:
        raise EvidenceError("事件链为空，无法导出证据包")

    if clean and dest.exists():
        shutil.rmtree(dest)
    (dest / "ticket" / "bodies").mkdir(parents=True, exist_ok=True)

    # 1) 原样拷贝账本与元数据
    shutil.copyfile(out_dir / EVENTS_NAME, dest / EVENTS_REL)
    shutil.copyfile(meta_path, dest / "ticket" / "metadata.json")

    # 2) 产物正文快照 + 对应表
    artifacts, problems, warnings = _snapshot_artifacts(
        out_dir, event_summary.artifact_events, dest / "ticket" / "bodies",
    )
    (dest / "artifacts.json").write_text(
        json.dumps({"schema_version": PACK_SCHEMA_VERSION, "artifacts": artifacts},
                   ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )

    # 3) 契约快照
    if gates_json is not None and Path(gates_json).is_file():
        (dest / "contracts.json").write_text(
            json.dumps(_contract_snapshot(Path(gates_json), event_summary.steps),
                       ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    else:
        warnings.append("未提供 gates.json，未包含契约快照")

    # 4) 外部验证回执（R3：VerificationEvidence 会自动序列化成绑定回执）
    receipts: list[dict] = []
    for verification in (verifications or []):
        if isinstance(verification, dict):
            receipts.append(verification)
        elif hasattr(verification, "to_receipt"):
            receipts.append(verification.to_receipt())
        else:
            receipts.append({"kind": "verification", "note": str(verification)})
    # R3：事件链里通过 record-verification 登记过的验证 run（verification_recorded
    # 事件 + metadata.verification_runs）也一并纳入回执，让回归证据随包可取证。
    for run in (meta.get("verification_runs") or []):
        if not isinstance(run, dict):
            continue
        receipts.append({
            "kind": "verification_recorded",
            "fingerprint": run.get("evidence", ""),
            "baseline": run.get("baseline", ""),
            "outcome": run.get("outcome", ""),
            "layer": run.get("layer", ""),
            "scenario": run.get("scenario", ""),
            "note": run.get("note", ""),
            "run_id": run.get("run_id", ""),
            "recorded_at": run.get("at", ""),
        })
    (dest / "verifications.json").write_text(
        json.dumps({"schema_version": PACK_SCHEMA_VERSION, "receipts": receipts},
                   ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if not receipts:
        warnings.append("未包含外部验证回执（如测试命令退出码），证据力受限")

    # 5) 独立校验器（原样复制，保持零依赖）
    import codecs

    from . import pack_verify

    verifier_src = Path(pack_verify.__file__).read_bytes().decode("utf-8")
    (dest / "verify.py").write_bytes(codecs.BOM_UTF8 + verifier_src.encode("utf-8"))
    (dest / "README.md").write_text(
        PACK_README.format(ticket_id=ticket_id, version=__version__, generated_at=_now()),
        encoding="utf-8",
    )

    # 6) 清单（最后生成，覆盖以上所有文件；manifest 自身不列入，避免自引用）
    from .pack_verify import pack_digest, sha256_file

    entries: list[dict] = []
    for path in sorted(dest.rglob("*")):
        if not path.is_file() or path.name == "manifest.json":
            continue
        entries.append({
            "path": path.relative_to(dest).as_posix(),
            "sha256": sha256_file(path),
            "size": path.stat().st_size,
        })
    digest = pack_digest(entries)
    manifest = {
        "schema_version": PACK_SCHEMA_VERSION,
        "pack_kind": PACK_KIND,
        "generated_at": _now(),
        "generator": {"name": "icode-agent", "version": __version__},
        "ticket": {
            "ticket_id": ticket_id,
            "status": meta.get("status"),
            "requirement": meta.get("requirement"),
        },
        "scope": {
            "event_count": event_summary.event_count,
            "artifact_count": len(artifacts),
            "steps": sorted(s for s in event_summary.steps if s),
        },
        "hash_algorithm": "sha256",
        "canonical_json": {"ensure_ascii": False, "sort_keys": True, "separators": [",", ":"]},
        "event_chain": {
            "genesis_hash": "0" * 64,
            "note": "event_hash = sha256(规范JSON(事件去除 event_hash 字段))",
        },
        "files": entries,
        "pack_digest": digest,
        "boundaries": [
            "证明过程记录自洽且未被篡改，不证明代码绝对正确",
            "pack_digest 需外部锚定才具抗抵赖力",
            "权限模型为应用层限制，非内核级沙箱",
            "未接入 sequential-thinking，推理 trace 如实标 degraded",
        ],
    }
    (dest / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # 7) 自校验：用**包内同一套校验逻辑**回校（不是另写一份）
    selfcheck_problems = verify_pack(dest)
    problems.extend(selfcheck_problems)

    return PackReport(
        ok=not problems,
        pack_dir=str(dest),
        ticket_id=ticket_id,
        event_count=event_summary.event_count,
        artifact_count=len(artifacts),
        pack_digest=digest,
        problems=problems,
        warnings=warnings,
        selfcheck_ok=not selfcheck_problems,
    )


def collect_verifications(exit_code: int, argv: list[str], output: str) -> dict:
    """构造一条外部验证回执（例如独立跑 unittest 的结果）。"""
    import hashlib

    return {
        "kind": "command",
        "argv": list(argv),
        "exit_code": int(exit_code),
        "captured_at": _now(),
        "output_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
        "output_tail": "\n".join(output.strip().splitlines()[-8:]),
    }


def save_verification_receipt(evidence: object, destination: Path | str) -> Path:
    """原子创建一份独立验证回执；目标已存在或父目录缺失时绝不覆盖/创建。"""
    from .self_verify import VerificationEvidence

    if not isinstance(evidence, VerificationEvidence):
        raise EvidenceError("验证证据不支持回执序列化")

    try:
        receipt = evidence.to_receipt()
        if not isinstance(receipt, dict):
            raise EvidenceError("验证回执必须是 JSON 对象")
        payload = (
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
    except EvidenceError:
        raise
    except (AttributeError, OverflowError, RecursionError, TypeError, ValueError, UnicodeError):
        raise EvidenceError("验证回执无法编码为 JSON") from None

    try:
        target = Path(destination)
        target_value = os.fspath(target)
    except (TypeError, ValueError):
        raise EvidenceError("验证回执目标文件名无效") from None
    if "\x00" in target_value or target.name in ("", ".", ".."):
        raise EvidenceError("验证回执目标文件名无效")
    if not target.parent.is_dir():
        raise EvidenceError("验证回执父目录不存在")

    descriptor = -1
    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", dir=target.parent,
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        # Hard-link publication is atomic and fails if the destination exists.
        # This keeps a partially written receipt from appearing at its final name.
        os.link(temporary_path, target)
        return target
    except FileExistsError:
        raise EvidenceError("验证回执目标已存在，拒绝覆盖") from None
    except OSError:
        raise EvidenceError("验证回执无法安全写入或发布") from None
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except OSError:
                pass
