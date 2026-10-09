"""CI build selection contracts, independent of native Windows acceptance."""

import importlib.util
import io
import json
import os
from pathlib import Path, PureWindowsPath
import shutil
import stat
import subprocess
import sys
import tempfile
from contextlib import ExitStack, redirect_stdout
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
MARKER = "# CI-only selected build context; not product executable authorization."
NS = "http://schemas.microsoft.com/developer/msbuild/2003"


class TestWindowsBuildContext(unittest.TestCase):
    def api(self):
        spec = importlib.util.find_spec("scripts.probe_windows_build_context")
        self.assertIsNotNone(spec, "build-context CI diagnostic is missing")
        import scripts.probe_windows_build_context as api
        return api

    def test_interface_exists_without_product_authority(self):
        api = self.api()
        self.assertTrue(callable(api.probe))
        self.assertTrue(callable(api.main))

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="icode-context-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.context = self.root / "icode-windows-build-context.json"
        self.project = self.root / "icode_windows_bootstrap.vcxproj"
        self.metadata = dict(schema_version=1, generator="Visual Studio 17 2022", platform="x64",
                             toolset="v143", sdk_version="10.0.22621.0", msbuild="C:\\Build Tools\\MSBuild.exe")
        self.properties = dict(Configuration="Release", Platform="x64", PlatformToolset="v143",
            WindowsTargetPlatformVersion="10.0.22621.0", VCToolsInstallDir="C:\\VC\\Tools\\",
            WindowsSdkDir="C:\\SDK\\", MSBuildToolsPath="C:\\Build Tools\\")
        self.write_context(self.metadata)
        self.project.write_bytes(self.xml())
        self.real_lstat = Path.lstat

    def write_context(self, value):
        self.context.write_bytes(json.dumps(value).encode())

    def xml(self, platform="x64"):
        return (f'<?xml version="1.0" encoding="utf-8"?><Project xmlns="{NS}">'
                '<PropertyGroup><WindowsTargetPlatformVersion>10.0.22621.0</WindowsTargetPlatformVersion>'
                '</PropertyGroup><PropertyGroup Condition="' + "'$(Configuration)|$(Platform)' == 'Release|"
                + platform + '\'"><PlatformToolset>v143</PlatformToolset></PropertyGroup></Project>').encode()

    def result(self, value=None):
        return 0, json.dumps({"Properties": self.properties if value is None else value}).encode(), b""

    def windows_lstat(self, path, *args, **kwargs):
        # Real fixtures can themselves live on C: on a Windows test host.
        if path == self.root or self.root in path.parents:
            return self.real_lstat(path, *args, **kwargs)
        name = PureWindowsPath(path)
        if name == PureWindowsPath(self.metadata["msbuild"]):
            return SimpleNamespace(st_mode=stat.S_IFREG | 0o666)
        if name in {PureWindowsPath(self.properties[key])
                    for key in ("VCToolsInstallDir", "WindowsSdkDir", "MSBuildToolsPath")}:
            return SimpleNamespace(st_mode=stat.S_IFDIR | 0o777)
        if name.drive:
            raise FileNotFoundError(str(name))
        return self.real_lstat(path, *args, **kwargs)

    def invoke(self, *, bad=False, count=0, arch="x64", root=None, result=None, effect=None, platform="win32"):
        api = self.api()
        with patch.object(api.sys, "platform", platform), \
                patch.object(Path, "lstat", lambda path, *args, **kwargs: self.windows_lstat(path, *args, **kwargs)), \
                patch.object(api, "_run_unittest_with_bounded_output",
                             return_value=self.result() if result is None else result, side_effect=effect) as runner:
            if bad:
                with self.assertRaises((OSError, UnicodeError, ValueError, RuntimeError, ET.ParseError)):
                    api.probe(self.root if root is None else root, arch)
                self.assertEqual(runner.call_count, count)
                return
            receipt = api.probe(self.root if root is None else root, arch)
        return receipt, runner

    def test_two_architectures_exact_command_receipt_and_runner_bounds(self):
        for arch, platform in (("x64", "x64"), ("arm64", "ARM64")):
            with self.subTest(arch=arch):
                self.metadata["platform"] = self.properties["Platform"] = platform
                self.write_context(self.metadata)
                self.project.write_bytes(self.xml(platform))
                receipt, runner = self.invoke(arch=arch)
                self.assertEqual(receipt, dict(schema_version=1, architecture=arch,
                    **{key: self.metadata[key] for key in ("generator", "toolset", "sdk_version", "msbuild")},
                    **{key: self.properties[key] for key in ("VCToolsInstallDir", "WindowsSdkDir", "MSBuildToolsPath")}))
                runner.assert_called_once_with([self.metadata["msbuild"], str(self.project), "-nologo",
                    "-noAutoResponse", "-nodeReuse:false", "-maxCpuCount:1", "-property:Configuration=Release",
                    f"-property:Platform={platform}", "-getProperty:Configuration,Platform,PlatformToolset,"
                    "WindowsTargetPlatformVersion,VCToolsInstallDir,WindowsSdkDir,MSBuildToolsPath"],
                    workspace=self.root, timeout=30, output_limit_bytes=16384, environment=os.environ.copy())

    def test_root_architecture_platform_zero_execution(self):
        for kwargs in (dict(platform="linux"), dict(arch="ARM64"), dict(arch="x86"), dict(root=Path("relative")),
                       dict(root=self.root / "missing"), dict(root=self.context)):
            with self.subTest(kwargs=kwargs):
                self.invoke(bad=True, **kwargs)

    def test_windows_fixture_registry_uses_canonical_windows_paths(self):
        entries = [(self.metadata["msbuild"], stat.S_ISREG)] + [
            (self.properties[key], stat.S_ISDIR)
            for key in ("VCToolsInstallDir", "WindowsSdkDir", "MSBuildToolsPath")]
        for value, predicate in entries:
            with self.subTest(value=value):
                normalized = PureWindowsPath(value)
                try:
                    info = self.windows_lstat(normalized)
                except FileNotFoundError:
                    self.fail(f"registered Windows path rejected after normalization: {normalized}")
                self.assertTrue(predicate(info.st_mode))
        with self.assertRaises(FileNotFoundError):
            self.windows_lstat(PureWindowsPath("C:\\missing\\"))
        self.assertTrue(stat.S_ISDIR(self.windows_lstat(self.root).st_mode))
        self.assertEqual(self.windows_lstat(self.context).st_size, self.context.stat().st_size)

    def test_link_metadata_negative_control_needs_no_symlink_privilege(self):
        # No native Windows link/privilege proof: link rejection is metadata-only.
        with patch.object(Path, "symlink_to", side_effect=AssertionError("native link creation forbidden")):
            self.test_fixed_files_reject_directories_symlinks_and_size_changes()

    def test_context_each_missing_duplicate_and_closed_schema(self):
        for key in self.metadata:
            with self.subTest(key=key):
                data = dict(self.metadata)
                del data[key]
                self.write_context(data)
                self.invoke(bad=True)
                raw = json.dumps(self.metadata)
                self.context.write_text(raw[:-1] + "," + json.dumps(key) + ":" + json.dumps(self.metadata[key]) + "}")
                self.invoke(bad=True)
        for data in (dict(self.metadata, extra=1), dict(self.metadata, schema_version=True),
                     dict(self.metadata, schema_version=1.0), dict(self.metadata, schema_version=2), [], None):
            self.write_context(data)
            self.invoke(bad=True)

    def test_context_strings_control_surrogate_generator_platform_and_tool(self):
        for key in self.metadata:
            if key == "schema_version":
                continue
            for value in ("", 1, None, "bad\x00", "bad\n", "bad\x7f", "bad\x85", "bad\ud800"):
                with self.subTest(key=key, value=repr(value)):
                    self.write_context(dict(self.metadata, **{key: value}))
                    self.invoke(bad=True)
        for key, value in (("generator", "Ninja"), ("generator", "Visual Studio 17 2022 extra"),
                           ("platform", "ARM64"), ("msbuild", "MSBuild.exe"), ("msbuild", "C:MSBuild.exe"),
                           ("msbuild", "C:\\missing\\MSBuild.exe"), ("msbuild", self.properties["VCToolsInstallDir"]),
                           ("msbuild", "C:\\Build Tools\\other.exe")):
            with self.subTest(key=key, value=value):
                self.write_context(dict(self.metadata, **{key: value}))
                self.invoke(bad=True)

    def test_context_raw_utf8_bom_empty_limit_json_constants_and_depth(self):
        valid = self.context.read_bytes()
        for raw in (b"", b"\xff", b"\xef\xbb\xbf" + valid, b"x" * 4097, b'{"schema_version":NaN}',
                    b'{"schema_version":Infinity}', b"[" * 2000 + b"0" + b"]" * 2000, valid + b"PRIVATE"):
            with self.subTest(size=len(raw)):
                self.context.write_bytes(raw)
                self.invoke(bad=True)

    def test_fixed_files_reject_directories_symlinks_and_size_changes(self):
        for target in (self.context, self.project):
            original = target.read_bytes()
            target.unlink()
            target.mkdir()
            self.invoke(bad=True)
            target.rmdir()
            target.write_bytes(original)
            api = self.api()
            # Synthetic lstat metadata avoids Windows link-creation privileges.
            # This establishes parser admission only, not native symlink behavior.
            def linked(path, *args, **kwargs):
                if path == target:
                    return SimpleNamespace(st_mode=stat.S_IFLNK | 0o777, st_size=len(original))
                return self.windows_lstat(path, *args, **kwargs)
            with patch.object(Path, "lstat", linked), patch.object(api.sys, "platform", "win32"), \
                    patch.object(api, "_run_unittest_with_bounded_output") as runner:
                with self.assertRaises(RuntimeError):
                    api.probe(self.root, "x64")
                runner.assert_not_called()
            def changed(path, *args, **kwargs):
                info = self.windows_lstat(path, *args, **kwargs)
                return SimpleNamespace(st_mode=info.st_mode, st_size=info.st_size + 1) if path == target else info
            with patch.object(Path, "lstat", changed), patch.object(api.sys, "platform", "win32"), \
                    patch.object(api, "_run_unittest_with_bounded_output") as runner:
                with self.assertRaises(RuntimeError):
                    api.probe(self.root, "x64")
                runner.assert_not_called()

    def test_xml_bom_whitespace_and_unrelated_configuration_accepted(self):
        extra = '<PropertyGroup Condition="' + "'$(Configuration)|$(Platform)'=='Debug|ARM64'" + '"><PlatformToolset>bad</PlatformToolset></PropertyGroup>'
        self.project.write_bytes(b"\xef\xbb\xbf" + self.xml().replace(b"' == 'Release|x64'", b"'=='Release|x64'").replace(
            b"</Project>", extra.encode() + b"</Project>"))
        self.invoke()

    def test_xml_namespace_root_sdk_toolset_current_configuration_entities_and_bytes(self):
        valid = self.xml()
        sdk = b"<WindowsTargetPlatformVersion>10.0.22621.0</WindowsTargetPlatformVersion>"
        tool = b"<PlatformToolset>v143</PlatformToolset>"
        cases = [valid.replace(NS.encode(), b"urn:wrong"), valid.replace(b"Project", b"Other"),
                 valid.replace(sdk, b""), valid.replace(sdk, sdk * 2), valid.replace(sdk, b"<WindowsTargetPlatformVersion/>"),
                 valid.replace(tool, b""), valid.replace(tool, tool * 2), valid.replace(tool, b"<PlatformToolset/>"),
                 valid.replace(b"Release|x64", b"Debug|x64"), valid.replace(b"Release|x64", b"Release|ARM64"),
                 valid.replace(b"v143", b"v142"), valid.replace(b"22621", b"19041"),
                 valid.replace(b"</Project>", valid[valid.index(b'<PropertyGroup Condition='):valid.index(b"</Project>")] + b"</Project>"),
                 valid.replace(b"'$(Configuration)|$(Platform)'", b"'$(Configuration)'"),
                 b"<!DOCTYPE Project>" + valid, b'<!ENTITY private "secret">' + valid,
                 b"<Project>", b"\xff", b"", b"x" * (1024 * 1024 + 1)]
        for index, raw in enumerate(cases):
            with self.subTest(index=index):
                self.project.write_bytes(raw)
                self.invoke(bad=True)

    def test_result_exact_types_exit_stdout_stderr_limits_and_json(self):
        good = self.result()
        cases = [list(good), good[:2], good + (b"",), (True, good[1], b""), (0.0, good[1], b""),
                 (1, good[1], b"PRIVATE"),
                 (0, good[1].decode(), b""), (0, b"", b""), (0, good[1], ""), (0, good[1], b"PRIVATE"),
                 (0, b"x" * 16385, b""), (0, b"\xff", b""), (0, b"\xef\xbb\xbf" + good[1], b""),
                 (0, b"[" * 2000 + b"0" + b"]" * 2000, b"")]
        for raw in (b"{}", b'{"Properties":{},"Extra":{}}', b'{"Properties":{},"Properties":{}}',
                    b'{"Properties":NaN}', b'{"Properties":[]}', b'{"Properties":null}', good[1] + b"PRIVATE"):
            cases.append((0, raw, b""))
        for index, result in enumerate(cases):
            with self.subTest(index=index):
                self.invoke(bad=True, count=1, result=result)

    def test_result_each_property_missing_duplicate_extra_type_controls_and_surrogate(self):
        for key in self.properties:
            with self.subTest(key=key):
                missing = dict(self.properties)
                del missing[key]
                self.invoke(bad=True, count=1, result=self.result(missing))
                raw = json.dumps(self.properties)
                duplicate = raw[:-1] + "," + json.dumps(key) + ":" + json.dumps(self.properties[key]) + "}"
                self.invoke(bad=True, count=1, result=(0, ('{"Properties":' + duplicate + "}").encode(), b""))
            for value in ("", None, 1, "bad\n", "bad\x85", "bad\udfff"):
                with self.subTest(key=key, value=repr(value)):
                    self.invoke(bad=True, count=1, result=self.result(dict(self.properties, **{key: value})))
        self.invoke(bad=True, count=1, result=self.result(dict(self.properties, Extra="bad")))

    def test_result_matching_properties_and_absolute_existing_directories(self):
        for key in ("Configuration", "Platform", "PlatformToolset", "WindowsTargetPlatformVersion"):
            self.invoke(bad=True, count=1, result=self.result(dict(self.properties, **{key: "wrong"})))
        for key in ("VCToolsInstallDir", "WindowsSdkDir", "MSBuildToolsPath"):
            for value in ("relative", "C:relative", "C:\\missing\\", self.metadata["msbuild"]):
                with self.subTest(key=key, value=value):
                    self.invoke(bad=True, count=1, result=self.result(dict(self.properties, **{key: value})))

    def main_call(self, effect=None):
        api = self.api()
        output = io.StringIO()
        with patch.object(sys, "argv", ["probe", "--build-directory", str(self.root), "--architecture", "x64"]), \
                patch.object(api, "probe", side_effect=effect, return_value={"schema_version": 1, "name": "工具"}), redirect_stdout(output):
            code = api.main()
        return code, output.getvalue()

    def test_main_fixed_receipt_expected_errors_privacy_and_programming_errors(self):
        self.assertEqual(self.main_call(), (0, 'windows-build-context status=PASS production_authority=none\n'
            'windows-build-context receipt={"schema_version":1,"name":"\\u5de5\\u5177"}\n'))
        for error, kind in ((OSError("PRIVATE"), "os_error"), (UnicodeError("PRIVATE"), "unicode_error"),
                            (ValueError("PRIVATE"), "validation_value"), (RuntimeError("PRIVATE"), "validation_runtime"),
                            (ET.ParseError("PRIVATE"), "xml_parse"), (RecursionError("PRIVATE"), "validation_runtime"),
                            (subprocess.TimeoutExpired("PRIVATE", 30), "timeout"),
                            (subprocess.CalledProcessError(1, "PRIVATE"), "subprocess_error")):
            expected = (1, "::error::windows_build_context_probe_failed\n"
                + 'windows-build-context rejection={"schema_version":1,"stage":"unavailable","failure_kind":"'
                + kind + '","production_authority":"none"}\n')
            self.assertEqual(self.main_call(error), expected)
        for error in (TypeError("bug"), AssertionError("bug"), MemoryError(), KeyboardInterrupt(), SystemExit()):
            with self.assertRaises(type(error)) as raised:
                self.main_call(error)
            self.assertIs(raised.exception, error)

    def test_timeout_and_old_msbuild_never_trigger_a_second_query(self):
        api = self.api()
        with patch.object(Path, "lstat", lambda path, *args, **kwargs: self.windows_lstat(path, *args, **kwargs)), \
                patch.object(api.sys, "platform", "win32"), \
                patch.object(api, "_run_unittest_with_bounded_output",
                             side_effect=subprocess.TimeoutExpired("PRIVATE", 30)) as runner:
            with self.assertRaises(subprocess.TimeoutExpired):
                api.probe(self.root, "x64")
            runner.assert_called_once()
        self.invoke(bad=True, count=1, result=(1, b"", b"old MSBuild PRIVATE unsupported -getProperty"))

    def test_cli_accepts_only_the_two_fixed_argument_names(self):
        api = self.api()
        for flags in (["--build-dir", str(self.root), "--architecture", "x64"],
                      ["--build-directory", str(self.root), "--architecture", "x64", "--target", "Build"]):
            with patch.object(sys, "argv", ["probe", *flags]), patch.object(api, "probe", return_value={}) as probe, \
                    patch.object(sys, "stderr", io.StringIO()), redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    api.main()
                self.assertEqual(raised.exception.code, 2)
                probe.assert_not_called()

    def test_unicode_tool_path_and_casefold_basename_are_preserved(self):
        self.metadata["msbuild"] = "C:\\工具\\MsBuIlD.ExE"
        self.write_context(self.metadata)
        receipt, runner = self.invoke()
        self.assertEqual(receipt["msbuild"], self.metadata["msbuild"])
        self.assertEqual(runner.call_args.args[0][0], self.metadata["msbuild"])

    def test_windows_objects_reject_links_before_and_after_query(self):
        api = self.api()
        for key in ("msbuild", "VCToolsInstallDir", "WindowsSdkDir", "MSBuildToolsPath"):
            selected = self.metadata[key] if key == "msbuild" else self.properties[key]
            def linked(path, *args, **kwargs):
                if PureWindowsPath(path) == PureWindowsPath(selected):
                    return SimpleNamespace(st_mode=stat.S_IFLNK | 0o777)
                return self.windows_lstat(path, *args, **kwargs)
            with patch.object(Path, "lstat", linked), patch.object(api.sys, "platform", "win32"), \
                    patch.object(api, "_run_unittest_with_bounded_output", return_value=self.result()) as runner:
                with self.assertRaises(ValueError):
                    api.probe(self.root, "x64")
                self.assertEqual(runner.call_count, 0 if key == "msbuild" else 1)

    def test_msbuild_named_directory_is_rejected_before_query(self):
        api = self.api()
        def directory_tool(path, *args, **kwargs):
            if PureWindowsPath(path) == PureWindowsPath(self.metadata["msbuild"]):
                return SimpleNamespace(st_mode=stat.S_IFDIR | 0o777)
            return self.windows_lstat(path, *args, **kwargs)
        with patch.object(Path, "lstat", directory_tool), patch.object(api.sys, "platform", "win32"), \
                patch.object(api, "_run_unittest_with_bounded_output") as runner:
            with self.assertRaises(ValueError):
                api.probe(self.root, "x64")
            runner.assert_not_called()


    def diagnostic_api(self):
        api = self.api()
        for name in ("probe", "main", "_ProbeDiagnostic", "_new_diagnostic",
                     "_set_diagnostic_stage", "_mark_diagnostic_stage", "_get_diagnostic_stage",
                     "_failure_kind", "_rejection_line", "_emit_rejection",
                     "VerificationOutputCaptureError", "VerificationOutputLimitError"):
            self.assertTrue(callable(getattr(api, name, None)),
                            "missing diagnostic interface: " + name)
        for name in ("_STAGES", "_FAILURE_KINDS"):
            self.assertIs(type(getattr(api, name, None)), frozenset,
                          "missing exact frozenset metadata: " + name)
        self.assertIs(type(getattr(api, "_REJECTION_PREFIX", None)), str)
        self.assertEqual(api._REJECTION_PREFIX, "windows-build-context rejection=")
        import inspect
        parameter = inspect.signature(api.probe).parameters.get("_diagnostic")
        self.assertIsNotNone(parameter, "missing private keyword-only diagnostic parameter")
        self.assertIs(parameter.kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertIsNone(parameter.default)
        return api

    def diagnostic_main(self, *, arch="x64", platform="win32", result=None,
                        effect=None, lstat=None, stream=None):
        api = self.diagnostic_api()
        output = io.StringIO() if stream is None else stream
        with ExitStack() as stack:
            stack.enter_context(patch.object(sys, "argv", ["probe", "--build-directory",
                str(self.root), "--architecture", arch]))
            stack.enter_context(patch.object(api.sys, "platform", platform))
            stack.enter_context(patch.object(Path, "lstat", lstat or
                (lambda path, *args, **kwargs: self.windows_lstat(path, *args, **kwargs))))
            runner = stack.enter_context(patch.object(api, "_run_unittest_with_bounded_output",
                return_value=(self.result() if effect is None else (0, b"", b""))
                if result is None else result, side_effect=effect))
            stack.enter_context(redirect_stdout(output))
            code = api.main()
        return code, output.getvalue(), runner

    def assert_rejection(self, output, stage, kind):
        prefix = "windows-build-context rejection="
        lines = output.splitlines(keepends=True)
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0], "::error::windows_build_context_probe_failed\n")
        self.assertTrue(lines[1].startswith(prefix))
        self.assertTrue(lines[1].endswith("\n"))
        self.assertLessEqual(len(lines[1].encode("ascii")), 256)
        data = json.loads(lines[1][len(prefix):-1])
        self.assertEqual(set(data), {"schema_version", "stage", "failure_kind", "production_authority"})
        self.assertIs(type(data["schema_version"]), int)
        self.assertEqual(data["schema_version"], 1)
        for key in ("stage", "failure_kind", "production_authority"):
            self.assertIs(type(data[key]), str)
        self.assertEqual(data, dict(schema_version=1, stage=stage,
            failure_kind=kind, production_authority="none"))
        self.assertNotIn("PRIVATE_PAYLOAD", output)
        return data

    def test_diagnostic_real_stage_rejections_and_query_counts(self):
        cases = (
            ("input", "validation_value", 0),
            ("context_read", "os_error", 0),
            ("context_validate", "validation_value", 0),
            ("msbuild_identity", "validation_value", 0),
            ("project_read", "os_error", 0),
            ("project_validate", "xml_parse", 0),
            ("query", "timeout", 1),
            ("query_result", "validation_runtime", 1),
            ("output_json", "validation_value", 1),
            ("properties_validate", "validation_value", 1),
            ("tool_directory", "validation_value", 1),
        )
        for stage, kind, calls in cases:
            with self.subTest(stage=stage):
                self.write_context(self.metadata)
                self.project.write_bytes(self.xml())
                kwargs = {}
                if stage == "input":
                    kwargs["platform"] = "linux"
                elif stage == "context_read":
                    self.context.unlink()
                elif stage == "context_validate":
                    self.context.write_bytes(b"{")
                elif stage == "msbuild_identity":
                    self.write_context(dict(self.metadata, msbuild="C:\\Build Tools\\other.exe"))
                elif stage == "project_read":
                    self.project.unlink()
                elif stage == "project_validate":
                    self.project.write_bytes(b"<Project>")
                elif stage == "query":
                    kwargs["effect"] = subprocess.TimeoutExpired("PRIVATE_PAYLOAD", 30)
                elif stage == "query_result":
                    kwargs["result"] = (1, b"PRIVATE_PAYLOAD", b"")
                elif stage == "output_json":
                    kwargs["result"] = (0, b"{", b"")
                elif stage == "properties_validate":
                    kwargs["result"] = self.result(dict(self.properties, Platform="wrong"))
                elif stage == "tool_directory":
                    kwargs["result"] = self.result(dict(self.properties, WindowsSdkDir="relative"))
                code, output, runner = self.diagnostic_main(**kwargs)
                self.assertEqual(code, 1)
                self.assert_rejection(output, stage, kind)
                self.assertEqual(runner.call_count, calls)

    def test_diagnostic_real_json_xml_property_semantics_are_not_mocked(self):
        valid = json.dumps(self.metadata).encode()
        for raw, kind in ((b"\xff", "unicode_error"),
                          (b"[" * 2000 + b"0" + b"]" * 2000, "validation_runtime"),
                          (valid[:-1] + b',"schema_version":1}', "validation_value"),
                          (b'{"schema_version":NaN}', "validation_value")):
            with self.subTest(context_kind=kind):
                self.context.write_bytes(raw)
                code, output, runner = self.diagnostic_main()
                self.assertEqual(code, 1)
                self.assert_rejection(output, "context_validate", kind)
                runner.assert_not_called()
        self.write_context(self.metadata)
        for raw, kind in ((b"\xff", "unicode_error"),
                          (b"<!DOCTYPE Project>" + self.xml(), "validation_value"),
                          (self.xml().replace(b"22621", b"19041"), "validation_value"),
                          (self.xml().replace(b"v143", b"v142"), "validation_value")):
            with self.subTest(project_kind=kind):
                self.project.write_bytes(raw)
                code, output, runner = self.diagnostic_main()
                self.assertEqual(code, 1)
                self.assert_rejection(output, "project_validate", kind)
                runner.assert_not_called()
        self.project.write_bytes(self.xml())
        for raw, stage, kind in ((b"\xff", "output_json", "unicode_error"),
                                (b'{"Properties":NaN}', "output_json", "validation_value"),
                                (b'{"Properties":{}}', "properties_validate", "validation_value")):
            with self.subTest(output_stage=stage, output_kind=kind):
                code, output, runner = self.diagnostic_main(result=(0, raw, b""))
                self.assertEqual(code, 1)
                self.assert_rejection(output, stage, kind)
                runner.assert_called_once()

    def test_diagnostic_kind_priority_and_unavailable(self):
        api = self.diagnostic_api()
        cases = (
            (subprocess.TimeoutExpired("PRIVATE_PAYLOAD", 30), "timeout"),
            (api.VerificationOutputCaptureError("PRIVATE_PAYLOAD"), "output_capture"),
            (api.VerificationOutputLimitError(16384), "output_limit"),
            (UnicodeDecodeError("utf-8", b"\xff", 0, 1, "PRIVATE_PAYLOAD"), "unicode_error"),
            (ET.ParseError("PRIVATE_PAYLOAD"), "xml_parse"),
            (FileNotFoundError("PRIVATE_PAYLOAD"), "os_error"),
            (ValueError("PRIVATE_PAYLOAD"), "validation_value"),
            (RuntimeError("PRIVATE_PAYLOAD"), "validation_runtime"),
            (RecursionError("PRIVATE_PAYLOAD"), "validation_runtime"),
            (subprocess.CalledProcessError(1, "PRIVATE_PAYLOAD", output=b"PRIVATE_PAYLOAD",
                stderr=b"PRIVATE_PAYLOAD"), "subprocess_error"),
            (Exception("PRIVATE_PAYLOAD"), "unavailable"),
        )
        for error, expected in cases:
            with self.subTest(kind=expected, error_type=type(error).__name__):
                self.assertEqual(api._failure_kind(error), expected)
        self.assertEqual(api._FAILURE_KINDS, frozenset(kind for _, kind in cases))
        self.assertEqual(len(api._FAILURE_KINDS), 10)

    def test_diagnostic_poison_str_repr_and_sensitive_payload_are_absent(self):
        api = self.diagnostic_api()
        def poison(self):
            raise AssertionError("exception text must never be read")
        def private_payload(self, name):
            if name in ("args", "cmd", "output", "stderr", "returncode", "__cause__", "__context__"):
                raise AssertionError("exception payload must never be read")
            return BaseException.__getattribute__(self, name)
        for base, args, kind in ((OSError, ("PRIVATE_PAYLOAD",), "os_error"),
                                (ValueError, ("PRIVATE_PAYLOAD",), "validation_value"),
                                (RuntimeError, ("PRIVATE_PAYLOAD",), "validation_runtime"),
                                (ET.ParseError, ("PRIVATE_PAYLOAD",), "xml_parse"),
                                (UnicodeError, ("PRIVATE_PAYLOAD",), "unicode_error"),
                                (RecursionError, ("PRIVATE_PAYLOAD",), "validation_runtime"),
                                (api.VerificationOutputCaptureError, ("PRIVATE_PAYLOAD",), "output_capture"),
                                (api.VerificationOutputLimitError, (16384,), "output_limit"),
                                (subprocess.TimeoutExpired, ("PRIVATE_PAYLOAD", 30), "timeout"),
                                (subprocess.CalledProcessError, (1, "PRIVATE_PAYLOAD"), "subprocess_error"),
                                (subprocess.SubprocessError, ("PRIVATE_PAYLOAD",), "subprocess_error")):
            error_class = type("PoisonError", (base,), {"__str__": poison, "__repr__": poison,
                "__getattribute__": private_payload})
            code, output, runner = self.diagnostic_main(effect=error_class(*args))
            self.assertEqual(code, 1)
            self.assert_rejection(output, "query", kind)
            runner.assert_called_once()

    def test_diagnostic_single_slot_closed_labels_and_isolated_instances(self):
        api = self.diagnostic_api()
        first, second = api._ProbeDiagnostic(), api._ProbeDiagnostic()
        self.assertEqual(api._ProbeDiagnostic.__slots__, ("stage",))
        self.assertFalse(hasattr(first, "__dict__"))
        expected = frozenset(("input", "context_read", "context_validate", "msbuild_identity",
            "project_read", "project_validate", "query", "query_result", "output_json",
            "properties_validate", "tool_directory", "unavailable"))
        self.assertEqual(api._STAGES, expected)
        class StringSubclass(str):
            pass
        for stage in sorted(expected):
            api._mark_diagnostic_stage(first, stage)
            self.assertEqual(api._get_diagnostic_stage(first), stage)
            self.assertEqual(api._get_diagnostic_stage(second), "unavailable")
        for stage in ("PRIVATE_PAYLOAD", None, 1, StringSubclass("query")):
            api._mark_diagnostic_stage(first, stage)
            self.assertEqual(api._get_diagnostic_stage(first), "unavailable")
        first.stage = StringSubclass("query")
        self.assertEqual(api._get_diagnostic_stage(first), "unavailable")
        first.stage = "PRIVATE_PAYLOAD"
        self.assertEqual(api._get_diagnostic_stage(first), "unavailable")
        del first.stage
        self.assertEqual(api._get_diagnostic_stage(first), "unavailable")
        api._mark_diagnostic_stage(first, "query")
        self.assertEqual(api._get_diagnostic_stage(first), "query")

    def test_diagnostic_foreign_and_subclass_objects_never_read_attributes(self):
        api = self.diagnostic_api()
        class Foreign:
            def __getattribute__(self, name):
                raise AssertionError("foreign attribute read")
            def __setattr__(self, name, value):
                raise AssertionError("foreign attribute write")
        class Subclass(api._ProbeDiagnostic):
            def __init__(self):
                pass
            def __getattribute__(self, name):
                raise AssertionError("subclass attribute read")
            def __setattr__(self, name, value):
                raise AssertionError("subclass attribute write")
        for observer in (None, Foreign(), Subclass()):
            api._mark_diagnostic_stage(observer, "query")
            self.assertEqual(api._get_diagnostic_stage(observer), "unavailable")
            with patch.object(api.sys, "platform", "win32"), \
                    patch.object(Path, "lstat", lambda path, *a, **k: self.windows_lstat(path, *a, **k)), \
                    patch.object(api, "_run_unittest_with_bounded_output", return_value=self.result()) as runner:
                receipt = api.probe(self.root, "x64", _diagnostic=observer)
            self.assertEqual(receipt["architecture"], "x64")
            runner.assert_called_once()

    def test_diagnostic_marker_fault_clears_old_stage_and_recovers(self):
        api = self.diagnostic_api()
        observer = api._ProbeDiagnostic()
        api._mark_diagnostic_stage(observer, "context_read")
        for error in (ValueError("PRIVATE_PAYLOAD"), RuntimeError("PRIVATE_PAYLOAD"),
                      OSError("PRIVATE_PAYLOAD")):
            with patch.object(api, "_set_diagnostic_stage", side_effect=error):
                api._mark_diagnostic_stage(observer, "query")
            self.assertEqual(api._get_diagnostic_stage(observer), "unavailable")
            api._mark_diagnostic_stage(observer, "query_result")
            self.assertEqual(api._get_diagnostic_stage(observer), "query_result")
        real_setattr = object.__setattr__
        def bad_setattr(instance, name, value):
            if value == "query":
                raise OSError("PRIVATE_PAYLOAD")
            real_setattr(instance, name, value)
        with patch.object(api._ProbeDiagnostic, "__setattr__", bad_setattr):
            api._mark_diagnostic_stage(observer, "query")
        self.assertEqual(api._get_diagnostic_stage(observer), "unavailable")
        api._mark_diagnostic_stage(observer, "tool_directory")
        self.assertEqual(api._get_diagnostic_stage(observer), "tool_directory")
        with patch.object(api, "_set_diagnostic_stage", side_effect=OSError("PRIVATE_PAYLOAD")):
            code, output, runner = self.diagnostic_main(effect=ValueError("PRIVATE_PAYLOAD"))
        self.assertEqual(code, 1)
        self.assert_rejection(output, "unavailable", "validation_value")
        runner.assert_called_once()
        with patch.object(api, "_set_diagnostic_stage", side_effect=OSError("PRIVATE_PAYLOAD")):
            code, output, runner = self.diagnostic_main()
        self.assertEqual(code, 0)
        self.assertNotIn("rejection=", output)
        runner.assert_called_once()

    def test_diagnostic_reset_fault_drops_slot_and_inaccessible_stage_has_no_credit(self):
        api = self.diagnostic_api()
        observer = api._ProbeDiagnostic()
        observer.stage = "context_read"
        reset = SimpleNamespace(__setattr__=unittest.mock.Mock(side_effect=OSError("PRIVATE_PAYLOAD")),
                                __delattr__=object.__delattr__)
        with patch.object(api, "_set_diagnostic_stage", side_effect=ValueError("PRIVATE_PAYLOAD")), \
                patch.object(api, "object", reset, create=True):
            api._mark_diagnostic_stage(observer, "query")
        self.assertEqual(api._get_diagnostic_stage(observer), "unavailable")
        api._mark_diagnostic_stage(observer, "query")
        self.assertEqual(api._get_diagnostic_stage(observer), "query")
        def inaccessible(instance):
            raise OSError("PRIVATE_PAYLOAD")
        with patch.object(api._ProbeDiagnostic, "stage", property(inaccessible)):
            api._mark_diagnostic_stage(observer, "tool_directory")
            self.assertEqual(api._get_diagnostic_stage(observer), "unavailable")
        api._mark_diagnostic_stage(observer, "query_result")
        self.assertEqual(api._get_diagnostic_stage(observer), "query_result")

    def test_diagnostic_factory_fault_preserves_success_and_failure_once(self):
        api = self.diagnostic_api()
        with patch.object(api, "_new_diagnostic", side_effect=OSError("PRIVATE_PAYLOAD")):
            code, output, runner = self.diagnostic_main()
        self.assertEqual(code, 0)
        self.assertNotIn("rejection=", output)
        runner.assert_called_once()
        with patch.object(api, "_new_diagnostic", side_effect=OSError("PRIVATE_PAYLOAD")):
            code, output, runner = self.diagnostic_main(effect=RuntimeError("PRIVATE_PAYLOAD"))
        self.assertEqual(code, 1)
        self.assert_rejection(output, "unavailable", "validation_runtime")
        runner.assert_called_once()

    def test_diagnostic_main_instances_are_fresh_after_a_previous_rejection(self):
        api = self.diagnostic_api()
        observers = []
        def factory():
            observer = api._ProbeDiagnostic()
            observers.append(observer)
            return observer
        with patch.object(api, "_new_diagnostic", side_effect=factory) as created:
            first_code, first_output, first_runner = self.diagnostic_main(effect=ValueError("PRIVATE_PAYLOAD"))
            self.context.write_bytes(b"{")
            second_code, second_output, second_runner = self.diagnostic_main()
        self.assertEqual(created.call_count, 2)
        self.assertEqual((first_code, second_code), (1, 1))
        self.assertIsNot(observers[0], observers[1])
        self.assert_rejection(first_output, "query", "validation_value")
        self.assert_rejection(second_output, "context_validate", "validation_value")
        self.assertEqual((observers[0].stage, observers[1].stage), ("query", "context_validate"))
        first_runner.assert_called_once()
        second_runner.assert_not_called()

    def test_diagnostic_get_stage_and_kind_faults_use_unavailable_without_retry(self):
        api = self.diagnostic_api()
        observer = api._ProbeDiagnostic()
        observer.stage = "query"
        def bad_getattribute(instance, name):
            raise OSError("PRIVATE_PAYLOAD")
        with patch.object(api._ProbeDiagnostic, "__getattribute__", bad_getattribute), \
                patch.object(api, "_new_diagnostic", return_value=observer):
            code, output, runner = self.diagnostic_main(effect=ValueError("PRIVATE_PAYLOAD"))
        self.assertEqual(code, 1)
        self.assert_rejection(output, "unavailable", "validation_value")
        runner.assert_called_once()
        for value in ("PRIVATE_PAYLOAD", None, 1):
            with patch.object(api, "_failure_kind", return_value=value):
                code, output, runner = self.diagnostic_main(effect=ValueError("PRIVATE_PAYLOAD"))
            self.assertEqual(code, 1)
            self.assert_rejection(output, "query", "unavailable")
            runner.assert_called_once()
        with patch.object(api, "_failure_kind", side_effect=RuntimeError("PRIVATE_PAYLOAD")):
            code, output, runner = self.diagnostic_main(effect=ValueError("PRIVATE_PAYLOAD"))
        self.assertEqual(code, 1)
        self.assert_rejection(output, "query", "unavailable")
        runner.assert_called_once()

    def test_diagnostic_closed_payload_all_stage_kind_pairs_fit_ascii_budget(self):
        api = self.diagnostic_api()
        observer = api._ProbeDiagnostic()
        for stage in sorted(api._STAGES):
            observer.stage = stage
            for kind in sorted(api._FAILURE_KINDS):
                with self.subTest(stage=stage, kind=kind), \
                        patch.object(api, "_failure_kind", return_value=kind):
                    line = api._rejection_line(observer, ValueError("PRIVATE_PAYLOAD"))
                self.assertIs(type(line), str)
                self.assert_rejection("::error::windows_build_context_probe_failed\n" + line, stage, kind)
        class StringSubclass(str):
            pass
        with patch.object(api, "_failure_kind", return_value=StringSubclass("timeout")):
            line = api._rejection_line(observer, ValueError("PRIVATE_PAYLOAD"))
        self.assert_rejection("::error::windows_build_context_probe_failed\n" + line,
                              observer.stage, "unavailable")

    def test_diagnostic_serialization_and_single_write_fault_preserve_original_failure(self):
        api = self.diagnostic_api()
        for failure in (OSError("PRIVATE_PAYLOAD"), ValueError("PRIVATE_PAYLOAD")):
            with patch.object(api.json, "dumps", side_effect=failure) as serializer:
                code, output, runner = self.diagnostic_main(effect=RuntimeError("PRIVATE_PAYLOAD"))
            self.assertEqual((code, output), (1, "::error::windows_build_context_probe_failed\n"))
            serializer.assert_called_once()
            runner.assert_called_once()
        class BrokenDiagnosticStream(io.StringIO):
            def __init__(self):
                super().__init__()
                self.attempts = 0
            def write(self, value):
                if value.startswith("windows-build-context rejection="):
                    self.attempts += 1
                    raise OSError("PRIVATE_PAYLOAD")
                return super().write(value)
        output = BrokenDiagnosticStream()
        code, text, runner = self.diagnostic_main(effect=ValueError("PRIVATE_PAYLOAD"), stream=output)
        self.assertEqual((code, text), (1, "::error::windows_build_context_probe_failed\n"))
        self.assertEqual(output.attempts, 1)
        runner.assert_called_once()
        class PartialDiagnosticStream(BrokenDiagnosticStream):
            def write(self, value):
                if value.startswith("windows-build-context rejection="):
                    self.attempts += 1
                    io.StringIO.write(self, value[:12])
                    raise OSError("PRIVATE_PAYLOAD")
                return io.StringIO.write(self, value)
        partial = PartialDiagnosticStream()
        code, text, runner = self.diagnostic_main(effect=ValueError("PRIVATE_PAYLOAD"), stream=partial)
        self.assertEqual(code, 1)
        self.assertEqual(text, "::error::windows_build_context_probe_failed\nwindows-buil")
        self.assertEqual(partial.attempts, 1)
        runner.assert_called_once()
        class RecordingStream(io.StringIO):
            def __init__(self):
                super().__init__()
                self.lines = []
            def write(self, value):
                if value.startswith("windows-build-context rejection="):
                    self.lines.append(value)
                return super().write(value)
        output = RecordingStream()
        code, text, runner = self.diagnostic_main(effect=ValueError("PRIVATE_PAYLOAD"), stream=output)
        self.assertEqual(code, 1)
        self.assertEqual(len(output.lines), 1)
        self.assert_rejection(text, "query", "validation_value")
        self.assertTrue(output.lines[0].endswith("\n"))
        runner.assert_called_once()

    def test_diagnostic_invalid_serialized_line_is_not_truncated_or_written(self):
        api = self.diagnostic_api()
        class RecordingStream(io.StringIO):
            def __init__(self):
                super().__init__()
                self.attempts = 0
            def write(self, value):
                if value.startswith("windows-build-context rejection="):
                    self.attempts += 1
                return super().write(value)
        for serialized in ("x" * 257, "工具", 1, None, "{}", "[]", "not-json",
                           '{"schema_version":true,"stage":"query","failure_kind":"validation_value","production_authority":"none"}',
                           '{"schema_version":1,"stage":"PRIVATE_PAYLOAD","failure_kind":"validation_value","production_authority":"none"}',
                           '{"schema_version":1,"stage":"query","failure_kind":"validation_value","production_authority":"none","extra":1}',
                           '{"schema_version":1,"schema_version":1,"stage":"query","failure_kind":"validation_value","production_authority":"none"}'):
            stream = RecordingStream()
            with patch.object(api.json, "dumps", return_value=serialized) as serializer:
                code, output, runner = self.diagnostic_main(effect=ValueError("PRIVATE_PAYLOAD"), stream=stream)
            self.assertEqual((code, output), (1, "::error::windows_build_context_probe_failed\n"))
            self.assertEqual(stream.attempts, 0)
            serializer.assert_called_once()
            runner.assert_called_once()

    def test_diagnostic_serialized_whitespace_is_rejected_before_any_diagnostic_write(self):
        api = self.diagnostic_api()
        compact = ('{"schema_version":1,"stage":"query","failure_kind":"validation_value",'
                   '"production_authority":"none"}')
        cases = [("trailing_cr", compact + "\r"), ("trailing_lf", compact + "\n"),
                 ("trailing_space", compact + " "), ("trailing_tab", compact + "\t"),
                 ("token_lf", compact.replace(",", ",\n", 1)),
                 ("token_cr", compact.replace(",", ",\r", 1)),
                 ("token_tab", compact.replace(",", ",\t", 1)),
                 ("token_spaces", compact.replace(":", ":  ", 1))]
        class RecordingStream(io.StringIO):
            def __init__(self):
                super().__init__()
                self.attempts = 0
            def write(self, value):
                if value.startswith("windows-build-context rejection="):
                    self.attempts += 1
                return super().write(value)
        for name, serialized in cases:
            with self.subTest(name=name):
                self.assertLessEqual(len((api._REJECTION_PREFIX + serialized + "\n").encode("ascii")), 256)
                self.assertEqual(json.loads(serialized), dict(schema_version=1, stage="query",
                    failure_kind="validation_value", production_authority="none"))
                stream = RecordingStream()
                with patch.object(api.json, "dumps", return_value=serialized) as serializer:
                    code, output, runner = self.diagnostic_main(effect=ValueError("PRIVATE_PAYLOAD"), stream=stream)
                self.assertEqual((code, output), (1, "::error::windows_build_context_probe_failed\n"))
                self.assertEqual(stream.attempts, 0)
                serializer.assert_called_once()
                runner.assert_called_once()

    def test_diagnostic_fatal_faults_propagate_from_every_protected_boundary(self):
        api = self.diagnostic_api()
        class FatalStream(io.StringIO):
            def __init__(self, error):
                super().__init__()
                self.error = error
            def write(self, value):
                if value.startswith("windows-build-context rejection="):
                    raise self.error
                return super().write(value)
        for error_type in (MemoryError, KeyboardInterrupt, SystemExit):
            for boundary in ("_new_diagnostic", "_set_diagnostic_stage", "_failure_kind", "serialize", "write"):
                error = error_type("PRIVATE_PAYLOAD")
                with self.subTest(error_type=error_type.__name__, boundary=boundary):
                    with ExitStack() as stack:
                        stream = None
                        if boundary == "serialize":
                            stack.enter_context(patch.object(api.json, "dumps", side_effect=error))
                        elif boundary == "write":
                            stream = FatalStream(error)
                        else:
                            stack.enter_context(patch.object(api, boundary, side_effect=error))
                        with self.assertRaises(error_type) as raised:
                            self.diagnostic_main(effect=ValueError("PRIVATE_PAYLOAD"), stream=stream)
                    self.assertIs(raised.exception, error)
            observer = api._ProbeDiagnostic()
            error = error_type("PRIVATE_PAYLOAD")
            def fatal_getattribute(instance, name):
                raise error
            with patch.object(api._ProbeDiagnostic, "__getattribute__", fatal_getattribute):
                with self.assertRaises(error_type) as raised:
                    api._get_diagnostic_stage(observer)
            self.assertIs(raised.exception, error)
            error = error_type("PRIVATE_PAYLOAD")
            with self.assertRaises(error_type) as raised:
                self.diagnostic_main(effect=error)
            self.assertIs(raised.exception, error)

    def test_diagnostic_original_generic_write_failure_still_propagates(self):
        error = OSError("PRIVATE_PAYLOAD")
        class BrokenGenericStream(io.StringIO):
            def write(self, value):
                if value.startswith("::error::"):
                    raise error
                return super().write(value)
        with self.assertRaises(OSError) as raised:
            self.diagnostic_main(effect=ValueError("PRIVATE_PAYLOAD"), stream=BrokenGenericStream())
        self.assertIs(raised.exception, error)

    def test_diagnostic_old_two_arguments_runner_exception_identity_and_no_observer_factory(self):
        api = self.diagnostic_api()
        output = io.StringIO()
        with patch.object(api, "_new_diagnostic", side_effect=AssertionError("old API creates observer")), \
                redirect_stdout(output):
            receipt, runner = self.invoke()
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(receipt["architecture"], "x64")
        runner.assert_called_once()
        for error in (api.VerificationOutputCaptureError("PRIVATE_PAYLOAD"),
                      api.VerificationOutputLimitError(16384),
                      subprocess.TimeoutExpired("PRIVATE_PAYLOAD", 30),
                      TypeError("PRIVATE_PAYLOAD"), AssertionError("PRIVATE_PAYLOAD")):
            with patch.object(api.sys, "platform", "win32"), \
                    patch.object(Path, "lstat", lambda path, *a, **k: self.windows_lstat(path, *a, **k)), \
                    patch.object(api, "_run_unittest_with_bounded_output", side_effect=error) as runner, \
                    redirect_stdout(output):
                with self.assertRaises(type(error)) as raised:
                    api.probe(self.root, "x64")
            self.assertIs(raised.exception, error)
            self.assertEqual(output.getvalue(), "")
            runner.assert_called_once()

    def test_diagnostic_exact_side_effects_match_old_call_without_extra_reads_or_queries(self):
        api = self.diagnostic_api()
        snapshots = []
        for observed in (False, True):
            events = []
            old_read, old_json, old_project = api._read_regular, api._json, api._project_selection
            def lstat(path, *args, **kwargs):
                events.append(("lstat", str(path)))
                return self.windows_lstat(path, *args, **kwargs)
            def read(path, limit):
                events.append(("read", str(path), limit))
                return old_read(path, limit)
            def decode(raw):
                events.append(("json", raw))
                return old_json(raw)
            def project(raw, platform):
                events.append(("project", raw, platform))
                return old_project(raw, platform)
            with patch.object(api.sys, "platform", "win32"), patch.object(Path, "lstat", lstat), \
                    patch.object(api, "_read_regular", read), patch.object(api, "_json", decode), \
                    patch.object(api, "_project_selection", project), \
                    patch.object(api, "_run_unittest_with_bounded_output", return_value=self.result()) as runner:
                kwargs = {"_diagnostic": api._ProbeDiagnostic()} if observed else {}
                receipt = api.probe(self.root, "x64", **kwargs)
            snapshots.append((receipt, events, runner.call_args))
            runner.assert_called_once()
            self.assertEqual([event[1] for event in events if event[0] == "lstat"],
                [str(self.root), str(self.context), str(Path(self.metadata["msbuild"])),
                 str(self.project), *(str(Path(self.properties[key])) for key in
                     ("VCToolsInstallDir", "WindowsSdkDir", "MSBuildToolsPath"))])
            self.assertEqual(len([event for event in events if event[0] == "read"]), 2)
            self.assertEqual(len([event for event in events if event[0] == "json"]), 2)
            self.assertEqual(len([event for event in events if event[0] == "project"]), 1)
            self.assertEqual(runner.call_args.kwargs, dict(workspace=self.root, timeout=30,
                output_limit_bytes=16384, environment=os.environ.copy()))
        self.assertEqual(snapshots[0], snapshots[1])
        import inspect
        source = "\n".join(inspect.getsource(getattr(api, name)) for name in
            ("_new_diagnostic", "_set_diagnostic_stage", "_mark_diagnostic_stage",
             "_get_diagnostic_stage", "_failure_kind", "_rejection_line", "_emit_rejection"))
        for forbidden in ("lstat(", ".open(", ".read(", "_run_unittest_with_bounded_output(",
                          "time.", "threading.", "subprocess.run(", "sleep(", "retry"):
            self.assertNotIn(forbidden, source)

    def test_diagnostic_two_architectures_main_success_preserves_exact_original_two_lines(self):
        for arch, platform in (("x64", "x64"), ("arm64", "ARM64")):
            with self.subTest(arch=arch):
                self.metadata["platform"] = self.properties["Platform"] = platform
                self.write_context(self.metadata)
                self.project.write_bytes(self.xml(platform))
                receipt = dict(schema_version=1, architecture=arch,
                    **{key: self.metadata[key] for key in ("generator", "toolset", "sdk_version", "msbuild")},
                    **{key: self.properties[key] for key in ("VCToolsInstallDir", "WindowsSdkDir", "MSBuildToolsPath")})
                code, output, runner = self.diagnostic_main(arch=arch)
                self.assertEqual((code, output), (0,
                    "windows-build-context status=PASS production_authority=none\n"
                    + "windows-build-context receipt="
                    + json.dumps(receipt, separators=(",", ":"), ensure_ascii=True) + "\n"))
                self.assertNotIn("rejection=", output)
                runner.assert_called_once()

    def test_diagnostic_cli_errors_exit_two_before_probe_or_factory(self):
        api = self.diagnostic_api()
        cases = ([], ["--build-directory", str(self.root)],
            ["--build-directory", str(self.root), "--architecture", "x86"],
            ["--build-dir", str(self.root), "--architecture", "x64"],
            ["--build-directory", str(self.root), "--architecture", "x64", "--extra"],
            ["--build-directory", str(self.root), "--architecture", "ARM64"])
        for flags in cases:
            with self.subTest(flags=flags), patch.object(sys, "argv", ["probe", *flags]), \
                    patch.object(api, "probe") as probe, patch.object(api, "_new_diagnostic") as factory, \
                    patch.object(sys, "stderr", io.StringIO()), redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    api.main()
                self.assertEqual(raised.exception.code, 2)
                probe.assert_not_called()
                factory.assert_not_called()


class TestWindowsBuildContextHostCMake(unittest.TestCase):
    """Synthetic project(NONE) serialization; no actual VS/compiler credit."""

    def setUp(self):
        self.cmake = shutil.which("cmake")
        self.assertIsNotNone(self.cmake, "host CMake required for explicit class")
        temporary = tempfile.TemporaryDirectory(prefix="icode-context-cmake-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.msbuild = self.root / "工具 MSBuild.exe"
        self.msbuild.write_bytes(b"owned synthetic tool; never executed")
        source = (ROOT / "native/windows/CMakeLists.txt").read_text()
        self.assertEqual(source.count(MARKER), 1)
        self.block = source.split(MARKER, 1)[1]

    def configure(self, **overrides):
        values = dict(ICODE_BUILD_WINDOWS_BOOTSTRAP="ON", MSVC="TRUE", CMAKE_GENERATOR="Visual Studio 17 2022",
            CMAKE_GENERATOR_PLATFORM="x64", CMAKE_VS_PLATFORM_TOOLSET="v143",
            CMAKE_VS_WINDOWS_TARGET_PLATFORM_VERSION="10.0.22621.0", CMAKE_VS_MSBUILD_COMMAND=str(self.msbuild),
            ICODE_WINDOWS_BUILD_CONTEXT_DIAGNOSTIC="ON")
        values.update(overrides)
        src = Path(tempfile.mkdtemp(dir=self.root, prefix="source-"))
        build = Path(tempfile.mkdtemp(dir=self.root, prefix="build-"))
        lines = ['cmake_minimum_required(VERSION 3.20)', 'project(context_test NONE)']
        lines.extend(f'set({key} [==[{value}]==])' for key, value in values.items() if value is not None)
        (src / "CMakeLists.txt").write_text("\n".join(lines) + "\n" + MARKER + self.block, encoding="utf-8")
        result = subprocess.run([self.cmake, "-S", str(src), "-B", str(build)], capture_output=True,
            timeout=30, env=dict(os.environ, CMAKE_BUILD_PARALLEL_LEVEL="1"))
        return result, build

    def test_on_exact_fields_unicode_quotes_backslashes_two_platforms(self):
        for platform in ("x64", "ARM64"):
            result, build = self.configure(CMAKE_GENERATOR_PLATFORM=platform, CMAKE_VS_PLATFORM_TOOLSET='v143工具"\\suffix')
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            data = json.loads((build / "icode-windows-build-context.json").read_bytes().decode("utf-8"))
            self.assertEqual(data, dict(schema_version=1, generator="Visual Studio 17 2022", platform=platform,
                toolset='v143工具"\\suffix', sdk_version="10.0.22621.0", msbuild=str(self.msbuild)))

    def test_owned_unicode_tool_filename_is_legal_on_windows(self):
        self.assertTrue(self.msbuild.is_file())
        self.assertIn("工具", self.msbuild.name)
        self.assertFalse(set(self.msbuild.name) & set('<>:"/\\|?*'))
        self.assertFalse(self.msbuild.name.endswith((" ", ".")))

    def test_off_and_default_generate_nothing(self):
        for value in ("OFF", None):
            result, build = self.configure(ICODE_WINDOWS_BUILD_CONTEXT_DIAGNOSTIC=value, MSVC="FALSE",
                CMAKE_VS_MSBUILD_COMMAND="MSBuild.exe")
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            self.assertFalse((build / "icode-windows-build-context.json").exists())

    def test_on_missing_selection_relative_missing_directory_tools_and_controls_fail(self):
        cases = [dict(ICODE_BUILD_WINDOWS_BOOTSTRAP="OFF"), dict(MSVC="FALSE"), dict(CMAKE_GENERATOR="Ninja"),
            dict(CMAKE_GENERATOR_PLATFORM=""), dict(CMAKE_GENERATOR_PLATFORM="Win32"), dict(CMAKE_VS_PLATFORM_TOOLSET=""),
            dict(CMAKE_VS_WINDOWS_TARGET_PLATFORM_VERSION=""), dict(CMAKE_VS_MSBUILD_COMMAND="MSBuild.exe"),
            dict(CMAKE_VS_MSBUILD_COMMAND=str(self.root)), dict(CMAKE_VS_MSBUILD_COMMAND=str(self.root / "missing"))]
        for key in ("CMAKE_GENERATOR", "CMAKE_GENERATOR_PLATFORM", "CMAKE_VS_PLATFORM_TOOLSET",
                    "CMAKE_VS_WINDOWS_TARGET_PLATFORM_VERSION", "CMAKE_VS_MSBUILD_COMMAND"):
            cases.append({key: None})
            for control in ("\n", "\x01", "\x7f", "\x85"):
                cases.append({key: "bad" + control})
        for index, values in enumerate(cases):
            with self.subTest(index=index):
                result, build = self.configure(**values)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((build / "icode-windows-build-context.json").exists())
