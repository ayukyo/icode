#!/usr/bin/env python3
"""运行跨平台 workspace 回归，并把失败摘要写入 GitHub 检查注解。"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path


CROSS_PLATFORM_GIT_OBJECT_TESTS = (
    "tests.test_r3_regression.TestResultCommitTreeBinding.test_commit_tree读取只读对象并且不改用户index",
    "tests.test_r3_regression.TestResultCommitTreeBinding.test_commit_tree读取忽略replace_refs",
    "tests.test_r3_regression.TestResultCommitTreeBinding.test_commit_tree读取支持SHA256对象格式",
    "tests.test_r3_regression.TestResultCommitTreeBinding.test_result_commit只接受完整commit对象SHA",
    "tests.test_r3_regression.TestResultCommitTreeBinding.test_git只读查询清除继承环境且禁止惰性网络取对象",
    "tests.test_r3_regression.TestResultCommitTreeBinding.test_result_commit绑定受测tree且纳入最终回执指纹",
    "tests.test_r3_regression.TestResultCommitTreeBinding.test_result_commit树不匹配时报告失败关闭",
    "tests.test_r3_regression.TestResultCommitTreeBinding.test_不存在的结果commit对象失败关闭并保留请求SHA",
    "tests.test_r3_regression.TestResultCommitTreeBinding.test_commit对象内容与OID不匹配时失败关闭",
    "tests.test_r3_regression.TestResultCommitTreeBinding.test_tree对象内容与OID不匹配时失败关闭",
    "tests.test_r3_regression.TestResultCommitTreeBinding.test_tree对象超出读取预算时失败关闭",
    "tests.test_r3_regression.TestResultCommitTreeBinding.test_commit正文读取预算绑定预查大小",
    "tests.test_r3_regression.TestResultCommitTreeBinding.test_tree正文读取预算绑定预查大小",
    "tests.test_r3_regression.TestResultCommitTreeBinding.test_Git原始对象读取超出输出上限时提前终止",
    "tests.test_r3_regression.TestResultCommitTreeBinding.test_partial_clone缺少tree时拒绝惰性取回",
    "tests.test_r3_regression.TestResultCommitTreeBinding.test无稳定受测tree时拒绝读取结果提交",
    "tests.test_r3_regression.TestResultCommitTreeBinding.test_same_tree的后测commit仅标记内容匹配不倒推测试时序",
)

DEFAULT_MODULES = (
    "tests.test_workspace",
    "tests.test_autonomy",
    "tests.test_workbench",
    # Object reading is cross-platform; run its focused methods, not the
    # run_task integration case that requires a supported worktree tree OID.
    *CROSS_PLATFORM_GIT_OBJECT_TESTS,
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
            print(f"::error title=Workspace regression test failure::{summary}", flush=True)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main(tuple(sys.argv[1:]) or DEFAULT_MODULES))
