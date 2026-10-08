"""Verify the OS-enforced command-denial receipt from an installed wheel."""

from __future__ import annotations

import sys
from dataclasses import replace
import tempfile
from pathlib import Path


class ProbeFailure(RuntimeError):
    """A path-free failure classification for CI output."""


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ProbeFailure(code)


def _run_command(context: object, source: str):
    from icode.tools import default_registry

    return default_registry().invoke(
        "run_command",
        context,
        {"argv": [sys.executable, "-c", source], "timeout": 5},
    )


def _probe() -> None:
    if not sys.platform.startswith("linux"):
        raise ProbeFailure("unsupported_platform")

    import icode
    from icode.isolation import LandlockSandbox, probe_native_sandbox
    from icode.sandbox_policy import NetworkMode, SandboxPolicy
    from icode.tools import POLICY_DENIED_USER_MESSAGE, ToolContext

    package_path = Path(icode.__file__).resolve()
    checkout_root = Path(__file__).resolve().parents[1]
    _require("site-packages" in package_path.parts, "package_not_installed_in_venv")
    _require(not package_path.is_relative_to(checkout_root), "package_loaded_from_checkout")

    sandbox = LandlockSandbox.from_bundle()
    _require(sandbox is not None, "installed_landlock_helper_missing")
    _require(sandbox.manifest is not None, "installed_landlock_manifest_missing")
    native_probe = probe_native_sandbox(sandbox)
    _require(native_probe.ready, "installed_landlock_probe_failed")

    with tempfile.TemporaryDirectory(prefix="icode-wheel-receipt-") as raw:
        workspace = Path(raw).resolve()
        policy = SandboxPolicy(
            schema_version=1,
            run_id="installed-wheel-receipt",
            ticket_id="installed-wheel-receipt",
            step="code",
            workspace_root=workspace,
            read_roots=(workspace,),
            write_roots=(workspace,),
            deny_read_roots=(),
            deny_write_roots=(),
            network_mode=NetworkMode.DENY,
            allowed_domains=(),
            process_limit=8,
            wall_timeout_seconds=8,
            output_limit_bytes=1024,
            protected_paths=(),
        )
        context = ToolContext(root=workspace, sandbox=sandbox, policy=policy)

        denied = _run_command(
            context,
            "import socket; socket.socket(socket.AF_INET, socket.SOCK_STREAM)",
        )
        expected_receipt = {
            "schema_version": 1,
            "enforcement_layer": "os_seccomp_user_notif",
            "os_enforced": True,
            "category": "network_socket",
            "source": "seccomp_user_notif",
            "count": 1,
        }
        _require(not denied.ok, "network_socket_deny_succeeded")
        _require(
            denied.content == POLICY_DENIED_USER_MESSAGE,
            "unsafe_denial_message",
        )
        _require(
            denied.meta.get("error_code") == "policy_denied",
            "stable_denial_code_missing",
        )
        _require(
            denied.meta.get("violation_observer_status") == "complete",
            "native_observer_incomplete",
        )
        _require(
            denied.meta.get("violation_receipt") == expected_receipt,
            "native_receipt_mismatch",
        )
        denied_meta = repr(denied.meta)
        _require("AF_INET" not in denied_meta, "raw_operation_leaked")
        _require(str(workspace) not in denied_meta, "workspace_path_leaked")

        allowed = _run_command(
            context,
            "import socket; left, right = socket.socketpair(socket.AF_UNIX); "
            "left.sendall(b'ok'); assert right.recv(2) == b'ok'; "
            "left.close(); right.close()",
        )
        _require(allowed.ok, "unix_socket_positive_control_failed")
        _require(
            allowed.meta.get("violation_observer_status") == "complete",
            "positive_control_observer_incomplete",
        )
        _require("violation_receipt" not in allowed.meta, "positive_control_misclassified")
        _require(allowed.meta.get("resource_receipt", {}).get("configured") is True,
                 "positive_control_quota_unconfigured")
        _require(allowed.meta.get("scope_cleanup_ok") is True, "positive_control_scope_not_collected")
        _require(allowed.meta.get("payload_started") is None, "positive_control_invented_exec_evidence")

        quota_context = ToolContext(root=workspace, sandbox=sandbox,
                                    policy=replace(policy, process_limit=1))
        quota = _run_command(quota_context,
            "import errno,os\n"
            "try: child=os.fork()\n"
            "except OSError as error: assert error.errno==errno.EAGAIN\n"
            "else:\n"
            " if child==0: os._exit(0)\n"
            " os.waitpid(child,0);raise AssertionError('quota absent')\n")
        _require(quota.ok, "installed_root_payload_quota_not_enforced")
        _require(quota.meta.get("resource_receipt", {}).get("limit") == 1,
                 "installed_quota_limit_mismatch")
        _require(quota.meta.get("scope_cleanup_ok") is True, "installed_quota_scope_not_collected")
        _require(quota.meta.get("payload_started") is None, "installed_quota_invented_exec_evidence")

        ordinary_failure = _run_command(context, "raise SystemExit(13)")
        _require(not ordinary_failure.ok, "ordinary_exit_13_succeeded")
        _require(ordinary_failure.meta.get("exit_code") == 13, "ordinary_exit_code_lost")
        _require(
            ordinary_failure.meta.get("violation_observer_status") == "complete",
            "ordinary_failure_observer_incomplete",
        )
        _require("error_code" not in ordinary_failure.meta, "ordinary_exit_misclassified")
        _require(
            "violation_receipt" not in ordinary_failure.meta,
            "ordinary_exit_emitted_native_receipt",
        )


def main() -> int:
    try:
        _probe()
    except ProbeFailure as exc:
        print(f"::error::{exc}")
        return 1
    except Exception as exc:  # noqa: BLE001 - CI output must not leak command/path details.
        print(f"::error::unexpected_{type(exc).__name__}")
        return 1
    print("installed wheel USER_NOTIF receipt and registry task quota: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
