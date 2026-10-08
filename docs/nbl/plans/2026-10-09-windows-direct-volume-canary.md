# Windows 固定卷路径兼容性探针 Implementation Plan

## 2026-10-09后续原生窗口与路径夹具修正

0f来源窗口最终收尾：run37823992396/head SHA0f终态success，validate及四signed全部成功；根独立回读四格完整decoded日志与元数据，各19PASS，proof依次为x64/3.11.9 `54052974`、x64/3.12.10 `54052995`、ARM64/3.11.9 `54055031`、ARM64/3.12.10 `54053287`，jobs分别 `113477187317/113477187183/113477187282/113477187287`。实际x64 Server2025 image20260925.250.1，ARM Windows11 image20261004.176.1；均Go1.27.1及9项offline测试通过。原始direct-volume/ctime探针输出未转发，只取得实际安装链19项摘要，不冒称原marker或标准用户/UAC/held-HANDLE证据。主CI、来源、Pages均终态STOP；当前构建context诊断尚未发布，不能沿用0f信用。下面“来源进行中”属于收尾前历史观察。

夹具修正已main提交推送为 `0f557b10c9df759de4d7550dc73f5d99c3b95f2a`，父58；push/远端refs/官方main分别核实。[主CI37823992667](https://github.com/ayukyo/icode/actions/runs/37823992667)终态37success/4failure/3整jobskip。根独立读macOS job113471953291：418tests/0skip及75lease/0skip成功；独立读两个Windows workspace113471953110/113471953430：各412tests/20既有skip，旧路径断言不再在失败集合。x64仅两ERROR（Git10093、observed[0] IndexError），ARM仅一FAIL一ERROR（Git10038的dispatch0!=1、Git10093）；不把x64 IndexError倒填成10038。非verbose日志不含该method单独PASS行，证据来自精确SHA选择合同与实际整套/失败清单，不冒称独立取得单测试标记。两Reviewer仍exit78/WFP无匹配drop，R2/R3不变；0f来源四signed仍进行中，Pages精确SHA已success并STOP。

一行夹具修正最终软件门：独立双审各51PASS/0skip/0问题，根20轮1020PASS/0skip（3.370秒），DEFAULT418PASS/0skip（165.288秒）；新完整preflight三道通过，2261 total/2202PASS/59既有skip/0FAIL/0ERROR，测试477.499秒、守护478.797秒。compileall-j1及治理/站点/竞品/diff通过；目标SHA前后未变。此窗口准备精确main提交推送，下一新SHA原生夹具结果仍待验；下面“进行中”是收尾前历史记录。

本窗口最新收尾：来源run37820895762已终态success，validate及四signed全部成功；最后ARM64 Py3.11 job113464942576证明54045309。根代理已经独立读取四格完整decoded日志及run SHA/终态，不只依赖观察者结论。四格各19PASS，均完成已安装gh→C binding→Go真实正负控→固定卷路径→v1/拒绝→导出；两Py3.12最终bytes构建本轮实际通过。固定卷路径只关闭此CI兼容性子门，原marker未公开仍如实记录，不授锁/UAC/生产权限。CI及Pages也已终态，独立观察者全部STOP，无取消/重跑。

| 架构/实际Python | job | proof | 实际OS/image | 此窄原生链 |
|---|---|---|---|---|
| x64/3.11.9 | 113464942515 | 54044125 | Server2025/windows-2025-vs2026 20260925.250.1 | 19PASS |
| x64/3.12.10 | 113464942560 | 54044235 | 同x64 image | 19PASS |
| ARM64/3.11.9 | 113464942576 | 54045309 | Windows11/windows-11-vs2026-arm64 20261004.176.1 | 19PASS |
| ARM64/3.12.10 | 113464942575 | 54044287 | 同ARM64 image | 19PASS |

夹具修正现已独立SPEC与不同QUALITY均批准0/0/0；各51PASS/0skip（0.219/0.177秒），两个审查者都实际用自有目录别名复现旧断言失败和新方法通过。根20轮1020PASS/0skip，DEFAULT418PASS/0skip（165.288秒）；新完整preflight进行中。此一行修正尚未发布或取得新SHA原生结果。以下三格已成功的文字是收尾前观察，不覆盖上表最新四格。

main `58c93518117c117f0e37c8af33ef2a049ddfdbe6` 已提交推送并由远端 refs/官方接口核实。主 [CI37820895924](https://github.com/ayukyo/icode/actions/runs/37820895924) 终态 failure：44 jobs 为36success/5failure/3整jobskip；双Python全仓各2261 total/71skip成功。新资源夹具在Windows短名 `RUNNER~1` 与规范长名比较、macOS `/var` 与 `/private/var` 比较失败：根代理分别回读 [x64日志113461355989](https://github.com/ayukyo/icode/actions/runs/37820895924/job/113461355989) 和 [macOS日志113461355841](https://github.com/ayukyo/icode/actions/runs/37820895924/job/113461355841)。两Windows workspace各412 total/2FAIL/1ERROR/20skip；macOS418 total/1FAIL/0skip。既有SKILL Git匿名管道和Reviewer无匹配WFP拒绝事件仍独立失败，不归因于此夹具。

生产者本来就规范化包路径及purelib；修正只把测试期望根改成 `Path(raw).resolve()`，保持全部tuple和拒绝断言，生产源码/权限/vendor/workflow无修改。根真实临时目录别名先1assertion FAIL/0ERROR后GREEN；独立SPEC自有别名同样RED→GREEN，51PASS/0skip（0.219秒）、0/0/0。当前测试SHA256 `1b97ca3d0e280ce2c5583f9eb96af92753efc60ea24f1fdff9508cbf190b7cd6`；不同QUALITY、DEFAULT/全仓守护另验。根20轮实际1020PASS/0skip（3.370秒）。此WIP还未提交，新SHA Windows/macOS夹具复验不可用58的结果代替。

同一58 [来源run37820895762](https://github.com/ayukyo/icode/actions/runs/37820895762) 已有x64 Py3.11 [113464942515](https://github.com/ayukyo/icode/actions/runs/37820895762/job/113464942515)、x64 Py3.12 [113464942560](https://github.com/ayukyo/icode/actions/runs/37820895762/job/113464942560)、ARM64 Py3.12 [113464942575](https://github.com/ayukyo/icode/actions/runs/37820895762/job/113464942575) success，各安装摘要19PASS，含fixed-volume接受；证明54044125/54044235/54044287。根已独立回读x64 Py3.11完整日志；两Py3.12为独立观察者回读，完整四格还差ARM64 Py3.11。原探针成功标记被既有摘要捕获，日志没有该原字符串，不声称取得原marker。两Py3.12原先生成头失败本轮未复现，但不是生产锁/UAC/标准用户/Win10/配额或R2/R3总门证明；本片仍 `partially_verified`。下面矩阵是此前软件冻结时的历史记录，不倒填原生层。

## 2026-10-09实施窗口（软件审查中，非原生结论）

Tasks1–3源码完成：作者初始夹具错误修正后，旧main/缺接口真实4FAIL/0ERROR；扩展接口与DEFAULT真实18FAIL/0ERROR，再19PASS/0skip。根完整回读后补调用顺序/无NUL与receipt缺字段/错值负控；同期9ed两Py3.12生成头失败促成最小ctime修复，新增回归先3assertion FAIL/0ERROR，再GREEN。当前7文件组合50PASS/0skip（0.188秒），编译-j1通过；Task4独立SPEC→不同QUALITY、20轮、DEFAULT和全仓守护尚未完成，未提交。下面未打勾参考步骤保留原设计状态，不代表这些结果已在Windows运行。

ctime修复只在Windows跨路径/FD排除语义不同的ctime，并保留可用birthtime和其余对象身份；两侧各自前后仍完整ctime、POSIX跨仍完整。生成器固定失败报文不变、旧头不能报告成功。该组合阶段不扩大产品API/vendor/Go/C/workflow权限。9ed原生四格为两Py3.11通过、两Py3.12失败，后续四格须绑定本阶段新SHA；完整R2/R3门仍未过。

进一步兼容复核：仅win32且提供st_birthtime_ns时采用跨birthtime；无该字段的3.11保留原完整crossctime。新增legacy对照实际1FAIL/0ERROR→GREEN，最终定点51PASS/0skip（0.186秒），旧50项批准失效并重新审查7文件。根首次ctime夹具插入位置曾产生NameError，已改正且不计有效RED；上面的3FAIL指修正后无ERROR断言窗口。源码最终冻结生成器 `7b4badefddc9348e6972220eb4869966c00d4b9d7e8380745e8ed712f3428894`、binding测试 `8f8e88c39521869d981f47eb7a6acced38960a46a517b52eb590a9514a699d5f`；其它五文件保持冻结，native仍待验。

最终冻结独立SPEC实际51PASS/0skip（0.215秒）；不同QUALITY实际87PASS/0skip（6.933秒），两审0/0/0批准，7SHA前后相同。QUALITY包含真实POSIX hostC/CMake合成逻辑和有界捕获负控，不授Windows信用。根20轮串行守护已开始，DEFAULT/全仓尚未完成；未提交或推送本片。

后续根守护：7文件有序sha256sum输出聚合为 `ca04e90ce1e208cb0df4e0fe2d91ae7c04706672b1e9350ea62ff2ec02b2be14`；20轮每轮87方法，实际1740PASS/0skip（137.184秒），每轮含hostC/CMake和5秒超时负控，编译1。DEFAULT已开始；全仓preflight待其完成后串行运行。未改vendor/native/权限，未给新四格原生信用。

后续DEFAULT实际418PASS/0skip（164.201秒），完整preflight三道串行运行中；尚未提交。治理/站点/竞品检查及compileall-j1通过，文档收尾后再核非测试守护。

最终本机守护返回：完整preflight实际2261 total/2202PASS/59既有skip/0FAIL/0ERROR，三道全部通过；测试479.282秒、守护480.571秒。独立双审、20轮、DEFAULT及此全仓守护针对相同7文件冻结。文档更新后复核非测试检查，准备按既有授权main提交推送；新SHA原生四格仍未运行。此结果不使下面deploy/consumption变成pass。

### acceptance_contract

| Expected behavior | Required layers | Consumers | Scenarios | Environment/device | Baseline | Pass criteria |
|---|---|---|---|---|---|---|
| CI安装Go使用四条固定卷路径返回正例及wrong-SHA拒绝；失败不导出 | static/unit/build/host/deploy/consumption | 新探针/有界runner/signed安装唯一接点/现Go | 两架构两解释器、Unicode/错误/旧分支 | 本机逻辑；Windows signed四格 | 9ed加上述7文件冻结 | 软件及新SHA四格均实际通过；不要求本片证明UAC/标准用户隔离 |

### verification_matrix

| Layer | Required | Consumer | Scenario | Environment/device | Baseline/artifact | Action | Evidence | Result |
|---|---|---|---|---|---|---|---|---|
| static | yes | 七文件及Go/runner接口 | 顺序/flags/wire/权限范围 | 主机只读 | 聚合ca04e90c | 完整回读/两独立审查 | 最终SPEC/不同QUALITY 0/0/0 | pass |
| unit | yes | 路径/API/wire/生成器/真实main夹具 | 正负控/异常/旧分支 | 主机软件 | 同冻结 | 定点/重复/DEFAULT/全仓 | SPEC51、QUALITY87、20轮1740、DEFAULT418均0skip；全仓2261含59既有skip无失败，3道通过 | pass（本片定点无skip） |
| build/host | yes | CMake→生成器→host query | 同mtime/旧头/失败/实际capture | POSIX synthetic PE/host ELF | 同冻结 | 实际j1构建及有界捕获 | QUALITY与20轮实际执行，非Windows二进制 | pass（宿主逻辑） |
| deploy | yes | MSVC/签名/安装wheel | x64/ARM64×Py3.11/3.12 | Windows CI实际OS/权限待记录 | 待本片新SHA | 构建签名安装 | 本片未提交，未运行；9ed结果不覆盖 | inconclusive |
| consumption | yes | 安装Go及实际四路径 | 正例/错误SHA负例/阻断导出 | 同四Windows格 | 待新SHA | 实际执行并读原始日志 | 未运行；fake receipt不授此层信用 | inconclusive |

### negative_evidence

9ed双Py3.12生成器失败阻断其后签名/安装，反驳四格已通过；两Py3.11成功仅覆盖旧C绑定。当前查询HANDLE在执行前关闭，且share7允许写删，不能证明生产锁或同对象启动。缺新SHA原生日志只构成未观察，不等于平台支持或不支持。

### gaps

完整preflight已通过，本片待提交推送；owner根代理，安全下一步为收尾非测试检查后精确main提交推送。四格安装/Go消费缺失；owner独立CI观察者与根代理，安全下一步仅回收新SHA原始日志/OS上下文，不回退原盘符或放松检查。缺新SHA原生证据阻止本片整体verified。UAC/held-HANDLE/标准用户/Win10/配额及R2/R3总门属于后续独立必需层，不能由此片关闭。

### verdict

`partially_verified`：只允许称上述冻结软件、主机构建逻辑和DEFAULT已通过；原生canary仍unverified，不称Windows已支持GLOBALROOT、Py3.12实际问题已解决或R2/R3完成。无已关闭工单状态变更。

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development (recommended) or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在既有签名安装CI中实际验证Go的四条GLOBALROOT路径兼容性，不增加产品启动权限。

**Architecture:** 固定安装包资源经元数据HANDLE查询NT卷路径，再关闭HANDLE并转换Win32 GLOBALROOT路径。复用既有有界runner执行原Go正负例，唯一CI消费者失败时不导出wheel；这不是资源锁、同对象启动或生产权限。

**Tech Stack:** Python3.11/3.12标准库ctypes、现有icode runner、既有随包Go1.27.1 verifier与Windows x64/ARM64 signed CI。

---

基线9ed0700；设计[固定卷canary](../specs/2026-10-09-windows-direct-volume-canary-design.md)SHA256 `20eaff207ee73a5bbbeff8a534cab3a171d2183f824e637fda74d694f3cc565f`。只读研究独立运行；用户已要求main自主继续，沿明确批准路线，不再创建远端开发分支。根代理保留文档唯一写权；实现者仅下述脚本/测试/DEFAULT接点，不能改vendor、Go/C、生产provenance或权限。源码未开始，本计划代码是实现参考，不是测试结果。

## 文件责任

- 新 `scripts/probe_windows_direct_volume.py`：CI-only固定资源探针，只有--source-sha。
- 新 `tests/test_windows_direct_volume.py`：portable class，对路径、fake Win32 API、有界原wire和错误进行软件验收。
- 改 `scripts/run_windows_wheel_ci.py`：signed+Go分支既有crypto negative后增加一次脚本调用。
- 改 `tests/test_windows_bootstrap_binding.py`：保留真实main/export夹具，新增顺序、失败及零调用。
- 改 `scripts/run_workspace_ci.py` 与 `tests/test_run_workspace_ci.py`：portable class选择一次，不包含native/平台skip。

### Task 1: 先建立真实软件RED

**状态**
- [ ] 任务完成

**Dependencies:** None
**Parallelizable:** No（共享源码唯一写者；不并行改配对消费者）

- [ ] 写新增portable class，先用接口断言失败而不是ImportError；路径函数名固定 `_nt_to_globalroot`。以下测试可原样用于初始RED及路径正例：

```python
import importlib.util
import unittest

class TestWindowsDirectVolume(unittest.TestCase):
    def _api(self):
        spec = importlib.util.find_spec("scripts.probe_windows_direct_volume")
        self.assertIsNotNone(spec, "direct-volume CI probe is missing")
        import scripts.probe_windows_direct_volume as api
        return api

    def test_exact_volume_prefix_and_unicode_are_preserved(self):
        api = self._api()
        for tail in ("native\\icode-provenance-windows-x64.exe", "用户\\🧪\\native"):
            source = "\\Device\\HarddiskVolume12\\" + tail
            self.assertEqual(api._nt_to_globalroot(source), "\\\\?\\GLOBALROOT" + source)

    def test_wrong_namespace_or_ambiguous_component_is_not_a_volume_path(self):
        api = self._api()
        for path in (
            "C:\\native\\a.exe", "\\Device\\HarddiskVolume\\a.exe",
            "\\Device\\HarddiskVolume１２\\a.exe", "\\Device\\Harddisk0\\a.exe",
            "\\Device\\HarddiskVolume1\\..\\a.exe", "\\Device\\HarddiskVolume1\\a:stream",
            "\\Device\\HarddiskVolume1\\a.\\b", "\\Device\\HarddiskVolume1\\a ",
            "\\Device\\HarddiskVolume1\\a\\\\b", "\\Device\\HarddiskVolume1\\a\x00",
        ):
            with self.subTest(path=path), self.assertRaises(ValueError):
                api._nt_to_globalroot(path)
```

- [ ] 正式Python运行 `python -m unittest tests.test_windows_direct_volume -v`，记录实际FAIL、0ERROR，旧源码不修改；不能将坏fixture/导入异常算RED。
- [ ] 在旧 `test_signed_install_order_and_failure_gates_preserve_no_go_proof_only` 的valid分支，要求stages包含 `installed verifier accepts direct-volume paths`，原9ed实际main应断言FAIL。新增 `direct_volume_failure` 模式，在该stage抛RuntimeError；后续GREEN必须rc1/export不存在。保留原七模式全部事实，不把新增测试存在本身当native。

### Task 2: 最小CI脚本实现与portable错误负控

**状态**
- [ ] 任务完成

**Dependencies:** Task 1
**Parallelizable:** No（先真实RED，再最小实现；native执行留CI）

- [ ] 下列完整参考实现定义全部接口；按现有风格用apply_patch新建脚本。若自审发现真实错误，先补针对RED再修，不能照抄未验证代码并宣称完成。

```python
"""CI compatibility canary; not a file lock or executable launch grant."""
from __future__ import annotations
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import sysconfig

_PATH_CAPACITY = 32768
_IMAGE_LIMIT = 64 * 1024 * 1024
_WIRE_LIMIT = 512
_TIMEOUT = 30

def _nt_to_globalroot(path: str) -> str:
    if type(path) is not str:
        raise ValueError("invalid_volume_path")
    match = re.fullmatch(r"\\Device\\HarddiskVolume[0-9]+\\(.+)", path, re.IGNORECASE)
    if match is None:
        raise ValueError("invalid_volume_path")
    for part in match.group(1).split("\\"):
        if (not part or part in (".", "..") or part.endswith((".", " "))
                or any(ord(char) < 32 or char in ':<>"|?*/' for char in part)):
            raise ValueError("invalid_volume_path")
    return "\\\\?\\GLOBALROOT" + path

def _kernel():
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
        ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.GetFinalPathNameByHandleW.argtypes = [wintypes.HANDLE,
        ctypes.POINTER(ctypes.c_wchar), wintypes.DWORD, wintypes.DWORD]
    kernel.GetFinalPathNameByHandleW.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    return kernel

def direct_volume_path(path: Path, *, directory: bool = False) -> str:
    if sys.platform != "win32" or type(directory) is not bool:
        raise ValueError("windows_probe_only")
    kernel = _kernel()
    flags = 0x02000000 if directory else 0
    handle = kernel.CreateFileW(str(path), 0x80, 7, None, 3, flags, None)
    if type(handle) is not int or handle in (0, -1, ctypes.c_void_p(-1).value):
        raise OSError("volume_path_open_failed")
    try:
        buffer = ctypes.create_unicode_buffer(_PATH_CAPACITY)
        length = kernel.GetFinalPathNameByHandleW(handle, buffer, len(buffer), 2)
        if type(length) is not int or not 0 < length < len(buffer):
            raise OSError("volume_path_query_failed")
        value = buffer.value
        if len(value.encode("utf-16-le", errors="strict")) // 2 != length:
            raise OSError("volume_path_query_incomplete")
        return _nt_to_globalroot(value)
    finally:
        if not kernel.CloseHandle(handle):
            raise OSError("volume_path_close_failed")

def _installed_resources():
    import icode
    from icode.native_helper import windows_arch_from_platform
    package = Path(icode.__file__).resolve().parent
    package.relative_to(Path(sysconfig.get_paths()["purelib"]).resolve())
    arch = windows_arch_from_platform(sysconfig.get_platform())
    native = package / "native"
    helper = native / f"icode-sandbox-windows-{arch}.exe"
    verifier = native / f"icode-provenance-windows-{arch}.exe"
    proof = Path(str(helper) + ".sigstore.json")
    return arch, native, helper, verifier, proof

def probe(source_sha: str) -> None:
    if sys.platform != "win32" or type(source_sha) is not str or re.fullmatch(r"[0-9a-f]{40}", source_sha) is None:
        raise ValueError("invalid_probe_input")
    from icode.runner import _run_unittest_with_bounded_output
    from icode.native_helper import windows_pe_architecture
    arch, native, helper, verifier, proof = _installed_resources()
    info = helper.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 < info.st_size <= _IMAGE_LIMIT:
        raise ValueError("invalid_installed_artifact")
    with helper.open("rb") as stream:
        image = stream.read(_IMAGE_LIMIT + 1)
    if len(image) != info.st_size or windows_pe_architecture(image) != arch:
        raise ValueError("invalid_installed_artifact")
    executable = direct_volume_path(verifier)
    artifact = direct_volume_path(helper)
    bundle = direct_volume_path(proof)
    cwd = Path(direct_volume_path(native, directory=True))
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR") if key in os.environ}
    argv = [executable, "--artifact", artifact, "--bundle", bundle,
            "--source-sha", source_sha, "--arch", arch]
    expected = dict(schema_version=1, provenance_verified=True, launch_authorized=False,
        artifact_sha256=hashlib.sha256(image).hexdigest(), source_sha=source_sha, architecture=arch)
    expected_wire = json.dumps(expected, separators=(",", ":")).encode("ascii") + b"\n"
    result = _run_unittest_with_bounded_output(argv, workspace=cwd, timeout=_TIMEOUT,
        output_limit_bytes=_WIRE_LIMIT, environment=env)
    if type(result) is not tuple or len(result) != 3 or type(result[0]) is not int or result[0] != 0 or type(result[1]) is not bytes or type(result[2]) is not bytes or result[1] != expected_wire or result[2] != b"":
        raise ValueError("direct_volume_positive_failed")
    wrong_source = "0" * 40 if source_sha != "0" * 40 else "1" * 40
    negative_argv = list(argv)
    negative_argv[6] = wrong_source
    result = _run_unittest_with_bounded_output(negative_argv, workspace=cwd, timeout=_TIMEOUT,
        output_limit_bytes=_WIRE_LIMIT, environment=env)
    if type(result) is not tuple or len(result) != 3 or type(result[0]) is not int or result[0] != 78 or type(result[1]) is not bytes or type(result[2]) is not bytes or result[1] != b"" or result[2] != b"icode_provenance: verification_failed\n":
        raise ValueError("direct_volume_negative_failed")

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args()
    try:
        probe(args.source_sha)
    except (ImportError, OSError, UnicodeError, ValueError, RuntimeError, subprocess.SubprocessError):
        print("::error::windows_direct_volume_probe_failed")
        return 1
    print("windows-direct-volume compatibility=PASS launch_authorized=false")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] 加配对软件负控：fake kernel各API为callable mock，query通过修改buffer并返回UTF16 code-unit长度；assert目录flags/访问0x80/share7/open3、关闭顺序与次数。Query返回0/32768/超上限/bool、内容不完整/非法namespace或close失败时均无PASS；open失败不close未知句柄。补32位INVALID_HANDLE_VALUE与0/None/bool。
- [ ] `probe` mock安装资源与真实临时PE，不执行synthetic；fake路径converter记录四次及directory=True。Patch `icode.runner._run_unittest_with_bounded_output` 返回canonical receipt与旧78负例，assert精确argv/cwd/30sec/512bytes/窄env；负SHA必须改argv索引6，不能误改--source-sha token。加入六字段bool/int混淆、duplicate/extra/trailing/非法UTF8、错误返回类型、非零/stdout/stderr负控、timeout/limit/capture异常。
- [ ] 正文参考使用canonical Go JSON字节比较，更严格拒绝重复/额外/类型别名；这不改Go wire。验证 `subprocess.TimeoutExpired` 经main的 `subprocess.SubprocessError` 捕获走固定失败；不得吞KeyboardInterrupt/SystemExit或程序性异常。
- [ ] 运行portable class全部GREEN，记录无skip与host mocks边界；实际Win32/Go尚未运行不授信用。

### Task 3: 接入唯一CI消费者与DEFAULT

**状态**
- [ ] 任务完成

**Dependencies:** Task 2
**Parallelizable:** No（消费必须在已验证分支，先单点TDD后配对同步）

- [ ] 在 `scripts/run_windows_wheel_ci.py` 既有 `installed verifier rejects actual cryptographic negative controls` 调用之后、退出真实Go分支之前加入：

```python
_run("installed verifier accepts direct-volume paths",
     [str(python), "-I", str(_REPOSITORY / "scripts" / "probe_windows_direct_volume.py"),
      "--source-sha", env["GITHUB_SHA"]], cwd=root, env=clean_env)
```

- [ ] 更新Task1真实main夹具，valid顺序包含gh→binding→Go正例→既有negative→新canary→v1；新stageRuntimeError rc1且无export，gh/binding/Go故障零canary，unsigned/proof-only零canary。
- [ ] DEFAULT_MODULES加入且仅一次 `"tests.test_windows_direct_volume.TestWindowsDirectVolume"`，配对CI选择测试：

```python
self.assertEqual(DEFAULT_MODULES.count("tests.test_windows_direct_volume.TestWindowsDirectVolume"), 1)
self.assertNotIn("tests.test_windows_direct_volume", DEFAULT_MODULES)
```

- [ ] 本机定点运行新class、原bootstrap binding portable、旧wheel packaging、run_workspace_ci选择、workflow contracts、既有provenance adapter。保留原v1/78和无Go分支，不修改workflow权限、MANIFEST、native二进制或vendor。

### Task 4: 自审、冻结与阶段验收

**状态**
- [ ] 任务完成

**Dependencies:** Task 3
**Parallelizable:** No（只读研究与CI观察可并行，验收必须针对冻结源）

- [ ] 实现者进行SPEC和QUALITY两轮自审；报精确变更文件、SHA256、真实RED/GREEN计数/skip/时间、错误及未运行层后STOP，不commit/push、不触碰根文档。
- [ ] 根代理完整回读后独立SPEC→不同QUALITY；冻结一致才跑20轮、DEFAULT、全仓 `python scripts/preflight.py` 三道、compileall-j1、治理/官网/竞品/diff。使用既有正式Python与验证Go，CMAKE_BUILD_PARALLEL_LEVEL=1，GOMAXPROCS=1、GOFLAGS=-p=1。源码变更重启针对性审查与阶段守护，不隐藏失败或旧skip。
- [ ] 全门通过再git add精确允许文件/根文档、cached diff check、main commit/push，refs和官方connector核精确SHA。新SHA四signed实际原日志独立观察；缺格不报告canary完整验收。旧9ed观察不被取消/当成新SHA信用，若仍运行不要无意义文档push。
- [ ] 在路线图/持续竞品与设计分层矩阵记实际正负例/上下文/OS版本；不把管理员CI说成标准用户、Windows hosted说成Win10或本片说成held-HANDLE。同对象消费下一设计仍需alias漂移负控与实际HANDLE identity闭环，不开放R2/R3。

---
**Execution Mode:** serial

用户已明确要求直接main连续开发，覆盖技能默认worktree/分支与阶段等命令约定；保持唯一源码写者、独立只读研究和双审。若平台线程上限拒绝新实现agent，复用已STOP代理但发送完整新上下文，并明确该降级，不假称fresh agent。
