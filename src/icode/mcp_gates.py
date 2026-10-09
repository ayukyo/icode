"""宿主侧 cheap-research gate 记录器。

模型不能直接写工单隐藏账本；当前 ICODE runner 也没有把 cheap-research
MCP 暴露给模型。因此在步骤产物已经落盘后，由宿主根据可复核的本地事实
写入最终 gate trace。工具未暴露时只记录结构化降级，不把降级伪装成调用成功。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

TRACE_NAME = ".mcp_gate_trace.jsonl"
_FUNCTION_RE = re.compile(r"^\s*(?:async\s+)?def\s+[A-Za-z_]\w*\s*\(", re.MULTILINE)
_CODE_SUFFIXES = {".py"}


def _catalog_constants(skill_root: Path) -> tuple[int, int]:
    """读取 vendor gate 真源；缺失时 fail closed 到最小阈值。"""
    path = Path(skill_root) / "mcp" / "cheap-research" / "gates.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        constants = dict(data.get("constants") or {})
        return int(constants["dedup_min_functions"]), int(constants["merge_min_rounds"])
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return 50, 2


def _git_root(workspace: Path) -> Path | None:
    marker = workspace / ".git"
    if not marker.exists():
        return None
    try:
        proc = subprocess.run(
            ["git", "-C", str(workspace), "rev-parse", "--show-toplevel"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False,
            timeout=5, text=True, encoding="utf-8", errors="replace",
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    root = Path(proc.stdout.strip())
    return root.resolve() if root.is_dir() else None


def _python_function_count(root: Path) -> int:
    """统计受控 Git 文件中的 Python 定义；未知语言不冒充已扫描。"""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return 0
    if proc.returncode != 0:
        return 0
    total = 0
    for raw in proc.stdout.split(b"\0"):
        if not raw:
            continue
        path = root / os.fsdecode(raw)
        if path.suffix.lower() not in _CODE_SUFFIXES or path.is_symlink() or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        total += len(_FUNCTION_RE.findall(text))
    return total


def _row(
    *, ticket_id: str, gate_id: str, tool: str, eligible: bool,
    evidence: dict, decision: str, attempted: bool, result: str,
    availability: dict | None = None,
) -> dict:
    row = {
        "schema_version": 2,
        "ticket_id": ticket_id,
        "step": "review" if gate_id.startswith("review.") else "merge",
        "gate_id": gate_id,
        "tool": tool,
        "eligible": eligible,
        "evidence": evidence,
        "decision": decision,
        "attempted": attempted,
        "result": result,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    if availability is not None:
        row["availability"] = availability
    return row


def _write_rows(out_dir: Path, rows: list[dict]) -> None:
    path = Path(out_dir) / TRACE_NAME
    existing: list[dict] = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except (UnicodeError, json.JSONDecodeError):
                continue
            if isinstance(item, dict):
                existing.append(item)
    keys = {(str(row.get("step")), str(row.get("gate_id"))) for row in rows}
    kept = [row for row in existing if (str(row.get("step")), str(row.get("gate_id"))) not in keys]
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
                for row in [*kept, *rows]),
        encoding="utf-8",
    )


def record_step_gate_trace(
    out_dir: Path, *, step: str, ticket_id: str, workspace: Path, skill_root: Path,
) -> None:
    """记录 review/merge 的 deterministic gate 结论。

    `cheap_available` 当前明确为 False：默认 runner 的工具注册表没有
    cheap-research MCP。未来实际接入后由调用方传入真实能力，而不是修改
    trace 文本来变绿。
    """
    if step not in {"review", "merge"}:
        return
    out_dir = Path(out_dir)
    workspace = Path(workspace).resolve()
    dedup_threshold, merge_threshold = _catalog_constants(Path(skill_root))
    cheap_available = False
    rg_available = shutil.which("rg") is not None
    rows: list[dict] = []

    if step == "review":
        root = _git_root(workspace)
        roots = [str(root)] if root is not None else []
        function_count = _python_function_count(root) if root is not None else 0
        rows.append(_row(
            ticket_id=ticket_id, gate_id="review.dedup", tool="extract",
            eligible=bool(roots) and rg_available and cheap_available and function_count >= dedup_threshold,
            evidence={
                "affected_repo_roots": roots,
                "function_count": function_count,
                "threshold": dedup_threshold,
                "rg_available": rg_available,
                "cheap_available": cheap_available,
                "scan_status": "python_git_files_only" if root is not None else "no_git_root",
            },
            decision="skipped_not_eligible", attempted=False, result="not_applicable",
        ))
        rounds = sorted(out_dir.glob("review_round_*.json"))
        if rounds or (out_dir / "02_review.md").is_file():
            source = rounds[-1].name if rounds else "02_review.md"
            rows.append(_row(
                ticket_id=ticket_id, gate_id="review.result_summary", tool="summarize",
                eligible=True, evidence={"result_source": source, "review_rounds": len(rounds) or 1},
                decision="unavailable_before_call", attempted=False, result="unavailable",
                availability={
                    "tool_visible": False, "discovery_ref": "icode.default_registry",
                    "reason": "not_exposed", "fallback": "merge_reads_review_round_json",
                    "evidence_ref": source,
                },
            ))
    else:
        rounds = sorted(out_dir.glob("review_round_*.json"))
        count = len(rounds)
        evidence = {"review_rounds": count, "threshold": merge_threshold}
        if count < merge_threshold:
            rows.append(_row(
                ticket_id=ticket_id, gate_id="merge.cross_round_summary", tool="summarize",
                eligible=False, evidence=evidence, decision="skipped_not_eligible",
                attempted=False, result="not_applicable",
            ))
        else:
            rows.append(_row(
                ticket_id=ticket_id, gate_id="merge.cross_round_summary", tool="summarize",
                eligible=True, evidence=evidence, decision="unavailable_before_call",
                attempted=False, result="unavailable",
                availability={
                    "tool_visible": False, "discovery_ref": "icode.default_registry",
                    "reason": "not_exposed", "fallback": "merge_reads_review_round_json",
                    "evidence_ref": "review_round_*.json",
                },
            ))
    _write_rows(out_dir, rows)
