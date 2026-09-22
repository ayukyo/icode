"""契约握手里程碑（Phase 1 核心交付）。

目的：在**不接真模型、不联网、零成本**的前提下，证明本 Agent 与控制面完全对齐。

流程完全由 `gates.json` 的 step_contracts 驱动，不写死步骤表也不写死复检顺序：
    create → step start
           → 按契约顺序执行 required_checks
             · before_write 之前先落产物，再逐个登记 artifact
             · after_wait 边界做一次 check
           → step finish(success)
           → transition 推进状态
           → trace 校验事件链

注意：握手产生的 `01_plan.md` 是**契约探测产物，不是真实计划**，
不可被当作任何真实交付的证据。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .config import Settings
from .contracts import ContractSet, StepContract
from .control import ControlPlane, make_request
from .disclosure import load_guide

PROBE_BANNER = "<!-- 契约探测产物：由 icode handshake 生成，非真实计划，不可作为交付证据 -->"

# 步骤 -> 完成后目标状态：**从 gates.json 的 state_machine 派生**（不写死映射）。
# 见 ContractSet.status_for_step()。


@dataclass
class Checkpoint:
    name: str
    ok: bool
    detail: str = ""

    def __str__(self) -> str:
        return f"{'OK  ' if self.ok else 'FAIL'} {self.name}" + (f" :: {self.detail}" if self.detail else "")


@dataclass
class AdvanceOutcome:
    """状态前移结果。

    `blocked` 对"契约探测"而言是**预期且正确**的行为：
    门禁要求真实证据（思考 trace、语义决策记录…），而探测件没有，
    所以门禁应当拒绝前移 —— 我们**不伪造证据**去凑前移。
    """

    status: str  # passed | blocked | failed | skipped
    target: str
    failed_gates: list[dict] = field(default_factory=list)
    note: str = ""

    @property
    def blocked_by_evidence(self) -> bool:
        return self.status == "blocked"


@dataclass
class HandshakeReport:
    ticket_id: str
    out_dir: str
    step: str
    checkpoints: list[Checkpoint] = field(default_factory=list)
    trace: dict = field(default_factory=dict)
    advance: AdvanceOutcome | None = None
    error: str = ""

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.checkpoints.append(Checkpoint(name=name, ok=ok, detail=detail))

    @property
    def ok(self) -> bool:
        """契约层是否全部通过（状态前移被门禁拦截**不算失败**）。"""
        return not self.error and all(c.ok for c in self.checkpoints)

    def render(self) -> str:
        lines = [
            f"契约握手：{self.step}  工单={self.ticket_id}",
            f"工单目录：{self.out_dir}",
            "",
            "【契约层】",
        ]
        lines += [f"  {c}" for c in self.checkpoints]
        if self.trace:
            lines += [
                "",
                "【事件链】",
                f"  event_count={self.trace.get('event_count')} status={self.trace.get('status')}",
                f"  未闭合：steps={len(self.trace.get('open_steps') or {})} "
                f"operations={len(self.trace.get('open_operations') or {})} "
                f"agents={len(self.trace.get('open_agents') or [])}",
            ]
        if self.advance is not None:
            lines += ["", f"【状态前移 -> {self.advance.target}】"]
            if self.advance.status == "passed":
                lines.append("  OK   状态已前移")
            elif self.advance.status == "blocked":
                lines.append("  BLOCK 被门禁拦截（探测件无真实证据，属预期行为，未造假）")
                for g in self.advance.failed_gates:
                    lines.append(f"         - {g['gate_id']}：{g.get('issues') or g.get('detail', '')}")
                lines.append("         待补证据见 docs/upstream-contract.md")
            elif self.advance.status == "skipped":
                lines.append(f"  SKIP {self.advance.note or '该步骤不参与主流程'}")
            else:
                lines.append(f"  FAIL {self.advance.note}")
        if self.error:
            lines += ["", f"  错误：{self.error}"]
        lines += ["", "结果：" + ("契约握手通过" if self.ok else "未通过")]
        return "\n".join(lines)


def next_out_dir(workspace: Path) -> Path:
    """在 workspace 下分配下一个 `.icode_output_N` 目录（与上游约定一致）。"""
    root = Path(workspace) / ".icode_output"
    root.mkdir(parents=True, exist_ok=True)
    n = 1
    while (root / f".icode_output_{n}").exists():
        n += 1
    out = root / f".icode_output_{n}"
    out.mkdir(parents=True)
    return out


def _ticket_file_outputs(contract: StepContract) -> tuple[tuple[str, str], ...]:
    """契约中需要落盘的产物：(端口 id, 相对路径)。glob 类产物跳过。"""
    out: list[tuple[str, str]] = []
    for port in contract.outputs:
        if port.kind == "ticket_file" and port.value:
            out.append((port.id, port.value))
    return tuple(out)


def _probe_body(step: str, contract: StepContract) -> str:
    ports = "\n".join(f"- {p.kind}: {p.value}{' （必需）' if p.required else ''}" for p in contract.outputs)
    return (
        f"{PROBE_BANNER}\n\n"
        f"# 契约探测：{step}\n\n"
        f"本文件由 `icode handshake` 离线生成，用于验证控制面契约握手，\n"
        f"**不代表真实交付内容**，不得作为证据引用。\n\n"
        f"## 该步骤声明的产物端口\n\n{ports}\n"
    )


def _summarize_failed_gates(data: dict) -> list[dict]:
    """从 transition 的失败响应中抽取门禁缺口（gate_id + 具体 issues）。"""
    out: list[dict] = []
    for g in data.get("failed_gates") or []:
        gate_id = str(g.get("gate_id", "unknown"))
        detail = g.get("detail")
        issues: list[str] = []
        if isinstance(detail, str):
            try:
                parsed = json.loads(detail)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                for item in parsed.get("gates") or []:
                    issues.extend(str(i) for i in (item.get("issues") or []))
                for item in parsed.get("steps") or []:
                    issues.extend(str(i) for i in (item.get("issues") or []))
        if not issues and isinstance(detail, str):
            issues = [detail[:200]]
        out.append({"gate_id": gate_id, "issues": issues})
    return out


def run_handshake(
    settings: Settings,
    *,
    workspace: Path,
    step: str = "plan",
    ticket_id: str = "HANDSHAKE-1",
    requirement: str = "离线契约握手：验证 Agent 与控制面的步骤/边界/产物契约对齐",
) -> HandshakeReport:
    """执行一次完整的离线握手。全程不联网、不调用模型。

    边界说明：本函数**只验证契约层**（start/check/artifact/finish/trace）。
    状态前移会尝试执行，但若门禁要求真实证据（思考 trace、语义决策…），
    探测件会被正确拦截 —— 这是预期结果，**不视为失败，也不伪造证据**。
    """
    workspace = Path(workspace).resolve()
    cp = ControlPlane(settings)
    report: HandshakeReport | None = None

    try:
        contracts = ContractSet.load(settings.gates_json)
        report = HandshakeReport(ticket_id=ticket_id, out_dir="", step=step)
        report.add("载入 gates.json 契约", True, f"schema_version={contracts.schema_version}，{len(contracts.steps())} 个已登记步骤")

        if not contracts.has(step):
            report.add(f"步骤 {step} 已在契约中登记", False, f"已登记：{', '.join(contracts.steps())}")
            return report
        contract = contracts.step(step)
        report.add(f"步骤 {step} 已在契约中登记", True, f"复检点={list(contract.required_checks)}")

        # 渐进披露：门禁简报（强制层）必须先于执行拿到
        guide = load_guide(settings.steps_dir, step)
        if guide is not None:
            brief, truncated = guide.mandatory_brief(contract)
            report.add(
                "门禁简报（强制注入层）可用",
                bool(brief),
                f"{len(brief)} 字符 / 全文 {guide.total_chars} 字符"
                + ("（超预算已截断）" if truncated else ""),
            )
        else:
            report.add("门禁简报（强制注入层）可用", True, "steps/ 无对应文档，仅用机器契约")
            brief = ""

        out_dir = next_out_dir(workspace)
        report.out_dir = str(out_dir)

        # 1) 建单
        created = cp.create(
            out_dir, ticket_id=ticket_id, requirement=requirement, birth="plan",
        )
        report.add("工单创建（create）", created.ok and created.data.get("ok") is True,
                   f"status={created.data.get('status')}")

        # 2) step start
        attempt = cp.step_start(out_dir, step, ticket_id=ticket_id)
        report.add("步骤开始（step start）", bool(attempt), f"attempt={attempt}")

        # 3) 按契约顺序执行复检点
        occurrence = 0
        written: set[str] = set()
        for boundary in contract.required_checks:
            if boundary == "after_wait":
                occurrence += 1
                res = cp.step_check(out_dir, step, attempt, boundary,
                                    ticket_id=ticket_id, occurrence=occurrence)
                report.add(f"边界复检 {boundary}", res.data.get("result") == "pass",
                           f"result={res.data.get('result')}")
                continue

            occurrence += 1
            res = cp.step_check(out_dir, step, attempt, boundary,
                                ticket_id=ticket_id, occurrence=occurrence)
            ok = res.data.get("result") == "pass"
            report.add(f"边界复检 {boundary}", ok, f"result={res.data.get('result')}")
            if not ok:
                report.error = f"边界复检 {boundary} 未通过，按契约应回流 {contract.route_for('default')}"
                return report

            if boundary == "before_write":
                for port_id, rel in _ticket_file_outputs(contract):
                    target = out_dir / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(_probe_body(step, contract), encoding="utf-8")
                    art = cp.artifact(out_dir, step, attempt, rel, ticket_id=ticket_id)
                    report.add(f"产物登记 {rel}", art.ok and art.data.get("ok") is True,
                               f"port={port_id}")
                    written.add(rel)

        # 4) 终结回执
        finish = cp.step_finish(out_dir, step, attempt, "success",
                                ticket_id=ticket_id, evidence=["handshake:offline"])
        report.add("步骤终结（finish success）", finish.data.get("ok") is True,
                   f"outcome={finish.data.get('outcome')}")

        # 5) 状态流转（目标状态由 gates.json 的状态机派生，不写死）
        #    门禁要求真实证据，探测件通常会被拦下 —— 如实记录，不造假、不算失败。
        target_status = contracts.status_for_step(step)
        if target_status:
            tr = cp.transition(out_dir, target_status, ticket_id=ticket_id)
            if tr.returncode == 0 and tr.data.get("ok") is True:
                report.advance = AdvanceOutcome(status="passed", target=target_status)
            elif tr.data.get("fail_closed"):
                report.advance = AdvanceOutcome(
                    status="blocked",
                    target=target_status,
                    failed_gates=_summarize_failed_gates(tr.data),
                    note=str(tr.data.get("error", "")),
                )
            else:
                report.advance = AdvanceOutcome(
                    status="failed", target=target_status,
                    note=str(tr.data.get("error") or tr.data.get("raw") or "未知原因"),
                )
            if report.advance.status == "blocked":
                gates = ", ".join(g["gate_id"] for g in report.advance.failed_gates)
                report.add("状态前移被门禁拦截（预期：探测件无真实证据）", True,
                           f"待补证据门禁 = {gates}")
        else:
            report.advance = AdvanceOutcome(
                status="skipped", target="-", note="该步骤不参与主流程状态流转")
            report.add("状态流转（该步骤不参与主流程）", True, "跳过")

        # 6) 事件链校验
        trace = cp.trace(out_dir)
        report.trace = trace.data
        chain_ok = bool(trace.data.get("ok"))
        report.add("事件链可读（trace）", chain_ok,
                   f"event_count={trace.data.get('event_count')}")
        closed = not any([
            trace.data.get("open_steps"), trace.data.get("open_operations"),
            trace.data.get("open_agents"),
        ])
        report.add("无未闭合步骤/动作/代理", closed,
                   f"open_steps={trace.data.get('open_steps')} "
                   f"open_ops={list((trace.data.get('open_operations') or {}).keys())}")

        report.add("握手产物标注为探测（非证据）",
                   all((out_dir / rel).read_text(encoding="utf-8").startswith(PROBE_BANNER)
                       for rel in written) if written else False)
        return report

    except Exception as exc:  # noqa: BLE001 - 报告需要把失败原因带回给调用方
        if report is None:
            report = HandshakeReport(ticket_id=ticket_id, out_dir="", step=step)
        report.error = f"{type(exc).__name__}: {exc}"
        return report


def request_preview(ticket_id: str, step: str) -> list[str]:
    """展示确定性幂等键的派生结果（供测试与说明使用）。"""
    return [
        make_request(ticket_id, "create"),
        make_request(ticket_id, f"step-{step}-start"),
        make_request(ticket_id, f"step-{step}-check", boundary="before_write", occurrence=1),
        make_request(ticket_id, f"step-{step}-finish"),
    ]
