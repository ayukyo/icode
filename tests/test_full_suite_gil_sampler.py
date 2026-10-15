"""Semantic diagnostics contracts; no C timer or intentional crash oracle."""
import faulthandler
import io
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

from tests.test_macos_m0a2_vectors import software_fixture

ROOT = Path(__file__).resolve().parents[1]


class FullSuiteGilSamplerTests(unittest.TestCase):
    def exercise(self, code=0, dump_error=False, join_error=False,
                 start_error=None, churn=False):
        options = dict(code=code, dump_error=dump_error, join_error=join_error,
                       start_error=start_error, churn=churn)
        bootstrap = (
            "import json,sys\n"
            "from tests.test_full_suite_gil_sampler import FullSuiteGilSamplerTests as T\n"
            "print(json.dumps(T._exercise_child(**json.loads(sys.argv[1]))))\n"
        )
        result = subprocess.run(
            [sys.executable, "-B", "-c", bootstrap, json.dumps(options)],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
            errors="strict", timeout=15,
        )
        self.assertEqual(result.returncode, 0, "isolated semantic child failed")
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 1, "expected exactly one child JSON record")
        data = json.loads(lines[0])
        self.assertTrue(data["argv_restored"])
        self.assertTrue(data["path_restored"])
        self.assertTrue(all(not item["alive"] for item in data["workers"]))
        self.assertTrue(data["no_error_values"])
        return data

    @staticmethod
    def _exercise_child(code=0, dump_error=False, join_error=False,
                        start_error=None, churn=False):
        # Called only by the explicit child bootstrap, never by parent discovery.
        self = unittest.TestCase()
        namespace = runpy.run_path(str(ROOT / "scripts/run_full_suite_ci.py"))
        main = namespace["main"]
        main.__globals__["TRACE_INTERVAL_SECONDS"] = 0.01
        real_thread = threading.Thread
        real_dump = faulthandler.dump_traceback
        seen = threading.Event()
        workers = []
        observations = []
        owner = threading.get_ident()
        originally_enabled = faulthandler.is_enabled()
        original_argv = sys.argv
        original_path = sys.path[:]
        start_failure = OSError("injected_start_" + str(start_error))
        suite_failure = SystemExit(code)
        interrupt_failure = KeyboardInterrupt()

        class Worker(real_thread):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                workers.append(self)

            def start(self):
                if start_error == "before":
                    raise start_failure
                result = super().start()
                if start_error == "after":
                    raise start_failure
                return result

            def join(self, *args, **kwargs):
                result = super().join(*args, **kwargs)
                if join_error == "interrupt":
                    raise interrupt_failure
                if join_error:
                    raise OSError("injected_join_failure")
                return result

        with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as stream:
            def dump(file=None, all_threads=False):
                observations.append((file is stream, all_threads,
                                     threading.get_ident() != owner))
                try:
                    if dump_error:
                        raise OSError("injected_dump_failure")
                    real_dump(file=file, all_threads=all_threads)
                finally:
                    seen.set()

            def suite(name, **kwargs):
                self.assertEqual((name, kwargs),
                                 ("unittest", {"run_name": "__main__",
                                               "alter_sys": True}))
                self.assertTrue(faulthandler.is_enabled())
                with mock.patch.object(sys, "stderr", io.StringIO()):
                    if churn:
                        for _ in range(2000):
                            meta, rows = software_fixture()
                    self.assertTrue(seen.wait(2), "real sampler never ran")
                raise suite_failure

            caught = None
            with mock.patch.object(sys, "stderr", stream), \
                 mock.patch.object(threading, "Thread", Worker), \
                 mock.patch.object(faulthandler, "dump_traceback", dump), \
                 mock.patch.object(faulthandler, "dump_traceback_later",
                                   side_effect=AssertionError("C timer forbidden")), \
                 mock.patch.object(faulthandler, "cancel_dump_traceback_later",
                                   side_effect=AssertionError("C cancel forbidden")), \
                 mock.patch.object(runpy, "run_module", side_effect=suite):
                try:
                    main()
                except BaseException as error:
                    caught = error
            # Do not leave a process-wide fatal handler pointing at a closed fd.
            if originally_enabled:
                faulthandler.enable(file=sys.stderr, all_threads=True)
            else:
                faulthandler.disable()
            stream.seek(0)
            output = stream.read()
        # Only booleans, fixed type names, integer exits and worker metadata cross
        # the process boundary; never transmit exception values, locals or stacks.
        return {
            "caught_type": type(caught).__name__,
            "suite_is_primary": caught is suite_failure,
            "interrupt_is_primary": caught is interrupt_failure,
            "startup_is_primary": caught is start_failure,
            "argv_restored": sys.argv is original_argv,
            "path_restored": sys.path == original_path,
            "workers": [{"alive": worker.is_alive(), "name": worker.name,
                         "daemon": worker.daemon} for worker in workers],
            "observations": observations,
            "periodic_header": "Periodic full-suite stack sample:" in output,
            "no_error_values": all(value not in output for value in
                                   ("injected_dump_failure", "injected_join_failure",
                                    "injected_start_")),
        }

    def test_real_short_samples_use_fixed_stream_and_stop_after_fixture_churn(self):
        data = self.exercise(churn=True)
        self.assertEqual(data["caught_type"], "SystemExit")
        self.assertTrue(data["suite_is_primary"])
        self.assertEqual(len(data["workers"]), 1)
        self.assertTrue(data["observations"])
        self.assertTrue(all(item == [True, True, True]
                            for item in data["observations"]))
        self.assertTrue(data["periodic_header"])

    def test_sampling_failure_never_masks_existing_suite_exit(self):
        for code in (None, False, 0, 1, 7, 0.0, "0"):
            with self.subTest(code=code):
                data = self.exercise(code=code, dump_error=True)
                self.assertEqual(len(data["workers"]), 1)
                self.assertTrue(data["observations"])
                succeeded = (code is None or
                             isinstance(code, int) and code == 0)
                if succeeded:
                    self.assertEqual(data["caught_type"], "RuntimeError")
                else:
                    self.assertEqual(data["caught_type"], "SystemExit")
                    self.assertTrue(data["suite_is_primary"])

    def test_join_failure_never_masks_existing_suite_exit(self):
        for code in (None, False, 0, 1, 7, 0.0, "0"):
            for mode in (True, "interrupt"):
                with self.subTest(code=code, mode=mode):
                    data = self.exercise(code=code, join_error=mode)
                    self.assertEqual(len(data["workers"]), 1)
                    self.assertTrue(data["observations"])
                    succeeded = (code is None or
                                 isinstance(code, int) and code == 0)
                    if not succeeded:
                        self.assertEqual(data["caught_type"], "SystemExit")
                        self.assertTrue(data["suite_is_primary"])
                    elif mode == "interrupt":
                        self.assertEqual(data["caught_type"], "KeyboardInterrupt")
                        self.assertTrue(data["interrupt_is_primary"])
                    else:
                        self.assertEqual(data["caught_type"], "RuntimeError")

    def test_start_failure_before_or_after_launch_remains_primary(self):
        for phase in ("before", "after"):
            with self.subTest(phase=phase):
                data = self.exercise(start_error=phase)
                self.assertEqual(len(data["workers"]), 1)
                self.assertEqual(data["caught_type"], "OSError")
                self.assertTrue(data["startup_is_primary"])


if __name__ == "__main__":
    unittest.main()
