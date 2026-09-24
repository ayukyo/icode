"""离线保证测试：Phase 1 全流程必须零网络访问。

两层保证：
1. 静态：核心模块不得出现网络相关导入（新增模块需显式登记到豁免表）；
2. 运行时：把 socket 打瘸后跑完整握手，仍然必须通过。
"""

from __future__ import annotations

import ast
import socket
import sys
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

from tests._support import REPO_ROOT, require_skill, temp_workspace

from icode.cli import cmd_doctor
from icode.handshake import run_handshake

# 必须完全离线的"契约核心"模块（相对 src/）。
# 注：Phase 2 起 cli.py 与 backends/__init__.py 会（传递）引用网络模块
#     （真模型后端 + 代理自检），因此不再列入；但契约内核必须始终无网络依赖。
OFFLINE_MODULES = (
    "icode/__init__.py",
    "icode/config.py",
    "icode/contracts.py",
    "icode/control.py",
    "icode/disclosure.py",
    "icode/guard.py",
    "icode/handshake.py",
    "icode/reasoning.py",
    "icode/budget.py",
    "icode/approvals.py",
    "icode/operations.py",
    "icode/backends/base.py",
    "icode/backends/fake.py",
    "icode/tools/base.py",
    "icode/tools/builtin.py",
)

NETWORK_IMPORTS = {"socket", "ssl", "urllib", "http", "requests", "httpx", "aiohttp", "ftplib", "smtplib"}


class TestStaticOffline(unittest.TestCase):
    def test_核心模块无网络导入(self) -> None:
        offenders: list[str] = []
        for rel in OFFLINE_MODULES:
            path = REPO_ROOT / "src" / rel
            self.assertTrue(path.is_file(), f"模块缺失：{rel}")
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split(".")[0] in NETWORK_IMPORTS:
                            offenders.append(f"{rel}: import {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    root = (node.module or "").split(".")[0]
                    if root in NETWORK_IMPORTS:
                        offenders.append(f"{rel}: from {node.module} import ...")
        self.assertEqual(offenders, [], f"Phase 1 核心模块出现网络导入：{offenders}")

    def test_假后端不发起任何外部调用(self) -> None:
        from icode.backends import FakeBackend

        backend = FakeBackend(["离线回答"])
        msg = backend.complete([{"role": "user", "content": "hi"}])
        self.assertEqual(msg.content, "离线回答")
        self.assertFalse(msg.has_tool_calls)
        self.assertEqual(len(backend.calls), 1)


class TestRuntimeOffline(unittest.TestCase):
    def test_doctor_如实报告_r2_合同尚未执行(self) -> None:
        settings = require_skill()

        with temp_workspace() as ws:
            stdout = StringIO()
            args = Namespace(
                skill_root=str(settings.skill_root),
                workspace=str(ws),
            )
            with redirect_stdout(stdout):
                rc = cmd_doctor(args)

        output = stdout.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("隔离后端：", output)
        self.assertIn("R2 策略合同：v1", output)
        self.assertIn("一致性测试：尚未执行", output)
        if sys.platform.startswith("linux"):
            self.assertIn("随包 Linux 助手", output)
            self.assertIn("策略级隔离未就绪", output)

    def test_socket_被禁用时握手仍通过(self) -> None:
        settings = require_skill()

        def _blocked(*_args, **_kwargs):  # pragma: no cover - 仅在误联网时触发
            raise AssertionError("Phase 1 不应发起任何网络连接")

        with temp_workspace() as ws:
            with mock.patch.object(socket, "socket", _blocked), \
                 mock.patch.object(socket, "create_connection", _blocked), \
                 mock.patch.object(socket, "getaddrinfo", _blocked):
                report = run_handshake(settings, workspace=ws, step="plan")
            self.assertTrue(report.ok, report.render())


if __name__ == "__main__":
    unittest.main()
