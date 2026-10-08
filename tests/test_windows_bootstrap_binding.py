"""Build binding software contracts, not native Windows launch evidence."""

from __future__ import annotations

import hashlib
import json
import os
import re
import platform
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import importlib.util
import sys
import zipfile
import io
from contextlib import redirect_stdout
from types import SimpleNamespace
import stat

from scripts import run_windows_wheel_ci as wheel_ci

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "native/windows/icode_windows_bootstrap.c"
HEADER = "icode_windows_verifier_binding.h"
_HOST_CMAKE_ARCH = {
    "x86_64": ("x64", 0x8664, "_M_X64"),
    "amd64": ("x64", 0x8664, "_M_X64"),
    "arm64": ("arm64", 0xAA64, "_M_ARM64"),
    "aarch64": ("arm64", 0xAA64, "_M_ARM64"),
}


def fixture_header(root, arch="x64", digest="a" * 64, schema=1):
    # Explicit synthetic header: host cc never proves a real Go/Windows build.
    machine = {"x64": "0x8664", "arm64": "0xAA64"}[arch]
    (root / HEADER).write_text(
        f'#define ICODE_VERIFIER_BINDING_SCHEMA {schema}\n'
        f'#define ICODE_VERIFIER_BINDING_MACHINE {machine}\n'
        f'#define ICODE_VERIFIER_BINDING_SHA256 "{digest}"\n', encoding="ascii")


def binding_output(arch="x64", digest="a" * 64):
    return json.dumps({
        "helper": "icode-windows-bootstrap", "binding_schema_version": 1,
        "architecture": arch, "verifier_sha256": digest,
        "setup_complete": False, "command_execution": False,
        "isolation_ready": False, "launch_authorized": False,
    }, separators=(",", ":")).encode() + b"\n"


class TestWindowsBootstrapBinding(unittest.TestCase):
    def generator(self):
        source = ROOT / "scripts/windows_bootstrap_binding.py"
        self.assertTrue(source.is_file(), "same-bytes binding generator is missing")
        spec = importlib.util.spec_from_file_location("binding_generator_test", source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_binding_validator_is_a_strict_raw_bytes_contract(self):
        validator = getattr(wheel_ci, "_validate_verifier_binding_output", None)
        self.assertIsNotNone(validator, "raw build binding validator is missing")
        self.assertEqual(validator(binding_output(), "x64")["verifier_sha256"], "a" * 64)

    def test_file_identity_compares_kind_not_windows_exe_suffix_permission_hint(self):
        generator = self.generator()
        # CPython 3.11 Windows lstat adds 0111 for .exe suffixes; fstat's
        # GetFileInformationByHandle projection does not. This is not an ACL.
        values = dict(st_dev=1, st_ino=2, st_mode=stat.S_IFREG | 0o666,
                      st_nlink=1, st_size=134, st_mtime_ns=5, st_ctime_ns=6)
        fd = SimpleNamespace(**values)
        path = SimpleNamespace(**dict(values, st_mode=stat.S_IFREG | 0o777))
        self.assertEqual(generator._file_identity(path), generator._file_identity(fd))
        for field, value in (("st_mode", stat.S_IFLNK | 0o777), ("st_dev", 9),
                             ("st_ino", 9), ("st_nlink", 2), ("st_size", 9),
                             ("st_mtime_ns", 9), ("st_ctime_ns", 9)):
            with self.subTest(field=field):
                changed = SimpleNamespace(**dict(values, **{field: value}))
                self.assertNotEqual(generator._file_identity(fd), generator._file_identity(changed))

    def test_binding_validator_rejects_closed_types_bytes_and_trailing_output(self):
        validator = wheel_ci._validate_verifier_binding_output
        valid = binding_output()
        self.assertEqual(validator(valid[:-1] + b"\r\n", "x64")["architecture"], "x64")
        for bad in (valid.decode(), b"", valid[:-1], valid + b"\n", valid + b"PRIVATE",
                    b" " + valid, valid[:-1] + b" \n",
                    valid[:-1] + b"\r\r\n", b"\xff\n", b"x" * 513,
                    valid.replace(b'"binding_schema_version":1', b'"binding_schema_version":true'),
                    valid.replace(b'"binding_schema_version":1', b'"binding_schema_version":1.0'),
                    valid.replace(b'"setup_complete":false', b'"setup_complete":0'),
                    valid.replace(b'"launch_authorized":false', b'"launch_authorized":true'),
                    valid.replace(b'"architecture":"x64"', b'"architecture":"arm64"'),
                    valid.replace(b'a' * 64, b'A' * 64),
                    valid.replace(b'a' * 64, b'a' * 63), valid.replace(b'a' * 64, b'a' * 65),
                    valid.replace(b'a' * 64, b'g' * 64),
                    valid.replace(b'"helper":', b'"helper":"duplicate","helper":'),
                    valid.replace(b'}\n', b',"extra":false}\n'), b'[]\n', b'null\n'):
            with self.subTest(output=repr(bad)[:80]), self.assertRaises(RuntimeError):
                validator(bad, "x64")
        for field in json.loads(valid):
            changed = json.loads(valid)
            del changed[field]
            with self.subTest(missing=field), self.assertRaises(RuntimeError):
                validator(json.dumps(changed).encode() + b"\n", "x64")
        padded = valid[:-2] + b" " * (512 - len(valid)) + b"}\n"
        self.assertEqual(len(padded), 512)
        self.assertEqual(validator(padded, "x64")["verifier_sha256"], "a" * 64)
        for field in ("setup_complete", "command_execution", "isolation_ready", "launch_authorized"):
            for value in (0, 0.0, "false", None, True):
                changed = json.loads(valid); changed[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(RuntimeError):
                    validator(json.dumps(changed).encode() + b"\n", "x64")

    def test_generator_reads_actual_bytes_not_adjacent_digest_or_mtime(self):
        generator = self.generator()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            verifier, header = root / "verifier.exe", root / HEADER
            first = wheel_ci._synthetic_pe(0x8664) + b"A"
            verifier.write_bytes(first)
            (root / "verifier.exe.sha256").write_text("0" * 64)
            generator.generate_binding_header(verifier, "x64", header)
            self.assertIn(hashlib.sha256(first).hexdigest(), header.read_text())
            before = verifier.stat()
            second = first[:-1] + b"B"
            verifier.write_bytes(second)
            os.utime(verifier, ns=(before.st_atime_ns, before.st_mtime_ns))
            generator.generate_binding_header(verifier, "x64", header)
            self.assertIn(hashlib.sha256(second).hexdigest(), header.read_text())
            self.assertNotIn(hashlib.sha256(first).hexdigest(), header.read_text())

    def test_generator_rejects_missing_wrong_arch_empty_nonregular_and_oversize(self):
        generator = self.generator()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            verifier, header = root / "verifier.exe", root / HEADER
            header.write_bytes(b"previous header")
            for label in ("missing", "empty", "bad_pe", "arch", "oversize", "directory", "hardlink"):
                with self.subTest(case=label):
                    if verifier.exists():
                        if verifier.is_dir(): verifier.rmdir()
                        else: verifier.unlink()
                    if label == "empty": verifier.write_bytes(b"")
                    elif label == "bad_pe": verifier.write_bytes(b"not PE")
                    elif label == "arch": verifier.write_bytes(wheel_ci._synthetic_pe(0xAA64))
                    elif label == "oversize":
                        with verifier.open("wb") as stream: stream.truncate(64 * 1024 * 1024 + 1)
                    elif label == "directory": verifier.mkdir()
                    elif label == "hardlink":
                        verifier.write_bytes(wheel_ci._synthetic_pe(0x8664))
                        os.link(verifier, root / "second-link.exe")
                    with self.assertRaises((OSError, ValueError)):
                        generator.generate_binding_header(verifier, "x64", header)
                    self.assertEqual(header.read_bytes(), b"previous header")

    def test_generator_accepts_exact_byte_budget_and_both_pe_architectures(self):
        generator = self.generator()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            verifier = root / "verifier.exe"
            for arch, machine in (("x64", 0x8664), ("arm64", 0xAA64)):
                verifier.write_bytes(wheel_ci._synthetic_pe(machine))
                self.assertEqual(generator.read_verifier_image(verifier, arch), verifier.read_bytes())
            with verifier.open("wb") as stream:
                stream.write(wheel_ci._synthetic_pe(0x8664))
                stream.truncate(generator.MAX_VERIFIER_BYTES)
            image = generator.read_verifier_image(verifier, "x64")
            self.assertEqual(len(image), 64 * 1024 * 1024)

    def test_generator_detects_actual_file_replacement_and_in_read_mutation(self):
        generator = self.generator()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            verifier, other = root / "verifier.exe", root / "other.exe"
            image = wheel_ci._synthetic_pe(0x8664)
            verifier.write_bytes(image)
            other.write_bytes(image)
            original_open = Path.open
            # The original lstat and a different same-bytes FD cannot bind.
            with patch.object(Path, "open", lambda path, *args, **kwargs: original_open(other, *args, **kwargs)):
                with self.assertRaises(ValueError): generator.read_verifier_image(verifier, "x64")

            class MutatingReader:
                def __enter__(self):
                    self.stream = original_open(verifier, "rb")
                    return self
                def __exit__(self, *args): self.stream.close()
                def fileno(self): return self.stream.fileno()
                def read(self, count):
                    data = self.stream.read(count)
                    with original_open(verifier, "wb") as target: target.write(image + b"changed")
                    return data

            with patch.object(Path, "open", return_value=MutatingReader()):
                with self.assertRaises(ValueError): generator.read_verifier_image(verifier, "x64")

    def test_real_generator_cli_failure_never_reports_old_header_success(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            verifier, header = root / "input.exe", root / HEADER
            verifier.write_bytes(wheel_ci._synthetic_pe(0x8664))
            argv = [sys.executable, "-B", str(ROOT / "scripts/windows_bootstrap_binding.py"),
                    "--verifier", str(verifier), "--architecture", "x64", "--output", str(header)]
            result = subprocess.run(argv, capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            before = header.read_bytes()
            verifier.write_bytes(b"bad PE")
            result = subprocess.run(argv, capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, b"")
            self.assertIn(result.stderr, (
                b"windows_bootstrap_binding: invalid_verifier_input_or_header_output\n",
                b"windows_bootstrap_binding: invalid_verifier_input_or_header_output\r\n"))
            self.assertEqual(header.read_bytes(), before)

    def test_raw_query_uses_combined_bounded_capture_and_rejects_errors(self):
        from icode.runner import VerificationOutputCaptureError, VerificationOutputLimitError
        query = getattr(wheel_ci, "_query_verifier_binding", None)
        self.assertIsNotNone(query, "bounded raw query is missing")
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            with patch.object(wheel_ci, "_run_unittest_with_bounded_output", create=True,
                              return_value=(0, binding_output(), b"")) as run:
                self.assertEqual(query(root / "installed.exe", "x64", cwd=root, env={})["verifier_sha256"], "a" * 64)
                self.assertEqual(run.call_args.args[0], [str(root / "installed.exe"), "--verifier-binding-json"])
                self.assertEqual(run.call_args.kwargs, dict(workspace=root, timeout=5, output_limit_bytes=512, environment={}))
            for result in ((1, binding_output(), b""), (False, binding_output(), b""),
                           (0, binding_output(), b"warning"), (0, b"x" * 513, b"")):
                with self.subTest(result=result[0:1]), patch.object(wheel_ci, "_run_unittest_with_bounded_output", create=True, return_value=result):
                    with self.assertRaises(RuntimeError): query(root / "installed.exe", "x64", cwd=root, env={})
            for failure in (subprocess.TimeoutExpired("query", 5), OSError("capture"),
                            VerificationOutputLimitError(512, return_code=0),
                            VerificationOutputCaptureError("cleanup_unknown", return_code=0)):
                with self.subTest(error=type(failure)), patch.object(wheel_ci, "_run_unittest_with_bounded_output", create=True, side_effect=failure):
                    with self.assertRaises(type(failure)): query(root / "installed.exe", "x64", cwd=root, env={})

    def test_installed_binding_hashes_go_bytes_instead_of_manifests(self):
        verify = getattr(wheel_ci, "_verify_installed_verifier_binding", None)
        self.assertIsNotNone(verify, "installed Go binding gate is missing")
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            helper = root / "icode-sandbox-windows-x64.exe"
            verifier = root / "icode-provenance-windows-x64.exe"
            image = wheel_ci._synthetic_pe(0x8664) + b"A"
            verifier.write_bytes(image)
            digest = hashlib.sha256(image).hexdigest()
            with patch.object(wheel_ci, "_query_verifier_binding", create=True, return_value=json.loads(binding_output(digest=digest))):
                verify(helper, "x64", cwd=root, env={})
                verifier.write_bytes(image[:-1] + b"B")
                (root / "icode-provenance-windows-x64.exe.sha256").write_text(hashlib.sha256(verifier.read_bytes()).hexdigest())
                (root / "RECORD").write_text("self-consistent updated record")
                with self.assertRaises(RuntimeError): verify(helper, "x64", cwd=root, env={})
                verifier.write_bytes(wheel_ci._synthetic_pe(0xAA64))
                with self.assertRaises(ValueError): verify(helper, "x64", cwd=root, env={})
                verifier.unlink()
                with self.assertRaises(OSError): verify(helper, "x64", cwd=root, env={})

    def test_workflows_bind_actual_go_and_probe_only_targets_without_unsigned_query(self):
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        for job, targets in (("windows-reviewer-snapshot-probe", "icode_wfp_event_probe"),
                             ("windows-appcontainer-read-handle-probe", "icode_appcontainer_read_probe icode_wfp_event_probe")):
            section = re.split(r"\n  [a-z0-9-]+:\n", ci.split(f"\n  {job}:\n", 1)[1], maxsplit=1)[0]
            self.assertTrue("-DICODE_BUILD_WINDOWS_BOOTSTRAP=OFF" in section, job + " must disable bootstrap")
            self.assertTrue(f"--target {targets} --parallel 1" in section, job + " must build only its probes")
        unsigned = ci.split("\n  windows-bootstrap-wheel:\n", 1)[1].split("\n  presentation:", 1)[0]
        self.assertIn("uses: actions/setup-go@", unsigned)
        self.assertIn("go build -mod=readonly -p 6", unsigned)
        self.assertIn("-o $verifier .\n", unsigned)
        self.assertIn('-DICODE_WINDOWS_PROVENANCE_VERIFIER="$verifier"', unsigned)
        self.assertNotIn("--verifier-binding-json", unsigned)
        self.assertNotIn("--provenance-verifier", unsigned)
        signed = (ROOT / ".github/workflows/windows-helper-provenance.yml").read_text(encoding="utf-8")
        self.assertIn('-DICODE_WINDOWS_PROVENANCE_VERIFIER="$verifier"', signed)
        self.assertLess(signed.index("go build -mod=readonly"), signed.index("cmake -S native/windows"))

    def test_portable_binding_contract_selected_once_without_host_compiler_credit(self):
        from scripts.run_workspace_ci import DEFAULT_MODULES
        self.assertEqual(DEFAULT_MODULES.count("tests.test_windows_bootstrap_binding.TestWindowsBootstrapBinding"), 1)
        self.assertNotIn("tests.test_windows_bootstrap_binding", DEFAULT_MODULES)
        self.assertNotIn("tests.test_windows_bootstrap_binding.TestWindowsBootstrapBindingHostCompiler", DEFAULT_MODULES)

    def test_signed_install_order_and_failure_gates_preserve_no_go_proof_only(self):
        # Mock only external build/install/gh/Go commands; retain real main,
        # query validation, installed raw byte hashing and export filesystem.
        for mode in ("valid", "gh_failure", "c_drift", "binding_failure", "go_failure", "proof_only", "unsigned"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                helper = root / "icode-sandbox-windows-x64.exe"
                verifier = root / "icode-provenance-windows-x64.exe"
                image = wheel_ci._synthetic_pe(0x8664)
                helper.write_bytes(image + b"C")
                original_c_digest = hashlib.sha256(helper.read_bytes()).hexdigest()
                verifier.write_bytes(image + b"Go")
                bundle, notices = root / "proof.json", root / "notices.txt"
                bundle.write_bytes(b"opaque CI proof fixture")
                Path(str(helper) + ".sigstore.json").write_bytes(bundle.read_bytes())
                notices.write_bytes(b"notice fixture\n")
                output = root / "export"
                argv = ["probe", "--native-helper", str(helper)]
                if mode != "unsigned": argv += ["--provenance-bundle", str(bundle), "--wheel-output", str(output)]
                if mode not in ("proof_only", "unsigned"):
                    argv += ["--provenance-verifier", str(verifier), "--provenance-notices", str(notices)]
                stages = []

                def external(stage, args, *, cwd, env):
                    stages.append(stage)
                    if stage == "install Windows wheel" and mode == "c_drift":
                        helper.write_bytes(image + b"changed installed C")
                    if stage == "cryptographically verify installed CI artifact provenance":
                        self.assertEqual(args[3], str(helper), "gh must verify installed C, not staging C")
                        if mode == "gh_failure": raise RuntimeError("gh rejected C fixture")
                        if hashlib.sha256(Path(args[3]).read_bytes()).hexdigest() != original_c_digest:
                            raise RuntimeError("simulated gh rejected changed installed C bytes")
                    if stage.startswith("build "):
                        dist = Path(args[args.index("--outdir") + 1]); dist.mkdir()
                        name = "fixture-py3-none-any.whl" if "pure" in stage else "fixture-py3-none-win_amd64.whl"
                        with zipfile.ZipFile(dist / name, "w") as archive: archive.writestr("fixture", b"wheel fixture")
                    if stage == "resolve installed helper without source checkout": return str(helper) + "\n"
                    if stage == "verify installed wheel using its offline verifier" and mode == "go_failure":
                        raise RuntimeError("Go rejected proof fixture")
                    if stage == "run installed native bootstrap metadata":
                        return json.dumps({"helper": "icode-windows-bootstrap", "bootstrap_version": 1,
                            "runner_protocol_version": 1, "architecture": "x64", "setup_complete": False,
                            "command_execution": False, "isolation_ready": False}, separators=(",", ":")) + "\n"
                    return ""

                def raw_query(args, **kwargs):
                    stages.append("binding query")
                    self.assertIn("cryptographically verify installed CI artifact provenance", stages)
                    self.assertEqual(args, [str(helper), "--verifier-binding-json"])
                    digest = "0" * 64 if mode == "binding_failure" else hashlib.sha256(verifier.read_bytes()).hexdigest()
                    return (0, binding_output(digest=digest), b"")

                with patch.object(sys, "argv", argv), patch.object(wheel_ci.sys, "platform", "win32"), \
                     patch.object(wheel_ci.sysconfig, "get_platform", return_value="win-amd64"), \
                     patch.dict(os.environ, {"GITHUB_SHA": "a" * 40}), \
                     patch.object(wheel_ci, "_run", side_effect=external), \
                     patch.object(wheel_ci, "check_windows_wheel", return_value=[]), \
                     patch.object(wheel_ci, "_run_unittest_with_bounded_output", side_effect=raw_query), redirect_stdout(io.StringIO()):
                    result = wheel_ci.main()
                if mode in ("gh_failure", "c_drift", "binding_failure", "go_failure"):
                    self.assertEqual(result, 1)
                    self.assertFalse(output.exists(), "failure exported a signed wheel")
                else: self.assertEqual(result, 0)
                if mode in ("gh_failure", "c_drift", "proof_only", "unsigned"):
                    self.assertNotIn("binding query", stages)
                if mode in ("gh_failure", "c_drift", "binding_failure", "proof_only", "unsigned"):
                    self.assertNotIn("verify installed wheel using its offline verifier", stages)
                if mode == "valid":
                    ordered = ["cryptographically verify installed CI artifact provenance", "binding query",
                               "verify installed wheel using its offline verifier", "run installed native bootstrap metadata"]
                    self.assertEqual([stages.index(x) for x in ordered], sorted(stages.index(x) for x in ordered))
                    self.assertEqual(len(list(output.glob("*.whl"))), 1)


@unittest.skipUnless(os.name == "posix" and shutil.which("cc"), "POSIX synthetic host C compiler unavailable")
class TestWindowsBootstrapBindingHostCompiler(unittest.TestCase):
    def test_source_adjacent_stale_header_cannot_override_current_build_header(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source, build = root / "source", root / "build"
            source.mkdir(); build.mkdir()
            copied = source / SOURCE.name
            copied.write_bytes(SOURCE.read_bytes())
            fixture_header(source, digest="b" * 64)
            fixture_header(build, digest="a" * 64)
            binary = build / "bootstrap"
            result = subprocess.run([
                shutil.which("cc"), "-std=c11", "-D_WIN32", "-D_M_X64", "-I", str(build),
                str(copied), "-o", str(binary),
            ], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            queried = subprocess.run([str(binary), "--verifier-binding-json"], capture_output=True, timeout=5)
            self.assertEqual(queried.stdout, binding_output(digest="a" * 64))

    def configure(self, root, verifier=None, bootstrap=True):
        _arch, _machine, define = _HOST_CMAKE_ARCH[platform.machine().lower()]
        argv = ["cmake", "-S", str(ROOT / "native/windows"), "-B", str(root / "build"),
                "-DWIN32=TRUE", f"-DCMAKE_C_FLAGS=-D_WIN32 -D{define}",
                f"-DPython3_EXECUTABLE={sys.executable}"]
        if verifier is not None: argv.append(f"-DICODE_WINDOWS_PROVENANCE_VERIFIER={verifier}")
        if not bootstrap: argv.append("-DICODE_BUILD_WINDOWS_BOOTSTRAP=OFF")
        return subprocess.run(argv, capture_output=True, timeout=30)

    @unittest.skipUnless(shutil.which("cmake"), "host CMake unavailable")
    def test_default_build_requires_explicit_go_and_probe_only_can_opt_out(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            missing = self.configure(root)
            self.assertNotEqual(missing.returncode, 0, "default build accepted no verifier input")
            probe = self.configure(root, bootstrap=False)
            self.assertEqual(probe.returncode, 0, probe.stderr)
            built = subprocess.run(["cmake", "--build", str(root / "build"),
                                    "--target", "icode_windows_bootstrap", "--parallel", "1"],
                                   capture_output=True, timeout=30)
            self.assertNotEqual(built.returncode, 0, "probe-only mode exposed bootstrap target")

    @unittest.skipUnless(shutil.which("cmake"), "host CMake unavailable")
    def test_every_build_relinks_current_same_mtime_go_and_refuses_stale_header(self):
        # WIN32 and compiler defines are explicit synthetic logic inputs. Neither
        # the test PE nor this host ELF is a real Go binary/Windows acceptance.
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            verifier = root / "verifier.exe"
            arch, machine, _define = _HOST_CMAKE_ARCH[platform.machine().lower()]
            first = wheel_ci._synthetic_pe(machine) + b"A"
            verifier.write_bytes(first)
            configured = self.configure(root, verifier)
            self.assertEqual(configured.returncode, 0, configured.stderr)
            build_argv = ["cmake", "--build", str(root / "build"), "--target", "icode_windows_bootstrap", "--parallel", "1"]
            binary = root / f"build/icode-sandbox-windows-{arch}"
            for image in (first, first[:-1] + b"B"):
                before = verifier.stat()
                verifier.write_bytes(image)
                os.utime(verifier, ns=(before.st_atime_ns, before.st_mtime_ns))
                built = subprocess.run(build_argv, capture_output=True, timeout=30)
                self.assertEqual(built.returncode, 0, built.stderr)
                result = subprocess.run([str(binary), "--verifier-binding-json"], capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, binding_output(arch, hashlib.sha256(image).hexdigest()))
            alternate = root / "alternate-verifier.exe"
            alternate.write_bytes(first + b"reconfigured")
            configured = self.configure(root, alternate)
            self.assertEqual(configured.returncode, 0, configured.stderr)
            built = subprocess.run(build_argv, capture_output=True, timeout=30)
            self.assertEqual(built.returncode, 0, built.stderr)
            rebound = subprocess.run([str(binary), "--verifier-binding-json"], capture_output=True, timeout=5)
            self.assertEqual(rebound.stdout, binding_output(arch, hashlib.sha256(alternate.read_bytes()).hexdigest()))
            configured = self.configure(root, verifier)
            self.assertEqual(configured.returncode, 0, configured.stderr)
            for label in ("missing", "wrong_arch", "bad_generator"):
                with self.subTest(case=label):
                    if label == "missing": verifier.unlink()
                    elif label == "wrong_arch": verifier.write_bytes(wheel_ci._synthetic_pe(0xAA64 if arch == "x64" else 0x8664))
                    else:
                        verifier.write_bytes(first)
                        configured = subprocess.run([
                            "cmake", "-S", str(ROOT / "native/windows"), "-B", str(root / "build"),
                            f"-DPython3_EXECUTABLE={root / 'missing-python'}",
                        ], capture_output=True, timeout=30)
                        self.assertNotEqual(configured.returncode, 0)
                    built = subprocess.run(build_argv, capture_output=True, timeout=30)
                    self.assertNotEqual(built.returncode, 0, "old header/EXE allowed a successful build")

    def test_new_query_emits_explicit_synthetic_header_binding(self):
        for arch, define in (("x64", "_M_X64"), ("arm64", "_M_ARM64")):
            with self.subTest(arch=arch), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                fixture_header(root, arch)
                binary = root / "bootstrap"
                compiled = subprocess.run([
                    shutil.which("cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-D_WIN32", f"-D{define}", "-I", str(root), str(SOURCE), "-o", str(binary),
                ], capture_output=True, timeout=30)
                self.assertEqual(compiled.returncode, 0, compiled.stderr)
                result = subprocess.run([str(binary), "--verifier-binding-json"],
                                        capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, binding_output(arch))
                self.assertEqual(result.stderr, b"")
                binding = wheel_ci._query_verifier_binding(binary, arch, cwd=root, env=os.environ.copy())
                self.assertEqual(binding["verifier_sha256"], "a" * 64)
                for extra in (["--verifier-binding-json", "extra"], ["--verifier-binding-json", "setup"]):
                    rejected = subprocess.run([str(binary), *extra], capture_output=True, timeout=5)
                    self.assertEqual(rejected.returncode, 78)
                    self.assertEqual(rejected.stdout, b"")
                    self.assertEqual(rejected.stderr, b"icode_windows_bootstrap: unsupported_operation\n")

    def test_old_missing_wrong_arch_and_bad_digest_headers_cannot_compile(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            for label in ("missing", "old", "wrong_arch", "short_digest"):
                with self.subTest(case=label):
                    header = root / HEADER
                    if header.exists(): header.unlink()
                    if label == "old": fixture_header(root, schema=0)
                    elif label == "wrong_arch": fixture_header(root, "arm64")
                    elif label == "short_digest": fixture_header(root, digest="a" * 63)
                    compiled = subprocess.run([
                        shutil.which("cc"), "-std=c11", "-D_WIN32", "-D_M_X64", "-I", str(root),
                        "-c", str(SOURCE), "-o", str(root / "bad.o"),
                    ], capture_output=True, timeout=30)
                    self.assertNotEqual(compiled.returncode, 0, "invalid header compiled")

    def test_actual_raw_query_limit_stderr_invalid_utf8_and_timeout_are_not_success(self):
        from icode.runner import VerificationOutputLimitError
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            helper = root / "synthetic-query"
            for label, program, error in (
                ("limit", "import os;os.write(1,b'x'*513)", VerificationOutputLimitError),
                ("combined_limit", "import os;os.write(1,b'x'*512);os.write(2,b'x')", VerificationOutputLimitError),
                ("stderr", f"import os;os.write(1,{binding_output()!r});os.write(2,b'warning')", RuntimeError),
                ("utf8", "import os;os.write(1,b'\\xff\\n')", RuntimeError),
                ("timeout", "import time;time.sleep(10)", subprocess.TimeoutExpired),
            ):
                with self.subTest(case=label):
                    helper.write_text(f"#!{sys.executable}\n{program}\n", encoding="utf-8")
                    helper.chmod(0o700)
                    with self.assertRaises(error):
                        wheel_ci._query_verifier_binding(helper, "x64", cwd=root, env=os.environ.copy())
