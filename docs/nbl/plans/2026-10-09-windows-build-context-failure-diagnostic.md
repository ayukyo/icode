# Windows Build Context Failure Diagnostic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development (recommended) or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Windows 构建上下文受捕获拒绝在保留泛错误和 exit1 的同时，尽力增加只含闭集 stage/kind 的失败诊断。

**Architecture:** 每次 main 新建仅持有一个 stage 字符串的私有观察对象，probe 增加默认 None 的私有 keyword-only 参数。保持旧两个位置参数、业务求值顺序、返回值、异常 identity、单次有界查询以及成功两行；只在原 main 捕获范围内输出失败分类。一个新作者改两个源文件，fresh SPEC 与不同 QUALITY 串行审查，root 验证后按既有授权发布并独立观察新 SHA。

**Tech Stack:** Python 3.11 unittest、现有 icode.runner 错误类型/有界 runner、固定 JSON/XML fixture、既有 GitHub Windows provenance 工作流。

---

## 入口、冻结与权限

请求路径与实际 Git root 均为 `/home/orbbec/git/icode`；main 源码基线 `d365e6f15d2d1a223ec60ba18310647c338f4eba`，vendor gitlink `1693651c1bd7daad3272eb054f0f81d6f254d08d`。冻结设计 [failure design](../specs/2026-10-09-windows-build-context-failure-design.md) SHA256 `ca76a993b0fbfc40fe78e80070f373c11dbd951ef76e50d688cbc1207e748ecc`，设计已由独立 SPEC 与不同 QUALITY 以 C0/I0/M0 冻结。计划作者没有实施代码、执行样例或测试、提交或推送。

用户已明确持续自主开发、root 决定阶段、mainonly；这取代技能默认 worktree、逐阶段 userwait，不取消独立双审或验证门。计划作者完成后 STOP，不自动调用执行技能或再派子代理；root fresh 计划 SPEC→不同 QUALITY 通过后才派实施。所有源代码示例都是待实施内容；本计划检查仅允许 AST parse，不 exec，不把代码写入 source。

真实问题、已有实现、调用链均已核：118a 原 Windows 窗口只有泛错误，不能定性 timeout；现有 probe 已严格校验、一次 property-only 查询和 30秒/16384字节限制。调用链为 workflow→main→probe→既有 bounded runner；PE capture 的 `_probe_context(build_directory, architecture)` 仍用两个位置参数，不能改其 ABI。已核现有 DEFAULT 选择完整 `TestWindowsBuildContext` class 与配对 no-skip 守卫，不需新增选择。

结构化思考记录：需求分解为受捕获失败类别/位置与旧合同；方案是每次显式 observer 而非 ContextVar；风险是观察故障遮蔽业务、旧 stage 残留、foreign 属性访问、文本泄漏和输出重试，以精确类型/单 slot/闭标签/普通故障隔离控制。独立研究与 root 已核 [固定 Codex 2c3156a](../specs/2026-10-09-windows-build-context-rejection-research.md) 和 [持续对照](../../agent-landscape-live.md)：采纳类型类别与 payload 分离及敏感哨兵测试；暂缓生产 runner 遥测；不适配公开 message/path/错误字符串解析。固定 Apache-2.0 源码机制借鉴，无代码复制、新依赖、权限或部署，不刷新全部20上游。

## 文件职责与验收映射

| 文件 | 责任和修改边界 |
| --- | --- |
| `scripts/probe_windows_build_context.py` | 只增加私有闭集观察/分类/输出 helper，替换整个 probe 和 main；原读取/解析 helper 不改 |
| `tests/test_windows_build_context.py` | 复用现有 fixture，在已有 portable class 内加方法/辅助，逐字修改原失败 golden；HostCMake 不改 |
| 本新计划与冻结新设计 | 设计合同、可实施静态代码和实际验收履历；冻结设计正文不得重写 |
| root 历史 reader plan、研究与 landscape | root 维护阶段收尾与证据；作者不能编辑，发布前 root 精确列路径 |

不改 DEFAULT、workflow、capture、vendor、src、native、依赖、预算、生产准入或签名权限。

| 设计要求 | 实现位置 | 具名测试/验证 |
| --- | --- | --- |
| 12 stage / 10 kind 与继承优先级 | `_STAGES`、`_FAILURE_KINDS`、标记点、分类器 | `test_diagnostic_real_stage_rejections_and_query_counts`、`test_diagnostic_kind_priority_and_unavailable` |
| 只有一个 stage / 精确类型 / 隔离恢复 | `_ProbeDiagnostic`、`_mark_diagnostic_stage`、`_get_diagnostic_stage` | foreign、single_slot、marker_fault、get_stage_fault 三类方法 |
| 原求值/副作用/2参/identity | probe 顺序保持，仅拆嵌套读/解析 | old_two_arguments、exact_side_effects、runner_identity；原双架构 runner bounds 方法 |
| 闭四字段精确类型 / ASCII / 256bytes / 无 payload | `_rejection_line`、一次 `sys.stdout.write` | closed_payload、poison、malformed_line、serialization_and_write_fault |
| 普通诊断故障不遮蔽 / fatal不吞 | factory/marker/get-stage/分类/输出局部保护 | factory_fault、marker_fault、get_stage_fault、kind_fault、fatal、generic_write_fault |
| 成功原两行与失败原首行 | main | 原 golden 修改、two_architectures_main_golden |
| CLI 原2flags、错误2/noprobe、DEFAULT无skip | 原 parser 不变 | cli_errors、既有选择守卫、20轮关键class |
| 软件门与新SHA原生信用分离 | Task2→Task3 | actual counts、原三道 preflight、新SHA四格/API/artifact观察 |

## 环境：所有实施命令串行、低负载

以下环境前缀每个 shell 会话先执行一次；不借 PATH 改产品权限：

```bash
export PATH=/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin:/tmp/icode-sigstore-go-gwCdn3/go/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PYTHONPATH=src:.
export PYTHONDONTWRITEBYTECODE=1
export GOMAXPROCS=1
export GOFLAGS=-p=1
export GOTOOLCHAIN=local
export CMAKE_BUILD_PARALLEL_LEVEL=1
cd /home/orbbec/git/icode
test -x /tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python
test -x /tmp/icode-sigstore-go-gwCdn3/go/bin/go
/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python --version
/tmp/icode-sigstore-go-gwCdn3/go/bin/go version
git branch --show-current
git status --short
sha256sum docs/nbl/specs/2026-10-09-windows-build-context-failure-design.md
```

Expected：两个test-x均0，Python3.11.15、Go1.27.1、main、冻结 SHA 对应；正确可执行文件是venv/bin/python，版本号不作为文件名。计划路径修正时仅实际执行上述test-x和两个version命令，得到Python 3.11.15与go1.27.1，未运行测试/样例。旧 reader plan dirty 属 root，保留。若基线漂移，先回读差异和调用链，不覆盖用户变化。每 step 是一次约2–5分钟动作；长验证命令启动是一个 step，持续运行时每60秒内汇报，完成读取结果再进入下一步，不以时长预测替代通过记录。

### Task 1: 一个新作者对两源完成真实 TDD 与自审

**状态**
- [x] 任务完成（两源冻结；仅 portable 实现范围）

**Dependencies:** None
**Parallelizable:** No (同一作者完整掌握两源合同；后续审查只能读冻结实现)

作者范围仅两源；禁止修改本计划、设计、研究、历史计划或 landscape，禁止提交/推送。任何需要扩大源码范围的发现回 root，不能绕开门。

- [x] **Step 1: 回读两个源文件全部内容及旧调用，记录现存合同。**

```bash
git diff -- scripts/probe_windows_build_context.py tests/test_windows_build_context.py
sed -n '1,260p' scripts/probe_windows_build_context.py
sed -n '1,480p' tests/test_windows_build_context.py
sed -n '85,118p' src/icode/runner.py
rg -n '_probe_context|probe_windows_build_context|TestWindowsBuildContext' scripts/probe_windows_pe_capture.py scripts/run_workspace_ci.py tests/test_run_workspace_ci.py
```

Expected：复用现有 `VerificationOutputCaptureError`、`VerificationOutputLimitError`，不用新异常类；query旧 argv、cwd、env快照、30/16384、一调用，三个工具目录 lstat 顺序不变。现有 source183/test403 是计划编写时读数，实施以实际全读为准。

- [x] **Step 2: 使用 apply_patch 在测试 imports 增加 ExitStack，并加入下列完整辅助与测试。**

将 `from contextlib import redirect_stdout` 精确替换为：

```python
from contextlib import ExitStack, redirect_stdout
```

在 `TestWindowsBuildContext` 内、`TestWindowsBuildContextHostCMake` 之前加入以下全部内容，保持四空格缩进；helper 复用 `write_context/xml/result/windows_lstat`，真实 JSON/XML/Properties 语义不 mock 成成功。新增方法不添加 skip/decorator，不另造 class，DEFAULT 自动选择全部。

```python
    def diagnostic_api(self):
        api = self.api()
        for name in ("probe", "main", "_ProbeDiagnostic", "_new_diagnostic",
                     "_set_diagnostic_stage", "_mark_diagnostic_stage", "_get_diagnostic_stage",
                     "_failure_kind", "_rejection_line", "_emit_rejection",
                     "VerificationOutputCaptureError", "VerificationOutputLimitError"):
            self.assertTrue(callable(getattr(api, name, None)),
                            "missing diagnostic interface: " + name)
        for name in ("_STAGES", "_FAILURE_KINDS"):
            self.assertIs(type(getattr(api, name, None)), frozenset,
                          "missing exact frozenset metadata: " + name)
        self.assertIs(type(getattr(api, "_REJECTION_PREFIX", None)), str)
        self.assertEqual(api._REJECTION_PREFIX, "windows-build-context rejection=")
        import inspect
        parameter = inspect.signature(api.probe).parameters.get("_diagnostic")
        self.assertIsNotNone(parameter, "missing private keyword-only diagnostic parameter")
        self.assertIs(parameter.kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertIsNone(parameter.default)
        return api

    def diagnostic_main(self, *, arch="x64", platform="win32", result=None,
                        effect=None, lstat=None, stream=None):
        api = self.diagnostic_api()
        output = io.StringIO() if stream is None else stream
        with ExitStack() as stack:
            stack.enter_context(patch.object(sys, "argv", ["probe", "--build-directory",
                str(self.root), "--architecture", arch]))
            stack.enter_context(patch.object(api.sys, "platform", platform))
            stack.enter_context(patch.object(Path, "lstat", lstat or
                (lambda path, *args, **kwargs: self.windows_lstat(path, *args, **kwargs))))
            runner = stack.enter_context(patch.object(api, "_run_unittest_with_bounded_output",
                return_value=(self.result() if effect is None else (0, b"", b""))
                if result is None else result, side_effect=effect))
            stack.enter_context(redirect_stdout(output))
            code = api.main()
        return code, output.getvalue(), runner

    def assert_rejection(self, output, stage, kind):
        prefix = "windows-build-context rejection="
        lines = output.splitlines(keepends=True)
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0], "::error::windows_build_context_probe_failed\n")
        self.assertTrue(lines[1].startswith(prefix))
        self.assertTrue(lines[1].endswith("\n"))
        self.assertLessEqual(len(lines[1].encode("ascii")), 256)
        data = json.loads(lines[1][len(prefix):-1])
        self.assertEqual(set(data), {"schema_version", "stage", "failure_kind", "production_authority"})
        self.assertIs(type(data["schema_version"]), int)
        self.assertEqual(data["schema_version"], 1)
        for key in ("stage", "failure_kind", "production_authority"):
            self.assertIs(type(data[key]), str)
        self.assertEqual(data, dict(schema_version=1, stage=stage,
            failure_kind=kind, production_authority="none"))
        self.assertNotIn("PRIVATE_PAYLOAD", output)
        return data

    def test_diagnostic_real_stage_rejections_and_query_counts(self):
        cases = (
            ("input", "validation_value", 0),
            ("context_read", "os_error", 0),
            ("context_validate", "validation_value", 0),
            ("msbuild_identity", "validation_value", 0),
            ("project_read", "os_error", 0),
            ("project_validate", "xml_parse", 0),
            ("query", "timeout", 1),
            ("query_result", "validation_runtime", 1),
            ("output_json", "validation_value", 1),
            ("properties_validate", "validation_value", 1),
            ("tool_directory", "validation_value", 1),
        )
        for stage, kind, calls in cases:
            with self.subTest(stage=stage):
                self.write_context(self.metadata)
                self.project.write_bytes(self.xml())
                kwargs = {}
                if stage == "input":
                    kwargs["platform"] = "linux"
                elif stage == "context_read":
                    self.context.unlink()
                elif stage == "context_validate":
                    self.context.write_bytes(b"{")
                elif stage == "msbuild_identity":
                    self.write_context(dict(self.metadata, msbuild="C:\\Build Tools\\other.exe"))
                elif stage == "project_read":
                    self.project.unlink()
                elif stage == "project_validate":
                    self.project.write_bytes(b"<Project>")
                elif stage == "query":
                    kwargs["effect"] = subprocess.TimeoutExpired("PRIVATE_PAYLOAD", 30)
                elif stage == "query_result":
                    kwargs["result"] = (1, b"PRIVATE_PAYLOAD", b"")
                elif stage == "output_json":
                    kwargs["result"] = (0, b"{", b"")
                elif stage == "properties_validate":
                    kwargs["result"] = self.result(dict(self.properties, Platform="wrong"))
                elif stage == "tool_directory":
                    kwargs["result"] = self.result(dict(self.properties, WindowsSdkDir="relative"))
                code, output, runner = self.diagnostic_main(**kwargs)
                self.assertEqual(code, 1)
                self.assert_rejection(output, stage, kind)
                self.assertEqual(runner.call_count, calls)

    def test_diagnostic_real_json_xml_property_semantics_are_not_mocked(self):
        valid = json.dumps(self.metadata).encode()
        for raw, kind in ((b"\xff", "unicode_error"),
                          (b"[" * 2000 + b"0" + b"]" * 2000, "validation_runtime"),
                          (valid[:-1] + b',"schema_version":1}', "validation_value"),
                          (b'{"schema_version":NaN}', "validation_value")):
            with self.subTest(context_kind=kind):
                self.context.write_bytes(raw)
                code, output, runner = self.diagnostic_main()
                self.assertEqual(code, 1)
                self.assert_rejection(output, "context_validate", kind)
                runner.assert_not_called()
        self.write_context(self.metadata)
        for raw, kind in ((b"\xff", "unicode_error"),
                          (b"<!DOCTYPE Project>" + self.xml(), "validation_value"),
                          (self.xml().replace(b"v143", b"v142"), "validation_value")):
            with self.subTest(project_kind=kind):
                self.project.write_bytes(raw)
                code, output, runner = self.diagnostic_main()
                self.assertEqual(code, 1)
                self.assert_rejection(output, "project_validate", kind)
                runner.assert_not_called()
        self.project.write_bytes(self.xml())
        for raw, stage, kind in ((b"\xff", "output_json", "unicode_error"),
                                (b'{"Properties":NaN}', "output_json", "validation_value"),
                                (b'{"Properties":{}}', "properties_validate", "validation_value")):
            with self.subTest(output_stage=stage, output_kind=kind):
                code, output, runner = self.diagnostic_main(result=(0, raw, b""))
                self.assertEqual(code, 1)
                self.assert_rejection(output, stage, kind)
                runner.assert_called_once()

    def test_diagnostic_kind_priority_and_unavailable(self):
        api = self.diagnostic_api()
        cases = (
            (subprocess.TimeoutExpired("PRIVATE_PAYLOAD", 30), "timeout"),
            (api.VerificationOutputCaptureError("PRIVATE_PAYLOAD"), "output_capture"),
            (api.VerificationOutputLimitError(16384), "output_limit"),
            (UnicodeDecodeError("utf-8", b"\xff", 0, 1, "PRIVATE_PAYLOAD"), "unicode_error"),
            (ET.ParseError("PRIVATE_PAYLOAD"), "xml_parse"),
            (FileNotFoundError("PRIVATE_PAYLOAD"), "os_error"),
            (ValueError("PRIVATE_PAYLOAD"), "validation_value"),
            (RuntimeError("PRIVATE_PAYLOAD"), "validation_runtime"),
            (RecursionError("PRIVATE_PAYLOAD"), "validation_runtime"),
            (subprocess.CalledProcessError(1, "PRIVATE_PAYLOAD", output=b"PRIVATE_PAYLOAD",
                stderr=b"PRIVATE_PAYLOAD"), "subprocess_error"),
            (Exception("PRIVATE_PAYLOAD"), "unavailable"),
        )
        for error, expected in cases:
            with self.subTest(kind=expected, error_type=type(error).__name__):
                self.assertEqual(api._failure_kind(error), expected)
        self.assertEqual(api._FAILURE_KINDS, frozenset(kind for _, kind in cases))
        self.assertEqual(len(api._FAILURE_KINDS), 10)

    def test_diagnostic_poison_str_repr_and_sensitive_payload_are_absent(self):
        api = self.diagnostic_api()
        def poison(self):
            raise AssertionError("exception text must never be read")
        def private_payload(self, name):
            if name in ("args", "cmd", "output", "stderr", "returncode", "__cause__", "__context__"):
                raise AssertionError("exception payload must never be read")
            return BaseException.__getattribute__(self, name)
        for base, args, kind in ((OSError, ("PRIVATE_PAYLOAD",), "os_error"),
                                (ValueError, ("PRIVATE_PAYLOAD",), "validation_value"),
                                (RuntimeError, ("PRIVATE_PAYLOAD",), "validation_runtime"),
                                (ET.ParseError, ("PRIVATE_PAYLOAD",), "xml_parse"),
                                (UnicodeError, ("PRIVATE_PAYLOAD",), "unicode_error"),
                                (RecursionError, ("PRIVATE_PAYLOAD",), "validation_runtime"),
                                (api.VerificationOutputCaptureError, ("PRIVATE_PAYLOAD",), "output_capture"),
                                (api.VerificationOutputLimitError, (16384,), "output_limit"),
                                (subprocess.TimeoutExpired, ("PRIVATE_PAYLOAD", 30), "timeout"),
                                (subprocess.CalledProcessError, (1, "PRIVATE_PAYLOAD"), "subprocess_error"),
                                (subprocess.SubprocessError, ("PRIVATE_PAYLOAD",), "subprocess_error")):
            error_class = type("PoisonError", (base,), {"__str__": poison, "__repr__": poison,
                "__getattribute__": private_payload})
            code, output, runner = self.diagnostic_main(effect=error_class(*args))
            self.assertEqual(code, 1)
            self.assert_rejection(output, "query", kind)
            runner.assert_called_once()

    def test_diagnostic_single_slot_closed_labels_and_isolated_instances(self):
        api = self.diagnostic_api()
        first, second = api._ProbeDiagnostic(), api._ProbeDiagnostic()
        self.assertEqual(api._ProbeDiagnostic.__slots__, ("stage",))
        self.assertFalse(hasattr(first, "__dict__"))
        expected = frozenset(("input", "context_read", "context_validate", "msbuild_identity",
            "project_read", "project_validate", "query", "query_result", "output_json",
            "properties_validate", "tool_directory", "unavailable"))
        self.assertEqual(api._STAGES, expected)
        class StringSubclass(str):
            pass
        for stage in sorted(expected):
            api._mark_diagnostic_stage(first, stage)
            self.assertEqual(api._get_diagnostic_stage(first), stage)
            self.assertEqual(api._get_diagnostic_stage(second), "unavailable")
        for stage in ("PRIVATE_PAYLOAD", None, 1, StringSubclass("query")):
            api._mark_diagnostic_stage(first, stage)
            self.assertEqual(api._get_diagnostic_stage(first), "unavailable")
        first.stage = StringSubclass("query")
        self.assertEqual(api._get_diagnostic_stage(first), "unavailable")
        first.stage = "PRIVATE_PAYLOAD"
        self.assertEqual(api._get_diagnostic_stage(first), "unavailable")
        del first.stage
        self.assertEqual(api._get_diagnostic_stage(first), "unavailable")
        api._mark_diagnostic_stage(first, "query")
        self.assertEqual(api._get_diagnostic_stage(first), "query")

    def test_diagnostic_foreign_and_subclass_objects_never_read_attributes(self):
        api = self.diagnostic_api()
        class Foreign:
            def __getattribute__(self, name):
                raise AssertionError("foreign attribute read")
            def __setattr__(self, name, value):
                raise AssertionError("foreign attribute write")
        class Subclass(api._ProbeDiagnostic):
            def __init__(self):
                pass
            def __getattribute__(self, name):
                raise AssertionError("subclass attribute read")
            def __setattr__(self, name, value):
                raise AssertionError("subclass attribute write")
        for observer in (None, Foreign(), Subclass()):
            api._mark_diagnostic_stage(observer, "query")
            self.assertEqual(api._get_diagnostic_stage(observer), "unavailable")
            with patch.object(api.sys, "platform", "win32"), \
                    patch.object(Path, "lstat", lambda path, *a, **k: self.windows_lstat(path, *a, **k)), \
                    patch.object(api, "_run_unittest_with_bounded_output", return_value=self.result()) as runner:
                receipt = api.probe(self.root, "x64", _diagnostic=observer)
            self.assertEqual(receipt["architecture"], "x64")
            runner.assert_called_once()

    def test_diagnostic_marker_fault_clears_old_stage_and_recovers(self):
        api = self.diagnostic_api()
        observer = api._ProbeDiagnostic()
        api._mark_diagnostic_stage(observer, "context_read")
        for error in (ValueError("PRIVATE_PAYLOAD"), RuntimeError("PRIVATE_PAYLOAD")):
            with patch.object(api, "_set_diagnostic_stage", side_effect=error):
                api._mark_diagnostic_stage(observer, "query")
            self.assertEqual(api._get_diagnostic_stage(observer), "unavailable")
            api._mark_diagnostic_stage(observer, "query_result")
            self.assertEqual(api._get_diagnostic_stage(observer), "query_result")
        real_setattr = object.__setattr__
        def bad_setattr(instance, name, value):
            if value == "query":
                raise OSError("PRIVATE_PAYLOAD")
            real_setattr(instance, name, value)
        with patch.object(api._ProbeDiagnostic, "__setattr__", bad_setattr):
            api._mark_diagnostic_stage(observer, "query")
        self.assertEqual(api._get_diagnostic_stage(observer), "unavailable")
        api._mark_diagnostic_stage(observer, "tool_directory")
        self.assertEqual(api._get_diagnostic_stage(observer), "tool_directory")
        with patch.object(api, "_set_diagnostic_stage", side_effect=OSError("PRIVATE_PAYLOAD")):
            code, output, runner = self.diagnostic_main(effect=ValueError("PRIVATE_PAYLOAD"))
        self.assertEqual(code, 1)
        self.assert_rejection(output, "unavailable", "validation_value")
        runner.assert_called_once()
        with patch.object(api, "_set_diagnostic_stage", side_effect=OSError("PRIVATE_PAYLOAD")):
            code, output, runner = self.diagnostic_main()
        self.assertEqual(code, 0)
        self.assertNotIn("rejection=", output)
        runner.assert_called_once()

    def test_diagnostic_reset_fault_drops_slot_and_inaccessible_stage_has_no_credit(self):
        api = self.diagnostic_api()
        observer = api._ProbeDiagnostic()
        observer.stage = "context_read"
        reset = SimpleNamespace(__setattr__=unittest.mock.Mock(side_effect=OSError("PRIVATE_PAYLOAD")),
                                __delattr__=object.__delattr__)
        with patch.object(api, "_set_diagnostic_stage", side_effect=ValueError("PRIVATE_PAYLOAD")), \
                patch.object(api, "object", reset, create=True):
            api._mark_diagnostic_stage(observer, "query")
        self.assertEqual(api._get_diagnostic_stage(observer), "unavailable")
        api._mark_diagnostic_stage(observer, "query")
        self.assertEqual(api._get_diagnostic_stage(observer), "query")
        def inaccessible(instance):
            raise OSError("PRIVATE_PAYLOAD")
        with patch.object(api._ProbeDiagnostic, "stage", property(inaccessible)):
            api._mark_diagnostic_stage(observer, "tool_directory")
            self.assertEqual(api._get_diagnostic_stage(observer), "unavailable")

    def test_diagnostic_factory_fault_preserves_success_and_failure_once(self):
        api = self.diagnostic_api()
        with patch.object(api, "_new_diagnostic", side_effect=OSError("PRIVATE_PAYLOAD")):
            code, output, runner = self.diagnostic_main()
        self.assertEqual(code, 0)
        self.assertNotIn("rejection=", output)
        runner.assert_called_once()
        with patch.object(api, "_new_diagnostic", side_effect=OSError("PRIVATE_PAYLOAD")):
            code, output, runner = self.diagnostic_main(effect=RuntimeError("PRIVATE_PAYLOAD"))
        self.assertEqual(code, 1)
        self.assert_rejection(output, "unavailable", "validation_runtime")
        runner.assert_called_once()

    def test_diagnostic_main_instances_are_fresh_after_a_previous_rejection(self):
        api = self.diagnostic_api()
        observers = []
        def factory():
            observer = api._ProbeDiagnostic()
            observers.append(observer)
            return observer
        with patch.object(api, "_new_diagnostic", side_effect=factory) as created:
            first_code, first_output, first_runner = self.diagnostic_main(effect=ValueError("PRIVATE_PAYLOAD"))
            self.context.write_bytes(b"{")
            second_code, second_output, second_runner = self.diagnostic_main()
        self.assertEqual(created.call_count, 2)
        self.assertEqual((first_code, second_code), (1, 1))
        self.assertIsNot(observers[0], observers[1])
        self.assert_rejection(first_output, "query", "validation_value")
        self.assert_rejection(second_output, "context_validate", "validation_value")
        self.assertEqual((observers[0].stage, observers[1].stage), ("query", "context_validate"))
        first_runner.assert_called_once()
        second_runner.assert_not_called()

    def test_diagnostic_get_stage_and_kind_faults_use_unavailable_without_retry(self):
        api = self.diagnostic_api()
        observer = api._ProbeDiagnostic()
        observer.stage = "query"
        def bad_getattribute(instance, name):
            raise OSError("PRIVATE_PAYLOAD")
        with patch.object(api._ProbeDiagnostic, "__getattribute__", bad_getattribute), \
                patch.object(api, "_new_diagnostic", return_value=observer):
            code, output, runner = self.diagnostic_main(effect=ValueError("PRIVATE_PAYLOAD"))
        self.assertEqual(code, 1)
        self.assert_rejection(output, "unavailable", "validation_value")
        runner.assert_called_once()
        for value in ("PRIVATE_PAYLOAD", None, 1):
            with patch.object(api, "_failure_kind", return_value=value):
                code, output, runner = self.diagnostic_main(effect=ValueError("PRIVATE_PAYLOAD"))
            self.assertEqual(code, 1)
            self.assert_rejection(output, "query", "unavailable")
            runner.assert_called_once()
        with patch.object(api, "_failure_kind", side_effect=RuntimeError("PRIVATE_PAYLOAD")):
            code, output, runner = self.diagnostic_main(effect=ValueError("PRIVATE_PAYLOAD"))
        self.assertEqual(code, 1)
        self.assert_rejection(output, "query", "unavailable")
        runner.assert_called_once()

    def test_diagnostic_closed_payload_all_stage_kind_pairs_fit_ascii_budget(self):
        api = self.diagnostic_api()
        observer = api._ProbeDiagnostic()
        for stage in sorted(api._STAGES):
            observer.stage = stage
            for kind in sorted(api._FAILURE_KINDS):
                with self.subTest(stage=stage, kind=kind), \
                        patch.object(api, "_failure_kind", return_value=kind):
                    line = api._rejection_line(observer, ValueError("PRIVATE_PAYLOAD"))
                self.assertIs(type(line), str)
                self.assert_rejection("::error::windows_build_context_probe_failed\n" + line, stage, kind)
        class StringSubclass(str):
            pass
        with patch.object(api, "_failure_kind", return_value=StringSubclass("timeout")):
            line = api._rejection_line(observer, ValueError("PRIVATE_PAYLOAD"))
        self.assert_rejection("::error::windows_build_context_probe_failed\n" + line,
                              observer.stage, "unavailable")

    def test_diagnostic_serialization_and_single_write_fault_preserve_original_failure(self):
        api = self.diagnostic_api()
        for failure in (OSError("PRIVATE_PAYLOAD"), ValueError("PRIVATE_PAYLOAD")):
            with patch.object(api.json, "dumps", side_effect=failure) as serializer:
                code, output, runner = self.diagnostic_main(effect=RuntimeError("PRIVATE_PAYLOAD"))
            self.assertEqual((code, output), (1, "::error::windows_build_context_probe_failed\n"))
            serializer.assert_called_once()
            runner.assert_called_once()
        class BrokenDiagnosticStream(io.StringIO):
            def __init__(self):
                super().__init__()
                self.attempts = 0
            def write(self, value):
                if value.startswith("windows-build-context rejection="):
                    self.attempts += 1
                    raise OSError("PRIVATE_PAYLOAD")
                return super().write(value)
        output = BrokenDiagnosticStream()
        code, text, runner = self.diagnostic_main(effect=ValueError("PRIVATE_PAYLOAD"), stream=output)
        self.assertEqual((code, text), (1, "::error::windows_build_context_probe_failed\n"))
        self.assertEqual(output.attempts, 1)
        runner.assert_called_once()
        class PartialDiagnosticStream(BrokenDiagnosticStream):
            def write(self, value):
                if value.startswith("windows-build-context rejection="):
                    self.attempts += 1
                    io.StringIO.write(self, value[:12])
                    raise OSError("PRIVATE_PAYLOAD")
                return io.StringIO.write(self, value)
        partial = PartialDiagnosticStream()
        code, text, runner = self.diagnostic_main(effect=ValueError("PRIVATE_PAYLOAD"), stream=partial)
        self.assertEqual(code, 1)
        self.assertEqual(text, "::error::windows_build_context_probe_failed\nwindows-buil")
        self.assertEqual(partial.attempts, 1)
        runner.assert_called_once()
        class RecordingStream(io.StringIO):
            def __init__(self):
                super().__init__()
                self.lines = []
            def write(self, value):
                if value.startswith("windows-build-context rejection="):
                    self.lines.append(value)
                return super().write(value)
        output = RecordingStream()
        code, text, runner = self.diagnostic_main(effect=ValueError("PRIVATE_PAYLOAD"), stream=output)
        self.assertEqual(code, 1)
        self.assertEqual(len(output.lines), 1)
        self.assert_rejection(text, "query", "validation_value")
        self.assertTrue(output.lines[0].endswith("\n"))
        runner.assert_called_once()

    def test_diagnostic_invalid_serialized_line_is_not_truncated_or_written(self):
        api = self.diagnostic_api()
        for serialized in ("x" * 257, "工具", 1, None, "{}", "[]", "not-json",
                           '{"schema_version":true,"stage":"query","failure_kind":"validation_value","production_authority":"none"}',
                           '{"schema_version":1,"stage":"PRIVATE_PAYLOAD","failure_kind":"validation_value","production_authority":"none"}',
                           '{"schema_version":1,"stage":"query","failure_kind":"validation_value","production_authority":"none","extra":1}',
                           '{"schema_version":1,"schema_version":1,"stage":"query","failure_kind":"validation_value","production_authority":"none"}'):
            with patch.object(api.json, "dumps", return_value=serialized):
                code, output, runner = self.diagnostic_main(effect=ValueError("PRIVATE_PAYLOAD"))
            self.assertEqual((code, output), (1, "::error::windows_build_context_probe_failed\n"))
            runner.assert_called_once()

    def test_diagnostic_serialized_whitespace_is_rejected_before_any_diagnostic_write(self):
        api = self.diagnostic_api()
        compact = ('{"schema_version":1,"stage":"query","failure_kind":"validation_value",'
                   '"production_authority":"none"}')
        cases = [("trailing_cr", compact + "\r"), ("trailing_lf", compact + "\n"),
                 ("trailing_space", compact + " "), ("trailing_tab", compact + "\t"),
                 ("token_lf", compact.replace(",", ",\n", 1)),
                 ("token_cr", compact.replace(",", ",\r", 1)),
                 ("token_tab", compact.replace(",", ",\t", 1)),
                 ("token_spaces", compact.replace(":", ":  ", 1))]
        class RecordingStream(io.StringIO):
            def __init__(self):
                super().__init__()
                self.attempts = 0
            def write(self, value):
                if value.startswith("windows-build-context rejection="):
                    self.attempts += 1
                return super().write(value)
        for name, serialized in cases:
            with self.subTest(name=name):
                self.assertLessEqual(len((api._REJECTION_PREFIX + serialized + "\n").encode("ascii")), 256)
                self.assertEqual(json.loads(serialized), dict(schema_version=1, stage="query",
                    failure_kind="validation_value", production_authority="none"))
                stream = RecordingStream()
                with patch.object(api.json, "dumps", return_value=serialized) as serializer:
                    code, output, runner = self.diagnostic_main(effect=ValueError("PRIVATE_PAYLOAD"), stream=stream)
                self.assertEqual((code, output), (1, "::error::windows_build_context_probe_failed\n"))
                self.assertEqual(stream.attempts, 0)
                serializer.assert_called_once()
                runner.assert_called_once()

    def test_diagnostic_fatal_faults_propagate_from_every_protected_boundary(self):
        api = self.diagnostic_api()
        class FatalStream(io.StringIO):
            def __init__(self, error):
                super().__init__()
                self.error = error
            def write(self, value):
                if value.startswith("windows-build-context rejection="):
                    raise self.error
                return super().write(value)
        for error_type in (MemoryError, KeyboardInterrupt, SystemExit):
            for boundary in ("_new_diagnostic", "_set_diagnostic_stage", "_failure_kind", "serialize", "write"):
                error = error_type("PRIVATE_PAYLOAD")
                with self.subTest(error_type=error_type.__name__, boundary=boundary):
                    with ExitStack() as stack:
                        stream = None
                        if boundary == "serialize":
                            stack.enter_context(patch.object(api.json, "dumps", side_effect=error))
                        elif boundary == "write":
                            stream = FatalStream(error)
                        else:
                            stack.enter_context(patch.object(api, boundary, side_effect=error))
                        with self.assertRaises(error_type) as raised:
                            self.diagnostic_main(effect=ValueError("PRIVATE_PAYLOAD"), stream=stream)
                    self.assertIs(raised.exception, error)
            observer = api._ProbeDiagnostic()
            def fatal_getattribute(instance, name):
                raise error_type("PRIVATE_PAYLOAD")
            with patch.object(api._ProbeDiagnostic, "__getattribute__", fatal_getattribute):
                with self.assertRaises(error_type):
                    api._get_diagnostic_stage(observer)
            error = error_type("PRIVATE_PAYLOAD")
            with self.assertRaises(error_type) as raised:
                self.diagnostic_main(effect=error)
            self.assertIs(raised.exception, error)

    def test_diagnostic_original_generic_write_failure_still_propagates(self):
        error = OSError("PRIVATE_PAYLOAD")
        class BrokenGenericStream(io.StringIO):
            def write(self, value):
                if value.startswith("::error::"):
                    raise error
                return super().write(value)
        with self.assertRaises(OSError) as raised:
            self.diagnostic_main(effect=ValueError("PRIVATE_PAYLOAD"), stream=BrokenGenericStream())
        self.assertIs(raised.exception, error)

    def test_diagnostic_old_two_arguments_runner_exception_identity_and_no_observer_factory(self):
        api = self.diagnostic_api()
        with patch.object(api, "_new_diagnostic", side_effect=AssertionError("old API creates observer")):
            receipt, runner = self.invoke()
        self.assertEqual(receipt["architecture"], "x64")
        runner.assert_called_once()
        for error in (api.VerificationOutputCaptureError("PRIVATE_PAYLOAD"),
                      api.VerificationOutputLimitError(16384),
                      subprocess.TimeoutExpired("PRIVATE_PAYLOAD", 30),
                      TypeError("PRIVATE_PAYLOAD"), AssertionError("PRIVATE_PAYLOAD")):
            with patch.object(api.sys, "platform", "win32"), \
                    patch.object(Path, "lstat", lambda path, *a, **k: self.windows_lstat(path, *a, **k)), \
                    patch.object(api, "_run_unittest_with_bounded_output", side_effect=error) as runner:
                with self.assertRaises(type(error)) as raised:
                    api.probe(self.root, "x64")
            self.assertIs(raised.exception, error)
            runner.assert_called_once()

    def test_diagnostic_exact_side_effects_match_old_call_without_extra_reads_or_queries(self):
        api = self.diagnostic_api()
        snapshots = []
        for observed in (False, True):
            events = []
            old_read, old_json, old_project = api._read_regular, api._json, api._project_selection
            def lstat(path, *args, **kwargs):
                events.append(("lstat", str(path)))
                return self.windows_lstat(path, *args, **kwargs)
            def read(path, limit):
                events.append(("read", str(path), limit))
                return old_read(path, limit)
            def decode(raw):
                events.append(("json", raw))
                return old_json(raw)
            def project(raw, platform):
                events.append(("project", raw, platform))
                return old_project(raw, platform)
            with patch.object(api.sys, "platform", "win32"), patch.object(Path, "lstat", lstat), \
                    patch.object(api, "_read_regular", read), patch.object(api, "_json", decode), \
                    patch.object(api, "_project_selection", project), \
                    patch.object(api, "_run_unittest_with_bounded_output", return_value=self.result()) as runner:
                kwargs = {"_diagnostic": api._ProbeDiagnostic()} if observed else {}
                receipt = api.probe(self.root, "x64", **kwargs)
            snapshots.append((receipt, events, runner.call_args))
            runner.assert_called_once()
            self.assertEqual([event[1] for event in events if event[0] == "lstat"],
                [str(self.root), str(self.context), str(Path(self.metadata["msbuild"])),
                 str(self.project), *(str(Path(self.properties[key])) for key in
                     ("VCToolsInstallDir", "WindowsSdkDir", "MSBuildToolsPath"))])
            self.assertEqual(len([event for event in events if event[0] == "read"]), 2)
            self.assertEqual(len([event for event in events if event[0] == "json"]), 2)
            self.assertEqual(len([event for event in events if event[0] == "project"]), 1)
            self.assertEqual(runner.call_args.kwargs, dict(workspace=self.root, timeout=30,
                output_limit_bytes=16384, environment=os.environ.copy()))
        self.assertEqual(snapshots[0], snapshots[1])
        import inspect
        source = "\n".join(inspect.getsource(getattr(api, name)) for name in
            ("_new_diagnostic", "_set_diagnostic_stage", "_mark_diagnostic_stage",
             "_get_diagnostic_stage", "_failure_kind", "_rejection_line", "_emit_rejection"))
        for forbidden in ("lstat(", ".open(", ".read(", "_run_unittest_with_bounded_output(",
                          "time.", "threading.", "subprocess.run(", "sleep(", "retry"):
            self.assertNotIn(forbidden, source)

    def test_diagnostic_two_architectures_main_success_preserves_exact_original_two_lines(self):
        for arch, platform in (("x64", "x64"), ("arm64", "ARM64")):
            with self.subTest(arch=arch):
                self.metadata["platform"] = self.properties["Platform"] = platform
                self.write_context(self.metadata)
                self.project.write_bytes(self.xml(platform))
                receipt = dict(schema_version=1, architecture=arch,
                    **{key: self.metadata[key] for key in ("generator", "toolset", "sdk_version", "msbuild")},
                    **{key: self.properties[key] for key in ("VCToolsInstallDir", "WindowsSdkDir", "MSBuildToolsPath")})
                code, output, runner = self.diagnostic_main(arch=arch)
                self.assertEqual((code, output), (0,
                    "windows-build-context status=PASS production_authority=none\n"
                    + "windows-build-context receipt="
                    + json.dumps(receipt, separators=(",", ":"), ensure_ascii=True) + "\n"))
                self.assertNotIn("rejection=", output)
                runner.assert_called_once()

    def test_diagnostic_cli_errors_exit_two_before_probe_or_factory(self):
        api = self.diagnostic_api()
        cases = ([], ["--build-directory", str(self.root)],
            ["--build-directory", str(self.root), "--architecture", "x86"],
            ["--build-dir", str(self.root), "--architecture", "x64"],
            ["--build-directory", str(self.root), "--architecture", "x64", "--extra"],
            ["--build-directory", str(self.root), "--architecture", "ARM64"])
        for flags in cases:
            with self.subTest(flags=flags), patch.object(sys, "argv", ["probe", *flags]), \
                    patch.object(api, "probe") as probe, patch.object(api, "_new_diagnostic") as factory, \
                    patch.object(sys, "stderr", io.StringIO()), redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    api.main()
                self.assertEqual(raised.exception.code, 2)
                probe.assert_not_called()
                factory.assert_not_called()
```

- [x] **Step 3: 用 apply_patch 逐字替换原 `test_main_fixed_receipt_expected_errors_privacy_and_programming_errors`，保留 main_call helper。**

不把旧原捕获错误继续断言为只有泛错误；因为 `main_call` mock probe 不标记，stage 必须 unavailable：

```python
    def test_main_fixed_receipt_expected_errors_privacy_and_programming_errors(self):
        self.assertEqual(self.main_call(), (0, 'windows-build-context status=PASS production_authority=none\n'
            'windows-build-context receipt={"schema_version":1,"name":"\\u5de5\\u5177"}\n'))
        for error, kind in ((OSError("PRIVATE"), "os_error"), (UnicodeError("PRIVATE"), "unicode_error"),
                            (ValueError("PRIVATE"), "validation_value"), (RuntimeError("PRIVATE"), "validation_runtime"),
                            (ET.ParseError("PRIVATE"), "xml_parse"), (RecursionError("PRIVATE"), "validation_runtime"),
                            (subprocess.TimeoutExpired("PRIVATE", 30), "timeout"),
                            (subprocess.CalledProcessError(1, "PRIVATE"), "subprocess_error")):
            expected = (1, "::error::windows_build_context_probe_failed\n"
                + 'windows-build-context rejection={"schema_version":1,"stage":"unavailable","failure_kind":"'
                + kind + '","production_authority":"none"}\n')
            self.assertEqual(self.main_call(error), expected)
        for error in (TypeError("bug"), AssertionError("bug"), MemoryError(), KeyboardInterrupt(), SystemExit()):
            with self.assertRaises(type(error)) as raised:
                self.main_call(error)
            self.assertIs(raised.exception, error)
```

- [x] **Step 4: 运行新增 portable class，记录真实 RED。**

```bash
/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B -m unittest tests.test_windows_build_context.TestWindowsBuildContext -v
```

Expected：实际非零，新增方法先通过test-only `diagnostic_api` 的精确接口断言门，缺helper/class/metadata/keyword只产生 assertion FAILURE（F）；原失败golden的新输出断言也可提供行为F。任何ERROR（E），包括AttributeError/TypeError、语法/import或fixture问题，均不是有效RED，必须先修测试夹具后重跑。最初guard导致的F只证明接口尚缺，不能声称stage/kind、故障或其它细行为已运行；记录每个新增test id的实际F/E/退出码和具体断言，不预造方法数量或RED数，尚未实施不得记GREEN。现有 `.api` / `main_call` / 旧两位置参数合同不改；guard仅用于本片新测试及 `diagnostic_main`。

- [x] **Step 5: apply_patch 替换 runner import，并在 `_UNSAFE_TEXT` 后加入完整私有诊断代码。**

原单行 runner import 精确替换为：

```python
from icode.runner import (  # noqa: E402
    VerificationOutputCaptureError,
    VerificationOutputLimitError,
    _run_unittest_with_bounded_output,
)
```

新私有代码如下。闭集用 frozenset 已足够，不另加 enum/依赖。一个 slot 仅存当前字符串；不保存 exception、bool、history或结果。清 stage 的 ordinary fault 退为无 slot 时 getter unavailable；任意被破坏物理对象不承诺完整观察信用。

```python
_STAGES = frozenset((
    "input", "context_read", "context_validate", "msbuild_identity",
    "project_read", "project_validate", "query", "query_result", "output_json",
    "properties_validate", "tool_directory", "unavailable",
))
_FAILURE_KINDS = frozenset((
    "timeout", "output_capture", "output_limit", "unicode_error", "xml_parse",
    "os_error", "validation_value", "validation_runtime", "subprocess_error", "unavailable",
))
_REJECTION_PREFIX = "windows-build-context rejection="


class _ProbeDiagnostic:
    __slots__ = ("stage",)

    def __init__(self):
        self.stage = "unavailable"


def _new_diagnostic() -> _ProbeDiagnostic:
    return _ProbeDiagnostic()


def _set_diagnostic_stage(diagnostic: _ProbeDiagnostic, stage: str) -> None:
    diagnostic.stage = stage


def _mark_diagnostic_stage(diagnostic: object, stage: object) -> None:
    if type(diagnostic) is not _ProbeDiagnostic:
        return
    try:
        selected = stage if type(stage) is str and stage in _STAGES else "unavailable"
        _set_diagnostic_stage(diagnostic, selected)
    except MemoryError:
        raise
    except Exception:
        # A failed new marker cannot leave the previous operation as evidence.
        try:
            object.__setattr__(diagnostic, "stage", "unavailable")
        except MemoryError:
            raise
        except Exception:
            try:
                object.__delattr__(diagnostic, "stage")
            except MemoryError:
                raise
            except Exception:
                pass


def _get_diagnostic_stage(diagnostic: object) -> str:
    if type(diagnostic) is not _ProbeDiagnostic:
        return "unavailable"
    try:
        stage = diagnostic.stage
        return stage if type(stage) is str and stage in _STAGES else "unavailable"
    except MemoryError:
        raise
    except Exception:
        return "unavailable"


def _failure_kind(error: BaseException) -> str:
    # Type-only matching; specific runner/subprocess types precede their bases.
    for error_type, label in (
        (subprocess.TimeoutExpired, "timeout"),
        (VerificationOutputCaptureError, "output_capture"),
        (VerificationOutputLimitError, "output_limit"),
        (UnicodeError, "unicode_error"),
        (ET.ParseError, "xml_parse"),
        (OSError, "os_error"),
        (ValueError, "validation_value"),
        (RuntimeError, "validation_runtime"),
        (subprocess.SubprocessError, "subprocess_error"),
    ):
        if isinstance(error, error_type):
            return label
    return "unavailable"


def _rejection_line(diagnostic: object, error: BaseException) -> str | None:
    stage = _get_diagnostic_stage(diagnostic)
    try:
        kind = _failure_kind(error)
    except MemoryError:
        raise
    except Exception:
        kind = "unavailable"
    if type(kind) is not str or kind not in _FAILURE_KINDS:
        kind = "unavailable"
    payload = {"schema_version": 1, "stage": stage, "failure_kind": kind,
               "production_authority": "none"}
    serialized = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
    if type(serialized) is not str:
        return None
    line = _REJECTION_PREFIX + serialized + "\n"
    if len(line.encode("ascii")) > 256:
        return None
    # Closed keys and labels have no whitespace; require one compact JSON line.
    if any(character.isspace() for character in serialized):
        return None
    decoded = json.loads(serialized, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    if (type(decoded) is not dict or decoded != payload
            or type(decoded.get("schema_version")) is not int):
        return None
    return line


def _emit_rejection(diagnostic: object, error: BaseException) -> None:
    line = _rejection_line(diagnostic, error)
    if line is not None:
        # One write only after the complete bounded ASCII line is ready.
        sys.stdout.write(line)
```

ordinary 保护边界内 helper/setter 可注入故障；不为“将最外安全 wrapper 替换为任意抛错函数”的 monkeypatch 无穷加 wrapper。裸 MemoryError 重抛，KI/SE 非 Exception 自然传播。仅成功完整写出的诊断行有解析信用，损坏物理 stdout 可能部分写，不承诺原子性/无碎片。

- [x] **Step 6: apply_patch 用以下内容替换整个 probe 函数。**

```python
def probe(build_directory: Path, architecture: str, *, _diagnostic=None) -> dict:
    """One bounded, property-only query of an explicitly selected CI MSBuild."""
    _mark_diagnostic_stage(_diagnostic, "input")
    if sys.platform != "win32" or architecture not in ("x64", "arm64"):
        raise ValueError("unsupported platform or architecture")
    if not build_directory.is_absolute() or not stat.S_ISDIR(build_directory.lstat().st_mode):
        raise ValueError("build directory must exist and be absolute")
    _mark_diagnostic_stage(_diagnostic, "context_read")
    context_raw = _read_regular(build_directory / "icode-windows-build-context.json", _CONTEXT_LIMIT)
    _mark_diagnostic_stage(_diagnostic, "context_validate")
    context = _json(context_raw)
    if type(context) is not dict or set(context) != _CONTEXT_FIELDS:
        raise ValueError("context field set mismatch")
    if type(context["schema_version"]) is not int or context["schema_version"] != 1:
        raise ValueError("context schema mismatch")
    for field in _CONTEXT_FIELDS - {"schema_version"}:
        _string(context[field])
    platform = {"x64": "x64", "arm64": "ARM64"}[architecture]
    if (re.fullmatch(r"Visual Studio [0-9]+ [0-9]{4}", context["generator"]) is None
            or context["platform"] != platform):
        raise ValueError("generator or platform mismatch")
    msbuild = context["msbuild"]
    _mark_diagnostic_stage(_diagnostic, "msbuild_identity")
    if PureWindowsPath(msbuild).name.casefold() != "msbuild.exe":
        raise ValueError("explicit MSBuild executable required")
    _windows_path(msbuild, directory=False)
    project = build_directory / "icode_windows_bootstrap.vcxproj"
    _mark_diagnostic_stage(_diagnostic, "project_read")
    project_raw = _read_regular(project, _PROJECT_LIMIT)
    _mark_diagnostic_stage(_diagnostic, "project_validate")
    sdk, toolset = _project_selection(project_raw, platform)
    if sdk != context["sdk_version"] or toolset != context["toolset"]:
        raise ValueError("project and context selected properties disagree")
    argv = [
        msbuild, str(project), "-nologo", "-noAutoResponse", "-nodeReuse:false", "-maxCpuCount:1",
        "-property:Configuration=Release", f"-property:Platform={platform}",
        "-getProperty:" + ",".join(_PROPERTY_FIELDS),
    ]
    _mark_diagnostic_stage(_diagnostic, "query")
    result = _run_unittest_with_bounded_output(
        argv, workspace=build_directory, timeout=30, output_limit_bytes=_OUTPUT_LIMIT,
        environment=os.environ.copy(),
    )
    _mark_diagnostic_stage(_diagnostic, "query_result")
    if type(result) is not tuple or len(result) != 3:
        raise RuntimeError("invalid MSBuild runner result")
    code, stdout, stderr = result
    if (type(code) is not int or code != 0 or type(stdout) is not bytes
            or not 0 < len(stdout) <= _OUTPUT_LIMIT or type(stderr) is not bytes or stderr):
        raise RuntimeError("MSBuild property query failed")
    _mark_diagnostic_stage(_diagnostic, "output_json")
    output = _json(stdout)
    _mark_diagnostic_stage(_diagnostic, "properties_validate")
    if type(output) is not dict or set(output) != {"Properties"}:
        raise ValueError("MSBuild output root mismatch")
    properties = output["Properties"]
    if type(properties) is not dict or set(properties) != set(_PROPERTY_FIELDS):
        raise ValueError("MSBuild property field set mismatch")
    for field in _PROPERTY_FIELDS:
        _string(properties[field])
    for field, expected in (
        ("Configuration", "Release"), ("Platform", platform),
        ("PlatformToolset", toolset), ("WindowsTargetPlatformVersion", sdk),
    ):
        if properties[field] != expected:
            raise ValueError("MSBuild evaluated selection mismatch")
    _mark_diagnostic_stage(_diagnostic, "tool_directory")
    for field in _PROPERTY_FIELDS[4:]:
        _windows_path(properties[field], directory=True)
    return {
        "schema_version": 1, "architecture": architecture, "generator": context["generator"],
        "toolset": toolset, "sdk_version": sdk, "msbuild": msbuild,
        **{field: properties[field] for field in _PROPERTY_FIELDS[4:]},
    }
```

阶段只在原操作前标记；query 标记包括环境快照，不能证明子进程已启动。未新增文件读/lstat/clock/thread/重试；旧嵌套表达式拆为同序各一次。业务不包新大 catch、不返回假成功、不重包异常。

- [x] **Step 7: apply_patch 用以下内容替换整个 main 函数。**

```python
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--build-directory", required=True, type=Path)
    parser.add_argument("--architecture", required=True, choices=("x64", "arm64"))
    args = parser.parse_args()
    try:
        diagnostic = _new_diagnostic()
    except MemoryError:
        raise
    except Exception:
        diagnostic = None
    try:
        receipt = probe(args.build_directory, args.architecture, _diagnostic=diagnostic)
    except (OSError, UnicodeError, ValueError, RuntimeError, ET.ParseError, subprocess.SubprocessError) as error:
        print("::error::windows_build_context_probe_failed")
        try:
            _emit_rejection(diagnostic, error)
        except MemoryError:
            raise
        except Exception:
            pass
        return 1
    print("windows-build-context status=PASS production_authority=none")
    print("windows-build-context receipt=" + json.dumps(receipt, separators=(",", ":"), ensure_ascii=True))
    return 0
```

原业务捕获 tuple 完全不增删；泛错误 print 在新诊断吞错范围外。成功两 print 字符逐字保留；CLI 解析在 factory/probe 之前。

- [x] **Step 8: 运行同一 portable class，记录真实 GREEN 或修复两源后重跑。**

```bash
/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B -m unittest tests.test_windows_build_context.TestWindowsBuildContext -v
git diff --check
```

Expected：实际0F/E/skip，原测试和新增方法同轮通过；按真实测试摘要记数。若失败先定位测试/实现与冻结设计，不改预算、不跳过测试、不扩大捕获 tuple。代码建议是最小设计实现，作者可修正本两源中的有证据遗漏，若变动公开合同需回 root 重审设计。

- [x] **Step 9: 作者逐项 SPEC 自审，再 QUALITY 自审，冻结两源 SHA 并 STOP。**

```bash
git diff -- scripts/probe_windows_build_context.py tests/test_windows_build_context.py
sha256sum scripts/probe_windows_build_context.py tests/test_windows_build_context.py
sha256sum docs/nbl/specs/2026-10-09-windows-build-context-failure-design.md
git status --short
```

Expected：逐项核上表及12stage/10kind/4字段；真 JSON/XML/property 拒绝、0/1query、旧identity和成功golden、foreign属性零访问、ordinary/fatal保护、无新增业务I/O。无未定义引用/占位；设计 SHA 不变；作者交 root 实际 RED/GREEN 原输出、两源SHA和自审问题数，不提交或继续下一 Task。

### Task 2: fresh 双审与 root 完整软件验收

**状态**
- [x] 任务完成（仅本片软件验收；本片发布观察及整体门另验）

**Dependencies:** Task 1
**Parallelizable:** No (SPEC→不同QUALITY→root验证，全部读取同一冻结实现)

- [x] **Step 1: root 派 fresh 全局 SPEC，只读两源、完整冻结设计和计划，输出 C/I/M。**

不是复用设计或计划审查者的旧结论；审查整个最终源而非仅 diff。要核旧 capture 两参数调用、全部继承优先级、marker ordinary clear/recovery、getter unavailable、fatal传播、false信用边界。SPEC 不改 source 或测试、不提交。问题回唯一作者修复两源，再冻结 SHA 并重审，未零缺陷不进入 QUALITY。

- [x] **Step 2: 不同 fresh QUALITY 对同一 SHA 做只读质量/异常/副作用审查。**

核无路径/原值/异常 str/repr/args/cause/context 读取，无 query重试/lstat增量/clock/thread，单slot且精确observer类型，无多余依赖/捕获宽化。具体类型优先和RecursionError不能遗漏；静态代码一一对应真实测试。出现问题同样回唯一作者修复，并重走 SPEC→不同 QUALITY；把通过绑定两源SHA，不把作者自审代独立审查。

- [x] **Step 3: root 运行定点，核准确存在的 runner class 与旧 capture 合同。**

```bash
rg -n '^class Test(IndependentVerification|WindowsTestProcessHandle|WindowsTestProcessObserver)' tests/test_runner.py
/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B -m unittest tests.test_windows_build_context.TestWindowsBuildContext tests.test_windows_pe_capture.TestWindowsPeCapture tests.test_windows_bootstrap.TestWindowsBootstrap tests.test_run_workspace_ci.TestWorkspaceCiCoverage tests.test_runner.TestIndependentVerification tests.test_runner.TestWindowsTestProcessHandle tests.test_runner.TestWindowsTestProcessObserver -v
```

Expected：准确存在的上述class实际退出0；新增 portable 方法零skip。runner class 中原生/平台/工具依赖 skip 如实逐项说明，不称 native 验收；不把系统 Windows skip 编造成 portable失败分类已修复。记录实际 total/F/E/skip、退出码及 elapsed；需要计时只由 root 验证外部记录，不加 probe 遥测。

- [x] **Step 4: 定点结束后串行20轮 portable关键class，按 actual计数。**

```bash
/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B -c 'import sys, unittest
names = ("tests.test_windows_build_context.TestWindowsBuildContext", "tests.test_windows_pe_capture.TestWindowsPeCapture", "tests.test_run_workspace_ci.TestWorkspaceCiCoverage")
total = 0
for round_number in range(1, 21):
    print("build-context diagnostic round", round_number, flush=True)
    suite = unittest.defaultTestLoader.loadTestsFromNames(names)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    total += result.testsRun
    print("actual", result.testsRun, "failures", len(result.failures), "errors", len(result.errors), "skips", len(result.skipped), flush=True)
    if not result.wasSuccessful() or result.skipped:
        sys.exit(1)
print("actual aggregate", total, flush=True)'
```

Expected：每轮实际0F/E/skip，累计为20轮真实执行次数；不把重复执行计为新增方法，不先写固定PASS总数。若选择守卫自带必要平台门，先读实际结果和守卫定义再评估，不删除/放宽来取得绿色。

- [x] **Step 5: 20轮完成后跑现有 DEFAULT，结束后跑原 preflight 完整三道。**

```bash
/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B scripts/run_workspace_ci.py
/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B scripts/preflight.py
```

两命令必须串行，Expected：均实际exit0，preflight明确三道通过。其 tests 原内部调用 `[sys.executable, "-m", "unittest"]`，cwd=str(REPO)、capture_output=True、text=True、encoding=utf-8、errors=replace、shell=False，不能改变 argv/kwargs、筛选测试或重复运行子命令；若 root 只读 wrapper 提取原摘要，必须每原调用仅执行一次并保留返回码。全文unittest skip按实际平台单列，软件成功不授原生Windows/PE/load/完整R2R3。

- [x] **Step 6: 仓外临时 pyc、compile-j1，然后治理/site/landscape/diff。**

```bash
diagnostic_pyc_dir=$(mktemp -d /tmp/icode-context-diagnostic-pyc-XXXXXX)
PYTHONPYCACHEPREFIX="$diagnostic_pyc_dir" /tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B -m compileall -q -j 1 src scripts tests
/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B scripts/check_governance.py
/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B scripts/check_site.py
/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B scripts/check_agent_landscape.py --today 2026-10-09
git diff --check
```

Expected：各命令实际0，pyc只在上述mktemp仓外路径；不递归删除用户路径。landscape只检查20项结构/排期，定点研究复用固定 Codex 证据不表示全部上游刚刷新。

- [x] **Step 7: root 更新履历并做精确相关文档连续两轮 clean。**

root 全文读 `/home/orbbec/.agents/skills/doc-contract-consistency-audit/SKILL.md` 后使用该 skill，按实际证据更新本计划状态/实际计数和历史 reader plan 收尾，不改冻结设计；研究/landscape仅补本阶段事实和取舍。两次分别运行以下命令，第一次完成读取全部疑似项后才第二次；若本阶段另外新增 root调查文档，先确定精确路径并显式补入两个命令的清单，不能目录扫描替代范围核对。

```bash
/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B /home/orbbec/.agents/skills/doc-contract-consistency-audit/scripts/check_consistency.py docs/nbl/plans/2026-10-09-windows-build-context-failure-diagnostic.md docs/nbl/specs/2026-10-09-windows-build-context-failure-design.md docs/nbl/specs/2026-10-09-windows-build-context-rejection-research.md docs/nbl/plans/2026-10-09-windows-pe-reader-foundation.md docs/agent-landscape-live.md
/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B /home/orbbec/.agents/skills/doc-contract-consistency-audit/scripts/check_consistency.py docs/nbl/plans/2026-10-09-windows-build-context-failure-diagnostic.md docs/nbl/specs/2026-10-09-windows-build-context-failure-design.md docs/nbl/specs/2026-10-09-windows-build-context-rejection-research.md docs/nbl/plans/2026-10-09-windows-pe-reader-foundation.md docs/agent-landscape-live.md
```

Expected：两轮各0疑似项，人工再核12/10/4/256、源码scope/两参调用/保密字段、上一/本片时间窗及信用分离。不得将冻结设计/本计划例子写成实施已发生；疑似项逐项人工归类并精确修复root文档后重跑，不改扫描器掩盖问题。

- [x] **Step 8: 最终冻结源与文档，重验 secrets/submodule/diff及治理。**

```bash
sha256sum scripts/probe_windows_build_context.py tests/test_windows_build_context.py docs/nbl/specs/2026-10-09-windows-build-context-failure-design.md
/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B scripts/check_governance.py
/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B scripts/check_site.py
/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B scripts/check_agent_landscape.py --today 2026-10-09
/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B scripts/preflight.py --only secrets
/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B scripts/preflight.py --only submodule
git diff --check
git -C vendor/icode-skill status --porcelain
git -C vendor/icode-skill rev-parse HEAD
git ls-files -s vendor/icode-skill
```

Expected：全部实际0且两源SHA与双审/软件测试相同；冻结设计SHA不变；vendor clean/head=gitlink。源变化回Task1并双审/重验，文档变化回Step7双轮clean，不能在最终守卫后悄改source。

### Task 3: root 精确 main 发布与独立新 SHA 观察

**状态**
- [x] 发布和观察结束（ef43 CI五失败保留；测试兼容修正与原生总门另验）

**Dependencies:** Task 2
**Parallelizable:** No (必须软件门与双审结束，观察必须绑定本片新SHA)

- [x] **Step 1: root 核最终范围与已授权发布条件，显式暂存本片两源和精确文档。**

```bash
git branch --show-current
git rev-parse HEAD
git status --short
git diff --stat
git diff -- scripts/probe_windows_build_context.py tests/test_windows_build_context.py
git add -- scripts/probe_windows_build_context.py tests/test_windows_build_context.py
git add -f -- docs/nbl/specs/2026-10-09-windows-build-context-failure-design.md docs/nbl/plans/2026-10-09-windows-build-context-failure-diagnostic.md
git add -- docs/nbl/plans/2026-10-09-windows-pe-reader-foundation.md docs/nbl/specs/2026-10-09-windows-build-context-rejection-research.md docs/agent-landscape-live.md
git diff --cached --name-only
git diff --cached --check
```

命令是已知候选清单，不授权混入未知root dirty。root发布前核上述历史/研究/landscape确实是本片收尾；若还有新的实际相关证据文档，先说明精确路径、纳入Step7/8验证、再逐路径暂存。不能 `git add .`/`git add -A`、不能创建分支或修改vendor。force-add只用于已审查的新spec/plan单路径，若其它文档ignored只对已核路径显式force；不扩大源scope。

- [x] **Step 2: root 在 main 精确阶段 commit/push，读取远端新 SHA。**

```bash
git commit -m "fix(ci): classify Windows build-context rejection without payload"
git push origin main
git rev-parse HEAD
git ls-remote origin refs/heads/main
git status --short
```

Expected：提交实际成功、origin/main与HEAD精确相同；报告实际SHA和保留的无关dirty。用户已授权此阶段main发布，不能新增权限；若推送受拒先定位真实原因/现有authority，禁止force-push、禁绕过检查。不得提前标记发布完成。

- [x] **Step 3: 派独立只读观察者绑定新SHA，分别读取Windows四格日志和jobs/artifacts。**

root先用实际新SHA找到新 run，观察者不能把118a/d365窗口代新SHA，不重新触发workflow或增签名权限。只读命令先列精确run与headSha：

```bash
diagnostic_commit=$(git rev-parse HEAD)
gh run list --workflow windows-helper-provenance.yml --commit "$diagnostic_commit" --limit 10 --json databaseId,headSha,status,conclusion,url
gh run list --workflow ci.yml --commit "$diagnostic_commit" --limit 10 --json databaseId,headSha,status,conclusion,url
diagnostic_provenance_run=$(gh run list --workflow windows-helper-provenance.yml --commit "$diagnostic_commit" --limit 1 --json databaseId --jq '.[0].databaseId // empty')
test -n "$diagnostic_provenance_run"
gh run view "$diagnostic_provenance_run" --json databaseId,headSha,status,conclusion,jobs,url
gh run view "$diagnostic_provenance_run" --log
gh api "repos/ayukyo/icode/actions/runs/$diagnostic_provenance_run/artifacts"
```

已只读核实际文件名为 `windows-helper-provenance.yml` 和 `ci.yml`；观察时再核 `rg --files .github/workflows`、run headSha 与 main精确相同。没有匹配run时以上test失败，保留unknown并继续产品提供的只读等待/监控，不用历史run补齐。观察者按工具结构化实参读取确认的run/jobs/raw log/artifacts，长原日志分片完整读且不只依赖摘要，记录 Windows x64/arm64 × Python3.11/3.12 每格状态、原始context首行/失败闭JSON或成功receipt、后续PE采集/签名/安装与artifact是否实际发生；missing/skip/unknown分别保留。失败诊断只有query+output_capture时不推Job/EOF/timeout根因；无失败重现只说本窗口。

- [x] **Step 4: root 收独立新SHA报告，记录阶段七维证据与剩余原生门。**

受本片范围影响的stage/kind诊断实际拒绝行必须四keys/闭标签/ASCII/≤256/LF，完整原日志可解析才授诊断信用；不把物理截断行作可信回执。独立观察与root证据按run/job/headSha分别核，签名/19项安装/artifact仅据本SHA实际发生记。当前软件阶段完成不等于原生故障修复、实际PE解析/加载、Windows生产隔离或整体R2/R3通过。

交付时按真实证据填写以下固定七维报告；未经测试不能写“全覆盖/100%”。

【架构级自检报告】
- 语法/编译：列实际 portable/full/compile-j1退出码。
- 依赖/调用链：旧capture两参调用、runner复用、DEFAULT守卫实际结果。
- 逻辑/边界：12stage/10kind/4fields/256bytes、0/1query、真实RED→GREEN。
- 异常处理：ordinary诊断边界/ME-KI-SE/旧TypeError-AssertionError/异常identity实际具名结果。
- 关联模块：两源scope，capture/bootstrap/CI/runner定点结果；不改native/vendor。
- 兼容安全：两arch成功原两行、失败原首行、payload poison、文档clean/secrets/submodule。
- 可运行性：本机实际执行范围与环境skips，独立新SHA四格与未验证门明确。

## 计划作者自审与停止点

已完整映射冻结设计到Task1测试/实现和Task2/3验收，12stage、10kind、四字段、旧两参数与main关键字参数一致；全部helper有完整定义。共有21个具名新增 `test_diagnostic_` 测试方法，加 `diagnostic_api` / `diagnostic_main` / `assert_rejection` 三个辅助，合计24个新增class方法；现有golden完整替换另计，7个Python围栏完成静态AST parse。任务3工作流名按现有文件回读修正；序列化mock不可先破坏fixture已在辅助中规避，完整行另核JSON字段/重复key/精确schema类型。独立SPEC发现合法JSON的多余whitespace可穿过语义相等校验，已补ASCII/≤256之后、写前拒绝任何serialized whitespace，仍只调用serializer一次；新增具名负控含合法payload尾CR/LF/空格/tab和token间LF/CR/tab/spaces八种污染。root复核TDD要求后补test-only接口assertion guard，新测试直接或经 `diagnostic_main` 进入guard，缺接口为F，所有E无效先修fixture；接口RED不授细行为已运行信用，既有api/main_call不变。已扫描未发现占位，新增源引用均在当前文件/现有fixture或明确import中定义。代码只作静态AST检查，不运行任何计划样例、RED/GREEN命令或功能测试。作者只能创建本文件；root既有reader plan dirty保留。计划双审与实现/软件/原生结果均未在本计划编写时声称通过。

---
## root 实施与验收履历

2026-10-09 作者真实 TDD：测试先行的有效 RED 原摘要 `Ran 41 tests in 0.124s / FAILED (failures=42)`，exit1、0E/skip；42是断言记录，不是42个独立方法。21新增方法的接口守卫产生41记录（18单项、11stage、10当时解析subTest、2arch），旧golden缺rejection另1F。接口RED不证明细行为已运行。首次生产补丁漏helper造成中间42F/170E，修正后消除；该实施遗漏不计有效RED或通过信用。最终同环境GREEN `Ran 41 tests in 0.239s / OK`，exit0、0F/E/skip。自审补强增加SDK、ordinary marker恢复及serializer/write0等负控；最终仍21新增tests、3helpers，作者SPEC→QUALITY自审C0/I0/M0并STOP。

冻结两源码：probe326行SHA256 `972068e700b642cd63f6971127bf719d5e81fb3c66c5cfcbfdc341a05a9e40d7`；tests1026行 `37036bdd3498b4d8572363626fad5fb9a498a33d04dad670318464d22a81381f`。root全文回读与独立纯AST确认原7helper、HostCMake与所有旧方法保持，唯一旧golden允许变更；旧capture67行仍两参数调用，完整业务diff无新增I/O/预算/runner改动。

fresh实施SPEC C0/I0/M0，41P/0F/E/skip/0.283s/exit0；不同freshQUALITY C0/I0/M0，41P/0F/E/skip/0.204s/exit0；均全文两源/冻结设计/计划、审前后两源SHA不变并只读STOP。120stage/kind组合是classifier mock输出矩阵，不是120真实业务故障。root关联定点134total/130P/0F/E/4平台skip/6.332s/exit0；skip分别macOS原生zombie/ps、Windows Job启动、Windows后代pipe清理、Windows超时pipe清理，新增portable零skip。

root串行20轮每轮84P/0F/E/skip，实际合计1680执行/exit0，不是1680新增方法。DEFAULT随后启动；完整preflight、编译、最终文档/密钥/vendor门及本片提交/远端新SHA观察仍待实际结果。Python3.11.15、Go1.27.1、所有构建并发1；当前基线仍d365/vendor1693651，原生与整体R2/R3无新增完成信用。

新root独立研究路径 `docs/nbl/specs/2026-10-09-provider-endpoint-and-secret-research.md` 纳入本片Step7精确两轮文档清单及发布候选。固定OpenCode/Codex/CPython与供应商官方文档仅作下一R3设计输入；独立证据审查最初两个定位M修正为LoopResult.error/loop315后C0/I0/M0，文档SHA `1ebeeda075935a0e2bf8edaa35ddd40655abbff55f10fd7354703f69fce31ab7`。未读KEY、模型HTTP、探测旧域名或修改后端；不扩本片两个源码。

root后续实际软件门：DEFAULT539P/0F/E/skip/163.745s/exit0，原bootstrap byte binding PASS。随后原三道preflight全部exit0：完整2394total/2335P/59既有环境skip/0F/E，unittest484.538s；原tests子调用一次、完整argv/kwargs核相等、返回对象不改、wrapper结束还原。child wall484.855043s、preflight wall486.051765s、child exit0，byte binding PASS；不能将59平台/工具skip计为native验收。

compileall实际-j1/exit0/wall0.483069s，缓存仅仓外`/tmp/icode-context-diagnostic-pyc-Qc96Ny`；治理/site/landscape/diff逐项exit0。相关文档的最终两轮clean、冻结守卫及本片提交/新SHA观察尚待，源码仍原两冻结SHA。

【架构级自检报告】

- 语法/编译：portable定点、DEFAULT、原完整unittest与compile-j1实际通过。
- 依赖/调用链：旧capture两参ABI、原7helper与DEFAULT选择保持；bootstrap/runner关联定点通过。
- 逻辑/边界：12stage/10kind/4fields/256bytes、真实解析拒绝、0/1query与20轮通过，历史接口RED不冒领行为信用。
- 异常处理：具名ordinary/fatal/旧编程错误与identity负控通过，只授已测试边界，不承诺所有环境故障。
- 关联模块：源码限本片两路径，runner/native/vendor/workflow未改；平台skip如实保留。
- 兼容安全：成功原两行/失败原首行、exception payload poison通过；最终密钥/vendor/文档门另据实际结果更新。
- 可运行性：本机软件合同通过；原生Windows新SHA、实际成品PE/加载、配额/隔离及模型/R2/R3未获本片信用。

本片预计发布精确7路径：两源码及本计划、冻结设计、root新provider研究、历史reader计划收尾、持续对照，共五文档。旧rejection研究只参与一致性扫描，未修改不暂存。下一R3设计`docs/nbl/specs/2026-10-09-r3-provider-transport-privacy-design.md`已独立静态SPEC→不同QUALITY C0/I0/M0，计划仅文档编写中；其设计/计划属于下一片，本片不暂存且不在持续对照新增未发布链接，也不在完整守卫期间实施后端。

root最终守卫实际：精确六文档第一/第二轮各0疑似项/exit0，新增provider研究已明确加入清单；治理/site/landscape/diff/secrets/submodule再次逐项exit0。两源SHA和冻结设计ca76a993不变，vendor HEAD/gitlink1693651且工作树空。上述七维的本片兼容安全最终门通过；更新本状态后仍重跑当前文档连续两轮clean，再核精确index，不能把Task3提交/观察提前标通过。下一R3设计/计划只留下一片，旧全文检查命令与测试scope没有改。

发布后实际履历：root状态更新后的当前六文档连续两轮各0疑似项，再次治理/site/landscape/secrets/submodule/diff全exit0；精确index为上述7路径，逐项index bytes=工作树，两源与冻结设计SHA对应双审和完整测试。普通git add因父docs忽略规则返回1但已暂存已跟踪路径；随后只对明确七路径中的已核文档force-add，未扩大目录，最后exact index/diff检查通过。commit与push分别exit0，新SHA `ef43f6f316d319a530f4ffc9df002e63a057f7a0`，parent d365；远端ls-remote只main且SHA相同，root官方GitHub API亦核main/parent/tree。

root00:05:59UTC绑定新CI37862964280 queued、provenance37862964266 in_progress、Pages37862964261 in_progress，各head_sha精确ef43。已派新的独立只读观察者；尚无终态/四格/实际失败闭JSON或成品信用，不重跑/取消或借旧d365补齐。下一R3传输隐私仅设计双审已过、独立计划编写中，不在本片源冻结期间改后端。

ef43观察中间事实（不替代最终run结论）：Pages已completed/success，root一次独立读取完整67行deploy日志，job113602891841/artifact11587141330/build_version精确ef43，00:06:01.598Z Reported success。随后root各一次取得Windows Reviewer x64 job113602846304与arm64 job113602846072的完整decoded日志，分别1828/1878行；全返回保存、只对源SHA/镜像与决定性尾段逐行回读，不冒称逐行读完全部日志。两格均1test/1F、候选exit78/cleanup=true/child_token_receipt=None；IPv4/IPv6 error10035、wait_expired=true、connect_denied=false，private-network正控exit91/credit=false，WFP capability订阅return5、classify未尝试，runner观察者有效但no_matching_event、capture archive_member_missing。上述不能算网络DENY或确认根因，也不授R2/R3通过信用。CI/签名仍由独立观察者按同SHA继续，不重复轮询已终态Pages或旧d365/118a。

### Python JSON 测试可移植性复核基线

ef43新CI的Python3.12.15 job113602846168在00:13:28UTC出现具名断言失败；root一次取得完整281行decoded日志，逐行核决定性234–255段。深度2000、4001字节的顶层数组在context预算4096内；测试固定期待validation_runtime，而该窗口实际context_validate/validation_value，旧首行及四字段仍闭合。生产分类忠实于实际异常，不能改分类或放宽安全准入来配合测试。

| 基线项 | 已绑定事实与未观察边界 |
| --- | --- |
| identity/time | GitHub hosted Linux/x64 job113602846168，Python3.12.15；原始失败00:13:28UTC；非用户目标设备，不适用物理序列号 |
| repo/runtime | job checkout ef43；分析仓库 `/home/orbbec/git/icode` 分支main/HEAD ef43，vendor1693651；验证前源码冻结、dirty仅root诊断履历 |
| artifact/evidence | 原CI完整decoded文本保存并定点回读；未下载或执行远端二进制；当前问题为portable测试假设，不是成品隔离失败归因 |
| verification | 本机现有Python3.11.15同方法1P/0.055s；3.12.13为1F/0E/skip/0.147s，3.13.12为1F/0E/skip/0.168s，均独立串行重现；本机补丁尚未验收，非远端3.12.15同版本证明 |
| parser boundary | root离线直接json.loads比较100/2000/8000层：3.11为list/RecursionError/RecursionError；3.12.13和3.13.12均为list。不能把8000层转到输出预算后预设runtime，不能推广全部Python实现的阈值 |
| unresolved/ceiling | 已支持测试固定递归阈值不跨版本；仅限该测试原因。root派单方法最小修正与三版本TDD，再fresh双审和完整守卫；新发布/远端结果待证，不授R2/R3总验收 |

方案：用100层、201字节有效顶层数组固定触发原context结构ValueError/query0，不改生产任何代码、预算或标签。已有RecursionError→validation_runtime分类器类型正控保留；不冒称这个新向量是真实递归拒绝证明。此次紧急小修沿用本阶段已核独立研究，不重复20竞品扫描，不让研究或下一个后端实现混入测试修复。后续所有修复结果按新源码SHA另记，不能回写ef43 CI为通过。

ef43主CI已终态：root一次独立取得run37862964280/jobs全部44条/artifacts0，全部head_sha精确ef43，00:16:09UTC completed/failure，36success/5failure/3workflow skip。五失败逐项是Python3.12.15、双Windows Workspace、双Reviewer，不将跳过或软件成功抵消。root另一次取得Python3.11、Linux/Mac ARM workspace和Mac Intel原生日志：Python3.11完整2394total/2323P/71skip/0F/E/604.742s；3.12为2394/2322P/71skip/1F/0E/424.518s。Linux及Mac ARM DEFAULT分别539P/0skip/225.272s、539P/0skip/224.668s，随后各75P。Windows x64/arm64分别533total/511P/1F/1E/20skip/333.218s与347.836s，root各取完整429/480行并逐读失败尾段；ContractEngineering779的Git10093和1017的dispatch0≠1/Git10038保留。两格snapshot观察first git_metadata/listing/mask16，second completed，call returned；不推写入者或稳定性根因。Mac Intel两个slow deadline实际ok，但conformance6/10/critical=false/platform_critical=false/ready=false，resource_limits仍unverified，不授quota修复信用。

签名validate job113602845025已success，root一次取得完整430行并逐读397–403实际三guard OK和治理通过；Python3.11.17/Go1.27.1、独立verifier fixture9P。quiet完整preflight不提供独立完整测试计数，不借用其它窗口总数。其后四格实际job x64/3.11=113605822271、x64/3.12=113605822261、arm64/3.11=113605822253、arm64/3.12=113605822239，仍按此run待最后终态，不能预先勾Task3 Step4。

ef43窗口收尾：三个run均终态且独立观察者STOP，CI36success/5failure/3skip、provenance5/5success（00:21:47UTC）、Pages2/2success；不再轮询。root另一次取得签名终态run/全部5jobs/全部4artifacts，并各一次取得四格完整decoded日志（x64及ARM3.12各730行、ARM3.11为779行）；全保存并解析回执，仅源绑定、context、采集/attestation、19脚本阶段和上传段逐行回读，不称全部人类日志已通读。四格VS18 2026/v145/MSVC19.51.36260.0、VCTools14.51.36231、SDK10.0.26100.0、MSBuild18.10.1-1.26427.6+3cd27c13e，Python3.11实际3.11.9、3.12实际3.12.10，Go1.27.1及MSBuild工具路径匹配架构。context原两行PASS；本窗口无原生失败闭JSON，不授其实际query故障定位信用。

| 格子/job | helper SHA256 / attestation | artifact / ZIP SHA256 / bytes |
| --- | --- | --- |
| x64/3.11，113605822271 | 9f8132cdc9d2ac2d06b232656574a5074680090b8b4144c5403e5b83df7971b9 / 54144584 | 11587461842 / 6da47f2c2a85e00f5539f5bb3273de06bca338997d2a99c668f0805e35c6e0b8 / 8359559 |
| x64/3.12，113605822261 | 28188b5a4d5c398ef6877a7ff8fa243d9b24b2115874670164792a76012b9cd6 / 54144764 | 11587503000 / 0c3ecc7f03af629beb70a6b4144a71c6421e62740c1340338b9c11a5717aca85 / 8359441 |
| ARM64/3.11，113605822253 | fa8f336343581343178105df94b44a2248e92fe85cfb92b943c14bbee02a5b05 / 54145211 | 11587702707 / 417c4b8b344cfe205989a7d4f0e4b177facb34165774496ac72253e85c88961a / 7569655 |
| ARM64/3.12，113605822239 | 9d32a2a3423cb47f4687e40cb383194a1846c5dc8f34a2307c2a4868779c5eab / 54145094 | 11587846176 / 5ef814769df046428df3d70d1051d4dabd89cc83d2da7902ddcc68807235e2d7 / 7569647 |

root独立比对四格采集helper_hash=attestation subject，上传ZIP digest/ID/size=artifact API且run/main/sourceSHA全精确ef43；只读文本，不下载成品或独立做成品密码学/PE解析。四格各19个实际安装脚本阶段PASS（ARM3.11为704–722，其它655–673），含cryptographic/offline verifier、实际negative controls、bytebinding/direct-volume/metadata及refusal；9fixture unittest另计。四CAPTURED均parse_complete/runtime_load_verified/source_launch_verified=false，不能因签名成功翻转。Pages artifact API的唯一11587141330同run/sourceef43、313411B、ZIP sha25622930eacaa75f0bb3ea0ad5eeec3ad6484a508bae99065e2b4be4956a8d6ae1b与日志对应。本Task3仅发布/独立观察结束，CI失败与R2/R3保持未通过。

### 单方法兼容修正实施履历（尚未发布）

fresh作者改前独立命名方法：3.11.15为1P/0.058s；3.12.13为1F/0E/skip/0.121s、3.13.12为1F/0E/skip/0.224s，两RED均同固定标签失配、exit1。仅指定方法+2/-1：新增原因注释、100层数组/validation_value，无production改动或版本分支/skip/宽标签。GREEN完整class三版各41P/0F/E/skip（0.215/0.299/0.319s），3.11关联三class84P/0.444s，全exit0；207为执行次数，不是207新增方法。SPEC→QUALITY作者自审均通过STOP。

tests新冻结SHA256 `88ccaec7a27c3d5a9264313dc5d3049e50f08d52754184e04bf88a0c73323cac`（1027行）；probe仍972068e7、runner2b145db4、冻结设计ca76a993，方法外字节保持。fresh独立SPEC C0/I0/M0、三版各41P/0F/E/skip（0.205/0.288/0.327s）；不同freshQUALITY C0/I0/M0、三版各41P/0F/E/skip（0.216/0.248/0.473s），前后源SHA一致、只读STOP。root关联7class134total/130P/4原平台skip/0F/E/6.442s/exit0（首次输出部分截断，仅实际摘要及决定段信用，未声称全行阅读）；portable无skip。root随后20轮各84P/0F/E/skip、1680执行/exit0。

修后独立软件门：DEFAULT539P/0F/E/skip/163.858s/exit0、bootstrap byte binding PASS；原完整三道全部exit0，2394total/2335P/59环境skip/0F/E/484.328s。原tests子调用一次、完整argv/kwargs绑定核相等且返回对象不改，child wall484.620307s、preflight wall485.730703s、结束恢复wrapper，byte binding PASS。此处仅本轮冻结源，不混用ef43修前记录。compileall -j1实际exit0/wall0.487686s，缓存仅仓外 `/tmp/icode-json-portability-pyc-Te8EkL`；治理/site/landscape/diff各exit0。最后文档连续两轮clean、密钥/vendor及发布仍待实际结果。

【架构级自检报告】（本次三行测试修正，非整体R2/R3）
- 语法/编译：三版本class、DEFAULT、原完整unittest及compile-j1通过。
- 依赖/调用链：生产probe/runner及既有调用ABI未改，配对选择守卫通过。
- 逻辑/边界：确定性201字节数组校验结构拒绝；独立类型分类仍严格测试RecursionError，无阈值假设。
- 异常处理：真实UTF-8/JSON/XML及闭标签/预算/poison既有定点通过；不声称所有原生异常已覆盖。
- 关联模块：仅单方法三行改动，原方法外字节相同；其余改动为窗口履历。
- 兼容安全：本机3.11.15/3.12.13/3.13.12通过；最终保密与文档守卫据实补录，ef43的3.12.15旧失败保留。
- 可运行性：本机冻结源可运行；新远端CI及Windows产品总验收尚未取得通过信用。

发布前最终门：精确六文档连续两轮各0疑似项/exit0，密钥/子模块各exit0；vendor HEAD=gitlink1693651且工作树空。probe/tests/design冻结SHA一致，实际runner路径 `src/icode/runner.py` SHA2b145db4不变（初次误用不存在的scripts路径，已按probe真实import定位重核，不将失败命令报通过）。治理/site/landscape/diff实际通过。当前状态更新后再执行两轮文档clean并精确暂存三路径；提交/远端新窗口另外记录，下一R3设计/计划/研究留后续阶段。

**Execution Mode:** serial

执行链：新唯一作者Task1→fresh全局SPEC→不同QUALITY→root Task2→root Task3与独立新SHA观察。计划作者到此STOP；root fresh计划双审通过后，按已读 SDD 派新实施作者，不由计划作者自动handoff或再次派代理。
