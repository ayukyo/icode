# Linux LA-1 内存诊断实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development or nbl.executing-plans to implement this plan task-by-task. 单一实现写者串行推进；独立 SPEC 完成后由不同审查者做 QUALITY。主代理负责完整守护、精确路径提交及 main 发布；实施者不自行提交或推送。

**Goal:** 实现冻结 LA-1 的不可变内存诊断、严格有界 codec、真实宿主收集及当前环境绑定检查；诊断从不授予执行权。

**Architecture:** 新内部模块只复用现有包内 helper 核验与两个 Linux 探针。codec 只验证数据；collector 无参数读取可信宿主；binding 只重读身份。没有 selector、CLI、UI、磁盘缓存、ready 属性、新权限或第二套 probe。

**Tech Stack:** Python >=3.11 标准库 dataclasses/json/hashlib/platform/datetime/unittest；复用 isolation/native_helper/sandbox_policy；无新依赖，编译 -j1（用户上限 -j6）。

冻结设计：[Linux 运行保护准入回执](../specs/2026-10-12-linux-admission-receipt-design.md)。源基线 `8b1afd4d347173453252d3d22ba7ec5cdbd805f5`、实施前main文档提交 `e72c229`。状态：实际软件实现、独立SPEC→不同QUALITY和root完整守护通过，待阶段main提交；真实结果见文末，计划演练不授软件实现或原生信用。三问已在冻结设计确认；root sequential-thinking 92–94、98–100 已完成。只新增两个代码文件：`src/icode/linux_admission_diagnostic.py`、`tests/test_linux_admission_diagnostic.py`。

## 已核对的实际依赖

| 实际对象 | 本片使用方式与限制 |
| --- | --- |
| `native_helper.bundled_linux_helper() -> Path \| None` | 固定包内 `native/icode-landlock`，不查 PATH/项目文件；已内部调用核验 |
| `verify_native_helper(binary: Path, manifest: Path) -> bool` | manifest 是 `binary.parent / 'icode-landlock.sha256'`；拒绝缺失、非普通文件、多链接、无执行权限及摘要不符；没有 ELF machine 核验 |
| `LandlockSandbox(helper: str, manifest: str \| None)` | 由本次已核验 helper 构造候选；不调用 selector，不改 `policy_contract_ready=False` |
| `probe_native_sandbox(sandbox) -> NativeProbeResult` | 仅取 `.ready`，必须 exact bool；不读取 `.checks/.detail` |
| `probe_linux_protected_paths(sandbox) -> LinuxProtectedPathProbeResult` | 仅取 `.passed`，必须 exact bool；`.executed` 含异常路径，不提升完整执行/cleanup 信用 |
| `sandbox_policy.POLICY_SCHEMA_VERSION = 1` | 从真实模块读取；必须 exact int 且 >0，bool 不合格 |
| 既有 `tests/test_native_helper.py` 与 `tests/test_isolation.py` | unittest、`unittest.mock.patch` 和临时目录模式；命令使用仓库 `.venv/bin/python` |

冻结设计实际列出 **13 个顶层 exact keys**，不是 14 个：scope、schema_version、platform、os_build、architecture、helper_sha256、policy_schema_version、checked_at、status、reason、observations、observation_coverage、cleanup_status。observations 另有两个 exact keys。以冻结设计为准，不补自造字段。

研究沿[持续对照](../../agent-landscape-live.md)既有固定 Codex/OpenHands 证据：采纳结果/来源/授权分层；暂缓正式持久化与生产准入；不适配 doctor bool/旧磁盘 JSON 直接授权。复用机制，无源码复制、许可不明代码或新依赖；本计划没有刷新上游 HEAD 或全部观察名单。独立研究由 root 刷新阶段记录，不替代实现验收。

## Task 1：严格 codec → collector → binding（同一完整模块）

**Dependencies:** 冻结设计、上述实际接口核对。

**Parallelizable:** No。codec → collector → binding 是串行依赖；只读研究可以独立进行。

- [ ] 先新增下列完整行为测试。随后建立下面 RED scaffold；模块可导入，四接口和不可变数据形状都存在，不能把 ImportError 当 RED。
- [ ] 运行 `./.venv/bin/python -B -m unittest tests.test_linux_admission_diagnostic.CodecTests.test_exact_bytes_canonical_lf_duplicate_keys_and_named_limit tests.test_linux_admission_diagnostic.HostTests.test_success_reads_actual_digest_without_admission tests.test_linux_admission_diagnostic.HostTests.test_helper_changed_or_disappeared_discards_both_summaries tests.test_linux_admission_diagnostic.HostTests.test_exception_stops_next_probe_but_rechecks_helper_and_sanitizes tests.test_linux_admission_diagnostic.HostTests.test_binding_platform_os_arch_helper_policy_drift_and_read_errors -v`，必须5方法均出现断言失败、0 ERROR，而非导入/拼写/fixture ERROR。重点记录 canonical、畸形拒绝、helper 变化、第一探针异常不启动第二探针及当前绑定漂移失败；其它完整负控在最小实现后逐项取RED，不把TypeError记为行为RED。

RED scaffold 是暂时放入新模块的完整内容；先验证具体行为失败，再整体替换为本任务最终实现：

```python
from __future__ import annotations
import hashlib
import json
import platform
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from . import native_helper, sandbox_policy
from .isolation import LandlockSandbox, probe_native_sandbox, probe_linux_protected_paths

MAX_DIAGNOSTIC_BYTES = 16 * 1024

@dataclass(frozen=True, slots=True)
class LinuxDiagnosticObservations:
    minimal_probe: bool | None
    protected_path_probe: bool | None

@dataclass(frozen=True, slots=True)
class LinuxAdmissionDiagnostic:
    scope: str
    schema_version: int
    platform: str
    os_build: str | None
    architecture: str | None
    helper_sha256: str | None
    policy_schema_version: int
    checked_at: str
    status: str
    reason: str
    observations: LinuxDiagnosticObservations
    observation_coverage: str
    cleanup_status: str

def serialize_linux_admission_diagnostic(report):
    return json.dumps(asdict(report)).encode('ascii')

def validate_linux_admission_diagnostic(wire):
    try:
        payload = json.loads(wire)
        payload['observations'] = LinuxDiagnosticObservations(**payload['observations'])
        return LinuxAdmissionDiagnostic(**payload)
    except Exception:
        raise ValueError('invalid_linux_admission_diagnostic') from None

def collect_linux_admission_diagnostic():
    return LinuxAdmissionDiagnostic(
        'linux_admission_diagnostic', 1, 'linux', 'stub', 'x86_64', None,
        sandbox_policy.POLICY_SCHEMA_VERSION, '2026-10-12T00:00:00Z',
        'incomplete', 'helper_unavailable', LinuxDiagnosticObservations(None, None),
        'legacy_probe_summary_only', 'unknown',
    )

def linux_diagnostic_binding_current(report):
    return True
```

- [ ] RED 确認後以以下完整实现替换 scaffold。codec 是内部纯数据合同；失败统一 `ValueError('invalid_linux_admission_diagnostic') from None`。`Exception` 不吞 KeyboardInterrupt/SystemExit。嵌套 observations 也是 frozen，不能在 frozen 外壳内留下 mutable dict。

```python
"""Internal Linux diagnostics; never grants sandbox execution authority."""
from __future__ import annotations

import hashlib
import json
import platform
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import native_helper, sandbox_policy
from .isolation import (
    LandlockSandbox, probe_linux_protected_paths, probe_native_sandbox,
)

MAX_DIAGNOSTIC_BYTES = 16 * 1024
_KEYS = frozenset({
    'scope', 'schema_version', 'platform', 'os_build', 'architecture',
    'helper_sha256', 'policy_schema_version', 'checked_at', 'status',
    'reason', 'observations', 'observation_coverage', 'cleanup_status',
})
_OBS_KEYS = frozenset({'minimal_probe', 'protected_path_probe'})
_REASONS = frozenset({
    'unsupported_environment', 'helper_unavailable', 'helper_changed',
    'invalid_observation', 'observation_incomplete',
})


@dataclass(frozen=True, slots=True)
class LinuxDiagnosticObservations:
    minimal_probe: bool | None
    protected_path_probe: bool | None


@dataclass(frozen=True, slots=True)
class LinuxAdmissionDiagnostic:
    scope: str
    schema_version: int
    platform: str
    os_build: str | None
    architecture: str | None
    helper_sha256: str | None
    policy_schema_version: int
    checked_at: str
    status: str
    reason: str
    observations: LinuxDiagnosticObservations
    observation_coverage: str
    cleanup_status: str


def _canonical(payload: dict) -> bytes:
    return (json.dumps(
        payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
    ) + '\n').encode('ascii')


def _ascii_os(value: object) -> bool:
    return (type(value) is str and 1 <= len(value) <= 256
            and all(32 <= ord(char) <= 126 for char in value))


def _checked_payload(payload: object) -> dict:
    if type(payload) is not dict or payload.keys() != _KEYS:
        raise ValueError
    if (type(payload['scope']) is not str
            or payload['scope'] != 'linux_admission_diagnostic'
            or type(payload['schema_version']) is not int
            or payload['schema_version'] != 1
            or type(payload['platform']) is not str
            or payload['platform'] != 'linux'
            or type(payload['status']) is not str
            or payload['status'] != 'incomplete'
            or type(payload['observation_coverage']) is not str
            or payload['observation_coverage'] != 'legacy_probe_summary_only'
            or type(payload['cleanup_status']) is not str
            or payload['cleanup_status'] != 'unknown'):
        raise ValueError
    policy = payload['policy_schema_version']
    if type(policy) is not int or policy <= 0:
        raise ValueError
    os_build, arch = payload['os_build'], payload['architecture']
    if os_build is not None and not _ascii_os(os_build):
        raise ValueError
    if arch is not None and (type(arch) is not str or arch not in ('x86_64', 'arm64')):
        raise ValueError
    digest = payload['helper_sha256']
    if digest is not None and (type(digest) is not str
            or re.fullmatch(r'[0-9a-f]{64}', digest) is None):
        raise ValueError
    stamp = payload['checked_at']
    if type(stamp) is not str or re.fullmatch(
            r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z', stamp) is None:
        raise ValueError
    datetime.fromisoformat(stamp[:-1] + '+00:00')
    reason = payload['reason']
    if type(reason) is not str or reason not in _REASONS:
        raise ValueError
    observations = payload['observations']
    if type(observations) is not dict or observations.keys() != _OBS_KEYS:
        raise ValueError
    values = tuple(observations[key] for key in sorted(_OBS_KEYS))
    if any(value is not None and type(value) is not bool for value in values):
        raise ValueError
    complete_host = os_build is not None and arch is not None
    if reason == 'unsupported_environment':
        valid = not complete_host and digest is None and values == (None, None)
    elif reason in ('helper_unavailable', 'helper_changed'):
        valid = complete_host and digest is None and values == (None, None)
    elif reason == 'invalid_observation':
        valid = complete_host and digest is not None and None in values
    else:
        valid = complete_host and digest is not None and all(
            type(value) is bool for value in values)
    if not valid:
        raise ValueError
    return payload


def _pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _report(payload: dict) -> LinuxAdmissionDiagnostic:
    values = dict(payload)
    values['observations'] = LinuxDiagnosticObservations(**values['observations'])
    return LinuxAdmissionDiagnostic(**values)


def serialize_linux_admission_diagnostic(report: LinuxAdmissionDiagnostic) -> bytes:
    try:
        if (type(report) is not LinuxAdmissionDiagnostic
                or type(report.observations) is not LinuxDiagnosticObservations):
            raise ValueError
        wire = _canonical(_checked_payload(asdict(report)))
        if len(wire) > MAX_DIAGNOSTIC_BYTES:
            raise ValueError
        return wire
    except Exception:
        raise ValueError('invalid_linux_admission_diagnostic') from None


def validate_linux_admission_diagnostic(wire: bytes) -> LinuxAdmissionDiagnostic:
    try:
        if type(wire) is not bytes or not 1 <= len(wire) <= MAX_DIAGNOSTIC_BYTES:
            raise ValueError
        payload = _checked_payload(json.loads(
            wire.decode('ascii'), object_pairs_hook=_pairs,
        ))
        if _canonical(payload) != wire:
            raise ValueError
        return _report(payload)
    except Exception:
        raise ValueError('invalid_linux_admission_diagnostic') from None


def _host() -> tuple[str | None, str | None]:
    try:
        os_build = platform.release() + ' ' + platform.version()
        if not _ascii_os(os_build):
            os_build = None
    except Exception:
        os_build = None
    try:
        arch = {'x86_64': 'x86_64', 'amd64': 'x86_64',
                'aarch64': 'arm64', 'arm64': 'arm64'}.get(platform.machine().lower())
    except Exception:
        arch = None
    return os_build, arch


def _helper_identity() -> tuple[Path, str] | None:
    try:
        helper = native_helper.bundled_linux_helper()
        if helper is None:
            return None
        manifest = helper.parent / 'icode-landlock.sha256'
        if native_helper.verify_native_helper(helper, manifest) is not True:
            return None
        with helper.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        # Verify the actual read digest too; this is package consistency, not pinning.
        if (manifest.read_text(encoding='ascii').strip() != digest
                or native_helper.verify_native_helper(helper, manifest) is not True):
            return None
        return helper, digest
    except Exception:
        return None


def _new_report(os_build, arch, digest, policy, stamp, reason, summaries):
    return _report(_checked_payload({
        'scope': 'linux_admission_diagnostic', 'schema_version': 1,
        'platform': 'linux', 'os_build': os_build, 'architecture': arch,
        'helper_sha256': digest, 'policy_schema_version': policy,
        'checked_at': stamp, 'status': 'incomplete', 'reason': reason,
        'observations': dict(zip(('minimal_probe', 'protected_path_probe'), summaries)),
        'observation_coverage': 'legacy_probe_summary_only', 'cleanup_status': 'unknown',
    }))


def collect_linux_admission_diagnostic() -> LinuxAdmissionDiagnostic:
    if not sys.platform.startswith('linux'):
        raise ValueError('linux_admission_unavailable') from None
    try:
        policy = sandbox_policy.POLICY_SCHEMA_VERSION
        if type(policy) is not int or policy <= 0:
            raise ValueError
        stamp = datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
    except Exception:
        raise ValueError('linux_admission_unavailable') from None
    os_build, arch = _host()
    if os_build is None or arch is None:
        return _new_report(os_build, arch, None, policy, stamp,
                           'unsupported_environment', (None, None))
    before = _helper_identity()
    if before is None:
        return _new_report(os_build, arch, None, policy, stamp,
                           'helper_unavailable', (None, None))
    summaries = [None, None]
    # A normal exception terminates observation; existing probes retain cleanup ownership.
    try:
        sandbox = LandlockSandbox(
            helper=str(before[0]), manifest=str(before[0].parent / 'icode-landlock.sha256'),
        )
        first = probe_native_sandbox(sandbox).ready
        summaries[0] = first if type(first) is bool else None
        second = probe_linux_protected_paths(sandbox).passed
        summaries[1] = second if type(second) is bool else None
    except Exception:
        pass
    after = _helper_identity()
    current_host = _host()
    # Policy integrity precedes every post-observation early return.
    try:
        current_policy = sandbox_policy.POLICY_SCHEMA_VERSION
    except Exception:
        raise ValueError('linux_admission_unavailable') from None
    if type(current_policy) is not int or current_policy <= 0 or current_policy != policy:
        raise ValueError('linux_admission_unavailable') from None
    if current_host != (os_build, arch):
        return _new_report(None, current_host[1], None, policy, stamp,
                           'unsupported_environment', (None, None))
    if after is None or after != before:
        return _new_report(os_build, arch, None, policy, stamp,
                           'helper_changed', (None, None))
    reason = 'invalid_observation' if None in summaries else 'observation_incomplete'
    return _new_report(os_build, arch, before[1], policy, stamp, reason, summaries)


def linux_diagnostic_binding_current(report: LinuxAdmissionDiagnostic) -> bool:
    try:
        serialize_linux_admission_diagnostic(report)
        if report.reason != 'observation_incomplete' or not sys.platform.startswith('linux'):
            return False
        if type(sandbox_policy.POLICY_SCHEMA_VERSION) is not int:
            return False
        if sandbox_policy.POLICY_SCHEMA_VERSION != report.policy_schema_version:
            return False
        if _host() != (report.os_build, report.architecture):
            return False
        helper = _helper_identity()
        return helper is not None and helper[1] == report.helper_sha256
    except Exception:
        return False
```

- [ ] 新增下面完整测试文件，codec/collect/binding 在同一文件，但按方法明确依赖。测试 patch 只存在测试内部；公共 collector 不接 observer、helper 路径或 clock 参数。helper 测试使用真实临时字节和真实核验，probe 替身只证控制流及旧摘要合同。

```python
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from dataclasses import FrozenInstanceError, asdict, replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import icode.linux_admission_diagnostic as diagnostic


def report(reason='observation_incomplete'):
    host = (None, 'x86_64') if reason == 'unsupported_environment' else ('kernel build', 'x86_64')
    digest = 'a' * 64 if reason in ('invalid_observation', 'observation_incomplete') else None
    values = (True, False) if reason == 'observation_incomplete' else (None, None)
    return diagnostic.LinuxAdmissionDiagnostic(
        'linux_admission_diagnostic', 1, 'linux', *host, digest, 1,
        '2026-10-12T00:00:00Z', 'incomplete', reason,
        diagnostic.LinuxDiagnosticObservations(*values), 'legacy_probe_summary_only', 'unknown',
    )


def canonical(payload):
    return (json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True) + '\n').encode('ascii')


class CodecTests(unittest.TestCase):
    def invalid(self, wire):
        with self.assertRaises(ValueError) as raised:
            diagnostic.validate_linux_admission_diagnostic(wire)
        self.assertEqual(str(raised.exception), 'invalid_linux_admission_diagnostic')
        self.assertTrue(raised.exception.__suppress_context__)

    def test_five_combinations_roundtrip_and_immutable(self):
        for reason in ('unsupported_environment', 'helper_unavailable', 'helper_changed',
                       'invalid_observation', 'observation_incomplete'):
            with self.subTest(reason=reason):
                source = report(reason)
                wire = diagnostic.serialize_linux_admission_diagnostic(source)
                self.assertEqual(wire, canonical(asdict(source)))
                self.assertEqual(diagnostic.validate_linux_admission_diagnostic(wire), source)
                with self.assertRaises(FrozenInstanceError):
                    source.status = 'ready'
                with self.assertRaises(FrozenInstanceError):
                    source.observations.minimal_probe = True

    def test_exact_bytes_canonical_lf_duplicate_keys_and_named_limit(self):
        wire = canonical(asdict(report()))
        self.assertEqual(diagnostic.MAX_DIAGNOSTIC_BYTES, 16384)
        invalid = [wire.decode(), bytearray(wire), memoryview(wire), wire[:-1],
                   wire + b'\n', b' ' + wire, wire.replace(b':', b': ', 1),
                   wire.replace(b'"schema_version":1', b'"schema_version":1,"schema_version":1'),
                   wire.replace(b'"minimal_probe":true', b'"minimal_probe":true,"minimal_probe":true'),
                   b'\xff\n', b'{}\n', b'[]\n']
        for value in invalid:
            with self.subTest(kind=type(value), size=len(value)):
                self.invalid(value)
        # Both exact bound and bound+1 reach rejection without accepting padding.
        for size in (16384, 16385):
            self.invalid(wire[:-1] + b' ' * (size - len(wire)) + b'\n')
        with patch.object(diagnostic, 'MAX_DIAGNOSTIC_BYTES', len(wire)):
            self.assertEqual(diagnostic.validate_linux_admission_diagnostic(wire), report())
        with patch.object(diagnostic, 'MAX_DIAGNOSTIC_BYTES', len(wire) - 1):
            self.invalid(wire)
            with self.assertRaisesRegex(ValueError, '^invalid_linux_admission_diagnostic$'):
                diagnostic.serialize_linux_admission_diagnostic(report())

    def test_oversize_canonical_wire_rejected_by_both_interfaces(self):
        source = report()
        wire = canonical(asdict(source))
        with patch.object(diagnostic, 'MAX_DIAGNOSTIC_BYTES', len(wire) - 1):
            self.invalid(wire)
            with self.assertRaisesRegex(ValueError, '^invalid_linux_admission_diagnostic$'):
                diagnostic.serialize_linux_admission_diagnostic(source)

    def test_types_enums_host_timestamp_and_legacy_dict_rejected(self):
        mutations = {
            'scope': ['other'], 'schema_version': [True, 2, '1'],
            'platform': ['windows'], 'policy_schema_version': [True, 0, -1, '1'],
            'status': ['ready', 'blocked'], 'reason': ['unknown'],
            'observation_coverage': ['full'], 'cleanup_status': ['passed'],
            'os_build': ['', 'x' * 257, 'é', 'a\nb', 1],
            'architecture': ['mips', 1], 'helper_sha256': ['A' * 64, 'a' * 63, 1],
            'checked_at': ['2026-02-30T00:00:00Z', '2026-10-12T00:00:00+00:00',
                           '2026-10-12T00:00:00.1Z', '0000-01-01T00:00:00Z'],
            'observations': [{'minimal_probe': 1, 'protected_path_probe': False},
                             {'minimal_probe': True},
                             {'minimal_probe': True, 'protected_path_probe': False, 'detail': 'private'}],
        }
        for key, values in mutations.items():
            for value in values:
                payload = asdict(report())
                payload[key] = value
                with self.subTest(key=key, value=value):
                    self.invalid(canonical(payload))
        for payload in ({'ready': True, 'detail': 'secret'},
                        dict(asdict(report()), unexpected='private')):
            self.invalid(canonical(payload))
        missing = asdict(report())
        del missing['scope']
        self.invalid(canonical(missing))
        with self.assertRaisesRegex(ValueError, '^invalid_linux_admission_diagnostic$'):
            diagnostic.serialize_linux_admission_diagnostic(replace(report(), status='ready'))
        with self.assertRaisesRegex(ValueError, '^invalid_linux_admission_diagnostic$'):
            diagnostic.serialize_linux_admission_diagnostic(asdict(report()))
        with self.assertRaisesRegex(ValueError, '^invalid_linux_admission_diagnostic$'):
            diagnostic.serialize_linux_admission_diagnostic(replace(
                report(), observations={'minimal_probe': True, 'protected_path_probe': False}))

    def test_reason_combinations_and_partial_summary(self):
        for reason in ('unsupported_environment', 'helper_unavailable', 'helper_changed',
                       'invalid_observation', 'observation_incomplete'):
            payload = asdict(report(reason))
            payload['observations'] = {'minimal_probe': True, 'protected_path_probe': False}
            if reason != 'observation_incomplete':
                self.invalid(canonical(payload))
        for key in ('os_build', 'architecture', 'helper_sha256'):
            payload = asdict(report())
            payload[key] = None
            self.invalid(canonical(payload))
        for values in ((None, False), (True, None), (None, None)):
            source = replace(report('invalid_observation'),
                             observations=diagnostic.LinuxDiagnosticObservations(*values))
            self.assertEqual(diagnostic.validate_linux_admission_diagnostic(
                diagnostic.serialize_linux_admission_diagnostic(source)), source)


class HostTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.helper = Path(self.directory.name) / 'icode-landlock'
        self.write_helper(b'helper-a')
        self.patches = [
            patch.object(diagnostic.sys, 'platform', 'linux'),
            patch.object(diagnostic.platform, 'release', return_value='kernel'),
            patch.object(diagnostic.platform, 'version', return_value='build'),
            patch.object(diagnostic.platform, 'machine', return_value='x86_64'),
            patch.object(diagnostic.native_helper, 'bundled_linux_helper', return_value=self.helper),
            patch.object(diagnostic, 'probe_native_sandbox', return_value=SimpleNamespace(ready=True)),
            patch.object(diagnostic, 'probe_linux_protected_paths', return_value=SimpleNamespace(passed=False)),
        ]
        self.mocks = [item.start() for item in self.patches]
        for item in self.patches:
            self.addCleanup(item.stop)

    def write_helper(self, content):
        self.helper.write_bytes(content)
        os.chmod(self.helper, 0o755)
        (self.helper.parent / 'icode-landlock.sha256').write_text(
            hashlib.sha256(content).hexdigest() + '\n', encoding='ascii')

    def collect(self):
        result = diagnostic.collect_linux_admission_diagnostic()
        self.assertEqual(diagnostic.validate_linux_admission_diagnostic(
            diagnostic.serialize_linux_admission_diagnostic(result)), result)
        self.assertEqual(result.status, 'incomplete')
        self.assertEqual(result.cleanup_status, 'unknown')
        return result

    def test_success_reads_actual_digest_without_admission(self):
        result = self.collect()
        self.assertEqual(result.reason, 'observation_incomplete')
        self.assertEqual(result.helper_sha256, hashlib.sha256(b'helper-a').hexdigest())
        self.assertEqual(result.os_build, 'kernel build')
        self.assertEqual(result.observations, diagnostic.LinuxDiagnosticObservations(True, False))
        self.assertTrue(diagnostic.linux_diagnostic_binding_current(result))
        self.assertFalse(hasattr(result, 'ready'))
        self.assertRegex(result.checked_at, r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')
        for values in ((True, True), (False, True), (False, False)):
            self.mocks[5].return_value = SimpleNamespace(ready=values[0])
            self.mocks[6].return_value = SimpleNamespace(passed=values[1])
            self.assertEqual(self.collect().reason, 'observation_incomplete')

    def test_nonlinux_unsupported_and_helper_unavailable_do_not_probe(self):
        with patch.object(diagnostic.sys, 'platform', 'darwin'):
            with self.assertRaisesRegex(ValueError, '^linux_admission_unavailable$'):
                diagnostic.collect_linux_admission_diagnostic()
        for field, value in (('machine', 'mips'), ('release', '\n')):
            with patch.object(diagnostic.platform, field, return_value=value):
                result = self.collect()
                self.assertEqual(result.reason, 'unsupported_environment')
                self.assertFalse(diagnostic.linux_diagnostic_binding_current(result))
        self.helper.unlink()
        result = self.collect()
        self.assertEqual(result.reason, 'helper_unavailable')
        self.assertFalse(diagnostic.linux_diagnostic_binding_current(result))
        self.mocks[5].assert_not_called()
        self.mocks[6].assert_not_called()

    def test_helper_changed_or_disappeared_discards_both_summaries(self):
        for changed in (True, False):
            self.write_helper(b'helper-a')
            def change(sandbox):
                if changed:
                    self.write_helper(b'helper-b')
                else:
                    self.helper.unlink()
                return SimpleNamespace(passed=True)
            self.mocks[6].side_effect = change
            result = self.collect()
            self.assertEqual(result.reason, 'helper_changed')
            self.assertIsNone(result.helper_sha256)
            self.assertEqual(result.observations, diagnostic.LinuxDiagnosticObservations(None, None))
            self.assertFalse(diagnostic.linux_diagnostic_binding_current(result))

    def test_exception_stops_next_probe_but_rechecks_helper_and_sanitizes(self):
        def broken(sandbox):
            self.write_helper(b'helper-b')
            raise RuntimeError('/private/path SID secret')
        self.mocks[5].side_effect = broken
        result = self.collect()
        self.assertEqual(result.reason, 'helper_changed')
        self.mocks[6].assert_not_called()
        self.assertNotIn(b'private', diagnostic.serialize_linux_admission_diagnostic(result))
        self.mocks[5].side_effect = RuntimeError('private')
        result = self.collect()
        self.assertEqual(result.reason, 'invalid_observation')
        self.assertFalse(diagnostic.linux_diagnostic_binding_current(result))
        self.mocks[6].assert_not_called()

    def test_malformed_summary_is_null_and_second_exception_is_partial(self):
        for value in (1, 'true', None):
            self.mocks[5].return_value = SimpleNamespace(ready=value)
            result = self.collect()
            self.assertEqual(result.reason, 'invalid_observation')
            self.assertIsNone(result.observations.minimal_probe)
        self.mocks[5].return_value = SimpleNamespace(ready=True)
        self.mocks[6].side_effect = RuntimeError('private')
        result = self.collect()
        self.assertEqual(result.observations, diagnostic.LinuxDiagnosticObservations(True, None))

    def test_binding_platform_os_arch_helper_policy_drift_and_read_errors(self):
        result = self.collect()
        cases = [patch.object(diagnostic.sys, 'platform', 'win32'),
                 patch.object(diagnostic.platform, 'release', return_value='new'),
                 patch.object(diagnostic.platform, 'machine', return_value='aarch64'),
                 patch.object(diagnostic.platform, 'version', side_effect=OSError('private')),
                 patch.object(diagnostic.native_helper, 'bundled_linux_helper', return_value=None),
                 patch.object(diagnostic.sandbox_policy, 'POLICY_SCHEMA_VERSION', 2),
                 patch.object(diagnostic.sandbox_policy, 'POLICY_SCHEMA_VERSION', True)]
        for change in cases:
            with change:
                self.assertFalse(diagnostic.linux_diagnostic_binding_current(result))
        self.write_helper(b'helper-b')
        self.assertFalse(diagnostic.linux_diagnostic_binding_current(result))
        self.assertFalse(diagnostic.linux_diagnostic_binding_current(asdict(result)))
        self.assertFalse(diagnostic.linux_diagnostic_binding_current(replace(result, status='ready')))
        self.assertFalse(diagnostic.linux_diagnostic_binding_current(report('helper_changed')))

    def test_host_changes_during_observation_clear_binding(self):
        self.mocks[1].side_effect = ['kernel', 'new']
        result = self.collect()
        self.assertEqual(result.reason, 'unsupported_environment')
        self.assertIsNone(result.os_build)
        self.assertIsNone(result.helper_sha256)
        self.assertEqual(result.observations, diagnostic.LinuxDiagnosticObservations(None, None))

    def test_interrupts_propagate_identical_objects(self):
        for interruption in (KeyboardInterrupt('private'), SystemExit(7)):
            for target, operation in (
                (self.mocks[5], diagnostic.collect_linux_admission_diagnostic),
                (self.mocks[4], lambda: diagnostic.linux_diagnostic_binding_current(report())),
            ):
                target.side_effect = interruption
                with self.assertRaises(type(interruption)) as raised:
                    operation()
                self.assertIs(raised.exception, interruption)
                target.side_effect = None
        self.mocks[6].assert_not_called()

    def test_arm_aliases_and_invalid_policy(self):
        for raw, expected in (('AMD64', 'x86_64'), ('aarch64', 'arm64'), ('arm64', 'arm64')):
            with patch.object(diagnostic.platform, 'machine', return_value=raw):
                self.assertEqual(self.collect().architecture, expected)
        for value in (True, 0, '1'):
            with patch.object(diagnostic.sandbox_policy, 'POLICY_SCHEMA_VERSION', value):
                with self.assertRaisesRegex(ValueError, '^linux_admission_unavailable$'):
                    diagnostic.collect_linux_admission_diagnostic()

    def test_policy_drift_precedes_helper_and_host_early_returns(self):
        for policy in (True, 2, 0):
            for helper_change in ('changed', 'missing', 'stable'):
                for host_change in (False, True):
                    with self.subTest(policy=policy, helper=helper_change, host=host_change):
                        self.write_helper(b'helper-a')
                        self.mocks[1].side_effect = None
                        self.mocks[1].return_value = 'kernel'
                        def change(sandbox):
                            if helper_change == 'changed':
                                self.write_helper(b'helper-b')
                            elif helper_change == 'missing':
                                self.helper.unlink()
                            if host_change:
                                self.mocks[1].return_value = 'new'
                            diagnostic.sandbox_policy.POLICY_SCHEMA_VERSION = policy
                            return SimpleNamespace(passed=True)
                        self.mocks[6].side_effect = change
                        with patch.object(diagnostic.sandbox_policy, 'POLICY_SCHEMA_VERSION', 1):
                            with self.assertRaisesRegex(ValueError, '^linux_admission_unavailable$'):
                                diagnostic.collect_linux_admission_diagnostic()


if __name__ == '__main__':
    unittest.main()
```

- [ ] 实施者对新增policy优先级先取行为RED：临时将current_policy核验块移回helper/host早返回之后，运行 `./.venv/bin/python -B -m unittest tests.test_linux_admission_diagnostic.HostTests.test_policy_drift_precedes_helper_and_host_early_returns -v`，预期18组合中至少变化分支出现assertion FAIL、0 ERROR；再恢复完整实现。该RED实际对应观察中policy变化，不用错误导入替代。
- [ ] GREEN：运行 `./.venv/bin/python -B -m unittest tests.test_linux_admission_diagnostic -v`，预期 15 方法、0 skip、0 failure/error；测试替身与真实 native 信用分账，不把该计数当实际运行结果。
- [ ] 定点关联：`./.venv/bin/python -B -m unittest tests.test_linux_admission_diagnostic tests.test_native_helper tests.test_isolation`。结果取真实输出；已有平台 skip 保留，不能算通过。
- [ ] 负控必须实际证明测试捕获边界失效。以下临时 monkeypatch 命令没有源码持久改动；每个 test runner 预期 FAIL，全部确实失败后脚本 exit0。若任何变体成功，脚本 exit1 并先补测试。两个独立codec变体仅删除长度上限门，保留strict bytes、schema、canonical与固定错误；大小行为测试不含常量值断言。变体不修改默认命名常量，测试内部降低门限构成有效超限canonical输入。常量16384的恒等断言另账，不能当长度安全RED。

```bash
./.venv/bin/python -B - <<'PY'
import unittest
from dataclasses import asdict
from unittest.mock import patch
import icode.linux_admission_diagnostic as d

def validate_without_size_gate(wire):
    try:
        if type(wire) is not bytes or not wire:
            raise ValueError
        payload = d._checked_payload(d.json.loads(
            wire.decode('ascii'), object_pairs_hook=d._pairs,
        ))
        if d._canonical(payload) != wire:
            raise ValueError
        return d._report(payload)
    except Exception:
        raise ValueError('invalid_linux_admission_diagnostic') from None

def serialize_without_size_gate(report):
    try:
        if (type(report) is not d.LinuxAdmissionDiagnostic
                or type(report.observations) is not d.LinuxDiagnosticObservations):
            raise ValueError
        return d._canonical(d._checked_payload(asdict(report)))
    except Exception:
        raise ValueError('invalid_linux_admission_diagnostic') from None

assert d.MAX_DIAGNOSTIC_BYTES == 16384
cases = (
    ('tests.test_linux_admission_diagnostic.CodecTests.test_oversize_canonical_wire_rejected_by_both_interfaces',
     patch.object(d, 'validate_linux_admission_diagnostic', validate_without_size_gate)),
    ('tests.test_linux_admission_diagnostic.CodecTests.test_oversize_canonical_wire_rejected_by_both_interfaces',
     patch.object(d, 'serialize_linux_admission_diagnostic', serialize_without_size_gate)),
    ('tests.test_linux_admission_diagnostic.HostTests.test_helper_changed_or_disappeared_discards_both_summaries',
     patch.object(d, 'linux_diagnostic_binding_current', return_value=True)),
    ('tests.test_linux_admission_diagnostic.HostTests.test_exception_stops_next_probe_but_rechecks_helper_and_sanitizes',
     patch.object(d, '_helper_identity', return_value=None)),
)
valid_red = True
for name, mutation in cases:
    with mutation:
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromName(name))
    valid_red = valid_red and bool(result.failures) and not result.errors
raise SystemExit(0 if valid_red else 1)
PY
```

第四负控刻意抹去真实 helper 身份，测试应断言 expected helper_changed 与实际 helper_unavailable 不同；它只证测试区分收集前不可用与观察中变化，不冒充直接验证 probe2 重入。probe2 不启动由真实普通异常测试的 `assert_not_called` 单独验收。

## Task 2：冻结软件合同与主代理验收

**Dependencies:** Task 1 GREEN、有效断言 RED、负控全部闭合。

**Parallelizable:** No。先独立 SPEC，修完冻结，再由不同审查者 QUALITY；实现者不与审查者同时改文件。

- [ ] 独立 SPEC 逐项核 13 exact keys/5组合/bytes/canonical LF/16KiB/重复key/bool整数拒绝/固定错误from None/KI-SE原对象。核 helper变化优先于畸形摘要，helper_changed清全部摘要和摘要绑定；invalid_observation只能稳定合法helper；正常异常后probe2不启动。
- [ ] 不同 QUALITY 核隐私、异常、TOCTOU边界、不可变嵌套、调用链及测试是否只镜像实现。明确 helper 的前后读取只是本地诊断一致性，不是 race-free pin、ELF架构或发布者认证。fresh observation_incomplete 可绑定True，但状态与cleanup仍incomplete/unknown，没有执行者接线。
- [ ] 主代理完整回读两个新文件，检查 `git diff --check` 与精确改动范围；不改既有探针、评分器、doctor字典、授权或生产后端。
- [ ] 主代理运行 `./.venv/bin/python -m compileall -q -j1 src/icode/linux_admission_diagnostic.py tests/test_linux_admission_diagnostic.py`，以及新完整 `./.venv/bin/python scripts/preflight.py`；提交前再运行 `./.venv/bin/python scripts/preflight.py --only secrets`、`./.venv/bin/python scripts/preflight.py --only submodule`、`./.venv/bin/python scripts/check_site.py`，预期均exit0。不能复用旧结果或访问/打印 key；执行现有secret守护不等于授权读取key正文。
- [ ] 主代理写实际七维架构级自检报告：语法编译、依赖调用链、逻辑边界、异常处理、关联模块、兼容安全、可运行性。每项只依据真实证据，不把100%可运行外推到原生安装或产品授权。
- [ ] 主代理精确 whitelist 仅两个新代码文件、本计划及已经批准的阶段证据文档；main-only，核 cached diff 后按已授权发布流程提交，记录精确 SHA。子代理不运行 Git 写操作。
- [ ] 阶段结束刷新持续竞品对照的相关固定证据与采纳/暂缓/不适配，保留历史日期，不声称新上游 HEAD。
- [ ] Linux installed x64/arm64 真实 helper/probe/环境漂移验收另账，在后续精确 SHA 原生窗口实施；没有真实 native 测试不能关闭安装门。Windows/macOS、R2/R3、生产选择、获批网络合流、正式缓存/UI均未由本片完成。

## 需审查的细化与风险

OS build使用真实 `platform.release() + ' ' + platform.version()`，非ASCII/超过256/读取异常为null；架构宿主规范化，不认证ELF。收集前后宿主身份变化清绑定、OS=null并返回unsupported_environment，符合该组合至少一项null；policy常量损坏或观察中变化无法组成任何合法回执，固定linux_admission_unavailable。额外宿主复核仅各读一次，helper核验是有限本地文件读取；不重跑probe、不认证已执行对象。与冻结设计相容性须在SPEC中明确核对。正常异常只捕获Exception；KI/SE传播，现有probe内部责任不迁移到诊断对象。数据格式认证不等于来源认证，手工构造的合法诊断也永远无执行权。

旧 minimal probe 的 `not success(argv)` 会将部分启动None折叠为DENY子检查，protected异常仍可能executed=True；本片不取checks/detail补信用。前后摘要相同看不见A→B→A，也不固定probe实际执行的FD；bindingTrue只表示当前宿主身份相符，不能认证探针完整执行、cleanup、helper运行对象或授权来源。

**Execution Mode:** serial。按 codec → collector → binding → 软件 SPEC → 不同 QUALITY → root 守护/阶段提交推进；installed Linux x64/arm64 原生验收后续另账。

## 实际执行记录（2026-10-12 北京时间，软件门通过）

上文代码块是经过计划审查的设计参考，不是当前源码逐字副本。实际实现复用了相同合同，但内部校验函数与测试方法名称不同；重跑应以 `src/icode/linux_admission_diagnostic.py`、`tests/test_linux_admission_diagnostic.py` 的真实源码和下面实际命令为准，不执行已被实际源码替代的计划内 mutation 示例。

首轮 codec 的五个方法取得14个断言失败、0 ERROR 后转绿。随后发现 collector/binding 曾先于对应测试实现；这部分未获 TDD 信用，已暂停并丢弃未提交实现。根代理在重置后的合法 scaffold 上复跑十个 Host 方法，取得27个断言失败、0 ERROR；新的独立实现任务先复现同一 RED，再从测试实现 collector/binding。原15个方法转绿，另七个已满足现有合同的补充方法直接转绿，不补造它们的历史 RED。

实际软件 SPEC 对首版22个方法独立运行通过、C0/I0/M0。不同 QUALITY 指出系统时间读取/格式化的普通异常未脱敏（I1）；新增时钟测试先取得2个断言失败、0 ERROR，再仅给时间生成增加普通异常边界。六个子项覆盖 now/strftime 的普通异常、KI与SE；失败时不读取宿主/helper、不调用探针，中断保留原对象。修复后23个方法通过，待独立复审和根代理完整守护。

首版完整 preflight 在 QUALITY 发现 I1 后由根代理主动中断，返回 exit1/测试门阻断；不计全绿、不用于提交。修复后必须从头重跑。首版实现者的关联测试126项为115通过/11既有跳过，包含旧原生调用，不把它当新诊断 installed x64/ARM64 验收；独立审查仅运行纯替身的新测试。

根代理已完整回读两个实际文件，运行新22项为22通过；实际源码内存负控分别移除 serializer/validator 的尺寸门，独立超限测试各取得1个断言失败、0 ERROR；强制 binding=True，helper变化测试取得1个断言失败、0 ERROR。负控不修改磁盘源码，MAX默认仍16384。时钟修复后SPEC→不同QUALITY各独立23项通过、C0/I0/M0；根代理移除时间异常保护的实际源码负控取得2个断言失败、0 ERROR（第一次演练复制了全局字典，使mock未生效，6个失败不计信用；改用实际模块全局后重跑）。完整守护与阶段提交尚未通过，不提前登记完成。

当前重跑入口：`./.venv/bin/python -B -m unittest tests.test_linux_admission_diagnostic -q`。诊断仍固定 incomplete、legacy_probe_summary_only、cleanup unknown；没有生产选择、缓存、CLI/UI或执行授权接线。

18:22:39 UTC，修复后根代理完整preflight exit0，密钥扫描、子模块完整性、全测试三道均通过；此前主动中断结果不被覆盖为通过。随后根代理独立运行新诊断/native_helper/isolation关联套件，127项、116通过/11既有跳过、0 FAIL/ERROR，28.795秒。compileall -j1、diff检查、官网检查均exit0；三文档一致性检查修复表格内union管线转义后零疑似项。提交前另跑fresh secrets与submodule守护，不读取外置key正文。

最终冻结源码SHA256为 `cbbf95bf4c0421a057472e1737f808dc298ae800ca11a3696023d29a79d8e3d5`，测试为 `3132f2ac0763c2c46050f833acd395419281c773e0d6c899975d9894decba78e`。本记录只关闭LA-1软件门；installed两架构、生产准入、网络合流、持久化/UI及R2/R3总门仍未关闭。

【架构级自检报告】

- 语法/编译：compileall -j1、23项导入/执行及完整测试门通过。
- 依赖/调用链：复用现有helper/probe/policy接口；无执行者、selector或模型授权接线。
- 逻辑/边界：严格13键/五组合、helper/host/policy漂移、规范格式、超限与绑定负控通过。
- 异常处理：普通错误固定脱敏、时钟六子项与KI/SE原身份通过；未知cleanup不补信用。
- 关联模块：127项关联回归无失败；既有11跳过保留，不当安装验收。
- 兼容安全：旧后端、状态机、Git工具、权限、依赖及vendor不变，诊断始终无执行权。
- 可运行性：本机软件守护通过；真实安装包及R2/R3未验收，不报告100%总体通过。
