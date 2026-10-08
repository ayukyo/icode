# Windows PE 样本采集 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development to implement this plan task-by-task. Steps use checkbox tracking.

**Goal:** 在签名前有界采集固定最终C的实际imports/manifest样本，绑定原字节摘要，保持所有生产授权false。

**Architecture:** CI-only脚本调用既有context probe与binary bounded runner，只选实际根下各一个dumpbin/mt候选；不执行目标PE。采集和安全解析分开；缺件、变化、输出/清理异常阻断签名，普通安装不变。

**Tech Stack:** Python3.11/3.12标准库、现有PE machine API及WindowsJob监督、当前VS/SDK工具。无新runtime依赖。

---

基线 main3ef；[设计](../specs/2026-10-09-windows-pe-capture-design.md) 前版 SHA256 `82a169277f4b4de9c768e822e218abdb327a854cda3c67a727d26d6ea0472373` 曾经独立SPEC→不同QUALITY均0/0/0。2026-10-09 并行研究发现 DUMPBIN 默认 PDB 搜索，修订为 `/nopdb /imports` 并去掉其 `/nologo`；仅有种子和最小 stub 时暂停 Task 2，修订待双审，旧冻结不授权新 argv 实现。用户已授权主阶段自主设计、实现及合格后main提交推送，并明确只保留main；覆盖技能默认工作树/分支/逐步等待选择，不扩大任何权限、安装、KEY或SKILL修改范围。root唯一文档写者，每Task一名新鲜实现者，禁止并行写源码；研究/审查只读独立。编译保守1，任何编译不超过6。

修订双审已结束：独立增量 SPEC 与不同新鲜 QUALITY 均 Critical0 / Important0 / Minor0，实读同一 SHA256 `b994521314f07b51417126cbc9d07101d867eaff4fc67b46017159f1a9fd35d4`；此版为当前冻结设计，覆盖上段“待双审”的历史状态。Task2 可恢复，对精确新 argv 先行为 RED→GREEN；当前仅有接口 stub，不伪造旧 argv 实现的回归失败。

文件责任：新增 `scripts/probe_windows_pe_capture.py`（CI采集）与 `tests/test_windows_pe_capture.py`（portable/host边界）；仅修改 `.github/workflows/windows-helper-provenance.yml`、`scripts/run_workspace_ci.py`、`tests/test_run_workspace_ci.py`、`tests/test_windows_bootstrap.py` 的配对接点。原context脚本/native_helper/CMake/C/Go/vendor/MANIFEST/产品API/权限/其余workflow不改。root当前两份验收docs WIP保留，不由实现者操作git。

## Task 1：先固定缺失接口的真实 RED

**状态**
- [x] 任务完成（只完成RED种子，不是实现）

**Dependencies:** None
**Parallelizable:** No（唯一测试写者，后续依赖此RED）

- [x] 完读设计及现ctx probe/PE helper边界。只新建测试文件，seed如下，不建脚本、不写skip或expectedFailure：

```python
import importlib.util
import unittest

class TestWindowsPeCapture(unittest.TestCase):
    def test_capture_interface_exists(self):
        found = importlib.util.find_spec("scripts.probe_windows_pe_capture")
        self.assertIsNotNone(found, "CI PE capture implementation is required")
        if found is not None:
            module = __import__("scripts.probe_windows_pe_capture", fromlist=["capture"])
            self.assertTrue(callable(getattr(module, "capture", None)))
```

- [x] 运行 `PYTHONPATH=src:. python -B -m unittest tests.test_windows_pe_capture.TestWindowsPeCapture -v`。实际1个明确AssertionError/0ERROR/0SKIP；root另跑相同1FAIL（0.000秒），没有ModuleNotFoundError/非法fixture。
- [x] 实现者内置SPEC自审（符合只RED约束）→QUALITY自审、diffcheck均通过并STOP，不commit/push，不修改任何doc。seed11行，SHA256 `5039343ceee5e0d4c9cb9cca60e812582f5a7f9bf64443202e5085aea0ddb654`；源码仍未创建。此时仅Task1 RED阶段完成，不是采集功能通过。

## Task 2：有界采集器与portable/host合同

**状态**
- [x] 任务完成（采集器软件合同，未接CI或授原生信用）

最终实现者两轮内置自审无未修问题，root 完读两源码及依赖并另跑正确新旧组合：90 PASS / 0 FAIL / 0 ERROR / 0 SKIP，7.749秒，含新模块24（portable23 + HostCLI1）与旧模块66。TDD原组六次累计不是独立method计数：精确参数2、context49、三对象6、runner/manifest27、字节/后读7、canonical/CLI15个AssertionFAIL，各0ERROR/0SKIP，逐组GREEN；保留上述错误模块名首次2loaderERROR。

root另发现HostCLI原无条件要求Linux：父宿主darwin/win32软件模拟分别1个AssertionFAIL/0ERROR/0SKIP。原作者新增结构回归真实2FAIL→GREEN，泛化为空owned buildroot的固定CLI失败，不加skip、不弱化rc/stdout/stderr、不改生产脚本。父宿主/子进程模拟只算兼容合同，真实CLI只在本机Linux运行，不能计Mac/Windows原生。源码SHA `6bca66405942b036e39713c43d020171301b7a5d6ed63c74d359c0f436f980f5`，测试最终SHA `611a9d49e663262c42e9ae99a9587b1beee4c52e881fe1e85cd8e4ce0656164f`；旧测试SHA `d2a8c2430f790cec2ee550e3f1a38b88cca8349aad1569d6f10721b336169862` 留作历史，不再沿用其自审结论。实现者compileall-j1与diffcheck通过；全局双审/20/DEFAULT/full须六文件冻结后另跑。

**Dependencies:** Task 1
**Parallelizable:** No（新增两文件唯一写者，不接CI）

- [x] 保留种子，先补行为失败测试：两架构已选根/精确argv（DUMPBIN 必须 `/nopdb /imports` 且无 `/nologo`，mt 保留 `-nologo`）/最小环境、原bytes与无损base64、三个false字段、完整九字段context、固定目标和零目标执行。使用合成machine PE、Windows逻辑工具路径mock，私有临时目录/target/manifest用owned真实fixture；不创建真实系统目录、非法Windows文件名或依赖symlink权限。最小环境尚无原生可运行信用，任何失败不自动继承额外变量。
- [x] 新脚本参考完整核心如下。内部允许等价分解，常量/API/返回字段及冻结设计不变；代码在测试RED后才落源码。`_read_regular`、`probe`、`windows_pe_architecture`、`windows_arch_from_platform` 是现存API，先完整阅读。

```python
"""Capture public CI PE inspection bytes without product execution authority."""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import subprocess
import sys
import sysconfig
import tempfile
import xml.etree.ElementTree as ET

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "src"))
from icode.native_helper import windows_arch_from_platform, windows_pe_architecture
from icode.runner import _run_unittest_with_bounded_output
from scripts.probe_windows_build_context import _read_regular, probe as _probe_context

_IMAGE_LIMIT = 8 * 1024 * 1024
_OUTPUT_LIMIT = 16384
_MANIFEST_LIMIT = 4096
_RECEIPT_LIMIT = 32768
_CONTEXT_KEYS = {"schema_version", "architecture", "generator", "toolset", "sdk_version",
                 "msbuild", "VCToolsInstallDir", "WindowsSdkDir", "MSBuildToolsPath"}

def _image_digest(path: Path, architecture: str) -> str:
    raw = _read_regular(path, _IMAGE_LIMIT)
    if windows_pe_architecture(raw) != architecture:
        raise ValueError("image machine mismatch")
    return hashlib.sha256(raw).hexdigest()

def _invoke(argv: list[str], directory: Path, environment: dict[str, str],
            *, require_stdout: bool) -> bytes:
    result = _run_unittest_with_bounded_output(
        argv, workspace=directory, timeout=30, output_limit_bytes=_OUTPUT_LIMIT,
        environment=environment,
    )
    if type(result) is not tuple or len(result) != 3:
        raise RuntimeError("runner shape")
    code, stdout, stderr = result
    if (type(code) is not int or code != 0 or type(stdout) is not bytes
            or type(stderr) is not bytes or stderr
            or len(stdout) + len(stderr) > _OUTPUT_LIMIT
            or (require_stdout and not stdout)):
        raise RuntimeError("inspection failed")
    return stdout

def _encode(receipt: dict) -> str:
    text = json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    if len(text.encode("ascii")) > _RECEIPT_LIMIT:
        raise ValueError("receipt budget")
    return text

def capture(build_directory: Path, architecture: str) -> dict:
    if (sys.platform != "win32" or architecture not in ("x64", "arm64")
            or windows_arch_from_platform(sysconfig.get_platform()) != architecture):
        raise ValueError("platform mismatch")
    context = _probe_context(build_directory, architecture)
    if (type(context) is not dict or set(context) != _CONTEXT_KEYS
            or type(context["schema_version"]) is not int or context["schema_version"] != 1
            or context["architecture"] != architecture
            or any(type(context[k]) is not str or not context[k]
                   for k in _CONTEXT_KEYS - {"schema_version"})):
        raise ValueError("context shape")
    sdk = context["sdk_version"]
    if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+", sdk) is None:
        raise ValueError("sdk path component")
    for key in ("VCToolsInstallDir", "WindowsSdkDir"):
        if not PureWindowsPath(context[key]).is_absolute():
            raise ValueError("tool root")
    host = "Hostx64" if architecture == "x64" else "Hostarm64"
    dumpbin = Path(str(PureWindowsPath(context["VCToolsInstallDir"])
                       / "bin" / host / architecture / "dumpbin.exe"))
    mt = Path(str(PureWindowsPath(context["WindowsSdkDir"])
                  / "bin" / sdk / architecture / "mt.exe"))
    helper = build_directory / "Release" / f"icode-sandbox-windows-{architecture}.exe"
    paths = (helper, dumpbin, mt)
    before = tuple(_image_digest(p, architecture) for p in paths)
    system = {name: os.environ.get(name, "") for name in ("SystemRoot", "WINDIR")}
    if any(not value for value in system.values()):
        raise ValueError("missing system root")
    with tempfile.TemporaryDirectory(prefix="icode-pe-capture-", dir=build_directory) as temp:
        directory = Path(temp)
        environment = {**system, "TEMP": str(directory), "TMP": str(directory)}
        imports = _invoke([str(dumpbin), "/nopdb", "/imports", str(helper)],
                          directory, environment, require_stdout=True)
        output = directory / "manifest.xml"
        try:
            output.lstat()
        except FileNotFoundError:
            pass
        else:
            raise ValueError("preexisting output")
        _invoke([str(mt), "-nologo", "-inputresource:" + str(helper) + ";#1",
                 "-out:" + str(output)], directory, environment, require_stdout=False)
        manifest = _read_regular(output, _MANIFEST_LIMIT)
    # CI TCB only: same bytes before/after is not a HANDLE/ancestor lock.
    if tuple(_image_digest(p, architecture) for p in paths) != before:
        raise RuntimeError("inspected bytes changed")
    receipt = {"schema_version": 1, "architecture": architecture, "build_context": context,
               "helper_sha256": before[0],
               "dumpbin": {"path": str(dumpbin), "sha256": before[1]},
               "mt": {"path": str(mt), "sha256": before[2]},
               "dumpbin_stdout_base64": base64.b64encode(imports).decode("ascii"),
               "manifest_base64": base64.b64encode(manifest).decode("ascii"),
               "parse_complete": False, "runtime_load_verified": False,
               "source_launch_verified": False}
    _encode(receipt)
    return receipt

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--build-directory", required=True, type=Path)
    parser.add_argument("--architecture", required=True, choices=("x64", "arm64"))
    args = parser.parse_args()
    try:
        receipt = capture(args.build_directory, args.architecture)
        encoded = _encode(receipt)
    except (OSError, UnicodeError, ValueError, RuntimeError, ET.ParseError,
            subprocess.SubprocessError):
        print("::error::windows_pe_capture_probe_failed")
        return 1
    print("windows-pe-capture status=CAPTURED production_authority=none")
    print("windows-pe-capture receipt=" + encoded)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

- [x] 正控测试用完整owned fixture，每次fresh context dict。mock `_probe_context` 返回设计九字段、sys.platform=win32及sysconfig win_amd64/win_arm64。工具逻辑路径不要在真实文件系统创建，patch `_read_regular` 仅映射两候选合成PE，其余target/manifest走原函数。synthetic PE可由以下定义生成，不能称真实dumpbin/mt/加载验收：

```python
import struct
def pe_image(architecture):
    image = bytearray(128)
    image[:2] = b"MZ"
    struct.pack_into("<I", image, 0x3c, 64)
    image[64:68] = b"PE\0\0"
    struct.pack_into("<H", image, 68, {"x64": 0x8664, "arm64": 0xaa64}[architecture])
    return bytes(image)
```

- [x] runner positive side-effect 收集 argv/kwargs；dumpbin 返回 `(0,b"\x80raw imports\r\n",b"")`，mt 从固定 `-out:` argv解析本次owned Path 并写 `b"\xffraw manifest"`，返回 `(0,b"",b"")`。断言base64.decode还原，不宣称报告可解析；helper不是argv[0]，两次workspace相同私有目录、env键只有四个、输出起初不存在、返回后目录已移除。支持两架构，并核 `capture` 返回字段闭集及所有三个false。
- [x] 每个异常族先加失败测试再修实现，预期抛固定类型、零后续调用/无成功CLI标记：
  - platform/architecture/python target 不匹配、SDK穿越、错schema bool/float/缺/extra/context arch；relative tool roots与缺系统根。
  - 三对象各缺/非regular/S_IFLNK元数据/0/超8MiB/错machine，保证工具未调用；不依赖真实链接权限。
  - runner None/list/tuple错长度、code bool/非0、stdout/stderr非bytes、非空stderr、空dumpbin、合计超16384；dumpbin失败零mt，mt失败无receipt。
  - mt未写/空/非regular/S_IFLNK元数据/超4096、dumpbin提前造旧manifest；拒绝旧文件和截断读取。
  - 目标及两工具逐件调用后同尺寸换bytes；新目标/原文件读异常、runner异常、context异常、owned cleanup异常；全部不得成功，KI/SystemExit透传。
  - canonical ASCII JSON、raw字节无损、总JSON超32768在标记前拒绝、错误不含模拟秘密/raw异常；参数未知/缩写rc2。主机非Windows CLI固定失败不运行native，Host-only CLI class不进DEFAULT。
- [x] 运行 `PYTHONPATH=src:. python -B -m unittest tests.test_windows_pe_capture -v` 与当前实际旧模块 `tests.test_windows_build_context tests.test_windows_bootstrap_binding tests.test_windows_direct_volume`，记录真实RED/GREEN/skip。计划原先写错后两模块名（`test_windows_build_binding` / `test_windows_direct_volume_canary`），实现者首次实际运行26 attempted、2 loaderERROR；保留该命名偏差结果，不算实现回归已通过，必须以正确模块重跑。不得删除或弱化旧assertions以制造GREEN。
- [x] 内置SPEC逐条→QUALITY逐条、diffcheck，回报两源码SHA与实际测试计数/限制、STOP。根全读两文件并独立定点复验后才允许Task3。

## Task 3：签名前门与DEFAULT配对接线

**状态**
- [x] 任务完成（接线软件合同，未有新SHA原生采样）

新鲜唯一四文件作者先实际2AssertionFAIL/0ERROR/0SKIP，再指定组合54PASS/0SKIP；内置SPEC→QUALITY无未修问题（不替独立评审），compileall-j1三Python/diffcheck通过。diff仅workflow2行、DEFAULT1项、paired两测试55行，旧断言/权限/action/matrix保持。root已完整阅读四文件当前内容和diff，另跑两新源＋三旧模块＋两paired模块：121 PASS / 0 FAIL / 0 ERROR / 0 SKIP，8.089秒；不是20轮或完整preflight。

**Dependencies:** Task 2
**Parallelizable:** No（唯一四接线文件写者，不碰两新文件/设计/docs）

- [x] 全读四允许文件。先在 `TestWindowsBootstrap` 增 `test_pe_capture_runs_after_context_before_attestation`，在 `TestWorkspaceCiCoverage` 增 `test_pe_capture_portable_contract_is_selected_once`，断言新脚本命令缺失与DEFAULT缺失是真实AssertionError RED，不用fixture错误。
- [x] sign旧context CLI及rc gate后仅追加以下两行，旧构建/默认OFF/权限/matrix/action SHA/安装/export全部保持：

```powershell
python scripts/probe_windows_pe_capture.py --build-directory $buildDirectory --architecture '${{ matrix.helper-architecture }}'
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

- [x] DEFAULT只增加 `"tests.test_windows_pe_capture.TestWindowsPeCapture"` 恰好一次，不能整模块或Host-only class。paired选择测试用unittest.loadTestsFromName实际遍历methods确认存在、无class/method skip；workflow测试同时核finalbuild→旧ctx/rc→新capture/rc→attest→install/upload及只有main sign写权，采集命令固定参数且不执行helper。旧paired断言不删。
- [x] 运行 `PYTHONPATH=src:. python -B -m unittest tests.test_run_workspace_ci tests.test_windows_bootstrap tests.test_windows_pe_capture.TestWindowsPeCapture -v`，记录从RED到GREEN无新skip。实现者内置SPEC→QUALITY、diffcheck及四文件SHA，STOP，不commit/push。根全读四文件diff及独立复验。

## Task 4：冻结、全局双审、交付与四格原生采样

**状态**
- [x] 任务完成（仅可信CI样本采集子门）

**Dependencies:** Task 3
**Parallelizable:** No（冻结后测试串行；只读研究/观察独立）

六源码已停止写入，按下列顺序执行 `sha256sum` 的输出再 `sha256sum`，aggregate为 `923e226fd83c71db37bd23c403837b2024a6519fd8d0e9f1a71e147514b74da2`。开始新鲜独立GLOBAL SPEC，之后需不同GLOBAL QUALITY；未获双审批准，不开20/DEFAULT/full或commit。

全局源码双审现已结束（覆盖上段“开始审查”的历史状态）：新鲜SPEC Critical0/Important0/Minor0、独立121PASS/0skip7.958秒；不同新鲜QUALITY亦0/0/0、独立121PASS/0skip7.887秒，另实际loader确认portable23/Host0/ID无重复。两审均完整读六文件及真实调用链，审前后设计/源码/aggregate完全相同。允许root依次开始20→DEFAULT→full；本片原生门及生产/R2R3门仍未关闭。

root20轮已完成并退出：每轮实际121PASS/0skip，共2420PASS、0FAIL/ERROR/SKIP，wall161.087秒；源码aggregate仍923e226。确认退出后才启动DEFAULT，尚不填完整软件门PASS。并行研究现已结束，结果记为[下一片R3验证工厂的设计输入](../specs/2026-10-09-r3-workbench-verification-research.md)，不在本片接线该工厂或授执行就绪。

DEFAULT也已完成并退出：461 PASS / 0 FAIL / 0 ERROR / 0 SKIP，164.259秒。确认退出后才启动完整三道preflight；root只加只读诊断包装，保留原 `guard_tests` 的解释器/argv/cwd/捕获与返回码，用实际子进程完成输出记录总数，不改变测试选择或例外。

完整preflight已实际退出0，三道全部通过：2313 total / 2254 PASS / 59既有平台环境SKIP / 0 FAIL / 0 ERROR，unittest475.779秒，子进程wall475.995秒；没有新增skip。随后compileall-j1全src/scripts/tests、治理、站点、对照排期、diffcheck均退出0；源码aggregate仍923e226，固定vendor1693651c无改动。软件门已关闭，下一步仅按已授权main提交推送，再另验真实四格。

发布记录（2026-10-09，覆盖上一段待提交状态）：main 已提交并推送 `ccbe67bb65d5246a61fb3078b85c83fba5aa7c42`。root 核对精确12个暂存路径、六个 Git index blob 摘要与冻结值、父提交3ef及cached diff；普通add的忽略docs提示退出1未被忽略，随后仅对六个必要文档逐个force-add并重新核对。推送后独立remote refs与GitHub官方main均为ccbe67，工作树干净；没有release/PyPI发布或vendor改动。

新SHA CI `37840482757`、Windows helper provenance `37840482713` 已启动，四格原生采样仍待决定性日志，不沿用3ef信用。官网 `37840482735` 已终态success：独立观察者核validate checkout、artifact `11577352344`，root另读deploy job `113528355740`，实际payload的artifact_id与pages_build_version精确绑定ccbe67，日志`Reported success!`。该部署证明网站发布，不证明Windows采样或生产安全。

原生收尾（覆盖上段待验状态）：来源[run37840482713](https://github.com/ayukyo/icode/actions/runs/37840482713)现completed/success，validate及四签名格全部success。独立只读观察者逐组回读decoded日志，root另逐组取同日志，核闭集11字段/完整九context/三个false，旧context→CAPTURED→实际attestation时间顺序、目标SHA与attestation行相等，以及每格后续19项安装PASS。正式artifact API共4个，都精确绑定ccbe67且未过期；未下载二进制或把zip大小当PE长度。三个新run均终态并STOP，不再轮询。

| 原生格 | Job | 实际OS/image/Python | CAPTURED UTC→attestation UTC | Proof | Artifact | 安装 |
|---|---|---|---|---|---|---|
| x64/3.11 | 113532978872 | Server2025/10.0.26100/windows-2025-vs2026 20260925.250.1/3.11.9 | 20:48:42→20:48:44 | 54094233 | 11577484265 | 19PASS |
| x64/3.12 | 113532978926 | 同Server2025/image/3.12.10 | 20:49:19→20:49:21 | 54094459 | 11577544108 | 19PASS |
| ARM64/3.11 | 113532978949 | Win11/10.0.26200/windows-11-vs2026-arm64 20261004.176.1/3.11.9 | 20:51:55→20:51:57 | 54095206 | 11577813392 | 19PASS |
| ARM64/3.12 | 113532978910 | 同Win11ARM/image/3.12.10 | 20:49:37→20:49:39 | 54094547 | 11578581430 | 19PASS |

四格context共同VS18 2026/v145、SDK10.0.26100.0、VCTools14.51.36231；实际VC根`C:\Program Files\Microsoft Visual Studio\18\Enterprise\VC\Tools\MSVC\14.51.36231\`，SDK根`C:\Program Files (x86)\Windows Kits\10\`，MSBuild及其ToolsPath分别amd64/arm64。所选dumpbin后缀`bin\Hostx64\x64\dumpbin.exe`或`bin\Hostarm64\arm64\dumpbin.exe`，mt后缀`bin\10.0.26100.0\x64\mt.exe`或arm64；这次四键最小env实际可运行，无回退/扩env，不外推其它版本与Win10。

| 对象 | 本窗口实际SHA256 |
|---|---|
| x64 dumpbin | 357c989e1c926841df4e6e97c25a60b205b30110cd6db39bde8d81a627e48ebb |
| ARM64 dumpbin | c31a8583ff860b2a0d6eada1cd037c5b7003ed122301a5ad0594265ad088a862 |
| x64 mt | fb1ab75294b78619bd6ac8cadf30cb95befbc7324703cbe2654ef800ddd2bf4d |
| ARM64 mt | c3b01462a70c83fc9a1fedb8acebbbf1949540a8b9f02e099bbbcc4f8b80eb21 |
| x64 3.11目标C | 5247bf9f6dfccba1e6fd8a552e76214844aae4a4a03a4f3a269e3f18406dd3d7 |
| x64 3.12目标C | 8f4a98b64b4cfd910ae59d30878e4c18e4c7a1dc66dada7f136fdae83f44a3e3 |
| ARM64 3.11目标C | 118c27d64ccd33c3875a7b3928ebf57a7b7d37d87ba4e5955c31f1eb2373c091 |
| ARM64 3.12目标C | 6dfd7f0320a2cfba50e78ce9aff8d95afc9d67109f221a598a47e8de4979b961 |

root另以strict base64解码/重编码及hashlib核原样字节：x64两格imports各3924B，SHA `2a0ed9d19149eadad7d572e417fcb381141a539b391cb7e32da7c5c3ce0c403e`；ARM两格各3771B，SHA `8fd9cd2aadfa72cd1dd6ecf21418ee4563e98bdf9d202257dbc4153ec7116bf4`。manifest四格相同406B、SHA `be8918559280a2e74748bf8f6238b568ed7cbf75183b2180a6a8a979a1ebf243`；实际前缀UTF8 BOM，strict utf-8-sig解码观察为asInvoker/uiAccess=false XML。三格逐bytes解码，最后ARM3.11完整base64与已解码ARM3.12逐字相等；无截断。receipt x646946B/ARM6752B。imports本窗口实际ASCII/英文、Version14.51.36260.0，报告见KERNEL32.dll及LoadLibraryExW/GetProcAddress；这只是观察，不是语言/whole-output/动态依赖完整性合同。源工具及目标前后bytes预算检查通过的receipt不提供各PE精确长度，不能编造长度。

同SHA[主CI37840482757](https://github.com/ayukyo/icode/actions/runs/37840482757)终态failure：44jobs=36success/4failure/3skip/1cancelled。两Linux全量2313 total/71skip/0F/E，3.11 617.326秒、3.12 439.276秒。Windows两workspace各455 total/F1/E1/20skip：x64新ERROR为baseline windows_directory_changed，ARM对应ERROR为inspection Git10093；两格legacy code FAIL为Git10038。两Reviewer gate/observer ready但IPv6 evidence_unavailable、no_matching_event/archive_member_missing；独立cap正控exit91 ipv4_connect且canary=false，不能给网络拒绝信用。Ubuntu22原生job在apt阶段cancelled，后续未运行，日志不说明取消主体或原因。新快照研究[另记](../specs/2026-10-09-windows-directory-change-research.md)，不将新ERROR叫旧Git或flaky。主CI失败不反驳本片四格样本已取得，但明确阻断R2/R3整体。

| 源码 | SHA256 |
|---|---|
| scripts/probe_windows_pe_capture.py | 6bca66405942b036e39713c43d020171301b7a5d6ed63c74d359c0f436f980f5 |
| tests/test_windows_pe_capture.py | 611a9d49e663262c42e9ae99a9587b1beee4c52e881fe1e85cd8e4ce0656164f |
| .github/workflows/windows-helper-provenance.yml | 2253f957b321ab497a2b007e265df7a32083ef8562d9cf07081c3832b1522fe4 |
| scripts/run_workspace_ci.py | e6727c55205f36e9f97de4cc6fefd4b9493c41cb905318449699655fc845f02e |
| tests/test_run_workspace_ci.py | bbc2fb800d6016d0ef97fe6a41e0d972cfa0bbd55578451e1a1c41eefeb659ca |
| tests/test_windows_bootstrap.py | 5fb3029b434819b8cc4dfb7b30c6a7a80d0b24ddaf7c295c7f12a0b0bdbb1d9d |

- [x] root冻结六源码各SHA与aggregate，源码不再写；独立新鲜GLOBAL SPEC→不同GLOBAL QUALITY全读源码与设计/当前依赖，任何整改先RED/GREEN再冻结、重新两审。Task自审不替全局审。
- [x] root定点组合新portable/paired/旧context/binding/direct-volume实际通过后，20轮同组合、零FAIL/ERROR/新增SKIP。全部退出再跑DEFAULT，DEFAULT退出再完整preflight，禁止重叠以免资源抖动。过程PATH仅明确Python/Go，GOMAXPROCS1、GOFLAGS=-p=1、GOTOOLCHAIN=local、CMAKE_BUILD_PARALLEL_LEVEL1；不猜计数。
- [x] `python -B -m compileall -q -j 1 src scripts tests`、`python -B scripts/check_governance.py`、`python -B scripts/check_site.py`、`python -B scripts/check_agent_landscape.py`、`git diff --check`、preflight密钥/子模块门均通过。CODEX附带KEY仍仓外、禁止打印/提交；模型API检查不混入本片样本。
- [x] root更新五字段分层证据及研究采纳记录、七维自检；只stage六源文件及必要精确docs（忽略docs逐个force-add），核cached父SHA/列表/diff/hash。完整守护后main commit/push ccbe67，独立查remote refs及官方main一致；无release/PyPI，无旧run取消。3ef三个run已STOP。
- [x] 新SHA四格只读独立观察，实际报告platform/image/Python/context、dumpbin/mt存在及执行返回、完整base64样本/摘要、CAPTURED与三个false、attest前顺序、四proof和19项安装PASS。root另读决定性日志/解码完整bytes；没有回退或扩环境。public fixed C报告限定PE introspection，无KEY/模型或用户工程输入；报告本身可逆，不称脱敏。
- [x] 本片只关闭“可信CI样本已采集”；下一完整解析及真实加载负控按实际样本另设计。R2/R3/Win10/标准用户/UAC/DPAPI/配额/工作台provider/真实六步都不关闭。

## acceptance_contract

| Expected behavior | Required layers | Consumers | Scenarios | Environment/device | Baseline | Pass criteria |
|---|---|---|---|---|---|---|
| 固定目标与工具原bytes有界采集、失败停签、普通安装不变 | static/unit/host/native CI consumption | sign工作流、DEFAULT portable | 两架构正控/负控，旧ctx、纯包兼容 | 主机mock/新SHA四hosted Windows格 | main3ef及设计b994521 | 双审/20轮/完整守护、四格完整samples及签名安装；CAPTURED不等安全PASS |

## verification_matrix

| Layer | Required | Consumer | Scenario | Environment/device | Baseline/artifact | Action | Evidence | Result |
|---|---|---|---|---|---|---|---|---|
| static | yes | 六文件调用链 | 设计/权限/旧兼容 | 当前源码 | 设计b994521/main3ef/源码923e226 | 独立设计与源码SPEC→不同QUALITY | 两源码审各0问题/121PASS0skip，根六文件全读 | verified（仅冻结软件合同） |
| unit/host | yes | 采集器/DEFAULT | 合成正负/CLI/预算 | 本机与portable | 源码923e226 | RED/GREEN，根新旧+paired复验、20/default/full、其它守护 | 定点121、20轮2420、DEFAULT461均PASS/0skip；full2313/59既有skip/0失败、三道通过，软件模拟不授原生 | verified（仅软件层） |
| native consumption | yes | sign | 真实工具→samples→attest→安装 | Server2025 x64/Win11ARM，两Python实际版本 | main ccbe67/run37840482713 | 独立decoded、root逐组回读/原bytes复核 | 四CAPTURED/3false/完整samples/绑定摘要/attest前/各19安装PASS | verified（仅可信CI样本子门） |

## negative_evidence

官方未保证工具人读文本编码或稳定标题；现有PE API仍没有导入/资源解析。新ccbe四格已提供候选及完整样本证据，覆盖旧无存在性/运行证据状态；实际ASCII/BOM观察不构成所有语言/PE/资源解析合同。CAPTURED不反驳 pre-main 搜索风险或证明动态/传递依赖来源。

## gaps

root/独立观察者：本片软件门、main提交推送与新SHA四格样本/签名安装均已核实。本片没有剩余采集缺口；完整解析、其它resource/language、真实加载/首UAC/Win10/标准用户/生产与R2/R3各独立门保留。主CI失败另列，不可抹去。

## verdict

`verified`（仅可信CI样本采集）：冻结设计/实现、独立全局双审、根定点121、20轮、DEFAULT/全仓守护、main提交推送、新SHA四格原生采集/签名及各19安装均通过。本片已完成，不报告生产安全、Windows普通用户或R2/R3完成；新主CI仍有失败与取消。

## 架构级自检报告（仅本片软件范围）

- ✅ 语法/编译：全源码compileall-j1、定点真实C/CMake编译及完整测试通过。
- ✅ 依赖/调用链：复用context/regular/PE/bounded runner，采集失败停签，DEFAULT实际loader及paired合同完整。
- ✅ 逻辑/边界：两架构候选、严格类型/限额/原bytes变化/闭集JSON，通过独立双审、20轮及完整回归。
- ✅ 异常处理：列举expected错误固定输出，cleanup失败拒绝，控制流/编程错误透传；不宣称覆盖未知原生工具故障。
- ✅ 关联模块：六文件成对修改，旧CMake/C/Go/vendor/MANIFEST及权限/action/matrix没有额外修改。
- ✅ 兼容安全：正确旧回归及全仓通过；HostCLI宿主假设经真实RED整改，0新增skip；未授产品执行或隔离权限。
- ✅ 可运行性：软件门及限定hosted Windows四格实际通过；不能写“R2/R3整体100%”或生产可用。

根自审：设计每节都有Task2/3/4接点；无未定义API或省略的依赖；样本限额/公开范围/前后bytes非锁与原生不预填一致，参考代码必须测试后才落实现。

---
**Execution Mode:** serial
