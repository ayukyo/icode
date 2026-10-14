# Candidate Windows fixture paths Implementation Plan

> **For agentic workers:** 后续按 nbl.executing-plans 分片执行；本轮仅独立只读研究、PLAN与RAM静态，须 root全文回读和fresh SPEC/不同QUALITY审查后才实施。

**Goal:** 对齐VerificationTests初始仓库路径/字节前提及真实编译产物文件名，让原ctime/目录身份负控和真实fresh-build测试走到原断言。

**Architecture:** 只改一个现有测试文件：setUp复用CandidateTests的canonical repo/local autocrlf/LF先例；编译方法用同一binary路径贯穿命令、执行与provenance。产品containment/ctime/identity/hash判断和三个未归因same-content方法不动。

**Tech Stack:** Python3.10、Git、已有cc与candidate双平台CI；无新依赖/权限、无CI配置修改。

---

## 冻结输入、dirty保护与原始RED

2026-10-14 本轮开始实际只读HEAD `b88b1933cbb6ffb39736b0d3512a85f40d7ba464`。后续root通知HEAD已前进到仅timer提交`fc4d358`（未push），本片目标文件仍b88同blob；实施时以目标blob/raw hash为冻结边界，先核实际HEAD与非重叠变化，不能强行回退HEAD。

唯一待改文件 `/home/orbbec/projects/icode-skill/tests/test_candidate_verification.py`：Git blob `ed485144884e86fb5e47a9e0f2c76a2777c911c9`，raw SHA-256 `b7bc81f33f8aa126a47a65e204e30b9004390a1e2ab70a4602c0495afa3040aa`。后续若目标不同须回读差异并重新审查，不覆盖。本文预期patch后hash见末尾静态核验表。

本轮已观察dirty：`tests/test_test_result_summary.py`、`tools/lint_workflow_contract.py`、新 `tests/test_candidate_linter_utf8_unit.py`；它们由root其它工作产生，本文不改、不清理、不纳入本片diff。提交是否带其它已审小片由root冻结实际候选，不能伪称整体工作树clean。权威Agent工作区同样保留既有dirty。

父任务已实际取 [b88 Windows run38557889221/job115831450703](https://github.com/ayukyo/icode-skill/actions/runs/38557889221/job/115831450703)：11:45:50Z footer `10 failed, 95 passed, 3 subtests passed in 454.56s`，rc1；Linux job115831451892为105+5subtests、89.33s通过。四UTF8consumer原目标已绿，本文不重复其修复。本计划作者未重新抓取b88整份raw，以下b88结论来源为root原日志回报。

两个目标仍真实RED：

1. `VerificationTests.test_fresh_old_ctime_and_changed_directory_identity_still_rejected`：resolved artifact为`C:\Users\runneradmin\...`，直接测试传入build_dir仍`C:\Users\RUNNER~1\...`，`relative_to`先拒outside-build-dir，未到预期predates；root核b88 raw再次确认。原02 [job115818993268](https://github.com/ayukyo/icode-skill/actions/runs/38554148462/job/115818993268)同一trace已由本文作者实际取回核对。
2. `VerificationTests.test_reproducible_compiled_artifact_new_ctime_old_mtime_is_fresh`：Windows编译/执行后`os.utime(build/hello)`找不到路径；产物使用`.exe`必须在所有读写/绑定处一致。保留原真实编译、执行、mtime/ctime与fresh receipt断言。

不另制造生产bug或新增镜像测试；以上原CI为现有测试的历史RED。后续必要最小本机定点与新候选原105日志共同验收，不把旧RED与新GREEN写成同一次执行。

## 三问、完整调用链与限定范围

真实问题如上；已有实现为`tests/test_candidate_freshness.py::CandidateTests.setUp`的`repo.resolve(strict=True)`、临时仓库`core.autocrlf=false`及显式UTF8/LF。本片复用同一约定，不引入工具或抽象。

产品链已实际核对：`cmd_build_start`经`verification_evidence.safe_directory` resolve目录并记录设备/inode；fresh验证再次safe_directory核目录身份，然后`artifact_facts` resolve产物、检查位于build_dir、ctime不早于观察、流式真实hash、文件读前后身份及时间不变。直接ctime负控传未canonical的build_dir导致测试前提不一致；不修改产品API去忽略outside或predates。

LF范围严格限定为setUp四个初始文件（`.gitignore`、`source.py`、`README.md`、`cookie_reader.py`）及编译方法新建的`hello.c`。其它测试中的后续源码/README/JSON write_text保持原样，仍可能受平台默认newline影响；本片不宣称所有后续字节都统一或所有合同已保证。

三个未归因same-content方法及其helper不修改；FIFO、mode、newline文件名测试不修改。`core.autocrlf=false`仅当前临时fixture仓库local配置，不改真实工程/global/system配置；可能改变其它方法观察结果，但原始父/子A/B必须继续使用原Git对象、原fixture独立执行。fixture后same-content若绿仅记“在新前提下通过”，不预授其历史根因或回归归属。

## Task 1：冻结原文件并应用完整单文件patch

**Dependencies:** root全文回读及fresh双审通过  
**Parallelizable:** No（先冻结后改）

- [ ] 在权威Skill目录只读核当前HEAD、dirty、目标hash和目标diff。预期目标匹配上述冻结值，重叠差异先停止；非重叠已审变更保留。

```bash
git rev-parse HEAD
git status --short
git hash-object --no-filters tests/test_candidate_verification.py
sha256sum tests/test_candidate_verification.py
git diff -- tests/test_candidate_verification.py
```

- [ ] 使用apply_patch应用下方完整patch；只含setUp与一个编译测试方法，不改其它方法/生产代码。原先的控制面strict UTF8消费行保留。

```diff
diff --git a/tests/test_candidate_verification.py b/tests/test_candidate_verification.py
--- a/tests/test_candidate_verification.py
+++ b/tests/test_candidate_verification.py
@@ -24,14 +24,16 @@
         self.addCleanup(self.temp.cleanup)
         self.repo = Path(self.temp.name) / "repo"
         self.repo.mkdir()
+        self.repo = self.repo.resolve(strict=True)
         self.git("init", "-q")
+        self.git("config", "core.autocrlf", "false")
         self.git("config", "user.email", "test@example.invalid")
         self.git("config", "user.name", "Evidence Test")
-        (self.repo / ".gitignore").write_text(".icode_output/\nbuild/\n")
-        (self.repo / "source.py").write_text("value = 1\n")
-        (self.repo / "README.md").write_text("Initial documentation\n")
-        (self.repo / "cookie_reader.py").write_text("value = 0\n")
+        (self.repo / ".gitignore").write_text(".icode_output/\nbuild/\n", encoding="utf-8", newline="\n")
+        (self.repo / "source.py").write_text("value = 1\n", encoding="utf-8", newline="\n")
+        (self.repo / "README.md").write_text("Initial documentation\n", encoding="utf-8", newline="\n")
+        (self.repo / "cookie_reader.py").write_text("value = 0\n", encoding="utf-8", newline="\n")
         self.git("add", ".")
         self.git("commit", "-qm", "base")
         self.ticket = self.repo / ".icode_output/.icode_output_1"
         self.contract = {"required": True, "required_layers": ["physical"],
@@ -375,22 +377,24 @@
     def test_reproducible_compiled_artifact_new_ctime_old_mtime_is_fresh(self):
         source = self.repo / "hello.c"
-        source.write_text("int main(void) { return 0; }\n")
+        source.write_text("int main(void) { return 0; }\n", encoding="utf-8", newline="\n")
         build = self.repo / "build"
         build.mkdir()
-        parameters = {"configure_command": ["cc", "--version"], "build_command": ["cc", "hello.c", "-o", "build/hello"]}
+        binary = build / ("hello.exe" if os.name == "nt" else "hello")
+        binary_relative = binary.relative_to(self.repo).as_posix()
+        parameters = {"configure_command": ["cc", "--version"], "build_command": ["cc", "hello.c", "-o", binary_relative]}
         candidate = self.snapshot()["candidate_id"]
         start = self.call("build-start", "--dir", self.ticket, "--build-dir", build, "--candidate-id", candidate,
                           "--parameters-json", json.dumps(parameters), "--request-id", "compile-start")
         self.assertEqual(subprocess.run(["cc", "--version"], capture_output=True).returncode, 0)
-        compiled = subprocess.run(["cc", str(source), "-o", str(build / "hello")], capture_output=True, text=True)
+        compiled = subprocess.run(["cc", str(source), "-o", str(binary)], capture_output=True, text=True)
         self.assertEqual(compiled.returncode, 0, compiled.stderr)
-        self.assertEqual(subprocess.run([str(build / "hello")]).returncode, 0)
-        os.utime(build / "hello", (1, 1))
+        self.assertEqual(subprocess.run([str(binary)]).returncode, 0)
+        os.utime(binary, (1, 1))
         receipt = self.meta()["extensions"]["verification"]["build_starts"][-1]
-        self.assertLess((build / "hello").stat().st_mtime_ns, receipt["observed_ns"])
-        self.assertGreaterEqual((build / "hello").stat().st_ctime_ns, receipt["observed_ns"])
-        sha = hashlib.sha256((build / "hello").read_bytes()).hexdigest()
-        provenance = dict(self.binary_provenance(start, [{"path": "build/hello", "sha256": sha}]), **parameters, compiler="cc")
+        self.assertLess(binary.stat().st_mtime_ns, receipt["observed_ns"])
+        self.assertGreaterEqual(binary.stat().st_ctime_ns, receipt["observed_ns"])
+        sha = hashlib.sha256(binary.read_bytes()).hexdigest()
+        provenance = dict(self.binary_provenance(start, [{"path": binary_relative, "sha256": sha}]), **parameters, compiler="cc")
         self.record_artifacts(provenance, request="reproducible-artifact")
 
     def test_artifact_byte_budget_rejects_before_append_and_can_be_explicitly_raised(self):
```

- [ ] RAM AST及精确diff核验，不生成pyc/产物，不运行full。独立审查确认只有两个代码区域改动、产品文件及三个same-content方法/helper未变。

## 路径与断言完整映射

| 环节 | 修正后的同一来源 | 必须保留的验证 |
| --- | --- | --- |
| repo/source/ticket | mkdir后strict resolve的self.repo；后续source、build、ticket从其派生 | 真实Git fixture、真实candidate与工单 |
| 直接ctime负控build_dir | `artifact.parent`从canonical self.repo派生；测试原正文不改 | 仍要求predates；不能以outside替代 |
| 目录替换负控 | canonical self.repo/build → build.old → 新build | `directory identity changed`、原metadata/events bytes不变 |
| configure/build pre-receipt | configure仍cc --version；build输出由binary_relative派生 | build-start真实参数绑定 |
| actual compile/execute | Windows build/hello.exe；Linux build/hello；绝对binary用于真实cc与执行 | cc存在、compile rc0、binary运行rc0 |
| 时间与hash | 同一binary执行utime/stat/read_bytes | mtime旧、ctime不早于receipt、真实SHA256 |
| provenance | `binary_relative=...as_posix()`，来自同一binary；parameters覆盖原helper命令 | 实际artifact路径/hash、receipt命令一致、fresh record通过 |

不新增skip、fakebinary、timestamp mock、伪SHA或兼容fallback。若平台ctime/编译工具本身出现其它不满足，原样失败另诊断，不放宽原断言。

## Task 2：必要两方法定点GREEN与同SHA原105门

**Dependencies:** Task1、frozen patch独立审查通过  
**Parallelizable:** No（结果绑定实际实施候选）

- [ ] 后续仅跑下列两个现有方法作为必要本机定点，或由可用线上定点入口执行；不安装本机pytest/MCP。命令使用stdlib从tests导入，严格只加载2方法，不运行全类。

```text
python -B -c "import sys,unittest; sys.path.insert(0,'tests'); s=unittest.defaultTestLoader.loadTestsFromNames(['test_candidate_verification.VerificationTests.test_fresh_old_ctime_and_changed_directory_identity_still_rejected','test_candidate_verification.VerificationTests.test_reproducible_compiled_artifact_new_ctime_old_mtime_is_fresh']); assert s.countTestCases()==2, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
```

必须实际2方法、0skip/ERROR、exit0。Windows是关键新GREEN；Linux对应方法继续真实执行通过。若缺cc或平台不具原ctime前提，记录真实失败，不擅自skip。测试修改前本机若不重现（如没有短alias），保留历史CI RED，不能伪称取得新本机RED。

- [ ] 先完成必要密钥/固定子仓完整性、fresh SPEC与不同QUALITY审查，再依当前授权由root提交推送main待验收候选；不建分支/标签、不改Agentpin、不触其它未审dirty。此计划本轮不执行Git写操作。
- [ ] 复用现有candidate workflow：新测试源路径已匹配`tests/test_candidate*`，原五文件完整collection105/execution、provider20、trigger3、Linux shell17必须保留；不加CI步骤或env，只消费新候选现有原始日志。

```text
python -m pytest -p no:anyio tests/test_candidate_freshness.py tests/test_candidate_inspection_generations.py tests/test_candidate_verification.py tests/test_delivery_inventory.py tests/test_delivery_report.py --collect-only -q
python -m pytest -p no:anyio tests/test_candidate_freshness.py tests/test_candidate_inspection_generations.py tests/test_candidate_verification.py tests/test_delivery_inventory.py tests/test_delivery_report.py -q
```

- [ ] 同SHA记录run/job、平台/Python/Git、105 collection、实际pass/fail/subtests/skip/warning/exit；两个目标需逐项确认走完原断言。source及fixture前提变更影响全VerificationTests，还须原105回归，不能只以定点绿授整体兼容。
- [ ] 三个same-content方法的结果只作fixture后观察；不删除原始A/B任务、不把新前提下通过追认为历史父版本通过或新provider无回归。其它FIFO/mode/newline/standalone linter失败单列，保持整体Windowscompatibility未过，R2/R3仍未完成。

## 定点研究决策与验收边界

本轮RAM实际核验：完整两hunk patch `git apply --check` 通过；按本文patch投影的完整Python AST通过；三个same-content方法及其共享helper与原文件逐段相同。未运行TEST/编译/原生或full，未写Skill文件；实际原测试raw hash重核不变。最终投影测试raw SHA-256：`13a1758791c169fbfe6c39e4c2826b6d907f3a5d1abd9efc3deaeaf92a1ae92c`（原LF保留），后续实施后须精确匹配。

2026-10-14 复用已实际核对的 [Python3.10 pathlib resolve](https://docs.python.org/3.10/library/pathlib.html#pathlib.Path.resolve)、[Python3.10 open/newline](https://docs.python.org/3.10/library/functions.html#open)、[Git gitattributes](https://git-scm.com/docs/gitattributes)机制和本仓CandidateTests先例。Python文档当前页面版本3.10.22，原Windowsrunner3.10.11；Git在线文档非固定源码commit，规范只解释机制不证明实际根因。没有刷新20项竞品或上游HEAD。

采纳：明确初始fixture路径与字节、显式平台可执行文件名、同一产物贯穿provenance，收益是原测试可到达时间/身份/hash断言，成本单文件两个区域；许可/安全/兼容影响仅测试前提，无复制代码或新依赖权限。暂缓：所有后续文本写点统一、三个same-content归因及产品canonicalization泛化。不适配：改生产containment/ctime、忽略mode/FIFO、全局autocrlf或CIenv、跳过真实编译。验收为原两方法＋同SHA105实际结果，不是研究结论。

## 【架构级自检报告】

- ✅ 语法/编译：完整patch应用check与完整测试投影AST通过；本轮RAM静态，不授编译/运行通过。
- ✅ 依赖/调用链：source/build/binary/receipt/provenance映射完整，原产品safe_directory/artifact_facts链不改。
- ✅ 逻辑/边界：LF只保障五处创建前提，后续write_text未统一；same-content仍待原始A/B。
- ✅ 异常处理：strict resolve失败、编译失败、时间/身份不符仍失败，无skip/fallback/吞异常。
- ✅ 关联模块：唯一待实施测试文件，保留已有dirty与旧105；本轮只新增本文。
- ✅ 兼容安全：真实binary/ctime/hash/冻结bytes断言保留，不改生产候选、权限、Git全局配置。
- ✅ 可运行性：动态定点与同SHA线上未执行；不声称100%运行或整体完成。

**Execution Mode:** inline（现有fixture/一个编译方法；本轮PLAN ONLY，交root全文及fresh双审）。
