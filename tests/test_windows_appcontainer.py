"""R2.3 AppContainer 文件/网络边界实验；不是生产后端 ready 证明。"""

from __future__ import annotations

import ctypes
import hashlib
import http.client
import http.server
import json
import ntpath
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import sysconfig
import tempfile
import threading
import time
import unittest
from collections.abc import Callable
from unittest import mock
from urllib.parse import urlsplit

import icode.windows_appcontainer as windows_appcontainer
from icode.windows_appcontainer import (
    _AppContainerSetupError,
    _delete_appcontainer_profile,
    _get_appcontainer_localappdata_path,
)
from icode.windows_appcontainer import _walk_workspace, run_windows_appcontainer
from icode.windows_job import (
    _append_windows_environment_value,
    _build_windows_environment_block,
    WindowsJobResult,
    run_windows_job,
)


class TestWindowsAppContainer(unittest.TestCase):
    def test_staging诊断只物化根内链接且保留源运行时不变(self) -> None:
        stage_runtime = getattr(
            windows_appcontainer, "_copy_runtime_tree_for_diagnostic", None,
        )
        self.assertTrue(callable(stage_runtime), "缺少 runtime staging 诊断入口")
        if not callable(stage_runtime):
            return
        with tempfile.TemporaryDirectory(prefix="icode-runtime-stage-test-") as raw:
            root = Path(raw)
            source = root / "runtime"
            source.mkdir()
            real = source / "python-real.exe"
            real.write_bytes(b"known interpreter bytes")
            link = source / "python.exe"
            try:
                link.symlink_to(real.name)
            except OSError as exc:
                self.skipTest(f"当前文件系统不支持符号链接测试：{exc}")

            destination = root / "icode-runtime-staging-copy"
            summary = stage_runtime(source, destination)

            self.assertEqual(summary["materialized_links"], 1)
            self.assertEqual((destination / "python.exe").read_bytes(), real.read_bytes())
            self.assertFalse((destination / "python.exe").is_symlink())
            self.assertTrue(link.is_symlink())
            self.assertEqual(windows_appcontainer._runtime_reparse_inventory(destination)["symbolic_link"], 0)

    def test_stagingACL诊断只接受runner临时目录中的专用根(self) -> None:
        validate_roots = getattr(
            windows_appcontainer, "_validate_diagnostic_runtime_roots", None,
        )
        self.assertTrue(callable(validate_roots), "缺少 staging ACL 诊断根验证器")
        if not callable(validate_roots):
            return
        with tempfile.TemporaryDirectory(prefix="icode-runtime-staging-test-") as raw:
            parent = Path(raw)
            workspace = parent / "task"
            workspace.mkdir()
            staging = parent / "icode-runtime-staging-copy"
            staging.mkdir()
            executable = staging / "python.exe"
            executable.write_bytes(b"native executable placeholder")
            self.assertEqual(
                validate_roots(
                    (staging,), executable=executable, workspace=workspace,
                ),
                (staging.resolve(),),
            )

            ordinary = parent / "runtime"
            ordinary.mkdir()
            with self.assertRaises(_AppContainerSetupError):
                validate_roots(
                    (ordinary,), executable=ordinary / "python.exe", workspace=workspace,
                )
            with self.assertRaises(_AppContainerSetupError):
                validate_roots(
                    (staging,), executable=ordinary / "python.exe", workspace=workspace,
                )

    def test显式staging根不能绕过ACL诊断门(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-staging-gate-") as raw:
            result = run_windows_appcontainer(
                [sys.executable], cwd=raw, timeout_seconds=1,
                _diagnostic_runtime_roots=(Path(raw),),
            )
        self.assertEqual(result.error, "invalid_diagnostic_probe")

    def test_staging诊断拒绝根外链接且不创建副本(self) -> None:
        stage_runtime = getattr(
            windows_appcontainer, "_copy_runtime_tree_for_diagnostic", None,
        )
        self.assertTrue(callable(stage_runtime), "缺少 runtime staging 诊断入口")
        if not callable(stage_runtime):
            return
        with tempfile.TemporaryDirectory(prefix="icode-runtime-stage-outside-") as raw:
            root = Path(raw)
            source = root / "runtime"
            source.mkdir()
            outside = root / "outside.bin"
            outside.write_bytes(b"private")
            link = source / "python.exe"
            try:
                link.symlink_to(outside)
            except OSError as exc:
                self.skipTest(f"当前文件系统不支持符号链接测试：{exc}")
            destination = root / "icode-runtime-staging-copy"

            with self.assertRaises(_AppContainerSetupError) as raised:
                stage_runtime(source, destination)

            self.assertEqual(raised.exception.error, "runtime_staging_unsafe_reparse")
            self.assertFalse(destination.exists())
            self.assertEqual(outside.read_bytes(), b"private")

    def test_staging诊断拒绝非专用或临时目录外目标(self) -> None:
        stage_runtime = getattr(
            windows_appcontainer, "_copy_runtime_tree_for_diagnostic", None,
        )
        self.assertTrue(callable(stage_runtime), "缺少 runtime staging 诊断入口")
        if not callable(stage_runtime):
            return
        with tempfile.TemporaryDirectory(prefix="icode-runtime-stage-target-") as raw:
            root = Path(raw)
            source = root / "runtime"
            source.mkdir()
            (source / "python.exe").write_bytes(b"runtime")
            destinations = (
                root / "ordinary-directory-name",
                Path(tempfile.gettempdir()).resolve().parent
                / f"icode-runtime-staging-outside-{os.getpid()}",
            )
            for destination in destinations:
                with self.subTest(destination_kind="named" if destination.parent == root else "outside"):
                    with self.assertRaises(_AppContainerSetupError) as raised:
                        stage_runtime(source, destination)
                    self.assertEqual(raised.exception.error, "runtime_staging_copy_failed")
                    self.assertFalse(destination.exists())

    def test_staging诊断拒绝目录链接避免递归复制(self) -> None:
        stage_runtime = getattr(
            windows_appcontainer, "_copy_runtime_tree_for_diagnostic", None,
        )
        self.assertTrue(callable(stage_runtime), "缺少 runtime staging 诊断入口")
        if not callable(stage_runtime):
            return
        with tempfile.TemporaryDirectory(prefix="icode-runtime-stage-dirlink-") as raw:
            root = Path(raw)
            source = root / "runtime"
            source.mkdir()
            target = source / "target"
            target.mkdir()
            (target / "sentinel.bin").write_bytes(b"inside")
            alias = source / "target-alias"
            try:
                alias.symlink_to(target, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"当前文件系统不支持目录符号链接测试：{exc}")
            destination = root / "icode-runtime-staging-copy"

            with self.assertRaises(_AppContainerSetupError) as raised:
                stage_runtime(source, destination)

            self.assertEqual(raised.exception.error, "runtime_staging_unsafe_reparse")
            self.assertFalse(destination.exists())
            self.assertEqual((target / "sentinel.bin").read_bytes(), b"inside")

    def test_staging诊断拒绝词法根内的链接循环(self) -> None:
        stage_runtime = getattr(
            windows_appcontainer, "_copy_runtime_tree_for_diagnostic", None,
        )
        self.assertTrue(callable(stage_runtime), "缺少 runtime staging 诊断入口")
        if not callable(stage_runtime):
            return
        with tempfile.TemporaryDirectory(prefix="icode-runtime-stage-link-chain-") as raw:
            root = Path(raw)
            source = root / "runtime"
            source.mkdir()
            first_link = source / "first-link.bin"
            second_link = source / "second-link.bin"
            try:
                first_link.symlink_to(second_link.name)
                second_link.symlink_to(first_link.name)
            except OSError as exc:
                self.skipTest(f"当前文件系统不支持符号链接测试：{exc}")
            destination = root / "icode-runtime-staging-copy"

            with self.assertRaises(_AppContainerSetupError) as raised:
                stage_runtime(source, destination)

            self.assertEqual(raised.exception.error, "runtime_staging_unsafe_reparse")
            self.assertFalse(destination.exists())

    def test_reparse点原因映射为固定脱敏类别(self) -> None:
        symlink_mode = mock.Mock(st_mode=stat.S_IFLNK, st_reparse_tag=0)
        junction_tag = getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", 0xA0000003)
        symlink_tag = getattr(stat, "IO_REPARSE_TAG_SYMLINK", 0xA000000C)
        junction = mock.Mock(st_mode=stat.S_IFDIR, st_reparse_tag=junction_tag)
        symlink = mock.Mock(st_mode=stat.S_IFREG, st_reparse_tag=symlink_tag)
        unknown = mock.Mock(st_mode=stat.S_IFDIR, st_reparse_tag=0x12345678)

        self.assertEqual(windows_appcontainer._reparse_kind(symlink_mode), "symbolic_link")
        self.assertEqual(windows_appcontainer._reparse_kind(junction), "mount_point")
        self.assertEqual(windows_appcontainer._reparse_kind(symlink), "symbolic_link")
        self.assertEqual(windows_appcontainer._reparse_kind(unknown), "other_reparse")

    def test_reparse目标关系诊断只返回固定路径关系类别(self) -> None:
        self.assertEqual(
            windows_appcontainer._classify_runtime_link_target(
                "python311.exe", r"C:\hostedtoolcache\windows\Python\3.11\x64",
                r"C:\hostedtoolcache\windows\Python\3.11\x64", windows=True,
            ),
            "inside_root",
        )
        self.assertEqual(
            windows_appcontainer._classify_runtime_link_target(
                r"..\outside\python311.exe",
                r"C:\hostedtoolcache\windows\Python\3.11\x64",
                r"C:\hostedtoolcache\windows\Python\3.11\x64", windows=True,
            ),
            "outside_root",
        )
        self.assertEqual(
            windows_appcontainer._classify_runtime_link_target(
                r"\\build-share\python\python.exe",
                r"C:\hostedtoolcache\windows\Python\3.11\x64",
                r"C:\hostedtoolcache\windows\Python\3.11\x64", windows=True,
            ),
            "outside_root",
        )
        self.assertEqual(
            windows_appcontainer._classify_runtime_link_target(
                r"\??\Volume{1234}\python.exe",
                r"C:\hostedtoolcache\windows\Python\3.11\x64",
                r"C:\hostedtoolcache\windows\Python\3.11\x64", windows=True,
            ),
            "unknown",
        )
        self.assertEqual(
            windows_appcontainer._classify_runtime_link_target(
                r"\\?\C:\hostedtoolcache\windows\Python\3.11\x64\python311.exe",
                r"C:\hostedtoolcache\windows\Python\3.11\x64",
                r"C:\hostedtoolcache\windows\Python\3.11\x64", windows=True,
            ),
            "inside_root",
        )

    def test_runtime重解析清点不跟随链接且不输出目标(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-runtime-reparse-inventory-") as raw:
            parent = Path(raw)
            runtime = parent / "python"
            runtime.mkdir()
            workspace = parent / "task"
            workspace.mkdir()
            internal_target = runtime / "python-real.exe"
            internal_target.write_bytes(b"inside")
            external_target = parent / "outside.exe"
            external_target.write_bytes(b"outside")
            external_directory = parent / "outside-runtime"
            external_directory.mkdir()
            (external_directory / "sentinel.exe").write_bytes(b"outside")
            links = (
                runtime / "python.exe", runtime / "helper.exe",
                runtime / "vendor",
            )
            try:
                links[0].symlink_to(internal_target)
                links[1].symlink_to(external_target)
                links[2].symlink_to(external_directory, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"文件系统不支持符号链接清点测试：{exc}")

            summary = windows_appcontainer._runtime_reparse_inventory(runtime)

        self.assertEqual(summary["entries"], 4)
        self.assertEqual(summary["symbolic_link"], 3)
        self.assertEqual(summary["link_target_inside_root"], 1)
        self.assertEqual(summary["link_target_outside_root"], 2)
        self.assertEqual(summary["link_target_unknown"], 0)
        self.assertNotIn(str(parent), repr(summary))

        with tempfile.TemporaryDirectory(prefix="icode-runtime-reparse-inventory-limit-") as raw:
            root = Path(raw)
            (root / "first").write_text("1", encoding="utf-8")
            (root / "second").write_text("2", encoding="utf-8")
            with self.assertRaises(_AppContainerSetupError):
                windows_appcontainer._runtime_reparse_inventory(root, max_entries=1)
            with self.assertRaises(_AppContainerSetupError):
                windows_appcontainer._runtime_reparse_inventory(
                    root, deadline=time.monotonic() - 1,
                )

    @unittest.skipUnless(
        sys.platform == "win32"
        and os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("RUNNER_OS") == "Windows"
        and os.environ.get("ICODE_DIAGNOSTIC_RUNTIME_REPARSE_INVENTORY") == "true",
        "运行时 reparse 清点只在单独启用的 Windows Actions 诊断步骤执行",
    )
    def test_诊断Python运行时重解析目标关系(self) -> None:
        roots = tuple(dict.fromkeys((Path(sys.prefix), Path(sys.base_prefix))))
        summary = {
            "root_count": len(roots),
            "entries": 0,
            "symbolic_link": 0,
            "mount_point": 0,
            "other_reparse": 0,
            "link_target_inside_root": 0,
            "link_target_outside_root": 0,
            "link_target_unknown": 0,
        }
        for root in roots:
            observed = windows_appcontainer._runtime_reparse_inventory(root)
            for name, count in observed.items():
                summary[name] += count
        self._workflow_notice(
            "Python runtime reparse inventory (path-free lexical relation)",
            json.dumps(summary, ensure_ascii=True, separators=(",", ":")),
        )

    def test_runtime根在触碰文件系统前识别UNC路径(self) -> None:
        self.assertTrue(
            windows_appcontainer._is_unc_runtime_root(
                r"\\build-share\python\3.12", windows=True,
            ),
        )
        self.assertTrue(
            windows_appcontainer._is_unc_runtime_root(
                "//build-share/python/3.12", windows=True,
            ),
        )
        self.assertFalse(
            windows_appcontainer._is_unc_runtime_root(
                r"C:\hostedtoolcache\Python\3.12", windows=True,
            ),
        )
        self.assertFalse(
            windows_appcontainer._is_unc_runtime_root(
                r"\\build-share\python\3.12", windows=False,
            ),
        )

    def test_workspace_DACL读取不要求运行时快照对象标识(self) -> None:
        snapshot = windows_appcontainer._DaclSnapshot(
            path=Path("runtime"), dacl=b"dacl", control=0, revision=1,
            present=True, defaulted=False, file_identity=(1, 0),
        )
        with mock.patch.object(
            windows_appcontainer, "_read_dacl_state", return_value=snapshot,
        ) as read_state:
            dacl, protected = windows_appcontainer._read_dacl(
                Path("runtime"), object(), object(),
            )
        self.assertEqual(dacl, b"dacl")
        self.assertFalse(protected)
        self.assertEqual(read_state.call_args.args[0], Path("runtime"))

    def _workflow_notice(self, name: str, detail: str) -> None:
        """Expose only bounded probe outcomes in public Actions annotations."""
        if os.environ.get("GITHUB_ACTIONS") != "true":
            return
        safe_detail = detail[:500].replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::notice title=R2.3 {name}::{safe_detail}", flush=True)

    def _workflow_json_notice(self, name: str, detail: dict[str, object]) -> None:
        encoded = json.dumps(detail, ensure_ascii=True, separators=(",", ":"))
        self.assertLessEqual(
            len(encoded), 500,
            f"R2.3 JSON notice {name!r} would be silently truncated",
        )
        self._workflow_notice(name, encoded)

    def test_JSON工作流回执超限时必须显式失败(self) -> None:
        with self.assertRaises(AssertionError):
            self._workflow_json_notice("test", {"payload": "x" * 500})

    def test_staging基线规范化仅接受自动继承控制位变化(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-staging-acl-baseline-") as raw:
            root = Path(raw) / "icode-runtime-staging-test"
            root.mkdir()
            before = windows_appcontainer._DaclSnapshot(
                path=root, dacl=b"original-dacl", control=0x0004, revision=1,
                present=True, defaulted=False, file_identity=(1, 2),
            )
            after = windows_appcontainer._DaclSnapshot(
                path=root, dacl=b"original-dacl", control=0x0404, revision=1,
                present=True, defaulted=False, file_identity=(1, 2),
            )
            with mock.patch.dict(os.environ, {
                "GITHUB_ACTIONS": "true",
                "RUNNER_OS": "Windows",
                "ICODE_DIAGNOSTIC_RUNTIME_STAGING": "true",
            }), mock.patch.object(
                windows_appcontainer, "_read_dacl_state", side_effect=(before, after),
            ), mock.patch.object(windows_appcontainer, "_set_dacl") as set_dacl:
                delta = windows_appcontainer._normalize_staged_runtime_acl_baseline(
                    root, object(), object(),
                )

        self.assertEqual(delta, 0x0400)
        set_dacl.assert_called_once()
        self.assertEqual(set_dacl.call_args.args[0], root)

    def test_staging基线已规范化时不再写入ACL(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-staging-acl-baseline-") as raw:
            root = Path(raw) / "icode-runtime-staging-test"
            root.mkdir()
            snapshot = windows_appcontainer._DaclSnapshot(
                path=root, dacl=b"original-dacl", control=0x0404, revision=1,
                present=True, defaulted=False, file_identity=(1, 2),
            )
            with mock.patch.dict(os.environ, {
                "GITHUB_ACTIONS": "true",
                "RUNNER_OS": "Windows",
                "ICODE_DIAGNOSTIC_RUNTIME_STAGING": "true",
            }), mock.patch.object(
                windows_appcontainer, "_read_dacl_state", return_value=snapshot,
            ), mock.patch.object(windows_appcontainer, "_set_dacl") as set_dacl:
                delta = windows_appcontainer._normalize_staged_runtime_acl_baseline(
                    root, object(), object(),
                )

        self.assertEqual(delta, 0)
        set_dacl.assert_not_called()

    def test_staging基线规范化发现DACL变化时失败关闭(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-staging-acl-baseline-") as raw:
            root = Path(raw) / "icode-runtime-staging-test"
            root.mkdir()
            before = windows_appcontainer._DaclSnapshot(
                path=root, dacl=b"original-dacl", control=0x0004, revision=1,
                present=True, defaulted=False, file_identity=(1, 2),
            )
            after = windows_appcontainer._DaclSnapshot(
                path=root, dacl=b"changed-dacl", control=0x0404, revision=1,
                present=True, defaulted=False, file_identity=(1, 2),
            )
            with mock.patch.dict(os.environ, {
                "GITHUB_ACTIONS": "true",
                "RUNNER_OS": "Windows",
                "ICODE_DIAGNOSTIC_RUNTIME_STAGING": "true",
            }), mock.patch.object(
                windows_appcontainer, "_read_dacl_state", side_effect=(before, after),
            ), mock.patch.object(windows_appcontainer, "_set_dacl"):
                with self.assertRaises(_AppContainerSetupError) as raised:
                    windows_appcontainer._normalize_staged_runtime_acl_baseline(
                        root, object(), object(),
                    )

        self.assertEqual(raised.exception.error, "runtime_acl_normalization_failed")

    @staticmethod
    def _runtime_acl_restore_categories(
        transaction: windows_appcontainer._RuntimeAclTransaction,
        sid: ctypes.c_void_p,
    ) -> dict[str, object]:
        """Classify the first restore mismatch without exposing object paths."""
        try:
            root = transaction.roots[0]
            actual_paths = windows_appcontainer._walk_workspace(root)
            expected = {
                item.path: item for item in transaction.entries
                if item.path == root or item.path.is_relative_to(root)
            }
            actual_set = set(actual_paths)
            expected_set = set(expected)
            actual_only = len(actual_set - expected_set)
            expected_only = len(expected_set - actual_set)
            if actual_only or expected_only:
                return {
                    "state": "path_set_mismatch",
                    "actual_only": actual_only,
                    "expected_only": expected_only,
                }

            for path in actual_paths:
                current = windows_appcontainer._read_dacl_state(
                    path, transaction.advapi, transaction.kernel,
                )
                before = expected[path]
                dacl_changed = current.dacl != before.dacl
                metadata_changes = {
                    "control_changed": current.control != before.control,
                    "revision_changed": current.revision != before.revision,
                    "present_changed": current.present != before.present,
                    "defaulted_changed": current.defaulted != before.defaulted,
                    "file_identity_changed": current.file_identity != before.file_identity,
                }
                metadata_changed = any(metadata_changes.values())
                sid_residual = windows_appcontainer._contains_sid(
                    current.dacl, sid, transaction.advapi,
                )
                if dacl_changed or metadata_changed or sid_residual:
                    return {
                        "state": "object_mismatch",
                        "object": "root" if path == root else "descendant",
                        "dacl_changed": dacl_changed,
                        "metadata_changed": metadata_changed,
                        **metadata_changes,
                        "control_delta": before.control ^ current.control,
                        "sid_residual": sid_residual,
                    }
            return {"state": "snapshot_match_after_failure", "objects": len(actual_paths)}
        except _AppContainerSetupError as exc:
            return {"state": "inspection_failed", "category": exc.error}
        except (OSError, RuntimeError, ValueError):
            return {"state": "inspection_failed", "category": "filesystem_error"}

    def _observe_runtime_acl_restore(
        self,
        restore: Callable[[windows_appcontainer._RuntimeAclTransaction, ctypes.c_void_p], bool],
        transaction: windows_appcontainer._RuntimeAclTransaction,
        sid: ctypes.c_void_p,
        report: dict[str, object],
    ) -> bool:
        try:
            restored = restore(transaction, sid)
        except Exception:
            report.update({"state": "restore_exception"})
            raise
        report.update(
            {"state": "restored"}
            if restored
            else self._runtime_acl_restore_categories(transaction, sid)
        )
        return restored

    def test_runtime_ACL恢复诊断只报告脱敏的不匹配类别(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-runtime-acl-diagnostic-") as raw:
            root = Path(raw) / "runtime"
            root.mkdir()
            child = root / "python.dll"
            child.write_bytes(b"runtime")

            def snapshot(path: Path, dacl: bytes, *, control: int = 0):
                info = path.lstat()
                return windows_appcontainer._DaclSnapshot(
                    path=path, dacl=dacl, control=control, revision=1,
                    present=True, defaulted=False,
                    file_identity=(int(info.st_dev), int(info.st_ino)),
                )

            transaction = windows_appcontainer._RuntimeAclTransaction(
                roots=(root,),
                entries=(snapshot(root, b"original-root"), snapshot(child, b"original-child")),
                advapi=object(), kernel=object(), snapshot_duration_ms=1,
            )
            child_after = snapshot(child, b"changed-child")
            root_after = snapshot(root, b"original-root", control=0x0400)
            child_original = snapshot(child, b"original-child")

            def read_state(path: Path, _advapi: object, _kernel: object):
                return snapshot(path, b"original-root") if path == root else child_after

            with mock.patch.object(
                windows_appcontainer, "_walk_workspace", return_value=[root, child],
            ), mock.patch.object(
                windows_appcontainer, "_read_dacl_state", side_effect=read_state,
            ), mock.patch.object(
                windows_appcontainer, "_contains_sid", return_value=False,
            ):
                report = self._runtime_acl_restore_categories(
                    transaction, ctypes.c_void_p(123),
                )

        self.assertEqual(report["state"], "object_mismatch")
        self.assertEqual(report["object"], "descendant")
        self.assertTrue(report["dacl_changed"])
        self.assertFalse(report["metadata_changed"])
        self.assertFalse(report["control_changed"])
        self.assertFalse(report["revision_changed"])
        self.assertFalse(report["present_changed"])
        self.assertFalse(report["defaulted_changed"])
        self.assertFalse(report["file_identity_changed"])
        self.assertEqual(report["control_delta"], 0)
        self.assertNotIn(str(root), repr(report))

        with mock.patch.object(
            windows_appcontainer, "_walk_workspace", return_value=[root, child],
        ), mock.patch.object(
            windows_appcontainer, "_read_dacl_state",
            side_effect=lambda path, _advapi, _kernel: (
                root_after if path == root else child_original
            ),
        ), mock.patch.object(
            windows_appcontainer, "_contains_sid", return_value=False,
        ):
            root_report = self._runtime_acl_restore_categories(
                transaction, ctypes.c_void_p(123),
            )

        self.assertEqual(root_report["state"], "object_mismatch")
        self.assertEqual(root_report["object"], "root")
        self.assertFalse(root_report["dacl_changed"])
        self.assertTrue(root_report["metadata_changed"])
        self.assertTrue(root_report["control_changed"])
        self.assertFalse(root_report["revision_changed"])
        self.assertFalse(root_report["present_changed"])
        self.assertFalse(root_report["defaulted_changed"])
        self.assertFalse(root_report["file_identity_changed"])
        self.assertEqual(root_report["control_delta"], 0x0400)
        self.assertNotIn(str(root), repr(root_report))

    @staticmethod
    def _read_cmd_exit_status(path: Path) -> int | None:
        try:
            label, value = path.read_text(encoding="ascii").strip().split("=", 1)
            return int(value) if label == "exit_code" else None
        except (OSError, ValueError):
            return None

    @staticmethod
    def _profile_env_values(env_lines: list[str]) -> list[str]:
        return [
            line.split("=", 1)[1]
            for line in env_lines
            if line.partition("=")[0].casefold() == "localappdata" and "=" in line
        ]

    @classmethod
    def _profile_env_matches_api(cls, env_lines: list[str], profile_paths: list[str]) -> bool:
        values = cls._profile_env_values(env_lines)
        if len(profile_paths) != 1 or len(values) != 1:
            return False
        actual = values[0].rstrip("\\/").casefold()
        expected = profile_paths[0].rstrip("\\/").casefold()
        return bool(actual) and actual == expected

    @staticmethod
    def _profile_path_relation(actual: str, expected: str) -> str:
        actual_path = ntpath.normcase(ntpath.normpath(actual))
        expected_path = ntpath.normcase(ntpath.normpath(expected))
        if not ntpath.isabs(actual_path) or not ntpath.isabs(expected_path):
            return "invalid"
        if actual_path == expected_path:
            return "exact"
        try:
            common_path = ntpath.commonpath([actual_path, expected_path])
        except ValueError:
            return "other"
        if common_path == expected_path:
            relative_path = ntpath.relpath(actual_path, expected_path)
            components = relative_path.split(ntpath.sep)
            first_component = components[0].casefold()
            category = {
                "temp": "api_child_temp",
                "local": "api_child_local",
                "localstate": "api_child_local_state",
            }.get(first_component, "api_child_other")
            return category if len(components) == 1 else f"{category}_nested"
        if common_path == actual_path:
            return "api_parent"
        if ntpath.dirname(actual_path) == ntpath.dirname(expected_path):
            return "sibling"
        return "other"

    @staticmethod
    def _profile_path_stat_class(path: str) -> str:
        try:
            metadata = os.stat(path)
        except OSError as exc:
            winerror = getattr(exc, "winerror", None)
            if isinstance(exc, FileNotFoundError) or winerror in {2, 3}:
                return "not_found"
            if isinstance(exc, PermissionError) or winerror == 5:
                return "access_denied"
            return "other_error"
        return "directory" if stat.S_ISDIR(metadata.st_mode) else "not_directory"

    @staticmethod
    def _decode_cmd_unicode_output(contents: bytes) -> str:
        if contents.startswith(b"\xff\xfe"):
            contents = contents[2:]
        return contents.decode("utf-16-le")

    @staticmethod
    def _append_expected_profile_path(block: str, name: str, value: str) -> str:
        updated = _append_windows_environment_value(block, name, value)
        if name.casefold() == "localappdata":
            # Test-only alias enables an in-process comparison without logging either path.
            updated = _append_windows_environment_value(
                updated, "ICODE_EXPECTED_LOCALAPPDATA", value,
            )
        return updated

    def test_CMD退出码探针要求命名字段避免数字被解析成重定向(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-cmd-status-") as raw:
            status = Path(raw) / "status.txt"
            status.write_text("exit_code=7", encoding="ascii")
            self.assertEqual(self._read_cmd_exit_status(status), 7)
            status.write_text("7", encoding="ascii")
            self.assertIsNone(self._read_cmd_exit_status(status))

    def test_CMDUnicode输出解析支持有无BOM且拒绝损坏文本(self) -> None:
        expected = "LOCALAPPDATA=C:\\Users\\runner\\AppData\\Local\\Packages\\icode\\AC\r\n"
        encoded = expected.encode("utf-16-le")
        self.assertEqual(self._decode_cmd_unicode_output(encoded), expected)
        self.assertEqual(
            self._decode_cmd_unicode_output(b"\xff\xfe" + encoded), expected,
        )
        with self.assertRaises(UnicodeDecodeError):
            self._decode_cmd_unicode_output(b"\x00")

    def test_profile环境路径诊断要求唯一键值并与API路径匹配(self) -> None:
        profile_line = r"LOCALAPPDATA=C:\Users\runner\AppData\Local\Packages\icode\AC"
        self.assertEqual(self._profile_env_values([profile_line]), [
            r"C:\Users\runner\AppData\Local\Packages\icode\AC",
        ])
        self.assertTrue(self._profile_env_matches_api(
            [profile_line],
            ["c:\\users\\RUNNER\\AppData\\Local\\Packages\\icode\\AC\\"],
        ))
        self.assertFalse(self._profile_env_matches_api(
            [r"LOCALAPPDATA=C:\Users\runner\AppData\Local\Packages\other\AC"],
            [r"C:\Users\runner\AppData\Local\Packages\icode\AC"],
        ))
        self.assertFalse(self._profile_env_matches_api(
            [r"LOCALAPPDATA=C:\one", r"LOCALAPPDATA=C:\two"], [r"C:\one"],
        ))
        self.assertTrue(self._profile_env_matches_api(
            [r"LOCALAPPDATA=C:\profile\AC\Temp"], ["C:\\profile\\AC\\Temp\\"],
        ))

    def test_profile路径关系只返回脱敏子目录类别(self) -> None:
        expected = r"C:\Users\runner\AppData\Local\Packages\icode\AC"
        self.assertEqual(self._profile_path_relation(expected + "\\", expected), "exact")
        self.assertEqual(
            self._profile_path_relation(expected + r"\Temp", expected), "api_child_temp",
        )
        self.assertEqual(
            self._profile_path_relation(expected + r"\Local", expected), "api_child_local",
        )
        self.assertEqual(
            self._profile_path_relation(expected + r"\LocalState", expected),
            "api_child_local_state",
        )
        self.assertEqual(
            self._profile_path_relation(expected + r"\Private", expected), "api_child_other",
        )
        self.assertEqual(
            self._profile_path_relation(expected + r"\Temp\Nested", expected),
            "api_child_temp_nested",
        )
        self.assertEqual(
            self._profile_path_relation(expected + r"\Local\Nested", expected),
            "api_child_local_nested",
        )
        self.assertEqual(
            self._profile_path_relation(expected + r"\Private\Nested", expected),
            "api_child_other_nested",
        )
        self.assertEqual(self._profile_path_relation(ntpath.dirname(expected), expected), "api_parent")
        self.assertEqual(
            self._profile_path_relation(ntpath.dirname(expected) + r"\AC2", expected),
            "sibling",
        )
        self.assertEqual(self._profile_path_relation(r"D:\Other", expected), "other")
        self.assertEqual(self._profile_path_relation("relative", expected), "invalid")

    def test_profile环境诊断alias只复制API路径且不输出路径(self) -> None:
        expected = r"C:\Users\runner\AppData\Local\Packages\icode\AC"
        block = self._append_expected_profile_path("\0\0", "LOCALAPPDATA", expected)
        values = {
            entry.split("=", 1)[0].casefold(): entry.split("=", 1)[1]
            for entry in block.split("\0") if entry and "=" in entry
        }
        self.assertEqual(values.get("localappdata"), expected)
        self.assertEqual(values.get("icode_expected_localappdata"), expected)
        self.assertEqual(len(values), 2)

    def _mock_profile_apis(self) -> dict[str, mock.Mock]:
        import ctypes

        apis = {name: mock.Mock() for name in ("userenv", "kernel32", "advapi32", "ole32")}

        def create_profile(*args: object) -> int:
            sid_output = args[-1]
            ctypes.cast(sid_output, ctypes.POINTER(ctypes.c_void_p)).contents.value = 123
            return 0

        apis["userenv"].CreateAppContainerProfile.side_effect = create_profile
        apis["userenv"].DeleteAppContainerProfile.return_value = 0
        apis["advapi32"].IsValidSid.return_value = True
        apis["advapi32"].GetLengthSid.return_value = 12
        return apis

    def test_workspace目录拒绝链接与硬链接(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-paths-") as raw:
            root = Path(raw)
            target = root / "outside.txt"
            target.write_text("outside", encoding="utf-8")
            workspace = root / "task"
            workspace.mkdir()
            try:
                (workspace / "link.txt").symlink_to(target)
            except OSError:
                pass  # Windows without developer mode may deny symlink creation.
            else:
                with self.assertRaises(_AppContainerSetupError) as caught:
                    _walk_workspace(workspace)
                self.assertIn("类别=symbolic_link", caught.exception.detail)

        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-hardlinks-") as raw:
            root = Path(raw)
            source = root / "outside.txt"
            source.write_text("outside", encoding="utf-8")
            workspace = root / "task"
            workspace.mkdir()
            try:
                os.link(source, workspace / "linked.txt")
            except OSError as exc:
                self.skipTest(f"文件系统不支持硬链接测试：{exc}")
            with self.assertRaises(_AppContainerSetupError):
                _walk_workspace(workspace)

    def test_runtime_ACL目录扫描支持对象数和时限上限(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-runtime-tree-limit-") as raw:
            root = Path(raw)
            (root / "python.dll").write_bytes(b"runtime")
            with self.assertRaises(_AppContainerSetupError):
                windows_appcontainer._walk_workspace(root, max_entries=1)
            with self.assertRaises(_AppContainerSetupError):
                windows_appcontainer._walk_workspace(
                    root, deadline=time.monotonic() - 1,
                )

    def test_runtime根校验去重并拒绝覆盖工作区的目录(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-runtime-roots-") as raw:
            parent = Path(raw)
            runtime = parent / "python"
            runtime.mkdir()
            workspace = parent / "task"
            workspace.mkdir()

            roots = windows_appcontainer._validate_runtime_roots(
                (runtime, runtime.resolve()), workspace=workspace,
            )

            self.assertEqual(roots, (runtime.resolve(),))
            with self.assertRaises(_AppContainerSetupError):
                windows_appcontainer._validate_runtime_roots(
                    (parent,), workspace=workspace,
                )

    def test_runtime根校验拒绝嵌套授权根和用户目录根(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-runtime-roots-overlap-") as raw:
            parent = Path(raw)
            runtime = parent / "python"
            nested = runtime / "Lib"
            nested.mkdir(parents=True)
            workspace = parent / "task"
            workspace.mkdir()

            with self.assertRaises(_AppContainerSetupError):
                windows_appcontainer._validate_runtime_roots(
                    (runtime, nested), workspace=workspace,
                )
            with self.assertRaises(_AppContainerSetupError):
                windows_appcontainer._validate_runtime_roots(
                    (Path.home(),), workspace=workspace,
                )

    def test_runtime根校验拒绝指向外部目录的符号链接(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-runtime-root-link-") as raw:
            parent = Path(raw)
            actual = parent / "python"
            actual.mkdir()
            workspace = parent / "task"
            workspace.mkdir()
            link = parent / "python-alias"
            try:
                link.symlink_to(actual, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"文件系统不支持符号链接测试：{exc}")

            with self.assertRaises(_AppContainerSetupError):
                windows_appcontainer._validate_runtime_roots(
                    (link,), workspace=workspace,
                )

    def test_runtime树ACL快照以脱敏类别拒绝符号链接(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-runtime-tree-link-") as raw:
            parent = Path(raw)
            runtime = parent / "python"
            runtime.mkdir()
            workspace = parent / "task"
            workspace.mkdir()
            outside = parent / "outside.dll"
            outside.write_bytes(b"outside")
            try:
                (runtime / "python.dll").symlink_to(outside)
            except OSError as exc:
                self.skipTest(f"文件系统不支持符号链接测试：{exc}")

            with self.assertRaises(_AppContainerSetupError) as caught:
                windows_appcontainer._snapshot_runtime_acl_roots(
                    (runtime,), workspace=workspace, advapi=object(), kernel=object(),
                )

        self.assertEqual(caught.exception.error, "unsupported_runtime_root")
        self.assertIn("symbolic_link", caught.exception.detail)
        self.assertNotIn(str(parent), caught.exception.detail)

    def test_runtime_ACL快照枚举完整树并拒绝受保护DACL(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-runtime-acl-snapshot-") as raw:
            parent = Path(raw)
            runtime = parent / "python"
            runtime.mkdir()
            sample = runtime / "python.dll"
            sample.write_bytes(b"runtime")
            workspace = parent / "task"
            workspace.mkdir()

            def read_state(path: Path, _advapi: object, _kernel: object):
                info = path.lstat()
                return windows_appcontainer._DaclSnapshot(
                    path=path, dacl=b"original-dacl", control=0, revision=1,
                    present=True, defaulted=False,
                    file_identity=(int(info.st_dev), int(info.st_ino)),
                )

            with mock.patch.object(
                windows_appcontainer, "_read_dacl_state", side_effect=read_state,
            ):
                snapshot = windows_appcontainer._snapshot_runtime_acl_roots(
                    (runtime,), workspace=workspace, advapi=object(), kernel=object(),
                )
            self.assertEqual(
                {item.path for item in snapshot.entries}, {runtime, sample},
            )

            def read_protected_state(path: Path, _advapi: object, _kernel: object):
                state = read_state(path, _advapi, _kernel)
                if path == sample:
                    return windows_appcontainer._DaclSnapshot(
                        path=path, dacl=state.dacl,
                        control=windows_appcontainer._SE_DACL_PROTECTED, revision=1,
                        present=True, defaulted=False,
                        file_identity=state.file_identity,
                    )
                return state

            with mock.patch.object(
                windows_appcontainer, "_read_dacl_state", side_effect=read_protected_state,
            ), self.assertRaises(_AppContainerSetupError):
                windows_appcontainer._snapshot_runtime_acl_roots(
                    (runtime,), workspace=workspace, advapi=object(), kernel=object(),
                )

    def test_runtime_ACL预检失败回执保留脱敏拒绝原因(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-runtime-acl-reason-") as raw:
            parent = Path(raw)
            runtime = parent / "python"
            runtime.mkdir()
            workspace = parent / "task"
            workspace.mkdir()
            with mock.patch.object(
                windows_appcontainer, "_walk_workspace",
                side_effect=_AppContainerSetupError(
                    "unsupported_workspace_entry", "任务目录含硬链接，AppContainer 拒绝启动",
                ),
            ), self.assertRaises(_AppContainerSetupError) as caught:
                windows_appcontainer._snapshot_runtime_acl_roots(
                    (runtime,), workspace=workspace, advapi=object(), kernel=object(),
                )

        self.assertEqual(caught.exception.error, "unsupported_runtime_root")
        self.assertIn("unsupported_workspace_entry", caught.exception.detail)
        self.assertIn("硬链接", caught.exception.detail)
        self.assertNotIn(str(runtime), caught.exception.detail)

    def test_runtime_ACL逐根只授读取执行且先记录待恢复根(self) -> None:
        import ctypes

        with tempfile.TemporaryDirectory(prefix="icode-runtime-acl-apply-") as raw:
            parent = Path(raw)
            first = parent / "python-a"
            second = parent / "python-b"
            first.mkdir()
            second.mkdir()
            workspace = parent / "task"
            workspace.mkdir()

            def read_state(path: Path, _advapi: object, _kernel: object):
                info = path.lstat()
                return windows_appcontainer._DaclSnapshot(
                    path=path, dacl=b"original-dacl", control=0, revision=1,
                    present=True, defaulted=False,
                    file_identity=(int(info.st_dev), int(info.st_ino)),
                )

            with mock.patch.object(
                windows_appcontainer, "_read_dacl_state", side_effect=read_state,
            ):
                transaction = windows_appcontainer._snapshot_runtime_acl_roots(
                    (first, second), workspace=workspace,
                    advapi=object(), kernel=object(),
                )

            calls: list[tuple[Path, int]] = []

            def apply(root: Path, _sid: object, access: int, *_apis: object) -> None:
                calls.append((root, access))
                if root == second:
                    raise _AppContainerSetupError("runtime_acl_failed", "injected failure")

            with mock.patch.object(
                windows_appcontainer, "_read_dacl_state", side_effect=read_state,
            ), mock.patch.object(
                windows_appcontainer, "_contains_sid", return_value=False,
            ), mock.patch.object(
                windows_appcontainer, "_add_runtime_acl", side_effect=apply,
            ), self.assertRaises(_AppContainerSetupError):
                windows_appcontainer._grant_runtime_acl_roots(
                    transaction, ctypes.c_void_p(123),
                )

            expected_access = (
                windows_appcontainer._FILE_GENERIC_READ
                | windows_appcontainer._FILE_GENERIC_EXECUTE
            )
            self.assertEqual(calls, [(first, expected_access), (second, expected_access)])
            self.assertEqual(transaction.modified_roots, [first, second])

    def test_runtime_ACL恢复按逆序执行并要求全树状态精确匹配(self) -> None:
        import ctypes

        with tempfile.TemporaryDirectory(prefix="icode-runtime-acl-restore-") as raw:
            parent = Path(raw)
            first = parent / "python-a"
            second = parent / "python-b"
            first.mkdir()
            second.mkdir()
            workspace = parent / "task"
            workspace.mkdir()

            def read_state(path: Path, _advapi: object, _kernel: object):
                info = path.lstat()
                return windows_appcontainer._DaclSnapshot(
                    path=path, dacl=b"original-dacl", control=0, revision=1,
                    present=True, defaulted=False,
                    file_identity=(int(info.st_dev), int(info.st_ino)),
                )

            with mock.patch.object(
                windows_appcontainer, "_read_dacl_state", side_effect=read_state,
            ):
                transaction = windows_appcontainer._snapshot_runtime_acl_roots(
                    (first, second), workspace=workspace,
                    advapi=object(), kernel=object(),
                )
            transaction.modified_roots[:] = [first, second]
            restored: list[Path] = []

            with mock.patch.object(
                windows_appcontainer, "_set_dacl",
                side_effect=lambda path, *_args: restored.append(path),
            ), mock.patch.object(
                windows_appcontainer, "_read_dacl_state", side_effect=read_state,
            ), mock.patch.object(
                windows_appcontainer, "_contains_sid", return_value=False,
            ):
                result = windows_appcontainer._restore_runtime_acl_roots(
                    transaction, ctypes.c_void_p(123),
                )

            self.assertTrue(result)
            self.assertEqual(restored, [second, first])
            self.assertEqual(transaction.modified_roots, [])

    def test_非_windows平台明确拒绝(self) -> None:
        if sys.platform == "win32":
            self.skipTest("仅用于验证非 Windows 拒绝路径")
        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-unsupported-") as raw:
            result = run_windows_appcontainer(
                [sys.executable, "-V"], cwd=raw, timeout_seconds=2,
            )
        self.assertFalse(result.executed)
        self.assertFalse(result.cleanup_ok)
        self.assertEqual(result.error, "unsupported_platform")

    def test_lpApplicationName诊断在AppContainer外层拒绝其它命令(self) -> None:
        executable = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "whoami.exe"
        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-invalid-diagnostic-") as raw, \
             mock.patch("icode.windows_appcontainer.sys.platform", "win32"), \
             mock.patch("icode.windows_appcontainer.Path.is_absolute", return_value=True), \
             mock.patch("icode.windows_appcontainer.Path.is_file", return_value=True), \
             mock.patch("icode.windows_appcontainer.ctypes.WinDLL", create=True) as load_api:
            result = run_windows_appcontainer(
                [str(executable), "/all"], cwd=raw, timeout_seconds=2,
                _diagnostic_null_application_name=True,
            )
        self.assertFalse(result.executed)
        self.assertEqual(result.error, "invalid_diagnostic_probe")
        load_api.assert_not_called()

    def test_runtime_ACL诊断在GitHubActions以外被拒绝(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-runtime-acl-gate-") as raw, \
             mock.patch("icode.windows_appcontainer.sys.platform", "win32"), \
             mock.patch.dict(
                 os.environ,
                 {
                     "GITHUB_ACTIONS": "false", "RUNNER_OS": "Windows",
                     "ICODE_DIAGNOSTIC_RUNTIME_ACL": "true",
                 },
             ):
            result = run_windows_appcontainer(
                [sys.executable, "-c", "pass"], cwd=raw, timeout_seconds=2,
                _diagnostic_runtime_acl=True,
            )

        self.assertFalse(result.executed)
        self.assertEqual(result.error, "invalid_diagnostic_probe")
        self.assertFalse(result.cleanup_ok)

    def test_runtime_ACL差分缺少专用环境开关时拒绝(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-runtime-acl-opt-in-") as raw, \
             mock.patch("icode.windows_appcontainer.sys.platform", "win32"), \
             mock.patch.dict(
                 os.environ,
                 {"GITHUB_ACTIONS": "true", "RUNNER_OS": "Windows"},
                 clear=True,
             ):
            host_runtime = run_windows_appcontainer(
                [sys.executable, "-c", "pass"], cwd=raw, timeout_seconds=2,
                _diagnostic_runtime_acl=True,
            )
            staged_runtime = run_windows_appcontainer(
                [sys.executable, "-c", "pass"], cwd=raw, timeout_seconds=2,
                _diagnostic_runtime_acl=True,
                _diagnostic_runtime_roots=(Path(raw),),
            )

        self.assertEqual(host_runtime.error, "invalid_diagnostic_probe")
        self.assertEqual(staged_runtime.error, "invalid_diagnostic_probe")
        self.assertFalse(host_runtime.executed)
        self.assertFalse(staged_runtime.executed)
        self.assertFalse(host_runtime.cleanup_ok)
        self.assertFalse(staged_runtime.cleanup_ok)

    def test_runtime_ACL诊断在主进程前授权并在退出后恢复(self) -> None:
        apis = self._mock_profile_apis()
        transaction = windows_appcontainer._RuntimeAclTransaction(
            roots=(Path("C:/runtime"),), entries=(),
            advapi=apis["advapi32"], kernel=apis["kernel32"],
            snapshot_duration_ms=1,
        )
        job_result = WindowsJobResult(True, 0, None, True, "")
        with tempfile.TemporaryDirectory(prefix="icode-runtime-acl-flow-") as raw, \
             mock.patch("icode.windows_appcontainer.sys.platform", "win32"), \
             mock.patch.dict(
                 os.environ,
                 {
                     "GITHUB_ACTIONS": "true", "RUNNER_OS": "Windows",
                     "ICODE_DIAGNOSTIC_RUNTIME_ACL": "true",
                 },
             ), \
             mock.patch(
                 "icode.windows_appcontainer.ctypes.WinDLL",
                 create=True,
                 side_effect=lambda name, **_kwargs: apis[name],
             ), \
             mock.patch(
                 "icode.windows_appcontainer._grant_workspace_acl",
                 return_value=(b"workspace-dacl", apis["advapi32"], apis["kernel32"]),
             ), \
             mock.patch(
                 "icode.windows_appcontainer._get_appcontainer_localappdata_path",
                 return_value=r"C:\runner\profile\AC",
             ), \
             mock.patch(
                 "icode.windows_appcontainer._snapshot_runtime_acl_roots",
                 return_value=transaction,
             ) as snapshot, \
             mock.patch("icode.windows_appcontainer._grant_runtime_acl_roots") as grant, \
             mock.patch(
                 "icode.windows_appcontainer._restore_runtime_acl_roots", return_value=True,
             ) as restore_runtime, \
             mock.patch(
                 "icode.windows_appcontainer._restore_workspace_acl", return_value=True,
             ), mock.patch(
                 "icode.windows_appcontainer.run_windows_job", return_value=job_result,
             ) as run_job:
            result = run_windows_appcontainer(
                [sys.executable, "-c", "pass"], cwd=raw, timeout_seconds=2,
                _diagnostic_runtime_acl=True,
            )

        self.assertTrue(result.executed, result)
        self.assertTrue(result.cleanup_ok, result)
        snapshot.assert_called_once()
        self.assertEqual(
            snapshot.call_args.args[0], (Path(sys.prefix), Path(sys.base_prefix)),
        )
        grant.assert_called_once_with(transaction, apis["advapi32"].FreeSid.call_args.args[0])
        restore_runtime.assert_called_once()
        self.assertGreaterEqual(run_job.call_count, 1)

    def test_容器LOCALAPPDATA通过SID字符串查询并释放Win32内存(self) -> None:
        import ctypes

        sid_text = ctypes.create_unicode_buffer("S-1-15-2-123")
        profile_path = ctypes.create_unicode_buffer(
            r"C:\Users\runner\AppData\Local\Packages\icode\AC",
        )
        advapi = mock.Mock()
        userenv = mock.Mock()
        kernel = mock.Mock()
        ole32 = mock.Mock()

        def convert_sid(sid: object, output: object) -> int:
            self.assertEqual(getattr(sid, "value", sid), 123)
            ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p)).contents.value = (
                ctypes.addressof(sid_text)
            )
            return 1

        def get_appcontainer_path(sid_string: str, output: object) -> int:
            self.assertEqual(sid_string, "S-1-15-2-123")
            ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p)).contents.value = (
                ctypes.addressof(profile_path)
            )
            return 0

        advapi.ConvertSidToStringSidW.side_effect = convert_sid
        userenv.GetAppContainerFolderPath.side_effect = get_appcontainer_path
        kernel.LocalFree.return_value = None
        with mock.patch("icode.windows_appcontainer.sys.platform", "win32"):
            path = _get_appcontainer_localappdata_path(
                ctypes.c_void_p(123), userenv, advapi, kernel, ole32,
            )

        self.assertEqual(path, r"C:\Users\runner\AppData\Local\Packages\icode\AC")
        kernel.LocalFree.assert_called_once()
        ole32.CoTaskMemFree.assert_called_once()

    def test_容器LOCALAPPDATA查询失败时释放SID且不猜路径(self) -> None:
        import ctypes

        sid_text = ctypes.create_unicode_buffer("S-1-15-2-123")
        advapi = mock.Mock()
        userenv = mock.Mock()
        kernel = mock.Mock()
        ole32 = mock.Mock()

        def convert_sid(sid: object, output: object) -> int:
            ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p)).contents.value = (
                ctypes.addressof(sid_text)
            )
            return 1

        advapi.ConvertSidToStringSidW.side_effect = convert_sid
        userenv.GetAppContainerFolderPath.return_value = 0x80004005
        kernel.LocalFree.return_value = None
        with self.assertRaises(_AppContainerSetupError), \
             mock.patch("icode.windows_appcontainer.sys.platform", "win32"):
            _get_appcontainer_localappdata_path(
                ctypes.c_void_p(123), userenv, advapi, kernel, ole32,
            )
        kernel.LocalFree.assert_called_once()
        ole32.CoTaskMemFree.assert_not_called()

    def test_profile删除按官方约定重试并确认profile数据目录消失(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-profile-delete-") as raw:
            profile_path = Path(raw) / "AC"
            profile_path.mkdir()
            userenv = mock.Mock()

            def delete_profile(_profile: str) -> int:
                if userenv.DeleteAppContainerProfile.call_count == 2:
                    profile_path.rmdir()
                return 0

            userenv.DeleteAppContainerProfile.side_effect = delete_profile
            deleted, detail = _delete_appcontainer_profile(
                "icode-test", userenv, str(profile_path),
            )

        self.assertTrue(deleted, detail)
        self.assertEqual(detail, "")
        self.assertEqual(userenv.DeleteAppContainerProfile.call_count, 2)

    def test_profile数据目录残留时删除验证失败(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-profile-residue-") as raw:
            profile_path = Path(raw) / "AC"
            profile_path.mkdir()
            userenv = mock.Mock()
            userenv.DeleteAppContainerProfile.return_value = 0

            deleted, detail = _delete_appcontainer_profile(
                "icode-test", userenv, str(profile_path),
            )

        self.assertFalse(deleted)
        self.assertEqual(detail, "profile_storage_residual")
        self.assertEqual(userenv.DeleteAppContainerProfile.call_count, 2)

    def test_profile删除API连续失败时即使数据目录缺失也不报成功(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-profile-delete-error-") as raw:
            absent_path = Path(raw) / "already-missing"
            userenv = mock.Mock()
            userenv.DeleteAppContainerProfile.return_value = 0x80004005

            deleted, detail = _delete_appcontainer_profile(
                "icode-test", userenv, str(absent_path),
            )

        self.assertFalse(deleted)
        self.assertEqual(detail, "profile_delete_failed:0x80004005")
        self.assertEqual(userenv.DeleteAppContainerProfile.call_count, 2)

    def test_容器路径查询失败时不启动命令且保留准确清理结果(self) -> None:
        apis = self._mock_profile_apis()
        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-path-failure-") as raw, \
             mock.patch("icode.windows_appcontainer.sys.platform", "win32"), \
             mock.patch(
                 "icode.windows_appcontainer.ctypes.WinDLL",
                 create=True,
                 side_effect=lambda name, **_kwargs: apis[name],
             ), \
             mock.patch(
                 "icode.windows_appcontainer._grant_workspace_acl",
                 return_value=(b"original-dacl", apis["advapi32"], apis["kernel32"]),
             ), \
             mock.patch(
                 "icode.windows_appcontainer._get_appcontainer_localappdata_path",
                 side_effect=_AppContainerSetupError(
                     "appcontainer_profile_path_failed", "profile path unavailable",
                 ),
             ), \
             mock.patch("icode.windows_appcontainer._restore_workspace_acl", return_value=True), \
             mock.patch("icode.windows_appcontainer.run_windows_job") as run_job:
            result = run_windows_appcontainer(
                [sys.executable, "-c", "pass"], cwd=raw, timeout_seconds=2,
            )

        self.assertFalse(result.executed)
        self.assertEqual(result.error, "appcontainer_profile_path_failed")
        self.assertTrue(result.cleanup_ok)
        run_job.assert_not_called()
        apis["userenv"].DeleteAppContainerProfile.assert_called_once()
        apis["advapi32"].FreeSid.assert_called_once()

    def test_容器正常启动和撤权探针都只收到当前profile路径(self) -> None:
        profile_path = r"C:\Users\runner\AppData\Local\Packages\icode\AC"
        apis = self._mock_profile_apis()
        job_result = WindowsJobResult(True, 0, None, True, "")
        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-profile-path-") as raw, \
             mock.patch("icode.windows_appcontainer.sys.platform", "win32"), \
             mock.patch(
                 "icode.windows_appcontainer.ctypes.WinDLL",
                 create=True,
                 side_effect=lambda name, **_kwargs: apis[name],
             ), \
             mock.patch(
                 "icode.windows_appcontainer._grant_workspace_acl",
                 return_value=(b"original-dacl", apis["advapi32"], apis["kernel32"]),
             ), \
             mock.patch(
                 "icode.windows_appcontainer._get_appcontainer_localappdata_path",
                 return_value=profile_path,
             ), \
             mock.patch("icode.windows_appcontainer._restore_workspace_acl", return_value=True), \
             mock.patch(
                 "icode.windows_appcontainer.run_windows_job", return_value=job_result,
             ) as run_job:
            result = run_windows_appcontainer(
                [sys.executable, "-c", "pass"], cwd=raw, timeout_seconds=2,
            )

        self.assertTrue(result.executed)
        self.assertTrue(result.cleanup_ok)
        self.assertEqual(run_job.call_count, 2, "主命令和 ACL 撤权探针都应在同一容器中运行")
        for call in run_job.call_args_list:
            self.assertEqual(call.kwargs["_appcontainer_sid"], 123)
            self.assertEqual(call.kwargs["_appcontainer_localappdata"], profile_path)

    @unittest.skipUnless(sys.platform == "win32", "需 Windows AppContainer 原生实测")
    def test_profile专属目录可写且进程退出后删除(self) -> None:
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        command = system_root / "System32" / "cmd.exe"
        profile_paths: list[str] = []
        profile_directory_exists_before_launch: list[bool] = []
        marker_present_before_delete: list[bool] = []
        profile_actual_stat_before_delete: list[str] = []
        profile_actual_relation_before_delete: list[str] = []
        profile_actual_samefile_as_api_before_delete: list[bool] = []
        marker_name = "icode-profile-lifecycle-probe.txt"
        delete_profile = _delete_appcontainer_profile

        def get_profile_path(
            sid: ctypes.c_void_p,
            userenv: ctypes.WinDLL,
            advapi: ctypes.WinDLL,
            kernel: ctypes.WinDLL,
            ole32: ctypes.WinDLL,
        ) -> str:
            path = _get_appcontainer_localappdata_path(
                sid, userenv, advapi, kernel, ole32,
            )
            profile_paths.append(path)
            profile_directory_exists_before_launch.append(Path(path).is_dir())
            return path

        def observe_profile_delete(
            profile: str, userenv: ctypes.WinDLL, localappdata: str | None,
        ) -> tuple[bool, str]:
            marker_path = Path(localappdata or "") / marker_name
            marker_present_before_delete.append(marker_path.is_file())
            actual_stat_class = "unavailable"
            actual_path_relation = "unavailable"
            actual_samefile_as_api = False
            try:
                unicode_status = self._read_cmd_exit_status(profile_env_unicode_status)
                unicode_output = self._decode_cmd_unicode_output(
                    profile_env_unicode_value.read_bytes(),
                ).splitlines()
                actual_paths = self._profile_env_values(unicode_output)
                if unicode_status == 0 and len(actual_paths) == 1:
                    actual_stat_class = self._profile_path_stat_class(actual_paths[0])
                    if localappdata:
                        actual_path_relation = self._profile_path_relation(
                            actual_paths[0], localappdata,
                        )
                        if actual_stat_class == "directory":
                            actual_samefile_as_api = Path(actual_paths[0]).samefile(localappdata)
            except (OSError, UnicodeDecodeError, ValueError):
                pass  # Diagnostic failure must not prevent the real profile cleanup.
            profile_actual_stat_before_delete.append(actual_stat_class)
            profile_actual_relation_before_delete.append(actual_path_relation)
            profile_actual_samefile_as_api_before_delete.append(actual_samefile_as_api)
            return delete_profile(profile, userenv, localappdata)

        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-profile-lifecycle-") as raw:
            workspace = Path(raw) / "task"
            workspace.mkdir()
            script = workspace / "profile-write.cmd"
            profile_env_state = workspace / "profile-env-state.txt"
            profile_env_value = workspace / "profile-env-value.txt"
            profile_env_unicode_value = workspace / "profile-env-unicode-value.txt"
            profile_env_unicode_status = workspace / "profile-env-unicode-status.txt"
            profile_env_compare = workspace / "profile-env-compare.txt"
            profile_expected_env_state = workspace / "profile-expected-env-state.txt"
            profile_directory_state = workspace / "profile-directory-state.txt"
            profile_write_status = workspace / "profile-write-status.txt"
            profile_write_stderr = workspace / "profile-write-stderr.txt"
            # The space before `>` prevents a trailing status digit being parsed as a file descriptor.
            script.write_text(
                "@echo off\r\n"
                f'if defined LOCALAPPDATA (echo defined> "{profile_env_state.name}") '
                f'else (echo missing> "{profile_env_state.name}")\r\n'
                f'set LOCALAPPDATA > "{profile_env_value.name}"\r\n'
                f'if defined ICODE_EXPECTED_LOCALAPPDATA '
                f'(echo defined> "{profile_expected_env_state.name}") '
                f'else (echo missing> "{profile_expected_env_state.name}")\r\n'
                f'cmd.exe /u /d /c "set LOCALAPPDATA" '
                f'> "{profile_env_unicode_value.name}"\r\n'
                f'echo exit_code=%errorlevel% > "{profile_env_unicode_status.name}"\r\n'
                f'if /i "%LOCALAPPDATA%"=="%ICODE_EXPECTED_LOCALAPPDATA%" '
                f'(echo match> "{profile_env_compare.name}") '
                f'else (echo mismatch> "{profile_env_compare.name}")\r\n'
                f'if exist "%LOCALAPPDATA%\\." (echo exists> "{profile_directory_state.name}") '
                f'else (echo missing> "{profile_directory_state.name}")\r\n'
                f'(echo profile-write-ok> "%LOCALAPPDATA%\\{marker_name}") '
                f'2> "{profile_write_stderr.name}"\r\n'
                f'echo exit_code=%errorlevel% > "{profile_write_status.name}"\r\n',
                encoding="utf-8",
            )
            with mock.patch(
                "icode.windows_appcontainer._get_appcontainer_localappdata_path",
                side_effect=get_profile_path,
            ), mock.patch(
                "icode.windows_appcontainer._delete_appcontainer_profile",
                side_effect=observe_profile_delete,
            ), mock.patch(
                "icode.windows_job._append_windows_environment_value",
                side_effect=self._append_expected_profile_path,
            ):
                result = run_windows_appcontainer(
                    [str(command), "/d", "/c", f".\\{script.name}"],
                    cwd=workspace, timeout_seconds=8, process_limit=2,
                )
            try:
                profile_write_error = profile_write_stderr.read_text(
                    encoding="utf-8", errors="replace",
                ).casefold()
            except OSError:
                profile_write_error = ""
            if "access is denied" in profile_write_error or "access denied" in profile_write_error:
                profile_write_error_class = "access_denied"
            elif "path not found" in profile_write_error or "cannot find the path" in profile_write_error:
                profile_write_error_class = "path_not_found"
            elif "file not found" in profile_write_error or "cannot find the file" in profile_write_error:
                profile_write_error_class = "file_not_found"
            elif profile_write_error:
                profile_write_error_class = "other_write_error"
            else:
                profile_write_error_class = "no_stderr"
            profile_write_status_value = self._read_cmd_exit_status(profile_write_status)
            try:
                profile_env_defined = (
                    profile_env_state.read_text(encoding="utf-8").strip() == "defined"
                )
            except OSError:
                profile_env_defined = False
            try:
                profile_expected_env_defined = (
                    profile_expected_env_state.read_text(encoding="ascii").strip() == "defined"
                )
            except OSError:
                profile_expected_env_defined = False
            profile_env_matches_api = False
            try:
                profile_env_lines = profile_env_value.read_text(
                    encoding="utf-8", errors="replace",
                ).splitlines()
                profile_env_matches_api = self._profile_env_matches_api(
                    profile_env_lines, profile_paths,
                )
            except OSError:
                profile_env_matches_api = False
            profile_unicode_env_matches_api = False
            profile_unicode_env_matches_host = False
            profile_unicode_env_lines: list[str] = []
            profile_unicode_output_present = False
            try:
                profile_unicode_set_status = self._read_cmd_exit_status(
                    profile_env_unicode_status,
                )
            except OSError:
                profile_unicode_set_status = None
            try:
                profile_unicode_output = profile_env_unicode_value.read_bytes()
                profile_unicode_output_present = bool(profile_unicode_output)
                profile_unicode_env_lines = self._decode_cmd_unicode_output(
                    profile_unicode_output,
                ).splitlines()
                if profile_unicode_set_status == 0 and profile_unicode_env_lines:
                    profile_unicode_env_matches_api = self._profile_env_matches_api(
                        profile_unicode_env_lines, profile_paths,
                    )
            except (OSError, UnicodeDecodeError):
                profile_unicode_env_matches_api = False
            host_localappdata = os.environ.get("LOCALAPPDATA")
            host_localappdata_defined = bool(host_localappdata)
            actual_profile_paths = self._profile_env_values(profile_unicode_env_lines)
            profile_unicode_actual_value_defined = len(actual_profile_paths) == 1
            if profile_unicode_set_status == 0 and profile_unicode_env_lines and host_localappdata:
                profile_unicode_env_matches_host = self._profile_env_matches_api(
                    profile_unicode_env_lines, [host_localappdata],
                )
            try:
                profile_env_equals_api = (
                    profile_env_compare.read_text(encoding="ascii").strip() == "match"
                )
            except OSError:
                profile_env_equals_api = False
            try:
                profile_directory_visible = (
                    profile_directory_state.read_text(encoding="utf-8").strip() == "exists"
                )
            except OSError:
                profile_directory_visible = False

        self._workflow_notice(
            "profile storage lifecycle",
            f"executed={result.executed} exit={result.exit_code} cleanup={result.cleanup_ok} "
            f"env={profile_env_defined}/{profile_expected_env_defined}/{host_localappdata_defined} "
            f"unicode={profile_unicode_set_status}/{profile_unicode_output_present} "
            f"equals_api={profile_env_matches_api}/{profile_unicode_env_matches_api} "
            f"equals_host={profile_unicode_env_matches_host} alias_match={profile_env_equals_api} "
            f"actual={profile_unicode_actual_value_defined} "
            f"stat={profile_actual_stat_before_delete} relation={profile_actual_relation_before_delete} "
            f"same_api={profile_actual_samefile_as_api_before_delete} "
            f"dir_before={profile_directory_exists_before_launch} visible={profile_directory_visible} "
            f"write={profile_write_status_value}/{profile_write_error_class} "
            f"marker={marker_present_before_delete}",
        )
        self.assertTrue(result.executed, result)
        self.assertEqual(result.exit_code, 0, result)
        self.assertTrue(result.cleanup_ok, result)
        self.assertEqual(len(profile_paths), 1)
        self.assertEqual(marker_present_before_delete, [True])
        self.assertFalse(
            Path(profile_paths[0]).exists(),
            "profile storage must be removed when the AppContainer job ends",
        )

    def test_LOCALAPPDATA诊断在AppContainer外层拒绝用户命令(self) -> None:
        executable = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "whoami.exe"
        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-invalid-localappdata-") as raw, \
             mock.patch("icode.windows_appcontainer.sys.platform", "win32"), \
             mock.patch("icode.windows_appcontainer.Path.is_absolute", return_value=True), \
             mock.patch("icode.windows_appcontainer.Path.is_file", return_value=True), \
             mock.patch("icode.windows_appcontainer.ctypes.WinDLL", create=True) as load_api:
            result = run_windows_appcontainer(
                [str(executable), "/all"], cwd=raw, timeout_seconds=2,
                _diagnostic_omit_localappdata=True,
            )
        self.assertFalse(result.executed)
        self.assertEqual(result.error, "invalid_diagnostic_probe")
        load_api.assert_not_called()

    def test_省略LOCALAPPDATA差分不能与app_name差分叠加(self) -> None:
        executable = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "whoami.exe"
        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-overlapping-diagnostics-") as raw, \
             mock.patch("icode.windows_appcontainer.sys.platform", "win32"), \
             mock.patch("icode.windows_appcontainer.Path.is_absolute", return_value=True), \
             mock.patch("icode.windows_appcontainer.Path.is_file", return_value=True), \
             mock.patch("icode.windows_appcontainer.ctypes.WinDLL", create=True) as load_api:
            result = run_windows_appcontainer(
                [str(executable)], cwd=raw, timeout_seconds=2,
                _diagnostic_omit_localappdata=True,
                _diagnostic_null_application_name=True,
            )
        self.assertFalse(result.executed)
        self.assertEqual(result.error, "invalid_diagnostic_probe")
        load_api.assert_not_called()

    @unittest.skipUnless(sys.platform == "win32", "需 Windows AppContainer 原生实测")
    def test_诊断仅LOCALAPPDATA最小环境块下的系统程序启动(self) -> None:
        """The wrapper adds only its profile path to this intentionally empty base block."""
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        executable = system_root / "System32" / "whoami.exe"
        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-empty-env-") as raw:
            workspace = Path(raw) / "task"
            workspace.mkdir()
            safe_environment = _build_windows_environment_block(
                executable, workspace, system_root,
            )
            # The base block is intentionally empty; the wrapper adds only its profile path.
            # Never pass lpEnvironment=None, which would copy arbitrary runner variables.
            with mock.patch(
                "icode.windows_job._build_windows_environment_block",
                side_effect=("\0\0", safe_environment),
            ):
                result = run_windows_appcontainer(
                    [str(executable)], cwd=workspace, timeout_seconds=10, process_limit=2,
                )
            self._workflow_notice(
                "minimal base environment plus profile LOCALAPPDATA",
                f"executed={result.executed} exit={result.exit_code} error={result.error} "
                f"cleanup={result.cleanup_ok} detail={result.detail}",
            )
            self.assertTrue(result.executed, result)
            self.assertEqual(result.exit_code, 0, result)
            self.assertTrue(result.cleanup_ok, result)

    @unittest.skipUnless(sys.platform == "win32", "需 Windows AppContainer 原生实测")
    def test_AppContainer环境块仅比普通Job多容器LOCALAPPDATA(self) -> None:
        """AppContainer receives its own profile path, never the host profile variable."""
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        executable = system_root / "System32" / "whoami.exe"
        target_executable = os.path.normcase(str(executable))
        observed_blocks: list[str] = []
        appcontainer_blocks: list[str] = []
        append_environment_value = _append_windows_environment_value
        observed_metadata: list[str] = []

        def build_and_observe(
            executable_path: str | os.PathLike[str],
            cwd: str | os.PathLike[str],
            system_root_path: str | os.PathLike[str],
        ) -> str:
            block = _build_windows_environment_block(
                executable_path, cwd, system_root_path,
            )
            if os.path.normcase(os.fspath(executable_path)) == target_executable:
                observed_blocks.append(block)
                entries = [entry for entry in block.split("\0") if entry]
                names = [
                    entry[:entry.index("=", 1)] if entry.startswith("=")
                    else entry.split("=", 1)[0]
                    for entry in entries
                ]
                observed_metadata.append(
                    f"chars={len(block)} utf16_bytes={len(block.encode('utf-16-le'))} "
                    f"nul_chars={block.count(chr(0))} names={names} "
                    f"sha256={hashlib.sha256(block.encode('utf-16-le')).hexdigest()}"
                )
            return block

        def append_and_observe(block: str, name: str, value: str) -> str:
            result = append_environment_value(block, name, value)
            if name.casefold() == "localappdata":
                appcontainer_blocks.append(result)
            return result

        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-matched-env-") as raw:
            workspace = Path(raw) / "task"
            workspace.mkdir()
            with mock.patch(
                "icode.windows_job._build_windows_environment_block",
                side_effect=build_and_observe,
            ), mock.patch(
                "icode.windows_job._append_windows_environment_value",
                side_effect=append_and_observe,
            ):
                ordinary = run_windows_job(
                    [str(executable)], cwd=workspace, timeout_seconds=10,
                )
                appcontainer = run_windows_appcontainer(
                    [str(executable)], cwd=workspace, timeout_seconds=10,
                    process_limit=2,
                )

        self._workflow_notice(
            "AppContainer profile LOCALAPPDATA environment control",
            f"ordinary=executed:{ordinary.executed},exit:{ordinary.exit_code},"
            f"error:{ordinary.error},cleanup:{ordinary.cleanup_ok}; "
            f"appcontainer=executed:{appcontainer.executed},exit:{appcontainer.exit_code},"
            f"error:{appcontainer.error},cleanup:{appcontainer.cleanup_ok},"
            f"detail:{appcontainer.detail}; captured_blocks={len(observed_blocks)} "
            f"metadata={observed_metadata[:2]}",
        )

        self.assertTrue(ordinary.executed, ordinary)
        self.assertEqual(ordinary.exit_code, 0, ordinary)
        self.assertTrue(ordinary.cleanup_ok, ordinary)
        self.assertGreaterEqual(len(observed_blocks), 2, "both primary launches must build an environment")
        def parse(block: str) -> dict[str, str]:
            entries: dict[str, str] = {}
            for entry in block.split("\0"):
                if not entry:
                    continue
                separator = entry.index("=", 1) if entry.startswith("=") else entry.index("=")
                entries[entry[:separator]] = entry[separator + 1:]
            return entries

        ordinary_entries, appcontainer_base_entries = map(parse, observed_blocks[:2])
        self.assertEqual(observed_blocks[0], observed_blocks[1])
        self.assertEqual(appcontainer_base_entries, ordinary_entries)
        self.assertEqual(
            len(appcontainer_blocks), 2,
            "the AppContainer main command and ACL-revocation probe both use its profile variable",
        )
        appcontainer_entries = parse(appcontainer_blocks[0])
        self.assertNotIn("LOCALAPPDATA", ordinary_entries)
        self.assertIn("LOCALAPPDATA", appcontainer_entries)
        self.assertTrue(Path(appcontainer_entries["LOCALAPPDATA"]).is_absolute())
        self.assertEqual(
            [parse(block)["LOCALAPPDATA"] for block in appcontainer_blocks],
            [appcontainer_entries["LOCALAPPDATA"]] * len(appcontainer_blocks),
        )
        self.assertEqual(
            {key: value for key, value in appcontainer_entries.items() if key != "LOCALAPPDATA"},
            ordinary_entries,
        )
        self.assertTrue(appcontainer.executed, appcontainer)
        self.assertEqual(appcontainer.exit_code, 0, appcontainer)
        self.assertTrue(appcontainer.cleanup_ok, appcontainer)

    @unittest.skipUnless(sys.platform == "win32", "需 Windows AppContainer 原生实测")
    def test_诊断lpApplicationName显式路径与NULL差分(self) -> None:
        """Compare only lpApplicationName while keeping the suspended Job path intact."""
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        executable = system_root / "System32" / "whoami.exe"
        target_executable = os.path.normcase(str(executable))
        observed_blocks: list[str] = []
        appcontainer_blocks: list[str] = []
        append_environment_value = _append_windows_environment_value

        def build_and_observe(
            executable_path: str | os.PathLike[str],
            cwd: str | os.PathLike[str],
            system_root_path: str | os.PathLike[str],
        ) -> str:
            block = _build_windows_environment_block(
                executable_path, cwd, system_root_path,
            )
            if os.path.normcase(os.fspath(executable_path)) == target_executable:
                observed_blocks.append(block)
            return block

        def append_and_observe(block: str, name: str, value: str) -> str:
            result = append_environment_value(block, name, value)
            if name.casefold() == "localappdata":
                appcontainer_blocks.append(result)
            return result

        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-lpappname-") as raw:
            workspace = Path(raw) / "task"
            workspace.mkdir()
            with mock.patch(
                "icode.windows_job._build_windows_environment_block",
                side_effect=build_and_observe,
            ), mock.patch(
                "icode.windows_job._append_windows_environment_value",
                side_effect=append_and_observe,
            ):
                null_application_name = run_windows_appcontainer(
                    [str(executable)], cwd=workspace, timeout_seconds=10,
                    process_limit=2, _diagnostic_null_application_name=True,
                )

        env_equal = len(observed_blocks) == 2 and observed_blocks[0] == observed_blocks[1]
        self._workflow_notice(
            "lpApplicationName A/B diagnostic",
            f"candidate=executed:{null_application_name.executed},"
            f"exit:{null_application_name.exit_code},error:{null_application_name.error},"
            f"cleanup:{null_application_name.cleanup_ok}; environment_blocks="
            f"{len(observed_blocks)},equal:{env_equal}; "
            f"ab:{null_application_name.detail.partition('application_name_ab=')[2]}",
        )
        self.assertGreaterEqual(len(observed_blocks), 2, "both launches must reach environment setup")
        self.assertEqual(observed_blocks[0], observed_blocks[1])
        self.assertEqual(
            len(appcontainer_blocks), 3,
            "the A/B launches and ACL-revocation probe each use the same profile variable",
        )
        self.assertEqual(appcontainer_blocks[0], appcontainer_blocks[1])

        def profile_localappdata_value(block: str) -> str:
            entries = [
                entry for entry in block.split("\0") if entry
                and entry[:entry.index("=", 1)].casefold() == "localappdata"
            ]
            self.assertEqual(len(entries), 1, "final AppContainer block must contain one profile path")
            return entries[0].split("=", 1)[1]

        localappdata_values = [
            profile_localappdata_value(block) for block in appcontainer_blocks
        ]
        self.assertEqual(localappdata_values[1:], [localappdata_values[0]] * 2)
        self.assertTrue(null_application_name.executed, null_application_name)
        self.assertEqual(null_application_name.exit_code, 0, null_application_name)
        self.assertTrue(null_application_name.cleanup_ok, null_application_name)
        app_name_ab = null_application_name.detail.partition("application_name_ab=")[2]
        self.assertIn("baseline:executed:True,exit:0", app_name_ab)
        self.assertIn("candidate:executed:True,exit:0", app_name_ab)

    @unittest.skipUnless(sys.platform == "win32", "需 Windows AppContainer 原生实测")
    def test_诊断同一profile仅追加LOCALAPPDATA差分(self) -> None:
        """Keep profile SID and launch inputs fixed while adding its official local-data path."""
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        executable = system_root / "System32" / "whoami.exe"
        target_executable = os.path.normcase(str(executable))
        observed_blocks: list[str] = []
        appcontainer_blocks: list[str] = []
        append_environment_value = _append_windows_environment_value

        def build_and_observe(
            executable_path: str | os.PathLike[str],
            cwd: str | os.PathLike[str],
            system_root_path: str | os.PathLike[str],
        ) -> str:
            block = _build_windows_environment_block(
                executable_path, cwd, system_root_path,
            )
            if os.path.normcase(os.fspath(executable_path)) == target_executable:
                observed_blocks.append(block)
            return block

        def append_and_observe(block: str, name: str, value: str) -> str:
            result = append_environment_value(block, name, value)
            if name.casefold() == "localappdata":
                appcontainer_blocks.append(result)
            return result

        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-localappdata-") as raw:
            workspace = Path(raw) / "task"
            workspace.mkdir()
            with mock.patch(
                "icode.windows_job._build_windows_environment_block",
                side_effect=build_and_observe,
            ), mock.patch(
                "icode.windows_job._append_windows_environment_value",
                side_effect=append_and_observe,
            ):
                candidate = run_windows_appcontainer(
                    [str(executable)], cwd=workspace, timeout_seconds=10,
                    process_limit=2, _diagnostic_omit_localappdata=True,
                )

        ab_summary = candidate.detail.partition("localappdata_ab=")[2]
        self._workflow_notice(
            "same-profile LOCALAPPDATA A/B diagnostic",
            f"candidate=executed:{candidate.executed},exit:{candidate.exit_code},"
            f"error:{candidate.error},cleanup:{candidate.cleanup_ok}; "
            f"ab={ab_summary}; captured_blocks={len(observed_blocks)}",
        )
        self.assertEqual(len(observed_blocks), 2, "baseline and candidate must both launch")
        self.assertIn("baseline:executed:False", ab_summary)
        self.assertIn("baseline_win32_error:203", ab_summary)
        self.assertIn("candidate:executed:True,exit:0", ab_summary)

        def parse(block: str) -> dict[str, str]:
            entries: dict[str, str] = {}
            for entry in block.split("\0"):
                if not entry:
                    continue
                separator = entry.index("=", 1) if entry.startswith("=") else entry.index("=")
                entries[entry[:separator]] = entry[separator + 1:]
            return entries

        baseline_entries, candidate_base_entries = map(parse, observed_blocks)
        self.assertEqual(observed_blocks[0], observed_blocks[1])
        self.assertEqual(candidate_base_entries, baseline_entries)
        self.assertEqual(
            len(appcontainer_blocks), 2,
            "the A/B candidate and ACL-revocation probe use the profile variable",
        )
        candidate_entries = parse(appcontainer_blocks[0])
        self.assertNotIn("LOCALAPPDATA", baseline_entries)
        self.assertIn("LOCALAPPDATA", candidate_entries)
        self.assertEqual(
            parse(appcontainer_blocks[1])["LOCALAPPDATA"],
            candidate_entries["LOCALAPPDATA"],
        )
        self.assertEqual(
            {key: value for key, value in candidate_entries.items() if key != "LOCALAPPDATA"},
            baseline_entries,
        )
        self.assertTrue(candidate.executed, candidate)
        self.assertEqual(candidate.exit_code, 0, candidate)
        self.assertTrue(candidate.cleanup_ok, candidate)

    @unittest.skipUnless(sys.platform == "win32", "需 Windows AppContainer 原生实测")
    def test_诊断容器对宿主Python运行时文件的直接读取(self) -> None:
        """Distinguish runtime DACL access from a missing or misplaced dependency."""
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        command = system_root / "System32" / "cmd.exe"
        executable = Path(sys.executable)
        stdlib = Path(sysconfig.get_path("stdlib"))
        version = f"{sys.version_info.major}{sys.version_info.minor}"
        dll_name = sysconfig.get_config_var("DLLLIBRARY") or f"python{version}.dll"
        candidates = [
            ("system32_control", system_root / "System32" / "whoami.exe"),
            ("python_executable", executable),
            ("python_shared_library", executable.parent / dll_name),
            ("stdlib_pathlib", stdlib / "pathlib.py"),
            ("stdlib_encodings", stdlib / "encodings" / "__init__.py"),
            ("stdlib_archive", executable.parent / f"python{version}.zip"),
        ]
        runtime_files = [(label, path) for label, path in candidates if path.is_file()]
        self._workflow_notice(
            "Python runtime direct-read inventory",
            json.dumps(
                {
                    "candidate_count": len(candidates),
                    "available_count": len(runtime_files),
                    "available_labels": [label for label, _ in runtime_files],
                },
                ensure_ascii=True,
                separators=(",", ":"),
            ),
        )
        self.assertGreaterEqual(
            len(runtime_files), 4,
            "Windows CI runtime layout changed; direct-read diagnostic lacks enough samples",
        )
        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-runtime-access-") as raw:
            workspace = Path(raw) / "task"
            workspace.mkdir()
            copy_script = workspace / "copy-runtime.cmd"
            copy_started = workspace / "copy-runtime-started.txt"
            for index, (label, source) in enumerate(runtime_files):
                destination_name = f"runtime-copy-{index}.bin"
                destination = workspace / destination_name
                copy_message = workspace / f"runtime-copy-{index}.message.txt"
                copy_started.unlink(missing_ok=True)
                copy_message.unlink(missing_ok=True)
                copy_script.write_text(
                    f'@echo off\r\necho started> "{copy_started.name}"\r\n'
                    f'copy /b "{source}" "{destination_name}" '
                    f'> "{copy_message.name}" 2>&1\r\n',
                    encoding="utf-8",
                )
                # The Package SID is granted the task directory, not its temp parents.
                result = run_windows_appcontainer(
                    [str(command), "/d", "/c", f".\\{copy_script.name}"],
                    cwd=workspace, timeout_seconds=8, process_limit=2,
                )
                copy_script_started = copy_started.is_file()
                source_size = source.stat().st_size
                copied_size = destination.stat().st_size if destination.is_file() else None
                try:
                    copy_output = copy_message.read_text(
                        encoding="utf-8", errors="replace",
                    ).casefold()
                except OSError:
                    copy_output = ""
                if copied_size == source_size:
                    copy_error_class = "read_ok"
                elif "access is denied" in copy_output or "access denied" in copy_output:
                    copy_error_class = "access_denied"
                elif "cannot find the path" in copy_output or "path not found" in copy_output:
                    copy_error_class = "path_not_found"
                elif "cannot find the file" in copy_output or "file not found" in copy_output:
                    copy_error_class = "file_not_found"
                elif copy_output:
                    copy_error_class = "other_copy_error"
                else:
                    copy_error_class = "no_copy_diagnostic"
                error_class = "none"
                if result.error is not None:
                    error_class = (
                        result.error
                        if result.error in {
                            "timeout", "native_api_failed", "cleanup_failed", "job_creation_failed",
                        }
                        else "other_error"
                    )
                result_summary: dict[str, object] = {
                    "label": label,
                    "copy_script_started": copy_script_started,
                    "source_size": source_size,
                    "source_read_match": copied_size == source_size,
                    "copy_error_class": copy_error_class,
                    "executed": result.executed,
                    "exit_code": result.exit_code,
                    "error_class": error_class,
                    "cleanup_ok": result.cleanup_ok,
                    "copied_size": copied_size,
                }
                # Emit each bounded, path-free observation before assertions so an
                # early runtime/ACL failure cannot hide earlier file results.
                self._workflow_notice(
                    "Python runtime direct-read diagnostic",
                    json.dumps(result_summary, ensure_ascii=True, separators=(",", ":")),
                )
                self.assertTrue(result.executed, result)
                self.assertIsNone(result.error, result)
                self.assertTrue(result.cleanup_ok, result)
            self.assertTrue(
                result_summary["copy_script_started"],
                "AppContainer did not start the workspace-relative copy script",
            )

    @unittest.skipUnless(
        sys.platform == "win32"
        and os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("RUNNER_OS") == "Windows"
        and os.environ.get("ICODE_DIAGNOSTIC_RUNTIME_ACL") == "true",
        "host runtime ACL A/B 仅在显式启用的隔离诊断环境执行",
    )
    def test_诊断Python运行时只读ACL启动写入拒绝与精确恢复(self) -> None:
        """Mutate only hosted toolcache ACLs, then require byte-exact restoration."""
        with tempfile.TemporaryDirectory(prefix="icode-runtime-acl-native-") as raw:
            workspace = Path(raw) / "task"
            workspace.mkdir()
            marker = workspace / "python-runtime-started.txt"
            write_denied = workspace / "runtime-write-denied.txt"
            network_denied = workspace / "runtime-network-denied.txt"
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
                listener.bind(("127.0.0.1", 0))
                listener.listen(1)
                port = listener.getsockname()[1]
                script = (
                    "import os,pathlib,socket,sys,sysconfig,encodings\n"
                    "marker=pathlib.Path('python-runtime-started.txt')\n"
                    "stdlib=pathlib.Path(sysconfig.get_path('stdlib'))\n"
                    "files=[pathlib.Path(sys.executable),pathlib.Path(pathlib.__file__),"
                    "pathlib.Path(encodings.__file__)]\n"
                    "dll=sysconfig.get_config_var('DLLLIBRARY')\n"
                    "if dll: files.extend([pathlib.Path(sys.executable).parent/dll,"
                    "pathlib.Path(sys.base_prefix)/dll])\n"
                    "for item in files:\n"
                    "    if item.is_file(): item.read_bytes()\n"
                    "try:\n"
                    "    fd=os.open(pathlib.__file__,os.O_WRONLY|os.O_APPEND)\n"
                    "except OSError:\n"
                    "    pathlib.Path('runtime-write-denied.txt').write_text('true')\n"
                    "else:\n"
                    "    os.close(fd); raise SystemExit(73)\n"
                    "try:\n"
                    f"    socket.create_connection(('127.0.0.1',{port}),timeout=1)\n"
                    "except OSError:\n"
                    "    pathlib.Path('runtime-network-denied.txt').write_text('true')\n"
                    "else:\n"
                    "    raise SystemExit(74)\n"
                    "marker.write_text('started')\n"
                )
                argv = [sys.executable, "-I", "-c", script]
                baseline = run_windows_appcontainer(
                    argv, cwd=workspace, timeout_seconds=10, process_limit=4,
                )
                marker.unlink(missing_ok=True)
                write_denied.unlink(missing_ok=True)
                network_denied.unlink(missing_ok=True)
                candidate = run_windows_appcontainer(
                    argv, cwd=workspace, timeout_seconds=10, process_limit=4,
                    _diagnostic_runtime_acl=True,
                )

            summary = {
                "baseline_executed": baseline.executed,
                "baseline_exit": baseline.exit_code,
                "baseline_cleanup": baseline.cleanup_ok,
                "candidate_executed": candidate.executed,
                "candidate_exit": candidate.exit_code,
                "candidate_cleanup": candidate.cleanup_ok,
                "runtime_marker": marker.is_file(),
                "runtime_write_denied": write_denied.is_file(),
                "network_denied": network_denied.is_file(),
                "runtime_acl_restore_verified": "runtime_acl_restore_verified=true" in candidate.detail,
                "detail": candidate.detail,
            }
            self._workflow_notice(
                "Python runtime read-only ACL A/B",
                json.dumps(summary, ensure_ascii=True, separators=(",", ":")),
            )
            self.assertTrue(baseline.cleanup_ok, baseline)
            self.assertTrue(candidate.executed, candidate)
            self.assertEqual(candidate.exit_code, 0, candidate)
            self.assertTrue(marker.is_file(), "Python did not write its workspace marker")
            self.assertTrue(write_denied.is_file(), "runtime files unexpectedly accepted write-open")
            self.assertTrue(network_denied.is_file(), "runtime ACL altered the default-deny network boundary")
            self.assertTrue(candidate.cleanup_ok, candidate)
            self.assertIn("runtime_acl_restore_verified=true", candidate.detail)

    @unittest.skipUnless(
        sys.platform == "win32"
        and os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("RUNNER_OS") == "Windows"
        and os.environ.get("ICODE_DIAGNOSTIC_RUNTIME_STAGING") == "true",
        "disposable staged Python runtime 只在独立 Windows Actions 诊断步骤执行",
    )
    def test_诊断stagedPython运行时可读执行不可写且恢复清理(self) -> None:
        if Path(sys.prefix).resolve() != Path(sys.base_prefix).resolve():
            self.skipTest("CI 当前 Python 是 venv；该诊断要求固定 base runtime root")
        source_root = Path(sys.base_prefix).resolve(strict=True)
        source_executable = source_root / Path(sys.executable).name
        source_stdlib = Path(sysconfig.get_path("stdlib")).resolve(strict=True)
        source_probe = source_stdlib / "pathlib.py"
        self.assertTrue(source_executable.is_file(), "host Python executable is missing")
        self.assertTrue(source_probe.is_file(), "host Python stdlib sample is missing")

        temporary = tempfile.TemporaryDirectory(prefix="icode-runtime-stage-run-")
        temp_root = Path(temporary.name)
        workspace = temp_root / "task"
        workspace.mkdir()
        staged_root = temp_root / "icode-runtime-staging-copy"
        stage_summary: dict[str, int] = {}
        dacl_targets: list[Path] = []
        original_set_dacl = windows_appcontainer._set_dacl
        runtime_acl_snapshot = mock.Mock()
        runtime_acl_restore_report: dict[str, object] = {}
        original_restore_runtime_acl = windows_appcontainer._restore_runtime_acl_roots

        def record_dacl_target(
            path: Path, dacl: ctypes.c_void_p, advapi: ctypes.WinDLL,
        ) -> None:
            dacl_targets.append(Path(path).resolve(strict=True))
            original_set_dacl(path, dacl, advapi)

        try:
            try:
                stage_summary = windows_appcontainer._copy_runtime_tree_for_diagnostic(
                    source_root, staged_root,
                )
            except _AppContainerSetupError as exc:
                self._workflow_notice(
                    "Python runtime staging copy",
                    json.dumps({"copy_error": exc.error}, separators=(",", ":")),
                )
                self.fail(f"runtime staging failed closed: {exc.error}")

            staged_executable = staged_root / source_executable.name
            self.assertTrue(staged_executable.is_file(), "staged Python executable is missing")
            try:
                host_stage_probe = subprocess.run(
                    [
                        str(staged_executable), "-I", "-c",
                        "import _ctypes,_sqlite3,_ssl,ctypes,encodings,json,pathlib,platform,sqlite3,ssl; "
                        "print(json.dumps({'version':platform.python_version()}))",
                    ],
                    cwd=workspace, capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=10,
                    shell=False, check=False,
                )
                host_stage_probe_exit = host_stage_probe.returncode
                host_stage_probe_error = "none"
                try:
                    host_stage_version = json.loads(host_stage_probe.stdout).get("version")
                except (AttributeError, json.JSONDecodeError):
                    host_stage_version = None
            except subprocess.TimeoutExpired:
                host_stage_probe_exit = None
                host_stage_probe_error = "timeout"
                host_stage_version = None
            except OSError:
                host_stage_probe_exit = None
                host_stage_probe_error = "launch_failed"
                host_stage_version = None
            self._workflow_json_notice(
                "Python runtime staging host positive control",
                {
                    "executed": host_stage_probe_exit is not None,
                    "exit": host_stage_probe_exit,
                    "error": host_stage_probe_error,
                    "version": host_stage_version,
                },
            )
            self.assertEqual(
                host_stage_probe_exit, 0,
                f"staged Python did not pass its host positive control ({host_stage_probe_error})",
            )
            baseline_marker = workspace / "staging-baseline-started"
            baseline = run_windows_appcontainer(
                [
                    str(staged_executable), "-I", "-c",
                    "from pathlib import Path; Path('staging-baseline-started').write_text('started')",
                ],
                cwd=workspace, timeout_seconds=10, process_limit=4,
            )

            workspace_marker = workspace / "staging-workspace-write"
            script_started_marker = workspace / "staging-python-script-started"
            imports_completed_marker = workspace / "staging-python-imports-completed"
            paths_completed_marker = workspace / "staging-python-paths-completed"
            runtime_write_completed_marker = workspace / "staging-runtime-write-completed"
            source_read_completed_marker = workspace / "staging-source-read-completed"
            network_completed_marker = workspace / "staging-network-completed"
            python_failure_marker = workspace / "staging-python-failure-class"
            runtime_write_probe = staged_root / "staging-runtime-write-probe"
            runtime_write_marker = workspace / "staging-runtime-write-denied"
            child_marker = workspace / "staging-child-started"
            result_marker = workspace / "staging-result.json"
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
                listener.bind(("127.0.0.1", 0))
                listener.listen(1)
                listener.settimeout(1)
                port = listener.getsockname()[1]
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    accepted, _address = listener.accept()
                    accepted.close()

                child_script = (
                    "import _ctypes,_sqlite3,_ssl; from pathlib import Path; "
                    f"Path({str(child_marker)!r}).write_text('child-ok')"
                )
                script = (
                    "open('staging-python-script-started','w',encoding='ascii').write('1')\n"
                    "try:\n"
                    "    import _ctypes,_sqlite3,_ssl,ctypes,encodings,json,pathlib,"
                    "platform,socket,sqlite3,ssl,subprocess,sys,sysconfig; from pathlib import Path\n"
                    "except Exception as exc:\n"
                    "    open('staging-python-failure-class','w',encoding='ascii').write("
                    "'imports:'+type(exc).__name__)\n"
                    "    raise\n"
                    "def checkpoint(name): Path(name).write_text('1',encoding='ascii')\n"
                    "def failed(stage,exc): Path('staging-python-failure-class').write_text("
                    "stage+':'+type(exc).__name__,encoding='ascii')\n"
                    "checkpoint('staging-python-imports-completed')\n"
                    "try:\n"
                    "    root=Path(sys.executable).resolve(strict=True).parent\n"
                    "    modules=[pathlib,encodings,json,platform,ssl,sqlite3,_ctypes,_sqlite3,_ssl]\n"
                    "    module_roots=all(Path(m.__file__).absolute().is_relative_to(root) "
                    "for m in modules)\n"
                    "    prefix_ok=Path(sys.prefix).resolve(strict=True)==root\n"
                    "except Exception as exc:\n"
                    "    failed('runtime_path',exc)\n"
                    "    raise\n"
                    "checkpoint('staging-python-paths-completed')\n"
                    "try:\n"
                    f"    Path({str(runtime_write_probe)!r}).write_bytes(b'x')\n"
                    "except PermissionError:\n"
                    "    runtime_write_denied=True\n"
                    "except OSError as exc:\n"
                    "    failed('runtime_write',exc)\n"
                    "    raise\n"
                    "else:\n"
                    "    runtime_write_denied=False\n"
                    "if runtime_write_denied:\n"
                    f"    Path({str(runtime_write_marker)!r}).write_text('denied')\n"
                    "checkpoint('staging-runtime-write-completed')\n"
                    "try:\n"
                    f"    Path({str(source_probe)!r}).read_bytes()\n"
                    "except PermissionError:\n"
                    "    source_runtime_denied=True\n"
                    "except OSError as exc:\n"
                    "    failed('source_read',exc)\n"
                    "    raise\n"
                    "else:\n"
                    "    source_runtime_denied=False\n"
                    "checkpoint('staging-source-read-completed')\n"
                    "try:\n"
                    f"    socket.create_connection(('127.0.0.1',{port}),timeout=1)\n"
                    "except PermissionError:\n"
                    "    network_denied=True\n"
                    "except OSError as exc:\n"
                    "    failed('network',exc)\n"
                    "    raise\n"
                    "else:\n"
                    "    network_denied=False\n"
                    "checkpoint('staging-network-completed')\n"
                    "try:\n"
                    "    workspace=Path.cwd()\n"
                    f"    Path({str(workspace_marker)!r}).write_text('write-ok')\n"
                    "except Exception as exc:\n"
                    "    failed('workspace_write',exc)\n"
                    "    raise\n"
                    f"child_code={child_script!r}\n"
                    "try:\n"
                    "    child=subprocess.run([sys.executable,'-I','-c',child_code],"
                    "timeout=5,check=False)\n"
                    "except Exception as exc:\n"
                    "    failed('child_launch',exc)\n"
                    "    raise\n"
                    "result={'prefix_ok':prefix_ok,'module_roots':module_roots,"
                    "'python_version':platform.python_version(),"
                    "'runtime_write_denied':runtime_write_denied,"
                    "'source_runtime_denied':source_runtime_denied,"
                    "'network_denied':network_denied,'child_exit':child.returncode}\n"
                    f"Path({str(result_marker)!r}).write_text(json.dumps(result))\n"
                    "if not all((prefix_ok,module_roots,runtime_write_denied,"
                    "source_runtime_denied,network_denied,child.returncode==0)):\n"
                    "    raise SystemExit(78)\n"
                )
                try:
                    compile(script, "<staged-runtime-probe>", "exec")
                except SyntaxError:
                    self.fail("staged runtime probe script is syntactically invalid")
                with mock.patch(
                    "icode.windows_appcontainer._snapshot_runtime_acl_roots",
                    wraps=windows_appcontainer._snapshot_runtime_acl_roots,
                ) as runtime_acl_snapshot, mock.patch(
                    "icode.windows_appcontainer._set_dacl",
                    side_effect=record_dacl_target,
                ), mock.patch(
                    "icode.windows_appcontainer._restore_runtime_acl_roots",
                    side_effect=lambda transaction, sid: self._observe_runtime_acl_restore(
                        original_restore_runtime_acl,
                        transaction, sid, runtime_acl_restore_report,
                    ),
                ):
                    candidate = run_windows_appcontainer(
                        [str(staged_executable), "-I", "-c", script],
                        cwd=workspace, timeout_seconds=20, process_limit=4,
                        _diagnostic_runtime_acl=True,
                        _diagnostic_runtime_roots=(staged_root,),
                    )

            try:
                staged_result = json.loads(result_marker.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                staged_result = {}
            python_failure = "not_observed"
            try:
                raw_failure = python_failure_marker.read_text(encoding="ascii").strip()
            except OSError:
                raw_failure = ""
            allowed_failure_records = {
                f"{stage}:{error}"
                for stage in (
                    "imports", "runtime_path", "runtime_write", "source_read",
                    "network", "workspace_write", "child_launch",
                )
                for error in (
                    "AttributeError", "FileNotFoundError", "ImportError", "ModuleNotFoundError",
                    "NameError", "NotADirectoryError", "OSError", "PermissionError",
                    "RuntimeError", "TimeoutExpired", "TypeError", "ValueError",
                )
            }
            if raw_failure in allowed_failure_records:
                python_failure = raw_failure
            elif raw_failure:
                python_failure = "invalid_marker"
            runtime_write_probe.unlink(missing_ok=True)
            summary = {
                **stage_summary,
                "baseline_executed": baseline.executed,
                "baseline_exit": baseline.exit_code,
                "baseline_cleanup": baseline.cleanup_ok,
                "baseline_started": baseline_marker.is_file(),
                "candidate_executed": candidate.executed,
                "candidate_exit": candidate.exit_code,
                "candidate_error": candidate.error,
                "candidate_cleanup": candidate.cleanup_ok,
                "staged_python_version": staged_result.get("python_version"),
                "acl_baseline_normalization": (
                    candidate.detail.split(
                        "runtime_acl_baseline_normalized=true control_delta=", 1,
                    )[1].split(";", 1)[0]
                    if "runtime_acl_baseline_normalized=true control_delta=" in candidate.detail
                    else "not_observed"
                ),
                "python_script_started": script_started_marker.is_file(),
                "python_imports_completed": imports_completed_marker.is_file(),
                "python_paths_completed": paths_completed_marker.is_file(),
                "runtime_write_check_completed": runtime_write_completed_marker.is_file(),
                "source_read_check_completed": source_read_completed_marker.is_file(),
                "network_check_completed": network_completed_marker.is_file(),
                "python_failure": python_failure,
                "runtime_marker": candidate.executed and candidate.exit_code == 0,
                "workspace_write": workspace_marker.is_file(),
                "runtime_write_denied": runtime_write_marker.is_file()
                or staged_result.get("runtime_write_denied") is True,
                "source_runtime_denied": staged_result.get("source_runtime_denied") is True,
                "network_denied": staged_result.get("network_denied") is True,
                "module_roots": staged_result.get("module_roots") is True,
                "prefix_ok": staged_result.get("prefix_ok") is True,
                "child_started": child_marker.is_file(),
                "acl_restore_verified": "runtime_acl_restore_verified=true" in candidate.detail,
                "acl_roots_are_staged": runtime_acl_snapshot.call_args is not None
                and runtime_acl_snapshot.call_args.args[0] == (staged_root.resolve(),),
                "source_acl_untouched": not any(
                    path == source_root
                    or path.is_relative_to(source_root)
                    or source_root.is_relative_to(path)
                    for path in dacl_targets
                ),
                "candidate_detail_flags": [
                    label for label, marker in (
                        ("runtime_acl_snapshot", "runtime_acl_snapshot="),
                        ("runtime_acl_baseline_normalized", "runtime_acl_baseline_normalized=true"),
                        ("runtime_acl_access_granted", "runtime_acl_access=read_execute"),
                        ("runtime_acl_restore_verified", "runtime_acl_restore_verified=true"),
                        ("runtime_acl_restore_failed", "runtime_acl_restore_failed"),
                        ("workspace_acl_restore_failed", "workspace_acl_restore_failed"),
                        ("workspace_acl_revocation_unverified", "workspace_acl_revocation_unverified"),
                        ("profile_storage_residual", "profile_storage_residual"),
                        ("profile_storage_unverified", "profile_storage_unverified"),
                        ("profile_delete_failed", "profile_delete_failed"),
                        ("sid_release_failed", "sid_release_failed"),
                        ("job_terminate_failed", "TerminateJobObject err="),
                        ("job_query_failed", "QueryInformationJobObject err="),
                    ) if marker in candidate.detail
                ],
                "runtime_acl_restore_report": runtime_acl_restore_report or {"state": "not_observed"},
            }
            self._workflow_json_notice(
                "Python disposable staging inventory",
                {
                    "source_entries": summary.get("source_entries"),
                    "materialized_links": summary.get("materialized_links"),
                    "staged_entries": summary.get("staged_entries"),
                    "host_python_version": host_stage_version,
                },
            )
            self._workflow_json_notice(
                "Python disposable staging lifecycle",
                {
                    "baseline_executed": summary["baseline_executed"],
                    "baseline_exit": summary["baseline_exit"],
                    "baseline_cleanup": summary["baseline_cleanup"],
                    "baseline_started": summary["baseline_started"],
                    "candidate_executed": summary["candidate_executed"],
                    "candidate_exit": summary["candidate_exit"],
                    "candidate_error": summary["candidate_error"],
                    "candidate_cleanup": summary["candidate_cleanup"],
                    "staged_python_version": summary["staged_python_version"],
                },
            )
            self._workflow_json_notice(
                "Python disposable staging cleanup diagnostics",
                {"detail_flags": summary["candidate_detail_flags"]},
            )
            self._workflow_json_notice(
                "Python disposable staging ACL mismatch classification",
                summary["runtime_acl_restore_report"],
            )
            self._workflow_json_notice(
                "Python disposable staging script checkpoints",
                {
                    "script_started": summary["python_script_started"],
                    "imports_completed": summary["python_imports_completed"],
                    "paths_completed": summary["python_paths_completed"],
                    "runtime_write_check_completed": summary["runtime_write_check_completed"],
                    "source_read_check_completed": summary["source_read_check_completed"],
                    "network_check_completed": summary["network_check_completed"],
                    "python_failure": summary["python_failure"],
                },
            )
            self._workflow_json_notice(
                "Python disposable staging boundary assertions",
                {
                    "acl_restore_verified": summary["acl_restore_verified"],
                    "acl_baseline_normalization_delta": summary["acl_baseline_normalization"],
                    "acl_roots_are_staged": summary["acl_roots_are_staged"],
                    "source_acl_untouched": summary["source_acl_untouched"],
                    "runtime_marker": summary["runtime_marker"],
                    "workspace_write": summary["workspace_write"],
                    "runtime_write_denied": summary["runtime_write_denied"],
                    "source_runtime_denied": summary["source_runtime_denied"],
                    "network_denied": summary["network_denied"],
                    "module_roots": summary["module_roots"],
                    "prefix_ok": summary["prefix_ok"],
                    "child_started": summary["child_started"],
                },
            )
        finally:
            temporary.cleanup()

        stage_deleted = not temp_root.exists()
        self._workflow_json_notice(
            "Python disposable staging deletion",
            {"staging_removed": stage_deleted},
        )
        self.assertTrue(baseline.cleanup_ok, "baseline AppContainer cleanup failed")
        self.assertFalse(summary["baseline_started"], "AppContainer read staged runtime before grant")
        self.assertTrue(candidate.executed, "staged AppContainer process did not start")
        self.assertEqual(candidate.exit_code, 0, "staged runtime probe did not complete")
        self.assertTrue(candidate.cleanup_ok, "staged AppContainer cleanup failed")
        self.assertTrue(summary["python_script_started"], "staged Python never entered its command script")
        self.assertIn(
            summary["acl_baseline_normalization"], {"0", "1024"},
            "staging ACL baseline normalization was not verified",
        )
        self.assertTrue(summary["acl_restore_verified"], "staged runtime DACL was not exactly restored")
        self.assertTrue(summary["acl_roots_are_staged"], "runtime ACL transaction escaped the staging root")
        self.assertTrue(summary["source_acl_untouched"], "source runtime ACL was modified")
        self.assertTrue(summary["workspace_write"], "AppContainer could not write its task workspace")
        self.assertTrue(summary["runtime_write_denied"], "staged runtime accepted a write")
        self.assertTrue(summary["source_runtime_denied"], "AppContainer read the original runtime")
        self.assertTrue(summary["network_denied"], "staging changed the default-deny network boundary")
        self.assertTrue(summary["module_roots"], "Python imported a module outside the staged runtime")
        self.assertTrue(summary["prefix_ok"], "staged Python resolved its prefix outside the staging root")
        self.assertTrue(summary["child_started"], "staged Python child process did not start")
        self.assertTrue(stage_deleted, "staged runtime directory remains after cleanup")

    @unittest.skipUnless(sys.platform == "win32", "需 Windows AppContainer 原生实测")
    def test_在AppContainer中运行Python并解析工作路径(self) -> None:
        """Verify the host Python runtime and path behavior, not only System32 tools."""
        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-python-") as raw:
            root = Path(raw).resolve()
            workspace = root / "task"
            workspace.mkdir()
            marker = workspace / "python-probe.json"
            profile_paths: list[str] = []

            def get_profile_path(
                sid: ctypes.c_void_p,
                userenv: ctypes.WinDLL,
                advapi: ctypes.WinDLL,
                kernel: ctypes.WinDLL,
                ole32: ctypes.WinDLL,
            ) -> str:
                path = _get_appcontainer_localappdata_path(
                    sid, userenv, advapi, kernel, ole32,
                )
                profile_paths.append(path)
                return path

            probe = (
                "import json\n"
                "from pathlib import Path\n"
                "import sys\n"
                "import os\n"
                "result = {}\n"
                "for label, value in [('cwd', Path.cwd()), ('executable', Path(sys.executable))]:\n"
                "    try:\n"
                "        result[label] = str(value.resolve(strict=True))\n"
                "    except Exception as exc:\n"
                "        result[label] = f'{type(exc).__name__}: {exc}'\n"
                "profile_marker = Path(os.environ['LOCALAPPDATA']) / 'icode-profile-lifecycle-probe'\n"
                "profile_marker.write_text('temporary', encoding='utf-8')\n"
                f"Path({str(marker)!r}).write_text(json.dumps(result), encoding='utf-8')\n"
            )
            with mock.patch(
                "icode.windows_appcontainer._get_appcontainer_localappdata_path",
                side_effect=get_profile_path,
            ):
                result = run_windows_appcontainer(
                    [sys.executable, "-S", "-c", probe],
                    cwd=workspace, timeout_seconds=15, process_limit=4,
                )
            self._workflow_notice(
                "Python runtime",
                f"executed={result.executed} exit={result.exit_code} error={result.error} "
                f"cleanup={result.cleanup_ok} detail={result.detail}",
            )
            self.assertTrue(result.executed, result)
            self.assertEqual(result.exit_code, 0, result)
            self.assertTrue(result.cleanup_ok, result)
            self.assertTrue(marker.is_file(), "AppContainer Python did not write its workspace marker")
            path_result = marker.read_text(encoding="utf-8")
            self._workflow_notice("Python path resolution", path_result)
            resolved = json.loads(path_result)
            self.assertEqual(set(resolved), {"cwd", "executable"})
            self.assertEqual(len(profile_paths), 1)
            self.assertFalse(
                Path(profile_paths[0]).exists(),
                "容器退出后 profile 私有数据目录必须已删除",
            )
            for label, value in resolved.items():
                self.assertTrue(
                    Path(value).is_absolute(),
                    f"AppContainer could not resolve {label}: {value}",
                )

    @unittest.skipUnless(sys.platform == "win32", "需 Windows AppContainer 原生实测")
    def test_工作区ACL与容器profile隔离且默认拒绝网络(self) -> None:
        requests: list[str] = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - 标准库接口名
                requests.append(self.path)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"host-positive-control")

            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                pass

        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-test-") as raw:
            root = Path(raw).resolve()
            workspace = root / "task"
            workspace.mkdir()
            nested = workspace / "existing" / "nested"
            nested.mkdir(parents=True)
            (nested / "input.txt").write_text("existing-workspace-file", encoding="utf-8")
            outside_secret = root / "outside-secret.txt"
            outside_secret.write_text("must-not-enter-appcontainer", encoding="utf-8")
            outside_write = root / "outside-write.txt"

            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            url = f"http://127.0.0.1:{server.server_port}/probe"
            try:
                # 宿主正向对照：listener 确实可达，沙箱负例才有解释力。
                parsed = urlsplit(url)
                connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=3)
                connection.request("GET", parsed.path)
                response = connection.getresponse()
                self.assertEqual(response.read(), b"host-positive-control")
                connection.close()
                self.assertEqual(requests, ["/probe"])
                requests.clear()
                self._workflow_notice("host loopback positive control", "listener reachable")

                system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
                curl = system_root / "System32" / "curl.exe"
                command = system_root / "System32" / "cmd.exe"
                self.assertTrue(curl.is_file(), "Windows 目标环境需提供系统 curl.exe")
                inline_marker = workspace / "inline-write.txt"
                inline_write = run_windows_appcontainer(
                    [
                        str(command), "/d", "/c",
                        "echo inline-write-ok> inline-write.txt",
                    ],
                    cwd=workspace, timeout_seconds=8, process_limit=2,
                )
                self._workflow_notice(
                    "AppContainer relative cwd write control",
                    f"executed={inline_write.executed} exit={inline_write.exit_code} "
                    f"error={inline_write.error} cleanup={inline_write.cleanup_ok} "
                    f"marker={inline_marker.is_file()}",
                )
                self.assertTrue(inline_write.executed, inline_write)
                self.assertEqual(inline_write.exit_code, 0, inline_write)
                self.assertTrue(inline_write.cleanup_ok, inline_write)
                self.assertEqual(inline_marker.read_text(encoding="utf-8").strip(), "inline-write-ok")

                allowed_write = workspace / "new-output.txt"
                copied_secret = workspace / "outside-copy.txt"
                copied_nested = workspace / "nested-copy.txt"
                child_started = workspace / "child-started.txt"
                child_late = workspace / "child-late.txt"
                child_release = workspace / "child-release.txt"
                child_launch_log = workspace / "child-launch.log"
                script_complete = workspace / "probe-script-complete.txt"
                child_script = workspace / "child.cmd"
                child_script.write_text(
                    "@echo off\r\n"
                    f'echo started> "{child_started.name}"\r\n'
                    ":wait_for_release\r\n"
                    f'if not exist "{child_release.name}" goto wait_for_release\r\n'
                    f'echo late> "{child_late.name}"\r\n',
                    encoding="utf-8",
                )
                # Prove the exact child payload can observe release and write its
                # late marker when it is not under the AppContainer Job.
                host_control = subprocess.Popen(
                    [str(command), "/d", "/c", f".\\{child_script.name}"],
                    cwd=workspace,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                try:
                    deadline = time.monotonic() + 10
                    while (
                        not child_started.is_file()
                        and host_control.poll() is None
                        and time.monotonic() < deadline
                    ):
                        time.sleep(0.05)
                    self.assertTrue(
                        child_started.is_file(),
                        "host positive control did not start the descendant",
                    )
                    child_release.write_text("release", encoding="utf-8")
                    deadline = time.monotonic() + 5
                    while not child_late.is_file() and time.monotonic() < deadline:
                        time.sleep(0.05)
                    self.assertTrue(
                        child_late.is_file(),
                        "host positive control did not write the late marker",
                    )
                    host_control.wait(timeout=5)
                    self.assertEqual(host_control.returncode, 0)
                finally:
                    if not child_release.exists():
                        child_release.write_text("release", encoding="utf-8")
                    try:
                        host_control.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        host_control.kill()
                        host_control.wait(timeout=5)
                self._workflow_notice(
                    "descendant payload positive control",
                    f"started={child_started.is_file()} late_marker={child_late.is_file()} "
                    f"exit={host_control.returncode}",
                )
                child_started.unlink(missing_ok=True)
                child_late.unlink(missing_ok=True)
                child_release.unlink(missing_ok=True)
                script = workspace / "probe.cmd"
                script.write_text(
                    "@echo off\r\n"
                    f'echo workspace-write-ok> "{allowed_write.name}"\r\n'
                    f'type "{os.path.relpath(nested / "input.txt", workspace)}" '
                    f'> "{copied_nested.name}"\r\n'
                    f'type "{os.path.relpath(outside_secret, workspace)}" '
                    f'> "{copied_secret.name}"\r\n'
                    f'echo escape> "{os.path.relpath(outside_write, workspace)}"\r\n'
                    f'"{curl}" --noproxy "*" --connect-timeout 1 --max-time 2 '
                    f'"{url}" > "network.txt" 2>&1\r\n'
                    f'start "" /b cmd.exe /d /c .\\{child_script.name} '
                    f'> "{child_launch_log.name}" 2>&1\r\n'
                    ":wait_for_child\r\n"
                    f'if not exist "{child_started.name}" goto wait_for_child\r\n'
                    f'echo reached-end> "{script_complete.name}"\r\n'
                    "exit /b 0\r\n",
                    encoding="utf-8",
                )
                # Use a cwd-relative entry point so access stays within the task ACL.
                result = run_windows_appcontainer(
                    [str(command), "/d", "/c", f".\\{script.name}"],
                    cwd=workspace, timeout_seconds=12, process_limit=8,
                )
                try:
                    child_launch_output = child_launch_log.read_text(
                        encoding="utf-8", errors="replace",
                    ).casefold()
                except OSError:
                    child_launch_output = ""
                if "access is denied" in child_launch_output or "access denied" in child_launch_output:
                    child_launch_error_class = "access_denied"
                elif "not recognized" in child_launch_output or "cannot find" in child_launch_output:
                    child_launch_error_class = "command_or_script_not_found"
                elif child_launch_output:
                    child_launch_error_class = "other_output"
                else:
                    child_launch_error_class = "no_output"
                self._workflow_notice(
                    "workspace and network probe",
                    f"executed={result.executed} exit={result.exit_code} error={result.error} "
                    f"cleanup={result.cleanup_ok} script_complete={script_complete.is_file()} "
                    f"workspace_write={allowed_write.is_file()} nested_copy={copied_nested.is_file()} "
                    f"outside_write={outside_write.exists()} child_started={child_started.is_file()} "
                    f"child_launch_log={child_launch_log.is_file()} "
                    f"child_launch_error_class={child_launch_error_class} detail={result.detail}",
                )

                self.assertTrue(result.executed, result)
                self.assertIsNone(result.error, result)
                self.assertTrue(result.cleanup_ok, result)
                self.assertTrue(
                    script_complete.is_file(),
                    "AppContainer workspace probe did not reach its completion marker",
                )
                self.assertEqual(result.exit_code, 0, result)
                self.assertEqual(allowed_write.read_text(encoding="utf-8").strip(), "workspace-write-ok")
                self.assertEqual(
                    (nested / "input.txt").read_text(encoding="utf-8"),
                    "existing-workspace-file",
                )
                self.assertEqual(
                    copied_nested.read_text(encoding="utf-8").strip(),
                    "existing-workspace-file",
                )
                self.assertNotIn("must-not-enter-appcontainer", copied_secret.read_text(encoding="utf-8"))
                self.assertFalse(outside_write.exists())
                self.assertEqual(requests, [], "AppContainer unexpectedly reached localhost")
                self.assertTrue(
                    child_started.is_file(),
                    "AppContainer descendant did not start; check the bounded launch diagnostic",
                )
                child_release.write_text("release", encoding="utf-8")
                deadline = time.monotonic() + 5
                while not child_late.is_file() and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertFalse(child_late.exists(), "AppContainer Job left a descendant alive")

                child_started.unlink()
                child_late.unlink(missing_ok=True)
                child_release.unlink(missing_ok=True)
                timeout_script = workspace / "timeout-parent.cmd"
                timeout_script.write_text(
                    "@echo off\r\n"
                    f'start "" /b cmd.exe /d /c .\\{child_script.name}\r\n'
                    ":hold\r\n"
                    "goto hold\r\n",
                    encoding="utf-8",
                )
                timed_out = run_windows_appcontainer(
                    [str(command), "/d", "/c", f".\\{timeout_script.name}"],
                    cwd=workspace, timeout_seconds=2, process_limit=8,
                )
                self._workflow_notice(
                    "timeout cleanup probe",
                    f"executed={timed_out.executed} error={timed_out.error} "
                    f"cleanup={timed_out.cleanup_ok} detail={timed_out.detail}",
                )
                self.assertTrue(timed_out.executed, timed_out)
                self.assertEqual(timed_out.error, "timeout", timed_out)
                self.assertTrue(timed_out.cleanup_ok, timed_out)
                self.assertTrue(child_started.is_file(), "timeout descendant did not start")
                child_release.write_text("release", encoding="utf-8")
                deadline = time.monotonic() + 5
                while not child_late.is_file() and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertFalse(child_late.exists(), "timeout left an AppContainer descendant alive")

                limited_marker = workspace / "process-limit-child.txt"
                limited_parent_attempted = workspace / "process-limit-parent-attempted.txt"
                limited_status = workspace / "process-limit-launch-status.txt"
                limited_child = workspace / "process-limit-child.cmd"
                limited_child.write_text(
                    "@echo off\r\n"
                    f'echo escaped> "{limited_marker.name}"\r\n'
                    "exit /b 0\r\n",
                    encoding="utf-8",
                )
                limited_parent = workspace / "process-limit-parent.cmd"
                # Keep whitespace before `>` so CMD does not treat a status digit as an FD.
                limited_parent.write_text(
                    "@echo off\r\n"
                    f'echo attempted> "{limited_parent_attempted.name}"\r\n'
                    f'cmd.exe /d /c .\\{limited_child.name}\r\n'
                    f'echo exit_code=%errorlevel% > "{limited_status.name}"\r\n'
                    "exit /b 0\r\n",
                    encoding="utf-8",
                )
                limit_control = run_windows_appcontainer(
                    [str(command), "/d", "/c", f".\\{limited_parent.name}"],
                    cwd=workspace, timeout_seconds=5, process_limit=2,
                )
                positive_launch_status = self._read_cmd_exit_status(limited_status)
                self._workflow_notice(
                    "process limit positive control",
                    f"executed={limit_control.executed} exit={limit_control.exit_code} "
                    f"cleanup={limit_control.cleanup_ok} "
                    f"parent_attempted={limited_parent_attempted.is_file()} "
                    f"child_marker={limited_marker.is_file()} "
                    f"launch_status={positive_launch_status}",
                )
                self.assertTrue(limit_control.executed, limit_control)
                self.assertEqual(limit_control.exit_code, 0, limit_control)
                self.assertTrue(limit_control.cleanup_ok, limit_control)
                self.assertTrue(limited_parent_attempted.is_file(), "parent spawn attempt was not recorded")
                self.assertTrue(
                    limited_marker.is_file(),
                    "the process-limit payload must start without the one-process cap",
                )
                self.assertEqual(positive_launch_status, 0, "positive child launch must succeed")
                limited_marker.unlink()
                limited_parent_attempted.unlink()
                limited_status.unlink(missing_ok=True)
                limited = run_windows_appcontainer(
                    [str(command), "/d", "/c", f".\\{limited_parent.name}"],
                    cwd=workspace, timeout_seconds=5, process_limit=1,
                )
                negative_launch_status = self._read_cmd_exit_status(limited_status)
                self._workflow_notice(
                    "process limit probe",
                    f"executed={limited.executed} exit={limited.exit_code} error={limited.error} "
                    f"cleanup={limited.cleanup_ok} "
                    f"parent_attempted={limited_parent_attempted.is_file()} "
                    f"child_marker={limited_marker.is_file()} "
                    f"launch_status={negative_launch_status} detail={limited.detail}",
                )
                self.assertTrue(limited.executed, limited)
                self.assertEqual(limited.exit_code, 0, limited)
                self.assertTrue(limited.cleanup_ok, limited)
                self.assertTrue(limited_parent_attempted.is_file(), "parent did not reach child creation")
                self.assertFalse(limited_marker.exists(), "Job active-process limit was not enforced")
                self.assertIsNotNone(negative_launch_status, "child launch result was not recorded")
                self.assertNotEqual(negative_launch_status, 0, "one-process cap must reject child creation")
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
