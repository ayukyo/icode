"""Real loopback producer/Actions notice budget; software only, no OS APIs."""
from __future__ import annotations

import ast
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from tests import test_windows_loopback_config_observation as original

ROOT = Path(__file__).resolve().parents[1]
REVIEWER = ROOT / "tests/test_windows_appcontainer.py"
PARENT = ROOT / "scripts/run_windows_appcontainer_read_probe.py"


def actual_functions(path, names, *, class_name=None):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    body = tree.body
    if class_name is not None:
        body = next(node.body for node in body if isinstance(node, ast.ClassDef)
                    and node.name == class_name)
    selected = [node for node in body if isinstance(node, ast.FunctionDef)
                and node.name in names]
    if {node.name for node in selected} != set(names):
        raise AssertionError("actual notice/comparison functions missing")
    future = ast.ImportFrom(module="__future__",
                            names=[ast.alias(name="annotations")], level=0)
    namespace = dict(json=json, os=os)
    exec(compile(ast.fix_missing_locations(ast.Module(
        body=[future, *selected], type_ignores=[])), str(path), "exec"), namespace)
    return {name: namespace[name] for name in names}


class TestPositiveLoopbackNoticeBudget(unittest.TestCase):
    def setUp(self):
        methods = actual_functions(REVIEWER, {
            "_workflow_notice", "_workflow_json_notice",
        }, class_name="TestWindowsAppContainer")
        case = type("ActualNoticeCase", (unittest.TestCase,), methods)
        self.consumer = case()
        self.parent = actual_functions(PARENT, {
            "_positive_loopback_unknown", "_positive_loopback_comparison",
        })

    def unknown(self, phase):
        return self.parent["_positive_loopback_unknown"](phase, "protocol_error")

    def drive(self, factory, **options):
        harness = original.TestPositiveLoopbackConfig()
        output = io.StringIO()
        with patch.object(original, "sample", side_effect=factory), \
                patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}), \
                contextlib.redirect_stdout(output):
            outcome = harness.execute_positive(
                json_notice=self.consumer._workflow_json_notice,
                comparison=self.parent["_positive_loopback_comparison"],
                unknown=self.parent["_positive_loopback_unknown"],
                **options,
            )
        frames = []
        for line in output.getvalue().splitlines():
            if line.startswith("positive_loopback_config_"):
                prefix, decoded = line.split("=", 1)
                name = {
                    "positive_loopback_config_pre": "Windows positive loopback configuration pre",
                    "positive_loopback_config_post": "Windows positive loopback configuration post",
                    "positive_loopback_config_comparison": "Windows positive loopback configuration comparison",
                }[prefix]
            else:
                self.assertTrue(line.startswith("::notice title=R2.3 "))
                name, encoded = line[len("::notice title=R2.3 "):].split("::", 1)
                decoded = encoded.replace("%0A", "\n").replace("%0D", "\r").replace("%25", "%")
            self.assertLessEqual(len(decoded), 500)
            detail = json.loads(decoded)
            self.assertEqual(decoded, json.dumps(detail, ensure_ascii=True, separators=(",", ":")))
            frames.append((name, detail))
        return outcome, frames

    def assert_samples(self, frames, pre, post, comparison):
        expected = [
            ("Windows positive loopback configuration pre", pre),
            ("Windows positive loopback configuration post", post),
            ("Windows positive loopback configuration comparison", {"comparison": comparison}),
        ]
        self.assertEqual(frames[:3], expected)
        self.assertEqual(set(frames[0][1]), set(pre))
        self.assertEqual(set(frames[1][1]), set(post))

    def test_complete_and_unknown_use_actual_producer_consumer_without_loss(self):
        # Snapshot before patching original.sample to avoid recursive fixture calls.
        base = original.sample
        def maximum(phase):
            return dict(base(phase), entry_count=4096, target_match=True,
                        target_attributes=0xFFFFFFFF, sid_frees_attempted=4096,
                        sid_frees_confirmed=4096, array_release="confirmed")
        for factory, comparison in ((maximum, "consistent_endpoints"),
                                    (self.unknown, "unknown")):
            with self.subTest(comparison=comparison):
                expected_pre, expected_post = factory("pre"), factory("post")
                result, frames = self.drive(factory)
                self.assertIsNone(result.failure)
                self.assertEqual(result.events, ["pre", "launch", "post"])
                self.assertEqual(result.observed, [(original.PROFILE, "pre"),
                                                   (original.PROFILE, "post")])
                self.assertEqual(len(frames), 3)
                self.assert_samples(frames, expected_pre, expected_post, comparison)

    def test_unreaped_stops_and_original_errors_keep_full_samples(self):
        for options, events, failure in (
            ({"pre_stop": True}, ["pre"], "pre helper was not reaped"),
            ({"post_stop": True}, ["pre", "launch", "post"], "post helper was not reaped"),
            ({"clean": False}, ["pre", "launch"], "original-first"),
            ({"launch_error": True}, ["pre", "launch"], "OSError"),
        ):
            with self.subTest(options=options):
                result, frames = self.drive(self.unknown, **options)
                self.assertEqual(result.events, events)
                self.assertIsNotNone(result.failure)
                self.assertIn(failure, result.failure)
                post = self.unknown("post") if "post" in events else \
                    self.parent["_positive_loopback_unknown"]("post", "not_attempted")
                self.assert_samples(frames, self.unknown("pre"), post, "unknown")
                if options.get("post_stop"):
                    self.assertEqual(frames[3:], [
                        ("Windows private-network first result preserved",
                         {"executed": True, "exit": 105, "cleanup": True}),
                    ])
                else:
                    self.assertEqual(len(frames), 3)

    def test_actual_notice_guard_and_actions_escaping_remain_enforced(self):
        package_import=subprocess.run([sys.executable,"-I","-B","-c",
            "import sys;sys.path[:0]="+repr([str(ROOT),str(ROOT/"src")])+
            ";import tests.test_windows_loopback_notice_budget"],
            cwd=ROOT,capture_output=True,timeout=10)
        self.assertEqual(package_import.returncode,0,package_import.stderr.decode("utf-8","replace"))
        self.assertEqual(package_import.stdout,b"")
        self.assertEqual(package_import.stderr,b"")
        output = io.StringIO()
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}), \
                contextlib.redirect_stdout(output):
            self.consumer._workflow_json_notice("encoding", {"text": "%\r\n汉"})
            self.consumer._workflow_notice("raw encoding", "%\r\n")
            with self.assertRaisesRegex(AssertionError, "would be silently truncated"):
                self.consumer._workflow_json_notice(
                    "Windows positive loopback configuration pre", {"text": "X" * 500})
            self.consumer._workflow_json_notice(
                "Windows positive loopback configuration arbitrary", {"text": "%"})
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}), \
                contextlib.redirect_stdout(output):
            for phase in ("pre", "post", "comparison"):
                self.consumer._workflow_json_notice(
                    "Windows positive loopback configuration " + phase, {"value": 1})
        self.assertEqual(output.getvalue().splitlines(), [
            '::notice title=R2.3 encoding::{"text":"%25\\r\\n\\u6c49"}',
            "::notice title=R2.3 raw encoding::%25%0D%0A",
            '::notice title=R2.3 Windows positive loopback configuration arbitrary::{"text":"%25"}',
        ])


if __name__ == "__main__":
    unittest.main()
