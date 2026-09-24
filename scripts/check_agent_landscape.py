#!/usr/bin/env python3
"""提醒复核开源 Agent 对照；日期/数量检查不证明源码已核对。"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOCUMENT = ROOT / "docs" / "agent-landscape-live.md"
DATES = re.compile(
    r"^- 最近观察：(\d{4}-\d{2}-\d{2})；下次全量复核：不晚于 (\d{4}-\d{2}-\d{2})$",
    re.MULTILINE,
)
PROJECT = re.compile(r"^\|[^|]*\|\s*\[[^]]+\]\((https?://[^)]+)\)", re.MULTILINE)
MAX_REVIEW_DAYS = 30


def check_document(body: str, today: date) -> list[str]:
    """只检查复核排期与观察名单结构，不推断上游是否真的更新。"""
    problems: list[str] = []
    matches = DATES.findall(body)
    if len(matches) != 1:
        problems.append("观察日期或下次全量复核日期缺失、重复或格式无效")
    else:
        try:
            observed, due = (date.fromisoformat(value) for value in matches[0])
        except ValueError:
            problems.append("观察日期或复核日期不是有效日历日期")
        else:
            if observed > today:
                problems.append("最近观察日期不能位于未来")
            if due < observed or due > observed + timedelta(days=MAX_REVIEW_DAYS):
                problems.append("下次全量复核必须在最近观察后 30 天内")
            if today > due:
                problems.append(f"开源 Agent 对照已逾期：应于 {due.isoformat()} 前复核")

    section = body.partition("## 20 个观察对象\n")
    if not section[1]:
        problems.append("缺少 20 个观察对象章节")
    else:
        table = section[2].split("\n## ", 1)[0]
        projects = PROJECT.findall(table)
        if len(projects) != 20 or len(set(projects)) != 20:
            problems.append("观察名单必须包含 20 个不同项目链接")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document", type=Path, default=DEFAULT_DOCUMENT)
    parser.add_argument("--today", type=date.fromisoformat, default=date.today())
    parser.add_argument("--warn-only", action="store_true")
    args = parser.parse_args(argv)

    try:
        body = args.document.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        problems = ["无法读取开源 Agent 持续对照文档"]
    else:
        problems = check_document(body, args.today)

    if problems:
        prefix = "::warning::" if os.environ.get("GITHUB_ACTIONS") else "WARNING: "
        for problem in problems:
            print(f"{prefix}{problem}", file=sys.stderr)
        return 0 if args.warn_only else 1

    print("开源 Agent 对照复核排期有效；观察名单 20 项（不代表上游源码已复核）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
