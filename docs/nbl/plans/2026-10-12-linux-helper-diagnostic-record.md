# Linux helper finite diagnostic record Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development (recommended) or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 Linux 安装包故障 JSON 生产与发布链中增加六个有限事实字段，使启动、ready 与资源通道观察可分别核对。

**Architecture:** 直接复用 `run_fault` 已有 result、固定 workspace/ready 文件与 resource_receipt，不新增执行入口。真实 publisher 使用 exact 类型、有限范围和固定枚举白名单；便携测试编译并执行实际 producer 字典 AST，并调用真实 publisher。

**Tech Stack:** Python 3.11+、unittest、ast、现有 JSON publisher、原 Linux wheel CI。

---

## 当前范围与证据

本次作者只写本 PLAN；下述代码是未来 SOURCE 资产，未创建测试、未改脚本、未运行代码或守护、未做 Git writes。root 的 sequential-thinking 182–184 已完成需求、复用、风险三问。设计依据为 [DESIGN](../specs/2026-10-12-linux-helper-diagnostic-record-design.md)。当前 Windows finite 片必须实际发布之后才能开始这里的 SOURCE；全程只能有一个源码 writer，不交叠冻结候选。

main `74163aa59affa406bed230679ac29ec638c0c979` 的 ubuntu22.04-arm/job114634914991 已安装 probe exit1，原日志窗口 UTC 02:10:58–02:13:16。wheel `e5371a5efdccccc2750a89fa2dd3fe1e7802af4d4b3b11466b03a2d4ea5f75c7`、helper `cee8a99a3f8f178624b6e0031e878f759940ea0acbe47e6d3178f4990135dc4c`、manifest `76277e8312d32f04284dc7a7dcbf50b607a71d6933563594cb237039ce8ef51a`，arm64/kernel6.8.0-1064-azure/systemd249，vendor21566a5。原84记录中32正控未见 error/身份非pass；context/scope/timeout 实际 error=resource_channel_failed，原 `run_fault` 固定要求 timeout，因此负控未通过。原 stderr 仅发布2659bytes，实际 exit/ready/resource terminal unknown，不能推断 traceback、其余失败数、quota/manager/时序根因或偶发。

本片只补观察，不修复已知负控 mismatch；不改原断言、quota、timeout、错误优先级、broker/native/workflows/vendor/KEY。旧失败历史保留，新 SHA 的四格安装原日志另验，重跑不能覆盖原失败。六字段不认证 payload 身份、回收或 timeout 根因；None 是未观察，不是 false 或通过。

## 文件结构与合同

| 路径 | 责任 |
| --- | --- |
| `scripts/probe_installed_linux_helper_object.py` | 在 `run_fault` 原 print 字典增加六字段，保持 print 在断言与 fixture 自清理之前 |
| `scripts/run_native_wheel_ci.py` | 原 `_publish_helper_dispatch_records` 增加有限白名单 |
| `tests/test_linux_helper_diagnostic_record.py` | 新便携 actual AST/publisher 测试资产 |
| `docs/nbl/plans/2026-10-12-linux-helper-diagnostic-record.md` | 本计划与实际阶段记录 |
| `docs/nbl/specs/2026-10-12-linux-helper-diagnostic-record-design.md` | 已有设计与状态记录 |
| `docs/agent-landscape-live.md` | 研究选择与软件/发布/安装观察分账 |

未来冻结、stage、交付精确以上六路径。其它 dirty 文件不属于候选，既有 Windows PLAN 不修改。

| 新字段 | producer 来源 | publisher 合同 |
| --- | --- | --- |
| exit_code | result.exit_code，result 缺失为 None | exact int，闭区间 -255..255，或 None；bool 禁止 |
| payload_started | result.payload_started，result 缺失为 None | exact bool 或 None |
| payload_ready | 固定 `(workspace / "ready").exists()` | exact bool，None 禁止 |
| resource_configured | dict resource_receipt 的 configured；无 receipt 为 None | exact bool 或 None |
| resource_channel_status | dict receipt 的 channel_status；无 receipt 为 None | complete/incomplete/None |
| resource_terminal | dict receipt 的 terminal；无 receipt 为 None | preexec_failed/finished/cleanup_failed/None |

## Task 1: 新测试先行，两个有效目标 RED

**状态**

- [x] 任务完成（实际结果见 SOURCE 记录；生产实现仍待 Task2）

**Dependencies:** None
**Parallelizable:** No（先等待当前 Windows finite 实际发布；唯一 SOURCE writer 串行工作，相关研究只读独立进行）

- [x] Step 1: root 确认当前 Windows finite 已实际 push，原前候选 CI 均终态，读取六路径与调用链，启动相关独立只读研究。研究复用下文固定版本，记录采纳/暂缓/不适配；不阻塞已明确安全测试工作，不以研究替软件验收。

- [x] Step 2: 新建 `tests/test_linux_helper_diagnostic_record.py`，完整内容如下。不导入或调用原 native probe，AST 只执行原 print 内 dict call；既有 publisher API 已存在，不准用 stub 或缺 API 错误取得 RED。实际资产的等价整理与隐私补充见文末记录。

```python
from __future__ import annotations

import ast
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]
FIELDS = (
    "exit_code", "payload_started", "payload_ready", "resource_configured",
    "resource_channel_status", "resource_terminal",
)
GOOD = dict(exit_code=-15, payload_started=True, payload_ready=True,
            resource_configured=True, resource_channel_status="complete",
            resource_terminal="finished")
PRIVATE = "PRIVATE-PATH-COMMAND-STDERR-SENTINEL"


class TestLinuxHelperDiagnosticRecord(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = ROOT / "scripts/run_native_wheel_ci.py"
        spec = importlib.util.spec_from_file_location(
            "native_wheel_ci_linux_diagnostic_test", source)
        cls.publisher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.publisher)

    def producer(self, result, *, ready=True):
        source = ROOT / "scripts/probe_installed_linux_helper_object.py"
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        methods = [node for node in ast.walk(tree)
                   if isinstance(node, ast.FunctionDef) and node.name == "run_fault"]
        self.assertEqual(len(methods), 1)
        calls = []
        for node in ast.walk(methods[0]):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "print" and node.args):
                continue
            dumps = node.args[0]
            if not (isinstance(dumps, ast.Call)
                    and isinstance(dumps.func, ast.Attribute)
                    and isinstance(dumps.func.value, ast.Name)
                    and dumps.func.value.id == "json" and dumps.func.attr == "dumps"
                    and dumps.args):
                continue
            record = dumps.args[0]
            if (isinstance(record, ast.Call) and isinstance(record.func, ast.Name)
                    and record.func.id == "dict"
                    and any(item.arg == "scenario" for item in record.keywords)):
                calls.append(record)
        self.assertEqual(len(calls), 1, "must locate actual fault print dict")
        # Execute the actual expression, not a test copy of its projection.
        expression = ast.fix_missing_locations(ast.Expression(copy.deepcopy(calls[0])))
        with tempfile.TemporaryDirectory(prefix="icode-diagnostic-test-") as raw:
            workspace = Path(raw)
            if ready:
                (workspace / "ready").touch()
            namespace = dict(
                scenario="timeout", resource_mode=True, consumer="context",
                ctx=object(), result=result, error=None, workspace=workspace,
                linux_arch_from_machine=lambda machine: "arm64",
                platform=SimpleNamespace(machine=lambda: "aarch64",
                                         release=lambda: "6.8.0-test"),
                process_closed=True, channels_closed=True, threads_stopped=True,
                owner_states=["closed"], scope_states=["confirmed"], scope_gc=True,
                workspace_live=True, processes=[SimpleNamespace(pid=1234)],
                systemd=["systemd 249"], package_hash="a" * 64,
                manifest_hash="b" * 64,
            )
            return eval(compile(expression, str(source), "eval"), namespace)

    def result(self, receipt=True):
        value = SimpleNamespace(error="resource_channel_failed", exit_code=-15,
                                payload_started=True)
        if receipt is True:
            value.resource_receipt = dict(configured=True, channel_status="complete",
                                          terminal="finished", private=PRIVATE)
        elif receipt is not False:
            value.resource_receipt = receipt
        return value

    def publish(self, raw):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.publisher._publish_helper_dispatch_records(json.dumps(raw))
        lines = output.getvalue().splitlines()
        prefix = "helper-dispatch-record "
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith(prefix), output.getvalue())
        return json.loads(lines[0][len(prefix):]), output.getvalue()

    def test_actual_producer_six_fields(self):
        record = self.producer(self.result())
        self.assertTrue(set(FIELDS).issubset(record), "actual producer lacks six fields")
        self.assertEqual({name: record[name] for name in FIELDS}, GOOD)
        self.assertEqual(record["error"], "resource_channel_failed")

    def test_actual_publisher_six_fields(self):
        published, _ = self.publish(dict(architecture="arm64", topology="scope", **GOOD))
        self.assertTrue(set(FIELDS).issubset(published), "actual publisher drops six fields")
        self.assertEqual({name: published[name] for name in FIELDS}, GOOD)

    def test_producer_missing_result_and_ready_false(self):
        record = self.producer(None, ready=False)
        self.assertTrue(set(FIELDS).issubset(record))
        self.assertIs(record["payload_ready"], False)
        for name in FIELDS:
            if name != "payload_ready":
                self.assertIsNone(record[name])
        self.assertEqual(record["error"], "raised")
        published, output = self.publish(record)
        self.assertEqual({name: published[name] for name in FIELDS},
                         {name: record[name] for name in FIELDS})
        self.assertEqual(published["error"], "raised")
        self.assertNotIn(PRIVATE, output)

    def test_producer_missing_none_empty_and_non_dict_receipt(self):
        for receipt in (False, None, {}, [], PRIVATE):
            with self.subTest(receipt=receipt):
                record = self.producer(self.result(receipt))
                self.assertTrue(set(FIELDS).issubset(record))
                for name in FIELDS[3:]:
                    self.assertIsNone(record[name])
                self.assertEqual(record["exit_code"], -15)
                published, output = self.publish(record)
                self.assertEqual({name: published[name] for name in FIELDS},
                                 {name: record[name] for name in FIELDS})
                self.assertEqual(published["error"], "resource_channel_failed")
                self.assertNotIn(PRIVATE, output)

    def test_publisher_allowed_values_and_none(self):
        allowed = {
            "exit_code": (-255, -1, 0, 255, None),
            "payload_started": (True, False, None),
            "payload_ready": (True, False),
            "resource_configured": (True, False, None),
            "resource_channel_status": ("complete", "incomplete", None),
            "resource_terminal": ("preexec_failed", "finished", "cleanup_failed", None),
        }
        for name, values in allowed.items():
            for value in values:
                with self.subTest(name=name, value=value):
                    raw = dict(architecture="arm64", topology="scope", **{name: value})
                    published, _ = self.publish(raw)
                    self.assertIn(name, published)
                    self.assertIs(type(published[name]), type(value))
                    self.assertEqual(published[name], value)

    def test_publisher_invalid_values_are_deleted_without_echo(self):
        invalid = {
            "exit_code": (True, False, -256, 256, 1.0, PRIVATE, [], {}),
            "payload_started": (0, 1, "true", PRIVATE, [], {}),
            "payload_ready": (None, 0, 1, "true", PRIVATE, [], {}),
            "resource_configured": (0, 1, "true", PRIVATE, [], {}),
            "resource_channel_status": (True, 1, "finished", PRIVATE, [], {}),
            "resource_terminal": (True, 1, "complete", PRIVATE, [], {}),
        }
        for name, values in invalid.items():
            for value in values:
                with self.subTest(name=name, value=value):
                    raw = dict(architecture="arm64", topology="scope", **{name: value})
                    raw.update(private_path=PRIVATE, stderr=PRIVATE, command=PRIVATE,
                               resource_receipt={"private": PRIVATE})
                    published, output = self.publish(raw)
                    self.assertNotIn(name, published)
                    self.assertNotIn(PRIVATE, output)
                    for extra in ("private_path", "stderr", "command", "resource_receipt"):
                        self.assertNotIn(extra, published)

    def test_old_record_compatibility(self):
        raw = dict(architecture="x86_64", topology="no-scope", scenario="timeout",
                   error="timeout", process_closed=True)
        published, _ = self.publish(raw)
        self.assertEqual(published, raw)
        self.assertTrue(set(FIELDS).isdisjoint(published))

    def test_actual_producer_to_publisher_preserves_failure_and_privacy(self):
        raw = self.producer(self.result())
        raw.update(stderr=PRIVATE, command=PRIVATE, private_path=PRIVATE)
        published, output = self.publish(raw)
        self.assertTrue(set(FIELDS).issubset(published))
        self.assertEqual({name: published[name] for name in FIELDS}, GOOD)
        self.assertEqual(published["error"], "resource_channel_failed")
        self.assertNotIn(PRIVATE, output)
        invalid = {
            "exit_code": (True, False, -256, 256, 1.0, PRIVATE, [], {}),
            "payload_started": (0, 1, "true", PRIVATE, [], {}),
            "resource_configured": (0, 1, "true", PRIVATE, [], {}),
            "resource_channel_status": (True, 1, "finished", PRIVATE, [], {}),
            "resource_terminal": (True, 1, "complete", PRIVATE, [], {}),
        }
        for name, values in invalid.items():
            for value in values:
                with self.subTest(name=name, value=value):
                    result = self.result()
                    if name in ("exit_code", "payload_started"):
                        setattr(result, name, value)
                    else:
                        key = {"resource_configured": "configured",
                               "resource_channel_status": "channel_status",
                               "resource_terminal": "terminal"}[name]
                        result.resource_receipt[key] = value
                    raw = self.producer(result)
                    raw.update(stderr=PRIVATE, command=PRIVATE, private_path=PRIVATE)
                    published, output = self.publish(raw)
                    self.assertNotIn(name, published)
                    for other in FIELDS:
                        if other != name:
                            self.assertEqual(published[other], GOOD[other])
                    self.assertEqual(published["error"], "resource_channel_failed")
                    self.assertNotIn(PRIVATE, output)


if __name__ == "__main__":
    unittest.main()
```

上述 `SimpleNamespace` 仅表示软件 double；真实 result/receipt 契约来自已读原调用链，不把 fixture 当 native 身份或资源成功证明。AST fixture 明确提供原字典所需全部 actual names；`result=None` 仍执行实际分支。

- [x] Step 3: 作者分别跑两个目标，root 全文读新测试后独立重现相同目标；保存实际命令、原输出、计数与 exit。期望每条各1test/1assertFAIL/0error/0skip/exit1：producer 缺字段与 publisher 丢字段。NameError、ImportError、AttributeError、选择不到 AST、fixture 错误均不授 RED，修测试后重验。

```bash
.venv/bin/python -m unittest tests.test_linux_helper_diagnostic_record.TestLinuxHelperDiagnosticRecord.test_actual_producer_six_fields -v
.venv/bin/python -m unittest tests.test_linux_helper_diagnostic_record.TestLinuxHelperDiagnosticRecord.test_actual_publisher_six_fields -v
```

- [x] Step 4: 冻结仅测试资产并停止 Task1 writer，root 核两个有效 RED；此时不 commit/push、不 GREEN、不改变原验收谓词。

## Task 2: 六字段配对最小 GREEN

**状态**

- [x] 任务完成（SOURCE 双审与完整守护仍属 Task3）

**Dependencies:** Task 1
**Parallelizable:** No（不同 fresh writer 接续；producer/publisher 是同一个字段合同）

- [x] Step 1: 在 `run_fault` 原 `print(json.dumps(dict(...` 的 `error=` 之前插入下列六个 keyword。只改此故障字典，不改正控记录、捕获、原断言及 finally。重复有限 receipt 类型条件用于本地投影，不另建生产 API。

```python
                    exit_code=result.exit_code if result is not None else None,
                    payload_started=result.payload_started if result is not None else None,
                    payload_ready=(workspace / "ready").exists(),
                    resource_configured=(getattr(result, "resource_receipt", None).get("configured")
                        if type(getattr(result, "resource_receipt", None)) is dict else None),
                    resource_channel_status=(getattr(result, "resource_receipt", None).get("channel_status")
                        if type(getattr(result, "resource_receipt", None)) is dict else None),
                    resource_terminal=(getattr(result, "resource_receipt", None).get("terminal")
                        if type(getattr(result, "resource_receipt", None)) is dict else None),
```

- [x] Step 2: 在 publisher `enums` 的 `exception` 条目之后插入两项；保留原 enums 检查，它先 exact str/None 才做集合成员运算，不对非法 list/dict 抛异常。

```python
        "resource_channel_status": {None, "complete", "incomplete"},
        "resource_terminal": {None, "preexec_failed", "finished", "cleanup_failed"},
```

在原 `for name in hashes:` 之前插入下列代码。`payload_ready` 不接受 None，其它两个 bool 允许 None；exit 不转换、不推导成功、不 echo 未知值。

```python
        for name in ("payload_started", "resource_configured", "payload_ready"):
            value = record.get(name)
            if name in record and (type(value) is bool or
                    (name != "payload_ready" and value is None)):
                safe[name] = value
        value = record.get("exit_code")
        if "exit_code" in record and (value is None or
                (type(value) is int and -255 <= value <= 255)):
            safe["exit_code"] = value
```

- [x] Step 3: 作者与 root 各实际跑两目标，再跑新完整8方法及旧关联回归；新文件必须零 F/E/skip，旧 native/optin skip 单列，不能把便携测试当 native 通过。

```bash
.venv/bin/python -m unittest tests.test_linux_helper_diagnostic_record.TestLinuxHelperDiagnosticRecord.test_actual_producer_six_fields -v
.venv/bin/python -m unittest tests.test_linux_helper_diagnostic_record.TestLinuxHelperDiagnosticRecord.test_actual_publisher_six_fields -v
.venv/bin/python -m unittest tests.test_linux_helper_diagnostic_record -v
.venv/bin/python -m unittest tests.test_linux_helper_dispatch -v
```

- [x] Step 4: 作者静态 SPEC→QUALITY 自审及七维报告，停止源码写入；root 全文读最终两个脚本改动及新测试，检查 producer 的 print 仍先于 mismatch/ready/cleanup 断言、异常捕获不变。任何后续代码变动撤销前候选测试信用，重新冻结与验收。

## Task 3: 双审、完整守护、精确发布与新 SHA 原 CI

**状态**

- [ ] 任务完成

**Dependencies:** Task 2
**Parallelizable:** No（每门依赖前门；只读观察/相关研究可以独立开展）

- [x] Step 1: root 冻结SOURCE，独立 fresh SPEC 全文审查后，不同 fresh QUALITY 全文审查。原 broker/native/workflows/timeout/quota/断言无变化是硬门；先修问题再重冻结重验，不以作者自审代替双审。DOCS阶段记录仍随实际观察追加，最终六路径字节在stage前冻结核验。

- [x] Step 2: root 执行原完整守护，必须原 stdout 三门通过且 exit0；原 preflight 无 JSON，不虚构 `ok` 或猜隐藏全量计数。分别记录命令、session、原结果。

```bash
CMAKE_BUILD_PARALLEL_LEVEL=1 MAKEFLAGS=-j1 .venv/bin/python -B -u scripts/preflight.py
.venv/bin/python -B -m compileall -q -j1 src tests scripts
.venv/bin/python -B scripts/check_site.py
.venv/bin/python -B scripts/check_governance.py
.venv/bin/python -B scripts/preflight.py --only secrets
.venv/bin/python -B scripts/preflight.py --only submodule
git diff --check
```

- [x] Step 3: 最后文档修改后两次执行原文档 scanner。逐项手核代码/fixture 误报，记录原非零数，不改成零；记录修改与复核。不在本计划写作阶段执行。

```bash
.venv/bin/python -B /home/orbbec/.agents/skills/doc-contract-consistency-audit/scripts/check_consistency.py docs/nbl/plans/2026-10-12-linux-helper-diagnostic-record.md docs/nbl/specs/2026-10-12-linux-helper-diagnostic-record-design.md docs/agent-landscape-live.md
.venv/bin/python -B /home/orbbec/.agents/skills/doc-contract-consistency-audit/scripts/check_consistency.py docs/nbl/plans/2026-10-12-linux-helper-diagnostic-record.md docs/nbl/specs/2026-10-12-linux-helper-diagnostic-record-design.md docs/agent-landscape-live.md
```

- [x] Step 4: 开始与结束各更新 live 相关条目、DESIGN/PLAN 真实状态，历史保留。加入下列有限研究选择，之后只用真实命令/结果补充，不提前写源码/安装通过。

```markdown
Linux helper 六字段有限故障记录阶段：复用2026-10-12 02:14–02:17 UTC独立研究，固定Codex7f892275e31002f0422477c6219189284560e689/Apache-2.0与Microsoft connect/WSAEventSelect/Winsock error codes官方资料，不声称HEAD/20项刷新。采纳诊断与准入分账及本工程已有白名单publisher，补exit/start/ready/configured/channel/terminal有限事实；收益为缩小ARM timeout负控unknown，成本为配对投影、actual AST/真实publisher便携测试及新SHA四格原日志。暂缓stderr正文、扩字段、生产行为修复；不适配重跑覆盖741失败、ready/receipt/零exit自动授native成功或R2/R3。无源码复制、新依赖、权限或服务动作。开始SOURCE另启相关独立只读研究，软件、发布、安装与未解决根因分别记录。
```

- [ ] Step 5: 原前候选 CI 都终态、当前守护/双审与既有发布授权满足后，root 执行既有精确 main 流程。stage 前检查 index 仅精确六路径，各字节等于冻结工作树，拒绝无关 dirty、RED或未经审查变更；本作者不执行这些命令。

```bash
git add scripts/probe_installed_linux_helper_object.py scripts/run_native_wheel_ci.py tests/test_linux_helper_diagnostic_record.py
git add -f docs/nbl/plans/2026-10-12-linux-helper-diagnostic-record.md docs/nbl/specs/2026-10-12-linux-helper-diagnostic-record-design.md docs/agent-landscape-live.md
git diff --cached --check
git diff --cached --name-only
git commit -m "test(linux): publish finite helper fault diagnostics"
git push origin main
git ls-remote --heads origin
```

实际 push 成功、远端仅 main 且 SHA 一致才记录发布，不新 branch、不取消前候选 CI。每 task 不单独 commit 未完成测试片；当前完整候选一次发布满足精确范围。

- [ ] Step 6: root 与独立只读观察者监测新 SHA 全部 CI 至终态，读取四 Linux 安装包原日志与 main/Pages/Reviewer 结果。

```bash
gh run list --commit "$(git rev-parse HEAD)" --limit 100 --json databaseId,name,status,conclusion,headSha,url
gh run list --commit "$(git rev-parse HEAD)" --limit 100 --json databaseId --jq '.[].databaseId' | while IFS= read -r diagnostic_run_id; do
    gh run view "$diagnostic_run_id" --json headSha,status,conclusion,jobs,url
    gh run view "$diagnostic_run_id" --log
done
```

从该实际列表逐个选择 run，使用 GitHub 只读日志接口取得完整原日志；记录实际 run/job ID、UTC、OS/Python/arch、wheel/helper/manifest 摘要、stage/exit 与 consumer/topology/scenario。逐条核原故障 JSON 六字段、原 timeout/ready 断言、原收尾事实，不把 publisher 软件 GREEN 替代安装结果。不能凭 job success 推断所有字段正常，不能凭 ready/receipt/exit 推导 error 应是什么。原741失败与原 hidden stderr unknown 保留；若新字段仍不能定位，结论保持 unknown，继续只读分析，不放宽 timeout。Reviewer failure/skip、网络 inconclusive、总 CI failure 如实单列，不借 Linux 诊断授 DENY/ready/R2/R3。

## 研究来源与验收归属

作者本次仅完整读取本地 DESIGN、actual run_fault/断言/finally、实际 publisher、既有 publisher 测试与原 Windows PLAN ARM 基线。研究来自独立观察者2026-10-12 02:14–02:17 UTC已核固定 [Codex smoke L470–527](https://github.com/openai/codex/blob/7f892275e31002f0422477c6219189284560e689/codex-rs/windows-sandbox-rs/sandbox_smoketests.py#L470-L527)、Apache-2.0 与 Microsoft [connect](https://learn.microsoft.com/en-us/windows/win32/api/winsock2/nf-winsock2-connect)、[WSAEventSelect](https://learn.microsoft.com/en-us/windows/win32/api/winsock2/nf-winsock2-wsaeventselect)、[Winsock errors](https://learn.microsoft.com/en-us/windows/win32/winsock/windows-sockets-error-codes-2)。只借鉴诊断与准入分账机制，无上游代码复制；Windows pending/rc!=0 不解释 ARM 故障或放宽本地精确合同。SOURCE 开始前须重新开启相关独立只读研究。

## 计划静态 SPEC→QUALITY 自审

SPEC 覆盖：证据边界在“当前范围”；六字段来源和有限合同在表与 Task2；actual producer/publisher 两目标 RED、None/缺result/缺receipt/非法/privacy/oldcompat 在 Task1；作者/root GREEN 及关联回归在 Task2；双审、完整守护、两次文档扫描、六路径/main/CI终态在 Task3。无未分配设计要求。

QUALITY 覆盖：fixture 提供 print 字典全部 actual names，实际 AST 只抽取原 dict call、不执行 native probe；publisher 真实加载，旧 API 存在；exact bool/int 与范围/枚举先类型后成员测试，恶意 sentinel 不回显；软件 double/native信用明确分账。命令均为未来执行资产，无本轮运行通过信用。

【架构级自检报告】

- 语法/编译：完整代码资产静态核对；本轮未执行解析/编译，动态通过待 SOURCE。
- 依赖/调用链：producer→原 publisher→既有 CI 接线配对完整，不新增入口。
- 逻辑/边界：六字段、None、非法类型/枚举、范围、ready false、缺 result/receipt 均有实际资产覆盖。
- 异常处理：原 BaseException/断言/finally 不变，类型过滤不泄漏 stderr；动态异常验收待 SOURCE。
- 关联模块：精确六路径，旧 publisher 回归与新 AST/publisher 测试同步，双审/守护已列门。
- 兼容安全：旧记录缺字段保持兼容，无新权限/依赖；生产行为与原负控合同不可放宽。
- 可运行性：代码/命令完整但本轮禁止运行，不能声称100%或软件/native通过。

**Execution Mode:** serial（本作者仅 DOCS 交付并停止；root 管理唯一串行 SOURCE writer 与独立只读研究/双审，不由本作者自动 handoff SOURCE）。

## SOURCE 开始记录（2026-10-12 UTC）

02:45 root 实际核 main `d05a23832d7c5c494743abfb63a3ca9a8b1d8a27`，工作树 clean。前一 Windows finite 候选原完整 preflight session86008 exit0，日志 `/tmp/icode-windows-connect-preflight.m5HtX2/typescript`；精确五路径 stage 字节核验、提交及 push 已成功，远端仅 main。其前候选741三工作流已全部终态；d05 的新 CI 只读跟踪中，下一次 push 必须等待其全部终态，不取消进行中的 CI。

本片 PLAN 经 fresh SPEC 和不同 fresh QUALITY 复核均 C0/I0/M0；测试资产最后静态核验摘要 `d3f2ffbbc9269a807fb7365d0d6379be3cb4932994718098f28ddf5edf8036c7`，不表示运行通过。当前启用唯一 Task1 SOURCE writer，仅创建新便携测试；独立只读研究与 CI 观察已启动。两个原生产脚本保持未改，先取得实际 producer/publisher 目标断言 RED，再由不同 fresh writer 实现六字段配对。

Task1 实际新增8方法，函数组织、GOOD构造与夹具局部写法对批准资产作语义等价整理，未扩生产API。root全文检查后补充第8端到端正常/非法分支的stderr/command/private_path sentinel及第6嵌套resource_receipt sentinel；最终测试SHA256 `d5dc95d7e1292f3de8d0c5fefdafed50de8208cb0a201f8eec4c18643ce03b23`。作者停止写入，两目标各1test/1assertFAIL/0error/0skip/exit1，0.027s/0.004s；root最终独立同命令复现各1test/1assertFAIL/0error/0skip/exit1，0.062s/0.003s。失败分别为actual producer缺六字段与实际publisher丢字段，无缺API/AST/夹具错误。不将未实现资产RED称软件通过。

Task1各门实际已满足：Windows实际发布与独立研究；创建测试；作者/root分别两个有效目标RED；最终测试冻结且停止writer。Task2由不同fresh writer串行接续，仅改两个配对脚本，测试保持上述摘要。

Task2 实际两个脚本各增加9行，未改测试或任何原验收谓词。作者两单目标各1/OK、新8/OK、旧dispatch41/OK，均0F/E/skip/exit0；py_compile与diff检查exit0，SPEC→QUALITY自审零问题并停止SOURCE。root全文核实际diff及新测试，独立新8/0.593s、旧41/0.261s，均0F/E/skip/exit0；两单目标各1/OK（0.051s/0.003s）。compileall-j1/site/governance实际通过。

最终SOURCE冻结摘要：producer `d0323a0e23291768e5a251bb41407b76e64881cb85f0e8e8f77578c1638fb37f`；publisher `a708c14f4a797ed174cdb94c519940b30d58a1b88d9651e2a4ea833fec47c4ed`；TEST保持Task1最终摘要。print仍在所有原断言及finally之前；只有限投影/白名单变化。fresh SOURCE SPEC只读进行中，不同QUALITY、原完整守护及新SHA安装包均未预授。

SOURCE fresh SPEC最终C0/I0/M0，独立新8/0.644s与旧41/0.294s；不同fresh QUALITY最终C0/I0/M0，独立新8/0.590s与旧41/0.277s，均0F/E/skip。QUALITY另以RAM-only原HEAD源对两个核心target做鉴别，2test/2assertFAIL/0error/skip，0.050s，无文件写入；不替代既有RED历史。两审结束摘要与冻结值一致，未修改源码。

root唯一原完整preflight session60796于02:57 UTC开始，低资源-j1，日志 `/tmp/icode-linux-diagnostic-preflight.w0Ej2V/typescript`。此记录时仍在运行，不能提前授完整守护或发布信用。

03:00 UTC root实际GET d05三工作流jobs，均running0：CI38196699811为46项=41success/2Reviewerfailure/3skip；provenance38196699727为5/5success；Pages38196699759为2/2success。此为上一提交终态前门，不代表本候选完整守护或新字段已安装验收。root另取d05 ubuntu22.04-arm原日志84records，四timeout场景均error=timeout/exception=null，本次未重现741 mismatch；不归因于仅Windows修改、不撤销741失败，不授ARM根因修复。

原完整preflight唯一session60796最终exit0：原三门stdout均OK，仓外日志footer实际2026-10-12 11:06:46+08:00/COMMAND_EXIT_CODE=0，root03:06:53 UTC取得完整结果；开始footer为10:56:59+08:00，此前“02:57开始”是分钟近似。三SOURCE摘要保持冻结值，无隐藏本机全量计数猜测。软件守护通过不授新SHA installed、ARM根因或R2/R3。文档最终两次原扫描、secret/vendor复核及精确六路径发布随后进行。

【架构级自检报告】（SOURCE软件阶段）

- ✅ 语法/编译：原完整preflight、compileall-j1、diff检查通过。
- ✅ 依赖/调用链：实际producer→publisher配对及49定向回归通过。
- ✅ 逻辑/边界：类型、None、非法范围/枚举、ready false、旧缺字段及E2E矩阵通过。
- ✅ 异常处理：原捕获/断言/清理保持；原错误不被诊断字段改写。
- ✅ 关联模块：两脚本各+9行，broker/native/workflows/vendor未改，独立双审无遗留。
- ✅ 兼容安全：旧记录兼容、敏感sentinel过滤，密钥与固定vendor原守护通过。
- ✅ 可运行性：软件契约及原完整守护通过；原生安装包与整体R2/R3另验，不声称整体100%。

最终三文档原scanner两次均exit0/raw疑似0；人工代码/契约核对未见真实遗留，非使用改写扫描器取得零。追加本真实记录后再次连续两轮复核才能stage。新鲜secret与submodule单门各exit0，vendor固定21566a589cbe98bd35372a04bbb6ca1c51d8eed2且clean。Step5实际精确stage/commit/push及Step6新SHA原安装包观察仍待，不在尚未执行时打勾。
