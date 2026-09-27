"""R2 策略命令的宿主侧启动与回收，不代替 OS 文件/网络隔离。"""

from __future__ import annotations

import errno
import math
import os
import selectors
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .sandbox_policy import SandboxPolicy

_READ_CHUNK_BYTES = 64 * 1024
_CLEANUP_TIMEOUT_SECONDS = 1


@dataclass(frozen=True)
class ExecutionResult:
    exit_code: int | None
    output: str
    output_bytes: int
    error: str | None
    output_truncated: bool
    cleanup_ok: bool
    cleanup_errno: int | None
    raw_output: bytes = b""


def _policy_environment(root: Path, *, git_status: bool = False) -> dict[str, str]:
    """只传运行必需的显式变量，避免模型命令继承宿主密钥与凭据。"""
    paths = [str(Path(sys.executable).parent)]
    paths.extend(
        part for part in os.environ.get("PATH", os.defpath).split(os.pathsep)
        if Path(part).is_absolute()
    )
    environment = {
        "PATH": os.pathsep.join(dict.fromkeys(paths)),
        "HOME": str(root),
        "TMPDIR": str(root),
        "LANG": "C",
        "PYTHONUTF8": "1",
        "PYTHONNOUSERSITE": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
    }
    # src 布局是本地 Python 工程常见形态；只从当前工作区派生，不继承宿主 PYTHONPATH。
    source_dir = root / "src"
    if source_dir.is_dir() and source_dir.resolve().is_relative_to(root):
        environment["PYTHONPATH"] = str(source_dir)
    if git_status:
        # Git status is a fixed internal query; never inherit host Git controls
        # or search user-writable executable directories for Git helpers.
        environment.update(
            {
                "PATH": "/usr/bin:/bin",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_PAGER": "cat",
                "PAGER": "cat",
            }
        )
        environment.pop("PYTHONPATH", None)
    return environment


def _stop_group(process: subprocess.Popen[bytes]) -> tuple[bool, int | None]:
    """即便主进程已退出，也清除其仍留在同一会话的后台子进程。"""
    ok = True
    cleanup_errno: int | None = None
    # macOS 上对仅剩僵尸主进程的组发信号会返回 EPERM；先 reap 主进程，
    # 若还有同组子进程，组仍存在，下面的 killpg 仍能清理它们。
    process.poll()
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError as exc:
        ok = False
        cleanup_errno = exc.errno
        try:
            process.kill()
        except ProcessLookupError:
            pass
        except OSError:
            pass
    try:
        process.wait(timeout=_CLEANUP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        ok = False
        cleanup_errno = errno.ETIMEDOUT
    return ok, cleanup_errno


def execute_policy_command(
    argv: list[str], *, cwd: Path, policy: SandboxPolicy, timeout: int | float,
    git_status: bool = False, output_limit_bytes: int | None = None,
) -> ExecutionResult:
    """执行已由原生后端包装的命令；超时/超量时终止整组。"""
    return _execute_policy_command(
        argv, cwd=cwd, policy=policy, timeout=timeout,
        git_status=git_status, output_limit_bytes=output_limit_bytes,
    )


def _execute_policy_command(
    argv: list[str], *, cwd: Path, policy: SandboxPolicy, timeout: int | float,
    git_status: bool = False, output_limit_bytes: int | None = None,
    pass_fds: tuple[int, ...] = (),
    on_spawn: Callable[[subprocess.Popen[bytes], float], None] | None = None,
) -> ExecutionResult:
    """Private process core with a narrowly scoped trusted-launch hook."""
    if os.name != "posix":
        return ExecutionResult(None, "", 0, "unsupported_platform", False, False, None)
    if (
        type(pass_fds) is not tuple
        or any(type(descriptor) is not int or descriptor < 0 for descriptor in pass_fds)
        or len(set(pass_fds)) != len(pass_fds)
    ):
        return ExecutionResult(None, "", 0, "invalid_handoff", False, True, None)

    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        return ExecutionResult(None, "", 0, "invalid_timeout", False, True, None)
    try:
        timeout_seconds = float(timeout)
    except (OverflowError, TypeError, ValueError):
        return ExecutionResult(None, "", 0, "invalid_timeout", False, True, None)
    if not math.isfinite(timeout_seconds):
        return ExecutionResult(None, "", 0, "invalid_timeout", False, True, None)
    if isinstance(timeout, int):
        # Preserve the existing integer API's one-second minimum while allowing
        # trusted internal callers to pass the remaining fractional deadline.
        timeout_seconds = max(1.0, timeout_seconds)
    elif timeout_seconds <= 0:
        return ExecutionResult(None, "", 0, "invalid_timeout", False, True, None)

    output_limit = policy.output_limit_bytes
    if output_limit_bytes is not None:
        try:
            requested_output_limit = int(output_limit_bytes)
        except (TypeError, ValueError, OverflowError):
            return ExecutionResult(None, "", 0, "invalid_output_limit", False, True, None)
        if requested_output_limit < 1:
            return ExecutionResult(None, "", 0, "invalid_output_limit", False, True, None)
        output_limit = min(output_limit, requested_output_limit)

    deadline = time.monotonic() + min(timeout_seconds, policy.wall_timeout_seconds)
    try:
        launch_options = {"pass_fds": pass_fds} if pass_fds else {}
        process = subprocess.Popen(  # noqa: S603 - argv 经原生策略包装且 shell=False
            argv, cwd=str(cwd),
            env=_policy_environment(policy.workspace_root, git_status=git_status),
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            shell=False, start_new_session=True, **launch_options,
        )
    except (OSError, ValueError):
        return ExecutionResult(None, "", 0, "launch_failed", False, True, None)

    chunks: list[bytes] = []
    output_bytes = 0
    error: str | None = None
    selector = selectors.DefaultSelector()
    try:
        assert process.stdout is not None
        if on_spawn is not None:
            try:
                on_spawn(process, deadline)
            except Exception:  # noqa: BLE001 - trusted handoff failure denies execution.
                error = "proxy_setup_failed"
        if error is None:
            selector.register(process.stdout, selectors.EVENT_READ)
        while error is None and (selector.get_map() or process.poll() is None):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                error = "timeout"
                break
            if not selector.get_map():
                try:
                    process.wait(timeout=remaining)
                except subprocess.TimeoutExpired:
                    error = "timeout"
                    break
                continue
            for key, _ in selector.select(remaining):
                chunk = os.read(
                    key.fd,
                    min(_READ_CHUNK_BYTES, output_limit - output_bytes + 1),
                )
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                remaining_bytes = output_limit - output_bytes
                chunks.append(chunk[:remaining_bytes])
                output_bytes += min(len(chunk), remaining_bytes)
                if len(chunk) > remaining_bytes:
                    error = "output_limit"
                    break
            if error is not None:
                break
    except OSError:
        error = "read_failed"
    finally:
        selector.close()
        cleanup_ok, cleanup_errno = _stop_group(process)
        if process.stdout is not None:
            process.stdout.close()

    raw_output = b"".join(chunks)
    return ExecutionResult(
        process.returncode,
        raw_output.decode("utf-8", errors="replace"),
        output_bytes,
        error if cleanup_ok else "cleanup_failed",
        error == "output_limit",
        cleanup_ok,
        cleanup_errno,
        raw_output,
    )


def execute_linux_leased_connect_candidate(
    argv: list[str], *, cwd: Path, sandbox: object,
    policy: SandboxPolicy, scope: object, timeout: int | float,
    output_limit_bytes: int | None = None,
) -> ExecutionResult:
    """Run one trusted Linux proxy candidate with helper/session ownership.

    This is a staged integration seam only: it is not registered as an Agent
    tool and does not change ``execute_policy_command`` or the worker DENY
    policy. A trusted caller must supply a current, policy-bound host lease
    scope. Product exposure remains blocked on the OS proxy-only conformance
    gate and explicit approval workflow.
    """
    if not sys.platform.startswith("linux"):
        return ExecutionResult(None, "", 0, "unsupported_platform", False, False, None)

    from .isolation import LandlockSandbox
    from .network_proxy_scope import HostHttpsConnectScope
    from .network_proxy_server import LinuxHostConnectProxySession
    from .linux_proxy_handoff import create_loopback_listener_handoff_channel
    from .sandbox_policy import NetworkMode

    if (
        not isinstance(sandbox, LandlockSandbox)
        or not isinstance(policy, SandboxPolicy)
        or policy.network_mode is not NetworkMode.DENY
        or policy.allowed_domains
        or not isinstance(scope, HostHttpsConnectScope)
    ):
        return ExecutionResult(None, "", 0, "invalid_proxy_scope", False, True, None)
    scope_validated = False
    host_control: socket.socket | None = None
    sender_control: socket.socket | None = None
    try:
        scope.validate_policy_binding(policy)
        scope_validated = True
        workspace = policy.workspace_root.resolve(strict=True)
        working_directory = Path(cwd).resolve(strict=True)
        working_directory.relative_to(workspace)
        if not working_directory.is_dir():
            raise ValueError("cwd is not a directory")
        if (
            not isinstance(argv, list)
            or not argv
            or any(type(part) is not str or "\x00" in part for part in argv)
            or not argv[0]
        ):
            raise ValueError("invalid argv")
        host_control, sender_control = create_loopback_listener_handoff_channel()
        wrapped = sandbox.wrap_leased_connect_candidate(
            argv, policy=policy, sender_control=sender_control,
        )
    except (OSError, RuntimeError, TypeError, ValueError):
        if sender_control is not None:
            sender_control.close()
        if host_control is not None:
            host_control.close()
        cleanup_ok = True
        if scope_validated:
            try:
                cleanup_ok = scope.close()
            except Exception:  # noqa: BLE001 - scope cleanup failure is not success.
                cleanup_ok = False
        return ExecutionResult(
            None, "", 0, "proxy_setup_failed" if cleanup_ok else "cleanup_failed",
            False, cleanup_ok, None if cleanup_ok else errno.EBUSY,
        )
    except BaseException:
        if sender_control is not None:
            sender_control.close()
        if host_control is not None:
            host_control.close()
        if scope_validated:
            try:
                scope.close()
            except BaseException:
                pass
        raise

    session: LinuxHostConnectProxySession | None = None
    scope_cleanup_ok = True

    def start_handoff(process: subprocess.Popen[bytes], deadline: float) -> None:
        nonlocal session, host_control
        assert sender_control is not None
        sender_control.close()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("proxy handoff deadline elapsed")
        if remaining <= 5.0:
            handoff_timeout = remaining / 2.0
            ready_timeout = remaining - handoff_timeout
        else:
            handoff_timeout = 5.0
            ready_timeout = min(1.0, remaining - handoff_timeout)
        if host_control is None:
            raise RuntimeError("proxy handoff control socket is unavailable")
        session = LinuxHostConnectProxySession(
            host_control,
            expected_pid=process.pid,
            scope=scope,
            handoff_timeout_seconds=handoff_timeout,
            ready_timeout_seconds=ready_timeout,
        )
        host_control = None
        session.start()

    result: ExecutionResult
    try:
        assert sender_control is not None
        result = _execute_policy_command(
            wrapped,
            cwd=working_directory,
            policy=policy,
            timeout=timeout,
            output_limit_bytes=output_limit_bytes,
            pass_fds=(sender_control.fileno(),),
            on_spawn=start_handoff,
        )
    finally:
        descriptor_cleanup_ok = True
        try:
            if sender_control is not None:
                sender_control.close()
        except OSError:
            descriptor_cleanup_ok = False
        if host_control is not None:
            try:
                host_control.close()
            except OSError:
                descriptor_cleanup_ok = False
        try:
            scope_cleanup_ok = (
                session.close() if session is not None else scope.close()
            ) and descriptor_cleanup_ok
        except Exception:  # noqa: BLE001 - no unconfirmed proxy cleanup is reported as success.
            scope_cleanup_ok = False
    cleanup_ok = result.cleanup_ok and scope_cleanup_ok
    if not cleanup_ok:
        return ExecutionResult(
            result.exit_code, result.output, result.output_bytes,
            "cleanup_failed", result.output_truncated, False,
            result.cleanup_errno or errno.EBUSY, result.raw_output,
        )
    return result
