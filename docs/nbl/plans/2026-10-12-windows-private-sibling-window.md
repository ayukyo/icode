# Windows 私有 sibling 创建三窗实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `nbl.superpowers:nbl.subagent-driven-development` to execute this serial plan, with one implementation writer per stage. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在私有 parent 下观测四个 route/kind 变体的真实 sibling 创建，分别给出 unpinned/pinned/released 三窗回执。观测不授 security、consumer、launch、UAC、R2/R3 信用。

**Architecture:** 新增两个测试文件，复用原 `_Fixture('parent','new')` 的 prepare/observer/pin/base cleanup；新的 codec、native acquisition、sampler 和三窗 controller 都在 `tests/windows_private_sibling_fixture.py` 内。所有 children 由外层持有，先逆序一次关闭和精确删除，再 base.close。新 scope 独立，不改原 fixture 或生产 backend/validator。

**Tech Stack:** Python 3.11/3.12、stdlib unittest/ctypes/json、Windows NTFS、现有 metadata/OA/IOSB/security reader/primary-token capture；无新增依赖、vendor 源码或 workflow 权限。

**Execution Mode:** serial，采用 `nbl.superpowers:nbl.subagent-driven-development`，每阶段一个实施writer；main-only不要求root亲自写全部阶段。研究与复审为只读；本文本身不执行源码落地、Git 写、CI 写或重守护。

**Dependencies:** 冻结 [设计](../specs/2026-10-12-windows-private-sibling-window-design.md) 的完整 protocol/lifecycle/budget；实际基础fixture基线 `8b1afd4`，文档基线 `e72c229`。本计划最终SPEC→不同QUALITY均C0/I0/M0，允许进入分Task单写者TDD；设计若改变先回到同一门。Linux独立片已发布f648812，不改变本片基础fixture或生产后端。

**Parallelizable:** 仅独立只读上游调研、SPEC/QUALITY 复审可并行；Task 1–5 源码写入串行、每阶段唯一writer。不要用子 agent 同时写共享 fixture/test 文件。

实际必需 selector 是 **`scripts/run_workspace_ci.py`**，不存在 `scripts/run_windows_workspace_ci.py`。接线沿用 `startup_pin_tests(platform)` 和 `main()` 的 required prefix，不创建替代脚本。实际 guard 是 `tests/test_windows_startup_pin_ci.py`；原 portable 31 类、native 4 类，原 counts 保留。

## Task 1：独立 scope codec，先验证失败断言

Files: Create `tests/windows_private_sibling_fixture.py`; Create `tests/test_windows_private_sibling_window.py`。Dependencies: 冻结SPEC与计划SPEC→不同QUALITY；Parallelizable: 否，共享两个新增文件。

- [x] 完整重读 spec 与上述 actual 源文件；核对三问已确认。入口只接受 exact route/kind 枚举；invalid/non-Windows 必须在 native loader、token capture、临时目录之前拒绝。
- [x] 先加入后文 portable class 的 codec/entrypoint 测试。新模块缺失阶段仅是脚手架失败，不算有效 RED；最小导入骨架就绪后，取得断言失败的 RED，并记录实际命令/输出。
- [x] 使用下面完整可导入fixture骨架，只定义待实现的codec/入口；portable test文件先加入完整共享imports/class及receipt helper，然后**仅加入**Task1的前四个方法。Task1未使用的 `_Harness` 留到Task2获取测试再加入。`python -m unittest`在模块/方法加载正常之后必须由这些断言失败，而不是ImportError。

```python
import json
import os

_PHASES = ('unpinned', 'pinned', 'released')
_ROUTES, _KINDS = ('win32', 'nt_relative'), ('file', 'directory')


def _encode(data):
    return (json.dumps(data, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=True).encode('ascii') + b'\n')


def validate_wire(wire):
    return {}


def run_variant(route, kind):
    return b'{}\n'
```

- [x] Task1明确RED命令：`.venv/bin/python -m unittest tests.test_windows_private_sibling_window.PrivateSiblingPortableTests.test_wire_all_route_kind_and_effect_combinations tests.test_windows_private_sibling_window.PrivateSiblingPortableTests.test_entry_rejects_before_loader`。骨架无`_Fixture`时entry测试的patch必须使用`create=True`；不以patch缺属性错误授RED。codec骨架返回`{}`与真实期望对象的`assertEqual`失败，入口骨架返回bytes导致`assertRaises`失败；阶段期望**2 run/2 assertion FAIL/0 ERROR**。GREEN后再加入剩余codec负例。
- [x] 实现下列 codec block；不引用旧 DACL validator。`_StageFailure` 只接收内部 whitelist stage，failure_message 不读任意异常属性。

```python
"""CI-only sibling creation observation; never a launch/security authority."""
import ctypes
import json
import os

from tests.windows_private_dacl_fixture import (
    _Fixture, _ConvertedDacl, _CONTENT, _marker, _stable,
)
from icode.windows_startup_native import (
    _INFO_CLASSES, _UNICODE_STRING, _OBJECT_ATTRIBUTES, _IO_STATUS_BLOCK,
)
from icode.windows_startup_pin import StartupFileMetadata, _metadata

_U32, _I32, _VOID = ctypes.c_uint32, ctypes.c_int32, ctypes.c_void_p
_INVALID = _VOID(-1).value
_DENIED = frozenset((5, 32, 33))
_NT_DENIED = frozenset((0xC0000022, 0xC0000043, 0xC0000054))
_PHASES = ('unpinned', 'pinned', 'released')
_ROUTES, _KINDS = ('win32', 'nt_relative'), ('file', 'directory')
_FAILURE = 'private_sibling_window_failed'
_STAGES = frozenset((
    'fixture', 'prepare', 'child_sd', 'initial', 'start_pin', 'release_pin',
    'cleanup', 'wire',
) + tuple(phase + '_' + step for phase in _PHASES
          for step in ('before', 'direct_add', 'create', 'after', 'child')))


class _StageFailure(RuntimeError):
    pass


def failure_message(error):
    if type(error) is _StageFailure:
        args = error.args
        if (type(args) is tuple and len(args) == 1
                and type(args[0]) is str and args[0] in _STAGES):
            return _FAILURE + ':' + args[0]
    return _FAILURE


def _require(condition):
    if not condition:
        raise ValueError('invalid_private_sibling_receipt')


def _object(value, keys):
    _require(type(value) is dict and value.keys() == keys)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _encode(data):
    return (json.dumps(data, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=True).encode('ascii') + b'\n')


def validate_wire(wire):
    try:
        _require(type(wire) is bytes and 1 <= len(wire) <= 8192)
        data = json.loads(wire.decode('ascii', 'strict'), object_pairs_hook=_unique)
        _require(_encode(data) == wire)
        _object(data, {'scope', 'schema_version', 'route', 'kind', 'windows',
                       'cleanup_confirmed', 'consumer_ready',
                       'compatibility_accepted', 'launch_authorized'})
        _require(type(data['scope']) is str
                 and data['scope'] == 'private_sibling_window_observation')
        _require(type(data['schema_version']) is int and data['schema_version'] == 1)
        _require(type(data['route']) is str and data['route'] in _ROUTES)
        _require(type(data['kind']) is str and data['kind'] in _KINDS)
        _require(data['cleanup_confirmed'] is True)
        for field in ('consumer_ready', 'compatibility_accepted', 'launch_authorized'):
            _require(data[field] is False)
        windows = data['windows']
        _require(type(windows) is list and len(windows) == 3)
        for event, phase in zip(windows, _PHASES):
            _object(event, {'window', 'direct_add', 'create', 'effect',
                            'parent_metadata_changed', 'leaf_metadata_changed',
                            'identity_stable', 'bytes_stable',
                            'parent_sd_stable', 'leaf_sd_stable', 'child'})
            _require(type(event['window']) is str and event['window'] == phase)
            for field in ('identity_stable', 'bytes_stable',
                          'parent_sd_stable', 'leaf_sd_stable'):
                _require(event[field] is True)
            for field in ('parent_metadata_changed', 'leaf_metadata_changed'):
                _require(type(event[field]) is bool)
            _object(event['direct_add'], {'access', 'result'})
            _require(type(event['direct_add']['access']) is int
                     and event['direct_add']['access'] == (2 if data['kind'] == 'file' else 4))
            _require(type(event['direct_add']['result']) is int
                     and event['direct_add']['result'] in ({0} | _DENIED))
            effect = event['effect']
            _require(type(effect) is str and effect in ('created', 'blocked'))
            _require(phase == 'pinned' or effect == 'created')
            created = effect == 'created'
            native = event['create']
            if data['route'] == 'win32':
                _object(native, {'result'})
                _require(type(native['result']) is int)
                _require(native['result'] == 0 if created else native['result'] in _DENIED)
            else:
                _object(native, {'return_u32', 'iosb'} if created else {'return_u32'})
                _require(type(native['return_u32']) is int)
                if created:
                    _require(native['return_u32'] == 0)
                    _object(native['iosb'], {'status_u32', 'information'})
                    _require(type(native['iosb']['status_u32']) is int
                             and native['iosb']['status_u32'] == 0)
                    _require(type(native['iosb']['information']) is int
                             and native['iosb']['information'] == 2)
                else:
                    _require(native['return_u32'] in _NT_DENIED)
            if created:
                child = event['child']
                _object(child, {'identity_distinct', 'volume_matches', 'kind_matches',
                                'nonreparse', 'not_delete_pending', 'protected',
                                'template_verified', 'empty_file'})
                for field in child.keys() - {'empty_file'}:
                    _require(child[field] is True)
                _require(child['empty_file'] is (True if data['kind'] == 'file' else None))
            else:
                _require(event['child'] is None)
        return data
    except Exception:
        raise ValueError('invalid_private_sibling_receipt') from None
```

- [x] codec 的 exact str/int/bool、duplicate key、canonical ASCII/LF、跨 route effect、两个正控全部 GREEN。不要把 json parser 可接受当合法 wire。

Task1 实施记录（2026-10-11 UTC）：唯一writer报告最小可导入骨架下两个选定codec/入口方法实际2 run/2 assertion FAIL/0 ERROR；实现后完整4方法GREEN，旧DACL transport加新测试共9方法通过。root完整回读119行fixture与132行test，并独立执行 `.venv/bin/python -B -m unittest tests.test_windows_private_sibling_window -q`，4 run/0 FAIL/ERROR/skip。该历史RED由writer实测，root未重新撤回实现复跑，不记root RED信用。fixture SHA256 `a381faf4ae79f9c2f61e57b16216faacdfd350eaa1a4943c30ead9c370368229`；test SHA256 `04817495e01e47b79b73b9c658994d5a9d5309c2546684dc50b72d054f10750c`。fresh CODE SPEC与不同QUALITY均C0/I0/M0，分别独立运行四方法及纯Python边界补测。合法Windows入口仍固定fail-closed，尚未实现controller；没有Task2/3/4、原生Windows、172预算、完整守护或R2/R3通过信用。Task2开始后这两个hash只绑定Task1历史候选。

## Task 2：native ABI、局部 acquisition 与 ownership

Files: Modify 新 fixture；Modify 新 test。Dependencies: Task 1；Parallelizable: 否，共享fixture/test。

Task2 实施状态：已完成局部acquisition软件片，fresh CODE SPEC→不同QUALITY各C0/I0/M0。唯一writer在最小create blocked骨架下执行选定Win32创建方法，实际1 run/1 assertion FAIL/0ERROR；随后五方法GREEN和全九方法GREEN。root完整回读实际329行fixture/394行test并独立全9方法0FAIL/ERROR/skip；两审查者各独立全9及纯Python补测。最终fixture SHA256 `1498f12e2dd6b2cbcf88623e33f0a091c539e894a943631f02c179cfa815b879`，test SHA256 `a3962f7bd093987bb63c4efa6916a2604d86bcc20ac56f6746e85c6f05d33d71`；历史RED骨架fixture `0f4624385c57815683f4fa7a36facad93dc95c3cba80701220e1f485575e345f`、test `ec5215f59771fcd86d9c8065b4cd956f5a0466dbe2924554c926ca7ec360f018`由writer实测，root未撤回实现复跑。compileall-j1通过。剩余controller/采样/删除/实际create RETURN-event与原生证据仍未实施；此记录只绑定Task2候选，不提前授Task3或172预算信用。下面checkbox保留具体合同核验清单，进入Task3前两轮实际核验已覆盖Task2各项。

- [x] 先写真实 native acquisition helper 的 ctypes fake 测试；direct ADD 失败仍必须调用 create；取得后注册前异常必须在 acquisition 同一 try 内收尾，不使用 generic `_call`/`_at_stage` 包 native create。
- [x] Task2先加入Task4完整文本中的`test_native_abi_and_full_sd`、`test_win32_creation_and_directory_witness`、`test_nt_success_and_failure_outputs`、`test_acquisition_registration_return_interrupts`、`test_unknown_outputs_and_known_owner_collision`五个完整方法。它们此阶段只调用实际`_Creation`与ledger，不依赖Task3的`_run_variant`；真实owner转换指针与directory witness失败后的全局删除子例已移动到Task3的controller/cleanup方法，Task3追加这些方法时再纳入。先使下列完整`_Slot`/`_Ledger`/`_Creation`可导入，并将`create()`方法体暂时替换为完整一行`return 'blocked', {'result': 5}`；执行 `.venv/bin/python -m unittest tests.test_windows_private_sibling_window.PrivateSiblingPortableTests.test_win32_creation_and_directory_witness`，实际进入helper后由created结果断言失败，阶段期望**1 run/1 assertion FAIL/0 ERROR**。
- [x] Task2替换回下列最终native代码后的明确GREEN命令：`.venv/bin/python -m unittest tests.test_windows_private_sibling_window.PrivateSiblingPortableTests.test_native_abi_and_full_sd tests.test_windows_private_sibling_window.PrivateSiblingPortableTests.test_win32_creation_and_directory_witness tests.test_windows_private_sibling_window.PrivateSiblingPortableTests.test_nt_success_and_failure_outputs tests.test_windows_private_sibling_window.PrivateSiblingPortableTests.test_acquisition_registration_return_interrupts tests.test_windows_private_sibling_window.PrivateSiblingPortableTests.test_unknown_outputs_and_known_owner_collision`；阶段期望**5 run/0 FAIL/0 ERROR**。trace矩阵不留到Task4第一次写，也不提前引入Task3controller。
- [x] 加入下列 block。`_Ledger` 仅跟踪本片 child/ADD acquisition 与当前真实 base observer/pin；active/unknown 裸值阻断，新一次实际 acquisition 可复用已 confirmed-close 的数值作为新代次。旧 owner once-close 状态不复活。旧base未保存 prepare 临时 HANDLE 历史，不伪造其 ledger；生产backend内部retired规则不改。此澄清已重新SPEC→不同QUALITY C0/I0/M0。

```python
class _SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [('nLength', _U32), ('lpSecurityDescriptor', _VOID),
                ('bInheritHandle', _I32)]


def _valid_handle(value):
    return type(value) is int and 0 < value < _INVALID


def _choose(first, error):
    if first is None:
        return error
    if isinstance(first, (KeyboardInterrupt, SystemExit)):
        return first
    if isinstance(error, (KeyboardInterrupt, SystemExit)):
        return error
    return first


class _Slot:
    def __init__(self, path, directory):
        self.path, self.directory = path, directory
        self.owned_path = False
        self.handle = None
        self.close_attempted = self.close_confirmed = False
        self.remove_attempted = self.remove_confirmed = False


class _Ledger:
    def __init__(self, base):
        self.base = base
        self.active, self.retired, self.unknown = set(), set(), set()

    def known(self):
        values = self.active | self.unknown
        observer = self.base.observer
        if observer is not None:
            values |= {owner.value for owner in observer.handles.values()}
        if self.base.pin is not None:
            values |= set(self.base.pin._handles)
            backend = self.base.pin._backend
            values |= set(getattr(backend, '_unknown', ()))
        return values

    def claim(self, slot, handle):
        if not _valid_handle(handle) or handle in self.known():
            raise RuntimeError(_FAILURE)
        slot.handle = handle
        self.active.add(handle)

    def recover(self, slot, handle):
        # A collision is an existing owner, never this acquisition's resource.
        if slot.handle is None and _valid_handle(handle) and handle not in self.known():
            slot.handle = handle
            self.active.add(handle)

    def close(self, slot):
        if slot.close_attempted:
            if not slot.close_confirmed:
                raise RuntimeError(_FAILURE)
            return
        slot.close_attempted = True
        if slot.handle is None:
            slot.close_confirmed = True
            return
        value = slot.handle
        self.active.discard(value)
        self.retired.add(value)
        try:
            result = self.base.api.kernel.CloseHandle(value)
            if type(result) is not int or result == 0:
                raise RuntimeError(_FAILURE)
            slot.close_confirmed = True
        except BaseException:
            self.unknown.add(value)
            raise


class _Creation:
    def __init__(self, base, ledger):
        self.base, self.ledger = base, ledger
        self.kernel = base.api.kernel
        self.kernel.CreateDirectoryW.argtypes = [ctypes.c_wchar_p, _VOID]
        self.kernel.CreateDirectoryW.restype = _I32
        self.ntdll = ctypes.WinDLL('ntdll')
        self.ntdll.NtCreateFile.argtypes = [
            ctypes.POINTER(_VOID), _U32, ctypes.POINTER(_OBJECT_ATTRIBUTES),
            ctypes.POINTER(_IO_STATUS_BLOCK), _VOID, _U32, _U32, _U32, _U32, _VOID, _U32,
        ]
        self.ntdll.NtCreateFile.restype = _I32

    def direct_add(self, kind):
        slot = _Slot(None, True)
        value = None
        try:
            value = self.kernel.CreateFileW(self.base.parent, 2 if kind == 'file' else 4,
                7, None, 3, 0x2200000, None)
            if value == _INVALID:
                code = ctypes.get_last_error()
                if type(code) is not int or code not in _DENIED:
                    raise RuntimeError(_FAILURE)
                return code
            self.ledger.claim(slot, value)
            self.ledger.close(slot)
            return 0
        except BaseException as original:
            try:
                self.ledger.recover(slot, value)
                self.ledger.close(slot)
            except BaseException as cleanup:
                selected = _choose(original, cleanup)
                if selected is not original:
                    raise selected
            raise

    def create(self, route, kind, phase, full_sd, root, slot):
        # Buffers, output containers, result and exact path exist before acquire.
        sa = _SECURITY_ATTRIBUTES(ctypes.sizeof(_SECURITY_ATTRIBUTES), full_sd, 0)
        output, ios = _VOID(), _IO_STATUS_BLOCK()
        basename = 'sibling-' + phase
        encoded = basename.encode('utf-16-le', 'strict')
        if not encoded or len(encoded) + 2 > 65535:
            raise RuntimeError(_FAILURE)
        buffer = ctypes.create_string_buffer(encoded + b'\0\0')
        name = _UNICODE_STRING(len(encoded), len(encoded) + 2, ctypes.addressof(buffer))
        oa = _OBJECT_ATTRIBUTES(ctypes.sizeof(_OBJECT_ATTRIBUTES), root,
            ctypes.pointer(name), 0x1040, full_sd, None)
        result, value = None, None
        confirmed_create = False
        try:
            if route == 'nt_relative':
                result = self.ntdll.NtCreateFile(ctypes.byref(output), 0x120081,
                    ctypes.byref(oa), ctypes.byref(ios), None, 0, 7, 2,
                    0x200020 | (1 if kind == 'directory' else 0x40), None, 0)
                value = output.value
                if type(result) is not int or not -(2**31) <= result < 2**31:
                    raise RuntimeError(_FAILURE)
                unsigned = result & 0xffffffff
                if result != 0:
                    if value is not None or unsigned not in _NT_DENIED:
                        raise RuntimeError(_FAILURE)
                    # Non-pending failure IOSB is not a return-value authority.
                    return 'blocked', {'return_u32': unsigned}
                confirmed_create = ios.u.Status == 0 and ios.Information == 2
                if not confirmed_create:
                    raise RuntimeError(_FAILURE)
                self.ledger.claim(slot, value)
                slot.owned_path = True
                return 'created', {'return_u32': unsigned, 'iosb': {
                    'status_u32': ios.u.Status & 0xffffffff, 'information': ios.Information}}
            if kind == 'directory':
                result = self.kernel.CreateDirectoryW(slot.path, ctypes.byref(sa))
                if type(result) is not int:
                    raise RuntimeError(_FAILURE)
                if result == 0:
                    code = ctypes.get_last_error()
                    if type(code) is not int or code not in _DENIED:
                        raise RuntimeError(_FAILURE)
                    return 'blocked', {'result': code}
                confirmed_create = True
                slot.owned_path = True
                value = self.kernel.CreateFileW(slot.path, 0x120081, 7, None, 3, 0x2200000, None)
                self.ledger.claim(slot, value)
            else:
                result = self.kernel.CreateFileW(slot.path, 0x120081, 7,
                    ctypes.byref(sa), 1, 0x200000, None)
                value = result
                if value == _INVALID:
                    code = ctypes.get_last_error()
                    if type(code) is not int or code not in _DENIED:
                        raise RuntimeError(_FAILURE)
                    return 'blocked', {'result': code}
                # Valid CREATE_NEW result proves pathname creation, but a known
                # numeric owner collision still makes this observation fail.
                confirmed_create = _valid_handle(value) and value not in self.ledger.known()
                self.ledger.claim(slot, value)
                slot.owned_path = True
            return 'created', {'result': 0}
        except BaseException as original:
            # Re-read direct native output; unknown status never authorizes path removal.
            if route == 'nt_relative':
                value = output.value
                confirmed_create = (type(result) is int and result == 0
                                    and ios.u.Status == 0 and ios.Information == 2
                                    and _valid_handle(value)
                                    and (value == slot.handle or value not in self.ledger.known()))
            elif kind == 'directory':
                confirmed_create = type(result) is int and result != 0
            else:
                # Interrupt may arrive after result was stored but before
                # the separate value assignment; recover the native result.
                value = result
                confirmed_create = (_valid_handle(result)
                                    and (result == slot.handle or result not in self.ledger.known()))
            if confirmed_create:
                slot.owned_path = True
            try:
                self.ledger.recover(slot, value)
                self.ledger.close(slot)
            except BaseException as cleanup:
                selected = _choose(original, cleanup)
                if selected is not original:
                    raise selected
            raise
```

- [x] 复核 ctypes 使用 actual production OA/IOSB/UNICODE_STRING，`restype=c_int32`，full SD 是 `_ConvertedDacl.output.value`，不是 acquire 返回的 interior DACL。SA BOOL/DWORD 显式 32 bit、SD 生命周期跨全部 create。
- [x] Nt success 四条件齐全；仅实际 failure return 三码 blocked，无 failure IOSB 字段；pending/warning/non-created/partial/collision 都 FAIL。Nt directory options 和 desired access 不降级、不删 flag，不加 fallback/skip。

## Task 3：实时双对象 sampler、child 专用 validator、三窗 controller

Files: Modify 新 fixture；Modify 新 test。Dependencies: Task 2；Parallelizable: 否，共享fixture/test。

Task3 实施状态：已完成软件片，fresh实际CODE SPEC→不同QUALITY各C0/I0/M0，root全文回读605行fixture/795行test并独立18方法通过。唯一writer先在合法wire controller骨架取得1 run/1 assertion FAIL/0ERROR（真实create数0而预期3），再实现真实controller；自审另发现示例公开入口仅按异常type转发会泄漏非法stage，新增同方法负控取得1 run/1 assertion FAIL/0ERROR，再改有限白名单后18GREEN。两个RED均由writer实测，不借计划演练或由root撤回实现认证。冻结fixture SHA256 `11a8c7d49a4bb200644683d26e54cd3ea4d835bf02b69b088bbe195bcb0834e0`、test `2ec9def1ff80e6b6cd553f6f9f4f0c81c477e5bc97f0eb48ba34516bad9dbb10`，只绑定此历史候选。四变体真正create RETURN-event的KI/SE八例已走outer cleanup；fake24 HANDLE/68 reader callbacks/12 conversion-free与静态80/172明确分账，原生未验。Task1有效Windows入口“controller尚未实现”的临时断言改为受控普通错误/信号边界，非法前拒加强保留，没有在portable里真实执行native。下列公开入口示例已同步实际白名单修复；另设计表格仅转义竖线以修正Markdown列数，API flags不变。

- [x] 先测首 unpinned-before 的双 SD raw baseline，leaf 必须与 base.initial.raw 匹配。禁止声称 base.prepare 保存 parent raw，禁止额外 prepin SD sample。
- [x] Task3先加入剩余sampler/controller/child/cleanup/预算方法（不再首次编写Task2 native故障方法）。将下面完整临时`_run_variant`骨架与其它可导入helper写入后，执行 `.venv/bin/python -m unittest tests.test_windows_private_sibling_window.PrivateSiblingPortableTests.test_controller_windows_pin_and_retention`，回执合法但actual `h.log`create计数0导致断言RED。再替换为本Task最终真实controller并GREEN。每个RED保存实际selected命令、断言和调用证据；不得导入测试class形成循环依赖。

```python
def _run_variant(route, kind):
    child = dict.fromkeys(('identity_distinct', 'volume_matches', 'kind_matches',
        'nonreparse', 'not_delete_pending', 'protected', 'template_verified'), True)
    child['empty_file'] = True if kind == 'file' else None
    native = ({'result': 0} if route == 'win32' else
              {'return_u32': 0, 'iosb': {'status_u32': 0, 'information': 2}})
    windows = [{'window': phase, 'direct_add': {
        'access': 2 if kind == 'file' else 4, 'result': 0}, 'create': native,
        'effect': 'created', 'parent_metadata_changed': False,
        'leaf_metadata_changed': False, 'identity_stable': True, 'bytes_stable': True,
        'parent_sd_stable': True, 'leaf_sd_stable': True, 'child': child}
        for phase in _PHASES]
    return _encode({'scope': 'private_sibling_window_observation', 'schema_version': 1,
        'route': route, 'kind': kind, 'windows': windows, 'cleanup_confirmed': True,
        'consumer_ready': False, 'compatibility_accepted': False, 'launch_authorized': False})
```
- [x] 加入下列 block。query 只查已持有 HANDLE；新 file 的零 bytes 规则在这里独立验证，不修改生产 `_metadata` 非空门。pin 原 HANDLE 只 borrow，不插到 backend `_active`。

```python
def _query(api, handle, directory):
    file_type = api.kernel.GetFileType(handle)
    if type(file_type) is not int or file_type != 1:
        raise RuntimeError(_FAILURE)
    values = {}
    for info, structure in _INFO_CLASSES.items():
        value = structure()
        result = api.kernel.GetFileInformationByHandleEx(handle, info,
            ctypes.byref(value), ctypes.sizeof(value))
        if type(result) is not int or result == 0:
            raise RuntimeError(_FAILURE)
        values[info] = value
    basic, standard, tag, identity = (values[key] for key in (0, 1, 9, 18))
    if (basic.FileAttributes != tag.FileAttributes or tag.ReparseTag
            or standard.Directory not in (0, 1) or standard.DeletePending not in (0, 1)
            or bool(basic.FileAttributes & 0x10) != bool(standard.Directory)):
        raise RuntimeError(_FAILURE)
    return StartupFileMetadata(identity.VolumeSerialNumber, bytes(identity.FileId),
        bool(standard.Directory), bool(basic.FileAttributes & 0x400),
        bool(standard.DeletePending), 'disk', standard.NumberOfLinks,
        standard.EndOfFile, basic.ChangeTime)


def _child_metadata(meta, directory):
    if type(meta) is not StartupFileMetadata or type(directory) is not bool:
        raise RuntimeError(_FAILURE)
    for field, low, high in (
        ('volume_serial', 0, 2**64 - 1), ('links', 0, 2**32 - 1),
        ('size', 0, 2**63 - 1), ('change_time', -(2**63), 2**63 - 1),
    ):
        value = getattr(meta, field)
        if type(value) is not int or not low <= value <= high:
            raise RuntimeError(_FAILURE)
    if (type(meta.file_id) is not bytes or len(meta.file_id) != 16
            or any(type(getattr(meta, field)) is not bool
                   for field in ('directory', 'reparse', 'delete_pending'))
            or type(meta.file_type) is not str or meta.file_type != 'disk'
            or meta.directory is not directory or meta.reparse or meta.delete_pending
            or (not directory and (meta.links != 1 or meta.size != 0))):
        raise RuntimeError(_FAILURE)
    return meta


def _identity(meta):
    return meta.volume_serial, meta.file_id, meta.directory, meta.file_type


class _Observation:
    def __init__(self, base):
        self.base = base
        self.raw_baseline = None
        self.child_ids = set()

    def sample(self, phase):
        base = self.base
        if phase == 'pinned':
            pin = base.pin
            pin._require_open()
            if not 2 <= len(pin._handles) <= 32:
                raise RuntimeError(_FAILURE)
            parent_handle, leaf_handle = pin._handles[-2:]
            backend = pin._backend
            parent = _metadata(backend.query(parent_handle), directory=True, max_bytes=4096)
            leaf = _metadata(backend.query(leaf_handle), directory=False, max_bytes=4096)
            if (len(pin._baseline) != len(pin._handles)
                    or _identity(pin._baseline[-2]) != _identity(parent)
                    or _identity(pin._baseline[-1]) != _identity(leaf)):
                raise RuntimeError(_FAILURE)
            parent_raw = backend.query_security(parent_handle)
            leaf_raw = backend.query_security(leaf_handle)
            if backend._security_reader.cleanup_unconfirmed:
                raise RuntimeError(_FAILURE)
            content = backend.read(leaf_handle, 0, len(_CONTENT))
        else:
            observer = base.observer
            parent, leaf = observer.query('parent'), observer.query('leaf')
            parent_raw = observer.reader.read(observer.handles['parent'].value)
            leaf_raw = observer.reader.read(observer.handles['leaf'].value)
            if observer.reader.cleanup_unconfirmed:
                raise RuntimeError(_FAILURE)
            handle = observer.handles['leaf'].value
            position, count = ctypes.c_int64(), _U32()
            buffer = ctypes.create_string_buffer(len(_CONTENT))
            result = base.api.kernel.SetFilePointerEx(handle, 0, ctypes.byref(position), 0)
            if type(result) is not int or result == 0 or position.value != 0:
                raise RuntimeError(_FAILURE)
            result = base.api.kernel.ReadFile(handle, buffer, len(_CONTENT), ctypes.byref(count), None)
            if type(result) is not int or result == 0 or count.value != len(_CONTENT):
                raise RuntimeError(_FAILURE)
            content = buffer.raw
        sample = {'parent': parent, 'leaf': leaf, 'bytes': content,
                  'parent_raw': parent_raw, 'leaf_raw': leaf_raw}
        _stable(base.initial, sample)
        for raw in (parent_raw, leaf_raw):
            if type(raw) is not bytes:
                raise RuntimeError(_FAILURE)
            _marker(raw, base.host, 0x80)
        if self.raw_baseline is None:
            if phase != 'unpinned' or leaf_raw != base.initial['raw']:
                raise RuntimeError(_FAILURE)
            self.raw_baseline = (parent_raw, leaf_raw)
        if (parent_raw, leaf_raw) != self.raw_baseline:
            raise RuntimeError(_FAILURE)
        return sample

    def root(self, phase):
        if phase != 'pinned':
            return self.base.observer.handles['parent'].value
        pin = self.base.pin
        pin._require_open()
        if not 2 <= len(pin._handles) <= 32:
            raise RuntimeError(_FAILURE)
        # The immediately preceding sample already bound this position/identity.
        return pin._handles[-2]

    def child(self, slot, kind, before):
        meta = _child_metadata(_query(self.base.api, slot.handle, kind == 'directory'),
                               kind == 'directory')
        key = (meta.volume_serial, meta.file_id)
        reserved = {(before[role].volume_serial, before[role].file_id)
                    for role in ('parent', 'leaf')}
        if (meta.volume_serial != before['parent'].volume_serial
                or key in reserved or key in self.child_ids):
            raise RuntimeError(_FAILURE)
        raw = self.base.observer.reader.read(slot.handle)
        if self.base.observer.reader.cleanup_unconfirmed:
            raise RuntimeError(_FAILURE)
        _marker(raw, self.base.host, 0x80)
        self.child_ids.add(key)
        return {'identity_distinct': True, 'volume_matches': True, 'kind_matches': True,
                'nonreparse': True, 'not_delete_pending': True, 'protected': True,
                'template_verified': True, 'empty_file': True if kind == 'file' else None}


def _remove(slot):
    if not slot.owned_path or slot.remove_attempted:
        return
    slot.remove_attempted = True
    if slot.directory:
        os.rmdir(slot.path)
    else:
        os.unlink(slot.path)
    slot.remove_confirmed = True


def _cleanup(base, ledger, slots, sd, original):
    failure = original
    operations = []
    if base.pin is not None:
        operations.append(base.pin.close)
    if sd is not None:
        operations.append(sd.close)
    for slot in reversed(slots):
        operations.append(lambda slot=slot: ledger.close(slot))
        operations.append(lambda slot=slot: _remove(slot))
    operations.append(base.close)
    for operation in operations:
        try:
            operation()
        except BaseException as error:
            failure = _choose(failure, error)
    if sd is not None and not sd.confirmed:
        failure = _choose(failure, _StageFailure('cleanup'))
    for slot in slots:
        if not slot.close_confirmed or (slot.owned_path and not slot.remove_confirmed):
            failure = _choose(failure, _StageFailure('cleanup'))
    return failure


def _run_variant(route, kind):
    stage, base, ledger, sd = 'fixture', None, None, None
    slots, events, original = [], [], None
    try:
        base = _Fixture('parent', 'new')
        ledger = _Ledger(base)
        stage = 'prepare'
        base.prepare()
        stage = 'initial'
        observe = _Observation(base)
        create = _Creation(base, ledger)
        stage = 'child_sd'
        sd = _ConvertedDacl(base.api)
        sd.acquire(base.host, 0x80)
        full_sd = sd.output.value
        if not _valid_handle(full_sd):
            raise RuntimeError(_FAILURE)
        for phase in _PHASES:
            if phase == 'pinned':
                stage = 'start_pin'
                base.start_pin()
            elif phase == 'released':
                stage = 'release_pin'
                values = tuple(base.pin._handles)
                base.pin.close()
                if base.pin.close_confirmed is not True:
                    raise RuntimeError(_FAILURE)
                ledger.retired.update(values)
                base.pin = None
            stage = phase + '_before'
            before = observe.sample(phase)
            stage = phase + '_direct_add'
            direct_error = None
            try:
                direct = create.direct_add(kind)
            except Exception as error:
                direct_error = error
            # KI/SE from ADD is deliberately outside this ordinary-error branch.
            slot = _Slot(os.path.join(base.parent, 'sibling-' + phase), kind == 'directory')
            slots.append(slot)
            stage = phase + '_create'
            try:
                effect, native = create.create(route, kind, phase, full_sd, observe.root(phase), slot)
            except BaseException as error:
                if direct_error is not None:
                    raise _choose(direct_error, error)
                raise
            if direct_error is not None:
                stage = phase + '_direct_add'
                raise direct_error
            stage = phase + '_after'
            after = observe.sample(phase)
            stage = phase + '_child'
            if phase != 'pinned' and effect != 'created':
                raise RuntimeError(_FAILURE)
            child = observe.child(slot, kind, before) if effect == 'created' else None
            events.append({'window': phase, 'direct_add': {
                'access': 2 if kind == 'file' else 4, 'result': direct},
                'create': native, 'effect': effect,
                'parent_metadata_changed': before['parent'] != after['parent'],
                'leaf_metadata_changed': before['leaf'] != after['leaf'],
                'identity_stable': True, 'bytes_stable': True,
                'parent_sd_stable': True, 'leaf_sd_stable': True, 'child': child})
    except BaseException as error:
        original = error if isinstance(error, (KeyboardInterrupt, SystemExit)) else _StageFailure(stage)
    if base is not None:
        error = _cleanup(base, ledger, slots, sd, original)
        if error is not None:
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise error
            raise original if original is not None else _StageFailure('cleanup')
    elif original is not None:
        raise original
    data = {'scope': 'private_sibling_window_observation', 'schema_version': 1,
            'route': route, 'kind': kind, 'windows': events, 'cleanup_confirmed': True,
            'consumer_ready': False, 'compatibility_accepted': False, 'launch_authorized': False}
    try:
        wire = _encode(data)
        validate_wire(wire)
        return wire
    except Exception:
        raise _StageFailure('wire') from None


def run_variant(route, kind):
    if (type(route) is not str or route not in _ROUTES
            or type(kind) is not str or kind not in _KINDS or os.name != 'nt'):
        raise RuntimeError(_FAILURE)
    try:
        return _run_variant(route, kind)
    except Exception as error:
        if failure_message(error) != _FAILURE:
            raise _StageFailure(error.args[0]) from None
        raise RuntimeError(_FAILURE) from None
```

- [x] 完成 acquisition fault 的 RED/GREEN：实际 function output 写入后抛错不删 unknown path；确认 success 注册前/return 边界 KI/SE 保留原对象；active collision不关闭；unknown-close裸值不得复用；confirmed-close数值被真实native获取的新代次可拥有并once关闭；所有 once close/free 不确认无 wire；directory native BOOL 成功后 witness 失败仍删除 owned directory。
- [x] child 保留到三窗结束。正常 cleanup 顺序必须是 reverse child HANDLE close + exact unlink/rmdir，再 base.close；关闭失败仍尝试其它 owned 资源，不递归 root，不重试旧数值。blocked slot 不做删除，也不增加 observer/reopen。
- [x] 固定预算复算：每变体 initial2 + before/after12 + createdchild3 =17 SD reads；四变体68 +基础转换8+child转换4=80 allocation/free；HANDLE 基础16+child12+ADD12+pin≤128+token4=≤172。Python leaf streams另账。若实际调用图超出，停止，先回 SPEC/QUALITY；不用减少验收断言掩盖预算。
- [x] 预算信用分开：fake实际执行并计数的是新增child/ADD **24次HANDLE acquisition/24次once close**，SD reader callback **68次**及真实conversion-owner fake调用 **12 acquire/12 LocalFree**。fake base.prepare/pin未执行真实token/config/observer/pin native获取，故172只属当前base/native源码锚点的静态上限（见spec复用表），不是fake实测总获取数；68次reader callback亦不等于原生GetSecurityInfo/LocalFree实测。实施后记录真实调用图和四格原生结果，禁止把静态公式写成实测全预算。

## Task 4：portable actual controller 与原生两个方法

Files: Modify 新 test；Modify `scripts/run_workspace_ci.py`; Modify `tests/test_windows_startup_pin_ci.py`。Dependencies: Task 3；Parallelizable: 否，阶段唯一writer。

Task4 实施记录：唯一writer在原CI下取得实际1方法/1断言FAIL/0ERROR（20个模块方法中2个native被跳过，CI错误返回0），接入必测前缀后该负控通过。root独立运行完整guard与新模块，实际34方法=32通过+2个明确Windows平台跳过，0FAIL/ERROR；其中guard14项零跳过，新模块18项portable通过。fixture605行及原portable前795行字节不变。最终test SHA256 `20960290ba05bb631fc19fc7dd1efe527a051c7c89d0a56dd748d8468e8ba337`，selector `043cc21e6382d0caf3f56332ead123e29886008a6d1a05c3ddc3d5a75b8c1627`，guard `4ea643a75ded803f3a78ca5ec77f1f1b12c9557b30062461fbee3ad3f063eb59`。独立SPEC→不同QUALITY与整片审查均零遗留；完整preflight session81741三道通过/exit0。两个skip不授原生信用，四格原生矩阵仍待线上验收。

- [x] 使用 unittest fake native 实际运行 `_Creation`/`_Observation`/`_run_variant`，不以另写 mock controller 替代。所有 fake 信用只属 transport/software。
- [x] 新 test 的最终 class 采用一个 `PrivateSiblingPortableTests`、两个 Windows native 方法。portable 最终数量以实际 loader 为准并同步 guard exact count；不得靠子测试数冒充 method 数。下列 native block 必须原样保留其抑制私密 traceback 边界。

```python
import sys
import unittest


@unittest.skipUnless(sys.platform == 'win32', 'native Windows only')
class WindowsPrivateSiblingWindowNativeTests(unittest.TestCase):
    def _observe(self, kind):
        from tests.windows_private_sibling_fixture import run_variant, validate_wire, failure_message
        for route in ('win32', 'nt_relative'):
            try:
                wire = run_variant(route, kind)
                validate_wire(wire)
            except BaseException as error:
                message = failure_message(error)
                if message != 'private_sibling_window_failed':
                    message += ':' + route + ':' + kind
                raise AssertionError(message) from None
            print(wire.decode('ascii'), end='')

    def test_private_sibling_file_three_windows(self):
        self._observe('file')

    def test_private_sibling_directory_three_windows(self):
        self._observe('directory')
```

在 native block 前加入以下 portable block（复用既有只读 test helper，不修改旧测试）。这些 fake 直接穿过新fixture的真实 native/helper/sampler/controller；native 信用仍仅来自 Windows 方法。

```python
import copy
import ctypes
import inspect
import json
import linecache
import sys
import unittest
from contextlib import ExitStack, contextmanager
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

from tests.test_windows_private_dacl_window import ApiFixture, raw_marker, snapshot
from tests.test_windows_startup_security_native import Function
from icode.windows_startup_pin import StartupFileMetadata
import tests.windows_private_sibling_fixture as m


class _Harness:
    def __init__(self):
        self.log, self.reads, self.next = [], [], 100
        self.error, self.add_error, self.block_phase = 5, None, None
        self.fail_witness, self.nt_return = False, 0
        self.nt_status, self.nt_information = 0, 2
        self.native_error, self.close_error, self.remove_error = None, None, None
        self.null_output, self.partial_output, self.forced_handle = False, False, None
        self.pin_error, self.raw_by_handle = None, {}
        self.allocations = []
        self.metadata = {10: snapshot()['parent'], 11: snapshot()['leaf']}
        self.f = ApiFixture(m)
        self.api = SimpleNamespace(kernel=self.f.kernel, advapi=self.f.advapi,
                                   call=lambda function, *args: function(*args))
        self.api.kernel.CreateFileW = Function(self.open)
        self.api.kernel.CreateDirectoryW = Function(self.mkdir)
        self.api.kernel.CloseHandle = Function(self.close)
        self.api.kernel.GetFileInformationByHandleEx = Function(self.info)
        self.ntdll = SimpleNamespace(NtCreateFile=Function(self.nt_create))
        self.reader = SimpleNamespace(read=self.read_sd, cleanup_unconfirmed=False)
        self.base = SimpleNamespace(parent='owned-parent', leaf='owned-parent/leaf',
            api=self.api, host='S-1-5-21-1', pin=None, initial=snapshot(),
            observer=SimpleNamespace(handles={'parent': SimpleNamespace(value=10),
                                             'leaf': SimpleNamespace(value=11)},
                                     reader=self.reader, query=self.query))
        self.base.prepare, self.base.start_pin, self.base.close = self.prepare, self.start_pin, self.base_close

    def prepare(self):
        self.log.append(('prepare',))
        # Exercise setup SD owners, independently of the child conversion owner.
        for role in ('leaf', 'parent'):
            owner = m._ConvertedDacl(self.api)
            owner.acquire(self.base.host, 0x80)
            owner.close()
            self.read_sd(11 if role == 'leaf' else 10)

    def allocate(self, directory):
        handle = self.next if self.forced_handle is None else self.forced_handle
        self.next += 1
        self.allocations.append(handle)
        self.metadata[handle] = StartupFileMetadata(1, handle.to_bytes(16, 'little'),
            directory, False, False, 'disk', 1, 0, 1)
        return handle

    def open(self, path, access, share, sa, disposition, flags, template):
        if access in (2, 4):
            self.log.append(('add', access))
            if self.add_error is not None:
                self.error = self.add_error
                return m._INVALID
            return self.allocate(True)
        if disposition == 1:
            self.log.append(('create', 'win32', 'file', path))
            attributes = ctypes.cast(sa, ctypes.POINTER(m._SECURITY_ATTRIBUTES)).contents
            self.log.append(('sa', attributes.nLength, attributes.lpSecurityDescriptor, attributes.bInheritHandle))
            if self.block_phase is not None and path.endswith('sibling-' + self.block_phase):
                return m._INVALID
            return None if self.null_output else self.allocate(False)
        self.log.append(('witness', path))
        return (m._INVALID if self.fail_witness else None if self.null_output else self.allocate(True))

    def mkdir(self, path, sa):
        self.log.append(('create', 'win32', 'directory', path))
        attributes = ctypes.cast(sa, ctypes.POINTER(m._SECURITY_ATTRIBUTES)).contents
        self.log.append(('sa', attributes.nLength, attributes.lpSecurityDescriptor, attributes.bInheritHandle))
        return 0 if self.block_phase is not None and path.endswith('sibling-' + self.block_phase) else 1

    def nt_create(self, output, access, attributes, iosb, allocation, attrs, share,
                  disposition, options, ea, ea_length):
        oa = ctypes.cast(attributes, ctypes.POINTER(m._OBJECT_ATTRIBUTES)).contents
        name = oa.ObjectName.contents
        basename = ctypes.string_at(name.Buffer, name.Length).decode('utf-16-le')
        self.log.append(('create', 'nt_relative', bool(options & 1), basename, oa.RootDirectory))
        status = self.nt_return
        if self.block_phase is not None and basename == 'sibling-' + self.block_phase:
            status = ctypes.c_int32(0xC0000022).value
        if (status == 0 and not self.null_output) or self.native_error is not None or self.partial_output:
            handle = self.allocate(bool(options & 1))
            ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p))[0] = handle
        ios = ctypes.cast(iosb, ctypes.POINTER(m._IO_STATUS_BLOCK)).contents
        ios.u.Status, ios.Information = self.nt_status, self.nt_information
        if self.native_error is not None:
            raise self.native_error
        return status

    def info(self, handle, info, output, length):
        value = ctypes.cast(output, ctypes.POINTER(m._INFO_CLASSES[info])).contents
        meta = self.metadata[handle]
        if info in (0, 9):
            value.FileAttributes = (16 if meta.directory else 128) | (0x400 if meta.reparse else 0)
            if info == 0:
                value.ChangeTime = meta.change_time
        elif info == 1:
            value.Directory, value.DeletePending = meta.directory, meta.delete_pending
            value.NumberOfLinks, value.EndOfFile = meta.links, meta.size
        else:
            value.VolumeSerialNumber = meta.volume_serial
            ctypes.memmove(value.FileId, meta.file_id, 16)
        return 1

    def query(self, role):
        return self.metadata[10 if role == 'parent' else 11]

    def read_sd(self, handle):
        self.reads.append(handle)
        return self.raw_by_handle.get(handle, raw_marker())

    def close(self, handle):
        self.log.append(('close', handle))
        if self.close_error is not None:
            raise self.close_error
        return 1

    def remove(self, path):
        self.log.append(('remove', path))
        if self.remove_error is not None:
            raise self.remove_error

    def start_pin(self):
        self.log.append(('pin_start',))
        self.metadata.update({20: self.metadata[10], 21: self.metadata[11]})
        pin = SimpleNamespace(_handles=[20, 21], _baseline=[self.metadata[20], self.metadata[21]],
                              close_confirmed=False)
        pin._require_open = lambda: None
        pin._backend = SimpleNamespace(query=lambda handle: self.metadata[handle],
            query_security=self.read_sd, _security_reader=self.reader,
            read=lambda handle, offset, count: m._CONTENT, _unknown=set())
        def close_pin():
            if not pin.close_confirmed:
                self.log.append(('pin_close',))
                if self.pin_error is not None:
                    raise self.pin_error
                pin.close_confirmed = True
        pin.close = close_pin
        self.base.pin = pin

    def base_close(self):
        self.log.append(('base_close',))

    def environment(self):
        stack = ExitStack()
        stack.enter_context(patch.object(m, '_Fixture', return_value=self.base))
        stack.enter_context(patch.object(ctypes, 'WinDLL', create=True, return_value=self.ntdll))
        stack.enter_context(patch.object(ctypes, 'get_last_error', create=True, side_effect=lambda: self.error))
        stack.enter_context(patch.object(m.os, 'unlink', side_effect=self.remove))
        stack.enter_context(patch.object(m.os, 'rmdir', side_effect=self.remove))
        return stack


@contextmanager
def _interrupt(function, needle, error, predicate=lambda local: True):
    previous, fired = sys.gettrace(), [False]
    def trace(frame, event, arg):
        if (frame.f_code is function.__code__ and not fired[0]
                and ((event == 'line' and needle in linecache.getline(frame.f_code.co_filename, frame.f_lineno))
                     or (event == 'return' and needle == '__return__'))
                and predicate(frame.f_locals)):
            fired[0] = True
            raise error
        return trace
    sys.settrace(trace)
    try:
        yield fired
    finally:
        sys.settrace(previous)


class PrivateSiblingPortableTests(unittest.TestCase):
    def receipt(self, route='win32', kind='file', blocked=False):
        windows = []
        for phase in m._PHASES:
            deny = blocked and phase == 'pinned'
            native = ({'result': 5 if deny else 0} if route == 'win32' else
                      {'return_u32': 0xC0000022} if deny else
                      {'return_u32': 0, 'iosb': {'status_u32': 0, 'information': 2}})
            child = None if deny else dict.fromkeys((
                'identity_distinct', 'volume_matches', 'kind_matches', 'nonreparse',
                'not_delete_pending', 'protected', 'template_verified'), True)
            if child is not None:
                child['empty_file'] = True if kind == 'file' else None
            windows.append({'window': phase, 'direct_add': {'access': 2 if kind == 'file' else 4, 'result': 0},
                'create': native, 'effect': 'blocked' if deny else 'created',
                'parent_metadata_changed': False, 'leaf_metadata_changed': False,
                'identity_stable': True, 'bytes_stable': True, 'parent_sd_stable': True,
                'leaf_sd_stable': True, 'child': child})
        return {'scope': 'private_sibling_window_observation', 'schema_version': 1,
                'route': route, 'kind': kind, 'windows': windows, 'cleanup_confirmed': True,
                'consumer_ready': False, 'compatibility_accepted': False, 'launch_authorized': False}

    def test_entry_rejects_before_loader(self):
        class Text(str):
            pass
        for route, kind in ((Text('win32'), 'file'), ('win32', Text('file')), ('other', 'file'), ('win32', None)):
            with patch.object(m, '_Fixture', create=True) as constructor, patch.object(m.os, 'name', 'nt'):
                with self.assertRaises(RuntimeError):
                    m.run_variant(route, kind)
                constructor.assert_not_called()
        with patch.object(m, '_Fixture', create=True) as constructor, patch.object(m.os, 'name', 'posix'):
            with self.assertRaises(RuntimeError):
                m.run_variant('win32', 'file')
            constructor.assert_not_called()

    def test_wire_all_route_kind_and_effect_combinations(self):
        for route in m._ROUTES:
            for kind in m._KINDS:
                for blocked in (False, True):
                    for direct in (0, 5, 32, 33):
                        data = self.receipt(route, kind, blocked)
                        data['windows'][1]['direct_add']['result'] = direct
                        self.assertEqual(m.validate_wire(m._encode(data)), data)

    def test_wire_rejects_types_keys_and_canonical_drift(self):
        data = self.receipt()
        wire = m._encode(data)
        for invalid in (wire[:-1], wire + b'\n', b' ' + wire, wire.replace(b',', b', ', 1),
                        wire.replace(b'"schema_version":1', b'"schema_version":1,"schema_version":1'),
                        b'\xff\n', b'x' * 8193, wire.decode('ascii')):
            with self.assertRaises(ValueError):
                m.validate_wire(invalid)
        objects = [data, data['windows'][0], data['windows'][0]['direct_add'],
                   data['windows'][0]['create'], data['windows'][0]['child']]
        for obj in objects:
            for key in list(obj):
                value = obj.pop(key)
                with self.assertRaises(ValueError):
                    m.validate_wire(m._encode(data))
                obj[key] = value
            obj['extra'] = None
            with self.assertRaises(ValueError):
                m.validate_wire(m._encode(data))
            del obj['extra']
        for field in ('access', 'result'):
            bad = self.receipt()
            bad['windows'][0]['direct_add'][field] = True
            with self.assertRaises(ValueError):
                m.validate_wire(m._encode(bad))
        class Integer(int):
            pass
        with patch.object(m.json, 'loads', return_value=dict(data, schema_version=Integer(1))):
            with self.assertRaises(ValueError):
                m.validate_wire(wire)

    def test_wire_positive_controls_and_authority(self):
        for phase in (0, 2):
            bad = self.receipt(blocked=True)
            bad['windows'][phase].update(effect='blocked', create={'result': 5}, child=None)
            with self.assertRaises(ValueError):
                m.validate_wire(m._encode(bad))
        for field in ('cleanup_confirmed', 'consumer_ready', 'compatibility_accepted', 'launch_authorized'):
            bad = self.receipt()
            bad[field] = 1
            with self.assertRaises(ValueError):
                m.validate_wire(m._encode(bad))

    def test_native_abi_and_full_sd(self):
        h = _Harness()
        ledger = m._Ledger(h.base)
        with h.environment():
            create = m._Creation(h.base, ledger)
            self.assertEqual(create.ntdll.NtCreateFile.restype, ctypes.c_int32)
            self.assertEqual(len(create.ntdll.NtCreateFile.argtypes), 11)
            slot = m._Slot('owned-child', False)
            effect, result = create.create('nt_relative', 'file', 'unpinned', 12345, 10, slot)
            args = h.ntdll.NtCreateFile.calls[-1]
            oa = ctypes.cast(args[2], ctypes.POINTER(m._OBJECT_ATTRIBUTES)).contents
            self.assertEqual((oa.Length, oa.RootDirectory, oa.Attributes, oa.SecurityDescriptor,
                              oa.SecurityQualityOfService), (ctypes.sizeof(oa), 10, 0x1040, 12345, None))
            self.assertEqual(args[1], 0x120081)
            self.assertEqual(args[5:], (0, 7, 2, 0x200060, None, 0))
            self.assertEqual(effect, 'created')
            ledger.close(slot)
        self.assertEqual(m._SECURITY_ATTRIBUTES._fields_[0][1], ctypes.c_uint32)
        self.assertEqual(m._SECURITY_ATTRIBUTES._fields_[2][1], ctypes.c_int32)

    def test_win32_creation_and_directory_witness(self):
        for kind in m._KINDS:
            h = _Harness()
            with h.environment():
                create = m._Creation(h.base, m._Ledger(h.base))
                slot = m._Slot('owned-child', kind == 'directory')
                effect, native = create.create('win32', kind, 'unpinned', 12345, 10, slot)
                self.assertEqual((effect, native), ('created', {'result': 0}))
                self.assertTrue(slot.owned_path)
                self.assertIn(('sa', ctypes.sizeof(m._SECURITY_ATTRIBUTES), 12345, 0), h.log)
                args = h.api.kernel.CreateFileW.calls[-1]
                self.assertEqual((args[1], args[2], args[4], args[5]),
                    (0x120081, 7, 3 if kind == 'directory' else 1, 0x2200000 if kind == 'directory' else 0x200000))

    def test_nt_success_and_failure_outputs(self):
        for code in m._NT_DENIED:
            h = _Harness()
            h.nt_return, h.nt_status, h.nt_information = ctypes.c_int32(code).value, 7, 99
            with h.environment():
                create = m._Creation(h.base, m._Ledger(h.base))
                self.assertEqual(create.create('nt_relative', 'file', 'pinned', 12345, 10,
                    m._Slot('owned-child', False)), ('blocked', {'return_u32': code}))
        for ret, status, info in ((0x103, 0, 2), (1, 0, 2), (0, 1, 2), (0, 0, 1)):
            h = _Harness()
            h.nt_return, h.nt_status, h.nt_information = ret, status, info
            with h.environment():
                with self.assertRaises(RuntimeError):
                    m._Creation(h.base, m._Ledger(h.base)).create('nt_relative', 'file',
                        'pinned', 12345, 10, m._Slot('owned-child', False))
        for route in m._ROUTES:
            for kind in m._KINDS:
                for fault in ('null', 'partial', 'active', 'unknown'):
                    with self.subTest(route=route, kind=kind, fault=fault):
                        h = _Harness()
                        ledger = m._Ledger(h.base)
                        if fault == 'null':
                            h.null_output = True
                        elif fault == 'partial':
                            if route != 'nt_relative':
                                continue
                            h.nt_return = ctypes.c_int32(0xC0000022).value
                            h.partial_output = True
                        else:
                            h.forced_handle = 10 if fault == 'active' else 900
                            if fault == 'unknown':
                                ledger.unknown.add(900)
                        slot = m._Slot('owned-child', kind == 'directory')
                        with h.environment():
                            with self.assertRaises(RuntimeError):
                                m._Creation(h.base, ledger).create(route, kind, 'pinned', 12345, 10, slot)
                        if fault in ('active', 'unknown'):
                            self.assertFalse(any(row[0] == 'close' for row in h.log))
                        if fault == 'partial':
                            self.assertFalse(slot.owned_path)
                            self.assertEqual(sum(row[0] == 'close' for row in h.log), 1)

    def test_direct_add_is_independent_of_create(self):
        for route in m._ROUTES:
            for kind in m._KINDS:
                h = _Harness()
                with h.environment():
                    m._run_variant(route, kind)
                calls = [args for args in h.api.kernel.CreateFileW.calls if args[1] in (2, 4)]
                self.assertEqual(len(calls), 3)
                for args in calls:
                    self.assertEqual(args, (h.base.parent, 2 if kind == 'file' else 4,
                                           7, None, 3, 0x2200000, None))
        for error in (5, 32, 33, 87):
            h = _Harness()
            h.add_error = error
            with h.environment():
                if error == 87:
                    with self.assertRaises(m._StageFailure):
                        m._run_variant('win32', 'file')
                else:
                    self.assertEqual(len(m.validate_wire(m._run_variant('win32', 'file'))['windows']), 3)
            self.assertTrue(any(row[0] == 'create' for row in h.log))
        h = _Harness()
        h.close_error = RuntimeError()
        with h.environment():
            with self.assertRaises(m._StageFailure):
                m._run_variant('win32', 'file')
        self.assertEqual(sum(row[0] == 'create' for row in h.log), 1)
        for error in (KeyboardInterrupt(), SystemExit()):
            h = _Harness()
            with h.environment(), patch.object(m._Creation, 'direct_add', side_effect=error):
                with self.assertRaises(type(error)) as caught:
                    m._run_variant('win32', 'file')
                self.assertIs(caught.exception, error)
            self.assertFalse(any(row[0] == 'create' for row in h.log))

    def test_controller_windows_pin_and_retention(self):
        for route in m._ROUTES:
            for kind in m._KINDS:
                h = _Harness()
                with h.environment():
                    data = m.validate_wire(m._run_variant(route, kind))
                self.assertEqual([event['window'] for event in data['windows']], list(m._PHASES))
                created = [index for index, row in enumerate(h.log) if row[0] == 'create']
                removed = [index for index, row in enumerate(h.log) if row[0] == 'remove']
                self.assertEqual(len(created), 3)
                self.assertGreater(min(removed), max(created))
                self.assertLess(h.log.index(('pin_close',)), created[2])
                if route == 'nt_relative':
                    self.assertEqual([row[4] for row in h.log if row[0] == 'create'], [10, 20, 10])
        # Actual Creation.create RETURN event is after its local try has ended.
        # The registered slot belongs to _run_variant, so outer cleanup closes
        # the acquired child and removes its confirmed owned path exactly once.
        for route in m._ROUTES:
            for kind in m._KINDS:
                for signal in (KeyboardInterrupt(), SystemExit()):
                    h = _Harness()
                    with self.subTest(route=route, kind=kind, boundary='create_actual_return', signal=type(signal)), h.environment():
                        with _interrupt(m._Creation.create, '__return__', signal) as fired:
                            with self.assertRaises(type(signal)) as caught:
                                m._run_variant(route, kind)
                        self.assertTrue(fired[0])
                        self.assertIs(caught.exception, signal)
                    self.assertEqual(sum(row[0] == 'create' for row in h.log), 1)
                    self.assertEqual(len(h.allocations), 2)
                    closes = [row[1] for row in h.log if row[0] == 'close']
                    self.assertCountEqual(closes, h.allocations)
                    self.assertEqual(len(closes), 2)
                    removes = [row[1] for row in h.log if row[0] == 'remove']
                    self.assertEqual(removes, [m.os.path.join(h.base.parent, 'sibling-unpinned')])
                    self.assertEqual(h.log[-1], ('base_close',))
        # Task3 adds the actual converted-owner pointer and full lifecycle cases;
        # Task2's five acquisition methods have no _run_variant dependency.
        for route in m._ROUTES:
            for kind in m._KINDS:
                h = _Harness()
                with h.environment():
                    m._run_variant(route, kind)
                full = ctypes.addressof(h.f.pointer)
                if route == 'win32':
                    self.assertEqual([row[2] for row in h.log if row[0] == 'sa'], [full] * 3)
                else:
                    h = _Harness()
                    full_pointers = []
                    def capture(*args):
                        oa = ctypes.cast(args[2], ctypes.POINTER(m._OBJECT_ATTRIBUTES)).contents
                        full_pointers.append(oa.SecurityDescriptor)
                        self.assertEqual(args[8], 0x200020 | (1 if kind == 'directory' else 0x40))
                        return h.nt_create(*args)
                    h.ntdll.NtCreateFile = Function(capture)
                    with h.environment():
                        m._run_variant(route, kind)
                    self.assertEqual(full_pointers, [ctypes.addressof(h.f.pointer)] * 3)
                self.assertNotEqual(full, full + 20)
        for route in m._ROUTES:
            for kind in m._KINDS:
                for phase in m._PHASES:
                    h = _Harness()
                    h.block_phase = phase
                    with h.environment():
                        if phase == 'pinned':
                            data = m.validate_wire(m._run_variant(route, kind))
                            self.assertEqual(data['windows'][1]['effect'], 'blocked')
                            self.assertIsNone(data['windows'][1]['child'])
                        else:
                            with self.assertRaises(m._StageFailure):
                                m._run_variant(route, kind)
        for error in (RuntimeError(), KeyboardInterrupt(), SystemExit()):
            h = _Harness()
            h.pin_error = error
            with h.environment():
                with self.assertRaises(type(error) if not isinstance(error, Exception) else m._StageFailure) as caught:
                    m._run_variant('nt_relative', 'directory')
                if not isinstance(error, Exception):
                    self.assertIs(caught.exception, error)
            self.assertEqual(sum(row[0] == 'create' for row in h.log), 2)

    def test_first_before_and_cross_window_raw(self):
        h = _Harness()
        observe = m._Observation(h.base)
        with h.environment():
            before = observe.sample('unpinned')
            self.assertEqual(observe.raw_baseline, (before['parent_raw'], before['leaf_raw']))
            h.reader.read = lambda handle: raw_marker(0x100)
            with self.assertRaises(RuntimeError):
                observe.sample('released')
        h = _Harness()
        h.base.initial['raw'] = raw_marker(0x100)
        with h.environment():
            with self.assertRaises(RuntimeError):
                m._Observation(h.base).sample('unpinned')
        # Both descriptors pass the same protected template, but raw bytes differ.
        from tests.test_windows_startup_security import descriptor, acl, ace, sid
        reordered = descriptor(control=0x9004, dacl=acl([
            ace(mask=0x80, trustee=sid(1, (0,))),
            ace(mask=0x1f01ff, trustee=sid(5, (32, 544))),
            ace(mask=0x1f01ff, trustee=sid(5, (18,))),
            ace(mask=0x1f01ff, trustee=sid(5, (21, 1))),
        ]))
        m._marker(reordered, 'S-1-5-21-1', 0x80)
        self.assertNotEqual(reordered, raw_marker())
        for role in ('parent', 'leaf'):
            h = _Harness()
            observe = m._Observation(h.base)
            with h.environment():
                observe.sample('unpinned')
                h.raw_by_handle[10 if role == 'parent' else 11] = reordered
                with self.assertRaises(RuntimeError):
                    observe.sample('released')

    def test_identity_bytes_and_metadata_change(self):
        h = _Harness()
        with h.environment():
            observe = m._Observation(h.base)
            observe.sample('unpinned')
            h.metadata[10] = replace(h.metadata[10], change_time=2)
            observe.sample('released')
            h.metadata[10] = replace(h.metadata[10], file_id=b'x' * 16)
            with self.assertRaises(RuntimeError):
                observe.sample('released')
        h = _Harness()
        with h.environment(), patch.object(h.api.kernel, 'ReadFile', return_value=0):
            with self.assertRaises(RuntimeError):
                m._Observation(h.base).sample('unpinned')
        h = _Harness()
        h.metadata[11] = replace(h.metadata[11], file_id=b'wrong-leaf-id---!')
        with h.environment():
            with self.assertRaises(Exception):
                m._Observation(h.base).sample('unpinned')
        h = _Harness()
        def wrong_bytes(handle, buffer, count, actual, overlap):
            ctypes.memmove(buffer, b'x' * count, count)
            ctypes.cast(actual, ctypes.POINTER(ctypes.c_uint32))[0] = count
            return 1
        with h.environment(), patch.object(h.api.kernel, 'ReadFile', side_effect=wrong_bytes):
            with self.assertRaises(RuntimeError):
                m._Observation(h.base).sample('unpinned')

    def test_child_metadata_and_actual_security(self):
        file = StartupFileMetadata(1, b'c' * 16, False, False, False, 'disk', 1, 0, 1)
        self.assertIs(m._child_metadata(file, False), file)
        self.assertIs(m._child_metadata(replace(file, directory=True, size=123, links=3), True).directory, True)
        for bad in (replace(file, size=1), replace(file, links=2), replace(file, reparse=True),
                    replace(file, delete_pending=True), replace(file, volume_serial=True)):
            with self.assertRaises(RuntimeError):
                m._child_metadata(bad, False)
        with self.assertRaises(Exception):
            m._metadata(file, directory=False, max_bytes=4096)
        h = _Harness()
        slot = m._Slot('owned-child', False)
        slot.handle = h.allocate(False)
        h.reader.read = lambda handle: raw_marker(0x100)
        with self.assertRaises(RuntimeError):
            m._Observation(h.base).child(slot, 'file', snapshot())

    def test_child_identity_retained_distinct(self):
        h = _Harness()
        observe = m._Observation(h.base)
        slot = m._Slot('owned-child', False)
        slot.handle = h.allocate(False)
        observe.child(slot, 'file', snapshot())
        with self.assertRaises(RuntimeError):
            observe.child(slot, 'file', snapshot())
        h.metadata[slot.handle] = replace(h.metadata[slot.handle], file_id=snapshot()['leaf'].file_id)
        with self.assertRaises(RuntimeError):
            m._Observation(h.base).child(slot, 'file', snapshot())

    def test_acquisition_registration_return_interrupts(self):
        # Trace actual source lines: after native result is saved, before claim,
        # after claim, and at the successful return boundary, for all variants.
        for route in m._ROUTES:
            for kind in m._KINDS:
                saved = ('value = output.value' if route == 'nt_relative' else
                         'value = result' if kind == 'file' else 'if type(result) is not int:')
                for boundary in (saved, 'self.ledger.claim(slot, value)',
                                 '__return__', "return 'created',"):
                    for error in (KeyboardInterrupt(), SystemExit()):
                        h = _Harness()
                        slot = m._Slot('owned-child', kind == 'directory')
                        predicate = lambda local: True
                        with self.subTest(route=route, kind=kind, boundary=boundary, signal=type(error)), h.environment():
                            create = m._Creation(h.base, m._Ledger(h.base))
                            target = create.ledger.claim if boundary == '__return__' else create.create
                            with _interrupt(target, boundary, error, predicate) as fired:
                                with self.assertRaises(type(error)) as caught:
                                    create.create(route, kind, 'unpinned', 12345, 10, slot)
                            self.assertTrue(fired[0])
                            self.assertIs(caught.exception, error)
                        self.assertTrue(slot.owned_path)
                        expected = 0 if route == 'win32' and kind == 'directory' and boundary == saved else 1
                        self.assertEqual(sum(row[0] == 'close' for row in h.log), expected)
        for error in (KeyboardInterrupt(), SystemExit()):
            h = _Harness()
            ledger = m._Ledger(h.base)
            actual = ledger.claim
            def claim(slot, value):
                actual(slot, value)
                raise error
            with h.environment(), patch.object(ledger, 'claim', side_effect=claim):
                slot = m._Slot('owned-child', False)
                with self.assertRaises(type(error)) as caught:
                    m._Creation(h.base, ledger).create('nt_relative', 'file', 'unpinned', 12345, 10, slot)
                self.assertIs(caught.exception, error)
            self.assertEqual(sum(row[0] == 'close' for row in h.log), 1)
            self.assertTrue(slot.owned_path)

    def test_unknown_outputs_and_known_owner_collision(self):
        h = _Harness()
        h.native_error = KeyboardInterrupt()
        slot = m._Slot('unknown-path', False)
        with h.environment():
            with self.assertRaises(KeyboardInterrupt):
                m._Creation(h.base, m._Ledger(h.base)).create('nt_relative', 'file',
                    'unpinned', 12345, 10, slot)
        self.assertFalse(slot.owned_path)
        self.assertEqual(sum(row[0] == 'close' for row in h.log), 1)
        h = _Harness()
        ledger = m._Ledger(h.base)
        for value in (10, 11):
            with self.assertRaises(RuntimeError):
                ledger.claim(m._Slot('owned-child', False), value)
        first = m._Slot('owned-first', False)
        ledger.claim(first, 500)
        h.close_error = RuntimeError()
        with self.assertRaises(RuntimeError):
            ledger.close(first)
        with self.assertRaises(RuntimeError):
            ledger.claim(m._Slot('owned-second', False), 500)
        h.close_error = None
        first = m._Slot('owned-first', False)
        ledger.claim(first, 501)
        ledger.close(first)
        second = m._Slot('owned-second', False)
        ledger.claim(second, 501)
        ledger.close(second)
        ledger.close(first)
        self.assertEqual(h.log.count(('close', 501)), 2)
        # Demonstrate numerical reuse from the actual native helper, not only
        # calling ledger.claim: first acquisition confirmed closed, second new.
        h = _Harness()
        ledger = m._Ledger(h.base)
        with h.environment():
            create = m._Creation(h.base, ledger)
            first = m._Slot('owned-first', False)
            create.create('win32', 'file', 'unpinned', 12345, 10, first)
            ledger.close(first)
            h.next = first.handle
            second = m._Slot('owned-second', False)
            create.create('win32', 'file', 'released', 12345, 10, second)
            self.assertEqual(first.handle, second.handle)
            self.assertTrue(second.owned_path)
            ledger.close(second)
        self.assertEqual(h.log.count(('close', first.handle)), 2)

    def test_cleanup_one_attempt_reverse_and_priority(self):
        h = _Harness()
        h.fail_witness = True
        with h.environment():
            with self.assertRaises(m._StageFailure):
                m._run_variant('win32', 'directory')
        self.assertTrue(any(row[0] == 'remove' for row in h.log))
        h = _Harness()
        ledger = m._Ledger(h.base)
        slots = [m._Slot('owned-' + str(index), False) for index in range(3)]
        for index, slot in enumerate(slots):
            ledger.claim(slot, 600 + index)
            slot.owned_path = True
        h.remove_error = RuntimeError()
        original = KeyboardInterrupt()
        with h.environment():
            self.assertIs(m._cleanup(h.base, ledger, slots, None, original), original)
        self.assertEqual([row[1] for row in h.log if row[0] == 'close'], [602, 601, 600])
        self.assertEqual([row[1] for row in h.log if row[0] == 'remove'], ['owned-2', 'owned-1', 'owned-0'])
        self.assertEqual(h.log[-1], ('base_close',))
        self.assertIs(m._choose(RuntimeError(), original), original)
        self.assertIs(m._choose(original, SystemExit()), original)
        for signal in (KeyboardInterrupt(), SystemExit()):
            for stage in ('sd_free', 'remove'):
                h = _Harness()
                count = [0]
                def free(pointer):
                    count[0] += 1
                    if count[0] == 3:
                        raise signal
                    return None
                if stage == 'sd_free':
                    h.f.kernel.LocalFree = Function(free)
                else:
                    h.remove_error = signal
                with h.environment():
                    with self.assertRaises(type(signal)) as caught:
                        m._run_variant('win32', 'file')
                    self.assertIs(caught.exception, signal)
                self.assertEqual(h.log[-1], ('base_close',))
                self.assertEqual(sum(row[0] == 'remove' for row in h.log), 3)
        h = _Harness()
        count = [0]
        def unconfirmed_free(pointer):
            count[0] += 1
            return pointer if count[0] == 3 else None
        h.f.kernel.LocalFree = Function(unconfirmed_free)
        with h.environment():
            with self.assertRaises(m._StageFailure) as caught:
                m._run_variant('win32', 'file')
            self.assertEqual(caught.exception.args, ('cleanup',))
        self.assertEqual(count[0], 3)
        for phase in ('unpinned', 'pinned', 'released', 'child'):
            h = _Harness()
            actual_sample, actual_child = m._Observation.sample, m._Observation.child
            def sample(owner, current):
                if current == phase:
                    h.reader.cleanup_unconfirmed = True
                return actual_sample(owner, current)
            def child(owner, *args):
                if phase == 'child':
                    h.reader.cleanup_unconfirmed = True
                return actual_child(owner, *args)
            with h.environment(), patch.object(m._Observation, 'sample', sample), patch.object(m._Observation, 'child', child):
                with self.assertRaises(m._StageFailure):
                    m._run_variant('win32', 'file')

    def test_failure_diagnostic_is_finite_and_private(self):
        for stage in m._STAGES:
            self.assertEqual(m.failure_message(m._StageFailure(stage)), m._FAILURE + ':' + stage)
        class Hostile(RuntimeError):
            @property
            def args(self):
                raise AssertionError('must not read custom args')
        self.assertEqual(m.failure_message(Hostile()), m._FAILURE)
        self.assertEqual(m.failure_message(m._StageFailure('C:\\private\\secret')), m._FAILURE)
        source = inspect.getsource(m._Creation.create)
        self.assertNotIn('._call(', source)
        self.assertNotIn('_at_stage(', source)

    def test_static_all_created_budget(self):
        total_reads, total_converts, total_frees, new_acquires, new_closes = 0, 0, 0, 0, 0
        for route in m._ROUTES:
            for kind in m._KINDS:
                h = _Harness()
                with h.environment():
                    m.validate_wire(m._run_variant(route, kind))
                self.assertEqual(len(h.reads), 17)
                self.assertEqual(sum(row[0] == 'add' for row in h.log), 3)
                self.assertEqual(sum(row[0] == 'create' for row in h.log), 3)
                total_reads += len(h.reads)
                total_converts += len(h.f.advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.calls)
                total_frees += len(h.f.kernel.LocalFree.calls)
                self.assertEqual(len(h.allocations), 6)
                closes = [row[1] for row in h.log if row[0] == 'close']
                self.assertCountEqual(closes, h.allocations)
                self.assertEqual(len(closes), 6)
                new_acquires += len(h.allocations)
                new_closes += len(closes)
        self.assertEqual((total_reads, total_converts, total_frees), (68, 12, 12))
        self.assertEqual(total_reads + total_converts, 80)
        self.assertEqual((new_acquires, new_closes), (24, 24))
        # Static upper bound from current real source/spec, not fake-native count:
        # base config+observer4, children3, ADD3, pin<=32, token1 per variant.
        self.assertEqual(4 * (4 + 3 + 3 + 32 + 1), 172)
```

portable 测试的必要方法清单（每个方法必须有真实断言，不以方法名作为覆盖证据）：

| method | 必须执行与断言 |
| --- | --- |
| test_entry_rejects_before_loader | invalid exact type/enum 和 non-Windows 对 `_Fixture`/WinDLL/token/mkdtemp 零调用 |
| test_wire_all_route_kind_and_effect_combinations | 四 route/kind × pinned created/blocked；ADD result 与 create 独立，包括 ADD denied/create success |
| test_wire_rejects_types_keys_and_canonical_drift | 所有层缺/extra key、bool-as-int、subclasses、duplicate、nonASCII、排序/LF/空白、length8193 |
| test_wire_positive_controls_and_authority | unpinned/released blocked拒绝；三个authority/cleanup/stable exact identity |
| test_native_abi_and_full_sd | Task2直接acquisition的SA sizeof/32bit、Nt11arg/restype、actual OA/IOSB和传入fullpointer、single name/root/flags；真实conversionowner fullSD≠interior全链断言在Task3controller追加 |
| test_win32_creation_and_directory_witness | Task2两kind nativeparams、BOOL成功owned；Task3cleanup追加witness失败后的全局删除断言 |
| test_nt_success_and_failure_outputs | actual return/IOSB/Info；finite failure IOSB随意；pending/warning/Info错/partial/NULL/collision无wire |
| test_direct_add_is_independent_of_create | 2/4一个ADD、share7、close一次；三finite denied仍create；unknown/close不确认仍create再FAIL；KI/SE停止 |
| test_controller_windows_pin_and_retention | actual controller三窗顺序、pin release后released、三个children全程保留、borrow root切换；四变体×KI/SE真正Creation.create RETURN-event，由已登记slot的outercleanup once关闭/删除 |
| test_first_before_and_cross_window_raw | 首before保存双raw、leaf与base.initial匹配；prepare parentraw不伪授；任意后续SD漂移拒绝 |
| test_identity_bytes_and_metadata_change | parent/leaf identity与_CONTENT稳定；ChangeTime变化只bool记录，不调用revalidate |
| test_child_metadata_and_actual_security | zero-file专用门、dirEOF非负、volume/role/link/reparse/DeletePending/actualSD模板 |
| test_child_identity_retained_distinct | parent/leaf/prior children碰撞拒绝，所有children保留防ID回收 |
| test_acquisition_registration_return_interrupts | Task2 native result保存/claim前/claim实际RETURN/created-return执行前KI/SE；原对象身份保持；Creation.create真正RETURN-event在Task3controller测outercleanup |
| test_unknown_outputs_and_known_owner_collision | native抛错有output一次close不删unknownpath；active/unknown不close旧值；confirmed-close数值复用新代次onceclose |
| test_cleanup_one_attempt_reverse_and_priority | reverse close+exact removal→base、普通错误继续、主体KI/SE优先、cleanupKI/SE优先、SD一次free不确认无wire |
| test_failure_diagnostic_is_finite_and_private | stage whitelist、hostile自定义属性不读、无path/SID/SD/HANDLE/exceptiontext；外层native异常边界 |
| test_static_all_created_budget | fake新增HANDLE24/close24、SD callbacks68和conversion12/free12；当前base/native静态HANDLE≤172独立账，三个create与一个同kindADD/窗，无额外prepin/reset/sample |

- [x] **18 个 portable methods** 全部落地并通过实际 loader，若为清晰边界而拆分更多方法，修改 exact count 后重新过 selector/guard；不得减少上述覆盖。
- [x] `startup_pin_tests()` portable tuple 末追加 `tests.test_windows_private_sibling_window.PrivateSiblingPortableTests`；nt conditional tuple 末追加 `tests.test_windows_private_sibling_window.WindowsPrivateSiblingWindowNativeTests`。`main()` selected_pin_ids 前缀集合追加 `tests.test_windows_private_sibling_window.`，复用原 fixture/subTest skip fail逻辑，不改可选语义。
- [x] guard：PORTABLE_CLASSES/COUNTS 末追加新 portable class/18；NATIVE_CLASSES/COUNTS 末追加新 native class/2。`test_default_selects_complete_pin_contract_once` selected prefix 追加 sibling。`test_real_class_and_module_loader_cannot_hide_required_skip` 显式添加 sibling portable18、native2；其模块 fixtures tuple追加 sibling module。旧 `PORTABLE_CLASSES[-4:]` 改为旧DACL四类的固定显式选择或精确旧slice `[-5:-1]`，避免追加后遗漏首个旧DACL类。新增 sibling module platform skip test，loader expected20/run20/skipped2/code1；旧DACL34不变。现有 body/fixture/nested-subTest loops 自动覆盖新classes。
- [x] selector 和 guard 用以下精确 diff 接线；不增加其它 runner 和 workflow。

```diff
--- a/scripts/run_workspace_ci.py
+++ b/scripts/run_workspace_ci.py
@@
         "tests.test_windows_private_dacl_window.PrivateDaclLifecycleTests",
+        "tests.test_windows_private_sibling_window.PrivateSiblingPortableTests",
@@
-           "tests.test_windows_private_dacl_window.WindowsPrivateDaclWindowNativeTests") if platform == "nt" else ()),
+           "tests.test_windows_private_dacl_window.WindowsPrivateDaclWindowNativeTests",
+           "tests.test_windows_private_sibling_window.WindowsPrivateSiblingWindowNativeTests") if platform == "nt" else ()),
@@
             "tests.test_windows_private_dacl_window.",
+            "tests.test_windows_private_sibling_window.",
--- a/tests/test_windows_startup_pin_ci.py
+++ b/tests/test_windows_startup_pin_ci.py
@@
     "tests.test_windows_private_dacl_window.PrivateDaclLifecycleTests",
+    "tests.test_windows_private_sibling_window.PrivateSiblingPortableTests",
@@
-NATIVE_CLASSES = (NATIVE_CLASS, NATIVE_SECURITY_CLASS, NATIVE_IDENTITY_CLASS, NATIVE_DACL_CLASS)
-NATIVE_COUNTS = (6, 2, 2, 2)
+NATIVE_SIBLING_CLASS = "tests.test_windows_private_sibling_window.WindowsPrivateSiblingWindowNativeTests"
+NATIVE_CLASSES = (NATIVE_CLASS, NATIVE_SECURITY_CLASS, NATIVE_IDENTITY_CLASS, NATIVE_DACL_CLASS,
+                  NATIVE_SIBLING_CLASS)
+NATIVE_COUNTS = (6, 2, 2, 2, 2)
@@
-                   1, 6, 21, 5, 5, 5, 11, 3, 13)
+                   1, 6, 21, 5, 5, 5, 11, 3, 13, 18)
@@
                                          "tests.test_windows_private_dacl_window.",
+                                         "tests.test_windows_private_sibling_window.",
@@
-                                *zip(PORTABLE_CLASSES[-4:], PORTABLE_COUNTS[-4:]),
-                                (NATIVE_DACL_CLASS, 2)):
+                                *zip(PORTABLE_CLASSES[-5:-1], PORTABLE_COUNTS[-5:-1]),
+                                (PORTABLE_CLASSES[-1], 18),
+                                (NATIVE_DACL_CLASS, 2), (NATIVE_SIBLING_CLASS, 2)):
@@
-                          "tests.test_windows_private_dacl_window"):
+                          "tests.test_windows_private_dacl_window",
+                          "tests.test_windows_private_sibling_window"):
```

新增下面 guard method，沿用旧 guard 的 existing imports/run_ci；完整模块在非Windows手工选择时 native skip 必须 fail，且不会获原生信用。

```python
    def test_private_sibling_module_platform_skip_never_receives_native_credit(self):
        module_id = "tests.test_windows_private_sibling_window"
        module = importlib.import_module(module_id)
        native = module.WindowsPrivateSiblingWindowNativeTests
        missing = object()
        original = native.__dict__.get("__unittest_skip__", missing)
        try:
            if original is not missing:
                del native.__unittest_skip__
            with patch.object(native, "__unittest_skip__", True, create=True):
                code, result = self.run_ci((module_id,))
        finally:
            if original is not missing:
                native.__unittest_skip__ = original
            elif "__unittest_skip__" in native.__dict__:
                del native.__unittest_skip__
        self.assertIs(native.__dict__.get("__unittest_skip__", missing), original)
        self.assertEqual(result.testsRun, 20)
        self.assertEqual(len(result.skipped), 2)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.failures, [])
        self.assertEqual(code, 1)
```

- [x] 启动 portable完整模块/guard/selector三者实际回归，确保非Windows默认选portable一次/native零次；Windows默认选native两方法各一次；任何Windows方法、fixture、subTest skip为FAIL；missing method加载error不伪通过。

## Task 5：单 writer 交付守护与四格原生分账

Dependencies: Task 1–4；Parallelizable: 只读复审可并行，守护/提交顺序依赖串行。源码提交前由 root 执行既有 ICODE 工作流，不由计划作者运行。

root实际阶段记录：Task1–4各有效断言RED→GREEN后CODE SPEC→不同QUALITY均零遗留；整片GLOBAL SPEC→不同QUALITY分别实际45方法=43通过/2个native平台跳过，C0/I0/M0。root独立32项portable/guard零跳过、连续20轮每轮18项零跳过、关联208项196通过/12平台跳过；compileall-j1、site、governance、landscape排期和diff检查通过。完整preflight session81741三道通过/exit0（2026-10-11 19:01至19:10 UTC），尚未发布。结束研究沿用上述固定Codex/SRT取舍，仅落地有限观察机制，没有改生产principal/ACL/安装策略，许可证与依赖范围不扩大。四格native与172原生预算仍未验收。

精确发布whitelist为六路径：`tests/windows_private_sibling_fixture.py`、`tests/test_windows_private_sibling_window.py`、`scripts/run_workspace_ci.py`、`tests/test_windows_startup_pin_ci.py`、本文和对应冻结设计。root完成完整守护及fresh secrets/submodule后才`git add -f --`这六路径，核对cached名单、逐文件索引与已审查磁盘字节一致，再按既有授权commit/push main；不得混入其它阶段或新草稿。

交付前核验：LA-2a已独立提交并推送main `fccb526f61bd9e593136c5c47b9792193ae95cf2`。本片与LA-2a六个CODE文件从完整守护开始至发布前SHA256不变，两片共享同一次完整整树守护结果，不把前片提交称为本片原生CI。root随后重新执行secrets及submodule各exit0；本片尚待提交和新的四格日志。

【架构级自检报告】（root软件候选）

- 语法/编译：compileall-j1及实际模块/guard运行通过。
- 依赖/调用链：两个新增测试文件、原native ABI复用及CI必测接线完整。
- 逻辑/边界：四变体三窗由实际controller的fake native测试覆盖，正控/有限拒绝/严格协议分账。
- 异常处理：一次清理、unknown阻断、KI/SE原对象和有限失败脱敏测试通过，不声称覆盖全部原生故障。
- 关联模块：旧DACL/selector/optional语义回归保持；整片两轮审查零遗留。
- 兼容安全：生产后端与ready不改，Nt目录参数仍待native正控。
- 可运行性：已测软件项通过；完整守护三道通过；发布与四格Windows原生待验，不写100%。

- [ ] 新功能有效assertion RED→GREEN逐task留证，完整实施复审 SPEC→不同QUALITY C0/I0/M0；不得用import error/旧源码测试通过代替新行为RED。
- [x] `.venv/bin/python -m unittest tests.test_windows_private_sibling_window.PrivateSiblingPortableTests tests.test_windows_startup_pin_ci`；portable与guard无skip，原native非Windows条件skip另账。
- [x] 新portable class连续20轮；每轮读取返回码且失败立即阻断，禁止最终一轮成功掩盖中间失败。
- [x] 关联回归 `.venv/bin/python -m unittest tests.test_windows_private_dacl_window tests.test_windows_startup_pin tests.test_windows_startup_native tests.test_windows_startup_security_native tests.test_windows_startup_host_identity tests.test_run_workspace_ci tests.test_windows_startup_pin_ci`。保留旧模块/可选skip语义，不修改test_run_workspace_ci旧counts。
- [ ] 完整 `.venv/bin/python scripts/preflight.py` 三道（fresh secrets/vendor integrity/full tests）；不得只 `--only tests` 就声称preflight完整。核对实际 GUARDS 名称、退出码和报告，全部必需通过。
- [x] `.venv/bin/python -m compileall -q -j 1 tests/windows_private_sibling_fixture.py tests/test_windows_private_sibling_window.py scripts/run_workspace_ci.py tests/test_windows_startup_pin_ci.py`；`check_agent_landscape.py`、`check_governance.py`、`check_site.py`、diff whitespace检查。源码仍只在四个授权路径；文档同步范围由root既有任务管理。
- [ ] phase结束刷新研究取舍，引用spec固定Codex `8c0f7011674145da7e10627769fb221c74fbf7a0`、SRT `5507fb0e639c00f845554336ece62e27af5b1bb7`和Apache-2.0原文；不查HEAD不复制依赖。机制采纳、暂缓、不适配沿用spec；不能把计划实现列成当前能力。
- [ ] 按用户已有授权执行root main提交/CI流程。此计划本身不授权任何Git写或CI写，不新增workflow、服务、MSIX/UAC/privilege或不可信principal。
- [ ] 四格 x64/ARM64 × Python3.11/3.12 分别保存完整原始日志，核对每格4variants/12windows且strict wire合法；全部完成才有16variants/48windows。任何格finite正控拒绝、无NTFS、unknownstatus、directoryoptions不兼容、cleanup不确认，都FAIL不skip、不fallback、不撤flag。
- [ ] 本机fake只记software transport；原生created/blocked只记当前宿主FA下窗口能力，均不是securitypass。原片DACL四格不能代替本片；consumer_ready/compatibility_accepted/launch_authorized始终false。

## 计划审查状态与待决精确点

本文提供完整fixture、18方法portable（含四变体精确linecache/sys.settrace获取边界故障矩阵）、2方法native、可导入RED骨架及确切selector/guard接线文本。Python代码块AST解析按各自所属上下文；以linecache内存module运行计划文本的18 portable方法全部通过（18/0failure/0error），没有新源码文件落地，也没有本片实际TDD/native/四格信用。ownership acquisition代次澄清已在冻结spec另经SPEC→不同QUALITY C0/I0/M0；最终计划独立SPEC→不同QUALITY各C0/I0/M0，root完整回读和修订边界回读后允许开始Task1，不授实际实现信用。

2026-10-12计划自查按**真实阶段装配**分别在内存module演练：Task1仅可导入codec/入口stub和两个selected方法；Task2仅最终codec/native acquisition及所列五个方法，未装配Task3controller；Task3在完整helper上临时覆写本文固定回执stub。Task3最终controller方法另覆盖四变体×KI/SE共8个真正`_Creation.create` RETURN-event：local try已退出，已登记slot由outer cleanup承担once close/exact remove，不能把`ledger.claim` RETURN或`return created`执行前的local handler覆盖称为create真正RETURN覆盖。各装配结果如下，独立于最终18方法演练，不授实际源码TDD或Windows信用。

| 计划文本装配 | 实际内存结果 | 验证含义 |
| --- | --- | --- |
| Task1 RED：`validate_wire`返回`{}`、入口返回bytes | 2 run / 2 assertion FAIL / 0 ERROR | codec对象与入口前置拒绝断言有效，无import/attribute错误 |
| Task2 RED：actual class可导入、create一行blocked骨架 | 1 run / 1 assertion FAIL / 0 ERROR | Win32 created结果断言有效 |
| Task2 GREEN：最终codec+native两块、五个Task2方法 | 5 run / 0 FAIL / 0 ERROR | acquisition阶段无需尚不存在的`_run_variant` |
| Task3 RED：最终helper+临时固定合法回执controller | 1 run / 1 assertion FAIL / 0 ERROR | 无实际create调用不能通过controller断言 |
| 最终计划文本 | 18 run / 0 FAIL / 0 ERROR；8 Python blocks AST通过 | 最终组合与故障矩阵可演练，实施时仍须真实RED/GREEN与守护 |

【架构级自检报告（计划候选阶段）】

- 语法/文档：已读冻结spec及实际selector/guard；主要代码块AST与内存18方法通过，仍待独立计划复审。
- 依赖/调用链：真实路径已纠正；新fixture/newtest与required接线明确，旧fixture/生产源码不改。
- 逻辑/边界：三窗正控、ADD独立、actual create/SD/bytes/identity与protocol列明。
- 异常处理：same local try、once close/free、unknown path、reverse cleanup与KI/SE原对象门列明；需实现故障测试验证。
- 关联模块：旧DACL slice/count保护和新prefix/fixtures/subTest守护同步要求明确。
- 兼容安全：Nt目录组合待native正控；四格分账，无security/authority新增信用。
- 可运行性：计划文本内存18方法通过；本片源码、有效TDD、完整守护与四格native均未实施，无100%通过声明。
