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
from contextlib import redirect_stdout
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
        for error in (OSError("PRIVATE"), UnicodeError("PRIVATE"), ValueError("PRIVATE"), RuntimeError("PRIVATE"),
                      ET.ParseError("PRIVATE"), RecursionError("PRIVATE"),
                      subprocess.TimeoutExpired("PRIVATE", 30), subprocess.CalledProcessError(1, "PRIVATE")):
            self.assertEqual(self.main_call(error), (1, "::error::windows_build_context_probe_failed\n"))
        for error in (TypeError("bug"), AssertionError("bug"), KeyboardInterrupt(), SystemExit()):
            with self.assertRaises(type(error)):
                self.main_call(error)

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
