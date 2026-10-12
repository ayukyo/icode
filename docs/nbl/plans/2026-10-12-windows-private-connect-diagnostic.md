# Windows Private Connect Diagnostic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development 或 nbl.executing-plans task-by-task。root 管理唯一串行 SOURCE writer；独立 SPEC 与不同 QUALITY 只读审查，不启动并行 SOURCE。本轮仅 DOCS ONLY，禁止自动实施、测试、提交或发布。

**Goal:** 只将固定 privateNetwork 正控的真正 `connection.connect` 异常投影为有限非零 exit/stage，保留未知与所有安全准入合同。

**Architecture:** 复用现有 embedded-code/pure-helper 模式，将同一个分类器源码拼进固定 probe，并由便携测试执行该常量。只在原 connect 调用捕获 Exception，完成原 with 清理后才抛 SystemExit；清理失败仍由旧 stage hook 处理。父侧只增加固定 exit translator 映射。

**Tech Stack:** Python 标准库、unittest、AST、现有 Windows AppContainer/Job CI；不新增依赖或权限。

---

## 已确认边界与开工门

真实缺口：`src/icode/windows_job.py:75–79,175–188` 的普通异常 hook 将 IPv4 connect 失败折叠为91，IPv6为93，不能区分 TimeoutError 与 Winsock 错误。父侧已有固定 translator、nonce/token 验证、两栈 exact canary 与清理校验，可直接复用。root 已完成 sequential-thinking 176–178 的需求、方案、风险三步；此处记录其结论，不声称本作者重新调用。

前三个实 CI SHA 的正控 exit91、Reviewer10035/wait_expired/unknown 是已有观察，不证明隔离根因。新 stage 只解释私有正控，不能授零能力 Reviewer DENY、ready 或 R2/R3；10013也不能凭此诊断证明目标 WFP 因果。

Linux S1a SOURCE 当前已停止，完整 preflight session45514 在途。本计划作者不实施。实施必须等 S1a 发布、前 CI terminal、root 冻结本阶段精确基线，且全文独立读本计划与 fresh SPEC→不同 QUALITY 通过。用户选择 main 工作区覆盖默认 worktree；不创建 worktree。

保留：`socket.socket`、AF_INET/AF_INET6、127.0.0.1/::1、3秒 socket timeout、12秒父超时、原 payload/父 nonce/token/Job、原 fixed argv 准入、原网络 DENY/ready/payload 谓词、清理责任。禁止更换 socket API、增加等待、capability/ACL/WFP/服务/网络/MSIX/提权/loopback exemption。

## 精确五路径

| 路径 | 责任 |
| --- | --- |
| `src/icode/windows_job.py` | embedded classifier、原 connect 接线、有限 translator 扩展 |
| `tests/test_windows_private_connect_diagnostic.py` | 新纯分类/真实 AST 接线/有限映射/notice 联动测试 |
| `tests/test_windows_appcontainer.py` | 3037–3038 的 `range(105)` 一行改为实际 mapping keys |
| `docs/nbl/plans/2026-10-12-windows-private-connect-diagnostic.md` | 本计划及 root 实际执行证据 |
| `docs/agent-landscape-live.md` | 阶段开始/结束取舍与证据边界 |

第五路径配对由 root 在读到真实 `range(105)` 后明确授权；禁止第六源码路径或工作流修改。`tests/_support.py` 已提供路径引导，复用、不编辑。原 CI Reviewer 方法直接构建当前固定 probe，原69 required 方法清单不需加入本便携测试；原生运行方式不变。

## 分类合同

所有新码105–118互不重复、exact int、0..255、非零。每栈7类：TimeoutError、真实 winerror10013/10035/10060、仅 errno10013/10035/10060。保留 errno 三类有必要：真实 Python OSError 在不同解释器/平台可能仅提供 errno；单独 stage 标明来源，不伪造 winerror。errno13/EACCES不映射10013。

优先顺序：只接受 exact int91/93作为栈基码；输入不合法固定返回91，不得授分类。KI/SE原对象直接抛出。TimeoutError（含 socket.timeout 同一类）先分类。仅 OSError读取属性；winerror=None才尝试 errno，合法 winerror优先；未知、bool/string/float/越界或属性读取普通异常回该栈91/93。若 winerror是未知值，即使errno可识别也不改写来源。任何属性读取 KI/SE不捕获。

connect异常只存分类结果，在with正常退出后抛SystemExit；不在except内直接退出，避免close普通异常掩盖classified结果后误授诊断。close失败的旧hook结果保持91/93；成功send后close失败保持92/94。系统异常不捕获，不吞BaseException；不打印异常正文/SID/path/地址/nonce/未知数字，不新增JSON通道。

### Task 1: 测试先行及有效 RED

**状态**

- [x] 任务完成

**Dependencies:** None
**Parallelizable:** No（SOURCE root 单写者，须先通过开工门）

- [x] Step 1: 新建下列完整测试文件。此代码是计划内容，本轮不写入测试文件、不执行。

```python
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
```

- [x] Step 2: root 在 SRC 冻结后，先添加最小 classifier stub 常量并拼入原 probe，只返回原栈码；禁止提交 stub。它让测试因真实分类不符 RED，避免 module/API 错误冒充 RED：

```python
_PRIVATE_NETWORK_CONNECT_CLASSIFIER_CODE = """\
def _private_network_connect_failure_exit_code(connect_failure_exit_code, error):
    return connect_failure_exit_code if type(connect_failure_exit_code) is int and connect_failure_exit_code in (91, 93) else 91
"""
```

拼接点在 `_TOKEN_CAPABILITY_SID_CLASSIFIER_CODE` 后新增 `+ _PRIVATE_NETWORK_CONNECT_CLASSIFIER_CODE`，其余不改；真实 loop 在 Task2 接线。执行：

```bash
.venv/bin/python -m unittest tests.test_windows_private_connect_diagnostic.TestPrivateConnectDiagnostic.test_timeout_classification_target -v
.venv/bin/python -m unittest tests.test_windows_private_connect_diagnostic.TestPrivateConnectDiagnostic.test_actual_loop_timeout_target -v
```

两个目标均应 assertion FAIL，第一为91 !=105，第二为真实loop仍原TimeoutError而非SystemExit；不得有import/API ERROR或skip。root须独立重复同目标并保留原输出，RED不发布、不commit。

### Task 2: 最小 classifier、真实 loop、translator 与一行 notice 配对

**状态**

- [x] 任务完成

**Dependencies:** Task 1
**Parallelizable:** No（root唯一writer）

- [x] Step 1: 将 Task1 stub 完整替换如下，保持同常量拼接点。

```python
_PRIVATE_NETWORK_CONNECT_CLASSIFIER_CODE = """\
def _private_network_connect_failure_exit_code(connect_failure_exit_code, error):
    if isinstance(error, (KeyboardInterrupt, SystemExit)):
        raise error
    if type(connect_failure_exit_code) is not int or connect_failure_exit_code not in (91, 93):
        return 91
    offset = 0 if connect_failure_exit_code == 91 else 7
    if isinstance(error, TimeoutError):
        return 105 + offset
    if not isinstance(error, OSError):
        return connect_failure_exit_code
    try:
        winerror = getattr(error, 'winerror', None)
        if winerror is not None:
            if type(winerror) is not int:
                return connect_failure_exit_code
            code = {10013: 106, 10035: 107, 10060: 108}.get(winerror)
        else:
            errno = getattr(error, 'errno', None)
            if type(errno) is not int:
                return connect_failure_exit_code
            code = {10013: 109, 10035: 110, 10060: 111}.get(errno)
    except Exception:
        return connect_failure_exit_code
    return connect_failure_exit_code if code is None else code + offset
"""
```

- [x] Step 2: 原 for tuple 不变，仅其 body 替换为以下完整代码。结果在原 socket owner 正常清理后发出，close异常不可得到 connect 分类信用。

```python
    _failure_exit_code = connect_failure_exit_code
    classified_connect_exit = None
    with socket.socket(family, socket.SOCK_STREAM) as connection:
        connection.settimeout(3)
        try:
            connection.connect((address, port))
        except Exception as error:
            classified_connect_exit = _private_network_connect_failure_exit_code(
                connect_failure_exit_code, error,
            )
        if classified_connect_exit is None:
            _failure_exit_code = send_failure_exit_code
            connection.sendall(payload)
    if classified_connect_exit is not None:
        raise SystemExit(classified_connect_exit)
```

- [x] Step 3: 原0/80–104 mapping 每项逐字保持，仅在104后增加以下14项。

```python
    105: "ipv4_connect_timeout",
    106: "ipv4_connect_winerror_10013",
    107: "ipv4_connect_winerror_10035",
    108: "ipv4_connect_winerror_10060",
    109: "ipv4_connect_errno_10013",
    110: "ipv4_connect_errno_10035",
    111: "ipv4_connect_errno_10060",
    112: "ipv6_connect_timeout",
    113: "ipv6_connect_winerror_10013",
    114: "ipv6_connect_winerror_10035",
    115: "ipv6_connect_winerror_10060",
    116: "ipv6_connect_errno_10013",
    117: "ipv6_connect_errno_10035",
    118: "ipv6_connect_errno_10060",
```

- [x] Step 4: `tests/test_windows_appcontainer.py` 原 longest-network-notice generator 的 `for code in range(105)` 精确替换为：

```python
                 for code in windows_job_module._PRIVATE_NETWORK_CAPABILITY_EXIT_STAGES), key=len,
```

其余 fixture、500预算、期待值、原方法行为不改。新增 stage 均短于原 longest token stage。

- [x] Step 5: root完整运行新测试与原 associated 回归，不以纯helper GREEN替代actual loop。

```bash
.venv/bin/python -m unittest tests.test_windows_private_connect_diagnostic -v
.venv/bin/python -m unittest tests.test_windows_appcontainer -v
```

新文件应零skip/F/E，旧文件平台skip单列；真实Windows结果另验。针对Task1两目标必须明确RED→GREEN。stage/code未接线或setup/timeout/send/close错误被误分类，停止SOURCE验收。

### Task 3: 审查、完整守护与发布后的实 Windows 分账

**状态**

- [ ] 任务完成

**Dependencies:** Task 2
**Parallelizable:** No（每道门依赖前一道；观察者只读可独立复核）

- [x] Step 1: root冻结精确五文件diff，fresh SPEC之后不同QUALITY全文审查。检查旧mapping、parent12秒、socket3秒、两个canary/payload、父token与Job清理、网络DENY谓词和fixed admission均未改变；两轮有问题先修再重新冻结。任何代码改动撤销先前候选测试信用。

- [x] Step 2: root执行原完整守护，原stdout三门实际通过且exit0；此脚本不输出JSON，不要求虚构JSON `ok`，不只看启动或空输出。

```bash
CMAKE_BUILD_PARALLEL_LEVEL=1 MAKEFLAGS=-j1 .venv/bin/python -B -u scripts/preflight.py
.venv/bin/python -B -m compileall -q -j1 src tests scripts
.venv/bin/python -B scripts/check_site.py
.venv/bin/python -B scripts/check_governance.py
.venv/bin/python -B scripts/preflight.py --only secrets
.venv/bin/python -B scripts/preflight.py --only submodule
git diff --check
```

最后文档修改后，两次运行原文档scanner；逐疑似项手核代码误报，不把非零原数改成零。列明实际命令、session、完整原输出结果；未执行不得补“通过”。此处不启动这些命令。

```bash
.venv/bin/python -B /home/orbbec/.agents/skills/doc-contract-consistency-audit/scripts/check_consistency.py docs/nbl/plans/2026-10-12-windows-private-connect-diagnostic.md docs/agent-landscape-live.md
```

- [x] Step 3: live记录追加下文，已有历史条目保留。开始与结束刷新仅本片相关项目，未核完整20项名单或HEAD不得这样声称。

```markdown
Windows private connect finite诊断阶段：复用2026-10-12 01:30 UTC独立只读研究及固定Codex7f892275e31002f0422477c6219189284560e689/Apache-2.0，观察缺口是普通异常折叠91/93，隔离根因仍未知。采纳有限固定TimeoutError/winerror/errno分类、同一embedded helper与actual probe AST接线/清理负控；暂缓换后端、WFP特权过滤与延时；不适配timeout/91/rc!=0授DENY。收益是减少诊断误判，成本为14固定枚举、便携故障测试和实际Windows日志；无源码复制、依赖/权限/网络或服务动作。软件、发布和原生结果按实际证据分别追加，不预授Reviewer DENY/ready或R2/R3。
```

- [ ] Step 4: 原前CI终态、发布权限与本候选守护确认后，root按既有精确stage/main push流程发布；本计划不执行Git writes。不得commit RED stub、额外dirty文件或未冻结改动。

```bash
git add src/icode/windows_job.py tests/test_windows_private_connect_diagnostic.py tests/test_windows_appcontainer.py
git add -f docs/nbl/plans/2026-10-12-windows-private-connect-diagnostic.md docs/agent-landscape-live.md
git diff --cached --check
git diff --cached --name-only
git commit -m "test(windows): classify fixed private-connect failures"
git push origin main
git ls-remote --heads origin
```

commit前核index仅本五路径且每文件字节等于冻结工作树；没有模型凭据/vendor或两份其它阶段计划。实际push成功、远端仅main且同本次SHA后才登记发布，不新branch、不取消前候选CI。

- [ ] Step 5: root与独立观察者各读新SHA四Windows workspace/provenance原日志及两个Reviewer原方法日志，记录OS/Python/arch、确切新stage/exit、两canary、父token、cleanup、原DENY/ready。原69 required启动源码清单不改；新增便携测试通过原unittest discovery执行，不冒充原生方法。新code全部nonzero/inconclusive，双canary及parent token verified、exit0与cleanup同时成立才有原正控observed信用，仍不能单独给零cap DENY。原Reviewerfailure允许保持，但必须诚实记录整体CI失败，不借本片解释或隐藏。

## 研究归属与来源

作者只读本地actual源码/测试/CI与live最后Windows研究条目，不联网、不刷新上游HEAD。独立研究者2026-10-12 01:30 UTC实际取得固定[Codex smoke L470–527](https://github.com/openai/codex/blob/7f892275e31002f0422477c6219189284560e689/codex-rs/windows-sandbox-rs/sandbox_smoketests.py#L470-L527)及Apache-2.0；其direct-loopback只要求rc!=0，不适配ICODE严格10013 gate。Microsoft [WSAEventSelect](https://learn.microsoft.com/en-us/windows/win32/api/winsock2/nf-winsock2-wsaeventselect)/[connect](https://learn.microsoft.com/en-us/windows/win32/api/winsock2/nf-winsock2-connect)区分pending与completion，[packaged loopback](https://learn.microsoft.com/en-us/windows/apps/develop/communication/interprocess-communication#loopback) exemption不证明本unpackaged profile根因，不实施exemption。采纳机制而不复制代码；零新依赖、权限或许可义务。

## 计划静态两阶段自审与七维报告

本轮只静态审计划：第一阶段需求覆盖/调用链对照，第二阶段代码签名/有限枚举/fixture/步骤一致性对照。root另外全文独立读与fresh SPEC→不同QUALITY；本作者无源码、测试、Windows原生或发布通过信用。

【架构级自检报告】

- 语法/编译：仅静态代码审阅；未执行编译，实际通过待root。
- 依赖/调用链：计划拼接actual常量、原actual AST loop、原translator及notice枚举配对完整。
- 逻辑/边界：列明两栈、winerror/errno区别、exact类型、未知、KI/SE、setup/send/close；动态验收待root。
- 异常处理：计划只捕获connect Exception，with清理责任与原hook保持；普通属性失败回legacy。
- 关联模块：五路径冻结；授权的一行notice枚举修复已明确，无第六SOURCE。
- 兼容安全：原0/80–104与准入/时限/权限/credit合同保持的要求已明确，实际diff复核待root。
- 可运行性：完整代码/夹具/命令已提供，但本轮禁止运行，不能声称100%通过。

**Execution Mode:** serial（当前作者只交付计划；root管理唯一串行SOURCE writer，独立审查只读，既有持续开发授权不被本作者交付动作终止）。

## Root 实际开工记录（2026-10-12）

S1a原完整preflight45514 exit0后，root精确四路径且index字节一致，实际commit/push main `74163aa59affa406bed230679ac29ec638c0c979`，ls-remote仅main同SHA。此前S0b三个流程已终态；新741三流程运行中，下一发布必须等待终态，不能取消。Windows计划fresh SPEC→不同QUALITY初有两组M，root补官方unittest生命周期、文案、14exact stage断言和双栈signals后QUALITY完整复核C0/I0/M0；最终代码资产冻结计划摘要`1bc19e2e5f2de4c268f6a35cf80f6783c9a0ce2f169142f948a83fce6c64c834`。root全文重读资产后启动唯一fresh Task1 writer，只有测试+未发布最小stub授权，未授GREEN。

并行原CI另发现Ubuntu22.04 ARM安装probe失败，job114634914991，02:13:16 UTC记录；root已取得原日志，实际wheel `e5371a5efdccccc2750a89fa2dd3fe1e7802af4d4b3b11466b03a2d4ea5f75c7`、helper `cee8a99a3f8f178624b6e0031e878f759940ea0acbe47e6d3178f4990135dc4c`、manifest `76277e8312d32f04284dc7a7dcbf50b607a71d6933563594cb237039ce8ef51a`，ARM64/kernel6.8.0-1064-azure/systemd249，vendor仍21566a5固定。分析工作树与runtime提交同741，但Windows临时stub不属于该runtime；没有修复/verification候选。

原84有限record的32正控未见error或身份非pass；故障context/scope/timeout实际error=resource_channel_failed，而安装脚本673行精确要求timeout，证明该负控未通过。所有record均process/channels/threads/workspace终态true不替代预期error和payload断言。stderr正文被既有producer隐藏，只发布2659bytes，不能反推其它assert失败数、实际exit_code、ready存在或资源channel失效根因。root已记录sequential179–181需求/复用/风险；当前结论仅“timeout负控实际错误种类与合同不符”，不是已确认生产根因、偶发或修复。只读观察继续，Windowsfinite片不借此降门，也不并行改Linux源码。

并行研究实际复取窗口02:14–02:17 UTC，独立观察者再次核固定Codex7f892275…源码L470–527及Apache-2.0 LICENSE、Microsoft connect/WSAEventSelect/Winsock error codes官方页面。采纳允许canary与直接连接负控分账、pending与completion区分；不适配Codex非零rc/短timeout替ICODE精确10013门；暂缓复制代码、capability/权限/豁免及后端切换。10035是pending，10013即WSAEACCES仍须关联本候选事实，研究不替原生证明。不刷新HEAD/20名单。

ARM失败基线（使用bug-investigation-baseline-checklist限定结论，不进行现场设备归因）：

| section | 事实与未观察边界 |
| --- | --- |
| identity | GitHub托管ubuntu22.04-arm/job114634914991，非用户现场设备；物理SN/MAC不适用，运行uid1001由bridge原记录观察 |
| time_window | 原日志02:10:58 checkout至02:13:16失败，UTC；源为GitHub runner，未另证物理时钟偏差 |
| repo_matrix | runtime/analysis main74163aa，vendor21566a5；Windows未发布变更不属于runtime；verification不存在 |
| artifact_identity | 上段wheel/helper/manifest摘要与arm64/kernel/systemd原日志绑定；独立临时venv安装，不授其它机器/版本 |
| evidence_sources | GitHub原日志完整取得，但producer只发布84有限JSON与stderr字节数，正文未发布；不伪称有traceback |
| unresolved | 实际exit_code、payload ready、resource terminal及原断言正文unknown；root负责后续最小有限诊断设计，不放宽timeout预期 |
| conclusion_ceiling | observation_only：timeout负控返回错误种类违约，尚非根因或修复实证 |

Claim ledger：84记录与一条timeout mismatch是fact（原JSON＋固定脚本673）；认为quota/时序/manager导致是尚未证实hypothesis；宣称所有四格安装通过已被此job失败refuted；原隐藏stderr、ready/exit/terminal为unobserved。当前不重跑覆盖，不修改验收谓词。

Task1作者实际新11方法/313行测试与计划资产逐字一致，首跑缺constant AttributeError仅1error/exit1、不授RED；最小stub后两目标各1test/1assertFAIL/0error/skip、exit1，随后停止写。root全文读实际测试及6行源码diff并独立重现分类目标91!=105（0.000s）、旧实际AST loop的TimeoutError不是SystemExit（0.001s），都精确1/1/0/0。冻结stub SOURCE `e24bfb5cc1bdcda4eeda04599781bdcb7f48fa05cd0f5608757901669f8f2707`、TEST `0199e7d9cb3e24e52f8ccddd7b528b7b2bccb97686c4001fc794a1f3f83a92d5`。原loop/map/notice/admission未改；作者SPEC→QUALITY自审零遗留，七维记录明确RED非GREEN。仅允许不同fresh Task2 writer替stub、接真实loop、14mapping及原notice一行，不提前授完整/原生通过。

Task2不同fresh作者已GREEN后停止写；真实两个target各1项0F/E/skip，0.000/0.003s；新11/2.686s零skip、旧99/2.662s与13既有native/optin skip、0F/E，均exit0。root全文读最终diff与完整新测试，独立新11/2.688s零skip、旧99/2.617s与13skip、0F/E/exit0；SOURCE `ac2bfbe924a9b03b68ab0304f55cfcfde7b79615c3563c0db61ca099d335d640`、旧test `51de57ea545f03091c5154621037f22cd08355ba120c1c1705bd865840fdf562`，新test保持Task1摘要。关键分支仅等价合并type检查表达式并补注释，不改分类合同；原可见资产与真实代码不要求逐字相同。作者SPEC→QUALITY自审零遗留；root独立compileall-j1/site/governance/diff通过，fresh SOURCE SPEC在途，之后不同QUALITY与原完整守护尚待。Linux portable不授Windows原生、安装、DENY或R2/R3。

fresh SOURCE SPEC→不同QUALITY最终均C0/I0/M0，各自实际新11/2.670s及2.666s无skip、旧99/2.633s及2.672s有13既有skip、0F/E/exit0；双方RAM-only旧stub＋741原probe各复现两有效目标assertFAIL而非error，恢复实际源码后摘要完全一致。root冻结三SOURCE后启动唯一原完整preflight session86008，日志`/tmp/icode-windows-connect-preflight.m5HtX2/typescript`，CMAKE_BUILD_PARALLEL_LEVEL=1/MAKEFLAGS=-j1、script -e -f。当前尚在运行，不能用启动或前两守护授全量完成，不启动第二份全量测试。

发布前原文档扫描初轮2文件/1疑似，root逐项核唯一type(error为54–368 Python fence内的真实函数调用（249行），不是链接；原数1、排除代码假阳性1、实际遗留0，未改scanner。最终文档字节还须连续两次原扫描，逐次登记，不把原非零写成零。

741前候选三流程于02:33:57 UTC全部终态；root02:35 UTC独立jobs API核主CI46=40success/3failure/3skip、provenance5/5success、Pages2/2success、running0。独立观察者另实取四签装原日志并用固定741 chain/source validator及原src内存复验8payload，独立期望版本来自setup/provisioning；四格69required无skip、历史producer目标RED成立。此处为观察者验证结果，不假称root本轮也执行8validator；owner_untrusted/三authority=false仍保留，签装不授UAC/launch/网络门。原ARM timeout mismatch及双Reviewer失败保留，下一push没有取消进行中候选风险。

唯一原完整preflight session86008实际exit0，原日志三道OK及COMMAND_EXIT_CODE="0"，root于02:38:58 UTC取得终态；源码三个摘要保持，未猜本机隐藏全量计数。compileall-j1/site/governance/diff已实过；密钥及固定vendor发布前实际各exit0，原用户最高j6本轮j1。原文档连续两扫各原1疑似/type(error仅代码fence假阳性1、真实遗留0，不改scanner或伪称原数0；本句记录后发布前再两扫保持相同门，精确五路径/index核验通过后才main提交/推送，尚不预生成发布SHA。

本片七维软件自检至此均有实证：语法与实际AST/compile通过；同helper→probe→translator→notice依赖完整；11项边界与旧99回归通过（13skip不授原生）；普通异常/原signal/with清理目标通过；原准入/Job/token/预算/工作流不变；密钥/vendor守护与零新权限保护兼容；原完整测试和软件可运行性通过。Windows原生、新SHA签装、DENY、UAC/launch、ARM负控及整体R2/R3仍另验，不授100%整体验收。

【架构级自检报告】（冻结软件候选，完整守护和原生仍待）

- 语法/编译：实际嵌入AST/portable与compileall-j1通过。
- 依赖/调用链：同classifier/probe/translator/notice完整配对，无新依赖。
- 逻辑/边界：两栈有限映射、未知/type/顺序负控通过，原准入条件保持。
- 异常处理：connect/非connect/close/普通属性/原KI/SE目标通过，不声称所有未知异常覆盖。
- 关联模块：旧99回归0F/E、13平台skip分账，workflow/69required/其它SOURCE不改。
- 兼容安全：socket/时限/token/Job/nonce/双canary/预算/权限/DENY保持。
- 可运行性：本机软件片通过；原完整预检、安装及Windows原生未预授完成。
