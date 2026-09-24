"""命令行入口。

Phase 1（离线、零成本）：
    icode doctor            自检：能力与环境（不上网）
    icode handshake         契约握手：证明与控制面对齐
    icode steps             列出 gates.json 登记的步骤契约
    icode brief <step>      打印该步骤的门禁简报（渐进披露的强制层）
    icode outline <step>    打印该步骤文档的章节索引（渐进披露的懒加载入口）

Phase 2（真模型）：
    icode step-run --workspace <dir> --step plan --backend openai-compatible ...
    icode task --fixture pycalc --backend openai-compatible ...
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import ConfigError, load_settings, mask_secret, repo_root, resolve_api_key
from .contracts import ContractError, ContractSet, check_steps_alignment
from .control import ControlError, ControlPlane
from .disclosure import disclosure_report, load_guide, summarize
from .guard import Guard, Scope
from .handshake import run_handshake

REPO_ROOT = repo_root()


def _build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    _add_common_args(common)
    parser = argparse.ArgumentParser(
        prog="icode",
        description="ICODE 自主 Agent 运行时（过程可审计）",
    )
    parser.add_argument("--version", action="version", version=f"icode-agent {__version__}")
    parser.add_argument("--skill-root", help="icode-skill 源仓路径（默认自动探测）")
    sub = parser.add_subparsers(dest="command")

    def _add(name: str, **kw):
        """统一挂载公共参数，保证 --skill-root 位置无关。"""
        return sub.add_parser(name, parents=[common], **kw)

    p_doc = _add("doctor", help="自检环境与能力（离线）")
    p_doc.add_argument("--workspace", default=".", help="工作区根，用于权限模型自检")

    p_hs = _add("handshake", help="离线契约握手（不调用模型、不联网）")
    p_hs.add_argument("--workspace", required=True, help="握手工程根（工单将落在其 .icode_output/ 下）")
    p_hs.add_argument("--step", default="plan", help="要握手的步骤（默认 plan）")
    p_hs.add_argument("--ticket-id", default="HANDSHAKE-1")
    p_hs.add_argument("--requirement", default="离线契约握手：验证 Agent 与控制面的步骤/边界/产物契约对齐")

    _add("steps", help="列出 gates.json 登记的步骤契约")

    p_brief = _add("brief", help="打印步骤的门禁简报（强制注入层）")
    p_brief.add_argument("step")

    p_outline = _add("outline", help="打印步骤文档章节索引（懒加载入口）")
    p_outline.add_argument("step")

    # ---- Phase 2：真模型运行 ----

    p_step = _add("step-run", help="用真模型按契约执行一个步骤（plan 等）")
    p_step.add_argument("--workspace", required=True)
    p_step.add_argument("--step", default="plan")
    p_step.add_argument("--ticket-id", default="E2E-1")
    p_step.add_argument("--requirement", default="")
    _add_model_args(p_step)
    _add_loop_args(p_step, default_turns=16)

    p_task = _add("task", help="在隔离的靶场副本上做能力验证（真模型 + 独立跑测试）")
    p_task.add_argument("--fixture", default="pycalc", help="tests/fixtures 下的靶场名")
    p_task.add_argument("--workspace", help="指定工作区（默认自动建临时隔离副本）")
    p_task.add_argument("--task", default="", help="任务描述（默认新增 calc_gcd/calc_lcm）")
    _add_model_args(p_task)
    _add_loop_args(p_task)

    # ---- Phase 3：证据包 ----

    p_ev = _add("evidence", help="把工单导出为可独立校验的证据包")
    p_ev.add_argument("--ticket", required=True, help="v3 工单目录")
    p_ev.add_argument("--dest", required=True, help="证据包输出目录")
    p_ev.add_argument("--receipt-from", help="在该目录独立跑 python -m unittest 并把退出码写入回执")
    p_ev.add_argument("--receipt", action="append", default=[], help="额外回执 JSON 文件（可重复）")

    p_evv = _add("verify-pack", help="校验证据包（使用包内同一套逻辑）")
    p_evv.add_argument("pack")

    # ---- Phase 4：韧性 ----

    p_rec = _add("recover", help="分析被中断的工单该怎么继续（默认只分析，不执行业务动作）")
    p_rec.add_argument("--ticket", required=True, help="v3 工单目录")
    p_rec.add_argument("--step", default="plan")
    p_rec.add_argument("--resolve-attempt", help="人工核对真实状态后，为该 attempt 补 operation finish")
    p_rec.add_argument("--outcome", default="success", help="补 finish 时的结果")
    p_rec.add_argument("--evidence", default="", help="补 finish 的证据引用")
    p_rec.add_argument("--check", default="", help="补 finish 的核对说明")
    p_rec.add_argument("--resume", action="store_true",
                       help="判定可恢复后，立即用真模型继续执行该步骤")
    _add_model_args(p_rec)
    _add_loop_args(p_rec, default_turns=16)

    # ---- Phase 5：WebUI ----
    # 命名划线（D13 补充）：上游的 `/icode ui` 是**宿主的工单浏览器**，
    # 本命令是我们的**执行前端**。为免混淆，本仓用 `webui` 而不是 `ui`。

    # ---- Phase 6：完整链路 ----

    p_chain = _add("chain", help="串起完整链路 plan→review→merge→code→deepcheck→audit")
    p_chain.add_argument("--workspace", required=True)
    p_chain.add_argument("--requirement", required=True)
    p_chain.add_argument("--ticket-id", default="CHAIN-1")
    p_chain.add_argument("--only", default="", help="只跑指定步骤（逗号分隔），默认全部")
    p_chain.add_argument("--delivery-verdict", default="verification_pending",
                         choices=["verified", "verification_pending", "blocked", "not_applicable"],
                         help="completed 状态的交付结论；默认取最保守值，不自动升级为 verified")
    _add_model_args(p_chain)
    _add_loop_args(p_chain, default_turns=20)

    p_ui = _add("webui", help="启动本地审批台（仅监听 127.0.0.1）")
    p_ui.add_argument("--port", type=int, default=0, help="0 = 由系统分配空闲端口")
    p_ui.add_argument("--no-browser", action="store_true")
    p_ui.add_argument("--approval-timeout", type=float, default=300.0,
                      help="等待人工确认的秒数；超时按拒绝处理")
    p_ui.add_argument("--demo", action="store_true",
                      help="放入一条示例待确认项，便于空跑体验（不执行任何真实动作）")

    p_workbench = _add("workbench", help="启动单工程研发工单工作台（仅监听 127.0.0.1）")
    p_workbench.add_argument("--workspace", required=True, help="服务端可信工程根")
    p_workbench.add_argument("--port", type=int, default=0, help="0 = 由系统分配空闲端口")
    p_workbench.add_argument("--no-browser", action="store_true")
    p_workbench.add_argument(
        "--enable-autonomous",
        action="store_true",
        help="显式启用自主执行（默认关闭）",
    )
    _add_model_args(p_workbench)
    _add_loop_args(p_workbench, default_turns=20)

    return parser


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    """子命令级公共参数。

    用独立 dest 承接，避免覆盖全局同名参数的解析结果（两者都写时以子命令为准）。
    """
    parser.add_argument("--skill-root", dest="skill_root_sub", default=None,
                        help="icode-skill 源仓路径（也可写在子命令之前）")


def _add_model_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--backend", default="fake", choices=["fake", "openai-compatible"])
    parser.add_argument("--model", default="", help="模型名（默认 MiniMax-M3）")
    parser.add_argument("--base-url", default="", help="OpenAI 兼容端点")
    parser.add_argument("--key-file", default="", help="仓外密钥文件路径（绝不入库）")
    parser.add_argument("--no-proxy", action="store_true",
                        help="强制直连，忽略 HTTP(S)_PROXY（托管环境的隧道代理常导致 502）")
    parser.add_argument("--proxy", default="", help="只走指定代理")


def _add_loop_args(parser: argparse.ArgumentParser, *, default_turns: int = 12) -> None:
    parser.add_argument("--max-turns", type=int, default=default_turns)
    parser.add_argument("--budget-tokens", type=int, default=0, help="0=只观测不设闸门")
    parser.add_argument("--approve", action="store_true",
                        help="交互式审批（默认拒绝一切需人工确认的动作）")
    parser.add_argument("--quiet", action="store_true", help="不打印回合过程")
    parser.add_argument("--isolation", default="auto",
                        help="隔离后端：auto（默认，按实测能力选择）/ none / bwrap / docker / podman")


def _load(args: argparse.Namespace) -> tuple[object, ContractSet]:
    settings = load_settings(args.skill_root)
    return settings, ContractSet.load(settings.gates_json)


def cmd_doctor(args: argparse.Namespace) -> int:
    print("ICODE Agent 自检（离线）")
    try:
        settings = load_settings(args.skill_root)
    except ConfigError as exc:
        print(f"  [FAIL] icode-skill 源仓：{exc}")
        return 1
    print(f"  [OK  ] icode-skill 源仓：{settings.skill_root}")

    if not settings.exists():
        print("  [FAIL] 契约文件或控制面脚本缺失")
        return 1
    contracts = ContractSet.load(settings.gates_json)
    print(f"  [OK  ] gates.json：schema_version={contracts.schema_version}，"
          f"{len(contracts.steps())} 个已登记步骤")
    print(f"         复检边界：{', '.join(contracts.boundaries())}")
    print(f"         操作类别：{', '.join(contracts.operation_classes())}")
    print(f"         失败分类：{', '.join(contracts.failure_policies())}")

    issues = check_steps_alignment(contracts, settings.steps_dir)
    if issues:
        print(f"  [WARN] 契约与 steps/ 文档存在 {len(issues)} 处不一致：")
        for it in issues[:8]:
            print(f"         - {it}")
    else:
        print("  [OK  ] 契约与 steps/ 文档一致")

    stats = disclosure_report(settings.steps_dir, contracts.steps())
    print(f"  [OK  ] 渐进披露：{summarize(stats)}")

    cp = ControlPlane(settings, check=False)
    probe = cp.run("--help")
    print(f"  [{'OK  ' if probe.returncode == 0 else 'FAIL'}] 控制面可执行："
          f"{settings.control_script.name}")

    guard = Guard(Scope(workspace_root=Path(args.workspace).resolve()))
    g = guard.summary()
    print(f"  [OK  ] 权限模型：应用层限制（is_sandbox={g['is_sandbox']}）"
          f" 工作区={g['workspace_root']}")

    # 隔离能力：只报实测结果，措辞不得超出实际能力
    from .isolation import capability_report

    report = capability_report()
    selected = report["selected"]
    avail = [p for p in report["probes"] if p["available"]]
    print(f"  [{'OK  ' if selected['is_real_isolation'] else 'WARN'}] 隔离后端：{report['honest_label']}")
    print(f"         后端={selected['backend']}"
          + (f"；已强制={selected.get('enforced')}" if selected.get("enforced") else ""))
    print(f"  [INFO] R2 策略合同：v{report['policy_schema_version']}")
    print("         一致性测试：尚未执行（下一阶段原生后端自测后才会产生结果）")
    if sys.platform.startswith("linux"):
        bundled = report["bundled_linux_helper"]
        state = "最小负向探测通过" if bundled["minimal_probe_passed"] else bundled["detail"]
        print(f"  [INFO] 随包 Linux 助手：{state}")
    print("  [WARN] 策略级隔离未就绪：自动模式仍拒绝外部命令")
    if not selected.get("is_real_isolation"):
        print("         ⚠ 无内核/容器级隔离：模型若绕过运行时直接执行 shell，应用层规则不构成保障")
        print("           Linux 随包助手正在完整策略验收；无需为自动模式额外安装 bubblewrap")
    if avail:
        names = "、".join(p["name"] for p in avail)
        print(f"         探测到可执行文件：{names}")
        print("         注意：可执行文件存在 ≠ 可用（受限环境会按安全策略拦截）。"
              "WSL 需显式 --isolation wsl 指定后才实测。")
    else:
        print("         未探测到任何后端可执行文件（bwrap / sandbox-exec / wsl / docker / podman）")

    try:
        key = resolve_api_key()
        print(f"  [OK  ] 模型密钥可解析：{mask_secret(key)}（Phase 2 真模型后端使用）")
    except ConfigError:
        print("  [SKIP] 模型密钥未配置（离线流程不需要）")

    from .config import llm_no_proxy, llm_proxy

    if llm_no_proxy():
        proxy_desc = "强制直连（ICODE_LLM_NO_PROXY）"
    elif llm_proxy():
        proxy_desc = f"显式代理 {llm_proxy()}"
    else:
        import urllib.request

        env = urllib.request.getproxies()
        proxy_desc = (env.get("https") or env.get("http") or "无") + "（跟随环境）"
    print(f"  [INFO] 模型端点代理：{proxy_desc}")
    print("         若经代理出现 502/407，用 --no-proxy 或 ICODE_LLM_NO_PROXY=1 绕过")

    print("\n结果：自检完成")
    return 0


def cmd_handshake(args: argparse.Namespace) -> int:
    settings = load_settings(args.skill_root)
    report = run_handshake(
        settings,
        workspace=Path(args.workspace),
        step=args.step,
        ticket_id=args.ticket_id,
        requirement=args.requirement,
    )
    print(report.render())
    return 0 if report.ok else 1


def cmd_steps(args: argparse.Namespace) -> int:
    _, contracts = _load(args)
    for name in contracts.steps():
        c = contracts.step(name)
        ins = ", ".join(p.value or p.id for p in c.required_inputs) or "-"
        outs = ", ".join(p.value or p.id for p in c.required_outputs) or "-"
        checks = ", ".join(c.required_checks) or "-"
        print(f"{name:<10} 输入={ins:<28} 产物={outs:<28} 复检={checks}")
    return 0


def cmd_brief(args: argparse.Namespace) -> int:
    settings, contracts = _load(args)
    if not contracts.has(args.step):
        print(f"未知步骤：{args.step}；已登记：{', '.join(contracts.steps())}", file=sys.stderr)
        return 2
    guide = load_guide(settings.steps_dir, args.step)
    contract = contracts.step(args.step)
    if guide is None:
        print(f"steps/ 无 {args.step} 文档，仅输出机器契约：\n")
        print(contract)
        return 0
    brief, truncated = guide.mandatory_brief(contract)
    print(brief)
    if truncated:
        print("\n（注：门禁简报已按预算截断）", file=sys.stderr)
    return 0


def cmd_outline(args: argparse.Namespace) -> int:
    settings, contracts = _load(args)
    guide = load_guide(settings.steps_dir, args.step)
    if guide is None:
        print(f"steps/ 无 {args.step} 文档", file=sys.stderr)
        return 2
    contract = contracts.step(args.step) if contracts.has(args.step) else None
    st = guide.stats(contract)
    print(f"{guide.path}")
    print(f"全文 {st.total_chars:,} 字符 / {st.section_count} 个章节；"
          f"强制层 {st.mandatory_chars:,} 字符（{st.ratio:.1%}）\n")
    for s in guide.outline():
        flag = "*" if any(k in s.title for k in ("门禁", "强制", "必须", "禁止", "不得", "前置", "校验")) else " "
        print(f" {flag} L{s.start:<5} {s.title}  ({s.chars:,} 字符)")
    print("\n（* 标记的章节进入强制层；其余按需加载）")
    return 0


def _build_runner(args: argparse.Namespace):
    """构造 backend / approver / 预算 / 事件钩子。"""
    from .approvals import CliApprover, DenyAllApprover
    from .backends import build_backend
    from .budget import Budget

    backend = build_backend(
        args.backend,
        key_file=args.key_file or None,
        model=args.model or None,
        base_url=args.base_url or None,
        proxy=args.proxy or None,
        no_proxy=args.no_proxy,
    )
    approver = CliApprover() if args.approve else DenyAllApprover()
    budget = Budget(expected_tokens=args.budget_tokens)
    if hasattr(backend, "active_proxy"):
        print(f"  代理：{backend.active_proxy()}")  # type: ignore[attr-defined]

    def on_event(kind: str, payload: dict) -> None:
        if args.quiet:
            return
        if kind == "assistant":
            calls = payload.get("tool_calls") or []
            text = (payload.get("content") or "").strip().replace("\n", " ")[:120]
            print(f"  [回合 {payload.get('index')}] {text}"
                  + (f"  → 工具 {calls}" if calls else ""))
        elif kind == "tool_start":
            print(f"      · 调用 {payload.get('tool')}")
        elif kind == "tool_result":
            print(f"        {'成功' if payload.get('ok') else '失败'}")
        elif kind == "tool_denied":
            print(f"        [拒绝] {payload.get('reason')}")
        elif kind == "approval_requested":
            print(f"        [待确认] {payload.get('reason')}")
        elif kind == "operation_ambiguous":
            print(f"        [副作用歧义] {payload.get('detail')}")

    from .isolation import select_sandbox

    sandbox = select_sandbox(None if args.isolation == "auto" else args.isolation)
    if hasattr(sandbox, "describe"):
        claim = sandbox.describe().get("claim", "")
        print(f"  隔离：{claim}")
    return backend, approver, budget, on_event, sandbox


def cmd_step_run(args: argparse.Namespace) -> int:
    from .loop import LoopConfig
    from .runner import run_contract_step

    settings = load_settings(args.skill_root)
    backend, approver, budget, on_event, sandbox = _build_runner(args)
    print(f"契约步骤执行：{args.step}（backend={getattr(backend, 'name', '?')}）")
    report = run_contract_step(
        settings, backend=backend, workspace=Path(args.workspace), step=args.step,
        ticket_id=args.ticket_id, requirement=args.requirement,
        approver=approver, loop_config=LoopConfig(max_turns=args.max_turns),
        budget=budget, on_event=on_event, sandbox=sandbox,
    )
    print(report.render())
    return 0 if report.ok else 1


def cmd_task(args: argparse.Namespace) -> int:
    import tempfile

    from .loop import LoopConfig
    from .runner import DEFAULT_TASK, prepare_workspace, run_task

    settings = load_settings(args.skill_root)
    backend, approver, budget, on_event, sandbox = _build_runner(args)

    if args.workspace:
        workspace = Path(args.workspace)
    else:
        tmp = Path(tempfile.mkdtemp(prefix="icode_task_"))
        workspace = prepare_workspace(args.fixture, tmp / args.fixture, repo_root=REPO_ROOT)
        print(f"隔离工作区：{workspace}（靶场副本，与仓库基线隔离）")

    print(f"能力验证（backend={getattr(backend, 'name', '?')}，独立跑测试取退出码）")
    report = run_task(
        settings, backend=backend, workspace=workspace,
        task=args.task or DEFAULT_TASK, approver=approver,
        loop_config=LoopConfig(max_turns=args.max_turns), budget=budget, on_event=on_event,
        sandbox=sandbox,
    )
    print(report.render())
    print("成本：" + _budget_line(backend))
    return 0 if report.ok else 1


def _budget_line(backend) -> str:
    usage = getattr(backend, "usage", None)
    if usage is None:
        return "n/a"
    return (f"{usage.calls} 次调用 / {usage.total_tokens:,} tokens"
            f"（prompt {usage.prompt_tokens:,} / completion {usage.completion_tokens:,}"
            f" / cached {usage.cached_tokens:,}）")


def cmd_evidence(args: argparse.Namespace) -> int:
    import json as _json

    from .evidence import build_evidence_pack, collect_verifications
    from .runner import run_unittest

    settings = load_settings(args.skill_root)

    receipts: list[dict] = []
    for path in args.receipt:
        p = Path(path)
        if not p.is_file():
            print(f"回执文件不存在：{p}", file=sys.stderr)
            return 2
        data = _json.loads(p.read_text(encoding="utf-8"))
        receipts.extend(data if isinstance(data, list) else [data])

    if args.receipt_from:
        workdir = Path(args.receipt_from).resolve()
        code, output = run_unittest(workdir)
        receipts.append(collect_verifications(code, [sys.executable, "-m", "unittest"], output))
        print(f"  外部验证回执：python -m unittest @ {workdir} → 退出码 {code}")

    report = build_evidence_pack(
        args.ticket, dest=args.dest, gates_json=settings.gates_json, verifications=receipts,
    )
    print(report.render())
    if report.ok:
        print("\n独立校验（不依赖本工具）：")
        print(f"  python {Path(report.pack_dir) / 'verify.py'} {report.pack_dir}")
    return 0 if report.ok else 1


def cmd_verify_pack(args: argparse.Namespace) -> int:
    from .pack_verify import verify_pack

    pack = Path(args.pack)
    problems = verify_pack(pack)
    if problems:
        print(f"证据包校验失败：{pack}")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"证据包校验通过：{pack}")
    print("  已核验：清单完整性 · 事件链哈希链 · 正文与链上哈希对应 · 包摘要")
    return 0


def cmd_recover(args: argparse.Namespace) -> int:
    import json as _json

    from .checkpoint import Checkpointer
    from .recovery import Recoverer

    settings = load_settings(args.skill_root)
    out_dir = Path(args.ticket).resolve()
    meta_path = out_dir / ".ico_metadata.json"
    if not meta_path.is_file():
        print(f"不是 v3 工单目录（缺 .ico_metadata.json）：{out_dir}", file=sys.stderr)
        return 2
    ticket_id = str(_json.loads(meta_path.read_text(encoding="utf-8")).get("ticket_id") or "")

    cp = ControlPlane(settings)
    ck = Checkpointer(out_dir, ticket_id=ticket_id, step=args.step, attempt="")
    recoverer = Recoverer(cp, out_dir, ticket_id)

    if args.resolve_attempt:
        ok = recoverer.resolve_open_operation(
            args.resolve_attempt, outcome=args.outcome,
            evidence=args.evidence or "manual-verify", check_ref=args.check or "人工核对",
        )
        print(f"  补 finish：{'成功' if ok else '失败'}（attempt={args.resolve_attempt}）")
        print()

    decision = recoverer.analyze(args.step, checkpointer=ck)
    print(decision.render())
    print()
    print(decision.resume_brief())

    if not args.resume:
        if decision.needs_human:
            print("\n（存在需人工处理项：未自动继续。核对后可用 --resolve-attempt 补回执，再 --resume）")
        return 0 if not decision.needs_human else 1

    if decision.needs_human:
        print("\n拒绝自动恢复：请先人工核对真实状态。", file=sys.stderr)
        return 1

    from .loop import LoopConfig
    from .runner import resume_contract_step

    backend, approver, budget, on_event, sandbox = _build_runner(args)
    print(f"\n恢复执行（backend={getattr(backend, 'name', '?')}）")
    report = resume_contract_step(
        settings, backend=backend, out_dir=out_dir, step=args.step, ticket_id=ticket_id,
        approver=approver, loop_config=LoopConfig(max_turns=args.max_turns),
        budget=budget, on_event=on_event, sandbox=sandbox,
    )
    print(report.render())
    return 0 if report.ok else 1


def cmd_webui(args: argparse.Namespace) -> int:
    """启动本地审批台。

    注意本命令**只负责"审批"这一层**：它不写工单状态、不接受路径或命令。
    """
    import threading

    from .approvals import ApprovalRequest
    from .webui import serve

    server, approver = serve(
        port=args.port, open_browser=not args.no_browser, timeout=args.approval_timeout
    )
    print(f"  服务地址：{server.url}")
    print("  按 Ctrl+C 结束（结束即作废所有挂起项）")

    if args.demo:
        sample = ApprovalRequest(
            tool="run_command",
            arguments={"argv": ["some-unknown-binary", "--go"]},
            reason="不在白名单：some-unknown-binary",
            opclass="managed_write",
            workspace=str(Path.cwd()),
        )

        def _ask() -> None:
            granted = approver.ask(sample)
            print(f"\n  示例审批结果：{'已放行' if granted else '已拒绝/超时'}")

        threading.Thread(target=_ask, daemon=True).start()

    try:
        while True:
            threading.Event().wait(1.0)
    except KeyboardInterrupt:
        print("\n  正在关闭 WebUI…")
        server.stop()
    return 0


def cmd_workbench(args: argparse.Namespace) -> int:
    """启动单工程工单工作台；工程路径只在服务端配置。"""
    import threading
    import webbrowser

    from .workbench import WorkbenchServer

    settings = load_settings(args.skill_root)
    executor = None
    isolation_level = "not_configured"
    if args.enable_autonomous:
        if args.max_turns <= 0:
            raise ConfigError("--max-turns 必须大于 0")
        if args.budget_tokens < 0:
            raise ConfigError("--budget-tokens 不能小于 0")
        from .autonomy import NativeChainExecutor
        from .loop import LoopConfig

        backend, approver, budget, on_event, sandbox = _build_runner(args)
        executor = NativeChainExecutor(
            settings,
            backend=backend,
            approver=approver,
            loop_config=LoopConfig(max_turns=args.max_turns),
            budget=budget,
            on_event=on_event,
            sandbox=sandbox,
        )
        isolation_level = (
            "enforced" if sandbox.is_real_isolation
            and callable(getattr(sandbox, "wrap_policy", None))
            else "policy_unavailable"
        )
    server = WorkbenchServer(
        settings=settings,
        workspace=Path(args.workspace),
        port=args.port,
        enable_autonomous=args.enable_autonomous,
        autonomy_executor=executor,
        autonomy_limits={
            "max_turns": args.max_turns,
            "budget_tokens": args.budget_tokens,
            "isolation_level": isolation_level,
        },
    )
    url = server.start()
    print(f"  工作台：{url}")
    print(f"  工程：{Path(args.workspace).expanduser().resolve()}")
    print(f"  自主执行：{'已启用' if args.enable_autonomous else '未启用'}")
    print("  按 Ctrl+C 结束")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        while True:
            threading.Event().wait(1.0)
    except KeyboardInterrupt:
        print("\n  正在关闭工作台…")
        server.stop()
    return 0


def cmd_chain(args: argparse.Namespace) -> int:
    from .chain import run_chain
    from .loop import LoopConfig

    settings = load_settings(args.skill_root)
    backend, approver, budget, on_event, sandbox = _build_runner(args)
    steps = tuple(x.strip() for x in args.only.split(",") if x.strip()) or None
    if steps:
        print(f"仅执行指定步骤：{steps}")
    print()
    report = run_chain(
        settings, backend=backend, workspace=Path(args.workspace),
        requirement=args.requirement, ticket_id=args.ticket_id, steps=steps,
        approver=approver, loop_config=LoopConfig(max_turns=args.max_turns),
        budget=budget, on_event=on_event, sandbox=sandbox,
        on_step=lambda name, sr: print(f"\n===== 步骤 {name} 完成："
                                       f"{'OK' if sr.ok else 'FAIL'} =====\n{sr.render()}\n"),
    )
    print(report.render())
    print("成本：" + _budget_line(backend))
    return 0 if report.ok else 1


_COMMANDS = {
    "doctor": cmd_doctor,
    "chain": cmd_chain,
    "handshake": cmd_handshake,
    "steps": cmd_steps,
    "brief": cmd_brief,
    "outline": cmd_outline,
    "step-run": cmd_step_run,
    "task": cmd_task,
    "evidence": cmd_evidence,
    "verify-pack": cmd_verify_pack,
    "recover": cmd_recover,
    "webui": cmd_webui,
    "workbench": cmd_workbench,
}


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    # 子命令级 --skill-root 优先（让位置无关）
    if getattr(args, "skill_root_sub", None):
        args.skill_root = args.skill_root_sub
    if not args.command:
        parser.print_help()
        return 0
    handler = _COMMANDS[args.command]
    try:
        return handler(args)
    except (ConfigError, ContractError, ControlError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    except NotADirectoryError as exc:
        # 跨平台常见坑：把 Git Bash 的 /c/xxx 传给 Windows Python
        print(f"路径无效（不是目录）：{exc}\n"
              "  提示：Windows 上请使用 `C:/...` 形式的路径，"
              "Git Bash 的 `/c/...` 形式 Windows Python 无法识别。", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"文件系统错误：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - 后端/网络错误要给可读提示而非堆栈
        from .backends import BackendError

        if isinstance(exc, BackendError):
            print(f"模型调用错误：{exc}", file=sys.stderr)
            return 3
        raise


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
