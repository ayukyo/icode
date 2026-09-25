from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from icode.git_status import GitStatusParseError, parse_porcelain_v2


class TestPorcelainV2Parser(unittest.TestCase):
    def test_clean_output_is_empty(self) -> None:
        self.assertEqual(parse_porcelain_v2(b""), ())

    def test_parses_output_from_real_git(self) -> None:
        git = shutil.which("git")
        if git is None:
            self.skipTest("需要 Git CLI 验证真实 porcelain-v2 输出")

        with tempfile.TemporaryDirectory(prefix="icode-git-status-") as raw:
            root = Path(raw)

            def run_git(*args: str) -> bytes:
                result = subprocess.run(
                    [git, *args], cwd=root, capture_output=True, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
                return result.stdout

            run_git("init", "--quiet")
            (root / "tracked.txt").write_text("before\n", encoding="utf-8")
            run_git("add", "--", "tracked.txt")
            run_git(
                "-c", "user.name=ICODE test", "-c", "user.email=icode@example.invalid",
                "commit", "--quiet", "-m", "baseline",
            )
            (root / "tracked.txt").write_text("after\n", encoding="utf-8")
            (root / "new file.txt").write_text("untracked\n", encoding="utf-8")

            entries = parse_porcelain_v2(
                run_git("status", "--porcelain=v2", "-z", "--untracked-files=all"),
            )

        self.assertEqual(
            {(entry.kind, entry.path) for entry in entries},
            {("tracked", b"tracked.txt"), ("untracked", b"new file.txt")},
        )

    def test_accepts_intent_to_add_status_from_real_git(self) -> None:
        git = shutil.which("git")
        if git is None:
            self.skipTest("需要 Git CLI 验证真实 porcelain-v2 输出")

        with tempfile.TemporaryDirectory(prefix="icode-git-intent-to-add-") as raw:
            root = Path(raw)

            def run_git(*args: str) -> bytes:
                result = subprocess.run(
                    [git, *args], cwd=root, capture_output=True, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
                return result.stdout

            run_git("init", "--quiet")
            (root / "intent.txt").write_text("intent\n", encoding="utf-8")
            run_git("add", "--intent-to-add", "--", "intent.txt")
            entries = parse_porcelain_v2(
                run_git("status", "--porcelain=v2", "-z", "--untracked-files=all"),
            )

        self.assertEqual(len(entries), 1)
        self.assertEqual((entries[0].path, entries[0].index_status, entries[0].worktree_status),
                         (b"intent.txt", ".", "A"))

    def test_tracked_path_keeps_xy_and_arbitrary_path_bytes(self) -> None:
        oid = b"a" * 40
        path = b"space and\nnewline-\xff.txt"
        output = (
            b"1 M. N... 100644 100644 100644 " + oid + b" " + oid + b" " + path + b"\0"
        )

        entries = parse_porcelain_v2(output)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].path, path)
        self.assertEqual(entries[0].kind, "tracked")
        self.assertEqual((entries[0].index_status, entries[0].worktree_status), ("M", "."))
        self.assertIsNone(entries[0].original_path)
        self.assertEqual(entries[0].submodule_status, b"N...")

    def test_submodule_state_is_preserved_for_broker_fail_closed(self) -> None:
        oid = b"a" * 40
        output = (
            b"1 .M S.M. 160000 160000 160000 "
            + oid + b" " + oid + b" modules/dependency\0"
        )

        entries = parse_porcelain_v2(output)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].path, b"modules/dependency")
        self.assertEqual(entries[0].submodule_status, b"S.M.")

    def test_rename_consumes_second_nul_terminated_path(self) -> None:
        oid = b"b" * 40
        output = (
            b"2 R. N... 100644 100644 100644 " + oid + b" " + oid
            + b" R100 new name\0old\nname\0"
        )

        entries = parse_porcelain_v2(output)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].path, b"new name")
        self.assertEqual(entries[0].original_path, b"old\nname")
        self.assertEqual((entries[0].index_status, entries[0].worktree_status), ("R", "."))

    def test_unmerged_untracked_and_unknown_headers(self) -> None:
        oid = b"c" * 64
        output = (
            b"# future.header value\0"
            + b"u UU N... 100644 100644 100644 100644 "
            + oid + b" " + oid + b" " + oid + b" conflict\0"
            + b"? new file\0"
        )

        entries = parse_porcelain_v2(output)

        self.assertEqual([entry.kind for entry in entries], ["unmerged", "untracked"])
        self.assertEqual(entries[0].path, b"conflict")
        self.assertEqual((entries[0].index_status, entries[0].worktree_status), ("U", "U"))
        self.assertEqual(entries[1].path, b"new file")
        self.assertIsNone(entries[1].index_status)

    def test_ignored_record_is_preserved_as_distinct_kind(self) -> None:
        entries = parse_porcelain_v2(b"! ignored file\0")
        self.assertEqual(len(entries), 1)
        self.assertEqual((entries[0].kind, entries[0].path), ("ignored", b"ignored file"))

    def test_all_documented_tracked_xy_status_shapes_are_accepted(self) -> None:
        oid = b"e" * 40
        valid_statuses = (
            "M.", "MM", "MT", "MD", "T.", "TM", "TT", "TD",
            "A.", "AM", "AT", "AD", "D.", "R.", "RM", "RT", "RD",
            "C.", "CM", "CT", "CD", ".M", ".T", ".D", ".R", ".C",
        )
        for status in valid_statuses:
            with self.subTest(status=status):
                output = (
                    b"1 " + status.encode("ascii")
                    + b" N... 100644 100644 100644 " + oid + b" " + oid + b" file\0"
                )
                self.assertEqual(len(parse_porcelain_v2(output)), 1)

    def test_accepts_documented_file_modes_including_sparse_index_and_deletion(self) -> None:
        oid = b"f" * 40
        for mode in (b"000000", b"040000", b"100644", b"100755", b"120000", b"160000"):
            with self.subTest(mode=mode):
                output = (
                    b"1 M. N... " + mode + b" " + mode + b" " + mode
                    + b" " + oid + b" " + oid + b" path\0"
                )
                self.assertEqual(len(parse_porcelain_v2(output)), 1)

    def test_malformed_or_truncated_stream_fails_closed(self) -> None:
        malformed = (
            b"#\0",
            b"1 M. N... 100644 100644 100644 " + b"d" * 40 + b" " + b"d" * 40 + b" path",
            b"2 R. N... 100644 100644 100644 " + b"d" * 40 + b" " + b"d" * 40 + b" R100 new\0",
            b"1 Z. N... 100644 100644 100644 " + b"d" * 40 + b" " + b"d" * 40 + b" path\0",
            b"1 DA N... 100644 100644 100644 " + b"d" * 40 + b" " + b"d" * 40 + b" path\0",
            b"1 DD N... 100644 100644 100644 " + b"d" * 40 + b" " + b"d" * 40 + b" path\0",
            b"1 M. N... 10064x 100644 100644 " + b"d" * 40 + b" " + b"d" * 40 + b" path\0",
            b"1 M. N... 777777 777777 777777 " + b"d" * 40 + b" " + b"d" * 40 + b" path\0",
            b"1 M. N... 100644 100644 100644 " + b"d" * 40 + b" " + b"d" * 39 + b" path\0",
            b"? \0",
            b"x unsupported\0",
            b"u UU N... 100644 100644 100644 100644 " + b"d" * 40 + b" " + b"d" * 40 + b" path\0",
        )
        for output in malformed:
            with self.subTest(output=output[:24]):
                with self.assertRaises(GitStatusParseError):
                    parse_porcelain_v2(output)


if __name__ == "__main__":
    unittest.main()
