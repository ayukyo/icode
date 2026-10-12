"""Software contract checks for the installed Linux helper diagnostic record.

These checks grant neither native conformance credit nor readiness evidence.
"""

import ast
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]
FIELDS = (
    "exit_code", "payload_started", "payload_ready", "resource_configured",
    "resource_channel_status", "resource_terminal",
)
GOOD = dict(zip(FIELDS, (-15, True, True, True, "complete", "finished")))
PRIVATE = "PRIVATE-PATH-COMMAND-STDERR-SENTINEL"


class TestLinuxHelperDiagnosticRecord(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = ROOT / "scripts/run_native_wheel_ci.py"
        spec = importlib.util.spec_from_file_location(
            "native_wheel_ci_linux_diagnostic_test", source)
        cls.publisher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.publisher)

    def result(self, receipt=True, **changes):
        result = SimpleNamespace(
            error="resource_channel_failed", exit_code=-15, payload_started=True)
        if receipt is True:
            result.resource_receipt = {
                "configured": True, "channel_status": "complete",
                "terminal": "finished", "private": PRIVATE,
            }
        elif receipt is not False:
            result.resource_receipt = receipt
        for name, value in changes.items():
            setattr(result, name, value)
        return result

    def produce(self, result, ready=True):
        source = ROOT / "scripts/probe_installed_linux_helper_object.py"
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        functions = [node for node in ast.walk(tree)
                     if isinstance(node, ast.FunctionDef) and node.name == "run_fault"]
        self.assertEqual(len(functions), 1, "expected one actual run_fault")
        expressions = []
        for node in ast.walk(functions[0]):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "print" and node.args):
                continue
            dumps = node.args[0]
            if not (isinstance(dumps, ast.Call) and isinstance(dumps.func, ast.Attribute)
                    and isinstance(dumps.func.value, ast.Name)
                    and dumps.func.value.id == "json" and dumps.func.attr == "dumps"
                    and dumps.args):
                continue
            record = dumps.args[0]
            if (isinstance(record, ast.Call) and isinstance(record.func, ast.Name)
                    and record.func.id == "dict"
                    and any(keyword.arg == "scenario" for keyword in record.keywords)):
                expressions.append(record)
        self.assertEqual(len(expressions), 1, "expected one actual fault record")
        # Evaluate the actual production expression, without importing the native probe.
        expression = ast.fix_missing_locations(ast.Expression(copy.deepcopy(expressions[0])))
        compiled = compile(expression, str(source), "eval")
        with tempfile.TemporaryDirectory() as raw:
            workspace = Path(raw)
            if ready:
                (workspace / "ready").touch()
            namespace = {
                "scenario": "timeout", "resource_mode": True, "consumer": "context",
                "ctx": object(), "result": result, "error": None, "workspace": workspace,
                "linux_arch_from_machine": lambda machine: "arm64",
                "platform": SimpleNamespace(machine=lambda: "aarch64", release=lambda: "6.8.0-test"),
                "process_closed": True, "channels_closed": True, "threads_stopped": True,
                "owner_states": ["closed"], "scope_states": ["confirmed"],
                "scope_gc": True, "workspace_live": True,
                "processes": [SimpleNamespace(pid=1234)], "systemd": ["systemd 249"],
                "package_hash": "a" * 64, "manifest_hash": "b" * 64,
            }
            return eval(compiled, namespace)

    def publish(self, raw):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.publisher._publish_helper_dispatch_records(json.dumps(raw))
        stdout = output.getvalue()
        lines = stdout.splitlines()
        self.assertEqual(len(lines), 1, "publisher must emit exactly one line")
        prefix = "helper-dispatch-record "
        self.assertTrue(lines[0].startswith(prefix))
        return json.loads(lines[0][len(prefix):]), stdout

    def six_fields(self, record):
        self.assertTrue(set(FIELDS).issubset(record), "record lacks six fields")
        return {name: record[name] for name in FIELDS}

    def invalid_values(self):
        return {
            "exit_code": (True, False, -256, 256, 1.0, PRIVATE, [], {}),
            "payload_started": (0, 1, "true", PRIVATE, [], {}),
            "payload_ready": (0, 1, "true", PRIVATE, [], {}, None),
            "resource_configured": (0, 1, "true", PRIVATE, [], {}),
            "resource_channel_status": (True, 1, "finished", PRIVATE, [], {}),
            "resource_terminal": (True, 1, "complete", PRIVATE, [], {}),
        }

    def test_actual_producer_six_fields(self):
        record = self.produce(self.result())
        self.assertTrue(set(FIELDS).issubset(record), "actual producer lacks six fields")
        self.assertEqual(self.six_fields(record), GOOD)
        self.assertEqual(record["error"], "resource_channel_failed")

    def test_actual_publisher_six_fields(self):
        raw = {"architecture": "arm64", "topology": "scope", **GOOD}
        record, _ = self.publish(raw)
        self.assertTrue(set(FIELDS).issubset(record), "actual publisher lacks six fields")
        self.assertEqual(self.six_fields(record), GOOD)

    def test_producer_missing_result_and_ready_false(self):
        record = self.produce(None, ready=False)
        expected = dict.fromkeys(FIELDS)
        expected["payload_ready"] = False
        self.assertEqual(self.six_fields(record), expected)
        self.assertEqual(record["error"], "raised")
        published, stdout = self.publish(record)
        self.assertEqual(self.six_fields(published), expected)
        self.assertEqual(published["error"], "raised")
        self.assertNotIn(PRIVATE, stdout)

    def test_producer_missing_none_empty_and_non_dict_receipt(self):
        for receipt in (False, None, {}, [], PRIVATE):
            with self.subTest(receipt=receipt):
                record = self.produce(self.result(receipt))
                expected = {**GOOD, "resource_configured": None,
                            "resource_channel_status": None, "resource_terminal": None}
                self.assertEqual(self.six_fields(record), expected)
                self.assertEqual(record["exit_code"], -15)
                published, stdout = self.publish(record)
                self.assertEqual(self.six_fields(published), self.six_fields(record))
                self.assertEqual(published["error"], record["error"])
                self.assertNotIn(PRIVATE, stdout)

    def test_publisher_allowed_values_and_none(self):
        allowed = {
            "exit_code": (-255, -1, 0, 255, None),
            "payload_started": (True, False, None),
            "payload_ready": (True, False),
            "resource_configured": (True, False, None),
            "resource_channel_status": ("complete", "incomplete", None),
            "resource_terminal": ("preexec_failed", "finished", "cleanup_failed", None),
        }
        for name, values in allowed.items():
            for value in values:
                with self.subTest(field=name, value=value):
                    record, _ = self.publish({"architecture": "arm64", "topology": "scope", name: value})
                    self.assertIn(name, record)
                    self.assertIs(type(record[name]), type(value))
                    self.assertEqual(record[name], value)

    def test_publisher_invalid_values_are_deleted_without_echo(self):
        private_fields = ("private_path", "stderr", "command", "resource_receipt")
        for name, values in self.invalid_values().items():
            for value in values:
                with self.subTest(field=name, value=value):
                    raw = {"architecture": "arm64", "topology": "scope", **GOOD, name: value}
                    raw.update(dict.fromkeys(private_fields, PRIVATE))
                    raw["resource_receipt"] = {"private": PRIVATE}
                    record, stdout = self.publish(raw)
                    self.assertNotIn(name, record)
                    for private_field in private_fields:
                        self.assertNotIn(private_field, record)
                    self.assertNotIn(PRIVATE, stdout)

    def test_old_record_compatibility(self):
        raw = {"architecture": "x86_64", "topology": "no-scope", "scenario": "timeout",
               "error": "timeout", "process_closed": True}
        record, _ = self.publish(raw)
        self.assertEqual(record, raw)
        for name in FIELDS:
            self.assertNotIn(name, record)

    def test_actual_producer_to_publisher_preserves_failure_and_privacy(self):
        record = self.produce(self.result())
        record.update(stderr=PRIVATE, command=PRIVATE, private_path=PRIVATE)
        published, stdout = self.publish(record)
        self.assertEqual(self.six_fields(published), GOOD)
        self.assertEqual(published["error"], record["error"])
        self.assertNotIn(PRIVATE, stdout)
        receipt_keys = {"resource_configured": "configured",
                        "resource_channel_status": "channel_status", "resource_terminal": "terminal"}
        for name, values in self.invalid_values().items():
            if name == "payload_ready":
                continue
            for value in values:
                with self.subTest(field=name, value=value):
                    result = self.result()
                    if name in receipt_keys:
                        result.resource_receipt[receipt_keys[name]] = value
                    else:
                        setattr(result, name, value)
                    record = self.produce(result)
                    record.update(stderr=PRIVATE, command=PRIVATE, private_path=PRIVATE)
                    published, stdout = self.publish(record)
                    self.assertNotIn(name, published)
                    for other in FIELDS:
                        if other != name:
                            self.assertIn(other, published)
                            self.assertIs(type(published[other]), type(GOOD[other]))
                            self.assertEqual(published[other], GOOD[other])
                    self.assertEqual(published["error"], record["error"])
                    self.assertNotIn(PRIVATE, stdout)


if __name__ == "__main__":
    unittest.main()
