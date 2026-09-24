#!/usr/bin/env python3
"""Offline policy checks for repository automation and README status badges."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
WORKFLOW_FILES = tuple(sorted((*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml"))))
ACTION_REF = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)", re.MULTILINE)
PINNED_ACTION_REF = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")

EXPECTED_BADGES = {
    "README.md": (
        "[![CI](https://github.com/ayukyo/icode/actions/workflows/ci.yml/badge.svg?branch=main)]"
        "(https://github.com/ayukyo/icode/actions/workflows/ci.yml)",
        "[![Pages](https://github.com/ayukyo/icode/actions/workflows/pages.yml/badge.svg?branch=main)]"
        "(https://github.com/ayukyo/icode/actions/workflows/pages.yml)",
        "[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)",
        "[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12-blue.svg)]"
        "(pyproject.toml)",
    ),
    "README.zh-CN.md": (
        "[![CI](https://github.com/ayukyo/icode/actions/workflows/ci.yml/badge.svg?branch=main)]"
        "(https://github.com/ayukyo/icode/actions/workflows/ci.yml)",
        "[![Pages](https://github.com/ayukyo/icode/actions/workflows/pages.yml/badge.svg?branch=main)]"
        "(https://github.com/ayukyo/icode/actions/workflows/pages.yml)",
        "[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)",
        "[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12-blue.svg)]"
        "(pyproject.toml)",
    ),
}
BADGE_LOCAL_TARGETS = (ROOT / "LICENSE", ROOT / "pyproject.toml")


def _require_tokens(path: Path, tokens: tuple[str, ...]) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return [
        f"{path.relative_to(ROOT)}: missing {token!r}"
        for token in tokens
        if token not in text
    ]


def check_action_pins() -> list[str]:
    problems: list[str] = []
    for workflow in WORKFLOW_FILES:
        text = workflow.read_text(encoding="utf-8")
        references = ACTION_REF.findall(text)
        if not references:
            problems.append(f"{workflow.relative_to(ROOT)}: no action references found")
        for reference in references:
            if not PINNED_ACTION_REF.fullmatch(reference):
                problems.append(
                    f"{workflow.relative_to(ROOT)}: action is not pinned to a 40-character SHA: "
                    f"{reference}"
                )
    return problems


def check_workflow_contracts() -> list[str]:
    problems: list[str] = []
    common = (
        "permissions:",
        "contents: read",
        "concurrency:",
        "cancel-in-progress: true",
        "timeout-minutes:",
        "persist-credentials: false",
    )
    problems.extend(
        _require_tokens(
            WORKFLOWS / "ci.yml",
            common
            + (
                "pull_request:",
                "push:",
                "submodules: recursive",
                'python-version: ["3.11", "3.12"]',
                "python -m compileall",
                "python -m unittest",
                "python scripts/preflight.py",
                "python scripts/check_site.py",
                "python scripts/check_governance.py",
            ),
        )
    )
    problems.extend(
        _require_tokens(
            WORKFLOWS / "pages.yml",
            common
            + (
                "pages: write",
                "id-token: write",
                "python3 scripts/check_site.py",
            ),
        )
    )
    problems.extend(
        _require_tokens(
            WORKFLOWS / "research-refresh.yml",
            common + (
                "schedule:",
                "workflow_dispatch:",
                "python3 scripts/check_agent_landscape.py",
            ),
        )
    )
    problems.extend(_require_tokens(WORKFLOWS / "ci.yml", (
        "python scripts/check_agent_landscape.py --warn-only",
    )))
    return problems


def check_dependabot() -> list[str]:
    return _require_tokens(ROOT / ".github" / "dependabot.yml", (
        "version: 2",
        'package-ecosystem: "pip"',
        'package-ecosystem: "github-actions"',
        'directory: "/"',
        "interval: \"weekly\"",
    ))


def check_badges() -> list[str]:
    problems: list[str] = []
    for filename, tokens in EXPECTED_BADGES.items():
        problems.extend(_require_tokens(ROOT / filename, tokens))
    problems.extend(
        f"missing badge target: {path.relative_to(ROOT)}"
        for path in BADGE_LOCAL_TARGETS
        if not path.is_file()
    )
    return problems


def main() -> int:
    required = (
        WORKFLOWS / "ci.yml",
        WORKFLOWS / "pages.yml",
        WORKFLOWS / "research-refresh.yml",
        ROOT / ".github" / "dependabot.yml",
    )
    missing = [
        f"missing required file: {path.relative_to(ROOT)}"
        for path in required
        if not path.is_file()
    ]
    if missing:
        problems = missing
    else:
        problems = check_action_pins()
        problems.extend(check_workflow_contracts())
        problems.extend(check_dependabot())
        problems.extend(check_badges())

    if problems:
        print(f"Governance checks failed: {len(problems)} problem(s)", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        return 1

    print("Governance checks passed")
    print(f"- Workflows with immutable action pins: {len(WORKFLOW_FILES)}")
    print(f"- Bilingual README badge sets: {len(EXPECTED_BADGES)}")
    print("- Dependabot ecosystems: pip, github-actions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
