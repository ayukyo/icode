"""Host-crash diagnostics must use the installed Python runtime, not /usr/bin."""

import ast
from pathlib import Path
import sys
import unittest
from unittest import mock

from tests._support import temp_workspace
from icode.isolation import LandlockSandbox, probe_linux_process_tree_cleanup


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux host-crash runtime test")
class TestLinuxCleanupRuntime(unittest.TestCase):
    def _attempt(self, *, system_python_missing: bool = False, runtime_error: bool = False):
        with temp_workspace() as root:
            helper = root / "helper"
            helper.write_bytes(b"validation fixture; never executed")
            venv = root / "venv with spaces"
            base = root / "base runtime"
            (venv / "bin").mkdir(parents=True)
            base.mkdir()
            interpreter = venv / "bin" / "python"
            interpreter.symlink_to(sys.executable)
            sandbox = LandlockSandbox(str(helper), manifest=str(root / "helper.sha256"))
            original_is_file = Path.is_file

            def is_file(path):
                if system_python_missing and path == Path("/usr/bin/python3"):
                    return False
                return original_is_file(path)

            with mock.patch("icode.isolation.sys.platform", "linux"), \
                 mock.patch("icode.isolation.sys.executable", str(interpreter)), \
                 mock.patch("icode.isolation.sys.prefix", str(venv)), \
                 mock.patch("icode.isolation.sys.base_prefix", str(base)), \
                 mock.patch("icode.native_helper.verify_native_helper", return_value=True), \
                 mock.patch.object(Path, "is_file", is_file), \
                 mock.patch.object(sandbox, "wrap", wraps=sandbox.wrap) as wrap, \
                 mock.patch("icode.isolation.subprocess.Popen", side_effect=OSError("private-path")) as launch:
                if runtime_error:
                    with mock.patch.object(sandbox, "_runtime_read_roots", side_effect=RuntimeError("private-root")):
                        result = probe_linux_process_tree_cleanup(sandbox)
                else:
                    result = probe_linux_process_tree_cleanup(sandbox)
            return result, wrap, launch, str(interpreter), (str(venv), str(base))

    def test_missing_system_python_does_not_prevent_current_runtime_probe(self):
        result, wrap, launch, interpreter, _ = self._attempt(system_python_missing=True)
        wrap.assert_called_once()
        launch.assert_called_once()
        self.assertEqual(wrap.call_args.args[0][:3], [interpreter, "-I", "-c"])
        self.assertTrue(result.executed)
        self.assertFalse(result.passed)
        self.assertNotIn("private-path", result.detail)

    def test_host_preserves_current_venv_path_and_isolated_mode(self):
        _, _, launch, interpreter, _ = self._attempt()
        argv = launch.call_args.args[0]
        self.assertEqual(argv[:3], [interpreter, "-I", "-c"])

    def test_wrapped_command_preserves_runtime_roots_and_rebinds_only_parent_pid(self):
        _, _, launch, interpreter, runtime_roots = self._attempt()
        host = ast.parse(launch.call_args.args[0][-1])
        assignments = [statement for statement in host.body if isinstance(statement, ast.Assign)]
        self.assertEqual(len(assignments), 2)
        wrapped = ast.literal_eval(assignments[0].value)
        actual_roots = [wrapped[index + 1] for index, value in enumerate(wrapped) if value == "--runtime-read"]
        self.assertCountEqual(actual_roots, runtime_roots)
        for root in runtime_roots:
            index = wrapped.index(root)
            self.assertEqual(wrapped[index - 1], "--runtime-read")
        self.assertEqual(wrapped[wrapped.index("--") + 1:][:3], [interpreter, "-I", "-c"])
        target = ast.parse("wrapped[wrapped.index('--parent-pid') + 1] = str(os.getpid())").body[0]
        self.assertEqual(ast.dump(assignments[1]), ast.dump(target))

    def test_grandchild_also_uses_isolated_current_interpreter(self):
        _, wrap, _, _, _ = self._attempt()
        wrap.assert_called_once()
        child = wrap.call_args.args[0][-1]
        call = ast.parse(child).body[1].value
        argv = call.args[0]
        self.assertEqual(ast.unparse(argv.elts[0]), "sys.executable")
        self.assertEqual([ast.literal_eval(value) for value in argv.elts[1:3]], ["-I", "-c"])

    def test_invalid_runtime_roots_fail_before_starting_host(self):
        result, wrap, launch, _, _ = self._attempt(runtime_error=True)
        wrap.assert_called_once()
        launch.assert_not_called()
        self.assertFalse(result.passed)
        self.assertEqual(result.detail, "Linux process-tree cleanup probe failed: setup")
        self.assertNotIn("private-root", result.detail)
