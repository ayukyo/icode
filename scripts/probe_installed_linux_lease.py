"""Offline lease E2E for an installed Linux wheel, never a product self-test.

The sole DNS substitute is scoped to this isolated validation interpreter. It
routes one fixed hostname to a local canary; it must never run inside doctor,
the workbench, or an interpreter serving other tasks. No execution is enabled.
"""

from __future__ import annotations

import errno
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
from unittest import mock

_DOMAIN = "packages.example"
_TTL_SECONDS = 5
_TOTAL_TIMEOUT_SECONDS = 35
_COMMAND_TIMEOUT_SECONDS = 15


class ProbeFailure(RuntimeError):
    """A fixed, path-free failure classification."""


class ProbeSkipped(RuntimeError):
    """Known namespace/loopback denial, without readiness credit."""


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ProbeFailure(code)


def _remaining(deadline: float, cap: float) -> float:
    remaining = min(cap, deadline - time.monotonic())
    _require(remaining > 0, "probe_deadline_exceeded")
    return remaining


def _open_fds() -> set[int]:
    descriptors = set()
    for value in os.listdir("/proc/self/fd"):
        descriptor = int(value)
        try:
            os.fstat(descriptor)
        except OSError as error:
            if error.errno == errno.EBADF:
                continue  # The directory enumeration FD is already closed.
            raise
        descriptors.add(descriptor)
    return descriptors


def _read_exact(peer: socket.socket, size: int, deadline: float) -> bytes:
    received = bytearray()
    while len(received) < size:
        peer.settimeout(_remaining(deadline, 10))
        chunk = peer.recv(size - len(received))
        _require(bool(chunk), "canary_read_incomplete")
        received.extend(chunk)
    return bytes(received)


def _namespace_preflight(sandbox: object, workspace: Path, deadline: float) -> None:
    marker = workspace / "namespace-ready"
    namespace = os.readlink("/proc/self/ns/net")
    source = (
        "import os, socket; from pathlib import Path\n"
        f"assert os.readlink('/proc/self/ns/net') != {namespace!r}\n"
        "listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
        "listener.bind(('127.0.0.1', 0)); listener.listen(1); listener.close()\n"
        f"Path({str(marker)!r}).touch()\n"
    )
    command = sandbox.wrap([sys.executable, "-B", "-c", source], workspace=workspace)
    command.insert(command.index("--"), "--network-loopback-only")
    result = subprocess.run(
        command, cwd=workspace, stdin=subprocess.DEVNULL,
        capture_output=True, text=True, timeout=_remaining(deadline, 8), check=False,
    )
    if result.returncode == 0:
        _require(marker.is_file(), "namespace_marker_missing")
        return
    known_denial = any(text in result.stderr for text in (
        "unshare user/pid/network namespace: Operation not permitted",
        "unshare user/pid/network namespace: Permission denied",
        f"ICODE_LOOPBACK_SETUP_FAILURE stage=enable errno={errno.EPERM}",
        f"ICODE_LOOPBACK_SETUP_FAILURE stage=enable errno={errno.EACCES}",
    ))
    if known_denial and not marker.exists():
        raise ProbeSkipped("namespace_unavailable")
    raise ProbeFailure("namespace_preflight_failed")


def _worker_source(blocked_port: int, expires_at_ns: int) -> str:
    # Keep the main tunnel fully open: half-close EOF is not TTL evidence.
    return (
        "import errno, os, socket, time, urllib.error, urllib.request\n"
        "try: socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)\n"
        "except OSError as error: assert error.errno == errno.EPERM\n"
        "else: raise AssertionError('new unix socket permitted')\n"
        "host, port = os.environ['ICODE_PROXY_LISTENER'].rsplit(':', 1)\n"
        "proxies = urllib.request.getproxies()\n"
        "assert proxies.get('https') == f'http://{host}:{int(port)}'\n"
        "assert not proxies.get('http') and not proxies.get('all')\n"
        "try: urllib.request.urlopen('https://packages.example/', timeout=2)\n"
        "except (urllib.error.URLError, OSError): pass\n"
        "else: raise AssertionError('fixed TLS alert should end handshake')\n"
        "direct = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
        f"direct.settimeout(2); code = direct.connect_ex(('127.0.0.1', {blocked_port}))\n"
        "direct.close(); assert code == errno.ECONNREFUSED\n"
        "client = socket.create_connection((host, int(port)), timeout=2)\n"
        "client.sendall(b'CONNECT packages.example:443 HTTP/1.1\\r\\nHost: packages.example\\r\\n\\r\\n')\n"
        "response = bytearray()\n"
        "while not response.endswith(b'\\r\\n\\r\\n'):\n"
        "    chunk = client.recv(1); assert chunk; response.extend(chunk)\n"
        "    assert len(response) <= 128\n"
        "assert response == b'HTTP/1.1 200 Connection Established\\r\\n\\r\\n'\n"
        "client.sendall(b'worker-to-host-marker')\n"
        "reply = bytearray(); expected = b'host-to-worker-marker'\n"
        "while len(reply) < len(expected):\n"
        "    chunk = client.recv(len(expected) - len(reply)); assert chunk; reply.extend(chunk)\n"
        "assert reply == expected\n"
        "client.settimeout(10); assert client.recv(1) == b''\n"
        f"assert time.monotonic_ns() >= {expires_at_ns}\n"
        "client.close(); print('lease-expiry-closed-client')\n"
    )


def _cleanup_resources(runtime, sockets, executor, deadline: float) -> bool:
    """Attempt every cleanup, preserving interruptions until after the attempts."""
    operations = []
    if runtime is not None:
        operations.append((runtime.close, True))
    operations.extend((peer.close, False) for peer in sockets)
    if executor is not None and executor.ident is not None:
        operations.append((
            lambda: executor.join(timeout=max(0, min(18, deadline - time.monotonic()))),
            False,
        ))
    if runtime is not None:
        operations.append((runtime.close, True))  # Retry after in-flight work ends.
    ok = True
    pending_interrupt = None
    for operation, require_true in operations:
        try:
            result = operation()
            if require_true and result is not True:
                ok = False
        except Exception:
            ok = False
        except BaseException as interrupt:
            ok = False
            if pending_interrupt is None:
                pending_interrupt = interrupt
    if pending_interrupt is not None:
        raise pending_interrupt
    return ok and (executor is None or not executor.is_alive())


def _probe() -> None:
    _require(sys.platform.startswith("linux"), "unsupported_platform")
    import icode
    from icode.approvals import ScriptedApprover
    from icode.execution_broker import execute_linux_leased_connect_candidate
    from icode.isolation import LandlockSandbox
    from icode.network_destination import ResolvedNetworkTarget
    from icode.network_lease import NetworkLeaseAuthority, NetworkPurpose
    from icode.network_proxy_scope import HostConnectRuntime
    from icode.sandbox_policy import NetworkMode, SandboxPolicy

    package = Path(icode.__file__).resolve()
    checkout = Path(__file__).resolve().parents[1]
    _require("site-packages" in package.parts, "package_not_installed_in_venv")
    _require(not package.is_relative_to(checkout), "package_loaded_from_checkout")
    sandbox = LandlockSandbox.from_bundle()
    _require(sandbox is not None and sandbox.manifest is not None, "installed_helper_unavailable")
    deadline = time.monotonic() + _TOTAL_TIMEOUT_SECONDS
    baseline_fds = _open_fds()
    baseline_threads = set(threading.enumerate())
    with tempfile.TemporaryDirectory(prefix="icode-wheel-lease-") as raw:
        workspace = Path(raw).resolve()
        _namespace_preflight(sandbox, workspace, deadline)
        policy = SandboxPolicy(
            schema_version=1, run_id="wheel-lease", ticket_id="wheel-lease", step="code",
            workspace_root=workspace, read_roots=(workspace,), write_roots=(workspace,),
            deny_read_roots=(), deny_write_roots=(), network_mode=NetworkMode.DENY,
            allowed_domains=(), process_limit=8, wall_timeout_seconds=20,
            output_limit_bytes=4096, protected_paths=(),
        )
        sockets: list[socket.socket] = []
        runtime = None
        executor = None
        outcomes = []
        errors = []
        # This patch is only in the isolated CI process, not in installed code.
        def resolve_canary(hostname, port, resolver=None):
            _require(hostname == _DOMAIN and port == 443, "unexpected_canary_destination")
            return (ResolvedNetworkTarget(
                socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP,
                upstream_listener.getsockname(),
            ),)

        with mock.patch("icode.network_connector.resolve_public_tcp_targets", side_effect=resolve_canary):
            try:
                listeners = []
                for _ in range(2):
                    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sockets.append(listener)
                    listener.bind(("127.0.0.1", 0)); listener.listen(2)
                    listener.settimeout(_remaining(deadline, 10))
                    with socket.create_connection(listener.getsockname(), timeout=_remaining(deadline, 2)) as control:
                        control.sendall(b'host-network-control')
                        peer, _address = listener.accept()
                        with peer:
                            peer.settimeout(_remaining(deadline, 2))
                            _require(
                                _read_exact(peer, len(b'host-network-control'), deadline) == b'host-network-control',
                                "host_positive_control_failed",
                            )
                    listeners.append(listener)
                upstream_listener, blocked_listener = listeners
                authority = NetworkLeaseAuthority()
                runtime = HostConnectRuntime(authority, sweep_interval_seconds=0.01)
                runtime.start()
                issued = authority.request_lease(
                    policy, approver=ScriptedApprover([True]), purpose=NetworkPurpose.PACKAGE_INSTALL,
                    allowed_domains=(_DOMAIN,), ttl_seconds=_TTL_SECONDS,
                )
                scope = runtime.create_scope(issued, policy, NetworkPurpose.PACKAGE_INSTALL)
                source = _worker_source(blocked_listener.getsockname()[1], issued.lease.expires_at_monotonic_ns)

                def execute():
                    try:
                        outcomes.append(execute_linux_leased_connect_candidate(
                            [sys.executable, "-B", "-c", source], cwd=workspace,
                            sandbox=sandbox, policy=policy, scope=scope,
                            timeout=_COMMAND_TIMEOUT_SECONDS,
                        ))
                    except BaseException as error:
                        errors.append(error)

                executor = threading.Thread(target=execute, name="icode-wheel-lease-worker", daemon=True)
                executor.start()
                tls_peer, _address = upstream_listener.accept()
                sockets.append(tls_peer)
                tls_peer.settimeout(_remaining(deadline, 10))
                _require(_read_exact(tls_peer, 2, deadline) == b'\x16\x03', "stdlib_https_proxy_control_failed")
                tls_peer.sendall(b'\x15\x03\x03\x00\x02\x02\x28')
                tls_peer.close()
                upstream, _address = upstream_listener.accept()
                sockets.append(upstream)
                upstream.settimeout(_remaining(deadline, 10))
                received = _read_exact(upstream, len(b'worker-to-host-marker'), deadline)
                _require(received == b'worker-to-host-marker', "upstream_marker_mismatch")
                upstream.sendall(b'host-to-worker-marker')
                _require(upstream.recv(1) == b'', "upstream_not_closed_by_expiry")
                _require(time.monotonic_ns() >= issued.lease.expires_at_monotonic_ns, "upstream_closed_before_expiry")
                executor.join(timeout=_remaining(deadline, 18))
                _require(not executor.is_alive() and not errors and len(outcomes) == 1, "executor_incomplete")
                result = outcomes[0]
                _require(result.error is None and result.exit_code == 0 and result.cleanup_ok, "candidate_failed")
                _require(result.output.strip() == 'lease-expiry-closed-client', "worker_expiry_evidence_missing")
                for listener in listeners:
                    listener.settimeout(_remaining(deadline, 0.1))
                    try:
                        unexpected, _address = listener.accept()
                    except socket.timeout:
                        continue
                    unexpected.close()
                    raise ProbeFailure("worker_reached_host_listener_directly")

                # Fresh, open scope: rejection must not be explained by the
                # previous candidate having already closed its own scope.
                expired = authority.request_lease(
                    policy, approver=ScriptedApprover([True]), purpose=NetworkPurpose.PACKAGE_INSTALL,
                    allowed_domains=(_DOMAIN,), ttl_seconds=1,
                    now_monotonic_ns=time.monotonic_ns() - 2_000_000_000,
                )
                expired_scope = runtime.create_scope(expired, policy, NetworkPurpose.PACKAGE_INSTALL)
                _require(expired_scope._closed is False, "expired_scope_already_closed")
                _require(time.monotonic_ns() >= expired.lease.expires_at_monotonic_ns, "expired_lease_not_yet_expired")
                marker = workspace / "expired-payload"
                refused = execute_linux_leased_connect_candidate(
                    [sys.executable, "-B", "-c", f"from pathlib import Path; Path({str(marker)!r}).touch()"],
                    cwd=workspace, sandbox=sandbox, policy=policy, scope=expired_scope,
                    timeout=_remaining(deadline, 3),
                )
                _require(refused.error == "proxy_setup_failed" and refused.cleanup_ok, "expired_scope_not_refused")
                _require(not marker.exists(), "expired_payload_started")
            finally:
                _require(
                    _cleanup_resources(runtime, sockets, executor, deadline),
                    "probe_cleanup_unconfirmed",
                )
    _require(_open_fds() == baseline_fds, "probe_descriptor_leak")
    _require(set(threading.enumerate()) <= baseline_threads, "probe_thread_leak")


def main() -> int:
    try:
        _probe()
    except ProbeSkipped:
        print("::warning::installed lease probe: SKIP namespace_unavailable conformance_credit=none")
        return 77
    except ProbeFailure as error:
        print(f"::error::installed lease probe: {error}")
        return 1
    except Exception:
        print("::error::installed lease probe: unexpected_probe_failure")
        return 1
    print("installed lease probe: PASS conformance_credit=none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
