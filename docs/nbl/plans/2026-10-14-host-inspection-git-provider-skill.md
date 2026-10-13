# Skill Inspection Git Provider 软件子片 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development (recommended) or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Skill helper 中交付可独立验证的五类 typed Git provider 软件接口及全消费者传播，旧 `None` 本地行为保持原样；不开放宿主身份绑定、不更新 Agent pin、不宣称 S2c 完成。

**Architecture:** helper 保留原普通 Git 实现，显式 provider 分支仅接收固定 query 类型和有界结果。provider 注入是一种宿主程序内依赖，不是模型能力或授权；第一子片仅软件语义 fixture，真实 transport/ledger/对象 snapshot/Agent 工具及 native 权限链另立完整计划。

**Tech Stack:** Python stdlib、现 inspection helper、stdlib unittest 软件 fixture、线上既有 pytest legacy 回归、GitHub Actions Ubuntu/Windows 软件门。

---

状态：PLAN ONLY。e92设计SPEC C0/I0/M0、QUALITY C0/I1/M1；修订95199设计已获独立SPEC及不同QUALITY均C0/I0/M0。首计划候选 `2ac47f1a1712c0ef7c5afc8566f1502624e7a4df39b6c8312c0133df52840a8c` SPEC C0/I2/M0，真实漏provider的related关联与Windows relpath分隔符已在本次修订，计划仍待fresh双审。当前禁止 SOURCE/TEST/CI/Git 变更。本文代码只是后续作者应执行的完整资产，未在源仓创建。用户 main-only 约束优先于技能的新 worktree/立即执行要求；不创建分支、worktree、标签或自动实施。

## 来源、阶段和修改边界

主仓 `/home/orbbec/projects/icode` HEAD `6e893f0170b74c32d7143680636d85f400ecc7c9`；软件子片源仓 `/home/orbbec/projects/icode-skill` main `52cb6b3f0229bfc16e6faf00ce5dd2506e252a22`，远端 freshness 由主代理 `8dfb2d` 的 ls-remote 证据确认。D 用户 dirty 工作树不覆盖/暂存。

| 阶段 | 实际可交付内容 | 完成标准 | 尚不具备 |
|---|---|---|---|
| P1，本计划 | typed helper/provider、全部 helper 消费者、独立 RED/GREEN/legacy、Skill 软件 CI | 所有计划资产与候选绑定的软件验收通过 | host binding/真实 Git身份/native权限/S2c |
| P2，另立完整 PLAN 后执行 | CP 私有 FD transport、host v1 ledger、immutable metadata/object closure、所有 CP 消费者及权限 oracle | 新完整计划及实际 host/native CI | Agent模型工具闭环、安装升级矩阵 |
| P3，另立完整 PLAN 后执行 | Agent assess/schema/loop/prompt、安装/runtime manifest、完整旧215→新pin差异治理、跨平台/native闭环 | 实际主仓/Skill候选 SHA、全部必要job日志与exit | 通过前不得称整个契约完成 |

P2/P3 的实施门是完成各自具体代码/测试/依赖/故障处理计划并独立双审，不能直接拿本文只读阶段表实施。此表明确不执行后续阶段，不用空白实现替代完整计划。

| 文件（P1 后续才改） | 责任 |
|---|---|
| Skill `tools/inspection_worklist.py` | 同文件定义 stdlib typed ABI；查询分支与全部 helper 传播；不加 CP CLI/provider 自动发现 |
| Skill `tests/test_inspection_git_provider_unit.py` | 本文完整新 stdlib unittest 资产，行为 RED、provider failures、真实本地 Git legacy |
| Skill `.github/workflows/inspection-software.yml` | 本文完整 main-push 软件门；无网络/原生权限或 S2c 通过含义 |

不修改 CP、crosscheck CLI、Agent、vendor/gitlink、manifest、安装脚本或公开模型 schema。全部新接口仅由可信程序显式对象调用，不能从环境/报告/命令行 JSON 获得 provider。

## Task 1：独立 TEST 作者建立完整软件 RED 资产

**状态**

- [ ] 任务完成

**Dependencies:** None
**Parallelizable:** No (QUALITY 完成且主代理解冻 TEST 后才写；SOURCE 作者必须不同)

- [ ] Step 1：主代理记录设计 QUALITY 和本计划独立双审结论，确认 canonical source SHA 和 clean state；任一变更冲突停止，不回退用户文件。

```bash
git -C /home/orbbec/projects/icode-skill rev-parse HEAD
git -C /home/orbbec/projects/icode-skill status --porcelain
```

Expected：HEAD 为上述52cb基线、无未归属变更；这些是后续执行命令，本次未执行。

- [ ] Step 2：独立 TEST 作者通过 apply_patch 创建完整 `tests/test_inspection_git_provider_unit.py`：

```python
"""Software-only provider fixtures; no host identity or native isolation claim."""
import copy
import hashlib
import importlib.util
import inspect
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

TOOL = Path(__file__).resolve().parents[1] / "tools/inspection_worklist.py"
spec = importlib.util.spec_from_file_location("inspection_provider_unit", TOOL)
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)
OID = "1" * 40
OLD = b"int timestamp_old(void) { return 1; }\n"

def invoke(function, *args, provider, **kwargs):
    # Before SOURCE: run actual existing semantics, not TypeError/import RED.
    if "git_provider" in inspect.signature(function).parameters:
        kwargs["git_provider"] = provider
    return function(*args, **kwargs)

ProviderBase = getattr(api, "InspectionGitProvider", object)

class FixtureProvider(ProviderBase):
    def __init__(self, root):
        self.workspace = root
        self.calls = []
        self.fault = None
    def query(self, request, *, limit):
        op = request.operation.value
        self.calls.append(request)
        if op == "resolve_commit":
            data = (OID + "\n").encode("ascii")
        elif op == "diff_names":
            data = b"src/current.c\0src/old.c\0outside.c\0"
        elif op == "list_files":
            data = (b"src/current.c\0src/old.c\0src/test_current.c\0"
                    if request.kind == "association" else b"src/added.c\0")
        elif op == "historical_blob":
            data = OLD
        elif op == "trigger_diff":
            data = b"@@ -1 +1 @@\n-int64_t clock_ns = -1;\n+return 1;\n"
        else:
            raise AssertionError("unexpected provider operation")
        error, exit_code, truncated = None, 0, False
        if self.fault == "exit":
            exit_code = 2
        elif self.fault == "error":
            error = "query_failed"
        elif self.fault == "truncated":
            truncated = True
        elif self.fault == "malformed_names" and op == "diff_names":
            data = b"../escape.c\0"
        elif self.fault == "non_utf8" and op == "historical_blob":
            data = b"\xff"
        elif self.fault == "overflow":
            data = b"x" * (limit + 1)
        elif self.fault == "bad_result":
            return SimpleNamespace(data=data, exit_code=0, truncated=False, error=None)
        elif self.fault == "missing_nul" and op in ("diff_names", "list_files"):
            data = b"src/current.c"
        elif self.fault == "non_utf8_names" and op in ("diff_names", "list_files"):
            data = b"\xff\0"
        elif self.fault == "bool_exit":
            exit_code = False
        elif self.fault == "nonbool_truncated":
            truncated = "false"
        Result = getattr(api, "GitQueryResult", SimpleNamespace)
        return Result(data=data, exit_code=exit_code, truncated=truncated,
                      error=error)

class NestedRelatedProvider(FixtureProvider):
    def query(self, request, *, limit):
        op = request.operation.value
        if op not in ("diff_names", "list_files"):
            return super().query(request, limit=limit)
        self.calls.append(request)
        if op == "diff_names":
            data = b"src/nested/current.c\0"
        elif request.kind == "association":
            data = b"src/nested/current.c\0"
            if "related/nested" in request.scopes:
                data += b"related/nested/related.c\0related/nested/test_related.c\0"
        else:
            data = b""
        return api.GitQueryResult(data=data, exit_code=0, truncated=False, error=None)

def entries(report):
    return {f["path"]: f for u in report["units"] for f in u["files"]}

def reads(report):
    for f in entries(report).values():
        f["reads"] = {phase: f["sha256"] for phase in report["required_phases"]}

def assessment(check, report):
    old = entries(report)["src/old.c"]
    evidence = {"kind": "source", "path": "src/old.c", "start_line": 1,
                "end_line": 1, "source_sha256": old["sha256"],
                "excerpt": OLD.decode("utf-8")}
    return {"cells": {item: {"status": "handled",
        "reason": "Software fixture validates located evidence; no device judgment.",
        "evidence": [copy.deepcopy(evidence)]} for item in check["required_items"]}}

class ProviderUnitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / "src").mkdir()
        (self.root / "src/current.c").write_bytes(b"int current(void) { return 1; }\n")
        (self.root / "src/test_current.c").write_bytes(b"int test_current(void) { return 1; }\n")
        (self.root / "src/added.c").write_bytes(b"int added(void) { return 1; }\n")
        (self.root / "outside.c").write_bytes(b"int outside(void) { return 1; }\n")
        self.provider = FixtureProvider(self.root)
    def build(self):
        return invoke(api.build_worklist, self.root, ["src/current.c"],
                      step="code", ticket_id="software-unit", attempt="a1",
                      scopes=["src"], provider=self.provider)
    def test_current_changed_deleted_and_full_scope(self):
        with patch.object(api, "_git", side_effect=AssertionError("raw Git fallback")):
            report = self.build()
        self.assertEqual("complete_within_scope", report["coverage_status"])
        files = entries(report)
        self.assertTrue({"src/current.c", "src/old.c", "src/added.c",
                         "src/test_current.c"}.issubset(files))
        self.assertEqual("deleted", files["src/old.c"]["kind"])
        self.assertEqual(hashlib.sha256(OLD).hexdigest(), files["src/old.c"]["sha256"])
        self.assertEqual(hashlib.sha256((self.root / "src/current.c").read_bytes()).hexdigest(),
                         files["src/current.c"]["sha256"])
        self.assertIn({"path": "outside.c", "reason": "out_of_scope"}, report["exclusions"])
        self.assertTrue(any(c.operation.value == "diff_names" and c.scopes == ()
                            for c in self.provider.calls))
        self.assertTrue(any(c.operation.value == "trigger_diff" for c in self.provider.calls))
    def test_rebuild_assess_deleted_evidence_and_findings(self):
        report = self.build()
        self.assertEqual("complete_within_scope", report["coverage_status"])
        reads(report)
        with patch.object(api, "_git", side_effect=AssertionError("raw Git fallback")):
            for check in report["checks"]:
                invoke(api.apply_assessment, report, self.root, check["check_id"],
                       "code_review", assessment(check, report), provider=self.provider)
            issues = invoke(api.validate_worklist, report, self.root,
                            provider=self.provider)
            self.assertEqual([], issues)
            location = {k: v for k, v in assessment(report["checks"][0], report)
                        ["cells"][report["checks"][0]["required_items"][0]]
                        ["evidence"][0].items() if k != "kind"}
            findings = [{"id": "f1", "verification_status": "confirmed",
                         "locations": [location], "evidence_boundary": "software fixture"}]
            self.assertEqual([], invoke(api.validate_findings, findings, report,
                                        self.root, provider=self.provider))
        self.assertTrue(any(c.ref == OID for c in self.provider.calls
                            if c.operation.value == "resolve_commit"))
        broken = copy.deepcopy(report)
        check = broken["checks"][0]
        item = check["required_items"][0]
        check["results"]["code_review"]["cells"][item]["evidence"][0]["excerpt"] = "wrong\n"
        self.assertTrue(invoke(api.validate_worklist, broken, self.root,
                               provider=self.provider))
        self.assertTrue(api.validate_worklist(report, self.root))
    def test_query_failures_never_complete(self):
        for fault in ("exit", "error", "truncated", "malformed_names", "non_utf8", "overflow", "bad_result"):
            with self.subTest(fault=fault):
                self.provider.fault = fault
                try:
                    report = self.build()
                except (ValueError, OSError):
                    continue
                self.assertNotEqual("complete_within_scope", report["coverage_status"])
                self.assertTrue(report["unobserved"])
    def test_nested_posix_scopes_and_scope_external_related(self):
        (self.root / "src/nested").mkdir()
        (self.root / "related/nested").mkdir(parents=True)
        for relative in ("src/nested/current.c", "related/nested/related.c",
                         "related/nested/test_related.c"):
            (self.root / relative).write_bytes(b"int value(void) { return 1; }\n")
        provider = NestedRelatedProvider(self.root)
        with patch.object(api, "_git", side_effect=AssertionError("raw Git fallback")):
            report = invoke(api.build_worklist, self.root, ["src/nested/current.c"],
                step="code", ticket_id="software-unit", attempt="a1",
                scopes=["src/nested"], related=["related/nested/related.c"],
                provider=provider)
        self.assertEqual("complete_within_scope", report["coverage_status"])
        self.assertIn("related/nested/test_related.c", entries(report))
        self.assertTrue(any(c.operation.value == "list_files" and c.kind == "association"
                            and "related/nested" in c.scopes for c in provider.calls))
        self.assertTrue(any(c.operation.value == "diff_names" and c.scopes == ("src/nested",)
                            for c in provider.calls))
        self.assertTrue(all("\\" not in scope for c in provider.calls for scope in c.scopes))
    def test_direct_result_validator_rejects_invalid_outputs(self):
        self.assertTrue(hasattr(api, "_provider_query"), "typed result validator is required")
        request = api.GitQuery(api.GitOperation.LIST_FILES, kind="others")
        for fault in ("missing_nul", "non_utf8_names", "bool_exit", "nonbool_truncated", "bad_result"):
            with self.subTest(fault=fault):
                self.provider.fault = fault
                with self.assertRaises(ValueError):
                    api._provider_query(self.root, self.provider, request, 8192)
    def test_assessment_failure_is_atomic(self):
        report = self.build()
        self.assertEqual("complete_within_scope", report["coverage_status"])
        reads(report)
        check = report["checks"][0]
        cells = assessment(check, report)
        saved = copy.deepcopy(report)
        self.provider.fault = "non_utf8"
        with self.assertRaises(ValueError):
            invoke(api.apply_assessment, report, self.root, check["check_id"],
                   "code_review", cells, provider=self.provider)
        self.assertEqual(saved, report)
    def test_workspace_nested_and_names_budget_reject(self):
        self.provider.workspace = self.root / "src"
        with self.assertRaises(ValueError):
            invoke(api.build_worklist, self.root, ["src/current.c"], step="code",
                ticket_id="software-unit", attempt="a1", scopes=["src"],
                provider=self.provider)
        self.provider.workspace = self.root
        (self.root / "src/.git").mkdir()
        with self.assertRaises(ValueError):
            self.build()
        (self.root / "src/.git").rmdir()
        with self.assertRaises(ValueError):
            invoke(api.build_worklist, self.root, ["src/current.c"], step="code",
                ticket_id="software-unit", attempt="a1", scopes=["src"],
                max_files=1, provider=self.provider)
    def test_legacy_real_git_none_is_unchanged(self):
        self.assertIsNotNone(shutil.which("git"), "fixture needs actual Git")
        def git(*args):
            return subprocess.run(["git", "-C", str(self.root), *args],
                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        git("init", "-q")
        git("config", "user.name", "Software Fixture")
        git("config", "user.email", "fixture@example.invalid")
        git("add", ".")
        git("commit", "-qm", "baseline")
        (self.root / "src/current.c").write_bytes(b"int current(void) { return 2; }\n")
        options = dict(step="code", ticket_id="legacy-unit", attempt="a1", scopes=["src"])
        old = api.build_worklist(self.root, ["src/current.c"], **options)
        explicit = invoke(api.build_worklist, self.root, ["src/current.c"],
                          provider=None, **options)
        self.assertEqual(old, explicit)
        self.assertEqual("complete_within_scope", old["coverage_status"])

if __name__ == "__main__":
    unittest.main()
```

- [ ] Step 3：运行正式 RED，只跑新 stdlib 文件，不用 unittest loader 加载 pytest 文件。

```bash
cd /home/orbbec/projects/icode-skill
python3 -m unittest discover -s tests -p test_inspection_git_provider_unit.py -v
```

Expected：current/rebuild/assessment_atomic/nested_related 四方法以 `AssertionError: complete_within_scope != partial` 失败（顺序显示可能反向）；workspace_nested_budget 为 `AssertionError: ValueError not raised`；direct_resultvalidator 为明确接口assert失败，非ImportError。query_failures/真实legacy通过。总8methods，5行为AssertionError加1接口AssertionError；不能仅拿接口失败替代5个行为RED。nested fixture在SOURCE前不会被调用，不存在未定义类型ImportError/TypeError。完整日志绑定52cb/source/test hash；若错误类别不同先修TEST，不改SOURCE。

- [ ] Step 4：TEST 作者交完整测试差异和 RED 证据给主代理；主代理冻结资产。SOURCE 作者不同，禁止降断言/改 expected/跳测试来变绿。Task 2 才允许修改 helper。

## Task 2：不同 SOURCE 作者定义 typed ABI 和有界验证

**状态**

- [ ] 任务完成

**Dependencies:** Task 1
**Parallelizable:** No (接口与消费者必须同候选提交，RED资产已冻结)

- [ ] Step 1：在 `tools/inspection_worklist.py` imports 加下面三行，`InspectionError` 后加入完整 ABI。只有五类固定 operation，不接受 argv/命令/目录/context dump。

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

class GitOperation(Enum):
    RESOLVE_COMMIT = "resolve_commit"
    DIFF_NAMES = "diff_names"
    LIST_FILES = "list_files"
    HISTORICAL_BLOB = "historical_blob"
    TRIGGER_DIFF = "trigger_diff"

@dataclass(frozen=True)
class GitQuery:
    operation: GitOperation
    ref: str = ""
    oid: str = ""
    path: str = ""
    scopes: tuple[str, ...] = ()
    kind: str = ""

@dataclass(frozen=True)
class GitQueryResult:
    data: bytes
    exit_code: int
    truncated: bool
    error: str | None = None

class InspectionGitProvider(ABC):
    workspace: Path

    @abstractmethod
    def query(self, request: GitQuery, *, limit: int) -> GitQueryResult:
        """Return bounded fixed-query bytes; this ABI grants no host authority."""

def _provider_query(root, provider, request, limit):
    if not isinstance(provider, InspectionGitProvider) or provider.workspace != root:
        raise InspectionError("provider workspace/type mismatch")
    if not isinstance(request, GitQuery) or not isinstance(request.operation, GitOperation):
        raise InspectionError("invalid typed Git query")
    if not _positive(limit) or type(request.scopes) is not tuple:
        raise InspectionError("invalid provider query budget/scopes")
    op = request.operation
    if op == GitOperation.RESOLVE_COMMIT:
        if not isinstance(request.ref, str) or not request.ref or request.ref.startswith("-"):
            raise InspectionError("invalid provider baseline")
        if request.oid or request.path or request.scopes or request.kind:
            raise InspectionError("unexpected resolve fields")
    else:
        if request.ref:
            raise InspectionError("unexpected query ref")
        if op != GitOperation.LIST_FILES and not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", request.oid):
            raise InspectionError("invalid provider commit OID")
        if op == GitOperation.LIST_FILES:
            if request.oid or request.path or request.kind not in ("others", "association"):
                raise InspectionError("invalid list_files kind/fields")
        elif op == GitOperation.DIFF_NAMES:
            if request.path or request.kind:
                raise InspectionError("unexpected diff fields")
        elif op in (GitOperation.HISTORICAL_BLOB, GitOperation.TRIGGER_DIFF):
            _path(root, request.path)
            if request.scopes or request.kind:
                raise InspectionError("unexpected content fields")
        for scope in request.scopes:
            _path(root, scope, directory=True)
    result = provider.query(request, limit=limit)
    if not isinstance(result, GitQueryResult) or type(result.data) is not bytes:
        raise InspectionError("invalid provider result type")
    if type(result.exit_code) is not int or type(result.truncated) is not bool:
        raise InspectionError("invalid provider result status")
    if result.error is not None or result.exit_code != 0 or result.truncated or len(result.data) > limit:
        raise InspectionError("provider query failed/incomplete")
    if op == GitOperation.RESOLVE_COMMIT:
        try:
            resolved = result.data.decode("ascii").strip()
        except UnicodeError as exc:
            raise InspectionError("invalid provider commit bytes") from exc
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", resolved):
            raise InspectionError("invalid provider commit output")
    elif op in (GitOperation.DIFF_NAMES, GitOperation.LIST_FILES):
        if result.data and not result.data.endswith(b"\0"):
            raise InspectionError("unterminated provider names")
        for raw in result.data.split(b"\0")[:-1]:
            try:
                _path(root, raw.decode("utf-8"))
            except UnicodeError as exc:
                raise InspectionError("nonUTF8 provider name") from exc
    return result.data, False
```

provider 不承诺 native 身份；workspace/type/output 验证只是软件合同。第一片不从不可信 caller 自动构造该对象。host v1 后续将使用此对象并另行证明权限/来源，不能称 fake provider 成功等于真实 inspection。

- [ ] Step 2：完整替换 `_repo`，保持 `None` 分支原循环行为；provider 只支持逻辑 root repo，看到 nested `.git` 拒绝，不让父仓吸收。

```python
def _repo(root, path, *, git_provider=None):
    current = (root / path).parent
    if git_provider is not None:
        if not isinstance(git_provider, InspectionGitProvider) or git_provider.workspace != root:
            raise InspectionError("provider workspace/type mismatch")
        while current == root or root in current.parents:
            if (current / ".git").exists() and current != root:
                raise InspectionError("nested repository unsupported by provider")
            if current == root:
                return root
            current = current.parent
        raise InspectionError("provider path outside workspace")
    while current == root or root in current.parents:
        if (current / ".git").exists():
            return current
        current = current.parent
    return None
```

- [ ] Step 3：Task 3 的完整传播改动同一源码候选执行；不可单独提交只定义 ABI 但无消费者的空片。

## Task 3：所有 helper Git query 和 assessment 消费者显式传播

**状态**

- [ ] 任务完成

**Dependencies:** Task 2
**Parallelizable:** No (单 helper 文件，不能多作者并发写)

- [ ] Step 1：所有相关函数定义增加 keyword-only provider，完整签名如下，其他参数及顺序原样：

```python
def _trigger_content(root, path, data, repo, baseline, max_bytes, debt, *, git_provider=None):
def _content(root, path, repo, baseline, max_bytes, *, artifact=False, git_provider=None):
def build_worklist(workspace, code_files, *, step, ticket_id, attempt, mode="full",
                   related=None, scopes=None, baselines=None, max_files=200,
                   max_bytes=1048576, git_provider=None):
def _rebuild(report, workspace, code_files=None, *, git_provider=None):
def _assessment_issues(assessment, check, report, root, required, *,
                       allow_unfinished=False, cache=None, git_provider=None):
def _checks_issues(report, expected, root, required, *, required_checks_version=None,
                   allow_unfinished=False, git_provider=None):
def apply_assessment(report, workspace, check_id, phase, assessment, *, git_provider=None):
def validate_worklist(report, workspace, *, code_files=None, step=None,
                      ticket_id=None, attempt=None, allow_incomplete=False,
                      required_checks_version=None, git_provider=None):
def validate_findings(findings, report, workspace, *, git_provider=None):
```

这些是现有函数签名替换清单，保留各函数原完整 body，下述明确变更各调用点；不是向源码写没有 body 的定义。

- [ ] Step 2：两个 content query 精确替换，当前文件读取、UTF8/binary/max_bytes 边界原样：

```python
# _trigger_content: replace only the existing _git assignment.
if git_provider is None:
    diff, cut = _git(repo, ["diff", "--no-ext-diff", "--no-textconv", "--no-renames",
                          "--unified=0", baseline, "--", f":(literal){rel}"], max_bytes)
else:
    diff, cut = _provider_query(root, git_provider,
        GitQuery(GitOperation.TRIGGER_DIFF, oid=baseline, path=rel), max_bytes)

# _content: deleted branch replaces only the existing _git assignment.
if git_provider is None:
    data, cut = _git(repo, ["show", "--no-ext-diff", "--no-textconv", f"{baseline}:{rel}"], max_bytes)
else:
    data, cut = _provider_query(root, git_provider,
        GitQuery(GitOperation.HISTORICAL_BLOB, oid=baseline, path=rel), max_bytes)
```

- [ ] Step 3：build_worklist `names` 完整替换；typed query 与 legacy args 分离，不解析/转发任意 argv。host provider outside 扫描同样要求完整，`required_scan=False` 只保留旧路径原语义。

```python
def names(repo, args, *, required_scan=True, request=None):
    label = repo.relative_to(root).as_posix()
    if git_provider is None:
        data, cut = _git(repo, args, max_files * 4096)
    else:
        data, cut = _provider_query(root, git_provider, request, max_files * 4096)
    chunks = data.split(b"\0")[:-1]
    if git_provider is not None and len(chunks) > max_files:
        raise InspectionError("provider names exceed max_files")
    if required_scan and (cut or len(chunks) > max_files):
        debt[label] = "candidate budget truncated; remaining paths unobserved"
    return [os.fsdecode(c) for c in chunks[:max_files]]
```

- [ ] Step 4：baseline 解析 `_git` assignment 精确分支替换：

```python
if git_provider is None:
    oid, cut = _git(repo, ["rev-parse", "--verify", "--end-of-options", ref + "^{commit}"])
else:
    oid, cut = _provider_query(root, git_provider,
        GitQuery(GitOperation.RESOLVE_COMMIT, ref=ref), 8192)
```

- [ ] Step 5：build_worklist 五处扫描调用完整替换；保留原 diff/local_scopes/pathspecs/association_specs 的构造供 legacy 使用：

```python
changed = set(names(repo, diff + pathspecs,
    request=GitQuery(GitOperation.DIFF_NAMES, oid=baseline, scopes=tuple(Path(s).as_posix() for s in local_scopes)))) if local_scopes else set()
untracked = set(names(repo, ["ls-files", "--others", "--exclude-standard", "-z", "--", *pathspecs],
    request=GitQuery(GitOperation.LIST_FILES, kind="others", scopes=tuple(Path(s).as_posix() for s in local_scopes)))) if local_scopes else set()
scoped = set(names(repo, ["ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", *association_specs],
    request=GitQuery(GitOperation.LIST_FILES, kind="association", scopes=tuple(Path(s).as_posix() for s in association_scopes))))
outside = set(names(repo, diff + excluded_specs, required_scan=False,
    request=GitQuery(GitOperation.DIFF_NAMES, oid=baseline))) | set(names(repo,
    ["ls-files", "--others", "--exclude-standard", "-z", "--", *excluded_specs], required_scan=False,
    request=GitQuery(GitOperation.LIST_FILES, kind="others")))
```

provider scopes `()` 表示全逻辑仓库，所有 names 操作固定排除 `.icode_output`；provider 的 typed ABI 文档/fixture和未来 host实现必须保持这个语义，不能把 `()` 理解成不扫描。association_scopes包括related父目录，其 `_repo` 判断必须带provider；送入typedquery前用Path.as_posix标准化合法Windows relpath，不改Nonelegacy原argv/pathspec。P1消费kind只有others/association，DESIGN提到tracked保留为后阶段明确扩展，不冒本片已具备。nested related fixture覆盖scope外多层目录及同stem未修改test，两个平台都必须执行。

- [ ] Step 6：精确传播所有内部调用。以下每个实际现有调用都加给出的 keyword，不作函数名反射批量替换；没有列出的消费者须静态扫描发现后补完整，不留 raw `_git` 分支可在 provider 下触达。

```python
# Every _repo occurrence in build_worklist/_assessment_issues/validate_findings:
_repo(root, p, git_provider=git_provider)
_repo(root, path, git_provider=git_provider)
_repo(root, seed, git_provider=git_provider)
# build content/trigger:
_content(root, path, repo, report["resolved_baselines"].get(label), max_bytes,
         git_provider=git_provider)
_trigger_content(root, path, data, repo, report["resolved_baselines"].get(label),
                 max_bytes, debt, git_provider=git_provider)
# _rebuild -> build (preserve original report baselines restoration):
build_worklist(workspace, report["code_files"] if code_files is None else code_files,
               baselines=pinned, git_provider=git_provider, **options)
# assessment source evidence (including deleted) / artifact evidence:
_content(root, path, repo, report["resolved_baselines"].get(label), report["max_bytes"],
         git_provider=git_provider)
_content(root, path, None, None, report["max_bytes"], artifact=True,
         git_provider=git_provider)
# _checks_issues -> _assessment_issues:
_assessment_issues(results[phase], check, report, root, required,
    allow_unfinished=allow_unfinished, cache=cache, git_provider=git_provider)
# apply_assessment -> validate and assessment:
validate_worklist(pending, workspace, allow_incomplete=True,
    required_checks_version=CHECKS_VERSION, git_provider=git_provider)
_assessment_issues(assessment, check, report, _workspace(workspace), required,
    allow_unfinished=True, git_provider=git_provider)
# validate_worklist -> rebuild/checks:
_rebuild(report, workspace, code_files, git_provider=git_provider)
_checks_issues(report, expected, _workspace(workspace), required,
    required_checks_version=required_checks_version,
    allow_unfinished=allow_incomplete and incomplete, git_provider=git_provider)
# validate_findings -> rebuild and located content:
_rebuild(report, root, git_provider=git_provider)
_content(root, path, repo, expected["resolved_baselines"].get(label),
         expected["max_bytes"], git_provider=git_provider)
```

Test fixture 前后所有 `_git` 分支被 monkeypatch 为立即 AssertionError，GREEN 因此必须真的全传播。`apply_assessment` 只有 validation 成功后写结果，不能因 provider failure 改结果。legacy artifact source separation 不变。

- [ ] Step 7：不同 SOURCE 作者交完整 helper patch（非摘录）及源码 hash给主代理；两次静态 scan确认所有调用点：

```bash
rg -n '_repo\(|_content\(|_trigger_content\(|_rebuild\(|validate_worklist\(|_checks_issues\(|_assessment_issues\(|apply_assessment\(' tools/inspection_worklist.py
rg -n '_git\(|git_provider|GitQuery\(' tools/inspection_worklist.py
```

Expected：所有 provider-aware消费者显式传递，所有 `_git` 调用只在 `git_provider is None` 分支；不得靠字符串argparser给 provider任意Git执行。CP当前未传 provider 是本片明确未开放路径，必须保持原可运行接口。

## Task 4：定点 GREEN 与 legacy，自审后独立双审

**状态**

- [ ] 任务完成

**Dependencies:** Task 3
**Parallelizable:** No (完整源码候选形成后才验证)

- [ ] Step 1：运行新 stdlib GREEN及语法检查；不修改 frozen TEST 断言。

```bash
cd /home/orbbec/projects/icode-skill
python3 -m unittest discover -s tests -p test_inspection_git_provider_unit.py -v
python3 -m py_compile tools/inspection_worklist.py tests/test_inspection_git_provider_unit.py
```

Expected：8个test methods、原7fault和新增5direct-result subtests均执行、退出0；nested fixture两个平台都执行，不skipWindows。实际计数不同或discovery空拒绝通过。真实临时Gitlegacy在其中；py_compile不代替行为。

- [ ] Step 2：静态确认旧公开调用无需provider，schema/report字段原样；SOURCE作者完成语法/依赖/逻辑/异常/关联/兼容/可运行七维报告；本片“可运行”仅helper软件和legacy。
- [ ] Step 3：fresh不同 SPEC/QUALITY审查完整candidate与冻结TEST，记录C/I/M、来源SHA和问题处置；任何必要缺陷解决后重验受影响定点，不能把新fixture仿真实现当host权限证据。

## Task 5：Skill main 候选提交与独立线上软件门

**状态**

- [ ] 任务完成

**Dependencies:** Task 4
**Parallelizable:** No (本机必要检查、双审均通过后才能推候选)

- [ ] Step 1：后续 SOURCE 作者通过apply_patch新增完整 `.github/workflows/inspection-software.yml`；没有复用假定存在的 CI：52cb 已查现docx/public-site/release workflow没有匹配inspection-only变化的软件门。

```yaml
name: Inspection helper software
on:
  push:
    branches: [main]
    paths:
      - 'tools/inspection_worklist.py'
      - 'tests/test_inspection*'
      - 'tests/test_crosscheck*'
      - 'tests/test_candidate_inspection_generations.py'
      - '.github/workflows/inspection-software.yml'
  workflow_dispatch:
permissions:
  contents: read
concurrency:
  group: inspection-software-${{ github.sha }}
  cancel-in-progress: false
jobs:
  software:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-22.04, windows-latest]
    runs-on: ${{ matrix.os }}
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262
        with:
          persist-credentials: false
      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065
        with:
          python-version: '3.10'
      - name: Record actual source and tools
        run: |
          git rev-parse HEAD
          python --version
          git --version
      - name: Install legacy test runner
        run: python -m pip install --disable-pip-version-check --no-cache-dir pytest==9.0.3
      - name: Provider stdlib software contract
        run: python -m unittest discover -s tests -p test_inspection_git_provider_unit.py -v
      - name: Syntax
        run: python -m py_compile tools/inspection_worklist.py tests/test_inspection_git_provider_unit.py
      - name: Existing inspection legacy regressions
        run: python -m pytest -p no:anyio tests/test_inspection_worklist.py tests/test_inspection_checks.py tests/test_inspection_assess_cli.py tests/test_inspection_integration.py tests/test_crosscheck.py tests/test_candidate_inspection_generations.py -q
      - name: Existing Linux shell contracts
        if: runner.os == 'Linux'
        shell: bash
        run: |
          bash tests/test_inspection_worklist_contract.sh
          bash tests/test_crosscheck_contract.sh
```

pytest pin和action SHA复用实际现public-site/docx workflow，不在本机装pytest或全量回归；线上依赖安装失败算CI失败，不当legacy通过。Windows原有合法平台skip只按其明确定义记录，不能替代Linux必要行为；新unit不能全skip。

- [ ] Step 2：主代理 read-only检查完整候选、密钥扫描（用现仓库工具而非自造声称）、diff whitespace、未归属文件；仅当前3文件加入candidate。提交前再次确认branch=main、remote current fast-forward；远端新提交时停止发布并读差异，禁止reset/rebase/force。

```bash
git status --short
git diff --check
git diff --stat
git branch --show-current
git ls-remote origin refs/heads/main
```

Expected：可归属的仅helper/test/workflow；所有证据绑定本次content hashes。当前没有新host ledger入口，不更新任何Agentpin。

- [ ] Step 3：只在主代理确认候选必要检查与双审通过后，依用户既有授权提交推Skill main；命令精确文件清单，无 `git add .`。

```bash
git add tools/inspection_worklist.py tests/test_inspection_git_provider_unit.py .github/workflows/inspection-software.yml
git commit -m "feat: add typed inspection Git provider software contract"
git push origin main
```

Expected：只向已有main fast-forward候选，不发布产品或tag；失败原样保留。这个阶段的提交不同于代码步骤每改几行commit，用户安全验收顺序优先。

- [ ] Step 4：记录实际candidateSHA、workflow/run/job两平台、完整日志和exit、任何skip；只在软件门全部必要项通过后报告“P1 helper 软件子片通过”。无需本机重复整套pytest。开始P2完整PLAN编制，不自动实现P2，也不把P1认定为S2c或整体host契约完成。

## 自审、证据边界和执行方式

SPEC映射：5类typedquery→Task2/3；Nonelegacy→Task1/4/5；全scopes/outside/trigger/deleted/assessment/findings→Task1/3；failedprovider无complete→Task1/2；不同TEST/SOURCE作者与语义RED→Task1；完整候选/不同双审/线上门→Task4/5。hostbinding/transport/objectsnapshot/Agentassess工具/安装/native矩阵都明确P2/P3另立计划，P1不对这些任务发成功声明。

类型一致性：`InspectionGitProvider.query(GitQuery, *, limit) -> GitQueryResult`、五enum值、tuple scopes、workspace Path统一；fixture仅在 SOURCE 未具备接口时走现legacy函数获得语义RED，GREEN必须typed对象并且全部provider查询绕开raw `_git`。

七维自检：计划Markdown可读；Task1–5依赖链完整；错误/超限/路径/UTF8/历史内容边界有实际assert资产；关联扫描覆盖全部helper消费者；旧None行为及真实临时Git验证明确；源码未写、未运行，不宣称编译/运行100%。QUALITY门未关闭，禁止自动调用执行技能。执行技能要求的自动handoff被用户PLAN-only/SOURCE冻结约束覆盖。

本次修订 PLAN QA 已只读重建文末完整patch到Python内存：全部old/context行精确匹配实际52cb helper，所有hunk old/new计数匹配，重建AST成功；AST枚举全部 `_repo` 调用均显式传provider，遗漏related调用已关闭。嵌入完整TEST AST成功且实际8methods；nested POSIX scopes规范化与5项directresult负控资产已加入。未创建SOURCE/TEST/CI文件，未执行RED/GREEN或候选实现；语义执行证据必须由Task1/4实际产生，不拿语法QA替代。

---
**Execution Mode:** serial


## 完整 SOURCE 候选补丁资产（仅计划文本）

以下补丁针对实际52cb基线，可供不同 SOURCE 作者用 apply_patch逐hunk落实；它是Task2/3全部改动的完整候选，不允许只实施前述摘录。没有额外类型模块或importlib sys.path假设，沿现spec_from_file_location直接加载的测试模式；不加future annotations，避免未注册sys.modules的dataclass解析失败。SOURCE作者仍须完整阅读基线、核对冲突和独立GREEN，不把这份计划代码当已实施证据。

```diff
--- a/tools/inspection_worklist.py
+++ b/tools/inspection_worklist.py
@@ -14,6 +14,9 @@
 import stat
 import subprocess
 import time
+from abc import ABC, abstractmethod
+from dataclasses import dataclass
+from enum import Enum
 from queue import Empty, Full, Queue
 from threading import Event, Thread

@@ -54,6 +57,91 @@
     """Invalid input or an unsafe/inaccessible inspection boundary."""


+class GitOperation(Enum):
+    RESOLVE_COMMIT = "resolve_commit"
+    DIFF_NAMES = "diff_names"
+    LIST_FILES = "list_files"
+    HISTORICAL_BLOB = "historical_blob"
+    TRIGGER_DIFF = "trigger_diff"
+
+@dataclass(frozen=True)
+class GitQuery:
+    operation: GitOperation
+    ref: str = ""
+    oid: str = ""
+    path: str = ""
+    scopes: tuple[str, ...] = ()
+    kind: str = ""
+
+@dataclass(frozen=True)
+class GitQueryResult:
+    data: bytes
+    exit_code: int
+    truncated: bool
+    error: str | None = None
+
+class InspectionGitProvider(ABC):
+    workspace: Path
+
+    @abstractmethod
+    def query(self, request: GitQuery, *, limit: int) -> GitQueryResult:
+        """Return bounded fixed-query bytes; this ABI grants no host authority."""
+
+def _provider_query(root, provider, request, limit):
+    if not isinstance(provider, InspectionGitProvider) or provider.workspace != root:
+        raise InspectionError("provider workspace/type mismatch")
+    if not isinstance(request, GitQuery) or not isinstance(request.operation, GitOperation):
+        raise InspectionError("invalid typed Git query")
+    if not _positive(limit) or type(request.scopes) is not tuple:
+        raise InspectionError("invalid provider query budget/scopes")
+    op = request.operation
+    if op == GitOperation.RESOLVE_COMMIT:
+        if not isinstance(request.ref, str) or not request.ref or request.ref.startswith("-"):
+            raise InspectionError("invalid provider baseline")
+        if request.oid or request.path or request.scopes or request.kind:
+            raise InspectionError("unexpected resolve fields")
+    else:
+        if request.ref:
+            raise InspectionError("unexpected query ref")
+        if op != GitOperation.LIST_FILES and not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", request.oid):
+            raise InspectionError("invalid provider commit OID")
+        if op == GitOperation.LIST_FILES:
+            if request.oid or request.path or request.kind not in ("others", "association"):
+                raise InspectionError("invalid list_files kind/fields")
+        elif op == GitOperation.DIFF_NAMES:
+            if request.path or request.kind:
+                raise InspectionError("unexpected diff fields")
+        elif op in (GitOperation.HISTORICAL_BLOB, GitOperation.TRIGGER_DIFF):
+            _path(root, request.path)
+            if request.scopes or request.kind:
+                raise InspectionError("unexpected content fields")
+        for scope in request.scopes:
+            _path(root, scope, directory=True)
+    result = provider.query(request, limit=limit)
+    if not isinstance(result, GitQueryResult) or type(result.data) is not bytes:
+        raise InspectionError("invalid provider result type")
+    if type(result.exit_code) is not int or type(result.truncated) is not bool:
+        raise InspectionError("invalid provider result status")
+    if result.error is not None or result.exit_code != 0 or result.truncated or len(result.data) > limit:
+        raise InspectionError("provider query failed/incomplete")
+    if op == GitOperation.RESOLVE_COMMIT:
+        try:
+            resolved = result.data.decode("ascii").strip()
+        except UnicodeError as exc:
+            raise InspectionError("invalid provider commit bytes") from exc
+        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", resolved):
+            raise InspectionError("invalid provider commit output")
+    elif op in (GitOperation.DIFF_NAMES, GitOperation.LIST_FILES):
+        if result.data and not result.data.endswith(b"\0"):
+            raise InspectionError("unterminated provider names")
+        for raw in result.data.split(b"\0")[:-1]:
+            try:
+                _path(root, raw.decode("utf-8"))
+            except UnicodeError as exc:
+                raise InspectionError("nonUTF8 provider name") from exc
+    return result.data, False
+
+
 def _positive(value):
     return type(value) is int and value > 0

@@ -216,8 +304,18 @@
         raise InspectionError(f"git unavailable/timeout: {exc}") from exc


+def _repo(root, path, *, git_provider=None):
-def _repo(root, path):
     current = (root / path).parent
+    if git_provider is not None:
+        if not isinstance(git_provider, InspectionGitProvider) or git_provider.workspace != root:
+            raise InspectionError("provider workspace/type mismatch")
+        while current == root or root in current.parents:
+            if (current / ".git").exists() and current != root:
+                raise InspectionError("nested repository unsupported by provider")
+            if current == root:
+                return root
+            current = current.parent
+        raise InspectionError("provider path outside workspace")
     while current == root or root in current.parents:
         if (current / ".git").exists():
             return current
@@ -248,15 +346,19 @@
     return [{key: c.get(key) for key in CHECK_IDENTITY_KEYS} for c in checks]


+def _trigger_content(root, path, data, repo, baseline, max_bytes, debt, *, git_provider=None):
-def _trigger_content(root, path, data, repo, baseline, max_bytes, debt):
     text = data.decode("utf-8")
     if repo is not None and baseline is not None:
         # Only removed lines supplement current source. A removed clock/cast
         # must retain its prompt, without importing unrelated historical code.
         rel = (root / path).relative_to(repo).as_posix()
         try:
+            if git_provider is None:
+                diff, cut = _git(repo, ["diff", "--no-ext-diff", "--no-textconv", "--no-renames",
+                    "--unified=0", baseline, "--", f":(literal){rel}"], max_bytes)
+            else:
+                diff, cut = _provider_query(root, git_provider,
+                    GitQuery(GitOperation.TRIGGER_DIFF, oid=baseline, path=rel), max_bytes)
-            diff, cut = _git(repo, ["diff", "--no-ext-diff", "--no-textconv", "--no-renames",
-                "--unified=0", baseline, "--", f":(literal){rel}"], max_bytes)
             text += "\n" + "\n".join(line[1:] for line in diff.decode("utf-8").splitlines()
                                     if line.startswith("-") and not line.startswith("---"))
             if cut:
@@ -279,7 +381,7 @@
     return checks


+def _content(root, path, repo, baseline, max_bytes, *, artifact=False, git_provider=None):
-def _content(root, path, repo, baseline, max_bytes, *, artifact=False):
     target = root / _path(root, path, artifact=artifact)
     if target.exists():
         if not stat.S_ISREG(target.stat().st_mode):
@@ -291,7 +393,11 @@
         if repo is None or baseline is None:
             raise InspectionError("missing historical baseline content")
         rel = target.relative_to(repo).as_posix()
+        if git_provider is None:
+            data, cut = _git(repo, ["show", "--no-ext-diff", "--no-textconv", f"{baseline}:{rel}"], max_bytes)
+        else:
+            data, cut = _provider_query(root, git_provider,
+                GitQuery(GitOperation.HISTORICAL_BLOB, oid=baseline, path=rel), max_bytes)
-        data, cut = _git(repo, ["show", "--no-ext-diff", "--no-textconv", f"{baseline}:{rel}"], max_bytes)
         if cut:
             raise InspectionError("historical content exceeds max_bytes")
         kind = "deleted"
@@ -308,7 +414,7 @@

 def build_worklist(workspace, code_files, *, step, ticket_id, attempt, mode="full",
                    related=None, scopes=None, baselines=None, max_files=200,
+                   max_bytes=1048576, git_provider=None):
-                   max_bytes=1048576):
     root = _workspace(workspace)
     if not isinstance(step, str) or step not in PHASES or mode not in ("full", "fast"):
         raise InspectionError("invalid step/mode")
@@ -336,14 +442,19 @@
     required = {p: "code_files" for p in seeds}
     for p in related:
         required.setdefault(p, "explicit_related")
+    repos = sorted({r for p in seeds + related for r in [_repo(root, p, git_provider=git_provider)] if r is not None})
-    repos = sorted({r for p in seeds + related for r in [_repo(root, p)] if r is not None})
     if set(baselines) - {r.relative_to(root).as_posix() for r in repos}:
         raise InspectionError("baseline key is not an affected repository")

+    def names(repo, args, *, required_scan=True, request=None):
-    def names(repo, args, *, required_scan=True):
         label = repo.relative_to(root).as_posix()
+        if git_provider is None:
+            data, cut = _git(repo, args, max_files * 4096)
+        else:
+            data, cut = _provider_query(root, git_provider, request, max_files * 4096)
+        chunks = data.split(b"\0")[:-1]
+        if git_provider is not None and len(chunks) > max_files:
+            raise InspectionError("provider names exceed max_files")
-        data, cut = _git(repo, args, max_files * 4096)
-        chunks = data.split(b"\0")[:-1]  # Ignore any truncated terminal filename.
         if required_scan and (cut or len(chunks) > max_files):
             debt[label] = "candidate budget truncated; remaining paths unobserved"
         return [os.fsdecode(c) for c in chunks[:max_files]]
@@ -355,7 +466,11 @@
         if not isinstance(ref, str) or not ref or ref.startswith("-"):
             raise InspectionError(f"invalid baseline: {label}")
         try:
+            if git_provider is None:
+                oid, cut = _git(repo, ["rev-parse", "--verify", "--end-of-options", ref + "^{commit}"])
+            else:
+                oid, cut = _provider_query(root, git_provider,
+                    GitQuery(GitOperation.RESOLVE_COMMIT, ref=ref), 8192)
-            oid, cut = _git(repo, ["rev-parse", "--verify", "--end-of-options", ref + "^{commit}"])
             if cut:
                 raise InspectionError("baseline output truncated")
         except InspectionError as exc:
@@ -369,14 +484,19 @@
         # of enumeration itself (not merely filtered after consuming budgets).
         excluded_specs = [":(glob,exclude)**/.icode_output/**"]
         pathspecs = [f":(literal){s}" for s in local_scopes] + excluded_specs
+        changed = set(names(repo, diff + pathspecs,
+            request=GitQuery(GitOperation.DIFF_NAMES, oid=baseline, scopes=tuple(Path(s).as_posix() for s in local_scopes)))) if local_scopes else set()
+        untracked = set(names(repo, ["ls-files", "--others", "--exclude-standard", "-z", "--", *pathspecs],
+            request=GitQuery(GitOperation.LIST_FILES, kind="others", scopes=tuple(Path(s).as_posix() for s in local_scopes)))) if local_scopes else set()
-        changed = set(names(repo, diff + pathspecs)) if local_scopes else set()
-        untracked = set(names(repo, ["ls-files", "--others", "--exclude-standard", "-z", "--", *pathspecs])) if local_scopes else set()
         association_scopes = sorted(set(local_scopes) | {os.path.relpath((root / p).parent, repo)
-            for p in related if _repo(root, p) == repo})
+            for p in related if _repo(root, p, git_provider=git_provider) == repo})
         association_specs = [f":(literal){s}" for s in association_scopes] + excluded_specs
+        scoped = set(names(repo, ["ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", *association_specs],
+            request=GitQuery(GitOperation.LIST_FILES, kind="association", scopes=tuple(Path(s).as_posix() for s in association_scopes))))
+        outside = set(names(repo, diff + excluded_specs, required_scan=False,
+            request=GitQuery(GitOperation.DIFF_NAMES, oid=baseline))) | set(names(repo,
+            ["ls-files", "--others", "--exclude-standard", "-z", "--", *excluded_specs], required_scan=False,
+            request=GitQuery(GitOperation.LIST_FILES, kind="others")))
-        scoped = set(names(repo, ["ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", *association_specs]))
-        outside = set(names(repo, diff + excluded_specs, required_scan=False)) | set(names(repo,
-            ["ls-files", "--others", "--exclude-standard", "-z", "--", *excluded_specs], required_scan=False))
         for local in sorted(changed | untracked | scoped | outside):
             path = (repo / local).relative_to(root).as_posix()
             # Ticket sidecars are never source candidates. Their normal growth
@@ -401,14 +521,14 @@
                 if local in changed | untracked:
                     debt[path] = str(exc)
                 continue
+            if _repo(root, path, git_provider=git_provider) != repo:  # Never absorb a nested repository through its parent.
-            if _repo(root, path) != repo:  # Never absorb a nested repository through its parent.
                 excluded[path] = "different_repository"
                 continue
             candidates.add(path)
             if local in changed | untracked:
                 required.setdefault(path, "git_change")
     for seed in seeds + related:
+        if _repo(root, seed, git_provider=git_provider) is None:
-        if _repo(root, seed) is None:
             debt[seed] = "no affected Git repository; diff/association coverage unavailable"
             parent = (root / seed).parent
             try:
@@ -431,7 +551,7 @@
             except OSError as exc:
                 debt[seed] = f"no Git; association directory unreadable: {exc}"
         for path in sorted(candidates):
+            if Path(path).suffix.lower() in ASSOCIATED_SUFFIXES and _stem(path) == _stem(seed) and _repo(root, path, git_provider=git_provider) == _repo(root, seed, git_provider=git_provider):
-            if Path(path).suffix.lower() in ASSOCIATED_SUFFIXES and _stem(path) == _stem(seed) and _repo(root, path) == _repo(root, seed):
                 required.setdefault(path, "same_stem_or_test")
     groups, source_groups = {}, {}
     ordered = seeds + sorted(set(required) - set(seeds))
@@ -439,16 +559,16 @@
         if index >= max_files:
             debt[path] = "required file exceeds max_files budget"
             continue
+        repo = _repo(root, path, git_provider=git_provider)
-        repo = _repo(root, path)
         label = repo.relative_to(root).as_posix() if repo else None
         try:
+            data, kind = _content(root, path, repo, report["resolved_baselines"].get(label), max_bytes, git_provider=git_provider)
-            data, kind = _content(root, path, repo, report["resolved_baselines"].get(label), max_bytes)
         except (InspectionError, OSError) as exc:
             debt[path] = str(exc)
             continue
         groups.setdefault((label, _stem(path)), []).append(dict(path=path, sha256=hashlib.sha256(data).hexdigest(), kind=kind, reason=required[path], rules=_rules(path), reads={}))
         if Path(path).suffix.lower() in SOURCE_SUFFIXES:
+            text = _trigger_content(root, path, data, repo, report["resolved_baselines"].get(label), max_bytes, debt, git_provider=git_provider)
-            text = _trigger_content(root, path, data, repo, report["resolved_baselines"].get(label), max_bytes, debt)
             kinds = set()
             if TIMESTAMP_SIGNAL.search(text) or INTEGER_CONVERSION.search(text):
                 kinds.add("timestamp_contract")
@@ -467,7 +587,7 @@
     return report


+def _rebuild(report, workspace, code_files=None, *, git_provider=None):
-def _rebuild(report, workspace, code_files=None):
     if not isinstance(report, dict):
         raise InspectionError("report must be an object")
     keys = ("code_files", "step", "ticket_id", "attempt", "mode", "related", "scopes", "baselines", "max_files", "max_bytes")
@@ -483,7 +603,7 @@
     # symbolic branch/tag. No fallback to a different HEAD is permitted.
     options = {k: report[k] for k in keys if k not in ("code_files", "baselines")}
     expected = build_worklist(workspace, report["code_files"] if code_files is None else code_files,
+                              baselines=pinned, git_provider=git_provider, **options)
-                              baselines=pinned, **options)
     expected["baselines"] = report["baselines"]
     return expected

@@ -502,7 +622,7 @@
     return result


+def _assessment_issues(assessment, check, report, root, required, *, allow_unfinished=False, cache=None, git_provider=None):
-def _assessment_issues(assessment, check, report, root, required, *, allow_unfinished=False, cache=None):
     """Validate each explicit cell and its source/artifact evidence without executing tests."""
     if not isinstance(assessment, dict) or set(assessment) != {"cells"} or not isinstance(assessment["cells"], dict):
         return ["assessment must contain only cells"]
@@ -536,9 +656,9 @@
                     if set(ref) != fields or path not in check["paths"] or path not in required:
                         raise InspectionError("source evidence must locate a current check member")
                     if (kind, path) not in cache:
+                        repo = _repo(root, path, git_provider=git_provider)
-                        repo = _repo(root, path)
                         label = repo.relative_to(root).as_posix() if repo else None
+                        data, _ = _content(root, path, repo, report["resolved_baselines"].get(label), report["max_bytes"], git_provider=git_provider)
-                        data, _ = _content(root, path, repo, report["resolved_baselines"].get(label), report["max_bytes"])
                         cache[kind, path] = (hashlib.sha256(data).hexdigest(), data.decode("utf-8").splitlines(keepends=True))
                     digest, lines = cache[kind, path]
                     start, end = ref["start_line"], ref["end_line"]
@@ -554,7 +674,7 @@
                     if not isinstance(ref["evidence_boundary"], str) or not ref["evidence_boundary"].strip():
                         raise InspectionError("artifact evidence requires a nonempty boundary")
                     if (kind, path) not in cache:
+                        data, _ = _content(root, path, None, None, report["max_bytes"], artifact=True, git_provider=git_provider)
-                        data, _ = _content(root, path, None, None, report["max_bytes"], artifact=True)
                         cache[kind, path] = hashlib.sha256(data).hexdigest()
                     if ref["sha256"] != cache[kind, path]:
                         raise InspectionError("artifact evidence hash drift")
@@ -565,7 +685,7 @@
     return issues


+def _checks_issues(report, expected, root, required, *, required_checks_version=None, allow_unfinished=False, git_provider=None):
-def _checks_issues(report, expected, root, required, *, required_checks_version=None, allow_unfinished=False):
     if required_checks_version is not None and (type(required_checks_version) is not int or required_checks_version != CHECKS_VERSION):
         return ["unsupported required_checks_version"]
     present = "checks_version" in report or "checks" in report
@@ -592,11 +712,11 @@
                     issues.append(f"missing assessment: {check['kind']}:{phase}")
                 continue
             issues.extend(f"{check['kind']}:{phase}:{issue}" for issue in _assessment_issues(
+                results[phase], check, report, root, required, allow_unfinished=allow_unfinished, cache=cache, git_provider=git_provider))
-                results[phase], check, report, root, required, allow_unfinished=allow_unfinished, cache=cache))
     return issues


+def apply_assessment(report, workspace, check_id, phase, assessment, *, git_provider=None):
-def apply_assessment(report, workspace, check_id, phase, assessment):
     """Record one complete, independently assessed phase after its actual Read.

     This shared API mutates only after successful validation. Callers retain
@@ -604,7 +724,7 @@
     Neither a handled record nor a lexical trigger proves semantic correctness.
     """
     pending = dict(report, coverage_status="partial", debt_reason="pending assessment")
+    issues = validate_worklist(pending, workspace, allow_incomplete=True, required_checks_version=CHECKS_VERSION, git_provider=git_provider)
-    issues = validate_worklist(pending, workspace, allow_incomplete=True, required_checks_version=CHECKS_VERSION)
     if issues:
         raise InspectionError(str(issues))
     selected = [c for c in report["checks"] if c["check_id"] == check_id]
@@ -614,7 +734,7 @@
     required = _flatten(report)
     if any(required[path]["reads"].get(phase) != required[path]["sha256"] for path in check["paths"]):
         raise InspectionError("assessment requires current Read for every check member in this phase")
+    issues = _assessment_issues(assessment, check, report, _workspace(workspace), required, allow_unfinished=True, git_provider=git_provider)
-    issues = _assessment_issues(assessment, check, report, _workspace(workspace), required, allow_unfinished=True)
     if issues:
         raise InspectionError(str(issues))
     check["results"][phase] = copy.deepcopy(assessment)
@@ -622,9 +742,9 @@


 def validate_worklist(report, workspace, *, code_files=None, step=None,
+                      ticket_id=None, attempt=None, allow_incomplete=False, required_checks_version=None, git_provider=None):
-                      ticket_id=None, attempt=None, allow_incomplete=False, required_checks_version=None):
     try:
+        expected = _rebuild(report, workspace, code_files, git_provider=git_provider)
-        expected = _rebuild(report, workspace, code_files)
         actual, required = _flatten(report), _flatten(expected)
         issues = []
         for key in ("schema_version", "workspace", "step", "ticket_id", "attempt", "mode", "required_phases", "code_files", "related", "scopes", "baselines", "resolved_baselines", "max_files", "max_bytes"):
@@ -660,7 +780,7 @@
         if status != "complete_within_scope" and not (allow_incomplete and incomplete):
             issues.append("inspection incomplete without accepted explicit debt")
         issues.extend(_checks_issues(report, expected, _workspace(workspace), required,
+            required_checks_version=required_checks_version, allow_unfinished=allow_incomplete and incomplete, git_provider=git_provider))
-            required_checks_version=required_checks_version, allow_unfinished=allow_incomplete and incomplete))
         debt_paths = {d["path"] for d in unobserved}
         for path in sorted(set(actual) & set(required)):
             f, target = actual[path], required[path]
@@ -684,10 +804,10 @@
         return [f"invalid worklist: {exc}"]


+def validate_findings(findings, report, workspace, *, git_provider=None):
-def validate_findings(findings, report, workspace):
     try:
         root = _workspace(workspace)
+        expected = _rebuild(report, root, git_provider=git_provider)
-        expected = _rebuild(report, root)
         actual, required = _flatten(report), _flatten(expected)
         if report.get("workspace") != str(root) or set(actual) != set(required):
             raise InspectionError("finding worklist scope/workspace drift")
@@ -730,9 +850,9 @@
                     start, end = loc["start_line"], loc["end_line"]
                     if not _positive(start) or not _positive(end) or end < start:
                         raise InspectionError("invalid 1-based line range")
+                    repo = _repo(root, path, git_provider=git_provider)
-                    repo = _repo(root, path)
                     label = repo.relative_to(root).as_posix() if repo else None
+                    data, _ = _content(root, path, repo, expected["resolved_baselines"].get(label), expected["max_bytes"], git_provider=git_provider)
-                    data, _ = _content(root, path, repo, expected["resolved_baselines"].get(label), expected["max_bytes"])
                     if loc["source_sha256"] != hashlib.sha256(data).hexdigest():
                         raise InspectionError("source_sha256 drift")
                     lines = data.decode("utf-8").splitlines(keepends=True)
```


复杂跨消费者单文件传播需要context isolation；TEST、SOURCE、SPEC、QUALITY作者分离，Task1→2→3→4→5是串行依赖链。本次只提交计划供独立审查，不执行。

## 执行记录（2026-10-14，软件候选，非 R2/R3 通过）

冻结计划原 SHA256 为 `038931d3af0c4f1a3b4a795caf75b661260bb09a13e00ba4e398ac1b42a7040e`；实际实施只涉及 Skill 的 helper、独立单元测试和软件 CI 三个文件。root 已实际完成源码全文阅读；复杂修改前实际 sequential-thinking 三步记录 `dcee2d`。TEST 与 SOURCE 作者分离，实际源码经 fresh 独立 SPEC 与另一 QUALITY 均 C0/I0/M0。

原 8 方法测试在旧源码上实际 RED（6 assertion failure、0 error/skip），原计划实现后 Linux 与 Windows 实际 GREEN。源码自审随后发现未使用字段的假值类型可绕过检查，追加 14 行测试覆盖 4 字段×7 假值类型；root 实测旧实现新增 28 assertion failure，旧 8 方法仍通过。另一个源码作者只增加 3 行字符串字段类型校验，没有删减原断言。最终 9 方法 Linux 0.115s、Windows 1.796s，均 0 failure/error/skip，退出 0；语法编译与 diff-check 通过。

候选内容 SHA256：helper `c7ad6c9ab55c8f8f2446dcc9f8e6fc54583925caa2d94fd1dcb047bfc863a3aa`；TEST `1efaab01c9870faf7b1faef6c3cc7ce4b0471273465254b701e6991b97737bc0`；CI `5fd95bcde20a7f34d0d2e8e1065a5cbfc126ea22d357ec94c24ccec158e4da14`。复用 Agent preflight 的密钥扫描规则，仅扫描这三个交付文件，命中 0；这不是 Skill 全仓扫描或新契约的宿主安全证明。

Task 1–4 的本地针对性实施与源码审查已有上述证据。Task 5 仍待精确提交 SHA 的线上 Linux/Windows 旧契约回归与 Linux shell 合同；尚未提交/推送时不得报告线上通过。该片仅提供程序化 typed provider API，不新增 CP CLI、宿主绑定或 Agent 固定版本，不证明真实隔离链、原生安全或 R2/R3 完整验收。

实际候选 `4d9b07616f3f8c7e3d39e73b6da3494b44799392` 已提交（3b5303）并推送 Skill main（d51938），父 `52cb6b3`；仅三个路径，索引字节与候选摘要逐项一致、均 100644。[软件 CI38441664572](https://github.com/ayukyo/icode-skill/actions/runs/38441664572) 已真实触发，Ubuntu job115449521529 / Windows job115449521129 在旧回归中；新 provider 与 syntax 步成功，终态及完整旧回归证据待收，不借此关闭 Task 5。

同SHA双软件job现已真实终态 failure。Linux原日志：162旧Python测试 /69.90s通过、inspection shell通过；crosscheck shell缺`rg`，RESULT2pass/15fail、exit1。Windows原日志：旧回归74fail/88pass /176.44s，涉及excerpt字节漂移、cp1252、清空子env随机数初始化和execution binding路径；新provider/语法仍通过。root仅在新workflow补Linux条件安装ripgrep5行，未改旧合同或产品，Windows分类须独立诊断后形成最小修复，不称P1验收已过。上述在途描述保留历史观察点，Task5仍开放。

文档入索引后 diff-check 真实拦截内嵌 SOURCE diff 的26个单空格上下文行。仅把这些文档表示改为空行；重建原统一diff时，hunk中的空行恢复为单空格 context prefix即可。root逐字核仅26处空白替换，没有改变加/减行、TEST/CI或实际Skill源码；原批准与执行用补丁摘要保留历史，不把新文档字节当原038摘要。第一次计数诊断因相邻行的非重叠匹配假设失败，改逐行精确计数后通过，不当产品失败或绕过检查。
