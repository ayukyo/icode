"""跨进程工单租约测试。"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from tests._support import temp_workspace

from icode.workspace import TicketLease, WorkspaceBusyError, WorkspaceError


_CHILD_ACQUIRE = """
from pathlib import Path
import sys

from icode.workspace import TicketLease, WorkspaceBusyError

try:
    lease = TicketLease.acquire(
        Path(sys.argv[1]),
        project_id=sys.argv[2],
        ticket_id=sys.argv[3],
        run_id=sys.argv[4],
    )
except WorkspaceBusyError:
    print("busy")
else:
    print("acquired")
    lease.release()
"""


class TestTicketLease(unittest.TestCase):
    def setUp(self) -> None:
        self._workspace = temp_workspace()
        self.data_root = self._workspace.__enter__()

    def tearDown(self) -> None:
        self._workspace.__exit__(None, None, None)

    def _acquire_in_child(self, ticket_id: str, *, project_id: str = "project-1") -> str:
        env = os.environ.copy()
        source_root = str(Path(__file__).resolve().parents[1] / "src")
        existing = env.get("PYTHONPATH")
        env["PYTHONPATH"] = os.pathsep.join(
            part for part in (source_root, existing) if part
        )
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                _CHILD_ACQUIRE,
                str(self.data_root),
                project_id,
                ticket_id,
                "child-run",
            ],
            check=True,
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
        return completed.stdout.strip()

    def test_同一工程同一工单被第二进程拒绝(self) -> None:
        with TicketLease.acquire(self.data_root, "project-1", "ticket-1", "parent-run"):
            self.assertEqual(self._acquire_in_child("ticket-1"), "busy")

    def test_不同工单可由两个进程同时持有(self) -> None:
        with TicketLease.acquire(self.data_root, "project-1", "ticket-1", "parent-run"):
            self.assertEqual(self._acquire_in_child("ticket-2"), "acquired")

    def test_release_后另一进程可重新获取(self) -> None:
        lease = TicketLease.acquire(self.data_root, "project-1", "ticket-1", "parent-run")
        lease.release()

        self.assertEqual(self._acquire_in_child("ticket-1"), "acquired")

    def test_重复_release_安全(self) -> None:
        lease = TicketLease.acquire(self.data_root, "project-1", "ticket-1", "parent-run")
        lease.release()
        lease.release()

        self.assertEqual(self._acquire_in_child("ticket-1"), "acquired")

    def test_锁路径只含工程与工单身份摘要(self) -> None:
        project_id = "../../untrusted-project"
        ticket_id = "nested/untrusted-ticket"
        expected_name = hashlib.sha256(
            project_id.encode("utf-8") + b"\0" + ticket_id.encode("utf-8")
        ).hexdigest()

        with TicketLease.acquire(
            self.data_root, project_id, ticket_id, "run-1"
        ) as lease:
            self.assertEqual(lease.path.name, expected_name)
            self.assertTrue(lease.path.is_relative_to(self.data_root))
            relative = str(lease.path.relative_to(self.data_root))
            self.assertNotIn(project_id, relative)
            self.assertNotIn(ticket_id, relative)

    def test_锁成功后写入稳定诊断元数据(self) -> None:
        with TicketLease.acquire(
            self.data_root, "project-1", "ticket-1", "run-1"
        ) as lease:
            metadata_path = lease.path

        # Windows 的字节区间锁可能拒绝另一个句柄读取被锁字节，释放后再读。
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

        self.assertEqual(
            metadata,
            {
                "pid": os.getpid(),
                "project_id": "project-1",
                "run_id": "run-1",
                "schema_version": 1,
                "ticket_id": "ticket-1",
            },
        )

    def test_拒绝空值_控制字符及不可编码字符串(self) -> None:
        invalid_values = ("", "line\nbreak", "delete\x7f", "surrogate\ud800")
        for field_index in range(3):
            for invalid in invalid_values:
                values = ["project-1", "ticket-1", "run-1"]
                values[field_index] = invalid
                with self.subTest(field=field_index, value=repr(invalid)):
                    with self.assertRaises(WorkspaceError):
                        TicketLease.acquire(self.data_root, *values)

    def test_元数据写入异常后关闭句柄并释放锁(self) -> None:
        with mock.patch("icode.workspace.os.fsync", side_effect=OSError("disk error")):
            with self.assertRaises(WorkspaceError):
                TicketLease.acquire(
                    self.data_root, "project-1", "ticket-1", "parent-run"
                )

        self.assertEqual(self._acquire_in_child("ticket-1"), "acquired")

    def test_目录创建失败统一为_workspace_error(self) -> None:
        not_a_directory = self.data_root / "file"
        not_a_directory.write_text("occupied", encoding="utf-8")

        with self.assertRaises(WorkspaceError):
            TicketLease.acquire(not_a_directory, "project-1", "ticket-1", "run-1")


if __name__ == "__main__":
    unittest.main()
