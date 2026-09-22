#!/usr/bin/env python3
"""阶段交付前的三道守护（roadmap §7.1）。

本仓开启"每阶段自动 commit + push"，没有人工把关机会，
所以这三道必须**在提交前**自动跑过：

    ① 密钥扫描      全仓扫描密钥形态与密钥文件名
    ② 子模块完整性   vendor/icode-skill 必须无任何本地修改
    ③ 测试全绿       python -m unittest 退出码 0

用法：
    python scripts/preflight.py            # 全部三道
    python scripts/preflight.py --only secrets
退出码：0 = 全部通过；1 = 有阻断项。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SUBMODULE = REPO / "vendor" / "icode-skill"

# 扫描时跳过的目录（子模块内容由上游自己负责；.git 不是工作区内容）
SKIP_DIRS = {".git", "vendor", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv"}

# 密钥形态：命中即阻断
SECRET_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bsk-[A-Za-z0-9_\-]{16,}\b", "疑似 API key（sk- 形态）"),
    (r"\bBearer\s+[A-Za-z0-9_\-\.]{20,}", "疑似 Bearer token"),
    (r'"apiKey"\s*:\s*"[^"]{12,}"', "疑似 apiKey 字面量"),
    (r"\bANTHROPIC_AUTH_TOKEN\b\s*[:=]\s*[\"']?[A-Za-z0-9_\-]{20,}", "疑似 Anthropic token"),
    (r"\bgh[pousr]_[A-Za-z0-9]{30,}\b", "疑似 GitHub token"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "私钥文件内容"),
)

# 不允许出现在仓库内的文件名形态（.gitignore 是兜底，这里是硬检查）
FORBIDDEN_NAME_RE = re.compile(r"(key|密钥|secret|token|credential)", re.IGNORECASE)
FORBIDDEN_SUFFIXES = {".key", ".pem", ".p12", ".pfx", ".env"}


def _iter_files() -> list[Path]:
    out: list[Path] = []
    for p in REPO.rglob("*"):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.relative_to(REPO).parts):
            continue
        out.append(p)
    return out


def guard_secrets() -> list[str]:
    problems: list[str] = []
    for path in _iter_files():
        rel = path.relative_to(REPO)
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            problems.append(f"{rel}: 禁止入库的文件类型 {path.suffix}")
            continue
        if FORBIDDEN_NAME_RE.search(path.name) and path.suffix.lower() == ".txt":
            problems.append(f"{rel}: 文件名疑似凭据载体")
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "\x00" in text[:2048]:  # 二进制跳过
            continue
        for pattern, label in SECRET_PATTERNS:
            if re.search(pattern, text):
                problems.append(f"{rel}: {label}")
                break
    return problems


def guard_submodule() -> list[str]:
    problems: list[str] = []
    if not SUBMODULE.is_dir():
        return ["vendor/icode-skill 不存在（子模块未初始化）"]

    status = _git(["-C", str(SUBMODULE), "status", "--porcelain"])
    if status.strip():
        problems.append(f"子模块工作树被修改（两仓必须独立）：\n{status.strip()[:500]}")

    head = _git(["-C", str(SUBMODULE), "rev-parse", "HEAD"]).strip()
    gitlink = _git(["ls-files", "-s", "vendor/icode-skill"]).strip()
    if gitlink:
        recorded = gitlink.split()[1]
        if recorded != head:
            problems.append(f"子模块 HEAD({head[:12]}) != 记录的 gitlink({recorded[:12]})；"
                            "若是有意 bump，请确认已跑冒烟测试")
    return problems


def guard_tests() -> list[str]:
    proc = subprocess.run(
        [sys.executable, "-m", "unittest"],
        cwd=str(REPO), capture_output=True, text=True,
        encoding="utf-8", errors="replace", shell=False,
    )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-15:]
        return ["测试未全绿：\n" + "\n".join(tail)]
    return []


def _git(args: list[str]) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=str(REPO), capture_output=True, text=True,
        encoding="utf-8", errors="replace", shell=False,
    )
    return proc.stdout or ""


GUARDS = {
    "secrets": ("① 密钥扫描", guard_secrets),
    "submodule": ("② 子模块完整性", guard_submodule),
    "tests": ("③ 测试全绿", guard_tests),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="阶段交付前的三道守护")
    parser.add_argument("--only", choices=sorted(GUARDS), help="只跑其中一道")
    args = parser.parse_args(argv)

    selected = [args.only] if args.only else list(GUARDS)
    failed: list[str] = []
    print("阶段交付前置守护")
    for key in selected:
        title, fn = GUARDS[key]
        problems = fn()
        if problems:
            failed.append(key)
            print(f"  [FAIL] {title}")
            for p in problems:
                for line in str(p).splitlines():
                    print(f"         {line}")
        else:
            print(f"  [OK  ] {title}")

    print()
    if failed:
        print(f"结果：阻断（{len(failed)}/{len(selected)} 道未过）—— 不允许 commit / push")
        return 1
    print(f"结果：全部通过（{len(selected)} 道）—— 可以 commit / push")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
