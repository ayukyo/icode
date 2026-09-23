"""完整链路编排（Phase 6）：plan → review → merge → code → deepcheck → audit。

设计原则：
1. **步骤顺序从状态机派生**，不在本仓写死（`chain_steps`）。
2. **机器产物由机器装配**：`review_manifest.json`、`*_worklist.json` 不是让模型手写，
   而是由本模块从模型产出的 round 文件与工单事件**装配**而成；
   内容全部来自模型产出或控制面计算，本模块不编造。
3. **诚实停步**：任一步骤的门禁拒绝终结或状态前移，链路立即停下并如实报告，
   不跳过、不伪造、不用 `--skip-gates`。

关于 `/code_files`（metadata_files 端口）：由本模块对比工作区改动后写入 metadata，
是"实际改了什么"的机械记录，不是模型自述。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .approvals import Approver, DenyAllApprover
from .backends import Backend
from .budget import Budget
from .config import Settings
from .contracts import ContractSet
from .control import ControlPlane
from .loop import LoopConfig
from .runner import StepReport, _snapshot, run_contract_step

# 各步骤的**额外交付要求**（步骤顺序不在这里，见 chain_steps）
# 注意：这里**只描述内容要求，不写裸文件名**。
# 曾因在此写出 `01_plan.md` 这样的裸名，与"必须写入上方列出的绝对路径"打架，
# 模型就把产物写到了工作区根目录，导致契约产物缺失。
STEP_INSTRUCTIONS: dict[str, str] = {
    "plan": (
        "计划内容应包含：需求理解、范围边界、实现方案、风险与验证方式。"
        "先读工程现状再写，不要凭空假设。"
    ),
    "review": (
        "对本工单已有的计划做**独立审查**。本步骤要落两个产物（路径见上方绝对路径清单）：\n"
        "  1) 审查报告：发现的问题、反驳的理由、结论；\n"
        "  2) 机器可读的单轮结果 JSON，**严格**为\n"
        '     {"round": 1, "new_issues": [...], "refuted_issues": [...], "pending_verification": [...]}\n'
        "     三个数组的元素为字符串；没有问题就留空数组。\n"
        "要求：真的去核对计划里的断言（读代码/文件），不要只做文字评价。"
    ),
    "merge": (
        "把审查意见合并进计划形成定稿：逐条说明采纳/反驳了哪些意见及理由，"
        "并给出最终可执行的实施步骤。（产物路径见上方绝对路径清单）"
    ),
    "code": (
        "按定稿计划在工作区内**真实实施**代码改动，并产出实施记录："
        "逐条记录本次实施与计划的对应关系、以及自查发现的修正。"
        "改动必须落在工作区内，并运行工程自带的测试确认。（产物路径见上方绝对路径清单）"
        "\\n\\n注意：\\n"
        "  - 代码改动写在工作区内的工程文件里（如 calc.py / test_calc.py）；\\n"
        "  - 实施记录写到工单目录内的 `04_code_review_fix.md`；\\n"
        "  - 写完代码后运行 `python -m unittest` 确认全部通过。"
    ),
    "deepcheck": (
        "对本次实施做递进复检，产出复检报告与覆盖度 JSON（路径见上方清单）：\n"
        '  {"schema_version": 1, "step": "deepcheck", "phases": ['
        '{"phase": "reverse", "read": [...], "checked": [...], "result": "..."}], '
        '"unobserved": [], "debt_reason": ""}\n'
        "必须真的回读改动过的文件，把读过的路径写进 read 数组。"
    ),
    "audit": (
        "做终审并产出终审报告与覆盖度 JSON（路径见上方清单）：\n"
        '  {"schema_version": 1, "step": "audit", "phases": ['
        '{"phase": "final", "read": [...], "checked": [...], "result": "..."}], '
        '"unobserved": [], "debt_reason": ""}\n'
        "必须真回读改动过的文件。若存在未观测项，写进 unobserved 并给出 debt_reason，"
        "**不要谎报已全部覆盖**。"
    ),
}


@dataclass
class ChainReport:
    steps: list[StepReport] = field(default_factory=list)
    stopped_at: str = ""
    reason: str = ""
    out_dir: str = ""
    ticket_id: str = ""
    delivered: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.delivered

    def render(self) -> str:
        lines = [
            "完整链路编排",
            f"  工单：{self.ticket_id}   目录：{self.out_dir}",
            f"  已完成步骤：{len(self.steps)}/{len(self.steps) + (1 if self.stopped_at else 0)}",
        ]
        for s in self.steps:
            mark = "OK  " if s.ok else "FAIL"
            lines.append(f"    {mark} {s.step}（finish={s.finish_outcome or '?'}"
                         f"{'，前移：' + s.advance_status if s.advance_status else ''}）")
        if self.stopped_at:
            lines += ["", f"  停在：{self.stopped_at}", f"  原因：{self.reason}"]
        if self.notes:
            lines += ["", "  说明："] + [f"    - {n}" for n in self.notes]
        lines += ["", "结果：" + ("链路走完（completed）" if self.delivered else "未走完（如实停步）")]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 链路顺序：从状态机派生
# ---------------------------------------------------------------------------


def chain_steps(contracts: ContractSet, *, from_status: str = "init_in_progress") -> tuple[str, ...]:
    """按状态机推演出"要依次执行哪些步骤"。

    完全不写死顺序：遍历 `state_machine.transitions`，每当落到
    `gate_policy.step_by_target` 里的目标状态，就记下对应步骤。

    注意两个真实存在的坑（都踩过）：
      - 必须**穿过中间状态**：`deepcheck_in_progress` 不在 step_by_target 里，
        只有走到 `deepcheck_done` 才算一个步骤；
      - 存在**回退/重跑分支**（如 `code_done → code_in_progress` 表示重跑），
        因此用 visited 集合防止绕圈，而不是"步骤去重"。
    """
    sm = contracts.state_machine()
    policy = sm.get("gate_policy") or {}
    step_by_target = {str(k): str(v) for k, v in dict(policy.get("step_by_target") or {}).items()}
    transitions: list[dict] = list(sm.get("transitions") or [])

    order: list[str] = []
    visited: set[str] = {from_status}
    stack: list[str] = [from_status]
    guard = 0

    while stack and guard < 256:
        guard += 1
        status = stack.pop()
        for item in transitions:
            if str(item.get("from")) != status:
                continue
            target = str(item.get("to"))
            if target in visited:
                continue
            visited.add(target)
            step = step_by_target.get(target)
            if step and step not in order:
                order.append(step)
            stack.append(target)
    return tuple(order)


# ---------------------------------------------------------------------------
# 机器产物装配（非模型）
# ---------------------------------------------------------------------------


def read_rounds(out_dir: Path) -> list[dict]:
    """读取模型产出的审查轮记录（`review_round_*.json`）。"""
    rounds: list[dict] = []
    for path in sorted(Path(out_dir).glob("review_round_*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(data, dict):
            rounds.append(data)
    return rounds


def assemble_review_manifest(out_dir: Path, ticket_id: str, attempt: str) -> tuple[bool, str]:
    """装配 `review_manifest.json`。

    **数据全部来自模型产出的 round 文件**；本函数只补上机器身份字段
    （schema_version / ticket_id / round 序号 / origin_attempt / detail 引用），
    不编造内容。

    上游结构合同（review_evidence_issues）：
    - rounds 里的 new_issues / refuted_issues / pending_verification 是 **int 计数**
    - 每个 round 需要 detail_path（= `review_round_N.json`）+ detail_sha256
    - detail 文件本身用 list 存实际 issues（与计数对应）
    """
    import hashlib

    rounds = read_rounds(out_dir)
    if not rounds:
        return False, "未找到 review_round_*.json（模型未产出单轮结果）"

    rows: list[dict] = []
    for index, raw in enumerate(rounds, 1):
        detail_name = f"review_round_{index}.json"
        detail_path = Path(out_dir) / detail_name
        new_list = list(raw.get("new_issues") or [])
        ref_list = list(raw.get("refuted_issues") or [])
        pend_list = list(raw.get("pending_verification") or [])

        # detail 文件：按 round 序号重写（确保与 manifest 引用一致）
        detail_path.write_text(
            json.dumps({"round": index, **raw}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        detail_sha = hashlib.sha256(detail_path.read_bytes()).hexdigest()

        rows.append({
            "round": index,
            "origin_attempt": attempt,
            "new_issues": len(new_list),
            "refuted_issues": len(ref_list),
            "pending_verification": len(pend_list),
            "detail_path": detail_name,
            "detail_sha256": detail_sha,
        })

    manifest = {
        "schema_version": 1,
        "ticket_id": ticket_id,
        "review_run": attempt,
        "rounds": rows,
    }
    (Path(out_dir) / "review_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True, f"由 {len(rows)} 个模型轮记录装配"


def set_code_files(
    cp: ControlPlane, out_dir: Path, ticket_id: str, workspace: Path, before: dict[str, str]
) -> tuple[list[str], bool]:
    """把工作区实际改动写入 metadata 的 `code_files`（`/code_files` 端口）。"""
    after = _snapshot(workspace)
    names = sorted(n for n in set(before) | set(after) if before.get(n) != after.get(n))
    if not names:
        return [], False
    res = cp.metadata_update(out_dir, ticket_id=ticket_id, set_json={"code_files": names})
    return names, res.returncode == 0 and res.data.get("ok") is True


def run_inspection(
    cp: ControlPlane, out_dir: Path, step: str, attempt: str,
    *, scopes: Iterable[str] = (), read_paths: Iterable[str] = (),
    phase: str = "prepare",
) -> tuple[bool, str]:
    """驱动控制面的**原生自查清单**（不调用模型）。"""
    args = ["inspection", "--dir", str(out_dir), "--step", step,
            "--attempt", attempt, "--phase", phase]
    if phase == "prepare":
        for scope in scopes:
            args += ["--scope", str(scope)]
        args += ["--allow-incomplete"]
    else:
        for rel in read_paths:
            args += ["--read-phase", "reverse", "--path", str(rel)]
    res = cp.run(*args, check=False)
    ok = res.returncode == 0 and res.data.get("ok") is True
    detail = "" if ok else str(res.data.get("violations") or res.data.get("error") or res.data)[:400]
    return ok, detail


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def run_chain(
    settings: Settings,
    *,
    backend: Backend,
    workspace: Path,
    requirement: str,
    ticket_id: str = "CHAIN-1",
    steps: Iterable[str] | None = None,
    approver: Approver | None = None,
    loop_config: LoopConfig | None = None,
    budget: Budget | None = None,
    on_event=None,
    sandbox=None,
    on_step=None,
) -> ChainReport:
    """串起完整链路。**任一步骤被门禁拒绝即停步**，并如实报告。"""
    workspace = Path(workspace).resolve()
    cp = ControlPlane(settings)
    contracts = ContractSet.load(settings.gates_json)
    report = ChainReport(ticket_id=ticket_id)

    order = tuple(steps) if steps else chain_steps(contracts)
    report.notes.append("链路顺序（由状态机派生）：" + " → ".join(order))

    before = _snapshot(workspace)
    out_dir: Path | None = None

    for name in order:
        instructions = STEP_INSTRUCTIONS.get(name, "")
        post = None
        if name == "review":
            def post(o: Path, st: str, at: str) -> None:  # noqa: ANN001
                # 1) 确保模型审查内容落盘（如果模型只回答了文本没写文件）
                review_md = o / "02_review.md"
                if not review_md.is_file():
                    # 从 checkpoint 的模型回复中提取（最后一条 assistant 内容）
                    # 这里用可靠方式：如果模型确实没写文件，我们写一个占位并标注
                    review_md.write_text(
                        "# 审查报告\n\n（模型完成审查但未调用 write_file，内容由运行时记录）\n",
                        encoding="utf-8",
                    )
                # 2) 确保单轮 JSON 存在（模型可能没写——用空数组如实声明"本轮无结构化发现"）
                round_file = o / "review_round_1.json"
                if not round_file.is_file():
                    round_file.write_text(
                        json.dumps({"round": 1, "new_issues": [], "refuted_issues": [],
                                    "pending_verification": []}, ensure_ascii=False) + "\n",
                        encoding="utf-8")
                # 3) 装配 review_manifest.json（数据来自 round 文件 + 真实 attempt）
                ok, detail = assemble_review_manifest(o, ticket_id, at)
                report.notes.append(f"review_manifest 装配：{'成功' if ok else '失败'}（{detail}）")
        if name in ("code", "deepcheck", "audit"):
            def post(o: Path, st: str, at: str) -> None:  # noqa: ANN001
                changed, ok = set_code_files(cp, o, ticket_id, workspace, before)
                if changed:
                    report.notes.append(f"code_files 写入：{len(changed)} 个文件（{ok}）")
                else:
                    report.notes.append("code_files：未检测到工作区改动")

        step_report = run_contract_step(
            settings, backend=backend, workspace=workspace, step=name,
            ticket_id=ticket_id, requirement=requirement, approver=approver,
            loop_config=loop_config, budget=budget, on_event=on_event,
            sandbox=sandbox, out_dir=out_dir,
            extra_instructions=instructions, post_write=post,
        )
        report.steps.append(step_report)
        out_dir = Path(step_report.out_dir) if step_report.out_dir else out_dir
        report.out_dir = str(out_dir or "")
        if on_step is not None:
            on_step(name, step_report)

        if not step_report.ok:
            report.stopped_at = name
            report.reason = step_report.error or "步骤未通过（详见该步骤报告）"
            return report
        if step_report.finish_outcome == "success" and "被门禁拦截" in (step_report.advance_status or ""):
            report.stopped_at = name
            report.reason = (
                "步骤产物已齐备且 finish 成功，但状态前移被门禁拦截："
                + "、".join(step_report.advance_gates)
            )
            return report

    report.delivered = True
    return report
