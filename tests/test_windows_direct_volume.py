"""Portable canary contracts; mocks are not native Windows evidence."""

from __future__ import annotations

import importlib.util
import ctypes
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts.run_windows_wheel_ci import _synthetic_pe


class TestWindowsDirectVolume(unittest.TestCase):
    def _api(self):
        spec = importlib.util.find_spec("scripts.probe_windows_direct_volume")
        self.assertIsNotNone(spec, "direct-volume CI probe is missing")
        from scripts import probe_windows_direct_volume
        return probe_windows_direct_volume

    def test_exact_volume_prefix_and_unicode_are_preserved(self):
        api = self._api()
        for tail in ("native\\icode-provenance-windows-x64.exe", "用户\\🧪\\native"):
            source = "\\Device\\HarddiskVolume12\\" + tail
            self.assertEqual(api._nt_to_globalroot(source), "\\\\?\\GLOBALROOT" + source)

    def test_wrong_namespace_or_ambiguous_component_is_not_a_volume_path(self):
        api = self._api()
        for path in (
            "C:\\native\\a.exe", "\\Device\\HarddiskVolume\\a.exe",
            "\\Device\\HarddiskVolume１２\\a.exe", "\\Device\\Harddisk0\\a.exe",
            "\\Device\\HarddiskVolume1\\..\\a.exe", "\\Device\\HarddiskVolume1\\a:stream",
            "\\Device\\HarddiskVolume1\\a.\\b", "\\Device\\HarddiskVolume1\\a ",
            "\\Device\\HarddiskVolume1\\a\\\\b", "\\Device\\HarddiskVolume1\\a\x00",
            "\\Device\\HarddiskVolume1\\", "\\Device\\HarddiskVolume1\\.\\a",
            "\\Device\\HarddiskVolume1\\a/b", "\\Device\\Mup\\server\\a",
            None, True, 1, b"\\Device\\HarddiskVolume1\\a",
        ):
            with self.subTest(path=path), self.assertRaises(ValueError):
                api._nt_to_globalroot(path)

    def _kernel_fixture(self, value="\\Device\\HarddiskVolume1\\用户\\🧪\\native"):
        def query(handle, buffer, capacity, flags):
            buffer.value = value
            return len(value.encode("utf-16-le")) // 2
        return SimpleNamespace(CreateFileW=Mock(return_value=123),
            GetFinalPathNameByHandleW=Mock(side_effect=query), CloseHandle=Mock(return_value=1))

    def test_kernel_api_widths_and_signatures_are_explicit(self):
        api = self._api()
        kernel = self._kernel_fixture()
        with patch.object(api.ctypes, "WinDLL", create=True, return_value=kernel) as dll:
            self.assertIs(api._kernel(), kernel)
        dll.assert_called_once_with("kernel32", use_last_error=True)
        self.assertEqual(ctypes.sizeof(kernel.CreateFileW.argtypes[1]), 4)
        self.assertEqual(ctypes.sizeof(kernel.CreateFileW.argtypes[2]), 4)
        self.assertEqual(ctypes.sizeof(kernel.CreateFileW.restype), ctypes.sizeof(ctypes.c_void_p))
        self.assertEqual(ctypes.sizeof(kernel.GetFinalPathNameByHandleW.restype), 4)
        self.assertEqual(ctypes.sizeof(kernel.CloseHandle.restype), 4)
        self.assertEqual(len(kernel.CreateFileW.argtypes), 7)
        self.assertEqual(len(kernel.GetFinalPathNameByHandleW.argtypes), 4)

    def test_metadata_open_flags_unicode_query_and_close_are_exact(self):
        api = self._api()
        for directory in (False, True):
            with self.subTest(directory=directory):
                kernel = self._kernel_fixture()
                with patch.object(api.sys, "platform", "win32"), patch.object(api, "_kernel", return_value=kernel):
                    result = api.direct_volume_path(Path("metadata"), directory=directory)
                self.assertEqual(result, "\\\\?\\GLOBALROOT\\Device\\HarddiskVolume1\\用户\\🧪\\native")
                kernel.CreateFileW.assert_called_once_with("metadata", 0x80, 7, None, 3,
                    0x02000000 if directory else 0, None)
                args = kernel.GetFinalPathNameByHandleW.call_args.args
                self.assertEqual((args[0], args[2], args[3]), (123, 32768, 2))
                kernel.CloseHandle.assert_called_once_with(123)

    def test_invalid_open_handles_are_never_queried_or_closed(self):
        api = self._api()
        for handle in (0, None, False, True, -1, 0xffffffff, ctypes.c_void_p(-1).value):
            with self.subTest(handle=handle):
                kernel = self._kernel_fixture(); kernel.CreateFileW.return_value = handle
                with patch.object(api.sys, "platform", "win32"), patch.object(api, "_kernel", return_value=kernel), self.assertRaises(OSError):
                    api.direct_volume_path(Path("metadata"))
                kernel.GetFinalPathNameByHandleW.assert_not_called()
                kernel.CloseHandle.assert_not_called()

    def test_api_lifecycle_order_and_unterminated_full_buffer_are_checked(self):
        api = self._api()
        for unterminated in (False, True):
            with self.subTest(unterminated=unterminated):
                kernel = self._kernel_fixture()
                timeline = Mock()
                for name in ("CreateFileW", "GetFinalPathNameByHandleW", "CloseHandle"):
                    timeline.attach_mock(getattr(kernel, name), name)
                if unterminated:
                    def fill(handle, buffer, capacity, flags):
                        buffer[:] = "x" * capacity
                        return capacity - 1
                    kernel.GetFinalPathNameByHandleW.side_effect = fill
                with patch.object(api.sys, "platform", "win32"), patch.object(api, "_kernel", return_value=kernel):
                    if unterminated:
                        with self.assertRaises(OSError):
                            api.direct_volume_path(Path("metadata"))
                    else:
                        api.direct_volume_path(Path("metadata"))
                self.assertEqual([call[0] for call in timeline.mock_calls],
                                 ["CreateFileW", "GetFinalPathNameByHandleW", "CloseHandle"])

    def test_invalid_query_lengths_and_contents_close_once(self):
        api = self._api()
        for result in (0, 32768, 32769, True, False, None, -1, 1):
            with self.subTest(length=result):
                kernel = self._kernel_fixture()
                kernel.GetFinalPathNameByHandleW.side_effect = None
                kernel.GetFinalPathNameByHandleW.return_value = result
                with patch.object(api.sys, "platform", "win32"), patch.object(api, "_kernel", return_value=kernel), self.assertRaises(OSError):
                    api.direct_volume_path(Path("metadata"))
                kernel.CloseHandle.assert_called_once_with(123)
        for value in ("C:\\wrong", "\\Device\\HarddiskVolume1\\a:stream", "\\Device\\HarddiskVolume1\\a\x00tail"):
            with self.subTest(value=value):
                kernel = self._kernel_fixture(value)
                with patch.object(api.sys, "platform", "win32"), patch.object(api, "_kernel", return_value=kernel), self.assertRaises((ValueError, OSError)):
                    api.direct_volume_path(Path("metadata"))
                kernel.CloseHandle.assert_called_once_with(123)

    def test_query_exception_and_close_failure_cannot_report_success(self):
        api = self._api()
        for failure in (OSError("query private"), UnicodeError("query private")):
            kernel = self._kernel_fixture(); kernel.GetFinalPathNameByHandleW.side_effect = failure
            with patch.object(api.sys, "platform", "win32"), patch.object(api, "_kernel", return_value=kernel), self.assertRaises(type(failure)):
                api.direct_volume_path(Path("metadata"))
            kernel.CloseHandle.assert_called_once_with(123)
        kernel = self._kernel_fixture(); kernel.CloseHandle.return_value = 0
        with patch.object(api.sys, "platform", "win32"), patch.object(api, "_kernel", return_value=kernel), self.assertRaises(OSError):
            api.direct_volume_path(Path("metadata"))
        kernel.CloseHandle.assert_called_once_with(123)

    def test_wrong_platform_or_nonbool_directory_never_opens(self):
        api = self._api()
        for platform, directory in (("linux", False), ("win32", 1), ("win32", None)):
            with self.subTest(platform=platform, directory=directory), patch.object(api.sys, "platform", platform), patch.object(api, "_kernel") as kernel, self.assertRaises(ValueError):
                api.direct_volume_path(Path("metadata"), directory=directory)
            kernel.assert_not_called()

    def _probe_fixture(self, api, root, source="a" * 40, arch="x64"):
        helper = root / f"icode-sandbox-windows-{arch}.exe"
        image = _synthetic_pe(0x8664 if arch == "x64" else 0xaa64)
        helper.write_bytes(image)
        verifier = root / f"icode-provenance-windows-{arch}.exe"
        proof = Path(str(helper) + ".sigstore.json")
        resources = (arch, root, helper, verifier, proof)
        receipt = dict(schema_version=1, provenance_verified=True, launch_authorized=False,
            artifact_sha256=hashlib.sha256(image).hexdigest(), source_sha=source, architecture=arch)
        wire = json.dumps(receipt, separators=(",", ":")).encode("ascii") + b"\n"
        return resources, wire

    def test_probe_exact_four_paths_argv_budget_environment_and_negative_source(self):
        api = self._api()
        for arch, source in (("x64", "a" * 40), ("arm64", "0" * 40)):
            with self.subTest(arch=arch), tempfile.TemporaryDirectory() as raw:
                root = Path(raw); resources, wire = self._probe_fixture(api, root, source, arch)
                converted = ["\\\\?\\GLOBALROOT\\Device\\HarddiskVolume1\\" + name for name in ("verifier", "helper", "proof", "native")]
                with patch.object(api.sys, "platform", "win32"), patch.object(api, "_installed_resources", return_value=resources), patch.object(api, "direct_volume_path", side_effect=converted) as paths, patch.dict(os.environ, {"SystemRoot": "windows", "WINDIR": "windows", "PRIVATE": "not inherited"}, clear=True), patch("icode.runner._run_unittest_with_bounded_output", side_effect=[(0, wire, b""), (78, b"", b"icode_provenance: verification_failed\n")]) as run:
                    api.probe(source)
                self.assertEqual([call.args[0] for call in paths.call_args_list], [resources[3], resources[2], resources[4], root])
                self.assertEqual([call.kwargs for call in paths.call_args_list], [{}, {}, {}, {"directory": True}])
                expected = [converted[0], "--artifact", converted[1], "--bundle", converted[2], "--source-sha", source, "--arch", arch]
                self.assertEqual(run.call_args_list[0].args[0], expected)
                expected[6] = "1" * 40 if source == "0" * 40 else "0" * 40
                self.assertEqual(run.call_args_list[1].args[0], expected)
                for call in run.call_args_list:
                    self.assertEqual(call.kwargs, dict(workspace=Path(converted[3]), timeout=30, output_limit_bytes=512,
                        environment={"SystemRoot": "windows", "WINDIR": "windows"}))

    def test_probe_rejects_noncanonical_positive_results_before_negative(self):
        api = self._api()
        with tempfile.TemporaryDirectory() as raw:
            resources, wire = self._probe_fixture(api, Path(raw))
            bad_wires = [wire[:-1], wire + b"\n", wire + b"PRIVATE", b"\xff\n", wire.replace(b'"schema_version":1', b'"schema_version":true'), wire.replace(b'"schema_version":1', b'"schema_version":1.0'), wire.replace(b'"provenance_verified":true', b'"provenance_verified":1'), wire.replace(b'"launch_authorized":false', b'"launch_authorized":0'), wire.replace(b'"schema_version":', b'"schema_version":1,"schema_version":'), wire.replace(b'}\n', b',"extra":false}\n')]
            receipt = json.loads(wire)
            for field in receipt:
                missing = dict(receipt)
                del missing[field]
                bad_wires.append(json.dumps(missing, separators=(",", ":")).encode() + b"\n")
            for field, value in (("artifact_sha256", "0" * 64),
                                 ("source_sha", "0" * 40), ("architecture", "arm64")):
                changed = dict(receipt, **{field: value})
                bad_wires.append(json.dumps(changed, separators=(",", ":")).encode() + b"\n")
            results = [(0, bad, b"") for bad in bad_wires] + [None, [0, wire, b""], (0, wire), (True, wire, b""), (1, wire, b""), (0, wire.decode(), b""), (0, wire, ""), (0, wire, b"warning")]
            for index, result in enumerate(results):
                with self.subTest(case=index), patch.object(api.sys, "platform", "win32"), patch.object(api, "_installed_resources", return_value=resources), patch.object(api, "direct_volume_path", return_value="fixed"), patch("icode.runner._run_unittest_with_bounded_output", return_value=result) as run, self.assertRaises(ValueError):
                    api.probe("a" * 40)
                self.assertEqual(run.call_count, 1)

    def test_probe_rejects_negative_result_type_code_and_wire(self):
        api = self._api()
        with tempfile.TemporaryDirectory() as raw:
            resources, wire = self._probe_fixture(api, Path(raw))
            error = b"icode_provenance: verification_failed\n"
            for result in (None, [78, b"", error], (78, b""), (True, b"", error), (0, b"", error), (78, b"output", error), (78, "", error), (78, b"", error.decode()), (78, b"", error[:-1]), (78, b"", error + b"\n")):
                with self.subTest(result=repr(result)), patch.object(api.sys, "platform", "win32"), patch.object(api, "_installed_resources", return_value=resources), patch.object(api, "direct_volume_path", return_value="fixed"), patch("icode.runner._run_unittest_with_bounded_output", side_effect=[(0, wire, b""), result]) as run, self.assertRaises(ValueError):
                    api.probe("a" * 40)
                self.assertEqual(run.call_count, 2)

    def test_probe_capture_timeout_and_budget_errors_propagate(self):
        from icode.runner import VerificationOutputCaptureError, VerificationOutputLimitError
        api = self._api()
        with tempfile.TemporaryDirectory() as raw:
            resources, wire = self._probe_fixture(api, Path(raw))
            for failure in (subprocess.TimeoutExpired("PRIVATE", 30), VerificationOutputLimitError(512, return_code=0), VerificationOutputCaptureError("cleanup_unknown", return_code=0)):
                for negative in (False, True):
                    effects = [(0, wire, b""), failure] if negative else [failure]
                    with self.subTest(error=type(failure), negative=negative), patch.object(api.sys, "platform", "win32"), patch.object(api, "_installed_resources", return_value=resources), patch.object(api, "direct_volume_path", return_value="fixed"), patch("icode.runner._run_unittest_with_bounded_output", side_effect=effects), self.assertRaises(type(failure)):
                        api.probe("a" * 40)

    def test_invalid_input_is_rejected_before_resource_or_process_access(self):
        api = self._api()
        for platform, source in (("linux", "a" * 40), ("win32", None), ("win32", True), ("win32", 1), ("win32", "A" * 40), ("win32", "a" * 39), ("win32", "a" * 41)):
            with self.subTest(platform=platform, source=source), patch.object(api.sys, "platform", platform), patch.object(api, "_installed_resources") as resources, patch("icode.runner._run_unittest_with_bounded_output") as run, self.assertRaises(ValueError):
                api.probe(source)
            resources.assert_not_called(); run.assert_not_called()

    def test_invalid_helper_bytes_and_metadata_prevent_conversion_and_execution(self):
        api = self._api()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); resources, _ = self._probe_fixture(api, root); helper = resources[2]
            for image in (b"", b"not PE", _synthetic_pe(0xaa64)):
                helper.write_bytes(image)
                with self.subTest(image=image[:2]), patch.object(api.sys, "platform", "win32"), patch.object(api, "_installed_resources", return_value=resources), patch.object(api, "direct_volume_path") as paths, patch("icode.runner._run_unittest_with_bounded_output") as run, self.assertRaises(ValueError):
                    api.probe("a" * 40)
                paths.assert_not_called(); run.assert_not_called()
            helper.write_bytes(_synthetic_pe(0x8664))
            info = helper.lstat()
            for mode, nlink, size in ((stat.S_IFDIR, 1, info.st_size), (stat.S_IFLNK, 1, info.st_size), (stat.S_IFREG, 2, info.st_size), (stat.S_IFREG, 1, 64 * 1024 * 1024 + 1), (stat.S_IFREG, 1, info.st_size + 1)):
                fake = SimpleNamespace(st_mode=mode, st_nlink=nlink, st_size=size)
                with self.subTest(mode=mode, nlink=nlink, size=size), patch.object(api.sys, "platform", "win32"), patch.object(api, "_installed_resources", return_value=resources), patch.object(Path, "lstat", return_value=fake), patch.object(api, "direct_volume_path") as paths, patch("icode.runner._run_unittest_with_bounded_output") as run, self.assertRaises(ValueError):
                    api.probe("a" * 40)
                paths.assert_not_called(); run.assert_not_called()

    def test_resources_use_installed_purelib_and_actual_supported_architecture(self):
        import icode
        api = self._api()
        with tempfile.TemporaryDirectory() as raw:
            purelib = Path(raw); package = purelib / "icode"
            for platform, arch in (("win-amd64", "x64"), ("win-arm64", "arm64")):
                with self.subTest(platform=platform), patch.object(icode, "__file__", str(package / "__init__.py")), patch.object(api.sysconfig, "get_paths", return_value={"purelib": str(purelib)}), patch.object(api.sysconfig, "get_platform", return_value=platform):
                    found = api._installed_resources()
                native = package / "native"
                self.assertEqual(found, (arch, native, native / f"icode-sandbox-windows-{arch}.exe", native / f"icode-provenance-windows-{arch}.exe", native / f"icode-sandbox-windows-{arch}.exe.sigstore.json"))
            with patch.object(api.sysconfig, "get_paths", return_value={"purelib": str(purelib)}), self.assertRaises(ValueError):
                api._installed_resources()
            with patch.object(icode, "__file__", str(package / "__init__.py")), patch.object(api.sysconfig, "get_paths", return_value={"purelib": str(purelib)}), patch.object(api.sysconfig, "get_platform", return_value="win32"), self.assertRaises(ValueError):
                api._installed_resources()

    def test_main_fixed_success_and_expected_errors_do_not_expose_private_values(self):
        api = self._api()
        failures = [ImportError("PRIVATE"), OSError("PRIVATE"), UnicodeError("PRIVATE"), ValueError("PRIVATE"), RuntimeError("PRIVATE"), subprocess.SubprocessError("PRIVATE"), subprocess.TimeoutExpired("PRIVATE", 30)]
        for failure in (None, *failures):
            output = io.StringIO()
            with self.subTest(error=type(failure)), patch.object(sys, "argv", ["probe", "--source-sha", "a" * 40]), patch.object(api, "probe", side_effect=failure), redirect_stdout(output):
                code = api.main()
            self.assertEqual(code, 0 if failure is None else 1)
            self.assertEqual(output.getvalue(), "windows-direct-volume compatibility=PASS launch_authorized=false\n" if failure is None else "::error::windows_direct_volume_probe_failed\n")

    def test_main_does_not_swallow_interrupt_or_programming_errors(self):
        api = self._api()
        for failure in (KeyboardInterrupt(), SystemExit(12), TypeError("PRIVATE"), KeyError("PRIVATE"), AssertionError("PRIVATE")):
            with self.subTest(error=type(failure)), patch.object(sys, "argv", ["probe", "--source-sha", "a" * 40]), patch.object(api, "probe", side_effect=failure), redirect_stdout(io.StringIO()), self.assertRaises(type(failure)):
                api.main()
