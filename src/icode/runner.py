"""真模型运行器：契约驱动的步骤执行 + 隔离靶场上的能力验证。

两件事，严格区分，**不互相冒充**：

1. `run_contract_step` —— 按 gates.json 契约跑一个步骤（默认 plan）：
   start → check → 模型工作（工具循环）→ artifact 登记 → check → finish
   产出真实的步骤产物，事件链可追溯。

2. `run_task` —— 在**隔离的靶场副本**上做能力验证：
   让模型真的改代码，然后由**我们自己独立跑测试**取退出码作为证据
   （模型的自我声明不算证据）。

关于"为什么不直接跑完整 1→6"：
`code` 步骤的必需输入包含 `03_plan_final.md`（由 merge 步骤产出，
而 merge 依赖 review 的多轮对抗审查）。因此 P2 不去假装跑完整链路，
而是先把"单步骤在真模型下按契约完成 + 真实能力验证"做扎实。
详见 docs/roadmap.md 的自我修正记录。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .approvals import Approver, DenyAllApprover
from .backends import Backend, Usage
from .budget import Budget, BudgetTracker
from .config import Settings
from .contracts import ContractSet
from .control import ControlPlane, make_request
from .disclosure import load_guide
from .guard import Guard, Scope
from .loop import AgentLoop, LoopConfig, LoopResult
from .operations import OperationRecorder
from .reasoning import ReasoningGate, TraceRow, append_trace
from .tools import ToolContext, default_registry

# 靶场默认位置（相对仓库根）
FIXTURES_ROOT_REL = Path("tests") / "fixtures"

DEFAULT_TASK = (
    "为 calc.py 新增两个函数并补充单元测试：\n"
    "1) calc_gcd(a, b) —— 整数最大公约数；a=b=0 时返回 0\n"
    "2) calc_lcm(a, b) —— 整数最小公倍数；任一参数为 0 时返回 0；结果溢出 int32 时抛 CalcError(CALC_ERR_OVERFLOW)\n"
    "要求：在 test_calc.py 中补充覆盖正常值与边界（0、负数、溢出）的用例；"
    "最后运行 `python -m unittest` 确认全部通过。"
)


@dataclass
class StepReport:
    step: str
    ok: bool
    out_dir: str
    checkpoints: list[tuple[str, bool, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    loop: LoopResult | None = None
    trace: dict = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)
    reasoning_rows: list[TraceRow] = field(default_factory=list)
    advance_status: str = ""
    advance_gates: list[str] = field(default_factory=list)
    finish_outcome: str = ""
    error: str = ""

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.checkpoints.append((name, ok, detail))

    def warn(self, text: str) -> None:
        self.warnings.append(text)

    def render(self) -> str:
        lines = [f"契约步骤：{self.step}", f"工单目录：{self.out_dir}", "", "【契约层】"]
        lines += [f"  {'OK  ' if ok else 'FAIL'} {name}" + (f" :: {d}" if d else "")
                  for name, ok, d in self.checkpoints]
        if self.artifacts:
            lines += ["", "【产物登记】"] + [f"  {a}" for a in self.artifacts]
        if self.loop:
            lines += ["", "【模型工作】", "  " + self.loop.render().replace("\n", "\n  ")]
        if self.trace:
            lines += ["", "【事件链】",
                      f"  event_count={self.trace.get('event_count')} status={self.trace.get('status')}",
                      f"  未闭合：steps={len(self.trace.get('open_steps') or {})} "
                      f"operations={len(self.trace.get('open_operations') or {})}"]
        if self.reasoning_rows:
            lines += ["", "【推理 trace（如实记录）】"]
            for row in self.reasoning_rows:
                lines.append(
                    f"  step={row.step} tier={row.tier} mechanism={row.mechanism} "
                    f"attempted={row.attempted} result={row.result}"
                )
                if row.degraded_reason:
                    lines.append(f"    degraded_reason={row.degraded_reason}")
        if self.advance_status:
            gates = f"（门禁：{', '.join(self.advance_gates)}）" if self.advance_gates else ""
            lines += ["", f"【状态前移】{self.advance_status}{gates}"]
        if self.warnings:
            lines += ["", "【提示（不阻断）】"] + [f"  - {w}" for w in self.warnings]
        if self.error:
            lines += ["", f"  错误：{self.error}"]
        lines += ["", "结果：" + ("通过" if self.ok else "未通过")]
        return "\n".join(lines)


@dataclass
class TaskReport:
    task: str
    workspace: str
    exit_code: int
    test_output: str
    loop: LoopResult | None = None
    changed_files: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and self.exit_code == 0

    def render(self) -> str:
        lines = [
            "能力验证（隔离靶场）",
            f"  工作区：{self.workspace}",
            f"  独立验证：python -m unittest 退出码 = {self.exit_code}",
        ]
        if self.changed_files:
            lines.append("  改动文件：" + "、".join(self.changed_files))
        if self.loop:
            lines += ["", "  " + self.loop.render().replace("\n", "\n  ")]
        if self.test_output:
            tail = self.test_output.strip().splitlines()[-6:]
            lines += ["", "  测试输出（末尾）"] + [f"    {t}" for t in tail]
        if self.error:
            lines += ["", f"  错误：{self.error}"]
        lines += ["", "结果：" + ("通过（独立验证退出码 0）" if self.ok else "未通过")]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 靶场隔离（B3：绝不污染 tests/fixtures）
# ---------------------------------------------------------------------------


def prepare_workspace(fixture: str, target: Path, *, repo_root: Path) -> Path:
    """把靶场复制到目标目录；目标是**副本**，与仓库基线隔离。"""
    src = repo_root / FIXTURES_ROOT_REL / fixture
    if not src.is_dir():
        raise FileNotFoundError(f"靶场不存在：{src}")
    dst = Path(target)
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    return dst


def _snapshot(root: Path) -> dict[str, str]:
    import hashlib

    out: dict[str, str] = {}
    for p in sorted(Path(root).rglob("*")):
        if p.is_file() and ".icode_output" not in p.parts:
            out[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def _changed(before: dict[str, str], after: dict[str, str]) -> list[str]:
    names = set(before) | set(after)
    return sorted(n for n in names if before.get(n) != after.get(n))


def run_unittest(workspace: Path, *, timeout: int = 180) -> tuple[int, str]:
    """**由运行时自己**跑测试取退出码（模型自述不算证据）。"""
    proc = subprocess.run(  # noqa: S603 - 参数列表 + shell=False
        [sys.executable, "-m", "unittest"],
        cwd=str(workspace), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout, shell=False,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


# ---------------------------------------------------------------------------
# 契约步骤（真模型）
# ---------------------------------------------------------------------------


def run_contract_step(
    settings: Settings,
    *,
    backend: Backend,
    workspace: Path,
    step: str = "plan",
    ticket_id: str = "E2E-1",
    requirement: str = "",
    approver: Approver | None = None,
    loop_config: LoopConfig | None = None,
    budget: Budget | None = None,
    on_event=None,
) -> StepReport:
    """按契约执行一个步骤，模型通过工具循环完成该步骤的产物。"""
    workspace = Path(workspace).resolve()
    cp = ControlPlane(settings)
    report = StepReport(step=step, ok=False, out_dir="")

    try:
        contracts = ContractSet.load(settings.gates_json)
        if not contracts.has(step):
            report.error = f"契约未登记步骤 {step}"
            return report
        contract = contracts.step(step)
        report.add(f"契约载入（{step}）", True, f"复检点={list(contract.required_checks)}")

        # 渐进披露：只取门禁强制层，不整篇注入
        guide = load_guide(settings.steps_dir, step)
        brief = ""
        if guide is not None:
            # 先分配工单目录，才能把"输入是否存在"如实写进简报
            from .handshake import next_out_dir

            out_dir = next_out_dir(workspace)
            report.out_dir = str(out_dir)
            brief, _ = guide.mandatory_brief(contract, ticket_dir=out_dir)
            report.add("门禁简报（强制层）", bool(brief), f"{len(brief)} 字符")
        else:
            from .handshake import next_out_dir

            out_dir = next_out_dir(workspace)
            report.out_dir = str(out_dir)

        ok_create = cp.create(out_dir, ticket_id=ticket_id,
                              requirement=requirement or DEFAULT_TASK, birth="plan")
        report.add("工单创建", ok_create.data.get("ok") is True,
                   f"status={ok_create.data.get('status')}")

        attempt = cp.step_start(out_dir, step, ticket_id=ticket_id)
        report.add("step start", bool(attempt), f"attempt={attempt}")

        # 契约驱动的复检点 + 模型工作
        occurrence = 0
        for boundary in contract.required_checks:
            occurrence += 1
            res = cp.step_check(out_dir, step, attempt, boundary,
                                ticket_id=ticket_id, occurrence=occurrence)
            passed = res.data.get("result") == "pass"
            report.add(f"边界复检 {boundary}", passed, f"result={res.data.get('result')}")
            if not passed:
                report.error = f"边界复检 {boundary} 未通过，应回流 {contract.route_for('default')}"
                return report

            if boundary == "before_write":
                loop = _run_agent(
                    backend=backend, workspace=workspace, out_dir=out_dir,
                    ticket_id=ticket_id, step=step, brief=brief, contract=contract,
                    requirement=requirement or DEFAULT_TASK, approver=approver,
                    loop_config=loop_config, budget=budget, on_event=on_event,
                )
                report.loop = loop
                if not loop.ok:
                    # 由**证据**判定成败，而不是由循环的停止原因判定：
                    # 触到回合上限时若必需产物齐备，属软性提示而非失败。
                    report.warn(
                        f"回合循环未自然结束（stop_reason={loop.stop_reason}"
                        f"{'：' + loop.error if loop.error else ''}）；"
                        "本次仍以契约产物是否齐备作为判定依据"
                    )
                # 登记本步骤声明的产物
                missing: list[str] = []
                for port in contract.outputs:
                    if port.kind != "ticket_file" or not port.value:
                        continue
                    target = out_dir / port.value
                    if not target.is_file():
                        report.add(f"产物缺失 {port.value}", False, "模型未产出该文件")
                        missing.append(port.value)
                        continue
                    art = cp.artifact(out_dir, step, attempt, port.value, ticket_id=ticket_id)
                    report.add(f"产物登记 {port.value}", art.data.get("ok") is True, f"port={port.id}")
                    report.artifacts.append(port.value)

        finish = cp.step_finish(
            out_dir, step, attempt,
            "success" if not missing else "failure",
            ticket_id=ticket_id, evidence=["e2e:model-run"], check=False,
        )
        report.finish_outcome = str(finish.data.get("outcome") or "")
        if finish.data.get("ok") is True:
            report.add(f"step finish（outcome={report.finish_outcome}）", True,
                       "回执被控制面接受")
        else:
            detail = str(finish.data.get("error") or "未知原因")
            report.add("step finish（被门禁拒绝，如实上报）", False, detail[:160])

        # 推理 trace：如实写（能力不足就是 degraded）
        gate = ReasoningGate.load(settings.skill_root / "mcp" / "reasoning-gate" / "gates.json")
        row = gate.build_row(ticket_id, step)
        if row is not None:
            append_trace(out_dir / ".thinking_gate_trace.jsonl", [row])
            report.reasoning_rows.append(row)
            report.add("推理 trace 写入", True,
                       f"result={row.result} attempted={row.attempted}")

        # 状态前移（目标状态由 gates.json 的状态机派生；门禁可能拦截，如实上报）
        target_status = contracts.status_for_step(step)
        if target_status:
            tr = cp.transition(out_dir, target_status, ticket_id=ticket_id)
            if tr.data.get("ok") is True:
                report.advance_status = "已前移"
            else:
                report.advance_status = "被门禁拦截（如实上报，未造假）"
                report.advance_gates = [str(g.get("gate_id")) for g in (tr.data.get("failed_gates") or [])]

        trace = cp.trace(out_dir)
        report.trace = trace.data
        report.add("事件链可读", bool(trace.data.get("ok")),
                   f"event_count={trace.data.get('event_count')}")
        report.add("无未闭合步骤/动作",
                   not any([trace.data.get("open_steps"), trace.data.get("open_operations")]))

        report.ok = all(ok for _, ok, _ in report.checkpoints) and not report.error
        return report

    except Exception as exc:  # noqa: BLE001
        report.error = f"{type(exc).__name__}: {exc}"
        return report


def _run_agent(
    *, backend, workspace, out_dir, ticket_id, step, brief, contract, requirement,
    approver, loop_config, budget, on_event,
) -> LoopResult:
    registry = default_registry()
    guard = Guard(Scope(workspace_root=workspace))
    ctx = ToolContext(root=workspace)
    loop = AgentLoop(
        backend=backend,
        registry=registry,
        guard=guard,
        ctx=ctx,
        approver=approver or DenyAllApprover(),
        operations=OperationRecorder(ControlPlane(load_settings_for(workspace)), out_dir, ticket_id),
        budget=BudgetTracker(budget or Budget()),
        config=loop_config or LoopConfig(),
        on_event=on_event,
    )
    outputs = [p.value for p in contract.outputs if p.kind == "ticket_file" and p.value]
    deliverable_lines = [
        f"  - {Path(out_dir) / name}   （端口 {port.id}）"
        for name, port in (
            (p.value, p) for p in contract.outputs if p.kind == "ticket_file" and p.value
        )
    ]
    system = (
        "你是 ICODE 工作流中的执行代理，工作在一个隔离的工作区副本里。\n"
        "你只能通过工具行动；工作区外的读写会被权限模型拒绝。\n\n"
        "【门禁要求（必须遵守）】\n" + brief + "\n\n"
        "【本次实际提供的输入】\n"
        f"  - 需求（已在下方给出，无需寻找）\n"
        f"  - 工单目录：{out_dir}\n"
        "  简报中标为「本次不存在」的输入**不要去找**。\n\n"
        "【本步骤必须落盘的文件（缺一即失败）】\n"
        + ("\n".join(deliverable_lines) if deliverable_lines else "  （本步骤无文件产物）") + "\n"
        "硬性要求：\n"
        "  1. 必须**调用 write_file 工具**把内容写入上面的绝对路径；\n"
        "     只在回复文本里描述内容**不算完成**，步骤会失败。\n"
        "  2. 这些路径位于工单目录内（属于工作区），写入是允许的。\n"
        "  3. 工作区内的工程文件可自由读取与修改；工作区外的读取会被拒绝，不要尝试。\n"
        "  4. 写完后用 read_file 回读确认内容已落盘。\n\n"
        "【行动纪律（重要）】\n"
        "  - 读必要的文件后**立即开始产出产物**，不要把回合花在环境侦察上；\n"
        "  - 禁止为了探查环境而执行 whoami / uname / printenv / basename 这类与产出无关的命令；\n"
        "  - 不确定路径时用 glob 一次即可，不要反复 ls 同一目录。\n"
    )
    if requirement:
        system += f"\n【本次需求】\n{requirement}\n"
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": (
            f"请完成 {step} 步骤，并把产物写入上面列出的绝对路径。"
            "完成后简要说明你写了哪个文件、内容要点是什么。"
        )},
    ]
    return loop.run(messages)


def load_settings_for(_workspace: Path) -> Settings:
    """运行期定位 icode-skill（子模块）；与工作区无关。"""
    from .config import load_settings

    return load_settings()


# ---------------------------------------------------------------------------
# 能力验证（隔离靶场）
# ---------------------------------------------------------------------------


def run_task(
    settings: Settings,
    *,
    backend: Backend,
    workspace: Path,
    task: str = DEFAULT_TASK,
    approver: Approver | None = None,
    loop_config: LoopConfig | None = None,
    budget: Budget | None = None,
    on_event=None,
) -> TaskReport:
    """在隔离工作区用真模型完成一个编码任务，并用**独立跑测试**的退出码验收。"""
    workspace = Path(workspace).resolve()
    before = _snapshot(workspace)

    registry = default_registry()
    guard = Guard(Scope(workspace_root=workspace))
    ctx = ToolContext(root=workspace)
    loop = AgentLoop(
        backend=backend, registry=registry, guard=guard, ctx=ctx,
        approver=approver or DenyAllApprover(),
        budget=BudgetTracker(budget or Budget()),
        config=loop_config or LoopConfig(),
        on_event=on_event,
    )
    system = (
        "你是编码代理，工作在隔离的工作区副本里。\n"
        "用工具读改文件、跑命令。改动必须有依据，最后运行 `python -m unittest` 确认通过。\n"
        "不要修改工作区外的文件。\n"
    )
    result = loop.run([
        {"role": "system", "content": system},
        {"role": "user", "content": task},
    ])

    after = _snapshot(workspace)
    changed = _changed(before, after)
    exit_code, output = run_unittest(workspace)
    return TaskReport(
        task=task, workspace=str(workspace), exit_code=exit_code,
        test_output=output, loop=result, changed_files=changed,
        error=result.error,
    )
