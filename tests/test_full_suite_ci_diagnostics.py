"""Tiny subprocess contracts: never discover the repository suite in a child."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
OLD = "python -m unittest"
NEW = "python -u scripts/run_full_suite_ci.py"


def full_command():
    text = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    marker = "      - name: Run the full unit test suite\n        run: "
    if text.count(marker) != 1:
        raise AssertionError("full suite step must be unique")
    command = text.split(marker, 1)[1].splitlines()[0]
    if command not in (OLD, NEW):
        raise AssertionError("unexpected full suite command")
    return command


class FullSuiteDiagnosticsTests(unittest.TestCase):
    def fixture(self, root, outcome):
        body = {
            "pass": "self.assertTrue(True)",
            "fail": "self.fail('fixture_failure')",
            "skip": "self.skipTest('fixture_skip')",
            "hang": "local_secret = 'LOCAL_VALUE_SENTINEL'; time.sleep(30)",
        }[outcome]
        (root / "test_a.py").write_text(
            "import time, unittest\nclass Tiny(unittest.TestCase):\n"
            "    def test_wait(self):\n        " + body + "\n",
            encoding="utf-8",
        )
        (root / "test_b.py").write_text(
            "import unittest\nclass Other(unittest.TestCase):\n"
            "    def test_discovered(self):\n        self.assertTrue(True)\n",
            encoding="utf-8",
        )

    def command(self, instrumentation=None):
        active = full_command()
        if instrumentation is None:
            if active == OLD:
                return [sys.executable, "-m", "unittest"]
            return [sys.executable, "-u", str(ROOT / "scripts/run_full_suite_ci.py")]
        path = str(ROOT / "scripts/run_full_suite_ci.py")
        bootstrap = (
            "import faulthandler,json,runpy,sys,threading\n"
            "faulthandler.disable()\n"
            "real_enable=faulthandler.enable\n"
            "def enable(file=None,all_threads=True):\n"
            " real_enable(file=file,all_threads=all_threads)\n"
            " print('FATAL:'+json.dumps([file is sys.stderr,all_threads,faulthandler.is_enabled()]),file=sys.stderr,flush=True)\n"
            "faulthandler.enable=enable\n"
            "def forbidden(*args,**kwargs):\n"
            " raise AssertionError('C watchdog forbidden')\n"
            "faulthandler.dump_traceback_later=forbidden\n"
            "faulthandler.cancel_dump_traceback_later=forbidden\n"
            "namespace=runpy.run_path(" + repr(path) + ")\n"
            "main=namespace['main']\n"
            "configured=main.__globals__['TRACE_INTERVAL_SECONDS']\n"
            "real_thread=threading.Thread\n"
            "class ObservedThread(real_thread):\n"
            " def start(self):\n"
            "  print('ARM:'+json.dumps([configured,self.daemon,self.name]),file=sys.stderr,flush=True)\n"
            "  return super().start()\n"
            " def join(self,*args,**kwargs):\n"
            "  result=super().join(*args,**kwargs)\n"
            "  print('CANCEL:'+json.dumps([not self.is_alive()]),file=sys.stderr,flush=True)\n"
            "  return result\n"
            "threading.Thread=ObservedThread\n"
        )
        if instrumentation == "short":
            bootstrap += "main.__globals__['TRACE_INTERVAL_SECONDS']=0.1\n"
        if active == OLD:
            bootstrap += "sys.argv=['unittest'];runpy.run_module('unittest',run_name='__main__',alter_sys=True)\n"
        else:
            bootstrap += "main()\n"
        return [sys.executable, "-u", "-c", bootstrap]

    def run_tiny(self, root, command):
        return subprocess.run(
            command, cwd=root, capture_output=True, text=True,
            encoding="utf-8", errors="strict", timeout=8,
        )

    def test_default_discovery_exit_and_verbose(self):
        for outcome, code in (("pass", 0), ("fail", 1), ("skip", 0)):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as name:
                root = Path(name)
                self.fixture(root, outcome)
                baseline = self.run_tiny(root, [sys.executable, "-m", "unittest"])
                active = self.run_tiny(root, self.command())
                self.assertEqual(baseline.returncode, code, baseline.stderr)
                self.assertEqual(active.returncode, code, active.stderr)
                for result in (baseline, active):
                    self.assertIn("Ran 2 tests", result.stderr)
                    self.assertEqual(result.stdout, "")
                self.assertRegex(active.stderr, r"test_wait \(test_a\.Tiny(?:\.test_wait)?\) \.\.\.")
                self.assertRegex(active.stderr, r"test_discovered \(test_b\.Other(?:\.test_discovered)?\) \.\.\.")
                if outcome == "fail":
                    self.assertIn("FAILED (failures=1)", active.stderr)
                elif outcome == "skip":
                    self.assertIn("OK (skipped=1)", active.stderr)
                else:
                    self.assertIn("OK", active.stderr)

    def test_real_script_preserves_module_import_visibility_with_pythonpath_src(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "scripts").mkdir()
            (root / "src").mkdir()
            (root / "scripts/_diag_scripts_only.py").write_text("", encoding="utf-8")
            (root / "src/_diag_src_only.py").write_text("", encoding="utf-8")
            (root / "_diag_cwd_only.py").write_text("", encoding="utf-8")
            (root / "test_visibility.py").write_text(
                "import importlib.util, json, unittest\n"
                "class Visibility(unittest.TestCase):\n"
                "    def test_visibility(self):\n"
                "        print('VISIBILITY:'+json.dumps({name: "
                "importlib.util.find_spec('_diag_'+name+'_only') is not None "
                "for name in ('scripts','src','cwd')}, sort_keys=True))\n",
                encoding="utf-8",
            )
            env = os.environ.copy()
            env["PYTHONPATH"] = "src"
            baseline_command = [sys.executable, "-m", "unittest"]
            if full_command() == OLD:
                active_command = baseline_command
            else:
                script = root / "scripts/run_full_suite_ci.py"
                script.write_bytes((ROOT / "scripts/run_full_suite_ci.py").read_bytes())
                active_command = [sys.executable, "-u", str(script)]
            observations = []
            for command in (baseline_command, active_command):
                result = subprocess.run(
                    command, cwd=root, env=env, capture_output=True, text=True,
                    encoding="utf-8", errors="strict", timeout=8,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("Ran 1 test", result.stderr)
                lines = result.stdout.splitlines()
                self.assertEqual(len(lines), 1, result.stdout)
                self.assertTrue(lines[0].startswith("VISIBILITY:"), result.stdout)
                observations.append(json.loads(lines[0].removeprefix("VISIBILITY:")))
            expected = {"scripts": False, "src": True, "cwd": True}
            self.assertEqual(observations[0], expected)
            self.assertEqual(observations[1], observations[0])

    def test_timer_armed_and_cancelled_for_all_normal_exits(self):
        for outcome, code in (("pass", 0), ("fail", 1), ("skip", 0)):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as name:
                root = Path(name)
                self.fixture(root, outcome)
                result = self.run_tiny(root, self.command("record"))
                self.assertEqual(result.returncode, code, result.stderr)
                self.assertEqual(result.stderr.count("FATAL:[true, true, true]"), 1)
                self.assertEqual(result.stderr.count('ARM:[120, true, "full-suite-stack-sampler"]'), 1)
                self.assertEqual(result.stderr.count("CANCEL:[true]"), 1)
                self.assertLess(result.stderr.index("FATAL:"), result.stderr.index("ARM:"))
                self.assertLess(result.stderr.index("ARM:"), result.stderr.index("Ran 2 tests"))
                self.assertGreater(result.stderr.index("CANCEL:[true]"), result.stderr.index("Ran 2 tests"))

    def test_short_hang_emits_periodic_stacks_and_child_is_reaped(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            self.fixture(root, "hang")
            child = subprocess.Popen(
                self.command("short"), cwd=root, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="strict",
            )
            try:
                with self.assertRaises(subprocess.TimeoutExpired):
                    child.communicate(timeout=2)
            finally:
                if child.poll() is None:
                    child.kill()
                stdout, stderr = child.communicate(timeout=3)
            self.assertIsNotNone(child.returncode)
            self.assertNotEqual(child.returncode, 0)
            self.assertEqual(stdout, "")
            self.assertIn('ARM:[120, true, "full-suite-stack-sampler"]', stderr)
            self.assertGreaterEqual(stderr.count("Periodic full-suite stack sample:"), 2, stderr)
            self.assertIn("in test_wait", stderr)
            self.assertNotIn("LOCAL_VALUE_SENTINEL", stderr)
            self.assertNotIn("OK", stderr)

    def test_ci_wiring_keeps_budget_matrix_and_following_guards(self):
        text = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertEqual(full_command(), NEW)
        self.assertIn("timeout-minutes: 25", text)
        self.assertIn('python-version: ["3.11", "3.12"]', text)
        full = text.index("- name: Run the full unit test suite")
        secret = text.index("run: python scripts/preflight.py --only secrets", full)
        submodule = text.index("run: python scripts/preflight.py --only submodule", secret)
        self.assertLess(full, secret)
        self.assertLess(secret, submodule)


if __name__ == "__main__":
    unittest.main()
