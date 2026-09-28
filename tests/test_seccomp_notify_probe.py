"""Linux seccomp USER_NOTIF test-only prototype; never scores product readiness."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(
    sys.platform.startswith("linux") and shutil.which("cc"),
    "需要 Linux 与 C 编译器",
)
class TestSeccompUserNotificationProbe(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temporary_directory = tempfile.TemporaryDirectory(
            prefix="icode-seccomp-notify-test-",
        )
        cls.addClassCleanup(cls._temporary_directory.cleanup)
        root = Path(cls._temporary_directory.name)
        source = (
            Path(__file__).resolve().parent
            / "fixtures"
            / "native"
            / "seccomp_user_notif_probe.c"
        )
        cls._executable = root / "seccomp-user-notif-probe"
        result = subprocess.run(
            [
                shutil.which("cc") or "cc",
                "-std=c11",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                str(source),
                "-o",
                str(cls._executable),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        if result.returncode != 0:
            raise AssertionError(f"native probe compile failed: {result.stderr[-1200:]}")

    def _run_probe(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(self._executable), *arguments],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )

    def test_user_notification_denial_has_broker_and_allow_positive_controls(self) -> None:
        result = self._run_probe()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("probe:seccomp_user_notification=received", result.stdout)
        self.assertIn("probe:observer_ack_before_syscall=1", result.stdout)
        self.assertIn("probe:broker_reply=EPERM", result.stdout)
        self.assertIn("probe:allowed_unix_socketpair=1", result.stdout)
        self.assertIn("probe:payload_denied_errno=EPERM", result.stdout)
        self.assertIn("probe:conformance_credit=none", result.stdout)
        self.assertNotIn("probe:receipt=", result.stdout)

    def test_observer_handshake_rejection_prevents_payload_start(self) -> None:
        result = self._run_probe("--reject-handshake")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("probe:handshake_rejected=1", result.stdout)
        self.assertIn("probe:payload_started=0", result.stdout)
        self.assertIn("probe:conformance_credit=none", result.stdout)

    def test_normal_exit_13_emits_no_notification_marker(self) -> None:
        result = self._run_probe("--exit-13")

        self.assertEqual(result.returncode, 13)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
