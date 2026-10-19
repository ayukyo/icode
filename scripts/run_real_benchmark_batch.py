#!/usr/bin/env python3
"""R7 后收束 W2：真实模型评测跑批驱动器（统计口径，非演示）。

对 pycalc 靶场任务连续执行 N 次完整 agent 循环（真模型 + 独立跑测试验收），
每 run 独立 backend/工作区，结果进入 R7 benchmark 账本并产出四率报告。

诚实边界（规格 §3 W2）：
- 这是单靶场任务、单一模型的口径端到端，不是多仓库公开评测；
- 失败 run 如实入账，不重试美化；
- cost 未进入 pricing 表时如实 null，不冒充数值；
- 密钥只经参数/环境传入，绝不写入任何产物。

用法：
    python scripts/run_real_benchmark_batch.py \
        --model MiniMax-M3 --base-url https://api.minimaxi.com/v1/chat/completions \
        --key-file /path/to/key --runs 5 --out-dir docs/nbl/benchmarks/<stamp>/
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from icode.approvals import DenyAllApprover  # noqa: E402
from icode.backends import build_backend  # noqa: E402
from icode.benchmark import (  # noqa: E402
    RunLedger,
    aggregate,
    render_report_markdown,
    render_report_json,
    save_ledger_json,
)
from icode.budget import Budget  # noqa: E402
from icode.config import load_settings  # noqa: E402
from icode.loop import LoopConfig  # noqa: E402
from icode.runner import DEFAULT_TASK, prepare_workspace, run_task  # noqa: E402

BATCH_SCOPE_NOTE = (
    "范围声明：单靶场任务（pycalc/DEFAULT_TASK）、单一模型、隔离工作区；"
    "这是 R7 benchmark 口径的端到端统计，不是多仓库公开评测。"
    "n=5 的样本量不足以支撑任何泛化结论。"
    "cost_usd 为 pricing 表静态估算价，不是账单。"
    "循环参数：max_turns=24、max_output_tokens=8192、max_repairs=2、预算硬停=120K tokens（hard_ratio=1.0）。"
    "pricing 表 minimax 条目已于 2026-10-19 修正（per-M 数字曾填入 per-1K 表，"
    "高估 1000 倍）；修正后 cost 为 $0.30/$1.20 per M 静态估算价，仍不是账单。"
    "驱动只产出 success/failed 两态；refused/human_intervention 为保留态。"
)


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
            capture_output=True, text=True, timeout=15,
        )
        return out.stdout.strip() if out.returncode == 0 else "unknown"
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"


def _classify(report) -> tuple[str, bool, bool]:
    """把 TaskReport 映射为 (result, first_pass, recovered)。

    recovered 口径（评审 M-B 统一后）：曾经历失败（存在修复循环）且最终
    success。失败 run 的 recovered 恒为 False——"恢复"只属于最终成功者。
    """
    if report.ok:
        first_pass = not report.repair_attempts
        return ("success", first_pass, bool(report.repair_attempts))
    # refused/human_intervention 为保留态：驱动不启用审批类判定规则（规格 v1.1）
    return ("failed", False, False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--key-file", required=True)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--fixture", default="pycalc")
    parser.add_argument("--budget-tokens", type=int, default=120_000)
    parser.add_argument("--max-turns", type=int, default=24)
    parser.add_argument("--max-repairs", type=int, default=2)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--task", default=None, help="默认 DEFAULT_TASK")
    parser.add_argument("--task-id", default=None,
                        help="任务集标识，默认 <fixture>/default")
    args = parser.parse_args()
    if args.runs < 1 or args.runs > 20:
        print("runs 必须在 1..20", file=sys.stderr)
        return 2

    settings = load_settings()
    commit = _git_commit()
    task_text = args.task or DEFAULT_TASK
    task_digest = hashlib.sha256(task_text.encode("utf-8")).hexdigest()
    out_dir = Path(args.out_dir)
    (out_dir / "runs").mkdir(parents=True, exist_ok=True)

    task_id = args.task_id or f"{args.fixture}/default"
    ledger = RunLedger(max_records=args.runs)
    totals_hint = {"calls": 0, "total_tokens": 0}
    for index in range(1, args.runs + 1):
        run_id = f"minimax-m3-pycalc-{index:02d}"
        print(f"=== run {index}/{args.runs} ({run_id}) ===", flush=True)
        try:
            with tempfile.TemporaryDirectory(prefix="icode-bench-") as raw:
                workspace = prepare_workspace(
                    args.fixture, Path(raw) / args.fixture, repo_root=REPO_ROOT)
                backend = build_backend(
                    "openai-compatible", key_file=args.key_file, model=args.model,
                    base_url=args.base_url,
                )
                try:
                    report = run_task(
                        settings, backend=backend, workspace=workspace,
                        task=task_text, approver=DenyAllApprover(),
                        loop_config=LoopConfig(max_turns=args.max_turns,
                                               max_output_tokens=8192),
                        budget=Budget(expected_tokens=args.budget_tokens,
                                      hard_ratio=1.0),
                        max_repairs=args.max_repairs,
                    )
                    error_code = ""
                except Exception as exc:  # noqa: BLE001 - 环境/预算异常也是统计事实
                    report = None
                    error_code = type(exc).__name__
                    print(f"run 异常：{error_code}", flush=True)
        except Exception as exc:  # noqa: BLE001 - m1：构造失败也如实入账
            report = None
            error_code = type(exc).__name__
            backend = None
            print(f"run 构造失败：{error_code}", flush=True)
        usage = getattr(backend, "usage", None) if backend is not None else None
        metrics = usage.as_metrics() if usage is not None else {}
        if report is None:
            result, first_pass, recovered = "failed", False, False
            exit_code = -1
            changed = []
            repairs = 0
        else:
            result, first_pass, recovered = _classify(report)
            exit_code = report.exit_code
            changed = list(report.changed_files)[:32]
            repairs = len(report.repair_attempts)
        record = {
            "run_id": run_id,
            "task_id": task_id,
            "repo": "ayukyo/icode",
            "commit": commit,
            "backend": "openai-compatible",
            "model": args.model,
            "result": result,
            "first_pass": first_pass,
            "recovered": recovered,
            "prompt_tokens": int(metrics.get("prompt_tokens", 0) or 0),
            "completion_tokens": int(metrics.get("completion_tokens", 0) or 0),
            "total_tokens": int(metrics.get("total_tokens", 0) or 0),
            "latency_ms": int(metrics.get("latency_ms", 0) or 0),
            "cost_usd": metrics.get("cost_usd"),
            "task_digest": task_digest,
            "budget": {
                "max_tokens": args.budget_tokens,
                "max_cost_usd": None,
                "max_minutes": None,
            },
        }
        try:
            ledger.append(record)
        except Exception as exc:  # noqa: BLE001
            print(f"记录入账失败：{exc}", file=sys.stderr)
            return 1
        totals_hint["calls"] += int(metrics.get("calls", 0) or 0)
        totals_hint["total_tokens"] += record["total_tokens"]
        raw = {
            "run_id": run_id,
            "result": result,
            "first_pass": first_pass,
            "recovered": recovered,
            "exit_code": exit_code,
            "error_code": error_code,
            "repairs": repairs,
            "changed_files": changed,
            "usage": metrics,
            "ok_detail": None if report is None else bool(report.ok),
            "error_text": None if report is None else (report.error or "")[:512],
        }
        (out_dir / "runs" / f"raw-{index:02d}.json").write_text(
            json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # m1：增量落盘——任一后续 run 崩溃，已完成的样本仍在账本
        save_ledger_json(ledger, out_dir / "ledger.json")
        print(f"  → {result} tokens={record['total_tokens']:,} "
              f"(累计 {totals_hint['total_tokens']:,})", flush=True)

    save_ledger_json(ledger, out_dir / "ledger.json")
    (out_dir / "report.md").write_text(
        BATCH_SCOPE_NOTE + "\n\n" + render_report_markdown(ledger), encoding="utf-8")
    (out_dir / "report.json").write_text(
        json.dumps({**aggregate(ledger), "scope_note": BATCH_SCOPE_NOTE},
                   ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    print("BATCH_DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
