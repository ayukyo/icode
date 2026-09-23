"""控制面薄适配测试。"""

from __future__ import annotations

import unittest
from pathlib import Path

from tests._support import require_skill

from icode.control import ControlPlane, ControlResult


class RecordingControlPlane(ControlPlane):
    """不启动子进程，只记录最终参数列表。"""

    def __init__(self) -> None:
        super().__init__(require_skill())
        self.calls: list[tuple[str, ...]] = []

    def run(self, *args: str, check: bool | None = None) -> ControlResult:
        self.calls.append(tuple(args))
        return ControlResult(args=tuple(args), returncode=0, data={"ok": True})


class TestControlPlaneIntakeAdapter(unittest.TestCase):
    def test_create_next_只转发可信工作区与业务意图(self) -> None:
        cp = RecordingControlPlane()

        result = cp.create_next(
            workspace=Path("/srv/project"),
            requirement="Fix reconnect",
            request_id="ui-123",
            index_path=Path("/tmp/index.json"),
        )

        self.assertTrue(result.ok)
        self.assertEqual(
            cp.calls[-1],
            (
                "create-next",
                "--workspace", "/srv/project",
                "--requirement", "Fix reconnect",
                "--request-id", "ui-123",
                "--index", "/tmp/index.json",
            ),
        )

    def test_create_next_索引覆盖可省略(self) -> None:
        cp = RecordingControlPlane()
        cp.create_next(
            workspace="/srv/project",
            requirement="Fix reconnect",
            request_id="ui-123",
        )
        self.assertNotIn("--index", cp.calls[-1])

    def test_metadata_update_允许调用方提供独立幂等键(self) -> None:
        cp = RecordingControlPlane()

        cp.metadata_update(
            "/tmp/ticket",
            ticket_id="IC-1",
            set_json={"extensions": {"icode_agent": {"locale": "en-US"}}},
            request="intake-ui-123",
        )

        args = cp.calls[-1]
        self.assertEqual(args[args.index("--request-id") + 1], "intake-ui-123")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
