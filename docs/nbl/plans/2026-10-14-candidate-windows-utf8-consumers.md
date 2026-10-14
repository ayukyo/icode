# Candidate Windows UTF-8 consumers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL：后续实施使用 nbl.executing-plans 或经主代理安排的小片实施/审查。本轮仅文档及 RAM 静态核验，不自动执行计划；须 root 全文审阅及 fresh 双审后才允许实施。

**Goal:** 只修原 CI 已证明的两处 UTF-8 消费端，恢复原控制面拒绝正文和 Markdown 工件读取，保持严格解码与原断言。

**Architecture:** `VerificationTests.call` 明确按现有控制面 UTF-8 wire 解码；Markdown 测试按既有工件写入编码读取。两行改动不改变生产代码、子进程 argv、测试夹具源码字节、Git配置或任何门禁判断。

**Tech Stack:** Python 3.10 / stdlib、既有 pytest 9.0.3、既有 GitHub Actions 双平台 candidate 工作流；无新增依赖和权限。

---

## 1. 冻结输入与真实 RED

2026-10-14 实际核对权威 Skill `/home/orbbec/projects/icode-skill` HEAD：`a3999a2cfa1050fc3f189f59c9a04e4f67fbbc0c`。实施前必须仍匹配下列原文件，否则停止套用 patch，先重新核对差异，不能覆盖其它人的变更。

| 文件 | 原 Git blob OID | 原 raw SHA-256 | 两行 patch 后预期 raw SHA-256 |
| --- | --- | --- | --- |
| `tests/test_candidate_verification.py` | `e0026eedc4b458fee1b2091fbbfcf4d78095421e` | `b5832674a32aa2c6893c3ecab8fb910c270611a0a1f3eeb5768b0b6c95243391` | `b7bc81f33f8aa126a47a65e204e30b9004390a1e2ab70a4602c0495afa3040aa` |
| `tests/test_delivery_report.py` | `4351e30043b8fd1e290a7665580d40c16342f158` | `62c247df742e6e17d2fcda14edcb9a72b61b8f78e5b130fc62498dd64b0667f4` | `7c6a4c2f9ca26cba1827bad80cd629da251f1989350b21698ce4760150b620a7` |

真实原 RED：[run 38554148462 / Windows job 115818993268](https://github.com/ayukyo/icode-skill/actions/runs/38554148462/job/115818993268)，实际 checkout `02f419d449f3ba9ba87717a928f740b6ce17e327`，Windows Server 2025 / Python 3.10.11，legacy `16 failed, 92 passed, 5 warnings in 392.59s`、exit 1。其中 13 普通失败节点 + forged-shapes 三 subtest 失败，不是16个独立方法。

本片四个原目标节点：

1. `tests/test_candidate_verification.py::VerificationTests::test_controlled_candidate_fields_still_reject_forged_shapes`：`kind=step_started/step_finished/metadata_updated` 三 subtest，控制面 child exit 2，但 cp1252 `_readerthread` UnicodeDecodeError 后 stdout=None，测试 `.strip()` 崩溃。
2. `tests/test_candidate_verification.py::VerificationTests::test_fresh_build_receipt_real_sha_and_protected_extension`：同类 reader-thread 失败。
3. `tests/test_candidate_verification.py::VerificationTests::test_same_request_different_candidate_conflicts_and_old_pass_cannot_hide_failure`：同类 reader-thread 失败。
4. `tests/test_delivery_report.py::test_markdown_output_contains_independent_direct_and_provenance_facts`：产物已成功生成，`markdown.read_text()` 使用 cp1252，引发 UnicodeDecodeError。

原五 warnings 精确为前三节点的三 + 一 + 一次 reader-thread 失败。保留原日志和全部16F，不取消或重跑原 run；历史 RED 足以支撑此两行现有测试修正，不另写人造生产 bug 或重复测试。

实施前用 `git ls-tree 02f419d449f3ba9ba87717a928f740b6ce17e327 -- tests/test_candidate_verification.py tests/test_delivery_report.py` 确认原 RED 文件仍为表中 blob。原 RED SHA 与新候选 SHA 始终分别记录，不把历史红与未来绿写成同一执行。

## 2. 三问、完整范围与不变量

真实问题已由原运行 trace 确认；已有实现是 Skill `tools/icode_control.py` 原生入口 UTF-8 stdout，以及 `tools/icode_delivery.py` UTF-8 工件写入。Agent `src/icode/control.py::ControlPlane.run` 已带 `-X utf8` 并明确 UTF-8 消费，本片只对齐测试的既有 wire，不修改 Agent。

调用链保护：保留原 child argv、timeout=30、capture_output=True、text=True、预期 returncode 判断、json.loads 和所有业务断言。未传 errors 时 Python 默认 strict；禁止加 replace/ignore，禁止 `stdout or ''`、吞 None/EOF、接受空 dict 作为替代修复。本片不改现有 `.strip()`/fallback 表达式，其原有行为不被本片扩展。

已全文核对两测试文件并检索所有 `read_text/write_text/subprocess.run`。除本片 Markdown 读点外无其它 `read_text` 消费端；其余 metadata `write_text(json.dumps(...))` 默认 `ensure_ascii=True`，正文 ASCII；其它工件/源码文本写点也为 ASCII。没有实证要求本片附带改 JSON 写点，全部保留，避免顺手改变 Windows newline 或夹具候选字节。

明确排除：repo.resolve、autocrlf、LF、新增测试拆分、mode/FIFO/newline文件名、hello.exe、直接 linter child argv/env、所有其它 subprocess、生产 SOURCE、CI配置、Git系统配置、依赖/权限、Agent gitlink、R2/R3验收。standalone linter 空stdout尚无原 bytes stderr 归因，本片不加 `-X utf8` 或 env 使其消失。

## Task 1：核 frozen baseline 与精确两行 patch

**Dependencies:** root 全文审阅与 fresh 双审通过  
**Parallelizable:** No（冻结校验后才可修改）

- [ ] 在权威 Skill 根只读执行下列命令；预期 HEAD 与两文件 OID/SHA-256 匹配表格，工作树两文件无未审差异。

```bash
git rev-parse HEAD
git status --short
git hash-object --no-filters tests/test_candidate_verification.py tests/test_delivery_report.py
sha256sum tests/test_candidate_verification.py tests/test_delivery_report.py
git ls-tree 02f419d449f3ba9ba87717a928f740b6ce17e327 -- tests/test_candidate_verification.py tests/test_delivery_report.py
```

- [ ] 使用 apply_patch 应用以下完整唯一修改。不补其它“顺便修复”。两个 hunk 各一个唯一锚点；缺失或不唯一即停止并回读原文件。

```diff
diff --git a/tests/test_candidate_verification.py b/tests/test_candidate_verification.py
--- a/tests/test_candidate_verification.py
+++ b/tests/test_candidate_verification.py
@@ -47,5 +47,5 @@
     def call(self, *args, ok=True):
         result = subprocess.run([sys.executable, "-B", str(ROOT / "tools/icode_control.py"), *map(str, args)],
-                                capture_output=True, text=True, timeout=30)
+                                capture_output=True, text=True, timeout=30, encoding="utf-8")
         self.assertEqual(result.returncode == 0, ok, (result.stdout, result.stderr))
         return json.loads(result.stdout) if result.stdout.strip().startswith("{") else {}
diff --git a/tests/test_delivery_report.py b/tests/test_delivery_report.py
--- a/tests/test_delivery_report.py
+++ b/tests/test_delivery_report.py
@@ -163,4 +163,4 @@
                            "--output", str(output), "--markdown", str(markdown)], capture_output=True, text=True)
     assert proc.returncode == 0, proc.stdout + proc.stderr
-    content = markdown.read_text()
+    content = markdown.read_text(encoding="utf-8")
     assert all(value in content for value in ("Target built", "Binary executed", "original-source", "artifact-sha", "SN=fixture", "source.log", "not_run"))
```

- [ ] RAM 静态核验两文件 AST、严格 UTF-8 读入、预期哈希与恰好两行 diff。不 import 测试模块、不生成 pyc、不安装 pytest/MCP、不运行原生或 full。实施后的最小核验命令如下；脚本只读源文件并在 RAM compile，不产生测试或产物。

```bash
python3 -B -c 'import ast,pathlib; paths=("tests/test_candidate_verification.py","tests/test_delivery_report.py"); [(ast.parse(pathlib.Path(p).read_text(encoding="utf-8"), filename=p), print(p, "AST_OK")) for p in paths]'
sha256sum tests/test_candidate_verification.py tests/test_delivery_report.py
git diff --check
git diff --numstat -- tests/test_candidate_verification.py tests/test_delivery_report.py
git diff -- tests/test_candidate_verification.py tests/test_delivery_report.py
```

预期两次 AST_OK、两文件新哈希匹配表格、diff --check exit0、numstat 每文件 `1 1`、无额外文件差异。语法核验不替运行 GREEN。

## Task 2：原四节点定点 GREEN 与同 SHA 完整105合同

**Dependencies:** Task 1、必要密钥/固定子仓完整性检查、独立 SPEC 与不同 QUALITY 审查通过  
**Parallelizable:** No（新候选需要先冻结实际 SHA）

- [ ] 依现有用户授权将待验收候选提交推送 Skill main，不新建分支/标签。此计划不给本轮文档阶段执行 Git 的授权；由 root 在实施验收阶段处理。
- [ ] 复用现有 `.github/workflows/candidate-provider-software.yml` 的 push触发，不修改 CI、不增加全局编码环境。绑定实际候选 SHA、run/job、平台与原日志。现有 Linux / Windows 作业已运行全部五文件，因此本片定点 GREEN 首选从同 SHA 完整执行的 collection、失败清单和总量核出，避免重复跑整套。
- [ ] 对每平台完整核实 collection仍105且四目标存在；执行中无skip/error、无目标失败、三 forged-shapes kind 全部完成且无 subtest失败、无五项 reader-thread warning。其它方法失败允许保留在原失败清单，但整体阶段仍失败；必须把本片四目标 GREEN 与“105整体是否通过”分开写。
- [ ] 如果完整原日志不足以逐节点/三kind确定结果，保持该格 unobserved。下面是所需定点执行的精确命令，由后续有能力的线上定点入口运行；本片不为此改CI或在缺pytest的Windows本机安装依赖。没有入口或日志不足时明确报证据不足，不推断GREEN。

```text
python -m pytest -p no:anyio tests/test_candidate_verification.py::VerificationTests::test_controlled_candidate_fields_still_reject_forged_shapes tests/test_candidate_verification.py::VerificationTests::test_fresh_build_receipt_real_sha_and_protected_extension tests/test_candidate_verification.py::VerificationTests::test_same_request_different_candidate_conflicts_and_old_pass_cannot_hide_failure tests/test_delivery_report.py::test_markdown_output_contains_independent_direct_and_provenance_facts -q
```

定点验收预期：四原目标全部通过、三个 forged kind 全通过、exit0、无skip/error/reader-thread warning。原例中的控制面拒绝仍为非零退出码且 metadata/events冻结断言通过；report仍验证全部既有字段，无空文本替代。

- [ ] 既有同 SHA完整命令必须保留，不以定点绿替代：

```text
python -m pytest -p no:anyio tests/test_candidate_freshness.py tests/test_candidate_inspection_generations.py tests/test_candidate_verification.py tests/test_delivery_inventory.py tests/test_delivery_report.py --collect-only -q
python -m pytest -p no:anyio tests/test_candidate_freshness.py tests/test_candidate_inspection_generations.py tests/test_candidate_verification.py tests/test_delivery_inventory.py tests/test_delivery_report.py -q
```

- [ ] 收齐 Windows / Linux provider20、trigger3及现有Linux shell17结果，记录真实exit。新 commit 的其他工作流即使7jobs全绿，也不能抵销旧candidate16F或代替本片同SHA105合同。

交付格式：`candidate_sha / run/job / platform / four-target result / forged3 / reader-warning count / full105 result+exit / remaining failures`。本片仅两行消费修正；其余 FIFO、mode、filename、exe、path、same-content及standalone linter问题未解决，整个Windows compatibility和R2/R3仍未完成。若出现新错误或目标仍红，先读该候选原日志再另定最小修复，不扩展当前patch或关闭检查。

## 研究复用与风险决策

2026-10-14 沿上轮已实际核对的 [Python 3.10 subprocess 官方合同](https://docs.python.org/3.10/library/subprocess.html)与仓库控制面 wire：`encoding` 指定父侧文本解码，未指定 errors 仍 strict；child 环境不因此改变。Markdown读端与既有写端UTF-8一致。Git raw/tree 与换行规范沿[官方 gitattributes](https://git-scm.com/docs/gitattributes)及上轮固定对照保留；本片不改它，不重新刷新竞品名单。

采纳：显式wire消费与工件读取，收益是恢复原断言，成本两行。暂缓：尚未有bytes stderr的standalone linter和未归因同内容节点。不适配：CIenv兜底、decode容错、删断言、mock成功或原套测试整组skip。只使用标准库现有参数，不复制第三方代码、不增许可义务/依赖/权限。

## 【架构级自检报告】

- ✅ 语法/编译：本轮 RAM投影两个唯一锚点已 AST解析通过，预期SHA已计算；生产/运行测试未执行。
- ✅ 依赖/调用链：保留 child argv、timeout、returncode、JSON与业务断言；只指定已有UTF-8消费者。
- ✅ 逻辑/边界：五warning、四目标/三subtest与完整105区分；不吞None/EOF、不接受损坏字节。
- ✅ 异常处理：strict默认、拒绝码及冻结断言保留；standalone linter仍单列未归因。
- ✅ 关联模块：仅规划两行测试改动，本文为唯一新增文件；其它夹具/源码/CI/env/Git不改。
- ✅ 兼容安全：raw bytes、line ending、Git tree、mode、候选ID和生产行为不变；Linux仍需同SHA回归。
- ✅ 可运行性：仅PLAN/RAM静态完成；定点GREEN与线上105未执行，不声称100%运行或阶段完成。

**Execution Mode:** inline（两文件两行机械消费修正；本轮 PLAN ONLY，root全文回读及fresh双审后才进入实施）。
