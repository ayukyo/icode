from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock

from scripts import preflight


class TestPreflightFileDiscovery(TestCase):
    def test_secret_scan_file_discovery_prunes_private_playwright_runtime(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            tracked_file = root / "src" / "safe.py"
            tracked_file.parent.mkdir()
            tracked_file.write_text("safe = True\n", encoding="utf-8")
            private_file = root / ".playwright-mcp" / "private.txt"
            private_file.parent.mkdir()
            private_file.write_text("private runtime data\n", encoding="utf-8")

            walked_directories: list[Path] = []
            real_walk = os.walk

            def recording_walk(*args: object, **kwargs: object):
                for current, directories, filenames in real_walk(*args, **kwargs):
                    walked_directories.append(Path(current).relative_to(root))
                    yield current, directories, filenames

            with (
                mock.patch.object(preflight, "REPO", root),
                mock.patch.object(preflight.os, "walk", side_effect=recording_walk),
            ):
                discovered = preflight._iter_files()

            self.assertEqual(discovered, [tracked_file])
            self.assertNotIn(Path(".playwright-mcp"), walked_directories)

    def test_secret_scan_file_discovery_keeps_regular_file_symlinks(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target.txt"
            target.write_text("synthetic test fixture\n", encoding="utf-8")
            link = root / "src" / "linked.txt"
            link.parent.mkdir()
            try:
                link.symlink_to(target)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"file symlinks unavailable: {exc}")

            with mock.patch.object(preflight, "REPO", root):
                discovered = preflight._iter_files()

            self.assertIn(link, discovered)
