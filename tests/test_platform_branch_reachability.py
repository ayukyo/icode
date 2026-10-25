"""平台分支可达性守卫：让被 skip 掩盖的**引用错误**在本机暴露。

CI 的 POSIX/macOS 腿能发现问题，但反馈很慢；本机（Windows）跑这些测试时
它们被 `skipUnless(os.name == "posix")` 直接跳过——分支里的 NameError、
属性缺失、patch 目标失配，本机一律看不见。

本守卫剥掉 skip 标记让测试体真的跑起来，并**只把「引用类」失败判为回归**：

- `NameError` —— 引用了未定义的名字（搬迁后忘了同步 import 的典型症状）；
- `AttributeError` —— 引用了不存在的属性（如 patch 目标已随代码搬走）。

平台本身的能力差异（Windows 没有 `os.killpg`、没有 kqueue、bwrap 缺失等）
表现为别的异常类型，不在此列，因此不产生误报。
"""
from __future__ import annotations

import os
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 引用类错误：与平台无关，搬迁代码后忘了同步 import/patch 目标就会命中。
REFERENCE_ERRORS = (NameError, AttributeError)


def _strip_skips(cls: type) -> None:
    for name in list(vars(cls)):
        member = getattr(cls, name)
        if callable(member) and name.startswith("test_"):
            member.__unittest_skip__ = False
            member.__unittest_skip_why__ = ""


def _reference_failures(cls: type) -> list[tuple[str, str]]:
    """强制运行类内全部测试，返回 [(测试名, 引用类错误)]。"""
    _strip_skips(cls)
    found: list[tuple[str, str]] = []
    for name in sorted(n for n in dir(cls) if n.startswith("test_")):
        result = unittest.TestResult()
        try:
            cls(name).run(result)
        except REFERENCE_ERRORS as error:
            found.append((name, f"{type(error).__name__}: {error}"))
            continue
        except Exception:
            continue  # 其它异常 = 平台能力差异，不算引用回归
        if result.wasSuccessful():
            continue
        for _, traceback in list(result.failures) + list(result.errors):
            for line in traceback.split("\n"):
                if "NameError" in line or "AttributeError" in line:
                    found.append((name, line.strip()))
                    break
    return found


class PlatformBranchReachabilityTests(unittest.TestCase):
    """被平台 skip 掩盖的引用错误，必须在本机就能发现。"""

    def test_runner_verification_tests_have_no_reference_errors(self) -> None:
        """TestIndependentVerification：剥掉 skip 后不得出现 NameError/AttributeError。"""
        from tests.test_runner import TestIndependentVerification

        failures = _reference_failures(TestIndependentVerification)
        self.assertEqual(
            [], failures,
            "以下测试在剥掉平台 skip 后出现引用类错误"
            "（多半是搬迁后 patch 目标或 import 没同步，Windows 上被 skip 掩盖）：\n  "
            + "\n  ".join(f"{name}: {detail}" for name, detail in failures),
        )

    def test_stripping_skips_actually_runs_the_tests(self) -> None:
        """守卫本身要有效：确认 skip 确实被剥掉了（否则上一条永远绿）。"""
        from tests.test_runner import TestIndependentVerification

        _strip_skips(TestIndependentVerification)
        method = getattr(
            TestIndependentVerification, "test_POSIX失去子进程状态时拒绝继续")
        self.assertFalse(
            getattr(method, "__unittest_skip__", True),
            "skip 标记未能剥除，守卫会失去意义",
        )


if __name__ == "__main__":
    unittest.main()
