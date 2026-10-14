"""Portable tests of fixed private-connect code; no native isolation credit."""
import ast
import socket
import sys
import types
import unittest
from unittest import mock

from tests import _support  # noqa: F401
from icode import windows_job as job
from tests import test_windows_appcontainer as app_tests


def os_error(value, source="winerror"):
    error = OSError(13, "private synthetic message")
    error.winerror = value if source == "winerror" else None
    error.errno = value if source == "errno" else 13
    return error


class UnreadableWinerror(OSError):
    @property
    def winerror(self):
        raise ValueError("private property failure")


class UnreadableErrno(OSError):
    @property
    def errno(self):
        raise ValueError("private property failure")


def classifier():
    namespace = {"__builtins__": __builtins__}
    exec(compile(job._PRIVATE_NETWORK_CONNECT_CLASSIFIER_CODE,
                 "<actual-private-connect-classifier>", "exec"), namespace)
    return namespace["_private_network_connect_failure_exit_code"]


def actual_network_code():
    tree = ast.parse(job._PRIVATE_NETWORK_CAPABILITY_PROBE_CODE)
    loops = [node for node in tree.body if isinstance(node, ast.For)
             and isinstance(node.target, ast.Tuple)
             and [item.id for item in node.target.elts] == [
                 "family", "address", "port", "connect_failure_exit_code",
                 "send_failure_exit_code"]]
    if len(loops) != 1:
        raise AssertionError("fixed network loop missing or ambiguous")
    module = ast.Module(body=[loops[0]], type_ignores=[])
    return compile(ast.fix_missing_locations(module), "<actual-network-loop>", "exec")


def run_network(fault=None, family=socket.AF_INET, phase="connect", cleanup_fault=None):
    events = []

    class Connection:
        def __init__(self, current):
            self.family = current

        def trip(self, current_phase):
            if fault is not None and self.family == family and phase == current_phase:
                raise fault

        def __enter__(self):
            events.append((self.family, "enter"))
            self.trip("enter")
            return self

        def settimeout(self, seconds):
            events.append((self.family, "timeout", seconds))
            self.trip("timeout")

        def connect(self, target):
            events.append((self.family, "connect", target))
            self.trip("connect")

        def sendall(self, payload):
            events.append((self.family, "send", payload))
            self.trip("send")

        def __exit__(self, *exc):
            events.append((self.family, "close"))
            if cleanup_fault is not None and self.family == family:
                raise cleanup_fault
            self.trip("close")
            return False

    def create(current, kind):
        events.append((current, "create", kind))
        if fault is not None and current == family and phase == "create":
            raise fault
        return Connection(current)

    fake_socket = types.SimpleNamespace(
        AF_INET=socket.AF_INET, AF_INET6=socket.AF_INET6,
        SOCK_STREAM=socket.SOCK_STREAM, socket=create,
    )
    namespace = {
        "__builtins__": __builtins__, "socket": fake_socket,
        "sys": types.SimpleNamespace(argv=["-c", "43123", "43124"]),
        "payload": b"unchanged-parent-nonce-token-payload",
        "_failure_exit_code": 104,
        "_private_network_connect_failure_exit_code": classifier(),
    }
    error = None
    try:
        exec(actual_network_code(), namespace)
    except BaseException as caught:  # observer only; assert exact object below
        error = caught
    return events, namespace, error


class TestPrivateConnectDiagnostic(unittest.TestCase):
    def test_timeout_classification_target(self):
        self.assertEqual(classifier()(91, TimeoutError("private")), 105)
        self.assertEqual(classifier()(93, socket.timeout("private")), 112)

    def test_classifier_matrix(self):
        classify = classifier()
        for base, offset in ((91, 0), (93, 7)):
            for source, start in (("winerror", 106), ("errno", 109)):
                for index, value in enumerate((10013, 10035, 10060)):
                    with self.subTest(base=base, source=source, value=value):
                        self.assertEqual(classify(base, os_error(value, source)),
                                         start + offset + index)
            for source in ("winerror", "errno"):
                for value in (True, False, "10013", 10013.0, -1,
                              13, 0, 10061, 2 ** 80):
                    self.assertEqual(classify(base, os_error(value, source)), base)
            for error in (ValueError("private"), UnreadableWinerror(),
                          UnreadableErrno(), OSError(13, "private")):
                self.assertEqual(classify(base, error), base)
            precedence = os_error(10035)
            precedence.errno = 10013
            self.assertEqual(classify(base, precedence), 107 + offset)
            precedence.winerror = 10061
            self.assertEqual(classify(base, precedence), base)
        for bad in (True, False, "91", 91.0, None, 92, 2 ** 80):
            self.assertEqual(classify(bad, TimeoutError()), 91)
        for signal in (KeyboardInterrupt("private"), SystemExit(44)):
            with self.assertRaises(type(signal)) as captured:
                classify(91, signal)
            self.assertIs(captured.exception, signal)

    def test_actual_loop_timeout_target(self):
        for family, expected in ((socket.AF_INET, 105), (socket.AF_INET6, 112)):
            events, namespace, error = run_network(TimeoutError(), family)
            self.assertIsInstance(error, SystemExit)
            self.assertEqual(error.code, expected)
            self.assertEqual(events[-1], (family, "close"))
            self.assertEqual(namespace["_failure_exit_code"],
                             91 if family == socket.AF_INET else 93)
            self.assertFalse(any(item[:2] == (family, "send") for item in events))

    def test_actual_loop_all_classified_connect_errors(self):
        for family, offset in ((socket.AF_INET, 0), (socket.AF_INET6, 7)):
            for source, start in (("winerror", 106), ("errno", 109)):
                for index, value in enumerate((10013, 10035, 10060)):
                    events, _, error = run_network(os_error(value, source), family)
                    self.assertIsInstance(error, SystemExit)
                    self.assertEqual(error.code, start + offset + index)
                    self.assertEqual(events[-1], (family, "close"))

    def test_success_keeps_both_families_and_payload_order(self):
        events, namespace, error = run_network()
        self.assertIsNone(error)
        self.assertEqual(events, [
            (socket.AF_INET, "create", socket.SOCK_STREAM),
            (socket.AF_INET, "enter"), (socket.AF_INET, "timeout", 3),
            (socket.AF_INET, "connect", ("127.0.0.1", 43123)),
            (socket.AF_INET, "send", namespace["payload"]),
            (socket.AF_INET, "close"),
            (socket.AF_INET6, "create", socket.SOCK_STREAM),
            (socket.AF_INET6, "enter"), (socket.AF_INET6, "timeout", 3),
            (socket.AF_INET6, "connect", ("::1", 43124)),
            (socket.AF_INET6, "send", namespace["payload"]),
            (socket.AF_INET6, "close"),
        ])

    def test_nonconnect_faults_keep_original_stage_hook(self):
        tree = ast.parse(job._PRIVATE_NETWORK_CAPABILITY_PROBE_CODE)
        hook = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "_stage_failure_hook")
        hook_code = compile(ast.Module(body=[hook], type_ignores=[]), "<actual-hook>", "exec")
        for family, connect_stage, send_stage in (
                (socket.AF_INET, 91, 92), (socket.AF_INET6, 93, 94)):
            for phase in ("create", "enter", "timeout", "send", "close"):
                fault = TimeoutError("private")
                _, namespace, error = run_network(fault, family, phase)
                self.assertIs(error, fault)
                namespace["sys"] = types.SimpleNamespace(
                    exit=sys.exit, __excepthook__=mock.Mock())
                exec(hook_code, namespace)
                with self.assertRaises(SystemExit) as captured:
                    namespace["_stage_failure_hook"](type(error), error, None)
                self.assertEqual(captured.exception.code,
                                 send_stage if phase in ("send", "close") else connect_stage)

    def test_connect_unknown_and_cleanup_masking_remain_legacy(self):
        for family, base in ((socket.AF_INET, 91), (socket.AF_INET6, 93)):
            _, _, error = run_network(OSError(13, "private"), family)
            self.assertIsInstance(error, SystemExit)
            self.assertEqual(error.code, base)
        # Exercise actual with cleanup: a close fault supersedes the pending
        # classifier result, so only the original ordinary-exception hook applies.
        for family, base in ((socket.AF_INET, 91), (socket.AF_INET6, 93)):
            close_fault = ValueError("private close")
            events, namespace, error = run_network(
                TimeoutError(), family, cleanup_fault=close_fault)
            self.assertIs(error, close_fault)
            self.assertEqual(events[-1], (family, "close"))
            self.assertEqual(namespace["_failure_exit_code"], base)

    def test_signals_propagate_exact_object(self):
        for family in (socket.AF_INET, socket.AF_INET6):
            for phase in ("create", "enter", "timeout", "connect", "send", "close"):
                for signal in (KeyboardInterrupt("private"), SystemExit(44)):
                    events, _, error = run_network(signal, family=family, phase=phase)
                    self.assertIs(error, signal)
                    if phase in ("timeout", "connect", "send", "close"):
                        self.assertEqual(events[-1], (family, "close"))

    def test_fixed_probe_and_finite_translator(self):
        mapping = job._PRIVATE_NETWORK_CAPABILITY_EXIT_STAGES
        self.assertEqual(set(mapping), {0, *range(80, 119)})
        self.assertEqual(len(mapping.values()), len(set(mapping.values())))
        self.assertTrue(all(type(key) is int and 0 <= key <= 255 for key in mapping))
        legacy = {
            0: "probe_completed", 80: "probe_initialization", 81: "token_open",
            82: "token_appcontainer", 83: "token_package_sid",
            84: "token_capabilities", 85: "token_package_sid_text",
            86: "token_capability_sid_text", 87: "token_appcontainer_match",
            88: "token_package_sid_match", 89: "token_capability_sid_match",
            90: "token_capability_enabled_missing_zero_attributes",
            91: "ipv4_connect", 92: "ipv4_send", 93: "ipv6_connect", 94: "ipv6_send",
            95: "token_capability_enabled_missing_nonzero_attributes",
            96: "token_capability_sid_internet_client",
            97: "token_capability_sid_internet_client_server",
            98: "token_capability_sid_other_well_known",
            99: "token_capability_sid_unrecognized",
            100: "token_capability_sid_classifier_error",
            101: "token_capability_enabled_check", 102: "token_capability_payload",
            103: "token_handle_close", 104: "network_probe_setup",
        }
        self.assertEqual({code: mapping[code] for code in legacy}, legacy)
        added = {
            105: "ipv4_connect_timeout", 106: "ipv4_connect_winerror_10013",
            107: "ipv4_connect_winerror_10035", 108: "ipv4_connect_winerror_10060",
            109: "ipv4_connect_errno_10013", 110: "ipv4_connect_errno_10035",
            111: "ipv4_connect_errno_10060", 112: "ipv6_connect_timeout",
            113: "ipv6_connect_winerror_10013", 114: "ipv6_connect_winerror_10035",
            115: "ipv6_connect_winerror_10060", 116: "ipv6_connect_errno_10013",
            117: "ipv6_connect_errno_10035", 118: "ipv6_connect_errno_10060",
        }
        self.assertEqual({code: mapping[code] for code in added}, added)
        argv = job._build_private_network_capability_probe_argv(
            r"C:\temp\icode-runtime-staging-reviewer-test\python.exe",
            43123, 43124, "0" * 32, "S-1-15-2-123")
        self.assertEqual(argv[1:3], ["-I", "-c"])
        self.assertEqual(argv[3], job._PRIVATE_NETWORK_CAPABILITY_PROBE_CODE)
        self.assertEqual(argv[4:], ["43123", "43124", "0" * 32, "S-1-15-2-123"])
        self.assertIn(job._PRIVATE_NETWORK_CONNECT_CLASSIFIER_CODE, argv[3])
        cwd = r"C:\temp\icode-reviewer-appcontainer-probe-test\task-scratch"
        with mock.patch.dict(job.os.environ, {
                "GITHUB_ACTIONS": "true", "RUNNER_OS": "Windows",
                "ICODE_DIAGNOSTIC_NETWORK_CAPABILITY": "true"}, clear=True), \
             mock.patch.object(job.tempfile, "gettempdir", return_value=r"C:\temp"):
            self.assertTrue(job._is_fixed_private_network_capability_probe(argv, cwd))
            altered = list(argv)
            altered[3] += "\npass\n"
            self.assertFalse(job._is_fixed_private_network_capability_probe(altered, cwd))
        for code in range(105, 119):
            self.assertNotEqual(job._private_network_capability_exit_stage(code), "unclassified")
        for value in (True, "105", 119, -1, 2 ** 80):
            self.assertEqual(job._private_network_capability_exit_stage(value), "unclassified")
        self.assertEqual(job._private_network_capability_exit_stage(None), "no_exit_code")

    def test_attribute_signal_is_not_swallowed(self):
        for attribute in ("winerror", "errno"):
            for signal in (KeyboardInterrupt("private"), SystemExit(44)):
                def fail_read(self):
                    raise signal
                error_type = type("SignalOSError", (OSError,), {
                    attribute: property(fail_read)})
                error = error_type()
                for base in (91, 93):
                    with self.assertRaises(type(signal)) as captured:
                        classifier()(base, error)
                    self.assertIs(captured.exception, signal)

    def test_real_notice_budget_enumerates_actual_mapping(self):
        method = app_tests.TestWindowsAppContainer.test_Reviewer快照原生探针脚本在非Windows主机可静态解析
        # The original method uses its real combined maximum-field fixture.
        # Do not recreate or weaken that fixture or increase the transport budget.
        import inspect
        source = inspect.getsource(method)
        self.assertIn("for code in windows_job_module._PRIVATE_NETWORK_CAPABILITY_EXIT_STAGES", source)
        for label in (
            "positive_loopback_config_pre",
            "positive_loopback_config_post",
            "positive_loopback_config_comparison",
        ):
            self.assertIn(label, source)
        case = app_tests.TestWindowsAppContainer(method.__name__)
        result = unittest.TestResult()
        case.run(result)
        self.assertEqual(result.testsRun, 1)
        self.assertFalse(result.errors)
        self.assertFalse(result.failures)
        self.assertFalse(result.skipped)
        longest = max(job._PRIVATE_NETWORK_CAPABILITY_EXIT_STAGES.values(), key=len)
        legacy_longest = max((stage for code, stage in
                              job._PRIVATE_NETWORK_CAPABILITY_EXIT_STAGES.items()
                              if code < 105), key=len)
        self.assertLessEqual(len(longest), len(legacy_longest))


if __name__ == "__main__":
    unittest.main()
