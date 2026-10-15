# Windows CI positive loopback admin TEST assets Implementation Plan

> For agentic workers: 本轮仅 DOC。root 全文及 fresh SPEC/不同 QUALITY 双审通过后，才允许独立 TEST 作者按本文件新增测试；不同 SOURCE 作者实现主 PLAN。现在禁止实际 TEST/SOURCE/CI/Git/API/native/admin/install/full 动作。主 PLAN 和本资产必须共同冻结，不允许单独执行。

**Goal:** 用真实生产 parser/serializer/协调器及低层 adapter 算法验证单预绑定 positive SID 的软件边界，保留 Windows 原生事实的独立验收。

**Architecture:** 协调器测试采用持久字节和有状态 OS 模型；底层测试调用真实 Native 算法，替换最底层 Win32 callable 并填充真实 ctypes 结构。两者都只授软件信用。core 402 行及已有 35P 资产不改。

**Tech Stack:** Python 3.12 标准库 unittest、ctypes、importlib、tempfile；不新增安装或依赖。

---

## 冻结依据及阶段边界

已全文读取父 SPEC `docs/nbl/specs/2026-10-15-windows-ci-positive-loopback-exemption-design.md` 和 addendum `docs/nbl/specs/2026-10-15-windows-ci-positive-loopback-admin-binding-design.md`（root 指定 SHA256 `8d3f0a749962f8f25b6cc3ee1aab42e613f1d7d27d4851613aa345e4e74726ae`），实际 core、Get include、wrapper Create/launch/finally、Reviewer TEST 正控链及 CI 标准用户启动/180s准备边界。只读旧主 PLAN draft，绝不照旧单60s窗口编测试。

当前输入候选绑定 root 通知的 `619ed7771d9741eab11cb8a333965521d0c8d228`。纯 core/原冻结 TEST 已在该 main 候选；本文件、admin addendum、主 admin PLAN 均未纳入该候选，本文没有任何 Git 写操作或线上验收声明。

root 实际历史 e94 sourcechain 证据揭示必须单独验证的兼容性风险：volume root owner 为 other，Authenticated Users 有直接 add_subdir=4，而下一层 protected，旧 launch_authorized=false。因此理想模型中的 BA/SYSTEM owner 与空ACL成功绝不证明 runner 可准入；不能为通过而盲增 owner 白名单、猜 TrustedInstaller 身份或删祖先安全门。

root 独立研究固定 CPython `v3.12.10` / `0cc81280367df838c4b199f8f0378837165071c2`：`getpath.py`294–351在site前读exe同级/父级cfg；388–419中DLL对应`._pth`优先，672–689中importsite可覆盖`-S`；585–658将缺席的`python312.zip`也加入sys.path。独立研究者进一步核定`Python/initconfig.c`738–787中`-I`不隐含`-S`；`Python/dynload_win.c`148–198存在python3.dll回退，224–231以DEFAULT_DIRS|DLL_LOAD_DIR加载pyd。证据固定在[CPython v3.12.10](https://github.com/python/cpython/tree/v3.12.10)，不是本片Windows运行结果。Native测试必须按实际冻结layout检查这些存在/缺席/额外配置路径及外部借用拒绝，记录实际加载DLL/pyd路径；不能仅凭`-I -S`授loading安全。暂缓embeddable/新PyConfig架构，不在本片扩展。

真实问题是当前没有 privileged adapter；现有 Get include 只输出目标采样，不能证明完整 foreign SID/Attributes，现有 probeRoot 标准用户 Modify 不可作 privileged loading/ledger 根。复用现有 core 的 canonical SID 和操作 request validator，但其可构造 flags、State、CleanupPlan 都不是 OS authority。

本文件现含八个完整 TEST 资产，与主 PLAN 的真实 Admin/reader/Win32/Store/jobs/Native/entry逐一对齐。当前152方法已在明确指定的3.11.17解释器完成DOC RAM诊断，全部通过；最终运行快照、围栏hash及历史fixture更正见末节。110/124/127/146等计数仅为明确保留的历史，不是当前状态。全部代码围栏现冻结，后续仅审查记录与元数据。root 全文及fresh SPEC/不同QUALITY通过之前禁止正式TDD；完整Windows/nativeprepare、consumer接线及双Windows真实恢复仍未验收。

## TEST 责任与证据界限

软件测试必须检查输出、持久化原件、允许副作用的实际变化及事件顺序，不能只断言 mock 被调用。假的 Win32 函数持有真实 ctypes 内存，以可控返回值模拟合法 OS ABI 与故障；它不证明 Windows ACL、Job、内核坏指针、安全加载或系统豁免实际有效。原生仅 GitHub 临时 runner 同候选 x64/ARM64，且只能修改同一 admin 预绑定 positive SID。Reviewer/foreign 不主动修改，不在本机运行系统操作。

Linux 的 `ctypes.wintypes.DWORD/FILETIME` 可能随 host `c_ulong` 变宽；本文件 fake 按生产同一 Python 结构填内存，只验证该 host 下算法，不证明 Win32 SDK ABI。真实指针表也不证明真实 Windows allocation ownership。当前本机 3.11 若用于软件诊断，不授目标 Python 3.12、Windows x64/ARM64 ABI 或调用约定信用。

root 实际诊断收据 `06906c`：WSL Python 3.11.17 上 DWORD/LONG/BOOL 均为8字节、FILETIME为16、WORD为2、HANDLE为8。此为实际 host 布局差异，不能用本文件 same-structure fake 测试通过掩盖；Windows ABI 门仍须逐项运行和比对。

## Task 1：完整 Get reader 与 mapping 的完整软件 TEST 资产

**Dependencies:** 主 PLAN 的 `scripts/windows_positive_loopback_admin.py`、`scripts/windows_positive_loopback_full_get.py` 接口共同冻结。
**Parallelizable:** No（正式 TEST-only RED、独立双审之后才 SOURCE）。

- [ ] 用 apply_patch 新增下方完整 `tests/test_windows_positive_loopback_admin_get.py`。缺组件必须是 setUp 中明确 Assertion RED，依赖加载内部错误不得伪装缺组件；不允许 skip。
- [ ] 运行 `PYTHONPATH=src python -m unittest tests.test_windows_positive_loopback_admin_get -v`。新组件不存在时应为逐方法 Assertion FAIL、零 ERROR/skip；SOURCE 后全部 PASS。
- [ ] 核原 core/旧测试/CI 字节未变，记录实际退出状态及日志 SHA。此轮 DOC 阶段不运行以上命令。

```python
"""Complete Get software boundary; fake Win32 ABI, never native evidence."""
from __future__ import annotations
import ctypes
from ctypes import wintypes
import importlib
import io
from pathlib import PureWindowsPath
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import patch


def optional(name):
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        if exc.name != name:
            raise
        return None


admin = optional("scripts.windows_positive_loopback_admin")
reader = optional("scripts.windows_positive_loopback_full_get")


def raw(entries):
    return dict(schema=1, entries=entries, api_code=0, complete=True,
                sid_attempted=len(entries), sid_freed=len(entries),
                array_freed=True, library_freed=True, process_reaped=True)


def binary(last):
    return bytes((1, 2)) + (15).to_bytes(6, "big") + struct.pack("<II", 2, last)


class MemoryOS:
    """Own real allocations; no callable here invokes the operating system."""
    def __init__(self, module, count=2):
        self.module = module
        self.buffers = [ctypes.create_string_buffer(binary(i + 1)) for i in range(count)]
        self.rows = (module.SID_AND_ATTRIBUTES * count)()
        for i, buffer in enumerate(self.buffers):
            self.rows[i].Sid = ctypes.addressof(buffer)
            self.rows[i].Attributes = 0x80000004 + i
        self.count = count
        self.code = 0
        self.null_array = False
        self.invalid = set()
        self.fail_free = set()
        self.lengths = {}
        self.freed = []
        self.events = []
        self.library = SimpleNamespace(_handle=700)
        self.library_ok = True

    def query(self, count, array):
        self.events.append("query")
        ctypes.cast(count, ctypes.POINTER(wintypes.DWORD))[0] = self.count
        ctypes.cast(array, ctypes.POINTER(ctypes.c_void_p))[0] = (
            0 if self.null_array else ctypes.addressof(self.rows))
        return self.code

    def IsValidSid(self, pointer):
        self.events.append(("valid", pointer))
        return pointer not in self.invalid

    def GetLengthSid(self, pointer):
        return self.lengths.get(pointer, 16)

    def GetProcessHeap(self):
        return 600

    def HeapFree(self, heap, flags, pointer):
        address = pointer.value if isinstance(pointer, ctypes.c_void_p) else pointer
        if heap != 600 or flags != 0 or address in self.freed:
            raise AssertionError("wrong allocator or double free")
        self.freed.append(address)
        self.events.append(("free", address))
        return address not in self.fail_free

    def FreeLibrary(self, handle):
        if handle != 700:
            raise AssertionError("wrong library handle")
        self.events.append("unload")
        return self.library_ok

    def load(self):
        return self, self, self.library, self.query


class TestAdminCompleteGet(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(admin, "new admin component absent; expected facility RED")
        self.assertIsNotNone(reader, "new complete Get component absent; expected facility RED")

    def collect(self, model):
        with patch.object(reader, "_load", model.load):
            return reader.collect()

    def test_mapping_binary_identity_and_order_independence(self):
        rows = [["S-1-15-2-1", 0x80000004], ["S-1-15-2-2", 0xffffffff]]
        self.assertEqual(admin._mapping(raw(rows)), admin._mapping(raw(rows[::-1])))
        self.assertEqual(set(admin._mapping(raw(rows)).values()), {0x80000004, 0xffffffff})

    def test_mapping_exact_schema_types_and_release_counts(self):
        good = raw([["S-1-15-2-1", 7]])
        cases = [dict(good, extra=1), {k:v for k,v in good.items() if k != "complete"}]
        for key in ("schema", "api_code", "sid_attempted", "sid_freed"):
            cases.append(dict(good, **{key: True}))
        for key in ("complete", "array_freed", "library_freed", "process_reaped"):
            for value in (False, None, 1):
                cases.append(dict(good, **{key:value}))
        for key in ("sid_attempted", "sid_freed"):
            for value in (0, 2, -1):
                cases.append(dict(good, **{key:value}))
        for case in cases:
            with self.subTest(case=case), self.assertRaises((admin.AdminError, ValueError)):
                admin._mapping(case)

    def test_mapping_duplicate_sid_attributes_and_limit(self):
        cases = [raw([["S-1-15-2-1", 1], ["S-1-15-2-1", 2]]),
                 raw([["S-1-15-2-01", 1]]), raw([["S-1-15-2-1", True]]),
                 raw([["S-1-15-2-1", -1]]), raw([["S-1-15-2-1", 1 << 32]]),
                 raw([["S-1-15-2-1", 1]] * 4097)]
        for case in cases:
            with self.subTest(case=case), self.assertRaises((admin.AdminError, ValueError)):
                admin._mapping(case)
        boundary = [["S-1-15-2-" + str(index + 1), index] for index in range(4096)]
        self.assertEqual(len(admin._mapping(raw(boundary))), 4096)

    def test_collect_real_buffers_all_entries_and_allocator_pairing(self):
        model = MemoryOS(reader)
        result = self.collect(model)
        self.assertTrue(result["complete"])
        self.assertIsNone(result["process_reaped"])
        self.assertEqual(result["entries"], [["S-1-15-2-1", 0x80000004],
                                             ["S-1-15-2-2", 0x80000005]])
        self.assertEqual(model.freed, [ctypes.addressof(b) for b in model.buffers]
                         + [ctypes.addressof(model.rows)])
        self.assertEqual((result["sid_attempted"], result["sid_freed"]), (2, 2))
        self.assertEqual(model.events[-1], "unload")

    def test_collect_zero_entries_is_complete_without_sid_free(self):
        model = MemoryOS(reader, 0)
        model.null_array = True
        result = self.collect(model)
        self.assertTrue(result["complete"])
        self.assertEqual(result["entries"], [])
        self.assertEqual(model.freed, [])

    def test_collect_no_partial_snapshot_for_bad_count_or_api(self):
        for mode in ("api", "limit", "null"):
            model = MemoryOS(reader)
            if mode == "api": model.code = 5
            if mode == "limit": model.count = 4097
            if mode == "null": model.null_array = True
            result = self.collect(model)
            self.assertFalse(result["complete"])
            self.assertEqual(result["entries"], [])
            self.assertEqual(model.freed, [])

    def test_collect_unsafe_ownership_graph_never_double_frees(self):
        for mode in ("null", "array_alias", "sid_alias", "invalid"):
            model = MemoryOS(reader)
            if mode == "null": model.rows[1].Sid = 0
            if mode == "array_alias": model.rows[1].Sid = ctypes.addressof(model.rows)
            if mode == "sid_alias": model.rows[1].Sid = model.rows[0].Sid
            if mode == "invalid": model.invalid.add(model.rows[1].Sid)
            result = self.collect(model)
            self.assertFalse(result["complete"])
            self.assertEqual(result["entries"], [])
            self.assertEqual(model.freed, [])

    def test_collect_binary_duplicate_releases_safe_distinct_allocations(self):
        model = MemoryOS(reader)
        ctypes.memmove(model.buffers[1], model.buffers[0], 16)
        result = self.collect(model)
        self.assertFalse(result["complete"])
        self.assertEqual(len(model.freed), 3)

    def test_collect_failed_release_or_sid_length_stays_incomplete(self):
        for mode in ("sid_free", "array_free", "library", "length"):
            model = MemoryOS(reader)
            if mode == "sid_free": model.fail_free.add(model.rows[0].Sid)
            if mode == "array_free": model.fail_free.add(ctypes.addressof(model.rows))
            if mode == "library": model.library_ok = False
            if mode == "length": model.lengths[model.rows[0].Sid] = 69
            self.assertFalse(self.collect(model)["complete"])

    def test_sid_binary_text_validation(self):
        self.assertEqual(reader._text_sid(binary(1)), "S-1-15-2-1")
        for value in (b"", binary(1)[:-1], bytes((2,)) + binary(1)[1:],
                      bytes((1, 0)) + b"\0" * 6, "S-1-15-2-1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                reader._text_sid(value)

    def test_load_binding_body_survives_free_library_failure(self):
        body=AttributeError("modeled_export_body");released=[]
        class Function:
            def __init__(self,body):self.body=body
            def __call__(self,*args):return self.body(*args)
        def directory(buffer,capacity):buffer.value=r"C:\Windows\System32";return len(buffer.value)
        def free(handle):released.append(handle);raise OSError("modeled_FreeLibrary_cleanup")
        kernel=SimpleNamespace(GetSystemDirectoryW=Function(directory),FreeLibrary=Function(free),
            GetProcessHeap=Function(lambda:600),HeapFree=Function(lambda *args:1))
        advapi=SimpleNamespace(IsValidSid=Function(lambda *args:1),GetLengthSid=Function(lambda *args:16))
        class Library:
            _handle=700
            def __getattr__(self,name):raise body
        def dll(name,**options):
            if name=="kernel32":return kernel
            if name==r"C:\Windows\System32\advapi32.dll":return advapi
            if name==r"C:\Windows\System32\FirewallAPI.dll":return Library()
            raise AssertionError("nonfixed library")
        with patch.object(reader,"Path",PureWindowsPath),patch.object(reader.ctypes,"WinDLL",dll,create=True):
            with self.assertRaises(Exception) as caught:reader._load()
        self.assertEqual(released,[700]);self.assertIs(caught.exception,body)
        self.assertTrue(any(n.startswith("cleanup_unknown:") for n in getattr(body,"__notes__",())))

    def test_load_system_directory_exports_and_failed_binding_release(self):
        class Function:
            def __init__(self, body): self.body = body
            def __call__(self, *args): return self.body(*args)
        for missing in (False, True):
            loaded, freed, exports = [], [], []
            def directory(buffer, capacity):
                buffer.value = r"C:\Windows\System32"
                return len(buffer.value)
            kernel = SimpleNamespace(
                GetSystemDirectoryW=Function(directory),
                FreeLibrary=Function(lambda handle: freed.append(handle) or 1),
                GetProcessHeap=Function(lambda: 600),
                HeapFree=Function(lambda *args: 1))
            advapi = SimpleNamespace(IsValidSid=Function(lambda *args: 1),
                                     GetLengthSid=Function(lambda *args: 16))
            class Library:
                _handle = 700
                def __getattr__(self, name):
                    exports.append(name)
                    if name != "NetworkIsolationGetAppContainerConfig" or missing:
                        raise AttributeError(name)
                    return Function(lambda *args: 0)
            library = Library()
            def dll(name, **options):
                loaded.append((name, options))
                if name == "kernel32": return kernel
                if name == r"C:\Windows\System32\advapi32.dll": return advapi
                if name == r"C:\Windows\System32\FirewallAPI.dll": return library
                raise AssertionError("non-system library requested")
            with patch.object(reader, "Path", PureWindowsPath), patch.object(
                    reader.ctypes, "WinDLL", dll, create=True):
                if missing:
                    with self.assertRaises(AttributeError): reader._load()
                    self.assertEqual(freed, [700])
                else:
                    self.assertIs(reader._load()[2], library)
                    self.assertEqual(freed, [])
            self.assertEqual(exports, ["NetworkIsolationGetAppContainerConfig"])
            self.assertEqual([name for name, options in loaded], ["kernel32",
                r"C:\Windows\System32\advapi32.dll",
                r"C:\Windows\System32\FirewallAPI.dll"])
            self.assertEqual([options.get("winmode") for name, options in loaded[1:]],
                             [0x800, 0x800])

    def test_worker_entry_exact_argv_and_private_complete_output(self):
        import json
        import sys
        result = raw([["S-1-15-2-1", 7]])
        result["process_reaped"] = None
        for platform, arguments in (("linux", ["reader", "--full-get"]),
                ("win32", ["reader", "--full-get", "extra"]),
                ("win32", ["reader", "--arbitrary-command"])):
            stream = SimpleNamespace(buffer=io.BytesIO())
            with patch.object(reader.sys, "platform", platform), patch.object(
                    reader.sys, "argv", arguments), patch.object(reader.sys, "stdout", stream):
                self.assertEqual(reader.main(), 2)
                self.assertEqual(stream.buffer.getvalue(), b"")
        for complete, expected in ((True, 0), (False, 4)):
            value = dict(result, complete=complete)
            stream = SimpleNamespace(buffer=io.BytesIO())
            with patch.object(reader.sys, "platform", "win32"), patch.object(
                    reader.sys, "argv", ["reader", "--full-get"]), patch.object(
                    reader.sys, "stdout", stream), patch.object(reader, "collect", lambda: value):
                self.assertEqual(reader.main(), expected)
            self.assertEqual(json.loads(stream.buffer.getvalue()), value)
            self.assertIsNone(json.loads(stream.buffer.getvalue())["process_reaped"])


if __name__ == "__main__":
    unittest.main()
```

## Task 2：双 binding parser 完整 TEST 资产

**Dependencies:** Task 1 与主 PLAN 的四个真实 encode/validate 接口。
**Parallelizable:** No（共同 schema 冻结，不修改现 core）。

- [ ] 用 apply_patch 新增完整 `tests/test_windows_positive_loopback_admin_binding.py`。
- [ ] 运行 `PYTHONPATH=src python -m unittest tests.test_windows_positive_loopback_admin_binding -v`，预期组件不存在为 Assertion RED；实现后全部 PASS。只运行真实 parser，不以并行测试假 parser 代替。

```python
"""Dual-domain software protocol; no sender or OS authentication claim."""
from __future__ import annotations
from dataclasses import asdict
import hashlib
import importlib
import json
import unittest
from icode import windows_positive_loopback_policy as policy

NAME = "scripts.windows_positive_loopback_admin"
try:
    admin = importlib.import_module(NAME)
except ModuleNotFoundError as exc:
    if exc.name != NAME: raise
    admin = None


def wire(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def identity():
    return dict(schema=1, domain="icode_positive_bootstrap_v1",
        repository="ayukyo/icode", source_sha="a" * 40, run_id="123",
        run_attempt=1, job="windows-reviewer-snapshot-probe", matrix="x64",
        session="4" * 32, account_sid="S-1-5-21-1-2-3-1001", pid=1234,
        process_created=5678, positive_profile="icode-" + "1" * 32,
        reviewer_profile="icode-" + "2" * 32,
        positive_sid="S-1-15-2-1-2-3-4-5-6-7",
        reviewer_sid="S-1-15-2-8-9-10-11-12-13-14", nonce="3" * 32,
        ipv4_port=12345, ipv6_port=23456, prepared_ms=1000,
        preparation_deadline_ms=181000)


def manifest(bootstrap, start=180999):
    fields = {key:value for key,value in bootstrap.items() if key not in
        {"schema", "domain", "session", "prepared_ms", "preparation_deadline_ms"}}
    return policy.Manifest(admission=policy.AdmissionFacts(True, True, True, True, True),
                           **fields, started_ms=start, deadline_ms=start + 60000)


class TestAdminBindings(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(admin, "new admin binding component absent; facility RED")
        self.b = identity()
        self.m = manifest(self.b)
        self.session = self.b["session"]

    def test_bootstrap_real_producer_parser_digest_and_exact_fields(self):
        produced = admin.encode_bootstrap_request(self.b)
        body = json.loads(produced)
        self.assertEqual(body["binding"], hashlib.sha256(wire(self.b)).hexdigest())
        self.assertEqual(set(body), {"schema", "domain", "kind", "binding", "session",
            "pid", "process_created", "positive_profile", "positive_sid", "reviewer_sid",
            "nonce", "ipv4_port", "ipv6_port"})
        self.assertEqual(admin.validate_bootstrap_request(produced, self.b, 180999),
                         "profile_created")
        self.assertNotIn("binding", self.b)
        self.assertLessEqual(len(produced), 4096)

    def test_bootstrap_identity_each_field_digest_binds_and_bad_shapes_reject(self):
        original = admin.encode_bootstrap_request(self.b)
        for key in self.b:
            changed = dict(self.b)
            changed[key] = None
            with self.subTest(key=key), self.assertRaises((admin.AdminError, policy.PolicyError)):
                admin.encode_bootstrap_request(changed)
        for key in ("source_sha", "run_id", "session", "nonce", "positive_profile"):
            changed = dict(self.b)
            changed[key] = changed[key].replace("1", "5").replace("a", "b").replace("3", "6").replace("4", "7")
            with self.subTest(key=key), self.assertRaises((admin.AdminError, policy.PolicyError)):
                admin.validate_bootstrap_request(original, changed, 1001)
        for key in ("schema", "pid", "process_created", "run_attempt", "ipv4_port",
                    "ipv6_port", "prepared_ms", "preparation_deadline_ms"):
            changed = dict(self.b, **{key:True})
            with self.subTest(key=key), self.assertRaises((admin.AdminError, policy.PolicyError)):
                admin.encode_bootstrap_request(changed)

    def test_dual_clocks_near_preparation_expiry_gets_new_immutable_operation_window(self):
        created = admin.encode_bootstrap_request(self.b)
        self.assertEqual(admin.validate_bootstrap_request(created, self.b, 180999), "profile_created")
        operation = admin.encode_operation_request(self.m, self.session)
        self.assertEqual(admin.validate_operation_request(operation, self.m, self.session, 240998),
                         "probe_finished")
        self.assertEqual((self.m.started_ms, self.m.deadline_ms), (180999, 240999))
        for now in (999, 181000, 181001, True):
            with self.subTest(now=now), self.assertRaises(admin.AdminError):
                admin.validate_bootstrap_request(created, self.b, now)
        for now in (180998, 240999, 241000, True):
            with self.subTest(now=now), self.assertRaises(policy.PolicyError):
                admin.validate_operation_request(operation, self.m, self.session, now)

    def test_domain_and_core_requests_cannot_cross_admission(self):
        created = admin.encode_bootstrap_request(self.b)
        operation = admin.encode_operation_request(self.m, self.session)
        naked = policy.encode_request(self.m, "profile_created")
        with self.assertRaises(admin.AdminError):
            admin.validate_operation_request(created, self.m, self.session, 181000)
        for value in (operation, naked):
            with self.subTest(value=value), self.assertRaises(admin.AdminError):
                admin.validate_bootstrap_request(value, self.b, 1001)
        self.assertEqual(json.loads(operation)["request"],
                         json.loads(policy.encode_request(self.m, "probe_finished")))

    def test_request_each_field_missing_extra_or_wrong_type_rejects(self):
        for mode in ("bootstrap", "operation"):
            original = json.loads(admin.encode_bootstrap_request(self.b) if mode == "bootstrap"
                                  else admin.encode_operation_request(self.m, self.session))
            def validate(value):
                if mode == "bootstrap":
                    return admin.validate_bootstrap_request(value, self.b, 1001)
                return admin.validate_operation_request(value, self.m, self.session, 181000)
            for key in original:
                missing = dict(original); del missing[key]
                wrong = dict(original, **{key:None})
                for changed in (missing, wrong):
                    with self.subTest(mode=mode, key=key), self.assertRaises(
                            (admin.AdminError, policy.PolicyError)):
                        validate(wire(changed))
            with self.assertRaises((admin.AdminError, policy.PolicyError)):
                validate(wire(dict(original, extra=1)))

    def test_parser_duplicate_keys_utf8_nan_size_and_bool_int_reject(self):
        created = admin.encode_bootstrap_request(self.b)
        operation = admin.encode_operation_request(self.m, self.session)
        for good, validate in (
            (created, lambda data: admin.validate_bootstrap_request(data, self.b, 1001)),
            (operation, lambda data: admin.validate_operation_request(data, self.m, self.session, 181000))):
            for bad in (b"", b"x" * 4097, b"\xff", b"[]", b'{"x":NaN}',
                        good[:-1] + b',"schema":1}', good.replace(b'"schema":1', b'"schema":true')):
                with self.subTest(bad=bad), self.assertRaises((admin.AdminError, policy.PolicyError)):
                    validate(bad)
        outer = json.loads(operation)
        for key in outer["request"]:
            changed = json.loads(operation)
            changed["request"][key] = None
            with self.subTest(key=key), self.assertRaises((admin.AdminError, policy.PolicyError)):
                admin.validate_operation_request(wire(changed), self.m, self.session, 181000)
        changed = json.loads(operation); changed["request"]["ipv4_port"] = True
        with self.assertRaises(policy.PolicyError):
            admin.validate_operation_request(wire(changed), self.m, self.session, 181000)

    def test_operation_binding_session_candidate_and_window_are_immutable(self):
        from dataclasses import replace
        operation = admin.encode_operation_request(self.m, self.session)
        for changed in (replace(self.m, source_sha="b" * 40),
                        replace(self.m, started_ms=181000, deadline_ms=241000),
                        replace(self.m, ipv6_port=23457)):
            with self.subTest(changed=changed), self.assertRaises(policy.PolicyError):
                admin.validate_operation_request(operation, changed, self.session, 181001)
        with self.assertRaises(admin.AdminError):
            admin.validate_operation_request(operation, self.m, "5" * 32, 181001)


if __name__ == "__main__":
    unittest.main()
```

## Task 3：真实 Win32 adapter 算法的完整软件 TEST 资产

**Dependencies:** 主 PLAN 的 `scripts/windows_positive_loopback_admin_win32.py` 围栏共同冻结。
**Parallelizable:** No（故障语义与上层恢复同一合同）。

- [ ] apply_patch 新增完整 `tests/test_windows_positive_loopback_admin_win32.py`。本资产直接调用生产 Win32 方法，只有最底层 callable 为假；不加载实际 DLL。
- [ ] 运行 `PYTHONPATH=src python -m unittest tests.test_windows_positive_loopback_admin_win32 -v`，缺组件必须逐方法 Assertion RED；实现后全部 PASS。

```python
"""Real Win32 adapter algorithms over synthetic ABI memory; software proof only."""
from __future__ import annotations
import ctypes as c
from ctypes import wintypes as t
import importlib
import struct
from types import SimpleNamespace as N
import unittest

NAME = "scripts.windows_positive_loopback_admin_win32"
try:
    native = importlib.import_module(NAME)
except ModuleNotFoundError as exc:
    if exc.name != NAME: raise
    native = None


def put(pointer, kind, value):
    c.cast(pointer, c.POINTER(kind))[0] = value


class ByteFileOS:
    def __init__(self, initial=b"old trailing data"):
        self.bytes = initial
        self.position = 0
        self.events = []
        self.fail = None
        self.short = False

    def SetFilePointerEx(self, handle, distance, output, method):
        if handle != 90 or distance != 0 or method != 0: raise AssertionError("seek")
        self.events.append("seek"); self.position = 0
        return self.fail != "seek"

    def WriteFile(self, handle, data, length, count, overlap):
        self.events.append("write")
        if handle != 90 or overlap is not None: raise AssertionError("write handle")
        actual = length - 1 if self.short else length
        self.bytes = c.string_at(data, actual) + self.bytes[actual:]
        self.position = actual
        put(count, t.DWORD, actual)
        return self.fail != "write"

    def ReadFile(self, handle, buffer, length, count, overlap):
        self.events.append("read")
        value = self.bytes[:length]
        c.memmove(buffer, value, len(value)); put(count, t.DWORD, len(value))
        return self.fail != "read"

    def SetEndOfFile(self, handle):
        self.events.append("truncate"); self.bytes = self.bytes[:self.position]
        return self.fail != "truncate"

    def FlushFileBuffers(self, handle):
        self.events.append("flush")
        return self.fail != "flush"


class TestAdminWin32(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(native, "new Win32 adapter absent; expected facility RED")
        self.w = native.Win32.__new__(native.Win32)

    def test_write_changes_bytes_truncates_and_flushes_in_order(self):
        model = ByteFileOS(); self.w.k = model
        self.w.write(90, b"new")
        self.assertEqual(model.bytes, b"new")
        self.assertEqual(model.events, ["seek", "write", "truncate", "flush"])

    def test_write_short_or_each_boundary_failure_never_claims_durable_success(self):
        for failure in ("seek", "write", "truncate", "flush", "short"):
            model = ByteFileOS(); self.w.k = model
            model.fail = failure; model.short = failure == "short"
            with self.subTest(failure=failure), self.assertRaises(native.Failure):
                self.w.write(90, b"new")
            if failure in ("seek", "write", "short"):
                self.assertNotIn("flush", model.events)

    def test_read_real_buffer_limit_and_actual_bytes(self):
        for value, limit in ((b"abc", 3), (b"", 0)):
            model = ByteFileOS(value); self.w.k = model
            self.assertEqual(self.w.read(90, limit), value)
        self.w.k = ByteFileOS(b"abcd")
        with self.assertRaises(native.Failure): self.w.read(90, 3)
        model = ByteFileOS(b"abc"); model.fail = "read"; self.w.k = model
        with self.assertRaises(native.Failure): self.w.read(90, 3)

    def job(self, pids, *, assigned=None, listed=None, returned=None, ok=True):
        pids = tuple(pids)
        def query(job, information, output, capacity, size):
            self.assertEqual((job, information), (80, 3))
            header = struct.pack("<II", len(pids) if assigned is None else assigned,
                                 len(pids) if listed is None else listed)
            c.memmove(output, header, 8)
            values = c.cast(c.byref(output, 8), c.POINTER(c.c_size_t))
            for index, pid in enumerate(pids): values[index] = pid
            put(size, t.DWORD, returned if returned is not None else
                8 + len(pids) * c.sizeof(c.c_size_t))
            return ok
        self.w.k = N(QueryInformationJobObject=query)
        return self.w.job_pids(80)

    def test_job_query_real_pid_list_empty_single_nested_and_max(self):
        for values in ((), (1234,), (1234, 4321), tuple(range(1, 33))):
            self.assertEqual(self.job(values), values)

    def test_job_query_incomplete_duplicate_zero_and_api_failure_reject(self):
        cases = [dict(pids=(1234,), assigned=2), dict(pids=(), assigned=33, listed=33),
                 dict(pids=(1234,), returned=8), dict(pids=(1234, 1234)),
                 dict(pids=(0,)), dict(pids=(1234,), ok=False),
                 dict(pids=(1234,), returned=9 + 32*c.sizeof(c.c_size_t))]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(native.Failure): self.job(**case)

    def test_file_info_identity_reparse_hardlink_and_directory_shape(self):
        for attrs, links, directory, accepted in ((0,1,False,True), (0x10,1,True,True),
                (0x400,1,False,False), (0,2,False,False), (0x10,1,False,False),
                (0,1,True,False)):
            def info(handle, output):
                value = c.cast(output, c.POINTER(native.FILE_INFO)).contents
                value.attributes=attrs; value.links=links; value.volume=7
                value.index_high=2; value.index_low=3
                return 1
            self.w.k = N(GetFileInformationByHandle=info)
            if accepted:
                self.assertEqual(self.w.info(90, directory=directory), (7, (2 << 32) | 3))
            else:
                with self.subTest(attrs=attrs, links=links), self.assertRaises(native.Failure):
                    self.w.info(90, directory=directory)

    def test_security_reads_actual_owner_acl_bytes_and_protection_bit(self):
        owner = c.create_string_buffer(bytes((1,1)) + b"\0"*5 + b"\5" + struct.pack("<I",18))
        acl = c.create_string_buffer(struct.pack("<BBHHH",2,0,8,0,0))
        def dacl(descriptor, present, output, defaulted):
            put(present,t.BOOL,1); put(defaulted,t.BOOL,0)
            put(output,c.c_void_p,c.addressof(acl)); return 1
        def owner_fn(descriptor, output, defaulted):
            put(output,c.c_void_p,c.addressof(owner)); put(defaulted,t.BOOL,0); return 1
        def control(descriptor, output, revision):
            put(output,t.WORD,0x1000); put(revision,t.DWORD,1); return 1
        self.w.a = N(GetSecurityDescriptorDacl=dacl, GetSecurityDescriptorOwner=owner_fn,
            GetSecurityDescriptorControl=control, IsValidSid=lambda value: 1,
            GetLengthSid=lambda value: 12)
        self.assertEqual(self.w.security(10), (owner.raw[:12], acl.raw[:8], True))
        self.w.a.IsValidSid = lambda value: 0
        with self.assertRaises(native.Failure): self.w.security(10)

    def test_process_creation_time_uses_full_filetime(self):
        def times(handle, created, exited, kernel, user):
            value = c.cast(created,c.POINTER(t.FILETIME)).contents
            value.dwHighDateTime=0x12345678; value.dwLowDateTime=0xabcdef01
            return 1
        self.w.k=N(GetProcessTimes=times)
        self.assertEqual(self.w.process_created(123), 0x12345678abcdef01)
        self.w.k.GetProcessTimes=lambda *args: 0
        with self.assertRaises(native.Failure): self.w.process_created(123)

    def test_open_file_final_descriptor_free_failure_closes_unreturned_handle(self):
        owner=c.create_string_buffer(bytes((1,1))+b"\0"*5+b"\5"+struct.pack("<I",18))
        acl=c.create_string_buffer(struct.pack("<BBHHH",2,0,8,0,0))
        alive=set();descriptors=set();closed=[];counter=[700]
        def descriptor(text,revision,output,size):
            value=counter[0];counter[0]+=1;descriptors.add(value)
            put(output,c.c_void_p,value);return 1
        def info(handle,output):
            value=c.cast(output,c.POINTER(native.FILE_INFO)).contents
            value.links=1;value.volume=7;value.index_low=90;return 1
        def dacl(pointer,present,output,defaulted):
            put(present,t.BOOL,1);put(defaulted,t.BOOL,0)
            put(output,c.c_void_p,c.addressof(acl));return 1
        def own(pointer,output,defaulted):
            put(defaulted,t.BOOL,0);put(output,c.c_void_p,c.addressof(owner));return 1
        def control(pointer,output,revision):
            put(output,t.WORD,0x1000);put(revision,t.DWORD,1);return 1
        def security(handle,kind,flags,a,b,d,e,output):
            descriptors.add(799);put(output,c.c_void_p,799);return 0
        def create(*args):alive.add(90);return 90
        def final(handle,buffer,size,flags):buffer.value="/model/private.bin";return len(buffer.value)
        def close(handle):
            if handle not in alive:raise AssertionError("unowned/double close")
            alive.remove(handle);closed.append(handle);return 1
        def free(pointer):
            value=pointer.value
            if value not in descriptors:raise AssertionError("unowned/double descriptor free")
            if value==700:return value  # Outer allocation fails only after inner verification succeeds.
            descriptors.remove(value);return 0
        self.w.k=N(CreateFileW=create,GetFileInformationByHandle=info,
            GetFinalPathNameByHandleW=final,CloseHandle=close,LocalFree=free)
        self.w.a=N(ConvertStringSecurityDescriptorToSecurityDescriptorW=descriptor,
            GetSecurityInfo=security,GetSecurityDescriptorDacl=dacl,
            GetSecurityDescriptorOwner=own,GetSecurityDescriptorControl=control,
            IsValidSid=lambda pointer:1,GetLengthSid=lambda pointer:12)
        with self.assertRaises(native.Failure):self.w.open_file("/model/private.bin","private")
        self.assertEqual(alive,set(),"failed return must not strand acquired file handle")
        self.assertEqual(closed,[90])

    def test_process_user_real_token_buffer_sid_bounds_and_release(self):
        for mode in ("ok", "grow", "null", "outside", "invalid", "sid_overflow"):
            closed, freed = [], []
            text = c.create_unicode_buffer("S-1-5-21-1-2-3-1001")
            def open_token(process, access, output):
                self.assertEqual((process,access),(123,8)); put(output,t.HANDLE,321); return 1
            def token_info(token, information, buffer, capacity, needed):
                self.assertEqual((token.value,information),(321,1)); put(needed,t.DWORD,64)
                if buffer is None: return 0
                record = c.cast(buffer,c.POINTER(native.TOKEN_USER)).contents
                address = c.addressof(buffer) + c.sizeof(native.TOKEN_USER)
                c.memmove(address, bytes((1,1))+b"\0"*5+b"\5"+struct.pack("<I",18),12)
                record.sid = (0 if mode == "null" else c.addressof(buffer)-1
                              if mode == "outside" else address)
                if mode == "grow": put(needed,t.DWORD,65)
                return 1
            def convert(sid, output):
                put(output,t.LPWSTR,c.cast(text,t.LPWSTR)); return 1
            self.w.k=N(CloseHandle=lambda handle: closed.append(handle.value if hasattr(handle,"value") else handle) or 1,
                       LocalFree=lambda pointer: freed.append(pointer) or 0)
            self.w.a=N(OpenProcessToken=open_token,GetTokenInformation=token_info,
                IsValidSid=lambda pointer: mode != "invalid",
                GetLengthSid=lambda pointer: 68 if mode == "sid_overflow" else 12,
                ConvertSidToStringSidW=convert)
            if mode == "ok":
                self.assertEqual(self.w.process_user(123),text.value)
                self.assertEqual(len(freed),1)
            else:
                with self.subTest(mode=mode),self.assertRaises(native.Failure):
                    self.w.process_user(123)
                self.assertEqual(freed,[])
            self.assertEqual(closed,[321])

    def test_ancestor_acl_real_ace_bytes_reject_untrusted_writer(self):
        identities = {name: bytes((1,1))+b"\0"*5+b"\5"+struct.pack("<I",number)
            for name,number in (("S-1-5-32-544",544),("S-1-5-18",18),
                                 ("S-1-5-21-1",1001),("foreign",2001))}
        self.w.sid_binary=lambda text: identities[text]
        self.w.process_user=lambda handle: "S-1-5-21-1"
        self.w.k=N(GetCurrentProcess=lambda: 1,LocalFree=lambda value: 0)
        def get_security(handle, kind, flags, owner, group, dacl, sacl, output):
            put(output,c.c_void_p,700); return 0
        self.w.a=N(GetSecurityInfo=get_security)
        for owner,ace_kind,ace_flags,mask,trust,expected in (
            ("S-1-5-18",0,0,0x40000000,False,False),
            ("S-1-5-18",0,0,0x00000004,False,False),
            ("S-1-5-18",0,0,0x40000000,True,True),
            ("S-1-5-18",0,0,0x80000000,False,True),
            ("S-1-5-18",0,8,0x40000000,False,True),
            ("S-1-5-18",1,0,0x40000000,False,True),
            ("foreign",0,0,0x80000000,False,False)):
            sid=identities["S-1-5-32-544" if trust else "foreign"]
            ace=struct.pack("<BBHI",ace_kind,ace_flags,8+len(sid),mask)+sid
            acl=struct.pack("<BBHHH",2,0,8+len(ace),1,0)+ace
            self.w.security=lambda descriptor: (identities[owner],acl,False)
            if expected: self.w.verify_ancestor(90)
            else:
                with self.subTest(owner=owner,mask=mask),self.assertRaises(native.Failure):
                    self.w.verify_ancestor(90)

    def test_effective_access_preserves_actual_granted_mask_and_releases_owned_handles(self):
        for mode in ("read_only","write","denied","oversize","api_failure"):
            closed,freed=[],[]
            def security(handle,kind,flags,owner,group,dacl,sacl,output):
                self.assertEqual((handle,kind,flags),(90,1,7))
                put(output,c.c_void_p,700); return 0
            def token(process,access,output):
                self.assertEqual((process,access),(123,10)); put(output,t.HANDLE,321); return 1
            def duplicate(source,level,output):
                self.assertEqual((source.value,level),(321,2)); put(output,t.HANDLE,322); return 1
            def access(descriptor,impersonation,desired,mapping,privileges,size,granted,allowed):
                self.assertEqual(desired,0x02000000)
                actual=c.cast(mapping,c.POINTER(native.GENERIC_MAPPING)).contents
                self.assertEqual((actual.read,actual.write,actual.execute,actual.all),
                                 (0x120089,0x120116,0x1200A0,0x1F01FF))
                put(size,t.DWORD,16385 if mode=="oversize" else 8)
                put(granted,t.DWORD,0x120116 if mode=="write" else 0x120089)
                put(allowed,t.BOOL,mode!="denied")
                return mode!="api_failure"
            self.w.a=N(GetSecurityInfo=security,OpenProcessToken=token,
                       DuplicateToken=duplicate,AccessCheck=access)
            self.w.k=N(CloseHandle=lambda handle: closed.append(handle.value if hasattr(handle,"value") else handle) or 1,
                       LocalFree=lambda pointer: freed.append(pointer) or 0)
            if mode in ("oversize","api_failure"):
                with self.subTest(mode=mode),self.assertRaises(native.Failure):
                    self.w.effective_access(90,123)
            else:
                observed=self.w.effective_access(90,123)
                self.assertEqual(observed["granted"],0x120116 if mode=="write" else 0x120089)
                self.assertEqual(observed["access_status"],mode!="denied")
                self.assertEqual(observed["privilege_bytes"],8)
            self.assertEqual(closed,[322,321]); self.assertEqual(len(freed),1)

    def test_effective_access_cleanup_attempts_all_and_preserves_body_first_error(self):
        for failed in (322,321,700):
            for body_failed in (False,True):
                with self.subTest(failed=failed,body_failed=body_failed):
                    acquired=set();attempted=[];body=native.Failure("modeled_access_body")
                    def security(handle,kind,flags,a,b,d,e,output):
                        acquired.add(700);put(output,c.c_void_p,700);return 0
                    def token(process,access,output):
                        acquired.add(321);put(output,t.HANDLE,321);return 1
                    def duplicate(source,level,output):
                        acquired.add(322);put(output,t.HANDLE,322);return 1
                    def access(descriptor,impersonation,desired,mapping,privileges,size,granted,allowed):
                        if body_failed:raise body
                        put(size,t.DWORD,8);put(granted,t.DWORD,0);put(allowed,t.BOOL,1);return 1
                    def release(resource):
                        value=resource.value if hasattr(resource,"value") else resource
                        if value not in acquired:raise AssertionError("unowned/double release")
                        attempted.append(value)
                        if value==failed:return 0
                        acquired.remove(value);return 1
                    self.w.a=N(GetSecurityInfo=security,OpenProcessToken=token,
                        DuplicateToken=duplicate,AccessCheck=access)
                    self.w.k=N(CloseHandle=release,LocalFree=lambda pointer:0 if release(pointer) else pointer.value)
                    with self.assertRaises(native.Failure) as caught:self.w.effective_access(90,123)
                    self.assertEqual(attempted,[322,321,700],"one cleanup failure must not skip remaining owned resources")
                    self.assertEqual(acquired,{failed})
                    if body_failed:self.assertIs(caught.exception,body)
                    self.assertTrue(any(note.startswith("cleanup_unknown:")
                                        for note in getattr(caught.exception,"__notes__",())))

    def test_verify_security_cleanup_attempts_both_descriptors_and_preserves_body(self):
        owner=c.create_string_buffer(bytes((1,1))+b"\0"*5+b"\5"+struct.pack("<I",18))
        acl=c.create_string_buffer(struct.pack("<BBHHH",2,0,8,0,0))
        for failed in (700,701):
            for body_failed in (False,True):
                with self.subTest(failed=failed,body_failed=body_failed):
                    acquired=set();attempted=[];body=native.Failure("modeled_security_body")
                    def descriptor(text,revision,output,size):
                        acquired.add(701);put(output,c.c_void_p,701);return 1
                    def security(handle,kind,flags,a,b,d,e,output):
                        acquired.add(700);put(output,c.c_void_p,700);return 0
                    def dacl(pointer,present,output,defaulted):
                        put(present,t.BOOL,1);put(defaulted,t.BOOL,0)
                        put(output,c.c_void_p,c.addressof(acl));return 1
                    def own(pointer,output,defaulted):
                        put(defaulted,t.BOOL,0);put(output,c.c_void_p,c.addressof(owner));return 1
                    def control(pointer,output,revision):
                        if body_failed:raise body
                        put(output,t.WORD,0x1000);put(revision,t.DWORD,1);return 1
                    def free(pointer):
                        value=pointer.value
                        if value not in acquired:raise AssertionError("unowned/double free")
                        attempted.append(value)
                        if value==failed:return value
                        acquired.remove(value);return 0
                    self.w.k=N(LocalFree=free)
                    self.w.a=N(ConvertStringSecurityDescriptorToSecurityDescriptorW=descriptor,
                        GetSecurityInfo=security,GetSecurityDescriptorDacl=dacl,
                        GetSecurityDescriptorOwner=own,GetSecurityDescriptorControl=control,
                        IsValidSid=lambda pointer:1,GetLengthSid=lambda pointer:12)
                    with self.assertRaises(native.Failure) as caught:self.w.verify_security(90,"private")
                    self.assertEqual(attempted,[700,701],"actual descriptor free failure must not strand expected descriptor")
                    self.assertEqual(acquired,{failed})
                    if body_failed:self.assertIs(caught.exception,body)
                    self.assertTrue(any(note.startswith("cleanup_unknown:")
                                        for note in getattr(caught.exception,"__notes__",())))

    def test_win32_remaining_owners_keep_body_and_attempt_independent_cleanup(self):
        targets={"open_file":"GetFileInformationByHandle","pin_ancestor":"GetFileInformationByHandle",
            "create_directory":"CreateDirectoryW","set_root_dacl":"SetSecurityInfo",
            "sid_binary":"IsValidSid","assert_admin":"CheckTokenMembership",
            "verify_ancestor":"GetSecurityDescriptorOwner","observe_security":"GetSecurityDescriptorOwner",
            "process_user":"GetTokenInformation"}
        for owner,target in targets.items():
            with self.subTest(owner=owner):
                owned=set();attempted=[];failed=[];counter=[700];active=[False]
                body=native.Failure("modeled_"+owner+"_body")
                sid=c.create_string_buffer(bytes((1,1))+b"\0"*5+b"\5"+struct.pack("<I",18))
                acl=c.create_string_buffer(struct.pack("<BBHHH",2,0,8,0,0))
                def trip(name):
                    if name==target:active[0]=True;raise body
                def allocation(output):
                    value=counter[0];counter[0]+=1;owned.add(value);put(output,c.c_void_p,value);return 1
                def descriptor(text,revision,output,size):return allocation(output)
                def security(handle,kind,flags,a,b,d,e,output):allocation(output);return 0
                def own(pointer,output,defaulted):
                    trip("GetSecurityDescriptorOwner");put(defaulted,t.BOOL,0)
                    put(output,c.c_void_p,c.addressof(sid));return 1
                def dacl(pointer,present,output,defaulted):
                    put(present,t.BOOL,1);put(defaulted,t.BOOL,0);put(output,c.c_void_p,c.addressof(acl));return 1
                def control(pointer,output,revision):put(output,t.WORD,0x1000);put(revision,t.DWORD,1);return 1
                def valid(pointer):trip("IsValidSid");return 1
                def create(*args):owned.add(90);return 90
                def info(handle,output):
                    trip("GetFileInformationByHandle")
                    value=c.cast(output,c.POINTER(native.FILE_INFO)).contents
                    value.attributes=0;value.links=1;value.volume=7;value.index_low=90;return 1
                def release(resource):
                    value=resource.value if hasattr(resource,"value") else resource
                    if value not in owned:raise AssertionError("unowned/double release")
                    if active[0]:attempted.append(value)
                    if active[0] and not failed:
                        failed.append(value);raise native.Failure("modeled_cleanup")
                    owned.remove(value);return 1
                def free(resource):release(resource);return 0
                def create_dir(*args):trip("CreateDirectoryW");return 1
                def set_security(*args):trip("SetSecurityInfo");return 0
                def convert_sid(text,output):owned.add(c.addressof(sid));put(output,c.c_void_p,c.addressof(sid));return 1
                def membership(*args):trip("CheckTokenMembership");return 1
                def open_token(process,access,output):owned.add(321);put(output,t.HANDLE,321);return 1
                def token_info(token,kind,buffer,capacity,needed):
                    put(needed,t.DWORD,64)
                    if buffer is None:return 0
                    trip("GetTokenInformation");return 1
                self.w.k=N(CreateFileW=create,GetFileInformationByHandle=info,CloseHandle=release,
                    LocalFree=free,CreateDirectoryW=create_dir)
                self.w.a=N(ConvertStringSecurityDescriptorToSecurityDescriptorW=descriptor,
                    GetSecurityInfo=security,GetSecurityDescriptorOwner=own,GetSecurityDescriptorDacl=dacl,
                    GetSecurityDescriptorControl=control,IsValidSid=valid,GetLengthSid=lambda pointer:12,
                    SetSecurityInfo=set_security,ConvertStringSidToSidW=convert_sid,
                    CheckTokenMembership=membership,OpenProcessToken=open_token,GetTokenInformation=token_info)
                with self.assertRaises(native.Failure) as caught:
                    if owner=="open_file":self.w.open_file("/model/private.bin","private")
                    elif owner=="pin_ancestor":self.w.pin_ancestor("/model")
                    elif owner=="create_directory":self.w.create_directory("/model/new","private")
                    elif owner=="set_root_dacl":self.w.set_root_dacl(90,"old","new")
                    elif owner=="sid_binary":self.w.sid_binary("S-1-5-18")
                    elif owner=="assert_admin":self.w.assert_admin()
                    elif owner=="verify_ancestor":self.w.verify_ancestor(90)
                    elif owner=="observe_security":self.w.observe_security(90)
                    else:self.w.process_user(90)
                self.assertTrue(active[0],"case must reach intended real owner body")
                self.assertEqual(owned,set(failed),"every other acquired resource must be attempted")
                self.assertIs(caught.exception,body)
                self.assertTrue(any(n.startswith("cleanup_unknown:") for n in getattr(body,"__notes__",())))


if __name__ == "__main__":
    unittest.main()
```

## Task 4：真实 Admin 协调器的完整软件 TEST 资产

**Dependencies:** Task 1–3、主 PLAN Admin 公共方法与最终 ledger 字段共同冻结。
**Parallelizable:** No（与真实 Native 严格账本资产交叉核对后才冻结）。

以下 FakeNative 只提供协调器边界的有状态软件输入，绝不代替 Task 3/实际 Native 的低层句柄算法测试或 nativeprepare。真实 parser、mapping、Admin 状态更新、序列化持久字节、完整映射副作用均运行。此 TEST 中的 modeled receipt 不得导出为 Windows 事实。

- [ ] apply_patch 新增完整 `tests/test_windows_positive_loopback_admin.py`。
- [ ] 运行 `PYTHONPATH=src python -m unittest tests.test_windows_positive_loopback_admin -v`，缺新组件为 Assertion RED；SOURCE 后全部 PASS。测试冻结后不得由SOURCE作者修改以补绿。

```python
"""Real coordinator over durable stateful model; no Windows authority."""
from __future__ import annotations
import copy
from dataclasses import asdict
import importlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from icode import windows_positive_loopback_policy as policy
from tests.test_windows_positive_loopback_admin_binding import identity, manifest

NAME="scripts.windows_positive_loopback_admin"
try:
    admin=importlib.import_module(NAME)
except ModuleNotFoundError as exc:
    if exc.name != NAME: raise
    admin=None


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode("ascii")


class ModelStore:
    def __init__(self, model):
        self.model=model
        self.data=dict(phase="prepared",session=model.boot["session"],first_error=None,
            cleanup_error=None,owned_intent=False,observations={},target_attributes=None)
        self.durable=b""
        self.closed=False
        self.flush()

    def flush(self):
        if self.model.fail_flush:
            raise RuntimeError("modeled flush failure")
        self.durable=canonical(self.data)
        self.model.events.append(("flush",json.loads(self.durable)))

    def close(self):
        self.closed=True


class ModelNative:
    def __init__(self):
        self.boot=identity(); self.clock=180999; self.op=None
        self.events=[]; self.fail_flush=False; self.fail_get=False
        self.fail_delete=False; self.unreaped=False; self.parent_alive=True
        self.parent_pids=(1234,); self.created_consumed=False; self.finished_consumed=False
        self.foreign="S-1-15-2-99"; self.config={self.foreign:0x80000004}
        self.results={"add":dict(pid=11,process_created=12,exit_code=0,timed_out=False,reaped=True),
            "delete":dict(pid=13,process_created=14,exit_code=0,timed_out=False,reaped=True)}
        self.store=ModelStore(self); self.closed=False

    def freeze(self, context, account):
        self.events.append(("freeze",context,account)); return Path("/model/admin")
    def prepare(self, root, account_sid):
        if root!=Path("/model/admin") or account_sid!=self.boot["account_sid"]:
            raise RuntimeError("modeled identity mismatch")
        return self.store
    def reopen(self, root):
        if root!=Path("/model/admin"): raise RuntimeError("modeled wrong root")
        self.store.data=json.loads(self.store.durable)
        return self.store
    def verify_store(self, store):
        if store is not self.store or not store.durable: raise RuntimeError("bad store")
    def attach_parent(self, store, pid):
        if pid!=self.boot["pid"]: raise RuntimeError("wrong pid")
        self.events.append(("attach",pid))
    def publish_manifest(self, store): self.events.append(("bootstrap_published",))
    def bootstrap(self, store): return copy.deepcopy(self.boot)
    def manifest(self, store):
        if self.op is None: raise RuntimeError("no operation")
        return self.op
    def freeze_operation(self, store):
        if self.op is not None: raise RuntimeError("operation already frozen")
        self.op=manifest(self.boot,self.clock); self.events.append(("operation",self.op.digest))
        return self.op
    def now_ms(self): return self.clock
    def verify_parent(self, store):
        if not self.parent_alive: raise RuntimeError("parent exited")
    def consume_request(self, store, kind):
        attribute="created_consumed" if kind=="profile_created" else "finished_consumed"
        if getattr(self,attribute): raise RuntimeError("consumed")
        setattr(self,attribute,True)
        self.events.append(("consume",kind))
        return (admin.encode_bootstrap_request(self.boot) if kind=="profile_created" else
                admin.encode_operation_request(self.op,self.boot["session"]))
    def full_get(self, store):
        if self.fail_get: raise RuntimeError("modeled Get failure")
        rows=[[sid,value] for sid,value in self.config.items()]
        return dict(schema=1,entries=rows,api_code=0,complete=True,
            sid_attempted=len(rows),sid_freed=len(rows),array_freed=True,
            library_freed=True,process_reaped=True)
    def command(self, store, op):
        saved=json.loads(store.durable)
        if not saved["owned_intent"] or saved["phase"] not in ("add_intent","cleanup_intent"):
            raise AssertionError("command before persisted intent")
        self.events.append(("command",op,copy.deepcopy(saved)))
        if op=="add": self.config[self.boot["positive_sid"]]=7
        elif op=="delete" and not self.fail_delete: self.config.pop(self.boot["positive_sid"],None)
        else:
            if op!="delete": raise AssertionError("nonfixed operation")
        result=copy.deepcopy(self.results[op]); self.unreaped=not result["reaped"]
        return result
    def parent_only(self, store):
        return self.parent_alive and self.parent_pids==(self.boot["pid"],)
    def reap_commands(self, store):
        if self.unreaped: raise RuntimeError("late add may still write")
        self.events.append(("commands_reaped",))
    def has_add_attempt(self, store):
        return any(event[:2]==("command","add") for event in self.events)
    def stop_parent_job(self, store):
        self.parent_pids=(); self.parent_alive=False; self.events.append(("outer_empty",))
    def publish(self, store, kind, data):
        self.events.append(("receipt",kind,copy.deepcopy(data))); return copy.deepcopy(data)
    def wait_request(self, store, kind, timeout_ms):
        self.events.append(("wait",kind,timeout_ms))


class TestAdminCoordinator(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(admin,"new admin coordinator absent; expected facility RED")
        self.model=ModelNative()
        self.patch=patch.object(admin,"Native",lambda: self.model); self.patch.start()
        self.addCleanup(self.patch.stop)
        root=admin.Admin.freeze_before_user({"candidate":"model"},"temporary-model")
        self.controller=admin.Admin.prepare(root,self.model.boot["account_sid"])
        self.controller.attach_parent(self.model.boot["pid"])

    def added(self):
        self.controller.created()
        self.assertIn(self.model.boot["positive_sid"],self.model.config)
        return self.controller

    def commands(self):
        return [event[1] for event in self.model.events if event[0]=="command"]

    def test_normal_nonempty_foreign_configuration_exactly_restored_and_intent_precedes_add(self):
        before=dict(self.model.config); self.added()
        receipt=self.controller.finished()
        self.assertEqual(self.model.config,before)
        self.assertEqual(self.commands(),["add","delete"])
        self.assertTrue(receipt["native_restoration_verified"])
        self.assertEqual(receipt["domain"],"icode_positive_operation_v1")
        command=next(event for event in self.model.events if event[:2]==("command","add"))
        self.assertEqual(command[2]["phase"],"add_intent")
        self.assertEqual(command[2]["observations"]["baseline"]["entries"],
                         [[self.model.foreign,0x80000004]])

    def test_preexisting_positive_or_reviewer_is_never_deleted_or_taken_over(self):
        for key in ("positive_sid","reviewer_sid"):
            self.setUpModelForSubcase()
            sid=self.model.boot[key]; self.model.config[sid]=0xabcdef01
            before=dict(self.model.config)
            with self.assertRaises(admin.AdminError): self.controller.created()
            receipt=self.controller.cleanup(abnormal=True)
            self.assertEqual(self.model.config,before); self.assertEqual(self.commands(),[])
            self.assertEqual(receipt["stage"],"not_owned")
            self.assertIsNone(receipt["native_restoration_verified"])

    def setUpModelForSubcase(self):
        self.model=ModelNative()
        self.controller=admin.Admin.prepare(Path("/model/admin"),self.model.boot["account_sid"])
        self.controller.attach_parent(self.model.boot["pid"])

    def test_durable_flush_failure_prevents_any_add(self):
        self.model.fail_flush=True
        with self.assertRaises(Exception): self.controller.created()
        self.assertEqual(self.commands(),[])
        self.assertNotIn(self.model.boot["positive_sid"],self.model.config)

    def test_unstable_baseline_and_incomplete_get_never_add(self):
        first=self.model.full_get(self.model.store)
        second=copy.deepcopy(first); second["entries"][0][1]=9
        with patch.object(self.model,"full_get",side_effect=[first,second]):
            with self.assertRaises(admin.AdminError): self.controller.created()
        self.assertEqual(self.commands(),[])
        self.assertEqual(self.controller.data["first_error"],"baseline_delta")
        self.setUpModelForSubcase(); self.model.fail_get=True
        with self.assertRaises(admin.AdminError): self.controller.created()
        self.assertEqual(self.commands(),[])
        self.assertEqual(self.controller.data["first_error"],"get_failed")

    def test_consumed_session_cannot_issue_second_add_or_delete(self):
        self.added()
        with self.assertRaises(admin.AdminError): self.controller.created()
        self.controller.finished()
        with self.assertRaises(admin.AdminError): self.controller.finished()
        self.assertEqual(self.commands(),["add","delete"])

    def test_add_failure_after_write_keeps_first_error_and_still_owned_cleanup(self):
        self.model.results["add"]["exit_code"]=5
        with self.assertRaises(admin.AdminError): self.controller.created()
        self.assertEqual(self.controller.data["first_error"],"add_failed")
        receipt=self.controller.cleanup(abnormal=True)
        self.assertNotIn(self.model.boot["positive_sid"],self.model.config)
        self.assertFalse(receipt["native_restoration_verified"])
        self.assertEqual(self.controller.data["first_error"],"add_failed")

    def test_unreaped_late_add_blocks_delete_until_recovery_observes_exit(self):
        self.model.results["add"]["reaped"]=False
        with self.assertRaises(admin.AdminError): self.controller.created()
        with self.assertRaises(admin.AdminError): self.controller.cleanup(abnormal=True)
        self.assertEqual(self.commands(),["add"])
        self.assertIn(self.model.boot["positive_sid"],self.model.config)
        self.model.unreaped=False
        admin.Admin.recover(Path("/model/admin"))
        self.assertEqual(self.commands(),["add","delete"])
        self.assertNotIn(self.model.boot["positive_sid"],self.model.config)
        self.assertTrue(self.model.store.closed)

    def test_foreign_change_preserved_owned_target_removed_but_restore_unknown(self):
        self.added(); self.model.config[self.model.foreign]=0xdeadbeef
        self.model.config["S-1-15-2-100"]=0x80000001
        receipt=self.controller.cleanup(abnormal=True)
        self.assertEqual(self.model.config,{self.model.foreign:0xdeadbeef,
                                           "S-1-15-2-100":0x80000001})
        self.assertFalse(receipt["native_restoration_verified"])
        self.assertEqual(self.controller.data["first_error"],"foreign_delta")

    def test_target_attribute_conflict_refuses_delete(self):
        self.added(); self.model.config[self.model.boot["positive_sid"]]=8
        with self.assertRaises(admin.AdminError): self.controller.cleanup(abnormal=True)
        self.assertEqual(self.commands(),["add"])
        self.assertEqual(self.controller.data["first_error"],"owner_conflict")
        self.assertEqual(self.model.config[self.model.boot["positive_sid"]],8)

    def test_owned_intent_without_actual_add_attempt_cannot_adopt_later_target(self):
        self.model.op=manifest(self.model.boot,self.model.clock)
        self.controller.data.update(phase="add_intent",owned_intent=True)
        self.controller.data["observations"]["baseline"]=self.model.full_get(self.model.store)
        self.controller.store.flush()
        self.model.config[self.model.boot["positive_sid"]]=7
        with self.assertRaises(admin.AdminError):self.controller.cleanup(abnormal=True)
        self.assertEqual(self.commands(),[])
        self.assertEqual(self.controller.data["first_error"],"owner_conflict")
        self.assertEqual(self.model.config[self.model.boot["positive_sid"]],7)

    def test_deadline_cleanup_removes_target_without_success_credit(self):
        self.added(); self.model.clock=self.model.op.deadline_ms
        receipt=self.controller.cleanup(abnormal=True)
        self.assertNotIn(self.model.boot["positive_sid"],self.model.config)
        self.assertFalse(receipt["native_restoration_verified"])
        self.assertEqual(self.controller.data["first_error"],"deadline")

    def test_extra_job_member_causes_abnormal_stop_before_delete(self):
        self.added(); self.model.parent_pids=(1234,4321)
        with self.assertRaises(admin.AdminError): self.controller.finished()
        self.assertEqual(self.model.parent_pids,())
        events=[event[0] for event in self.model.events]
        stop=events.index("outer_empty")
        deletion=next(i for i,event in enumerate(self.model.events) if event[:2]==("command","delete"))
        self.assertLess(stop,deletion)
        self.assertEqual(self.controller.data["first_error"],"parent_failed")

    def test_cleanup_failure_retains_operation_first_error_and_ledger(self):
        self.model.results["add"]["exit_code"]=5
        with self.assertRaises(admin.AdminError): self.controller.created()
        self.model.fail_delete=True
        with self.assertRaises(admin.AdminError): self.controller.cleanup(abnormal=True)
        saved=json.loads(self.model.store.durable)
        self.assertEqual(saved["first_error"],"add_failed")
        self.assertEqual(saved["cleanup_error"],"cleanup_failed")
        self.assertTrue(saved["owned_intent"])

    def test_serve_wait_freeze_and_publish_failures_are_durable_non_success(self):
        for boundary in ("first_wait","second_wait","freeze_operation","publish_add"):
            with self.subTest(boundary=boundary):
                self.setUpModelForSubcase()
                original_publish=self.model.publish
                def wait(store,kind,timeout_ms):
                    if boundary==("first_wait" if kind=="profile_created" else "second_wait"):
                        raise RuntimeError("modeled request IO failure")
                def publish(store,kind,value):
                    if boundary=="publish_add" and kind=="add":raise RuntimeError("modeled publication failure")
                    return original_publish(store,kind,value)
                stack=[patch.object(self.model,"wait_request",wait),patch.object(self.model,"publish",publish)]
                if boundary=="freeze_operation":
                    stack.append(patch.object(self.model,"freeze_operation",side_effect=RuntimeError("modeled freeze failure")))
                for item in stack:item.start()
                try:
                    with self.assertRaises(Exception):self.controller.serve()
                finally:
                    for item in reversed(stack):item.stop()
                saved=json.loads(self.model.store.durable)
                self.assertIsNotNone(saved["first_error"],"serve boundary error must precede cleanup success")
                self.assertFalse(saved.get("exact_restoration",False))
                receipts=[event[2] for event in self.model.events if event[:2]==("receipt","cleanup")]
                self.assertTrue(all(value.get("native_restoration_verified") is not True for value in receipts))

    def test_serve_wait_body_survives_cleanup_error_without_lying_about_durable_first_error(self):
        body=RuntimeError("modeled_wait_body")
        def wait(store,kind,timeout):
            if kind=="probe_finished":raise body
        self.model.fail_delete=True
        with patch.object(self.model,"wait_request",wait):
            with self.assertRaises(RuntimeError) as caught:self.controller.serve()
        saved=json.loads(self.model.store.durable)
        self.assertEqual(saved["first_error"],"finished_request")
        self.assertEqual(saved["cleanup_error"],"cleanup_failed")
        self.assertIs(caught.exception,body)
        self.assertTrue(any(n.startswith("cleanup_unknown:") for n in getattr(body,"__notes__",())))

    def test_recover_actual_cleanup_body_survives_final_store_close(self):
        self.added();self.model.fail_get=True;captured=[]
        original=admin.Admin.cleanup
        def observe(controller,**options):
            try:return original(controller,**options)
            except BaseException as error:captured.append(error);raise
        def close():raise RuntimeError("modeled_recover_close")
        with patch.object(admin.Admin,"cleanup",observe),patch.object(self.model.store,"close",close):
            with self.assertRaises(Exception) as caught:admin.Admin.recover(Path("/model/admin"))
        self.assertEqual(len(captured),1);self.assertIs(caught.exception,captured[0])
        self.assertTrue(any(n.startswith("cleanup_unknown:") for n in getattr(caught.exception,"__notes__",())))


if __name__=="__main__":
    unittest.main()
```

## Task 5：真实 Store 算法的完整软件 TEST 资产

**Dependencies:** Task 3、主 PLAN `scripts/windows_positive_loopback_admin_store.py` 完整资产。
**Parallelizable:** No（身份/Flush合同需与 Native facade 共同冻结）。

- [ ] apply_patch 新增完整 `tests/test_windows_positive_loopback_admin_store.py`。
- [ ] 运行 `PYTHONPATH=src python -m unittest tests.test_windows_positive_loopback_admin_store -v`。模型句柄对应真实字节表，生产 Store 读取/写入/核identity/序列化；不把该层称真实NTFS locking/ACL证明。

```python
"""Real Store algorithms over byte/identity model; no native filesystem proof."""
from __future__ import annotations
import importlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

NAME="scripts.windows_positive_loopback_admin_store"
try:
    storage=importlib.import_module(NAME)
except ModuleNotFoundError as exc:
    if exc.name!=NAME: raise
    storage=None


class Files:
    def __init__(self):
        self.nodes={}; self.handles={}; self.next=100; self.events=[]
        self.replace_during_read=False; self.fail_write=False
    def open_file(self,path,descriptor,*,create=False,write=False,**options):
        name=Path(path).name
        if create:
            if name in self.nodes: raise RuntimeError("already exists")
            self.nodes[name]=dict(identity=(7,self.next),bytes=b"",descriptor=descriptor)
        if name not in self.nodes: raise RuntimeError("absent")
        node=self.nodes[name]
        if node["descriptor"]!=descriptor: raise RuntimeError("descriptor mismatch")
        handle=self.next; self.next+=1; self.handles[handle]=node
        self.events.append(("open",name,write))
        return handle,node["identity"]
    def read(self,handle,limit):
        node=self.handles[handle]
        if self.replace_during_read: node["identity"]=(8,999)
        if len(node["bytes"])>limit: raise RuntimeError("too large")
        return node["bytes"]
    def write(self,handle,value):
        node=self.handles[handle]; node["bytes"]=value
        self.events.append(("bytes",value))
        if self.fail_write: raise RuntimeError("modeled Flush failure")
        self.events.append(("durable",value))
    def info(self,handle,**options): return self.handles[handle]["identity"]
    def close(self,handle):
        self.events.append(("close",handle)); del self.handles[handle]


class TestAdminStore(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(storage,"new Store component absent; facility RED")
        self.store=storage.Store.__new__(storage.Store)
        self.store.root=Path("/model/icode-positive-admin-"+"1"*32)
        self.store.data=dict(schema=1,account_sid="S-1-5-21-1-2-3-1001",file_identities={})
        self.store.w=Files(); self.store.handles=[]; self.store.pins=[]

    def test_canonical_wire_real_decode_duplicate_nan_utf8_limits(self):
        value={"b":2,"a":1}
        self.assertEqual(storage.wire(value),b'{"a":1,"b":2}')
        self.assertEqual(storage.decode(storage.wire(value),100),value)
        for bad in (b"",b"x"*101,b"\xff",b'{"a":1,"a":2}',b'{"a":NaN}'):
            with self.subTest(bad=bad),self.assertRaises(storage.Failure):
                storage.decode(bad,100)

    def test_roles_exact_account_binding_and_private_default(self):
        private=self.store.file_descriptor("private")
        self.assertEqual(private,storage.PRIVATE)
        public=self.store.file_descriptor("public")
        request=self.store.file_descriptor("request")
        self.assertEqual(public,private+"(A;;FR;;;S-1-5-21-1-2-3-1001)")
        self.assertEqual(request,private+"(A;;0x120003;;;S-1-5-21-1-2-3-1001)")
        with self.assertRaises(storage.Failure): self.store.file_descriptor("execute")
        self.store.data["account_sid"]="S-1-5-18"
        with self.assertRaises(storage.Failure): self.store.file_descriptor("request")

    def test_create_write_read_real_bytes_and_identity_saved(self):
        self.store.write("bootstrap.json",b"first","public",create=True)
        identity=self.store.data["file_identities"]["bootstrap.json"]
        self.assertEqual(identity,[7,100])
        self.store.write("bootstrap.json",b"second","public")
        self.assertEqual(self.store.read("bootstrap.json",self.store.file_descriptor("public"),100),b"second")
        self.assertEqual(self.store.w.handles,{})
        self.assertEqual(self.store.w.nodes["bootstrap.json"]["bytes"],b"second")

    def test_replaced_file_before_write_or_during_read_rejects_and_closes_handle(self):
        self.store.write("receipt.json",b"valid","public",create=True)
        node=self.store.w.nodes["receipt.json"]
        node["identity"]=(7,999)
        with self.assertRaises(storage.Failure): self.store.write("receipt.json",b"forged","public")
        self.assertEqual(node["bytes"],b"valid")
        node["identity"]=tuple(self.store.data["file_identities"]["receipt.json"])
        self.store.w.replace_during_read=True
        with self.assertRaises(storage.Failure):
            self.store.read("receipt.json",self.store.file_descriptor("public"),100)
        self.assertEqual(self.store.w.handles,{})

    def test_flush_serializes_actual_data_and_propagates_durable_failure(self):
        self.store.w.nodes["ledger.json"]=dict(identity=(7,200),bytes=b"old",descriptor=storage.PRIVATE)
        self.store.data["file_identities"]["ledger.json"]=[7,200]
        self.store.flush()
        saved=json.loads(self.store.w.nodes["ledger.json"]["bytes"])
        self.assertEqual(saved,self.store.data)
        self.store.data["owned_intent"]=True; self.store.w.fail_write=True
        with self.assertRaises(RuntimeError): self.store.flush()
        self.assertEqual(self.store.w.handles,{})
        self.assertNotEqual(self.store.w.events[-2][0],"durable")

    def test_leaf_names_reject_paths_and_freeform_names(self):
        for name in ("../ledger.json","a/b","a\\b",".","..","",1,"x"*101):
            with self.subTest(name=name),self.assertRaises(storage.Failure): self.store._leaf(name)
        for name in ("ledger.json","profile_created.request","probe_finished.request"):
            self.store._leaf(name)

    def directory_model(self, root):
        # Real namespace existence; only the Win32 consumer boundary is modeled.
        # No exists() patch and no exists_ok: a duplicate leaf is never created.
        model=SimpleNamespace(created=[],trusted={root},handles={},next=700)
        def create(path,descriptor):
            self.assertEqual(descriptor,storage.PRIVATE)
            path.mkdir()
            model.created.append(path); model.trusted.add(path)
        def pin(path,**options):
            if path not in model.trusted: raise storage.Failure("untrusted_directory")
            handle=model.next; model.next+=1; model.handles[handle]=path
            return handle
        model.create_directory=create; model.pin_ancestor=pin
        def opened(path,descriptor,*,directory=False,**options):
            self.assertEqual(descriptor,storage.PRIVATE);self.assertTrue(directory)
            if path not in model.trusted or path.is_symlink() or path.resolve(strict=True)!=path:
                raise storage.Failure("untrusted_directory")
            handle=pin(path)
            return handle,(7,path.stat().st_ino)
        model.open_file=opened
        model.info=lambda handle,**options:(7,model.handles[handle].stat().st_ino)
        model.close=lambda handle:model.handles.pop(handle)
        self.store.root=root; self.store.w=model
        return model

    def test_freeze_nested_trusted_directory_sequence_uses_real_store(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); model=self.directory_model(root)
            # Exact Native.freeze ordering, not a replacement FakeStore method.
            sequence=("trusted","trusted/scripts","trusted/src","trusted/src/icode")
            for relative in sequence:
                try:self.store.create_directory(relative)
                except storage.Failure as exc:
                    self.fail("Native.freeze nested directory chain rejected "+relative+": "+str(exc))
            expected=[root/name for name in sequence]
            self.assertEqual(model.created,expected)
            self.assertTrue(all(path.is_dir() for path in expected))
            self.assertEqual(set(self.store.pins),set(model.handles))
            self.assertTrue(self.store.pins,"admitted directory identities remain pinned until Store.close")
            self.store.close()
            self.assertEqual(model.handles,{})

    def test_directory_creation_still_rejects_existing_leaf_without_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); model=self.directory_model(root)
            self.store.create_directory("trusted")
            with self.assertRaises(storage.Failure):self.store.create_directory("trusted")
            self.assertEqual(model.created,[root/"trusted"])
            self.store.close()
            self.assertEqual(model.handles,{})

    def test_directory_creation_rejects_preexisting_untrusted_ancestor(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); model=self.directory_model(root)
            (root/"foreign").mkdir()  # Not admitted by the private-directory model.
            with self.assertRaises(storage.Failure):self.store.create_directory("foreign/child")
            self.assertFalse((root/"foreign/child").exists())
            self.assertEqual(model.created,[])
            self.assertEqual(model.handles,{})

    def test_close_attempts_all_handles_even_when_one_release_fails(self):
        attempted=[]
        def close(handle):
            attempted.append(handle)
            if handle==2: raise storage.Failure("release failed")
        self.store.w=SimpleNamespace(close=close)
        self.store.handles=[1,2]; self.store.pins=[3,4]
        with self.assertRaises(storage.Failure): self.store.close()
        self.assertEqual(attempted,[2,1,4,3])
        self.assertEqual((self.store.handles,self.store.pins),([],[]))

    def test_store_file_owners_preserve_body_with_close_failure(self):
        for owner in ("flush","read","write"):
            with self.subTest(owner=owner):
                self.setUp();body=storage.Failure("modeled_store_"+owner)
                model=self.store.w;model.nodes["ledger.json"]=dict(identity=(7,200),bytes=b"{}",descriptor=storage.PRIVATE)
                self.store.data["file_identities"]["ledger.json"]=[7,200]
                attempted=[]
                def bad_close(handle):attempted.append(handle);raise storage.Failure("modeled_store_close")
                def bad_body(*args):raise body
                model.close=bad_close
                if owner=="read":model.read=bad_body
                else:model.write=bad_body
                with self.assertRaises(storage.Failure) as caught:
                    if owner=="flush":self.store.flush()
                    elif owner=="read":self.store.read("ledger.json",storage.PRIVATE,100)
                    else:self.store.write("ledger.json",b"new")
                self.assertEqual(len(attempted),1)
                self.assertIs(caught.exception,body)
                self.assertTrue(any(n.startswith("cleanup_unknown:") for n in getattr(body,"__notes__",())))

    def test_store_create_owned_file_and_pin_cleanup_attempts_all_preserves_body(self):
        for failed_kind in ("ledger.json","root","route"):
            for body_failed in (False,True):
                with self.subTest(failed_kind=failed_kind,body_failed=body_failed):
                    root=Path("/model/parent/icode-positive-admin-"+"1"*32)
                    acquired={};attempted=[];counter=[100];failed=[];body=storage.Failure("modeled_create_body")
                    def allocate(kind):
                        handle=counter[0];counter[0]+=1;acquired[handle]=kind;return handle
                    def opened(path,*args,**options):
                        handle=allocate("root" if options.get("directory") else Path(path).name)
                        return handle,(7,handle)
                    def close(handle):
                        if handle not in acquired:raise AssertionError("unowned/double close")
                        attempted.append(handle)
                        if acquired[handle]==failed_kind and not failed:
                            failed.append(handle);raise storage.Failure("modeled_create_close")
                        del acquired[handle]
                    def write(handle,value):
                        if body_failed and acquired[handle]=="ledger.json":raise body
                    model=SimpleNamespace(assert_admin=lambda:None,pin_ancestor=lambda *a,**k:allocate("route"),
                        create_directory=lambda *a:None,open_file=opened,write=write,close=close)
                    with patch.object(storage,"Win32",lambda:model):
                        with self.assertRaises(storage.Failure) as caught:
                            storage.Store.create(root,dict(schema=1,file_identities={}))
                    self.assertEqual(set(acquired),set(failed),"Store.create must attempt every independently owned pin")
                    self.assertEqual(len(attempted),len(set(attempted)))
                    if body_failed:self.assertIs(caught.exception,body)
                    self.assertTrue(any(n.startswith("cleanup_unknown:") for n in getattr(caught.exception,"__notes__",())))

    def test_store_init_directory_and_close_owners_preserve_original_failure(self):
        for owner in ("init","directory","close"):
            with self.subTest(owner=owner):
                body=storage.Failure("modeled_"+owner+"_body");attempted=[];alive={}
                def allocate(kind):
                    handle=100+len(alive);alive[handle]=kind;return handle
                def close(handle):
                    attempted.append(handle)
                    if handle not in alive:raise AssertionError("unowned/double close")
                    if not hasattr(close,"failed"):
                        close.failed=True;raise body if owner=="close" else storage.Failure("modeled_close")
                    del alive[handle]
                if owner=="close":
                    self.store.handles=[allocate("file"),allocate("file")];self.store.pins=[allocate("pin")]
                    self.store.w=SimpleNamespace(close=close)
                    with self.assertRaises(storage.Failure) as caught:self.store.close()
                elif owner=="directory":
                    with tempfile.TemporaryDirectory() as temporary:
                        root=Path(temporary);model=self.directory_model(root);original_info=model.info
                        def info(handle,**options):raise body
                        model.info=info;original_close=model.close
                        def fail_close(handle):attempted.append(handle);raise storage.Failure("modeled_directory_close")
                        model.close=fail_close
                        with self.assertRaises(storage.Failure) as caught:self.store.create_directory("one/two")
                        self.assertEqual(len(attempted),2)
                else:
                    root=Path("/model/icode-positive-admin-"+"1"*32)
                    def info(handle,**options):
                        if alive[handle]=="root":raise body
                        return (7,handle)
                    model=SimpleNamespace(assert_admin=lambda:None,
                        pin_ancestor=lambda path,**k:allocate("root" if path==root else "route"),
                        info=info,observe_security=lambda handle:{},close=close)
                    with patch.object(storage,"Win32",lambda:model),patch.object(Path,"resolve",lambda path,**k:path):
                        with self.assertRaises(storage.Failure) as caught:storage.Store(root)
                    self.assertEqual(len(alive),1)
                self.assertIs(caught.exception,body)
                self.assertTrue(any(n.startswith("cleanup_unknown:") for n in getattr(caught.exception,"__notes__",())))

    def tree(self,source,names,*,enumeration_error=False,drift=False,reparse=None,clock=None,faults=None):
        model=SimpleNamespace(opened=0,written=0,closed=[],creates=[])
        def create_file(path,*args): model.opened+=1; return 501
        model.k=SimpleNamespace(CreateFileW=create_file)
        model.create_directory=lambda path,descriptor:model.creates.append(path)
        model.verify_ancestor=lambda handle:None
        calls={}
        def info(handle):
            calls[handle]=calls.get(handle,0)+1
            return (7,999 if drift and handle==501 and calls[handle]>1 else handle)
        model.info=info
        model.read=lambda handle,size:b""
        model.open_file=lambda *args,**options:(502,(7,502))
        def write(handle,value): model.written+=1
        model.write=write; model.close=lambda handle:model.closed.append(handle)
        if faults is not None:
            faults["model"]=model
            def release(handle):
                model.closed.append(handle)
                if handle==faults["failed"]:raise storage.Failure("modeled_copy_close")
            model.close=release
            if faults.get("body") is not None:
                def failed_write(*args):raise faults["body"]
                model.write=failed_write
        store=SimpleNamespace(root=self.store.root,w=model)
        def walk(root,topdown=True,followlinks=False,onerror=None):
            yield str(source),[],names
            if enumeration_error:
                if onerror is not None: onerror(OSError("modeled child scandir denied"))
                return
        def symlink(path):
            return path==reparse if reparse is not None else False
        def lstat(path,*args,**kwargs):
            return SimpleNamespace(st_size=0,st_file_attributes=0x400 if path==reparse else 0)
        stack=[patch.object(storage.os,"walk",walk),patch.object(Path,"is_symlink",symlink),
               patch.object(Path,"lstat",lstat)]
        if clock is not None:stack.append(patch.object(storage.time,"monotonic",side_effect=clock))
        for item in stack:item.start()
        try:
            result=storage.copy_private_tree(store,source,"runtime",deadline=1 if clock else 10**20)
            return result,model
        finally:
            for item in reversed(stack):item.stop()

    def test_copytree_child_enumeration_failure_rejects_partial_records(self):
        with tempfile.TemporaryDirectory() as temporary:
            source=Path(temporary)
            with self.assertRaises((OSError,storage.Failure)):
                self.tree(source,["normal.bin"],enumeration_error=True)

    def test_copytree_output_source_release_attempts_all_and_preserves_body(self):
        for failed in (502,501):
            for body_failed in (False,True):
                with self.subTest(failed=failed,body_failed=body_failed),tempfile.TemporaryDirectory() as temporary:
                    body=storage.Failure("modeled_copy_body") if body_failed else None
                    faults=dict(failed=failed,body=body)
                    with self.assertRaises(storage.Failure) as caught:self.tree(Path(temporary),["normal.bin"],faults=faults)
                    self.assertEqual(faults["model"].closed,[502,501])
                    if body_failed:self.assertIs(caught.exception,body)
                    self.assertTrue(any(n.startswith("cleanup_unknown:") for n in getattr(caught.exception,"__notes__",())))

    def test_copytree_root_or_child_reparse_identity_drift_and_deadline_reject(self):
        with tempfile.TemporaryDirectory() as temporary:
            source=Path(temporary)
            for reparse in (source,source/"child.bin"):
                with self.subTest(reparse=reparse),self.assertRaises(storage.Failure):
                    self.tree(source,["child.bin"],reparse=reparse)
            with self.assertRaises(storage.Failure):self.tree(source,["normal.bin"],drift=True)
            with self.assertRaises(storage.Failure):self.tree(source,["normal.bin"],clock=[0,2,2,2])

    def test_copytree_actual_count_ceiling_is_not_truncated_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            source=Path(temporary)
            with self.assertRaises(storage.Failure):
                self.tree(source,[f"file-{index}.bin" for index in range(100001)])


if __name__=="__main__":
    unittest.main()
```

## Task 6：真实 run_fixed / Job 生命周期完整 TEST 资产

**Dependencies:** Task 3、5 与主 PLAN `scripts/windows_positive_loopback_admin_jobs.py` 完整资产。
**Parallelizable:** No（持久状态、Resume和独立recovery须同一合同）。

- [ ] apply_patch 新增完整 `tests/test_windows_positive_loopback_admin_jobs.py`。
- [ ] 运行 `PYTHONPATH=src python -m unittest tests.test_windows_positive_loopback_admin_jobs -v`。该资产直接运行生产 run_fixed/create_job/wait_empty/_argv 与生产 Win32 job_pids/process_created；只在最底层 Win32 callable/受保护Store I/O边界使用模型。

```python
"""Fixed Job algorithm on real ctypes buffers and synthetic process handles."""
from __future__ import annotations
import copy
import ctypes as c
from ctypes import wintypes as t
import importlib
import json
from pathlib import Path, PureWindowsPath
import struct
from types import SimpleNamespace as N
import unittest
from unittest.mock import patch

NAME="scripts.windows_positive_loopback_admin_jobs"
try:
    jobs=importlib.import_module(NAME)
except ModuleNotFoundError as exc:
    if exc.name!=NAME: raise
    jobs=None


def put(pointer,kind,value): c.cast(pointer,c.POINTER(kind))[0]=value


class Kernel:
    def __init__(self,store,win32):
        self.store,self.win32=store,win32
        self.mode="ok"; self.events=[]; self.members=(); self.exited=False
        self.resumed=False; self.alive=set(); self.attributes={}
        self.closed=[]; self.null_created=False
    def LocalFree(self,pointer): return 0
    def CreateJobObjectW(self,security,name):
        self.events.append("job"); self.alive.add(10); return 10
    def SetInformationJobObject(self,job,kind,pointer,size):
        limits=c.cast(pointer,c.POINTER(self.win32.EXTENDED_LIMITS)).contents
        if (job,kind,limits.basic.flags)!=(10,9,0x2000): raise AssertionError("limits")
        return 1
    def CreateFileW(self,path,access,sharing,security,creation,flags,template):
        if path!=r"\\.\NUL": raise AssertionError("nonfixed null path")
        self.null_created=True; self.alive.add(21); return 21
    def InitializeProcThreadAttributeList(self,pointer,count,flags,size):
        if count!=2 or flags!=0: raise AssertionError("attribute count")
        put(size,c.c_size_t,128); return pointer is not None
    def UpdateProcThreadAttribute(self,attribute_list,flags,kind,pointer,size,previous,returned):
        self.attributes[kind]=(pointer.value,size)
        return 1
    def DeleteProcThreadAttributeList(self,pointer): self.events.append("delete_attributes")
    def CreateProcessW(self,application,command,process_security,thread_security,inherit,flags,
                       environment,cwd,startup,output):
        self.events.append("create_suspended")
        if flags!=(4|0x400|0x80000|0x08000000) or inherit is not True:
            raise AssertionError("flags")
        if application!=self.store.data["system_tool"]["path"]: raise AssertionError("tool")
        if set(self.attributes)!={0x2000D,0x20002}: raise AssertionError("attributes")
        ptr,size=self.attributes[0x2000D]
        if size!=c.sizeof(t.HANDLE) or c.cast(ptr,c.POINTER(t.HANDLE))[0]!=10:
            raise AssertionError("job-list lifetime")
        ptr,size=self.attributes[0x20002]
        if tuple(c.cast(ptr,c.POINTER(t.HANDLE))[i] for i in range(2))!=(20,21):
            raise AssertionError("handle-list lifetime")
        start=c.cast(startup,c.POINTER(self.win32.STARTUP_EX)).contents
        if (start.startup.stdin,start.startup.stdout,start.startup.stderr)!=(21,20,20):
            raise AssertionError("stdio")
        process=c.cast(output,c.POINTER(self.win32.PROCESS)).contents
        process.process=30; process.thread=31
        self.alive.update((30,31))
        process.pid=0 if self.mode=="zero_pid" else 1234; process.tid=1235
        self.members=(9999,) if self.mode=="admission" else (1234,)
        return 1
    def GetProcessTimes(self,handle,created,exited,kernel,user):
        value=c.cast(created,c.POINTER(t.FILETIME)).contents
        value.dwLowDateTime=5678; value.dwHighDateTime=0; return 1
    def QueryInformationJobObject(self,job,kind,output,capacity,returned):
        if self.resumed and self.mode=="query_failure_after_resume": return 0
        c.memmove(output,struct.pack("<II",len(self.members),len(self.members)),8)
        if self.resumed and self.mode=="query_incomplete_after_resume":
            c.memmove(output,struct.pack("<II",len(self.members)+1,len(self.members)),8)
        values=c.cast(c.byref(output,8),c.POINTER(c.c_size_t))
        for index,pid in enumerate(self.members): values[index]=pid
        put(returned,t.DWORD,8+len(self.members)*c.sizeof(c.c_size_t)); return 1
    def ResumeThread(self,thread):
        self.events.append("resume")
        saved=json.loads(self.store.durable)
        record=saved["commands"][-1]
        if record["state"]!="ready" or record["resume_attempted"] is not None:
            raise AssertionError("resume without flushed ready identity")
        self.resumed=True
        if self.mode=="resume_exception": raise RuntimeError("ambiguous Resume")
        return 0 if self.mode=="resume_bad" else 1
    def WaitForSingleObject(self,handle,milliseconds):
        self.events.append(("wait",milliseconds))
        if milliseconds==5000:
            if self.mode=="reap_timeout": return 258
            self.exited=True
            self.members=(4321,) if self.mode in ("descendant","persistent_descendant","terminate_failure") else ()
            return 0
        if self.mode=="reap_timeout": return 258
        return 0 if self.exited else 258
    def TerminateJobObject(self,job,code):
        self.events.append("terminate")
        if self.mode=="terminate_failure": return 0
        self.exited=True
        if self.mode!="persistent_descendant": self.members=()
        return 1
    def GetExitCodeProcess(self,handle,output):
        self.events.append("exit_code")
        if self.mode=="exit_failure": return 0
        put(output,t.DWORD,0); return 1
    def CloseHandle(self,handle):
        if handle not in self.alive: raise AssertionError("double or unowned close")
        self.closed.append(handle)
        if self.mode=="close_failure" and handle==31: return 0
        self.alive.discard(handle); return 1


class ModelStore:
    def __init__(self,win32):
        self.root=Path("/model/admin")
        self.data=dict(session="4"*32,commands=[],owned_intent=True,phase="add_intent",
            operation_manifest=dict(started_ms=1000,deadline_ms=61000),
            bootstrap=dict(positive_sid="S-1-15-2-1",reviewer_sid="S-1-15-2-2"),
            system_tool=dict(path=r"C:\Windows\System32\CheckNetIsolation.exe"))
        self.w=win32.Win32.__new__(win32.Win32)
        self.kernel=Kernel(self,win32); self.w.k=self.kernel
        self.w.system_directory=PureWindowsPath(r"C:\Windows\System32")
        self.w.descriptor=lambda sddl:c.c_void_p(700)
        self.w.verify_security=lambda *args,**kwargs:None
        def open_output(*args,**kwargs):
            self.kernel.alive.add(20); return 20,(7,20)
        self.w.open_file=open_output
        self.files={}; self.durable=b""; self.fail_flush_state=None
        self.failed_once=False; self.flushes=[]
        self.flush()
    def write(self,name,value,*,create=False):
        if create and name in self.files: raise AssertionError("duplicate output")
        self.files[name]=value
    def flush(self):
        current=self.data["commands"][-1] if self.data["commands"] else {}
        if self.fail_flush_state is not None and current.get("state")==self.fail_flush_state and not self.failed_once:
            self.failed_once=True; raise RuntimeError("modeled FlushFileBuffers failed")
        self.durable=json.dumps(self.data,sort_keys=True,separators=(",",":"))
        self.flushes.append(copy.deepcopy(self.data))


class TestAdminJobs(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(jobs,"new fixed Job adapter absent; facility RED")
        self.win32=importlib.import_module("scripts.windows_positive_loopback_admin_win32")
        self.store=ModelStore(self.win32)
        self.patches=[patch.object(jobs.c,"set_last_error",lambda value:None,create=True),
                      patch.object(jobs.c,"get_last_error",lambda:0,create=True),
                      patch.object(jobs.time,"monotonic",lambda:1.0),
                      patch.object(jobs.time,"sleep",lambda seconds:None)]
        for item in self.patches: item.start(); self.addCleanup(item.stop)

    def test_normal_real_run_fixed_flushes_ready_before_resume_and_reaps_all(self):
        result=jobs.run_fixed(self.store,"add")
        self.assertTrue(result["reaped"])
        self.assertEqual((result["pid"],result["process_created"],result["resume_returned"]),(1234,5678,1))
        self.assertEqual(self.store.kernel.members,())
        self.assertTrue(self.store.kernel.exited)
        self.assertEqual(set(self.store.kernel.closed),{10,20,21,30,31})
        self.assertEqual(self.store.kernel.alive,set())
        self.assertEqual(json.loads(self.store.durable)["commands"][-1]["state"],"reaped")

    def test_create_job_final_descriptor_free_failure_closes_unreturned_job(self):
        self.store.kernel.LocalFree=lambda pointer:700
        with self.assertRaises(self.win32.Failure):
            jobs.create_job(self.store,"Local\\ICODE.Positive.test")
        self.assertEqual(self.store.kernel.alive,set(),"failed return must not strand acquired Job")
        self.assertEqual(self.store.kernel.closed,[10])

    def test_create_job_body_is_not_replaced_by_descriptor_or_job_cleanup(self):
        for failed in ("descriptor","job"):
            with self.subTest(failed=failed):
                self.store=ModelStore(self.win32);k=self.store.kernel
                body=self.win32.Failure("modeled_job_body")
                def limits(*args):raise body
                k.SetInformationJobObject=limits
                original_close=k.CloseHandle
                if failed=="descriptor":k.LocalFree=lambda pointer:700
                else:
                    def close(handle):original_close(handle);raise self.win32.Failure("modeled_job_close")
                    k.CloseHandle=close
                with self.assertRaises(self.win32.Failure) as caught:jobs.create_job(self.store,"Local\\owned")
                self.assertEqual(k.closed,[10])
                self.assertIs(caught.exception,body)
                self.assertTrue(any(n.startswith("cleanup_unknown:") for n in getattr(body,"__notes__",())))

    def test_run_fixed_body_survives_all_cleanup_boundaries_and_all_handles_attempted(self):
        for failed in ("thread","attributes","terminate","flush"):
            with self.subTest(failed=failed):
                self.store=ModelStore(self.win32);k=self.store.kernel
                body=self.win32.Failure("modeled_command_body")
                def resume(thread):raise body
                k.ResumeThread=resume
                if failed=="thread":k.mode="close_failure"
                elif failed=="attributes":
                    def attributes(pointer):raise self.win32.Failure("modeled_attributes_cleanup")
                    k.DeleteProcThreadAttributeList=attributes
                elif failed=="terminate":k.mode="terminate_failure"
                else:self.store.fail_flush_state="reaped_after_failure"
                clock=[1.0]
                def now():clock[0]+=0.01;return clock[0]
                with patch.object(jobs.time,"monotonic",now),self.assertRaises(self.win32.Failure) as caught:
                    jobs.run_fixed(self.store,"add")
                self.assertEqual(set(k.closed),{10,20,21,30,31},"cleanup failure must not stop independent CloseHandle attempts")
                self.assertIs(caught.exception,body)
                self.assertTrue(any(n.startswith("cleanup_unknown:") for n in getattr(body,"__notes__",())))

    def test_successful_create_bad_pid_or_job_admission_never_resumes_and_reaps(self):
        for mode in ("zero_pid","admission"):
            self.store=ModelStore(self.win32); self.store.kernel.mode=mode
            with self.subTest(mode=mode),self.assertRaises(self.win32.Failure):
                jobs.run_fixed(self.store,"add")
            self.assertFalse(self.store.kernel.resumed)
            self.assertTrue(self.store.kernel.exited); self.assertEqual(self.store.kernel.members,())
            self.assertIn("terminate",self.store.kernel.events)

    def test_ready_flush_failure_never_resumes_and_actually_reaps_suspended_process(self):
        self.store.fail_flush_state="ready"
        with self.assertRaises(RuntimeError): jobs.run_fixed(self.store,"add")
        self.assertFalse(self.store.kernel.resumed)
        self.assertTrue(self.store.kernel.exited); self.assertEqual(self.store.kernel.members,())
        saved=json.loads(self.store.durable)["commands"][-1]
        self.assertFalse(saved["resume_attempted"])
        self.assertTrue(saved["reaped"])

    def test_ready_flush_crossing_core_deadline_never_resumes(self):
        clock={"now":1.0};original=self.store.flush
        self.store.data["operation_manifest"]["deadline_ms"]=1500
        def flush():
            original()
            if self.store.data["commands"] and self.store.data["commands"][-1]["state"]=="ready":clock["now"]=1.6
        self.store.flush=flush
        with patch.object(jobs.time,"monotonic",lambda:clock["now"]):
            with self.assertRaises(self.win32.Failure):jobs.run_fixed(self.store,"add")
        self.assertFalse(self.store.kernel.resumed)
        self.assertTrue(self.store.kernel.exited)
        self.assertEqual(self.store.kernel.members,())
        self.assertFalse(json.loads(self.store.durable)["commands"][-1]["resume_attempted"])

    def test_resume_nonone_and_ambiguous_exception_do_not_return_success(self):
        for mode in ("resume_bad","resume_exception"):
            self.store=ModelStore(self.win32); self.store.kernel.mode=mode
            with self.subTest(mode=mode),self.assertRaises((self.win32.Failure,RuntimeError)):
                jobs.run_fixed(self.store,"add")
            self.assertTrue(self.store.kernel.resumed)
            self.assertTrue(self.store.kernel.exited); self.assertEqual(self.store.kernel.members,())

    def test_root_exit_is_insufficient_while_descendant_pid_remains(self):
        self.store.kernel.mode="descendant"
        result=jobs.run_fixed(self.store,"add")
        self.assertTrue(result["reaped"])
        self.assertIn("terminate",self.store.kernel.events)
        self.assertEqual(self.store.kernel.members,())
        events=self.store.kernel.events
        self.assertLess(events.index("terminate"),events.index("exit_code"))

    def test_exitcode_and_final_flush_failure_raise_despite_process_exit(self):
        for mode in ("exit_failure","final_flush"):
            self.store=ModelStore(self.win32)
            if mode=="final_flush":self.store.fail_flush_state="reaped"
            else:self.store.kernel.mode=mode
            with self.subTest(mode=mode),self.assertRaises((self.win32.Failure,RuntimeError)):
                jobs.run_fixed(self.store,"add")
            self.assertTrue(self.store.kernel.exited); self.assertEqual(self.store.kernel.members,())

    def test_final_close_failure_cannot_return_success(self):
        self.store.kernel.mode="close_failure"
        with self.assertRaises(self.win32.Failure): jobs.run_fixed(self.store,"add")
        self.assertEqual(set(self.store.kernel.closed),{10,20,21,30,31})
        self.assertEqual(self.store.kernel.alive,{31})

    def test_argv_fixed_positive_sid_and_replay_refusal(self):
        expected=[r"C:\Windows\System32\CheckNetIsolation.exe","LoopbackExempt","-a","-p=S-1-15-2-1"]
        self.assertEqual(jobs._argv(self.store,"add"),expected)
        self.store.data["phase"]="cleanup_intent"
        self.assertEqual(jobs._argv(self.store,"delete"),expected[:2]+["-d",expected[-1]])
        for kind in ("clear","-c","-is","shell",None):
            with self.subTest(kind=kind),self.assertRaises(self.win32.Failure):jobs._argv(self.store,kind)
        self.store.data["phase"]="add_intent"
        self.store.data["commands"].append(dict(kind="add"))
        with self.assertRaises(self.win32.Failure):jobs._argv(self.store,"add")

    def advancing_clock(self):
        state={"calls":0,"now":0.0}
        def now():
            state["calls"]+=1
            if state["calls"]>40: raise AssertionError("test clock finite-step guard")
            state["now"]+=0.75
            return state["now"]
        return state,now

    def test_wait_empty_continuing_descendants_has_finite_deadline_and_refuses(self):
        self.store.kernel.members=(4321,)
        state,now=self.advancing_clock()
        with patch.object(jobs.time,"monotonic",now):
            with self.assertRaises(self.win32.Failure):jobs.wait_empty(self.store,10,2000)
        self.assertGreater(state["calls"],1); self.assertLess(state["calls"],10)
        self.assertEqual(self.store.kernel.members,(4321,))

    def test_wait_empty_actual_query_failure_or_incomplete_never_means_empty(self):
        for mode in ("query_failure_after_resume","query_incomplete_after_resume"):
            self.store=ModelStore(self.win32);self.store.kernel.mode=mode
            self.store.kernel.resumed=True;self.store.kernel.members=(4321,)
            state,now=self.advancing_clock()
            with patch.object(jobs.time,"monotonic",now):
                with self.subTest(mode=mode),self.assertRaises(self.win32.Failure):
                    jobs.wait_empty(self.store,10,2000)
            self.assertEqual(self.store.kernel.members,(4321,))
            self.assertLess(state["calls"],10)

    def test_run_fixed_persistent_descendant_query_unknown_never_reports_reaped(self):
        for mode in ("persistent_descendant","query_failure_after_resume","query_incomplete_after_resume"):
            self.store=ModelStore(self.win32);self.store.kernel.mode=mode
            state,now=self.advancing_clock()
            with patch.object(jobs.time,"monotonic",now):
                with self.subTest(mode=mode),self.assertRaises(self.win32.Failure):
                    jobs.run_fixed(self.store,"add")
            record=self.store.data["commands"][-1]
            self.assertFalse(record["reaped"])
            self.assertNotEqual(record["state"],"reaped")
            self.assertFalse(json.loads(self.store.durable)["commands"][-1]["reaped"])
            self.assertLess(state["calls"],40)
            self.assertEqual(set(self.store.kernel.closed),{10,20,21,30,31})

    def test_run_fixed_terminate_failure_or_reap_wait_timeout_never_succeeds(self):
        for mode in ("terminate_failure","reap_timeout"):
            self.store=ModelStore(self.win32);self.store.kernel.mode=mode
            state,now=self.advancing_clock()
            with patch.object(jobs.time,"monotonic",now):
                with self.subTest(mode=mode),self.assertRaises(self.win32.Failure):
                    jobs.run_fixed(self.store,"add")
            self.assertFalse(self.store.data["commands"][-1]["reaped"])
            self.assertFalse(json.loads(self.store.durable)["commands"][-1]["reaped"])
            self.assertIn("terminate",self.store.kernel.events)
            self.assertLess(state["calls"],40)


if __name__=="__main__":
    unittest.main()
```

持久 ready/resume_attempted=None 的崩溃恢复必须由真实 Native.reap_commands/has_add_attempt 原账本读取测试闭合；run_fixed 的同实例 finally 把 None 改 False 仅证明该实例知道没有到 Resume，不能用于已经崩溃的旧进程。独立recovery的完整TEST在 Native实际恢复算法可读后绑定，不用本层临时对象替代。

## Task 7：真实 Native facade / durable recovery 完整 TEST 资产

**Dependencies:** Task 1–6、主 PLAN Native 全文及固定入口共同冻结；当前继续审查，不授整体冻结。
**Parallelizable:** No（真实权限、账本、加载与恢复需要同一合同）。

本资产直接实例化真实 Native，运行真实 ledger/context/verify_store/request/full_get/_process/parent_only/reap_commands/has_add_attempt/_loader 算法。fixture 的进程、Job、字节存储与账号查询是明确的OS边界模型；低层ABI/Win32/Store/jobs由前六资产独立测试。不会 patch Native 类或把 policy State 送入权限入口。

- [ ] apply_patch 新增完整 `tests/test_windows_positive_loopback_admin_native.py`。
- [ ] 运行 `PYTHONPATH=src python -m unittest tests.test_windows_positive_loopback_admin_native -v`；缺新组件必须 Assertion RED。实施前整体TEST/SOURCE双审；当前只允许root明确授权的RAM诊断。

```python
"""Real Native algorithms; every OS object here is an explicit software model."""
from __future__ import annotations
import copy
import ctypes as c
from ctypes import wintypes as t
from dataclasses import asdict
import importlib
import json
from pathlib import Path
from types import SimpleNamespace as N
import unittest
from unittest.mock import patch
from tests.test_windows_positive_loopback_admin_binding import identity,manifest
from icode import windows_positive_loopback_policy as policy

NAME="scripts.windows_positive_loopback_admin_native"
try:
    native=importlib.import_module(NAME)
except ModuleNotFoundError as exc:
    if exc.name!=NAME:raise
    native=None


def put(pointer,kind,value):c.cast(pointer,c.POINTER(kind))[0]=value
def serialized(value):return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode("ascii")
def snapshot(entries):
    return dict(schema=1,entries=entries,api_code=0,complete=True,sid_attempted=len(entries),
        sid_freed=len(entries),array_freed=True,library_freed=True,process_reaped=True)


def image_bytes(matrix="x64",*,dll=False):
    raw=bytearray(256);raw[:2]=b"MZ";raw[60:64]=(64).to_bytes(4,"little")
    raw[64:68]=b"PE\0\0";raw[68:70]={"x64":0x8664,"ARM64":0xAA64}[matrix].to_bytes(2,"little")
    raw[86:88]=(0x2000 if dll else 0).to_bytes(2,"little")
    return bytes(raw)


class Boundary:
    def __init__(self,store):
        self.store=store;self.error=0;self.next=100;self.handles={};self.closed=[]
        self.processes={1234:dict(created=5678,alive=True,user=store.boot["account_sid"]),
                        2234:dict(created=6789,alive=True,user=store.boot["account_sid"])}
        self.jobs={store.data["outer_job"]:[1234]};self.k=self;self.a=self;self.u=self
        self.system_directory=Path("/windows/System32")
        self.security_changed=False
        self.mode="ok";self.impersonated=False;self.impersonation_events=[]
        self.buffers={};self.sid_buffers={};self.descriptor_frees=0;self.sid_frees=0
        self.version_changes={}
    def assert_admin(self):pass
    def info(self,handle,*,directory=False):return (7,1)
    def verify_security(self,handle,sddl,**options):
        if self.security_changed:raise native.Failure("modeled_security_changed")
    def _handle(self,kind,value):
        self.next+=1;self.handles[self.next]=(kind,value);return self.next
    def close(self,handle):
        handle=handle.value if hasattr(handle,"value") else handle
        if handle not in self.handles:raise AssertionError("unowned/double close")
        self.closed.append(self.handles.pop(handle))
    def LookupAccountNameW(self,system,name,sid,size,domain,domain_size,use):
        raw=policy.sid_bytes(self.store.boot["account_sid"])
        put(size,t.DWORD,len(raw));put(domain_size,t.DWORD,2);put(use,t.DWORD,1)
        if sid is None:self.error=122;return 0
        c.memmove(sid,raw,len(raw));domain.value="M";return 1
    def IsValidSid(self,sid):return 1
    def GetLengthSid(self,sid):
        address=sid.value if isinstance(sid,c.c_void_p) else c.cast(sid,c.c_void_p).value
        return self.sid_buffers[address][1] if address in self.sid_buffers else len(policy.sid_bytes(self.store.boot["account_sid"]))
    def OpenProcess(self,access,inherit,pid):
        if pid not in self.processes:self.error=87;return 0
        return self._handle("process",pid)
    def process_created(self,handle):return 5678 if handle==1 else self.processes[self.handles[handle][1]]["created"]
    def process_user(self,handle):return self.processes[self.handles[handle][1]]["user"]
    def WaitForSingleObject(self,handle,milliseconds):
        if handle==1:return 258
        return 258 if self.processes[self.handles[handle][1]]["alive"] else 0
    def OpenJobObjectW(self,access,inherit,name):
        if name not in self.jobs:self.error=2;return 0
        return self._handle("job",name)
    def job_pids(self,handle):return tuple(self.jobs[self.handles[handle][1]])
    def IsProcessInJob(self,process,job,inside):
        pid=self.handles[process][1];members=self.jobs[self.handles[job][1]]
        put(inside,t.BOOL,pid in members);return 1
    def TerminateJobObject(self,job,code):
        members=self.jobs[self.handles[job][1]]
        for pid in members:
            if pid in self.processes:self.processes[pid]["alive"]=False
        members.clear();return 1
    def pin_ancestor(self,path,*,observe_only=False):return self._handle("route",str(path))
    def observe_security(self,handle):
        return dict(owner_binary=policy.sid_bytes("S-1-5-18").hex(),dacl_binary="0200080000000000",protected=True)
    def effective_access(self,handle,parent):
        return dict(api_completed=True,access_status=True,granted=0,privilege_bytes=0)
    def CreateFileW(self,path,*args):
        mask=args[0]
        if self.impersonated:
            leaf=Path(path).name
            permitted=(leaf=="readonly-request.canary" and mask==2 and self.mode!="deny_request") or (
                leaf=="readonly-public.canary" and mask==0x80000000)
            if self.mode=="allow_private" and leaf=="readonly-private.canary" and mask==2:permitted=True
            if not permitted:self.error=32 if self.mode=="wrong_denial" else 5;return c.c_void_p(-1).value
        return self._handle("file",path)
    def read(self,handle,limit):
        path=self.handles[handle][1];value=self.store.files[Path(path).name]
        if len(value)>limit:raise native.Failure("modeled_read_limit")
        return value
    def open_file(self,path,descriptor,**options):
        handle=self._handle("file",str(path));return handle,self.info(handle)
    def write(self,handle,value):self.store.files[Path(self.handles[handle][1]).name]=value
    def create_directory(self,path,descriptor):pass
    def verify_ancestor(self,handle):pass
    def WriteFile(self,handle,data,size,count,overlap):
        path=self.handles[handle][1]
        value=data[:size] if type(data) is bytes else c.string_at(data,size)
        self.store.files[Path(path).name]=value;put(count,t.DWORD,len(value));return 1
    def OpenProcessToken(self,parent,access,output):put(output,t.HANDLE,self._handle("token",parent));return 1
    def DuplicateToken(self,token,level,output):put(output,t.HANDLE,self._handle("token",token.value));return 1
    def ImpersonateLoggedOnUser(self,token):self.impersonated=True;self.impersonation_events.append("enter");return 1
    def RevertToSelf(self):self.impersonated=False;self.impersonation_events.append("leave");return 1
    def SetFileAttributesW(self,path,value):
        if self.mode=="allow_attributes":return 1
        self.error=5;return 0
    def MoveFileExW(self,source,destination,flags):
        if self.mode=="allow_rename":
            self.store.files[Path(destination).name]=self.store.files.pop(Path(source).name);return 1
        self.error=5;return 0
    def GetCurrentProcess(self):return 1
    def descriptor(self,sddl):
        buffer=c.create_string_buffer(b"synthetic-descriptor");address=c.addressof(buffer)
        self.buffers[address]=buffer;return c.c_void_p(address)
    def LocalFree(self,pointer):
        address=pointer.value if hasattr(pointer,"value") else pointer
        if address not in self.buffers:raise AssertionError("wrong descriptor allocator or double free")
        del self.buffers[address];self.descriptor_frees+=1;return None
    def DeriveAppContainerSidFromAppContainerName(self,name,output):
        raw=policy.sid_bytes(self.store.boot["positive_sid"])
        buffer=c.create_string_buffer(raw);address=c.addressof(buffer)
        self.sid_buffers[address]=(buffer,len(raw));put(output,c.c_void_p,address);return 0
    def FreeSid(self,pointer):
        if pointer.value not in self.sid_buffers:raise AssertionError("wrong SID allocator or double free")
        del self.sid_buffers[pointer.value];self.sid_frees+=1;return None
    def GetFileInformationByHandle(self,handle,output):
        value=c.cast(output,c.POINTER(native.abi.FILE_INFO)).contents
        value.attributes=0;value.links=2;value.volume=7;value.index_high=0;value.index_low=1
        value.size_high=0;value.size_low=256;return 1
    def GetFinalPathNameByHandleW(self,handle,buffer,capacity,flags):
        buffer.value=self.handles[handle][1];return len(buffer.value)

    def library(self,path,**options):
        if Path(path).name!="version.dll":return N()
        if Path(path)!=self.system_directory/"version.dll" or options.get("winmode")!=0x800:
            raise AssertionError("nonfixed version library")
        class Function:
            def __init__(self,body):self.body=body
            def __call__(self,*args):return self.body(*args)
        def read_version(path,handle,size,buffer):
            words=[0xFEEF04BD,0x10000,10<<16,1<<16,10<<16,1<<16,0,0,0,
                   2 if Path(path).suffix.lower()==".dll" else 1,0,0,0]
            for index,value in self.version_changes.get(Path(path).name,{}).items():words[index]=value
            raw=b"".join(value.to_bytes(4,"little") for value in words)
            c.memmove(buffer,raw,len(raw));return 1
        def query(buffer,subkey,pointer,count):
            put(pointer,c.c_void_p,c.addressof(buffer));put(count,t.UINT,52);return 1
        return N(GetFileVersionInfoSizeW=Function(lambda *args:52),
                 GetFileVersionInfoW=Function(read_version),VerQueryValueW=Function(query))


class NativeStore:
    def __init__(self):
        self.boot=identity();b=self.boot
        ctx={key:b[key] for key in ("repository","source_sha","run_id","run_attempt","job","matrix")}
        import hashlib
        self.root=Path("/model/icode-positive-admin-"+hashlib.sha256(serialized(ctx)).hexdigest()[:32]);self.root_handle=1
        self.handles=[];self.pins=[];self.route_records=[];self.files={};self.fail_flush=False
        self.extra_files=[];self.extra_directories=[];self.existing_slots=set()
        self.closed=False
        reader=b"fixed-reader"
        frozen_reader=dict(path="trusted/scripts/windows_positive_loopback_full_get.py",identity=[7,1],
                           size=len(reader),sha256=hashlib.sha256(reader).hexdigest())
        self.files["windows_positive_loopback_full_get.py"]=reader
        self.tree_files=[frozen_reader["path"]];self.tree_directories=[".","runtime","trusted","trusted/scripts"]
        security=dict(owner_binary=policy.sid_bytes("S-1-5-18").hex(),dacl_binary="0200080000000000",protected=True)
        access=dict(api_completed=True,access_status=True,granted=0,privilege_bytes=0)
        route=dict(path="/",identity=[7,1],security=copy.deepcopy(security),effective=copy.deepcopy(access))
        image=dict(path="/windows/System32/CheckNetIsolation.exe",identity=[7,1],
            security=copy.deepcopy(security),effective=copy.deepcopy(access),
            file_info=dict(identity=[7,1],links=2,attributes=0,size=256),
            file_version=[10,0,1,0],product_version=[10,0,1,0])
        raw=image_bytes(ctx["matrix"])
        self.files["CheckNetIsolation.exe"]=raw
        image["provenance"]=dict(file_info=copy.deepcopy(image["file_info"]),
            sha256=hashlib.sha256(raw).hexdigest(),machine={"x64":0x8664,"ARM64":0xAA64}[ctx["matrix"]],
            file_version=list(image["file_version"]),product_version=list(image["product_version"]))
        self.data=dict(schema=1,context=ctx,account_name="icodeprobe_a",account_sid=b["account_sid"],
            session=b["session"],root_identity=[7,1],phase="bound",bootstrap=copy.deepcopy(b),
            operation_manifest=None,owned_intent=False,intent_ms=None,target_attributes=None,
            commands=[],observations={},reads=[],file_identities={},frozen_files=[frozen_reader],
            frozen_directories=[dict(path=name,identity=[7,1]) for name in self.tree_directories],
            system_tool=None,consumed={"profile_created":False,"probe_finished":False},
            parent=dict(pid=b["pid"],process_created=b["process_created"]),
            outer_job="Local\\ICODE.Positive."+b["session"]+".parent",first_error=None,
            cleanup_error=None,add_verified=False,delete_verified=False,others_preserved=False,
            exact_restoration=False,readonly_prepare=dict(schema=1,routes=[route],root_security=security,
                root_effective=access,sdk_layout_verified=True,python_binding_verified=True,
                loader_verified=True,canaries_verified=True,loader_images=[copy.deepcopy(image),
                    dict(path=str(self.root/frozen_reader["path"]),identity=list(frozen_reader["identity"]),
                         security=copy.deepcopy(security),effective=copy.deepcopy(access),file_info=None,provenance=None)],
                tool=[copy.deepcopy(image)],runner_arch_raw="X64"),operation_completed_ms=None,
            prepared_ms=b["prepared_ms"],profile_names=[b["positive_profile"],b["reviewer_profile"]],
            nonce=b["nonce"],ports=[b["ipv4_port"],b["ipv6_port"]])
        self.w=Boundary(self);self.flush()
    def flush(self):
        if self.fail_flush:raise native.Failure("modeled_flush")
        self.durable=serialized(self.data)
    def read(self,name,descriptor,limit):
        value=self.durable if name=="ledger.json" else self.files[name]
        if len(value)>limit:raise native.Failure("file_limit")
        return value
    def write(self,name,value,role="private",*,create=False):self.files[name]=value
    def file_descriptor(self,role):return native.Store.file_descriptor(self,role)
    def close(self):
        for collection in (self.handles,self.pins):
            while collection:self.w.close(collection.pop())
        self.closed=True


class TestAdminNative(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(native,"new Native component absent; expected facility RED")
        self.store=NativeStore();self.n=native.Native()
        b=self.store.boot
        self.env=dict(GITHUB_ACTIONS="true",RUNNER_ENVIRONMENT="github-hosted",RUNNER_OS="Windows",
            GITHUB_REPOSITORY=b["repository"],GITHUB_SHA=b["source_sha"],GITHUB_RUN_ID=b["run_id"],
            GITHUB_RUN_ATTEMPT=str(b["run_attempt"]),GITHUB_JOB=b["job"],RUNNER_ARCH="X64" if b["matrix"]=="x64" else "ARM64",
            GITHUB_REF="refs/heads/main",GITHUB_WORKFLOW_REF="ayukyo/icode/.github/workflows/ci.yml@refs/heads/main",
            GITHUB_WORKFLOW_SHA=b["source_sha"],ICODE_CI_POSITIVE_LOOPBACK_ADMIN="1",
            ICODE_CI_POSITIVE_LOOPBACK_DEDICATED_WRITER="1")
        self.patches=[patch.dict(native.os.environ,self.env,clear=True),
            patch.object(native.c,"WinDLL",lambda path,**options:self.store.w.library(path,**options),create=True),
            patch.object(native.c,"set_last_error",lambda value:setattr(self.store.w,"error",value),create=True),
            patch.object(native.c,"get_last_error",lambda:self.store.w.error,create=True),
            patch.object(native.time,"monotonic",lambda:180.999)]
        original_lstat,original_exists,original_glob,original_resolve=Path.lstat,Path.exists,Path.glob,Path.resolve
        root_prefix=str(self.store.root)
        def lstat(path,*args,**options):
            return N(st_file_attributes=0,st_size=0,st_mode=0) if str(path).startswith(root_prefix) else original_lstat(path,*args,**options)
        def exists(path):return str(path) in self.store.existing_slots if str(path).startswith(root_prefix) else original_exists(path)
        def glob(path,pattern):
            if str(path).startswith(root_prefix):return iter(Path(value) for value in self.store.existing_slots if Path(value).parent==path and value.endswith("._pth"))
            return original_glob(path,pattern)
        def resolve(path,*args,**options):
            return path if str(path).startswith((root_prefix,"/windows")) else original_resolve(path,*args,**options)
        def walk(path,*args,**options):
            base=Path(path).relative_to(self.store.root).as_posix()
            directories=self.store.tree_directories+self.store.extra_directories
            for value in directories:
                if value!=base and not value.startswith(base+"/"):continue
                current=self.store.root/value
                files=[Path(item).name for item in self.store.tree_files+self.store.extra_files if (self.store.root/item).parent==current]
                children=[Path(item).name for item in directories if (self.store.root/item).parent==current]
                yield str(current),children,files
        self.patches += [patch.object(Path,"lstat",lstat),patch.object(Path,"exists",exists),
                         patch.object(Path,"glob",glob),patch.object(Path,"resolve",resolve),patch.object(native.os,"walk",walk)]
        for item in self.patches:item.start();self.addCleanup(item.stop)

    def operation(self):
        self.store.data["consumed"]["profile_created"]=True
        base=snapshot([["S-1-15-2-99",0x80000004]])
        self.store.data["observations"]={"baseline_first":copy.deepcopy(base),"baseline":base}
        self.store.flush()
        return self.n.freeze_operation(self.store)

    def ledger(self,value):
        # Same explicit role context as each real Native entry point, not a
        # replacement parser or a permissive callback into production code.
        return native.ledger(value,private_root=self.store.root,system_directory=self.store.w.system_directory)

    def command_record(self,*,state="ready",pid=2234,attempted=None):
        return dict(kind="add",job="Local\\ICODE.Positive."+self.store.data["session"]+".command.0",
            output="command-0.out",state=state,pid=pid,process_created=6789 if pid else None,
            resume_permitted=pid is not None,resume_attempted=attempted,resume_returned=None,
            exit_code=None,timed_out=False,reaped=False)

    def ready(self,record=None):
        operation=self.operation()
        self.store.data.update(phase="add_intent",owned_intent=True,intent_ms=operation.started_ms)
        record=self.command_record() if record is None else record
        self.store.data["commands"]=[record];self.store.flush()
        self.store.w.jobs[record["job"]]=[2234]
        return record

    def test_context_exact_environment_and_schema_rejects_spoofed_inputs(self):
        self.assertEqual(native.context(self.store.data["context"]),self.store.data["context"])
        for key in self.env:
            with self.subTest(key=key),patch.dict(native.os.environ,{key:"wrong"}):
                with self.assertRaises(native.Failure):native.context(self.store.data["context"])
        for changed in (dict(self.store.data["context"],extra=1),
                        dict(self.store.data["context"],run_attempt=True)):
            with self.assertRaises(native.Failure):native.context(changed)

    def test_context_official_arch_mapping_and_cross_or_nonofficial_values_reject(self):
        for matrix,architecture in (("x64","X64"),("ARM64","ARM64")):
            value=dict(self.store.data["context"],matrix=matrix)
            with patch.dict(native.os.environ,{"RUNNER_ARCH":architecture}):
                self.assertEqual(native.context(value),value)
            for wrong in ({"X64","ARM64","x64","arm64","X86","ARM","unknown"}-{architecture}):
                with self.subTest(matrix=matrix,wrong=wrong),patch.dict(native.os.environ,{"RUNNER_ARCH":wrong}):
                    with self.assertRaises(native.Failure):native.context(value)

    def test_ledger_exact_top_level_and_critical_types(self):
        self.n.verify_store(self.store)
        for key in self.store.data:
            value=copy.deepcopy(self.store.data);del value[key]
            with self.subTest(key=key),self.assertRaises(native.Failure):self.ledger(value)
        for key,value in (("schema",True),("consumed",{"profile_created":1,"probe_finished":False}),
                          ("ports",[True,2]),("target_attributes",True),("owned_intent",1)):
            changed=copy.deepcopy(self.store.data);changed[key]=value
            with self.subTest(key=key),self.assertRaises(native.Failure):self.ledger(changed)

    def test_ledger_bootstrap_identity_cannot_disagree_with_owned_context(self):
        self.ledger(self.store.data)
        for key,value in (("source_sha","b"*40),("pid",4321),("nonce","8"*32),
                          ("ipv4_port",12346),("positive_profile","icode-"+"9"*32)):
            changed=copy.deepcopy(self.store.data);changed["bootstrap"][key]=value
            with self.subTest(key=key),self.assertRaises(native.Failure):self.ledger(changed)

    def test_verify_store_extra_files_directories_and_startup_slots_reject(self):
        self.n.verify_store(self.store)
        for relative in ("runtime/unlisted.pyd","trusted/unlisted.py"):
            self.store.extra_files=[relative]
            with self.subTest(relative=relative),self.assertRaises(native.Failure):self.n.verify_store(self.store)
        self.store.extra_files=[];self.store.extra_directories=["runtime/injected"]
        with self.assertRaises(native.Failure):self.n.verify_store(self.store)
        self.store.extra_directories=[]
        for relative in ("pyvenv.cfg","runtime/pyvenv.cfg","runtime/python312._pth","runtime/python3._pth","runtime/python312.zip"):
            self.store.existing_slots={str(self.store.root/relative)}
            with self.subTest(relative=relative),self.assertRaises(native.Failure):self.n.verify_store(self.store)
        self.store.existing_slots=set()

    def test_operation_uses_fresh_clock_and_can_only_freeze_once(self):
        result=self.operation()
        self.assertEqual((result.started_ms,result.deadline_ms),(180999,240999))
        self.assertEqual(self.store.data["operation_manifest"],asdict(result))
        with self.assertRaises(native.Failure):self.n.freeze_operation(self.store)

    def test_request_real_slot_bytes_are_consumed_durably_once(self):
        self.store.files[native.SLOTS["profile_created"]]=b"fixed request bytes"
        result=self.n.consume_request(self.store,"profile_created")
        self.assertEqual(result,b"fixed request bytes")
        self.assertTrue(json.loads(self.store.durable)["consumed"]["profile_created"])
        with self.assertRaises(native.Failure):self.n.consume_request(self.store,"profile_created")
        self.assertEqual(self.store.data["commands"],[])

    def test_consumption_failed_flush_does_not_return_request_or_start_command(self):
        self.store.files[native.SLOTS["profile_created"]]=b"fixed request bytes"
        self.store.fail_flush=True
        with self.assertRaises(native.Failure):self.n.consume_request(self.store,"profile_created")
        self.assertFalse(json.loads(self.store.durable)["consumed"]["profile_created"])
        self.assertEqual(self.store.data["commands"],[])

    def test_parent_only_checks_real_identity_membership_and_complete_pid_set(self):
        self.assertTrue(self.n.parent_only(self.store))
        name=self.store.data["outer_job"]
        self.store.w.jobs[name]=[1234,4321]
        self.assertFalse(self.n.parent_only(self.store))
        self.store.w.processes[1234]["created"]=9999
        with self.assertRaises(native.Failure):self.n.parent_only(self.store)
        self.assertEqual(self.store.w.handles,{})

    def test_durable_ready_unknown_resume_requires_actual_job_termination_and_exit(self):
        record=self.ready()
        self.assertIsNone(json.loads(self.store.durable)["commands"][0]["resume_attempted"])
        self.n.reap_commands(self.store)
        self.assertFalse(self.store.w.processes[2234]["alive"])
        self.assertEqual(self.store.w.jobs[record["job"]],[])
        self.assertTrue(self.n.has_add_attempt(self.store))
        self.assertEqual(self.store.w.handles,{})

    def test_missing_job_with_live_recorded_process_refuses_no_late_add_claim(self):
        record=self.ready();del self.store.w.jobs[record["job"]]
        with self.assertRaises(native.Failure):self.n.reap_commands(self.store)
        self.assertTrue(self.store.w.processes[2234]["alive"])
        self.assertEqual(self.store.w.handles,{})

    def test_missing_outer_job_rejection_releases_parent_handle(self):
        del self.store.w.jobs[self.store.data["outer_job"]]
        with self.assertRaises(native.Failure):self.n.verify_parent(self.store)
        self.assertEqual(self.store.w.handles,{})

    def test_stop_parent_missing_job_but_live_parent_refuses_and_closes_handle(self):
        del self.store.w.jobs[self.store.data["outer_job"]]
        with self.assertRaises(native.Failure):self.n.stop_parent_job(self.store)
        self.assertTrue(self.store.w.processes[1234]["alive"])
        self.assertEqual(self.store.w.handles,{})

    def test_allocated_without_identity_cannot_adopt_unknown_add_attempt(self):
        record=self.ready(self.command_record(state="allocated",pid=None,attempted=False))
        with self.assertRaises(native.Failure):self.n.reap_commands(self.store)
        self.assertEqual(self.store.w.jobs[record["job"]],[])
        self.assertFalse(self.n.has_add_attempt(self.store))

    def test_has_add_attempt_true_none_false_permitted_and_identity_are_distinct(self):
        for attempted,expected in ((True,True),(None,True),(False,False)):
            self.store=NativeStore();self.ready(self.command_record(attempted=attempted))
            self.assertEqual(self.n.has_add_attempt(self.store),expected)
        self.store=NativeStore();record=self.command_record();del record["resume_permitted"]
        self.ready(record)
        with self.assertRaises(native.Failure):self.n.has_add_attempt(self.store)
        for missing in ("pid","process_created"):
            self.store=NativeStore();record=self.command_record();record[missing]=None
            self.ready(record)
            with self.subTest(missing=missing),self.assertRaises(native.Failure):self.n.has_add_attempt(self.store)

    def test_real_admin_cleanup_with_known_no_resume_refuses_unexpected_target(self):
        record=self.command_record(state="reaped_after_failure",attempted=False);record["reaped"]=True
        self.ready(record)
        self.store.w.processes[2234]["alive"]=False;self.store.w.jobs[record["job"]]=[]
        calls=[]
        raw=snapshot([["S-1-15-2-99",0x80000004],[self.store.boot["positive_sid"],7]])
        raw["process_reaped"]=None
        def worker(store,kind):
            calls.append(kind)
            if kind!="get":raise AssertionError("known-not-resumed add never grants delete")
            number=len(store.data["commands"])
            result=self.command_record(state="reaped",attempted=True)
            result.update(kind="get",job="Local\\ICODE.Positive."+store.data["session"]+".command."+str(number),
                output="command-"+str(number)+".out",resume_returned=1,exit_code=0,reaped=True)
            store.files[result["output"]]=serialized(raw);store.data["commands"].append(result);store.flush()
            return copy.deepcopy(result)
        admin_module=importlib.import_module("scripts.windows_positive_loopback_admin")
        controller=admin_module.Admin.__new__(admin_module.Admin)
        controller.native=self.n;controller.store=self.store;controller.data=self.store.data
        with patch.object(native,"run_fixed",worker):
            with self.assertRaises(admin_module.AdminError):controller.cleanup(abnormal=False)
        self.assertEqual(calls,["get"])
        self.assertEqual(controller.data["first_error"],"owner_conflict")
        self.assertEqual(controller.data["observations"]["pre_delete"]["entries"][-1],
                         [self.store.boot["positive_sid"],7])

    def repeat_completed_cleanup(self, foreign_changed=False):
        operation=self.operation(); completed=operation.started_ms+1
        record=self.command_record(state="reaped",attempted=True)
        record.update(reaped=True,resume_returned=1,exit_code=0)
        self.store.data.update(phase="cleaned",owned_intent=True,intent_ms=operation.started_ms,
            add_verified=True,delete_verified=True,others_preserved=True,exact_restoration=True,
            operation_completed_ms=completed,target_attributes=7,commands=[record])
        base=copy.deepcopy(self.store.data["observations"]["baseline"])
        self.store.data["observations"].update(
            after_add=snapshot(base["entries"]+[[self.store.boot["positive_sid"],7]]),
            pre_delete=copy.deepcopy(base),post_delete=copy.deepcopy(base))
        self.store.w.processes[2234]["alive"]=False
        self.store.flush()
        # Validate a real producer-shaped success ledger before entering cleanup.
        self.n.verify_store(self.store)
        raw=snapshot([["S-1-15-2-99",0x80000005 if foreign_changed else 0x80000004]])
        raw["process_reaped"]=None; calls=[]
        def worker(store,kind):
            calls.append(kind)
            if kind!="get":raise AssertionError("completed cleanup must not issue another mutation")
            number=len(store.data["commands"])
            result=self.command_record(state="reaped",attempted=True)
            result.update(kind="get",job="Local\\ICODE.Positive."+store.data["session"]+".command."+str(number),
                output="command-"+str(number)+".out",resume_returned=1,exit_code=0,reaped=True)
            store.files[result["output"]]=serialized(raw);store.data["commands"].append(result);store.flush()
            return copy.deepcopy(result)
        module=importlib.import_module("scripts.windows_positive_loopback_admin")
        controller=module.Admin.__new__(module.Admin)
        controller.native=self.n;controller.store=self.store;controller.data=self.store.data
        with patch.object(native,"run_fixed",worker),patch.object(native.time,"monotonic",
                lambda:(operation.deadline_ms+1000)/1000):
            try:receipt=controller.cleanup(abnormal=True)
            except module.AdminError as exc:
                self.fail("independent always cleanup rejected valid completed ledger: "+str(exc))
        self.assertEqual(self.store.data["operation_completed_ms"],completed)
        self.assertEqual(self.store.data["operation_manifest"]["deadline_ms"],operation.deadline_ms)
        self.assertEqual(self.store.data["operation_manifest"]["started_ms"],operation.started_ms)
        self.assertTrue(calls);self.assertTrue(all(kind=="get" for kind in calls))
        self.n.verify_store(self.store)
        return receipt

    def test_real_completed_cleanup_independent_always_is_idempotent_after_deadline(self):
        receipt=self.repeat_completed_cleanup()
        self.assertTrue(receipt["native_restoration_verified"])
        self.assertEqual(self.store.data["phase"],"cleaned")
        self.assertIsNone(self.store.data["first_error"])
        self.assertIsNone(self.store.data["cleanup_error"])

    def test_real_completed_cleanup_foreign_change_never_reuses_exact_success(self):
        receipt=self.repeat_completed_cleanup(foreign_changed=True)
        self.assertFalse(receipt["native_restoration_verified"])
        self.assertFalse(self.store.data["exact_restoration"])
        self.assertEqual(self.store.data["first_error"],"foreign_delta")

    def test_real_first_cleanup_producer_then_independent_reopen_cleanup(self):
        operation=self.operation()
        record=self.command_record(state="reaped",attempted=True)
        record.update(reaped=True,resume_returned=1,exit_code=0)
        base=copy.deepcopy(self.store.data["observations"]["baseline"])
        self.store.data.update(phase="added",owned_intent=True,intent_ms=operation.started_ms,
            target_attributes=7,add_verified=True,commands=[record])
        self.store.data["observations"]["after_add"]=snapshot(base["entries"]+[[self.store.boot["positive_sid"],7]])
        self.store.w.processes[2234]["alive"]=False
        self.store.flush();self.n.verify_store(self.store)
        flush_records=[]
        def checked_flush():
            # Every production intermediate Flush must itself remain replayable.
            self.ledger(self.store.data)
            NativeStore.flush(self.store)
            self.ledger(native.decode(self.store.durable,8388608))
            flush_records.append(copy.deepcopy(self.store.data))
        self.store.flush=checked_flush
        calls=[]
        def worker(store,kind):
            calls.append(kind)
            if kind!="get":raise AssertionError("target already absent: no further mutation")
            index=len(store.data["commands"])
            result=self.command_record(state="reaped",attempted=True)
            result.update(kind="get",job="Local\\ICODE.Positive."+store.data["session"]+".command."+str(index),
                output="command-"+str(index)+".out",resume_returned=1,exit_code=0,reaped=True)
            raw=copy.deepcopy(base);raw["process_reaped"]=None
            store.files[result["output"]]=serialized(raw);store.data["commands"].append(result);store.flush()
            return copy.deepcopy(result)
        module=importlib.import_module("scripts.windows_positive_loopback_admin")
        def controller():
            result=module.Admin.__new__(module.Admin)
            result.native=self.n;result.store=self.store;result.data=self.store.data
            return result
        with patch.object(native,"run_fixed",worker):
            first=controller().cleanup(abnormal=False)
            self.assertTrue(first["native_restoration_verified"])
            completed=self.store.data["operation_completed_ms"]
            durable=self.store.durable;files=copy.deepcopy(self.store.files)
            processes=copy.deepcopy(self.store.w.processes);job_members=copy.deepcopy(self.store.w.jobs)
            # Independent object reopens persisted bytes, not the first controller state.
            reopened=NativeStore();reopened.data=native.decode(durable,8388608)
            reopened.durable=durable;reopened.files=files
            reopened.w.processes=processes;reopened.w.jobs=job_members
            self.store=reopened;self.n=native.Native();self.n.verify_store(self.store)
            self.store.flush=checked_flush
            with patch.object(native.time,"monotonic",lambda:(operation.deadline_ms+1000)/1000):
                try:second=controller().cleanup(abnormal=True)
                except module.AdminError as exc:self.fail("real first-cleanup ledger failed independent always: "+str(exc))
            self.assertTrue(second["native_restoration_verified"])
            self.assertEqual(self.store.data["operation_completed_ms"],completed)
            self.assertEqual(self.store.data["operation_manifest"]["deadline_ms"],operation.deadline_ms)
            self.n.verify_store(self.store)
            self.assertTrue(any(row["phase"]=="cleanup_intent" and not row["exact_restoration"]
                                and not row["delete_verified"] for row in flush_records))

    def test_ledger_intermediate_cleanup_flush_cannot_retain_completed_success_flags(self):
        self.repeat_completed_cleanup()
        valid=copy.deepcopy(self.store.data)
        changed=copy.deepcopy(valid);changed["phase"]="cleanup_intent"
        with self.assertRaises(native.Failure):self.ledger(changed)
        changed.update(exact_restoration=False,delete_verified=False,others_preserved=False)
        self.ledger(changed)
        for missing in ("readonly_prepare","parent","outer_job"):
            changed=copy.deepcopy(valid);changed[missing]=None
            with self.subTest(missing=missing),self.assertRaises(native.Failure):self.ledger(changed)

    def test_ledger_owned_baselines_cannot_precontain_positive_or_reviewer(self):
        self.ready();valid=copy.deepcopy(self.store.data)
        for key in ("positive_sid","reviewer_sid"):
            changed=copy.deepcopy(valid)
            for name in ("baseline_first","baseline"):
                changed["observations"][name]=snapshot([[self.store.boot[key],7]])
            with self.subTest(key=key),self.assertRaises(native.Failure):self.ledger(changed)

    def test_ledger_owned_baselines_must_agree_and_observations_bind_target_attributes(self):
        self.ready();valid=copy.deepcopy(self.store.data)
        changed=copy.deepcopy(valid)
        changed["observations"]["baseline_first"]=snapshot([["S-1-15-2-99",9]])
        with self.subTest(kind="baseline_delta"),self.assertRaises(native.Failure):self.ledger(changed)
        changed=copy.deepcopy(valid);changed.update(phase="added",add_verified=True,target_attributes=7)
        changed["observations"]["after_add"]=copy.deepcopy(changed["observations"]["baseline"])
        with self.subTest(kind="after_add_missing_target"),self.assertRaises(native.Failure):self.ledger(changed)

    def test_reused_pid_is_not_killed_but_owned_job_descendant_is_stopped(self):
        record=self.ready()
        self.store.w.processes[2234]["created"]=9999
        self.store.w.processes[4321]=dict(created=1111,alive=True,user=self.store.boot["account_sid"])
        self.store.w.jobs[record["job"]]=[4321]
        self.n.reap_commands(self.store)
        self.assertTrue(self.store.w.processes[2234]["alive"])
        self.assertFalse(self.store.w.processes[4321]["alive"])
        self.assertEqual(self.store.w.handles,{})

    def test_stale_memory_reaped_flag_never_overrides_persisted_ready_record(self):
        self.ready();self.store.data["commands"][0]["reaped"]=True
        with self.assertRaises(native.Failure):self.n.reap_commands(self.store)
        self.assertTrue(self.store.w.processes[2234]["alive"])

    def test_complete_get_worker_may_not_supply_its_own_reaped_credit(self):
        raw=snapshot([["S-1-15-2-99",7]]);raw["process_reaped"]=None
        def worker(store,kind):
            number=len(store.data["commands"])
            record=self.command_record(state="reaped",attempted=True)
            record.update(kind="get",job="Local\\ICODE.Positive."+store.data["session"]+".command."+str(number),
                output="command-"+str(number)+".out",resume_returned=1,exit_code=0,reaped=True)
            store.files[record["output"]]=serialized(raw)
            store.data["commands"].append(record);store.flush()
            return copy.deepcopy(record)
        with patch.object(native,"run_fixed",worker):
            observed=self.n.full_get(self.store)
        self.assertTrue(observed["process_reaped"])
        import hashlib
        read=self.store.data["reads"][0]
        self.assertEqual(set(read),{"started_ms","finished_ms","command_index","raw_sha256","reader_sha256"})
        self.assertEqual((read["started_ms"],read["finished_ms"],read["command_index"]),(180999,180999,0))
        self.assertEqual(read["raw_sha256"],hashlib.sha256(serialized(observed)).hexdigest())
        self.assertEqual(read["reader_sha256"],self.store.data["frozen_files"][0]["sha256"])
        raw["process_reaped"]=True
        with patch.object(native,"run_fixed",worker):
            with self.assertRaises(native.Failure):self.n.full_get(self.store)

    def test_get_unreaped_timed_out_or_nonzero_never_returns_complete_mapping(self):
        for changed in (dict(reaped=False,timed_out=False,exit_code=0),
                        dict(reaped=True,timed_out=True,exit_code=0),
                        dict(reaped=True,timed_out=False,exit_code=5)):
            with patch.object(native,"run_fixed",lambda store,kind:dict(changed,output="worker.out")):
                with self.subTest(changed=changed),self.assertRaises(native.Failure):self.n.full_get(self.store)

    def test_bootstrap_publication_uses_nested_identity_and_independent_digest(self):
        import hashlib
        self.n.publish_manifest(self.store)
        published=json.loads(self.store.files["bootstrap.json"])
        self.assertEqual(set(published),{"identity","binding"})
        self.assertEqual(published["identity"],self.store.boot)
        self.assertEqual(published["binding"],hashlib.sha256(serialized(self.store.boot)).hexdigest())

    def test_loader_real_algorithm_rejects_module_extension_and_dll_external_origins(self):
        extensions=("_ctypes","_socket","select","_hashlib","_ssl","unicodedata")
        modules={name:N(__file__=str(self.store.root/"runtime/DLLs"/(name+".pyd"))) for name in extensions}
        self.store.data["frozen_files"]=[dict(path="runtime/DLLs/"+name+".pyd") for name in extensions]
        self.store.data["frozen_files"] += [dict(path="runtime/"+name) for name in ("python312.dll","python3.dll")]
        dlls={name:str(self.store.root/"runtime"/name) if name.startswith("python") else
              str(self.store.w.system_directory/name) for name in
              ("python312.dll","python3.dll","advapi32.dll","userenv.dll","kernel32.dll","FirewallAPI.dll")}
        for name in dlls:
            if not name.startswith("python"):self.store.files[name]=image_bytes(dll=True)
        names=list(dlls)
        self.store.w.GetModuleHandleW=lambda name:names.index(name)+1
        def filename(handle,buffer,capacity):
            buffer.value=dlls[names[handle-1]];return len(buffer.value)
        self.store.w.GetModuleFileNameW=filename
        def enumerate_modules(current,output,capacity,returned):
            for index,name in enumerate(names):output[index]=index+1
            put(returned,t.DWORD,len(names)*c.sizeof(t.HANDLE));return 1
        self.store.w.K32EnumProcessModules=enumerate_modules
        with patch.object(native.sys,"executable",str(self.store.root/"runtime/python.exe")),patch.object(
            native.sys,"flags",N(isolated=1,no_site=1,dont_write_bytecode=1)),patch.object(
            native.sys,"modules",modules),patch.object(native.importlib,"import_module",lambda name:modules[name]),patch.object(
            Path,"resolve",lambda path,*args,**kwargs:path),patch.object(native.c,"WinDLL",self.store.w.library,create=True),patch.object(
            native.sys,"path",[str(self.store.root/name) for name in ("runtime/python312.zip","runtime/DLLs","runtime/Lib","runtime","trusted","trusted/src")]):
            self.n._loader(self.store,123)
            self.store.close();self.assertEqual(self.store.w.handles,{})
            for paths in (native.sys.path+["/external"],native.sys.path+native.sys.path[:1],
                          native.sys.path+[native.sys.path[0].upper()],native.sys.path[:-1]):
                with patch.object(native.sys,"path",paths):
                    with self.assertRaises(native.Failure):self.n._loader(self.store,123)
            modules["_ssl"].__file__="/external/ssl.pyd"
            with self.assertRaises(native.Failure):self.n._loader(self.store,123)
            modules["_ssl"].__file__=str(self.store.root/"runtime/DLLs/_ssl.pyd")
            dlls["python312.dll"]="/external/python312.dll"
            with self.assertRaises(native.Failure):self.n._loader(self.store,123)

    def test_loader_route_or_leaf_access_failure_closes_every_allocated_handle(self):
        extensions=("_ctypes","_socket","select","_hashlib","_ssl","unicodedata")
        for stage in ("route_api","route_rights","leaf_api","leaf_rights"):
            self.store=NativeStore()
            modules={name:N(__file__=str(self.store.root/"runtime/DLLs"/(name+".pyd"))) for name in extensions}
            self.store.data["frozen_files"]=[dict(path="runtime/DLLs/"+name+".pyd") for name in extensions]
            self.store.data["frozen_files"] += [dict(path="runtime/"+name) for name in ("python312.dll","python3.dll")]
            names=["python312.dll","python3.dll","advapi32.dll","userenv.dll","kernel32.dll","FirewallAPI.dll"]
            paths=[str(self.store.root/"runtime"/name) if name.startswith("python") else
                   str(self.store.w.system_directory/name) for name in names]
            self.store.w.GetModuleHandleW=lambda name:names.index(name)+1
            def filename(handle,buffer,capacity):buffer.value=paths[handle-1];return len(buffer.value)
            self.store.w.GetModuleFileNameW=filename
            def enum(current,output,capacity,returned):output[0]=1;put(returned,t.DWORD,c.sizeof(t.HANDLE));return 1
            self.store.w.K32EnumProcessModules=enum
            # The production low-level role is 'file'; map it to the requested
            # leaf fault without changing the actual allocation/close table.
            def effective(handle,parent):
                kind=self.store.w.handles[handle][0]
                match=(kind=="route" and stage.startswith("route")) or (kind=="file" and stage.startswith("leaf"))
                if match and stage.endswith("api"):raise native.Failure("modeled_access_api")
                return dict(api_completed=True,access_status=True,granted=0x100 if match else 0,privilege_bytes=0)
            self.store.w.effective_access=effective
            with patch.object(native.sys,"executable",str(self.store.root/"runtime/python.exe")),patch.object(
                native.sys,"flags",N(isolated=1,no_site=1,dont_write_bytecode=1)),patch.object(native.sys,"modules",modules),patch.object(
                native.importlib,"import_module",lambda name:modules[name]),patch.object(Path,"resolve",lambda path,*args,**kwargs:path),patch.object(
                native.c,"WinDLL",lambda *args,**options:N(),create=True),patch.object(native.sys,"path",[str(self.store.root/name) for name in (
                "runtime/python312.zip","runtime/DLLs","runtime/Lib","runtime","trusted","trusted/src")]):
                with self.subTest(stage=stage),self.assertRaises(native.Failure):self.n._loader(self.store,123)
            self.store.close()
            with self.subTest(stage=stage):self.assertEqual(self.store.w.handles,{})

    def test_real_canaries_standard_token_writes_only_request_and_reads_public(self):
        self.store.files.update({"readonly-request.canary":b"","readonly-public.canary":b"public",
                                 "readonly-private.canary":b"private"})
        self.n._canaries(self.store,123)
        self.assertEqual(self.store.files["readonly-request.canary"],b"ok")
        self.assertEqual(self.store.files["readonly-public.canary"],b"public")
        self.assertEqual(self.store.files["readonly-private.canary"],b"private")
        self.assertFalse(self.store.w.impersonated)
        self.assertEqual(self.store.w.impersonation_events,["enter","leave"])
        self.assertEqual(self.store.w.handles,{})

    def test_real_canary_negative_rights_wrong_error_and_rename_fail_closed(self):
        for mode in ("deny_request","allow_private","wrong_denial","allow_attributes","allow_rename"):
            self.store=NativeStore();self.store.w.mode=mode
            self.store.files.update({"readonly-request.canary":b"","readonly-public.canary":b"public",
                                     "readonly-private.canary":b"private"})
            with self.subTest(mode=mode),self.assertRaises(native.Failure):self.n._canaries(self.store,123)
            self.assertFalse(self.store.w.impersonated)
            self.assertEqual(self.store.w.impersonation_events,["enter","leave"])
            self.assertEqual(self.store.w.handles,{})

    def test_real_canary_token_cleanup_attempts_both_and_preserves_body_or_revert_error(self):
        for failed_token in (1,2):
            for body_mode in ("ok","write_error","revert_error","write_and_revert_error"):
                with self.subTest(failed_token=failed_token,body_mode=body_mode):
                    self.store=NativeStore();w=self.store.w;attempted=[];token_attempts=[]
                    body=native.Failure("modeled_canary_body")
                    self.store.files.update({"readonly-request.canary":b"","readonly-public.canary":b"public",
                                             "readonly-private.canary":b"private"})
                    def close_handle(resource):
                        handle=resource.value if hasattr(resource,"value") else resource
                        if handle not in w.handles:raise AssertionError("unowned/double close")
                        kind=w.handles[handle][0];attempted.append(handle)
                        if kind=="token":
                            token_attempts.append(handle)
                            if len(token_attempts)==failed_token:return 0
                        w.closed.append(w.handles.pop(handle));return 1
                    w.CloseHandle=close_handle
                    # Execute actual Win32.close too; inject failure only at CloseHandle.
                    w.close=native.abi.Win32.close.__get__(w,type(w))
                    if body_mode in ("write_error","write_and_revert_error"):
                        def write_error(*args):raise body
                        w.WriteFile=write_error
                    if body_mode in ("revert_error","write_and_revert_error"):
                        def revert_error():
                            w.impersonated=False;w.impersonation_events.append("leave")
                            raise body if body_mode=="revert_error" else native.Failure("modeled_revert_cleanup")
                        w.RevertToSelf=revert_error
                    with self.assertRaises(native.Failure) as caught:self.n._canaries(self.store,123)
                    self.assertEqual(len(token_attempts),2,"duplicate close failure must not skip original token")
                    self.assertEqual(len(w.handles),1)
                    self.assertEqual(next(iter(w.handles.values()))[0],"token")
                    self.assertFalse(w.impersonated)
                    if body_mode!="ok":self.assertIs(caught.exception,body)
                    self.assertTrue(any(note.startswith("cleanup_unknown:")
                                        for note in getattr(caught.exception,"__notes__",())))

    def test_recovery_work_budget_is_one_deadline_not_reset_per_command(self):
        clock={"now":180.999};budgets=[]
        self.n.recovery_deadline=185999
        def worker(store,kind,*,budget_ms):
            budgets.append(budget_ms);clock["now"]+=3;return {"modeled":True}
        with patch.object(native.time,"monotonic",lambda:clock["now"]),patch.object(native,"run_fixed",worker):
            self.n._run(self.store,"get")
            with self.assertRaises(native.Failure):self.n._run(self.store,"get")
            with self.assertRaises(native.Failure):self.n._run(self.store,"delete")
        self.assertEqual(budgets,[5000,2000])
        self.assertEqual(self.n.recovery_deadline,185999)

    def test_real_admin_recovery_deadline_starts_before_reopen_validation(self):
        clock={"now":180.999}
        admin_module=importlib.import_module("scripts.windows_positive_loopback_admin")
        def reopen_storage(root):
            self.assertEqual(root,self.store.root);clock["now"]+=31;return self.store
        with patch.object(native.time,"monotonic",lambda:clock["now"]),patch.object(native,"Store",reopen_storage):
            with self.assertRaises(native.Failure) as caught:admin_module.Admin.recover(self.store.root)
        self.assertEqual(caught.exception.args,("recovery_deadline",))
        self.assertTrue(self.store.closed)

    def source_tree(self,mode):
        source=Path("/source/Lib");self.store.files["sample.py"]=b"abc"
        state={"walks":0};original_read=self.store.w.read
        def walk(root,*args,**options):
            state["walks"]+=1
            if mode=="count":
                for index in range(10001):yield str(source/("directory-"+str(index))),[],[]
                return
            names=["sample.py"]
            if mode=="directory_drift" and state["walks"]>=3:names.append("added.py")
            yield str(source),[],names
            if mode=="enumeration_error":options["onerror"](OSError("modeled denied child"))
        def lstat(path,*args,**options):
            return N(st_size=3 if path.name=="sample.py" else 0,st_mode=0,
                     st_file_attributes=0x400 if mode=="reparse" and path==source else 0)
        def read(handle,limit):
            if mode=="file_drift" and state["walks"]>=3:return b"xyz"
            return original_read(handle,limit)
        with patch.object(native.os,"walk",walk),patch.object(Path,"lstat",lstat),patch.object(
            Path,"resolve",lambda path,*args,**options:path),patch.object(self.store.w,"read",read):
            return self.n._source_tree(self.store,source,"runtime/Lib",1000)

    def test_source_tree_double_enumeration_and_file_reread_preserve_full_copy(self):
        import hashlib
        records=self.source_tree("ok")
        self.assertEqual(len(records),1)
        self.assertEqual(records[0]["path"],"runtime/Lib/sample.py")
        self.assertEqual(records[0]["sha256"],hashlib.sha256(b"abc").hexdigest())
        self.assertEqual(self.store.w.handles,{})

    def test_native_copy_and_source_tree_owners_attempt_all_preserve_body(self):
        for owner in ("copy_file","source_tree"):
            for failed_index in ((0,1) if owner=="copy_file" else (0,1,3)):
                for body_failed in (False,True):
                    with self.subTest(owner=owner,failed_index=failed_index,body_failed=body_failed):
                        self.store=NativeStore();w=self.store.w;allocated=[];attempted=[];failed=[]
                        body=native.Failure("modeled_"+owner+"_body")
                        original_allocate=w._handle;original_close=w.close
                        def allocate(kind,value):
                            handle=original_allocate(kind,value)
                            if (owner=="copy_file" and kind=="file") or (owner=="source_tree" and kind=="route"):
                                allocated.append(handle)
                            return handle
                        def close(handle):
                            if handle in allocated:
                                attempted.append(handle)
                                if allocated.index(handle)==failed_index and not failed:
                                    failed.append(handle);raise native.Failure("modeled_owner_close")
                            return original_close(handle)
                        w._handle=allocate;w.close=close
                        if body_failed:
                            def write(*args):raise body
                            w.write=write
                        with self.assertRaises(native.Failure) as caught:
                            if owner=="source_tree":self.source_tree("ok")
                            else:
                                self.store.files["sample.py"]=b"abc"
                                with patch.object(Path,"lstat",lambda *a,**k:N(st_size=3,st_file_attributes=0,st_mode=0)),patch.object(
                                    Path,"stat",lambda *a,**k:N(st_size=3)),patch.object(Path,"resolve",lambda path,*a,**k:path):
                                    self.n._copy_file(self.store,Path("/source/sample.py"),"trusted/sample.py")
                        self.assertEqual(set(w.handles),set(failed),"each owned source/output/pin must be independently attempted")
                        self.assertEqual(len(attempted),len(set(attempted)))
                        if body_failed:self.assertIs(caught.exception,body)
                        self.assertTrue(any(n.startswith("cleanup_unknown:") for n in getattr(caught.exception,"__notes__",())))

    def test_native_process_job_owners_release_both_and_preserve_body(self):
        for owner in ("verify_parent","stop_parent_job","reap_commands"):
            for failed_kind in ("job","process"):
                for body_failed in (False,True):
                    with self.subTest(owner=owner,failed_kind=failed_kind,body_failed=body_failed):
                        self.store=NativeStore();w=self.store.w
                        if owner=="reap_commands":self.ready()
                        acquired=[];attempted=[];failed=[];body=native.Failure("modeled_"+owner+"_body")
                        original_allocate=w._handle;original_close=w.close
                        def allocate(kind,value):
                            handle=original_allocate(kind,value)
                            if kind in ("job","process"):acquired.append(handle)
                            return handle
                        def close(handle):
                            if handle in acquired:
                                attempted.append(handle)
                                if w.handles[handle][0]==failed_kind and not failed:
                                    failed.append(handle);raise native.Failure("modeled_pair_close")
                            return original_close(handle)
                        w._handle=allocate;w.close=close
                        if body_failed:
                            def fault(*args):raise body
                            if owner=="verify_parent":w.IsProcessInJob=fault
                            else:w.TerminateJobObject=fault
                        clock=[180.999]
                        def now():clock[0]+=0.01;return clock[0]
                        with patch.object(native.time,"monotonic",now),self.assertRaises(native.Failure) as caught:
                            getattr(self.n,owner)(self.store)
                        self.assertTrue(acquired)
                        self.assertEqual(set(attempted),set(acquired),"job close failure must not skip held parent/process")
                        self.assertEqual(set(w.handles),set(failed))
                        if body_failed:self.assertIs(caught.exception,body)
                        self.assertTrue(any(n.startswith("cleanup_unknown:") for n in getattr(caught.exception,"__notes__",())))

    def test_attach_parent_failure_still_reaps_and_closes_each_acquired_resource(self):
        for cleanup in ("process_close","job_close","terminate","wait"):
            with self.subTest(cleanup=cleanup):
                self.store=NativeStore();w=self.store.w
                self.store.data.update(phase="prepared",bootstrap=None,parent=None,outer_job=None,readonly_prepare=None)
                self.store.flush();body=native.Failure("modeled_attach_body")
                acquired=[];attempted=[];cleanup_events=[];original_allocate=w._handle;original_close=w.close
                def allocate(kind,value):
                    handle=original_allocate(kind,value)
                    if kind in ("job","process"):acquired.append(handle)
                    return handle
                def job(security,name):w.jobs[name]=[];return w._handle("job",name)
                def assign(*args):raise body
                original_terminate=w.TerminateJobObject
                def terminate(job,code):
                    cleanup_events.append("terminate")
                    if cleanup=="terminate":raise native.Failure("modeled_terminate_cleanup")
                    return original_terminate(job,code)
                def terminate_process(handle,code):
                    cleanup_events.append("terminate")
                    if cleanup=="terminate":raise native.Failure("modeled_terminate_cleanup")
                    w.processes[w.handles[handle][1]]["alive"]=False;return 1
                original_wait=w.WaitForSingleObject
                def wait(handle,milliseconds):
                    if milliseconds==2000:
                        cleanup_events.append("wait")
                        if cleanup=="wait":raise native.Failure("modeled_wait_cleanup")
                    return original_wait(handle,milliseconds)
                def close(handle):
                    if handle in acquired:
                        attempted.append(handle)
                        kind=w.handles[handle][0]
                        if cleanup==kind+"_close":raise native.Failure("modeled_attach_close")
                    return original_close(handle)
                w._handle=allocate;w.close=close;w.CreateJobObjectW=job
                w.SetInformationJobObject=lambda *args:1;w.AssignProcessToJobObject=assign
                w.TerminateJobObject=terminate;w.TerminateProcess=terminate_process;w.WaitForSingleObject=wait
                with self.assertRaises(native.Failure) as caught:self.n.attach_parent(self.store,1234)
                self.assertEqual(set(attempted),set(acquired),"failed termination/wait/first close cannot strand other owned handles")
                self.assertIn("terminate",cleanup_events)
                self.assertIs(caught.exception,body)
                self.assertTrue(any(n.startswith("cleanup_unknown:") for n in getattr(body,"__notes__",())))

    def attach_case(self,stage,*,failures=()):
        self.store=NativeStore();w=self.store.w
        self.store.data.update(phase="prepared",bootstrap=None,parent=None,outer_job=None,readonly_prepare=None)
        self.store.flush();w.jobs={}
        w.processes[4321]=dict(created=9876,alive=True,user=self.store.boot["account_sid"])
        w.processes[9999]=dict(created=1111,alive=True,user="S-1-5-21-1-2-3-9999")
        state=dict(events=[],acquired=[],body=native.Failure("modeled_attach_"+stage))
        original_allocate=w._handle;original_close=w.close;original_wait=w.WaitForSingleObject
        original_terminate=w.TerminateJobObject;original_user=w.process_user;original_created=w.process_created
        original_inside=w.IsProcessInJob;inside_calls=[0]
        def allocate(kind,value):
            handle=original_allocate(kind,value)
            if kind in ("process","job"):state["acquired"].append(handle)
            return handle
        def job(security,name):w.jobs[name]=[];return w._handle("job",name)
        def assign(job,process):
            state["events"].append("assign")
            if stage in ("unassigned","assign_exited"):
                if stage=="assign_exited":w.processes[w.handles[process][1]]["alive"]=False
                raise state["body"]
            members=(w.handles[process][1],) if stage=="transferred" else (w.handles[process][1],4321)
            w.jobs[w.handles[job][1]].extend(members);return 1
        def inside(*args):
            inside_calls[0]+=1
            if stage=="assigned" and inside_calls[0]==1:raise state["body"]
            return original_inside(*args)
        def terminate_job(job,code):
            state["events"].append("terminate_job")
            if "terminate_job" in failures:raise native.Failure("modeled_job_terminate_cleanup")
            return original_terminate(job,code)
        def terminate_process(process,code):
            state["events"].append("terminate_process")
            if "terminate_process" in failures:raise native.Failure("modeled_process_terminate_cleanup")
            w.processes[w.handles[process][1]]["alive"]=False;return 1
        def wait(handle,milliseconds):
            if milliseconds==0 and stage=="wait":return 0xffffffff
            if milliseconds==2000:
                state["events"].append("wait")
                if "wait" in failures:raise native.Failure("modeled_attach_wait_cleanup")
            return original_wait(handle,milliseconds)
        def user(handle):
            if stage=="token":raise state["body"]
            return original_user(handle)
        def created(handle):
            if stage=="creation":raise state["body"]
            if stage=="creation_zero":return 0
            if stage=="creation_bool":return True
            if stage=="creation_overflow":return 1<<64
            return original_created(handle)
        def close(handle):
            handle=handle.value if hasattr(handle,"value") else handle
            if handle in state["acquired"]:
                kind=w.handles[handle][0];state["events"].append("close_"+kind)
                if "close_"+kind in failures:raise native.Failure("modeled_attach_"+kind+"_close")
            return original_close(handle)
        if stage=="sid":w.processes[1234]["user"]="S-1-5-21-1-2-3-9999"
        if stage=="exited":w.processes[1234]["alive"]=False
        w._handle=allocate;w.close=close;w.CreateJobObjectW=job
        w.SetInformationJobObject=lambda *args:1;w.AssignProcessToJobObject=assign
        w.IsProcessInJob=inside;w.TerminateJobObject=terminate_job;w.TerminateProcess=terminate_process
        w.WaitForSingleObject=wait;w.process_user=user;w.process_created=created
        if stage=="transferred":
            def readonly_failure(*args):raise state["body"]
            self.n.readonly_prepare=readonly_failure
        with self.assertRaises(native.Failure) as caught:self.n.attach_parent(self.store,1234)
        state["error"]=caught.exception
        return state

    def test_attach_unverified_identity_is_closed_but_never_terminated(self):
        for stage in ("sid","token","wait","exited","creation",
                      "creation_zero","creation_bool","creation_overflow"):
            with self.subTest(stage=stage):
                state=self.attach_case(stage)
                self.assertEqual(self.store.w.handles,{})
                self.assertFalse(any(event.startswith("terminate_") for event in state["events"]),
                                 "held handle does not authorize killing an unverified PID")
                self.assertEqual(self.store.w.processes[1234]["alive"],stage!="exited")
                self.assertTrue(self.store.w.processes[9999]["alive"])
                if stage in ("token","creation"):self.assertIs(state["error"],state["body"])
                elif not stage.startswith("creation_"):self.assertEqual(state["error"].args,("parent_identity",))

    def test_attach_authenticated_but_unassigned_parent_is_directly_reaped(self):
        state=self.attach_case("unassigned")
        self.assertEqual(self.store.w.handles,{})
        self.assertIs(state["error"],state["body"])
        self.assertFalse(self.store.w.processes[1234]["alive"],"empty Job termination cannot reap an unassigned parent")
        self.assertIn("terminate_process",state["events"])
        self.assertIn("wait",state["events"])
        self.assertTrue(self.store.w.processes[4321]["alive"])
        self.assertTrue(self.store.w.processes[9999]["alive"])

    def test_attach_assigned_parent_is_reaped_through_actual_job_members_only(self):
        state=self.attach_case("assigned")
        self.assertIs(state["error"],state["body"])
        self.assertFalse(self.store.w.processes[1234]["alive"])
        self.assertFalse(self.store.w.processes[4321]["alive"])
        self.assertTrue(self.store.w.processes[9999]["alive"])
        self.assertTrue(all(not members for members in self.store.w.jobs.values()))
        self.assertIn("terminate_job",state["events"])
        self.assertNotIn("terminate_process",state["events"])
        self.assertEqual(self.store.w.handles,{})

    def test_attach_assign_failure_already_exited_needs_no_blind_termination(self):
        state=self.attach_case("assign_exited")
        self.assertIs(state["error"],state["body"])
        self.assertFalse(self.store.w.processes[1234]["alive"])
        self.assertFalse(any(event.startswith("terminate_") for event in state["events"]),
                         "held-handle signaled exit needs no speculative termination")
        self.assertTrue(self.store.w.processes[4321]["alive"])
        self.assertTrue(self.store.w.processes[9999]["alive"])
        self.assertEqual(self.store.w.handles,{})

    def test_attach_unassigned_multiple_cleanup_failures_attempt_all_keep_body(self):
        state=self.attach_case("unassigned",failures=("terminate_process","wait","close_process","close_job"))
        self.assertIs(state["error"],state["body"])
        self.assertTrue(self.store.w.processes[1234]["alive"],"failed termination must remain unknown, not reaped")
        for event in ("terminate_process","wait","close_process","close_job"):
            self.assertIn(event,state["events"],"one cleanup failure must not skip an independent attempt")
        self.assertEqual(len(self.store.w.handles),2)
        self.assertTrue(any(note.startswith("cleanup_unknown:") for note in getattr(state["error"],"__notes__",())))

    def test_attach_post_transfer_failure_leaves_reclamation_to_store_owner(self):
        state=self.attach_case("transferred")
        self.assertIs(state["error"],state["body"])
        self.assertTrue(self.store.w.processes[1234]["alive"])
        self.assertFalse(any(event.startswith("terminate_") for event in state["events"]))
        self.assertEqual(set(self.store.w.handles),set(state["acquired"]))
        self.assertEqual(set(self.store.handles),set(state["acquired"]))
        self.store.close()
        self.assertEqual(self.store.w.handles,{})

    def test_native_single_handle_owners_preserve_body_on_release_failure(self):
        for owner in ("_process","_outer","parent_only","readonly_prepare","_tool",
                      "verify_store_directory","verify_store_file","verify_store_image","_derived"):
            with self.subTest(owner=owner):
                self.store=NativeStore();w=self.store.w;body=native.Failure("modeled_"+owner+"_body")
                active=[False];attempted=[];original_close=w.close
                def fault(*args,**options):active[0]=True;raise body
                def close(handle):
                    if active[0]:attempted.append(handle);raise native.Failure("modeled_single_close")
                    return original_close(handle)
                w.close=close
                if owner=="_process":w.process_created=fault
                elif owner=="_outer":w.verify_security=fault
                elif owner=="parent_only":
                    original_query=w.job_pids;queries=[0]
                    def query(handle):
                        queries[0]+=1
                        if queries[0]==2:return fault()
                        return original_query(handle)
                    w.job_pids=query
                elif owner=="readonly_prepare":
                    self.store.data["readonly_prepare"]=None;w.observe_security=fault
                elif owner=="_tool":w.read=fault
                elif owner=="_derived":
                    w.IsValidSid=fault
                    def free(pointer):attempted.append(pointer.value);raise native.Failure("modeled_sid_free")
                    w.FreeSid=free
                else:
                    original_info=w.info;original_read=w.read
                    def info(handle,**options):
                        if owner=="verify_store_directory" and handle in w.handles and w.handles[handle][0]=="route":return fault()
                        return original_info(handle,**options)
                    def read(handle,size):
                        if handle in w.handles:
                            path=Path(w.handles[handle][1])
                            if ((owner=="verify_store_file" and path.name=="windows_positive_loopback_full_get.py") or
                                (owner=="verify_store_image" and path.name=="CheckNetIsolation.exe")):return fault()
                        return original_read(handle,size)
                    w.info=info;w.read=read
                with self.assertRaises(native.Failure) as caught:
                    if owner=="_process":self.n._process(self.store,self.store.data["parent"])
                    elif owner=="_outer":self.n._outer(self.store)
                    elif owner=="_derived":self.n._derived(w,self.store.data["profile_names"][0])
                    elif owner.startswith("verify_store"):self.n.verify_store(self.store)
                    else:getattr(self.n,owner)(self.store)
                self.assertTrue(active[0],"case must enter intended owner's actual body")
                self.assertTrue(attempted)
                self.assertIs(caught.exception,body)
                self.assertTrue(any(n.startswith("cleanup_unknown:") for n in getattr(body,"__notes__",())))

    def test_source_tree_pin_is_owned_before_identity_query_can_fail(self):
        w=self.store.w;body=native.Failure("modeled_pin_info_body");attempted=[]
        original_info=w.info;original_close=w.close
        def info(handle,**options):
            if handle in w.handles and w.handles[handle][0]=="route":raise body
            return original_info(handle,**options)
        def close(handle):attempted.append(handle);return original_close(handle)
        with patch.object(w,"info",info),patch.object(w,"close",close):
            with self.assertRaises(native.Failure) as caught:self.source_tree("ok")
        self.assertTrue(attempted,"pin acquired before info must be registered for cleanup")
        self.assertEqual(w.handles,{})
        self.assertIs(caught.exception,body)

    def test_canary_request_and_public_file_close_failures_preserve_original_body(self):
        for stage in ("request","public"):
            with self.subTest(stage=stage):
                self.store=NativeStore();w=self.store.w;body=native.Failure("modeled_canary_file_body")
                self.store.files.update({"readonly-request.canary":b"","readonly-public.canary":b"public",
                                         "readonly-private.canary":b"private"})
                original_close=w.close;attempted=[]
                def close(handle):
                    handle=handle.value if hasattr(handle,"value") else handle
                    attempted.append(w.handles[handle][0])
                    kind,value=w.handles[handle]
                    if kind=="file" and Path(value).name=="readonly-"+stage+".canary":
                        raise native.Failure("modeled_canary_file_close")
                    return original_close(handle)
                w.close=close
                if stage=="request":
                    def write(*args):raise body
                    w.WriteFile=write
                else:
                    def read(*args):raise body
                    w.read=read
                with self.assertRaises(native.Failure) as caught:self.n._canaries(self.store,123)
                self.assertEqual(attempted.count("token"),2)
                self.assertIs(caught.exception,body)
                self.assertTrue(any(n.startswith("cleanup_unknown:") for n in getattr(body,"__notes__",())))

    def test_native_lifecycle_store_close_does_not_replace_freeze_reopen_prepare_body(self):
        for owner in ("freeze","reopen","prepare"):
            with self.subTest(owner=owner):
                self.store=NativeStore();w=self.store.w;body=native.Failure("modeled_"+owner+"_body")
                closed=[];body_entered=[]
                def close():closed.append(True);raise native.Failure("modeled_lifecycle_close")
                self.store.close=close
                def fault(*args,**options):body_entered.append(True);raise body
                patches=[patch.object(native,"Store",lambda root:self.store)]
                if owner=="reopen":w.assert_admin=fault
                elif owner=="prepare":
                    self.store.data.update(phase="frozen",account_sid=None,bootstrap=None,parent=None,outer_job=None,readonly_prepare=None)
                    self.store.flush();w.LookupAccountNameW=fault
                else:
                    # Only OS/storage/runtime boundaries are modeled; Native.freeze
                    # and its actual trusted-context/account/path gates still run.
                    checkout=Path(policy.__file__).resolve(strict=True).parents[2]
                    patches=[patch.object(native,"Win32",lambda:w),
                        patch.object(native,"__file__",str(checkout/"scripts/preflight.py")),
                        patch.dict(native.os.environ,{"GITHUB_WORKSPACE":str(checkout)}),
                        patch.object(native.sys,"base_prefix","/model/runtime"),
                        patch.object(native.sys,"executable","/model/runtime/python.exe")]
                    def lookup(system,name,sid,size,domain,domain_size,use):w.error=1332;return 0
                    w.LookupAccountNameW=lookup
                    def temporary(capacity,buffer):buffer.value="/tmp";return len(buffer.value)
                    w.GetTempPathW=temporary
                    self.store.create_directory=fault
                    factory=N(create=lambda root,data:self.store)
                    patches.append(patch.object(native,"Store",factory))
                for item in patches:item.start()
                try:
                    with self.assertRaises(native.Failure) as caught:
                        if owner=="freeze":self.n.freeze(self.store.data["context"],self.store.data["account_name"])
                        elif owner=="prepare":self.n.prepare(self.store.root,self.store.boot["account_sid"])
                        else:self.n.reopen(self.store.root)
                finally:
                    for item in reversed(patches):item.stop()
                self.assertTrue(closed)
                self.assertTrue(body_entered,"case must actually raise intended lifecycle body before cleanup")
                self.assertIs(caught.exception,body)
                self.assertTrue(any(n.startswith("cleanup_unknown:") for n in getattr(body,"__notes__",())))

    def test_prepare_root_and_socket_cleanup_keep_original_body_and_close_store(self):
        for stage in ("root_dacl","socket_bind"):
            with self.subTest(stage=stage):
                self.store=NativeStore();w=self.store.w;body=native.Failure("modeled_prepare_"+stage)
                self.store.data.update(phase="frozen",account_sid=None,bootstrap=None,parent=None,outer_job=None,readonly_prepare=None)
                self.store.flush();attempted=[];original_close=w.close;active=[False]
                def store_close():attempted.append("store");raise native.Failure("modeled_prepare_store_close")
                self.store.close=store_close
                def dacl(*args):
                    if stage=="root_dacl":active[0]=True;raise body
                w.set_root_dacl=dacl
                def close(handle):
                    attempted.append("root")
                    if stage=="root_dacl" and active[0]:raise native.Failure("modeled_root_close")
                    return original_close(handle)
                w.close=close
                class Socket:
                    def __enter__(self):return self
                    def __exit__(self,*args):self.close()
                    def setsockopt(self,*args):pass
                    def bind(self,*args):raise body
                    def close(self):attempted.append("socket");raise native.Failure("modeled_socket_close")
                with patch.object(native,"Store",lambda root:self.store),patch.object(native.socket,"socket",lambda *a:Socket()),patch.object(
                    native.socket,"SO_EXCLUSIVEADDRUSE",-5,create=True):
                    with self.assertRaises(native.Failure) as caught:self.n.prepare(self.store.root,self.store.boot["account_sid"])
                self.assertIn("store",attempted)
                self.assertIn("root" if stage=="root_dacl" else "socket",attempted)
                self.assertIs(caught.exception,body)
                self.assertTrue(any(n.startswith("cleanup_unknown:") for n in getattr(body,"__notes__",())))

    def test_source_tree_enumeration_reparse_membership_file_drift_count_reject_and_close(self):
        for mode in ("enumeration_error","reparse","directory_drift","file_drift","count"):
            self.store=NativeStore()
            with self.subTest(mode=mode),self.assertRaises(native.Failure):self.source_tree(mode)
            with self.subTest(mode=mode):self.assertEqual(self.store.w.handles,{})

    def test_system_image_hardlinks_are_role_scoped_and_bad_shape_rejected(self):
        path=self.store.w.system_directory/"CheckNetIsolation.exe"
        info=self.n._image_info(self.store,99,path)
        self.assertEqual(info,dict(identity=[7,1],links=2,attributes=0,size=256))
        with self.assertRaises(native.Failure):self.n._image_info(self.store,99,self.store.root/"private.exe")
        for attributes,links,index in ((0x400,2,1),(0x10,2,1),(0,0,1),(0,2,0)):
            def query(handle,output):
                value=c.cast(output,c.POINTER(native.abi.FILE_INFO)).contents
                value.attributes=attributes;value.links=links;value.volume=7;value.index_low=index;return 1
            with patch.object(self.store.w,"GetFileInformationByHandle",query):
                with self.subTest(attributes=attributes,links=links,index=index),self.assertRaises(native.Failure):
                    self.n._image_info(self.store,99,path)

    def tool(self,mode):
        import struct
        raw=bytearray(256);raw[:2]=b"MZ";raw[60:64]=(64).to_bytes(4,"little")
        raw[64:68]=b"PE\0\0";raw[68:70]=(0xAA64 if mode=="wrong_arch" else 0x8664).to_bytes(2,"little")
        self.store.files["CheckNetIsolation.exe"]=bytes(raw)
        words=[0xFEEF04BD,0x10000,10<<16,(1<<16)|2,10<<16,(1<<16)|3,0,0,0,1,0,0,0]
        if mode=="bad_magic":words[0]=0
        if mode=="bad_type":words[9]=2
        class Function:
            def __init__(self,body):self.body=body
            def __call__(self,*args):return self.body(*args)
        def read_version(path,handle,size,buffer):c.memmove(buffer,struct.pack("<13I",*words),52);return 1
        def query(buffer,subkey,pointer,count):
            put(pointer,c.c_void_p,c.addressof(buffer)+(52 if mode=="version_pointer" else 0))
            put(count,t.UINT,52);return 1
        version=N(GetFileVersionInfoSizeW=Function(lambda *args:51 if mode=="version_size" else 52),
                  GetFileVersionInfoW=Function(read_version),VerQueryValueW=Function(query))
        def dll(path,**options):
            self.assertEqual((path,options.get("winmode")),(str(self.store.w.system_directory/"version.dll"),0x800))
            return version
        with patch.object(native.c,"WinDLL",dll,create=True):return self.n._tool(self.store)

    def test_tool_reads_actual_pe_version_buffer_and_pins_exact_system_image(self):
        record=self.tool("ok")
        self.assertEqual(record["file_version"],[10,0,1,2])
        self.assertEqual(record["product_version"],[10,0,1,3])
        self.assertEqual(record["file_info"]["links"],2)
        self.assertEqual(record["machine"],0x8664)
        self.assertEqual(record["path"],str(self.store.w.system_directory/"CheckNetIsolation.exe"))
        self.assertEqual(len(self.store.handles),1)
        self.store.close();self.assertEqual(self.store.w.handles,{})

    def test_shared_dll_real_proof_and_durable_image_hash_version_drift_reject(self):
        path=self.store.w.system_directory/"kernel32.dll"
        self.store.files[path.name]=image_bytes(dll=True)
        handle=self.store.w.CreateFileW(str(path),0x80020080)
        try:
            proof=self.n._image_provenance(self.store,handle,path,dll=True)
            self.assertEqual(proof["file_info"]["size"],len(self.store.files[path.name]))
            self.assertEqual(proof["machine"],0x8664)
            for mode in ("not_dll","unknown_machine","wrong_version_type","bad_magic"):
                self.store.files[path.name]=image_bytes(dll=mode!="not_dll")
                self.store.w.version_changes={}
                if mode=="unknown_machine":
                    raw=bytearray(self.store.files[path.name]);raw[68:70]=(0xffff).to_bytes(2,"little")
                    self.store.files[path.name]=bytes(raw)
                elif mode=="wrong_version_type":self.store.w.version_changes[path.name]={9:1}
                elif mode=="bad_magic":self.store.files[path.name]=b"NO"+self.store.files[path.name][2:]
                with self.subTest(mode=mode),self.assertRaises(native.Failure):
                    self.n._image_provenance(self.store,handle,path,dll=True)
        finally:self.store.w.close(handle)
        self.store.w.version_changes={}
        self.n.verify_store(self.store)
        original=self.store.files["CheckNetIsolation.exe"]
        self.store.files["CheckNetIsolation.exe"]=original[:-1]+b"x"
        with self.assertRaises(native.Failure):self.n.verify_store(self.store)
        self.store.files["CheckNetIsolation.exe"]=original
        self.store.w.version_changes["CheckNetIsolation.exe"]={3:2<<16}
        with self.assertRaises(native.Failure):self.n.verify_store(self.store)
        self.store.w.version_changes={}
        self.n.verify_store(self.store)
        self.assertEqual(self.store.w.handles,{})

    def test_system32_singlelink_image_cannot_downgrade_to_private_nullable_proof(self):
        path=self.store.w.system_directory/"kernel32.dll"
        self.store.files[path.name]=image_bytes(dll=True)
        original_query=self.store.w.GetFileInformationByHandle
        def singlelink(handle,output):
            result=original_query(handle,output)
            if self.store.w.handles.get(handle)==("file",str(path)):
                c.cast(output,c.POINTER(native.abi.FILE_INFO)).contents.links=1
            return result
        with patch.object(self.store.w,"GetFileInformationByHandle",singlelink):
            handle=self.store.w.CreateFileW(str(path),0x80020080)
            try:proof=self.n._image_provenance(self.store,handle,path,dll=True)
            finally:self.store.w.close(handle)
            row=dict(path=str(path),identity=proof["file_info"]["identity"],
                security=self.store.w.observe_security(1),effective=self.store.w.effective_access(1,123),
                file_info=proof["file_info"],provenance=proof)
            self.store.data["readonly_prepare"]["loader_images"]=[row]
            self.store.flush();self.n.verify_store(self.store)
            row["file_info"]=None;row["provenance"]=None
            self.store.flush()
            # Same admitted System32 pathname and single-link OS identity;
            # nullable record fields cannot choose the private-frozen role.
            with self.subTest(boundary="admission"),self.assertRaises(native.Failure):
                native.admission(self.store.data["readonly_prepare"],self.store.data["context"]["matrix"],
                    private_images=[self.store.root/item["path"] for item in self.store.data["frozen_files"]],
                    system_directory=self.store.w.system_directory)
            self.store.files[path.name]=b"NO"+self.store.files[path.name][2:]
            with self.subTest(boundary="verify_store"),self.assertRaises(native.Failure):
                self.n.verify_store(self.store)
        self.assertEqual(self.store.w.handles,{})

    def test_tool_architecture_version_size_pointer_signature_and_type_reject_without_leak(self):
        for mode in ("wrong_arch","version_size","version_pointer","bad_magic","bad_type"):
            self.store=NativeStore()
            with self.subTest(mode=mode),self.assertRaises(native.Failure):self.tool(mode)
            self.store.close()
            with self.subTest(mode=mode):self.assertEqual(self.store.w.handles,{})

    def abi_observation(self):
        # Synthetic host-layout observation for parser tests only. The actual
        # Windows SDK executable remains a separate x64/ARM64 native gate.
        a=native.abi
        names={"SA":a.SA,"FILE_INFO":a.FILE_INFO,"STARTUP":a.STARTUP,"STARTUP_EX":a.STARTUP_EX,
            "PROCESS":a.PROCESS,"TOKEN_USER":a.TOKEN_USER,"GENERIC_MAPPING":a.GENERIC_MAPPING,
            "EXTENDED_LIMITS":a.EXTENDED_LIMITS}
        value=dict(schema=1,machine="x64",DWORD=c.sizeof(t.DWORD),BOOL=c.sizeof(t.BOOL),
            FILETIME=c.sizeof(t.FILETIME),HANDLE=c.sizeof(t.HANDLE),
            sa_descriptor=a.SA.descriptor.offset,file_volume=a.FILE_INFO.volume.offset,
            file_links=a.FILE_INFO.links.offset,startup_stdin=a.STARTUP.stdin.offset,
            startup_attributes=a.STARTUP_EX.attributes.offset,process_pid=a.PROCESS.pid.offset,
            token_sid=a.TOKEN_USER.sid.offset,job_pid_list=8,job_list_attribute=0x2000D,
            calling_convention_verified=True,owned_buffer_freed=True)
        value.update({name:c.sizeof(kind) for name,kind in names.items()})
        extra={"IO":a.IO,"LIMITS":a.LIMITS,"FILETIME":t.FILETIME,"SID_AND_ATTRIBUTES":native.SID_AND_ATTRIBUTES}
        layout=dict(WORD=c.sizeof(t.WORD),LONG=c.sizeof(t.LONG),ULONG_PTR=c.sizeof(c.c_size_t),
                    IO=c.sizeof(a.IO),LIMITS=c.sizeof(a.LIMITS),SID_AND_ATTRIBUTES=c.sizeof(native.SID_AND_ATTRIBUTES))
        for name,kind in {**names,**extra}.items():
            layout.update({name+"."+field:getattr(kind,field).offset for field,_kind in kind._fields_})
        layout.update({"JOB_PID.assigned":0,"JOB_PID.count":4,"JOB_PID.pids":8});value["layout"]=layout
        return value

    def consume_abi(self,value):
        self.store.files["command-0.out"]=serialized(value)
        result=dict(output="command-0.out",reaped=True,timed_out=False,exit_code=0)
        with patch.object(native,"run_fixed",lambda store,kind:dict(result)):self.n._abi(self.store)

    def test_abi_real_python_consumer_checks_schema_and_pairs_descriptor_and_derived_sid_frees(self):
        self.consume_abi(self.abi_observation())
        self.assertEqual((self.store.w.descriptor_frees,self.store.w.sid_frees),(1,1))
        self.assertEqual((self.store.w.buffers,self.store.w.sid_buffers),({},{}))

    def test_abi_schema_flag_machine_width_and_offset_mutations_reject(self):
        original=self.abi_observation()
        cases=[]
        for key,value in (("schema",True),("machine","ARM64"),("calling_convention_verified",False),
                          ("owned_buffer_freed",False),("DWORD",4 if original["DWORD"]!=4 else 8)):
            changed=copy.deepcopy(original);changed[key]=value;cases.append(changed)
        for key in original["layout"]:
            changed=copy.deepcopy(original);changed["layout"][key]+=1;cases.append(changed)
        missing=copy.deepcopy(original);del missing["HANDLE"];cases.append(missing)
        for changed in cases:
            with self.subTest(changed=changed),self.assertRaises(native.Failure):self.consume_abi(changed)
        self.assertEqual((self.store.w.descriptor_frees,self.store.w.sid_frees),(0,0))

    def test_abi_python_get_process_times_failure_cannot_borrow_c_flag(self):
        with patch.object(self.store.w,"process_created",lambda handle:0):
            with self.assertRaises(native.Failure):self.consume_abi(self.abi_observation())
        self.assertEqual((self.store.w.descriptor_frees,self.store.w.sid_frees),(0,0))


if __name__=="__main__":unittest.main()
```

## Task 8：真实固定 entry.main 完整 TEST 资产

**Dependencies:** Task 1–7 与主 PLAN完整 `scripts/windows_positive_loopback_admin_entry.py`。
**Parallelizable:** No（固定入口与实际Native/下片workflow准入同一合同）。

- [ ] apply_patch 新增完整 `tests/test_windows_positive_loopback_admin_entry.py`。
- [ ] 运行 `PYTHONPATH=src python -m unittest tests.test_windows_positive_loopback_admin_entry -v`。直接执行真实 entry.main，只有其 Admin/Native OS消费者边界使用固定模型，不创建实际豁免或进程。

`readonly_ready`文本从来不能单独授ready。受信workflow必须同时等待真实entry进程exit0、其全部finally/Store.close完成及同候选原件；若先emit后finally失败，实际非零/unknown必须拒绝。下片不得只grep stdout或把本片fake当原生准备成功。

```python
"""Real fixed entry.main control flow; modeled privileged consumers only."""
from __future__ import annotations
import importlib
import io
import json
from pathlib import Path
from types import SimpleNamespace as N
import unittest
from unittest.mock import patch
from tests.test_windows_positive_loopback_admin_binding import identity

NAME="scripts.windows_positive_loopback_admin_entry"
try:
    entry=importlib.import_module(NAME)
except ModuleNotFoundError as exc:
    if exc.name!=NAME:raise
    entry=None


class Consumer:
    def __init__(self):
        self.events=[];self.fail_close=False;self.fail_cleanup=False;self.wait=0
        self.receipt={"stage":"cleaned","binding":"b"*64,"native_restoration_verified":True};self.first_error=None
        self.data={"phase":"prepared","parent":{"pid":1234,"process_created":5678}}
        self.snapshots=[self.snapshot(),self.snapshot()]
        self.store=N(w=N(k=N(WaitForSingleObject=self.wait_parent),close=self.close_handle),close=self.close_store)
        self.native=N(full_get=self.full_get,stop_parent_job=self.stop,reap_commands=self.reap,_process=self.process)
    @staticmethod
    def snapshot():
        return dict(schema=1,entries=[["S-1-15-2-99",7]],api_code=0,complete=True,
            sid_attempted=1,sid_freed=1,array_freed=True,library_freed=True,process_reaped=True)
    def attach_parent(self,pid):
        if pid!=1234:raise RuntimeError("wrong modeled parent")
        self.events.append("attach");self.data["phase"]="bound"
    def serve(self):self.events.append("serve");self.data["phase"]="cleaned";return dict(self.receipt)
    def cleanup(self,*,abnormal):
        self.events.append(("cleanup",abnormal))
        if self.fail_cleanup:raise RuntimeError("modeled cleanup failed")
        self.data["phase"]="cleaned"
    def _failure(self,error):self.first_error=self.first_error or error;self.events.append(("failure",error))
    def full_get(self,store):self.events.append("get");return self.snapshots.pop(0)
    def stop(self,store):self.events.append("stop_parent")
    def reap(self,store):self.events.append("reap_commands")
    def process(self,store,identity,*,allow_gone=False):self.events.append("held_parent");return 50
    def wait_parent(self,handle,milliseconds):self.events.append(("wait_parent",milliseconds));return self.wait
    def close_handle(self,handle):self.events.append(("close_handle",handle))
    def close_store(self):
        self.events.append("close_store")
        if self.fail_close:raise RuntimeError("modeled CloseHandle failed")


class TestAdminEntry(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(entry,"new fixed entry absent; expected facility RED")
        self.admin_module=importlib.import_module("scripts.windows_positive_loopback_admin")
        self.flags=N(isolated=1,no_site=1,dont_write_bytecode=1)
        self.root=Path("/model/icode-positive-admin-"+"1"*32);self.consumer=Consumer()
        b=identity()
        self.env=dict(GITHUB_ACTIONS="true",RUNNER_ENVIRONMENT="github-hosted",RUNNER_OS="Windows",
            GITHUB_REPOSITORY=b["repository"],GITHUB_SHA=b["source_sha"],GITHUB_RUN_ID=b["run_id"],
            GITHUB_RUN_ATTEMPT=str(b["run_attempt"]),GITHUB_JOB=b["job"],RUNNER_ARCH="X64",
            GITHUB_REF="refs/heads/main",GITHUB_WORKFLOW_REF="ayukyo/icode/.github/workflows/ci.yml@refs/heads/main",
            GITHUB_WORKFLOW_SHA=b["source_sha"],ICODE_CI_POSITIVE_LOOPBACK_ADMIN="1",
            ICODE_CI_POSITIVE_LOOPBACK_DEDICATED_WRITER="1")
        test=self
        class AdminBoundary:
            @classmethod
            def freeze_before_user(cls,context,account):
                test.consumer.events.append(("freeze",account,context));return test.root
            @classmethod
            def prepare(cls,root,sid):
                if root!=test.root or sid!=b["account_sid"]:raise RuntimeError("modeled binding")
                test.consumer.events.append("prepare");return test.consumer
            @classmethod
            def recover(cls,root):
                if root!=test.root:raise RuntimeError("modeled recovery binding")
                test.consumer.events.append("recover");return dict(test.consumer.receipt)
        local_sys=N(platform="win32",version_info=(3,12,10),flags=self.flags,
            executable=str(self.root/"runtime/python.exe"),path=list(entry.sys.path),stdout=entry.sys.stdout,
            exception=entry.sys.exception)
        self.patches=[patch.object(self.admin_module,"Admin",AdminBoundary),patch.dict(entry.os.environ,self.env,clear=True),
            patch.object(entry,"sys",local_sys),
            patch.object(entry,"__file__",str(self.root/"trusted/scripts/windows_positive_loopback_admin_entry.py")),
            patch.object(Path,"resolve",lambda path,*args,**options:path)]
        for item in self.patches:item.start();self.addCleanup(item.stop)
        self.output=b""
    def invoke(self,argv):
        stream=N(buffer=io.BytesIO())
        try:
            with patch.object(entry.sys,"stdout",stream):return entry.main(argv)
        finally:self.output=stream.buffer.getvalue()
    def args(self,kind):
        result=[kind,"--root",str(self.root)]
        if kind in ("serve","readonly"):result += ["--account-sid",identity()["account_sid"],"--parent","1234"]
        return result
    def wrong_flags(self,**changed):return N(**{**vars(self.flags),**changed})

    def test_entry_actual_main_body_survives_parent_cleanup_and_store_close_failures(self):
        for owner in ("cleanup","store_close","parent_handle"):
            with self.subTest(owner=owner):
                self.consumer=Consumer();body=RuntimeError("modeled_entry_body")
                def fault(*args,**options):raise body
                def cleanup_fault(*args,**options):
                    self.consumer.events.append("cleanup_attempt");raise RuntimeError("modeled_entry_cleanup")
                def close_fault(*args):
                    self.consumer.events.append("close_attempt");raise RuntimeError("modeled_entry_close")
                if owner=="parent_handle":
                    self.consumer.store.w.k.WaitForSingleObject=fault
                    self.consumer.store.w.close=close_fault
                    operation="serve"
                else:
                    self.consumer.native.full_get=fault;operation="readonly"
                    if owner=="cleanup":self.consumer.cleanup=cleanup_fault
                    else:self.consumer.store.close=close_fault
                with self.assertRaises(RuntimeError) as caught:self.invoke(self.args(operation))
                self.assertIs(caught.exception,body)
                self.assertTrue("close_store" in self.consumer.events or "close_attempt" in self.consumer.events)
                self.assertTrue(any(n.startswith("cleanup_unknown:") for n in getattr(body,"__notes__",())))

    def test_freeze_only_from_original_checkout_before_private_restart(self):
        with patch.object(entry,"__file__","/model/checkout/scripts/windows_positive_loopback_admin_entry.py"):
            self.assertEqual(self.invoke(["freeze","--account","icodeprobe_a"]),0)
        self.assertEqual(json.loads(self.output)["stage"],"frozen")
        self.assertEqual(self.consumer.events[0][:2],("freeze","icodeprobe_a"))
        self.consumer.events.clear()
        with self.assertRaises(RuntimeError):self.invoke(["freeze","--account","icodeprobe_a"])
        self.assertEqual(self.consumer.events,[])

    def test_private_arguments_cross_root_wrong_python_and_client_handle_refuse(self):
        for argv in (["readonly","--root","/other","--account-sid",identity()["account_sid"],"--parent","1234"],
            ["recover","--root",str(self.root),"--parent","1234"],
            ["serve","--root",str(self.root)],self.args("serve")+["--handle","99"]):
            with self.subTest(argv=argv),self.assertRaises((RuntimeError,SystemExit)):self.invoke(argv)
        with patch.object(entry.sys,"executable","/external/python.exe"):
            with self.assertRaises(RuntimeError):self.invoke(self.args("readonly"))
        self.assertEqual(self.consumer.events,[])

    def test_platform_python_flags_and_unknown_operation_refuse(self):
        for key,value in (("platform","linux"),("version_info",(3,11,17)),
                ("flags",self.wrong_flags(isolated=0)),
                ("flags",self.wrong_flags(no_site=0)),
                ("flags",self.wrong_flags(dont_write_bytecode=0))):
            with patch.object(entry.sys,key,value):
                with self.subTest(key=key,value=value),self.assertRaises(RuntimeError):self.invoke(self.args("readonly"))
        with self.assertRaises(SystemExit):self.invoke(["arbitrary-command"])
        self.assertEqual(self.consumer.events,[])

    def test_readonly_success_requires_complete_configuration_and_cleanup_close(self):
        self.assertEqual(self.invoke(self.args("readonly")),0)
        self.assertEqual(json.loads(self.output)["stage"],"readonly_ready")
        self.assertEqual(self.consumer.events,["prepare","attach","get","stop_parent","get",("cleanup",True),"close_store"])

    def test_readonly_configuration_delta_emits_no_ready_and_still_cleans(self):
        self.consumer.snapshots[1]["entries"][0][1]=8
        with self.assertRaises(RuntimeError):self.invoke(self.args("readonly"))
        self.assertEqual(self.output,b"")
        self.assertIn(("cleanup",True),self.consumer.events)
        self.assertEqual(self.consumer.events[-1],"close_store")

    def test_readonly_emitted_line_cannot_override_finally_failure(self):
        for failure in ("fail_cleanup","fail_close"):
            self.consumer=Consumer();setattr(self.consumer,failure,True)
            with self.subTest(failure=failure),self.assertRaises(RuntimeError):self.invoke(self.args("readonly"))
            self.assertEqual(json.loads(self.output)["stage"],"readonly_ready")
            self.assertEqual(self.consumer.events[-1],"close_store")
            # There was no successful main return/exit0: stdout alone grants nothing.

    def test_serve_waits_for_original_parent_finally_before_closing_owned_job(self):
        self.assertEqual(self.invoke(self.args("serve")),0)
        self.assertEqual(json.loads(self.output)["stage"],"completed")
        wait=self.consumer.events.index(("wait_parent",30000))
        self.assertLess(wait,self.consumer.events.index("close_store"))
        self.assertIn(("close_handle",50),self.consumer.events)
        self.assertNotIn("stop_parent",self.consumer.events)

    def test_serve_parent_finally_timeout_stops_and_refuses_completed(self):
        self.consumer.wait=258
        with self.assertRaises(RuntimeError):self.invoke(self.args("serve"))
        self.assertEqual(self.output,b"")
        self.assertEqual(self.consumer.first_error,"parent_failed")
        self.assertLess(self.consumer.events.index(("wait_parent",30000)),self.consumer.events.index("stop_parent"))
        self.assertEqual(self.consumer.events[-1],"close_store")

    def test_recover_uses_only_exact_trusted_root_and_result_status(self):
        self.assertEqual(self.invoke(self.args("recover")),0)
        self.assertEqual(self.consumer.events,["recover"])
        self.consumer.receipt["native_restoration_verified"]=None
        self.assertEqual(self.invoke(self.args("recover")),4)
        self.assertEqual(json.loads(self.output)["stage"],"recovery")


if __name__=="__main__":unittest.main()
```

## 其余组件的强制验收约束

本节是 TEST/SOURCE 对齐条件，不是可替代完整代码的测试资产，也不授本文件冻结状态。每行软件判据必须由真实组件输出和有状态边界副作用检查，不允许仅查源码字符串。

| 边界 | 必须观察的软件行为 | 原生信用界限 |
| --- | --- | --- |
| privileged loading | 临时用户不存在时冻结 interpreter/stdlib/scripts/imports；坏 owner/DACL、用户可写依赖、身份/hash变化、reparse/hardlink均拒绝；不是固定路径就可信 | 假ACL/文件ID表仅模型；真实NTFS/加载须同SHA两Windows |
| CPython loading layout | 精确检查exe/DLL对应._pth、exe同级与父级pyvenv.cfg、python312.zip存在与缺席路径；额外/缺失/变化拒绝，禁止外部stdlib/DLL借用；不靠-I/-S声明补证 | fake只证明拒绝算法；双Windows实际sys.path/DLL/pyd解析仍须原件 |
| bootstrap | domain固定`icode_positive_bootstrap_v1`，identity不自含digest；public包仅identity/binding；180000ms；同created槽持久消费一次，旧内存对象/旧账本实例不重开 | 请求文本不证明Create成功或调用者身份 |
| operation | domain固定`icode_positive_operation_v1`；session为admin生成32小写hex；outer exact schema/session/request；内层真实core serializer/validator；prepared clock不可替代add_intent起≤60000ms | core State及flags无OS authority |
| schema/parser | 逐字段删/增/错类型、duplicate keys、UTF8错误、NaN、超4096、bool-as-int、wrongSID/profile/nonce/port/PID/creationtime/run/job/candidate、跨domain和重放均拒绝且无命令副作用 | 不能把nonce称秘密认证 |
| 固定 request slot | 只读期间拒写，持有目录/文件handle确认volume/file ID、owner/DACL、无链接，独立只读receipt与admin-onlyledger；替换/拒Flush/消费后重开均拒绝 | 内存文件表不证明真实NTFS race已消除 |
| 双预算 | prepare接近180s仍可合法创建全新≤60soperation；bootstrap过期不得命令；operation过期不得launch/成功但必须窄清理；固定端口冲突不重选 | 时间预算非OS路径hard deadline |
| 固定CLI | 真实argv生产仅`System32/CheckNetIsolation.exe` + `LoopbackExempt` + `-a`或`-d` + `-p=<预绑定positive>`；环境SystemRoot/PATH污染、自由路径/命令/op/SID均无影响或拒绝 | 不主动运行CLI/安装工具 |
| suspended命令 | CreateProcess时JOB_LIST admission；持有精确PID/creationtime；intent和PID持久Flush完成后才Resume；create/assign/persist/Flush/Resume每阶段故障不授成功 | 假Win32事件序列仅软件ABI/算法；原生检验实际Job admission |
| command回收 | wait结果、held process已退出、完整Job PID query为空均必须真实读边界；false reaped、active count0但列表不空、list截断均拒绝 | 不能用CommandResult.reaped=True当OS证明 |
| outerJob | 正常要求Assigned/Returned完整一致且恰为live held parent PID，creationtime/token SID相同；额外helper/错PID/父退出/PID复用/截断必须异常；异常terminate后完整空列表 | 不声称包含任意恶意账号借其它系统设施生成的所有进程 |
| late add | 未观测退出的add不能并发delete；回收后freshGet决定唯一SID清理；晚写、超时、写后丢回执均不launch，fallback重开原ledger仍可窄清理 | 实际未回收保持unknown，不能凭进程句柄关闭推断退出 |
| 映射/ownership | 非空foreign/非零Attributes逐项保持；positive或Reviewer预有条目拒绝且零delete；目标属性冲突拒删；foreign新增/删/改不回滚，窄删owned后整体仍unknown | 不为负控修改foreign/Reviewer；不声称穷尽ABA或未知并发 |
| independent recovery | 精确trusted_root且同context；账本在account/probeRoot删除树之外；坏schema/丢intent/丢命令身份/权限改变不猜SID；完成后二次recover幂等不发新命令 | always未运行/runner丢失只能unknown |
| 首错/收据 | operation错误永不被cleanup错误覆盖；cleanup错误独立列出；unknown/null不得补true；每ordinary JSON≤500B，不截断/自由分片、不泄漏完整SID名单 | 软件receipt绝不能授native恢复或Reviewer DENY |
| 真实consumer | 必须另片真实Create hr0/SID match→created→只读addreceipt→原固定launch→Job事实→delete前清理；None保持旧链；两nonce/ACL/profile各自核验 | 本片admin单独通过不代表consumer接线/系统通路通过 |

## 后续 CI 的只读 native prepare 先行门

同新候选的 x64/ARM64 必须先执行真实 Native prepare 正控，位于任何 CheckNetIsolation add/delete 之前。它必须使用真实 runner 的 loading root、每级祖先 owner/ACL、held file identity、runtime/stdlib/import依赖、标准账号不存在/后创建绑定、完整 Get 及 outer Job compatibility；固定 schema 导出角色和完整性摘要，私有原件保留。该门不新增豁免、修改 foreign/Reviewer 或通过白名单遮掩现有拒绝。

该门必须包含 Windows SDK 编译得到的 `sizeof/offsetof` 与实际 Python ctypes 的逐项对照：DWORD/BOOL/HANDLE/ULONG_PTR、SA、FILE_INFO、STARTUP/STARTUP_EX、PROCESS、TOKEN_USER、SID_AND_ATTRIBUTES、FILETIME、Job PID list头/元素宽度，以及 Job limit/IO 结构。可复用现有 native ABI 校验机制，须在新真实 Native/CI PLAN 冻结精确资产及入口；不能只对照两份Python常量。DLL WinAPI calling convention、restype/argtypes、pointer ownership、attribute list/Job handle list/SECURITY_ATTRIBUTES/环境块/字符串 buffer 在调用期间的生命期分别核验，不能因 host fake自产自读一致就授通过。

准备门若因祖先 owner/ACL、依赖路径、Nested Job 或角色链不满足而拒绝，本候选停在明确 stage 的 failed/unknown。保留原件，后续由 SOURCE/安全合同重新评审能够证明的精确前提；不能把“软件fake通过”或“下一层protected”直接授父目录安全或 native 可运行。原生门的执行命令必须在完整 Native facade/只读入口冻结后逐字绑定，不由本TEST文件发明入口。当前没有执行该门，也没有真实 Windows 可运行信用。

## root 授权的 DOC RAM 预演记录

仅从已读DOC围栏创建RAM模块，未创建实际SOURCE/TEST、未调用真实Windows/API/CLI。早期缺失 Native 时仅用实例化立即 Assertion 的 import 哨兵使Admin可载入；协调TEST随即patch为本文明确模型，哨兵没有任何真实方法，不能补Source inventory/Native验收。Native围栏出现后所有后续RAM均加载真实Native，彻底移除哨兵。

解释器更正：从`9fb5a8`至`8bd8fc`的早期RAM误用了WSL默认python3，实际traceback为`/usr/lib/python3.10`，不是3.11或3.12；原先“RAM全在WSL3.11”表述错误，现明确撤回并保留这些历史结果。`06906c`仍仅是root另行运行的3.11布局诊断，不能转授早期RAM版本。自`a0b02e`起固定`/home/orbbec/icode-r2r3-env.DL2JQJ/bin/python`，真实打印3.11.17版本；没有安装解释器。所有RAM均不授产品支持、正式TDD或Windows/native信用。

| 历史快照 | 真实结果 | 归因 |
| --- | --- | --- |
| SOURCE `49ad7aa935cf402a93dba2def37869474ac6621b5b9a9f67667be9a9c8c384bf` / TEST `220d4e7377e3390475f904c7d3c880eb0380813e4e37363bb85684b5d9eb95d1`，工具`9fb5a8` | 60方法；4 Assertion失败、15 ERROR、0skip | Get12P/binding7P；Win假HANDLE未normalize；Admin新has_add_attempt未同步model；Job初始None故障开关误触发；Store两个SOURCE行为缺口 |
| SOURCE 同上 / TEST `cebaf4983d70d02af183d587cd7a82affbb275e0c1ad605202627899152997f8`，工具`696cb3` | 61方法；59P/2 Assertion失败/0ERROR/0skip | Get12P/binding7P/Win11P/Admin13P/Job8P；Store10方法两失败仍为scandirerror返回partial及source root reparse未拒。已向SOURCE作者报告，不放松TEST |
| SOURCE `301e0496487b1443a6e69e10ae710f3e261e85a2a03e8cde7708dd2de0c30cf7` / TEST `0e13b22da12ee7c4d6dd91f5016ec5438a0cdd3cbf546e1ae9b02dfe375af8a1`，工具`fed12e` | 同61方法，61P/0F/0ERROR/0skip | SOURCE修复原路径逐祖先/root reparse检查及os.walk onerror；原两Store负控字节不变。Get12/binding7/Win11/Admin13/Store10/Job8均仅RAM诊断 |
| SOURCE `60328cac6b33f32c7f5d4c579207147d0d2c7e63511d1458be0c0151090bf407` / TEST `5dc0150823012fc162ffa4b165a01cee47385a08b9421cb2602c44ceee18e806`，工具`67b388` | 同61方法，61P/0F/0ERROR/0skip | TEST Job模型改为创建时实际分配handle表、拒绝double/unowned close；正常alive为空，close失败保留alive线程31。仍仅RAM诊断 |
| SOURCE 同上 / TEST `e0c58c4ed1ef67d7c2c6d88f1b92cf035c471186ed197bfafdf3f58879416b5e`，工具`803d7f` | 65方法，65P/0F/0ERROR/0skip | Job新增4方法，真实wait_empty递进单调钟与有限步上限；持续后代/Query失败或不完整/Terminate失败/Wait超时均不返回成功、内存及持久reaped=false。Get12/binding7/Win11/Admin13/Store10/Job12，仍仅RAM诊断 |
| SOURCE `38d5ce841464f6b210cd6853341be0070683d25eeccfc3daa5a78072d0636b0b` / TEST `6091f1f868f2d67fa53dd2c96f4f3e456ec6b41bfddf08c072e26531971c62cc`，工具`ac9561` | 83方法；7 Assertion/0ERROR/0skip | 默认3.10历史诊断。Native真实ledger五个跨字段subcase未拒；loader路由故障漏handle、reap缺job分支漏process。SOURCE作者修正，TEST语义未放松 |
| SOURCE `117337c486e2271e8903085348adb1a49ee3a265274b3b68aef6f11f4c746ed8` / TEST `475e314b5d78e52132198c673e6032be160ec8cb94aaf5737e57a98318ce2dfe`，工具`a0b02e` | 指定3.11.17，总exit1 | fixture尚未模拟新增readonly路径namespace与System32 FILE_INFO，Native20ERROR；Entry局部sys facade后9P。没有把fixture ERROR计SOURCE缺陷 |
| SOURCE `5fb165f051d31118dac04ae45d6747d733212e93b18eeb2bf69032447f011b82` / TEST `1c5c43db88a1f842893c0f4d06b5f0e9642e11e530351927ddf94c3ba5d32fd8`，工具`5c2efb` | 指定3.11.17，99方法；97P/2ERROR/0skip，总exit1 | Native25P；Entry新增compact receipt字段stage/binding未补fixture，按真实producer补齐，未放松入口门 |
| SOURCE `d37fe1a0d57669ac6b10f404fba13af1aa682eca05a7332bf4703b5d16c1246c` / TEST `5244ce1f0799cd911244da81ea3c39f5e3fd472340fc00ccd7661838bef176c0`，工具`e7c6cb` | 指定3.11.17，110方法；110P/0F/0ERROR/0skip，总exit0 | Get12/binding7/Win11/Admin13/Store10/Job13/Native35/Entry9；真实Native/entry加载，无哨兵。仍仅DOC RAM预演 |

这些hash只绑定各次运行前DOC字节；本记录添加后TEST DOC hash自然改变，不称同字节重跑。此为未冻结计划的诊断，既不是正式TDD RED/GREEN，也不是完整admin或Windows原生验证。

早期诊断harness逐组件继续且未累计shell退出，因此它退出0不能代表失败轮通过；判据一直保留实际failures/errors/skip。自指定3.11.17轮开始，harness累计所有failure/error/skip并总exit1/0，失败不再返回0。最后完整合并原输出24703 UTF-8字节的SHA256为`5dbd943a7628e84fb82690ffea7eeb99d324f9fc77794697cf282cbb854c07f8`（工具`e7c6cb`；哈希工具`aa040a`）。正式TEST阶段仍使用直接unittest原退出，不把RAM预演称TDD。

## 冻结八资产清单与正式语义 RED

各围栏均末尾LF，UTF-8编码；围栏本身不计入资产。以下只冻结TEST代码字节，非本DOC含后续元数据的自引用hash。

| 目标路径 | LF行 | UTF-8字节 | SHA256 | test方法 |
| --- | ---: | ---: | --- | ---: |
| `tests/test_windows_positive_loopback_admin_get.py` | 291 | 13757 | `e6a12c31a2c892171f9fc86a9315205b6b04a73ff4bf574621b5ca50b512dda6` | 13 |
| `tests/test_windows_positive_loopback_admin_binding.py` | 157 | 8584 | `166cf869042951ac6a8e56ac929ef9c6edd0a667959506dcef1cb59475c27b21` | 7 |
| `tests/test_windows_positive_loopback_admin_win32.py` | 428 | 25692 | `8dd0535ed8dce763c1318a027a697b7881c693cfedd9079a90f0bb8e6b6b4582` | 15 |
| `tests/test_windows_positive_loopback_admin.py` | 319 | 17194 | `5af0dce6810fea898e70c61bd9f790f371192d961bf47add388ce5e87dfec770` | 16 |
| `tests/test_windows_positive_loopback_admin_store.py` | 351 | 20080 | `d4d5cb7d3f54ca1ce7589ca6ce9803a9ef877bd7e6775385ace16e879d2583ad` | 17 |
| `tests/test_windows_positive_loopback_admin_jobs.py` | 342 | 18823 | `cc92211105763ba104c1bcd382aefcd8c12db46676978ba1eeef4ccb608a9e46` | 16 |
| `tests/test_windows_positive_loopback_admin_native.py` | 1383 | 90222 | `a1bb44a91775b91153cf5bd0ddae0631e39710fd10c481293d8c04d9f3aabc76` | 58 |
| `tests/test_windows_positive_loopback_admin_entry.py` | 192 | 11446 | `fefa7004009ccf26a4809ca2f795a00943166d8c894df59296e22b4ab189eb17` | 10 |

正式TEST-only必须由不同于SOURCE的作者，在确认八新SOURCE路径仍不存在后，apply_patch仅新增上述八TEST完整字节。不得把内存注入harness落地作实际依赖。ROOT/src现有纯core保持原样；当前八模块预期分别13/7/15/16/17/16/52/10个setUp Assertion FAIL，合计146F、0P、0ERROR、0skip，原exit1；这只是新增设施缺失RED，不是146个既有产品Bug。内部依赖错名、ModuleNotFound/TypeError/loader ERROR不算合格RED。记录完整原退出与日志hash、核资产字节后，fresh actualTEST SPEC→不同QUALITY，才允许不同SOURCE作者落已双审SOURCE资产。

ROOT正式单次命令（不是当前执行指令）：`PYTHONPATH=src /home/orbbec/icode-r2r3-env.DL2JQJ/bin/python -m unittest tests.test_windows_positive_loopback_admin_get tests.test_windows_positive_loopback_admin_binding tests.test_windows_positive_loopback_admin_win32 tests.test_windows_positive_loopback_admin tests.test_windows_positive_loopback_admin_store tests.test_windows_positive_loopback_admin_jobs tests.test_windows_positive_loopback_admin_native tests.test_windows_positive_loopback_admin_entry -v`。指定3.11仅本机软件诊断，产品/host CI仍3.12，同SHA双Windows实际ABI/loading/Job/ACL/nonce/恢复门不可被此命令替代。不提交、不安装、不运行任何admin入口或实际系统命令，直到root另行解冻相应阶段。

【历史110方法快照的架构级自检报告，非当前计数】
语法/编译：八Python围栏AST及指定3.11.17 RAM110P，通过仅软件诊断；依赖/调用链：真实Admin/reader/Win32/Store/jobs/Native/entry逐层对齐，实际consumer与CI接线仍待下一片；逻辑/边界：完整Get、双预算、owned/foreign、持久化/Resume/Job回收、durable recovery、角色loading/版本/ABI消费者与固定入口均有完整软件资产；异常处理：保留原失败与解释器更正，未知不补true，不使用哨兵补Native；关联模块：本轮只新增本DOC；兼容安全：不改现core/旧链/权限，Reviewer/foreign永不主动修改；可运行性：当前快照RAM110P，未正式TDD、未Windows编译/运行、未验系统豁免/恢复；整体仍待root全文及fresh双审，不能声称100%原生可运行。

---
**Execution Mode:** serial（DOC-only，不触发实施）。

## fresh SPEC 后的嵌套目录回归：当前不再是110方法冻结快照

本小节113方法为中间历史；最新I1–5完整121方法诊断见末节，资产表已更新最新字节。

root授权仅本TEST DOC增补，未改SOURCE。Task5新增3方法，当前八资产共113方法；上文110P与110缺SOURCE预期属于原冻结历史，不能迁移为当前完整运行结果。当前正式缺SOURCE预期调整为12/7/11/13/13/13/35/9，即113 Assertion FAIL、0P/0ERROR/0skip、exit1，仍待实际正式TEST-only取证。

真实复核完整阅读Store.create_directory、Native.freeze及既有Store测试：freeze先创建trusted再trusted/scripts，而原方法遍历每个分量，只要祖先trusted已存在即抛directory_exists。新增测试调用真实Store方法，按freeze原顺序创建trusted、trusted/scripts、trusted/src、trusted/src/icode；Win32底层create_directory替身使用真实临时namespace的mkdir且不允许exists_ok，未patch Path.exists、未绕过生产路径判断。另保留既有叶拒绝、预存在但未获私有准入的祖先拒绝及零新建负控。此测试不决定安全复用existing ancestor策略，SOURCE需独立证明准入/身份/权限而非宽松exists_ok。

工具`bcdc63`实际指定`/home/orbbec/icode-r2r3-env.DL2JQJ/bin/python`，打印`3.11.17 (main, Oct 9 2026, 15:21:28) [Clang 22.1.3]`。SOURCE DOC SHA256 `f68bdea3aad642db88d6f01ba6c90fb1a898f81105de2c7c6a5bfb83c1a2006e`，TEST运行前DOC SHA256 `9a75cd649dea4c4687b287bbdf79fd1029495ebd66a7fe50b5e0650d0385509a`。仅运行完整Store模块13方法，实际12P/1Assertion FAIL/0ERROR/0skip，合并退出1；未将该局部结果称113整片结果。

失败方法`test_freeze_nested_trusted_directory_sequence_uses_real_store`：真实Store围栏162行抛`Failure: directory_exists`；测试138行调用、140行转为语义`AssertionError: Native.freeze nested directory chain rejected trusted/scripts: directory_exists`。另外两新增拒绝方法通过。完整原合并输出SHA256 `5c464b63d33cf7cf63ad069f1f4dee8f1dfb26178c52018c670387933e2f8072`（哈希工具`b7bb2b`）。这是DOC RAM的实际SOURCE缺口诊断，不是正式TDD或原生证据；本记录加入后DOC hash自然不同。

【架构级自检报告】语法/编译：当前Store围栏由指定3.11成功compile；依赖/调用链：真实Store及freeze同序列，不替换FakeStore；逻辑/边界：新增3方法、保留拒绝门；异常处理：实际1Assertion失败如实保留；关联模块：仅本DOC；兼容安全：未改SOURCE/core/系统权限；可运行性：Store实际12P/1F，尚未修复，不能交付GREEN或100%可运行声明。其余7围栏字节不变，后续fresh审查与实际TEST-only仍必需。

## fresh SPEC I1–5：原SOURCE完整语义RED（121方法）

本节是原f68诊断历史，不是最新修订快照；最新123方法及合法producer夹具同步见末节。资产清单表已更新当前围栏字节。

原115方法完整保留，再新增6方法。当前八围栏方法数12/7/12/14/13/14/40/9，共121。上文110P与113历史不授此快照GREEN；正式缺SOURCE预期也更新为同分布121 Assertion FAIL、0P/0ERROR/0skip、exit1，尚未正式落TEST执行。

I2在Native资产新增2个有效success-ledger replay方法及1个真实producer序列方法：真实Admin第一次cleanup成功，保存durable原字节，以独立新Store对象decode重开、新Native及新Admin controller再次always cleanup；真实Native.verify_store/full_get/ledger未替换、不绕校验。worker只有固定get边界模型，实际追加完整command和raw文件字节。旧两replay是手工构造合法成功ledger，不能独自证明第一次生产；新增producer序列已补此缺口。正控允许第二次在原deadline后重验，但必须保留原started/deadline/completed；foreign变化负控不得复用exact成功，不允许再次add/delete。原CODE三方法皆实际Assertion失败。

I3：真实Win32.open_file的descriptor/info/security/最终路径算法均执行，fake只替换最底API和ctypes内存；内层descriptor释放成功，外层LocalFree失败使return取消，却未关闭已取得文件句柄90，stateful alive断言失败。真实Jobs.create_job的最底Kernel LocalFree失败后，Job10同样留alive。两个方法均保留分配/关闭所有权表，不只断言mock调用次数。

I4：真实Admin.serve，最底Native消费者模型在first_wait、second_wait、freeze_operation、publish_add四边界抛错；实际durable first_error仍None，四subcase均Assertion失败。断言必须持久首因、exact不为true、cleanup收据不能宣称native_restoration_verified=True；原异常不被收据成功掩盖。该层只授协调算法，不声称Native请求ACL或真实发布通道。

I5：真实Native.ledger，对真实ready前置账本做四负控：两baseline都预含positive、都预含Reviewer、两baseline不同、added+target_attributes=7而after_add缺目标。原ledger只逐个_mapping接受合法形状而未闭合跨观测语义，四subcase实际均Failure未抛。测试不授delete所有权、不改foreign/Reviewer。

完整诊断工具`7541a1`：实际解释器`/home/orbbec/icode-r2r3-env.DL2JQJ/bin/python`，`3.11.17 (main, Oct 9 2026, 15:21:28) [Clang 22.1.3]`；SOURCE DOC `f68bdea3aad642db88d6f01ba6c90fb1a898f81105de2c7c6a5bfb83c1a2006e`；TEST运行前DOC `29749020c2325ae67524020dd9f5a3046de43467dfe05f8cbccb444281a14422`。121方法，9个失败方法含14个Assertion失败条目、其余112方法通过，0ERROR/0skip，真实总exit1。完整合并原输出37966 UTF-8字节，SHA256 `6b4d37eb0609f2c5091735afd7aeac1f2fe6388e438686f72a6264f8c94fbc8a`。root工具`7baafb`独立同快照复核同结果，仍非正式TDD/native。

此前工具`5858d1`为121方法13Assertion/1ERROR/0skip/exit1；ERROR是测试错误引用未导出的native.LEDGER_LIMIT，不是SOURCE缺陷，已改用真实Store既有8388608边界值。随后`7541a1`才是上述无ERROR语义RED，不能混淆。

最小root复现：在现有DOC RAM harness加载七真实SOURCE与八TEST后，仅运行`unittest.defaultTestLoader.loadTestsFromNames(['test_real_first_cleanup_producer_then_independent_reopen_cleanup'], modules[6].TestAdminNative)`（或从该class建立同名TestSuite）。不落文件；必须保持f68 SOURCE与上列TEST围栏字节。首次cleanup真实成功，第二次`Admin.cleanup`源码364行抛cleanup_failed，TEST484行转`AssertionError: real first-cleanup ledger failed independent always: cleanup_failed`。只运行此一方法原退出也必须为1。

【架构级自检报告】语法/编译：8围栏真实compile与AST通过；依赖/调用链：真实Store/Admin/Native/ledger/Win32/jobs消费链，未跳校验；逻辑/边界：121方法并保留全部旧负控；异常处理：14Assertion与早期fixture ERROR均原样记录；关联模块：只改本TEST DOC；兼容安全：未改SOURCE/core/Git/实际TEST及权限；可运行性：真实整体exit1，SOURCE待独立作者修复，禁止称GREEN/正式TDD/原生完成。

## 修订SOURCE的合法producer夹具同步及稳定123方法快照

本轮先完整读修订Admin._failure/created/cleanup/serve、Store.create_directory及资源transfer、Native.ledger/consume_request、image_proof/admission/_image_provenance/_loader/_tool_admission/verify_store，并向独立SOURCE作者确认接口。仍仅修改本TEST DOC，不落实际SOURCE/TEST、不改core、不执行Git/Windows/API/CLI。使用nbl.receiving-code-review技能，逐项核对真实实现再同步夹具，不把review文字或宽松fake当验收。

所有原121方法及断言意义保留。Store目录模型仅新增最底open_file：exact PRIVATE、directory=True、真实临时namespace/非symlink/canonical、真实inode身份；成功后断言所有pins对应实际活句柄，再调用真实Store.close核归零。已有叶与未获私有准入祖先仍拒，不能通过成功立即close断言迫使SOURCE丢生命周期pin。

两个手工成功ledger replay夹具补真实producer所需after_add=B+target、单次成功add完整record（attemptedTrue/returned1/reapedTrue/exit0/noTimeout）、pre_delete/post_delete与原completed clock；真实Native.verify_store/ledger始终执行。真实第一次cleanup→独立重开测试每个生产中间Flush之前调用真实ledger、持久序列化后decode再调用真实ledger，并保存阶段序列；新Store对象只重开持久字节，不重生原OS对象，进程退出与Job成员事实保持同一边界状态。新增第122方法明确拒绝cleanup_intent仍持exact/delete成功flags、拒绝缺readonly/parent/job；正确durable撤成功flags的中间账本合法。不用noop readiness或删负控获得通过。

新shared-image fixture提供实际256字节PE、Machine、Characteristics DLL位、ctypes真实52字节VS_FIXEDFILEINFO（DLL FileType2、tool FileType1）、完整raw SHA256和严格provenance；真实Native._image_provenance读取/解析，真实verify_store再次读取并逐项比较。新增第123方法：共享DLL不是DLL、未知Machine、错Version FileType、坏MZ均拒；持久已准入OS image同长度raw变化（hash漂移）和version变化也均拒。没有patch image_proof/_image_provenance/verify_store/ledger，也不把这些软件PE字节赋予真实Windows映像可信度。

中间记录如实保留：`53d174`绑定SOURCE `e6b0511373924f84c49f94a5288dd5ef2f152f94aec77f0761568fe16ace4bf1` / TEST `295a66d1b30a574951e28de24588b5016bdd5538142b594fdaffd7266bf514df`，指定3.11.17，122方法121P/1AssertionF/0ERROR/0skip、exit1；原因是夹具重开错误重生了已退出PID2234，非新SOURCE缺陷。修为保持原process/jobs事实后`036b66`同SOURCE / TEST `25c0cd83a01f2c48437944b025f2cc97647df1192ed543d5802a71ccfdb3be0c`实际122P、exit0，但工具输出截断，不给完整日志hash。随后SOURCE切换新image schema为`d65a95ac1a6356f3417cbba2e26bbc5d31bba241db8212b180f76a99e91be953`时，同TEST工具`dd2023`实际122方法0F/22ERROR/0skip、exit1（admission_record_schema、缺advapi32.dll字节等旧fixture），不能继承e6b通过或将fixture ERROR当SOURCE RED。

SOURCE作者确认d65a95完整CODE稳定后同步image fixture，`649d9d`绑定TEST `dcc7dc016d0dbd5729b18b1eaa56fca6e7463995ba601fabecd4ad233f818a75`实际122P/0F/0ERROR/0skip、exit0。加入必要shared-image负控后最终工具`7b02dc`：真实解释器`/home/orbbec/icode-r2r3-env.DL2JQJ/bin/python`，打印`3.11.17 (main, Oct 9 2026, 15:21:28) [Clang 22.1.3]`；SOURCE DOC SHA256 `d65a95ac1a6356f3417cbba2e26bbc5d31bba241db8212b180f76a99e91be953`；TEST运行前DOC SHA256 `534c0080a2461d8b5ee5754e44676348340ded1ddac66f16964992a518a25c73`。完整123方法，123P/0F/0ERROR/0skip，真实总exit0。完整合并输出25836 UTF-8字节SHA256 `6bbc5cebcf006bde80d121bcb5a182e896b101954ac8f50974326e452dab9fe0`，未截断。当前8围栏字节与该次运行不变，只有本元数据追加使DOC hash变化。

当前正式缺SOURCE语义RED预期明确更新为12/7/12/14/13/14/42/9，共123 setUp Assertion FAIL，0P/0ERROR/0skip、exit1。它仍只是预期，不是本轮已经正式执行的TDD RED；未来必须先按冻结TEST落实际资产取RED并fresh双审，再不同SOURCE作者实施。本轮所有通过/失败只授DOC RAM算法诊断，不授Windows SDK ABI、实际DLL调用/NTFS/ACL/Job回收、豁免与精确恢复、consumer接线或产品验收。

【架构级自检报告】语法/编译：8围栏AST及指定3.11.17实际RAM123P；依赖/调用链：真实生产方法与底层边界对齐，中间Flush不绕真实ledger；逻辑/边界：全部121旧方法保留并新增2必要跨字段/image负控；异常处理：历史RED、fixture故障、截断输出均按真实退出区分；关联模块：唯一写本TEST DOC；兼容安全：不改SOURCE/core/实际TEST/Git/本机系统权限；可运行性：冻结软件快照123P，尚未正式TDD/Windows原生/真实consumer与CI全门，禁止称100%产品可运行。

## 同scope角色降格补充：当前124方法，d65仍实际RED

本节保留d65原件RED；后续角色修订的最终124P及当前冻结字节见末节，不将两SOURCE混作同快照。

root与SOURCE作者只读核实角色选择缺口后，保留原123方法，追加真实System32 DLL nullable-proof降格负控，当前分布12/7/12/14/13/14/43/9。方法`test_system32_singlelink_image_cannot_downgrade_to_private_nullable_proof`先以实际`/windows/System32/kernel32.dll`路径、实际ctypes FILE_INFO links=1、真实PE/Type2/版本/proof及真实verify_store正控通过；随后保持路径/identity/security/effective，仅置file_info=None/provenance=None，再破坏该文件MZ。真实admission和真实verify_store均必须拒绝，不能让可变nullable字段自行选择private frozen角色。其余CheckNet工具保持links2原事实，未修改为未知private路径，也不绕过真实ledger/loader校验。

工具`b0ef02`实际指定3.11.17，SOURCE DOC `d65a95ac1a6356f3417cbba2e26bbc5d31bba241db8212b180f76a99e91be953` / TEST运行前DOC `8334dbfcdaccd4c1abf8d6ef252c65fbeefea80c25967d82f1e2570e7d75fbad`：完整Native43方法，42方法P、1失败方法含2Assertion subfail、0ERROR/0skip、exit1。TEST868/871行分别`AssertionError: Failure not raised`，完整原输出11407 UTF-8字节SHA256 `dca87c1096b49e1fae7e7b7214ca92b45894e4df24d2b6415a6273a9ea6db1e5`。最小root复现：既有DOC RAM loader后，仅加载该TestAdminNative方法并保留原退出1。没有执行实际System32访问或写入，所有DLL字节都是软件边界模型。

此前`9f2fe4`同d65 / TEST `d145433a92d57a35d5bb63dcbf71649579fbf56f70b68bda0526fa0d4ed4cc09`为43方法0F/1fixture ERROR/0skip、exit1：最初singlelink替身错误改变所有OS image links，使无关CheckNet工具原links2与账本不符，已限定仅kernel32.dll handle后才得到上述有效两Assertion RED，不计该fixture ERROR为SOURCE缺陷。123P不授当前新增124方法通过；正式缺SOURCE预期也相应为124 Assertion FAIL、0P/0ERROR/0skip、exit1，仍待正式执行。

【架构级自检报告】语法/编译：新增方法实际compile；依赖/调用链：真实admission/verify_store及合法shared proof正控；逻辑/边界：原123保留、同路径角色降格拒绝合同；异常处理：真实2Assertion及旧fixture ERROR分账；关联模块：仅本DOC；兼容安全：无SOURCE/实际TEST/Git/native修改；可运行性：当前局部真实exit1，待独立SOURCE修复，不宣称GREEN或原生角色安全。

## 最终角色绑定修订：完整124方法冻结

本节为角色修订历史快照；fresh SPEC新增同scope资源释放失败负控后当前127方法，见末节，表格为当前围栏。

收到独立SOURCE作者接口冻结信号后，完整读真实admission/ledger/private批准集合与verify_store重开角色分支及全部Native ledger调用位置。其正式签名为`admission(value,matrix,*,private_images=(),system_directory=None)`、`ledger(data,*,private_root=None,system_directory=None)`；实际Native入口始终传真实root/System32，不由nullable字段自选角色。测试只同步合法fixture：全部直接ledger调用和真实producer每次中间Flush校验都传同实际store.root、store.w.system_directory；新增默认合法private reader image，路径来自原frozen_files批准集合、file_info/provenance皆None，证明私有成功形状不因缺默认参数误拒。该helper仍只转调用真实ledger，没有重写验证算法或放松readiness。

角色降格原方法、原System32 DLL路径、单link事实及两个拒绝断言完全保留；直接admission调用同样传冻结私有批准集合及实际systemdir，避免测到缺参数而非真实角色约束。124方法集合不变，分布12/7/12/14/13/14/43/9；资产表为当前最终UTF-8/LF围栏字节。后续只更新本节元数据，不改任何TEST围栏。

完整工具`b780ae`：指定`/home/orbbec/icode-r2r3-env.DL2JQJ/bin/python`，真实`3.11.17 (main, Oct 9 2026, 15:21:28) [Clang 22.1.3]`；实际读取SOURCE DOC SHA256 `ea31789d28d7280730ee36ce7f5c8427e6a5f7ea807ac6f9376adab45bb9814d`，TEST运行前DOC SHA256 `a8a1c3305bce86ace8cad59c0e5e742ebaedc121b6cc018b7de1784fd278d5a8`。全124方法，124P/0F/0ERROR/0skip、真实总exit0；完整合并原输出26059 UTF-8字节SHA256 `8d9d5ffebe70d10dfee1a5f8eab5a646e68275ab08fab4d4d214683c455e5ff4`，无截断。root另工具`d04e27`亲核ea317与作者792535的七SOURCE围栏字节相同，并独立角色方法1P；该单方法不替代本次完整124P，仍按实际ea317记录运行绑定。

原f68的121方法14Assertion RED、原d65的角色降格两Assertion RED与全部fixture故障历史保留，不修改SOURCE来取绿、不删旧负控。当前正式缺SOURCE语义RED仍预期124 setUp Assertion FAIL、0P/0ERROR/0skip、exit1，尚未正式落TEST验证；先实际TEST-only及fresh双审，再不同作者SOURCE。DOC RAM124P不授正式TDD或任何Windows原生ABI/ACL/Job/DLL/loading/豁免恢复/consumer通路证明。

【架构级自检报告】语法/编译：8围栏实际compile，完整124P；依赖/调用链：真实Native/ledger及显式角色参数完整；逻辑/边界：124方法原语义不变、批准私有正控与System32降格负控均通过；异常处理：原有效RED和fixture ERROR分账保留；关联模块：唯一写原TEST DOC；兼容安全：未改SOURCE/core/实际TEST/Git/本机系统；可运行性：仅冻结软件诊断124P/exit0，正式TDD与Windows双平台原生/consumer门仍待执行，不宣称100%产品可运行。交root全文及fresh独立双审后再解冻后续阶段。

## fresh Windows SPEC：资源释放失败attempt-all及原body首因（127方法）

root确认同根I1后，仅新增3方法，所有原124方法和断言保留；当前分布12/7/14/14/13/14/44/9。先完整读原Win32.effective_access、verify_security、Native._canaries及现有底API模型，向独立SOURCE作者冻结异常合同：body原异常同一对象与args保留；每条cleanup失败通过BaseException.add_note添加`cleanup_unknown:`前缀及真实释放异常repr；body正常时必须抛实际cleanup错误而非返回成功。不增加账本字段/公共接口，未知释放状态不能报成功。

Win32新增2方法。effective_access实际GetSecurityInfo/OpenProcessToken/DuplicateToken/AccessCheck算法运行，底API维护分配/释放所有权集合：分别令322、321或700释放失败，body正常/底API抛预构造body Failure各一，共6subcase；断言全部[322,321,700]尝试，只有失败资源仍owned，原body对象不被cleanup错误覆盖且有cleanup_unknown notes。verify_security实际descriptor/security及ctypes owner/ACL算法运行，700或701的LocalFree失败×body正常/异常，共4subcase；两个SD皆需尝试释放，原body同对象/notes。拒绝double/unowned free，不只核mock调用次数。

Native新增1方法直接运行真实_canaries和真实Win32.close，仅最底CloseHandle注入token释放故障。duplicate/original token各失败一次，分别body正常、WriteFile body异常、RevertToSelf异常、WriteFile与Revert双异常，共8subcase；断言两个token释放皆被尝试、仅失败token仍owned、已Revert边界状态、原body同对象及notes。此为软件状态模型，不声称真实token已经释放或真实标准权限成立。

工具`d0d0e9`实际指定`/home/orbbec/icode-r2r3-env.DL2JQJ/bin/python`，打印`3.11.17 (main, Oct 9 2026, 15:21:28) [Clang 22.1.3]`；SOURCE DOC SHA256 `a8d439041767efd04b34caa3eff91664d2900912966fdca3b6688e685185060f`；TEST运行前DOC SHA256 `4975a1383e089b668300bc0686c5967f8333409073e533ea959a039d32bffd7b`。完整127方法，原124方法P、新3失败方法含18Assertion subfail，0ERROR/0skip，真实总exit1。原日志44523 UTF-8字节SHA256 `c0ea731450a732a0b06d8978cdc05a947b640bfe2d36349b98dc346d59a29054`。第一次外层工具JSON展示有截断，随后直接输出同一已保存完整原字符串，未重跑或修改结果；上述hash绑定完整原字符串。

有效失败包括：TEST Win32314行实际attempt[322]或[322,321]少后续资源；351行[700]缺701；原body被Failure('free_descriptor')覆盖；Native747行只attempt一个token，751行原body被Failure('close_handle')覆盖；body正常但最后释放失败时notes缺失。127缺SOURCE正式预期更新为127 Assertion FAIL/0P/0ERROR/0skip、exit1，仍非正式执行。本次取证后才通知独立SOURCE作者修原3处，无SOURCE修改或真实Windows/API/CLI。

【架构级自检报告】语法/编译：8围栏实际compile+AST；依赖/调用链：实际Win32/Native算法与底API资源表对齐；逻辑/边界：原124不变、新3覆盖首/中/尾释放失败与body/revert叠错；异常处理：18Assertion真实RED，首因及cleanupunknown合同明确；关联模块：唯一写原TEST DOC；兼容安全：不改SOURCE/core/实际TEST/Git/本机系统权限；可运行性：当前127实际exit1，等待独立SOURCE修复，不授GREEN/正式TDD/原生信用。

## 资源释放修订后最终127方法冻结

独立SOURCE作者收到上述有效原a8d RED后，仅修三处attempt-all/原body首因/cleanup_unknown notes。TEST作者完整读修订后的三方法，保持全部127方法围栏与原RED逐字不变，不通过改断言适配SOURCE取绿。实际运行前TEST DOC `981a3256d35c3acbe97962485589d7d52e1ab2ab4e5302b7eae459f13c1c1639`仅含比原4975更新的历史元数据；所有8围栏字节相同。

最终完整工具`41360f`：指定`/home/orbbec/icode-r2r3-env.DL2JQJ/bin/python`，真实打印`3.11.17 (main, Oct 9 2026, 15:21:28) [Clang 22.1.3]`。实际SOURCE DOC SHA256 `10a0712601320a1824ff0e387489d59ce05cd2de2393b1af9ba7f847c1995f85`，TEST运行前DOC同上述981a。全127方法，127P/0F/0ERROR/0skip，真实总exit0，完整合并原输出26736 UTF-8字节SHA256 `316d413278743e6cc55753e4944ee3469b5390e8cc76b284a6170a873d81a85d`，无截断。新3方法的18个原失败subcase均通过，全部旧124方法保持通过。

源码字节另工具`b5d064`核：Win32围栏461LF/24117字节SHA256 `29fb30b36df01544e709c2dba48cdd77efd24e8fd20cc98354e2038822d367c6`；Native围栏1336LF/84264字节SHA256 `e0c7cdeaf58b075bc779a944a2ef52c53cb15d105c0a2bb3f0dc26a23b0d1d02`，与作者修订后b046快照相同。作者确认之后仅SOURCE元数据变化；root工具`13c954`亦独立b046/TEST981a完整127P/0F/0ERROR/0skip/exit0。两次按各自真实DOC hash分账，不将元数据hash当作同一运行。

当前正式缺SOURCE预期仍为12/7/14/14/13/14/44/9，共127 Assertion FAIL、0P/0ERROR/0skip、exit1，尚未正式落TEST取证。以上仅DOC RAM诊断，不是正式TDD RED/GREEN，更不授实际Windows API/ABI/token/ACL/Job/DLL/豁免或精确恢复信用。原a8d有效18Assertion RED及更早全部历史保留。当前TEST围栏冻结，元数据完成后停止写本DOC，交root全文/fresh双审。

【架构级自检报告】语法/编译：8围栏实际compile/AST及完整127P；依赖/调用链：三修订真实算法、底API资源所有权模型与原链完整；逻辑/边界：所有旧124方法与新18subcase保留通过；异常处理：attempt-all、原body同对象、cleanup_unknown notes均软件验证；关联模块：唯一写原TEST DOC；兼容安全：未改SOURCE/core/实际TEST/Git/本机系统权限；可运行性：最终软件快照127P/exit0，正式TDD及Windows双平台/consumer全门未执行，不宣称100%产品可运行。

## 全owner同根QUALITY修订：最终146方法冻结

fresh Windows QUALITY发现同根资源owner遗漏后，root授权一次同scope补全，不再仅修三个方法。本轮只写本TEST DOC；保留原127个方法及原断言，新增19方法，当前八资产分布13/7/15/16/17/16/52/10，共146。现有有状态OS边界与真实ctypes内存继续复用；不新增生产模块/账本字段、全局测试框架或实际SOURCE/TEST，不执行Git/native/admin/安装/全量产品测试。root允许既有Win32模块窄私有_release_owned机制；测试不以直接测试该helper替代每个真实owner消费链。

| owner范围 | 实际执行及最底故障点 |
| --- | --- |
| Get._load | 真实绑定export body异常与FreeLibrary失败叠加，原AttributeError对象必须保留；collect沿原complete=False/计数/逐SID-array-library尝试合同，不改为异常API/不扩schema |
| Win32 | open_file、pin_ancestor、create_directory、set_root_dacl、sid_binary、assert_admin、verify_ancestor、observe_security、process_user分别到具体底API body，故障发生后才注入LocalFree/CloseHandle失败；配合原effective_access/verify_security三方法负控 |
| Store | __init__、create内file/外pins、flush/read/write、create_directory、close、copy_private_tree；首/中/尾释放故障代表、body成功/失败代表，真实Store方法不被FakeStore替换 |
| Jobs | 真实create_job的body+descriptor/job清理叠错；真实run_fixed body与terminate/wait-empty、attributeDelete、全部handle close、末Flush故障，继续attempt独立资源并保原异常/notes |
| Native复制 | _copy_file源/out、_source_tree实际调用copy_private_tree后的源目录pins及复读；pin获取后info失败也必须已登记为owned，不能在未登记窗口漏句柄 |
| Native进程 | attach_parent失败后的独立terminate/wait/reap与process/job关闭；verify_parent/stop_parent_job/reap_commands双handle、_process/_outer/parent_only单handle，不把close当已退出证明 |
| Native生命周期 | freeze/reopen/prepare的实际Store边界、prepare root DACL和socket bind/close、verify_store目录/冻结文件/shared-image重开、_tool、_derived、readonly_prepare、_canaries request/public文件；原_canaries token/Revert负控不删 |
| Admin与entry | 真实serve第二wait+cleanup双fail保原body，同时明确durable first_error本来已正确（不谎称账本丢首错）；真实recover finally Store.close；真实entry.main parent handle、outer cleanup及最终Store.close |

每个异常API负控检查原body同一对象（不是只比较文本）、原错误语义、cleanup_unknown notes、已拥有资源的独立attempt和真实模型副作用；body正常但释放失败必须非成功，不能关闭句柄即授OS回收。Native.freeze/reopen/prepare虽用已有NativeStore存储边界，实际Native方法及上下文/账号/路径门仍执行；Store本身另有真实算法负控。所有模型仅软件，不授Windows标准token/实际ACL/Job/native loading事实。

### 原949全批记录及fixture更正边界

原SOURCE DOC `949e38c22b613d7011525dcb737ffb863cbfdc87fddcc5386cd94e7d0902ce0e` / TEST `9338b38c8372e242aead54ae997c69433ee1bb5268ce3a78fc8d2fcc6b1c488c`实际146方法、80Assertion条目、0ERROR/0skip、exit1。该轮canary文件测试未normalize t.HANDLE，使两条失败先停在fixture计数，不能计为该owner有效SOURCE RED；修后改为真实token两次关闭再核原body。

后续同原949 / TEST `0ddd5c441d533f364ccbe3b5ea27b16314244104e3daaddb6fb39f40acf47d19`实际仍146方法、80Assertion条目、0ERROR/0skip、exit1；完整原合并输出54162 UTF-8字节SHA256 `057c1691de3933177a6dd96b58f12c6c92a621fe4f99cf35293a7fb9daca36e8`。此轮canary两条确切失败已变为原body对象被file-close异常覆盖。另root工具`72612c`独立同原949实际Store.copytree/create两方法10Assertion/0ERROR/0skip/exit1，确认source/pins未attempt、body覆盖、notes缺失因果；该局部不代替全owner计数。

但是0ddd轮加入的lifecycle三subcase以body.__traceback__非None当到达门，此判据后来证实错误：unittest.assertRaises会主动with_traceback(None)清掉原异常traceback。修后源码诊断工具`325262`的真实trace已观察freeze/reopen/prepare均抛指定body；测试最终改为底边界body_entered事件并保留同对象断言。另外prepare.root-close注入过早打中reopen内部验证的close，最终限定只有DACL body已发生后才释放失败。因此不得把原949的80条全部归为最终夹具逐owner有效RED，不得把最终修正TEST与原949宣称同字节复跑；原949全文未保存为可直接复用RAM对象，按root要求没有逆patch重构或追认。其他已亲核实际资源泄漏/原body覆盖因果保留，fixture失败明确分账。

### 修后夹具同步及最终完整软件诊断

修后SOURCE首次attempt-all会在Terminate失败后继续独立wait_empty；原故障组合沿用固定monotonic，无法模拟真实deadline，session15097已明确中断（exit1，无完整case结果，不计SOURCE失败）。最终仅这类故障路径加有限递进clock，不放松任何回收/首错断言。第一次有限钟轮绑定SOURCE `6e6cf3d1f89710879758cbe8eed67c5885416676e1f39fb8b53d1fd5d9e5b0ae` / TEST `ecc286047253836843b640c191aa290d3294e75b0c5cca0c72e9c272cb475163`，实际146方法、5Assertion/9ERROR/0skip、exit1：entry局部sys facade缺新增sys.exception；旧Store.close故障fixture注入RuntimeError与原assertRaisesFailure不匹配；上述traceback guard和root-close时机有误。均为fixture问题，不计新SOURCE缺陷。

合法同步措施仅为：entry局部sys.exception委托真实解释器方法、不改全局sys；旧Store.close仍保原assertRaisesFailure，底close改注入Failure从而同原首cleanup异常合同一致；lifecycle采用明确body_entered事件；root-close仅body发生后失败；递进monotonic让真实wait_empty有界。原19新增方法、全部原127方法及原断言语义均保留，不通过noop ledger/ready/OS事实或删除负控取绿。

同修正TEST `3d4e199674e6c15335a5f212163e8bf4a3e25cf9b7bd04536fc1b6b8940d0e42` / SOURCE `6aec8c8849557f67d6ee85ff5e5f400d246d70b8081f6e1eaa6ee992e1454732`（作者确认仅比6e6cf更新metadata），session97054完整完成：146P/0F/0ERROR/0skip、exit0，10.183s，首段`a09f98`及终段`505e3e`拼接完整952 UTF-8字节SHA256 `44c04c9726de24993dce8b0aaf257a6c3e5b172fb010ba0a881195429e87f6a6`。

独立SOURCE作者最后将既有三个“立即释放”LocalFree路径改为同scope notes合同（open_file/create_job转交前、_abi descriptor），测试未再增场景或改围栏。完整读修订后最终工具`366afa`：指定`/home/orbbec/icode-r2r3-env.DL2JQJ/bin/python`，真实打印`3.11.17 (main, Oct 9 2026, 15:21:28) [Clang 22.1.3]`；实际SOURCE DOC SHA256 `10e1bedb316bc84b22f6705dc393791bbd1ed2be3265916464da1a059f640ba2` / TEST运行前DOC SHA256 `3d4e199674e6c15335a5f212163e8bf4a3e25cf9b7bd04536fc1b6b8940d0e42`。全146方法，146P/0F/0ERROR/0skip、真实exit0，11.800s；完整原合并输出952 UTF-8字节SHA256 `2e236cf90fd8ef275b698768a3657f0428db9c3bfc90d50cd1342c4258ed321d`，无截断（verbosity=0，含argparse预期负控usage，不是额外ERROR）。root工具`2452a1`独立同快照亦完整146P/0F/0ERROR/0skip/exit0。

当时146版八围栏字节与3d4e运行快照完全不变；该节资产表元数据更新使DOC整体hash改变。后续152版已修改Native TEST围栏，不继承这句同字节声明。RAM只执行七Python SOURCE投影（Win32→Store→Jobs→Getworker→Native→Admin→entry），C/CMake两个资产不执行；TEST加载binding先于其余引用者，运行全部八模块并累计failure/error/skip决定原exit1/0，未落投影文件。精确完整harness已通过协作消息交root，无新的harness文件/工具安装。

历史146版缺SOURCE预期13/7/15/16/17/16/52/10，共146 setUp Assertion FAIL、0P/0ERROR/0skip、exit1；仍须未来实际TEST-only取证，当前不是正式TDD。历史原RED与最终fixture并非同字节，不能写成正式RED→GREEN；146P仅软件RAM诊断，不授Windows SDK ABI、真实ACL/Job/loading/豁免恢复/consumer接线或产品完成。

### attach_parent 生命周期模型纠正与原件 RED／修后 GREEN（当前152方法）

此前146P的attach故障替身曾将TerminateJob无条件视为杀死parent，未按实际成员关系区分认证失败与未入Job；该历史通过不证明这两种安全边界。此次保留原146方法与断言，只有该底API模型恢复真实成员语义，新增6个真实Native.attach_parent方法。IsProcessInJob只在assigned首次正常验证位置注入body异常，恢复查询按实际成员返回；模型明确区分未认证、已认证未入组、已入组、Assign失败已退出、以及已转交Store后的所有权。creation读取失败、0、bool、2^64均不授终止资格；终止失败/等待失败/两个close失败须独立attempt且保原body对象与cleanup_unknown notes。

原件SOURCE完整SHA256 `26dfbd2748e47a193bb8bd4b9eb4c9703c0d9d087200848ae8eabb7b1739ed40`；同修正TEST运行快照 `7cdac7a19acb967dd9334359c747697c6b580bbf05270d64b51e9d98a704d1bd`。工具`e29884`使用指定3.11.17解释器，完整152方法，11个语义Assertion失败、0ERROR、0skip，真实exit1，10.267s。原146方法全P；新增assigned实际成员与transfer后Store持有/close正控P；未认证8subcases、未入组仍alive、多清理失败未attempt直接回收、已退出仍盲终止共11F。完整合并原输出40920 UTF-8字节SHA256 `33383fe39f4750bd064811174525f157ad9f9e5fdf3249095a71e59edef78565`，RAM原输出完整保留；展示截断不改变该原件摘要。前一中间TEST4fff14的5方法7Assertion记录及9029cdb的151方法8Assertion记录不冒充此最终修正快照。

当前模块方法数13/7/15/16/17/16/58/10，总152；不同SOURCE作者局部修订后，工具`b0f335`对SOURCE `c35d140264186a3a1d47ece71a49c6cf86484fe56f1ab4e6d028995be8bede86` / TEST运行DOC `3c0bd0d314d5b5de896851f5150a27f076370985f5a3fed80da34eae3e16f890`完成同围栏完整回归：明确3.11.17、152P/0F/0ERROR/0skip、真实exit0、11.931s。完整原合并输出952 UTF-8字节SHA256 `425bf66533047268f45486ed05f13c2a01aefd528d79e698b9abd480a09c6952`。TEST代码与原26dfbd/7cdac7a的152方法11Assertion RED完全同字节，只有元数据改变；这仍仅为软件RAM诊断，不是正式TDD或native信用，也未落实际TEST/SOURCE。当前缺SOURCE预计152 setUp Assertion FAIL/0P/0ERROR/0skip/exit1，未来仍须实际TEST-only取证。

【架构级自检报告】语法/编译：8围栏真实compile/AST及最终152P；依赖/调用链：所有新增owner都调用真实方法，复用底API/持久字节模型；逻辑/边界：原127方法保留，逐owner故障及未知非成功合同明确；异常处理：旧RED与修正fixture不追认、所有实际ERROR/中断/退出均分账；关联模块：唯一写原TEST DOC；兼容安全：未改SOURCE/core/实际TEST/Git/ICODE-SKILL/本机系统权限；可运行性：只授绑定最终快照152P/exit0的软件信用，正式TDD与双Windows/native/consumer全门未执行，不宣称100%产品可运行。
