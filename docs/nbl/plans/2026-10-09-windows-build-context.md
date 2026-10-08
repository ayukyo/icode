# Windows 构建工具选择诊断 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development (recommended) or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 仅在signed CI签名前，记录并交叉验证本次CMake/MSBuild实际工具选择。

**Architecture:** 默认OFF的CMake诊断生成六字段context；CI-only检查器从同一build根读取固定项目，以同一绝对MSBuild做七属性无build评估。失败阻断attest，不回退PATH；不新增产品执行能力或依赖。

**Tech Stack:** CMake3.20+、Python3.11/3.12 stdlib及已有有界runner、MSBuild17.8+、现四格Windows signed CI。

---

基线main `0f557b10c9df759de4d7550dc73f5d99c3b95f2a`；只改测试根的前片已验收推送，本片原生产者与设计基线58相同。设计 [build-context](../specs/2026-10-09-windows-build-context-design.md) 冻结SHA256 `5bed7f91d70f18554474d40bacdc71104b71b247ede5eddf9eb7ca2bd8f4f07c`，独立SPEC及不同QUALITY批准；QUALITY唯一非阻断建议纳入：MSBuild17.8以下不支持getProperty，必须固定错误且零后续签名，不另造版本/PATH探测。原设计的“待审”属于写入窗口，本条为最新批准状态；本计划尚未实施。

最新发布窗口（2026-10-09）：本片软件已main提交推送 `3ef4ecd7b4854985202e39704c8efa9e2c1be22b`（父0f），push/远端refs/官方main分别核实、提交后工作树干净。精确CI37829612670、来源37829612739仍观察中；Pages37829612642终态success，根另读deploy113491304514，artifact11572727568及pages_build_version精确3ef，Pages观察STOP。根另读macOS workspace113491240520：实际438/0skip（265.021秒）及75lease/0skip（3.950秒）成功，image macos26-arm64 20260907.0351.1；非verbose无逐method PASS标记，不冒称取得独立单测输出。Windows四context尚未执行；0f四signed19PASS不覆盖本片，R2/R3总门不变。下文实施前、守护中、待提交文字保留其历史窗口，最新本条优先。

CI终态追加（2026-10-09）：根独立回读 run37829612670 的 head SHA 精确3ef及44 jobs，completed/failure，37success/4failure/3whole-job-skip。失败限于下述两工作区和两Reviewer；三个已关闭历史probe gate仍为skip，不算PASS。根另读 Python3.11 job113491240860 与 Python3.12 job113491240971：各2287 tests/71skip/0failure/0error，分别616.409与575.483秒，即各2216PASS；不能倒填本机2228PASS/59skip。CI观察STOP，Pages已STOP；只继续签名四格。此是固定提交的远端结果，不是R2/R3整体验收。

签名终态追加（2026-10-09）：根独立核 run37829612739 的 head SHA 精确3ef、completed/success，并回读下列四份 decoded 日志；每份都有固定 `windows-build-context status=PASS production_authority=none`、schema1的完整canonical receipt，且该receipt在本格真实attestation之前，后续19项安装/验签/绑定/负控全部PASS。七源码 SHA 与冻结441788逐项不变。本诊断子门关闭；CI整体失败与R2/R3未完成状态保持，不用旧0f回执补证。

| 实际平台/Python | job | 实际映像版本 | receipt UTC / attest UTC | proof | 安装PASS |
|---|---|---|---|---|---|
| Server2025 x64 / 3.11.9 | 113496182651 | windows-2025-vs2026 / 20260925.250.1 | 19:22:05 / 19:22:07 | [54067141](https://github.com/ayukyo/icode/attestations/54067141) | 19 |
| Server2025 x64 / 3.12.10 | 113496182793 | windows-2025-vs2026 / 20260925.250.1 | 19:21:53 / 19:21:55 | [54067077](https://github.com/ayukyo/icode/attestations/54067077) | 19 |
| Windows11 ARM64 / 3.11.9 | 113496182648 | windows-11-vs2026-arm64 / 20261004.176.1 | 19:24:29 / 19:24:32 | [54067855](https://github.com/ayukyo/icode/attestations/54067855) | 19 |
| Windows11 ARM64 / 3.12.10 | 113496182838 | windows-11-vs2026-arm64 / 20261004.176.1 | 19:22:37 / 19:22:39 | [54067313](https://github.com/ayukyo/icode/attestations/54067313) | 19 |

四格共同receipt字段：`schema_version=1`、`generator=Visual Studio 18 2026`、`toolset=v145`、`sdk_version=10.0.26100.0`、`VCToolsInstallDir=C:\Program Files\Microsoft Visual Studio\18\Enterprise\VC\Tools\MSVC\14.51.36231\`、`WindowsSdkDir=C:\Program Files (x86)\Windows Kits\10\`。x64两格 `architecture=x64`、`msbuild=C:/Program Files/Microsoft Visual Studio/18/Enterprise/MSBuild/Current/Bin/amd64/MSBuild.exe`、`MSBuildToolsPath=C:\Program Files\Microsoft Visual Studio\18\Enterprise\MSBuild\Current\Bin\amd64`；ARM两格 `architecture=arm64`、`msbuild=C:/Program Files/Microsoft Visual Studio/18/Enterprise/MSBuild/Current/Bin/arm64/MSBuild.exe`、`MSBuildToolsPath=C:\Program Files\Microsoft Visual Studio\18\Enterprise\MSBuild\Current\Bin\arm64`。这些是项目评估后所选值，不是dumpbin/mt文件存在性、工具对象锁或Win10原生证据。UTC时间均为2026-10-08，Asia/Shanghai观察日期为10-09。三个run均终态，观察STOP。

根代理唯一文档写者。串行实现者只可改下列七文件；不改vendor、C代码、产品API、权限、其它workflow、Go或MANIFEST。用户指定main自主继续，不创建开发分支/额外worktree，不因技能默认交接要求等待新命令；安全范围或特权变更仍需新授权。编译保守1、不超过6。

同 SHA 的工作区回读（2026-10-09）：根独立取得 x64 job113491240924 与 ARM64 job113491240965 的 decoded 日志，分别432 tests/320.296秒与432 tests/350.341秒，均 failures=1/errors=1/skipped=20、exit1。新失败只有 code 步的 Git WinError10038 与 history prepare 的 Git WinError10093；本窗口未出现旧 IndexError，不移植旧失败。无逐方法输出，故仅能记录整套结果和本片未列入失败列表，不能列20条独立原生PASS。根另读 Reviewer113491241001/113491241208：x64 observer gate=unavailable、ARM=ready，但两者 IPv6 loopback=evidence_unavailable、helper exit78、cleanup=true、单测1failure；不能把ARM的observer就绪写为网络拒绝已证明。进一步 SKILL Git 源码变更仍待独立授权，既有三校验器授权不扩大到它；本片不绕过这些失败。

| 文件 | 责任 |
|---|---|
| native/windows/CMakeLists.txt | 末尾新增默认OFF的context诊断 |
| scripts/probe_windows_build_context.py | 固定资源检查/属性评估/封闭输出 |
| tests/test_windows_build_context.py | portable合同与真实host CMake序列化夹具，分别class |
| scripts/run_workspace_ci.py | 只选portable class一次 |
| tests/test_run_workspace_ci.py | 配对选择合同 |
| .github/workflows/windows-helper-provenance.yml | 四signed构建后、签名前唯一接点 |
| tests/test_windows_bootstrap.py | 复用已有签名workflow/权限合同测试，增加诊断顺序 |

## Task 1: 建立真正的软件RED

**状态**
- [x] 任务完成（仅RED种子，非功能GREEN）

**Dependencies:** None
**Parallelizable:** No（同一实现者持有配对文件，源码串行）

- [ ] 在新测试文件建立入口缺失的assertion，禁止ImportError作为RED：

```python
import importlib.util
import unittest

class TestWindowsBuildContext(unittest.TestCase):
    def api(self):
        spec = importlib.util.find_spec("scripts.probe_windows_build_context")
        self.assertIsNotNone(spec, "build-context CI diagnostic is missing")
        import scripts.probe_windows_build_context as api
        return api

    def test_interface_exists_without_product_authority(self):
        api = self.api()
        self.assertTrue(callable(api.probe))
        self.assertTrue(callable(api.main))
```

- [ ] 用正式解释器运行 `python -B -m unittest tests.test_windows_build_context.TestWindowsBuildContext -v`；旧main应1assertion FAIL/0ERROR。先记录实际结果再实现，夹具错位/导入异常不计RED。

2026-10-09实际Task1：独立实现者仅新增15行种子测试，SHA256 `b0ac4af6a562db8a65fe1cfa8d6bf5a6564fc8a3e75a4c3cc2680279c8efe696`；作者及根各实际1assertion FAIL/0ERROR/0SKIP，0.000秒，缺少spec的断言失败而非导入异常。内置spec/quality自审通过，作者STOP；下一fresh实现者仅Task2接手，不把RED说功能通过。

## Task 2: 实现固定检查器与context序列化

**状态**
- [x] 任务完成（软件实现与夹具；真实VS另验）

**Dependencies:** Task 1
**Parallelizable:** No（生产者/消费者合同成对修改）

- [ ] 新检查器采用以下完整最小实现作为参考，错误仅在main转成固定报文。实现者可为可读性拆分函数，但不能减少任何检查、临时猜路径或输出异常正文：

```python
"""CI-only build selection diagnostic; no product launch authority."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path, PureWindowsPath
import re
import stat
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from icode.runner import _run_unittest_with_bounded_output

CONTEXT_LIMIT = 4096
PROJECT_LIMIT = 1024 * 1024
OUTPUT_LIMIT = 16384
TIMEOUT = 30
FIELDS = {"schema_version", "generator", "platform", "toolset", "sdk_version", "msbuild"}
PROPERTIES = ("Configuration", "Platform", "PlatformToolset", "WindowsTargetPlatformVersion",
              "VCToolsInstallDir", "WindowsSdkDir", "MSBuildToolsPath")
NS = "{http://schemas.microsoft.com/developer/msbuild/2003}"

def text(value):
    if type(value) is not str or not value or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("invalid_context_string")
    value.encode("utf-8", errors="strict")
    return value

def read_fixed(path, limit):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
        raise ValueError("invalid_context_file")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) != info.st_size or len(raw) > limit:
        raise ValueError("invalid_context_file")
    return raw

def unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate_context_member")
        value[key] = item
    return value

def reject_constant(value):
    raise ValueError("invalid_context_constant")

def load_json(raw):
    if type(raw) is not bytes:
        raise ValueError("invalid_context_bytes")
    try:
        return json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=unique,
                          parse_constant=reject_constant)
    except RecursionError as exc:
        raise ValueError("invalid_context_depth") from exc

def existing_windows_path(value, *, directory=False):
    value = text(value)
    if not PureWindowsPath(value).is_absolute():
        raise ValueError("relative_build_tool")
    info = Path(value).lstat()
    valid = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if not valid:
        raise ValueError("invalid_build_tool_path")
    return value

def project_selection(raw, platform):
    source = raw.decode("utf-8", errors="strict")
    if "<!DOCTYPE" in source.upper() or "<!ENTITY" in source.upper():
        raise ValueError("invalid_build_project")
    project = ET.fromstring(source)
    if project.tag != NS + "Project":
        raise ValueError("invalid_build_project")
    sdks = [text(node.text) for node in project.findall(f"{NS}PropertyGroup/{NS}WindowsTargetPlatformVersion")]
    toolsets = []
    for group in project.findall(NS + "PropertyGroup"):
        condition = group.get("Condition", "").strip()
        match = re.fullmatch(r"'\$\(Configuration\)\|\$\(Platform\)'\s*==\s*'Release\|(x64|ARM64)'", condition)
        if match is not None and match.group(1) == platform:
            toolsets.extend(text(node.text) for node in group.findall(NS + "PlatformToolset"))
    if len(sdks) != 1 or len(toolsets) != 1:
        raise ValueError("ambiguous_build_project")
    return toolsets[0], sdks[0]

def probe(build_directory, architecture):
    if sys.platform != "win32" or architecture not in ("x64", "arm64") or not build_directory.is_absolute():
        raise ValueError("invalid_build_context_input")
    if not build_directory.is_dir():
        raise ValueError("invalid_build_context_input")
    context = load_json(read_fixed(build_directory / "icode-windows-build-context.json", CONTEXT_LIMIT))
    if type(context) is not dict or set(context) != FIELDS or type(context["schema_version"]) is not int or context["schema_version"] != 1:
        raise ValueError("invalid_build_context_schema")
    for key in FIELDS - {"schema_version"}:
        text(context[key])
    platform = {"x64": "x64", "arm64": "ARM64"}[architecture]
    if context["platform"] != platform or re.fullmatch(r"Visual Studio [0-9]+ [0-9]{4}", context["generator"]) is None:
        raise ValueError("wrong_build_context_platform")
    msbuild = existing_windows_path(context["msbuild"])
    if PureWindowsPath(msbuild).name.casefold() != "msbuild.exe":
        raise ValueError("wrong_build_tool")
    project = build_directory / "icode_windows_bootstrap.vcxproj"
    selected = project_selection(read_fixed(project, PROJECT_LIMIT), platform)
    if selected != (context["toolset"], context["sdk_version"]):
        raise ValueError("wrong_build_context_selection")
    argv = [msbuild, str(project), "-nologo", "-noAutoResponse", "-nodeReuse:false", "-maxCpuCount:1",
            "-property:Configuration=Release", f"-property:Platform={platform}",
            "-getProperty:" + ",".join(PROPERTIES)]
    result = _run_unittest_with_bounded_output(argv, workspace=build_directory, timeout=TIMEOUT,
                    output_limit_bytes=OUTPUT_LIMIT, environment=os.environ.copy())
    if (type(result) is not tuple or len(result) != 3 or type(result[0]) is not int or result[0] != 0
            or type(result[1]) is not bytes or type(result[2]) is not bytes or result[2] != b""
            or not 0 < len(result[1]) <= OUTPUT_LIMIT):
        raise ValueError("build_property_query_failed")
    root = load_json(result[1])
    if type(root) is not dict or set(root) != {"Properties"}:
        raise ValueError("invalid_build_properties")
    properties = root["Properties"]
    if type(properties) is not dict or set(properties) != set(PROPERTIES):
        raise ValueError("invalid_build_properties")
    for name in PROPERTIES:
        text(properties[name])
    if (properties["Configuration"], properties["Platform"], properties["PlatformToolset"], properties["WindowsTargetPlatformVersion"]) != ("Release", platform, context["toolset"], context["sdk_version"]):
        raise ValueError("wrong_build_properties")
    paths = {name: existing_windows_path(properties[name], directory=True) for name in PROPERTIES[-3:]}
    return dict(schema_version=1, architecture=architecture, generator=context["generator"],
                toolset=context["toolset"], sdk_version=context["sdk_version"], msbuild=msbuild, **paths)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-directory", type=Path, required=True)
    parser.add_argument("--architecture", choices=("x64", "arm64"), required=True)
    args = parser.parse_args()
    try:
        receipt = probe(args.build_directory, args.architecture)
    except (OSError, UnicodeError, ValueError, RuntimeError, ET.ParseError, subprocess.SubprocessError):
        print("::error::windows_build_context_probe_failed")
        return 1
    print("windows-build-context status=PASS production_authority=none")
    print("windows-build-context receipt=" + json.dumps(receipt, separators=(",", ":"), ensure_ascii=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] CMake末尾新增如下独立块。保留原文件全部字节（当前 HEAD 为100行），诊断OFF不生成文件/不执行Python/不改变target；不新增模块模板或sdist依赖：

```cmake
# CI-only selected build context; not product executable authorization.
option(ICODE_WINDOWS_BUILD_CONTEXT_DIAGNOSTIC "Emit CI-only selected build context" OFF)
if(ICODE_WINDOWS_BUILD_CONTEXT_DIAGNOSTIC)
  if(NOT ICODE_BUILD_WINDOWS_BOOTSTRAP OR NOT MSVC OR
     NOT CMAKE_GENERATOR MATCHES "^Visual Studio ")
    message(FATAL_ERROR "Windows build context requires a VS bootstrap build")
  endif()
  if(NOT IS_ABSOLUTE "${CMAKE_VS_MSBUILD_COMMAND}" OR
     NOT EXISTS "${CMAKE_VS_MSBUILD_COMMAND}" OR
     IS_DIRECTORY "${CMAKE_VS_MSBUILD_COMMAND}")
    message(FATAL_ERROR "Windows build context requires explicit MSBuild")
  endif()
  set(_icode_context "{\"schema_version\":1")
  foreach(_icode_pair
      "generator|CMAKE_GENERATOR" "platform|CMAKE_GENERATOR_PLATFORM"
      "toolset|CMAKE_VS_PLATFORM_TOOLSET" "sdk_version|CMAKE_VS_WINDOWS_TARGET_PLATFORM_VERSION"
      "msbuild|CMAKE_VS_MSBUILD_COMMAND")
    string(REPLACE "|" ";" _icode_fields "${_icode_pair}")
    list(GET _icode_fields 0 _icode_key)
    list(GET _icode_fields 1 _icode_variable)
    set(_icode_value "${${_icode_variable}}")
    if(_icode_value STREQUAL "" OR _icode_value MATCHES "[\r\n\t]")
      message(FATAL_ERROR "Invalid Windows build context value")
    endif()
    string(REPLACE "\\" "\\\\" _icode_value "${_icode_value}")
    string(REPLACE "\"" "\\\"" _icode_value "${_icode_value}")
    string(APPEND _icode_context ",\"${_icode_key}\":\"${_icode_value}\"")
  endforeach()
  string(APPEND _icode_context "}\n")
  file(GENERATE OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/icode-windows-build-context.json"
       CONTENT "${_icode_context}")
endif()
```

- [ ] portable测试用真实临时context/project文件、固定Windows词法路径，仅mock现存Windows工具/目录和有界runner；禁止mock JSON/XML验证及成功判定。定义合法六字段context、七属性输出、两个配置XML，分别实际调用x64/arm64 probe。每个负控断言零runner（输入拒绝）或恰好一次runner且拒绝（输出失败），完整argv须与上面固定列表一致。

```python
def test_both_architectures_crosscheck_actual_fixture_bytes(self):
    import json
    from pathlib import Path
    from types import SimpleNamespace
    import stat
    import tempfile
    from unittest.mock import patch
    api = self.api()
    for architecture, platform in (("x64", "x64"), ("arm64", "ARM64")):
        with self.subTest(architecture=architecture), tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            context = dict(schema_version=1, generator="Visual Studio 18 2026", platform=platform,
                           toolset="v145", sdk_version="10.0.26100.0", msbuild="C:/VS/MSBuild.exe")
            properties = dict(Configuration="Release", Platform=platform, PlatformToolset="v145",
                              WindowsTargetPlatformVersion="10.0.26100.0", VCToolsInstallDir="C:/VS/VC",
                              WindowsSdkDir="C:/Kits", MSBuildToolsPath="C:/VS")
            (root / "icode-windows-build-context.json").write_text(json.dumps(context), encoding="utf-8")
            xml = ('<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">'
                   '<PropertyGroup><WindowsTargetPlatformVersion>10.0.26100.0</WindowsTargetPlatformVersion></PropertyGroup>'
                   f'<PropertyGroup Condition="\'$(Configuration)|$(Platform)\'==\'Release|{platform}\'">'
                   '<PlatformToolset>v145</PlatformToolset></PropertyGroup></Project>')
            (root / "icode_windows_bootstrap.vcxproj").write_text(xml, encoding="utf-8")
            original_lstat = Path.lstat
            def windows_tool_fixture(path, *args, **kwargs):
                name = str(path).replace("\\", "/")
                if name == "C:/VS/MSBuild.exe":
                    return SimpleNamespace(st_mode=stat.S_IFREG)
                if name in ("C:/VS/VC", "C:/Kits", "C:/VS"):
                    return SimpleNamespace(st_mode=stat.S_IFDIR)
                return original_lstat(path, *args, **kwargs)
            output = json.dumps({"Properties": properties}).encode("utf-8")
            with patch.object(api.sys, "platform", "win32"), patch.object(Path, "lstat", windows_tool_fixture), \
                    patch.object(api, "_run_unittest_with_bounded_output", return_value=(0, output, b"")) as run:
                observed = api.probe(root, architecture)
            self.assertEqual(observed["architecture"], architecture)
            self.assertEqual(observed["sdk_version"], "10.0.26100.0")
            self.assertEqual(observed["msbuild"], context["msbuild"])
            argv = [context["msbuild"], str(root / "icode_windows_bootstrap.vcxproj"), "-nologo", "-noAutoResponse",
                    "-nodeReuse:false", "-maxCpuCount:1", "-property:Configuration=Release", f"-property:Platform={platform}",
                    "-getProperty:" + ",".join(api.PROPERTIES)]
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args, (argv,))
            self.assertEqual(run.call_args.kwargs["workspace"], root)
            self.assertEqual(run.call_args.kwargs["timeout"], 30)
            self.assertEqual(run.call_args.kwargs["output_limit_bytes"], 16384)
```

- [ ] 精确负控向量：context schema True/1.0/0/2、每字段删除/extra/重复/空/控制/孤立代理项、超过4096及文件链接/目录/空；architecture错/大小写错误、相对build根/不存在、generator非VS、裸/相对/不存在/目录msbuild、basename错误；XML无namespace/错误根/缺SDK/重复SDK/缺当前toolset/重复当前toolset/仅Debug或其它平台/DOCTYPE/ENTITY/畸形/超过1MiB；输出非tuple/错长度/bool退出/非零/空bytes/str bytes/非空stderr/超限/非法UTF8/重复/extra/字段逐个删除/错配置平台toolsetSDK/三个目录逐个相对或缺失；RuntimeError/TimeoutExpired固定错误且无receipt，TypeError/KeyboardInterrupt不吞。旧MSBuild返回非零“不识别参数”按固定错误拒绝，不原样输出stderr。
- [ ] host CMake class使用源码中上述marker后的真实块，放自有临时 `project(... NONE)` 工程，设置假MSVC/VS/平台/toolset/SDK和实际临时MSBuild.exe文件；只验证序列化。OFF实际不生成；ON实际JSON精确六字段/路径引号与反斜线转义；缺VS/缺bootstrap/缺SDK/裸MSBuild/目录输入configure实际非零。正式构建 `--parallel 1`，不把伪变量称真实VS工具选择。临时根先resolve，避免重引入短名/路径别名问题。该class不进入DEFAULT，无编译器时明确记录未测而不混入portable信用。
- [ ] 运行新portable、host class及原bootstrap/direct-volume关联测试，记录实际PASS/FAIL/skip。目标是所有新portable零skip；host情况单列。

## Task 3: 配对CI接点与选择

2026-10-09 Task2复核窗口：作者最终18 portable/3合成CMake PASS、零skip并STOP，但根独立用 `PureWindowsPath` 对四登记路径调用夹具取得1 assertion FAIL/0ERROR/0SKIP（0.001秒）：目录尾分隔符规范化后原字符串比较不识别。根另发现Host实际文件名含Windows非法双引号、portable原生symlink创建依赖未确认权限。只重新授权测试文件修复并新增回归；不改检查器/CMake或隐藏skip。Task2尚未接受，Task3不得提前接线。CMake原文件实为100行，按全部字节保持验收，不按先前误写111行。

同日整改后最新验收：作者新3回归实际5 assertion FAIL/0ERROR/0SKIP（0.051秒），修复后3GREEN；最终20 portable/4合成CMake/36旧关联各通过且零skip，双阶段自审通过并STOP。根回读全部三文件与SHA，独立合跑60PASS/0FAIL/0ERROR/0SKIP（0.984秒）；登记Windows路径使用PureWindowsPath比较、真实root/file lstat和missing负控保持，链接仅S_IFLNK模拟且零runner，不声称原生创建链接。Task2软件验收接受，fresh Task3唯一四文件接线开始。

| Task2文件 | SHA256 |
|---|---|
| scripts/probe_windows_build_context.py | f36627de7fe93886f250eefd85c5e46f78f1c19b6e35d182f905ad87e6aea7d2 |
| native/windows/CMakeLists.txt | a617f5c0cd5c1e50065aad54469bba20f9c63c7065475b48176bff9c9f30105c |
| tests/test_windows_build_context.py | d835e1ef8902b394a37958915cb77497ec1a3d63310b9964b0f32496691d0402 |

**状态**
- [x] 任务完成（软件接线；原生待发布）

**Dependencies:** Task 2
**Parallelizable:** No（合同成对，唯一源码写者）

- [ ] signed工作流原configure命令末尾只追加 `-DICODE_WINDOWS_BUILD_CONTEXT_DIAGNOSTIC=ON`；原build成功检查后、attest之前新增：

```powershell
python scripts/probe_windows_build_context.py --build-directory $buildDirectory --architecture '${{ matrix.helper-architecture }}'
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

- [ ] 在DEFAULT_MODULES的bootstrap/direct-volume旁加且仅一次：

```python
"tests.test_windows_build_context.TestWindowsBuildContext",
```

- [ ] 配对选择合同测试完整内容：

```python
def test_build_context_portable_contract_is_selected_once(self):
    name = "tests.test_windows_build_context.TestWindowsBuildContext"
    self.assertEqual(DEFAULT_MODULES.count(name), 1)
    self.assertNotIn("tests.test_windows_build_context", DEFAULT_MODULES)
    self.assertNotIn(name + "HostCMake", DEFAULT_MODULES)
```

- [ ] 在已有 `TestWindowsBootstrap` 中加入配对顺序合同；复用它的现权限测试而不另造治理模块：

```python
def test_build_context_diagnostic_runs_after_final_build_before_attestation(self):
    workflow = (SOURCE.parents[2] / ".github/workflows/windows-helper-provenance.yml").read_text(encoding="utf-8")
    validate, _, signing = workflow.partition("\n  sign:\n")
    option = "-DICODE_WINDOWS_BUILD_CONTEXT_DIAGNOSTIC=ON"
    probe = "python scripts/probe_windows_build_context.py --build-directory $buildDirectory --architecture '${{ matrix.helper-architecture }}'"
    self.assertEqual(workflow.count(option), 1)
    self.assertEqual(workflow.count(probe), 1)
    self.assertNotIn(option, validate)
    self.assertNotIn(probe, validate)
    build = signing.index("cmake --build $buildDirectory")
    stop = signing.index("if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }", build)
    call = signing.index(probe)
    attest = signing.index("- name: Attest exactly one final helper")
    self.assertLess(build, stop)
    self.assertLess(stop, call)
    self.assertLess(call, attest)
    self.assertIn(probe + "\n          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }", signing)
    self.assertEqual(workflow.count("id-token: write"), 1)
    self.assertEqual(workflow.count("attestations: write"), 1)
    self.assertNotIn("contents: write", workflow)
```

- [ ] 正式运行 `python -B -m unittest tests.test_windows_build_context tests.test_run_workspace_ci tests.test_windows_bootstrap -v`；原binding/direct-volume定点另外关联，真实实际数量以loader为准，不预写PASS计数。

## Task 4: 冻结审查、守护及原生回收

Task3实际验收（2026-10-09）：作者新2方法在旧接点实际2 assertion FAIL/0ERROR/0SKIP（0.005秒），接线后53PASS/0skip及旧关联36PASS/0skip，SPEC与QUALITY自审通过并STOP。根完整回读四文件及diff，独立合跑89PASS/0FAIL/0ERROR/0SKIP（1.034秒），CMake原100行全部字节和四格签名矩阵保持；七源码聚合SHA256 `441788123c0d1bd7e77b1f395f96f51ceefe7788d83702e0e3f406c3c811d25f` 冻结进入独立GLOBAL SPEC，再由不同fresh QUALITY。未跑20/DEFAULT/full，未提交或取得新SHA原生信用。

GLOBAL SPEC已完整回读七文件、实际有界runner和固定设计，独立89PASS/0skip并另做70项控制/异常JSON拒绝检查；前后SHA一致、无Critical/Important/Minor，批准并STOP。不同fresh GLOBAL QUALITY进行中；研究另刷新后续最终PE检查候选，实际四context尚无，不提前定工具路径或白名单。

GLOBAL QUALITY最新批准并STOP：不同审查者完整回读七文件/设计/原HEAD diff/Windows有界runner与Job生命周期，独立89PASS/0skip及3项POSIX runner实际bytes/合计输出限额/超时检查；五Python AST与diff通过、七SHA前后一致，0Critical/Important/Minor。实际host CMake3.22.1；3.20只做语法兼容审查而未实际运行，不冒称版本全测。根compileall-j1、治理/站点/竞品/diff也通过；20轮及默认/全仓守护开始，未提交或授原生信用。

根20轮已实际完成：每轮89项、FAIL/ERROR/SKIP均0，合计1780PASS/0skip（19.405秒）；DEFAULT仍运行，full尚未开始。末轮计数前已启动DEFAULT，存在短暂两套主机进程重叠，并非完全串行启动；每套内仍单并发/每轮串行，无测试或接口减项。后续full须等待DEFAULT退出；所有编译命令保持1、未超过用户6上限。

DEFAULT实际438PASS/0FAIL/0ERROR/0SKIP（163.275秒）并正常退出后，根才启动完整preflight。密钥扫描与固定vendor169完整性已通过，完整测试进行中；不按旧2261数预填本片结果，不隐藏既有skip。

最终软件守护实际完成：完整preflight三道通过，2287 total/2228PASS/59既有SKIP/0FAIL/0ERROR；测试475.079秒、守护476.450秒、实际rc0。独立双审各89PASS/0skip、根20轮1780PASS/0skip及DEFAULT438PASS/0skip，七源码冻结441788保持。compileall-j1、治理/站点/竞品/diff已过；根收尾文档后重核非测试守护，合格才main提交推送。Task4软件部分通过，原生四格仍待新SHA，整体task不提前勾完。

| Task3文件 | SHA256 |
|---|---|
| .github/workflows/windows-helper-provenance.yml | a436fa32045fb68685ce1dd53d4bda8d337f3cd092c4379b48e9bf999820db67 |
| scripts/run_workspace_ci.py | 5b4f3f60d3363e166ce84859744be3be6bd4e795ee0cc9d5f5b29d99cdd2eb4b |
| tests/test_run_workspace_ci.py | eeb9efce9842b5347ae5eb52a0fb73105735281580047f431da5b92e8ecd64a7 |
| tests/test_windows_bootstrap.py | 061d302d3e73eb3577e5e18b21a6115edb40eab7db30e0c6a16d17394a64d071 |

**状态**
- [x] 任务完成（Task4；仅本片CI诊断子门）

**Dependencies:** Task 3
**Parallelizable:** No（冻结后审查；远端只读观察可独立并行）

- [x] 全读七文件diff与调用链，freeze各SHA256；独立SPEC→不同fresh QUALITY，不携root思考历史。整改须TDD后重新freeze/审查，不沿用旧批准。
- [x] 20轮串行新portable/选择/治理及旧bootstrap/direct-volume，零新skip；DEFAULT、完整 `python -B scripts/preflight.py`，打印实际unittest尾部而不改变结果；compileall-j1、治理/站点/竞品/diff、vendor gitlink干净。20轮末段与DEFAULT短暂重叠的实际时间顺序见上文，不声称所有套件启动完全串行。
- [x] 根更新分层证据及研究采纳记录，文档收尾后重核非测试检查。git stage精确七文件与本片docs，核staged列表/父SHA，按现用户授权main提交推送、验证remote refs及官方main。原0f CI独立观察终态STOP，未以新推送取消它。
- [x] 独立只读新SHA四格run，每格实际记录OS/image/Python/context receipt/固定PASS、签名前位置、proof/安装后19PASS；四格成功才关闭此诊断子门。下一设计仍不提前实现生产安全措施。

## acceptance_contract

默认OFF兼容；ON只对实际VS bootstrap生成六字段，所选绝对MSBuild固定评估七属性与项目/context交叉吻合，失败阻断签名。可观察输出不带原异常或环境，不授产品权限。

| Expected behavior | Required layers | Consumers | Scenarios | Environment/device | Baseline | Pass criteria |
|---|---|---|---|---|---|---|
| 实际构建工具选择匹配且签名前失败关闭；普通安装无新增要求 | static/unit/host/native consumption | 既有sign工作流；DEFAULT portable | OFF、正控及负控；x64/ARM64×Python3.11/3.12 | Linux合成夹具；四格GitHub hosted Windows | main0f及七文件冻结441788 | 双审/20轮/DEFAULT/full守护通过；新SHA四格实际context/PASS且后续签名安装通过 |

## verification_matrix

| Layer | Required | Consumer | Scenario | Environment/device | Baseline/artifact | Action | Evidence | Result |
|---|---|---|---|---|---|---|---|---|
| static | yes | 七文件实际调用链 | 字段/权限/顺序与旧兼容 | 当前源码 | 七源码冻结441788、设计5bed7f | 全读/独立SPEC→不同QUALITY | 上文两全局审查0问题及七逐项SHA | pass |
| unit | yes | probe/DEFAULT/workflow | 正负控与既有回归 | Linux主机、合成Windows元数据 | 同七冻结 | 定点/20轮/DEFAULT/full preflight | 89、1780、438均0skip；2287 total/2228PASS/59既有skip、0F/E、3道通过 | pass（skip明示） |
| build/host | yes | CMake metadata producer | ON序列化及OFF兼容 | 本机实际CMake3.22.1 | 同七冻结 | 4项HostCMake | 上文实际4PASS/0skip；不是最低3.20实跑 | pass（主机范围） |
| deploy/consumption | yes | 四格sign消费者 | 实际MSBuild评估→attest→安装 | Server2025 x64/Windows11 ARM，各CPython3.11.9/3.12.10 | 精确3ef及顶部四proof | 独立取得四decoded log、解析receipt并核顺序/后续 | run37829612739 success；四context固定PASS及各19安装PASS，root全部回读 | pass（CI范围） |

## negative_evidence

固定CMake可回退裸MSBuild，反驳变量必为绝对路径的假设；实施前signed日志无工具选择receipt，不能由成品构建成功倒推已收集。3ef四格现在已实际取得receipt，但旧MSBuild/属性缺失/非UTF8原生负控仍只有软件模拟，不称所有VS版本受支持。新CI的Git与Reviewer失败见顶部，不由本片成功抵消。

## gaps

本诊断正向四格及软件门已关闭，根补齐远端记录，这两份后续文档拟随下一PE软件交付，不伪称追加已在3ef中。owner根：后续采集已独立设计/TDD/全局双审/20/default/full通过（六源码923e226），见[采集当前计划](./2026-10-09-windows-pe-capture.md)，但dumpbin/mt精确文件/输出与manifest行为尚无新SHA原生样本；四格另验，不阻断已关闭的本片范围，但阻断PE解析/加载结论。生产held-HANDLE/祖先/DACL/UAC/DLL/DPAPI/配额、macOS quota、默认新工单与R3模型1→6/90%仍是独立硬门，不在本片关闭范围。

## verdict

`verified`（仅本片CI build-context）：实现、全局双审、本机完整守护和3ef四格签名安装正向链均通过；不称Windows生产加载、全部工具版本/原生负控或R2/R3验收完成。

---
**Execution Mode:** serial
