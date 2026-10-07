"""Installed-wheel lease validation stays isolated from product networking."""

from contextlib import redirect_stdout
import importlib.util
import inspect
import socket
from io import StringIO
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from scripts import run_native_wheel_ci


class TestInstalledLinuxLeaseProbe(unittest.TestCase):
    def _module(self):
        path = Path(__file__).resolve().parents[1] / "scripts/probe_installed_linux_lease.py"
        self.assertTrue(path.is_file(), "installed wheel lease probe is missing")
        spec = importlib.util.spec_from_file_location("installed_lease_probe", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_wheel_runner_calls_isolated_lease_probe_after_install(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "scripts/run_native_wheel_ci.py").read_text()
        self.assertIn('"probe installed wheel network lease expiry"', source)
        self.assertIn('"probe_installed_linux_lease.py"', source)
        stage = source.split('"probe installed wheel network lease expiry"', 1)[1].split("\n            )", 1)[0]
        self.assertIn('str(python), "-I"', stage)
        self.assertIn("allow_environment_skip=True", stage)
        self.assertLess(source.index('_run("install wheel"'), source.index('"probe installed wheel network lease expiry"'))

    def test_probe_errors_do_not_expose_raw_details(self) -> None:
        module = self._module()
        for fault in (module.ProbeFailure("fixed_probe_failure"), OSError("PRIVATE_IO_DETAIL")):
            with self.subTest(kind=type(fault).__name__):
                output = StringIO()
                with mock.patch.object(module, "_probe", side_effect=fault), redirect_stdout(output):
                    self.assertEqual(module.main(), 1)
                self.assertNotIn("PRIVATE_IO_DETAIL", output.getvalue())
                self.assertNotIn("Traceback", output.getvalue())
                self.assertIn("::error::", output.getvalue())

    def test_environment_skip_has_distinct_exit_and_never_claims_pass(self) -> None:
        module = self._module()
        output = StringIO()
        with mock.patch.object(module, "_probe", side_effect=module.ProbeSkipped("namespace_unavailable")), redirect_stdout(output):
            self.assertEqual(module.main(), 77)
        self.assertIn("SKIP", output.getvalue())
        self.assertNotIn("PASS", output.getvalue())
        self.assertIn("conformance_credit=none", output.getvalue())

    def test_wheel_runner_accepts_environment_skip_only_when_explicit(self) -> None:
        self.assertIn("allow_environment_skip", inspect.signature(run_native_wheel_ci._run).parameters)
        skipped = subprocess.CompletedProcess(["probe"], 77, "PRIVATE_STDOUT", "PRIVATE_STDERR")
        output = StringIO()
        with mock.patch.object(run_native_wheel_ci.subprocess, "run", return_value=skipped), redirect_stdout(output):
            run_native_wheel_ci._run("lease probe", ["probe"], cwd=Path("/"), allow_environment_skip=True)
        self.assertIn("SKIP", output.getvalue())
        self.assertNotIn("PASS", output.getvalue())
        self.assertNotIn("PRIVATE_", output.getvalue())
        with mock.patch.object(run_native_wheel_ci.subprocess, "run", return_value=skipped):
            with self.assertRaises(RuntimeError):
                run_native_wheel_ci._run("lease probe", ["probe"], cwd=Path("/"))

    def test_runtime_cleanup_exception_cannot_skip_real_socket_close(self) -> None:
        module = self._module()
        cleanup = getattr(module, "_cleanup_resources", None)
        self.assertTrue(callable(cleanup), "each owned resource needs independent cleanup")
        runtime = mock.Mock()
        runtime.close.side_effect = [OSError("PRIVATE_CLOSE_DETAIL"), True]
        with socket.socket() as peer:
            self.assertFalse(cleanup(runtime, [peer], None, 0))
            self.assertEqual(peer.fileno(), -1)

    def test_namespace_skip_requires_known_denial_and_absent_payload_marker(self) -> None:
        module = self._module()
        cases = (
            (78, "unshare user/pid/network namespace: Operation not permitted", False, module.ProbeSkipped),
            (78, "unexpected helper failure", False, module.ProbeFailure),
            (78, "unshare user/pid/network namespace: Operation not permitted", True, module.ProbeFailure),
            (0, "", False, module.ProbeFailure),
        )
        for code, stderr, marker_present, expected in cases:
            with self.subTest(code=code, marker=marker_present, expected=expected.__name__):
                with tempfile.TemporaryDirectory() as raw:
                    workspace = Path(raw)
                    if marker_present:
                        (workspace / "namespace-ready").touch()
                    sandbox = mock.Mock()
                    sandbox.wrap.return_value = ["helper", "--runtime-read", "venv-prefix", "--", sys.executable]
                    result = subprocess.CompletedProcess([], code, "", stderr)
                    with mock.patch.object(module.os, "readlink", return_value="host-netns"), \
                         mock.patch.object(module.subprocess, "run", return_value=result) as run:
                        with self.assertRaises(expected):
                            module._namespace_preflight(sandbox, workspace, time.monotonic() + 2)
                    command = run.call_args.args[0]
                    self.assertIn("--runtime-read", command)
                    self.assertEqual(command[-1], sys.executable)
                    self.assertLess(command.index("--network-loopback-only"), command.index("--"))
                    self.assertEqual(sandbox.wrap.call_args.args[0][0], sys.executable)

    def test_worker_program_is_valid_and_does_not_half_close_ttl_tunnel(self) -> None:
        module = self._module()
        source = module._worker_source(12345, 999999)
        compile(source, "installed-lease-worker", "exec")
        self.assertNotIn("shutdown", source)
        self.assertIn("time.monotonic_ns() >= 999999", source)
        self.assertIn("urllib.request.urlopen", source)
        self.assertIn("errno.EPERM", source)
        self.assertIn("errno.ECONNREFUSED", source)

    def test_fixed_canary_reads_tolerate_one_byte_fragments(self) -> None:
        module = self._module()
        read_exact = getattr(module, "_read_exact", None)
        self.assertTrue(callable(read_exact), "TCP recv must not assume a complete message")
        peer = mock.Mock()
        peer.recv.side_effect = [b"a", b"b", b"c"]
        self.assertEqual(read_exact(peer, 3, time.monotonic() + 1), b"abc")
        self.assertEqual([call.args[0] for call in peer.recv.call_args_list], [3, 2, 1])

    def test_fixed_canary_reads_reject_early_eof_and_expired_deadline(self) -> None:
        module = self._module()
        read_exact = getattr(module, "_read_exact", None)
        self.assertTrue(callable(read_exact), "short EOF must fail closed")
        peer = mock.Mock()
        peer.recv.side_effect = [b"a", b""]
        with self.assertRaises(module.ProbeFailure):
            read_exact(peer, 3, time.monotonic() + 1)
        peer.reset_mock()
        with self.assertRaises(module.ProbeFailure):
            read_exact(peer, 3, time.monotonic() - 1)
        peer.recv.assert_not_called()

    def test_cleanup_interrupt_propagates_only_after_real_socket_close(self) -> None:
        module = self._module()
        cleanup = getattr(module, "_cleanup_resources", None)
        self.assertTrue(callable(cleanup), "interrupt must not skip later cleanup")
        runtime = mock.Mock()
        fault = KeyboardInterrupt()
        runtime.close.side_effect = [fault, True]
        with socket.socket() as peer:
            with self.assertRaises(KeyboardInterrupt) as caught:
                cleanup(runtime, [peer], None, 0)
            self.assertIs(caught.exception, fault)
            self.assertEqual(peer.fileno(), -1)
