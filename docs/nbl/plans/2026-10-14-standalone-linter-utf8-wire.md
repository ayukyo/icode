# Standalone linter UTF-8 wire Implementation Plan

> **For agentic workers:** 后续使用 nbl.executing-plans 按 TEST → SOURCE → CI验收逐片实施；本轮仅 PLAN / RAM静态，不自动调用执行技能。须 root全文回读、fresh SPEC与不同QUALITY审查后才能实施。

**Goal:** standalone `lint_workflow_contract.py --json` 即使stdout环境为cp1252，也输出严格UTF-8的有效JSON，保留原物理失败门禁与rc1。

**Architecture:** 复用控制面原生入口的TextIOWrapper限定UTF-8 reconfigure；import及被重定向捕获的main不改流。新stdlib测试用真实工单/真实CLI的bytes验证生产wire，再用既有双平台工作流独立执行，保留完整105旧合同。

**Tech Stack:** Python3.10 stdlib、既有Git / GitHub Actions；不新增产品依赖、权限、全局环境或第三方代码。

---

## 冻结输入与边界

2026-10-14 实际只读核对权威Skill `/home/orbbec/projects/icode-skill` HEAD `b88b1933cbb6ffb39736b0d3512a85f40d7ba464`，working tree clean。前两行consumer已在此SHA，不能混入本片生产修复或回写其历史红。Agent gitlink不动。

| 原文件 | Git blob OID | raw SHA-256 |
| --- | --- | --- |
| `tools/lint_workflow_contract.py` | `71f0450cf2ec33eefd82793fbac47e20f3a6eecb` | `3f612d81ae539bf12ab197a8c8c9b95463d8883e15cdc751ae8a7a344b14f1f6` |
| `tools/icode_control.py`（复用入口先例，不改） | `8a0da9ee6eff2f3f70ebabdfb9fcd445480b3a8b` | `26f7d6938ebb49bca91eaf89784913221d2f355b61cdcd5120b0797ceb73b9fe` |
| `.github/workflows/candidate-provider-software.yml` | `6defcbda02e1451c2f5d03d29365dcc1acc56404` | `78dc0f5763469b56bb72635fb09b8327dd9e9b73c1bccf93f7b27ebb73d373e8` |
| `tests/test_candidate_verification.py`（复用fixture，不改） | `ed485144884e86fb5e47a9e0f2c76a2777c911c9` | `b7bc81f33f8aa126a47a65e204e30b9004390a1e2ab70a4602c0495afa3040aa` |

实施前先重核HEAD/上述原文件哈希及新测试路径不存在；任何重叠差异先回读，禁止覆盖别人变更。唯一新测试路径：`tests/test_candidate_linter_utf8_unit.py`。

真实问题/已有实现/调用链三问已确认：linter `--json` 的 `print(json.dumps(..., ensure_ascii=False))` 生产端仍依赖stdout编码；`icode_control.py` 原生入口已有 `isinstance(sys.stdout, io.TextIOWrapper)` + UTF-8 reconfigure；linter生产入口只 `sys.exit(main())`。`main` 仍由argparse先验证参数，`--json`只承诺成功完成输入校验后的报告，缺参数原本rc2/stderr文本，不新增“所有错误都JSON”合同。

root真实Windows诊断回报：原单项默认环境17.040s PASS（b9792a/c0d93c）；同一真实fixture先physical fail再simulated pass，独立standalone bytes调用仅child env分别为 `PYTHONIOENCODING=cp1252:strict` 与 `utf-8:strict`（a47879/4dcc4b）。前者rc1/stdout0/stderr751且UnicodeEncodeError与cp1252标记true；后者rc1/stdout891/stderr0、strictUTF8 JSON dict true。是受控生产编码差异，不是原runner唯一因果证明；本计划作者未重跑该动态诊断。

原 [Windows job115818993268 / run38554148462](https://github.com/ayukyo/icode-skill/actions/runs/38554148462/job/115818993268) checkout02f419d、16F/92P/5warnings保留。其standalone linter空stdout只是原观察，不能因本片受控复现就追认全部16F已归因或修好。

## 方案取舍

采纳控制面同款原生入口guard，成本一个import和三行入口配置；对真实CLI统一UTF-8，但对import/直接main的StringIO不动。暂缓包装/替换sys.stdout与通用跨脚本框架，当前无必要。拒绝在测试childargv加 `-X utf8`、仅改CIenv、父侧replace/ignore解码、ASCII转义全部报告、吞空JSON或改blocked/退出码。生产端不修改stderr；参数错误的原有行为保留。

## Task 1：新增完整stdlib TEST，取得受控semantic RED

**Dependencies:** frozen输入重核、root全文回读及fresh双审通过  
**Parallelizable:** No（先TEST后SOURCE，不提前修生产）

- [ ] 只新增以下完整测试文件；不继承或直接导入VerificationTests类到本模块命名空间，以免unittest额外收集原74个方法。通过模块别名复用一次真实fixture，3方法共享只读报告输入；setUpClass异常也清理。

```python
"""Standalone linter UTF-8 wire; real subprocesses and immutable ticket bytes."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import unittest
from unittest import mock

import test_candidate_verification as fixtures


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/lint_workflow_contract.py"


class StandaloneLinterUtf8Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = fixtures.VerificationTests(methodName="runTest")
        try:
            cls.fixture.setUp()
            cls.fixture.record("fail", request="wire-physical-fail")
            cls.fixture.record("pass", "simulated", request="wire-simulated-pass")
            cls.before = cls.fixture.frozen()
        except BaseException:
            cls.fixture.doCleanups()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.fixture.doCleanups()

    def assert_unchanged(self):
        self.assertEqual(self.before, self.fixture.frozen())

    def arguments(self):
        return [str(SCRIPT), str(self.fixture.ticket),
                "--step", "audit-verified", "--strict", "--json"]

    def assert_blocked_report(self, report):
        self.assertIsInstance(report, dict)
        self.assertGreater(report["blocked"], 0)
        gates = [g for g in report["gates"] if g["gate"] == "delivery_evidence"]
        self.assertEqual(len(gates), 1)
        self.assertEqual(gates[0]["status"], "blocked")
        self.assertTrue(any("outcome=fail" in issue for issue in gates[0]["issues"]), gates)

    def test_native_stdout_json_utf8_keeps_physical_failure(self):
        for encoding in ("cp1252:strict", "utf-8:strict"):
            with self.subTest(stdout_encoding=encoding):
                environment = dict(os.environ, PYTHONIOENCODING=encoding)
                result = subprocess.run([sys.executable, "-B", *self.arguments()],
                                        capture_output=True, timeout=30, env=environment)
                self.assertIsInstance(result.stdout, bytes)
                self.assertIsInstance(result.stderr, bytes)
                self.assertEqual(result.returncode, 1)
                self.assert_unchanged()
                # The old producer must fail an assertion here, not a JSON/decode error.
                self.assertTrue(result.stdout.strip(), "standalone JSON stdout is empty")
                try:
                    report = json.loads(result.stdout.decode("utf-8", errors="strict"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    self.fail("standalone stdout must be valid UTF-8 JSON: " + type(exc).__name__)
                self.assertEqual(result.stderr, b"")
                self.assert_blocked_report(report)
                self.assert_unchanged()

    def test_import_and_redirected_main_keep_text_stream(self):
        original_stdout = sys.stdout
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            spec = importlib.util.spec_from_file_location("wire_linter_import", SCRIPT)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.assertIs(sys.stdout, stream)
            self.assertEqual(stream.getvalue(), "")
            with mock.patch.object(sys, "argv", self.arguments()):
                result = module.main()
            self.assertIs(sys.stdout, stream)
            self.assertEqual(result, 1)
            self.assert_blocked_report(json.loads(stream.getvalue()))
            stream.seek(0)
            stream.truncate(0)
            with mock.patch.object(sys, "argv", self.arguments()):
                with self.assertRaises(SystemExit) as stopped:
                    runpy.run_path(str(SCRIPT), run_name="__main__")
            self.assertEqual(stopped.exception.code, 1)
            self.assertIs(sys.stdout, stream)
        self.assertIs(sys.stdout, original_stdout)
        self.assert_blocked_report(json.loads(stream.getvalue()))
        self.assert_unchanged()

    def test_missing_arguments_keep_argparse_stderr_contract(self):
        environment = dict(os.environ, PYTHONIOENCODING="cp1252:strict")
        result = subprocess.run([sys.executable, "-B", str(SCRIPT)],
                                capture_output=True, timeout=30, env=environment)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        self.assertIn(b"usage:", result.stderr)
        self.assertIn(b"out_dir", result.stderr)
        self.assertNotIn(b"UnicodeEncodeError", result.stderr)
        self.assert_unchanged()


if __name__ == "__main__":
    unittest.main()
```

- [ ] 先保持生产与workflow冻结，只运行本新文件的严格3方法loader；单次真实fixture，不能discover全部candidate测试。

```text
python -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_candidate_linter_utf8_unit.py'); assert s.countTestCases()==3, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
```

预期旧生产真实RED：cp1252子例AssertionError `standalone JSON stdout is empty`；同一方法utf8子例及其余2方法通过，无ERROR/skip/fixture失败。若出现导入、fixture、JSONDecodeError或其他原因，RED不成立，先定位，不进入SOURCE。记录实际Python/Git、平台、exit和原始安全日志；本轮不运行此命令，后续本机必要定点允许使用已可用stdlib，不安装pytest/MCP。newTEST的 `PYTHONIOENCODING` 只在每个真实child进程生效，是故障刺激而非修复；测试父环境不改。

## Task 2：生产最小patch，重复同一3方法GREEN

**Dependencies:** Task1真实semantic RED及新TEST独立审查通过  
**Parallelizable:** No（保护RED→SOURCE顺序）

- [ ] 仅对 `tools/lint_workflow_contract.py` 应用以下完整patch，依原control先例，不改main、报告结构、argparse、stderr或生产返回码。

```diff
diff --git a/tools/lint_workflow_contract.py b/tools/lint_workflow_contract.py
--- a/tools/lint_workflow_contract.py
+++ b/tools/lint_workflow_contract.py
@@ -44,3 +44,4 @@
 import sys
+import io
 import json
 import argparse
@@ -821,2 +822,5 @@
 if __name__ == "__main__":
+    # Native CLI stdout is a UTF-8 wire; imported/captured main stays text-only.
+    if isinstance(sys.stdout, io.TextIOWrapper):
+        sys.stdout.reconfigure(encoding="utf-8")
     sys.exit(main())
```

- [ ] 原样重跑Task1严格3方法loader。预期3方法、2编码子例全部GREEN、0skip/ERROR、loader exit0。真实CLI两编码仍rc1、有效strictUTF8 JSON、stderr空、delivery_evidence blocked且issues保留outcome=fail；metadata/events bytes不变。import/main重定向和缺参数rc2也必须通过。
- [ ] SOURCE新增不接受encoding异常吞掉或fallback；reconfigure失败继续原异常，不能把坏wire报告为成功。测试不要求stderr全部JSON。stdio TextIOWrapper限定使StringIO/其它正常text capture能力沿原行为保持。

## Task 3：窄CI接线，保证新TEST确实执行

**Dependencies:** Task2定点GREEN、源码fresh SPEC与不同QUALITY审查通过  
**Parallelizable:** No（CI消费完整已审候选）

现有push paths的 `tests/test_candidate*` 会被新TEST触发，但原legacy步骤只列五个文件，不会执行该新TEST；因此必须独立strict3 runner。同时加linter源文件路径，防后续单改生产wire漏触发。

- [ ] 对现有 `.github/workflows/candidate-provider-software.yml` 仅加以下一条path和一个step；旧20 provider、trigger3、syntax、完整105 collection/execution、shell17、permissions、matrix和timeout不变。

```diff
diff --git a/.github/workflows/candidate-provider-software.yml b/.github/workflows/candidate-provider-software.yml
--- a/.github/workflows/candidate-provider-software.yml
+++ b/.github/workflows/candidate-provider-software.yml
@@ -5,3 +5,4 @@
     paths:
+      - 'tools/lint_workflow_contract.py'
       - 'tools/icode_candidate.py'
       - 'tools/icode_control.py'
@@ -50,2 +51,4 @@
+      - name: Standalone linter UTF-8 wire contract
+        run: python -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_candidate_linter_utf8_unit.py'); assert s.countTestCases()==3, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
       - name: Syntax
         run: python -B -m py_compile tools/icode_candidate.py tests/test_candidate_git_provider_unit.py
```

- [ ] 验证新TEST文件名匹配push pattern，runner literal与Task1命令完全相同、严格count=3/零skip/真实执行，原旧步骤逐项保留。无continue-on-error、无全局locale/PYTHONUTF8/PYTHONIOENCODING、更改子进程argv或额外依赖。
- [ ] 完成本机必要AST/精确diff/密钥/固定子仓完整性与独立审查后，按既有main-only授权由root提交推送待验收候选，不建分支/标签、不更新Agentpin。收齐新候选两平台strict3原job日志与exit，并收同SHA原完整105及provider20/trigger3/Linux shell17。

验收分层：新wire3方法两平台通过才授此窄wire软件行为；原105若因mode/FIFO/path/exe/same-content等仍失败，则整体Windowscompatibility仍未过，逐项保留。不得用此新测试绿、b88旧其它7jobs绿或默认环境17s单项绿代替同SHA完整105；不取消重跑隐藏失败，不授R2/R3。

## 静态核验与交付记录

本轮只允许从本文RAM抽取完整python、diff/YAML做AST/应用匹配/结构核对，不运行测试、不import fixture、不写Skill文件或生成pyc。实施记录必须包括 frozenSHA、原/新文件hash、新TEST3方法collection、原semantic RED、同命令GREEN、SOURCE前后diff、实际候选SHA、workflow/job/平台/Python/Git、raw exit和剩余旧合同失败。新TEST及两个现有文件变动之外不得有本片修改。

本轮实际RAM核验：完整新TEST与生产投影AST通过；新TEST恰好3个test方法；两个完整diff均 `git apply --check` 通过（仅check，不写工作树）；CI投影保持Syntax name/run相邻并独立增加strict3 step。原Skill文件哈希重核不变、working tree仍clean。以下hash按本文code block正文加一个末尾LF、原文件LF投影计算，实施后必须精确匹配：

| 最终资产 | 预期raw SHA-256 |
| --- | --- |
| `tests/test_candidate_linter_utf8_unit.py` | `eb0aaec3fe85c3bb32f50498bdf9feee4b414c90f9e693273a0266f3e8f3b4b5` |
| `tools/lint_workflow_contract.py` | `3bd65f665547baaa1e00bffd73f484d0cd14f6e4d978189381e286b89c804568` |
| `.github/workflows/candidate-provider-software.yml` | `c2f2ac59f94f2179b5ac05f86b455080e2715a0dd4d74abb50f82d0aa26e319b` |

## 定点研究复用

2026-10-14 复用已实际核对的 [Python3.10 subprocess编码合同](https://docs.python.org/3.10/library/subprocess.html)及 [TextIOWrapper.reconfigure](https://docs.python.org/3.10/library/io.html#io.TextIOWrapper.reconfigure)官方规范和仓库control入口。采纳显式生产wire/严格父侧decode，暂缓通用stdio包装框架，不适配全局环境掩盖和容错decode。收益是standalone可用且gate保持拒绝，成本小片SOURCE/3方法/一个CIstep；不复制第三方代码，无新增许可/依赖/权限，不刷新竞品20项或上游HEAD。

## 【架构级自检报告】

- ✅ 语法/编译：完整TEST/SOURCE投影AST通过、两个patch应用check通过、3方法静态计数正确；本轮仅RAM静态，不授运行通过。
- ✅ 依赖/调用链：复用真实VerificationTests模块fixture；不直接导入其类避免重复收集，严格独立3方法runner保证CI执行。
- ✅ 逻辑/边界：cp1252真实producer semantic RED与consumer问题分开；有效JSON仍blocked/rc1。
- ✅ 异常处理：损坏/空JSON转AssertionError而非解析ERROR；缺参数保持argparse rc2/stderr，生产无异常吞掉。
- ✅ 关联模块：主入口/ioimport、stdlibTEST与CI源路径/runner成套；旧105及其它步骤保留。
- ✅ 兼容安全：import/redirectedmain、metadata/events frozen、模拟不能覆盖物理失败；无全局env/产品权限/依赖变更。
- ✅ 可运行性：本轮PLAN，动态RED/GREEN/线上均未执行；不声称100%运行或阶段完成。

**Execution Mode:** inline（窄stdio入口与3方法fixture/CI接线；本轮不执行，交root全文与fresh双审）。
