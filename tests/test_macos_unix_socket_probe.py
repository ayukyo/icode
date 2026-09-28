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


if __name__ == "__main__":
    unittest.main()
