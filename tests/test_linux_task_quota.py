"""Real delegated cgroup component checks; no product conformance credit."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "native/linux/icode_task_quota.h"


class TestLinuxTaskQuotaSource(unittest.TestCase):
    def test_independent_quota_component_exists(self) -> None:
        self.assertTrue(HEADER.is_file(), "native quota component must exist")


@unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("cc"),
                     "requires Linux and a C compiler; conformance_credit=none")
class TestLinuxTaskQuota(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temporary = tempfile.TemporaryDirectory(prefix="icode-task-quota-test-")
        cls.addClassCleanup(cls._temporary.cleanup)
        cls._executable = Path(cls._temporary.name) / "quota-probe"
        result = subprocess.run(
            [shutil.which("cc") or "cc", "-std=c11", "-O2", "-Wall", "-Wextra",
             "-Werror", "-pthread", "-I", str(ROOT / "native/linux"),
             str(ROOT / "tests/fixtures/native/linux_task_quota_probe.c"),
             "-o", str(cls._executable)],
            capture_output=True, text=True, timeout=15, check=False,
        )
        if result.returncode:
            raise AssertionError(f"quota probe compile failed: {result.stderr[-1200:]}")

    def _probe(self, mode: str, *, delegated: bool = True) -> str:
        environment = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"}
        if mode == "invalid":
            command = [str(self._executable), mode]
        else:
            uid = os.getuid()
            bus = Path(f"/run/user/{uid}/bus")
            if uid == 0 or not bus.is_socket() or not Path("/usr/bin/systemd-run").is_file():
                self.skipTest("nonroot user manager bus unavailable; conformance_credit=none")
            environment.update(XDG_RUNTIME_DIR=f"/run/user/{uid}",
                               DBUS_SESSION_BUS_ADDRESS=f"unix:path={bus}")
            unit = f"icode-task-{uuid.uuid4().hex}.scope"
            command = ["/usr/bin/systemd-run", "--user", "--scope", "--quiet",
                       f"--unit={unit}",
                       "--property=Delegate=pids" if delegated else "--property=Delegate=no",
                       str(self._executable), mode, unit]
        result = subprocess.run(command, capture_output=True, text=True, check=False,
                                timeout=15, env=environment)
        if result.returncode == 77 and result.stdout == "probe:prerequisite_unavailable=1\n":
            self.skipTest("delegated cgroup2 pids/clone3 unavailable; conformance_credit=none")
        self.assertEqual(result.returncode, 0, result.stderr[-1200:])
        self.assertEqual(result.stderr, "")
        self.assertIn("probe:conformance_credit=none", result.stdout)
        return result.stdout

    def test_invalid_unit_and_cap_reject_before_creating_nodes(self) -> None:
        self.assertIn("probe:invalid_inputs_rejected=1", self._probe("invalid"))

    def test_cap_two_counts_root_and_descendant_not_supervisor(self) -> None:
        result = self._probe("cap2")
        for line in ("probe:payload_tasks=2", "probe:descendant_created=1",
                     "probe:supervisor_outside_payload=1", "probe:management_fds_closed=1",
                     "probe:empty_cleanup=1"):
            self.assertIn(line, result)

    def test_cap_one_denies_fork_without_marker_and_records_event(self) -> None:
        result = self._probe("cap1")
        for line in ("probe:payload_tasks=1", "probe:creation_denied=EAGAIN",
                     "probe:descendant_marker=0", "probe:pids_event_increased=1"):
            self.assertIn(line, result)

    def test_cap_one_counts_threads_as_tasks(self) -> None:
        result = self._probe("thread1")
        self.assertIn("probe:creation_denied=EAGAIN", result)
        self.assertIn("probe:descendant_marker=0", result)
        self.assertIn("probe:pids_event_increased=1", result)

    def test_populated_finish_denies_then_empty_finish_succeeds(self) -> None:
        result = self._probe("populated")
        self.assertIn("probe:populated_cleanup_rejected=1", result)
        self.assertIn("probe:empty_cleanup=1", result)

    def test_replaced_payload_is_not_deleted(self) -> None:
        self.assertIn("probe:replacement_preserved=1", self._probe("replaced"))

    def test_existing_nodes_are_not_adopted_or_overwritten(self) -> None:
        self.assertIn("probe:collision_preserved=1", self._probe("collision"))

    def test_nonexclusive_scope_rejects_before_creating_nodes(self) -> None:
        self.assertIn("probe:nonexclusive_rejected=1", self._probe("nonexclusive"))

    def test_existing_empty_child_rejects_without_changing_scope(self) -> None:
        self.assertIn("probe:existing_empty_child_preserved=1", self._probe("other-empty"))

    def test_root_unique_but_populated_child_rejects_without_changing_scope(self) -> None:
        self.assertIn("probe:existing_populated_child_preserved=1",
                      self._probe("other-populated"))

    def test_legal_large_cap_is_exact_or_fails_closed(self) -> None:
        self.assertIn("probe:large_cap_exact_or_rejected=1", self._probe("max-cap"))

    def test_modified_quota_rejects_before_creating_payload(self) -> None:
        self.assertIn("probe:modified_limit_rejected=1", self._probe("modified-limit"))

    def test_scope_not_writable_rejects_before_payload(self) -> None:
        self.assertIn("probe:scope_not_writable_rejected=1",
                      self._probe("scope-not-writable", delegated=False))

    def test_close_does_not_report_or_perform_finish(self) -> None:
        self.assertIn("probe:close_is_not_finish=1", self._probe("close"))


if __name__ == "__main__":
    unittest.main()
