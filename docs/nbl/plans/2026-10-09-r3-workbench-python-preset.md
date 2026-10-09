# R3 Workbench Python Preset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development (recommended) or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 由可信 workbench CLI 启动者显式选择固定 Python unittest 预设，接通现有宿主工程检查，并固定同次 execute 的首次工程 Plan。

**Architecture:** 新冻结 provider 只构造既有 VerificationCheck/VerificationPlan；CLI 不读取工程配置或浏览器命令。NativeChainExecutor 仅对精确内置 provider 类型使用调用内局部 Plan，其余 provider 和 adapter 合同不变。runner、broker、资源、Reviewer、tree、CP/evidence 的既有拒绝门负责实际执行准入。

**Tech Stack:** Python 3.11/3.12 标准库、unittest、argparse、现有 ICODE 合同与跨平台 workspace CI。

---

本计划起草基线为 main `6ded1d3c16c265fda16fa6506cb57c29067b5fbd`，vendor `1693651c1bd7daad3272eb054f0f81d6f254d08d`。设计 [2026-10-09-r3-workbench-python-preset-design.md](../specs/2026-10-09-r3-workbench-python-preset-design.md) SHA256 `82927b604112b74998aa1f904feede09c51a5782489bae3c57d9f7406647da75`，研究 [2026-10-09-workbench-preset-upstream-refresh.md](../specs/2026-10-09-workbench-preset-upstream-refresh.md) SHA256 `33ca31bc6be7b5a1769010ad113afda3efedd3015fbd37d06c10d9bf4bb8b33e`。root 已确认不同独立设计 SPEC/QUALITY 均 C0/I0/M0 并 STOP；这是设计批准，尚无实现或新增运行结果。

三问已有当前源码证据：工作台未传 provider，正式 code/deepcheck 被 `verification_plan_required` 阻断；已有固定孤立 unittest 语法和 provider 接口可复用；调用链为 CLI → NativeChainExecutor → run_chain → run_contract_step → 宿主 verification → resource broker → 独立 Reviewer/受测 tree/CP/evidence。起草者完整读 writing-plans、设计/研究、cli/autonomy/engineering_verification、workbench/autonomy 测试、两个 CI 选择文件，定点核 runner 准入、broker 最小限额与孤立模板合同。没有导入生产模块、运行测试或模型 HTTP。

用户 main-only 和持续自主阶段授权覆盖技能的默认 worktree、逐任务提交和例行等待。执行模式为串行：每实现任务一个 fresh writer，源写入与任何测试串行；作者自审后先 fresh SPEC、再另一 fresh QUALITY，前后绑定相同源码 SHA。每任务禁止 commit/push，root 全片完整门通过后才精确提交 main。此计划作者只写本文，停止，不自动执行技能 handoff。

## 边界与文件职责

| 路径 | 职责 |
| --- | --- |
| `src/icode/verification_presets.py`（新增） | 冻结启动解释器身份、校验 context/policy、固定 argv 构造 Plan；TYPE_CHECKING 导入 ExecutionContext 避免循环 |
| `src/icode/cli.py` | workbench 唯一可选预设、未启用自动的前置拒绝、真实 Native 接线 |
| `src/icode/autonomy.py` | 精确内置类型首次有效 Plan 的调用内局部复用 |
| `tests/test_verification_presets.py`（新增） | 工厂真实正控与 portable 身份/输入/fatal 负控 |
| `tests/test_workbench.py` | parser/main/cmd 到真实 Native 的配置与调用接线 |
| `tests/test_autonomy.py` | 单次、新 execute、线程、漂移及第三方兼容 |
| `scripts/run_workspace_ci.py` | DEFAULT 唯一完整加载新增测试模块，保留全部旧选择 |
| `tests/test_run_workspace_ci.py` | 选择覆盖和无静态 skip 配对守卫 |

只改上述八个源/测试选择路径；必要阶段文档为本文、冻结设计、定点研究和 `docs/agent-landscape-live.md` 的相关条目。不改 runner/broker/config/loop/GUI/native/vendor/workflow/依赖，不新增端点、权限、UI/API readiness 协议或 provider 注册。预设不授权 macOS/Windows 工程执行，不提供普通 subprocess fallback。启动解释器在可信 CLI 构造时冻结；工程根 inode、环境、run/ticket 在本次第一工程步骤冻结，不能称 session/intent 创建起全部对象已冻结。

普通构造故障固定为 ConfigError，不含路径/异常正文；MemoryError/KeyboardInterrupt/SystemExit 在 provider 构造和 CLI 直接 cmd 层保留同一异常对象。运行期 provider 仍由 Native 的既有异常稳定码处理，不在本片改公共错误协议。Check 默认 180 秒/1 MiB；broker 实际按 check 与每步 policy 最小值收敛，不称 run 累计墙钟限额。

## 所有运行命令的固定环境

执行者每个新 shell 先定义以下函数，后文 `preset_python` 命令均在 `/home/orbbec/git/icode` 中执行。它完整保留可信解释器 lexical 路径，不搜索另一 Python。不得读取 KEY/私有配置，不请求模型 HTTP。

```bash
cd /home/orbbec/git/icode
preset_python() {
  env PATH=/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin:/tmp/icode-sigstore-go-gwCdn3/go/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 GOMAXPROCS=1 GOFLAGS=-p=1 GOTOOLCHAIN=local CMAKE_BUILD_PARALLEL_LEVEL=1 /tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B "$@"
}
git branch --show-current
git rev-parse HEAD
git status --short
git -C vendor/icode-skill rev-parse HEAD
git -C vendor/icode-skill status --porcelain
sha256sum docs/nbl/specs/2026-10-09-r3-workbench-python-preset-design.md docs/nbl/specs/2026-10-09-workbench-preset-upstream-refresh.md
```

Expected：main、上述 HEAD/vendor、vendor clean、两冻结 SHA 一致。本文与必要未跟踪设计/研究不等于未知用户改动；writer 精确核当前 dirty owner，不覆盖其它改动。若 main 已合法前进，root 重新确认相关源码/规格，不创建分支或静默沿用旧锚。

### Task 1: 冻结 Python 工厂与真实 CLI 接线

**状态**
- [x] 任务完成

**Dependencies:** None
**Parallelizable:** No (同一 writer 修改工厂与 CLI 及两测试；测试不得与写源并行)

- [x] **Step 1: 新增工厂测试，先用接口断言取得有效 RED。**

用 apply_patch 新建 `tests/test_verification_presets.py`，全文如下。模块不存在时 `_provider_type` 明确 assertion FAIL，不能把 ImportError/fixture ERROR 算作 RED。

```python
"""Host-owned Python preset contracts; fixtures do not grant native authority."""

from __future__ import annotations

import dataclasses
import importlib
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from icode.autonomy import ExecutionContext
from icode.config import ConfigError
from icode.engineering_verification import VerificationPlan, _executable_identity
from icode.sandbox_policy import NetworkMode, SandboxPolicy
from tests._support import temp_workspace


class TestPythonUnittestPlanProvider(unittest.TestCase):
    def _provider_type(self):
        name = "icode.verification_presets"
        self.assertIsNotNone(importlib.util.find_spec(name), "Python preset module is missing")
        module = importlib.import_module(name)
        provider_type = getattr(module, "PythonUnittestPlanProvider", None)
        self.assertTrue(callable(provider_type), "Python preset provider is missing")
        return provider_type

    def _inputs(self, root, *, step="code", ticket="PRESET-1", run="actual-run"):
        root = root.resolve()
        context = ExecutionContext(ticket, root / "ticket", root, "check", "code_in_progress", ())
        policy = SandboxPolicy(
            1, run, ticket, step, root, (root,), (root,), (), (root / ".git",),
            NetworkMode.DENY, (), 8, 30, 65536, (root / ".git",),
        )
        return context, policy

    def test_factory_interface_exists(self):
        self._provider_type()

    def test_real_interpreter_fixed_argv_steps_limits_and_policy_identity(self):
        provider_type = self._provider_type()
        executable = Path(sys.executable)
        provider = provider_type(executable)
        with temp_workspace() as root:
            context, policy = self._inputs(root)
            plan = provider(context, policy)
            self.assertIs(type(plan), VerificationPlan)
            self.assertEqual(plan.workspace_root, root.resolve())
            self.assertEqual((plan.run_id, plan.ticket_id), (policy.run_id, context.ticket_id))
            self.assertEqual(plan.steps, ("code", "deepcheck"))
            self.assertEqual(len(plan.checks), 1)
            check = plan.checks[0]
            self.assertEqual(check.argv, (
                str(executable), "-I", "-B", "-X", "utf8", "-m", "unittest", "discover",
                "-s", str(root.resolve()), "-t", str(root.resolve()),
            ))
            self.assertEqual((check.check_id, check.kind, check.adapter, check.cwd, check.required),
                             ("python-unittest", "test", "unittest_summary_v1", ".", True))
            self.assertEqual((check.timeout_seconds, check.output_limit_bytes), (180, 1024 * 1024))
            self.assertEqual(check.executable_identity, _executable_identity(executable))
            self.assertEqual(plan.workspace_identity, (root.stat().st_dev, root.stat().st_ino))
            self.assertTrue(plan.environment)
            with self.assertRaises(dataclasses.FrozenInstanceError):
                provider.executable = executable

    def test_lexical_launcher_is_preserved_without_resolve_or_path_search(self):
        provider_type = self._provider_type()
        with temp_workspace() as root:
            context, policy = self._inputs(root)
            executable = root.resolve() / "selected-venv" / "bin" / "python"
            with patch("icode.verification_presets._executable_identity", return_value="launch") as startup, \
                    patch("icode.engineering_verification._executable_identity", return_value="launch") as check_identity:
                provider = provider_type(executable)
                plan = provider(context, policy)
            self.assertEqual(provider.executable, executable)
            self.assertEqual(plan.checks[0].argv[0], str(executable))
            self.assertEqual([call.args[0] for call in startup.call_args_list], [executable, executable])
            check_identity.assert_called_once_with(executable)

    def test_constructor_rejects_nonabsolute_and_unavailable_without_details(self):
        provider_type = self._provider_type()
        for executable in (None, "", Path("."), Path("python")):
            with self.subTest(executable=executable), self.assertRaises(ConfigError) as caught:
                provider_type(executable)
            self.assertEqual(str(caught.exception), "Python unittest 预设解释器不可用")
        for error in (OSError("PRIVATE_PATH"), RuntimeError("PRIVATE_BODY"), ValueError("PRIVATE_BODY")):
            with self.subTest(error=type(error).__name__), \
                    patch("icode.verification_presets._executable_identity", side_effect=error), \
                    self.assertRaises(ConfigError) as caught:
                provider_type(Path(sys.executable))
            self.assertEqual(str(caught.exception), "Python unittest 预设解释器不可用")
            self.assertNotIn("PRIVATE", str(caught.exception))
            self.assertNotIn(sys.executable, str(caught.exception))

    def test_constructor_fatal_exceptions_preserve_original_object(self):
        provider_type = self._provider_type()
        for error in (MemoryError("fatal"), KeyboardInterrupt("fatal"), SystemExit(19)):
            with self.subTest(error=type(error).__name__), \
                    patch("icode.verification_presets._executable_identity", side_effect=error), \
                    self.assertRaises(type(error)) as caught:
                provider_type(Path(sys.executable))
            self.assertIs(caught.exception, error)

    def test_launch_identity_drift_refuses_before_check_construction(self):
        provider_type = self._provider_type()
        with temp_workspace() as root:
            context, policy = self._inputs(root)
            with patch("icode.verification_presets._executable_identity", side_effect=("startup", "changed")):
                provider = provider_type(Path(sys.executable))
                with patch("icode.verification_presets.VerificationCheck") as check, self.assertRaises(ValueError):
                    provider(context, policy)
                check.assert_not_called()

    def test_check_construction_identity_drift_refuses_before_plan(self):
        provider_type = self._provider_type()
        with temp_workspace() as root:
            context, policy = self._inputs(root)
            with patch("icode.verification_presets._executable_identity", return_value="startup"), \
                    patch("icode.engineering_verification._executable_identity", return_value="changed"):
                provider = provider_type(Path(sys.executable))
                with patch("icode.verification_presets.VerificationPlan") as plan, self.assertRaises(ValueError):
                    provider(context, policy)
                plan.assert_not_called()

    def test_wrong_workspace_ticket_step_and_missing_policy_refuse_before_identity(self):
        provider_type = self._provider_type()
        provider = provider_type(Path(sys.executable))
        with temp_workspace() as root, temp_workspace() as other:
            context, policy = self._inputs(root)
            variants = (
                (context, None),
                (context, object()),
                (dataclasses.replace(context, ticket_id="OTHER"), policy),
                (dataclasses.replace(context, workspace=other.resolve()), policy),
                (context, dataclasses.replace(policy, step="plan")),
                (context, dataclasses.replace(policy, step="task")),
            )
            for candidate_context, candidate_policy in variants:
                with self.subTest(policy=candidate_policy), \
                        patch("icode.verification_presets._executable_identity") as identity, \
                        self.assertRaises(ValueError):
                    provider(candidate_context, candidate_policy)
                identity.assert_not_called()

    def test_direct_provider_calls_make_new_plans_for_actual_runs_and_steps(self):
        provider_type = self._provider_type()
        provider = provider_type(Path(sys.executable))
        with temp_workspace() as root:
            context, policy = self._inputs(root)
            first = provider(context, policy)
            second = provider(context, dataclasses.replace(policy, step="deepcheck", run_id="next-run"))
            self.assertIsNot(first, second)
            self.assertEqual((first.run_id, second.run_id), ("actual-run", "next-run"))
            self.assertEqual(first.steps, second.steps)


if __name__ == "__main__":
    unittest.main()
```

```bash
preset_python -m unittest tests.test_verification_presets.TestPythonUnittestPlanProvider.test_factory_interface_exists -v
```

Expected：1 assertion FAIL、0 ERROR，缺模块断言具名；若出现 import/fixture ERROR 先修测试夹具再记录 RED。

- [x] **Step 2: 添加 CLI 测试，先运行独立 parser RED。**

`tests/test_workbench.py` import 区在 `from io import StringIO` 后加 `from pathlib import Path`，在 `import re` 后加 `import sys`；用 `from contextlib import redirect_stderr, redirect_stdout` 替换原 contextlib 导入；替换 `from icode.autonomy import ExecutionResult` 为下列完整导入行；替换 CLI 导入为下列行。

```python
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from icode.autonomy import ExecutionContext, ExecutionResult, NativeChainExecutor
from icode.cli import _build_parser, cmd_workbench, main
```

在 `class TestWorkbenchCLI(unittest.TestCase):` 之后、原首方法之前插入全部以下方法。真实 parser/main/cmd 和 Native 构造不 mock；server/wait/backend 是边界 double。工厂/Native 运行细节在 Task 2 的调用链矩阵另验。

```python
    def test_verification_preset_parser_is_explicit_and_workbench_only(self):
        parser = _build_parser()
        default = parser.parse_args(["workbench", "--workspace", "/srv/project"])
        self.assertTrue(hasattr(default, "verification_preset"), "preset parser option is missing")
        self.assertIsNone(default.verification_preset)
        selected = parser.parse_args([
            "workbench", "--workspace", "/srv/project", "--enable-autonomous",
            "--verification-preset", "python-unittest",
        ])
        self.assertEqual(selected.verification_preset, "python-unittest")
        with self.assertRaises(SystemExit) as unknown:
            parser.parse_args(["workbench", "--workspace", "/srv/project", "--verification-preset", "shell"])
        self.assertEqual(unknown.exception.code, 2)
        with self.assertRaises(SystemExit) as other:
            parser.parse_args(["webui", "--verification-preset", "python-unittest"])
        self.assertEqual(other.exception.code, 2)

    def test_preset_without_autonomy_main_refuses_before_settings_backend_server(self):
        parser_args = _build_parser().parse_args(["workbench", "--workspace", "/srv/project"])
        self.assertTrue(hasattr(parser_args, "verification_preset"), "preset parser option is missing")
        output = StringIO()
        with patch("icode.cli.load_settings") as settings, \
                patch("icode.cli._build_runner") as backend, \
                patch("icode.workbench.WorkbenchServer") as server, \
                redirect_stderr(output):
            code = main(["workbench", "--workspace", "/srv/project",
                         "--verification-preset", "python-unittest"])
        self.assertEqual(code, 2)
        self.assertEqual(output.getvalue(), "错误：--verification-preset 需要 --enable-autonomous\n")
        settings.assert_not_called()
        backend.assert_not_called()
        server.assert_not_called()

    def test_real_cmd_constructs_real_native_with_selected_provider_and_old_namespace(self):
        from icode.verification_presets import PythonUnittestPlanProvider
        settings = require_skill()
        sandbox = SimpleNamespace(
            is_real_isolation=True, policy_contract_ready=True,
            wrap_policy=lambda *args, **kwargs: [], prepare_policy=lambda policy: None,
        )
        for selected, old_namespace in ((False, False), (True, False), (False, True)):
            with self.subTest(selected=selected, old_namespace=old_namespace):
                argv = ["workbench", "--workspace", "/srv/project", "--enable-autonomous", "--no-browser"]
                if selected:
                    argv += ["--verification-preset", "python-unittest"]
                args = _build_parser().parse_args(argv)
                if old_namespace:
                    del args.verification_preset
                with patch("icode.cli.load_settings", return_value=settings), \
                        patch("icode.cli._build_runner", return_value=(None, None, None, None, sandbox)), \
                        patch("icode.workbench.WorkbenchServer") as server, \
                        patch("threading.Event") as event, redirect_stdout(StringIO()):
                    server.return_value.start.return_value = "http://127.0.0.1:1234/"
                    event.return_value.wait.side_effect = KeyboardInterrupt
                    self.assertEqual(cmd_workbench(args), 0)
                executor = server.call_args.kwargs["autonomy_executor"]
                self.assertIs(type(executor), NativeChainExecutor)
                self.assertIs(executor.settings, settings)
                self.assertIs(executor.sandbox, sandbox)
                provider = executor.verification_plan_provider
                if selected:
                    self.assertIs(type(provider), PythonUnittestPlanProvider)
                    self.assertEqual(provider.executable, Path(sys.executable))
                    with temp_workspace() as root:
                        from icode.sandbox_policy import NetworkMode, SandboxPolicy
                        context = ExecutionContext("CLI-1", root / "ticket", root.resolve(), "check", "code_in_progress", ())
                        policy = SandboxPolicy(1, "cli-run", "CLI-1", "code", root.resolve(),
                            (root.resolve(),), (root.resolve(),), (), (root.resolve() / ".git",),
                            NetworkMode.DENY, (), 8, 30, 65536, (root.resolve() / ".git",))
                        plan = provider(context, policy)
                        self.assertEqual(plan.run_id, "cli-run")
                        self.assertEqual(plan.checks[0].argv[0], sys.executable)
                        self.assertEqual(plan.steps, ("code", "deepcheck"))
                else:
                    self.assertIsNone(provider)
                server.return_value.stop.assert_called_once_with()

    def test_selected_constructor_failure_is_fixed_and_precedes_backend(self):
        from icode.config import ConfigError
        args = _build_parser().parse_args([
            "workbench", "--workspace", "/srv/project", "--enable-autonomous",
            "--verification-preset", "python-unittest", "--no-browser",
        ])
        with patch("icode.cli.load_settings", return_value=require_skill()), \
                patch("icode.verification_presets._executable_identity", side_effect=OSError("PRIVATE_PATH")), \
                patch("icode.cli._build_runner") as backend, \
                patch("icode.workbench.WorkbenchServer") as server, self.assertRaises(ConfigError) as caught:
            cmd_workbench(args)
        self.assertEqual(str(caught.exception), "Python unittest 预设解释器不可用")
        backend.assert_not_called()
        server.assert_not_called()

    def test_selected_constructor_fatal_reaches_direct_cmd_unchanged(self):
        args = _build_parser().parse_args([
            "workbench", "--workspace", "/srv/project", "--enable-autonomous",
            "--verification-preset", "python-unittest", "--no-browser",
        ])
        for error in (MemoryError("fatal"), KeyboardInterrupt("fatal"), SystemExit(23)):
            with self.subTest(error=type(error).__name__), \
                    patch("icode.cli.load_settings", return_value=require_skill()), \
                    patch("icode.verification_presets._executable_identity", side_effect=error), \
                    patch("icode.cli._build_runner") as backend, \
                    patch("icode.workbench.WorkbenchServer") as server, \
                    self.assertRaises(type(error)) as caught:
                cmd_workbench(args)
            self.assertIs(caught.exception, error)
            backend.assert_not_called()
            server.assert_not_called()
```

```bash
preset_python -m unittest tests.test_workbench.TestWorkbenchCLI.test_verification_preset_parser_is_explicit_and_workbench_only -v
```

Expected：1 assertion FAIL、0 ERROR，真实 parser Namespace 无该属性；不先运行尚依赖新生产模块的整类取得 ImportError。

- [x] **Step 3: 新建完整生产工厂。**

用 apply_patch 新建 `src/icode/verification_presets.py`，全文如下。

```python
"""Explicit host-owned verification presets, never project command configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from .config import ConfigError
from .engineering_verification import VerificationCheck, VerificationPlan, _executable_identity
from .sandbox_policy import SandboxPolicy

if TYPE_CHECKING:
    from .autonomy import ExecutionContext


@dataclass(frozen=True)
class PythonUnittestPlanProvider:
    executable: Path
    _startup_identity: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        # Keep the lexical venv launcher: resolving argv0 can select base Python.
        if not isinstance(self.executable, Path) or not self.executable.is_absolute():
            raise ConfigError("Python unittest 预设解释器不可用")
        try:
            identity = _executable_identity(self.executable)
        except (OSError, RuntimeError, ValueError):
            raise ConfigError("Python unittest 预设解释器不可用") from None
        object.__setattr__(self, "_startup_identity", identity)

    def __call__(self, context: ExecutionContext, policy: SandboxPolicy) -> VerificationPlan:
        if not isinstance(policy, SandboxPolicy) or policy.step not in ("code", "deepcheck"):
            raise ValueError("invalid Python preset policy")
        root = context.workspace.resolve(strict=True)
        if (policy.workspace_root != root
                or policy.workspace_root != policy.workspace_root.resolve(strict=True)
                or policy.ticket_id != context.ticket_id):
            raise ValueError("Python preset identity mismatch")
        if _executable_identity(self.executable) != self._startup_identity:
            raise ValueError("Python preset executable changed")
        check = VerificationCheck(
            check_id="python-unittest", kind="test", adapter="unittest_summary_v1",
            cwd=".", required=True,
            argv=(str(self.executable), "-I", "-B", "-X", "utf8", "-m", "unittest",
                  "discover", "-s", str(root), "-t", str(root)),
        )
        # Check observes the executable again; a construction-window swap fails.
        if check.executable_identity != self._startup_identity:
            raise ValueError("Python preset executable changed")
        return VerificationPlan(
            workspace_root=root, run_id=policy.run_id, ticket_id=context.ticket_id,
            checks=(check,), steps=("code", "deepcheck"),
        )
```

解释器不用 `.absolute()`/`.resolve()` 改写、不用 PATH/项目配置选择替代。这里只捕获普通不可用异常；fatal 不变。TYPE_CHECKING 避免 autonomy 导入新模块后反向 runtime 导入。运行期无新错误正文外泄路径：既有 Native 捕获 provider 普通异常为固定 `verification_plan_provider_failed`。

- [x] **Step 4: 给 CLI 唯一参数并接入真实 Native。**

在 `_build_parser()` 的 `p_workbench.add_argument("--enable-autonomous", ...)` 完整调用之后、`_add_model_args(p_workbench)` 之前插入：

```python
    p_workbench.add_argument(
        "--verification-preset",
        choices=("python-unittest",),
        default=None,
        help="显式选择宿主工程检查预设（需要 --enable-autonomous）",
    )
```

在 `cmd_workbench()` 的 `from .workbench import WorkbenchServer` 之后、`settings = load_settings(args.skill_root)` 之前插入：

```python
    verification_preset = getattr(args, "verification_preset", None)
    if verification_preset is not None and not args.enable_autonomous:
        raise ConfigError("--verification-preset 需要 --enable-autonomous")
```

在同方法 `from .loop import LoopConfig` 之后、`backend, approver, budget, on_event, sandbox = _build_runner(args)` 之前插入：

```python
        verification_plan_provider = None
        if verification_preset == "python-unittest":
            from .verification_presets import PythonUnittestPlanProvider

            verification_plan_provider = PythonUnittestPlanProvider(Path(sys.executable))
```

在同方法的 `executor = NativeChainExecutor(...)` 调用里，`sandbox=sandbox,` 之后插入：

```python
            verification_plan_provider=verification_plan_provider,
```

其它参数/文案/server limits/main 捕获不改。旧 Namespace 没有新属性时等价无预设；未知 CLI 值仍 argparse 退出2。构造工厂先于 backend，防止解释器故障后发生模型后端构造。

- [x] **Step 5: GREEN、作者两阶段自审和任务双审后 STOP。**

```bash
preset_python -m unittest tests.test_verification_presets tests.test_workbench.TestWorkbenchCLI -v
git diff --check
sha256sum src/icode/verification_presets.py src/icode/cli.py tests/test_verification_presets.py tests/test_workbench.py
git diff -- src/icode/cli.py tests/test_workbench.py
```

Expected：全部新增方法实际 PASS、0 FAIL/ERROR/skip。作者先逐项对照规格，再查循环导入、固定 argv/fatal、旧 Namespace 和真实 Native 接线质量，记录七维结果与实际测试数字，不写预报 PASS。fresh SPEC 先完整读同四源+设计/研究/本任务，另一 fresh QUALITY 再核同 SHA；作者按问题修复再重跑定点，不用不同版本拼批准。根保留 SHA 后接 Task 2；writer STOP，不 commit/push/full。

### Task 2: Native 调用内局部 Plan 与兼容矩阵

**状态**
- [x] 任务完成

**Dependencies:** Task 1
**Parallelizable:** No (先复用已批准工厂，再验证两工程步骤不重新授权；唯一源 writer)

- [x] **Step 1: 添加完整 Native 测试，先取得同一 Plan RED。**

在 `tests/test_autonomy.py` 的 `class TestIntentPayload(unittest.TestCase):` 之前插入以下完整新类。它复用现有 RecordingControl/verified-session 夹具；与 Task 1 同样接口先断言存在。双重绑定 run_chain stub 是明确编排边界 double，使真实 Native 的内置 runner 分支可观察，不宣称 stub 是实际工程执行。实际 runner 拒绝门在漂移方法调用和既有关联测试另验。

```python
class TestNativePythonPreset(unittest.TestCase):
    def provider(self):
        import importlib
        import importlib.util
        name = "icode.verification_presets"
        self.assertIsNotNone(importlib.util.find_spec(name), "Python preset module is missing")
        return importlib.import_module(name).PythonUnittestPlanProvider(Path(sys.executable))

    def context(self, root, *, ticket="NATIVE-PRESET"):
        root = root.resolve()
        return ExecutionContext(ticket, root / "ticket", root, "check", "code_in_progress", ())

    def control(self, context, *, run="native-run"):
        control = RecordingControl()
        root = context.workspace.resolve()
        control.session = SimpleNamespace(policy=lambda step: SandboxPolicy(
            1, run, context.ticket_id, step, root, (root,), (root,), (), (root / ".git",),
            NetworkMode.DENY, (), 8, 30, 65536, (root / ".git",),
        ))
        return control

    def sandbox(self):
        return SimpleNamespace(
            is_real_isolation=True, policy_contract_ready=True,
            prepare_policy=lambda policy: None, wrap_policy=lambda argv, **kwargs: list(argv),
        )

    def execute_fixture(self, context, control, provider, callback):
        # Bind both symbols to the same boundary double; Native itself is real.
        with patch("icode.autonomy.run_chain", callback), \
                patch("icode.autonomy.chain_steps", return_value=("code", "deepcheck")), \
                patch("icode.autonomy.ControlPlane.trace", return_value=SimpleNamespace(
                    returncode=0, data={"ticket_id": context.ticket_id, "status": "code_in_progress"})):
            executor = NativeChainExecutor(require_skill(), backend=FakeBackend([]),
                step_runner=callback, sandbox=self.sandbox(), verification_plan_provider=provider)
            return executor, executor.execute(context, control)

    def test_exact_builtin_same_execute_reuses_one_plan_and_shared_budget(self):
        with temp_workspace() as root:
            context = self.context(root)
            calls = []
            def step(settings, **kwargs):
                calls.append(kwargs)
                return ChainReport(delivered=True)
            provider = self.provider()
            provider_type = type(provider)
            original = provider_type.__call__
            observed = []
            def create(candidate, context, policy):
                plan = original(candidate, context, policy)
                observed.append(plan)
                return plan
            with patch.object(provider_type, "__call__", create):
                _executor, result = self.execute_fixture(context, self.control(context), provider, step)
            self.assertEqual(result.state, "succeeded")
            self.assertEqual(len(observed), 1, "builtin must construct only the first engineering plan")
            self.assertEqual([call["steps"] for call in calls], [("code",), ("deepcheck",)])
            self.assertIs(calls[0]["verification_plan"], calls[1]["verification_plan"])
            self.assertIs(calls[0]["budget_tracker"], calls[1]["budget_tracker"])
            self.assertIs(calls[0]["verification_plan"], observed[0])

    def test_new_execute_same_executor_creates_new_plan_for_new_run(self):
        with temp_workspace() as root:
            context = self.context(root)
            calls = []
            def step(settings, **kwargs):
                calls.append(kwargs)
                return ChainReport(delivered=True)
            with patch("icode.autonomy.run_chain", step), \
                    patch("icode.autonomy.chain_steps", return_value=("code", "deepcheck")), \
                    patch("icode.autonomy.ControlPlane.trace", return_value=SimpleNamespace(
                        returncode=0, data={"ticket_id": context.ticket_id, "status": "code_in_progress"})):
                executor = NativeChainExecutor(require_skill(), backend=FakeBackend([]), step_runner=step,
                    sandbox=self.sandbox(), verification_plan_provider=self.provider())
                self.assertEqual(executor.execute(context, self.control(context, run="one")).state, "succeeded")
                self.assertEqual(executor.execute(context, self.control(context, run="two")).state, "succeeded")
            plans = [call["verification_plan"] for call in calls]
            self.assertIs(plans[0], plans[1])
            self.assertIs(plans[2], plans[3])
            self.assertIsNot(plans[0], plans[2])
            self.assertEqual([plan.run_id for plan in plans], ["one", "one", "two", "two"])
            self.assertIsNot(calls[0]["budget_tracker"], calls[2]["budget_tracker"])

    def test_shared_executor_concurrent_tickets_do_not_share_plan_or_budget(self):
        with temp_workspace() as parent:
            roots = (parent / "first", parent / "second")
            for root in roots:
                root.mkdir()
            contexts = [self.context(root, ticket=f"THREAD-{index}") for index, root in enumerate(roots)]
            calls = []
            results = []
            failures = []
            lock = threading.Lock()
            barrier = threading.Barrier(2)
            def step(settings, **kwargs):
                with lock:
                    calls.append(kwargs)
                if kwargs["steps"] == ("code",):
                    barrier.wait(ASYNC_TEST_TIMEOUT_SECONDS)
                return ChainReport(delivered=True)
            def trace(_self, out_dir):
                ticket = next(context.ticket_id for context in contexts if context.out_dir == out_dir)
                return SimpleNamespace(returncode=0, data={"ticket_id": ticket, "status": "code_in_progress"})
            with patch("icode.autonomy.run_chain", step), \
                    patch("icode.autonomy.chain_steps", return_value=("code", "deepcheck")), \
                    patch("icode.autonomy.ControlPlane.trace", trace):
                executor = NativeChainExecutor(require_skill(), backend=FakeBackend([]), step_runner=step,
                    sandbox=self.sandbox(), verification_plan_provider=self.provider())
                def invoke(context):
                    try:
                        result = executor.execute(context, self.control(context, run="run-" + context.ticket_id))
                        with lock:
                            results.append(result)
                    except BaseException as error:
                        with lock:
                            failures.append(error)
                threads = [threading.Thread(target=invoke, args=(context,)) for context in contexts]
                started = []
                try:
                    for thread in threads:
                        thread.start()
                        started.append(thread)
                    for thread in started:
                        thread.join(ASYNC_TEST_TIMEOUT_SECONDS)
                    self.assertTrue(all(not thread.is_alive() for thread in started))
                finally:
                    barrier.abort()
                    for thread in started:
                        thread.join(ASYNC_TEST_TIMEOUT_SECONDS)
            self.assertEqual(failures, [])
            self.assertEqual([result.state for result in results], ["succeeded", "succeeded"])
            groups = [[call for call in calls if call["ticket_id"] == context.ticket_id] for context in contexts]
            self.assertTrue(all(len(group) == 2 for group in groups))
            for context, group in zip(contexts, groups):
                self.assertIs(group[0]["verification_plan"], group[1]["verification_plan"])
                self.assertIs(group[0]["budget_tracker"], group[1]["budget_tracker"])
                self.assertEqual(group[0]["verification_plan"].workspace_root, context.workspace)
                self.assertEqual(group[0]["verification_plan"].ticket_id, context.ticket_id)
            self.assertIsNot(groups[0][0]["verification_plan"], groups[1][0]["verification_plan"])
            self.assertIsNot(groups[0][0]["budget_tracker"], groups[1][0]["budget_tracker"])

    def test_generic_and_subclass_provider_keep_per_step_calls(self):
        provider_type = type(self.provider())
        for mode in ("generic", "subclass"):
            with self.subTest(mode=mode), temp_workspace() as root:
                context = self.context(root)
                calls = []
                generated = []
                base = provider_type(Path(sys.executable))
                def generic(context, policy):
                    plan = base(context, policy)
                    generated.append(plan)
                    return plan
                class Subclass(provider_type):
                    def __call__(candidate, context, policy):
                        plan = super().__call__(context, policy)
                        generated.append(plan)
                        return plan
                provider = generic if mode == "generic" else Subclass(Path(sys.executable))
                def step(settings, **kwargs):
                    calls.append(kwargs)
                    return ChainReport(delivered=True)
                _executor, result = self.execute_fixture(context, self.control(context), provider, step)
                self.assertEqual(result.state, "succeeded")
                self.assertEqual(len(generated), 2)
                self.assertIsNot(generated[0], generated[1])
                self.assertIs(calls[0]["verification_plan"], generated[0])
                self.assertIs(calls[1]["verification_plan"], generated[1])

    def test_custom_adapter_keeps_signature_and_does_not_call_provider(self):
        with temp_workspace() as root:
            context = self.context(root)
            calls = []
            def provider(context, policy):
                raise AssertionError("custom adapter must not acquire a new plan")
            def custom(settings, *, backend, workspace, requirement, ticket_id, steps, out_dir,
                       approver, loop_config, budget, on_event, sandbox, policy):
                calls.append((steps, policy))
                return ChainReport(delivered=True)
            with patch("icode.autonomy.chain_steps", return_value=("code", "deepcheck")), \
                    patch("icode.autonomy.ControlPlane.trace", return_value=SimpleNamespace(
                        returncode=0, data={"ticket_id": context.ticket_id, "status": "code_in_progress"})):
                executor = NativeChainExecutor(require_skill(), backend=FakeBackend([]), step_runner=custom,
                    sandbox=self.sandbox(), verification_plan_provider=provider)
                result = executor.execute(context, self.control(context))
            self.assertEqual(result.state, "succeeded")
            self.assertEqual([item[0] for item in calls], [("code",), ("deepcheck",)])

    def test_reused_plan_identity_is_rechecked_on_later_step(self):
        with temp_workspace() as root:
            context = self.context(root)
            calls = []
            def step(settings, **kwargs):
                calls.append(kwargs)
                object.__setattr__(kwargs["verification_plan"], "run_id", "tampered")
                return ChainReport(delivered=True)
            _executor, result = self.execute_fixture(context, self.control(context), self.provider(), step)
            self.assertEqual(result, ExecutionResult("blocked", "deepcheck", "verification_plan_identity_mismatch"))
            self.assertEqual(len(calls), 1)

    def test_between_steps_root_environment_and_tool_drift_do_not_reauthorize(self):
        from icode import engineering_verification as verification, runner
        from icode.isolation import NoIsolation
        for mutation, expected in (("root", "verification_plan_identity_mismatch"),
                                   ("environment", "verification_plan_identity_mismatch"),
                                   ("tool", "verification_tool_changed")):
            with self.subTest(mutation=mutation), temp_workspace() as parent, ExitStack() as stack:
                root = parent / "workspace"
                root.mkdir()
                context = self.context(root)
                plans = []
                errors = []
                original_environment = verification._policy_environment
                def step(settings, **kwargs):
                    plan = kwargs["verification_plan"]
                    plans.append(plan)
                    if kwargs["steps"] == ("code",):
                        if mutation == "root":
                            root.rename(parent / "original")
                            root.mkdir()
                        elif mutation == "environment":
                            stack.enter_context(patch.object(verification, "_policy_environment",
                                side_effect=lambda workspace: dict(original_environment(workspace), PRESET_DRIFT="1")))
                        else:
                            stack.enter_context(patch.object(runner, "_executable_identity", return_value="changed"))
                        return ChainReport(delivered=True)
                    with patch.object(runner, "ControlPlane") as cp, patch.object(runner, "_run_agent") as model:
                        report = runner.run_contract_step(settings, backend=FakeBackend([]), workspace=context.workspace,
                            step="deepcheck", ticket_id=context.ticket_id, policy=kwargs["policy"],
                            verification_plan=plan, sandbox=NoIsolation(), out_dir=context.out_dir)
                    errors.append(report.error)
                    cp.assert_not_called()
                    model.assert_not_called()
                    return ChainReport(delivered=False, stopped_at="deepcheck")
                _executor, result = self.execute_fixture(context, self.control(context), self.provider(), step)
                self.assertEqual(result.state, "blocked")
                self.assertEqual(errors, [expected])
                self.assertEqual(len(plans), 2)
                self.assertIs(plans[0], plans[1])

    def test_missing_and_broken_providers_keep_existing_stable_errors(self):
        with temp_workspace() as root:
            context = self.context(root)
            def broken(context, policy):
                raise ValueError("PRIVATE_SENTINEL")
            for provider, expected in ((None, "verification_plan_required"),
                                       (broken, "verification_plan_provider_failed"),
                                       (lambda context, policy: object(), "verification_plan_invalid")):
                with self.subTest(expected=expected):
                    def step(settings, **kwargs):
                        self.fail("invalid provider must not reach adapter")
                    _executor, result = self.execute_fixture(context, self.control(context), provider, step)
                    self.assertEqual(result.error_code, expected)
                    self.assertNotIn("PRIVATE", repr(result))
```

```bash
preset_python -m unittest tests.test_autonomy.TestNativePythonPreset.test_exact_builtin_same_execute_reuses_one_plan_and_shared_budget -v
```

Expected：1 assertion FAIL、0 ERROR，当前工厂创建两次且 code/deepcheck Plan 不同。factory Task 1 必须先 GREEN；不能把未实现导入错误当局部缓存 RED。

- [x] **Step 2: 只改 Native 局部缓存，不更改任意 provider 语义。**

`src/icode/autonomy.py` 在 `from .engineering_verification import VerificationPlan` 后加：

```python
from .verification_presets import PythonUnittestPlanProvider
```

在 `execute()` 的 `budget_tracker = BudgetTracker(self.budget or Budget())` 后加：

```python
        # Only this built-in preset freezes one plan within this invocation.
        # Never retain plans on the executor or change arbitrary provider calls.
        preset_plan: VerificationPlan | None = None
```

把 `verification_plan = self.verification_plan_provider(context, policy)` 单行替换为完整以下块，保留原 try/except 包围范围：

```python
                    if type(self.verification_plan_provider) is PythonUnittestPlanProvider and preset_plan is not None:
                        verification_plan = preset_plan
                    else:
                        verification_plan = self.verification_plan_provider(context, policy)
```

在现有 `if (verification_plan.run_id != policy.run_id ... step not in verification_plan.steps):` 的 mismatch 返回之后、下一 `try:` 之前插入：

```python
                if type(self.verification_plan_provider) is PythonUnittestPlanProvider:
                    preset_plan = verification_plan
```

type/identity/step 检查每步仍执行，包括复用 Plan；仅首次通过门后的对象可以保存。不用 isinstance/鸭子缓存属性/实例共享字典，不改 provider/custom adapter 签名、不在 TypeError 后重试。新 execute/resume 自然创建新局部 Plan 与已有调用内 BudgetTracker。后续 runner 继续核根 inode/环境/工具；step policy 越严格仍按 broker min 生效。

- [x] **Step 3: CLI 到真实 Native 的实际执行软件接线正负控。**

在 `tests/test_workbench.py` 的 `class TestWorkbenchCLI(unittest.TestCase):` 内、`test_verification_preset_parser_is_explicit_and_workbench_only` 前插入如下完整方法。它保持真实 Native 与真实 run_chain，只在工程步骤边界替换 `icode.chain.run_contract_step`；不造资源/Reviewer/evidence PASS。

```python
    def test_main_selected_provider_reaches_real_native_and_chain_default_stays_blocked(self):
        from icode.runner import StepReport
        from icode.sandbox_policy import NetworkMode, SandboxPolicy
        settings = require_skill()
        sandbox = SimpleNamespace(
            is_real_isolation=True, policy_contract_ready=True,
            wrap_policy=lambda argv, **kwargs: list(argv), prepare_policy=lambda policy: None,
        )
        for selected in (False, True):
            with self.subTest(selected=selected), temp_workspace() as root:
                root = root.resolve()
                directory = root / "ticket"
                directory.mkdir()
                (directory / ".ico_metadata.json").write_text(json.dumps({"ticket_id": "CLI-NATIVE"}), encoding="utf-8")
                argv = ["workbench", "--workspace", str(root), "--enable-autonomous", "--no-browser"]
                if selected:
                    argv += ["--verification-preset", "python-unittest"]
                with patch("icode.cli.load_settings", return_value=settings), \
                        patch("icode.cli._build_runner", return_value=(None, None, None, None, sandbox)), \
                        patch("icode.workbench.WorkbenchServer") as server, \
                        patch("threading.Event") as event, redirect_stdout(StringIO()):
                    server.return_value.start.return_value = "http://127.0.0.1:1234/"
                    event.return_value.wait.side_effect = KeyboardInterrupt
                    self.assertEqual(main(argv), 0)
                executor = server.call_args.kwargs["autonomy_executor"]
                self.assertIs(type(executor), NativeChainExecutor)
                context = ExecutionContext("CLI-NATIVE", directory, root, "check", "code_in_progress", ())
                control = SimpleNamespace(session=SimpleNamespace(policy=lambda step: SandboxPolicy(
                    1, "cli-native-run", "CLI-NATIVE", step, root, (root,), (root,), (), (root / ".git",),
                    NetworkMode.DENY, (), 8, 30, 65536, (root / ".git",))), safe_point=lambda step: None)
                observed = []
                def contract_step(settings, **kwargs):
                    observed.append(kwargs)
                    return StepReport(kwargs["step"], True, str(directory), finish_outcome="success")
                with patch("icode.autonomy.chain_steps", return_value=("code", "deepcheck")), \
                        patch("icode.autonomy.ControlPlane.trace", return_value=SimpleNamespace(
                            returncode=0, data={"ticket_id": "CLI-NATIVE", "status": "code_in_progress"})), \
                        patch("icode.chain.run_contract_step", contract_step):
                    result = executor.execute(context, control)
                if selected:
                    self.assertEqual(result.state, "succeeded")
                    self.assertEqual([call["step"] for call in observed], ["code", "deepcheck"])
                    self.assertIs(observed[0]["verification_plan"], observed[1]["verification_plan"])
                    self.assertEqual(observed[0]["verification_plan"].run_id, "cli-native-run")
                    self.assertEqual(observed[0]["verification_plan"].checks[0].argv[0], sys.executable)
                    self.assertIs(observed[0]["budget_tracker"], observed[1]["budget_tracker"])
                else:
                    self.assertEqual(result, ExecutionResult("blocked", "code", "verification_plan_required"))
                    self.assertEqual(observed, [])
```

- [x] **Step 4: GREEN、作者两阶段自审、任务双审与六源冻结。**

```bash
preset_python -m unittest tests.test_verification_presets tests.test_workbench.TestWorkbenchCLI tests.test_autonomy.TestNativePythonPreset tests.test_autonomy.TestNativeChainExecutor tests.test_contract_engineering.TestContractEngineering.test_native_provider_required_and_exception_are_stable_before_adapter -v
git diff --check
sha256sum src/icode/verification_presets.py src/icode/cli.py src/icode/autonomy.py tests/test_verification_presets.py tests/test_workbench.py tests/test_autonomy.py
git diff -- src/icode/autonomy.py tests/test_autonomy.py tests/test_workbench.py
```

Expected：新增 portable 方法实际0 FAIL/ERROR/skip，实际同一 Plan、新调用/双线程独立、generic/subclass 每步、custom adapter 精确参数和每步 type/identity 源码均确认。作者先自 SPEC 再自 QUALITY；fresh 独立 SPEC 后不同 QUALITY 绑定同六源，前后 SHA 不变。当前运行证明属于软件编排/runner 拒绝/真实解释器身份；不称 native/model 工程往返通过。root 接 Task 3；writer STOP、不提交、不 full。

### Task 3: CI 完整选择与配对静态守卫

**状态**
- [x] 任务完成

**Dependencies:** Task 2
**Parallelizable:** No (新增测试已冻结后再调整选择，必须保留现有 DEFAULT)

- [x] **Step 1: 新增选择合同，取得独立 RED。**

在 `tests/test_run_workspace_ci.py` 的 `class TestWorkspaceCiCoverage(unittest.TestCase):` 后、原首方法之前插入以下完整方法。

```python
    def test_python_preset_module_selected_once_completely_without_static_skips(self):
        name = "tests.test_verification_presets"
        self.assertEqual(DEFAULT_MODULES.count(name), 1)
        module = importlib.import_module(name)
        test_class = getattr(module, "TestPythonUnittestPlanProvider", None)
        self.assertTrue(isinstance(test_class, type))
        methods = unittest.defaultTestLoader.getTestCaseNames(test_class)
        self.assertTrue(methods)
        self.assertFalse(getattr(test_class, "__unittest_skip__", False))
        for method in methods:
            self.assertFalse(getattr(getattr(test_class, method), "__unittest_skip__", False))
        def cases(suite):
            for test in suite:
                if isinstance(test, unittest.TestSuite):
                    yield from cases(test)
                else:
                    yield test
        expected = {name + ".TestPythonUnittestPlanProvider." + method for method in methods}
        selected = [test for selection in DEFAULT_MODULES
                    if selection == name or selection.startswith(name + ".")
                    for test in cases(unittest.defaultTestLoader.loadTestsFromName(selection))]
        self.assertEqual({test.id() for test in selected}, expected)
        self.assertEqual(len(selected), len(expected))
        for test in selected:
            self.assertIs(type(test), test_class)
            self.assertFalse(getattr(type(test), "__unittest_skip__", False))
            self.assertFalse(getattr(getattr(test, test._testMethodName), "__unittest_skip__", False))
        for old in ("tests.test_workbench", "tests.test_autonomy"):
            self.assertEqual(DEFAULT_MODULES.count(old), 1)

    def test_preset_cli_and_native_methods_are_selected_once_without_static_skips(self):
        from tests.test_workbench import TestWorkbenchCLI
        from tests.test_autonomy import TestNativePythonPreset
        def cases(suite):
            for test in suite:
                if isinstance(test, unittest.TestSuite):
                    yield from cases(test)
                else:
                    yield test
        for name, test_class in (("tests.test_workbench", TestWorkbenchCLI),
                                 ("tests.test_autonomy", TestNativePythonPreset)):
            self.assertEqual(DEFAULT_MODULES.count(name), 1)
            methods = unittest.defaultTestLoader.getTestCaseNames(test_class)
            self.assertTrue(methods)
            expected = {name + "." + test_class.__name__ + "." + method for method in methods}
            selected = [test for selection in DEFAULT_MODULES
                        if selection == name or selection.startswith(name + ".")
                        for test in cases(unittest.defaultTestLoader.loadTestsFromName(selection))
                        if type(test) is test_class]
            self.assertEqual({test.id() for test in selected}, expected)
            self.assertEqual(len(selected), len(expected))
            self.assertFalse(getattr(test_class, "__unittest_skip__", False))
            for test in selected:
                self.assertFalse(getattr(getattr(test, test._testMethodName), "__unittest_skip__", False))
```

```bash
preset_python -m unittest tests.test_run_workspace_ci.TestWorkspaceCiCoverage.test_python_preset_module_selected_once_completely_without_static_skips -v
```

Expected：1 assertion FAIL、0 ERROR，模块选择次数实际0≠1。静态无 skip 只是选择源码合同，不能据此声称全环境运行零skip。

- [x] **Step 2: 只在 DEFAULT 加一个完整模块。**

`scripts/run_workspace_ci.py` 的 `DEFAULT_MODULES` 中，在 `"tests.test_backend_transport_privacy",` 之后、`"tests.test_autonomy",` 之前精确插入一行：

```python
    "tests.test_verification_presets",
```

不删除/重复任何旧项，不改 `main`、CROSS_PLATFORM_R3_TESTS、POSIX selection、skip 返回规则或 workflow。使用模块名而非择方法确保新增工厂全部向量加载。

- [x] **Step 3: GREEN、自审及任务双审后八源冻结。**

```bash
preset_python -m unittest tests.test_verification_presets tests.test_workbench.TestWorkbenchCLI tests.test_autonomy.TestNativePythonPreset tests.test_run_workspace_ci.TestWorkspaceCiCoverage -v
git diff --check
sha256sum src/icode/verification_presets.py src/icode/cli.py src/icode/autonomy.py tests/test_verification_presets.py tests/test_workbench.py tests/test_autonomy.py scripts/run_workspace_ci.py tests/test_run_workspace_ci.py
git diff -- scripts/run_workspace_ci.py tests/test_run_workspace_ci.py
```

Expected：新增方法实际0 FAIL/ERROR/skip，既有选择逐项保留，前六源 SHA 与 Task 2 同。作者先规格自审再质量自审，fresh SPEC→不同 QUALITY 前后绑定八源；任务 writer STOP、不提交/full。

### Task 4: Fresh 全局复核与 root 串行软件门

**状态**
- [x] 任务完成

**Dependencies:** Task 3
**Parallelizable:** No (全部 writer STOP，同八源冻结，定点→20轮→DEFAULT→原完整 preflight 串行)

- [x] **Step 1: fresh 全局 SPEC，再不同 fresh 全局 QUALITY。**

两审各全文读冻结设计/研究/本文、八源，定点读实际 CLI/Native→chain/runner→verification→resource/Reviewer/tree/evidence 链。先 SPEC C/I/M0，再不同 QUALITY C/I/M0；前后核八 SHA。可使用 Task 3 Step 3 同定点命令，不并行 full，不以任务审查替代全局。任何源码修改回对应任务 RED/GREEN、重新冻结/双审。独立研究仅复核已固定 Aider/Codex 链接，不复制源码、不访问模型配置。

- [x] **Step 2: root 独立关联回归，分层记录。**

```bash
sha256sum src/icode/verification_presets.py src/icode/cli.py src/icode/autonomy.py tests/test_verification_presets.py tests/test_workbench.py tests/test_autonomy.py scripts/run_workspace_ci.py tests/test_run_workspace_ci.py
preset_python -m unittest tests.test_verification_presets tests.test_workbench.TestWorkbenchCLI tests.test_autonomy.TestNativePythonPreset tests.test_autonomy.TestNativeChainExecutor tests.test_run_workspace_ci.TestWorkspaceCiCoverage tests.test_engineering_verification.TestPythonIsolatedTemplate tests.test_engineering_verification.TestEngineeringResourceDispatch tests.test_contract_engineering.TestContractEngineering tests.test_shared_runtime_budget tests.test_engineering_evidence -v
```

Expected：实际 exit0；新增 portable 零skip，已有平台/资源环境skip只按实际报告，不改 skip 或降门。记录三层：CLI/Native 编排 doubles；既有 isolated 模板的实际子进程正负控；实际 Linux 全工程往返仍待独立门，不用前两层抵第三层。根/环境/身份漂移拒绝、资源无fallback、独立 Reviewer、受测 tree、CP/evidence 旧合同必须保留。

- [x] **Step 3: 每轮新 TestLoader，串行20轮，不预填数字。**

```bash
preset_python -c 'import sys, unittest
names = ("tests.test_verification_presets", "tests.test_workbench.TestWorkbenchCLI", "tests.test_autonomy.TestNativePythonPreset", "tests.test_run_workspace_ci.TestWorkspaceCiCoverage.test_python_preset_module_selected_once_completely_without_static_skips", "tests.test_run_workspace_ci.TestWorkspaceCiCoverage.test_preset_cli_and_native_methods_are_selected_once_without_static_skips")
total = 0
for round_number in range(1, 21):
    print("workbench preset round", round_number, flush=True)
    suite = unittest.TestLoader().loadTestsFromNames(names)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    print("actual", result.testsRun, "failures", len(result.failures), "errors", len(result.errors), "skips", len(result.skipped), flush=True)
    if result.testsRun <= 0 or not result.wasSuccessful() or result.failures or result.errors or result.skipped:
        sys.exit(1)
    total += result.testsRun
print("actual aggregate", total, flush=True)'
```

Expected：20轮各非空、0 FAIL/ERROR/skip；累计次数由实际输出计算，不称累计为新增方法数。源有变化则同 freeze 的20轮信用失效，重新任务门和全局门。

- [x] **Step 4: DEFAULT 后只跑一次原完整 preflight。**

```bash
preset_python scripts/run_workspace_ci.py
preset_python -c 'import re, sys, time
from scripts import preflight
original = preflight.subprocess.run
seen = []
def observe(*args, **kwargs):
    selected = bool(args) and args[0] == [sys.executable, "-m", "unittest"]
    if selected:
        assert len(args) == 1
        assert kwargs == dict(cwd=str(preflight.REPO), capture_output=True, text=True, encoding="utf-8", errors="replace", shell=False)
        assert not seen
        started = time.monotonic()
        result = original(*args, **kwargs)
        seen.append(result)
        print("original full child wall", time.monotonic() - started, "returncode", result.returncode, flush=True)
        for stream in (result.stdout or "", result.stderr or ""):
            for line in stream.splitlines():
                if re.search(r"^Ran [0-9]+ tests? in |^OK(?:$| \()|^FAILED|bootstrap.*binding|verifier.*binding", line, re.I):
                    print(line, flush=True)
        return result
    return original(*args, **kwargs)
preflight.subprocess.run = observe
started = time.monotonic()
try:
    code = preflight.main([])
finally:
    preflight.subprocess.run = original
assert len(seen) == 1
print("original preflight wall", time.monotonic() - started, flush=True)
sys.exit(code)'
```

Expected：DEFAULT actual exit0、原 secrets/submodule/tests 三道 actual pass、原完整 child 恰好一次，argv/kwargs 与结果对象原样，完整 total/F/E/skip 如实记录。这等价原完整 `preset_python -m scripts.preflight`；不得再启动第二次 full、改 child argv/筛模块/改环境择绿。wrapper 仅打印已返回 stdout/stderr 的总结，不增加验收信用。长运行用产品返回 session 的机制查询和≤60秒进度更新，不与源修改或另一全量并行。

- [x] **Step 5: compile-j1、治理、官网、竞品排期与七维报告。**

```bash
preset_pyc_dir=$(mktemp -d /tmp/icode-workbench-preset-pyc-XXXXXX)
PYTHONPYCACHEPREFIX="$preset_pyc_dir" preset_python -m compileall -q -j 1 src scripts tests
preset_python scripts/check_governance.py
preset_python scripts/check_site.py
preset_python scripts/check_agent_landscape.py --today 2026-10-09
git diff --check
sha256sum src/icode/verification_presets.py src/icode/cli.py src/icode/autonomy.py tests/test_verification_presets.py tests/test_workbench.py tests/test_autonomy.py scripts/run_workspace_ci.py tests/test_run_workspace_ci.py
```

Expected：全部 actual exit0，缓存仅任务 mktemp 目录，八源仍同 freeze；不递归删除缓存。竞品工具只证明20项名单/日期结构，不称20仓源码已重查。root 按真实结果输出下面完整七维报告，并把范围限定本片软件：

```text
【架构级自检报告】
语法/编译：记录实际 compile-j1 和测试退出码
依赖/调用链：记录 TYPE_CHECKING 无循环和 CLI→Native→旧 runner 链
逻辑/边界：记录固定 argv、root/run/ticket/steps、局部缓存与漂移矩阵
异常处理：记录普通固定提示、构造/直cmd fatal 原对象和旧 Native 稳定码
关联模块：记录资源/Reviewer/tree/CP/evidence 与 DEFAULT 保留
兼容安全：记录无预设/generic/subclass/custom adapter、平台准入无扩张
可运行性：记录本机实际 RED/GREEN/20/DEFAULT/full；原生/模型未验部分另列
```

任何项不通过禁止交付；不得把未验 native/model 写为“100%”。通过项可以用✅标识，失败/未验按实际标识，报告不能遗漏。

### Task 5: 文档两轮 clean、精确 main 发布和新 SHA 观察

**状态**
- [ ] 任务完成

**Dependencies:** Task 4
**Parallelizable:** No (源码完整门同 freeze 后才文档/发布；新观察绑定实际发布 SHA)

- [x] **Step 1: root 更新实际履历和相关持续对照，再两轮文档 clean。**

root 先完整读 `/home/orbbec/.agents/skills/doc-contract-consistency-audit/SKILL.md`，按实际证据用 apply_patch 更新本文 checkbox/履历和 `docs/agent-landscape-live.md` 相关条目。冻结设计/研究内容保持原 SHA，不把起草“未实现”改成历史窗口已验；本文追加新实际时点。写明 RED 断言与 fixture ERROR 区别、每次 total/F/E/skip、作者与独立审查分层、八 SHA、本机软件和剩余 native/model 门。记录采用/暂缓/不适配与许可证范围，不扩展当前源码切片。

```bash
preset_python /home/orbbec/.agents/skills/doc-contract-consistency-audit/scripts/check_consistency.py docs/nbl/plans/2026-10-09-r3-workbench-python-preset.md docs/nbl/specs/2026-10-09-r3-workbench-python-preset-design.md docs/nbl/specs/2026-10-09-workbench-preset-upstream-refresh.md docs/agent-landscape-live.md
preset_python /home/orbbec/.agents/skills/doc-contract-consistency-audit/scripts/check_consistency.py docs/nbl/plans/2026-10-09-r3-workbench-python-preset.md docs/nbl/specs/2026-10-09-r3-workbench-python-preset-design.md docs/nbl/specs/2026-10-09-workbench-preset-upstream-refresh.md docs/agent-landscape-live.md
```

Expected：连续两轮各0疑似项，并人工核启动解释器/第一工程计划两冻结时点、静态守卫/实际skip区别、每命令限额/非run总预算、软件/native/模型分层、旧观察来源不冒称当前实读。第一轮问题解决后才第二轮。文档修改后再次两轮；无源码变化不重复 full。

- [x] **Step 2: 最终同八源核 SHA，非测试守卫。**

```bash
sha256sum src/icode/verification_presets.py src/icode/cli.py src/icode/autonomy.py tests/test_verification_presets.py tests/test_workbench.py tests/test_autonomy.py scripts/run_workspace_ci.py tests/test_run_workspace_ci.py
sha256sum docs/nbl/specs/2026-10-09-r3-workbench-python-preset-design.md docs/nbl/specs/2026-10-09-workbench-preset-upstream-refresh.md docs/nbl/plans/2026-10-09-r3-workbench-python-preset.md
preset_python scripts/preflight.py --only secrets
preset_python scripts/preflight.py --only submodule
preset_python scripts/check_governance.py
preset_python scripts/check_site.py
preset_python scripts/check_agent_landscape.py --today 2026-10-09
git diff --check
git -C vendor/icode-skill status --porcelain
git -C vendor/icode-skill rev-parse HEAD
git ls-files -s vendor/icode-skill
```

Expected：actual0、八源与全局双审/软件同 freeze，两输入 SHA 不变，vendor clean/head=gitlink。源变化回任务门；文档变化回两轮，final guard 后不悄改源。

- [ ] **Step 3: root 精确暂存、提交/推送 main；不逐任务提交。**

```bash
git branch --show-current
git rev-parse HEAD
git status --short
git diff --stat
git diff -- src/icode/cli.py src/icode/autonomy.py tests/test_workbench.py tests/test_autonomy.py scripts/run_workspace_ci.py tests/test_run_workspace_ci.py
git add -- src/icode/verification_presets.py src/icode/cli.py src/icode/autonomy.py tests/test_verification_presets.py tests/test_workbench.py tests/test_autonomy.py scripts/run_workspace_ci.py tests/test_run_workspace_ci.py docs/agent-landscape-live.md
git add -f -- docs/nbl/plans/2026-10-09-r3-workbench-python-preset.md docs/nbl/specs/2026-10-09-r3-workbench-python-preset-design.md docs/nbl/specs/2026-10-09-workbench-preset-upstream-refresh.md
git diff --cached --name-only
git diff --cached --check
git diff --cached --stat
git diff --cached -- src/icode/cli.py src/icode/autonomy.py tests/test_workbench.py tests/test_autonomy.py scripts/run_workspace_ci.py tests/test_run_workspace_ci.py
git commit -m "feat: add explicit workbench Python unittest preset"
git push origin main
preset_commit=$(git rev-parse HEAD)
git show --no-patch --format='%H %P %T' "$preset_commit"
git ls-remote origin refs/heads/main
git status --short
```

Expected：仅已审八源和必要四文档候选，index bytes 与已验工作树逐一相同；parent/root main 绑定，远端refs/main同实际新 SHA，未知dirty不混入。已在旧提交发布的文档不重复计入变更路径；不使用 add . / -A、不创建分支、不改vendor。commit/push 只由 root 按既有 main 发布授权执行，完整门之前禁止执行。stage 若包含非预期路径，先定位，不提交。

- [ ] **Step 4: fresh 独立只读观察新 SHA，root 独立回读关键日志。**

本机没有 `gh` 可执行文件（独立 SPEC 和作者均 `command -v gh` exit1/no output），使用当前已可用 GitHub connector；不安装 CLI、不新增依赖。下列完整 JavaScript 在 `functions.exec` 运行，接口和 `structuredContent.content` 格式已由 root 实际验证。首次从本 repo 的真实 HEAD 发现 run，所有整数 ID 只来自该 SHA 的官方列表；后续调用用同一 store 保留已读取日志和 STOP 状态。作者此轮只静态核对代码，不调用 GitHub 网络。

```javascript
const repo = "ayukyo/icode";
const api = "https://api.github.com/repos/" + repo;
const workflows = new Set(["CI", "Public website", "Windows helper provenance"]);
function requireValue(condition, message) {
  if (!condition) throw new Error(message);
}
function content(result) {
  requireValue(!result.isError && typeof result.structuredContent?.content === "string",
               "GitHub connector response unavailable");
  return result.structuredContent.content;
}
async function fetchJson(url) {
  const result = await tools.mcp__codex_apps__github_fetch({url});
  const parsed = JSON.parse(content(result));
  requireValue(parsed !== null && typeof parsed === "object", "GitHub JSON object required");
  return parsed;
}
function idValid(id) {
  return Number.isSafeInteger(id) && id > 0;
}
async function collection(path, field) {
  const values = [];
  for (let page = 1; ; page += 1) {
    const separator = path.includes("?") ? "&" : "?";
    const data = await fetchJson(api + path + separator + "per_page=100&page=" + page);
    requireValue(Array.isArray(data[field]), "GitHub collection unavailable");
    values.push(...data[field]);
    if (data[field].length < 100) return values;
  }
}
function summary(log) {
  const lines = [];
  const stable = /\b(?:UNVERIFIED|no_matching_event|archive_member_missing|wait_timeout|wait_expired|canaryfalse|criticalfalse|readyfalse)\b/g;
  for (const raw of log.split(/\r?\n/)) {
    const line = raw.replace(/^\d{4}-\d{2}-\d{2}T\S+\s+/, "");
    if (/^(?:Ran [0-9]+ tests? in [0-9.]+s|OK(?: \([^\r\n]{1,200}\))?|FAILED(?: \([^\r\n]{1,200}\))?)$/.test(line)) {
      lines.push(line);
    }
    for (const marker of line.match(stable) || []) lines.push(marker);
    for (const marker of line.match(/"(?:parse_complete|runtime_load_verified|source_launch_verified)"\s*:\s*(?:true|false)/g) || []) {
      lines.push(marker);
    }
    if (/bootstrap.*binding.*PASS/i.test(line)) lines.push("bootstrap_binding_PASS");
    if (/Reported success/.test(line)) lines.push("Reported success");
    if (line.includes("https://ayukyo.github.io/icode/")) lines.push("public_website_url_present");
  }
  return [...new Set(lines)].slice(0, 80);
}
function decisiveJob(run, job) {
  if (run.name === "Public website") return /^(?:validate|deploy)$/.test(job.name);
  if (run.name === "Windows helper provenance") return /^(?:validate|Attest and install bootstrap\b)/.test(job.name);
  return /^(?:Python\b|.*workspace\b|.*Reviewer\b|.*native\b)/i.test(job.name);
}
async function observePresetOnce() {
  const head = await tools.exec_command({
    cmd: "git rev-parse HEAD", workdir: "/home/orbbec/git/icode", max_output_tokens: 100,
  });
  requireValue(head.exit_code === 0 && typeof head.output === "string", "Git HEAD unavailable");
  const commit = head.output.trim();
  requireValue(/^[0-9a-f]{40}$/.test(commit), "Full source SHA required");
  requireValue(commit !== "6ded1d3c16c265fda16fa6506cb57c29067b5fbd", "New published source required");
  const key = "workbench-python-preset-observation:" + commit;
  const state = load(key) || {commit, jobs: {}, stoppedRuns: []};
  requireValue(state.commit === commit, "Observation source mismatch");
  const discovered = await fetchJson(api + "/actions/runs?head_sha=" + commit + "&per_page=30");
  requireValue(Array.isArray(discovered.workflow_runs), "Workflow discovery unavailable");
  for (const run of discovered.workflow_runs) {
    requireValue(idValid(run.id) && run.head_sha === commit, "Discovered run source mismatch");
  }
  store(key + ":discovery", discovered);
  const runs = await collection("/actions/runs?head_sha=" + commit, "workflow_runs");
  const chosen = [];
  for (const listed of runs) {
    requireValue(idValid(listed.id) && listed.head_sha === commit, "Listed run source mismatch");
    if (!workflows.has(listed.name)) continue;
    chosen.push(listed);
    if (state.stoppedRuns.includes(listed.id)) continue;
    const run = await fetchJson(api + "/actions/runs/" + listed.id);
    requireValue(run.id === listed.id && run.head_sha === commit && run.name === listed.name,
                 "Workflow run identity mismatch");
    store(key + ":run:" + run.id, run);
    const jobs = await collection("/actions/runs/" + run.id + "/jobs", "jobs");
    for (const job of jobs) {
      requireValue(idValid(job.id) && job.run_id === run.id && job.head_sha === commit,
                   "Workflow job source mismatch");
    }
    store(key + ":jobs:" + run.id, jobs);
    text({commit, run_id: run.id, workflow: run.name, status: run.status, conclusion: run.conclusion,
          jobs: jobs.map(job => ({id: job.id, name: job.name, status: job.status, conclusion: job.conclusion}))});
    for (const job of jobs) {
      if (job.status !== "completed" || !decisiveJob(run, job) || state.jobs[job.id]) continue;
      if (job.conclusion === "skipped") {
        state.jobs[job.id] = {run_id: run.id, head_sha: commit, skipped: true};
        store(key, state);
        continue;
      }
      const result = await tools.mcp__codex_apps__github_fetch_workflow_job_logs({repo_full_name: repo, job_id: job.id});
      const log = content(result);
      store(key + ":log:" + job.id, log);
      state.jobs[job.id] = {run_id: run.id, head_sha: commit, decoded_log_saved: true};
      store(key, state);
      text({commit, run_id: run.id, job_id: job.id, name: job.name, conclusion: job.conclusion,
            summary: summary(log), coverage: "bounded summary and stable markers only"});
    }
    if (run.status === "completed" && jobs.every(job => job.status === "completed")) {
      state.stoppedRuns.push(run.id);
      store(key, state);
      text({commit, run_id: run.id, state: "STOP", conclusion: run.conclusion});
    }
  }
  const found = [...new Set(chosen.map(run => run.name))];
  text({commit, observed_workflows: found, missing_workflows: [...workflows].filter(name => !found.includes(name)),
        active_run_ids: chosen.filter(run => !state.stoppedRuns.includes(run.id)).map(run => run.id)});
}
await observePresetOnce();
```

无缺失 workflow 且所有当前 scope run STOP 后结束该 SHA 观察，不继续列表轮询。仍在运行时使用产品等待机制，下一次仅对未 STOP run 复核 run/jobs，已完成 job 日志不重复取；不因等待而调用 rerun/dispatch。日志完整 decoded string 只保存到 store；打印有限摘要/固定标记，不能称全文人工实读或 binary/PE 验证。如需某关键证据额外读取，只从已保存的对应新 SHA 日志定点提取并说明实际范围；不打印整段异常路径、任意正文或未知 JSON 字段。独立观察者仅 read-only，不下载 artifact、不读取 token/KEY/私有配置、不请求模型 HTTP，不写旧 plan 的历史 checkbox。

本段 I1 修订后作者只读静态自审：16个 Python 代码块 AST 解析、15个 Bash 代码块 `bash -n` 均通过；1个 JavaScript 代码块仅核接口/返回格式/身份与 STOP 逻辑，未执行。没有导入仓库、运行测试或调用 GitHub 网络，源码及其余任务代码不变。该修订仍须同 SPEC 复审→不同 QUALITY，不借静态解析预报线上观察通过。

Expected：Linux/macOS/Windows workspace 新模块完整加载及实际 summary、两 Python full 结果、失败/skip 格如实分列；静态 selection 不代替运行结果。Pages 必须绑定实际 deploy/head；签名/provenance 成功不抵 workspace/native 失败。长期 run 用产品等待机制及≤60秒进度更新，到终态 STOP。未获结果保持未勾选。真实模型1→6、≥90%和 R2/R3 总门，以及实际 Linux 资源/Reviewer/tree/CP 往返，均不因本片软件通过自动关闭。

## 前片历史窗口：来源必须保留

以下为 root 给定的前片 `6ded1d3c16c265fda16fa6506cb57c29067b5fbd` 观察事实，计划作者没有重取远端日志，不能称作者独立实读，也不能用于新 SHA 验收。

root 本机前片完整 suite 2414 total/2355 PASS/59 skip/0 FAIL/ERROR，490.568秒；DEFAULT558 PASS，20×43=860。发布9路径，tree `7c5904cdca90d565955d18077ac19a81c52c0b27`，parent `cad0eb17b206ce276b325f3209ff601480be06d8`。

root 独立官方 GET 核 [CI37869620556](https://github.com/ayukyo/icode/actions/runs/37869620556) 终态 failure、44 jobs=37 success/4 failure/3 retired skip，全部 head6ded。root 实读 job113624448263：2414 total/2343 PASS/71 skip/0 FAIL/ERROR，609.912秒，bootstrap binding PASS；Linux workspace113624448493 DEFAULT558 PASS/0skip，226.094秒，network75 PASS。root 实读 x64 workspace113624448502：552 total/530 PASS/1 FAIL/1 ERROR/20skip，224.432秒，incremental CP baseline Win10093 ERROR 与 nativelegacycode CP Win10038 FAIL。Python3.12 同2414/71skip、mac DEFAULT558 PASS、ARM workspace 同两错误来自独立 observer，root 当时未重取这三日志。

root 实读 x64 Reviewer113624448214 决定性 JSON：exit78/tokenNone，IPv4/v6 10035 wait timeout、canaryfalse、WFP ready但 no_matching_event，capture archive_member_missing；mac native113624448401 实际6/10、criticalfalse、readyfalse、resource UNVERIFIED。不能被软件或签名 PASS 抵消。

[Pages37869620562](https://github.com/ayukyo/icode/actions/runs/37869620562) 终态 success2/2；root 完整 deploy log success `01:25:24.8207053Z`、build version6ded，URL `https://ayukyo.github.io/icode/`；artifact11589633268 ZIP SHA256 `a74235ef907dcd526559e96322d7b642046b63b7788604c0ba732725cd2692bf`，313408 bytes。

root 后续独立收尾 [provenance37869620540](https://github.com/ayukyo/icode/actions/runs/37869620540) 终态 success5/5，observer STOP。root 读取 run/jobs/四 artifacts 元数据和四份 decoded 决定性片段；每格19个安装验证脚本 PASS，另一个独立 buildcontext PASS，不能把 grep20 记为20个安装脚本。capture 的 parse_complete/runtime_load_verified/source_launch_verified 均 false，未下载 binary、独立 PE 解析、加载或来源启动。root 程序核 capture helper=attestation subject、上传日志 artifact ID/size/ZIP=API、source6ded/run一致且未过期；仅该来源证据成立，不抵 native/Reviewer/workspace 失败。

| 前片矩阵 | job | attestation | artifact | bytes | helper SHA256 | ZIP SHA256 |
| --- | --- | --- | --- | --- | --- | --- |
| ARM64/3.12 | 113627308893 | 54160359 | 11590790796 | 7570533 | `a154cabab0f57daa6b16d36b87c93156f1a0823b9de4f9d050821f14ce123225` | `02c30af9e359a1987f3f23512446b3d7e482726442928dd1fc16a4e6db5b30af` |
| ARM64/3.11 | 113627308988 | 54160480 | 11590771005 | 7570472 | `94573020948bdedff9bf8c110e2cf70e2c4f2627a1d019aa0a2cf8193b975606` | `a806f3bf1ce1f7f8f02700166384e49b2ec773f6f0a38fa566b839d182583149` |
| x64/3.11 | 113627308992 | 54160105 | 11590830539 | 8360317 | `29746adf70008c4f768516b35760181bdab96cb051a590bc170bf926aadf759a` | `77f13ac3c8b034bbc335ceb18403e0b2356745d5083250ae79d3357ec6ac514d` |
| x64/3.12 | 113627309009 | 54159956 | 11589724854 | 8360283 | `c6ac7dbf1be762b3fc218b557d215812201c18a10695d8d394ee50e162385ac3` | `7db0167e708d01f0bd7511760470e2e6f0f2d79b2a69c13e440f50c1c2085198` |

前片三个远端窗口均 terminal/STOP，不能继续 poll 旧窗口或把旧成功填入本片新 SHA 验收。

## 计划自审与未完成门

- [x] 工厂/CLI 的完整可执行代码与固定 argv、普通/fatal、旧 Namespace 正负控已按批准规格实施和运行。
- [x] Native 精确 type 的局部 Plan、每步 type/identity、跨新execute/线程和任意provider/subclass/custom adapter已运行。
- [x] 新模块完整 DEFAULT 与无静态skip配对守卫已运行，全部旧项保留。
- [x] fresh全局SPEC→不同QUALITY、root关联、20轮、DEFAULT、唯一原完整preflight、compile-j1、七维、两clean实际通过。
- [ ] 精确main提交推送与新SHA只读观察完成；未验/失败native/model/R2/R3仍明确列出。

起草时全部 checkbox 未勾选。设计两审是已有静态输入，本文还需 fresh 计划 SPEC→不同 QUALITY，不能自动继承设计批准。上游机制仅引用研究中固定 Aider `5dc9490bb35f9729ef2c95d00a19ccd30c26339c`、Codex `0ada5d8806cdad498230d5b1b2924091e04c8feb` 与完整读 Apache-2.0 的历史观察，不扩大调研或复制实现。

---
**Execution Mode:** serial

## 实施履历：2026-10-09 03:10 UTC 软件门

这是起草之后的新实际窗口；前文设计/研究的未实现、未审状态及前片观察保留其历史时间。基线 main `6ded1d3c16c265fda16fa6506cb57c29067b5fbd`、vendor `1693651c1bd7daad3272eb054f0f81d6f254d08d`，本批尚未提交/推送或获得新 SHA 线上结果。Task 1–4 已实际完成；Task 5 未得结果的格仍留空。全部运行串行，源码 writer 已 STOP。

| 任务 | 作者 RED（total/F/E/skip，exit1） | 作者 GREEN（全P/零F/E/skip，exit0） | fresh SPEC | 不同 fresh QUALITY |
| --- | --- | --- | --- | --- |
| Task 1 工厂/CLI | 两次各1/1/0/0，分别0.000s和0.003s；接口及parser断言，不是fixture ERROR | 20，0.235s | 20，0.255s，C0/I0/M0 | 20，0.227s，C0/I0/M0 |
| Task 2 局部 Plan | 1/1/0/0，0.071s，实际断言2!=1 | 41，1.164s | 41，1.066s，C0/I0/M0 | 41，1.078s，C0/I0/M0 |
| Task 3 DEFAULT | 1/1/0/0，0.000s，实际断言0!=1 | 52，0.908s | 52，0.910s，C0/I0/M0 | 52，0.947s，C0/I0/M0 |

作者分别完成自SPEC/自QUALITY；任务审查和全局审查是另一个独立层。Task 1 的 test_workbench SHA 为 `4e4779dea6301a6557fa211c2f0ab112403f8f6c90061d2613c66a59dca016b3`，Task 2 加入真实Native接线后变为下表；不挪用旧SHA审查信用。Task 3 QUALITY 报告的 CLI SHA 曾少两个字符，同一审查者仅执行SHA回读修正为下表完整64位，root独立核实际八摘要；没有源码修改或测试重跑。

全局 fresh SPEC和不同fresh QUALITY均完整读八源/三文档及完整diff、定点核下游；各52P/0F/E/skip/exit0，分别0.991s、0.941s，均C0/I0/M0并STOP。root完整读取新工厂/测试及各任务修改diff、定点核下游，不把此范围冒称新全文阅读全部八源。

| 冻结路径 | SHA256 |
| --- | --- |
| `src/icode/verification_presets.py` | `2ceb3f574fe2f93622c4f10977cbdd57787b97c9b9b35a9265b4185b35ca757f` |
| `src/icode/cli.py` | `34f35d1e73597f254bcbe07691ba889b8ab2de94f0694b8e6d09f4e8e4dd3199` |
| `src/icode/autonomy.py` | `0b2613691e178a6452f3dc3c66481d9d104553d15922b3f069fd00d95fe8dbf8` |
| `tests/test_verification_presets.py` | `33df5f048a20f3b780b959b0f711e005dbaba2f8dd8de6a18fb3148cf4ab303e` |
| `tests/test_workbench.py` | `1f48124b507bfb227023a8be4369c16014cad636246de2d2d79537b60370761f` |
| `tests/test_autonomy.py` | `b6959f3b2acf2e337276fe8ca9f79d3c677cee760d81d3767d90a10e962a0148` |
| `scripts/run_workspace_ci.py` | `353b108aebac6cf0a7c99d6ba24a24a05681cb439a30e9c6b63c44db4a0d3e57` |
| `tests/test_run_workspace_ci.py` | `455b42fddf48cffea9c3af4d597126339385c0712eb470aba440cb6dcf2662a0` |

root独立软件门在同八摘要完成：
- 关联回归实际175P/0F/E/skip，71.744s，exit0；CLI/Native编排doubles、既有孤立模板实际子进程与Linux完整产品往返信用分开，后者仍待实际验收。
- 20轮每轮重新创建TestLoader，各31P/0F/E/skip，累计620次，exit0；累计不是新增方法数。stdout/stderr混排使初次行首摘要解析只识别8条，root从同一完整输出核20条actual记录和1–20轮header，去掉观察正则行首锚后确认；没有改变测试命令、源码或重跑。
- DEFAULT实际581P/0F/E/skip，168.680s，exit0，installed bootstrap verifier byte binding PASS。
- 原完整preflight三道通过；原child argv/kwargs及返回对象不修改，完整child调用恰好一次。2439total/2380P/59既有环境skip/0F/E，491.125s，child wall491.4709412099328s、preflight wall492.6374912902247s，exit0；bootstrap byte binding PASS。不能拿静态无skip守卫冒称完整suite零skip。
- compileall显式-j1 exit0，wall0.577225329s，cache仅仓外 `/tmp/icode-workbench-preset-pyc-Es1bJJ`；治理、网站、对照排期和diff各exit0。对照工具只验20项结构/日期，不称20上游源码重新核查。
- 七维报告实际通过范围仅本批软件：语法/编译、依赖/调用链、逻辑/边界、异常、关联、兼容、安全及本机可运行性；原生/模型未验部分不写100%。

### 阶段末上游只读刷新

独立研究窗口02:30:32–02:33:35 UTC（10:30:32–10:33:35 Asia/Shanghai）。Aider仍固定 `5dc9490bb35f9729ef2c95d00a19ccd30c26339c`（2026-05-22T14:02:20Z）；Codex main已到 `03b761dca9b04f47e166494232d70b3fe7c6738a`（committer2026-10-09T02:04:35Z）。两仓未归档、Apache-2.0。root在02:31:14 UTC独立核官方分支及[固定比较](https://github.com/openai/codex/compare/0ada5d8806cdad498230d5b1b2924091e04c8feb...03b761dca9b04f47e166494232d70b3fe7c6738a)13个文件名：ahead1，为realtime voice/protocol/schema生成相关改动，不是13文件全文人工代码审查。

独立研究逐字比较原始内容并核Git blob，四相关文件在新旧Codex SHA相同：loader `46dbb8b055768542c4d0360059823411cdc66023`、exec_policy `79d564e338a99a753729a2df4ddaaf1e0a4df77b`、config `f10ea126f962a85594fb15d648067b3005c4d7d2`、LICENSE `4606e72e042564097e8780d66c1d4dcb611869bd`。新时点实际定点阅读[loader85–102](https://github.com/openai/codex/blob/03b761dca9b04f47e166494232d70b3fe7c6738a/codex-rs/config/src/loader/mod.rs#L85-L102)、1113–1180/1753–1771、[exec_policy394–460](https://github.com/openai/codex/blob/03b761dca9b04f47e166494232d70b3fe7c6738a/codex-rs/core/src/exec_policy.rs#L394-L460)、[config4151–4202](https://github.com/openai/codex/blob/03b761dca9b04f47e166494232d70b3fe7c6738a/codex-rs/core/src/config/mod.rs#L4151-L4202)；Aider args548–563/main1056–1063/commands993–1044。初始许可证全文阅读是先前窗口，新时点通过相同blob/正文比较确认未变，不冒称重复全文人工阅读。root本次只独立读分支/比较元数据，不冒称新增全文源码实读。

**采纳：**可信启动者显式固定预设、项目配置与授权分离、能力不足拒绝；收益是补真实工作台provider接线并防步骤间重新授权，成本为仅宿主Python可发现项目和本批身份/兼容矩阵。**暂缓：**任意字符串/callable测试命令、provider注册、环境注入/依赖安装/自动猜项目。**不适配：**用上游批准规则绕sandbox或增权限、软件测试等同原生/模型准入。只借机制，无源码复制、依赖或权限新增；完整20名单未在本片刷新。

### 本时点剩余门

Task 5文档两轮clean、最终守卫、精确main发布及新SHA观察须各自实际返回；冻结设计/研究仍原摘要，起草1278行除checkbox外规范字节不变。后续只追加实际时点，不为metadata重复本次完整suite。

前片6ded三工作流终态/STOP仅属前片，详细run/job/来源表见上面历史窗口；新SHA结果不可从旧窗口填入。Windows Git10093/10038、Reviewer10035/缺token/WFP无匹配事件仍失败，签名capture三false/完整PE/实际加载/首次UAC仍未通过；macOS单任务quota和Linux完整产品资源/Reviewer/tree/CP/evidence往返仍未验。真实模型账户/完整endpoint待确认，模型1→6及≥90%实际对照、R2/R3整体均未通过；此前三个UTF8/current-interpreter校验器授权不扩成SKILL Git管道修改许可。

03:12:34 UTC收尾文档/非测试门：四文档连续两轮实际各0疑似项；人工核计数/枚举与标题，尤其启动解释器和首次工程Plan冻结时点、静态skip守卫与运行skip、每命令限额非run总预算、作者/独立审查/root读取范围、旧/新窗口和软件/native/模型分层。root读取起草前1278行并仅逆转已勾checkbox后，与保存的原规范文本逐字符相同；两冻结设计/研究仍原SHA。secrets/submodule/治理/site/landscape/diff各exit0，vendor工作树空、HEAD和gitlink均1693651。本行仅追加实际时点；最终metadata后还须再做两轮clean与非测试守卫，源码没有变化，不重复full。Task5发布和新SHA观察仍未有结果，不能提前勾选。
