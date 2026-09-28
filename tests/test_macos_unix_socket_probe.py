"""Test-only native probe for path-scoped macOS AF_UNIX policy."""

from __future__ import annotations

from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest

from tests import macos_unix_socket_probe as probe
from icode.isolation import MacSeatbeltSandbox


class TestUnixSocketPolicyBuilder(unittest.TestCase):
    def test_curl_socks5_uds_support_requires_version_and_build_feature(self) -> None:
        supports = getattr(probe, "supports_curl_socks5_uds", None)
        self.assertTrue(callable(supports), "curl SOCKS-over-UDS capability check is missing")

        self.assertTrue(supports(
            "curl 7.84.0 (x86_64-apple-darwin)\n"
            "Features: HTTPS-proxy UnixSockets\n",
        ))
        self.assertFalse(supports(
            "curl 7.83.1 (x86_64-apple-darwin)\n"
            "Features: HTTPS-proxy UnixSockets\n",
        ))
        self.assertFalse(supports(
            "curl 8.0.0 (x86_64-apple-darwin)\n"
            "Features: HTTPS-proxy\n",
        ))
        self.assertFalse(supports("not a curl version report\n"))

    def test_curl_socks5_uds_proxy_url_quotes_and_bounds_socket_path(self) -> None:
        build_url = getattr(probe, "curl_socks5_uds_proxy_url", None)
        self.assertTrue(callable(build_url), "curl SOCKS-over-UDS URL builder is missing")
        self.assertEqual(
            build_url(Path("/private/tmp/proxy root.sock")),
            "socks5h://localhost/private/tmp/proxy%20root.sock",
        )
        for invalid_path in (
            Path("relative/proxy.sock"),
            Path("/private/../tmp/proxy.sock"),
            Path("/private/tmp/proxy\n.sock"),
            Path("/" + "a" * 104),
        ):
            with self.subTest(path=str(invalid_path)):
                with self.assertRaises(ValueError):
                    build_url(invalid_path)

    def test_test_only_socks5_uds_canary_allows_only_approved_domain(self) -> None:
        canary_type = getattr(probe, "Socks5UdsCanary", None)
        self.assertTrue(callable(canary_type), "test-only SOCKS5 UDS canary is missing")

        with tempfile.TemporaryDirectory(prefix="icode-socks5-uds-") as raw_root:
            socket_path = Path(raw_root) / "proxy.sock"
            with canary_type(
                socket_path,
                approved_target=("approved.example", 45678),
                blocked_target=("blocked.example", 45678),
            ) as canary:
                approved_reply = self._socks5_canary_request(
                    socket_path, "approved.example", 45678,
                )
                blocked_reply = self._socks5_canary_request(
                    socket_path, "blocked.example", 45678,
                )

            self.assertEqual(approved_reply[0], 0)
            self.assertIn(b"icode-socks5-uds-canary", approved_reply[1])
            self.assertEqual(blocked_reply[0], 2)
            self.assertEqual(blocked_reply[1], b"")
            self.assertEqual(
                canary.observed_targets,
                [("approved.example", 45678), ("blocked.example", 45678)],
            )

    @staticmethod
    def _recv_exact(client: socket.socket, size: int) -> bytes:
        result = bytearray()
        while len(result) < size:
            chunk = client.recv(size - len(result))
            if not chunk:
                raise AssertionError("test canary closed a short SOCKS5 reply")
            result.extend(chunk)
        return bytes(result)

    @staticmethod
    def _socks5_canary_request(
        socket_path: Path, hostname: str, port: int,
    ) -> tuple[int, bytes]:
        domain = hostname.encode("ascii")
        request = (
            b"\x05\x01\x00\x03" + bytes((len(domain),)) + domain
            + port.to_bytes(2, "big")
        )
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(2)
            client.connect(str(socket_path))
            client.sendall(b"\x05\x01\x00")
            if TestUnixSocketPolicyBuilder._recv_exact(client, 2) != b"\x05\x00":
                raise AssertionError("test canary rejected no-auth SOCKS5 negotiation")
            client.sendall(request)
            reply_head = TestUnixSocketPolicyBuilder._recv_exact(client, 4)
            if reply_head[0] != 5 or reply_head[2] != 0:
                raise AssertionError("test canary returned a malformed SOCKS5 reply")
            address_length = {1: 4, 4: 16}.get(reply_head[3])
            if reply_head[3] == 3:
                address_length_byte = TestUnixSocketPolicyBuilder._recv_exact(client, 1)
                address_length = address_length_byte[0]
            if address_length is None:
                raise AssertionError("test canary returned an unknown SOCKS5 address type")
            remaining = address_length + 2
            TestUnixSocketPolicyBuilder._recv_exact(client, remaining)
            if reply_head[1] != 0:
                return reply_head[1], b""

            client.sendall(
                b"GET /canary HTTP/1.1\r\nHost: approved.example\r\n"
                b"Connection: close\r\n\r\n"
            )
            response = bytearray()
            while len(response) <= 4096:
                chunk = client.recv(min(512, 4097 - len(response)))
                if not chunk:
                    break
                response.extend(chunk)
            return reply_head[1], bytes(response)

    def test_policy_grants_only_outbound_unix_socket_beneath_approved_root(self) -> None:
        builder = getattr(probe, "build_test_profile", None)
        self.assertTrue(callable(builder), "test-only Seatbelt profile builder is missing")

        base = "(version 1)(deny default)"
        approved = Path("/private/tmp/approved sockets")
        profile = builder(base, approved)

        self.assertTrue(profile.startswith(base))
        self.assertIn(
            '(allow file-read-metadata file-test-existence '
            '(subpath "/private/tmp/approved sockets"))',
            profile,
        )
        self.assertIn("(allow system-socket (socket-domain AF_UNIX))", profile)
        self.assertIn(
            '(allow network-outbound (remote unix-socket '
            '(subpath "/private/tmp/approved sockets")))',
            profile,
        )
        self.assertNotIn("network-bind", profile)
        self.assertNotIn('(allow network*)', profile)
        self.assertNotIn('(allow network-outbound (remote ip', profile)

    def test_policy_builder_rejects_relative_and_control_character_paths(self) -> None:
        builder = getattr(probe, "build_test_profile", None)
        self.assertTrue(callable(builder), "test-only Seatbelt profile builder is missing")

        with self.assertRaises(ValueError):
            builder("(version 1)(deny default)", Path("relative/socket-root"))
        with self.assertRaises(ValueError):
            builder("(version 1)(deny default)", Path("/private/tmp/bad\nroot"))

    def test_policy_builder_quotes_sbpl_path_literals(self) -> None:
        builder = getattr(probe, "build_test_profile", None)
        self.assertTrue(callable(builder), "test-only Seatbelt profile builder is missing")

        profile = builder(
            "(version 1)(deny default)",
            Path('/private/tmp/a "quoted" root'),
        )
        self.assertIn('/private/tmp/a \\"quoted\\" root', profile)


@unittest.skipUnless(sys.platform == "darwin", "requires native macOS Seatbelt")
class TestNativeUnixSocketPolicy(unittest.TestCase):
    @staticmethod
    def _run_probe(
        sandbox_exec: str, profile: str, cwd: Path, source: str,
        *arguments: str,
    ) -> str:
        try:
            result = subprocess.run(
                [sandbox_exec, "-p", profile, sys.executable, "-S", "-c", source,
                 *arguments],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=6,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise AssertionError("sandboxed socket probe exceeded its deadline") from None
        except OSError:
            raise AssertionError("could not start sandboxed socket probe") from None
        if result.returncode != 0:
            raise AssertionError("sandboxed socket probe did not exit cleanly")
        markers = [line for line in result.stdout.splitlines() if line.startswith("probe:")]
        if len(markers) != 1:
            raise AssertionError("sandboxed socket probe returned an invalid marker")
        return markers[0]

    @staticmethod
    def _run_sandboxed_curl(
        sandbox_exec: str,
        profile: str,
        curl_path: str,
        cwd: Path,
        environment: dict[str, str],
        url: str,
    ) -> tuple[int, bytes]:
        try:
            result = subprocess.run(
                [
                    sandbox_exec, "-p", profile, curl_path, "-q", "--fail",
                    "--silent", "--show-error", "--max-time", "4",
                    "--noproxy", "", "--output", "-", url,
                ],
                cwd=cwd,
                env=environment,
                capture_output=True,
                timeout=8,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise AssertionError("sandboxed curl canary exceeded its deadline") from None
        except OSError:
            raise AssertionError("could not start sandboxed curl canary") from None
        return result.returncode, result.stdout

    def test_path_scoped_unix_proxy_works_while_other_sockets_remain_denied(self) -> None:
        sandbox_exec = shutil.which("sandbox-exec") or "/usr/bin/sandbox-exec"
        if not Path(sandbox_exec).is_file():
            self.skipTest("sandbox-exec is unavailable")

        with tempfile.TemporaryDirectory(
            prefix="icode-seatbelt-unix-probe-", dir="/private/tmp",
        ) as raw_root:
            root = Path(raw_root)
            workspace = root / "workspace"
            approved_root = root / "proxy"
            other_root = workspace / "other"
            workspace.mkdir()
            approved_root.mkdir(parents=True)
            other_root.mkdir()
            allowed_path = approved_root / "proxy.sock"
            denied_path = other_root / "other.sock"

            sandbox = MacSeatbeltSandbox(sandbox_exec=sandbox_exec)
            base_profile = sandbox._profile(workspace, False)
            profile = probe.build_test_profile(base_profile, approved_root)
            allowed_source = (
                "import errno, socket, sys\n"
                "client = None\n"
                "try:\n"
                "    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)\n"
                "    client.settimeout(2)\n"
                "    client.connect(sys.argv[1])\n"
                "    client.sendall(b'icode-unix-probe')\n"
                "    print('probe:connected')\n"
                "except OSError as exc:\n"
                "    print('probe:denied' if exc.errno in (errno.EPERM, errno.EACCES) "
                "else 'probe:unexpected')\n"
                "finally:\n"
                "    if client is not None: client.close()\n"
            )
            unlink_source = (
                "import errno, os, sys\n"
                "try:\n"
                "    os.unlink(sys.argv[1])\n"
                "except OSError as exc:\n"
                "    print('probe:denied' if exc.errno in (errno.EPERM, errno.EACCES) "
                "else 'probe:unexpected')\n"
                "else:\n"
                "    print('probe:unlinked')\n"
            )
            tcp_source = (
                "import errno, socket, sys\n"
                "client = None\n"
                "try:\n"
                "    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
                "    client.settimeout(2)\n"
                "    client.connect(('127.0.0.1', int(sys.argv[1])))\n"
                "    print('probe:connected')\n"
                "except OSError as exc:\n"
                "    print('probe:denied' if exc.errno in (errno.EPERM, errno.EACCES) "
                "else 'probe:unexpected')\n"
                "finally:\n"
                "    if client is not None: client.close()\n"
            )

            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as allowed_listener:
                allowed_listener.bind(str(allowed_path))
                allowed_listener.listen(1)
                allowed_listener.settimeout(2)
                allowed_result = self._run_probe(
                    sandbox_exec, profile, workspace, allowed_source,
                    str(allowed_path),
                )
                self.assertEqual(allowed_result, "probe:connected")
                connection, _ = allowed_listener.accept()
                with connection:
                    connection.settimeout(1)
                    received = bytearray()
                    while len(received) < len(b"icode-unix-probe"):
                        chunk = connection.recv(len(b"icode-unix-probe") - len(received))
                        if not chunk:
                            break
                        received.extend(chunk)
                    self.assertEqual(bytes(received), b"icode-unix-probe")
                unlink_result = self._run_probe(
                    sandbox_exec, profile, workspace, unlink_source,
                    str(allowed_path),
                )
                self.assertEqual(unlink_result, "probe:denied")
                self.assertTrue(allowed_path.exists())

            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as denied_listener:
                denied_listener.bind(str(denied_path))
                denied_listener.listen(1)
                denied_listener.settimeout(0.25)
                denied_result = self._run_probe(
                    sandbox_exec, profile, workspace, allowed_source,
                    str(denied_path),
                )
                self.assertEqual(denied_result, "probe:denied")
                with self.assertRaises(socket.timeout):
                    denied_listener.accept()

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_listener:
                tcp_listener.bind(("127.0.0.1", 0))
                tcp_listener.listen(1)
                tcp_listener.settimeout(0.25)
                tcp_result = self._run_probe(
                    sandbox_exec, profile, workspace, tcp_source,
                    str(tcp_listener.getsockname()[1]),
                )
                self.assertEqual(tcp_result, "probe:denied")
                with self.assertRaises(socket.timeout):
                    tcp_listener.accept()

        print(
            "::notice::macos-seatbelt-unix-socket "
            "approved_unix=connected_payload_verified=yes "
            "other_unix=denied tcp_loopback=denied conformance_credit=none",
            flush=True,
        )

    def test_sandboxed_curl_uses_all_proxy_with_path_scoped_socks5_uds(self) -> None:
        sandbox_exec = shutil.which("sandbox-exec") or "/usr/bin/sandbox-exec"
        curl_path = shutil.which("curl")
        if not Path(sandbox_exec).is_file() or curl_path is None:
            print(
                "::warning::macos-seatbelt-curl-socks-uds "
                "supported=no reason=client_or_sandbox_exec_missing conformance_credit=none",
                flush=True,
            )
            self.skipTest("curl or sandbox-exec is unavailable; no conformance credit")
        try:
            version_result = subprocess.run(
                [curl_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            print(
                "::warning::macos-seatbelt-curl-socks-uds "
                "supported=no reason=version_probe_failed conformance_credit=none",
                flush=True,
            )
            self.skipTest("curl version probe failed; no conformance credit")
        if version_result.returncode != 0 or not probe.supports_curl_socks5_uds(
            version_result.stdout,
        ):
            print(
                "::warning::macos-seatbelt-curl-socks-uds "
                "supported=no reason=version_or_unix_sockets_feature_missing "
                "conformance_credit=none",
                flush=True,
            )
            self.skipTest("curl lacks SOCKS5 UDS support; no conformance credit")

        sandbox = MacSeatbeltSandbox(sandbox_exec=sandbox_exec)
        with tempfile.TemporaryDirectory(
            prefix="icode-seatbelt-curl-socks-", dir="/private/tmp",
        ) as raw_root:
            root = Path(raw_root)
            workspace = root / "workspace"
            approved_root = root / "proxy"
            workspace.mkdir()
            approved_root.mkdir()
            socket_path = approved_root / "socks.sock"
            proxy_url = probe.curl_socks5_uds_proxy_url(socket_path)
            profile = probe.build_test_profile(
                sandbox._profile(workspace, False), approved_root,
            )
            environment = {
                "PATH": "/usr/bin:/bin",
                "HOME": str(workspace),
                "LC_ALL": "C",
                "ALL_PROXY": proxy_url,
                "NO_PROXY": "",
                "no_proxy": "",
            }
            allowed_url = "http://approved.example:45678/canary"
            blocked_url = "http://blocked.example:45678/canary"
            with probe.Socks5UdsCanary(
                socket_path,
                approved_target=("approved.example", 45678),
                blocked_target=("blocked.example", 45678),
            ) as canary:
                allowed_status, allowed_body = self._run_sandboxed_curl(
                    sandbox_exec, profile, curl_path, workspace,
                    environment, allowed_url,
                )
                blocked_status, blocked_body = self._run_sandboxed_curl(
                    sandbox_exec, profile, curl_path, workspace,
                    environment, blocked_url,
                )

            self.assertEqual(allowed_status, 0)
            self.assertEqual(allowed_body, probe.Socks5UdsCanary._CANARY_BODY)
            self.assertNotEqual(blocked_status, 0)
            self.assertEqual(blocked_body, b"")
            self.assertEqual(
                canary.observed_targets,
                [("approved.example", 45678), ("blocked.example", 45678)],
            )
            self.assertEqual(canary.failures, [])

        print(
            "::notice::macos-seatbelt-curl-socks-uds "
            "curl_supported=yes socks5h_domain_preserved=yes "
            "approved_canary=yes blocked_target=denied conformance_credit=none",
            flush=True,
        )


if __name__ == "__main__":
    unittest.main()
