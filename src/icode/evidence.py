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
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import __version__
from .contracts import ContractSet
from .pack_verify import EVENTS_REL, verify_pack

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


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _read_events(out_dir: Path) -> list[dict]:
    path = Path(out_dir) / EVENTS_NAME
    if not path.is_file():
        raise EvidenceError(f"事件链不存在：{path}")
    events: list[dict] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise EvidenceError(f"事件链第 {lineno} 行不可解析：{exc}") from None
    return events


def _safe_name(text: str) -> str:
    keep = [c if (c.isalnum() or c in "-_.") else "_" for c in text]
    return "".join(keep).strip("_") or "artifact"


def _snapshot_artifacts(
    out_dir: Path, events: list[dict], bodies_dir: Path
) -> tuple[list[dict], list[str], list[str]]:
    """把链上登记的产物正文快照进包里，并建立正文↔链上哈希的对应表。"""
    from .pack_verify import sha256_file

    entries: list[dict] = []
    problems: list[str] = []
    warnings: list[str] = []

    for index, event in enumerate(events, 1):
        if event.get("event_type") != "artifact_written":
            continue
        payload = event.get("payload") or {}
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
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    ticket_id = str(meta.get("ticket_id") or "UNKNOWN")

    events = _read_events(out_dir)
    if not events:
        raise EvidenceError("事件链为空，无法导出证据包")

    if clean and dest.exists():
        shutil.rmtree(dest)
    (dest / "ticket" / "bodies").mkdir(parents=True, exist_ok=True)

    # 1) 原样拷贝账本与元数据
    shutil.copyfile(out_dir / EVENTS_NAME, dest / EVENTS_REL)
    shutil.copyfile(meta_path, dest / "ticket" / "metadata.json")

    # 2) 产物正文快照 + 对应表
    artifacts, problems, warnings = _snapshot_artifacts(out_dir, events, dest / "ticket" / "bodies")
    (dest / "artifacts.json").write_text(
        json.dumps({"schema_version": PACK_SCHEMA_VERSION, "artifacts": artifacts},
                   ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )

    # 3) 契约快照
    steps = {
        str((e.get("payload") or {}).get("step"))
        for e in events
        if e.get("event_type") == "step_started" and (e.get("payload") or {}).get("step")
    }
    if gates_json is not None and Path(gates_json).is_file():
        (dest / "contracts.json").write_text(
            json.dumps(_contract_snapshot(Path(gates_json), steps),
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
            "event_count": len(events),
            "artifact_count": len(artifacts),
            "steps": sorted(s for s in steps if s),
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
        event_count=len(events),
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
