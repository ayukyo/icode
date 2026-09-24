"""工具集测试（离线）。"""

from __future__ import annotations

import unittest
import hashlib
import os
from pathlib import Path
from unittest.mock import patch

from tests._support import temp_workspace

from icode.tools import OPCLASS_MANAGED_WRITE, OPCLASS_READ_ONLY, ToolContext, default_registry


class TestFileTools(unittest.TestCase):
    def setUp(self) -> None:
        self._ws = temp_workspace()
        self.root: Path = self._ws.__enter__()
        (self.root / "pkg").mkdir()
        (self.root / "pkg" / "m.py").write_text(
            "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n",
            encoding="utf-8",
        )
        (self.root / "pkg" / "note.txt").write_text("TODO: 补测试\n", encoding="utf-8")
        self.reg = default_registry()
        self.ctx = ToolContext(root=self.root)

    def tearDown(self) -> None:
        self._ws.__exit__(None, None, None)

    def test_读文件带行号(self) -> None:
        r = self.reg.invoke("read_file", self.ctx, {"path": "pkg/m.py"})
        self.assertTrue(r.ok)
        self.assertIn("1| def add", r.content)
        self.assertEqual(r.meta["total_lines"], 6)

    def test_分段读(self) -> None:
        r = self.reg.invoke("read_file", self.ctx, {"path": "pkg/m.py", "offset": 5, "limit": 2})
        self.assertTrue(r.ok)
        self.assertIn("def sub", r.content)
        self.assertIn("共 6 行", r.content)

    def test_读不存在文件(self) -> None:
        r = self.reg.invoke("read_file", self.ctx, {"path": "nope.py"})
        self.assertFalse(r.ok)
        self.assertEqual(r.meta["error"], "not_found")

    @unittest.skipUnless(os.name == "posix", "需要 POSIX 符号链接语义")
    def test_策略读文件不跟随工作区外链接(self) -> None:
        from icode.sandbox_policy import NetworkMode, SandboxPolicy

        with temp_workspace() as outside:
            secret = outside / "secret.txt"
            secret.write_text("PRIVATE_MARKER\n", encoding="utf-8")
            (self.root / "linked-secret.txt").symlink_to(secret)
            policy = SandboxPolicy(
                schema_version=1, run_id="run", ticket_id="ticket", step="code",
                workspace_root=self.root, read_roots=(self.root,), write_roots=(self.root,),
                deny_read_roots=(), deny_write_roots=(),
                network_mode=NetworkMode.DENY, allowed_domains=(), process_limit=8,
                wall_timeout_seconds=10, output_limit_bytes=1024, protected_paths=(),
            )
            result = self.reg.invoke("read_file", ToolContext(root=self.root, policy=policy),
                                     {"path": "linked-secret.txt"})
            self.assertFalse(result.ok)
            self.assertEqual(result.meta["error"], "read_denied")
            self.assertNotIn("PRIVATE_MARKER", result.content)
            (self.root / "linked-internal.py").symlink_to(self.root / "pkg" / "m.py")
            internal = self.reg.invoke("read_file", ToolContext(root=self.root, policy=policy),
                                       {"path": "linked-internal.py"})
            self.assertTrue(internal.ok)
            self.assertIn("def add", internal.content)

    def test_显式外部读文件工具兼容(self) -> None:
        with temp_workspace() as outside:
            source = outside / "note.txt"
            source.write_text("approved text\n", encoding="utf-8")
            result = self.reg.invoke("read_file", self.ctx, {"path": str(source)})
            self.assertTrue(result.ok)
            self.assertIn("approved text", result.content)

    def test_glob(self) -> None:
        r = self.reg.invoke("glob", self.ctx, {"pattern": "**/*.py"})
        self.assertTrue(r.ok)
        self.assertIn("pkg/m.py", r.content)

    def test_glob_拒绝父目录与绝对模式(self) -> None:
        inner = self.root / "inner"
        inner.mkdir()
        context = ToolContext(root=inner)
        secret = self.root / "outside-secret.py"
        secret.write_text("outside", encoding="utf-8")
        for pattern in ("../outside-secret.py", str(secret)):
            with self.subTest(pattern=pattern):
                result = self.reg.invoke("glob", context, {"pattern": pattern})
                self.assertFalse(result.ok)
                self.assertEqual(result.meta.get("error"), "invalid_pattern")
                self.assertNotIn("outside-secret.py", result.content)

    @unittest.skipUnless(os.name == "posix", "需要 POSIX 符号链接语义")
    def test_glob_不枚举链接指向的外部目录(self) -> None:
        with temp_workspace() as outside:
            (outside / "outside-secret.py").write_text("outside", encoding="utf-8")
            (self.root / "external").symlink_to(outside, target_is_directory=True)
            for pattern in ("external/*.py", "**/*.py"):
                with self.subTest(pattern=pattern):
                    result = self.reg.invoke("glob", self.ctx, {"pattern": pattern})
                    self.assertTrue(result.ok)
                    self.assertNotIn("outside-secret.py", result.content)
            self.assertIn("pkg/m.py", self.reg.invoke(
                "glob", self.ctx, {"pattern": "**/*.py"}
            ).content)

    def test_glob_保留递归匹配语义(self) -> None:
        (self.root / "pkg" / "deep").mkdir()
        (self.root / "pkg" / "deep" / "n.py").write_text("pass\n", encoding="utf-8")
        deep = self.reg.invoke("glob", self.ctx, {"pattern": "**/*.py"})
        self.assertEqual(deep.content.splitlines(), ["pkg/deep/n.py", "pkg/m.py"])
        shallow = self.reg.invoke("glob", self.ctx, {"pattern": "pkg/*.py"})
        self.assertEqual(shallow.content.splitlines(), ["pkg/m.py"])

    def test_glob_策略拒读目录不会列出(self) -> None:
        from icode.sandbox_policy import NetworkMode, SandboxPolicy

        denied = self.root / "private"
        denied.mkdir()
        (denied / "secret.py").write_text("pass\n", encoding="utf-8")
        policy = SandboxPolicy(
            schema_version=1, run_id="run", ticket_id="ticket", step="code",
            workspace_root=self.root, read_roots=(self.root,), write_roots=(self.root,),
            deny_read_roots=(denied,), deny_write_roots=(),
            network_mode=NetworkMode.DENY, allowed_domains=(), process_limit=8,
            wall_timeout_seconds=10, output_limit_bytes=1024, protected_paths=(),
        )
        result = self.reg.invoke("glob", ToolContext(root=self.root, policy=policy),
                                 {"pattern": "**/*.py"})
        self.assertTrue(result.ok)
        self.assertEqual(result.content.splitlines(), ["pkg/m.py"])

    def test_grep_返回_file_line(self) -> None:
        r = self.reg.invoke("grep", self.ctx, {"pattern": r"def \w+"})
        self.assertTrue(r.ok)
        self.assertIn("pkg/m.py:1:", r.content)

    @unittest.skipUnless(os.name == "posix", "需要 POSIX 符号链接语义")
    def test_grep_递归扫描不读取外部链接文件(self) -> None:
        with temp_workspace() as outside:
            secret = outside / "secret.txt"
            secret.write_text("LEAK_MARKER\n", encoding="utf-8")
            (self.root / "linked-secret.txt").symlink_to(secret)
            (self.root / "linked-dir").symlink_to(outside, target_is_directory=True)
            result = self.reg.invoke("grep", self.ctx, {"pattern": "LEAK_MARKER"})
            self.assertTrue(result.ok)
            self.assertEqual(result.meta["hits"], 0)
            self.assertNotIn("linked-secret.txt:", result.content)

    def test_grep_策略拒读目录不读取正文(self) -> None:
        from icode.sandbox_policy import NetworkMode, SandboxPolicy

        denied = self.root / "private"
        denied.mkdir()
        (denied / "secret.txt").write_text("PRIVATE_MARKER\n", encoding="utf-8")
        policy = SandboxPolicy(
            schema_version=1, run_id="run", ticket_id="ticket", step="code",
            workspace_root=self.root, read_roots=(self.root,), write_roots=(self.root,),
            deny_read_roots=(denied,), deny_write_roots=(),
            network_mode=NetworkMode.DENY, allowed_domains=(), process_limit=8,
            wall_timeout_seconds=10, output_limit_bytes=1024, protected_paths=(),
        )
        result = self.reg.invoke("grep", ToolContext(root=self.root, policy=policy),
                                 {"pattern": "PRIVATE_MARKER"})
        self.assertTrue(result.ok)
        self.assertEqual(result.meta["hits"], 0)
        explicit = self.reg.invoke("grep", ToolContext(root=self.root, policy=policy),
                                   {"pattern": "PRIVATE_MARKER", "path": "private"})
        self.assertFalse(explicit.ok)
        self.assertEqual(explicit.meta["error"], "read_denied")

    def test_grep_显式外部目录仍可扫描(self) -> None:
        with temp_workspace() as outside:
            (outside / "note.txt").write_text("APPROVED_MARKER\n", encoding="utf-8")
            result = self.reg.invoke("grep", self.ctx, {
                "pattern": "APPROVED_MARKER", "path": str(outside),
            })
            self.assertTrue(result.ok)
            self.assertEqual(result.meta["hits"], 1)
            self.assertIn("note.txt:1:", result.content)

    def test_grep_非法正则不炸(self) -> None:
        r = self.reg.invoke("grep", self.ctx, {"pattern": "([unclosed"})
        self.assertFalse(r.ok)
        self.assertEqual(r.meta["error"], "bad_regex")

    def test_写文件用LF(self) -> None:
        r = self.reg.invoke("write_file", self.ctx, {"path": "new/a.py", "content": "x = 1\ny = 2\n"})
        self.assertTrue(r.ok)
        self.assertEqual(r.opclass, OPCLASS_MANAGED_WRITE)
        self.assertNotIn(b"\r\n", (self.root / "new" / "a.py").read_bytes())

    @unittest.skipUnless(os.name == "posix", "需要 POSIX 符号链接语义")
    def test_写工具不改工作区外链接目标(self) -> None:
        with temp_workspace() as outside:
            secret = outside / "secret.txt"
            secret.write_text("before\n", encoding="utf-8")
            (self.root / "linked-secret.txt").symlink_to(secret)
            (self.root / "linked-dir").symlink_to(outside, target_is_directory=True)
            for tool, arguments in (
                ("write_file", {"path": "linked-secret.txt", "content": "after\n"}),
                ("write_file", {"path": "linked-dir/new.txt", "content": "after\n"}),
                ("edit_file", {"path": "linked-secret.txt", "old": "before", "new": "after"}),
            ):
                with self.subTest(tool=tool, path=arguments["path"]):
                    result = self.reg.invoke(tool, self.ctx, arguments)
                    self.assertFalse(result.ok)
                    self.assertEqual(result.meta["error"], "write_denied")
            self.assertEqual(secret.read_text(encoding="utf-8"), "before\n")
            self.assertFalse((outside / "new.txt").exists())

    def test_策略写工具拒绝受保护目录(self) -> None:
        from icode.sandbox_policy import NetworkMode, SandboxPolicy

        protected = self.root / ".git"
        protected.mkdir()
        config = protected / "config"
        config.write_text("before\n", encoding="utf-8")
        policy = SandboxPolicy(
            schema_version=1, run_id="run", ticket_id="ticket", step="code",
            workspace_root=self.root, read_roots=(self.root,), write_roots=(self.root,),
            deny_read_roots=(), deny_write_roots=(protected,),
            network_mode=NetworkMode.DENY, allowed_domains=(), process_limit=8,
            wall_timeout_seconds=10, output_limit_bytes=1024,
            protected_paths=(protected,),
        )
        context = ToolContext(root=self.root, policy=policy)
        for tool, arguments in (
            ("write_file", {"path": ".git/config", "content": "after\n"}),
            ("edit_file", {"path": ".git/config", "old": "before", "new": "after"}),
        ):
            with self.subTest(tool=tool):
                result = self.reg.invoke(tool, context, arguments)
                self.assertFalse(result.ok)
                self.assertEqual(result.meta["error"], "write_denied")
        self.assertEqual(config.read_text(encoding="utf-8"), "before\n")

    def test_策略编辑必须同时有读取权限(self) -> None:
        from icode.sandbox_policy import NetworkMode, SandboxPolicy

        private = self.root / "private"
        private.mkdir()
        target = private / "note.txt"
        target.write_text("before\n", encoding="utf-8")
        policy = SandboxPolicy(
            schema_version=1, run_id="run", ticket_id="ticket", step="code",
            workspace_root=self.root, read_roots=(self.root,), write_roots=(self.root,),
            deny_read_roots=(private,), deny_write_roots=(),
            network_mode=NetworkMode.DENY, allowed_domains=(), process_limit=8,
            wall_timeout_seconds=10, output_limit_bytes=1024, protected_paths=(),
        )
        result = self.reg.invoke("edit_file", ToolContext(root=self.root, policy=policy), {
            "path": "private/note.txt", "old": "before", "new": "after",
        })
        self.assertFalse(result.ok)
        self.assertEqual(result.meta["error"], "read_denied")
        self.assertEqual(target.read_text(encoding="utf-8"), "before\n")

    @unittest.skipUnless(os.name == "posix", "需要 POSIX 文件模式和硬链接语义")
    def test_安全覆盖保留模式且不修改外部硬链接目标(self) -> None:
        target = self.root / "executable.sh"
        target.write_text("old\n", encoding="utf-8")
        target.chmod(0o755)
        result = self.reg.invoke("write_file", self.ctx, {
            "path": "executable.sh", "content": "new\n",
        })
        self.assertTrue(result.ok)
        self.assertEqual(target.stat().st_mode & 0o777, 0o755)
        target.chmod(0o4755)
        replaced_mode = self.reg.invoke("write_file", self.ctx, {
            "path": "executable.sh", "content": "again\n",
        })
        self.assertTrue(replaced_mode.ok)
        self.assertEqual(target.stat().st_mode & 0o7777, 0o755)
        with temp_workspace() as outside:
            secret = outside / "secret.txt"
            secret.write_text("outside\n", encoding="utf-8")
            os.link(secret, self.root / "hardlink.txt")
            replaced = self.reg.invoke("write_file", self.ctx, {
                "path": "hardlink.txt", "content": "inside\n",
            })
            self.assertTrue(replaced.ok)
            self.assertEqual(secret.read_text(encoding="utf-8"), "outside\n")
            self.assertEqual((self.root / "hardlink.txt").read_text(encoding="utf-8"),
                             "inside\n")

    def test_edit_要求唯一匹配(self) -> None:
        ok = self.reg.invoke("edit_file", self.ctx, {
            "path": "pkg/m.py", "old": "return a + b", "new": "return a + b  # noqa"})
        self.assertTrue(ok.ok)

        missing = self.reg.invoke("edit_file", self.ctx, {
            "path": "pkg/m.py", "old": "不存在的片段", "new": "x"})
        self.assertFalse(missing.ok)
        self.assertEqual(missing.meta["error"], "no_match")

        ambiguous = self.reg.invoke("edit_file", self.ctx, {
            "path": "pkg/m.py", "old": "def ", "new": "def _"})
        self.assertFalse(ambiguous.ok)
        self.assertEqual(ambiguous.meta["error"], "not_unique")

    def test_未知工具给出可用清单(self) -> None:
        r = self.reg.invoke("rm_rf", self.ctx, {})
        self.assertFalse(r.ok)
        self.assertIn("可用：", r.content)

    def test_参数不合法被兜住(self) -> None:
        r = self.reg.invoke("read_file", self.ctx, {"unexpected": 1})
        self.assertFalse(r.ok)
        self.assertEqual(r.meta["error"], "bad_arguments")

    def test_schema_可用于_function_calling(self) -> None:
        schemas = self.reg.schemas()
        names = {s["function"]["name"] for s in schemas}
        self.assertIn("read_file", names)
        for s in schemas:
            self.assertEqual(s["type"], "function")
            self.assertIn("parameters", s["function"])


class TestRunCommand(unittest.TestCase):
    def setUp(self) -> None:
        self._ws = temp_workspace()
        self.root: Path = self._ws.__enter__()
        self.reg = default_registry()
        self.ctx = ToolContext(root=self.root)

    def tearDown(self) -> None:
        self._ws.__exit__(None, None, None)

    def test_执行并取退出码(self) -> None:
        import sys

        r = self.reg.invoke("run_command", self.ctx, {"argv": [sys.executable, "-c", "print('hi')"]})
        self.assertTrue(r.ok)
        self.assertEqual(r.meta["exit_code"], 0)
        self.assertIn("hi", r.content)

    def test_非零退出码被如实反映(self) -> None:
        import sys

        r = self.reg.invoke("run_command", self.ctx, {"argv": [sys.executable, "-c", "raise SystemExit(3)"]})
        self.assertFalse(r.ok)
        self.assertEqual(r.meta["exit_code"], 3)

    def test_执行工具本身拒绝非字符串参数(self) -> None:
        with patch("subprocess.run") as spawned:
            for bad in ({"python": "-V"}, ["python", 1], ["python", None],
                        ["", "python"], ["python", "\x00"], 'python "', 7):
                with self.subTest(argv=bad):
                    result = self.reg.invoke("run_command", self.ctx, {"argv": bad})
                    self.assertFalse(result.ok)
                    self.assertEqual(result.meta["error"], "invalid_argv")
            spawned.assert_not_called()

    def test_只读命令归类为_read_only(self) -> None:
        r = self.reg.invoke("run_command", self.ctx, {"argv": ["git", "status"]})
        self.assertEqual(r.opclass, OPCLASS_READ_ONLY)

    def test_git_写操作不算只读(self) -> None:
        r = self.reg.invoke("run_command", self.ctx, {"argv": ["git", "commit", "-m", "x"]})
        self.assertEqual(r.opclass, OPCLASS_MANAGED_WRITE)

    def test_策略工作区改动清单不调用_git(self) -> None:
        (self.root / "modified.txt").write_text("before", encoding="utf-8")
        (self.root / "removed.txt").write_text("removed", encoding="utf-8")
        baseline = {
            name: hashlib.sha256((self.root / name).read_bytes()).hexdigest()
            for name in ("modified.txt", "removed.txt")
        }
        (self.root / "modified.txt").write_text("after", encoding="utf-8")
        (self.root / "removed.txt").unlink()
        (self.root / "added.txt").write_text("added", encoding="utf-8")
        self.ctx.change_baseline = baseline
        registry = default_registry(include_changes=True)
        with patch("subprocess.run", side_effect=AssertionError("Git must not run")):
            result = registry.invoke("workspace_changes", self.ctx, {})
        self.assertTrue(result.ok, result.content)
        self.assertEqual(result.opclass, OPCLASS_READ_ONLY)
        self.assertIn("A added.txt", result.content)
        self.assertIn("M modified.txt", result.content)
        self.assertIn("D removed.txt", result.content)

    def test_分层策略工作区拒绝普通_git_命令(self) -> None:
        from icode.sandbox_policy import NetworkMode, SandboxPolicy
        from icode.isolation import NoIsolation

        checkout = self.root / "checkout"
        code = checkout / "code"
        code.mkdir(parents=True)
        protected = checkout / ".git"
        protected.write_text("gitdir: protected\n", encoding="utf-8")
        policy = SandboxPolicy(
            schema_version=1, run_id="run", ticket_id="ticket", step="code",
            workspace_root=code, read_roots=(code,), write_roots=(code,),
            deny_read_roots=(), deny_write_roots=(protected,),
            network_mode=NetworkMode.DENY, allowed_domains=(), process_limit=8,
            wall_timeout_seconds=10, output_limit_bytes=1024,
            protected_paths=(protected,),
        )
        context = ToolContext(root=code, sandbox=NoIsolation(), policy=policy)
        for command in ("status", "diff"):
            with self.subTest(command=command):
                result = self.reg.invoke("run_command", context, {"argv": ["git", command]})
                self.assertFalse(result.ok)
                self.assertEqual(result.meta.get("error"), "git_broker_unavailable")


if __name__ == "__main__":
    unittest.main()
