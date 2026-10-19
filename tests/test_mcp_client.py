"""MCP 客户端：分发层强制、batch 拒绝、有界与治理链继承（R5/W3）。"""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory

from icode.backends import FakeBackend
from icode.extensions import (
    McpClient,
    McpClientError,
    mcp_tool_to_tool,
)
from icode.loop import AgentLoop, LoopConfig
from icode.tools.base import (
    OPCLASS_EXTERNAL,
    OPCLASS_READ_ONLY,
    ToolContext,
    ToolRegistry,
)
from icode.guard import Guard, Scope

_TESTS_DIR = Path(__file__).resolve().parent
_SERVER = _TESTS_DIR / "_mcp_fake_server.py"


def _spawn(mode: str, **kwargs) -> McpClient:
    client = McpClient([sys.executable, str(_SERVER), mode], **kwargs)
    client.start()
    return client


class TestMcpProtocol(unittest.TestCase):
    def test_initialize与tools_list正常路径(self) -> None:
        with _spawn("normal") as client:
            info = client.initialize()
            self.assertEqual(info["serverInfo"]["name"], "fake-mcp")
            self.assertEqual(client.server_info["name"], "fake-mcp")
            tools = client.list_tools()
            self.assertEqual([tool.name for tool in tools], ["jira_search"])
            result = client.call_tool("jira_search", {"q": "bug"})
            self.assertTrue(result.ok)
            self.assertEqual(result.text, "pong")
            self.assertFalse(result.truncated)

    def test_会话目录零新文件且客户端不执行回灌指令(self) -> None:
        with TemporaryDirectory() as tmp:
            with _spawn("instruction_payload", cwd=tmp) as client:
                client.initialize()
                result = client.call_tool("jira_search", {"q": "x"})
                # 回灌文本只是数据：不含执行语义，也不产生任何文件
                self.assertIn("rm -rf /", result.text)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_服务端发起的文件请求被拒付(self) -> None:
        with _spawn("push_file_request") as client:
            client.initialize()
            result = client.call_tool("jira_search", {"q": "x"})
            self.assertTrue(result.ok)
            self.assertEqual([r["method"] for r in client.refusals], ["fs/write_file"])
            self.assertTrue(client.refusals[0]["had_id"])

    def test_服务端发起的采样请求被拒付(self) -> None:
        with _spawn("push_request") as client:
            client.initialize()
            result = client.call_tool("jira_search", {"q": "x"})
            self.assertTrue(result.ok)
            self.assertEqual([r["method"] for r in client.refusals],
                             ["sampling/createMessage"])

    def test_服务端通知被忽略且不破坏请求(self) -> None:
        with _spawn("push_notification") as client:
            client.initialize()
            result = client.call_tool("jira_search", {"q": "x"})
            self.assertTrue(result.ok)
            self.assertEqual(client.refusals,
                             [{"method": "notifications/message", "had_id": False}])

    def test_batch帧整体拒绝(self) -> None:
        with _spawn("batch") as client:
            client.initialize()
            with self.assertRaises(McpClientError) as caught:
                client.call_tool("jira_search", {"q": "x"})
            self.assertEqual(caught.exception.code, "batch_not_supported")

    def test_响应id不匹配即协议错误(self) -> None:
        with _spawn("wrong_id") as client:
            client.initialize()
            with self.assertRaises(McpClientError) as caught:
                client.list_tools()
            self.assertEqual(caught.exception.code, "protocol_error")

    def test_畸形帧即协议错误(self) -> None:
        with _spawn("malformed") as client:
            client.initialize()
            with self.assertRaises(McpClientError) as caught:
                client.list_tools()
            self.assertEqual(caught.exception.code, "protocol_error")

    def test_超帧上限失败封闭(self) -> None:
        with _spawn("oversize", max_line_bytes=65536) as client:
            client.initialize()
            with self.assertRaises(McpClientError) as caught:
                client.list_tools()
            self.assertEqual(caught.exception.code, "oversize_response")

    def test_读超时失败封闭(self) -> None:
        with _spawn("slow", timeout_seconds=0.5) as client:
            client.initialize()
            with self.assertRaises(McpClientError) as caught:
                client.list_tools()
            self.assertEqual(caught.exception.code, "timeout")

    def test_服务端提前退出给出稳定码(self) -> None:
        client = _spawn("exit_after_initialize")
        try:
            client.initialize()
            with self.assertRaises(McpClientError) as caught:
                client.list_tools()
            self.assertIn(caught.exception.code,
                          ("transport_closed", "timeout"))
        finally:
            client.close()

    def test_远端错误映射为稳定码(self) -> None:
        with _spawn("remote_error") as client:
            client.initialize()
            with self.assertRaises(McpClientError) as caught:
                client.call_tool("jira_search", {"q": "x"})
            self.assertEqual(caught.exception.code, "remote_error")

    def test_输出截断有界(self) -> None:
        with _spawn("long_output") as client:
            client.initialize()
            result = client.call_tool("jira_search", {"q": "x"}, max_result_chars=1000)
            self.assertTrue(result.truncated)
            self.assertEqual(len(result.text), 1000)

    def test_客户端不发送协议外方法(self) -> None:
        client = McpClient([sys.executable, str(_SERVER), "normal"])
        client.start()
        try:
            with self.assertRaises(McpClientError) as caught:
                client._send("resources/read", {})
            self.assertEqual(caught.exception.code, "client_method_refused")
        finally:
            client.close()


class TestMcpToolAdapter(unittest.TestCase):
    def test_包装后的工具经ToolRegistry同一治理链(self) -> None:
        with _spawn("normal") as client:
            client.initialize()
            (description,) = client.list_tools()
            tool = mcp_tool_to_tool(description, client, opclass=OPCLASS_EXTERNAL)
            registry = ToolRegistry()
            registry.register(tool)

            # ① Guard 拒绝时 handler 不执行：非命令类工具走 check_read(ctx.root)，
            #    allowed_read_files 不含 root 即 DENY——与内建工具同一裁决路径。
            events: list[tuple[str, dict]] = []
            from icode.approvals import DenyAllApprover
            from icode.budget import BudgetTracker
            with TemporaryDirectory() as tmp:
                root = Path(tmp)
                guard = Guard(Scope(workspace_root=root,
                                    allowed_read_files=(root / "other.txt",)))
                ctx = ToolContext(root=root)
                backend = FakeBackend([
                    {"content": "", "tool_calls": [{
                        "id": "c1", "name": tool.name, "arguments": {"q": "bug"},
                    }]},
                    {"content": "完成"},
                ])
                loop = AgentLoop(
                    backend=backend, registry=registry, guard=guard, ctx=ctx,
                    approver=DenyAllApprover(), operations=None,
                    budget=BudgetTracker(), config=LoopConfig(max_turns=3),
                    on_event=lambda name, payload: events.append((name, payload)),
                )
                result = loop.run([{"role": "user", "content": "查工单"}])
            self.assertTrue(any(name == "tool_denied" for name, _ in events))
            tool_messages = [m for m in result.messages if m.get("role") == "tool"]
            self.assertTrue(tool_messages)
            # Guard 在 handler 之前截停：invocation 判定为 deny，loop 不会 invoke。
            self.assertEqual(result.turns[0].invocations[0].decision, "deny")

            # ② 放行时 handler 经 registry.invoke 到达远端，且 opclass 非只读
            #    触发副作用回执（与内建写/执行类工具同一规则）。
            started: list[tuple[str, str]] = []
            finished: list[tuple[str, str]] = []

            class _Recorder:
                def start(self, name, opclass, input_desc):
                    started.append((name, opclass))
                    return SimpleNamespace(
                        can_execute=True, attempt="att-1",
                        already_applied=False, detail="",
                    )

                def finish(self, attempt, outcome, evidence, check_ref, failure):
                    finished.append((attempt, outcome))
                    return True

            with TemporaryDirectory() as tmp:
                root = Path(tmp)
                ctx = ToolContext(root=root)
                backend = FakeBackend([
                    {"content": "", "tool_calls": [{
                        "id": "c1", "name": tool.name, "arguments": {"q": "bug"},
                    }]},
                    {"content": "完成"},
                ])
                loop = AgentLoop(
                    backend=backend,
                    registry=registry,
                    guard=Guard(Scope(workspace_root=root)), ctx=ctx,
                    approver=DenyAllApprover(), operations=_Recorder(),
                    budget=BudgetTracker(), config=LoopConfig(max_turns=3),
                )
                result = loop.run([{"role": "user", "content": "查工单"}])
            self.assertEqual(started, [(f"tool:{tool.name}", OPCLASS_EXTERNAL)])
            self.assertEqual(finished, [("att-1", "success")])
            self.assertTrue(result.ok)

    def test_会话不可用或参数不匹配时失败封闭(self) -> None:
        client = McpClient([sys.executable, str(_SERVER), "normal"])
        client.start()
        client.initialize()
        (description,) = client.list_tools()
        tool = mcp_tool_to_tool(description, client, opclass=OPCLASS_READ_ONLY)
        client.close()
        result = tool.run(ToolContext(root=Path("/tmp")), {"q": "bug"})
        self.assertFalse(result.ok)
        self.assertEqual(result.meta["error"], "mcp_session_unavailable")

    def test_工具名非法拒绝包装(self) -> None:
        with _spawn("normal") as client:
            client.initialize()
            (description,) = client.list_tools()
            from icode.extensions import McpToolDescription
            with self.assertRaises(ValueError):
                mcp_tool_to_tool(
                    McpToolDescription(name="Bad Name; rm -rf /"), client,
                )


if __name__ == "__main__":
    unittest.main()
