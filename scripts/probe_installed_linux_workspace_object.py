"""Exercise session-owned workspace objects using only an installed wheel."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile


class ProbeFailure(RuntimeError):
    """Only fixed classifications may reach the public CI log."""


def _require(condition: bool, category: str) -> None:
    if not condition:
        raise ProbeFailure(category)


def _probe() -> None:
    import icode
    from icode.isolation import LandlockSandbox, PreparedCommand
    from icode.tools import ToolContext, default_registry
    from icode.workspace import WorkspaceManager

    _require(sys.platform.startswith("linux"), "unsupported_platform")
    installed = Path(icode.__file__).resolve()
    checkout = Path(__file__).resolve().parents[1]
    _require("site-packages" in installed.parts and not installed.is_relative_to(checkout),
             "package_not_installed")
    sandbox = LandlockSandbox.from_bundle()
    _require(sandbox is not None and sandbox.manifest is not None, "bundled_helper_missing")
    package_root = installed.parent
    helper = Path(sandbox.helper).resolve(strict=True)
    manifest = Path(sandbox.manifest).resolve(strict=True)
    _require(helper.is_relative_to(package_root) and manifest.is_relative_to(package_root)
             and not helper.is_relative_to(checkout) and not manifest.is_relative_to(checkout),
             "helper_not_from_installed_package")
    _require(not sandbox.policy_contract_ready, "unexpected_readiness")

    with tempfile.TemporaryDirectory(prefix="icode-wheel-workspace-object-") as raw:
        root = Path(raw).resolve()
        source = root / "源码 source"
        source.mkdir()
        (source / "source.py").write_text("VALUE = 1\n", encoding="utf-8")
        git_env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        git_env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        for arguments in (("init", "-q"), ("add", "source.py"), ("commit", "-qm", "base")):
            subprocess.run(
                ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false",
                 "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "-C", str(source), *arguments],
                env=git_env, check=True, capture_output=True, timeout=15,
            )
        manager = WorkspaceManager(source, root / "data", "wheel-object", isolate_git_metadata=True)
        with manager.open("wheel-object", "wheel-object-run") as session:
            descriptor = session.workspace_fd
            _require(type(descriptor) is int and descriptor >= 3, "session_object_missing")
            status = os.fstat(descriptor)
            _require(session.workspace_fd_identity == (status.st_dev, status.st_ino),
                     "session_identity_mismatch")
            context = ToolContext(session.workspace_root, sandbox=sandbox,
                                  policy=session.policy("code", process_limit=1),
                                  workspace_session=session)
            prepared = context.wrap_command([sys.executable, "-I", "-c", "print('unused')"])
            _require(isinstance(prepared, PreparedCommand) and prepared.pass_fds == (descriptor,)
                     and prepared.cwd == "/", "workspace_launch_metadata_missing")
            context.close()
            _require(os.fstat(descriptor).st_ino == status.st_ino, "borrower_closed_owner")

            def execute(code: str, timeout: int = 5):
                return default_registry().invoke("run_command", context,
                    {"argv": [sys.executable, "-I", "-c", code], "timeout": timeout})

            positive = execute(
                "import errno,os\n"
                f"try: os.fstat({descriptor})\n"
                "except OSError as error: assert error.errno == errno.EBADF\n"
                "else: raise AssertionError('host root descriptor inherited')\n"
                "assert open('source.py').read() == 'VALUE = 1\\n'\n"
                "open('created','w').write('installed-object')\n"
                "try: child=os.fork()\n"
                "except OSError as error: assert error.errno == errno.EAGAIN\n"
                "else:\n"
                " if child == 0: os._exit(23)\n"
                " os.waitpid(child,0); raise AssertionError('quota missing')\n")
            _require(positive.ok, "workspace_resource_execution_failed")
            _require((session.workspace_root / "created").read_text() == "installed-object",
                     "workspace_write_missing")
            receipt = positive.meta.get("resource_receipt", {})
            _require(receipt.get("limit") == 1 and receipt.get("configured") is True
                     and receipt.get("channel_status") == "complete"
                     and receipt.get("terminal") == "finished", "resource_receipt_incomplete")
            _require(positive.meta.get("scope_cleanup_ok") is True
                     and positive.meta.get("violation_observer_status") == "complete",
                     "workspace_observer_or_cleanup_failed")

            timed = execute("import time; open('started','w').write('ok'); time.sleep(30)", timeout=1)
            _require(not timed.ok and timed.meta.get("error") == "timeout", "timeout_not_enforced")
            _require(timed.meta.get("cleanup_ok") is True and timed.meta.get("scope_cleanup_ok") is True,
                     "timeout_cleanup_failed")
            _require((session.workspace_root / "started").is_file(), "timeout_payload_not_observed")
            _require(os.fstat(descriptor).st_ino == status.st_ino, "owner_lost_after_timeout")

            # Freeze the native claim, then fault-inject a matching new FD/path.
            # The receiving helper must reject the original dev/inode mismatch.
            rejected = context.wrap_command([sys.executable, "-I", "-c",
                                             "open('must-not-run','w').write('bad')"])
            original = session.workspace_root.with_name("original-code")
            session.workspace_root.rename(original)
            session.workspace_root.mkdir()
            os.close(descriptor)
            replacement = os.open(session.workspace_root, os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
            if replacement != descriptor:
                try:
                    os.dup2(replacement, descriptor, inheritable=False)
                finally:
                    os.close(replacement)
            result = subprocess.run(rejected, pass_fds=rejected.pass_fds, cwd=rejected.cwd,
                                    capture_output=True, timeout=8)
            _require(result.returncode != 0
                     and b"workspace FD does not match directory object" in result.stderr,
                     "native_frozen_identity_not_checked")
            _require(not (original / "must-not-run").exists()
                     and not (session.workspace_root / "must-not-run").exists(),
                     "identity_rejection_started_payload")
        _require(session.workspace_fd is None, "session_object_not_released")


def main() -> int:
    try:
        _probe()
    except ProbeFailure as error:
        print(f"::error::{error}")
        return 1
    except Exception as error:  # noqa: BLE001 - paths/commands never reach public logs.
        print(f"::error::unexpected_{type(error).__name__}")
        return 1
    print("installed wheel session workspace object, task quota and cleanup: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
