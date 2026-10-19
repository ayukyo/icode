"""可复现评测口径（R7/W4）：run 记录、账本、聚合与报告。

边界：本模块是**纯口径层**——禁网络、禁模型调用，只做记录校验、统计聚合
与报告渲染。真实评测跑批（多仓库任务集、真实模型预算、主流 Agent 对比）
属显式暂缓（规格 §5）。

反"cherry-pick"纪律（G4）：账本只增、报告必须列出全部 run、聚合与渲染
函数**没有**任何筛选/排除参数（测试做结构断言）；run 数为 0 时报告明确
"无样本，不构成统计结论"，绝不冒充统计结论。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "RESULT_STATES",
    "RUN_RECORD_FIELDS",
    "BUDGET_FIELDS",
    "RecordError",
    "LedgerFull",
    "validate_run_record",
    "RunRecord",
    "RunLedger",
    "load_ledger_json",
    "save_ledger_json",
    "aggregate",
    "render_report_json",
    "render_report_markdown",
    "main",
]

RESULT_STATES = ("success", "failed", "refused", "human_intervention")

BUDGET_FIELDS = frozenset({"max_tokens", "max_cost_usd", "max_minutes"})

RUN_RECORD_FIELDS = frozenset({
    "run_id", "task_id", "repo", "commit", "backend", "model",
    "result", "first_pass", "recovered",
    "prompt_tokens", "completion_tokens", "total_tokens",
    "latency_ms", "cost_usd", "task_digest", "budget",
})

_HEX64_RE = re.compile(r"[0-9a-f]{64}")
_FIELD_TEXT_MAX = 256
_MAX_LEDGER_RECORDS = 1024
LEDGER_SCHEMA_VERSION = 1


class RecordError(RuntimeError):
    """run 记录校验失败（稳定消息前缀 ``benchmark/``）。"""


class LedgerFull(RuntimeError):
    """账本写满 fail-closed（不静默截断、不丢样本）。"""


def _fail(message: str) -> RecordError:
    return RecordError(f"benchmark/{message}")


def _non_empty_str(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > _FIELD_TEXT_MAX:
        raise _fail(f"{label} 必须是非空且不超过 {_FIELD_TEXT_MAX} 字符的字符串")
    return value


def _non_negative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _fail(f"{label} 必须是非负整数")
    return value


def _non_negative_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise _fail(f"{label} 必须是非负数值")
    return float(value)


@dataclass(frozen=True)
class RunRecord:
    """一次评测 run 的冻结记录（字段封闭，见 RUN_RECORD_FIELDS）。"""

    run_id: str
    task_id: str
    repo: str
    commit: str
    backend: str
    model: str
    result: str
    first_pass: bool
    recovered: bool
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: int
    cost_usd: float | None
    task_digest: str
    budget: dict

    def public_projection(self) -> dict:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "repo": self.repo,
            "commit": self.commit,
            "backend": self.backend,
            "model": self.model,
            "result": self.result,
            "first_pass": self.first_pass,
            "recovered": self.recovered,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "latency_ms": self.latency_ms,
            "cost_usd": self.cost_usd,
            "task_digest": self.task_digest,
            "budget": dict(self.budget),
        }


def validate_run_record(raw: object) -> RunRecord:
    """校验并构造 run 记录：字段封闭、结果态封闭、数值非负、任务摘要 64hex。"""
    if not isinstance(raw, dict):
        raise _fail("run 记录必须是对象")
    keys = set(raw)
    if keys != set(RUN_RECORD_FIELDS):
        missing = sorted(RUN_RECORD_FIELDS - keys)
        extra = sorted(keys - RUN_RECORD_FIELDS)
        detail = []
        if missing:
            detail.append(f"缺少字段 {','.join(missing)}")
        if extra:
            detail.append(f"含未知字段 {','.join(extra)}")
        raise _fail("；".join(detail))
    for label in ("run_id", "task_id", "repo", "commit", "backend", "model"):
        _non_empty_str(raw[label], label)
    if raw["result"] not in RESULT_STATES:
        raise _fail(f"result 不在封闭结果态词表内：{raw['result']!r}")
    for label in ("first_pass", "recovered"):
        if not isinstance(raw[label], bool):
            raise _fail(f"{label} 必须是布尔")
    for label in ("prompt_tokens", "completion_tokens", "total_tokens", "latency_ms"):
        _non_negative_int(raw[label], label)
    cost_usd = raw["cost_usd"]
    if cost_usd is not None:
        _non_negative_number(cost_usd, "cost_usd")
    task_digest = raw["task_digest"]
    if not isinstance(task_digest, str) or not _HEX64_RE.fullmatch(task_digest):
        raise _fail("task_digest 必须是 64 位小写 hex")
    budget = raw["budget"]
    if not isinstance(budget, dict) or set(budget) != BUDGET_FIELDS:
        raise _fail("budget 必须恰含 max_tokens/max_cost_usd/max_minutes 三键")
    for label in ("max_tokens", "max_minutes"):
        value = budget[label]
        if value is not None:
            _non_negative_int(value, f"budget.{label}")
    max_cost = budget["max_cost_usd"]
    if max_cost is not None:
        _non_negative_number(max_cost, "budget.max_cost_usd")
    return RunRecord(
        run_id=raw["run_id"],
        task_id=raw["task_id"],
        repo=raw["repo"],
        commit=raw["commit"],
        backend=raw["backend"],
        model=raw["model"],
        result=raw["result"],
        first_pass=raw["first_pass"],
        recovered=raw["recovered"],
        prompt_tokens=raw["prompt_tokens"],
        completion_tokens=raw["completion_tokens"],
        total_tokens=raw["total_tokens"],
        latency_ms=raw["latency_ms"],
        cost_usd=None if cost_usd is None else float(cost_usd),
        task_digest=task_digest,
        budget=dict(budget),
    )


class RunLedger:
    """只增有界的 run 账本：重复 run_id 拒绝、写满 fail-closed、线程安全。"""

    def __init__(self, max_records: int = _MAX_LEDGER_RECORDS) -> None:
        if max_records < 1:
            raise _fail("max_records 必须为正")
        self._max_records = max_records
        self._records: list[RunRecord] = []
        self._seen_run_ids: set[str] = set()

    def __len__(self) -> int:
        return len(self._records)

    def append(self, raw: object) -> RunRecord:
        record = validate_run_record(raw)
        if record.run_id in self._seen_run_ids:
            raise _fail(f"run_id 重复：{record.run_id}")
        if len(self._records) >= self._max_records:
            raise LedgerFull(f"benchmark/账本已满（{self._max_records} 条），fail-closed")
        self._records.append(record)
        self._seen_run_ids.add(record.run_id)
        return record

    def records(self) -> tuple[RunRecord, ...]:
        return tuple(self._records)


def load_ledger_json(path: Path | str) -> RunLedger:
    """从 JSON 文件加载账本（schema 封闭，逐条校验，重复/未知字段即失败）。"""
    path = Path(path)
    try:
        bundle = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise _fail(f"账本文件不可解析：{type(exc).__name__}") from None
    if not isinstance(bundle, dict) or set(bundle) != {"schema_version", "records"}:
        raise _fail("账本文件必须恰含 schema_version 与 records 两键")
    if bundle["schema_version"] != LEDGER_SCHEMA_VERSION:
        raise _fail("账本 schema_version 不受支持")
    records = bundle["records"]
    if not isinstance(records, list):
        raise _fail("账本 records 必须是数组")
    ledger = RunLedger(max_records=max(_MAX_LEDGER_RECORDS, len(records)))
    for index, raw in enumerate(records, 1):
        try:
            ledger.append(raw)
        except RecordError as exc:
            raise _fail(f"第 {index} 条记录无效：{exc}") from None
    return ledger


def save_ledger_json(ledger: RunLedger, path: Path | str) -> Path:
    path = Path(path)
    bundle = {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "records": [r.public_projection() for r in ledger.records()],
    }
    path.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return path


def record_digest(record: RunRecord) -> str:
    """记录自摘要（canonical sha256；聚合结果可复现性的一部分）。"""
    canonical = json.dumps(
        record.public_projection(), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def aggregate(ledger: RunLedger) -> dict:
    """聚合四率与用量汇总（口径在返回值内显式写出分母定义）。

    无筛选/排除参数：所有 run 都进入统计与 runs 列表。
    """
    records = ledger.records()
    total = len(records)
    runs = [r.public_projection() for r in sorted(records, key=lambda r: r.run_id)]
    successes = sum(1 for r in records if r.result == "success")
    first_passes = sum(1 for r in records if r.first_pass)
    interventions = sum(1 for r in records if r.result == "human_intervention")
    # recovered 口径（评审 M-B 统一后）：recovered=True 的 run 必然最终 success
    # （曾经历失败后恢复）。分母 = 经历过失败的 run（非 first_pass）。
    experienced_failure = total - first_passes
    recoveries = sum(1 for r in records if r.recovered)
    rates = {
        "success_rate": {
            "value": (successes / total) if total else None,
            "denominator": "全部 run",
        },
        "first_pass_gate_rate": {
            "value": (first_passes / total) if total else None,
            "denominator": "全部 run（门禁一次通过，无重试后通过）",
        },
        "recovery_rate": {
            "value": (recoveries / experienced_failure) if experienced_failure else None,
            "denominator": "经历过失败的 run（非 first_pass）；recovered 指其中最终成功者",
        },
        "intervention_rate": {
            "value": (interventions / total) if total else None,
            "denominator": "全部 run",
        },
    }
    cost_known = all(r.cost_usd is not None for r in records)
    if not records:
        totals = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "latency_ms": 0,
            "cost_usd": None,
            "cost_usd_note": "无样本",
        }
    elif cost_known:
        totals = {
            "prompt_tokens": sum(r.prompt_tokens for r in records),
            "completion_tokens": sum(r.completion_tokens for r in records),
            "total_tokens": sum(r.total_tokens for r in records),
            "latency_ms": sum(r.latency_ms for r in records),
            "cost_usd": sum(r.cost_usd for r in records),  # type: ignore[type-var]
            "cost_usd_note": None,
        }
    else:
        totals = {
            "prompt_tokens": sum(r.prompt_tokens for r in records),
            "completion_tokens": sum(r.completion_tokens for r in records),
            "total_tokens": sum(r.total_tokens for r in records),
            "latency_ms": sum(r.latency_ms for r in records),
            "cost_usd": None,
            "cost_usd_note": "部分 run 成本未知，汇总拒绝冒充数值（沿用 Usage 纪律）",
        }
    return {
        "schema_version": 1,
        "run_count": total,
        "rates": rates,
        "totals": totals,
        "runs": runs,
    }


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def render_report_json(ledger: RunLedger) -> str:
    """JSON 报告：同输入字节级稳定（canonical json，无时间戳）。"""
    return _canonical_json(aggregate(ledger))


def render_report_markdown(ledger: RunLedger) -> str:
    """Markdown 报告：必须逐条列出全部 run（含失败样本）。"""
    report = aggregate(ledger)
    lines: list[str] = ["# icode benchmark 报告", ""]
    if report["run_count"] == 0:
        lines += [
            "无样本，不构成统计结论。",
            "",
            "本工具只提供口径与报告；真实评测跑批需另行授权执行（规格 §5 暂缓项）。",
            "",
        ]
        return "\n".join(lines)
    lines.append(f"- run 数：{report['run_count']}")
    for name, label in (
        ("success_rate", "成功率"),
        ("first_pass_gate_rate", "首次门禁通过率"),
        ("recovery_rate", "恢复率"),
        ("intervention_rate", "人工介入率"),
    ):
        entry = report["rates"][name]
        value = entry["value"]
        rendered = "n/a" if value is None else f"{value:.4f}"
        lines.append(f"- {label}：{rendered}（分母={entry['denominator']}）")
    totals = report["totals"]
    cost = totals["cost_usd"]
    cost_text = "未知（" + str(totals["cost_usd_note"]) + "）" if cost is None else f"${cost:.6f}"
    lines += [
        f"- token 合计：prompt={totals['prompt_tokens']} "
        f"completion={totals['completion_tokens']} "
        f"total={totals['total_tokens']}",
        f"- 耗时合计：{totals['latency_ms']} ms",
        f"- 成本合计：{cost_text}",
        "",
        "## 全部 run（含失败样本，无筛选）",
        "",
        "| run_id | task | repo@commit | backend/model | result | first_pass | recovered | total_tokens | cost_usd |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for run in report["runs"]:
        cost_cell = "-" if run["cost_usd"] is None else f"{run['cost_usd']:.6f}"
        lines.append(
            f"| {run['run_id']} | {run['task_id']} | {run['repo']}@{run['commit'][:12]} "
            f"| {run['backend']}/{run['model']} | {run['result']} "
            f"| {run['first_pass']} | {run['recovered']} "
            f"| {run['total_tokens']} | {cost_cell} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI 入口（无任何筛选/排除参数）：``report <ledger.json> [out.json out.md]``。"""
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] != "report" or len(args) not in (2, 4):
        print(
            "用法：python -m icode.benchmark report <ledger.json> [out.json out.md]",
            file=sys.stderr,
        )
        return 2
    try:
        ledger = load_ledger_json(args[1])
    except RecordError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if len(args) == 4:
        Path(args[2]).write_text(render_report_json(ledger) + "\n", encoding="utf-8")
        Path(args[3]).write_text(render_report_markdown(ledger), encoding="utf-8")
        return 0
    print(render_report_json(ledger))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
