"""Linux 原生助手异常退出时的真实后代清理回归。"""

from __future__ import annotations

import array
import errno
import hashlib
import os
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from tests._support import temp_workspace
from icode.execution_broker import execute_policy_command
from icode.isolation import LandlockSandbox, probe_linux_process_tree_cleanup
from icode.sandbox_policy import NetworkMode, SandboxPolicy


@unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("cc"),
                     "需要 Linux C 编译器；命名空间权限由用例实测")
class TestLinuxPidNamespaceCleanup(unittest.TestCase):
    @staticmethod
    def _namespace_network_permission_denied(stderr: str) -> bool:
        return (
            "unshare user/pid/network namespace: Operation not permitted" in stderr
            or "unshare user/pid/network namespace: Permission denied" in stderr
            or any(
                f"ICODE_LOOPBACK_SETUP_FAILURE stage=enable errno={code}" in stderr
                for code in (errno.EPERM, errno.EACCES)
            )
        )

    def _probe_loopback_network_namespace(
        self,
        helper_command: tuple[str, ...],
        *,
        workspace: Path,
        marker: Path,
    ) -> tuple[bool, str]:
        """Check loopback setup before an opaque proxy handoff can hide stderr."""
        system_python = Path("/usr/bin/python3")
        self.assertTrue(system_python.is_file())
        if not helper_command or any(not part for part in helper_command):
            self.fail("invalid loopback namespace preflight command")
        parent_netns = os.readlink("/proc/self/ns/net")
        payload = (
            "import os, socket\n"
            f"assert os.readlink('/proc/self/ns/net') != {parent_netns!r}\n"
            "server = socket.socket(socket.AF_INET, socket.SOCK_STREAM, "
            "socket.IPPROTO_TCP)\n"
            "server.bind(('127.0.0.1', 0)); server.listen(1)\n"
            "server.close()\n"
            f"open({str(marker)!r}, 'wb').close()\n"
        )
        result = subprocess.run(
            [
                *helper_command,
                "--workspace", str(workspace),
                "--parent-pid", str(os.getpid()),
                "--network-loopback-only", "--",
                str(system_python), "-c", payload,
            ],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        if result.returncode == 0:
            self.assertTrue(marker.is_file(), result.stderr)
            return True, result.stderr
        if self._namespace_network_permission_denied(result.stderr):
            self.assertFalse(marker.exists(), result.stderr)
            return False, result.stderr
        self.fail(
            "loopback namespace preflight failed unexpectedly: "
            f"exit={result.returncode}, stderr={result.stderr!r}"
        )

    def test候选E2E前置探测识别loopback权限失败且payload未运行(self) -> None:
        source = Path(__file__).resolve().parents[1] / "native/linux/icode_landlock.c"
        launcher_source = (
            Path(__file__).resolve().parent / "native/deny_loopback_ioctl.c"
        )
        compiler = shutil.which("cc") or "cc"
        with temp_workspace() as root:
            helper = root / "icode-landlock"
            launcher = root / "deny-loopback-ioctl"
            for source_file, executable in (
                (source, helper), (launcher_source, launcher),
            ):
                subprocess.run(
                    [compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                     str(source_file), "-o", str(executable)],
                    check=True, capture_output=True, text=True,
                )
            workspace = root / "code"
            workspace.mkdir()
            marker = workspace / "loopback-preflight-ran"
            available, detail = self._probe_loopback_network_namespace(
                (str(launcher), str(helper)), workspace=workspace, marker=marker,
            )

        self.assertFalse(available, detail)
        self.assertIn(
            f"ICODE_LOOPBACK_SETUP_FAILURE stage=enable errno={errno.EPERM}", detail,
        )
        self.assertFalse(marker.exists())

    def test_loopback代理实验态不能到宿主或外部网络(self) -> None:
        source = Path(__file__).resolve().parents[1] / "native/linux/icode_landlock.c"
        system_python = Path("/usr/bin/python3")
        self.assertTrue(system_python.is_file())
        with temp_workspace() as root:
            helper = root / "icode-landlock"
            subprocess.run(
                [shutil.which("cc") or "cc", "-std=c11", "-O2", "-Wall", "-Wextra",
                 "-Werror", str(source), "-o", str(helper)],
                check=True, capture_output=True, text=True,
            )
            workspace = root / "code"
            workspace.mkdir()
            payload_started = workspace / "payload-started"
            host_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                host_listener.bind(("127.0.0.1", 0))
                host_listener.listen(1)
                host_port = host_listener.getsockname()[1]
                parent_netns = os.readlink("/proc/self/ns/net")
                code = (
                    "from pathlib import Path\n"
                    f"Path({str(payload_started)!r}).write_text('started')\n"
                    "import errno, os, socket\n"
                    f"assert os.readlink('/proc/self/ns/net') != {parent_netns!r}\n"
                    "server = socket.socket(socket.AF_INET, socket.SOCK_STREAM,\n"
                    "                       socket.IPPROTO_TCP)\n"
                    "server.bind(('127.0.0.1', 0)); server.listen(1)\n"
                    "client = socket.create_connection(server.getsockname(), timeout=1)\n"
                    "accepted, _ = server.accept()\n"
                    "client.sendall(b'loopback'); assert accepted.recv(8) == b'loopback'\n"
                    "accepted.close(); client.close(); server.close()\n"
                    "host = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
                    "host_result = host.connect_ex(('127.0.0.1', "
                    f"{host_port}))\n"
                    "host.close()\n"
                    "assert host_result == errno.ECONNREFUSED, host_result\n"
                    "outside = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
                    "outside.settimeout(1)\n"
                    "outside_result = outside.connect_ex(('198.51.100.1', 443))\n"
                    "outside.close()\n"
                    "assert outside_result == errno.ENETUNREACH, outside_result\n"
                    "if socket.has_ipv6:\n"
                    "    ipv6 = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)\n"
                    "    ipv6.settimeout(1)\n"
                    "    ipv6_result = ipv6.connect_ex(('2001:db8::1', 443, 0, 0))\n"
                    "    ipv6.close()\n"
                    "    assert ipv6_result in (errno.ENETUNREACH,\n"
                    "                           errno.EHOSTUNREACH,\n"
                    "                           errno.EAFNOSUPPORT), ipv6_result\n"
                    "for family, kind, protocol in (\n"
                    "    (socket.AF_INET, socket.SOCK_DGRAM, 0),\n"
                    "    (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_UDP),\n"
                    "    (socket.AF_UNIX, socket.SOCK_STREAM, 0),\n"
                    "):\n"
                    "    try: socket.socket(family, kind, protocol)\n"
                    "    except OSError as exc: assert exc.errno == errno.EPERM, exc\n"
                    "    else: raise AssertionError('non-proxy socket type allowed')\n"
                    "for kind in (socket.SOCK_STREAM, socket.SOCK_DGRAM,\n"
                    "             socket.SOCK_SEQPACKET):\n"
                    "    pair_left, pair_right = socket.socketpair(\n"
                    "        socket.AF_UNIX, kind)\n"
                    "    pair_left.send(b'ipc'); assert pair_right.recv(3) == b'ipc'\n"
                    "    pair_left.close(); pair_right.close()\n"
                    "try: socket.socketpair(socket.AF_INET)\n"
                    "except OSError as exc: assert exc.errno == errno.EPERM, exc\n"
                    "else: raise AssertionError('non-local socketpair allowed')\n"
                    "for family, kind, protocol in (\n"
                    "    (socket.AF_UNIX, socket.SOCK_RAW, 0),\n"
                    "    (socket.AF_UNIX, socket.SOCK_STREAM, 1),\n"
                    "):\n"
                    "    try: socket.socketpair(family, kind, protocol)\n"
                    "    except OSError as exc: assert exc.errno == errno.EPERM, exc\n"
                    "    else: raise AssertionError('invalid local socketpair allowed')\n"
                    "print('isolated-loopback-only')\n"
                )
                result = subprocess.run(
                    [str(helper), "--workspace", str(workspace),
                     "--parent-pid", str(os.getpid()), "--network-loopback-only", "--",
                     str(system_python), "-c", code],
                    capture_output=True, text=True, timeout=8, check=False,
                )
            finally:
                host_listener.close()

            setup_failure = next(
                (line for line in result.stderr.splitlines()
                 if line.startswith("ICODE_LOOPBACK_SETUP_FAILURE ")),
                None,
            )
            if setup_failure is not None:
                fields = dict(
                    field.split("=", 1)
                    for field in setup_failure.split()[1:]
                    if "=" in field
                )
                if (fields.get("stage") == "enable"
                        and fields.get("errno") in {
                            str(errno.EPERM), str(errno.EACCES),
                        }):
                    self.assertFalse(payload_started.exists(), result.stderr)
                    self.skipTest(
                        "runner 不允许在新 network namespace 配置 loopback; "
                        "探测已失败关闭，正向网络验证未执行"
                    )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("isolated-loopback-only", result.stdout)

    def test可信helper交接后授权隧道随租约到期关闭(self) -> None:
        from icode.execution_broker import execute_linux_leased_connect_candidate
        from icode.approvals import ScriptedApprover
        from icode.network_destination import ResolvedNetworkTarget
        from icode.network_lease import NetworkLeaseAuthority, NetworkPurpose
        from icode.network_proxy_scope import HostConnectRuntime

        source = Path(__file__).resolve().parents[1] / "native/linux/icode_landlock.c"
        system_python = Path("/usr/bin/python3")
        self.assertTrue(system_python.is_file())
        with temp_workspace() as root:
            helper = root / "icode-landlock"
            subprocess.run(
                [shutil.which("cc") or "cc", "-std=c11", "-O2", "-Wall", "-Wextra",
                 "-Werror", str(source), "-o", str(helper)],
                check=True, capture_output=True, text=True,
            )
            manifest = root / "icode-landlock.sha256"
            manifest.write_text(
                hashlib.sha256(helper.read_bytes()).hexdigest() + "\n",
                encoding="ascii",
            )
            sandbox = LandlockSandbox(helper=str(helper), manifest=str(manifest))
            workspace = root / "code"
            workspace.mkdir()
            preflight_marker = workspace / "loopback-preflight-ran"
            loopback_available, preflight_detail = (
                self._probe_loopback_network_namespace(
                    (str(helper),), workspace=workspace, marker=preflight_marker,
                )
            )
            if not loopback_available:
                self.assertFalse(preflight_marker.exists(), preflight_detail)
                self.skipTest(
                    "runner blocks namespace loopback setup; preflight failed closed"
                )
            policy = SandboxPolicy(
                schema_version=1,
                run_id="linux-proxy-handoff-run",
                ticket_id="ICODE-LINUX-PROXY-HANDOFF",
                step="code",
                workspace_root=workspace,
                read_roots=(workspace,),
                write_roots=(workspace,),
                deny_read_roots=(),
                deny_write_roots=(),
                network_mode=NetworkMode.DENY,
                allowed_domains=(),
                process_limit=8,
                wall_timeout_seconds=60,
                output_limit_bytes=4096,
                protected_paths=(),
            )
            authority = NetworkLeaseAuthority()
            issued = authority.request_lease(
                policy,
                approver=ScriptedApprover([True]),
                purpose=NetworkPurpose.PACKAGE_INSTALL,
                allowed_domains=("packages.example",),
                ttl_seconds=5,
            )
            runtime = HostConnectRuntime(authority, sweep_interval_seconds=0.01)
            runtime.start()
            scope = runtime.create_scope(
                issued, policy, NetworkPurpose.PACKAGE_INSTALL,
            )
            upstream_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            upstream_listener.bind(("127.0.0.1", 0))
            upstream_listener.listen(1)
            upstream_listener.settimeout(3.0)
            host_only_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            host_only_listener.bind(("127.0.0.1", 0))
            host_only_listener.listen(1)
            upstream: socket.socket | None = None
            result_holder = []
            executor_thread: threading.Thread | None = None
            try:
                worker = (
                    "import errno, os, socket\n"
                    "try: socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)\n"
                    "except OSError as exc: assert exc.errno == errno.EPERM, exc\n"
                    "else: raise AssertionError('worker created a new AF_UNIX socket')\n"
                    "host, port = os.environ['ICODE_PROXY_LISTENER'].rsplit(':', 1)\n"
                    "proxy_port = int(port)\n"
                    f"host_ports = ({upstream_listener.getsockname()[1]}, "
                    f"{host_only_listener.getsockname()[1]})\n"
                    "blocked_port = next(candidate for candidate in host_ports\n"
                    "                     if candidate != proxy_port)\n"
                    "direct = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
                    "direct_result = direct.connect_ex(('127.0.0.1', blocked_port))\n"
                    "direct.close()\n"
                    "assert direct_result == errno.ECONNREFUSED, direct_result\n"
                    "client = socket.create_connection((host, int(port)), timeout=2)\n"
                    "client.sendall(b'CONNECT packages.example:443 HTTP/1.1\\r\\n"
                    "Host: packages.example\\r\\n\\r\\n')\n"
                    "response = bytearray()\n"
                    "while not response.endswith(b'\\r\\n\\r\\n'):\n"
                    "    response.extend(client.recv(1))\n"
                    "assert response == b'HTTP/1.1 200 Connection Established"
                    "\\r\\n\\r\\n', response\n"
                    "client.sendall(b'worker-to-host-marker')\n"
                    "client.shutdown(socket.SHUT_WR)\n"
                    "expected = b'host-to-worker-marker'\n"
                    "reply = bytearray()\n"
                    "while len(reply) < len(expected):\n"
                    "    reply.extend(client.recv(len(expected) - len(reply)))\n"
                    "assert reply == expected, reply\n"
                    "client.settimeout(10)\n"
                    "assert client.recv(1) == b'', 'lease expiry did not close client'\n"
                    "client.close()\n"
                    "print('lease-expiry-closed-client')\n"
                )
                resolver = lambda hostname, port, resolver=None: (
                    ResolvedNetworkTarget(
                        family=socket.AF_INET,
                        socket_type=socket.SOCK_STREAM,
                        protocol=socket.IPPROTO_TCP,
                        sockaddr=upstream_listener.getsockname(),
                    ),
                )
                def execute() -> None:
                    result_holder.append(execute_linux_leased_connect_candidate(
                        [str(system_python), "-c", worker],
                        cwd=workspace,
                        sandbox=sandbox,
                        policy=policy,
                        scope=scope,
                        timeout=15,
                    ))

                executor_thread = threading.Thread(target=execute, daemon=True)
                with (
                    mock.patch(
                        "icode.network_connector.resolve_public_tcp_targets",
                        side_effect=resolver,
                    ),
                    mock.patch.dict(os.environ, {
                        "ICODE_PROXY_LISTENER": "198.51.100.9:443",
                    }),
                ):
                    executor_thread.start()
                    try:
                        upstream, _address = upstream_listener.accept()
                    except socket.timeout:
                        executor_thread.join(timeout=18)
                        if result_holder and self._namespace_network_permission_denied(
                            result_holder[0].output
                        ):
                            self.assertNotIn(
                                "handoff-proxy-payload-ran", result_holder[0].output,
                            )
                            self.skipTest(
                                "runner blocks user/network namespace setup; helper failed closed"
                            )
                        self.fail(
                            "host proxy did not receive the worker CONNECT request: "
                            + (str(result_holder[0]) if result_holder else "launcher still running")
                        )
                    upstream.settimeout(10.0)
                    self.assertEqual(upstream.recv(64), b"worker-to-host-marker")
                    upstream.sendall(b"host-to-worker-marker")
                    # The active tunnel must remain open until lease expiry,
                    # then the authority must close the peer owned by relay.
                    self.assertEqual(upstream.recv(1), b"")
                    executor_thread.join(timeout=18)
                self.assertFalse(executor_thread.is_alive(), "trusted launcher did not finish")
                result = result_holder[0]
                self.assertIsNone(result.error, result.output)
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertTrue(result.cleanup_ok)
                self.assertIn("lease-expiry-closed-client", result.output)
                self.assertGreaterEqual(
                    time.monotonic_ns(), issued.lease.expires_at_monotonic_ns,
                )

                expired_marker = workspace / "expired-scope-payload-ran"
                expired_result = execute_linux_leased_connect_candidate(
                    [str(system_python), "-c",
                     f"from pathlib import Path; Path({str(expired_marker)!r}).touch()"],
                    cwd=workspace, sandbox=sandbox, policy=policy, scope=scope,
                    timeout=3,
                )
                self.assertEqual(expired_result.error, "proxy_setup_failed")
                self.assertTrue(expired_result.cleanup_ok)
                self.assertFalse(expired_marker.exists())
            finally:
                if executor_thread is not None:
                    executor_thread.join(timeout=18)
                runtime.close()
                upstream_listener.close()
                host_only_listener.close()
                if upstream is not None:
                    upstream.close()

    def test_helper未交接listener时launcher失败关闭scope且不运行payload(self) -> None:
        from icode.approvals import ScriptedApprover
        from icode.execution_broker import execute_linux_leased_connect_candidate
        from icode.network_lease import (
            NetworkLeaseAuthority,
            NetworkLeaseValidationError,
            NetworkPurpose,
        )
        from icode.network_proxy_scope import HostConnectRuntime

        with temp_workspace() as root:
            helper = root / "helper-exits-before-handoff"
            helper.write_text("#!/bin/sh\nexit 37\n", encoding="ascii")
            helper.chmod(0o755)
            manifest = root / "helper.sha256"
            manifest.write_text(
                hashlib.sha256(helper.read_bytes()).hexdigest() + "\n",
                encoding="ascii",
            )
            workspace = (root / "code").resolve()
            workspace.mkdir()
            policy = SandboxPolicy(
                schema_version=1, run_id="failed-handoff", ticket_id="failed-handoff",
                step="code", workspace_root=workspace, read_roots=(workspace,),
                write_roots=(workspace,), deny_read_roots=(), deny_write_roots=(),
                network_mode=NetworkMode.DENY, allowed_domains=(), process_limit=8,
                wall_timeout_seconds=5, output_limit_bytes=1024, protected_paths=(),
            )
            authority = NetworkLeaseAuthority()
            issued = authority.request_lease(
                policy,
                approver=ScriptedApprover([True]),
                purpose=NetworkPurpose.PACKAGE_INSTALL,
                allowed_domains=("packages.example",),
                ttl_seconds=30,
            )
            runtime = HostConnectRuntime(authority, sweep_interval_seconds=0.01)
            runtime.start()
            scope = runtime.create_scope(
                issued, policy, NetworkPurpose.PACKAGE_INSTALL,
            )
            marker = workspace / "payload-ran"
            try:
                result = execute_linux_leased_connect_candidate(
                    ["/usr/bin/touch", str(marker)],
                    cwd=workspace,
                    sandbox=LandlockSandbox(helper=str(helper), manifest=str(manifest)),
                    policy=policy,
                    scope=scope,
                    timeout=3,
                )
                self.assertEqual(result.error, "proxy_setup_failed")
                self.assertTrue(result.cleanup_ok)
                self.assertFalse(marker.exists())
                with self.assertRaises(NetworkLeaseValidationError):
                    scope.verify_lease()
            finally:
                runtime.close()

    def test已撤销租约在launcher前拒绝且回收scope(self) -> None:
        from icode.approvals import ScriptedApprover
        from icode.execution_broker import execute_linux_leased_connect_candidate
        from icode.network_lease import NetworkLeaseAuthority, NetworkPurpose
        from icode.network_proxy_scope import HostConnectRuntime

        with temp_workspace() as root:
            workspace = (root / "code").resolve()
            workspace.mkdir()
            policy = SandboxPolicy(
                schema_version=1, run_id="revoked-before-launch", ticket_id="revoked-before-launch",
                step="code", workspace_root=workspace, read_roots=(workspace,),
                write_roots=(workspace,), deny_read_roots=(), deny_write_roots=(),
                network_mode=NetworkMode.DENY, allowed_domains=(), process_limit=8,
                wall_timeout_seconds=5, output_limit_bytes=1024, protected_paths=(),
            )
            authority = NetworkLeaseAuthority()
            issued = authority.request_lease(
                policy,
                approver=ScriptedApprover([True]),
                purpose=NetworkPurpose.PACKAGE_INSTALL,
                allowed_domains=("packages.example",),
                ttl_seconds=30,
            )
            runtime = HostConnectRuntime(authority, sweep_interval_seconds=1.0)
            runtime.start()
            time.sleep(0.02)  # Let the monitor's initial sweep finish before revocation.
            scope = runtime.create_scope(
                issued, policy, NetworkPurpose.PACKAGE_INSTALL,
            )
            self.assertGreater(authority.revoke(policy), issued.lease.generation)
            marker = workspace / "payload-ran"
            try:
                result = execute_linux_leased_connect_candidate(
                    ["/usr/bin/touch", str(marker)],
                    cwd=workspace,
                    sandbox=LandlockSandbox(helper=str(root / "missing-helper")),
                    policy=policy,
                    scope=scope,
                    timeout=3,
                )
                self.assertEqual(result.error, "proxy_setup_failed")
                self.assertTrue(result.cleanup_ok)
                self.assertFalse(marker.exists())
                self.assertTrue(scope._closed)
                self.assertNotIn(id(scope), runtime._scopes)
            finally:
                runtime.close()

    def test策略不匹配scope拒绝launcher但不关闭其他工单scope(self) -> None:
        from dataclasses import replace

        from icode.approvals import ScriptedApprover
        from icode.execution_broker import execute_linux_leased_connect_candidate
        from icode.network_lease import NetworkLeaseAuthority, NetworkPurpose
        from icode.network_proxy_scope import HostConnectRuntime

        with temp_workspace() as root:
            workspace = (root / "code").resolve()
            workspace.mkdir()
            policy = SandboxPolicy(
                schema_version=1, run_id="scope-owner", ticket_id="scope-owner",
                step="code", workspace_root=workspace, read_roots=(workspace,),
                write_roots=(workspace,), deny_read_roots=(), deny_write_roots=(),
                network_mode=NetworkMode.DENY, allowed_domains=(), process_limit=8,
                wall_timeout_seconds=5, output_limit_bytes=1024, protected_paths=(),
            )
            authority = NetworkLeaseAuthority()
            issued = authority.request_lease(
                policy,
                approver=ScriptedApprover([True]),
                purpose=NetworkPurpose.PACKAGE_INSTALL,
                allowed_domains=("packages.example",),
                ttl_seconds=30,
            )
            runtime = HostConnectRuntime(authority, sweep_interval_seconds=1.0)
            runtime.start()
            time.sleep(0.02)
            scope = runtime.create_scope(
                issued, policy, NetworkPurpose.PACKAGE_INSTALL,
            )
            try:
                result = execute_linux_leased_connect_candidate(
                    ["/usr/bin/true"],
                    cwd=workspace,
                    sandbox=LandlockSandbox(helper=str(root / "missing-helper")),
                    policy=replace(policy, ticket_id="different-ticket"),
                    scope=scope,
                    timeout=3,
                )
                self.assertEqual(result.error, "proxy_setup_failed")
                self.assertTrue(result.cleanup_ok)
                self.assertFalse(scope._closed)
                scope.verify_lease()
                self.assertIn(id(scope), runtime._scopes)
            finally:
                runtime.close()

    def test错误host_ack时payload不会启动(self) -> None:
        from icode.linux_proxy_handoff import create_loopback_listener_handoff_channel

        source = Path(__file__).resolve().parents[1] / "native/linux/icode_landlock.c"
        with temp_workspace() as root:
            helper = root / "icode-landlock"
            subprocess.run(
                [shutil.which("cc") or "cc", "-std=c11", "-O2", "-Wall", "-Wextra",
                 "-Werror", str(source), "-o", str(helper)],
                check=True, capture_output=True, text=True,
            )
            workspace = root / "code"
            workspace.mkdir()
            marker = workspace / "must-not-run"
            host_control, sender_control = create_loopback_listener_handoff_channel()
            process: subprocess.Popen[str] | None = None
            descriptors: list[int] = []
            try:
                command = [
                    str(helper), "--workspace", str(workspace),
                    "--parent-pid", str(os.getpid()), "--network-loopback-only",
                    "--proxy-control-fd", str(sender_control.fileno()), "--",
                    "/usr/bin/touch", str(marker),
                ]
                process = subprocess.Popen(
                    command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, pass_fds=(sender_control.fileno(),),
                )
                sender_control.close()
                host_control.settimeout(4)
                payload, ancillary, flags, _ = host_control.recvmsg(
                    128,
                    socket.CMSG_SPACE(array.array("i").itemsize)
                    + socket.CMSG_SPACE(struct.calcsize("3i")),
                )
                if payload == b"":
                    _stdout, stderr = process.communicate(timeout=3)
                    if self._namespace_network_permission_denied(stderr):
                        self.skipTest(
                            "runner blocks user/network namespace setup; helper failed closed"
                        )
                self.assertFalse(flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC))
                self.assertTrue(payload.startswith(b"ICODE_PROXY_LISTENER_V1"))
                self.assertEqual(len(payload), len(b"ICODE_PROXY_LISTENER_V1") + 16)
                credentials = []
                for level, kind, data in ancillary:
                    if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                        values = array.array("i")
                        values.frombytes(data[:len(data) - len(data) % values.itemsize])
                        descriptors.extend(values)
                    elif level == socket.SOL_SOCKET and kind == socket.SCM_CREDENTIALS:
                        credentials.append(struct.unpack("3i", data))
                self.assertEqual(len(descriptors), 1)
                self.assertEqual(len(credentials), 1)
                self.assertEqual(credentials[0][0], process.pid)
                nonce_offset = len(b"ICODE_PROXY_LISTENER_V1")
                nonce = payload[nonce_offset:]
                self.assertEqual(len(nonce), 16)
                wrong_nonce = bytes([nonce[0] ^ 1]) + nonce[1:]
                host_control.send(b"ICODE_PROXY_LISTENER_ACK_V1" + wrong_nonce)
                _stdout, stderr = process.communicate(timeout=5)
                self.assertNotEqual(process.returncode, 0, stderr)
                self.assertFalse(marker.exists())
            finally:
                for descriptor in descriptors:
                    os.close(descriptor)
                if process is not None and process.poll() is None:
                    process.kill()
                    process.communicate(timeout=3)
                sender_control.close()
                host_control.close()

    def test不存在的proxy_control_fd在namespace和payload启动前失败(self) -> None:
        source = Path(__file__).resolve().parents[1] / "native/linux/icode_landlock.c"
        with temp_workspace() as root:
            helper = root / "icode-landlock"
            subprocess.run(
                [shutil.which("cc") or "cc", "-std=c11", "-O2", "-Wall", "-Wextra",
                 "-Werror", str(source), "-o", str(helper)],
                check=True, capture_output=True, text=True,
            )
            workspace = root / "code"
            workspace.mkdir()
            marker = workspace / "must-not-run"
            result = subprocess.run(
                [str(helper), "--workspace", str(workspace),
                 "--parent-pid", str(os.getpid()), "--network-loopback-only",
                 "--proxy-control-fd", str(2**31 - 1), "--",
                 "/usr/bin/touch", str(marker)],
                capture_output=True, text=True, timeout=4, check=False,
            )

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("proxy control descriptor is not a trusted channel", result.stderr)
        self.assertFalse(marker.exists())

    def test_host关闭handoff控制通道时payload不会启动(self) -> None:
        from icode.linux_proxy_handoff import create_loopback_listener_handoff_channel

        source = Path(__file__).resolve().parents[1] / "native/linux/icode_landlock.c"
        with temp_workspace() as root:
            helper = root / "icode-landlock"
            subprocess.run(
                [shutil.which("cc") or "cc", "-std=c11", "-O2", "-Wall", "-Wextra",
                 "-Werror", str(source), "-o", str(helper)],
                check=True, capture_output=True, text=True,
            )
            workspace = root / "code"
            workspace.mkdir()
            marker = workspace / "must-not-run"
            host_control, sender_control = create_loopback_listener_handoff_channel()
            process: subprocess.Popen[str] | None = None
            descriptors: list[int] = []
            try:
                command = [
                    str(helper), "--workspace", str(workspace),
                    "--parent-pid", str(os.getpid()), "--network-loopback-only",
                    "--proxy-control-fd", str(sender_control.fileno()), "--",
                    "/usr/bin/touch", str(marker),
                ]
                process = subprocess.Popen(
                    command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, pass_fds=(sender_control.fileno(),),
                )
                sender_control.close()
                host_control.settimeout(4)
                payload, ancillary, flags, _ = host_control.recvmsg(
                    128,
                    socket.CMSG_SPACE(array.array("i").itemsize)
                    + socket.CMSG_SPACE(struct.calcsize("3i")),
                )
                if payload == b"":
                    _stdout, stderr = process.communicate(timeout=3)
                    if self._namespace_network_permission_denied(stderr):
                        self.skipTest(
                            "runner blocks user/network namespace setup; helper failed closed"
                        )
                self.assertFalse(flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC))
                self.assertTrue(payload.startswith(b"ICODE_PROXY_LISTENER_V1"))
                self.assertEqual(len(payload), len(b"ICODE_PROXY_LISTENER_V1") + 16)
                for level, kind, data in ancillary:
                    if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                        values = array.array("i")
                        values.frombytes(data[:len(data) - len(data) % values.itemsize])
                        descriptors.extend(values)
                self.assertEqual(len(descriptors), 1)
                host_control.close()
                _stdout, stderr = process.communicate(timeout=5)
                self.assertNotEqual(process.returncode, 0, stderr)
                self.assertFalse(marker.exists())
            finally:
                for descriptor in descriptors:
                    os.close(descriptor)
                if process is not None and process.poll() is None:
                    process.kill()
                    process.communicate(timeout=3)
                sender_control.close()
                host_control.close()

    def test预先排队的固定ack不能释放payload(self) -> None:
        from icode.linux_proxy_handoff import (
            ProxyHandoffError,
            create_loopback_listener_handoff_channel,
            receive_loopback_listener,
        )

        source = Path(__file__).resolve().parents[1] / "native/linux/icode_landlock.c"
        with temp_workspace() as root:
            helper = root / "icode-landlock"
            subprocess.run(
                [shutil.which("cc") or "cc", "-std=c11", "-O2", "-Wall", "-Wextra",
                 "-Werror", str(source), "-o", str(helper)],
                check=True, capture_output=True, text=True,
            )
            workspace = root / "code"
            workspace.mkdir()
            marker = workspace / "must-not-run"
            host_control, sender_control = create_loopback_listener_handoff_channel()
            process: subprocess.Popen[str] | None = None
            received: socket.socket | None = None
            try:
                # Reproduce the ordering race: the old fixed ACK can be queued
                # before the helper has sent its listener for host validation.
                host_control.send(b"ICODE_PROXY_LISTENER_ACK_V1")
                command = [
                    str(helper), "--workspace", str(workspace),
                    "--parent-pid", str(os.getpid()), "--network-loopback-only",
                    "--proxy-control-fd", str(sender_control.fileno()), "--",
                    "/usr/bin/touch", str(marker),
                ]
                process = subprocess.Popen(
                    command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, pass_fds=(sender_control.fileno(),),
                )
                sender_control.close()
                # Make the close-before-receive ordering deterministic: the
                # queued legacy ACK must be rejected before the host reads the
                # listener packet, regardless of runner scheduling.
                process.wait(timeout=5)
                try:
                    # The helper may reject the stale ACK and close a seqpacket
                    # channel while its SCM_RIGHTS message is still unread. Linux
                    # can surface that close as ECONNRESET instead of delivering
                    # the queued listener; use the production receiver so both
                    # fail-closed outcomes are handled identically.
                    received = receive_loopback_listener(
                        host_control,
                        expected_pid=process.pid,
                        timeout_seconds=4,
                    )
                except ProxyHandoffError:
                    stdout, stderr = process.communicate(timeout=3)
                    if self._namespace_network_permission_denied(stderr):
                        self.assertFalse(marker.exists())
                        self.skipTest(
                            "runner blocks user/network namespace setup; helper failed closed"
                        )
                else:
                    _stdout, stderr = process.communicate(timeout=5)
                self.assertNotEqual(process.returncode, 0, stderr)
                self.assertIn("loopback listener handoff", stderr)
                self.assertFalse(marker.exists())
            finally:
                if received is not None:
                    received.close()
                if process is not None and process.poll() is None:
                    process.kill()
                    process.communicate(timeout=3)
                sender_control.close()
                host_control.close()

    def test_loopback接口配置被拒时payload不会启动(self) -> None:
        source = Path(__file__).resolve().parents[1] / "native/linux/icode_landlock.c"
        launcher_source = (
            Path(__file__).resolve().parent / "native/deny_loopback_ioctl.c"
        )
        with temp_workspace() as root:
            helper = root / "icode-landlock"
            launcher = root / "deny-loopback-ioctl"
            compiler = shutil.which("cc") or "cc"
            for source_file, executable in (
                (source, helper), (launcher_source, launcher),
            ):
                subprocess.run(
                    [compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                     str(source_file), "-o", str(executable)],
                    check=True, capture_output=True, text=True,
                )
            workspace = root / "code"
            workspace.mkdir()
            marker = workspace / "must-not-run"
            result = subprocess.run(
                [str(launcher), str(helper), "--workspace", str(workspace),
                 "--parent-pid", str(os.getpid()), "--network-loopback-only", "--",
                 "/usr/bin/python3", "-c",
                 f"from pathlib import Path; Path({str(marker)!r}).touch()"],
                capture_output=True, text=True, timeout=8, check=False,
            )

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(
            f"ICODE_LOOPBACK_SETUP_FAILURE stage=enable errno={errno.EPERM}",
            result.stderr,
        )
        self.assertFalse(marker.exists())

    def test_loopback代理实验态选项重复时不启动命令(self) -> None:
        source = Path(__file__).resolve().parents[1] / "native/linux/icode_landlock.c"
        with temp_workspace() as root:
            helper = root / "icode-landlock"
            subprocess.run(
                [shutil.which("cc") or "cc", "-std=c11", "-O2", "-Wall", "-Wextra",
                 "-Werror", str(source), "-o", str(helper)],
                check=True, capture_output=True, text=True,
            )
            workspace = root / "code"
            workspace.mkdir()
            marker = workspace / "must-not-run"
            result = subprocess.run(
                [str(helper), "--workspace", str(workspace),
                 "--parent-pid", str(os.getpid()), "--network-loopback-only",
                 "--network-loopback-only", "--", "/usr/bin/touch", str(marker)],
                capture_output=True, text=True, timeout=4, check=False,
            )

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("duplicate loopback-only network option", result.stderr)
        self.assertFalse(marker.exists())

    def test_继承NOCLDWAIT和屏蔽SIGCHLD仍正确等待命令(self) -> None:
        source = Path(__file__).resolve().parents[1] / "native/linux/icode_landlock.c"
        launcher_source = Path(__file__).resolve().parent / "native/no_cldwait_launcher.c"
        system_python = Path("/usr/bin/python3")
        self.assertTrue(system_python.is_file())
        with temp_workspace() as root:
            helper = root / "icode-landlock"
            launcher = root / "no-cldwait-launcher"
            for source_file, executable in ((source, helper), (launcher_source, launcher)):
                subprocess.run(
                    [shutil.which("cc") or "cc", "-std=c11", "-O2", "-Wall", "-Wextra",
                     "-Werror", str(source_file), "-o", str(executable)],
                    check=True, capture_output=True, text=True,
                )
            result = subprocess.run(
                [str(launcher), str(helper), "--workspace", str(root),
                 "--parent-pid", str(os.getpid()), "--",
                 str(system_python), "-c", "print('payload-ok')"],
                capture_output=True, text=True, timeout=4, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("payload-ok", result.stdout)

    def test_宿主预开外部可写FD不能穿透Landlock(self) -> None:
        source = Path(__file__).resolve().parents[1] / "native/linux/icode_landlock.c"
        system_python = Path("/usr/bin/python3")
        self.assertTrue(system_python.is_file())
        with temp_workspace() as root:
            helper = root / "icode-landlock"
            subprocess.run(
                [shutil.which("cc") or "cc", "-std=c11", "-O2", "-Wall", "-Wextra",
                 "-Werror", str(source), "-o", str(helper)],
                check=True, capture_output=True, text=True,
            )
            workspace = root / "code"
            workspace.mkdir()
            outside = root / "outside-secret"
            outside.write_bytes(b"safe")
            with outside.open("r+b") as preopened:
                code = (
                    "import errno, os\n"
                    f"try: os.write({preopened.fileno()}, b'bad')\n"
                    "except OSError as exc:\n"
                    "    assert exc.errno == errno.EBADF, exc\n"
                    "    print('fd-closed')\n"
                    "else: print('fd-leaked')\n"
                )
                result = subprocess.run(
                    [str(helper), "--workspace", str(workspace),
                     "--parent-pid", str(os.getpid()), "--",
                     str(system_python), "-c", code],
                    pass_fds=(preopened.fileno(),), capture_output=True,
                    text=True, timeout=4, check=False,
                )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("fd-closed", result.stdout)
            self.assertEqual(outside.read_bytes(), b"safe")

    def test_忽略SIGCHLD的宿主仍正确等待命令(self) -> None:
        source = Path(__file__).resolve().parents[1] / "native/linux/icode_landlock.c"
        system_python = Path("/usr/bin/python3")
        self.assertTrue(system_python.is_file())
        with temp_workspace() as root:
            helper = root / "icode-landlock"
            subprocess.run(
                [shutil.which("cc") or "cc", "-std=c11", "-O2", "-Wall", "-Wextra",
                 "-Werror", str(source), "-o", str(helper)],
                check=True, capture_output=True, text=True,
            )
            # 驱动进程 exec 助手，外层 unittest 仍保持正常 SIGCHLD，以免
            # Python subprocess 将 ECHILD 误当作正常返回码。
            command = [str(helper), "--workspace", str(root),
                       "--parent-pid", str(os.getpid()), "--",
                       str(system_python), "-c", "print('payload-ok')"]
            driver = (
                "import os, signal\n"
                "signal.signal(signal.SIGCHLD, signal.SIG_IGN)\n"
                f"os.execv({str(helper)!r}, {command!r})\n"
            )
            result = subprocess.run([sys.executable, "-c", driver],
                                    capture_output=True, text=True, timeout=4,
                                    check=False)
            self.assertIn("payload-ok", result.stdout)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_命名空间创建失败绝不降级执行命令(self) -> None:
        source = Path(__file__).resolve().parents[1] / "native/linux/icode_landlock.c"
        denier_source = Path(__file__).resolve().parent / "native/deny_unshare.c"
        system_python = Path("/usr/bin/python3")
        self.assertTrue(system_python.is_file())
        with temp_workspace() as root:
            helper = root / "icode-landlock"
            denier = root / "deny-unshare"
            for source_file, executable in ((source, helper), (denier_source, denier)):
                subprocess.run(
                    [shutil.which("cc") or "cc", "-std=c11", "-O2", "-Wall", "-Wextra",
                     "-Werror", str(source_file), "-o", str(executable)],
                    check=True, capture_output=True, text=True,
                )
            marker = root / "must-not-run"
            code = f"from pathlib import Path; Path({str(marker)!r}).write_text('bad')"
            result = subprocess.run(
                [str(denier), str(helper), "--workspace", str(root),
                 "--parent-pid", str(os.getpid()), "--", str(system_python), "-c", code],
                capture_output=True, text=True, timeout=4, check=False,
            )
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("unshare user/pid namespace", result.stderr)
            self.assertFalse(marker.exists(), "命名空间启动失败却执行了受限命令")

    def test_超时也清理已脱组后代(self) -> None:
        source = Path(__file__).resolve().parents[1] / "native/linux/icode_landlock.c"
        with temp_workspace() as root:
            helper = root / "icode-landlock"
            subprocess.run(
                [shutil.which("cc") or "cc", "-std=c11", "-O2", "-Wall", "-Wextra",
                 "-Werror", str(source), "-o", str(helper)],
                check=True, capture_output=True, text=True,
            )
            workspace = root / "code"
            workspace.mkdir()
            started = workspace / "timeout-started"
            survived = workspace / "timeout-survived"
            grandchild = (
                "import os, time\nfrom pathlib import Path\n"
                "os.setsid()\n"
                f"Path({str(started)!r}).write_text('detached')\n"
                "time.sleep(1.6)\n"
                f"Path({str(survived)!r}).write_text('escaped')\n"
            )
            parent = (
                "import subprocess, sys, time\nfrom pathlib import Path\n"
                f"subprocess.Popen([sys.executable, '-c', {grandchild!r}], "
                "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, "
                "stderr=subprocess.DEVNULL)\n"
                f"for _ in range(200):\n    if Path({str(started)!r}).exists(): break\n"
                "    time.sleep(0.01)\n"
                "else: raise RuntimeError('grandchild did not start')\n"
                "print('detached-started', flush=True)\n"
                "time.sleep(5)\n"
            )
            policy = SandboxPolicy(
                schema_version=1, run_id="pidns-timeout", ticket_id="pidns-timeout",
                step="code", workspace_root=workspace, read_roots=(workspace,),
                write_roots=(workspace,), deny_read_roots=(), deny_write_roots=(),
                network_mode=NetworkMode.DENY, allowed_domains=(), process_limit=8,
                wall_timeout_seconds=1, output_limit_bytes=1024, protected_paths=(),
            )
            result = execute_policy_command(
                LandlockSandbox(helper=str(helper)).wrap(
                    [sys.executable, "-c", parent], workspace=workspace,
                ),
                cwd=workspace, policy=policy, timeout=1,
            )
            self.assertEqual(result.error, "timeout", result)
            self.assertTrue(result.cleanup_ok, result)
            self.assertIn("detached-started", result.output)
            self.assertEqual(started.read_text(encoding="ascii"), "detached")
            time.sleep(1.8)
            self.assertFalse(survived.exists())

    def test_输出超限也清理已脱组后代(self) -> None:
        source = Path(__file__).resolve().parents[1] / "native/linux/icode_landlock.c"
        with temp_workspace() as root:
            helper = root / "icode-landlock"
            subprocess.run(
                [shutil.which("cc") or "cc", "-std=c11", "-O2", "-Wall", "-Wextra",
                 "-Werror", str(source), "-o", str(helper)],
                check=True, capture_output=True, text=True,
            )
            workspace = root / "code"
            workspace.mkdir()
            started = workspace / "output-started"
            survived = workspace / "output-survived"
            grandchild = (
                "import os, time\nfrom pathlib import Path\n"
                "os.setsid()\n"
                f"Path({str(started)!r}).write_text('detached')\n"
                "time.sleep(1.2)\n"
                f"Path({str(survived)!r}).write_text('escaped')\n"
            )
            parent = (
                "import subprocess, sys, time\nfrom pathlib import Path\n"
                f"subprocess.Popen([sys.executable, '-c', {grandchild!r}], "
                "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, "
                "stderr=subprocess.DEVNULL)\n"
                f"for _ in range(200):\n    if Path({str(started)!r}).exists(): break\n"
                "    time.sleep(0.01)\n"
                "else: raise RuntimeError('grandchild did not start')\n"
                "print('X' * 1000, flush=True)\n"
                "time.sleep(5)\n"
            )
            policy = SandboxPolicy(
                schema_version=1, run_id="pidns-output", ticket_id="pidns-output",
                step="code", workspace_root=workspace, read_roots=(workspace,),
                write_roots=(workspace,), deny_read_roots=(), deny_write_roots=(),
                network_mode=NetworkMode.DENY, allowed_domains=(), process_limit=8,
                wall_timeout_seconds=5, output_limit_bytes=64, protected_paths=(),
            )
            sandbox = LandlockSandbox(helper=str(helper))
            result = execute_policy_command(
                sandbox.wrap([sys.executable, "-c", parent], workspace=workspace),
                cwd=workspace, policy=policy, timeout=5,
            )
            self.assertEqual(result.error, "output_limit", result)
            self.assertTrue(result.cleanup_ok, result)
            self.assertEqual(started.read_text(encoding="ascii"), "detached")
            time.sleep(1.4)
            self.assertFalse(survived.exists())

    def test_后台进程继承stdout也不能拖住已结束命令(self) -> None:
        source = Path(__file__).resolve().parents[1] / "native/linux/icode_landlock.c"
        system_python = Path("/usr/bin/python3")
        self.assertTrue(system_python.is_file())
        with temp_workspace() as root:
            helper = root / "icode-landlock"
            subprocess.run(
                [shutil.which("cc") or "cc", "-std=c11", "-O2", "-Wall", "-Wextra",
                 "-Werror", str(source), "-o", str(helper)],
                check=True, capture_output=True, text=True,
            )
            started = root / "stdout-started"
            survived = root / "stdout-survived"
            grandchild = (
                "import os, time\nfrom pathlib import Path\n"
                "os.setsid()\n"
                f"Path({str(started)!r}).write_text('ready')\n"
                "time.sleep(1.2)\n"
                f"Path({str(survived)!r}).write_text('escaped')\n"
            )
            parent = (
                "import subprocess, sys, time\nfrom pathlib import Path\n"
                f"subprocess.Popen([sys.executable, '-c', {grandchild!r}])\n"
                f"for _ in range(200):\n    if Path({str(started)!r}).exists(): break\n"
                "    time.sleep(0.01)\n"
                "else: raise RuntimeError('grandchild did not start')\n"
                "print('command-exited', flush=True)\n"
            )
            outcome = subprocess.run(
                [str(helper), "--workspace", str(root), "--parent-pid", str(os.getpid()),
                 "--", str(system_python), "-c", parent],
                capture_output=True, text=True, timeout=3, check=False,
            )
            self.assertEqual(outcome.returncode, 0, outcome.stderr)
            self.assertIn("command-exited", outcome.stdout)
            self.assertTrue(started.exists())
            time.sleep(1.4)
            self.assertFalse(survived.exists())

    def test_受限命令不是PID1且不能干扰可信监督者(self) -> None:
        source = Path(__file__).resolve().parents[1] / "native/linux/icode_landlock.c"
        system_python = Path("/usr/bin/python3")
        self.assertTrue(system_python.is_file())
        with temp_workspace() as root:
            helper = root / "icode-landlock"
            subprocess.run(
                [shutil.which("cc") or "cc", "-std=c11", "-O2", "-Wall", "-Wextra",
                 "-Werror", str(source), "-o", str(helper)],
                check=True, capture_output=True, text=True,
            )
            code = (
                "import ctypes, os, signal\n"
                "assert os.getpid() == 2 and os.getppid() == 1, "
                "(os.getpid(), os.getppid())\n"
                "libc = ctypes.CDLL(None, use_errno=True)\n"
                "class H(ctypes.Structure):\n"
                "    _fields_ = [('version', ctypes.c_uint32), ('pid', ctypes.c_int)]\n"
                "class D(ctypes.Structure):\n"
                "    _fields_ = [('effective', ctypes.c_uint32), "
                "('permitted', ctypes.c_uint32), ('inheritable', ctypes.c_uint32)]\n"
                "caps = (D * 2)()\n"
                "assert libc.capget(ctypes.byref(H(0x20080522, 0)), ctypes.byref(caps)) == 0\n"
                "assert all(not (c.effective or c.permitted or c.inheritable) for c in caps)\n"
                "assert libc.prctl(39, 0, 0, 0, 0) == 1\n"  # PR_GET_NO_NEW_PRIVS
                "assert libc.ptrace(16, 1, 0, 0) == -1\n"  # PTRACE_ATTACH
                "assert ctypes.get_errno() == 1\n"
                "class IOVec(ctypes.Structure):\n"
                "    _fields_ = [('base', ctypes.c_void_p), ('length', ctypes.c_size_t)]\n"
                "buffer = ctypes.create_string_buffer(1)\n"
                "local = IOVec(ctypes.cast(buffer, ctypes.c_void_p), 1)\n"
                "remote = IOVec(1, 1)\n"
                "ctypes.set_errno(0)\n"
                "assert libc.process_vm_readv(1, ctypes.byref(local), 1, "
                "ctypes.byref(remote), 1, 0) == -1\n"
                "assert ctypes.get_errno() == 1\n"
                "ctypes.set_errno(0)\n"
                "assert libc.process_vm_writev(1, ctypes.byref(local), 1, "
                "ctypes.byref(remote), 1, 0) == -1\n"
                "assert ctypes.get_errno() == 1\n"
                "os.kill(1, signal.SIGKILL)\n"  # 子 PID namespace 无权杀 PID 1
                "print('supervisor-intact', flush=True)\n"
            )
            result = subprocess.run(
                [str(helper), "--workspace", str(root), "--parent-pid", str(os.getpid()),
                 "--", str(system_python), "-c", code],
                capture_output=True, text=True, timeout=4, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("supervisor-intact", result.stdout)

    def test_宿主强杀后主动脱组的多层后代不能残留(self) -> None:
        source = Path(__file__).resolve().parents[1] / "native/linux/icode_landlock.c"
        with temp_workspace() as root:
            helper = root / "icode-landlock"
            subprocess.run(
                [shutil.which("cc") or "cc", "-std=c11", "-O2", "-Wall", "-Wextra",
                 "-Werror", str(source), "-o", str(helper)],
                check=True, capture_output=True, text=True,
            )
            import hashlib

            manifest = root / "icode-landlock.sha256"
            manifest.write_text(
                hashlib.sha256(helper.read_bytes()).hexdigest() + "\n",
                encoding="ascii",
            )
            result = probe_linux_process_tree_cleanup(
                LandlockSandbox(helper=str(helper), manifest=str(manifest))
            )

        self.assertTrue(result.executed, result.detail)
        self.assertTrue(result.passed, result.detail)
        self.assertEqual(
            result.checks,
            {
                "descendant_started": True,
                "descendant_detached": True,
                "descendant_alive_before_host_kill": True,
                "host_killed": True,
                "descendant_exited": True,
                "no_delayed_write": True,
            },
        )

    def test_后代退出FD在宿主被杀前就绪时拒绝错误归因(self) -> None:
        source = Path(__file__).resolve().parents[1] / "native/linux/icode_landlock.c"
        with temp_workspace() as root:
            helper = root / "icode-landlock"
            subprocess.run(
                [shutil.which("cc") or "cc", "-std=c11", "-O2", "-Wall", "-Wextra",
                 "-Werror", str(source), "-o", str(helper)],
                check=True, capture_output=True, text=True,
            )
            import hashlib

            manifest = root / "icode-landlock.sha256"
            manifest.write_text(
                hashlib.sha256(helper.read_bytes()).hexdigest() + "\n",
                encoding="ascii",
            )
            sandbox = LandlockSandbox(helper=str(helper), manifest=str(manifest))
            read_fd, write_fd = os.pipe()
            os.close(write_fd)
            try:
                # Pipe HUP 作为已就绪 FD 替身，锁住探针对任何退出事件的拒绝路径。
                with mock.patch(
                    "icode.isolation._open_verified_descendant_pidfd",
                    return_value=os.dup(read_fd),
                ):
                    result = probe_linux_process_tree_cleanup(sandbox)
            finally:
                os.close(read_fd)

        self.assertTrue(result.executed, result.detail)
        self.assertFalse(result.passed, result.detail)
        self.assertEqual(result.detail, "descendant_exited_before_host_kill")
        self.assertTrue(result.checks["descendant_started"])
        self.assertTrue(result.checks["descendant_detached"])
        self.assertFalse(result.checks["descendant_alive_before_host_kill"])
        self.assertFalse(result.checks["host_killed"])


if __name__ == "__main__":
    unittest.main()
