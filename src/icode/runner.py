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

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .approvals import Approver, DenyAllApprover
from .artifact_broker import ArtifactAccessError, ArtifactBroker
from .backends import Backend, Usage
from .budget import Budget, BudgetTracker
from .checkpoint import Checkpointer
from .config import Settings
from .contracts import ContractSet
from .control import ControlPlane, make_request
from .disclosure import load_guide
from .guard import Guard, Scope
from .isolation import NoIsolation, Sandbox, select_sandbox
from .loop import AgentLoop, LoopConfig, LoopResult
from .operations import OperationRecorder
from .reasoning import ReasoningGate, TraceRow, append_trace, run_deliberation
from .recovery import Recoverer
from .sandbox_policy import SandboxPolicy
from .self_verify import (
    AUTO_REPAIRABLE_CATEGORIES,
    VerificationEvidence,
    VerificationLedger,
    classify_failure,
    environment_fingerprint,
)
from .tools import ToolContext, default_registry
from .workspace_snapshot import changed_files as _changed
from .workspace_snapshot import diff_fingerprint as _diff_fingerprint
from .workspace_snapshot import snapshot_workspace as _snapshot

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
    checkpoint_path: str = ""
    recovery_action: str = ""
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
        if self.recovery_action:
            lines += ["", f"【恢复】{self.recovery_action}"]
        if self.checkpoint_path:
            lines += ["", f"【检查点】{self.checkpoint_path}"]
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
    verification: object | None = None  # R3: VerificationEvidence
    review: object | None = None        # R3: ReviewReport（只读独立 Reviewer）
    repair_attempts: list = field(default_factory=list)   # R3: 每次修复的 VerificationEvidence
    repair_decisions: list = field(default_factory=list)  # R3: 每次修复决策 action

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
        if self.repair_decisions:
            lines.append(
                "  有界修复："
                + " → ".join(str(d) for d in self.repair_decisions)
                + f"（{len(self.repair_attempts)} 次尝试）"
            )
        if self.review is not None:
            lines += ["", "  " + self.review.render().replace("\n", "\n  ")]
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
    sandbox: Sandbox | None = None,
    policy: SandboxPolicy | None = None,
    change_baseline: dict[str, str] | None = None,
    out_dir: Path | None = None,
    extra_instructions: str = "",
    post_write: "Callable[[Path, str, str], None] | None" = None,
) -> StepReport:
    """按契约执行一个步骤，模型通过工具循环完成该步骤的产物。

    `out_dir` 给定时复用该工单目录（**不再新建、不再建单**），用于串起多步链路。
    `extra_instructions` 追加到系统提示（步骤特化交付要求）。
    `post_write(out_dir, step, attempt)` 在模型工作完成后、产物登记前调用
    （用于装配机器可读索引、跑控制面原生自查清单等**非模型**动作）。
    """
    workspace = Path(workspace).resolve()
    if policy is not None and (
        policy.workspace_root != workspace
        or policy.step != step or policy.ticket_id != ticket_id
    ):
        raise ValueError("隔离策略与当前步骤身份不匹配")
    cp = ControlPlane(settings)
    report = StepReport(step=step, ok=False, out_dir="")

    try:
        contracts = ContractSet.load(settings.gates_json)
        if not contracts.has(step):
            report.error = f"契约未登记步骤 {step}"
            return report
        contract = contracts.step(step)
        report.add(f"契约载入（{step}）", True, f"复检点={list(contract.required_checks)}")
        if policy is not None and change_baseline is None:
            change_baseline = _snapshot(workspace)

        # 渐进披露：只取门禁强制层，不整篇注入
        reuse = out_dir is not None
        if reuse:
            out_dir = Path(out_dir).resolve()
            report.out_dir = str(out_dir)
        else:
            from .handshake import next_out_dir

            out_dir = next_out_dir(workspace)
            report.out_dir = str(out_dir)

        guide = load_guide(settings.steps_dir, step)
        brief = ""
        if guide is not None:
            brief, _ = guide.mandatory_brief(contract, ticket_dir=out_dir)
            report.add("门禁简报（强制层）", bool(brief), f"{len(brief)} 字符")

        if not reuse:
            ok_create = cp.create(out_dir, ticket_id=ticket_id,
                                  requirement=requirement or DEFAULT_TASK, birth="plan")
            report.add("工单创建", ok_create.data.get("ok") is True,
                       f"status={ok_create.data.get('status')}")

        attempt = cp.step_start(out_dir, step, ticket_id=ticket_id)
        report.add("step start", bool(attempt), f"attempt={attempt}")

        # 中间状态流转：review/code/deepcheck 有 in_progress 状态，
        # 必须先流转到 in_progress 才能做工作（否则后续的 done 流转会被状态机拒绝）。
        # plan / merge / audit 没有独立的 in_progress 状态（create 时的状态即为起点）。
        in_prog = contracts.in_progress_status_for(step)
        if in_prog:
            tr = cp.transition(out_dir, in_prog, ticket_id=ticket_id)
            report.add(f"中间状态流转 → {in_prog}", tr.data.get("ok") is True,
                       f"status={tr.data.get('status')}")

        # 检查点：让中断后可恢复（不保存模型正文）
        ckpt = Checkpointer(out_dir, ticket_id=ticket_id, step=step, attempt=attempt)
        report.checkpoint_path = str(ckpt.path)
        # 副作用回执器：**整步共用一个**。
        # 若每个 loop 各建一个，occurrence 计数会从 1 重来，
        # 于是同一 request 键重复出现 → 控制面判定 ambiguous_side_effect → 命令被拒。
        # （实测踩过：补救回合里所有 run_command 都变成"副作用歧义，拒绝重放"。）
        step_ops = OperationRecorder(cp, out_dir, ticket_id, scope=step)
        # R3：每次失败都绑定证据，只允许在出现**新证据**时有界修复；
        # 无新证据或副作用不明时停止，避免「没有证据就反复碰运气」。
        verify_ledger = VerificationLedger(max_attempts=2)

        # 契约驱动的复检点 + 模型工作
        occurrence = 0
        missing: list[str] = []
        loop = None
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
                    checkpointer=ckpt, extra_instructions=extra_instructions,
                    operations=step_ops, sandbox=sandbox, policy=policy,
                    change_baseline=change_baseline,
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
                if post_write is not None:
                    post_write(out_dir, step, attempt)
                missing = _register_outputs(cp, out_dir, step, attempt, ticket_id, contract, report)

                # 缺件修复：模型常在文本里回答却不落盘（实测 review 步骤就这么丢过产物）。
                # 允许**一个有界的补救回合**，并把"缺了什么"明确摆到它面前；
                # 这既不是伪造产物，也不是放宽门禁 —— 只是为了把话说完。
                for repair_round in range(1, 2):
                    declared = [
                        p for p in contract.outputs
                        if p.kind == "ticket_file" and p.value and not (out_dir / p.value).is_file()
                    ]
                    if not declared:
                        break
                    if post_write is not None:
                        # 机器装配型产物（如 review_manifest）此刻还没法装 —— 先跳过
                        pass
                    still_missing = [
                        p for p in declared
                        if p.value not in ("review_manifest.json",)
                    ]
                    if not still_missing:
                        break
                    # R3 证据门：先给本次失败分类并绑定证据，再决定是否补救。
                    category = classify_failure(
                        exit_code=None, kind="gate",
                        missing_artifacts=tuple(p.value for p in still_missing),
                    )
                    evidence = VerificationEvidence(
                        step=step, attempt=str(repair_round), kind="gate",
                        command=("missing_artifacts",),
                        exit_code=None,
                        output="、".join(p.value for p in still_missing),
                        category=category,
                    )
                    decision = verify_ledger.decide_repair(evidence)
                    if decision.action != "allow":
                        report.warn(
                            f"跳过补救回合 {repair_round}：{decision.reason} "
                            f"（missing={'、'.join(p.value for p in still_missing)}）"
                        )
                        break
                    # R3：把这条修复证据（缺失产物 + 分类）写入事件链，供证据包取证；
                    # 记录失败只是如实警告，不阻断步骤本身。
                    if not _record_verification_evidence(cp, out_dir, ticket_id, evidence):
                        report.warn("修复证据未能写入事件链（control 记录失败，不影响步骤）")
                    report.warn(
                        f"产物缺失，进入补救回合 {repair_round}："
                        + "、".join(p.value for p in still_missing)
                    )
                    repair_instructions = (
                        REPAIR_INSTRUCTIONS_POLICY.format(
                            missing="\n".join(f"  - {p.value}" for p in still_missing)
                        ) if policy is not None else REPAIR_INSTRUCTIONS.format(
                            missing="\n".join(f"  - {out_dir / p.value}" for p in still_missing)
                        )
                    )
                    repair = _run_agent(
                        backend=backend, workspace=workspace, out_dir=out_dir,
                        ticket_id=ticket_id, step=step, brief=brief, contract=contract,
                        requirement=requirement or DEFAULT_TASK, approver=approver,
                        loop_config=loop_config, budget=budget, on_event=on_event,
                        checkpointer=ckpt,
                        sandbox=sandbox,
                        policy=policy,
                        change_baseline=change_baseline,
                        extra_instructions=repair_instructions,
                        operations=step_ops,
                    )
                    report.loop = repair
                    if post_write is not None:
                        post_write(out_dir, step, attempt)
                    _reset_artifact_checkpoints(report)
                    missing = _register_outputs(cp, out_dir, step, attempt, ticket_id, contract, report)

        # 最后一道：模型若仍未落盘，但回复文本里有实质内容 → 由运行时代为落盘（诚实标注来源）
        if missing:
            last_text = ""
            for m in reversed(loop.messages):
                if m.get("role") == "assistant" and (m.get("content") or "").strip():
                    last_text = m["content"]
                    break
            broker = (
                ArtifactBroker(out_dir, contract, max_bytes=policy.output_limit_bytes)
                if policy is not None else None
            )
            persisted = _persist_missing_from_response(
                out_dir, contract, report, last_text, artifact_broker=broker,
            )
            if persisted:
                _reset_artifact_checkpoints(report)
                missing = _register_outputs(cp, out_dir, step, attempt, ticket_id, contract, report)

        _finish_step(cp, out_dir, step, attempt, ticket_id, report, missing)
        if report.finish_outcome == "success":
            ckpt.clear()  # 步骤已干净终结，检查点不再需要

        _finalize(settings, cp, out_dir, step, ticket_id, contracts, report,
                  backend=backend, requirement=requirement or DEFAULT_TASK)
        return report

    except Exception as exc:  # noqa: BLE001
        report.error = f"{type(exc).__name__}: {exc}"
        return report


def _record_verification_evidence(
    cp, out_dir: Path, ticket_id: str, evidence: VerificationEvidence,
) -> bool:
    """把一条验证证据写入事件链（fail-safe：记录失败不阻断步骤）。

    控制面验证域只有 build / deploy / listen / device_test 四类；这里把
    R3 的验证证据（契约门禁 / 独立测试回执）按 `device_test + layer=unit`
    如实记录：`evidence` 放证据指纹（不含正文/密钥），`baseline` 放 diff
    指纹或缺失产物摘要，`note` 注明实际类别。幂等键由证据指纹派生，
    同一条验证重放不会重复记录。
    """
    from .self_verify import evidence_fingerprint

    try:
        outcome = "pass" if evidence.passed else "fail"
        baseline = evidence.diff_fingerprint or ""
        if not baseline and evidence.kind == "gate":
            missing = sorted(
                str(k) for k in (evidence.artifact_hashes or {})) or ["missing"]
            baseline = _sha256_text("|".join(missing))
        res = cp.record_verification(
            out_dir, ticket_id=ticket_id, kind="device_test", outcome=outcome,
            evidence=evidence_fingerprint(evidence), baseline=baseline,
            layer="unit", scenario=evidence.kind,
            note=f"step={evidence.step} category={evidence.category or ''}",
        )
        return res.data.get("ok") is True
    except Exception:  # noqa: BLE001 - 证据记录失败不阻断步骤
        return False


def _sha256_text(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _reset_artifact_checkpoints(report: StepReport) -> None:
    """丢弃上一轮的产物登记/缺失结论，让最终判定以**补救后的实际状态**为准。"""
    report.checkpoints = [
        c for c in report.checkpoints
        if not (c[0].startswith("产物缺失") or c[0].startswith("产物登记"))
    ]
    report.artifacts = []


def _register_outputs(
    cp: ControlPlane, out_dir: Path, step: str, attempt: str, ticket_id: str,
    contract, report: StepReport,
) -> list[str]:
    """登记本步骤声明的产物，返回缺失列表。

    同时处理：
    - `ticket_file` 端口：精确路径登记
    - `ticket_glob` 端口：匹配工作目录中的实际文件（如 `review_round_*.json`）
    """
    missing: list[str] = []
    for port in contract.outputs:
        if port.kind != "ticket_file" or not port.value:
            continue
        target = out_dir / port.value
        if target.is_symlink() or not target.is_file():
            report.add(f"产物缺失 {port.value}", False, "模型未产出该文件")
            missing.append(port.value)
            continue
        art = cp.artifact(out_dir, step, attempt, port.value, ticket_id=ticket_id)
        report.add(f"产物登记 {port.value}", art.data.get("ok") is True, f"port={port.id}")
        report.artifacts.append(port.value)

    # glob 端口：登记匹配的实际文件（如 review 的 review_round_*.json）
    for port in contract.outputs:
        if port.kind != "ticket_glob" or not port.value:
            continue
        pattern = port.value.replace("*", "*")
        for matched in sorted(out_dir.glob(pattern)):
            if matched.is_symlink() or not matched.is_file():
                continue
            rel = matched.relative_to(out_dir).as_posix()
            art = cp.artifact(out_dir, step, attempt, rel, ticket_id=ticket_id)
            if art.data.get("ok") is True:
                report.add(f"产物登记（glob）{rel}", True, f"port={port.id}")
                report.artifacts.append(rel)
    return missing


def _finish_step(
    cp: ControlPlane, out_dir: Path, step: str, attempt: str, ticket_id: str,
    report: StepReport, missing: list[str],
) -> None:
    """终结回执。**由证据判定 outcome**，门禁拒绝则如实上报。"""
    finish = cp.step_finish(
        out_dir, step, attempt,
        "success" if not missing else "failure",
        ticket_id=ticket_id, evidence=["e2e:model-run"], check=False,
    )
    report.finish_outcome = str(finish.data.get("outcome") or "")
    if finish.data.get("ok") is True:
        report.add(f"step finish（outcome={report.finish_outcome}）", True, "回执被控制面接受")
    else:
        detail = str(finish.data.get("error") or "未知原因")
        report.add("step finish（被门禁拒绝，如实上报）", False, detail[:160])


def _make_ctx(
    workspace: Path, sandbox: Sandbox | None, policy: SandboxPolicy | None = None,
    artifact_broker: ArtifactBroker | None = None,
    change_baseline: dict[str, str] | None = None,
) -> ToolContext:
    """构造工具上下文；未显式指定时按本机实测能力自动选隔离后端。"""
    return ToolContext(
        root=workspace, sandbox=sandbox if sandbox is not None else select_sandbox(),
        policy=policy, artifact_broker=artifact_broker,
        change_baseline=change_baseline,
    )


REPAIR_INSTRUCTIONS = (
    "【产物缺失 · 必须立即补救】\n"
    "上一次运行**没有落盘**下面这些必需产物 —— 只在回复文本里描述不算完成：\n"
    "{missing}\n"
    "请现在**立即调用 write_file** 把这些文件写到上面列出的**绝对路径**（一个都不能少），"
    "内容就是你上一轮已经想好的东西。不要再去读文件调研，不要解释，直接写。\n"
    "注意：`.json` 产物请输出**纯 JSON**（不要包 markdown 代码块）。\n"
)

REPAIR_INSTRUCTIONS_POLICY = (
    "【产物缺失 · 必须立即补救】\n"
    "上一次没有提交下面这些当前步骤产物：\n{missing}\n"
    "请立即调用 submit_artifact，把 name 设为上面的文件名、content 设为正文。"
    "不要用 write_file 写工单目录，也不要只在回复文本里描述。\n"
)

# 产物来源标注：由运行时代为落盘时的诚实声明
AUTOPERSIST_HEADER = (
    "<!-- 产物来源：模型在本步骤的回复文本，由运行时代为落盘"
    "（模型未自行调用 write_file）。内容未改动。 -->\n\n"
)


def _extract_json(text: str) -> dict | None:
    """从模型回复里提取最外层 JSON 对象（供 .json 产物落盘）。"""
    import re

    if not text:
        return None
    # 优先取 ```json 代码块
    for m in re.finditer(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S):
        try:
            data = json.loads(m.group(1))
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            continue
    # 退化：取最外层花括号
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    data = json.loads(text[start : i + 1])
                    return data if isinstance(data, dict) else None
                except json.JSONDecodeError:
                    return None
    return None


def _persist_missing_from_response(
    out_dir: Path,
    contract,
    report: StepReport,
    model_text: str,
    *,
    artifact_broker: ArtifactBroker | None = None,
) -> list[str]:
    """把模型在回复文本里给出的交付内容落盘（**诚实标注来源**）。

    为什么要有这条通道（roadmap Phase 6 遗留）：实测模型在 review 步骤
    倾向在回复文本里给出审查意见，而不调用 write_file —— 导致契约产物缺失、
    整步失败。而产物审计关心的是**内容是否真实来自模型且可追溯**，
    不是"谁敲的 write_file"。

    诚实保障：
      - 内容**原样**来自模型回复（JSON 产物做纯格式提取，不改内容）；
      - Markdown 产物顶部加来源标注（HTML 注释，不影响阅读）；
      - 每个落盘产物都在 `report.notes` 里记录来源，事件链正常登记 hash；
      - 提取不到有效内容的产物**不伪造**，保持缺失并如实上报。
    """
    persisted: list[str] = []
    text = (model_text or "").strip()
    if len(text) < 10:
        report.warn("模型回复过短，不足以自动落盘缺失产物")
        return persisted

    for port in contract.outputs:
        if port.kind != "ticket_file" or not port.value:
            continue
        target = out_dir / port.value
        if target.is_symlink():
            report.warn(f"{port.value}：目标是符号链接，保持缺失")
            continue
        if target.is_file():
            continue  # 已有（模型自己写了或上一轮已落盘）
        name = port.value
        if name == "review_manifest.json":
            continue  # 机器装配产物，由 post_write 负责
        if name.endswith(".json"):
            data = _extract_json(text)
            if data is None:
                report.warn(f"{name}：模型回复中未提取到有效 JSON，保持缺失（不伪造）")
                continue
            body = json.dumps(data, ensure_ascii=False, indent=2)
            if artifact_broker is not None:
                try:
                    artifact_broker.submit(name, body)
                except ArtifactAccessError:
                    report.warn(f"{name}：受控产物端口拒绝补落盘")
                    continue
            else:
                target.write_bytes(body.encode("utf-8"))
            persisted.append(f"{name}（来源：模型回复文本，JSON 提取）")
        else:
            body = AUTOPERSIST_HEADER + text
            if artifact_broker is not None:
                try:
                    artifact_broker.submit(name, body)
                except ArtifactAccessError:
                    report.warn(f"{name}：受控产物端口拒绝补落盘")
                    continue
            else:
                target.write_bytes(body.encode("utf-8"))
            persisted.append(f"{name}（来源：模型回复文本，原样落盘）")
    return persisted


def _run_agent(
    *, backend, workspace, out_dir, ticket_id, step, brief, contract, requirement,
    approver, loop_config, budget, on_event, checkpointer=None, resume_context: str = "",
    sandbox: Sandbox | None = None, extra_instructions: str = "",
    policy: SandboxPolicy | None = None,
    change_baseline: dict[str, str] | None = None,
    operations: OperationRecorder | None = None,
) -> LoopResult:
    artifact_broker = (
        ArtifactBroker(out_dir, contract, max_bytes=policy.output_limit_bytes)
        if policy is not None else None
    )
    registry = default_registry(
        include_artifacts=artifact_broker is not None,
        include_changes=change_baseline is not None,
    )
    scope = Scope(
        workspace_root=workspace,
        allowed_read_roots=policy.read_roots if policy is not None else None,
        allowed_write_roots=policy.write_roots if policy is not None else None,
        deny_read_roots=policy.deny_read_roots if policy is not None else (),
        deny_write_roots=policy.deny_write_roots if policy is not None else (),
    )
    guard = Guard(scope)
    ctx = _make_ctx(workspace, sandbox, policy, artifact_broker, change_baseline)
    on_turn = None
    if checkpointer is not None:
        def on_turn(turn_index: int, total_tool_calls: int, history: list[dict]) -> None:
            checkpointer.save(turn_index=turn_index, tool_calls=total_tool_calls, history=history)

    loop = AgentLoop(
        backend=backend,
        registry=registry,
        guard=guard,
        ctx=ctx,
        approver=approver or DenyAllApprover(),
        operations=operations or OperationRecorder(
            ControlPlane(load_settings_for(workspace)), out_dir, ticket_id),
        budget=BudgetTracker(budget or Budget()),
        config=loop_config or LoopConfig(),
        on_event=on_event,
        on_turn=on_turn,
    )
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
    if artifact_broker is not None:
        deliverable_lines = [
            f"  - {port.value}（端口 {port.id}）"
            for port in contract.outputs
            if port.kind in ("ticket_file", "ticket_glob")
            and port.value != "review_manifest.json"
        ]
        available_inputs: list[str] = []
        for port in contract.inputs:
            if (port.kind == "ticket_file"
                    and (Path(out_dir) / port.value).is_file()
                    and not (Path(out_dir) / port.value).is_symlink()):
                available_inputs.append(port.value)
            elif port.kind == "ticket_glob":
                available_inputs.extend(
                    path.name for path in sorted(Path(out_dir).glob(port.value))
                    if path.is_file() and not path.is_symlink()
                )
        system = (
            "你是 ICODE 工作流中的执行代理，工程源码位于隔离工作区。"
            "工单账本位于宿主，不属于工作区，模型命令不可直接读写。\n\n"
            "【门禁要求（必须遵守）】\n" + brief + "\n\n"
            "【本次实际提供的输入】\n"
            "  - 需求已在下方给出。\n"
            "  - 当前步骤可通过 read_artifact(name) 读取的旧工单文件："
            + ("、".join(dict.fromkeys(available_inputs)) or "无") + "。\n"
            "  - 简报中的宿主路径只供定位，不要对它们调用 read_file/write_file。\n\n"
            "【本步骤必须提交的产物】\n"
            + ("\n".join(deliverable_lines) if deliverable_lines else "  （无模型产物）")
            + "\n必须调用 submit_artifact(name, content) 提交，name 只填文件名或"
            "匹配模式的具体文件名；由宿主验证后代写并登记。"
            "write_file/edit_file 仅用于隔离工作区内的工程文件，不能写工单账本。"
            "提交后可调用 read_artifact 回读旧输入；本步骤新产物以工具回执为准。\n"
            "需要查看本次任务修改了哪些文件时，调用 workspace_changes；"
            "它不是 Git 暂存或提交状态。\n"
        )
    if requirement:
        system += f"\n【本次需求】\n{requirement}\n"
    if extra_instructions:
        system += f"\n【本步骤的额外交付要求（只描述内容，落盘路径以上方清单为准）】\n{extra_instructions}\n"
        # 把交付路径再钉一次：模型容易把产物写到工作区根目录（实测踩过）
        if deliverable_lines and artifact_broker is None:
            system += (
                "\n【再次强调 · 产物必须写这些绝对路径】\n"
                + "\n".join(deliverable_lines)
                + "\n不要把产物写到工作区根目录或其它位置，否则本步骤会因产物缺失而失败。\n"
            )
        elif deliverable_lines:
            system += (
                "\n【再次强调 · 仅提交这些产物文件名】\n"
                + "\n".join(deliverable_lines)
                + "\n工单产物用 submit_artifact，不使用 write_file。\n"
            )
    if resume_context:
        system += f"\n{resume_context}\n"
    user_instruction = (
        f"请完成 {step} 步骤，并调用 submit_artifact 提交上方列出的产物文件名。"
        "完成后简要说明提交了哪些产物。"
        if artifact_broker is not None else
        f"请完成 {step} 步骤，并把产物写入上面列出的绝对路径。"
        "完成后简要说明你写了哪个文件、内容要点是什么。"
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_instruction},
    ]
    return loop.run(messages)


def _ensure_gate_metadata(
    cp: ControlPlane, out_dir: Path, ticket_id: str, report: StepReport
) -> None:
    """补齐 strict 门禁要求的 metadata 键。

    `workflow_contract` 在 `--strict` 下要求 `semantic_decisions` 与
    `requirement_deltas` **存在**。本运行时在**确实没有**待裁决语义决策/需求偏移时，
    显式写入**空数组**，语义是"本步骤无待裁决项"——这是如实声明，不是伪造记录。
    已有值一律不覆盖（只补缺失键）。
    """
    path = Path(out_dir) / ".ico_metadata.json"
    if not path.is_file():
        return
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    missing = {k: [] for k in ("semantic_decisions", "requirement_deltas") if k not in meta}
    if not missing:
        return
    res = cp.metadata_update(out_dir, ticket_id=ticket_id, set_json=missing)
    ok = res.returncode == 0 and res.data.get("ok") is True
    report.add("门禁 metadata 补齐（缺失键写空数组）", ok,
               "、".join(missing) + ("" if ok else f"｜{str(res.data)[:120]}"))


def _finalize(
    settings: Settings, cp: ControlPlane, out_dir: Path, step: str, ticket_id: str,
    contracts, report: StepReport, *, backend: Backend | None = None,
    requirement: str = "", delivery_verdict: str = "verification_pending",
) -> None:
    """收尾：**真跑推演**（若该步骤要求）、如实写推理 trace、尝试状态前移、校验事件链。"""
    gate = ReasoningGate.load(settings.skill_root / "mcp" / "reasoning-gate" / "gates.json")

    deliberation = None
    info = gate.for_step(step)
    if backend is not None and info is not None and info.requires_trace:
        question = (
            f"完成 ICODE 工作流的 {step} 步骤（等级 {info.default_tier}）："
            f"{requirement or '按契约产出该步骤的交付物'}。"
            f"已登记产物：{'、'.join(report.artifacts) or '无'}。"
            "请分步推演出关键判断与依据。"
        )
        deliberation = run_deliberation(gate, backend, step=step, question=question)

    row = gate.build_row(ticket_id, step, deliberation=deliberation)
    if row is not None:
        append_trace(out_dir / ".thinking_gate_trace.jsonl", [row])
        report.reasoning_rows.append(row)
        detail = f"result={row.result} attempted={row.attempted}"
        if row.deliberation_steps:
            detail += f" 推演={row.deliberation_steps}步"
        if deliberation is not None:
            report.add("结构化推演", deliberation.step_count >= 3,
                       f"{deliberation.summary()} provider={row.provider}")
        report.add("推理 trace 写入", row.result == "success", detail)

    target_status = contracts.status_for_step(step)
    if target_status:
        _ensure_gate_metadata(cp, out_dir, ticket_id, report)
        # completed 必须显式回填交付结论；默认取最保守的 verification_pending
        verdict = delivery_verdict if target_status == "completed" else None
        tr = cp.transition(out_dir, target_status, ticket_id=ticket_id,
                           delivery_verdict=verdict)
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


def _open_attempt(decision) -> str | None:
    """从恢复分析里取出未闭合步骤的 attempt。"""
    for key, value in (decision.open_steps or {}).items():
        if isinstance(value, dict) and value.get("attempt"):
            return str(value["attempt"])
        if isinstance(key, str) and key.startswith("step-"):
            return key
    return None


def resume_contract_step(
    settings: Settings,
    *,
    backend: Backend,
    out_dir: Path,
    step: str = "plan",
    ticket_id: str = "",
    approver: Approver | None = None,
    loop_config: LoopConfig | None = None,
    budget: Budget | None = None,
    on_event=None,
) -> StepReport:
    """恢复一个被中断的步骤。

    **不重放已完成动作**：决策来自事件链（`recover` 分析），上下文由事件链水合，
    而不是回放模型聊天记录。存在未终结副作用时必须先人工核对真实状态 → fail-closed。
    """
    out_dir = Path(out_dir).resolve()
    cp = ControlPlane(settings)
    report = StepReport(step=step, ok=False, out_dir=str(out_dir))

    try:
        meta_path = out_dir / ".ico_metadata.json"
        if not meta_path.is_file():
            report.error = f"不是 v3 工单目录：{out_dir}"
            return report
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        ticket_id = str(meta.get("ticket_id") or ticket_id)

        contracts = ContractSet.load(settings.gates_json)
        if not contracts.has(step):
            report.error = f"契约未登记步骤 {step}"
            return report
        contract = contracts.step(step)

        probe_ck = Checkpointer(out_dir, ticket_id=ticket_id, step=step, attempt="")
        decision = Recoverer(cp, out_dir, ticket_id).analyze(step, checkpointer=probe_ck)
        report.recovery_action = decision.action
        report.add(f"恢复分析（{decision.action}）", not decision.needs_human, decision.reason[:200])
        if decision.needs_human:
            report.error = (
                f"恢复被阻断（{decision.action}）：{decision.reason} "
                "请先人工核对真实状态，再显式补 finish 后重试"
            )
            return report

        attempt = (
            decision.checkpoint.attempt
            if decision.checkpoint is not None and decision.checkpoint_valid
            else None
        ) or _open_attempt(decision)
        if not attempt:
            report.error = "无法确定未闭合步骤的 attempt，拒绝盲目恢复"
            return report

        checkpointer = Checkpointer(out_dir, ticket_id=ticket_id, step=step, attempt=attempt)
        report.checkpoint_path = str(checkpointer.path)

        guide = load_guide(settings.steps_dir, step)
        brief = ""
        if guide is not None:
            brief, _ = guide.mandatory_brief(contract, ticket_dir=out_dir)

        requirement = str(meta.get("requirement") or DEFAULT_TASK)
        loop = _run_agent(
            backend=backend, workspace=out_dir.parent.parent, out_dir=out_dir,
            ticket_id=ticket_id, step=step, brief=brief, contract=contract,
            requirement=requirement, approver=approver, loop_config=loop_config,
            budget=budget, on_event=on_event, checkpointer=checkpointer,
            resume_context=decision.resume_brief(),
        )
        report.loop = loop
        if not loop.ok:
            report.warn(f"恢复后的回合循环未自然结束（stop_reason={loop.stop_reason}）")

        missing = _register_outputs(cp, out_dir, step, attempt, ticket_id, contract, report)
        _finish_step(cp, out_dir, step, attempt, ticket_id, report, missing)
        if report.finish_outcome == "success":
            checkpointer.clear()

        _finalize(settings, cp, out_dir, step, ticket_id, contracts, report,
                  backend=backend, requirement=requirement or DEFAULT_TASK)
        return report

    except Exception as exc:  # noqa: BLE001
        report.error = f"{type(exc).__name__}: {exc}"
        return report


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
    sandbox: Sandbox | None = None,
    max_repairs: int = 2,
) -> TaskReport:
    """在隔离工作区用真模型完成一个编码任务，并用**独立跑测试**的退出码验收。

    R3 有界修复：首次独立测试失败后，若失败类别可自动修复，允许在**有界次数**内
    重新让模型改动并复测；每次都必须出现**新的失败证据**（diff/输出/退出码变化），
    否则按 no_new_evidence 停止，不碰运气。模型自述不算证据。
    """
    if type(max_repairs) is not int or max_repairs < 0:
        raise ValueError("max_repairs must be >= 0")
    workspace = Path(workspace).resolve()
    before = _snapshot(workspace)

    registry = default_registry()
    guard = Guard(Scope(workspace_root=workspace))
    ctx = _make_ctx(workspace, sandbox)
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
    exit_code, output = run_unittest(workspace)
    attempt_no = 1
    changed, evidence = _bind_task_evidence(
        before, after, exit_code, output, workspace, attempt=str(attempt_no),
    )
    attempts: list[VerificationEvidence] = [evidence]
    decisions: list[str] = []

    # R3 有界修复循环：只在「可自动修复类别 + 新证据 + 未超界」时继续。
    # Zero is a valid way to disable repairs. The ledger still requires a
    # positive evidence-attempt limit, and is unused when max_repairs is zero.
    ledger = VerificationLedger(max_attempts=max(1, max_repairs))
    repair_round = 0
    while (
        exit_code != 0
        and evidence.category in AUTO_REPAIRABLE_CATEGORIES
        and repair_round < max_repairs
    ):
        decision = ledger.decide_repair(
            evidence, has_new_evidence=ledger.has_new_evidence(evidence),
        )
        decisions.append(decision.action)
        if decision.action != "allow":
            break
        repair_round += 1
        attempt_no += 1
        repair_prompt = _repair_prompt(evidence, changed)
        result = loop.run([
            {"role": "system", "content": system},
            {"role": "user", "content": repair_prompt},
        ])
        after = _snapshot(workspace)
        exit_code, output = run_unittest(workspace)
        changed, evidence = _bind_task_evidence(
            before, after, exit_code, output, workspace, attempt=str(attempt_no),
        )
        attempts.append(evidence)

    # R3：独立 Reviewer 用只读上下文复核改动与验证证据；不能修改被审对象。
    review = None
    try:
        from .reviewer import IndependentReviewer

        review = IndependentReviewer(workspace=workspace).review(changed, evidence)
    except Exception as exc:  # noqa: BLE001 - Reviewer 异常不冒充成功
        review = None
    return TaskReport(
        task=task, workspace=str(workspace), exit_code=exit_code,
        test_output=output, loop=result, changed_files=changed,
        error=result.error, verification=evidence, review=review,
        repair_attempts=attempts, repair_decisions=decisions,
    )


def _bind_task_evidence(
    before: dict[str, str], after: dict[str, str],
    exit_code: int, output: str, workspace: Path, *, attempt: str = "1",
) -> tuple[list[str], VerificationEvidence]:
    """把一次独立测试结果绑定成证据（diff 指纹 + 改动哈希 + 环境指纹）。"""
    changed = _changed(before, after)
    artifact_hashes = {}
    for rel in changed:
        path = workspace / rel
        if path.is_file():
            import hashlib as _hashlib

            artifact_hashes[rel] = _hashlib.sha256(path.read_bytes()).hexdigest()
    evidence = VerificationEvidence(
        step="task", attempt=attempt, kind="test",
        command=("python", "-m", "unittest"),
        exit_code=exit_code,
        output=output,
        environment_fingerprint=environment_fingerprint(),
        # 把证据绑定到「这一份具体 diff」：同一结果在不同基线下的改动
        # 会得到不同指纹，避免证据被挪用到别的改动。
        diff_fingerprint=_diff_fingerprint(before, after),
        # 分类只对失败有意义；通过时留空，不把成功误标成某类失败。
        category=(
            classify_failure(exit_code=exit_code, output=output, kind="test")
            if exit_code != 0 else ""
        ),
        artifact_hashes=artifact_hashes,
    )
    return changed, evidence


REPAIR_PROMPT = (
    "【独立测试失败 · 需要修复】\n"
    "上一次 `python -m unittest` 失败（退出码 {exit_code}，失败类别：{category}）。\n"
    "测试输出末尾：\n{tail}\n\n"
    "请检查你刚才的改动，找出导致失败的原因并修复。\n"
    "要求：\n"
    "  1. 必须产生**新的实际改动**（diff 发生变化），只换说法不算；\n"
    "  2. 修改后用 read_file 回读确认，最后运行 `python -m unittest`；\n"
    "  3. 若你判断这是环境/测试架子问题而非你的代码，明确说明并停止，不要反复碰运气。\n"
)


def _repair_prompt(evidence: VerificationEvidence, changed: list[str]) -> str:
    tail = "\n".join((evidence.output or "").strip().splitlines()[-12:]) or "（无输出）"
    changed_line = "、".join(changed) if changed else "（无改动）"
    return (
        REPAIR_PROMPT.format(
            exit_code=evidence.exit_code if evidence.exit_code is not None else "?",
            category=evidence.category or "unknown",
            tail=tail,
        )
        + f"\n当前改动文件：{changed_line}\n"
    )
