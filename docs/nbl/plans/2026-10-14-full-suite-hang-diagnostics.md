# Full-suite Hang Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development (recommended) or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变 Python 3.11/3.12 默认 unittest discover、真实退出语义、25 分钟预算及后续安全门的前提下，为下一候选增加逐例日志和每 120 秒全 Python 线程栈，缩小挂起定位盲区。

**Architecture:** 一个固定 stdlib wrapper 调用原 `unittest.__main__`，仅增加 `-v` 与 faulthandler watchdog；CI 用 `-u` 启动该 wrapper。五个匿名微型子进程契约验证 discover/退出/定时器/回收，绝不在本机运行仓库全套。

**Tech Stack:** CPython 3.11/3.12、unittest、runpy、faulthandler、subprocess、GitHub Actions。

---

## 0. 状态、权限与停止点

2026-10-14；本文件为 PLAN ONLY。root 已实际完成 sequential-thinking e1a74d 三步，确认真实挂起观察、复用原 unittest 入口、风险与取证边界。本轮仅新增本文件；SOURCE/TEST/CI/Git/系统均未实施。当前 Agent 权威工作区 `/home/orbbec/projects/icode`，HEAD `8273cba0fbd82ede73bb9da7f0ba7d2845266b1f`。既有 dirty `docs/development-handoff.md`、`docs/agent-landscape-live.md` 属 root，保留不碰。

本计划覆盖技能默认自动执行/建工作树/提交建议：完成后停止，先 fresh SPEC → 不同 QUALITY → root 全文复核，才可解冻。未来 TEST 作者与 SOURCE/CI 作者不同；仅获得该时点明确授权者可提交推送 main。不得因本文件推断提交、推送、取消、重跑、安装或宿主权限授权。

三问：真实问题是 3.12 没有完成 footer 且被取消；现有默认 unittest 已实现选择和退出，不重写；影响链仅 full-suite 启动及观察，后续 secrets/submodule 原条件和顺序保留。故不做 Docker/隔离源码猜测修复，不扩展进程观察。

## 1. 故障基线七字段

| 字段 | 当前事实与边界 |
| --- | --- |
| identity | GitHub hosted runner，3.12 日志 Ubuntu 24.04.5 / Python 3.12.15；物理序列号/MAC 未取得且本软件诊断不要求设备身份。不能从 orphan PID 推断进程身份链。 |
| time_window | 2026-10-14 UTC：job 13:18:20.882；full 13:18:28.336；最后 bridge observation 13:25:52.996；取消 13:43:34.196。原始 GitHub 时间戳，同源无需本地时钟拼接。约 25 分钟与预算吻合，不证明取消原因或挂起根因。 |
| repo_matrix | runtime/analysis baseline 都绑定 Agent 8273cba0fbd82ede73bb9da7f0ba7d2845266b1f；相较 db47b1299bfa2016adfc88cd7d23c51da919afa3，src/tests/scripts/.github/workflows/native 无差异。vendor pin 21566a589cbe98bd35372a04bbb6ca1c51d8eed2。未来验证必须重新绑定实际候选 SHA。 |
| artifact_identity | 源码型 Python job，不存在本片设备部署/固件产物；CI 原始文件 SHA256 c9e5d83337256c417320139a25cffa53a18eb67240d59890d62250b9ca158929。新资产字节冻结见 §4；不得用计划投影当部署事实。 |
| evidence_sources | run38570665028/job115874692561 原始日志独立读取 119124 字符/299 行，无 Ran/OK；同 run 3.11 job115874693153 原始 footer：3300 tests / 891.195s / skipped=93 / OK。root API 全终态：CI 48=42S+2ReviewerF+1cancel+3skip，provenance38570665021 5S、Pages38570665136 2S，合计55。全量终态计数来自 root，非本计划新增 API 证明。 |
| unresolved | 无逐例 -v、取消前线程栈、orphan argv/PPID；最后 bridge 输出不能标记当前活动测试。owner=root；下一步仅为候选增加栈诊断，不重复旧失败。 |
| conclusion_ceiling | 已证诊断盲区；允许定位下一次实际 Python 栈阻塞。禁止声称 Docker、bridge、ContainerSandbox 或 Python3.12 已定根因/已修复；没有下一同 SHA 线上证据前不得说挂起已解决。 |

### Claim ledger

| Claim | Kind | Source | Boundary | Status |
| --- | --- | --- | --- | --- |
| 3.12 full 无完成 footer且 job cancelled | fact | job115874692561 原日志与 root API | 只绑定8273/attempt1 | 已观察 |
| 3.11同候选完成3300/891.195s/93skip | fact | job115874693153 footer 13:36:10.980 UTC | 不代表3.12或新候选 | 已观察 |
| 25分钟预算触发取消 | inference | job间隔与 timeout-minutes:25 | 仅时间相合，未取得取消触发者证据 | 未定 |
| orphan Docker16961 是根因 | unobserved | cleanup另见 Python2354 | 无命令行/父子/栈，不能归因 | 不采纳 |
| 最后bridge输出即挂住测试 | unobserved | 最后observation13:25:52.996 | 无-v，可能后续模块/清理 | 不采纳 |
| wrapper修复业务挂起 | unobserved | 本片只诊断 | 不修产品、不延长预算 | 禁止宣称 |

### 已排除的直接推断

`ContainerSandbox.wrap` 只组装 argv，无子进程执行。原 native Reviewer probe 显式要求 `ICODE_RUN_CONTAINER_REVIEWER_PROBE=1`，本 full matrix 未设置，且该 subprocess 自带45秒 timeout；不能凭 orphan Docker 盲改。最后 observation 靠近 `tests/test_linux_contract_engineering.py` 最后方法，但默认 discover 顺序之后仍有多个模块；无逐例信息不能缩小到具体挂起调用。两 Reviewer exit78 的旧失败独立保留，不算本片根因。

## 2. 复用与安全设计

采纳：CPython 官方 [faulthandler 3.12 文档](https://docs.python.org/3.12/library/faulthandler.html) 的 watchdog/all-thread traceback 与取消接口；[unittest 命令行文档](https://docs.python.org/3.12/library/unittest.html#command-line-interface) 的默认 discover/-v。观察日期2026-10-14。使用标准库 API，不复制外部实现，不新增依赖或许可负担；本次是机械诊断小片，无新增竞品研究，复用原独立源码核查。暂缓：进程树/Docker cmdline/网络或宿主权限采集。

- 路径兼容：脚本入口原生会把 `scripts/` 放在 `sys.path[0]`，runpy/discover不自动移除。runner只先导入os/sys，把该首项替换为 `os.getcwd()`，保留后续 `PYTHONPATH` 项，再导入诊断/运行模块；finally恢复原argv与path。新oracle用真实script进程（不是-c→run_path）与-m对照，验证scripts专属helper不可见、cwd和相对PYTHONPATH=src专属helper均可见。
- 原 `python -m unittest` 无指定模块时执行 `unittest.__main__` 的 `main(module=None)`。新 wrapper 通过 runpy 执行同一模块，仅固定 argv 为 `["unittest", "-v"]`，不指定 test name、pattern、start directory、loader、runner、skip 或 failfast。
- CI 当前工作目录和 `PYTHONPATH: src` 不变；`python -u` 取消父 Python stdout/stderr 缓冲，`-v` 在执行每例前写标识。wrapper 不增加 CLI/env 开关，生产间隔为常量120秒。
- 定时器 `repeat=True, exit=False`，不杀被测进程，不将卡住转PASS。finally 调用 cancel 并恢复 argv；不捕获/改写 SystemExit，pass=0、fail=1、all-skip=0 保持。硬取消/kill 不保证 finally，正常和 unittest SystemExit 均必须取消。
- 仅输出 Python 栈中的文件名、函数名、行号，不读 locals/argv/env、不 dump source、不输出命令或环境。文件路径和函数名仍属可见诊断元数据；现有失败 traceback/log本来可能输出内容，本片不声称替所有测试日志脱敏。
- watchdog 120秒一次，25分钟 job 上限内最多12次（120…1440秒，安装工具已占用时间只会更少）。CPython 单次最多100线程、每线程100frames、每字符串500字符；诊断附加输出在次数/结构上有界，不截断原 suite stderr、不丢弃失败后伪称PASS。不得把这些结构上限宣传为整个 suite 日志字节硬配额或无限线程完整覆盖。
- 不添加 stdout重定向/日志过滤；保留原退出、25min、fail-fast:false、matrix3.11/3.12、权限、checkout/pins、env、secret guard和submodule guard。suite失败后后门仍按原Actions成功条件跳过，不加always去改变现有门语义。
- 新5方法由正常 discover自动加入；原3300既有集合不筛选。在无并行漂移时预期3305方法，原93skip不被本片消除；实际线上报告必须逐平台核实际count/skip，不能只硬贴旧3300。subTests不当独立方法计数。

## 3. 任务顺序与正式验收

### Task 1：独立 TEST 作者，仅新增契约

Dependencies: fresh SPEC、不同 QUALITY、root 全文批准。Parallelizable: no。

- [ ] 再核HEAD/dirty和§4CI原hash；漂移则暂停重冻，不覆盖root文档。
- [ ] 仅按附录A新增 `tests/test_full_suite_ci_diagnostics.py`（200行）；不得先建runner或改CI。
- [ ] 用下列严格定点命令，先验证 count=5；要求真实旧命令执行的 AssertionRED，0ERROR、0skip。预期4方法红、路径兼容正控1方法绿，8个 failure记录来自4红方法（两个方法各3subTests）；不可误报8方法或要求兼容正控假RED。若缺文件/ImportError、timeout基础设施ERROR或集合变化，停下诊断，不能算RED。
- [ ] 保存实际命令/候选与字节hash/完整失败断言/elapsed。与本计划匿名RAM记录分账。

```bash
PYTHONPATH=src python -B - <<'PY'
import sys
import unittest
from tests.test_full_suite_ci_diagnostics import FullSuiteDiagnosticsTests
suite = unittest.defaultTestLoader.loadTestsFromTestCase(FullSuiteDiagnosticsTests)
if suite.countTestCases() != 5:
    raise SystemExit("expected exactly 5 diagnostics contracts")
result = unittest.TextTestRunner(verbosity=2).run(suite)
if result.testsRun != 5 or result.skipped:
    raise SystemExit("unexpected diagnostics count or skip")
sys.exit(not result.wasSuccessful())
PY
```

### Task 2：不同 SOURCE 作者，原子接线

Dependencies: Task1正式语义RED已存证且root认可；TEST作者不兼任。Parallelizable: no。

- [ ] 重读完整现CI和附录A/B；校验TEST原样，原CIhash仍一致。
- [ ] 新增附录B runner（30行），CI只套用附录C一处命令替换。单独加runner不接线不是完成。
- [ ] AST校验TEST/runner；严格5定点应5/0F/0E/0skip GREEN；禁止全套/Docker/native/install。
- [ ] 校验§4三投影hash、CI patch unique、逆还原CI逐字等原；新文件不夹带其它更改。
- [ ] fresh实际SPEC与不同QUALITY独立审查；保留历史RED，不用本片“修复”旧Reviewer失败。

### Task 3：root验收候选与线上取证

Dependencies: Task2实际双审0；现有55job均终态；root必要secret/submodule和审查门通过。Parallelizable: no（两个Python matrix可由CI原样并行）。

- [ ] root全文复读实际资产，按既有授权提交main待验收候选；不创建分支/tag，不取消/重跑旧失败。
- [ ] 同SHA绑定run/job/attempt、Python版本、原始-v日志、周期trace、退出状态、实际count/skip和后续两门；保持25分钟，绝不加预算掩盖。
- [ ] 成功应保留默认集合（若无其它变化，3305方法）及真实footer；失败/取消/观察不足不授全套或挂起修复信用。3.11/3.12分别核。
- [ ] 若复现卡住，从最后-v开始行和连续线程栈提出下一最小诊断；栈在外部进程wait只说明等待点，不自动证明外部根因。若本轮未复现，仅称诊断已接线/该次suite通过。
- [ ] 若无周期栈、日志截断或超时前未满120秒，按实际标unobserved，不以匿名短测试补线上证据。不扩进程权限或改产品，另行请求必要方向。

## 4. 冻结资产与逆差分

所有资产UTF-8、LF、有最终换行；附录代码 fence 内完整内容即资产（不含fence）。CI除附录C以外逐字不变。

| 资产 | 原SHA256 | 投影SHA256 |
| --- | --- | --- |
| tests/test_full_suite_ci_diagnostics.py | 不存在 | e35437acb1a96ba28d253fbca9eaa33a683786826465d33def21d97b04db1edb |
| scripts/run_full_suite_ci.py | 不存在 | 820330ab86a1681bd03102ed6622ebedd2e83bd951be3beb48dfcadf794787b8 |
| .github/workflows/ci.yml | c9e5d83337256c417320139a25cffa53a18eb67240d59890d62250b9ca158929 | 0abad9d728f177a4094ff98ea563c6d07a171f44fb667c2d2f041545ee89d0d4 |

附录C完整patch文本SHA256：9eb59a40740743e776fddeeb1aea8bfdf8ebfd6d482e81a443878aca96866993（LF、有最终换行）。

逆差分规则：唯一 `        run: python -u scripts/run_full_suite_ci.py\n` 替回 `        run: python -m unittest\n`，所得bytes/hash必须完全恢复原CI。新TEST/runner无既有文件可覆盖；若实际已存在，同样停止重冻。任何已有root/doc/Skill dirty均不在任务内。

## 5. 计划阶段诊断记录（不是正式TDD/不是原挂起复现）

### 保留旧版I1历史，不沿旧GREEN解冻

旧348L计划SHA256 `5345718816b4f9b6402c30b6c384d0e98929233184f88ab5a7d36ad5d9fead34` 的SPEC正式C0/I1/M0，位置为旧296–312 runner与329 CI：真实script保留scripts路径；discover只补cwd，runpy不会清除。独立SPEC完整报告已回读。Windows CPython3.11匿名对照原-m与旧script均discover1/rc0，但scripts专属helper分别不可见/可见；这是真实路径兼容缺陷，不证明旧3300已受影响，且不是旧挂起根因。[CPython v3.11.15 loader.py L269–277](https://github.com/python/cpython/blob/v3.11.15/Lib/unittest/loader.py#L269-L277)与该机制一致。

旧4契约漏了此oracle，timer的-c→run_path不能证明真实script入口路径。原作者匿名旧4/8Assertion/0ERRORskip/2.304s、新4GREEN/2.293s，以及独立SPEC旧4/8Assertion/0ERRORskip/2.939s、新4GREEN/2.912s均保留历史，不能沿用为修订通过。首次更早verbose格式oracle不兼容导致投影3subTest断言失败，同样保留，不改写历史。

### 修订后的匿名投影

只在匿名 `TemporaryDirectory` 写投影小runner/CI和微型模块，TEST类从RAM执行；子进程cwd也是匿名目录，不会 discover 仓库3300。WSL python3软件诊断，非正式TEST先行：

- 新A/旧实际CI命令：collect5，4方法红+路径正控1绿，共8AssertionFailure / 0ERROR / 0skip / 2.390s。旧命令不调用runner，不靠缺文件ImportError。
- 新A/新CI/旧有缺陷runner（I1逆向mutation）：collect5，路径oracle真实scripts=True对比原-m的False，仅1AssertionFailure，另4绿，0ERROR/skip / 2.437s。证明新增oracle能抓旧兼容缺陷，不用-c伪装真实script入口。
- 新A/B/C投影：collect5，5GREEN / 0ERROR / 0skip / 2.448s。路径用真正的 `python -u <匿名project>/scripts/run_full_suite_ci.py`，cwd是匿名project、env中PYTHONPATH精确为相对src（仅测试子进程），无-c/run_path；结果scripts=False、src=True、cwd=True，与原-m一致，且都discover1/rc0。
- 其它pass/fail/skip真实子进程默认discover2，退出0/1/0；正常路径arm/cancel spy保持。短hang仍使用真实faulthandler，仅测试bootstrap把请求120秒转为0.1秒，父2秒超时kill且3秒内communicate回收。timer测试的-c→run_path只证明定时器契约，路径语义由独立真实script测试证明；短测试不等于生产120秒周期或CI25min已验证。
- AST parse两资产、CI唯一替换及逐字inverse通过；CI patch及投影hash与旧版相同，TEST/runner已重新冻结。尚无实际TEST/SOURCE实施、正式RED/GREEN、新候选3.11/3.12线上证据。不得解冻，必须fresh SPEC→不同QUALITY→root全文。

## 附录A：完整新TEST

```python
"""Tiny subprocess contracts: never discover the repository suite in a child."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
OLD = "python -m unittest"
NEW = "python -u scripts/run_full_suite_ci.py"


def full_command():
    text = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    marker = "      - name: Run the full unit test suite\n        run: "
    if text.count(marker) != 1:
        raise AssertionError("full suite step must be unique")
    command = text.split(marker, 1)[1].splitlines()[0]
    if command not in (OLD, NEW):
        raise AssertionError("unexpected full suite command")
    return command


class FullSuiteDiagnosticsTests(unittest.TestCase):
    def fixture(self, root, outcome):
        body = {
            "pass": "self.assertTrue(True)",
            "fail": "self.fail('fixture_failure')",
            "skip": "self.skipTest('fixture_skip')",
            "hang": "local_secret = 'LOCAL_VALUE_SENTINEL'; time.sleep(30)",
        }[outcome]
        (root / "test_a.py").write_text(
            "import time, unittest\nclass Tiny(unittest.TestCase):\n"
            "    def test_wait(self):\n        " + body + "\n",
            encoding="utf-8",
        )
        (root / "test_b.py").write_text(
            "import unittest\nclass Other(unittest.TestCase):\n"
            "    def test_discovered(self):\n        self.assertTrue(True)\n",
            encoding="utf-8",
        )

    def command(self, instrumentation=None):
        active = full_command()
        if instrumentation is None:
            if active == OLD:
                return [sys.executable, "-m", "unittest"]
            return [sys.executable, "-u", str(ROOT / "scripts/run_full_suite_ci.py")]
        bootstrap = (
            "import faulthandler,json,runpy,sys\n"
            "real_arm=faulthandler.dump_traceback_later\n"
            "def arm(timeout,repeat=False,file=None,exit=False):\n"
            " print('ARM:'+json.dumps([timeout,repeat,file is sys.stderr,exit]),"
            "file=sys.stderr,flush=True)\n"
        )
        if instrumentation == "short":
            bootstrap += " real_arm(0.1,repeat=repeat,file=file,exit=exit)\n"
        bootstrap += (
            "def cancel():\n"
            " faulthandler.cancel_dump_traceback_later=real_cancel\n"
            " real_cancel()\n"
            " print('CANCEL',file=sys.stderr,flush=True)\n"
            "real_cancel=faulthandler.cancel_dump_traceback_later\n"
            "faulthandler.dump_traceback_later=arm\n"
            "faulthandler.cancel_dump_traceback_later=cancel\n"
        )
        if active == OLD:
            bootstrap += (
                "sys.argv=['unittest']\n"
                "runpy.run_module('unittest',run_name='__main__',alter_sys=True)\n"
            )
        else:
            path = str(ROOT / "scripts/run_full_suite_ci.py")
            bootstrap += (
                "sys.argv=[" + repr(path) + "]\n"
                "runpy.run_path(" + repr(path) + ",run_name='__main__')\n"
            )
        return [sys.executable, "-u", "-c", bootstrap]

    def run_tiny(self, root, command):
        return subprocess.run(
            command, cwd=root, capture_output=True, text=True,
            encoding="utf-8", errors="strict", timeout=8,
        )

    def test_default_discovery_exit_and_verbose(self):
        for outcome, code in (("pass", 0), ("fail", 1), ("skip", 0)):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as name:
                root = Path(name)
                self.fixture(root, outcome)
                baseline = self.run_tiny(root, [sys.executable, "-m", "unittest"])
                active = self.run_tiny(root, self.command())
                self.assertEqual(baseline.returncode, code, baseline.stderr)
                self.assertEqual(active.returncode, code, active.stderr)
                for result in (baseline, active):
                    self.assertIn("Ran 2 tests", result.stderr)
                    self.assertEqual(result.stdout, "")
                self.assertRegex(active.stderr, r"test_wait \(test_a\.Tiny(?:\.test_wait)?\) \.\.\.")
                self.assertRegex(active.stderr, r"test_discovered \(test_b\.Other(?:\.test_discovered)?\) \.\.\.")
                if outcome == "fail":
                    self.assertIn("FAILED (failures=1)", active.stderr)
                elif outcome == "skip":
                    self.assertIn("OK (skipped=1)", active.stderr)
                else:
                    self.assertIn("OK", active.stderr)

    def test_real_script_preserves_module_import_visibility_with_pythonpath_src(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "scripts").mkdir()
            (root / "src").mkdir()
            (root / "scripts/_diag_scripts_only.py").write_text("", encoding="utf-8")
            (root / "src/_diag_src_only.py").write_text("", encoding="utf-8")
            (root / "_diag_cwd_only.py").write_text("", encoding="utf-8")
            (root / "test_visibility.py").write_text(
                "import importlib.util, json, unittest\n"
                "class Visibility(unittest.TestCase):\n"
                "    def test_visibility(self):\n"
                "        print('VISIBILITY:'+json.dumps({name: "
                "importlib.util.find_spec('_diag_'+name+'_only') is not None "
                "for name in ('scripts','src','cwd')}, sort_keys=True))\n",
                encoding="utf-8",
            )
            env = os.environ.copy()
            env["PYTHONPATH"] = "src"
            baseline_command = [sys.executable, "-m", "unittest"]
            if full_command() == OLD:
                active_command = baseline_command
            else:
                script = root / "scripts/run_full_suite_ci.py"
                script.write_bytes((ROOT / "scripts/run_full_suite_ci.py").read_bytes())
                active_command = [sys.executable, "-u", str(script)]
            observations = []
            for command in (baseline_command, active_command):
                result = subprocess.run(
                    command, cwd=root, env=env, capture_output=True, text=True,
                    encoding="utf-8", errors="strict", timeout=8,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("Ran 1 test", result.stderr)
                lines = result.stdout.splitlines()
                self.assertEqual(len(lines), 1, result.stdout)
                self.assertTrue(lines[0].startswith("VISIBILITY:"), result.stdout)
                observations.append(json.loads(lines[0].removeprefix("VISIBILITY:")))
            expected = {"scripts": False, "src": True, "cwd": True}
            self.assertEqual(observations[0], expected)
            self.assertEqual(observations[1], observations[0])

    def test_timer_armed_and_cancelled_for_all_normal_exits(self):
        for outcome, code in (("pass", 0), ("fail", 1), ("skip", 0)):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as name:
                root = Path(name)
                self.fixture(root, outcome)
                result = self.run_tiny(root, self.command("record"))
                self.assertEqual(result.returncode, code, result.stderr)
                self.assertEqual(result.stderr.count("ARM:[120, true, true, false]"), 1)
                self.assertEqual(result.stderr.count("CANCEL"), 1)
                self.assertLess(result.stderr.index("ARM:"), result.stderr.index("Ran 2 tests"))
                self.assertGreater(result.stderr.index("CANCEL"), result.stderr.index("Ran 2 tests"))

    def test_short_hang_emits_periodic_stacks_and_child_is_reaped(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            self.fixture(root, "hang")
            child = subprocess.Popen(
                self.command("short"), cwd=root, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="strict",
            )
            try:
                with self.assertRaises(subprocess.TimeoutExpired):
                    child.communicate(timeout=2)
            finally:
                if child.poll() is None:
                    child.kill()
                stdout, stderr = child.communicate(timeout=3)
            self.assertIsNotNone(child.returncode)
            self.assertNotEqual(child.returncode, 0)
            self.assertEqual(stdout, "")
            self.assertIn("ARM:[120, true, true, false]", stderr)
            self.assertGreaterEqual(stderr.count("Timeout ("), 2, stderr)
            self.assertIn("in test_wait", stderr)
            self.assertNotIn("LOCAL_VALUE_SENTINEL", stderr)
            self.assertNotIn("OK", stderr)

    def test_ci_wiring_keeps_budget_matrix_and_following_guards(self):
        text = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertEqual(full_command(), NEW)
        self.assertIn("timeout-minutes: 25", text)
        self.assertIn('python-version: ["3.11", "3.12"]', text)
        full = text.index("- name: Run the full unit test suite")
        secret = text.index("run: python scripts/preflight.py --only secrets", full)
        submodule = text.index("run: python scripts/preflight.py --only submodule", secret)
        self.assertLess(full, secret)
        self.assertLess(secret, submodule)


if __name__ == "__main__":
    unittest.main()
```

## 附录B：完整新runner

```python
"""Bounded CI diagnostics around the unchanged unittest default discovery."""
import os
import sys

TRACE_INTERVAL_SECONDS = 120


def main():
    original_argv = sys.argv
    original_path = sys.path[:]
    sys.path[0] = os.getcwd()
    sys.argv = ["unittest", "-v"]
    try:
        import faulthandler
        import runpy

        faulthandler.dump_traceback_later(
            TRACE_INTERVAL_SECONDS, repeat=True, file=sys.stderr, exit=False
        )
        try:
            runpy.run_module("unittest", run_name="__main__", alter_sys=True)
        finally:
            faulthandler.cancel_dump_traceback_later()
    finally:
        sys.argv = original_argv
        sys.path[:] = original_path


if __name__ == "__main__":
    main()
```

## 附录C：完整CI patch

```diff
--- a/.github/workflows/ci.yml
+++ b/.github/workflows/ci.yml
@@ -63,7 +63,7 @@
       - name: Compile Python sources
         run: python -m compileall -q src tests scripts
       - name: Run the full unit test suite
-        run: python -m unittest
+        run: python -u scripts/run_full_suite_ci.py
       # The full-suite step above is the tests gate. Do not run it a second
       # time through the composite preflight; keep the other two gates explicit.
       - name: Run the secret delivery guard
```

## 6. 七维自检与交付边界

【架构级自检报告】

1. 语法/编译：投影TEST/runner AST通过；未实施，不声称仓库编译或CI通过。
2. 依赖/调用链：仅stdlib，原unittest.__main__，默认discover和两后门保持；无新依赖。
3. 逻辑/边界：pass/fail/skip、真实script路径/PYTHONPATH、周期栈、正常cancel、kill/reap匿名微型投影通过；不等于原hang根因。
4. 异常处理：SystemExit原样传播；父短测试超时必回收。外部硬kill不保证finally，明确保留。
5. 关联模块：仅未来3资产；CI权限/env/pins/matrix/预算不变，root既有文档dirty保留。
6. 兼容安全：不筛测试、不改skip、不延预算；trace无locals/argv/env，诊断结构有界，旧失败不隐藏。
7. 可运行性：冻结5契约投影已软件验证；正式RED/GREEN、实际部署及双Python同SHA full均待后续，不能写100%产品验收。

**串行 footer：** Task1(TEST正式RED) → Task2(不同SOURCE/CI作者、strict5GREEN、actual双审) → Task3(root候选main与同SHA线上验收)。本轮停在计划交付，禁止自动执行。
