"""R7/W4：benchmark 评测口径——记录封闭 schema、账本、聚合与报告。"""

import inspect
import json
import tempfile
import unittest
from pathlib import Path

from icode import benchmark
from icode.benchmark import (
    BUDGET_FIELDS,
    LedgerFull,
    RecordError,
    RESULT_STATES,
    RunLedger,
    aggregate,
    load_ledger_json,
    main,
    render_report_json,
    render_report_markdown,
    save_ledger_json,
    validate_run_record,
)

BUDGET = {"max_tokens": 100000, "max_cost_usd": 1.5, "max_minutes": 10}


def _raw_run(**overrides):
    base = {
        "run_id": "run-1",
        "task_id": "task-1",
        "repo": "example/repo",
        "commit": "0123456789abcdef",
        "backend": "openai-compatible",
        "model": "test-model",
        "result": "success",
        "first_pass": True,
        "recovered": False,
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150,
        "latency_ms": 1200,
        "cost_usd": 0.02,
        "task_digest": "ab" * 32,
        "budget": dict(BUDGET),
    }
    base.update(overrides)
    return base


class ValidateTests(unittest.TestCase):
    def test_valid_record_roundtrip(self):
        record = validate_run_record(_raw_run())
        self.assertEqual(record.run_id, "run-1")
        self.assertEqual(record.cost_usd, 0.02)

    def test_result_state_closed(self):
        for bad in ("OK", "passed", "", None, "Success"):
            with self.subTest(bad=bad):
                with self.assertRaises(RecordError):
                    validate_run_record(_raw_run(result=bad))

    def test_unknown_and_missing_fields_rejected(self):
        extra = _raw_run(seed=1)
        with self.assertRaises(RecordError):
            validate_run_record(extra)
        missing = _raw_run()
        del missing["first_pass"]
        with self.assertRaises(RecordError):
            validate_run_record(missing)

    def test_numeric_and_bool_discipline(self):
        with self.assertRaises(RecordError):
            validate_run_record(_raw_run(total_tokens=-1))
        with self.assertRaises(RecordError):
            validate_run_record(_raw_run(first_pass="yes"))
        with self.assertRaises(RecordError):
            validate_run_record(_raw_run(cost_usd=-0.1))
        self.assertIsNone(validate_run_record(_raw_run(cost_usd=None)).cost_usd)

    def test_task_digest_and_budget_closed(self):
        with self.assertRaises(RecordError):
            validate_run_record(_raw_run(task_digest="short"))
        bad_budget = _raw_run(budget={"max_tokens": 1})
        with self.assertRaises(RecordError):
            validate_run_record(bad_budget)
        self.assertEqual(BUDGET_FIELDS,
                         {"max_tokens", "max_cost_usd", "max_minutes"})


class LedgerTests(unittest.TestCase):
    def test_duplicate_run_id_rejected(self):
        ledger = RunLedger()
        ledger.append(_raw_run())
        with self.assertRaises(RecordError):
            ledger.append(_raw_run(result="failed", first_pass=False))

    def test_overflow_fail_closed(self):
        ledger = RunLedger(max_records=2)
        ledger.append(_raw_run(run_id="a"))
        ledger.append(_raw_run(run_id="b"))
        with self.assertRaises(LedgerFull):
            ledger.append(_raw_run(run_id="c"))
        self.assertEqual(len(ledger), 2)  # 拒绝后不部分写入

    def test_save_load_roundtrip(self):
        ledger = RunLedger()
        ledger.append(_raw_run(run_id="a"))
        ledger.append(_raw_run(run_id="b", result="failed", first_pass=False,
                               recovered=True, cost_usd=None))
        with tempfile.TemporaryDirectory(prefix="icode-r7-bench-") as raw:
            path = Path(raw) / "ledger.json"
            save_ledger_json(ledger, path)
            loaded = load_ledger_json(path)
            self.assertEqual(
                [r.run_id for r in loaded.records()], ["a", "b"])
            self.assertIsNone(loaded.records()[1].cost_usd)
            blob = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(set(blob), {"schema_version", "records"})


class AggregateTests(unittest.TestCase):
    def _sample_ledger(self) -> RunLedger:
        ledger = RunLedger()
        ledger.append(_raw_run(run_id="r1", result="success", first_pass=True))
        ledger.append(_raw_run(run_id="r2", result="failed", first_pass=False,
                               recovered=True, cost_usd=None))
        ledger.append(_raw_run(run_id="r3", result="human_intervention",
                               first_pass=False, recovered=False))
        return ledger

    def test_rates_with_explicit_denominators(self):
        report = aggregate(self._sample_ledger())
        rates = report["rates"]
        self.assertAlmostEqual(rates["success_rate"]["value"], 1 / 3)
        self.assertAlmostEqual(rates["first_pass_gate_rate"]["value"], 1 / 3)
        self.assertAlmostEqual(rates["recovery_rate"]["value"], 1 / 2)
        self.assertAlmostEqual(rates["intervention_rate"]["value"], 1 / 3)
        for entry in rates.values():
            self.assertIn("denominator", entry)

    def test_cost_null_discipline(self):
        report = aggregate(self._sample_ledger())
        self.assertIsNone(report["totals"]["cost_usd"])
        self.assertIn("成本未知", report["totals"]["cost_usd_note"])
        self.assertEqual(report["totals"]["total_tokens"], 450)

    def test_byte_stability(self):
        ledger = self._sample_ledger()
        self.assertEqual(render_report_json(ledger), render_report_json(ledger))
        copy = RunLedger()
        for raw in (
            _raw_run(run_id="r1"), _raw_run(run_id="r2", result="failed",
                                            first_pass=False, recovered=True,
                                            cost_usd=None),
            _raw_run(run_id="r3", result="human_intervention",
                     first_pass=False),
        ):
            copy.append(raw)
        self.assertEqual(render_report_json(ledger), render_report_json(copy))

    def test_zero_runs_reported_honestly(self):
        report = aggregate(RunLedger())
        self.assertEqual(report["run_count"], 0)
        for entry in report["rates"].values():
            self.assertIsNone(entry["value"])
        markdown = render_report_markdown(RunLedger())
        self.assertIn("无样本，不构成统计结论", markdown)

    def test_report_lists_all_runs_including_failures(self):
        markdown = render_report_markdown(self._sample_ledger())
        for run_id in ("r1", "r2", "r3"):
            self.assertIn(run_id, markdown)
        self.assertIn("human_intervention", markdown)
        self.assertIn("failed", markdown)


class NoCherryPickStructureTests(unittest.TestCase):
    """结构断言：聚合/渲染/CLI 无任何筛选或排除参数（G4④）。"""

    def test_aggregate_and_render_have_no_filter_params(self):
        self.assertEqual(list(inspect.signature(benchmark.aggregate).parameters),
                         ["ledger"])
        self.assertEqual(
            list(inspect.signature(benchmark.render_report_json).parameters),
            ["ledger"])
        self.assertEqual(
            list(inspect.signature(benchmark.render_report_markdown).parameters),
            ["ledger"])
        source = inspect.getsource(benchmark.aggregate)
        for banned in ("exclude", "only_runs", "skip", "select", "filter"):
            self.assertNotIn(banned, source)

    def test_cli_only_takes_ledger_and_outputs(self):
        source = inspect.getsource(benchmark.main)
        for banned in ("--only", "--exclude", "--filter", "--select"):
            self.assertNotIn(banned, source)

    def test_cli_report_exit_codes(self):
        ledger = RunLedger()
        ledger.append(_raw_run(run_id="r1"))
        ledger.append(_raw_run(run_id="r2", result="failed", first_pass=False,
                               recovered=True, cost_usd=None))
        with tempfile.TemporaryDirectory(prefix="icode-r7-bench-") as raw:
            path = Path(raw) / "ledger.json"
            save_ledger_json(ledger, path)
            self.assertEqual(main(["report", str(path)]), 0)
            self.assertEqual(main(["report", str(path), str(Path(raw) / "o.json"),
                                   str(Path(raw) / "o.md")]), 0)
            self.assertIn("r2", (Path(raw) / "o.md").read_text(encoding="utf-8"))
            self.assertEqual(main(["nope"]), 2)
            bad = Path(raw) / "bad.json"
            bad.write_text('{"schema_version": 9, "records": []}', encoding="utf-8")
            self.assertEqual(main(["report", str(bad)]), 1)


if __name__ == "__main__":
    unittest.main()
