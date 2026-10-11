# Windows 内部来源 owner 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development to implement this plan task-by-task. 用户授权 main-only、自主推荐选择；不新建分支/worktree、不重复文档批准。TDD、自SPEC→自QUALITY、独立全片SPEC→不同QUALITY与完整验收仍强制。

**Goal:** 将现有 source 政策绑定实际持有的两组来源对象，不提供启动授权。

**Architecture:** 固定包资源词法定位→真实宿主身份→两个独立backend/pin owner→同HANDLE全链政策→保留live context→跨调用重验→全局逆序一次清理。失败继续阻断卷根，既有策略/native/ABI/UAC不改。

**Tech Stack:** Python3.11+、现有ctypes运输、unittest；编译-j1，无新增依赖/权限。

---

## 前置证据与文件边界

基线main `37f100a0566e9225630e409b8077a1c06789b649`，vendor `21566a589cbe98bd35372a04bbb6ca1c51d8eed2`。四installed观察完成但source政策全部失败（每资源仅root首先拒绝），不能借provenance5/5授启动/兼容。正式[设计](../specs/2026-10-11-windows-source-owner-design.md)与[前片结果](./2026-10-11-windows-installed-chain-observation.md)为边界。

Task1仅新 `src/icode/windows_startup_source.py`、`tests/test_windows_startup_source.py`；Task2仅 `scripts/run_workspace_ci.py` 与 `tests/test_windows_startup_pin_ci.py` 接线。root拥有新设计/本计划、前片计划与 `docs/agent-landscape-live.md`。不修改其他产品模块、probe/wheel父监督、workflow权限、native、vendor或用户文件。已有第三方摘要/签名不成为本片输入。

## Task 1：固定来源与复合 live owner

**Dependencies:** None
**Parallelizable:** No（单写者，职责是一个复合资源生命周期）

- [x] 先建 `SourceInterfaceTests`：以 `find_spec` / callable 断言模块和无参数入口缺失，获得 assertion FAIL/0ERROR。再分组写下面 SourceLocatorTests / SourceOwnerTests，逐组真实RED→GREEN；不把ModuleNotFound、AttributeError或fixture错误算RED，不一次写完产品再补测试。

```python
def test_internal_module_exists(self):
    self.assertIsNotNone(importlib.util.find_spec('icode.windows_startup_source'))
```

- [x] locator与入口按以下完整结构实现；固定资源必须使用当前模块位置，无public injection参数。纯路径判断先于identity/nativeopen。

```python
import os
import sysconfig
from pathlib import PureWindowsPath
from .native_helper import windows_arch_from_platform
from .windows_startup_host_identity import WindowsStartupHostIdentity
from .windows_startup_native import WindowsStartupPinBackend
from .windows_startup_pin import (
    MAX_STARTUP_BYTES, StartupPinError, StartupPinCloseError,
    _local_components, _metadata, pin_startup_file,
)
from .windows_startup_security import (
    StartupSecurityError, _validate_host_sid,
    parse_startup_security, check_startup_security,
)

_MAX_CHAIN_NODES = 32
_MAX_SNAPSHOT_ACES = 512
_RESOURCES = ('helper', 'verifier')

def _installed_resources():
    _local_components(__file__)
    module = PureWindowsPath(__file__)
    if module.name != 'windows_startup_source.py' or module.parent.name != 'icode':
        raise StartupPinError('invalid installed startup package')
    arch = windows_arch_from_platform(sysconfig.get_platform())
    paths = tuple((key, module.parent / 'native' / f'icode-{name}-windows-{arch}.exe')
                  for key, name in (('helper', 'sandbox'), ('verifier', 'provenance')))
    for key, path in paths:
        if not 2 <= 1 + len(_local_components(str(path))[1]) <= _MAX_CHAIN_NODES:
            raise StartupPinError('startup source chain budget exceeded')
    return paths

def pin_installed_startup_sources():
    if os.name != 'nt':
        raise StartupPinError('native Windows startup sources unavailable')
    resources = _installed_resources()
    identity = WindowsStartupHostIdentity()
    host_sid = identity.capture()
    if identity.cleanup_unconfirmed is not False:
        raise StartupSecurityError('startup host identity cleanup unconfirmed')
    _validate_host_sid(host_sid)
    result = PinnedStartupSources(host_sid)
    pending = None
    try:
        for resource, path in resources:
            pending = pin_startup_file(str(path), _backend=WindowsStartupPinBackend())
            result._owners.append((resource, pending))
            pending = None
        result._snapshots = result._verify()
        result._ready = True
        return result
    except BaseException as original:
        if pending is not None:
            pending._close_preserving_exception(original)
        result._close_preserving_exception(original)
        raise
```

构造后 append 失败也不能遗失刚取得的 owner：pending涵盖取得到登记窗口，成功登记后才清空。append之后、清空pending前若中断，pending就是最新资源，先自闭，再composite逆序；既有owner.closed使重复调用不重关句柄/不重试unknown。禁止测试专用公开方法。取得调用本身失败仍由既有pin负责其当次半成品清理，已登记资源由composite负责。

- [x] 同对象校验实现以下算法；不要调用会自闭子owner的revalidate。每次两份SD的entries只计一次各份，即使reader/policy内部再次parse。

```python
def _verify_metadata(owner):
    owner._require_open()
    if not 2 <= len(owner._handles) <= _MAX_CHAIN_NODES or len(owner._handles) != len(owner._baseline):
        raise StartupPinError('invalid startup source chain')
    for handle, baseline in zip(owner._handles, owner._baseline):
        current = _metadata(owner._backend.query(handle),
                            directory=baseline.directory, max_bytes=MAX_STARTUP_BYTES)
        if current != baseline:
            raise StartupPinError('startup source metadata changed')

def _verify(self):
    budget = 0
    snapshots = []
    for resource, owner in self._owners:
        _verify_metadata(owner)
        raws = []
        for handle, baseline in zip(owner._handles, owner._baseline):
            before = _metadata(owner._backend.query(handle),
                               directory=baseline.directory, max_bytes=MAX_STARTUP_BYTES)
            first = owner._backend.query_security(handle)
            second = owner._backend.query_security(handle)
            after = _metadata(owner._backend.query(handle),
                              directory=baseline.directory, max_bytes=MAX_STARTUP_BYTES)
            if before != baseline or after != baseline:
                raise StartupPinError('startup source metadata changed')
            if type(first) is not bytes or type(second) is not bytes or first != second:
                raise StartupSecurityError('startup source descriptor changed')
            budget += len(parse_startup_security(first).entries) + len(parse_startup_security(second).entries)
            if budget > _MAX_SNAPSHOT_ACES:
                raise StartupSecurityError('startup source security budget exceeded')
            check_startup_security(first, role='source', host_sid=self._host_sid,
                                   directory=baseline.directory)
            raws.append(first)
        _verify_metadata(owner)
        snapshots.append(tuple(raws))
    result = tuple(snapshots)
    if self._snapshots and result != self._snapshots:
        raise StartupSecurityError('startup source descriptor changed')
    return result
```

- [x] 实现 class所有公开生命周期，不返回launch/path/SD/SID；单actor由可信caller遵守。

```python
class PinnedStartupSources:
    def __init__(self, host_sid):
        self._host_sid = host_sid
        self._owners = []
        self._snapshots = ()
        self._ready = False
        self._closed = False
        self._close_errors = ()

    def __copy__(self):
        raise StartupPinError('startup sources owner cannot be copied')
    def __deepcopy__(self, memo):
        raise StartupPinError('startup sources owner cannot be copied')
    def __reduce_ex__(self, protocol):
        raise StartupPinError('startup sources owner cannot be serialized')

    @property
    def closed(self):
        return self._closed
    @property
    def close_confirmed(self):
        return self._closed and all(owner.close_confirmed for _, owner in self._owners)
    @property
    def close_errors(self):
        return self._close_errors

    def _require_open(self):
        if self._closed or not self._ready:
            raise StartupPinError('startup sources owner is closed or uninitialized')
    def _resource(self, resource):
        self._require_open()
        if type(resource) is not str or resource not in _RESOURCES:
            raise StartupPinError('invalid startup source resource')
        return dict(self._owners)[resource]
    def content(self, resource):
        return self._resource(resource).content
    def sha256(self, resource):
        return self._resource(resource).sha256
    def revalidate(self):
        self._require_open()
        try:
            self._verify()
        except BaseException as original:
            self._close_preserving_exception(original)
            raise
    def close(self):
        if self._closed:
            return
        self._closed = True
        errors = []
        for resource, owner in reversed(self._owners):
            try:
                owner.close()
            except BaseException as error:
                errors.append(error)
        self._close_errors = tuple(errors)
        if errors:
            for error in errors:
                if not isinstance(error, Exception):
                    raise error
            raise StartupPinCloseError(self._close_errors)
    def _close_preserving_exception(self, original):
        already_closed = self._closed
        try:
            self.close()
        except BaseException:
            pass
        if not self.close_confirmed and not already_closed:
            try:
                BaseException.add_note(original, 'Startup source cleanup unconfirmed')
            except BaseException:
                pass
    def __enter__(self):
        self._require_open()
        return self
    def __exit__(self, exc_type, exc, traceback):
        if exc is not None:
            self._close_preserving_exception(exc)
        else:
            self.close()
        return False
```

允许保留此代码语义的可读性小调整，不可增加外部输入/skip/角色旁路。构造验证真实SID；class本身内部，未ready的手建对象不能取bytes或重验，私有成员不声称抵御同TCB Python篡改。

- [x] 测试fixture复用 `tests.test_windows_startup_pin.FakeBackend` 的真实owner运输边界与 `tests.test_windows_startup_security.descriptor/acl/ace/sid` 原bytes parser；增加backend.query_security返回owned数据（默认admin owner、host或admin写ACE），保留真实pin owner不mock它。每个backend有不同resource label和共同全局calls列表，关闭记录 `(resource, handle)`；可复用数值1..N但必须不同backend。目录角色可扩展N节点fixture，不能用固定handle<4冒充32节点。

精确负控矩阵：两资源×每节点×SD读取两轮/query时点×RuntimeError/KI/SE；构造第二资源每open/query/read失败；政策admin/system/host允许source、other owner/非可信WRITE_DAC或DELETE_CHILD/空DACL拒绝、unknown/parser拒绝；SD第二轮改变、重验时仍合格但raw变更、各metadata字段漂移；每资源节点32通过/33定位拒绝0open，两份SD计数512通过/514失败；正常/body失败叠加每位置close失败（普通/KI/SE），确认仍尝试后续所有资源、全局verifier先helper、每handle一次，unknown永不重试。所有断言主体原exception `is` 保留，hostile __getattribute__/__notes__不遮原错；error notes只固定文字。资源exactstr、closed/unready、copy/deepcopy/pickle分别拒绝且不改变live/close账。

入口/定位测试patch仅os.name、模块__file__、get_platform、真实identity供应和backend工厂，绝不mock check_startup_security/parser/pin owner。核user site含空格/Unicode定位不依赖purelib，错误文件shape/相对UNC/reparse词法/unsafe/不支持arch/过长链在捕获前失败；实际文件打开不存在时失败无fallback；identity错/cleanup未知0open。CLI任意kwargs/JSON传入触发TypeError不触native。原生信用不从fixture推导。

- [x] `.venv/bin/python -B -m unittest tests.test_windows_startup_source -v` 实跑；所有新增便携0skip/F/E，20轮每次独立load suite。再关联pin/native/security/reader/identity/installedchain，compileall-j1/diff、自SPEC后自QUALITY，报RED/GREEN真实次数、类/方法数、两文件SHA256。冻结、不自行提交、不触Task2。

### Task1 冻结软件证据（2026-10-11）

writer自SPEC→自QUALITY均C0/I0/M0，实际六组assertion RED（1、1、1、196、1、1次失败，均0ERROR）后GREEN；该历史为writer记录，root未重演历史RED。最终Interface3/Locator3/Owner18，共24便携方法；source207行、test461行。root已全文回读两新文件与上下游，实际24 PASS、20轮480 PASS/0skip/F/E；新+六旧关联241 run=231 PASS/10既定Windows平台skip，compileall-j1通过。Task1不授权Windows原生/安装兼容/launch，Task2与全片独立双审/完整preflight仍待。

冻结SHA256：source `8da1e1d4d6728add21d36ff925e8ad7bdc99b45e04bd42232d409399d9f90813`；test `49ac8d53e204c790235d54dabc23df3a9e3b7e886d77fcd8733859084195a58e`。正式设计 `1a81a7c0e7f06d938a940be6b0f18b86ce3472cecadbe4cea7ed759be8435a9a`。四文档checker0疑似/site首轮通过（9外链未fetch）。没有旧产品策略/native/workflow/vendor变更。

## Task 2：必需CI接线

**Dependencies:** Task 1
**Parallelizable:** No（依赖真实类/方法数和冻结源）

- [x] 先在 paired guard加Task1实际三类和真实counts，以及 DEFAULT新module一次/selector完全unique断言，跑出assertion FAIL/0ERROR；保持所有旧类与native counts6/2/2。既有skip矩阵必须实际覆盖新增类，method/class/module选择、setUp/tearDown/Class/Module和nested subTest不能变可选。

```python
# scripts/run_workspace_ci.py startup_pin_tests portable tuple 追加
'tests.test_windows_startup_source',
# main 的 selected_pin_ids prefix tuple 追加
'tests.test_windows_startup_source.',
# tests/test_windows_startup_pin_ci.py PORTABLE_CLASSES 追加
'tests.test_windows_startup_source.SourceInterfaceTests',
'tests.test_windows_startup_source.SourceLocatorTests',
'tests.test_windows_startup_source.SourceOwnerTests',
# selected prefix追加 'tests.test_windows_startup_source'；恰一次断言
self.assertEqual(ci.DEFAULT_MODULES.count('tests.test_windows_startup_source'), 1)
```

PORTABLE_COUNTS取真实loader，不固定预估；DEFAULT经既有startup_pin_tests('posix')展开，不另加一次造成重复。最小paired两文件GREEN，不改其它R3选择/可选/native含义或workflow。

- [x] 关联source/startupguard/workspaceci/旧运输全跑，20轮完整posix startup+guard0skip/F/E，取实数不估计；syntax-j1/diff、自SPEC→自QUALITY，冻结两文件并报告四功能摘要。Task1新模块未再变更。

## Task 3：全片验证、发布和原生分账

### Task2 实际冻结及全片窗口（2026-10-11）

Task2仅既有两文件，writer实际guard11 methods/87 assertion RED/0ERROR/0skip后GREEN11 PASS；自SPEC→自QUALITY各C0/I0/M0。实际loader source类3/3/18、新module24；posix231/nt241均unique，source在selector/DEFAULT恰一次，旧207/217IDs与guard11/native6/2/2/optional语义全部保留。root全文回读两文件diff与调用链、实际九模块279 run=269 PASS/10正常Windows native skip；20轮每次独立load实际posix startup+guard242/轮、4840 PASS/0skip/F/E。四功能compileall-j1与diff通过；Windows清单884 unique、新source24为位置645–668仅为root词法loader，不是原生执行。

Task2 SHA256：CI `074a747e28f9e3b4f9ee58f423c78e42ca9ad7d488df6cd351a516a2cf5cbd19`；guard `6f1b3f60e54d91c4e4b77dcb4bc24a035417bd487797e4797caf53ece7f3f26b`；Task1两摘要/设计摘要未变。全片独立SPEC已C0/I0/M0，另实际279关联与4840轮次；独立内存第二backend构造RuntimeError/KI/SE原身份/第一owner回收、禁止child.revalidate后正常、real nested skip CI1均另核。不同QUALITY现进行；root完整preflight session39952针对同冻结候选并行启动，①密钥②子模块通过，③全仓测试仍在运行，尚未授完整通过。若审查需要改功能则重新冻结/双审/完整守护，不借旧候选信用。

**Dependencies:** Task 1, Task 2
**Parallelizable:** No（最终候选冻结）

- [x] root全文回读四功能及上下游，独立SPEC→不同QUALITY所有C/I/M解决后重新核冻结/关联/20轮。任何产品源改动需重新冻结和审查；研究不能替代测试。
- [x] 完整 `CMAKE_BUILD_PARALLEL_LEVEL=1 MAKEFLAGS=-j1 .venv/bin/python -u scripts/preflight.py` 三道exit0；四新/关联文档check_consistency、site两轮、diff/秘密/子模块检查。七维报告仅真实通过范围，不报Windows/整体100%。
- [ ] root exact add四功能及关联文档（ignored新docs需add-f确切路径）、commit/push main与lsremote；每阶段软件通过才发布，不混用户改动。原生CI对新source便携方法/fixture必需执行，既有安装观察仍独立；新consumer Windows正控/叶负控及普通host安装兼容未证明就保留缺口，继续下一原生/卷根合同片，不止于软件。

自审：接口、定位、identity、双owner、同对象政策、budget、异常/close、copy/pickle分别落Task1；真实选择和不可skip落Task2；双审/全验/main发布与原生分账落Task3。根兼容和publisher/UAC未塞进软件通过。

### 最终软件候选验证（2026-10-11）

不同全片QUALITY已完成，C0/I0/M0；独立实际279 run=269 PASS/10既定平台skip、20轮4840 PASS/0skip/F/E，另核parser中断与关闭未知的异常身份、全局逆序一次回收和不重试。SPEC与QUALITY为不同审查者，均未修改冻结文件。root额外bootstrap/packaged-skill32项PASS/0skip；四功能及设计摘要与上述冻结一致。

root完整preflight session39952已结束exit0，密钥、固定子模块、全仓unittest三道均通过。预检成功路径没有公开全仓测试数量，因此不猜计数。上文“QUALITY进行/全仓运行”为历史窗口。软件通过不授Windows新consumer原生执行、普通安装兼容、publisher/加载边界、首UAC或R2/R3整体通过。

【架构级自检报告】（仅本软件候选范围）

- 语法/编译：四功能compileall-j1、diff检查通过。
- 依赖/调用链：复用既有pin、身份、reader与policy；新模块一次进入必需CI选择。
- 逻辑/边界：269关联PASS、20轮4840 PASS；两资源/预算/漂移边界覆盖。
- 异常处理：取得、验证、关闭及中断故障矩阵通过；未知关闭不重试，不吞原异常。
- 关联模块：旧207/217选择ID、既定平台skip及可选语义保留；32安装关联PASS。
- 兼容安全：旧policy与setup/spawn拒绝门不变；普通Windows安装兼容仍待验证。
- 可运行性：本地便携及完整预检通过；新消费者Windows原生、首UAC及R2/R3整体未通过，不能声称100%。

---
**Execution Mode:** serial
