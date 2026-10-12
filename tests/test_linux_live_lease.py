"""Linux 活跃租约检查：真实持有对象与文件身份，故障注入限定在检查边界。"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

import icode.workspace as workspace_module
from icode.workspace import TicketLease, WorkspaceError
from tests._support import temp_workspace


ERROR = "工单租约不可用"
CHILD = """
from pathlib import Path
import sys
from icode.workspace import TicketLease, WorkspaceBusyError

try:
    lease = TicketLease.acquire(Path(sys.argv[1]), 'project', 'ticket', 'child')
except WorkspaceBusyError:
    print('busy')
else:
    lease.release()
    print('acquired')
"""


@unittest.skipUnless(sys.platform.startswith('linux'), 'Linux S1a lease slice')
class TestLinuxLiveLease(unittest.TestCase):
    def setUp(self) -> None:
        workspace = temp_workspace()
        self.root = workspace.__enter__()
        self.addCleanup(workspace.__exit__, None, None, None)
        self.lease = TicketLease.acquire(self.root, 'project', 'ticket', 'run')
        self.addCleanup(self.release_owned)

    def release_owned(self) -> None:
        stream = self.lease._stream
        externally_closed = stream is not None and stream.closed
        try:
            self.lease.release()
        except WorkspaceError:
            # 外部真实 close 后，原 owner 的 release 仍必须清空所有权。
            if not (externally_closed and self.lease._stream is None):
                raise

    def assert_fixed(self, action) -> None:
        with self.assertRaises(WorkspaceError) as caught:
            action()
        self.assertEqual(str(caught.exception), ERROR)
        self.assertIsNone(caught.exception.__cause__)
        self.assertTrue(caught.exception.__suppress_context__)

    def test_released_lease_is_rejected(self) -> None:
        self.lease.release()
        self.assert_fixed(self.lease._validate_active)
        self.assertIsNone(self.lease._stream)

    def test_live_lease_returns_none_and_preserves_owner(self) -> None:
        stream = self.lease._stream
        descriptor = stream.fileno()
        before = os.fstat(descriptor)
        self.assertIsNone(self.lease._validate_active())
        self.assertIs(self.lease._stream, stream)
        self.assertFalse(stream.closed)
        after = os.fstat(descriptor)
        self.assertEqual((after.st_dev, after.st_ino), (before.st_dev, before.st_ino))

    def test_actual_external_stream_close_is_rejected(self) -> None:
        stream = self.lease._stream
        stream.close()
        self.assert_fixed(self.lease._validate_active)
        self.assertIs(self.lease._stream, stream)
        self.assertTrue(stream.closed)

    def test_actual_path_replacement_is_rejected_without_owner_close(self) -> None:
        stream = self.lease._stream
        descriptor = stream.fileno()
        previous = self.lease.path.with_name(self.lease.path.name + '.previous')
        self.lease.path.rename(previous)
        self.lease.path.write_bytes(b'replacement')
        self.assert_fixed(self.lease._validate_active)
        self.assertIs(self.lease._stream, stream)
        self.assertFalse(stream.closed)
        self.assertEqual(os.fstat(descriptor).st_ino, previous.lstat().st_ino)

    def test_actual_unlink_is_rejected_without_owner_close(self) -> None:
        stream = self.lease._stream
        descriptor = stream.fileno()
        self.lease.path.unlink()
        self.assert_fixed(self.lease._validate_active)
        self.assertIs(self.lease._stream, stream)
        self.assertFalse(stream.closed)
        os.fstat(descriptor)

    def test_no_reacquire_unlock_or_stream_io(self) -> None:
        stream = self.lease._stream
        before = self.lease.__dict__.copy()
        offset = stream.tell()
        payload = self.lease.path.read_bytes()
        with (
            mock.patch.multiple(
                stream, seek=mock.DEFAULT, read=mock.DEFAULT, write=mock.DEFAULT,
                flush=mock.DEFAULT, truncate=mock.DEFAULT, close=mock.DEFAULT,
            ) as stream_calls,
            mock.patch.object(workspace_module, '_acquire_file_lock') as acquire,
            mock.patch.object(workspace_module, '_release_file_lock') as release,
            mock.patch.object(workspace_module.os, 'open') as open_fd,
            mock.patch.object(workspace_module.os, 'close') as close_fd,
        ):
            self.assertIsNone(self.lease._validate_active())
            for observed in (*stream_calls.values(), acquire, release, open_fd, close_fd):
                observed.assert_not_called()
        self.assertEqual(self.lease.__dict__, before)
        self.assertEqual(stream.tell(), offset)
        self.assertEqual(self.lease.path.read_bytes(), payload)

    def test_other_process_remains_busy_after_check(self) -> None:
        self.lease._validate_active()
        environment = os.environ.copy()
        source = str(Path(__file__).resolve().parents[1] / 'src')
        environment['PYTHONPATH'] = source + os.pathsep + environment.get('PYTHONPATH', '')
        completed = subprocess.run(
            [sys.executable, '-c', CHILD, str(self.root)],
            env=environment, check=True, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(completed.stdout.strip(), 'busy')

    def test_invalid_fileno_values_are_rejected_before_identity(self) -> None:
        stream = self.lease._stream
        for value in (True, False, -1, 0, 1, 2, '3', None):
            with self.subTest(value=value):
                with (
                    mock.patch.object(stream, 'fileno', return_value=value),
                    mock.patch.object(workspace_module, '_validate_lock_file_identity') as identity,
                ):
                    self.assert_fixed(self.lease._validate_active)
                    identity.assert_not_called()
        self.assertFalse(stream.closed)

    def test_fileno_ordinary_failure_has_fixed_error(self) -> None:
        stream = self.lease._stream
        with mock.patch.object(stream, 'fileno', side_effect=OSError('private fd detail')):
            self.assert_fixed(self.lease._validate_active)

    def test_each_os_identity_observation_ordinary_failure_is_fixed(self) -> None:
        stream = self.lease._stream
        descriptor = stream.fileno()
        for name in ('lstat', 'fstat'):
            with self.subTest(observation=name):
                with mock.patch.object(
                    workspace_module.os, name, side_effect=OSError('private path detail'),
                ) as observation:
                    self.assert_fixed(self.lease._validate_active)
                    observation.assert_called_once()
                self.assertIs(self.lease._stream, stream)
                self.assertFalse(stream.closed)
                os.fstat(descriptor)

    def test_first_signal_original_object_is_preserved(self) -> None:
        stream = self.lease._stream
        descriptor = stream.fileno()
        for name in ('lstat', 'fstat'):
            for signal in (KeyboardInterrupt('stop'), SystemExit(23)):
                with self.subTest(observation=name, signal=type(signal).__name__):
                    with mock.patch.object(
                        workspace_module.os, name, side_effect=signal,
                    ) as observation:
                        with self.assertRaises(type(signal)) as caught:
                            self.lease._validate_active()
                        self.assertIs(caught.exception, signal)
                        observation.assert_called_once()
                    self.assertIs(self.lease._stream, stream)
                    self.assertFalse(stream.closed)
                    os.fstat(descriptor)


if __name__ == '__main__':
    unittest.main()
