# Full-suite GIL sampler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development to implement this plan task-by-task. This is a serial handoff, not authorization to implement during plan authoring.

**Goal:** Replace the unsafe diagnostic C watchdog with GIL-held Python sampling without changing suite scope or exit truth.

**Architecture:** One Event/Thread owns periodic synchronous faulthandler dumps. Main owns stop/join and preserves original suite failure while promoting diagnostics-only failure to nonzero. The existing 120-second period and fatal handlers remain.

**Tech Stack:** Python standard library, unittest, existing GitHub CI.

---

## 1. Authority, frozen inputs and boundaries

Companion SPEC: `docs/nbl/specs/2026-10-15-full-suite-gil-sampler-design.md`.
Analysis HEAD: `b341cb1f010942d99f56861f9eff0ff60f84fc57`.
No actual implementation or Git write is performed by the document author.
Root's explicit authoritative-main workflow overrides skill defaults for new
branches/worktrees/frequent commits/automatic implementation. No extra agent
is spawned during document authoring. Root controls later serial dispatch.

| Input | Lines / bytes | SHA256 |
|---|---|---|
| scripts/run_full_suite_ci.py | 31 / 805 | 2c8e51157fde95bcaf17475bd56ade9c554dec4985d7715d26ddb5c8551cc35d |
| tests/test_full_suite_ci_diagnostics.py | 209 / 10174 | 3a3b8a07668c9a13e9c87882776583143f67416b654a0a06e9f6c3d9b56591e1 |
| .github/workflows/ci.yml | 2549 / 137190 | 9825850137f1b244940bd7fc412af8f1e72d81c052384e93c75fe702243cefc6 |
| tests/test_macos_m0a2_vectors.py | 991 / 56361 | 286dc2d8e3648431c0e725ee913247c5eccd941e1473dc4c59cce90103faf199 |

New TEST path must not exist before Task1:
`tests/test_full_suite_gil_sampler.py`. New configuration/dependency/native
paths are forbidden. This slice changes runner, existing diagnostics TEST, new
regression TEST and the approved docs/records only. Mac fixtures, Skill/pin and
product code remain unchanged. Record root's separate in-flight docs rather
than overwriting them. CI needs no command/matrix/budget/permissions change:
default discovery already includes both diagnostics modules. Do not add a
second full-suite execution or another native gate.

Only formal TEST/SOURCE review may authorize applying the assets below.
Projection/syntax validation is not formal RED/GREEN. A local minimized SIGSEGV
is incident evidence, never a required test outcome. Use `python -B` and outer
subprocess timeouts for targeted commands; never deliberately crash or create
core files as part of formal tests.

Review correction I1: the earlier same-process semantic harness could capture
the outer full-suite sampler through its global mock and fail fixed-stream
assertions. Independent review reproduced that counterexample. Asset A below
isolates all four cases/global mocks in explicitly selected short child helpers;
the parent never patches globals or filters observations, and never stops the
outer sampler. Old zero-review claims for the harness are withdrawn; earlier
incident/projection results remain historical, not revised formal acceptance.
The next different QUALITY review found two further issues (C0/I2/M0): Python
does not treat SystemExit(0.0) as a successful exit, and cleanup KeyboardInterrupt
must not be converted to RuntimeError after a successful suite. The corrected
assets below use exact Python exit semantics and original exception identity;
this correction does not restore any earlier zero-review claim by itself.

## 2. Task 1: independently author TEST and obtain genuine RED

**Dependencies:** None (after SPEC and PLAN dual review).
**Parallelizable:** No (TEST must precede a different SOURCE author).

- [ ] Verify all four frozen inputs and new path absence, read the complete
  original five methods and runner. Revalidate any drift before writing.
- [ ] Add Asset A below as the complete new TEST file. It uses real Thread,
  real synchronous dump in its positive semantic case, and an independently
  injected prohibition on C timer calls. It does not import private sampler
  helpers or assert an implementation-specific source substring.
  All semantic execution and global mocks run only in an explicitly invoked
  short-lived child with a 15-second outer timeout. The parent must not patch
  faulthandler, threading, runpy or sys streams, stop the outer sampler, or
  discard observations from an unexpected thread/stream.
- [ ] Adapt the old TEST with Asset B. Preserve the existing five methods and
  every assertion not explicitly replaced below; do not weaken discovery,
  import visibility, original exits, real fatal enable, no-locals or reap.
- [ ] Formal RED uses only this C-timer-prohibited selector with a 30-second
  outer timeout:
  `/home/orbbec/icode-r2r3-env.DL2JQJ/bin/python -B -m unittest tests.test_full_suite_gil_sampler tests.test_full_suite_ci_diagnostics.FullSuiteDiagnosticsTests.test_timer_armed_and_cancelled_for_all_normal_exits tests.test_full_suite_ci_diagnostics.FullSuiteDiagnosticsTests.test_short_hang_emits_periodic_stacks_and_child_is_reaped -v`.
  Expect genuine Assertion failures on old SOURCE, no ERROR/skip. Record actual
  counts/timing/exit, not projected numbers. The old timer is prohibited before
  execution, so this RED must not intentionally produce SIGSEGV/core.
  Do not run the old uninstrumented tiny/import methods before SOURCE: those
  launch the old real runner and would arm its original 120s C timer.
- [ ] TEST author performs SPEC and QUALITY self-review. Root obtains different
  SPEC and QUALITY review, both C0/I0/M0. Freeze both TEST hashes. No SOURCE yet.

### Asset A: complete tests/test_full_suite_gil_sampler.py

```python
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
```

### Asset B: exact existing-TEST adaptations

Replace only `FullSuiteDiagnosticsTests.command` with this complete method:

```python
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
```

In `test_timer_armed_and_cancelled_for_all_normal_exits`, replace the assertions
after returncode with this block. Counts precede index lookup, so old SOURCE
produces a genuine Assertion, not a missing-marker ValueError:

```python
                self.assertEqual(result.stderr.count("FATAL:[true, true, true]"), 1)
                self.assertEqual(result.stderr.count('ARM:[120, true, "full-suite-stack-sampler"]'), 1)
                self.assertEqual(result.stderr.count("CANCEL:[true]"), 1)
                self.assertLess(result.stderr.index("FATAL:"), result.stderr.index("ARM:"))
                self.assertLess(result.stderr.index("ARM:"), result.stderr.index("Ran 2 tests"))
                self.assertGreater(result.stderr.index("CANCEL:[true]"), result.stderr.index("Ran 2 tests"))
```

In `test_short_hang_emits_periodic_stacks_and_child_is_reaped`, replace only
the old ARM assertion and Timeout-count assertion with:

```python
            self.assertIn('ARM:[120, true, "full-suite-stack-sampler"]', stderr)
            self.assertGreaterEqual(stderr.count("Periodic full-suite stack sample:"), 2, stderr)
```

Keep actual Popen/kill/communicate reaping, LOCAL_VALUE_SENTINEL rejection,
no OK, test_wait stack, default discovery, PYTHONPATH and CI assertions intact.
No other method, decorator or fixture body changes. There remain five old
methods plus four new methods; nested synthetic observer output is not an
additional native test count.

## 3. Task 2: different SOURCE author, bounded implementation

**Dependencies:** Task 1 dual TEST review and frozen genuine RED.
**Parallelizable:** No (different author; frozen oracle is not editable).

- [ ] Different SOURCE author reproduces formal RED using frozen TEST assets.
- [ ] Replace only `scripts/run_full_suite_ci.py` with Asset C below. Do not
  edit TEST to make SOURCE pass, add configuration, signals or C timers.
- [ ] Run both full diagnostics modules with a 30-second outer timeout:
  `/home/orbbec/icode-r2r3-env.DL2JQJ/bin/python -B -m unittest tests.test_full_suite_ci_diagnostics tests.test_full_suite_gil_sampler -v`.
  Expect nine parents passing, zero failure/error/skip, exit0. Record actual
  elapsed time and software-only credit. Do not run full/native locally.
- [ ] SOURCE self SPEC/QUALITY then different SPEC and QUALITY, both C0/I0/M0.
  Review exception precedence, stream lifetime, thread stop/join and GIL blind
  spot explicitly. A review fix must return through both reviews.

### Asset C: complete scripts/run_full_suite_ci.py

```python
"""GIL-held periodic diagnostics around unchanged unittest default discovery."""
import os
import sys

TRACE_INTERVAL_SECONDS = 120


def main():
    original_argv = sys.argv
    original_path = sys.path[:]
    sys.path[0] = os.getcwd()
    sys.argv = ["unittest", "-v"]
    try:
        import faulthandler
        import runpy
        import threading

        stream = sys.stderr
        faulthandler.enable(file=stream, all_threads=True)
        stop = threading.Event()
        errors = []

        def sample():
            try:
                while not stop.wait(TRACE_INTERVAL_SECONDS):
                    stream.write("Periodic full-suite stack sample:\n")
                    stream.flush()
                    faulthandler.dump_traceback(file=stream, all_threads=True)
            except BaseException as error:
                errors.append(error)

        sampler = threading.Thread(target=sample,
                                   name="full-suite-stack-sampler", daemon=True)
        suite_error = None
        try:
            sampler.start()
            runpy.run_module("unittest", run_name="__main__", alter_sys=True)
        except BaseException as error:
            suite_error = error
            raise
        finally:
            # Keep stream alive until a real join; daemon is not cleanup credit.
            for action in (stop.set, sampler.join):
                try:
                    action()
                except BaseException as error:
                    errors.append(error)
            if errors:
                succeeded = (suite_error is None or
                             isinstance(suite_error, SystemExit) and
                             (suite_error.code is None or
                              isinstance(suite_error.code, int) and
                              suite_error.code == 0))
                if succeeded:
                    for error in errors:
                        if not isinstance(error, Exception):
                            raise error
                    raise RuntimeError("full-suite diagnostic sampler failed") from None
                # Never mask an existing suite failure or disclose error values.
                try:
                    stream.write("Full-suite diagnostic sampler failed; preserving suite failure.\n")
                    stream.flush()
                except BaseException:
                    pass
    finally:
        sys.argv = original_argv
        sys.path[:] = original_path


if __name__ == "__main__":
    main()
```

The join is deliberately not a claim of bounded native cancellation. If stderr
blocks or a C extension permanently owns the GIL, the unchanged 25-minute CI
budget remains the hard limit. No silent return while a normally joinable worker
is alive; no extra local timeout/configuration. A join exception after the real
join is tested. Startup failure before launch and after real launch is tested;
both still run stop/join cleanup and preserve the startup exception. A join on
an unstarted thread can raise a secondary RuntimeError; it must not replace the
primary startup error. Asynchronous start interruption is not an atomic cancel
guarantee: a later-starting worker sees the set Event before sampling and keeps
the stream in its closure; failed join does not earn cleanup acceptance. An
impossible-to-stop/broken Event is not advertised as repaired.
Success means normal return, SystemExit(None), or an integer zero (including
False), not equal-valued float0.0 or string"0". If cleanup/sampling fails after
success, raise the first captured non-Exception BaseException object unchanged;
only ordinary Exception failures become the fixed RuntimeError. Existing
nonzero suite/start exceptions remain primary, even over a later interrupt.
The child creates each suite/interrupt object once and reports identity booleans,
not exception values. Four methods retain their shape; subcases cover None,
False, 0, 1, 7, 0.0 and "0", plus ordinary and interrupting post-real-join errors.

## 4. Task 3: root integration, provenance and global gates

**Dependencies:** Task 2 dual SOURCE review.
**Parallelizable:** No (candidate closure and root-owned docs).

- [ ] Root checks the exact three implementation paths, both approved docs,
  frozen Mac fixture and CI inputs; verify no other product/Skill/pin changes.
- [ ] CI remains byte-identical: `python -u scripts/run_full_suite_ci.py`,
  Python3.11/3.12, timeout25, original permissions, matrix, secrets and submodule
  guards. No new full run or trigger is needed. New tests are default-discovered.
- [ ] Root alone appends an evidence-bounded entry to handoff/live records:
  incident/minimized observations are historical evidence; new source is a
  candidate diagnostic change, permanent-GIL blind spot is explicit, full-suite
  and native verification remain pending. Preserve unrelated dirty changes.
- [ ] Run targeted nine methods, diffcheck, existing minimal secrets/submodule
  checks. Keep stderr fixture output/local stack assertions meaningful.
- [ ] Different global SPEC, then different global QUALITY over the actual whole
  candidate; both C0/I0/M0. Document all input/output hashes, exact scope and
  staged-index review. Do not stage/commit as an implementation subtask here.
- [ ] Only root, after all b341 same-repository runs are terminal, may prepare
  and push the reviewed pending-acceptance main candidate under existing user
  authorization. No cancel/retry masking. No requirement to await b341 before
  formal RED or SOURCE work. Do not claim candidate completion at push.
- [ ] Observe candidate-bound 3.11 and 3.12 full logs/exits and following guards;
  failures/skips are not passes. Preserve original71 incident evidence. No
  cross-platform/native acceptance is inferred from this diagnostic-only slice.

## 5. Self-review and execution handoff

- [ ] Map every SPEC contract to Asset A/B/C or Task3; no missing permission,
  lifecycle, exception-precedence or blind-spot item.
- [ ] Compile all fenced Python assets in RAM. Confirm original five methods
  remain and new four methods use no C timer except forbidden mock oracles.
- [ ] Inspect all source changes and every caller; preserve unittest's actual
  discovery/SystemExit behavior and global argv/path restoration.
- [ ] Record projections separately from later actual RED/GREEN. Do not weaken
  the independent new semantic test to fit old adapter instrumentation.

**Execution Mode:** serial.

This authoring turn stops for root's full-document review and independent
SPEC/QUALITY. No automatic implementation dispatch, source/test edit, worktree,
commit or push is authorized by merely saving this plan.
