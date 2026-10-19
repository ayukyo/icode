"""区域写租约：重叠拒绝、相异并行、跨进程锁、控制面消毒（R6/W2）。"""

import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from icode.write_lease import (
    LeaseBusy,
    LeaseError,
    WriteLeaseBoard,
    normalize_region,
    regions_overlap,
)

_HOLD_SCRIPT = (
    "import sys, time\n"
    "sys.path.insert(0, {src!r})\n"
    "from icode.write_lease import WriteLeaseBoard\n"
    "board = WriteLeaseBoard({lease_dir!r})\n"
    "lease = board.acquire(('src',), 'external-holder')\n"
    "print('held', flush=True)\n"
    "time.sleep(6)\n"
)


class TestRegionNormalization(unittest.TestCase):
    def test_合法区域规范化为段元组(self) -> None:
        self.assertEqual(normalize_region("src/core"), ("src", "core"))
        self.assertEqual(normalize_region("src\\core"), ("src", "core"))

    def test_非法区域拒绝(self) -> None:
        for region in ("", "/abs/path", "/src/core/", "../escape", "a/../b", "C:/x",
                       ".ico_events.jsonl", "x/../../y", None, "a b"):
            with self.subTest(region=region):
                with self.assertRaises(LeaseError):
                    normalize_region(region)

    def test_重叠判定是前缀相关(self) -> None:
        self.assertTrue(regions_overlap(("src",), ("src", "core")))
        self.assertTrue(regions_overlap(("src", "core"), ("src",)))
        self.assertTrue(regions_overlap(("src",), ("src",)))
        self.assertFalse(regions_overlap(("src",), ("tests",)))


class TestLeaseBoard(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.board = WriteLeaseBoard(Path(self._tmp.name) / "leases")
        self.addCleanup(self._tmp.cleanup)

    def test_相异区域可并行持有(self) -> None:
        first = self.board.acquire(("src",), "executor#T#1")
        second = self.board.acquire(("tests",), "executor#T#2")
        self.assertEqual(self.board.holders(), {
            "src": ["executor#T#1"], "tests": ["executor#T#2"],
        })
        first.release()
        second.release()
        self.assertEqual(self.board.holders(), {})

    def test_重叠区域第二个获取者被拒且原持有不受影响(self) -> None:
        first = self.board.acquire(("src",), "executor#T#1")
        for region in (("src",), ("src", "core")):
            with self.subTest(region=region):
                with self.assertRaises(LeaseBusy):
                    self.board.acquire(region, "executor#T#2")
        self.assertEqual(self.board.holders()["src"], ["executor#T#1"])
        first.release()
        # 释放后同区域可再获取
        again = self.board.acquire(("src",), "executor#T#2")
        again.release()

    def test_释放后区域立即可复用且释放幂等(self) -> None:
        lease = self.board.acquire(("src",), "executor#T#1")
        lease.release()
        lease.release()
        again = self.board.acquire(("src",), "executor#T#2")
        again.release()

    def test_异常退出时with块保证回收(self) -> None:
        try:
            with self.board.acquire(("src",), "executor#T#1"):
                raise RuntimeError("工作失败")
        except RuntimeError:
            pass
        again = self.board.acquire(("src",), "executor#T#2")
        again.release()

    def test_非法持有者与非法区域拒绝(self) -> None:
        with self.assertRaises(LeaseError):
            self.board.acquire(("src",), "")
        with self.assertRaises(LeaseError):
            self.board.acquire("../escape", "executor#T#1")

    def test_线程竞争只允许一个持有者(self) -> None:
        outcomes: list[str] = []
        lock = threading.Lock()

        def worker(index: int) -> None:
            try:
                self.board.acquire(("src",), f"executor#T#{index}")
                with lock:
                    outcomes.append("won")
            except LeaseBusy:
                with lock:
                    outcomes.append("busy")

        threads = [threading.Thread(target=worker, args=(index,))
                   for index in range(1, 5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(outcomes.count("won"), 1)
        self.assertEqual(outcomes.count("busy"), 3)


class TestCrossProcessLease(unittest.TestCase):
    def test_跨进程锁竞争被拒(self) -> None:
        import os
        with tempfile.TemporaryDirectory() as tmp:
            lease_dir = str(Path(tmp) / "leases")
            repo_src = str(Path(__file__).resolve().parent.parent / "src")
            script = _HOLD_SCRIPT.format(src=repo_src, lease_dir=lease_dir)
            child = subprocess.Popen(
                [sys.executable, "-c", script],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            try:
                line = child.stdout.readline().strip()  # 等待子进程持锁
                self.assertEqual(line, "held")
                board = WriteLeaseBoard(Path(lease_dir))
                with self.assertRaises(LeaseBusy):
                    board.acquire(("src",), "executor#T#1")
            finally:
                child.terminate()
                child.wait(timeout=10)
            # 子进程退出后锁释放，可再获取
            board = WriteLeaseBoard(Path(lease_dir))
            lease = board.acquire(("src",), "executor#T#1")
            lease.release()


if __name__ == "__main__":
    unittest.main()
