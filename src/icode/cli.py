"""命令行入口。

Phase 1 命令（全部离线、零成本）：
    icode doctor            自检：能力与环境（不上网）
    icode handshake         契约握手：证明与控制面对齐
    icode steps             列出 gates.json 登记的步骤契约
    icode brief <step>      打印该步骤的门禁简报（渐进披露的强制层）
    icode outline <step>    打印该步骤文档的章节索引（渐进披露的懒加载入口）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import ConfigError, load_settings, mask_secret, resolve_api_key
from .contracts import ContractError, ContractSet, check_steps_alignment
from .control import ControlError, ControlPlane
from .disclosure import disclosure_report, load_guide, summarize
from .guard import Guard, Scope
from .handshake import run_handshake


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="icode",
        description="ICODE 自主 Agent 运行时（过程可审计）",
    )
    parser.add_argument("--version", action="version", version=f"icode-agent {__version__}")
    parser.add_argument("--skill-root", help="icode-skill 源仓路径（默认自动探测）")
    sub = parser.add_subparsers(dest="command")

    p_doc = sub.add_parser("doctor", help="自检环境与能力（离线）")
    p_doc.add_argument("--workspace", default=".", help="工作区根，用于权限模型自检")

    p_hs = sub.add_parser("handshake", help="离线契约握手（不调用模型、不联网）")
    p_hs.add_argument("--workspace", required=True, help="握手工程根（工单将落在其 .icode_output/ 下）")
    p_hs.add_argument("--step", default="plan", help="要握手的步骤（默认 plan）")
    p_hs.add_argument("--ticket-id", default="HANDSHAKE-1")
    p_hs.add_argument("--requirement", default="离线契约握手：验证 Agent 与控制面的步骤/边界/产物契约对齐")

    sub.add_parser("steps", help="列出 gates.json 登记的步骤契约")

    p_brief = sub.add_parser("brief", help="打印步骤的门禁简报（强制注入层）")
    p_brief.add_argument("step")

    p_outline = sub.add_parser("outline", help="打印步骤文档章节索引（懒加载入口）")
    p_outline.add_argument("step")

    return parser


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
    print("         ⚠ 非内核级沙箱，Phase 5 之前不得对外宣称安全沙箱")

    try:
        key = resolve_api_key()
        print(f"  [OK  ] 模型密钥可解析：{mask_secret(key)}（Phase 1 不使用）")
    except ConfigError:
        print("  [SKIP] 模型密钥未配置（Phase 1 离线流程不需要）")

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


_COMMANDS = {
    "doctor": cmd_doctor,
    "handshake": cmd_handshake,
    "steps": cmd_steps,
    "brief": cmd_brief,
    "outline": cmd_outline,
}


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    handler = _COMMANDS[args.command]
    try:
        return handler(args)
    except (ConfigError, ContractError, ControlError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
