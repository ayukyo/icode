"""持续研究记录的日期门禁；不把日期检查当作源码复核。"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

from tests._support import temp_workspace


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_agent_landscape.py"


def _document(next_review: str, *, projects: int = 20,
              observed: str = "2026-09-24") -> str:
    rows = "\n".join(
        f"| 编码 Agent | [Project {index}](https://example.org/{index}) | 关注 | 观察 |"
        for index in range(projects)
    )
    return (
        "# 开源 AI Agent 持续对照与借鉴记录\n\n"
        f"- 最近观察：{observed}；下次全量复核：不晚于 {next_review}\n\n"
        "## 20 个观察对象\n\n"
        "| 分组 | 项目 | 本次关注点 | 证据深度 |\n"
        "|---|---|---|---|\n"
        f"{rows}\n\n"
        "## 本次深读的版本锚点\n"
    )


class TestAgentLandscapeRefresh(unittest.TestCase):
    def _run(self, document: str, *args: str) -> subprocess.CompletedProcess[str]:
        with temp_workspace() as root:
            path = root / "landscape.md"
            path.write_text(document, encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(SCRIPT), "--document", str(path), *args],
                capture_output=True, text=True, check=False,
            )

    def test_复核日当天仍有效(self) -> None:
        result = self._run(_document("2026-10-24"), "--today", "2026-10-24")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("20", result.stdout)

    def test_逾期定时检查失败而日常开发仅提示(self) -> None:
        document = _document("2026-10-24")
        strict = self._run(document, "--today", "2026-10-25")
        self.assertEqual(strict.returncode, 1, strict.stdout + strict.stderr)
        self.assertIn("逾期", strict.stderr)
        advisory = self._run(document, "--today", "2026-10-25", "--warn-only")
        self.assertEqual(advisory.returncode, 0, advisory.stderr)
        self.assertIn("逾期", advisory.stderr)

    def test_日期无效或观察名单不满二十项不可伪装有效(self) -> None:
        invalid_date = self._run(_document("not-a-date"), "--today", "2026-09-24")
        self.assertEqual(invalid_date.returncode, 1)
        short_list = self._run(_document("2026-10-24", projects=19),
                               "--today", "2026-09-24")
        self.assertEqual(short_list.returncode, 1)

    def test_未来观察日期不能延后到期提醒(self) -> None:
        result = self._run(
            _document("2026-11-24", observed="2026-10-25"),
            "--today", "2026-10-24",
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("未来", result.stderr)


if __name__ == "__main__":
    unittest.main()
