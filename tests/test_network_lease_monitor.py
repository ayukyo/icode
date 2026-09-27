"""Automatic expiry sweeping stays owned by trusted host code."""

from __future__ import annotations

import socket
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tests import _support  # noqa: F401  # Add the repository's src/ to sys.path.

from icode.approvals import ScriptedApprover
from icode.network_lease import (
    NetworkLeaseAuthority,
    NetworkPurpose,
)
from icode.sandbox_policy import NetworkMode, SandboxPolicy


class NetworkLeaseMonitorTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.workspace = Path(self._temporary_directory.name).resolve()
        self.policy = SandboxPolicy(
            schema_version=1,
            run_id="run-monitor-test",
            ticket_id="ICODE-NET-MONITOR",
            step="code",
            workspace_root=self.workspace,
            read_roots=(self.workspace,),
            write_roots=(self.workspace,),
            deny_read_roots=(self.workspace / ".git",),
            deny_write_roots=(self.workspace / ".git",),
            network_mode=NetworkMode.DENY,
            allowed_domains=(),
            process_limit=8,
            wall_timeout_seconds=60,
            output_limit_bytes=4096,
            protected_paths=(self.workspace / ".git",),
        )
        self.authority = NetworkLeaseAuthority()

    def issue_lease(self):
        return self.authority.request_lease(
            self.policy,
            approver=ScriptedApprover([True]),
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            allowed_domains=("packages.example",),
            ttl_seconds=1,
        )

    def make_tcp_pair(self) -> tuple[socket.socket, socket.socket]:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.settimeout(2.0)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        self.addCleanup(listener.close)

        proxy_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(proxy_socket.close)
        proxy_socket.connect(listener.getsockname())
        peer, _ = listener.accept()
        peer.settimeout(3.0)
        self.addCleanup(peer.close)
        return proxy_socket, peer

    def test_expiry_monitor_closes_a_real_registered_tcp_socket(self) -> None:
        from icode.network_lease import NetworkLeaseExpiryMonitor

        issued = self.issue_lease()
        proxy_socket, peer = self.make_tcp_pair()
        self.authority.register_active_sockets(
            issued,
            self.policy,
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            hostname="packages.example",
            port=443,
            now_monotonic_ns=time.monotonic_ns(),
            sockets=(proxy_socket,),
        )
        monitor = NetworkLeaseExpiryMonitor(
            self.authority,
            sweep_interval_seconds=0.01,
        )
        self.addCleanup(monitor.stop)

        monitor.start()

        self.assertEqual(peer.recv(1), b"")
        self.assertTrue(monitor.stop())
        self.assertFalse(monitor.running)

    def test_failed_expiry_close_is_retried_without_killing_monitor(self) -> None:
        from icode.network_lease import NetworkLeaseExpiryMonitor

        issued = self.issue_lease()
        first_attempt = threading.Event()
        second_attempt = threading.Event()
        attempts = 0

        def close_once_fails() -> bool:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                first_attempt.set()
                return False
            second_attempt.set()
            return True

        self.authority.register_active_connection(
            issued,
            self.policy,
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            hostname="packages.example",
            port=443,
            now_monotonic_ns=time.monotonic_ns(),
            close=close_once_fails,
        )
        monitor = NetworkLeaseExpiryMonitor(
            self.authority,
            sweep_interval_seconds=0.01,
        )
        self.addCleanup(monitor.stop)

        monitor.start()

        self.assertTrue(first_attempt.wait(timeout=3.0))
        self.assertTrue(second_attempt.wait(timeout=3.0))
        self.assertGreaterEqual(monitor.failure_count, 1)
        self.assertTrue(monitor.running)
        self.assertTrue(monitor.stop())

    def test_failed_sweep_reports_only_a_fixed_health_category(self) -> None:
        from icode.network_lease import NetworkLeaseExpiryMonitor

        issued = self.issue_lease()
        callback_started = threading.Event()

        def fail_with_sensitive_error() -> bool:
            callback_started.set()
            raise OSError("private-host.example:443 connection detail")

        self.authority.register_active_connection(
            issued,
            self.policy,
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            hostname="packages.example",
            port=443,
            now_monotonic_ns=time.monotonic_ns(),
            close=fail_with_sensitive_error,
        )
        monitor = NetworkLeaseExpiryMonitor(
            self.authority,
            sweep_interval_seconds=0.5,
        )
        self.addCleanup(monitor.stop)

        monitor.start()

        self.assertTrue(callback_started.wait(timeout=3.0))
        deadline = time.monotonic() + 1.0
        while monitor.failure_count == 0 and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertGreaterEqual(monitor.failure_count, 1)
        self.assertEqual(monitor.last_error, "connection_cleanup_failed")
        self.assertNotIn("private-host", str(monitor.last_error))
        self.assertTrue(monitor.stop())

    def test_monitor_validates_interval_and_is_single_use(self) -> None:
        from icode.network_lease import NetworkLeaseExpiryMonitor

        for invalid_interval in (
            True, 0, 0.001, 1.1, float("inf"), float("nan"), 10**10_000,
        ):
            with self.subTest(interval=invalid_interval):
                with self.assertRaises(ValueError):
                    NetworkLeaseExpiryMonitor(
                        self.authority,
                        sweep_interval_seconds=invalid_interval,
                    )

        monitor = NetworkLeaseExpiryMonitor(self.authority)
        self.assertTrue(monitor.stop())
        with self.assertRaises(RuntimeError):
            monitor.start()

    def test_stop_reports_when_sweep_thread_exceeds_join_deadline(self) -> None:
        from icode.network_lease import NetworkLeaseExpiryMonitor

        sweep_entered = threading.Event()
        release_sweep = threading.Event()

        def blocked_sweep(_now_monotonic_ns: int) -> int:
            sweep_entered.set()
            release_sweep.wait(timeout=2.0)
            return 0

        monitor = NetworkLeaseExpiryMonitor(self.authority)
        self.addCleanup(monitor.stop)
        self.addCleanup(release_sweep.set)

        with patch.object(
            self.authority,
            "close_expired_connections",
            side_effect=blocked_sweep,
        ), patch(
            "icode.network_lease.NETWORK_LEASE_MONITOR_STOP_TIMEOUT_SECONDS",
            0.05,
        ):
            monitor.start()
            self.assertTrue(sweep_entered.wait(timeout=1.0))
            self.assertFalse(monitor.stop())
            release_sweep.set()
            self.assertTrue(monitor.stop())


if __name__ == "__main__":
    unittest.main()
