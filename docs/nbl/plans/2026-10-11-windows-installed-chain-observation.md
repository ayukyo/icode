# Windows 已安装来源整链观察 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development task-by-task。用户明确main直接开发，无分支/worktree；仅一个写者，任务内TDD及自SPEC→QUALITY，最终root独立SPEC后不同QUALITY、验证、提交推送。

**Goal:** 在真实已安装Windows wheel中只读观察helper/verifier与全部祖先的固定source权限策略，有限脱敏记录拒绝而不授启动。

**Architecture:** 测试专用script复用既有pin/运输/parser/policy/identity；owned数据、严格有限JSON和raw-byte监督分层。产品模块/ABI/策略不改。

**Tech Stack:** Python3.11/3.12、标准库、unittest、已有Win32 ctypes；编译-j1。

[设计](../specs/2026-10-11-windows-installed-chain-observation-design.md)冻结92e915f42a8f552d2e018f32c4a4055f8bf3a78e3ed77e9db531f874c665ec13。身份main90704四Windows格是实现前置门，必须实际全通过才开始Task1，不能因x64两格通过推断ARM。设计首SPEC I2已修后C0/I0/M0，不同QUALITY另记；研究固定Codex/SRT及Apache2，无复制代码/新依赖/提权。

## 文件职责

当前前置门已实过：设计SPEC后不同QUALITY均C0/I0/M0，QUALITY关联63PASS；root独立逐四Windows日志815/20、native608/609=`..`及fixture652/670通过、ReaderThread0，具体job见[身份发布记录](./2026-10-11-windows-host-identity.md)。开始Task1只授这些限定前置门，不授新探针、安装权限、启动或R2/R3。开头“待四格/不同QUALITY另记”为最初窗口保留。

| 文件 | 本片修改 |
| --- | --- |
| scripts/probe_windows_installed_chain.py | 新增仅测试专用定位/同HANDLE观察/有限回执和严格validator |
| tests/test_windows_installed_chain.py | 新增全部便携TDD/故障/预算/脱敏合同；无平台skip |
| scripts/run_windows_wheel_ci.py | 最小新增有界调用与严格回执消费，proof+verifier模式既有安装门后 |
| tests/test_windows_bootstrap_binding.py | 更新原真实main安装模拟链，新增观察失败不导出/调用顺序合同 |
| scripts/run_workspace_ci.py | 选择新便携测试一次并纳入必需method/fixture/subTest skip阻断 |
| tests/test_windows_startup_pin_ci.py | 配对loader/skip合同；旧全部选择和optional语义不变 |

源码windows_startup_*、nativeHelper、workflow/权限、固定子模块不改。新test脚本imports不得运行API；新fixture没有实际Windows信用。源码6项功能按单写者Task1→Task2串行，独立只读研究/CI观察可并行。

## Task 1：只读观察、精确回执与便携负控

**Dependencies:** 90704身份四Windows格实际通过；设计SPEC与不同QUALITY通过
**Parallelizable:** No（先冻结新script/test供接线）

- [x] 新测试先证明模块和callable接口assertion RED（0 ImportError/ERROR），然后只实现最小接口GREEN；接口固定 `_installed_resources`, `_observe_resource`, `probe`, `validate_wire`, `main`，内部参数仅供trusted script/便携fake，不增加CLI外部SID/path/role输入。

```python
def test_interface(self):
    self.assertIsNotNone(importlib.util.find_spec('scripts.probe_windows_installed_chain'))
    from scripts import probe_windows_installed_chain as api
    for name in ('_installed_resources', '_observe_resource', 'probe', 'validate_wire', 'main'):
        self.assertTrue(callable(getattr(api, name, None)))
```

命令 `.venv/bin/python -B -m unittest tests.test_windows_installed_chain -v`，真实RED/GREEN写履历；后续行为测试同样先断言失败，不能只有缺导入/fixture异常。

- [x] 固定实现定位：导入实际installed icode，`Path(icode.__file__)` 与 `Path(sysconfig.get_paths()['purelib'])` 均要求词法绝对本地盘路径/无`..`，不得先resolve/abspath消除异常成分；包必须为purelib下固定 `icode/__init__.py`，不能只接受任意同名字文件。架构只用现windows_arch_from_platform。构造固定native两文件，先核每资源root+components≤32，禁止缺失资源回退、环境/CWD/PATH或bundled_windows_helper/provenance执行调用。相对/越界/同名其它包/Unicode合法路径/两架构均有便携正负控；真实打开不存在路径由pin失败。

```python
def _installed_resources():
    import icode
    from icode.native_helper import windows_arch_from_platform
    package_file = Path(icode.__file__)
    purelib = Path(sysconfig.get_paths()['purelib'])
    if (not package_file.is_absolute() or not purelib.is_absolute()
            or '..' in package_file.parts or '..' in purelib.parts
            or package_file != purelib / 'icode' / '__init__.py'):
        raise ValueError('invalid_installed_location')
    arch = windows_arch_from_platform(sysconfig.get_platform())
    native = package_file.parent / 'native'
    return arch, (('helper', native / f'icode-sandbox-windows-{arch}.exe'),
                  ('verifier', native / f'icode-provenance-windows-{arch}.exe'))
```

实际定位仍用现 `_local_components` 校验本地卷/成分；此代码按平台Path语义，portable定位测试用真实临时目录或patch该边界，不把LinuxPath冒充WindowsAPI。

- [x] 类别固定admin/system优先host，之后well-known公共类别，未知一律other；owner只admin/system/host/other。mutation位复用现security私有 `_MUTATION_ACCESS_MASK/_DELETE_CHILD`，不另维护更宽或更窄安全政策。仅在成功query/parse之后以下独立check调用捕获已知拒绝，query_security的任何错误不可捕获降级：

```python
_POLICY_REASONS = {
    'startup security owner is not trusted for role': 'owner_untrusted',
    'untrusted ACE permits startup mutation': 'mutation_untrusted',
    'empty DACL cannot establish usable startup security': 'empty_dacl',
}

def _policy_result(raw, host_sid, directory):
    try:
        check_startup_security(raw, role='source', host_sid=host_sid, directory=directory)
    except StartupSecurityError as error:
        # Only this known pure-policy invocation is classified.
        reason = _POLICY_REASONS.get(str(error))
        if reason is None:
            raise
        return reason
    return 'pass'
```

测试真实构造supported SD交叉核policy：可信source host/ADMIN/SYSTEM、OWNER RIGHTS、公共mutation拒绝、empty DACL、目录DELETE_CHILD vs文件非mutation、继承/deny不抵消。reader预parse失败及与LocalFree未确认复合时都FAIL，不需、也不可取得未返回raw。

```python
_PUBLIC_TRUSTEES = {
    'S-1-1-0': 'everyone', 'S-1-5-11': 'authenticated_users',
    'S-1-5-32-545': 'builtin_users', 'S-1-3-0': 'creator_owner',
    'S-1-3-4': 'owner_rights',
}

def _owner_category(sid, host_sid):
    if sid == 'S-1-5-32-544':
        return 'admin'
    if sid == 'S-1-5-18':
        return 'system'
    return 'host' if sid == host_sid else 'other'

def _entry_records(entries, host_sid, directory):
    mutation = _MUTATION_ACCESS_MASK | (_DELETE_CHILD if directory else 0)
    result = []
    for entry in entries:
        category = _owner_category(entry.sid, host_sid)
        if category == 'other':
            category = _PUBLIC_TRUSTEES.get(entry.sid, 'other')
        result.append(dict(allowed=entry.allowed, flags=entry.flags,
                           mutation=entry.mask & mutation, trustee=category))
    return result
```

- [x] 每资源各新backend，由现pin拥有整链；先整体revalidate，逐对象同handle metadata before→raw before→raw after→metadata after，所有metadata须等baseline、raw exact bytes且相等、两次parse都支持；两轮ACE均计总512，超限失败。每个chain节点记录index、root/ancestor/file、真实directory、两个observed_equal=true、parser_result=supported、owner分类、policy_result及有限ACE。不得将owner/raw/SID/路径/metadataID返回；两个资源所有成功观察后总汇必须重算。

```python
def _observe_resource(resource, path, host_sid, budget):
    backend = WindowsStartupPinBackend()
    owner = pin_startup_file(str(path), _backend=backend)
    try:
        owner.revalidate()
        if not 2 <= len(owner._handles) <= 32:
            raise ValueError('chain_budget_exceeded')
        records = []
        for index, (handle, baseline) in enumerate(zip(owner._handles, owner._baseline)):
            before = backend.query(handle)
            raw_before = backend.query_security(handle)
            raw_after = backend.query_security(handle)
            after = backend.query(handle)
            if before != baseline or after != baseline or raw_before != raw_after:
                raise ValueError('chain_observation_drift')
            first = parse_startup_security(raw_before)
            second = parse_startup_security(raw_after)
            budget[0] += len(first.entries) + len(second.entries)
            if budget[0] > 512:
                raise ValueError('ace_budget_exceeded')
            kind = 'root' if index == 0 else ('file' if index == len(owner._handles)-1 else 'ancestor')
            records.append(dict(index=index, kind=kind, directory=baseline.directory,
                metadata_observed_equal=True, descriptor_observed_equal=True,
                parser_result='supported', policy_result=_policy_result(raw_before, host_sid, baseline.directory),
                owner=_owner_category(first.owner_sid, host_sid),
                entries=_entry_records(first.entries, host_sid, baseline.directory)))
        owner.revalidate()
        digest = owner.sha256
        owned = len(owner._handles)
    except BaseException as original:
        owner._close_preserving_exception(original)
        raise
    owner.close()
    if not owner.close_confirmed:
        raise ValueError('chain_cleanup_unconfirmed')
    return dict(resource=resource, role='source', image_sha256=digest, chain=records,
                owned_handles=owned, confirmed_closes=owned, unconfirmed_closes=0)
```

这是完整所有权控制流参考； `_owner_category/_entry_records`由上一类别/位合同实现。正常close必须在主体handler之外，避免已close的返回侧故障重复关闭。预算在open前定位检查，owner取得后节点预算二次核。返回确认数仅表示owner对每个已注册owned handle最终close确认，不宣称任意字节码中断原子性。前后metadata错误结构/false字段不得因自定义相等混入成功：复用owner.revalidate及metadata exact type边界或每次 `_metadata` 校验。

- [x] `probe(source_sha)`平台/参数验证先于任何资源/identity/API；hostcapture一次且cleanup确认，两个资源分别新backend共享全轮ACE预算，记录Python[major,minor]及sys.getwindowsversion()[major,minor,build]整数，固定schema字段。CLI main只有--source-sha；成功在全清理和validate_wire后输出单行JSON，失败固定脱敏错误，不打印str(exception)/cause/输入。内部_observe_resource保持原KI/SE身份及主体异常优先；CLI明确KI转固定错误和130退出、内部SE固定错误和1退出，普通未知Exception固定错误和1退出；不打印traceback泄露安装路径，argparse的用户帮助/正常CLI退出保持。

```python
def probe(source_sha):
    if sys.platform != 'win32' or type(source_sha) is not str or re.fullmatch('[0-9a-f]{40}', source_sha) is None:
        raise ValueError('invalid_probe_input')
    arch, resources = _installed_resources()
    identity = WindowsStartupHostIdentity()
    host_sid = identity.capture()
    if identity.cleanup_unconfirmed:
        raise ValueError('host_cleanup_unconfirmed')
    budget = [0]
    observed = [_observe_resource(name, path, host_sid, budget) for name, path in resources]
    version = sys.getwindowsversion()
    return dict(schema_version=1, scope='installed_source_chain_observation',
        source_sha=source_sha, architecture=arch, python=list(sys.version_info[:2]),
        windows=[version.major, version.minor, version.build], observation_complete=True,
        source_policy_all_passed=all(node['policy_result']=='pass' for item in observed for node in item['chain']),
        protected_observed=False, compatibility_accepted=False, launch_authorized=False, resources=observed)
```

- [x] 实现严格validator完整合同：只exact bytes、1..256KiB、恰一个末尾LF或CRLF，UTF8 strict、object_pairs_hook拒重复成员、精确所有字段集合、类型（bool/int非别名）、有限枚举；按下表逐层核，再将对象canonical separators JSON+同末尾newline与原wire逐字节比较，拒绝额外空白/行/Unicode自由值。schema与source_sha/arch须精确expected，Python仅[3,11]/[3,12]，windows三exact int各0..2**32-1；all_passed由chain重新推导。

| 对象 | 精确字段/约束 |
| --- | --- |
| top | probe上例全部12字段，四false/observation true精确bool，schema_version exact int1 |
| resources | exact list长度2；resource顺序helper/verifier，role精确source，image_sha256小写hex64 |
| resource | resource/role/image_sha256/chain/owned_handles/confirmed_closes/unconfirmed_closes；后3exact int，owned=confirmed=len(chain)，unknown=0 |
| chain | exact list2..32；每节点index exact int顺序0..n-1，kind root/ancestor/file按位置确定，directory精确bool且只有最终file false |
| node | index/kind/directory/metadata_observed_equal/descriptor_observed_equal/parser_result/policy_result/owner/entries；两equal必须exact true；supported/四policy/四owner有限值 |
| entries | exact list，累加数量×2≤512，空列表只接受empty_dacl或owner_untrusted（先判owner）；empty_dacl必须空，mutation_untrusted必须有非可信allow mutation；其它result按owner/entries有限信息与政策顺序重算 |
| ACE | allowed exact bool；flags exact int合法0x1f范围；mutation exact int且只含对应file/dir mutation位；trustee九固定类别，非自由字符串 |

owner/trustee无法还原组或SID；父validator仅证明有限记录内逻辑，不作独立OS权限证明。trusted包括admin/system/host，owner_rights按已核owner映射；creator_owner仍非额外trusted。未知政策异常不能从任意文案映射进有限枚举。validator任何失败固定ValueError不含原wire。

validator完整循环参考（常量字段集合直接取上表，上述表是精确数据定义而非可选字段）：

```python
def validate_wire(wire, source_sha, arch):
    def fail():
        raise ValueError('invalid_installed_chain_receipt')
    def keys(value, expected):
        if type(value) is not dict or set(value) != set(expected.split()):
            fail()
    def number(value, low, high):
        if type(value) is not int or not low <= value <= high:
            fail()
    def literal(value, expected):
        if type(value) is not type(expected) or value != expected:
            fail()
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                fail()
            value[key] = item
        return value
    if type(wire) is not bytes or not 0 < len(wire) <= 256*1024:
        fail()
    ending = b'\r\n' if wire.endswith(b'\r\n') else b'\n'
    if not wire.endswith(ending):
        fail()
    try:
        data = json.loads(wire[:-len(ending)].decode('utf-8', 'strict'), object_pairs_hook=unique)
    except (ValueError, UnicodeError, RecursionError):
        fail()
    keys(data, 'schema_version scope source_sha architecture python windows observation_complete source_policy_all_passed protected_observed compatibility_accepted launch_authorized resources')
    for name, expected in dict(schema_version=1, scope='installed_source_chain_observation',
            source_sha=source_sha, architecture=arch, observation_complete=True,
            protected_observed=False, compatibility_accepted=False, launch_authorized=False).items():
        literal(data[name], expected)
    if type(data['python']) is not list or len(data['python']) != 2:
        fail()
    number(data['python'][0], 3, 3)
    number(data['python'][1], 11, 12)
    if type(data['windows']) is not list or len(data['windows']) != 3:
        fail()
    for value in data['windows']:
        number(value, 0, 2**32-1)
    resources = data['resources']
    if type(resources) is not list or len(resources) != 2:
        fail()
    ace_total = 0
    all_passed = True
    for resource, name in zip(resources, ('helper', 'verifier')):
        keys(resource, 'resource role image_sha256 chain owned_handles confirmed_closes unconfirmed_closes')
        literal(resource['resource'], name)
        literal(resource['role'], 'source')
        digest = resource['image_sha256']
        if type(digest) is not str or re.fullmatch('[0-9a-f]{64}', digest) is None:
            fail()
        chain = resource['chain']
        if type(chain) is not list or not 2 <= len(chain) <= 32:
            fail()
        for field in ('owned_handles', 'confirmed_closes'):
            number(resource[field], len(chain), len(chain))
        number(resource['unconfirmed_closes'], 0, 0)
        for index, node in enumerate(chain):
            keys(node, 'index kind directory metadata_observed_equal descriptor_observed_equal parser_result policy_result owner entries')
            number(node['index'], index, index)
            directory = index != len(chain)-1
            kind = 'root' if index == 0 else ('ancestor' if directory else 'file')
            for field, expected in dict(kind=kind, directory=directory,
                    metadata_observed_equal=True, descriptor_observed_equal=True,
                    parser_result='supported').items():
                literal(node[field], expected)
            if type(node['owner']) is not str or node['owner'] not in ('admin', 'system', 'host', 'other'):
                fail()
            entries = node['entries']
            if type(entries) is not list:
                fail()
            ace_total += len(entries)*2
            if ace_total > 512:
                fail()
            bad_mutation = False
            mask = _MUTATION_ACCESS_MASK | (_DELETE_CHILD if directory else 0)
            for entry in entries:
                keys(entry, 'allowed flags mutation trustee')
                if type(entry['allowed']) is not bool:
                    fail()
                number(entry['flags'], 0, 0x1f)
                number(entry['mutation'], 0, mask)
                if entry['mutation'] & ~mask:
                    fail()
                if (type(entry['trustee']) is not str or entry['trustee'] not in
                        ('admin', 'system', 'host', 'everyone', 'authenticated_users',
                         'builtin_users', 'creator_owner', 'owner_rights', 'other')):
                    fail()
                if (entry['allowed'] and entry['mutation'] and entry['trustee'] not in
                        ('admin', 'system', 'host', 'owner_rights')):
                    bad_mutation = True
            expected_policy = ('owner_untrusted' if node['owner']=='other' else
                               'empty_dacl' if not entries else
                               'mutation_untrusted' if bad_mutation else 'pass')
            literal(node['policy_result'], expected_policy)
            all_passed = all_passed and expected_policy == 'pass'
    literal(data['source_policy_all_passed'], all_passed)
    canonical = json.dumps(data, separators=(',', ':')).encode('ascii') + ending
    if canonical != wire:
        fail()
    return data
```

validator的expected source_sha/arch自身也须先核hex40/x64或arm64精确类型，不能让None/bool作为预期字面值混入；测试覆盖。所有有限字符串和数字都核后才canonical encode；任何普通错误必须固定错误边界，不漏wire。JSON非标准NaN/Infinity虽会加载，但有限结构的exact类型/枚举/数值边界一律拒绝。

```python
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-sha', required=True)
    args = parser.parse_args(argv)
    try:
        receipt = probe(args.source_sha)
        wire = json.dumps(receipt, separators=(',', ':')).encode('ascii') + b'\n'
        validate_wire(wire, args.source_sha, receipt['architecture'])
    except KeyboardInterrupt:
        print('windows_installed_chain_observation_failed', file=sys.stderr)
        return 130
    except (SystemExit, Exception):
        print('windows_installed_chain_observation_failed', file=sys.stderr)
        return 1
    print(wire[:-1].decode('ascii'))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
```

main的所有普通序列化/验证故障都固定错误；最终stdout写出失败不可能伪造完整成功回执，parentraw监督继续阻断。args正常help/语法错误在主体handler之外沿argparse既有约定，不把用户帮助退出码改成观察错误。

- [x] 便携TDD完整矩阵及边界：每位置query/parser/policy未知失败、metadata/SD漂移、身份拒绝0open、第二资源故障第一已清理、close失败/主体KI与SE+复合close（原identity/no重试）、hostile异常/私有值与cause不泄露；正常policy拒绝继续所有节点和第二资源。链32/33、两轮ACE512/514、输出limit/limit+1，UTF8/重复/类型别名/extra/missing/index/kind/role/aggregate欺骗与参数失配均断言失败。独立backend也用真实退休规则数值回收fixture验证，不靠call次数自报。
- [x] newtests 20轮0skip/F/E，关联旧pure/reader/pin/identity/transport全跑；compileall -j1、两文件diff/selfSPEC后selfQUALITY，报告RED/GREEN真实结果、类方法数与冻结摘要。不提交、不碰Task2文件或产品源。

## Task 2：安装CI raw监督与便携必需选择

### Task1 实际冻结验收（2026-10-11）

Task1 两个新文件已实现并冻结；本节记录软件证据，不授安装原生、兼容或启动信用。writer 的真实 assertion RED→GREEN 分别为接口1、定位/策略4、观察8、probe/wire/CLI11、未知返回策略1，均0 ERROR；早期接口占位和测试语法 ERROR不计产品RED，后续16方法仅为矩阵扩展。以上原始履历来自writer记录，独立审查未重演历史RED。

root全文回读两个新文件及调用链，实际新suite41 PASS/0skip，20轮820 PASS；旧关联加新模块217 run=207 PASS/10 Windows平台skip/0失败，安装旧调用链相关74 PASS。两文件compileall-j1、diff检查通过。独立SPEC之后不同QUALITY均C0/I0/M0，各实跑217关联和820轮次；SPEC另验复合query/close错误身份保留，QUALITY另验720份回执、5760节点的策略重算矩阵。这些是便携观察/运输fixture，不是Windows实机证据。

冻结摘要：script `19a9c21e204d04675e3d2c46f410afc0d4836add11843d387cf960cc3a6a2b21`；test `cccf69f62c6d42ffd806d599dac10b0951217cc359dc1d1693462fdb13c4e720`。合法wire精确预算边界通过缩小同一 `_WIRE_LIMIT` 验证；生产256KiB和+1畸形回执均拒绝，不虚构合法256KiB正控。Task2仅四既有文件单写者接线，Task1继续冻结；全片审查、完整preflight和新SHA安装四格仍待。

阶段结束只读研究实际12:56–12:57 UTC复核同固定Codex/SRT及Apache2，无HEAD/二十名单刷新或复制代码、新依赖/权限。root另核[Python3.12官方-I](https://docs.python.org/3.12/using/cmdline.html#cmdoption-I)和[GetSecurityInfo](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-getsecurityinfo)：采纳同HANDLE/独立backend/raw有限监督；暂缓guard写对象、protected/UAC；不适配warn-and-continue或修改host ACL过门。`-I`仅导入路径隔离，不是OS沙箱，也不禁用正常site；venv解释器、site初始化与CI probe属于测试TCB。两次SD相等仅为观察一致，不是ACL冻结；先行path provenance不认证后来held bytes。收益限于避免对象错配/输出泄漏，成本是预算、故障负控与真实安装四格，不改变完整窗口或R2/R3验收。

**Dependencies:** Task 1（新script/test冻结并由root回读）
**Parallelizable:** No（单写者、计数接线依赖真实loader）

- [x] 先新增真实安装模拟负控与严格选择断言RED，再改四既有功能文件。runwheel新内部 `_observe_installed_chain(python, source_sha, arch, *, cwd, env)` 仅执行固定script；复用raw监督256KiB/30s、stdout严格bytes/stderr空、code exactint0、tuple exacttype/长度3。import新script validator在host侧验证后打印有限ASCII JSON，阶段标签必须observation_complete且compatibility_accepted=false，不说政策通过。捕获失败固定RuntimeError fromNone，超时/捕获未确认继续阻断。

```python
def _observe_installed_chain(python, source_sha, arch, *, cwd, env):
    from scripts.probe_windows_installed_chain import validate_wire
    result = _run_unittest_with_bounded_output(
        [str(python), '-I', '-B', '-X', 'utf8',
         str(_REPOSITORY / 'scripts/probe_windows_installed_chain.py'), '--source-sha', source_sha],
        workspace=cwd, timeout=30, output_limit_bytes=256*1024, environment=env)
    if (type(result) is not tuple or len(result)!=3 or type(result[0]) is not int
            or result[0]!=0 or type(result[1]) is not bytes or type(result[2]) is not bytes or result[2]):
        raise RuntimeError('installed chain observation failed')
    receipt = validate_wire(result[1], source_sha, arch)
    print(json.dumps(receipt, separators=(',', ':')))
    print('installed-chain observation_complete=true compatibility_accepted=false launch_authorized=false')
```

hook位置：proof+verifier模式direct-volume既有调用之后、bootstrap metadata及末尾rename负控之前：`_observe_installed_chain(python, env['GITHUB_SHA'], arch, cwd=root, env=clean_env)`。不得改_run宽松解码/全旧行为；raw函数本来单独固定bootstrap query，原mock须按argv分派新probe，不能把新probe误当--verifier-binding-json。

- [x] 完整读原TestWindowsBootstrapBinding.test_signed_install_order_and_failure_gates_preserve_no_go_proof_only，保留全部旧模式并新增chain_failure；valid新probe有完整有限正控fixture，先行gh/binding/Go/directvolume失败及unsigned/proof_only模式不能进入probe；新probe失败不导出wheel、不运行后续metadata/rename。便携validator按明确schema构造synthetic receipt，不称原生证明。
- [x] scripts/run_workspace_ci的DEFAULT新增新便携module一次、required prefix加入新module，pairedCI更新实际loader唯一数和class/count，不改optional/native旧含义；method/class+module fixture/nestedsubTest skip各真实RED→GREEN。不要凭估计填新总数，取Task1真实loader，nt旧176/posix166 baseline保持。
- [x] 编译-j1、关联新模块/bootstrapbinding/directvolume/原pinCI/runworkspace/workflow合同，全部便携20轮0skip/F/E，自SPEC→QUALITY，冻结四文件并报告；不自行提交，不改新script/test。

## Task 3：全片验收与新SHA安装四格

### Task2 实际候选冻结（2026-10-11）

四既有功能文件已接线并冻结，Task1两文件摘要未变。writer实际安装/选择/skip负控166次assertion failure、入口4次assertion failure，均0 ERROR，再最小接线GREEN；此历史RED来源于writer记录。writer自SPEC后自QUALITY均C0/I0/M0，119关联0skip/F/E、20轮218/轮共4360 PASS；扩大295关联=285 PASS/10正常Windows平台skip，额外bootstrap/packaged_skill32 PASS。

root独立回读四文件全部diff及前后安装/metadata/rename/export调用链，实际295关联结果同上；实核posix207、nt217均唯一、新module和DEFAULT恰一次、guard11，另20轮4360 PASS/0skip/F/E。六文件compileall-j1、diff通过；普通监督/validation失败固定错误fromNone，父侧仅输出验证过的有限回执。全片独立SPEC→不同QUALITY及完整preflight仍待，不能把候选冻结当发布或Windows原生信用。

Task2摘要：runwheel `32548a99501908cc874e86798de0e28f8b806b1d70a6782f2d67d22772c9312e`；bootstrap test `4c8b8b35d95d8aedf5e9cb87ea0f7e55ad2811b539d2a200272a025dd9361bda`；workspace selector `44268d966aa9b294007bed86b0c4fd863bd89487c7f44dda7410df10866890f1`；paired guard `45c564d4d17890f7640927282b45544d9493a2d568bd31d66c9676e952a2e174`。产品windows_startup_*、ABI、policy、workflow权限及固定子模块不改。

### 全片独立双审（2026-10-11）

六功能摘要冻结后，全片独立SPEC→不同QUALITY均C0/I0/M0；两者各完整回读六文件/设计/计划及实际依赖，各119 PASS、295=285 PASS/10平台skip、20轮4360 PASS/0skip/F/E、实际loader207/217 unique及guard11。SPEC额外复合query/close保持原异常身份/全链一次逆序清理。QUALITY扩大关联362=352 PASS/10同平台skip，另用真实POSIX有界子进程向父validator交合法/政策拒绝回执、非法UTF8、stderr、额外私有输出及超时，均符合合同；真实产生256KiB+1输出触发limit错误并转固定RuntimeError fromNone，未打印私有值，初次超长argv仅OSError不冒充输出超限。全部仅便携/本机监督证据，不授Windows原生。root另实跑bootstrap/packaged_skill32 PASS。新完整preflight session71764已启动，尚未据运行中状态授通过；四Windows安装格仍待新SHA。

**Dependencies:** Task 1, Task 2
**Parallelizable:** No（完整候选冻结）

完整preflight session71764已结束exit0：密钥、固定子模块、全仓unittest三道均通过。完整测试成功正文由既有preflight捕获，不臆造本机全量方法数；295关联/4360轮次和32额外套件为root另跑的实际可见计数。上节“尚在运行/未授通过”保留启动窗口，以本条刷新为准。文档与站点最终两轮、exact staging及main推送另验；新Windows安装四格未跑，不授R2/R3总门。

软件已实际发布main `37f100a0566e9225630e409b8077a1c06789b649`：10确切文件1479+/19-，commit/push成功、ls-remote同SHA、发布后工作区干净。最后四文档两轮0疑似、site两轮通过（9外链未fetch）、额外密钥扫描、cached diff与六冻结摘要均通过；源码产品策略/固定子模块/workflow权限不改。root七维自检仅授本片便携软件，原生安装另验。新[CI38142958343](https://github.com/ayukyo/icode/actions/runs/38142958343)、[provenance38142958337](https://github.com/ayukyo/icode/actions/runs/38142958337)、[Pages38142958335](https://github.com/ayukyo/icode/actions/runs/38142958335)已启动，以新SHA逐格日志为准；root仅词法重建候选Windows清单860唯一，不是实机执行。新41方法位置604–644、parent raw4为280–283、身份native653/654、校验fixture697/715供原生日志核对，不借旧815通过信用。

- [x] root全文回读六文件及关联调用链，确认产品源/子模块/workflow权限不变，精确loader/真实负控、关联/20轮/compileall-j1/diff；阶段结束只读研究刷新固定取舍，不代native。
- [x] 全片独立SPEC后不同QUALITY解决所有C/I/M；若修源测试须重新冻结、审查与必要全验，不能拿旧候选通过信用。
- [x] `CMAKE_BUILD_PARALLEL_LEVEL=1 MAKEFLAGS=-j1 .venv/bin/python -u scripts/preflight.py`新完整三道exit0，site/doc两轮及七维真实报告；root exact add（ignored docs add-f）、commit/push main和lsremote确认，不上传KEY、不改无关用户文件。
- [x] 新SHA provenance installed x64/ARM64×3.11/3.12逐格实际有限JSON：resource/helper/verifier、chain全祖先、policy拒绝、budget与close全部确认；严格区分“观察完整”和“策略通过”。若query/parser/native失败查根因，不加skip或宽松readraw。workspace方法/fixture/subTest必需0skip也另验。Win10/普通host/protected/full窗口/生产consumer/UAC/模型90%及R2/R3仍未授信用；下一片以实际数据选择最小契约。

### 新 SHA 原生窗口（2026-10-11 13:35 UTC）

root 已独立取得四份完整 workspace 日志：x64/3.11 `114480393166`、x64/3.12 `114480393317`、ARM64/3.11 `114480393318`、ARM64/3.12 `114480393395`。每格实际860 run/20既定可选skip；新41方法、parent raw4、身份native2及两个必需fixture位置均为通过，无必需skip或reader异常；后续junction3、leased75亦通过。这关闭本片 workspace 接线门，不是安装链权限或启动证明。

新 provenance validate `114480392559` 实际 success，四 installed 作业已开始：ARM64/3.11 `114483000698`、x64/3.12 `114483000706`、x64/3.11 `114483000723`、ARM64/3.12 `114483000727`，有限JSON与清理结果仍待。Pages validate/deploy `114480392568`/`114480415098`均实际success。主CI两格Reviewer网络门继续失败关闭；root核x64完整日志仍为10035、wait_expired、connect_denied=false，不授网络DENY。不得用其它作业成功抹去R2/R3缺口。

### 本片最终原生结果（2026-10-11）

四 installed 作业全部 success，root 已独立取得四份完整日志、各唯一有限JSON并以冻结 `validate_wire` 严格验证原wire、对应SHA与架构：x64/3.11 `114483000723`、x64/3.12 `114483000706`、ARM64/3.11 `114483000698`、ARM64/3.12 `114483000727`。两x64 Windows版本10.0.26100，两ARM版本10.0.26200；版本major=10不意味着Windows10，实际runner仍分别Server2025/Windows11，不授Win10格。

每格 helper/verifier各13节点，各13 confirmed closes、0 unconfirmed，两轮ACE合计188≤512。各资源仅卷根 owner=other/policy=owner_untrusted，其余12节点pass；四格合计104节点、96pass/8拒绝、104确认关闭。四格 observation_complete=true，source_policy_all_passed=false；protected_observed/compatibility_accepted/launch_authorized均false，固定parent stage正确，既有19安装阶段保持。完整观察与安全回收门关闭；来源政策、默认安装兼容和启动门明确没有通过。

主CI终态46 jobs=41success/2旧Reviewer failure/3既定skip；全量Python3.11/3.12各实际2813run/81skip，耗时555.080s/490.754s。provenance5/5、Pages2/2实际success。两Reviewer继续10035/wait_expired/connect_denied=false、positive-control91，不授网络DENY，R2/R3未完成。root七维软件报告与本片原生观察成立，但不能写整平台可运行性100%。

下一片[内部来源owner设计](../specs/2026-10-11-windows-source-owner-design.md)只将原政策绑定live对象，仍拒绝不合格卷根；卷根owner先失败掩盖后续mutation拒绝，不能猜TrustedInstaller或直接跳过根。13:32–13:41 UTC只读研究详见新设计，未改部署/许可/权限，未执行UAC。

计划自审：每项设计有Task1/2/3对应，定位、角色、三policy拒绝/reader失败、所有权、两轮预算和有限schema一致；无额外许可/依赖/权限。Task1较完整但只有两个新文件/一个职责，Task2依赖其冻结类与实际字段，Task3依赖全片；不能并行写。用户main/推荐自主要求覆盖默认worktree与逐步人工批准，其余TDD/审查/验收门保留。

**Execution Mode:** serial
