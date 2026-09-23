#!/usr/bin/env python3
"""运行 R2.1 专项测试，并把失败摘要写入 GitHub 检查注解。"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path


DEFAULT_MODULES = (
    "tests.test_workspace",
    "tests.test_autonomy",
    "tests.test_workbench",
)


def _workflow_escape(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def main(modules: tuple[str, ...] = DEFAULT_MODULES) -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        for test, traceback in (*result.failures, *result.errors):
            details = traceback[-1800:] if traceback else "test failed without traceback"
            summary = _workflow_escape(f"{test.id()}:\n{details}")
            print(f"::error title=R2.1 workspace test failure::{summary}", flush=True)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main(tuple(sys.argv[1:]) or DEFAULT_MODULES))
