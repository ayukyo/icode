# Windows 原宿主身份 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development task-by-task。用户明确main直接开发，不创建分支/worktree；单写者、真实TDD、自SPEC/QUALITY、root回读、独立SPEC后不同QUALITY，root最终提交。

**Goal:** 只读捕获当前宿主primary token的canonical SID，确认一次回收后返回，补身份读取来源而不授启动权限。

**Architecture:** 独立内部ctypes owner，无PID/HANDLE/SID输入；owned TOKEN_USER buffer内有界定位SID，复用现有 `_sid`。旧管道、Job、pin/backend、权限parser保持不变，整链消费者另片。

**Tech Stack:** Python3.11/3.12、ctypes/unittest、固定Win32 API，标准库，编译-j1。

具体合同为[已审设计](../specs/2026-10-11-windows-host-identity-design.md)。基线main `0d40c25`；该SHA四Windows运输格日志已实际核775 tests/20 optional skip及必需6+2原生零skip，前置门通过。完整CI/Reviewer/R2/R3不因运输通过而关闭。

## Task 1：只读owner与便携故障合同

**Dependencies:** None（上述运输前置门已过）
**Parallelizable:** No（单写者、冻结后再接CI）

- [x] 新 `tests/test_windows_startup_host_identity.py`，先运行接口存在性assertion RED，不用ImportError冒充产品失败：

```python
import importlib.util
import unittest

class HostIdentityInterfaceTests(unittest.TestCase):
    def test_module_and_capture_interface(self):
        self.assertIsNotNone(importlib.util.find_spec('icode.windows_startup_host_identity'))
        from icode import windows_startup_host_identity as module
        cls = getattr(module, 'WindowsStartupHostIdentity', None)
        self.assertTrue(callable(cls))
        self.assertTrue(callable(getattr(cls, 'capture', None)))
```

运行 `.venv/bin/python -B -m unittest tests.test_windows_startup_host_identity -v`；预期明确assertion失败/0 ERROR。随后按设计补自有ctypes buffer+fake callable DLL，真实transport断言RED，再实现，不倒填RED。

- [x] 新 `src/icode/windows_startup_host_identity.py`，以下为完整控制流参考；实现可用同等更小结构，不扩大合同：

```python
import ctypes
import os
from .windows_startup_security import StartupSecurityError, _sid

_U32, _I32, _VOID = ctypes.c_uint32, ctypes.c_int32, ctypes.c_void_p
_INVALID = _VOID(-1).value
_TOKEN_QUERY, _TOKEN_USER, _MAX_BYTES = 8, 1, 4096
_CLEANUP_NOTE = 'Startup host token cleanup unconfirmed'

class _TokenUser(ctypes.Structure):
    _fields_ = [('Sid', _VOID), ('Attributes', _U32)]

class WindowsStartupHostIdentity:
    def __init__(self):
        if os.name != 'nt':
            raise StartupSecurityError('native Windows startup host identity unavailable')
        self.cleanup_unconfirmed = False
        try:
            self._kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            self._advapi32 = ctypes.WinDLL('advapi32', use_last_error=True)
            signatures = (
                (self._kernel32, 'GetCurrentProcess', [], _VOID),
                (self._advapi32, 'OpenProcessToken', [_VOID, _U32, ctypes.POINTER(_VOID)], _I32),
                (self._advapi32, 'GetTokenInformation',
                 [_VOID, _I32, _VOID, _U32, ctypes.POINTER(_U32)], _I32),
                (self._kernel32, 'CloseHandle', [_VOID], _I32),
            )
            for library, name, arguments, result in signatures:
                function = getattr(library, name)
                function.argtypes, function.restype = arguments, result
        except Exception:
            raise StartupSecurityError('native Windows startup host identity API unavailable') from None

    @staticmethod
    def _call(function, *arguments):
        try:
            return function(*arguments)
        except Exception:
            raise StartupSecurityError('startup host identity native invocation failed') from None

    def _release(self, output, original=None):
        if not output.value or output.value == _INVALID:
            return
        self.cleanup_unconfirmed = True
        try:
            if not self._call(self._kernel32.CloseHandle, output.value):
                raise StartupSecurityError(_CLEANUP_NOTE)
            self.cleanup_unconfirmed = False
        except BaseException:
            if original is None:
                raise
            try:
                BaseException.add_note(original, _CLEANUP_NOTE)
            except BaseException:
                pass

    def capture(self) -> str:
        if self.cleanup_unconfirmed:
            raise StartupSecurityError(_CLEANUP_NOTE)
        output = _VOID()
        try:
            process = self._call(self._kernel32.GetCurrentProcess)
            if not process:
                raise StartupSecurityError('startup host process query failed')
            opened = self._call(self._advapi32.OpenProcessToken,
                                process, _TOKEN_QUERY, ctypes.byref(output))
            if not opened or not output.value or output.value == _INVALID:
                raise StartupSecurityError('startup host token query failed')
            returned = _U32()
            sized = self._call(self._advapi32.GetTokenInformation,
                               output.value, _TOKEN_USER, None, 0, ctypes.byref(returned))
            last_error = self._call(ctypes.get_last_error)
            minimum = ctypes.sizeof(_TokenUser) + 8
            if sized or last_error != 122 or not minimum <= returned.value <= _MAX_BYTES:
                raise StartupSecurityError('invalid startup host token sizing receipt')
            capacity = returned.value
            buffer = ctypes.create_string_buffer(capacity)
            received = self._call(self._advapi32.GetTokenInformation,
                                  output.value, _TOKEN_USER, buffer, capacity,
                                  ctypes.byref(returned))
            if not received or not minimum <= returned.value <= capacity:
                raise StartupSecurityError('invalid startup host token returned window')
            raw = buffer.raw[:returned.value]
            header = _TokenUser.from_buffer_copy(raw)
            offset = (header.Sid or 0) - ctypes.addressof(buffer)
            if not ctypes.sizeof(_TokenUser) <= offset <= returned.value - 8:
                raise StartupSecurityError('invalid startup host SID offset')
            result, _end = _sid(raw, offset, returned.value)
        except BaseException as original:
            self._release(output, original)
            raise
        self._release(output)
        return result
```

普通解析/分配/复制故障同样不能泄露原异常；实现须用固定错误边界覆盖上述参考代码内native调用之外的普通故障，同时保持原BaseException身份。native ABI无_pack_；4096内部预算、122命名常量，具体生产常量命名遵循同目录风格。输出无效时不关闭；每个合法output回收1次。不把示例代码等同已验证实现。

- [x] 便携成功样例：SID header/body位于实际owned buffer，第二次返回窗口小于capacity也可合法；非零Attributes、非零padding、SID不紧邻header、body恰结束returned、重复正常capture各新token一次close。signature明确四API，用GetCurrentProcess所得值原样传OpenProcessToken，TOKEN_QUERY8/TokenUser1，pseudo零close，不调用SID native API或env/account。
- [x] 所有拒绝样例：NULL/INVALID open output、false及output后OSError/KI/SystemExit、sizing意外success/last-error非122/长度小大、second false/零/小/超capacity、SID pointer NULL/低地址/header内/尾端/窗外、rev/count/truncated body；body失败仍close1，普通固定文案/原KI或SE身份；无任意危险pointer解引用。
- [x] close非零确认；零/OSError/KI/SE/关闭后抛异常均unknown；主体+cleanup错误固定note（含hostile note），unknown实例再capture零API零close，无关闭输出则zero-close。明确输出写入后的Python行事件故障测试，不宣称字节码原子性。
- [x] 全suite命令同上GREEN；新便携类串行20轮实际method counts、0 skip/F/E。source/test全文自SPEC和QUALITY，root全文回读和关联pure parser/reader suites。记录实际RED/GREEN，不改其它模块或提交。

## Task 2：原生身份正控与必需CI

**Dependencies:** Task 1（软件合同冻结）
**Parallelizable:** No（依赖最终测试类/方法数）

- [x] 仅同一新测试文件加 `@unittest.skipUnless(os.name == 'nt', 'Windows native identity required')` 原生类，实际构造/重复capture检查canonical str及cleanup=false；独立OpenProcessToken(TOKEN_QUERY)/GetTokenInformation/IsValidSid/ConvertSidToStringSidW校验正控，独立一次CloseHandle/LocalFree核回执，全部native API/fixture失败在nt上FAIL而非skip。核x64/ARM64 ABI offsets0/8/size16。独立正控SID API只消费先界定buffer范围的pointer，不与产品parser循环自证，不修改宿主token/ACL。
- [x] 完整回读 `scripts/run_workspace_ci.py`、`tests/test_windows_startup_pin_ci.py`、`tests/test_run_workspace_ci.py` 后最小接线：`startup_pin_tests`始终选择本片实际全部便携类，nt另选择原生类；required prefix加 `tests.test_windows_startup_host_identity.`；旧纯/运输/共享锁和optional语义不变。不改workflow六格或CI权限。

```python
# CI合同先用真实loader检测唯一性，不用写在job名中的版本当运行证明。
suite = unittest.defaultTestLoader.loadTestsFromNames(startup_pin_tests('nt'))
ids = list(_leaf_test_ids(suite))
self.assertEqual(len(ids), len(set(ids)))
self.assertTrue(any(value.startswith('tests.test_windows_startup_host_identity.') for value in ids))
```

- [x] 更新实际类方法计数/唯一覆盖合同，新增本片method、class/module fixture、nested subTest skip拒绝测试真实RED→GREEN，旧optional仍0退出；具体新增计数只能取冻结Task1真实loader。运行 `.venv/bin/python -B -m unittest tests.test_windows_startup_host_identity tests.test_windows_startup_pin_ci tests.test_run_workspace_ci -v`；Linux本片native只平台skip，便携及必需skip负控全部PASS。

## Task 2b：同批Windows验收的输出夹具小修

**Dependencies:** Task 2（冻结后另一个单写者，绝不并发改测试）
**Parallelizable:** No（纳入最终候选审查）

本项来自实际运输CI两次readerthread异常的[已核独立诊断](../windows-ci-verifier-encoding-diagnostic-2026-10-11.md)，是确保同批Windows验收不忽略独立校验器输出，不在身份产品中扩大范围。仅改 `tests/test_contract_engineering.py` 的 `test_native_legacy_code_actual_cp_to_independent_pack` 和 `tests/test_execution_binding_pack.py` 的 `test_real_bound_partial_pack_is_portable_after_code_disappears`，约十余行；保持产品诊断/校验退出码、其余fixture及全阶段冻结源不变。

- [x] 完整读两测试文件及真实pack_verify.main诊断上下文。只读受控subprocess.run替身仅对argv含本包verify.py返回exit0/stdout=None，其余调用真实透传，记录现夹具误放行；用新增输出断言证明该损失必须失败，不虚构Windows实跑。
- [x] 两处verify argv改 `[sys.executable, '-I', '-B', '-X', 'utf8', str(pack / 'verify.py'), str(pack)]`，第一处parent增加 `encoding='utf-8'`，第二处已有UTF8保持；不加errors=replace。exit0之后分别断言stdout确为非空str、包含 `证据包校验通过`、对应工单及 `已核验`（源fixtures分别ENG-CONTRACT与pack-bind）。明确实际输出匹配这三个字段，不靠任意非空信息过关。

```python
self.assertIsInstance(proc.stdout, str)
self.assertIn('证据包校验通过', proc.stdout)
self.assertIn('工单：pack-bind', proc.stdout)
self.assertIn('已核验', proc.stdout)
```

- [x] 实跑 `.venv/bin/python -B -m unittest tests.test_contract_engineering.TestContractEngineering.test_native_legacy_code_actual_cp_to_independent_pack tests.test_execution_binding_pack.BindingPackTests.test_real_bound_partial_pack_is_portable_after_code_disappears -v`；受控stdout=None各明确assertion失败/0ERROR，恢复后两既有test全部通过。记录实际负控/正常输出，不永久引入故障替身/宽松解码或额外进程框架。
- [x] 单点两文件diff/compileall-j1、自SPEC/QUALITY、root回读差异；全片独立审查和新完整preflight一并覆盖。新SHA四Windows日志须另外确认原两readerthread异常消失；Ubuntu成功不替代此项。

## Task 3：全片验证、发布和新SHA原生核对

**Dependencies:** Task 1, Task 2, Task 2b
**Parallelizable:** No（冻结候选审查后发布）

- [x] root关联 `.venv/bin/python -B -m unittest tests.test_windows_startup_host_identity tests.test_windows_startup_security tests.test_windows_startup_security_native tests.test_windows_startup_pin tests.test_windows_startup_native tests.test_windows_startup_pin_ci tests.test_run_workspace_ci tests.test_ci_workflow_contracts -v`，便携20轮0skip/F/E、compileall -q -j1触及源/测试/selector、diff格式检查；旧源摘要不变。
- [x] 全片独立SPEC后不同QUALITY均解决C/I/M；阶段结束独立只读研究刷新本片固定证据，记采纳/暂缓/不适配，research不代实现或Windows信用。
- [x] `CMAKE_BUILD_PARALLEL_LEVEL=1 MAKEFLAGS=-j1 .venv/bin/python -u scripts/preflight.py`新完整三道exit0，站点/文档两轮和七维实际报告；root精确git add源码测试selector及相关docs（docs必要add-f），commit/push main并ls-remote确认，不由agent提交，不上传KEY或无关改动。
- [x] 新SHA四Windows workspace逐格核实际capture方法/fixture/subTest非skip与日志；失败先修根因，Win10/普通host未跑不授信用。发布前Linux只有portable信用，发布后原生证据另记；纯身份不授整链/UAC/R2/R3。

**Execution Mode:** serial

## main 发布与四格原生刷新

后续同SHA provenance [38139112765](https://github.com/ayukyo/icode/actions/runs/38139112765) 已5/5success：validate114469093957；四安装x64/3.11=114471521040、x64/3.12=114471521064、ARM/3.11=114471521101、ARM/3.12=114471521089。root逐四日志核安装资源解析、密码学来源、verifier字节绑定/offline校验、实际密码学负控/direct-volume、元数据与setup/commands拒绝等实际PASS。下文“当时安装仍运行”为旧窗口；这些仅新SHA安装/来源/静态信用，不证明新整链观察（尚在开发）、UAC或R2/R3。

main `90704b41439c025d7f5ff9f8689db3b7b208cc91` 已实际commit/push，ls-remote相同且发布后工作区干净。最后两轮六文档0疑似、site两轮通过（9外链未fetch）、密钥单道通过、cached格式通过及六冻结hash一致；完整三道见12:19记录。精确12文件1189+/12-，无KEY/子模块/权限/旧生产源变更；git add首次因全局docs忽略返回1，root核实际12 staged并对确切docs add-f后提交，未扩scope。

[CI38139112777](https://github.com/ayukyo/icode/actions/runs/38139112777) 四Windows workspace全部实际success；root分别回读完整日志并独立按该SHA selector重建815唯一leaf，首段progress每格815=795 PASS/20 optional skip。新身份独立OS正控/ABI两方法1-based608/609都是`.`，两校验夹具652/670都是`.`；每格无required skip、ReaderThread/UnicodeDecodeError/_readerthread，随后junction3/leased75也通过。

| 实际格 | job |
| --- | --- |
| x64/Python3.11 | 114469094582 |
| x64/Python3.12 | 114469094615 |
| ARM64/Python3.11 | 114469094699 |
| ARM64/Python3.12 | 114469094644 |

独立观察者确认整个CI46 completed=41success/2Reviewer failure/3既有skip；Reviewer两格仍10035/wait_expired、deny=false/credit=false，不视network-DENY或R2/R3通过。宿主身份与输出夹具本片hosted runner限定门已过；Win10/普通host、整链、protected/加载/UAC与模型一致性不因本片关闭。provenance新SHA安装四格当时仍运行，不能沿用0d40 credit。

## 全片冻结观察（软件检查完成，发布和原生核对另记）

最终软件检查：2026-10-11 12:19 UTC，完整preflight session25375退出0，密钥、固定子模块、全仓测试三道均通过；守护隐藏成功测试正文，未推断全仓方法数量。下面“尚在运行/审查尚未执行”为各自历史窗口，以本条为当前刷新。Task2/2b勾选只表示软件实现、负控与审查完成；两处Windows readerthread异常是否消失和新身份两项原生检查仍须新SHA四格日志确认。六功能摘要保持，发布前再跑文档/站点两轮与密钥检查。

【架构级自检报告】（本软件候选范围）
- 语法/编译：六功能文件compileall -j1、diff检查通过。
- 依赖/调用链：旧parser/reader/pin及CI成对关联239 run，229 PASS/10 Windows平台skip。
- 逻辑/边界：177便携/CI方法20轮3540 PASS，窗口/所有权/未知回收负控通过。
- 异常处理：故障合同及丢失stdout两明确assertion FAIL/0 ERROR负控通过；不宣称任意中断全覆盖。
- 关联模块：六功能文件独立SPEC后不同QUALITY均C0/I0/M0；无旧生产源/子模块/权限修改。
- 兼容安全：原有便携合同和全仓守护通过，Windows兼容待新SHA原生，不新增依赖或提权。
- 可运行性：Linux软件测试可运行；Windows原生和完整WP0b/R2/R3尚未验收，不报100%。

全片审查刷新：独立SPEC及随后不同QUALITY均C0/I0/M0，六功能摘要全部匹配；QUALITY实际80 run=78 PASS/2 Windows平台skip，loader166/176唯一、loststdout两负控各1assertionFAIL/0ERROR，共用deepcheck与strictUTF8参数检查通过。两审均完整回读六文件与设计/计划；此仅软件候选审查，25375全仓守护及新SHA原生仍分别待验。

独立全片SPEC已C0/I0/M0，六冻结摘要匹配；实际80 run=78PASS/2平台skip、loader166/176unique及loststdout两负控各1assertionFAIL/0ERROR。随后不同QUALITY已启动，root新完整preflight25375的密钥/子模块两道实际通过，全仓测试仍在运行；未授最终三道或新原生信用。

Task2b仅两个既有tests11+/3-：-I/-B保留，显式-Xutf8与parent严格UTF8、stdout类型/成功/工单/已核验语义；旧lost-stdout误放行2，经新合同各assertionFAIL/0ERROR，真实2PASS与共用helper deepcheck1PASS；临时观察器漏return所致AttributeError已修正且未落盘，不计产品失败。root独立回读diff及两完整相关调用链、再跑loststdout实际2 assertionFAIL/0ERROR与整批239 run=229 PASS/10Windows平台skip；不是修复后Windows运行。fixture摘要分别 `743664c2d669356b00acde2d7420b31fb6ba788130201518a6fb855499018211` / `98da4dc4f1f1db3c67edd8ac351907199674fd95b0e8204e98f2d00c6573ec1f`。

root独立实跑startup166+guard11，串行20轮3540 PASS/0skip/F/E；实际loaderposix166/166unique、nt176/176unique。所有触及源/测试/selector compileall -q -j1与tracked格式检查通过。新完整preflight session25375已经启动，未完成不预授三道通过；全片SPEC进行中，随后不同QUALITY，不复用Task1双审替全片批准。

阶段结束独立只读研究12:05–12:09 UTC沿同固定Codex/SRT/Apache2（未刷新HEAD/完整二十名单），root此前已另核固定raw与Microsoft原文。采纳budget/returned window/owned copy及实际新readonlyowner，拒绝全访问/裸SID/uncheckedcleanup，暂缓整链、线程effective身份、组AccessCheck及UAC。nativeoracle预证明SID全body范围再独立OS转换与cleanupreceipt，但仅覆盖当前实际主token和其稳定假设，4096/64bit布局为本片合同，不声称所有authority显示格式/impersonation/任意中断/整链授权。无复制源、新依赖/权限或新方案扩展，具体固定来源见设计，实际新Windows两方法仍待发布后四格。

计划自审：范围只覆盖[身份设计]的独立capture子片，后续整链明确不在本片；源码/测试/CI成对，零外部身份参数，具体API、控制流、命令及负控明确，无新增依赖/权限或原生失败回退。用户main/自动继续指令覆盖skill默认worktree和逐步用户批准建议，其余TDD/双审门保留。

## Task1 已冻结软件履历

以下保留Task1结束窗口；Task2后续观察：单写者已冻结portable37原字节及生产源，新增native2和CI接线。presence/selector真实3 assertion FAIL/0ERROR；旧prefix对新body/fixture/nestedskip的三方法真实97 subTest assertion FAIL/0ERROR→GREEN。三模块77 run=75 PASS/2 Linux平台skip；posix166/nt176 unique leaves，guard11，177 portable/CI PASS及37+11串行20轮960 PASS/0skip/F/E。root已回读新增native完整class、selector及pairedCI差异；全片独立审查、Task2b夹具小修和新完整preflight尚未执行，不先授通过。Task2 source摘要保持，身份测试新 `105d8e13e14ecd127ae193b9e0046f8e8055cd6e3f5977098e19a9abc318ad3f`、selector `212339ee66d79a7ce83cf15351321a015343f11ca604d6387711bfaad5f4e0f0`、pairedCI `9c270de195dffa9989757fabe677ebbc2d4ff3826342ee698fb34b11f0bf74be`；test_run_workspace_ci未修改。native2未在Linux运行，软件实现不代新SHA Windows门。

接口1 assertion RED→GREEN1；运输扩展30 run/29 assertion FAIL→构造最小GREEN，再actualcapture5 run/1 assertion FAIL→GREEN30；复制夹具属性被ctypes覆盖的3失败是测试错误，修__getattribute__后恢复，不计产品RED；最终37方法（Interface1/Constructor4/Transport32）。单写者内置SPEC/QUALITY通过，root全文回读源120/test555及37suitePASS、关联100PASS和串行20轮740PASS/0skip/F/E，compileall-j1通过。独立SPEC初C0/I1/M0：缺类/capture直接导入或访问导致ERROR，writer仅改getattr/assertcallable，内存两个缺失各1assertionFAIL/0ERROR恢复37PASS；SPEC复核C0/I0/M0，随后不同QUALITYC0/I0/M0，摘要匹配。源 `15f056759efa239aae888fe220851467f4d7bf32a9167efa5e35f0fe631c9be1`，测试 `8e261611d57d5fb58025859c46413498d969d6c5fb0c3fdea9c234fd8178adad`；pure_sid与SDreader源摘要保持。Task1软件合同完成但未发布；Task2新增native类之前的测试摘要单独保留历史，Task2仍待、不授原生或完整阶段。
