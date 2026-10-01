#!/usr/bin/env python3
"""运行跨平台 workspace 回归，并把失败摘要写入 GitHub 检查注解。"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path


# Keep the cross-platform R3 regression matrix bounded while exercising the
# real task-to-tree and task-receipt CLI chains on every workspace platform.
CROSS_PLATFORM_R3_TESTS = (
    "tests.test_r3_regression.TestTaskReviewAndDiffBinding.test_run_task证据锚定真实Git基线和含预存脏改动的快照",
    "tests.test_r3_regression.TestTaskReviewAndDiffBinding.test_SHA256基线自动选择对应tree对象格式",
    "tests.test_r3_regression.TestResultCommitTreeBinding.test_run_task显式参数自动绑定结果commit",
    "tests.test_r3_regression.TestResultCommitTreeBinding.test_run_task成功测试绑定受测tree和结果commit",
    "tests.test_evidence.TestEvidencePack.test真实task回执经CLI保存导入证据包并独立校验",
    "tests.test_evidence.TestEvidencePack.test_evidence导入无效回执时返回用户错误且不触碰目标包",
    "tests.test_evidence.TestStandaloneVerifier.test_内置和独立校验器对畸形JSON结构返回失败而不抛异常",
    "tests.test_evidence.TestStandaloneVerifier.test_内置和独立校验器拒绝证据包路径越界",
    "tests.test_evidence.TestStandaloneVerifier.test_内置和独立校验器拒绝固定成员符号链接",
    "tests.test_evidence.TestStandaloneVerifier.test_内置和独立校验器不跟随未登记的外部链接目录",
    "tests.test_evidence.TestStandaloneVerifier.test_内置和独立校验器拒绝证据包中的重复JSON成员名",
    "tests.test_runner.TestReviewStepReadOnlyContext.test_review阶段无隔离沙箱时命令在启动前拒绝且不产生标记",
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
    # Keep the integration matrix bounded while exercising task-tree capture,
    # result-commit binding, and receipt export/import on each workspace platform.
    *CROSS_PLATFORM_R3_TESTS,
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
