"""R2.3 Windows 工单级 Job Object 原生清理试验。"""

from __future__ import annotations

import ast
import ctypes
import inspect
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from tests._support import temp_workspace

import icode.windows_job as windows_job_module
from icode.windows_job import (
    WindowsJobResult,
    _allocate_attribute_list_buffer,
    _append_windows_environment_value,
    _build_windows_environment_block,
    _build_private_network_capability_probe_argv,
    _is_fixed_private_network_capability_probe,
    _is_fixed_system_whoami_probe,
    _private_network_capability_exit_stage,
    probe_windows_job_cleanup,
    run_windows_job,
)


class TestWindowsJob(unittest.TestCase):
    def test_挂起进程token核验位于入Job之后且ResumeThread之前(self) -> None:
        source = inspect.getsource(run_windows_job)
        assignment = source.index("kernel.AssignProcessToJobObject(job, process.hProcess)")
        inspection = source.index("_read_windows_appcontainer_token_receipt(")
        resume = source.index("kernel.ResumeThread(process.hThread)")
        self.assertLess(assignment, inspection)
        self.assertLess(inspection, resume)
        self.assertIn("if _diagnostic_private_network_capability:", source)

    def test_父进程实读挂起子进程token并校验capability(self) -> None:
        receipt_type = windows_job_module._WindowsAppContainerTokenReceipt
        sid_and_attributes_type = windows_job_module._TOKEN_PROBE_SID_AND_ATTRIBUTES
        token_groups_type = windows_job_module._TOKEN_PROBE_GROUPS
        token_appcontainer_type = windows_job_module._TOKEN_PROBE_APPCONTAINER_INFORMATION

        package_sid_storage = ctypes.create_string_buffer(16)
        capability_sid_storage = ctypes.create_string_buffer(16)
        unexpected_sid_storage = ctypes.create_string_buffer(16)
        package_sid_storage.raw = b"package-sid-test"
        capability_sid_storage.raw = b"capability-sid!!"
        unexpected_sid_storage.raw = b"unexpected-sid!!"

        def make_api(*, appcontainer: int = 1, capability_count: int = 1,
                     package_sid: int | None = None,
                     capability_sid: int | None = None, attributes: int = 0x4,
                     fail_class: int | None = None, close_ok: bool = True):
            package_sid_address = (
                package_sid if package_sid is not None
                else ctypes.addressof(package_sid_storage)
            )
            capability_sid_address = (
                capability_sid if capability_sid is not None
                else ctypes.addressof(capability_sid_storage)
            )

            def write_returned_length(pointer, value):
                ctypes.cast(pointer, ctypes.POINTER(ctypes.c_uint32))[0] = value

            def open_process_token(_process, desired_access, token_out):
                self.assertEqual(desired_access, 0x0008)  # TOKEN_QUERY
                ctypes.cast(token_out, ctypes.POINTER(ctypes.c_void_p))[0] = 123
                return 1

            def get_token_information(_token, info_class, output, capacity, returned):
                if info_class == fail_class:
                    return 0
                if info_class == 29:  # TokenIsAppContainer
                    value = ctypes.c_uint32(appcontainer)
                    required = ctypes.sizeof(value)
                    if capacity < required:
                        write_returned_length(returned, required)
                        return 0
                    ctypes.memmove(output, ctypes.byref(value), required)
                elif info_class == 31:  # TokenAppContainerSid
                    structure_bytes = ctypes.sizeof(token_appcontainer_type)
                    sid_bytes = ctypes.string_at(package_sid_address, 16)
                    required = structure_bytes + len(sid_bytes)
                    if capacity < required:
                        write_returned_length(returned, required)
                        return 0
                    output_address = ctypes.cast(output, ctypes.c_void_p).value
                    value = token_appcontainer_type()
                    value.TokenAppContainer = output_address + structure_bytes
                    ctypes.memmove(output, ctypes.byref(value), structure_bytes)
                    ctypes.memmove(
                        output_address + structure_bytes, sid_bytes, len(sid_bytes),
                    )
                elif info_class == 30:  # TokenCapabilities
                    header_bytes = token_groups_type.Groups.offset
                    entry_bytes = ctypes.sizeof(sid_and_attributes_type)
                    sid_bytes = (
                        ctypes.string_at(capability_sid_address, 16)
                        if capability_count else b""
                    )
                    required = (
                        header_bytes + capability_count * entry_bytes + len(sid_bytes)
                    )
                    if capacity < required:
                        write_returned_length(returned, required)
                        return 0
                    output_address = ctypes.cast(output, ctypes.c_void_p).value
                    ctypes.memset(output, 0, required)
                    groups = ctypes.cast(
                        output, ctypes.POINTER(token_groups_type),
                    ).contents
                    groups.GroupCount = capability_count
                    if capability_count:
                        groups.Groups[0].Sid = output_address + header_bytes + (
                            capability_count * entry_bytes
                        )
                        groups.Groups[0].Attributes = attributes
                        ctypes.memmove(
                            groups.Groups[0].Sid, sid_bytes, len(sid_bytes),
                        )
                else:
                    self.fail(f"unexpected token information class: {info_class}")
                write_returned_length(returned, required)
                return 1

            def equal_sid(left, right):
                left_value = ctypes.cast(left, ctypes.c_void_p).value
                right_value = ctypes.cast(right, ctypes.c_void_p).value
                return int(ctypes.string_at(left_value, 16) == ctypes.string_at(right_value, 16))

            return (
                SimpleNamespace(
                    OpenProcessToken=open_process_token,
                    GetTokenInformation=get_token_information,
                    EqualSid=equal_sid,
                ),
                SimpleNamespace(CloseHandle=lambda _handle: int(close_ok)),
            )

        advapi, kernel = make_api()
        matched = windows_job_module._read_windows_appcontainer_token_receipt(
            456, ctypes.addressof(package_sid_storage),
            ctypes.addressof(capability_sid_storage), advapi=advapi, kernel=kernel,
        )
        self.assertIsInstance(matched, receipt_type)
        self.assertEqual(matched.stage, "matched")
        self.assertTrue(matched.verified)
        self.assertEqual(matched.capability_count, 1)
        self.assertTrue(matched.package_sid_match)
        self.assertTrue(matched.capability_sid_match)
        self.assertTrue(matched.capability_enabled)
        self.assertTrue(matched.token_handle_closed)
        self.assertNotIn("S-1-", repr(matched))

        mismatch_cases = (
            ({"package_sid": ctypes.addressof(unexpected_sid_storage)},
             "package_sid_mismatch"),
            ({"capability_sid": ctypes.addressof(unexpected_sid_storage)},
             "capability_sid_mismatch"),
            ({"attributes": 0}, "capability_not_enabled"),
            ({"capability_count": 0}, "capability_count_mismatch"),
            ({"capability_count": 2}, "capability_count_mismatch"),
            ({"appcontainer": 0}, "appcontainer_mismatch"),
            ({"fail_class": 30}, "capabilities_query_failed"),
            ({"close_ok": False}, "token_handle_close_failed"),
        )
        for options, expected_stage in mismatch_cases:
            with self.subTest(expected_stage=expected_stage):
                advapi, kernel = make_api(**options)
                receipt = windows_job_module._read_windows_appcontainer_token_receipt(
                    456, ctypes.addressof(package_sid_storage),
                    ctypes.addressof(capability_sid_storage),
                    advapi=advapi, kernel=kernel,
                )
                self.assertEqual(receipt.stage, expected_stage)
                self.assertFalse(receipt.verified)

    def test_private_network正控token句柄关闭失败不报告cleanup通过(self) -> None:
        class ProcessInformation(ctypes.Structure):
            _fields_ = [
                ("hProcess", ctypes.c_void_p), ("hThread", ctypes.c_void_p),
                ("dwProcessId", ctypes.c_uint32), ("dwThreadId", ctypes.c_uint32),
            ]

        kernel = mock.Mock()
        advapi = mock.Mock()
        capability_sid = ctypes.create_string_buffer(16)
        kernel.CreateJobObjectW.return_value = 101
        kernel.SetInformationJobObject.return_value = 1
        kernel.UpdateProcThreadAttribute.return_value = 1
        kernel.AssignProcessToJobObject.return_value = 1
        kernel.ResumeThread.return_value = 1
        kernel.WaitForSingleObject.return_value = 0
        kernel.GetExitCodeProcess.return_value = 1
        kernel.TerminateJobObject.return_value = 1
        kernel.QueryInformationJobObject.return_value = 1
        kernel.CloseHandle.return_value = 1
        kernel.LocalFree.return_value = 0

        def initialize_attribute_list(attribute_list, _count, _flags, size):
            if attribute_list is None:
                ctypes.cast(size, ctypes.POINTER(ctypes.c_size_t)).contents.value = 64
                return 0
            return 1

        def convert_capability_sid(_name, sid_out):
            ctypes.cast(sid_out, ctypes.POINTER(ctypes.c_void_p)).contents.value = (
                ctypes.addressof(capability_sid)
            )
            return 1

        def create_process(*arguments):
            process = ctypes.cast(
                arguments[-1], ctypes.POINTER(ProcessInformation),
            ).contents
            process.hProcess = 202
            process.hThread = 303
            return 1

        kernel.InitializeProcThreadAttributeList.side_effect = initialize_attribute_list
        kernel.CreateProcessW.side_effect = create_process
        advapi.ConvertStringSidToSidW.side_effect = convert_capability_sid
        failed_close_receipt = windows_job_module._WindowsAppContainerTokenReceipt(
            "token_handle_close_failed", True, True, 1, True, True, False,
        )

        with temp_workspace() as workspace, \
             mock.patch("icode.windows_job.sys.platform", "win32"), \
             mock.patch(
                 "icode.windows_job._is_fixed_private_network_capability_probe",
                 return_value=True,
             ), \
             mock.patch("icode.windows_job.Path.is_absolute", return_value=True), \
             mock.patch("icode.windows_job.Path.is_file", return_value=True), \
             mock.patch("icode.windows_job.Path.resolve", return_value=workspace), \
             mock.patch("icode.windows_job.Path.is_dir", return_value=True), \
             mock.patch(
                 "ctypes.WinDLL",
                 side_effect=lambda name, **_kwargs: kernel if name == "kernel32" else advapi,
                 create=True,
             ), \
             mock.patch("ctypes.set_last_error", create=True), \
             mock.patch("ctypes.get_last_error", return_value=122, create=True), \
             mock.patch("ctypes.FormatError", return_value="expected test", create=True), \
             mock.patch(
                 "icode.windows_job._read_windows_appcontainer_token_receipt",
                 return_value=failed_close_receipt,
             ):
            result = run_windows_job(
                [r"C:\Python\python.exe"], cwd=workspace, timeout_seconds=2,
                _appcontainer_sid=123, _diagnostic_private_network_capability=True,
            )

        self.assertTrue(result.executed)
        self.assertEqual(result.exit_code, 0)
        self.assertIs(result.child_token_receipt, failed_close_receipt)
        self.assertFalse(result.cleanup_ok)
        self.assertEqual(result.error, "cleanup_failed")
        self.assertIn("token", result.detail.casefold())

    def test_TokenCapabilities按TOKEN_GROUPS布局并校验返回长度(self) -> None:
        helper_code = windows_job_module._TOKEN_GROUPS_CAPABILITY_PARSER_CODE
        namespace: dict[str, object] = {
            "ctypes": ctypes,
            "wintypes": ctypes.wintypes,
        }
        exec(compile(helper_code, "<token-groups-parser>", "exec"), namespace)
        group_type = namespace["TOKEN_GROUPS"]
        parse = namespace["_read_single_token_capability"]
        sid_storage = ctypes.create_string_buffer(16)
        group = group_type()
        group.GroupCount = 1
        group.Groups[0].Sid = ctypes.addressof(sid_storage)
        for attributes in (0x4, 0x5, 0):
            with self.subTest(attributes=attributes):
                group.Groups[0].Attributes = attributes
                buffer = ctypes.create_string_buffer(ctypes.sizeof(group))
                ctypes.memmove(buffer, ctypes.byref(group), ctypes.sizeof(group))
                sid, observed_attributes = parse(
                    ctypes.addressof(buffer), len(buffer), len(buffer),
                )
                self.assertEqual(sid, ctypes.addressof(sid_storage))
                self.assertEqual(observed_attributes, attributes)
                self.assertEqual(
                    bool(observed_attributes & windows_job_module._SE_GROUP_ENABLED),
                    attributes in (0x4, 0x5),
                )

        header_size = group_type.Groups.offset
        entry_size = ctypes.sizeof(namespace["SID_AND_ATTRIBUTES"])
        truncated = ctypes.create_string_buffer(ctypes.sizeof(group))
        ctypes.memmove(truncated, ctypes.byref(group), ctypes.sizeof(group))
        with self.assertRaisesRegex(ValueError, "return length"):
            parse(
                ctypes.addressof(truncated), len(truncated),
                header_size + entry_size - 1,
            )
        with self.assertRaisesRegex(ValueError, "buffer capacity"):
            parse(
                ctypes.addressof(truncated), len(truncated), len(truncated) + 1,
            )

    def test_private_network正控失败阶段使用有界exit码(self) -> None:
        expected_stages = [
            (None, "no_exit_code"),
            (0, "probe_completed"),
            (80, "probe_initialization"),
            (81, "token_open"),
            (82, "token_appcontainer"),
            (83, "token_package_sid"),
            (84, "token_capabilities"),
            (85, "token_package_sid_text"),
            (86, "token_capability_sid_text"),
            (87, "token_appcontainer_match"),
            (88, "token_package_sid_match"),
            (89, "token_capability_sid_match"),
            (90, "token_capability_enabled_missing_zero_attributes"),
            (91, "ipv4_connect"),
            (92, "ipv4_send"),
            (93, "ipv6_connect"),
            (94, "ipv6_send"),
            (95, "token_capability_enabled_missing_nonzero_attributes"),
            (96, "token_capability_sid_internet_client"),
            (97, "token_capability_sid_internet_client_server"),
            (98, "token_capability_sid_other_well_known"),
            (99, "token_capability_sid_unrecognized"),
            (100, "token_capability_sid_classifier_error"),
            (101, "token_capability_enabled_check"),
            (102, "token_capability_payload"),
            (103, "token_handle_close"),
            (104, "network_probe_setup"),
            (1, "unclassified"),
            (-1, "unclassified"),
            (True, "unclassified"),
        ]
        for exit_code, expected in expected_stages:
            with self.subTest(exit_code=exit_code):
                self.assertEqual(
                    _private_network_capability_exit_stage(exit_code), expected,
                )

        argv = _build_private_network_capability_probe_argv(
            r"C:\actions\_temp\icode-runtime-staging-reviewer-fixed\python.exe",
            43123, 43124, "0123456789abcdef0123456789abcdef",
            "S-1-15-2-123456789-123456789-123456789-123456789",
        )
        compile(argv[3], "<private-network-capability-probe>", "exec")
        probe_tree = ast.parse(argv[3])
        network_loops = [
            node for node in ast.walk(probe_tree)
            if isinstance(node, ast.For)
            and isinstance(node.target, ast.Tuple)
            and any(
                isinstance(target, ast.Name) and target.id == "family"
                for target in node.target.elts
            )
        ]
        self.assertEqual(len(network_loops), 1)
        network_loop = network_loops[0]
        self.assertEqual(len(network_loop.target.elts), 5)
        self.assertIsInstance(network_loop.iter, ast.Tuple)
        self.assertTrue(all(
            isinstance(entry, ast.Tuple) and len(entry.elts) == 5
            for entry in network_loop.iter.elts
        ))
        self.assertEqual(
            [target.id for target in network_loop.target.elts],
            [
                "family", "address", "port", "connect_failure_exit_code",
                "send_failure_exit_code",
            ],
        )

        connected: list[tuple[int, tuple[str, int]]] = []
        sent: list[tuple[int, bytes]] = []

        class FakeConnection:
            def __init__(self, family: int) -> None:
                self.family = family

            def __enter__(self) -> FakeConnection:
                return self

            def __exit__(self, *_exc: object) -> bool:
                return False

            def settimeout(self, _timeout: float) -> None:
                pass

            def connect(self, address: tuple[str, int]) -> None:
                connected.append((self.family, address))

            def sendall(self, payload: bytes) -> None:
                sent.append((self.family, payload))

        fake_socket = SimpleNamespace(
            AF_INET=2,
            AF_INET6=23,
            SOCK_STREAM=1,
            socket=lambda family, _kind: FakeConnection(family),
        )
        loop_namespace = {
            "socket": fake_socket,
            "sys": SimpleNamespace(argv=["python", "43123", "43124"]),
            "payload": b"fixed-probe-receipt",
            "_failure_exit_code": 104,
        }
        loop_program = compile(
            ast.Module(body=[network_loop], type_ignores=[]),
            "<private-network-socket-loop>", "exec",
        )
        exec(loop_program, loop_namespace)
        self.assertEqual(
            connected,
            [(2, ("127.0.0.1", 43123)), (23, ("::1", 43124))],
        )
        self.assertEqual(
            sent, [(2, b"fixed-probe-receipt"), (23, b"fixed-probe-receipt")],
        )
        self.assertEqual(loop_namespace["_failure_exit_code"], 94)

        self.assertIn("_failure_exit_code = 80", argv[3])
        self.assertIn("_failure_exit_code = 81", argv[3])
        self.assertIn("_failure_exit_code = 82", argv[3])
        self.assertIn("_failure_exit_code = 83", argv[3])
        self.assertIn("_failure_exit_code = 84", argv[3])
        self.assertIn("_failure_exit_code = 85", argv[3])
        self.assertIn("_failure_exit_code = 86", argv[3])
        self.assertIn("_failure_exit_code = 87", argv[3])
        self.assertIn("_failure_exit_code = 88", argv[3])
        self.assertIn("_failure_exit_code = 89", argv[3])
        self.assertIn(
            "mismatch_exit_code = _private_network_capability_sid_mismatch_exit_code(",
            argv[3],
        )
        self.assertIn("_failure_exit_code = 100", argv[3])
        self.assertIn(
            "raise SystemExit(mismatch_exit_code)",
            argv[3],
        )
        self.assertIn("_failure_exit_code = 90", argv[3])
        self.assertIn(
            "_failure_exit_code = 90 if capability_attributes == 0 else 95",
            argv[3],
        )
        self.assertLess(
            argv[3].index("_failure_exit_code = 101"),
            argv[3].index("if not (capability_attributes & SE_GROUP_ENABLED):"),
        )
        self.assertLess(
            argv[3].index("_failure_exit_code = 102"),
            argv[3].index("payload = json.dumps({"),
        )
        self.assertIn(
            "token_closed = kernel.CloseHandle(token)",
            argv[3],
        )
        self.assertIn("if not token_closed:", argv[3])
        self.assertIn(
            "raise RuntimeError('AppContainer token handle close failed')",
            argv[3],
        )
        self.assertLess(
            argv[3].index("token_closed = kernel.CloseHandle(token)"),
            argv[3].index("_failure_exit_code = 103"),
        )
        self.assertLess(
            argv[3].index("kernel.CloseHandle(token)"),
            argv[3].index("_failure_exit_code = 104"),
        )
        self.assertLess(
            argv[3].index("_failure_exit_code = 104"),
            argv[3].index("for family, address, port, connect_failure_exit_code"),
        )
        self.assertIn("_read_single_token_capability(", argv[3])
        self.assertIn("len(capability_buffer), returned.value", argv[3])
        self.assertIn("if not appcontainer.value:", argv[3])
        self.assertNotIn("appcontainer.value != 1", argv[3])
        self.assertIn("'127.0.0.1', int(sys.argv[1]), 91, 92)", argv[3])
        self.assertIn("'::1', int(sys.argv[2]), 93, 94)", argv[3])
        self.assertIn("_failure_exit_code = connect_failure_exit_code", argv[3])
        self.assertIn("_failure_exit_code = send_failure_exit_code", argv[3])
        self.assertIn("sys.exit(_failure_exit_code)", argv[3])
        self.assertIn("import sys\n_failure_exit_code = 80", argv[3])
        self.assertLess(
            argv[3].index("import sys\n_failure_exit_code = 80"),
            argv[3].index("sys.excepthook = _stage_failure_hook"),
        )
        self.assertLess(
            argv[3].index("sys.excepthook = _stage_failure_hook"),
            argv[3].index("import ctypes, json, socket"),
        )

    def test_private_network正控只把未知SID分类到固定阶段码(self) -> None:
        namespace: dict[str, object] = {}
        exec(
            compile(
                windows_job_module._TOKEN_CAPABILITY_SID_CLASSIFIER_CODE,
                "<token-capability-sid-classifier>", "exec",
            ),
            namespace,
        )
        classify = namespace["_private_network_capability_sid_mismatch_exit_code"]
        cases = (
            ("S-1-15-3-1", 96),
            ("S-1-15-3-2", 97),
            ("S-1-15-3-4", 98),
            ("S-1-15-3-10", 98),
            ("S-1-15-3-1024-123456", 99),
            ("S-1-5-21-123456", 99),
            (None, 99),
        )
        for sid_text, expected in cases:
            with self.subTest(sid_text=sid_text):
                self.assertEqual(classify(sid_text), expected)

    def test_private_network正控仅在token句柄关闭失败时使用阶段103(self) -> None:
        argv = _build_private_network_capability_probe_argv(
            r"C:\actions\_temp\icode-runtime-staging-reviewer-fixed\python.exe",
            43123, 43124, "0123456789abcdef0123456789abcdef",
            "S-1-15-2-123456789-123456789-123456789-123456789",
        )
        probe_tree = ast.parse(argv[3])
        close_finally = next(
            node for node in ast.walk(probe_tree)
            if isinstance(node, ast.Try)
            and any(
                isinstance(descendant, ast.Call)
                and isinstance(descendant.func, ast.Attribute)
                and isinstance(descendant.func.value, ast.Name)
                and descendant.func.value.id == "kernel"
                and descendant.func.attr == "CloseHandle"
                for statement in node.finalbody
                for descendant in ast.walk(statement)
            )
        )
        close_program = compile(
            ast.Module(body=close_finally.finalbody, type_ignores=[]),
            "<private-network-token-close>", "exec",
        )

        for prior_stage in (88, 90, 95, 102):
            with self.subTest(outcome="closed", prior_stage=prior_stage):
                namespace = {
                    "sys": sys,
                    "_failure_exit_code": prior_stage,
                    "kernel": SimpleNamespace(CloseHandle=lambda _token: True),
                    "token": object(),
                }
                exec(close_program, namespace)
                self.assertEqual(namespace["_failure_exit_code"], prior_stage)

        for close_result, close_error in ((False, None), (None, OSError("close failed"))):
            with self.subTest(close_result=close_result, close_error=close_error):
                def close_handle(_token: object) -> bool:
                    if close_error is not None:
                        raise close_error
                    return bool(close_result)

                namespace = {
                    "sys": sys,
                    "_failure_exit_code": 90,
                    "kernel": SimpleNamespace(CloseHandle=close_handle),
                    "token": object(),
                }
                with self.assertRaises(RuntimeError if close_error is None else OSError):
                    exec(close_program, namespace)
                self.assertEqual(namespace["_failure_exit_code"], 103)

    def test_private_network能力正控只接受固定CI回环探针(self) -> None:
        environment = {
            "GITHUB_ACTIONS": "true",
            "RUNNER_OS": "Windows",
            "ICODE_DIAGNOSTIC_NETWORK_CAPABILITY": "true",
            "RUNNER_TEMP": r"C:\actions\_temp",
        }
        runtime = (
            r"C:\actions\_temp\icode-runtime-staging-reviewer-"
            "0123456789abcdef0123456789abcdef"
        )
        executable = runtime + r"\python.exe"
        workspace = (
            r"C:\actions\_temp\icode-reviewer-appcontainer-probe-fixed\task-scratch"
        )
        argv = _build_private_network_capability_probe_argv(
            executable, 43123, 43124, "0123456789abcdef0123456789abcdef",
            "S-1-15-2-123456789-123456789-123456789-123456789",
        )
        with mock.patch.dict(os.environ, environment, clear=True), \
             mock.patch(
                 "icode.windows_job.tempfile.gettempdir",
                 return_value=r"C:\actions\_temp",
             ):
            self.assertTrue(_is_fixed_private_network_capability_probe(argv, workspace))

            invalid_argv = (
                [argv[0], argv[1], argv[2],
                 "import socket; socket.create_connection(('1.1.1.1', 443))", *argv[4:]],
                [*argv[:-4], "0", *argv[-3:]],
                [*argv, "extra"],
            )
            for candidate in invalid_argv:
                with self.subTest(candidate=candidate):
                    self.assertFalse(
                        _is_fixed_private_network_capability_probe(candidate, workspace),
                    )
            self.assertFalse(
                _is_fixed_private_network_capability_probe(
                    argv, r"C:\actions\_work\repo\task-scratch",
                ),
            )

        with mock.patch.dict(
            os.environ,
            {**environment, "ICODE_DIAGNOSTIC_NETWORK_CAPABILITY": "false"},
            clear=True,
        ), mock.patch(
            "icode.windows_job.tempfile.gettempdir",
            return_value=r"C:\actions\_temp",
        ):
            self.assertFalse(_is_fixed_private_network_capability_probe(argv, workspace))

    def test_private_network能力入口拒绝非固定命令和错误能力数量(self) -> None:
        with temp_workspace() as workspace, \
             mock.patch("icode.windows_job.sys.platform", "win32"), \
             mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch("ctypes.WinDLL", create=True) as load_api:
            result = run_windows_job(
                [sys.executable, "-I", "-c", "pass"], cwd=workspace,
                timeout_seconds=2, _appcontainer_sid=123,
                _diagnostic_private_network_capability=True,
            )
        self.assertFalse(result.executed)
        self.assertEqual(result.error, "invalid_diagnostic_probe")
        load_api.assert_not_called()

    def test_private_network能力启动属性仅请求单一SID(self) -> None:
        from ctypes import wintypes

        api = mock.Mock()
        api.CreateJobObjectW.return_value = 1
        api.SetInformationJobObject.return_value = 1
        api.UpdateProcThreadAttribute.return_value = 1
        api.CreateProcessW.return_value = 0
        api.CloseHandle.return_value = 1
        api.LocalFree.side_effect = (0, 1)
        sid_storage = ctypes.create_string_buffer(16)

        def convert_capability_sid(_name: str, output: object) -> int:
            ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p)).contents.value = (
                ctypes.addressof(sid_storage)
            )
            return 1

        api.ConvertStringSidToSidW.side_effect = convert_capability_sid

        def initialize_attribute_list(
            attribute_list: object, _count: int, _flags: int, size: object,
        ) -> int:
            if attribute_list is None:
                ctypes.cast(size, ctypes.POINTER(ctypes.c_size_t)).contents.value = 64
                return 0
            return 1

        api.InitializeProcThreadAttributeList.side_effect = initialize_attribute_list
        observed: dict[str, int] = {}

        class SID_AND_ATTRIBUTES(ctypes.Structure):
            _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]

        class SECURITY_CAPABILITIES(ctypes.Structure):
            _fields_ = [
                ("AppContainerSid", ctypes.c_void_p),
                ("Capabilities", ctypes.POINTER(SID_AND_ATTRIBUTES)),
                ("CapabilityCount", wintypes.DWORD),
                ("Reserved", wintypes.DWORD),
            ]

        def observe_security_attribute(
            _attribute_list: object, _flags: int, attribute: int, payload: object,
            _size: int, _previous: object, _return_size: object,
        ) -> int:
            if attribute == 0x00020009:
                security = ctypes.cast(
                    payload, ctypes.POINTER(SECURITY_CAPABILITIES),
                ).contents
                observed["count"] = int(security.CapabilityCount)
                observed["reserved"] = int(security.Reserved)
                observed["sid"] = int(security.AppContainerSid or 0)
                observed["capability_sid"] = int(security.Capabilities[0].Sid or 0)
                observed["attributes"] = int(security.Capabilities[0].Attributes)
            return 1

        api.UpdateProcThreadAttribute.side_effect = observe_security_attribute
        environment = {
            "GITHUB_ACTIONS": "true",
            "RUNNER_OS": "Windows",
            "ICODE_DIAGNOSTIC_NETWORK_CAPABILITY": "true",
            "RUNNER_TEMP": r"C:\actions\_temp",
        }
        executable = (
            r"C:\actions\_temp\icode-runtime-staging-reviewer-"
            "0123456789abcdef0123456789abcdef\python.exe"
        )
        workspace = (
            r"C:\actions\_temp\icode-reviewer-appcontainer-probe-fixed\task-scratch"
        )
        argv = _build_private_network_capability_probe_argv(
            executable, 43123, 43124, "0123456789abcdef0123456789abcdef",
            "S-1-15-2-123456789-123456789-123456789-123456789",
        )
        with temp_workspace() as local_workspace, \
             mock.patch("icode.windows_job._is_fixed_private_network_capability_probe", return_value=True), \
             mock.patch("icode.windows_job.Path.is_absolute", return_value=True), \
             mock.patch("icode.windows_job.Path.is_file", return_value=True), \
             mock.patch("icode.windows_job.Path.resolve", return_value=local_workspace), \
             mock.patch("icode.windows_job.Path.is_dir", return_value=True), \
             mock.patch("icode.windows_job.sys.platform", "win32"), \
             mock.patch.dict(os.environ, environment, clear=True), \
             mock.patch("ctypes.WinDLL", return_value=api, create=True), \
             mock.patch("ctypes.set_last_error", create=True), \
             mock.patch(
                 "ctypes.get_last_error", side_effect=(122, 203, 122, 203), create=True,
             ), \
             mock.patch("ctypes.FormatError", return_value="expected test stop", create=True):
            result = run_windows_job(
                argv, cwd=workspace, timeout_seconds=2, _appcontainer_sid=123,
                _diagnostic_private_network_capability=True,
            )
            local_free_failure = run_windows_job(
                argv, cwd=workspace, timeout_seconds=2, _appcontainer_sid=123,
                _diagnostic_private_network_capability=True,
            )

        self.assertFalse(result.executed)
        self.assertEqual(result.error, "native_api_failed")
        self.assertTrue(result.cleanup_ok)
        self.assertFalse(local_free_failure.cleanup_ok)
        self.assertEqual(local_free_failure.error, "cleanup_failed")
        self.assertEqual(observed, {
            "count": 1, "reserved": 0, "sid": 123,
            "capability_sid": ctypes.addressof(sid_storage), "attributes": 0x00000004,
        })

    def test_FILE_STANDARD_INFO使用Win32BOOLEAN字段布局(self) -> None:
        standard_info = getattr(windows_job_module, "_FILE_STANDARD_INFO", None)
        self.assertIsNotNone(standard_info, "FILE_STANDARD_INFO layout is not exposed for validation")
        self.assertEqual(standard_info.DeletePending.offset, 20)
        self.assertEqual(standard_info.Directory.offset, 21)
        field_types = dict(standard_info._fields_)
        self.assertEqual(ctypes.sizeof(field_types["DeletePending"]), 1)
        self.assertEqual(ctypes.sizeof(field_types["Directory"]), 1)
        self.assertEqual(ctypes.sizeof(standard_info), 24)

    @unittest.skipUnless(sys.platform == "win32", "需 Windows 文件句柄原生验证")
    def test_只读句柄拒绝目录句柄(self) -> None:
        from ctypes import wintypes

        with temp_workspace() as workspace:
            probe = workspace / "icode-appcontainer-read-probe.exe"
            probe.write_bytes(b"directory-handle-test-placeholder")
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.CreateFileW.argtypes = [
                wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
            ]
            kernel.CreateFileW.restype = wintypes.HANDLE
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel.CloseHandle.restype = wintypes.BOOL
            directory_handle = kernel.CreateFileW(
                str(workspace), 0x80000000, 0x00000007, None,
                3, 0x02000000 | 0x00000080, None,
            )
            self.assertTrue(directory_handle)
            try:
                with mock.patch.dict(
                    os.environ,
                    {
                        "GITHUB_ACTIONS": "true",
                        "RUNNER_OS": "Windows",
                        "ICODE_DIAGNOSTIC_READ_HANDLE": "true",
                    },
                ):
                    result = run_windows_job(
                        [str(probe), "--input-handle", windows_job_module._READ_HANDLE_PLACEHOLDER],
                        cwd=workspace, timeout_seconds=2, _appcontainer_sid=123,
                        _diagnostic_read_handle=int(directory_handle),
                    )
            finally:
                kernel.CloseHandle(directory_handle)

        self.assertFalse(result.executed)
        self.assertEqual(result.error, "invalid_diagnostic_probe")

    def test_AppContainer只读句柄占位符绑定到精确继承句柄值(self) -> None:
        bind = getattr(windows_job_module, "_bind_read_handle_placeholder", None)
        self.assertTrue(callable(bind), "AppContainer read-handle binding is not implemented")
        placeholder = windows_job_module._READ_HANDLE_PLACEHOLDER
        self.assertEqual(
            bind(["reader.exe", "--input-handle", placeholder], 0x1234),
            ["reader.exe", "--input-handle", "4660"],
        )

    def test_AppContainer只读句柄占位符拒绝缺失重复和非法句柄(self) -> None:
        bind = getattr(windows_job_module, "_bind_read_handle_placeholder", None)
        self.assertTrue(callable(bind), "AppContainer read-handle binding is not implemented")
        placeholder = windows_job_module._READ_HANDLE_PLACEHOLDER
        invalid = (
            ([], 0x1234),
            (["reader.exe", placeholder, placeholder], 0x1234),
            (["reader.exe", f"--handle={placeholder}"], 0x1234),
            (["reader.exe", placeholder], 0),
            (["reader.exe", placeholder], -1),
            (["reader.exe", placeholder], True),
        )
        for argv, handle_value in invalid:
            with self.subTest(argv=argv, handle_value=handle_value):
                with self.assertRaises(ValueError):
                    bind(argv, handle_value)

    def test_只读句柄不允许脱离AppContainer或留下未绑定占位符(self) -> None:
        placeholder = windows_job_module._READ_HANDLE_PLACEHOLDER
        with temp_workspace() as workspace, \
             mock.patch("icode.windows_job.sys.platform", "win32"), \
             mock.patch("ctypes.WinDLL", create=True) as load_api:
            without_appcontainer = run_windows_job(
                [sys.executable, "--input-handle", placeholder],
                cwd=workspace, timeout_seconds=2, _diagnostic_read_handle=123,
            )
            unbound_placeholder = run_windows_job(
                [sys.executable, "--input-handle", placeholder],
                cwd=workspace, timeout_seconds=2,
            )

        for result in (without_appcontainer, unbound_placeholder):
            self.assertFalse(result.executed)
            self.assertEqual(result.error, "invalid_diagnostic_probe")
        load_api.assert_not_called()

    def test_底层只读句柄入口拒绝绕过固定GitHub探针门(self) -> None:
        placeholder = windows_job_module._READ_HANDLE_PLACEHOLDER
        with temp_workspace() as workspace, \
             mock.patch("icode.windows_job.sys.platform", "win32"), \
             mock.patch.dict(
                 os.environ,
                 {
                     "GITHUB_ACTIONS": "true",
                     "RUNNER_OS": "Windows",
                     "ICODE_DIAGNOSTIC_READ_HANDLE": "true",
                 },
                 clear=True,
             ), mock.patch(
                 "ctypes.WinDLL", side_effect=OSError(5, "expected test stop"), create=True,
             ) as load_api:
            result = run_windows_job(
                [sys.executable, "--input-handle", placeholder],
                cwd=workspace, timeout_seconds=2, _appcontainer_sid=123,
                _diagnostic_read_handle=456,
            )

        self.assertFalse(result.executed)
        self.assertEqual(result.error, "invalid_diagnostic_probe")
        load_api.assert_not_called()

    def test_普通WindowsJob创建进程时不继承宿主句柄(self) -> None:
        api = mock.Mock()
        api.CreateJobObjectW.return_value = 1
        api.SetInformationJobObject.return_value = 1
        api.CreateProcessW.return_value = 0
        api.CloseHandle.return_value = 1
        with temp_workspace() as workspace, \
             mock.patch("icode.windows_job.sys.platform", "win32"), \
             mock.patch("ctypes.WinDLL", return_value=api, create=True), \
             mock.patch("ctypes.get_last_error", return_value=0, create=True):
            result = run_windows_job(
                [sys.executable], cwd=workspace, timeout_seconds=2,
            )

        self.assertFalse(result.executed)
        self.assertTrue(result.cleanup_ok)
        self.assertEqual(result.error, "native_api_failed")
        self.assertIs(api.CreateProcessW.call_args.args[4], False)

    def test_AppContainer属性列表缓冲区有足够大小并按指针对齐(self) -> None:
        import ctypes

        for required_size in (1, 37, 64):
            with self.subTest(required_size=required_size):
                storage, pointer = _allocate_attribute_list_buffer(required_size)
                self.assertGreaterEqual(ctypes.sizeof(storage), required_size)
                self.assertEqual(
                    pointer.value % ctypes.sizeof(ctypes.c_void_p), 0,
                )

    def test_AppContainer属性列表拒绝非正大小(self) -> None:
        for required_size in (0, -1):
            with self.subTest(required_size=required_size):
                with self.assertRaises(ValueError):
                    _allocate_attribute_list_buffer(required_size)

    def test_lpApplicationName诊断仅允许固定whoami绝对路径(self) -> None:
        system_root = r"C:\Windows"
        accepted = (
            [r"C:\Windows\System32\whoami.exe"],
            [r"c:\windows\SYSTEM32\whoami.exe"],
        )
        for argv in accepted:
            with self.subTest(argv=argv):
                self.assertTrue(_is_fixed_system_whoami_probe(argv, system_root))

        rejected = (
            [],
            [r"C:\Windows\System32\whoami.exe", "/all"],
            [r"C:\Windows\System32\cmd.exe"],
            [r"C:\Windows\System32\..\whoami.exe"],
            [r"System32\whoami.exe"],
            [r"D:\Windows\System32\whoami.exe"],
        )
        for argv in rejected:
            with self.subTest(argv=argv):
                self.assertFalse(_is_fixed_system_whoami_probe(argv, system_root))

    def test_lpApplicationName诊断拒绝普通Job和其它可执行文件(self) -> None:
        with temp_workspace() as workspace, \
             mock.patch("icode.windows_job.sys.platform", "win32"), \
             mock.patch("icode.windows_job.Path.is_absolute", return_value=True), \
             mock.patch("icode.windows_job.Path.is_file", return_value=True), \
             mock.patch("ctypes.WinDLL", create=True) as load_api:
            ordinary_job = run_windows_job(
                [r"C:\Windows\System32\whoami.exe"], cwd=workspace,
                timeout_seconds=2, _diagnostic_null_application_name=True,
            )
            other_executable = run_windows_job(
                [sys.executable], cwd=workspace, timeout_seconds=2,
                _appcontainer_sid=123, _diagnostic_null_application_name=True,
            )
        for result in (ordinary_job, other_executable):
            self.assertFalse(result.executed)
            self.assertEqual(result.error, "invalid_diagnostic_probe")
        load_api.assert_not_called()

    def test_lpApplicationName诊断仅将NULL传给固定AppContainer探针(self) -> None:
        import ctypes

        api = mock.Mock()
        api.CreateJobObjectW.return_value = 1
        api.SetInformationJobObject.return_value = 1
        api.UpdateProcThreadAttribute.return_value = 1
        api.CreateProcessW.return_value = 0
        api.CloseHandle.return_value = 1

        def initialize_attribute_list(
            attribute_list: object, count: int, flags: int, size: object,
        ) -> int:
            if attribute_list is None:
                ctypes.cast(size, ctypes.POINTER(ctypes.c_size_t)).contents.value = 64
                return 0
            return 1

        api.InitializeProcThreadAttributeList.side_effect = initialize_attribute_list
        with temp_workspace() as workspace, \
             mock.patch("icode.windows_job.sys.platform", "win32"), \
             mock.patch("icode.windows_job.Path.is_absolute", return_value=True), \
             mock.patch("icode.windows_job.Path.is_file", return_value=True), \
             mock.patch("icode.windows_job.Path.resolve", return_value=Path(r"C:\task")), \
             mock.patch("icode.windows_job.Path.is_dir", return_value=True), \
             mock.patch("ctypes.WinDLL", return_value=api, create=True), \
             mock.patch("ctypes.set_last_error", create=True), \
             mock.patch("ctypes.get_last_error", side_effect=(122, 203), create=True), \
             mock.patch("ctypes.FormatError", return_value="diagnostic failure", create=True):
            result = run_windows_job(
                [r"C:\Windows\System32\whoami.exe"], cwd=workspace,
                timeout_seconds=2, _appcontainer_sid=123,
                _diagnostic_null_application_name=True,
            )

        self.assertEqual(result.error, "native_api_failed")
        self.assertTrue(result.cleanup_ok)
        create_args = api.CreateProcessW.call_args.args
        self.assertIsNone(create_args[0])
        self.assertIn("C:\\Windows\\System32\\whoami.exe", ctypes.wstring_at(create_args[1]))
        self.assertEqual(create_args[5], 0x00080404)

    def test_自定义环境块保留驱动器目录但不继承宿主变量(self) -> None:
        block = _build_windows_environment_block(
            r"D:\Python\python.exe", r"E:\tickets\task-1", r"D:\Windows",
        )
        entries = [entry for entry in block.split("\0") if entry]
        names = [
            entry[:entry.index("=", 1)] if entry.startswith("=")
            else entry.split("=", 1)[0]
            for entry in entries
        ]
        self.assertTrue(block.endswith("\0\0"))
        self.assertEqual(names, sorted(names, key=str.casefold))
        self.assertEqual(entries[0], "=D:=D:\\")
        self.assertEqual(entries[1], r"=E:=E:\tickets\task-1")
        self.assertIn(r"D:\Python;D:\Windows\System32", block)
        self.assertNotIn("OPENAI_API_KEY", block)
        self.assertNotIn("GIT_DIR", block)

    def test_只追加LOCALAPPDATA时其它环境项保持不变(self) -> None:
        baseline = _build_windows_environment_block(
            r"C:\Windows\System32\whoami.exe", r"C:\tickets\task-1", r"C:\Windows",
        )
        candidate = _append_windows_environment_value(
            baseline, "LOCALAPPDATA", r"C:\Users\runner\AppData\Local\Packages\icode\AC",
        )

        def parse(block: str) -> dict[str, str]:
            entries: dict[str, str] = {}
            for entry in block.split("\0"):
                if not entry:
                    continue
                separator = entry.index("=", 1) if entry.startswith("=") else entry.index("=")
                entries[entry[:separator]] = entry[separator + 1:]
            return entries

        baseline_entries = parse(baseline)
        candidate_entries = parse(candidate)
        self.assertNotIn("LOCALAPPDATA", baseline_entries)
        self.assertEqual(
            {key: value for key, value in candidate_entries.items() if key != "LOCALAPPDATA"},
            baseline_entries,
        )
        self.assertEqual(
            candidate_entries["LOCALAPPDATA"],
            r"C:\Users\runner\AppData\Local\Packages\icode\AC",
        )

    def test_AppContainer_LOCALAPPDATA要求有效SID和绝对路径(self) -> None:
        with temp_workspace() as workspace, \
             mock.patch("icode.windows_job.sys.platform", "win32"), \
             mock.patch("icode.windows_job.Path.is_absolute", return_value=True), \
             mock.patch("icode.windows_job.Path.is_file", return_value=True), \
             mock.patch("ctypes.WinDLL", create=True) as load_api:
            ordinary_job = run_windows_job(
                [r"C:\Windows\System32\whoami.exe"], cwd=workspace,
                timeout_seconds=2, _appcontainer_localappdata=r"C:\sandbox\profile",
            )
            relative_profile = run_windows_job(
                [r"C:\Python\python.exe"], cwd=workspace,
                timeout_seconds=2, _appcontainer_sid=123,
                _appcontainer_localappdata="relative-profile",
            )
        for result in (ordinary_job, relative_profile):
            self.assertFalse(result.executed)
            self.assertEqual(result.error, "invalid_diagnostic_probe")
        load_api.assert_not_called()

    @unittest.skipUnless(sys.platform == "win32", "需 Windows Job Object 实测")
    def test_空环境块下普通Job可启动系统程序(self) -> None:
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        executable = system_root / "System32" / "whoami.exe"
        with temp_workspace() as workspace, mock.patch(
            "icode.windows_job._build_windows_environment_block", return_value="\0\0",
        ):
            result = run_windows_job([str(executable)], cwd=workspace, timeout_seconds=10)
        if os.environ.get("GITHUB_ACTIONS") == "true":
            detail = (
                result.detail[:300].replace("%", "%25")
                .replace("\r", "%0D").replace("\n", "%0A")
            )
            print(
                "::notice title=R2.3 ordinary Job empty-environment control::"
                f"executed={result.executed} exit={result.exit_code} error={result.error} "
                f"cleanup={result.cleanup_ok} detail={detail}",
                flush=True,
            )
        self.assertTrue(result.executed, result)
        self.assertEqual(result.exit_code, 0, result)
        self.assertTrue(result.cleanup_ok, result)

    def test_非_windows_不能运行(self) -> None:
        if sys.platform == "win32":
            self.skipTest("仅校验非 Windows 拒绝")
        result = run_windows_job([sys.executable, "-V"], cwd=os.getcwd(), timeout_seconds=2)
        self.assertFalse(result.executed)
        self.assertFalse(result.cleanup_ok)
        probe = probe_windows_job_cleanup()
        self.assertFalse(probe.executed)
        self.assertFalse(probe.passed)

    def test_CreateProcess失败时保留原始错误且不误报清理失败(self) -> None:
        api = mock.Mock()
        api.CreateJobObjectW.return_value = 1
        api.SetInformationJobObject.return_value = 1
        api.CreateProcessW.return_value = 0
        api.CloseHandle.return_value = 1
        with temp_workspace() as workspace, \
             mock.patch("icode.windows_job.sys.platform", "win32"), \
             mock.patch("ctypes.WinDLL", return_value=api, create=True), \
             mock.patch("ctypes.get_last_error", return_value=203, create=True), \
             mock.patch("ctypes.FormatError", return_value="environment missing", create=True):
            result = run_windows_job(
                [sys.executable], cwd=workspace, timeout_seconds=2,
            )
        self.assertFalse(result.executed)
        self.assertEqual(result.error, "native_api_failed")
        self.assertTrue(result.cleanup_ok)
        self.assertIn("err=203", result.detail)
        self.assertEqual(api.CreateProcessW.call_args.args[0], sys.executable)

    def test_AppContainer启动环境保留盘符伪变量(self) -> None:
        import ctypes

        api = mock.Mock()
        api.CreateJobObjectW.return_value = 1
        api.SetInformationJobObject.return_value = 1
        attribute_addresses: list[int] = []

        def initialize_attribute_list(
            attribute_list: object, count: int, flags: int, size: object,
        ) -> int:
            if attribute_list is None:
                ctypes.cast(size, ctypes.POINTER(ctypes.c_size_t)).contents.value = 64
                return 0
            address = ctypes.cast(attribute_list, ctypes.c_void_p).value
            attribute_addresses.append(address or 0)
            return 1

        api.InitializeProcThreadAttributeList.side_effect = initialize_attribute_list
        api.UpdateProcThreadAttribute.return_value = 1
        environment: dict[str, str] = {}

        def fail_create_process(*args: object) -> int:
            block = args[6]
            environment["block"] = ctypes.wstring_at(
                ctypes.addressof(block), len(block),
            )
            return 0

        api.CreateProcessW.side_effect = fail_create_process
        api.CloseHandle.return_value = 1
        with temp_workspace() as workspace, \
             mock.patch("icode.windows_job.Path.resolve", return_value=Path("C:\\task")), \
             mock.patch("icode.windows_job.Path.is_dir", return_value=True), \
             mock.patch("icode.windows_job.sys.platform", "win32"), \
             mock.patch("ctypes.WinDLL", return_value=api, create=True), \
             mock.patch("ctypes.set_last_error", create=True), \
             mock.patch("ctypes.get_last_error", side_effect=(122, 203), create=True), \
             mock.patch("ctypes.FormatError", return_value="environment missing", create=True):
            result = run_windows_job(
                [sys.executable], cwd=workspace, timeout_seconds=2,
                _appcontainer_sid=123,
            )
        self.assertEqual(result.error, "native_api_failed")
        self.assertEqual(len(attribute_addresses), 1)
        self.assertEqual(
            attribute_addresses[0] % ctypes.sizeof(ctypes.c_void_p), 0,
        )
        self.assertIn("attr_size_query_expected=True", result.detail)
        self.assertIn("attr_size_query_error=122", result.detail)
        self.assertIn("attr_init_ok=True", result.detail)
        self.assertIn("security_attribute=0x00020009", result.detail)
        self.assertIn("attr_update_ok=True", result.detail)
        self.assertIn("flags=0x00080404", result.detail)
        entries = [entry for entry in environment["block"].split("\0") if entry]
        self.assertIn(r"=C:=C:\task", entries)
        system_root = os.environ.get("SystemRoot", "C:\\Windows")
        self.assertIn(f"SystemRoot={system_root}", entries)
        self.assertTrue(any(entry.startswith("PATH=") for entry in entries))

    def test_局部自检启动失败不能误报通过(self) -> None:
        failed = WindowsJobResult(False, None, "job_creation_failed", False, "failed")
        with mock.patch("icode.windows_job.sys.platform", "win32"), \
             mock.patch("icode.windows_job.run_windows_job", return_value=failed) as launch:
            probe = probe_windows_job_cleanup()
        self.assertEqual(launch.call_count, 2)
        self.assertTrue(probe.executed)
        self.assertFalse(probe.passed)
        self.assertEqual(probe.checks, {"normal_exit": False, "timeout": False})

    @unittest.skipUnless(sys.platform == "win32", "需 Windows Job Object 实测")
    def test_正常退出与超时均回收后代(self) -> None:
        with temp_workspace() as workspace:
            for mode, delay, timeout in (("normal", 1.5, 5), ("timeout", 3, 1)):
                started = workspace / f"{mode}-started"
                residue = workspace / f"{mode}-residue"
                child_code = (
                    "import time\nfrom pathlib import Path\n"
                    f"Path({str(started)!r}).write_text('ready')\n"
                    f"time.sleep({delay})\n"
                    f"Path({str(residue)!r}).write_text('late')\n"
                )
                parent_code = (
                    "import subprocess, sys, time\nfrom pathlib import Path\n"
                    f"subprocess.Popen([sys.executable, '-c', {child_code!r}], "
                    "creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)\n"
                    f"for _ in range(200):\n    if Path({str(started)!r}).exists(): break\n"
                    "    time.sleep(0.01)\n"
                    "else: raise RuntimeError('child did not start')\n"
                    + ("time.sleep(8)\n" if mode == "timeout" else "")
                )
                result = run_windows_job(
                    [sys.executable, "-c", parent_code],
                    cwd=workspace, timeout_seconds=timeout,
                )
                self.assertTrue(result.executed, result)
                self.assertTrue(started.is_file(), result)
                self.assertTrue(result.cleanup_ok, result)
                self.assertEqual(result.error, "timeout" if mode == "timeout" else None)
                time.sleep(delay + 0.2)
                self.assertFalse(residue.exists(), result)

    @unittest.skipUnless(sys.platform == "win32", "需 Windows Job Object 实测")
    def test_局部自检不冒充完整沙箱(self) -> None:
        from icode.isolation import capability_report

        report = capability_report()
        probe = report["windows_job_cleanup"]
        self.assertTrue(probe["executed"])
        self.assertEqual(probe["checks"], {"normal_exit": True, "timeout": True})
        self.assertTrue(probe["passed"], probe["detail"])
        # Scoring is executed, but a Job-only cleanup probe is not a complete
        # backend self-test or process-tree cleanup proof.
        contract = report["conformance_contract"]
        self.assertTrue(contract["executed"])
        self.assertFalse(contract["outcomes"]["doctor_self_test"])
        self.assertFalse(contract["outcomes"]["process_tree_cleanup"])

    @unittest.skipUnless(sys.platform == "win32", "需 Windows Job Object 崩溃实测")
    def test_宿主崩溃关闭job句柄也回收后代(self) -> None:
        with temp_workspace() as workspace:
            started = workspace / "crash-started"
            residue = workspace / "crash-residue"
            child_code = (
                "import time\nfrom pathlib import Path\n"
                f"Path({str(started)!r}).write_text('ready')\n"
                "time.sleep(2)\n"
                f"Path({str(residue)!r}).write_text('late')\n"
            )
            task_code = (
                "import subprocess, sys, time\n"
                f"subprocess.Popen([sys.executable, '-c', {child_code!r}], "
                "creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)\n"
                "time.sleep(8)\n"
            )
            source = Path(__file__).resolve().parents[1] / "src"
            broker_code = (
                "import sys\n"
                f"sys.path.insert(0, {str(source)!r})\n"
                "from icode.windows_job import run_windows_job\n"
                f"run_windows_job([sys.executable, '-c', {task_code!r}], "
                f"cwd={str(workspace)!r}, timeout_seconds=15)\n"
            )
            broker = subprocess.Popen(
                [sys.executable, "-c", broker_code], cwd=workspace,
                env={
                    "SystemRoot": os.environ.get("SystemRoot", r"C:\Windows"),
                    "PATH": str(Path(sys.executable).parent),
                    "PYTHONUTF8": "1",
                },
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                until = time.monotonic() + 5
                while time.monotonic() < until and not started.is_file():
                    if broker.poll() is not None:
                        self.fail("Job broker exited before descendant startup")
                    time.sleep(0.02)
                self.assertTrue(started.is_file(), "Job descendant did not start")
            finally:
                if broker.poll() is None:
                    broker.kill()
                broker.wait(timeout=5)
            time.sleep(2.2)
            self.assertFalse(residue.exists(), "Broker crash left a Job descendant alive")


if __name__ == "__main__":
    unittest.main()
