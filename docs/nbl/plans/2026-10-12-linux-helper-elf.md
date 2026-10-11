# LA-2b1 Linux 助手有限 ELF 核验实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development，逐task fresh writer、单一源码writer，先实际RED→GREEN后独立SPEC→不同QUALITY。用户明确main-only覆盖技能worktree/分支默认；不新建分支。

**Goal:** 包内Linux resolver拒绝非ELF或错机器助手，不修改generic脚本兼容，不增加执行授权。

**Architecture:** native_helper复用generic形态/摘要门，新增64字节有限头与真实宿主映射；resolver仍固定包路径，只返回候选Path。静态检查不是同FD执行或publisher认证。

**Tech Stack:** Python3.11/3.12，stdlib struct/platform/hashlib/unittest；无新增依赖、权限或安装步骤。

**Dependencies:** [冻结设计](../specs/2026-10-12-linux-helper-elf-design.md)实际设计SPEC→不同QUALITY零遗留；前片main c153154。设计审查候选a7dbaa5摘要见设计头部，状态变更不修改合同。本计划已经root self-review及fresh PLAN SPEC→不同QUALITY各C0/I0/M0，冻结合同后进入Task1。

只写`src/icode/native_helper.py`及新`tests/test_linux_helper_elf.py`；阶段发布文档限本文、冻结设计、持续对照。不改setup、wheelchecker、isolation、selector、LA1 schema、Windows、vendor、model或CI权限。下面测试替身只替宿主/包位置或精确读取故障，实际调用本仓函数；不执行任何helper。

## Task 1：完整测试文件与旧resolver有效RED

**Dependencies:** 冻结设计/计划。**Parallelizable:** No，唯一测试writer；源码仍旧实现。

状态：已完成RED目标；实际唯一测试writer新增293行/12方法后停止，root全文回读并独立selected1方法/1 assertion FAIL/0ERROR，真实旧resolver返回包内非ELF Path。root及writer原helper7项均通过；fresh实际CODE SPEC后不同QUALITY各零遗留。测试SHA256`0ecaedb65cf875faa575847f03278f7912d946423a2d7810c21bf17fd4bc335d`，旧源码`fb1452a794c8c17b49c282e8484d536ea7662a83c957fa07c0400fd5dfe61c0e`。实际文件按项目中文说明/类型注解/subTest等价实现冻结12方法case合同；不要求与示例逐byte相等，不减少覆盖。其它新函数测试在旧源码阶段未运行，不授新12项GREEN信用。

- [x] 完整读设计与实际native_helper、原helper测试和明确脚本兼容回归，三问与owner边界核对。
- [x] 新增以下完整测试文件；不得新增源码stub以制造导入失败。新函数测试在实现前未运行，不把missing attribute当有效RED。

```python
"""Finite Linux ELF checks; no helper is executed."""
from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
import struct
import unittest
from unittest.mock import Mock, patch

from tests._support import temp_workspace
import icode.native_helper as h


def image(machine=62, kind=2):
    value = bytearray(64)
    value[:7] = b'\x7fELF\x02\x01\x01'
    struct.pack_into('<HHI', value, 16, kind, machine, 1)
    struct.pack_into('<H', value, 52, 64)
    return bytes(value)


def write_helper(root, content):
    native = root / 'native'
    native.mkdir(exist_ok=True)
    binary = native / 'icode-landlock'
    manifest = native / 'icode-landlock.sha256'
    binary.write_bytes(content)
    binary.chmod(0o755)
    manifest.write_text(hashlib.sha256(content).hexdigest() + '\n', encoding='ascii')
    return binary, manifest


class FaultStream:
    def __init__(self, content, failure=None, phase='header'):
        self.inner = io.BytesIO(content)
        self.failure, self.phase = failure, phase
        self.requests = []
    @property
    def closed(self):
        return self.inner.closed
    def readable(self):
        return True
    def readinto(self, buffer):
        if self.failure is not None and self.phase == 'digest':
            raise self.failure
        return self.inner.readinto(buffer)
    def read(self, size=-1):
        self.requests.append(size)
        if self.failure is not None and self.phase == 'header':
            raise self.failure
        return self.inner.read(size)
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.inner.close()


class LinuxHelperElfTests(unittest.TestCase):
    def test_bundle_rejects_digest_matching_non_elf(self):
        with temp_workspace() as root:
            binary, _ = write_helper(root, b'not-an-ELF-helper')
            with (patch.object(h, '__file__', str(root / 'native_helper.py')),
                  patch.object(h.sys, 'platform', 'linux'),
                  patch('platform.machine', return_value='x86_64')):
                self.assertIsNone(h.bundled_linux_helper())
            self.assertTrue(binary.is_file())

    def test_parser_supported_machines_and_object_types(self):
        for machine, expected in ((62, 'x86_64'), (183, 'arm64')):
            for kind in (2, 3):
                with self.subTest(machine=machine, kind=kind):
                    self.assertEqual(h.linux_elf_architecture(image(machine, kind)), expected)
                    # Unused fields and trailing bytes are not full loader proof.
                    value = bytearray(image(machine, kind))
                    value[7:16] = b'\xff' * 9
                    value[24:52] = b'\xff' * 28
                    value[54:64] = b'\xff' * 10
                    self.assertEqual(h.linux_elf_architecture(bytes(value) + b'tail'), expected)

    def test_parser_rejects_types_lengths_and_bad_fields(self):
        class BytesSubclass(bytes):
            pass
        for value in (None, False, 'ELF', bytearray(image()), memoryview(image()),
                      BytesSubclass(image()), *(image()[:n] for n in range(64))):
            self.assertIsNone(h.linux_elf_architecture(value))
        for offset, payload in ((0, b'bad!'), (4, b'\x01'), (5, b'\x02'),
                                (6, b'\x00'), (16, b'\x01\0'), (16, b'\x04\0'),
                                (18, b'\x03\0'), (20, b'\0\0\0\0'),
                                (52, b'\x3f\0'), (52, b'\x41\0')):
            value = bytearray(image())
            value[offset:offset + len(payload)] = payload
            self.assertIsNone(h.linux_elf_architecture(bytes(value)))

    def test_machine_mapping_is_finite_and_exact(self):
        for raw, expected in (('x86_64', 'x86_64'), ('X86_64', 'x86_64'),
                              ('aarch64', 'arm64'), ('ARM64', 'arm64')):
            self.assertEqual(h.linux_arch_from_machine(raw), expected)
        class StrSubclass(str):
            pass
        for value in (None, True, [], '', 'amd64', 'x86', 'x86_64-extra',
                      ' arm64', StrSubclass('arm64')):
            with self.assertRaisesRegex(ValueError, '^unsupported Linux architecture$'):
                h.linux_arch_from_machine(value)

    def test_real_file_digest_and_architecture(self):
        for machine, arch in ((62, 'x86_64'), (183, 'arm64')):
            for kind in (2, 3):
                with temp_workspace() as root:
                    binary, manifest = write_helper(root, image(machine, kind))
                    self.assertTrue(h.verify_linux_helper(binary, manifest, expected_arch=arch))
                    wrong = 'arm64' if arch == 'x86_64' else 'x86_64'
                    self.assertFalse(h.verify_linux_helper(binary, manifest, expected_arch=wrong))
                    binary.write_bytes(image(machine, kind) + b'changed')
                    self.assertFalse(h.verify_linux_helper(binary, manifest, expected_arch=arch))

    def test_manifest_shapes_and_execute_permission(self):
        for content in ('0' * 64 + '\n', 'invalid', '\u00e9', ''):
            with temp_workspace() as root:
                binary, manifest = write_helper(root, image())
                manifest.write_text(content, encoding='utf-8')
                self.assertFalse(h.verify_linux_helper(binary, manifest, expected_arch='x86_64'))
        with temp_workspace() as root:
            binary, manifest = write_helper(root, image())
            with patch.object(h.os, 'access', return_value=False):
                self.assertFalse(h.verify_linux_helper(binary, manifest, expected_arch='x86_64'))
            manifest.unlink()
            self.assertFalse(h.verify_linux_helper(binary, manifest, expected_arch='x86_64'))
            manifest.write_text(hashlib.sha256(image()).hexdigest() + '\n', encoding='ascii')
            binary.unlink()
            self.assertFalse(h.verify_linux_helper(binary, manifest, expected_arch='x86_64'))
            binary.mkdir()
            self.assertFalse(h.verify_linux_helper(binary, manifest, expected_arch='x86_64'))

    @unittest.skipUnless(os.name == 'posix', 'POSIX link creation; no Windows credit')
    def test_real_links_are_rejected(self):
        for target in ('binary', 'manifest'):
            for kind in ('hard', 'symbolic'):
                with temp_workspace() as root:
                    binary, manifest = write_helper(root, image())
                    path = binary if target == 'binary' else manifest
                    extra = path.parent / 'other'
                    if kind == 'hard':
                        os.link(path, extra)
                    else:
                        path.rename(extra)
                        path.symlink_to(extra)
                    self.assertFalse(h.verify_linux_helper(binary, manifest, expected_arch='x86_64'))

    def test_invalid_expected_arch_refuses_before_open(self):
        class StrSubclass(str):
            pass
        for arch in (None, True, [], 'x64', StrSubclass('x86_64')):
            with (patch.object(h, 'verify_native_helper') as generic,
                  patch.object(Path, 'open') as opened):
                self.assertFalse(h.verify_linux_helper(Path('unused'), Path('unused'), expected_arch=arch))
                generic.assert_not_called()
                opened.assert_not_called()

    def test_bundle_matches_actual_host_without_path_fallback(self):
        for machine, arch in (('x86_64', 62), ('aarch64', 183), ('arm64', 183)):
            with temp_workspace() as root:
                binary, manifest = write_helper(root, image(arch))
                outsider = root / 'outsider'
                outsider.mkdir()
                (outsider / binary.name).write_bytes(image(arch))
                (outsider / binary.name).chmod(0o755)
                (outsider / manifest.name).write_text(hashlib.sha256(image(arch)).hexdigest() + '\n', encoding='ascii')
                with (patch.object(h, '__file__', str(root / 'native_helper.py')),
                      patch.object(h.sys, 'platform', 'linux'),
                      patch('platform.machine', return_value=machine),
                      patch.dict(os.environ, {'PATH': str(outsider)})):
                    self.assertEqual(h.bundled_linux_helper(), binary)
                    wrong = 183 if arch == 62 else 62
                    write_helper(root, image(wrong))
                    self.assertIsNone(h.bundled_linux_helper())
                    binary.unlink()
                    manifest.unlink()
                    self.assertIsNone(h.bundled_linux_helper())

    def test_host_failure_and_non_linux_refuse_before_file_checks(self):
        for value in ('unknown', None, [], True):
            with (patch.object(h.sys, 'platform', 'linux'),
                  patch('platform.machine', return_value=value),
                  patch.object(h, 'verify_linux_helper') as verify):
                self.assertIsNone(h.bundled_linux_helper())
                verify.assert_not_called()
        for failure in (OSError('private'), RuntimeError('private'), ValueError('private')):
            with (patch.object(h.sys, 'platform', 'linux'),
                  patch('platform.machine', side_effect=failure),
                  patch.object(h, 'verify_linux_helper') as verify):
                self.assertIsNone(h.bundled_linux_helper())
                verify.assert_not_called()
        with (patch.object(h.sys, 'platform', 'win32'),
              patch('platform.machine') as machine, patch.object(h, 'verify_linux_helper') as verify):
            self.assertIsNone(h.bundled_linux_helper())
            machine.assert_not_called()
            verify.assert_not_called()

    def test_digest_and_header_streams_close_on_faults(self):
        original_open = Path.open
        for phase in ('digest', 'header'):
            for failure in (None, OSError('private'), ValueError('private'),
                            KeyboardInterrupt('private'), SystemExit('private')):
                with temp_workspace() as root:
                    content = image()
                    binary, manifest = write_helper(root, content)
                    streams = []
                    def opened(path, mode='r', *args, **kwargs):
                        if path == binary and mode == 'rb':
                            ordinal = len(streams)
                            selected = ordinal == (0 if phase == 'digest' else 1)
                            stream = FaultStream(content, failure if selected else None, phase)
                            streams.append(stream)
                            return stream
                        return original_open(path, mode, *args, **kwargs)
                    with patch.object(Path, 'open', new=opened):
                        if isinstance(failure, (KeyboardInterrupt, SystemExit)):
                            with self.assertRaises(type(failure)) as caught:
                                h.verify_linux_helper(binary, manifest, expected_arch='x86_64')
                            self.assertIs(caught.exception, failure)
                        else:
                            self.assertIs(h.verify_linux_helper(binary, manifest, expected_arch='x86_64'),
                                          failure is None)
                    self.assertTrue(streams)
                    expected_count = 1 if phase == 'digest' and failure is not None else 2
                    self.assertEqual(len(streams), expected_count)
                    self.assertTrue(all(stream.closed for stream in streams))
                    if len(streams) == 2:
                        self.assertEqual(streams[1].requests, [64])

    def test_host_interrupts_preserve_original_object(self):
        for failure in (KeyboardInterrupt('private'), SystemExit('private')):
            with (patch.object(h.sys, 'platform', 'linux'),
                  patch('platform.machine', side_effect=failure)):
                with self.assertRaises(type(failure)) as caught:
                    h.bundled_linux_helper()
                self.assertIs(caught.exception, failure)
```

- [x] 执行有效RED：`.venv/bin/python -m unittest tests.test_linux_helper_elf.LinuxHelperElfTests.test_bundle_rejects_digest_matching_non_elf -v`。预期1方法/1 assertion FAIL/0ERROR，旧resolver实际返回临时binary Path而非None。不执行新函数缺失的其它测试，不授ImportError/AttributeError信用。
- [x] 原baseline：`.venv/bin/python -m unittest tests.test_native_helper -q`应7方法通过；只新增测试后writer停止、记录SHA和完整selected RED。测试总12方法，POSIX本机无平台skip。

## Task 2：专用核验与resolver最小补丁

**Dependencies:** Task1有效磁盘RED和原baseline。**Parallelizable:** No，fresh源码writer，测试候选不变。

- [x] fresh writer复现同selected RED，不回退root源码；只修改native_helper.py，import区追加`import platform`，在generic结束与bundled_linux_helper之间加入完整代码：

```python
_LINUX_ELF_HEADER_SIZE = 64
_LINUX_ELF_MACHINE_ARCH = {62: 'x86_64', 183: 'arm64'}


def linux_elf_architecture(image: bytes) -> str | None:
    """Inspect a finite ELF64LE header, not loadability or launch identity."""
    if type(image) is not bytes or len(image) < _LINUX_ELF_HEADER_SIZE:
        return None
    if image[:7] != b'\x7fELF\x02\x01\x01':
        return None
    object_type, machine, version = struct.unpack_from('<HHI', image, 16)
    header_size = struct.unpack_from('<H', image, 52)[0]
    if object_type not in (2, 3) or version != 1 or header_size != _LINUX_ELF_HEADER_SIZE:
        return None
    return _LINUX_ELF_MACHINE_ARCH.get(machine)


def linux_arch_from_machine(machine: str) -> str:
    """Map only the supported Linux host machine spellings."""
    if type(machine) is not str:
        raise ValueError('unsupported Linux architecture')
    architecture = {'x86_64': 'x86_64', 'aarch64': 'arm64', 'arm64': 'arm64'}.get(machine.lower())
    if architecture is None:
        raise ValueError('unsupported Linux architecture')
    return architecture


def verify_linux_helper(binary: Path, manifest: Path, *, expected_arch: str) -> bool:
    """Check package shape, digest and a finite matching ELF header.

    This path-based check is not publisher authentication, complete ELF
    validation, immutable content, or a race-free launch grant.
    """
    if type(expected_arch) is not str or expected_arch not in ('x86_64', 'arm64'):
        return False
    try:
        if not verify_native_helper(binary, manifest):
            return False
        with binary.open('rb') as stream:
            header = stream.read(_LINUX_ELF_HEADER_SIZE)
        return linux_elf_architecture(header) == expected_arch
    except (OSError, ValueError):
        return False
```

- [x] 仅替换原Linux包内resolver为下列完整函数，generic与所有Windows函数逐byte保持原状（import/插入位置除外）：

```python
def bundled_linux_helper() -> Path | None:
    """Return a matching package candidate, never an execution grant."""
    if not sys.platform.startswith('linux'):
        return None
    try:
        architecture = linux_arch_from_machine(platform.machine())
    except Exception:  # Host detection has no effects; signals still propagate.
        return None
    directory = Path(__file__).resolve().parent / 'native'
    binary = directory / 'icode-landlock'
    manifest = directory / 'icode-landlock.sha256'
    return binary if verify_linux_helper(binary, manifest, expected_arch=architecture) else None
```

- [x] 同selected RED命令应1GREEN；完整`.venv/bin/python -m unittest tests.test_linux_helper_elf tests.test_native_helper tests.test_linux_admission_diagnostic -q`应42方法通过（12+7+23，本机POSIX）。检查原generic和Windows函数未扩散，源码writer内置SPEC→QUALITY零遗留后停止；不运行full/native/Git或改文档。

## Task 3：独立实现复审与root交付

**Dependencies:** Task2同候选GREEN。**Parallelizable:** No，SPEC后不同QUALITY；只读研究可独立。

Task2实际完成：唯一源码writer仅改native_helper，旧resolver selected1断言RED/0ERROR→同测试GREEN；42关联及1显式脚本兼容通过。source SHA256 `c5c5d88b8d3fb7c56cd0e574358bc125f3788cac0d0607c7c415ccefd336008c`，测试SHA256保持`0ecaedb65cf875faa575847f03278f7912d946423a2d7810c21bf17fd4bc335d`。原generic与全部Windows函数字节未变，writer已停止。root全文回读并独立43通过/零跳过，fresh CODE SPEC后不同QUALITY各零遗留且各实际43通过；compileall-j1、site和20项对照排期检查通过。完整preflight三道已启动，结果待实际返回，不用focused代替。

- [x] fresh SPEC核设计全部有限字段、expected架构前拒、读取64、KI/SE两stream、包固定位置、legacy兼容；不同QUALITY核同候选资源/无授权扩大。两者C0/I0/M0，source改变须重新门。
- [x] root回读两个完整文件；独立42软件回归及真实显式脚本兼容测试：`.venv/bin/python -m unittest tests.test_isolation.TestSandboxWrapping.test_landlock_策略路径逐次校验助手摘要 -q`，本机Linux应1通过，未运行helper payload，不授原生。
- [ ] root完整`.venv/bin/python scripts/preflight.py`三道、`.venv/bin/python -m compileall -q -j1 src scripts tests`、`.venv/bin/python scripts/check_site.py`、landscape排期及doc-consistency检查；实际平台skip与软件分账。原模型凭据未变不重复401；不读取正文。
- [x] 阶段研究记录刷新引用冻结设计与固定Codex/OpenHands机制，采纳静态架构，暂缓sameFDexec，不适配可选摘要/路径fallback；记录观察日期、固定源码及许可，不抄实现。
- [ ] 完整通过后root fresh `.venv/bin/python scripts/preflight.py --only secrets`及`--only submodule`；只`git add -f -- src/icode/native_helper.py tests/test_linux_helper_elf.py docs/nbl/plans/2026-10-12-linux-helper-elf.md docs/nbl/specs/2026-10-12-linux-helper-elf-design.md docs/agent-landscape-live.md`。确认main、cached名单恰五路径且每个索引字节匹配已审磁盘，`git diff --cached --check`0，再分别`git commit -m 'fix(linux): validate bundled helper ELF architecture'`、`git push origin main`。add/commit/push逐条exit0才继续，任何失败不跳门；未发布的其它草稿不混提交。
- [ ] 记录实际完整守护时间、hash、focused计数与main SHA；下一片才设计sameFD执行所有权，不授安装包x64/ARM64、静态链接/完整loader、准备执行对象一致或R2/R3信用。

【架构级自检报告】（计划候选）

- 语法/文档：root与两审查者各独立三Python块AST通过；计划审查候选SHA256为`39d0bb8b07b4ce6b42340a717e2d7d3fb3f8d4c2471757036b81fdddbc25d1fe`。
- 依赖/调用链：Linuxresolver新门，generic/Windows/显式入口不变。
- 逻辑/边界：实际旧resolverRED与有限头/文件/宿主正负控明确。
- 异常处理：两次自有stream关闭、普通错误与KI/SE原对象覆盖；无任务FD。
- 关联模块：LA1 schema及selector不改，显式脚本独立回归。
- 兼容安全：没有权限/服务/依赖新增，没有sameFD/racefree声明。
- 可运行性：root与两审查者各独立旧源码selected1方法/1断言FAIL/0ERROR，纯内存装配候选12通过/零跳过；这只是计划演练，未授磁盘TDD、native、完整守护或总体通过。

进入Task1前root实际sequential-thinking113–115，明确源码/test唯一writer串行、原generic/Windows兼容和独立守护。独立PLAN SPEC后不同QUALITY各零遗留，参考设计状态更新后的SHA256`695a6157faa97ca1e6766b7012667ab32def7f378f6fa71534e7990bc5aa4dac`，状态记录不改变冻结接口/测试合同。

**Execution Mode:** serial。不是机械改动，需调用链与故障验证，Task1→Task2→Task3；进入SDD前root self-review及fresh PLAN SPEC→不同QUALITY。

### 本片提交前完整验收记录

2026-10-11 19:42:59 UTC，root完整`preflight.py`实际exit0、三道全部通过（非only子集）；不凭输出推断完整测试数量。执行期间源码及测试冻结为上述c5c5d88b/0ecaedb6，两阶段独立CODE审查及root各43通过/零跳过，generic与六个Windows函数逐byte不变。compileall-j1、site、governance、20项观察排期、doc-consistency连续两次及diff检查均通过。下一片owner设计草稿未混入本片精确五路径提交。本记录提交前冻结，后续真实main SHA、push与新CI由Git历史及持续对照接续记录；不预记发布成功。

【架构级自检报告】（软件候选）

- ✅ 语法/编译：compileall-j1及实际模块运行通过。
- ✅ 依赖/调用链：专用核验接包内Linuxresolver，原generic/Windows保留。
- ✅ 逻辑/边界：有限头/真实摘要/宿主及拒绝回归通过。
- ✅ 异常处理：本片规定普通失败、KI/SE原对象及自有stream关闭通过。
- ✅ 关联模块：43关联软件方法通过，LA-1及显式脚本保持。
- ✅ 兼容安全：没有执行、FD所有权、权限、依赖或回退扩大。
- ✅ 可运行性：本片软件与完整三道守护通过；安装包、原生同对象启动及R2/R3未授通过。
