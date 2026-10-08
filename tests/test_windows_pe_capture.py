import importlib.util
import base64
from contextlib import ExitStack, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path, PureWindowsPath
import stat
import struct
import subprocess
import sys
import sysconfig
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from scripts.probe_windows_build_context import _read_regular as real_read_regular
from icode.runner import _run_unittest_with_bounded_output as real_runner

IMAGE_LIMIT = 8 * 1024 * 1024
OUTPUT = b'\x80raw imports\r\n'
MANIFEST = b'\xffraw manifest'
EXPECTED_ERRORS = (OSError, UnicodeError, ValueError, RuntimeError, ET.ParseError,
                   subprocess.SubprocessError)


class TestWindowsPeCapture(unittest.TestCase):
    """Portable admission controls; synthetic PE and Windows tools carry no native credit."""

    def test_capture_interface_exists(self):
        found = importlib.util.find_spec('scripts.probe_windows_pe_capture')
        self.assertIsNotNone(found, 'CI PE capture implementation is required')
        if found is not None:
            module = __import__('scripts.probe_windows_pe_capture', fromlist=['capture'])
            self.assertTrue(callable(getattr(module, 'capture', None)))

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='icode-pe-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        (self.root / 'Release').mkdir()
        (self.root / 'tools').mkdir()
        self.real_lstat = Path.lstat
        self.calls = []
        self.configure('x64')

    @property
    def api(self):
        # Keep the seed's missing-module assertion reachable before importing.
        import scripts.probe_windows_pe_capture as api
        return api

    @staticmethod
    def image(arch):
        raw = bytearray(128)
        raw[:2] = b'MZ'
        struct.pack_into('<I', raw, 0x3c, 64)
        raw[64:68] = b'PE\0\0'
        struct.pack_into('<H', raw, 68, {'x64': 0x8664, 'arm64': 0xaa64}[arch])
        return bytes(raw)

    def configure(self, arch):
        self.arch = arch
        self.context = dict(schema_version=1, architecture=arch, generator='Visual Studio 17 2022',
            toolset='v143', sdk_version='10.0.22621.0', msbuild='C:\\Build Tools\\MSBuild.exe',
            VCToolsInstallDir='C:\\工具\\VC\\', WindowsSdkDir='C:\\SDK\\',
            MSBuildToolsPath='C:\\Build Tools\\')
        self.target = self.root / 'Release' / f'icode-sandbox-windows-{arch}.exe'
        self.target.write_bytes(self.image(arch))
        self.dumpbin = PureWindowsPath(self.context['VCToolsInstallDir']) / 'bin' / ('Host' + arch) / arch / 'dumpbin.exe'
        self.mt = PureWindowsPath(self.context['WindowsSdkDir']) / 'bin' / self.context['sdk_version'] / arch / 'mt.exe'
        self.tools = {}
        # Only Windows logical path resolution is mocked. File reads, lengths,
        # metadata and raw bytes use legal, owned fixtures on every host.
        for tool in (self.dumpbin, self.mt):
            backing = self.root / 'tools' / tool.name
            raw = bytearray(self.image(arch))
            raw[-len(tool.name):] = tool.name.encode('ascii')
            backing.write_bytes(raw)
            self.tools[tool] = backing

    def read_regular(self, path, limit):
        return real_read_regular(self.tools.get(PureWindowsPath(path), path), limit)

    def runner(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        if argv[0] == str(self.dumpbin):
            return 0, OUTPUT, b''
        self.assertEqual(argv[0], str(self.mt), 'only the two selected tools may execute')
        Path(argv[3].removeprefix('-out:')).write_bytes(MANIFEST)
        return 0, b'', b''

    def invoke(self, *, platform='win32', compiled=None, context=None, read=None, runner=None,
               env=None, bad=False, count=None, context_error=None):
        self.calls = []
        with ExitStack() as stack:
            stack.enter_context(patch.object(self.api, 'sys', sys, create=True))
            stack.enter_context(patch.object(sys, 'platform', platform))
            stack.enter_context(patch.object(self.api, 'sysconfig', sysconfig, create=True))
            stack.enter_context(patch.object(sysconfig, 'get_platform', return_value=compiled or 'win-' + ('amd64' if self.arch == 'x64' else 'arm64')))
            probe = stack.enter_context(patch.object(self.api, '_probe_context',
                return_value=dict(self.context) if context is None else context,
                side_effect=context_error, create=True))
            stack.enter_context(patch.object(self.api, '_read_regular', side_effect=read or self.read_regular, create=True))
            execution = stack.enter_context(patch.object(self.api, '_run_unittest_with_bounded_output', side_effect=runner or self.runner, create=True))
            stack.enter_context(patch.dict(os.environ, {'SystemRoot': 'C:\\Windows', 'WINDIR': 'C:\\Windows', 'PATH': 'PRIVATE',
                'INCLUDE': 'PRIVATE', 'LIB': 'PRIVATE', 'MODEL_SECRET': 'PRIVATE'} if env is None else env, clear=True))
            if bad:
                try:
                    self.api.capture(self.root, self.arch)
                except Exception as error:
                    self.assertIsInstance(error, EXPECTED_ERRORS, 'failure must use the public expected error protocol')
                else:
                    self.fail('unsafe capture returned a successful receipt')
                if count is not None:
                    self.assertEqual(execution.call_count, count)
                return
            result = self.api.capture(self.root, self.arch)
        return result, execution, probe

    def test_two_architectures_exact_nopdb_argv_receipt_bytes_and_owned_cleanup(self):
        for arch in ('x64', 'arm64'):
            with self.subTest(arch=arch):
                self.configure(arch)
                receipt, execution, probe = self.invoke()
                digest = hashlib.sha256(self.image(arch)).hexdigest()
                self.assertEqual(receipt, dict(schema_version=1, architecture=arch, build_context=self.context,
                    helper_sha256=digest, dumpbin=dict(path=str(self.dumpbin),
                        sha256=hashlib.sha256(self.tools[self.dumpbin].read_bytes()).hexdigest()),
                    mt=dict(path=str(self.mt), sha256=hashlib.sha256(self.tools[self.mt].read_bytes()).hexdigest()),
                    dumpbin_stdout_base64=base64.b64encode(OUTPUT).decode('ascii'),
                    manifest_base64=base64.b64encode(MANIFEST).decode('ascii'), parse_complete=False,
                    runtime_load_verified=False, source_launch_verified=False))
                probe.assert_called_once_with(self.root, arch)
                self.assertEqual(execution.call_count, 2)
                first, second = self.calls
                owned = first[1]['workspace']
                self.assertEqual(owned.parent, self.root)
                self.assertTrue(owned.name.startswith('icode-pe-capture-'))
                self.assertEqual(second[1]['workspace'], owned)
                self.assertEqual(first[0], [str(self.dumpbin), '/nopdb', '/imports', str(self.target)])
                self.assertEqual(second[0], [str(self.mt), '-nologo', '-inputresource:' + str(self.target) + ';#1', '-out:' + str(owned / 'manifest.xml')])
                for _, options in self.calls:
                    self.assertEqual(options, dict(workspace=owned, timeout=30, output_limit_bytes=16384,
                        environment=dict(SystemRoot='C:\\Windows', WINDIR='C:\\Windows', TEMP=str(owned), TMP=str(owned))))
                self.assertFalse(owned.exists())
                self.assertEqual(base64.b64decode(receipt['dumpbin_stdout_base64']), OUTPUT)
                self.assertEqual(base64.b64decode(receipt['manifest_base64']), MANIFEST)

    def test_platform_requested_and_python_compiled_architecture_reject_before_tools(self):
        for platform, compiled, requested in (('linux', 'win-amd64', 'x64'),
                ('win32', 'win-arm64', 'x64'), ('win32', 'win-amd64', 'arm64'),
                ('win32', 'linux-x86_64', 'x64'), ('win32', 'win32', 'x64'),
                ('win32', 'win-amd64', 'ARM64'), ('win32', 'win-amd64', 'x86')):
            with self.subTest(platform=platform, compiled=compiled, requested=requested):
                self.arch = requested
                self.invoke(platform=platform, compiled=compiled, bad=True, count=0)

    def test_context_closed_nine_fields_strict_schema_strings_architecture_and_roots(self):
        cases = [dict(self.context, extra='PRIVATE'), [], {}, True]
        cases += [dict(self.context, schema_version=value) for value in (True, 1.0, 0, 2, '1')]
        cases += [dict(self.context, architecture='arm64')]
        for key in self.context:
            missing = dict(self.context)
            del missing[key]
            cases.append(missing)
            if key != 'schema_version':
                cases += [dict(self.context, **{key: value}) for value in ('', None, 1)]
        for key in ('VCToolsInstallDir', 'WindowsSdkDir'):
            cases += [dict(self.context, **{key: value}) for value in ('relative', 'C:relative', '\\relative')]
        for case in cases:
            with self.subTest(context=case):
                self.invoke(context=case, bad=True, count=0)

    def test_sdk_four_ascii_decimal_segments_reject_traversal_and_unicode(self):
        for value in ('../10.0.1.0', '10.0.1.0/..', '10.0.1', '10.0.1.0.0',
                      '１０.0.1.0', '10.0.-1.0', '10.0.1.0\n', '10.0.1.0\\x', '10..1.0'):
            with self.subTest(sdk=value):
                self.invoke(context=dict(self.context, sdk_version=value), bad=True, count=0)

    def test_missing_or_empty_system_roots_reject_before_tools(self):
        for env in ({}, {'WINDIR': 'C:\\Windows'}, {'SystemRoot': 'C:\\Windows'},
                    {'SystemRoot': '', 'WINDIR': 'C:\\Windows'},
                    {'SystemRoot': 'C:\\Windows', 'WINDIR': ''}):
            with self.subTest(env=env):
                self.invoke(env=env, bad=True, count=0)

    def test_three_images_each_reject_missing_directory_link_empty_oversize_and_machine(self):
        for selected in (self.target, *self.tools.values()):
            for kind in ('missing', 'directory', 'link', 'empty', 'oversize', 'wrong-machine', 'malformed', 'size-change'):
                with self.subTest(path=selected.name, kind=kind), ExitStack() as stack:
                    original = selected.read_bytes()
                    if kind in ('missing', 'directory'):
                        selected.unlink()
                        if kind == 'directory':
                            selected.mkdir()
                    elif kind in ('empty', 'oversize', 'wrong-machine', 'malformed'):
                        selected.write_bytes({'empty': b'', 'oversize': b'x' * (IMAGE_LIMIT + 1),
                            'wrong-machine': self.image('arm64'), 'malformed': b'not PE'}[kind])
                    else:
                        def metadata(path, *args, **kwargs):
                            info = self.real_lstat(path, *args, **kwargs)
                            if path == selected:
                                return SimpleNamespace(st_mode=stat.S_IFLNK if kind == 'link' else info.st_mode,
                                    st_size=info.st_size + (kind == 'size-change'))
                            return info
                        stack.enter_context(patch.object(Path, 'lstat', metadata))
                    try:
                        self.invoke(bad=True, count=0)
                    finally:
                        if kind == 'directory':
                            selected.rmdir()
                        selected.write_bytes(original)

    def test_image_reads_use_the_existing_bounded_reader_without_hardlink_policy(self):
        counts = []
        def read(path, limit):
            counts.append((path, limit))
            return self.read_regular(path, limit)
        self.invoke(read=read)
        self.assertEqual(counts[:3], [(self.target, IMAGE_LIMIT), (Path(str(self.dumpbin)), IMAGE_LIMIT),
                                     (Path(str(self.mt)), IMAGE_LIMIT)])
        for owned in (self.target, *self.tools.values()):
            info = self.real_lstat(owned)
            # No extra nlink policy: supplying nlink=2 cannot reject a regular PE.
            def metadata(path, *args, **kwargs):
                if path == owned:
                    return SimpleNamespace(st_mode=info.st_mode, st_size=info.st_size, st_nlink=2)
                return self.real_lstat(path, *args, **kwargs)
            with patch.object(Path, 'lstat', metadata):
                self.invoke()

    def test_runner_each_stage_strict_tuple_exit_bytes_stderr_and_combined_budget(self):
        cases = [None, [0, OUTPUT, b''], (0, OUTPUT), (0, OUTPUT, b'', b''),
            (True, OUTPUT, b''), (0.0, OUTPUT, b''), (1, OUTPUT, b'PRIVATE'),
            (0, 'PRIVATE', b''), (0, bytearray(OUTPUT), b''), (0, OUTPUT, ''),
            (0, OUTPUT, b'PRIVATE'), (0, b'x' * 16385, b''), (0, b'x' * 16384, b'x')]
        for stage in ('dumpbin', 'mt'):
            for index, result in enumerate(cases + ([(0, b'', b'')] if stage == 'dumpbin' else [])):
                with self.subTest(stage=stage, case=index):
                    def execute(argv, **kwargs):
                        if argv[0] == str(self.dumpbin) and stage == 'dumpbin':
                            return result
                        normal = self.runner(argv, **kwargs)
                        return result if argv[0] == str(self.mt) else normal
                    self.invoke(runner=execute, bad=True, count=1 if stage == 'dumpbin' else 2)
                    self.assertFalse(any(path.name.startswith('icode-pe-capture-') for path in self.root.iterdir()))

    def test_manifest_missing_empty_directory_link_oversize_and_length_change_fail(self):
        for kind in ('missing', 'empty', 'directory', 'link', 'oversize', 'size-change'):
            with self.subTest(kind=kind), ExitStack() as stack:
                outputs = []
                def execute(argv, **kwargs):
                    if argv[0] == str(self.dumpbin):
                        return self.runner(argv, **kwargs)
                    output = Path(argv[3].removeprefix('-out:'))
                    outputs.append(output)
                    if kind == 'directory':
                        output.mkdir()
                    elif kind != 'missing':
                        output.write_bytes(b'' if kind == 'empty' else b'x' * 4097 if kind == 'oversize' else MANIFEST)
                    return 0, b'', b''
                def metadata(path, *args, **kwargs):
                    info = self.real_lstat(path, *args, **kwargs)
                    if path in outputs and kind in ('link', 'size-change'):
                        return SimpleNamespace(st_mode=stat.S_IFLNK if kind == 'link' else info.st_mode,
                            st_size=info.st_size + (kind == 'size-change'))
                    return info
                stack.enter_context(patch.object(Path, 'lstat', metadata))
                self.invoke(runner=execute, bad=True, count=2)
                self.assertFalse(outputs[0].parent.exists())

    def test_dumpbin_cannot_supply_a_preexisting_manifest_or_dangling_link(self):
        for kind in ('old-file', 'dangling-link'):
            with self.subTest(kind=kind):
                output_paths = []
                def execute(argv, **kwargs):
                    if argv[0] == str(self.dumpbin):
                        output = kwargs['workspace'] / 'manifest.xml'
                        output_paths.append(output)
                        if kind == 'old-file':
                            output.write_bytes(b'old PRIVATE')
                    return self.runner(argv, **kwargs)
                def metadata(path, *args, **kwargs):
                    if kind == 'dangling-link' and path in output_paths:
                        return SimpleNamespace(st_mode=stat.S_IFLNK, st_size=0)
                    return self.real_lstat(path, *args, **kwargs)
                with patch.object(Path, 'lstat', metadata):
                    self.invoke(runner=execute, bad=True, count=1)
                self.assertFalse(output_paths[0].parent.exists())

    def test_raw_non_xml_manifest_and_output_boundary_are_not_parsed_or_truncated(self):
        def execute(argv, **kwargs):
            result = self.runner(argv, **kwargs)
            if argv[0] == str(self.dumpbin):
                return 0, bytes(range(256)) * 64, b''
            Path(argv[3].removeprefix('-out:')).write_bytes(bytes(range(256)) * 16)
            return result
        receipt, _, _ = self.invoke(runner=execute)
        self.assertEqual(base64.b64decode(receipt['dumpbin_stdout_base64']), bytes(range(256)) * 64)
        self.assertEqual(base64.b64decode(receipt['manifest_base64']), bytes(range(256)) * 16)

    def test_three_images_same_size_changes_after_tools_and_second_read_errors_fail(self):
        for selected in (self.target, *self.tools.values()):
            for kind in ('same-size-change', 'read-error'):
                with self.subTest(path=selected.name, kind=kind):
                    original = selected.read_bytes()
                    reads = {}
                    def read(path, limit):
                        backing = self.tools.get(PureWindowsPath(path), path)
                        reads[backing] = reads.get(backing, 0) + 1
                        if backing == selected and reads[backing] == 2 and kind == 'read-error':
                            raise OSError('PRIVATE post-tool read')
                        return self.read_regular(path, limit)
                    def execute(argv, **kwargs):
                        result = self.runner(argv, **kwargs)
                        if argv[0] == str(self.mt) and kind == 'same-size-change':
                            selected.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
                        return result
                    try:
                        self.invoke(read=read, runner=execute, bad=True, count=2)
                    finally:
                        selected.write_bytes(original)

    def test_success_rereads_all_three_original_images_after_owned_cleanup(self):
        reads = []
        def read(path, limit):
            if len(reads) >= 4:
                self.assertFalse(self.calls[0][1]['workspace'].exists())
            reads.append((path, limit))
            return self.read_regular(path, limit)
        self.invoke(read=read)
        image_reads = [(self.target, IMAGE_LIMIT), (Path(str(self.dumpbin)), IMAGE_LIMIT), (Path(str(self.mt)), IMAGE_LIMIT)]
        self.assertEqual(reads[:3], image_reads)
        self.assertEqual(reads[3][1], 4096)
        self.assertEqual(reads[4:], image_reads)

    def test_context_runner_read_and_owned_cleanup_expected_exceptions_fail_closed(self):
        errors = (OSError('PRIVATE'), UnicodeError('PRIVATE'), ValueError('PRIVATE'), RuntimeError('PRIVATE'),
                  ET.ParseError('PRIVATE'), subprocess.TimeoutExpired('PRIVATE', 30),
                  subprocess.CalledProcessError(1, 'PRIVATE', b'PRIVATE', b'PRIVATE'))
        for error in errors:
            with self.subTest(origin='context', error=type(error).__name__):
                self.invoke(context_error=error, bad=True, count=0)
            for stage in ('dumpbin', 'mt'):
                with self.subTest(origin=stage, error=type(error).__name__):
                    def execute(argv, **kwargs):
                        if argv[0] == str(self.dumpbin if stage == 'dumpbin' else self.mt):
                            raise error
                        return self.runner(argv, **kwargs)
                    self.invoke(runner=execute, bad=True, count=1 if stage == 'dumpbin' else 2)
            with self.subTest(origin='initial-read', error=type(error).__name__):
                def read(path, limit):
                    raise error
                self.invoke(read=read, bad=True, count=0)
        cleanup = tempfile.TemporaryDirectory.cleanup
        def failed_cleanup(temporary):
            cleanup(temporary)
            raise OSError('PRIVATE cleanup')
        with patch.object(tempfile.TemporaryDirectory, 'cleanup', failed_cleanup):
            self.invoke(bad=True, count=2)
        self.assertFalse(self.calls[0][1]['workspace'].exists())

    def test_capture_control_flow_and_programming_exceptions_propagate(self):
        for error in (KeyboardInterrupt(), SystemExit(7), TypeError('bug'), AssertionError('bug')):
            for origin in ('context', 'dumpbin', 'mt'):
                with self.subTest(origin=origin, error=type(error).__name__):
                    def execute(argv, **kwargs):
                        if argv[0] == str(self.dumpbin if origin == 'dumpbin' else self.mt):
                            raise error
                        return self.runner(argv, **kwargs)
                    with self.assertRaises(type(error)):
                        self.invoke(context_error=error if origin == 'context' else None, runner=execute)
                    self.assertFalse(any(path.name.startswith('icode-pe-capture-') for path in self.root.iterdir()))

    def main_call(self, *, receipt=None, error=None, flags=None):
        self.assertTrue(callable(getattr(self.api, 'main', None)), 'fixed capture CLI is required')
        output = io.StringIO()
        argv = ['probe', '--build-directory', str(self.root), '--architecture', 'x64'] if flags is None else ['probe', *flags]
        with patch.object(sys, 'argv', argv), redirect_stdout(output), \
                patch.object(self.api, 'capture', return_value=receipt, side_effect=error) as capture:
            result = self.api.main()
        return result, output.getvalue(), capture

    def test_main_canonical_ascii_closed_receipt_and_public_reversible_bytes(self):
        receipt, _, _ = self.invoke()
        code, output, capture = self.main_call(receipt=receipt)
        canonical = json.dumps(receipt, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
        self.assertEqual((code, output), (0, 'windows-pe-capture status=CAPTURED production_authority=none\n'
            'windows-pe-capture receipt=' + canonical + '\n'))
        capture.assert_called_once_with(self.root, 'x64')
        self.assertTrue(output.isascii())
        self.assertEqual(json.loads(canonical), receipt)

    def test_capture_canonical_json_total_budget_rejects_without_truncation(self):
        self.invoke(context=dict(self.context, generator='工具' * 6000), bad=True, count=2)

    def test_main_budget_is_checked_before_captured_marker(self):
        code, output, _ = self.main_call(receipt={'public': '工具' * 6000})
        self.assertEqual((code, output), (1, '::error::windows_pe_capture_probe_failed\n'))
        self.assertNotIn('CAPTURED', output)

    def test_main_only_fixed_errors_and_no_private_exception_or_tool_output(self):
        for error in (OSError('PRIVATE'), UnicodeError('PRIVATE'), ValueError('PRIVATE'), RuntimeError('PRIVATE'),
                      ET.ParseError('PRIVATE'), subprocess.TimeoutExpired('PRIVATE', 30, b'PRIVATE', b'PRIVATE'),
                      subprocess.CalledProcessError(1, 'PRIVATE', b'PRIVATE', b'PRIVATE')):
            with self.subTest(error=type(error).__name__):
                code, output, _ = self.main_call(error=error)
                self.assertEqual((code, output), (1, '::error::windows_pe_capture_probe_failed\n'))
        for error in (TypeError('bug'), AssertionError('bug'), KeyboardInterrupt(), SystemExit(7)):
            with self.subTest(error=type(error).__name__), self.assertRaises(type(error)):
                self.main_call(error=error)

    def test_cli_unknown_abbreviated_missing_and_wrong_architecture_exit_two_before_capture(self):
        self.assertTrue(callable(getattr(self.api, 'main', None)), 'fixed capture CLI is required')
        for flags in (['--build-dir', str(self.root), '--architecture', 'x64'],
                      ['--build-directory', str(self.root), '--arch', 'x64'],
                      ['--build-directory', str(self.root), '--architecture', 'x64', '--target', 'x'],
                      ['--build-directory', str(self.root), '--architecture', 'x86'], []):
            with self.subTest(flags=flags), patch.object(sys, 'argv', ['probe', *flags]), \
                    patch.object(self.api, 'capture') as capture, patch.object(sys, 'stderr', io.StringIO()), \
                    redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    self.api.main()
                self.assertEqual(raised.exception.code, 2)
                capture.assert_not_called()

    def test_existing_bounded_runner_preserves_real_child_raw_bytes_and_rejects_combined_overflow(self):
        result = real_runner([sys.executable, '-B', '-c',
            "import os; os.write(1, b'\\x80raw\\r\\n'); os.write(2, b'\\xfferr')"],
            workspace=self.root, timeout=30, output_limit_bytes=16384, environment=os.environ.copy())
        self.assertEqual(result, (0, b'\x80raw\r\n', b'\xfferr'))
        with self.assertRaises(RuntimeError):
            real_runner([sys.executable, '-B', '-c',
                "import os; os.write(1, b'x'*10000); os.write(2, b'y'*10000)"],
                workspace=self.root, timeout=30, output_limit_bytes=16384, environment=os.environ.copy())

    def test_host_cli_negative_control_accepts_simulated_non_linux_parents_without_skips(self):
        # Parent platform and CLI subprocess are simulated here; this supplies
        # compatibility evidence only, not native macOS/Windows execution.
        for platform in ('darwin', 'win32'):
            with self.subTest(platform=platform):
                directories = []
                def fixed_failure(argv, **kwargs):
                    directory = Path(argv[4])
                    self.assertTrue(directory.is_dir())
                    self.assertTrue(directory.name.startswith('icode-pe-cli-'))
                    self.assertEqual(list(directory.iterdir()), [])
                    directories.append(str(directory))
                    return SimpleNamespace(returncode=1,
                        stdout=b'::error::windows_pe_capture_probe_failed\n', stderr=b'')
                with patch.object(sys, 'platform', platform), \
                        patch.object(subprocess, 'run', side_effect=fixed_failure) as execute:
                    case = TestWindowsPeCaptureHostCLI('test_empty_build_root_fixed_failure_without_windows_tools')
                    result = unittest.TestResult()
                    case.run(result)
                self.assertEqual((result.testsRun, result.failures, result.errors, result.skipped), (1, [], [], []))
                execute.assert_called_once_with([sys.executable, '-B', str(Path(self.api.__file__)),
                    '--build-directory', directories[0], '--architecture', 'x64'], capture_output=True, timeout=30)
                self.assertFalse(Path(directories[0]).exists())


class TestWindowsPeCaptureHostCLI(unittest.TestCase):
    """Actual CLI empty-build-root negative control; excluded from DEFAULT, no native tool credit."""

    def test_empty_build_root_fixed_failure_without_windows_tools(self):
        import scripts.probe_windows_pe_capture as api
        self.assertTrue(callable(getattr(api, 'main', None)), 'fixed capture CLI is required')
        with tempfile.TemporaryDirectory(prefix='icode-pe-cli-') as directory:
            result = subprocess.run([sys.executable, '-B', str(Path(api.__file__)),
                '--build-directory', directory, '--architecture', 'x64'], capture_output=True, timeout=30)
        self.assertEqual((result.returncode, result.stdout, result.stderr),
            (1, b'::error::windows_pe_capture_probe_failed\n', b''))
